#!/bin/bash
# Play the reconstructed Wonder Boy in the Hatari GUI — a window, sound, and a joystick.
#
#   run.sh              -> disk/WB.PRG, the PLAY build (built for you if it is missing)
#   run.sh rebuild      -> force `build.sh play` first
#   run.sh parsecheck   -> print the exact command below and PARSE it, without opening a machine
#
# THE EXEC LINE AT THE BOTTOM IS THE ONE COMMAND NO HEADLESS CHECK RUNS, and that cost a person a
# broken launch: `--sound on` sat there through thirteen green smoke modes and is rejected by
# Hatari's own parser, which takes a FREQUENCY (off, or 6000-50066). `parsecheck` is the cheap fix —
# it builds the identical argument list and hands it to Hatari with `--help` appended, which parses
# every option before it and then stops without booting anything. `smoke.py runsh` is that check with
# a control on top: it re-runs the same line with the rejected value put back and requires a refusal.
#
# CONTROLS. The game reads joystick 1 and nothing else (`WB_JOY1_STATE`; the IKBD `$ff` report
# header, wonderboy_main.c's ACIA handler), so this launches Hatari with `--joy1 keys`:
#
#   cursor keys   move / duck / climb          Right-Ctrl   fire
#   F12           Hatari's own menu             Ctrl-Q      quit Hatari
#
# Hatari owns that mapping, not this script: if fire is somewhere else on your build, F12 ->
# "Joysticks" shows and changes it. Ctrl-Q is how you leave — see "WHAT YOU WILL SEE" below.
#
# WHAT YOU WILL SEE, stated exactly, because it is less than "the game".
#
#   The reconstruction is entered the way the original enters it: `jmp $4a0` with a stage ALREADY
#   LOADED. The chain that loads one is unported (atari/README.md §2), so this build stages the
#   ORIGINAL's own post-boot RAM — measured off a real emulated machine by `original.py dump` — and
#   jumps in. You therefore get the first playable stage, mid-game, with no title screen, no credits
#   and no attract mode, and the run begins at the frame the original's boot handed over on.
#
#   From there the frame loop is the original's: `do { ... } while (1)`, no exit instruction. This
#   build lifts the fifty-two-frame count and the watchdog the headless modes need
#   (wonderboy_main.c's SMOKE_PLAY block), so it runs until you close the window. MEASURED, not
#   assumed: `smoke.py play` runs it headless past 12,000 vblanks and asserts it is still flipping
#   buffers at the end — README.md's play row carries the reading.
#
#   IT IS SLOW, and that is the number to have before you start it: FOUR TO FIVE FRAMES A SECOND on
#   an 8 MHz 68000 (measured headless, 1,004 frames in 12,000 vblanks under TOS 1.04 and 1,160 under
#   EmuTOS — the ROM decides how much of the window is left after it boots, so the figure belongs to
#   the ROM as well as to the build). The reconstruction is C compiled for a chip the original was
#   hand-written for and no work has gone into the gap. What you get is the game running and
#   responding, not the game at speed. (Hatari's fast-forward, F-key or menu, helps.)
#
#   IT TAKES THE MACHINE — real vectors at $70 and $118, as the original does — and normally never
#   gives it back, so Ctrl-Q is the exit. NORMALLY: the frame loop kept its third way out, so one of
#   game_key_actions' three endings really does leave it and hand the machine back. What happens
#   when it does IS asserted, on the frame build that shares this build's whole exit path: all three
#   endings driven and the hand-back read back from outside the program (smoke.py m3, README §12).
#   Driving them is also what found the hang that used to follow any key-driven exit (README §8).
#
#   WHAT IS NOT ASSERTED BY ANYTHING: that the stick MOVES HIM. The ACIA handler's two joystick arms
#   have never executed under any headless check, and that boundary is MEASURED rather than assumed
#   — Hatari's --control-socket can inject a KEY at the emulated IKBD (and the code really does reach
#   WB_KEY_LAST_SCANCODE), but --joy1 keys maps HOST key events onto the stick, so the two never meet
#   and WB_JOY1_STATE stays $00. This runner and a person at the cursor keys are what run those arms.
#   README.md's M3 joystick row has the readings.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BUILD="$HERE/build"
DISK="$HERE/disk"
PLAY_PRG="$BUILD/WB-play.PRG"

MODE="${1:-}"
if [ "$MODE" = "rebuild" ] || [ ! -f "$PLAY_PRG" ]; then
  bash "$HERE/build.sh" play
fi

