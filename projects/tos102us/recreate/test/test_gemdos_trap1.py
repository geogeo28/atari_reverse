"""The GEMDOS TRAP ENTRY @ $fc4f6e..$fc5091 — `src/gemdos/trap1.S`, and `Super` inside it.

    $fc4f6e  btst   #5,(sp)              ; the frame's SR: was the caller in supervisor mode?
    $fc4f76  cmpi.w #32,(a0)             ; ...and is this `Super`? — the two arms, per caller mode
    $fc4f8a  move.l a6,-(sp) / movea.l $87ce,a6    ; everything else: frame the process
    $fc4fb8  movea.l #$16ce,sp           ; ...and run the dispatcher on the OS's own stack
    $fc4fe0  jsr    $fc94e4

WHAT PROVES THE RECONSTRUCTION is not this file. `src/gemdos/trap1.S` is a byte-for-byte
transcription, and a transcription's differential is the SECOND DIFFERENTIAL of Tier 3's numerator:
the m68k assembly of that file, entered over the same staged frame as the ROM, required to leave the
same image, the same WHOLE register file and the same chip traffic
(`tools/recreate_kit/rom_bench.py`, `RomBench.measure_transcription`). It runs from
`test_the_m68k_transcription_equals_the_rom` below and again, with a cost attached, from
`test_tier3.py` over the same `gemdos.TRANSCRIPTIONS`.

WHAT IS IN THIS FILE is everything that is a claim about the ROM rather than about the copy: that
the hand-built frame really is a `trap #1`'s; where the calling process's registers go and what the
frame looks like; that the dispatcher runs on `$16ce`; that the caller gets EVERY register back,
which is the opposite of the BIOS entry's contract; and `Super`'s six arms, two of which carry
quirks a reconstruction would be tempted to tidy away.

THE BYTE PIN IS EXACT HERE, with nothing spliced. `src/bios/trap.S` needs three opcode words changed
because it reaches its dispatch tables PC-relatively; every external reference in this routine is
already absolute or immediate in the ROM, so the transcription assembles the ROM's own 292 bytes
wherever it is linked.
"""
import re

import pytest

from harness import BASE_IMAGE, addrs, diff_spans, differing_addresses, emu, make_image

import abi
import case
import gemdos
import trap
from opcodes import RTE
from recreate_kit.rom_bench import RomBench


@pytest.fixture(scope="module")
def bench():
    """The cross-compiled blob, loaded once per worker — `test_tier3.py`'s fixture, for its reason:
    a missing blob is a broken target build and must FAIL rather than skip."""
    return RomBench()


# Where a NULL DISPATCHER is staged, for the caller-cost measurement: a handler whose whole body is
# the `rte` that consumes the frame the caller built.
NULL_DISPATCHER_AT = gemdos.BUFFER_AT
RTE_INSNS, RTE_CYCLES = 1, 20
RESET_INSNS, RESET_CYCLES = 1, 40          # what the oracle charges before either entry runs

# A GEMDOS call that reaches the dispatcher, does nothing to the image and answers a constant — the
# shortest whole call there is, and therefore the one every structural claim below is made over.
SVERSION = addrs.GEMDOS_SVERSION_FN

# `Super`'s three arguments, as the ABI names them.
SUPER_TO_SUPERVISOR = 0                 # ...or back to user, depending on the caller's own mode
SUPER_QUERY = 1
SUPER_IS_SUPERVISOR = 0xFFFF_FFFF       # what the query answers a supervisor caller
SUPER_IS_USER = 0                       # ...and a user one


def run(pokes, entry=trap.CALLER_AT, regs=None, stop_pc=0):
    """One run of the ORIGINAL, entered at the caller the case staged."""
    return emu.run(make_image(pokes), entry, dict(regs or trap.ENTRY_REGS), stop_pc=stop_pc)


