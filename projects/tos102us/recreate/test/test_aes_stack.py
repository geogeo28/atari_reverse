"""THE SCREEN MANAGER'S STACK (`aes_stack.py`; ruling W2-R3 of AES band 5 wave 2) — and the stack reading's own
shapes (`aes_switch.StackReading`) that the screen manager's paths were the first to need.

WHAT IS HELD, on both blobs:
  * THE READING'S SHAPES, each over a listing of its own: what it FOLLOWS — a frame pointer's `link` / `unlk`, the
    build's halt, a routine that leaves the stack, a register reused as data on the way out, a function spilt to
    ONE slot of the frame, a routine read for the one routine its caller hands it, a branch into another routine's
    tail, a declared exception word — and, beside each, THE LISTING IN WHICH THE RULE FAILS, refused by name.
  * THE DECLARATIONS, held to the build: who hands everyobj which routine; that ob_user's pointer is the machine's;
    dsptch's cost and the Line-A trap's, each read or measured, never typed in.
  * THE FINDINGS, PINNED (W2-R3): our own frames by chain, the OS's need under a trap by VDI call (OUR VDI on our
    shore), the interrupts' nest, what an application's routine is left — and THE VERDICT AS A NUMBER, "over by N",
    for the bound and for each measured run. A FINDING IS ASSERTED, not expected to fail: any change either way —
    a frame flattened, a frame grown — reddens the pin that names it.
THE PINS ARE LAYOUT NUMBERS OF OUR BUILD (as band 4 pins its dispatcher's): a pin that moves is re-pinned WITH THE
REASON — which frame, which call — never to make a run green.
"""
import pytest

from recreate_kit import rom_bench

import aes
import aes_stack as stack
import aes_switch as switch

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
THE_WALKS = {("aes_ob_draw", "aes_just_draw_alcyon"), ("aes_draw_change", "aes_newrect_alcyon"),
             ("aes_newrect", "aes_mkrect_alcyon")}


def test_every_walk_is_handed_one_routine_by_value(blob):
    """everyobj's callers, over the whole blob: ob_draw hands just_draw, draw_change newrect, newrect mkrect — each
    named at the call, so every walk the build makes is read for the routine it is really handed."""
    assert stack.routines_handed_to(blob.elf, "aes_everyobj") == THE_WALKS


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
        unwalked.of("aes_ob_draw")
    unparked = StackReading(blob.elf, stack.THROUGH_A_POINTER, calls_what_it_is_handed=stack.CALLS_WHAT_IT_IS_HANDED,
                            takes_an_exception=line_a)
    with pytest.raises(AssertionError, match="aes_dsptch: .* leaves the function 6 bytes below"):
        unparked.of("aes_ev_block")
    assert "aes_mn_do" not in stack.THROUGH_A_POINTER and stack.reading(blob.elf).of("aes_mn_do").deepest > 0


def test_the_opcode_switch_is_refused_by_name_and_is_on_no_path_read(blob):
    """WAVE 3'S (ruling W2-R5): `aes_dispatch` is compiled as a jump table, which the reading REFUSES by name — and
    no path of the screen manager goes through it (a process that enters the AES by `trap #2` does)."""
    with pytest.raises(AssertionError, match="aes_dispatch: the stack reading does not follow the transfer `jmp %pc@"):
        StackReading(blob.elf, stack.THROUGH_A_POINTER).of(stack.THE_OPCODE_SWITCH)
    read = stack.reading(blob.elf)
    stack.bound(blob)
    assert stack.THE_OPCODE_SWITCH not in read.functions_read() and "aes_ev_multi" in read.functions_read()


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
        assert entries <= {stack.SCREEN_MANAGER_ENTRY}, f"the build hands pstart {entries}: a process entry nothing reads"
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
SPAN = 1196                             # [uda + 74, $a898): PD1's stack
BENCH, SHIPPED = BLOBS
# OUR OWN FRAMES, deepest: a slider dragged, a press waited for, bchange looking the window up (both blobs).
OWN_CHAIN = (("aes_rom_ctlmgr", 44), ("aes_hctl_button", 32), ("aes_hctl_window", 112), ("aes_gr_slidebox", 68),
             ("aes_gr_dragbox", 112), ("aes_gr_wait", 72), ("aes_gr_stilldn", 64), ("aes_ev_multi", 60), ("aes_forker", 60),
             ("aes_bchange_fork", 16), ("aes_bchange", 52), ("aes_mowner", 28), ("aes_wm_find", 28), ("aes_ob_find", 100),
             ("aes_ob_actxywh", 36), ("aes_ob_offset", 24))
