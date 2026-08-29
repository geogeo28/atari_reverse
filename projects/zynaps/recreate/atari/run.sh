#!/bin/bash
# Launch the `play` build with a screen and sound, for a person rather than for a check.
#
#   bash atari/build.sh play && bash atari/run.sh
#
# WHAT IT IS. The title picture the reconstruction drew, with the title tune ticking off the
# reconstruction's own vertical-blank handler, running until the window is closed. M1 HAS NO INPUT
# PATH — nothing reads the keyboard or the joystick, because the routine that would
# (`title_attract_loop` @ 0x12ac2) is unported and blocked on the same ACIA wall as `ikbd_send_cmd`
# (../STATUS.md). So there is nothing to press. Close the window to stop it.
#
# The machine matches `smoke.py`'s exactly, bar the display and the sound: the numbers a person
# hears have to come from the configuration the checks were made on. See README.md's "The machine".
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
TOS="$REPO/tools/hatari/TOS104US.img"
PRG="$HERE/build/ZYNAPS-play.PRG"

[ -f "$PRG" ] || { echo "no $PRG — run \`bash $HERE/build.sh play\` first"; exit 1; }
[ -f "$TOS" ] || { echo "no TOS ROM at $TOS"; exit 1; }
cp "$PRG" "$HERE/disk/ZYNAPS.PRG"

# THE MEMORY SIZE IS SCRAPED FROM smoke.py, not retyped. It is the one machine setting this build
# cannot get wrong quietly: too little and the 1 MiB image has no room, and a person playing on a
# different machine from the one the checks were made on is comparing nothing. One canonical
# definition, read across the language boundary (CLAUDE.md §5) — everything else on the line below
# is display and sound, which smoke.py deliberately does not have.
MEMSIZE_MB=$(sed -n 's/^MEMSIZE_MB *= *\([0-9][0-9]*\).*/\1/p' "$HERE/smoke.py")
[ -n "$MEMSIZE_MB" ] || { echo "no MEMSIZE_MB in $HERE/smoke.py — the two would disagree"; exit 1; }

SOUND_HZ=44100

exec hatari --tos "$TOS" --machine st --memsize "$MEMSIZE_MB" --monitor rgb \
     --confirm-quit off --statusbar off --drive-led off --frameskips 0 \
     --sound "$SOUND_HZ" --zoom 2 \
     --harddrive "$HERE/disk" --auto 'C:\ZYNAPS.PRG'
