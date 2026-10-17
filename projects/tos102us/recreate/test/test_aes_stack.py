"""THE SCREEN MANAGER'S STACK (`aes_stack.py`; ruling W2-R3 of AES band 5 wave 2) — and the stack reading's own
shapes (`aes_switch.StackReading`) that the screen manager's paths were the first to need.

WHAT IS HELD, on both blobs:
  * THE READING'S SHAPES, each over a listing of its own: what it FOLLOWS — a frame pointer's `link` / `unlk`, the
    build's halt, a routine that leaves the stack, a register reused as data on the way out, a function spilt to
    ONE slot of the frame, a routine read for the one routine its caller hands it, a branch into another routine's
    tail, a declared exception word — and, beside each, THE LISTING IN WHICH THE RULE FAILS, refused by name.
  * THE DECLARATIONS, held to the build: who hands everyobj which routine; that ob_user's pointer is the machine's;
    dsptch's cost and the Line-A trap's, each read or measured, never typed in.
  * THE FINDINGS, PINNED (W2-R3): our own frames by chain, the OS's need under a trap by VDI call (EACH BLOB'S OWN
    VDI on our shore, handlers and all — who ran is held), the interrupts' nest, what an application's routine is
    left — and THE VERDICT AS A NUMBER ("N spare" for the shipped blob, the gate; "over by N" for the bench blob,
    reported), for the bound — AT A TRAP CALL BY CALL: each trap site charged
    its own VDI call's measured need — and for each measured run. A FINDING IS ASSERTED, not expected to fail: any change either way —
    a frame flattened, a frame grown — reddens the pin that names it.
  * THE TRAP PATH (band 5 wave 3, rulings W2-R5 and W3-R8) — a process that enters by `trap #2`: THE JUMP TABLE of
    the opcode switch read from the blob's bytes and its refusals; THE DOOR'S SHAPES, each over a listing of its own
    and over THE ROM'S OWN BYTES (a stack begun, a stack left for good, a routine that never returns, a private
    stack left for the one it came on, a declared trap); the bound through the switch on both blobs BESIDE PD2'S
    1,396 BYTES AND AN ALLOCATED PD'S 1,788, by the call; crit_err's and ub_trampoline's private stacks.
    THE VERDICT THERE IS A FINDING TOO, pinned as the number it is: "OVER BY 178" until THE DOOR DIET (wave 3,
    2026-10-11), and since it "FITS, 20 SPARE" for the shipped blob — every arm of the switch, bound and measured —
    with what was cut said above the pins and the bench blob's "over by 150" reported beside it.
  * THE START-UP (band 5 wave 4, rulings W4-R4 and W4-R9) — gem_entry's two stacks: THE START-UP'S SHAPES, each over a
    listing of its own (a run that ends where it began: Super; a routine that loads its stack twice and loops; a
    call out of the build; the desk door's pad; `__DOS`'s return through a parked address; a body cut at its own
    return site's label); THE ROM'S OWN START-UP read through them and HELD TO ITS BOOT (where each routine is
    entered: deskmain 62 under PD0's top), with the ROM's measured depths; and, for each blob, THE TWO GATES BOUND
    AND MEASURED — the first stack's 134 bytes (88 taken, 46 spare) and the ROM-depth rule (every call out of the
    build entered where the ROM enters it; our own boot arriving at deskmain with the ROM's SP) — beside PD0's own
    frames and what dos_exec leaves an application's trap.
THE PINS ARE LAYOUT NUMBERS OF OUR BUILD (as band 4 pins its dispatcher's): a pin that moves is re-pinned WITH THE
REASON — which frame, which call — never to make a run green.
"""
import collections
import re
import struct
from pathlib import Path

import pytest

from harness import BASE_IMAGE, addrs, emu
from recreate_kit import rom_bench

import aes
import aes_boot
import aes_stack as stack
import aes_switch as switch
import case
import derived

LONG_BYTES = aes.LONG_BYTES
BLOBS = stack.BLOBS
StackReading, StackUse = switch.StackReading, switch.StackUse


@pytest.fixture(scope="module", params=BLOBS.values(), ids=BLOBS)
def blob(request):
    """A blob for what is READ off it: the kit's own bench — no battery's registry behind it."""
    return rom_bench.RomBench(request.param)


# ---- THE SHAPES, each over a listing of its own ----------------------------------------------------------------------------
A_LEAF = [(0x200, "rts")]
DEEP = [(0x300, "lea %sp@(-40),%sp"), (0x304, "lea %sp@(40),%sp"), (0x308, "rts")]
STARTS = {0x200: "leaf", 0x300: "deep"}


def _read(body, **declared):
    return StackReading.of_listing({"caller": body, "leaf": A_LEAF, "deep": DEEP}, STARTS, **declared).of("caller")


def _refused(body, by, **declared):
    with pytest.raises(AssertionError, match=by):
        _read(body, **declared)


# (1) A FRAME POINTER'S FRAME.
LINKED = [(0x100, "linkw %fp,#-12"), (0x104, "moveml %d6-%d7,%sp@-"), (0x108, "jsr 300 <deep>"),
          (0x10e, "moveml %sp@+,%d6-%d7"), (0x112, "unlk %fp"), (0x114, "rts")]


def test_a_link_and_its_unlk_are_followed():
    """`link a6,#-12` takes 16 bytes, the `unlk` gives them back WHATEVER SP stands at — the frame pointer says
    where — and the `rts` is reached with the function's own return address under SP."""
    assert _read(LINKED) == StackUse(4 + 12 + 8 + LONG_BYTES + 40, ("caller", "deep"), None, ("caller",))
    # ...SP lowered under the frame and never raised again: the `unlk` alone puts it back.
    unbalanced = [(0x100, "linkw %fp,#-4"), (0x104, "subql #8,%sp"), (0x106, "unlk %fp"), (0x108, "rts")]
    assert _read(unbalanced).deepest == 4 + 4 + 8
    # ...and a frame pointer set by hand (savestate's `movea.l sp,a6` / `unlk a6`).
    assert _read([(0x100, "subql #8,%sp"), (0x102, "moveal %sp,%fp"), (0x104, "unlk %fp"), (0x106, "addql #4,%sp"),
                  (0x108, "rts")]).deepest == 8


@pytest.mark.parametrize("body, by", [
    ([step for step in LINKED if step[1] != "unlk %fp"], "the `rts` at 0x114 is reached 16 bytes below"),
    ([(0x100, "unlk %fp"), (0x102, "rts")], "with no `link` of the function's own reaching it"),
    ([(0x100, "linkw %fp,#-4"), (0x104, "moveal %fp@(8),%fp"), (0x108, "unlk %fp"), (0x10a, "rts")], "A6 stored to"),
    ([(0x100, "linkw %fp,#-4"), (0x104, "moveml %sp@+,%a5-%fp"), (0x108, "unlk %fp"), (0x10a, "rts")], "A6 stored to"),
    ([(0x100, "beqs 108 <caller+0x8>"), (0x102, "linkw %fp,#0"), (0x106, "unlk %fp"), (0x108, "unlk %fp"), (0x10a, "rts")],
     "with no `link` of the function's own reaching it"),
    ([(0x100, "subql #4,%sp"), (0x102, "jmp 200 <leaf>")], "leaves the function 4 bytes below"),
], ids=["the unlk dropped", "an unlk and no link", "the frame pointer loaded since", "the frame pointer popped since",
        "an unlk one path links for and one does not", "a jump away under its own pushes"])
def test_a_frame_the_reading_cannot_follow_is_refused_by_name(body, by):
    _refused(body, by)


# (2) THE HALT.
def test_the_halt_ends_a_path():
    """`trap #7` is `recreate_not_reconstructed` on target: nothing runs after it. What LIES after it — an arm GCC
    laid there, here one the reading would refuse — is read only where another path reaches it."""
    halted = [(0x100, "subql #8,%sp"), (0x102, "trap #7"), (0x104, "trap #1"), (0x106, "rts")]
    assert _read(halted) == StackUse(8, ("caller",), None, ("caller",))
    reached = [(0x100, "beqs 106 <caller+0x6>"), (0x102, "subql #8,%sp"), (0x104, "trap #7"), (0x106, "trap #1"), (0x108, "rts")]
    _refused(reached, "no frame of the OS under a trap")
    # ...and it is no return: a body whose last instruction is the halt runs off nothing.
    assert _read([(0x100, "jsr 300 <deep>"), (0x106, "trap #7")]).deepest == LONG_BYTES + 40
    # ...nor does what a register held where the build halts reach the call laid after it.
    data_then_the_halt = [(0x100, "lea 300 <deep>,%a2"), (0x106, "beqs 10c <caller+0xc>"), (0x108, "moveal %a5@,%a2"),
                          (0x10a, "trap #7"), (0x10c, "jsr %a2@"), (0x10e, "rts")]
    assert _read(data_then_the_halt).path == ("caller", "deep")


# (3) A ROUTINE THAT LEAVES THE STACK: dsptch, as `src/aes/switch.S` and disp have it.
SWITCH = {
    "dsptch": [(0x400, "tstb c67e <x>"), (0x406, "beqs 40a <dsptch+0xa>"), (0x408, "rts"), (0x40a, "movew %sr,%sp@-"),
               (0x40c, "movel %a0,%sp@-"), (0x40e, "jmp 500 <disp>")],
    "disp": [(0x500, "linkw %fp,#-4"), (0x504, "moveml %d7/%a5,%sp@-"), (0x508, "jsr 600 <savestate>"), (0x50e, "rts")],
    "savestate": [(0x600, "tstb c67e <x>"), (0x606, "beqs 60e <savestate+0xe>"), (0x608, "unlk %fp"),
                  (0x60a, "moveal %sp@+,%a0"), (0x60c, "rte"), (0x60e, "linkw %fp,#0"), (0x612, "moveal %sp,%fp"),
                  (0x614, "unlk %fp"), (0x616, "moveal %sp@,%a0"), (0x618, "lea 8c1a <x>,%sp"), (0x61e, "jmp %a0@")],
}
SWITCH_S_BYTES = 2 + 4 + (4 + 4) + 8 + 4 + 4    # SR, A0; disp's link and its two registers; the `jsr`; savestate's link
WAITS = [(0x100, "subql #8,%sp"), (0x102, "jsr 400 <dsptch>"), (0x108, "addql #8,%sp"), (0x10a, "rts")]


def test_a_routine_that_leaves_the_stack_is_a_leaf_of_what_it_takes_first():
    """Read down dsptch's own instructions, THROUGH its jump to disp and disp's call of savestate, to the `lea` that
    leaves: the bytes are the listing's, and a caller holds them under its own."""
    assert switch.bytes_before_it_leaves(SWITCH, "dsptch") == SWITCH_S_BYTES
    read = StackReading.of_listing({"caller": WAITS, **SWITCH}, {0x400: "dsptch"}, leaves_the_stack=("dsptch",))
    assert read.of("caller") == StackUse(8 + LONG_BYTES + SWITCH_S_BYTES, ("caller", "dsptch"), None, ("caller",))


def test_undeclared_the_routine_that_leaves_is_refused_and_a_leaf_that_does_not_leave_is_too():
    """THE RED before the rule: read as any function, dsptch jumps away under its own pushes. And the rule's own
    refusals: a callee that returns, an `rte` that is no return to the caller, a routine that never leaves."""
    with pytest.raises(AssertionError, match="leaves the function 6 bytes below"):
        StackReading.of_listing({"caller": WAITS, **SWITCH}, {0x400: "dsptch"}).of("caller")
    returning = {**SWITCH, "savestate": [(0x600, "rts")]}
    with pytest.raises(AssertionError, match="it returns"):
        switch.bytes_before_it_leaves(returning, "dsptch")
    one_pop_short = {**SWITCH, "savestate": [step for step in SWITCH["savestate"] if step[0] != 0x60a]}
    with pytest.raises(AssertionError, match="is not a return to the routine's own caller"):
        switch.bytes_before_it_leaves(one_pop_short, "dsptch")
    with pytest.raises(AssertionError, match="never leaves the stack"):
        switch.bytes_before_it_leaves({"dsptch": [(0x400, "subql #4,%sp"), (0x402, "addql #4,%sp"), (0x404, "rts")]}, "dsptch")


def test_dsptch_s_cost_is_the_listing_s_and_the_one_a_run_of_it_takes(blob):
    """THE DECLARED LEAF, HELD: what the reading charges a caller for dsptch is read off the blob's own listing of
    `switch.S` and disp — and is what the blob's dsptch stores below the SP it is called at, run on the screen
    manager's stack to disp's loop. More than nothing: a cost of 0 would hide every frame of a park."""
    read = stack.reading(blob.elf).of("aes_dsptch").deepest
    assert read == switch.bytes_before_it_leaves(switch.listed_functions(blob.elf), "aes_dsptch") > 0
    assert stack.dsptch_measured(stack.shore_of(blob)) == read


# (4) A REGISTER REUSED AS DATA, THEN LEFT.
KEPT_THEN_REUSED_ON_THE_WAY_OUT = [
    (0x100, "lea 300 <deep>,%a2"), (0x106, "jsr %a2@"), (0x108, "tstw %d0"), (0x10a, "beqs 114 <caller+0x14>"),
    (0x10c, "jsr %a2@"), (0x10e, "bras 106 <caller+0x6>"),
    (0x114, "moveaw %sp@(8),%a2"), (0x118, "movel %a2,%d0"), (0x11a, "rts")]


def test_a_register_holds_at_a_call_what_the_paths_to_that_call_left_in_it():
    """`aes_mn_do`'s A2: ob_actxywh's address through the loop, an object number on the way out. The data reaches no
    call — so each call through A2 is ob_actxywh's, with no declaration."""
    assert _read(KEPT_THEN_REUSED_ON_THE_WAY_OUT) == StackUse(LONG_BYTES + 40, ("caller", "deep"), None, ("caller",))
    # ...where a branch carries the data back to a call, that call is through a pointer of the machine: refused.
    back_to_a_call = KEPT_THEN_REUSED_ON_THE_WAY_OUT[:-1] + [(0x11a, "bras 10c <caller+0xc>")]
    _refused(back_to_a_call, "calls through %a2 at 0x10[6c], which holds a pointer read out of memory")
    # ...what a call leaves in a scratch register is the callee's; a register popped back is the caller's again.
    _refused([(0x100, "lea 300 <deep>,%a0"), (0x106, "jsr 200 <leaf>"), (0x10c, "jsr %a0@"), (0x10e, "rts")],
             "which holds a pointer read out of memory")
    _refused([(0x100, "movel %a2,%sp@-"), (0x102, "lea 300 <deep>,%a2"), (0x108, "moveal %sp@+,%a2"), (0x10a, "jsr %a2@"),
              (0x10c, "rts")], "nothing it loads there names a function")
    # ...and a call one path reaches with the function loaded and another with nothing loaded is no call of that
    # function alone: refused, where reading every load of the body would have passed it.
    _refused([(0x100, "beqs 108 <caller+0x8>"), (0x102, "lea 300 <deep>,%a2"), (0x108, "jsr %a2@"), (0x10a, "rts")],
             "which a path reaches holding what the function's caller left there")


def test_a_function_spilt_to_a_slot_is_what_that_slot_holds_and_no_other():
    """GCC, where it keeps a frame pointer (`aes_just_draw`), spills a function's address to `d(a6)` and calls
    through it: a slot of the frame, like `d(sp)`. In a function that never `link`s, `d(a6)` is memory. AND A SLOT
    IS ONE PLACE: `4(sp)` after eight bytes pushed is the slot `12(sp)` was before them — while a call through an
    ARGUMENT's slot is not the function a local slot holds."""
    same_slot = [(0x100, "subql #8,%sp"), (0x102, "movel #768,%sp@(4)"), (0x10a, "subql #8,%sp"), (0x10c, "moveal %sp@(12),%a0"),
                 (0x110, "jsr %a0@"), (0x112, "lea %sp@(16),%sp"), (0x116, "rts")]
    assert _read(same_slot).deepest == 16 + LONG_BYTES + 40
    through_an_argument = [(0x100, "subql #8,%sp"), (0x102, "movel #768,%sp@(4)"), (0x10a, "moveal %sp@(12),%a0"),
                           (0x10e, "jsr %a0@"), (0x110, "addql #8,%sp"), (0x112, "rts")]
    _refused(through_an_argument, "calls through %a0 at 0x10e, which holds a pointer read out of memory")
    spilt = [(0x100, "linkw %fp,#-8"), (0x104, "lea 300 <deep>,%a0"), (0x10a, "movel %a0,%fp@(-8)"), (0x10e, "jsr %a0@"),
             (0x110, "moveal %fp@(-8),%a0"), (0x114, "jsr %a0@"), (0x116, "unlk %fp"), (0x118, "rts")]
    assert _read(spilt).deepest == 4 + 8 + LONG_BYTES + 40
    _refused([(0x100, "moveal %fp@(8),%a0"), (0x104, "jsr %a0@"), (0x106, "rts")], "which holds a pointer read out of memory")
    # ...even beside a function the same body spills to a real slot: what `d(a6)` yields there is not that function.
    _refused([(0x100, "movel #768,%sp@(8)"), (0x108, "moveal %fp@(8),%a0"), (0x10c, "jsr %a0@"), (0x10e, "rts")],
             "which holds a pointer read out of memory")


# (5) A POINTER OF THE MACHINE, DECLARED — AND A ROUTINE THAT CALLS WHAT ITS CALLER HANDS IT.
OB_USER = [(0x100, "moveal %a2@(0,%d2:l),%a0"), (0x104, "movel %a3,%sp@-"), (0x106, "jsr %a0@"), (0x108, "addql #4,%sp"),
           (0x10a, "rts")]
WALK = [(0x700, "subql #8,%sp"), (0x702, "moveal %sp@(16),%a0"), (0x706, "jsr %a0@"), (0x708, "addql #8,%sp"), (0x70a, "rts")]
WALKS_AGAIN = [(0x800, "pea 300 <deep>"), (0x806, "jsr 700 <walk>"), (0x80c, "addql #4,%sp"), (0x80e, "rts")]
WALKED = {"walk": WALK, "again": WALKS_AGAIN, "deep": DEEP, "leaf": A_LEAF}
WALK_STARTS = {**STARTS, 0x700: "walk", 0x800: "again"}


def _walking(*pushes):
    body = [(0x100 + 6 * nth, text) for nth, text in enumerate(pushes)]
    at = 0x100 + 6 * len(pushes)
    pushed = 4 * sum(text.startswith(("pea", "clrl")) for text in pushes) - 4 * sum(text.startswith("addql") for text in pushes)
    return body + [(at, "jsr 700 <walk>"), (at + 6, f"lea %sp@({pushed}),%sp"), (at + 10, "rts")]


def _walk_read(body, **declared):
    return StackReading.of_listing({"caller": body, **WALKED}, WALK_STARTS, **declared).of("caller")


def test_an_application_s_routine_is_declared_and_counted_as_its_call():
    """ob_user's `jsr (a0)` is through a USERBLK of the machine: refused undeclared; declared AN APPLICATION'S
    ROUTINE it is the return address and nothing under it — and the chain says where it ends."""
    _refused(OB_USER, "calls through %a0 at 0x106, which holds a pointer read out of memory")
    read = _read(OB_USER, through_a_pointer={"caller": (switch.AN_APPLICATION_S_ROUTINE,)})
    assert read == StackUse(4 + LONG_BYTES, ("caller", switch.AN_APPLICATION_S_ROUTINE), None, ("caller",))


def test_a_routine_that_calls_what_it_is_handed_is_read_for_each_caller_s_routine():
    """everyobj: its pointer is ITS CALLER'S ARGUMENT. Read once for each routine a call site names by value among
    its pushes — a walk handed the leaf is not charged the deep routine another caller hands it, and a routine that
    walks again under a walk is no recursion."""
    handed = {"calls_what_it_is_handed": ("walk",)}
    assert _walk_read(_walking("pea 200 <leaf>"), **handed) == StackUse(4 + LONG_BYTES + 8 + LONG_BYTES, ("caller", "walk<-leaf", "leaf"),
                                                                        None, ("caller",))
    assert _walk_read(_walking("pea 300 <deep>"), **handed).deepest == 4 + LONG_BYTES + 8 + LONG_BYTES + 40
    again = _walk_read(_walking("pea 800 <again>"), **handed)
    assert again.path == ("caller", "walk<-again", "again", "walk<-deep", "deep")
    # ...UNDECLARED, the walk's pointer is one handed in as an argument; declared flat (every routine anyone hands
    # it), the walk under a walk is recursion — the two refusals the rule replaces.
    with pytest.raises(AssertionError, match="walk calls through %a0 at 0x706, which holds a pointer read out of memory"):
        _walk_read(_walking("pea 200 <leaf>"))
    with pytest.raises(AssertionError, match="does not follow recursion"):
        _walk_read(_walking("pea 800 <again>"), through_a_pointer={"walk": ("again", "deep", "leaf")})


@pytest.mark.parametrize("pushes, by", [
    (("pea 1 <x>",), "hands its callee at 0x106 no routine"),
    (("pea 200 <leaf>", "pea 300 <deep>"), "hands its callee at 0x10c \\['deep', 'leaf'\\]"),
    (("pea 200 <leaf>", "jsr 200 <leaf>", "addql #4,%sp", "clrl %sp@-"), "hands its callee at 0x118 no routine"),
], ids=["no routine by value", "two routines by value", "a routine pushed for the call before"])
def test_a_call_site_that_does_not_name_one_routine_is_refused(pushes, by):
    with pytest.raises(AssertionError, match=by):
        _walk_read(_walking(*pushes), calls_what_it_is_handed=("walk",))


# (6) WHAT THE SCREEN MANAGER'S PATHS MET BESIDE THE FIVE.
def test_a_branch_into_another_routine_is_read_from_where_it_lands():
    """A transcription's shared tail (`aes_rom_streq` ends in `aes_rom_unfmt_str`'s `clr.w d0` / `rts`): read FROM
    THE INSTRUCTION BRANCHED TO — the routine's entry, which the branch never runs, may be anything."""
    other = [(0x900, "lea %sp@(-100),%sp"), (0x904, "trap #1"), (0x906, "clrw %d0"), (0x908, "rts")]
    body = [(0x100, "tstb %a0@"), (0x102, "beqw 906 <other+0x6>"), (0x106, "braw 908 <other+0x8>")]
    read = StackReading.of_listing({"caller": body, "other": other}, {0x900: "other"}).of("caller")
    assert read == StackUse(0, ("caller", "other+0x8"), None, ("caller",))


def test_what_gas_and_the_generated_glue_spell_their_own_way():
    """`lea (sp),sp` — the shipped glue's drop after a call of no argument — moves nothing; a label listed twice
    (libgcc's reused `L3`) names no one routine and is refused; a label inside a routine of known end is its own."""
    assert switch.stack_effect("lea %sp@,%sp") == 0
    listing = ("00000100 <first>:\n     100:\t4e 75\trts\n00000102 <L3>:\n     102:\t4e 75\trts\n"
               "00000104 <sized>:\n     104:\t59 8f\tsubql #4,%sp\n00000106 <L1>:\n     106:\t58 8f\taddql #4,%sp\n"
               "     108:\t4e 75\trts\n0000010a <L3>:\n     10a:\t4e 75\trts\n")
    functions = switch.listed_functions_of(listing, {0x104: 0x10a})
    assert sorted(functions) == ["L3", "first", "sized"] and len(functions["sized"]) == 3
    read = StackReading.of_listing(functions)
    assert read.of("sized").deepest == 4
    with pytest.raises(AssertionError, match="labels more than one routine `L3`"):
        read.of("L3")


def test_the_compiler_s_long_arithmetic_is_read_as_the_routines_it_is(blob):
    """libgcc's `__divsi3` and its kin, on the blob: each read whole — its reused local labels inside it, no
    function — and returning where it was entered."""
    read, functions = stack.reading(blob.elf), switch.listed_functions(blob.elf)
    present = [name for name in switch.THE_COMPILER_S_ARITHMETIC if name in functions]
    assert "__divsi3" in present and "__udivsi3" in present
    assert read.of("__divsi3").path == ("__divsi3", "__udivsi3")
    assert all(read.of(name).at_a_trap is None for name in present), "each is read to its own `rts`: no refusal"
    assert not any(isinstance(body, switch.ListedMoreThanOnce) for body in functions.values())


# ---- THE DECLARATIONS, HELD TO THE BUILD -----------------------------------------------------------------------------------
THE_WALKS = {("aes_draw_change", "aes_newrect_alcyon"), ("aes_newrect", "aes_mkrect_alcyon"),
             # (band 6's binding: the table's thunk is a caller — the ROM's desk walks a tree through it)
             ("linef_to_aes_everyobj", stack.FROM_A_ROM_CALLER)}


def test_every_walk_is_handed_one_routine_by_value(blob):
    """everyobj's callers, over the whole blob: draw_change hands newrect, newrect mkrect — each named at the call, so
    every walk the build makes is read for the routine it is really handed — and, since band 6's binding, the Line-F
    table's thunk of it, whose routine is a ROM caller's (the ROM's desk's walks: read where that caller names it). ob_draw IS NONE OF THEM since the door
    diet (band 5 wave 3): it holds the walk as its own body and calls just_draw as C calls (`src/aes/obdraw.c`) —
    read as any routine is, with no Alcyon entry under it and no symbol of one in the blob."""
    assert stack.routines_handed_to(blob.elf, "aes_everyobj") == THE_WALKS
    read = stack.reading(blob.elf)
    assert "aes_just_draw" in read.of("aes_ob_draw").path
    assert not any(name.startswith("aes_everyobj") for name in read.read_as("aes_ob_draw"))
    assert not stack.links(blob.elf, "aes_just_draw_alcyon")


def test_ob_user_s_pointer_is_the_machine_s_and_mn_do_s_register_needs_no_declaration(blob):
    """THE REDS ON THE BUILD: without its declaration ob_user is refused BY NAME (the pointer is a USERBLK's);
    without the walk's rule everyobj is; and mn_do — refused while a register's loads were read without their paths
    — is declared nowhere and read."""
    line_a = {stack.THE_LINE_A_INIT: stack.line_a_need()}
    undeclared = StackReading(blob.elf, switch.THROUGH_A_POINTER, leaves_the_stack=stack.LEAVES_THE_STACK,
                              calls_what_it_is_handed=stack.CALLS_WHAT_IT_IS_HANDED, takes_an_exception=line_a)
    with pytest.raises(AssertionError, match="aes_ob_user calls through %a0 .* a pointer read out of memory"):
        undeclared.of("aes_ob_user")
    unwalked = StackReading(blob.elf, stack.THROUGH_A_POINTER, leaves_the_stack=stack.LEAVES_THE_STACK, takes_an_exception=line_a)
    with pytest.raises(AssertionError, match="aes_everyobj calls through %a0 .* a pointer read out of memory"):
        unwalked.of("aes_draw_change")
    unparked = StackReading(blob.elf, stack.THROUGH_A_POINTER, calls_what_it_is_handed=stack.CALLS_WHAT_IT_IS_HANDED,
                            takes_an_exception=line_a)
    with pytest.raises(AssertionError, match="aes_dsptch: .* leaves the function 6 bytes below"):
        unparked.of("aes_ev_block")
    assert "aes_mn_do" not in stack.THROUGH_A_POINTER and stack.reading(blob.elf).of("aes_mn_do").deepest > 0


def test_the_opcode_switch_is_on_no_path_of_the_screen_manager_s(blob):
    """`aes_dispatch` is compiled as a jump table (ruling W2-R5): no path of the screen manager goes through it — a
    process that enters the AES by `trap #2` does, and THE TRAP PATH below reads it."""
    on_its_paths = stack.reading(blob.elf).functions_read(*stack.entered_at(blob.elf)[0])
    assert stack.THE_OPCODE_SWITCH not in on_its_paths and "aes_ev_multi" in on_its_paths


# (7) WHAT THE LISTING DOES NOT SHOW, AND WHAT THE READING MUST NOT GUESS (the review's shapes: each read LOW before).
LINE_A = ".short 0xa000"


