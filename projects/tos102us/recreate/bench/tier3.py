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
import ctypes
import functools
import os
import re
import struct
import sys
from collections import namedtuple
from pathlib import Path

RECREATE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RECREATE.parents[2] / "tools"))     # reverse/tools — the shared recreate kit
sys.path.insert(0, str(RECREATE / "tools"))                # this project's own tools
sys.path.insert(0, str(RECREATE / "test"))                 # ...and the cases the differentials use

# FIRST, before any module that derives: it stamps the tree's files as this process finds them (`test/derived.py`,
# "the key names the tree this process is made of").
import derived                                             # noqa: E402,F401
import fork_pool                                           # noqa: E402
from recreate_kit import project                           # noqa: E402
project.load(RECREATE)

from recreate_kit import rom_bench                         # noqa: E402
from recreate_kit.rom_bench import (BENCH_DIR, BENCH_ELF, Measurement, vet_the_run_just_made,   # noqa: E402
                                    watched_original)
from harness import BASE_IMAGE, addrs, diff_spans, differing_addresses, emu, make_image   # noqa: E402  (binds the kit)
import abi                                                 # noqa: E402
import case                                                # noqa: E402
from case import tier3_dropped, tier3_unanswered           # noqa: E402  (every component's rows' drops, unanswered)
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
# ...and the four ISR batteries, for their TRANSCRIPTION cases — `src/bios/isr.S`, the handlers a
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
# ...and the byte-exact `.S` machinery — the TRANSCRIBED table, every component's `.S` rows, the call graph (T→) reads.
import transcription                                       # noqa: E402
# ...and the VDI's door, whose `addrs.h` convention, primitive contracts and Alcyon signatures the VDI rows
# derive from — every battery that declares one is imported by `test_boot_snapshot` above.
import vdi                                                 # noqa: E402
# ...and the naming rule every ROM-routine row is labelled and symbolled by (VDI, Line-A, AES alike).
import routines                                            # noqa: E402
# ...and the shipped blob's glue generator, for the thunks mechanism (T→G) counts the cycles of.
import shipped_glue                                        # noqa: E402
# ...and the escape's transcription battery, for the ROM spans escape.S transcribes and the prefix of the thunks it
# reaches the console's C through — what mechanism (T←) splits an escape `.S` row by.
import test_vdi_escape_transcription as escape_transcription   # noqa: E402
# ...and the AES's door, for the spans mechanism (V) holds the ROM's side of a row through the OS to: its text and the
# Line-F handler's RAM copy.
import aes                                                 # noqa: E402
# ...and the event door, whose watch over a run (`DoorStops`) mechanism (EV) windows BOTH sides' runs with.
import aes_event                                           # noqa: E402
# ...and the opcode words, for the one a listing is searched for: `trap #2`.
import opcodes                                             # noqa: E402

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
# WHAT THE ROWS ABOVE THE BAR HAVE IN COMMON, said once so no entry need say it again. The lettered
# mechanisms below cover all of them, and none is a defect in a reconstruction. All but two are named
# by the entries that carry them; (T) and (T→) are RULES, and carry their rows with no entry at all:
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
#       page off it (`$fc2a0c`'s first instruction is `lea $c76(a5),a0`). A C handler body is handed
#       that zero as its IMAGE ARGUMENT instead, which the C needs and the vector does
#       not, so `include/staged_call.h` pins A5 as an OPERAND of every vector call: one
#       `suba.l %a5,%a5`, 8 cycles, per call. It is a CORRECTNESS guarantee with no Tier 1 surface —
#       the cross-compiled `isr_acia` spun to the oracle's cap without it in the build that found
#       it, and passes by coincidence in a build where GCC happens to hold the image pointer in A5 —
#       so the rows that carry it are PINNED: deleting it leaves every differential green and moves
#       them to the ratios each entry names.
#
#       FOR THE THREE HANDLERS IT IS MOOT ON TARGET NOW: `src/bios/isr.S` ships each as the ROM's own
#       instructions, `lea 0,a5` and all, and the C bodies these rows price are twins no entry calls.
#       The pin still serves every OTHER C caller of a RAM vector (`src/vdi/screen.c`'s tick chain).
#
#   (T) SHIPS AS THE ROM'S OWN INSTRUCTIONS. The user's rule for the hand-written 68000: port it to C
#       first, and where the C measures over the bar, SHIP a byte-pinned `.S` transcription instead —
#       `include/transcribed.h`, the TRANSCRIBED table, is the one place that says which. A C row of
#       a routine in that table is over the bar by design and is admitted, verdict `transcribed`, ONLY
#       while EVERY one of the routine's `.S` rows measures at or under the bar (`ships_within_bar`):
#       derived from the measurements, never typed, so deleting a `.S` row or letting one drift over the
#       bar reds the C rows with it. A WRITTEN ENTRY for a `.S` row carries nothing here — the one way a
#       `.S` row over the bar still carries its routine's C rows is mechanism (T←) below, derived as well.
#       What those C rows price is the C Tier 1 proves, and where their cycles go is the same few things
#       each time: (A) and (M) on every entry, the callee-saved `movem` pair GCC opens before the first
#       branch, and hand 68000 GCC does not emit — (E) twice over in the
#       palette pair; in the raster primitives a write-mode arm reached by `jmp (a5)` through a
#       PC-relative table, a Bresenham that runs per-plane code it built on the stack, a span count spent
#       by two `subq`/`bcs` before a `dbf`; and in the pure helpers the carry an `add.w` leaves, a
#       `-(An)`, a compare against memory in a `dbf` loop.
#   (T→) SHIPS THROUGH A CALL. The C that CALLS a transcribed routine — a VDI function round `$a00e`, the
#       polygon layer round `$a003`/`$a006`, `v_show_c` round the sprite — reaches the `.S` on target, through
#       glue, and the C twin's cycles are nobody's cost. So every row whose C reaches a transcribed core (the
#       m68k build's own call graph, `transcription.reaching_transcribed_cores`) is measured on the SHIPPED
#       CONFIGURATION's blob instead (`build/bench_shipped/`, `../Makefile`): the same sources with each
#       called core replaced by a thunk GENERATED from the table (`bench/shipped_glue.py`) that enters the
#       `.S`. Its verdict is `through` at or under the bar and OVER above it — derived, never typed: a `.S`
#       that drifts moves its callers' rows with it, and `test_tier3.py` refuses a written entry for any of
#       them. The ratio includes the thunk's `movem` pair, which a shipped build pays.
#   (T→G) THE GLUE ITSELF. A thunk is the one thing in the shipped configuration no ROM routine has: the ROM's
#       compiled caller pushed the Alcyon frame, or loaded the argument registers, INLINE on its way to the
#       `jsr`, where a GCC caller hands its longword slots to a thunk that saves the callee-saved registers
#       the entry changes, re-pushes the slots as the entry's frame, and makes a second `jsr` — measured on
#       do_arrow's arrowhead, 128 cycles per smul_div call and 216 per filled_poly one, 94% of that row's
#       excess. So every (T→) row is PROFILED as it is measured (the oracle's cycle-per-PC tally) and the
#       cycles spent inside the generated thunks' own bytes are counted (`glue_ranges`: the shipped ELF's
#       SIZED symbols of `bench/shipped_glue.py`'s thunks). A row over the bar as shipped whose ratio NET OF
#       THAT GLUE is at or under it is verdict `glue` — derived, never typed; the table prints both ratios.
#       A row over the bar even net of the glue is its OWN body's cost: OVER, unless an entry accepts that
#       body's mechanism at the shipped number. (The letter is not (G): that one is taken, above.)
#   (T←) A `.S` THAT CALLS C — (T→)'s mirror image. The VDI escape (`src/vdi/escape.S`) is the ROM's instructions, but
#       its table and branches name the VT52 CONSOLE's routines, which ship as C (`src/bios/vt52.c`): escape.S reaches
#       each through a THUNK of its own (a sized `escape_to_<body>` symbol), and what such a `.S` row measures is its
#       own instructions PLUS the thunks PLUS the console's C, against the ROM's own instructions plus the ROM's
#       console. So every `.S` row of a routine in `CALLS_INTO_C` is PROFILED (the oracle's cycle-per-PC tally, both
#       sides, the ROM window included) and split: OUR side's OWN cycles are everything the blob ran less the thunks'
#       bytes and less the C they reach (the m68k call graph's closure of the thunks' callees); the ROM's are the
#       cycles inside the ROM spans the `.S` transcribes. A row over the bar whose OWN ratio is at or under it is
#       verdict `own` — derived, never typed, and `test_tier3.py` refuses a written entry for it — and the rest of its
#       cost is the console's C against the ROM's console, which is exactly what `Bconout(CON:)`'s rows price: the
#       rule carries a row only while every acceptance it CITES (`CONSOLE_C_ACCEPTED_BY`) still stands. A spill in
#       the `.S`'s own instructions, or a call out of it to C that is not the console's, lands on OUR side of the own
#       ratio and reds the row — any row of the routine, under the bar as a whole or not. The table prints both ratios.
#       ONE MEASURED LENIENCE: a ROM byte the escape and the console BOTH execute counts as the escape's on the ROM's
#       side — vq_chcells' `rts` ($fc444e), which ESC A-D and ESC J branch to when they refuse a move — so the rows
#       refused at an edge read 0.85 (88 cycles against 104), 16 cycles a spill could hide in on those rows alone.
#   (V) THROUGH THE OS. The AES draws through the VDI by `trap #2` (`aes/gsx.h`), and on target our C's trap lands in
#       the snapshot's own vector — GEM's selector switch, the BIOS's VDI door, the ROM's VDI, Line-A — exactly where
#       the ROM's does: both columns run those bytes, and they dwarf the AES's part (measured: v_pline's triangle row,
#       the OS both run is 31,224 of the ROM's 31,774 cycles, 98%), so a whole-run ratio would let an AES body twice the
#       ROM's pass. So every row whose m68k C REACHES the trap (the call graph's closure onto a function holding
#       `trap #2`) is PROFILED and priced on its OWN cycles: OURS every blob cycle less the glue's (T→G); the ROM's the cycles
#       at PCs in the AES text and in the Line-F handler's RAM copy (`AES_OWN_SPANS`: the Line-F overhead IS the ROM
#       AES's own cost), less the trap's selector switch both sides run. Everything else — the trap path, the VDI,
#       Line-A, code the VDI builds on the stack, staged stubs — is in neither, and the ROM's own is measured on a run
#       of the original ALONE, so a C that strayed into the AES's ROM bytes cannot be credited with them
#       (`_measure_through_the_os` refuses it). The own ratio is printed in the ratio column, the whole run's beneath.
#       At or under the bar it is `net` only while it stays there WITH the glue counted back on our side ((ours + glue)
#       / the ROM's); a row under the bar only because the thunks are off is verdict `glue`, exactly as (T→G) labels the
#       same lenience, and the line beneath prints the ratio with the glue. Over the bar on the own ratio, OVER unless
#       an entry accepts it. An entry — an acceptance or a pin under the bar — is written at the number that SHIPS, the
#       own ratio WITH the glue counted back, as a (T→) row's is at its shipped one; a pinned row still splits `net`
#       from `glue`. Derived, never typed: `test_tier3.py` refuses a written entry for a row the rule carries.
#   (EV) THROUGH THE EVENT LAYER — (V) for the AES's own event layer, which no C holds yet. A row whose C reaches the
#       event door (`aes/evdoor.h`: on target the ROM's call itself, its frame pushed and a `jsr` to ev_multi or ap_rdwr)
#       runs that ROM code on both sides, and it is AES text: so BOTH runs are WATCHED, stopped at each door entry and at
#       the return address its call left (`DoorWindows`: our `jsr`'s, the ROM's Line-F word's), and the AES-span cycles
#       between are a WINDOW, the event layer's. The two sides' windows must be EQUAL, one by one (the event layer is
#       the same code over the same machine on both); the ROM's own is its AES-span cycles LESS them; ours is (V)'s, the
#       frame's pushes in it as the ROM's Line-F word is in its; an AES-span cycle of ours outside every window is
#       refused by name, and the OS both ran must still cost both sides the same. Priced, judged and labelled as (V)
#       rows are (`net`/`glue`/OVER), the table's line beneath counting the windows. Derived: the door calls are the
#       blob's `jsr`s into the AES text, the rows the call graph's callers of the functions holding one. (The letter is
#       not (E): that one is taken, above.) A LONG SESSION — one call of hundreds of thousands of instructions — is
#       priced by its SLICES, a row each (`aes_event.register_slices`): both sides run the whole session and are held
#       to all of the above over it, and the row's costs are those between two arrivals both sides make at one PC (a
#       door call, a trap taken, the entry, the return), our run held to the ROM's at both (`_priced_on_its_slice`).
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
    # WHAT THIS PIN CANNOT SEE: it catches the bracket DELETED (about -0.05), but a cycle count is blind
    # to every mutant that spends the same instructions — the restore moved BEFORE the exchange, the
    # exchange moved OUTSIDE the bracket, the restore writing `mask | $700` (the tick masked for good on
    # target). The surface that sees them is the SR itself: the target C run from SR = $2000 / $2300
    # with the SR recorded at the USER_TIM write and on return, which needs the kit to report SR (the
    # oracle enters at IPL 7 and reports none) — PARKED as a kit item, with SR/A7 in `emu.REPORTED_REGS`.
    ("vdi_vex_timv", "exchange"): (
        1.09, "under the bar and pinned for `xbios_giaccess`'s reason: the `ori.w #$700,sr` bracket "
              "round the USER_TIM exchange (ipl.h) is this cycle count's alone to see — its deletion, "
              "not its placement (above)"),
    # The two rows that are over the bar EVEN NET OF THE GLUE (T→G): the callee is the `.S`, and what is left
    # is the caller's own body — (A) and (D) through the call. Each C passes the image and the caller's D0 to
    # a register routine the ROM enters with nothing (`vdi/helpers.h`, `vdi/mouse.h`), and the call lands
    # in a thunk that loads D0 and enters the `.S`: two pushes, a pop, and the thunk's `move.l`/`jsr`/`rts`
    # where the ROM's one `jsr` was the whole of it.
    ("vdi_vq_key_s", "every bit set but Control"): (1.52, "(A) + (D) through get_kbshift's glue, as shipped: "
                                                          "220 -> 314 cycles"),
    ("vdi_choice", "sampled"): (1.49, "(A) + (D) through poll_choice's glue, as shipped: 270 -> 382 cycles. "
                                      "It read 0.62 while GCC inlined poll_choice's C; a core the target "
                                      "build replaces with its `.S` cannot be inlined (`TRANSCRIBED_CORE`)"),
    # A (V) row over the bar on its OWN cycles, where nothing is shared: gsx_moff's open nest calls nothing, and the
    # ROM's `tst.w $c86a / bne / addq.w #1,$c86a / rts` is the whole of it. The C's floor is (A): the image pointer
    # loaded (`movea.l 4(sp),a0`) and $c86a, past a 16-bit displacement, added to it (`adda.l #imm`) — the rest is the
    # ROM's own `move.w/beq/addq.w/move.w/rts` (the hide path split off so this one builds no frame, `src/aes/gsx.c`).
    # A byte-exact `.S` is impossible: the hide path's Line-F call word cannot execute in an AES `.S`, and a `.S` that
    # reached C instead through a thunk of its own ((T←), as the VDI escape does) would no longer be the ROM's bytes.
    ("aes_gsx_moff", "the nest already open"): (1.23, "(A) on its own cycles, nothing shared: 62 -> 76 cycles"),
    # ...and gsx_graphic's mode already held — the start-up's own call ($fead68, gl_graphic 1 since gsx_wsopen): the
    # ROM's `move.w 4(sp),d0 / lea $c90c,a1 / cmp.w (a1),d0 / beq / rts`, 58 cycles. The C's floor, counted from its
    # instructions: the image pointer loaded (`movea.l 4(sp)`, 16), $c90c's displacement SPLIT between a `lea d16(a0)`
    # (8) and the compare's own (`cmp.w d16(a0)`, 12), the argument word (12), the branch not taken (8) and `rts` (16)
    # = 72 — 4 under an `adda.l` of the whole address (the change of mode split off, `src/aes/gsxif.c`). No `.S`: its
    # other arms make the escapes' Line-F call.
    ("aes_gsx_graphic", "the mode held"): (1.24, "(A) on its own cycles, nothing shared: 58 -> 72 cycles"),

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
    # FIVE WERE RE-PINNED when the target build dropped type-based aliasing (`atari/target.mk`,
    # `-fno-strict-aliasing`): GCC allocates the inlined drivers' registers differently (one more callee-saved
    # register pushed round the whole dispatch), 8-16 cycles either way per arm — on arms this small, a ratio
    # move of 0.03-0.21.
    ("bios_bconout", "midi"): (
        2.82, "(A)+(B): 142 -> 400 cycles over a driver whose whole body is a status read and a "
              "data write — the dispatch chain IS the routine"),
    ("bios_bconout", "no driver"): (
        3.84, "(B) alone, over a driver that is a bare `rts`: 76 -> 292"),
    ("bios_bconout", "printer held off"): (
        1.96, "(A)+(B) over the give-up arm, which is two longword reads and a store: 194 -> 380"),
    ("bios_bconout", "rs232 ring only"): (
        1.87, "(A)+(B): 302 -> 566. The ring put is six field accesses the ROM makes off one `lea`"),
    ("bios_bconout", "rs232 primed"): (
        1.44, "722 -> 1040, and it includes the `ipl.h` bracket around the prime that Tier 1 cannot "
              "see (src/xbios/gibit.c's argument)"),
    # The CONSOLE's accepted rows are also what mechanism (T←) CITES for the escape's `.S` (`CONSOLE_C_ACCEPTED_BY`):
    # escape.S reaches the same C bodies through its thunks, so their cost is accepted here, once.
    ("bios_bconout", "console escape state"): (
        3.24, "(A)+(B) over a state-machine arm whose whole body is `move.l a0,$4a8`: 212 -> 686"),
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

    # ---- THE INTERRUPT HANDLERS (BIOS wave 2) — since wave 18, their C TWINS ----
    # EVERY `isr_*` ROW WITH AN ENTRY BELOW PRICES C THAT DOES NOT SHIP: the handlers are `src/bios/isr.S`, the ROM's
    # own instructions, and these are the twins Tier 1 proves. The entries are kept as written (the HBL's always stood
    # beside a transcribed entry); wiring them into mechanism (T) instead is owed a ruling (STATUS.md, Next).
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
    #       shipped ROM installs in each vector — the ROM's own handler, byte for byte — and its
    #       rows pay the `movem` pair on both sides. Each handler therefore has two rows: the C TWIN,
    #       where (I) still stands and a figure under the bar is under it partly for a reason that
    #       is not a saving, and the ENTRY, where nothing is missing from either column.
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
              "register file for. It is also what says the TWIN's body has not grown (it ships "
              "nowhere: `src/bios/isr.S` is the handler). The row WITHOUT the hole is the table's "
              "`isr_vbl_entry / a quiet frame`, the ROM's own instructions at 1.00, which has no entry"),
    ("isr_vbl", "a monitor change"): (
        1.00, "PINNED, not accepted: the arm is 2001 passes of `dbf` doing nothing — the shifter "
              "settling — and a delay's only surface is its cost. Delete the loop and every Tier 1 "
              "case stays green (`src/bios/vbl.c`); this row is 20,840 cycles against 20,870. The "
              "RATIO is too coarse to hold the count on its own — a pass either way moves it by "
              "0.0005 — so `test_bios_vbl.py` pins the absolute number as well"),
    ("isr_vbl", "a frame with everything queued"): (
        1.14, "(A) and (L) over a blank that does everything at once: 2062 -> 2356 cycles. The "
              "queue walk and the dump hook are two staged calls, and GCC saves round them — though "
              "NOT what the ROM's `movem.l d7/a0` saves: this twin holds a pointer in A6 across "
              "each, which is why it does not ship (`src/bios/vbl.c`)"),
    ("isr_timer_c", "a divided-away tick"): (
        1.18, "(A) and (H): 102 -> 120 cycles, 5 instructions to 9. Three of the ROM's five are "
              "`addq.l`/`rol.w`/`bclr` straight to memory, and every one of them is a load, an "
              "operation and a store here"),
    ("isr_timer_c", "a serviced tick"): (
        1.08, "PINNED under the bar: (A), (H) and (L) spread over a tick that steps the sound "
              "driver, the auto-repeat and the OS vector come to 978 -> 1052 cycles. The pin says "
              "the C TWIN's body has not grown; what runs 200 times a second is `src/bios/isr.S`'s "
              "entry, the ROM's own instructions, whose row is 1.00 and has no entry. It was "
              "1.06 (1040) until BIOS wave 3: the auto-repeat's injection at `$fc2c42` is a real "
              "call to `kbd_queue_key` in the twin rather than the halt it was"),
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

    # ---- ...and the same four handlers as `src/bios/isr.S` installs them: NO ENTRY, BY DESIGN ----
    # The `... ISR entry` rows carried eight written entries here (the blank 1.23 / 1.24 and its 1.01 pin, the
    # serviced tick 1.33, the ACIA 1.71 / 1.52 / 1.12 / 1.18) while each handler was the ROM's entry sequence round a
    # C BODY. They are the ROM's own instructions now (`src/bios/isr.S`, byte-pinned by each handler's battery), by
    # the project's rule for hand 68000 whose C measures over the bar — and every one of those rows measures 1.00,
    # instruction for instruction and cycle for cycle. A row at 1.00 needs no entry, and one over the bar here would
    # be a transcription that stopped being one: `OVER`, with nothing to carry it.
    #
    # THE C ROWS ABOVE KEEP THEIR ENTRIES, as the HBL's always has beside its transcribed entry: each prices a C TWIN
    # no entry calls — what Tier 1 proves and nothing ships — and none of them moved. The two REAL-VECTOR rows of the
    # ACIA still run the ROM'S OWN chain under both columns (the captured machine's `$fc29fc` / `$fc2a0c` are left in
    # KBDVECS), so `acia_service.c` and `keyboard.c` are priced by their own rows below and not by those.

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
              "fixed at 0. Priced AS SHIPPED (T→) since the loader's span clear became a `.S`; this "
              "arm reaches none of it, and measures the same 226 cycles on either blob."),

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
    # (N) (M)'s DUAL: A ROUTINE WHOSE ANSWER IS SEVERAL REGISTERS. A Line-A primitive answers in D0-D2/A0-A2
    #     and a C function returns one register, so the core returns D0 and writes the rest through a
    #     pointer (`src/vdi/linea.c`, `test/vdi.py`'s `declare_primitive`): one `movea.l 8(sp),a0` plus
    #     a store per register, where the ROM's `lea`s WERE the answer. Tier 1 compares every register;
    #     this column holds D0 and the cost. Its one example, $a000 (2.43: four `lea`/`move.l` against four
    #     stores through the pointer), ships as the ROM's own instructions (`src/vdi/entry.S`), and mechanism
    #     (T) carries its C row — so no entry here names it.

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
RETURNS_WORD = 2            # int16_t — an Alcyon `int`, whose callers read D0.w alone (`vdi/helpers.h`)
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
    # it reads off the frame. `arg_address(0)` is the copy of that frame at POINTER_STORAGE.
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
# `dropped` is the case's own `((lo, hi, why), ...)` (`case.tier3_dropped()`, every component's): the spans its image compare leaves
# out, each vetted by `RomBench` and printed under the row. `()` for every row but a few whose C parks a return
# address the ROM parks its own in; the battery's own differential still compares those bytes.
# `delivered` is the case's own `{door call: (found, wrote)}` (`test_boot_snapshot.delivered_of`): the interrupts a row
# is TAKEN THROUGH, laid at the entry of the same door call on every run of it — both sides (EV). `{}` for every other.
# `slice` is the case's own `aes_event.Slice` (`aes_event.SLICED_ROWS`): the part of a long session the row is PRICED
# on — its run between two arrivals both sides make (MECHANISM (EV)'s slices, below). None for every other row.
# `registered` is the name the row's case is REGISTERED under (`test_boot_snapshot.VERIFIED_CASES`, and for a row taken
# through interrupts `aes_event.INTERRUPTED_ROWS`): what its session is found by (`session_of`). `case` is that name
# TRIMMED for the table (`_case_label`), which no registry is keyed by. None for a row no `VERIFIED_CASES` entry makes.
Row = namedtuple("Row", "function case entry symbol args regs pokes psg_seed io_seed returns "
                        "transcription address staged_entry shared_entry schedule dropped delivered slice registered",
                 defaults=(False, None, (0, 0), (0, 0), (), (), {}, None, None))


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

