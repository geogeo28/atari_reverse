#!/bin/bash
# Build ZYNAPS.PRG from the verified reconstruction with the m68k-elf cross toolchain, and stage a
# GEMDOS drive for Hatari.
#
#   build.sh title      -> M1: the boot's verified slices up to 0x101ba, the title picture on
#                          screen, the title tune (0x0b) ticking off the reconstruction's own
#                          vertical-blank handler, then a clean hand-back and Pterm.
#   build.sh titlefault -> M1's NEGATIVE CONTROL: identical, with ONE PEN corrupted on its way to
#                          the shifter and nothing else. The pens and the rendered picture must go
#                          red while the framebuffer, the trap ledger and the PSG timeline stay
#                          green — and `smoke.py titlefault` inverts its verdict.
#   build.sh floppy     -> the M1 build again, plus disk/ZYNAPS.ST: a BOOTABLE FAT12 floppy laid
#                          out like the original's, with our .PRG where the game's used to be
#                          (AUTO\ZYNAPS17.PRG, the name TOS's desktop looks for). That is the form
#                          that goes onto the real STE. `smoke.py floppy` boots it.
#   build.sh play       -> the same boot with the anchor and the teardown lifted, so the title
#                          screen runs until the window is closed. M1 HAS NO INPUT PATH: nothing
#                          reads the joystick or the keyboard, because the routine that would
#                          (`title_attract_loop` @ 0x12ac2) is unported. It is a thing to look at
#                          and listen to.
#
# Writes disk/{ZYNAPS.PRG,ZYNAPS.IMG} plus the game's own data files, and keeps
# build/ZYNAPS-<mode>.PRG so a check needing two builds in sequence does not have to rebuild.
# build/ and disk/ are gitignored (the repo .gitignore already covers
# projects/*/recreate/atari/{build,disk}).
#
# THE CORES ARE COMPILED UNCHANGED — no `-D` reaches ../src or ../include, and the checks below
# measure that rather than asserting it in prose. The seam is now the INCLUDE PATH plus ONE omitted
# directory:
#   * shim_include/ shadows the kit's `os.h` (real GEMDOS, no-op Super) and `#include_next`s the
#     rest. It no longer shadows `hw.h`: the kit exports `hw_read8` and `hw_write8/16/32` itself and
#     zynaps_backend.c is the target half of exactly those four names.
#   * ALL of the kit's src/ is left out — its own headers say so (psg.c, hw.c, sched.c: "Off-target
#     only ... a build for the real Atari writes the ports itself"). EVERY core in ../src is built:
#     there is no exclusion any more, because src/irq_hw_offtarget.c's three empty bodies became
#     ordinary `hw_write*` calls in video.c and irq.c.
#     ONE OF THE THREE WAS NOT AN EMPTY BODY ON THIS SIDE, and dropping the exclusion dropped it:
#     zynaps_backend.c's `mfp_ack_timer_b` was a real READ-MODIFY-WRITE (`&= ~bit`), and what
#     ../src/irq.c ships is a plain store of 0 — which acknowledges every in-service MFP channel
#     rather than Timer B's. It is dormant in M1 (nothing starts a timer) and README.md's Unpinned 2
#     is where it is carried; it is named here so that this list is not read as "nothing was lost".
set -euo pipefail

# The pen `titlefault` corrupts. THREE is not arbitrary and the reason is the control's own
# `picture` arm: it has to be a pen the title picture actually uses, or the arm would fail for a
# reason about coverage rather than about the fault (the sibling project's recorded trap). smoke.py
# does not take the number from here — the binary publishes it in STATE.BIN — but it DOES decode
# ZYNPIC.PIC and refuse a fault pen that is not on screen, so this line cannot go stale silently.
FAULT_PEN=3