@pytest.mark.parametrize("body, by", [
    ([(0x100, LINE_A), (0x102, "rts")], "`.short 0xa000` at 0x100 is a Line-A trap"),
    ([(0x100, ".short 0xf12c"), (0x102, "rts")], "is a Line-F word"),
    ([(0x100, "psave 508f <x-0x10>"), (0x104, "rts")], "is a Line-F word"),
    ([(0x100, ".short 0x4e41"), (0x102, "rts")], "is a word objdump does not decode"),
    ([(0x100, "trapv"), (0x102, "rts")], "does not know the instruction `trapv`"),
    ([(0x100, "chkw %d0,%d1"), (0x102, "rts")], "does not know the instruction `chkw"),
    ([(0x100, "moveal %a0,%sp"), (0x102, "lea %sp@(-400),%sp"), (0x106, "rts")], "does not follow `moveal %a0,%sp`"),
    ([(0x100, "lea %fp@(-24),%sp"), (0x104, "rts")], "`lea %fp@\\(-24\\),%sp` at 0x100 with no `link`"),
    ([(0x100, "exg %a0,%sp"), (0x102, "rts")], "does not follow `exg %a0,%sp`"),
    ([(0x100, "exg %sp,%a0"), (0x102, "rts")], "does not follow `exg %sp,%a0`"),
    ([(0x100, "subal %d0,%sp"), (0x102, "rts")], "does not follow `subal %d0,%sp`"),
    ([(0x100, "lea 300 <deep>,%a2"), (0x106, "exg %a2,%a3"), (0x108, "jsr %a2@"), (0x10a, "rts")], "holds a pointer read out of memory"),
    ([(0x100, "lea 300 <deep>,%a2"), (0x106, "moveml %a0@,%a2-%a3"), (0x10a, "jsr %a2@"), (0x10c, "rts")],
     "holds a pointer read out of memory"),
    ([(0x100, "lea 300 <deep>,%a2"), (0x106, "tstb %a2@+"), (0x108, "jsr %a2@"), (0x10a, "rts")], "holds a pointer read out of memory"),
    ([(0x100, "movel #768,%d2"), (0x106, "swap %d2"), (0x108, "moveal %d2,%a0"), (0x10a, "jsr %a0@"), (0x10c, "rts")],
     "holds a pointer read out of memory"),
], ids=["a Line-A trap", "a Line-F call word", "a Line-F word as objdump decodes one", "a word of no instruction", "trapv",
        "chk", "SP loaded from a register", "SP set off a frame pointer never linked", "SP exchanged", "SP exchanged, named first", "an alloca",
        "a register exchanged", "registers loaded from memory", "a register stepped by its own operand", "a register swapped"])
def test_what_the_listing_does_not_say_is_refused_by_name(body, by):
    _refused(body, by)


def test_a_declared_exception_word_takes_what_it_is_declared_to_and_sp_comes_back():
    """A Line-A trap DECLARED (`takes_an_exception`: the 68000's frame and its handler's own, measured by whoever
    declares it): charged under the SP it is met at, and nothing of it is left on the stack after."""
    body = [(0x100, "subql #8,%sp"), (0x102, LINE_A), (0x104, "jsr 300 <deep>"), (0x10a, "addql #8,%sp"), (0x10c, "rts")]
    assert _read(body, takes_an_exception={LINE_A: 100}).deepest == 8 + 100
    assert _read(body, takes_an_exception={LINE_A: 42}).deepest == 8 + LONG_BYTES + 40


def test_sp_put_back_into_a_linked_frame_and_the_pushes_and_pops_of_one_operand():
    """`lea d(a6),sp` — the same stack, at the frame's own byte (it was read as a stack LEFT, the count begun again
    at 0: 404 where the truth is 432); `tst.l (sp)+` pops; `st -(sp)` pushes a word; a glue's `movea.l <saved>,sp`
    ends a path ON ITS PRIVATE STACK ONLY."""
    deep = [(0x300, "lea %sp@(-400),%sp"), (0x304, "lea %sp@(400),%sp"), (0x308, "rts")]
    framed = [(0x100, "linkw %fp,#-100"), (0x104, "lea %fp@(-24),%sp"), (0x108, "jsr 300 <deep>"), (0x10e, "unlk %fp"), (0x110, "rts")]
    assert StackReading.of_listing({"caller": framed, "deep": deep}, STARTS).of("caller").deepest == 4 + 24 + LONG_BYTES + 400
    assert _read([(0x100, "movel %d0,%sp@-"), (0x102, "tstl %sp@+"), (0x104, "rts")]).deepest == 4
    assert _read([(0x100, "st %sp@-"), (0x102, "addql #2,%sp"), (0x104, "rts")]).deepest == 2
    glue = [(0x100, "movel %sp,8000 <saved>"), (0x106, "lea 8100 <top>,%sp"), (0x10c, "jsr 300 <deep>"),
            (0x112, "moveal 8000 <saved>,%sp"), (0x118, "rts")]
    assert _read(glue).deepest == LONG_BYTES + 40


def test_the_line_a_trap_in_gsx_mfsave_is_refused_undeclared_and_its_need_is_measured(blob):
    """THE RED ON THE BUILD: `aes_gsx_mfsave`'s `$a000` (ct_mouse saves the mouse form with it, on the screen
    manager's stack) was read as nothing. Undeclared it is refused by name; declared, it takes what the ROM's
    Line-A dispatcher is MEASURED to — the exception frame and more."""
    undeclared = StackReading(blob.elf, stack.THROUGH_A_POINTER, leaves_the_stack=stack.LEAVES_THE_STACK,
                              calls_what_it_is_handed=stack.CALLS_WHAT_IT_IS_HANDED)
    with pytest.raises(AssertionError, match="aes_gsx_mfsave: `.short 0xa000` at 0x[0-9a-f]+ is a Line-A trap"):
        undeclared.of("aes_ct_mouse")
    assert stack.line_a_need() == THE_LINE_A_TRAP_TAKES > stack.EXCEPTION_FRAME_BYTES
    assert stack.reading(blob.elf).of("aes_gsx_mfsave").deepest >= THE_LINE_A_TRAP_TAKES


# ---- THE BOUND: from where it is read ------------------------------------------------------------------------------------------
def test_the_reading_starts_at_the_screen_manager_s_entry_the_moment_a_blob_links_it(blob):
    """BY SYMBOL: a blob that links `aes_rom_ctlmgr` is read FROM IT — entered by an `rte`, nothing allowed above —
    and it is then the one process entry the build hands pstart; until then, from the four handlers under ctlmgr's
    allowance, and the build hands pstart nothing."""
    read, entries = stack.bound(blob), stack.process_entries(blob.elf)
    if stack.links(blob.elf, stack.SCREEN_MANAGER_ENTRY):
        assert (read.entered_at, read.allowed) == ((stack.SCREEN_MANAGER_ENTRY,), 0)
        assert read.chain[0][0] == read.trap_chain[0][0] == stack.SCREEN_MANAGER_ENTRY
        # ---- band 5 wave 3, slice L ---- ...beside gotopgm, which the accessory loader's sndcli hands it: AN APPLICATION'S
        # entry — its `rte` leaves for the program (`stack.process_entries`), no code of the build to read a depth from
        assert entries <= {stack.SCREEN_MANAGER_ENTRY, "aes_rom_gotopgm"}, f"the build hands pstart {entries}: a process entry nothing reads"
    else:
        assert (read.entered_at, read.allowed) == (stack.HANDLERS, stack.CTLMGR_S_OWN_BYTES_ALLOWED) and not entries
        assert read.chain[0] == read.trap_chain[0] == (stack.ALLOWED, stack.CTLMGR_S_OWN_BYTES_ALLOWED)


def test_the_entry_is_found_by_its_symbol_alone(monkeypatch):
    """...and the choice is the symbol table's: with the entry linked, no handler and no allowance."""
    monkeypatch.setattr(stack, "links", lambda elf, symbol: symbol == stack.SCREEN_MANAGER_ENTRY)
    assert stack.entered_at("any blob") == ((stack.SCREEN_MANAGER_ENTRY,), 0)
    monkeypatch.setattr(stack, "links", lambda elf, symbol: False)
    assert stack.entered_at("any blob") == (stack.HANDLERS, stack.CTLMGR_S_OWN_BYTES_ALLOWED)


def test_a_chain_s_frames_sum_to_its_depth_and_every_handler_is_read(blob):
    read = stack.bound(blob)
    assert sum(held for _function, held in read.chain) == read.deepest
    assert sum(held for _function, held in read.trap_chain) == read.at_a_trap
    for handler in stack.HANDLERS:
        assert stack.reading(blob.elf).of(handler).deepest > 0


# ---- THE FINDINGS, PINNED (W2-R3) ------------------------------------------------------------------------------------------
# Every number below is OUR BUILD'S OWN — a frame GCC lays, a call our VDI makes, a handler's pushes — or the ROM's
# beside it; none is a capture's (the runs start at a booted machine's first idle, which the oracle's boot reaches
# the same way every time: `aes_boot`). A PIN THAT MOVES SAYS WHICH FRAME OR WHICH CALL, AND IS RE-PINNED WITH THAT
# REASON. Nothing here is "expected to fail": the verdict is a number, asserted.
#
# RE-PINNED WHOLE BY THE FRAME DIET, 2026-10-10 (`include/stack_diet.h`: 33 routines of these paths, and v_gtext's deep frame since, compiled with the
# -O2 passes that spend stack turned off, just_draw's four parts routines of their own, three bodies taken by their
# one deep caller). WHAT IT WAS, kept as history: own frames 908 (36 spare under the nest); the deepest trap an
# icon's blit at 886 / 896 — with the worst call's need and the nest 1,480 / 1,490, OVER BY 284 / 294; a menu
# dropped measured 952 / 956 (over by 8 / 12 with the nest), an icon in it 1,174 / 1,184 (over by 230 / 240); a
# USERDEF's routine entered 682 down (210 bytes less than under the ROM); untouched at most 88.
#
# AND AGAIN BY THE DOOR DIET, 2026-10-11 (band 5 wave 3; its own section is THE TRAP PATH's, below): made for an
# accessory's stack, three of its cuts lie on the screen manager's paths too — ob_draw holds everyobj's walk as its own
# body and calls just_draw as C calls (170 bytes of three frames became 88), gr_watchbox's wait is a routine of its
# own (100 -> 60), and the marks on the window layer. WHAT IT WAS BEFORE, kept as history: the deepest trap an icon's
# fill in a menu at 614 / 624; the shipped blob's bound 36 SPARE and the bench blob's over by 134; a menu dropped
# measured 1,038 / 864, an icon in it 1,078 / 904; a USERDEF's routine entered 538 down.
#
# AND AGAIN BY ITS THIRD PASS, THE SAME DAY — THE REVIEW'S FINDING: the "need of our VDI" pinned here for a pass was
# the ROM's handlers' behind our dispatcher (a uniform + 32), because the staging mapped no table slot to the blob's
# own handlers. With them bound (`aes_switch.vdi_table_mapping`) the shipped blob's worst chain was OVER BY 16 and
# the bench blob's by 190 — where the pass before had pinned "44 / 40 spare". What the third pass changed in the
# build: the VDI dispatcher's call keeps no register round itself, as the ROM's does not (44 bytes under every VDI
# function), and v_gtext's deep frame carries a mark (12). THE GATE IS THE SHIPPED BLOB — the program; the bench blob
# links the C twins of the raster cores a ROM ships as the ROM's instructions, and its figure is REPORTED, not gated.
SPAN = 1196                             # [uda + 74, $a898): PD1's stack
BENCH, SHIPPED = BLOBS
# OUR OWN FRAMES, deepest: a slider dragged, a press waited for, bchange looking the window up (both blobs).
OWN_CHAIN = (("aes_rom_ctlmgr", 36), ("aes_hctl_button", 28), ("aes_hctl_window", 88), ("aes_gr_slidebox", 68),
             ("aes_gr_dragbox", 88), ("aes_gr_wait", 40), ("aes_gr_stilldn", 64), ("aes_ev_multi", 52), ("aes_forker", 40),
             ("aes_bchange_fork", 16), ("aes_bchange", 32), ("aes_mowner", 24), ("aes_wm_find", 28), ("aes_ob_find", 80),
             ("aes_ob_actxywh", 36), ("aes_ob_offset", 24))
# ...and to the deepest `trap #2`: NO LONGER A DRAW'S (an icon's fill in a menu, 614 / 624 down, until the door diet
# took 82 bytes off every object drawn) but THE MOUSE'S — forker, under the same slider's wait, running mchange,
# which asks the VDI where the mouse is. The shipped blob's VDI bindings go through its generated glue
# (`aes_gsx_ncode`'s 10 bytes).
TO_THE_MOUSE = OWN_CHAIN[:9] + (("aes_mchange_fork", 16), ("aes_mchange", 64))
TRAP_CHAIN = {BENCH: TO_THE_MOUSE + (("aes_gsx_ncode", 0), ("aes_gsx2", 0)),
              SHIPPED: TO_THE_MOUSE + (("aes_gsx_ncode", 10), ("aes_rom_gsx_ncode", 0), ("aes_rom_gsx2", 0))}
OWN_FRAMES, AT_THE_DEEPEST_TRAP = 744, {BENCH: 584, SHIPPED: 594}
# THE OS UNDER A `trap #2`, BY THE VDI'S OPCODE — the lowest STORE under the trap's frame. Through THE ROM'S VDI the
# most is v_gtext's (8), not a blit's (109 vro_cpyfm, 121 vrt_cpyfm: 256) — and the keyboard poll's 130 that band 4
# measures is vsm_string's (31). EVERY CALL THE SCREEN MANAGER'S PATHS CAN MAKE IS HERE (held below): vsl_color (17),
# vsm_locator (28) and vq_mouse (124) are no scenario's and are measured by the ROM's own routines beside them.
# TWO MORE SINCE WAVE 3 (the trap path's: appl_tplay's arm exchanges the motion and the cursor routines — vex_motv 126,
# vex_curv 127 — and no path of the screen manager's asks either; measured by ap_tplay's own row, `THE_ROWS_BESIDE`).
THE_ROM_S_VDI_NEEDS = {6: 184, 8: 310, 12: 132, 17: 112, 22: 112, 23: 140, 24: 144, 25: 112, 28: 128, 31: 130, 32: 112,
                       33: 116, 109: 256, 111: 100, 113: 104, 114: 152, 121: 256, 122: 138, 123: 120, 124: 112, 126: 100,
                       127: 100, 128: 112, 129: 156}
# ...and through EACH BLOB'S OWN VDI — its entry, its dispatcher AND ITS OWN HANDLERS (`who_ran` holds that they ran).
# The shipped blob's raster cores are the ROM's instructions, so its text, lines, fills and blits are within 32 of
# the ROM's (the two image-only thunks, the C handler's frames) and its setters SHALLOWER (no Alcyon `link`); the
# bench blob's are the C twins of those cores, which no ROM ships: 520 under a text, 460 under an icon's blit.
OUR_VDI_NEEDS = {
    BENCH: {6: 304, 8: 520, 12: 124, 17: 96, 22: 96, 23: 108, 24: 108, 25: 96, 28: 142, 31: 138, 32: 96, 33: 96, 109: 320,
            111: 104, 113: 96, 114: 260, 121: 460, 122: 228, 123: 168, 124: 96, 126: 96, 127: 96, 128: 112, 129: 136},
    SHIPPED: {6: 208, 8: 342, 12: 124, 17: 96, 22: 96, 23: 108, 24: 108, 25: 96, 28: 130, 31: 138, 32: 96, 33: 96, 109: 244,
              111: 88, 113: 96, 114: 172, 121: 244, 122: 166, 123: 140, 124: 96, 126: 96, 127: 96, 128: 116, 129: 136}}
# ...and HOW FAR SP CAN HAVE STOOD BELOW THAT STORE: the largest allocation nothing stored under that a run reached
# under the opcode (the rest 0). The shipped blob's blits run the ROM's copy-raster, whose 76-byte frame of locals is
# allocated before anything is stored in it: charged whole. AND ITS LINES AND FILLS RUN ITS OWN ENGINES' 20 — the
# vertical line's `lea -20(sp),sp` and the filled rectangle's `link a6,#-20` (RE-PINNED BY THE FOURTH PASS,
# 2026-10-10: the third had 0 for both, because the Line-A vectors were left naming THE ROM'S engines and a stop at
# the blob's own was never reached; the sites they feed are 84 and 92 bytes from the gate).
UNSTORED_UNDER = {BENCH: {122: 4, 123: 4, 129: 4}, SHIPPED: {6: 20, 109: 76, 114: 20, 121: 76, 129: 4}}
# WHICH RASTER ENGINES RAN under each opcode, the blob's own (the ROM's: never, under any). The shipped blob's are
# the ROM's instructions behind the Line-A vectors; the bench blob's C calls a twin by name where it does not hold
# the engine's body itself (its blits and fills do: no symbol of the twins' is entered under 109, 114 and 121).
V_PLINE, VRO_CPYFM, VR_RECFL = 6, 109, 114
ENGINES_RAN = {
    BENCH: {V_PLINE: ("linea_cpu_vline",), 8: ("linea_cpu_fast_text", "linea_cpu_textblt")},
    SHIPPED: {V_PLINE: ("linea_rom_cpu_hline", "linea_rom_cpu_vline"), 8: ("linea_rom_cpu_fast_text", "linea_rom_cpu_textblt"),
              VRO_CPYFM: ("linea_rom_cpu_blit",), VR_RECFL: ("linea_rom_cpu_rect_fill",), 121: ("linea_rom_cpu_blit",)}}
V_GTEXT, VRT_CPYFM = 8, 121
THE_NEST, THE_HORIZONTAL_BLANK = 252, 8           # hbl 8 + vbl 100 + the deeper MFP handler 144: the ROM's handlers' and ours
THE_LINE_A_TRAP_TAKES = 42
# WHAT AN APPLICATION'S ROUTINE STANDS UNDER (ob_user's `jsr (a0)`). THE DEEPEST ANY PATH OF THE LISTING ENTERS IT:
# 468 down, both blobs — an object WATCHED under a window's button (gr_watchbox > ob_change > just_draw), which the
# reading cannot tell is never a USERDEF. A USERDEF IN A MENU — the path a run makes — is entered 456 down, read off
# the listing (`IN_A_MENU`) and MEASURED the same to the byte; under the ROM, measured, 472.
AT_THE_USERDEF_CALL, IN_A_MENU, UNDER_THE_ROM_S = 468, 456, 472
# ...what PD1's stack then leaves the application's routine at the listing's deepest (728; 476 with the nest), and
# THE FINDING OF THE DOOR DIET: in a menu ours is entered ABOVE the ROM's, 16 bytes more left (66 less before it).
A_USERDEF_S_ROUTINE_IS_LEFT = SPAN - AT_THE_USERDEF_CALL
MORE_LEFT_IN_A_MENU_THAN_UNDER_THE_ROM = 16
THE_MENU_S_PASS = "aes_mn_do"
# THE MEASURED RUNS from the real entry, the lowest store on PD1's stack: (the ROM's machine, ours on the bench
# blob, ours on the shipped blob) — each blob's own VDI, handlers and all, under its traps.
MEASURED = {stack.THE_ELEVATOR: (628, 816, 714), stack.THE_TITLE: (548, 760, 658), stack.THE_CLOSER: (474, 600, 528),
            stack.THE_MENU: (722, 956, 782), stack.THE_ICON: (814, 996, 822), stack.THE_USERDEF: (722, 956, 782)}
UNTOUCHED_AT_MOST = 56                  # what a run's lowest SP can be below its lowest store, by the listing (the AES's frames)
# THE VERDICT, bytes SPARE of the 1,196 (negative: OVER). THE SHIPPED BLOB FITS, 106 SPARE (36 before the door diet);
# THE BENCH BLOB IS OVER BY 64 (134).
# AT ITS TRAPS, CALL BY CALL, each site charged its own call's need and the unstored allocation under it:
#   shipped — the worst is an icon's BLIT (vrt_cpyfm, 518 down: 244 stored + the copy-raster's 76) = 838;
#             its label's text is next (gsx_tblt, 492 down + v_gtext's 342 = 834: 110 spare);
#   bench   — the icon's label's text, 488 + 520 = 1,008.
# THE ICON OF THOSE SITES IS NO LONGER THE MENU'S: the deepest path to gr_gicon is an object watched under a window's
# button (hctl_window > gr_watchbox > ob_change > just_draw), 12 bytes below the menu's own (mn_do > ob_draw >
# just_draw) — a path the listing has and no run makes; the menu's icon, which a run does draw, is held to ITS site
# (`test_a_measured_run_is_never_deeper_than_the_bound_and_the_icon_s_run_is_its_text_s_site`).
THE_WORST_SITE = {BENCH: ("aes_gsx_tblt", 488, (V_GTEXT,)), SHIPPED: ("aes_vrt_cpyfm", 518, (VRT_CPYFM,))}
SPARE_AT_ITS_TRAPS = {BENCH: -64, SHIPPED: 106}
THE_TEXT_S_SITE_ON_THE_SHIPPED_BLOB, ITS_SPARE = ("aes_gsx_tblt", 492), 110
THE_MENU_S_TEXT_SITE = {BENCH: 476, SHIPPED: 480}           # gsx_tblt under the icon's label, the icon an item of a menu
# ...which the listing's deepest text site is BELOW since the door diet: an icon watched under a window's button
# (gr_watchbox > ob_change > just_draw), a path of the listing no run makes, 12 bytes under mn_do > ob_draw > just_draw.
THE_LISTING_S_DEEPEST_TEXT_IS_BELOW_THE_MENU_S_BY = 12
OWN_FRAMES_SPARE = 200                                      # 1,196 - (744 + 252)
# ...and THE COARSE SUM beside it, a call no path makes — the deepest trap charged the worst call's need. OVER on the
# bench blob; ON THE SHIPPED BLOB IT FITS TOO since the door diet, by 8 bytes (it was over by 22).
CHARGED_THE_WORST_IT_IS_OVER_BY = {BENCH: 160, SHIPPED: -8}  # 584 + 520 + 252; 594 + 342 + 252
# The one site whose opcode neither the listing nor a declaration says (gsx_xline's sibling call of gsx_1code, its
# arguments stored into its own argument slots): charged the worst need of all.
SITES_CHARGED_THE_WORST = {"aes_gsx_xline"}
A_VDI_OPCODE_NO_RUN_TAKES = addrs.VDI_ROM_V_OPNWK_OPCODE     # the AES opens its workstation once, in no run measured here


def _moved(read, pinned):
    """The first frame of a chain that is not its pin's — the words of a red."""
    return next((f"{found} where the pin holds {held}" for found, held in zip(read, pinned) if found != held),
                f"{len(read)} frames where the pin holds {len(pinned)}")


def test_finding_our_own_frames_by_chain(blob):
    """THE BOUND, PINNED BY CHAIN on each blob: every frame of the two deepest chains. A frame that grows — or is
    flattened — reddens here BY ITS NAME, on whichever chain it stands."""
    read, shore = stack.bound(blob), stack.shore_of(blob)
    moved = [f"the chain to the deepest trap: {_moved(read.trap_chain, TRAP_CHAIN[shore])}"] * (tuple(read.trap_chain) != TRAP_CHAIN[shore])
    moved += [f"the deepest chain of our own frames: {_moved(read.chain, OWN_CHAIN)}"] * (tuple(read.chain) != OWN_CHAIN)
    assert not moved, f"{shore}: " + "; ".join(moved)
    assert (read.deepest, read.at_a_trap) == (OWN_FRAMES, AT_THE_DEEPEST_TRAP[shore])


def test_finding_the_os_under_a_trap_by_its_call_ours_and_the_rom_s():
    """THE OS TERM, PINNED BY VDI CALL: through the ROM's VDI, and through EACH BLOB'S OWN — its dispatcher and its
    handlers — with, beside each store, the unstored allocation a run reached under it. The icon's blit (vrt_cpyfm)
    is among them: only the staged icon makes it."""
    assert stack.os_needs() == THE_ROM_S_VDI_NEEDS == stack.needs_bounded()
    for shore in BLOBS:
        assert stack.os_needs(shore) == OUR_VDI_NEEDS[shore], f"{shore}: say which handler's frame moved"
        assert {opcode: under for opcode, under in stack.unstored_under(shore).items() if under} == UNSTORED_UNDER[shore]
        assert stack.needs_bounded(shore) == {opcode: need + UNSTORED_UNDER[shore].get(opcode, 0)
                                              for opcode, need in OUR_VDI_NEEDS[shore].items()}
        assert stack.under_a_trap(shore) == OUR_VDI_NEEDS[shore][V_GTEXT]
    only_the_icon_s = {trap.opcode for trap in stack.traps_of(stack.THE_ICON)} - {trap.opcode for trap in stack.traps_of(stack.THE_MENU)}
    assert VRT_CPYFM in only_the_icon_s
    beside = {trap.opcode for name in stack.THE_ROUTINES_BESIDE for trap in stack.traps_beside(name)}
    in_the_scenarios = {trap.opcode for name in stack.SCENARIOS for trap in stack.traps_of(name)}
    assert beside - in_the_scenarios == {addrs.VDI_ROM_VSL_COLOR_OPCODE, addrs.VDI_ROM_LOCATOR_OPCODE, addrs.VDI_ROM_VQ_MOUSE_OPCODE}, (
        "the routines beside the scenarios are run for the three calls no scenario's handler takes")
    rows_beside = {trap.opcode for name in stack.THE_ROWS_BESIDE for trap in stack.traps_of_a_row(name)}
    assert rows_beside - in_the_scenarios - beside == {addrs.VDI_ROM_VEX_MOTV_OPCODE, addrs.VDI_ROM_VEX_CURV_OPCODE}, (
        "ap_tplay's row is run for the two calls of the trap path no run before it takes")


def test_under_our_traps_our_own_handlers_ran_and_the_rom_s_did_not():
    """WHO RAN (the review's blocker, 2026-10-10): for every opcode a need is priced for, the blob's OWN handler was
    entered under that opcode's trap and the ROM table's own entry NEVER — on both blobs; and on the ROM's shore the
    reverse. A staging that stops at the dispatcher (the ROM's handlers behind it) reds here by the opcode's number."""
    for shore in BLOBS:
        ran = stack.who_ran(shore)
        assert set(ran) == set(OUR_VDI_NEEDS[shore])
        assert all(ours >= 1 and the_rom_s == 0 for ours, the_rom_s in ran.values()), (
            f"{shore}: (ours entered, the ROM's entered) by opcode {ran}")
    the_rom_s_own = stack.who_ran(stack.THE_ROM_S)
    assert all(ours == 0 and the_rom_s >= 1 for ours, the_rom_s in the_rom_s_own.values()), the_rom_s_own


def test_the_handler_who_ran_looks_for_is_the_one_of_the_opcode_s_own_name(blob):
    """`who_ran`'s places are NOT the mapping's: each is the symbol `include/addrs.h` names the opcode by
    (`VDI_ROM_VRT_CPYFM_OPCODE` -> `vdi_vrt_cpyfm`), read off the blob's symbol table — so a mapping that answered
    one opcode with another's handler (two of equal need) is entered where this does not look. Held: the names, for
    the two blits; that an opcode `addrs.h` does not name is refused; and that today the two derivations agree."""
    named = {opcode: stack.the_handlers_named_for(opcode, blob.elf) for opcode in (VRO_CPYFM, VRT_CPYFM)}
    assert set(named[VRO_CPYFM]) == {"vdi_vro_cpyfm"} and set(named[VRT_CPYFM]) == {"vdi_vrt_cpyfm"}
    assert named[VRO_CPYFM] != named[VRT_CPYFM]
    with pytest.raises(AssertionError, match="names no VDI_ROM_<NAME>_OPCODE"):
        stack.the_handlers_named_for(0x7FFF, blob.elf)
    for opcode, handler in switch.our_vdi_handlers(blob).items():
        if opcode in OUR_VDI_NEEDS[stack.shore_of(blob)]:
            assert handler.entry in stack.the_handlers_named_for(opcode, blob.elf).values(), f"opcode {opcode}: {handler}"