# ---- the VDI's, DERIVED rather than listed, so a band adds one `addrs.h` pair and no line here ----
# A VDI FUNCTION (`VDI_ROM_<FN>` with an `_OPCODE` sibling — `addrs.h`'s convention) takes nothing and
# answers only through memory: its arguments are the arrays the Line-A pointers name, which the case
# staged as image. A LINE-A PRIMITIVE is called as `test/vdi.py`'s `declare_primitive` says — its C
# arguments are the registers named there, and it is priced on D0: `RomBench.measure` compares D0 at the
# signature's width, and a C function cannot leave A0-A2 as a 68000 routine does — so a primitive that
# answers in SEVERAL registers returns D0 and writes the rest through a last pointer, which this column
# hands `POINTER_STORAGE` (the dropped band's floor, see above). Those other registers are Tier 1's to
# compare, register by register (`vdi._run_primitive_at`); this column prices the cost and holds D0.
VDI_FUNCTIONS = sorted(name for name in dir(addrs)
                       if name.startswith(routines.VDI_PREFIX) and hasattr(addrs, name + "_OPCODE"))
CALL.update({name: Call((IMAGE,), RETURNS_NOTHING) for name in VDI_FUNCTIONS})
CALL.update({name: Call((IMAGE, *(EntryRegister(register) for register in contract.arguments),
                         *((POINTER_STORAGE,) if len(contract.results) > 1 else ())),
                        RETURNS_LONG if "d0" in contract.results else RETURNS_NOTHING)
             for name, contract in vdi.PRIMITIVES.items()})
# ...and the VDI's C HELPERS the attribute setters share, entered by `jsr` over an Alcyon frame rather
# than by opcode (`src/vdi/attributes.c`): `VDI_ROM_<HELPER>` in `addrs.h`, core `vdi_<helper>`.
CALL.update({"VDI_ROM_ST_FL_PTR": Call((IMAGE,), RETURNS_NOTHING),
             "VDI_ROM_ARB_CORNER": Call((IMAGE, arg_long(0), arg_word(4)), RETURNS_NOTHING)})
# ...and the ENTRIES (`src/vdi/entry.c`): the dispatcher, a VDI function's shape less the opcode; and `trap #2`'s
# entry, D1 the parameter block, answering the WORD VDI_RESULT (the high half of D0 is the dispatched function's).
CALL.update({"VDI_ROM_DISPATCH": Call((IMAGE,), RETURNS_NOTHING),
             "VDI_ROM_ENTRY": Call((IMAGE, EntryRegister("d1")), RETURNS_WORD)})
# ...and every ALCYON call (`vdi.declare_alcyon`: the pure helpers of `src/vdi/helpers.c`, the polygon and
# contour-fill layer of `src/vdi/fill.c`): WORD arguments decoded out of the frame the case poked and an
# `int` answer in D0.w. DERIVED from the one statement of each core's C signature: the image where the core
# takes it, and every other argument read out of the frame at the offset the widths before it add up to.
# (The register routines among the helpers are `declare_primitive`s above.)
_FRAME_DECODERS = {vdi.WORD_ARG: arg_signed_word, vdi.LONG_ARG: arg_long}
# The answer widths are the differential's own set (`aes.RESULT_WIDTHS`, its keys `test_tier3.py` pins equal to these).
_ALCYON_RETURNS = {ctypes.c_uint16: RETURNS_WORD, ctypes.c_uint32: RETURNS_LONG, None: RETURNS_NOTHING}


def _alcyon_call(signature):
    """The `Call` of an Alcyon routine out of its `vdi.Alcyon` signature."""
    args, offset = [], 0
    for argtype in signature.argtypes:
        if argtype is vdi.IMAGE_ARG:
            args.append(IMAGE)
            continue
        args.append(_FRAME_DECODERS[argtype](offset))
        offset += vdi.ARG_BYTES[argtype]
    return Call(tuple(args), _ALCYON_RETURNS[signature.restype])


# ...less the ones whose C takes an argument no frame carries (`vdi.declare_alcyon`'s `host_arguments`: gemdos_call's
# return site), which no frame could decode — their C rows are unpriced (`test_vdi_helpers_gemdos.py`).
CALL.update({name: _alcyon_call(signature) for name, signature in vdi.ALCYON.items() if not signature.host_arguments})
# ...and THE DISPATCHER'S ENTRY (`src/aes/switch.S`), called as the event layer's C calls it — `aes_dsptch(image)`, the
# pushed image pointer nobody's. No `declare_alcyon` names it: off target dsptch is a header's inline over the
# dispatcher's hook (`aes/switch.h`), with no core of its own name for a declaration to bind.
CALL.update({"AES_ROM_DSPTCH": Call((IMAGE,), RETURNS_NOTHING)})


# Every VDI, Line-A and AES routine `CALL` prices is named by the one naming rule (`test/routines.py`) — its label
# (`Line-A linea_hline`, `VDI vsl_type`, `AES ob_offset`) and its C core both — so none needs a line here, a register
# helper is labelled `VDI` whichever door declared its contract, and an AES routine's `CALL` is its `vdi.declare_alcyon`
# signature's, derived above like every Alcyon core's.
ROM_ROUTINES = sorted(name for name in CALL if routines.prefix_of(name))
UNNUMBERED_ROUTINE_ROLES.update({name: routines.role(name) for name in ROM_ROUTINES})
SYMBOL_OF_ROUTINE = {name: routines.core_symbol(name) for name in ROM_ROUTINES}
UNNUMBERED_ROUTINE_NAMES = {getattr(addrs, name): name for name in UNNUMBERED_ROUTINE_ROLES}

# How a TRANSCRIPTION row names itself, keyed by the blob symbol: `src/bios/trap.S`'s entries and
# `src/gemdos/trap1.S` in one map, because `_transcription_row` reads one list of labels and each
# wave's module owns its own (`trap.LABELS`, `gemdos.LABELS`) — and the TRANSCRIBED table's, every
# component's (`transcription.LABELS`).
TRANSCRIPTION_LABELS = {**trap.LABELS, **gemdos.LABELS, **transcription.LABELS}


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
    """...and the C core's name, which is the same `addrs.h` name lower-cased (less a VDI or Line-A
    routine's `ROM_` — `SYMBOL_OF_ROUTINE`)."""
    name = _routine(entry)
    return SYMBOL_OF_ROUTINE.get(name, name.lower())


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


# Every component's rows' drops, read once: the registries are complete by now (`test_boot_snapshot`, imported above, imports every battery).
DROPPED = tier3_dropped()
# ...and the rows whose answer is compared at no width: an arm on which the ROM leaves its caller's D0.
UNANSWERED = tier3_unanswered()


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
               RETURNS_NOTHING if name in UNANSWERED else call.returns, False, address, staged_entry, (0, 0), schedule,
               DROPPED.get(name, ()), test_boot_snapshot.delivered_of(case), aes_event.SLICED_ROWS.get(name), name)


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


def _table_transcription_row(case):
    """One hand-68000 routine's `.S` row, of any component the TRANSCRIBED table serves (`test/transcription.py`'s
    `register_transcription`): the trap entries' shape, plus the I/O a case declares — the palette pair reads and
    writes the shifter."""
    name, symbol, caller, regs, pokes, caller_cost, io_seed = case
    return Row(TRANSCRIPTION_LABELS[symbol], name, caller, symbol, (), regs, pokes, None, io_seed,
               RETURNS_NOTHING, True, getattr(addrs, transcription.transcription_routine(symbol)), (0, 0), caller_cost)


ISR_TRANSCRIPTION_CASES = (test_bios_hbl.TRANSCRIPTION_CASES + test_bios_vbl.TRANSCRIPTION_CASES
                           + test_bios_timerc.TRANSCRIPTION_CASES
                           + test_bios_ikbd.TRANSCRIPTION_CASES)

ALL_CASES = tuple(test_boot_snapshot.VERIFIED_CASES) + EXTRA_CASES
ROWS = (tuple(row for row in (_row(case) for case in ALL_CASES) if row is not None)
        + tuple(_transcription_row(case) for case in trap.CASES + tuple(gemdos.TRANSCRIPTIONS))
        + tuple(_isr_transcription_row(case) for case in ISR_TRANSCRIPTION_CASES)
        + tuple(_table_transcription_row(case) for case in transcription.TRANSCRIPTIONS))
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


def rom_address(row):
    """The ROM address a row is ABOUT — the key a routine's C rows and its `.S` rows share."""
    return row.address or row.entry


# MECHANISM (T), derived from `include/transcribed.h` (`transcription.TRANSCRIBED`): each TRANSCRIBED routine,
# by its ROM address, and the `.S` rows that price what a target build ships for it.
TRANSCRIBED_AT = {getattr(addrs, transcription.transcription_routine(entry)): entry
                  for entry in transcription.TRANSCRIBED}
SHIPPED_ROWS = {address: tuple(row for row in ROWS if row.transcription and rom_address(row) == address)
                for address in TRANSCRIBED_AT}


def is_transcribed_c_row(row):
    """A C row of a routine the target build ships as its `.S` — the rows (T) is asked about."""
    return not row.transcription and rom_address(row) in TRANSCRIBED_AT


def ships_within_bar(row, measurement_of):
    """(T): is the `.S` a target build ships for `row`'s routine priced, and at or under the bar on EVERY
    row — or over it only where mechanism (T←) carries that `.S` row on its own instructions? A written entry
    never counts. `measurement_of(row)` is how a caller hands over a `Measurement` — the table has every row
    measured, the gate measures on demand — so the rule is stated once whoever asks. No `.S` row at all is a no."""
    shipped = SHIPPED_ROWS.get(rom_address(row), ())
    return bool(shipped) and all(_shipped_row_within_bar(each, measurement_of(each)) for each in shipped)


def _shipped_row_within_bar(row, measured):
    return own_within_bar(row, measured) and (measured.ratio <= TIER3_FUNCTION_BAR
                                              or carried_by_its_own_instructions(row, measured))


# MECHANISM (T→): the C whose cost, as shipped, includes a `.S`, and the blob that prices it as shipped.
SHIPPED_BENCH_DIR = transcription.SHIPPED_ELF.parent
BUILT_ELF = RECREATE / BENCH_DIR / BENCH_ELF


@functools.cache
def _reaching_transcribed_cores():
    graph = transcription.call_graph(BUILT_ELF)
    vet_no_row_is_ambiguous(graph)
    return frozenset(transcription.reaching_transcribed_cores(graph))


def vet_no_row_is_ambiguous(graph):
    """No row's symbol, and no transcribed core, may be a name the call graph QUALIFIED (`transcription.nodes_of_labels`): its
    bare-name node would then be one of several functions of that name, and (T→) could read the wrong one's calls
    — or none — and price the row on the C twin without a word."""
    ambiguous = transcription.qualified_bases(graph) & ({row.symbol for row in ROWS} | set(transcription.TRANSCRIBED_CORES))
    assert not ambiguous, (
        f"{sorted(ambiguous)} name more than one function in the m68k build (a static and a global, or statics in "
        f"several files) — rename the static, so the call graph has one node for the name a row is priced by")


def ships_through_a_call(row):
    """(T→): is `row` the C of a routine that reaches a transcribed core — measured on the shipped blob?"""
    return not row.transcription and row.symbol in _reaching_transcribed_cores()


@functools.cache
def shipped_bench():
    """The SHIPPED CONFIGURATION's blob, loaded once per process."""
    return RomBench(SHIPPED_BENCH_DIR)      # this module's own (the fork codes relocated), over the shipped blob


# MECHANISM (T→G): the bytes of the shipped blob that are glue, and what a row spent inside them.
# ...the generated thunks', and the ALCYON ENTRIES': target-only `.S` that takes a ROM walker's Alcyon frame into a C
# core (`src/aes/obdraw.S`'s just_draw and `src/aes/wmupdate.S`'s newrect and mkrect, each a routine a C caller
# hands everyobj) — a thunk's mirror image, which no ROM routine has
# either. DERIVED: the `.globl`s of `atari/target.mk`'s ALCYON_ENTRY_SOURCES (`transcription.ALCYON_ENTRIES`). Both
# blobs link them, so a (V) row measured on either counts their cycles as glue (`_measure_through_the_os`).
ALCYON_ENTRIES = tuple(sorted(transcription.ALCYON_ENTRIES))


