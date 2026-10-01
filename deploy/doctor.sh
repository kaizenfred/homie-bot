#!/bin/bash
# Why is Homie down, and get him back up.
#
#   cd /opt/homie/app && git pull && bash deploy/doctor.sh
#
# Reports the service state, the real reason it stopped, and whether the
# config is sane — then repairs the two things that are repairable from here
# (the systemd start-limit trap, and a stopped service) and restarts.
#
# It never prints a secret. Keys are reported as present/absent and by shape
# only, so the output is safe to paste back into a chat.
set -uo pipefail          # deliberately not -e: a failing check must not
                          # abort the rest of the report

APP=/opt/homie/app
ENV=${HOMIE_ENV:-$APP/.env}
UNIT=/etc/systemd/system/homie.service

line() { printf '\n──────── %s\n' "$1"; }

line "service"
systemctl is-enabled homie 2>&1 | sed 's/^/  enabled: /'
systemctl is-active  homie 2>&1 | sed 's/^/  active : /'
systemctl show homie -p NRestarts --value 2>/dev/null | sed 's/^/  restarts since boot: /'
systemctl show homie -p ExecMainStartTimestamp --value 2>/dev/null | sed 's/^/  started: /'
systemctl show homie -p Result --value 2>/dev/null | sed 's/^/  last result: /'

# The failure this script exists for.
if systemctl show homie -p Result --value 2>/dev/null | grep -q 'start-limit'; then
    echo
    echo "  >> HIT THE START LIMIT. systemd gave up restarting it."
    echo "     That is the bug this script patches below — it was crashing,"
    echo "     and then it was abandoned. The log section says why it crashed."
fi

line "why it stopped (last 40 lines)"
journalctl -u homie -n 40 --no-pager 2>/dev/null | sed 's/^/  /' \
    || echo "  no journal available"

line "config sanity (no values printed)"
if [ ! -f "$ENV" ]; then
    echo "  MISSING: $ENV — the bot cannot start without it"
else
    getval() { grep "^$1=" "$ENV" 2>/dev/null | head -1 | cut -d= -f2-; }
    report() {
        local k="$1" v; v=$(getval "$k")
        if [ -z "$v" ]; then
            echo "  $k: EMPTY"
        elif echo "$v" | grep -q 'PASTE_'; then
            echo "  $k: STILL A PLACEHOLDER  <-- this breaks startup"
        else
            echo "  $k: set (${#v} chars)"
        fi
    }
    report BOT_TOKEN
    report ANTHROPIC_API_KEY
    echo "  PRESALE_ADDRESS: $(getval PRESALE_ADDRESS)"
    echo "  TOKEN_ADDRESS  : $(getval TOKEN_ADDRESS)"
    echo "  PRESALE_END    : $(getval PRESALE_END)"
    echo "  ARCADE_URL     : $(getval ARCADE_URL)"
    echo "  MAIN_CHAT_ID   : $(getval MAIN_CHAT_ID)   (blank is fine — /setgroup stores it in the db)"
fi

line "telegram"
TOKEN=$(grep '^BOT_TOKEN=' "$ENV" 2>/dev/null | head -1 | cut -d= -f2-)
if [ -n "${TOKEN:-}" ] && ! echo "$TOKEN" | grep -q 'PASTE_'; then
    # getMe is safe while the bot is stopped. Do NOT call getUpdates here:
    # it would steal the update queue from a running bot.
    ME=$(curl -s --max-time 15 "https://api.telegram.org/bot${TOKEN}/getMe")
    if echo "$ME" | grep -q '"ok":true'; then
        echo "  token accepted, bot is @$(echo "$ME" | grep -o '"username":"[^"]*"' | cut -d'"' -f4)"
    else
        echo "  TELEGRAM REJECTED THE TOKEN — revoked, or wrong value in .env"
    fi
else
    echo "  skipped (no usable token in .env)"
fi

line "machine"
echo "  uptime:$(uptime -p 2>/dev/null | sed 's/^up//')"
free -m 2>/dev/null | awk '/Mem:/{printf "  memory: %sMB used of %sMB\n",$3,$2}'
df -h / 2>/dev/null | awk 'NR==2{printf "  disk  : %s used of %s (%s)\n",$3,$2,$5}'
# An OOM kill is invisible in the service log but obvious here.
if dmesg 2>/dev/null | grep -qi 'killed process.*python'; then
    echo "  >> the kernel OOM-killed a python process at some point"
fi

line "repair"
# Running git as root in a homie-owned repo fails with "dubious ownership"
# and the pull silently does nothing. Set once, here, so every later update
# works from a root shell.
git config --global --add safe.directory "$APP" 2>/dev/null || true
# A previous root-run pull may have left files root-owned in a tree the
# service user has to write to.
chown -R homie:homie "$APP" 2>/dev/null || true
chmod 600 "$ENV" 2>/dev/null || true

if grep -q 'StartLimitIntervalSec=0' "$UNIT" 2>/dev/null; then
    echo "  unit already has the start-limit fix"
else
    echo "  patching the unit so a crash loop can never strand it again"
    # Insert into [Unit], which is where systemd reads this directive.
    sed -i '/^\[Unit\]/a StartLimitIntervalSec=0' "$UNIT"
    systemctl daemon-reload
fi

systemctl reset-failed homie 2>/dev/null || true
systemctl enable homie >/dev/null 2>&1 || true
systemctl restart homie
sleep 10

line "result"
if systemctl is-active --quiet homie; then
    echo "  homie is RUNNING"
    echo
    echo "  test it in the group:  /id@SpreadLightBot"
    echo "  then just:             homie you there?"
else
    echo "  homie is STILL DOWN. The crash reason is in the log section above —"
    echo "  the last few lines before it died are the ones that matter."
    echo "  Live view:  journalctl -u homie -f"
fi
echo
