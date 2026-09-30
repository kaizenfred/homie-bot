#!/bin/bash
# Turns the arcade on. Run it ON THE SERVER, after the DNS A record exists:
#
#   cd /opt/homie/app && git pull && bash deploy/setup-arcade.sh play.spreadlight.io
#
# What it does:
#   1. checks the domain actually points at this server (Caddy cannot get a
#      certificate before it does, and the failure it gives you otherwise is
#      not obvious)
#   2. opens 80 and 443 — the installer enables UFW with only SSH open, so
#      without this the certificate challenge never reaches the box
#   3. installs Caddy and points the domain at the arcade on 127.0.0.1:8080
#   4. sets ARCADE_URL in .env, which is the switch that turns /play on
#
# Safe to re-run: every step sets a value or is a no-op the second time.
set -euo pipefail

DOMAIN="${1:-}"
if [ -z "$DOMAIN" ]; then
    echo "usage: bash deploy/setup-arcade.sh <domain>"
    echo "   eg: bash deploy/setup-arcade.sh play.spreadlight.io"
    exit 1
fi

ENV=${HOMIE_ENV:-/opt/homie/app/.env}
[ -f "$ENV" ] || { echo "no .env at $ENV — is Homie installed here?"; exit 1; }

echo "==> checking DNS for $DOMAIN"
apt-get install -y dnsutils curl >/dev/null 2>&1 || true
MY_IP=$(curl -s --max-time 10 https://api.ipify.org || true)
DNS_IP=$(dig +short "$DOMAIN" A | tail -n1 || true)

if [ -z "$DNS_IP" ]; then
    echo "FAIL: $DOMAIN does not resolve yet."
    echo "      Add an A record for it pointing at ${MY_IP:-this server}, wait a"
    echo "      few minutes, then run this again. Nothing has been changed."
    exit 1
fi
if [ -n "$MY_IP" ] && [ "$DNS_IP" != "$MY_IP" ]; then
    echo "FAIL: $DOMAIN resolves to $DNS_IP but this server is $MY_IP."
    echo "      Fix the A record, wait for it to propagate, then run this again."
    echo "      Nothing has been changed."
    exit 1
fi
echo "    ok — $DOMAIN -> $DNS_IP"

echo "==> opening ports 80 and 443"
# Without this the ACME HTTP challenge is dropped by the firewall and Caddy
# retries forever with a misleading timeout.
ufw allow 80/tcp  >/dev/null 2>&1 || true
ufw allow 443/tcp >/dev/null 2>&1 || true

echo "==> installing Caddy"
if ! command -v caddy >/dev/null 2>&1; then
    apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl >/dev/null 2>&1
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
        > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -y >/dev/null 2>&1
    apt-get install -y caddy >/dev/null 2>&1
fi
caddy version

echo "==> writing Caddyfile"
# Everything goes to the arcade: /arcade/*.html for the games, /score for
# submissions (sl.js posts to ../score, which resolves to /score), /health.
cat > /etc/caddy/Caddyfile <<CADDYEOF
${DOMAIN} {
    encode gzip
    reverse_proxy 127.0.0.1:8080
}
CADDYEOF

systemctl reload caddy 2>/dev/null || systemctl restart caddy
sleep 3

echo "==> setting ARCADE_URL"
URL="https://${DOMAIN}"
if grep -q '^ARCADE_URL=' "$ENV"; then
    sed -i "s|^ARCADE_URL=.*|ARCADE_URL=${URL}|" "$ENV"
else
    printf 'ARCADE_URL=%s\n' "$URL" >> "$ENV"
fi
chown homie:homie "$ENV" 2>/dev/null || true
chmod 600 "$ENV"

systemctl restart homie
sleep 8

echo
echo "==> checking it actually serves"
LOCAL=$(curl -s --max-time 10 http://127.0.0.1:8080/health || echo FAILED)
echo "    local  : $LOCAL"
PUBLIC=$(curl -s --max-time 30 "${URL}/health" || echo FAILED)
echo "    public : $PUBLIC"
echo

if [ "$PUBLIC" = "ok" ]; then
    echo "arcade is live at ${URL}"
    echo
    echo "LAST STEP — in BotFather, /newgame three times."
    echo "The short names must match EXACTLY or /play will error:"
    echo "    shadowwave    (title: Shadow Wave)"
    echo "    lumenrun      (title: Lumen Run)"
    echo "    lightrally    (title: Light Rally)"
    echo "BotFather asks for a title, a description and a 640x360 photo each."
    echo "Then run /play in the group."
else
    echo "The public check did not come back 'ok'."
    echo "If local said 'ok', the bot is fine and it is Caddy or DNS:"
    echo "    systemctl status caddy"
    echo "    journalctl -u caddy -n 40 --no-pager"
    echo "A certificate can take a minute on first issue — try ${URL}/health again."
fi
