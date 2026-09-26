"""TIER 3 — what the recreate costs against what the ROM costs, function by function.

    make bench                  # from recreate/ — build the cores for the 68000 and print the table

Each row is ONE verified case, run twice on one instrument: the ORIGINAL's own machine code in place
at its `$fcxxxx` address, and the same C cross-compiled by `m68k-elf-gcc` with the shipped ROM
build's own flags (`atari/target.mk`), staged in free RAM inside the same post-boot snapshot.
`tools/recreate_kit/rom_bench.py` owns the mechanism and the SECOND DIFFERENTIAL that comes with it —
a row is printed only if the m68k build left the same image, the same return value, the same
callee-saved file and the same off-image traffic as the ROM did.

THE ROWS ARE NOT A LIST ANYBODY TYPED. They are `test_boot_snapshot.VERIFIED_CASES` — the project's
own register of every case a battery has verified, built from each battery's own case constructors —
run again with a cost attached. That is the whole design of this file: a second hand-written list of
entries, registers and pokes is exactly how a ratio comes to be a number about a case nobody proved,
and it drifts silently because both lists keep working. What this file adds is the one thing that
list cannot carry: HOW OUR C IS CALLED over the same case (`CALL` below), which is a fact about the C
signature and not about the ROM. Even the argument VALUES are decoded out of the frame the case
itself poked, so the two cannot disagree about what the call means.

`test/test_tier3.py` is the GATE over the same registry: every row at or under `TIER3_FUNCTION_BAR`
unless `PERF_ACCEPTED` carries it, and every pinned row still measuring what it was pinned at. That
file also refuses a verified case with NO row here. This file prints; that file decides.
"""
import argparse
import struct
import sys
from collections import namedtuple
from pathlib import Path

RECREATE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RECREATE.parents[2] / "tools"))     # reverse/tools — the shared recreate kit
sys.path.insert(0, str(RECREATE / "tools"))                # this project's own tools
sys.path.insert(0, str(RECREATE / "test"))                 # ...and the cases the differentials use

from recreate_kit import project                           # noqa: E402
project.load(RECREATE)

from recreate_kit.rom_bench import RomBench                # noqa: E402
from harness import addrs, emu                             # noqa: E402  (binds the kit)
import abi                                                 # noqa: E402
# THE REGISTER OF VERIFIED CASES, and with it every battery whose constructors built one. Importing a
# test module from a bench script is deliberate: that module is where this project keeps the list of
# what it has verified (it is the list the snapshot mask is checked against), and a Tier 3 row is a
# verified case with a cost attached. A copy here would be a second answer to "what is verified".
import test_boot_snapshot                                  # noqa: E402
import test_xbios_supexec as supexec                       # noqa: E402
# ...and the TRANSCRIPTION cases, which are the same idea for the one routine that is not C:
# `src/bios/trap.S`, the exception handler every BIOS and XBIOS call is entered through. They
# are kept in `test/trap.py` rather than in `VERIFIED_CASES` because they are proved through a
# different relation — see `RomBench.measure_transcription` and `measure` below.
import trap                                                # noqa: E402
# ...and the INTERRUPT HANDLERS' case shape, for the same reason: a handler's case is
# entered at a TRAMPOLINE in the staging band rather than at the routine, so getting from
# a row's entry back to the ROM address it is about is this module's map to give
# (`test/isr.py`).
import isr                                                 # noqa: E402
# ...and the four ISR batteries, for their TRANSCRIPTION cases — `src/bios/isr.S`, the stubs a
# shipped ROM installs in the four vectors. They live beside each handler's own registered cases
# (both are built from ONE spec, so the two rows are two relations over one verified run) rather
# than in a list here, which is `trap.CASES`' arrangement one file per handler.
import test_bios_hbl                                       # noqa: E402
import test_bios_ikbd                                      # noqa: E402
import test_bios_timerc                                    # noqa: E402
import test_bios_vbl                                       # noqa: E402
# ...and the GEMDOS wave's own shared module, for two things this file cannot get anywhere else: the
# trap #1 entry's TRANSCRIPTION rows and their label (`gemdos.TRANSCRIPTIONS`/`LABELS`, `trap.py`'s
# arrangement under GEMDOS names), and the SLICE trampoline a dispatcher row is entered at, because
# `$fc973e` is inside a frame nothing can enter directly (`gemdos.ROUTINE_OF_TRAMPOLINE`).
import gemdos                                              # noqa: E402
# ...and GEMDOS wave 2's process module, for the SECOND slice trampoline: `Pexec` past the
# termination record it arms is entered through a stub of its own, which costs two instructions
# where the dispatcher's costs three (`SLICE_ENTRY_COST` below).
import gemdos_process                                      # noqa: E402

# THE BAR, named once and read by both this file and the gate. A function above it is a perf item
# rather than a verified row (../README.md, "Tier 3 — performance"): it is brought under by the
# levers the game recreates used — a hand-asm twin pinned to the C core — or it is accepted below,
# in writing, with its measured cost.
TIER3_FUNCTION_BAR = 1.10

# How far a PINNED ratio may move before it is a change somebody has to make on purpose. Wide enough
# that it is never noise — nothing here is sampled, both sides are counted instruction by instruction
# by the same deterministic CPU model, so a row that moves at all moved because the code did — and
# narrow enough that losing a handful of cycles off a 200-cycle routine reddens.
RATIO_TOLERANCE = 0.02

