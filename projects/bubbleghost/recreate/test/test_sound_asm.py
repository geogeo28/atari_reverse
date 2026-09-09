"""The C-vs-ASM differential for the 200 Hz tick — `../src/asm/sound_tick.S` against `../src/sound.c`.

    original  ==(test_sound.py)==  timer_c_sound_isr  ==(this file)==  timer_c_sound_isr_asm

Both links are exact over the same two surfaces — the WHOLE image, and the ordered YM2149 access
ledger — so the twin is pinned to the original transitively without a second oracle run. The C core
stays the reference: it is what the oracle verified, and nothing here re-derives what it should do.

WHAT MAKES THIS FILE'S COVERAGE THE C BATTERY'S OWN. `test_sound.py::isr_case` calls
`assert_twin_matches_the_c` for EVERY case it stages — thirteen batteries, two of them fuzzes and
one of them all 47 shipped definitions — so the twin is compared on exactly the cases the C was
verified on rather than on a second, smaller list somebody would have had to keep in step.
`test_the_c_battery_runs_the_twin` is what stops those calls going quietly missing; the batteries
here are the ones about the TWIN rather than about the engine — the transcription against the .PRG's
own bytes, the cost of the code around it, the frame the interrupt entry reads back, and the two
controls that say the comparison is not vacuous.

THE CHIP NEEDS NO CALLBACK DOOR, and that is why this suite can compare cycles at all. The twin
writes $ffff8800/$ffff8802 with the original's own `move.b` pairs, and the kit's oracle decodes
those two ports in its memory callback (`tools/recreate_kit/oracle/shim.c`, `m68k_write_memory_8`)
— so a twin run leaves its register writes in the ORACLE's PSG ledger while the C core's
`psg_port_write` leaves them in the CANDIDATE's, and the two streams are compared here. One
spelling serves both builds: what this differential runs is instruction-for-instruction what the
machine runs.
"""
import functools
import re
from pathlib import Path

import pytest

import abi
import harness
import emu
import loader
from harness import report

from recreate_kit.asm_twin import AsmTwins

# The twin, and the C core it stands in for.
TWIN = "timer_c_sound_isr_asm"
# The transcribed span: [0x145be, 0x148d6) of the original — the whole per-voice loop plus the three
# duration counters read back at the end. What lies outside it, on both sides, is in
# `../src/asm/sound_tick.S`'s header comment.
ORIGINAL_BODY = (0x145be, 0x148d6)

# The bar the twin is held to, as a fraction of what the ORIGINAL's own handler costs for the same
# case. It is UNDER 1.0 because the twin does strictly less around the same body: a C function saves
# the callee-saved half of the register set a vector handler must save whole, and the two `sr`
# instructions the original spends dropping to IPL 5 have no counterpart here. That is a FLAT 86
# cycles a call, so a bar at 1.0 would have handed a translation defect 2-14% of free headroom
# depending on the case — measured 2026-09-08, on Musashi's counter, over the four staged shapes:
#
#     idle 450/522 = 0.8621x   one voice 1514/1600 = 0.9463x
#     three voices 3706/3792 = 0.9773x   key-off 4450/4536 = 0.9810x
#
# The bar sits just above the worst of them. ../STATUS.md, "Performance", wave 5b, carries the rest.
COST_BAR = 0.99

_TWINS = None


def twins():
    """The assembled blob, loaded once per worker. `AsmTwins.require()` raises with the build
    command if it was never assembled — LOUD rather than skipped, since a skip would look like
    coverage."""
    global _TWINS
    if _TWINS is None:
        _TWINS = AsmTwins(Path(__file__).resolve().parents[1] / "build" / "asm", loader.IMAGE_SIZE)
    return _TWINS


def _run_the_c(image, ticks):
    """`ticks` ticks of the C core over a copy of `image` — (the image it left, its PSG stream).

    THE CTYPES SIGNATURES ARE `test_sound.py`'S, and importing it is what installs them. `getattr`
    on a CDLL hands back an object CACHED per library for the whole process, so a second `argtypes`
    assignment for the same symbol is a second spelling of it that wins or loses by import order —
    the hazard `tools/recreate_kit/asm_twin.py::_bind_callbacks` carries the same note about.
    """
    import test_sound                                                              # noqa: F401
    buf = harness.candidate_image(image)
    harness.arm_candidate()
    # ...`_ticks` for one tick too: `../src/sound.c`'s glue is a `for` around the same call, so a
    # `ticks == 1` branch here would be a second spelling of the same run.
    harness._lib.g_timer_c_sound_isr_ticks(buf, ticks)
    return bytes(buf), harness.candidate_psg_events()


