#!/bin/bash
# Build ZYNAPS.PRG from the verified reconstruction with the m68k-elf cross toolchain, and stage a
# GEMDOS drive for Hatari.
#
#   build.sh title      -> M1: the boot's verified slices up to 0x101ba, the title picture on
#                          screen, the title tune (0x0b) ticking off the reconstruction's own
#                          vertical-blank handler, then a clean hand-back and Pterm.
#   build.sh titlefault -> M1's NEGATIVE CONTROL: identical, with ONE PEN corrupted on its way to
#                          the shifter and nothing else. The pens and the rendered picture must go
#                          red while the framebuffer, the trap ledger and the PSG timeline stay
#                          green — and `smoke.py titlefault` inverts its verdict.
#   build.sh game       -> M2: THE WHOLE PROGRAM — the rest of the boot, the attract loop, the
#                          section chain, the frame loop and the endings, out of verified slices in
#                          the original's own order. Headless: it stops at a declared frame count
#                          and dumps its framebuffer, pens and entity table at declared frames, so
#                          `smoke.py game` can compare them against the shipped binary frame for
#                          frame.
#   build.sh gamefault  -> M2's NEGATIVE CONTROL: the same build with ONE STEP of the section chain
#                          dropped and nothing else. What the game DRAWS must go red at every frame
#                          while the pens, the exit path and the record stay green.
#   build.sh play       -> the game with both budgets out of reach, so it runs until the window is
#                          closed. `run.sh` gives it a screen, sound and a joystick — the one input
#                          path no headless check can exercise.
#   build.sh playtitle  -> the M1 title build with its anchor out of reach, kept for bisecting.
#
# ...and a SECOND argument picks the MEDIUM, `gemdos` (the default) or `floppy`:
#
#   build.sh play floppy -> ...plus disk/ZYNAPS.ST: a BOOTABLE FAT12 floppy laid out like the
#                          original's, with our .PRG where the game's used to be
#                          (AUTO\ZYNAPS17.PRG, the name TOS's desktop looks for). That is the form
#                          that goes onto the real STE.
#   build.sh floppy     -> the legacy spelling of `title floppy`; `smoke.py floppy` names it.
#
# Writes disk/{ZYNAPS.PRG,ZYNAPS.IMG} plus the game's own data files, and keeps
# build/ZYNAPS-<mode>.PRG so a check needing two builds in sequence does not have to rebuild.
# build/ and disk/ are gitignored (the repo .gitignore already covers
# projects/*/recreate/atari/{build,disk}).
#
# THE CORES ARE COMPILED UNCHANGED — no `-D` reaches ../src or ../include, and the checks below
# measure that rather than asserting it in prose. The seam is now the INCLUDE PATH plus ONE omitted
# directory:
#   * shim_include/ shadows FOUR of the kit's headers, and in two different ways:
#       - `os.h` (real GEMDOS, no-op Super) and `sched.h` (uncapped busy waits) shadow PARTIALLY,
#         replacing what they must and `#include_next`ing the rest;
#       - `hw.h` and `psg.h` shadow OUTRIGHT. The kit's own hw.h asks a target build to supply
#         `hw_read8`, `hw_write8/16/32` and the three read-modify-writes itself, and psg.h says the
#         same of `psg_port_write`; supplying all eight as `static inline` is what lets a caller's
#         CONSTANT address fold the address ladder and the store-classification chain away (205
#         cycles a call for a 24-cycle store, before). They cannot `#include_next`: the kit declares
#         those eight `extern`, and C forbids redeclaring one `static`. The "shadows define exactly
#         the doors the kit declares" gate below is what ties the two halves together instead, and
#         `psg_port_read` is the one name deliberately left out — a core that acquired a PSG read
#         then fails to COMPILE rather than reading a real chip with no surface behind it.
#     zynaps_backend.c keeps the counters those doors bump and the one door that is a protocol
#     rather than a store (the shifter's video base).
#     WHAT THE CORES SEE GREW WITH THIS, and it is why hw.h includes only CORE and KIT headers:
#     every core says `#include "hw.h"`, so anything that header pulls in lands in six verified
#     translation units — `zynaps_target.h` among them, if it were allowed to, taking `zy_image_base`
#     and the whole shim surface with it while the census below stayed green.
#   * ALL of the kit's src/ is left out — its own headers say so (psg.c, hw.c, sched.c: "Off-target
#     only ... a build for the real Atari writes the ports itself"). EVERY core in ../src is built:
#     there is no exclusion any more, because src/irq_hw_offtarget.c's three empty bodies became
#     ordinary `hw_write*` calls in video.c and irq.c.
#     ONE OF THE THREE WAS NOT AN EMPTY BODY ON THIS SIDE, and dropping the exclusion dropped it:
#     zynaps_backend.c's `mfp_ack_timer_b` was a real READ-MODIFY-WRITE (`&= ~bit`), and what
#     ../src/irq.c ships is a plain store of 0 — which acknowledges every in-service MFP channel
#     rather than Timer B's. It is dormant in M1 (nothing starts a timer) and README.md's Unpinned 2
#     is where it is carried; it is named here so that this list is not read as "nothing was lost".
set -euo pipefail

# The pen `titlefault` corrupts. THREE is not arbitrary and the reason is the control's own
# `picture` arm: it has to be a pen the title picture actually uses, or the arm would fail for a
# reason about coverage rather than about the fault (the sibling project's recorded trap). smoke.py
# does not take the number from here — the binary publishes it in STATE.BIN — but it DOES decode
# ZYNPIC.PIC and refuse a fault pen that is not on screen, so this line cannot go stale silently.
FAULT_PEN=3

# THE MEDIUM IS A FLAG, NOT A MODE, and that is README.md's Unpinned 14 discharged. It used to be a
# fourth entry in the enum below, which meant `build.sh floppy` produced a SECOND COPY of the title
# binary under another name and the medium that actually goes on the STE was the one medium whose
# checks had never been shown able to go red. Now any mode can be built onto a floppy:
#
#   build.sh game            -> build/ZYNAPS-game.PRG on the GEMDOS drive
#   build.sh game floppy     -> ...the same binary, plus disk/ZYNAPS.ST with it in AUTO\
#   build.sh floppy          -> LEGACY SPELLING of `title floppy`, kept because README.md and
#                               `smoke.py floppy` both name it and M1's evidence is filed under it.
MODE="${1:-title}"
MEDIUM="${2:-gemdos}"
if [ "$MODE" = "floppy" ]; then MODE=title; MEDIUM=floppy; fi
case "$MEDIUM" in
  gemdos|floppy) ;;
  *) echo "usage: build.sh <mode> [gemdos | floppy]"; exit 2 ;;
esac

case "$MODE" in
  title)      DEF="" ;;
  titlefault) DEF="-DZY_FAULT_PEN=$FAULT_PEN" ;;
  # ---- M2 --------------------------------------------------------------------------------------
  # THE WHOLE PROGRAM: the rest of the boot, the attract loop, the section chain, the frame loop
  # and the endings, composed out of verified slices in the original's own order. `game` is the
  # HEADLESS form — it stops at a declared `frame_loop_once` count and dumps its framebuffer, pens
  # and entity table at declared frames so `smoke.py game` can compare them against the shipped
  # binary at the same frames.
  game)       DEF="-DZY_PHASE=1" ;;
  # M2's NEGATIVE CONTROL: the game build with ONE STEP of the section chain dropped and nothing
  # else — the two `bsr`s at 0x1085a, the player intro screen and the whole-panel repaint. A dropped
  # composition step is the defect this milestone is most exposed to, since the whole of M2 is calls
  # to verified slices and what can be wrong is the order and the set. The framebuffer and the
  # entity table must go red at every sampled frame while the pens, the exit path and the program's
  # own record stay green; `smoke.py gamefault` inverts its verdict for that split.
  # zynaps_main.c's `play_one_game` says why this fault and not the one that was tried first.
  gamefault)  DEF="-DZY_PHASE=1 -DZY_GAME_FAULT=1" ;;
  # ...AND THE ONE A PERSON PLAYS, which is the same code with both budgets moved out of reach: no
  # frame limit, no anchor, no dumps, so the game runs until the window is closed. At 50 Hz 2^32
  # vertical blanks is about 2.7 years and 2^32 frames rather longer.
  #
  # `play` USED TO BE THE TITLE BUILD and is now the game build, which is the milestone in one line.
  play)       DEF="-DZY_PHASE=1 -DZY_SMOKE_VBLS=0xffffffffu -DZY_GAME_FRAMES=0xffffffffu \
                   -DZY_FRAME_SAMPLES=0u" ;;
  # The M1 title build with its anchor moved out of reach — kept because it is the one build whose
  # every surface `smoke.py title` has certified, and the thing to look at when the game build is
  # being bisected.
  playtitle)  DEF="-DZY_SMOKE_VBLS=0xffffffffu" ;;
  *) echo "usage: build.sh [title | titlefault | game | gamefault | play | playtitle]" \
          "[gemdos | floppy]"; exit 2 ;;
esac

HERE="$(cd "$(dirname "$0")" && pwd)"
REC="$(cd "$HERE/.." && pwd)"                             # recreate/
TOOLS="$(cd "$REC/../../../tools" && pwd)"                # the workspace's game-agnostic tooling
KIT="$TOOLS/recreate_kit"                                 # the shared harness
BIN="$REC/../bin"                                         # projects/zynaps/bin
BUILD="$HERE/build"; DISK="$HERE/disk"
PRG="ZYNAPS.PRG"
mkdir -p "$BUILD" "$DISK"
# A FAILED BUILD MUST LEAVE NO PRG BEHIND FOR smoke.py TO RUN. Every gate below exits non-zero, but
# the per-mode artifact from the previous successful build would still be on disk, and smoke.py reads
# `build/ZYNAPS-<mode>.PRG` by name — so a green smoke after a red build is the stale binary passing,
# not this tree (measured 2026-08-29: the os_in_image gate reddened and the old title PRG smoked OK).
rm -f "$BUILD/ZYNAPS-$MODE.PRG" "$BUILD/$PRG"

CC=m68k-elf-gcc

