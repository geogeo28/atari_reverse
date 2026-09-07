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
# THE CORES ARE COMPILED UNCHANGED — the only build-level difference from the differential .so is
# the INCLUDE PATH (shim_include/ shadows the kit's os.h, hw.h, psg.h and sched.h with the real-TOS
# ones, and ../include/init.h with its two XBIOS answers) and the kit sources that are left out:
# src/hw.c, src/psg.c, src/sched.c and src/os_log.c, whose work the shim does for real. See
# README.md's seam table.
set -euo pipefail

# The smoke build's default frame limit, which smoke.py's SMOKE_ATTRACT_FRAMES mirrors and asserts.
# 200 attract frames is past the prescroll, past two of the three text pages, and eighty frames past
# the framebuffer differential's own anchor (smoke.py's ANCHOR_SCROLL_POS = attract frame 120).
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
        -I$HERE/shim_include -I$REC/include -I$KIT/include -Wall -Wextra"
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

echo ">> compile + link (base 0, keep relocs)"
$CC $CFLAGS $DEF -T "$HERE/tos.ld" -Wl,--emit-relocs \
    "$HERE/flyshark_os.s" "$HERE/flyshark_main.c" "$HERE/flyshark_backend.c" $CORES -lgcc \
    -o "$BUILD/flyshark.elf"

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
