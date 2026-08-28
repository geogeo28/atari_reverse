#!/bin/bash
# Play Zynaps (Hewson, 1988) in the Hatari GUI -- a window, sound, joystick on the keyboard.
#
#   play.sh              -> the FAITHFUL disk: gw/dumps/zynaps/zynaps.stx, protection tracks intact
#   play.sh st           -> bin/zynaps.st, the patched raw sector image (no protection tracks)
#   play.sh gemdos       -> bin/disk/ as drive C:, auto-running C:\AUTO\ZYNAPS17.PRG (no floppy)
#   play.sh headless [stx|st|gemdos] [--tos 102|104] [--tos-rom PATH] [--out DIR]
#                        -> no window: boot, drive the front end, and photograph into out/boot/
#
# Everything after the mode is forwarded to tools/boot_shots.py, which OWNS the Hatari command line:
# the media matrix, the TOS ROM, the machine and the memory size all live there and this script asks
# for them with `--print-command`.  Keeping two copies is what let them drift three ways -- the gold
# master mounted writable in one and write-protected in the other among them.
#
# All three media reach the game (out/boot/, and README.md "Boot results"); the .stx is the default
# because it is the only one that is a faithful copy of the user's disk.
#
# CONTROLS: the game is JOYSTICK PORT 1, emulated on the keyboard by `--joy1 keys` (F12 ->
# Joysticks -> port 1 -> Define keys to rebind).  Its front end also takes the keyboard directly:
#   SPACE   step to the next front-end page      1  one-player game      2  two-player game
# Ctrl-Q quits Hatari.
#
# TOS: the two FLOPPY media run identically on TOS 1.02 and 1.04 (both measured); `gemdos` needs
# 1.04, because Hatari refuses directory emulation below it.  ZYN_TOS_ROM=/path/to/tos.img boots a
# different ROM, and the driver reads its version word to tag the files a headless run writes.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DRIVER="$HERE/tools/boot_shots.py"

MODE="${1:-stx}"
shift || true

TOS_ARGS=()
if [ -n "${ZYN_TOS_ROM:-}" ]; then TOS_ARGS=(--tos-rom "$ZYN_TOS_ROM"); fi

if [ "$MODE" = headless ]; then
  HEADLESS_MODE="${1:-stx}"
  shift || true
  exec python3 "$DRIVER" "$HEADLESS_MODE" ${TOS_ARGS[@]+"${TOS_ARGS[@]}"} "$@"
fi

# One argument per line, so a path with a space in it survives the trip back.  `mapfile` would say
# this in one line and does not exist in the bash 3.2 that ships with macOS.
ARGS=()
while IFS= read -r argument; do
  ARGS+=("$argument")
done < <(python3 "$DRIVER" "$MODE" --print-command ${TOS_ARGS[@]+"${TOS_ARGS[@]}"} "$@")

if [ ${#ARGS[@]} -eq 0 ]; then
  echo "error: $DRIVER produced no command line for mode '$MODE'" >&2
  exit 1
fi
exec "${ARGS[@]}"