MODE="${1:-title}"
case "$MODE" in
  title)      DEF="" ;;
  titlefault) DEF="-DZY_FAULT_PEN=$FAULT_PEN" ;;
  # THE FLOPPY IS THE TITLE BINARY ON DIFFERENT MEDIA, and that is the whole difference: no `-D`,
  # so the .PRG this writes is byte-for-byte the one `smoke.py title` judged. What it adds is
  # mkfloppy.py at the end.
  floppy)     DEF="" ;;
  # THE PLAY BUILD IS THE TITLE BUILD WITH ITS ANCHOR MOVED OUT OF REACH, and that is the whole
  # difference — no `#ifdef` in the C, so the code a person watches is the code the smoke asserted.
  # zynaps_main.c waits for `zy_vbl_ticks` to reach this number before it anchors, dumps and hands
  # the machine back; at 50 Hz, 2^32 vblanks is about 2.7 years, so it never does.
  play)       DEF="-DZY_SMOKE_VBLS=0xffffffffu" ;;
  *) echo "usage: build.sh [title | titlefault | floppy | play]"; exit 2 ;;
esac

HERE="$(cd "$(dirname "$0")" && pwd)"
REC="$(cd "$HERE/.." && pwd)"                             # recreate/
TOOLS="$(cd "$REC/../../../tools" && pwd)"                # the workspace's game-agnostic tooling
KIT="$TOOLS/recreate_kit"                                 # the shared harness
BIN="$REC/../bin"                                         # projects/zynaps/bin
BUILD="$HERE/build"; DISK="$HERE/disk"
PRG="ZYNAPS.PRG"
mkdir -p "$BUILD" "$DISK"

CC=m68k-elf-gcc

# ---- stage the drive ---------------------------------------------------------------------------
# The GAME'S OWN DATA FILES, copied rather than symlinked: Hatari's GEMDOS drive emulation walks a
# host directory, and the original boots from exactly this set (projects/zynaps/tools/boot_shots.py,
# `gemdos` mode, drives `bin/disk`). The .PRG goes at the ROOT and not in AUTO\, because smoke.py
# starts it with `--auto` and the game resolves its lowercase filenames against the current
# directory — which is the root either way.
echo ">> stage drive"
PY="$REC/.venv/bin/python"; [ -x "$PY" ] || PY=python3
find "$BIN/disk" -maxdepth 1 -type f -exec cp {} "$DISK/" \;
DATA_FILES=$(find "$DISK" -maxdepth 1 -type f ! -name 'ZYNAPS.*' ! -name '*.BIN' | wc -l | tr -d ' ')
echo "   $DATA_FILES data files from $BIN/disk (bin/disk/AUTO is the ORIGINAL's launcher, not ours)"

# The staged image comes FIRST: its byte length is the one source of truth for how much
# zynaps_main.c must read back in, and it is passed straight to the compiler.
"$PY" "$HERE/gen_image.py" "$BIN/ZYNAPS17.PRG" "$DISK/ZYNAPS.IMG"
IMG_BYTES=$(wc -c < "$DISK/ZYNAPS.IMG" | tr -d ' ')       # BSD wc pads with spaces

# ...and the base it is staged AT is scraped from ../project.toml rather than written here. That
# file is where 0x10000 is argued for ("names.txt addresses are Ghidra addresses at this base, so it
# must not move"), and a second spelling could drift from the loader gen_image.py uses.
LOAD_BASE=$(sed -n 's/^load_base *= *\(0x[0-9a-fA-F]*\).*/\1/p' "$REC/project.toml")
[ -n "$LOAD_BASE" ] || { echo "ERROR: no load_base in $REC/project.toml"; exit 1; }
DEF="$DEF -DPROGRAM_BYTES=$IMG_BYTES -DZY_LOAD_BASE=$LOAD_BASE"

