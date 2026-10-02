"""Generate the three 640x360 cover images BotFather asks for.

Run:  python3 tools/make_game_covers.py [outdir]

They are drawn to match arcade/sl.css exactly — same palette, same mono
type, same amber bloom — so the card Telegram shows and the game it opens
look like the same product. 640x360 is BotFather's required size.
"""
import math
import pathlib
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

W, H = 640, 360
SS = 2                      # supersample, then downscale — cheap antialiasing

# straight from arcade/sl.css — cold is the machine, warm is you
BG      = (4, 3, 12)        # --void
DECK    = (10, 10, 31)      # --deck
GRID    = (27, 31, 74)      # --grid
NEON    = (25, 230, 255)    # --neon   the city, UI chrome
HOT     = (255, 46, 136)    # --hot    danger
SHADOW  = (157, 78, 221)    # --volt   the shadow mass
LIGHT   = (255, 201, 60)    # --light  you
GLOW    = (255, 165, 43)    # the light's halo
GOOD    = (43, 255, 207)    # --mint   pickups
INK     = (232, 244, 255)   # --ink
DIM     = (90, 106, 154)    # --dim

MONO  = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONOB = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"


def font(path, size):
    return ImageFont.truetype(path, size * SS)


def tracked(d, xy, text, f, fill, track=0):
    """Draw text with letter-spacing, which Pillow has no setting for."""
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + track * SS
    return x


def tracked_width(d, text, f, track=0):
    return sum(d.textlength(c, font=f) + track * SS for c in text)


def base():
    """Night, with the city glowing just past the bottom edge.

    Matches the radial-gradient on body in sl.css: the source of light is
    always below the frame, which is what makes the dark feel like a place
    rather than an empty background.
    """
    img = Image.new("RGB", (W * SS, H * SS), BG)
    d = ImageDraw.Draw(img)
    cx, cy = W * SS * 0.5, H * SS * 1.18
    rmax = H * SS * 0.95
    for y in range(H * SS):
        for_x = []
        dy = (y - cy) / rmax
        t = min(1.0, abs(dy))
        k = (1 - t) ** 2.2
        d.line([(0, y), (W * SS, y)],
               fill=(int(BG[0] + 16 * k), int(BG[1] + 22 * k), int(BG[2] + 61 * k)))
    return img


def scanlines(img, period=3, strength=58):
    """CRT line structure, same 2px-on/1px-off rhythm as sl.css."""
    d = ImageDraw.Draw(img)
    for y in range(0, H * SS, period * SS):
        for yy in range(y, min(y + SS, H * SS)):
            d.line([(0, yy), (W * SS, yy)], fill=(0, 0, 0))
    return Image.blend(img, img.filter(ImageFilter.GaussianBlur(0.4 * SS)), 0.35)


def horizon(d, y, colour=NEON, rows=7):
    """A perspective grid receding to the vanishing point."""
    for i in range(rows):
        t = i / rows
        yy = y + (H - y) * (t ** 1.9)
        a = 0.30 * (1 - t)
        d.line([(0, yy * SS), (W * SS, yy * SS)],
               fill=tuple(int(c * a) for c in colour), width=max(1, int(1.5 * SS)))
    for i in range(-9, 10):
        a = 0.22 * (1 - abs(i) / 10)
        d.line([(W * SS / 2 + i * 13 * SS, y * SS), (W * SS / 2 + i * 150 * SS, H * SS)],
               fill=tuple(int(c * a) for c in colour), width=max(1, int(1.2 * SS)))


def lay(img, art, radius=18):
    """Composite the art onto the background so light ADDS but dark stays dark.

    Screening a big blur over the whole frame lifts the background off the
    brand's near-black and the piece goes grey. Building the glow on black
    first, then taking the per-pixel maximum, keeps the empty areas at #07070d
    while the lit areas still bloom.
    """
    glow = art.filter(ImageFilter.GaussianBlur(radius * SS))
    lit = ImageChops.screen(art, glow)       # shapes + halo, on black
    return ImageChops.lighter(img, lit)      # never darkens, never washes


