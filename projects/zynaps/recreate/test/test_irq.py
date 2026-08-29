"""Differential tests for the three VBL/Timer-B handler pairs (src/irq.c).

EVERY ONE OF THEM RETURNS WITH `rte`, not `rts`, so each case enters through `abi.interrupt_frame_pokes`
— a stub that pushes the 68000 exception frame the handler pops and lands its `rte` on an ordinary
`rts`. The frame itself is inside the stack-guard band the differential drops.

WHAT THESE CASES DO AND DO NOT HOLD. The flags, countdowns, shadow palette and colour-bar list are
in the image and fully compared, and `sound_tick`'s chip traffic is compared through the kit's PSG
ledger. The shifter (`$ff8240..`) and MFP (`$fffa0f`) stores are outside the image: the oracle drops
them and the candidate makes none, so no case here can fail on them. include/irq.h says why and
STATUS.md's rows say so per handler.
"""
import ctypes
import random

import pytest

import abi
import harness
from harness import differential, report

ENTRY_VBL_ISR = 0x10776
ENTRY_TIMER_B_ISR = 0x10782
ENTRY_VBL_ISR_TITLE = 0x106a2
ENTRY_TIMER_B_RASTER_ISR = 0x106ae
ENTRY_ATTRACT_VBL_ISR = 0x12c9e
ENTRY_ATTRACT_RASTERBAR_ISR = 0x12cc0
ENTRY_VBL_MENU = 0x13c26
ENTRY_IKBD_ACIA_ISR = 0x14456

A_VSYNC_FLAG = 0x198ab            # mirror of include/irq.h
A_PALETTE_HW_SHADOW = 0x18fc4
A_PALETTE_CYCLE_WORDS = 0x18fd0
A_PALETTE_SWAP_LONG = 0x18fda
A_PALETTE_SWAP_COUNTDOWN = 0x19683
A_PALETTE_ROTATE_COUNTDOWN = 0x19684
A_ATTRACT_RASTER_LINE = 0x19f22
A_ATTRACT_RASTER_LIST_PTR = 0x19f24
A_ATTRACT_RASTER_LIST = 0x1a976
PALETTE_PENS = 16
PALETTE_CYCLE_WORDS = 5
PALETTE_SWAP_PERIOD = 8
PALETTE_ROTATE_PERIOD = 4
ATTRACT_BAR_FIRST_LINE = 1
ATTRACT_BAR_LAST_LINE = 0x27
A_IKBD_PACKET_PTR = 0x195d4       # mirrors of include/irq.h's ACIA block
A_IKBD_PACKET_REMAINING = 0x19671
A_IKBD_JOYSTICK_STATE = 0x19680
A_KEY_SCANCODE = 0x19685
IKBD_JOYSTICK_HEADER = 0xfd
IKBD_JOYSTICK_PACKET_BYTES = 2
ACIA_STATUS_IRQ = 0x80
ACIA_STATUS_RX_FULL = 0x01
KEY_RELEASE_BIT = 0x80
MFP_GPIP_ACIA_IDLE = 0x10
A_MENU_PALETTE = 0x19f46
A_VBL_WAIT_FLAG = 0x198a7
A_RASTER_PHASE = 0x198a8
RASTER_PHASE_PERIOD = 2

# A case here arms a voice so that the sound tick does REAL work — without it every voice is
# disabled and the tick is eleven register pushes and the noise sweep. Both the record builder and
# the tune-stream lookup are IMPORTED from test_sound.py rather than restated: they describe another
# subsystem's record, and a second copy here would be a second thing to keep right. If an offset
# moved, this file would go on poking the old one, the voice would simply never be enabled, and
# every case below would stay green having verified nothing. test_sound.py's own MIRRORS is what
# pins them to `include/sound.h`.
from test_sound import TUNE_BOOT_NUMBER, tune_stream, voice_pokes         # noqa: E402

# ...and the ACIA's two port addresses from the battery that already owns them. They are the KIT's
# constants (`OS_HW_ACIA_STATUS` / `OS_HW_ACIA_DATA` in tools/recreate_kit/include/os.h), not this
# project's, so `test_constants.py`'s MIRRORS cannot pin them to an include/ header — importing the
# one Python spelling is what keeps there from being two.
from test_input import HW_ACIA_DATA, HW_ACIA_STATUS                       # noqa: E402

