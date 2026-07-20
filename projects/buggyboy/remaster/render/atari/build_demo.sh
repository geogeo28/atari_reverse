#!/bin/bash
# Build the interactive road + HUD demo .PRG and stage a drive for Hatari.
#   build_demo.sh     -> build/DEMO.PRG + disk/DEMO.PRG
# Bakes the captured road + HUD inputs (gen_demo_fixture.py) into build/demo_fixture.h, cross-compiles
# remaster's geometry + road + HUD cores + the TOS shim, and wraps to a GEMDOS .PRG. build/ and disk/
# are gitignored. Requires the recreate .so to be built (the fixture generator drives it).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REMASTER="$(cd "$HERE/../.." && pwd)"       # remaster/
BUILD="$HERE/build"; DISK="$HERE/disk"
mkdir -p "$BUILD" "$DISK"

PY="$REMASTER/../recreate/.venv/bin/python"; [ -x "$PY" ] || PY=python3

echo ">> generate demo fixture (road tables + pose + HUD assets + golden) from the host harness"
"$PY" "$HERE/gen_demo_fixture.py"

CC=m68k-elf-gcc
# -O2 (not -Os): the road blit primitives must inline or the per-column call overhead ~doubles the
# render cost (see tools/bench.py). -fno-tree-loop-distribute-patterns keeps the hand-written fill
# loops from being turned into libc calls.
CFLAGS="-m68000 -O2 -fno-tree-loop-distribute-patterns -ffreestanding -fno-jump-tables \
        -fomit-frame-pointer -nostdlib -I$REMASTER/include -I$HERE/shim_include -I$BUILD -Wall -Wextra"
CORES="$REMASTER/src/geometry.c $REMASTER/src/road.c $REMASTER/src/scroll.c $REMASTER/src/course.c $REMASTER/src/hud.c $REMASTER/src/text.c"

echo ">> compile + link (base 0, keep relocs)"
$CC $CFLAGS -T "$HERE/tos.ld" -Wl,--emit-relocs \
    "$HERE/os.s" "$HERE/demo_main.c" $CORES -lgcc -o "$BUILD/demo.elf"

# _start must sit at the very first byte of text (GEMDOS enters there).
ENTRY=$(m68k-elf-nm "$BUILD/demo.elf" | awk '$3=="_start"{print $1}')
[ "$ENTRY" = "00000000" ] || { echo "ERROR: _start not at 0 (got $ENTRY)"; exit 1; }

echo ">> objcopy -> flat binary"
m68k-elf-objcopy -O binary "$BUILD/demo.elf" "$BUILD/demo.bin"

echo ">> wrap -> GEMDOS .PRG"
"$PY" "$HERE/mkprg.py" "$BUILD/demo.elf" "$BUILD/demo.bin" "$BUILD/DEMO.PRG"

cp "$BUILD/DEMO.PRG" "$DISK/DEMO.PRG"
ls -l "$DISK/DEMO.PRG"