def finish(img, title, kicker="SPREADLIGHT ARCADE"):
    d = ImageDraw.Draw(img)
    f_kick = font(MONO, 12)
    f_title = font(MONOB, 40)

    tracked(d, (46 * SS, 44 * SS), kicker, f_kick, NEON, track=4)

    # The one loud moment, matching #msg h1 in sl.css: a misconverged CRT,
    # magenta bleeding left and cyan right from under the amber. Drawn as
    # three offset passes because that is literally what text-shadow does.
    tx, ty = 44 * SS, 68 * SS
    tracked(d, (tx - 2 * SS, ty), title.upper(), f_title, HOT, track=2)
    tracked(d, (tx + 2 * SS, ty), title.upper(), f_title, NEON, track=2)
    tracked(d, (tx, ty), title.upper(), f_title, LIGHT, track=2)

    # rule under the title, fading like a signal losing power
    y = 126 * SS
    tw = tracked_width(d, title.upper(), f_title, 2)
    steps = 60
    for i in range(steps):
        t = i / steps
        x0, x1 = 46 * SS + tw * t, 46 * SS + tw * (t + 1 / steps)
        a = (1 - t) ** 1.4
        d.line([(x0, y), (x1, y)],
               fill=(int(GLOW[0] * a + BG[0]), int(GLOW[1] * a + BG[1]),
                     int(GLOW[2] * a + BG[2])),
               width=2 * SS)

    img = scanlines(img)
    return img.resize((W, H), Image.LANCZOS)


def orb(d, cx, cy, r, colour, rings=5):
    """A light source: solid core, concentric falloff."""
    for i in range(rings, 0, -1):
        rr = r * i / rings * 2.4
        a = (1 - i / rings) ** 2 * 0.5
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                  fill=(int(colour[0] * a + BG[0] * (1 - a)),
                        int(colour[1] * a + BG[1] * (1 - a)),
                        int(colour[2] * a + BG[2] * (1 - a))))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=colour)


# --- Shadow Wave: thread the gap in an advancing wall of shadow -------------
def shadow_wave():
    img = base()
    art = Image.new("RGB", img.size, BG)
    d = ImageDraw.Draw(art)
    horizon(d, 300, NEON, rows=6)

    # stacked sine walls, each with a gap — the actual mechanic
    for n, (amp, yoff, gapx, alpha) in enumerate([
            (26, 250, 300, 0.30), (32, 290, 420, 0.55), (38, 330, 215, 1.0)]):
        col = tuple(int(c * alpha + BG[i] * (1 - alpha)) for i, c in enumerate(SHADOW))
        pts = []
        for x in range(0, W + 4, 4):
            y = yoff + math.sin(x / 46 + n * 1.3) * amp
            pts.append((x * SS, y * SS))
        for i in range(len(pts) - 1):
            x = pts[i][0] / SS
            if abs(x - gapx) < 46:          # the gap you aim for
                continue
            d.line([pts[i], pts[i + 1]], fill=col, width=9 * SS)

    orb(d, 215 * SS, 292 * SS, 9 * SS, LIGHT)   # player, lined up on the gap
    for i, dy in enumerate([20, 36, 50]):       # motion trail behind it
        a = 0.4 - i * 0.12
        d.ellipse([(215 - 4) * SS, (292 + dy - 4) * SS,
                   (215 + 4) * SS, (292 + dy + 4) * SS],
                  fill=tuple(int(c * a + BG[j] * (1 - a)) for j, c in enumerate(GLOW)))

    img = lay(img, art)
    return finish(img, "Shadow Wave")