# Rows whose measured ratio is PINNED: {(symbol, case): (the ratio when it was written, why)}.
#
# An entry is a decision on the record, not a silencer, and it does two jobs at once:
#
#   * a row ABOVE the bar is ACCEPTED by its entry — without one the gate reds — and the entry says
#     what it measured and why that is the right trade;
#   * a row UNDER the bar is pinned because its cycle count is the ONLY surface something in it has.
#     `xbios_giaccess` is the case: its interrupt bracket (`ipl.h`) is a no-op off target, so every
#     Tier 1 differential stays green if it vanishes, and the 46 cycles it costs are what say it is
#     there.
#
# `test_tier3.py` refuses a stale entry: one naming no row, one that has drifted, and one recorded
# above the bar whose row has since come back under it.
# WHAT THE ROWS ABOVE THE BAR HAVE IN COMMON, said once so seventeen entries need not each say it.
# Three mechanisms cover all of them, and none is a defect in a reconstruction:
#
#   (A) THE IMAGE POINTER. Every core takes `uint8_t *image` and loads it out of the frame —
#       `moveal %sp@(4),%a0`, 12 cycles — where the ROM reaches the same memory through the
#       dispatcher's own `suba.l a5,a5` and an `(a5)` displacement, at no cost at all. On a routine
#       whose whole body is `move.l _drvbits,d0 / rts` that ONE load is the entire excess, and a
#       ratio is a poor instrument for it: +16 cycles reads as 1.50x. The structural lever, if this
#       is ever worth a wave, is the SHIPPED build rather than the C — a ROM that compiles the cores
#       with the base fixed at 0 pays none of it, and would then need its own numerator.
#   (B) THE BIOS CHARACTER-DEVICE DISPATCH (`bios_bcon*`). The ROM's three instructions
#       `lsl.w #2,d0 / movea.l 0(a0,d0.w),a0 / jmp (a0)` are an indirect jump into the driver; the C
#       reads the same vector and must then decide WHICH driver it is, which `-fno-jump-tables` (a
#       ROM build's flag: a jump table is a relocation) compiles to a compare chain. The `no driver`
#       arm walks all of it and then computes by hand the D0 the ROM got free out of its own `lsl.w`.
#   (C) XBIOS `Cursconf`'s ARM SELECTION. `jmp TABLE(pc,d0.w)` against a bounds test, the same table
#       read (the C reproduces the displacement the ROM leaves in D0 — see `cursconf.c`) and a
#       compare chain, for the same reason as (B).
#
#   (D) THE CALLER'S D0 AS AN ARGUMENT. A ROM routine that writes only D0's LOW WORD (`move.w
#       <ea>,d0`) leaves the caller's high half, and the C says so by taking that D0 as a parameter
#       and returning the whole register — which GCC compiles to `move.l 4(sp),d0 / clr.w d0 /
#       or.w d1,d0`, three instructions and ~28 cycles where the ROM's one `move.w` WAS the whole
#       result path. The alternative is a `uint16_t` core, which would agree with a reconstruction
#       that had cleared the half the ROM preserves (`kbrate.c`), so this is the cost of being able
#       to say the true thing at all.
#   (E) AN I/O ADDRESS THE ROM KEEPS IN AN ADDRESS REGISTER. `lea $ffff8240,a0` plus an indexed
#       `0(a0,d1.w)`, against GCC computing the whole address in D0 (`addi.l #$ff8240,d0`, 16
#       cycles) and moving it to A0. The C names the register by its 24-bit address, which is what
#       makes the declared I/O map and the write ledger able to compare it at all.
#   (F) A BYTE READ WIDENED TO A LONGWORD. The ROM clears the register once BEFORE the byte move
#       (`moveq #0,d0`, 4 cycles); GCC spells the same widening AFTER it (`andi.l #255,d0`, 16).
#   (G) A BYTE THE ROM READS OUT OF ITS OWN ARGUMENT FRAME. `move.b 9(sp),$ffff8201` takes bits
#       23..16 of a longword argument for nothing, because the frame is memory and the byte has an
#       address; the C is handed the longword as a VALUE and extracts it with shifts.
#   (J) `movep.l`, WHICH C HAS NO FORM FOR. The 68901 sits on every other byte of the bus, and the
#       68000 has one instruction for reading four such registers into a longword — which is how
#       `Rsconf` fetches the configuration it reports. Off target and on, the C is four `io_read8`
#       calls and the shifts and ORs that pack them, because each byte is a DECLARED read of its own
#       address and the ordered ledger compares them one at a time (`hw.h`, Phase 15): one
#       instruction becomes ten. The lever, if it is ever worth one, is a hand-asm twin pinned to
#       the C core by the twin differential, exactly as the game recreates use.
#   (K) THE RAM-VECTOR BASE REGISTER. Every routine TOS installs in a system vector is entered with
#       A5 = 0 — the ROM's handlers establish it once with `lea 0,a5` and index low RAM and the I/O
#       page off it (`$fc2a0c`'s first instruction is `lea $c76(a5),a0`). `src/bios/isr.S` spells
#       that zero as the PUSHED IMAGE ARGUMENT instead, which the C body needs and the vector does
#       not, so `include/staged_call.h` pins A5 as an OPERAND of every vector call: one
#       `suba.l %a5,%a5`, 8 cycles, per call. It is a CORRECTNESS guarantee with no Tier 1 surface —
#       the cross-compiled `isr_acia` spun to the oracle's cap without it in the build that found
#       it, and passes by coincidence in a build where GCC happens to hold the image pointer in A5 —
#       so the rows that carry it are PINNED: deleting it leaves every differential green and moves
#       them to the ratios each entry names.
#
#       THE DEEPER LEVER IS UNMEASURED AND RECORDED RATHER THAN TAKEN: `-ffixed-a5` in
#       `atari/target.mk` plus the ROM's own `suba.l a5,a5` in each `src/bios/isr.S` stub would set
#       the register ONCE per interrupt instead of once per call — zero per-call cost — at the price
#       of one fewer allocatable address register in every core the shipped build compiles. What is
#       in the tree is the interim: correct everywhere, paid per call, and priced by these rows.
#
# Every entry below states the measured ratio and the absolute cycles, because on routines this small
# the absolute number is the one a reader can act on.
PERF_ACCEPTED = {
    ("xbios_giaccess", "read"): (
        0.60, "includes the interrupt bracket the ROM's own `ori.w #$700,sr` makes (ipl.h), which "
              "the Tier 1 differential cannot see: the oracle enters at IPL 7 and reports no SR, so "
              "this cycle count is the whole surface the mask has"),
    ("xbios_giaccess", "write"): (
        0.74, "the same bracket, over the write path's extra port access — see the row above"),

    # (A) alone, on a trap leaf, is not written down at all any more: those rows are admitted by
    # THE LEAF RULE below, which measures the excess against the dispatched call the machine really
    # makes instead of against a fragment nobody executes on its own.
    ("xbios_iorec", "xbios_iorec"): (
        1.48, "(A) plus the ROM's `lea IOREC_TABLE(a5),a0` / indexed load against a C bound and a "
              "shift: 58 -> 86 cycles, four instructions to eight"),
    ("xbios_kbrate", "read"): (
        1.80, "(A) plus the two `tst.w` the C makes of arguments the ROM tests as it stores them: "
              "50 -> 90 cycles, four instructions to eight"),
    ("xbios_kbrate", "write"): (1.28, "the same, over the arm that stores both: 116 -> 148 cycles"),

    # (B) — the character-device dispatch the C must decide rather than jump through.
    ("bios_bconstat", "console ring empty"): (1.26, "(B) 138 -> 174 cycles, 14 instructions to 18"),
    ("bios_bconstat", "console ring ready"): (1.29, "(B) 136 -> 176 cycles, 13 instructions to 18"),
    ("bios_bconstat", "no driver"): (
        1.88, "(B) the arm that pays the WHOLE compare chain and then computes the dispatch's own "
              "`lsl.w` result by hand: 86 -> 162 cycles, 7 instructions to 16"),
    ("bios_bconin", "console"): (1.18, "(B) 336 -> 398 cycles, 29 instructions to 37"),
    ("bios_bconin", "midi"): (1.16, "(B) 344 -> 400 cycles, 30 instructions to 39"),
    # BIOS wave 3 brought Bcostat's whole table into reach — four drivers a DECLARED hardware byte
    # made runnable (TRAP_MODEL.md, Phases 7 and 15) — and (B)'s compare chain grew by the four
    # entries that took: every row here pays it in full before it reaches its own arm, so the whole
    # table moved together and the console's row moved most, being the one with no body of its own.
    # The lever is the same as (B)'s everywhere else and is a wave of its own: a shipped ROM builds
    # these with a jump table, which is what the ROM's `jmp (a0)` really is.
    ("bios_bcostat", "console"): (
        1.84, "(B) over a driver whose whole body is `moveq #-1,d0`, so the dispatch IS the routine: "
              "90 -> 166 cycles, 8 instructions to 17. It was 1.44 over a chain of two drivers; the "
              "chain is six now, and this arm is the one that pays it with nothing to amortise it "
              "against"),
    ("bios_bcostat", "printer"): (
        1.55, "(B) over a body that is one declared read and a `btst`: 128 -> 198 cycles. The read "
              "itself is free on both sides — the MFP answers a byte — so the excess is the chain"),
    ("bios_bcostat", "ikbd"): (
        1.46, "(B) over the IKBD 6850's TDRE, the same one-read body: 126 -> 184 cycles"),
    ("bios_bcostat", "midi"): (
        1.44, "(B) over the MIDI 6850's, which differs from the row above only in which model serves "
              "the byte — a NAMED slot against a declared one — and costs two cycles less for it: "
              "126 -> 182"),

    # ...and `Bconout` (BIOS wave 3), which is the same dispatch over SIX drivers that do work. The
    # two rows that need no entry are the two whose driver is big enough to swallow it: `ikbd` at
    # 1.01 (the 951-iteration settle the 6301 is owed) and `printer` at 1.05 (the whole YM2149
    # send). Everything else here is (B) over a body of a handful of instructions, or the console.
    ("bios_bconout", "midi"): (
        2.76, "(A)+(B): 142 -> 392 cycles over a driver whose whole body is a status read and a "
              "data write — the dispatch chain IS the routine"),
    ("bios_bconout", "no driver"): (
        3.63, "(B) alone, over a driver that is a bare `rts`: 76 -> 276"),
    ("bios_bconout", "printer held off"): (
        1.88, "(A)+(B) over the give-up arm, which is two longword reads and a store: 194 -> 364"),
    ("bios_bconout", "rs232 ring only"): (
        1.90, "(A)+(B): 302 -> 574. The ring put is six field accesses the ROM makes off one `lea`"),
    ("bios_bconout", "rs232 primed"): (
        1.44, "722 -> 1040, and it includes the `ipl.h` bracket around the prime that Tier 1 cannot "
              "see (src/xbios/gibit.c's argument)"),
    ("bios_bconout", "console escape state"): (
        3.27, "(A)+(B) over a state-machine arm whose whole body is `move.l a0,$4a8`: 212 -> 694"),
    ("bios_bconout", "console line feed"): (
        2.24, "716 -> 1604: the cursor lock, the cell arithmetic and the unlock, each of which is a "
              "handful of field accesses off the ROM's one `lea $2994,a4`. It was 2.21 (1580) until "
              "`cell_address`'s two clamps became the N-flag test the ROM makes of them rather than "
              "the signed compare they had been transcribed as — 24 cycles, and a correctness fix "
              "(`m68k_idioms.h`, `word_difference_is_negative`)"),
    ("bios_bconout", "console glyph"): (
        1.93, "2268 -> 4388 over a 32-byte blit: the ROM's inner loop is `move.b (a2),(a3) / "
              "adda.w / adda.w / dbf` and GCC will not give back the `dbf`"),
    ("bios_bconout", "console glyph with the cursor"): (
        1.71, "the same body plus the cell inversion, 3452 -> 5916 — the inversion is the half that "
              "ports well"),
    ("bios_bconout", "raw console"): (
        1.85, "the glyph row without the state dispatch: 2220 -> 4114"),
    # ...and the two SCREEN rows, which are PINNED UNDER THE BAR rather than accepted: their loops
    # are spelt as the ROM's own instructions and nothing in Tier 1 can see the shape, only the
    # bytes. The cycle count is the whole surface those spellings have.
    ("bios_bconout", "console scroll"): (
        1.03, "180,794 -> 185,754 moving 30 KB. PINNED, not accepted: the copy is now the ROM's own "
              "`move.l (a1)+,(a0)+` four times under a `dbra`, which is what the four unrolled "
              "copies and the 16-bit post-tested pass counter in `conout_glyph.c` are for — written "
              "as a counted inner loop GCC kept a count, a compare and a branch per longword and "
              "this row read 2.03 (367,470); before the CURSOR_BARRIERs, 3.22. Every one of those "
              "spellings is invisible to the differential, which compares the bytes moved and not "
              "the instructions that moved them, so this number is their only surface"),
    ("bios_bconout", "console clear to end of screen"): (
        1.49, "166,492 -> 247,614 filling 30 KB. Three levers, each measured: a group the run covers "
              "WHOLLY is a store and not a read-modify-write (8.17x before that), the row walks as a "
              "POINTER (2.24x with it), and the middle run is now one loop PER PLANE COUNT, so the "
              "four-plane arm is the ROM's own `move.l (a2)+ / move.l (a2)+ / dbf` rather than a "
              "counted loop inside a counted loop. WHAT IS LEFT is the two EDGE groups of every scan "
              "line: the ROM masks a whole group with `and.l`/`or.l` pairs where this fills it a "
              "word at a time. That is the next lever and it is not taken"),

    # (C) — Cursconf's arm selection, and the widest row here.
    # (J) — `movep.l`, and the interrupt mask the differential cannot see.
    ("xbios_rsconf", "report"): (
        2.03, "(J) 220 -> 446 cycles, 18 instructions to 37. The whole of it is the `movep.l` (one "
              "instruction, four declared reads and the packing) and the six argument words read "
              "out of the caller's block where the ROM tests them in place; the arm itself stores "
              "nothing. It also carries the `ori.w #$700,sr` the ROM never restores (ipl.h), which "
              "no Tier 1 case can see"),
    ("xbios_rsconf", "store four"): (
        1.72, "(J) the same, over the arm that stores all four USART registers: 292 -> 502 cycles"),
    ("xbios_rsconf", "baud"): (
        1.11, "(J) and (A) over the arm that reprograms timer D: 1436 -> 1594 cycles, 116 "
              "instructions to 140. The same `movep.l` the report row pays 2.03 for — four "
              "`io_read8` calls of their own declared addresses where the 68000 has one instruction "
              "— and the image-pointer load beside it, DILUTED here by the hundred-odd instructions "
              "of the shared timer programmer ($fc25b0) this arm runs through, whose cost is "
              "measured inside this row and `Xbtimer`'s and nowhere else. The excess is 158 cycles, "
              "far past the leaf rule's 40, so it is written down rather than ruled on"),

    # ...and one row pinned UNDER the bar, because a cycle count is all the surface it has.
    ("xbios_ikbdws", "xbios_ikbdws"): (
        1.00, "the IKBD sender's 951-iteration SETTLING DELAY, which the Tier 1 differential cannot "
              "see: it touches no memory, no compared register and no chip, so deleting it leaves "
              "every case green and the 6301 short of the gap it needs — this row is its whole "
              "surface. 83,976 -> 83,994 cycles for two bytes, nearly all of it that loop. What the "
              "6301 is owed is ELAPSED TIME, so the delay is a FLOOR and a counted C loop that made "
              "the same 951 passes more cheaply would not meet it: measured at 0.86 (72,598 cycles, "
              "a seventh of the gap missing), which is why the target build spells the loop as the "
              "ROM's own `bsr`-to-an-`rts` under `dbf` — `src/xbios/acia.c`. The 18 cycles over are "
              "the one `bra.s` that jumps the `rts`. `Initmous`'s two rows send through the same "
              "loop and moved with it, to 1.00"),

    ("xbios_cursconf", "blink"): (
        1.65, "(C) 104 -> 172 cycles, down from 238: the jump-table read is now made in the arm "
              "that uses it rather than above the switch. What is left is the bounds test, that "
              "read, and a compare chain to one of EIGHT arms where the ROM's `jmp TABLE(pc,d0.w)` "
              "reaches any of them in three instructions"),
    ("xbios_cursconf", "get rate"): (
        1.33, "104 -> 138 cycles, up from 0.90x, and the whole of it is that the two arms that DRAW "
              "made this routine a NON-LEAF: GCC opens an outgoing-argument frame on every path and "
              "the chain grew from six arms to eight. The ROM pays neither. The alternative was the "
              "halt those two arms used to be"),
    ("xbios_cursconf", "hide"): (
        1.37, "1278 -> 1752, the dispatch above plus the cursor inversion"),
    ("xbios_cursconf", "show"): (
        1.47, "1408 -> 2066, the same with the forced-visible arm"),

    # ---- the XBIOS screen and sound leaves (BIOS wave 2) ----
    # The two GI-bit rows are UNDER the bar and pinned for `xbios_giaccess`'s reason: their OUTER
    # interrupt bracket is a second one, around BOTH `Giaccess` calls rather than inside each, and it
    # is what makes the port-A read-modify-write atomic against the 200 Hz driver's own `$ff8800`
    # writes. Off target it is a no-op, so deleting it leaves every Tier 1 case green and moves only
    # these numbers.
    ("xbios_ongibit", "xbios_ongibit"): (
        0.90, "includes the OUTER interrupt bracket spanning both Giaccess calls (ipl.h), which the "
              "Tier 1 differential cannot see: the oracle enters at IPL 7 and reports no SR, so this "
              "cycle count is the whole surface that bracket has. 664 -> 604 cycles, of which 16 are "
              "(D) in its cheapest form: the `movem` pair gives the caller's D0 back, so the core "
              "takes it and returns it, and GCC spells the whole pass-through as one `move.l "
              "4(sp),d0` (0.88 before that argument, measured)"),
    ("xbios_offgibit", "xbios_offgibit"): (
        0.90, "the same bracket and the same pass-through, over the `and.b` twin — see the row "
              "above"),

    # ...and `Vsync`'s two rows, UNDER the bar and pinned for the same reason a third time. Its
    # unmask is the routine's TERMINATION rather than its manners — at IPL 7 the blank it waits for
    # is never taken — and off target `ipl.h` is a no-op, so deleting the bracket leaves every Tier 1
    # case green. These cycles are the only surface it has. The two rows differ in how many times the
    # wait goes round, which is the ONE thing the schedule's `nth` decides (`test_xbios_vsync`).
    ("xbios_vsync", "the blank at spin 1"): (
        0.97, "includes the interrupt bracket (`ipl.h`) the ROM makes with `move.w sr,-(sp)` / "
              "`andi.w #$f8ff,sr` and undoes with `move.w (sp)+,sr`, which the Tier 1 differential "
              "cannot see. Under 1.00 because the target bracket keeps the entry SR in a register "
              "where the ROM pushes and pops it: 156 -> 152 cycles over one iteration of the wait"),
    ("xbios_vsync", "the blank at spin 4"): (
        0.92, "the same bracket over four iterations, where the loop rather than the entry is most "
              "of the cost: 252 -> 236. The pair is what says the bracket is priced at more than "
              "one arrival count — see `test_xbios_vsync.PRICED_SPINS`"),

    # (F) — and this is the only row in the table where the byte widening is the whole difference.
    ("xbios_physbase", "xbios_physbase"): (
        1.12, "(F) 138 -> 150 cycles at the SAME seven instructions: `andi.l #255,d0` after the byte "
              "load where the ROM's `moveq #0,d0` cleared the register before it, and those 12 "
              "cycles are the entire excess"),

    # (Dosound's two arms are (A)-only trap leaves, and the LEAF RULE below admits them.)

    # (A) + (D) — Setpalette WAS one of those leaves and is not one any more: it hands the caller's
    # D0 back, so its excess is no longer the image pointer alone and the rule must not be asked.
    ("xbios_setpalette", "xbios_setpalette"): (
        1.73, "(A) plus (D) over a routine that IS one store: 84 -> 116 cycles, 3 instructions to 5. "
              "The ROM's `move.l 4(sp),$45a / rts` touches no register, so the core takes the "
              "entering D0 and returns it — one `move.l 4(sp),d0`, 16 cycles, which on a 44-cycle "
              "body is the whole of the difference between this and the 1.36 it measured as a "
              "`void` core. A ratio is a poor instrument at this size; the absolute is 32 cycles"),

    # (A) + (G) + (D) — the screen base the ROM stores straight out of its frame, and the D0 it
    # gives back. The pass-through is 16 cycles on both arms, so the SHORTER one moves further.
    ("xbios_setscreen", "both bases"): (
        1.28, "(A) plus (G) plus (D): the C is handed the physical base as a VALUE and extracts bits "
              "23..8 with `move.l`/`clr.w`/`swap` and an `lsr.l` where the ROM stores 9(sp) and "
              "10(sp) as bytes, and it loads the entering D0 to hand back — 202 -> 248 cycles, 11 "
              "instructions to 19 (1.19 before that argument, measured)"),
    ("xbios_setscreen", "keep everything"): (
        1.24, "the same (A) and (D) over the arm that does nothing at all: three tests and an `rts` "
              "in the ROM, 130 -> 152 cycles, 8 instructions to 11. (G) is absent here — no store is "
              "made — so this row is the pointer load and the pass-through alone, 22 cycles of a "
              "90-cycle body (1.07 before that argument, measured)"),

    # (D) + (E) — the caller's D0 as an argument, and the palette base as an immediate.
    ("xbios_setcolor", "read"): (
        1.28, "(D) plus (E): 140 -> 168 cycles, 10 instructions to 14"),
    ("xbios_setcolor", "write"): (
        1.18, "the same two over the arm that stores: 160 -> 182 cycles, 11 instructions to 15"),

    # (A) + (D) — and together they are the widest pair in this wave.
    ("xbios_setprt", "write"): (
        1.59, "(A) plus (D) over a three-instruction routine: 108 -> 148 cycles, 6 instructions to "
              "10. Its neighbour `Dosound` pays only (A) and sits at 1.23 — the difference between "
              "them IS (D), measured"),
    ("xbios_setprt", "report only"): (
        1.80, "the same pair over the arm that only reports: 90 -> 130 cycles"),

    # ---- THE INTERRUPT HANDLERS (BIOS wave 2) ----
    # A handler is entered by the MACHINE, and two consequences run through every row below.
    #
    #   (H) THE MFP ACKNOWLEDGEMENT. Timer C and the ACIA handler each end by clearing their own bit
    #       of $fffa11, which the ROM does in ONE `bclr` and the reconstruction does as a declared
    #       read and a ledgered store (`include/xbios/mfp.h` carries the argument: the seven bits the
    #       instruction preserves are seven other channels, and a door whose read half is a
    #       fabricated 0 cannot hold them). Two bus accesses where the original makes one, on a
    #       routine whose whole fast path is four instructions.
    #   (I) THE ENTRY GLUE IS NOT IN THE CORE, and it moves a C row the OTHER way. The ROM's own
    #       `movem.l d0-a6,-(sp)` / `movem.l (sp)+,d0-a6` and its `rte` are the machine's contract
    #       rather than the routine's, and a C function has no register file to save — so the
    #       ORIGINAL's column carries them and a C core's does not.
    #
    #       IT IS ANSWERED, and the `... ISR entry` rows are the answer: `src/bios/isr.S` is what a
    #       shipped ROM installs in each vector — the ROM's own entry sequence around the C body —
    #       and its rows pay the `movem` pair on both sides, so their ratio is the two handlers' own
    #       cycles with no hole in it. Each handler therefore has two rows: the C CORE, where (I)
    #       still stands and a figure under the bar is under it partly for a reason that is not a
    #       saving, and the ENTRY, where nothing is missing from either column.
    #   (L) A VECTOR ROUTINE KEEPS TO NOTHING. `include/staged_call.h`'s `jsr` tells GCC that every
    #       data register and A0-A5 are gone across a call into `swv_vec`, `_vblqueue`, `scr_dump`,
    #       `etv_timer` or KBDVECS — because what runs there is RAM, and the ROM defends itself by
    #       hand at the same places (`movem.l d7/a0,-(sp)` around each queue slot, `suba.l a5,a5`
    #       after each group). GCC's answer is to save what it is holding around each call, which is
    #       the same defence in the same place and is not free: measured on the ACIA handler, whose
    #       body is two such calls and nothing else, it is +147 cycles on a 269-cycle core.
    #
    # Every figure below is NET of the entry observation, as the rows above are: the table prints
    # the oracle's raw counts and the ratio is computed from these. An `... ISR entry` row is net of
    # the staged caller both sides run as well (`isr.SHARED_ENTRY_COST`).
    ("isr_hbl", "a frame already masked"): (
        1.18, "(A) 68 -> 80 cycles, six instructions to seven: the C loads the image pointer AND "
              "the frame address out of its own frame, where the ROM's `2(sp)` is free"),
    ("isr_vbl", "the semaphore taken"): (
        1.27, "(A) 98 -> 124 cycles, 5 instructions to 11. The arm is three memory read-modify-"
              "writes in the ROM (`addq.l`, `subq.w`, `addq.w` straight to absolute addresses) and "
              "the same three through an image pointer here"),
    ("isr_vbl", "a quiet frame"): (
        0.97, "(I) 736 -> 716 cycles: UNDER the bar, and pinned because the reason is a hole rather "
              "than a saving — the original's column carries the `movem` pair this core has no "
              "register file for. It is also what says the body has not grown. The row WITHOUT the "
              "hole is `isr_vbl_entry / a quiet frame` below"),
    ("isr_vbl", "a monitor change"): (
        1.00, "PINNED, not accepted: the arm is 2001 passes of `dbf` doing nothing — the shifter "
              "settling — and a delay's only surface is its cost. Delete the loop and every Tier 1 "
              "case stays green (`src/bios/vbl.c`); this row is 20,840 cycles against 20,870. The "
              "RATIO is too coarse to hold the count on its own — a pass either way moves it by "
              "0.0005 — so `test_bios_vbl.py` pins the absolute number as well"),
    ("isr_vbl", "a frame with everything queued"): (
        1.14, "(A) and (L) over a blank that does everything at once: 2062 -> 2356 cycles. The "
              "queue walk and the dump hook are two staged calls, and the register saves GCC makes "
              "around them are the ROM's own `movem.l d7/a0` in another place"),
    ("isr_timer_c", "a divided-away tick"): (
        1.18, "(A) and (H): 102 -> 120 cycles, 5 instructions to 9. Three of the ROM's five are "
              "`addq.l`/`rol.w`/`bclr` straight to memory, and every one of them is a load, an "
              "operation and a store here"),
    ("isr_timer_c", "a serviced tick"): (
        1.08, "PINNED under the bar: (A), (H) and (L) spread over a tick that steps the sound "
              "driver, the auto-repeat and the OS vector come to 978 -> 1052 cycles. This is the "
              "routine that runs 200 times a second, so the pin is what says the body has not "
              "grown; the row a hand-asm twin would be measured against is its ENTRY below. It was "
              "1.06 (1040) until BIOS wave 3: the auto-repeat's injection at `$fc2c42` is a real "
              "call to `kbd_queue_key` now rather than the halt it was"),
    # ...and the ACIA handler's C core, which BIOS wave 3 moved over the bar with a CORRECTNESS pin
    # rather than a body: mechanism (K).
    ("isr_acia", "one pass"): (
        1.11, "includes the A5 = 0 pin at each of the two RAM-vector calls (mechanism (K)): 468 "
              "cycles against 424, of which 16 are the two `suba.l %a5,%a5`. PINNED rather than "
              "merely accepted — deleting the pin leaves all 30 cases of test_bios_ikbd.py green "
              "and moves this row to 1.04 (440 cycles), which is the whole of its surface"),
    ("isr_acia", "two passes"): (
        1.10, "the same pin over two passes — four vector calls, 646 cycles against 590. PINNED: "
              "without it, 1.03 (606). The pair with the row above says the pin is a RATE (8 cycles "
              "a call) and not a constant"),

    # ---- ...and the same four handlers as `src/bios/isr.S` installs them (BIOS wave 2) ----
    # No (A) and no (I): the image base is a pushed 0 where the ROM zeroes A5, and both columns pay
    # the ROM's own `movem` pair. What is left in these rows is the C BODY against the ROM's inline
    # one, plus the `pea`/`jsr`/`addq` of calling it at all — about 56 cycles — and (L).
    #
    # THE LEVER FOR ALL FOUR IS ONE THING: a hand-asm body, pinned to the C core by the same twin
    # differential the game recreates use. That is a wave of its own and it is the timer C row that
    # earns it first, at 200 Hz.
    ("isr_vbl_entry", "a quiet frame"): (
        1.23, "736 -> 908 cycles. The body is the monitor follower, the cursor blink and the "
              "floppy gate, none of which does anything on a quiet blank — so this row is very "
              "nearly the C body's own prologue and the call that reaches it"),
    ("isr_vbl_entry", "a frame with everything queued"): (
        1.24, "2062 -> 2548 cycles over a blank thirty times the size of the quiet one above: the "
              "palette move, the screen base, the queue walk and the dump hook. (L) is most of it. "
              "Re-pinned from 1.23 (2536) in BIOS wave 3, when `src/bios/vbl.c` moved under it"),
    ("isr_timer_c_entry", "a serviced tick"): (
        1.33, "(H) and (L): 978 -> 1296 cycles. The acknowledgement is the ROM's own `bclr` in this "
              "stub, so what is left is the C body — the Dosound step, the auto-repeat countdowns "
              "and the register saves GCC makes around the `jsr` into `etv_timer`. It was 1.31 "
              "until BIOS wave 3, for the C row's reason: the auto-repeat injection is a real call "
              "now"),
    ("isr_acia_entry", "one pass"): (
        1.71, "(H) and (L), and this handler is nothing else: its body is two staged calls and an "
              "acknowledgement. 384 -> 656 cycles, of which +147 is the clobber list alone "
              "(measured: the same core was 269 cycles before `staged_call.h` stopped promising "
              "that a routine in a RAM vector keeps to the C ABI). +28 cycles since the A5 pin "
              "landed (mechanism (K)); 752 against 480 as the table prints them. Without the pin, "
              "1.64"),
    ("isr_acia_entry", "two passes"): (
        1.52, "THE SAME EXCESS as the row above, over an entry that is 166 cycles longer on "
              "BOTH sides: 550 -> 834. The handler's loop is free — a second pass costs the two "
              "builds exactly the same — so the excess this row carries is the one-time one the row "
              "above measures, amortised, and the ratio falls because the entry grew rather than "
              "because anything improved. The lever is the same hand-asm body, and the two rows now "
              "say between them that it would buy a constant, not a rate. 930 against 646 as the "
              "table prints them; without the A5 pin (mechanism (K)), 1.44"),
    # ...and the two REAL-VECTOR cases, which price EXACTLY the same thing the two rows above do,
    # amortised over a chain that does real work. BOTH COLUMNS RUN THE ROM'S CHAIN here, and that is
    # worth saying plainly: the captured machine's own `$fc29fc`/`$fc2a0c` are left in KBDVECS, and
    # the cross-compiled `isr_acia` jumps through those slots exactly as the ROM's handler does — so
    # `acia_service.c` and `keyboard.c` never execute under the recreate's column. What these rows
    # measure is the handler's own bracket, its loop, its A5 pins and its acknowledgement, over a
    # denominator the ROM chain makes large. The six cores' own cost is in their own rows.
    ("isr_acia_entry", "real vectors, a mouse packet"): (
        1.12, "the handler's bracket over a three-pass loop assembling a packet: 2880 cycles against "
              "2584. The excess is the same +296 the two rows above carry — the movem clobber list "
              "plus six A5 pins over three passes (mechanism (K)) — against a denominator the ROM's "
              "own service routines fill, which is why it reads as 1.12 where the empty entry reads "
              "as 1.71. Without the pin, 1.10"),
    ("isr_acia_entry", "real vectors, a keystroke"): (
        1.18, "one pass of the same chain, the same bracket: 1908 against 1636. Without the pin, "
              "1.16"),

    # ---- THE ACIA INPUT CHAIN, reached through KBDVECS (BIOS wave 3) ----
    # Five rows, and they exist because the two above cannot price them: a row whose original and
    # recreate columns run the SAME ROM routines says nothing about our C. These enter each core at
    # its own address, and between them they carry (A), (L) and one more:
    #
    #   (M) A ROUTINE WHOSE ARGUMENTS ARE ALREADY IN REGISTERS. Nothing here is called by a C
    #       caller: the ACIA handler jumps through a KBDVECS slot, `acia_take_byte` falls into the
    #       scancode arm, and timer C's auto-repeat jumps into the key path — so every one of these
    #       is entered with its arguments in hand, the byte in D0 and the record in A0. Our C takes
    #       the same values as PARAMETERS, so the m68k ABI builds a frame the callee then reads back:
    #       two or three `move.l n(sp),Rn` where the ROM had them already. It is (A) with more than
    #       one argument, and on bodies this small it is most of the excess.
    ("midi_acia_service", "a byte"): (
        1.40, "(A) and (L): 322 -> 450 cycles at 22 instructions against 23. The body is a status "
              "read, a data read and ONE call through a KBDVECS slot, and `staged_call.h` tells GCC "
              "that call keeps to nothing — so GCC's own `movem.l` pair saves more of the file than "
              "the ROM's `movem.l d2/a0-a2`, at the same instruction count and 128 more cycles"),
    ("ikbd_acia_service", "a packet's last byte"): (
        1.75, "the same two over the arm that does the most — the descriptor read, the packet fill "
              "and the dispatch through the slot the descriptor names: 618 -> 1080 cycles, 47 "
              "instructions to 65. TWO calls rather than one (`acia_take_byte` and then the packet "
              "vector), so (L)'s save is paid twice, and (M) on top: `acia_take_byte(image, iorec, "
              "acia_base)` is a three-argument frame where the ROM's `bsr` had A0 and A1 in hand"),
    ("midi_queue_byte", "one byte into the ring"): (
        1.53, "(A) and (M) ALONE, which makes this the cleanest measurement of (M) in the table: no "
              "call, no chip, and a body that is six field accesses off one `lea` in the ROM. "
              "116 -> 178 cycles, 10 instructions to 14 — the image pointer and two register "
              "arguments, read back out of a frame the caller had to build"),
    ("kbd_scancode", "a key"): (
        1.61, "(A), (M) and one more: the ROM FALLS INTO `$fc2c42` where the C makes a CALL of it, "
              "so the key path's three arguments are pushed and read back a second time. 802 -> "
              "1288 cycles over the arm an ordinary letter takes — nine `cmpi.b`, the auto-repeat "
              "arming, and then the whole of the row below"),
    ("kbd_queue_key", "a key"): (
        1.85, "(A) and (M) over the three `Keytbl` reads and the ring put: the ROM indexes all of it "
              "off the A0 and D0 it was entered with, and every one of them is an argument load "
              "here. 520 -> 964 cycles, and it is the widest ratio of the five because its body is "
              "small enough — a table read and a four-byte store — for the marshalling to be a "
              "third of it"),
    ("isr_vbl_entry", "a monitor change"): (
        1.01, "PINNED, not accepted, for the C row's reason one line up: 20,870 -> 21,032 cycles "
              "is the shifter settling, and a delay has no surface but its cost"),

    # ---- the GEMDOS RAM-ONLY LEAVES (GEMDOS wave 1) ----
    ("gemdos_fsetdta", "gemdos_fsetdta"): (
        1.17, "(A)+(D), and nothing else: 132 -> 148 cycles is the image pointer loaded off the "
              "frame plus the ENTRY D0 the ROM never writes, which the C takes as a third argument "
              "and loads from the frame too. The ROM's whole body is "
              "`link a6,#-4 / move.l 8(a6),$20(a0)`"),

    # ---- the GEMDOS CHARACTER DEVICES (GEMDOS wave 1) ----
    # NO ENTRY, and that is the wave's own result rather than an omission. These fifteen leaves each
    # reach the BIOS, and the target build takes the ROM's own `trap #13` to do it
    # (`src/gemdos/console.c`), so both columns carry the trap, the BIOS dispatcher and the driver.
    # Every one of the 60-odd rows then lands between 0.60x and 1.01x — where the direct call they
    # used to make had put twenty-three of them over the bar, on mechanism (B) paid once per BIOS
    # call with no trap on our side to cover it. The entries that accepted those are deleted rather
    # than re-pinned: `test_no_pinned_ratio_is_stale` reds on an acceptance whose row has come back
    # under the bar, which is what caught them.

    # ---- the PROCESS group (GEMDOS wave 2) ----
    # ONE entry out of the wave's seventeen priced rows; everything else in the file-system and
    # process groups lands at or under 1.04. `gemdos_resync_clock` was accepted here at 1.18 on a
    # rationale that blamed the ledger — "two `movep`s and a loop become 42 calls" — which was true
    # of the calls and false about the excess: what cost the cycles was the two digit buffers kept
    # as IMAGE OFFSETS and swapped each pass, which made `image + offset` a per-digit recomputation
    # and `read_clock_digits` an out-of-line six-register call. Respelt as `uint8_t *`
    # (`src/gemdos/process.c`) the row measures 1.04 with the same reads in the same order, so the
    # acceptance is DELETED rather than re-pinned — `test_no_pinned_ratio_is_stale`'s own rule.
    ("gemdos_pexec", "a refused mode"): (
        1.79, "(A), at the size where a ratio is a poor instrument. The whole routine on this arm "
              "is two `tst.w 8(a6)` and a `moveq #-32,d0` — 104 cycles; our C is handed an image "
              "pointer and four arguments, and copies the three pointers into its own frame before "
              "the mode test because the file lookup's call must keep them alive — three hoisted "
              "`move.l` spills of about 84 cycles, which is about the whole excess of 82 (78 before "
              "the lookup existed; splitting the "
              "admitted modes into a function of their own measured WORSE, the sibling call "
              "reloading all four). The structural lever is (A)'s: a shipped build with the base "
              "fixed at 0."),

    # ---- the DISPATCHER's own arms (fs wave 3) ----
    # ONE entry. The device arm's short rows (one byte, a count of 0 or of 64 KB, `Fseek` on the console)
    # sit at 0.98-1.07 once the resolution and the device arm are one call (`src/gemdos/dispatch.c`); this
    # is the one arm with no body at all to amortise a call against.
    ("gemdos_dispatch_selector", "Cconws of an empty string redirected to a file"): (
        1.71, "the redirection table's `jmp (a0)` against a C call: the ROM reaches `Cconws`'s arm in one "
              "indexed jump and the empty string ends it at its first `tst.b`; ours pays the call into "
              "`character_call` (four arguments pushed, three registers saved), the compare chain its "
              "switch becomes under -fno-jump-tables, and `redirect_jump_d0`'s record arithmetic for the "
              "D0 this arm alone hands back — 538 -> 892 cycles, 39 instructions to 77. The same arm over "
              "three bytes measures 0.96"),
}

