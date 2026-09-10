#!/bin/bash
# Build FLYSHARK.PRG from the verified reconstruction with the m68k-elf cross toolchain, stage a
# drive for Hatari, and write the bootable floppy.
#
#   build.sh                 -> the PLAYABLE build: no limit, no files written, real stick
#   build.sh smoke [frames]  -> the same program with a frame limit and a record (smoke.py's build)
#
# Each writes disk/FLYSHARK.PRG *and* keeps build/FLYSHARK-<mode>.PRG, so a check that needs both
# builds in sequence does not have to rebuild.
#
# Stages disk/{AUTO/FLYSHARK.PRG, FLYSHARK.IMG, A/*} and writes disk/FLYSHARK.ST. build/ and disk/
# are gitignored.
#
# THE CORES' SOURCE IS COMPILED UNCHANGED, and FOUR things differ from the differential .so — the
# first two are the seam, the last two are the performance campaign's (../STATUS.md, "On-target
# performance"), and every one of them is a build-level difference rather than a source one:
#   1. the INCLUDE PATH — shim_include/ shadows the kit's os.h, hw.h, psg.h and sched.h with the
#      real-TOS ones, and ../include/init.h with its two XBIOS answers (README.md's seam table);
#   2. the kit sources left out: src/hw.c, src/psg.c, src/sched.c and src/os_log.c, whose work the
#      shim does for real;
#   3. -DFS_ASM_SPRITE, which makes ../src/sprite.c's four seams CALL THE ASM TWINS instead of
#      their own C — the unclipped sprite blitters, the GATED ones, the five restore blitters and
#      the ring-seam copy. It is the one -D here that changes which code runs, and it is gated below
#      rather than trusted — a -D that changed a core's BEHAVIOUR would be a different thing
#      entirely and does not belong in this list;
#   4. HOT_CFLAGS, which recompiles ONE core at a higher optimisation level.
# Both 3 and 4 are pinned: 3 by ../test/test_asm_{sprite,restore,clipped}.py plus the three gates
# below, and both by smoke.py's framebuffer identity, which is what says a codegen change altered no
# pixel.
#
# $FS_DIAG_CFLAGS IS A FIFTH, AND IT IS DIAGNOSTIC ONLY. It is appended to CFLAGS for every core and
# for the link, and NOTHING in this repository sets it except `atari/profile.py --phases`, which
# turns GCC's inlining off so that `../src/sprite.c`'s static phase helpers keep their own symbols
# and the profiler can charge a phase instead of folding all of them into `render_frame`. A build
# made with it runs EXTRA CALL FRAMES and is therefore slower than the one that ships: it is a
# measuring instrument, not a game, and it must never be what a play build is made with.
set -euo pipefail

# The smoke build's default frame limit, which smoke.py's SMOKE_ATTRACT_FRAMES mirrors and asserts.
# 200 attract frames is past the prescroll, past two of the three text pages, and eighty frames past
# the LAST of the framebuffer differential's anchors (smoke.py's FRAME_ANCHORS: attract frames 50
# and 120, one per text page; `check_the_record` asserts this limit outlasts the later of them).
SMOKE_FRAMES_DEFAULT=200

MODE="${1:-play}"
case "$MODE" in
  play)  DEF="" ;;
  smoke) DEF="-DFS_SMOKE=1 -DFS_ATTRACT_FRAMES=${2:-$SMOKE_FRAMES_DEFAULT}" ;;
  *) echo "usage: build.sh [play | smoke [frames]]"; exit 2 ;;
esac

HERE="$(cd "$(dirname "$0")" && pwd)"
REC="$(cd "$HERE/.." && pwd)"                             # recreate/
KIT="$(cd "$REC/../../../tools/recreate_kit" && pwd)"     # the shared harness (machine.h, os.h)
REPO="$(cd "$REC/../../.." && pwd)"
BIN="$REC/../bin"                                         # projects/flyingshark/bin
BUILD="$HERE/build"; DISK="$HERE/disk"
PRG="FLYSHARK.PRG"
mkdir -p "$BUILD" "$DISK/AUTO" "$DISK/A"

