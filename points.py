"""Lumens (✨) — the community point ledger and rank system.

Design rules, all deliberate:
  * Lumens are NOT redeemable for tokens, BNB, or money. They buy status and
    nothing else. See the note in README — that line is what keeps a community
    points system from looking like an unregistered promotional scheme.
  * Points cannot be transferred between members. No transfers = no sybil
    farming, no secondary market, no "buy Lumens" DM scams.
  * Every award is written to an audit table, so you can always answer
    "why does this person have 4000 Lumens".
  * Chat earning is rate-limited and daily-capped so spamming the group is a
    worse strategy than talking in it.
"""

import time

import db

# --- earning rules ----------------------------------------------------------

MSG_LUMENS = 1
MSG_COOLDOWN_SEC = 45        # min gap between two earning messages
MSG_DAILY_CAP = 25           # most Lumens/day from chatting alone
MSG_MIN_CHARS = 8            # "lol" doesn't pay

CHECKIN_BASE = 5
CHECKIN_STREAK_BONUS = 2     # per consecutive day
CHECKIN_STREAK_MAX = 10      # bonus stops growing here

# what each activity pays
AWARDS = {
    "charades_win": 15,
    "charades_actor": 10,
    "scramble_win": 8,
    "riddle_win": 8,
    "art_submit": 10,
    "art_win": 100,
    "art_runner_up": 40,
    "arcade_high": 25,
    "welcome": 5,
}

# --- ranks ------------------------------------------------------------------
#
# Two tracks, same thresholds. Every tier is deliberately prestige-matched so
# neither side is the "weak" pick — Star and Headliner are both "the famous
# one", Lighthouse and Mainstage are both the landmark you can see from far off.
#
# LIGHT    how far your light reaches
# FESTIVAL the same climb, told in Fred's other language
#
# (threshold, light name, light icon, festival name, festival icon)

RANKS = [
    (0,    "Spark",      "🔅", "Glowstick", "🟢"),
    (100,  "Candle",     "🕯", "Strobe",    "⚡"),
    (300,  "Lantern",    "🏮", "Laser",     "💫"),
    (750,  "Beacon",     "🔦", "Spotlight", "🔆"),
    (1500, "Lighthouse", "🗼", "Mainstage", "🎪"),
    (3000, "Star",       "⭐", "Headliner", "🎤"),
    (6000, "Supernova",  "🌟", "Legend",    "👑"),
]

TRACKS = ("light", "festival")
DEFAULT_TRACK = "light"


def _slot(track):
    return (3, 4) if track == "festival" else (1, 2)


def tier_index(lifetime):
    idx = 0
    for i, entry in enumerate(RANKS):
        if lifetime >= entry[0]:
            idx = i
    return idx


def rank_for(lifetime, track=DEFAULT_TRACK):
    """Returns ((threshold, name, icon), next_or_None) for the given track."""
    n, ic = _slot(track)
    i = tier_index(lifetime)
    cur = (RANKS[i][0], RANKS[i][n], RANKS[i][ic])
    nxt = None
    if i + 1 < len(RANKS):
        e = RANKS[i + 1]
        nxt = (e[0], e[n], e[ic])
    return cur, nxt


def both_names(lifetime):
    """The pair of titles available at this tier: (light, festival)."""
    e = RANKS[tier_index(lifetime)]
    return (e[1], e[2]), (e[3], e[4])


def other_track(track):
    return "light" if track == "festival" else "festival"


def rank_line(lifetime, track=DEFAULT_TRACK):
    (_, name, icon), nxt = rank_for(lifetime, track)
    if not nxt:
        return f"{icon} {name} — top rank fam"
    return f"{icon} {name} · {nxt[0] - lifetime} to {nxt[2]} {nxt[1]}"


def progress_to_next(lifetime):
    i = tier_index(lifetime)
    floor = RANKS[i][0]
    if i + 1 >= len(RANKS):
        return "▰" * 10, 100
    span = RANKS[i + 1][0] - floor
    pct = 0 if span <= 0 else min((lifetime - floor) / span, 1)
    filled = round(pct * 10)
    return "▰" * filled + "▱" * (10 - filled), round(pct * 100)


# --- core ops ---------------------------------------------------------------

def _today():
    return time.strftime("%Y-%m-%d", time.gmtime())


def award(user_id, chat_id, amount, reason, username=None):
    """Add Lumens and log why. Returns the new lifetime total."""
    db.add_points(user_id, chat_id, amount, reason, username)
    return db.get_points(user_id, chat_id)["lifetime"]


def award_named(user_id, chat_id, key, username=None, multiplier=1):
    amount = int(AWARDS.get(key, 0) * multiplier)
    if amount <= 0:
        return None, 0
    lifetime = award(user_id, chat_id, amount, key, username)
    return lifetime, amount


def earn_from_message(user_id, chat_id, text, username=None):
    """Rate-limited chat earning. Returns (lumens, crossed_rank) or (0, None)."""
    if len(text.strip()) < MSG_MIN_CHARS:
        return 0, None

    row = db.get_points(user_id, chat_id)
    now = int(time.time())
    if now - row["last_earn"] < MSG_COOLDOWN_SEC:
        return 0, None

    today = _today()
    earned_today = row["earned_today"] if row["earn_day"] == today else 0
    if earned_today >= MSG_DAILY_CAP:
        return 0, None

    before = row["lifetime"]
    db.add_points(user_id, chat_id, MSG_LUMENS, "chat", username)
    db.touch_earn(user_id, chat_id, today, earned_today + MSG_LUMENS)
    after = before + MSG_LUMENS

    crossed = None
    if tier_index(before) != tier_index(after):
        crossed = tier_index(after)
    return MSG_LUMENS, crossed


def check_in(user_id, chat_id, username=None):
    """Daily check-in. Returns (lumens, streak) or (None, streak) if already done."""
    row = db.get_points(user_id, chat_id)
    today = _today()
    if row["checkin_day"] == today:
        return None, row["streak"]

    yesterday = time.strftime(
        "%Y-%m-%d", time.gmtime(time.time() - 86400)
    )
    streak = row["streak"] + 1 if row["checkin_day"] == yesterday else 1
    bonus = min(streak, CHECKIN_STREAK_MAX) * CHECKIN_STREAK_BONUS
    total = CHECKIN_BASE + bonus

    db.add_points(user_id, chat_id, total, "checkin", username)
    db.set_checkin(user_id, chat_id, today, streak)
    return total, streak


def leaderboard(chat_id, limit=10, since_ts=None):
    return db.top_points(chat_id, limit, since_ts)
