#!/bin/bash
# Build a demo .PRG with the m68k-elf toolchain and stage a drive for Hatari.
#   build.sh [leg|results|highscore|intermission]   (default: leg)
#     leg          -> disk/DEMO.PRG          runs g_draw_leg_results
#     results      -> disk/RESULTS.PRG       runs g_draw_results_screen
#     highscore    -> disk/HIGHSCORE.PRG     g_update_highscore (populate table) then g_draw_results_screen
#     intermission -> disk/INTERMISSION.PRG  g_init_scoretable then g_draw_intermission (scroller)
# All stage disk/{STATIC.BIN,GRAPHICS.GRA,COURSES.DAT}; highscore also stages HISCORE.BIN.
# build/ and disk/ are gitignored.
set -euo pipefail

SCREEN="${1:-leg}"
case "$SCREEN" in
  leg)          DEF="";                 PRG="DEMO.PRG" ;;
  results)      DEF="-DDEMO_RESULTS";   PRG="RESULTS.PRG" ;;
  highscore)    DEF="-DDEMO_HIGHSCORE"; PRG="HIGHSCORE.PRG" ;;
  intermission) DEF="-DDEMO_INTERMISSION"; PRG="INTERMISSION.PRG" ;;
  *) echo "usage: build.sh [leg|results|highscore|intermission]"; exit 2 ;;
esac

HERE="$(cd "$(dirname "$0")" && pwd)"
REC="$(cd "$HERE/../.." && pwd)"          # recreate/
BIN="$REC/../bin"                          # projects/buggyboy/bin
BUILD="$HERE/build"; DISK="$HERE/disk"
mkdir -p "$BUILD" "$DISK"

CC=m68k-elf-gcc
CFLAGS="-m68000 -Os -ffreestanding -fno-jump-tables -fomit-frame-pointer -nostdlib \
        -I$REC/include -I$HERE/shim_include -Wall"
# highscore/intermission pull in g_init_scoretable/g_update_highscore (highscore.c),
# g_draw_intermission (intermission.c) and, via update_highscore, g_EGOFF (sound.c).
CORES="$REC/src/results.c $REC/src/screen.c $REC/src/text.c $REC/src/graphics.c \
       $REC/src/highscore.c $REC/src/intermission.c $REC/src/sound.c"

echo ">> compile + link $SCREEN (base 0, keep relocs)"
$CC $CFLAGS $DEF -T "$HERE/tos.ld" -Wl,--emit-relocs \
    "$HERE/os.s" "$HERE/main.c" $CORES -lgcc -o "$BUILD/demo.elf"

# _start must sit at the very first byte of text (GEMDOS enters there).
ENTRY=$(m68k-elf-nm "$BUILD/demo.elf" | awk '$3=="_start"{print $1}')
[ "$ENTRY" = "00000000" ] || { echo "ERROR: _start not at 0 (got $ENTRY)"; exit 1; }

echo ">> objcopy -> flat binary"
m68k-elf-objcopy -O binary "$BUILD/demo.elf" "$BUILD/demo.bin"

echo ">> wrap -> GEMDOS .PRG"
python3 "$HERE/mkprg.py" "$BUILD/demo.elf" "$BUILD/demo.bin" "$BUILD/$PRG"

echo ">> stage drive"
PY="$REC/.venv/bin/python"; [ -x "$PY" ] || PY=python3
cp "$BUILD/$PRG" "$DISK/$PRG"
"$PY" "$HERE/gen_static.py" "$BIN/BUGGYBOY.PRG" "$DISK/STATIC.BIN"
cp "$BIN/GRAPHICS.GRA" "$DISK/GRAPHICS.GRA"
cp "$BIN/COURSES.DAT" "$DISK/COURSES.DAT"
[ "$SCREEN" = highscore ] && "$PY" "$HERE/gen_hiscore.py" "$DISK/HISCORE.BIN"
ls -l "$DISK"
