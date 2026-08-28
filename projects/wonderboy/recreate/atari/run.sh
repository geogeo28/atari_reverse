#!/bin/bash
# Play the reconstructed Wonder Boy in the Hatari GUI — a window, sound, and a joystick.
#
#   run.sh              -> disk/WB.PRG, the OWN-ENTRY build (built for you if it is missing)
#   run.sh rebuild      -> force `build.sh ownrun` first
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
#   cursor keys   move / duck / climb          Right-Ctrl   fire (and every title/credits prompt)
#   ESC           quit the round: the data-disk prompt, then the title screen again
#   F12           Hatari's own menu             Ctrl-Q      quit Hatari
#
# Hatari owns that mapping, not this script: if fire is somewhere else on your build, F12 ->
# "Joysticks" shows and changes it. Ctrl-Q is how you leave — see "WHAT YOU WILL SEE" below.
#
# IF FIRE DOES NOTHING, CHECK THE KEY FIRST AND THEN SUSPECT THE BUILD — both branches are real and
# they are told apart in that order every time:
#
#   * THE KEY. Hatari's default fire for `--joy1 keys` is RIGHT-Control, and most Mac keyboards do
#     not have one. F12 -> "Joysticks" -> port 1 -> "Define keys" rebinds it to something you can
#     press. Do that before concluding anything about the reconstruction.
#   * THE BUILD. A fire gate that still never answers WITH A KEY YOU HAVE SEEN WORK is the build,
#     and there is a known shape for it: the boot's IKBD mouse-disable not going out, which leaves
#     the controller reporting fire as a mouse button. README §4 has that one.
#
# Worth rebinding rather than working around, because THIS IS THE ONLY TEST THIS PROJECT HAS OF THE
# JOYSTICK INPUT PATH: every headless pass answers the fire gates by poking WB_JOY1_STATE at the
# wait's own PC, so a person pressing fire here is the only thing that has ever driven the ACIA
# handler's `$ff` joystick arm — which is how that defect reached a real STE before it reached a row.
#
# WHAT YOU WILL SEE, stated exactly, because it is both more and less than "the game".
#
#   THE PROGRAM BOOTS ITSELF. Since batch 44 phase E this is the OWN-ENTRY build: the drive carries
#   the shipped `SWB.PRG` image plus the game's own seven resources, and the reconstruction runs
#   ../src/boot.c's four composed slices to get from the program image to a playable stage. So you
#   get the REAL TITLE SCREEN, drawn out of the disk's own TITLESCR.RAD by reconstructed code; fire
#   takes you to the credits; fire again loads stage 1's overlay, its tiles and its sprites; and then
#   the frame loop starts. No measured RAM is staged and no dump is needed for any of it.
#
#   AND THE ENDINGS COME BACK TO IT — ALL FIVE OF THEM. The frame loop has five ways out and every
#   one is wired to the address the original's own `jmp` names. Three are keys: a round end and the
#   cheat's level skip call the stage load again (so finishing a round really does load the next
#   stage), and ESC draws the data-disk prompt and then walks the whole chain again — prompt, title,
#   credits, stage. THE OTHER TWO ARE THE PLAYER'S, and they are the ones a person meets without
#   pressing anything: spending a life or walking into the collision map's exit tile reloads the
#   stage, and the game-over box expiring draws the data-disk prompt. MEASURED headless, six
#   passes, both ROMs: `smoke.py ownplay`. This binary itself is booted by `smoke.py ownrun`, which
#   is what says the uncapped build links, boots and gets through the file seam.
#
#   The frame loop itself is the original's: `do { ... } while (1)`, no exit instruction. This build
#   lifts the fifty-two-frame count, the frame watchdog AND the fire gates' spin bound that the
#   headless modes need (wonderboy_main.c's SMOKE_PLAY block), so a prompt waits for you rather than
#   giving up after six seconds and the game runs until you close the window.
#
#   IT IS SLOW, and that is the number to have before you start it: FOUR TO FIVE FRAMES A SECOND on
#   an 8 MHz 68000 (measured headless, 1,004 frames in 12,000 vblanks under TOS 1.04 and 1,160 under
#   EmuTOS — the ROM decides how much of the window is left after it boots, so the figure belongs to
#   the ROM as well as to the build). The reconstruction is C compiled for a chip the original was
#   hand-written for and no work has gone into the gap. What you get is the game running and
#   responding, not the game at speed. (Hatari's fast-forward, F-key or menu, helps.)
#
#   IT TAKES THE MACHINE — real vectors at $70 and $118, as the original does — and never gives it
#   back on its own, so Ctrl-Q is the exit. That is a CHANGE from the play build this replaced: there
#   an ending left the frame loop and handed the machine back, because there was no boot chain to
#   return into. Here every one of the five endings goes back into the chain, which is what the
#   original does, so no ending ends the program. ONE THING STILL CAN end it: a stage load the drive
#   cannot answer stops the ladder and hands the machine back with the reason in its record — the
#   declared retry policy (README §15), driven headless by `smoke.py ownplay` passes 5 AND 6: one
#   withholds the next stage's overlay and stops at the reload arm, one withholds the prompt's own
#   picture and stops at the restart arm, both with real data and no fault injected. The hand-back
#   itself is still asserted, on the frame build that shares this build's exit path: all three
#   endings driven and the two vectors read back from outside the program (smoke.py m3, README §12). Driving them is also what found the hang that used to follow
#   any key-driven exit (README §8).
#
#   THE MOUSE IS TURNED OFF WHILE THE GAME RUNS, as the original turns it off: `install` sends IKBD
#   command $12 at boot, which is `init_ikbd` ($e48c) reproduced, and it is what makes fire work at
#   all — on a real ST joystick 1's fire and the mouse's RIGHT BUTTON are the same line. THIS BUILD
#   NEVER GIVES THE MACHINE BACK, so nothing here re-enables it: the reset button, or closing Hatari,
#   is what returns your mouse. STATUS.md's batch 44 phase H addendum has the mechanism.
#
#   WHAT IS NOT ASSERTED BY ANYTHING: that the stick MOVES HIM. The ACIA handler's two joystick arms
#   have never executed under any headless check, and that boundary is MEASURED rather than assumed
#   — Hatari's --control-socket can inject a KEY at the emulated IKBD (and the code really does reach
#   WB_KEY_LAST_SCANCODE), but --joy1 keys maps HOST key events onto the stick, so the two never meet
#   and WB_JOY1_STATE stays $00. This runner and a person at the cursor keys are what run those arms.
#   README.md's M3 joystick row has the readings. The FIRE gates are the same boundary from the other
#   side: headless they are answered by a debugger poking WB_JOY1_STATE, and here by a real IKBD
#   report the ACIA handler files.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BUILD="$HERE/build"
DISK="$HERE/disk"
PLAY_BUILD=ownrun
PLAY_PRG="$BUILD/WB-$PLAY_BUILD.PRG"

