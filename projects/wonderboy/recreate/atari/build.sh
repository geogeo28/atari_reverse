#!/bin/bash
# Build WB.PRG from the verified reconstruction with the m68k-elf cross toolchain, and stage a drive
# for Hatari.
#
#   build.sh            -> the M1 build: stage the image, take the machine, run SMOKE_VBLS vblanks
#                          through the reconstructed vbl_handler, hand it back, dump STATS.BIN
#   build.sh novbl      -> M1's NEGATIVE CONTROL: identical, minus the level-4 vector install. Every
#                          M1 assertion that depends on the machine driving the reconstruction must
#                          FAIL, and smoke.py inverts its verdict for this build.
#   build.sh m2         -> the FRAME build: the image is the ORIGINAL's post-boot RAM instead of the
#                          program plus seeds, and the shim runs game_main_loop rather than counting
#                          vblanks. Needs `python3 atari/original.py dump` first — the image cannot
#                          be computed, only measured (gen_image.py's honesty line).
#   build.sh title      -> the TITLE build: M1's image, plus the boot's own five-call title slice —
#                          load TITLESCR.RAD across the file seam, depack it, set the palette. The
#                          first picture here the reconstruction DRAWS rather than inherits.
#   build.sh titlecredits -> its NEGATIVE CONTROL: the same three calls aimed at CREDITS.RAD.
#   build.sh boot       -> the BOOT build: M1's image again, and ALL THREE of ../src/boot.c's
#                          composed slices in the boot's own order, with the boot's own fire gates
#                          between them — the title, the credits and the per-stage load. It ends by
#                          writing the whole game span out as BOOT.IMG, which is `original.py dump`'s
#                          measured image RECOMPUTED.
#   build.sh bootfault  -> its MIS-RUN CONTROL: the same build with the CREDITS slice's call
#                          suppressed and nothing else, so the run's shape — both gates, the other
#                          two slices, the span written — is unchanged and what must redden is the
#                          credits picture and the span's own named bands.
#   build.sh ownplay    -> THE OWN-ENTRY BUILD: the boot build's chain AND the frame loop, with
#                          `game_key_actions`' three endings wired to the addresses the original's
#                          own `jmp`s name — a round end or a level skip reloads the stage, ESC
#                          shows the data-disk prompt and walks the whole chain again. It stages
#                          M1's image and NO palette: the boot puts the pens up itself. Headless
#                          bounds: the fire gates spin out, the frame loop stops at its anchor
#                          count, and the ladder takes at most OWN_LEG_LIMIT endings.
#   build.sh ownrun     -> the same build with every bound lifted (-DSMOKE_PLAY), which is what
#                          `atari/run.sh` launches for a person.
#
# Writes disk/{WB.PRG,WB.IMG} and keeps build/WB-<mode>.PRG so a check needing two builds in
# sequence does not have to rebuild. build/ and disk/ are gitignored (repo .gitignore already covers
# projects/*/recreate/atari/{build,disk}/).
#
# THE CORES ARE COMPILED UNCHANGED except for one flag they themselves anticipate: -DWB_ON_TARGET
# turns the arm inside the port's ONE shifter sink — `../src/shifter.c` and `../include/shifter.h` —
# into real stores. The differential .so never sees that define, so `make test` is untouched, and two
# checks below MEASURE that rather than asserting it in prose:
# `assert_the_differential_build_is_unchanged` (no core reaches `wb_target_*` outside a guard) and
# `assert_the_sink_arm_lives_in_one_place` (no second file grows a guard of its own).
#
# THE SEAM IS THE LINK, not the include path. Every kit symbol Wonder Boy calls is a real symbol, so
# the kit's src/{hw,psg,sched,disk,os_refusal,dosound_log}.c are simply left out. THE SURFACE IS
# SEVEN SYMBOLS AND wonderboy_backend.c OWES SIX OF THEM: `os_refused` is the seventh and is
# deliberately NOT defined, because -DOS_NO_REFUSAL_TALLY makes the kit's own os.h serve an inline
# identity for it. Joust needs a `shim_include/os.h` shadow because the helpers it replaces are
# `static inline`; this game calls none of those — which is a property of the CORES and so is
# checked, below, rather than believed.
set -euo pipefail

# THE MODES THAT RUN FRAMES, in one place. They stage the original's post-boot RAM and its palette,
# they carry M2_ENTRY_UNWIND, and they are the ones smoke.py stages `PENS.IMG` for. smoke.py SCRAPES
# this line rather than keeping its own list — a second spelling would let a new frame mode boot
# without the palette it needs and report "no M2.BIN", which reads like a crash (CLAUDE.md §5).
FRAME_MODES="m2 m5fault m5flash m6rearm m3fault play"

# ...AND THE MODES THAT RUN FRAMES OVER AN IMAGE THEY COMPUTED THEMSELVES. They compile -DSMOKE_M2
# for `run_frames` exactly as the list above does, and they stage the M1 image and no palette,
# because their own boot chain produces both. So they are the one exception to the rule below, and
# they are named rather than special-cased inside it.
#
# smoke.py DOES NOT SCRAPE THIS LINE, and an earlier draft of this comment said it did — which is
# the kind of claim that makes a reader stop looking for the drift it promises is impossible. What
# smoke.py holds is the two BUILD NAMES (`OWN_BUILDS`, `OWN_RUN_BUILD`), and they are pinned to this
# line the other way round: `smoke.py ownplay` and `smoke.py ownrun` name .PRGs this script writes as
# `WB-<mode>.PRG`, so a mode renamed here and not there fails at the .PRG lookup with the build
# command printed. FRAME_MODES is scraped because smoke.py has to STAGE differently for those modes;
# nothing about these two needs a list.
OWN_ENTRY_MODES="ownplay ownrun"