def test_under_our_traps_our_own_raster_engines_ran_and_the_rom_s_never():
    """WHO RAN, ONE LEVEL DOWN (the third pass's review): under every opcode priced, on both blobs, NO ENGINE OF THE
    ROM'S was entered — none of the ten the booted machine's Line-A vectors hold — and the blob's own were, under the
    opcodes pinned: on the shipped blob through the mapped vectors, on the bench blob by name. On the ROM's shore the
    ROM's run, under the same five opcodes. A staging that leaves the vectors reds here by the opcode's number."""
    for shore in BLOBS:
        ran = stack.engines_ran(shore)
        assert all(the_rom_s == 0 for _ours, the_rom_s in ran.values()), f"{shore}: an engine of the ROM's ran: {ran}"
        assert {opcode: ours for opcode, (ours, _the_rom_s) in ran.items() if ours} == ENGINES_RAN[shore]
    the_rom_s_own = stack.engines_ran(stack.THE_ROM_S)
    assert {opcode for opcode, (_ours, the_rom_s) in the_rom_s_own.items() if the_rom_s} == set(ENGINES_RAN[SHIPPED])
    assert all(ours == () for ours, _the_rom_s in the_rom_s_own.values())


THE_DRAWING_VECTORS = 6                 # bit-blit, fast text, the filled rectangle, the two lines, TextBlt


def test_every_line_a_vector_is_mapped_to_an_engine_of_the_blob_or_declared_left(blob, monkeypatch):
    """THE DECLARED MAPPING OF THE VECTORS, HELD: all ten of the boot's table are answered — on the shipped blob the
    six drawing vectors by the blob's own engine of the ROM routine's name, the console's four declared left; on the
    bench blob, whose C calls its engines by name, every one left. A memory mapped already is refused; and a blob
    that reaches its engines through the vectors and LACKS one is refused by the vector and the ROM routine's name."""
    engines, mapping = switch.our_linea_engines(blob), switch.linea_vector_mapping(blob)
    ships_them = blob.elf == stack.transcription.SHIPPED_ELF
    assert len(engines) == len(switch.linea_vectors()) == switch.vdi.LINEA_VECTOR_COUNT == 10
    assert len(mapping) == (THE_DRAWING_VECTORS if ships_them else 0)
    for vector, held in mapping.items():
        engine = engines[vector]
        assert int.from_bytes(held, "big") == engine.entry != engine.the_rom_s and engine.symbol.startswith("linea_rom_cpu_")
    left = [engine for engine in engines.values() if engine.entry is None]
    assert len(left) == (4 if ships_them else 10)
    mapped = stack.with_our_vdi(stack.make_image(stack.aes_gsx.machine()), stack.shore_of(blob))
    for vector in switch.linea_vectors():
        expected = mapping.get(vector, engines[vector].the_rom_s.to_bytes(4, "big"))
        assert bytes(mapped[vector:vector + 4])[1:] == expected[1:]
    repointed = stack.make_image(stack.aes_gsx.machine())
    repointed[switch.vdi.LINEA_VECTOR_TEXTBLT:switch.vdi.LINEA_VECTOR_TEXTBLT + 4] = (0x12345678).to_bytes(4, "big")
    repointed[blob.base:blob.base + len(blob.blob)] = blob.blob
    with pytest.raises(AssertionError, match="0x2a38 does not hold the ROM's engine"):
        switch._our_vdi_under_the_trap(repointed, blob)
    table = [symbol for symbol in stack.transcription.symbol_table(blob.elf) if symbol.name != "linea_rom_cpu_textblt"]
    monkeypatch.setattr(stack.transcription, "symbol_table", lambda elf: table)
    with pytest.raises(AssertionError, match=r"HAS NO ENGINE FOR THE LINE-A VECTOR AT 0x2a38.*LINEA_ROM_CPU_TEXTBLT"):
        switch._our_engines_of.__wrapped__(blob.elf, True)


def test_the_vectors_the_shipped_blob_s_code_loads_are_mapped_ones():
    """READ OFF THE HANDLERS: every instruction of the shipped blob that loads an address register from a longword
    of the Line-A vector table (`movea.l $2a24,a5 / jsr (a5)`: copy-raster's, the fill's, TextBlt's) names a vector
    the staging maps — none of the console's four, none left to the ROM."""
    blob = stack.blob_of(SHIPPED)
    mapped, vectors = set(switch.linea_vector_mapping(blob)), set(switch.linea_vectors())
    loaded = {int(found.group(1), 16) for run in stack.listed_runs(stack.transcription.listing(blob.elf)) for _at, text in run
              if (found := re.match(r"^moveal ([0-9a-f]+) <[^>]+>,%a\d$", text)) and int(found.group(1), 16) in vectors}
    assert len(loaded) >= 3 and loaded <= mapped, f"loaded as a routine's address: {sorted(map(hex, loaded))}"


def test_every_slot_of_the_vdi_s_tables_is_mapped_to_a_handler_of_the_blob(blob):
    """THE DECLARED MAPPING, HELD: all 71 slots of the two opcode tables have a handler in the blob, by the ROM
    routine's own name; a C handler is reached through an image-only thunk (the build's own shape, to the byte), a
    handler that ships as its `.S` is the slot's value itself — on the shipped blob alone; a memory the mapping was
    not made in is refused."""
    handlers, (slots, thunks) = switch.our_vdi_handlers(blob), switch.vdi_table_mapping(blob)
    assert len(handlers) == len(slots) == len(switch.vdi_table_slots()) == 71
    direct = {handler.symbol for handler in handlers.values() if not handler.through_a_thunk}
    ships_them = blob.elf == stack.transcription.SHIPPED_ELF
    assert direct == ({"vdi_rom_escape", "vdi_rom_vs_color", "vdi_rom_vq_color", "vdi_rom_vr_trnfm", "vdi_rom_vsc_form"}
                      if ships_them else set())
    (at, laid), = thunks.items()
    for handler in handlers.values():
        held = int.from_bytes(slots[handler.slot], "big")
        if handler.through_a_thunk:
            thunk = laid[held - at:held - at + len(switch._an_image_only_thunk_into(handler.entry))]
            assert thunk == switch._an_image_only_thunk_into(handler.entry) and held != handler.entry
        else:
            assert held == handler.entry
    unmapped = stack.make_image(stack.aes_gsx.machine())
    with pytest.raises(AssertionError, match="not this blob's handler"):
        switch.entered_under_the_trap(blob, V_GTEXT, unmapped)
    mapped = stack.with_our_vdi(stack.make_image(stack.aes_gsx.machine()), stack.shore_of(blob))
    assert switch.entered_under_the_trap(blob, V_GTEXT, mapped) == int.from_bytes(slots[handlers[V_GTEXT].slot], "big")
    with pytest.raises(AssertionError, match="mapped already"):
        switch._our_vdi_under_the_trap(mapped, blob)


ALLOCATED_AND_LOADED = [(0x100, "lea %sp@(-76),%sp"), (0x104, "moveal 29a2 <x>,%a2"), (0x10a, "rts")]
ALLOCATED_AND_PUSHED = [(0x100, "lea %sp@(-24),%sp"), (0x104, "moveml %d2-%d7,%sp@-"), (0x108, "rts")]
LINKED_AND_CALLED = [(0x100, "linkw %fp,#-84"), (0x104, "jsr 300 <deep>"), (0x10a, "rts")]
# TextBlt's own entry: a `link` on A5, a store ABOVE the SP it leaves, then the push down the straight line.
LINKED_ON_A5_AND_PUSHED = [(0x100, "linkw %a5,#-84"), (0x104, "clrw %a5@(-82)"), (0x108, "moveml %d3-%d7/%a3-%a4,%sp@-"), (0x10c, "rts")]
LINKED_ON_A5_AND_LEFT = [(0x100, "linkw %a5,#-84"), (0x104, "clrw %a5@(-82)"), (0x108, "beqs 110 <x+0x10>"),
                         (0x10a, "moveml %d3-%d7/%a3-%a4,%sp@-"), (0x10e, "rts")]
TWO_RUNS = [(0x100, "subql #4,%sp"), (0x102, "lea %sp@(-16),%sp"), (0x106, "movew %d0,%sp@(2)"), (0x10a, "tstw %d0"),
            (0x10c, "bnes 120 <x+0x20>"), (0x10e, "subql #8,%sp"), (0x110, "pea 1 <x>"), (0x114, "rts")]
STORED_AT_ITS_OWN_SP = [(0x100, "subql #4,%sp"), (0x102, "movel %d0,%sp@"), (0x104, "rts")]
POPPED_BEFORE_ANY_STORE = [(0x100, "subql #8,%sp"), (0x102, "movel %sp@+,%d0"), (0x104, "movel %d0,%sp@-"), (0x106, "rts")]
AN_UNKNOWN_INSTRUCTION_DOWN_THE_LINE = [(0x100, "subql #8,%sp"), (0x102, "frobl %d0,%d1"), (0x104, "movel %d0,%sp@-"), (0x106, "rts")]


def test_an_allocation_nothing_is_stored_under_is_read_off_the_listing():
    """`unstored_runs`: a run of allocations is one (its last instruction, its bytes whole) when the straight line
    after it is LEFT — a branch, a return, SP raised — before anything is stored at or below the SP it left; a push,
    a `pea`, a call or a store to `(sp)` down that line makes it none. A `link` allocates ON ANY ADDRESS REGISTER;
    and an instruction the stack reading does not know, on that line, is REFUSED by name, not passed over."""
    assert stack.unstored_runs(ALLOCATED_AND_LOADED) == {0x100: 76}
    assert stack.unstored_runs(ALLOCATED_AND_PUSHED) == {} == stack.unstored_runs(LINKED_AND_CALLED)
    assert stack.unstored_runs(LINKED_ON_A5_AND_PUSHED) == {} and stack.unstored_runs(LINKED_ON_A5_AND_LEFT) == {0x100: 84}
    assert stack.unstored_runs(TWO_RUNS) == {0x102: 20}
    assert stack.unstored_runs(STORED_AT_ITS_OWN_SP) == {} and stack.unstored_runs(POPPED_BEFORE_ANY_STORE) == {0x100: 8}
    with pytest.raises(AssertionError, match="does not know the instruction `frobl %d0,%d1`"):
        stack.unstored_runs(AN_UNKNOWN_INSTRUCTION_DOWN_THE_LINE)


A_LISTING = """
00030000 <labelled>:
   30000:\t4e71           \tnop
   30002:\t4e75           \trts
\t...
   30010:\t4fef ffec      \tlea %sp@(-20),%sp
   30014:\t4e75           \trts

00030016 <twice>:
   30016:\t598f           \tsubql #4,%sp
   30018:\t4e75           \trts
00030020 <twice>:
   30020:\t518f           \tsubql #8,%sp
   30022:\t4e75           \trts
"""


def test_every_instruction_of_a_listing_is_scanned_whatever_labels_it(blob):
    """NOTHING IS PASSED OVER: an allocation under no label (the shipped blob's displaced C cores), and under a
    name the listing labels twice, is found — and on each blob the runs hold every instruction the listing has."""
    runs = stack.listed_runs(A_LISTING)
    assert [run[0][0] for run in runs] == [0x30000, 0x30010, 0x30016, 0x30020]
    assert {at: size for run in runs for at, size in stack.unstored_runs(run).items()} == {0x30010: 20, 0x30016: 4, 0x30020: 8}
    listing = stack.transcription.listing(blob.elf)
    listed = sum(bool(switch.LISTED_LINE.match(line)) for line in listing.splitlines())
    assert sum(len(run) for run in stack.listed_runs(listing)) == listed > 50_000
    # ...and ON THE SHIPPED BLOB SOME ALLOCATIONS LIE UNDER NO LABEL the symbol table sizes (a displaced C core's
    # entry, past its symbol's end): found all the same — a scan of the labelled functions alone has fewer.
    labelled = {at for body in switch.listed_functions(blob.elf).values() for at, _text in body}
    under_no_label = set(stack.unstored_allocations(blob.elf)) - labelled
    assert bool(under_no_label) == (blob.elf == stack.transcription.SHIPPED_ELF), sorted(map(hex, under_no_label))
    # ...TextBlt's `link a5,#-84` among them, stored under down its line: not charged, and by the reader's own word.
    textblt = switch.listed_functions(blob.elf)["linea_rom_cpu_textblt"]
    assert textblt[0][1] == "linkw %a5,#-84" and textblt[0][0] not in stack.unstored_allocations(blob.elf)
    assert stack._allocated_by(textblt[0][1]) == 84


def test_the_unstored_charge_is_the_largest_reached_under_the_opcode():
    """Two allocations reached under one call: the LARGER is charged (the smallest, or the first, would be the
    same number on today's blobs, where each opcode reaches one size); one reached under another call is that
    call's; an opcode that reaches none is charged 0."""
    allocations = {0x100: 4, 0x200: 76, 0x300: 20}
    reached = {(VRT_CPYFM, 0x100): 3, (VRT_CPYFM, 0x200): 1, (V_PLINE, 0x300): 2, (V_PLINE, 0x100): 1}
    assert stack.the_largest_reached(reached, allocations, (V_PLINE, V_GTEXT, VRT_CPYFM)) == {V_PLINE: 20, V_GTEXT: 0, VRT_CPYFM: 76}


class _CountsItsStops:
    first = frozenset()

    def stopped(self, pc, sp, memory):
        raise AssertionError("no stop of the inner watch's was armed")


def test_a_place_is_armed_again_at_every_trap():
    """`_ArrivalsAt`: the trap's handler is a stop of the watch's own, so a place reached under one call and next
    under another — nothing else stopping between — is counted for both; and it is no place to count."""
    watch = stack._ArrivalsAt({0x500}, trap=0x900)
    memory = bytearray(0x10000)
    assert watch.first == {0x500, 0x900}
    memory[stack.VDI_OPCODE_AT:stack.VDI_OPCODE_AT + 2] = V_PLINE.to_bytes(2, "big")
    assert watch.stopped(0x500, 0, memory) == {0x900}
    assert watch.stopped(0x900, 0, memory) == {0x500}
    memory[stack.VDI_OPCODE_AT:stack.VDI_OPCODE_AT + 2] = VR_RECFL.to_bytes(2, "big")
    assert watch.stopped(0x500, 0, memory) == {0x900}
    assert watch.arrived == {(V_PLINE, 0x500): 1, (VR_RECFL, 0x500): 1}
    with pytest.raises(AssertionError, match="no place to count"):
        stack._ArrivalsAt({0x900}, trap=0x900)


# ---- THE TRAP SITES: every trap under a call that names its opcode, and every opcode measured ---------------------------------
def test_every_trap_of_the_screen_manager_s_paths_is_under_a_site_and_the_deepest_site_is_the_deepest_trap(blob):
    """THE SITES ARE ALL THE TRAPS: the one routine that takes `trap #2` is reached only through the routines that
    hand an opcode on or by a call that is itself a site — so the deepest site's trap is the reading's deepest trap,
    to the byte — and no other function read takes the trap itself."""
    read, sites = stack.reading(blob.elf), stack.trap_sites(blob.elf)
    assert max(site.depth for site in sites) == stack.bound(blob).at_a_trap
    entries = stack.entered_at(blob.elf)[0]
    takers = {name for name in read.functions_read(*entries) & set(read.functions())
              if any(text == switch.TRAP_2 for _at, text in read.functions()[name])}
    assert takers and takers <= set(stack.TAKES_THE_TRAP), f"`trap #2` is taken in {sorted(takers)}"
    # ...and the routine that takes it is CALLED only by a site or by a routine that hands its opcode on.
    callers = {function.partition(switch.HANDED)[0].partition(switch.INTO)[0] for function in read.read_as(*entries)
               for callee, _under, _at in read.sites(function) if callee.partition(switch.INTO)[0] in stack.TAKES_THE_TRAP}
    # (the shipped blob's `aes_gsx2` is its glue into the `.S`: the trap's own routine, called by its name)
    assert callers <= {site.function for site in sites} | set(stack.HANDS_ITS_OPCODE_ON + stack.TAKES_THE_TRAP)


def test_every_call_a_site_can_make_is_measured_on_every_shore(blob):
    """NO NEED IS ASSUMED: every VDI opcode a site of this blob can ask — read off its call or declared for its
    function — has a measured need through the ROM's VDI and through this blob's own."""
    asked = {opcode for site in stack.trap_sites(blob.elf) if site.opcodes for opcode in site.opcodes}
    assert len(asked) > 15 and asked <= set(stack.os_needs()) and asked <= set(stack.os_needs(stack.shore_of(blob)))
    assert set(stack.os_needs()) == set(THE_ROM_S_VDI_NEEDS)


def test_a_site_whose_opcode_is_not_read_is_charged_what_its_function_is_declared_to_ask_or_the_worst(blob):
    """THE THREE WAYS A SITE IS CHARGED: the opcode its call names; its function's declared ones, the deepest need
    among them; neither — the worst need of any call (pinned: which sites those are)."""
    shore, sites = stack.shore_of(blob), stack.trap_sites(blob.elf)
    assert {site.function for site in sites if site.opcodes is None} == SITES_CHARGED_THE_WORST
    for site in sites:
        if site.opcodes is None:
            assert stack.need_under(site, shore) == stack.under_a_trap(shore)
        elif site.function in stack.OPCODES_DECLARED and len(site.opcodes) > 1:
            assert site.opcodes == stack.opcodes_declared(site.function)
            assert stack.need_under(site, shore) == max(stack.needs_bounded(shore)[opcode] for opcode in site.opcodes)
    # ...THE DEEPEST of a declared function's calls, not the first nor the least (gsx_attr's own three need the same):
    a_text_or_a_setter = stack.TrapSite("a_function", 0x100, 500, (addrs.VDI_ROM_VSWR_MODE_OPCODE, V_GTEXT, addrs.VDI_ROM_VST_COLOR_OPCODE))
    assert stack.need_under(a_text_or_a_setter, shore) == stack.needs_bounded(shore)[V_GTEXT] > stack.needs_bounded(shore)[addrs.VDI_ROM_VSWR_MODE_OPCODE]
    a_blit = stack.TrapSite("a_function", 0x100, 500, (VRT_CPYFM,))
    assert stack.need_under(a_blit, shore) == OUR_VDI_NEEDS[shore][VRT_CPYFM] + UNSTORED_UNDER[shore].get(VRT_CPYFM, 0)
    unmeasured = stack.TrapSite("a_function", 0x100, 500, (A_VDI_OPCODE_NO_RUN_TAKES,))
    with pytest.raises(AssertionError, match="no run.*measured"):
        stack.need_under(unmeasured, shore)


C_CALL = [(0x100, "pea 1 <a-0x2ffff>"), (0x104, "pea 2 <a-0x2fffe>"), (0x108, "pea 72 <a-0x2ff8e>"), (0x10c, "movel %a2,%sp@-"),
          (0x10e, "lea 38e18 <aes_gsx_ncode>,%a3"), (0x114, "jsr %a3@")]
ALCYON_CALL = [(0x200, "movew %d0,%sp@-"), (0x202, "movew #122,%sp@-"), (0x206, "bsrw 300 <aes_rom_gsx_1code>")]


@pytest.mark.parametrize("body, alcyon, opcode", (
    (C_CALL, False, 0x72), (ALCYON_CALL, True, 122),
    ([(0x100, "moveq #113,%d1"), (0x102, "movel %d1,%sp@(44)"), (0x106, "movel %d4,%sp@(40)"), (0x10a, "jmp 300 <aes_gsx_1code>")], False, None),
    ([(0x100, "movel %d3,%sp@-"), (0x102, "movel %a2,%sp@-"), (0x104, "jsr 300 <aes_gsx_ncode>")], False, None),
    ([(0x100, "pea 72 <a-0x2ff8e>"), (0x104, "jsr 300 <aes_gsx_ncode>")], False, None),
    ([(0x0fc, "pea 1 <a-0x2ffff>"), (0x100, "pea 72 <a-0x2ff8e>"), (0x104, "jsr 300 <aes_gsx_ncode>")], False, None),
    ([(0x200, "movew #122,%sp@-"), (0x204, "movew %d0,%sp@-"), (0x206, "bsrw 300 <aes_rom_gsx_1code>")], True, None),
    ([(0x100, "pea ffffffff <b+0xfffa1577>"), (0x104, "movel %a2,%sp@-"), (0x106, "jsr 300 <aes_gsx_1code>")], False, None),
), ids=("a C call: the opcode pushed before the image", "an Alcyon call: the opcode pushed last", "stored, not pushed",
        "a register's value", "no image pushed after it", "two immediates and no image after them",
        "another word pushed after it", "no opcode's value"))
def test_an_opcode_is_read_off_the_call_that_names_it_and_off_nothing_else(body, alcyon, opcode):
    assert stack._opcode_read_at(body, len(body) - 1, alcyon) == opcode


TWO_PATHS_JOINED_AT_THE_IMAGE_S_PUSH = [
    (0x100, "beqs 10a <a_function+0xa>"), (0x102, "pea 8 <a-0x2fff8>"), (0x106, "bras 10e <a_function+0xe>"),
    (0x10a, "pea 20 <a-0x2ffe0>"), (0x10e, "movel %a2,%sp@-"), (0x110, "jsr 300 <aes_gsx_ncode>")]
THE_OPCODE_S_SLOT_STORED_OVER = [(0x100, "pea 20 <a-0x2ffe0>"), (0x104, "movel %a2,%sp@-"), (0x106, "movel %d3,%sp@(4)"),
                                 (0x10a, "jsr 300 <aes_gsx_ncode>")]
ANOTHER_SLOT_STORED = [(0x100, "pea 20 <a-0x2ffe0>"), (0x104, "movel %a2,%sp@-"), (0x106, "movel %d3,%sp@(8)"),
                       (0x10a, "jsr 300 <aes_gsx_ncode>")]
AN_ALCYON_PUSH_A_BRANCH_LANDS_AFTER = [(0x200, "movew #122,%sp@-"), (0x204, "lea 38e18 <aes_rom_gsx_1code>,%a0"),
                                       (0x20a, "jsr %a0@"), (0x20c, "bras 204 <a_function+0x4>")]


@pytest.mark.parametrize("body, alcyon, by", (
    (TWO_PATHS_JOINED_AT_THE_IMAGE_S_PUSH, False, "a branch lands at 0x10e"),
    (THE_OPCODE_S_SLOT_STORED_OVER, False, "stores into the slot of the VDI opcode"),
    (AN_ALCYON_PUSH_A_BRANCH_LANDS_AFTER, True, "a branch lands at 0x204"),
), ids=("two paths joined at the image's push", "the opcode's slot stored over", "a branch landing after an Alcyon push"))
def test_an_opcode_the_text_s_order_cannot_say_is_refused_by_name(body, alcyon, by):
    """THE REVIEW'S TWO SHAPES (neither in today's listings: all 38 sites of both blobs read or declared): read in
    text order the first was the cheaper of two opcodes and the second a stale immediate. Refused, by the address."""
    with pytest.raises(AssertionError, match=by):
        stack._opcode_read_at(body, len(body) - 1 if not alcyon else 2, alcyon, "a_function")


def test_a_store_into_another_argument_s_slot_is_passed_over():
    assert stack._opcode_read_at(ANOTHER_SLOT_STORED, len(ANOTHER_SLOT_STORED) - 1, False) == 0x20


_A_VDI_OPCODE_NAMED = re.compile(r"\bVDI_ROM_\w+_OPCODE\b")


def _c_body_of(function):
    source = (derived.RECREATE / "src" / "aes" / stack.THE_SOURCE_OF[function]).read_text()
    return re.search(rf"^[\w \*]+\b{function}\(.*?^}}", source, re.MULTILINE | re.DOTALL).group(0)


@pytest.mark.parametrize("function", stack.OPCODES_DECLARED)
def test_a_declared_function_s_opcodes_are_its_source_s_and_its_listing_s(function, blob):
    """A DECLARATION HELD TWICE: the opcodes a function is declared to ask are exactly the ones its C body names —
    and each is an immediate of its listing on this blob (a function rewritten to ask another reddens here)."""
    assert set(_A_VDI_OPCODE_NAMED.findall(_c_body_of(function))) == set(stack.OPCODES_DECLARED[function])
    immediates = {int(value) for _at, text in stack.reading(blob.elf).functions()[function] for value in re.findall(r"#(\d+)\b", text)}
    # ...a word of its own, or the high word of the longword contrl[0] and [1] are stored as (gsx_tblt's).
    as_a_high_word = {value >> aes.WORD_BYTES * 8 for value in immediates}
    for opcode in stack.opcodes_declared(function):
        assert opcode in immediates | as_a_high_word, f"{function}'s listing has no immediate {opcode}"


def test_finding_the_nest_a_horizontal_blank_a_vertical_blank_inside_it_an_mfp_interrupt_inside_that():
    """THE NEST, PINNED: each handler's need measured on its own entry — the ROM's from its vectors, ours the build's
    — and equal. The horizontal blank's 8 bytes are charged: its handler raises nothing, so a vertical blank is
    taken inside it (`aes_stack`'s comment says why it cannot be ruled out)."""
    assert stack.hbl_need() == THE_HORIZONTAL_BLANK and stack.nest() == THE_NEST
    for shore in BLOBS:
        assert (stack.hbl_need(shore), stack.nest(shore)) == (THE_HORIZONTAL_BLANK, THE_NEST)
        assert stack.nest(shore) == THE_HORIZONTAL_BLANK + switch.worst_interrupt_need(switch.our_interrupt_needs(stack.blob_of(shore)))


def test_the_dispatcher_s_stack_is_charged_the_same_nest():
    """BAND 4'S FIGURE TAKES THE HORIZONTAL BLANK TOO (the frame diet's pass, 2026-10-10: `test_aes_evdisp_model.py`
    charged a vertical blank and an MFP interrupt, 244, and reported 40 spare of 640): what it pins as left of the
    dispatcher's 640 bytes is under this module's nest — and is more than it was, the same marks having flattened
    forker's paths."""
    import test_aes_evdisp_model as dispatcher
    for shore, directory in BLOBS.items():
        blob = rom_bench.RomBench(directory)
        slack = dispatcher.THE_SLACK[blob.elf.parent.name]
        assert slack == dispatcher.DISPATCHER_STACK_BYTES - dispatcher._bound(blob) - stack.nest(shore) and slack > 0


def test_finding_the_verdict_the_shipped_blob_fits_its_stack_and_the_bench_blob_s_figure_is_reported(blob):
    """THE VERDICT AGAINST W2-R3, AS NUMBERS, each blob's own VDI under its traps. Our own frames with the nest on
    top: 200 spare on both. At its traps, each site charged ITS OWN call's need, the unstored allocation under it
    and the nest: THE SHIPPED BLOB — THE PROGRAM, AND THE GATE — FITS WITH 106 TO SPARE, its worst an icon's blit;
    THE BENCH BLOB IS OVER BY 64 at the icon's label, under the C twin of a text blit no ROM ships (reported, not
    gated: a measuring build). A frame that grows on either changes THIS PIN, by name."""
    shore, read = stack.shore_of(blob), stack.bound(blob)
    assert SPAN - (read.deepest + stack.nest(shore)) == OWN_FRAMES_SPARE
    needed, at_a_trap = stack.need(blob)
    deepest, site = stack.at_its_traps(blob)
    assert at_a_trap and SPAN - needed == SPARE_AT_ITS_TRAPS[shore], (
        f"{shore}: the bound needs {needed} of {SPAN} — {SPAN - needed} spare, where the finding holds "
        f"{SPARE_AT_ITS_TRAPS[shore]}: say which frame or call moved, and re-pin")
    assert (site.function, site.depth, site.opcodes) == THE_WORST_SITE[shore]
    assert needed == deepest + THE_NEST == site.depth + stack.needs_bounded(shore)[site.opcodes[0]] + THE_NEST


SPARE_BEFORE_THE_DOOR_DIET = 36          # the shipped blob's screen manager, at 05bc5d6


def test_the_gate_is_the_shipped_blob_and_it_fits_with_room():
    """THE GATE ON THE FLIP (ruling W2-R3; the third pass's rulings): the SHIPPED blob's bound, its own handlers
    bound, is inside the 1,196 bytes with at least 32 to spare — and its text's site, the icon's label, with 110.
    THE DOOR DIET MUST NOT MAKE IT WORSE (its brief): it had 36 to spare before, and has no less."""
    shipped = stack.blob_of(SHIPPED)
    needed, _at_a_trap = stack.need(shipped)
    assert SPAN - needed >= 32 and SPAN - needed >= SPARE_BEFORE_THE_DOOR_DIET
    function, depth = THE_TEXT_S_SITE_ON_THE_SHIPPED_BLOB
    text = max((site for site in stack.trap_sites(shipped.elf) if site.function == function), key=lambda site: site.depth)
    assert (text.depth, SPAN - text.depth - stack.need_under(text, SHIPPED) - THE_NEST) == (depth, ITS_SPARE)