# ---- stage the drive ---------------------------------------------------------------------------
# The GAME'S OWN DATA FILES, copied rather than symlinked: Hatari's GEMDOS drive emulation walks a
# host directory, and the original boots from exactly this set (projects/zynaps/tools/boot_shots.py,
# `gemdos` mode, drives `bin/disk`). The .PRG goes at the ROOT and not in AUTO\, because smoke.py
# starts it with `--auto` and the game resolves its lowercase filenames against the current
# directory — which is the root either way.
echo ">> stage drive"
PY="$REC/.venv/bin/python"; [ -x "$PY" ] || PY=python3
# A PREVIOUS RUN'S OUTPUTS ARE NOT DATA FILES, and on a floppy build they are not harmless: every
# `.BIN` the shim wrote last time is still sitting on the staged drive, and `mkfloppy.py` puts the
# whole drive on the volume — measured at 79 files and 588 KB, most of it last run's frame dumps.
# The game's own data files are .PIC/.DAT/.MAP and are never `.BIN`, so the pattern is exact.
rm -f "$DISK"/*.BIN
find "$BIN/disk" -maxdepth 1 -type f -exec cp {} "$DISK/" \;
DATA_FILES=$(find "$DISK" -maxdepth 1 -type f ! -name 'ZYNAPS.*' ! -name '*.BIN' | wc -l | tr -d ' ')
echo "   $DATA_FILES data files from $BIN/disk (bin/disk/AUTO is the ORIGINAL's launcher, not ours)"

# The staged image comes FIRST: its byte length is the one source of truth for how much
# zynaps_main.c must read back in, and it is passed straight to the compiler.
"$PY" "$HERE/gen_image.py" "$BIN/ZYNAPS17.PRG" "$DISK/ZYNAPS.IMG"
IMG_BYTES=$(wc -c < "$DISK/ZYNAPS.IMG" | tr -d ' ')       # BSD wc pads with spaces

# ...and the base it is staged AT is scraped from ../project.toml rather than written here. That
# file is where 0x10000 is argued for ("names.txt addresses are Ghidra addresses at this base, so it
# must not move"), and a second spelling could drift from the loader gen_image.py uses.
LOAD_BASE=$(sed -n 's/^load_base *= *\(0x[0-9a-fA-F]*\).*/\1/p' "$REC/project.toml")
[ -n "$LOAD_BASE" ] || { echo "ERROR: no load_base in $REC/project.toml"; exit 1; }
DEF="$DEF -DPROGRAM_BYTES=$IMG_BYTES -DZY_LOAD_BASE=$LOAD_BASE"

# ---- the trap-register scan --------------------------------------------------------------------
# The workspace's one hardware-only bug class that nothing else can see: TOS preserves %d3-%d7 and
# %a3-%a6 across a trap, GCC believes %d2/%a2 survive too, and a wrapper that does not save the pair
# silently corrupts a variable in its C caller. Invisible to every differential in this project, to
# the compiler, and often to emulation. `--expect` is the count of wrappers the scan EVALUATED, so a
# regex that stopped matching reds here instead of passing vacuously over a file it cannot parse.
#
# ELEVEN: Fcreate, Fopen, Fclose, Fread, Fwrite, Super, zy_leave_supervisor, Physbase, Logbase,
# Getrez, Setscreen. `_start` also traps (Pterm0) and is exempt by the scan's own rule — it never
# returns, so there is no caller left to corrupt.
TRAP_WRAPPERS=11
echo ">> trap-register scan ($TRAP_WRAPPERS wrappers)"
"$TOOLS/assert_trap_registers.sh" --expect "$TRAP_WRAPPERS" "$HERE/zynaps_os.s"

# ---- compile + link ----------------------------------------------------------------------------
# THERE IS NO -Wno-array-bounds, and that is deliberate: the flag would reach the VERIFIED CORES
#   too, in the one build where an out-of-bounds index reads live machine memory rather than the
#   harness's guarded image. The shim's own absolute-address dereferences carry a scoped
#   `#pragma GCC diagnostic` instead — see `read_vector` in zynaps_main.c.
# -fno-tree-loop-distribute-patterns: at -O2 GCC recognises zynaps_backend.c's hand-written
#   memcpy/memset loops and replaces them with calls to memcpy/memset — i.e. with themselves.
# -DOS_NO_REFUSAL_TALLY: the kit's os.h anticipates exactly this build and compiles `os_refused`
#   down to an inline identity, so its src/os_refusal.c is not needed. It also compiles away
#   `ikbd_send_cmd`'s give-up arm, which is the only place a core reaches the tally.
# shim_include FIRST: that is the whole seam (it shadows the kit's os.h, hw.h, psg.h and sched.h).
CFLAGS="-m68000 -O2 -fno-tree-loop-distribute-patterns -ffreestanding -fno-jump-tables \
        -fomit-frame-pointer -nostdlib -DOS_NO_REFUSAL_TALLY \
        -I$HERE/shim_include -I$REC/include -I$KIT/include -Wall -Wextra"

# EVERY core in ../src, as a wildcard rather than a typed list, so one added there is built here
# without anyone remembering to add it. There is no exclusion: the kit's write ledger retired
# src/irq_hw_offtarget.c, which was the only file a target build had to skip. What that cost is at
# the top of this script, under the seam description — one of the three bodies it excluded was a
# target-correct read-modify-write, not an empty stub.
# The KIT's src/ is excluded whole, stated in each of those files' own headers (psg.c, hw.c, sched.c:
# "Off-target only ... a build for the real Atari writes the ports itself").
CORES="$(ls "$REC"/src/*.c)"
[ -n "$CORES" ] || { echo "ERROR: no cores found in $REC/src"; exit 1; }

# ---- THE ASM TWINS ------------------------------------------------------------------------------
# ../src/asm/*.S are hand-written m68k TRANSCRIPTIONS of the original binary's own instruction
# sequences for the hottest cores, carrying those cores' C signatures. They are substituted for the
# C at the CALL SITE, through a per-subsystem seam macro in that subsystem's header — scroll.h's
# `ZY_SCROLL()`, sprite.h's `ZY_SPRITE()` — which the ASM_SEAM_DEFINES below switch over. The C
# stays compiled and stays the reference: ../test/test_scroll.py and ../test/test_sprite.py prove
# it equal to the original, ../test/test_asm_*.py prove each twin equal to it, both byte for byte
# over the whole image, so this substitution changes the program's SPEED and nothing else.
# See ../src/asm/README.md for the recipe and for what to do when adding the next one.
# `2>/dev/null || true` is what makes the message below REACHABLE: this script runs under
# `set -euo pipefail`, so a bare `ls` over an empty or missing src/asm/ aborts the shell on the
# assignment itself and the reader gets ls' "No such file or directory" instead of the diagnosis.
# (The CORES= line above has the same shape; it predates the twins and is left as it is.)
ASM_CORES="$(ls "$REC"/src/asm/*.S 2>/dev/null || true)"
[ -n "$ASM_CORES" ] || { echo "ERROR: no asm twins found in $REC/src/asm"; exit 1; }
# ONE DEFINE PER SEAM, SCRAPED FROM THE HEADERS RATHER THAN LISTED HERE. Each subsystem header
# guards its twin declarations with `#ifdef ZY_ASM_<SUBSYSTEM>` and defines a `ZY_<SUBSYSTEM>()`
# macro beside them; those `#ifdef`s are the source of truth for which seams exist, exactly as the
# `*_asm(` declarations below are the source of truth for which twins do. A hand-kept list here
# would be the same thing said twice, and the way it fails is the way this whole substitution fails
# — silently, with that subsystem's call sites back on the C, correct and several times too slow.
# (The gate below still catches a missing define; this is what stops there being one to miss.)
ASM_SEAM_DEFINES="$(grep -ohE '^#ifdef +ZY_ASM_[A-Z]+' "$REC"/include/*.h \
                    | awk '{print "-D" $2}' | sort -u | tr '\n' ' ')"
[ -n "$ASM_SEAM_DEFINES" ] || {
  echo "ERROR: no '#ifdef ZY_ASM_*' block in $REC/include/*.h, so no seam would be switched on and"
  echo "       every twin below would be linked but unreachable. The scrape has stopped matching the"
  echo "       headers."
  exit 1; }
DEF="$DEF $ASM_SEAM_DEFINES"

# COMPILED TO OBJECTS FIRST, so the two halves of the seam can be ASKED WHAT THEY DEFINE before
# they are linked together. The gate below is the whole reason this is not one `gcc` invocation.
# ---- THE ONE PER-FILE OPTIMISATION FLAG, AND WHY IT IS A LIST OF ONE ---------------------------
#
# A flag here reaches a VERIFIED CORE, so it is added per file and only where the generated code was
# read and the frame re-measured. `-funroll-loops` on ../src/video.c is that case:
# `shifter_upload_palette_longs` is a fixed EIGHT-iteration loop over the shifter's colour block,
# entered twice a vertical blank (`vbl_menu` and `timer_b_raster_isr` both call it), and at -O2 the
# compiler keeps the loop — so every one of the eight stores re-derives the register's bus address
# and pays the loop's own compare and branch. Unrolled it becomes eight `move.l <image>,$ff824x`
# with the addresses as immediates, which is the shape the original's `movem.l #$00ff,$ff8240.l`
# has. The codegen scans below are what say the unrolled form did not acquire the class-6
# effective-address shape, and they run on the linked binary rather than on this decision.
#
# -O3 GENERATES THE SAME EIGHT STORES HERE and is not used, because it would also change every
# other inlining decision in the file for no measured gain. NOTHING IS ADDED FOR ../src/scroll.c,
# where README.md's PERFORMANCE section measured `-funroll-loops` to be worth about 5% of the
# frame: those loops are being replaced by hand-written assembly twins, and a flag tuning code that
# is on its way out would be measured once and then be wrong.
CORE_UNIT_WITH_EXTRA_FLAGS=video.c
core_extra_flags() {
  case "$(basename "$1")" in
  "$CORE_UNIT_WITH_EXTRA_FLAGS") echo "-funroll-loops" ;;
  *)                             echo "" ;;
  esac
}