def call(selector, args=(), entry=addrs.GEMDOS_TRAP1, staged=None, stop_pc=0):
    """...and the ordinary shape of one: a supervisor caller, through the hand-built frame."""
    return run({trap.CALLER_AT: trap.caller(selector, args),
                abi.FIRST_ARG: trap.longword(entry), **(staged or {})}, stop_pc=stop_pc)


# ---- the case shape's own proof ------------------------------------------------------------------

def test_the_hand_built_frame_is_the_one_a_real_trap_1_builds():
    """THE CASE SHAPE'S OWN PROOF, and every other claim in this file rests on it.

    The cases stage a caller that builds the exception frame by hand and enters the entry through
    it, because a real `trap #1` reaches the machine's own vector table and could therefore only run
    the ROM's. So the hand-built frame has to be shown to be the same frame: the same call through a
    caller that TRAPS, and the two runs required indistinguishable in the register file and in every
    byte outside the run's own stack band.

    They differ in one thing and it is the one they must — the RETURN PC the entry saved, which is
    each caller's own address. It lives in the process frame on the caller's stack here rather than
    in a system save area, so the span is computed from where the entry left the frame.
    """
    hand = {trap.CALLER_AT: trap.caller(SVERSION),
            abi.FIRST_ARG: trap.longword(addrs.GEMDOS_TRAP1)}
    real = {trap.TRAP_CALLER_AT: gemdos.trap_caller(SVERSION)}
    hand_final, _writes, hand_regs = run(hand)
    real_final, _writes, real_regs = run(real, entry=trap.TRAP_CALLER_AT)

    assert {name: hand_regs[name] for name in emu.REPORTED_REGS} == \
           {name: real_regs[name] for name in emu.REPORTED_REGS}

    stubs = set(range(trap.CALLER_AT, trap.CALLER_AT + len(hand[trap.CALLER_AT]))) | \
        set(range(trap.TRAP_CALLER_AT,
                  trap.TRAP_CALLER_AT + len(real[trap.TRAP_CALLER_AT])))
    differing = set(differing_addresses(memoryview(hand_final), memoryview(real_final),
                                        diff_spans(), stubs.__contains__))
    assert not differing, (
        f"a hand-built frame and a real `trap #1` left different memory at "
        f"{sorted(hex(at) for at in differing)} — the staged caller is not entering the entry the "
        f"way the processor does")


# ---- the process frame ---------------------------------------------------------------------------

def test_the_entry_frames_the_process_in_its_own_basepage():
    """WHERE A GEMDOS CALL'S REGISTERS GO, and it is not where a BIOS call's go.

    The BIOS dispatcher frames the caller in the OS's shared save area at `savptr`. GEMDOS frames it
    in the RUNNING PROCESS'S BASEPAGE — D0/A3-A5 at +$68, A6 at +$78 and a pointer at +$7c to the
    rest, which is on the caller's own stack. The reason is `Pterm`: a GEMDOS call is the one a
    process can be destroyed inside of, so the state it is abandoned in has to belong to it.
    """
    final, writes, _regs = call(SVERSION)
    saved = [case.long_in(final, gemdos.BASEPAGE + addrs.BASEPAGE_SAVED_D0 + 4 * index)
             for index in range(addrs.BASEPAGE_SAVED_REGISTERS)]
    # D0 is the one slot that does NOT come back holding what the caller had: the epilogue writes
    # the dispatcher's RESULT there, because that is the slot the closing `movem` restores D0 from.
    assert saved[0] == addrs.GEMDOS_VERSION
    assert saved[1:] == [trap.ENTRY_REGS[name] for name in ("a3", "a4", "a5", "a6")]
    assert gemdos.BASEPAGE + addrs.BASEPAGE_SAVED_FRAME in writes, \
        "the entry did not record where it put the rest of the frame"


