"""All tunable settings live here. Everything reads from .env"""

import os
from dotenv import load_dotenv

load_dotenv()


def _raw(key, default=""):
    """Env value with any trailing ` # comment` stripped.

    Some .env parsers hand back the comment when the value itself is empty,
    which used to crash startup on a commented-but-blank setting.
    """
    val = os.getenv(key)
    if val is None:
        return default
    if "#" in val:
        val = val.split("#", 1)[0]
    val = val.strip().strip('"').strip("'")
    return val if val else default


def _int(key, default):
    try:
        return int(_raw(key) or default)
    except ValueError:
        return default


def _float(key, default):
    try:
        return float(_raw(key) or default)
    except ValueError:
        return default


def _bool(key, default=True):
    val = _raw(key).lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


def _id_list(key):
    out = set()
    for part in _raw(key).replace(" ", "").split(","):
        if part:
            try:
                out.add(int(part))
            except ValueError:
                pass
    return out


def _name_list(key):
    return {p.lstrip("@").lower()
            for p in _raw(key).replace(" ", "").split(",") if p}


# --- Telegram ---------------------------------------------------------------
BOT_TOKEN = _raw("BOT_TOKEN", "")
MAIN_CHAT_ID = _int("MAIN_CHAT_ID", 0)        # negative number, e.g. -1001234567890
ADMIN_IDS = _id_list("ADMIN_IDS")
ADMIN_USERNAMES = _name_list("ADMIN_USERNAMES")   # e.g. KaizenFresh

# Names Homie answers to in chat, on top of his @handle and display name.
# Members type "homie", never "@SpreadLightBot" — without this he never
# realises he's being spoken to.
BOT_NICKNAMES = _name_list("BOT_NICKNAMES") or {"homie"}

# The display name Telegram shows for the bot. Applied at startup through
# setMyName, so it needs no trip to BotFather. The @username is separate and
# can only be changed by hand in BotFather.
BOT_NAME = _raw("BOT_NAME", "LIGHT")

