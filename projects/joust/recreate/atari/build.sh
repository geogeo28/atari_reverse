#!/bin/bash
# Build JOUST.PRG from the verified reconstruction with the m68k-elf cross toolchain, and stage a
# drive for Hatari.
#
#   build.sh              -> playable build (real console + real joysticks)
#   build.sh title        -> dump the title screen and terminate
#   build.sh smoke [N]    -> type '1', run N frames, dump two of them and the stats
#   build.sh quit         -> type '1', play, then Ctrl-C: the reconstruction's quit path, for real
#   build.sh quittitle    -> Ctrl-C on the title screen instead
#   build.sh restart      -> type '1', play, R (restart), then Ctrl-C from the new title screen
#   build.sh framediff    -> pinned run for the frame-by-frame differential against the shipped binary
#
# Each writes disk/JOUST.PRG *and* keeps build/JOUST-<mode>.PRG, so a check that needs two builds in
# sequence (smoke.py hiscore) can have them without rebuilding.
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
EARLY_FRAME=2                    # the second gameplay frame is dumped too, to witness animation

# The scripted console (joust_main.c): SMOKE_SCRIPT_KEYS is the sequence of ASCII bytes to type and
# SMOKE_SCRIPT_WAIT how many console polls to wait for each after the previous was taken. On the
# title screen a pass polls ~400 times, so a small wait lands on the first pass; during play
# poll_quit_key is exactly one poll per frame, so a wait THERE is a frame count.
# The keys are passed as the C MACRO NAMES joust_main.c watches for, never as bytes: a second
# spelling here could drift from the shim's watcher and the only symptom would be a run that plays
# on to the --run-vbls limit and reports a missing STATS.BIN.
KEY_ONE_PLAYER=KEY_ONE_PLAYER    # '1' — starts a one-player game
KEY_QUIT=KEY_CTRL_C              # quits to the desktop
KEY_RESTART=KEY_RESTART_UPPER    # 'R' — restarts the game
TITLE_POLLS=8                    # polls to leave for a real key before typing one on the title
PLAY_FRAMES=60                   # ...and frames of play before the next scripted key

# The frame differential's two pins and its sample depths. RNG_PARK is a GHIDRA address inside the
# 6906-byte relocation-free stretch at 0x1551a — the only kind of place where this build's image and
# the shipped binary's memory hold the same bytes (joust_main.c explains why that matters).
RNG_PARK=0x1551a
# EVERY sample depth has a MOVING neighbour — frame N differs from N+1 — which is what lets the
# mis-anchor control below fail on all six. Measured deltas to N+1: 113, 25, 227, 281, 282, 287.
# They are not evenly spread on purpose: with the sticks centred the screen is static from about
# frame 2 to frame 110 (the rider settles, then nothing moves until the first enemy is on the
# board), so evenly spaced depths would mostly have sampled the same painted frame.
FRAME_SAMPLES=1,115,150,180,210,240
FRAMEDIFF_LAST=241

MODE="${1:-play}"
case "$MODE" in
  title)     DEF="-DSMOKE -DSMOKE_TITLE" ;;
  smoke)     DEF="-DSMOKE -DSMOKE_FRAMES=${2:-$SMOKE_FRAMES_DEFAULT} -DSMOKE_EARLY_FRAME=$EARLY_FRAME \
                  -DSMOKE_SCRIPT_KEYS=$KEY_ONE_PLAYER -DSMOKE_SCRIPT_WAIT=$TITLE_POLLS" ;;
  quit)      DEF="-DSMOKE -DSMOKE_SCRIPT_KEYS=$KEY_ONE_PLAYER,$KEY_QUIT \
                  -DSMOKE_SCRIPT_WAIT=$TITLE_POLLS,$PLAY_FRAMES" ;;
  quittitle) DEF="-DSMOKE -DSMOKE_SCRIPT_KEYS=$KEY_QUIT -DSMOKE_SCRIPT_WAIT=$TITLE_POLLS" ;;
  restart)   DEF="-DSMOKE -DSMOKE_SCRIPT_KEYS=$KEY_ONE_PLAYER,$KEY_RESTART,$KEY_QUIT \
                  -DSMOKE_SCRIPT_WAIT=$TITLE_POLLS,$PLAY_FRAMES,$TITLE_POLLS" ;;
  # The frame differential (smoke.py framediff). The key is typed on the FIRST console poll so the
  # game starts after exactly one attract pass, as it does on the shipped side when the debugger
  # forces its Bconstat; the RNG cursor is parked where both programs' bytes are identical; and one
  # run dumps every sampled frame. See joust_main.c's "frame differential" section for the physics.
  framediff) DEF="-DSMOKE -DSMOKE_SCRIPT_KEYS=$KEY_ONE_PLAYER -DSMOKE_SCRIPT_WAIT=1 \
                  -DSMOKE_RNG_PTR=$RNG_PARK -DSMOKE_FRAME_DUMPS=$FRAME_SAMPLES \
                  -DSMOKE_FRAMES=$FRAMEDIFF_LAST" ;;
  play)      DEF="" ;;
  *) echo "usage: build.sh [title | smoke [frames] | quit | quittitle | restart | framediff]"; exit 2 ;;
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

# The jmp_buf's length is one value in two languages that cannot import each other, so it is pinned
# here rather than left to a comment: setjmp writes JB_LONGS longwords into a buffer the C declares
# as SHIM_JMP_BUF_LONGS, and a mismatch would scribble past a BSS array on the restart path only.
JB_ASM=$(sed -n 's/.*JB_LONGS *= *\([0-9]*\).*/\1/p' "$HERE/joust_os.s")
JB_C=$(sed -n 's/^#define SHIM_JMP_BUF_LONGS *\([0-9]*\).*/\1/p' "$HERE/shim_include/tos.h")
[ -n "$JB_ASM" ] && [ "$JB_ASM" = "$JB_C" ] || {
  echo "ERROR: jmp_buf length disagrees — joust_os.s JB_LONGS=$JB_ASM, tos.h SHIM_JMP_BUF_LONGS=$JB_C"
  exit 1; }

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
cp "$BUILD/$PRG" "$BUILD/JOUST-$MODE.PRG"
ls -l "$DISK/$PRG" "$DISK/JOUST.IMG"