# ---- THE LEAF RULE — the rows where a ratio is the wrong instrument ------------------------------
#
# Mechanism (A) on a TRAP LEAF is the case a written acceptance serves worst. The whole excess is one
# `moveal %sp@(4),%a0` — 12 to 16 cycles, the same instruction on every one of them — and over a
# routine whose body is `move.l _drvbits,d0 / rts` that reads as 1.50x. Ten entries then said the
# same sentence ten times, each carrying a hand-copied ratio somebody has to re-pin the day the core
# moves, and a reader learned nothing from the sixth.
#
# WHAT THE MACHINE ACTUALLY PAYS is what the rule measures against instead. Nothing CALLS a BIOS
# leaf: a caller reaches it through `trap #13`, and the dispatcher's own cycles dwarf it. So
# Drvmap's +16 is 16 cycles on a whole `Bios(10)` call, not 16 on a 32-cycle fragment nobody ever
# executes alone — a few per cent rather than half again. The dispatcher's cost is READ from the
# rows this same table measures (`dispatch_cycles` below), never written down here: it is a
# measurement like every other number in this file.
#
# A row NAMED BELOW is then admitted when its excess is small BOTH ways — at most
# `LEAF_SLACK_CYCLES` absolutely, which is one pointer load and change and never a branch or a loop,
# and at most `LEAF_SLACK_FRACTION` of the dispatched call it is part of. A row that is not named is
# not eligible whatever it measures: the naming IS the claim that (A) is the whole of its excess,
# and only a reader of the two listings can make that claim.
#
# INTERRUPT-HANDLER ROWS ARE DELIBERATELY OUT OF IT. A handler is dispatched by the machine and pays
# no dispatcher, so there is no whole call for its excess to be a fraction of — every ISR row keeps
# its written entry above, and the rule refuses the largest of them (`isr_vbl / a frame with
# everything queued`, +282 cycles) on the absolute test alone. `test_tier3.py` pins both halves.
LEAF_SLACK_CYCLES = 40
LEAF_SLACK_FRACTION = 0.075