def test_finding_charged_the_worst_call_at_its_deepest_trap_the_bound_would_be_over(blob):
    """THE COARSE SUM, KEPT AS A FINDING: the deepest trap (the mouse asked for under a slider's wait) with the worst
    need of any call (a text's) under it and the nest — a call no path makes. OVER BY 160 ON THE BENCH BLOB; the
    shipped blob's is INSIDE the stack by 8 since the door diet (over by 22 before it). The call-by-call bound is
    never above it."""
    shore = stack.shore_of(blob)
    assert stack.need_charged_the_worst(blob) - SPAN == CHARGED_THE_WORST_IT_IS_OVER_BY[shore]
    assert stack.need(blob)[0] <= stack.need_charged_the_worst(blob)
    assert stack.need_charged_the_worst(blob) == stack.bound(blob).at_a_trap + stack.under_a_trap(shore) + stack.nest(shore)


def test_finding_what_an_application_s_routine_is_left(blob):
    """A USERDEF'S DRAW ROUTINE RUNS ON THIS STACK, and no reading bounds it: so what is said of it is what it HAS.
    The deepest any path of the listing enters it is 468 bytes down (an object watched under a window's button): 728
    left, 476 with the interrupts' nest. IN A MENU — the path a run makes — it is entered 456 down, the listing's
    figure and the measured one to the byte; under the ROM, 472: 16 bytes MORE left than under the ROM. (Before the
    door diet, 2026-10-11: 538 down in a menu, 66 less than under the ROM; before the frame diet: 682, 210 less.)"""
    shore, read = stack.shore_of(blob), stack.reading(blob.elf)
    depth, path = stack.at_the_userdef_call(blob)
    assert depth == AT_THE_USERDEF_CALL and path[-2:] == ("aes_ob_user", stack.AN_APPLICATION_S_ROUTINE)
    assert (SPAN - depth, SPAN - depth - stack.nest(shore)) == (A_USERDEF_S_ROUTINE_IS_LEFT, A_USERDEF_S_ROUTINE_IS_LEFT - THE_NEST)
    in_a_menu = (read.deepest_to(stack.SCREEN_MANAGER_ENTRY, THE_MENU_S_PASS)[0]
                 + read.deepest_to(THE_MENU_S_PASS, stack.AN_APPLICATION_S_ROUTINE)[0])
    assert in_a_menu == IN_A_MENU <= depth
    assert stack.measured(stack.THE_USERDEF, shore).userdef_at == in_a_menu, "the listing's depth at the menu's call is the run's"
    assert stack.measured(stack.THE_USERDEF).userdef_at == UNDER_THE_ROM_S
    assert UNDER_THE_ROM_S - in_a_menu == MORE_LEFT_IN_A_MENU_THAN_UNDER_THE_ROM > 0


@pytest.mark.parametrize("scenario", stack.SCENARIOS)
def test_finding_the_measured_runs_from_the_real_entry(scenario):
    """EACH SCENARIO, RUN: the ROM-booted machine and the two whose screen manager is ours (our VDI under their
    traps), continued by the same hand — the same handlers called — and the lowest byte of PD1's stack each stores."""
    runs = [stack.measured(scenario, shore) for shore in (stack.THE_ROM_S, *BLOBS)]
    assert tuple(run.deepest for run in runs) == MEASURED[scenario], f"{scenario}: say which frame or call moved"
    assert runs[0].observed == runs[1].observed == runs[2].observed


# THE MEASURED VERDICT: a run's lowest store + the nest, bytes SPARE of the stack (negative: OVER) — bench, shipped.
# ON THE SHIPPED BLOB EVERY RUN FITS: a menu dropped with 162 to spare, an icon in it with 122 (80 and 40 before the
# door diet). On the bench blob the menu's two are still over, by 12 and 52 (its C text blit). (Before the frame diet
# a menu dropped was over by 8 / 12 with THE ROM'S handlers behind our dispatcher — which was all that was measured.)
MEASURED_SPARE = {stack.THE_ELEVATOR: (128, 230), stack.THE_TITLE: (184, 286), stack.THE_CLOSER: (344, 416),
                  stack.THE_MENU: (-12, 162), stack.THE_ICON: (-52, 122), stack.THE_USERDEF: (-12, 162)}
# ...and how far each still is from the ROM's own run (bench, shipped): the ABI's longword slots and image pointer on
# every call of the path, the two thunks under the trap — and, on the bench blob, the raster cores' C twins. AN ICON
# IN A MENU IS 8 BYTES FROM THE ROM'S OWN RUN on the shipped blob (90 before the door diet).
DEEPER_THAN_THE_ROM_S_BY = {stack.THE_ELEVATOR: (188, 86), stack.THE_TITLE: (212, 110), stack.THE_CLOSER: (126, 54),
                            stack.THE_MENU: (234, 60), stack.THE_ICON: (182, 8), stack.THE_USERDEF: (234, 60)}


@pytest.mark.parametrize("scenario", stack.SCENARIOS)
def test_finding_the_verdict_of_a_measured_run_with_the_nest_on_top(scenario):
    """...AND WHAT EACH IS BESIDE THE STACK with the nest on top: ON THE SHIPPED BLOB EVERY RUN FITS — and how much
    deeper than the ROM's own run each still goes. The ROM's own run fits every time. (A run's depth is its lowest
    STORE: SP itself may have stood lower — by the AES's `untouched_at_most`, or an unstored allocation of the VDI's.)"""
    spare = tuple(SPAN - stack.measured(scenario, shore).deepest - stack.nest(shore) for shore in BLOBS)
    assert spare == MEASURED_SPARE[scenario] and spare[1] > 0, (
        f"{scenario}: {spare} spare (bench, shipped) where the finding holds {MEASURED_SPARE[scenario]}")
    deeper = tuple(stack.measured(scenario, shore).deepest - stack.measured(scenario).deepest for shore in BLOBS)
    assert deeper == DEEPER_THAN_THE_ROM_S_BY[scenario]
    assert stack.measured(scenario).deepest + stack.nest() <= SPAN, "the ROM's own run, its own handlers on top"


def test_a_measured_run_is_never_deeper_than_the_bound_and_the_icon_s_run_is_its_text_s_site(blob):
    """WHAT HOLDS THE READING TO THE TRUTH: no run is deeper than the listing's bound with each trap's own need under
    it — and the staged icon's run IS a site of the reading, realised: its lowest store is the depth of gsx_tblt's
    trap under the icon's label and this blob's own v_gtext's need under it, to the byte. THE SITE IS THE MENU'S —
    the deepest gsx_tblt under mn_do, where the run draws its icon — which since the door diet is 12 bytes above the
    listing's deepest (an icon watched under a window's button: a path no run makes). (The shipped blob's WORST site
    is the icon's blit, by the unstored 76 no store shows.)"""
    shore, read, listing = stack.shore_of(blob), stack.bound(blob), stack.reading(blob.elf)
    at_its_traps, _site = stack.at_its_traps(blob)
    for scenario in stack.SCENARIOS:
        assert stack.measured(scenario, shore).deepest <= max(read.deepest, at_its_traps)
    menu_at = listing.deepest_to(stack.SCREEN_MANAGER_ENTRY, THE_MENU_S_PASS)[0]
    text = max((site for site in stack.trap_sites_under(listing, THE_MENU_S_PASS, menu_at) if site.opcodes == (V_GTEXT,)),
               key=lambda site: site.depth)
    deepest = max((site for site in stack.trap_sites(blob.elf) if site.opcodes == (V_GTEXT,)), key=lambda site: site.depth)
    assert text.depth == THE_MENU_S_TEXT_SITE[shore] == deepest.depth - THE_LISTING_S_DEEPEST_TEXT_IS_BELOW_THE_MENU_S_BY
    assert stack.measured(stack.THE_ICON, shore).deepest == text.depth + stack.os_needs(shore)[V_GTEXT]


def test_the_two_limits_of_a_measured_depth_are_said_and_the_first_is_bounded(blob):
    """A MEASURED DEPTH IS A LOWEST STORE, not a lowest SP — an allocated frame's untouched bottom is invisible to a
    write ledger (the oracle's run has no per-instruction hook a suite can afford) — and no interrupt is TAKEN at a
    run's deepest point. The first is bounded from the listing: no function the reading reads allocates more than
    this many bytes in a run of instructions that store nothing there."""
    assert stack.untouched_at_most(blob) == UNTOUCHED_AT_MOST
    allocating = [(0x100, "linkw %fp,#-12"), (0x104, "lea %sp@(-40),%sp"), (0x108, "subql #8,%sp"), (0x10a, "movel %d0,%sp@-"),
                  (0x10c, "lea %sp@(-20),%sp"), (0x110, "jsr 300 <deep>"), (0x116, "subql #4,%sp"), (0x118, "rts")]
    assert stack.longest_allocation(allocating) == 12 + 40 + 8, "a run of allocations counts whole; a push or a call ends it"
    assert "lowest STORE" in stack.LIMITS and "no interrupt" in stack.LIMITS and stack.LIMITS in stack.report()


def test_the_stack_is_read_off_the_machine():
    lo, top = stack.stack_of(stack._booted(stack.THE_ROM_S).image())
    assert top - lo == SPAN and lo == stack.aes_event.uda_of(stack.SCREEN_MANAGER, stack._booted(stack.THE_ROM_S).image()) + aes.UDA_STATE_BYTES


# ================================================================================================================================
# THE TRAP PATH (band 5 wave 3; rulings W2-R5, W3-R8): a process that enters the AES by `trap #2`
# ================================================================================================================================
# ---- (8) THE JUMP TABLE, over a listing of its own ---------------------------------------------------------------------------
TABLE_AT = 0x11c
DEFAULT_ARM, THE_DEEP_ARM, THE_LEAF_ARM = 0x122, 0x128, 0x130
# A switch of three words as GCC lays one: the frame, the guard, the index widened and doubled, the word loaded, the
# jump — THE TABLE'S WORDS AS OBJDUMP DECODES THEM (one "instruction" that would take 4,000 bytes if it were walked)
# — the default arm, and two arms that branch back to it.
A_SWITCH = [(0x100, "lea %sp@(-24),%sp"), (0x104, "cmpiw #2,%d0"), (0x108, "bhiw 122 <caller+0x22>"),
            (0x10c, "andil #65535,%d0"), (0x112, "addl %d0,%d0"), (0x114, "movew %pc@(11c <caller+0x1c>,%d0:l),%d0"),
            (0x118, "jmp %pc@(11c <caller+0x1c>,%d0:w)"),
            (TABLE_AT, "lea %sp@(-4000),%sp"), (0x120, ".short 0x0006"),
            (DEFAULT_ARM, "lea %sp@(24),%sp"), (0x126, "rts"),
            (THE_DEEP_ARM, "jsr 300 <deep>"), (0x12e, "bras 122 <caller+0x22>"),
            (THE_LEAF_ARM, "subql #8,%sp"), (0x132, "jsr 200 <leaf>"), (0x138, "addql #8,%sp"), (0x13a, "bras 122 <caller+0x22>")]
ITS_WORDS = (THE_DEEP_ARM - TABLE_AT, THE_LEAF_ARM - TABLE_AT, DEFAULT_ARM - TABLE_AT)
THE_SWITCH_S_FRAME = 24


def _bytes_of(words, at=TABLE_AT):
    """`{address: byte}` of a table's `words` laid at `at`: what `StackReading.of_listing` reads a table from."""
    return dict(enumerate(struct.pack(f">{len(words)}H", *(word & aes.WORD_MASK for word in words)), at))


def _with(body, **replaced):
    """`body` with the instruction at each `at_<hex address>` replaced."""
    by_address = {int(name[len("at_"):], 16): text for name, text in replaced.items()}
    assert set(by_address) <= {at for at, _text in body}
    return [(at, by_address.get(at, text)) for at, text in body]


def test_a_jump_table_is_read_from_the_bytes_and_every_arm_is_walked_at_the_depth_of_the_jump():
    """THE SHAPE (ruling W2-R5): the count is the guard's (`cmpi.w #2`: three words), the words are the BYTES', each
    a distance from the table; every arm is walked at the depth of the `jmp` — the deep one's callee under the
    frame — and the table's own words, which the listing prints as an instruction of 4,000 bytes, never are."""
    read = StackReading.of_listing({"caller": A_SWITCH, "leaf": A_LEAF, "deep": DEEP}, STARTS, text_bytes=_bytes_of(ITS_WORDS))
    assert read.tables("caller") == {0x118: switch.JumpTable(TABLE_AT, 3, (THE_DEEP_ARM, THE_LEAF_ARM, DEFAULT_ARM))}
    assert read.of("caller").deepest == THE_SWITCH_S_FRAME + LONG_BYTES + 40
    assert {read.depth_at("caller", arm) for arm in (DEFAULT_ARM, THE_DEEP_ARM, THE_LEAF_ARM)} == {THE_SWITCH_S_FRAME}
    assert read.returns("caller")
    # ...and WHICH CALLS ONE ARM MAKES (`reached_from`): the deep arm's and the default's instructions, not the leaf arm's.
    assert read.reached_from("caller", THE_DEEP_ARM) == {THE_DEEP_ARM, 0x12e, DEFAULT_ARM, 0x126}
    # A WORD IS SIGNED: an arm BEFORE the table (here the guard again) is reached by a negative distance.
    backwards = [(0x100, "tstw %d0"), *_with(A_SWITCH[1:7], at_104="cmpiw #1,%d0", at_108="bhiw 120 <caller+0x20>"),
                 (TABLE_AT, "orib #0,%d0"), (0x120, "rts"), (0x122, "jsr 300 <deep>"), (0x128, "rts")]
    read = StackReading.of_listing({"caller": backwards, "deep": DEEP}, STARTS, text_bytes=_bytes_of((0x122 - TABLE_AT, 0x104 - TABLE_AT)))
    assert read.tables("caller")[0x118].targets == (0x122, 0x104) and read.of("caller").deepest == LONG_BYTES + 40


@pytest.mark.parametrize("body, words, by", [
    (_with(A_SWITCH, at_104="moveq #2,%d1"), ITS_WORDS, "has no guard the stack reading knows"),
    (_with(A_SWITCH, at_10c="tstw %d0"), ITS_WORDS, "has no guard the stack reading knows"),
    (_with(A_SWITCH, at_114="movew %pc@(11c <caller+0x1c>,%d1:l),%d0"), ITS_WORDS, r"name the registers \['%d0', '%d1'\]"),
    (_with(A_SWITCH, at_114="movew %pc@(120 <caller+0x20>,%d0:l),%d0"), ITS_WORDS, "and the tables 120 / 11c"),
    (A_SWITCH, ITS_WORDS[:2], "word 2 of the jump table at 0x11c is not among the bytes"),
    (A_SWITCH, (ITS_WORDS[0], 2, ITS_WORDS[2]), "word 1 of the jump table at 0x11c leads to 0x11e — no listed instruction"),
    (A_SWITCH, (ITS_WORDS[0], 0x13, ITS_WORDS[2]), "word 1 of the jump table at 0x11c leads to 0x12f — no listed instruction"),
    (_with(A_SWITCH, at_13a="bras 112 <caller+0x12>"), ITS_WORDS, "a branch lands at 0x112, between the guard"),
    (_with(A_SWITCH, at_13a="bras 11c <caller+0x1c>"), ITS_WORDS, "a path reaches 0x11c, inside a jump table's words"),
], ids=["no compare", "the index not widened", "two registers", "two tables", "a word the bytes do not hold",
        "a word into the table itself", "a word to no instruction", "a branch past the guard", "a path into the table's words"])
def test_a_jump_table_the_reading_cannot_read_is_refused_by_name(body, words, by):
    """EACH SHAPE THE RULE FAILS IN: a count that would be a guess, a table read from the listing's noise, an arm
    that is none, a path that skips the guard — refused, never read short."""
    _refused(body, by, text_bytes=_bytes_of(words))


def test_a_register_loaded_before_the_switch_holds_its_function_in_every_arm():
    """THE FLOW GOES THROUGH THE TABLE (`_Loads`): a function GCC keeps in a register across the switch is what an
    arm's `jsr (a2)` calls — read without the table, no path reached the arm and the call had no callee."""
    kept = [(0x100, "lea 300 <deep>,%a2"), *A_SWITCH[1:7], (TABLE_AT, "orib #0,%d0"), (0x120, ".short 0x0006"),
            (DEFAULT_ARM, "rts"), (THE_DEEP_ARM, "jsr %a2@"), (0x12a, "rts"), (THE_LEAF_ARM, "rts")]
    assert _read(kept, text_bytes=_bytes_of(ITS_WORDS)).deepest == LONG_BYTES + 40


# THE OPCODE SWITCH'S OWN TABLE, as `src/aes/gemsuper.c`'s switch is: the ROM's 116 words (opcodes 10..125), 68 arms
# that are a call and the default the 48 others share. Numbers of the SOURCE's switch, not of a layout.
THE_SWITCH_S_WORDS, ITS_ARMS, OPCODES_OF_THE_DEFAULT_ARM = 116, 69, 48
GEMSUPER = aes.header_constants("gemsuper.h")


def test_the_opcode_switch_s_table_is_the_blob_s_own_bytes_and_every_arm_is_reached(blob):
    """ON THE BUILD: one table, as long as its guard says, EACH WORD THE BLOB'S OWN (read out of the binary here, off
    the listing's hexadecimal column there: equal), its first word appl_init's; every arm stands at the depth of the
    jump, the guard's branch goes to the arm the 48 unassigned opcodes share — and with the bytes withheld the
    build's switch is REFUSED."""
    read = stack.trap_reading(blob.elf)
    table, first = stack.the_switch_s_table(blob.elf)
    held = struct.unpack_from(f">{table.words}h", blob.blob, table.at - blob.base)
    assert table.targets == tuple(table.at + distance for distance in held)
    assert (table.words, len(set(table.targets)), first) == (THE_SWITCH_S_WORDS, ITS_ARMS, GEMSUPER["AES_APPL_INIT_OPCODE"])
    (jump,) = read.tables(stack.THE_OPCODE_SWITCH)
    body = read.functions()[stack.THE_OPCODE_SWITCH]
    read.of(stack.THE_OPCODE_SWITCH)
    assert {read.depth_at(stack.THE_OPCODE_SWITCH, arm) for arm in table.targets} == {read.depth_at(stack.THE_OPCODE_SWITCH, jump)}
    default = int(next(text for _at, text in body if text.startswith("bhi")).split(" ")[1], 16)
    assert table.targets.count(default) == OPCODES_OF_THE_DEFAULT_ARM == max(map(table.targets.count, table.targets))
    with pytest.raises(AssertionError, match="word 0 of the jump table at 0x[0-9a-f]+ is not among the bytes"):
        StackReading.of_listing({stack.THE_OPCODE_SWITCH: body}).tables(stack.THE_OPCODE_SWITCH)


# ---- (9) THE DOOR'S SHAPES, each over a listing of its own -------------------------------------------------------------------
A_STACK_BEGINS, A_STACK_IS_LEFT, A_PRIVATE_TOP = "moveal %fp@(62),%sp", "moveal %a0@(70),%sp", "moveal #37958,%sp"
ENDS_ON_A_CALL = [(0x100, "moveal #1280,%a0"), (0x106, "jsr %a0@")]
NEVER_BACK = [(0x500, "linkw %fp,#-4"), (0x504, "jsr 600 <way_out>")]
WAY_OUT = [(0x600, "addal #12,%sp"), (0x606, A_STACK_IS_LEFT), (0x60a, "rte")]
DOOR_STARTS = {**STARTS, 0x500: "entry", 0x600: "way_out"}


def _door(entry=NEVER_BACK, **declared):
    return StackReading.of_listing({"caller": ENDS_ON_A_CALL, "entry": entry, "way_out": WAY_OUT, "leaf": A_LEAF}, DOOR_STARTS,
                                   **declared)


def test_a_body_may_end_on_a_call_of_a_routine_that_never_returns_and_of_no_other():
    """THE HANDLER'S `jsr (a0)` AND aes_entry's LAST CALL: A0 is loaded BY VALUE (`movea.l #<entry>,a0`), the callee
    links and never unlinks, its own last call is of a routine that LEAVES THE STACK FOR GOOD (declared) — none of
    the three returns (`returns`: READ, not declared), so nothing is walked past either call. A callee that can
    return is the old refusal: the path runs off the body."""
    read = _door(leaves_its_stack_at=(A_STACK_IS_LEFT,))
    assert read.of("caller").deepest == LONG_BYTES + 2 * LONG_BYTES + LONG_BYTES
    assert not (read.returns("caller") or read.returns("entry") or read.returns("way_out")) and read.returns("leaf")
    with pytest.raises(AssertionError, match="does not follow `moveal %a0@\\(70\\),%sp`"):
        _door().of("caller")
    with pytest.raises(AssertionError, match=r"caller: a path runs off the listed body's last instruction .* its callee \['entry'\] returns"):
        _door(entry=[(0x500, "rts")], leaves_its_stack_at=(A_STACK_IS_LEFT,)).of("caller")


def test_whether_a_routine_returns_is_read_off_its_paths():
    """`returns`: a return of its own; a jump to a routine that returns; a private stack left for the one it came on
    — and NOT the halt, a declared leaving, or a last call of a routine that does not."""
    halts = [(0x100, "tstw %d0"), (0x102, "trap #7")]
    jumps = [(0x100, "jmp 200 <leaf>")]
    assert not StackReading.of_listing({"caller": halts}).returns("caller")
    assert StackReading.of_listing({"caller": jumps, "leaf": A_LEAF}, STARTS).returns("caller")
    assert not StackReading.of_listing({"caller": [(0x100, "jmp 500 <halts>")], "halts": [(0x500, "trap #7")]}, {0x500: "halts"}).returns("caller")


def test_a_stack_that_begins_is_counted_from_what_is_declared_kept_there():
    """`movea.l 62(a6),sp` — THE PROCESS'S OWN STACK from here on: declared with the bytes below its top the machine
    keeps there, the count goes on from them (what was pushed before stood on another stack); undeclared, SP from
    the machine is refused as it always was."""
    body = [(0x100, "movel %d0,%sp@-"), (0x102, A_STACK_BEGINS), (0x106, "movel %d1,%sp@-"), (0x108, "jsr 300 <deep>"), (0x10e, "trap #7")]
    assert _read(body, begins_a_stack={A_STACK_BEGINS: 6}).deepest == 6 + LONG_BYTES + LONG_BYTES + 40
    _refused(body, "does not follow `moveal %fp@\\(62\\),%sp`")


def test_a_private_stack_is_begun_where_declared_and_left_for_the_one_it_came_on():
    """crit_err's shape: its caller's SP parked, A STACK OF ITS OWN begun by a declared instruction (the count from
    its top), its registers and a call there, then `movea.l <saved>,sp` — and the routine RETURNS (a glue's does
    too, by `rte`). The declaration is matched whoever listed the instruction: a blob's objdump (`8c42 <name>`) or
    the ROM's own decoding (`0x8c42`)."""
    for saved in ("8c42 <saved>", "0x8c42"):
        body = [(0x100, f"movel %sp,{saved}"), (0x106, A_PRIVATE_TOP), (0x10c, "moveml %d3-%d7/%a3-%fp,%sp@-"),
                (0x110, "jsr 300 <deep>"), (0x116, "moveml %sp@+,%d3-%d7/%a3-%fp"), (0x11a, f"moveal {saved},%sp"), (0x120, "rts")]
        read = StackReading.of_listing({"caller": body, "deep": DEEP}, STARTS, begins_a_stack={A_PRIVATE_TOP: 0})
        assert read.of("caller").deepest == 9 * LONG_BYTES + LONG_BYTES + 40 and read.returns("caller")
        assert read.depth_at("caller", 0x106) == 0
    _refused(body, "does not follow `moveal #37958,%sp`")
    by_address = StackReading.of_listing({"caller": _with(body, at_106="moveal 0x8c3a,%sp"), "deep": DEEP}, STARTS,
                                         begins_a_stack={"moveal 8c3a <aes_userdef_stack>,%sp": 0})
    assert by_address.of("caller").deepest == 9 * LONG_BYTES + LONG_BYTES + 40


def test_a_trap_of_the_os_is_charged_what_it_is_declared_to_take_and_refused_undeclared():
    """`trap #1` (GEMDOS) on a path: the OS's frames land under it. DECLARED with the bytes its handler takes, it is
    charged where it stands; undeclared it is the refusal it always was. (`trap #2` stays the VDI's, answered apart.)"""
    body = [(0x100, "subql #8,%sp"), (0x102, "trap #1"), (0x104, "addql #8,%sp"), (0x106, "rts")]
    assert _read(body, takes_an_exception={"trap #1": 50}).deepest == 8 + 50
    _refused(body, "caller takes `trap #1` at 0x102: the stack reading counts no frame of the OS under a trap other than `trap #2`")


# ---- THE DOOR AS THE ROM SPELLS IT, and what the reading is told about the trap path ------------------------------------------
THE_HANDLER_S_PUSHES = LONG_BYTES + 2 * aes.WORD_BYTES + LONG_BYTES     # the block, a zero word, the selector; its `jsr (a0)`
AES_ENTRY_S_FRAME = LONG_BYTES + LONG_BYTES                             # `link a6,#-4`
THE_THUNK_ADDS = LONG_BYTES + 2 * LONG_BYTES + LONG_BYTES               # aes_entry's `jsr`; the block and the image; its `jsr`
THE_DOOR_S_BYTES = stack.KEPT_UNDER_THE_TOP + THE_HANDLER_S_PUSHES + AES_ENTRY_S_FRAME + THE_THUNK_ADDS     # 6 + 12 + 8 + 16
THE_DOOR_S_PATH = (stack.THE_TRAP_HANDLER, stack.AES_ENTRY, stack.THE_MARSHAL_S_THUNK, stack.THE_MARSHAL)


def test_the_door_s_own_bytes_are_read_off_the_rom():
    """THE ROM'S OWN DOOR THROUGH THE READING'S DOOR SHAPES (`the_door_listed`: `$fe3eca..$fe3f3d` and aes_entry as
    `rom_data` decodes them): 42 bytes stand above the marshal — what the UDA keeps under the top, the handler's
    three pushes and its `jsr (a0)`, aes_entry's `link`, the thunk — and none of the three routines returns. THE
    REDS: without either declaration the ROM's door is refused by name."""
    assert stack.the_door_s_bytes() == (THE_DOOR_S_BYTES, THE_DOOR_S_PATH) and THE_DOOR_S_BYTES == 42
    functions, starts = stack.the_door_listed()
    assert f"moveal #{addrs.AES_ROM_ENTRY},%a0" in dict(functions[stack.THE_TRAP_HANDLER]).values(), "the by-value operand"
    door = StackReading.of_listing(functions, starts, begins_a_stack=stack.THE_DOOR_BEGINS, leaves_its_stack_at=(stack.THE_WAY_OUT_LEAVES,))
    assert not any(door.returns(routine) for routine in (stack.THE_TRAP_HANDLER, stack.AES_ENTRY, stack.THE_WAY_OUT))
    with pytest.raises(AssertionError, match="the stack reading does not follow `moveal %fp@\\(62\\),%sp`"):
        StackReading.of_listing(functions, starts, leaves_its_stack_at=(stack.THE_WAY_OUT_LEAVES,)).of(stack.THE_TRAP_HANDLER)
    with pytest.raises(AssertionError, match="does not follow `moveal %a0@\\(70\\),%sp`"):
        StackReading.of_listing(functions, starts, begins_a_stack=stack.THE_DOOR_BEGINS).of(stack.THE_TRAP_HANDLER)


