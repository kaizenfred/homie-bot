"""Can Homie moderate, and can he be hijacked?

Run from the repo root:  python3 tests/test_moderation.py

Every check here is a bug that was live at some point. The two that matter
most are the false positives — "let's hit it" being deleted as profanity and
"ok.Thanks" being deleted as a scam link — because those punish real members
for typing normally, and because a well-meaning tweak to either filter brings
them straight back.
"""
import asyncio, datetime as dt, os, sys, tempfile

os.environ["BOT_TOKEN"] = "123456:TEST"
os.environ["DB_PATH"] = tempfile.mktemp(suffix=".db")
os.environ["ADMIN_USERNAMES"] = "KaizenFresh"
os.environ["ADMIN_IDS"] = ""
os.environ["MAIN_CHAT_ID"] = "-1001111111111"
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

from telegram import Chat, Message, MessageEntity, User
import admins, bot, config, db

db.init()
GROUP = -1001111111111
db.set_main_chat(GROUP)

FRED = User(id=900, first_name="Fred", is_bot=False, username="KaizenFresh")
IMPOSTOR = User(id=901, first_name="Fred", is_bot=False, username="KaizenFresh")
MEMBER = User(id=902, first_name="Dana", is_bot=False, username="dana")

deleted, sent, restricted, banned = [], [], [], []


class FakeBot:
    id = 777
    username = "SpreadLightBot"
    first_name = "Homie"

    def __init__(self, chat_admins=(900,), can_delete=True):
        self._admins, self._can_delete = set(chat_admins), can_delete

    async def get_chat_administrators(self, chat_id):
        class M:
            def __init__(s, uid): s.user = User(id=uid, first_name="A", is_bot=False)
        return [M(u) for u in self._admins]

    async def get_chat_member(self, chat_id, user_id):
        class M:
            status = "administrator"
            user = User(id=user_id, first_name="A", is_bot=False)
        return M()

    async def get_chat(self, chat_id):
        return Chat(id=chat_id, type="supergroup")

    async def send_message(self, chat_id, text, **kw):
        sent.append((chat_id, text)); return None

    async def restrict_chat_member(self, chat_id, user_id, **kw):
        restricted.append((chat_id, user_id))

    async def ban_chat_member(self, chat_id, user_id, **kw):
        banned.append((chat_id, user_id))

    async def unban_chat_member(self, chat_id, user_id, **kw):
        banned.append(("un", chat_id, user_id))

    async def send_chat_action(self, *a, **kw):
        pass


class FakeCtx:
    def __init__(self, fb, args=None):
        self.bot, self.args = fb, args or []
        self.bot_data, self.user_data = {}, {}


class FakeMsg:
    """Stands in for telegram.Message, which is frozen and can't be stubbed."""

    def __init__(self, user, text=None, caption=None, ents=(), cents=(),
                 can_delete=True, reply_to=None):
        self.message_id = 10
        self.date = dt.datetime.now(dt.timezone.utc)
        self.chat = Chat(id=GROUP, type="supergroup")
        self.from_user = user
        self.text, self.caption = text, caption
        self.entities, self.caption_entities = ents, cents
        self.reply_to_message = reply_to
        self._can_delete = can_delete

    def _parse(self, body, ents, types):
        out = {}
        for e in ents or ():
            if e.type in types:
                out[e] = (body or "")[e.offset:e.offset + e.length]
        return out

    def parse_entities(self, types=None):
        return self._parse(self.text, self.entities, types or [])

    def parse_caption_entities(self, types=None):
        return self._parse(self.caption, self.caption_entities, types or [])

    async def delete(self):
        if not self._can_delete:
            raise RuntimeError("not enough rights")
        deleted.append(self.message_id)

    async def reply_text(self, t, **kw):
        sent.append((GROUP, t))


def msg(user, text=None, caption=None, ents=None, cents=None,
        can_delete=True, reply_to=None):
    return FakeMsg(user, text, caption, ents or (), cents or (),
                   can_delete, reply_to)


class FakeUpdate:
    edited_message = None
    def __init__(self, m):
        self.message = m
        self.effective_message = m
        self.effective_user = m.from_user
        self.effective_chat = m.chat


def run(c): return asyncio.get_event_loop().run_until_complete(c)
fails = []


def check(label, cond):
    print(f"{'  ok ' if cond else 'FAIL '} {label}")
    if not cond: fails.append(label)


# === 1. admin identity ======================================================
print("\n-- admin identity --")
fb = FakeBot(chat_admins=(900,))
ctx = FakeCtx(fb)
check("Fred (real chat admin) verifies", run(admins.verify(ctx, FakeUpdate(msg(FRED, "/say hi")))))
check("Fred's numeric id got pinned", 900 in admins.pinned())

admins.forget_chat(GROUP)
fb2 = FakeBot(chat_admins=(900,))        # impostor is NOT a chat admin
ctx2 = FakeCtx(fb2)
check("handle thief with same @ is refused",
      not run(admins.verify(ctx2, FakeUpdate(msg(IMPOSTOR, "/say rug")))))
check("thief was not pinned", 901 not in admins.pinned())
check("plain member refused",
      not run(admins.verify(ctx2, FakeUpdate(msg(MEMBER, "/say hi")))))

# === 2. admin list is cached, not re-fetched per message ====================
print("\n-- admin lookup cost --")
calls = {"n": 0}
class CountingBot(FakeBot):
    async def get_chat_administrators(self, chat_id):
        calls["n"] += 1
        return await super().get_chat_administrators(chat_id)
