"""The BIOS / XBIOS TRAP DISPATCHER @ $fc07f2..$fc0845 — the entry every other battery starts past.

    $fc07f2  xbios_trap14   lea   XBIOS_FUNCTION_TABLE(pc),a0     ; vector $b8
    $fc07f6                 bra.s trap_dispatch_common
    $fc07f8  bios_trap13    lea   BIOS_FUNCTION_TABLE(pc),a0      ; vector $b4, falling through into
    $fc07fc  trap_dispatch_common
                            movea.l savptr,a1                     ; ...the body both traps share

`src/bios/trap.S` is the reconstruction, and it is ASSEMBLY rather than C because an exception
handler cannot be C on the target: it is entered with a 68000 exception frame, it moves the stack
pointer between the supervisor and user stacks, and the register file it hands back is its contract.
That file's header has the argument in full.

WHAT PROVES THE RECONSTRUCTION, and it is not this file. A transcription's differential is the
SECOND DIFFERENTIAL of Tier 3's numerator — the m68k assembly of `trap.S`, entered over the same
staged frame as the ROM, required to leave the same image, the same WHOLE register file and the same
chip traffic (`tools/recreate_kit/rom_bench.py`, `RomBench.measure_transcription`). It runs from
`test_the_m68k_transcription_equals_the_rom` below and again, with a cost attached, from
`test_tier3.py` over the same `trap.CASES`.

WHAT IS IN THIS FILE is everything that is a claim about the ROM rather than about the copy: that
the hand-built frame the cases stage really is the one a `trap #13` builds; what the save area holds
and how deep; that the called routine is entered with A5 = 0; which registers come back and which do
not; what an out-of-range function number returns; and the two arms nothing else in this project
ever executes — the INDIRECT table entry and the user-mode caller.

THE ONE ARM THAT IS DOCUMENTED RATHER THAN EXECUTED is a NEGATIVE function number. The bound check
is `cmp.w (a0)+,d0` / `bge`, which is SIGNED, so it bounds the number from above only: `Bios(-1)`
passes it, `lsl.w #2` makes $fffc, and `move.l (0,a0,d0.w),d0` reads the four bytes BELOW the table
— for the BIOS table, the dispatcher's own `rte` opcode — and `jsr`s through them, to $4e73000c.
There is no case for that here because there is nothing to compare: the run walks off into unmapped
memory and ends at the instruction cap on both sides. It is a real ROM quirk and `trap.S` reproduces
it; what would pin it is an oracle that could assert "and then it faulted", which this one cannot.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from harness import (BASE_IMAGE, OS_PSG_PORT_SELECT, addrs, diff_spans, differing_addresses, emu,
                     make_image)

import abi
import trap
from opcodes import RTE, TRAP_BIOS, TRAP_XBIOS
from recreate_kit.rom_bench import RomBench


@pytest.fixture(scope="module")
def bench():
    """The cross-compiled blob, loaded once per worker — `test_tier3.py`'s fixture, for its reason:
    a missing blob is a broken target build and must FAIL rather than skip."""
    return RomBench()

# Where a NULL DISPATCHER is staged — a handler whose whole body is the `rte` that consumes the
# frame the caller built, which is how a caller's own cost is measured with nothing else in it.
NULL_DISPATCHER_AT = trap.ROUTINE_AT
RTE_CYCLES = 20                 # 68000 `rte`: 20 cycles, and it is one instruction
RTE_INSNS = 1

# What the oracle charges before either entry executes anything (test_tier3.RESET_OBSERVATION,
# named here because this file subtracts it by hand rather than through `Measurement`).
RESET_INSNS = 1
RESET_CYCLES = 40


def run(case_pokes, entry=trap.CALLER_AT, regs=None, stop_pc=0):
    """One run of the ORIGINAL, entered at the caller the case staged."""
    return emu.run(make_image(case_pokes), entry, dict(regs or trap.ENTRY_REGS), stop_pc=stop_pc)


def call(function, args=(), handler=addrs.BIOS_TRAP13, staged=None):
    """...and the ordinary shape of one: a supervisor caller, through the hand-built frame."""
    pokes = {trap.CALLER_AT: trap.caller(function, args),
             abi.FIRST_ARG: trap.longword(handler), **(staged or {})}
    return run(pokes)


def witness(final, at):
    return int.from_bytes(bytes(final[at:at + 4]), "big")


# ---- the case shape itself: is the staged frame a trap's? ----------------------------------------

@pytest.mark.parametrize("trap_opcode,handler,function", (
    (TRAP_BIOS, addrs.BIOS_TRAP13, addrs.BIOS_DRVMAP_FN),
    (TRAP_XBIOS, addrs.XBIOS_TRAP14, addrs.XBIOS_LOGBASE_FN),
))
def test_the_hand_built_frame_is_the_one_a_real_trap_builds(trap_opcode, handler, function):
    """THE CASE SHAPE'S OWN PROOF, and every other claim in this file rests on it.

    The cases stage a caller that builds the exception frame by hand and enters the dispatcher
    through it, because a real `trap` reaches the machine's own vector table and could therefore
    only ever run the ROM's dispatcher — never our transcription. So the hand-built frame has to be
    shown to be the same frame: the same case through a caller that TRAPS, and the two runs required
    indistinguishable in the register file they leave and in every byte of memory outside the run's
    own stack band.

    They differ in exactly one thing, and it is the one thing they must: the RETURN PC in the save
    area, which is each caller's own address. Asserted as a span rather than waved at — the saved SR
    beside it is required EQUAL, which is the real claim about `move.w sr,-(sp)`.
    """
    hand = {trap.CALLER_AT: trap.caller(function), abi.FIRST_ARG: trap.longword(handler)}
    real = {trap.TRAP_CALLER_AT: trap.trap_caller(function, opcode=trap_opcode)}
    hand_final, _writes, hand_regs = run(hand)
    real_final, _writes, real_regs = run(real, entry=trap.TRAP_CALLER_AT)

    assert {name: hand_regs[name] for name in emu.REPORTED_REGS} == \
           {name: real_regs[name] for name in emu.REPORTED_REGS}

    # The two stubs themselves, which are the one thing the two runs are MEANT to differ in — and
    # the band the oracle's own stack lives in, dropped through `harness.diff_spans()` rather than
    # re-spelt here, so this reads the same band `harness.differential` and `RomBench` read.
    caller_bytes = set(range(trap.CALLER_AT, trap.CALLER_AT + len(hand[trap.CALLER_AT]))) | \
        set(range(trap.TRAP_CALLER_AT, trap.TRAP_CALLER_AT + len(real[trap.TRAP_CALLER_AT])))
    differing = set(differing_addresses(memoryview(hand_final), memoryview(real_final),
                                        diff_spans(), caller_bytes.__contains__))
    saved_pc = set(range(trap.SAVED_PC_AT, trap.SAVED_PC_AT + 4))
    assert differing <= saved_pc, (
        f"a hand-built frame and a real `trap` left different memory at "
        f"{sorted(hex(at) for at in differing - saved_pc)} — the staged caller is not entering the "
        f"dispatcher the way the processor does")
    assert hand_final[trap.SAVED_SR_AT:trap.SAVED_SR_AT + 2] == \
        real_final[trap.SAVED_SR_AT:trap.SAVED_SR_AT + 2], \
        "`move.w sr,-(sp)` pushed a different status word than the trap exception does"


# ---- the save area: one frame per call, and savptr walks --------------------------------------

def test_the_dispatcher_frames_one_call_in_the_save_area_and_unwinds_it():
    """`movea.l savptr,a1` ... `move.l a1,savptr` on the way in, and the mirror image on the way out.

    The DEPTH is the claim a reader cannot get from the final image, because by then the frame is
    popped: the staged routine records savptr while the call is in flight, and it has moved down by
    exactly one frame — the exception frame's 6 bytes plus the ten registers' 40.
    """
    final, writes, _regs = call(addrs.BIOS_RWABS_FN, staged=trap.INDIRECT)
    assert witness(final, trap.WITNESS_SAVPTR) == trap.FRAME_AT, "the frame is not one frame deep"
    assert witness(final, addrs.SYSVAR_SAVPTR) == trap.SAVE_AREA_TOP, "savptr was not unwound"
    assert addrs.SYSVAR_SAVPTR in writes, "savptr is REWRITTEN on both edges, not left alone"
    assert trap.FRAME_AT == trap.SAVE_AREA_TOP - addrs.TRAP_SAVE_FRAME_BYTES


def test_the_saved_frame_holds_the_exception_frame_above_the_registers():
    """What one frame IS, read back out of the save area: ten longwords, then the return PC, then
    the SR word at the top — which is the order the two `movem`s and the two `move`s produce, and
    the order `rte` needs them rebuilt in."""
    final, _writes, _regs = call(addrs.BIOS_DRVMAP_FN)
    saved = [int.from_bytes(bytes(final[trap.FRAME_AT + 4 * i:trap.FRAME_AT + 4 * i + 4]), "big")
             for i in range(addrs.TRAP_SAVED_REGISTERS)]
    # `movem.l regs,-(a1)` writes downwards from A7, so in ASCENDING memory the file reads d3..a6
    # and then A7 — which is the caller's own stack pointer, and the reason the restoring `movem`
    # puts the supervisor stack back without a word about it.
    assert saved[:len(trap.PRESERVED)] == [trap.ENTRY_REGS[name] for name in trap.PRESERVED], \
        "the register half of the frame is not d3-d7/a3-a6 in that order"
    assert saved[len(trap.PRESERVED)] < emu.STACK_TOP, "the tenth longword is not a stack pointer"
    assert int.from_bytes(bytes(final[trap.SAVED_SR_AT:trap.SAVED_SR_AT + 2]), "big") & \
        (1 << addrs.SR_SUPERVISOR_BIT), "a supervisor caller's frame says it was not supervisor"


# ---- the call itself --------------------------------------------------------------------------

def test_the_called_routine_is_entered_with_a5_zero():
    """`suba.l a5,a5`, which is why every other battery in this project passes `{"a5": 0}` — and it
    is asserted from inside the call, by a routine the case wrote, rather than inferred from one."""
    final, _writes, regs = call(addrs.BIOS_RWABS_FN, staged=trap.INDIRECT)
    assert witness(final, trap.WITNESS_A5) == 0
    assert regs["a5"] == trap.ENTRY_REGS["a5"], "...and the caller's own A5 is handed back"


def test_the_indirect_table_entry_is_followed_through_its_ram_vector():
    """Bit 31 set means the entry is the address of a LONGWORD holding the routine, not the routine
    — how Rwabs, Getbpb and Mediach reach a driver that is not in the ROM. The case points `hdv_rw`
    at a routine of its own, and what proves the arm was taken is that the routine ran."""
    final, _writes, regs = call(addrs.BIOS_RWABS_FN, staged=trap.INDIRECT)
    assert regs["d0"] == trap.scribbled("d0"), "the routine the RAM vector names did not run"
    assert witness(final, trap.WITNESS_SAVPTR) == trap.FRAME_AT


@pytest.mark.parametrize("function,handler,expected", (
    (addrs.BIOS_DRVMAP_FN, addrs.BIOS_TRAP13, "SYSVAR_DRVBITS"),
    (addrs.XBIOS_LOGBASE_FN, addrs.XBIOS_TRAP14, "SYSVAR_V_BAS_AD"),
))
def test_each_entry_indexes_its_own_table(function, handler, expected):
    """The two entries differ in one instruction — which table `a0` is loaded with — so the proof is
    that the same function NUMBER through the two of them reaches different routines. 10 is Drvmap
    under trap #13 and 3 is Logbase under trap #14, and each answers with its own system variable."""
    _final, _writes, regs = call(function, handler=handler)
    at = getattr(addrs, expected)
    assert regs["d0"] == int.from_bytes(bytes(BASE_IMAGE[at:at + 4]), "big")


