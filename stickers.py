"""Turn a logo into Telegram stickers and custom emoji.

Send Homie a logo in a DM and he makes it into a sticker in the community's
own pack. The conversion is the interesting part, because a logo and a sticker
are not the same kind of image:

  * A logo usually arrives on a white card. A sticker has no card — it sits
    directly on whatever the reader's chat background is, so the white has to
    come off or every sticker is a white rectangle.
  * Once the white is gone, a dark logo is invisible on a dark theme and a
    light one is invisible on a light theme. Roughly half of Telegram runs
    dark. So the artwork gets an outline in whichever direction it needs,
    which is why real sticker packs almost all have one.
  * Telegram is strict about size: a sticker must be exactly 512 on its
    longest side, a custom emoji exactly 100x100.

Pillow is the only dependency, deliberately — this runs on a small box and
numpy and scipy are a lot of machinery to install for one flood fill.

ONE THING THIS CANNOT DO. A bot may CREATE a custom emoji pack, and anyone
with Telegram Premium can then use it. But a bot may only put custom emoji
into its own messages if it has bought an extra username on Fragment:

    "Custom emoji entities can only be used by bots that purchased
     additional usernames on Fragment."

So Homie can make the emoji pack and the fam can use it. Homie typing those
emoji in his own messages is the part that needs a Fragment purchase. Stickers
have no such restriction, which is why the sticker half is the one wired into
his replies.
"""

import io
import logging
from collections import deque

log = logging.getLogger(__name__)

try:
    from PIL import Image, ImageChops, ImageFilter
except ImportError:                                   # pragma: no cover
    Image = None
    log.warning("Pillow not installed — sticker making is off. "
                "pip install -r requirements.txt")

STICKER_PX = 512          # longest side, exactly
EMOJI_PX = 100            # exactly, both sides
MAX_BYTES = 480 * 1024    # Telegram's ceiling is 512KB; leave headroom

# The flood fill that removes the background runs on a small copy and the
# result is scaled back up. 256 is plenty to find where a white card ends,
# it keeps the fill fast, and scaling the mask up again softens the cut edge,
# which is exactly what you want anyway.
KNOCKOUT_PX = 256


def available() -> bool:
    return Image is not None


# --- background removal -----------------------------------------------------

def _corner_colour(img):
    """The background colour, if the four corners agree on one."""
    w, h = img.size
    pts = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    cols = [img.getpixel(p)[:3] for p in pts]
    first = cols[0]
    for c in cols[1:]:
        if max(abs(a - b) for a, b in zip(c, first)) > 26:
            return None          # a photo or a full-bleed design: leave it be
    return first


TOLERANCE = 38
# How big a colour step the fill must stop against to count as a real edge.
# See _knockout for why this number is the whole trick.
EDGE_STEP = 70


