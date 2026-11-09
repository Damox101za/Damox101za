"""Network-themed contribution graph.

Draws the last year of GitHub contributions as a network: each day with
contributions is a node, empty days are idle ports. A data packet leaves the
core switch, follows a fibre route through every active node week by week,
and each node lights up with a ping as the packet arrives.

Usage:
    GITHUB_TOKEN=... python3 network_graph.py <github-username> <output-dir>
    python3 network_graph.py --sample <output-dir>      # offline test data
"""
import json
import math
import os
import random
import sys
import urllib.request
from pathlib import Path

CELL, GAP = 11, 3
STEP = CELL + GAP
LEFT, TOP = 74, 40          # room for the core switch and the title
TRAVEL_S = 16.0             # time for the packet to cover the whole route
HOLD_S, FADE_S = 3.0, 1.0   # lit network stays up, then fades and loops
TOTAL_S = TRAVEL_S + HOLD_S + FADE_S

THEMES = {
    "dark": {
        "bg": "#0d1117", "port": "#161b22", "port_stroke": "#21262d",
        "levels": ["#3b1f78", "#5b2bbf", "#8b5cf6", "#c4b5fd"],
        "packet": "#22d3ee", "fibre": "#22d3ee", "text": "#8b949e",
        "title": "#e6edf3", "switch": "#1f2937", "switch_stroke": "#7c3aed",
    },
    "light": {
        "bg": "#ffffff", "port": "#ebedf0", "port_stroke": "#d0d7de",
        "levels": ["#ddd6fe", "#a78bfa", "#7c3aed", "#4c1d95"],
        "packet": "#0891b2", "fibre": "#0891b2", "text": "#57606a",
        "title": "#1f2328", "switch": "#f3f0ff", "switch_stroke": "#7c3aed",
    },
}

LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
          "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}

QUERY = """query($login: String!) { user(login: $login) { contributionsCollection {
  contributionCalendar { totalContributions weeks { contributionDays {
    contributionCount contributionLevel weekday } } } } } }"""