def test_a_function_number_at_or_past_the_count_returns_without_dispatching():
    """The bound check, and what the caller gets when it fails.

    D0 is NOT an error code: the low word is the function number the caller asked for, and the high
    word is the caller's own D0, untouched — the dispatcher only ever wrote D0's low half. A
    reconstruction that cleared D0 first, or answered -1, would agree with the ROM about everything
    else in the image and differ here alone.
    """
    _final, _writes, regs = call(trap.BIOS_FUNCTION_COUNT)
    caller_high = trap.ENTRY_REGS["d0"] & 0xFFFF_0000
    assert regs["d0"] == caller_high | trap.BIOS_FUNCTION_COUNT


def test_an_out_of_range_number_still_frames_and_unwinds():
    """...and it takes the whole path around the `jsr` rather than returning early: the frame is
    pushed before the bound check and popped after it, so savptr comes back where it was."""
    final, writes, _regs = call(trap.BIOS_FUNCTION_COUNT)
    assert witness(final, addrs.SYSVAR_SAVPTR) == trap.SAVE_AREA_TOP
    assert trap.FRAME_AT in writes, "no frame was written, so the bound check is being made first"


# ---- the register file the caller gets back ----------------------------------------------------

def test_the_dispatcher_hands_back_d3_to_d7_and_a3_to_a6_and_nothing_else():
    """THE REGISTER CONTRACT, and the half of it that has cost a real-hardware run.

    The `movem` pair saves and restores d3-d7/a3-a7 and no more, so D1, D2, A0, A1 and A2 come back
    holding whatever the called routine left in them — which is `docs/on-target-execution.md`'s
    "TOS traps clobber d2/a2 that GCC thinks are callee-saved". The staged routine scribbles a
    distinct value into every one of them, and this is that fact with an address on it.
    """
    _final, _writes, regs = call(addrs.BIOS_RWABS_FN, staged=trap.INDIRECT)
    for name in trap.PRESERVED:
        assert regs[name] == trap.ENTRY_REGS[name], f"{name} should have been handed back"
    for name in trap.PASSED_THROUGH:
        assert regs[name] == trap.scribbled(name), (
            f"{name} came back as the caller left it, but the ROM's `movem` list does not carry it "
            f"— a caller that relied on this would be right here and wrong on the machine")
    for name in trap.DISPATCHER_SCRATCH:
        assert regs[name] == trap.SAVE_AREA_TOP, (
            f"{name} is the dispatcher's own walking frame pointer and its epilogue reloads it from "
            f"savptr, so the caller gets the save area's top rather than the routine's value")


