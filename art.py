"""SpreadLight art contest — community-made art, voted on in the group.

On the "shill" part, which shapes how this is built:

Rewarding people to post promotional content about a token on social media,
without disclosure, is what the FTC endorsement guides are about, and the SEC
has pursued undisclosed paid crypto promotion. So this feature deliberately
pays Lumens for MAKING and SHARING art inside the community — never for
posting it to an outside platform, which Homie can't verify anyway.

If people do share it outward (and they will, that's the point), /artrules
tells them to say they hold $LIGHT. That one line costs nothing and takes the
whole problem off the table.
"""

import time

PROMPTS = [
    "draw what 'spread light' means to you",
    "a lighthouse, any style, any medium",
    "SpreadLight x your city",
    "the moment someone helped you when they didn't have to",
    "what a Lightworker looks like",
    "$LIGHT logo, reimagined",
    "a candle lighting another candle",
    "sunrise over somewhere that matters to you",
    "the charity wallet as a physical object",
    "make the ugliest SpreadLight art you possibly can",
    "SpreadLight in the year 3000",
    "a festival crowd made of light",
    "your pet as a Lightworker",
    "Hi 5 in, High 5 out — visualised",
    "SpreadLight as a 1970s album cover",
]

RULES = """<b>SpreadLight art contest ✨</b>

<b>how it works</b>
• send your art here with /submit (or reply to your image with /submit)
• one entry per person per round
• the group votes, highest votes wins
• {submit} Lumens just for entering, {win} for the win, {runner} for 2nd

<b>the rules</b>
• make it yourself. AI tools are fine, stealing someone's art is not
• nothing hateful, nothing NSFW, nobody's face without their say-so
• no price talk, no "this will 100x", no fake partnerships or exchange logos
• if you post it outside this group, say you hold $LIGHT. one line, that's it

<b>what the Lumens are</b>
points for status in here. they are not tokens, they can't be cashed out,
sold, or swapped, and they never will be. they're for the leaderboard."""


def new_round_id():
    return time.strftime("%Y-%W", time.gmtime())


def rules_text(awards):
    return RULES.format(
        submit=awards["art_submit"],
        win=awards["art_win"],
        runner=awards["art_runner_up"],
    )