def fetch(login: str):
    token = os.environ["GITHUB_TOKEN"]
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=body,
        headers={"Authorization": f"bearer {token}", "User-Agent": "network-graph"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if "errors" in data:
        raise SystemExit(f"GitHub API error: {data['errors']}")
    cal = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    weeks = [[(d["weekday"], LEVELS[d["contributionLevel"]]) for d in w["contributionDays"]]
             for w in cal["weeks"]]
    return cal["totalContributions"], weeks


def sample():
    rng = random.Random(7)
    weeks = []
    for w in range(53):
        days = range(7) if w < 52 else range(3)
        busy = 0.25 + 0.45 * (0.5 + 0.5 * math.sin(w / 6))
        weeks.append([(d, rng.choice([1, 1, 2, 2, 3, 4]) if rng.random() < busy else 0)
                      for d in days])
    total = sum(lvl * 3 for w in weeks for _, lvl in w)
    return total, weeks


def build(total: int, weeks, theme: dict) -> str:
    cols = len(weeks)
    width = LEFT + cols * STEP + 16
    height = TOP + 7 * STEP + 34
    centre = lambda c, r: (LEFT + c * STEP + CELL / 2, TOP + r * STEP + CELL / 2)

    # Route: core switch -> every active node, week by week, alternating
    # top-down / bottom-up so the fibre snakes instead of zig-zagging.
    core = (30, TOP + 3 * STEP + CELL / 2)
    nodes = []
    for c, week in enumerate(weeks):
        active = sorted((d, lvl) for d, lvl in week if lvl)
        if c % 2:
            active.reverse()
        nodes += [(c, d, lvl) for d, lvl in active]

    points = [core] + [centre(c, r) for c, r, _ in nodes]
    dists = [0.0]
    for a, b in zip(points, points[1:]):
        dists.append(dists[-1] + math.dist(a, b))
    route_len = dists[-1] or 1.0

    def kt(t: float) -> str:
        return f"{min(max(t / TOTAL_S, 0), 1):.5f}"

    fade_start = kt(TRAVEL_S + HOLD_S)
    loop = f'dur="{TOTAL_S}s" repeatCount="indefinite"'
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">',
        '<defs><filter id="glow" x="-50%" y="-50%" width="200%" height="200%">'
        '<feGaussianBlur stdDeviation="2.2" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>',
        f'<rect width="100%" height="100%" rx="8" fill="{theme["bg"]}"/>',
        f'<text x="16" y="24" font-size="13" font-weight="700" fill="{theme["title"]}">'
        f'⚡ packet trace</text>',
        f'<text x="{width - 16}" y="24" font-size="11" text-anchor="end" fill="{theme["text"]}">'
        f'{total} contributions · {len(nodes)} active nodes · last 12 months</text>',
    ]

    # Idle ports and dim nodes (the network before the packet arrives).
    for c, week in enumerate(weeks):
        for d, lvl in week:
            x, y = LEFT + c * STEP, TOP + d * STEP
            if lvl:
                out.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" '
                           f'fill="{theme["levels"][lvl - 1]}" opacity="0.28"/>')
            else:
                out.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" '
                           f'fill="{theme["port"]}" stroke="{theme["port_stroke"]}" stroke-width="0.6"/>')

    # Core switch with blinking LEDs.
    sx, sy = 12, core[1] - 13
    out.append(f'<rect x="{sx}" y="{sy}" width="40" height="26" rx="4" fill="{theme["switch"]}" '
               f'stroke="{theme["switch_stroke"]}" stroke-width="1.2"/>')
    for i in range(4):
        out.append(f'<circle cx="{sx + 8 + i * 8}" cy="{sy + 9}" r="1.8" fill="{theme["packet"]}">'
                   f'<animate attributeName="opacity" values="1;0.2;1" dur="{0.6 + i * 0.25:.2f}s" '
                   f'repeatCount="indefinite"/></circle>')
    out.append(f'<text x="{sx + 20}" y="{sy + 21}" font-size="7" text-anchor="middle" '
               f'fill="{theme["text"]}">CORE</text>')

    path_d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in points)
    group_fade = (f'<animate attributeName="opacity" values="1;1;0;0" '
                  f'keyTimes="0;{fade_start};{kt(TOTAL_S - 0.05)};1" {loop}/>')

    # Lit layer: fibre trail, node lights and pings. Fades out together at the end.
    out.append('<g>' + group_fade)
    out.append(f'<path d="{path_d}" fill="none" stroke="{theme["fibre"]}" stroke-width="1.1" '
               f'stroke-linejoin="round" opacity="0.45" stroke-dasharray="{route_len:.1f}" '
               f'stroke-dashoffset="{route_len:.1f}">'
               f'<animate attributeName="stroke-dashoffset" values="{route_len:.1f};0;0" '
               f'keyTimes="0;{kt(TRAVEL_S)};1" {loop}/></path>')
    for (c, r, lvl), dist in zip(nodes, dists[1:]):
        t = dist / route_len * TRAVEL_S
        x, y = LEFT + c * STEP, TOP + r * STEP
        cx, cy = x + CELL / 2, y + CELL / 2
        on, lit = kt(t), kt(t + 0.15)
        ping_end = kt(min(t + 0.9, TRAVEL_S + HOLD_S - 0.1))
        out.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" '
                   f'fill="{theme["levels"][lvl - 1]}" opacity="0">'
                   f'<animate attributeName="opacity" values="0;0;1;1" keyTimes="0;{on};{lit};1" {loop}/></rect>')
        out.append(f'<circle cx="{cx}" cy="{cy}" r="4" fill="none" stroke="{theme["packet"]}" '
                   f'stroke-width="1" opacity="0">'
                   f'<animate attributeName="r" values="4;4;13;13" keyTimes="0;{on};{ping_end};1" {loop}/>'
                   f'<animate attributeName="opacity" values="0;0;0.9;0;0" '
                   f'keyTimes="0;{on};{lit};{ping_end};1" {loop}/></circle>')
    out.append('</g>')

    # The packet itself, gliding at a constant speed along the route.
    out.append(f'<g filter="url(#glow)">{group_fade}'
               f'<circle r="3.2" fill="{theme["packet"]}">'
               f'<animateMotion path="{path_d}" keyPoints="0;1;1" keyTimes="0;{kt(TRAVEL_S)};1" '
               f'calcMode="linear" {loop}/></circle></g>')

    # Legend.
    ly = TOP + 7 * STEP + 20
    lx = width - 16 - 5 * STEP - 62
    out.append(f'<text x="{lx}" y="{ly + 9}" font-size="10" fill="{theme["text"]}">idle</text>')
    swatches = [theme["port"]] + theme["levels"]
    for i, colour in enumerate(swatches):
        out.append(f'<rect x="{lx + 28 + i * STEP}" y="{ly}" width="{CELL}" height="{CELL}" rx="2" fill="{colour}"/>')
    out.append(f'<text x="{lx + 28 + 5 * STEP + 4}" y="{ly + 9}" font-size="10" fill="{theme["text"]}">busy</text>')
    out.append(f'<text x="16" y="{ly + 9}" font-size="10" fill="{theme["text"]}">'
               f'● packet  ━ fibre route  ◌ ping</text>')

    out.append('</svg>')
    return "\n".join(out)


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    who, out_dir = sys.argv[1], Path(sys.argv[2])
    total, weeks = sample() if who == "--sample" else fetch(who)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, theme in THEMES.items():
        path = out_dir / f"network-graph-{name}.svg"
        path.write_text(build(total, weeks, theme), encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
