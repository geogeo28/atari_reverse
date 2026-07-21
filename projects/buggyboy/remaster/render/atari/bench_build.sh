#!/bin/bash
# Build the remaster render cores + bench wrappers to a 68000 ELF for cycle benchmarking.
#   bench_build.sh   -> build/bench.elf   (loaded by tools/bench.py into Musashi)
# Same toolchain/flags as build_demo.sh, but links bench_main.c (per-function entry wrappers) instead
# of the demo shim, and stops at the ELF (no .PRG). Requires the recreate .so (fixture generator).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REMASTER="$(cd "$HERE/../.." && pwd)"
BUILD="$HERE/build"; mkdir -p "$BUILD"

PY="$REMASTER/../recreate/.venv/bin/python"; [ -x "$PY" ] || PY=python3

echo ">> generate demo fixture (shared with the demo) for the bench structs"
"$PY" "$HERE/gen_demo_fixture.py" >/dev/null

CC=m68k-elf-gcc
# -O2 (matching recreate's recon) so the hot blit primitives inline; -Os leaves them as calls and the
# per-column overhead dominates the road blit. -fno-tree-loop-distribute-patterns: keep GCC from
# turning the hand-written fill loops into memset/memcpy calls (as recreate does).
CFLAGS="-m68000 -O2 -fno-tree-loop-distribute-patterns -ffreestanding -fno-jump-tables \
        -fomit-frame-pointer -nostdlib -I$REMASTER/include -I$HERE/shim_include -I$BUILD -Wall -Wextra"
CORES="$REMASTER/src/geometry.c $REMASTER/src/road.c $REMASTER/src/scroll.c \
       $REMASTER/src/course.c $REMASTER/src/hud.c $REMASTER/src/text.c $REMASTER/src/assets.c"

echo ">> compile + link bench.elf (base 0, keep relocs)"
$CC $CFLAGS -T "$HERE/tos.ld" -Wl,--emit-relocs \
    "$HERE/os.s" "$HERE/shim.c" "$HERE/bench_main.c" $CORES -lgcc -o "$BUILD/bench.elf"

echo ">> objcopy -> flat binary (loaded into Musashi at base 0)"
m68k-elf-objcopy -O binary "$BUILD/bench.elf" "$BUILD/bench.bin"

echo ">> bench.elf ready:"
m68k-elf-nm "$BUILD/bench.elf" | grep -E ' T bench_' | sort
