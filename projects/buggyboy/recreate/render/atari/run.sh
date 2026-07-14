#!/bin/bash
# Watch the demo interactively: launch Hatari (GUI) auto-running DEMO.PRG. Press a key in the
# emulator to exit the demo. Run build.sh first. For headless verification use run_hatari.py.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TOS="$(find /opt/homebrew/Cellar/hatari -name tos.img 2>/dev/null | head -1)"
exec hatari --memsize 4 --monitor rgb --tos-res low --tos "$TOS" \
            --harddrive "$HERE/disk" --auto 'C:\DEMO.PRG'