@functools.cache
def sized_glue(elf, names):
    """`[(start, end)]` of the glue `names` in `elf` — each its SIZED symbol (`shipped_glue` emits `.size`, and so does
    each Alcyon entry), so the range is the glue's own instructions and not the `.S` or the C it enters. Glue the ELF
    does not size is refused: counting nothing for it would pass its cycles off as the caller's body."""
    sized = {symbol.name: (symbol.start, symbol.start + symbol.size) for symbol in transcription.symbol_table(elf)
             if symbol.size is not None and symbol.name in names}
    if set(sized) != names:
        raise LookupError(f"{elf} sizes no glue for {sorted(names - set(sized))} — rebuild it (`make bench`): its glue "
                          f"predates `bench/shipped_glue.py`'s `.size` lines")
    return sorted(sized.values())


def glue_ranges():
    """Every generated thunk and Alcyon entry in the shipped blob."""
    return sized_glue(transcription.SHIPPED_ELF, frozenset(shipped_glue.thunked_cores()) | frozenset(ALCYON_ENTRIES))


def alcyon_entry_ranges(elf):
    """...and the Alcyon entries alone, in `elf` — the only glue a blob without the thunks links."""
    return sized_glue(elf, frozenset(ALCYON_ENTRIES))


def _cycles_in(ranges):
    """What the profiled run spent at the PCs of `[(lo, hi)]` — blob or ROM, both sides' tallies together."""
    return sum(emu.prof_cycles(lo, hi) for lo, hi in ranges)


def cycles_inside_glue():
    """The cycles the profiled run spent executing thunk instructions: the glue's own profile slots alone."""
    return _cycles_in(glue_ranges())


def _measure_call(bench, row, watch=None, original_watch=None):
    """A C row's `Measurement` on `bench` — the one spelling of the call, whichever blob prices it. `watch` is (EV)'s
    door windows (`DoorWindows`), for a row whose C reaches the event layer; `original_watch` the ROM's side's, for a row
    taken through interrupts (`aes_event.delivering`)."""
    measured = bench.measure(row.entry, row.symbol, args=row.args, regs=row.regs, pokes=row.pokes, psg_seed=row.psg_seed,
                             io_seed=row.io_seed, returns=row.returns, staged_entry=row.staged_entry,
                             schedule=row.schedule, dropped=row.dropped, watch=watch, original_watch=original_watch)
    vet_what_our_run_stored(row)
    return measured


# A DROP OF BYTES THAT DIFFER BY NATURE IS SYMMETRIC ON TARGET. The kit holds a drop to the ORIGINAL's ledger alone
# (`vet_dropped`: every dropped byte one the ROM's run stored) — which proves nothing about OUR side. A drop excuses
# two values that differ because each run stored ITS OWN (its caller's status register, an address in its own frame,
# its own depth on a stack): never a byte one of the two did not store at all. So EVERY dropped byte of a row is
# held to OUR run's ledger too — read where our run has just ended, the bench's last (`emu.bench_writes`: the
# original went first, `RomBench._both_sides`) — whatever the drop's kind:
#   * an SR SAVE WORD (`aes_event.SR_DROPS`): a build whose mask bracket was lost (`aes/switch.h`'s `sr_mask_saving`
#     compiled away, a wait re-arming the tick with interrupts open) stores no word, and the drop would hide that;
#   * A QPB'S ADDRESS LEFT IN AN EVB (`aes_event.QPB_ADDRESS_WHY`): a wait queued with no QPB of its own;
#   * A PROCESS'S SAVED CONTEXT, THE DISPATCHER'S STACK (the switch's rows): a switch that saved nothing;
#   * a return address a door PARKS (GEMDOS's RETSAV), and any kind a later row names — held without a word here.
# ONE KIND IS ONE-SIDED BY NATURE, and named (ONE_SIDED_BY_NATURE): the Line-F handler's own `movem` mask word, which
# every masked Alcyon return of the ROM's rewrites and our C — no Line-F return of its own — never stores. A row
# stages it at the value the ROM's run leaves, and its companion compares it with nothing dropped. A NEW one-sided
# drop is therefore refused by name until it is declared here, with its reason.
# (A code address the two builds hold in data — a fork queue entry's code, a recorded one, a glue handed to the VDI —
# is no drop at all: RELOCATED and compared exactly, below.)
#
# WHERE THE RULE LIVES: here, at the ONE place a row's own run is made with its drops — `vet_what_our_run_stored`,
# called by the primitive every dropping path makes its run through (`_measure_call`: a plain row, a shipped one, a
# row through the OS, a sliced session's one pair of runs) — and `measure` holds, for every row with such a drop,
# that the vet RAN for it (`_VETTED`): a measuring path that made its run past it (a `.S` row's, a (T←) one's) is
# refused by name, not silently one-sided.
_VETTED = []                            # the rows whose own run the rule was asked about, since `measure` last looked
ONE_SIDED_BY_NATURE = frozenset((lo, hi) for lo, hi, _why in aes.LINE_F_MASK_WINDOW)


def drops_held_to_our_run(row):
    """The drops of `row` OUR run must have stored too, `(lo, hi, why)` each: every one but the one-sided kind."""
    return [(lo, hi, why) for lo, hi, why in row.dropped if (lo, hi) not in ONE_SIDED_BY_NATURE]


def sr_save_words_dropped(row):
    """The SR save words (`aes_event.SR_DROPS`) `row` drops: `(lo, hi)` each."""
    return [(lo, hi) for lo, hi, _why in row.dropped if lo in aes_event.SR_DROPS]


def vet_our_run_stored_its_drops(row, stored):
    """`stored` (our run's write ledger) holds every byte `row` drops as differing by nature — else refused by name."""
    for lo, hi, why in drops_held_to_our_run(row):
        missing = [at for at in range(lo, hi) if at not in stored]
        assert not missing, (
            f"{row.symbol} / {row.case}: the row drops [{lo:#x}, {hi:#x}) — {why} — which the ROM's run stores, and OUR "
            f"run never stored {[f'{at:#x}' for at in missing]}: "
            + ("its interrupt-mask bracket is missing from the build's path (`aes/switch.h`), which the drop would "
               "otherwise hide" if lo in aes_event.SR_DROPS else
               "a drop is of what BOTH runs store, each its own value — one-sided, it would hide a build that stores "
               "nothing there"))


def rom_routine_holding(address):
    """The `addrs` name of the AES routine whose body `address` lies in: the last entry at or below it."""
    entries = {getattr(addrs, name): name for name in dir(addrs)
               if name.startswith(aes_event.ENTRY_PREFIX) and aes.AES_TEXT[0] <= getattr(addrs, name) < aes.AES_TEXT[1]}
    return entries[max(entry for entry in entries if entry <= address)]


# WHICH FORK FUNCTION'S ENTRY OUR BUILD QUEUES IS HELD TWICE: by the relocation's exact compare (a code that is
# another function's maps back to another ROM address, and differs), and by the BUILD — each routine of ours names
# the entries of exactly the fork functions the ROM's routine names by its immediates (`fork_entries_named_by`,
# held on both blobs by `test_tier3.py`).
def fork_functions_named_by_the_rom():
    """`{an AES routine's `addrs` name: the fork functions (their ROM addresses) its instructions name by an
    immediate}` — every site of `aes.FORK_FUNCTION_IMMEDIATES`, by the routine it lies in."""
    named = {}
    for site, function in aes.FORK_FUNCTION_IMMEDIATES:
        named.setdefault(rom_routine_holding(site), set()).add(function)
    return named


def fork_entries_named_by(elf, symbol):
    """The fork functions (their ROM addresses, `aes_event.FORK_ENTRY_SYMBOLS`) whose ENTRY in `elf` the function
    `symbol` names — an address taken, pushed or compared, read off the listing of that function's own bytes."""
    placed = _placed(elf)
    spans = _function_ranges(elf).get(symbol, ())
    named = set()
    for line in transcription.listing(elf).splitlines():
        match = re.match(r"\s+([0-9a-f]+):\t", line)
        if match and any(lo <= int(match.group(1), 16) < hi for lo, hi in spans):
            # ...as the listing spells an address: an immediate in decimal (`cmpil #197840`), an operand by its symbol.
            named.update(function for function, entry in aes_event.FORK_ENTRY_SYMBOLS.items() if entry in placed
                         and (f"<{entry}>" in line or re.search(rf"#{placed[entry]}\b", line)))
    return named


def vet_what_our_run_stored(row):
    """THE RULE (above), asked where `row`'s own run has just ended: our ledger read once, only for a row that drops
    such bytes."""
    if not drops_held_to_our_run(row):
        return
    vet_our_run_stored_its_drops(row, emu.bench_writes(BASE_IMAGE)[0])
    _VETTED.append((row.symbol, row.case))


_PROFILING = []                         # not empty while `_profiled` has the cycle profile on


def _profiled(run):
    """`run()`'s answer, measured with the cycle profile cleared first and enabled only while it runs."""
    emu.prof_reset()
    emu.prof_enable(True)
    _PROFILING.append(run)
    try:
        return run()
    finally:
        _PROFILING.pop()
        emu.prof_enable(False)


def _measure_as_shipped(row, watch=None, original_watch=None):
    """A (T→) row on the shipped blob, PROFILED: the `Measurement` carries `glue_cycles` beside its costs."""
    measured = _profiled(lambda: _measure_call(shipped_bench(), row, watch, original_watch))
    measured.glue_cycles = cycles_inside_glue()
    return measured


def glue_cycles_of(measured):
    """What `measured` spent inside glue: a (T→) row's and a (V) row's measurements carry it, every other enters none."""
    return getattr(measured, "glue_cycles", 0)


def ratio_net_of_glue(measured):
    """(T→G): the ratio with the thunks' cycles taken off OUR side alone — the ROM has no thunk to take off."""
    return (measured.recreate_net - glue_cycles_of(measured)) / measured.original_net


# MECHANISM (T←): a `.S` that calls C through thunks of its own, and what its rows are split by.
# `thunk_prefix` names its `.S`→C thunks (sized local symbols); `spans` are the ROM's `[lo, hi)` its own instructions
# transcribe; `carried_by` are the PERF_ACCEPTED keys that already accept the cost of the C those thunks reach.
CallsIntoC = namedtuple("CallsIntoC", "thunk_prefix spans carried_by")
# The console's C as Bconout(CON:) prices it: the cursor lock, placement and unlock (the line feed's), a glyph with and
# without the cursor, the clear, and the state machine's ESC — every console body escape.S's thunks enter.
CONSOLE_C_ACCEPTED_BY = (
    ("bios_bconout", "console escape state"),
    ("bios_bconout", "console line feed"),
    ("bios_bconout", "console glyph"),
    ("bios_bconout", "console glyph with the cursor"),
    ("bios_bconout", "console clear to end of screen"),
)
CALLS_INTO_C = {
    addrs.VDI_ROM_ESCAPE: CallsIntoC(escape_transcription.THUNK_PREFIX,
                                     tuple((region.lo, region.hi) for region in escape_transcription.REGIONS),
                                     CONSOLE_C_ACCEPTED_BY),
}


def calls_into_c(row):
    """Is `row` a `.S` row of a routine that reaches C through its own thunks (T←)?"""
    return row.transcription and rom_address(row) in CALLS_INTO_C


@functools.cache
def _function_ranges(elf):
    """`{node: [(start, end)]}` — every function in `elf`, under the call graph's own node names (`transcription.nodes_of_labels`:
    a static's name qualified where another definition shares it). A function the symbol table sizes ends there; one
    it does not (libgcc's `__mulsi3`) runs on to the next function's start, as the call graph reads it."""
    functions = sorted({(symbol.start, symbol.name): symbol for symbol in transcription.symbol_table(elf)
                        if symbol.kind in "Tt"}.values())
    nodes = transcription.nodes_of_labels([(symbol.start, symbol.name) for symbol in functions], transcription.symbol_origins(elf))
    starts = sorted({symbol.start for symbol in functions})
    ranges = {}
    for symbol in functions:
        end = symbol.start + symbol.size if symbol.size is not None else next(
            (start for start in starts if start > symbol.start), None)
        if end is not None:
            ranges.setdefault(nodes[(symbol.start, symbol.name)], []).append((symbol.start, end))
    return ranges


@functools.cache
def into_c_ranges(elf, thunk_prefix):
    """`(thunks, callees)`: the `[(start, end)]` of the `.S`→C thunks named `thunk_prefix*` in `elf` — SIZED symbols,
    as `glue_ranges` requires of the generated ones, so a thunk's range is its own bytes and not the `.S` round it —
    and of every C function they reach, the call graph's closure of their callees."""
    graph = transcription.call_graph(elf)
    ranges = _function_ranges(elf)
    sized = {symbol.name for symbol in transcription.symbol_table(elf) if symbol.size is not None}
    thunks = {node for node in graph if node.startswith(thunk_prefix)}
    callees, frontier = set(), set().union(*(graph[thunk] for thunk in thunks))
    while frontier:
        callees |= frontier
        frontier = set().union(*(graph.get(node, set()) for node in frontier)) - callees - thunks
    unplaced = sorted((thunks - sized) | (callees - set(ranges)))
    if not thunks or unplaced:
        raise LookupError(f"{elf} places no range for {unplaced or thunk_prefix + '*'} — a `.S`→C thunk needs `.size`, "
                          f"and every function it reaches a start")
    return (tuple(span for thunk in sorted(thunks) for span in ranges[thunk]),
            tuple(span for callee in sorted(callees) for span in ranges[callee]))


def _measure_into_c(row, bench):
    """A (T←) `.S` row, PROFILED: the `Measurement` carries `own_cycles` (ours, the ROM's) and `into_c_cycles` (the
    thunks', the C's) beside its costs. OURS is everything the blob ran less the thunks and the C — so a spill in the
    `.S`, or a call to any other C, stays in it — and the ROM's is the cycles inside the spans the `.S` transcribes.
    Code both sides run from the same bytes (a ROM routine the `.S` jumps to, a staged RAM stub) is in neither."""
    split = CALLS_INTO_C[rom_address(row)]
    thunks, callees = into_c_ranges(bench.elf, split.thunk_prefix)
    measured = _profiled(lambda: _measure_transcription(row, bench))
    thunk_cycles, c_cycles = _cycles_in(thunks), _cycles_in(callees)
    measured.into_c_cycles = (thunk_cycles, c_cycles)
    measured.own_cycles = (emu.prof_cycles(bench.base, bench.end) - thunk_cycles - c_cycles, _cycles_in(split.spans))
    return measured


def own_ratio(measured):
    """(T←) and (V): our own cycles against the ROM's — the only part of such a row our build is answerable for."""
    ours, original = measured.own_cycles
    assert original > 0, "the ROM spent nothing in the spans this row is answerable for — the row enters no arm of it"
    return ours / original


def own_ratio_with_glue(measured):
    """(V): the own ratio with the thunks' cycles counted back on our side — what decides `net` against `glue`."""
    ours, original = measured.own_cycles
    return (ours + glue_cycles_of(measured)) / original


def cited_acceptances_stand(row):
    """Is every acceptance a (T←) routine cites for its C still written, and still an acceptance (over the bar)?"""
    return all(key in PERF_ACCEPTED and PERF_ACCEPTED[key][0] > TIER3_FUNCTION_BAR
               for key in CALLS_INTO_C[rom_address(row)].carried_by)


def own_within_bar(row, measured):
    """(T←) holds EVERY row of a `.S` that calls C to its own instructions — under the bar as a whole too, where the
    code it shares with the ROM (a routine it jumps to) would otherwise dilute a spill of its own into the average."""
    return not calls_into_c(row) or own_ratio(measured) <= TIER3_FUNCTION_BAR


# MECHANISM (V): C that reaches the VDI through `trap #2`, priced on the AES's own cycles (the legend above).
# The ROM's side: the AES's text and the Line-F handler's RAM copy, less GEM's selector switch (the trap arm a VDI
# call runs, `move.l SYSVAR_VDI_ENTRY,-(sp); rts`), which our build's trap runs from the same bytes.
LINE_F_HANDLER_COPY = (aes.AES_LINEF_COPY, aes.AES_LINEF_COPY + aes.LINEF_COPY_BYTES)
GEM_SELECTOR_SWITCH = (addrs.GEM_TRAP2, addrs.GEM_TRAP2_PTERM_ARM)
AES_OWN_SPANS = ((aes.AES_TEXT[0], GEM_SELECTOR_SWITCH[0]), (GEM_SELECTOR_SWITCH[1], aes.AES_TEXT[1]), LINE_F_HANDLER_COPY)
# `trap #2` as the m68k listing spells it: its opcode word, and the mnemonic.
_LISTED_TRAP_2 = re.compile(rf"^\s+([0-9a-f]+):\s+{opcodes.TRAP_GEM.hex()}\s+trap #2\s*$", re.M)


@functools.cache
def trap_2_functions(elf):
    """The call-graph nodes of `elf` whose OWN instructions include a `trap #2` — the bridge, inlined wherever a
    caller compiled it (`aes/gsx.h`'s `gsx_trap`)."""
    traps = [int(at, 16) for at in _LISTED_TRAP_2.findall(transcription.listing(elf))]
    return frozenset(node for node, spans in _function_ranges(elf).items()
                     if any(lo <= at < hi for lo, hi in spans for at in traps))


@functools.cache
def _reaching_the_trap():
    """Every function of the m68k build from which a `trap #2` is reachable: the bridge's holders and their callers,
    closed over the call graph."""
    graph = transcription.call_graph(BUILT_ELF)
    vet_no_row_is_ambiguous(graph)
    return frozenset(transcription.callers_closure(graph, trap_2_functions(BUILT_ELF)))


def goes_through_the_os(row):
    """(V) and (EV): is `row` the C of a routine that reaches the VDI by `trap #2`, or the event layer through one of
    the event door's entries — priced on its own cycles?"""
    return not row.transcription and (row.symbol in _reaching_the_trap() or arrives_at_an_entry(row))


