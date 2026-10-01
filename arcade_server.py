"""Arcade: serves the HTML5 games and accepts scores.

The honest limitation up front: any browser game can have its score faked by
someone with dev tools. This closes the easy holes but not that one:

  * the play URL carries a short-lived HMAC token tied to one user, one chat
    and one message, so you can't submit a score for somebody else
  * tokens expire, so a captured URL is worthless an hour later
  * each game declares a MAX_SCORE and anything above it is dropped
  * Lumens for arcade play are a flat, small, once-per-day award — winning
    the board is bragging rights, not a payout

That combination means faking a score gets you a name on a leaderboard and
nothing else, which is the right amount of prize for a game in a group chat.
"""

import hmac
import hashlib
import json
import logging
import pathlib
import time

import config

log = logging.getLogger(__name__)

try:
    from aiohttp import web
except ImportError:
    web = None

ARCADE_DIR = pathlib.Path(__file__).parent / "arcade"

# short_name in BotFather -> (file, title, plausible ceiling)
GAMES = {
    "shadowwave": ("shadowwave.html", "Shadow Wave", 250_000),
    "lumenrun": ("lumenrun.html", "Lumen Run", 250_000),
    "lightrally": ("lightrally.html", "Light Rally", 250_000),
}

TOKEN_TTL = 3600


# --- tokens -----------------------------------------------------------------

def _secret():
    # derived from the bot token, so there's nothing extra to configure
    return hashlib.sha256(
        ("arcade" + config.BOT_TOKEN).encode()
    ).digest()


def make_token(user_id, chat_id, game, message_id=None, inline_id=None):
    exp = int(time.time()) + TOKEN_TTL
    body = f"{user_id}:{chat_id}:{game}:{message_id or 0}:{inline_id or ''}:{exp}"
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{body}:{sig}"


def read_token(token):
    try:
        user_id, chat_id, game, message_id, inline_id, exp, sig = token.split(":")
    except ValueError:
        return None
    body = f"{user_id}:{chat_id}:{game}:{message_id}:{inline_id}:{exp}"
    want = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, want):
        return None
    if int(exp) < time.time():
        return None
    return {
        "user_id": int(user_id), "chat_id": int(chat_id), "game": game,
        "message_id": int(message_id) or None, "inline_id": inline_id or None,
    }


def play_url(user_id, chat_id, game, message_id=None, inline_id=None):
    base = config.ARCADE_URL.rstrip("/")
    token = make_token(user_id, chat_id, game, message_id, inline_id)
    return f"{base}/arcade/{GAMES[game][0]}?g={game}&t={token}"


# --- web server -------------------------------------------------------------

# Binary types must not be given a charset — aiohttp would label a PNG as
# utf-8 text and browsers would refuse to render it.
TEXT_TYPES = {"html": "text/html", "js": "application/javascript",
              "css": "text/css", "svg": "image/svg+xml"}
BINARY_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "webp": "image/webp", "ico": "image/x-icon"}


async def _serve_file(request):
    name = request.match_info["name"]
    if "/" in name or ".." in name:
        raise web.HTTPNotFound()
    path = ARCADE_DIR / name
    if not path.is_file():
        raise web.HTTPNotFound()
    ext = name.rsplit(".", 1)[-1].lower()
    if ext in BINARY_TYPES:
        return web.Response(body=path.read_bytes(),
                            content_type=BINARY_TYPES[ext])
    return web.Response(body=path.read_bytes(),
                        content_type=TEXT_TYPES.get(ext, "text/plain"),
                        charset="utf-8")


async def _index(request):
    """Something human at the root.

    The bare domain used to 404, which looks identical to a broken deploy
    when you are checking whether the arcade came up. This is also the page
    a shared play.spreadlight.io link lands on.
    """
    path = ARCADE_DIR / "index.html"
    if not path.is_file():
        return web.Response(text="arcade is up", content_type="text/plain")
    return web.Response(body=path.read_bytes(),
                        content_type="text/html", charset="utf-8")


async def _post_score(request):
    try:
        data = await request.json()
    except (json.JSONDecodeError, ValueError):
        raise web.HTTPBadRequest()

    claim = read_token(str(data.get("t", "")))
    if not claim:
        return web.json_response({"ok": False, "why": "bad token"}, status=403)

    game = claim["game"]
    if game not in GAMES or data.get("g") != game:
        return web.json_response({"ok": False, "why": "bad game"}, status=400)

    try:
        score = int(data.get("score", 0))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "why": "bad score"}, status=400)
    if score <= 0 or score > GAMES[game][2]:
        return web.json_response({"ok": False, "why": "out of range"}, status=400)

    await request.app["on_score"](claim, score)
    return web.json_response({"ok": True})


async def start_server(on_score):
    """Runs alongside the bot. on_score(claim, score) is awaited per submission."""
    if web is None:
        log.error("aiohttp not installed — arcade disabled. pip install aiohttp")
        return None
    app = web.Application()
    app["on_score"] = on_score
    app.add_routes([
        web.get("/", _index),
        web.get("/arcade/{name}", _serve_file),
        web.post("/score", _post_score),
        web.get("/health", lambda r: web.Response(text="ok")),
    ])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.ARCADE_BIND, config.ARCADE_PORT)
    await site.start()
    log.info("arcade serving on %s:%s (public: %s)",
             config.ARCADE_BIND, config.ARCADE_PORT, config.ARCADE_URL)
    return runner
