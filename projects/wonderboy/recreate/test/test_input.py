"""Differential test for the joystick edge pipeline (src/input.c): `joy1_latch_edge` @ $88c and
`joy1_newly_pressed` @ $682.

Both run under the Musashi oracle and as the reconstruction on the same image, diffed byte for byte
over the whole image. The two have DIFFERENT surfaces and each case asserts on the one that matters:

  * the latch's whole effect is two bytes of memory, and the cases pin which byte moved where —
    a port that copied the pipeline in the wrong order would leave both stages equal and is caught
    by seeding all three bytes distinctly;
  * the edge computes nothing in memory AT ALL. Its only output is d0, and only d0's LOW BYTE is
    the answer: every instruction in it is a `.b` op, so the caller's own top 24 bits survive the
    call. Each case therefore enters the oracle with a seeded d0 and compares the whole longword,
    which is what pins the operand size — a port that returned a full word or long would agree on
    memory (there is none) and differ only here.

KNOWINGLY NOT PINNED
  * where the input comes from. `joy1_state` is filled by an IKBD interrupt handler ($858) that no
    case here runs; these two routines only ever see it as a byte in memory, which is how it is
    seeded.
  * that the mask is used as a rising EDGE by anything. The three callers in ../decomp.c are
    outside this battery; what is pinned is the byte the routine returns for a given pair of frames.
"""
import ctypes

import pytest

import leaf
from layout import wb

JOY1_STATE = wb("JOY1_STATE")
JOY1_PREV = wb("JOY1_PREV")
JOY1_CURRENT = wb("JOY1_CURRENT")

BYTE = 1
BYTE_MASK = 0xff
D0_ABOVE_LOW_BYTE = 0xffffff00

# `move.b joy1_prev,d0 / move.b joy1_current,d1 / eor.b d1,d0 / and.b d1,d0 / rts` — 18 bytes.
NEWLY_PRESSED_ENTRY = (b"\x10\x39" + JOY1_PREV.to_bytes(4, "big")        # move.b <abs>.l,d0
                       + b"\x12\x39" + JOY1_CURRENT.to_bytes(4, "big")   # move.b <abs>.l,d1
                       + b"\xb3\x00"                                     # eor.b d1,d0
                       + b"\xc0\x01"                                     # and.b d1,d0
                       + b"\x4e\x75")
# `move.b joy1_current,joy1_prev / move.b joy1_state,joy1_current / rts` — 20 bytes. The second move
# reads through a SHORT absolute operand, which is why it is 8 bytes where the first is 10.
LATCH_ENTRY = (b"\x13\xf9" + JOY1_CURRENT.to_bytes(4, "big") + JOY1_PREV.to_bytes(4, "big")
               + b"\x13\xf8" + JOY1_STATE.to_bytes(2, "big") + JOY1_CURRENT.to_bytes(4, "big")
               + b"\x4e\x75")
# Keyed by ../names.txt's name, so each entry is pinned by a case of its own rather than by an
# assert that a preceding one can hide.
ENTRY_BYTES = {"joy1_newly_pressed": NEWLY_PRESSED_ENTRY, "joy1_latch_edge": LATCH_ENTRY}

# (previous frame, this frame, what the pair stands for). Bit 7 is fire (../names.txt, joy1_state).
FIRE = 0x80
EDGE_CASES = (
    (0x00, 0x00, "nothing held, nothing pressed"),
    (0x00, FIRE, "fire pressed this frame — the case the routine exists for"),
    (FIRE, FIRE, "fire HELD: an edge detector must report nothing"),
    (FIRE, 0x00, "fire released: a falling edge is not a rising one"),
    (0x0f, 0x3c, "some directions released and others pressed in the same frame"),
    (0xff, 0xff, "every bit held"),
    (0x00, 0xff, "every bit pressed at once"),
)

