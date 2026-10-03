"""SpreadLight community bot — entrypoint.

Run with:  python bot.py
"""

import datetime as dt
import logging
import random
import re
import sys
import time

from telegram import (
    ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup,
    InlineQueryResultGame, Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.error import Forbidden
from telegram.ext import (
    Application, ApplicationHandlerStop, CallbackQueryHandler, CommandHandler,
    ContextTypes, InlineQueryHandler,
    MessageHandler, filters,
)

import admins
import arcade_server
import community
import config
import db
import games
import guard
import moderation
import persona
import points
import presale
import shield
import stickers

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("spreadlight")


def is_admin(update: Update) -> bool:
    """Fast, identity-only check. See admins.py for why usernames don't count."""
    return admins.is_admin(update.effective_user)


async def admin_ok(update: Update, ctx) -> bool:
    """The check every admin command uses. Verifies a handle claim properly."""
    return await admins.verify(ctx, update)


def body_of(msg) -> str:
    """The text of a message, wherever Telegram put it.

    A caption is text. Photos and videos carry theirs in `caption`, and for a
    long time the guards only ever read `text` — so a fake contract address
    posted under an image walked straight past the shield.
    """
    if not msg:
        return ""
    return msg.text or msg.caption or ""


_NAME_RE = None


def addressed(ctx, text) -> bool:
    """Is Homie being spoken to?

    Matches his @handle AND his name. The two differ — the handle is
    @SpreadLightBot, the name is "homie" — and people only ever type the name.
    """
    global _NAME_RE
    if not text:
        return False
    low = text.lower()
    handle = (ctx.bot.username or "").lower()
    if handle and f"@{handle}" in low:
        return True
    if _NAME_RE is None:
        names = set(config.BOT_NICKNAMES)
        if ctx.bot.first_name:
            names.add(ctx.bot.first_name.lower())
        names = {re.escape(n) for n in names if n}
        # "homie" is ordinary slang in this community. A possessive or
        # determiner in front of it means someone is talking about a mate,
        # not to the bot — "my homie just aped in" is not a question for him.
        _NAME_RE = (re.compile(
            r"(?<![a-z0-9])(?<!my )(?<!your )(?<!his )(?<!her )(?<!our )"
            r"(?<!their )(?<!that )(?<!some )(?<!a )(?<!the )"
            r"(?:" + "|".join(names) + r")(?![a-z0-9])")
            if names else re.compile(r"(?!x)x"))
    return bool(_NAME_RE.search(low))


def display_name(user) -> str:
    return user.first_name or user.username or f"user{user.id}"


# --- commands ---------------------------------------------------------------

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        if await admin_ok(update, ctx):
            db.kv_set("founder_dm", update.effective_chat.id)
        if ctx.args and ctx.args[0] == "play":
            # Arrived from the group's arcade menu, having never opened a
            # chat with the bot. Drop them straight into the arcade rather
            # than a greeting they have to read before finding /play again.
            await cmd_play(update, ctx)
            return
        if ctx.args and ctx.args[0] == "pitch":
            ctx.user_data["pitch_mode"] = True
            await update.effective_message.reply_text(
                "aight go ahead — who are you, what do you do, and what are "
                "you proposing? send it in one message and I'll put it in "
                "front of Fred"
            )
            return
    extra = ("\n\n🛡 /mod — moderation commands · /health — my permissions"
             if admins.is_admin(update.effective_user) else "")
    await update.effective_message.reply_text(
        "yo, I'm Homie ✨ I hang out here.\n\n"
        "/howtobuy — never bought crypto? start here\n"
        "/presale — progress and countdown\n"
        "/ca — official contract addresses\n"
        "/stats — community numbers\n"
        "/play — arcade · /rank — your Lumens\n"
        "/ask — ask me anything about the project\n\n"
        "Tag me or reply to me and I'll answer." + extra
    )


async def cmd_presale(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    raised = await presale.raised_bnb()
    await update.effective_message.reply_text(
        f"<b>$LIGHT presale</b>\n{presale.progress_block(raised)}\n\n"
        f'<a href="{config.PRESALE_URL}">join the presale</a> · /ca for addresses\n\n'
        "<i>the team never DMs first</i>",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def cmd_ca(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Fixed text, never AI. Tap-to-copy addresses."""
    lines = ["<b>official $LIGHT addresses</b>"]
    if config.TOKEN_ADDRESS_DISPLAY:
        lines.append(f"\ntoken\n<code>{config.TOKEN_ADDRESS_DISPLAY}</code>")
    if config.PRESALE_ADDRESS_DISPLAY:
        lines.append(f"\npresale pool\n<code>{config.PRESALE_ADDRESS_DISPLAY}</code>")
    lines.append(f'\n<a href="{config.PRESALE_URL}">presale on PinkSale</a>')
    lines.append("\n⚠️ any other address posted anywhere is a scam. "
                 "tap an address to copy it — never retype one.")
    await update.effective_message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def cmd_howtobuy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Fixed text, never AI.

    The buy flow moves real money, so it is not generated. A model that
    invents a step here costs somebody their BNB. Homie can talk around it
    conversationally — knowledge.md is loaded for that — but the canonical
    steps live in this string and nowhere else.
    """
    text = (
        "🪜 <b>how to get $LIGHT</b>\n"
        "never done this before? this is the whole thing, in order.\n\n"

        "<b>1 · get some BNB</b>\n"
        "any big exchange that lists BNB — binance, coinbase, kraken, mexc. "
        "you'll need ID verification, which can take a day or two, so don't "
        "start this in the last hour of the sale.\n\n"

        "<b>2 · make a wallet</b>\n"
        "metamask or trust wallet, both free. set the network to "
        "<b>BNB Smart Chain</b>.\n"
        "it shows you 12 or 24 recovery words — write them on paper, keep "
        "them offline. never type them into anything, never photograph them, "
        "never send them to anyone. not to me, not to the founder, not to "
        "\"support\". anyone asking is robbing you.\n\n"

        "<b>3 · send the BNB to your wallet</b>\n"
        "this is the step that loses people money, so go slow:\n"
        "• the network must say <b>BNB Smart Chain</b> / <b>BEP20</b>. not "
        "BEP2, not ethereum, not ERC-20\n"
        "• some exchanges don't offer BEP20 for BNB. if yours doesn't, use "
        "one that does — don't pick the closest-looking option\n"
        "• copy-paste your address, never retype it\n"
        "• nervous? send a tiny test amount first. costs pennies\n"
        "• leave ~0.002 BNB spare for gas, or you can't afford the fee to "
        "contribute\n\n"

        "<b>4 · contribute</b>\n"
        "open the presale link from /ca, connect your wallet, enter an "
        "amount, confirm. min 0.05 BNB, max 1 BNB per wallet.\n\n"

        "<b>5 · claim when it's over</b>\n"
        "tokens don't land straight away. after the sale closes and gets "
        "finalised, come back to the same pinksale page and claim. same "
        "wallet, same page — there is no separate claim site, and anyone "
        "sending you one is scamming you.\n\n"

        "if we don't hit the 5 BNB soft cap, the sale fails and you withdraw "
        "your BNB back through pinksale. your money isn't trapped.\n\n"

        "⚠️ the team never DMs first. one presale link, it's in /ca. "
        "stuck anywhere? ask in here — that's what we're for ✨"
    )
    await update.effective_message.reply_text(
        text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    t = db.presale_totals()
    try:
        live = await ctx.bot.get_chat_member_count(chat_id)
    except Exception:
        live = "?"
    await update.effective_message.reply_text(
        f"✨ Lightworkers: {live}\n"
        f"🗣 Active in chat: {db.member_count(chat_id)}\n"
        f"🤝 Contributions: {t['txs']} from {t['wallets']} wallets\n"
        f"💰 Tracked total: {t['total_bnb']:.3f} BNB"
    )


async def cmd_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    question = " ".join(ctx.args) if ctx.args else ""
    if not question:
        await msg.reply_text("Ask me something — `/ask what is the charity tax?`")
        return
    chat_id = update.effective_chat.id
    author = display_name(update.effective_user)
    db.log_message(chat_id, "user", author, question)
    if not ai_allowed(ctx, chat_id, update.effective_user.id):
        await msg.reply_text("gimme a sec fam, one at a time 😄")
        return
    await ctx.bot.send_chat_action(chat_id, ChatAction.TYPING)
    answer = await persona.respond_to(chat_id, ctx.bot.first_name, author)
    if answer:
        db.log_message(chat_id, "assistant", ctx.bot.first_name, answer)
        await msg.reply_text(answer)


async def cmd_sweep(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await admin_ok(update, ctx):
        return
    msg = await update.effective_message.reply_text("Sweeping for deleted accounts…")
    checked, removed = await moderation.sweep(ctx.bot, update.effective_chat.id)
    await msg.edit_text(f"Checked {checked} members. Removed {removed} deleted accounts.")


async def cmd_say(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Broadcast to the main chat: /say your message here"""
    if not await admin_ok(update, ctx):
        return
    text = " ".join(ctx.args)
    if not text:
        await update.effective_message.reply_text("Usage: /say <message>")
        return
    await ctx.bot.send_message(db.main_chat(config.MAIN_CHAT_ID), text)


async def cmd_leads(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await admin_ok(update, ctx):
        return
    rows = db.recent_leads(10)
    if not rows:
        await update.effective_message.reply_text("no pitches yet")
        return
    out = []
    for r in rows:
        handle = f"@{r['username']}" if r["username"] else r["name"]
        out.append(f"• {handle} [{r['source']}] — {r['content'][:120]}")
    await update.effective_message.reply_text("\n\n".join(out))


async def cmd_reload(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Pick up edits to banned_words.txt / marketer_words.txt without a restart."""
    if not await admin_ok(update, ctx):
        return
    guard.reload_lists()
    await update.effective_message.reply_text("word lists reloaded")


async def cmd_forgive(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Reply to someone with /forgive to wipe their strikes and unmute them."""
    if not await admin_ok(update, ctx):
        return
    chat_id = update.effective_chat.id
    user_id, label, rest = await _target_of(update, ctx)
    if not user_id:
        await update.effective_message.reply_text(label)
        return
    db.clear_strikes(user_id, chat_id)
    # The pitch flag is the one that bites hardest when it's wrong: a member
    # the keyword filter mistook for an agency gets routed to the leads pile
    # for good and Homie never replies to them in DM again. Forgiveness has
    # to mean that too.
    db.clear_pitcher(user_id)
    disarm_captcha(ctx, chat_id, user_id)
    try:
        chat = await ctx.bot.get_chat(chat_id)
        perms = chat.permissions or ChatPermissions(
            can_send_messages=True, can_send_other_messages=True,
            can_add_web_page_previews=True, can_send_polls=True,
            can_invite_users=True,
        )
        await ctx.bot.restrict_chat_member(chat_id, user_id, permissions=perms)
    except Exception:
        pass
    await update.effective_message.reply_text(f"{label} is clean, we move on")


# --- manual moderation ------------------------------------------------------
#
# Everything above this line is automatic. None of it is a substitute for an
# owner being able to act: the shield catches a pattern, but a human spotting
# a raid, a troll or a bad actor needs to be able to say so directly, and
# needs to be able to undo the bot when it gets somebody wrong.

async def _target_of(update, ctx):
    """Who an admin command is aimed at, and what's left of the arguments.

    Returns (user_id, label, rest). `rest` matters: with a reply the whole
    argument list is the reason, but when the target came from the arguments
    the first one has been used up. Getting that wrong silently ate the
    reason on "/ban spamming" and read a user id as a mute duration.
    """
    msg = update.effective_message
    args = list(ctx.args or [])
    if msg.reply_to_message and msg.reply_to_message.from_user:
        return (msg.reply_to_message.from_user.id,
                display_name(msg.reply_to_message.from_user), args)
    if args:
        arg = args[0].lstrip("@")
        rest = args[1:]
        if arg.lstrip("-").isdigit():
            return int(arg), f"user {arg}", rest
        found = db.find_member(arg, update.effective_chat.id)
        if found:
            return found["user_id"], found["first_name"] or f"@{arg}", rest
        # Telegram gives bots no way to turn a handle into an id unless the
        # bot has seen that person before. Say that plainly instead of
        # failing in a way that looks like the command is broken.
        return None, (
            f"I've never seen @{arg} post here, so I can't look up their id. "
            "Reply to one of their messages instead, or give me the numeric "
            "id — /id while replying to them shows it."), rest
    return None, "reply to someone, or give me an @handle or a user id", args


async def cmd_ban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin: /ban (as a reply, or with a handle/id) [reason]"""
    if not await admin_ok(update, ctx):
        return
    chat_id = update.effective_chat.id
    user_id, label, rest = await _target_of(update, ctx)
    if not user_id:
        await update.effective_message.reply_text(label)
        return
    if admins.is_admin_id(user_id) or user_id in await admins.chat_admin_ids(
            ctx, chat_id):
        await update.effective_message.reply_text("not banning an admin fam")
        return
    reason = " ".join(rest) or "no reason given"
    try:
        await ctx.bot.ban_chat_member(chat_id, user_id)
    except Exception as e:
        await update.effective_message.reply_text(f"couldn't ban them: {e}")
        return
    db.mark_removed(user_id, chat_id)
    await update.effective_message.reply_text(
        f"banned {label} — {reason}\nundo with <code>/unban {user_id}</code>",
        parse_mode=ParseMode.HTML)


async def cmd_unban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin: /unban <id or @handle>. Lets a banned person rejoin."""
    if not await admin_ok(update, ctx):
        return
    chat_id = update.effective_chat.id
    user_id, label, rest = await _target_of(update, ctx)
    if not user_id:
        await update.effective_message.reply_text(label)
        return
    try:
        # only_if_banned keeps this from silently kicking a current member
        await ctx.bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
    except Exception as e:
        await update.effective_message.reply_text(f"couldn't unban them: {e}")
        return
    db.clear_strikes(user_id, chat_id)
    await update.effective_message.reply_text(
        f"{label} can come back in. they'll need a fresh invite link")


async def cmd_mute(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin: /mute [minutes] as a reply. Default MUTE_MINUTES."""
    if not await admin_ok(update, ctx):
        return
    chat_id = update.effective_chat.id
    user_id, label, rest = await _target_of(update, ctx)
    if not user_id:
        await update.effective_message.reply_text(label)
        return
    minutes = config.MUTE_MINUTES
    for arg in rest:
        if arg.isdigit():
            minutes = max(1, min(int(arg), 60 * 24 * 365))
            break
    until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)
    try:
        await ctx.bot.restrict_chat_member(
            chat_id, user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until)
    except Exception as e:
        await update.effective_message.reply_text(f"couldn't mute them: {e}")
        return
    await update.effective_message.reply_text(
        f"{label} is muted for {minutes} min. /unmute to lift it early")


async def cmd_unmute(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin: /unmute as a reply. Also clears their strikes."""
    if not await admin_ok(update, ctx):
        return
    chat_id = update.effective_chat.id
    user_id, label, rest = await _target_of(update, ctx)
    if not user_id:
        await update.effective_message.reply_text(label)
        return
    chat = await ctx.bot.get_chat(chat_id)
    perms = chat.permissions or ChatPermissions(
        can_send_messages=True, can_send_other_messages=True,
        can_add_web_page_previews=True, can_send_polls=True,
        can_invite_users=True)
    try:
        await ctx.bot.restrict_chat_member(chat_id, user_id, permissions=perms)
    except Exception as e:
        await update.effective_message.reply_text(f"couldn't unmute them: {e}")
        return
    db.clear_strikes(user_id, chat_id)
    # A pending captcha mute is the other way somebody ends up silenced, and
    # an admin unmuting them means they are vouched for — so stand the timer
    # down rather than removing them a minute later.
    disarm_captcha(ctx, chat_id, user_id)
    await update.effective_message.reply_text(f"{label} can talk again ✨")


async def cmd_warn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin: /warn as a reply [reason]. A strike without deleting anything."""
    if not await admin_ok(update, ctx):
        return
    chat_id = update.effective_chat.id
    user_id, label, rest = await _target_of(update, ctx)
    if not user_id:
        await update.effective_message.reply_text(label)
        return
    reason = " ".join(rest)
    strikes = db.add_strike(user_id, chat_id,
                            config.STRIKE_DECAY_HOURS * 3600)
    tail = f" — {reason}" if reason else ""
    await update.effective_message.reply_text(
        f"{label}: strike {strikes} of {config.PROFANITY_STRIKES}{tail}")


async def cmd_strikes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin: who's on strikes in this chat."""
    if not await admin_ok(update, ctx):
        return
    chat_id = update.effective_chat.id
    rows = db.strike_board(chat_id)
    if not rows:
        await update.effective_message.reply_text("nobody's on strikes ✨")
        return
    now = int(time.time())
    lines = [f"<b>strikes</b> (forgiven after "
             f"{config.STRIKE_DECAY_HOURS}h idle)"]
    for r in rows:
        who_ = (f"@{r['username']}" if r["username"]
                else r["first_name"] or f"user {r['user_id']}")
        hours = (now - (r["last_ts"] or now)) // 3600
        lines.append(f"• {who_} — {r['count']}, last {hours}h ago")
    await update.effective_message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_del(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin: reply to a message with /del to remove it and the command."""
    if not await admin_ok(update, ctx):
        return
    msg = update.effective_message
    if not msg.reply_to_message:
        await msg.reply_text("reply to the message you want gone")
        return
    try:
        await msg.reply_to_message.delete()
    except Exception as e:
        await msg.reply_text(f"couldn't delete it: {e}")
        return
    try:
        await msg.delete()
    except Exception:
        pass


async def cmd_mod(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin: the moderation cheat sheet, since none of this is discoverable."""
    if not await admin_ok(update, ctx):
        return
    await update.effective_message.reply_text(
        "<b>🛡 moderation</b>\n"
        "most of these work as a reply, or with an @handle / user id\n\n"
        "/del — delete the message you replied to\n"
        "/warn [reason] — a strike, nothing deleted\n"
        "/mute [minutes] — default "
        f"{config.MUTE_MINUTES}\n"
        "/unmute — lift a mute and clear their strikes\n"
        "/ban [reason] · /unban &lt;id&gt;\n"
        "/forgive — wipe strikes, unmute, clear a pitch flag\n"
        "/strikes — who's on strikes here\n"
        "/sweep — remove deleted accounts\n"
        "/health — what I can and can't do in this group\n\n"
        f"automatic: scam shield, {config.PROFANITY_STRIKES}-strike language "
        f"filter, join captcha, impersonator ban",
        parse_mode=ParseMode.HTML)


async def cmd_health(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin: does Homie actually have the rights he needs here?

    The permission that matters is the one you find out about during a raid.
    This asks Telegram up front.
    """
    if not await admin_ok(update, ctx):
        return
    chat_id = update.effective_chat.id
    lines = ["<b>🩺 health</b>"]
    try:
        me = await ctx.bot.get_chat_member(chat_id, ctx.bot.id)
        status = me.status
        lines.append(f"my role: {status}")
        if status != "administrator":
            lines.append("❌ <b>I'm not an admin here</b> — I can't delete "
                         "anything, mute anyone or run the captcha")
        else:
            checks = [
                ("delete messages", getattr(me, "can_delete_messages", None)),
                ("ban / remove users", getattr(me, "can_restrict_members", None)),
                ("invite users", getattr(me, "can_invite_users", None)),
            ]
            for label, ok in checks:
                lines.append(f"{'✅' if ok else '❌'} {label}")
            if not getattr(me, "can_delete_messages", None):
                lines.append("\n⚠️ without delete, the shield can spot a scam "
                             "but can't remove it")
    except Exception as e:
        lines.append(f"couldn't read my own permissions: {e}")

    home = db.main_chat(config.MAIN_CHAT_ID)
    lines.append(f"\nhome chat: <code>{home or 'not set — run /setgroup'}</code>")
    if home and home != chat_id:
        lines.append("⚠️ this isn't the home chat — alerts go elsewhere")
    lines.append(f"founder DM: {'✅' if founder_chat_id() else '❌ DM me once'}")
    lines.append(f"pinned admins: {len(admins.pinned()) or 'none yet'}")
    lines.append(f"shield: {'on' if config.SHIELD_ENABLED else 'OFF'} · "
                 f"captcha: {'on' if config.CAPTCHA_ENABLED else 'OFF'} · "
                 f"language filter: "
                 f"{'on' if config.PROFANITY_FILTER else 'OFF'}")
    if not config.ALLOWED_TG:
        lines.append("⚠️ ALLOWED_TG is empty — I'd delete our own invite link")
    await update.effective_message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML)


# --- stickers ---------------------------------------------------------------

EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]+")


async def _image_bytes(msg, ctx):
    """The picture attached to a message, whatever shape it arrived in."""
    src = msg.reply_to_message or msg
    if src.photo:
        f = await ctx.bot.get_file(src.photo[-1].file_id)     # biggest size
    elif src.document and (src.document.mime_type or "").startswith("image/"):
        f = await ctx.bot.get_file(src.document.file_id)
    elif src.sticker:
        f = await ctx.bot.get_file(src.sticker.file_id)
    else:
        return None
    return bytes(await f.download_as_bytearray())


async def _make_sticker(update, ctx, kind):
    """Convert a logo and hand it back ready for @Stickers.

    It does NOT try to push into the community pack, and that's Telegram's
    rule rather than a shortcut: addStickerToSet is documented as working on
    "a set created by the bot". t.me/addstickers/SpreadLight was made by a
    person through @Stickers, so no bot can add to it, ever. What Homie CAN
    do is the part that's actually fiddly — cutting the background, sizing to
    exactly 512, and giving the art an outline so it survives both themes —
    and then hand back a file that @Stickers will accept as-is.

    /sticker own puts it in a second, bot-owned pack instead, for anyone who
    would rather Homie kept his own.
    """
    if not await admin_ok(update, ctx):
        return
    msg = update.effective_message
    if not stickers.available():
        await msg.reply_text(
            "I can't process images — Pillow isn't installed yet. On the "
            "server:\n<code>bash /opt/homie/app/deploy/update.sh</code>",
            parse_mode=ParseMode.HTML)
        return

    data = await _image_bytes(msg, ctx)
    if not data:
        await msg.reply_text(
            f"send me a logo, or reply to one, with /{kind}\n\n"
            "a PNG with transparency is ideal, but a logo on a plain white or "
            "black card works too — I'll cut the card off.\n"
            f"<code>/{kind} 🕊</code> sets the emoji · "
            f"<code>/{kind} square</code> keeps the background · "
            f"<code>/{kind} own</code> puts it in my own pack",
            parse_mode=ParseMode.HTML)
        return

    args = " ".join(ctx.args or [])
    low = args.lower()
    faces = EMOJI_RE.findall(args)
    cut = "never" if "square" in low else "always" if "cut" in low else "auto"

    try:
        image, note = stickers.to_sticker(data, emoji=(kind == "emoji"),
                                          cut=cut)
    except Exception as e:
        log.exception("sticker conversion failed")
        await msg.reply_text(f"couldn't convert that one: {e}")
        return

    if "own" in low:
        try:
            await stickers.add_to_pack(ctx.bot, update.effective_user.id,
                                       image, faces or ["✨"], kind=kind)
        except Exception as e:
            log.exception("sticker pack add failed")
            await msg.reply_text(f"Telegram wouldn't take it: {e}")
            return
        link = stickers.pack_link(ctx.bot.username, kind)
        await msg.reply_text(f"in my own pack ✨ <i>{note}</i>\n{link}",
                             parse_mode=ParseMode.HTML,
                             disable_web_page_preview=True)
        return

    target = stickers.community_pack() or "your pack"
    await msg.reply_document(
        document=image,
        filename=f"{kind}.webp",
        caption=(f"ready — {stickers.describe(image)}\n<i>{note}</i>\n\n"
                 f"send this file to @Stickers and pick <b>{target}</b>. "
                 f"It has to go through @Stickers because a bot can only add "
                 f"to a pack it made itself.\n\nthen reply to the sticker "
                 f"here with <code>/stickeruse welcome</code> to put it on a "
                 f"moment."),
        parse_mode=ParseMode.HTML)


async def cmd_sticker(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin: /sticker [emoji] [square|cut|own] — a logo becomes a sticker."""
    await _make_sticker(update, ctx, "sticker")


async def cmd_emoji(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin: /emoji [emoji] — same, at the 100x100 custom emoji needs."""
    await _make_sticker(update, ctx, "emoji")


async def cmd_stickerpack(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """The community pack. /stickerpack <link> (admin) points me at it."""
    msg = update.effective_message
    if ctx.args and await admin_ok(update, ctx):
        stickers.set_community_pack(ctx.args[0])
        await msg.reply_text(
            f"got it — the fam's pack is <b>{stickers.community_pack()}</b>",
            parse_mode=ParseMode.HTML)
        return

    lines = ["<b>✨ stickers</b>"]
    pack = stickers.community_pack()
    if pack:
        lines.append(f'<a href="https://t.me/addstickers/{pack}">'
                     f"t.me/addstickers/{pack}</a>")
    else:
        lines.append("<i>no pack set — admins: /stickerpack &lt;link&gt;</i>")
    if stickers.owner_of("sticker"):
        lines.append("mine: " + stickers.pack_link(ctx.bot.username))

    assigned = [r for r in stickers.ROLES if stickers.for_role(r)]
    if assigned:
        lines.append("\nI use one for: " + ", ".join(assigned))
    await msg.reply_text("\n".join(lines), parse_mode=ParseMode.HTML,
                         disable_web_page_preview=True)


async def cmd_stickeruse(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin: reply to a sticker with /stickeruse <role> to wire it to a moment."""
    if not await admin_ok(update, ctx):
        return
    msg = update.effective_message
    role = (ctx.args[0].lower() if ctx.args else "")

    if role not in stickers.ROLES:
        lines = ["<b>sticker moments</b>"]
        for name, what in stickers.ROLES.items():
            mark = "✅" if stickers.for_role(name) else "—"
            lines.append(f"{mark} <code>{name}</code> — {what}")
        lines.append("\nreply to a sticker with <code>/stickeruse welcome</code>"
                     "\n<code>/stickeruse welcome off</code> to clear one")
        await msg.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        return

    if len(ctx.args) > 1 and ctx.args[1].lower() in ("off", "none", "clear"):
        stickers.unassign(role)
        await msg.reply_text(f"cleared the {role} sticker")
        return

    if not (msg.reply_to_message and msg.reply_to_message.sticker):
        await msg.reply_text("reply to the sticker you want for that moment")
        return
    stickers.assign(role, msg.reply_to_message.sticker.file_id)
    await msg.reply_text(f"that's the <b>{role}</b> sticker now — "
                         f"{stickers.ROLES[role]}", parse_mode=ParseMode.HTML)


async def cmd_play(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Post the arcade menu. Each button sends that game's card."""
    if not config.ARCADE_ENABLED:
        await update.effective_message.reply_text(
            "arcade isn't switched on yet fam. try /scramble or /riddle")
        return
    rows = [[InlineKeyboardButton(title, callback_data=f"arc:{short}")]
            for short, (_, title, _) in arcade_server.GAMES.items()]
    await update.effective_message.reply_text(
        "🕹 <b>the arcade</b>\npick one — I'll send it to your DMs so the chat stays clear. high scores still go on the group board",
        parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(rows))


async def on_arcade_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Menu button -> send that person their own game card, in their DMs.

    The card used to go to the group, so every tap dropped another one into
    the chat and everybody watched everybody else pick a game. Sending it to
    the tapper's private chat keeps the group quiet and gives each player
    their own card — which is also where their own high score belongs.
    """
    q = update.callback_query
    short = q.data.split(":", 1)[1]
    try:
        await ctx.bot.send_game(q.from_user.id, short)
    except Forbidden:
        # They have never opened a chat with the bot, so it may not DM them.
        # answerCallbackQuery accepts a t.me/<bot>?start= link, which opens
        # the bot for them — the one URL shape Telegram allows here.
        handle = ctx.bot.username
        await q.answer(url=f"https://t.me/{handle}?start=play")
        return
    except Exception:
        log.exception("send_game failed for %s", short)
        await q.answer(
            f"couldn't open {short} — it may not be registered yet",
            show_alert=True)
        return
    await q.answer("sent to your DMs 🕹")


async def on_game_launch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Telegram's own Play button -> hand back a signed, per-user URL."""
    q = update.callback_query
    short = q.game_short_name
    if short not in arcade_server.GAMES:
        await q.answer("unknown game", show_alert=True)
        return
    # Two different chats, and conflating them is what broke the leaderboard.
    # The card lives in the player's DM; Lumens and /scores belong to the
    # group. Telegram's own scoreboard has to be written back to the chat the
    # card is actually in, everything else has to be filed against the group.
    board_chat = db.main_chat(config.MAIN_CHAT_ID)
    card_chat = q.message.chat.id if q.message else None
    if q.message and q.message.chat.type != "private":
        board_chat = q.message.chat.id
    url = arcade_server.play_url(
        q.from_user.id, board_chat, short,
        card_chat=card_chat,
        message_id=q.message.message_id if q.message else None,
        inline_id=q.inline_message_id,
    )
    await q.answer(url=url)


async def cmd_scores(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = community._board_chat(update)
    blocks = []
    for short, (_, title, _) in arcade_server.GAMES.items():
        rows = db.top_scores(chat_id, short, 5)
        if not rows:
            continue
        lines = [f"<b>{title}</b>"]
        for i, r in enumerate(rows):
            mark = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i + 1}."
            who = f"@{r['username']}" if r["username"] else f"user{r['user_id']}"
            lines.append(f"{mark} {who} — {r['score']}")
        blocks.append("\n".join(lines))
    await update.effective_message.reply_text(
        "\n\n".join(blocks) if blocks else "no arcade scores yet fam 🕹",
        parse_mode=ParseMode.HTML)


async def cmd_setgroup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin, run once in the group: teaches Homie which chat is home."""
    if not await admin_ok(update, ctx):
        return
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.effective_message.reply_text("run this inside the group fam")
        return
    db.set_main_chat(chat.id)
    await update.effective_message.reply_text(
        f"locked in ✨ this is home now\n<code>{chat.id}</code>\n\n"
        "presale alerts, milestones and the daily post all land here.\n"
        "<i>if this group ever converts to a supergroup its id changes — "
        "just run /setgroup again.</i>",
        parse_mode=ParseMode.HTML)


async def cmd_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin: is the watcher pointed at the right contract?"""
    if not await admin_ok(update, ctx):
        return
    msg = await update.effective_message.reply_text("reading the chain…")
    raised = await presale.raised_bnb()
    totals = db.presale_totals()
    verdict = ("✅ looks right" if raised > 0 or totals["txs"]
               else "⚠️ nothing here — likely the wrong address")
    await msg.edit_text(
        f"<b>presale watcher</b>\n"
        f"watching <code>{config.PRESALE_ADDRESS_DISPLAY}</code>\n"
        f"pool balance: <b>{raised:.4f} BNB</b>\n"
        f"recorded: {totals['txs']} tx from {totals['wallets']} wallets\n"
        f"backend: {config.CHAIN_BACKEND}\n\n{verdict}",
        parse_mode=ParseMode.HTML)


async def cmd_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        f"chat_id: `{update.effective_chat.id}`\nyour id: `{update.effective_user.id}`",
        parse_mode=ParseMode.MARKDOWN,
    )


# --- conversation -----------------------------------------------------------

CURSE_LINES = [
    "keep it clean in here fam",
    "easy on the language fam",
    "we don't do that in here fam",
    "watch the mouth fam, we're better than that",
]


def founder_chat_id():
    """Where to send leads. Set automatically the first time you DM Homie."""
    stored = db.kv_get("founder_dm")
    if stored:
        return int(stored)
    return next(iter(config.ADMIN_IDS), None)


async def is_chat_admin(ctx, chat_id, user_id):
    return user_id in await admins.chat_admin_ids(ctx, chat_id)


NO_PERMS_COOLDOWN = 3600


async def warn_no_permission(ctx, chat_id, what):
    """Tell Fred when Homie is being asked to moderate and cannot.

    A failed delete used to log a line nobody reads and return as though the
    message were fine. The scam stayed up, the member was never warned, and
    the one person who could fix the permission had no idea. If Homie can't
    do his job he has to say so out loud.
    """
    key = f"noperm:{chat_id}"
    now = time.time()
    if now - ctx.bot_data.get(key, 0) < NO_PERMS_COOLDOWN:
        return
    ctx.bot_data[key] = now
    log.error("missing permission in %s: %s", chat_id, what)
    await notify_founder(
        ctx,
        f"⚠️ <b>I can't moderate {chat_id}</b>\n\n"
        f"Tried to {what} and Telegram refused. I need <b>Delete messages</b> "
        f"and <b>Ban users</b> in this group's admin settings — without them "
        f"the shield can spot a scam but can't remove it.",
    )


async def notify_founder(ctx, text):
    target = founder_chat_id()
    if not target:
        log.warning("no founder chat yet — DM Homie once so he can reach you")
        return
    try:
        await ctx.bot.send_message(target, text, parse_mode=ParseMode.HTML,
                                   disable_web_page_preview=True)
    except Exception:
        log.exception("could not reach founder")


def who(user):
    handle = f"@{user.username}" if user.username else f"id {user.id}"
    return f"{display_name(user)} ({handle})"


async def run_guards(update, ctx) -> bool:
    """Shield + profanity + marketer checks. True if the message was removed."""
    msg = update.effective_message
    user = update.effective_user
    chat_id = update.effective_chat.id
    text = body_of(msg)

    if is_admin(update) or await is_chat_admin(ctx, chat_id, user.id):
        return False

    # --- scam shield: foreign addresses and unapproved links ---
    if config.SHIELD_ENABLED:
        fake_ca = shield.foreign_addresses(text)
        links = shield.bad_links(msg, ctx.bot.username)
        if fake_ca or links:
            try:
                await msg.delete()
            except Exception:
                # The scam is still sitting in the chat. Say so in the chat,
                # because a warning members can see is better than nothing,
                # and get Fred's attention about the missing permission.
                await warn_no_permission(ctx, chat_id, "delete a scam message")
                await ctx.bot.send_message(
                    chat_id,
                    f"⚠️ do NOT use the address or link {display_name(user)} "
                    "just posted — it isn't ours and I couldn't remove it. "
                    "only trust /ca",
                )
                await notify_founder(
                    ctx,
                    f"🛡 <b>COULD NOT REMOVE</b> a scam message from "
                    f"{who(user)} — it is still live in the group\n\n"
                    f"{text[:900]}",
                )
                return True
            what = "an address that isn't ours" if fake_ca else "an outside link"
            await ctx.bot.send_message(
                chat_id,
                f"removed a message from {display_name(user)} with {what}. "
                "only trust /ca for addresses fam",
            )
            await notify_founder(
                ctx,
                f"🛡 <b>shield removed</b> a message from {who(user)}\n\n"
                f"{text[:900]}",
            )
            return True

        if shield.mentions_dm(text, chat_id):
            await ctx.bot.send_message(
                chat_id, shield.SCAM_WARNING, parse_mode=ParseMode.HTML,
            )
            # don't return — let the message stand, it's a real person asking

    # --- cursing ---
    if config.PROFANITY_FILTER and guard.has_profanity(text):
        try:
            await msg.delete()
        except Exception:
            await warn_no_permission(ctx, chat_id, "delete a message")
            return False

        strikes = db.add_strike(user.id, chat_id,
                               config.STRIKE_DECAY_HOURS * 3600)
        if strikes >= config.PROFANITY_STRIKES:
            until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
                minutes=config.MUTE_MINUTES)
            try:
                await ctx.bot.restrict_chat_member(
                    chat_id, user.id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=until,
                )
                await ctx.bot.send_message(
                    chat_id,
                    f"{display_name(user)} is on mute for "
                    f"{config.MUTE_MINUTES} min. strike "
                    f"{config.PROFANITY_STRIKES}",
                )
            except Exception:
                await warn_no_permission(ctx, chat_id, "mute a member")
        else:
            await ctx.bot.send_message(
                chat_id, f"{display_name(user)} — {random.choice(CURSE_LINES)}"
            )
        return True

    # --- marketer pitch ---
    if config.MARKETER_REROUTE and guard.is_marketer_pitch(text):
        try:
            await msg.delete()
        except Exception:
            await warn_no_permission(ctx, chat_id, "delete a pitch")
        db.flag_pitcher(user.id)
        db.add_lead(user.id, user.username, display_name(user), "group", text)
        await ctx.bot.send_message(
            chat_id,
            f'{display_name(user)} — Fred handles all promo and partnership '
            f'stuff himself. '
            f'<a href="https://t.me/{ctx.bot.username}?start=pitch">shoot me a DM</a> '
            f"and I'll put it straight in front of him 👋",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        await notify_founder(
            ctx,
            f"📣 <b>pitch in the group</b> from {who(user)} — rerouted to DM\n\n"
            f"{text[:900]}",
        )
        return True

    return False


def ai_allowed(ctx, chat_id, user_id) -> bool:
    """Per-person and per-chat ceiling on AI replies.

    Nothing used to stand between one bored member and the whole Anthropic
    bill. A floor between a person's replies costs a real conversation
    nothing — nobody types two questions in the same breath — and the hourly
    chat cap is there for the day a raid decides to make Homie talk.
    """
    now = time.time()
    if config.AI_USER_COOLDOWN_SEC:
        key = f"ai_user:{user_id}"
        if now - ctx.bot_data.get(key, 0) < config.AI_USER_COOLDOWN_SEC:
            return False
    if config.AI_CHAT_HOURLY_CAP:
        hour = int(now // 3600)
        key = f"ai_chat:{chat_id}:{hour}"
        used = ctx.bot_data.get(key, 0)
        if used >= config.AI_CHAT_HOURLY_CAP:
            log.warning("AI hourly cap reached in %s", chat_id)
            return False
        ctx.bot_data[key] = used + 1
    if config.AI_USER_COOLDOWN_SEC:
        ctx.bot_data[f"ai_user:{user_id}"] = now
    return True


async def on_private(update, ctx):
    """Anything sent to Homie one-to-one."""
    msg = update.effective_message
    user = update.effective_user
    chat_id = update.effective_chat.id
    text = body_of(msg)

    if await admin_ok(update, ctx):
        db.kv_set("founder_dm", chat_id)  # so Homie knows where to send leads
        db.log_message(chat_id, "user", display_name(user), text)
        answer = await persona.respond_to(chat_id, ctx.bot.first_name,
                                          display_name(user))
        if answer:
            db.log_message(chat_id, "assistant", ctx.bot.first_name, answer)
            await msg.reply_text(answer)
        return

    pitching = (
        db.is_pitcher(user.id)
        or ctx.user_data.get("pitch_mode")
        or guard.is_marketer_pitch(text)
    )

    if pitching:
        db.add_lead(user.id, user.username, display_name(user), "dm", text)
        await notify_founder(
            ctx,
            f"📬 <b>new pitch</b> from {who(user)}\n\n{text[:2000]}",
        )
        await msg.reply_text(
            "got it — passed straight to Fred. he reads every one of these "
            "himself so give him a day or two 🔥"
        )
        return

    db.log_message(chat_id, "user", display_name(user), text)
    if not ai_allowed(ctx, chat_id, user.id):
        return
    answer = await persona.respond_to(chat_id, ctx.bot.first_name,
                                      display_name(user))
    if answer:
        db.log_message(chat_id, "assistant", ctx.bot.first_name, answer)
        await msg.reply_text(answer)


async def on_group_pre(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """The shield, running before anything else can claim the message.

    This used to be a call inside on_message, which meant the guards only saw
    what on_message saw. Anything matched by an earlier handler skipped them
    entirely — a photo captioned "/submit" went to the art contest handler
    with its caption unexamined, so a scam link in that caption was never
    checked. A moderation pass has to be the FIRST thing that looks at a
    message, not one of several things competing for it.
    """
    msg = update.effective_message
    if not msg or not update.effective_user or not body_of(msg):
        return
    try:
        if await run_guards(update, ctx):
            raise ApplicationHandlerStop
    except ApplicationHandlerStop:
        raise
    except Exception:
        # A crash in here must never swallow the message silently or take the
        # bot down with it.
        log.exception("guard pass failed")


async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not update.effective_user:
        return
    text = body_of(msg)
    if not text:
        return

    if update.effective_chat.type == "private":
        await on_private(update, ctx)
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    author = display_name(user)

    db.touch_member(user.id, chat_id, user.username, user.first_name)

    # The guards already ran, in handler group -1, before anything else saw
    # this message. See on_group_pre.

    # An edited message has already been through the guards and the Lumens
    # counter once. Re-running the rest would double-log it and let somebody
    # farm points by editing the same line over and over.
    if update.edited_message:
        return

    db.log_message(chat_id, "user", author, text)

    # games + Lumens. a winning guess ends the turn here.
    if config.GAMES_ENABLED or config.POINTS_ENABLED:
        try:
            if await community.on_group_message(update, ctx):
                return
        except Exception:
            log.exception("community layer failed")

    mentioned = addressed(ctx, text)
    replied_to_bot = bool(
        msg.reply_to_message
        and msg.reply_to_message.from_user
        and msg.reply_to_message.from_user.id == ctx.bot.id
    )

    speak = mentioned or replied_to_bot
    if not speak:
        last = ctx.bot_data.get(f"ambient:{chat_id}", 0)
        fresh = (msg.date.timestamp() - last) > config.AMBIENT_COOLDOWN_SEC
        if fresh and random.random() < config.AMBIENT_REPLY_CHANCE:
            speak = True
            ctx.bot_data[f"ambient:{chat_id}"] = msg.date.timestamp()

    if not speak or not ai_allowed(ctx, chat_id, user.id):
        return

    await ctx.bot.send_chat_action(chat_id, ChatAction.TYPING)
    answer = await persona.respond_to(chat_id, ctx.bot.first_name, author)
    if answer:
        db.log_message(chat_id, "assistant", ctx.bot.first_name, answer)
        await msg.reply_text(answer)


def is_admin_user(user) -> bool:
    """Used on join, where an impersonation ban hangs on the answer.

    A handle claim is enough to be SPARED here but never enough to be
    obeyed: the worst a false positive does is let a real admin through the
    impersonation check, and the alternative — banning Fred because he is
    not pinned yet — is much worse.
    """
    return admins.is_admin(user) or admins.claims_admin(user)


async def send_welcome(ctx, chat_id, user):
    author = display_name(user)
    db.log_message(chat_id, "user", "system", f"{author} joined the group")
    text = await persona.welcome(chat_id, ctx.bot.first_name, author)
    if text:
        db.log_message(chat_id, "assistant", ctx.bot.first_name, text)
        await ctx.bot.send_message(chat_id, text)
    await stickers.send(ctx.bot, chat_id, "welcome")


async def on_join(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    for user in update.effective_message.new_chat_members:
        if user.is_bot:
            continue
        admin = is_admin_user(user)

        # 1. impersonators never get in the door
        reason = None if admin or not config.SHIELD_ENABLED \
            else shield.impersonation_reason(user)
        if reason:
            try:
                await ctx.bot.ban_chat_member(chat_id, user.id)
                await ctx.bot.send_message(
                    chat_id,
                    "bounced an impersonator at the door 🛡 "
                    "reminder fam: the team never DMs first",
                )
                # The ban is permanent, so the message that reports it has to
                # carry the way to undo it. The filter is a heuristic on
                # display names and it will be wrong sometimes.
                await notify_founder(
                    ctx,
                    f"🛡 <b>banned on join</b>: {who(user)} — {reason}\n\n"
                    f"If that was a real member: "
                    f"<code>/unban {user.id}</code>",
                )
            except Exception:
                await warn_no_permission(ctx, chat_id, "ban an impersonator")
                await notify_founder(
                    ctx,
                    f"🛡 <b>could not ban</b> a suspected impersonator — "
                    f"{who(user)} ({reason}) is still in the group",
                )
            continue

        db.touch_member(user.id, chat_id, user.username, user.first_name,
                        counts=False)

        # 2. captcha, then welcome once they pass
        if not config.CAPTCHA_ENABLED or admin:
            await send_welcome(ctx, chat_id, user)
            continue
        try:
            await ctx.bot.restrict_chat_member(
                chat_id, user.id,
                permissions=ChatPermissions(can_send_messages=False),
            )
        except Exception:
            log.warning("captcha: could not restrict %s, welcoming anyway", user.id)
            await send_welcome(ctx, chat_id, user)
            continue

        minutes = max(1, config.CAPTCHA_TIMEOUT_SEC // 60)
        button = InlineKeyboardMarkup([[InlineKeyboardButton(
            "i'm a Lightworker ✨", callback_data=f"cap:{user.id}",
        )]])
        prompt = await ctx.bot.send_message(
            chat_id,
            f"yo {display_name(user)} 👋 tap the button within {minutes} min "
            "so I know you're not a bot",
            reply_markup=button,
        )
        arm_captcha(ctx, chat_id, user.id, prompt.message_id,
                    config.CAPTCHA_TIMEOUT_SEC)


# --- captcha state ----------------------------------------------------------
#
# A pending captcha is a muted member and a job to un-mute or remove them.
# The job queue lives in memory, so a restart — a deploy, a crash, the kernel
# update that needed a reboot — used to drop it and leave that person muted in
# the group with no button that worked and nobody aware of it. Writing the
# pending set down means a restart can pick it back up.

CAPTCHA_KEY = "captcha:"


def arm_captcha(ctx, chat_id, user_id, msg_id, timeout):
    db.kv_set(f"{CAPTCHA_KEY}{chat_id}:{user_id}", msg_id)
    ctx.job_queue.run_once(
        job_captcha_timeout, timeout,
        data={"chat_id": chat_id, "user_id": user_id, "msg_id": msg_id},
        name=f"cap:{chat_id}:{user_id}",
    )


def disarm_captcha(ctx, chat_id, user_id):
    db.kv_delete(f"{CAPTCHA_KEY}{chat_id}:{user_id}")
    for job in ctx.job_queue.get_jobs_by_name(f"cap:{chat_id}:{user_id}"):
        job.schedule_removal()


async def restore_captchas(app):
    """Re-arm any captcha that was pending when we stopped.

    Everyone pending gets a fresh full window rather than being judged on a
    deadline that expired while Homie was down. The button in the chat still
    works, so a real person just taps it; a bot that was never going to tap
    is removed one window later than it would have been. Erring toward the
    real member is the right way round.
    """
    pending = db.kv_prefix(CAPTCHA_KEY)
    if not pending:
        return
    ctx = ContextTypes.DEFAULT_TYPE(application=app)
    armed = 0
    for key, msg_id in pending.items():
        try:
            chat_id, user_id = key[len(CAPTCHA_KEY):].split(":")
            arm_captcha(ctx, int(chat_id), int(user_id), int(msg_id),
                        config.CAPTCHA_TIMEOUT_SEC)
            armed += 1
        except (ValueError, TypeError):
            db.kv_delete(key)
    log.info("re-armed %s pending captcha(s) after restart", armed)


async def on_captcha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    target = int(q.data.split(":", 1)[1])
    if q.from_user.id != target:
        await q.answer("not your button fam 😄")
        return

    chat_id = q.message.chat.id
    chat = await ctx.bot.get_chat(chat_id)
    perms = chat.permissions or ChatPermissions(can_send_messages=True)
    try:
        await ctx.bot.restrict_chat_member(chat_id, target, permissions=perms)
    except Exception:
        log.exception("captcha: could not lift restriction for %s", target)

    disarm_captcha(ctx, chat_id, target)
    await q.answer("you're in ✨")
    try:
        await q.message.delete()
    except Exception:
        pass
    await send_welcome(ctx, chat_id, q.from_user)


async def job_captcha_timeout(ctx: ContextTypes.DEFAULT_TYPE):
    d = ctx.job.data
    db.kv_delete(f"{CAPTCHA_KEY}{d['chat_id']}:{d['user_id']}")
    try:
        await moderation.kick(ctx.bot, d["chat_id"], d["user_id"])
        db.mark_removed(d["user_id"], d["chat_id"])
    except Exception:
        log.warning("captcha: could not remove %s", d["user_id"])
    try:
        await ctx.bot.delete_message(d["chat_id"], d["msg_id"])
    except Exception:
        pass


async def on_leave(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_message.left_chat_member
    if user:
        db.mark_removed(user.id, update.effective_chat.id)


# --- scheduled jobs ---------------------------------------------------------

MILESTONES = [
    # (key, threshold in BNB, fixed message). Fixed text — no AI near numbers.
    ("soft", lambda: config.SOFT_CAP_BNB,
     "🎉 SOFT CAP HIT fam. {soft:g} BNB raised — the presale is officially a go. "
     "every Big Giver from here pushes us toward {hard:g}"),
    ("p25", lambda: config.HARD_CAP_BNB * 0.25,
     "quarter of the way to hard cap fam 🔥 {raised:.2f} of {hard:g} BNB"),
    ("p50", lambda: config.HARD_CAP_BNB * 0.50,
     "HALFWAY. {raised:.2f} of {hard:g} BNB. fam this is really happening"),
    ("p75", lambda: config.HARD_CAP_BNB * 0.75,
     "75% fam. {raised:.2f} of {hard:g} BNB. the light is getting bright in here ☀️"),
    ("hard", lambda: config.HARD_CAP_BNB,
     "HARD CAP. {hard:g} BNB. holy smokes fam, you absolute legends. "
     "thank you to every single Big Giver who chose to SpreadLight ✨"),
]

COUNTDOWNS = [
    # (key, seconds before end, fixed message)
    ("7d", 7 * 86400, "one week left in the presale fam ⏳ {progress}"),
    ("3d", 3 * 86400, "3 days left fam ⏳ {progress}"),
    ("1d", 86400, "24 hours left in the presale ⏳ {progress}"),
    ("6h", 6 * 3600, "6 hours left fam. last call is coming ⏳ {progress}"),
    ("1h", 3600, "ONE HOUR left in the presale fam ⏳ {progress}"),
]


async def post_milestones(ctx, raised, silent=False):
    """Fire any milestone crossed since last check. silent=True just records."""
    for key, threshold, text in MILESTONES:
        if db.kv_get(f"milestone:{key}") or raised < threshold():
            continue
        db.kv_set(f"milestone:{key}", "1")
        if silent:
            continue
        await ctx.bot.send_message(
            db.main_chat(config.MAIN_CHAT_ID),
            text.format(raised=raised, soft=config.SOFT_CAP_BNB,
                        hard=config.HARD_CAP_BNB),
        )
        await stickers.send(ctx.bot, db.main_chat(config.MAIN_CHAT_ID),
                            "milestone")


async def job_presale(ctx: ContextTypes.DEFAULT_TYPE):
    if not db.main_chat(config.MAIN_CHAT_ID):
        return          # waiting on /setgroup
    fresh = await presale.fetch_new_contributions()
    raised = await presale.raised_bnb()

    # First run ever: the chain already holds every contribution made before
    # Homie existed. Record them so totals and new-vs-returning are right, but
    # do NOT announce them — otherwise his opening act in a brand new group is
    # a burst of stale "new Lightworker!" cards for last week's money.
    # Instead he reports privately to the founder, which doubles as proof the
    # watcher is pointed at the right address.
    first_run = not db.kv_get("contributions_init")
    if first_run:
        db.kv_set("contributions_init", "1")
        await post_milestones(ctx, raised, silent=True)
        db.kv_set("milestones_init", "1")
        count = len(fresh)
        total = sum(tx["bnb"] for tx in fresh)
        if count:
            await notify_founder(
                ctx,
                f"✅ <b>presale watcher is live</b>\n"
                f"backfilled {count} past contribution(s), {total:.3f} BNB, "
                f"silently — the group won't see these.\n"
                f"pool balance reads {raised:.3f} BNB.\n\n"
                f"anything new from here gets announced.",
            )
        else:
            await notify_founder(
                ctx,
                "⚠️ <b>presale watcher found nothing</b>\n"
                f"no contributions at <code>{config.PRESALE_ADDRESS_DISPLAY}</code> "
                f"and its balance reads {raised:.3f} BNB.\n\n"
                "if money has gone in, PRESALE_ADDRESS is the wrong contract — "
                "swap it with TOKEN_ADDRESS in .env and restart.",
            )
        return

    # belt and braces: the milestone flag on its own, for older installs
    if not db.kv_get("milestones_init"):
        await post_milestones(ctx, raised, silent=True)
        db.kv_set("milestones_init", "1")

    for tx in fresh:
        if tx["bnb"] < config.MIN_ANNOUNCE_BNB:
            continue
        totals = db.presale_totals()
        totals["total_bnb"] = raised
        big = tx["bnb"] >= config.BIG_GIVER_BNB
        if tx["new_wallet"]:
            tag = "💫 BIG GIVER just stepped up" if big else "🌟 new Lightworker"
        else:
            tag = "🔁 Big Giver adding more" if big else "🔁 Lightworker adding more"
        card = (
            f"<b>{tag}</b>\n"
            f"<b>{tx['bnb']:.3f} BNB</b> from "
            f'<a href="https://bscscan.com/address/{tx["from"]}">'
            f"{presale.short_wallet(tx['from'])}</a>\n\n"
            f"{presale.progress_block(raised)}\n"
            f'<a href="https://bscscan.com/tx/{tx["hash"]}">view tx</a>'
        )
        await ctx.bot.send_message(
            db.main_chat(config.MAIN_CHAT_ID), card,
            parse_mode=ParseMode.HTML, disable_web_page_preview=True,
        )
        line = await persona.celebrate(
            db.main_chat(config.MAIN_CHAT_ID), ctx.bot.first_name,
            tx["bnb"], tx["new_wallet"], totals,
        )
        if line:
            db.log_message(db.main_chat(config.MAIN_CHAT_ID), "assistant", ctx.bot.first_name, line)
            await ctx.bot.send_message(db.main_chat(config.MAIN_CHAT_ID), line)
        if big:
            await stickers.send(ctx.bot, db.main_chat(config.MAIN_CHAT_ID),
                                "biggiver")

    await post_milestones(ctx, raised)


async def job_countdown(ctx: ContextTypes.DEFAULT_TYPE):
    if not db.main_chat(config.MAIN_CHAT_ID):
        return
    end = presale.end_time()
    if not end:
        return
    remaining = (end - dt.datetime.now(dt.timezone.utc)).total_seconds()
    first_run = not db.kv_get("countdown_init")
    db.kv_set("countdown_init", "1")

    for key, secs, text in COUNTDOWNS:
        if db.kv_get(f"countdown:{key}") or remaining > secs:
            continue
        db.kv_set(f"countdown:{key}", "1")
        # a mark that's already long past on first boot gets recorded, not posted
        if first_run and remaining < secs - 3600:
            continue
        if remaining <= 0:
            continue
        raised = await presale.raised_bnb()
        bar, pct = presale.progress_bar(raised, config.HARD_CAP_BNB)
        await ctx.bot.send_message(
            db.main_chat(config.MAIN_CHAT_ID),
            text.format(progress=f"\n{bar} {pct}% · {raised:.2f}/"
                                 f"{config.HARD_CAP_BNB:g} BNB"),
        )


async def job_sweep(ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = db.main_chat(config.MAIN_CHAT_ID)
    if not chat_id:
        return
    checked, removed = await moderation.sweep(ctx.bot, chat_id)
    log.info("sweep: checked %s, removed %s", checked, removed)
    # This runs unattended every 12 hours and removes people. Removing people
    # silently is not something a bot should do to somebody else's group.
    if removed:
        await notify_founder(
            ctx,
            f"🧹 <b>sweep</b>: removed {removed} deleted account(s) "
            f"from {chat_id} (checked {checked})",
        )


async def job_icebreaker(ctx: ContextTypes.DEFAULT_TYPE):
    if not db.main_chat(config.MAIN_CHAT_ID):
        return
    text = await persona.icebreaker(db.main_chat(config.MAIN_CHAT_ID), ctx.bot.first_name)
    if text:
        db.log_message(db.main_chat(config.MAIN_CHAT_ID), "assistant", ctx.bot.first_name, text)
        await ctx.bot.send_message(db.main_chat(config.MAIN_CHAT_ID), text)
        await stickers.send(ctx.bot, db.main_chat(config.MAIN_CHAT_ID), "gm")


# --- wiring -----------------------------------------------------------------

async def on_inline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Answer @SpreadLightBot in any chat with the three games.

    Registering a game in BotFather REQUIRES the bot to be in inline mode,
    so inline is on whether or not we use it. An inline-mode bot with no
    handler shows a spinner and then nothing, which looks broken — so it
    answers with the games, which is the one thing inline is good for here:
    sharing a cabinet into a chat the bot isn't even in.
    """
    if not config.GAMES_ENABLED:
        return
    results = [
        InlineQueryResultGame(id=short, game_short_name=short)
        for short in arcade_server.GAMES
    ]
    try:
        await update.inline_query.answer(results, cache_time=60)
    except Exception:
        log.exception("inline answer failed")


async def on_arcade_score(claim, score):
    """Called by the arcade web server when a run finishes."""
    app = _APP
    bot = app.bot
    user_id, chat_id, game = claim["user_id"], claim["chat_id"], claim["game"]

    try:
        member = await bot.get_chat_member(chat_id, user_id)
        username = member.user.username
        name = member.user.first_name or username or "a Lightworker"
    except Exception:
        username, name = None, "a Lightworker"

    best, _ = db.record_score(user_id, chat_id, game, username, score)

    # Telegram's own scoreboard, written onto the game card itself. This has
    # to target the chat the card is IN (the player's DM), not the chat the
    # score is filed AGAINST (the group) — pointing it at the group means
    # Telegram can't find the message and no leaderboard ever appears.
    #
    # The API takes chat_id+message_id OR inline_message_id, never both.
    try:
        if claim.get("inline_id"):
            await bot.set_game_score(
                user_id=user_id, score=score,
                inline_message_id=claim["inline_id"],
                disable_edit_message=False,
            )
        elif claim.get("card_chat") and claim.get("message_id"):
            await bot.set_game_score(
                user_id=user_id, score=score,
                chat_id=claim["card_chat"], message_id=claim["message_id"],
                disable_edit_message=False,
            )
        else:
            log.warning("no game message to score against: %s", claim)
    except Exception as e:
        # A lower score than the one already stored is refused by design, so
        # that one is expected. Anything else means the board is broken and
        # should be visible in the log rather than swallowed at debug level.
        msg = str(e).lower()
        if "not modified" in msg or "not_modified" in msg:
            log.debug("set_game_score: score not a new best")
        else:
            log.warning("set_game_score failed (%s): %s", claim, e)

    if not best or not config.POINTS_ENABLED:
        return

    # one arcade award per day, however many times they play
    today = time.strftime("%Y-%m-%d", time.gmtime())
    key = f"arcade_paid:{user_id}:{today}"
    if db.kv_get(key):
        return
    db.kv_set(key, "1")
    points.award(user_id, chat_id, config.ARCADE_DAILY_LUMENS,
                 f"arcade:{game}", username)

    title = arcade_server.GAMES[game][1]
    top = db.top_scores(chat_id, game, 1)
    crown = " 👑 new #1 on the board" if top and top[0]["user_id"] == user_id else ""
    try:
        await bot.send_message(
            db.main_chat(config.MAIN_CHAT_ID),
            f"🕹 {name} put up <b>{score}</b> on {title}{crown}\n"
            f"+{config.ARCADE_DAILY_LUMENS} ✨",
            parse_mode=ParseMode.HTML)
    except Exception:
        pass


_APP = None


async def _post_init(app):
    global _APP
    _APP = app
    await restore_captchas(app)
    if config.ARCADE_ENABLED:
        app.bot_data["arcade_runner"] = await arcade_server.start_server(
            on_arcade_score)


async def _post_shutdown(app):
    runner = app.bot_data.get("arcade_runner") if app.bot_data else None
    if runner:
        await runner.cleanup()


def main():
    missing = config.validate()
    if missing:
        print("Missing config: " + ", ".join(missing))
        sys.exit(1)

    db.init()
    app = (Application.builder()
           .token(config.BOT_TOKEN)
           .post_init(_post_init)
           .post_shutdown(_post_shutdown)
           .build())

    # Group -1 runs before every other handler, so the shield sees every
    # group message — commands and photo captions included — no matter which
    # handler would otherwise claim it.
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.CAPTION) & filters.ChatType.GROUPS,
        on_group_pre), group=-1)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("presale", cmd_presale))
    app.add_handler(CommandHandler("ca", cmd_ca))
    app.add_handler(CommandHandler("howtobuy", cmd_howtobuy))
    app.add_handler(CommandHandler("buy", cmd_howtobuy))       # people type this
    app.add_handler(CommandHandler("wallet", cmd_howtobuy))    # and this
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("ask", cmd_ask))
    app.add_handler(CommandHandler("sweep", cmd_sweep))
    app.add_handler(CommandHandler("say", cmd_say))
    app.add_handler(CommandHandler("leads", cmd_leads))
    app.add_handler(CommandHandler("reload", cmd_reload))
    app.add_handler(CommandHandler("forgive", cmd_forgive))

    # manual moderation
    app.add_handler(CommandHandler("mod", cmd_mod))
    app.add_handler(CommandHandler("health", cmd_health))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("mute", cmd_mute))
    app.add_handler(CommandHandler("unmute", cmd_unmute))
    app.add_handler(CommandHandler("warn", cmd_warn))
    app.add_handler(CommandHandler("strikes", cmd_strikes))
    app.add_handler(CommandHandler(["del", "delete"], cmd_del))

    # stickers made from logos
    app.add_handler(CommandHandler("sticker", cmd_sticker))
    app.add_handler(CommandHandler("emoji", cmd_emoji))
    app.add_handler(CommandHandler(["stickerpack", "packs"], cmd_stickerpack))
    app.add_handler(CommandHandler("stickeruse", cmd_stickeruse))
    # a logo sent to Homie with "/sticker" as its caption
    app.add_handler(MessageHandler(
        filters.PHOTO & filters.CaptionRegex(r"(?i)^/sticker"), cmd_sticker))
    app.add_handler(MessageHandler(
        filters.PHOTO & filters.CaptionRegex(r"(?i)^/emoji"), cmd_emoji))

    app.add_handler(CommandHandler("play", cmd_play))
    app.add_handler(CommandHandler("scores", cmd_scores))
    app.add_handler(CommandHandler("setgroup", cmd_setgroup))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("id", cmd_id))

    if config.GAMES_ENABLED or config.POINTS_ENABLED:
        community.register(app)
    app.add_handler(InlineQueryHandler(on_inline))
    app.add_handler(CallbackQueryHandler(on_arcade_pick, pattern=r"^arc:"))
    app.add_handler(CallbackQueryHandler(on_game_launch, game_pattern=r".*"))

    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_join))
    app.add_handler(CallbackQueryHandler(on_captcha, pattern=r"^cap:"))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, on_leave))
    # CAPTION as well as TEXT. A caption is just text that Telegram filed
    # under a different attribute, and a fake contract address under a photo
    # used to bypass every guard because this filter never looked at it.
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.CAPTION) & ~filters.COMMAND, on_message))

    jq = app.job_queue
    if config.PRESALE_ADDRESS:
        jq.run_repeating(job_presale, interval=config.PRESALE_POLL_SEC, first=10)
        jq.run_repeating(job_countdown, interval=600, first=30)
    else:
        log.warning("PRESALE_ADDRESS not set — contribution alerts are off")

    if config.DELETED_SWEEP_ENABLED:
        jq.run_repeating(
            job_sweep, interval=config.DELETED_SWEEP_HOURS * 3600, first=120
        )

    if 0 <= config.ICEBREAKER_HOUR_UTC <= 23:
        jq.run_daily(
            job_icebreaker,
            time=dt.time(hour=config.ICEBREAKER_HOUR_UTC, tzinfo=dt.timezone.utc),
        )

    log.info("SpreadLight bot starting…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
