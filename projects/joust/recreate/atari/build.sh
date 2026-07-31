#!/bin/bash
# Build JOUST.PRG from the verified reconstruction with the m68k-elf cross toolchain, and stage a
# drive for Hatari.
#
#   build.sh              -> disk/JOUST.PRG   playable build (real console + real joysticks)
#   build.sh title        -> disk/JOUST.PRG   -DSMOKE_TITLE: dump the title screen and terminate
#   build.sh smoke [N]    -> disk/JOUST.PRG   -DSMOKE_FRAMES=N: type '1', run N frames, dump
#
# Stages disk/{JOUST.PRG,JOUST.IMG,HIGH.SCO}. build/ and disk/ are gitignored.
#
# The cores are compiled UNCHANGED — the only build-level difference from the differential .so is
# the include path (shim_include/ shadows the kit's os.h with the real-TOS one) and the two kit
# sources that are left out: src/dosound_log.c, whose g_dosound joust_main.c supplies for real, and
# src/os_refusal.c, whose tally -DOS_NO_REFUSAL_TALLY compiles away (the kit's os.h anticipates
# exactly this build). See README.md.
set -euo pipefail

SMOKE_FRAMES_DEFAULT=240          # past frame 156, where the first gameplay play_sound fires
KEY_ONE_PLAYER=0x31              # '1' — the console key title_screen starts a one-player game on
KEY_AFTER_POLLS=8                # console polls to leave for a real key before typing it ourselves
EARLY_FRAME=2                    # the second gameplay frame is dumped too, to witness animation

case "${1:-}" in
  title) DEF="-DSMOKE -DSMOKE_TITLE" ;;
  smoke) DEF="-DSMOKE -DSMOKE_FRAMES=${2:-$SMOKE_FRAMES_DEFAULT} -DSMOKE_EARLY_FRAME=$EARLY_FRAME \
              -DSMOKE_KEY=$KEY_ONE_PLAYER -DSMOKE_KEY_AFTER=$KEY_AFTER_POLLS" ;;
  "")    DEF="" ;;
  *) echo "usage: build.sh [title | smoke [frames]]"; exit 2 ;;
esac

HERE="$(cd "$(dirname "$0")" && pwd)"
REC="$(cd "$HERE/.." && pwd)"                             # recreate/
KIT="$(cd "$REC/../../../tools/recreate_kit" && pwd)"     # the shared harness (machine.h, os.h)
BIN="$REC/../bin"                                         # projects/joust/bin
BUILD="$HERE/build"; DISK="$HERE/disk"
PRG="JOUST.PRG"
mkdir -p "$BUILD" "$DISK"

CC=m68k-elf-gcc
# -Wno-array-bounds: the shim dereferences fixed hardware / system-variable addresses (the shifter's
#   colour registers, the IKBD ACIA, _vblqueue) as absolute pointers, which GCC reads as an
#   out-of-bounds array[0] access.
# -fno-tree-loop-distribute-patterns: at -O2 GCC recognises the hand-written memcpy/memset loops in
#   joust_main.c and replaces them with calls to memcpy/memset — i.e. with themselves.
# shim_include FIRST: that is the whole seam (shim_include/os.h shadows the kit's).
CFLAGS="-m68000 -O2 -fno-tree-loop-distribute-patterns -ffreestanding -fno-jump-tables \
        -fomit-frame-pointer -nostdlib -DOS_NO_REFUSAL_TALLY \
        -I$HERE/shim_include -I$REC/include -I$KIT/include -Wall -Wextra -Wno-array-bounds"
CORES="$(ls "$REC"/src/*.c)"

# The staged image comes FIRST: its byte length is the one source of truth for how much
# joust_main.c must read back in, and it is passed straight to the compiler.
echo ">> stage drive"
PY="$REC/.venv/bin/python"; [ -x "$PY" ] || PY=python3
"$PY" "$HERE/gen_image.py" "$BIN/JOUST.PRG" "$DISK/JOUST.IMG"
cp "$BIN/HIGH.SCO" "$DISK/HIGH.SCO"
DEF="$DEF -DPROGRAM_BYTES=$(wc -c < "$DISK/JOUST.IMG" | tr -d ' ')"   # BSD wc pads with spaces

echo ">> compile + link (base 0, keep relocs)"
$CC $CFLAGS $DEF -T "$HERE/tos.ld" -Wl,--emit-relocs \
    "$HERE/joust_os.s" "$HERE/joust_main.c" $CORES -lgcc -o "$BUILD/joust.elf"

# _start must sit at the very first byte of text (GEMDOS enters there).
ENTRY=$(m68k-elf-nm "$BUILD/joust.elf" | awk '$3=="_start"{print $1}')
[ "$ENTRY" = "00000000" ] || { echo "ERROR: _start not at 0 (got $ENTRY)"; exit 1; }

# Drop .debug_* (and their .rela.debug_*, which carry odd-offset fixups mkprg would choke on);
# keep .rela.text/.rela.data, the R_68K_32 fixups the GEMDOS relocation table is built from.
m68k-elf-strip --strip-debug "$BUILD/joust.elf"

echo ">> objcopy -> flat binary"
m68k-elf-objcopy -O binary "$BUILD/joust.elf" "$BUILD/joust.bin"

echo ">> wrap -> GEMDOS .PRG"
python3 "$HERE/mkprg.py" "$BUILD/joust.elf" "$BUILD/joust.bin" "$BUILD/$PRG"

cp "$BUILD/$PRG" "$DISK/$PRG"
ls -l "$DISK/$PRG" "$DISK/JOUST.IMG"
