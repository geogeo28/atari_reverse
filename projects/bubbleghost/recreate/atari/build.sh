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
GLOBALS_LOAD_BASE=$(sed -n 's/^#define BG_LOAD_BASE *\(0x[0-9a-fA-F]*\).*/\1/p' "$REC/include/globals.h")
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
  FROM_H=$(sed -n "s/^#define BG_GATE_$GATE  *\([0-9]*\)u.*/\1/p" "$HERE/shim_include/tos.h")
  FROM_S=$(sed -n "s/^ *GATE_$GATE *= *\([0-9]*\).*/\1/p" "$HERE/bubble_os.s")
  [ -n "$FROM_H" ] && [ -n "$FROM_S" ] || {
    echo "ERROR: the gate operation BG_GATE_$GATE is missing from tos.h ('$FROM_H') or bubble_os.s"
    echo "       ('$FROM_S') — the scrape has stopped matching one of them, and a clean report from"
    echo "       it would mean nothing"; exit 1; }
  [ "$FROM_H" = "$FROM_S" ] || {
    echo "ERROR: BG_GATE_$GATE is $FROM_H in shim_include/tos.h and $FROM_S in bubble_os.s"; exit 1; }
done
echo ">> the supervisor gate's 3 operations agree between tos.h and bubble_os.s"

# ---- ...and the chip's two ports are ONE set of numbers in two languages ------------------------
# The trapped write is bubble_os.s's `bg_super_gate_entry` and the ISR's untrapped one is
# `psg_untrapped_write` in shim_include/psg.h; they address the same chip, so the port and the data
# displacement are scraped from both and compared. A disagreement here writes a sound register to
# whatever else lives at the address. (`PSG_REG_MASK` is deliberately NOT in this loop: only the
# trapped door masks, for the reason psg.h's header gives.)
for PORT in PSG_SELECT:BG_PSG_SELECT PSG_DATA:BG_PSG_DATA_OFFSET; do
  FROM_S=$(sed -n "s/^ *${PORT%%:*} *= *\([0-9a-fA-FxX]*\).*/\1/p" "$HERE/bubble_os.s")
  FROM_H=$(sed -n "s/^#define ${PORT##*:}  *\([0-9a-fA-FxX]*\)u.*/\1/p" "$HERE/shim_include/psg.h")
  # An EMPTY scrape is refused first, because `printf '%d' ""` is 0 with exit status 0 on the bash
  # this runs under — two missed patterns would otherwise agree at zero and the gate would print its
  # green line over nothing. Past that, both are normalised to decimal so 0x2 and 2 compare equal,
  # and a printf that REFUSES catches the other rot ("0x" out of a pattern that lost its digits).
  [ -n "$FROM_S" ] && [ -n "$FROM_H" ] || {
    echo "ERROR: ${PORT%%:*} scraped EMPTY from bubble_os.s ('$FROM_S') or ${PORT##*:} from"
    echo "       shim_include/psg.h ('$FROM_H') — the pattern has stopped matching, and a clean"
    echo "       report from it would mean nothing"; exit 1; }
  VALUE_S=$(printf '%d' "$FROM_S" 2>/dev/null) && VALUE_H=$(printf '%d' "$FROM_H" 2>/dev/null) || {
    echo "ERROR: ${PORT%%:*} scraped as '$FROM_S' from bubble_os.s and ${PORT##*:} as '$FROM_H' from"
    echo "       shim_include/psg.h, and at least one is not a number — the pattern is matching only"
    echo "       part of what it should, and a clean report from it would mean nothing"; exit 1; }
  [ "$VALUE_S" = "$VALUE_H" ] || {
    echo "ERROR: the PSG port is $FROM_S in bubble_os.s (${PORT%%:*}) and $FROM_H in"
    echo "       shim_include/psg.h (${PORT##*:}). The trapped and untrapped writes would reach"
    echo "       different addresses."; exit 1; }
done
# ...and that the untrapped door's BODY is those two macros and nothing else: exactly two volatile
# byte stores, select before data. The equality above pins the numbers; this pins that they are what
# the store reaches, which is the half no other surface has — the differential compiles the kit's
# psg.c and not this header, and STATE.BIN records nothing about the chip. A rotted `sed` scrapes
# empty, which is not the expected text either, so the check fails closed.
# THE WHOLE STORE LINE IS PINNED, NOT ONLY ITS TARGET. A first draft scraped the destination alone
# (`... \(.*\) = .*;`), which swallowed the value expression — so `(uint8_t)(reg & 15)` in the select
# store passed this gate green, and psg.h's whole argument for NOT masking (the original's ISR does
# not) would have been a comment contradicting its own code with no surface to say so.
PSG_STORES=$(sed -n '/^static inline void psg_untrapped_write/,/^}/p' "$HERE/shim_include/psg.h" \
             | sed -n 's/^ *\(\*(volatile uint8_t \*).* = .*;\)$/\1/p')