def _knockout(img, tolerance=TOLERANCE, force=False):
    """Make the card the logo is sitting on transparent.

    A flood fill from the edges, not a colour key. Keying every white pixel in
    the image would punch holes through white *inside* the logo — the counter
    of an 'o', a highlight, white type. Only background reachable from the
    border comes off, so enclosed areas survive.

    The hard part isn't the fill, it's knowing when NOT to run it. A logo on a
    white card and an illustration on a dark gradient both have four corners
    that agree, so corner-matching alone says yes to both — and on the
    gradient the fill stops wherever the tolerance happens to run out, which
    tears a ragged hole through the artwork.

    The tell is what the fill stops AGAINST. A real card ends at a hard edge:
    the pixel just outside the fill is the logo itself, far from the card
    colour. A gradient has no edge, so the fill just drifts until it exceeds
    the tolerance and the pixel outside is barely past it. Measured across
    these: flat cards step 82-107, gradients 39-47, against a tolerance of 38.
    """
    if img.getextrema()[3][0] < 250:
        return img, "already transparent"

    small = img.resize((KNOCKOUT_PX, KNOCKOUT_PX), Image.BILINEAR)
    bg = _corner_colour(small)
    if bg is None:
        return img, "corners disagree — not a flat background"

    px = small.load()
    w, h = small.size
    near = lambda c: max(abs(a - b) for a, b in zip(c[:3], bg)) <= tolerance

    seen = bytearray(w * h)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if not seen[y * w + x] and near(px[x, y]):
                seen[y * w + x] = 1; q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if not seen[y * w + x] and near(px[x, y]):
                seen[y * w + x] = 1; q.append((x, y))

    while q:
        x, y = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx] \
                    and near(px[nx, ny]):
                seen[ny * w + nx] = 1
                q.append((nx, ny))

    if sum(seen) < (w * h) * 0.02:
        return img, "almost nothing matched the background"

    if not force:
        steps = []
        for i, s in enumerate(seen):
            if not s:
                continue
            x, y = i % w, i // w
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx]:
                    steps.append(max(abs(a - b)
                                     for a, b in zip(px[nx, ny][:3], bg)))
        steps.sort()
        median = steps[len(steps) // 2] if steps else 0
        if median < EDGE_STEP:
            return img, (f"background fades instead of ending (edge step "
                         f"{median}) — kept square")

    mask = Image.frombytes("L", (w, h), bytes(0 if s else 255 for s in seen))
    mask = mask.resize(img.size, Image.BILINEAR)
    out = img.copy()
    out.putalpha(ImageChops.multiply(img.getchannel("A"), mask))
    return out, "background removed"


# --- outline ----------------------------------------------------------------

def _mean_luma(img):
    """Average brightness of the parts that aren't transparent."""
    small = img.resize((64, 64), Image.BILINEAR)
    rgb, alpha = small.convert("RGB"), small.getchannel("A")
    total = lit = 0
    for (r, g, b), a in zip(rgb.getdata(), alpha.getdata()):
        if a > 40:
            lit += (0.299 * r + 0.587 * g + 0.114 * b) * a / 255
            total += a / 255
    return (lit / total) if total else 128


def _outline(img, width, colour):
    """Grow a soft silhouette out from the artwork and fill it.

    Blur-and-boost rather than a MaxFilter: a 20px MaxFilter on a 512px image
    is slow, and a blurred edge gives a softer, less sticker-sheet result.
    """
    alpha = img.getchannel("A")
    spread = alpha.filter(ImageFilter.GaussianBlur(width * 0.55))
    spread = spread.point(lambda v: min(255, int(v * 4.2)))
    ring = ImageChops.subtract(spread, alpha)

    layer = Image.new("RGBA", img.size, colour + (0,))
    layer.putalpha(ring)
    return Image.alpha_composite(layer, img)


# --- the conversion ---------------------------------------------------------

def to_sticker(data, *, emoji=False, cut="auto", outline="auto", margin=0.07):
    """Logo bytes in, Telegram-ready WEBP bytes out.

    emoji=True gives the exact 100x100 a custom emoji needs; otherwise the
    longest side comes out at exactly 512, which is what Telegram requires
    of a sticker.

    cut: "auto" removes a flat background and leaves a gradient alone,
    "always" forces the cut, "never" keeps the full square.

    Returns (webp_bytes, note) — the note says what it decided about the
    background, because that is the one judgement call worth reporting back.
    """
    if Image is None:
        raise RuntimeError("Pillow is not installed")

    img = Image.open(io.BytesIO(data))
    if getattr(img, "n_frames", 1) > 1:
        img.seek(0)              # first frame of a GIF/animated source
    img = img.convert("RGBA")

    # Work at a sane size before anything else: a 4000px logo costs time in
    # every step below and the output is 512 at most.
    box = STICKER_PX * 2
    if max(img.size) > box:
        img.thumbnail((box, box), Image.LANCZOS)

    note = "kept square"
    if cut != "never":
        img, note = _knockout(img, force=(cut == "always"))

    bbox = img.getchannel("A").getbbox()
    if bbox:
        img = img.crop(bbox)

    size = EMOJI_PX if emoji else STICKER_PX
    pad = max(1, int(size * margin))
    fit = size - pad * 2
    scale = min(fit / img.width, fit / img.height)
    img = img.resize((max(1, round(img.width * scale)),
                      max(1, round(img.height * scale))), Image.LANCZOS)

    if outline and outline != "none":
        colour = ((255, 255, 255) if _mean_luma(img) < 140 else (10, 10, 31)) \
            if outline == "auto" else outline
        img = _outline(img, max(2, size * 0.022), colour)

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)

    # A sticker must be EXACTLY 512 on its long side. Centring on a square
    # canvas satisfies that for both shapes, and emoji need the square anyway.
    for quality in (95, 88, 80, 70, 60, 50):
        buf = io.BytesIO()
        canvas.save(buf, "WEBP", quality=quality, method=6)
        if buf.tell() <= MAX_BYTES:
            return buf.getvalue(), note
    return buf.getvalue(), note