# The (A)-ONLY TRAP LEAVES: every row whose excess over the original is the image-pointer load and
# nothing else. Read off `make bench`'s own instruction counts (one instruction more on each) and
# the two listings, which is why this is a list of names rather than something derived.
IMAGE_POINTER_LEAVES = frozenset({
    ("bios_drvmap", "bios_drvmap"),         # +16 cycles: two instructions become three
    ("xbios_logbase", "xbios_logbase"),     # +16, the same two-become-three
    ("bios_tickcal", "bios_tickcal"),       # +14
    ("bios_kbshift", "read"),               # +26
    ("bios_kbshift", "write"),              # +34, the widest the rule admits
    ("xbios_bioskeys", "xbios_bioskeys"),   # +16
    ("bios_getmpb", "bios_getmpb"),         # +30
    ("xbios_dosound", "play"),              # +20
    ("xbios_dosound", "report only"),       # +20, the same load over the shorter arm
})
assert not IMAGE_POINTER_LEAVES & set(PERF_ACCEPTED), (
    "a row is both named as an (A)-only leaf and carries a written PERF_ACCEPTED entry; the two are "
    "alternatives — the entry would decide it first and the rule would never be asked")

# The image base a core is handed. ROM MODE, so it is 0 and a core's `be32(image + SYSVAR_HZ_200)`
# reads the machine's real `$4ba` (tools/recreate_kit/rom_bench.py, "THE MEMORY LAYOUT").
IMAGE = 0

# What `returns` a C signature declares, in the bytes of D0 `RomBench.measure` compares.
RETURNS_LONG = 4            # uint32_t
RETURNS_BYTE = 1            # uint8_t — GCC leaves the caller's high word alone; the ROM clears it
RETURNS_NOTHING = 0         # void


class FrameArg:
    """A C argument decoded out of the ARGUMENT FRAME the case itself poked.

    The ROM reads its arguments as words and longwords at `4(sp)`; our C takes them as C arguments.
    Both must be the same numbers, and the only way to be sure of that is to read ours out of the
    bytes the case staged for the ROM rather than to write them down a second time — a `device` typed
    here as 2 where the case poked 3 would measure a different branch and say nothing.
    """

    def __init__(self, offset, fmt):
        self.offset = offset
        self.fmt = fmt

    def of(self, frame):
        return struct.unpack_from(self.fmt, frame, self.offset)[0]


# Where an IN/OUT pointer argument's storage goes: a COPY of the case's argument frame, at the FLOOR
# of the oracle's stack band — the one part of that band neither side's frame and neither side's
# arguments reach.
#
# WHY IT CANNOT BE THE FRAME ITSELF, which is the first thing anyone would try. The m68k C ABI puts
# our arguments at 8(sp), 12(sp)… — the SAME words the ROM reads its own out of, because they are
# one caller's frame — so staging ours writes over the case's. `xbios_protobt` is the routine that
# makes that visible: Alcyon C rewrites `serial` and `executable` in the caller's frame, so the C
# signature takes pointers, and a pointer AT the frame would address the words our own arguments had
# just overwritten (measured: the serial reads back as the pointer value).
#
# So the storage is a copy, and the copy has to live in the band `harness.diff_spans()` DROPS. Our
# build writes its result there and the original writes its own into the frame, so the two
# write-backs are not compared — which is exactly the coverage a Tier 1 case has, where the battery
# reads the ORACLE's back out of its write ledger and the candidate's out of its own `ctypes` cell.
# What IS compared is everything the routine did to the image: for Protobt that is the whole boot
# sector. Neither the case staging band nor anything else a case "owns" will do, because all of it
# is compared image: the "random serial" row invents a serial, writes it through the pointer, and
# the original never writes that byte — so the second differential reds on our own write-back.
#
# WHY THE FLOOR OF THE BAND and not the headroom above `stack_top`, which is where this constant used
# to sit. The band closes at `emu.STACK_BAND_HI` = stack_top + SENTINEL_SLOT_BYTES +
# STACK_ARGS_BYTES, and our own call fills nearly all of that: Protobt's five C arguments reach
# stack_top + 0x18 of the 0x1c (`asm_twin.stage_stack_args`). Below `stack_top` the band is 0xf00
# deep and the deepest frame the kit calls legitimate is `emu.STACK_SCRATCH` (0x400), so the floor is
# 0xb00 clear of anything either side pushes.
POINTER_STORAGE = emu.STACK_GUARD_LO


class FrameAddress:
    """...and the ADDRESS of one of those slots, for an IN/OUT pointer argument.

    It points into `POINTER_STORAGE` — a copy of the case's frame, poked at the floor of the band
    the diff drops — rather than into the frame; that comment says why.
    """

    def __init__(self, offset):
        self.offset = offset

    def of(self, _frame):
        return POINTER_STORAGE + self.offset


class EntryRegister:
    """A C argument that is a REGISTER the case is entered with, named by the register.

    Two kinds of routine need one. A trap routine's no-driver arm hands back the D0 the dispatcher
    left, so the C takes it and returns it. And a routine TOS reaches through a RAM vector has no
    argument frame at all — its caller leaves the byte in D0 and the record in A0 (`acia_take_byte`
    into `midivec`, `kbd_queue_key` from either of its two callers) — so the C's parameters ARE
    those registers.

    Taken from the CASE's own input registers rather than re-typed, for `FrameArg`'s reason: the
    oracle is entered with them and our C is passed them, and the two must be one value.
    """

    def __init__(self, name):
        self.name = name

    def of(self, _frame):
        raise AssertionError(f"{self.name} is resolved from the case's registers, not its frame")


ENTRY_D0 = EntryRegister("d0")
ENTRY_A0 = EntryRegister("a0")
ENTRY_D5 = EntryRegister("d5")
ENTRY_A4 = EntryRegister("a4")


def arg_word(offset):
    """An unsigned argument WORD at `offset` bytes into the frame — a `uint16_t` parameter."""
    return FrameArg(offset, ">H")


def arg_signed_word(offset):
    """...and a SIGNED one, for an `int16_t` parameter. The distinction is the caller's: the m68k ABI
    widens a `short` argument to a 32-bit slot, and a C caller widens it the way its type says."""
    return FrameArg(offset, ">h")


def arg_long(offset):
    """...and an argument LONGWORD — a `uint32_t` parameter, or an address one."""
    return FrameArg(offset, ">I")


def arg_address(offset):
    """...and a POINTER to the slot itself, for an in/out parameter (see `FrameAddress`)."""
    return FrameAddress(offset)


Call = namedtuple("Call", "args returns")

