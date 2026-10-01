#!/bin/bash
# =============================================================================
#  HOMIE — Hetzner first-boot setup  (v2)
#
#  Paste into the "Cloud config" box on the server-creation screen.
#  Fill in the TWO lines marked <<< first. Nothing else needs editing.
#
#  Use Ubuntu 24.04 LTS, not 26.04 — newer Ubuntu ships a Python that some
#  dependencies have no prebuilt wheels for yet, which makes pip try to
#  compile from source and fail the whole install silently.
#
#  When it finishes, Homie messages you on Telegram himself. If you get no
#  message within ~4 minutes, the bot token line is wrong.
# =============================================================================

REPO_URL="https://github.com/kaizenfred/homie-bot.git"
BOT_TOKEN="PASTE_BOTFATHER_TOKEN_HERE"        # <<< BotFather -> /mybots -> API Token
ANTHROPIC_API_KEY="PASTE_ANTHROPIC_KEY_HERE"  # <<< console.anthropic.com
ETHERSCAN_API_KEY=""                          # leave empty: uses keyless BSC node

# ------------------------- nothing below needs editing -----------------------
# deliberately NO `set -x` — it would echo the keys above into the log
set -e

LOG=/var/log/homie-setup.log
touch "$LOG"; chmod 600 "$LOG"          # not world-readable
log() { echo "[$(date -u +%H:%M:%S)] $*" >> "$LOG"; }

log "=== Homie setup starting ==="
log "python: $(python3 --version 2>&1)"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y                                        >>"$LOG" 2>&1
apt-get install -y python3 python3-venv python3-pip git \
                   ufw unattended-upgrades curl          >>"$LOG" 2>&1

id homie >/dev/null 2>&1 || useradd --system --create-home \
    --home-dir /opt/homie --shell /usr/sbin/nologin homie

log "cloning $REPO_URL"
rm -rf /opt/homie/app
git clone --depth 1 "$REPO_URL" /opt/homie/app           >>"$LOG" 2>&1
cd /opt/homie/app

log "building venv + installing deps (this is the slow part)"
python3 -m venv .venv                                    >>"$LOG" 2>&1
./.venv/bin/pip install --upgrade pip                    >>"$LOG" 2>&1
if ! ./.venv/bin/pip install -r requirements.txt         >>"$LOG" 2>&1; then
    log "FATAL: pip install failed — see above. Usually means the OS image is"
    log "       too new for these packages. Recreate on Ubuntu 24.04 LTS."
    echo "pip install failed" > /opt/homie/SETUP-FAILED.txt
    exit 1
fi
log "deps installed OK"

if [ -n "$ETHERSCAN_API_KEY" ]; then BACKEND="etherscan"; else BACKEND="rpc"; fi

cat > /opt/homie/app/.env <<ENVEOF
BOT_TOKEN=${BOT_TOKEN}
MAIN_CHAT_ID=
ADMIN_USERNAMES=KaizenFresh

ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
VOICE_FILE=voice.md
AMBIENT_REPLY_CHANCE=0.12
AMBIENT_COOLDOWN_SEC=300
CONTEXT_WINDOW=24
ICEBREAKER_HOUR_UTC=15

PRESALE_ADDRESS=0x975FfA9d75d4FdfC34B14e6bF5C67eF85fDE3aD9
TOKEN_ADDRESS=0x9cC488396E4973Bf341191Eb6196a1220CdB2E3A
PRESALE_URL=https://www.pinksale.finance/launchpad/bsc/0x975FfA9d75d4FdfC34B14e6bF5C67eF85fDE3aD9
WEBSITE_URL=https://spreadlight.io

CHAIN_BACKEND=${BACKEND}
ETHERSCAN_API_KEY=${ETHERSCAN_API_KEY}
BSC_RPC_URL=https://bsc-dataseed.binance.org
PRESALE_POLL_SEC=45
MIN_ANNOUNCE_BNB=0.01
BIG_GIVER_BNB=0.5
SOFT_CAP_BNB=5
HARD_CAP_BNB=15
PRESALE_END=2026-11-04T13:40:00+00:00