def test_the_user_mode_arm_runs_on_the_users_own_stack():
    """`btst #13` on the frame's SR, and the `move.l usp,sp` under it.

    A user-mode caller's arguments are on the USER stack, and the exception frame is on the
    supervisor one, so the dispatcher switches over before it pops the function number — and the
    called routine, its `jsr` return address and everything it pushes are on the user stack too.
    Nothing else in this project executes that arm: the oracle enters every run in supervisor mode,
    so it takes a caller that says otherwise, which is what `trap.user_mode_caller` is.
    """
    pokes = {trap.USER_CALLER_AT: trap.user_mode_caller(addrs.BIOS_RWABS_FN),
             abi.FIRST_ARG: trap.longword(addrs.BIOS_TRAP13),
             **trap.INDIRECT, **trap.user_stack(addrs.BIOS_RWABS_FN)}
    final, _writes, regs = run(pokes, entry=trap.USER_CALLER_AT)
    assert regs["d0"] == trap.scribbled("d0"), "the call did not reach the routine"
    assert witness(final, trap.WITNESS_SAVPTR) == trap.FRAME_AT
    assert int.from_bytes(bytes(final[trap.SAVED_SR_AT:trap.SAVED_SR_AT + 2]), "big") == \
        trap.USER_MODE_SR, "the frame this arm is selected by is not the one that was saved"


