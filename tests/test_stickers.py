"""A logo has to come out as something Telegram will actually accept.

Run from the repo root:  python3 tests/test_stickers.py

The size rules are hard requirements — Telegram rejects the upload outright
if the long side isn't exactly 512 (or the emoji isn't exactly 100x100), and
these are easy to break with an innocent-looking change to the padding.

The background rules are judgement, and the interesting case is the one that
should be LEFT ALONE: a logo on a flat white card should be cut out, but an
illustration on a dark gradient should not, even though both have four
corners that agree. Getting that wrong tears a ragged hole through artwork.
"""
import io
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import os                                  # noqa: E402
import tempfile                            # noqa: E402
os.environ.setdefault("BOT_TOKEN", "1:test")
os.environ["DB_PATH"] = tempfile.mktemp(suffix=".db")

from PIL import Image, ImageDraw, ImageFilter   # noqa: E402
import db                                  # noqa: E402
import stickers                            # noqa: E402

db.init()

fails = []


def check(label, cond, detail=""):
    print(f"{'  ok ' if cond else 'FAIL '} {label}"
          f"{(' — ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(label)


def png(img):
    b = io.BytesIO()
    img.convert("RGBA").save(b, "PNG")
    return b.getvalue()


def jpeg(img):
    b = io.BytesIO()
    img.convert("RGB").save(b, "JPEG", quality=92)
    return b.getvalue()


def mark(bg, fg, size=700, hole=True):
    """A logo shape with a light area INSIDE it, which a naive colour key
    would punch straight through."""
    im = Image.new("RGBA", (size, size), bg)
    d = ImageDraw.Draw(im)
    c, r = size // 2, size // 3
    d.ellipse([c - r, c - r, c + r, c + r], outline=fg, width=size // 16)
    d.polygon([(c, c - r // 2), (c + r // 2, c + r // 2),
               (c - r // 2, c + r // 2)], fill=fg)
    if hole:
        d.ellipse([c - 18, c + r // 5, c + 18, c + r // 5 + 36],
                  fill=(255, 255, 255, 255))
    return im


def glow(size=700):
    """An illustration on a gradient — the case that must NOT be cut.

    The blur matters. Concentric rings drawn straight onto a flat field leave
    a hard step at the outermost ring, which is a CARD, not a gradient — the
    first version of this fixture had exactly that bug and the test failed
    against correct code. A real glow is blurred light, and it is the absence
    of any hard edge that the guard is looking for.
    """
    im = Image.new("RGB", (size, size), (6, 10, 34))
    d = ImageDraw.Draw(im)
    for i in range(size // 2, 0, -4):
        a = (1 - i / (size / 2)) ** 1.5
        d.ellipse([size // 2 - i, size // 2 - i, size // 2 + i, size // 2 + i],
                  fill=(int(6 + 60 * a), int(10 + 150 * a), int(34 + 190 * a)))
    im = im.filter(ImageFilter.GaussianBlur(size * 0.06))
    d = ImageDraw.Draw(im)
    d.ellipse([size * 0.35, size * 0.35, size * 0.65, size * 0.65],
              fill=(255, 255, 255))
    return im.convert("RGBA")


check("Pillow is installed", stickers.available())
if not stickers.available():
    sys.exit(1)

# --- the hard size rules ----------------------------------------------------
cases = [
    ("logo on a white card (png)", png(mark((255, 255, 255, 255), (18, 18, 56, 255)))),
    ("logo on a white card (jpeg)", jpeg(mark((255, 255, 255, 255), (18, 18, 56, 255)))),
    ("white logo on black", png(mark((0, 0, 0, 255), (255, 255, 255, 255)))),
    ("already transparent", png(mark((0, 0, 0, 0), (25, 230, 255, 255)))),
    ("wide, not square", png(mark((255, 255, 255, 255), (18, 18, 56, 255)).resize((900, 380)))),
    ("illustration on a gradient", jpeg(glow())),
]
for label, data in cases:
    s, _ = stickers.to_sticker(data)
    e, _ = stickers.to_sticker(data, emoji=True)
    si, ei = Image.open(io.BytesIO(s)), Image.open(io.BytesIO(e))
    check(f"sticker is 512 on its long side — {label}",
          max(si.size) == 512 and min(si.size) <= 512, str(si.size))
    check(f"emoji is exactly 100x100 — {label}", ei.size == (100, 100), str(ei.size))
    check(f"under Telegram's 512KB — {label}", len(s) <= 512 * 1024,
          f"{len(s) / 1024:.0f}KB")

# --- the judgement call -----------------------------------------------------
_, note = stickers.to_sticker(png(mark((255, 255, 255, 255), (18, 18, 56, 255))))
check("a flat white card IS removed", "removed" in note, note)

_, note = stickers.to_sticker(png(mark((0, 0, 0, 255), (255, 255, 255, 255))))
check("a flat black card IS removed", "removed" in note, note)

_, note = stickers.to_sticker(jpeg(glow()))
check("a gradient is LEFT ALONE (the ragged-hole case)",
      "removed" not in note, note)

_, note = stickers.to_sticker(jpeg(glow()), cut="always")
check("…but can be forced", "removed" in note, note)

_, note = stickers.to_sticker(png(mark((255, 255, 255, 255), (18, 18, 56, 255))),
                              cut="never")
check("…and can be refused", "removed" not in note, note)

# white inside the logo must survive the cut
s, _ = stickers.to_sticker(png(mark((255, 255, 255, 255), (18, 18, 56, 255))))
img = Image.open(io.BytesIO(s)).convert("RGBA")
w, h = img.size
centre_opaque = sum(1 for y in range(h // 2 - 40, h // 2 + 60)
                    for x in range(w // 2 - 40, w // 2 + 40)
                    if img.getpixel((x, y))[3] > 200)
check("white inside the logo survives (no hole punched through)",
      centre_opaque > 2000, f"only {centre_opaque} opaque px in the middle")
check("the corners really are transparent",
      img.getpixel((2, 2))[3] == 0 and img.getpixel((w - 3, 2))[3] == 0)

# --- pack naming ------------------------------------------------------------
name = stickers.pack_name("SpreadLightBot")
check("pack name ends in _by_<bot> as Telegram demands",
      name.endswith("_by_SpreadLightBot"), name)
check("pack name has no consecutive underscores", "__" not in name, name)
check("pack name starts with a letter", name[0].isalpha(), name)
check("pack name is letters, digits and underscores only",
      all(c.isalnum() or c == "_" for c in name), name)

for raw, want in [("https://t.me/addstickers/SpreadLight", "SpreadLight"),
                  ("t.me/addstickers/SpreadLight/", "SpreadLight"),
                  ("SpreadLight", "SpreadLight")]:
    got = stickers.set_community_pack(raw)
    check(f"reads a pack link: {raw}", got == want, got)

print("\n" + ("ALL PASS" if not fails else f"FAILURES: {fails}"))
sys.exit(1 if fails else 0)