# ---- the trap-register scan --------------------------------------------------------------------
# The workspace's one hardware-only bug class that nothing else can see: TOS preserves %d3-%d7 and
# %a3-%a6 across a trap, GCC believes %d2/%a2 survive too, and a wrapper that does not save the pair
# silently corrupts a variable in its C caller. Invisible to every differential in this project, to
# the compiler, and often to emulation. `--expect` is the count of wrappers the scan EVALUATED, so a
# regex that stopped matching reds here instead of passing vacuously over a file it cannot parse.
#
# ELEVEN: Fcreate, Fopen, Fclose, Fread, Fwrite, Super, zy_leave_supervisor, Physbase, Logbase,
# Getrez, Setscreen. `_start` also traps (Pterm0) and is exempt by the scan's own rule — it never
# returns, so there is no caller left to corrupt.
TRAP_WRAPPERS=11
echo ">> trap-register scan ($TRAP_WRAPPERS wrappers)"
"$TOOLS/assert_trap_registers.sh" --expect "$TRAP_WRAPPERS" "$HERE/zynaps_os.s"

# ---- compile + link ----------------------------------------------------------------------------
# THERE IS NO -Wno-array-bounds, and that is deliberate: the flag would reach the VERIFIED CORES
#   too, in the one build where an out-of-bounds index reads live machine memory rather than the
#   harness's guarded image. The shim's own absolute-address dereferences carry a scoped
#   `#pragma GCC diagnostic` instead — see `read_vector` in zynaps_main.c.
# -fno-tree-loop-distribute-patterns: at -O2 GCC recognises zynaps_backend.c's hand-written
#   memcpy/memset loops and replaces them with calls to memcpy/memset — i.e. with themselves.
# -DOS_NO_REFUSAL_TALLY: the kit's os.h anticipates exactly this build and compiles `os_refused`
#   down to an inline identity, so its src/os_refusal.c is not needed. It also compiles away
#   `ikbd_send_cmd`'s give-up arm, which is the only place a core reaches the tally.
# shim_include FIRST: that is the whole seam (it shadows the kit's os.h, and nothing else).
CFLAGS="-m68000 -O2 -fno-tree-loop-distribute-patterns -ffreestanding -fno-jump-tables \
        -fomit-frame-pointer -nostdlib -DOS_NO_REFUSAL_TALLY \
        -I$HERE/shim_include -I$REC/include -I$KIT/include -Wall -Wextra"

# EVERY core in ../src, as a wildcard rather than a typed list, so one added there is built here
# without anyone remembering to add it. There is no exclusion: the kit's write ledger retired
# src/irq_hw_offtarget.c, which was the only file a target build had to skip. What that cost is at
# the top of this script, under the seam description — one of the three bodies it excluded was a
# target-correct read-modify-write, not an empty stub.
# The KIT's src/ is excluded whole, stated in each of those files' own headers (psg.c, hw.c, sched.c:
# "Off-target only ... a build for the real Atari writes the ports itself").
CORES="$(ls "$REC"/src/*.c)"
[ -n "$CORES" ] || { echo "ERROR: no cores found in $REC/src"; exit 1; }

# COMPILED TO OBJECTS FIRST, so the two halves of the seam can be ASKED WHAT THEY DEFINE before
# they are linked together. The gate below is the whole reason this is not one `gcc` invocation.
OBJ="$BUILD/obj"
rm -rf "$OBJ"; mkdir -p "$OBJ"
echo ">> compile (base 0, keep relocs)"
SHIM_OBJECTS=""; CORE_OBJECTS=""
for source in "$HERE/zynaps_os.s" "$HERE/zynaps_main.c" "$HERE/zynaps_backend.c"; do
  object="$OBJ/shim_$(basename "${source%.*}").o"
  $CC $CFLAGS $DEF -c "$source" -o "$object"
  SHIM_OBJECTS="$SHIM_OBJECTS $object"
done
for source in $CORES; do
  object="$OBJ/core_$(basename "${source%.c}").o"
  $CC $CFLAGS $DEF -c "$source" -o "$object"
  CORE_OBJECTS="$CORE_OBJECTS $object"
done

