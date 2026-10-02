"""A game run has to score the card it was launched from.

Run from the repo root:  python3 tests/test_arcade_score.py

The play token carries two chat ids: where the run is FILED (the group, for
Lumens and /scores) and where the game CARD is (the player's DM, for
Telegram's own leaderboard). Collapsing them into one is what made the
native leaderboard silently never appear.
"""
import asyncio, os, sys, tempfile

os.environ.setdefault("BOT_TOKEN", "123456:TEST-TOKEN-FOR-HMAC-ONLY")
os.environ["DB_PATH"] = tempfile.mktemp(suffix=".db")
os.environ["MAIN_CHAT_ID"] = "-1001111111111"
os.environ["ARCADE_URL"] = "https://play.spreadlight.io"
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

import arcade_server

GROUP = -1001111111111
DM = 555001
USER = 555001
CARD_MSG = 42

# --- token round trip -------------------------------------------------------
url = arcade_server.play_url(USER, GROUP, "shadowwave",
                             card_chat=DM, message_id=CARD_MSG)
tok = url.split("t=", 1)[1]
claim = arcade_server.read_token(tok)
assert claim is not None, "token failed to verify"
assert claim["chat_id"] == GROUP, claim
assert claim["card_chat"] == DM, claim
assert claim["message_id"] == CARD_MSG, claim
assert claim["inline_id"] is None, claim
print("token round trip        ok  ->", claim)

# inline id containing a colon used to destroy the token
inline = "AgAAAD:xyz:123"
c2 = arcade_server.read_token(
    arcade_server.make_token(USER, GROUP, "lumenrun", None, None, inline))
assert c2 and c2["inline_id"] == inline, c2
print("inline id with colons   ok  ->", c2["inline_id"])

# tamper check
bad = tok[:-1] + ("0" if tok[-1] != "0" else "1")
assert arcade_server.read_token(bad) is None
assert arcade_server.read_token("garbage") is None
assert arcade_server.read_token("a:b:c:d:e:f:g") is None
print("tamper / junk rejected  ok")

# --- on_arcade_score with a stub bot ---------------------------------------
import bot as bot_mod

calls = []


class FakeUser:
    username = "KaizenFresh"
    first_name = "Fred"


class FakeMember:
    user = FakeUser()


class FakeBot:
    async def get_chat_member(self, chat_id, user_id):
        calls.append(("get_chat_member", chat_id))
        return FakeMember()

    async def set_game_score(self, **kw):
        calls.append(("set_game_score", kw))

    async def send_message(self, chat_id, text, **kw):
        calls.append(("send_message", chat_id, text))


class FakeApp:
    bot = FakeBot()


import db  # noqa
db.init()

bot_mod._APP = FakeApp()
asyncio.run(bot_mod.on_arcade_score(claim, 1234))

sgs = [c for c in calls if c[0] == "set_game_score"]
assert len(sgs) == 1, calls
kw = sgs[0][1]
assert kw["chat_id"] == DM, f"scored against the wrong chat: {kw}"
assert kw["message_id"] == CARD_MSG, kw
assert "inline_message_id" not in kw, kw
print("set_game_score -> DM card  ok  ->", kw)

sent = [c for c in calls if c[0] == "send_message"]
assert sent and sent[0][1] == GROUP, calls
print("announcement -> group      ok")

import db  # noqa
rows = db.top_scores(GROUP, "shadowwave", 5)
assert rows and rows[0]["score"] == 1234 and rows[0]["user_id"] == USER, rows
assert not db.top_scores(DM, "shadowwave", 5), "score leaked into the DM board"
print("board row filed to group   ok  ->", dict(rows[0]))

# --- inline launch takes the other branch ----------------------------------
calls.clear()
asyncio.run(bot_mod.on_arcade_score(
    {"user_id": USER, "chat_id": GROUP, "card_chat": None, "game": "lumenrun",
     "message_id": None, "inline_id": "AgAAAD:xyz"}, 99))
kw = [c for c in calls if c[0] == "set_game_score"][0][1]
assert kw == {"user_id": USER, "score": 99,
              "inline_message_id": "AgAAAD:xyz",
              "disable_edit_message": False}, kw
print("inline launch branch       ok  ->", kw)

print("\nall good")
