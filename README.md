# Homie — SpreadLight community bot

A small, extendable Telegram bot for a token in presale. Four jobs:

1. **Runs the presale** — announces every Big Giver, tracks progress to soft
   and hard cap from the chain itself, posts milestones at 25/50/75/100%, and
   counts down the final week.
2. **Talks like you** — replies in your voice when tagged, replied to, or
   occasionally on its own. Welcomes new members by name and asks them a real
   question. Posts a daily check-in.
3. **Protects wallets** — deletes fake contract addresses and outside links,
   bans impersonators on the way in, warns anyone who mentions getting a DM,
   and makes every new joiner pass a captcha.
4. **Keeps the chat clean** — filters cursing with a three-strike mute, and
   reroutes marketers out of the group into Homie's DMs where Fred handles
   them personally.
5. **Runs the games** — Lumens points with ranks, three chat games, and a
   three-game HTML5 arcade with group high-score boards.
6. **Removes deleted accounts** on a schedule.
7. **Commands** — see the table at the bottom.

Roughly 700 lines total, no framework, SQLite for storage. Adding a feature
means adding one handler in `bot.py` and one table in `db.py`.

---

## Setup (15 minutes)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env
```

**1. Create the bot.** Message [@BotFather](https://t.me/BotFather) → `/newbot`.
Name it **Homie**, pick a username ending in `bot`. Copy the token into
`BOT_TOKEN`. Then:

- `/setprivacy` → **Disable**. Without this Homie only sees messages that tag
  him, and the whole conversational side is dead.
- `/setdescription` and `/setabouttext` — short, in his voice.
- `/setuserpic` — give him a face.
- `/setcommands`, paste:
  ```
  presale - progress and countdown
  ca - official contract addresses
  play - the arcade
  rank - your Lumens and rank
  leaderboard - top Lightworkers
  gm - daily check-in
  scramble - word game
  riddle - emoji puzzle
  charades - act it out
  lumens - how points work
  stats - community numbers
  ask - ask me anything about the project
  ```

**2. Build the new group.**

1. New Group → name it → add one throwaway account so Telegram lets you create
   it, then **convert to a supergroup** (happens automatically once you set a
   public link, or add 200+ members).
2. Group Settings → Permissions: turn **off** *Add Users* for regular members.
   During a presale, open invites are how raid bots get in.
3. Turn **off** *Send Media* and *Send Links* for regular members for the first
   week. Scammers post a fake contract in the first hour of a new group; this
   costs you almost nothing and removes the attack.
4. Set a public link (`t.me/yourgroup`) only once the above is set — the moment
   it's public, it's discoverable.
5. Add Homie, promote him to admin with **Ban users** and **Delete messages**.
6. Pin one message with the real contract and the real presale link. Keep it
   the only pinned message.

Keep the old group alive and pointed at the new one for a week before you
delete it — an abandoned group with your project name is a gift to an
impersonator.

**3. Get your IDs.** Start the bot (`python bot.py`), run `/id` in the group,
paste the two numbers into `MAIN_CHAT_ID` and `ADMIN_IDS`.

**4. Add your Anthropic key** for the conversational layer. Without it the bot
still runs, but replies are canned one-liners. Haiku is the default model —
it's fast and cheap enough to leave running in a busy group.

**5. Addresses are set and confirmed.**

| Variable | Address | What it is |
|---|---|---|
| `PRESALE_ADDRESS` | `0x9cC48839…CdB2E3A` | the pool that receives BNB — this is what Homie watches |
| `TOKEN_ADDRESS` | `0x975FfA9d…fDE3aD9` | the $LIGHT token contract (reference only) |

Sanity check before launch: send 0.01 BNB to the presale yourself and confirm
Homie posts it within a minute. That one test proves the whole chain works.

**6. `voice.md` is already written** from Fred's own messages. Add to the
"Real messages Fred has written" section any time — it's the highest-value
thing in the repo.

```bash
python bot.py
```

---

## Making it sound like you

`voice.md` is the personality, reloaded on every message so edits are live.
Adjectives get you maybe 60% of the way. Pasting 20 of your own real Telegram
or X messages under a `## Real messages I've written` heading gets you to 90%.
Do that first, tune the rest after you've watched it talk for a day.

