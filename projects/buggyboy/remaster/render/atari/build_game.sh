#!/bin/bash
# Build the on-target BuggyBoy game .PRG and stage it for Hatari.
#   build_game.sh                          -> build/BUGGYBOY.PRG + disk/BUGGYBOY.PRG   (shipping: boots the leg select, with sound)
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

# --- STE hardware-blitter target (PERF30 C4): additive, opt-in via GAME_STE=1. When GAME_STE is unset
#     every variable below is empty, so the stock ST build's CFLAGS / sources / link line are
#     byte-for-byte the SAME — verified by hashing build/BUGGYBOY.PRG with the flag off. GAME_STE_SELFTEST
#     also links the on-target blitter-vs-engine proof (src/blitter_selftest.c, run_ste_selftest.py). ---
STE_CFLAGS=""; STE_SOURCES=""
if [ "${GAME_STE:-0}" = "1" ]; then
    DEFAULT_PRG=BUGGYBST.PRG
    STE_CFLAGS="-DGAME_STE"
    STE_SOURCES="$REMASTER/src/blitter.c $REMASTER/src/blitter_objshift2.c $REMASTER/src/blitter_objshift.c"   # driver + both blitter paths
    if [ "${GAME_STE_SELFTEST:-0}" = "1" ]; then
        STE_CFLAGS="$STE_CFLAGS -DGAME_STE_SELFTEST"
        STE_SOURCES="$STE_SOURCES $REMASTER/src/blitter_selftest.c"
    fi
    if [ "${GAME_STE_SWEEP:-0}" = "1" ]; then
        STE_CFLAGS="$STE_CFLAGS -DGAME_STE_SWEEP"
        STE_SOURCES="$STE_SOURCES $REMASTER/src/blitter_sweep.c"
    fi
    if [ "${GAME_STE_CENSUS:-0}" = "1" ]; then            # slice-5 boot-table census (run_ste_census.py)
        STE_CFLAGS="$STE_CFLAGS -DGAME_STE_CENSUS"
        STE_SOURCES="$STE_SOURCES $REMASTER/src/blitter_census.c"
    fi
else
    DEFAULT_PRG=BUGGYBOY.PRG
fi

PRG="${GAME_PRG:-$DEFAULT_PRG}"             # output .PRG name (run_golden.py overrides to GOLDEN.PRG)

PY="$REMASTER/../recreate/.venv/bin/python"; [ -x "$PY" ] || PY=python3

echo ">> generate game fixture (road tables + pose + HUD assets + golden) from the host harness"
"$PY" "$HERE/gen_game_fixture.py"

# The sound driver (src/sound.c) reads its baked program-data blob from build/sound_data.h; the game
# shell + flow/event/player trigger sites link src/sound_trig.c against it. Generate it before compiling
# (idempotent, like gen_game_fixture.py above).
echo ">> generate sound fixture (const tables + tune streams + Dosound lists) for the sound driver"
"$PY" "$HERE/gen_sound_fixture.py"

