"""Bot-native games. No hosting, no web server — these work the moment the
bot is running.

  /charades  one member acts, everyone guesses  (needs the actor to have
             DM'd the bot once, so Telegram lets Homie send them the word)
  /scramble  unscramble the word, first correct answer wins
  /riddle    emoji puzzle, first correct answer wins

Rounds live in memory on purpose — if the bot restarts mid-round, the round
is simply gone rather than stuck. Winners' Lumens are already banked in
SQLite by the time that matters.
"""

import random
import time

# --- word banks -------------------------------------------------------------
# Mix of crypto, charity, festival and general words. Keep them actable.

CHARADES_WORDS = [
    # on brand
    "lighthouse", "candle", "sunrise", "flashlight", "campfire", "fireworks",
    "solar panel", "disco ball", "lantern", "spotlight", "glow stick",
    # giving
    "donation", "volunteer", "food bank", "high five", "hug", "gift wrap",
    "charity run", "soup kitchen", "blood drive", "helping hand",
    # crypto, lightly
    "diamond hands", "paper hands", "cold wallet", "mining rig", "moon",
    "hodl", "airdrop", "blockchain", "bull market", "bear market",
    # festival / EDM, Fred's world
    "festival wristband", "headliner", "drop the bass", "crowd surf",
    "silent disco", "light show", "main stage", "glitter", "confetti cannon",
    "sound check", "wristband scan", "rave", "stage dive", "laser show",
    # general, easy wins
    "penguin", "astronaut", "skateboard", "pizza delivery", "thunderstorm",
    "roller coaster", "karaoke", "fishing", "yoga", "barbecue",
]

SCRAMBLE_WORDS = [
    ("lumens", "what you earn in here"),
    ("lightworker", "what you are just by showing up"),
    ("charity", "the whole point"),
    ("candle", "one doesn't dim when it lights another"),
    ("beacon", "a rank worth climbing to"),
    ("kindness", "free to give, impossible to fake"),
    ("liquidity", "1% of the tax goes here"),
    ("presale", "where we are right now"),
    ("blockchain", "the ledger nobody can quietly edit"),
    ("nonprofit", "who the charity wallet pays"),
    ("community", "the actual product"),
    ("sunrise", "happens every single day, still undefeated"),
    ("generous", "the only flex that ages well"),
    ("transparent", "you can check every wallet yourself"),
    ("volunteer", "shows up without being asked"),
    ("festival", "where Fred spent his twenties"),
    ("gratitude", "the cheapest thing to give"),
    ("lantern", "portable, warm, ancient tech"),
    ("momentum", "hard to start, harder to stop"),
    ("brightness", "turn it up"),
]

RIDDLES = [
    ("🌞 + 📈", "sunrise", ["sunrise", "sun rise", "sun up"]),
    ("💎 + 🙌", "diamond hands", ["diamond hands", "diamondhands"]),
    ("🕯 + 🕯 + 🕯", "candlelight", ["candlelight", "candle light", "candles"]),
    ("🏠 + 💡", "lighthouse", ["lighthouse", "light house"]),
    ("❤️ + 🎁", "giving", ["giving", "charity", "generosity", "gift"]),
    ("🌕 + 🚀", "to the moon", ["to the moon", "moon", "moonshot"]),
    ("🤝 + 5️⃣", "high five", ["high five", "highfive", "hi five", "hi 5"]),
    ("🔦 + 🌑", "light in the dark", ["light in the dark", "light in dark"]),
    ("🐝 + 💡", "be the light", ["be the light", "bethelight"]),
    ("🎪 + 🎶", "music festival", ["music festival", "festival", "concert"]),
    ("💧 + ⚡", "hydration", ["hydration", "hydrate", "electrolytes"]),
    ("🌱 + 💰", "growth", ["growth", "grow", "growing"]),
    ("👐 + 🌍", "give back", ["give back", "giveback", "helping the world"]),
    ("🔒 + 💧", "locked liquidity", ["locked liquidity", "liquidity lock", "lp lock"]),
    ("⭐ + ⭐ + ⭐", "stars", ["stars", "star", "starlight"]),
]

ROUND_SECONDS = 90
_rounds = {}          # chat_id -> round dict


# --- helpers ----------------------------------------------------------------

def active(chat_id):
    r = _rounds.get(chat_id)
    if r and time.time() - r["started"] > ROUND_SECONDS:
        _rounds.pop(chat_id, None)
        return None
    return r


def end(chat_id):
    return _rounds.pop(chat_id, None)


def seconds_left(chat_id):
    r = _rounds.get(chat_id)
    if not r:
        return 0
    return max(0, int(ROUND_SECONDS - (time.time() - r["started"])))


def _norm(text):
    return "".join(ch for ch in (text or "").lower() if ch.isalnum() or ch == " ").strip()


# --- charades ---------------------------------------------------------------

def start_charades(chat_id, actor_id, actor_name):
    word = random.choice(CHARADES_WORDS)
    _rounds[chat_id] = {
        "kind": "charades", "answer": word, "accept": [word],
        "actor_id": actor_id, "actor_name": actor_name,
        "started": time.time(), "hint_given": False,
    }
    return word


# --- scramble ---------------------------------------------------------------

def _scramble(word):
    letters = list(word)
    for _ in range(12):
        random.shuffle(letters)
        if "".join(letters) != word:
            break
    return " ".join(l.upper() for l in letters)


def start_scramble(chat_id):
    word, clue = random.choice(SCRAMBLE_WORDS)
    _rounds[chat_id] = {
        "kind": "scramble", "answer": word, "accept": [word],
        "clue": clue, "scrambled": _scramble(word),
        "started": time.time(), "hint_given": False,
    }
    return _rounds[chat_id]


# --- riddle -----------------------------------------------------------------

def start_riddle(chat_id):
    emoji, answer, accept = random.choice(RIDDLES)
    _rounds[chat_id] = {
        "kind": "riddle", "answer": answer, "accept": accept,
        "emoji": emoji, "started": time.time(), "hint_given": False,
    }
    return _rounds[chat_id]


# --- guessing ---------------------------------------------------------------

def check_guess(chat_id, user_id, text):
    """Returns the round dict if this message won it, else None."""
    r = active(chat_id)
    if not r:
        return None
    # the actor can't win their own charade
    if r["kind"] == "charades" and user_id == r["actor_id"]:
        return None

    guess = _norm(text)
    if not guess:
        return None
    for candidate in r["accept"]:
        c = _norm(candidate)
        if guess == c or (len(c) > 5 and c in guess):
            return end(chat_id)
    return None


def hint(chat_id):
    """One hint per round. Returns the hint text or None."""
    r = active(chat_id)
    if not r or r["hint_given"]:
        return None
    r["hint_given"] = True
    answer = r["answer"]
    shown = "".join(ch if (i == 0 or ch == " ") else "_"
                    for i, ch in enumerate(answer))
    return f"{shown}  ({len(answer.replace(' ', ''))} letters)"