Two dials in `.env`:

- `AMBIENT_REPLY_CHANCE` — how often it jumps into conversations it wasn't
  tagged in. Start at `0.12`. Above `0.25` it starts feeling like it's
  hovering.
- `ICEBREAKER_HOUR_UTC` — the daily check-in. Set it to when your community is
  actually awake, not when you are.

Hard rules live in `persona.py` under `GUARDRAILS` and always override
`voice.md`: no price talk, no promises of returns, no financial advice, never
handle seed phrases, never invent a number or a date. Leave those in — a bot
speaking as the founder of a presale is the single easiest way to create a
problem you didn't intend.

---

## Presale progress

Progress is read straight from the pool's BNB balance on-chain — no API key,
and it counts contributions made before Homie existed. Set in `.env`:

```
SOFT_CAP_BNB=5
HARD_CAP_BNB=15
PRESALE_END=2026-11-04T23:59:00+00:00
```

**Copy the exact end time from the PinkSale page.** The value above assumes
midnight UTC; if PinkSale says a different hour, the countdown will be off by
that much.

What Homie posts, all fixed text — no AI anywhere near a number:

- every contribution card shows a progress bar, distance to soft cap, time left
- milestones: soft cap, then 25 / 50 / 75 / 100% of hard cap, each exactly once
- countdown: 7 days, 3 days, 24 hours, 6 hours, 1 hour before close

Milestones already passed when Homie first boots are recorded silently, so he
doesn't dump four celebrations into the chat on day one.

---

## Scam shield

Presale is peak scam season. Every reply in this section is fixed text, never
AI-generated — when the subject is where to send money, there's no room for a
creative answer.

**`/ca`** returns the token and pool addresses as tap-to-copy text. Homie is
also hard-instructed never to type an address himself — he points to `/ca`.
One hallucinated character would send someone's BNB into the void.

**Foreign addresses** — any `0x…` address that isn't the token or the pool gets
deleted, including lookalikes one character off. Add the charity Gnosis Safe to
`EXTRA_ALLOWED_ADDRESSES` once it's live.

**Outside links** — anything not on `ALLOWED_DOMAINS` gets deleted, including
hidden links behind text. That catches `spreadlight-claim.com` style drainers.
`t.me` links are blocked unless the handle is in `ALLOWED_TG` or is Homie
himself — put your group and channel handles there.

**Impersonators** are banned the moment they join. Triggers: a name or handle
that mimics an admin (`KaizenFresh`, `Kaizen Fr3sh`, `kaizenfresh_support`),
the project name plus a staff title (`SpreadLight Support`, `Homie Admin`), or
"support" / "helpdesk" / "admin" in a display name. It deliberately does *not*
ban someone for putting "SpreadLight" or "$LIGHT" in their name — that's a fan.

**DM mentions** — when anyone says "someone DMed me", "support messaged me" and
so on, Homie posts the "team never DMs first" warning. Rate-limited to once
every 10 minutes so it can't be spammed.

You get a private notice for every removal and every ban. Impersonator notices
carry the `/unban <id>` to undo them, because the trigger is a heuristic on
display names and it will be wrong sometimes.

**What the shield sees.** It runs in handler group `-1`, before any other
handler can claim the message, and it reads captions as well as text. Both of
those were bugs once: a fake address under a photo was invisible to it, and a
photo captioned `/submit` went to the art-contest handler with its caption
never examined.

**What it deliberately doesn't do.** A bare `word.word` is not treated as a
domain — Telegram's own link detection decides that, because it carries the
real TLD list. The regex backstop only fires on text with a scheme, a `www.`
or a path. Without that, "ok.Thanks" and "no.Im good" were read as links and
deleted with a public callout, which on phones happens constantly.

## Join captcha

New members are muted until they tap *i'm human ✨*. Pass → the chat's normal
permissions come back and Homie welcomes them by name. No tap within 3 minutes
→ removed, prompt deleted. Only the person who joined can press their button.

