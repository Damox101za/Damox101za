"""Smooth out the Pac-Man contribution graph SVGs.

The generator rounds animation keyTimes to 4 decimals. Over a ~3 minute loop
that makes each 200 ms step last either 186 ms or 203 ms, so Pac-Man and the
ghosts visibly speed up and slow down. This snaps every keyTime back onto the
exact frame grid (frame / total_frames) with full precision.
"""
import re
import sys
from pathlib import Path


def smooth(path: Path) -> None:
    svg = path.read_text(encoding="utf-8")
    frames_match = re.search(r"<frames>(\d+)</frames>", svg)
    duration_match = re.search(r"<durationMs>(\d+)</durationMs>", svg)
    if not frames_match or not duration_match:
        print(f"{path.name}: no frame metadata, left unchanged")
        return
    frames = int(frames_match.group(1))
    loop_dur = f'dur="{duration_match.group(1)}ms"'

    def fix_keytimes(match: re.Match) -> str:
        tag = match.group(0)
        if loop_dur not in tag:
            return tag  # only touch animations that run on the main loop
        def snap(kt: re.Match) -> str:
            times = [float(t) for t in kt.group(1).split(";")]
            snapped, last = [], 0.0
            for t in times:
                value = max(round(t * frames) / frames, last)  # keep order
                snapped.append(value)
                last = value
            snapped[0], snapped[-1] = times[0], times[-1]
            return 'keyTimes="' + ";".join(f"{t:.6f}".rstrip("0").rstrip(".") or "0" for t in snapped) + '"'
        return re.sub(r'keyTimes="([^"]*)"', snap, tag)

    fixed = re.sub(r"<animate(?:Transform|Motion)?\b[^>]*>", fix_keytimes, svg, flags=re.S)
    path.write_text(fixed, encoding="utf-8")
    print(f"{path.name}: keyTimes snapped to {frames} frames")


if __name__ == "__main__":
    for file in sys.argv[1:]:
        smooth(Path(file))
