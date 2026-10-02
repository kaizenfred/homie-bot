"""Command handlers for the community layer: Lumens, games, art contest.

Kept out of bot.py so both files stay readable. bot.py registers these with
register(app) and calls on_group_message() from its own message handler.
"""

import logging
import random
import time

from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters,
)

import admins
import art
import config
import db
import games
import points

log = logging.getLogger(__name__)


def _name(user):
    return user.first_name or user.username or f"user{user.id}"


async def _is_admin(update, ctx):
    """Same verified check bot.py uses — see admins.py.

    /give mints Lumens and /artend pays out a contest, so this is a real
    privilege and it must not hang on a Telegram handle anyone can take over
    once Fred renames himself.
    """
    return await admins.verify(ctx, update)


def _board_chat(update):
    """All scores live against the main group, even when asked in DM."""
    chat = update.effective_chat
    return chat.id if chat.type in ("group", "supergroup") else db.main_chat(config.MAIN_CHAT_ID)


# --- Lumens -----------------------------------------------------------------

async def cmd_rank(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    target = (msg.reply_to_message.from_user
              if msg.reply_to_message else update.effective_user)
    chat_id = _board_chat(update)

    row = db.get_points(target.id, chat_id)
    lifetime, track = row["lifetime"], row.get("track") or "light"
    (_, rank_name, icon), nxt = points.rank_for(lifetime, track)
    bar, pct = points.progress_to_next(lifetime)
    place = db.points_rank(target.id, chat_id)

    lines = [
        f"<b>{_name(target)}</b>",
        f"{icon} {rank_name} · #{place} in the fam",
        f"✨ {lifetime} Lumens",
        f"{bar} {pct}%",
    ]
    if nxt:
        lines.append(f"{nxt[0] - lifetime} more to {nxt[2]} {nxt[1]}")
    if row["streak"] > 1:
        lines.append(f"🔥 {row['streak']} day streak")

    kb = None
    if target.id == update.effective_user.id:
        alt = points.other_track(track)
        (_, alt_name, alt_icon), _ = points.rank_for(lifetime, alt)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(
            f"wear {alt_icon} {alt_name} instead", callback_data=f"trk:{alt}")]])
    await msg.reply_text("\n".join(lines), parse_mode=ParseMode.HTML,
                         reply_markup=kb)