SHIELD_ENABLED=true
ALLOWED_DOMAINS=spreadlight.io,pinksale.finance,bscscan.com,pancakeswap.finance
ALLOWED_TG=
EXTRA_ALLOWED_ADDRESSES=
PROTECTED_NAMES=kaizenfred

POINTS_ENABLED=true
GAMES_ENABLED=true
ARCADE_URL=
ARCADE_BIND=127.0.0.1
ARCADE_PORT=8080
ARCADE_DAILY_LUMENS=25

CAPTCHA_ENABLED=true
CAPTCHA_TIMEOUT_SEC=180

PROFANITY_FILTER=true
PROFANITY_STRIKES=3
MUTE_MINUTES=60
MARKETER_REROUTE=true

DB_PATH=/opt/homie/app/spreadlight.db
ENVEOF

chmod 600 /opt/homie/app/.env
chown -R homie:homie /opt/homie

# --- sanity-check the token BEFORE starting the bot -------------------------
# (getUpdates conflicts with the bot's own polling, so it has to happen first)
if echo "$BOT_TOKEN" | grep -q 'PASTE_'; then
    log "FATAL: BOT_TOKEN placeholder was never replaced."
    echo "BOT_TOKEN placeholder not replaced" > /opt/homie/SETUP-FAILED.txt
    exit 1
fi

ME=$(curl -s --max-time 20 "https://api.telegram.org/bot${BOT_TOKEN}/getMe" || true)
if ! echo "$ME" | grep -q '"ok":true'; then
    log "FATAL: Telegram rejected the bot token."
    echo "Telegram rejected the bot token" > /opt/homie/SETUP-FAILED.txt
    exit 1
fi
log "bot token accepted by Telegram"

# find any chat that has already talked to the bot, so we can report in
CHAT=$(curl -s --max-time 20 "https://api.telegram.org/bot${BOT_TOKEN}/getUpdates" \
       | tr '{},' '\n' | grep -m1 '"id":-\?[0-9]\{6,\}' \
       | grep -o '\-\?[0-9]\{6,\}' || true)

# --- service ----------------------------------------------------------------
cat > /etc/systemd/system/homie.service <<'SVCEOF'
[Unit]
Description=Homie - SpreadLight community bot
After=network-online.target
Wants=network-online.target
# Restart=always is a lie without this. systemd's default rate limit is 5
# starts in 10s; exceed it and the unit goes to "failed" and is never
# restarted again. A transient crash loop at 3am then leaves the bot dead
# until a human notices. 0 disables the limit: keep retrying, forever.
StartLimitIntervalSec=0

[Service]
User=homie
WorkingDirectory=/opt/homie/app
ExecStart=/opt/homie/app/.venv/bin/python bot.py
Restart=always
RestartSec=10
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable --now homie
sleep 12

if systemctl is-active --quiet homie; then
    log "SUCCESS: homie is running"
    echo ok > /opt/homie/SETUP-OK.txt
    if [ -n "$CHAT" ]; then
        curl -s --max-time 20 -X POST \
          "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
          -d "chat_id=${CHAT}" \
          --data-urlencode "text=setup finished, I'm alive ✨ run /setgroup in the group and then /check" \
          >/dev/null || true
    fi
else
    log "FATAL: service failed to stay up. Last lines:"
    journalctl -u homie -n 30 --no-pager >>"$LOG" 2>&1 || true
    echo "service crashed" > /opt/homie/SETUP-FAILED.txt
fi

ufw allow OpenSSH   >>"$LOG" 2>&1
ufw --force enable  >>"$LOG" 2>&1
dpkg-reconfigure -f noninteractive unattended-upgrades >>"$LOG" 2>&1 || true

# --- scrub the secrets cloud-init logged on its own ------------------------
for f in /var/log/cloud-init-output.log /var/log/cloud-init.log; do
    [ -f "$f" ] && sed -i \
        -e "s|${BOT_TOKEN}|<redacted>|g" \
        -e "s|${ANTHROPIC_API_KEY}|<redacted>|g" "$f" 2>/dev/null || true
    [ -f "$f" ] && chmod 600 "$f"
done
chmod 600 "$LOG"

log "=== Homie setup finished ==="