MODE="${1:-m1}"
case "$MODE" in
  m1)    DEF="" ;;
  # The control. Suppressing the ONE install is what makes M1's positives falsifiable: no vblank
  # reaches the reconstruction, so its counter stays at gen_image.py's seeded 0, the tempo byte stays
  # at the unwritten sentinel, the floppy timer never expires and the chip is never touched.
  novbl) DEF="-DSMOKE_NO_VBL_INSTALL" ;;
  m2)    DEF="-DSMOKE_M2" ;;
  # M5's SENSITIVITY CONTROL: the frame build with ONE pen corrupted on its way to the shifter. It is
  # a machine-COLOUR fault and nothing else — the reconstruction draws the same bytes — so every
  # surface that reads colour (the pens, the hardware vector, the rendered picture) must go red and
  # the framebuffer compare must not.
  #
  # PEN 3 RATHER THAN AN ARBITRARY ONE, and the reason is the rendered half of that claim: pen 3 is
  # $777, the white the HUD's panels and text are drawn in, so it is certainly on screen at every
  # anchor. A pen that happened not to appear in the picture would make the control's `picture`
  # arm fail for a reason about coverage rather than about the fault — which is the trap the sibling
  # project fell into and had to document.
  #
  # SMOKE.PY DOES NOT READ THIS LINE. The number reaches the check through the RECORD — the shim
  # publishes it as `M2.BIN`'s `fault_pen` and `assert_only_the_faulted_pen` requires the divergence
  # to be at exactly that pen and no other. Scraping it out of this script instead was the round's
  # own defect: the per-mode `.PRG`s persist while this file is edited, so the scrape would name a
  # pen the running binary need not have injected — the staleness hazard `capture_pc` exists to
  # avoid, reproduced one control over.
  m5fault) DEF="-DSMOKE_M2 -DM5_FAULT_PEN=3" ;;
  # M5's FLASH RUN: the frame build with `flip_screen`'s white-flash countdown armed. The seed is the
  # ORIGINAL's own operand — `move.w #$2,$714.w` at $1328, the lightning arm of `player_weapon_fire`
  # — and atari/original.py pokes the same word into the shipped binary at the same instant, so this
  # is one declared fabrication applied to both sides rather than a fixture on ours.
  # wonderboy_main.c's `arm_the_flash` has the census that says why it cannot be driven instead.
  # The seed itself is scraped from ../include/wonderboy.h below, once REC is known.
  m5flash) DEF="-DSMOKE_M2" ;;
  # M6's NEGATIVE CONTROL: the frame build re-publishing the staged palette after every frame. The
  # same sixteen words through the same sink, so no snapshot in this project can tell it from `m2` —
  # the framebuffer, the pens, the hardware vector and the rendered picture are all identical. Only
  # the ORDERED TIMELINE moves, which is what makes it the control that shows M6 can fail.
  m6rearm) DEF="-DSMOKE_M2 -DSMOKE_M6_REARM" ;;
  # M3's HAND-BACK CONTROL: the frame build that TAKES the machine and never gives the two vectors
  # back. Everything else is `m2` — the same install, the same driven ending, the same record — so
  # what reddens is exactly the hand-back: the two teardown read-backs inside the record, the
  # debugger's comparison of $70/$118 across the program's exit, and TOS's own frame clock, which
  # stops the moment its vertical-blank handler is no longer on the vector. It is the control that
  # shows M3's Pterm rows CAN fail, and it is the sibling project's real bug reproduced on purpose
  # (a handler left hooked into memory GEMDOS had taken back, found only by running past the exit).
  m3fault) DEF="-DSMOKE_M2 -DSMOKE_M3_NO_HANDBACK" ;;
  # THE TITLE BUILD: the first picture in this directory the RECONSTRUCTION produces rather than
  # inherits. It stages the M1 image — the program plus gen_image.py's seeds, no measured RAM at all
  # — and runs the boot's own five-call title slice over it, ending in a 32000-byte screen and
  # sixteen pens that are compared against the shipped binary's at `$e556`. It needs the .RAD files
  # on the drive, which smoke.py's `stage_drive` puts there.
  title)  DEF="-DSMOKE_TITLE" ;;
  # ...AND ITS NEGATIVE CONTROL: the same three calls, aimed at the game's OTHER shipped picture.
  # CREDITS.RAD depacks to the same 32,128 bytes through the same code into the same buffer, so
  # nothing about the run's shape moves — only the bytes on the screen — and every row of the
  # comparison that a different picture can break must break. The index is compiled in and REPORTED
  # BY THE BINARY (wonderboy_main.c's `resource_index`), which is `fault_pen`'s rule: the per-mode
  # `.PRG`s outlive an edit to this script, so a smoke that scraped the `-D` from here could name a
  # resource the running binary never asked for.
  #
  # THE INDEX IS SCRAPED FROM ../include/wonderboy.h rather than written as 1, so this control and
  # the reconstruction's own WB_RESOURCE_* enumeration cannot drift (CLAUDE.md §5).
  titlecredits) DEF="-DSMOKE_TITLE" ;;
  # THE BOOT BUILD: the whole chain, on the machine. It stages M1's image — the shipped program plus
  # gen_image.py's named seeds, not one byte of measured RAM — runs ../src/boot.c's three composed
  # slices in the boot's own order, and writes the game's whole address space out at the instant
  # `boot_load_stage` returns. That span is what `atari/original.py dump` MEASURES off the shipped
  # binary at $f8b4 and what gen_image.py stages; this build computes it. smoke.py differences the
  # two band by band, with every band named.
  boot)  DEF="-DSMOKE_BOOT" ;;
  # ...AND ITS MIS-RUN CONTROL: the middle slice's call suppressed, and nothing else. The middle one
  # on purpose — both fire gates are still crossed, both other slices still run, the span is still
  # written and the record is still complete, so the control's own run is SOUND (m2fault's rule) and
  # the only thing that changed is that one slice's work is missing. What must then redden is the
  # credits picture AND the span diff's named bands, and the mode must say WHICH.
  bootfault) DEF="-DSMOKE_BOOT -DBOOT_FAULT_SKIP_CREDITS" ;;
  # THE BUILD A PERSON PLAYS, and the only one here that is not a measurement. It is `m2` with the
  # frame count and the watchdog lifted (wonderboy_main.c's SMOKE_PLAY block says why each has to
  # go), so the reconstruction's frame loop runs until the window is closed. `atari/run.sh` builds
  # it and launches Hatari with a screen, sound and a joystick; `smoke.py play` is the half of it a
  # headless run can assert.
  play)  DEF="-DSMOKE_M2 -DSMOKE_PLAY" ;;
  # THE OWN-ENTRY BUILD. -DSMOKE_M2 is passed EXPLICITLY rather than being implied inside the C, so
  # a reader of this script — and the FRAME_MODES/OWN_ENTRY_MODES check below — can see that the
  # frame loop is compiled in. What makes it an own-entry build is that it is NOT in FRAME_MODES: it
  # stages the program plus seeds, and the boot chain it runs is what fills the rest.
  ownplay) DEF="-DSMOKE_OWNPLAY -DSMOKE_M2" ;;
  # ...and the one a person plays. -DSMOKE_PLAY lifts the frame count, the frame watchdog and the
  # fire waits' spin bound in one, which is the same switch the `play` build throws.
  ownrun)  DEF="-DSMOKE_OWNPLAY -DSMOKE_M2 -DSMOKE_PLAY" ;;
  *) echo "usage: build.sh [m1 | novbl | title | titlecredits | boot | bootfault |" \
          "$(echo "$FRAME_MODES $OWN_ENTRY_MODES" | tr ' ' '|')]"
     exit 2 ;;