# MECHANISM (EV): C that reaches the EVENT LAYER through the event door (`aes/evdoor.h`): on target each door call is
# the ROM's own — the frame pushed, a `jsr` to ev_multi or ap_rdwr at its ROM address — which our C runs from the same
# bytes the ROM's caller reaches by its Line-F word. Those routines are AES TEXT, so (V)'s accounting would book their
# cycles as the ROM's own on one side and refuse them on ours. So our run is WATCHED (`RomBench.measure`'s `watch`):
# stopped at every door entry the blob `jsr`s (each exact PC) and at the return address the `jsr` left, the
# AES-span cycles between each pair a WINDOW — and so is the ROM's own run (`_original_windows`), stopped at the same
# entries and at the address its Line-F word returns to. The windows are the event layer's cost, run on both sides from
# the same bytes over the same machine, and held EQUAL one by one, as (V)'s shared cycles are: a door call that took the
# event layer down a cheaper path than the ROM's would otherwise be credited to the ROM's own. The ROM's own is its
# AES-span cycles less its windows; ours keeps (V)'s, every blob cycle less the glue — the frame's pushes included, as
# the ROM's own includes its Line-F word's handler — and an AES-span cycle of ours OUTSIDE a window is refused by name:
# our C reaches the AES's ROM bytes only through the door. (V)'s shared-cycle equality still holds the OS both ran.
# Derived, never typed: the door calls are the blob's own `jsr`s into the AES text, the rows the call graph's callers of
# the functions holding one, the windows read off the two runs.
_LISTED_JSR_ABSOLUTE = re.compile(r"^\s+([0-9a-f]+):\s+4eb9 ([0-9a-f]{4}) ([0-9a-f]{4})\s+jsr ", re.M)
JSR_ABSOLUTE_BYTES = 6                 # `jsr <abs.l>`: the opcode word and the address


@functools.cache
def door_calls(elf):
    """`{call site: door entry}`: every `jsr` of `elf` to an absolute address in the AES's text — the event door's calls,
    the only way the C reaches that text."""
    return {int(at, 16): int(high + low, 16) for at, high, low in _LISTED_JSR_ABSOLUTE.findall(transcription.listing(elf))
            if aes.AES_TEXT[0] <= int(high + low, 16) < aes.AES_TEXT[1]}


@functools.cache
def _reaching_the_door():
    """Every function of the m68k build from which a door call is reachable: the functions holding one (the wrappers
    are inline) and their callers, closed over the call graph."""
    graph = transcription.call_graph(BUILT_ELF)
    vet_no_row_is_ambiguous(graph)
    sites = door_calls(BUILT_ELF)
    holders = frozenset(node for node, spans in _function_ranges(BUILT_ELF).items()
                        if any(lo <= at < hi for lo, hi in spans for at in sites))
    return frozenset(transcription.callers_closure(graph, holders))


def goes_through_the_door(row):
    """(EV): is `row` the C of a routine that reaches the event layer through the event door?"""
    return not row.transcription and row.symbol in _reaching_the_door()


# THE ARRIVALS RULE: A CALL OF AN ENTRY'S C TWIN is still an ARRIVAL of both runs — the same ordinal among a row's door
# calls, so a delivery or a slice's mark hangs on it as on any door call, and what the call is handed is held equal —
# but it OPENS NO WINDOW: nothing is taken off either side. The ROM's routine is then the ROM's OWN cost (its Line-F
# word and handler with it) and the twin ours, as any C's. Derived, off the blob:
#   * the TWINS are the door's entries whose core the blob links (`twin_entries`), our arrivals at them the twins' first
#     instructions (`EVDOOR_TWIN`, `include/transcribed.h`, is what keeps a first instruction to arrive at);
#   * an entry is REBOUND when no `jsr` into its ROM routine is left (`rebound_entries`: its wrapper is spelt through
#     `EVDOOR_REBOUND`, `aes/evdoor.h`) — the set the host's hook answers ARRIVED for, held equal by `test_tier3.py`;
#   * a twin whose entry still has its `jsr` is PENDING: the event layer's own C reaches it by its core (an arrival, no
#     window), the C outside the layer still reaches the ROM's routine through the door (a window). WHICH A ROW'S
#     CALLS ARE is the row's: `arrived_at_by_a_twin` reads it off the call graph for the ROM's watch, and a row whose
#     routine reaches one entry BOTH ways is refused by name — its ROM run's arrivals there could not be told apart.
# A row's entries may be mixed, some the ROM's and some C: windows are per call. What a twin may NOT do is run the
# AES's ROM bytes itself (a callee of its own left on the door): refused by name, its callee to be rebound first.
@functools.cache
def twin_entries(elf):
    """`{the twin's first instruction in elf: the ROM entry it stands for}` — the door's entries `elf` links a C twin
    of, rebound or pending (`aes_event.twins_in`'s derivation, off the blob)."""
    placed = _placed(elf)
    return {placed[routines.core_symbol(name)]: getattr(addrs, name) for name in aes_event.ENTRY_NAMES
            if routines.core_symbol(name) in placed}


def rebound_entries(elf):
    """The door's REBOUND entries as `elf` links them: a twin linked, and no `jsr` into the ROM's routine left
    (`aes_event.rebound_in`'s set, off the blob)."""
    return frozenset(twin_entries(elf).values()) - frozenset(door_calls(elf).values())


_A_LISTED_INSTRUCTION = re.compile(r"^\s+[0-9a-f]+:\t[^\t]*\t(\w+)[ \t]+(.*)$", re.M)
CALLS_LISTED_AS = frozenset({"jsr", "bsr", "bsrs", "bsrw", "bsrl", "jbsr"})


def references_to_twins(elf):
    """`[(mnemonic, the twin's symbol)]`: every instruction of `elf` that names a twin's FIRST INSTRUCTION — a call,
    a jump, a branch, an address taken. A twin is CALLED (`EVDOOR_A_CALL_NOT_A_JUMP`, `include/transcribed.h`): an
    arrival is closed at the return address its call left, so every one of these is a `jsr` (CALLS_LISTED_AS), held
    by `test_tier3.py` on both blobs."""
    placed = _placed(elf)
    named = {f"{placed[symbol]:x} <{symbol}>": symbol for symbol in
             (routines.core_symbol(name) for name in aes_event.ENTRY_NAMES) if symbol in placed}
    return [(mnemonic, symbol) for mnemonic, operands in _A_LISTED_INSTRUCTION.findall(transcription.listing(elf))
            for target, symbol in named.items() if target in operands]


# A TWIN CALLED THROUGH A REGISTER is a call all the same: where a function calls one twin more than once (a drag
# loop's ev_multi, fm_do's), GCC loads its address once — `lea <twin>,%aN` — and calls `jsr %aN@`. The arrival then
# holds a return address in our text like any `jsr`'s; what must not follow such a `lea` is a JUMP through the
# register (a tail call: the twin would hold its caller's caller's return address).
ADDRESS_TAKEN_AS = "lea"
_A_LISTED_LINE = re.compile(r"^\s+([0-9a-f]+):\t[^\t]*\t(\w+)[ \t]+(.*)$", re.M)


def twins_called_through_a_register(elf):
    """`[(the twin's symbol, the register its address is loaded into, the mnemonics of every transfer through that
    register in the loading function)]` — one per `lea <twin>,%aN` of `elf`."""
    placed = _placed(elf)
    named = {f"{placed[symbol]:x} <{symbol}>": symbol for symbol in
             (routines.core_symbol(name) for name in aes_event.ENTRY_NAMES) if symbol in placed}
    lines = [(int(at, 16), mnemonic, operands) for at, mnemonic, operands in _A_LISTED_LINE.findall(transcription.listing(elf))]
    spans = [span for spans in _function_ranges(elf).values() for span in spans]
    loaded = []
    for at, mnemonic, operands in lines:
        for target, symbol in named.items():
            if mnemonic == ADDRESS_TAKEN_AS and target in operands:
                register = operands.rsplit(",", 1)[-1].strip()
                lo, hi = next(span for span in spans if span[0] <= at < span[1])
                through = sorted({each for where, each, its in lines if lo <= where < hi and its.strip() == f"{register}@"})
                loaded.append((symbol, register, through))
    return loaded


def twins_reached_otherwise_than_by_a_call(elf):
    """...and the ones that are NOT a call, each once — what must be empty: an instruction that names a twin and is
    neither a call nor the load of its address for calls through a register (above), and a load whose register is
    then jumped through, or never called through."""
    not_calls = {(mnemonic, symbol) for mnemonic, symbol in references_to_twins(elf)
                 if mnemonic not in CALLS_LISTED_AS and mnemonic != ADDRESS_TAKEN_AS}
    not_calls |= {(f"{ADDRESS_TAKEN_AS} {register}, then {' / '.join(through) or 'no transfer'}", symbol)
                  for symbol, register, through in twins_called_through_a_register(elf)
                  if not through or any(each not in CALLS_LISTED_AS for each in through)}
    return sorted(not_calls)


def _twin_symbols():
    """`{a twin's symbol in the m68k build: its entry}`."""
    return {routines.core_symbol(name): getattr(addrs, name) for name in aes_event.ENTRY_NAMES
            if getattr(addrs, name) in twin_entries(BUILT_ELF).values()}


@functools.cache
def _arriving_at_an_entry():
    """Every function of the m68k build from which an ARRIVAL at a door entry is reachable: a door call (above), or a
    call of an entry's twin — the twins' callers and theirs. A twin is among them only as the caller of ANOTHER twin
    (its own row enters it: that is no arrival, `DoorStops`' `entered_at`)."""
    graph = transcription.call_graph(BUILT_ELF)
    twins = frozenset(_twin_symbols())
    callers = frozenset(node for node, callees in graph.items() if callees & twins)
    return _reaching_the_door() | frozenset(transcription.callers_closure(graph, callers))


@functools.cache
def _door_calls_held_by():
    """`{function of the m68k build: the entries it holds a `jsr` into the ROM of}` (the wrappers are inline)."""
    sites = door_calls(BUILT_ELF)
    return {node: frozenset(entry for at, entry in sites.items() if any(lo <= at < hi for lo, hi in spans))
            for node, spans in _function_ranges(BUILT_ELF).items()}


@functools.cache
def arrived_at_by_a_twin(symbol):
    """The entries the routine `symbol` of the m68k build ARRIVES AT BY THEIR TWIN — the OUTERMOST calls of its run:
    the call graph walked from it, a twin reached not walked into (what it calls is inside its call). Refused by name:
    an entry the same walk also reaches by a `jsr` into the ROM."""
    graph, twins, held = transcription.call_graph(BUILT_ELF), _twin_symbols(), _door_calls_held_by()
    by_a_twin, by_a_jsr, seen, walk = set(), set(), {symbol}, [symbol]
    while walk:
        node = walk.pop()
        by_a_jsr |= held.get(node, frozenset())
        for callee in graph.get(node, ()):
            if callee in twins:
                by_a_twin.add(twins[callee])
            elif callee not in seen:
                seen.add(callee)
                walk.append(callee)
    assert not by_a_twin & by_a_jsr, (
        f"{symbol} reaches {[f'{at:#x}' for at in sorted(by_a_twin & by_a_jsr)]} BOTH by the twin and by a `jsr` into "
        f"the ROM's routine: its ROM run's arrivals there are one PC, a window for some and none for others — rebind "
        f"the entry (`EVDOOR_REBOUND`) or reach it one way")
    return frozenset(by_a_twin)


def arrives_at_an_entry(row):
    """Is `row` the C of a routine whose run arrives at a door entry — the ROM's routine through the door, or its twin?
    Its runs are then WATCHED at the entries (`DoorWindows`): what deliveries, slices' marks and frames hang on."""
    return not row.transcription and row.symbol in _arriving_at_an_entry()


class DoorWindows(aes_event.DoorStops):
    """(EV)'s watch over a PROFILED run (`aes_event.DoorStops`): a stop at a door entry opens a window — the AES-span
    cycles so far kept, and what the call hands the entry (`DoorStops.call_at`: its frame, above the return address,
    read through its pointers) — and the stop at the return address the call left closes it. Refused by name: an entry
    reached from no call's return address, and a call that reaches the dispatcher (it would switch processes: a row's
    run returns). `windows` is each window's AES-span cycles, in order; `handed` each call's frame. `delivered` (a row
    taken through interrupts: `Row.delivered`) is laid at the entry of its door calls before the window opens, at no
    cost — on our side the Line-F mask word with it, which the row drops (our C never writes the word).

    A REBOUND entry's call (above) is an arrival with a window of NOTHING: at a twin (`twins`: our run, its calls
    made from `twins_called_from`) — which must have run no cycle of the AES's ROM, refused by name — and at a ROM
    entry of `rebound` (the ROM's run), whose cycles stay the ROM's own. `to_a_rebound_entry` says which calls those
    were: the watch's own knowledge, never read back off a window that came out empty.

    ...AND WHAT A REBOUND ENTRY'S CALL COST ITS OWN SHORE IS KEPT (`own_inside`, a figure per call: 0 for a call the
    ROM serves, which is a window already): the cycles of the shore's OWN count spent between the arrival and the
    return — the ROM routine's AES-span cycles on the ROM's shore, the twin's blob cycles less its glue on ours
    (`counting`: the shore's own running total; the AES spans', by default). Taken off nobody's column: it is what
    the CALLER's own cycles are net of (`caller_own_cycles`, the second count a door row is held by).
    AND THE THUNKS' CYCLES THE SAME WAY (`glue_inside`, per call; `counting`'s second total): a thunk that ran
    between the arrival and the return is THE ENTRY's — the twin's road to a transcribed core — and every other
    thunk of the run is the CALLER's own, counted back onto its second count as a row's are onto its first
    (`caller_glue_cycles`). EVERY CALL OPENED IS CLOSED: a run that ends inside one has booked the open call's
    cycles to its caller (`vet_every_call_closed`)."""

    def __init__(self, entries, returns, delivered=None, *, twins=None, twins_called_from=None, rebound=(),
                 dispatchers=()):
        super().__init__(entries, returns, blocks=True, delivered=delivered, twins=twins,
                         twins_called_from=twins_called_from, dispatchers=dispatchers)
        self.windows, self.handed, self.to_a_rebound_entry, self.own_inside, self.glue_inside = [], [], [], [], []
        self._rebound = frozenset(rebound)
        self._opened_at = self._open = self._own_at = self._glue_at = None
        self._own, self._glue = _aes_own_cycles_so_far, _no_glue

    def counting(self, own, glue=None):
        """This watch, its shore's OWN cycles read by `own()` — the running total a rebound entry's call is priced
        out of (above) — and its thunks' by `glue()` (none, on the ROM's shore)."""
        self._own, self._glue = own, glue or _no_glue
        return self

    def _opened(self, pc, sp, memory):
        self.handed.append(self.call_at(pc, sp, memory))
        self._opened_at, self._open, self._own_at, self._glue_at = _cycles_in(AES_OWN_SPANS), pc, self._own(), self._glue()

    def _closed(self):
        in_the_rom = _cycles_in(AES_OWN_SPANS) - self._opened_at
        assert not (self._open in self.twins and in_the_rom), (
            f"door call {self.calls - 1}: our twin of {self.entry_at(self._open):#x} ran {in_the_rom} cycles of the "
            f"AES's own ROM — a twin reaches no ROM routine: rebind the entry it called first")
        rebound = self._open in self._rebound or self._open in self.twins
        self.to_a_rebound_entry.append(rebound)
        self.windows.append(0 if rebound else in_the_rom)      # a twin's ran none of the ROM: held above
        self.own_inside.append(self._own() - self._own_at if rebound else 0)
        self.glue_inside.append(self._glue() - self._glue_at if rebound else 0)

    def vet_every_call_closed(self, who):
        """EVERY DOOR CALL THIS WATCH OPENED WAS CLOSED — refused by name otherwise: the lists a row is priced from
        are appended at the CLOSE, the call counted at the OPEN, so a run that ends inside a call (a twin that left
        by the dispatcher and was not resumed, an unbalanced stack) would compare equal on both shores with the
        open call's cycles booked as its caller's own."""
        assert len(self.windows) == self.calls, (
            f"{who}: {self.calls} door call(s) were opened and {len(self.windows)} closed — the run ended INSIDE "
            f"call {len(self.windows)} (of {self.entry_at(self._open):#x}): its cycles would be priced as its caller's")


def _no_glue():
    return 0


def _aes_own_cycles_so_far():
    """The ROM shore's own running total: the profiled run's cycles in the AES's text and Line-F handler."""
    return _cycles_in(AES_OWN_SPANS)


def _our_own_cycles_so_far(blob, glue):
    """...and OUR shore's, on `blob`: every cycle at its PCs less the ones inside `glue` (its thunks' ranges)."""
    return lambda: emu.prof_cycles(blob.base, blob.end) - _cycles_in(glue)


def _our_glue_cycles_so_far(glue):
    """...and what our shore has spent inside `glue` itself."""
    return lambda: _cycles_in(glue)


