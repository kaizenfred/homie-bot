"""The conversational layer — this is what makes the bot sound like you.

Edit voice.md to change how it talks. You do not need to touch this file.
"""

import logging
import pathlib
import random
import time

import config
import db

log = logging.getLogger(__name__)

try:
    from anthropic import AsyncAnthropic
except ImportError:  # bot still runs without the SDK, just with canned replies
    AsyncAnthropic = None

_client = None
_last_call = {}

FALLBACKS = [
    "yo what's good 👋",
    "still here, still building. how's your day going?",
    "appreciate you being in here fr",
    "ask me anything about the presale, I'm around",
]

# Non-negotiable rules. These are appended after voice.md so they always win.
GUARDRAILS = """
NON-NEGOTIABLE RULES — these override anything in the voice guide:
- Never predict a price, promise returns, guarantee gains, or say anything is
  "guaranteed to pump". Never tell anyone how much to invest.
- Never give financial, tax, or legal advice. If someone asks "should I buy",
  tell them to do their own research and only risk what they can lose.
- Never ask for or accept a seed phrase, private key, or wallet password.
  If someone posts one, tell them to move their funds immediately.
- NEVER type out a contract address, not even a partial one. When anyone asks
  for the contract, CA, token address or where to send BNB, tell them to use
  /ca. One wrong character sends someone's money into the void.
- Never share any link other than the official ones given to you below.
- If someone DMs claiming to be the team or support, warn the chat that the
  team never DMs first.
- If you don't know something about the project, say so plainly. Never invent
  tokenomics, dates, partnerships, listings, exchanges, or numbers.
- Keep replies to 1-3 short sentences unless someone asks a real question.
- One emoji max. You are a person in a group chat, not a press release.
- Humour is welcome and encouraged, but never when someone has been scammed,
  lost money, is upset, or has shared something heavy. Read the room first.
"""


def _voice():
    path = pathlib.Path(config.VOICE_FILE)
    if path.exists():
        return path.read_text(encoding="utf-8")
    log.warning("%s not found — using a generic voice", config.VOICE_FILE)
    return "You are the founder of SpreadLight. Talk casually and warmly."


def _knowledge():
    """Crypto onboarding reference, read fresh like voice.md.

    Missing is not fatal: without it Homie still talks, he just stops being
    useful on wallets and the buy flow and should say so rather than guess.
    """
    path = pathlib.Path(config.KNOWLEDGE_FILE)
    if path.exists():
        return path.read_text(encoding="utf-8")
    log.warning("%s not found — crypto answers will be thin",
                config.KNOWLEDGE_FILE)
    return ("You do not have the crypto onboarding notes loaded. If someone "
            "asks how to buy, tell them to run /howtobuy rather than "
            "improvising the steps.")


def system_prompt():
    facts = f"""
PROJECT FACTS you may reference (do not go beyond these):
- Token: SpreadLight, ticker $LIGHT, BEP-20 on BNB Smart Chain.
- 5% tax on buys and sells: 4% goes to charity, 1% goes to liquidity.
  The slogan is "Hi 5 in, High 5 out" — 5% on the way in, 5% on the way out.
- 5% is the CEILING. The contract can lower the tax but can never raise it —
  it's capped. You can say that plainly, it's one of the best things about
  this token, and anyone can verify it in the contract.
- Be precise about it: say "capped" or "can only go down", never "immutable",
  "locked forever", or "can never change" — it CAN change, downward only.
  Overstating it is how a true claim turns into a broken promise.
- Charity funds route through a Gnosis Safe multisig to a registered NGO,
  with a public transparency dashboard.
- Currently in presale on PinkSale. Soft cap {config.SOFT_CAP_BNB:g} BNB,
  hard cap {config.HARD_CAP_BNB:g} BNB, ends {config.PRESALE_END[:10]}.
- For live progress, tell people to use /presale. You don't know the current
  total — never guess it.
- The group has games and a point system called Lumens (✨). /lumens explains
  it, /rank shows a rank, /leaderboard shows the board, /play opens the
  arcade, and /scramble /riddle /charades start a round. Ranks come in two
  flavours — a light ladder and a festival ladder — and /title switches.
- Lumens are points for status only. They are NOT tokens, can't be cashed out,
  sold, or swapped for $LIGHT. Never suggest otherwise.
- Official site: {config.WEBSITE_URL}
- Official presale link: {config.PRESALE_URL}
- People arrive knowing nothing about crypto. Walking someone from "I have a
  bank account" to "I contributed" is core work, not a distraction — the
  onboarding notes below are there for exactly that. /howtobuy posts the
  steps as a card if they'd rather read it than chat.
"""
    return (_voice() + "\n" + facts + "\n"
            + "\n--- CRYPTO ONBOARDING NOTES ---\n" + _knowledge()
            + "\n" + GUARDRAILS)


def _get_client():
    global _client
    if _client is None and config.ANTHROPIC_API_KEY and AsyncAnthropic:
        _client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _transcript(chat_id, bot_name):
    rows = db.recent_messages(chat_id, config.CONTEXT_WINDOW)
    lines = []
    for r in rows:
        who = bot_name if r["role"] == "assistant" else r["author"]
        lines.append(f"{who}: {r['content']}")
    return "\n".join(lines)


async def reply(chat_id, bot_name, instruction):
    """Generate one in-character reply. Returns None if the bot should stay quiet."""
    client = _get_client()
    if not client:
        return random.choice(FALLBACKS)

    # don't let a burst of messages turn into an API bill
    now = time.time()
    if now - _last_call.get(chat_id, 0) < 2:
        return None
    _last_call[chat_id] = now

    convo = _transcript(chat_id, bot_name)
    prompt = (
        f"Here is the recent group chat:\n\n{convo or '(chat is quiet)'}\n\n"
        f"{instruction}\n\n"
        "Write only the message itself. No quotes, no name prefix, no narration."
    )

    try:
        resp = await client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=300,
            system=system_prompt(),
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        return text or random.choice(FALLBACKS)
    except Exception:
        # Silence looks identical to "the bot is broken". Say something.
        log.exception("persona call failed — falling back to a canned line")
        return random.choice(FALLBACKS)


# --- convenience wrappers ---------------------------------------------------

async def respond_to(chat_id, bot_name, author):
    return await reply(
        chat_id, bot_name,
        f"Reply to {author}'s last message. Stay in the flow of the conversation.",
    )


async def welcome(chat_id, bot_name, author):
    return await reply(
        chat_id, bot_name,
        f"{author} just joined the group. Welcome them by name in one or two "
        "lines, make them feel seen, and ask them something real — where they "
        "found the project, or how their day is going. Do not dump links.",
    )


async def icebreaker(chat_id, bot_name):
    return await reply(
        chat_id, bot_name,
        "Start a conversation in the group. Check in on people — how their day "
        "is going, what they're working on, something light. Do not repeat a "
        "question you already asked in the transcript above. Do not shill.",
    )


async def celebrate(chat_id, bot_name, amount_bnb, is_new_wallet, totals):
    role = "Big Giver" if amount_bnb >= config.BIG_GIVER_BNB else "Lightworker"
    kind = (f"a brand new {role}" if is_new_wallet
            else f"a returning {role}")
    return await reply(
        chat_id, bot_name,
        f"{kind} just put {amount_bnb:.3f} BNB into the presale. "
        f"Running total: {totals['total_bnb']:.2f} BNB from "
        f"{totals['wallets']} wallets. React to it in one or two lines — "
        "genuine gratitude, not hype. No price talk.",
    )