Pending captchas are written to the database and re-armed on startup, each
with a fresh window. The job queue is in memory, so before that a restart
during someone's captcha left them muted in the group permanently, with a
button that no longer did anything and nobody aware of it.

Admins skip both the captcha and the impersonator check.

## Moderating by hand

The automatic layers catch patterns. They are not a substitute for being able
to act, or to overrule the bot. `/mod` prints this list in Telegram:

| | |
|---|---|
| `/del` | delete the message you replied to |
| `/warn [reason]` | a strike, nothing deleted |
| `/mute [minutes]` | default `MUTE_MINUTES` |
| `/unmute` | lift a mute, clear their strikes, stand down a pending captcha |
| `/ban [reason]` · `/unban <id>` | |
| `/forgive` | wipe strikes, unmute, clear a pitch flag |
| `/strikes` | who's on strikes here |
| `/health` | what Homie can and can't actually do in this group |

Each takes a reply, an `@handle` or a numeric id. A handle only resolves for
someone Homie has seen post — the Bot API has no username lookup — and it says
so rather than failing silently.

**`/health` is the one to run after adding Homie to a group.** It asks Telegram
what permissions he actually holds. Without *Delete messages* the shield can
spot a scam and not remove it; it now warns the group and messages you instead
of logging a line nobody reads.

**Strikes decay** after `STRIKE_DECAY_HOURS` (default 7 days). They used to be
permanent, so one slip in March left a member a single word from a mute in
September.

## Stickers from logos

Send Homie a logo and he turns it into something Telegram will accept:

```
/sticker 🕊            reply to a logo, or caption the logo itself
/sticker 🕊 crop       crop to the middle first — for a wide banner or a
                       big scene, where the subject ends up tiny otherwise
/sticker 🕊 keep       keep the background instead of cutting it
/sticker 🕊 cut        force the background off
/sticker 🕊 own        put it in Homie's own pack rather than handing it back
/emoji 🕊              the 100x100 a custom emoji needs
```

He hands the file back, and you forward it to **@Stickers** to add it to the
community pack. That round trip is Telegram's rule, not a shortcut:
`addStickerToSet` works on *"a set created by the bot"*, and a pack made by a
person through @Stickers can never be extended by a bot. What Homie does is
the fiddly part — background, sizing, outline.

**The conversion.** A logo and a sticker are not the same kind of image. A
logo arrives on a white card; a sticker has no card, it sits on whatever the
reader's chat background is. So the card comes off via a flood fill from the
edges — not a colour key, which would punch holes through white *inside* the
logo. Then the art gets an outline, light or dark depending on which it
needs, because once the card is gone a dark logo vanishes on a dark theme and
about half of Telegram runs dark.

**Shape.** Telegram wants *one* side at exactly 512; the other can be anything
up to it. So a sticker keeps the artwork's real proportions instead of being
padded into a square — padding a 16:9 banner left the strip floating in a
mostly empty frame using 42% of the image, and the artwork on screen half the
size it could be. Custom emoji are the exception: those must be exactly
100×100, so they do get centred on a square.

**Knowing when not to cut** is the harder half. A logo on a white card and an
illustration on a dark gradient both have four corners that agree, so corner
matching says yes to both — and on the gradient the fill stops wherever the
tolerance runs out and tears a ragged hole through the artwork. The tell is
what the fill stops *against*: a real card ends at a hard edge, a gradient
just drifts. Measured across real inputs, flat cards step 82–107 and
gradients 39–47 against a tolerance of 38. Below 70 it keeps the square.

### Putting them on moments

```
/stickerpack <link>    point Homie at the community pack
/stickeruse            list the moments
/stickeruse welcome    reply to a sticker to wire it to one
/stickeruse welcome off
```

Moments: `welcome` (after the captcha), `milestone` (a cap is crossed),
`biggiver`, `gm` (the daily post), `hype`. Each is optional and silently does
nothing until assigned — and a `file_id` works whoever made the pack, so
these can be stickers from the community's own pack.

