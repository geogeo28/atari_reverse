#!/bin/bash
# Build the on-target BuggyBoy game .PRG and stage it for Hatari.
#   build_game.sh                          -> build/BUGGYBOY.PRG + disk/BUGGYBOY.PRG   (shipping: boots the leg select, no sound)
#   GAME_PRG=GOLDEN.PRG GAME_EXTRA_CFLAGS="-DGOLDEN_BOOT_LEG=0" build_game.sh
#                                          -> build/GOLDEN.PRG  + disk/GOLDEN.PRG      (golden harness variant: boots straight
#                                                                                       into leg 0 + dumps frame 0)
# Bakes the non-asset-file inputs (gen_game_fixture.py) into build/game_fixture.h, cross-compiles
# remaster's whole ported pipeline + the game shell + the TOS shim, and wraps to a GEMDOS .PRG. build/
# and disk/ are gitignored. Requires the recreate .so to be built (the fixture generator drives it).
#
# The SHIPPING BUGGYBOY.PRG carries no boot fast path — it boots into the leg select. The golden harness
# (run_golden.py) builds the GOLDEN.PRG variant with -DGOLDEN_BOOT_LEG=N so a fast-path frame-0 dump can
# be pinned byte-for-byte against recreate. GAME_EXTRA_CFLAGS also carries the debug flags (e.g.
# -DGAME_DUMP_STAGE=3 to cut the frame short and dump a partial render). Empty in a plain shipping build.
#
# Env knobs (all passed through to gen_game_fixture.py):
#   GAME_PRG=<name>   output .PRG name (default BUGGYBOY.PRG; run_golden.py -> GOLDEN.PRG).
#   GEN_GOLDEN=1      also render build/golden_leg<N>.bin + palette_leg<N>.bin (the golden-harness
#                     reference frame for leg GOLDEN_LEG). ONLY run_golden.py consumes those, so a plain
#                     shipping/bench build leaves it unset and skips that heavy full-pipeline render;
#                     game_fixture.h is generated either way.
#   GOLDEN_LEG=N      the golden-harness boot leg 0-4 (default 0): parameterises the golden render + the
#                     GAME_LEG_INDEX define. run_golden.py sets it == -DGOLDEN_BOOT_LEG so both sides agree.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REMASTER="$(cd "$HERE/../.." && pwd)"       # remaster/
BUILD="$HERE/build"; DISK="$HERE/disk"
mkdir -p "$BUILD" "$DISK"

PRG="${GAME_PRG:-BUGGYBOY.PRG}"             # output .PRG name (run_golden.py overrides to GOLDEN.PRG)

PY="$REMASTER/../recreate/.venv/bin/python"; [ -x "$PY" ] || PY=python3

echo ">> generate game fixture (road tables + pose + HUD assets + golden) from the host harness"
"$PY" "$HERE/gen_game_fixture.py"

CC=m68k-elf-gcc
# -O2 (not -Os): the road blit primitives must inline or the per-column call overhead ~doubles the
# render cost (see tools/bench.py). -fno-tree-loop-distribute-patterns keeps the hand-written fill
# loops from being turned into libc calls.
CFLAGS="-m68000 -O2 -fno-tree-loop-distribute-patterns -ffreestanding -fno-jump-tables \
        -fomit-frame-pointer -nostdlib -I$REMASTER/include -I$HERE/shim_include -I$BUILD -Wall -Wextra \
        ${GAME_EXTRA_CFLAGS:-}"
CORES="$REMASTER/src/geometry.c $REMASTER/src/road.c $REMASTER/src/scroll.c \
       $REMASTER/src/course.c $REMASTER/src/hud.c $REMASTER/src/text.c \
       $REMASTER/src/ground.c $REMASTER/src/sprite.c $REMASTER/src/object.c \
       $REMASTER/src/blit.c $REMASTER/src/object_list.c $REMASTER/src/gameplay.c \
       $REMASTER/src/player.c $REMASTER/src/events.c $REMASTER/src/assets.c \
       $REMASTER/src/intermission.c $REMASTER/src/results.c $REMASTER/src/flow.c \
       $REMASTER/src/frame.c"

echo ">> compile + link (base 0, keep relocs)"
$CC $CFLAGS -T "$HERE/tos.ld" -Wl,--emit-relocs \
    "$HERE/os.s" "$HERE/shim.c" "$HERE/game_main.c" $CORES -lgcc -o "$BUILD/game.elf"

# _start must sit at the very first byte of text (GEMDOS enters there).
ENTRY=$(m68k-elf-nm "$BUILD/game.elf" | awk '$3=="_start"{print $1}')
[ "$ENTRY" = "00000000" ] || { echo "ERROR: _start not at 0 (got $ENTRY)"; exit 1; }

echo ">> objcopy -> flat binary"
m68k-elf-objcopy -O binary "$BUILD/game.elf" "$BUILD/game.bin"

echo ">> wrap -> GEMDOS .PRG"
"$PY" "$HERE/mkprg.py" "$BUILD/game.elf" "$BUILD/game.bin" "$BUILD/$PRG"

cp "$BUILD/$PRG" "$DISK/$PRG"

# The game reads its own data files at boot (see include/assets.h), so they ship on the disk alongside
# the .PRG instead of being baked into it.
for data in COURSES.DAT GRAPHICS.GRA; do
    cp "$REMASTER/../bin/$data" "$DISK/$data"
done
ls -l "$DISK/$PRG" "$DISK/COURSES.DAT" "$DISK/GRAPHICS.GRA"