async def cmd_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Pick which ladder you climb. Same ranks, same thresholds, your call."""
    user = update.effective_user
    chat_id = _board_chat(update)
    row = db.get_points(user.id, chat_id)
    lifetime, track = row["lifetime"], row.get("track") or "light"
    (light_n, light_i), (fest_n, fest_i) = points.both_names(lifetime)

    mark = lambda w: " ✓" if track == w else ""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{light_i} {light_n}{mark('light')}",
                              callback_data="trk:light")],
        [InlineKeyboardButton(f"{fest_i} {fest_n}{mark('festival')}",
                              callback_data="trk:festival")],
    ])
    await update.effective_message.reply_text(
        "<b>pick your title</b>\n"
        "same ranks, same Lumens — just which name you wear.\n\n"
        "🔦 <b>the light track</b> — Spark · Candle · Lantern · Beacon · "
        "Lighthouse · Star · Supernova\n"
        "🎪 <b>the festival track</b> — Glowstick · Strobe · Laser · "
        "Spotlight · Mainstage · Headliner · Legend\n\n"
        "switch any time, costs nothing",
        parse_mode=ParseMode.HTML, reply_markup=kb)


async def on_track_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    track = q.data.split(":", 1)[1]
    if track not in points.TRACKS:
        await q.answer()
        return
    chat_id = _board_chat(update)
    db.set_track(q.from_user.id, chat_id, track)
    lifetime = db.get_points(q.from_user.id, chat_id)["lifetime"]
    (_, name, icon), _ = points.rank_for(lifetime, track)
    await q.answer(f"you're {name} now ✨")
    try:
        alt = points.other_track(track)
        (_, alt_name, alt_icon), _ = points.rank_for(lifetime, alt)
        await q.edit_message_reply_markup(InlineKeyboardMarkup([[
            InlineKeyboardButton(f"wear {alt_icon} {alt_name} instead",
                                 callback_data=f"trk:{alt}")]]))
    except Exception:
        pass


async def cmd_leaderboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = _board_chat(update)
    weekly = (ctx.args and ctx.args[0].lower().startswith("w"))
    since = int(time.time()) - 7 * 86400 if weekly else None
    rows = points.leaderboard(chat_id, 10, since)

    if not rows:
        await update.effective_message.reply_text(
            "nobody's on the board yet. be the first fam ✨")
        return

    medals = ["🥇", "🥈", "🥉"]
    out = ["<b>✨ Lumens — this week</b>" if weekly else "<b>✨ Lumens — all time</b>"]
    for i, r in enumerate(rows):
        mark = medals[i] if i < 3 else f"{i + 1}."
        who = f"@{r['username']}" if r["username"] else f"user{r['user_id']}"
        icon = "" if weekly else points.rank_for(
            r["score"], db.get_track(r["user_id"], chat_id))[0][2]
        out.append(f"{mark} {who} — {r['score']} {icon}".rstrip())
    await update.effective_message.reply_text(
        "\n".join(out), parse_mode=ParseMode.HTML)


async def cmd_checkin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = _board_chat(update)
    earned, streak = points.check_in(user.id, chat_id, user.username)

    if earned is None:
        await update.effective_message.reply_text(
            f"already checked in today fam. {streak} day streak 🔥")
        return
    flame = f" · {streak} day streak 🔥" if streak > 1 else ""
    await update.effective_message.reply_text(
        f"checked in ✨ +{earned} Lumens{flame}")


async def cmd_give(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin: reply to someone with /give 50 reason"""
    if not await _is_admin(update, ctx):
        return
    msg = update.effective_message
    if not msg.reply_to_message or not ctx.args:
        await msg.reply_text("reply to someone with /give <amount> [reason]")
        return
    try:
        amount = int(ctx.args[0])
    except ValueError:
        await msg.reply_text("that's not a number fam")
        return

    target = msg.reply_to_message.from_user
    reason = " ".join(ctx.args[1:]) or "founder award"
    lifetime = points.award(target.id, _board_chat(update), amount,
                            f"manual:{reason}", target.username)
    verb = "handed" if amount >= 0 else "took"
    await msg.reply_text(
        f"{verb} {_name(target)} {abs(amount)} Lumens — {reason}\n"
        f"they're on {lifetime} now")


async def cmd_lumens(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "<b>✨ Lumens</b>\n"
        "points for being part of the fam. earn them by talking, checking in "
        "with /gm, winning games, and making art.\n\n"
        f"chatting: +{points.MSG_LUMENS} (max {points.MSG_DAILY_CAP}/day)\n"
        f"/gm daily: +{points.CHECKIN_BASE} and up with a streak\n"
        f"games: +{points.AWARDS['scramble_win']}–"
        f"{points.AWARDS['charades_win']}\n"
        f"art contest: +{points.AWARDS['art_submit']} to enter, "
        f"+{points.AWARDS['art_win']} to win\n\n"
        "<b>Lumens are not tokens.</b> they can't be cashed out, sold or "
        "swapped for $LIGHT. they're for the leaderboard and bragging rights, "
        "that's it.\n\n"
        "every rank comes in two flavours — the light track or the "
        "festival track. same climb, your pick. /title\n\n"
        "/rank · /title · /leaderboard · /leaderboard week",
        parse_mode=ParseMode.HTML)


# --- games ------------------------------------------------------------------