# The MFP's GPIP is the kit's too, and `ikbd_acia_isr` is the first routine here to read it.
# `test_the_hardware_addresses_are_the_models_own` below pins all three against emu.HW_ADDRS.
HW_MFP_GPIP = 0xfffa01

for _name in ("g_vbl_isr", "g_timer_b_isr", "g_vbl_isr_title", "g_timer_b_raster_isr",
              "g_attract_vbl_isr", "g_attract_rasterbar_isr", "g_vbl_menu", "g_ikbd_acia_isr"):
    getattr(harness._lib, _name).argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    getattr(harness._lib, _name).restype = None


def _armed_voice_pokes():
    """Voice 1 armed on the in-game tune, exactly as sound_start would leave it.

    Poked rather than run, because the interrupt stub has no room for a `jsr sound_start` — and the
    arming itself is test_sound.py's to verify, not this battery's.
    """
    return voice_pokes(stream=tune_stream(TUNE_BOOT_NUMBER))


def _isr_case(entry, glue_name, pokes=None, poison=False):
    frame = abi.interrupt_frame_pokes(entry)
    frame.update(pokes or {})
    diffs, _ = differential(abi.STUB, {"_pokes": frame},
                            lambda lib, buf: getattr(lib, glue_name)(buf), poison=poison)
    assert not diffs, f"{glue_name}\n{report(diffs)}"


# =================================================================================================
# The in-game pair — 0x10776 / 0x10782
# =================================================================================================

@pytest.mark.parametrize("flag", (0, 1, 0xff))
def test_vbl_isr(flag):
    """Clear the sync flag, then run the sound driver. The flag is swept because the clear is a
    `clr.b` over whatever the frame loop last set, and a candidate that only cleared it when it was
    already set would agree on one of these values."""
    _isr_case(ENTRY_VBL_ISR, "g_vbl_isr", {A_VSYNC_FLAG: bytes([flag])})


def test_vbl_isr_with_a_voice_playing():
    """The same handler with the in-game tune armed, so the tick fetches a row, sets a period and
    pushes eleven registers the PSG ledger compares."""
    pokes = _armed_voice_pokes()
    pokes[A_VSYNC_FLAG] = b"\x01"
    _isr_case(ENTRY_VBL_ISR, "g_vbl_isr", pokes)


# NO POISON PASS ON THE TWO HANDLERS THAT TICK THE SOUND DRIVER (this one and the attract VBL).
# Measured, not assumed: with `poison=True` both fail inside the driver at psg_reg_shadow+1, because
# the tick's outputs include the modulation counters and the tune cursor, which are also its control
# flow — pre-inverting them sends the two cores down different arms. test_sound.py carries the same
# note over the routines themselves. What holds these two instead is that every flag and pointer a
# case drives is SEEDED with a value the handler cannot produce (0x1234, 0xdeadbeef, 0x01), so a
# candidate that failed to write one leaves the seed standing on the plain pass.


@pytest.mark.parametrize("flag", (0, 1, 0xff))
def test_timer_b_isr(flag):
    """The same flag, no sound, and an MFP acknowledge the image cannot hold — so the flag is the
    whole of what this case compares, and STATUS.md's row says so."""
    _isr_case(ENTRY_TIMER_B_ISR, "g_timer_b_isr", {A_VSYNC_FLAG: bytes([flag])})


# =================================================================================================
# The title pair — 0x106a2 / 0x106ae
# =================================================================================================

def test_vbl_isr_title():
    """Sound, then pen 0 blanked. The blanking is off-image, so what this holds is the tick."""
    _isr_case(ENTRY_VBL_ISR_TITLE, "g_vbl_isr_title", _armed_voice_pokes())


def _raster_pokes(swap_countdown, rotate_countdown, seed=0):
    """The shadow palette seeded with distinct words, plus the two countdowns.

    DISTINCT WORDS ARE THE POINT: the cycle rotates five of them and swaps the halves of a sixth, so
    over a shadow of equal words — or of zeroes, which is what the .PRG ships for most pens — both
    machines would be invisible.
    """
    rng = random.Random(seed)
    shadow = bytearray(rng.randbytes(2 * PALETTE_PENS))
    return {
        A_PALETTE_HW_SHADOW: bytes(shadow),
        A_PALETTE_SWAP_COUNTDOWN: bytes([swap_countdown]),
        A_PALETTE_ROTATE_COUNTDOWN: bytes([rotate_countdown]),
    }


