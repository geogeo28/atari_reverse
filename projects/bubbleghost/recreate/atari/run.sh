#!/bin/bash
# Launch the `play` build with a screen, a mouse and sound, for a person rather than for a check.
#
#   bash atari/build.sh play && bash atari/run.sh
#
# WHAT IT IS. `play` composes every verified slice of the program in the original's own order — the
# boot, the presentation and its speech, the menu with its blocking key reads, the room loop, the
# two end-of-room animations and the hall of fame — with no anchor and no frame budget, so it runs
# until the window is closed.
#
# IT IS ALSO THE DISCHARGE FOR THE INPUT PATH NO CHECK CAN EXERCISE, and for this game that is most
# of the input. Hatari's headless control protocol has SIX events — a double-click, the two right
# mouse buttons and three key events — and NO MOUSE MOTION of any kind: the pointer's position comes
# only from real host events, which do not exist under a dummy video driver. Bubble Ghost is played
# by moving the mouse (the ghost follows it) and blowing with a shift key, so `smoke.py` can judge
# the menu and the boot and CANNOT play the game at all. Under this script the mouse is a real one.
#
#   the mouse       moves the ghost; the game reads it through the VDI's `vq_mouse`
#   either shift    blows a puff of air (`vq_key_s` — the one gameplay input a headless run CAN
#                   press, because it is a key)
#   G / P / D / H   the menu, and 1 or 2 for the player count
#   ^S / ^R / ^P    sound toggle, restart and pause, which `game_frame_update`'s own poll reads
#
# The machine matches `smoke.py`'s exactly, bar the display and the sound: the numbers a person sees
# have to come from the configuration the checks were made on. The memory size is SCRAPED from
# build.sh rather than retyped — it is the one machine setting this build cannot get wrong quietly,
# because too little and the 664 KiB image has no room (CLAUDE.md §5).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
TOS="$REPO/tools/hatari/TOS104US.img"
PRG="$HERE/build/BUBBLE-play.PRG"

[ -f "$PRG" ] || { echo "no $PRG — run \`bash $HERE/build.sh play\` first"; exit 1; }
[ -f "$TOS" ] || { echo "no TOS ROM at $TOS"; exit 1; }
[ -f "$HERE/disk/GHOST.ST" ] || { echo "no $HERE/disk/GHOST.ST — run build.sh first"; exit 1; }
cp "$PRG" "$HERE/disk/c/BUBBLE.PRG"

MEMSIZE_MB=$(sed -n 's/^MEMSIZE_MB=\([0-9][0-9]*\).*/\1/p' "$HERE/build.sh")
[ -n "$MEMSIZE_MB" ] || { echo "no MEMSIZE_MB in $HERE/build.sh — the two would disagree"; exit 1; }

SOUND_HZ=44100

# A: is the game's own data volume and is not optional: three of the six files are opened as
# "A:GHOST.xxx" by the program itself (atari/build.sh's staging note).
exec hatari --tos "$TOS" --machine st --memsize "$MEMSIZE_MB" --monitor rgb --tos-res low \
     --confirm-quit off --statusbar off --drive-led off --frameskips 0 \
     --sound "$SOUND_HZ" --zoom 2 \
     --disk-a "$HERE/disk/GHOST.ST" \
     --harddrive "$HERE/disk/c" --auto 'C:\BUBBLE.PRG'
