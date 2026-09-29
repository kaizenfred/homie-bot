"""Removes deleted ("Deleted Account") users from the group.

Important limitation, read this once:
the Telegram Bot API gives a bot NO way to list group members. So this sweep
can only check users the bot has actually seen — anyone who joined or posted
since the bot was added. Members who have been silent since before the bot
arrived are invisible to it.

For a one-time full clear of every deleted account already in the group,
run tools/sweep_deleted.py, which uses your own account via MTProto.
"""

import asyncio
import logging

from telegram.error import BadRequest, Forbidden, RetryAfter

import db

log = logging.getLogger(__name__)

# statuses that mean the user is still in the group
PRESENT = {"member", "restricted", "administrator", "creator"}


def looks_deleted(chat_member):
    """A deleted Telegram account comes back with no name and no username."""
    user = chat_member.user
    if user.is_bot:
        return False
    if chat_member.status not in PRESENT:
        return False
    return not (user.first_name or "").strip() and not user.username


async def kick(bot, chat_id, user_id):
    """Ban then unban = remove without adding them to the ban list."""
    await bot.ban_chat_member(chat_id, user_id)
    await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)


async def sweep(bot, chat_id, limit=None):
    """Check tracked members and remove the deleted ones. Returns (checked, removed)."""
    user_ids = db.active_members(chat_id)
    if limit:
        user_ids = user_ids[:limit]

    checked = removed = 0
    for user_id in user_ids:
        try:
            member = await bot.get_chat_member(chat_id, user_id)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            continue
        except BadRequest:
            # user is no longer resolvable — treat as gone
            db.mark_removed(user_id, chat_id)
            continue
        except Forbidden:
            log.error("bot lost access to chat %s", chat_id)
            break
        checked += 1

        if member.status in ("left", "kicked"):
            db.mark_removed(user_id, chat_id)
        elif looks_deleted(member):
            try:
                await kick(bot, chat_id, user_id)
                db.mark_removed(user_id, chat_id)
                removed += 1
                log.info("removed deleted account %s", user_id)
            except (BadRequest, Forbidden) as e:
                log.warning("could not remove %s: %s", user_id, e)

        await asyncio.sleep(0.12)  # stay well under Telegram's rate limits

    return checked, removed