@pytest.mark.parametrize("swap", (1, 2, 0))
@pytest.mark.parametrize("rotate", (1, 2, 0))
def test_timer_b_raster_isr(swap, rotate):
    """Both colour cycles, at and either side of the frame they fire on.

    A countdown of 0 is the wrap arm: `subq.b` takes it to 0xff, which is not zero, so it does NOT
    fire — it waits another 255 frames. That is the case an `if (--n <= 0)` reconstruction would
    get wrong, and the only one that separates the two readings.
    """
    _isr_case(ENTRY_TIMER_B_RASTER_ISR, "g_timer_b_raster_isr",
              _raster_pokes(swap, rotate, seed=swap * 4 + rotate))


def test_timer_b_raster_isr_reloads_its_countdowns():
    """After firing, each countdown is reloaded with its own period — 8 for the swap and 4 for the
    rotate — so a candidate that reloaded both from one constant differs on one of them."""
    assert PALETTE_SWAP_PERIOD != PALETTE_ROTATE_PERIOD, (
        "the two periods must differ or this case cannot tell them apart")
    _isr_case(ENTRY_TIMER_B_RASTER_ISR, "g_timer_b_raster_isr", _raster_pokes(1, 1, seed=7))


def test_timer_b_raster_isr_attribution():
    """Poison the countdowns, the five cycle words and the swap long."""
    _isr_case(ENTRY_TIMER_B_RASTER_ISR, "g_timer_b_raster_isr", _raster_pokes(1, 1, seed=3),
              poison=True)


# =================================================================================================
# Attract mode — 0x12c9e / 0x12cc0
# =================================================================================================

def test_attract_vbl_isr():
    """Line back to 0, sync flag cleared, list cursor rewound to the band's start."""
    pokes = _armed_voice_pokes()
    pokes[A_ATTRACT_RASTER_LINE] = b"\x12\x34"
    pokes[A_ATTRACT_RASTER_LIST_PTR] = b"\xde\xad\xbe\xef"
    pokes[A_VSYNC_FLAG] = b"\x01"
    _isr_case(ENTRY_ATTRACT_VBL_ISR, "g_attract_vbl_isr", pokes)


# No poison pass here either — see the note under test_vbl_isr, which is the same driver and the
# same measured reason.


# A colour-bar list: {count, colour} word pairs. The counts are small and DIFFERENT so that one
# scanline retires the first pair and the next does not retire the second.
BAR_LIST = bytes.fromhex("0001 0700 0003 0070 0002 0007".replace(" ", ""))


def _bar_pokes(line, cursor_offset=0, list_bytes=BAR_LIST):
    return {
        A_ATTRACT_RASTER_LINE: line.to_bytes(2, "big"),
        A_ATTRACT_RASTER_LIST_PTR: (A_ATTRACT_RASTER_LIST + cursor_offset).to_bytes(4, "big"),
        A_ATTRACT_RASTER_LIST: list_bytes,
    }


@pytest.mark.parametrize("line", (0, 1, 2, ATTRACT_BAR_LAST_LINE - 2, ATTRACT_BAR_LAST_LINE - 1,
                                   ATTRACT_BAR_LAST_LINE, ATTRACT_BAR_LAST_LINE + 1, 0xffff))
def test_attract_rasterbar_line_band(line):
    """The band's two edges, either side of each.

    The line is incremented FIRST and the tests are on the new value, so entering at 0 puts the
    handler on line 1 — the first line inside the band — and entering at 0x26 puts it on 0x27, the
    first outside. 0xffff is the signed arm: `blt` and `bge` are signed compares, so a line that
    reads as -1 increments to 0 and is BELOW the band rather than far above it.
    """
    _isr_case(ENTRY_ATTRACT_RASTERBAR_ISR, "g_attract_rasterbar_isr", _bar_pokes(line))


@pytest.mark.parametrize("cursor_offset", (0, 4, 8))
def test_attract_rasterbar_walks_the_list(cursor_offset):
    """The count word is decremented IN PLACE and the cursor advances only when it hits zero — so
    the list is consumed as the band is painted, which is what the VBL's rewind exists to undo."""
    _isr_case(ENTRY_ATTRACT_RASTERBAR_ISR, "g_attract_rasterbar_isr",
              _bar_pokes(ATTRACT_BAR_FIRST_LINE, cursor_offset))


