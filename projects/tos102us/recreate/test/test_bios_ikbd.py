"""The ACIA handler @ $fc29ce — vector $118, the MFP channel the IKBD's 6850 and the MIDI 6850 share.

Its whole body is a loop over two vectors in RAM and a question to the MFP, so what a case here
stages is the two routines and what it declares is the MFP: GPIP bit 4 (is anybody still asserting?)
and the in-service register the handler acknowledges itself in.

WHAT THIS BATTERY DOES NOT REACH, and it is most of the keyboard: the two ROM routines the captured
machine really has in those slots ($fc29fc and $fc2a0c) read the 6850s' data ports and parse what
comes out — mouse, joystick, clock and status packets, and a scancode's way through the `Keytbl`
tables into the console IOREC. Every one of those reads pops the receive register, so a run needs a
declared SEQUENCE of bytes where the model has one per-run constant (os.h, `OS_HW_ACIA_DATA`). The
vectors are staged instead, and `test_the_captured_machine_has_the_rom_s_own_service_routines` is
what keeps the deferral checkable rather than invisible.

WHAT THE DECLARED SEQUENCE ADDED (TRAP_MODEL.md, Phase 16): the handler's LOOP. GPIP bit 4 used to
be a per-run constant here, so a case could declare the line idle (one pass) or asserted (a run that
never ends) and nothing in between; a list of `[asserted, idle]` is what drives the two-pass entry,
which is the shape the handler is a loop for. The packet drain out of `$fffc02` is the same model at
the address next door and is still deferred, for the reason above: it needs the ROM's own service
routines reconstructed, not a declaration.
"""
import ctypes
import struct

import pytest

import isr
from harness import addrs, emu, make_image, _lib

_lib.isr_acia.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
_lib.isr_acia.restype = None

MIDI_STUB = isr.STUB_BAND + 0x00
IKBD_STUB = isr.STUB_BAND + 0x10
DECOY_STUB = isr.STUB_BAND + 0x20
MARKS = isr.MARKS

MARK = isr.MARK
# GPIP bit 4 is ACTIVE LOW, so this is "neither 6850 wants anything more" and the loop makes one
# pass. Declared with every other bit set, so a reconstruction testing the wrong bit — or the whole
# byte — cannot pass by accident.
ACIA_LINE_IDLE = 0xFF
ISRB_HELD = 0xFF

# The ROM's own service routines, which this wave does not reconstruct. Named here rather than in
# `addrs.h` because nothing compiles against them: they are what the pin below reads out of the
# captured machine's KBDVECS.
ROM_MIDISYS, ROM_IKBDSYS = 0xFC29FC, 0xFC2A0C


marker_routine = isr.marker_routine


def set_register(opcode, value, at):
    """A staged routine that leaves `value` in one data register and marks itself — the only way to
    ask which registers the handler's own `movem.l` list really covers."""
    def effect(buf, _argument):
        buf[at] = MARK
    return struct.pack(">HI", opcode, value) + isr.store_byte(MARK, at) + isr.RTS, effect


MOVE_L_IMMEDIATE_D3 = 0x263C      # `move.l #<long>,d3` — inside the saved list
MOVE_L_IMMEDIATE_D4 = 0x283C      # ...and d4, which is outside it


def vectors(midi=MIDI_STUB, ikbd=IKBD_STUB):
    return {addrs.KBDVECS + addrs.KBDVECS_MIDISYS: struct.pack(">I", midi),
            addrs.KBDVECS + addrs.KBDVECS_IKBDSYS: struct.pack(">I", ikbd)}


def _glue(lib, buf):
    lib.isr_acia(buf)


def run(pokes=None, *, routines=None, gpip=ACIA_LINE_IDLE, isrb=ISRB_HELD, poison=True):
    if routines is None:
        routines = {MIDI_STUB: marker_routine(0), IKBD_STUB: marker_routine(1)}
    return isr.run(addrs.ISR_ACIA, _glue, pokes={**vectors(), **(pokes or {})},
                   routines=routines, poison=poison,
                   io_seed={addrs.MFP_GPIP: gpip, addrs.MFP_ISRB: isrb})


def test_the_vector_table_still_points_at_this_handler():
    assert isr.vector_in_snapshot(addrs.VECTOR_ACIA) == addrs.ISR_ACIA