**Custom emoji are the exception.** Homie can build an emoji pack and anyone
with Premium can use it, but a bot may only put custom emoji in *its own*
messages if it has bought an extra username on Fragment — *"Custom emoji
entities can only be used by bots that purchased additional usernames on
Fragment."* Stickers have no such restriction, which is why the sticker half
is the half wired into his replies.

### Admin rights are tied to an id, not a handle

A Telegram username is rented. Change yours and the old handle returns to the
pool for anyone to claim — and `/say` broadcasts to the whole group, `/leads`
reads every pitch sent in, `/setgroup` repoints the bot and `/give` mints
Lumens. So `ADMIN_USERNAMES` is only ever a **claim**: it is honoured once,
and only if Telegram independently agrees that person administrates the group,
and then their numeric id is pinned to the database and the handle stops
mattering. Put your own id in `ADMIN_IDS` (run `/id`) and nothing depends on a
name at all.

---

## Lumens ✨ — the point system

Points for status in the group. Homie shouts when someone ranks up.

**Every rank comes in two flavours.** Same thresholds, same Lumens — members
pick which name they wear, and switch any time with `/title`:

| ✨ | the light track | the festival track |
|---|---|---|
| 0 | 🔅 Spark | 🟢 Glowstick |
| 100 | 🕯 Candle | ⚡ Strobe |
| 300 | 🏮 Lantern | 💫 Laser |
| 750 | 🔦 Beacon | 🔆 Spotlight |
| 1,500 | 🗼 Lighthouse | 🎪 Mainstage |
| 3,000 | ⭐ Star | 🎤 Headliner |
| 6,000 | 🌟 Supernova | 👑 Legend |

The tiers are prestige-matched on purpose, so neither side is the weak pick —
Star and Headliner are both "the famous one", Lighthouse and Mainstage are
both the landmark you see from far off. New members default to the light
track; the rank-up message carries a one-tap button to flip.

| how you earn | Lumens |
|---|---|
| talking (45s cooldown, 25/day cap, 8+ chars) | 1 |
| `/gm` daily check-in | 5 + 2 per streak day, capped at 10 days |
| winning `/scramble` or `/riddle` | 8 |
| winning `/charades` (actor gets 10) | 15 |
| entering the art contest | 10 |
| winning the art contest | 100 |
| beating your arcade best (once/day) | 25 |

`/rank` · `/title` · `/leaderboard` · `/leaderboard week` · `/lumens`
Admin: `/give 50 reason` as a reply to someone.

**Lumens are deliberately not worth money.** They can't be cashed out, sold,
traded, or swapped for $LIGHT, they can't be transferred between members, and
Homie is instructed never to hint that they might be someday. Two reasons:
a points system that pays out is a promotional scheme with rules attached,
and non-transferable points are worthless to farm — which is why the
leaderboard will reflect real activity instead of bots.

Every award is written to a `points_log` table, so you can always answer
"why does this person have 4000 Lumens".

---

## Chat games

No hosting needed — these work the moment the bot runs.

**`/scramble`** — unscramble a SpreadLight-themed word, first correct wins.
**`/riddle`** — emoji puzzle (`🤝 + 5️⃣` → high five).
**`/charades`** — whoever runs it gets the word by DM and describes it in chat;
first correct guesser and the actor both get paid. The actor has to have DM'd
Homie once first, or Telegram won't let him send the word — Homie says so and
cancels cleanly.

All three run 90 seconds, take one `/hint`, and only one round runs at a time.

---

## The arcade

Four original games, built for phones, with group high-score boards.

| game | genre |
|---|---|
| **Shadow Wave** | fixed shooter — you're the last beacon, shadows descend |
| **Lumen Run** | maze collector — clear the grid, grab a sunburst and they run from you |
| **Light Rally** | paddle rally — every return speeds it up |
| **Neon Breach** | first person — a raycast arena, drones closing in, one thumb |