# HOW OUR BUILD IS CALLED, one entry per ROM routine, keyed by the `include/addrs.h` name of its
# entry address. The C core's own symbol is that name lower-cased — `XBIOS_RANDOM` is
# `xbios_random` — so it is derived rather than typed beside it; a core that did not follow the
# convention would fail at `RomBench.entry`, naming every symbol the blob does hold.
#
# This is the one thing `VERIFIED_CASES` cannot carry, because it is a fact about the C signature
# and not about the ROM. Everything else — the entry, the input registers, the pokes, the declared
# chip and I/O bytes — comes from that list, and every argument VALUE is decoded from the frame the
# case poked (`FrameArg`), so there is no number here to disagree with it.
CALL = {
    "BIOS_BCONSTAT": Call((IMAGE, ENTRY_D0, arg_word(0)), RETURNS_LONG),
    "BIOS_BCONIN": Call((IMAGE, ENTRY_D0, arg_word(0)), RETURNS_LONG),
    # ...and the one character-device call with a SECOND argument word: the device and the
    # character, both read off the frame the case poked (`src/bios/bcon.c`).
    "BIOS_BCONOUT": Call((IMAGE, ENTRY_D0, arg_word(0), arg_word(2)), RETURNS_LONG),
    "BIOS_BCOSTAT": Call((IMAGE, ENTRY_D0, arg_word(0)), RETURNS_LONG),
    "BIOS_DRVMAP": Call((IMAGE,), RETURNS_LONG),
    # ...and its D0 is the TPA's length, which the `sub.l` leaves there (`src/bios/getmpb.c`).
    "BIOS_GETMPB": Call((IMAGE, arg_long(0)), RETURNS_LONG),
    "BIOS_KBSHIFT": Call((IMAGE, arg_word(0)), RETURNS_LONG),
    "BIOS_SETEXC": Call((IMAGE, arg_word(0), arg_long(2)), RETURNS_LONG),
    "BIOS_TICKCAL": Call((IMAGE,), RETURNS_LONG),
    "XBIOS_BIOSKEYS": Call((IMAGE,), RETURNS_NOTHING),
    "XBIOS_CURSCONF": Call((IMAGE, ENTRY_D0, arg_word(0), arg_word(2)), RETURNS_LONG),
    # No image argument at all: this routine's whole effect is one declared I/O read (`getrez.c`).
    "XBIOS_GETREZ": Call((), RETURNS_BYTE),
    # ...and nor does this one — its arguments ARE the two words, and its effect is the chip.
    "XBIOS_GIACCESS": Call((arg_word(0), arg_word(2)), RETURNS_BYTE),
    "XBIOS_IOREC": Call((IMAGE, arg_word(0)), RETURNS_LONG),
    "XBIOS_KBRATE": Call((IMAGE, ENTRY_D0, arg_word(0), arg_word(2)), RETURNS_LONG),
    "XBIOS_KEYTBL": Call((IMAGE, arg_long(0), arg_long(4), arg_long(8)), RETURNS_LONG),
    "XBIOS_LOGBASE": Call((IMAGE,), RETURNS_LONG),
    "XBIOS_PROTOBT": Call((IMAGE, arg_long(0), arg_address(4), arg_signed_word(8), arg_address(10)),
                          RETURNS_NOTHING),
    "XBIOS_RANDOM": Call((IMAGE,), RETURNS_LONG),
    "XBIOS_SUPEXEC": Call((IMAGE, arg_long(0)), RETURNS_LONG),
    # ---- the XBIOS screen and sound leaves (BIOS wave 2) ----
    # No image argument: this one's whole input is the two shifter base registers (`physbase.c`).
    "XBIOS_PHYSBASE": Call((), RETURNS_LONG),
    "XBIOS_SETSCREEN": Call((IMAGE, ENTRY_D0, arg_long(0), arg_long(4), arg_word(8)),
                            RETURNS_LONG),
    "XBIOS_SETPALETTE": Call((IMAGE, ENTRY_D0, arg_long(0)), RETURNS_LONG),
    # ...nor does this one: one declared palette read, one ledgered store, and D0.
    "XBIOS_SETCOLOR": Call((ENTRY_D0, arg_word(0), arg_word(2)), RETURNS_LONG),
    # ...and these two reach the chip through `Giaccess` and the image not at all.
    "XBIOS_ONGIBIT": Call((ENTRY_D0, arg_word(0)), RETURNS_LONG),
    "XBIOS_OFFGIBIT": Call((ENTRY_D0, arg_word(0)), RETURNS_LONG),
    "XBIOS_DOSOUND": Call((IMAGE, arg_long(0)), RETURNS_LONG),
    "XBIOS_SETPRT": Call((IMAGE, ENTRY_D0, arg_word(0)), RETURNS_LONG),
    # ...and the one routine here that WAITS. Its argument list is ordinary; what is not is that its
    # case carries a SCHEDULE, without which neither side's loop would ever end (`Row.schedule`).
    "XBIOS_VSYNC": Call((IMAGE,), RETURNS_LONG),
    # ---- the MFP / timer / IKBD / serial leaves (BIOS wave 2) ----
    # No image argument: these two change a bit of an MFP register and touch memory not at all.
    # Their D0 is the MASKED channel, which the `andi.l #15` writes and the `movem.l (sp)+` restores
    # — not the argument, and not the caller's entry D0 (`src/xbios/mfp.c`).
    "XBIOS_JDISINT": Call((arg_word(0),), RETURNS_LONG),
    "XBIOS_JENABINT": Call((arg_word(0),), RETURNS_LONG),
    # ...and the two that DO reach the image: the vector slot at `$100 + channel * 4` is memory, so
    # the whole routine takes the image pointer where its two halves above do not.
    "XBIOS_MFPINT": Call((IMAGE, arg_word(0), arg_long(2)), RETURNS_LONG),
    "XBIOS_XBTIMER": Call((IMAGE, arg_word(0), arg_word(2), arg_word(4), arg_long(6)),
                          RETURNS_LONG),
    # ...and these two READ the image (the bytes to send) and write only an ACIA's data port.
    "XBIOS_IKBDWS": Call((IMAGE, arg_word(0), arg_long(2)), RETURNS_NOTHING),
    "XBIOS_MIDIWS": Call((IMAGE, arg_word(0), arg_long(2)), RETURNS_NOTHING),
    # A constant, and the smallest routine in this table: `move.l #$e12,d0 / rts`.
    "XBIOS_KBDVBASE": Call((), RETURNS_LONG),
    "XBIOS_INITMOUS": Call((IMAGE, arg_word(0), arg_long(2), arg_long(6)), RETURNS_LONG),
    # ...and this one takes the caller's whole ARGUMENT BLOCK, as the ROM does — six optional words
    # it reads off the frame. `arg_address(0)` is the copy of that frame at POINTER_STORAGE, which
    # is also the only form seven values could be passed in (`rom_bench._vet_stack_args_fit`).
    "XBIOS_RSCONF": Call((IMAGE, arg_address(0)), RETURNS_LONG),
    # ---- the INTERRUPT HANDLERS (BIOS wave 2) ----
    # None takes an argument — nothing calls one, the machine dispatches it — and none returns a
    # result: what a handler owes the interrupted program is the memory and the chip it left, and
    # the registers it gives back (`isr.assert_registers_survived`).
    #
    # The HBL is the exception, and its argument is not one the ROM has: a C function has no
    # `2(sp)` to reach, so the ADDRESS of the exception frame is what the reconstruction takes, and
    # this is the frame `test/isr.py` puts its registered cases' at.
    "ISR_HBL": Call((IMAGE, isr.STAGED_FRAME), RETURNS_NOTHING),
    "ISR_VBL": Call((IMAGE,), RETURNS_NOTHING),
    "ISR_TIMER_C": Call((IMAGE,), RETURNS_NOTHING),
    "ISR_ACIA": Call((IMAGE,), RETURNS_NOTHING),
    # ---- the ACIA INPUT CHAIN, reached through KBDVECS (BIOS wave 3) ----
    # None returns anything and none reads an argument frame: each is entered by the routine above it
    # with the registers the ROM's own callers leave, and the C takes exactly those as parameters
    # (`include/bios/acia_packets.h`, `include/bios/keyboard.h`). The two service routines take only the image
    # — their chip and their IOREC are the three instructions that are all each entry is.
    "MIDI_ACIA_SERVICE": Call((IMAGE,), RETURNS_NOTHING),
    "IKBD_ACIA_SERVICE": Call((IMAGE,), RETURNS_NOTHING),
    # `midi_queue_byte(image, iorec, byte)` — A0 is the record and D0 the raw byte, which is the
    # published KBDVECS contract for a byte vector (`test/acia.py`).
    "MIDI_QUEUE_BYTE": Call((IMAGE, ENTRY_A0, ENTRY_D0), RETURNS_NOTHING),
    # ...and the keyboard's pair, whose order is the other way round: `(image, scancode, iorec)` with
    # the scancode in D0 and the IOREC in A0.
    "KBD_SCANCODE": Call((IMAGE, ENTRY_D0, ENTRY_A0), RETURNS_NOTHING),
    "KBD_QUEUE_KEY": Call((IMAGE, ENTRY_D0, ENTRY_A0), RETURNS_NOTHING),
    # ---- the GEMDOS trap entry, the dispatcher and the RAM-only leaves (GEMDOS wave 1) ----
    # A GEMDOS leaf reads its arguments out of the ARGUMENT LIST the dispatcher hands it rather than
    # off its own frame, so the two are the same words here as everywhere: `gemdos.ARGUMENTS_AT` is
    # where the case staged the caller's own, and `arg_word`/`arg_long` read the leaf's out of the
    # frame at `abi.FIRST_ARG` (`test/gemdos.py`, `argument_list`).
    "GEMDOS_SVERSION": Call((), RETURNS_LONG),
    "GEMDOS_UNIMPLEMENTED": Call((), RETURNS_LONG),
    "GEMDOS_FGETDTA": Call((IMAGE,), RETURNS_LONG),
    # ...and the one leaf that writes no result of its own: the ROM's `move.l 8(a6),$20(a0)` leaves
    # the caller's D0 where it was, so the C takes it and hands it back.
    "GEMDOS_FSETDTA": Call((IMAGE, ENTRY_D0, arg_long(0)), RETURNS_LONG),
    "GEMDOS_DGETDRV": Call((IMAGE,), RETURNS_LONG),
    # ...and the one leaf here that reaches the BIOS: on target it takes the ROM's own `trap #13`,
    # so both columns of its row carry the dispatcher and `Drvmap` (`src/gemdos/leaves.c`).
    "GEMDOS_DSETDRV": Call((IMAGE, arg_word(0)), RETURNS_LONG),
    "GEMDOS_TGETDATE": Call((IMAGE,), RETURNS_LONG),
    "GEMDOS_TGETTIME": Call((IMAGE,), RETURNS_LONG),
    "GEMDOS_TSETDATE": Call((IMAGE, arg_word(0)), RETURNS_LONG),
    "GEMDOS_TSETTIME": Call((IMAGE, arg_word(0)), RETURNS_LONG),
    # The dispatcher itself, and the SLICE past the termination record it arms. Both take the
    # caller's argument LIST — the function number word and the arguments under it — which is what
    # the trap entry's `lea 50(frame),a0` hands them.
    "GEMDOS_DISPATCH": Call((IMAGE, gemdos.ARGUMENTS_AT), RETURNS_LONG),
    "GEMDOS_DISPATCH_SELECTOR": Call((IMAGE, gemdos.ARGUMENTS_AT), RETURNS_LONG),
    # ...and its media-change recovery's two helpers. The second never reads its argument — it
    # compares against the A4 its caller left (`src/gemdos/dispatch.c`) — so the C takes that register.
    "GEMDOS_FREE_DND_TREE": Call((IMAGE, arg_long(0)), RETURNS_NOTHING),
    "GEMDOS_FREE_DRIVE_OFDS": Call((IMAGE, ENTRY_A4), RETURNS_NOTHING),
    # ---- the GEMDOS CHARACTER DEVICES (GEMDOS wave 1) ----
    # The DEVICE is not an argument to any of these: each leaf reads its own standard handle out of
    # the running process's basepage and adds three (`src/gemdos/console.c`). What IS an argument is
    # the character word or the buffer longword the caller pushed — and, for the two that can return
    # without any call writing D0, the caller's own D0 (`include/gemdos/console.h`).
    "GEMDOS_CCONIN": Call((IMAGE,), RETURNS_LONG),
    "GEMDOS_CRAWCIN": Call((IMAGE,), RETURNS_LONG),
    "GEMDOS_CNECIN": Call((IMAGE,), RETURNS_LONG),
    "GEMDOS_CAUXIN": Call((IMAGE,), RETURNS_LONG),
    "GEMDOS_CCONIS": Call((IMAGE,), RETURNS_LONG),
    "GEMDOS_CAUXIS": Call((IMAGE,), RETURNS_LONG),
    "GEMDOS_CCONOS": Call((IMAGE,), RETURNS_LONG),
    "GEMDOS_CPRNOS": Call((IMAGE,), RETURNS_LONG),
    "GEMDOS_CAUXOS": Call((IMAGE,), RETURNS_LONG),
    "GEMDOS_CCONOUT": Call((IMAGE, arg_word(0)), RETURNS_LONG),
    "GEMDOS_CAUXOUT": Call((IMAGE, arg_word(0)), RETURNS_LONG),
    "GEMDOS_CPRNOUT": Call((IMAGE, arg_word(0)), RETURNS_LONG),
    "GEMDOS_CRAWIO": Call((IMAGE, arg_word(0)), RETURNS_LONG),
    # ...and the two with a POINTER argument, which also take `entry_d0`: `Cconws` over an empty
    # string hands back the sign-extended standard handle in D0's low word over the caller's high
    # half, and `Cconrs` writes only the low word on every path.
    "GEMDOS_CCONWS": Call((IMAGE, ENTRY_D0, arg_long(0)), RETURNS_LONG),
    "GEMDOS_CCONRS": Call((IMAGE, ENTRY_D0, arg_long(0)), RETURNS_LONG),
    # ---- the MEMORY MANAGER (GEMDOS wave 1) ----
    # The three trap leaves take the caller's own argument frame; the five under them are called by
    # name, with the arguments GEMDOS's own C left on the stack (`src/gemdos/memory.c`). `Mshrink`'s
    # frame is the odd one: a reserved zero word the ROM never reads, then the block and the length.
    "GEMDOS_POOL_ARENA_ALLOC": Call((IMAGE, arg_word(0)), RETURNS_LONG),
    "GEMDOS_POOL_GET": Call((IMAGE, arg_word(0)), RETURNS_LONG),
    "GEMDOS_POOL_FREE": Call((IMAGE, arg_long(0)), RETURNS_NOTHING),
    "GEMDOS_MD_ALLOC": Call((IMAGE, arg_long(0), arg_long(4)), RETURNS_LONG),
    "GEMDOS_MD_FREE_INSERT": Call((IMAGE, arg_long(0), arg_long(4)), RETURNS_NOTHING),
    "GEMDOS_MALLOC": Call((IMAGE, arg_long(0)), RETURNS_LONG),
    "GEMDOS_MFREE": Call((IMAGE, arg_long(0)), RETURNS_LONG),
    "GEMDOS_MSHRINK": Call((IMAGE, arg_long(2), arg_long(6)), RETURNS_LONG),
    # ---- the FILE SYSTEM (GEMDOS wave 2) ----
    # The two name-layer leaves and the matcher take the CALLER'S OWN D0 as well as their argument,
    # for mechanism (D)'s reason: each writes only part of the register and hands the rest back, so
    # a `uint16_t` core would agree with a reconstruction that had cleared a half the ROM preserves
    # (`src/gemdos/fs_name.c`). The first two touch the image not at all.
    "GEMDOS_FS_TOUPPER": Call((ENTRY_D0, arg_word(0)), RETURNS_LONG),
    "GEMDOS_FS_LOG2": Call((ENTRY_D0, arg_word(0)), RETURNS_LONG),
    "GEMDOS_CLUSTER_RECORD": Call((IMAGE, arg_word(0), arg_long(2)), RETURNS_LONG),
    "GEMDOS_NAME_MATCH": Call((ENTRY_D0, IMAGE, arg_long(0), arg_long(4)), RETURNS_LONG),
    "GEMDOS_BUILD_FCB_NAME": Call((IMAGE, arg_long(0), arg_long(4)), RETURNS_NOTHING),
    # ...and the three that reach the disk, each through the ROM's own `trap #13` on target
    # (`src/gemdos/fs_disk.c`): the case stages the driver the vectors name, so both columns run it.
    #
    # THEIR ~1.00 IS A RATIO OF THE WHOLE CALL AND NOT OF THE CORE, and it is worth saying where the
    # rows are. The staged `hdv_rw` stub copies 512 bytes at 22 cycles a byte, so ~11k of each of
    # these ~13k columns is the same driver on both shores; the core's own share is ~1-2k, and a
    # change to it moves the printed ratio by a fraction of what it moved the core by. NETTING THE
    # STUB OUT is the fix and is PARKED (`recreate/STATUS.md`): it wants a per-row `staged_entry`
    # measured from a zero-count `Rwabs`, which is a bench change rather than a case one.
    "GEMDOS_BUFFER_FLUSH": Call((IMAGE, arg_long(0)), RETURNS_NOTHING),
    "GEMDOS_RWABS_DATA": Call((IMAGE, arg_word(0), arg_word(2), arg_word(4), arg_long(6),
                               arg_long(10)), RETURNS_NOTHING),
    "GEMDOS_BUFFER_GET": Call((IMAGE, arg_word(0), arg_long(2), arg_word(6)), RETURNS_LONG),
    # ---- the FILE SYSTEM (GEMDOS fs wave 3) ----
    # The three byte copies: one C loop, each entry taking its ROM frame's (n.w, a.l, b.l) in order
    # (`src/gemdos/fs_copy.c`).
    "GEMDOS_COPY_OUT": Call((IMAGE, arg_word(0), arg_long(2), arg_long(6)), RETURNS_NOTHING),
    "GEMDOS_COPY_IN": Call((IMAGE, arg_word(0), arg_long(2), arg_long(6)), RETURNS_NOTHING),
    "GEMDOS_BCOPY": Call((IMAGE, arg_word(0), arg_long(2), arg_long(6)), RETURNS_NOTHING),
    "OS_SWAP_WORD": Call((IMAGE, arg_long(0)), RETURNS_NOTHING),
    "OS_SWAP_LONG": Call((IMAGE, arg_long(0)), RETURNS_NOTHING),
    # ...and the record layer (`src/gemdos/fs_records.c`). `fcb_name_eq` takes the caller's D0 for
    # `$fc5c9a`'s reason: its miss clears only the low word.
    "GEMDOS_FCB_NAME_EQ": Call((ENTRY_D0, IMAGE, arg_long(0), arg_long(4)), RETURNS_LONG),
    "GEMDOS_FCB_TO_TEXT": Call((IMAGE, arg_long(0), arg_long(4)), RETURNS_LONG),
    "GEMDOS_DND_PATH": Call((IMAGE, arg_long(0), arg_long(4)), RETURNS_LONG),
    "GEMDOS_FILL_DTA": Call((IMAGE, arg_long(0), arg_long(4)), RETURNS_NOTHING),
    "GEMDOS_OFD_NEW": Call((IMAGE, arg_long(0)), RETURNS_LONG),
    "GEMDOS_DND_NEW": Call((IMAGE, arg_long(0), arg_long(4)), RETURNS_LONG),
    "GEMDOS_OFD_OPEN": Call((IMAGE, arg_long(0), arg_long(4), arg_signed_word(8), arg_word(10)),
                            RETURNS_LONG),
    "GEMDOS_HANDLE_ALLOC": Call((IMAGE, arg_long(0), arg_long(4), arg_word(8)), RETURNS_LONG),
    "GEMDOS_DIR_ZERO_CLUSTER": Call((IMAGE, arg_long(0)), RETURNS_LONG),
    # ...and the drive and path layer (`src/gemdos/fs_drive.c`). A drive is a
    # SIGNED word everywhere in it (`movea.w` before every table index). `open_drive` reaches BIOS
    # `Getbpb` for a drive not yet logged in, through the ROM's own `trap #13` on target; the three
    # string routines take the caller's D0 for `$fc5c9a`'s reason.
    "GEMDOS_DMD_ALLOC": Call((IMAGE, arg_signed_word(0)), RETURNS_LONG),
    "GEMDOS_DMD_BUILD": Call((IMAGE, arg_long(0), arg_signed_word(4)), RETURNS_LONG),
    "GEMDOS_OPEN_DRIVE": Call((IMAGE, arg_signed_word(0)), RETURNS_LONG),
    "GEMDOS_PATH_START": Call((IMAGE, arg_long(0)), RETURNS_LONG),
    "GEMDOS_DOT_NAME": Call((ENTRY_D0, IMAGE, arg_long(0), arg_word(4)), RETURNS_LONG),
    "GEMDOS_SPLIT_PATH": Call((ENTRY_D0, IMAGE, arg_long(0), arg_long(4), arg_word(8)), RETURNS_LONG),
    "GEMDOS_STRNEQ": Call((ENTRY_D0, IMAGE, arg_word(0), arg_long(2), arg_long(6)), RETURNS_LONG),
    # ...and the I/O engine (`src/gemdos/fs_io.c`). `fat_get` takes the caller's D0
    # for `$fc5c9a`'s reason — its negative-cluster arm writes only the low word — and `ofd_xfer` its
    # copy routine as the ROM ADDRESS the frame holds, which the core maps to its reconstruction.
    # `advance` and `fat_set` leave only an incidental D0 no caller reads, so they are `void`.
    "GEMDOS_SPLIT_SHIFT": Call((IMAGE, arg_long(0), arg_long(4), arg_word(8)), RETURNS_LONG),
    "GEMDOS_OFD_ADVANCE": Call((IMAGE, arg_long(0), arg_long(4), arg_word(8)), RETURNS_NOTHING),
    "GEMDOS_OFD_SEEK": Call((IMAGE, arg_long(0), arg_long(4)), RETURNS_LONG),
    "GEMDOS_FAT_GET": Call((ENTRY_D0, IMAGE, arg_word(0), arg_long(2)), RETURNS_LONG),
    "GEMDOS_FAT_SET": Call((IMAGE, arg_word(0), arg_word(2), arg_long(4)), RETURNS_NOTHING),
    "GEMDOS_NEXT_CLUSTER": Call((IMAGE, arg_long(0), arg_word(4)), RETURNS_LONG),
    "GEMDOS_OFD_XFER": Call((IMAGE, arg_word(0), arg_long(2), arg_long(6), arg_long(10),
                             arg_long(14)), RETURNS_LONG),
    "GEMDOS_OFD_READ": Call((IMAGE, arg_long(0), arg_long(4), arg_long(8)), RETURNS_LONG),
    "GEMDOS_OFD_WRITE": Call((IMAGE, arg_long(0), arg_long(4), arg_long(8)), RETURNS_LONG),
    # The three leaves: `Fseek`'s frame is the offset longword first and the handle third.
    "GEMDOS_FREAD": Call((IMAGE, arg_signed_word(0), arg_long(2), arg_long(6)), RETURNS_LONG),
    "GEMDOS_FWRITE": Call((IMAGE, arg_signed_word(0), arg_long(2), arg_long(6)), RETURNS_LONG),
    "GEMDOS_FSEEK": Call((IMAGE, arg_long(0), arg_signed_word(4), arg_word(6)), RETURNS_LONG),
    # ...and the fs DIRECTORY layer (`src/gemdos/fs_dir.c`). The search's position and the walk's
    # tail are C POINTERS (`include/gemdos/fs_dir.h`): the frame's longword is the address, which in
    # ROM mode our build reaches directly, so it stores where the original does.
    "GEMDOS_DIR_SEARCH": Call((IMAGE, arg_long(0), arg_long(4), arg_word(8), arg_long(10)), RETURNS_LONG),
    "GEMDOS_FIND_DIR": Call((IMAGE, arg_long(0), arg_long(4), arg_word(8)), RETURNS_LONG),
    "GEMDOS_FSNEXT": Call((IMAGE,), RETURNS_LONG),
    # ...and the fs FILE layer (`src/gemdos/fs_file.c`) and the two leaves over a drive
    # (`src/gemdos/fs_leaves.c`). A handle and a drive are SIGNED words, as everywhere in GEMDOS.
    "GEMDOS_OFD_CLOSE": Call((IMAGE, arg_long(0), arg_word(4)), RETURNS_LONG),
    "GEMDOS_DELETE_ENTRY": Call((IMAGE, arg_long(0), arg_long(4), arg_long(8)), RETURNS_LONG),
    "GEMDOS_FDATIME": Call((IMAGE, arg_long(0), arg_signed_word(4), arg_word(6)), RETURNS_LONG),
    "GEMDOS_DFREE": Call((IMAGE, arg_long(0), arg_signed_word(4)), RETURNS_LONG),
    "GEMDOS_DGETPATH": Call((IMAGE, arg_long(0), arg_signed_word(4)), RETURNS_LONG),
    # ...and the NAME leaves (`src/gemdos/fs_open.c`): a path, then an attribute, mode or flag WORD.
    "GEMDOS_SFIRST": Call((IMAGE, arg_long(0), arg_word(4), arg_long(6)), RETURNS_LONG),
    "GEMDOS_FSFIRST": Call((IMAGE, arg_long(0), arg_word(4)), RETURNS_LONG),
    "GEMDOS_DSETPATH": Call((IMAGE, arg_long(0)), RETURNS_LONG),
    "GEMDOS_OPEN": Call((IMAGE, arg_long(0), arg_word(4)), RETURNS_LONG),
    "GEMDOS_FOPEN": Call((IMAGE, arg_long(0), arg_word(4)), RETURNS_LONG),
    "GEMDOS_FATTRIB": Call((IMAGE, arg_long(0), arg_word(4), arg_word(6)), RETURNS_LONG),
    "GEMDOS_FDELETE": Call((IMAGE, arg_long(0)), RETURNS_LONG),
    # ...and the CREATE layer (`src/gemdos/fs_create.c`): a path, and create's attribute WORD.
    "GEMDOS_CREATE": Call((IMAGE, arg_long(0), arg_word(4)), RETURNS_LONG),
    "GEMDOS_FCREATE": Call((IMAGE, arg_long(0), arg_word(4)), RETURNS_LONG),
    "GEMDOS_DDELETE": Call((IMAGE, arg_long(0)), RETURNS_LONG),
    "GEMDOS_DCREATE": Call((IMAGE, arg_long(0)), RETURNS_LONG),
    # ...and `Frename` (`src/gemdos/fs_rename.c`): the ABI's unused word, then the two paths.
    "GEMDOS_FRENAME": Call((IMAGE, arg_word(0), arg_long(2), arg_long(6)), RETURNS_LONG),
    # ---- the PROCESS group and the HANDLE machinery (GEMDOS wave 2) ----
    # A handle is SIGNED everywhere in this group — the bound `Fforce` applies is `bge`/`ble` over
    # -1..5 — so its argument words are `arg_signed_word` and its C parameters are `int16_t`
    # (`src/gemdos/handles.c`).
    "GEMDOS_FFORCE": Call((IMAGE, arg_signed_word(0), arg_signed_word(2)), RETURNS_LONG),
    "GEMDOS_FORCE_HANDLE": Call((IMAGE, arg_signed_word(0), arg_signed_word(2), arg_long(4)),
                                RETURNS_LONG),
    "GEMDOS_FDUP": Call((IMAGE, arg_signed_word(0)), RETURNS_LONG),
    "GEMDOS_FCLOSE": Call((IMAGE, arg_signed_word(0)), RETURNS_LONG),
    "GEMDOS_RELEASE_PROCESS": Call((IMAGE, arg_long(0)), RETURNS_NOTHING),
    # ...and the one routine here whose whole input is a chip: the Mega ST's battery clock, read
    # through the declared I/O map with the register written back (`src/gemdos/process.c`).
    "GEMDOS_RESYNC_CLOCK": Call((IMAGE,), RETURNS_NOTHING),
    "GEMDOS_INHERIT_CURDIR": Call((IMAGE, arg_signed_word(0), arg_signed_word(2), arg_long(4)),
                                  RETURNS_NOTHING),
    # `Pexec`'s own frame is the dispatcher's widest class: a mode WORD and three longwords. The
    # slice past the termination record takes the same four, because it is the same frame one
    # routine along (`test/gemdos_process.py`, `pexec_args`).
    "GEMDOS_PEXEC": Call((IMAGE, arg_word(0), arg_long(2), arg_long(6), arg_long(10)),
                         RETURNS_LONG),
    "GEMDOS_PEXEC_CREATE": Call((IMAGE, arg_word(0), arg_long(2), arg_long(6), arg_long(10)),
                                RETURNS_LONG),
    # ...and its loader, whose `Fopen` mode is the high half of the D5 it runs with — an ENTRY REGISTER
    # the case declares, which our core takes as its last argument (`src/gemdos/pexec_load.c`).
    "GEMDOS_PEXEC_LOAD": Call((IMAGE, arg_long(0), arg_long(4), ENTRY_D5), RETURNS_LONG),
}