# ---- A CODE ADDRESS THE MACHINE HOLDS IN DATA IS RELOCATED FOR OUR SHORE -----------------------------------------------
# A fork queue entry's CODE is a fork function's ADDRESS: the ROM's in the ROM, and in a build linked elsewhere the
# function's own entry there (`aes/evfork.h`: `aes_<fn>_fork`) — the same function, named in each shore's own space.
# Our forker `jsr`s what the entry holds, so a queue THE ROM'S CODE FILLED — the machine a row starts from (forker's
# own rows: a queue the ROM's interrupts filled), an interrupt's delivery laid into the run (a press, a move: the
# ROM's glue queues bchange, mchange) — would send our build into the ROM's fork functions: the AES's ROM run inside
# ours. And a queue OUR C filled holds our entries where the ROM's memory holds its own.
# So every place such an address lies is mapped by a BIJECTION {the ROM's routine: its entry in the blob} wherever a
# byte crosses between the shores, and NOTHING IS DROPPED for it: the compare is EXACT — each shore's longword names
# the same routine, held byte for byte, and a code that is no routine's of the registry (another routine queued, a
# stray value) is mapped nowhere and differs.
# ...BUT FOR ONE VALUE THE MAP ALONE WOULD PASS: THE ROM'S OWN ADDRESS, STORED BY OUR BUILD. The back-map rewrites a
# slot only where it holds one of OUR entries; a slot our run stored the ROM's address in (a relocation the build
# left UN-APPLIED: the host arm of `fork_bchange()` compiled into the blob) is left as it is — and equals the ROM's
# memory. So it is REFUSED BY NAME (`vet_no_slot_names_the_rom`): where our image is mapped ROM -> ours at entry
# (the queue, the recording — and every delivery laid into the run is), NO SLOT HOLDS A ROM ADDRESS OF THE REGISTRY
# where our run ends unless our own code put it there; and where it is mapped at exit alone (the glue: below), no
# slot holds one THE MACHINE DID NOT COME WITH in one of those slots, nor the call in its arguments — a displaced,
# restored or handed-in value travels, a fresh one is our installer's. (What that leaves: an installer that stores the ROM's glue over a machine
# already holding it. Held by the installers' own test, off the vectors: `test_aes_irq.py`.)
# THE PLACES ARE THE REGISTRY'S (`aes_event.CODE_RELOCATIONS`: declared beside the slots; `code_relocations` reads
# it for one run), each mapped at the same three moments:
#   * THE FORK QUEUE'S CODE SLOTS — those thirty-two longwords: OUR image at our run's entry, ROM -> ours, and OUR
#     final image BACK before the kit compares it (`RomBench._call`); a DELIVERY laid into our run
#     (`deliveries_for_our_shore`): what it found and what it wrote; a slice's MARK, where the two memories are
#     compared mid-run (`_differing_at_a_mark`).
#   * APPL_TRECORD'S BUFFER — forker's recorder copies each entry it runs OUT of the queue, code and all ($fe4c8e), and
#     MERGES a tick into the record before the cursor by comparing that record's code with tchange's own address. So
#     the records of the recording so far (`recorded_code_slots`: back from the cursor, while each holds a fork
#     function's code) are mapped ROM -> ours at entry — our forker's compare then finds OUR tchange — and they, with
#     every record our run wrote (`_records_written`: from the cursor it found to the one it left), ours -> ROM
#     before the compare.
#   * THE GLUE THE AES HANDS THE VDI (`aes_event.GLUE_CODES`): on target gsx_setmb names OUR button and motion glue.
#     AT EXIT ONLY, ours -> ROM: the machine a row starts from holds the ROM's glue in the VDI's vectors, and a vex
#     call hands what it DISPLACED to wherever its caller's contrl lies (measured: vex_butv's row, the caller's own
#     contrl at $76026) — a displaced value travels, so our image at entry is the ROM-made machine as it is, and
#     what our run stored of our own entries is given the ROM's names before the compare.
# NOT THE QUEUE'S, FOR A ROUTINE WHOSE RUN REACHES THE ROM'S OWN FORKER: while ev_multi — the one door entry that runs
# the fork queue ($fe69ca) — is still the ROM's call, a door user's run has the ROM's forker run OVER OUR MEMORY inside
# that call, and it must find the ROM's addresses there (measured: relocated, the ROM's forker `jsr`s our bchange and
# the call's window costs 5,060 cycles where the ROM's run spends 8,580). Read off the build: the functions from which
# a `jsr` into the ROM's ev_multi is reachable — none, once that entry is rebound.
FORK_CODE_SLOTS = aes_event.FORK_CODE_SLOTS
THE_ENTRY_THAT_RUNS_THE_FORK_QUEUE = addrs.AES_ROM_EV_MULTI


@functools.cache
def _reaching_the_rom_s_forker():
    """Every function of the m68k build from which a `jsr` into the ROM's ev_multi — its forker with it — is
    reachable: the functions holding one and their callers, closed over the call graph."""
    holders = frozenset(node for node, entries in _door_calls_held_by().items()
                        if THE_ENTRY_THAT_RUNS_THE_FORK_QUEUE in entries)
    return frozenset(transcription.callers_closure(transcription.call_graph(BUILT_ELF), holders)) if holders else frozenset()


@functools.cache
def fork_relocation(elf, symbol):
    """`{a fork function's ROM address: its entry in elf}` (`aes_event.FORK_ENTRY_SYMBOLS`) for a run of `symbol` on
    that blob — empty for a routine that reaches the ROM's forker (above), and for a build that links none of them."""
    if symbol is None or symbol in _reaching_the_rom_s_forker():        # (None: a watch made for no routine's run)
        return {}
    placed = _placed(elf)
    return {function: placed[entry] for function, entry in aes_event.FORK_ENTRY_SYMBOLS.items() if entry in placed}


def glue_code_slots():
    """The longwords a glue's address lies in once gsx_setmb has handed it to the VDI (above)."""
    return aes_event.GLUE_CODES.slots


@functools.cache
def glue_relocation(elf):
    """`{a glue's ROM address: its entry in elf}` — empty for a build that links none."""
    placed = _placed(elf)
    return {rom: placed[entry] for rom, entry in aes_event.GLUE_CODES.symbols.items() if entry in placed}


A_RECORD = "a record of appl_trecord's buffer"
# One relocation of the registry AS ONE RUN READS IT: `what` it is, the longwords it lies in, `{the ROM's routine:
# its entry in the blob}`, and whether our image is mapped at the run's entry too.
Relocation = namedtuple("Relocation", "what slots mapping at_entry", defaults=(True,))


def code_relocations(elf, symbol):
    """THE REGISTRY (`aes_event.CODE_RELOCATIONS`) for a run of `symbol` on the blob `elf`: a `Relocation` each —
    the fork queue's (empty for a routine that reaches the ROM's own forker, `fork_relocation`) and the glue's. The
    one reading every site that maps a code address makes: a run's entry and exit, a delivery, a mark."""
    mapped = {aes_event.FORK_CODES.what: (FORK_CODE_SLOTS, fork_relocation(elf, symbol)),
              aes_event.GLUE_CODES.what: (glue_code_slots(), glue_relocation(elf))}
    declared = {each.what: each.at_entry for each in aes_event.CODE_RELOCATIONS}
    assert sorted(mapped) == sorted(declared), "a relocation the registry declares is mapped by no site"
    return tuple(Relocation(what, *mapped[what], at_entry) for what, at_entry in declared.items())


def _backwards(mapping):
    return {entry: rom for rom, entry in mapping.items()}


BUS_LONG_MASK = 0xFFFFFFFF


def _long_at(memory, at):
    return int.from_bytes(memory[at:at + aes.LONG_BYTES], "big")


def map_code_slots(memory, slots, mapping, base=0):
    """The longwords `slots` of `memory` — a run of bytes that begins at the address `base` — mapped IN PLACE by
    `mapping`: each slot that lies whole inside it and holds one of the mapping's keys."""
    for slot in slots:
        if base <= slot and slot + aes.LONG_BYTES <= base + len(memory):
            code = _long_at(memory, slot - base)
            if code in mapping:
                memory[slot - base:slot - base + aes.LONG_BYTES] = mapping[code].to_bytes(aes.LONG_BYTES, "big")
    return memory


def map_fork_codes(memory, mapping, base=0):
    """...the fork queue's code slots (`map_code_slots`)."""
    return map_code_slots(memory, FORK_CODE_SLOTS, mapping, base)


# The most records a recording is walked back over: appl_trecord's count is a word, and no session records more than
# a handful — a bound for a walk over memory that is not a recording's at all.
MOST_RECORDS_WALKED = 0x1000


def _recording_cursor(memory):
    """Where appl_trecord's next record goes over `memory` — None while nothing records."""
    if not case.word_in(memory, aes.AES_GL_RECD):
        return None
    return case.long_in(memory, aes.AES_RECORD_CURSOR) & aes.OS_BUS_ADDR_MASK


def recorded_code_slots(memory, codes):
    """The code longwords of THE RECORDING SO FAR over `memory`: of each record back from the cursor while it holds
    one of `codes` (a fork function's address) — the buffer's start is appl_trecord's own local, so the records are
    told by what they hold. None while nothing records."""
    cursor, slots = _recording_cursor(memory), []
    if cursor is None:
        return ()
    record = cursor - aes.FORK_ENTRY_BYTES
    while record >= 0 and len(slots) < MOST_RECORDS_WALKED and _long_at(memory, record + aes.FORK_CODE) in codes:
        slots.append(record + aes.FORK_CODE)
        record -= aes.FORK_ENTRY_BYTES
    return tuple(slots)


def _records_written(memory, cursor_found):
    """The code longwords of the records a run wrote: from the cursor it found (`cursor_found`: None for a run
    begun while nothing recorded) to the one it left in `memory` — which it leaves where it is when a recording ends."""
    if cursor_found is None:
        return ()
    cursor_left = case.long_in(memory, aes.AES_RECORD_CURSOR) & aes.OS_BUS_ADDR_MASK
    assert 0 <= cursor_left - cursor_found <= MOST_RECORDS_WALKED * aes.FORK_ENTRY_BYTES, (
        f"the recorder's cursor went from {cursor_found:#x} to {cursor_left:#x} in one run: no recording's")
    return tuple(record + aes.FORK_CODE for record in range(cursor_found, cursor_left, aes.FORK_ENTRY_BYTES))


def _pokes_for_our_shore(pokes, relocations):
    mapped = {}
    for at, data in pokes.items():
        data = bytearray(data)
        for relocation in relocations:
            map_code_slots(data, relocation.slots, relocation.mapping, at)
        mapped[at] = bytes(data)
    return mapped


def deliveries_for_our_shore(delivered, elf, symbol):
    """`delivered` (`aes_event.deliveries`' `{ordinal: (found, wrote)}`, the ROM's interrupts over the ROM's memory) as
    they are laid into a run of `symbol` on the blob `elf`: every code address of the registry they found and wrote,
    relocated (above)."""
    relocations = [relocation for relocation in code_relocations(elf, symbol) if relocation.mapping and relocation.at_entry]
    if not delivered or not relocations:
        return delivered
    return {ordinal: (_pokes_for_our_shore(found, relocations), _pokes_for_our_shore(wrote, relocations))
            for ordinal, (found, wrote) in delivered.items()}


def _a_code_relocated(at, ours, original, relocations):
    """Is the byte at `at`, where two memories differ, inside a slot of the registry that holds on our shore the
    image of what the ROM's holds?"""
    return any(slot <= at < slot + aes.LONG_BYTES and relocation.mapping.get(_long_at(original, slot)) == _long_at(ours, slot)
               for relocation in relocations for slot in relocation.slots)


def rom_addresses_in(memory, relocation):
    """The ROM addresses of `relocation`'s routines its slots hold over `memory`."""
    return frozenset(_long_at(memory, slot) for slot in relocation.slots) & frozenset(relocation.mapping)


def vet_no_slot_names_the_rom(symbol, memory, relocations, came_with=None):
    """THE RULE (above), asked where our run of `symbol` has just ended, BEFORE its image is mapped back: no slot
    of the registry holds the ROM's own address of a routine the build has an entry for — but an address the run
    CAME WITH (`came_with`: `{what: the ROM addresses that may travel}` — an argument the call was handed and, for a
    relocation not mapped at entry, what its slots held at the run's entry). Refused by name."""
    for relocation in relocations:
        travelling = (came_with or {}).get(relocation.what, frozenset())
        named = [(slot, _long_at(memory, slot)) for slot in relocation.slots
                 if _long_at(memory, slot) in relocation.mapping and _long_at(memory, slot) not in travelling]
        assert not named, (
            f"{symbol}: OUR run left THE ROM'S OWN address {named[0][1]:#x} in {relocation.what} (the longword at "
            f"{named[0][0]:#x}{f', and {len(named) - 1} more' if len(named) > 1 else ''}) — no slot of it held that "
            f"address when our run was entered, so OUR CODE stored the ROM's: a relocation left un-applied in the "
            f"build (the host's spelling of a code address compiled for the target). On iron our forker or the VDI's "
            f"interrupt would `jsr` that address")


class RomBench(rom_bench.RomBench):
    """The kit's bench, OUR run's memory relocated at the two moments it meets the ROM's (above): the fork queue's
    codes and the recording's ROM -> ours as our run is entered, and they and the glue's ours -> ROM in the image it
    leaves, before anything compares it."""

    _put_back = ()                      # the spans of the row being measured that our run's image is given back

    def measure(self, entry, symbol, *args, dropped=(), **kwargs):
        """...and THE DISPATCHER'S OWN STACK put back as our run found it, for a row that drops it by name
        (`spans_put_back`): a switch runs on that stack and leaves it dead — and a build whose frames there are not
        the ROM's stores bytes the ROM's run never did, which no drop may name (a drop is of what the ORIGINAL
        wrote). Put back, what differs there is exactly what the ROM's run stored: the row's named, vetted drop. How
        DEEP our build goes on it is held where it is measured (the dispatcher's own battery).
        ONLY WHAT OUR RUN PUSHED IS PUT BACK (`_pushed_from_the_top`): the frames it stored down from the stack's
        top. A store of ours anywhere else in the span — a word parked at a wrong address under its frames — stays
        in the image, and differs."""
        self._put_back = tuple((lo, hi) for lo, hi in spans_put_back()
                               if any(lo <= at and upto <= hi for at, upto, _why in dropped))
        try:
            return super().measure(entry, symbol, *args, dropped=dropped, **kwargs)
        finally:
            self._put_back = ()

    def _call(self, image, symbol, *args, **kwargs):
        relocations = [relocation for relocation in code_relocations(self.elf, symbol) if relocation.mapping]
        forks = fork_relocation(self.elf, symbol)
        cursor_found = _recording_cursor(image) if forks else None
        recorded = recorded_code_slots(image, forks) if forks else ()
        for relocation in relocations:
            if relocation.at_entry:
                map_code_slots(image, relocation.slots, relocation.mapping)
        map_code_slots(image, recorded, forks)
        # WHAT MAY TRAVEL: a ROM address the CALL was handed as an argument (forkq queues the code it is handed,
        # gsx_setmb installs the routines it is handed: the case's own values, on both shores) — and, for a relocation
        # mapped at exit alone, what its slots held at entry.
        handed = frozenset(int(word) & BUS_LONG_MASK for word in (args[0] if args else kwargs.get("args", ())))
        came_with = {relocation.what: (handed & frozenset(relocation.mapping))
                     | (frozenset() if relocation.at_entry else rom_addresses_in(image, relocation))
                     for relocation in relocations}
        found = {(lo, hi): bytes(image[lo:hi]) for lo, hi in self._put_back}
        # OUR RUN ALONE, PROFILED (`OUR_RUN`): inside a measurement that profiles both runs (a (V) row's) the tally
        # so far is the original's, taken off; for any other row the profile is this run's own.
        within = bool(_PROFILING)
        if not within:
            emu.prof_reset()
            emu.prof_enable(True)
        before, before_declared = (_cycles_in(AES_OWN_SPANS), _cycles_in(DECLARED_SPANS)) if within else (0, 0)
        try:
            ours = super()._call(image, symbol, *args, **kwargs)
        finally:
            OUR_RUN.append(OurRun(symbol, _cycles_in(AES_OWN_SPANS) - before, within,
                                  _cycles_in(DECLARED_SPANS) - before_declared))
            if not within:
                emu.prof_enable(False)
        if found:
            stored = stored_by_the_run_just_made(ours.image)
            for (lo, hi), as_found in found.items():
                pushed_from = _pushed_from_the_top(stored, lo, hi)
                ours.image[pushed_from:hi] = as_found[pushed_from - lo:]
        written = _records_written(ours.image, cursor_found)
        vet_no_slot_names_the_rom(symbol, ours.image, relocations, came_with)
        vet_no_slot_names_the_rom(symbol, ours.image, [Relocation(A_RECORD, recorded + written, forks)], {A_RECORD: handed})
        for relocation in relocations:
            map_code_slots(ours.image, relocation.slots, _backwards(relocation.mapping))
        map_code_slots(ours.image, recorded + written, _backwards(forks))
        return ours


# How many bytes of a frame may lie unstored between two stores of one run's frames: A LONGWORD — measured on the
# one row that asks (dsptch's yield: our frames store [$8b2a, $8c1a) but for a slot of four bytes and one of two that
# GCC allocated and never stored). A store further than that under the frames is no part of them.
MOST_UNSTORED_FRAME_BYTES = aes.LONG_BYTES


def stored_by_the_run_just_made(memory):
    """The addresses the bench run that has just ended stored at (its write ledger, read over `memory`)."""
    return emu.bench_writes(memory)[0].keys()


def _pushed_from_the_top(stored, lo, hi):
    """Where the frames a run PUSHED on the stack `[lo, hi)` begin: the lowest address of the unbroken run of bytes
    it stored (`stored`: its write ledger) down from the top — `hi` for a run that pushed nothing there. A frame's
    slot the build allocated and never stored breaks the run no further than `MOST_UNSTORED_FRAME_BYTES`."""
    at, unstored = hi, 0
    for address in range(hi - 1, lo - 1, -1):
        if address in stored:
            at, unstored = address, 0
        else:
            unstored += 1
            if unstored > MOST_UNSTORED_FRAME_BYTES:
                break
    return at


# WHAT OUR RUNS SPENT IN THE AES'S OWN ROM, since `measure` last looked: one `OurRun` per run of ours a measuring
# path made (`RomBench._call`) — `in_the_aes` its cycles at the PCs of AES_OWN_SPANS, `profiled_with_the_original`
# whether the measurement profiles both runs itself. What THE GENERAL GUARD reads (`vet_our_run_kept_out_of_the_aes`).
OurRun = namedtuple("OurRun", "symbol in_the_aes profiled_with_the_original in_declared_spans")
OUR_RUN = []


def spans_put_back():
    """The `(lo, hi)` spans a row may ask our image be given back over (`RomBench.measure`): the dispatcher's stack."""
    return frozenset({aes_event.DISPATCHER_STACK})


def text_span(elf):
    """`(lo, hi)`: the span of `elf` its functions lie in — where a call of our build's own returns to."""
    spans = [span for spans in _function_ranges(elf).values() for span in spans]
    return min(lo for lo, _hi in spans), max(hi for _lo, hi in spans)


def our_windows(elf, delivered=None):
    """(EV)'s watch over OUR run on the blob `elf`: its door calls' entries, and the address after each `jsr` — the
    entries' twins with them (`twin_entries`), each reached from the blob's own text — and `delivered` laid at its
    calls (`DoorWindows`): AS OUR SHORE TAKES THEM, which is the caller's to have made of a row's
    (`deliveries_for_our_shore`). The build's own dispatcher is a stop inside a call, beside the ROM's
    (`our_dispatchers`): a twin that blocks is refused there by name."""
    calls = door_calls(elf)
    return DoorWindows(calls.values(), (at + JSR_ABSOLUTE_BYTES for at in calls), delivered, twins=twin_entries(elf),
                       twins_called_from=text_span(elf), dispatchers=our_dispatchers(elf))