# ...and to the deepest `trap #2`: an ICON drawn in a menu — its blit, vrt_cpyfm. The shipped blob's VDI bindings
# go through its generated glue (`aes_gsx_ncode`'s 10 bytes).
TO_THE_BLIT = (("aes_rom_ctlmgr", 44), ("aes_hctl_rect", 40), ("aes_mn_do", 144), ("aes_menu_down", 40), ("aes_ob_draw", 64),
               ("aes_everyobj<-aes_just_draw_alcyon", 94), ("aes_just_draw_alcyon", 24), ("aes_just_draw", 180),
               ("aes_gr_gicon", 68), ("gicon_blit", 76), ("aes_gsx_blt", 84), ("aes_vrt_cpyfm", 28))
TRAP_CHAIN = {BENCH: TO_THE_BLIT + (("aes_gsx_ncode", 0), ("aes_gsx2", 0)),
              SHIPPED: TO_THE_BLIT + (("aes_gsx_ncode", 10), ("aes_rom_gsx_ncode", 0), ("aes_rom_gsx2", 0))}
OWN_FRAMES, AT_THE_DEEPEST_TRAP = 908, {BENCH: 886, SHIPPED: 896}
# THE OS UNDER A `trap #2`, BY THE VDI'S OPCODE, through the ROM's VDI: the most is v_gtext's (8), not a blit's
# (109 vro_cpyfm, 121 vrt_cpyfm: 256) — and the keyboard poll's 130 that band 4 measures is vsm_string's (31).
THE_ROM_S_VDI_NEEDS = {6: 184, 8: 310, 12: 132, 22: 112, 23: 140, 24: 144, 25: 112, 31: 130, 32: 112, 33: 116, 109: 256,
                       111: 100, 113: 104, 114: 152, 121: 256, 122: 138, 123: 120, 128: 112, 129: 156}
OUR_VDI_GOES_DEEPER_BY = 32             # every call: our C dispatcher's frame under `vdi_rom_entry` (band 4 measured the same)
V_GTEXT, VRT_CPYFM = 8, 121
THE_NEST, THE_HORIZONTAL_BLANK = 252, 8           # hbl 8 + vbl 100 + the deeper MFP handler 144: the ROM's handlers' and ours
THE_LINE_A_TRAP_TAKES = 42
# WHAT AN APPLICATION'S ROUTINE STANDS UNDER (ob_user's `jsr (a0)`, a USERDEF in a menu): ours, both blobs — read off
# the listing and MEASURED the same to the byte — and the ROM's, measured.
AT_THE_USERDEF_CALL, UNDER_THE_ROM_S = 682, 472
# THE MEASURED RUNS from the real entry, the lowest store on PD1's stack: (the ROM's machine, ours on the bench
# blob, ours on the shipped blob) — our VDI under our traps.
MEASURED = {stack.THE_ELEVATOR: (628, 804, 814), stack.THE_TITLE: (548, 772, 782), stack.THE_CLOSER: (474, 616, 616),
            stack.THE_MENU: (722, 952, 956), stack.THE_ICON: (814, 1174, 1184), stack.THE_USERDEF: (722, 952, 956)}
