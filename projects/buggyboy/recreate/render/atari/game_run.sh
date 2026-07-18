#!/bin/bash
# Play BuggyBoy in Hatari (GUI), for side-by-side comparison of the reconstruction vs the original:
#   game_run.sh              -> the reconstructed game (disk/BUGGY.PRG); run game_build.sh first
#   game_run.sh original     -> the ORIGINAL binary (bin/START.PRG -> BUGGYBOY.PRG), same emulator
#                               setup, so speed/behaviour differences are apples-to-apples
# Both use the same TOS / memory / joystick config. Arrow keys steer / accelerate (emulated
# joystick), space = fire/gear, ESC quits a leg; F1-F5 pick a leg (reconstruction only needs this).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$(cd "$HERE/../../../bin" && pwd)"        # projects/buggyboy/bin (original binary + data)
TOS="$(find /opt/homebrew/Cellar/hatari -name tos.img 2>/dev/null | head -1)"
[ -n "$TOS" ] || { echo "no TOS ROM found under Hatari cellar"; exit 1; }

case "${1:-}" in
  original)
    # Stage the original binary + its data on a throwaway drive and auto-run its START.PRG loader.
    DRIVE="$HERE/disk_orig"
    mkdir -p "$DRIVE"
    cp "$BIN/START.PRG" "$BIN/BUGGYBOY.PRG" "$BIN/COURSES.DAT" "$BIN/GRAPHICS.GRA" "$DRIVE/"
    PRG="START.PRG"
    ;;
  "")
    DRIVE="$HERE/disk"
    PRG="BUGGY.PRG"
    ;;
  *) echo "usage: game_run.sh [original]"; exit 2 ;;
esac

# --joy1 keys maps the arrow keys + a fire key to ST joystick port 1 (the game reads joystick 1).
exec hatari --memsize 4 --monitor rgb --tos-res low --tos "$TOS" \
            --joy1 keys \
            --harddrive "$DRIVE" --auto "C:\\$PRG"
