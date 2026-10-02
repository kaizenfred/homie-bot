"""Who is allowed to command Homie, and who Telegram thinks runs the chat.

Two separate questions, deliberately kept apart:

  is_admin(user)        — may this person use Homie's admin commands?
  chat_admin_ids(...)   — who does Telegram consider an admin of this chat?

The first one used to be answered by comparing `user.username` to a string in
.env. That is not an identity. Telegram usernames are rented, not owned: when
you change yours the old handle goes back in the pool and anyone may take it.
With ADMIN_IDS empty — which is how the installer ships — the whole admin
surface (/say to broadcast to the group, /leads to read every pitch sent in,
/setgroup to repoint the bot at a different chat, /give to mint Lumens) was
guarded by a name that Fred could lose simply by renaming himself.

So a username match is now only ever a CLAIM. It is honoured once, and only
when Telegram independently agrees the claimant administrates the group. The
numeric id is then pinned to the database and that id is what counts from
then on. Losing or changing the handle no longer matters, and acquiring it
no longer helps.
"""

import logging
import time

import config
import db

log = logging.getLogger(__name__)

PIN_KEY = "admin_ids_pinned"
# How long to trust a fetched copy of the chat's admin list. The cost of a
# long TTL is that somebody promoted to moderator can still be moderated for
# that long; the cost of no cache is an API call per message. Three minutes
# is cheap enough to be invisible either way.
ADMIN_CACHE_SEC = 180

_cache = {}  # chat_id -> (expires_at, frozenset(user_ids))


# --- pinned ids -------------------------------------------------------------

def pinned():
    raw = db.kv_get(PIN_KEY, "") or ""
    out = set()
    for part in raw.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.add(int(part))
    return out


def pin(user_id):
    ids = pinned()
    if user_id in ids:
        return
    ids.add(user_id)
    db.kv_set(PIN_KEY, ",".join(str(i) for i in sorted(ids)))
    log.info("pinned admin id %s", user_id)


def unpin(user_id):
    ids = pinned()
    if user_id not in ids:
        return False
    ids.discard(user_id)
    db.kv_set(PIN_KEY, ",".join(str(i) for i in sorted(ids)))
    return True


def is_admin_id(user_id) -> bool:
    return user_id in config.ADMIN_IDS or user_id in pinned()


def is_admin(user) -> bool:
    """Identity only — no username anywhere near this."""
    if not user:
        return False
    return is_admin_id(user.id)


def claims_admin(user) -> bool:
    """Their handle is on the list, which on its own proves nothing."""
    if not user or not user.username:
        return False
    return user.username.lower() in config.ADMIN_USERNAMES


# --- Telegram's own view ----------------------------------------------------

async def chat_admin_ids(ctx, chat_id):
    """Admin ids for a chat, cached.

    run_guards needs this for every message so admins don't get moderated.
    It used to ask Telegram per message — one extra API round trip for every
    line anybody typed, which is both slow and a direct route into the rate
    limiter on a busy day. One call per five minutes is plenty; admin lists
    do not change by the second.
    """
    now = time.time()
    hit = _cache.get(chat_id)
    if hit and hit[0] > now:
        return hit[1]
    try:
        members = await ctx.bot.get_chat_administrators(chat_id)
        ids = frozenset(m.user.id for m in members)
    except Exception as e:
        log.debug("could not list admins for %s: %s", chat_id, e)
        # Keep a stale list rather than briefly treating admins as members.
        return hit[1] if hit else frozenset()
    _cache[chat_id] = (now + ADMIN_CACHE_SEC, ids)
    return ids


def forget_chat(chat_id):
    _cache.pop(chat_id, None)


# --- the check commands should use ------------------------------------------

async def verify(ctx, update) -> bool:
    """True if this person may run admin commands.

    A pinned id is enough. A bare username match is not: Telegram has to
    confirm they administrate the group first, and then the id gets pinned so
    the handle never matters again.
    """
    user = update.effective_user
    if not user:
        return False
    if is_admin(user):
        return True
    if not claims_admin(user):
        return False

    chat = update.effective_chat
    # In a group, check the group in front of us. In a DM there is no such
    # thing as an admin, so check the group Homie calls home.
    check_in = (chat.id if chat and chat.type in ("group", "supergroup")
                else db.main_chat(config.MAIN_CHAT_ID))

    if not check_in:
        # First run: /setgroup hasn't happened yet, so there is no group to
        # check against and no way to do better than the handle. This is the
        # one moment the claim is taken at face value, and it is also the
        # moment the real owner is the only person in the room.
        log.warning("no main chat yet — trusting the @%s handle once to "
                    "bootstrap admin, id %s", user.username, user.id)
        pin(user.id)
        return True

    if user.id in await chat_admin_ids(ctx, check_in):
        pin(user.id)
        return True

    log.warning("@%s (id %s) matches ADMIN_USERNAMES but is not an admin of "
                "%s — refused", user.username, user.id, check_in)
    return False