# The d0 the oracle is entered with. The routine only ever touches its low byte, so these are what
# the top 24 bits are pinned against; the low byte is seeded non-zero too, so a port that ORed its
# result into d0 instead of replacing the byte differs.
ENTRY_D0 = (0x00000000, 0xa5a5a5a5, 0xffffffff)

# (joy1_state, joy1_current, joy1_prev) before the latch. All three distinct wherever possible, so a
# port that shifted the wrong way, or wrote one stage twice, cannot land on the right answer.
LATCH_CASES = (
    (0x12, 0x34, 0x56),
    (0x00, 0xff, 0x0f),
    (FIRE, 0x00, 0x00),
    (0x00, 0x00, FIRE),
    (0x77, 0x77, 0x77),        # already settled: every stage the same, so nothing visibly moves
)

_newly_pressed = leaf.bind("g_joy1_newly_pressed", leaf.IMAGE_ARG + [ctypes.c_uint32],
                           ctypes.c_uint32)
_latch_glue = leaf.image_glue("joy1_latch_edge")


@pytest.mark.parametrize("name", sorted(ENTRY_BYTES))
def test_an_entry_is_the_instruction_this_battery_reconstructs(name):
    """Pins each entry point, and all three pipeline addresses, against the loaded image."""
    leaf.assert_entry_is(name, ENTRY_BYTES[name])


@pytest.mark.parametrize("entry_d0", ENTRY_D0, ids=[f"d0_{d:08x}" for d in ENTRY_D0])
@pytest.mark.parametrize("prev,current,what", EDGE_CASES,
                         ids=[f"{c[0]:02x}_to_{c[1]:02x}" for c in EDGE_CASES])
def test_the_edge_mask_is_returned_in_d0s_low_byte_alone(prev, current, what, entry_d0):
    pokes = {JOY1_PREV: bytes([prev]), JOY1_CURRENT: bytes([current])}
    info = leaf.run("joy1_newly_pressed",
                    lambda lib, buf: _newly_pressed(buf, entry_d0),
                    [],                       # it writes NOTHING: every image write would be stray
                    f"{what} (d0 in = {entry_d0:#010x})",
                    regs={"d0": entry_d0, "_pokes": pokes})
    assert info["ret"] == info["regs"]["d0"], (
        f"{what}: d0 cand={info['ret']:#010x} oracle={info['regs']['d0']:#010x}")
    # Stated independently of both implementations, and in the other of the two equivalent forms:
    # src/input.c reproduces the original's eor-then-and, this is the `current & ~prev` reading of
    # it, so a typo in either shows up rather than agreeing with itself.
    assert info["regs"]["d0"] & BYTE_MASK == current & ~prev & BYTE_MASK, what
    assert info["regs"]["d0"] & D0_ABOVE_LOW_BYTE == entry_d0 & D0_ABOVE_LOW_BYTE, (
        f"{what}: the byte ops disturbed d0 above its low byte")


@pytest.mark.parametrize("state,current,prev", LATCH_CASES,
                         ids=[f"{s:02x}_{c:02x}_{p:02x}" for s, c, p in LATCH_CASES])
def test_the_latch_shifts_the_pipeline_one_stage_down(state, current, prev):
    pokes = {JOY1_STATE: bytes([state]), JOY1_CURRENT: bytes([current]), JOY1_PREV: bytes([prev])}
    what = f"latch with state={state:#04x} current={current:#04x} prev={prev:#04x}"
    info = leaf.run("joy1_latch_edge", _latch_glue,
                    [(JOY1_PREV, BYTE), (JOY1_CURRENT, BYTE)], what, regs={"_pokes": pokes})
    # The write set is what the original left behind, so this says which stage ended up where
    # without re-deriving it from the reconstruction. A byte the original did not write kept its
    # seed, and the diff has already proved the reconstruction agrees byte for byte.
    written = info["writes"]
    assert written.get(JOY1_PREV, prev) == current, f"{what}: joy1_prev did not take joy1_current"
    assert written.get(JOY1_CURRENT, current) == state, (
        f"{what}: joy1_current did not take joy1_state")
