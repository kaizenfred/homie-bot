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
    ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
    MessageHandler, filters,
)

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

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("spreadlight")


def is_admin(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    if user.id in config.ADMIN_IDS:
        return True
    return bool(user.username) and user.username.lower() in config.ADMIN_USERNAMES


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
        if is_admin(update):
            db.kv_set("founder_dm", update.effective_chat.id)
        if ctx.args and ctx.args[0] == "pitch":
            ctx.user_data["pitch_mode"] = True
            await update.effective_message.reply_text(
                "aight go ahead — who are you, what do you do, and what are "
                "you proposing? send it in one message and I'll put it in "
                "front of Fred"
            )
            return
    await update.effective_message.reply_text(
        "yo, I'm Homie ✨ I hang out here.\n\n"
        "/howtobuy — never bought crypto? start here\n"
        "/presale — progress and countdown\n"
        "/ca — official contract addresses\n"
        "/stats — community numbers\n"
        "/play — arcade · /rank — your Lumens\n"
        "/ask — ask me anything about the project\n\n"
        "Tag me or reply to me and I'll answer."
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
    await ctx.bot.send_chat_action(chat_id, ChatAction.TYPING)
    answer = await persona.respond_to(chat_id, ctx.bot.first_name, author)
    if answer:
        db.log_message(chat_id, "assistant", ctx.bot.first_name, answer)
        await msg.reply_text(answer)


async def cmd_sweep(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    msg = await update.effective_message.reply_text("Sweeping for deleted accounts…")
    checked, removed = await moderation.sweep(ctx.bot, update.effective_chat.id)
    await msg.edit_text(f"Checked {checked} members. Removed {removed} deleted accounts.")


async def cmd_say(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Broadcast to the main chat: /say your message here"""
    if not is_admin(update):
        return
    text = " ".join(ctx.args)
    if not text:
        await update.effective_message.reply_text("Usage: /say <message>")
        return
    await ctx.bot.send_message(db.main_chat(config.MAIN_CHAT_ID), text)


async def cmd_leads(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
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
    if not is_admin(update):
        return
    guard.reload_lists()
    await update.effective_message.reply_text("word lists reloaded")


async def cmd_forgive(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Reply to someone with /forgive to wipe their strikes and unmute them."""
    if not is_admin(update):
        return
    target = update.effective_message.reply_to_message
    if not target:
        await update.effective_message.reply_text("reply to the person with /forgive")
        return
    chat_id = update.effective_chat.id
    user_id = target.from_user.id
    db.clear_strikes(user_id, chat_id)
    try:
        await ctx.bot.restrict_chat_member(
            chat_id, user_id,
            permissions=ChatPermissions(
                can_send_messages=True, can_send_other_messages=True,
                can_add_web_page_previews=True, can_send_polls=True,
                can_invite_users=True,
            ),
        )
    except Exception:
        pass
    await update.effective_message.reply_text(
        f"{display_name(target.from_user)} is clean, we move on"
    )


async def cmd_play(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Post the arcade menu. Each button sends that game's card."""
    if not config.ARCADE_ENABLED:
        await update.effective_message.reply_text(
            "arcade isn't switched on yet fam. try /scramble or /riddle")
        return
    rows = [[InlineKeyboardButton(title, callback_data=f"arc:{short}")]
            for short, (_, title, _) in arcade_server.GAMES.items()]
    await update.effective_message.reply_text(
        "🕹 <b>the arcade</b>\npick one — high scores go on the group board",
        parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(rows))


async def on_arcade_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Menu button -> send the actual Telegram game card."""
    q = update.callback_query
    short = q.data.split(":", 1)[1]
    await q.answer()
    try:
        await ctx.bot.send_game(q.message.chat.id, short)
    except Exception:
        log.exception("send_game failed for %s", short)
        await ctx.bot.send_message(
            q.message.chat.id,
            f"couldn't open {short} — it may not be registered with BotFather yet")


async def on_game_launch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Telegram's own Play button -> hand back a signed, per-user URL."""
    q = update.callback_query
    short = q.game_short_name
    if short not in arcade_server.GAMES:
        await q.answer("unknown game", show_alert=True)
        return
    chat_id = q.message.chat.id if q.message else db.main_chat(config.MAIN_CHAT_ID)
    url = arcade_server.play_url(
        q.from_user.id, chat_id, short,
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
    if not is_admin(update):
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
    if not is_admin(update):
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
    try:
        member = await ctx.bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


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
    """Profanity + marketer checks. Returns True if the message was removed."""
    msg = update.effective_message
    user = update.effective_user
    chat_id = update.effective_chat.id

    if is_admin(update) or await is_chat_admin(ctx, chat_id, user.id):
        return False

    # --- scam shield: foreign addresses and unapproved links ---
    if config.SHIELD_ENABLED:
        fake_ca = shield.foreign_addresses(msg.text)
        links = shield.bad_links(msg, ctx.bot.username)
        if fake_ca or links:
            try:
                await msg.delete()
            except Exception:
                log.warning("no delete permission in %s", chat_id)
                return False
            what = "an address that isn't ours" if fake_ca else "an outside link"
            await ctx.bot.send_message(
                chat_id,
                f"removed a message from {display_name(user)} with {what}. "
                "only trust /ca for addresses fam",
            )
            await notify_founder(
                ctx,
                f"🛡 <b>shield removed</b> a message from {who(user)}\n\n"
                f"{msg.text[:900]}",
            )
            return True

        if shield.mentions_dm(msg.text, chat_id):
            await ctx.bot.send_message(
                chat_id, shield.SCAM_WARNING, parse_mode=ParseMode.HTML,
            )
            # don't return — let the message stand, it's a real person asking

    # --- cursing ---
    if config.PROFANITY_FILTER and guard.has_profanity(msg.text):
        try:
            await msg.delete()
        except Exception:
            log.warning("no delete permission in %s", chat_id)
            return False

        strikes = db.add_strike(user.id, chat_id)
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
                    f"{config.MUTE_MINUTES} min. third strike",
                )
            except Exception:
                log.warning("could not mute %s", user.id)
        else:
            await ctx.bot.send_message(
                chat_id, f"{display_name(user)} — {random.choice(CURSE_LINES)}"
            )
        return True

    # --- marketer pitch ---
    if config.MARKETER_REROUTE and guard.is_marketer_pitch(msg.text):
        try:
            await msg.delete()
        except Exception:
            pass
        db.flag_pitcher(user.id)
        db.add_lead(user.id, user.username, display_name(user), "group", msg.text)
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
            f"{msg.text[:900]}",
        )
        return True

    return False


async def on_private(update, ctx):
    """Anything sent to Homie one-to-one."""
    msg = update.effective_message
    user = update.effective_user
    chat_id = update.effective_chat.id

    if is_admin(update):
        db.kv_set("founder_dm", chat_id)  # so Homie knows where to send leads
        db.log_message(chat_id, "user", display_name(user), msg.text)
        answer = await persona.respond_to(chat_id, ctx.bot.first_name,
                                          display_name(user))
        if answer:
            db.log_message(chat_id, "assistant", ctx.bot.first_name, answer)
            await msg.reply_text(answer)
        return

    pitching = (
        db.is_pitcher(user.id)
        or ctx.user_data.get("pitch_mode")
        or guard.is_marketer_pitch(msg.text)
    )

    if pitching:
        db.add_lead(user.id, user.username, display_name(user), "dm", msg.text)
        await notify_founder(
            ctx,
            f"📬 <b>new pitch</b> from {who(user)}\n\n{msg.text[:2000]}",
        )
        await msg.reply_text(
            "got it — passed straight to Fred. he reads every one of these "
            "himself so give him a day or two 🔥"
        )
        return

    db.log_message(chat_id, "user", display_name(user), msg.text)
    answer = await persona.respond_to(chat_id, ctx.bot.first_name,
                                      display_name(user))
    if answer:
        db.log_message(chat_id, "assistant", ctx.bot.first_name, answer)
        await msg.reply_text(answer)


async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.text or not update.effective_user:
        return

    if update.effective_chat.type == "private":
        await on_private(update, ctx)
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    author = display_name(user)

    db.touch_member(user.id, chat_id, user.username, user.first_name)

    if await run_guards(update, ctx):
        return

    db.log_message(chat_id, "user", author, msg.text)

    # games + Lumens. a winning guess ends the turn here.
    if config.GAMES_ENABLED or config.POINTS_ENABLED:
        try:
            if await community.on_group_message(update, ctx):
                return
        except Exception:
            log.exception("community layer failed")

    mentioned = addressed(ctx, msg.text)
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

    if not speak:
        return

    await ctx.bot.send_chat_action(chat_id, ChatAction.TYPING)
    answer = await persona.respond_to(chat_id, ctx.bot.first_name, author)
    if answer:
        db.log_message(chat_id, "assistant", ctx.bot.first_name, answer)
        await msg.reply_text(answer)


def is_admin_user(user) -> bool:
    if user.id in config.ADMIN_IDS:
        return True
    return bool(user.username) and user.username.lower() in config.ADMIN_USERNAMES


async def send_welcome(ctx, chat_id, user):
    author = display_name(user)
    db.log_message(chat_id, "user", "system", f"{author} joined the group")
    text = await persona.welcome(chat_id, ctx.bot.first_name, author)
    if text:
        db.log_message(chat_id, "assistant", ctx.bot.first_name, text)
        await ctx.bot.send_message(chat_id, text)


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
                await notify_founder(
                    ctx, f"🛡 <b>banned on join</b>: {who(user)} — {reason}",
                )
            except Exception:
                log.exception("could not ban impersonator %s", user.id)
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
        ctx.job_queue.run_once(
            job_captcha_timeout, config.CAPTCHA_TIMEOUT_SEC,
            data={"chat_id": chat_id, "user_id": user.id,
                  "msg_id": prompt.message_id},
            name=f"cap:{chat_id}:{user.id}",
        )


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

    for job in ctx.job_queue.get_jobs_by_name(f"cap:{chat_id}:{target}"):
        job.schedule_removal()
    await q.answer("you're in ✨")
    try:
        await q.message.delete()
    except Exception:
        pass
    await send_welcome(ctx, chat_id, q.from_user)


async def job_captcha_timeout(ctx: ContextTypes.DEFAULT_TYPE):
    d = ctx.job.data
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
    if not db.main_chat(config.MAIN_CHAT_ID):
        return
    checked, removed = await moderation.sweep(ctx.bot, db.main_chat(config.MAIN_CHAT_ID))
    log.info("sweep: checked %s, removed %s", checked, removed)


async def job_icebreaker(ctx: ContextTypes.DEFAULT_TYPE):
    if not db.main_chat(config.MAIN_CHAT_ID):
        return
    text = await persona.icebreaker(db.main_chat(config.MAIN_CHAT_ID), ctx.bot.first_name)
    if text:
        db.log_message(db.main_chat(config.MAIN_CHAT_ID), "assistant", ctx.bot.first_name, text)
        await ctx.bot.send_message(db.main_chat(config.MAIN_CHAT_ID), text)


# --- wiring -----------------------------------------------------------------

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

    # Telegram's own scoreboard on the game message
    try:
        await bot.set_game_score(
            user_id=user_id, score=score, chat_id=chat_id,
            message_id=claim["message_id"],
            inline_message_id=claim["inline_id"],
            disable_edit_message=False,
        )
    except Exception as e:
        log.debug("set_game_score skipped: %s", e)

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
    app.add_handler(CommandHandler("play", cmd_play))
    app.add_handler(CommandHandler("scores", cmd_scores))
    app.add_handler(CommandHandler("setgroup", cmd_setgroup))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("id", cmd_id))

    if config.GAMES_ENABLED or config.POINTS_ENABLED:
        community.register(app)
    app.add_handler(CallbackQueryHandler(on_arcade_pick, pattern=r"^arc:"))
    app.add_handler(CallbackQueryHandler(on_game_launch, game_pattern=r".*"))

    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_join))
    app.add_handler(CallbackQueryHandler(on_captcha, pattern=r"^cap:"))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, on_leave))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

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
