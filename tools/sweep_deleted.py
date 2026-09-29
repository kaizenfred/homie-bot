"""One-time full sweep of deleted accounts.

The bot can only see members who have joined or posted since it was added.
This script signs in as YOU (not the bot), so it can walk the entire member
list and remove every deleted account, including long-silent ones.

Run it once after adding the bot, then let the bot handle the rest.

Setup:
    pip install telethon
    Get api_id / api_hash from https://my.telegram.org  →  API development tools
    Put TG_API_ID, TG_API_HASH and TG_GROUP in .env
    You must be an admin of the group with "ban users" permission.

Usage:
    python tools/sweep_deleted.py            # list only, changes nothing
    python tools/sweep_deleted.py --remove   # actually remove them

Note: this uses your personal account through Telegram's official MTProto API.
Keep the pace slow (the script already does) and don't run it repeatedly.
"""

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import ChatBannedRights
from telethon.tl.functions.channels import EditBannedRequest

load_dotenv()

API_ID = os.getenv("TG_API_ID")
API_HASH = os.getenv("TG_API_HASH")
GROUP = os.getenv("TG_GROUP")  # @handle or numeric id

KICK = ChatBannedRights(until_date=None, view_messages=True)
UNBAN = ChatBannedRights(until_date=None, view_messages=False)


async def main(remove: bool):
    if not all([API_ID, API_HASH, GROUP]):
        sys.exit("Set TG_API_ID, TG_API_HASH and TG_GROUP in .env first.")

    async with TelegramClient("sweep_session", int(API_ID), API_HASH) as client:
        entity = await client.get_entity(GROUP)
        found = 0
        async for user in client.iter_participants(entity):
            if not user.deleted:
                continue
            found += 1
            print(f"deleted account: {user.id}")
            if remove:
                await client(EditBannedRequest(entity, user.id, KICK))
                await client(EditBannedRequest(entity, user.id, UNBAN))
                await asyncio.sleep(1.5)
        print(f"\n{found} deleted account(s) "
              f"{'removed' if remove else 'found (dry run)'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--remove", action="store_true", help="actually remove them")
    asyncio.run(main(p.parse_args().remove))