def test_the_rest_of_the_frame_is_on_the_callers_own_stack():
    """...and the other half, at the pointer the basepage holds: the OTHER stack pointer, the SR,
    the return PC, and then D1-D7/A0-A2. Fifty bytes, which is also the displacement back up to the
    caller's own words — `lea 50(a5),a0` is how the entry finds the argument list.

    READ WHILE THE FRAME IS LIVE, at the dispatcher's own first instruction. By the time the call
    has returned the epilogue has rebuilt the `rte`'s exception frame ON TOP of it — the SR lands in
    A1's low word and the PC over A2 — so the finished image holds a frame with two registers
    scribbled on, which is correct and is not what this case is about.
    """
    final, _writes, _regs = call(SVERSION, stop_pc=addrs.GEMDOS_DISPATCH)
    frame = case.long_in(final, gemdos.BASEPAGE + addrs.BASEPAGE_SAVED_FRAME)
    assert frame < emu.STACK_TOP, "a supervisor caller's frame is not on the supervisor stack"
    assert case.word_in(final, frame + 4) & (1 << addrs.SR_SUPERVISOR_BIT), \
        "the saved SR says a supervisor caller was not in supervisor mode"
    assert case.long_in(final, frame + 6) == trap.CALLER_AT + len(trap.caller(SVERSION)) - 6, \
        "the saved PC is not the instruction after the caller's own jump into the entry"
    registers = [case.long_in(final, frame + 0x0A + 4 * index)
                 for index in range(addrs.GEMDOS_SAVED_REGISTERS)]
    assert registers == [trap.ENTRY_REGS[name] for name in
                         ("d1", "d2", "d3", "d4", "d5", "d6", "d7", "a0", "a1", "a2")]
    assert addrs.GEMDOS_SAVED_FRAME_BYTES == 4 + 2 + 4 + 4 * addrs.GEMDOS_SAVED_REGISTERS


def test_the_dispatcher_runs_on_the_operating_systems_own_stack():
    """`movea.l #$16ce,sp`, before the call and after the frame is built — so the dispatcher and
    everything it calls run on a stack of the OS's own whatever the caller's was, and a program that
    traps with two bytes of stack left still gets a working GEMDOS."""
    _final, _writes, _regs = run(
        {trap.CALLER_AT: trap.caller(SVERSION),
         abi.FIRST_ARG: trap.longword(addrs.GEMDOS_TRAP1)},
        stop_pc=addrs.GEMDOS_DISPATCH)
    # Arriving at the dispatcher at all is the claim `stop_pc` makes; what the stack was is the
    # dispatcher's own frame, which its battery reads. Here it is enough that the switch happened
    # before the call, which the instruction order below says.
    switch = bytes(BASE_IMAGE[addrs.GEMDOS_TRAP1:addrs.GEMDOS_TRAP1_END])
    assert switch.count(b"\x2e\x7c" + trap.longword(addrs.GEMDOS_SUPERVISOR_STACK)) == 2, \
        "the entry no longer has one stack switch per caller mode"


def test_a_gemdos_call_hands_back_every_register():
    """THE REGISTER CONTRACT, and it is the OPPOSITE of the BIOS entry's.

    `src/bios/trap.S` gives the caller nine registers back and lets D1, D2, A0, A1 and A2 come back
    holding whatever the called routine left — `docs/on-target-execution.md`'s d2/a2 bug class.
    GEMDOS restores all fifteen out of the two halves of the process frame, and D0 is the result. A
    program written against that is right on the machine, so the reconstruction reproduces it.
    """
    _final, _writes, regs = call(SVERSION)
    assert regs["d0"] == addrs.GEMDOS_VERSION
    for name in emu.REPORTED_REGS:
        if name in ("d0", "ninsns", "cycles") or not name[0] in "da":
            continue
        assert regs[name] == trap.ENTRY_REGS[name], (
            f"{name} came back as {regs[name]:#x} rather than the caller's own "
            f"{trap.ENTRY_REGS[name]:#x} — the GEMDOS entry restores the whole file")