These are originals, not clones. Pac-Man is Bandai Namco's and Space Invaders
is Taito's — the sprites, names and characters are protected even if you
rewrite the code. Game *mechanics* aren't, so these use the same genres with
SpreadLight's own art and names. That's the difference between homage and a
takedown notice on a brand you're trying to build trust with.

### Neon Breach

A raycaster: 180 vertical columns, each one a ray walked through the map with
DDA. How far the ray travels sets how tall that slice of wall is and how far
it fades out. Drones and lumens are flat shapes projected into the same space
and clipped against the depth written down per column, which is what lets one
stand behind a pillar.

Controls are built for a thumb, not a keyboard: **hold anywhere** and the
touch point becomes a stick — slide to walk and turn — and a **tap** that
doesn't move is a shot. Two on-screen pads would eat a phone screen this
small. Keyboard works too, for anyone opening it on a desktop.

A drone that reaches you costs a light and gets thrown back into the arena
rather than destroyed, so a wave ends only when you have actually shot
everything in it.

### Difficulty

All four ramp with the wave or level, and all of them cap. The ceilings are
deliberate: in Lumen Run the shadows never get faster than 2.3 against the
runner's 2.4, because a chase you cannot outrun stops being a test of skill;
in Light Rally the ball stops accelerating at about 11px a frame, past which
it crosses the paddle between two visible frames and there is nothing left to
react to.

`tests/test_mazes.py` checks that every lumen in Lumen Run and every floor
tile in Neon Breach can actually be reached. That test exists because 17 of
Lumen Run's lumens once could not be — see the comment at the top of its
`MAZE`.

### Getting the arcade live

Everything else in this bot runs without it. The arcade is the one piece that
needs a public HTTPS address, because Telegram loads the game in a webview.

**1. Point a subdomain at the server** — an A record for `play.spreadlight.io`
to your box's IP.

**2. Caddy for TLS** (two lines, certificates are automatic):

```bash
apt install -y caddy
```
```
# /etc/caddy/Caddyfile
play.spreadlight.io {
    reverse_proxy 127.0.0.1:8080
}
```
```bash
systemctl reload caddy
```

**3. Set it in `.env`:**
```
ARCADE_URL=https://play.spreadlight.io
```

**4. Register each game with BotFather** — `/newgame`, once per game. The
**short name must match exactly**: `shadowwave`, `lumenrun`, `lightrally`,
`neonbreach`. BotFather asks for a title, description and photo each time;
`python3 tools/make_game_covers.py` writes the 640×360 photos it wants.

> `/newgame` requires the bot to be **in inline mode first** — BotFather
> answers "You have no inline bots yet" otherwise, which looks like a wrong
> turn rather than a missing prerequisite. `/setinline` on the bot, then
> `/newgame`. A new game added later needs only the `/newgame` step.

**5. Restart.** `/play` in the group now shows the menu, `/scores` shows the
boards.

### On fake scores

Any browser game can have its score faked by someone with dev tools. This
closes the easy holes but not that one: the play URL carries a short-lived
HMAC token tied to one user, one chat and one message, so you can't post a
score as someone else; tokens expire after an hour; anything above a per-game
ceiling is dropped. And the Lumens payout is a flat 25/day no matter the
score, so cheating buys a name on a leaderboard and nothing else. That's the
right size prize for a game in a group chat.

---

## Art contest

`/artround` (admin) opens a round with a prompt — pass your own or let Homie
pick from a bank. Members reply to their image with `/submit`, or DM it to
Homie. Each entry gets posted to the group with a vote button. One entry each,
one vote per person, no voting for yourself. `/artend` closes it, pays the top
three and announces the winner with their art.

`/artrules` posts the rules, including this line, which matters:

> if you post it outside this group, say you hold $LIGHT. one line, that's it.

Paying people to promote a token on social media without disclosure is what
the FTC endorsement guides cover, and the SEC has pursued undisclosed paid
crypto promotion. So Lumens are paid for making and sharing art *inside* the
community, never for posting to an outside platform — which Homie couldn't
verify anyway. People will still share it, and that one disclosure line takes
the whole problem off the table for free.

---

## Content filters