# ---- what a call COSTS, and the constant a reader needs to read the Tier 3 rows -----------------

# The three caller SHAPES this battery stages, each with the pokes it needs and the cost `trap.py`
# claims for it. One table rather than three tests, because the claim is the same claim three times
# and the thing that varies is the stub.
CALLER_SHAPES = (
    ("no arguments", trap.CALLER_AT, trap.caller(addrs.BIOS_DRVMAP_FN), {}, trap.caller_cost()),
    ("one argument word", trap.CALLER_AT, trap.caller(addrs.BIOS_KBSHIFT_FN, (0xffff,)), {},
     trap.caller_cost((0xffff,))),
    ("a user-mode caller", trap.USER_CALLER_AT, trap.user_mode_caller(addrs.BIOS_DRVMAP_FN),
     trap.user_stack(addrs.BIOS_DRVMAP_FN), trap.caller_cost(user_mode=True)),
)


@pytest.mark.parametrize("name,stub_at,stub,staged,cost", CALLER_SHAPES, ids=lambda arg: arg)
def test_each_caller_shape_costs_what_the_tier_3_rows_are_quoted_net_of(name, stub_at, stub,
                                                                       staged, cost):
    """Every Tier 3 row for this routine is a WHOLE CALL — the staged caller, the dispatcher and
    whatever it dispatched to — because that is the only way an exception handler can be entered.
    The caller's own cost is identical on both sides, so `rom_bench.Measurement` takes it off BOTH
    columns (`shared_entry`) and what is left is the two dispatchers. A row netted by the wrong
    constant is a row about nothing, so the constants are MEASURED here rather than declared, and
    per shape: a supervisor caller pushes each argument word itself and a user-mode one does not.

    Measured through a NULL DISPATCHER: a handler whose whole body is the `rte` that consumes the
    frame the caller built, so nothing but the caller is in the figure.
    """
    insns, cycles = cost
    pokes = {stub_at: stub, abi.FIRST_ARG: trap.longword(NULL_DISPATCHER_AT),
             NULL_DISPATCHER_AT: RTE, **staged}
    _final, _writes, regs = run(pokes, entry=stub_at)
    assert regs["cycles"] - RESET_CYCLES - RTE_CYCLES == cycles
    assert regs["ninsns"] - RESET_INSNS - RTE_INSNS == insns


