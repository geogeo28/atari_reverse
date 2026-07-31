#!/bin/bash
# Play the reconstructed Joust in the Hatari GUI, or run the ORIGINAL binary in the same setup for a
# side-by-side comparison.
#
#   run.sh            -> disk/JOUST.PRG   (build it first: build.sh)
#   run.sh original   -> the shipped ../../bin/JOUST.PRG, same TOS/memsize/joystick wiring
#
# Keys: '1' / '2' on the title screen pick a one- or two-player game (or press fire). In play, the
# cursor keys + right-Ctrl are joystick 1 (--joy1 keys). See README.md for what does NOT work yet.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REC="$(cd "$HERE/.." && pwd)"
DISK="$HERE/disk"
ROM="${JOUST_TOS_ROM:-$(ls "$REC"/../../../tools/hatari/TOS104US.img 2>/dev/null || true)}"
[ -n "$ROM" ] || { echo "set JOUST_TOS_ROM to a TOS ROM image"; exit 1; }

if [ "${1:-}" = "original" ]; then
  DRIVE="$HERE/disk_orig"; PRG="JOUST.PRG"
  mkdir -p "$DRIVE"
  cp "$REC/../bin/JOUST.PRG" "$REC/../bin/HIGH.SCO" "$DRIVE/"
else
  DRIVE="$DISK"; PRG="JOUST.PRG"
  [ -f "$DRIVE/$PRG" ] || { echo "build it first: bash $HERE/build.sh"; exit 1; }
fi

exec hatari --confirm-quit off --memsize 4 --monitor rgb --tos-res low --tos "$ROM" \
     --joy1 keys --harddrive "$DRIVE" --auto "C:\\$PRG"
