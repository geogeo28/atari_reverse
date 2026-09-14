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
# Every entry below states the measured ratio and the absolute cycles, because on routines this small
# the absolute number is the one a reader can act on.
PERF_ACCEPTED = {
    ("xbios_giaccess", "read"): (
        0.60, "includes the interrupt bracket the ROM's own `ori.w #$700,sr` makes (ipl.h), which "
              "the Tier 1 differential cannot see: the oracle enters at IPL 7 and reports no SR, so "
              "this cycle count is the whole surface the mask has"),
    ("xbios_giaccess", "write"): (
        0.74, "the same bracket, over the write path's extra port access — see the row above"),

    # (A) — the image pointer, and on these it is the whole of the difference.
    ("bios_drvmap", "bios_drvmap"): (1.50, "(A) 32 -> 48 cycles: two instructions become three"),
    ("xbios_logbase", "xbios_logbase"): (1.50, "(A) 32 -> 48 cycles, the same two-become-three"),
    ("bios_tickcal", "bios_tickcal"): (1.41, "(A) 34 -> 48 cycles, one instruction more"),
    ("bios_kbshift", "read"): (1.48, "(A) 54 -> 80 cycles, one instruction more"),
    ("bios_kbshift", "write"): (1.53, "(A) 64 -> 98 cycles, one instruction more"),
    ("xbios_bioskeys", "xbios_bioskeys"): (1.18, "(A) 88 -> 104 cycles, one instruction more"),
    ("bios_getmpb", "bios_getmpb"): (1.14, "(A) 214 -> 244 cycles, one instruction more"),
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
    ("bios_bcostat", "console"): (
        1.44, "(B) over a driver whose whole body is `moveq #-1,d0`, so the dispatch IS the routine: "
              "90 -> 130 cycles, 8 instructions to 13"),

    # (C) — Cursconf's arm selection, and the widest row here.
    ("xbios_cursconf", "blink"): (
        2.29, "(C) 104 -> 238 cycles, 9 instructions to 25. The widest row in the table and the one "
              "worth a lever first: the C pays the bounds test, the table read the ROM's `jmp` does "
              "for free, and a compare chain to the arm"),
}

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


class EntryD0:
    """The D0 the trap dispatcher left, which a few routines' no-driver arms hand back.

    Taken from the CASE's own input registers rather than re-typed, for `FrameArg`'s reason: the
    oracle is entered with it and our C is passed it, and the two must be one value.
    """

    def of(self, _frame):
        raise AssertionError("EntryD0 is resolved from the case's registers, not from its frame")


ENTRY_D0 = EntryD0()


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
    "BIOS_BCOSTAT": Call((IMAGE, ENTRY_D0, arg_word(0)), RETURNS_LONG),
    "BIOS_DRVMAP": Call((IMAGE,), RETURNS_LONG),
    "BIOS_GETMPB": Call((IMAGE, arg_long(0)), RETURNS_NOTHING),
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
      supexec.STUB_AT: supexec.read_long_from_stack_into_d0() + supexec.RTS}, None, None),
)

# One measured row. `entry`/`regs`/`pokes`/`psg_seed`/`io_seed` are the ORACLE's case, exactly as
# `harness.differential` takes it; `symbol`/`args` are how our build is called; `returns` is the
# width in bytes the C signature declares for its result (see `RomBench.measure`).
Row = namedtuple("Row", "function case entry symbol args regs pokes psg_seed io_seed returns")


def _function_label(entry):
    """"XBIOS Random ($11)" — from `addrs.h`'s own name for the entry and its function NUMBER.

    Not a label typed beside the row: `test_boot_snapshot.py` reads the dispatch table out of the
    mapped ROM and holds every one of these names to the entry it claims, so a label built from them
    cannot claim a function number the ROM does not give it.
    """
    name = test_boot_snapshot.TRAP_ROUTINE_NAMES[entry]
    trap, _, routine = name.partition("_")
    return f"{trap} {routine.capitalize()} (${getattr(addrs, f'{name}_FN'):02x})"


