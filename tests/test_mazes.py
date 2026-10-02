"""Every collectable in a game has to be collectable.

Run from the repo root:  python3 tests/test_mazes.py

Lumen Run ended a grid when the pellet count hit zero, and 17 of its 125
lumens were sealed behind walls — the whole top-right wing including one of
the four sunbursts, plus two pockets along the bottom. The count could never
reach zero, so the grid could never be cleared: no level 2, no clear bonus,
and a row of dots that visibly refused to be eaten.

The game now strips unreachable pellets at runtime so a bad edit can't make
it uncompletable. This test is the other half: it fails the EDIT, loudly,
instead of letting the runtime quietly paper over it.

Neon Breach gets the same treatment — a drone spawned in a sealed pocket
would be unkillable, and the wave would never end.
"""
import pathlib
import re
import sys
from collections import deque

ROOT = pathlib.Path(__file__).resolve().parent.parent
fails = []


def check(label, cond, detail=""):
    print(f"{'  ok ' if cond else 'FAIL '} {label}{(' — ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(label)


def grid_from(html, const):
    src = (ROOT / "arcade" / html).read_text()
    block = re.search(rf"const {const} = \[(.*?)\];", src, re.S)
    assert block, f"no {const} array in {html}"
    return re.findall(r'"([^"]*)"', block.group(1))


def flood(rows, start, solid, wrap=True):
    h, w = len(rows), len(rows[0])
    seen = {start}
    q = deque([start])
    while q:
        r, c = q.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr = r + dr
            nc = (c + dc) % w if wrap else c + dc
            if not (0 <= nr < h) or not (0 <= nc < w):
                continue
            if rows[nr][nc] in solid or (nr, nc) in seen:
                continue
            seen.add((nr, nc))
            q.append((nr, nc))
    return seen


# --- Lumen Run --------------------------------------------------------------
maze = grid_from("lumenrun.html", "MAZE")
widths = {len(r) for r in maze}
check("lumen run: every row is the same width", len(widths) == 1, str(widths))

# SPAWN in the game is {cx: 8, cy: 12}
spawn = (12, 8)
check("lumen run: the runner spawns on open floor", maze[spawn[0]][spawn[1]] != "#")

open_cells = flood(maze, spawn, "#")
pellets = [(r, c) for r, row in enumerate(maze)
           for c, ch in enumerate(row) if ch in ".o"]
stuck = [p for p in pellets if p not in open_cells]
check(f"lumen run: all {len(pellets)} lumens are reachable",
      not stuck, f"{len(stuck)} walled off at {stuck[:6]}")

bursts = [p for p in pellets if maze[p[0]][p[1]] == "o"]
check(f"lumen run: all {len(bursts)} sunbursts are reachable",
      all(b in open_cells for b in bursts))
check("lumen run: there are still four sunbursts", len(bursts) == 4, str(len(bursts)))

# --- Neon Breach ------------------------------------------------------------
arena = grid_from("neonbreach.html", "MAP")
widths = {len(r) for r in arena}
check("neon breach: every row is the same width", len(widths) == 1, str(widths))

# reset() puts the player at px 7.5, py 10.5 -> tile (10, 7)
pspawn = (10, 7)
check("neon breach: the player spawns on open floor",
      arena[pspawn[0]][pspawn[1]] not in "#=%")

reachable = flood(arena, pspawn, "#=%", wrap=False)
floor = [(r, c) for r, row in enumerate(arena)
         for c, ch in enumerate(row) if ch not in "#=%"]
sealed = [p for p in floor if p not in reachable]
check(f"neon breach: all {len(floor)} floor tiles are reachable",
      not sealed, f"{len(sealed)} sealed at {sealed[:6]}")

check("neon breach: the arena is walled in",
      all(ch == "#" for ch in arena[0]) and all(ch == "#" for ch in arena[-1])
      and all(r[0] == "#" and r[-1] == "#" for r in arena))

print("\n" + ("ALL PASS" if not fails else f"FAILURES: {fails}"))
sys.exit(1 if fails else 0)