# ---- THE DUPLICATE-SYMBOL GATE ------------------------------------------------------------------
# THE SHIM MAY NOT DEFINE A NAME A CORE DEFINES, and this is the check that says so in those words.
#
# It exists because the seam MOVES. `shifter_write_palette`, `shifter_clear_pen0` and
# `mfp_ack_timer_b` lived in zynaps_backend.c for as long as ../src/irq_hw_offtarget.c held their
# empty off-target bodies; when the kit's write ledger landed, the cores started defining all three
# themselves and the shim's copies became shadows of live code. The linker does object to that — but
# it objects as `multiple definition of 'shifter_clear_pen0'`, in the middle of a link line naming
# thirty files, and it says nothing about WHICH side is meant to own the name. This says it.
#
# It is also the half the linker cannot be relied on for: a build that ever acquires `-z muldefs`,
# or a variable that lands in COMMON, would link clean and run the WRONG BODY — the shim's stub in
# place of a verified core, with `make test` green on the core the machine never executes.
#
# Compared on DEFINED GLOBAL symbols only (nm's T/D/B/R), because a `static` on either side is not a
# collision and an undefined reference is the seam working as intended.
# `NF == 3` is not decoration: given several objects, nm prints a `file.o:` header and a blank line
# between them, and an awk that took $3 unconditionally would put empty strings in both lists — which
# `comm` then reports as a collision on every run, in a check whose whole job is to be quiet.
defined_globals() { m68k-elf-nm -g --defined-only $1 | awk 'NF == 3 {print $3}' | sort -u; }

# ...AND THE GATE PROVES IT CAN FAIL, on every run, in the TWO ways it can rot. The EA scan taught
# the first: a comparison that quietly stopped matching is indistinguishable from a clean build, so
# two synthetic lists with one name in common must produce exactly that name. The second is the half
# that scan does not have — `comm` over two EMPTY lists is also silent, and `defined_globals` is
# exactly the kind of thing that returns nothing when a tool's output shape moves under it (an nm
# that stopped printing three fields, a `-g` that stopped meaning "global"). So the lists are
# computed ONCE, asserted non-empty, and then compared.
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
  echo "       comparison below would be silent whatever the objects hold. defined_globals' parse"
  echo "       has stopped matching m68k-elf-nm's output."
  exit 1; }
COLLISIONS=$(comm -12 <(echo "$SHIM_SYMBOLS") <(echo "$CORE_SYMBOLS"))
[ -z "$COLLISIONS" ] || {
  echo "ERROR: the shim defines $(echo "$COLLISIONS" | wc -l | tr -d ' ') symbol(s) that ../src now"
  echo "       defines too. The core owns the name; delete the shim's copy (and, if it was a seam,"
  echo "       check that what replaced it is one of the kit's own hw_*/psg_* doors):"
  echo "$COLLISIONS" | sed 's/^/         /'
  exit 1; }
echo "   $SHIM_COUNT shim symbols vs $CORE_COUNT core symbols, no name in both"

# --no-warn-rwx-segments: tos.ld deliberately puts text, data and bss in ONE loadable image, because
# that is what a GEMDOS .PRG is — the loader has no notion of segment permissions and neither does a
# 68000 without an MMU. The warning is about ELF hygiene on a hosted target and says nothing here;
# silenced rather than tolerated so that a build's output stays worth reading.
echo ">> link"
$CC $CFLAGS -T "$HERE/tos.ld" -Wl,--emit-relocs -Wl,--no-warn-rwx-segments \
    $SHIM_OBJECTS $CORE_OBJECTS -lgcc -o "$BUILD/zynaps.elf"

# _start must sit at the very first byte of text (GEMDOS enters there).
ENTRY=$(m68k-elf-nm "$BUILD/zynaps.elf" | awk '$3=="_start"{print $1}')
[ "$ENTRY" = "00000000" ] || { echo "ERROR: _start not at 0 (got $ENTRY)"; exit 1; }

# ---- what the COMPILER produced, asked of the object it produced it in --------------------------

