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
# C at the CALL SITE, through ../include/scroll.h's `ZY_SCROLL()`, which -DZY_ASM_SCROLL below
# switches over. The C stays compiled and stays the reference — ../test/test_scroll.py proves it
# equal to the original and ../test/test_asm_scroll.py proves each twin equal to it, byte for byte
# over the whole image, so this substitution changes the program's SPEED and nothing else.
# See ../src/asm/README.md for the recipe and for what to do when adding the next one.
# `2>/dev/null || true` is what makes the message below REACHABLE: this script runs under
# `set -euo pipefail`, so a bare `ls` over an empty or missing src/asm/ aborts the shell on the
# assignment itself and the reader gets ls' "No such file or directory" instead of the diagnosis.
# (The CORES= line above has the same shape; it predates the twins and is left as it is.)
ASM_CORES="$(ls "$REC"/src/asm/*.S 2>/dev/null || true)"
[ -n "$ASM_CORES" ] || { echo "ERROR: no asm twins found in $REC/src/asm"; exit 1; }
DEF="$DEF -DZY_ASM_SCROLL"

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
# SILENT. Drop `-DZY_ASM_SCROLL` and every `ZY_SCROLL(fn)` resolves to the C again: the twins still
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
declared_twins() { grep -ohE '\b[a-z0-9_]+_asm\(' "$REC"/include/*.h | tr -d '(' | sort -u; }
undefined_in() { m68k-elf-nm -u $1 | awk 'NF == 2 {print $2}' | sort -u; }

echo ">> asm-twin gate (the call sites must reach the twins, not the C)"
TWINS=$(declared_twins)
TWIN_COUNT=$(echo "$TWINS" | grep -c . || true)
[ "$TWIN_COUNT" -gt 0 ] || {
  echo "ERROR: no *_asm twin is declared in $REC/include/*.h, so this gate would pass over any"
  echo "       build at all. Its scrape has stopped matching the headers."
  exit 1; }
ASM_DEFINED=$(defined_globals "$ASM_OBJECTS")
CORE_WANTED=$(undefined_in "$CORE_OBJECTS")
MISSING=$(comm -23 <(echo "$TWINS") <(echo "$ASM_DEFINED"))
[ -z "$MISSING" ] || {
  echo "ERROR: ../include/*.h declares these twins but no .S in $REC/src/asm defines them:"
  echo "$MISSING" | sed 's/^/         /'
  exit 1; }
UNCALLED=$(comm -23 <(echo "$TWINS") <(echo "$CORE_WANTED"))
[ -z "$UNCALLED" ] || {
  echo "ERROR: these twins are assembled and linked but NOTHING CALLS THEM, so the C cores are what"
  echo "       this build runs — the game would be correct and three times too slow. Either"
  echo "       -DZY_ASM_SCROLL was dropped, or a ZY_SCROLL() wrapper was lost from a call site in"
  echo "       $REC/src (frame.c's dispatch table and init.c's prefill are the two):"
  echo "$UNCALLED" | sed 's/^/         /'
  exit 1; }
# ...and the per-CALL-SITE half: a bare core name UNDEFINED in a core object is an unwrapped call.
TWIN_CORES=$(echo "$TWINS" | sed 's/_asm$//' | sort -u)
UNWRAPPED=$(comm -12 <(echo "$TWIN_CORES") <(echo "$CORE_WANTED"))
[ -z "$UNWRAPPED" ] || {
  echo "ERROR: a core object calls out to these C cores by name, but they have twins — so a call"
  echo "       site lost its ZY_SCROLL() wrapper and runs the slow C while the rest of the seam"
  echo "       looks intact. Wrap it (frame.c's dispatch table and its three direct calls, and"
  echo "       init.c's prefill, are the call sites):"
  echo "$UNWRAPPED" | sed 's/^/         /'
  exit 1; }
echo "   $TWIN_COUNT twins from $(echo $ASM_CORES | wc -w | tr -d ' ') asm objects, all called, no C core called"

# --no-warn-rwx-segments: tos.ld deliberately puts text, data and bss in ONE loadable image, because
# that is what a GEMDOS .PRG is — the loader has no notion of segment permissions and neither does a
# 68000 without an MMU. The warning is about ELF hygiene on a hosted target and says nothing here;
# silenced rather than tolerated so that a build's output stays worth reading.
echo ">> link"
$CC $CFLAGS -T "$HERE/tos.ld" -Wl,--emit-relocs -Wl,--no-warn-rwx-segments \
    $SHIM_OBJECTS $CORE_OBJECTS $ASM_OBJECTS -lgcc -o "$BUILD/zynaps.elf"

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
# `os_in_image` is on the list because the MODEL IS RIGHT ON TARGET: it is arithmetic on OS_IMAGE_SIZE
# — `addr <= size && count <= size - addr` — and the target's image is that same 1 MiB array, so the
# bound a core checks off target is the bound it must check here (shim_include/os.h's own os_fread
# relies on it). Its core callers are init.c's slice guards (the attract bar list, the section table).
REPLACED_OS_HELPERS='os_fopen|os_fread|os_fclose|os_super|os_refused|os_in_image'
OS_USED=$(grep -rhoE '\bos_[a-z_0-9]+' "$REC/src" "$REC/include" | sort -u || true)
OS_MODELLED=$(echo "$OS_USED" | grep -vE "^($REPLACED_OS_HELPERS)$" || true)
[ -z "$OS_MODELLED" ] || {
  echo "ERROR: a core calls a kit os_* helper this build does NOT replace, so it would run against"
  echo "       the deterministic model on real hardware. Replace it in shim_include/os.h, or say"
  echo "       why the model is right on target:"
  echo "$OS_MODELLED"; exit 1; }
echo "   the cores call $(echo "$OS_USED" | wc -l | tr -d ' ') os_* helper(s), all of them replaced"

echo ">> objcopy -> flat binary"
m68k-elf-strip --strip-debug "$BUILD/zynaps.elf"
m68k-elf-objcopy -O binary "$BUILD/zynaps.elf" "$BUILD/zynaps.bin"

echo ">> wrap -> GEMDOS .PRG"
"$PY" "$HERE/mkprg.py" "$BUILD/zynaps.elf" "$BUILD/zynaps.bin" "$BUILD/$PRG"

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
