"""Network-themed contribution graph (styled to match Commit Kaiju).

Draws the last year of GitHub contributions as a network: each day with
contributions is a node, empty days are idle ports. A data packet leaves a
pixel-art core switch, follows a fibre route through every active node week by
week, and each node lights up with a ping as the packet arrives while a counter
tallies the nodes brought online. Then the network reboots and loops.

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
HEIGHT = 162                # same height as the kaiju graph
PX = 3                      # switch pixel size
TRAVEL_S = 18.0             # time for the packet to cover the whole route
HOLD_S, FADE_S = 2.0, 1.5   # lit network stays up, then reboots and loops
TOTAL_S = TRAVEL_S + HOLD_S + FADE_S

# Pixel-art core switch: F frame, C chassis, P port, A antenna.
SWITCH = [
    "..A.........A..",
    "..A.........A..",
    "FFFFFFFFFFFFFFF",
    "FCCCCCCCCCCCCCF",
    "FCPPCPPCPPCPPCF",
    "FCCCCCCCCCCCCCF",
    "FCPPCPPCPPCPPCF",
    "FCCCCCCCCCCCCCF",
    "FFFFFFFFFFFFFFF",
    ".F...........F.",
]
LEDS = [(2, 3), (5, 3), (8, 3), (11, 3), (2, 5), (5, 5), (8, 5), (11, 5)]

THEMES = {
    "dark": {
        "bg": "#0d1117", "star": "#30363d", "port": "#161b22", "port_stroke": "#21262d",
        "levels": ["#4c2a9a", "#5b2bbf", "#8b5cf6", "#c4b5fd"],
        "packet": "#22d3ee", "fibre": "#22d3ee", "text": "#8b949e", "title": "#e6edf3",
        "F": "#7c3aed", "C": "#1f1638", "P": "#30363d", "A": "#a78bfa",
    },
    "light": {
        "bg": "#ffffff", "star": "#eaeef2", "port": "#ebedf0", "port_stroke": "#d0d7de",
        "levels": ["#ddd6fe", "#a78bfa", "#7c3aed", "#4c1d95"],
        "packet": "#0891b2", "fibre": "#0891b2", "text": "#57606a", "title": "#1f2328",
        "F": "#7c3aed", "C": "#f3f0ff", "P": "#d0d7de", "A": "#7c3aed",
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


def kt(t: float) -> str:
    return f"{min(max(t / TOTAL_S, 0), 1):.5f}"


def build(total: int, weeks, theme: dict) -> str:
    cols = len(weeks)
    width = LEFT + cols * STEP + 16
    height = HEIGHT
    centre = lambda c, r: (LEFT + c * STEP + CELL / 2, TOP + r * STEP + CELL / 2)

    # Route: core switch -> every active node, week by week, alternating
    # top-down / bottom-up so the fibre snakes instead of zig-zagging.
    sw_w, sw_h = len(SWITCH[0]) * PX, len(SWITCH) * PX
    sx, sy = 14, TOP + 3 * STEP + CELL / 2 - sw_h / 2
    core = (sx + sw_w, sy + 5 * PX)
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
    arrive = [d / route_len * TRAVEL_S for d in dists[1:]]

    reboot = TRAVEL_S + HOLD_S
    loop = f'dur="{TOTAL_S}s" repeatCount="indefinite"'
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">',
        '<defs><filter id="glow" x="-100%" y="-100%" width="300%" height="300%">'
        '<feGaussianBlur stdDeviation="2" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>',
        f'<rect width="100%" height="100%" rx="8" fill="{theme["bg"]}"/>',
    ]
    rng = random.Random(11)
    for _ in range(40):
        out.append(f'<rect x="{rng.uniform(8, width - 8):.0f}" y="{rng.uniform(30, height - 24):.0f}" '
                   f'width="1.5" height="1.5" fill="{theme["star"]}"/>')
    out.append(f'<text x="16" y="24" font-size="13" font-weight="700" fill="{theme["title"]}">'
               f'🛰️ network activity</text>')
    out.append(f'<text x="{width - 16}" y="24" font-size="11" text-anchor="end" fill="{theme["text"]}">'
               f'{total} contributions in the last year</text>')

    # Idle ports and dim nodes (the network before the packet arrives).
    for c, week in enumerate(weeks):
        for d, lvl in week:
            x, y = LEFT + c * STEP, TOP + d * STEP
            if lvl:
                out.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="1" '
                           f'fill="{theme["levels"][lvl - 1]}" opacity="0.28"/>')
            else:
                out.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="1" '
                           f'fill="{theme["port"]}" stroke="{theme["port_stroke"]}" stroke-width="0.6"/>')

    # Pixel-art core switch with blinking port LEDs.
    out.append(f'<g shape-rendering="crispEdges">')
    for y, row in enumerate(SWITCH):
        for x, ch in enumerate(row):
            if ch != ".":
                out.append(f'<rect x="{sx + x * PX}" y="{sy + y * PX}" width="{PX}" height="{PX}" fill="{theme[ch]}"/>')
    for i, (lx, ly) in enumerate(LEDS):
        out.append(f'<rect x="{sx + lx * PX}" y="{sy + ly * PX}" width="{PX}" height="{PX}" fill="{theme["packet"]}">'
                   f'<animate attributeName="opacity" values="1;0.15;1" dur="{0.5 + (i * 0.37) % 1.1:.2f}s" '
                   f'calcMode="discrete" repeatCount="indefinite"/></rect>')
    out.append('</g>')
    out.append(f'<text x="{sx + sw_w / 2}" y="{sy + sw_h + 10}" font-size="7" text-anchor="middle" '
               f'fill="{theme["text"]}">CORE</text>')

    path_d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in points)
    group_fade = (f'<animate attributeName="opacity" values="1;1;0;0" '
                  f'keyTimes="0;{kt(reboot)};{kt(TOTAL_S - 0.05)};1" {loop}/>')

    # Lit layer: fibre trail, node lights and pings. Fades out together at the end.
    out.append('<g>' + group_fade)
    out.append(f'<path d="{path_d}" fill="none" stroke="{theme["fibre"]}" stroke-width="1.1" '
               f'stroke-linejoin="round" opacity="0.45" stroke-dasharray="{route_len:.1f}" '
               f'stroke-dashoffset="{route_len:.1f}">'
               f'<animate attributeName="stroke-dashoffset" values="{route_len:.1f};0;0" '
               f'keyTimes="0;{kt(TRAVEL_S)};1" {loop}/></path>')
    for (c, r, lvl), t in zip(nodes, arrive):
        x, y = LEFT + c * STEP, TOP + r * STEP
        cx, cy = x + CELL / 2, y + CELL / 2
        on, lit = kt(t), kt(t + 0.15)
        ping_end = kt(min(t + 0.9, reboot - 0.1))
        out.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="1" '
                   f'fill="{theme["levels"][lvl - 1]}" opacity="0">'
                   f'<animate attributeName="opacity" values="0;0;1;1" keyTimes="0;{on};{lit};1" {loop}/></rect>')
        out.append(f'<circle cx="{cx}" cy="{cy}" r="4" fill="none" stroke="{theme["packet"]}" '
                   f'stroke-width="1" opacity="0">'
                   f'<animate attributeName="r" values="4;4;13;13" keyTimes="0;{on};{ping_end};1" {loop}/>'
                   f'<animate attributeName="opacity" values="0;0;0.9;0;0" '
                   f'keyTimes="0;{on};{lit};{ping_end};1" {loop}/></circle>')
    out.append('</g>')

    # The packet: a glowing pixel gliding at a constant speed along the route.
    out.append(f'<g filter="url(#glow)">{group_fade}'
               f'<rect x="-3" y="-3" width="6" height="6" fill="{theme["packet"]}" shape-rendering="crispEdges">'
               f'<animateMotion path="{path_d}" keyPoints="0;1;1" keyTimes="0;{kt(TRAVEL_S)};1" '
               f'calcMode="linear" {loop}/></rect></g>')

    # Counter (bottom left), one label per change, like the kaiju's tally.
    base = height - 10
    marks = [(0.0, 0)] + [(t, i + 1) for i, t in enumerate(arrive)]
    for j, (t, n) in enumerate(marks):
        t_next = marks[j + 1][0] if j + 1 < len(marks) else reboot
        if t_next <= t and j + 1 < len(marks):
            continue  # two nodes lit at the same instant: skip the in-between label
        vis = [(0, 0), (t, 1), (t_next, 0), (TOTAL_S, 0)] if t > 0 else [(0, 1), (t_next, 0), (TOTAL_S, 0)]
        out.append(f'<text x="16" y="{base}" font-size="11" font-weight="700" fill="{theme["title"]}" '
                   f'opacity="{1 if t == 0 else 0}">📡 {n} nodes online'
                   f'<animate attributeName="opacity" values="{";".join(str(v) for _, v in vis)}" '
                   f'keyTimes="{";".join(kt(x) for x, _ in vis)}" calcMode="discrete" {loop}/></text>')
    out.append(f'<text x="16" y="{base}" font-size="11" font-weight="700" fill="{theme["title"]}" opacity="0">'
               f'🔄 rebooting the network…'
               f'<animate attributeName="opacity" values="0;0;1;1;0" '
               f'keyTimes="0;{kt(reboot)};{kt(reboot + 0.01)};{kt(TOTAL_S - 0.01)};1" calcMode="discrete" {loop}/></text>')

    # Legend (bottom right).
    lx = width - 16 - 5 * STEP - 62
    out.append(f'<text x="{lx}" y="{base}" font-size="10" fill="{theme["text"]}">idle</text>')
    for i, colour in enumerate([theme["port"]] + theme["levels"]):
        out.append(f'<rect x="{lx + 28 + i * STEP}" y="{base - 9}" width="{CELL}" height="{CELL}" rx="1" fill="{colour}"/>')
    out.append(f'<text x="{lx + 28 + 5 * STEP + 4}" y="{base}" font-size="10" fill="{theme["text"]}">busy</text>')

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