def test_attract_rasterbar_count_of_zero_wraps():
    """`subi.w #$1` on a count of 0 gives 0xffff, which is not zero — so the pair is NOT retired and
    the cursor stays put for another 65535 scanlines. The band is 38 lines long, so a zero count is
    a bar that lasts the rest of the frame."""
    _isr_case(ENTRY_ATTRACT_RASTERBAR_ISR, "g_attract_rasterbar_isr",
              _bar_pokes(ATTRACT_BAR_FIRST_LINE, 0, bytes.fromhex("00000700000300700002 0007"
                                                                  .replace(" ", ""))))


def test_attract_rasterbar_attribution():
    """Poison the line word, the count word and the cursor."""
    _isr_case(ENTRY_ATTRACT_RASTERBAR_ISR, "g_attract_rasterbar_isr",
              _bar_pokes(ATTRACT_BAR_FIRST_LINE), poison=True)


# =================================================================================================
# The title/menu VBL — 0x13c26
# =================================================================================================

@pytest.mark.parametrize("phase", (0, 1, 2, 3, 0xff))
def test_vbl_menu(phase):
    """The raster phase counts UP and wraps at 2, and the wait flag is cleared only on the wrap.

    Every phase byte the counter can hold is driven, including the three that never occur in play
    (2, 3, 0xff): the original counts up and compares against 2, so a phase starting above 1 runs
    all the way round to 0 rather than wrapping on the next frame — which is what separates the
    instruction pair from the `^ 1` toggle a paraphrase would write.
    """
    pokes = _armed_voice_pokes()
    pokes[A_RASTER_PHASE] = bytes([phase])
    pokes[A_VBL_WAIT_FLAG] = b"\x01"
    _isr_case(ENTRY_VBL_MENU, "g_vbl_menu", pokes)


# ============================================================ ikbd_acia_isr @ 0x14456

# The status byte a real entry is taken on: the 6850 raised the interrupt (bit 7) and has a byte in
# its receive register (bit 0). Both bits are tested, one after the other, before the port is popped.
ACIA_STATUS_BYTE_READY = ACIA_STATUS_IRQ | ACIA_STATUS_RX_FULL

# Two scancodes the game's own front end reads — '1' and '2' — used as the key the handler is
# holding when a release arrives. A release code is the press code with bit 7 set.
KEY_1_SCANCODE = 0x02
KEY_2_SCANCODE = 0x03
# A cursor value the handler cannot produce, and a joystick pair neither state byte holds: without
# them a candidate that wrote nothing would look identical to one that wrote correctly, because both
# globals are zero in the loaded image.
CURSOR_CANARY = 0x0005a5a5
STATE_CANARY = b"\x5a\xa5"


def _acia_pokes(remaining, cursor=A_IKBD_JOYSTICK_STATE, scancode=0):
    """The handler's whole in-image input set, every byte of it seeded away from its own answers."""
    return {
        A_IKBD_PACKET_REMAINING: bytes([remaining]),
        A_IKBD_PACKET_PTR: cursor.to_bytes(4, "big"),
        A_IKBD_JOYSTICK_STATE: STATE_CANARY,
        A_KEY_SCANCODE: bytes([scancode]),
    }


def _acia_case(pokes, data=None, status=ACIA_STATUS_BYTE_READY, gpip=MFP_GPIP_ACIA_IDLE,
               poison=False, label="", max_insns=200_000):
    """One entry of the handler, with the two ACIA ports and the MFP GPIP declared.

    `data` is the byte the keyboard controller had put on the port, and it is None for the cases
    whose STATUS byte stops the handler before it pops the port: the slot is VOLATILE, and declaring
    a byte no read consumes would describe a machine state the case does not exercise.

    The GPIP defaults to the ACIA's line IDLE — it is ACTIVE LOW, so bit 4 SET means the controller
    has nothing more to say — which is what lets the handler leave after one pass. Every case
    declares it, because that slot carries no model default and an undeclared read is refused.
    """
    frame = abi.interrupt_frame_pokes(ENTRY_IKBD_ACIA_ISR)
    frame.update(pokes)
    hw_seed = {HW_ACIA_STATUS: status, HW_MFP_GPIP: gpip}
    if data is not None:
        hw_seed[HW_ACIA_DATA] = data
    diffs, info = differential(abi.STUB, {"_pokes": frame},
                               lambda lib, buf: lib.g_ikbd_acia_isr(buf),
                               poison=poison, hw_seed=hw_seed, max_insns=max_insns)
    assert not diffs, f"ikbd_acia_isr {label}\n{report(diffs)}"
    return info


