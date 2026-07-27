#!/bin/bash
# Build the remaster HUD demo .PRG.
#   build.sh          -> build/HUD.PRG   (run_hatari.py boots it from there)
# Bakes the captured HUD inputs (gen_hud_fixture.py) into build/hud_fixture.h, cross-compiles
# remaster's HUD (hud.c + text.c) + the TOS shim, and wraps to a GEMDOS .PRG. build/ is gitignored.
# Requires the recreate .so to be built (the fixture generator drives it).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REMASTER="$(cd "$HERE/../.." && pwd)"       # remaster/
BUILD="$HERE/build"
mkdir -p "$BUILD"

PY="$REMASTER/../recreate/.venv/bin/python"; [ -x "$PY" ] || PY=python3

echo ">> generate HUD fixture (background + assets + golden) from the host harness"
"$PY" "$HERE/gen_hud_fixture.py"

CC=m68k-elf-gcc
CFLAGS="-m68000 -Os -ffreestanding -fno-jump-tables -fomit-frame-pointer -nostdlib \
        -I$REMASTER/include -I$HERE/shim_include -I$BUILD -Wall -Wextra"
CORES="$REMASTER/src/hud.c $REMASTER/src/text.c"

echo ">> compile + link (base 0, keep relocs)"
$CC $CFLAGS -T "$HERE/tos.ld" -Wl,--emit-relocs \
    "$HERE/os.s" "$HERE/shim.c" "$HERE/main.c" $CORES -lgcc -o "$BUILD/hud.elf"

# _start must sit at the very first byte of text (GEMDOS enters there).
ENTRY=$(m68k-elf-nm "$BUILD/hud.elf" | awk '$3=="_start"{print $1}')
[ "$ENTRY" = "00000000" ] || { echo "ERROR: _start not at 0 (got $ENTRY)"; exit 1; }

echo ">> objcopy -> flat binary"
m68k-elf-objcopy -O binary "$BUILD/hud.elf" "$BUILD/hud.bin"

echo ">> wrap -> GEMDOS .PRG"
"$PY" "$HERE/mkprg.py" "$BUILD/hud.elf" "$BUILD/hud.bin" "$BUILD/HUD.PRG"

ls -l "$BUILD/HUD.PRG"