# Cases this file adds to the verified set, in `VERIFIED_CASES`' own shape.
#
# ONE, AND IT IS THE CASE TIER 3 EXISTS FOR. `test_xbios_supexec.py`'s module docstring says which of
# its claims the differential cannot make: that the routine the caller named sees the CALLER'S OWN
# STACK with nothing pushed over it — the difference between the ROM's `jmp (a0)` and a `jsr`. Off
# target the core reaches the staged routine through a host hook that has no 68000 stack to look at,
# so the claim is the oracle's alone there. Here the target build's body IS the `jmp`, and the stub
# reads the longword at (sp): the ORIGINAL's stub finds the sentinel return address `emu.run` planted
# for Supexec itself, and ours finds the one `run_bench` planted — the same address, and a DIFFERENT
# one the moment either side builds a frame. The stub is assembled by the battery's own helpers, so
# the two halves of this file's one extra case are still nobody's second spelling.
EXTRA_CASES = (
    ("xbios_supexec, the routine sees the caller's own (sp)", addrs.XBIOS_SUPEXEC, {"a5": 0},
     {abi.FIRST_ARG: struct.pack(">I", supexec.STUB_AT),
      supexec.STUB_AT: supexec.read_long_from_stack_into_d0() + supexec.RTS}, None, None, ()),
)

# One measured row. `entry`/`regs`/`pokes`/`psg_seed`/`io_seed` are the ORACLE's case, exactly as
# `harness.differential` takes it; `symbol`/`args` are how our build is called; `returns` is the
# width in bytes the C signature declares for its result (see `RomBench.measure`).
# `transcription` says WHICH RELATION the row is measured through: a C core is held to its return
# value and the callee-saved file, an m68k transcription to the whole register file it leaves. It
# defaults to False, so every C row above reads exactly as it did.
# `address` is the ROM address the row is ABOUT, when that is not where the case is entered — a
# transcription's case enters at the caller it staged, and STATUS.md's ledger is keyed by the
# routine's own $fcxxxx address.
# `staged_entry` is the `(instructions, cycles)` the ORIGINAL's column spends GETTING to the routine
# rather than inside it, and which our build never pays: an interrupt handler's case is reached
# through a two-instruction trampoline, because nothing CALLS a handler. `RomBench.measure` takes it
# off the original's column so the ratio is about the handler; the number is `isr.STAGED_ENTRY_COST`,
# MEASURED by `test_bios_hbl.py::test_the_staged_entry_costs_what_tier_3_takes_off_the_original`
# rather than declared, and it is `(0, 0)` for every row entered at its own address.
# `shared_entry` is the opposite subtraction and comes off BOTH columns: what both sides spend on
# the staged CALLER a transcription can only be entered through (`test/trap.py`'s `caller_cost`,
# measured by `test_bios_trap.py`). It is `(0, 0)` for every row that is entered at its own address.
# `schedule` is the case's own, straight out of `VERIFIED_CASES`: the stores an external agent makes
# while the run is in flight, which is what makes a routine that BUSY-WAITS measurable at all (Phase
# 8). It is `()` for every row but `Vsync`'s, and `RomBench.measure` hands the identical list to both
# doors — which is why those entries are READ-triggered (`test_xbios_vsync.blank_after`).
Row = namedtuple("Row", "function case entry symbol args regs pokes psg_seed io_seed returns "
                        "transcription address staged_entry shared_entry schedule",
                 defaults=(False, None, (0, 0), (0, 0), ()))