esac

# Whether $MODE is in a space-separated list, as a word match rather than a substring one.
in_list() { case " $2 " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }
is_frame_mode() { in_list "$1" "$FRAME_MODES"; }
is_own_entry_mode() { in_list "$1" "$OWN_ENTRY_MODES"; }

# ...AND THE TWO LISTS IN THIS FILE ARE PINNED TO THE `case` ABOVE, IN BOTH DIRECTIONS. `FRAME_MODES`
# is what smoke.py scrapes, but the `case` is what decides what a mode actually compiles — so a mode
# in one and not the other would stage the wrong image and report "no M2.BIN", which reads like a
# crash. Every check below is derived from $DEF rather than restating a `-D` a third time.
#
# BOTH DIRECTIONS, because one is not a pin. The first draft asked only "does a -DSMOKE_M2 build
# appear in a list", so a mode LISTED in either list that had lost its `-D` passed silently — an
# own-entry mode without -DSMOKE_OWNPLAY builds an M1 binary under an own-entry name, and smoke.py
# then reports "no OWN.BIN" about a build that never had a ladder in it.
has_define() { case " $DEF " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }

case "$DEF" in
  *-DSMOKE_M2*) is_frame_mode "$MODE" || is_own_entry_mode "$MODE" || {
      echo "ERROR: mode '$MODE' compiles -DSMOKE_M2 but is in neither FRAME_MODES=\"$FRAME_MODES\""
      echo "       nor OWN_ENTRY_MODES=\"$OWN_ENTRY_MODES\". It would be built as a frame binary"
      echo "       and staged with the M1 image and no palette."
      exit 1; } ;;
  *) ! is_frame_mode "$MODE" || {
      echo "ERROR: mode '$MODE' is in FRAME_MODES but does not compile -DSMOKE_M2."
      exit 1; }
     ! is_own_entry_mode "$MODE" || {
      echo "ERROR: mode '$MODE' is in OWN_ENTRY_MODES but does not compile -DSMOKE_M2, so it has no"
      echo "       frame loop — the ladder would boot the chain and have nothing to enter."
      exit 1; } ;;
esac
# ...and the other half of the own-entry pin: the list's members must carry the define that MAKES
# them own-entry builds. -DSMOKE_M2 alone is a frame build under an own-entry name.
if is_own_entry_mode "$MODE" && ! has_define "-DSMOKE_OWNPLAY"; then
  echo "ERROR: mode '$MODE' is in OWN_ENTRY_MODES but does not compile -DSMOKE_OWNPLAY — it would"
  echo "       build a frame binary, and smoke.py would report \"no OWN.BIN\" about a run that"
  echo "       never had a ladder in it."
  exit 1
fi
if has_define "-DSMOKE_OWNPLAY" && ! is_own_entry_mode "$MODE"; then
  echo "ERROR: mode '$MODE' compiles -DSMOKE_OWNPLAY but is not in OWN_ENTRY_MODES=\"$OWN_ENTRY_MODES\","
  echo "       so it would be staged as a plain build."
  exit 1
fi
# ...and the two lists must not overlap, or `is_frame_mode` would send an own-entry build to the
# dump. Checked rather than trusted, because the two are edited for different reasons.
for OWN in $OWN_ENTRY_MODES; do
  ! is_frame_mode "$OWN" || {
    echo "ERROR: '$OWN' is in BOTH FRAME_MODES and OWN_ENTRY_MODES — it would be staged with the"
    echo "       original's measured RAM, which is exactly what an own-entry build must not have."
    exit 1; }
done

HERE="$(cd "$(dirname "$0")" && pwd)"
REC="$(cd "$HERE/.." && pwd)"                             # recreate/
TOOLS="$(cd "$REC/../../../tools" && pwd)"                # the workspace's game-agnostic tooling
KIT="$TOOLS/recreate_kit"                                 # the shared harness
BIN="$REC/../bin"                                         # projects/wonderboy/bin
BUILD="$HERE/build"; DISK="$HERE/disk"
PRG="WB.PRG"
mkdir -p "$BUILD" "$DISK"

CC=m68k-elf-gcc

# A NUMBER A BUILD NEEDS IS SCRAPED FROM THE HEADER THAT DEFINES IT, never written here — one
# canonical definition (CLAUDE.md §5), and a build that cannot find it refuses rather than compiling
# an empty `-DFOO=`. Every `-D` below whose value belongs to the reconstruction comes through here.
wb_constant() {
  local VALUE
  VALUE=$(sed -n "s/^#define $1 *\([0-9][0-9]*\)u.*/\1/p" "$REC/include/wonderboy.h")
  [ -n "$VALUE" ] || { echo "ERROR: no plain-integer $1 in $REC/include/wonderboy.h" >&2; return 1; }
  echo "$VALUE"
}

# The flash seed is the ORIGINAL's own operand — `move.w #$2,$714.w` at $1328, the lightning arm.
if [ "$MODE" = m5flash ]; then
  DEF="$DEF -DM5_FLASH_SEED=$(wb_constant WB_PLAYER_LIGHTNING_FLASH)" || exit 1
fi
# ...and the title control's resource is the game's own index for CREDITS.RAD.
if [ "$MODE" = titlecredits ]; then
  DEF="$DEF -DTITLE_RESOURCE=$(wb_constant WB_RESOURCE_CREDITS)" || exit 1
fi

