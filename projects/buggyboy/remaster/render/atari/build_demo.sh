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
# DEMO_EXTRA_CFLAGS lets a debug run add flags (e.g. -DDEMO_DUMP_STAGE=3 to cut the frame short and
# dump a partial render, for pinpointing an on-target divergence). Empty in normal builds.
CFLAGS="-m68000 -O2 -fno-tree-loop-distribute-patterns -ffreestanding -fno-jump-tables \
        -fomit-frame-pointer -nostdlib -I$REMASTER/include -I$HERE/shim_include -I$BUILD -Wall -Wextra \
        ${DEMO_EXTRA_CFLAGS:-}"
CORES="$REMASTER/src/geometry.c $REMASTER/src/road.c $REMASTER/src/scroll.c \
       $REMASTER/src/course.c $REMASTER/src/hud.c $REMASTER/src/text.c \
       $REMASTER/src/ground.c $REMASTER/src/sprite.c $REMASTER/src/object.c \
       $REMASTER/src/blit.c $REMASTER/src/object_list.c $REMASTER/src/gameplay.c \
       $REMASTER/src/player.c $REMASTER/src/events.c $REMASTER/src/assets.c"

echo ">> compile + link (base 0, keep relocs)"
$CC $CFLAGS -T "$HERE/tos.ld" -Wl,--emit-relocs \
    "$HERE/os.s" "$HERE/shim.c" "$HERE/demo_main.c" $CORES -lgcc -o "$BUILD/demo.elf"

# _start must sit at the very first byte of text (GEMDOS enters there).
ENTRY=$(m68k-elf-nm "$BUILD/demo.elf" | awk '$3=="_start"{print $1}')
[ "$ENTRY" = "00000000" ] || { echo "ERROR: _start not at 0 (got $ENTRY)"; exit 1; }

echo ">> objcopy -> flat binary"
m68k-elf-objcopy -O binary "$BUILD/demo.elf" "$BUILD/demo.bin"

echo ">> wrap -> GEMDOS .PRG"
"$PY" "$HERE/mkprg.py" "$BUILD/demo.elf" "$BUILD/demo.bin" "$BUILD/DEMO.PRG"

cp "$BUILD/DEMO.PRG" "$DISK/DEMO.PRG"

# The demo reads the game's own data files at boot (see include/assets.h), so they ship on the disk
# alongside the .PRG instead of being baked into it.
for data in COURSES.DAT GRAPHICS.GRA; do
    cp "$REMASTER/../bin/$data" "$DISK/$data"
done
ls -l "$DISK/DEMO.PRG" "$DISK/COURSES.DAT" "$DISK/GRAPHICS.GRA"