# ---- the GEM trap, read but not reconstructed ---------------------------------------------------

@pytest.mark.parametrize("selector,arm", (
    (addrs.GEM_SELECTOR_PTERM, addrs.GEM_TRAP2_PTERM_ARM),
    (addrs.GEM_SELECTOR_AES, addrs.GEM_TRAP2_AES_ARM),
    (addrs.GEM_SELECTOR_AES_ALT, addrs.GEM_TRAP2_AES_ARM),
    (0x0073, addrs.GEM_TRAP2_VDI_ARM),          # the VDI's own opcode, and the default arm with it
    (0x00c7, addrs.GEM_TRAP2_VDI_ARM),          # ...one below the AES range, to show it is exact
    (0x00ca, addrs.GEM_TRAP2_VDI_ARM),          # ...and one above it
))
def test_the_gem_trap_selects_its_interface_by_d0_alone(selector, arm):
    """`trap #2` is the THIRD trap entry in this ROM and the only one that is not a table dispatch:
    three compares on D0 pick between GEMDOS `Pterm(0)`, the AES dispatcher and the VDI, and
    everything that is not $00, $c8 or $c9 is the VDI.

    Read off the ROM as a SLICE — each run stops at the arm it selected — because the arms themselves
    are the AES's and the VDI's waves, not this one's. It is here because the dispatcher's battery is
    where "what a trap entry is" is written down, and because the selector map is what every later
    case for those components will enter through.
    """
    # `emu.run` RAISES on a run that reached neither the checkpoint nor an `rts`, so selecting the
    # wrong arm fails here by itself; what the assertion adds is that the run stopped because it
    # arrived rather than because something else did.
    _final, _writes, regs = emu.run(make_image({}), addrs.GEM_TRAP2, {"d0": selector}, stop_pc=arm)
    assert regs["ninsns"] > 0


# ---- the reconstruction ------------------------------------------------------------------------

# What the transcription costs the machine over the ROM's own instructions, in full. The ROM reaches
# each of its two dispatch tables with `lea (d16,pc),a0` — 8 cycles — because they sit 84 and 76
# bytes past the instruction; `trap.S` is linked wherever the build puts it, so the same `lea`
# assembles as absolute long, 12 cycles. ONE of the two runs per call, and it is the whole cycle
# difference between the two sides.
#
# THREE OPCODE WORDS DIFFER, not one: the two `lea`s, and the `bra.s` between them, whose
# displacement the wider encoding moves from 4 to 6. The branch costs the same either way, which is
# why the cycle figure is still one `lea`'s — and it is a difference all the same, which is why
# `test_the_transcription_is_the_roms_bytes_but_for_the_two_leas` splices all three rather than
# claiming every other word matches.
#
# Asserted as an exact cycle count rather than left to the Tier 3 ratio: at ~500 cycles of dispatcher
# the four cycles are 0.8%, which is inside `tier3.RATIO_TOLERANCE` — a pin there would not notice
# them doubling.
LEA_ABSOLUTE_EXTRA_CYCLES = 4


