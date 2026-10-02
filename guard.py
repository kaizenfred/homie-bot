"""Content filters: cursing and marketer pitches.

Both work off plain text files you can edit without touching code:
    banned_words.txt   one word or phrase per line
    marketer_words.txt one phrase per line

Matching is normalised, so f*ck, f.u.c.k, fuuuck and fu(k all hit the same rule.
"""

import functools
import pathlib
import re

LEET = str.maketrans({
    "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t",
    "@": "a", "$": "s", "!": "i", "|": "i", "+": "t",
})

# a censored letter is usually one of these
WILDCARD = r"[*#%^]"

# What may sit BETWEEN two letters of one word: punctuation only, and not much
# of it. This used to be [\W_]* — any run of non-word characters, whitespace
# included — which quietly turned every filtered word into a phrase matcher.
# "let's hit it" matched "shit": the apostrophe satisfied the left boundary,
# then s + <space> + hit. Ordinary members were losing messages and collecting
# strikes for it. Deliberate spacing ("f u c k") is handled by despace()
# instead, which is a different shape of evasion and needs a different rule.
SEP = r"[^\w\s]{0,2}"

# Three or more single letters in a row, separated by anything non-word:
# "f u c k", "s.h.i.t", "b-i-t-c-h". Nobody writes like that by accident.
_SPACED_OUT = re.compile(r"(?<![a-z0-9])(?:[a-z][\W_]+){2,}[a-z](?![a-z0-9])")


def normalise(text):
    text = text.lower().translate(LEET)
    # collapse stretched letters: fuuuuck -> fuck, asshole -> ashole.
    # the word list is collapsed the same way, so both sides line up.
    return re.sub(r"(.)\1+", r"\1", text)


def despace(text):
    """Join runs of spaced-out single letters back into words."""
    return _SPACED_OUT.sub(
        lambda m: re.sub(r"[\W_]+", "", m.group(0)), text)


def _load(filename, fallback):
    path = pathlib.Path(filename)
    if not path.exists():
        path.write_text("\n".join(fallback) + "\n", encoding="utf-8")
    words = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip().lower()
        if line:
            words.append(line)
    return words


def _word_regex(word):
    """One word, tolerating separators, censor symbols and common suffixes."""
    tokens = []
    for token in normalise(word).split():
        chars = [f"(?:{re.escape(ch)}|{WILDCARD})" for ch in token]
        tokens.append(SEP.join(chars))
    # between the WORDS of a phrase, whitespace is expected and fine
    return r"[\W_]+".join(tokens) + r"(?:s|es|ed|er|ers|ing|in|y)?"


def _pattern(words):
    if not words:
        return None
    body = "|".join(_word_regex(w) for w in words)
    # boundaries stop "Scunthorpe" and "assessment" from tripping the filter
    return re.compile(r"(?<![a-z])(?:" + body + r")(?![a-z])")


@functools.lru_cache(maxsize=1)
def _profanity():
    return _pattern(_load("banned_words.txt", DEFAULT_PROFANITY))


@functools.lru_cache(maxsize=1)
def _marketer():
    return _pattern(_load("marketer_words.txt", DEFAULT_MARKETER))


def reload_lists():
    """Call after editing either file to pick up changes without a restart."""
    _profanity.cache_clear()
    _marketer.cache_clear()


def has_profanity(text):
    pattern = _profanity()
    if not pattern:
        return False
    clean = normalise(text or "")
    return bool(pattern.search(clean) or pattern.search(despace(clean)))


def is_marketer_pitch(text):
    """True when a message reads like an agency / promo / shill pitch."""
    pattern = _marketer()
    if not pattern:
        return False
    text = text or ""
    hits = pattern.findall(normalise(text))
    # one keyword can be innocent ("nice marketing"), two is a pitch.
    # a very long message with one hit is also a pitch — nobody writes
    # 400 characters about your "marketing" by accident.
    return len(set(hits)) >= 2 or (len(hits) >= 1 and len(text) > 300)


# --- defaults, written to disk on first run ---------------------------------

DEFAULT_PROFANITY = [
    "# one word or phrase per line, # starts a comment",
    "# matching ignores punctuation and letter-stretching",
    "# ADD YOUR OWN: slurs, and anything specific to your community.",
    "fuck", "shit", "bitch", "cunt", "asshole", "bastard", "dickhead",
    "motherfucker", "twat", "wanker", "prick", "slut", "whore",
    "# compounds — the word-boundary rule won't catch these on its own",
    "bullshit", "horseshit", "dipshit", "shithead", "shitshow",
    "dumbass", "jackass", "smartass", "bitchass",
    "fuckboy", "fuckface", "clusterfuck", "fuckery",
    "# scam / raid vocabulary worth catching too",
    "seed phrase", "private key", "send me your wallet",
]

DEFAULT_MARKETER = [
    "# phrases that mean someone is pitching you a service",
    "# two distinct hits (or one in a long message) triggers the reroute",
    "marketing agency", "marketing services", "promotion service",
    "we can promote", "i can promote", "promote your project",
    "grow your community", "boost your community", "increase your holders",
    "guaranteed holders", "real members", "active members",
    "shill service", "shillers", "calls channel", "call channel",
    "influencer marketing", "kol", "kols", "ama host", "host an ama",
    "listing service", "get listed", "cmc listing", "coingecko listing",
    "trending on", "dextools trending", "trending service",
    "press release", "media package", "pr package",
    "our portfolio", "our clients", "dm me for details", "dm for pricing",
    "our agency", "my agency", "partnership proposal", "collab proposal",
    "volume bot", "market making", "market maker",
]
