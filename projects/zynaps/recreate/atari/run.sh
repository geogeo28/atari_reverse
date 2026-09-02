#!/bin/bash
# Launch the `play` build with a screen and sound, for a person rather than for a check.
#
#   bash atari/build.sh play && bash atari/run.sh
#
# WHAT IT IS, AND IT IS THE WHOLE GAME NOW. `play` composes every verified slice of the program in
# the original's own order — the boot, the attract loop with its colour bars, the section chain, the
# frame loop and the endings — with no frame budget and no anchor, so it runs until the window is
# closed.
#
# IT IS ALSO THE DISCHARGE FOR THE ONE INPUT PATH NO CHECK CAN EXERCISE. Hatari swallows a key bound
# to its keyboard-as-joystick emulation, so a headless run cannot press the stick at all and
# `smoke.py game` pokes the byte the IKBD handler writes instead (docs/on-target-execution.md class
# 12). Under this script the stick is a REAL one — `--joystick 1` is Hatari's own documented
# "emulate joystick with cursor keys in given port", and PORT 1 is the one the game reads
# (`A_joystick_state` is the SECOND byte of the 6301's report; ../include/irq.h says so) — so the
# whole path from a key to a 6301 report to `ikbd_acia_isr` to the byte the game polls is exercised
# by a person and by nothing else.
#
#   cursor keys   move the ship
#   fire          whatever Hatari's Joystick dialog shows for port 1; its own `--joystick` help says
#                 only "cursor keys", so the fire key is READ OFF THAT DIALOG rather than asserted
#                 here — this file has not measured it and will not claim it.
#   1 / 2         one or two players, at the attract screen; those go through the KEYBOARD, which
#                 the same `ikbd_acia_isr` files, and are the half a headless run can press.
#
#
# The machine matches `smoke.py`'s exactly, bar the display and the sound: the numbers a person
# hears have to come from the configuration the checks were made on. See README.md's "Memory".
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
TOS="$REPO/tools/hatari/TOS104US.img"
PRG="$HERE/build/ZYNAPS-play.PRG"

[ -f "$PRG" ] || { echo "no $PRG — run \`bash $HERE/build.sh play\` first"; exit 1; }
[ -f "$TOS" ] || { echo "no TOS ROM at $TOS"; exit 1; }
cp "$PRG" "$HERE/disk/ZYNAPS.PRG"

# THE MEMORY SIZE IS SCRAPED FROM smoke.py, not retyped. It is the one machine setting this build
# cannot get wrong quietly: too little and the 512 KiB image has no room, and a person playing on a
# different machine from the one the checks were made on is comparing nothing. It is 1 MB since the
# diet — the machine Zynaps shipped on the generation of, and the size the whole smoke matrix is
# judged at (atari/README.md's "Memory"). One definition, read across the language boundary
# (CLAUDE.md §5) — everything else on the line below is display and sound, which smoke.py
# deliberately does not have.
#
# WHAT IS SCRAPED IS THE DEFAULT, and `smoke.py --memsize N` can be run against another size. That
# is deliberate — the matrix runs at 1 MB and 4 MB precisely to show the cadence does not depend on
# it — but it means this line tracks the size the checks are judged at, not every size they have
# been run at.
MEMSIZE_MB=$(sed -n 's/^MEMSIZE_MB *= *\([0-9][0-9]*\).*/\1/p' "$HERE/smoke.py")
[ -n "$MEMSIZE_MB" ] || { echo "no MEMSIZE_MB in $HERE/smoke.py — the two would disagree"; exit 1; }

SOUND_HZ=44100

# `--joystick 1` is the whole of the input path this script exists for; see the note at the top.
exec hatari --tos "$TOS" --machine st --memsize "$MEMSIZE_MB" --monitor rgb \
     --confirm-quit off --statusbar off --drive-led off --frameskips 0 \
     --sound "$SOUND_HZ" --zoom 2 --joystick 1 \
     --harddrive "$HERE/disk" --auto 'C:\ZYNAPS.PRG'