CC=m68k-elf-gcc
# -Wno-array-bounds is NOT here on purpose: the two places this build dereferences an absolute
#   address (the exception vectors, TOS's 200 Hz counter) carry their own `#pragma` in
#   flyshark_main.c, so the warning stays on for the ten verified cores.
# -fno-tree-loop-distribute-patterns: at -O2 GCC recognises the hand-written copy loops in
#   flyshark_backend.c and replaces them with calls to memcpy/memset — i.e. with themselves.
# shim_include FIRST: that is the whole seam.
CFLAGS="-m68000 -O2 -fno-tree-loop-distribute-patterns -ffreestanding -fno-jump-tables \
        -fomit-frame-pointer -nostdlib -DOS_NO_REFUSAL_TALLY \
        -I$HERE/shim_include -I$REC/include -I$KIT/include -Wall -Wextra \
        ${FS_DIAG_CFLAGS:-}"
if [ -n "${FS_DIAG_CFLAGS:-}" ]; then
  echo ">> DIAGNOSTIC BUILD: FS_DIAG_CFLAGS=${FS_DIAG_CFLAGS}"
  echo "   the .PRG this leaves staged is an INSTRUMENT, not a game — re-run build.sh to undo it"
fi
CORES="$(ls "$REC"/src/*.c)"