async def cmd_charades(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat_id = update.effective_chat.id
    if chat_id > 0:
        await msg.reply_text("charades is a group thing fam")
        return
    if games.active(chat_id):
        await msg.reply_text(f"round already running — {games.seconds_left(chat_id)}s left")
        return

    actor = update.effective_user
    word = games.start_charades(chat_id, actor.id, _name(actor))
    try:
        await ctx.bot.send_message(
            actor.id,
            f"you're up 🎭\n\nyour word is: <b>{word}</b>\n\n"
            "describe it in the group without saying it. "
            "no spelling it out, no rhyming with it.",
            parse_mode=ParseMode.HTML)
    except Exception:
        games.end(chat_id)
        await msg.reply_text(
            f"{_name(actor)} — DM me first so I can send you the word, "
            f"then run /charades again 👋")
        return

    await msg.reply_text(
        f"🎭 <b>charades</b>\n{_name(actor)} has the word. describe it fam, "
        f"everyone else guess.\n{games.ROUND_SECONDS}s on the clock · /hint",
        parse_mode=ParseMode.HTML)


async def cmd_scramble(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if games.active(chat_id):
        await update.effective_message.reply_text(
            f"round already running — {games.seconds_left(chat_id)}s left")
        return
    r = games.start_scramble(chat_id)
    await update.effective_message.reply_text(
        f"🔤 <b>unscramble it</b>\n\n<code>{r['scrambled']}</code>\n\n"
        f"<i>{r['clue']}</i>\n{games.ROUND_SECONDS}s · /hint",
        parse_mode=ParseMode.HTML)


async def cmd_riddle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if games.active(chat_id):
        await update.effective_message.reply_text(
            f"round already running — {games.seconds_left(chat_id)}s left")
        return
    r = games.start_riddle(chat_id)
    await update.effective_message.reply_text(
        f"🧩 <b>what's this</b>\n\n{r['emoji']}\n\n"
        f"{games.ROUND_SECONDS}s · /hint", parse_mode=ParseMode.HTML)


async def cmd_hint(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    h = games.hint(chat_id)
    if not h:
        await update.effective_message.reply_text(
            "no round running, or the hint's already out")
        return
    await update.effective_message.reply_text(f"💡 <code>{h}</code>",
                                              parse_mode=ParseMode.HTML)


WIN_LINES = [
    "{who} GOT IT ✨ +{n} Lumens",
    "there it is. {who} takes it, +{n} Lumens",
    "{who} with the answer 🔥 +{n} Lumens",
    "too easy for {who} apparently. +{n} Lumens",
]


async def _handle_guess(update, ctx):
    """Returns True if this message won a round."""
    msg = update.effective_message
    chat_id = update.effective_chat.id
    user = update.effective_user

    won = games.check_guess(chat_id, user.id, msg.text)
    if not won:
        return False

    key = {"charades": "charades_win", "scramble": "scramble_win",
           "riddle": "riddle_win"}[won["kind"]]
    _, amount = points.award_named(user.id, chat_id, key, user.username)
    line = random.choice(WIN_LINES).format(who=_name(user), n=amount)
    tail = f"\nthe answer was <b>{won['answer']}</b>"

    if won["kind"] == "charades":
        _, actor_amt = points.award_named(
            won["actor_id"], chat_id, "charades_actor")
        tail += f"\n{won['actor_name']} +{actor_amt} for acting it out"

    await msg.reply_text(line + tail, parse_mode=ParseMode.HTML)
    return True


# --- art contest ------------------------------------------------------------

async def cmd_artrules(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        art.rules_text(points.AWARDS), parse_mode=ParseMode.HTML)


async def cmd_artround(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin: /artround [prompt] — blank picks one for you."""
    if not await _is_admin(update, ctx):
        return
    prompt = " ".join(ctx.args) or random.choice(art.PROMPTS)
    round_id = art.new_round_id()
    db.start_art_round(round_id, prompt)
    await ctx.bot.send_message(
        db.main_chat(config.MAIN_CHAT_ID),
        f"🎨 <b>art contest is open</b>\n\nthis round: <b>{prompt}</b>\n\n"
        f"send it with /submit · rules in /artrules\n"
        f"+{points.AWARDS['art_submit']} just for entering, "
        f"+{points.AWARDS['art_win']} for the win",
        parse_mode=ParseMode.HTML)


async def cmd_submit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    round_id = db.art_round()
    if not round_id:
        await msg.reply_text("no art round running right now fam")
        return

    photo_msg = msg.reply_to_message if msg.reply_to_message else msg
    if not photo_msg.photo:
        await msg.reply_text(
            "send me the image with /submit in the caption, or reply to your "
            "image with /submit")
        return
    if db.already_submitted(round_id, user.id):
        await msg.reply_text("you're already in this round fam, one each")
        return

    file_id = photo_msg.photo[-1].file_id
    caption = (photo_msg.caption or "").replace("/submit", "").strip()
    art_id = db.add_art(round_id, user.id, db.main_chat(config.MAIN_CHAT_ID),
                        user.username, file_id, caption)
    _, amount = points.award_named(user.id, db.main_chat(config.MAIN_CHAT_ID),
                                   "art_submit", user.username)

    button = InlineKeyboardMarkup([[InlineKeyboardButton(
        "✨ vote (0)", callback_data=f"art:{art_id}")]])
    body = f"🎨 by {_name(user)}"
    if caption:
        body += f"\n<i>{caption[:200]}</i>"
    await ctx.bot.send_photo(
        db.main_chat(config.MAIN_CHAT_ID), file_id, caption=body,
        parse_mode=ParseMode.HTML, reply_markup=button)

    if update.effective_chat.type == "private":
        await msg.reply_text(f"in the contest ✨ +{amount} Lumens")


async def on_art_vote(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    art_id = int(q.data.split(":", 1)[1])
    ok, votes = db.vote_art(art_id, q.from_user.id)

    if not ok:
        await q.answer("already voted, or that's yours 😄")
        return
    await q.answer("voted ✨")
    try:
        await q.edit_message_reply_markup(InlineKeyboardMarkup([[
            InlineKeyboardButton(f"✨ vote ({votes})",
                                 callback_data=f"art:{art_id}")]]))
    except Exception:
        pass


async def cmd_artend(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin: close the round, pay out, announce."""
    if not await _is_admin(update, ctx):
        return
    round_id = db.art_round()
    if not round_id:
        await update.effective_message.reply_text("no round running")
        return

    winners = db.art_results(round_id, 3)
    db.start_art_round("", "")
    if not winners:
        await ctx.bot.send_message(db.main_chat(config.MAIN_CHAT_ID),
                                   "art round closed with no entries. next time fam")
        return

    medals = ["🥇", "🥈", "🥉"]
    keys = ["art_win", "art_runner_up", "art_runner_up"]
    lines = [f"🎨 <b>art contest results</b>\n<i>{db.art_prompt(round_id)}</i>\n"]
    for i, w in enumerate(winners):
        _, amount = points.award_named(
            w["user_id"], db.main_chat(config.MAIN_CHAT_ID), keys[i], w["username"])
        who = f"@{w['username']}" if w["username"] else "a Lightworker"
        lines.append(f"{medals[i]} {who} — {w['votes']} votes · +{amount} ✨")

    await ctx.bot.send_photo(
        db.main_chat(config.MAIN_CHAT_ID), winners[0]["file_id"],
        caption="\n".join(lines), parse_mode=ParseMode.HTML)


# --- called from bot.py's message handler -----------------------------------

async def on_group_message(update, ctx):
    """Guess check + Lumens earning. Returns True if it answered a round."""
    msg = update.effective_message
    user = update.effective_user
    chat_id = update.effective_chat.id

    if await _handle_guess(update, ctx):
        return True

    earned, crossed = points.earn_from_message(
        user.id, chat_id, msg.text, user.username)
    if crossed is not None:
        track = db.get_track(user.id, chat_id)
        lifetime = db.get_points(user.id, chat_id)["lifetime"]
        (_, rank_name, icon), _ = points.rank_for(lifetime, track)
        alt = points.other_track(track)
        (_, alt_name, alt_icon), _ = points.rank_for(lifetime, alt)
        await msg.reply_text(
            f"{_name(user)} just hit {icon} <b>{rank_name}</b> ✨",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                f"or wear {alt_icon} {alt_name}", callback_data=f"trk:{alt}")]]))
    return False