# ...AND THE TABLE PROVES IT NAMED A UNIT THIS BUILD ACTUALLY COMPILES. Every other measured claim
# in this script carries a control for the same reason: a `case` that stopped matching is
# indistinguishable from a clean build. If `../src/video.c` is renamed, or the palette upload moves
# to a unit of its own, the arm above silently returns nothing, `-funroll-loops` stops being applied
# and `shifter_upload_palette_longs` goes back from 756 cycles a call to 1,206 — with nothing red:
# `make test` measures no cycles, the EA scan checks the addressing SHAPE rather than whether the
# loop was unrolled, and smoke.py's pacing ceiling has 36 vblanks of slack for the loss to hide in.
# The sibling project does the same (projects/wonderboy/recreate/atari/build.sh's
# `assert_names_a_real_unit`, "so it is doing nothing ... a decision reverting itself in silence").
echo "$CORES" | grep -q "/$CORE_UNIT_WITH_EXTRA_FLAGS\$" || {
  echo "ERROR: core_extra_flags names '$CORE_UNIT_WITH_EXTRA_FLAGS', which is not one of the cores"
  echo "       this build compiles — so its -funroll-loops is being applied to nothing and the"
  echo "       palette upload has quietly gone back to its rolled form. Point it at the unit that"
  echo "       holds shifter_upload_palette_longs now, and re-measure with atari/profile.py."
  exit 1; }

OBJ="$BUILD/obj"
rm -rf "$OBJ"; mkdir -p "$OBJ"
echo ">> compile (base 0, keep relocs)"
SHIM_OBJECTS=""; CORE_OBJECTS=""
for source in "$HERE/zynaps_os.s" "$HERE/zynaps_main.c" "$HERE/zynaps_backend.c"; do
  object="$OBJ/shim_$(basename "${source%.*}").o"
  $CC $CFLAGS $DEF -c "$source" -o "$object"
  SHIM_OBJECTS="$SHIM_OBJECTS $object"
done
for source in $CORES; do
  object="$OBJ/core_$(basename "${source%.c}").o"
  $CC $CFLAGS $DEF $(core_extra_flags "$source") -c "$source" -o "$object"
  CORE_OBJECTS="$CORE_OBJECTS $object"
done
# The twins are `.S` (capital S) so cpp runs first, exactly as for the C above.
ASM_OBJECTS=""
for source in $ASM_CORES; do
  object="$OBJ/asm_$(basename "${source%.S}").o"
  $CC $CFLAGS $DEF -c "$source" -o "$object"
  ASM_OBJECTS="$ASM_OBJECTS $object"
done

# ---- THE DUPLICATE-SYMBOL GATE ------------------------------------------------------------------
# THE SHIM MAY NOT DEFINE A NAME A CORE DEFINES, and this is the check that says so in those words.
#
# It exists because the seam MOVES. `shifter_write_palette`, `shifter_clear_pen0` and
# `mfp_ack_timer_b` lived in zynaps_backend.c for as long as ../src/irq_hw_offtarget.c held their
# empty off-target bodies; when the kit's write ledger landed, the cores started defining all three
# themselves and the shim's copies became shadows of live code. The linker does object to that — but
# it objects as `multiple definition of 'shifter_clear_pen0'`, in the middle of a link line naming
# thirty files, and it says nothing about WHICH side is meant to own the name. This says it.
#
# It is also the half the linker cannot be relied on for: a build that ever acquires `-z muldefs`,
# or a variable that lands in COMMON, would link clean and run the WRONG BODY — the shim's stub in
# place of a verified core, with `make test` green on the core the machine never executes.
#
# Compared on DEFINED GLOBAL symbols only (nm's T/D/B/R), because a `static` on either side is not a
# collision and an undefined reference is the seam working as intended.
# `NF == 3` is not decoration: given several objects, nm prints a `file.o:` header and a blank line
# between them, and an awk that took $3 unconditionally would put empty strings in both lists — which
# `comm` then reports as a collision on every run, in a check whose whole job is to be quiet.
defined_globals() { m68k-elf-nm -g --defined-only $1 | awk 'NF == 3 {print $3}' | sort -u; }

# ...AND THE GATE PROVES IT CAN FAIL, on every run, in the TWO ways it can rot. The EA scan taught
# the first: a comparison that quietly stopped matching is indistinguishable from a clean build, so
# two synthetic lists with one name in common must produce exactly that name. The second is the half
# that scan does not have — `comm` over two EMPTY lists is also silent, and `defined_globals` is
# exactly the kind of thing that returns nothing when a tool's output shape moves under it (an nm
# that stopped printing three fields, a `-g` that stopped meaning "global"). So the lists are
# computed ONCE, asserted non-empty, and then compared.
GATE_CONTROL=$(comm -12 <(printf 'core_only\nshared_name\n') <(printf 'shared_name\nshim_only\n'))
[ "$GATE_CONTROL" = "shared_name" ] || {
  echo "ERROR: the duplicate-symbol gate named '$GATE_CONTROL' on a known collision, not"
  echo "       'shared_name' — it has rotted, and a clean report from it would mean nothing."
  exit 1; }

echo ">> duplicate-symbol gate (the shim may not define what a core defines)"
SHIM_SYMBOLS=$(defined_globals "$SHIM_OBJECTS")
CORE_SYMBOLS=$(defined_globals "$CORE_OBJECTS")
SHIM_COUNT=$(echo "$SHIM_SYMBOLS" | grep -c . || true)
CORE_COUNT=$(echo "$CORE_SYMBOLS" | grep -c . || true)
[ "$SHIM_COUNT" -gt 0 ] && [ "$CORE_COUNT" -gt 0 ] || {
  echo "ERROR: nm named $SHIM_COUNT shim and $CORE_COUNT core symbols — one of them is EMPTY, so the"
  echo "       comparison below would be silent whatever the objects hold. defined_globals' parse"
  echo "       has stopped matching m68k-elf-nm's output."
  exit 1; }
COLLISIONS=$(comm -12 <(echo "$SHIM_SYMBOLS") <(echo "$CORE_SYMBOLS"))
[ -z "$COLLISIONS" ] || {
  echo "ERROR: the shim defines $(echo "$COLLISIONS" | wc -l | tr -d ' ') symbol(s) that ../src now"
  echo "       defines too. The core owns the name; delete the shim's copy (and, if it was a seam,"
  echo "       check that what replaced it is one of the kit's own hw_*/psg_* doors):"
  echo "$COLLISIONS" | sed 's/^/         /'
  exit 1; }
echo "   $SHIM_COUNT shim symbols vs $CORE_COUNT core symbols, no name in both"

# ---- THE ASM-TWIN GATE --------------------------------------------------------------------------
# WHICH SYMBOLS CAME FROM ASM, ASKED OF THE OBJECTS — because the way this substitution fails is
# SILENT. Drop one of $ASM_SEAM_DEFINES and that seam's `ZY_*(fn)` resolves to the C again: the twins still
# assemble, still link, still export their names, and the game still computes exactly the right
# pixels — three times slower, with nothing but the frame rate to say so. Nothing else in this build
# or in `make test` would notice, because the C is not wrong; it is only slow.
#
# So the gate asks THREE things of the objects, over the twins ../include/ DECLARES (the headers are
# the source of truth for which cores have twins; a `.S` that defines a name no header declares is
# not part of the seam and is not counted):
#   * every declared twin is DEFINED by an asm object — a twin declared but never written, or a `.S`
#     left out of $ASM_CORES, names itself here rather than at the link;
#   * every declared twin is REFERENCED by a core object — which catches the whole seam collapsing,
#     since an unreferenced twin means every call site bound to the C;
#   * NO core object references the C CORE a twin replaces — which is the half the first two miss.
#     A twin with two call sites (`scroll_emit_tile_column` has one in frame.c and one in init.c)
#     stays "referenced" when only ONE of them loses its ZY_SCROLL() wrapper, so the second check
#     passes while the prefill silently runs the 4.5x C. This one cannot: an unwrapped call site is
#     exactly an UNDEFINED reference to the bare name. `src/scroll.c` names all of them too — in its
#     own jump table and `g_` glue — but it DEFINES them, so they are not undefined in its object
#     and it does not trip this. That is the point: the C's own file may call the C.
#
# THE HEADERS ARE GLOBBED, NOT NAMED. This gate was written for the scroll wave and a `scroll_`
# prefix would have gone on passing, quietly, over a sprite wave's twins in sprite.h — a coverage
# hole in the one check whose whole job is to notice a silent one. The `(` is what keeps prose out:
# a declaration is a name followed by an open paren, and no comment writes one.
#
# `nm -u` lists an object's undefined symbols, i.e. exactly what it calls out to.
# COMMENT LINES ARE DROPPED FIRST, and the older comment above ("no comment writes one") is why this
# is here: it was true until a comment cited a prototype. `include/asm_twin.h`'s usage example does
# exactly that, and before this filter `my_core_asm` was scraped as a declared twin and the gate
# demanded a `.S` define it (measured). A declaration in these headers never opens with `*` or `/`.
# `-h` IS LOAD-BEARING: given several files, grep prefixes every line with `filename:`, and the
# `^ZY_TWIN_VERIFICATION_ONLY` anchor below then matches nothing at all — the whole category goes
# quietly empty and every marked twin is demanded as shipped (measured).
strip_comments() { grep -vhE '^[[:space:]]*(\*|/)' "$@"; }
declared_twins() {
  strip_comments "$REC"/include/*.h | grep -ohE '\b[a-z0-9_]+_asm\(' | tr -d '(' | sort -u
}
undefined_in() { m68k-elf-nm -u $1 | awk 'NF == 2 {print $2}' | sort -u; }

# A TWIN THAT IS VERIFIED BUT DELIBERATELY NOT SHIPPED, declared as such in the header with
# `ZY_TWIN_VERIFICATION_ONLY` (include/frame.h defines the marker and says why the category exists).
# Wave D's three frame twins are the case: transcribed, differentially verified against the C over
# every staged world, and measured at +13 cycles a frame — so the game runs the C and the twins stay
# as the measurement. The marker sits on the SAME LINE as the name, which is what lets one grep pair
# them; a multi-line prototype puts the marker and the name on its first line for that reason.
# NO MATCHES IS A LEGAL ANSWER — the `|| true` is on the GREP and it is load-bearing. This script
# runs under `set -euo pipefail`, so a grep that finds nothing exits 1, the pipeline inherits it and
# the assignment below aborts the build with no message at all. MEASURED: removing the last marker
# from the headers killed `build.sh` silently at the gate's first line, which is the worst possible
# behaviour for the one check whose entire purpose is to be loud.
# THE MARKER MUST OPEN THE LINE, and both halves of this are measured rather than assumed.
# `^ZY_TWIN_VERIFICATION_ONLY[[:space:]]` excludes the `#define` itself and any PROSE that cites the
# macro — build.sh's older scraper leans on "no comment writes a `(`", and that stops being true the
# moment a comment quotes a prototype (measured: a comment naming the macro and `draw_char_asm(`
# was scraped as a twin). And `[^(]*` after the marker takes the FIRST `_asm(` on the line rather
# than the last: with a greedy `.*`, `ZY_TWIN_VERIFICATION_ONLY void a_asm(int); void b_asm(int);`
# returned `b_asm` — classing the marked twin as shipped and the unmarked one as verification-only,
# an exact inversion (measured on a synthetic header).
verification_only_twins() {
  { strip_comments "$REC"/include/*.h \
    | grep -ohE '^ZY_TWIN_VERIFICATION_ONLY[[:space:]].*[a-z0-9_]+_asm\(' || true; } \
    | sed -E 's/^ZY_TWIN_VERIFICATION_ONLY[^(]*[^a-z0-9_]([a-z0-9_]+_asm)\(.*/\1/' | sort -u
}