PSG_STORES_EXPECTED='*(volatile uint8_t *)BG_PSG_SELECT = (uint8_t)reg;
*(volatile uint8_t *)(BG_PSG_SELECT + BG_PSG_DATA_OFFSET) = value;'
[ "$PSG_STORES" = "$PSG_STORES_EXPECTED" ] || {
  echo "ERROR: psg_untrapped_write's body is not the two volatile byte stores this gate knows."
  echo "       expected:"; echo "$PSG_STORES_EXPECTED" | sed 's/^/         /'
  echo "       scraped:";  echo "$PSG_STORES"          | sed 's/^/         /'
  echo "       The 200 Hz ISR reaches the chip through this and nothing else watches it."; exit 1; }

# ...and that the TRAPPED door still MASKS, which is the other half of the asymmetry psg.h argues.
# The two doors are meant to disagree here — the original's do, its ISR writing the ports bare and
# only its trap handler carrying `and.b #$f,d1` @ 0x1495c — and neither half was watched by anything:
# the differential compiles the kit's psg.c and never this pair, so deleting the `andi.l` would make
# the doors agree silently, in the direction the header spends a page refusing.
PSG_TRAPPED_MASKS=$(grep -c '^ *andi\.l  *#PSG_REG_MASK,%d1$' "$HERE/bubble_os.s" || true)
[ "$PSG_TRAPPED_MASKS" = "1" ] || {
  echo "ERROR: bg_super_gate_entry's 'andi.l #PSG_REG_MASK,%d1' was scraped $PSG_TRAPPED_MASKS times"
  echo "       in bubble_os.s, not once. The TRAPPED door is where this build's register mask lives"
  echo "       (shim_include/psg.h's header argues why the untrapped one has none); losing it makes"
  echo "       the two doors agree where the original's two do not."; exit 1; }
echo ">> the chip's 2 ports agree between psg.h and bubble_os.s, the ISR's store is those 2 stores" \
     "and nothing else, and only the trapped door masks"

# ---- the trap-register scan ---------------------------------------------------------------------
# docs/on-target-execution.md class 3's register half: the one hardware-only bug class no
# differential in this workspace can see. The count is asserted so a rotted regex reds rather than
# passing vacuously over a file it no longer parses.
TRAP_WRAPPERS=29
echo ">> trap-register scan ($TRAP_WRAPPERS wrappers)"
"$TOOLS/assert_trap_registers.sh" --expect "$TRAP_WRAPPERS" "$HERE/bubble_os.s"

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
UNTRACKED_CORES=$(git -C "$REC" ls-files --others --exclude-standard -- 'src/*.c' 'include/*.h')
[ -z "$UNTRACKED_CORES" ] || {
  echo "ERROR: ../src or ../include holds source git does not track, and \`git diff\` is silent about"
  echo "       untracked files — so the gate above would have passed over it. Commit or remove:"
  echo "$UNTRACKED_CORES" | sed 's/^/         /'; exit 1; }
CORE_FILE_COUNT=$(git -C "$REC" ls-files -- 'src/*.c' 'include/*.h' | wc -l | tr -d ' ')
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

# ---- the sound tick is ONE symbol, because atari/profile.py measures it as one -------------------
# `SOUND_TICK_SYMBOLS` sums the profiler's per-ADDRESS rows over `timer_c_sound_isr`'s range, which
# is [its symbol, the next symbol above it). Every helper the 200 Hz handler runs is `static` and
# GCC inlines all of them, so that range IS the handler. profile.py refuses a name that VANISHES
# from the map and cannot see one that APPEARS — and a helper that stopped being inlined would both
# take its own cycles out of the sum and cut the handler's range short at itself, so the tick would
# read low twice over with nothing red. `static inline` is a hint; this is the assertion.
# NOT `nm | grep -q`: this file runs under `set -o pipefail`, `grep -q` closes the pipe on its FIRST
# match, and the SIGPIPE that kills `nm` then makes the pipeline's status 141 — so the one case the
# gate exists to catch is the one case the `&&` does not fire on. Measured here, with the symbol
# present and the gate green (2026-09-07). `grep -c` reads the whole stream instead.
MUST_STAY_INLINED="step_swept_envelope step_triangle_lfo psg_untrapped_write"
OBJECT_TEXT_SYMBOLS=$(m68k-elf-nm $CORE_OBJECTS $SHIM_OBJECTS | awk '$2 == "t" || $2 == "T" {print $3}')
for NAME in $MUST_STAY_INLINED; do
  OUT_OF_LINE=$(printf '%s\n' "$OBJECT_TEXT_SYMBOLS" | grep -c "^$NAME\$" || true)
  [ "$OUT_OF_LINE" = "0" ] || {
    echo "ERROR: $NAME has an out-of-line body in this build ($OUT_OF_LINE object(s)). It is one of"
    echo "       the routines atari/profile.py's sound-tick range assumes is inlined into"
    echo "       timer_c_sound_isr, so the tick would now be measured over less code than it runs."
    echo "       Either restore the inlining or add $NAME to SOUND_TICK_SYMBOLS and re-measure."
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