def test_a_user_mode_caller_is_framed_on_its_own_stack_and_returns_to_user_mode():
    """The arm the `btst #13` picks, and the one a real program takes: the caller's words are on the
    USER stack, so the frame is built there and the SUPERVISOR stack pointer is what gets saved
    beside it. Nothing else in this project executes it — the oracle enters every run in supervisor
    mode, so it takes a caller that says otherwise."""
    pokes = {trap.USER_CALLER_AT: trap.user_mode_caller(SVERSION),
             abi.FIRST_ARG: trap.longword(addrs.GEMDOS_TRAP1),
             **trap.user_stack(SVERSION)}
    final, _writes, regs = run(pokes, entry=trap.USER_CALLER_AT)
    assert regs["d0"] == addrs.GEMDOS_VERSION
    frame = case.long_in(final, gemdos.BASEPAGE + addrs.BASEPAGE_SAVED_FRAME)
    assert frame < trap.USER_STACK_AT, "the frame is not on the USER stack"
    assert case.word_in(final, frame + 4) == trap.USER_MODE_SR
    assert case.long_in(final, frame) >= emu.STACK_TOP - emu.STACK_SCRATCH, \
        "the stack pointer saved beside it is not the SUPERVISOR one"


# ---- `Super`, served inline ------------------------------------------------------------------------

@pytest.mark.parametrize("what,stub_at,stub,staged,expected", (
    ("a supervisor caller", trap.CALLER_AT,
     trap.caller(addrs.GEMDOS_SUPER_FN, gemdos.long_words(SUPER_QUERY)), {},
     SUPER_IS_SUPERVISOR),
    ("a user-mode caller", trap.USER_CALLER_AT,
     trap.user_mode_caller(addrs.GEMDOS_SUPER_FN, gemdos.long_words(SUPER_QUERY)),
     trap.user_stack(addrs.GEMDOS_SUPER_FN, gemdos.long_words(SUPER_QUERY)), SUPER_IS_USER),
), ids=lambda arg: arg)
def test_super_1_reports_the_callers_mode_and_changes_nothing(what, stub_at, stub, staged,
                                                              expected):
    """`Super(1)` — the arm both caller modes share, and the only one that leaves the mode alone.

    `move.l #$2000,d0 / and.w (sp),d0` answers 0 or -1 out of the frame's own SR, so the whole of D0
    is written: a supervisor caller gets $ffffffff and a user one a clean zero, not the caller's own
    high half with a flag in the bottom.
    """
    pokes = {stub_at: stub, abi.FIRST_ARG: trap.longword(addrs.GEMDOS_TRAP1), **staged}
    final, writes, regs = run(pokes, entry=stub_at)
    assert regs["d0"] == expected
    assert gemdos.BASEPAGE + addrs.BASEPAGE_SAVED_FRAME not in writes, \
        "`Super` framed the process — it is served inline, before any of that"
    assert case.long_in(final, addrs.GEMDOS_TERMINATION_JMPBUF) == \
        case.long_in(BASE_IMAGE, addrs.GEMDOS_TERMINATION_JMPBUF), \
        "`Super` reached the dispatcher, which it must never do"


def test_super_0_from_a_user_caller_switches_to_supervisor_on_the_callers_own_stack():
    """`Super(0)` from user mode: the caller keeps the stack it is already on and gets the OLD
    SUPERVISOR STACK POINTER back in D0 — which is what it later passes to `Super(ssp)` to go back.

    The exception frame is MOVED onto that stack with the S bit set, so the `rte` lands in
    supervisor mode running on what was the user stack.
    """
    arguments = gemdos.long_words(SUPER_TO_SUPERVISOR)
    pokes = {trap.USER_CALLER_AT: trap.user_mode_caller(addrs.GEMDOS_SUPER_FN, arguments),
             abi.FIRST_ARG: trap.longword(addrs.GEMDOS_TRAP1),
             **trap.user_stack(addrs.GEMDOS_SUPER_FN, arguments)}
    _final, _writes, regs = run(pokes, entry=trap.USER_CALLER_AT)
    assert emu.STACK_TOP - emu.STACK_SCRATCH <= regs["d0"] <= emu.STACK_TOP, (
        f"D0 is {regs['d0']:#x}, which is not the supervisor stack pointer the caller is being "
        f"handed custody of")