def test_the_joystick_packet_arrives_over_three_entries():
    """THE `$fd` HEADER AND THE TWO STATE BYTES, driven as the three separate entries they are.

    The data port is VOLATILE — one declaration describes ONE read of it — so a three-byte packet is
    three runs, each entered from the state the previous one left and each declaring the byte the
    controller had put there by then. That is not a workaround: on the machine these really are three
    interrupts, and running them as one would describe a port that answered three bytes to one
    declaration.

    Entry 1 arms the countdown and touches neither joystick byte. Entries 2 and 3 write through the
    cursor, and entry 3 is the one that REWINDS it — the rewind hangs off the countdown reaching
    zero, not off the header, which is what keeps every report landing at 0x19680 however many
    arrive.
    """
    _acia_case(_acia_pokes(remaining=0, cursor=CURSOR_CANARY),
               data=IKBD_JOYSTICK_HEADER, label="header")
    _acia_case(_acia_pokes(remaining=IKBD_JOYSTICK_PACKET_BYTES), data=0x53, label="joy 0")
    _acia_case(_acia_pokes(remaining=1, cursor=A_IKBD_JOYSTICK_STATE + 1), data=0x81,
               label="joy 1 + rewind")


def test_the_header_does_not_rewind_the_cursor():
    """The header arm, entered with the cursor at a value the handler cannot produce.

    Seeded, because the cursor's RESTING place is `A_ikbd_joystick_state`: a candidate that rewound
    on the header instead of on the last byte would agree with the original on every run starting
    from that resting value, which is every run in a game.
    """
    _acia_case(_acia_pokes(remaining=0, cursor=CURSOR_CANARY), data=IKBD_JOYSTICK_HEADER,
               poison=True, label="header keeps the cursor")


@pytest.mark.parametrize("remaining", (1, 2, 3, 0x7f, 0x80, 0xff))
def test_the_packet_countdown_rewinds_only_at_zero(remaining):
    """Every countdown the byte can hold, one entry each.

    `subq.b #1` then `bne`, so only a countdown of 1 rewinds the cursor; 0x80 and 0xff step down
    like any other, and 3 is one past the two the header arms — the game never produces it, and it
    is what says the rewind tests the stepped byte against zero rather than the packet length.
    """
    _acia_case(_acia_pokes(remaining=remaining, cursor=A_IKBD_JOYSTICK_STATE + 1), data=0x42,
               label=f"remaining={remaining:#x}")


@pytest.mark.parametrize("held", (KEY_2_SCANCODE, 0x7f, 0xff))
@pytest.mark.parametrize("data", (KEY_1_SCANCODE, KEY_2_SCANCODE, 0x82, 0x83, 0x8f))
def test_a_key_press_is_stored_and_its_own_release_clears_it(held, data):
    """The press/release pair over three held scancodes and five arriving bytes.

    Fifteen combinations rather than the two a worked example needs, because the release arm's whole
    content is a COMPARISON: 0x82 clears a held 0x02 and leaves a held 0x03 standing, and a candidate
    that cleared on any release at all passes every case where the two happen to agree. The held byte
    is seeded on every case, so "stored the press" and "left it alone" differ.

    THE HELD SET DELIBERATELY EXCLUDES 0 AND 0x02: the exhaustive sweep below already runs all 256
    arriving bytes against exactly those two, so running them here again would be ten identical
    differential runs and no extra distinction.
    """
    _acia_case(_acia_pokes(remaining=0, scancode=held), data=data,
               label=f"held={held:#x} data={data:#x}")