def test_the_captured_machine_has_the_rom_s_own_service_routines():
    """What this wave defers, read out of the snapshot rather than described. KBDVECS' last two
    longwords hold the two ROM routines that read the 6850s; every case below replaces them, so this
    is what says WHAT is being replaced and keeps the deferral honest."""
    assert isr.vector_in_snapshot(addrs.KBDVECS + addrs.KBDVECS_MIDISYS) == ROM_MIDISYS
    assert isr.vector_in_snapshot(addrs.KBDVECS + addrs.KBDVECS_IKBDSYS) == ROM_IKBDSYS


def test_both_service_routines_are_called_once_each_in_the_rom_s_order():
    """MIDI first, then the IKBD — the order the ROM's two `movea.l`s have, and the one thing the
    candidate's own call list is compared on."""
    info = run()
    assert info["writes"][MARKS] == MARK and info["writes"][MARKS + 1] == MARK
    assert isr.CALLS == [(MIDI_STUB, isr.NO_ARGUMENT), (IKBD_STUB, isr.NO_ARGUMENT)]


def test_each_routine_is_the_one_its_own_kbdvecs_slot_names():
    """A DECOY in each slot's place in turn, which is what makes the two vectors inputs rather than
    two addresses the reconstruction remembers."""
    routines = {MIDI_STUB: marker_routine(0), IKBD_STUB: marker_routine(1),
                DECOY_STUB: marker_routine(2)}
    swapped = run({**vectors(midi=DECOY_STUB)}, routines=routines)
    assert swapped["writes"][MARKS + 2] == MARK and MARKS not in swapped["writes"]
    assert isr.CALLS == [(DECOY_STUB, isr.NO_ARGUMENT), (IKBD_STUB, isr.NO_ARGUMENT)]


@pytest.mark.parametrize("isrb", (0xFF, 0x40, 0xBF, 0x00, 0x5A))
def test_the_channel_is_acknowledged_with_every_other_channel_s_bit_kept(isrb):
    """`bclr #6,$fffa11` through the declared map (`include/mfp.h`): the other seven bits are seven
    other channels' in-service flags, and the byte stored is a function of what the case says the
    register held."""
    info = run(isrb=isrb)
    assert info["regs"]["hw_writes"] == [
        (addrs.MFP_ISRB, 1, isrb & ~(1 << addrs.MFP_ISRB_ACIA_BIT))]


@pytest.mark.parametrize("gpip", (0xFF, 0x10, 0x9A, 0x1F))
def test_the_loop_ends_when_the_mfp_says_neither_chip_is_asserting(gpip):
    """GPIP bit 4 ALONE, and it is ACTIVE LOW: `btst #4 / beq` goes round again while the bit is
    clear. Every byte here has bit 4 SET and differs everywhere else, so a reconstruction testing
    another bit, or the whole byte, does not end where this one does.

    $fffa01 is a Phase-7 NAMED slot, so its ordered read stream is `hw_events` and not the declared
    map's `io_events` — one door in the case (`io_seed`), two models behind it.
    """
    info = run(gpip=gpip)
    assert info["regs"]["hw_events"] == [(addrs.MFP_GPIP, gpip)]
    assert info["regs"]["io_events"] == [(addrs.MFP_ISRB, 1, ISRB_HELD)]


# The same byte with bit 4 CLEAR, and every other bit set: "one of the 6850s is still asserting".
ACIA_LINE_ASSERTED = 0xFF & ~(1 << addrs.MFP_GPIP_ACIA_BIT)
# ...and a cap far below what any case here runs to, so the refusal below is the LOOP and not a slow
# machine: a terminating pass of this handler is two staged `rts`es and a `bclr`.
SPIN_INSN_CAP = 5000


@pytest.mark.parametrize("line", (ACIA_LINE_ASSERTED, [ACIA_LINE_ASSERTED, ACIA_LINE_ASSERTED]),
                         ids=("a constant", "a list"))