def test_what_the_uda_keeps_at_a_trap_is_the_top_less_the_trap_s_frame_on_the_machine():
    """THE DECLARATION HELD TO THE MACHINE (`KEPT_UNDER_THE_TOP`): the ROM's accessory boot stopped at ITS FIRST
    ARRIVAL at the handler's AES arm — an accessory's first trap, the 68000's frame just pushed: the UDA of the
    process that runs keeps exactly the SP the trap came in on, and that is its stack's top less the frame."""
    boot = aes_boot.booted(aes_boot.accessory_preinit(), aes_boot.accessory_disk_of(aes_boot.QUIET, aes_boot.QUIET),
                           until=addrs.GEM_TRAP2_AES_ARM)
    running = case.long_in(boot.ram, aes.AES_RLR) & stack.BUS
    uda, taken_on = case.long_in(boot.ram, running + aes.PD_UDA) & stack.BUS, boot.registers["isp"]
    tops = {stack.THE_FIRST_ACCESSORY_S_PD: aes.AES_UDA2_STACK_TOP}
    assert case.long_in(boot.ram, uda + aes.UDA_SUPER_SP) & stack.BUS == taken_on
    assert taken_on + stack.KEPT_UNDER_THE_TOP == tops.get(running, uda + stack.ALLOCATED_STACK_TOP)


def test_the_two_stacks_a_trap_caller_runs_on_are_read_off_the_machine():
    assert stack.trap_callers_spans() == {stack.PD2: PD2_S_SPAN, stack.AN_ALLOCATED_PD: AN_ALLOCATED_SPAN}


def test_the_trap_path_s_reading_starts_at_the_handler_s_arm_the_moment_a_blob_links_it(blob, monkeypatch):
    """BY SYMBOL, as the screen manager's entry was: a blob that links `aes_rom_trap2` is read FROM ITS AES ARM —
    nothing allowed above, and THE LINKED DOOR STANDS WHERE THE ROM'S DOES above the marshal; until then, from the
    marshal under the ROM-read bytes."""
    read = stack.trap_bound(blob)
    if stack.links(blob.elf, stack.THE_TRAP_HANDLER):
        assert (read.entered_at, read.allowed) == ((stack.THE_AES_ARM,), 0)
        assert stack.trap_reading(blob.elf).deepest_to(stack.THE_AES_ARM, stack.THE_MARSHAL)[0] == THE_DOOR_S_BYTES
        assert not stack.trap_reading(blob.elf).returns(stack.THE_AES_ARM)
    else:
        assert (read.entered_at, read.allowed) == ((stack.THE_MARSHAL,), THE_DOOR_S_BYTES)
        assert read.chain[0] == read.trap_chain[0] == (stack.THE_DOOR, THE_DOOR_S_BYTES)
    monkeypatch.setattr(stack, "links", lambda elf, symbol: symbol == stack.THE_TRAP_HANDLER)
    assert stack.trap_entered_at("any blob") == (stack.THE_AES_ARM, 0)
    monkeypatch.setattr(stack, "links", lambda elf, symbol: False)
    assert stack.trap_entered_at("any blob") == (stack.THE_MARSHAL, THE_DOOR_S_BYTES)


_A_USE_OF_SH_FIND = re.compile(r"\baes_sh_find\(([^;{]*)")       # to the statement's end: a call's arguments, or the definition's
THE_DEFINITION_S = "uint32_t routine"
THE_SHELL_S_SHOW_ENTRY = "sh_show_entry"                # the Alcyon entry `src/aes/shell.c` hands sh_find
THE_SOURCES = Path(__file__).resolve().parents[1] / "src" / "aes"


def test_sh_find_is_read_for_each_caller_s_argument_the_shell_hands_it_a_routine_and_no_other_caller_does(blob):
    """THE DECLARATION (`NO_ROUTINE_IS_HANDED`, `TRAP_PATH_CALLS_WHAT_IT_IS_HANDED`): sh_find calls through its
    `routine` argument where it is not 0. UNTIL BAND 5 WAVE 4 every call of the build's handed SH_FIND_NO_ROUTINE;
    THE SHELL'S OWN CALL NOW HANDS sh_show (`src/aes/shell.c`: the ROM's `sh_find(command, #$feaddc)`) — held to the
    sources: one call that names a routine, every other the constant. So sh_find is READ ONCE FOR EACH ARGUMENT: on
    the trap path for "no routine" alone (shel_find's arm lays a ZERO in the slot — its `jsr (a0)` is counted, nothing
    under it), and on PD0's paths, where a blob links the shell, FOR sh_show's ENTRY, whose drawing is then under it.
    A call that shows neither a zero nor one routine by value is refused; undeclared, sh_find is refused by name."""
    uses = [use.group(1) for source in sorted(THE_SOURCES.glob("*.c")) for use in _A_USE_OF_SH_FIND.finditer(source.read_text())]
    calls = [use for use in uses if THE_DEFINITION_S not in use]
    hand_none = [call for call in calls if "SH_FIND_NO_ROUTINE)" in call]
    assert len(hand_none) >= 2 and len(uses) == len(calls) + 1, calls
    assert [call for call in calls if call not in hand_none] == [call for call in calls if "sh_show_routine())" in call], calls
    assert aes.header_constants("shell.h")["SH_FIND_NO_ROUTINE"] == 0
    handed_none = f"{stack.SH_FIND}{switch.HANDED}{switch.NO_ROUTINE_IS_HANDED}"
    trap_path = stack.trap_reading(blob.elf)
    assert {name for name in trap_path.read_as(stack.trap_entered_at(blob.elf)[0]) if name.startswith(stack.SH_FIND)} == {handed_none}
    assert trap_path.deepest_to(handed_none, switch.NO_ROUTINE_IS_HANDED) is not None, "its `jsr (a0)`, counted"
    if stack.links(blob.elf, stack.GEM_ENTRY) and len(calls) > len(hand_none):
        start_up = stack.start_up_reading(blob.elf)
        on_pd0 = {name for name in start_up.read_as(stack.pd0_entry(blob.elf)) if name.startswith(stack.SH_FIND)}
        assert on_pd0 == {f"{stack.SH_FIND}{switch.HANDED}{THE_SHELL_S_SHOW_ENTRY}"}
        assert start_up.of(*on_pd0).deepest > trap_path.of(handed_none).deepest, "sh_show's drawing is under the shell's call"
    undeclared = StackReading(blob.elf, stack.THROUGH_A_POINTER, leaves_the_stack=stack.LEAVES_THE_STACK,
                              calls_what_it_is_handed=stack.CALLS_WHAT_IT_IS_HANDED,
                              takes_an_exception={stack.GEMDOS_TRAP: stack.gemdos_need()})
    with pytest.raises(AssertionError, match="aes_sh_find calls through %a0 .* a pointer read out of memory"):
        undeclared.of(stack.SH_FIND)


HANDS_ONE = [(0x100, "pea %pc@(300 <deep>)"), (0x104, "jsr 600 <walks>"), (0x10a, "addql #4,%sp"), (0x10c, "rts")]
HANDS_NONE = [(0x100, "clrl %sp@-"), (0x102, "jsr 600 <walks>"), (0x108, "addql #4,%sp"), (0x10a, "rts")]
TAILS_WITH_NONE = [(0x100, "clrl %sp@(4)"), (0x104, "jmp 600 <walks>")]
CALLS_ITS_ARGUMENT = [(0x600, "moveal %sp@(4),%a0"), (0x604, "tstl %a0"), (0x606, "beqs 60a <walks+0xa>"), (0x608, "jsr %a0@"), (0x60a, "rts")]


@pytest.mark.parametrize("caller, under", ((HANDS_ONE, LONG_BYTES + LONG_BYTES + LONG_BYTES + 40), (HANDS_NONE, LONG_BYTES + LONG_BYTES + LONG_BYTES),
                                           (TAILS_WITH_NONE, LONG_BYTES)))
def test_a_routine_handed_none_by_one_caller_and_one_by_another_is_read_for_each(caller, under):
    """sh_find's shape, over a listing of its own: a routine that calls the argument it is handed where it is not 0,
    read FOR EACH CALLER — the routine one names by value (pc-relative too), or NO ROUTINE where the call lays a zero
    longword for it, pushed or stored in a tail call's slot. THE RED: a call that shows neither."""
    declared = {"through_a_pointer": {"walks": (switch.NO_ROUTINE_IS_HANDED,)}, "calls_what_it_is_handed": ("walks",)}
    functions = {"caller": caller, "walks": CALLS_ITS_ARGUMENT, "deep": DEEP}
    assert StackReading.of_listing(functions, {0x600: "walks", 0x300: "deep"}, **declared).of("caller").deepest == under
    from_a_register = [(0x100, "movel %d3,%sp@-"), *HANDS_NONE[1:]]
    with pytest.raises(AssertionError, match="caller hands its callee at 0x102 no routine by value"):
        StackReading.of_listing({**functions, "caller": from_a_register}, {0x600: "walks", 0x300: "deep"}, **declared).of("caller")


CALLS_ITS_SECOND_ARGUMENT = [(0x600, "subql #8,%sp"), (0x602, "moveal %sp@(16),%a0"), (0x606, "tstl %a0"), (0x608, "beqs 60c <walks+0xc>"),
                             (0x60a, "jsr %a0@"), (0x60c, "addql #8,%sp"), (0x60e, "rts")]


def test_no_routine_is_read_only_where_the_zero_is_the_argument_the_callee_calls_through():
    """WHICH ARGUMENT THE ZERO IS, READ ON BOTH SIDES (the second review's crafted listing, F9.1): `walks(routine, 0)`
    — the routine handed FROM A REGISTER, a zero longword laid for ANOTHER argument on the same straight line — was
    read as "no routine", and the routine's 44 bytes under the `jsr (a0)` went uncounted. RED: refused by name, a
    routine handed a way the reading does not read. And for a callee that calls through its SECOND argument (its
    slot read at the depth its own frame stands at): a zero pushed first — the second argument — is "no routine",
    pushed last — the first — is not; a tail call's zero is read by the slot it is stored in."""
    declared = {"through_a_pointer": {"walks": (switch.NO_ROUTINE_IS_HANDED,)}, "calls_what_it_is_handed": ("walks",)}
    starts = {0x600: "walks", 0x300: "deep"}
    the_review_s = [(0x100, "lea %pc@(300 <deep>),%a0"), (0x104, "clrl %sp@-"), (0x106, "movel %a0,%sp@-"), (0x108, "jsr 600 <walks>"),
                    (0x10e, "addql #8,%sp"), (0x110, "rts")]
    with pytest.raises(AssertionError, match="caller hands its callee at 0x108 no routine by value"):
        StackReading.of_listing({"caller": the_review_s, "walks": CALLS_ITS_ARGUMENT, "deep": DEEP}, starts, **declared).of("caller")
    functions = {"walks": CALLS_ITS_SECOND_ARGUMENT, "deep": DEEP}
    zero_second = [(0x100, "clrl %sp@-"), (0x102, "movel %d3,%sp@-"), (0x104, "jsr 600 <walks>"), (0x10a, "addql #8,%sp"), (0x10c, "rts")]
    read = StackReading.of_listing({**functions, "caller": zero_second}, starts, **declared)
    assert read.of("caller").path[1] == f"walks{switch.HANDED}{switch.NO_ROUTINE_IS_HANDED}"
    assert read.of("caller").deepest == 2 * LONG_BYTES + LONG_BYTES + 8 + LONG_BYTES, "its `jsr (a0)` counted, nothing under it"
    zero_first = [(0x100, "movel %d3,%sp@-"), (0x102, "clrl %sp@-"), *zero_second[2:]]
    with pytest.raises(AssertionError, match="caller hands its callee at 0x104 no routine by value"):
        StackReading.of_listing({**functions, "caller": zero_first}, starts, **declared).of("caller")
    tails = [(0x100, "subql #8,%sp"), (0x102, "clrl %sp@(16)"), (0x106, "addql #8,%sp"), (0x108, "jmp 600 <walks>")]
    assert StackReading.of_listing({**functions, "caller": tails}, starts, **declared).of("caller").path[1].endswith(switch.NO_ROUTINE_IS_HANDED)
    tails_the_first = [(0x100, "subql #8,%sp"), (0x102, "clrl %sp@(12)"), (0x106, "addql #8,%sp"), (0x108, "jmp 600 <walks>")]
    with pytest.raises(AssertionError, match="caller hands its callee at 0x108 no routine by value"):
        StackReading.of_listing({**functions, "caller": tails_the_first}, starts, **declared).of("caller")


THE_GEMDOS_ENTRY_PUSHES = 10 * LONG_BYTES + LONG_BYTES + aes.WORD_BYTES + LONG_BYTES     # D1-A2, the PC, the SR, the USP ($fc4fc4..)
THE_BELL_TAKES = stack.EXCEPTION_FRAME_BYTES
THE_BELL_S_ROUTINE = "aes_bell"


def test_the_os_s_traps_on_the_trap_path_are_gemdos_s_and_the_bell_s_each_measured(blob):
    """WHAT THE MACHINE'S OWN HANDLERS TAKE OF THEIR CALLER'S STACK, MEASURED: GEMDOS the fifty bytes its entry pushes
    before it leaves for its own stack — the same under two functions — and the BIOS, under the bell, no more than
    the 68000's frame. Undeclared, the build's first GEMDOS binding is refused by name; and THE ONLY `trap #13` on
    the trap path is the bell's own call (Bconout of a BEL), as the need measured is."""
    assert stack.gemdos_need() == THE_GEMDOS_ENTRY_PUSHES == 50 and stack.bell_need() == THE_BELL_TAKES
    undeclared = StackReading(blob.elf, stack.TRAP_PATH_POINTERS, leaves_the_stack=stack.LEAVES_THE_STACK,
                              calls_what_it_is_handed=stack.CALLS_WHAT_IT_IS_HANDED)
    with pytest.raises(AssertionError, match="aes_dos_sdta takes `trap #1` at 0x[0-9a-f]+: the stack reading counts no frame"):
        undeclared.of("aes_dos_sdta")
    read = stack.trap_reading(blob.elf)
    taken = collections.Counter()
    for name in read.functions_read(stack.trap_entered_at(blob.elf)[0]) & set(read.functions()):
        texts = [text for _at, text in read.functions()[name]]
        for index, text in enumerate(texts):
            if switch._A_TRAP.match(text) and text not in (switch.TRAP_2, switch.THE_HALT):
                taken[text] += 1
                assert text != stack.THE_BELL_S_TRAP or tuple(texts[index - 2:index + 1]) == stack.THE_BELL_AS_LISTED, name
    assert set(taken) == {stack.GEMDOS_TRAP, stack.THE_BELL_S_TRAP}, f"the OS's traps on the trap path: {dict(taken)}"
    # ...AND EACH IS CHARGED ITS OWN NEED WHERE IT STANDS: the bell's routine goes as deep as its pushes and the BIOS's
    # six bytes — not GEMDOS's fifty (no pin above would move: no bell stands at a deepest point).
    uncharged = StackReading(blob.elf, takes_an_exception={stack.THE_BELL_S_TRAP: 0}).of(THE_BELL_S_ROUTINE).deepest
    assert read.of(THE_BELL_S_ROUTINE).deepest == uncharged + THE_BELL_TAKES


# ---- THE FINDINGS OF THE TRAP PATH, PINNED (ruling W3-R8) ---------------------------------------------------------------------
# Numbers of OUR BUILD, as the screen manager's are: a pin that moves says which frame or which call, and is re-pinned
# with that reason. THE VERDICT: THE SHIPPED BLOB FITS PD2 — EVERY ARM OF THE SWITCH, BOUND AND MEASURED — SINCE THE
# DOOR DIET (band 5 wave 3, 2026-10-11), 20 bytes spare by the bound; the bench blob does not, and is reported.
#
# WHAT THE DOOR DIET CUT, each said where it is made, and WHAT IT WAS BEFORE (at 05bc5d6: slice S's findings, the
# gate's "does not fit" — kept as history):
#   * THE SWITCH'S FIVE DEEP ARMS ARE ROUTINES IT LEAVES TO BY A JUMP (`src/aes/gemsuper.c`, A_DEEP_ARM): fsel_input,
#     wind_open, wind_close, wind_set and the default's alert stood on the switch's own 36 bytes and their call's
#     12-16 + 4; they stand on a routine's 12-20. (`aes_dispatch 56` -> `aes_dispatch 0 > fsel_input 20`.)
#   * THE MARSHAL'S COPIES IN ARE A ROUTINE OF THEIR OWN (`copied_in`): the five registers the marshal saved for
#     them lay under the switch — 116 -> 100.
#   * ob_draw HOLDS everyobj's WALK AS ITS OWN BODY and calls just_draw as C calls (`src/aes/obdraw.c`): ob_draw 60 >
#     everyobj 86 > the Alcyon entry 24 -> ob_draw 88; the entry is gone from the build.
#   * gr_watchbox's WAIT IS A ROUTINE OF ITS OWN (`src/aes/grwait.c`): 100 -> 60.
#   * THIRTEEN MARKS (`include/stack_diet.h`; `test_stack_diet.py` pins what each buys): fs_input 116 -> 96, ob_edit
#     96 -> 64, curfld 72 -> 52, fm_button 104 -> 92, fm_alert 92 -> 88, fm_dial, wm_opcl 56 -> 36, wm_close, wm_set,
#     draw_change 104 -> 92, w_move 84 -> 72, w_clipdraw 68 -> 40, and the marshal's own.
# BEFORE: own frames 1,092 / 1,096 (the selector's edit field redrawn: fs_input 116 > fm_do 92 > ob_edit 96 >
# curfld 72 > ob_draw 60 > everyobj 86 > the entry 24 > just_draw 124 ...); the worst trap site an icon's blit at
# 1,002 on the shipped blob — with its need and the nest 1,574, OVER PD2 BY 178 — and a text at 972 on the bench
# blob, 1,744, over by 348; EIGHT arms of the shipped blob over PD2 (fsel_input 1,574, wind_open 1,570, the default
# 1,550, wind_set 1,542, wind_close 1,538, form_error 1,518, form_alert 1,494, form_do 1,402) and twelve of the
# bench blob's; a USERDEF's routine entered 952 down; crit_err 610 / 440 spare.
PD2_S_SPAN, AN_ALLOCATED_SPAN = 1396, 1788      # [uda + 74, $ae5a) and [uda + 74, uda + 1862): off the machine
# OUR OWN FRAMES, deepest, FROM THE MARSHAL DOWN (the door's 42 above them): a button of the file selector watched
# while it is held — under its form_do, fm_button and gr_watchbox, the object changed and redrawn: an icon's label
# measured for its justification. (The selector's edit field redrawn, the deepest before the diet, is 4 bytes above
# it now: fm_do 92 > ob_edit 64 > curfld 52 > ob_draw 88 against fm_do 88 > fm_button 92 > gr_watchbox 60 > ob_change 64.)
FROM_THE_MARSHAL = (("aes_marshal", 100), ("aes_dispatch", 0), ("fsel_input", 20), ("aes_fs_input", 96), ("aes_fm_do", 88),
                    ("aes_fm_button", 92), ("aes_gr_watchbox", 60), ("aes_ob_change", 64))
TO_THE_LABEL = (("aes_just_draw", 124), ("aes_gr_gicon", 72), ("aes_gr_gtext", 52), ("aes_gr_just", 48), ("aes_gsx_tcalc", 28))
TRAP_PATH_OWN_CHAIN = {BENCH: FROM_THE_MARSHAL + TO_THE_LABEL + (("aes_xstrpix", 8),),
                       SHIPPED: FROM_THE_MARSHAL + TO_THE_LABEL + (("aes_xstrpix", 12), ("aes_rom_xstrpix", 0))}
# ...and to the deepest trap: the same icon's fill under its label, vr_recfl (gr_rect holds bb_fill's body).
TO_THE_FILL = (("aes_just_draw", 124), ("aes_gr_gicon", 68), ("aes_gr_rect", 48), ("aes_vr_recfl", 28))
TRAP_PATH_TRAP_CHAIN = {BENCH: FROM_THE_MARSHAL + TO_THE_FILL + (("aes_gsx_ncode", 0), ("aes_gsx2", 0)),
                        SHIPPED: FROM_THE_MARSHAL + TO_THE_FILL + (("aes_gsx_ncode", 10), ("aes_rom_gsx_ncode", 0), ("aes_rom_gsx2", 0))}
TRAP_PATH_OWN_FRAMES = {BENCH: 894, SHIPPED: 898}               # 42 + 852 / 856
TRAP_PATH_DEEPEST_TRAP = {BENCH: 830, SHIPPED: 840}
# THE VERDICT, bytes SPARE (negative: OVER), the nest's 252 on top:
#   our own frames alone fit PD2 — 250 / 246 spare;
#   AT ITS TRAPS, call by call, the worst is fsel_input's: shipped — the icon's blit under the selector's watched
#   button (vrt_cpyfm at 804: 244 stored + the copy-raster's 76) = 1,376: FITS PD2, 20 SPARE, 412 spare of an
#   allocated PD; bench — its label's text (gsx_tblt at 774 + the C twin's 520) = 1,546: over by 150, 242 spare of
#   an allocated PD.
TRAP_PATH_OWN_SPARE_OF_PD2 = {BENCH: 250, SHIPPED: 246}
TRAP_PATH_WORST_SITE = {BENCH: ("aes_gsx_tblt", 774, (V_GTEXT,)), SHIPPED: ("aes_vrt_cpyfm", 804, (VRT_CPYFM,))}
TRAP_PATH_SPARE = {BENCH: {stack.PD2: -150, stack.AN_ALLOCATED_PD: 242}, SHIPPED: {stack.PD2: 20, stack.AN_ALLOCATED_PD: 412}}
THE_GATE_S_MARGIN = 20                  # W3-R8: the shipped blob's worst arm, its need and the nest, of PD2's 1,396
# BY THE CALL: the arms of the switch that do NOT fit PD2 with the nest, the deepest first — `(AES opcode, bytes)`,
# THE_DEFAULT_ARM for the 48 opcodes the ROM answers with its alert. ON THE SHIPPED BLOB: NONE. On the bench blob,
# under the C twin of the text blit, eight: fsel_input 90, form_error 53, the default's alert, wind_open 101,
# wind_set 105, form_alert 52, wind_close 102, form_do 50. EVERY CALL FITS AN ALLOCATED PD, on both.
THE_DEFAULT_ARM = "the default arm"
CALLS_OVER_PD2 = {
    BENCH: ((90, 1546), (53, 1542), (THE_DEFAULT_ARM, 1538), (101, 1534), (105, 1522), (52, 1518), (102, 1506), (50, 1430)),
    SHIPPED: ()}
# ...and THE SHIPPED BLOB'S SEVEN DEEPEST ARMS, `(AES opcode, bytes with the nest)`: what each has to spare of PD2 is
# 1,396 less it — 20, 24, 28, 32, 44, 48, 60; the next arm (form_do) has 136.
THE_SHIPPED_BLOB_S_DEEPEST_CALLS = ((90, 1376), (53, 1372), (THE_DEFAULT_ARM, 1368), (101, 1364), (105, 1352), (52, 1348), (102, 1336))
# WHAT EVERY AES CALL TAKES BESIDE ITS ARM (`stack.beside_the_switch`): the marshal's copies in, 174 / 180 down — no
# arm's own frames are charged less, and the shipped blob's appl_init, an arm of no depth (178), is measured there.
BESIDE_THE_SWITCH = {BENCH: 174, SHIPPED: 180}
TRAP_PATH_SITES_CHARGED_THE_WORST = {"aes_gsx_xline", "aes_ap_tplay"}
TRAP_PATH_USERDEF_CALL = 754            # a G_USERDEF watched in a form of an accessory's: PD2 leaves its routine 642, 390 with the nest
PD2_LEAVES_A_USERDEF_S_ROUTINE = PD2_S_SPAN - TRAP_PATH_USERDEF_CALL
# crit_err's own 2,048 bytes: 46 of the handler's above eralert (read off the ROM), the thunk's 16, eralert's paths, the nest.
CRIT_ERR_S_SPAN, CRIT_ERR_READ = 2048, stack.PrivateStack(0, 46, (stack.CRIT_ERR, stack.ERALERT), True)
CRIT_ERR_SPARE = {BENCH: 570, SHIPPED: 740}
UB_TRAMPOLINE_READ = stack.PrivateStack(0, 8, (stack.UB_TRAMPOLINE, stack.THE_DESK_S_DRAW_CODE), True)


def test_finding_the_trap_path_s_own_frames_by_chain(blob):
    """THE BOUND THROUGH THE SWITCH, PINNED BY CHAIN from the marshal down — the door's bytes above it are the ROM's
    (42, held apart) — on each blob: a frame that grows or is flattened reddens here by its name."""
    read, shore = stack.trap_bound(blob), stack.shore_of(blob)
    own, trapped = tuple(read.chain)[-len(TRAP_PATH_OWN_CHAIN[shore]):], tuple(read.trap_chain)[-len(TRAP_PATH_TRAP_CHAIN[shore]):]
    moved = [f"the chain to the deepest trap: {_moved(trapped, TRAP_PATH_TRAP_CHAIN[shore])}"] * (trapped != TRAP_PATH_TRAP_CHAIN[shore])
    moved += [f"the deepest chain of our own frames: {_moved(own, TRAP_PATH_OWN_CHAIN[shore])}"] * (own != TRAP_PATH_OWN_CHAIN[shore])
    assert not moved, f"{shore}: " + "; ".join(moved)
    assert (read.deepest, read.at_a_trap) == (TRAP_PATH_OWN_FRAMES[shore], TRAP_PATH_DEEPEST_TRAP[shore])
    assert sum(held for _function, held in read.chain) == read.deepest
    assert sum(held for _function, held in read.trap_chain) == read.at_a_trap
    assert sum(held for _function, held in tuple(read.chain)[:-len(TRAP_PATH_OWN_CHAIN[shore])]) == THE_DOOR_S_BYTES


def test_every_call_a_site_of_the_trap_path_can_make_is_measured_on_every_shore(blob):
    """NO NEED IS ASSUMED on the trap path either: every VDI opcode one of its sites can ask has a measured need
    through the ROM's VDI and through this blob's own (the two the screen manager's paths never ask among them);
    the sites that name none are charged the worst — pinned: which."""
    shore, sites = stack.shore_of(blob), stack.trap_path_sites(blob.elf)
    asked = {opcode for site in sites if site.opcodes for opcode in site.opcodes}
    assert {addrs.VDI_ROM_VEX_MOTV_OPCODE, addrs.VDI_ROM_VEX_CURV_OPCODE} <= asked <= set(stack.os_needs()) & set(stack.os_needs(shore))
    assert {site.function for site in sites if site.opcodes is None} == TRAP_PATH_SITES_CHARGED_THE_WORST
    assert max(site.depth for site in sites) == stack.trap_bound(blob).at_a_trap
    assert {(site.function, site.at) for site in stack.trap_sites(blob.elf)} <= {(site.function, site.at) for site in sites}, (
        "a trap site of the screen manager's is none of the trap path's: evnt_multi's arm reaches them all")


def test_finding_the_verdict_of_the_trap_path_the_shipped_blob_fits_pd2_and_the_bench_blob_s_figure_is_reported(blob):
    """THE VERDICT AGAINST W3-R8, AS NUMBERS, each blob's own VDI under its traps and the nest on top. OUR OWN FRAMES
    FIT PD2 (246 spare on the shipped blob). AT ITS TRAPS, each site charged its own call's need: THE SHIPPED BLOB —
    THE PROGRAM, AND THE GATE — FITS PD2's 1,396 WITH 20 TO SPARE, its worst an icon's blit under the file selector's
    watched button, and an allocated PD's 1,788 with 412; THE BENCH BLOB IS OVER PD2 BY 150 at the icon's label,
    under the C twin of a text blit no ROM ships (reported, not gated). A frame that grows or is flattened changes
    THIS PIN, by name."""
    shore, read = stack.shore_of(blob), stack.trap_bound(blob)
    assert PD2_S_SPAN - (read.deepest + stack.nest(shore)) == TRAP_PATH_OWN_SPARE_OF_PD2[shore]
    needed, at_a_trap, site = stack.trap_need(blob)
    spare = {which: span - needed for which, span in stack.trap_callers_spans().items()}
    assert at_a_trap and spare == TRAP_PATH_SPARE[shore], (
        f"{shore}: the trap path needs {needed} — {spare} spare, where the finding holds {TRAP_PATH_SPARE[shore]}: say "
        f"which frame or call moved, and re-pin")
    assert (site.function, site.depth, site.opcodes) == TRAP_PATH_WORST_SITE[shore]
    assert needed == site.depth + stack.needs_bounded(shore)[site.opcodes[0]] + THE_NEST