def describe(data):
    """What came out, for a reply that says more than 'done'."""
    img = Image.open(io.BytesIO(data))
    return f"{img.width}x{img.height} {img.format}, {len(data) / 1024:.0f}KB"


# --- the packs themselves ---------------------------------------------------
#
# A pack belongs to a PERSON, not to the bot — Telegram wants a user_id for
# every create and every add, and it must be the same user each time. The bot
# only does the work. The owner's id is written down on creation so a later
# add from a different admin still goes to the right account rather than
# failing in a way that looks like the pack is broken.

import db   # noqa: E402  (kept here: the image half above has no db needs)

PACK_BASE = "spreadlight"
KINDS = {
    "sticker": ("regular", "SpreadLight", ""),
    "emoji": ("custom_emoji", "SpreadLight Emoji", "emoji"),
}


def pack_name(bot_username, kind="sticker"):
    """Telegram requires the name to end in _by_<bot_username>."""
    _, _, infix = KINDS[kind]
    stem = f"{PACK_BASE}_{infix}" if infix else PACK_BASE
    return f"{stem}_by_{bot_username}"


def pack_link(bot_username, kind="sticker"):
    return f"https://t.me/addstickers/{pack_name(bot_username, kind)}"


# The community's OWN pack — made by a person through @Stickers, which is why
# no bot can add to it (addStickerToSet: "a set created by the bot"). Homie
# can still send from it, and that is the half that matters: /stickeruse
# takes a sticker's file_id straight off a reply, and a file_id works
# whoever made the pack.
def community_pack():
    return db.kv_get("community_pack")


def set_community_pack(link):
    """Accepts a full t.me/addstickers link or a bare pack name."""
    name = (link or "").strip().rstrip("/").split("/")[-1].split("?")[0]
    name = "".join(ch for ch in name if ch.isalnum() or ch == "_")
    if name:
        db.kv_set("community_pack", name)
    return name


def _owner_key(kind):
    return f"stickerpack_owner:{kind}"


def owner_of(kind):
    v = db.kv_get(_owner_key(kind))
    return int(v) if v else None


async def add_to_pack(bot, user_id, image, emoji_list, kind="sticker"):
    """Put one converted image into the pack, creating the pack if needed.

    Returns (pack_name, created). Raises whatever Telegram raises — the
    caller turns that into something a human can act on.
    """
    from telegram import InputSticker
    from telegram.error import BadRequest

    name = pack_name(bot.username, kind)
    sticker_type, title, _ = KINDS[kind]

    # Whoever made the pack has to be the one who extends it.
    owner = owner_of(kind) or user_id

    uploaded = await bot.upload_sticker_file(
        user_id=owner, sticker=image, sticker_format="static")
    item = InputSticker(sticker=uploaded.file_id,
                        emoji_list=list(emoji_list) or ["✨"],
                        format="static")

    try:
        await bot.get_sticker_set(name)
        exists = True
    except BadRequest:
        exists = False

    if exists:
        await bot.add_sticker_to_set(user_id=owner, name=name, sticker=item)
        return name, False

    await bot.create_new_sticker_set(
        user_id=owner, name=name, title=title, stickers=[item],
        sticker_type=sticker_type)
    db.kv_set(_owner_key(kind), owner)
    return name, True


# --- what Homie does with them ----------------------------------------------
#
# A pack nobody uses is a folder of images. These are the moments worth a
# sticker; each one is optional and silently does nothing until an admin
# assigns one with /stickeruse.

ROLES = {
    "welcome": "when someone new clears the captcha",
    "milestone": "when the presale crosses a cap",
    "biggiver": "on a Big Giver contribution",
    "gm": "the daily check-in post",
    "hype": "spare — /say it yourself",
}


def assign(role, file_id):
    db.kv_set(f"sticker_role:{role}", file_id)


def unassign(role):
    db.kv_delete(f"sticker_role:{role}")


def for_role(role):
    return db.kv_get(f"sticker_role:{role}")


async def send(bot, chat_id, role):
    """Send the sticker for a moment, if one is set. Never raises."""
    file_id = for_role(role)
    if not file_id:
        return False
    try:
        await bot.send_sticker(chat_id, file_id)
        return True
    except Exception as e:
        log.debug("sticker %s failed: %s", role, e)
        return False