echo ">> stage drive"
PY="$REC/.venv/bin/python"; [ -x "$PY" ] || PY=python3
"$PY" "$HERE/gen_image.py" "$BIN/FLYSHARK.PRG" "$DISK/FLYSHARK.IMG"
# The eight files the boot loads and the twelve more the later levels ask for, exactly as
# `unpack_dist.py` carved them out of the release. The game opens them as `A\NAME`, relative to the
# drive it was booted from, so the subdirectory's name is the game's and not ours.
cp "$BIN"/disk/A/* "$DISK/A/"

# ---- the seam gates, before the compiler ------------------------------------------------------
# Each one is cheap and each one catches a class that otherwise compiles and then misbehaves on the
# machine (docs/on-target-execution.md, "The seam pattern", and class 12b).

# 1. EVERY `os_*` A CORE CALLS IS SHADOWED. A name this build leaves modelled would reach the
#    machine as a ledger append into a `g_os_event` nothing defines (a link error, at best) or as a
#    no-op that silently drops a trap. `os_refused` is the kit's own -DOS_NO_REFUSAL_TALLY arm.
REPLACED_OS_HELPERS="$(grep -ohE '\bos_[a-z0-9_]+' "$REC"/src/*.c | sort -u)"
for helper in $REPLACED_OS_HELPERS; do
  case "$helper" in
    os_refused) continue ;;
  esac
  grep -q "^static inline .*\b$helper(" "$HERE/shim_include/os.h" || {
    echo "ERROR: ../src/*.c calls $helper and shim_include/os.h does not shadow it"; exit 1; }
done
echo ">> os_* seam: $(echo "$REPLACED_OS_HELPERS" | wc -w | tr -d ' ') helpers the cores call, all shadowed"

# 2. THE CORES TAKE NOTHING FROM THIS DIRECTORY. A core that included a shim header directly would
#    compile differently in the two builds, which is the one thing the seam exists to prevent.
! grep -REn '#include *"(tos|flyshark)[a-z_]*\.h"' "$REC"/src "$REC"/include || {
  echo "ERROR: a core includes a shim header by name — the seam is the include PATH, not a name"
  exit 1; }

# 3. THE TRAP WRAPPERS SAVE %d2/%a2. The scan is the workspace's (docs/on-target-execution.md class
#    3) and it asserts the COUNT it evaluated, so a pattern that rotted reds rather than passing
#    vacuously. Sixteen returning wrappers: five GEMDOS file (Fopen/Fcreate/Fwrite/Fclose/Fread),
#    two GEMDOS control (Cconout/Super) plus `fs_leave_supervisor`, one BIOS (Bconout) and seven
#    XBIOS. `_start`'s own `trap #1` is Pterm0 and never returns, which is why the scan exempts it.
bash "$REPO/tools/assert_trap_registers.sh" --expect 16 "$HERE/flyshark_os.s"

# THE ONE CORE COMPILED HOTTER THAN THE REST, and it is a measured trade rather than a preference.
# `atari/profile.py ours` puts 77% of an attract frame inside `src/sprite.c`'s blitters; -O3 with
# `-funroll-loops` buys 20% of the whole frame there, and applied to EVERY core it also triples the
# program's text (50,688 -> 164,096 B), which overflows the 720 KB floppy and makes `mkfloppy.py`
# drop later levels' tile banks. Applied to this one file it costs a few KB. The SOURCE is still
# compiled unchanged — this is a flag, not a variant — and `smoke.py`'s framebuffer identity is what
# says the codegen change altered nothing.
# THE ASM TWINS. `../src/asm/sprite.S` transcribes the original's own four unclipped sprite
# blitters, `../src/asm/restore.S` its five restore blitters and its ring-seam copy, and
# `../src/asm/clipped.S` its four GATED blitter bodies; `-DFS_ASM_SPRITE` is what makes
# `../src/sprite.c`'s four seams call them instead of the C (`src/sprite.c`, "THE ASM-TWIN SEAM").
# It is ONE define for the whole of `src/asm/` rather than one per twin, and `../include/sprite.h`
# declares what it selects. The differential build never defines it, and `../test/test_asm_sprite.py`
# / `../test/test_asm_restore.py` / `../test/test_asm_clipped.py` are what prove the twins equal to
# their cores.
ASM_TWINS="$REC/src/asm/sprite.S $REC/src/asm/restore.S $REC/src/asm/clipped.S"
DEF="$DEF -DFS_ASM_SPRITE"

HOT_CORE="$REC/src/sprite.c"
HOT_CFLAGS="-O3 -funroll-loops --param max-unroll-times=2"
# `-vxF`: a FIXED whole-line match. `$HOT_CORE` is an absolute path, and a checkout directory
# holding a regex metacharacter (`+`, `[`, `(`) would make an anchored regex miss — compiling
# sprite.c twice and failing at the link, with the error naming duplicate symbols rather than this.
COOL_CORES="$(echo "$CORES" | grep -vxF "$HOT_CORE")"

echo ">> compile + link (base 0, keep relocs)"
$CC $CFLAGS $HOT_CFLAGS $DEF -c "$HOT_CORE" -o "$BUILD/sprite.o"
# ONE OBJECT PER `.S`, for the reason kit.mk assembles the suite's blob that way: the byte gate
# below asks an object what it defines, and two twins in one object would let a span pin name the
# wrong file when a body moved between them.
ASM_TWIN_OBJS=""
for twin in $ASM_TWINS; do
  obj="$BUILD/$(basename "$twin" .S)_asm.o"
  $CC $CFLAGS $DEF -c "$twin" -o "$obj"
  ASM_TWIN_OBJS="$ASM_TWIN_OBJS $obj"
done
$CC $CFLAGS $DEF -T "$HERE/tos.ld" -Wl,--emit-relocs \
    "$HERE/flyshark_os.s" "$HERE/flyshark_main.c" "$HERE/flyshark_backend.c" \
    $COOL_CORES "$BUILD/sprite.o" $ASM_TWIN_OBJS -lgcc \
    -o "$BUILD/flyshark.elf"

# THE ASM-TWIN GATE. This substitution fails SILENTLY: drop -DFS_ASM_SPRITE and the seam resolves to
# the C again, the twin still assembles, still links, still exports its name, and the game still
# draws exactly the right pixels — three times slower, with nothing but the frame rate to say so.
# `make test` would not notice either, because the C is not wrong, only slow. So the objects are
# asked directly: the twin must be DEFINED by the asm object and REFERENCED by the core that calls
# it. Proven able to fail — dropping the define reddens it and exits 1.
# ...AND THE OBJECT THAT SHIPS IS THE OBJECT THE TESTS PINNED. `test/test_asm_sprite.py` compares
# the KIT's blob (`build/asm/twins.bin`, assembled by kit.mk with its own flags — no `-O`, no
# `-ffreestanding`, and `-DRECREATE_HOST_DIFFERENTIAL` for the door stubs a twin that CALLS would
# need) against the .PRG span by span. This build assembles the same `.S` with a disjoint flag set,
# so without this line the byte pin would vouch for an object nobody assembled: the kit's own door
# mechanism invites `#ifdef RECREATE_HOST_DIFFERENTIAL` arms inside a `.S`, and the day one lands in
# a body the pin checks the off-target arm while the machine runs the other. The two are identical
# TODAY because `src/asm/sprite.S` has no conditional at all — which is exactly the property worth
# asserting rather than assuming, and it covers the C-ABI prologue and the width ladder too, neither
# of which is inside a byte-pinned span.
# ...AND THE OBJECT THAT SHIPS IS THE ORIGINAL'S OWN CODE, asserted against the original's bytes
# rather than against anything the suite built. `assert_twin_bytes.py`'s header has the argument;
# the short version is that ../test/test_asm_sprite.py pins the KIT's assembly of these `.S` files
# and this build assembles them with a disjoint flag set, so without this the byte pin would vouch
# for an object nobody assembled.
#
# NO CONDITIONAL ASSEMBLY, checked first and separately, because the span pin covers the transcribed
# BODIES and not the C-ABI prologue or the width ladder around them. An `#ifdef` is how those two
# assemblies could diverge at all (the kit's callback door selects its stubs on
# RECREATE_HOST_DIFFERENTIAL, which this build does not define), so its absence is what makes "the
# suite tested the same wrapper" true rather than hoped.
echo ">> asm twins: the shipped object against the original's own bytes"
! grep -nE '^[[:space:]]*#[[:space:]]*(if|ifdef|ifndef|else|elif|endif)' $ASM_TWINS || {
  echo "ERROR: a twin uses conditional assembly. The suite assembles these files with the kit's"
  echo "       flags and this build with its own, so an #ifdef means the bytes the tests pinned"
  echo "       and the bytes the machine runs are not the same code."; exit 1; }
python3 "$HERE/assert_twin_bytes.py" "$BUILD/sprite_asm.o" "$DISK/FLYSHARK.IMG" 0x10000 \
    sprite_blit_w16=0x153b2 sprite_blit_w32=0x15408 \
    sprite_blit_w48=0x154a4 sprite_blit_w64=0x15586
python3 "$HERE/assert_twin_bytes.py" "$BUILD/restore_asm.o" "$DISK/FLYSHARK.IMG" 0x10000 \
    restore_blit_w16=0x14d58 restore_blit_w32=0x14d6a restore_blit_w48=0x14d80 \
    restore_blit_w64=0x14d9a restore_blit_w80=0x14db8 scroll_wrap_copy_1280=0x156ae
# FOUR SEGMENTED BODIES, spelt as `<name>=<lo>:<hi>:<substitution sites>`. The gated twin's bodies
# read the clip gate with `btst #n,$16426.l` — an ABSOLUTE address, which a reconstruction whose
# image base is a run-time argument cannot name — so `../src/asm/clipped.S` substitutes
# `btst #n,(%a2)` and is pinned as the runs BETWEEN those instructions. `assert_twin_bytes.py`
# DERIVES those runs from the four numbers per body and asserts they tile the extent, which is what
# lets this list be the same four numbers `../test/test_asm_clipped.py`'s `GATED_BODIES` carries
# rather than twenty-two addresses copied by hand. What is not checked here is the substituted
# instruction itself and the `dbf` its shrink moves: those need the original's bit numbers and are
# the suite's, whose header carries the whole argument.
python3 "$HERE/assert_twin_bytes.py" "$BUILD/clipped_asm.o" "$DISK/FLYSHARK.IMG" 0x10000 \
    sprite_blit_w16_gated=0x14e1e:0x14e98:0x14e40,0x14e6c \
    sprite_blit_w32_gated=0x14f06:0x14fd8:0x14f28,0x14f80,0x14fac \
    sprite_blit_w48_gated=0x1505e:0x15188:0x15080,0x150d8,0x1512e,0x1515c \
    sprite_blit_w64_gated=0x15230:0x153b2:0x15252,0x152aa,0x15302,0x1535a,0x15386

# ONE LIST, AND IT COMES FROM THE HEADER — not from a literal here, and NOT from `../src/sprite.c`,
# which is the file being policed. A checklist grepped out of the seams could only ever confirm what
# those seams already say: delete one seam and the name leaves the list, the remaining twins check
# out, and the build goes green on exactly the silent regression this gate exists to catch. So the
# expectation is stated somewhere the seam cannot edit: `../include/sprite.h`'s prototype block,
# which is where a twin's C signature lives (../STATUS.md's "the twin's C ABI is spelt in three
# places").
#
# EACH TWIN HAS TWO ENTRY POINTS and the core may call EITHER: `<name>_asm` carries the C ABI and is
# what ../test/test_asm_sprite.py and ../test/test_asm_restore.py drive; `<name>_regs` takes the
# original's own registers and is what the two hot seams `jsr` (`src/asm/sprite.S`, "THE
# REGISTER-ABI ENTRY"). Both must be DEFINED when they exist, and the core must reference one of
# them PER TWIN — which is what makes unhooking a single seam red rather than invisible.
#
# `|| true`, so that finding NOTHING reaches the check below: under `set -e -o pipefail` a grep with
# no match would otherwise kill the script here, with an exit status and no sentence.
echo ">> asm twins: what ../include/sprite.h declares, against the objects"
ASM_TWIN_ENTRIES="$(grep -oE '\b[a-z0-9_]+_asm\(' "$REC/include/sprite.h" | tr -d '(' | sort -u || true)"
[ -n "$ASM_TWIN_ENTRIES" ] || {
  echo "ERROR: ../include/sprite.h declares no *_asm twin — either the block moved and this gate"
  echo "       now checks nothing, or the seam has genuinely gone"; exit 1; }
# The symbol tables are read ONCE into variables rather than piped into `grep -q`: under
# `set -o pipefail`, `grep -q` exits at its first match and leaves `nm` with a SIGPIPE, which makes
# the whole pipeline non-zero on a build that was perfectly good.
TWIN_DEFINED="$(m68k-elf-nm $ASM_TWIN_OBJS)"
CORE_SYMBOLS="$(m68k-elf-nm "$BUILD/sprite.o")"
# ...AND THE HEADER MUST NAME EVERY TWIN THE OBJECTS DEFINE, which is the same check inverted and is
# what stops the list going quietly short: a declaration that wrapped across two lines, or a twin
# added to a `.S` and to nothing else, would otherwise drop out of the loop below and the build
# would print a green line having checked one twin fewer than it has.
while read -r defined; do
  grep -qx "$defined" <<< "$ASM_TWIN_ENTRIES" || {
    echo "ERROR: $defined is defined by $ASM_TWINS and not declared in ../include/sprite.h, so it"
    echo "       is a twin no gate here knows about"; exit 1; }
done < <(grep -oE ' T [a-z0-9_]+_asm$' <<< "$TWIN_DEFINED" | cut -d' ' -f3 | sort -u)
for twin in $ASM_TWIN_ENTRIES; do
  grep -qE " T $twin$" <<< "$TWIN_DEFINED" || {
    echo "ERROR: $twin is not defined by $ASM_TWINS"; exit 1; }
  regs="${twin%_asm}_regs"
  called=""
  for entry in "$twin" "$regs"; do
    grep -qE " U $entry$" <<< "$CORE_SYMBOLS" && called="$entry"
  done
  [ -n "$called" ] || {
    echo "ERROR: the core calls neither $twin nor $regs — that seam resolved to the C, and the only"
    echo "       symptom would have been the frame rate"; exit 1; }
  # A register-ABI entry that EXISTS must also be the one the game enters. Otherwise the seam could
  # quietly fall back to the C ABI and pay the frame this wave measured and removed.
  if grep -qE " T $regs$" <<< "$TWIN_DEFINED" && [ "$called" != "$regs" ]; then
    echo "ERROR: $regs is defined but the core calls $twin — the seam is back on the C ABI"; exit 1
  fi
  echo "   $twin: defined, and the core calls $called"
done

# _start must sit at the very first byte of text (GEMDOS enters there).
ENTRY=$(m68k-elf-nm "$BUILD/flyshark.elf" | awk '$3=="_start"{print $1}')
[ "$ENTRY" = "00000000" ] || { echo "ERROR: _start not at 0 (got $ENTRY)"; exit 1; }

# ...and the RECORD must survive into it. In a play build nothing reads `g_record`, so a file-static
# one is dead stores and GCC deletes it — taking with it the only thing that says where the image
# array is, which is how `smoke.py --floppy-only` locates a program that writes no files. It is a
# global for that reason and this is the check that says so (flyshark_main.c carries the argument).
m68k-elf-nm "$BUILD/flyshark.elf" | grep -qE ' [BbDd] g_record$' || {
  echo "ERROR: g_record is not in the linked program — a play build has nothing to be located by"
  exit 1; }

# Drop .debug_* (and their .rela.debug_*, which carry odd-offset fixups mkprg would choke on);
# keep .rela.text/.rela.data, the R_68K_32 fixups the GEMDOS relocation table is built from.
m68k-elf-strip --strip-debug "$BUILD/flyshark.elf"

echo ">> objcopy -> flat binary"
m68k-elf-objcopy -O binary "$BUILD/flyshark.elf" "$BUILD/flyshark.bin"

echo ">> wrap -> GEMDOS .PRG"
python3 "$HERE/mkprg.py" "$BUILD/flyshark.elf" "$BUILD/flyshark.bin" "$BUILD/$PRG"

cp "$BUILD/$PRG" "$DISK/AUTO/$PRG"
cp "$BUILD/$PRG" "$BUILD/FLYSHARK-$MODE.PRG"

echo ">> floppy"
"$PY" "$HERE/mkfloppy.py" --prg "$BUILD/$PRG" --root "$DISK" --out "$DISK/FLYSHARK.ST"

ls -l "$DISK/AUTO/$PRG" "$DISK/FLYSHARK.IMG" "$DISK/FLYSHARK.ST"