echo ">> asm-twin gate (the call sites must reach the twins, not the C)"
TWINS=$(declared_twins)
TWIN_COUNT=$(echo "$TWINS" | grep -c . || true)
[ "$TWIN_COUNT" -gt 0 ] || {
  echo "ERROR: no *_asm twin is declared in $REC/include/*.h, so this gate would pass over any"
  echo "       build at all. Its scrape has stopped matching the headers."
  exit 1; }
VERIFY_ONLY=$(verification_only_twins)
VERIFY_ONLY_COUNT=$(echo "$VERIFY_ONLY" | grep -c . || true)
# NO SEPARATE "the marker names something that is not a twin" ARM, because it cannot fire: both
# scrapers read the same `_asm(` pattern out of the same headers, so a marked name is a declared one
# by construction. A MISSPELT one is caught by MISSING below instead - measured, by misspelling
# `frame_panel_scroll_and_ship_stage_asm` in the header and watching MISSING name it.
SHIPPED=$(comm -23 <(echo "$TWINS") <(echo "$VERIFY_ONLY" | grep . || true))
ASM_DEFINED=$(defined_globals "$ASM_OBJECTS")
CORE_WANTED=$(undefined_in "$CORE_OBJECTS")
# BOTH categories must be DEFINED by an asm object: a verification-only twin that stopped assembling
# is not a decision, it is a twin that vanished.
MISSING=$(comm -23 <(echo "$TWINS") <(echo "$ASM_DEFINED"))
[ -z "$MISSING" ] || {
  echo "ERROR: ../include/*.h declares these twins but no .S in $REC/src/asm defines them:"
  echo "$MISSING" | sed 's/^/         /'
  exit 1; }
UNCALLED=$(comm -23 <(echo "$SHIPPED") <(echo "$CORE_WANTED"))
[ -z "$UNCALLED" ] || {
  echo "ERROR: these twins are assembled and linked but NOTHING CALLS THEM, so the C cores are what"
  echo "       this build runs — the game would be correct and several times too slow. Either their"
  echo "       subsystem's seam define is MISSING from ASM_SEAM_DEFINES (which holds"
  echo "       '$ASM_SEAM_DEFINES'), or a seam wrapper was lost"
  echo "       from a call site in $REC/src:"
  echo "$UNCALLED" | sed 's/^/         /'
  exit 1; }
# ...and the INVERSE arm, which is what makes "verification only" a gate rather than a comment: a
# twin declared not-shipped must NOT be referenced by any core object. A seam wrapper left on one of
# their call sites would otherwise ship a twin the header says is not shipped - the same silent
# substitution this gate exists for, in the other direction.
SHIPPED_BY_MISTAKE=$(comm -12 <(echo "$VERIFY_ONLY" | grep . || true) <(echo "$CORE_WANTED"))
[ -z "$SHIPPED_BY_MISTAKE" ] || {
  echo "ERROR: these twins are declared ZY_TWIN_VERIFICATION_ONLY, but a core object CALLS them -"
  echo "       so this build ships a twin ../include/frame.h says it does not. Either drop the seam"
  echo "       wrapper from the call site in $REC/src, or drop the marker and mean it:"
  echo "$SHIPPED_BY_MISTAKE" | sed 's/^/         /'
  exit 1; }
# ...and the per-CALL-SITE half: a bare core name UNDEFINED in a core object is an unwrapped call.
# Over the SHIPPED twins only - a verification-only twin's C core is exactly what should be called.
TWIN_CORES=$(echo "$SHIPPED" | sed 's/_asm$//' | sort -u)
UNWRAPPED=$(comm -12 <(echo "$TWIN_CORES") <(echo "$CORE_WANTED"))
[ -z "$UNWRAPPED" ] || {
  echo "ERROR: a core object calls out to these C cores by name, but they have twins — so a call"
  echo "       site lost its ZY_SCROLL() / ZY_SPRITE() / ZY_TEXT() / ZY_FRAME() wrapper and runs the"
  echo "       slow C while"
  echo "       the rest of the seam looks intact. Grep $REC/src for the name below and wrap it in the"
  echo "       macro its subsystem header declares. NOTE the one shape this arm CANNOT see: a call"
  echo "       from inside the file that DEFINES the core (src/text.c's draw_text_record reaching"
  echo "       draw_char) is not an undefined reference, so it never lands here:"
  echo "$UNWRAPPED" | sed 's/^/         /'
  exit 1; }
# WHAT ACTUALLY GOES ON THE LINK LINE. A verification-only twin is assembled (the gate above asks
# its object for the symbol) but must not be LINKED: nothing calls it, there is no --gc-sections on
# this build, and three of them are ~4.4 KB of dead code in a .PRG that ships on a floppy. An object
# is dropped when every twin it defines is verification-only; one holding a shipped twin as well
# stays, whole.
ASM_LINK_OBJECTS=""
for object in $ASM_OBJECTS; do
  defines_shipped=$(comm -12 <(defined_globals "$object") <(echo "$SHIPPED"))
  defines_verify=$(comm -12 <(defined_globals "$object") <(echo "$VERIFY_ONLY" | grep . || true))
  # A .S MAY NOT MIX THE TWO CATEGORIES, and refusing it is what makes include/frame.h's "never
  # linked into the game" TRUE rather than merely true today. Were mixing allowed, the object would
  # have to be kept for its shipped twin and the verification-only one would ride into the .PRG as
  # dead code — silently, with the header still promising the opposite and no "not linked" line to
  # contradict it. The fix is to split the file, which costs nothing: a `.S` is a file of twins.
  if [ -n "$defines_verify" ] && [ -n "$defines_shipped" ]; then
    echo "ERROR: $(basename $object) defines BOTH a shipped and a verification-only twin, so this"
    echo "       build cannot honour either promise — keeping it links dead code into the .PRG,"
    echo "       dropping it removes a twin the game calls. Split the .S:"
    echo "         shipped:            $(echo $defines_shipped)"
    echo "         verification-only:  $(echo $defines_verify)"
    exit 1; fi
  if [ -n "$defines_verify" ]; then
    echo "   not linked (verification-only): $(basename $object)"
  else
    ASM_LINK_OBJECTS="$ASM_LINK_OBJECTS $object"
  fi
done

SHIPPED_COUNT=$(echo "$SHIPPED" | grep -c . || true)
LINKED_COUNT=$(echo $ASM_LINK_OBJECTS | wc -w | tr -d ' ')
echo "   $SHIPPED_COUNT twins from $LINKED_COUNT linked asm objects, all called, no C core called"
[ "$VERIFY_ONLY_COUNT" -eq 0 ] || \
  echo "   ...and $VERIFY_ONLY_COUNT verification-only from $(($(echo $ASM_CORES | wc -w) - LINKED_COUNT)) unlinked object(s): $(echo $VERIFY_ONLY)"

# --no-warn-rwx-segments: tos.ld deliberately puts text, data and bss in ONE loadable image, because
# that is what a GEMDOS .PRG is — the loader has no notion of segment permissions and neither does a
# 68000 without an MMU. The warning is about ELF hygiene on a hosted target and says nothing here;
# silenced rather than tolerated so that a build's output stays worth reading.
echo ">> link"
$CC $CFLAGS -T "$HERE/tos.ld" -Wl,--emit-relocs -Wl,--no-warn-rwx-segments \
    $SHIM_OBJECTS $CORE_OBJECTS $ASM_LINK_OBJECTS -lgcc -o "$BUILD/zynaps.elf"

# _start must sit at the very first byte of text (GEMDOS enters there).
ENTRY=$(m68k-elf-nm "$BUILD/zynaps.elf" | awk '$3=="_start"{print $1}')
[ "$ENTRY" = "00000000" ] || { echo "ERROR: _start not at 0 (got $ENTRY)"; exit 1; }

# ---- what the COMPILER produced, asked of the object it produced it in --------------------------