# THE PALETTE LOOP'S ADDRESSING MODE, and it is this workspace's most expensive on-target defect.
# GCC folded a sibling project's `for (i = 0; i < 16; i++) pen[i] = table[i]` into one instruction —
# `move.w (%a0)+,(%a0,%d0.l)` — and on the 68000 a MOVE's DESTINATION effective address is computed
# AFTER the source operand's postincrement, so every pen landed one register high and the sixteenth
# write hit $ff8260, the RESOLUTION register. TOS 1.04 died on the spot. Nothing in the diff was
# wrong and the C was not wrong either (docs/on-target-execution.md class 6).
#
# zynaps_backend.c is written so the shape cannot be emitted — each address is computed as a value
# and handed to a function — but "cannot" is a claim about a compiler, so it is measured. What is
# forbidden is one instruction using the SAME address register in a postincrement source and an
# indexed destination; it is the SHAPE that is suspect, not the target.
# ORDER MATTERS AND THE SCAN HAS TO KNOW IT. What is fatal is a postincrement SOURCE with an indexed
# DESTINATION on the same register; the mirror image — `move.l (%a0,%a1.l),(%a0)+` — is ordinary, and
# GCC emits it here. So the pattern spans the comma rather than looking for the two halves anywhere
# in the line. Both operand spellings binutils can print are covered — `(%a0)+,(%a0,` and the older
# `%a0@+,%a0@(` — because which one appears is a property of the disassembler's mode and not of the
# program, and a scan that knew only one would pass vacuously on a toolchain that used the other.
# The offsets are counted off the two spellings themselves, which is why they differ:
#   %a0@+,%a0@(      the register names start 1 and 7 characters into the match
#   (%a0)+,(%a0,     ...and 2 and 9 characters into it
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

# ...AND THE SCAN PROVES IT CAN FAIL, on every run. A pattern that quietly stopped matching would be
# indistinguishable from a clean binary — which is exactly how the sibling project's half-blind exit
# detector survived a year. Two synthetic lines, one per spelling, must both be named.
EA_CONTROL_LINES=2
EA_CONTROL=$(printf '%s\n%s\n' 'movew %a0@+,%a0@(0,%d0:l)' 'move.w (%a3)+,(%a3,%d1.l)' \
             | awk "$EA_SCAN" | wc -l | tr -d ' ')
[ "$EA_CONTROL" = "$EA_CONTROL_LINES" ] || {
  echo "ERROR: the EA scan named $EA_CONTROL of $EA_CONTROL_LINES known-bad lines — it has rotted,"
  echo "       and a clean report from it would mean nothing."; exit 1; }

# ONE disassembly, read by both scans below and left on disk: it is the first thing anyone wants
# after a red, and disassembling the shim plus every core twice is the slowest step in this script
# after the compile itself.
DISASSEMBLY="$BUILD/zynaps.dis"
m68k-elf-objdump -d "$BUILD/zynaps.elf" > "$DISASSEMBLY"
SHIFT_EA=$(awk "$EA_SCAN" "$DISASSEMBLY" || true)
[ -z "$SHIFT_EA" ] || {
  echo "ERROR: the 68000 EA-ordering shape is in the binary — a store through the same register it"
  echo "       postincrements. See docs/on-target-execution.md class 6."
  echo "$SHIFT_EA"; exit 1; }

