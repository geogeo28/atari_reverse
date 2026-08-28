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

for _name in ("g_vbl_isr", "g_timer_b_isr", "g_vbl_isr_title", "g_timer_b_raster_isr",
              "g_attract_vbl_isr", "g_attract_rasterbar_isr", "g_vbl_menu"):
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
    ("PALETTE_PENS", "include/irq.h", "PALETTE_PENS"),
    ("PALETTE_CYCLE_WORDS", "include/irq.h", "PALETTE_CYCLE_WORDS"),
    ("PALETTE_SWAP_PERIOD", "include/irq.h", "PALETTE_SWAP_PERIOD"),
    ("PALETTE_ROTATE_PERIOD", "include/irq.h", "PALETTE_ROTATE_PERIOD"),
    ("ATTRACT_BAR_FIRST_LINE", "include/irq.h", "ATTRACT_BAR_FIRST_LINE"),
    ("ATTRACT_BAR_LAST_LINE", "include/irq.h", "ATTRACT_BAR_LAST_LINE"),
    ("A_MENU_PALETTE", "include/irq.h", "A_menu_palette"),
    ("A_VBL_WAIT_FLAG", "include/irq.h", "A_vbl_wait_flag"),
    ("A_RASTER_PHASE", "include/irq.h", "A_raster_phase"),
    ("RASTER_PHASE_PERIOD", "include/irq.h", "RASTER_PHASE_PERIOD"),
)
ENTRY_PROLOGUES = {
    "ENTRY_VBL_ISR": "4239000198ab61006416",
    "ENTRY_TIMER_B_ISR": "4239000198ab08b90000",
    "ENTRY_VBL_ISR_TITLE": "610064f0427900ff8240",
    "ENTRY_TIMER_B_RASTER_ISR": "23f900018fc400ff8240",
    "ENTRY_ATTRACT_VBL_ISR": "427900019f2242390001",
    "ENTRY_ATTRACT_RASTERBAR_ISR": "48e70180067900010001",
    "ENTRY_VBL_MENU": "23f900019f4600ff8240",
}