def _run_the_asm(image, ticks):
    """The same `ticks` ticks of the twin — (the image it left, its PSG stream).

    One `call` per tick, because that is what the C's multi-tick glue does: a loop around the same
    entry, each tick starting from the image the last one left. The oracle resets its PSG ledger per
    run, so the stream is accumulated here to be the whole of what the C's one call logged. What a
    tick COSTS is not reported: the cost battery clocks a single call of its own, where "the cycles"
    is one number rather than a list nobody sums.
    """
    events = []
    for _ in range(ticks):
        run = twins().call(image, TWIN)
        image = run.image
        events += emu.psg_events()
    return image, events


def assert_twin_matches_the_c(pokes, ticks=1):
    """THE DIFFERENTIAL: the twin and its C core over one staged image, compared whole.

    Called by `test_sound.py::isr_case` for every case that file stages, and by the batteries below.
    `pokes` is that case's own poke map, so the two sides run on the identical staged memory.
    """
    image = harness.make_image(pokes)
    c_image, c_events = _run_the_c(image, ticks)
    asm_image, asm_events = _run_the_asm(image, ticks)

    # THE POSITIVE CONTROL, and it is what stops a twin that is a bare `rts` passing. Two identical
    # images prove nothing when neither side wrote one, and every tick of this handler writes at
    # least the conterm byte — `isr_case` stages it as `conterm ^ 0xff`, so the entry clear moves it
    # on every case there is. A case that ever stops changing the image is staged wrong.
    assert c_image != bytes(image), (
        f"the C core wrote nothing to the image over {ticks} tick(s), so comparing {TWIN} against "
        f"it tests nothing — the case is staged wrong, or the glue was never called")

    if asm_image != c_image:
        diffs = [(addr, c_image[addr], asm_image[addr])
                 for addr in range(len(c_image)) if c_image[addr] != asm_image[addr]]
        pytest.fail(f"{TWIN} diverges from the C core in {len(diffs)} byte(s) over {ticks} tick(s) "
                    f"(C, then asm)\n{report(diffs)}")
    assert asm_events == c_events, (
        f"{TWIN} and the C core drove the chip differently over {ticks} tick(s) — the image is "
        f"identical and only this ledger can see it (register, value in order)\n"
        f"  C   {_psg_text(c_events)}\n  asm {_psg_text(asm_events)}")


def _psg_text(events):
    return " ".join(f"r{reg}={value:#04x}" for _kind, reg, value in events) or "(nothing)"


# =================================================================================================
# The transcription: the assembled body IS the original's machine code
# =================================================================================================

def test_asm_body_transcribes_the_original():
    """The 792 bytes between `timer_c_sound_isr_body` and `..._body_end` are the .PRG's own
    0x145be..0x148d6.

    Not "computes the same thing" — the same machine code. This is what turns "it cannot cost more
    than the original" from a claim into a measurement, and it is why the differential above is
    allowed to be the only behavioural check on 262 hand-written instructions: an edit that computes
    the right answer by different instructions still fails here.
    """
    blob = twins()
    lo, hi = blob.entry("timer_c_sound_isr_body"), blob.entry("timer_c_sound_isr_body_end")
    assert hi > lo, "empty body bracket — the two labels are in the wrong order"
    mine = blob.bin.read_bytes()[lo:hi]
    theirs = bytes(harness.BASE_IMAGE[ORIGINAL_BODY[0]:ORIGINAL_BODY[1]])
    assert len(mine) == len(theirs), (
        f"the twin's body is {len(mine)} bytes and the original's span {len(theirs)} — one of the "
        f"two brackets has moved")
    assert mine == theirs, (
        f"the body is not a transcription of the original @ {ORIGINAL_BODY[0]:#x}\n"
        f"  twin     {mine.hex()}\n  original {theirs.hex()}")