def test_a_line_declared_still_asserted_spins_until_the_oracle_s_cap(line):
    """THE NEGATIVE CONTROL the four bytes above rest on, driven rather than described.

    A declaration that never says IDLE cannot end this loop, and the two shapes fail the same way:
    a per-run constant answers every round the same, and a LIST that runs out is served a refusal —
    which hands both cores 0, every bit clear, which this loop reads as "still asserting". Without
    this, every case above would be compatible with a handler that made one pass unconditionally and
    never asked the MFP at all.

    SO A READ PAST THE END IS NOT REACHABLE AS A RED FROM THIS ROUTINE, and that is a fact about the
    handler rather than a gap in the model: the loop's only exit IS the read, so a case that
    under-declares it never gets to the `rts` where a refusal would be reported. What both shapes
    produce instead is the honest failure — loud, on the ORACLE, at its instruction cap. The refusal
    itself is pinned where a routine reads a fixed number of times
    (`tools/recreate_kit/test/test_io_differential.py`).

    It runs the ORIGINAL alone, because the candidate is host C with no instruction cap of its own:
    the same declaration is an endless loop in the `.so`, which is what `ikbd.c`'s host-only pass
    bound turns into a red rather than a hung worker.
    """
    image = make_image(isr.case_pokes(addrs.ISR_ACIA, routines={
        MIDI_STUB: marker_routine(0), IKBD_STUB: marker_routine(1)}, pokes=vectors()))
    with pytest.raises(Exception) as raised:
        emu.run(image, isr.TRAMPOLINE_AT[addrs.ISR_ACIA], isr.DIRTY_REGISTERS,
                max_insns=SPIN_INSN_CAP,
                io_seed={addrs.MFP_GPIP: line, addrs.MFP_ISRB: ISRB_HELD})
    assert str(SPIN_INSN_CAP) in str(raised.value) or "cap" in str(raised.value).lower(), (
        f"the handler ended for a reason other than the instruction cap: {raised.value}")


def test_the_line_is_asked_about_exactly_once_per_pass():
    """One read per pass, and this case declares ONE BYTE, so it describes one pass: `btst #4,$fffa01`
    is re-executed on every round of the loop, and a run that went round twice would read it twice.
    The two-pass case below is the same claim from the other side."""
    assert len(run()["regs"]["hw_events"]) == 1


# ---- the TWO-PASS entry, which only a declared SEQUENCE can drive --------------------------------
# GPIP bit 4 is ACTIVE LOW and the handler asks the MFP after EVERY pass, so a two-pass entry reads
# $fffa01 asserted and then idle. One per-run constant cannot say that — declared low the loop never
# ends and declared high it describes one pass — which is what the DECLARED SEQUENCE model exists
# for (TRAP_MODEL.md, Phase 16). $fffa01 is a Phase-7 NAMED SLOT and the list goes through the same
# `io_seed` door a byte does; `emu.seed_split` routes it, and the reads come back in `hw_events`.
TWO_PASS_LINE = [ACIA_LINE_ASSERTED, ACIA_LINE_IDLE]


def test_a_second_pass_runs_both_service_routines_again_in_the_rom_s_order():
    """THE SHAPE THIS BATTERY COULD NOT REACH BEFORE. A byte that arrives while the first pass is
    running is serviced by the second — that is the whole reason the handler is a loop rather than
    two calls — and the claim is the CALL LIST: MIDI, IKBD, MIDI, IKBD, each vector RE-READ from
    KBDVECS on its own pass (`ikbd.c`), so a routine that replaced its own would be answered from
    the next round.
    """
    info = run(gpip=TWO_PASS_LINE)
    assert isr.CALLS == [(MIDI_STUB, isr.NO_ARGUMENT), (IKBD_STUB, isr.NO_ARGUMENT),
                         (MIDI_STUB, isr.NO_ARGUMENT), (IKBD_STUB, isr.NO_ARGUMENT)]
    assert info["writes"][MARKS] == MARK and info["writes"][MARKS + 1] == MARK


def test_the_two_passes_ask_the_mfp_twice_and_are_answered_the_list_in_order():
    """...and the reads themselves, which is the only surface a `btst` leaves: two entries in the
    NAMED SET's ledger — not the declared map's — because `$fffa01` is Phase 7's address however the
    case spelled the declaration. A reconstruction that asked once and looped on a remembered answer
    produces one entry and reds.
    """
    info = run(gpip=TWO_PASS_LINE)
    assert info["regs"]["hw_events"] == [(addrs.MFP_GPIP, ACIA_LINE_ASSERTED),
                                         (addrs.MFP_GPIP, ACIA_LINE_IDLE)]
    assert info["regs"]["io_events"] == [(addrs.MFP_ISRB, 1, ISRB_HELD)], (
        "the list leaked into the declared map's ledger, so one byte is being served by two models")


def test_the_channel_is_acknowledged_ONCE_however_many_passes_the_entry_took():
    """`bclr #6,$fffa11` is past the loop, not inside it. A reconstruction that acknowledged per pass
    writes the register twice, which only the hardware WRITE ledger can see — the second store is of
    the same byte, so the image and every other surface agree."""
    info = run(gpip=TWO_PASS_LINE)
    assert info["regs"]["hw_writes"] == [
        (addrs.MFP_ISRB, 1, ISRB_HELD & ~(1 << addrs.MFP_ISRB_ACIA_BIT))]