CC=m68k-elf-gcc
# -O3 (was -O2, not -Os): the road blit primitives must inline or the per-column call overhead ~doubles
# the render cost (see tools/bench.py). -O3 over -O2 measured -16,746 cyc on the gate frame and must
# match bench_build.sh flag-for-flag (run_golden.py verifies THIS build byte-exact under these flags —
# see PERF30.md "GCC-level sweep"). rm_blit_objshift also carries a per-function optimize() attribute in
# blit.c that is paired with this -O3. -fno-tree-loop-distribute-patterns keeps the hand-written fill
# loops from being turned into libc calls.
# -DRM_ASM_BLIT: dispatch both fine-x blitters (object_list.c's RM_BLIT_OBJSHIFT2 fixed-pass +
# RM_BLIT_OBJSHIFT colour-indexed pass 1) to the hand-written m68k cores src/asm/objshift2.S / objshift.S
# (PERF30 A3). run_golden.py verifies THIS build byte-exact in Hatari, which is the end-to-end pin that
# both asm paths draw the same pixels as the C references.
# -DRM_SOUND_TARGET: the on-target sound seam. It (a) swaps src/sound_trig.c's host Dosound ledger for
# the real XBIOS Dosound game_main.c provides over the baked SND_DOSOUND blob, and (b) turns the
# RM_SOUND_LOCK/UNLOCK trigger-mutation guards into the shell's VBL-reentrancy counter (no-ops on the
# host/bench builds, so the differential .so is unchanged). See game_main.c's sound-pump section.
# -DRM_ASM_ROAD: dispatch the WHOLE road (all seven band writers A/B/C-near/C-far/D) to the hand-written
# m68k cores src/asm/road_band.S (PERF30 road-asm slices 1-3). render_road now runs at 1.11x the original's
# hand-asm (230,766 cyc), no band inlined, no de-inline tax (see PERF30.md "Road-asm slice 3"). run_golden.py
# verifies THIS build byte-exact in Hatari — the end-to-end pin that every asm band draws the same pixels as
# its C reference. (No -DRM_ROAD_DIFF: the game omits road.c's bench-only differential entries.)
CFLAGS="-m68000 -O3 -fno-tree-loop-distribute-patterns -ffreestanding -fno-jump-tables \
        -fomit-frame-pointer -nostdlib -DRM_ASM_BLIT -DRM_ASM_ROAD -DRM_SOUND_TARGET -I$REMASTER/include -I$HERE/shim_include -I$BUILD -Wall -Wextra \
        ${STE_CFLAGS} ${GAME_EXTRA_CFLAGS:-}"
CORES="$REMASTER/src/geometry.c $REMASTER/src/road.c $REMASTER/src/scroll.c \
       $REMASTER/src/course.c $REMASTER/src/hud.c $REMASTER/src/text.c \
       $REMASTER/src/ground.c $REMASTER/src/sprite.c $REMASTER/src/object.c \
       $REMASTER/src/blit.c $REMASTER/src/object_list.c $REMASTER/src/gameplay.c \
       $REMASTER/src/player.c $REMASTER/src/events.c $REMASTER/src/assets.c \
       $REMASTER/src/intermission.c $REMASTER/src/results.c $REMASTER/src/flow.c \
       $REMASTER/src/sound.c $REMASTER/src/sound_trig.c $REMASTER/src/frame.c"

echo ">> compile + link (base 0, keep relocs)"
$CC $CFLAGS -T "$HERE/tos.ld" -Wl,--emit-relocs \
    "$HERE/os.s" "$REMASTER/src/asm/objshift2.S" "$REMASTER/src/asm/objshift.S" \
    "$REMASTER/src/asm/road_band.S" \
    "$HERE/shim.c" "$HERE/game_main.c" $CORES $STE_SOURCES -lgcc \
    -o "$BUILD/game.elf"

# _start must sit at the very first byte of text (GEMDOS enters there).
ENTRY=$(m68k-elf-nm "$BUILD/game.elf" | awk '$3=="_start"{print $1}')
[ "$ENTRY" = "00000000" ] || { echo "ERROR: _start not at 0 (got $ENTRY)"; exit 1; }

echo ">> objcopy -> flat binary"
m68k-elf-objcopy -O binary "$BUILD/game.elf" "$BUILD/game.bin"

echo ">> wrap -> GEMDOS .PRG"
"$PY" "$HERE/mkprg.py" "$BUILD/game.elf" "$BUILD/game.bin" "$BUILD/$PRG"

# GAME_NO_STAGE=1 stops here with the .PRG built but NOT copied to the Hatari drive. `make test`'s build
# gate sets it: the gate only needs to know the shell compiles and links, and re-staging disk/ on every
# test run would litter the mounted drive and could rewrite its data files under a running emulator.
if [ "${GAME_NO_STAGE:-0}" = "1" ]; then
    ls -l "$BUILD/$PRG"
    exit 0
fi

cp "$BUILD/$PRG" "$DISK/$PRG"

# The game reads its own data files at boot (see include/assets.h), so they ship on the disk alongside
# the .PRG instead of being baked into it.
for data in COURSES.DAT GRAPHICS.GRA; do
    cp "$REMASTER/../bin/$data" "$DISK/$data"
done
ls -l "$DISK/$PRG" "$DISK/COURSES.DAT" "$DISK/GRAPHICS.GRA"