# The image comes FIRST: its byte length is the one source of truth for how much wonderboy_main.c
# must read back in, and both it and the address it lands at are passed straight to the compiler.
# WB_STAGED_AT is scraped from ../project.toml rather than written here — that file is where the
# 0x3f8 load base is argued for, and a second spelling could drift from the loader gen_image.py uses.
echo ">> stage drive"
PY="$REC/.venv/bin/python"; [ -x "$PY" ] || PY=python3
if is_frame_mode "$MODE"; then
  # THE M2 IMAGE IS MEASURED, NOT COMPUTED, and this is where that costs something: the dump has to
  # exist before the build, and a stale one is worse than a missing one because it would build.
  DUMP="$BUILD/ORIGRAM.BIN"; REGS="$BUILD/ORIGREGS.txt"; PENS="$BUILD/ORIGPENS.BIN"
  # THE THREE ARTEFACTS MUST BE ONE BOOT'S, and an existence test cannot say that: an interrupted
  # dump leaves this boot's RAM beside the previous boot's registers and palette, all three present.
  # original.py stamps a manifest (boot id + size + digest each) after all three land, and this
  # verifies against it — so a mixed or half-written set refuses the build instead of producing an
  # image and an A5 from different boots.
  "$PY" -c "
import sys; sys.path.insert(0, '$HERE')
import original
ok, message = original.check_manifest('$BUILD')
print(('   ' if ok else 'ERROR: ') + message)
sys.exit(0 if ok else 1)" || exit 1
  "$PY" "$HERE/gen_image.py" "$BIN/disk1/AUTO/SWB.PRG" "$DISK/WB.IMG" --dump "$DUMP"
  # The palette is the boot's product too and it does not live in RAM — see wonderboy_main.c's
  # STAGED_PENS_FILE. Copied rather than generated: it is 32 bytes of measurement.
  cp "$PENS" "$DISK/PENS.IMG"
  # `game_main_loop` is `jmp`ed into and inherits the boot's registers; a5 is the sprite pass's
  # `unwind` and the ONE field of its argument that is a real input (../include/blit.h). Taken from
  # the same dump as the memory, so the two cannot come from different boots.
  #
  # PARSED BY original.py's OWN READER rather than by a sed here. The first draft was a sed, it did
  # not match (BSD sed has no `\b`), and even fixed it would have been a second spelling of a format
  # Python already parses — CLAUDE.md §5's across-a-language-boundary duplication, in the one place
  # where a silent mismatch would compile a plausible wrong number into the frame build.
  UNWIND=$("$PY" -c "
import sys; sys.path.insert(0, '$HERE')
import original
from pathlib import Path
value = original.register(Path('$REGS').read_text(), 'A5')
print('%#010x' % value if value is not None else '')")
  [ -n "$UNWIND" ] || { echo "ERROR: no A5 in $REGS — re-run \`atari/original.py dump\`"; exit 1; }
  DEF="$DEF -DM2_ENTRY_UNWIND=$UNWIND"
else
  "$PY" "$HERE/gen_image.py" "$BIN/disk1/AUTO/SWB.PRG" "$DISK/WB.IMG"
fi
IMG_BYTES=$(wc -c < "$DISK/WB.IMG" | tr -d ' ')           # BSD wc pads with spaces
STAGED_AT=$(sed -n 's/^load_base *= *\(0x[0-9a-fA-F]*\).*/\1/p' "$REC/project.toml")
[ -n "$STAGED_AT" ] || { echo "ERROR: no load_base in $REC/project.toml"; exit 1; }
DEF="$DEF -DPROGRAM_BYTES=$IMG_BYTES -DWB_STAGED_AT=$STAGED_AT"

# -Wno-array-bounds: the shim dereferences fixed hardware addresses (the shifter, the MFP, the ACIA)
#   as absolute pointers, which GCC reads as an out-of-bounds array[0] access.
# -fno-tree-loop-distribute-patterns: at -O2 GCC recognises wonderboy_backend.c's hand-written
#   memset/memcpy loops and replaces them with calls to memcpy/memset — i.e. with themselves.
# -DOS_NO_REFUSAL_TALLY: the kit's os.h anticipates exactly this build and compiles `os_refused`
#   down to an inline identity, so src/os_refusal.c is not needed. The one game-side call site
#   (../src/sound.c:786) then simply returns its sentinel, which is the routine bailing out of a
#   malformed sound pattern — and ../STATUS.md records that that opcode band ($98..$b7) has no
#   on-target story of its own yet.
# THERE IS NO -O HERE, and that is the point: the level is chosen PER TRANSLATION UNIT by
#   `opt_level_for` below, out of the one list `UNITS_BUILT_AT_O2`. The reason is a pair of
#   measurements (atari/profile.py, 2026-08-25, at 519b177).
#
#   -O3 IS WHAT THE FRAME IS MADE OF: 656.7 K -> 496.1 K cycles a frame, 12.20 -> 16.15 fps, from the
#   same sources. -fipa-cp-clone specialises a routine per CONSTANT argument, so the sprite blit's
#   ONE algorithm gets a clone per width table entry (blit_sprite_rows.constprop.N: 153 K -> 74 K a
#   frame) and the HUD's glyph plotter one per digit width (hud_plot_digit 2,100 -> 833 cycles, the
#   original's 862) — without the source giving up its one-algorithm shape.
#
#   AND THE PRICE IS CODE, PAID ON A 720 K FLOPPY. At -O3 everywhere WB.PRG went 107 -> 183 KB and
#   the boot disk (smoke.py's `build_floppy`, tools/st_build.py) came down to 1,024 bytes free of
#   728,064 — st_build.py refuses an overflow, so the next kilobyte of anything, resource or code,
#   simply would not have built. Buying that headroom back means asking each unit what its -O3 bytes
#   returned in the frame, which is what the list below records. MEASURED OVER THE WHOLE CHANGE:
#   WB-play.PRG 180,245 -> 154,384 B, the boot disk 1,024 -> 27,648 bytes free, and the frame
#   468.6 K -> 484.1 K cycles, 17.10 -> 16.55 fps. Only ~1.8 K of those cycles is WORK; the other
#   ~14.8 K is flip_screen's two vblank spins (../src/game.c's `wait_for_vbl_ready` and
#   `wait_for_vbl_tick`, through `sched_poll16`) waiting longer, because the frame already sits on a
#   vblank boundary and 1.8 K of work tips it past. The units NOT on the list — the frame loop —
#   keep -O3, and nothing about the link changes.
#
#   -flto on top FAILS this script's own checks today and is registered in ../STATUS.md's
#   "## Performance", under this batch, as an experiment NOT DONE rather than a lever measured.
# shim_include is on the path for tos.h / wonderboy_target.h / string.h ONLY; it shadows no kit header.
CFLAGS="-m68000 -fno-tree-loop-distribute-patterns -ffreestanding -fno-jump-tables \
        -fomit-frame-pointer -nostdlib -DOS_NO_REFUSAL_TALLY -DWB_ON_TARGET \
        -I$HERE/shim_include -I$REC/include -I$KIT/include -Wall -Wextra -Wno-array-bounds"
CORES="$(ls "$REC"/src/*.c)"

# ---- the optimisation level, one list, one measurement per entry --------------------------------
# HOW A UNIT IS NAMED, everywhere below: `<directory>_<file.ext>`. $UNITS spans TWO directories —
# this one and ../src — so a bare basename is not a name: two `.c` files called the same thing in
# the two would share one object path and one optimisation level, and the second compile would
# overwrite the first's object with no warning from anything here. The extension is kept because it
# is part of the file, not because it separates anything: `wonderboy_os.s` and a hypothetical
# `wonderboy_os.c` in one directory are told apart by it, but two directories are not.
unit_key() { printf '%s_%s' "$(basename "$(dirname "$1")")" "$(basename "$1")"; }

# THE DEFAULT IS -O3 (the banner above). This is its exception list, and every entry carries the
# number that put it there: the unit's -O2 -> -O3 text growth, against what the frame did with it.
# One list rather than a level repeated at each compile (CLAUDE.md §5), so that "why is this file
# built differently" is answered where the difference is made.
UNITS_BUILT_AT_O2=(
  src_behavior.c            # +16,818 B — the largest growth in the tree and the worst trade in it:
                            #   at -O2 the behaviour tier costs 1.8 K cycles a frame
                            #   (actor_behavior_pass, inclusive: 54.7 K -> 56.5 K), so those bytes
                            #   bought ~9 KB per K cycles, against src_blit.c's 16,660 B for the
                            #   sprite blit's 79 K, which is 0.2
  src_rad.c                 # +4,776 B — the .RAD depacker runs in the BOOT slices, never in a frame
  src_boot.c                # +1,762 B — the composed boot slices themselves, same reason
  atari_wonderboy_main.c    # +2,148 B — the shim: entry, staging, the record. Boot and teardown
  atari_wonderboy_backend.c # +1,360 B — the shim's kit surface. Its one hot routine is
                            #   `sched_poll16`, and that is flip_screen's vblank SPIN, so what it
                            #   costs is the waiting and not the code around it: 162.6 -> 162.5
                            #   cycles a call at -O2, with the number of calls following the frame
                            #   rather than the compiler
)

# ...AND THE UNITS THAT MAY NEVER JOIN IT. The four levers measured on 2026-08-25 exist ONLY at -O3,
# so moving one of these to the list above would hand its bytes back and take the WORK in the frame
# with them — silently, because nothing in `make test` and nothing else in this script measures a
# cycle. Whether that work shows up as frame RATE is a separate question, and scroll.c's re-measured
# entry below is the one that answers it "not today": read each entry for what it actually claims.
#   blit.c   the column loop is unrolled by a `#pragma GCC unroll` that -O2 DECLINES (the trip count
#            is a runtime `width->columns` until constant propagation makes it a literal), and the
#            register file only scalarises once those subscripts are constants: 74.2 K -> a fallback
#            of 153 K cycles a frame, and the clone assertion after the link is the tripwire
#   scroll.c NOT for its sixteen copy bodies, which is what this entry used to say: those are
#            instruction-for-instruction IDENTICAL at -O2 (compared per symbol, 2026-08-26 —
#            their runs are spelt out and their splits are compile-time constants, so there is
#            nothing left for -O3 to do to them). It is the ENGINE above them. At -O2 the
#            serve/step/fill tier stops being inlined into the queue drain:
#            bg_scroll_run_queue 9,790 -> 14,205 cycles a call and bg_scroll_serve_requests
#            296 -> 403, which is +4.4 K cycles a frame for 4,166 B of text. The FRAME itself
#            does not move (328.4 K, 24.40 fps either way) because flip_screen's vblank spin
#            absorbs it — and that is the reason to KEEP the -O3 rather than to spend it: the
#            frame sits ~8 K over two whole vblanks, so 4.4 K is over half the headroom left
#            before a third vblank comes back and takes a third of the frame rate with it
#   hud.c    -fipa-cp-clone specialises the glyph plotter per digit width (2,100 -> 833 cycles)
#   sound.c  the tick tier's d16(a3) addressing — 76 absolute address constants down to 10
UNITS_THAT_MUST_STAY_AT_O3="src_blit.c src_scroll.c src_hud.c src_sound.c"

# -O2 for the units named above, -O3 for every other one.
opt_level_for() { in_list "$(unit_key "$1")" "${UNITS_BUILT_AT_O2[*]}" && echo -O2 || echo -O3; }

# THE SPECIALISATION HAPPENED AT ALL — which is the whole of what this floor claims. -fipa-cp-clone
# is what turns blit.c's one algorithm into bodies with `width` a constant in each, which is what
# gives the `#pragma GCC unroll` above a trip count to work on; ZERO clones means none of that
# happened, and that is the failure being watched for.
#
# IT IS NOT A COUNT OF WIDTHS, and must not be read as one. How many clones GCC emits, and what it
# names them, is GCC's business: it clones on the `clipped` axis as well as the width one, it merges
# bodies that come out identical, and `.constprop.N` is a naming artefact of the pass rather than a
# per-width guarantee. Today's build happens to carry four. A floor set at today's number would
# fail on a compiler upgrade that emitted three good clones, and pass on one that emitted four
# useless ones — so the floor is 1, the honest claim.
#
# THE REGRESSION THIS STANDS IN FOR — the frame losing ~79 K cycles because the column loop went
# back to being runtime-counted — IS ONLY REALLY CAUGHT BY `python3 atari/profile.py ours`. That is
# the surface; this is a cheap tripwire in front of it, and neither `make test` nor anything else in
# this script measures a cycle.
BLIT_WIDTH_CLONES_MIN=1

# Comments stripped WITHOUT expanding includes: -fpreprocessed tells the preprocessor its input is
# already preprocessed, so `#include` is left alone while comments and line splices go. Both scans
# below need that — a core's prose mentions the very identifiers they hunt for, and the first draft
# of each tripped on its own documentation.
strip_comments() { $CC -fpreprocessed -E -P "$1" 2>/dev/null; }

# ---- the claim in the banner, measured ---------------------------------------------------------
# -DWB_ON_TARGET is passed HERE and nowhere else, so every `#ifdef WB_ON_TARGET` arm in ../src/ must
# vanish for the differential build. Asserted at the SOURCE, by preprocessing each core exactly as
# kit.mk does — without the define — and requiring that not one `wb_target_` token survives. A
# source-level check rather than an artifact comparison because it holds whether or not a .so has
# been built.
#
# EVERY CORE, not the one that carries a guard today. TWO did when this was written (game.c and
# stage.c) and naming them made the scan blind to a third: batch 44 phase C exported stage.c's
# shifter sink precisely so that boot.c would NOT grow one, and a scan that only ever looked at two
# files could not have said so.
#
# AND IT IS BLIND TO A SECOND COPY OF THE ARM, WHICH IT WAS ONCE CLAIMED TO CATCH. This scan
# preprocesses WITHOUT the define, so the contents of any `#ifdef WB_ON_TARGET` arm are GONE before
# the grep ever runs — and the `nm` half below is blind the same way, because the .so is built
# without the define too. What this pair really measures is the thing it is named for: that no core
# reaches `wb_target_*` OUTSIDE a guard, i.e. that the differential build is the same code it was.
# `assert_the_sink_arm_lives_in_one_place` below is the check that a second guard would trip, and it
# has to look at the source WITH the comments stripped and WITHOUT the preprocessor.
assert_the_differential_build_is_unchanged() {
  local HOST_CC="${CC_HOST:-cc}" LEAKED
  for CORE in $CORES; do
    LEAKED=$($HOST_CC -E -I"$REC/include" -I"$KIT/include" "$CORE" 2>/dev/null \
             | grep -c 'wb_target_' || true)
    [ "$LEAKED" = "0" ] || {
      # NO BACKTICKS IN THESE STRINGS. The first draft wrote a tidy `make test` in the message and
      # bash ran it: inside double quotes a backtick pair is command substitution, so the failure
      # path silently launched the whole differential suite before printing anything. Found when the
      # RED-check's output carried a clang error no part of this script compiles.
      echo "ERROR: $CORE reaches wb_target_* WITHOUT -DWB_ON_TARGET ($LEAKED references)."
      echo "       The differential .so would link the on-target arm, and the suite would no longer"
      echo "       be measuring the same code as before. Check the #ifdef guard."
      exit 1; }
  done
  # ...and the same claim from the other end when the artifact is there: the built .so must not name
  # the shim at all. Conditional because build/ is gitignored and a fresh clone has no .so yet.
  if [ -f "$REC/build/libwonderboy.so" ] && nm "$REC/build/libwonderboy.so" 2>/dev/null \
       | grep -q 'wb_target_'; then
    echo "ERROR: $REC/build/libwonderboy.so names wb_target_* — the differential build is NOT unchanged"
    exit 1
  fi
}

# ---- ...and the second copy of the arm, which the scan above CANNOT see -----------------------
# The port's shifter sink is ONE module — `../include/shifter.h` declares it and holds the off-target
# empties, `../src/shifter.c` defines the on-target stores — and that is the whole point of the
# module: a `WB_ON_TARGET` arm written out twice is one correction away from two files writing to
# different places on the one build where the write is real (batch 44 phase F folded two such copies
# together; phase C had already stopped a third).
#
# NOTHING ABOVE WOULD NOTICE A FOURTH. The scan above preprocesses without the define, so a new
# `#ifdef WB_ON_TARGET` arm in another core disappears before its grep. So the guard is counted HERE,
# at the source: comments stripped (the sink module's own prose names the macro, and so does
# ../include/game.h's pointer to it) and the preprocessor NOT run, over every core and every project
# header. The allowed set is exactly the two files the module is, named once.
SINK_MODULE_FILES="include/shifter.h src/shifter.c"

assert_the_sink_arm_lives_in_one_place() {
  local FOUND
  FOUND=$(for FILE in "$REC"/include/*.h "$REC"/src/*.c; do
            if strip_comments "$FILE" | grep -q 'WB_ON_TARGET'; then echo "${FILE#"$REC"/}"; fi
          done | sort | tr '\n' ' ')
  FOUND="${FOUND% }"
  [ "$FOUND" = "$SINK_MODULE_FILES" ] || {
    echo "ERROR: the WB_ON_TARGET arm is in [$FOUND], and the sink module is [$SINK_MODULE_FILES]."
    echo "       A second copy of the arm is one correction away from two files writing to two"
    echo "       different places on the one build where the write is real, and NOTHING ELSE in this"
    echo "       script can see it: assert_the_differential_build_is_unchanged preprocesses without"
    echo "       the define, so the new arm's contents are gone before its grep runs. Reach the sink"
    echo "       through ../include/shifter.h, or move the module and update SINK_MODULE_FILES."
    exit 1; }
}

# ---- the seam tripwire the symbol scan CANNOT be --------------------------------------------
# The post-link scan further down looks for MODEL SYMBOLS, and it is blind to the half of the kit
# that has none: `os_random`, `os_giaccess`, `os_bconin`, `os_bconstat`, `os_crawio`, `os_super` and
# the whole staged-file family are `static inline` in the kit's os.h. A core that started calling one
# would compile THE MODEL into the PRG — no undefined symbol, no g_* global, nothing for `nm` to
# find — and this build would happily "verify" the reconstruction against a keyboard that does not
# exist. That is precisely the false-green class the whole project is built to refuse.
#
# So the cores are scanned at the SOURCE for calls to anything named os_*, and the allowed set is
# named here. It is two: `os_in_image` is pure arithmetic over OS_IMAGE_SIZE and correct unchanged,
# and `os_refused` compiles to an inline identity under -DOS_NO_REFUSAL_TALLY. Anything else is a
# model with no on-target meaning, and adding one to this list is a decision about what the machine
# really answers — which is the decision this check exists to force someone to make in the open.
OS_HELPERS_WITH_AN_ON_TARGET_MEANING="os_in_image|os_refused"

assert_no_core_calls_a_modelled_os_helper() {
  local FOUND
  FOUND=$(for CORE in $CORES; do
            strip_comments "$CORE" \
              | grep -oE '\bos_[a-z_0-9]+[[:space:]]*\(' \
              | grep -oE '\bos_[a-z_0-9]+' \
              | grep -vxE "$OS_HELPERS_WITH_AN_ON_TARGET_MEANING" \
              | sed "s|^|$(basename "$CORE"): |"
          done | sort -u || true)
  [ -z "$FOUND" ] || {
    echo "ERROR: a core calls a MODELLED os.h helper, which is static inline and so would be"
    echo "       compiled into the PRG with nothing for the symbol scan to catch:"
    echo "$FOUND" | sed 's/^/         /'
    echo "       Give it a real on-target meaning (wonderboy_backend.c) and add it to"
    echo "       OS_HELPERS_WITH_AN_ON_TARGET_MEANING, or do not call it from a core."
    exit 1; }
}


# ---- the trap wrappers' register discipline, which NOTHING ELSE HERE CAN SEE ------------------
#
# THE SIBLING PROJECT'S FIRST REAL-HARDWARE BUG CLASS, pre-empted as a build gate. TOS preserves
# only %d3-%d7/%a3-%a6 across a trap, while m68k GCC believes %d2 and %a2 are callee-saved and
# caches live values in them across a call to any wrapper in wonderboy_os.s. A wrapper that does not
# save that pair silently corrupts one variable IN ITS CALLER — `docs/on-target-execution.md` has
# the measurement, where it cost BuggyBoy three bombs on the STE and was green under every
# differential the project had.
#
# EVERY WRAPPER IN THIS DIRECTORY ALREADY DOES IT (audited, batch 44 phase G: ten routines, ten
# `movem` pairs, argument offsets at +12 to match). What did NOT exist was anything that would
# notice if one stopped: the fault is invisible to `make test` (the differential does not run this
# file), to every `smoke.py` mode (Hatari's TOS happens not to clobber the pair), and to the
# compiler. So the discipline is asserted at the SOURCE, which is the one place it is legible.
#
# ROUTINE BY ROUTINE AND NOT FILE-WIDE, because a file-wide grep would be satisfied by ONE wrapper
# saving the pair while a new one next to it did not.
#
# THE SCAN ITSELF LIVES IN `tools/`, because the class is the WORKSPACE'S and not this game's: every
# port here compiles C against TOS through a hand-written `.s`, and the bug that motivates the gate
# was BuggyBoy's. `tools/assert_trap_registers.sh` has the argument, the routine-close rule and its
# own two mutation controls; this file supplies the one thing that is project policy — HOW MANY
# wrappers there are to find.
WONDERBOY_TRAP_WRAPPERS=10   # audited batch 44 phase G; `_start`'s Pterm0 never returns and is not one

echo ">> check the seam (the differential build, and the static-inline half the symbol scan misses)"
assert_the_differential_build_is_unchanged
assert_the_sink_arm_lives_in_one_place
assert_no_core_calls_a_modelled_os_helper
bash "$TOOLS/assert_trap_registers.sh" --expect "$WONDERBOY_TRAP_WRAPPERS" "$HERE/wonderboy_os.s"

# THE UNITS, IN LINK ORDER. `wonderboy_os.s` FIRST and everything else after it, because `_start`
# is its first instruction and GEMDOS enters the .PRG at the first byte of text — the check just
# below the link is what says so, and it is the reason this list is an ORDER and not a set.
UNITS="$HERE/wonderboy_os.s $HERE/wonderboy_main.c $HERE/wonderboy_backend.c $CORES"

# ...AND BOTH LEVEL LISTS ARE PINNED TO IT. A renamed or deleted unit would leave its name in one of
# them doing nothing — UNITS_BUILT_AT_O2 would stop buying its floppy bytes, and worse,
# UNITS_THAT_MUST_STAY_AT_O3 would stop protecting anything while still reading as a guard — a
# decision reverting itself in silence, which is exactly what naming the lists was meant to prevent.
# Checked rather than trusted, because the lists and $UNITS are edited for unrelated reasons.
UNIT_KEYS="$(for UNIT in $UNITS; do printf '%s ' "$(unit_key "$UNIT")"; done)"
assert_names_a_real_unit() {  # $1 = the key, $2 = the list it came from
  in_list "$1" "$UNIT_KEYS" || {
    echo "ERROR: $2 names '$1', which is not a unit this build compiles — so it is doing"
    echo "       nothing, and whatever replaced it is being built at the default -O3 with no"
    echo "       decision behind it. Update the list; each entry's measurement says what to redo."
    echo "       Units are keyed <directory>_<file.ext>, e.g. src_blit.c / atari_wonderboy_main.c."
    exit 1; }
}
for UNIT_AT_O3 in $UNITS_THAT_MUST_STAY_AT_O3; do
  assert_names_a_real_unit "$UNIT_AT_O3" UNITS_THAT_MUST_STAY_AT_O3
done
for UNIT_AT_O2 in "${UNITS_BUILT_AT_O2[@]}"; do
  assert_names_a_real_unit "$UNIT_AT_O2" UNITS_BUILT_AT_O2
  if in_list "$UNIT_AT_O2" "$UNITS_THAT_MUST_STAY_AT_O3"; then
    echo "ERROR: UNITS_BUILT_AT_O2 names '$UNIT_AT_O2', which is one of the units whose -O3 codegen"
    echo "       the frame is MADE of (UNITS_THAT_MUST_STAY_AT_O3, with the measurement per unit)."
    echo "       Dropping it to -O2 buys floppy bytes and pays for them in cycles that nothing here"
    echo "       and nothing in \`make test\` would report. Take the bytes somewhere else, or"
    echo "       re-measure this unit with atari/profile.py and move it out of that list first."
    exit 1
  fi
done

echo ">> compile + link (base 0, keep relocs)"
# ONE OBJECT PER UNIT, so each can carry its own -O; the objects are then linked in the same order
# the sources used to be passed in, with the same flags. Named by `unit_key` — the same key the
# level list is written in — so that units from the two source directories cannot collide here
# either, and so that "which object is this file's" has one answer.
OBJ="$BUILD/obj"; mkdir -p "$OBJ"; rm -f "$OBJ"/*.o
OBJECTS=""
for UNIT in $UNITS; do
  OBJECT="$OBJ/$(unit_key "$UNIT").o"
  $CC $CFLAGS "$(opt_level_for "$UNIT")" $DEF -c "$UNIT" -o "$OBJECT"
  OBJECTS="$OBJECTS $OBJECT"
done
# CFLAGS and not $DEF: the link still needs -m68000/-nostdlib/-ffreestanding to pick the right
# libgcc and startup behaviour, while the -D's are preprocessor-only and now belong to the -c step.
$CC $CFLAGS -T "$HERE/tos.ld" -Wl,--emit-relocs $OBJECTS -lgcc -o "$BUILD/wonderboy.elf"

# _start must sit at the very first byte of text (GEMDOS enters there).
ENTRY=$(m68k-elf-nm "$BUILD/wonderboy.elf" | awk '$3=="_start"{print $1}')
[ "$ENTRY" = "00000000" ] || { echo "ERROR: _start not at 0 (got $ENTRY)"; exit 1; }

# ...AND THE -O3 CODEGEN ITSELF, CHECKED RATHER THAN ASSUMED. Everything above verifies WHAT is in
# the PRG; this is the one check on HOW it was compiled, and it is here because the level is now a
# per-unit decision a future edit can reverse in one line of a bash array. The clones are the visible
# end of the whole chain — constant propagation specialises blit_sprite_rows per `blit_width`, which
# gives the column loop a constant trip count to unroll, which gives SRA constant subscripts to put
# the register file in registers. No clones means none of it happened.
BLIT_CLONES=$(m68k-elf-nm "$BUILD/wonderboy.elf" | grep -c 'blit_sprite_rows\.constprop' || true)
[ "$BLIT_CLONES" -ge "$BLIT_WIDTH_CLONES_MIN" ] || {
  echo "ERROR: the linked ELF has $BLIT_CLONES blit_sprite_rows.constprop clone(s), not"
  echo "       $BLIT_WIDTH_CLONES_MIN or more — the sprite blit was NOT specialised per width, so"
  echo "       its column loop is a runtime-counted loop again and the frame has just lost ~79 K"
  echo "       cycles. The usual cause is blit.c reaching UNITS_BUILT_AT_O2, or -fipa-cp-clone"
  echo "       going away from -O3; ../STATUS.md's \"## Performance\" has the measurement."
  exit 1; }

# NONE of the kit's off-target models may have been linked in. The build leaves their sources out,
# but a header that grew a `static inline` fallback — or a core that started calling one — would
# reintroduce the model silently and this build would "verify" against it. Checked, not trusted.
for MODEL in g_hw_reset g_psg_reset g_sched_reset g_dosound g_os_refusal_reset sched_poll8; do
  if m68k-elf-nm "$BUILD/wonderboy.elf" | awk '$3=="'"$MODEL"'"{found=1} END{exit !found}'; then
    echo "ERROR: the off-target model symbol $MODEL is in the PRG — a kit src/*.c leaked into the link"
    exit 1
  fi
done

# ...and the mirror: the SIX the backend owes must all be there, so a core that stopped calling one
# cannot quietly shrink the surface README.md enumerates. Six and not seven: the surface is seven
# symbols, and the seventh — `os_refused` — is deliberately undefined here (see the banner).
#
# `disk_read_file` is the newest of the six and the one whose absence would be quietest. It is a
# REAL symbol rather than a `static inline` precisely so this loop can see it (the kit's own
# include/disk.h says so in as many words), and the kit's src/disk.c — the staged-file half — is
# left out of the link exactly as src/hw.c and src/psg.c are.
for SYM in hw_read8 psg_port_read psg_port_write sched_wait8 sched_poll16 disk_read_file; do
  m68k-elf-nm "$BUILD/wonderboy.elf" | awk '$3=="'"$SYM"'"{found=1} END{exit !found}' \
    || { echo "ERROR: $SYM is not in the PRG — wonderboy_backend.c no longer covers the surface"; exit 1; }
done

# Drop .debug_* (and their .rela.debug_*, which carry odd-offset fixups mkprg would choke on);
# keep .rela.text/.rela.data, the R_68K_32 fixups the GEMDOS relocation table is built from.
m68k-elf-strip --strip-debug "$BUILD/wonderboy.elf"

echo ">> objcopy -> flat binary"
m68k-elf-objcopy -O binary "$BUILD/wonderboy.elf" "$BUILD/wonderboy.bin"

echo ">> wrap -> GEMDOS .PRG"
python3 "$HERE/mkprg.py" "$BUILD/wonderboy.elf" "$BUILD/wonderboy.bin" "$BUILD/$PRG"

cp "$BUILD/$PRG" "$DISK/$PRG"
cp "$BUILD/$PRG" "$BUILD/WB-$MODE.PRG"
# THE IMAGE IS KEPT PER MODE TOO, and it is not filing: the modes stage DIFFERENT images (m1 the
# program plus seeds at 136,408 bytes, m2 the original's post-boot RAM at 523,272) and the .PRG has
# its size compiled in. smoke.py runs five modes against one drive, so without a per-mode copy to
# re-stage from, `smoke.py m2` after `build.sh m1` boots the frame build over the M1 image — which
# is how the first draft failed, loudly here but silently for any future pair whose sizes agree.
cp "$DISK/WB.IMG" "$BUILD/WB-$MODE.IMG"
# The palette belongs to the FRAME modes alone. Keyed on the MODE and not on the file's existence: a
# `[ -f ... ] && cp ...` would have copied m2's leftover into an m1 build (measured, harmlessly —
# nothing reads it there), and as the tail of a `set -e` script a false test aborts the build.
if is_frame_mode "$MODE"; then
  cp "$DISK/PENS.IMG" "$BUILD/WB-$MODE.PENS"
else
  rm -f "$DISK/PENS.IMG" "$BUILD/WB-$MODE.PENS"
fi
ls -l "$DISK/$PRG" "$DISK/WB.IMG"
