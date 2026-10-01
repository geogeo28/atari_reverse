"""The rectangle helpers the target build ships as the ROM's own instructions (`src/aes/optimize.S`): r_get, r_set,
rc_copy, rc_equal, rc_union and rc_constrain.

Their C (`src/aes/rect.c`) is what every Tier 1 case proves (`test_aes_rect_helpers.py`); it measures over the 1.10 bar
against these routines, so by the user's rule the target carries the ROM's code. Two claims hold it: its BYTES are the
ROM's, every one — the optimize layer's one region, which `test_aes_strings_asm.py` declares and pins (rc_equal leaves
through the shared return tails at its far end, so the rectangle helpers share the string helpers' region) — and it
BEHAVES as the ROM, image and whole register file, through Tier 3's transcription relation over the C battery's own
shapes, here.

THE CALLER. `transcription.run_transcription` enters both sides at a staged caller that jumps through the routine
longword at `abi.FIRST_ARG`. An Alcyon routine reads its frame above its return address, so each frame width gets a
caller of its own (`frame_caller`): the frame staged above that longword, pushed a longword at a time, the routine
called, the frame dropped — a `jsr` with the ROM callers' frame. rc_copy, rc_equal, rc_union and rc_constrain take two
longwords, r_set three (a pointer and four words), r_get five.
"""
import struct

import pytest

import abi
import aes
import transcription
from case import merge_pokes
from opcodes import DROP_STACK_BYTES, PUSH_RETURN_PC, PUSH_STACK_LONG, RTS
import test_aes_rect_helpers as helpers

R_GET, R_SET, RC_COPY = helpers.R_GET, helpers.R_SET, helpers.RC_COPY
RC_EQUAL, RC_UNION, RC_CONSTRAIN = helpers.RC_EQUAL, helpers.RC_UNION, helpers.RC_CONSTRAIN

# ---- the frame callers --------------------------------------------------------------------------------------------
CALLERS_BYTES = 0xC0
CALLER_STRIDE = 0x30                     # the five-longword caller is 36 bytes
CALLERS_AT = aes.SPAN.claim(aes.WINDOW_AT + 0x1200, CALLERS_BYTES, "test/test_aes_rect_transcription.py: frame callers")
POOL = transcription.CallerPool(CALLERS_AT, CALLERS_AT + CALLERS_BYTES, CALLER_STRIDE)
FRAME_ARGUMENTS_AT = abi.FIRST_ARG + aes.LONG_BYTES     # above the routine longword the caller jumps through
_TO_RETURN = 8                                          # `pea` to the `lea` after the `rts`, from its extension word
# A caller's cost: `pea`, the routine's push, `rts`, `lea`, `rts` and one push per longword, as Musashi counts them
# (`test_transcribed.py` measures every registered caller against it).
CALLER_BASE_COST = (5, 80)
PUSH_COST = (1, 24)


def frame_caller_stub(longwords):
    """A caller pushing `longwords` of frame staged at FRAME_ARGUMENTS_AT (each push reaching the next longword
    down at the same displacement), calling through the routine longword, and dropping the frame."""
    from_entry_sp = aes.LONG_BYTES + longwords * aes.LONG_BYTES      # the last longword, past the sentinel
    to_routine = 2 * aes.LONG_BYTES + longwords * aes.LONG_BYTES     # the routine longword, once all is pushed
    stub = (longwords * (PUSH_STACK_LONG + struct.pack(">h", from_entry_sp))
            + PUSH_RETURN_PC + struct.pack(">h", _TO_RETURN)
            + PUSH_STACK_LONG + struct.pack(">h", to_routine)
            + RTS
            + DROP_STACK_BYTES + struct.pack(">h", longwords * aes.LONG_BYTES)
            + RTS)
    cost = tuple(base + longwords * each for base, each in zip(CALLER_BASE_COST, PUSH_COST))
    return stub, cost


def frame_caller(longwords):
    return POOL.staged(("frame", longwords), lambda: frame_caller_stub(longwords))