Two plain text files, created on first run, editable without touching code.
After editing either one, run `/reload` in the group — no restart needed.

### `banned_words.txt` — cursing

Matching is normalised, so all of these hit the same rule:
`fuck` · `F*CK` · `f.u.c.k` · `fuuuuck` · `sh1t` · `f u c k` · `fucking`

Word boundaries keep the obvious false positives out — *Scunthorpe*,
*assessment*, *classy*, *shiitake* all pass clean. Compounds like `bullshit`
need their own line, and a few are in there already.

What happens: message deleted, short line from Homie, strike recorded. Third
strike is a 60-minute mute. `/forgive` as a reply wipes someone's strikes and
unmutes them. Group admins are exempt from the whole thing.

The starter list covers common profanity. **Add slurs and anything specific to
your community yourself** — that list is yours to own, and it's the half that
actually matters.

### `marketer_words.txt` — pitch reroute

Catches agency and promo pitches: *marketing agency*, *calls channel*, *KOL*,
*dextools trending*, *volume bot*, *guaranteed holders*, *dm for pricing*, and
so on. Two distinct hits trigger it, or one hit in a message over 300
characters — so "the marketing on this is clean" stays put and a wall of text
about growing your holder count does not.

What happens: message deleted, Homie posts a public line pointing them at his
DMs with a `?start=pitch` deep link, and you get the full text forwarded
privately. In the DM Homie takes their pitch, files it, and tells them Fred
reads these himself. `/leads` shows the last ten.

**Homie needs to be able to reach you.** DM him once and send anything — that
registers your chat as the founder inbox. Until you do, pitches are stored but
not forwarded, and the log will say so.

---

## Chain data: which backend

`CHAIN_BACKEND=etherscan` (default) makes one API call per poll. BscScan's own
V1 API was retired and folded into Etherscan's V2 API — one key, all chains,
`chainid=56` for BSC. Free-tier availability for BNB Chain has been in flux, so
if your key gets rejected:

`CHAIN_BACKEND=rpc` needs no key at all. It scans recent blocks on a public BSC
node and filters for transactions to the presale address. Heavier on bandwidth
(BSC blocks are sub-second now), fine for a single address. Swap `BSC_RPC_URL`
for a private node if a public one starts rate-limiting you.

Either way the announcement is the same. Contributions are keyed by tx hash, so
a restart, a double poll, or a backend switch never double-posts.

---

## The deleted-accounts caveat (read this)

The Telegram Bot API gives a bot **no way to list group members**. There is no
`getChatMembers`. So `moderation.py` can only check users it has recorded —
anyone who joined or posted since you added the bot. A member who's been silent
since before then is invisible to it.

Detection is a heuristic: a deleted account comes back from `getChatMember`
with an empty name and no username.

For a complete one-time clear of everyone already in the group, run
`tools/sweep_deleted.py`. It signs in as *you* via Telegram's official MTProto
API, walks the full participant list, and reads the real `user.deleted` flag.
Dry-run first:

```bash
pip install telethon
python tools/sweep_deleted.py            # lists them, changes nothing
python tools/sweep_deleted.py --remove
```

Run it once. After that the bot keeps up on its own.

---

## Deploying (Hetzner, ~10 minutes)

### 1. Put the code on GitHub

The server pulls from a repo, which also makes later updates one command
instead of re-uploading everything.

Open **GitHub Desktop** → File → *Add local repository* → pick this folder →
*Publish repository*. Name it `homie-bot`. **Public is fine** — there are no
secrets in here, and `.gitignore` already blocks `.env` and the database.
Never commit `.env`.

### 2. Create the server