def test_super_from_a_supervisor_caller_returns_to_user_mode():
    """...and the same selector from the other side, which is the half the name does not say:
    `Super` toggles. A supervisor caller's `Super(0)` plants USP just past the exception frame — so
    the caller carries on on the stack it was already using — and clears the frame's S bit.

    THE RESULT IS NOT WRITTEN AT ALL on this arm, which is the quirk: the ROM never touches D0, so
    the caller reads its own D0 back as `Super`'s answer.
    """
    _final, _writes, regs = run(
        {trap.CALLER_AT: trap.caller(addrs.GEMDOS_SUPER_FN,
                                         gemdos.long_words(SUPER_TO_SUPERVISOR)),
         abi.FIRST_ARG: trap.longword(addrs.GEMDOS_TRAP1)})
    assert regs["d0"] == trap.ENTRY_REGS["d0"], (
        "D0 was written — the supervisor-mode `Super(0)` arm answers with the caller's own")


# Where a supervisor caller's `Super(ssp)` is told to put its stack. It must NOT be the user stack
# pointer the same stub plants: the arm compares the two and carries four bytes of the caller's own
# words across to the user stack when they differ, so one address for both would have the two writes
# land on top of each other. Both are inside the band the diff drops.
A_SUPERVISOR_STACK = trap.USER_STACK_AT - 0x20


def test_super_ssp_from_a_supervisor_caller_leaves_the_saved_sr_in_d0():
    """`Super(ssp)` from supervisor mode — how a program that called `Super(0)` goes back to user.

    Its quirk is D0: the arm pops the frame's SR into D0 on its way to rebuilding the frame on
    `ssp`, and never writes it again. So the caller's D0 comes back with its own high word and the
    SAVED STATUS REGISTER in the low one. A reconstruction that cleared D0, or answered the stack
    pointer, would agree about every byte of the image and differ here alone.

    READ AS A SLICE, stopped at the arm's own `rte`. Where a caller resumes after this arm is not
    something a staged caller can be made to survive: the ROM plants USP four bytes below where it
    found it and moves the first LONGWORD OF THE CALLER'S OWN ARGUMENT WORDS there, so what the
    caller returns onto is its stack shifted by an amount that depends on what it pushed. That is
    the ROM's behaviour and `trap1.S` reproduces it; the case reads the register rather than
    pretending to be a program that could carry on.
    """
    stub = gemdos.supervisor_caller_with_a_user_stack(
        addrs.GEMDOS_SUPER_FN, gemdos.long_words(A_SUPERVISOR_STACK))
    _final, _writes, regs = run({gemdos.SUPER_CALLER_AT: stub,
                                 abi.FIRST_ARG: trap.longword(addrs.GEMDOS_TRAP1)},
                                entry=gemdos.SUPER_CALLER_AT,
                                stop_pc=addrs.GEMDOS_SUPER_LEAVE_SUPERVISOR)
    assert regs["d0"] >> 16 == trap.ENTRY_REGS["d0"] >> 16
    assert regs["d0"] & (1 << addrs.SR_SUPERVISOR_BIT), (
        f"D0's low word is {regs['d0'] & 0xffff:#x}, which is not the supervisor SR the arm popped "
        f"into it")


# ---- what a call COSTS, and the constant the Tier 3 rows are quoted net of --------------------------