@pytest.mark.parametrize("case", trap.CASES, ids=lambda case: case[0])
def test_the_transcription_costs_the_rom_plus_one_absolute_lea(case, bench):
    """...and the same instructions, which is the other half of the claim: a transcription that had
    grown or lost one would differ here even where the cycle count happened to land."""
    _name, symbol, caller_at, regs, pokes, _cost = case
    measured = bench.measure_transcription(caller_at, symbol, regs, pokes=pokes)
    assert measured.recreate_insns == measured.original_insns
    assert measured.recreate_cycles - measured.original_cycles == LEA_ABSOLUTE_EXTRA_CYCLES


@pytest.mark.parametrize("seed", (1, 2, 3))
def test_no_case_here_depends_on_a_byte_the_capture_does_not_reproduce(seed):
    """THE MASK, for these cases — `test_boot_snapshot.py`'s claim, made over this battery's own
    register rather than over `VERIFIED_CASES`.

    Two captures of the same boot disagree over 1,929 bytes, and a case that read one of them would
    be verified against one particular boot. The dispatcher writes INTO one of those regions'
    neighbourhood — the save area is at $90c — so the question is a live one here rather than a
    formality. Running the ORIGINAL over the snapshot and over a snapshot whose masked regions hold
    noise, and requiring the two indistinguishable, is what answers it.

    `_scrambled_base` and `_oracle_outputs` are imported rather than copied: they are the project's
    definitions of "the same run over a scrambled capture", and a second copy is what drifts.
    """
    import test_boot_snapshot as snapshot

    scrambled = snapshot._scrambled_base(seed)
    for name, _symbol, caller_at, regs, pokes, _cost in trap.CASES:
        shape = (name, caller_at, regs, pokes, None, None, ())
        assert snapshot._oracle_outputs(scrambled, shape) == \
            snapshot._oracle_outputs(snapshot.BASE_IMAGE, shape), (
                f"{name} behaves differently over a snapshot whose masked regions hold noise, so it "
                f"reads a byte two captures of the same boot disagree about")


# ---- the header the transcription includes ------------------------------------------------------
# `src/bios/trap.S` is the only assembler in this recreate, and it includes `addrs.h` so the ROM
# addresses it transcribes are named once rather than twice. That makes the header's ASSEMBLER
# readability a property of this reconstruction, and these two pin it.

# A macro's value that mentions one of the kit's own `OS_…` names: readable in C, where `os.h` is
# included, and an undefined symbol in a `.S`, where the guard skips that include. (The pattern
# matches the identifier, not the substring, so a project constant NAMED `OS_MEMORY_DESCRIPTOR` on
# the left of a define is not one.)
OS_NAME = re.compile(r"(?<![A-Za-z0-9_])OS_[A-Za-z0-9_]+")
INCLUDE_DIR = Path(__file__).resolve().parents[1] / "include"


def test_the_psg_port_this_project_names_is_the_kit_s_own():
    """`addrs.h` spells $ff8800 because it must be readable by the assembler and by `tools/addrs.py`,
    which takes integers only; the kit's `os.h` spells it `OS_PSG_PORT_SELECT` and the oracle
    DECODES that address. One of the two is the copy, so it is pinned rather than trusted — the same
    shape `test_bios_vbl.py` gives `MFP_GPIP`."""
    assert addrs.PSG_PORT_SELECT == OS_PSG_PORT_SELECT


def test_the_header_the_transcription_includes_holds_no_os_names():
    """...and the general form of it: preprocess `addrs.h` AS ASSEMBLY and require that nothing it
    defines still expands to an `OS_…` token.

    The failure this refuses is quiet in the worst way. Skipping the `os.h` include leaves such a
    macro expanding to an undefined symbol, and the assembler says nothing about the header — it
    fails at whatever line USES the constant, so a `.S` that happens not to use it builds green and
    the trap is left for the next transcription to walk into.
    """
    if not shutil.which("m68k-elf-gcc"):
        pytest.skip("m68k-elf-gcc is not installed; the cross build is what this pins")
    dumped = subprocess.run(
        ["m68k-elf-gcc", "-E", "-dM", "-D__ASSEMBLER__", "-x", "assembler-with-cpp",
         f"-I{INCLUDE_DIR}", str(INCLUDE_DIR / "addrs.h")],
        check=True, capture_output=True, text=True).stdout
    residual = []
    for line in dumped.splitlines():
        if not line.startswith("#define "):
            continue
        name, _space, value = line[len("#define "):].partition(" ")
        if OS_NAME.search(value):
            residual.append(f"{name} -> {value.strip()}")
    assert not residual, (
        f"addrs.h defines {len(residual)} macro(s) that expand to a name only `os.h` provides, and "
        f"`os.h` is not included when the assembler reads it: {', '.join(residual)}. Spell the "
        f"value as the integer and pin it equal to os.h with a test, as PSG_PORT_SELECT and "
        f"MFP_GPIP are")