UNTOUCHED_AT_MOST = 88                  # what a run's lowest SP can be below its lowest store, by the listing
# THE VERDICT, bytes OVER the 1,196 (negative: spare).
OVER_AT_THE_DEEPEST_TRAP = {BENCH: 284, SHIPPED: 294}       # the bound: 886 / 896 + our VDI's most (342) + the nest
OWN_FRAMES_SPARE = 36                                       # 1,196 - (908 + 252)


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
    """THE OS TERM, PINNED BY VDI CALL: through the ROM's VDI, and through OURS — the one our build runs under its
    own traps — which goes 32 bytes deeper under every call. The icon's blit (vrt_cpyfm) is among them: it is the
    call the bound's deepest chain ends on, and only the staged icon makes it."""
    assert stack.os_needs() == THE_ROM_S_VDI_NEEDS
    for shore in BLOBS:
        assert stack.os_needs(shore) == {opcode: need + OUR_VDI_GOES_DEEPER_BY for opcode, need in THE_ROM_S_VDI_NEEDS.items()}
        assert stack.under_a_trap(shore) == THE_ROM_S_VDI_NEEDS[V_GTEXT] + OUR_VDI_GOES_DEEPER_BY
    only_the_icon_s = {trap.opcode for trap in stack.traps_of(stack.THE_ICON)} - {trap.opcode for trap in stack.traps_of(stack.THE_MENU)}
    assert VRT_CPYFM in only_the_icon_s


def test_finding_the_nest_a_horizontal_blank_a_vertical_blank_inside_it_an_mfp_interrupt_inside_that():
    """THE NEST, PINNED: each handler's need measured on its own entry — the ROM's from its vectors, ours the build's
    — and equal. The horizontal blank's 8 bytes are charged: its handler raises nothing, so a vertical blank is
    taken inside it (`aes_stack`'s comment says why it cannot be ruled out)."""
    assert stack.hbl_need() == THE_HORIZONTAL_BLANK and stack.nest() == THE_NEST
    for shore in BLOBS:
        assert (stack.hbl_need(shore), stack.nest(shore)) == (THE_HORIZONTAL_BLANK, THE_NEST)
        assert stack.nest(shore) == THE_HORIZONTAL_BLANK + switch.worst_interrupt_need(switch.our_interrupt_needs(stack.blob_of(shore)))


def test_finding_the_dispatcher_s_slack_with_the_horizontal_blank_charged():
    """WHAT THE SAME EIGHT BYTES DO TO BAND 4'S FIGURE (reported, not edited there: `test_aes_evdisp_model.py` pins
    the dispatcher's 640-byte stack with a vertical blank and an MFP interrupt, 600 of 640): with a horizontal
    blank under them it is 608 of 640 — 32 spare, not 40. It still fits."""
    import test_aes_evdisp_model as dispatcher
    for directory in BLOBS.values():
        slack = dispatcher.THE_SLACK[rom_bench.RomBench(directory).elf.parent.name]
        assert slack - THE_HORIZONTAL_BLANK == 32 and slack - THE_HORIZONTAL_BLANK > 0


def test_finding_the_verdict_our_own_frames_fit_and_the_bound_at_its_deepest_trap_is_over(blob):
    """THE VERDICT AGAINST W2-R3, AS NUMBERS. Our own frames with the nest on top: inside the stack, 36 spare. At
    the deepest trap, with OUR VDI's most under it and the nest: OVER — by 284 bytes on the bench blob, 294 on the
    shipped one. The flip does not land over this; a frame-diet that changes it changes THIS PIN, by name."""
    shore, read = stack.shore_of(blob), stack.bound(blob)
    assert SPAN - (read.deepest + stack.nest(shore)) == OWN_FRAMES_SPARE
    needed, at_a_trap = stack.need(blob)
    assert at_a_trap and needed - SPAN == OVER_AT_THE_DEEPEST_TRAP[shore], (
        f"{shore}: the bound needs {needed} of {SPAN} — over by {needed - SPAN}, where the finding holds "
        f"{OVER_AT_THE_DEEPEST_TRAP[shore]}: say which frame or call moved, and re-pin")
    assert needed == read.at_a_trap + THE_ROM_S_VDI_NEEDS[V_GTEXT] + OUR_VDI_GOES_DEEPER_BY + THE_NEST


