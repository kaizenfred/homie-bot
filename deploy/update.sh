#!/bin/bash
# The correct way to update a running Homie.
#
#   bash /opt/homie/app/deploy/update.sh
#
# Three things go wrong doing this by hand as root, and this handles all of
# them:
#
#   1. The repo belongs to the `homie` service user, so git run as root
#      refuses with "detected dubious ownership" and does nothing.
#   2. A pull that does work leaves the new files owned by root, inside a
#      tree the service user has to write to.
#   3. .env is gitignored, so a pull never carries config changes — a new
#      setting has to be added to .env separately, and silently isn't.
set -euo pipefail

APP=/opt/homie/app
cd "$APP"

echo "==> allowing root to use this repo"
git config --global --add safe.directory "$APP" 2>/dev/null || true

echo "==> pulling"
BEFORE=$(git rev-parse --short HEAD)
git pull --ff-only
AFTER=$(git rev-parse --short HEAD)
if [ "$BEFORE" = "$AFTER" ]; then
    echo "    already current at $AFTER"
else
    echo "    $BEFORE -> $AFTER"
    git log --oneline "$BEFORE..$AFTER" | sed 's/^/      /'
fi

echo "==> installing dependencies"
# A pull can bring a new import with it. Without this the bot comes back up
# crashing on ModuleNotFoundError, which looks like a broken deploy rather
# than a missing package — and the restart loop hides the real reason.
if ! ./.venv/bin/pip install -q -r requirements.txt 2>&1 | tail -5; then
    echo "    pip failed — the bot may not start. Output above."
fi
./.venv/bin/python -c "
import importlib, sys
missing = [m for m in ('telegram', 'httpx', 'dotenv', 'anthropic', 'aiohttp', 'PIL')
           if not importlib.util.find_spec(m)]
print('    all imports present' if not missing
      else '    STILL MISSING: ' + ', '.join(missing))
"

echo "==> restoring ownership"
# .env keeps its 600; everything else just needs to belong to the service user
chown -R homie:homie "$APP"
chmod 600 "$APP/.env" 2>/dev/null || true

echo "==> checking for new settings in env.example"
# A new feature usually adds a key. The pull brings env.example but never
# .env, so without this check a new setting sits unset and the feature
# quietly does nothing.
MISSING=""
while IFS= read -r key; do
    grep -q "^${key}=" "$APP/.env" 2>/dev/null || MISSING="$MISSING $key"
done < <(grep -oE '^[A-Z_]+=' "$APP/env.example" 2>/dev/null | tr -d '=')
if [ -n "$MISSING" ]; then
    echo "    these exist in env.example but not in your .env:"
    for k in $MISSING; do echo "      $k"; done
    echo "    (defaults apply, but set them if you want to change them)"
else
    echo "    .env has every key env.example knows about"
fi

echo "==> restarting"
systemctl restart homie
sleep 8

if systemctl is-active --quiet homie; then
    echo
    echo "homie is running on $AFTER"
    echo "test in the group:  homie you there?"
else
    echo
    echo "homie did NOT come back up. Why:"
    journalctl -u homie -n 25 --no-pager | sed 's/^/  /'
    echo
    echo "Full diagnosis:  bash $APP/deploy/doctor.sh"
fi