def entered(name, arguments, pokes):
    """`pokes` with `name`'s Alcyon frame of `arguments` where its frame caller reads it, and that caller."""
    frame = aes.alcyon_frame(name, *arguments)[abi.FIRST_ARG]
    assert len(frame) % aes.LONG_BYTES == 0
    return frame_caller(len(frame) // aes.LONG_BYTES), merge_pokes(aes.leaf_machine(onto=pokes),
                                                                    {FRAME_ARGUMENTS_AT: frame})


def run(name, arguments, pokes=None):
    caller, staged = entered(name, arguments, pokes)
    return transcription.run_transcription(name, staged, caller=caller)


def register(label, name, arguments, pokes=None):
    caller, staged = entered(name, arguments, pokes)
    return transcription.register_transcription(name, label, staged, caller=caller)


# ---- the relation over the C battery's shapes ---------------------------------------------------------------------
CASES = {
    (R_GET, "the desktop window"): ((helpers.DESKTOP_FULL, *helpers.ANSWER_WORDS), helpers.STALE_ANSWERS),
    (R_GET, "each word before the next"): ((helpers.FIRST_AT, helpers.FIRST_AT + aes.GRECT_Y, *helpers.ANSWER_WORDS[1:]),
                                           merge_pokes(helpers.STALE_ANSWERS, aes.grect_pokes(helpers.FIRST_AT, 3, 4, 5, 6))),
    (R_SET, "the desktop's words"): ((helpers.FIRST_AT, 0, 11, 320, 189), None),
    (R_SET, "the extremes"): ((helpers.FIRST_AT, -1, -32768, 32767, 0x8001), None),
    (RC_COPY, "an object's rectangle"): ((helpers.FILE_ROW, helpers.FIRST_AT), None),
    (RC_COPY, "one longword above itself"): ((helpers.FIRST_AT, helpers.FIRST_AT + aes.GRECT_W),
                                             aes.grect_pokes(helpers.FIRST_AT, 1, 2, 3, 4)),
    **{(RC_EQUAL, shape): ((helpers.FIRST_AT, helpers.SECOND_AT), helpers.two_rects(*rects))
       for shape, rects in helpers.PAIRS.items()},
    (RC_EQUAL, "the desktop's two rectangles"): ((helpers.DESKTOP_PREV, helpers.DESKTOP_FULL), None),
    **{(RC_UNION, shape): ((helpers.FIRST_AT, helpers.SECOND_AT), helpers.two_rects(*rects))
       for shape, rects in helpers.UNIONS.items()},
    (RC_UNION, "the desktop window"): ((helpers.DESKTOP_PREV, helpers.DESKTOP_FULL), None),
    **{(RC_CONSTRAIN, shape): ((helpers.FIRST_AT, helpers.SECOND_AT), helpers.two_rects(*rects))
       for shape, rects in helpers.CONSTRAINTS.items()},
    (RC_CONSTRAIN, "an object to the desktop"): ((helpers.DESKTOP_FULL, helpers.FILE_ROW), None),
}


@pytest.mark.parametrize("name,shape", sorted(CASES), ids=lambda value: value)
def test_the_transcription_behaves_as_the_rom(name, shape):
    arguments, pokes = CASES[(name, shape)]
    run(name, arguments, pokes)


def test_the_pointers_top_bytes_reach_the_transcription_as_they_reach_the_rom():
    """Every pointer tagged: the ROM's `movem` loads all 32 bits and the bus drops the top byte — so does the `.S`."""
    tagged = tuple(at | aes.BUS_TAG for at in (helpers.DESKTOP_FULL, *helpers.ANSWER_WORDS))
    run(R_GET, tagged, helpers.STALE_ANSWERS)
    run(RC_UNION, (helpers.FIRST_AT | aes.BUS_TAG, helpers.SECOND_AT | aes.BUS_TAG),
        helpers.two_rects(*helpers.UNIONS["disjoint"]))


for (_name, _shape), (_arguments, _pokes) in sorted(CASES.items()):
    register(_shape, _name, _arguments, _pokes)