def _symbol(entry):
    """...and the C core's name, which is the same `addrs.h` name lower-cased."""
    return test_boot_snapshot.TRAP_ROUTINE_NAMES[entry].lower()


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
        if arg is ENTRY_D0:
            out.append(regs.get("d0", 0))
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


def _row(case):
    """One `VERIFIED_CASES` entry as a bench row, or None when no `CALL` entry says how to call it."""
    name, entry, regs, pokes, psg_seed, io_seed = case
    routine = test_boot_snapshot.TRAP_ROUTINE_NAMES[entry]
    call = CALL.get(routine)
    if call is None:
        return None
    symbol = _symbol(entry)
    return Row(_function_label(entry), _case_label(name, symbol), entry, symbol,
               _resolve(call.args, pokes, regs), regs, _pokes_for(call, pokes), psg_seed, io_seed,
               call.returns)


ALL_CASES = tuple(test_boot_snapshot.VERIFIED_CASES) + EXTRA_CASES
ROWS = tuple(row for row in (_row(case) for case in ALL_CASES) if row is not None)
# ...and the verified cases this file does NOT price, which `test_tier3.py` reds on. Recorded rather
# than raised at import, so the gate names them all at once instead of the collection dying on the
# first: a function reconstructed without a Tier 3 row is the state the numerator exists to end.
UNPRICED = tuple(case[0] for case, row in zip(ALL_CASES, (_row(c) for c in ALL_CASES))
                 if row is None)


def measure(row, bench):
    """One row's `Measurement` — which is also its second differential, so this raises on a target
    build that does not equal the original."""
    return bench.measure(row.entry, row.symbol, args=row.args, regs=row.regs, pokes=row.pokes,
                         psg_seed=row.psg_seed, io_seed=row.io_seed, returns=row.returns)


def pin_of(row):
    """The `(ratio, why)` this row is pinned at, or None."""
    return PERF_ACCEPTED.get((row.symbol, row.case))


def verdict(row, ratio):
    """What the gate makes of one measured ratio — THE SINGLE RULE, read by the table and the gate.

    "ok" — under the bar and not pinned. "pinned" — under the bar, measuring what it was pinned at.
    "accepted" — over the bar, and an entry says so. "DRIFTED" — pinned, and no longer that number.
    "OVER" — over the bar with nothing accepting it.
    """
    pin = pin_of(row)
    if pin and abs(ratio - pin[0]) > RATIO_TOLERANCE:
        return "DRIFTED"
    if ratio <= TIER3_FUNCTION_BAR:
        return "pinned" if pin else "ok"
    return "accepted" if pin else "OVER"


FAILED = ("OVER", "DRIFTED")

# How wide the ROM-address column renders: `$fc1510` and two spaces. Every entry in this ROM is six
# hex digits, so it is a constant rather than a measurement over the rows.
ADDRESS_WIDTH = 9


def table(bench):
    """Every row measured, as the lines `make bench` writes and STATUS.md quotes."""
    overhead_insns, overhead_cycles = bench.overhead
    lines = [
        "Tier 3 — the recreate against the original, same case, same instrument (Musashi).",
        f"Costs are the oracle's own and include the {overhead_insns} instruction / "
        f"{overhead_cycles} cycles it charges before either entry executes anything; the RATIO is "
        f"net of that on both sides.",
        f"Bar: ratio <= {TIER3_FUNCTION_BAR:.2f} per function; a pinned row must stay within "
        f"{RATIO_TOLERANCE:.2f} of what it was pinned at.",
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
    for row in ROWS:
        m = measure(row, bench)
        state = verdict(row, m.ratio)
        lines.append(f"{row.function:<{name_width}}{f'${row.entry:x}':<{ADDRESS_WIDTH}}"
                     f"{row.case:<{case_width}}"
                     f"{f'{m.original_insns}/{m.original_cycles}':>14}"
                     f"{f'{m.recreate_insns}/{m.recreate_cycles}':>14}"
                     f"{m.ratio:>8.2f}  {'' if state == 'ok' else state}")
        if state in FAILED:
            failed.append((row, state))
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