def test_the_twin_never_stores_through_its_own_frame():
    """The eleven instructions OUTSIDE the transcribed span may read `%sp` once and never write it.

    `bg_timer_c_entry` pops the image base back off the stack after the call rather than re-reading
    `bg_image_base`, which is only safe because this callee treats its incoming argument slot as
    read-only — the m68k SysV ABI does not require that of a callee, and GCC's version of this
    handler was the reason the base used to be read twice (`atari/bubble_os.s`, the Timer C entry).
    The transcription pin does not hold it: the prologue and the epilogue are exactly the bytes
    OUTSIDE its bracket. So it is asserted here, over the source, where a spill added to the
    prologue would otherwise mirror a byte from a garbage address into TOS's $484 two hundred times
    a second — a machine write no differential and no screenshot can see.
    """
    source = (Path(__file__).resolve().parents[1] / "src" / "asm" / "sound_tick.S").read_text()
    head, _, rest = source.partition(f"\n{TWIN}:\n")
    assert rest, f"src/asm/sound_tick.S no longer defines {TWIN} at the start of a line"
    prologue, _, body = rest.partition("\ntimer_c_sound_isr_body:")
    epilogue = body.partition("\ntimer_c_sound_isr_body_end:")[2]
    assert prologue and epilogue, "the body's two bracket labels are gone or in the wrong order"
    # `%a7` IS `%sp` — one register, two spellings the assembler takes equally — so a spill written
    # the other way would slip past a scan for one of them. Comment lines are stripped first, and
    # the comment column with them: this is about instructions.
    stack = [line for line in (prologue + epilogue).splitlines()
             if not line.lstrip().startswith(("/*", "*", "|"))
             and re.search(r"%sp|%a7", line.split("|")[0])]
    assert len(stack) == 3, (
        f"src/asm/sound_tick.S names the stack pointer on {len(stack)} instruction(s) outside its "
        f"transcribed body; this suite knows three — the two `movem`s and the one `movea.l "
        f"20(%sp)` that reads the image base:\n" + "\n".join(stack))
    assert re.match(r"\s*movea\.l\s+20\(%(sp|a7)\),%a3", stack[1]), (
        f"the argument load is not the middle of the three stack instructions any more:\n"
        + "\n".join(stack))


# =================================================================================================
# Staging — the four shapes the cost and control batteries need
# =================================================================================================

def _isr_pokes(records, conterm=0x8f):
    """One tick's staged memory: the ISR state block, the conterm byte and three voice records.

    Built from `test_sound.py`'s own builders rather than beside them, so a record layout that moves
    moves in one place. The chain vector is the harness sentinel, which is where the handler's
    closing `rts` lands on the ORACLE side — the cost battery below runs the original itself.
    """
    import test_sound
    return abi.merge_pokes(test_sound.isr_state(emu.SENTINEL, conterm),
                           {test_sound.TOS_CONTERM: bytes([conterm ^ 0xff])},
                           test_sound.voice_records(records))


# Named rather than parametrized over the pokes themselves, because building them imports
# `test_sound` — and that file imports THIS one, so a case list built at import time would reach it
# half-initialised. The lookup happens inside a test, by which point both modules are whole.
CASE_NAMES = ("idle", "three voices", "one voice", "key-off")


@functools.lru_cache(maxsize=None)
def _staged_cases():
    """{name: pokes} for the cases the cost and control batteries run: one idle, and three shapes of
    armed voice that between them reach all five of the handler's chip writes."""
    import test_sound
    sounding = {
        test_sound.SND_VC_TONE_PERIOD: (2, 478),
        test_sound.SND_VC_NOISE_PERIOD: (2, 12),
        test_sound.SND_VC_VOLUME_INDEX: (2, 12),
        test_sound.SND_VC_VOL_PHASE: (2, 1),
        test_sound.SND_VC_VOL_ATTACK_STEP: (4, 0x1000),
        test_sound.SND_VC_PITCH_PHASE: (2, 1),
        test_sound.SND_VC_PITCH_STEP1: (4, 0x2000),
        test_sound.SND_VC_PITCH_TARGET1: (4, 0x40000),
        test_sound.SND_VC_NOISE_PHASE: (2, 1),
        test_sound.SND_VC_NOISE_STEP1: (4, 0x2000),
        test_sound.SND_VC_NOISE_TARGET1: (4, 0x40000),
    }
    idle = [test_sound.idle_record() for _ in range(test_sound.SND_VOICES)]
    armed = [test_sound.armed_record(40, sounding) for _ in range(test_sound.SND_VOICES)]
    one_voice = [test_sound.armed_record(40 if v == 0 else 0, sounding)
                 for v in range(test_sound.SND_VOICES)]
    # Duration 1 is the key-off tick — `armed_record` opens with the gate negative, so the counter
    # runs, reaches zero here, frees the voice and takes the three release phases with it.
    keying_off = [test_sound.armed_record(1, sounding) for _ in range(test_sound.SND_VOICES)]
    return dict(zip(CASE_NAMES, (_isr_pokes(idle), _isr_pokes(armed),
                                 _isr_pokes(one_voice), _isr_pokes(keying_off))))


