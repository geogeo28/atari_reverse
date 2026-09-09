#!/bin/bash
# build.sh — link the verified cores and the shim into BUBBLE.PRG, and refuse the builds that would
# be wrong in ways nothing downstream could see.
#
#   bash atari/build.sh [title | titlefault | titlepoke | titleisr | play] [gemdos | floppy]
#
# THE CORES ARE NOT EDITED AND THAT IS MEASURED, not asserted, and the measurement has two halves.
#
#   WHAT THE CORES SAY — `git` is asked. A core changed in the working tree, or one git does not
#   track at all, is REFUSED: every gate below this one measures ISOLATION and would pass over an
#   edited core, and the .PRG would then be a build of a program the differential never ran, which
#   is the one claim this directory makes that matters.
#   WHAT REACHES THE CORES — five gates: no core includes a shim-only header, no core reads a
#   target-only `-D`, no shim symbol collides with one a core defines, every kit `os_*` helper a core
#   calls is one this build replaces, and every `hw_*` door a core calls is one this build defines
#   (at the number of call sites the record's prediction is built on).
#
# The seam is the INCLUDE PATH plus one omitted directory (the kit's own `src/`), exactly as in
# projects/zynaps/recreate/atari/build.sh, whose gates this file's are modelled on.
#
# WHAT THE MODES ARE. `title` boots to the drawn menu and stops at an anchor a headless check can
# photograph; `titlefault`, `titlepoke` and `titleisr` are that build with one injected fault each
# (see below); `play` composes the whole program — the menu's own blocking key reads, the room loop,
# the endings — and runs until the window is closed. The mode is a `-D`, so the .PRG a check judges
# is the .PRG it ran.
set -euo pipefail

MODE="${1:-title}"
MEDIUM="${2:-gemdos}"
case "$MEDIUM" in
  gemdos|floppy) ;;
  *) echo "usage: build.sh [title | titlefault | titlepoke | titleisr | play] [gemdos | floppy]"
     exit 2 ;;
esac
# THE THREE NEGATIVE CONTROLS, one fault each, each aimed at a different surface. They are
# build-time `-D`s and not runtime flags, because a check judges the binary it ran; each publishes
# its own argument in STATE.BIN, so `smoke.py` refuses to grade a control mode against a .PRG that
# carries no fault.
#
# FAULT_PEN IS THE HARDWARE PEN, NOT THE VDI COLOUR INDEX, and the difference cost a control that
# passed vacuously: the menu text is drawn with `vst_color(handle, 1)`, and the VDI's colour 1 is
# WHITE, which in ST low resolution is hardware register 15. Faulting register 1 moved the chip's
# state and left the rendered picture identical, because no pixel on the menu screen uses it.
# `smoke.py` asserts the faulted pen is one the picture actually draws, so the arm cannot go back to
# being vacuous quietly.
#
# FAULT_IMAGE_WORD IS THE FIRST WORD OF THE FIRST MENU LINE — "Press [G] .......to play the Game",
# `A_text_menu_game` in ../include/frontend.h. It is the RUN-TIME address, because the shim pokes it
# after the crt0 has moved the DATA segment there. XORing it moves two glyphs on the screen and
# nothing else at all, which is what separates the MEMORY surface (the framebuffer against the
# original's) from the chip's own state.
FAULT_PEN=15
FAULT_IMAGE_WORD=0x24ff8
case "$MODE" in
  title)      DEF="-DBG_MODE=0" ;;
  titlefault) DEF="-DBG_MODE=0 -DBG_FAULT_PEN=$FAULT_PEN" ;;
  titlepoke)  DEF="-DBG_MODE=0 -DBG_FAULT_IMAGE_WORD=$FAULT_IMAGE_WORD" ;;
  titleisr)   DEF="-DBG_MODE=0 -DBG_FAULT_NO_TIMER_C=1" ;;
  play)       DEF="-DBG_MODE=1" ;;
  *) echo "usage: build.sh [title | titlefault | titlepoke | titleisr | play] [gemdos | floppy]"
     exit 2 ;;
esac

# ---- the machine the checks are judged at, and the budget the .PRG must fit ---------------------
# ONE DEFINITION, READ ACROSS THE LANGUAGE BOUNDARY (CLAUDE.md §5). Zynaps puts these in smoke.py
# and has build.sh scrape them; this tree runs the other way round, because the size gate below is
# the FIRST consumer and a build that cannot be run at all should not depend on the checker existing.
# `smoke.py` scrapes these three and PINS the TPA figure on every 1 MB run, so the number stays a
# measurement rather than becoming a policy.
MEMSIZE_MB=1
TPA_1MB_BYTES=940898      # MEASURED, on this program's own GEMDOS-drive run: STATE.BIN's
                          # TPA_HIGH - TPA_LOW at 1 MB, which is 1 MiB less TOS's 32 KiB screen and
                          # 74,902 B of low RAM, GEMDOS buffers and the basepage. `smoke.py` pins it
                          # against what the program measures on every 1 MB run, so it cannot drift
                          # into being a policy — the first draft carried Zynaps' figure and was 8 B
                          # out, which is exactly how that check earns its place.
STACK_RESERVE_BYTES=32768 # a reserve, not a measurement: what the C stack and TOS may still want

HERE="$(cd "$(dirname "$0")" && pwd)"
REC="$(cd "$HERE/.." && pwd)"                             # recreate/
TOOLS="$(cd "$REC/../../../tools" && pwd)"                # the workspace's game-agnostic tooling
KIT="$TOOLS/recreate_kit"                                 # the shared harness
BIN="$REC/../bin"                                         # projects/bubbleghost/bin
BUILD="$HERE/build"; DISK="$HERE/disk"
PRG="BUBBLE.PRG"
mkdir -p "$BUILD" "$DISK"
rm -f "$BUILD/BUBBLE-$MODE.PRG" "$BUILD/$PRG"
CC=m68k-elf-gcc
PY="$REC/.venv/bin/python"; [ -x "$PY" ] || PY=python3

# ---- stage the drive ----------------------------------------------------------------------------
# THE SIX DATA FILES GO ON A: AND NOTHING ELSE DOES. The program opens them by their own hard-coded
# names — "A:GHOST.DAT" and its five siblings, in the DATA segment and (for GHOST.LOA/VOI) built one
# byte at a time by `init_globals` — so the drive letter is the ORIGINAL'S, not a build-time choice,
# and this build does not patch it. `smoke.py` therefore mounts a floppy in A: even for its GEMDOS
# run; the .PRG and the files the run writes back live on C:, which is `disk/c`. The two volumes
# are separate directories because Hatari reads a subdirectory named C or D inside a GEMDOS drive as
# a PARTITION, so the A: staging cannot live under the drive it is not.
# ...EXCEPT THAT TWO OF THE SIX ARE NOT PREFIXED, which the trap ledger of the first run found and
# no reading of the source would have: `A_name_ghost_loa` and `A_name_ghost_voi` are the two names
# `init_globals` builds one byte at a time in the BSS, and they are "GHOST.LOA" and "GHOST.VOI" with
# NO DRIVE. So those two open on the CURRENT drive, which is A: on the original's floppy and C:
# under a GEMDOS run — and a GEMDOS run without them on C: gets Fopen's -33, reads the speech player
# into a buffer of zeros, and `jsr`s into it. That is a bus error at a garbage PC with nothing
# upstream of it wrong, which is exactly what the first run did.
echo ">> stage the drive"
PREFIXED_FILES="GHOST.DAT GHOST.DEM GHOST.PRE"   # opened as "A:GHOST.xxx" — the A: volume only
CURRENT_DRIVE_FILES="GHOST.LOA GHOST.VOI"        # opened by bare name — wherever the program runs
rm -f "$DISK/c"/*.BIN
mkdir -p "$DISK/a" "$DISK/c"
for file in $PREFIXED_FILES $CURRENT_DRIVE_FILES; do
  [ -f "$BIN/$file" ] || { echo "ERROR: no $BIN/$file — the game opens it by name"; exit 1; }
  cp "$BIN/$file" "$DISK/a/$file"
done
for file in $CURRENT_DRIVE_FILES; do cp "$BIN/$file" "$DISK/c/$file"; done
echo "   $(echo $PREFIXED_FILES $CURRENT_DRIVE_FILES | wc -w | tr -d ' ') data files -> $DISK/a," \
     "$(echo $CURRENT_DRIVE_FILES | wc -w | tr -d ' ') of them also -> $DISK/c (opened unprefixed)"
"$PY" "$HERE/gen_image.py" "$BIN/GHOST_PLAIN.PRG" "$DISK/c/GHOST.IMG"
IMG_BYTES=$(wc -c < "$DISK/c/GHOST.IMG" | tr -d ' ')        # BSD wc pads with spaces
LOAD_BASE=$(sed -n 's/^load_base *= *\(0x[0-9a-fA-F]*\).*/\1/p' "$REC/project.toml")
[ -n "$LOAD_BASE" ] || { echo "ERROR: no load_base in $REC/project.toml"; exit 1; }
DEF="$DEF -DPROGRAM_BYTES=$IMG_BYTES"
# ONE SCRAPER FOR A C `#define`, because FOUR sites in this file want it and a copy each is how they
# drift (wave 4's review found a third hand-written copy of this shape already drifted from
# the other two). The `u` suffix is OPTIONAL, because the kit spells `GEM_VDI 0x73u` and
# `VDI_CONTRL_SRC_MFDB 7` — and THE VALUE IS ANCHORED, because making `u` optional on its own turns
# this scrape from fail-closed to fail-OPEN. With `u` mandatory, `#define VDI_PB_PTSOUT 4 + 1`
# matched nothing and the empty-scrape guards below reddened; optional, it scrapes the leading `4`,
# compares equal to the assembly's 4, and prints a green line over a value that is really 5. So what
# may follow the digits is pinned too: an optional u/U, then end of line or whitespace or a comment.
# `printf '%d'` cannot catch this — a truncated numeric prefix is still a number.
scrape_c_define() {   # <header> <name> -> its value as written, or nothing
  sed -n "s|^#define $2  *\([0-9a-fA-FxX][0-9a-fA-FxX]*\)[uU]\{0,1\}\([ 	]*\(/\*.*\)\{0,1\}\)\{0,1\}\$|\1|p" "$1"
}