@pytest.mark.parametrize("data", (0x7b, 0x7c, 0x7d, 0x7e, 0xfb, 0xfc, 0xfe, 0xff))
def test_the_press_release_split_is_the_sign_of_the_difference(data):
    """`cmp.b #$fd,d1 / bmi` — and it is NOT `btst #7`, which is what these eight bytes say.

    The arm is chosen by the sign of `byte - 0xfd`, so the release arm is exactly 0x7d..0xfc: 0x7d
    and 0x7e are press codes that take it, and 0xfe/0xff are release codes that do not and are
    STORED as scancodes. 0x7b/0x7c sit on the other side of the low edge and 0xfb inside the arm.
    A candidate spelling the test as bit 7 agrees everywhere but on these, which is why they are here
    and why the shipped keyboard sending none of them is beside the point.
    """
    _acia_case(_acia_pokes(remaining=0, scancode=data & ~KEY_RELEASE_BIT), data=data,
               label=f"data={data:#x}")


@pytest.mark.parametrize("chunk", range(4))
def test_every_data_byte_through_both_arms(chunk):
    """All 256 bytes the port can answer, against two held scancodes, sharded four ways.

    Exhaustive because the byte is this routine's whole input and the three arms it picks between —
    header, release, press — are chosen by two compares on it. The held scancodes are 0 (nothing
    down, so the release arm's compare can only match a release of nothing) and 0x02, which exactly
    one of the 256 releases matches and the other 255 do not.
    """
    for held in (0, KEY_1_SCANCODE):
        for data in range(chunk, 0x100, 4):
            _acia_case(_acia_pokes(remaining=0, scancode=held), data=data,
                       label=f"held={held:#x} data={data:#x}")


@pytest.mark.parametrize("status", (0x00, 0x01, 0x7f, ACIA_STATUS_IRQ, 0xfe))
def test_a_status_byte_that_is_not_a_ready_receive_pops_nothing(status):
    """`btst #7` then `btst #0`, with BOTH gates driven separately.

    A status with the interrupt bit clear (0x00, 0x01, 0x7f) never reaches the second test; one with
    that bit set but no byte waiting (0x80, 0xfe) reaches it and stops there. No case here declares a
    data byte, because on these arms the port is never popped — and the READ ledger the differential
    compares is what says so, since a candidate that popped it anyway ledgers a read the oracle did
    not make.
    """
    _acia_case(_acia_pokes(remaining=IKBD_JOYSTICK_PACKET_BYTES, scancode=KEY_1_SCANCODE),
               data=None, status=status, poison=True, label=f"status={status:#x}")


def test_the_gpip_reentry_loop_is_a_run_the_model_cannot_serve():
    """THE ONE ARM NO CASE ABOVE REACHES, stated as a case rather than left looking untested.

    `btst #4,$fffffa01 / beq.s $14456` sends the handler round again while the ACIA's GPIP line is
    still asserted — ACTIVE LOW, so bit 4 CLEAR means "another byte is waiting". The GPIP is STATIC
    in the kit's seeded read model: ONE declaration describes every read of it, so a run declaring
    bit 4 clear never sees the line rise and the loop has no end. The oracle spends its instruction
    cap and the case is thrown away, exactly as an IKBD send declared with TDRE clear is.

    THAT IS THE MODEL'S SHAPE AND NOT A DEFECT IN THE CASE. Serving the second pass would need the
    GPIP to answer one byte and then another, which is a sequence and not a constant — and the DATA
    port the second pass would pop is VOLATILE for the same reason, so even a terminating loop could
    not be declared. The cap here is tiny on purpose: the point is that the spin never ends.

    The loop is spelt in `src/irq.c` because it is the instruction. A candidate that dropped it and
    serviced exactly one byte passes every drivable case above — STATUS.md records that survivor and
    names the surface that would catch it.
    """
    with pytest.raises(RuntimeError, match="did not reach"):
        _acia_case(_acia_pokes(remaining=0), data=KEY_1_SCANCODE, gpip=0, max_insns=2_000,
                   label="reentry")


