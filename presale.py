"""Watches the presale address on BNB Smart Chain and reports new contributions.

Two backends:
  CHAIN_BACKEND=etherscan  one HTTP call per poll. Needs an Etherscan V2 key
                           (the same key covers BSC via chainid=56).
  CHAIN_BACKEND=rpc        no API key at all. Scans recent blocks on a public
                           BSC node. Heavier, but free and dependency-free.
"""

import logging

import httpx

import config
import db

log = logging.getLogger(__name__)

# rpc backend: never scan more than this many blocks in one tick after downtime
MAX_BLOCK_CATCHUP = 400


async def _etherscan_new_txs():
    start = int(db.kv_get("etherscan_start_block", "0"))
    params = {
        "chainid": config.BSC_CHAIN_ID,
        "module": "account",
        "action": "txlist",
        "address": config.PRESALE_ADDRESS,
        "startblock": start,
        "endblock": 99999999,
        "sort": "asc",
        "apikey": config.ETHERSCAN_API_KEY,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(config.ETHERSCAN_URL, params=params)
        r.raise_for_status()
        data = r.json()

    if data.get("status") != "1":
        msg = data.get("message", "")
        if "No transactions found" not in msg:
            log.warning("etherscan: %s %s", msg, data.get("result"))
        return []

    out, highest = [], start
    for tx in data["result"]:
        highest = max(highest, int(tx["blockNumber"]))
        if tx.get("isError") == "1":
            continue
        if (tx.get("to") or "").lower() != config.PRESALE_ADDRESS:
            continue
        value = int(tx["value"])
        if value <= 0:
            continue
        out.append({
            "hash": tx["hash"],
            "from": tx["from"],
            "value": value,
            "block": int(tx["blockNumber"]),
            "ts": int(tx["timeStamp"]),
        })
    db.kv_set("etherscan_start_block", highest)
    return out


async def _rpc(client, method, params):
    r = await client.post(
        config.BSC_RPC_URL,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
    )
    r.raise_for_status()
    return r.json().get("result")


async def _rpc_new_txs():
    out = []
    async with httpx.AsyncClient(timeout=25) as client:
        head = int(await _rpc(client, "eth_blockNumber", []), 16)
        last = int(db.kv_get("rpc_last_block", str(head - 1)))
        start = max(last + 1, head - MAX_BLOCK_CATCHUP)

        for n in range(start, head + 1):
            block = await _rpc(client, "eth_getBlockByNumber", [hex(n), True])
            if not block:
                continue
            ts = int(block["timestamp"], 16)
            for tx in block.get("transactions", []):
                if (tx.get("to") or "").lower() != config.PRESALE_ADDRESS:
                    continue
                value = int(tx["value"], 16)
                if value <= 0:
                    continue
                out.append({
                    "hash": tx["hash"], "from": tx["from"],
                    "value": value, "block": n, "ts": ts,
                })
        db.kv_set("rpc_last_block", head)
    return out


async def fetch_new_contributions():
    """Returns a list of contributions not yet recorded in the database."""
    if not config.PRESALE_ADDRESS:
        return []
    try:
        txs = (await _etherscan_new_txs()
               if config.CHAIN_BACKEND == "etherscan"
               else await _rpc_new_txs())
    except Exception:
        log.exception("presale poll failed")
        return []

    fresh = []
    for tx in txs:
        is_new_wallet = not db.wallet_seen_before(tx["from"], tx["hash"])
        if db.record_contribution(tx["hash"], tx["from"], tx["value"],
                                  tx["block"], tx["ts"]):
            tx["bnb"] = tx["value"] / 1e18
            tx["new_wallet"] = is_new_wallet
            fresh.append(tx)
    return fresh


def short_wallet(addr):
    return f"{addr[:6]}…{addr[-4:]}"


# --- progress ---------------------------------------------------------------

import datetime as dt


async def raised_bnb():
    """BNB currently held by the presale pool, read straight from the chain.

    More accurate than summing announcements: it counts contributions made
    before Homie existed, and it needs no API key. Falls back to the local
    ledger if the node is unreachable.
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            wei = await _rpc(client, "eth_getBalance",
                             [config.PRESALE_ADDRESS, "latest"])
        return int(wei, 16) / 1e18
    except Exception:
        log.warning("balance read failed, using local ledger")
        return db.presale_totals()["total_bnb"]


def end_time():
    try:
        return dt.datetime.fromisoformat(config.PRESALE_END)
    except ValueError:
        return None


def time_left():
    """Human countdown, e.g. '12d 4h' or '3h 20m'. None once it's over."""
    end = end_time()
    if not end:
        return None
    delta = end - dt.datetime.now(dt.timezone.utc)
    secs = int(delta.total_seconds())
    if secs <= 0:
        return None
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def progress_bar(raised, cap, width=10):
    pct = 0 if cap <= 0 else min(raised / cap, 1)
    filled = round(pct * width)
    return "▰" * filled + "▱" * (width - filled), round(pct * 100)


def progress_block(raised):
    """The progress lines used in /presale and in contribution cards."""
    bar, pct = progress_bar(raised, config.HARD_CAP_BNB)
    soft = ("✅ soft cap hit" if raised >= config.SOFT_CAP_BNB
            else f"{config.SOFT_CAP_BNB - raised:.2f} BNB to soft cap")
    left = time_left()
    lines = [
        f"{bar} {pct}%",
        f"{raised:.2f} / {config.HARD_CAP_BNB:g} BNB · {soft}",
        f"⏳ {left} left" if left else "⏳ presale window closed",
    ]
    return "\n".join(lines)
