#!/bin/bash
# Play BLACK ICE in the Hatari GUI from the bootable floppy image — a window, sound, joystick on the keys.
#
#   run.sh              -> boots disk/BLACKICE.ST (built by `make` if missing) on an STE with 1 MB
#   run.sh gemdos       -> the same program from the GEMDOS drive disk/ instead of the floppy image
#   run.sh parsecheck   -> print the exact Hatari command line and let Hatari parse it without booting
#
# CONTROLS (joystick port 1 is emulated on the keyboard by Hatari's `--joy1 keys`):
#   cursor keys   move / turn        Right-Ctrl   fire   (F12 -> Joysticks -> port 1 -> Define keys to rebind:
#   Shift + left/right   strafe                           most Mac keyboards have no Right-Ctrl)
#   Z / X         strafe             1 / 2        weapon      7 / 8 / 9   throttle      P   pause
#   Space         fire (keyboard)    Esc          quit to the desktop        Ctrl-Q   quit Hatari
#
# `--country uk` boots EmuTOS as a PAL machine: at its default country it comes up 60 Hz, the 25 Hz
# simulation then ticks at 30 Hz and the music plays a fifth sharp (atari/README.md, fault 10).
# The title screen waits for fire. The ROM is Hatari's bundled EmuTOS (TOS 1.0x in tools/hatari has no
# STE support); set BI_TOS_ROM=/path/to/tos162.img to boot a real STE TOS instead.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-floppy}"
IMAGE="$HERE/disk/BLACKICE.ST"

[ -f "$IMAGE" ] || make -C "$HERE" "disk/BLACKICE.ST"

case "$MODE" in
  floppy|parsecheck) MEDIA=(--disk-a "$IMAGE" --protect-floppy off) ;;
  gemdos)            MEDIA=(--harddrive "$HERE/disk" --auto BLACKICE.PRG) ;;
  *) echo "usage: run.sh [floppy|gemdos|parsecheck]" >&2; exit 2 ;;
esac

ARGS=(--machine ste --memsize 1 --country uk --monitor rgb --sound 44100 --joy1 keys --confirm-quit off
      --statusbar off --drive-led off --frameskips 0 --zoom 2 "${MEDIA[@]}")
[ -n "${BI_TOS_ROM:-}" ] && ARGS=(--tos "$BI_TOS_ROM" "${ARGS[@]}")

if [ "$MODE" = parsecheck ]; then
  # --help makes Hatari parse every option before it and stop without booting; it exits 1 either way,
  # so the verdict is the text: an unknown or malformed option prints an error naming it.
  echo "hatari ${ARGS[*]}"
  if hatari "${ARGS[@]}" --help 2>&1 | grep -i -E "unknown|error|invalid" ; then exit 1; fi
  echo "parse ok"; exit 0
fi
exec hatari "${ARGS[@]}"