# --- Persona / conversation -------------------------------------------------
ANTHROPIC_API_KEY = _raw("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = _raw("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
VOICE_FILE = _raw("VOICE_FILE", "voice.md")
# Crypto onboarding reference — how to buy, wallets, networks, safety.
# Loaded fresh on every reply, same as voice.md, so edits go live without a
# restart. Kept separate from voice.md because one is how he talks and the
# other is what he knows; they change for different reasons.
KNOWLEDGE_FILE = _raw("KNOWLEDGE_FILE", "knowledge.md")

# chance (0-1) the bot jumps into a normal message it wasn't tagged in
AMBIENT_REPLY_CHANCE = _float("AMBIENT_REPLY_CHANCE", 0.12)
# hard floor between two ambient replies in the same chat, seconds
AMBIENT_COOLDOWN_SEC = _int("AMBIENT_COOLDOWN_SEC", 300)
# how many past messages the bot keeps as context per chat
CONTEXT_WINDOW = _int("CONTEXT_WINDOW", 24)
# hour (UTC, 0-23) the daily icebreaker fires. -1 disables it.
ICEBREAKER_HOUR_UTC = _int("ICEBREAKER_HOUR_UTC", 15)

# --- Presale watcher --------------------------------------------------------
PRESALE_ADDRESS_DISPLAY = _raw("PRESALE_ADDRESS")
PRESALE_ADDRESS = PRESALE_ADDRESS_DISPLAY.lower()
PRESALE_URL = _raw("PRESALE_URL", "https://spreadlight.io")
WEBSITE_URL = _raw("WEBSITE_URL", "https://spreadlight.io")

# "etherscan" (1 request per poll, needs a key) or "rpc" (keyless, heavier)
CHAIN_BACKEND = _raw("CHAIN_BACKEND", "etherscan").lower()
ETHERSCAN_API_KEY = _raw("ETHERSCAN_API_KEY", "")
ETHERSCAN_URL = "https://api.etherscan.io/v2/api"
BSC_CHAIN_ID = 56
BSC_RPC_URL = _raw("BSC_RPC_URL", "https://bsc-dataseed.binance.org")

PRESALE_POLL_SEC = _int("PRESALE_POLL_SEC", 45)
# ignore dust so the chat doesn't get spammed by 0.001 BNB tests
MIN_ANNOUNCE_BNB = _float("MIN_ANNOUNCE_BNB", 0.01)
# a contribution at or above this gets the "Big Giver" treatment
BIG_GIVER_BNB = _float("BIG_GIVER_BNB", 0.5)

TOKEN_ADDRESS_DISPLAY = _raw("TOKEN_ADDRESS")
TOKEN_ADDRESS = TOKEN_ADDRESS_DISPLAY.lower()
SOFT_CAP_BNB = _float("SOFT_CAP_BNB", 5)
HARD_CAP_BNB = _float("HARD_CAP_BNB", 15)
# ISO 8601 with timezone. Copy the exact end time from the PinkSale page.
PRESALE_END = _raw("PRESALE_END", "2026-11-04T15:00:00-05:00")

# --- Scam shield ------------------------------------------------------------
SHIELD_ENABLED = _bool("SHIELD_ENABLED", True)
# links to these domains are allowed; everything else is deleted
ALLOWED_DOMAINS = _name_list("ALLOWED_DOMAINS") or {
    "spreadlight.io", "pinksale.finance", "bscscan.com", "pancakeswap.finance",
}
# t.me handles that may be linked (your group, your channel). The bot's own
# handle is always allowed.
#
# This MUST include your own group. Left empty, the shield treats a link to
# the community's own invite as a scam link: it deletes the message and gives
# the member a strike for sharing the group they are standing in.
ALLOWED_TG = _name_list("ALLOWED_TG") or {"spreadlighttoken"}
# any other 0x address found in a message gets deleted
EXTRA_ALLOWED_ADDRESSES = _name_list("EXTRA_ALLOWED_ADDRESSES")
# handles an impersonator would copy. ADMIN_USERNAMES are always included.
# Keep this to real people's handles — a supporter putting "SpreadLight" in
# their name is a fan, not a scammer, and shouldn't get banned for it.
PROTECTED_NAMES = _name_list("PROTECTED_NAMES") or {"kaizenfred"}

# --- Games ------------------------------------------------------------------
GAMES_ENABLED = _bool("GAMES_ENABLED", True)
POINTS_ENABLED = _bool("POINTS_ENABLED", True)

# Arcade needs a public HTTPS address. Leave ARCADE_URL empty to run
# everything else without it.
ARCADE_URL = _raw("ARCADE_URL")
ARCADE_BIND = _raw("ARCADE_BIND", "127.0.0.1")
ARCADE_PORT = _int("ARCADE_PORT", 8080)
ARCADE_ENABLED = bool(ARCADE_URL)
# Lumens for beating your own arcade best, once per day
ARCADE_DAILY_LUMENS = _int("ARCADE_DAILY_LUMENS", 25)

# --- Join captcha -----------------------------------------------------------
CAPTCHA_ENABLED = _bool("CAPTCHA_ENABLED", True)
CAPTCHA_TIMEOUT_SEC = _int("CAPTCHA_TIMEOUT_SEC", 180)

# --- Deleted account cleanup ------------------------------------------------
DELETED_SWEEP_HOURS = _int("DELETED_SWEEP_HOURS", 12)
DELETED_SWEEP_ENABLED = _bool("DELETED_SWEEP_ENABLED", True)

# --- Content filters --------------------------------------------------------
PROFANITY_FILTER = _bool("PROFANITY_FILTER", True)
# strikes before a temporary mute
PROFANITY_STRIKES = _int("PROFANITY_STRIKES", 3)
MUTE_MINUTES = _int("MUTE_MINUTES", 60)
# A strike older than this is forgiven automatically. Without it, strikes are
# permanent and a member who slipped up once months ago sits one word away
# from a mute forever. 0 disables decay.
STRIKE_DECAY_HOURS = _int("STRIKE_DECAY_HOURS", 168)   # 7 days
MARKETER_REROUTE = _bool("MARKETER_REROUTE", True)

# --- AI cost control --------------------------------------------------------
# Every reply Homie writes costs money, and nothing stopped one member from
# holding /ask down. Per-person floor between AI replies, in seconds.
AI_USER_COOLDOWN_SEC = _int("AI_USER_COOLDOWN_SEC", 20)
# Ceiling on AI replies per chat per hour, as a backstop against a group-wide
# pile-on. 0 disables it.
AI_CHAT_HOURLY_CAP = _int("AI_CHAT_HOURLY_CAP", 120)

# --- Storage ----------------------------------------------------------------
DB_PATH = _raw("DB_PATH", "spreadlight.db")


def validate():
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if CHAIN_BACKEND == "etherscan" and PRESALE_ADDRESS and not ETHERSCAN_API_KEY:
        missing.append("ETHERSCAN_API_KEY (or set CHAIN_BACKEND=rpc)")
    return missing
