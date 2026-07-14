#!/bin/bash
# Build the leg-results demo .PRG with the m68k-elf toolchain and stage a drive for Hatari.
#   build.sh        -> render/atari/build/DEMO.PRG + render/atari/disk/{DEMO.PRG,STATIC.BIN,GRAPHICS.GRA}
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REC="$(cd "$HERE/../.." && pwd)"          # recreate/
BIN="$REC/../bin"                          # projects/buggyboy/bin
BUILD="$HERE/build"; DISK="$HERE/disk"
mkdir -p "$BUILD" "$DISK"

CC=m68k-elf-gcc
CFLAGS="-m68000 -Os -ffreestanding -fno-jump-tables -fomit-frame-pointer -nostdlib \
        -I$REC/include -I$HERE/shim_include -Wall"
CORES="$REC/src/results.c $REC/src/screen.c $REC/src/text.c $REC/src/graphics.c"

echo ">> compile + link (base 0, keep relocs)"
$CC $CFLAGS -T "$HERE/tos.ld" -Wl,--emit-relocs \
    "$HERE/os.s" "$HERE/main.c" $CORES -lgcc -o "$BUILD/demo.elf"

# _start must sit at the very first byte of text (GEMDOS enters there).
ENTRY=$(m68k-elf-nm "$BUILD/demo.elf" | awk '$3=="_start"{print $1}')
[ "$ENTRY" = "00000000" ] || { echo "ERROR: _start not at 0 (got $ENTRY)"; exit 1; }

echo ">> objcopy -> flat binary"
m68k-elf-objcopy -O binary "$BUILD/demo.elf" "$BUILD/demo.bin"

echo ">> wrap -> GEMDOS .PRG"
python3 "$HERE/mkprg.py" "$BUILD/demo.elf" "$BUILD/demo.bin" "$BUILD/DEMO.PRG"

echo ">> stage drive"
PY="$REC/.venv/bin/python"; [ -x "$PY" ] || PY=python3
cp "$BUILD/DEMO.PRG" "$DISK/DEMO.PRG"
"$PY" "$HERE/gen_static.py" "$BIN/BUGGYBOY.PRG" "$DISK/STATIC.BIN"
cp "$BIN/GRAPHICS.GRA" "$DISK/GRAPHICS.GRA"
ls -l "$DISK"