OUR_DSPTCH = "aes_dsptch"               # `aes/switch.h`: the entry a C twin that waits calls, `src/aes/switch.S`'s on target


def our_dispatchers(elf):
    """Where the blob `elf` places ITS OWN dsptch — what a twin that blocks reaches in place of the ROM's
    (`aes_event.DoorStops`' `dispatchers`): none, in a build that links no switch."""
    placed = _placed(elf)
    return frozenset({placed[OUR_DSPTCH]}) if OUR_DSPTCH in placed else frozenset()


@functools.cache
def _placed(elf):
    """`{symbol: its address in elf}`."""
    return {symbol.name: symbol.start for symbol in transcription.symbol_table(elf)}


def _original_windows(row, **marked):
    """(EV): the ROM's own run of `row`, WATCHED at the door's entries and the addresses their Line-F words return to
    (`aes_event.ROM_RETURNS`), its deliveries laid at its calls, and PROFILED (`watched_original`, over the case's
    image): its `DoorWindows`, the whole run's cycles, and its cycles in `AES_OWN_SPANS` — the ROM's own before its
    windows come off (`_original_own_cycles`' figure, read off this run: an interrupted row's original has no
    unwatched run). A sliced row's run is MARKED too (`_the_rom_s_marks`: the watch's `marks`; `marked` its options)."""
    assert not (row.regs or row.psg_seed or row.schedule), (
        f"{row.symbol} / {row.case}: a door row's ORIGINAL is re-run watched with the case's image and I/O map alone")
    # WHICH OF THE ROM's ARRIVALS OPEN NO WINDOW: at every entry the build has REBOUND — our run can only arrive at its
    # twin, by whatever road (a call through a POINTER too: the ROM's bchange, run off the fork queue, reaches
    # post_button by its Line-F word, and ours — queued by the same code — calls the twin: no call graph holds that
    # edge) — and at a PENDING entry this row's routine reaches by the twin (`arrived_at_by_a_twin`: read off the graph,
    # which is all that tells such a call from the door's `jsr` to the same routine).
    watch = DoorWindows(aes_event.ENTRIES, aes_event.ROM_RETURNS, row.delivered,
                        rebound=rebound_entries(BUILT_ELF) | arrived_at_by_a_twin(row.symbol)).entered_at(row.entry)
    if row.slice:
        watch.marked_with(_the_rom_s_marks(row, **marked))

    def run_and_mark():
        ran = watched_original(make_image(row.pokes), row.entry, watch, io_seed=row.io_seed)
        if row.slice:
            watch.marks.returned(watch.calls)
        return ran
    _final, _writes, run = _profiled(run_and_mark)
    vet_the_run_just_made(f"{row.symbol} / {row.case}: the ROM's watched run")
    return watch, run["cycles"], _cycles_in(AES_OWN_SPANS)


# (EV)'s SLICES: a row that is ONE SLICE of a long session (`aes_event.register_slices`: the file selector's listing, a
# key of a long typing session) — both sides run the whole session, as any row taken through interrupts, and the whole
# run is held to everything (EV) holds a row to; what is PRICED is the slice alone. Each run is MARKED at the slice's
# two ends (`aes_event.Marks`: arrivals both sides make at one PC — a door call, a trap taken, the entry, the return):
# what it had spent there, and its memory. Ours must reach each end as the ROM's does — after the same door calls, its
# memory the ROM's outside the stack band, the blob and the row's drops (`aes_event.vet_the_marks_agree`: a slice
# started a call late, or by a C that diverged before it, is refused by name) — and the row's costs, windows, own
# cycles and glue are then the differences between the two marks, the slice under `aes_event.SLICE_INSNS`.
def _the_rom_s_marks(row, **marked):
    """A sliced row's marks over the ROM's own run: its instructions and cycles, and its cycles in `AES_OWN_SPANS`.
    `marked`: `aes_event.Marks`' options — the session's other slices, every arrival."""
    return aes_event.Marks(row.slice, lambda: {**aes_event.run_cost(), "aes": _cycles_in(AES_OWN_SPANS)}, **marked)


def _our_marks(row, blob, glue, **marked):
    """...and over ours, on `blob`: its instructions and cycles, and its cycles at the blob's PCs and inside `glue`."""
    return aes_event.Marks(row.slice, lambda: {**aes_event.run_cost(), "blob": emu.prof_cycles(blob.base, blob.end),
                                                "glue": _cycles_in(glue)}, **marked)


def _differing_at_a_mark(row, blob):
    """How two memories at a slice's end are compared: everywhere the bench's second differential compares the final
    images — outside the oracle's stack band, the blob's span and the row's drops."""
    relocations = code_relocations(blob.elf, row.symbol)

    def excluded(address):
        return blob.base <= address < blob.end or any(lo <= address < hi for lo, hi, _why in row.dropped)

    def differing(ours, original):
        # ...and a code address OUR shore holds as the image of the ROM's is no difference (`code_relocations`).
        # (No session records: appl_trecord's buffer is relocated for a row's own run alone.)
        return [at for at in differing_addresses(memoryview(original), memoryview(ours), diff_spans(), excluded)
                if not _a_code_relocated(at, ours, original, relocations)]
    return differing


def _priced_on_its_slice(row, blob, original, windows, original_marks=None, our_marks=None):
    """The `Measurement` of a sliced row: the whole run's — measured, and held to (EV) — cut down to the slice. Its
    costs, windows, glue and own cycles are each side's between its two marks; ours agree with the ROM's at both
    (above); the slice is under the cap. The windows inside the slice are the event layer's on both sides (the whole
    run held them equal one by one, and our AES-span cycles to their sum). Net of the entry's reset only where the
    slice starts at the entry: the reset is spent there. `original` and `windows` are the two runs' watches; the
    marks are theirs — the row's own runs' — or the two given: its session's runs' marks, read for this row's slice
    (`Sessions`: one pair of runs for all a session's slices)."""
    who = f"{row.symbol} / {row.case}"
    original_marks, our_marks = original_marks or original.marks, our_marks or windows.marks
    aes_event.vet_the_marks_agree(who, our_marks, original_marks, _differing_at_a_mark(row, blob))
    ours, the_rom_s = our_marks.spent(f"{who}: our run"), original_marks.spent(f"{who}: the ROM's run")
    aes_event.vet_under_the_slice_cap(who, row.slice, the_rom_s["insns"])
    first, last = (mark.calls for mark in original_marks.ends(f"{who}: the ROM's run"))
    in_the_event_layer = sum(original.windows[first:last])
    overhead = blob.overhead if row.slice.start == aes_event.ENTRY else (0, 0)
    sliced = Measurement((the_rom_s["insns"], the_rom_s["cycles"]), (ours["insns"], ours["cycles"]), overhead)
    sliced.glue_cycles = ours["glue"]
    sliced.door_windows = tuple(windows.windows[first:last])
    sliced.rebound_calls = sum(windows.to_a_rebound_entry[first:last])
    sliced.rebound_own = (sum(windows.own_inside[first:last]), sum(original.own_inside[first:last]))
    sliced.rebound_glue = sum(windows.glue_inside[first:last])
    sliced.own_cycles = (ours["blob"] - ours["glue"] - overhead[1], the_rom_s["aes"] - in_the_event_layer - overhead[1])
    shared, original_shared = shared_cycles(sliced)
    assert shared == original_shared, (
        f"{who}: inside its slice the OS both sides run cost ours {shared} cycles and the ROM's {original_shared}")
    return sliced


def _original_own_cycles(row):
    """The ROM's own cycles over `row`'s case: the ORIGINAL run alone, profiled, inside `AES_OWN_SPANS`."""
    _profiled(lambda: emu.run(make_image(row.pokes), row.entry, dict(row.regs or {}), psg_seed=row.psg_seed,
                              io_seed=row.io_seed, schedule=row.schedule))
    return _cycles_in(AES_OWN_SPANS)


def _measure_through_the_os(row, bench):
    """A (V) row, PROFILED: the `Measurement` carries `own_cycles` (ours, the ROM's) beside its costs — and, measured
    as shipped, `glue_cycles` too. Ours is every cycle at the blob's PCs less the thunks'; the ROM's comes from its
    own run (`_original_own_cycles`), and the measurement's run of BOTH must spend exactly that much in the AES's
    spans: a cycle more is our build executing the AES's ROM bytes, which would be counted as the ROM's own. A SLICED
    row's is then cut to its slice (`_priced_on_its_slice`)."""
    measured, blob, original, windows = _held_through_the_os(row, bench)
    return _priced_on_its_slice(row, blob, original, windows) if row.slice else measured


def _held_through_the_os(row, bench, **marked):
    """...the WHOLE run's `Measurement`, held to everything (V) and (EV) hold a row to — with the blob it was measured
    on and the two runs' door watches (None for a row that reaches no door): `(measured, blob, original, windows)`. A
    sliced row's runs are marked (`marked`: `aes_event.Marks`' options)."""
    through_the_door = arrives_at_an_entry(row)
    assert through_the_door or not row.delivered, f"{row.symbol} / {row.case}: interrupts delivered at no door entry"
    assert row.delivered or not row.slice, f"{row.symbol} / {row.case}: a sliced row is taken through interrupts"
    original = None
    if through_the_door:
        original, original_watched, original_own = _original_windows(row, **marked)
    else:
        original_own = _original_own_cycles(row)
    shipped = ships_through_a_call(row)
    blob = shipped_bench() if shipped else bench
    # A twin's own row ENTERS the twin: no arrival at its first instruction (`DoorStops.entered_at`).
    glue = glue_ranges() if shipped else alcyon_entry_ranges(bench.elf)
    windows = (our_windows(blob.elf, deliveries_for_our_shore(row.delivered, blob.elf, row.symbol))
               .entered_at(_placed(blob.elf).get(row.symbol))
               .counting(_our_own_cycles_so_far(blob, glue), _our_glue_cycles_so_far(glue))
               if through_the_door else None)
    if row.slice:
        windows.marked_with(_our_marks(row, blob, glue, **marked))
    original_watch = aes_event.delivering(row.delivered, row.entry) if row.delivered else None
    if shipped:
        measured = _measure_as_shipped(row, windows, original_watch)
    else:
        measured = _profiled(lambda: _measure_call(bench, row, windows, original_watch))
        measured.glue_cycles = _cycles_in(alcyon_entry_ranges(bench.elf))
    if row.slice:
        windows.marks.returned(windows.calls)
    measured.door_windows = tuple(windows.windows) if windows else ()
    measured.rebound_calls = sum(windows.to_a_rebound_entry) if windows else 0
    measured.rebound_own = (sum(windows.own_inside), sum(original.own_inside)) if windows else (0, 0)
    measured.rebound_glue = sum(windows.glue_inside) if windows else 0
    if through_the_door:
        windows.vet_every_call_closed(f"{row.symbol} / {row.case}: our run")
        original.vet_every_call_closed(f"{row.symbol} / {row.case}: the ROM's run")
        assert original_watched == measured.original_cycles, (
            f"{row.symbol} / {row.case}: the ORIGINAL's watched run cost {original_watched} cycles and its run "
            f"{measured.original_cycles} — the windows were read off another run")
        assert original.handed == windows.handed, (
            f"{row.symbol} / {row.case}: our build handed the door {windows.handed} where the ROM's run hands "
            f"{original.handed} — a frame the image does not show")
        assert tuple(original.windows) == measured.door_windows, (
            f"{row.symbol} / {row.case}: the event layer cost the ROM's run {tuple(original.windows)} and ours "
            f"{measured.door_windows}, window by window — the door's calls took it down another path than the ROM's")
        assert original.to_a_rebound_entry == windows.to_a_rebound_entry, (
            f"{row.symbol} / {row.case}: the calls of a rebound entry are {windows.to_a_rebound_entry} on our run and "
            f"{original.to_a_rebound_entry} on the ROM's, call by call — the two watches disagree on which entries "
            f"the build has rebound, and the caller's own cycles would be net of other calls on each shore")
    in_the_event_layer = sum(original.windows) if through_the_door else 0
    ours_in_the_aes = _cycles_in(AES_OWN_SPANS) - original_own
    assert ours_in_the_aes == in_the_event_layer, (
        f"{row.symbol} / {row.case}: our build spent {ours_in_the_aes - in_the_event_layer} cycles inside the AES's own "
        f"ROM spans OUTSIDE the event door's windows — a (V) or (EV) row's C reaches the ROM only through the trap and "
        f"the door, never the AES's code itself")
    # Net of the reset both entries are charged (`Measurement`), which each tally places at its entry: own spans both.
    reset = measured.overhead_cycles
    measured.own_cycles = (emu.prof_cycles(blob.base, blob.end) - glue_cycles_of(measured) - reset,
                           original_own - in_the_event_layer - reset)
    shared, original_shared = shared_cycles(measured)
    assert shared == original_shared, (
        f"{row.symbol} / {row.case}: the OS both sides run cost ours {shared} cycles and the ROM's {original_shared} — "
        f"cost moved into code counted as shared (a jump into ROM code past the trap, other VDI arguments)")
    return measured, blob, original, windows


# ONE PAIR OF RUNS PRICES EVERY SLICE OF A SESSION. A session's rows are one machine and one set of deliveries
# (`aes_event.session_of`: one record), so measuring each row whole ran the same three sessions — the ROM's watched
# run, then the bench's original and ours — once per slice: 29 rows over 5 sessions, 87 whole sessions where 15 do.
# A `Sessions` measures a session ONCE, both runs marked at the ends of ALL its registered slices
# (`aes_event.Marks`' `others`), and cuts every row of it out of that pair (`_priced_on_its_slice`: each row still held
# to the ROM at its own two ends, under the cap, its shared cycles equal). What a row is refused for is kept and
# raised when that row is asked for. The runs' marks — a memory per end — are dropped once the rows are cut: nothing
# kept holds a watch (a refusal is kept WITHOUT its traceback, whose frames hold both), and a watch is no reference
# cycle (`aes_event.DoorStops`), so the marks go when `_session_s_rows_priced` returns.
# A memo is its holder's (`table`'s, a test module's fixture) and ONE BUILD's — the bench it is made with: a row
# measured WITHOUT one (`measure(row, bench)`) is always its own three runs, which is what a case that changes the run
# (a RED test's astray build) needs.
class Sessions:
    """`measure(row)` for the sliced rows of sessions over ONE build (`bench`), each session measured once (above):
    `aes_event.OncePerSession`, the value a session's rows priced."""

    def __init__(self, bench):
        self.bench = bench
        self._priced = aes_event.OncePerSession(lambda row: _session_s_rows_priced(row, bench))

    def measure(self, row):
        if not any(each is row for each in ROWS):
            return measure(row, self.bench)     # not the table's own row (a case's variant of one): its own runs
        priced = self._priced(row.registered, _machine_of(row), row)[row.symbol, row.case]
        if isinstance(priced, AssertionError):
            raise priced
        return priced


def _machine_of(row):
    """What `row`'s runs are over: all of it but its names and its slice — what a session's rows share."""
    return row._replace(case=None, slice=None, registered=None)


def session_of(row):
    """The session `row` is of (`aes_event.session_of`, by the name its case is registered under) — None for a row
    taken through no interrupts. A SLICED row that names no session is refused by name: priced by its own three
    runs it would cost the table's one lever without a word."""
    session = aes_event.session_of(row.registered)
    assert session is not None or not row.slice, (
        f"{row.symbol} / {row.case}: a sliced row registered as {row.registered!r}, which names no session "
        f"(`aes_event.INTERRUPTED_ROWS`)")
    return session


def registered(row):
    """...and that session's record for a row that has one: its routine, arguments, machine, deliveries and budget."""
    session = session_of(row)
    assert session is not None, f"{row.symbol} / {row.case}: no row taken through interrupts ({row.registered!r})"
    return session


def rows_of_the_session(session):
    """The sliced rows of ROWS that are `session`'s (`session_of`), in the table's order."""
    return [row for row in ROWS if row.slice and session_of(row) is session]


def _session_s_rows_priced(row, bench, **marked):
    """Every row of `row`'s session priced off ONE pair of runs: `{(symbol, case): its Measurement, or the
    AssertionError it is refused by}`. The premise is held by name: the session's rows are `row` but for their names
    and slice. A refusal of the WHOLE run is every row's, and raised here."""
    rows = rows_of_the_session(session_of(row))
    assert all(_machine_of(each) == _machine_of(row) for each in rows), (
        f"{row.symbol} / {row.case}: the rows of its session are not one machine — they cannot share a run")
    others = tuple(each.slice for each in rows if each.slice != row.slice)
    _VETTED.clear()
    _measured, blob, original, windows = _held_through_the_os(row, bench, others=others, **marked)
    assert not drops_held_to_our_run(row) or _VETTED, (
        f"{row.symbol} / {row.case}: its session drops a word OUR run must have stored too, and the session's runs "
        f"never asked our ledger — the drop would be one-sided for every slice of it")
    priced = {}
    for each in rows:
        try:
            priced[each.symbol, each.case] = _priced_on_its_slice(
                each, blob, original, windows, original.marks.cut_to(each.slice), windows.marks.cut_to(each.slice))
        except AssertionError as refused:
            priced[each.symbol, each.case] = refused.with_traceback(None)   # its frames hold the watches, and their marks
    return priced


# WHAT NO SLICE PRICES. A session's registered slices need not cover it: between them lie STRETCHES no row prices (a
# dialog's keys 2..36, the selector's first listing in a session that prices its clicks), and a dear stretch of C
# placed in one would leave the table without a word. So each session is also cut WHOLE — at every DOOR CALL its run
# makes and at its registered slices' own ends (`aes_event.Marks`' `every_door_call`, both shores, the two timelines
# held to the same arrivals after the same door calls) — and every stretch between consecutive cuts that no
# registered slice covers is priced as a slice is: each shore's OWN cycles between the two (`uncovered_stretches`).
# `test_tier3.py` holds each at or under its routine's worst registered row.
# CUT AT DOOR CALLS, NOT AT EVERY TRAP: a door call is the arrival both shores are held to by COUNT, and the stretches
# between two of them are shapes the size the table prices (a key, a click, a listing). Between two TRAPS the two
# builds do the same work a handful of instructions either side of the trap, and a stretch that fine has a ratio of
# its own that no row's average would bound (measured: Fsfirst to the first Fsnext, 158 ROM instructions, 420 own
# cycles against 468 — 0.90 inside a read priced at 0.84; 1,264 instructions between two of fm_do's VDI calls, 0.85
# inside a key priced at 0.77).
# `own_cycles`: (ours, the ROM's), as a row's; `rebound_own`: what the calls of rebound entries inside it cost each shore
Stretch = namedtuple("Stretch", "start stop insns own_cycles rebound_own", defaults=((0, 0),))


