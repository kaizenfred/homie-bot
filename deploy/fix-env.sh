#!/bin/bash
# Repoints an already-running Homie at the correct presale pool.
#
#   cd /opt/homie/app && git pull && bash deploy/fix-env.sh && systemctl restart homie
#
# .env is gitignored, so `git pull` can never fix it — it is written once at
# install time and then owned by the server. This patches the three lines that
# were wrong, and only those. Secrets in .env are left untouched.
#
# Safe to run twice: it sets values rather than swapping them, so a second run
# is a no-op rather than putting the addresses back the wrong way round.
set -euo pipefail

ENV=${HOMIE_ENV:-/opt/homie/app/.env}   # overridable so this can be tested
[ -f "$ENV" ] || { echo "no .env at $ENV — is Homie installed here?"; exit 1; }

# From the PinkSale page's own Pool Info / Token panels.
POOL=0x975FfA9d75d4FdfC34B14e6bF5C67eF85fDE3aD9   # holds contributed BNB
TOKEN=0x9cC488396E4973Bf341191Eb6196a1220CdB2E3A  # $LIGHT — never receives BNB
END=2026-11-04T13:40:00+00:00                     # End Time, 13:40 UTC

cp -a "$ENV" "$ENV.bak.$(date -u +%Y%m%d%H%M%S)"

set_key() {
    local key="$1" val="$2"
    if grep -q "^${key}=" "$ENV"; then
        # `|` as the delimiter: the values contain no pipes, but PRESALE_URL
        # nearby contains slashes.
        sed -i "s|^${key}=.*|${key}=${val}|" "$ENV"
    else
        printf '%s=%s\n' "$key" "$val" >> "$ENV"
    fi
}

set_key PRESALE_ADDRESS "$POOL"
set_key TOKEN_ADDRESS   "$TOKEN"
set_key PRESALE_END     "$END"

chown homie:homie "$ENV" 2>/dev/null || true
chmod 600 "$ENV"

echo "patched. .env now says:"
grep -E '^(PRESALE_ADDRESS|TOKEN_ADDRESS|PRESALE_END|PRESALE_URL)=' "$ENV"
echo
echo "now run:  systemctl restart homie"
echo "then in the group:  /check   (expect ~1.5 BNB, not 0.0000)"