# ONE SHAPE FOR THE FIVE COMPARISONS, for `scrape_c_define`'s and `require_once_in_routine`'s
# reason: five copies of "compare, print both, exit" is five places to fix when the format moves.
# A rotted pattern scrapes EMPTY, which is not the expected text either, so every one fails closed.
require_scrape_equals() {   # <expected> <scraped> <headline> <why it matters...>
  local expected=$1 scraped=$2 headline=$3; shift 3
  [ "$scraped" = "$expected" ] && return 0
  echo "ERROR: $headline"
  printf '       %s\n' "$@"
  echo "       expected:"; printf '%s\n' "$expected" | sed 's/^/         /'
  echo "       scraped:";  printf '%s\n' "$scraped"  | sed 's/^/         /'
  exit 1
}

GLOBALS_LOAD_BASE=$(scrape_c_define "$REC/include/globals.h" BG_LOAD_BASE)
[ -n "$GLOBALS_LOAD_BASE" ] || { echo "ERROR: no BG_LOAD_BASE in $REC/include/globals.h"; exit 1; }
[ "$((GLOBALS_LOAD_BASE))" = "$((LOAD_BASE))" ] || {
  echo "ERROR: project.toml's load_base ($LOAD_BASE) and include/globals.h's BG_LOAD_BASE"
  echo "       ($GLOBALS_LOAD_BASE) disagree, so the staged image and the cores' A_* addresses are"
  echo "       against different bases and every global would be read from the wrong place."
  exit 1; }

# ---- the stack reserve is ONE number in two languages -------------------------------------------
# `bubble_os.s`'s `Mshrink` keeps this much above the program for the C stack, and the size gate
# below subtracts the same figure from the TPA. CLAUDE.md §5: pin them equal rather than duplicating.
OS_RESERVE=$(sed -n 's/^ *STACK_RESERVE *= *\([0-9][0-9]*\).*/\1/p' "$HERE/bubble_os.s")
[ -n "$OS_RESERVE" ] || { echo "ERROR: no STACK_RESERVE in $HERE/bubble_os.s"; exit 1; }
[ "$OS_RESERVE" = "$STACK_RESERVE_BYTES" ] || {
  echo "ERROR: bubble_os.s keeps $OS_RESERVE B above the program and this file's size gate weighs"
  echo "       against $STACK_RESERVE_BYTES B. The .PRG would be judged against a budget it does"
  echo "       not have."; exit 1; }

# ---- the supervisor gate's three operations are ONE set of numbers in two languages -------------
# `bubble_os.s`'s handler dispatches on them and `shim_include/tos.h`'s callers pass them; a
# disagreement about which operation is 2 would store a PSG register number to an address.
for GATE in PSG_WRITE PSG_READ STORE8; do
  FROM_H=$(scrape_c_define "$HERE/shim_include/tos.h" "BG_GATE_$GATE")
  FROM_S=$(sed -n "s/^ *GATE_$GATE *= *\([0-9]*\).*/\1/p" "$HERE/bubble_os.s")
  [ -n "$FROM_H" ] && [ -n "$FROM_S" ] || {
    echo "ERROR: the gate operation BG_GATE_$GATE is missing from tos.h ('$FROM_H') or bubble_os.s"
    echo "       ('$FROM_S') — the scrape has stopped matching one of them, and a clean report from"
    echo "       it would mean nothing"; exit 1; }
  [ "$FROM_H" = "$FROM_S" ] || {
    echo "ERROR: BG_GATE_$GATE is $FROM_H in shim_include/tos.h and $FROM_S in bubble_os.s"; exit 1; }
done
echo ">> the supervisor gate's 3 operations agree between tos.h and bubble_os.s"

