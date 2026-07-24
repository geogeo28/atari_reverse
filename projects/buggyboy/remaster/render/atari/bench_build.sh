#!/bin/bash
# Build the remaster render cores + bench wrappers to a 68000 ELF for cycle benchmarking.
#   bench_build.sh   -> build/bench.elf   (loaded by tools/bench.py into Musashi)
# Same toolchain/flags as build_game.sh, but links bench_main.c (per-function entry wrappers) instead
# of the game shim, and stops at the ELF (no .PRG). Requires the recreate .so (fixture generator).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REMASTER="$(cd "$HERE/../.." && pwd)"
BUILD="$HERE/build"; mkdir -p "$BUILD"

PY="$REMASTER/../recreate/.venv/bin/python"; [ -x "$PY" ] || PY=python3

echo ">> generate game fixture (shared with the game) for the bench structs"
"$PY" "$HERE/gen_game_fixture.py" >/dev/null

CC=m68k-elf-gcc
# -O3 (was -O2) so the hot blit primitives inline; -Os leaves them as calls and the per-column overhead
# dominates the road blit. -O3 over -O2 measured -16,746 cyc on the gate frame (172.08 -> 169.99 ms):
# both fine-x engines improve (objshift -4,768, objshift2 -834) and the objsprite family broadly
# (draw_buggy -4,812, draw_fg_sprite -2,716, draw_ground -2,224), for -0.17 ms only on draw_hud (within
# noise) — see PERF30.md "GCC-level sweep". rm_blit_objshift additionally carries a per-function
# optimize() attribute (blit.c) that MUST stay paired with this -O3. -fno-tree-loop-distribute-patterns:
# keep GCC from turning the hand-written fill loops into memset/memcpy calls (as recreate does).
# -DRM_ASM_BLIT: link BOTH hand-written m68k cores (src/asm/objshift2.S fixed-pass + src/asm/objshift.S
# colour-indexed pass 1) and dispatch both blitters (object_list.c's RM_BLIT_OBJSHIFT2 / RM_BLIT_OBJSHIFT)
# to them, EXACTLY like the game build — so the composed rows (bench_objlist_fixed / bench_object_tree /
# bench_draw_frame) measure the asm the game runs. The C references rm_blit_objshift2 / rm_blit_objshift
# are still compiled (blit.c) and linked, so bench_main.c's bench_objshift2_c/_asm and bench_objshift_c/_asm
# wrappers can measure C vs asm side by side (PERF30 A3).
CFLAGS="-m68000 -O3 -fno-tree-loop-distribute-patterns -ffreestanding -fno-jump-tables \
        -fomit-frame-pointer -nostdlib -DRM_ASM_BLIT -I$REMASTER/include -I$HERE/shim_include -I$BUILD -Wall -Wextra"
CORES="$REMASTER/src/geometry.c $REMASTER/src/road.c $REMASTER/src/scroll.c \
       $REMASTER/src/course.c $REMASTER/src/hud.c $REMASTER/src/text.c \
       $REMASTER/src/ground.c $REMASTER/src/sprite.c $REMASTER/src/object.c \
       $REMASTER/src/blit.c $REMASTER/src/object_list.c $REMASTER/src/gameplay.c \
       $REMASTER/src/player.c $REMASTER/src/events.c $REMASTER/src/assets.c"

echo ">> compile + link bench.elf (base 0, keep relocs)"
$CC $CFLAGS -T "$HERE/tos.ld" -Wl,--emit-relocs \
    "$HERE/os.s" "$REMASTER/src/asm/objshift2.S" "$REMASTER/src/asm/objshift.S" \
    "$HERE/shim.c" "$HERE/bench_main.c" $CORES -lgcc \
    -o "$BUILD/bench.elf"

echo ">> objcopy -> flat binary (loaded into Musashi at base 0)"
m68k-elf-objcopy -O binary "$BUILD/bench.elf" "$BUILD/bench.bin"

echo ">> bench.elf ready:"
m68k-elf-nm "$BUILD/bench.elf" | grep -E ' T bench_' | sort
