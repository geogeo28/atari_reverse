#!/bin/bash
# Watch a demo interactively: launch Hatari (GUI) auto-running the demo .PRG. Press a key in the
# emulator to exit the demo. Run build.sh <screen> first. For headless verification use run_hatari.py.
#   run.sh [leg|results|highscore]   (default: leg)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
case "${1:-leg}" in
  leg)       PRG="DEMO.PRG" ;;
  results)   PRG="RESULTS.PRG" ;;
  highscore) PRG="HIGHSCORE.PRG" ;;
  *) echo "usage: run.sh [leg|results|highscore]"; exit 2 ;;
esac
TOS="$(find /opt/homebrew/Cellar/hatari -name tos.img 2>/dev/null | head -1)"
exec hatari --memsize 4 --monitor rgb --tos-res low --tos "$TOS" \
            --harddrive "$HERE/disk" --auto "C:\\$PRG"