[console.hetzner.com](https://console.hetzner.com) → New Project → Add Server

- **Location:** Ashburn, VA
- **Image:** Ubuntu 24.04
- **Type:** Shared vCPU → CAX11 (Arm, cheapest) or CX23 (x86)
- **Cloud config / User data:** paste `deploy/hetzner-cloud-init.sh`, with the
  four values at the top filled in

Click Create. The box installs Python, clones the repo, writes the config and
starts the service by itself. Give it about two minutes.

If anything looks wrong, the whole run is logged to `/var/log/homie-setup.log`
and you can read it from Hetzner's web console.

### 3. Tell Homie where home is

In the group, as admin:

```
/setgroup
```

That's it. Homie records the group's chat id himself, so it never has to be
known in advance — which matters, because **a basic group's id changes the
moment Telegram promotes it to a supergroup**. If that happens later, just run
`/setgroup` again.

Then `/check` confirms the presale watcher is pointed at the right contract.

### Updating later

```bash
cd /opt/homie/app && git pull && systemctl restart homie
```

Logs: `journalctl -u homie -f`

Back up `spreadlight.db` — it holds the contribution ledger, the Lumens
ledger and member history.

---

## Extending it

The layout is deliberately boring so you can bolt things on:

| File | What it owns |
|---|---|
| `bot.py` | handlers, commands, scheduled jobs |
| `config.py` | every setting, all from `.env` |
| `db.py` | schema + helpers, add a table and two functions |
| `persona.py` | the voice, the guardrails, the prompts |
| `presale.py` | on-chain polling, both backends |
| `moderation.py` | deleted-account sweep |
| `points.py` | Lumens ledger, ranks, earning rules |
| `community.py` | points/games/art command handlers |
| `games.py` | word banks and round state for chat games |
| `art.py` | art contest prompts and rules text |
| `arcade_server.py` | serves the games, validates scores |
| `arcade/` | the three HTML5 games |
| `shield.py` | fake addresses, bad links, impersonators, DM warnings |
| `guard.py` | cursing and marketer detection |

Likely next steps, in the order I'd do them:

1. **Referral leaderboard** — personal invite links, weekly shoutout for who
   brought the most fam. Reward with recognition and roles, not tokens.
2. **Port the Lumens ledger over** — you already built the points system; the
   `members` table is where it slots in.
3. **Buy bot** — after launch, point the poller at the PancakeSwap LP pair and
   decode `Swap` events.
4. **Charity wallet tracker** — same polling pattern pointed at the Gnosis Safe,
   posting a milestone whenever total donated crosses a round number.


---

## Commands

| command | who | what |
|---|---|---|
| `/start` | all | intro |
| `/presale` | all | progress bar, caps, countdown |
| `/ca` | all | official addresses, tap to copy |
| `/stats` | all | community numbers |
| `/ask <q>` | all | ask Homie something |
| `/lumens` | all | how points work |
| `/rank` | all | your rank (or reply to someone) |
| `/title` | all | switch between the light and festival ladders |
| `/leaderboard [week]` | all | top Lightworkers |
| `/gm` | all | daily check-in + streak |
| `/scramble` `/riddle` `/charades` `/hint` | all | chat games |
| `/play` `/scores` | all | arcade and its boards |
| `/submit` `/artrules` | all | art contest |
| `/artround [prompt]` `/artend` | admin | open/close an art round |
| `/give <n> [reason]` | admin | award Lumens (reply to someone) |
| `/say <msg>` | admin | broadcast to the group |
| `/leads` | admin | last 10 marketer pitches |
| `/sweep` | admin | remove deleted accounts now |
| `/mod` | admin | the moderation cheat sheet |
| `/health` | admin | what Homie can and can't do in this group |
| `/del` | admin | delete the message you replied to |
| `/warn [reason]` | admin | a strike, nothing deleted |
| `/mute [minutes]` · `/unmute` | admin | temporary silence, and lifting it |
| `/ban [reason]` · `/unban <id>` | admin | remove, and let back in |
| `/strikes` | admin | who's on strikes here |
| `/sticker [emoji]` · `/emoji` | admin | a logo becomes a sticker |
| `/stickerpack [link]` | all | the community pack |
| `/stickeruse <moment>` | admin | put a sticker on a moment |
| `/forgive` | admin | clear strikes, unmute, clear a pitch flag |
| `/reload` | admin | reload word lists |
| `/id` | admin | chat and user ids |

Moderation commands take a reply, an `@handle` or a numeric id.