def _ratio_of(ours, original):
    """`ours / original` — 0 where neither shore spent a cycle, and past every bar where ours alone did."""
    return ours / original if original > 0 else float("inf") if ours > 0 else 0.0


def stretch_ratio(stretch):
    """A stretch's own ratio — 0 where neither shore spent a cycle of its own in it (all of it the OS both run), and
    past every bar where ours alone did."""
    return _ratio_of(*stretch.own_cycles)


def stretch_caller_ratio(stretch):
    """...and its CALLER's own ratio: each shore's own cycles net of the rebound entries' calls inside the stretch
    (`caller_own_ratio`, a row's second count)."""
    return _ratio_of(*(own - inside for own, inside in zip(stretch.own_cycles, stretch.rebound_own)))


def _arrivals_held_equal(who, ours, the_rom_s):
    """Both shores' timelines are the same arrivals, each after the same door calls — refused by name at the first
    that is not: a trap our build takes that the ROM's run does not (or the other way), or takes a door call late."""
    differ = aes_event.first_to_differ(*([(arrival.at, arrival.calls) for arrival in shore] for shore in (ours, the_rom_s)))
    assert differ is None, (
        f"{who}: our run's arrival {differ} is {ours[differ].at if differ < len(ours) else 'none'} where the ROM's is "
        f"{the_rom_s[differ].at if differ < len(the_rom_s) else 'none'} — the two runs do not make the same arrivals "
        f"(ours {len(ours)}, the ROM's {len(the_rom_s)})")


def uncovered_stretches(row, bench, covered=None):
    """The stretches of `row`'s session that none of the slices `covered` prices (every registered slice of the
    session, by default), each a `Stretch` priced on both shores' own cycles (above). ONE pair of runs, marked at
    every door call; the whole run held to (EV) as any row's."""
    slices = [each.slice for each in rows_of_the_session(session_of(row))]
    _measured, blob, original, windows = _held_through_the_os(
        row, bench, others=tuple(each for each in slices if each != row.slice), every_door_call=True)
    entry = aes_event.Arrival(aes_event.ENTRY, 0, None)
    the_rom_s, ours = ([entry] + watch.marks.timeline for watch in (original, windows))
    _arrivals_held_equal(f"{row.symbol} / {row.case}", ours, the_rom_s)
    index = {arrival.at: nth for nth, arrival in enumerate(the_rom_s)}
    priced = set()
    for start, stop in (slices if covered is None else covered):
        priced.update(range(index[start], index[stop]))
    return [_stretch(ours[nth:nth + 2], the_rom_s[nth:nth + 2], original.windows, blob.overhead[1] if nth == 0 else 0,
                     (windows.own_inside, original.own_inside))
            for nth in range(len(the_rom_s) - 1) if nth not in priced]


def _between(arrivals, total):
    """What a run spent of the running total `total` between two consecutive `arrivals` of its timeline (the entry's
    has spent nothing)."""
    first, last = ((arrival.spent or {}).get(total, 0) for arrival in arrivals)
    return last - first


def _stretch(ours, the_rom_s, windows, reset, rebound_own=((), ())):
    """The `Stretch` between two consecutive arrivals — each shore's pair, the ROM's door `windows`, and the entry's
    `reset` cycles where the stretch starts at the entry: each shore's OWN cycles as a row's are (ours the blob's less
    its glue, the ROM's its AES spans less the event layer's windows inside the stretch). `rebound_own`: each
    shore's `DoorWindows.own_inside` (ours, the ROM's) — what the rebound entries' calls inside the stretch cost."""
    first, last = the_rom_s
    in_the_event_layer = sum(windows[first.calls:last.calls])
    mine = _between(ours, "blob") - _between(ours, "glue") - reset
    its = _between(the_rom_s, "aes") - in_the_event_layer - reset
    inside = tuple(sum(shore[first.calls:last.calls]) for shore in rebound_own)
    return Stretch(first.at, last.at, _between(the_rom_s, "insns"), (mine, its), inside)


def shared_cycles(measured):
    """(V): `(ours, the ROM's)` cycles in the OS both sides run — each side's whole, less its own and our thunks'."""
    ours, original = measured.own_cycles
    return measured.recreate_net - ours - glue_cycles_of(measured), measured.original_net - original


# THE SECOND COUNT A DOOR ROW IS HELD BY: ITS CALLER'S OWN CYCLES, NET OF THE REBOUND ENTRIES. A rebound entry's call
# opens no window: the twin's cycles are OURS and the ROM routine's the ROM's, inside both own columns. That is what
# makes the row a differential of the whole call — and it lets the CALLER's body hide in the entry's cost: gr_stilldn
# is 340 cycles of its own round an ev_multi of 5,374, six per cent of its own denominator once ev_multi is C, and a
# body seven times dearer would pass a bar held on the whole. So every row whose run arrives at a rebound entry is
# held TWICE, both by derivation:
#   (whole) its own ratio — every cycle of ours against the ROM's own, the rebound entries' calls in both;
#   (own)   THE CALLER'S OWN — each shore's own cycles less what the rebound entries' calls cost it
#           (`DoorWindows.own_inside`: the twins' cycles on our shore, the ROM routines' on the original's; unequal,
#           and held equal by nobody — the entries' own rows price the twins).
# A row with no such call has one count: the two are the same number. The table prints the second under the row
# wherever a call of a rebound entry is in it.
def rebound_own_of(measured):
    """`(ours, the ROM's)`: what the calls of rebound entries cost each shore inside `measured` — nothing, for a
    measurement no door watch made."""
    return getattr(measured, "rebound_own", (0, 0))


def caller_own_cycles(measured):
    """`(ours, the ROM's)`: a (V)/(EV) row's own cycles NET of the rebound entries' calls (above)."""
    return tuple(own - inside for own, inside in zip(measured.own_cycles, rebound_own_of(measured)))


def caller_own_ratio(measured):
    """The second count (above): the caller's own cycles, ours against the ROM's."""
    return _ratio_of(*caller_own_cycles(measured))


def caller_glue_cycles(measured):
    """THE CALLER'S OWN THUNKS: the row's glue cycles less the ones that ran INSIDE a rebound entry's call
    (`DoorWindows.glue_inside`: the twin's road to a transcribed core, the entry's). Which side of a window a thunk
    ran on is MEASURED, call by call — never read off which function the listing puts the `jsr` in."""
    return glue_cycles_of(measured) - getattr(measured, "rebound_glue", 0)


def caller_own_ratio_with_glue(measured):
    """...and the second count WITH those thunks counted back, as `own_ratio_with_glue` is the first's: the number
    of it that ships, and the one a pin of it is written at."""
    ours, original = caller_own_cycles(measured)
    return _ratio_of(ours + caller_glue_cycles(measured), original)


def counts_within_bar(measured):
    """Is a (V)/(EV) row at or under the bar ON BOTH COUNTS — its own ratio, and its caller's own?"""
    return own_ratio(measured) <= TIER3_FUNCTION_BAR and caller_own_ratio(measured) <= TIER3_FUNCTION_BAR


def counts_within_bar_with_glue(measured):
    """...and on both WITH THEIR THUNKS: the row's own with all of them, the caller's own with the caller's."""
    return (own_ratio_with_glue(measured) <= TIER3_FUNCTION_BAR
            and caller_own_ratio_with_glue(measured) <= TIER3_FUNCTION_BAR)


def has_a_second_count(measured):
    """Did this row's run call a rebound entry — is it held on the caller's own count too?"""
    return bool(getattr(measured, "rebound_calls", 0))


def gated_ratio(row, measured):
    """The ratio the bar is held to, and the table prints: a (V) row's OWN ratio, every other row's whole one."""
    return own_ratio(measured) if goes_through_the_os(row) else measured.ratio


def pinned_ratio(row, measured):
    """The ratio a pin or an acceptance is written at: the number that SHIPS — a (V) row's own ratio with its thunks'
    cycles counted back, as a (T→) row's whole ratio already includes them; every other row's whole one."""
    return own_ratio_with_glue(measured) if goes_through_the_os(row) else measured.ratio


def carried_by_its_own_instructions(row, measured):
    """(T←): is `row` a `.S` row whose own instructions are at or under the bar, the rest being C already accepted?"""
    return calls_into_c(row) and own_within_bar(row, measured) and cited_acceptances_stand(row)


def _measure_transcription(row, bench):
    """A `.S` row's `Measurement` (`RomBench.measure_transcription`). IT DROPS NOTHING: both shores are entered with
    ONE register file, the status register in it, and compared whole — a `.S` bracket stores the very word the ROM's
    does. A transcription row that names a drop is refused by name (the kit's door for it takes none: the drop would
    be read by nobody, and what it meant to excuse compared all the same — or, one day, not)."""
    assert not row.dropped, (
        f"{row.symbol} / {row.case}: a transcription row drops {[(f'{lo:#x}', f'{hi:#x}') for lo, hi, _why in row.dropped]} "
        f"— a `.S` row is compared whole (one register file on both shores): nothing of it differs by nature")
    return bench.measure_transcription(row.entry, row.symbol, row.regs, pokes=row.pokes, psg_seed=row.psg_seed,
                                       io_seed=row.io_seed, staged_entry=row.staged_entry, shared_entry=row.shared_entry)


def measure(row, bench, sessions=None):
    """One row's `Measurement` — which is also its second differential, so this raises on a target
    build that does not equal the original. `sessions` (a `Sessions`, made over this `bench`): the holder's
    memo of sessions measured, through which a session's sliced rows share one pair of runs.

    The two relations are the kit's, not a choice made here: a C core owes its caller a return value
    and the callee-saved file, and an m68k transcription owes it the WHOLE register file the ROM's
    own instructions leave (`tools/recreate_kit/rom_bench.py`). A row that ships through a call (T→) is
    measured on the shipped blob, whatever `bench` was handed, and profiled for its glue (T→G); a (V) row
    is profiled for its glue on whichever blob prices it — an Alcyon entry is glue on both — and every
    other row's glue is 0 (`glue_cycles_of`), because it enters no thunk. A `.S` row that calls C through
    thunks of its own (T←) is profiled on `bench` and split into its own instructions and the rest.
    """
    if sessions is not None and row.slice:
        assert sessions.bench is bench, (
            f"{row.symbol} / {row.case}: asked of sessions measured over another build — a memo is one build's")
        return sessions.measure(row)    # ...whose one pair of runs is held to the rule where it is made
    _VETTED.clear()
    OUR_RUN.clear()
    measured = _measured_on_its_path(row, bench)
    vet_our_run_kept_out_of_the_aes(row, measured, bench)
    assert not drops_held_to_our_run(row) or _VETTED, (
        f"{row.symbol} / {row.case}: the row drops bytes OUR run must have stored too (an SR save word, a QPB's "
        f"address, a saved context) and was measured on a path that never asked our ledger — the drop would be one-sided")
    return measured


# THE GENERAL GUARD: NO RUN OF OURS EXECUTES THE AES'S OWN ROM BUT THROUGH A DECLARED WINDOW. (V) and (EV) hold their
# rows to it (`_held_through_the_os`: an AES-span cycle of ours outside the door's windows is refused) — but which
# rows ARE theirs is read off the build's static call graph, and a call through a POINTER IN DATA is in no graph: a
# plain C row whose routine `jsr`s what a queue entry, a saved vector or a walked routine's slot holds would run the
# ROM's own AES routine over our memory and be priced "equal" on the ROM's own instructions (measured: forker over a
# ROM-made queue with its relocation off — 61,120 cycles of ours in the AES's text, the row at 1.00). So EVERY row's
# own run is profiled (`RomBench._call`: OUR_RUN) and held, whatever its path — plain, shipped, through the OS, a
# `.S`, a (T←) one: our cycles at the PCs of AES_OWN_SPANS are exactly the row's DECLARED ones — the door windows a
# watch opened (`Measurement.door_windows`), and the ROM text a row is declared to enter by a pointer the MACHINE
# holds (ENTERED_BY_THE_MACHINE_S_POINTER) — and nothing for a row that declares none. Measured over the table as it
# stands: of 1,890 rows one spends a cycle of ours there undeclared — drawrat's `.S` row, below.
#
# THE ONE DECLARATION: drawrat ($fed412) calls the cursor routine AES_DRWADDR holds — in the snapshot the ROM's own
# bare `rts` (justretf, $fed424: no cursor routine saved). The `.S` transcription run over that ROM-made machine
# enters those two bytes, sixteen cycles, as the ROM's run does. Relocating the slot (the fork codes' arrangement)
# would move the row's register file instead — a transcription is held to the WHOLE file, and A0 is the routine's
# address — so the span is declared, and the guard holds our run to having spent in it exactly what the declaration
# says. On a machine OUR code made the slot would hold our own `aes_rom_justretf`: gem_main and appl_tplay install it,
# routines not reconstructed yet (`test_aes_irq.OWED_BY_ROUTINES_NOT_RECONSTRUCTED`).
# `slot`: the longword of the machine that holds the pointer; `span`: the ROM text it leads into, `[lo, hi)`;
# `cycles`: what a run spends there.
EnteredByAPointer = namedtuple("EnteredByAPointer", "slot span cycles why")
RTS_CYCLES = 16
ENTERED_BY_THE_MACHINE_S_POINTER = {
    ("aes_rom_drawrat", "no cursor routine saved: the bare `rts`"): EnteredByAPointer(
        aes.header_constants("gsxif.h")["AES_DRWADDR"], (addrs.AES_ROM_JUSTRETF, addrs.AES_ROM_JUSTRETF + aes.WORD_BYTES),
        RTS_CYCLES, "AES_DRWADDR in the snapshot holds the ROM's justretf: drawrat's `jsr (a0)` enters its `rts`"),
}
DECLARED_SPANS = tuple(sorted({declared.span for declared in ENTERED_BY_THE_MACHINE_S_POINTER.values()}))


def declared_by_a_pointer(row):
    """`row`'s declared entry by a pointer the machine holds, or None — A STALE DECLARATION REFUSED IN ITS OWN
    WORDS: the slot of the row's machine no longer holds the span's address (the snapshot moved, a case staged
    another routine), so whatever our run then spends in the AES's ROM is not what this declares."""
    declared = ENTERED_BY_THE_MACHINE_S_POINTER.get((row.symbol, row.case))
    if declared:
        held = _long_at(make_image(row.pokes), declared.slot) & aes.OS_BUS_ADDR_MASK
        assert held == declared.span[0], (
            f"{row.symbol} / {row.case}: THE DECLARATION IS STALE — it says the machine's pointer at {declared.slot:#x} "
            f"leads into the ROM at {declared.span[0]:#x} ({declared.why}), and the row's machine holds {held:#x} there")
    return declared


def declared_in_the_aes(row, measured):
    """The cycles `row`'s own run may spend at the PCs of the AES's ROM: its door windows', and its declared entry by
    a pointer the machine holds."""
    by_a_pointer = declared_by_a_pointer(row)
    return sum(getattr(measured, "door_windows", ())) + (by_a_pointer.cycles if by_a_pointer else 0)


def vet_our_run_kept_out_of_the_aes(row, measured, bench):
    """THE GENERAL GUARD (above), asked once `row`'s runs are made: refused by name where our run spent a cycle in
    the AES's own ROM that the row does not declare — or where no run of ours was profiled at all. `bench`: the one
    the measurement was asked of — THIS module's (`RomBench`: the table's, the gate's), whose `_call` is where our
    run is profiled; a case that hands `measure` the KIT's own bench (a row measured past the relocation, to show
    what the relocation is for) made its run where nothing reads the profile, and is not this guard's."""
    if row.slice:
        return      # cut out of a WHOLE run, which (EV) held to its door windows call by call (`_held_through_the_os`)
    if not OUR_RUN and not isinstance(bench, RomBench):
        return
    assert OUR_RUN, f"{row.symbol} / {row.case}: measured on a path that made no profiled run of ours — the guard read nothing"
    spent, declared = sum(run.in_the_aes for run in OUR_RUN), declared_in_the_aes(row, measured)
    by_a_pointer, in_declared_spans = declared_by_a_pointer(row), sum(run.in_declared_spans for run in OUR_RUN)
    # ...and the pointer's cycles are spent IN ITS SPAN: sixteen cycles elsewhere in the AES's text are no `rts`.
    assert in_declared_spans == (by_a_pointer.cycles if by_a_pointer else 0), (
        f"{row.symbol} / {row.case}: OUR run spent {in_declared_spans} cycles in the ROM text a declared pointer of the "
        f"machine leads into ({[(f'{lo:#x}', f'{hi:#x}') for lo, hi in DECLARED_SPANS]}) where the row declares "
        f"{by_a_pointer.cycles if by_a_pointer else 0}")
    assert spent == declared, (
        f"{row.symbol} / {row.case}: OUR run spent {spent} cycles at the PCs of the AES's own ROM where the row "
        f"declares {declared} (its door windows, a declared entry by a pointer the machine holds) — our build "
        f"executed the ROM's AES code: a code address in data nobody relocated (a queue entry, a saved vector), or "
        f"a jump past the door. The row would be priced on the ROM's own instructions")


def _measured_on_its_path(row, bench):
    if calls_into_c(row):
        return _measure_into_c(row, bench)
    if row.transcription:
        return _measure_transcription(row, bench)
    if goes_through_the_os(row):
        return _measure_through_the_os(row, bench)
    if ships_through_a_call(row):
        return _measure_as_shipped(row)
    return _measure_call(bench, row)


def pin_of(row):
    """The `(ratio, why)` this row is pinned at, or None."""
    return PERF_ACCEPTED.get((row.symbol, row.case))


# A PINNED ROW THAT CALLS A REBOUND ENTRY IS PINNED ON BOTH COUNTS: its `PERF_ACCEPTED` entry holds the first (what
# ships: `pinned_ratio`), and this table the second — the caller's own with its own thunks
# (`caller_own_ratio_with_glue`). A pinned door row with NO entry here has drifted by definition: an acceptance
# written on one count would leave the caller's own free to move under it.
CALLER_PINS = {}


