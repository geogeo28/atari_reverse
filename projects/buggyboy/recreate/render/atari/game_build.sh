#!/bin/bash
# Build the playable BuggyBoy .PRG with the m68k-elf toolchain and stage a drive for Hatari.
#   game_build.sh          -> disk/BUGGY.PRG  (the full game)
#   game_build.sh smoke    -> disk/BUGGY.PRG  built with -DSMOKE=<frames>: skip leg-select, run N
#                             race frames, dump C:\SCREEN.BIN, terminate (headless verification)
# Stages disk/{STATIC.BIN,GRAPHICS.GRA,COURSES.DAT}. build/ and disk/ are gitignored.
#
# Unlike build.sh (static-screen demos), this links the WHOLE reconstruction: every core plus the
# game shim (game_main.c) and its trap/hardware wrappers (game_os.s). The shim's strong
# g_flip_screen / g_wait_vbl_set_offset override the (weak) harness stubs; the rest of the no-op
# glue (os.c) is replaced by the shim, so os.c is not compiled here.
set -euo pipefail

SMOKE_FRAMES=120
case "${1:-}" in
  smoke)   DEF="-DSMOKE=$SMOKE_FRAMES" ;;
  legdump) DEF="-DSMOKE=1 -DSMOKE_LEG" ;;   # draw g_draw_leg_results, dump it, terminate (byte check)
  "")      DEF="" ;;
  *) echo "usage: game_build.sh [smoke|legdump]"; exit 2 ;;
esac

HERE="$(cd "$(dirname "$0")" && pwd)"
REC="$(cd "$HERE/../.." && pwd)"          # recreate/
BIN="$REC/../bin"                          # projects/buggyboy/bin
BUILD="$HERE/build"; DISK="$HERE/disk"
PRG="BUGGY.PRG"
mkdir -p "$BUILD" "$DISK"

CC=m68k-elf-gcc
# -Wno-array-bounds: the shim dereferences fixed hardware/sysvar addresses (video shifter, YM2149,
# IKBD ACIA, _vblqueue) as absolute pointers, which GCC flags as out-of-bounds array[0] accesses.
CFLAGS="-m68000 -Os -ffreestanding -fno-jump-tables -fomit-frame-pointer -nostdlib \
        -I$REC/include -I$HERE/shim_include -Wall -Wno-array-bounds"
# All cores except os.c (the shim supplies its OS/hardware glue).
CORES="$(ls "$REC"/src/*.c "$REC"/src/machine/*.c | grep -v '/os\.c$')"

echo ">> compile + link game (base 0, keep relocs)"
$CC $CFLAGS $DEF -T "$HERE/tos.ld" -Wl,--emit-relocs \
    "$HERE/game_os.s" "$HERE/game_main.c" $CORES -lgcc -o "$BUILD/game.elf"

# _start must sit at the very first byte of text (GEMDOS enters there).
ENTRY=$(m68k-elf-nm "$BUILD/game.elf" | awk '$3=="_start"{print $1}')
[ "$ENTRY" = "00000000" ] || { echo "ERROR: _start not at 0 (got $ENTRY)"; exit 1; }

# Drop .debug_* (and their .rela.debug_*, which carry odd-offset fixups mkprg would choke on);
# keep .rela.text/.rela.data, the R_68K_32 fixups the GEMDOS reloc table is built from.
m68k-elf-strip --strip-debug "$BUILD/game.elf"

echo ">> objcopy -> flat binary"
m68k-elf-objcopy -O binary "$BUILD/game.elf" "$BUILD/game.bin"

echo ">> wrap -> GEMDOS .PRG"
python3 "$HERE/mkprg.py" "$BUILD/game.elf" "$BUILD/game.bin" "$BUILD/$PRG"

echo ">> stage drive"
PY="$REC/.venv/bin/python"; [ -x "$PY" ] || PY=python3
cp "$BUILD/$PRG" "$DISK/$PRG"
"$PY" "$HERE/gen_static.py" "$BIN/BUGGYBOY.PRG" "$DISK/STATIC.BIN"
cp "$BIN/GRAPHICS.GRA" "$DISK/GRAPHICS.GRA"
cp "$BIN/COURSES.DAT" "$DISK/COURSES.DAT"
ls -l "$DISK/$PRG"