def test_finding_what_an_application_s_routine_is_left(blob):
    """A USERDEF'S DRAW ROUTINE RUNS ON THIS STACK, and no reading bounds it: so what is said of it is what it HAS.
    It is entered 682 bytes down (the listing's figure, and the measured one, to the byte); under the ROM, 472. An
    application's routine has 210 bytes less than under the ROM: 514 left, 262 with the interrupts' nest."""
    shore = stack.shore_of(blob)
    depth, path = stack.at_the_userdef_call(blob)
    assert depth == AT_THE_USERDEF_CALL and path[-2:] == ("aes_ob_user", stack.AN_APPLICATION_S_ROUTINE)
    assert stack.measured(stack.THE_USERDEF, shore).userdef_at == depth, "the listing's depth at the call is the run's"
    assert stack.measured(stack.THE_USERDEF).userdef_at == UNDER_THE_ROM_S
    assert (SPAN - depth, SPAN - depth - stack.nest(shore), depth - UNDER_THE_ROM_S) == (514, 262, 210)


@pytest.mark.parametrize("scenario", stack.SCENARIOS)
def test_finding_the_measured_runs_from_the_real_entry(scenario):
    """EACH SCENARIO, RUN: the ROM-booted machine and the two whose screen manager is ours (our VDI under their
    traps), continued by the same hand — the same handlers called — and the lowest byte of PD1's stack each stores."""
    runs = [stack.measured(scenario, shore) for shore in (stack.THE_ROM_S, *BLOBS)]
    assert tuple(run.deepest for run in runs) == MEASURED[scenario], f"{scenario}: say which frame or call moved"
    assert runs[0].observed == runs[1].observed == runs[2].observed


# THE MEASURED VERDICT: a run's lowest store + the nest, bytes over the stack (negative: spare) — bench, shipped.
# WITH NO INTERRUPT AT ALL the icon's run leaves 22 / 12 bytes of the 1,196.
MEASURED_OVER = {stack.THE_ELEVATOR: (-140, -130), stack.THE_TITLE: (-172, -162), stack.THE_CLOSER: (-328, -328),
                 stack.THE_MENU: (8, 12), stack.THE_ICON: (230, 240), stack.THE_USERDEF: (8, 12)}


@pytest.mark.parametrize("scenario", stack.SCENARIOS)
def test_finding_the_verdict_of_a_measured_run_with_the_nest_on_top(scenario):
    """...AND WHAT EACH IS BESIDE THE STACK with the nest on top. A FINDING: A MENU DROPPED — a routine action — IS
    OVER BY 8 / 12 BYTES, and the icon's by 230 / 240; the gadgets' runs fit. The ROM's own run fits every time.
    (A run's depth is its lowest STORE: SP itself may have stood up to `untouched_at_most` lower.)"""
    over = tuple(stack.measured(scenario, shore).deepest + stack.nest(shore) - SPAN for shore in BLOBS)
    assert over == MEASURED_OVER[scenario], f"{scenario}: over by {over} (bench, shipped) where the finding holds {MEASURED_OVER[scenario]}"
    assert stack.measured(scenario).deepest + stack.nest() <= SPAN, "the ROM's own run, its own handlers on top"


def test_a_measured_run_is_never_deeper_than_the_bound_and_the_icon_s_run_is_the_deepest_trap_s_chain(blob):
    """WHAT HOLDS THE READING TO THE TRUTH: no run is deeper than the listing's bound with our VDI's need under its
    trap — and the staged icon's run IS the bound's deepest trap chain, realised: its lowest store is that trap's
    depth and vrt_cpyfm's own need under it, to the byte."""
    shore, read = stack.shore_of(blob), stack.bound(blob)
    for scenario in stack.SCENARIOS:
        assert stack.measured(scenario, shore).deepest <= max(read.deepest, read.at_a_trap + stack.under_a_trap(shore))
    assert stack.measured(stack.THE_ICON, shore).deepest == read.at_a_trap + stack.os_needs(shore)[VRT_CPYFM]


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