@pytest.mark.parametrize("what,stub_at,stub,staged,cost", (
    ("no arguments", trap.CALLER_AT, trap.caller(SVERSION), {}, trap.caller_cost()),
    ("a longword argument, as two words", trap.CALLER_AT,
     trap.caller(addrs.GEMDOS_FSETDTA_FN, gemdos.long_words(0)), {},
     trap.caller_cost(gemdos.long_words(0))),
    ("a user-mode caller", trap.USER_CALLER_AT, trap.user_mode_caller(SVERSION),
     trap.user_stack(SVERSION), trap.caller_cost(user_mode=True)),
), ids=lambda arg: arg)
def test_each_caller_shape_costs_what_the_tier_3_rows_are_quoted_net_of(what, stub_at, stub,
                                                                        staged, cost):
    """Every Tier 3 row for this routine is a WHOLE CALL, because an exception handler can only be
    entered through a caller. The caller's own cost is identical on both sides, so
    `rom_bench.Measurement` takes it off both columns and what is left is the two entries.

    The constants are `trap.py`'s, and this is where they are shown to hold for a GEMDOS caller too
    — the same three shapes, measured through a NULL DISPATCHER whose whole body is the `rte` that
    consumes the frame the caller built.
    """
    insns, cycles = cost
    pokes = {stub_at: stub, abi.FIRST_ARG: trap.longword(NULL_DISPATCHER_AT),
             NULL_DISPATCHER_AT: RTE, **staged}
    _final, _writes, regs = run(pokes, entry=stub_at)
    assert regs["cycles"] - RESET_CYCLES - RTE_CYCLES == cycles
    assert regs["ninsns"] - RESET_INSNS - RTE_INSNS == insns


# ---- the transcription -------------------------------------------------------------------------------

def test_the_transcription_is_the_roms_bytes_exactly(bench):
    """THE BYTE PIN, and the check the differential cannot make.

    The second differential runs the two entries over the cases below and requires the same image,
    the same register file and the same traffic — everything an instruction DOES. What it cannot see
    is an instruction no case distinguishes: `beq.w` transcribed as `bne.w` on an arm every case
    agrees about costs the same and leaves the same image. Nothing but the bytes says which ROM this
    is.

    Nothing is spliced, unlike `src/bios/trap.S`'s two `lea`s: every external reference in these two
    routines is absolute or immediate in the ROM itself, so a transcription linked anywhere is the
    ROM's own 292 bytes.
    """
    expected = bytes(BASE_IMAGE[addrs.GEMDOS_TRAP1:addrs.GEMDOS_TRAP1_END])
    blob_at = bench.entry("gemdos_trap1") - bench.base
    ours = bench.blob[blob_at:blob_at + len(expected)]
    assert ours == expected, (
        f"src/gemdos/trap1.S is not the ROM's instruction sequence. First difference at byte "
        f"{next(i for i, (a, b) in enumerate(zip(ours, expected)) if a != b)} of "
        f"{len(expected)}")


def test_the_c_entry_follows_the_trap_entry_in_the_transcription(bench):
    """...and that the pin above really covers BOTH routines. `gemdos_entry_c` is the OS's own door
    into GEMDOS ($fc5078) and it is inside the 292 bytes only because the assembler laid it out
    where the ROM has it — which is a fact about the build, so it is asserted rather than assumed."""
    assert bench.entry("gemdos_entry_c") - bench.entry("gemdos_trap1") == \
        addrs.GEMDOS_ENTRY_C - addrs.GEMDOS_TRAP1


@pytest.mark.parametrize("case", gemdos.TRANSCRIPTIONS, ids=lambda row: row[0])
def test_the_transcription_costs_exactly_what_the_rom_does(case, bench):
    """No relocated `lea`, so no extra cycle either: the two entries are the same instructions at the
    same prices, and a transcription that had grown or lost one would differ here."""
    _name, symbol, caller_at, regs, pokes, _cost = case
    measured = bench.measure_transcription(caller_at, symbol, regs, pokes=pokes)
    assert measured.recreate_insns == measured.original_insns
    assert measured.recreate_cycles == measured.original_cycles


def test_the_m68k_transcription_equals_the_rom(bench):
    """`src/gemdos/trap1.S` over every case, against the ROM's own instructions — the same image,
    the same WHOLE register file and the same off-image streams."""
    for _name, symbol, caller_at, regs, pokes, _cost in gemdos.TRANSCRIPTIONS:
        bench.measure_transcription(caller_at, symbol, regs, pokes=pokes)


# ---- the registry ---------------------------------------------------------------------------------------