def test_the_hardware_addresses_are_the_models_own():
    """The three addresses this battery declares must be slots the kit's seeded read model names.

    Unpinned, an address corrected in `os.h` would leave every `hw_seed` above declaring a byte no
    read consumes — `emu.hw_seed_bytes` refuses an address outside the table, so the failure would be
    loud, but it would name the harness rather than this drift. The ACIA DATA port is the one added
    for THIS handler, so its membership is the claim worth stating.
    """
    for address in (HW_ACIA_STATUS, HW_ACIA_DATA, HW_MFP_GPIP):
        assert address in harness.emu.HW_ADDRS, (
            f"{address:#x} is not in the seeded read model's table "
            f"({', '.join(f'{a:#x}' for a in harness.emu.HW_ADDRS)})")


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("A_VSYNC_FLAG", "include/irq.h", "A_vsync_flag"),
    ("A_PALETTE_HW_SHADOW", "include/irq.h", "A_palette_hw_shadow"),
    ("A_PALETTE_CYCLE_WORDS", "include/irq.h", "A_palette_cycle_words"),
    ("A_PALETTE_SWAP_LONG", "include/irq.h", "A_palette_swap_long"),
    ("A_PALETTE_SWAP_COUNTDOWN", "include/irq.h", "A_palette_swap_countdown"),
    ("A_PALETTE_ROTATE_COUNTDOWN", "include/irq.h", "A_palette_rotate_countdown"),
    ("A_ATTRACT_RASTER_LINE", "include/irq.h", "A_attract_raster_line"),
    ("A_ATTRACT_RASTER_LIST_PTR", "include/irq.h", "A_attract_raster_list_ptr"),
    ("A_ATTRACT_RASTER_LIST", "include/irq.h", "A_attract_raster_list"),
    ("PALETTE_PENS", "include/video.h", "PALETTE_PENS"),
    ("PALETTE_CYCLE_WORDS", "include/irq.h", "PALETTE_CYCLE_WORDS"),
    ("PALETTE_SWAP_PERIOD", "include/irq.h", "PALETTE_SWAP_PERIOD"),
    ("PALETTE_ROTATE_PERIOD", "include/irq.h", "PALETTE_ROTATE_PERIOD"),
    ("ATTRACT_BAR_FIRST_LINE", "include/irq.h", "ATTRACT_BAR_FIRST_LINE"),
    ("ATTRACT_BAR_LAST_LINE", "include/irq.h", "ATTRACT_BAR_LAST_LINE"),
    ("A_MENU_PALETTE", "include/irq.h", "A_menu_palette"),
    ("A_VBL_WAIT_FLAG", "include/irq.h", "A_vbl_wait_flag"),
    ("A_RASTER_PHASE", "include/irq.h", "A_raster_phase"),
    ("RASTER_PHASE_PERIOD", "include/irq.h", "RASTER_PHASE_PERIOD"),
    ("A_IKBD_PACKET_PTR", "include/irq.h", "A_ikbd_packet_ptr"),
    ("A_IKBD_PACKET_REMAINING", "include/irq.h", "A_ikbd_packet_remaining"),
    ("A_IKBD_JOYSTICK_STATE", "include/irq.h", "A_ikbd_joystick_state"),
    ("A_KEY_SCANCODE", "include/irq.h", "A_key_scancode"),
    ("IKBD_JOYSTICK_HEADER", "include/irq.h", "IKBD_JOYSTICK_HEADER"),
    ("IKBD_JOYSTICK_PACKET_BYTES", "include/irq.h", "IKBD_JOYSTICK_PACKET_BYTES"),
    ("ACIA_STATUS_IRQ", "include/irq.h", "ACIA_STATUS_IRQ"),
    ("ACIA_STATUS_RX_FULL", "include/irq.h", "ACIA_STATUS_RX_FULL"),
    ("KEY_RELEASE_BIT", "include/irq.h", "KEY_RELEASE_BIT"),
    ("MFP_GPIP_ACIA_IDLE", "include/irq.h", "MFP_GPIP_ACIA_IDLE"),
)
ENTRY_PROLOGUES = {
    "ENTRY_VBL_ISR": "4239000198ab61006416",
    "ENTRY_TIMER_B_ISR": "4239000198ab08b90000",
    "ENTRY_VBL_ISR_TITLE": "610064f0427900ff8240",
    "ENTRY_TIMER_B_RASTER_ISR": "23f900018fc400ff8240",
    "ENTRY_ATTRACT_VBL_ISR": "427900019f2242390001",
    "ENTRY_ATTRACT_RASTERBAR_ISR": "48e70180067900010001",
    "ENTRY_VBL_MENU": "23f900019f4600ff8240",
    "ENTRY_IKBD_ACIA_ISR": "48e7c0c041f9fffffc00",
}