# ---- the transcription, byte for byte -----------------------------------------------------------
# The two encodings the link forces, and the branch displacement they move. `lea (d16,pc),a0` is
# four bytes and reaches a table 84 or 76 bytes ahead; our tables are the ROM's own addresses and the
# file is linked wherever the build puts it, so the assembler has no choice but the absolute-long
# form — six bytes. The `bra.s` between them then has two more bytes to jump over.
LEA_ABSOLUTE_LONG_A0 = b"\x41\xf9"      # lea     <xxx>.l,a0
LEA_ABSOLUTE_BYTES = 6
BRA_SHORT = b"\x60"                     # bra.s   <d8>, the displacement in the second byte
BRA_SHORT_BYTES = 2
# A `bra.s` counts its displacement from the word AFTER its opcode word, which is the whole of it.
BRA_DISPLACEMENT_FROM = 2


def _expected_transcription():
    """The ROM's own bytes, with the three encodings a link legitimately changes spliced in.

    Everything from `trap_dispatch_common` on is the ROM's, taken verbatim — that is the claim this
    makes, and it is a stronger one than the cycle count: a `bge.s` transcribed as `bcc.s` costs the
    same, leaves the same image on every case this battery has, and differs HERE.
    """
    rom = bytes(BASE_IMAGE[addrs.XBIOS_TRAP14:addrs.BIOS_FUNCTION_TABLE])
    shared = rom[addrs.TRAP_DISPATCH_COMMON - addrs.XBIOS_TRAP14:]
    common_at = 2 * LEA_ABSOLUTE_BYTES + BRA_SHORT_BYTES
    displacement = common_at - (LEA_ABSOLUTE_BYTES + BRA_DISPLACEMENT_FROM)
    return (LEA_ABSOLUTE_LONG_A0 + trap.longword(addrs.XBIOS_FUNCTION_TABLE)
            + BRA_SHORT + bytes([displacement])
            + LEA_ABSOLUTE_LONG_A0 + trap.longword(addrs.BIOS_FUNCTION_TABLE)
            + shared)


def test_the_transcription_is_the_roms_bytes_but_for_the_two_leas(bench):
    """THE BYTE PIN, and the check the differential cannot make.

    The second differential runs the two dispatchers over six cases and requires the same image, the
    same register file and the same traffic — which is everything an instruction DOES. What it
    cannot see is an instruction no case distinguishes: the bound check is `bge.s` and the cases
    that exercise it are all non-negative, so `bcc.s` in its place passes every one of them, costs
    the same cycles, and is a different ROM. Nothing but the bytes says which one this is.

    So the whole of `src/bios/trap.S` is compared against the whole of $fc07f2..$fc0845, with only
    the three encodings above spliced — which is also what makes "+4 cycles and nothing else" a
    checked statement rather than a claim in a header.
    """
    blob_at = bench.entry("xbios_trap14") - bench.base
    expected = _expected_transcription()
    ours = bench.blob[blob_at:blob_at + len(expected)]
    assert ours == expected, (
        f"src/bios/trap.S is not the ROM's instruction sequence. First difference at byte "
        f"{next(i for i, (a, b) in enumerate(zip(ours, expected)) if a != b)} of "
        f"{len(expected)}; ours {ours.hex()} against {expected.hex()}")


def test_the_m68k_transcription_equals_the_rom(bench):
    """`src/bios/trap.S` over every case, against the ROM's own instructions.

    This is the transcription's differential, and the relation is stronger than a C core's: both
    sides are entered with the same whole register file and the whole of it must come back equal,
    alongside the same image and the same off-image streams (`RomBench.measure_transcription`).
    `test_tier3.py` runs the same cases again with the cost attached; this one is here so that a
    divergence names the dispatcher rather than a row of a table.
    """
    for _name, symbol, caller_at, regs, pokes, _cost in trap.CASES:
        bench.measure_transcription(caller_at, symbol, regs, pokes=pokes)
