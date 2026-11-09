"""Commit Kaiju: a monster stomps through the city of your contributions.

Each week of the last year is a building: every day with contributions adds a
floor, coloured by how busy that day was. An original pixel-art kaiju walks
across the skyline, flattening each building in a cloud of dust (the busiest
weeks get a breath blast first) while a counter tallies the commits destroyed.
Then the city rebuilds and the loop starts again.

Usage:
    GITHUB_TOKEN=... python3 kaiju_graph.py <github-username> <output-dir>
    python3 kaiju_graph.py --sample <output-dir>      # offline test data
"""
import json
import math
import os
import random
import sys
import urllib.request
from pathlib import Path

COL, BW = 14, 11            # building pitch and width
FLOOR, FGAP = 6, 1          # floor height and gap between floors
LEFT = 24
GROUND = 132                # y of the street
PX = 5                      # kaiju pixel size
WALK_S, HOLD_S, REBUILD_S = 18.0, 2.0, 1.5
TOTAL_S = WALK_S + HOLD_S + REBUILD_S

# Original kaiju sprite, facing right. B body, D dark, S spines, E eye,
# W teeth, L belly.
BODY = [
    "...........DBBBB...",
    "..........BBBBBBB..",
    ".....S....BBBBEBBB.",
    "....SS...BBBBBBBBBB",
    "...SSS..BBBBBBWW...",
    "...SS.BBBBBBBB.....",
    "..SS.BBBBBBBBBB....",
    "..S.BBBBLLBBBB.B...",
    ".S.BBBBLLLLBBB.B...",
    "D..BBBBLLLLBBBB....",
    "DD.BBBBLLLLBBB.....",
    ".DDBBBBBLLBBBB.....",
    "..DDBBBBBBBBB......",
]
LEGS_A = ["....BBB...BBB......", "....BB.....BB......", "...DDD....DDD......"]
LEGS_B = [".....BBB.BBB.......", "......BB.BB........", ".....DDD.DDD......."]
SPRITE_W, SPRITE_H = len(BODY[0]) * PX, (len(BODY) + 3) * PX
MOUTH = (16 * PX, 4 * PX + 1)

THEMES = {
    "dark": {
        "bg": "#0d1117", "star": "#30363d", "ground": "#30363d", "lot": "#21262d",
        "levels": ["#4c2a9a", "#5b2bbf", "#8b5cf6", "#c4b5fd"],
        "window": "#fde68a", "dim_window": "#a78bfa", "text": "#8b949e", "title": "#e6edf3",
        "B": "#7c3aed", "D": "#4c1d95", "S": "#22d3ee", "E": "#fde68a",
        "W": "#f8fafc", "L": "#a78bfa", "breath": "#22d3ee", "dust": "#6e7681",
    },
    "light": {
        "bg": "#ffffff", "star": "#eaeef2", "ground": "#d0d7de", "lot": "#ebedf0",
        "levels": ["#ddd6fe", "#a78bfa", "#7c3aed", "#4c1d95"],
        "window": "#f59e0b", "dim_window": "#7c3aed", "text": "#57606a", "title": "#1f2328",
        "B": "#7c3aed", "D": "#4c1d95", "S": "#0891b2", "E": "#fde047",
        "W": "#ffffff", "L": "#c4b5fd", "breath": "#06b6d4", "dust": "#afb8c1",
    },
}

LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
          "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}

QUERY = """query($login: String!) { user(login: $login) { contributionsCollection {
  contributionCalendar { totalContributions weeks { contributionDays {
    contributionCount contributionLevel } } } } } }"""