# THE THIRD RELATION: a routine NOTHING DISPATCHES BY NUMBER, so neither table below names it and
# neither would price it. Two kinds, and both need the same thing — a name and a role, because there
# is no function number for the column to carry:
#
#   * a routine TOS reaches through a RAM VECTOR. The ACIA handler jumps through a KBDVECS slot, and
#     the two keyboard routines are fallen into by `acia_take_byte` and jumped into by timer C's
#     auto-repeat. Without a row of their own they would be priced ONLY inside `isr_acia, real
#     vectors`, where both columns run the ROM's own chain: the cross-compiled `isr_acia` jumps
#     through KBDVECS exactly as the ROM does, so those rows never enter our C at all.
#   * a GEMDOS routine the OS's own C calls BY NAME — the allocator core, the record pool under it,
#     the dispatcher and the undefined-selector stub, which is reached by a table RECORD rather than
#     by a number.
#
# Each is named by its `addrs.h` constant — also the C core's symbol lower-cased, exactly as the
# dispatch-table relations' are — and mapped to what it IS, for the label: the SLOT it is installed
# in, the caller that falls into it, or what the routine does. The address map below is DERIVED from
# this one, so a routine cannot be priced without a label or labelled without being priced.
UNNUMBERED_ROUTINE_ROLES = {
    "MIDI_ACIA_SERVICE": "KBDVECS midisys",
    "IKBD_ACIA_SERVICE": "KBDVECS ikbdsys",
    "MIDI_QUEUE_BYTE": "KBDVECS midivec",
    "KBD_SCANCODE": "IKBD scancode arm",
    "KBD_QUEUE_KEY": "IKBD key into the ring",
    "GEMDOS_POOL_ARENA_ALLOC": "GEMDOS pool arena",
    "GEMDOS_POOL_GET": "GEMDOS pool record",
    "GEMDOS_POOL_FREE": "GEMDOS pool release",
    "GEMDOS_MD_ALLOC": "GEMDOS allocator core",
    "GEMDOS_MD_FREE_INSERT": "GEMDOS free-list insert",
    "GEMDOS_DISPATCH": "GEMDOS dispatcher",
    "GEMDOS_DISPATCH_SELECTOR": "GEMDOS dispatcher, past the record",
    "GEMDOS_FREE_DND_TREE": "GEMDOS DND tree release",
    "GEMDOS_FREE_DRIVE_OFDS": "GEMDOS drive's OFDs release",
    "GEMDOS_UNIMPLEMENTED": "GEMDOS undefined selector",
    # ...and GEMDOS wave 2's, which are the same kind: the file system's eight cores and the process
    # group's five, all of them called BY NAME out of GEMDOS's own C.
    "GEMDOS_FS_TOUPPER": "GEMDOS upper case",
    "GEMDOS_FS_LOG2": "GEMDOS log2",
    "GEMDOS_CLUSTER_RECORD": "GEMDOS cluster -> record",
    "GEMDOS_NAME_MATCH": "GEMDOS 8.3 name match",
    "GEMDOS_BUILD_FCB_NAME": "GEMDOS 8.3 name build",
    "GEMDOS_BUFFER_FLUSH": "GEMDOS buffer flush",
    "GEMDOS_RWABS_DATA": "GEMDOS data transfer",
    "GEMDOS_BUFFER_GET": "GEMDOS buffer cache",
    "GEMDOS_RELEASE_PROCESS": "GEMDOS process release",
    "GEMDOS_FORCE_HANDLE": "GEMDOS Fforce body",
    "GEMDOS_INHERIT_CURDIR": "GEMDOS curdir inherit",
    "GEMDOS_RESYNC_CLOCK": "GEMDOS clock resync",
    "GEMDOS_PEXEC_CREATE": "GEMDOS Pexec, past the record",
    "GEMDOS_PEXEC_LOAD": "GEMDOS Pexec loader",
    # ...fs wave 3's drive and path layer (`src/gemdos/fs_drive.c`).
    "GEMDOS_DMD_ALLOC": "GEMDOS drive records",
    "GEMDOS_DMD_BUILD": "GEMDOS BPB -> DMD",
    "GEMDOS_OPEN_DRIVE": "GEMDOS drive log-in",
    "GEMDOS_PATH_START": "GEMDOS path start",
    "GEMDOS_DOT_NAME": "GEMDOS . / .. test",
    "GEMDOS_SPLIT_PATH": "GEMDOS path component",
    "GEMDOS_STRNEQ": "GEMDOS strneq",
    # ...its I/O engine (`src/gemdos/fs_io.c`; the three leaves over it are dispatched by number).
    "GEMDOS_SPLIT_SHIFT": "GEMDOS split shift",
    "GEMDOS_OFD_ADVANCE": "GEMDOS OFD advance",
    "GEMDOS_OFD_SEEK": "GEMDOS OFD seek",
    "GEMDOS_FAT_GET": "GEMDOS FAT entry read",
    "GEMDOS_FAT_SET": "GEMDOS FAT entry write",
    "GEMDOS_NEXT_CLUSTER": "GEMDOS next cluster",
    "GEMDOS_OFD_XFER": "GEMDOS OFD transfer",
    "GEMDOS_OFD_READ": "GEMDOS OFD read",
    "GEMDOS_OFD_WRITE": "GEMDOS OFD write",
    # ...and its byte copies and record layer (`src/gemdos/fs_copy.c`, `src/gemdos/fs_records.c`).
    "GEMDOS_COPY_OUT": "GEMDOS copy, cache -> user",
    "GEMDOS_COPY_IN": "GEMDOS copy, user -> cache",
    "GEMDOS_BCOPY": "GEMDOS bcopy",
    "OS_SWAP_WORD": "OS byte swap, word",
    "OS_SWAP_LONG": "OS byte swap, long",
    "GEMDOS_FCB_NAME_EQ": "GEMDOS FCB name equality",
    "GEMDOS_FCB_TO_TEXT": "GEMDOS FCB name -> text",
    "GEMDOS_DND_PATH": "GEMDOS directory path",
    "GEMDOS_FILL_DTA": "GEMDOS DTA fill",
    "GEMDOS_OFD_NEW": "GEMDOS directory OFD",
    "GEMDOS_DND_NEW": "GEMDOS child DND",
    "GEMDOS_OFD_OPEN": "GEMDOS file OFD open",
    "GEMDOS_HANDLE_ALLOC": "GEMDOS handle allocation",
    "GEMDOS_DIR_ZERO_CLUSTER": "GEMDOS directory cluster zero",
    # ...and the fs DIRECTORY layer (`src/gemdos/fs_dir.c`; `Fsnext` is dispatched by number).
    "GEMDOS_DIR_SEARCH": "GEMDOS directory search",
    "GEMDOS_FIND_DIR": "GEMDOS path walk",
    # ...and the fs FILE layer (`src/gemdos/fs_file.c`; `Fdatime`, and `fs_leaves.c`'s `Dfree` and `Dgetpath`, by number).
    "GEMDOS_OFD_CLOSE": "GEMDOS OFD close",
    "GEMDOS_DELETE_ENTRY": "GEMDOS directory entry delete",
    # ...and the NAME leaves (`src/gemdos/fs_open.c`; the five leaves over these two are dispatched by number).
    "GEMDOS_SFIRST": "GEMDOS first search",
    "GEMDOS_OPEN": "GEMDOS open",
    # ...and the CREATE layer (`src/gemdos/fs_create.c`; Fcreate, Ddelete and Dcreate are dispatched by number).
    "GEMDOS_CREATE": "GEMDOS create",
}
UNNUMBERED_ROUTINE_NAMES = {getattr(addrs, name): name for name in UNNUMBERED_ROUTINE_ROLES}

# How a TRANSCRIPTION row names itself, keyed by the blob symbol: `src/bios/trap.S`'s entries and
# `src/gemdos/trap1.S` in one map, because `_transcription_row` reads one list of labels and each
# wave's module owns its own (`trap.LABELS`, `gemdos.LABELS`).
TRANSCRIPTION_LABELS = {**trap.LABELS, **gemdos.LABELS}


# ...and what each SLICE TRAMPOLINE costs, which is not one number. A slice case is entered at a
# stub in the staging band because the routine it is about is inside a frame its own prologue
# opened, and the stub sits in the ORIGINAL's column alone — our build is called as a C function and
# never runs it. The dispatcher's stub is THREE instructions (it stands the selector in the frame as
# well) and `Pexec`'s is two, so the one shared constant `_row` used to net every slice by cannot
# serve both. Each module MEASURES its own against the oracle (`test_gemdos_dispatch.py`,
# `test_gemdos_process_pexec.py`); this is where the two meet, keyed by the trampoline exactly as
# `gemdos.ROUTINE_OF_TRAMPOLINE` is.
SLICE_ENTRY_COST = {gemdos.TRAMPOLINE_AT: gemdos.SLICE_ENTRY_COST,
                    gemdos_process.SLICE_TRAMPOLINE_AT: gemdos_process.SLICE_ENTRY_COST}
assert set(SLICE_ENTRY_COST) == set(gemdos.ROUTINE_OF_TRAMPOLINE), (
    "a slice trampoline has a routine and no cost, or a cost and no routine — the two maps are "
    "keyed by the same addresses, and a missing cost would net a row by the wrong stub in silence")


def _entered_routine(entry):
    """The ROM address a case's entry is ABOUT, which is not the entry for a staged one.

    A GEMDOS dispatcher SLICE is entered at a trampoline in the staging band — `$fc973e` is inside
    the frame its own prologue opened, so nothing can enter it directly (`test/gemdos.py`).
    """
    return gemdos.ROUTINE_OF_TRAMPOLINE.get(entry, entry)


def _routine(entry):
    """The `addrs.h` NAME of the routine a case's entry belongs to — the `CALL` table's key.

    Three kinds of entry reach this. A trap routine's case is entered AT the routine, and the name is
    the one `test_boot_snapshot.py` holds to its dispatch-table slot. An interrupt handler's case is
    entered at a TRAMPOLINE (nothing calls a handler, so the case has to stage the exception frame
    its `rte` returns through), and the name comes from the handler that trampoline jumps to. And a
    routine nothing dispatches by number is entered at its own address but named by neither table —
    see `UNNUMBERED_ROUTINE_NAMES`. A GEMDOS dispatcher SLICE is the second kind of staged entry,
    named by the routine its trampoline jumps to.
    """
    handler = isr.HANDLER_OF_TRAMPOLINE.get(entry)
    if handler:
        return handler.constant
    entry = _entered_routine(entry)
    return (test_boot_snapshot.TRAP_ROUTINE_NAMES.get(entry)
            or UNNUMBERED_ROUTINE_NAMES.get(entry))


def _function_label(entry):
    """"XBIOS Random ($11)" — from `addrs.h`'s own name for the entry and its function NUMBER.

    Not a label typed beside the row: `test_boot_snapshot.py` reads the dispatch table out of the
    mapped ROM and holds every one of these names to the entry it claims, so a label built from them
    cannot claim a function number the ROM does not give it. An interrupt handler has no function
    number — it is dispatched rather than called — so its label carries its VECTOR instead, which
    its own battery reads out of the captured table.
    """
    handler = isr.HANDLER_OF_TRAMPOLINE.get(entry)
    if handler:
        return f"{handler.name} handler (vector ${handler.vector:02x})"
    address = _entered_routine(entry)
    name = _routine(entry)
    # THE UNNUMBERED CHECK COMES FIRST, and it is the address that decides it: a routine nothing
    # dispatches has no number to name it by, and asking `addrs` for a `<NAME>_FN` first would let a
    # constant that merely happens to have one relabel it.
    if address in UNNUMBERED_ROUTINE_NAMES:
        return f"{UNNUMBERED_ROUTINE_ROLES[name]} (${address:x})"
    trap_name, _, routine = name.partition("_")
    return f"{trap_name} {routine.capitalize()} (${getattr(addrs, f'{name}_FN'):02x})"


def _symbol(entry):
    """...and the C core's name, which is the same `addrs.h` name lower-cased."""
    return _routine(entry).lower()


def _case_label(name, symbol):
    """The case's own name out of `VERIFIED_CASES`, with the symbol its front repeats trimmed off —
    the function column already carries that."""
    prefix = f"{symbol}, "
    return name[len(prefix):] if name.startswith(prefix) else name


def _resolve(args, pokes, regs):
    """The C argument values for one case: literals as they stand, and everything else read out of
    the case's own staged argument frame or its input registers."""
    frame = pokes.get(abi.FIRST_ARG, b"")
    out = []
    for arg in args:
        if isinstance(arg, EntryRegister):
            out.append(regs.get(arg.name, 0))
        elif isinstance(arg, (FrameArg, FrameAddress)):
            out.append(arg.of(frame))
        else:
            out.append(arg)
    return tuple(out)


