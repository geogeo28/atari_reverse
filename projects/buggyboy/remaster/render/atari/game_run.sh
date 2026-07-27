#!/bin/bash
# Play BuggyBoy in Hatari (GUI), for side-by-side comparison of the remaster vs the original:
#   game_run.sh              -> the remaster (disk/BUGGYBOY.PRG); run build_game.sh first
#   game_run.sh original     -> the ORIGINAL binary (bin/START.PRG -> BUGGYBOY.PRG), same emulator
#                               setup, so speed/behaviour differences are apples-to-apples
# Same pattern as recreate/render/atari/game_run.sh (the reconstruction's launcher). Both arms use the
# same TOS / memory / joystick config. Arrow keys steer / accelerate (emulated joystick), space =
# fire/gear, ESC quits a leg; the remaster also takes F1-F5 to pick a leg and its extra keys — see
# README.md's key table. To play the remaster's STE blitter build, add --machine ste by hand (the same
# .PRG binds the blitter at boot; the original never uses it, so its arm has no STE variant).
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
    PRG="BUGGYBOY.PRG"
    ;;
  *) echo "usage: game_run.sh [original]"; exit 2 ;;
esac

# --joy1 keys maps the arrow keys + a fire key to ST joystick port 1 (both games read joystick 1).
exec hatari --memsize 4 --monitor rgb --tos-res low --tos "$TOS" \
            --joy1 keys \
            --harddrive "$DRIVE" --auto "C:\\$PRG"