# THE IKBD SPIN MUST HAVE NO CAP, asked of the code that was actually generated.
#
# ../src/input.c's `ikbd_send_cmd` carries a give-up arm, `IKBD_TX_POLL_MAX`, inside
# `#ifndef OS_NO_REFUSAL_TALLY` — it exists so that an OFF-TARGET case cannot spin for ever on a
# byte the harness forgot to seed. On the machine the 6850 really does empty, the original has no
# cap (`btst #1,$fffc00 / beq.s self / move.b d0,$fffc02 / rts`), and a build that shipped one would
# silently drop a command byte instead of waiting the extra microsecond. -DOS_NO_REFUSAL_TALLY is
# what removes it; this is the check that it did, because a `-D` that stopped reaching the cores
# would look like nothing at all.
#
# THE METRIC IS CONDITIONAL BRANCHES, AND IT IS PROVED AGAINST A REAL CAPPED BUILD. The uncapped
# routine is the original's four instructions and has exactly ONE conditional branch, the poll's own
# `beq` back to itself; the arm adds a second, whatever shape GCC gives it. An earlier draft of this
# scan counted COMPARISONS instead and was vacuous — measured: with the cap present GCC reverses the
# loop onto a countdown and emits `subq`/`bne` with no `cmp` or `tst` at all, so both builds scored
# zero and the gate could not fail. So the control is not a synthetic line here: it is ../src/input.c
# compiled a second time with the macro UNDEFINED, and the scan must score it HIGHER.
IKBD_UNCAPPED_BRANCHES=1
# Cut the routine at the next SYMBOL, not at the first `rts`: if GCC ever tail-called `hw_write8`
# out of it — plausible, the store is the last thing it does — there would be no `rts`, and the awk
# would run to the end of a 41 KB disassembly and count every branch in the program.
IKBD_BODY_SCAN='
  $0 ~ /<ikbd_send_cmd>:/ { inside = 1; next }
  inside && /^[0-9a-f]+ </ { exit }
  inside { print }'
# `bra`/`bsr`/`bset`/`btst`/`bclr`/`bchg` are deliberately absent: what the arm adds is a CONDITIONAL
# branch. Both suffix spellings binutils can print are covered (`bnes` and `bne.s`), for the EA
# scan's reason — which one appears is a property of the disassembler, not of the program.
IKBD_BRANCHES='\<(bcc|bcs|beq|bge|bgt|bhi|ble|bls|blt|bmi|bne|bpl|bvc|bvs)([sbwl]|\.[sbwl])?\>'
count_ikbd_branches() { awk "$IKBD_BODY_SCAN" "$1" | grep -cE "$IKBD_BRANCHES" || true; }

echo ">> the IKBD transmitter spin is uncapped"
# The control FIRST, so a scan that scores everything zero is caught before it reports on the build.
$CC $CFLAGS -UOS_NO_REFUSAL_TALLY -c "$REC/src/input.c" -o "$OBJ/input_capped.o" 2>/dev/null
m68k-elf-objdump -d "$OBJ/input_capped.o" > "$OBJ/input_capped.dis"
IKBD_CONTROL=$(count_ikbd_branches "$OBJ/input_capped.dis")
[ "$IKBD_CONTROL" -gt "$IKBD_UNCAPPED_BRANCHES" ] || {
  echo "ERROR: ../src/input.c compiled WITH the cap scores $IKBD_CONTROL conditional branch(es),"
  echo "       which is not more than the $IKBD_UNCAPPED_BRANCHES an uncapped build scores — this"
  echo "       scan cannot tell the two apart, and a clean report from it would mean nothing."
  exit 1; }
IKBD_SHIPPED=$(count_ikbd_branches "$DISASSEMBLY")
[ "$IKBD_SHIPPED" = "$IKBD_UNCAPPED_BRANCHES" ] || {
  echo "ERROR: the linked ikbd_send_cmd has $IKBD_SHIPPED conditional branch(es), not the"
  echo "       $IKBD_UNCAPPED_BRANCHES of the original's spin (the capped control has"
  echo "       $IKBD_CONTROL). Either the IKBD_TX_POLL_MAX give-up arm survived into the target"
  echo "       build — a slow transmitter would then lose the command byte — or the core moved."
  awk "$IKBD_BODY_SCAN" "$DISASSEMBLY"; exit 1; }
echo "   $IKBD_SHIPPED conditional branch, against the capped control's $IKBD_CONTROL"