def test_the_gate_of_the_door_flip_is_the_shipped_blob_and_every_arm_of_it_fits_pd2():
    """THE GATE ON THE DOOR FLIP (ruling W3-R8): the SHIPPED blob's trap path, its own handlers and engines under
    its traps, FITS an accessory's stack in PD2 with the nest — EVERY ARM of the opcode switch, all 69, the deepest
    with 20 bytes to spare. IT DID NOT at 05bc5d6 (over by 178; the pin this one replaces said the day a frame diet
    brought the bound under 1,396 it would redden): THE REASON is the door diet's cuts, listed above the pins. The
    margin is pinned, and a frame that eats it reddens here before the stack is short."""
    shipped = stack.blob_of(SHIPPED)
    needed, _at_a_trap, _site = stack.trap_need(shipped)
    assert PD2_S_SPAN - needed == TRAP_PATH_SPARE[SHIPPED][stack.PD2] == THE_GATE_S_MARGIN > 0
    calls = stack.calls_of_the_switch(shipped.elf, SHIPPED)
    assert len(calls) == ITS_ARMS and all(max(call.own, call.at_a_trap) + stack.nest(SHIPPED) <= PD2_S_SPAN - THE_GATE_S_MARGIN
                                          for call in calls)
    deepest = tuple((call.opcodes[0] if len(call.opcodes) == 1 else THE_DEFAULT_ARM, max(call.own, call.at_a_trap) + THE_NEST)
                    for call in calls[:len(THE_SHIPPED_BLOB_S_DEEPEST_CALLS)])
    assert deepest == THE_SHIPPED_BLOB_S_DEEPEST_CALLS, f"the shipped blob's deepest arms moved — say which arm's frames: {deepest}"


def _over(calls, shore, span):
    return tuple((call.opcodes[0] if len(call.opcodes) == 1 else THE_DEFAULT_ARM, max(call.own, call.at_a_trap) + stack.nest(shore))
                 for call in calls if max(call.own, call.at_a_trap) + stack.nest(shore) > span)


def test_finding_the_trap_path_by_the_call_which_arms_fit_which_stack(blob):
    """BY THE CALL: every opcode of the table is in one arm; the deepest arm IS the bound; the arms OVER PD2 are
    pinned by opcode and bytes (NONE on the shipped blob; eight on the bench blob — the file selector, the window
    calls that redraw, the alerts, form_do); every arm fits an allocated PD; and NO ARM IS CHARGED LESS THAN WHAT
    EVERY CALL TAKES BESIDE THE SWITCH — the marshal's copies in."""
    shore, calls = stack.shore_of(blob), stack.calls_of_the_switch(blob.elf, stack.shore_of(blob))
    table, first = stack.the_switch_s_table(blob.elf)
    assert sorted(opcode for call in calls for opcode in call.opcodes) == list(range(first, first + table.words))
    assert len(calls) == ITS_ARMS and max(map(len, (call.opcodes for call in calls))) == OPCODES_OF_THE_DEFAULT_ARM
    assert max(call.own for call in calls) == stack.trap_bound(blob).deepest
    assert max(call.at_a_trap for call in calls) + stack.nest(shore) == stack.trap_need(blob)[0]
    assert _over(calls, shore, PD2_S_SPAN) == CALLS_OVER_PD2[shore], f"{shore}: the calls over PD2 moved — say which arm's frames"
    assert not _over(calls, shore, AN_ALLOCATED_SPAN)
    assert any(call.at_a_trap == 0 and call.site is None for call in calls), "an arm that takes no trap (appl_init)"
    beside = stack.beside_the_switch(stack.trap_reading(blob.elf), *stack.trap_entered_at(blob.elf))
    assert beside == BESIDE_THE_SWITCH[shore] <= min(call.own for call in calls)


def test_finding_what_an_application_s_routine_is_left_on_the_trap_path(blob):
    """A G_USERDEF DRAWN FROM AN ACCESSORY: the deepest any path of the listing enters its routine is 754 bytes down
    on both blobs (the object watched in a form under the file selector's arm) — PD2 leaves it 642, 390 with the
    nest (444 and 192 before the door diet). No reader bounds what it then takes: the finding is what it is left."""
    depth, path = stack.trap_userdef_call(blob)
    assert depth == TRAP_PATH_USERDEF_CALL and path[-2:] == ("aes_ob_user", stack.AN_APPLICATION_S_ROUTINE)
    left = PD2_S_SPAN - depth, PD2_S_SPAN - depth - stack.nest(stack.shore_of(blob))
    assert left == (PD2_LEAVES_A_USERDEF_S_ROUTINE, PD2_LEAVES_A_USERDEF_S_ROUTINE - THE_NEST)


def test_finding_crit_err_s_and_ub_trampoline_s_private_stacks(blob):
    """THE TWO PRIVATE STACKS, their shapes READ OFF THE ROM: crit_err moves with nothing pushed on its caller's
    stack, holds 46 bytes of its own above eralert and RETURNS; with the thunk, the C eralert's paths — each trap
    its call's need of OUR VDI — and the nest it fits its 2,048 bytes, 740 spare on the shipped blob. ub_trampoline
    holds 8 above the desk's draw code, on the 1,024 bytes the booted desk's own pointer names the end of — and what
    that code takes of them is the ROM's until band 6."""
    assert stack.crit_err_read() == CRIT_ERR_READ and stack.ub_trampoline_read() == UB_TRAMPOLINE_READ
    assert stack.CRIT_ERR_STACK[1] - stack.CRIT_ERR_STACK[0] == CRIT_ERR_S_SPAN
    crit_err = dict(stack.rom_listed(addrs.AES_ROM_CRIT_ERR, stack.CRIT_ERR_ROM_END, {})).values()
    assert stack.CRIT_ERR_S_STACK_BEGINS in crit_err and f"movel %sp,{stack.CRIT_ERR_SP_SAVE:#x}" in crit_err
    # ...AND THE BLOB'S OWN crit_err, the moment it links one, stands where the ROM's does: its bytes and its thunk's.
    assert stack.crit_err_entered(blob.elf) == CRIT_ERR_READ.above + stack.A_TWO_WORD_THUNK_ADDS
    if stack.links(blob.elf, stack.CRIT_ERR):
        assert stack.trap_reading(blob.elf).returns(stack.CRIT_ERR)
    needed, at_a_trap, _site = stack.crit_err_need(blob)
    assert at_a_trap and CRIT_ERR_S_SPAN - needed == CRIT_ERR_SPARE[stack.shore_of(blob)]
    lo, top = stack.userdef_stack()
    assert top - lo == stack.USERDEF_STACK_BYTES == 1024 and lo % 2 == 0


# ---- THE TRAP PATH, MEASURED BEHIND THE DOOR (ruling W3-R8: bound AND measured) ------------------------------------------------
# `(PD2, an allocated PD)`: the bytes of each accessory's own stack used from the door's takeover on — the ROM's own
# boot beside each blob's, ITS OWN VDI under its traps. The deepest call is wind_open: 962 under the ROM, 1,016 ON
# THE SHIPPED BLOB — 54 bytes from the ROM's own run (1,214, and 252 from it, before the door diet) — and 1,210 on
# the bench blob. EVERY RUN REACHES ITS IDLE NOW. Before the door diet the bench blob's wind_open OVERFLOWED PD2 IN
# THE RUN ITSELF, no interrupt needed (1,408 bytes under the C twin of the text blit, 12 more than PD2 has: the saved
# context under the stack written over, the machine through the ROM's reset): THAT OVERFLOW IS GONE — the same call
# takes 1,210 — and what is left of the finding is the bench blob's figure with the nest on top, over by 66,
# reported and not gated. (A run that reaches no idle is still kept with its reason, and held to it below: no run
# of today's builds makes one.)
THE_ROM_S, WIND_OPEN, EVNT_MESAG, APPL_INIT = stack.THE_ROM_S, 101, 23, 10
THE_SWITCH_S_OWN_FRAME_DOWN = 178       # the door's 42, the marshal's 100 and the switch's own 36: an arm that calls nothing
DOOR_MEASURED = {stack.QUIETLY: {THE_ROM_S: (328, 328), BENCH: (318, 318), SHIPPED: (318, 318)},
                 stack.WITH_WINDOWS: {THE_ROM_S: (962, 962), BENCH: (1210, 1210), SHIPPED: (1016, 1016)}}
NO_IDLE_REACHED = frozenset()
THE_DEEPEST_CALL = {stack.QUIETLY: EVNT_MESAG, stack.WITH_WINDOWS: WIND_OPEN}
WITH_THE_ROM_S_VDI_UNDER_OUR_DOOR = {BENCH: 980, SHIPPED: 984}          # the windows again, the machine's VDI left: ours is the rest
MEASURED_SPARE_OF_PD2, MEASURED_SPARE_OF_AN_ALLOCATED_PD, THE_ROM_S_RUN_SPARE_OF_PD2 = 128, 520, 182
THE_BENCH_BLOB_S_RUN_IS_OVER_PD2_BY = 66                                # 1,210 + 252: reported, not gated


THE_OVERFLOW_S_END = re.compile(r"did not reach an idle within \d+ instructions: it stands at 0x(?P<pc>[0-9a-f]+) and the machine never waits")


def held_to_the_overflow_s_end(modes, shore, refused):
    """A run that reached no idle, HELD TO WHY in its own words (`refused`): the one reason a pin of `NO_IDLE_REACHED`
    may stand for — its stores went through the bottom of PD2's stack, the machine through the ROM's reset, and it
    stands in the BIOS's text outside every dispatcher. Any other refusal is named as another."""
    ended = THE_OVERFLOW_S_END.search(refused)
    assert ended, f"{modes}, {shore} reached no idle for another reason: {refused}"
    assert addrs.ROM_BASE <= int(ended["pc"], 16) < addrs.VDI_ROM_ESCAPE, "it stands in the BIOS's own text, below every VDI routine"


@pytest.mark.parametrize("blob_name", BLOBS)
def test_the_rom_s_vdi_text_watched_behind_the_door_holds_every_handler_and_engine_a_blob_replaces(blob_name):
    """THE SPAN'S EXTENT (wave 3's review, SH: cut to the entry's first bytes, every test passed). "0 cycles in the
    ROM's VDI text" says our VDI ran only if that text is ALL of it: the entry, the dispatcher, and — what catches a
    table slot or a Line-A vector left the ROM's — every ROM handler and every ROM engine the blob's own replace."""
    spans = stack.THE_ROM_S_VDI_TEXT
    blob = stack.blob_of(blob_name)
    replaced = [handler.the_rom_s for handler in switch.our_vdi_handlers(blob).values()]
    replaced += [engine.the_rom_s for engine in switch.our_linea_engines(blob).values() if engine.entry is not None]
    assert len(replaced) > 70 and spans[0][0] == addrs.VDI_ROM_ENTRY and all(lo < hi for lo, hi in spans)
    outside = sorted({f"{at:#x}" for at in replaced if not any(lo <= at < hi for lo, hi in spans)})
    assert all(any(lo <= at < hi for at in replaced) for lo, hi in spans), "a span watched that holds nothing a blob replaces"
    assert not outside, f"ROM handlers or engines the blob replaces lie outside the span watched: {outside}"


@pytest.mark.parametrize("shore", (THE_ROM_S, *BLOBS))
@pytest.mark.parametrize("modes", stack.DOOR_MODES)
def test_finding_the_measured_runs_behind_the_door(modes, shore):
    """THE RUNS, PINNED: each accessory's deepest store, the call it was made under, and whether the machine reached
    its idle — every run does, the bench blob's windows too since the door diet (above)."""
    run = stack.measured_at_the_door(modes, shore)
    assert tuple(run.deepest.values()) == DOOR_MEASURED[modes][shore], f"{modes}, {shore}: say which frame or call moved"
    assert (run.idle is None) == ((modes, shore) in NO_IDLE_REACHED) == (run.refused is not None)
    # WHY no idle, in the run's own words (wave 3's review, SI: ANY refusal read as "no idle" — a wrong one too): the
    # machine stands in the BIOS's text, outside every dispatcher, having gone through the ROM's reset.
    if run.refused is not None:
        held_to_the_overflow_s_end(modes, shore, run.refused)
    # WHO RAN THE DOOR, as the takeover's own vet read it (SC: the vet's call was held by nothing): made wherever an
    # idle was reached behind a door, the ROM's text of each part zero cycles, our handler and our gotopgm entered.
    assert (run.door_ran is not None) == (shore != THE_ROM_S and run.idle is not None)
    if run.door_ran is not None:
        door_ran, critical_errors = dict(run.door_ran), stack.aes_event.CRITICAL_ERROR_VECTOR.what
        assert set(door_ran) == {part.what for part in stack.aes_event.THE_DOOR}, "the shipped door, every part (eight since band 6's binding)"
        assert door_ran.pop(critical_errors) == (0, 0), "no critical error in a boot: neither crit_err runs"
        # ...NOR the four parts the full flip added — no tick, no mouse packet, no cursor routine, no window item in a boot
        # (...and the binding's table: no routine — nothing is entered at it on either shore)
        for part in (*stack.aes_event.STORED_BY_GEM_ENTRY, stack.aes_event.GLUE_CODES, stack.aes_event.LINEF_TABLE_SLOT):
            assert door_ran.pop(part.what) == (0, 0), part.what
        assert len(door_ran) == 2 and all(ours > 0 and the_rom_s == 0 for ours, the_rom_s in door_ran.values())
    for which, used in run.deepest.items():
        assert run.by_call[which, THE_DEEPEST_CALL[modes]] == used == max(depth for (stack_, _call), depth in run.by_call.items()
                                                                           if stack_ == which)


def test_a_door_run_asks_the_profile_s_ledger_and_holds_it_for_its_own_run(monkeypatch):
    """THE MEASURED RUNS ARE DOOR BOOTS IN ALL BUT NAME (the narrow door flip's fix pass, A-5: `_door_run` switched the
    profile on with no word to the ledger): begun while a measurement holds the profile it is REFUSED BY NAME before
    it runs an instruction; made uncached with nobody holding it, it holds the profile by its own name for the
    length of its run — the ROM's shore as a blob's — and lets it go."""
    modes, shore = stack.QUIETLY, SHIPPED
    asked = (*stack.DOOR_MODES[modes], shore, stack._content_of(shore), True)
    with stack.aes_event.profile_held("a measurement of this test's"):
        with pytest.raises(AssertionError, match="A PROFILED RUN INSIDE ANOTHER: a door run of the stack battery's .* inside a measurement of this test's"):
            stack._door_run.derive(*asked)
    held, to_an_idle = [], aes_boot._Run.to_an_idle

    def watched(run, *entered):
        held.append(tuple(stack.aes_event.PROFILE_HELD_BY))
        return to_an_idle(run, *entered)
    monkeypatch.setattr(aes_boot._Run, "to_an_idle", watched)
    run = stack._door_run.derive(*asked)
    assert held[0] == (stack.PROFILE_HELD_BY_A_DOOR_RUN,) and not stack.aes_event.PROFILE_HELD_BY
    assert tuple(run.deepest.values()) == DOOR_MEASURED[modes][shore], "and it is the run the pins hold"


A_STAGED_REFUSAL = "STAGED BY THE TEST: the run is refused after its last stop, as a run that reaches no idle is"


def test_a_run_that_reaches_no_idle_is_kept_with_its_reason_and_its_depths(monkeypatch):
    """THE KEPT-REFUSAL ARM OF `_door_run`, which no run of today's builds reaches (the door diet's review, B-F3:
    made to raise instead of keeping, every test passed). A REFUSAL OF THE HARNESS, STAGED — NO MACHINE STATE: the
    quiet pair's whole run behind the shipped blob's door, made uncached, and `aes_boot._Run.to_an_idle` made to
    raise `aes_boot.Refused` where it would return, its idle forgotten. What a refused run must keep: the reason in
    its own words, no idle, no vet of a door no idle was reached behind — and the depths of what it stored until
    then, which here are the whole run's."""
    made_whole = aes_boot._Run.to_an_idle

    def refused_at_its_end(run, *entered):
        made_whole(run, *entered)
        run.idle = None
        monkeypatch.setattr(aes_boot._Run, "to_an_idle", made_whole)    # the door's run alone: the stacks are read off another boot
        raise aes_boot.Refused(A_STAGED_REFUSAL)

    monkeypatch.setattr(aes_boot._Run, "to_an_idle", refused_at_its_end)
    modes, shore = stack.QUIETLY, SHIPPED
    run = stack._door_run.derive(*stack.DOOR_MODES[modes], shore, stack._content_of(shore), True)
    assert (run.refused, run.idle, run.door_ran) == (A_STAGED_REFUSAL, None, None)
    assert tuple(run.deepest.values()) == DOOR_MEASURED[modes][shore]
    # ...WHAT THE MEASURED RUNS' TEST HOLDS A REFUSAL TO (its branch is reached by no run either): this reason is
    # named as another; the overflow's own words pass where the machine stands in the BIOS's text, and not elsewhere.
    with pytest.raises(AssertionError, match="reached no idle for another reason: STAGED BY THE TEST"):
        held_to_the_overflow_s_end(modes, shore, run.refused)
    the_overflow_s_words = "the run did not reach an idle within {} instructions: it stands at {:#x} and the machine never waits"
    held_to_the_overflow_s_end(modes, shore, the_overflow_s_words.format(aes_boot.BOOT_INSNS, addrs.ROM_BASE))
    with pytest.raises(AssertionError, match="it stands in the BIOS's own text"):
        held_to_the_overflow_s_end(modes, shore, the_overflow_s_words.format(aes_boot.BOOT_INSNS, addrs.VDI_ROM_ESCAPE))
    # ...and THE REPORT SAYS A REFUSED RUN IN ITS OWN REASON (it printed one fixed cause for every refusal)
    used = " / ".join(str(depth) for depth in DOOR_MEASURED[modes][shore])
    spans = stack.trap_callers_spans()
    assert stack._the_door_run_s_words(shore, run, spans) == f"{shore} {used} — NO IDLE REACHED: {A_STAGED_REFUSAL}"
    reached = stack._the_door_run_s_words(shore, stack.measured_at_the_door(modes, shore), spans)
    assert reached.startswith(f"{shore} {used} (+ nest {THE_NEST}: ") and "NO IDLE" not in reached


def test_the_report_says_less_left_than_under_the_rom_where_ours_is_entered_deeper(blob):
    """THE REPORT'S "less / more left than under the ROM" (B-F5: said the other way round, every test passed): a
    routine entered DEEPER is left LESS — and each blob's own line says what its measured USERDEF in a menu is."""
    assert stack._left_against_the_rom_s(UNDER_THE_ROM_S + 2, UNDER_THE_ROM_S) == "2 bytes less left than under the ROM"
    assert stack._left_against_the_rom_s(UNDER_THE_ROM_S - 2, UNDER_THE_ROM_S) == "2 bytes more left than under the ROM"
    ours_at = stack.measured(stack.THE_USERDEF, stack.shore_of(blob)).userdef_at
    assert stack._left_against_the_rom_s(ours_at, stack.measured(stack.THE_USERDEF).userdef_at) == (
        f"{MORE_LEFT_IN_A_MENU_THAN_UNDER_THE_ROM} bytes more left than under the ROM")


@pytest.mark.parametrize("modes", stack.DOOR_MODES)
def test_behind_the_door_our_own_vdi_ran_and_the_rom_s_did_not(modes):
    """WHO RAN, BY CYCLE PROFILE (ruling W3-R11) from the takeover on: on a blob's shore NOT ONE CYCLE in the ROM's
    VDI text — entry, dispatcher, handlers, engines — and the blob's own dispatcher ran; on the ROM's shore the
    reverse. (The door itself is the takeover's to vet: `aes_boot._TakingOver.made` refuses a cycle in the ROM's.)
    THE CONTROL: the same run with the machine's VDI left under our door runs the ROM's VDI and not ours — and is
    as much shallower as our handlers are deeper."""
    for shore in BLOBS:
        run, control = stack.measured_at_the_door(modes, shore), stack.measured_at_the_door(modes, shore, our_vdi=False)
        assert run.the_rom_s_vdi == 0 < run.ours_vdi, f"{shore}: {run.the_rom_s_vdi} cycles in the ROM's VDI under a door called ours"
        assert control.ours_vdi == 0 < control.the_rom_s_vdi and control.idle is not None
        if modes == stack.WITH_WINDOWS:
            assert max(control.deepest.values()) == WITH_THE_ROM_S_VDI_UNDER_OUR_DOOR[shore] < max(run.deepest.values())
    the_rom_s_own = stack.measured_at_the_door(modes)
    assert the_rom_s_own.ours_vdi == 0 < the_rom_s_own.the_rom_s_vdi


def test_behind_the_door_each_blob_draws_the_screen_the_rom_draws():
    """WHAT THE RUN IS WORTH AS A RUN OF OUR CODE: with its own door, switch and VDI each blob's boot leaves THE
    SAME SCREEN, byte for byte, as the ROM's — both windows drawn. (The bench blob's did not while its wind_open
    overflowed PD2: it reaches its idle since the door diet, and draws what the ROM draws.)"""
    for modes in stack.DOOR_MODES:
        for shore in BLOBS:
            assert stack.measured_at_the_door(modes, shore).screen == stack.measured_at_the_door(modes).screen, f"{modes}, {shore}"


def test_finding_the_verdict_of_the_measured_run_behind_the_door_it_fits_pd2_with_the_nest():
    """THE GATE'S MEASURED HALF (ruling W3-R8): the shipped blob's deepest run, a window opened from PD2, uses 1,016
    of its 1,396 bytes — WITH THE NEST'S 252 ON TOP, 128 SPARE (over by 70 before the door diet), where the ROM's own
    run has 182. An allocated PD holds the same run with 520 spare. THE BENCH BLOB'S same run, reported: over PD2 by
    66 with the nest — and inside it without, which it was not."""
    run, spans = stack.measured_at_the_door(stack.WITH_WINDOWS, SHIPPED), stack.trap_callers_spans()
    needed = {which: used + stack.nest(SHIPPED) for which, used in run.deepest.items()}
    assert spans[stack.PD2] - needed[stack.PD2] == MEASURED_SPARE_OF_PD2 > 0
    assert spans[stack.AN_ALLOCATED_PD] - needed[stack.AN_ALLOCATED_PD] == MEASURED_SPARE_OF_AN_ALLOCATED_PD
    the_rom_s = stack.measured_at_the_door(stack.WITH_WINDOWS).deepest[stack.PD2] + stack.nest()
    assert spans[stack.PD2] - the_rom_s == THE_ROM_S_RUN_SPARE_OF_PD2
    bench = stack.measured_at_the_door(stack.WITH_WINDOWS, BENCH)
    assert bench.deepest[stack.PD2] + stack.nest(BENCH) - spans[stack.PD2] == THE_BENCH_BLOB_S_RUN_IS_OVER_PD2_BY
    assert bench.idle is not None and bench.deepest[stack.PD2] < spans[stack.PD2]


def test_a_run_behind_the_door_is_never_deeper_than_its_call_s_bound(blob):
    """WHAT HOLDS THE READING TO THE TRUTH on the trap path: under every AES call an accessory made, on either stack
    and in either pair, the lowest store is no deeper than THAT CALL's arm of the bound (its own frames — the
    marshal's copies beside the switch among them: the shipped blob's appl_init stores 180 down, 2 below its arm's
    own 178 — or its worst trap site with this blob's own VDI's need under it)."""
    shore = stack.shore_of(blob)
    bound_of = {opcode: max(call.own, call.at_a_trap) for call in stack.calls_of_the_switch(blob.elf, shore) for opcode in call.opcodes}
    for modes in stack.DOOR_MODES:
        for (which, opcode), used in stack.measured_at_the_door(modes, shore).by_call.items():
            assert used <= bound_of[opcode], f"{shore}, {modes}: AES call {opcode} used {used} of {which}: its bound is {bound_of[opcode]}"
    quiet = stack.measured_at_the_door(stack.QUIETLY, shore)
    assert quiet.by_call[stack.PD2, APPL_INIT] == max(BESIDE_THE_SWITCH[shore], THE_SWITCH_S_OWN_FRAME_DOWN) == bound_of[APPL_INIT]


# ---- (10) THE START-UP'S SHAPES, each over a listing of its own (band 5 wave 4) ------------------------------------------------
A_FIRST_STACK, A_SECOND_STACK = "moveal #35214,%sp", "moveal %fp,%sp"
A_SUPER_CALL = ("movel %sp,%sp@-", "movew #32,%sp@-", "trap #1")
A_ROM_S_SP, THE_ROM_S_DEPTH_THERE, A_ROM_ROUTINE, THE_DESK = "moveal #41832,%sp", 58, 0xfe272e, "the desk"
SUPERS = [(0x100, A_FIRST_STACK), (0x106, "movel %sp,%sp@-"), (0x108, "movew #32,%sp@-"), (0x10c, "trap #1"),
          (0x10e, "addqw #6,%sp"), (0x110, "jsr 300 <deep>"), (0x116, "trap #7")]
SUPER_DECLARED = {"begins_a_stack": {A_FIRST_STACK: 6}, "takes_an_exception": {"trap #1": 50}}


def test_a_run_declared_to_end_where_it_began_leaves_sp_there_and_takes_what_it_is_declared_to():
    """`Super(sp)`: THE STACK POINTER GEMDOS LEAVES IS ITS ARGUMENT — the SP before the call's own two pushes — and
    its frame is built in their six bytes. Declared, the `addq.w #6` that follows it stands SP SIX ABOVE where the
    pushes began (the stack's top, where the first is declared to begin six under it) and the trap takes nothing;
    undeclared, it is any GEMDOS trap — 50 bytes under the pushes, and every depth after it six too deep. REFUSED: a
    branch that lands inside the run."""
    declared = StackReading.of_listing({"caller": SUPERS, "deep": DEEP}, STARTS, ends_where_it_began={A_SUPER_CALL: 0}, **SUPER_DECLARED)
    assert declared.depth_at("caller", 0x110) == 0 and declared.of("caller").deepest == max(6 + 6, LONG_BYTES + 40)
    undeclared = StackReading.of_listing({"caller": SUPERS, "deep": DEEP}, STARTS, **SUPER_DECLARED)
    assert undeclared.depth_at("caller", 0x110) == 6 and undeclared.of("caller").deepest == 6 + 6 + 50
    charged = StackReading.of_listing({"caller": SUPERS, "deep": DEEP}, STARTS, ends_where_it_began={A_SUPER_CALL: 70}, **SUPER_DECLARED)
    assert charged.of("caller").deepest == 6 + 6 + 70, "the bytes the run's last instruction is declared to take are charged there"
    joined = [(0xfe, "beqs 108 <caller+0xa>"), *SUPERS]
    with pytest.raises(AssertionError, match="caller: a branch lands at 0x108, inside the run .* declared to end where it began"):
        StackReading.of_listing({"caller": joined, "deep": DEEP}, STARTS, ends_where_it_began={A_SUPER_CALL: 0}, **SUPER_DECLARED).of("caller")


LOOPS = [(0x100, A_FIRST_STACK), (0x106, "subql #8,%sp"), (0x108, "jsr 300 <deep>"), (0x10e, "addql #8,%sp"),
         (0x110, "jsr 200 <leaf>"), (0x116, A_SECOND_STACK), (0x118, "movel %d0,%sp@-"), (0x11a, "jsr 300 <deep>"),
         (0x120, "addql #4,%sp"), (0x122, "bras 110 <caller+0x10>")]
TWO_STACKS = {A_FIRST_STACK: 0, A_SECOND_STACK: 0}