def caller_pin_drifted(row, measured):
    """Is the second count of the pinned `row` no longer what it was pinned at (or pinned nowhere)?"""
    pinned = CALLER_PINS.get((row.symbol, row.case))
    return pinned is None or abs(caller_own_ratio_with_glue(measured) - pinned) > RATIO_TOLERANCE


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


def verdict(row, measured, dispatch, measurement_of):
    """What the gate makes of one measurement — THE SINGLE RULE, read by the table and the gate.

    "ok" — under the bar and not pinned. "pinned" — under the bar, measuring what it was pinned at.
    "accepted" — over the bar, and a written entry says so. "transcribed" — over the bar, the C of a
    routine the target build ships as its `.S`, every row of which is under it or carried by (T←) (mechanism
    (T); `measurement_of` hands over those rows' measurements — a written entry for a `.S` row never counts).
    "own" — a `.S` row over the bar whose OWN instructions are at or under it, the rest being the C it reaches
    through its own thunks, which the acceptances it cites carry (mechanism (T←)); a row of such a `.S` whose own
    instructions are over the bar is OVER whatever its whole ratio. "rule" — over the bar, and
    the LEAF RULE admits it on the measured excess. "through" — the C of a routine that reaches a transcribed
    core, measured as shipped (mechanism (T→)) and at or under the bar. "glue" — such a row over the bar as
    shipped and at or under it NET OF THE GLUE's own cycles (mechanism (T→G)); over it even net, the row is
    OVER unless an entry accepts its OWN body's cost, which it can only do at the shipped number. "net" — the C
    of a routine that reaches the VDI by `trap #2`, at or under the bar on its OWN cycles against the AES's
    (mechanism (V)), whatever its whole run, and still at or under it with its glue counted back; under the bar only
    net of that glue, the row is `glue` as (T→G) labels it, pinned or not; over the bar on its own cycles, OVER unless
    an entry accepts it or its routine's `.S` carries it (T). A row whose run arrives at a REBOUND entry is held on
    TWO counts — that own ratio, and its CALLER's own net of the rebound entries' calls (`caller_own_ratio`): over
    the bar on either, it is over the bar; under it on both only net of thunks — all of them on the first count, the
    caller's own on the second (`caller_glue_cycles`) — it is `glue`. "DRIFTED" — pinned, and no longer that number,
    which is `pinned_ratio`'s: what ships — or, for a pinned row that calls a rebound entry, its second count no
    longer the one `CALLER_PINS` holds. "OVER" — over the bar with nothing carrying it.
    """
    pin = pin_of(row)
    if pin and abs(pinned_ratio(row, measured) - pin[0]) > RATIO_TOLERANCE:
        return "DRIFTED"
    if pin and goes_through_the_os(row) and has_a_second_count(measured) and caller_pin_drifted(row, measured):
        return "DRIFTED"
    if goes_through_the_os(row):
        if counts_within_bar(measured):
            if not counts_within_bar_with_glue(measured):
                return "glue"
            return "pinned" if pin else "net"
        if pin:
            return "accepted"
        if is_transcribed_c_row(row):
            return "transcribed" if ships_within_bar(row, measurement_of) else "OVER"
        return "OVER"
    if not own_within_bar(row, measured):
        return "OVER"
    if measured.ratio <= TIER3_FUNCTION_BAR:
        return "pinned" if pin else "through" if ships_through_a_call(row) else "ok"
    if pin:
        return "accepted"
    if calls_into_c(row):
        return "own" if carried_by_its_own_instructions(row, measured) else "OVER"
    if ships_through_a_call(row):
        return "glue" if ratio_net_of_glue(measured) <= TIER3_FUNCTION_BAR else "OVER"
    if is_transcribed_c_row(row):
        return "transcribed" if ships_within_bar(row, measurement_of) else "OVER"
    return "rule" if rule_admits(row, measured, dispatch) else "OVER"


FAILED = ("OVER", "DRIFTED")

# How wide the ROM-address column renders: `$fc1510` and two spaces. Every entry in this ROM is six
# hex digits, so it is a constant rather than a measurement over the rows.
ADDRESS_WIDTH = 9
COST_HEADER = "insns/cycles"           # what each cost column's cell is


def _costs(measured):
    """A row's two costs, the original's then the recreate's, as `(insns, cycles)` each."""
    return ((measured.original_insns, measured.original_cycles), (measured.recreate_insns, measured.recreate_cycles))


def _cost(insns, cycles):
    return f"{insns}/{cycles}"


def _through_the_os_line(measured, indent):
    """The (V)/(EV) split under a row through the OS: the whole run's ratio, and what each side spent of its own."""
    ours, original = measured.own_cycles
    glue = glue_cycles_of(measured)
    shared, original_shared = shared_cycles(measured)
    # A door call the ROM serves on both sides is a window of its cycles; a rebound entry's opens none — told apart
    # by what the watch saw each call BE (`DoorWindows.to_a_rebound_entry`), not by a window that came out empty.
    windows, twins = getattr(measured, "door_windows", ()), getattr(measured, "rebound_calls", 0)
    served = len(windows) - twins
    return (f"{'':<{indent}}  whole run: {measured.ratio:.2f} — own {ours} cycles against the ROM's {original} in the "
            f"AES's text and Line-F handler; the OS both run {shared} against {original_shared}"
            + (f", the event layer's {sum(windows)} of it in {served} door window(s)" if served else "")
            + (f", {twins} call(s) of a rebound entry in the own cycles — the caller's own, net of them: "
               f"{caller_own_cycles(measured)[0]} against {caller_own_cycles(measured)[1]}, "
               f"{caller_own_ratio(measured):.2f}" if twins else "")
            + (f", and {glue} in thunks: {own_ratio_with_glue(measured):.2f} with them" if glue else ""))


# THE SECOND COUNT'S OWN LINE, in the form STATUS.md quotes and `test/test_status.py` pins: the row's own ratio, the
# caller's own, the two cycle counts behind it — and the caller's own thunks, with the ratio they make.
CALLER_LINE = ("{indent}  TWO COUNTS: {own:.2f} / {caller:.2f} ({ours} against {the_rom_s}) — own / the caller's own, "
               "net of {calls} call(s) of a rebound entry; {caller_glue} of the row's {glue} thunk cycles are the "
               "caller's own: {with_glue:.2f} with them")


def _two_counts_line(measured, indent):
    ours, the_rom_s = caller_own_cycles(measured)
    return CALLER_LINE.format(indent=" " * indent, own=own_ratio(measured), caller=caller_own_ratio(measured), ours=ours,
                              the_rom_s=the_rom_s, calls=measured.rebound_calls, caller_glue=caller_glue_cycles(measured),
                              glue=glue_cycles_of(measured), with_glue=caller_own_ratio_with_glue(measured))


def _own_split_line(measured, indent):
    """The (T←) split under a `.S` row over the bar: the own ratio, and where the rest of each side went."""
    (ours, original), (thunks, c_body) = measured.own_cycles, measured.into_c_cycles
    return (f"{'':<{indent}}  own instructions: {own_ratio(measured):.2f} ({ours} cycles against the ROM's {original}); "
            f"the rest {thunks} in thunks + {c_body} in the console's C against the ROM's other {measured.original_net - original}")


# ---- THE MEASURING PASS, OVER SEVERAL PROCESSES --------------------------------------------------------------------------
# A row's measurement is its own: two runs of the oracle over the row's machine, entered from the kit's reset — no
# row's number depends on which row was measured before it (the kit seeds every register a run begins with; the one
# thing rows share, a session's pair of runs, is shared inside a session). So the pass is cut into SHARES — each
# session's sliced rows one share, every other row a share of its own — and the shares measured by FORKS of this
# process taken after the registry is imported and the bench built (each inherits the rows, both blobs and the
# snapshot for nothing), each measurement sent back as it is made. THE TABLE IS JUDGED AND WRITTEN HERE, from the
# measurements in ROWS' own order, by the very code that judged a serial pass: the lines cannot differ unless a
# measurement does (`test_tier3.py` holds a share measured in a fork to the one measured in process; the whole table
# written by `--jobs 1` is the table written by any other count, line for line).
SERIAL = 1


def _shares(rows):
    """`rows`' indices, cut into what is measured together: a session's sliced rows (ONE pair of runs prices them
    all, `Sessions`) one share, every other row its own — the sessions first (they are the long ones: a pool that
    starts on them ends evenly)."""
    by_session, alone = {}, []
    for index, row in enumerate(rows):
        if row.slice:
            by_session.setdefault(id(session_of(row)), []).append(index)
        else:
            alone.append([index])
    return [*by_session.values(), *alone]


_POOL_S_BENCH = []                      # the bench the pool's forks measure over: set before they are made, inherited


def _measured_in_a_fork(share):
    """IN A FORK (or, for a serial pass, in this process — the same code): the measurements of one share of ROWS,
    `(index, Measurement)` each — or, for a row whose measurement raises (its second differential's refusal),
    `(index, the exception)` and the share's later rows left out, as a serial pass would never have reached them."""
    bench, sessions = _POOL_S_BENCH
    made = []
    for index in share:
        try:
            made.append((index, measure(ROWS[index], bench, sessions)))
        except Exception as refused:    # carried to the judge, which raises the FIRST of them in ROWS' order
            made.append((index, refused.with_traceback(None)))
            break
    return made


# How long the forks' pass may go with NO share coming back before it is ended by name (`fork_pool.Stuck`). The longest
# share is a sliced session's pair of runs: 3.2 s on a quiet machine, the longest single row 0.85 s (measured
# 2026-10-07, ten forks; the whole pass 10 s). A hundred times that: three agents' suites beside the bench have been
# measured at a load of 190 on ten cores.
LONGEST_SHARE_SECONDS = 3.2
MEASURING_STUCK_AFTER_SECONDS = 100 * LONGEST_SHARE_SECONDS


def measured_rows(bench, jobs=SERIAL, shares=None):
    """`[(row, its Measurement)]` over ROWS, in ROWS' order: by this process alone (`jobs` 1), or by `jobs` forks of
    it (above). A row whose measurement raises ends the pass with that exception either way — the first such row
    in ROWS' order — and so does a fork that DIES, or a pass that stops coming back (`fork_pool`: by name, where a
    `multiprocessing.Pool` waited for the lost share for ever). `shares`: the shares to measure, for a case that
    measures some of ROWS (every share, by default: the table's). EVERY ROW ASKED FOR COMES BACK, or the first row
    that raised: held here."""
    shares = _shares(ROWS) if shares is None else shares
    _POOL_S_BENCH[:] = [bench, Sessions(bench)]
    try:
        if jobs <= SERIAL:
            by_share = [_measured_in_a_fork(share) for share in sorted(shares)]
        else:
            by_share = fork_pool.over_forks(_measured_in_a_fork, shares, jobs, MEASURING_STUCK_AFTER_SECONDS,
                                            "tier3's measuring pass").values()
    finally:
        _POOL_S_BENCH.clear()
    made = dict(pair for share in by_share for pair in share)
    for index in sorted(made):
        if isinstance(made[index], Exception):
            raise made[index]
    asked = sorted(index for share in shares for index in share)
    assert sorted(made) == asked, (
        f"tier3's measuring pass was asked for {len(asked)} rows and {len(made)} came back: missing "
        f"{[ROWS[index].symbol for index in sorted(set(asked) - set(made))][:8]}")
    return [(ROWS[index], made[index]) for index in sorted(made)]


def table(bench, jobs=SERIAL):
    """Every row measured, as the lines `make bench` writes and STATUS.md quotes.

    MEASURED FIRST AND JUDGED AFTER, because one of the verdicts is about the others: the LEAF RULE
    is a fraction of what a trap dispatch costs, and that is two of these rows (`dispatch_cycles`).
    `jobs`: the processes the measuring pass is spread over (`measured_rows`) — the judging is this one's.
    """
    # One pass, keyed by the row, so `dispatch_cycles` below re-uses the pair rather than running
    # the oracle over them a third and fourth time.
    measured = measured_rows(bench, jobs)
    by_name = {(row.symbol, row.case): m for row, m in measured}
    dispatch = dispatch_cycles(by_name.__getitem__)

    def measurement_of(row):
        return by_name[(row.symbol, row.case)]
    overhead_insns, overhead_cycles = bench.overhead
    lines = [
        "Tier 3 — the recreate against the original, same case, same instrument (Musashi).",
        f"Costs are the oracle's own and include the {overhead_insns} instruction / "
        f"{overhead_cycles} cycles it charges before either entry executes anything; the RATIO is "
        f"net of that on both sides.",
        f"Bar: ratio <= {TIER3_FUNCTION_BAR:.2f} per function; a pinned row must stay within "
        f"{RATIO_TOLERANCE:.2f} of what it was pinned at.",
        "A TRANSCRIPTION's row is a whole call — an exception handler can only be entered through "
        "a caller — so its ratio is also net of the staged caller both sides run (trap.py's "
        "`caller_cost`: 7 / 106 with no arguments, +1 / +12 per argument word).",
        f"`rule`: over the bar, and admitted by the LEAF RULE — an (A)-only trap leaf whose excess "
        f"is <= {LEAF_SLACK_CYCLES} cycles and <= {LEAF_SLACK_FRACTION:.1%} of the "
        f"{dispatch} cycles this table measures a trap dispatch at, plus the leaf's own.",
        f"`transcribed`: over the bar, the C of a routine the target build ships as its `.S` "
        f"(include/transcribed.h), every `.S` row of which is <= {TIER3_FUNCTION_BAR:.2f} or `own`.",
        f"`own`: a `.S` row over the bar whose OWN instructions are <= {TIER3_FUNCTION_BAR:.2f} against the ROM's (T←): "
        f"the rest is the C it reaches through its own thunks, whose cost the Bconout(CON:) acceptances carry; "
        f"the split prints below the row.",
        f"`through`: <= {TIER3_FUNCTION_BAR:.2f} as SHIPPED — C that reaches a transcribed core, measured with "
        f"each such call entering the `.S` through generated glue (build/bench_shipped/).",
        f"`glue`: over the bar as shipped, and <= {TIER3_FUNCTION_BAR:.2f} NET of the cycles spent inside the "
        f"generated thunks themselves (T→G); every row over the bar as shipped prints that net ratio below it.",
        f"`net`: C that reaches the VDI by `trap #2`, its ratio its OWN cycles against the ROM's in the AES's text and "
        f"Line-F handler (V) — the OS both run from the same bytes in neither — <= {TIER3_FUNCTION_BAR:.2f}, and so "
        f"with its thunks' cycles counted back; the whole run's ratio prints below it. A (V) row <= "
        f"{TIER3_FUNCTION_BAR:.2f} only net of its thunks is `glue`, as (T→G), its ratio with them printed below. (EV): C "
        f"that reaches the event layer through the event door is priced the same way, the ROM routine its `jsr` "
        f"enters taken off both sides (the door's windows, counted below the row). A call of a REBOUND entry (its C "
        f"twin on our side) is taken off neither: it is in both own columns, and the row is held <= "
        f"{TIER3_FUNCTION_BAR:.2f} a SECOND time on its CALLER's own cycles, net of those calls on both sides — "
        f"printed below the row on a line of its own (`TWO COUNTS: own / the caller's own (ours against the ROM's)`), "
        f"with the thunks that ran OUTSIDE those calls (the caller's own, measured call by call) counted back: a row "
        f"<= {TIER3_FUNCTION_BAR:.2f} on the second count only net of them is `glue` too.",
        "A row whose image compare leaves a span out prints it below itself, with the case's reason: a difference "
        "by nature (a return address each build parks), which the ROM must write and the case's own differential "
        "still compares.",
        "",
    ]
    # Widths from the rows themselves rather than guessed: a case label one character over a fixed
    # column pushes every figure on that line out of its column, and a table that only lines up for
    # today's labels is one nobody will keep lined up.
    # ...and the two cost columns the same way, each two wider than its longest cell: a fixed width ran a
    # long run's two cells together into one unreadable number.
    name_width = max(len(row.function) for row in ROWS) + 2
    case_width = max(len(row.case) for row in ROWS) + 2
    cost_width = 2 + max([len(COST_HEADER)] + [len(_cost(*side)) for _row, m in measured for side in _costs(m)])
    # The ADDRESS column is what makes the file quotable: STATUS.md's ledger is keyed by ROM address,
    # and `test/test_status.py` pins its Tier 3 cells against these lines by that key.
    lines.append(f"{'function':<{name_width}}{'address':<{ADDRESS_WIDTH}}{'case':<{case_width}}"
                 f"{'original':>{cost_width}}{'recreate':>{cost_width}}{'ratio':>8}")
    lines.append(f"{'':<{name_width}}{'':<{ADDRESS_WIDTH}}{'':<{case_width}}"
                 f"{COST_HEADER:>{cost_width}}{COST_HEADER:>{cost_width}}")
    failed = []
    for row, m in measured:
        state = verdict(row, m, dispatch, measurement_of)
        original, recreate = (_cost(*side) for side in _costs(m))
        lines.append(f"{row.function:<{name_width}}"
                     f"{f'${row.address or row.entry:x}':<{ADDRESS_WIDTH}}"
                     f"{row.case:<{case_width}}"
                     f"{original:>{cost_width}}"
                     f"{recreate:>{cost_width}}"
                     f"{gated_ratio(row, m):>8.2f}  {'' if state == 'ok' else state}")
        if goes_through_the_os(row):
            lines.append(_through_the_os_line(m, name_width + ADDRESS_WIDTH))
            if has_a_second_count(m):
                lines.append(_two_counts_line(m, name_width + ADDRESS_WIDTH))
        if glue_cycles_of(m) and m.ratio > TIER3_FUNCTION_BAR:
            lines.append(f"{'':<{name_width + ADDRESS_WIDTH}}  net of the glue: {ratio_net_of_glue(m):.2f} "
                         f"({glue_cycles_of(m)} of the recreate's cycles are inside thunks)")
        if calls_into_c(row) and m.ratio > TIER3_FUNCTION_BAR:
            lines.append(_own_split_line(m, name_width + ADDRESS_WIDTH))
        lines += [f"{'':<{name_width + ADDRESS_WIDTH}}  dropped from the image compare: [${lo:x}, ${hi:x}) — {why}"
                  for lo, hi, why in row.dropped]
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
    parser.add_argument("--jobs", type=int, default=os.cpu_count(),
                        help="the processes the measuring pass is spread over (default: every core; 1: this "
                             "process alone, row after row) — the table is the same, line for line")
    options = parser.parse_args(argv)

    lines, refused = table(RomBench(), options.jobs)
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
