"""Tiny SQLite layer. One file, no ORM, easy to extend.

To add a feature: add a CREATE TABLE line to SCHEMA and a couple of helpers.
Existing tables are never dropped, so adding new ones is safe on restart.
"""

import sqlite3
import time
from contextlib import contextmanager

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    user_id     INTEGER NOT NULL,
    chat_id     INTEGER NOT NULL,
    username    TEXT,
    first_name  TEXT,
    first_seen  INTEGER NOT NULL,
    last_seen   INTEGER NOT NULL,
    messages    INTEGER NOT NULL DEFAULT 0,
    removed     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, chat_id)
);

CREATE TABLE IF NOT EXISTS contributions (
    tx_hash     TEXT PRIMARY KEY,
    wallet      TEXT NOT NULL,
    value_wei   TEXT NOT NULL,
    block       INTEGER NOT NULL,
    ts          INTEGER NOT NULL,
    announced   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_contrib_wallet ON contributions(wallet);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL,
    role        TEXT NOT NULL,
    author      TEXT NOT NULL,
    content     TEXT NOT NULL,
    ts          INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_chat ON messages(chat_id, id);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS strikes (
    user_id   INTEGER NOT NULL,
    chat_id   INTEGER NOT NULL,
    count     INTEGER NOT NULL DEFAULT 0,
    last_ts   INTEGER NOT NULL,
    PRIMARY KEY (user_id, chat_id)
);

CREATE TABLE IF NOT EXISTS leads (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL,
    username  TEXT,
    name      TEXT,
    source    TEXT NOT NULL,
    content   TEXT NOT NULL,
    ts        INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_user ON leads(user_id);

CREATE TABLE IF NOT EXISTS points (
    user_id      INTEGER NOT NULL,
    chat_id      INTEGER NOT NULL,
    username     TEXT,
    balance      INTEGER NOT NULL DEFAULT 0,
    lifetime     INTEGER NOT NULL DEFAULT 0,
    streak       INTEGER NOT NULL DEFAULT 0,
    checkin_day  TEXT NOT NULL DEFAULT '',
    earn_day     TEXT NOT NULL DEFAULT '',
    earned_today INTEGER NOT NULL DEFAULT 0,
    last_earn    INTEGER NOT NULL DEFAULT 0,
    track        TEXT NOT NULL DEFAULT 'light',
    PRIMARY KEY (user_id, chat_id)
);
CREATE INDEX IF NOT EXISTS idx_points_board ON points(chat_id, lifetime DESC);

CREATE TABLE IF NOT EXISTS points_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL,
    chat_id  INTEGER NOT NULL,
    amount   INTEGER NOT NULL,
    reason   TEXT NOT NULL,
    ts       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plog ON points_log(chat_id, ts);

CREATE TABLE IF NOT EXISTS art (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id  TEXT NOT NULL,
    user_id   INTEGER NOT NULL,
    chat_id   INTEGER NOT NULL,
    username  TEXT,
    file_id   TEXT NOT NULL,
    caption   TEXT,
    votes     INTEGER NOT NULL DEFAULT 0,
    ts        INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_art_round ON art(round_id, votes DESC);

CREATE TABLE IF NOT EXISTS art_votes (
    art_id   INTEGER NOT NULL,
    user_id  INTEGER NOT NULL,
    PRIMARY KEY (art_id, user_id)
);

CREATE TABLE IF NOT EXISTS arcade (
    user_id   INTEGER NOT NULL,
    chat_id   INTEGER NOT NULL,
    game      TEXT NOT NULL,
    username  TEXT,
    score     INTEGER NOT NULL DEFAULT 0,
    ts        INTEGER NOT NULL,
    PRIMARY KEY (user_id, chat_id, game)
);
CREATE INDEX IF NOT EXISTS idx_arcade ON arcade(chat_id, game, score DESC);
"""

_conn = None


def init():
    global _conn
    _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.executescript(SCHEMA)
    _migrate()
    _conn.commit()


def _migrate():
    """Add columns introduced after someone's DB was first created."""
    cols = {r[1] for r in _conn.execute("PRAGMA table_info(points)")}
    if cols and "track" not in cols:
        _conn.execute(
            "ALTER TABLE points ADD COLUMN track TEXT NOT NULL DEFAULT 'light'")


@contextmanager
def cursor():
    cur = _conn.cursor()
    try:
        yield cur
        _conn.commit()
    finally:
        cur.close()


# --- key/value --------------------------------------------------------------

def kv_get(key, default=None):
    with cursor() as c:
        row = c.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def kv_set(key, value):
    with cursor() as c:
        c.execute(
            "INSERT INTO kv(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )


# --- members ----------------------------------------------------------------

def touch_member(user_id, chat_id, username, first_name, counts=True):
    now = int(time.time())
    with cursor() as c:
        c.execute(
            """INSERT INTO members(user_id, chat_id, username, first_name,
                                   first_seen, last_seen, messages, removed)
               VALUES(?,?,?,?,?,?,?,0)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET
                   username   = excluded.username,
                   first_name = excluded.first_name,
                   last_seen  = excluded.last_seen,
                   removed    = 0,
                   messages   = members.messages + ?""",
            (user_id, chat_id, username, first_name, now, now,
             1 if counts else 0, 1 if counts else 0),
        )


def active_members(chat_id):
    with cursor() as c:
        rows = c.execute(
            "SELECT user_id FROM members WHERE chat_id=? AND removed=0", (chat_id,)
        ).fetchall()
    return [r["user_id"] for r in rows]


def mark_removed(user_id, chat_id):
    with cursor() as c:
        c.execute(
            "UPDATE members SET removed=1 WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        )


def member_count(chat_id):
    with cursor() as c:
        row = c.execute(
            "SELECT COUNT(*) n FROM members WHERE chat_id=? AND removed=0", (chat_id,)
        ).fetchone()
    return row["n"]


# --- contributions ----------------------------------------------------------

def record_contribution(tx_hash, wallet, value_wei, block, ts):
    """Returns True if this tx is new (i.e. should be announced)."""
    with cursor() as c:
        try:
            c.execute(
                "INSERT INTO contributions(tx_hash, wallet, value_wei, block, ts) "
                "VALUES(?,?,?,?,?)",
                (tx_hash.lower(), wallet.lower(), str(value_wei), block, ts),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def wallet_seen_before(wallet, exclude_tx):
    with cursor() as c:
        row = c.execute(
            "SELECT COUNT(*) n FROM contributions WHERE wallet=? AND tx_hash!=?",
            (wallet.lower(), exclude_tx.lower()),
        ).fetchone()
    return row["n"] > 0


def presale_totals():
    with cursor() as c:
        row = c.execute(
            "SELECT COUNT(*) txs, COUNT(DISTINCT wallet) wallets, "
            "COALESCE(SUM(CAST(value_wei AS REAL)),0) total FROM contributions"
        ).fetchone()
    return {
        "txs": row["txs"],
        "wallets": row["wallets"],
        "total_bnb": row["total"] / 1e18,
    }


# --- conversation context ---------------------------------------------------

def log_message(chat_id, role, author, content):
    with cursor() as c:
        c.execute(
            "INSERT INTO messages(chat_id, role, author, content, ts) VALUES(?,?,?,?,?)",
            (chat_id, role, author, content[:2000], int(time.time())),
        )
        # keep the table from growing forever
        c.execute(
            """DELETE FROM messages WHERE chat_id=? AND id NOT IN
               (SELECT id FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT 200)""",
            (chat_id, chat_id),
        )


def recent_messages(chat_id, limit):
    with cursor() as c:
        rows = c.execute(
            "SELECT role, author, content FROM messages WHERE chat_id=? "
            "ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
    return list(reversed([dict(r) for r in rows]))


# --- strikes ----------------------------------------------------------------

def add_strike(user_id, chat_id):
    """Bumps and returns the user's strike count for this chat."""
    now = int(time.time())
    with cursor() as c:
        c.execute(
            """INSERT INTO strikes(user_id, chat_id, count, last_ts)
               VALUES(?,?,1,?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET
                   count   = strikes.count + 1,
                   last_ts = excluded.last_ts""",
            (user_id, chat_id, now),
        )
        row = c.execute(
            "SELECT count FROM strikes WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ).fetchone()
    return row["count"]


def clear_strikes(user_id, chat_id):
    with cursor() as c:
        c.execute("DELETE FROM strikes WHERE user_id=? AND chat_id=?",
                  (user_id, chat_id))


# --- leads (marketers routed to DM) -----------------------------------------

def add_lead(user_id, username, name, source, content):
    with cursor() as c:
        c.execute(
            "INSERT INTO leads(user_id, username, name, source, content, ts) "
            "VALUES(?,?,?,?,?,?)",
            (user_id, username, name, source, content[:3000], int(time.time())),
        )


def flag_pitcher(user_id):
    kv_set(f"pitcher:{user_id}", "1")


def is_pitcher(user_id):
    return kv_get(f"pitcher:{user_id}") == "1"


def recent_leads(limit=10):
    with cursor() as c:
        rows = c.execute(
            "SELECT * FROM leads ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# --- points -----------------------------------------------------------------

def get_points(user_id, chat_id):
    with cursor() as c:
        row = c.execute(
            "SELECT * FROM points WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ).fetchone()
    if row:
        return dict(row)
    return {"user_id": user_id, "chat_id": chat_id, "username": None,
            "balance": 0, "lifetime": 0, "streak": 0, "checkin_day": "",
            "earn_day": "", "earned_today": 0, "last_earn": 0,
            "track": "light"}


def add_points(user_id, chat_id, amount, reason, username=None):
    now = int(time.time())
    with cursor() as c:
        c.execute(
            """INSERT INTO points(user_id, chat_id, username, balance, lifetime)
               VALUES(?,?,?,?,?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET
                   balance  = points.balance + ?,
                   lifetime = points.lifetime + ?,
                   username = COALESCE(excluded.username, points.username)""",
            (user_id, chat_id, username, amount, max(amount, 0),
             amount, max(amount, 0)),
        )
        c.execute(
            "INSERT INTO points_log(user_id, chat_id, amount, reason, ts) "
            "VALUES(?,?,?,?,?)",
            (user_id, chat_id, amount, reason, now),
        )


def touch_earn(user_id, chat_id, day, earned_today):
    with cursor() as c:
        c.execute(
            "UPDATE points SET earn_day=?, earned_today=?, last_earn=? "
            "WHERE user_id=? AND chat_id=?",
            (day, earned_today, int(time.time()), user_id, chat_id),
        )


def set_checkin(user_id, chat_id, day, streak):
    with cursor() as c:
        c.execute(
            "UPDATE points SET checkin_day=?, streak=? WHERE user_id=? AND chat_id=?",
            (day, streak, user_id, chat_id),
        )


def top_points(chat_id, limit=10, since_ts=None):
    with cursor() as c:
        if since_ts:
            rows = c.execute(
                """SELECT p.user_id, p.username, SUM(l.amount) AS score
                   FROM points_log l JOIN points p
                     ON p.user_id=l.user_id AND p.chat_id=l.chat_id
                   WHERE l.chat_id=? AND l.ts>=? AND l.amount>0
                   GROUP BY p.user_id ORDER BY score DESC LIMIT ?""",
                (chat_id, since_ts, limit),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT user_id, username, lifetime AS score FROM points "
                "WHERE chat_id=? AND lifetime>0 ORDER BY lifetime DESC LIMIT ?",
                (chat_id, limit),
            ).fetchall()
    return [dict(r) for r in rows]


def points_rank(user_id, chat_id):
    with cursor() as c:
        row = c.execute(
            "SELECT COUNT(*)+1 n FROM points WHERE chat_id=? AND lifetime > "
            "(SELECT lifetime FROM points WHERE user_id=? AND chat_id=?)",
            (chat_id, user_id, chat_id),
        ).fetchone()
    return row["n"] if row else None


# --- art contest ------------------------------------------------------------

def art_round():
    return kv_get("art_round", "")


def start_art_round(round_id, prompt):
    kv_set("art_round", round_id)
    kv_set(f"art_prompt:{round_id}", prompt)


def art_prompt(round_id):
    return kv_get(f"art_prompt:{round_id}", "")


def add_art(round_id, user_id, chat_id, username, file_id, caption):
    with cursor() as c:
        cur = c.execute(
            "INSERT INTO art(round_id, user_id, chat_id, username, file_id, "
            "caption, ts) VALUES(?,?,?,?,?,?,?)",
            (round_id, user_id, chat_id, username, file_id, caption,
             int(time.time())),
        )
        return cur.lastrowid


def already_submitted(round_id, user_id):
    with cursor() as c:
        row = c.execute(
            "SELECT COUNT(*) n FROM art WHERE round_id=? AND user_id=?",
            (round_id, user_id),
        ).fetchone()
    return row["n"] > 0


def vote_art(art_id, user_id):
    """Returns (ok, votes). ok=False if they already voted or it's their own."""
    with cursor() as c:
        row = c.execute("SELECT user_id FROM art WHERE id=?", (art_id,)).fetchone()
        if not row or row["user_id"] == user_id:
            return False, 0
        try:
            c.execute("INSERT INTO art_votes(art_id, user_id) VALUES(?,?)",
                      (art_id, user_id))
        except sqlite3.IntegrityError:
            cur = c.execute("SELECT votes FROM art WHERE id=?", (art_id,)).fetchone()
            return False, cur["votes"]
        c.execute("UPDATE art SET votes = votes + 1 WHERE id=?", (art_id,))
        cur = c.execute("SELECT votes FROM art WHERE id=?", (art_id,)).fetchone()
    return True, cur["votes"]


def art_results(round_id, limit=3):
    with cursor() as c:
        rows = c.execute(
            "SELECT * FROM art WHERE round_id=? ORDER BY votes DESC, ts ASC "
            "LIMIT ?", (round_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def art_count(round_id):
    with cursor() as c:
        row = c.execute("SELECT COUNT(*) n FROM art WHERE round_id=?",
                        (round_id,)).fetchone()
    return row["n"]


# --- arcade high scores -----------------------------------------------------

def record_score(user_id, chat_id, game, username, score):
    """Keeps only a personal best. Returns (is_personal_best, best)."""
    with cursor() as c:
        row = c.execute(
            "SELECT score FROM arcade WHERE user_id=? AND chat_id=? AND game=?",
            (user_id, chat_id, game),
        ).fetchone()
        if row and row["score"] >= score:
            return False, row["score"]
        c.execute(
            """INSERT INTO arcade(user_id, chat_id, game, username, score, ts)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(user_id, chat_id, game) DO UPDATE SET
                   score=excluded.score, username=excluded.username,
                   ts=excluded.ts""",
            (user_id, chat_id, game, username, score, int(time.time())),
        )
    return True, score


def top_scores(chat_id, game, limit=10):
    with cursor() as c:
        rows = c.execute(
            "SELECT user_id, username, score FROM arcade WHERE chat_id=? AND "
            "game=? ORDER BY score DESC LIMIT ?", (chat_id, game, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def set_track(user_id, chat_id, track):
    """Which title ladder this member wears. Creates the row if needed."""
    with cursor() as c:
        c.execute(
            "INSERT INTO points(user_id, chat_id, track) VALUES(?,?,?) "
            "ON CONFLICT(user_id, chat_id) DO UPDATE SET track=excluded.track",
            (user_id, chat_id, track),
        )


def get_track(user_id, chat_id):
    return get_points(user_id, chat_id).get("track") or "light"


def main_chat(fallback=0):
    """The group Homie works in.

    Learned at runtime the first time an admin runs /setgroup, so the chat id
    never has to be known before deployment — which matters because a basic
    group's id CHANGES when Telegram promotes it to a supergroup.
    """
    v = kv_get("main_chat")
    return int(v) if v else fallback


def set_main_chat(chat_id):
    kv_set("main_chat", int(chat_id))