def test_a_routine_that_loads_its_own_stack_twice_is_read_on_each_and_never_returns():
    """gem_entry's shape: no caller, A STACK BEGUN (declared), then ANOTHER (`movea.l a6,sp`, declared), a `jsr` whose
    callee returns only to a `bra` back to the loop's top — reached at one depth on either stack, and the second
    stack's own instruction reached again from the stack it began. READ FROM THAT INSTRUCTION the paths are THE
    SECOND STACK'S ALONE. THE REDS: the second load UNDECLARED is, on a stack the routine began, what a glue's way
    back is — the stack it came on again: the routine is read as RETURNING and NOTHING AFTER IT IS WALKED (which is
    why `aes_stack` holds that the start-up's gem_entry never returns and reaches gem_main); with neither declared it
    is refused; and a loop that comes back deeper than it left is two paths at two depths."""
    read = StackReading.of_listing({"caller": LOOPS, "leaf": A_LEAF, "deep": DEEP}, STARTS, begins_a_stack=TWO_STACKS)
    assert read.of("caller").deepest == 8 + LONG_BYTES + 40 and not read.returns("caller")
    assert [at for _callee, _under, at in read.sites("caller")] == [0x108, 0x110, 0x11a]
    assert read.of("caller+0x16").deepest == LONG_BYTES + LONG_BYTES + 40, "the second stack: the first one's 8 are not on it"
    assert read.depth_at("caller+0x16", 0x110) == 0 and read.deepest_to("caller+0x16", "leaf") == (LONG_BYTES, ("leaf",))
    undeclared = StackReading.of_listing({"caller": LOOPS, "leaf": A_LEAF, "deep": DEEP}, STARTS, begins_a_stack={A_FIRST_STACK: 0})
    assert undeclared.returns("caller") and [at for _callee, _under, at in undeclared.sites("caller")] == [0x108, 0x110]
    with pytest.raises(AssertionError, match="does not follow `moveal #35214,%sp`"):
        StackReading.of_listing({"caller": LOOPS, "leaf": A_LEAF, "deep": DEEP}, STARTS).of("caller")
    deeper = _with(LOOPS, at_120="addql #2,%sp")
    with pytest.raises(AssertionError, match="caller: two paths reach 0x110 at depths 0 and 2"):
        StackReading.of_listing({"caller": deeper, "leaf": A_LEAF, "deep": DEEP}, STARTS, begins_a_stack=TWO_STACKS).of("caller")


@pytest.mark.parametrize("spelt", ("jsr 0xfe272e", "jsr fe272e <_end+0xfa1234>", "jsr fe272e"))
def test_a_call_out_of_the_build_is_declared_named_and_counted_as_its_call(spelt):
    """THE DESK DOOR's `jsr <an address of the ROM>`: no listing of the build holds it. DECLARED, it is its `jsr` and
    nothing under it, NAMED in the path — whatever symbol objdump prints near the address; undeclared, refused."""
    body = [(0x100, "subql #4,%sp"), (0x102, spelt), (0x108, "addql #4,%sp"), (0x10a, "rts")]
    read = StackReading.of_listing({"caller": body}, out_of_the_build={A_ROM_ROUTINE: THE_DESK})
    assert read.of("caller") == StackUse(LONG_BYTES + LONG_BYTES, ("caller", THE_DESK), None, ("caller",)) and read.returns("caller")
    assert read.deepest_to("caller", THE_DESK) == (LONG_BYTES + LONG_BYTES, (THE_DESK,))
    with pytest.raises(AssertionError, match="does not follow the transfer|has no listing of the instruction at 0xfe272e"):
        StackReading.of_listing({"caller": body}).of("caller")
    with pytest.raises(AssertionError, match="does not follow the transfer|has no listing of the instruction at 0xfe272e"):
        StackReading.of_listing({"caller": body}, out_of_the_build={A_ROM_ROUTINE + 2: THE_DESK}).of("caller")


THROUGH_THE_DOOR = [(0x100, "linkw %fp,#-8"), (0x104, "movel %sp,%d3"), (0x106, A_ROM_S_SP), (0x10c, "movel %a0,%sp@"),
                    (0x10e, "movew %d1,%sp@-"), (0x110, "jsr 0xfe272e"), (0x116, "moveal %d3,%sp"), (0x118, "jsr 300 <deep>"),
                    (0x11e, "unlk %fp"), (0x120, "rts")]
THE_CALLER_IS_ENTERED = 20              # bytes below the stack's top, its return address among them
DOOR_DECLARED = {"stands_sp_at": {A_ROM_S_SP: THE_ROM_S_DEPTH_THERE}, "out_of_the_build": {A_ROM_ROUTINE: THE_DESK},
                 "entered_at_depth": {"caller": THE_CALLER_IS_ENTERED}}


def test_the_desk_door_stands_sp_at_a_declared_place_for_one_call_and_puts_it_back():
    """THE PAD (ruling W4-R4): `movea.l #<the ROM's SP>,sp` — SP stood where the ROM's stands, ON THE SAME STACK — the
    ROM's frame laid there, the call, and `movea.l <the register that kept it>,sp`: the callee is entered where the
    declaration says, WHATEVER OUR OWN FRAMES ARE, and after the door the count goes on from where it stood (the
    routine returns; what follows is walked). THE PLACE IS THE STACK'S, so the reading is told where the function is
    entered; `depth_at` the standing instruction is where OUR frames stood, from the function's own entry: the pad
    is the declared depth less both. REFUSED: undeclared; a function not told of; and SP from a register where
    nothing stood it anywhere."""
    read = StackReading.of_listing({"caller": THROUGH_THE_DOOR, "deep": DEEP}, STARTS, **DOOR_DECLARED)
    the_desk_is_entered = THE_CALLER_IS_ENTERED + read.deepest_to("caller", THE_DESK)[0]
    assert the_desk_is_entered == THE_ROM_S_DEPTH_THERE + 2 + LONG_BYTES, "where the declaration says, from the stack's top"
    assert read.depth_at("caller", 0x106) == LONG_BYTES + 8 == read.depth_at("caller", 0x118), "our own frames, before and after"
    assert THE_ROM_S_DEPTH_THERE - (THE_CALLER_IS_ENTERED + read.depth_at("caller", 0x106)) == 26, "the pad"
    through_the_door, after_it = THE_ROM_S_DEPTH_THERE - THE_CALLER_IS_ENTERED + 2 + LONG_BYTES, LONG_BYTES + 8 + LONG_BYTES + 40
    assert read.of("caller").deepest == max(through_the_door, after_it) == after_it and read.returns("caller")
    assert read.deepest_to("caller", "deep") == (LONG_BYTES + 8 + LONG_BYTES, ("deep",))
    undeclared = {name: told for name, told in DOOR_DECLARED.items() if name != "stands_sp_at"}
    with pytest.raises(AssertionError, match="does not follow `moveal #41832,%sp`"):
        StackReading.of_listing({"caller": THROUGH_THE_DOOR, "deep": DEEP}, STARTS, **undeclared).of("caller")
    untold = {name: told for name, told in DOOR_DECLARED.items() if name != "entered_at_depth"}
    with pytest.raises(AssertionError, match="caller: `moveal #41832,%sp` at 0x106 stands SP at a declared place .* not told how far"):
        StackReading.of_listing({"caller": THROUGH_THE_DOOR, "deep": DEEP}, STARTS, **untold).of("caller")
    never_stood = [line for line in THROUGH_THE_DOOR if line[1] != A_ROM_S_SP]
    with pytest.raises(AssertionError, match="does not follow `moveal %d3,%sp`"):
        StackReading.of_listing({"caller": never_stood, "deep": DEEP}, STARTS, **DOOR_DECLARED).of("caller")


def test_the_door_s_way_back_is_read_from_the_register_that_kept_sp_and_from_no_other():
    """THE PUT-BACK NAMES ITS REGISTER (the second review's crafted listing, F9.2): the door keeps the SP it leaves in
    ONE register (`move.l sp,d3`, the nearest above the standing instruction), and only `movea.l d3,sp` is its way
    back. RED, each by name: SP "put back" from D4 — what stands in SP after it is whatever D4 held, and the reading
    took it for our own frames —, and a place stood at with no register keeping the SP it left."""
    from_another = [(at, "moveal %d4,%sp" if text == "moveal %d3,%sp" else text) for at, text in THROUGH_THE_DOOR]
    with pytest.raises(AssertionError, match="caller: `moveal %d4,%sp` at 0x116 puts SP back from a register that is not %d3"):
        StackReading.of_listing({"caller": from_another, "deep": DEEP}, STARTS, **DOOR_DECLARED).of("caller")
    nothing_kept = [line for line in THROUGH_THE_DOOR if line[1] != "movel %sp,%d3"]
    with pytest.raises(AssertionError, match="stands SP at a declared place and no `move.l sp,<register>` above it keeps"):
        StackReading.of_listing({"caller": nothing_kept, "deep": DEEP}, STARTS, **DOOR_DECLARED).of("caller")
    kept_in_an_address_register = [(at, {"movel %sp,%d3": "moveal %sp,%a3", "moveal %d3,%sp": "moveal %a3,%sp"}.get(text, text))
                                   for at, text in THROUGH_THE_DOOR]
    read = StackReading.of_listing({"caller": kept_in_an_address_register, "deep": DEEP}, STARTS, **DOOR_DECLARED)
    assert read.depth_at("caller", 0x118) == LONG_BYTES + 8, "the register is read, not assumed"


DOS_GLUE = [(0x500, "movel %sp@+,8c22 <a_place>"), (0x506, "trap #1"), (0x508, "movew %d0,c918 <another>"),
            (0x50e, "moveal 8c22 <a_place>,%a0"), (0x514, "jmp %a0@")]
ITS_CALLER = [(0x100, "movel #4849664,%sp@-"), (0x106, "bsrs 500 <glue>"), (0x108, "addql #4,%sp"), (0x10a, "rts")]


def test_a_routine_that_pops_its_return_address_and_jumps_through_it_is_read_as_returning():
    """`__DOS`: `move.l (sp)+,<place>` — its own return address parked — the trap, then `movea.l <place>,a0` /
    `jmp (a0)`: THE ROUTINE'S RETURN, and GEMDOS's own bytes stand under THE CALLER's frame (four bytes above the SP
    the glue was entered at). REFUSED, as a jump through a pointer of the machine always was: a register loaded from
    ANOTHER place, the pop not the routine's first instruction, the jump reached at another depth."""
    def read(glue):
        return StackReading.of_listing({"caller": ITS_CALLER, "glue": glue}, {0x500: "glue"}, takes_an_exception={"trap #1": 50})
    assert read(DOS_GLUE).of("caller").deepest == LONG_BYTES + LONG_BYTES + (50 - LONG_BYTES) and read(DOS_GLUE).returns("caller")
    assert read(DOS_GLUE).of("glue") == StackUse(50 - LONG_BYTES, ("glue",), None, ("glue",))
    for broken in (_with(DOS_GLUE, at_50e="moveal 8c26 <elsewhere>,%a0"), [(0x4fe, "nop"), *DOS_GLUE],
                   _with(DOS_GLUE, at_508="subql #2,%sp")):
        with pytest.raises(AssertionError, match="glue calls through %a0 at 0x514, which holds a pointer read out of memory"):
            read(broken).of("caller")


CUT_AT_ITS_RETURN_SITE = {"routine": [(0x100, "movel #4849664,%sp@-"), (0x106, "bsrs 500 <glue>")],
                          "its_return_site": [(0x108, "addql #4,%sp"), (0x10a, "rts")], "glue": DOS_GLUE}


def test_a_body_cut_at_the_label_of_its_own_return_site_is_read_on_through_it():
    """pgmld's shape on the shipped blob: the instruction after its `bsr` of the DOS glue carries a LABEL (the ROM parks
    that address), and the listing ends the routine's body at the call. The callee RETURNS and the label begins right
    behind the call: the body goes on through it, at the depth it stood at — where a label further off, or a last
    call of a routine that never returns, leaves the body ended as it was."""
    read = StackReading.of_listing(CUT_AT_ITS_RETURN_SITE, {0x500: "glue"}, takes_an_exception={"trap #1": 50})
    assert read.of("routine").deepest == LONG_BYTES + LONG_BYTES + (50 - LONG_BYTES) and read.returns("routine")
    assert [at for at, _text in read.functions()["routine"]] == [0x100, 0x106, 0x108, 0x10a]
    further = {**CUT_AT_ITS_RETURN_SITE, "its_return_site": [(0x110, "addql #4,%sp"), (0x112, "rts")]}
    with pytest.raises(AssertionError, match=r"routine: a path runs off the listed body's last instruction .* its callee \['glue'\] returns"):
        StackReading.of_listing(further, {0x500: "glue"}, takes_an_exception={"trap #1": 50}).of("routine")
    never_back = {**CUT_AT_ITS_RETURN_SITE, "glue": [(0x500, "trap #7")]}
    halted = StackReading.of_listing(never_back, {0x500: "glue"})
    assert halted.of("routine").deepest == LONG_BYTES + LONG_BYTES and not halted.returns("routine")


# ---- (11) THE START-UP AS THE ROM SPELLS IT: gem_entry's two stacks (band 5 wave 4; rulings W4-R4, W4-R9) ----------------------
THE_FIRST_STACK_S, PD0_S = (0x890e, 0x8994), (0x9ca2, 0xa3a2)                      # 134 and 1,792 bytes
THE_FIRST_STACK_S_SPAN, PD0_S_SPAN = THE_FIRST_STACK_S[1] - THE_FIRST_STACK_S[0], PD0_S[1] - PD0_S[0]
THE_USER_STACK_LOADED = 0x898e          # `$fd9ecc movea.l #$898e,sp`: six under the top the Super call and the `addq` leave
# WHERE THE ROM ENTERS EACH ROUTINE, in bytes below its stack's top (its return address among them) — READ, and held
# to the ROM's boot below. gem_main: gem_entry's `jsr`. Its callees: `link #-8` and three registers under it (28) —
# sh_main and the reader among them. sh_main's: `link #-10` and three (26) more — deskmain, a bare call; dos_exec
# under a word and a longword pushed; the cartridge's under one longword. sh_cmd's (`link #-2`, two registers: 14):
# the two file routines bare, the two disk routines under one longword.
A_RETURN = LONG_BYTES
GEM_MAIN_S_FRAME, SH_MAIN_S_FRAME, SH_CMD_S_FRAME = LONG_BYTES + 8 + 3 * LONG_BYTES, LONG_BYTES + 10 + 3 * LONG_BYTES, LONG_BYTES + 2 + 2 * LONG_BYTES
THE_ROM_ENTERS_GEM_MAIN = A_RETURN                                                  # 4
THE_ROM_ENTERS_SH_MAIN = THE_ROM_ENTERS_GEM_MAIN + GEM_MAIN_S_FRAME + A_RETURN      # 32
THE_ROM_S_SP_IN_SH_MAIN = THE_ROM_ENTERS_SH_MAIN + SH_MAIN_S_FRAME                  # 58: `$a368`
THE_ROM_ENTERS_DESKMAIN = THE_ROM_S_SP_IN_SH_MAIN + A_RETURN                        # 62: `$a364`
THE_ROM_ENTERS_SH_CMD = THE_ROM_ENTERS_DESKMAIN                                     # 62
THE_ROM_S_SP_IN_SH_CMD = THE_ROM_ENTERS_SH_CMD + SH_CMD_S_FRAME                     # 76: `$a356`
THE_ROM_ENTERS = {
    stack.THE_FIRST_STACK: {addrs.AES_ROM_ROM_RSC_INIT: A_RETURN, addrs.AES_ROM_SIZE_THEGLO: A_RETURN},
    stack.PD0_S_STACK: {stack.GEM_MAIN_ROM: THE_ROM_ENTERS_GEM_MAIN, stack.SH_MAIN_ROM: THE_ROM_ENTERS_SH_MAIN,
                        stack.SH_CMD_ROM: THE_ROM_ENTERS_SH_CMD, stack.DESKMAIN_ROM: THE_ROM_ENTERS_DESKMAIN,
                        stack.DOS_EXEC_ROM: THE_ROM_S_SP_IN_SH_MAIN + aes.WORD_BYTES + LONG_BYTES + A_RETURN,         # 68: `$a35e`
                        stack.CART_EXEC_ROM: THE_ROM_S_SP_IN_SH_MAIN + LONG_BYTES + A_RETURN,                        # 66
                        addrs.AES_ROM_DESK_SHOW_FILE: THE_ROM_S_SP_IN_SH_CMD + A_RETURN,                             # 80
                        addrs.AES_ROM_DESK_PRINT_FILE: THE_ROM_S_SP_IN_SH_CMD + A_RETURN,
                        addrs.AES_ROM_DESK_FORMAT: THE_ROM_S_SP_IN_SH_CMD + LONG_BYTES + A_RETURN,                   # 84
                        addrs.AES_ROM_DESK_COPY_DISK: THE_ROM_S_SP_IN_SH_CMD + LONG_BYTES + A_RETURN}}
THE_ROUTINES_ON_PD0_ARE = {stack.GEM_MAIN_ROM: 884, stack.SH_MAIN_ROM: 534, stack.SH_CMD_ROM: 196}     # bytes, to the return word's end


def test_gem_entry_s_two_stacks_are_read_off_the_rom_s_own_operands():
    """THE FIRST STACK: from the end of the words gem_entry lays under the address it loads (`$8904..$890d`) to that
    address AND THE SUPER CALL'S SIX — 134 bytes; PD0's: UDA0's, past its saved state, to UDA1 — 1,792. And what a
    reading is told of them: the first begins SIX UNDER ITS TOP (the bytes the ROM's `addq.w #6` drops that it never
    pushed there), the second at its top."""
    assert stack.gem_entry_s_stacks() == {stack.THE_FIRST_STACK: THE_FIRST_STACK_S, stack.PD0_S_STACK: PD0_S}
    assert stack.spans_of_the_start_up() == {stack.THE_FIRST_STACK: THE_FIRST_STACK_S_SPAN, stack.PD0_S_STACK: PD0_S_SPAN}
    assert (THE_FIRST_STACK_S_SPAN, PD0_S_SPAN) == (134, 1792) and PD0_S == (aes.AES_THEGLO + aes.UDA_STATE_BYTES, aes.AES_UDA1)
    assert stack.the_first_stack_begins() == {f"moveal #{THE_USER_STACK_LOADED},%sp": stack.SUPER_S_PUSHES}
    assert THE_USER_STACK_LOADED + stack.SUPER_S_PUSHES == THE_FIRST_STACK_S[1]
    assert aes.header_constants("gemstart.h")["GEM_FIRST_STACK"] == THE_USER_STACK_LOADED


def test_the_rom_s_start_up_is_read_through_the_start_up_s_shapes():
    """THE ROM'S OWN gem_entry, gem_main, sh_main AND sh_cmd THROUGH THE READING (`the_rom_s_start_up`: `rom_data`'s
    decoding, every Line-F word read for what it is): WHERE EACH ROUTINE IS ENTERED — the ROM-depth rule's figures —
    and gem_entry never returns. THE REDS: without the Super call's declaration every depth of the first stack is SIX
    TOO DEEP — and the loop's top, which the `bra` reaches at PD0's top, is two paths at two depths: refused by name;
    without the first stack's beginning the ROM's gem_entry is refused by name."""
    read, names = stack.the_rom_s_start_up()
    assert stack.the_rom_enters() == THE_ROM_ENTERS
    assert THE_ROM_ENTERS[stack.PD0_S_STACK][stack.DESKMAIN_ROM] == 62 and THE_ROM_ENTERS[stack.PD0_S_STACK][stack.DOS_EXEC_ROM] == 68
    assert not read.returns(stack.THE_ROM_S_GEM_ENTRY) and read.returns(names[stack.GEM_MAIN_ROM])
    assert stack.the_rom_s_sp_at_the_door() == {THE_ROM_S_SP_IN_SH_MAIN, THE_ROM_S_SP_IN_SH_CMD}
    assert stack.the_desk_door_stands() == {f"moveal #{PD0_S[1] - depth},%sp": depth for depth in (THE_ROM_S_SP_IN_SH_MAIN, THE_ROM_S_SP_IN_SH_CMD)}
    declared, functions = stack.start_up_declared(), read.functions()
    starts = {address: name for address, name in names.items()}
    with pytest.raises(AssertionError, match="gem_entry: two paths reach 0xfd9f72 at depths 6 and 0"):
        StackReading.of_listing(functions, starts, takes_an_exception={stack.GEMDOS_TRAP: stack.gemdos_need()},
                                begins_a_stack=declared["begins_a_stack"]).of(stack.THE_ROM_S_GEM_ENTRY)
    with pytest.raises(AssertionError, match="the stack reading does not follow `moveal #35214,%sp`"):
        StackReading.of_listing(functions, starts, takes_an_exception={stack.GEMDOS_TRAP: stack.gemdos_need()},
                                ends_where_it_began=declared["ends_where_it_began"]).of(stack.THE_ROM_S_GEM_ENTRY)


def test_the_routines_read_on_pd0_are_each_a_callee_of_the_one_before_and_end_at_their_one_return_word():
    """THE THREE ALCYON ROUTINES THE READING LISTS (declared by address): gem_main is gem_entry's last call, sh_main a
    call of gem_main's, sh_cmd of sh_main's, the reader of gem_main's — and each is read to its one Line-F return
    word: 884, 534 and 196 bytes. Every call out of band 5 is a call of sh_main's or sh_cmd's own."""
    read, names = stack.the_rom_s_start_up()
    called_by = {caller: {callee for callee, _under, _at in read.sites(names[caller])} for caller in (stack.GEM_ENTRY_ROM, *THE_ROUTINES_ON_PD0_ARE)}
    assert max(read.sites(stack.THE_ROM_S_GEM_ENTRY), key=lambda site: site[2])[0] == names[stack.GEM_MAIN_ROM]
    assert {names[stack.SH_MAIN_ROM], names[stack.THE_INF_READER_ROM]} <= called_by[stack.GEM_MAIN_ROM]
    assert {names[stack.SH_CMD_ROM], names[stack.DESKMAIN_ROM], names[stack.DOS_EXEC_ROM], names[stack.CART_EXEC_ROM]} <= called_by[stack.SH_MAIN_ROM]
    assert {names[utility] for utility in stack.THE_SHELL_S_UTILITIES_ROM} <= called_by[stack.SH_CMD_ROM]
    for routine, size in THE_ROUTINES_ON_PD0_ARE.items():
        body = read.functions()[names[routine]]
        assert body[-1] == (routine + size - 1, "rts") and body[-2] == (routine + size - aes.WORD_BYTES, switch.UNLINK), hex(routine)


THE_BIOS_STARTS_GEM_AT_MASK = 3         # the pre-init capture's status word, `$0300`: user state, levels 4-7 open
THE_ROM_S_FIRST_STACK_USE = 84          # its lowest store `$8940`, under rom_rsc_init's Malloc: 50 spare
THE_ROM_S_MSHRINK_REACHES = stack.SUPER_S_PUSHES + 12 + 50      # 68: the Mshrink frame and GEMDOS's own pushes — READ, and measured
THE_ROM_S_INIT, THE_ROM_S_DESK, THE_ROM_S_DESK_PARKS = 282, 886, 350    # PD0: gem_main to deskmain; the desk to its idle; UDA+62 there


@pytest.mark.parametrize("boot", stack.THE_BOOTS)
def test_the_rom_s_boot_enters_each_routine_where_the_reading_says(boot):
    """THE READING HELD TO THE MACHINE: the ROM's own boot (the blank disk; two accessories) arrives at rom_rsc_init
    and size_theglo four bytes under the first stack's top — `$8990`: the top IS the loaded address and six — at
    gem_main four under PD0's, at the reader and sh_main 32 under, AT deskmain 62 UNDER: `$a364`. In user state at
    the mask the BIOS leaves; and all of it the ROM's GEM text, no blob laid."""
    run, machine = stack.start_up_run(boot), stack.THE_BOOTS[boot]()[0]
    tops = dict.fromkeys(THE_ROM_ENTERS[stack.THE_FIRST_STACK], THE_FIRST_STACK_S[1])       # any other is on PD0's
    below = {**THE_ROM_ENTERS[stack.THE_FIRST_STACK], **THE_ROM_ENTERS[stack.PD0_S_STACK], stack.THE_INF_READER_ROM: THE_ROM_ENTERS_SH_MAIN}
    assert set(run.entered) == set(stack.WATCHED_IN_THE_ROM_S_BOOT)
    for address, sp in run.entered.items():
        assert tops.get(address, PD0_S[1]) - sp == below[address], f"{boot}: the ROM enters {address:#x} with SP {sp:#x}"
    assert run.entered[stack.DESKMAIN_ROM] == 0xa364 and run.entered[addrs.AES_ROM_ROM_RSC_INIT] == 0x8990
    assert list(run.entered)[-1] == stack.DESKMAIN_ROM and run.ours == 0 and run.the_rom_s > 0
    status = machine.registers["sr"]
    assert not status & aes_boot.SR_SUPERVISOR and (status & addrs.SR_IPL_MASK) >> aes_boot.SR_IPL_SHIFT == THE_BIOS_STARTS_GEM_AT_MASK


@pytest.mark.parametrize("boot", stack.THE_BOOTS)
def test_finding_the_rom_s_own_depths_on_gem_entry_s_two_stacks(boot):
    """THE ROM'S MEASURED DEPTHS, each a lowest STORE of its own boot — the same on both disks. THE FIRST STACK: 84 of
    134 used, 50 spare, the deepest under rom_rsc_init; before it, the Mshrink trap reaches 68 — WHAT THE READING
    SAYS OF THE ROM'S OWN INSTRUCTIONS (the frame's 12 and GEMDOS's 50, six under the top), so GEMDOS takes of a USER
    caller's stack what it takes of a supervisor's. PD0: 282 of 1,792 during init, 886 under the desk to its first
    idle, parked 350 deep there."""
    run = stack.start_up_run(boot)
    assert stack.deepest_in(run, stack.THE_FIRST_STACK) == THE_ROM_S_FIRST_STACK_USE == THE_FIRST_STACK_S_SPAN - 50
    assert stack.deepest_in(run, stack.THE_FIRST_STACK, None, addrs.AES_ROM_ROM_RSC_INIT) == THE_ROM_S_MSHRINK_REACHES == 68
    assert stack.deepest_in(run, stack.PD0_S_STACK, stack.GEM_MAIN_ROM, stack.DESKMAIN_ROM) == THE_ROM_S_INIT
    assert stack.deepest_in(run, stack.PD0_S_STACK, stack.DESKMAIN_ROM) == THE_ROM_S_DESK
    assert PD0_S[1] - run.parked == THE_ROM_S_DESK_PARKS


def test_the_word_gem_entry_stores_inside_its_first_stack_lies_under_the_next_return_address():
    """A FINDING OF THE ROM'S, by reading and held to its run: `$8992` — `move.w #1`, "a disk to read DESKTOP.INF
    from" — LIES INSIDE THE FIRST STACK, in the longword the stack's first push goes to. gem_entry stores it AFTER
    rom_rsc_init returns, and the very next `jsr` (size_theglo's) writes its return address over it: what the `#E`
    reader finds there when it tests it is THE LOW WORD OF THAT RETURN ADDRESS, `$9f78` in the ROM — non-zero, so the
    ROM reads the file. (Ours holds the low word of ITS OWN return address there: a blob's is held non-zero below.)"""
    read, names = stack.the_rom_s_start_up()
    (inside, size), = stack.stored_inside_the_first_stack().items()
    assert (inside, size) == (THE_FIRST_STACK_S[1] - aes.WORD_BYTES, aes.WORD_BYTES) == (0x8992, 2)
    body = read.functions()[stack.THE_ROM_S_GEM_ENTRY]
    stored_at = next(at for at, text in body if text == f"movew #1,{inside:#x}")
    calls = sorted(at for _callee, _under, at in read.sites(stack.THE_ROM_S_GEM_ENTRY))
    assert calls[0] < stored_at < calls[1], "after rom_rsc_init's return, before size_theglo's call"
    returns_to = next(after for (at, _text), (after, _next) in zip(body, body[1:]) if at == calls[1])
    for boot in stack.THE_BOOTS:
        assert stack.start_up_run(boot).at_the_reader == struct.pack(">I", returns_to), boot
    assert returns_to & aes.WORD_MASK == 0x9f78
    reader = stack.alcyon_routine_listed(stack.THE_INF_READER_ROM, {})
    assert any(text == f"tstw {inside:#x}" for _at, text in reader), "the reader tests the word"