# THE CORES MAY ONLY READ A HARDWARE ADDRESS THE KIT MODELS, and this is the read half of the os_*
# census below. `hw_read8` used to be defined nowhere in this build, so a core that acquired a
# hardware read failed to LINK; zynaps_backend.c defines it now, for `ikbd_send_cmd`'s ACIA poll, and
# that link error is gone. Off target the kit REFUSES an address outside its seeded set and the
# harness throws the case away — but a core reading, say, $ff8260 through a bare literal is green
# there (the refusal tally is compiled out by -DOS_NO_REFUSAL_TALLY) and reads the real chip here.
# So every argument must be one of os.h's OS_HW_* names, which is what makes the address DECLARED.
echo ">> the cores read only hardware the kit models"
HW_READS=$(grep -rhoE '\bhw_read[0-9]+ *\( *[A-Za-z_0-9]+' "$REC/src" "$REC/include" \
           | sed 's/.*( *//' | sort -u || true)
UNDECLARED=$(echo "$HW_READS" | grep -v '^OS_HW_' || true)
[ -z "$UNDECLARED" ] || {
  echo "ERROR: a core reads a hardware address the kit's seeded READ model does not name:"
  echo "$UNDECLARED" | sed 's/^/         /'
  echo "       Off target that is a refusal; here it reads the real chip with no surface at all."
  exit 1; }
echo "   $(echo "$HW_READS" | grep -c . || true) hw_read site(s), all naming an OS_HW_* address"

# THE BIG-ENDIAN ACCESSORS MUST BE PLAIN LOADS. machine.h picks a native `*(uint32_t *)` on a
# big-endian target and byte assembly on the little-endian host; if the guard ever failed to fire,
# every field access in every core would compile to an `lsl #8` shuffle chain — a uniform ~4x
# slowdown and a 40% larger .PRG (class 1). The count is not zero, because a real shift-by-8 is an
# ordinary instruction; what would be diagnostic is HUNDREDS. Reported rather than gated, because
# the threshold is a guess and a guessed gate is worse than a printed number.
SHUFFLES=$(grep -c 'lsl.*#8' "$DISASSEMBLY" || true)
echo "   lsl #8 instructions: $SHUFFLES (hundreds would mean machine.h's big-endian arm did not fire)"

# ...and the arm itself, asked of the source rather than of the disassembly, so the number above has
# something to be read against.
$CC $CFLAGS -E -dM -x c /dev/null | grep -q '__ORDER_BIG_ENDIAN__' || {
  echo "ERROR: the m68k compiler does not define __ORDER_BIG_ENDIAN__ — machine.h's guard cannot"
  echo "       have selected the native accessors."; exit 1; }

# ---- what the SOURCE says, asked of the source --------------------------------------------------

# THE CORES ARE COMPILED UNCHANGED, and this measures it in the two ways it could stop being true.
# If either did, the differential .so and this .PRG would stop being the same program and `make
# test`'s green would stop saying anything about what runs here. (Joust and Wonder Boy each carry a
# check of this shape, for the same reason.)
#
# Asked of INCLUDES and MACRO NAMES rather than of any identifier, on purpose: `../src`'s own
# comments discuss `hw_write8` and the target build at length — that is the seam being documented
# where it lives — so a grep for identifiers would red on prose. An `#include` line and a `-D` name
# are code either way.
echo ">> the cores take nothing from this directory"
SHIM_HEADERS='tos\.h|zynaps_target\.h'
LEAKS=$(grep -rlE "^[[:space:]]*#[[:space:]]*include[[:space:]]*\"($SHIM_HEADERS)\"" \
        "$REC/src" "$REC/include" || true)
[ -z "$LEAKS" ] || { echo "ERROR: a core includes a shim header:"; echo "$LEAKS"; exit 1; }

# ...and the build's own `-D` names, which exist nowhere but here. A core reading one would compile
# differently in the two builds while looking identical in both.
TARGET_MACROS='PROGRAM_BYTES|ZY_LOAD_BASE|ZY_FAULT_PEN|ZY_SMOKE_VBLS'
LEAKS=$(grep -rlE "\b($TARGET_MACROS)\b" "$REC/src" "$REC/include" || true)
[ -z "$LEAKS" ] || { echo "ERROR: a core reads a target-only macro:"; echo "$LEAKS"; exit 1; }

