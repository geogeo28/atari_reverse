#!/bin/bash
# Play BuggyBoy: launch Hatari (GUI) auto-running the reconstructed game .PRG. Arrow keys steer /
# accelerate (emulated joystick), space = fire/gear, ESC quits a leg. Run game_build.sh first.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TOS="$(find /opt/homebrew/Cellar/hatari -name tos.img 2>/dev/null | head -1)"
[ -n "$TOS" ] || { echo "no TOS ROM found under Hatari cellar"; exit 1; }
# --joy1 keys maps the arrow keys + a fire key to ST joystick port 1 (the game reads joystick 1).
exec hatari --memsize 4 --monitor rgb --tos-res low --tos "$TOS" \
            --joy1 keys \
            --harddrive "$HERE/disk" --auto "C:\\BUGGY.PRG"