def test_dos_exec_parks_an_application_s_stack_64_under_its_entry_two_bytes_inside_gemdos_s_own_frame():
    """dos_exec (`$fe3d46..`): the SP it is entered at LESS 64 becomes PD0's stack for the program's own `trap #2`s —
    with the ROM's frames, 132 below PD0's top: 1,660 bytes under it. AND A FINDING OF THE ROM'S, BY READING: under
    that same entry SP dos_exec pushes Pexec's 16 bytes and GEMDOS saves its caller's 50 — to 66. THE PARKED POINTER
    STANDS TWO BYTES INSIDE WHAT GEMDOS SAVED (the high word of the caller's USP, which the program's first AES call
    stores over). No machine launches a program: read, not run; reproduced by the pin of `gemdosif.S`, not mended."""
    entered = THE_ROM_ENTERS[stack.PD0_S_STACK][stack.DOS_EXEC_ROM]
    assert stack.dos_exec_parks_under() == 64 == aes.header_constants("gemdosif.h")["DOS_EXEC_STACK_KEPT"]
    assert stack.parked_for_an_application(entered) == (132, 1660)
    assert stack.PEXEC_S_FRAME_BYTES + stack.gemdos_need() == 66 and stack.parked_inside_gemdos_s_frame(entered) == 2


def test_finding_the_first_stack_holds_no_interrupt_s_nest_under_the_rom_either():
    """WHAT THE FIRST-STACK GATE DOES NOT CHARGE, said as the number it is: gem_entry runs at interrupt mask 3 — the
    horizontal blank shut out, the vertical blank and the MFP open — and a vertical blank with an MFP interrupt
    inside it needs 244 bytes (the BOOTED machine's handlers: measured there, not at the pre-init stop). The ROM's own
    84 and that nest are 328 of 134: the stack was never sized for an interrupt at its deepest point, and the words
    under it are what one would store over. Under the ROM as under us; the gate is the ROM's own exposure, not more."""
    assert stack.nest_on_the_first_stack() == THE_NEST - THE_HORIZONTAL_BLANK == 244
    assert THE_ROM_S_FIRST_STACK_USE + stack.nest_on_the_first_stack() - THE_FIRST_STACK_S_SPAN == 194
    for shore in BLOBS:
        assert stack.nest_on_the_first_stack(shore) == stack.nest(shore) - stack.hbl_need(shore) == 244


_A_USE_OF_THE_XBIOS_DOOR = re.compile(r"\baes_trp14\(([^;{]*)")


def test_the_one_xbios_call_on_pd0_s_paths_is_getrez_and_its_need_is_measured():
    """THE DECLARATION (`THE_XBIOS_TRAP`): the AES's XBIOS door takes whatever function its caller names, and every
    call of band 5's code names Getrez (held to the sources: sh_main's, after the desk) — under which the machine's
    XBIOS takes the 68000's frame of its caller's stack and no more, measured."""
    uses = [use.group(1) for source in sorted(THE_SOURCES.glob("*.c")) for use in _A_USE_OF_THE_XBIOS_DOOR.finditer(source.read_text())]
    calls = [use for use in uses if "uint16_t function" not in use]
    assert calls and len(uses) == len(calls) + 1 and all("XBIOS_GETREZ_FN)" in call for call in calls), uses
    assert stack.getrez_need() == stack.EXCEPTION_FRAME_BYTES


# ---- (12) A BLOB'S OWN START-UP: THE TWO GATES, BOUND AND MEASURED (rulings W4-R9, W4-R4) --------------------------------------
# Numbers of OUR BUILD, as the trap path's are: a pin that moves says which frame, and is re-pinned with that reason.
# THE FIRST STACK: gem_entry's `jsr` (4) > the thunk that hands rom_rsc_init the image (8) > rom_rsc_init (20) >
# dos_alloc (56: its own 6 and GEMDOS's 50 under the Malloc trap) = 88 of 134 — FOUR MORE THAN THE ROM'S 84, 46 SPARE.
THE_FIRST_STACK_CHAIN = ((stack.ON_THE_FIRST_STACK, 4), ("gemstart_to_aes_rom_rsc_init", 8), ("aes_rom_rsc_init", 20), ("aes_dos_alloc", 56))
THE_FIRST_STACK_BOUND, THE_FIRST_STACK_GATE_S_MARGIN = 88, 46
# PD0's OWN FRAMES, deepest: the shell's error alert after a launch that failed — a button of the alert watched while it
# is held (the trap path's own deepest chain from fm_do down) under gem_main 12 > sh_main 24 > the_command_is_found 20.
PD0_FROM_GEM_ENTRY = (("aes_rom_gem_main", 12), ("aes_sh_main", 24), ("the_command_is_found", 20), ("aes_fm_error", 24), ("aes_fm_alert", 88))
PD0_OWN_FRAMES = {BENCH: 808, SHIPPED: 812}             # + the nest's 252: 732 / 728 spare of 1,792
# (RE-PINNED BY BAND 6's BINDING, +4 each: rom_ram's desk arm keeps the desktop tree's address in a local of its own —
# the ROM's `-10(a6)` ini_tree answers into — in the frame its resource part's reading stands on.)
PD0_BEFORE_THE_SHELL = {BENCH: (304, "bring_gem_up"), SHIPPED: (308, "bring_gem_up")}
# MEASURED, the blob's own gem_entry run from the pre-init stop over the blank disk to deskmain's entry (the machine's
# VDI under its traps is THE ROM'S: the blob's own is linked under no vector there): PD0's lowest store during init.
OUR_INIT_MEASURED = {BENCH: 376, SHIPPED: 386}          # the ROM's own: 282
# THE DESK DOOR (ruling W4-R4): where OUR frames stand before each door stands SP at the ROM's — sh_main's two doors
# 32 down (the ROM's 58: pad 26), sh_cmd's four 52 down (the ROM's 76: pad 24) — and THE VET'S MARGIN, what is left
# above the lowest SP the door lets ours stand at (the ROM's SP less the argument slot its call sequence stores in):
# deskmain 26 (a bare call: no slot), dos_exec 22, each utility 20.
THE_DOORS = (("aes_sh_cmd", THE_ROM_S_SP_IN_SH_CMD, 52, 20),) * 4 + (("aes_sh_main", THE_ROM_S_SP_IN_SH_MAIN, 32, 26),
                                                                    ("aes_sh_main", THE_ROM_S_SP_IN_SH_MAIN, 32, 22))
# AN APPLICATION'S TRAP UNDER sh_main: parked 132 below PD0's top, 1,660 bytes under it; the trap path's bound from
# there (its need with the nest, less the six an accessory's UDA keeps under its own top): 1,540 / 1,370.
AN_APPLICATION_IS_LEFT, THE_TRAP_PATH_NEEDS_THERE = 1660, {BENCH: 1540, SHIPPED: 1370}
# THE VDI CALLS OF PD0's PATHS NO RUN MEASURES ON OUR OWN VDI — init's own (v_opnwk, the escapes, vsl_type, vsl_width,
# vst_alignment... by opcode): their trap sites are NOT BOUND at a trap, and say so.
INIT_S_OPCODES_NOT_MEASURED = {1, 5, 15, 16, 38, 110, 118, 125}


def test_the_start_up_is_read_the_moment_a_blob_links_it(blob, monkeypatch):
    """BY SYMBOL: a blob that links `aes_rom_gem_entry` is read ON ITS TWO STACKS — the first to the instruction at
    which PD0's begins, PD0's from there: gem_entry never returns, its loop's foot calls gem_main, gem_main calls the
    shell — and one that links none is refused by name, never read as nothing."""
    assert stack.links(blob.elf, stack.GEM_ENTRY), stack.NOT_LINKED.format(blob.elf)
    read = stack.start_up_reading(blob.elf)
    assert not read.returns(stack.GEM_ENTRY) and not read.returns(stack.pd0_entry(blob.elf))
    gem_main, under = stack.our_gem_main(blob.elf)
    assert under == THE_ROM_ENTERS_GEM_MAIN and stack.SH_MAIN in {callee for callee, _under, _at in read.sites(gem_main)}
    assert [under for _callee, under, _at in read.sites(stack.ON_THE_FIRST_STACK)] == [A_RETURN, A_RETURN], "its two callees, at the top"
    assert read.functions()[stack.ON_THE_FIRST_STACK][-1][1] == switch.THE_HALT
    monkeypatch.setattr(stack, "links", lambda elf, symbol: False)
    with pytest.raises(AssertionError, match="links no `aes_rom_gem_entry`: its start-up is not read"):
        stack.start_up_reading.__wrapped__("a blob that links none")


def test_finding_the_first_stack_gate_bound_and_measured(blob):
    """THE FIRST-STACK GATE (ruling W4-R9), BOUND AND MEASURED, on each blob: the build can take 88 of gem_entry's 134
    bytes — its `jsr`, the thunk, rom_rsc_init and dos_alloc down to GEMDOS's own pushes under the Malloc trap — and
    its own run from the pre-init stop TAKES 88: the bound, to the byte; 46 spare where the ROM has 50. WHO RAN: the
    blob (cycles in its span), and NOT ONE CYCLE of the ROM's GEM text; each callee is entered where the reading
    says. No `trap #2` is taken there; no interrupt is charged (the finding above)."""
    shore = stack.shore_of(blob)
    needed, chain = stack.first_stack_bound(blob)
    assert (needed, tuple(chain)) == (THE_FIRST_STACK_BOUND, THE_FIRST_STACK_CHAIN), f"{shore}: {_moved(tuple(chain), THE_FIRST_STACK_CHAIN)}"
    assert THE_FIRST_STACK_S_SPAN - needed == THE_FIRST_STACK_GATE_S_MARGIN and needed - THE_ROM_S_FIRST_STACK_USE == 4
    gem_main, _under = stack.our_gem_main(blob.elf)
    run = stack.our_start_up_run(shore, gem_main)
    assert stack.deepest_in(run, stack.THE_FIRST_STACK) == THE_FIRST_STACK_BOUND, "measured: the bound itself"
    assert run.ended == (blob.entry(gem_main), PD0_S[1] - THE_ROM_ENTERS_GEM_MAIN) and run.ours > 0 and run.the_rom_s == 0
    read = stack.start_up_reading(blob.elf)
    for callee, under, _at in read.sites(stack.ON_THE_FIRST_STACK):
        assert THE_FIRST_STACK_S[1] - run.entered[blob.entry(callee)] == under, callee


# ---- WHO RAN, HELD: a stand-in that runs the ROM's GEM text FROM A LAID IMAGE, twice --------------------------------------------
# A LABELLED STAND-IN, no blob: eighteen bytes laid where a blob is — three `jsr`s of a bare `rts` and nothing else —
# entered as a blob's gem_entry is. Two of the `rts` are GEM's own text (the first and the last such word of
# `aes.AES_TEXT`, found in the ROM's bytes), one lies just below it (above it the ROM holds no `rts` word at all:
# the Line-F table and the resources).
RTS_WORD, JSR_ABSOLUTE_LONG = 0x4e75, 0x4eb9
RTS_CYCLES, JSR_ABSOLUTE_LONG_CYCLES = 16, 20           # the 68000's own


def _rts_words(lo, hi):
    return [at for at in range(lo, hi, aes.WORD_BYTES) if case.word_in(BASE_IMAGE, at) == RTS_WORD]


def the_stand_in():
    """`(the image, the `rts` words it calls inside GEM's text, those outside)`: a `jsr` of each, in address order."""
    lo, hi = aes.AES_TEXT
    inside, below = _rts_words(lo, hi), _rts_words(emu.ROM_BASE, lo)[-1]
    assert not _rts_words(hi, emu.ROM_END), "an `rts` word above GEM's text: the stand-in would call it too"
    called = (below, inside[0], inside[-1])
    return b"".join(struct.pack(">HI", JSR_ABSOLUTE_LONG, at) for at in called), (inside[0], inside[-1]), (below,)


def test_who_ran_is_one_run_s_own_cycles_over_the_whole_of_gem_s_text_whatever_the_profile_held_before():
    """THE START-UP RUN'S "WHO RAN", HELD BY A RUN THAT KNOWS THE ANSWER (the second review's F5: the mutant that
    reads the profile without differencing it lived in four arrangements of five, and a ROM span narrowed to two
    bytes lived in all). A LABELLED STAND-IN laid where a blob is and entered as one runs three `rts` of the ROM —
    GEM's own FIRST and LAST, and the last one below its text:
      * ROM TEXT RUN FROM A LAID IMAGE READS > 0: exactly the two `rts` inside (the measured start-ups' "not one cycle
        of the ROM's GEM text" would see it), and the one outside is no cycle of GEM's — the span profiled is
        `aes.AES_TEXT`, gem_entry to the Line-F table, from end to end and no further;
      * `ours` is the image's own three `jsr`s (and what the run's first step costs there: not pinned);
      * AND THE SAME RUN MADE AGAIN IN THIS PROCESS ANSWERS THE SAME — the profile is never reset, so a run's cycles
        are a DIFFERENCE over that run alone: alone, in any order, under any `-n`."""
    image, inside, outside = the_stand_in()
    lo, hi = aes.AES_TEXT
    assert (lo, hi) == (addrs.AES_ROM_GEM_ENTRY, aes.AES_LINEF_TABLE) and lo <= inside[0] < inside[1] < hi
    assert outside[0] < lo
    machine, disk = stack.THE_BOOTS[stack.THE_BLANK_DISK]()
    base = stack.blob_of(SHIPPED).base
    laid = (base, image, base)
    runs = [stack._start_up_run.derive(machine, disk, (), base + len(image), laid) for _each in range(2)]
    for run in runs:
        assert run.ended[0] == base + len(image)
        assert run.the_rom_s == len(inside) * RTS_CYCLES, "GEM's own text, run from a laid image — and no `rts` outside it"
        assert run.ours >= len(inside + outside) * JSR_ABSOLUTE_LONG_CYCLES
    assert runs[0] == runs[1], "the second run's cycles are its own"
    # ...and THE ROM'S OWN BOOT made after them is still no cycle of a laid image's, and many of GEM's.
    the_rom_s = stack._start_up_run.derive(machine, disk, (), stack.GEM_MAIN_ROM, None)
    assert the_rom_s.ours == 0 < the_rom_s.the_rom_s and the_rom_s.ended[0] == stack.GEM_MAIN_ROM
    assert stack._start_up_run.derive(machine, disk, (), stack.GEM_MAIN_ROM, None).the_rom_s == the_rom_s.the_rom_s


def test_a_blob_laid_over_bytes_that_are_not_clear_is_refused():
    """THE LAID RUN'S PREMISE, its refusal RED: the span the image is laid in holds nothing at the pre-init stop — an
    image laid over the machine's own bytes (here the system variables) would run a start-up of neither shore."""
    machine, disk = stack.THE_BOOTS[stack.THE_BLANK_DISK]()
    image, _inside, _outside = the_stand_in()
    over = addrs.SYSVAR_FRCLOCK - len(image)
    assert any(machine.ram[over:over + len(image)]), "the premise: the machine's own bytes lie there"
    with pytest.raises(AssertionError, match="the span the blob is laid in is not clear at the pre-init stop"):
        stack._start_up_run.derive(machine, disk, (), over + len(image), (over, image, over))


def test_a_trap_2_on_the_first_stack_is_refused_by_the_gate_s_bound(monkeypatch):
    """THE FIRST-STACK BOUND'S REFUSAL, RED on a crafted listing: gem_entry's first stack holds 134 bytes and the
    bound charges no VDI under it — a build whose first stretch takes a `trap #2` is named, not bounded."""
    crafted = StackReading.of_listing({stack.ON_THE_FIRST_STACK: [(0x100, "subql #4,%sp"), (0x102, switch.TRAP_2), (0x104, switch.THE_HALT)]})
    monkeypatch.setattr(stack, "start_up_reading", lambda elf: crafted)
    with pytest.raises(AssertionError, match="the build takes a `trap #2` on gem_entry's first stack"):
        stack.first_stack_bound(stack.blob_of(SHIPPED))


def test_the_gate_of_the_first_stack_is_the_shipped_blob_and_it_fits():
    """THE GATE (W4-R9): our boot does not land unless the SHIPPED blob's gem_entry fits its first stack, bound and
    measured — it does, 46 bytes spare by both. The margin is pinned: a frame that eats it reddens here first."""
    shipped = stack.blob_of(SHIPPED)
    needed, _chain = stack.first_stack_bound(shipped)
    measured = stack.deepest_in(stack.our_start_up_run(SHIPPED, stack.our_gem_main(shipped.elf)[0]), stack.THE_FIRST_STACK)
    assert THE_FIRST_STACK_S_SPAN - max(needed, measured) == THE_FIRST_STACK_GATE_S_MARGIN > 0


def test_the_word_the_reader_tests_inside_the_first_stack_is_not_zero_on_a_blob(blob):
    """THE ROM'S QUIRK, ON OURS (the finding above): what the `#E` reader tests at `$8992` is the low word of OUR
    gem_entry's return address from size_theglo — a number of the blob's LAYOUT. Zero would say "no disk": the INF
    never read. Read off the listing, held non-zero, and held to the run: the four bytes under the first stack's top
    at our reader's arrival are that return address."""
    shore, word = stack.shore_of(blob), stack.the_word_the_reader_tests(blob)
    assert word != 0, f"{shore}: gem_entry's loop links where its return address ends in $0000 — the reader would open no DESKTOP.INF"
    at_the_reader = stack.our_start_up_run(shore, stack.DESKMAIN_ROM).at_the_reader
    assert struct.unpack(">I", at_the_reader)[0] & aes.WORD_MASK == word and blob.base <= struct.unpack(">I", at_the_reader)[0] < blob.base + len(blob.blob)


def test_finding_pd0_s_own_frames_from_gem_main_down(blob):
    """PD0's STACK, THE BUILD'S OWN FRAMES from gem_entry's `jsr gem_main` down — init, the shell's loop, what stands
    above the desk door — pinned by chain: the deepest is the shell's error alert after a failed launch, 808 / 812;
    with the nest's 252, 732 / 728 SPARE of 1,792. Before the shell is entered: 304 / 308 (the ROM's own init is
    measured at 282, its VDI's need under its traps among them). The desk's own frames are the ROM's: not counted."""
    shore, read = stack.shore_of(blob), stack.pd0_bound(blob)
    assert tuple(read.chain)[1:1 + len(PD0_FROM_GEM_ENTRY)] == PD0_FROM_GEM_ENTRY, f"{shore}: {_moved(tuple(read.chain)[1:6], PD0_FROM_GEM_ENTRY)}"
    assert read.chain[0] == (stack.pd0_entry(blob.elf), A_RETURN) and read.deepest == PD0_OWN_FRAMES[shore]
    assert sum(held for _function, held in read.chain) == read.deepest
    assert PD0_S_SPAN - read.deepest - stack.nest(shore) == PD0_S_SPAN - PD0_OWN_FRAMES[shore] - THE_NEST > 700
    assert stack.pd0_during_init(blob) == PD0_BEFORE_THE_SHELL[shore]


def test_the_rom_depth_rule_every_call_out_of_the_build_is_entered_where_the_rom_enters_it(blob):
    """THE ROM-DEPTH RULE (ruling W4-R4), READ OFF THE BLOB: deskmain, dos_exec and the shell's four utilities are each
    entered EXACTLY where the ROM enters them — 62, 68, 80, 80, 84, 84 bytes below PD0's top — because every one is
    made through a door that stands SP at the ROM's own (a place READ OFF THE ROM: a door that stood it anywhere else
    is an instruction the reading refuses). THE PAD IS NEVER NEGATIVE: our frames stand 26 and 24 bytes ABOVE the
    ROM's at the doors, and above the lowest SP each door's own vet allows by 26, 22 and 20. The cartridge's
    routine is on no path of the build (W4-R12)."""
    the_rom_s = THE_ROM_ENTERS[stack.PD0_S_STACK]
    entered = stack.entered_out_of_the_build(blob)
    assert entered == {address: the_rom_s[address] for address in (stack.DOS_EXEC_ROM, stack.DESKMAIN_ROM, *stack.THE_SHELL_S_UTILITIES_ROM)}
    assert stack.CART_EXEC_ROM not in entered
    doors = stack.desk_door_calls(blob)
    assert tuple((call.function, call.stands, call.ours, call.floor - call.ours) for call in doors) == THE_DOORS, doors
    assert all(call.stands - call.ours > 0 and call.floor - call.ours >= 0 for call in doors)


OUR_READER_IS_ENTERED = 72              # bytes below PD0's top, on either blob (`$a35a`)


def test_the_reader_is_entered_seventy_two_bytes_down_read_and_measured_where_the_rom_s_is_thirty_two(blob):
    """THE `#E` READER'S ENTRY DURING INIT, READ AND MEASURED: ours 72 bytes below PD0's top (`$a35a`), where the ROM's
    own boot enters its reader 32 down — PD0's image during init differs by nature (ruling W4-R4 constrains the calls
    OUT of the build, and the reader is none); the ledger says the two figures, and this is what holds them."""
    read, top = stack.start_up_reading(blob.elf), PD0_S[1]
    run = stack.our_start_up_run(stack.shore_of(blob), stack.DESKMAIN_ROM)
    assert read.deepest_to(stack.pd0_entry(blob.elf), stack.THE_INF_READER)[0] == OUR_READER_IS_ENTERED
    assert top - run.entered[blob.entry(stack.THE_INF_READER)] == OUR_READER_IS_ENTERED and top - OUR_READER_IS_ENTERED == 0xa35a
    assert {top - stack.start_up_run(boot).entered[stack.THE_INF_READER_ROM] for boot in stack.THE_BOOTS} == {32}


def test_the_rom_depth_rule_measured_our_own_boot_enters_deskmain_where_the_rom_s_does(blob):
    """...AND MEASURED: the blob laid at the pre-init stop and entered at its own gem_entry (a LABELLED STAGING, ruling
    W4-R1's; the blank disk) arrives AT deskmain's OWN ADDRESS WITH THE ROM'S STACK POINTER, `$a364` — and to there
    NOT ONE CYCLE of the ROM's GEM text ran ("ours booted" is claimed TO deskmain's ENTRY and no further: ruling
    W4-R3). PD0's lowest store on the way: 376 / 386 bytes down, where the ROM's own init stores 282 down — the
    machine's VDI under our traps there is the ROM's. Over a disk with an accessory the run is refused by name."""
    shore = stack.shore_of(blob)
    run = stack.our_start_up_run(shore, stack.DESKMAIN_ROM)
    assert run.ended == (stack.DESKMAIN_ROM, PD0_S[1] - THE_ROM_ENTERS_DESKMAIN) == (addrs.AES_ROM_DESKMAIN, 0xa364)
    assert run.the_rom_s == 0 and run.ours > 0
    gem_main = blob.entry(stack.our_gem_main(blob.elf)[0])
    assert run.entered[gem_main] == PD0_S[1] - THE_ROM_ENTERS_GEM_MAIN
    assert stack.deepest_in(run, stack.PD0_S_STACK, gem_main) == OUR_INIT_MEASURED[shore] > THE_ROM_S_INIT
    assert stack.deepest_in(run, stack.THE_FIRST_STACK) == THE_FIRST_STACK_BOUND
    with pytest.raises(AssertionError, match="run over the blank disk alone: over 'two quiet accessories' the loader's first Pexec"):
        stack.our_start_up_run.__wrapped__(shore, stack.DESKMAIN_ROM, stack.TWO_QUIET_ACCESSORIES)


# THE ONE SET OF FIGURES FOR THE SHELL'S DEPTH (the integration of wave 4's four slices; each said it its own way).
# From PD0's top: gem_entry's `jsr` 4, gem_main's frame 8 (one saved register and the image it hands the shell: the
# ROM's 24) — so sh_main's return address lies 16 down where the ROM's lies 32, `$a392` against `$a382`; sh_main
# then stands 32 down at its two doors and sh_cmd 52 at its four (THE_DOORS: the ROM's 58 / 76, pads 26 / 24, the
# vet's margins 26 / 22 / 20). "The budget" a build must keep is those margins: 20 bytes more above the shell — in
# gem_entry's call, gem_main's frame, sh_main's or sh_cmd's — and the utilities' doors halt.
THE_BUILD_ENTERS_SH_MAIN = 16


def test_the_shell_is_entered_sixteen_bytes_down_read_and_measured_where_the_rom_s_is_thirty_two(blob):
    """sh_main's ENTRY, READ AND MEASURED on each blob: the reading reaches it 16 bytes below PD0's top through
    gem_main alone, and the blob's own run from the pre-init stop (the LABELLED STAGING, ruling W4-R1's; the blank
    disk) arrives at it with the stack pointer `$a392` — not one cycle of the ROM's GEM text on the way. The ROM's
    sh_main is entered 32 down (`$a382`): the 16 between them, and what the shell's own frames leave of the ROM's, IS
    the doors' pad. A frame that grows on EITHER side of this entry — gem_main's above it, the shell's below —
    moves this figure or THE_DOORS (the rule's own test, above): each reddens for its own side."""
    shore, read = stack.shore_of(blob), stack.start_up_reading(blob.elf)
    gem_main, _under = stack.our_gem_main(blob.elf)
    assert read.deepest_to(stack.pd0_entry(blob.elf), stack.SH_MAIN) == (THE_BUILD_ENTERS_SH_MAIN, (gem_main, stack.SH_MAIN))
    run = stack.our_start_up_run(shore, stack.SH_MAIN)
    assert run.ended == (blob.entry(stack.SH_MAIN), PD0_S[1] - THE_BUILD_ENTERS_SH_MAIN) and run.ended[1] == 0xa392
    assert run.the_rom_s == 0 and run.ours > 0
    the_rom_s = THE_ROM_ENTERS[stack.PD0_S_STACK][addrs.AES_ROM_SH_MAIN]
    assert the_rom_s == 32 and PD0_S[1] - the_rom_s == 0xa382
    in_sh_main = {call.ours - THE_BUILD_ENTERS_SH_MAIN for call in stack.desk_door_calls(blob) if call.function == stack.SH_MAIN}
    assert in_sh_main == {16}, "what sh_main itself holds at its two doors: its return address is counted in the entry's 16"


def test_finding_an_application_s_trap_under_sh_main_fits_what_dos_exec_leaves_it(blob):
    """AN APPLICATION'S `trap #2` ON PD0's STACK: dos_exec, entered where the ROM enters it, parks the stack pointer
    132 below the top — 1,660 bytes under it — and the trap path's bound from there, its own VDI's need and the nest
    on top, is 1,370 on the shipped blob: 290 SPARE (the bench blob's 1,540: 120). No machine launches a program:
    the bound's alone."""
    shore = stack.shore_of(blob)
    parked, left, needed = stack.an_application_s_trap(blob)
    assert (parked, left) == (THE_ROM_ENTERS[stack.PD0_S_STACK][stack.DOS_EXEC_ROM] + 64, AN_APPLICATION_IS_LEFT)
    the_gate_s_bound = PD2_S_SPAN - TRAP_PATH_SPARE[shore][stack.PD2]       # what the trap path needs of an accessory's stack
    assert needed == THE_TRAP_PATH_NEEDS_THERE[shore] == the_gate_s_bound - stack.KEPT_UNDER_THE_TOP
    assert left - needed == {BENCH: 120, SHIPPED: 290}[shore] > 0


def test_finding_the_vdi_calls_of_init_are_measured_on_no_vdi_of_ours(blob):
    """WHAT PD0's BOUND DOES NOT HOLD, by name: of the VDI opcodes a trap site of PD0's paths can ask, eight are asked
    by init alone and NO RUN MEASURES WHAT OUR OWN VDI NEEDS UNDER THEM (`os_needs`: the scenarios are the screen
    manager's and the trap path's). So PD0's stack is bound in OUR OWN FRAMES and NOT at its traps; the deepest trap
    of its paths stands 744 / 754 down, 786 / 776 above the nest's foot."""
    shore, read = stack.shore_of(blob), stack.start_up_reading(blob.elf)
    sites = stack.trap_sites_under(read, stack.pd0_entry(blob.elf))
    asked = {opcode for site in sites if site.opcodes for opcode in site.opcodes}
    assert asked - set(stack.needs_bounded(shore)) == INIT_S_OPCODES_NOT_MEASURED
    assert max(site.depth for site in sites) == stack.pd0_bound(blob).at_a_trap == {BENCH: 744, SHIPPED: 754}[shore]