MODE="${1:-}"
if [ "$MODE" = "rebuild" ] || [ ! -f "$PLAY_PRG" ]; then
  bash "$HERE/build.sh" "$PLAY_BUILD"
fi

# EVERYTHING BELOW THAT smoke.py ALREADY DECIDES IS ASKED OF smoke.py, not copied. Five things are
# shared with the headless modes, and a GUI launcher that disagreed about any of them would be
# playing a different build on a different machine from the one every check over there measured:
#
#   * THE DRIVE. `stage_drive` copies the .PRG together with THE IMAGE IT WAS BUILT AGAINST and the
#     palette beside it, and deletes any stale output first — each .PRG has its own image length
#     compiled in, and booting one over another mode's image reads as a crash. Every smoke mode
#     restages disk/ for its own build, so whatever ran last decides what is on the drive. FOR THIS
#     BUILD IT ALSO STAGES THE SEVEN RESOURCES the ladder can ask for by name (smoke.py's
#     `own_resource_indices`), which is the whole reason the game can boot itself here.
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
[ -f "$PLAY_PRG" ] || { echo "no $PLAY_PRG — run: bash $HERE/build.sh $PLAY_BUILD"; exit 1; }
{ read -r MEMSIZE; read -r MONITOR; read -r AUTOBOOT; read -r ROM; } <<EOF
$(PYTHONPATH="$HERE" python3 -c '
import contextlib, pathlib, sys, smoke
# STAGING TALKS, AND ITS TALK IS NOT ONE OF THE FOUR VALUES. `stage_drive` prints a note for this
# build — the corpus check that says every staged resource is byte-identical in the repaired tree —
# and the `read`s below take stdout LINE BY LINE, so that note arrived as the memory size and the
# ROM path arrived as `--tos C:\WB.PRG`. Caught by `run.sh parsecheck`, which is the one thing that
# runs this line without opening a machine. Redirected here rather than in smoke.py, because every
# other caller of `stage_drive` wants the note on stdout with the rest of its report.
with contextlib.redirect_stdout(sys.stderr):
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
  || { echo "staging failed — run: bash $HERE/build.sh $PLAY_BUILD"; exit 1; }
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

echo "-- $AUTOBOOT from the $PLAY_BUILD build; TOS=$ROM; ${MEMSIZE}MB $MONITOR; joystick 1 on the cursor keys"
exec hatari "${ARGV[@]}"