# =================================================================================================
# The cost, and the two controls
# =================================================================================================

@pytest.mark.parametrize("name", CASE_NAMES)
def test_asm_tick_costs_no_more_than_the_original(name):
    """Both sides clocked by ONE instrument — Musashi's cycle counter over one entry — so the ratio
    is a like-for-like reading and not two runs of different lengths compared.

    WHAT IT GUARDS IS THE SETUP AND TEARDOWN, and saying so is the point: a costly instruction
    INSIDE the transcribed span reddens `test_asm_body_transcribes_the_original` first and can never
    reach here, because that span is the original's own bytes. What varies is the eleven-instruction
    prologue and the three-instruction epilogue around it — the only code in the file anyone can
    write freely — and the bar is set from their measured cost rather than from parity with a
    handler that does strictly more (see COST_BAR).
    """
    import test_sound
    image = harness.make_image(_staged_cases()[name])
    _final, _writes, out_regs = emu.run(image, test_sound.ENTRY_TIMER_C_SOUND_ISR,
                                        regs={"a4": abi.A4_BASE})
    original = out_regs["cycles"]
    twin = twins().call(image, TWIN).cycles
    assert twin <= COST_BAR * original, (
        f"{name}: the twin costs {twin} cycles against the original's {original} "
        f"({twin / original:.4f}x), over its {COST_BAR}x bar — find what the prologue or the "
        f"epilogue gained, do not raise the bar")


@pytest.mark.parametrize("name", CASE_NAMES)
def test_asm_tick_matches_the_c_on_the_staged_cases(name):
    """The differential over the four staged shapes, so this file is not purely parasitic on
    `test_sound.py`'s batteries — a case list here fails on its own if the wiring below is what
    broke."""
    assert_twin_matches_the_c(_staged_cases()[name], ticks=4)


def test_the_psg_ledger_comparison_is_not_vacuous():
    """A staged case must actually DRIVE THE CHIP, or comparing two empty ledgers proves nothing.

    The engine's whole off-image output is those writes: an idle tick makes none, so a suite whose
    cases were all idle would compare the image, find it identical, and vouch for a twin that never
    wrote a register.
    """
    pokes = _staged_cases()["three voices"]
    _image, events = _run_the_c(harness.make_image(pokes), 1)
    assert events, "the C core drove no PSG register on the 'three voices' case — restage it"
    assert len({reg for _kind, reg, _value in events}) >= 4, (
        f"only {len({reg for _kind, reg, _value in events})} distinct register(s) written; the "
        f"three writes a sounding voice makes are volume, the tone pair and the noise period")


def test_the_c_battery_runs_the_twin():
    """`test_sound.py::isr_case` must call this file, because that call IS this suite's coverage.

    Losing it would leave every battery in that file green, every battery in this one green, and the
    twin compared on four staged cases instead of on the engine's whole verified corpus — which is
    exactly the shape of a check that has stopped checking and still reports a clean run.
    """
    # COMMENT LINES STRIPPED FIRST. `# test_sound_asm.assert_twin_matches_the_c(...)` satisfies a
    # raw substring scan while every battery in both files goes green having compared nothing —
    # which is the exact shape this test exists to refuse.
    source = "\n".join(line for line in
                       (Path(__file__).resolve().parent / "test_sound.py").read_text().splitlines()
                       if not line.lstrip().startswith("#"))
    body = source.split("def isr_case(")[1].split("\ndef ")[0]
    assert "assert_twin_matches_the_c(" in body, (
        "test_sound.py's isr_case no longer calls assert_twin_matches_the_c, so none of its ISR "
        "cases reach src/asm/sound_tick.S — see this file's docstring")
    # ...and the one ISR battery that stages its own pokes rather than going through `isr_case`.
    # It is the case that relocates the record base, which is the only thing that exercises the
    # twin's two image-relative pointer loads — the arithmetic the transcription pin does not cover.
    assert source.count("assert_twin_matches_the_c(") == 2, (
        f"test_sound.py calls assert_twin_matches_the_c "
        f"{source.count('assert_twin_matches_the_c(')} time(s); this suite knows two — `isr_case`, "
        f"and `test_isr_reads_its_pointers_out_of_the_state_block`, which stages its own pokes")
