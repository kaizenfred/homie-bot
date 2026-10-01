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

# straight from arcade/sl.css
BG      = (7, 7, 13)
INK     = (246, 243, 232)
DIM     = (111, 106, 134)
LIGHT   = (255, 215, 94)
GLOW    = (255, 176, 32)
SHADOW  = (91, 62, 168)
GOOD    = (87, 224, 160)

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
    """Near-black canvas with the faint vertical lift the games have."""
    img = Image.new("RGB", (W * SS, H * SS), BG)
    d = ImageDraw.Draw(img)
    for y in range(H * SS):
        t = y / (H * SS)
        k = int(10 * (1 - t) ** 2)
        d.line([(0, y), (W * SS, y)], fill=(BG[0] + k, BG[1] + k, BG[2] + k + 2))
    return img


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
    f_kick = font(MONO, 13)
    f_title = font(MONOB, 40)

    tracked(d, (46 * SS, 44 * SS), kicker, f_kick, DIM, track=3)
    tracked(d, (44 * SS, 70 * SS), title.upper(), f_title, LIGHT, track=2)

    # underline tying title to art, fading out like a light trail
    y = 126 * SS
    tw = tracked_width(d, title.upper(), f_title, 2)
    steps = 60
    for i in range(steps):
        t = i / steps
        x0 = 46 * SS + tw * t
        x1 = 46 * SS + tw * (t + 1 / steps)
        a = 1 - t
        d.line([(x0, y), (x1, y)],
               fill=(int(GLOW[0] * a + BG[0] * (1 - a)),
                     int(GLOW[1] * a + BG[1] * (1 - a)),
                     int(GLOW[2] * a + BG[2] * (1 - a))),
               width=2 * SS)

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

    ground = 300
    d.line([(0, ground * SS), (W * SS, ground * SS)], fill=SHADOW, width=3 * SS)
    for x in range(0, W, 34):                   # ground tick marks = speed
        d.line([(x * SS, ground * SS), ((x + 16) * SS, ground * SS)],
               fill=GLOW, width=3 * SS)

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

    for bx in [400, 560]:                                  # obstacles
        d.rectangle([bx * SS, (ground - 42) * SS, (bx + 16) * SS, ground * SS],
                    fill=SHADOW)

    img = lay(img, art)
    return finish(img, "Lumen Run")


# --- Light Rally: paddle, ball, rally ---------------------------------------
def light_rally():
    img = base()
    art = Image.new("RGB", img.size, BG)
    d = ImageDraw.Draw(art)

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


if __name__ == "__main__":
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in [("shadowwave", shadow_wave),
                     ("lumenrun", lumen_run),
                     ("lightrally", light_rally)]:
        p = out / f"{name}.png"
        img = fn()
        assert img.size == (W, H), img.size
        img.save(p)
        print(f"{p}  {img.size[0]}x{img.size[1]}  {p.stat().st_size // 1024}KB")