# THE os.h SHADOW'S CENTRAL CLAIM, MEASURED RATHER THAN ASSERTED IN PROSE. That file replaces FOUR
# kit helpers and pulls the rest in through `#include_next`, so every OTHER `os_*` — os_bconstat,
# os_bconin, os_giaccess, os_random, os_fwrite — is still the deterministic MODEL, compiled into the
# .PRG and answering out of an in-image register file. That is safe only while no core calls one,
# and the shadow's own header says so as a grep somebody ran once. This is that grep, every build.
#
# A core that reached os_bconin would LINK CLEANLY and read a real keypress out of a fabricated
# model, with -DOS_NO_REFUSAL_TALLY having compiled away the tally that would have counted it: no
# link error, no record field, no surface. README's own M2 plan ports the routines that would do it.
# `os_refused` is on this list for a different reason from the other four: it is not replaced by
# shim_include/os.h but by the KIT's own `-DOS_NO_REFUSAL_TALLY` arm, which compiles it to an inline
# identity (tools/recreate_kit/include/os.h). Its one core caller is `ikbd_send_cmd`'s give-up arm,
# which that same macro compiles away — see shim_include/tos.h on why the spin is unbounded here.
REPLACED_OS_HELPERS='os_fopen|os_fread|os_fclose|os_super|os_refused'
OS_USED=$(grep -rhoE '\bos_[a-z_0-9]+' "$REC/src" "$REC/include" | sort -u || true)
OS_MODELLED=$(echo "$OS_USED" | grep -vE "^($REPLACED_OS_HELPERS)$" || true)
[ -z "$OS_MODELLED" ] || {
  echo "ERROR: a core calls a kit os_* helper this build does NOT replace, so it would run against"
  echo "       the deterministic model on real hardware. Replace it in shim_include/os.h, or say"
  echo "       why the model is right on target:"
  echo "$OS_MODELLED"; exit 1; }
echo "   the cores call $(echo "$OS_USED" | wc -l | tr -d ' ') os_* helper(s), all of them replaced"

echo ">> objcopy -> flat binary"
m68k-elf-strip --strip-debug "$BUILD/zynaps.elf"
m68k-elf-objcopy -O binary "$BUILD/zynaps.elf" "$BUILD/zynaps.bin"

echo ">> wrap -> GEMDOS .PRG"
"$PY" "$HERE/mkprg.py" "$BUILD/zynaps.elf" "$BUILD/zynaps.bin" "$BUILD/$PRG"

cp "$BUILD/$PRG" "$DISK/$PRG"
cp "$BUILD/$PRG" "$BUILD/ZYNAPS-$MODE.PRG"
# The ELF beside it, because the floppy mode's ANCHOR needs a symbol address and a .PRG has no
# symbol table: `smoke.py` reads `zy_anchor`'s offset out of this and adds the load address it
# finds in RAM. Per mode for the .PRG's reason — an edit to this script must not leave a stripped
# binary being read against another build's symbols.
cp "$BUILD/zynaps.elf" "$BUILD/zynaps-$MODE.elf"
ls -l "$DISK/$PRG" "$DISK/ZYNAPS.IMG"

# ---- the bootable floppy ------------------------------------------------------------------------
# LAST, so the image is built out of a drive that is already complete: mkfloppy.py takes the staged
# root above (the 62 data files plus ZYNAPS.IMG) and puts THIS .PRG in AUTO\ under the original's
# own name. It verifies the finished volume with tools/st_extract.py's reader and refuses an image
# whose files do not match what went in, so a bad write is a red here and not a black screen later.
if [ "$MODE" = "floppy" ]; then
  echo ">> bootable floppy"
  "$PY" "$HERE/mkfloppy.py" --prg "$BUILD/ZYNAPS-$MODE.PRG" --root "$DISK" \
        --out "$DISK/ZYNAPS.ST"
fi
