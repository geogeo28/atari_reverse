#!/bin/bash
# Watch the remaster HUD demo in the Hatari GUI (press a key in the emulated ST to exit).
#   run.sh          # build.sh must have run first
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REMASTER="$(cd "$HERE/../.." && pwd)"
PY="$REMASTER/../recreate/.venv/bin/python"; [ -x "$PY" ] || PY=python3

read -r HATARI ROM < <("$PY" -c "
import sys; sys.path.insert(0, '$REMASTER/../recreate/oracle')
import tos_probe; print(tos_probe.find_hatari(), tos_probe.find_tos_rom())")
[ -n "$HATARI" ] && [ -n "$ROM" ] || { echo 'Hatari or TOS ROM not found (brew install hatari)'; exit 1; }

exec "$HATARI" --confirm-quit off --memsize 4 --monitor rgb --tos-res low \
     --tos "$ROM" --harddrive "$HERE/disk" --auto 'C:\HUD.PRG'