def register(app):
    app.add_handler(CommandHandler("rank", cmd_rank))
    app.add_handler(CommandHandler(["leaderboard", "top"], cmd_leaderboard))
    app.add_handler(CommandHandler(["gm", "checkin"], cmd_checkin))
    app.add_handler(CommandHandler("lumens", cmd_lumens))
    app.add_handler(CommandHandler("title", cmd_title))
    app.add_handler(CallbackQueryHandler(on_track_pick, pattern=r"^trk:"))
    app.add_handler(CommandHandler("give", cmd_give))

    app.add_handler(CommandHandler("charades", cmd_charades))
    app.add_handler(CommandHandler("scramble", cmd_scramble))
    app.add_handler(CommandHandler("riddle", cmd_riddle))
    app.add_handler(CommandHandler("hint", cmd_hint))

    app.add_handler(CommandHandler("artrules", cmd_artrules))
    app.add_handler(CommandHandler("artround", cmd_artround))
    app.add_handler(CommandHandler("artend", cmd_artend))
    app.add_handler(CommandHandler("submit", cmd_submit))
    app.add_handler(MessageHandler(
        filters.PHOTO & filters.CaptionRegex(r"(?i)/submit"), cmd_submit))
    app.add_handler(CallbackQueryHandler(on_art_vote, pattern=r"^art:"))