# --- Lumen Run: endless runner, collect the light ---------------------------
def lumen_run():
    img = base()
    art = Image.new("RGB", img.size, BG)
    d = ImageDraw.Draw(art)
    horizon(d, 304, NEON, rows=5)

    ground = 300
    d.line([(0, ground * SS), (W * SS, ground * SS)], fill=SHADOW, width=3 * SS)
    for x in range(0, W, 34):                   # ground tick marks = speed
        d.line([(x * SS, ground * SS), ((x + 16) * SS, ground * SS)],
               fill=NEON, width=3 * SS)

    # the runner's arc, mid-jump
    pts = [(80 + i * 4, ground - 18 - math.sin(i / 34 * math.pi) * 104)
           for i in range(0, 92)]
    for i in range(len(pts) - 1):
        a = 0.15 + 0.85 * (i / len(pts)) ** 2
        d.line([(pts[i][0] * SS, pts[i][1] * SS),
                (pts[i + 1][0] * SS, pts[i + 1][1] * SS)],
               fill=tuple(int(c * a + BG[j] * (1 - a)) for j, c in enumerate(GLOW)),
               width=4 * SS)

    orb(d, pts[-1][0] * SS, pts[-1][1] * SS, 11 * SS, LIGHT)

    for cx, cy in [(470, 212), (530, 188), (590, 232)]:   # lumens to collect
        orb(d, cx * SS, cy * SS, 6 * SS, GOOD, rings=4)

    for bx in [400, 560]:                                  # obstacles = danger
        d.rectangle([bx * SS, (ground - 42) * SS, (bx + 16) * SS, ground * SS],
                    fill=HOT)

    img = lay(img, art)
    return finish(img, "Lumen Run")


# --- Light Rally: paddle, ball, rally ---------------------------------------
def light_rally():
    img = base()
    art = Image.new("RGB", img.size, BG)
    d = ImageDraw.Draw(art)
    horizon(d, 322, NEON, rows=4)

    # brick wall being broken down
    for row in range(3):
        for col in range(9):
            if (row + col) % 4 == 3:
                continue
            x = 300 + col * 36
            y = 170 + row * 22
            a = 0.85 - row * 0.2
            d.rounded_rectangle([x * SS, y * SS, (x + 30) * SS, (y + 15) * SS],
                                radius=4 * SS,
                                fill=tuple(int(c * a + BG[i] * (1 - a))
                                           for i, c in enumerate(SHADOW)))

    # the rally line — ball's path, bouncing
    path = [(120, 300), (250, 212), (330, 262), (448, 196)]
    for i in range(len(path) - 1):
        a = 0.2 + 0.8 * (i / max(1, len(path) - 2))
        d.line([(path[i][0] * SS, path[i][1] * SS),
                (path[i + 1][0] * SS, path[i + 1][1] * SS)],
               fill=tuple(int(c * a + BG[j] * (1 - a)) for j, c in enumerate(GLOW)),
               width=3 * SS)

    orb(d, 448 * SS, 196 * SS, 10 * SS, LIGHT)

    d.rounded_rectangle([84 * SS, 306 * SS, 190 * SS, 316 * SS],
                        radius=5 * SS, fill=LIGHT)

    img = lay(img, art)
    return finish(img, "Light Rally")


