#!/bin/bash
# Play the reconstructed Flying Shark in the Hatari GUI, or run the ORIGINAL binary in the same
# setup for a side-by-side comparison.
#
#   run.sh            -> disk/ as C:, our AUTO\FLYSHARK.PRG  (build it first: build.sh)
#   run.sh floppy     -> disk/FLYSHARK.ST in drive A:, which is what a real machine gets
#   run.sh original   -> ../bin/disk as C:, the 1988 binary, same TOS and memory
#
# NO --auto ON ANY OF THEM, and that is the whole recipe: TOS's own `\AUTO\` scan runs the program
# before it puts up the desktop. Started from the desktop instead, the ORIGINAL loads high enough
# that its own screen ring lands on top of its loaded music driver and it dies on an illegal
# instruction (../../tools/boot_shots.py has the arithmetic); this build does not have that
# constraint (README.md, "The load-address budget") but is run the same way for comparability.
#
# CONTROLS: joystick 1. `--joy1 keys` binds the cursor keys and right-Ctrl to it, which is what a
# person without a stick plays with — the fire button starts a game from the attract screen and
# drops a bomb in play. P pauses (any stick input resumes), F10 abandons the game, and the keypad's
# 4 arms the cheat entry at the hall of fame. README.md's "What is unpinned" says which of those
# have been exercised and which have not.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REC="$(cd "$HERE/.." && pwd)"
DISK="$HERE/disk"
ROM="${FLYSHARK_TOS_ROM:-$(ls "$REC"/../../../tools/hatari/TOS104US.img 2>/dev/null || true)}"
[ -n "$ROM" ] || { echo "set FLYSHARK_TOS_ROM to a TOS ROM image"; exit 1; }

# 1 MB is the machine the release asks for and the budget README.md measures against; the game and
# this build both fit it. Raise it here if you want to watch the headroom rather than test it.
MEMSIZE=1

case "${1:-ours}" in
  floppy)
    [ -f "$DISK/FLYSHARK.ST" ] || { echo "build it first: bash $HERE/build.sh"; exit 1; }
    exec hatari --confirm-quit off --memsize "$MEMSIZE" --monitor rgb --tos "$ROM" \
         --joy1 keys --disk-a "$DISK/FLYSHARK.ST" ;;
  original)
    exec hatari --confirm-quit off --memsize "$MEMSIZE" --monitor rgb --tos "$ROM" \
         --joy1 keys --harddrive "$REC/../bin/disk" ;;
  ours)
    [ -f "$DISK/AUTO/FLYSHARK.PRG" ] || { echo "build it first: bash $HERE/build.sh"; exit 1; }
    exec hatari --confirm-quit off --memsize "$MEMSIZE" --monitor rgb --tos "$ROM" \
         --joy1 keys --harddrive "$DISK" ;;
  *) echo "usage: run.sh [ours | floppy | original]"; exit 2 ;;
esac
