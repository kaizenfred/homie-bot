#!/bin/bash
# =============================================================================
#  HOMIE — Hetzner first-boot setup
#
#  Paste this whole file into the "Cloud config" / "User data" box on the
#  Hetzner server-creation screen, BEFORE clicking Create.
#
#  Fill in the four values in the CONFIG block below first.
#  Everything after that runs by itself on first boot (about 2 minutes).
#
#  Progress log, if you ever need it:  /var/log/homie-setup.log
# =============================================================================

# ----------------------------- CONFIG: EDIT THESE ----------------------------

REPO_URL="https://github.com/YOURNAME/homie-bot.git"   # your GitHub repo
BOT_TOKEN="PASTE_BOTFATHER_TOKEN_HERE"                 # BotFather -> /mybots
ANTHROPIC_API_KEY="PASTE_ANTHROPIC_KEY_HERE"           # console.anthropic.com
ETHERSCAN_API_KEY=""                                   # optional, see note

# Leave ETHERSCAN_API_KEY empty and the bot reads the chain over a public
# BSC node instead. No key needed, slightly heavier, works fine.

# ------------------------- nothing below needs editing -----------------------

set -x
exec > >(tee -a /var/log/homie-setup.log) 2>&1
echo "=== Homie setup starting $(date -u) ==="

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git ufw unattended-upgrades

# a plain service account — the bot never needs root
id homie >/dev/null 2>&1 || useradd --system --create-home --home-dir /opt/homie --shell /usr/sbin/nologin homie

# code
rm -rf /opt/homie/app
git clone --depth 1 "$REPO_URL" /opt/homie/app
cd /opt/homie/app

python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

# config
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

PRESALE_ADDRESS=0x9cC488396E4973Bf341191Eb6196a1220CdB2E3A
TOKEN_ADDRESS=0x975FfA9d75d4FdfC34B14e6bF5C67eF85fDE3aD9
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
PRESALE_END=2026-11-04T15:00:00-05:00

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

# service
cat > /etc/systemd/system/homie.service <<'SVCEOF'
[Unit]
Description=Homie - SpreadLight community bot
After=network-online.target
Wants=network-online.target

[Service]
User=homie
WorkingDirectory=/opt/homie/app
ExecStart=/opt/homie/app/.venv/bin/python bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# modest hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable --now homie

# only SSH in; the bot makes outbound connections only
ufw allow OpenSSH
ufw --force enable

# security patches apply themselves
dpkg-reconfigure -f noninteractive unattended-upgrades

sleep 8
systemctl --no-pager status homie | head -20
echo "=== Homie setup finished $(date -u) ==="