# --- Neon Breach: first person, down the barrel -----------------------------
def neon_breach():
    """The cover has one job the others don't: say "first person" instantly.

    So it is drawn as the view itself — one-point perspective down a corridor,
    a crosshair on the vanishing point, and the emitter in the bottom of frame
    exactly where the game puts it. A side-on illustration of the same scene
    would look like every other cabinet on the rack.
    """
    img = base()
    art = Image.new("RGB", img.size, BG)
    d = ImageDraw.Draw(art)

    VX, VY = 404, 214           # vanishing point, off-centre so it isn't static

    # corridor: wall tops and bottoms converging on the vanishing point
    for side, edge in ((-1, 150), (1, 648)):
        for yy, col, a in ((132, NEON, 0.95), (318, NEON, 0.55)):
            x0 = edge if side > 0 else -8
            d.line([(x0 * SS, yy * SS), (VX * SS, VY * SS)],
                   fill=tuple(int(c * a + BG[i] * (1 - a)) for i, c in enumerate(col)),
                   width=3 * SS)

    # wall panels: vertical ribs, spaced by perspective so they bunch up
    for i in range(1, 11):
        t = i / 11
        depth = t ** 2.1
        wy_top = VY - (VY - 132) * (1 - depth)
        wy_bot = VY + (318 - VY) * (1 - depth)
        a = 0.14 + 0.5 * (1 - depth)
        col = tuple(int(c * a + BG[j] * (1 - a)) for j, c in enumerate(GRID))
        for side in (-1, 1):
            px = VX + side * (VX if side < 0 else (648 - VX)) * (1 - depth)
            d.line([(px * SS, wy_top * SS), (px * SS, wy_bot * SS)],
                   fill=col, width=3 * SS)

    # floor bands at whole-tile distances, same as the game draws them
    for i in range(1, 9):
        y = VY + 150 / i
        a = 0.1 + 0.42 * (1 / i)
        d.line([(0, y * SS), (W * SS, y * SS)],
               fill=tuple(int(c * a + BG[j] * (1 - a)) for j, c in enumerate(NEON)),
               width=2 * SS)

    def drone(cx, cy, r, colour, alpha=1.0):
        col = tuple(int(c * alpha + BG[i] * (1 - alpha)) for i, c in enumerate(colour))
        pts = [(cx + math.cos(i * math.pi / 3) * r,
                cy + math.sin(i * math.pi / 3) * r * 1.12) for i in range(6)]
        d.polygon([(p[0] * SS, p[1] * SS) for p in pts], outline=col, fill=DECK)
        for i in range(6):
            a, b = pts[i], pts[(i + 1) % 6]
            d.line([(a[0] * SS, a[1] * SS), (b[0] * SS, b[1] * SS)],
                   fill=col, width=max(1, int(r * 0.12)) * SS)
        d.ellipse([(cx - r * 0.44) * SS, (cy - r * 0.27) * SS,
                   (cx + r * 0.44) * SS, (cy + r * 0.27) * SS], fill=col)

    drone(196, 250, 48, NEON)         # close, bearing down
    drone(486, 224, 27, HOT)          # mid
    drone(330, 202, 14, SHADOW, 0.8)  # far, nearly in the dark

    orb(d, 286 * SS, 288 * SS, 8 * SS, LIGHT)     # a dropped lumen on the floor

    # crosshair, on the vanishing point
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        d.line([((VX + dx * 11) * SS, (VY + dy * 11) * SS),
                ((VX + dx * 32) * SS, (VY + dy * 32) * SS)],
               fill=GOOD, width=3 * SS)
    d.rectangle([(VX - 2) * SS, (VY - 2) * SS, (VX + 2) * SS, (VY + 2) * SS], fill=GOOD)

    # the emitter, bottom of frame
    d.polygon([(276 * SS, 360 * SS), (300 * SS, 300 * SS),
               (360 * SS, 300 * SS), (384 * SS, 360 * SS)],
              fill=DECK, outline=NEON)
    for xx in (300, 360):
        d.line([(xx * SS, 300 * SS), (xx * SS, 360 * SS)], fill=NEON, width=2 * SS)
    d.line([(300 * SS, 300 * SS), (360 * SS, 300 * SS)], fill=NEON, width=4 * SS)
    d.rectangle([320 * SS, 288 * SS, 340 * SS, 303 * SS], fill=GOOD)

    img = lay(img, art)
    return finish(img, "Neon Breach")


if __name__ == "__main__":
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in [("shadowwave", shadow_wave),
                     ("lumenrun", lumen_run),
                     ("lightrally", light_rally),
                     ("neonbreach", neon_breach)]:
        p = out / f"{name}.png"
        img = fn()
        assert img.size == (W, H), img.size
        img.save(p)
        print(f"{p}  {img.size[0]}x{img.size[1]}  {p.stat().st_size // 1024}KB")