def _pokes_for(call, pokes):
    """The case's pokes, plus the copy of its argument frame an IN/OUT pointer argument points at.

    Added only for a call that HAS one, and laid at `POINTER_STORAGE` — see that constant. The bytes
    are the case's own, so the two sides start from one declaration of what the arguments are.
    """
    if not any(isinstance(arg, FrameAddress) for arg in call.args):
        return pokes
    frame = pokes[abi.FIRST_ARG]
    # The copy's placement, re-tested where its size is known rather than left to the comment above:
    # the band has moved once already, and a copy that fell out of it would be OUR write-back landing
    # in compared image, while one that fell into the frames would be overwritten by a push.
    assert emu.STACK_GUARD_LO <= POINTER_STORAGE and \
        POINTER_STORAGE + len(frame) <= emu.STACK_TOP - emu.STACK_SCRATCH, (
            f"the {len(frame)}-byte frame copy at {POINTER_STORAGE:#x} is not inside "
            f"[{emu.STACK_GUARD_LO:#x}, {emu.STACK_TOP - emu.STACK_SCRATCH:#x}) — the part of the "
            f"band harness.diff_spans() drops that no frame of either side reaches")
    return {**pokes, POINTER_STORAGE: frame}


def _stop_pc(case):
    """The PC a case's differential stops at, or 0 for a routine that reaches its own `rts`."""
    return test_boot_snapshot.fields(case)[7]


def _row(case):
    """One `VERIFIED_CASES` entry as a bench row, or None when this file cannot make one.

    Two reasons it cannot, and they are different failures: no `CALL` entry says how to call the
    routine — which `UNPRICED` reds on — or the case is a CHECKPOINT, which no `CALL` entry could
    rescue. Tier 3 runs both columns to the routine's own `rts`, and `Pterm` has none.
    """
    name, entry, regs, pokes, psg_seed, io_seed, schedule, stop_pc = test_boot_snapshot.fields(case)
    if stop_pc:
        return None
    call = CALL.get(_routine(entry))
    if call is None:
        return None
    symbol = _symbol(entry)
    # A case entered at a STAGED trampoline is a row about the routine that trampoline reaches, and
    # its column carries what the trampoline itself cost — which our build, called as a C function,
    # never runs. The two kinds have their own measured constants (`isr.py`, `gemdos.py`).
    handler = isr.HANDLER_OF_TRAMPOLINE.get(entry)
    slice_of = gemdos.ROUTINE_OF_TRAMPOLINE.get(entry)
    if handler:
        address, staged_entry = handler.entry, isr.STAGED_ENTRY_COST
    elif slice_of:
        address, staged_entry = slice_of, SLICE_ENTRY_COST[entry]
    else:
        address, staged_entry = None, (0, 0)
    return Row(_function_label(entry), _case_label(name, symbol), entry, symbol,
               _resolve(call.args, pokes, regs), regs, _pokes_for(call, pokes), psg_seed, io_seed,
               call.returns, False, address, staged_entry, (0, 0), schedule)


def _transcription_row(case):
    """One `trap.CASES` entry as a bench row.

    It carries no `CALL` entry and needs none: a transcription has no C signature to be called
    through — both sides are entered at the CALLER the case staged, and the handler each reaches is
    the longword at `abi.FIRST_ARG` (`RomBench.measure_transcription`). So the only things this adds
    to the case are the label, which is the entry the case came in through, and what that caller
    costs — which the case carries because the shape it staged is what decides it.
    """
    name, symbol, caller, regs, pokes, caller_cost = case
    return Row(TRANSCRIPTION_LABELS[symbol], name, caller, symbol, (), regs, pokes, None, None,
               RETURNS_NOTHING, True, getattr(addrs, symbol.upper()), (0, 0), caller_cost)


def _isr_transcription_row(case):
    """One handler's WHOLE-HANDLER row: `src/bios/isr.S` against the ROM's own entry sequence.

    The C row above it prices the reconstruction's CORE — the handler as a C function, entered
    directly while the original runs the whole of itself, which is why its column carries a `movem`
    pair ours has no register file for (mechanism (I)). This row has no such hole: both sides are
    entered at the same staged trampoline and ours runs the same brackets the ROM does, so the
    ratio is the two handlers' own cycles and nothing else.
    """
    return Row(f"{case.handler.name} ISR entry (vector ${case.handler.vector:02x})",
               _case_label(case.name, case.handler.constant.lower()), case.caller, case.symbol,
               (), case.regs, case.pokes, case.psg_seed, case.io_seed,
               RETURNS_NOTHING, True, case.handler.entry, (0, 0), case.shared_entry)


ISR_TRANSCRIPTION_CASES = (test_bios_hbl.TRANSCRIPTION_CASES + test_bios_vbl.TRANSCRIPTION_CASES
                           + test_bios_timerc.TRANSCRIPTION_CASES
                           + test_bios_ikbd.TRANSCRIPTION_CASES)

ALL_CASES = tuple(test_boot_snapshot.VERIFIED_CASES) + EXTRA_CASES
ROWS = (tuple(row for row in (_row(case) for case in ALL_CASES) if row is not None)
        + tuple(_transcription_row(case) for case in trap.CASES + tuple(gemdos.TRANSCRIPTIONS))
        + tuple(_isr_transcription_row(case) for case in ISR_TRANSCRIPTION_CASES))
# ...and the verified cases this file does NOT price, which `test_tier3.py` reds on. Recorded rather
# than raised at import, so the gate names them all at once instead of the collection dying on the
# first: a function reconstructed without a Tier 3 row is the state the numerator exists to end.
UNPRICED = tuple(case[0] for case in ALL_CASES
                 if not _stop_pc(case) and _row(case) is None)
# ...and the ones it does not price for a reason no `CALL` entry could answer: a CHECKPOINT case
# stops at a PC instead of at an `rts`, so there is no second column to measure. Listed rather than
# silent — the table prints them under itself — but NOT in `UNPRICED`, because that list is the
# gate's "somebody forgot to say how this is called" and these are said.
CHECKPOINTS = tuple(case[0] for case in ALL_CASES if _stop_pc(case))


def measure(row, bench):
    """One row's `Measurement` — which is also its second differential, so this raises on a target
    build that does not equal the original.

    The two relations are the kit's, not a choice made here: a C core owes its caller a return value
    and the callee-saved file, and an m68k transcription owes it the WHOLE register file the ROM's
    own instructions leave (`tools/recreate_kit/rom_bench.py`).
    """
    if row.transcription:
        return bench.measure_transcription(row.entry, row.symbol, row.regs, pokes=row.pokes,
                                           psg_seed=row.psg_seed, io_seed=row.io_seed,
                                           staged_entry=row.staged_entry,
                                           shared_entry=row.shared_entry)
    return bench.measure(row.entry, row.symbol, args=row.args, regs=row.regs, pokes=row.pokes,
                         psg_seed=row.psg_seed, io_seed=row.io_seed, returns=row.returns,
                         staged_entry=row.staged_entry, schedule=row.schedule)


def pin_of(row):
    """The `(ratio, why)` this row is pinned at, or None."""
    return PERF_ACCEPTED.get((row.symbol, row.case))


# The two rows the DISPATCHED-CALL cost is read off: a whole `Bios(Drvmap)` through the dispatcher,
# and Drvmap entered directly. The difference between what the ORIGINAL spends on the two is the
# dispatcher's own cycles — the number the leaf rule's fraction is taken of, measured on this
# machine by this table rather than written down beside it.
DISPATCH_WHOLE_CALL = ("bios_trap13", "BIOS Drvmap, no arguments")
DISPATCH_LEAF = ("bios_drvmap", "bios_drvmap")


def row_named(key):
    """The row one `(symbol, case)` names — the key `PERF_ACCEPTED` and the rule are written in."""
    return {(row.symbol, row.case): row for row in ROWS}[key]


def dispatch_cycles(measurement_of):
    """What the machine spends REACHING a trap leaf, in cycles — 464 as measured today.

    Both halves are rows of this table, so this measures what the gate measures: the whole call less
    the leaf it dispatched to. A leaf's own cost is already net of the entry observation and the
    whole call's is also net of its staged caller, so the subtraction leaves the dispatcher alone.

    `measurement_of(key)` is how a caller hands over the two `Measurement`s — the table already has
    every row measured and the gate measures the pair on its own — so the SUBTRACTION is stated
    once whoever asks.
    """
    return (measurement_of(DISPATCH_WHOLE_CALL).original_net
            - measurement_of(DISPATCH_LEAF).original_net)


def rule_admits(row, measured, dispatch):
    """THE LEAF RULE: is this row's excess small enough, both ways, to need no written entry?

    `dispatch` is what a trap call costs before the leaf runs (`dispatch_cycles`). A row the
    listing does not name is never admitted — see `IMAGE_POINTER_LEAVES`.
    """
    if (row.symbol, row.case) not in IMAGE_POINTER_LEAVES:
        return False
    excess = measured.recreate_net - measured.original_net
    return excess <= LEAF_SLACK_CYCLES and \
        excess <= LEAF_SLACK_FRACTION * (dispatch + measured.original_net)


def verdict(row, measured, dispatch):
    """What the gate makes of one measurement — THE SINGLE RULE, read by the table and the gate.

    "ok" — under the bar and not pinned. "pinned" — under the bar, measuring what it was pinned at.
    "accepted" — over the bar, and a written entry says so. "rule" — over the bar, and the LEAF RULE
    admits it on the measured excess. "DRIFTED" — pinned, and no longer that number. "OVER" — over
    the bar with nothing carrying it.
    """
    pin = pin_of(row)
    if pin and abs(measured.ratio - pin[0]) > RATIO_TOLERANCE:
        return "DRIFTED"
    if measured.ratio <= TIER3_FUNCTION_BAR:
        return "pinned" if pin else "ok"
    if pin:
        return "accepted"
    return "rule" if rule_admits(row, measured, dispatch) else "OVER"


FAILED = ("OVER", "DRIFTED")

# How wide the ROM-address column renders: `$fc1510` and two spaces. Every entry in this ROM is six
# hex digits, so it is a constant rather than a measurement over the rows.
ADDRESS_WIDTH = 9


def table(bench):
    """Every row measured, as the lines `make bench` writes and STATUS.md quotes.

    MEASURED FIRST AND JUDGED AFTER, because one of the verdicts is about the others: the LEAF RULE
    is a fraction of what a trap dispatch costs, and that is two of these rows (`dispatch_cycles`).
    """
    # One pass, keyed by the row, so `dispatch_cycles` below re-uses the pair rather than running
    # the oracle over them a third and fourth time.
    measured = [(row, measure(row, bench)) for row in ROWS]
    by_name = {(row.symbol, row.case): m for row, m in measured}
    dispatch = dispatch_cycles(by_name.__getitem__)
    overhead_insns, overhead_cycles = bench.overhead
    lines = [
        "Tier 3 — the recreate against the original, same case, same instrument (Musashi).",
        f"Costs are the oracle's own and include the {overhead_insns} instruction / "
        f"{overhead_cycles} cycles it charges before either entry executes anything; the RATIO is "
        f"net of that on both sides.",
        f"Bar: ratio <= {TIER3_FUNCTION_BAR:.2f} per function; a pinned row must stay within "
        f"{RATIO_TOLERANCE:.2f} of what it was pinned at.",
        f"A TRANSCRIPTION's row is a whole call — an exception handler can only be entered through "
        f"a caller — so its ratio is also net of the staged caller both sides run (trap.py's "
        f"`caller_cost`: 7 / 106 with no arguments, +1 / +12 per argument word).",
        f"`rule`: over the bar, and admitted by the LEAF RULE — an (A)-only trap leaf whose excess "
        f"is <= {LEAF_SLACK_CYCLES} cycles and <= {LEAF_SLACK_FRACTION:.1%} of the "
        f"{dispatch} cycles this table measures a trap dispatch at, plus the leaf's own.",
        "",
    ]
    # Widths from the rows themselves rather than guessed: a case label one character over a fixed
    # column pushes every figure on that line out of its column, and a table that only lines up for
    # today's labels is one nobody will keep lined up.
    name_width = max(len(row.function) for row in ROWS) + 2
    case_width = max(len(row.case) for row in ROWS) + 2
    # The ADDRESS column is what makes the file quotable: STATUS.md's ledger is keyed by ROM address,
    # and `test/test_status.py` pins its Tier 3 cells against these lines by that key.
    lines.append(f"{'function':<{name_width}}{'address':<{ADDRESS_WIDTH}}{'case':<{case_width}}"
                 f"{'original':>14}{'recreate':>14}{'ratio':>8}")
    lines.append(f"{'':<{name_width}}{'':<{ADDRESS_WIDTH}}{'':<{case_width}}"
                 f"{'insns/cycles':>14}{'insns/cycles':>14}")
    failed = []
    for row, m in measured:
        state = verdict(row, m, dispatch)
        lines.append(f"{row.function:<{name_width}}"
                     f"{f'${row.address or row.entry:x}':<{ADDRESS_WIDTH}}"
                     f"{row.case:<{case_width}}"
                     f"{f'{m.original_insns}/{m.original_cycles}':>14}"
                     f"{f'{m.recreate_insns}/{m.recreate_cycles}':>14}"
                     f"{m.ratio:>8.2f}  {'' if state == 'ok' else state}")
        if state in FAILED:
            failed.append((row, state))
    if CHECKPOINTS:
        lines.append("")
        lines.append(f"{len(CHECKPOINTS)} verified case(s) are CHECKPOINTS and have no second "
                     f"column: {', '.join(CHECKPOINTS)}")
    if UNPRICED:
        lines.append("")
        lines.append(f"{len(UNPRICED)} verified case(s) with NO row here: {', '.join(UNPRICED)}")
    if failed:
        lines.append("")
        lines.append(f"{len(failed)} row(s) the gate refuses: "
                     + ", ".join(f"{row.symbol} / {row.case} ({state})" for row, state in failed))
    return lines, bool(failed or UNPRICED)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=None,
                        help="also write the table here — the file `make bench` produces and "
                             "STATUS.md's Tier 3 column is pinned against (test/test_status.py)")
    options = parser.parse_args(argv)

    lines, refused = table(RomBench())
    text = "\n".join(lines) + "\n"
    if options.out:
        options.out.parent.mkdir(parents=True, exist_ok=True)
        options.out.write_text(text)
    print(text, end="")
    # NON-ZERO, so a `make bench` that printed a table nobody read still FAILS. The gate is
    # test_tier3.py, but a report is the thing a reader trusts, and one that ends in a refused row
    # — or in a verified case nobody priced — must not exit 0.
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main())
