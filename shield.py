"""Scam shield — the stuff that protects people's wallets.

Three checks:
  1. foreign contract addresses and unapproved links get deleted
  2. new joiners impersonating the team get banned on entry
  3. anyone mentioning a DM gets the "team never DMs first" warning

Every reply here is fixed text, never AI-generated. When the subject is where
to send money, there's no room for a creative answer.
"""

import re
import time
from urllib.parse import urlparse

import config

ADDRESS_RE = re.compile(r"0x[a-fA-F0-9]{40}")
URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"((?:[a-z0-9-]+\.)+[a-z]{2,})(/[^\s]*)?",
    re.IGNORECASE,
)
# phrases that mean "someone DMed me"
DM_RE = re.compile(
    r"\b(?:dm'?e?d me|dmd me|messaged me|pm'?e?d me|inboxed me|"
    r"(?:got|received|getting) (?:a )?(?:dm|pm|message)|"
    r"someone (?:is )?(?:dm|messag|pm)|support (?:dm|messag|contact)ed)\b",
    re.IGNORECASE,
)
# words that only appear in an impersonator's display name
ROLE_WORDS = {"support", "admin", "official", "team", "mod", "moderator",
              "helpdesk", "help", "dev", "founder", "ceo"}

DM_WARNING_COOLDOWN = 600
_last_dm_warning = {}

SCAM_WARNING = (
    "⚠️ heads up fam — <b>the team never DMs first.</b> not Fred, not "
    "admins, not \"support\". anyone who messages you offering help, a "
    "whitelist spot, or a wallet fix is a scammer. block and report.\n\n"
    "the only real addresses are in /ca"
)


def allowed_addresses():
    addrs = {config.PRESALE_ADDRESS, config.TOKEN_ADDRESS}
    addrs |= config.EXTRA_ALLOWED_ADDRESSES
    return {a.lower() for a in addrs if a}


def foreign_addresses(text):
    """0x addresses in the message that aren't ours."""
    ok = allowed_addresses()
    return [a for a in ADDRESS_RE.findall(text) if a.lower() not in ok]


def _domain_allowed(domain):
    domain = domain.lower().removeprefix("www.")
    return any(domain == d or domain.endswith("." + d)
               for d in config.ALLOWED_DOMAINS)


def _tme_allowed(path, bot_username):
    handle = path.strip("/").split("/")[0].split("?")[0].lower()
    allowed = set(config.ALLOWED_TG)
    if bot_username:
        allowed.add(bot_username.lower())
    return handle in allowed


def bad_links(message, bot_username):
    """Links in the message that point anywhere we haven't approved."""
    urls = []
    # Telegram's own entity parsing catches hidden text links too
    for entity, text in message.parse_entities(["url", "text_link"]).items():
        urls.append(entity.url if entity.type == "text_link" else text)
    for match in URL_RE.finditer(message.text or ""):
        urls.append(match.group(0))

    bad = []
    for raw in urls:
        url = raw if "://" in raw else "https://" + raw
        parsed = urlparse(url)
        domain = (parsed.hostname or "").lower()
        if not domain or "." not in domain:
            continue
        if domain in ("t.me", "telegram.me", "telegram.dog"):
            if not _tme_allowed(parsed.path, bot_username):
                bad.append(raw)
        elif not _domain_allowed(domain):
            bad.append(raw)
    return bad


def _squash(text):
    """Lowercase, de-leet, strip everything that isn't a letter."""
    table = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a",
                           "5": "s", "7": "t", "@": "a", "$": "s"})
    text = (text or "").lower().translate(table)
    # common lookalike swaps scammers use in handles
    text = text.replace("rn", "m").replace("vv", "w")
    return re.sub(r"[^a-z]", "", text)


def impersonation_reason(user):
    """Why this user looks like an impersonator, or None if they don't."""
    name = f"{user.first_name or ''} {user.last_name or ''}"
    squashed_name = _squash(name)
    squashed_handle = _squash(user.username)
    words = set(re.findall(r"[a-z]+", name.lower()))

    for protected in config.PROTECTED_NAMES | config.ADMIN_USERNAMES:
        p = _squash(protected)
        if p and (p in squashed_name or p in squashed_handle):
            return f"name mimics '{protected}'"

    project = ("spreadlight" in squashed_name or "homie" in squashed_name
               or "spreadlight" in squashed_handle)
    if project and words & ROLE_WORDS:
        return "project name + staff title"
    if {"support", "helpdesk", "admin"} & words:
        return "staff title in display name"
    return None


def mentions_dm(text, chat_id):
    """True (and rate-limited) when someone says they got a DM."""
    if not DM_RE.search(text or ""):
        return False
    now = time.time()
    if now - _last_dm_warning.get(chat_id, 0) < DM_WARNING_COOLDOWN:
        return False
    _last_dm_warning[chat_id] = now
    return True