# ---- ...and the NUMBERS bubble_os.s shares with a C header are ONE set of numbers ---------------
# Fifteen entries, each `<asm name>:<C name>:<C file>`. The two PSG ports: bubble_os.s's trapped
# door (`bg_super_gate_entry`) and `../src/asm/sound_tick.S`'s five bare store pairs address the
# same chip from the two sides of the seam, and `shim_include/psg.h` is where the pair is spelt
# once — so a disagreement writes a sound register to whatever else lives at the address. This loop
# holds the trapped door to that header; `test/test_constants.py` holds the twin's `.equ`s to the
# same header, which is the half that reaches the chip 200 times a second. (`PSG_REG_MASK` is
# deliberately NOT here: only the trapped door masks, for the reason psg.h's header gives. **AND
# THERE IS NO LONGER A C UNTRAPPED DOOR TO PIN** — wave 7a deleted `psg_untrapped_write` and the
# `bg_in_timer_c` test that selected it, an arm nothing had set since wave 5b.)
#
# $484 IS NO LONGER ONE OF THEM, AND THAT IS ONE SPELLING FEWER RATHER THAN ONE PIN FEWER. The 200 Hz
# tick's `$484` mirror moved into `../src/asm/sound_tick.S` with the vector itself (wave 6a), where
# the store's operand IS that file's `TOS_CONTERM` equate — the same name the verified core header
# spells, held equal to it by test/test_constants.py over the assembled object. What this build adds
# on top is the conterm-mirror gate after the link, which builds its search pattern out of
# `../include/sound.h`'s own value: the two languages are compared there, against the instruction
# that ships, rather than against a second `= 0x484` nobody executes.
#
# AND THE THIRTEEN THE GEM DOOR IS BUILT OUT OF. `bg_gem_dispatch` is hand-written 68000 (wave 5a), so
# the selector it puts in `d0`, the `contrl` slots it patches, the opcode it dispatches on, the
# MFDB field it walks and the length of each parameter block are all IMMEDIATES in assembly where
# they used to be macros the compiler resolved. Every one of them is scraped back out of the header
# that owns it — the kit's `os.h` for the GEM layout, the cores' `frontend.h` for the game's own
# `contrl` address — so a slot index that moves reds the build instead of making the door patch the
# wrong two words. The two `_PB_` entries are the LAST index of each block, and the door derives
# each block's length as one more than it. `VDI_PB_PTSIN` is there because the door's cached tail
# restates that ONE slot by displacement, so an index that moved would restate the wrong pointer
# and leave the VDI reading its coordinates out of whichever array the game last put beside it.
# `A_VDI_PBLOCK` is there because `bg_gem_cache_vdi_pblock` reads the block DIRECTLY rather than
# being handed it, which is the one place in this file that names the game's block itself.
#
SHARED_NUMBERS=0
for PORT in PSG_SELECT:BG_PSG_SELECT:"$HERE/shim_include/psg.h" \
            PSG_DATA:BG_PSG_DATA_OFFSET:"$HERE/shim_include/psg.h" \
            GEM_VDI:GEM_VDI:"$KIT/include/os.h" \
            GEM_AES:GEM_AES:"$KIT/include/os.h" \
            VDI_VRO_CPYFM:VDI_VRO_CPYFM:"$KIT/include/os.h" \
            VDI_CONTRL_OPCODE:VDI_CONTRL_OPCODE:"$KIT/include/os.h" \
            VDI_CONTRL_SRC_MFDB:VDI_CONTRL_SRC_MFDB:"$KIT/include/os.h" \
            VDI_CONTRL_DST_MFDB:VDI_CONTRL_DST_MFDB:"$KIT/include/os.h" \
            VDI_PB_PTSIN:VDI_PB_PTSIN:"$KIT/include/os.h" \
            VDI_PB_PTSOUT:VDI_PB_PTSOUT:"$KIT/include/os.h" \
            AES_PB_ADDROUT:AES_PB_ADDROUT:"$KIT/include/os.h" \
            MFDB_ADDR:MFDB_ADDR:"$KIT/include/os.h" \
            MFDB_SCREEN_ADDR:MFDB_SCREEN_ADDR:"$KIT/include/os.h" \
            A_VDI_CONTRL:A_vdi_contrl:"$REC/include/frontend.h" \
            A_VDI_PBLOCK:A_vdi_pblock:"$REC/include/frontend.h"; do
  C_FILE=${PORT##*:}
  C_NAME=${PORT#*:}; C_NAME=${C_NAME%%:*}
  # ...and the SAME anchoring on the assembly side, for the same reason: `MFDB_ADDR = 0 + 8` would
  # otherwise scrape `0`, agree with the header's 0, and leave the door reading the raster pointer
  # from offset 8. The constants block right below these fifteen is written in expression form
  # (`CONTRL_SRC_MFDB_SLOT = VDI_CONTRL_SRC_MFDB * CONTRL_WORD_BYTES`), so that respelling is the
  # natural next edit. A `|` comment is this file's line-end, so it is what may follow the digits.
  # (`@` is the delimiter, because `|` is the pattern's own line-end comment character.)
  FROM_S=$(sed -n "s@^ *${PORT%%:*} *= *\([0-9a-fA-FxX][0-9a-fA-FxX]*\)\([ 	]*\(|.*\)\{0,1\}\)\{0,1\}\$@\1@p" "$HERE/bubble_os.s")
  FROM_H=$(scrape_c_define "$C_FILE" "$C_NAME")
  # An EMPTY scrape is refused first, because `printf '%d' ""` is 0 with exit status 0 on the bash
  # this runs under — two missed patterns would otherwise agree at zero and the gate would print its
  # green line over nothing. Past that, both are normalised to decimal so 0x2 and 2 compare equal,
  # and a printf that REFUSES catches the other rot ("0x" out of a pattern that lost its digits).
  [ -n "$FROM_S" ] && [ -n "$FROM_H" ] || {
    echo "ERROR: ${PORT%%:*} scraped EMPTY from bubble_os.s ('$FROM_S') or $C_NAME from"
    echo "       $C_FILE ('$FROM_H') — the pattern has stopped matching, and a clean"
    echo "       report from it would mean nothing"; exit 1; }
  VALUE_S=$(printf '%d' "$FROM_S" 2>/dev/null) && VALUE_H=$(printf '%d' "$FROM_H" 2>/dev/null) || {
    echo "ERROR: ${PORT%%:*} scraped as '$FROM_S' from bubble_os.s and $C_NAME as '$FROM_H' from"
    echo "       $C_FILE, and at least one is not a number — the pattern is matching only part of"
    echo "       what it should, and a clean report from it would mean nothing"; exit 1; }
  [ "$VALUE_S" = "$VALUE_H" ] || {
    echo "ERROR: the value is $FROM_S in bubble_os.s (${PORT%%:*}) and $FROM_H in $C_FILE"
    echo "       ($C_NAME). The two spellings would reach different bytes of the machine, or"
    echo "       different words of the game's own arrays."
    exit 1; }
  SHARED_NUMBERS=$((SHARED_NUMBERS + 1))
done
# ...and that the untrapped door's BODY is those two macros and nothing else: exactly two volatile
# byte stores, select before data. The equality above pins the numbers; this pins that they are what
# the store reaches, which is the half no other surface has — the differential compiles the kit's
# psg.c and not this header, and STATE.BIN records nothing about the chip. A rotted `sed` scrapes
# THE C SIDE OF THIS PAIR IS A HEADER CONSTANT NOW AND NOT A FUNCTION BODY, which is one gate
# fewer here rather than one pin fewer. Until wave 7a the loop above was backed by a scrape of
# `psg_untrapped_write`'s two volatile stores — the check that they were those two macros, select
# before data, value expression included, so that `(uint8_t)(reg & 15)` could not appear in one of
# them without the argument moving. That door is deleted (nothing had set the flag selecting it
# since wave 5b), so what reaches $ff8800 is the trapped door below and the twin's five transcribed
# pairs, and each is held by its own pin: the `andi.l` check here, and `test/test_sound_asm.py`'s
# transcription of `../src/asm/sound_tick.S`.

# ...and that the TRAPPED door still MASKS, which is the other half of the asymmetry psg.h argues.
# The two doors are meant to disagree here — the original's do, its ISR writing the ports bare and
# only its trap handler carrying `and.b #$f,d1` @ 0x1495c — and the trapped half is watched by
# nothing else: the differential compiles the kit's psg.c and never this door, so deleting the
# `andi.l` would make the two agree silently, in the direction the header spends a page refusing.
PSG_TRAPPED_MASKS=$(grep -c '^ *andi\.l  *#PSG_REG_MASK,%d1$' "$HERE/bubble_os.s" || true)
[ "$PSG_TRAPPED_MASKS" = "1" ] || {
  echo "ERROR: bg_super_gate_entry's 'andi.l #PSG_REG_MASK,%d1' was scraped $PSG_TRAPPED_MASKS times"
  echo "       in bubble_os.s, not once. The TRAPPED door is where this build's register mask lives"
  echo "       (shim_include/psg.h's header argues why the untrapped one has none); losing it makes"
  echo "       the two doors agree where the original's two do not."; exit 1; }
echo ">> bubble_os.s's $SHARED_NUMBERS shared numbers agree with their C headers, and only" \
     "the trapped door masks"

# ---- ...and the TWO C ARGUMENT LAYOUTS bubble_os.s hard-codes, which the loop above cannot see ---
# `bg_gem_dispatch` and `bg_gem_cache_vdi_pblock` are assembly and read their arguments at fixed
# `%sp` offsets (`ARG_MEM = 4`, `ARG_SELECTOR = 8`, `ARG_PBLOCK = 12`, m68k SysV: every scalar in
# its own longword slot, first argument lowest). Those offsets ARE the C prototypes, restated in a
# second language — and unlike the fifteen constants above there is no `#define` to scrape, so each
# prototype's own text is what is pinned. Reorder the parameters, widen one, or add one in front and
# the routine silently reads the wrong slots: for the door `%d1` becomes the selector, every staged
# pointer is translated by 0x73, and the ROM VDI is handed wild addresses inside a `trap #2`; for
# the cache primer `%a0` is built from a garbage base, five wild pointers are staged, and the flag
# is set anyway, so every VDI call for the rest of the run traps on them. Both are hardware-only
# faults (the differential runs neither routine) with no other surface in the tree — the anchor
# check would see the second, but only after the picture had been drawn through it.
for PROTOTYPE in "int bg_gem_dispatch(uint8_t *mem, uint32_t selector, uint32_t pblock);" \
                 "void bg_gem_cache_vdi_pblock(uint8_t *mem);"; do
  NAME=${PROTOTYPE#* }; NAME=${NAME%%(*}
  SCRAPED=$(grep -h "^[a-z].* $NAME(.*);\$" "$HERE"/shim_include/*.h)
  require_scrape_equals "$PROTOTYPE" "$SCRAPED" \
    "$NAME's prototype is not the one bubble_os.s's ARG_* stack offsets are written for." \
    "Change the offsets with it, or change it back."
done

# ...and that the door still BUMPS the three counters with a longword add. `bubble_backend.c` pins
# the C side (`_Static_assert(sizeof bg_vdi_calls == 4)`), which can only see C narrowing the type —
# an `addq.w` in the assembly would increment the high half of the neighbouring counter on this
# big-endian layout and nothing in C could say so. This is the other direction, in the same shape as
# the PSG store-line gate above: the instruction itself, counted.
for COUNTER in bg_vdi_calls bg_aes_calls bg_vdi_raster_copies; do
  BUMPS=$(grep -c "^ *addq\.l  *#1,$COUNTER\$" "$HERE/bubble_os.s" || true)
  [ "$BUMPS" = "1" ] || {
    echo "ERROR: 'addq.l #1,$COUNTER' was scraped $BUMPS times in bubble_os.s, not once. STATE.BIN"
    echo "       publishes this counter and smoke.py pins it; a narrowed or duplicated bump is a"
    echo "       silently wrong record."; exit 1; }
done
echo ">> the 2 C prototypes bubble_os.s reads at fixed %sp offsets match it, and the door's 3" \
     "counters take an addq.l each"

# ---- the trap-register scan ---------------------------------------------------------------------
# docs/on-target-execution.md class 3's register half: the one hardware-only bug class no
# differential in this workspace can see. The count is asserted so a rotted regex reds rather than
# passing vacuously over a file it no longer parses.
TRAP_WRAPPERS=29
echo ">> trap-register scan ($TRAP_WRAPPERS wrappers)"
"$TOOLS/assert_trap_registers.sh" --expect "$TRAP_WRAPPERS" "$HERE/bubble_os.s"

# ---- the VDI parameter block's CONSTANT SLOTS, which the door CACHES ----------------------------
# `bg_gem_cache_vdi_pblock` (bubble_os.s) translates the game's five VDI array pointers ONCE, on the
# line after `init_gem_and_screens` returns, and `bg_gem_dispatch` then restages `ptsin` alone — 130
# cycles of every VDI call (../STATUS.md, wave 7a). That rests on a claim about the CORES, which is
# the one kind of claim the rest of that door is written not to make: once the workstation is open,
# the four slots that are not `ptsin` never change again.
#
# THE CLAIM IS TRUE OF THIS TREE, AND THIS IS WHERE IT STAYS TRUE. Five scrapes over the committed
# cores AND the shim's own C — the shim is in the list because it can call a core slice directly
# (`bubble_main.c` composes the boot out of them), so a workstation reopen written THERE would
# rebind the block with every core-side scrape still green:
#   1. every parameter-block address in the tree is `vdi_pblock_slot`'s, and every one of ITS call
#      sites names a `VDI_PB_*` constant — so the ledger in 3 can see every writer, and a computed
#      index cannot walk round it;
#   2. the door is handed THAT block: the argument of every `os_vdi` call is `A_vdi_pblock`, which
#      is what the cache was taken from;
#   3. the writers of a NON-`ptsin` slot are exactly the ones the door expects, named by their
#      enclosing function: `vdi_call_at`, which files `contrl` on every call, and `v_opnvwk`, which
#      lends the VDI three of its caller's arrays and puts the library's four back — all of it
#      BEFORE the cache is taken;
#   4. ...and what `vdi_call_at` files there is the constant the cache holds. That is the half a
#      (function, slot) pair cannot see, and only the VALUE is pinned, not the whole store line:
#      the accessor around it is the cores' to rename;
#   5. those two writers run when the door thinks they do — `v_opnvwk` is called from
#      `init_gem_and_screens`, and `init_gem_and_screens` from `main_start_game`, which is the call
#      `bubble_main.c` primes the cache on the line after. The `g_*` callers in each expected list
#      are the differential's own entry glue, which no target build reaches.
# A `ptsin` WRITER IS DELIBERATELY NOT PINNED: that slot is restated on every call, so a new one is
# free, and a gate that refused it would refuse the next honest change for nothing. And what no
# scrape of C can reach — one of the four moved at RUN time, by a poke or a path this cannot see —
# is `bubble_main.c`'s anchor check, published as STATE.BIN's `VDI_PBLOCK_CACHE_STATE` and required
# to be 0 by `smoke.py`. Neither surface is the whole of it; the door's header says so too.
#
# EVERY SORT IS `LC_ALL=C`, because the expected lists below are literals in BYTE order: under a
# UTF-8 locale glibc gives `_` no primary weight, `vdi_call_at` and `v_opnvwk` swap, and the gate
# reds on an untouched tree.
PBLOCK_SOURCES=("$REC"/src/*.c "$HERE"/*.c)

# The awk prologue both ledger scrapes share — the enclosing function of a line, and comment lines
# skipped. Shared because a second copy of it is how the two would drift, and the COMMENT RULE IS
# FIRST so a block-comment line that happens to look like a function header cannot set `fn`; `fn`
# is reset per FILE so a match before a file's first header is never blamed on the previous file's
# last routine.
AWK_ENCLOSING_FUNCTION='
  FNR == 1 { fn = "<file scope>" }
  /^[ \t]*[*\/]/ { next }
  /^[A-Za-z_][A-Za-z0-9_ *]*[A-Za-z0-9_*]\(/ {
      head = $0; sub(/\(.*/, "", head); n = split(head, part, /[ \t*]+/); fn = part[n] }'

# 1. the spelling: the block is addressed through `vdi_pblock_slot`, and only by a named slot
PBLOCK_NAMERS=$(awk "$AWK_ENCLOSING_FUNCTION"'
  /A_vdi_pblock/ { print fn }' "${PBLOCK_SOURCES[@]}" | LC_ALL=C sort -u)
require_scrape_equals 'vdi_call_at
vdi_pblock_cache_state
vdi_pblock_slot' "$PBLOCK_NAMERS" \
  "A_vdi_pblock is named in a routine this build does not know." \
  "The GEM door caches four of that block's five slots, so EVERY writer has to be visible to the" \
  "ledger below — which means every slot address goes through vdi_pblock_slot(). The block itself" \
  "is named only to define that helper, to hand the door its argument, and to re-read the four" \
  "cached slots back at the anchor."
SLOT_CALLS=$(grep -h "vdi_pblock_slot(" "${PBLOCK_SOURCES[@]}" | grep -cv "vdi_pblock_slot(unsigned" || true)
SLOT_CALLS_NAMED=$(grep -hc "vdi_pblock_slot(VDI_PB_" "${PBLOCK_SOURCES[@]}" | paste -sd+ - | bc)
require_scrape_equals "$SLOT_CALLS" "$SLOT_CALLS_NAMED" \
  "a vdi_pblock_slot() call site does not name a VDI_PB_* slot." \
  "The ledger below reads slots by that spelling, so an index computed at run time — a loop, a" \
  "wrapper, a variable — would be a writer it cannot see, which is exactly the class the door" \
  "cannot survive. (counts are call sites total vs call sites naming a VDI_PB_* constant)"

# 2. ...and the door is handed that block and no other
OS_VDI_ARGUMENTS=$(grep -h "os_vdi(" "${PBLOCK_SOURCES[@]}" | grep -v "^[[:space:]]*[*/]" \
                   | sed 's/.*os_vdi([^,]*, *//; s/).*//' | LC_ALL=C sort -u)
require_scrape_equals 'A_vdi_pblock' "$OS_VDI_ARGUMENTS" \
  "an os_vdi() call passes a parameter block other than the one the cache was taken from." \
  "bg_gem_cache_vdi_pblock stages A_vdi_pblock's five pointers; the door then trusts four of its" \
  "own staged slots for whatever block it is handed."

# 3. the ledger: who writes a slot that is NOT ptsin, by enclosing function. EVERY occurrence on a
#    line is read, not the last one: a line naming two slots would otherwise report only the second,
#    and one whose second is `ptsin` would take the whole line out of the ledger — fail-open, in the
#    one gate whose comment promises the opposite.
PBLOCK_WRITERS=$(awk "$AWK_ENCLOSING_FUNCTION"'
  {
      rest = $0
      while (match(rest, /vdi_pblock_slot\(VDI_PB_[A-Z]+\)/)) {
          slot = substr(rest, RSTART, RLENGTH)
          rest = substr(rest, RSTART + RLENGTH)
          sub(/^vdi_pblock_slot\(VDI_PB_/, "", slot); sub(/\)$/, "", slot)
          if (slot != "PTSIN") print fn "|" slot
      }
  }' "${PBLOCK_SOURCES[@]}" | LC_ALL=C sort)
require_scrape_equals 'v_opnvwk|INTIN
v_opnvwk|INTIN
v_opnvwk|INTOUT
v_opnvwk|INTOUT
v_opnvwk|PTSOUT
v_opnvwk|PTSOUT
vdi_call_at|CONTRL' "$PBLOCK_WRITERS" \
  "a core writes a VDI parameter-block slot the GEM door's cache does not expect." \
  "The door translates contrl/intin/intout/ptsout ONCE, after init_gem_and_screens, and restates" \
  "only ptsin per call — so a writer of one of those four outside v_opnvwk leaves TOS reading the" \
  "game's arrays through a stale pointer, on a path no differential runs." \
  "Either move the writer, or take the cache out of bubble_os.s with it." \
  "(the list is <enclosing function>|<slot>, sorted)"

# 4. ...and the one PER-CALL writer files the constant the cache holds
CONTRL_VALUE=$(grep -h "vdi_pblock_slot(VDI_PB_CONTRL)" "${PBLOCK_SOURCES[@]}" \
               | sed 's/.*vdi_pblock_slot(VDI_PB_CONTRL))*, *//; s/ *);.*//' | LC_ALL=C sort -u)
require_scrape_equals 'A_vdi_contrl' "$CONTRL_VALUE" \
  "the per-call contrl store does not file the array the door's cache holds." \
  "vdi_call_at runs on EVERY VDI call, so what it stores IS what the cache must have translated." \
  "Only the value is pinned here; the accessor around it is the cores' to rename."

# 5. ...and the two writers run before the cache is taken, which is their CALLERS
for CHAIN in v_opnvwk:'g_v_opnvwk
init_gem_and_screens' init_gem_and_screens:'g_init_gem_and_screens
main_start_game'; do
  CALLEE=${CHAIN%%:*}
  CALLERS=$(awk "$AWK_ENCLOSING_FUNCTION"'
    $0 ~ callee "\\(" { if (fn != callee) print fn }' callee="$CALLEE" "${PBLOCK_SOURCES[@]}" \
            | LC_ALL=C sort -u)
  require_scrape_equals "${CHAIN#*:}" "$CALLERS" \
    "$CALLEE is called from somewhere the GEM door's cache does not account for." \
    "It may only run BEFORE bubble_main.c primes the cache — which is the line after" \
    "main_start_game — because it rebinds slots the door then stops restating."
done
echo ">> the VDI parameter block's 4 cached slots have the writers and the callers the door expects"

# ---- the cores are the tree's COMMITTED cores ---------------------------------------------------
# The isolation gates further down measure what reaches the cores. NONE of them looks at what the
# cores SAY, so an edited `../src/blit.c` would pass all of them and the .PRG would be a build of a
# program the differential never verified. `git` is the comparison: a tracked file that differs from
# its committed content, or a `.c`/`.h` git does not track at all, refuses the build. There is no
# flag to skip it — the way past it is a commit, which is also the thing that makes the claim true.
echo ">> the cores are the tree's committed cores"
git -C "$REC" diff --quiet HEAD -- src include || {
  echo "ERROR: ../src or ../include differs from its committed content. This build's whole claim is"
  echo "       that it compiles the cores the differential verified, so a dirty core is a different"
  echo "       program with the same name. Commit (or revert) these first:"
  git -C "$REC" diff --stat HEAD -- src include | sed 's/^/         /'
  exit 1; }
# ...OVER `src/asm/*.S` TOO, which is not decoration: an asm twin is a shipping core (it is linked
# below, and it is what the 200 Hz vector reaches), and an UNTRACKED one would be assembled, linked
# and certified by this gate's own green line. The tracked half above already covers a `.S` once it
# is committed; this is the half that was open. Measured 2026-09-08: with only the two C globs,
# `ls-files --others` returned nothing while `src/asm/sound_tick.S` sat untracked in the tree.
CORE_GLOBS=("src/*.c" "include/*.h" "src/asm/*.S")
UNTRACKED_CORES=$(git -C "$REC" ls-files --others --exclude-standard -- "${CORE_GLOBS[@]}")
[ -z "$UNTRACKED_CORES" ] || {
  echo "ERROR: ../src or ../include holds source git does not track, and \`git diff\` is silent about"
  echo "       untracked files — so the gate above would have passed over it. Commit or remove:"
  echo "$UNTRACKED_CORES" | sed 's/^/         /'; exit 1; }
CORE_FILE_COUNT=$(git -C "$REC" ls-files -- "${CORE_GLOBS[@]}" | wc -l | tr -d ' ')
[ "$CORE_FILE_COUNT" -gt 0 ] || {
  echo "ERROR: git tracks no ../src/*.c or ../include/*.h at all — the scrape is broken and a clean"
  echo "       report from this gate would mean nothing"; exit 1; }
echo "   $CORE_FILE_COUNT tracked core file(s), none modified, none untracked"

# ---- compile ------------------------------------------------------------------------------------
# `-fno-tree-loop-distribute-patterns` is what stops GCC turning bubble_backend.c's memcpy and
# memset into calls to themselves. `-DOS_NO_REFUSAL_TALLY` selects the kit's own inline `os_refused`,
# which is the identity — the cores' sentinel paths still work and nothing links the tally.
CFLAGS="-m68000 -O2 -fno-tree-loop-distribute-patterns -ffreestanding -fno-jump-tables \
        -fomit-frame-pointer -nostdlib -DOS_NO_REFUSAL_TALLY \
        -I$HERE/shim_include -I$REC/include -I$KIT/include -Wall -Wextra"
CORES="$(ls "$REC"/src/*.c)"
[ -n "$CORES" ] || { echo "ERROR: no cores found in $REC/src"; exit 1; }
SHIM_SOURCES="$HERE/bubble_os.s $HERE/bubble_main.c $HERE/bubble_backend.c"
# ---- ...and the ASM TWINS, which are cores too --------------------------------------------------
# `../src/asm/*.S` are hand-written m68k TRANSCRIPTIONS of the original binary's own instruction
# stream, each carrying the C signature of the verified core it substitutes for here. They are built
# from the SAME source the differential runs — `test/test_sound_asm.py` assembles them through
# kit.mk and compares each against its C core over the whole image and the PSG ledger — so what
# ships is instruction-for-instruction what was verified. Each `.S`'s own header says what it
# transcribes, what it does NOT, and which pin holds which half.
ASM_CORES="$(ls "$REC"/src/asm/*.S 2>/dev/null || true)"
[ -n "$ASM_CORES" ] || { echo "ERROR: no asm twins found in $REC/src/asm"; exit 1; }

OBJ="$BUILD/obj"
rm -rf "$OBJ"; mkdir -p "$OBJ"
echo ">> compile (base 0, keep relocs)"
SHIM_OBJECTS=""; CORE_OBJECTS=""
for source in $SHIM_SOURCES; do
  object="$OBJ/shim_$(basename "${source%.*}").o"
  $CC $CFLAGS $DEF -c "$source" -o "$object"
  SHIM_OBJECTS="$SHIM_OBJECTS $object"
done
for source in $CORES; do
  object="$OBJ/core_$(basename "${source%.c}").o"
  $CC $CFLAGS $DEF -c "$source" -o "$object"
  CORE_OBJECTS="$CORE_OBJECTS $object"
done
# A LOOP OF ITS OWN, and the reason is the object PREFIX rather than the flags: they are the C
# loop's flags exactly. `asm_` keeps a future `foo.c` and `foo.S` from writing the same object.
# (What kit.mk adds for the off-target assembly of these same files — `-DRECREATE_HOST_DIFFERENTIAL`
# and the door macros — is not subtracted here, because this build never had it; the two builds are
# held to the same bytes by the span check after the link rather than by their flag lists.)
for source in $ASM_CORES; do
  object="$OBJ/asm_$(basename "${source%.S}").o"
  $CC $CFLAGS $DEF -c "$source" -o "$object"
  CORE_OBJECTS="$CORE_OBJECTS $object"
done

# ---- the C sound tick is ONE symbol, because atari/profile.py measures it as one -----------------
# `SOUND_TICK_SYMBOLS` sums the profiler's per-ADDRESS rows over a range [symbol, the next symbol
# above it), and `../src/sound.c`'s `timer_c_sound_isr` is one of the ranges it sums on OUR side —
# not because the interrupt runs it (since wave 5b it runs the asm twin, and since wave 6a the
# vector IS the twin) but because it is still LINKED, and a build that somehow reached it again must
# show the cycles rather than hide them. For that reading to mean "the C core cost nothing" it has to
# cover the WHOLE C core: every helper the handler runs is `static` and GCC inlines all of them, so
# the range IS the handler. profile.py refuses a name that VANISHES from the map and cannot see one
# that APPEARS — a helper that stopped being inlined would take its own cycles out of the sum AND cut
# the core's range short at itself, so the row would read low twice over with nothing red.
# `static inline` is a hint; this is the assertion. (A third name stood in this list until wave 7a:
# `psg_untrapped_write`, which inlined into the same C core and would have cut its range short at
# itself just as the two step routines would. It is deleted with the `bg_in_timer_c` arm that
# selected it, so there is nothing left to keep inlined — a user-mode chip write is one `jsr` into
# the trap gate now, and the tick runs no C at all.)
# NOT `nm | grep -q`: this file runs under `set -o pipefail`, `grep -q` closes the pipe on its FIRST
# match, and the SIGPIPE that kills `nm` then makes the pipeline's status 141 — so the one case the
# gate exists to catch is the one case the `&&` does not fire on. Measured here, with the symbol
# present and the gate green (2026-09-07). `grep -c` reads the whole stream instead.
MUST_STAY_INLINED="step_swept_envelope step_triangle_lfo"
OBJECT_TEXT_SYMBOLS=$(m68k-elf-nm $CORE_OBJECTS $SHIM_OBJECTS | awk '$2 == "t" || $2 == "T" {print $3}')
for NAME in $MUST_STAY_INLINED; do
  OUT_OF_LINE=$(printf '%s\n' "$OBJECT_TEXT_SYMBOLS" | grep -c "^$NAME\$" || true)
  [ "$OUT_OF_LINE" = "0" ] || {
    echo "ERROR: $NAME has an out-of-line body in this build ($OUT_OF_LINE object(s)). It is one of"
    echo "       the routines atari/profile.py's sound-tick ranges assume is inlined into"
    echo "       timer_c_sound_isr, so that row would now be measured over less code than it holds."
    echo "       RESTORE THE INLINING. Adding \$NAME to SOUND_TICK_SYMBOLS is not the fix: its range"
    echo "       would then fold whatever else calls it into the 200 Hz figure."
    exit 1; }
done
# ...and the gate is only worth its line if it can see a symbol at all, so the scrape's own output is
# checked against a name that must always be there.
SCRAPE_CONTROL=$(printf '%s\n' "$OBJECT_TEXT_SYMBOLS" | grep -c "^timer_c_sound_isr$" || true)
[ "$SCRAPE_CONTROL" = "1" ] || {
  echo "ERROR: the inlining gate's nm scrape names timer_c_sound_isr $SCRAPE_CONTROL time(s), not"
  echo "       once — it is reading something other than this build's objects, and a clean report"
  echo "       from it would mean nothing"; exit 1; }
echo ">> the sound tick's helpers are inlined ($(echo $MUST_STAY_INLINED | wc -w | tr -d ' ') names)"

# ---- the duplicate-symbol gate ------------------------------------------------------------------
# The linker does object to a collision, but as `multiple definition of 'x'` in the middle of a
# ten-file link line, saying nothing about which side is meant to own the name. This says it.
defined_globals() { m68k-elf-nm -g --defined-only $1 | awk 'NF == 3 {print $3}' | sort -u; }
GATE_CONTROL=$(comm -12 <(printf 'core_only\nshared_name\n') <(printf 'shared_name\nshim_only\n'))
[ "$GATE_CONTROL" = "shared_name" ] || {
  echo "ERROR: the duplicate-symbol gate named '$GATE_CONTROL' on a known collision, not"
  echo "       'shared_name' — it has rotted, and a clean report from it would mean nothing."
  exit 1; }
echo ">> duplicate-symbol gate (the shim may not define what a core defines)"
SHIM_SYMBOLS=$(defined_globals "$SHIM_OBJECTS")
CORE_SYMBOLS=$(defined_globals "$CORE_OBJECTS")
SHIM_COUNT=$(echo "$SHIM_SYMBOLS" | grep -c . || true)
CORE_COUNT=$(echo "$CORE_SYMBOLS" | grep -c . || true)
[ "$SHIM_COUNT" -gt 0 ] && [ "$CORE_COUNT" -gt 0 ] || {
  echo "ERROR: nm named $SHIM_COUNT shim and $CORE_COUNT core symbols — one of them is EMPTY, so the"
  echo "       comparison below would be silent whatever the objects hold."
  exit 1; }
COLLISIONS=$(comm -12 <(echo "$SHIM_SYMBOLS") <(echo "$CORE_SYMBOLS"))
[ -z "$COLLISIONS" ] || {
  echo "ERROR: the shim defines $(echo "$COLLISIONS" | wc -l | tr -d ' ') symbol(s) that ../src now"
  echo "       defines too. The core owns the name; delete the shim's copy:"
  echo "$COLLISIONS" | sed 's/^/         /'
  exit 1; }
echo "   $SHIM_COUNT shim symbols vs $CORE_COUNT core symbols, no name in both"

# ---- the containment gate -----------------------------------------------------------------------
# READ THE INCLUDE CLOSURE, NOT THE `#include` LINES. A shim header a core reaches indirectly is
# still a header that changes what the core compiles to, which is the one thing this seam exists to
# prevent (docs/on-target-execution.md, "Two ways a seam leaks the harness into the shipped
# program"). `tos.h` is in the permitted set because `os.h`, `hw.h` and `psg.h` all pull it in for
# the traps they are made of — it declares nothing but the machine.
echo ">> the cores take nothing from this directory but the kit's own shadowed headers"
CORE_MAY_REACH="hw.h os.h psg.h string.h tos.h"
REACHED=$(for source in $CORES; do $CC $CFLAGS $DEF -MM "$source"; done \
          | tr ' ' '\n' | grep "shim_include/" | sed 's#.*shim_include/##' | sort -u | tr '\n' ' ')
[ -n "$REACHED" ] || {
  echo "ERROR: the cores reach NO header in shim_include/, which cannot be true — three of them"
  echo "       include os.h. \`gcc -MM\`'s output shape has moved under this gate and a clean"
  echo "       report from it would mean nothing."; exit 1; }
[ "$REACHED" = "$CORE_MAY_REACH " ] || {
  echo "ERROR: the cores' include closure reaches a different set of shim headers than the seam"
  echo "       declares. A header here that is not a shadow of a KIT header the cores already"
  echo "       include — or the trap layer those shadows are built on — is the shim leaking into"
  echo "       verified code."
  echo "         may reach: $CORE_MAY_REACH"
  echo "         reaches:   $REACHED"
  exit 1; }
echo "   $REACHED"

TARGET_MACROS='PROGRAM_BYTES|BG_MODE|BG_ANCHOR_HOLD_FRAMES|BG_TARGET_IMAGE_BYTES|BG_FAULT_PEN'
TARGET_MACROS="$TARGET_MACROS|BG_FAULT_IMAGE_WORD|BG_FAULT_NO_TIMER_C"
TARGET_MACROS="$TARGET_MACROS|BG_TARGET_SCREEN_BASE|BG_HEAP_BASE|BG_HEAP_LIMIT"
LEAKS=$(grep -rlE "\b($TARGET_MACROS)\b" "$REC/src" "$REC/include" || true)
[ -z "$LEAKS" ] || { echo "ERROR: a core reads a target-only macro:"; echo "$LEAKS"; exit 1; }
echo "   ...and no core reads a target-only -D"

# ---- every os_* the cores call is one this build replaces ---------------------------------------
# The list is scraped from the SHADOW rather than typed, so a helper this file stops replacing is a
# refused build rather than a core silently running against the deterministic model on real hardware.
echo ">> every kit os_* helper the cores call is replaced by the shadow"
REPLACED=$(grep -oE '^#define os_[a-z_0-9]+ +os_model_' "$HERE/shim_include/os.h" \
           | awk '{print $2}' | sort -u)
# THE EMPTINESS CHECK GOES BEFORE THE APPEND, not after it: `os_refused` is added unconditionally
# below, so a `[ -n ]` on the result of the two together can never fire whatever the scrape found.
[ -n "$REPLACED" ] || { echo "ERROR: the shadow replaces nothing — its #define scrape is broken"; exit 1; }
# `os_refused` is not a `#define ... os_model_` line: `-DOS_NO_REFUSAL_TALLY` selects the kit's own
# inline identity for it, so the cores' sentinel paths work with nothing here to shadow.
REPLACED="$REPLACED
os_refused"
# COMMENTS ARE STRIPPED FIRST, and that is not tidiness: `src/clib.c` names the kit's own
# `src/os_heap.c` in a comment and `os_console_take_key` in another, and a raw grep reads both as
# calls — so the gate refused a build over two names no core actually reaches. Stripping is what
# makes the list a list of CALLS.
CORE_STRIPPED=$($CC $CFLAGS $DEF -fpreprocessed -dD -E $CORES) || {
  echo "ERROR: the core os_* scan could not strip comments, so it saw less than it would report —"
  echo "       fix the strip rather than skipping the scan"; exit 1; }
OS_USED=$(echo "$CORE_STRIPPED" | grep -ohE '\bos_[a-z_0-9]+' | sort -u || true)
[ -n "$OS_USED" ] || { echo "ERROR: the cores name no os_* helper at all — the scrape is broken"; exit 1; }
MODELLED=$(comm -23 <(echo "$OS_USED") <(echo "$REPLACED" | sort -u) || true)
[ -z "$MODELLED" ] || {
  echo "ERROR: a core calls a kit os_* helper this build does NOT replace, so it would run against"
  echo "       the deterministic model on real hardware. Replace it in shim_include/os.h, or say"
  echo "       why the model is right on target:"
  echo "$MODELLED" | sed 's/^/         /'; exit 1; }
echo "   the cores name $(echo "$OS_USED" | wc -l | tr -d ' ') os_* helper(s), all replaced"

# ---- the hardware doors, and how many times the cores go through them ---------------------------
# shim_include/hw.h's header says one door is defined and five are not, and that the cores call the
# one at exactly two sites. Both halves are read off the tree here rather than believed: a core that
# started calling an undefined door would otherwise arrive as a link error naming a symbol and not
# the claim it broke, and a THIRD call site would arrive as STATE.BIN's HW_WRITES quietly counting
# something the smoke's exact prediction was not written for.
echo ">> the hardware doors the cores call are the ones shim_include/hw.h defines"
HW_WRITE_SITES=2      # install_sound_vectors and remove_sound_vectors (../src/sound.c)
HW_DOORS=$(sed -n 's/^static inline .* \(hw_[a-z_0-9]*\)(.*/\1/p' "$HERE/shim_include/hw.h" | sort -u)
[ -n "$HW_DOORS" ] || {
  echo "ERROR: shim_include/hw.h defines no hw_* door — the scrape is broken and a clean report"
  echo "       from this gate would mean nothing"; exit 1; }
HW_USED=$(echo "$CORE_STRIPPED" | grep -ohE '\bhw_[a-z_0-9]+' | sort -u || true)
[ -n "$HW_USED" ] || { echo "ERROR: the cores name no hw_* door at all — the scrape is broken"; exit 1; }
UNDOORED=$(comm -23 <(echo "$HW_USED") <(echo "$HW_DOORS"))
[ -z "$UNDOORED" ] || {
  echo "ERROR: a core calls a hardware door shim_include/hw.h does not define:"
  echo "$UNDOORED" | sed 's/^/         /'; exit 1; }
# `grep -o | wc -l` and not `grep -c`, which counts LINES and would read two calls on one line as
# one — the preprocessed output puts them on separate lines today and nothing keeps it that way.
SITES=$(echo "$CORE_STRIPPED" | grep -oE '\bhw_write8 *\(' | wc -l | tr -d ' ')
[ "$SITES" = "$HW_WRITE_SITES" ] || {
  echo "ERROR: the cores make $SITES hw_write8 call(s) and this build's record predicts"
  echo "       $HW_WRITE_SITES. Re-derive EXPECTED_HW_WRITES in smoke.py before raising this."
  exit 1; }
echo "   $(echo "$HW_DOORS" | tr '\n' ' ')— $SITES call site(s), which is what HW_WRITES predicts"

# ---- link ---------------------------------------------------------------------------------------
echo ">> link"
$CC $CFLAGS -T "$HERE/tos.ld" -Wl,--emit-relocs -Wl,--no-warn-rwx-segments \
    $SHIM_OBJECTS $CORE_OBJECTS -lgcc -o "$BUILD/bubble.elf"
ENTRY=$(m68k-elf-nm "$BUILD/bubble.elf" | awk '$3=="_start"{print $1}')
[ "$ENTRY" = "00000000" ] || { echo "ERROR: _start not at 0 (got $ENTRY)"; exit 1; }

DISASSEMBLY="$BUILD/bubble.dis"
m68k-elf-objdump -d "$BUILD/bubble.elf" > "$DISASSEMBLY"

# ---- the 200 Hz vector IS the asm twin, read back out of the linked binary ----------------------
# THE WHOLE TICK IS ONE ROUTINE NOW. `bg_timer_c_entry` is the head of `../src/asm/sound_tick.S`
# (wave 6a): the machine's $114 vector saves the register set, loads the image base, FALLS THROUGH
# into the 792 transcribed bytes, mirrors $484 out to the machine and `rts`es into TOS's own
# handler. Nothing about that shape is visible to any differential — it is interrupt glue,
# `docs/on-target-execution.md` class 3 — and every way it can fail is silent: calling the C core
# again would boot, play and sound identical at 440 cycles a tick more; losing the mirror would
# leave TOS's key click on with every check in the tree green; a vector that fell out before the
# body would leave the tick doing nothing at all, which is also a clean-looking screenshot for the
# length of a menu.
#
# SO THE ROUTINE ITSELF IS THE SCRAPE, entry label to its ONE `rts` — which is the whole routine
# because the transcribed body contains no `rts` of its own, and is a tighter scope than the
# label-to-next-label form the C door's gates use (this routine HAS interior labels: the twin's two
# span brackets sit inside it).
# ONE SPELLING OF EACH SYMBOL for the checks below and the messages they print, so re-pointing the
# gate at a renamed vector is one edit rather than a dozen.
TICK_VECTOR=bg_timer_c_entry
TICK_BODY=timer_c_sound_isr_body
TICK_BODY_END=${TICK_BODY}_end
TICK_VECTOR_ROUTINE=$(awk -v sym="$TICK_VECTOR" '$0 ~ "^[0-9a-f]+ <" sym ">:" {inside = 1}
                                                 inside {print}
                                                 inside && /[[:space:]]rts$/ {exit}' "$DISASSEMBLY")
[ -n "$TICK_VECTOR_ROUTINE" ] || {
  echo "ERROR: $TICK_VECTOR has no routine in $DISASSEMBLY — the scrape is broken and a clean"
  echo "       report from every check below it would mean nothing"; exit 1; }

# ...AND THE SCRAPE REALLY STOPPED AT THIS ROUTINE'S OWN `rts`, which the `-n` test above cannot
# say: the awk prints to END OF FILE when there is no `rts` to stop it, so a vector that left by
# `rte` instead would hand every check below a window running through its NEIGHBOURS, and each of
# them would then be answering about whatever the linker placed next. Two assertions close it — the
# last line IS the `rts`, and the only labels inside are this routine's own three.
TICK_VECTOR_LAST=$(printf '%s\n' "$TICK_VECTOR_ROUTINE" | awk -F'\t' 'END {print $NF}')
[ "$TICK_VECTOR_LAST" = "rts" ] || {
  echo "ERROR: $TICK_VECTOR's scrape ends on '$TICK_VECTOR_LAST', not rts. The routine leaves by"
  echo "       pushing bg_timer_c_chain and returning through it — that IS how TOS's own 200 Hz"
  echo "       work still happens — so an rte here is both a lost chain and a scrape that ran on"
  echo "       into the next routine."; exit 1; }
TICK_VECTOR_LABELS=$(printf '%s\n' "$TICK_VECTOR_ROUTINE" | sed -n 's/^[0-9a-f]* <\(.*\)>:$/\1/p')
[ "$TICK_VECTOR_LABELS" = "$(printf '%s\n%s\n%s' "$TICK_VECTOR" "$TICK_BODY" "$TICK_BODY_END")" ] || {
  echo "ERROR: $TICK_VECTOR's routine holds the labels below, not exactly its own three in order."
  printf '       %s\n' $TICK_VECTOR_LABELS
  echo "       Either the twin gained a symbol, or the scrape ran past this routine's end."
  exit 1; }

# ...AND IT IS THE TWIN'S OWN ROUTINE, not a same-named stub somewhere else. `nm` is asked of the
# object the twin was assembled into, because that is the claim: the vector the machine jumps to is
# the head of the transcription, in the file the differential verifies.
TICK_VECTOR_IN_TWIN=$(defined_globals "$OBJ/asm_sound_tick.o" | grep -c "^$TICK_VECTOR\$" || true)
[ "$TICK_VECTOR_IN_TWIN" = "1" ] || {
  echo "ERROR: $OBJ/asm_sound_tick.o defines $TICK_VECTOR $TICK_VECTOR_IN_TWIN time(s), not"
  echo "       once. The 200 Hz vector is the head of ../src/asm/sound_tick.S's transcription; a"
  echo "       definition anywhere else is a second handler with the same name."; exit 1; }

# CHECKS 2-6 BELOW ARE ONE SHAPE — "this is in the routine exactly once" — and are one function
# rather than five copies of a `grep -c` and a four-line `echo`. Each FAILS CLOSED: a pattern that
# rotted counts zero, which is not one. (Check 1 is the exception, being a must-be-ZERO, and carries
# its own whole-disassembly control for that reason.)
require_once_in_routine() {   # <grep flag: E|F> <pattern> <what it is> <why it matters...>
  local flag=$1 pattern=$2 what=$3; shift 3
  local seen
  seen=$(printf '%s\n' "$TICK_VECTOR_ROUTINE" | grep -c"$flag" -- "$pattern" || true)
  [ "$seen" = "1" ] && return 0
  echo "ERROR: $what appears $seen time(s) in $TICK_VECTOR's routine, not once."
  printf '       %s\n' "$@"
  exit 1
}

# 1. IT CALLS NOTHING. `jsr|bsr|jmp`, all three: the two call forms assemble differently and a `bsr`
#    to the C core would read as "never called" — a FALSE PASS, the direction that matters — and a
#    `jmp` would leave the routine without running its own epilogue. This is the successor to the
#    pair of counts this gate used to make (one call to the twin, none to the C core): with the
#    vector folded INTO the twin there is no correct call left to make from here. `bra`/`Bcc`/`dbf`
#    are NOT in this pattern, because the transcribed body is full of them; what covers a branch
#    round the body is check 2, over the prologue alone.
CALL_RE='[[:space:]](jsr|bsr|jmp)'
TICK_VECTOR_CALLS=$(printf '%s\n' "$TICK_VECTOR_ROUTINE" | grep -cE "$CALL_RE" || true)
[ "$TICK_VECTOR_CALLS" = "0" ] || {
  echo "ERROR: $TICK_VECTOR's routine makes $TICK_VECTOR_CALLS call(s)/jump(s); it must make"
  echo "       none. It runs ../src/asm/sound_tick.S's transcription by falling into it, and the C"
  echo "       core ../src/sound.c::timer_c_sound_isr — still linked, still the reference — must"
  echo "       not be what the interrupt reaches."; exit 1; }
#    ...and this is the ONE check here that fails OPEN, because a rotted pattern counts zero and
#    reads as a clean pass. So the same pattern is run over the WHOLE disassembly, where the answer
#    cannot be zero in a program built out of `jsr`s.
grep -qE "$CALL_RE" "$DISASSEMBLY" || {
  echo "ERROR: the call scan matched no jsr/bsr/jmp in the WHOLE of $DISASSEMBLY — its pattern has"
  echo "       rotted, so the zero it reported above meant nothing"; exit 1; }

# 2. THE PROLOGUE FALLS THROUGH INTO THE BODY, which is the claim the body's LABEL alone does not
#    make: a label inside the scrape says the two are laid out in that order and nothing about flow.
#    A `tst.b`/`beq` guard added to the prologue — or a `bra` left behind while bisecting — would
#    skip all 792 transcribed bytes with every other check here still green, still bumping
#    `bg_timer_c_ticks`, and still passing smoke.py's TIMER_C_TICKS. So the prologue is scraped on
#    its own and must contain NO control transfer of any kind.
TICK_VECTOR_PROLOGUE=$(printf '%s\n' "$TICK_VECTOR_ROUTINE" \
                       | awk -v body="$TICK_BODY" '$0 ~ "^[0-9a-f]+ <" body ">:" {exit} {print}')
PROLOGUE_BRANCHES=$(printf '%s\n' "$TICK_VECTOR_PROLOGUE" \
                    | grep -cE '[[:space:]](jsr|bsr|jmp|rts|rte|dbf|b[a-z])' || true)
[ "$PROLOGUE_BRANCHES" = "0" ] || {
  echo "ERROR: $TICK_VECTOR's prologue holds $PROLOGUE_BRANCHES control transfer(s); it must hold"
  echo "       none. The vector reaches the original's own 792 bytes by FALLING INTO them, and a"
  echo "       branch that skips them leaves a mute 200 Hz tick that every other check here — and"
  echo "       every smoke — reports as healthy."; exit 1; }
require_once_in_routine E "^[0-9a-f]+ <$TICK_BODY>:" "the transcribed body's label" \
  "The prologue falls through, so the body has to be what it falls INTO; this is the other" \
  "half of that, and it is where the 792 bytes the differential verified actually sit."

# 3. IT SAVES AND RESTORES THE WHOLE SET IT TOUCHES. This is `docs/on-target-execution.md`'s register
#    check, applied to the one arm no differential reaches: a vector owes its victim every register
#    it writes, and dropping a name is INVISIBLE everywhere else — the image is identical, the twin's
#    own battery runs the C-signature arm and never this one, and the cost pin gets CHEAPER.
#    DERIVED, NOT SPELT: the two lists are read out of the disassembly and held equal to each other,
#    and then every register the routine so much as MENTIONS has to be inside them — so a body that
#    starts using %a4 reds here instead of returning %a4 clobbered at 200 Hz, which a literal
#    `movem.l %d0-%d3/%a0-%a3` comparison could never have caught.
TICK_SAVE_LIST=$(printf '%s\n' "$TICK_VECTOR_ROUTINE" | sed -n 's/.*moveml \(%[^,]*\),%sp@-$/\1/p')
TICK_RESTORE_LIST=$(printf '%s\n' "$TICK_VECTOR_ROUTINE" | sed -n 's/.*moveml %sp@+,\(%.*\)$/\1/p')
[ -n "$TICK_SAVE_LIST" ] && [ "$TICK_SAVE_LIST" = "$TICK_RESTORE_LIST" ] || {
  echo "ERROR: $TICK_VECTOR saves '$TICK_SAVE_LIST' and restores '$TICK_RESTORE_LIST'. A vector"
  echo "       must hand every register back; an asymmetric pair (or a scrape that found neither)"
  echo "       corrupts whatever the interrupt landed in, 200 times a second."; exit 1; }
# `%d0-%d3/%a0-%a3` -> one register a line, so the mentioned set can be compared against it.
TICK_SAVED_REGISTERS=$(printf '%s\n' "$TICK_SAVE_LIST" | awk 'BEGIN { RS = "/" } {
    sub(/\n$/, "");
    if (length($0) == 3) { print $0; next }
    file = substr($0, 2, 1); low = substr($0, 3, 1) + 0; high = substr($0, 7, 1) + 0;
    for (n = low; n <= high; n++) print "%" file n
  }' | sort -u)
# ...against every register the routine names OUTSIDE those two instructions. `%sp` is objdump's own
# spelling for %a7 and is never in a `movem` list, so it cannot appear here.
TICK_USED_REGISTERS=$(printf '%s\n' "$TICK_VECTOR_ROUTINE" | grep -v moveml \
                      | grep -oE '%[da][0-7]' | sort -u)
[ -n "$TICK_USED_REGISTERS" ] || {
  echo "ERROR: $TICK_VECTOR's routine names no data or address register at all — the register scan"
  echo "       is broken and a clean report from it would mean nothing"; exit 1; }
UNSAVED=$(comm -23 <(printf '%s\n' "$TICK_USED_REGISTERS") <(printf '%s\n' "$TICK_SAVED_REGISTERS"))
[ -z "$UNSAVED" ] || {
  echo "ERROR: $TICK_VECTOR touches register(s) its movem pair does not save:"
  printf '       %s\n' $UNSAVED
  echo "       A 68000 vector owes its victim every register it writes, and nothing off target can"
  echo "       see this one: the image is identical, the differential runs the other arm, and the"
  echo "       twin's cost pin gets cheaper. Widen both movem lists in ../src/asm/sound_tick.S."
  exit 1; }

# 4. NOTHING ELSE TOUCHES THE STACK. The host arm has this rule as a pytest over its own object
#    (`test_the_twin_never_stores_through_its_own_frame`); this is the same rule on the arm that
#    pytest cannot see. Three mentions and no more: the chain push and the two `movem`s. A spill or a
#    scratch push added here writes memory nobody staged, and an unbalanced one makes the closing
#    `rts` return into the register file.
TICK_VECTOR_STACK=$(printf '%s\n' "$TICK_VECTOR_ROUTINE" | grep -cE '%sp|%a7' || true)
[ "$TICK_VECTOR_STACK" = "3" ] || {
  echo "ERROR: $TICK_VECTOR's routine names the stack pointer $TICK_VECTOR_STACK time(s), not 3 —"
  echo "       the bg_timer_c_chain push and the two movem halves. Anything else in an interrupt"
  echo "       handler's own frame is a write nobody staged."; exit 1; }
#    ...and the chain push is checked by POSITION rather than by count, because what matters is that
#    it happens BEFORE the register save: it is this routine's return address, so pushed anywhere
#    else the closing `rts` returns into the register file. (`awk -F'\t'` rather than a `sed` with a
#    `\t` in its pattern: only some `sed`s read that escape, and the one that does not would compare
#    a whole objdump line against the expected mnemonic.)
TICK_VECTOR_FIRST=$(printf '%s\n' "$TICK_VECTOR_ROUTINE" | awk -F'\t' 'NR == 2 {print $NF}')
case "$TICK_VECTOR_FIRST" in
  "movel "*"<bg_timer_c_chain>,%sp@-") ;;
  *) echo "ERROR: $TICK_VECTOR's first instruction is '$TICK_VECTOR_FIRST', not the push of"
     echo "       bg_timer_c_chain. TOS's own 200 Hz handler is this routine's return address and"
     echo "       has to be on the stack UNDER the saved registers."; exit 1;; esac

# 5. IT STILL MIRRORS $484 OUT TO THE MACHINE, at the address the VERIFIED CORE HEADER gives. The
#    pattern is built from `../include/sound.h`'s own TOS_CONTERM, so this is the two-language pin
#    the shared-numbers loop used to carry for `CONTERM` — made against the instruction that ships
#    rather than against a source line. `mirror_conterm`'s one-shot poke at PHASE_GEM_OPEN already
#    leaves the machine byte at 0 and the body clears the image byte every tick, so smoke.py's
#    CONTERM_AT_ANCHOR check passes whether or not the per-tick mirror runs: this is the only thing
#    in the tree that can see it go.
CONTERM_FROM_H=$(scrape_c_define "$REC/include/sound.h" TOS_CONTERM)
[ -n "$CONTERM_FROM_H" ] || {
  echo "ERROR: TOS_CONTERM scraped EMPTY from $REC/include/sound.h — the pattern has stopped"
  echo "       matching, and the mirror check below would be looking for the wrong address"; exit 1; }
CONTERM_DEC=$(printf '%d' "$CONTERM_FROM_H")
#    THE SOURCE REGISTER IS DERIVED, NOT SPELT, and that is what makes this check cover the base load
#    as well: the prologue's `movea.l bg_image_base,%aN` names the register, and the mirror has to
#    read the SAME one. Drop the base load and there is no register to derive; aim the mirror at a
#    different one and it does not match. Either way the tick would otherwise run on whatever %aN the
#    interrupt landed in — the whole handler against a wild base, silently, 200 times a second.
TICK_BASE_REGISTER=$(printf '%s\n' "$TICK_VECTOR_PROLOGUE" \
                     | sed -n 's/.*moveal [0-9a-f]* <bg_image_base>,\(%a[0-7]\)$/\1/p')
[ -n "$TICK_BASE_REGISTER" ] || {
  echo "ERROR: $TICK_VECTOR's prologue does not load bg_image_base into an address register. Every"
  echo "       address the transcribed body forms is that base plus an offset; without the load the"
  echo "       whole tick runs against whatever the interrupt was using."; exit 1; }
# `([^0-9a-f]|$)`, not `[^0-9a-f]`: objdump only annotates an absolute operand with `<symbol+0x..>`
# when a symbol resolves at or below it, so requiring a character AFTER the address would turn a
# link with nothing under $484 into a false red that reads exactly like the regression this catches.
CONTERM_MIRROR_RE="moveb $TICK_BASE_REGISTER@\($CONTERM_DEC\),$(printf '%x' "$CONTERM_DEC")([^0-9a-f]|\$)"
require_once_in_routine E "$CONTERM_MIRROR_RE" \
  "'move.b TOS_CONTERM($TICK_BASE_REGISTER),MACHINE_CONTERM' at $CONTERM_FROM_H (../include/sound.h's TOS_CONTERM)" \
  "That store IS the key click actually stopping, and losing it — or aiming it somewhere" \
  "else — is a silent regression no screenshot and no differential can see."

# 6. AND THE MIRROR HAPPENS BEFORE THE REGISTERS COME BACK, which every check above is blind to
#    because they all count rather than order. Restored first, the mirror reads
#    `interrupted_code_a3 + $484` and stores THAT byte into TOS's own key-click flag, twice a frame,
#    for the life of the run — with all five patterns still matching exactly once, the transcription
#    pin untouched (both instructions are outside its bracket), `make test` running the other arm,
#    and smoke.py's CONTERM_AT_ANCHOR green because `mirror_conterm` already left the machine byte
#    at 0. Line numbers within the routine are the cheapest thing that can see it.
MIRROR_AT=$(printf '%s\n' "$TICK_VECTOR_ROUTINE" | grep -nE "$CONTERM_MIRROR_RE" | cut -d: -f1)
RESTORE_AT=$(printf '%s\n' "$TICK_VECTOR_ROUTINE" | grep -nF 'moveml %sp@+,' | cut -d: -f1)
[ "$MIRROR_AT" -lt "$RESTORE_AT" ] || {
  echo "ERROR: $TICK_VECTOR mirrors \$484 at line $MIRROR_AT of its routine and restores its"
  echo "       registers at line $RESTORE_AT. The mirror reads the IMAGE through $TICK_BASE_REGISTER"
  echo "       and must run while that register is still ours."; exit 1; }

# ...AND THE BYTES THAT SHIP ARE THE BYTES THAT WERE VERIFIED. `test/test_sound_asm.py` compares the
# twin's transcribed span against the original's — but over the blob KIT.MK assembles, with kit.mk's
# flags and its `-DRECREATE_HOST_DIFFERENTIAL`. This build assembles the same `.S` with its own, and
# the two arms of that flag are exactly the entry and the epilogue AROUND the span: nothing else may
# differ, and nothing else held the two outputs against each other. So the same span is compared
# again HERE, against the same reference — the relocated image this build just generated, which IS
# the original's memory at ../project.toml's load base.
# The transcribed span's address in the original — the same pair `test/test_sound_asm.py` calls
# ORIGINAL_BODY, and the two are held equal by both comparing against the same image bytes.
TWIN_BODY_AT=0x145be
TWIN_SPAN=$("$PY" "$HERE/asm_twin_ships.py" "$OBJ/asm_sound_tick.o" timer_c_sound_isr \
            "$TWIN_BODY_AT" "$DISK/c/GHOST.IMG" "$LOAD_BASE")
[ "$TWIN_SPAN" = "OK" ] || {
  echo "ERROR: the asm twin this build assembled is not a transcription of the original: $TWIN_SPAN"
  echo "       test/test_sound_asm.py compares the same span over the blob the KIT assembles; this"
  echo "       is the same comparison over the object about to be LINKED, so the two builds cannot"
  echo "       ship different instruction streams under one green differential."; exit 1; }
echo ">> the 200 Hz vector IS the asm twin (calls nothing, falls into the body, saves the whole" \
     "register set, chains, mirrors $CONTERM_FROM_H), and the 792 bytes about to ship are the" \
     "original's own"

# ---- the codegen scan: docs/on-target-execution.md class 6 --------------------------------------
# A store through the same address register the source operand postincrements. The 68000 computes a
# MOVE's destination effective address AFTER the source's postincrement, so every element lands one
# slot high; it hangs the machine when the last one falls off the end of a hardware block. GCC emits
# it from C that reads perfectly, and `volatile` does not stop it.
EA_SCAN='
  { register = "";
    if (match($0, /%a[0-7]@\+,%a[0-7]@\(/)) {
      register = substr($0, RSTART + 1, 2);
      if (register != substr($0, RSTART + 7, 2)) register = "";
    } else if (match($0, /\(%a[0-7]\)\+,\(%a[0-7],/)) {
      register = substr($0, RSTART + 2, 2);
      if (register != substr($0, RSTART + 9, 2)) register = "";
    }
    if (register != "") print;
  }'
echo ">> codegen scan: the postincrement-source / indexed-destination shape"
EA_CONTROL_LINES=2
EA_CONTROL=$(printf '%s\n%s\n' 'movew %a0@+,%a0@(0,%d0:l)' 'move.w (%a3)+,(%a3,%d1.l)' \
             | awk "$EA_SCAN" | wc -l | tr -d ' ')
[ "$EA_CONTROL" = "$EA_CONTROL_LINES" ] || {
  echo "ERROR: the EA scan named $EA_CONTROL of $EA_CONTROL_LINES known-bad lines — it has rotted,"
  echo "       and a clean report from it would mean nothing."; exit 1; }
SHIFT_EA=$(awk "$EA_SCAN" "$DISASSEMBLY" || true)
[ -z "$SHIFT_EA" ] || {
  echo "ERROR: the 68000 EA-ordering shape is in the binary. See docs/on-target-execution.md class 6."
  echo "$SHIFT_EA"; exit 1; }
echo "   none"

# ---- the endianness tax: docs/on-target-execution.md class 1 -----------------------------------
$CC $CFLAGS -E -dM -x c /dev/null | grep -q '__ORDER_BIG_ENDIAN__' || {
  echo "ERROR: the m68k compiler does not define __ORDER_BIG_ENDIAN__ — machine.h's guard cannot"
  echo "       have selected the native accessors."; exit 1; }
SHUFFLES=$(grep -c 'lsl.*#8' "$DISASSEMBLY" || true)
echo "   lsl #8 instructions: $SHUFFLES (hundreds would mean machine.h's big-endian arm did not fire)"

# ---- objcopy -> .PRG ----------------------------------------------------------------------------
echo ">> objcopy -> flat binary"
m68k-elf-strip --strip-debug "$BUILD/bubble.elf"
m68k-elf-objcopy -O binary "$BUILD/bubble.elf" "$BUILD/bubble.bin"
echo ">> wrap -> GEMDOS .PRG"
PRG_REPORT=$("$PY" "$HERE/mkprg.py" "$BUILD/bubble.elf" "$BUILD/bubble.bin" "$BUILD/$PRG")
echo "$PRG_REPORT"

prg_field() { echo "$PRG_REPORT" | sed -n "s/.*[^a-z]$1=\([0-9][0-9]*\).*/\1/p"; }
TEXT_BYTES=$(prg_field text); DATA_BYTES=$(prg_field data); BSS_BYTES=$(prg_field bss)
[ -n "$TEXT_BYTES" ] && [ -n "$DATA_BYTES" ] && [ -n "$BSS_BYTES" ] || {
  echo "ERROR: mkprg.py's report line is not the text=/data=/bss= shape the size gate reads:"
  echo "       $PRG_REPORT"; exit 1; }
BASEPAGE_BYTES=256
LOAD_BYTES=$((BASEPAGE_BYTES + TEXT_BYTES + DATA_BYTES + BSS_BYTES))
BUDGET_BYTES=$((TPA_1MB_BYTES - STACK_RESERVE_BYTES))
echo ">> size gate (a ${MEMSIZE_MB} MB machine's TPA, measured)"
echo "   basepage=$BASEPAGE_BYTES text=$TEXT_BYTES data=$DATA_BYTES bss=$BSS_BYTES" \
     "-> $LOAD_BYTES B loaded"
echo "   budget $BUDGET_BYTES B = TPA $TPA_1MB_BYTES - stack reserve $STACK_RESERVE_BYTES"
echo "   $((BUDGET_BYTES - LOAD_BYTES)) B spare"
[ "$LOAD_BYTES" -le "$BUDGET_BYTES" ] || {
  echo "ERROR: $PRG needs $LOAD_BYTES B of TPA and a ${MEMSIZE_MB} MB machine has $BUDGET_BYTES B."
  echo "       Shrink BG_TARGET_IMAGE_BYTES (shim_include/os.h) or the binary — do NOT raise the"
  echo "       budget, which is a measurement and not a policy."
  exit 1; }

cp "$BUILD/$PRG" "$DISK/c/$PRG"
cp "$BUILD/$PRG" "$BUILD/BUBBLE-$MODE.PRG"
ls -l "$DISK/c/$PRG" "$DISK/c/GHOST.IMG"

# THE A: VOLUME IS BUILT ON EVERY RUN, not only for the floppy medium: the game opens three of its
# files as "A:GHOST.xxx" (build.sh's staging note), so even a GEMDOS run needs a floppy in A: — the
# drive letter is the ORIGINAL'S and this build does not patch it.
echo ">> the A: data volume"
"$PY" "$HERE/mkfloppy.py" --data "$DISK/a" --out "$DISK/GHOST.ST"

if [ "$MEDIUM" = "floppy" ]; then
  echo ">> bootable floppy"
  "$PY" "$HERE/mkfloppy.py" --prg "$BUILD/BUBBLE-$MODE.PRG" --data "$DISK/a" \
        --image "$DISK/c/GHOST.IMG" --out "$DISK/BUBBLE.ST"
fi