# The exact `movem.l d0-d3/a0-a3/a5` list, asked of the two registers that straddle its edge. THE
# ORACLE'S CLAIM ALONE (`isr.assert_registers_survived` says why), and the sharpest one available:
# a handler that saved "all the registers" would give D4 back too, and a caller of this one must not
# expect it to.
A_VALUE = 0x1234_5678


def test_a_service_routine_s_clobber_of_a_saved_register_does_not_escape():
    info = run(routines={MIDI_STUB: set_register(MOVE_L_IMMEDIATE_D3, A_VALUE, MARKS),
                         IKBD_STUB: marker_routine(1)})
    assert info["regs"]["d3"] == isr.DIRTY_REGISTERS["d3"]


def test_a_service_routine_s_clobber_of_an_unsaved_register_does():
    """D4 is outside the ROM's `movem` list, so the interrupted program gets it back CHANGED — which
    is a fact about the handler's contract and not a defect: the two service routines it calls are
    the ROM's own, and they keep to that list."""
    info = run(routines={MIDI_STUB: set_register(MOVE_L_IMMEDIATE_D4, A_VALUE, MARKS),
                         IKBD_STUB: marker_routine(1)})
    assert info["regs"]["d4"] == A_VALUE


def test_the_handler_gives_back_every_register_it_saved():
    saved = {name: value for name, value in isr.DIRTY_REGISTERS.items()
             if name in ("d0", "d1", "d2", "d3", "a0", "a1", "a2", "a3", "a5")}
    isr.assert_registers_survived(run(), saved)


# ---- the cases this battery REGISTERS -----------------------------------------------------------
# TWO, because the handler has two shapes and both are now reachable: one pass, and the loop's second
# round. The second used to be unreachable from a case — GPIP bit 4 was a per-run constant, so a
# declaration could say "idle" or say "asserted for ever" and nothing in between — and the DECLARED
# SEQUENCE is what made it a case (TRAP_MODEL.md, Phase 16).
REGISTERED = (
    {"name": "isr_acia, one pass", "entry": addrs.ISR_ACIA,
     "pokes": vectors(),
     "routines": {MIDI_STUB: marker_routine(0), IKBD_STUB: marker_routine(1)},
     "io_seed": {addrs.MFP_GPIP: ACIA_LINE_IDLE, addrs.MFP_ISRB: ISRB_HELD}},
    # ...and the TWO-PASS entry, which is a second SHAPE rather than a longer run of the first: the
    # loop's second round re-reads both KBDVECS vectors and calls both routines again, and it is
    # reachable only through a declared SEQUENCE (TRAP_MODEL.md, Phase 16). Before that model it was
    # not a case at all, so the handler's cost was priced over the arm a per-run constant could
    # describe and the loop's own cost was measured by nothing.
    {"name": "isr_acia, two passes", "entry": addrs.ISR_ACIA,
     "pokes": vectors(),
     "routines": {MIDI_STUB: marker_routine(0), IKBD_STUB: marker_routine(1)},
     "io_seed": {addrs.MFP_GPIP: TWO_PASS_LINE, addrs.MFP_ISRB: ISRB_HELD}},
)
VERIFIED_CASES = tuple(isr.registered(spec) for spec in REGISTERED)
# ...and the same case as a WHOLE-HANDLER one: `src/bios/isr.S`'s bracket — the `movem` pair whose
# list IS this handler's contract — held to the image, the WHOLE register file and the chip
# (`isr.transcribed`). Its frame is already in the band the diff drops.
TRANSCRIBED = REGISTERED
TRANSCRIPTION_CASES = tuple(isr.transcribed(spec) for spec in TRANSCRIBED)


@pytest.mark.parametrize("spec", REGISTERED, ids=lambda spec: spec["name"])
def test_every_registered_case_is_one_this_battery_proves(spec):
    """The row and the differential are the SAME spec (`isr.registered` / `isr.run_spec`)."""
    isr.run_spec(spec, _glue)


def test_the_stub_at_the_vector_is_the_rom_s_own_bytes():
    """`src/bios/isr.S`'s ACIA stub against the ROM's own words — the `movem` pair, which is the
    whole of the stub: everything this handler does is inside it, so the C core it calls is the
    whole of `isr_acia`."""
    isr.assert_the_stub_is_the_rom_s_bytes("ISR_ACIA")