def _transcription(name, stub_at, stub, staged, cost):
    return gemdos.register_transcription(name, "gemdos_trap1", stub_at, trap.ENTRY_REGS,
                                         gemdos.entry_pokes("gemdos_trap1", stub_at, stub, staged),
                                         cost)


def _register_all():
    """THE FOUR `Super` ARMS, and why the FRAMING path is not among them.

    A transcription case is a whole call on one image, and the two entries are at different
    addresses — so the moment the entry does `movea.l #$16ce,sp / jsr`, the four bytes of return
    address it pushes onto the OPERATING SYSTEM'S OWN STACK differ between the two runs. Those
    bytes are real image (the harness drops only its own stack band) and nothing in the relation
    can excuse them, which `test_the_framing_paths_only_divergence_is_its_own_return_address`
    measures rather than assumes.

    `Super` never switches stacks — it is served before any of that and returns through `rte` — so
    its arms are the ones a whole-call differential can carry. What holds the framing path instead
    is the exact byte pin above, which is a stronger statement about the instructions than a
    differential is, plus the ROM-side claims in this file.
    """
    _transcription("Super(1) from a supervisor caller", trap.CALLER_AT,
                   trap.caller(addrs.GEMDOS_SUPER_FN, gemdos.long_words(SUPER_QUERY)), {},
                   trap.caller_cost(gemdos.long_words(SUPER_QUERY)))
    _transcription("Super(0) from a supervisor caller, which leaves for user mode",
                   trap.CALLER_AT,
                   trap.caller(addrs.GEMDOS_SUPER_FN, gemdos.long_words(SUPER_TO_SUPERVISOR)), {},
                   trap.caller_cost(gemdos.long_words(SUPER_TO_SUPERVISOR)))
    _transcription("Super(1) from a USER-mode caller", trap.USER_CALLER_AT,
                   trap.user_mode_caller(addrs.GEMDOS_SUPER_FN,
                                           gemdos.long_words(SUPER_QUERY)),
                   trap.user_stack(addrs.GEMDOS_SUPER_FN, gemdos.long_words(SUPER_QUERY)),
                   trap.caller_cost(user_mode=True))
    _transcription("Super(0) from a USER-mode caller", trap.USER_CALLER_AT,
                   trap.user_mode_caller(addrs.GEMDOS_SUPER_FN,
                                           gemdos.long_words(SUPER_TO_SUPERVISOR)),
                   trap.user_stack(addrs.GEMDOS_SUPER_FN,
                                     gemdos.long_words(SUPER_TO_SUPERVISOR)),
                   trap.caller_cost(user_mode=True))


_register_all()


def test_the_framing_paths_only_divergence_is_its_own_return_address(bench):
    """...and the residual above, MEASURED: run a whole `Sversion` call through both entries and ask
    what differs.

    The answer must be the four bytes at `$16c6` and nothing else — the longword the `jsr` into the
    dispatcher pushes onto the OS's own supervisor stack, which is each entry's own address. A
    divergence anywhere else would be the transcription being wrong, and this is what says so
    instead of a paragraph claiming the case could not be run.
    """
    pokes = gemdos.entry_pokes("gemdos_trap1", trap.CALLER_AT, trap.caller(SVERSION))
    with pytest.raises(AssertionError) as refusal:
        bench.measure_transcription(trap.CALLER_AT, "gemdos_trap1", trap.ENTRY_REGS,
                                    pokes=pokes)
    differing = set(int(address, 16) for address in
                    re.findall(r"(0x[0-9a-f]+) \(0x", str(refusal.value)))
    pushed = set(range(addrs.GEMDOS_SUPERVISOR_STACK - 8, addrs.GEMDOS_SUPERVISOR_STACK - 4))
    assert differing and differing <= pushed, (
        f"the framing path diverges at {sorted(hex(at) for at in differing - pushed)} as well as at "
        f"the `jsr` return address on the OS stack — that is the transcription being wrong, not the "
        f"relation being unable to say so")