def fetch(login: str):
    token = os.environ["GITHUB_TOKEN"]
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=body,
        headers={"Authorization": f"bearer {token}", "User-Agent": "kaiju-graph"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if "errors" in data:
        raise SystemExit(f"GitHub API error: {data['errors']}")
    cal = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    return [[(d["contributionCount"], LEVELS[d["contributionLevel"]]) for d in w["contributionDays"]]
            for w in cal["weeks"]]


def sample():
    rng = random.Random(3)
    weeks = []
    for w in range(53):
        busy = 0.2 + 0.5 * (0.5 + 0.5 * math.sin(w / 5))
        days = []
        for _ in range(7 if w < 52 else 3):
            lvl = rng.choice([1, 1, 2, 2, 3, 4]) if rng.random() < busy else 0
            days.append((lvl * rng.randint(1, 4), lvl))
        weeks.append(days)
    return weeks


def kt(t: float) -> str:
    return f"{min(max(t / TOTAL_S, 0), 1):.5f}"


def keyed(attr: str, frames, extra: str = "") -> str:
    """SMIL animate over the main loop from (time, value) pairs."""
    frames = sorted(frames)
    times = ";".join(kt(t) for t, _ in frames)
    values = ";".join(str(v) for _, v in frames)
    return (f'<animate attributeName="{attr}" values="{values}" keyTimes="{times}" '
            f'dur="{TOTAL_S}s" repeatCount="indefinite"{extra}/>')


def sprite(rows, theme, y0=0) -> str:
    return "".join(
        f'<rect x="{x * PX}" y="{(y0 + y) * PX}" width="{PX}" height="{PX}" fill="{theme[ch]}"/>'
        for y, row in enumerate(rows) for x, ch in enumerate(row) if ch != ".")


def build(weeks, theme) -> str:
    cols = len(weeks)
    width = LEFT * 2 + cols * COL
    height = GROUND + 30
    total = sum(c for w in weeks for c, _ in w)
    x_start, x_end = -SPRITE_W - 10, width + 10
    speed = (x_end - x_start) / WALK_S
    rebuild = WALK_S + HOLD_S
    loop = f'dur="{TOTAL_S}s" repeatCount="indefinite"'

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">',
        f'<defs><clipPath id="above"><rect width="{width}" height="{GROUND}"/></clipPath></defs>',
        f'<rect width="100%" height="100%" rx="8" fill="{theme["bg"]}"/>',
    ]
    rng = random.Random(11)
    for _ in range(40):
        out.append(f'<rect x="{rng.uniform(8, width - 8):.0f}" y="{rng.uniform(34, 70):.0f}" '
                   f'width="1.5" height="1.5" fill="{theme["star"]}"/>')
    out.append(f'<text x="16" y="24" font-size="13" font-weight="700" fill="{theme["title"]}">'
               f'🦖 commit kaiju</text>')

    # City: the whole street shakes a little with each stomp.
    out.append(f'<g><animateTransform attributeName="transform" type="translate" '
               f'values="0,0;0,0.8;0,0;0,0" keyTimes="0;0.12;0.3;1" dur="0.5s" repeatCount="indefinite"/>')
    out.append(f'<rect x="0" y="{GROUND}" width="{width}" height="1.5" fill="{theme["ground"]}"/>')

    destroyed, tally = 0, []
    weekly = [sum(c for c, _ in w) for w in weeks]
    busiest = sorted(weekly, reverse=True)[max(len(weekly) // 8, 1) - 1] if any(weekly) else 0
    blasts = []
    for i, week in enumerate(weeks):
        bx = LEFT + i * COL
        floors = sorted((lvl for _, lvl in week if lvl), reverse=True)
        if not floors:
            out.append(f'<rect x="{bx}" y="{GROUND - 1.5}" width="{BW}" height="1.5" fill="{theme["lot"]}"/>')
            continue
        h = len(floors) * (FLOOR + FGAP)
        hit = (bx - SPRITE_W + 6 - x_start) / speed     # kaiju's snout reaches the building
        fall = hit + 0.6
        sink = [(0, 0), (hit, 0), (fall, h + 9), (rebuild, h + 9), (rebuild + REBUILD_S, 0), (TOTAL_S, 0)]
        out.append(f'<g clip-path="url(#above)"><g>'
                   f'<animateTransform attributeName="transform" type="translate" '
                   f'values="{";".join(f"0,{v}" for _, v in sink)}" '
                   f'keyTimes="{";".join(kt(t) for t, _ in sink)}" {loop}/>')
        for f, lvl in enumerate(floors):
            fy = GROUND - (f + 1) * (FLOOR + FGAP)
            out.append(f'<rect x="{bx}" y="{fy}" width="{BW}" height="{FLOOR}" rx="1" '
                       f'fill="{theme["levels"][lvl - 1]}"/>')
            # Windows: every floor has some, busier days have more and brighter ones.
            lit = theme["window"] if lvl >= 3 else theme["dim_window"]
            for wx in ((4.5,) if lvl == 1 else (2, 7)):
                out.append(f'<rect x="{bx + wx}" y="{fy + 2}" width="2" height="2" fill="{lit}"/>')
        if len(floors) >= 6:
            out.append(f'<rect x="{bx + BW / 2 - 0.5}" y="{GROUND - h - 6}" width="1" height="6" '
                       f'fill="{theme["levels"][-1]}"/>')
        out.append('</g></g>')

        # Rubble and dust.
        show = [(0, 0), (fall - 0.01, 0), (fall, 1), (rebuild, 1), (rebuild + 0.3, 0), (TOTAL_S, 0)]
        out.append(f'<g opacity="0">{keyed("opacity", show)}'
                   f'<path d="M{bx} {GROUND} l3 -3 l2 2 l3 -4 l3 5 z" fill="{theme["levels"][0]}"/></g>')
        for k in range(3):
            dx, r_end = (-3, 7, 3)[k], 6 + k * 2
            puff = [(0, 0), (hit, 0), (hit + 0.1, 0.8), (hit + 1.0, 0), (TOTAL_S, 0)]
            grow = [(0, 2), (hit, 2), (hit + 1.0, r_end), (TOTAL_S, r_end)]
            out.append(f'<circle cx="{bx + BW / 2 + dx}" cy="{GROUND - 3 - k * 3}" r="2" '
                       f'fill="{theme["dust"]}" opacity="0">{keyed("opacity", puff)}{keyed("r", grow)}</circle>')

        destroyed += weekly[i]
        tally.append((hit, destroyed))
        if busiest and weekly[i] >= busiest:
            blasts.append(hit)
    out.append('</g>')

    # Counter: one label per change, each shown until the next one.
    out.append(f'<text x="{width - 16}" y="24" font-size="11" text-anchor="end" fill="{theme["text"]}">'
               f'{total} contributions in the last year</text>')
    marks = [(0.0, 0)] + tally
    for j, (t, n) in enumerate(marks):
        t_next = marks[j + 1][0] if j + 1 < len(marks) else rebuild
        vis = [(0, 0), (t, 1), (t_next, 0), (TOTAL_S, 0)] if t > 0 else [(0, 1), (t_next, 0), (TOTAL_S, 0)]
        out.append(f'<text x="16" y="{height - 10}" font-size="11" font-weight="700" fill="{theme["title"]}" '
                   f'opacity="{1 if t == 0 else 0}">💥 {n} commits destroyed'
                   f'<animate attributeName="opacity" values="{";".join(str(v) for _, v in vis)}" '
                   f'keyTimes="{";".join(kt(x) for x, _ in vis)}" calcMode="discrete" {loop}/></text>')
    out.append(f'<text x="16" y="{height - 10}" font-size="11" font-weight="700" fill="{theme["title"]}" '
               f'opacity="0">🏗️ rebuilding the city…'
               f'{keyed("opacity", [(0, 0), (rebuild, 0), (rebuild + 0.01, 1), (TOTAL_S - 0.01, 1), (TOTAL_S, 0)])}</text>')

    # The kaiju: walks at a steady pace, bobbing, legs alternating.
    ky = GROUND - SPRITE_H + 1
    out.append(f'<g><animateTransform attributeName="transform" type="translate" '
               f'values="{x_start},{ky};{x_end},{ky};{x_end},{ky}" keyTimes="0;{kt(WALK_S)};1" {loop}/>')
    out.append('<g shape-rendering="crispEdges"><animateTransform attributeName="transform" type="translate" '
               'values="0,0;0,-1.5;0,0" dur="0.5s" repeatCount="indefinite"/>')
    out.append(sprite(BODY, theme))
    for legs, phase in ((LEGS_A, "1;0"), (LEGS_B, "0;1")):
        out.append(f'<g>{sprite(legs, theme, len(BODY))}'
                   f'<animate attributeName="opacity" values="{phase}" dur="0.5s" calcMode="discrete" '
                   f'repeatCount="indefinite"/></g>')
    # Spines glow, and a breath blast fires just before each of the busiest weeks.
    for hit in blasts:
        on = [(0, 0), (hit - 0.45, 0), (hit - 0.4, 1), (hit + 0.1, 1), (hit + 0.2, 0), (TOTAL_S, 0)]
        mx, my = MOUTH
        out.append(f'<path d="M{mx} {my} L{mx + 22} {my - 4} L{mx + 26} {my + 6} L{mx + 22} {my + 12} Z" '
                   f'fill="{theme["breath"]}" opacity="0">{keyed("opacity", [(t, v * 0.85) for t, v in on])}</path>')
    out.append('</g></g>')

    out.append('</svg>')
    return "\n".join(out)


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    who, out_dir = sys.argv[1], Path(sys.argv[2])
    weeks = sample() if who == "--sample" else fetch(who)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, theme in THEMES.items():
        path = out_dir / f"kaiju-graph-{name}.svg"
        path.write_text(build(weeks, theme), encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