# THE PALETTE LOOP'S ADDRESSING MODE, and it is this workspace's most expensive on-target defect.
# GCC folded a sibling project's `for (i = 0; i < 16; i++) pen[i] = table[i]` into one instruction —
# `move.w (%a0)+,(%a0,%d0.l)` — and on the 68000 a MOVE's DESTINATION effective address is computed
# AFTER the source operand's postincrement, so every pen landed one register high and the sixteenth
# write hit $ff8260, the RESOLUTION register. TOS 1.04 died on the spot. Nothing in the diff was
# wrong and the C was not wrong either (docs/on-target-execution.md class 6).
#
# THE ARGUMENT USED TO BE ABOUT ONE FILE AND IS NOW ONLY ABOUT THIS SCAN. While the doors were
# out-of-line functions in zynaps_backend.c, every hardware address was computed as a value and
# handed to a call, so the shape could not be emitted by construction and the scan confirmed a
# property the code already had. The doors are `static inline` now: the store is emitted INSIDE
# core loops — including `../src/video.c`'s palette upload, which `-funroll-loops` turns into eight
# absolute stores into the colour block — so the blast radius is every core loop that stores a
# hardware address, and this scan is the only thing between it and a hung TOS. Measured on today's
# binary: zero candidate lines, and the unrolled upload's last store begins at $ff825c, four bytes
# clear of the $ff8260 resolution register. What is forbidden is one instruction using the SAME
# address register in a postincrement source and an indexed destination; it is the SHAPE that is
# suspect, not the target.
# ORDER MATTERS AND THE SCAN HAS TO KNOW IT. What is fatal is a postincrement SOURCE with an indexed
# DESTINATION on the same register; the mirror image — `move.l (%a0,%a1.l),(%a0)+` — is ordinary, and
# GCC emits it here. So the pattern spans the comma rather than looking for the two halves anywhere
# in the line. Both operand spellings binutils can print are covered — `(%a0)+,(%a0,` and the older
# `%a0@+,%a0@(` — because which one appears is a property of the disassembler's mode and not of the
# program, and a scan that knew only one would pass vacuously on a toolchain that used the other.
# The offsets are counted off the two spellings themselves, which is why they differ:
#   %a0@+,%a0@(      the register names start 1 and 7 characters into the match
#   (%a0)+,(%a0,     ...and 2 and 9 characters into it
EA_SCAN='
  { register = "";
    if (match($0, /%a[0-7]@\+,%a[0-7]@\(/)) {
      register = substr($0, RSTART + 1, 2);
      if (register != substr($0, RSTART + 7, 2)) register = "";
    } else if (match($0, /\(%a[0-7]\)\+,\(%a[0-7],/)) {
      register = substr($0, RSTART + 2, 2);
      if (register != substr($0, RSTART + 9, 2)) register = "";
    }
    if (register != "") print;
  }'
echo ">> codegen scan: the postincrement-source / indexed-destination shape"

# ...AND THE SCAN PROVES IT CAN FAIL, on every run. A pattern that quietly stopped matching would be
# indistinguishable from a clean binary — which is exactly how the sibling project's half-blind exit
# detector survived a year. Two synthetic lines, one per spelling, must both be named.
EA_CONTROL_LINES=2
EA_CONTROL=$(printf '%s\n%s\n' 'movew %a0@+,%a0@(0,%d0:l)' 'move.w (%a3)+,(%a3,%d1.l)' \
             | awk "$EA_SCAN" | wc -l | tr -d ' ')
[ "$EA_CONTROL" = "$EA_CONTROL_LINES" ] || {
  echo "ERROR: the EA scan named $EA_CONTROL of $EA_CONTROL_LINES known-bad lines — it has rotted,"
  echo "       and a clean report from it would mean nothing."; exit 1; }

# ONE disassembly, read by both scans below and left on disk: it is the first thing anyone wants
# after a red, and disassembling the shim plus every core twice is the slowest step in this script
# after the compile itself.
DISASSEMBLY="$BUILD/zynaps.dis"
m68k-elf-objdump -d "$BUILD/zynaps.elf" > "$DISASSEMBLY"
SHIFT_EA=$(awk "$EA_SCAN" "$DISASSEMBLY" || true)
[ -z "$SHIFT_EA" ] || {
  echo "ERROR: the 68000 EA-ordering shape is in the binary — a store through the same register it"
  echo "       postincrements. See docs/on-target-execution.md class 6."
  echo "$SHIFT_EA"; exit 1; }

# THE IKBD SPIN MUST HAVE NO CAP, asked of the code that was actually generated.
#
# ../src/input.c's `ikbd_send_cmd` carries a give-up arm, `IKBD_TX_POLL_MAX`, inside
# `#ifndef OS_NO_REFUSAL_TALLY` — it exists so that an OFF-TARGET case cannot spin for ever on a
# byte the harness forgot to seed. On the machine the 6850 really does empty, the original has no
# cap (`btst #1,$fffc00 / beq.s self / move.b d0,$fffc02 / rts`), and a build that shipped one would
# silently drop a command byte instead of waiting the extra microsecond. -DOS_NO_REFUSAL_TALLY is
# what removes it; this is the check that it did, because a `-D` that stopped reaching the cores
# would look like nothing at all.
#
# THE METRIC IS CONDITIONAL BRANCHES, AND IT IS PROVED AGAINST A REAL CAPPED BUILD. The uncapped
# routine is the original's four instructions and has exactly ONE conditional branch, the poll's own
# `beq` back to itself; the arm adds a second, whatever shape GCC gives it. An earlier draft of this
# scan counted COMPARISONS instead and was vacuous — measured: with the cap present GCC reverses the
# loop onto a countdown and emits `subq`/`bne` with no `cmp` or `tst` at all, so both builds scored
# zero and the gate could not fail. So the control is not a synthetic line here: it is ../src/input.c
# compiled a second time with the macro UNDEFINED, and the scan must score it HIGHER.
IKBD_UNCAPPED_BRANCHES=1
# THE METRIC IS NO LONGER SPECIFIC TO THE CAP, and a reader of its red needs to know that. Since the
# doors became `static inline`, this routine contains an inlined `hw_read8` and `hw_write8` — whose
# video-base test and four-way tally chain are five more conditional branches that happen to FOLD,
# because the ACIA's address is a compile-time constant at both call sites. Measured today: still
# exactly 1. So anything that makes that address non-constant (routing it through a variable, an
# -fno-inline experiment, a GCC that declines to inline there) reds this scan with a message about
# IKBD_TX_POLL_MAX, which would then be the wrong diagnosis. It fails safe and it fails vague;
# atari/README.md's unpinned list carries that rather than this comment absorbing it.
# Cut the routine at the next SYMBOL, not at the first `rts`: if GCC ever tail-called `hw_write8`
# out of it — plausible, the store is the last thing it does — there would be no `rts`, and the awk
# would run to the end of a 41 KB disassembly and count every branch in the program.
IKBD_BODY_SCAN='
  $0 ~ /<ikbd_send_cmd>:/ { inside = 1; next }
  inside && /^[0-9a-f]+ </ { exit }
  inside { print }'
# `bra`/`bsr`/`bset`/`btst`/`bclr`/`bchg` are deliberately absent: what the arm adds is a CONDITIONAL
# branch. Both suffix spellings binutils can print are covered (`bnes` and `bne.s`), for the EA
# scan's reason — which one appears is a property of the disassembler, not of the program.
IKBD_BRANCHES='\<(bcc|bcs|beq|bge|bgt|bhi|ble|bls|blt|bmi|bne|bpl|bvc|bvs)([sbwl]|\.[sbwl])?\>'
count_ikbd_branches() { awk "$IKBD_BODY_SCAN" "$1" | grep -cE "$IKBD_BRANCHES" || true; }

echo ">> the IKBD transmitter spin is uncapped"
# The control FIRST, so a scan that scores everything zero is caught before it reports on the build.
$CC $CFLAGS -UOS_NO_REFUSAL_TALLY -c "$REC/src/input.c" -o "$OBJ/input_capped.o" 2>/dev/null
m68k-elf-objdump -d "$OBJ/input_capped.o" > "$OBJ/input_capped.dis"
IKBD_CONTROL=$(count_ikbd_branches "$OBJ/input_capped.dis")
[ "$IKBD_CONTROL" -gt "$IKBD_UNCAPPED_BRANCHES" ] || {
  echo "ERROR: ../src/input.c compiled WITH the cap scores $IKBD_CONTROL conditional branch(es),"
  echo "       which is not more than the $IKBD_UNCAPPED_BRANCHES an uncapped build scores — this"
  echo "       scan cannot tell the two apart, and a clean report from it would mean nothing."
  exit 1; }
IKBD_SHIPPED=$(count_ikbd_branches "$DISASSEMBLY")
[ "$IKBD_SHIPPED" = "$IKBD_UNCAPPED_BRANCHES" ] || {
  echo "ERROR: the linked ikbd_send_cmd has $IKBD_SHIPPED conditional branch(es), not the"
  echo "       $IKBD_UNCAPPED_BRANCHES of the original's spin (the capped control has"
  echo "       $IKBD_CONTROL). Either the IKBD_TX_POLL_MAX give-up arm survived into the target"
  echo "       build — a slow transmitter would then lose the command byte — or the core moved."
  awk "$IKBD_BODY_SCAN" "$DISASSEMBLY"; exit 1; }
echo "   $IKBD_SHIPPED conditional branch, against the capped control's $IKBD_CONTROL"

# ---- THE SHADOW MUST DEFINE EXACTLY THE DOORS THE KIT DECLARES ---------------------------------
#
# `shim_include/hw.h` and `psg.h` SHADOW the kit's headers rather than extending them: they cannot
# `#include_next` the originals, because C forbids a `static inline` definition of a name already
# declared `extern`. So on target the kit's declarations are never in the same translation unit as
# the definitions, and the only thing tying the two halves together is prose quoted into a comment.
#
# THAT MATTERS BECAUSE THE KIT IS SHARED. Four projects compile against `tools/recreate_kit`, and a
# door added, renamed or removed there for one of them — an `hw_or8` for a new read-modify-write,
# say — would leave this build compiling happily against a stale shadow while `make test`, which
# sees the kit's own header, is the only side that notices. The two builds would stop being the
# same program in the one way the "cores are compiled unchanged" census below cannot see, because
# that census reads INCLUDES and MACRO NAMES rather than the doors themselves.
#
# So the sets are compared. The kit DECLARES `<type> hw_name(...);` at the top level; the shadow
# DEFINES `static inline <type> hw_name(...)`. The `g_hw_*` and `g_psg_*` accessors are excluded by
# the pattern itself — they are the off-target harness's ledger readers, and a target build has no
# ledger for them to read.
echo ">> the shim's shadows define exactly the doors the kit declares"
kit_doors() { grep -hoE '^[a-z0-9_]+ +(hw|psg)_[a-z0-9_]+ *\(' "$@" | grep -oE '(hw|psg)_[a-z0-9_]+'; }
shadow_doors() { grep -hoE '^static inline [a-z0-9_]+ +(hw|psg)_[a-z0-9_]+ *\(' "$@" \
                 | grep -oE '(hw|psg)_[a-z0-9_]+'; }

# ...AND THE COMPARISON PROVES IT CAN FAIL, on every run and in BOTH directions — `comm` over two
# empty lists is silent, and two extractors that both stopped matching would be too.
DOOR_CONTROL=$(comm -3 <(printf 'hw_and8\nhw_write8\n') <(printf 'hw_write8\nhw_or8\n') \
               | tr -d '\t ' | tr '\n' ' ')
[ "$DOOR_CONTROL" = "hw_and8 hw_or8 " ] || {
  echo "ERROR: the door-set comparison named '$DOOR_CONTROL' on a known one-each-way difference,"
  echo "       not 'hw_and8 hw_or8 ' — it has rotted, and a clean report would mean nothing."
  exit 1; }

KIT_DOORS=$(kit_doors "$KIT/include/hw.h" "$KIT/include/psg.h" | sort -u)
SHADOW_DOORS=$(shadow_doors "$HERE/shim_include/hw.h" "$HERE/shim_include/psg.h" | sort -u)
[ -n "$KIT_DOORS" ] && [ -n "$SHADOW_DOORS" ] || {
  echo "ERROR: the door extractors found $(echo "$KIT_DOORS" | grep -c .) kit and"
  echo "       $(echo "$SHADOW_DOORS" | grep -c .) shadow declarations — one is EMPTY, so the"
  echo "       comparison below would be silent whatever the headers hold."
  exit 1; }
# `psg_port_read` is DELIBERATELY not shadowed: no core in this reconstruction reads the chip back,
# and leaving it undeclared means one that acquired a read fails to compile here rather than reading
# a real YM2149 with no surface to hold what came back. It is the one name allowed to differ.
UNSHADOWED_BY_DESIGN=psg_port_read
DOOR_DIFF=$(comm -3 <(echo "$KIT_DOORS") <(echo "$SHADOW_DOORS") | tr -d '\t' \
            | grep -vxF "$UNSHADOWED_BY_DESIGN" || true)
[ -z "$DOOR_DIFF" ] || {
  echo "ERROR: the kit's doors and the shim's shadows of them have diverged. A name the kit"
  echo "       declares and the shadow does not define is a door this build silently does not"
  echo "       have; one the shadow defines and the kit does not declare is a door the cores"
  echo "       cannot call. Either way the .PRG and \`make test\` stop being the same program:"
  echo "$DOOR_DIFF" | sed 's/^/         /'
  exit 1; }
echo "   $(echo "$SHADOW_DOORS" | grep -c .) doors shadowed, $UNSHADOWED_BY_DESIGN left out by design"

# THE CORES MAY ONLY READ A HARDWARE ADDRESS THE KIT MODELS, and this is the read half of the os_*
# census below. `hw_read8` used to be defined nowhere in this build, so a core that acquired a
# hardware read failed to LINK; shim_include/hw.h defines it now — for `ikbd_send_cmd`'s ACIA poll
# and for zynaps_main.c's MFP read-back at the hand-back — and
# that link error is gone. Off target the kit REFUSES an address outside its seeded set and the
# harness throws the case away — but a core reading, say, $ff8260 through a bare literal is green
# there (the refusal tally is compiled out by -DOS_NO_REFUSAL_TALLY) and reads the real chip here.
# So every argument must be one of os.h's OS_HW_* names, which is what makes the address DECLARED.
echo ">> the cores read only hardware the kit models"
HW_READS=$(grep -rhoE '\bhw_read[0-9]+ *\( *[A-Za-z_0-9]+' "$REC/src" "$REC/include" \
           | sed 's/.*( *//' | sort -u || true)
UNDECLARED=$(echo "$HW_READS" | grep -v '^OS_HW_' || true)
[ -z "$UNDECLARED" ] || {
  echo "ERROR: a core reads a hardware address the kit's seeded READ model does not name:"
  echo "$UNDECLARED" | sed 's/^/         /'
  echo "       Off target that is a refusal; here it reads the real chip with no surface at all."
  exit 1; }
echo "   $(echo "$HW_READS" | grep -c . || true) hw_read site(s), all naming an OS_HW_* address"

# ---- THE DOORS' COUNTERS MUST STAY ONE INSTRUCTION EACH ----------------------------------------
#
# zynaps_main.c's boot critical-section note states the assumption every exact-count assertion in
# smoke.py rests on: the counters are read on the main line and bumped inside interrupts, and that
# is safe ONLY while each `zy_*++` compiles to a single read-modify-write instruction — `addq.l
# #1,<abs>`, which the 68000 cannot interrupt. Split into `move.l <abs>,%dN / addq.l / move.l %dN,
# <abs>` it is three, an interrupt landing between the load and the store loses an increment, and
# `hw_writes` comes back short on a different frame each run.
#
# UNTIL THE DOORS WERE INLINED THAT WAS A ONE-OFF HUMAN READ OF ONE OBJECT. The seven `zy_*++` lived
# in zynaps_backend.c and one `objdump` covered them all. They are emitted at every inlined call
# site now — across ../src/video.c, irq.c, init.c, input.c, frame.c and sound.c — and
# `-funroll-loops` multiplies the video.c ones eightfold, in a routine entered twice a vertical
# blank. So the read became a scan.
#
# WHAT IS FORBIDDEN IS THE STORE-BACK, not the load: `g_record[REC_HW_WRITES] = zy_hw_writes` is a
# legitimate `move.l <counter>,%dN` and there are several. A split increment is separable from it by
# its final half — a `move` whose DESTINATION is a counter — and nothing in this program writes one
# any other way (they are only ever incremented). One instruction, or this is red.
COUNTERS='zy_hw_writes|zy_shifter_mode_writes|zy_palette_long_writes|zy_acia_bytes_sent'
COUNTERS="$COUNTERS|zy_rmw_stores|zy_psg_writes|zy_psg_refused"
COUNTER_STORE_SCAN="\bmove[bwl]?[[:space:]].*,[0-9a-f]+ <($COUNTERS)>"
echo ">> the doors' counters are single read-modify-write instructions"

# ...AND THE SCAN PROVES IT CAN FAIL, on every run, for the EA scan's reason: a pattern that
# quietly stopped matching is indistinguishable from a clean binary. The control is the middle and
# last lines of a split increment; the first (a load) must NOT match, or the scan would red on the
# record dump.
COUNTER_CONTROL_HITS=1
COUNTER_CONTROL=$(printf '%s\n%s\n' \
  'movel 10eea4 <zy_hw_writes>,%d1' \
  'movel %d1,10eea4 <zy_hw_writes>' | grep -cE "$COUNTER_STORE_SCAN" || true)
[ "$COUNTER_CONTROL" = "$COUNTER_CONTROL_HITS" ] || {
  echo "ERROR: the counter scan named $COUNTER_CONTROL of a split increment's two halves, not"
  echo "       $COUNTER_CONTROL_HITS — it matches the load as well as the store-back, or neither,"
  echo "       and a clean report from it would mean nothing."; exit 1; }

COUNTER_STORES=$(grep -E "$COUNTER_STORE_SCAN" "$DISASSEMBLY" || true)
[ -z "$COUNTER_STORES" ] || {
  echo "ERROR: a hardware-door counter is written by a plain MOVE, so its increment is no longer"
  echo "       one instruction. An interrupt landing inside the read-modify-write loses the count,"
  echo "       and smoke.py's exact totals go red on a different frame every run. See"
  echo "       shim_include/hw.h and zynaps_main.c's note on the boot's one critical section."
  echo "$COUNTER_STORES"; exit 1; }
COUNTER_INCREMENTS=$(grep -cE "\baddq[bwl]?[[:space:]].*,[0-9a-f]+ <($COUNTERS)>" "$DISASSEMBLY" || true)
echo "   $COUNTER_INCREMENTS increments, none split"

# THE BIG-ENDIAN ACCESSORS MUST BE PLAIN LOADS. machine.h picks a native `*(uint32_t *)` on a
# big-endian target and byte assembly on the little-endian host; if the guard ever failed to fire,
# every field access in every core would compile to an `lsl #8` shuffle chain — a uniform ~4x
# slowdown and a 40% larger .PRG (class 1). The count is not zero, because a real shift-by-8 is an
# ordinary instruction; what would be diagnostic is HUNDREDS. Reported rather than gated, because
# the threshold is a guess and a guessed gate is worse than a printed number.
SHUFFLES=$(grep -c 'lsl.*#8' "$DISASSEMBLY" || true)
echo "   lsl #8 instructions: $SHUFFLES (hundreds would mean machine.h's big-endian arm did not fire)"

# ...and the arm itself, asked of the source rather than of the disassembly, so the number above has
# something to be read against.
$CC $CFLAGS -E -dM -x c /dev/null | grep -q '__ORDER_BIG_ENDIAN__' || {
  echo "ERROR: the m68k compiler does not define __ORDER_BIG_ENDIAN__ — machine.h's guard cannot"
  echo "       have selected the native accessors."; exit 1; }

# ---- what the SOURCE says, asked of the source --------------------------------------------------

# THE CORES ARE COMPILED UNCHANGED, and this measures it in the two ways it could stop being true.
# If either did, the differential .so and this .PRG would stop being the same program and `make
# test`'s green would stop saying anything about what runs here. (Joust and Wonder Boy each carry a
# check of this shape, for the same reason.)
#
# Asked of the PREPROCESSED INCLUDE CLOSURE and of MACRO NAMES rather than of any identifier. Not of
# identifiers, because `../src`'s own comments discuss `hw_write8` and the target build at length —
# that is the seam being documented where it lives — so a grep for those would red on prose.
#
# AND NOT OF `#include` LINES ANY MORE, WHICH IS WHAT THIS CHECK USED TO READ. It grepped `../src`
# and `../include` for a DIRECT `#include "zynaps_target.h"` or `"tos.h"`. That was sound while the
# only shadow was `os.h`; once `hw.h` and `psg.h` became shadows too, a shim header could reach a
# core THROUGH one of them — a first draft of `shim_include/hw.h` included `zynaps_target.h` for
# `HW_BUS`, which put `zy_image_base`, `zynaps_main()` and every `zy_*` global into six verified
# translation units with this gate printing green, because no core contained the line it looked for.
# `gcc -MM` answers what the compiler actually opened, which is the question the gate was always
# asking.
#
# THE LIST IS WHAT THE CORES MAY REACH, not what they may not: a fifth shadow added to
# `shim_include/` reds here until someone says so out loud, which is the property the "and nothing
# else" wording never actually had. `tos.h` is on it because the `os.h` shadow needs the trap
# primitives; `string.h` because the cores need the three libc names m68k-elf does not ship.
echo ">> the cores take nothing from this directory"
CORE_MAY_REACH="hw.h os.h psg.h sched.h string.h tos.h"
shim_headers_reached() {
  for source in $CORES; do $CC $CFLAGS $DEF -MM "$source"; done \
    | tr ' ' '\n' | grep "shim_include/" | sed 's#.*shim_include/##' | sort -u | tr '\n' ' '
}
REACHED=$(shim_headers_reached)
[ -n "$REACHED" ] || {
  echo "ERROR: the cores reach NO header in shim_include/, which cannot be true — every one of them"
  echo "       includes os.h. \`gcc -MM\`'s output shape has moved under this gate and a clean"
  echo "       report from it would mean nothing."; exit 1; }
[ "$REACHED" = "$CORE_MAY_REACH " ] || {
  echo "ERROR: the cores' include closure reaches a different set of shim headers than the seam"
  echo "       declares. A header here that is not a shadow of a KIT header the cores already"
  echo "       include is the shim leaking into verified code — check what pulled it in, not just"
  echo "       what includes it directly."
  echo "         may reach: $CORE_MAY_REACH"
  echo "         reaches:   $REACHED"
  exit 1; }
echo "   $REACHED"

# ...and the build's own `-D` names, which exist nowhere but here. A core reading one would compile
# differently in the two builds while looking identical in both.
TARGET_MACROS='PROGRAM_BYTES|ZY_LOAD_BASE|ZY_FAULT_PEN|ZY_SMOKE_VBLS|ZY_PHASE|ZY_GAME_FRAMES'
# ZY_TARGET_IMAGE_BYTES is on the list even though shim_include/os.h — a header the cores DO
# reach — is where it lives. That is deliberate: the cores get its effect through os_in_image
# and must never spell it, because off target the name does not exist at all, so a core's
# `#ifdef ZY_TARGET_IMAGE_BYTES` arm would be live on the machine and silently false in the
# differential — the same defect the five macros above are listed for.
TARGET_MACROS="$TARGET_MACROS|ZY_TARGET_IMAGE_BYTES"
TARGET_MACROS="$TARGET_MACROS|ZY_FRAME_SAMPLES|ZY_GAME_FAULT"
TARGET_MACROS="$TARGET_MACROS|ZY_CHANCE_INDEX_REGISTER|ZY_GROUND_SPAWN_Y_REGISTER"
LEAKS=$(grep -rlE "\b($TARGET_MACROS)\b" "$REC/src" "$REC/include" || true)
[ -z "$LEAKS" ] || { echo "ERROR: a core reads a target-only macro:"; echo "$LEAKS"; exit 1; }

# THE os.h SHADOW'S CENTRAL CLAIM, MEASURED RATHER THAN ASSERTED IN PROSE. That file replaces FOUR
# kit helpers and pulls the rest in through `#include_next`, so every OTHER `os_*` — os_bconstat,
# os_bconin, os_giaccess, os_random, os_fwrite — is still the deterministic MODEL, compiled into the
# .PRG and answering out of an in-image register file. That is safe only while no core calls one,
# and the shadow's own header says so as a grep somebody ran once. This is that grep, every build.
#
# A core that reached os_bconin would LINK CLEANLY and read a real keypress out of a fabricated
# model, with -DOS_NO_REFUSAL_TALLY having compiled away the tally that would have counted it: no
# link error, no record field, no surface. README's own M2 plan ports the routines that would do it.
# `os_refused` is on this list for a different reason from the other four: it is not replaced by
# shim_include/os.h but by the KIT's own `-DOS_NO_REFUSAL_TALLY` arm, which compiles it to an inline
# identity (tools/recreate_kit/include/os.h). Its one core caller is `ikbd_send_cmd`'s give-up arm,
# which that same macro compiles away — see shim_include/tos.h on why the spin is unbounded here.
# `os_in_image` is on the list because the target's image is HALF the model's: shim_include/os.h
# shadows it to bound against ZY_TARGET_IMAGE_BYTES instead of OS_IMAGE_SIZE, which is what its own
# os_fread relies on to keep GEMDOS inside the .bss array. Its core callers are init.c's slice guards
# (the attract bar list, the section table), and README.md's "Memory" section argues why neither can
# produce an address in the half that went. `os_in_image_fixed` is deliberately NOT shadowed, and
# this list is why that is safe: no core calls it today, and one that started to would fail here.
REPLACED_OS_HELPERS='os_fopen|os_fread|os_fclose|os_super|os_refused|os_in_image'
OS_USED=$(grep -rhoE '\bos_[a-z_0-9]+' "$REC/src" "$REC/include" | sort -u || true)
OS_MODELLED=$(echo "$OS_USED" | grep -vE "^($REPLACED_OS_HELPERS)$" || true)
[ -z "$OS_MODELLED" ] || {
  echo "ERROR: a core calls a kit os_* helper this build does NOT replace, so it would run against"
  echo "       the deterministic model on real hardware. Replace it in shim_include/os.h, or say"
  echo "       why the model is right on target:"
  echo "$OS_MODELLED"; exit 1; }
echo "   the cores call $(echo "$OS_USED" | wc -l | tr -d ' ') os_* helper(s), all of them replaced"

# ...AND THE SHIM'S OWN C IS ON THE SAME HOOK, WHICH THE DIET IS WHAT MADE TRUE. The scan above
# covers the cores; the three files in THIS directory were left out because a modelled helper here
# was merely useless. It is worse than useless now: the model's fixed map puts its staged-file table
# at OS_FS_TABLE (0xbf000) and its staging area at OS_FS_STAGING (0xc0000), which were inside the
# 1 MiB array and are a quarter of a megabyte PAST the end of the 512 KiB one. So a shim helper that
# called os_fwrite would link cleanly, pass every scan above, and write over whatever `.bss` follows
# the image — the failure shim_include/os.h's own header describes as tearing down clean with every
# read-back green. `os_in_image_fixed` is on the list for the same reason: its bound is baked into a
# macro over OS_IMAGE_SIZE and cannot be shadowed, so it would answer yes for a quarter-megabyte of
# addresses this build does not own.
#
# THE SHADOW FILE ITSELF NAMES THE MODEL SPELLINGS, and must: `#define os_fopen os_model_fopen` is
# how it moves the kit's versions aside. Those five are what SHIM_OWN_OS_NAMES adds, and nothing
# else — a shim file that CALLED an `os_model_*` helper would still be caught, because the call
# would have to name one of the four the shadow does not define.
#
# COMMENTS ARE STRIPPED FIRST, and that is not tidiness — it is what makes this scan usable at all.
# These files argue at length about the helpers they do NOT call (`os_fs_copy_in_image` and
# `os_in_image_fixed` are both named in shim_include/os.h's own prose, explaining why neither is
# reached), so a raw grep reports the explanation as the defect and the only way to keep the gate
# green would be to delete the reasoning. `-fpreprocessed -dD -E` removes comments without expanding
# a macro or following an include, so what is scanned is the code and nothing else.
SHIM_OWN_OS_NAMES='os_model_fopen|os_model_fread|os_model_fclose|os_model_super|os_model_in_image'
# Its status is checked rather than discarded: with several inputs, a file the strip could not read
# would simply contribute no names while the others still did, and the scan would pass having seen
# less than it claims. It emits nothing on stderr today, so nothing is silenced either.
SHIM_STRIPPED=$(m68k-elf-gcc -fpreprocessed -dD -E "$HERE"/*.c "$HERE"/shim_include/*.h) || {
  echo "ERROR: the shim os_* scan could not strip comments from this directory, so it saw less"
  echo "       than it would report — fix the strip rather than skipping the scan"; exit 1; }
SHIM_OS_USED=$(echo "$SHIM_STRIPPED" | grep -ohE '\bos_[a-z_0-9]+' | sort -u || true)
[ -n "$SHIM_OS_USED" ] || {
  echo "ERROR: the shim os_* scan read no names at all — its comment strip or its grep is broken,"
  echo "       and a scan that matches nothing passes everything"; exit 1; }
SHIM_OS_MODELLED=$(echo "$SHIM_OS_USED" \
                   | grep -vE "^($REPLACED_OS_HELPERS|$SHIM_OWN_OS_NAMES)$" || true)
[ -z "$SHIM_OS_MODELLED" ] || {
  echo "ERROR: the shim itself names a kit os_* helper this build does NOT replace. On the model's"
  echo "       fixed map that would read or write a quarter of a megabyte past the end of the"
  echo "       target image, into .bss:"
  echo "$SHIM_OS_MODELLED"; exit 1; }
echo "   ...and the shim names $(echo "$SHIM_OS_USED" | wc -l | tr -d ' '), none of them modelled"

# ---- THE MEMORY CENSUS, RE-RUN EVERY BUILD -----------------------------------------------------
# The target image is HALF the differential's (shim_include/os.h's ZY_TARGET_IMAGE_BYTES), and the
# claim that pays for it is that no address the game names lands in the missing upper half. Every
# such address is an `A_<name>` — this project's spelling for a Ghidra address — so the census is a
# grep, and it runs here rather than sitting in README.md as a number somebody checked once: a new
# `A_*` above the image would otherwise compile, run against the `.bss` beyond the array, and be
# caught by nothing until the guard band or a crash.
#
# BOTH SPELLINGS, because there are two kinds of object in this .PRG. The cores say `#define A_x
# 0x…` in a header; the ASM TWINS in ../src/asm restate the same addresses as `.equ A_x, 0x…`, and
# those objects are linked (`build.sh` assembles them above). A census that read only the headers
# would miss a twin that named an address the C never does — which scroll_tile.S's own comment says
# is the normal case for an inline address in the original.
#
# AND IT FAILS CLOSED. A gate that greps a strict shape reports coverage of what it MATCHED, so a
# define written any other legal way (`(0x90000u)`, a decimal, a leading space) drops out of the set
# and the gate still prints "all below". So the strict matches are counted against a LOOSE count of
# every `A_*` declaration in either syntax, and a mismatch is a refusal — the same technique the
# trap-register scan's `--expect` uses, and for the same reason.
#
# WHAT IT DOES NOT COVER, said plainly: an address the code COMPUTES rather than names, and the
# EXTENT of a named one (this compares bases; only the two framebuffers have a compile-time extent
# check, in zynaps_main.c). Both are the watched bands' job — zynaps_main.c's IMAGE_WORLD_BYTES tail
# and IMAGE_GUARD_BYTES guard, checked by smoke.py — and README.md's "Memory" keeps them apart.
echo ">> memory census (every A_* the cores name is inside the target image)"
IMAGE_BYTES=$(sed -n 's/^#define ZY_TARGET_IMAGE_BYTES *\(0[xX][0-9a-fA-F]*\).*/\1/p' \
              "$HERE/shim_include/os.h")
[ -n "$IMAGE_BYTES" ] || {
  echo "ERROR: no ZY_TARGET_IMAGE_BYTES in $HERE/shim_include/os.h — the census has no bound"
  exit 1; }

# THE SOURCES AND ONLY THE SOURCES. `$HERE` is not passed whole: it holds `build/`, `disk/` and
# `out/`, and a grep that recursed into them would read a `.PRG`, a `.ST` or a memory dump — whose
# "Binary file … matches" line would land in the declaration count and turn the parse check below
# into a refusal whose message is about the wrong thing. Which build outputs happen to be on disk
# must not change what a gate concludes. Each path is quoted rather than word-split out of one
# string, so a path with a space or a glob character cannot silently select a different file set.
# `|| true` because this script is `set -euo pipefail` and grep exits 1 on no match — which would
# kill the build at the assignment, before the diagnostics below could say what was wrong.
CENSUS_DECL_RE='^[[:space:]]*(#define|\.equ)[[:space:]]+A_[A-Za-z0-9_]+'
CENSUS_DECLS=$(grep -rhE "$CENSUS_DECL_RE" \
               "$REC/include" "$REC/src" "$HERE"/*.c "$HERE/shim_include" || true)
# ONE NAME AND VALUE PER DECLARATION LINE, which is what makes the two counts comparable: `sed`'s
# `s///` substitutes once a line, where `grep -o` would emit a second match for a line that happens
# to mention another `A_name 0x…` in a trailing comment — and the shortfall below would then be
# NEGATIVE with an empty list under it. The `,?` is `.equ`'s separator; both spellings come out of
# here as `NAME VALUE`, so the loop that follows needs to know about only one shape.
CENSUS_ADDR_SED='s/^[[:space:]]*(#define|\.equ)[[:space:]]+(A_[A-Za-z0-9_]+),?[[:space:]]+'
CENSUS_ADDR_SED="$CENSUS_ADDR_SED"'(0[xX][0-9a-fA-F]+).*/\2 \3/p'
CENSUS_ADDRS=$(echo "$CENSUS_DECLS" | sed -nE "$CENSUS_ADDR_SED")
DECL_COUNT=$(echo "$CENSUS_DECLS" | grep -c . || true)
ADDR_COUNT=$(echo "$CENSUS_ADDRS" | grep -c . || true)
[ "$DECL_COUNT" -gt 0 ] || {
  echo "ERROR: the census found no A_* declarations at all — its grep is broken, and a census that"
  echo "       matches nothing passes everything"; exit 1; }
[ "$DECL_COUNT" = "$ADDR_COUNT" ] || {
  echo "ERROR: the census parsed $ADDR_COUNT addresses out of $DECL_COUNT A_* declarations, so"
  echo "       $((DECL_COUNT - ADDR_COUNT)) are UNCHECKED — and an address it cannot parse is"
  echo "       exactly the one that would be above the image. Give them a plain hex literal, or"
  echo "       teach this grep the shape they use:"
  echo "$CENSUS_DECLS" \
    | grep -vE 'A_[A-Za-z0-9_]+,?[[:space:]]+0[xX][0-9a-fA-F]+' | sed 's/^/     /'
  exit 1; }

OUTSIDE=""
while read -r NAME VALUE; do
  [ -n "$NAME" ] || continue
  # bash reads `0x…` natively, so there is no hand-rolled hex parser to get wrong.
  [ $((VALUE)) -lt $((IMAGE_BYTES)) ] || OUTSIDE="$OUTSIDE     $NAME = $VALUE"$'\n'
# A heredoc and not a pipe: a `while read` on the right of a pipe runs in a SUBSHELL, and $OUTSIDE
# would be discarded at the loop's end with every address reported clean.
done <<EOF
$CENSUS_ADDRS
EOF
[ -z "$OUTSIDE" ] || {
  echo "ERROR: an address a core names is at or above the target image's $IMAGE_BYTES:"
  printf '%s' "$OUTSIDE"
  echo "       Either the census in README.md is out of date, or this build cannot be shrunk"
  echo "       to $IMAGE_BYTES. Do not raise the bound without re-running the census."
  exit 1; }
echo "   $ADDR_COUNT A_* addresses (#define and .equ), all below $IMAGE_BYTES"

echo ">> objcopy -> flat binary"
m68k-elf-strip --strip-debug "$BUILD/zynaps.elf"
m68k-elf-objcopy -O binary "$BUILD/zynaps.elf" "$BUILD/zynaps.bin"

echo ">> wrap -> GEMDOS .PRG"
# Its own report line is kept, because the size gate below weighs the three numbers in it and a
# gate that printed different numbers from the wrapper would be two accounts of one file.
PRG_REPORT=$("$PY" "$HERE/mkprg.py" "$BUILD/zynaps.elf" "$BUILD/zynaps.bin" "$BUILD/$PRG")
echo "$PRG_REPORT"

# ---- THE 1 MB SIZE GATE ------------------------------------------------------------------------
# WHAT IS BEING WEIGHED: text + data + bss, which is exactly what GEMDOS carves out of the transient
# program area when it loads this .PRG. The stack is what is left above it, and `_start` takes no
# Mshrink, so a binary that eats the whole TPA does not fail to load — it loads, and then writes its
# own stack. That failure arrives in the middle of a boot with no message, which is why the refusal
# is here.
#
# THE BUDGET IS smoke.py's, SCRAPED. That file MEASURED the TPA a 1 MB TOS 1.04 machine leaves — it
# reads GEMDOS's own p_lowtpa/p_hitpa out of the record — and names the stack reserve; its "THE 1 MB
# BUDGET" block carries the arithmetic and the provenance. Scraped rather than respelt for the
# reason run.sh scrapes MEMSIZE_MB out of the same file: two numbers that must agree, one definition
# (CLAUDE.md §5).
#
# THE BUILD-TIME GATE IS THE COARSE ONE AND IT IS NOT THE ONLY ONE. It weighs the binary against a
# budget measured on ONE machine configuration; the RUN-TIME check is smoke.py's `check_the_memory`,
# which weighs the image against the p_hitpa the machine in front of it actually reported, plus the
# guard band above the image. This gate stops a too-big .PRG before anybody boots it; that one says
# the boot it did was inside its means.
scrape_int() {  # scrape_int <NAME> <file> -> the integer of `NAME = <digits>`
  sed -n "s/^$1 *= *\([0-9][0-9]*\).*/\1/p" "$2"
}
TPA_BYTES=$(scrape_int TPA_1MB_BYTES "$HERE/smoke.py")
RESERVE_BYTES=$(scrape_int STACK_RESERVE_BYTES "$HERE/smoke.py")
[ -n "$TPA_BYTES" ] && [ -n "$RESERVE_BYTES" ] || {
  echo "ERROR: no TPA_1MB_BYTES / STACK_RESERVE_BYTES in $HERE/smoke.py — the size gate has no"
  echo "       budget to weigh against, and a gate with no number passes everything"; exit 1; }
BUDGET_BYTES=$((TPA_BYTES - RESERVE_BYTES))

# The leading `[^a-z]` is what keeps `text=` from also matching inside a longer word, and the
# trailing `.*` is what lets the three fields share one line: mkprg.py prints them together with the
# .PRG's path in front, and that path is not this script's to control.
prg_field() {  # prg_field <name> -> mkprg.py's own count for it
  echo "$PRG_REPORT" | sed -n "s/.*[^a-z]$1=\([0-9][0-9]*\).*/\1/p"
}
TEXT_BYTES=$(prg_field text); DATA_BYTES=$(prg_field data); BSS_BYTES=$(prg_field bss)
[ -n "$TEXT_BYTES" ] && [ -n "$DATA_BYTES" ] && [ -n "$BSS_BYTES" ] || {
  echo "ERROR: mkprg.py's report line is not the text=/data=/bss= shape the size gate reads:"
  echo "       $PRG_REPORT"; exit 1; }
# THE BASEPAGE IS PART OF THE BILL. GEMDOS carves it out of the same TPA, immediately below the
# text, so a gate that weighed only text+data+bss would pass a binary that overruns by its length.
BASEPAGE_BYTES=256
LOAD_BYTES=$((BASEPAGE_BYTES + TEXT_BYTES + DATA_BYTES + BSS_BYTES))

echo ">> size gate (a 1 MB machine's TPA, measured)"
echo "   basepage=$BASEPAGE_BYTES text=$TEXT_BYTES data=$DATA_BYTES bss=$BSS_BYTES" \
     "-> $LOAD_BYTES B loaded"
echo "   budget $BUDGET_BYTES B = TPA $TPA_BYTES - stack reserve $RESERVE_BYTES"
echo "   $((BUDGET_BYTES - LOAD_BYTES)) B spare"
[ "$LOAD_BYTES" -le "$BUDGET_BYTES" ] || {
  echo "ERROR: $PRG needs $LOAD_BYTES B of TPA and a 1 MB machine has $BUDGET_BYTES B for it."
  echo "       Shrink ZY_TARGET_IMAGE_BYTES (shim_include/os.h) or the binary — do NOT raise the"
  echo "       budget, which is a measurement (smoke.py's 1 MB budget block) and not a policy."
  exit 1; }

cp "$BUILD/$PRG" "$DISK/$PRG"
cp "$BUILD/$PRG" "$BUILD/ZYNAPS-$MODE.PRG"
# The ELF beside it, because the floppy mode's ANCHOR needs a symbol address and a .PRG has no
# symbol table: `smoke.py` reads `zy_anchor`'s offset out of this and adds the load address it
# finds in RAM. Per mode for the .PRG's reason — an edit to this script must not leave a stripped
# binary being read against another build's symbols.
cp "$BUILD/zynaps.elf" "$BUILD/zynaps-$MODE.elf"
ls -l "$DISK/$PRG" "$DISK/ZYNAPS.IMG"

# ---- the bootable floppy ------------------------------------------------------------------------
# LAST, so the image is built out of a drive that is already complete: mkfloppy.py takes the staged
# root above (the 62 data files plus ZYNAPS.IMG) and puts THIS .PRG in AUTO\ under the original's
# own name. It verifies the finished volume with tools/st_extract.py's reader and refuses an image
# whose files do not match what went in, so a bad write is a red here and not a black screen later.
if [ "$MEDIUM" = "floppy" ]; then
  echo ">> bootable floppy"
  "$PY" "$HERE/mkfloppy.py" --prg "$BUILD/ZYNAPS-$MODE.PRG" --root "$DISK" \
        --out "$DISK/ZYNAPS.ST"
fi