# EVERYTHING BELOW THAT smoke.py ALREADY DECIDES IS ASKED OF smoke.py, not copied. Five things are
# shared with the headless modes, and a GUI launcher that disagreed about any of them would be
# playing a different build on a different machine from the one every check over there measured:
#
#   * THE DRIVE. `stage_drive` copies the .PRG together with THE IMAGE IT WAS BUILT AGAINST and the
#     palette beside it, and deletes any stale output first — each .PRG has its own image length
#     compiled in, and booting one over another mode's image reads as a crash. Every smoke mode
#     restages disk/ for its own build, so whatever ran last decides what is on the drive.
#   * THE ROM. $WB_TOS_ROM, then tools/hatari/TOS*.img NEWEST FIRST, then Hatari's bundled EmuTOS. A
#     plain `sorted()` picks TOS102US.img, which never runs the program at all under a GEMDOS drive.
#   * THE MACHINE SIZE. The 1 MiB image is the program's BSS, so the memory size is not a free
#     choice — and a person playing a differently-sized machine from the one `smoke.py play`
#     measured would get a different image base, which is exactly the drift that broke three pinned
#     counts on the other ROM (README.md §3).
#   * WHAT TO AUTO-BOOT, and * WHICH MONITOR. Both were hard-coded here in the first draft, which
#     made `C:\WB.PRG` a THIRD spelling of a name `stage_drive` and `run_hatari` already share.
#
# ONE VALUE PER LINE AND THE ROM LAST. `read -r A B` splits on whitespace, so a $WB_TOS_ROM path with
# a space in it truncated the ROM and smuggled the remainder into the memory size — past the guard
# below, because the guard only asks whether the size is non-empty.
[ -f "$PLAY_PRG" ] || { echo "no $PLAY_PRG — run: bash $HERE/build.sh play"; exit 1; }
{ read -r MEMSIZE; read -r MONITOR; read -r AUTOBOOT; read -r ROM; } <<EOF
$(PYTHONPATH="$HERE" python3 -c '
import pathlib, smoke
smoke.stage_drive(pathlib.Path("'"$PLAY_PRG"'"))
print(smoke.MEMSIZE_MB)
print(smoke.DEFAULT_MONITOR)
print(smoke.AUTO_BOOT)
print(smoke.find_tos() or "-")')
EOF
# A COMMAND SUBSTITUTION INSIDE A HERE-DOC IS NOT COVERED BY `set -e`, so a staging failure would
# otherwise reach `exec` as `--tos '' --memsize ''` and open a broken machine. `stage_drive` raises
# on a missing image or palette, which is precisely the case worth catching here. The LAST value read
# is the one to test: a short answer leaves it empty.
[ -n "${ROM:-}" ] && [ -n "${MEMSIZE:-}" ] \
  || { echo "staging failed — run: bash $HERE/build.sh play"; exit 1; }
[ "$ROM" = "-" ] && set -- || set -- --tos "$ROM"

# THE COMMAND, BUILT ONCE INTO AN ARRAY so that `parsecheck` can print and probe the very arguments
# `exec` would take. Two spellings of it — one to run and one to check — is a check that stops
# covering the line it is named for, which is the whole failure this mode exists to catch.
#
# Sound ON (Hatari's --sound takes a FREQUENCY, off/6000-50066 — "on" is rejected at parse time) and
# no --fast-forward, which is the whole difference from smoke.py's invocation: this one is for a
# person.
ARGV=( "$@" --sound 44100 --confirm-quit off --memsize "$MEMSIZE" --monitor "$MONITOR" \
       --tos-res low --joy1 keys --harddrive "$DISK" --auto "$AUTOBOOT" )

if [ "$MODE" = "parsecheck" ]; then
  # The list first, so smoke.py's control can substitute into the REAL arguments rather than into a
  # copy of them; then the probe. `--help` prints the usage and stops where it is reached, so a clean
  # parse is "the usage banner, and no line beginning Error". Its own exit status is 1 either way,
  # which is why the verdict is taken from the output and this script's status is set below.
  echo "RUNSH-ARGV-BEGIN"
  printf '%s\n' "${ARGV[@]}"
  echo "RUNSH-ARGV-END"
  PARSED="$(hatari "${ARGV[@]}" --help 2>&1 || true)"
  printf '%s\n' "$PARSED"
  # `if`, NOT `grep -q ... && { ... }`: under `set -e` a trailing `&&` list whose left side fails
  # takes the whole script's exit status with it, so the clean-parse path would have exited 1.
  if printf '%s\n' "$PARSED" | grep -q '^Error'; then
    echo "PARSE FAILED — Hatari rejected an option in the line above"
    exit 1
  fi
  if ! printf '%s\n' "$PARSED" | grep -q '^Usage:'; then
    echo "no usage banner — --help never ran, so nothing above was proved to parse"
    exit 1
  fi
  echo "OK: hatari accepts every option run.sh would launch with"
  exit 0
fi

echo "-- $AUTOBOOT from the play build; TOS=$ROM; ${MEMSIZE}MB $MONITOR; joystick 1 on the cursor keys"
exec hatari "${ARGV[@]}"