admins.forget_chat(GROUP)
cb = CountingBot(chat_admins=(900,)); cctx = FakeCtx(cb)
for _ in range(50):
    run(admins.chat_admin_ids(cctx, GROUP))
check(f"50 messages -> {calls['n']} API call(s)", calls["n"] == 1)

# === 3. the guards ==========================================================
print("\n-- guards --")
def guard_run(m, fb=None):
    deleted.clear(); sent.clear()
    fb = fb or FakeBot(chat_admins=(900,))
    c = FakeCtx(fb)
    return run(bot.run_guards(FakeUpdate(m), c)), c

CA = "0x" + "a" * 40
removed, _ = guard_run(msg(MEMBER, text=f"buy here {CA}"))
check("fake CA in text removed", removed and deleted)

removed, _ = guard_run(msg(MEMBER, caption=f"claim at {CA}"))
check("fake CA in a PHOTO CAPTION removed", removed and deleted)

removed, _ = guard_run(msg(MEMBER, caption="free light at free-light.top",
                           cents=[MessageEntity(type="url", offset=15, length=15)]))
check("scam link in a caption removed", removed and deleted)

removed, _ = guard_run(msg(MEMBER, text="let's hit it fam, lfg"))
check("\"let's hit it\" survives", not removed and not deleted)

removed, _ = guard_run(msg(MEMBER, text="ok.Thanks for the help"))
check("\"ok.Thanks\" survives", not removed and not deleted)

removed, _ = guard_run(msg(MEMBER, text="gm fam hope everyone's good"))
check("ordinary gm survives", not removed and not deleted)

removed, _ = guard_run(msg(MEMBER, text="what the fuck is this"))
check("actual profanity removed", removed and deleted)

removed, _ = guard_run(msg(FRED, text=f"official CA is {CA}"))
check("Fred is never moderated", not removed)

# admin by Telegram role only (not in ADMIN_USERNAMES)
MOD = User(id=903, first_name="Mo", is_bot=False, username="mo")
admins.forget_chat(GROUP)   # freshly promoted; cache must be re-read
removed, _ = guard_run(msg(MOD, text=f"CA {CA}"),
                       FakeBot(chat_admins=(900, 903)))
check("a chat admin is not moderated", not removed)

# === 4. no delete permission =================================================
print("\n-- no delete permission --")
deleted.clear(); sent.clear()
m = msg(MEMBER, text=f"scam {CA}", can_delete=False)
c = FakeCtx(FakeBot(chat_admins=(900,)))
res = run(bot.run_guards(FakeUpdate(m), c))
warned = any("couldn't remove" in t or "do NOT use" in t for _, t in sent)
check("shield still warns the chat when it can't delete", warned)
check("and reports it as handled, not as clean", res is True)

# === 5. strike decay ========================================================
print("\n-- strikes --")
db.clear_strikes(MEMBER.id, GROUP)
for _ in range(2):
    db.add_strike(MEMBER.id, GROUP, 3600)
n = db.add_strike(MEMBER.id, GROUP, 3600)
check("three strikes in a row count up", n == 3)
db.clear_strikes(MEMBER.id, GROUP)
db.add_strike(MEMBER.id, GROUP, 3600)
import sqlite3, time
with db.cursor() as cur:
    cur.execute("UPDATE strikes SET last_ts=? WHERE user_id=?",
                (int(time.time()) - 86400 * 30, MEMBER.id))
n = db.add_strike(MEMBER.id, GROUP, 3600)
check("a month-old strike is forgiven", n == 1)

# === 6. pitcher flag is clearable ===========================================
print("\n-- pitch flag --")
db.flag_pitcher(MEMBER.id)
check("flag sets", db.is_pitcher(MEMBER.id))
db.clear_pitcher(MEMBER.id)
check("/forgive can clear it", not db.is_pitcher(MEMBER.id))

# === 7. captcha survives a restart ==========================================
print("\n-- captcha persistence --")
class FakeJQ:
    def __init__(self): self.jobs = []
    def run_once(self, cb, when, data=None, name=None): self.jobs.append(name)
    def get_jobs_by_name(self, name): return []
jq = FakeJQ()
cctx = FakeCtx(FakeBot()); cctx.job_queue = jq
bot.arm_captcha(cctx, GROUP, 555, 99, 180)
check("pending captcha is written down",
      f"{bot.CAPTCHA_KEY}{GROUP}:555" in db.kv_prefix(bot.CAPTCHA_KEY))
pending = db.kv_prefix(bot.CAPTCHA_KEY)
check("and would be re-armed on boot", len(pending) == 1)
bot.disarm_captcha(cctx, GROUP, 555)
check("tapping the button clears it",
      not db.kv_prefix(bot.CAPTCHA_KEY))

# === 8. AI throttle =========================================================
print("\n-- AI cost control --")
tctx = FakeCtx(FakeBot())
allowed = sum(1 for _ in range(10) if bot.ai_allowed(tctx, GROUP, MEMBER.id))
check(f"10 rapid messages -> {allowed} AI call(s)", allowed == 1)
check("a different member still gets a reply",
      bot.ai_allowed(tctx, GROUP, 999))

print("\n" + ("ALL PASS" if not fails else f"FAILURES: {fails}"))
sys.exit(1 if fails else 0)
