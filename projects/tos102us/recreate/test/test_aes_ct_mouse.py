"""The control manager's MOUSE GRAB — `src/aes/ctrl.c`, through `test/aes_gsx.py`'s door (it reaches the VDI).

    ct_mouse(1)   gsx_mfsave; ct_shown = gl_mouse; ct_nest = gl_moff; gsx_mfset(ad_armice); if !gl_mouse:
                  gsx_1code(v_show_c, 0), gl_mouse = 1; gl_moff = 0
    ct_mouse(0)   gsx_ncode(v_hide_c, 0, 0); gsx_mfrestore; gl_mouse = 0; if ct_shown: gsx_ncode(v_show_c, 0, ??),
                  gl_mouse = 1; gl_moff = ct_nest

THE MISSING ARGUMENT (`ctrl.c`): the release's re-show hands gsx_ncode two words where it takes three, so contrl[3] is the
frame's never-written word -2(a6) — whatever the stack held. Entered directly, ct_mouse's `link` puts that word at
`STALE_COUNT_AT`: a case stages it there, and either drops contrl[3] by name (any other value) or compares it whole (the
C's value, `CT_MOUSE_STALE_COUNT`).

THE MACHINES: the snapshot's own (`aes_gsx.shown_machine`: the cursor shown), the cursor hidden the AES's way
(`aes_gsx.machine`), and each grab's END continued into its release (`case.continued_from`) — a real sequence, both shores
starting the release from the machine the ROM's own grab left (`grabbed`).
"""
import struct

import pytest

import aes
import aes_gsx as gsx
import case
import vdi
from case import merge_pokes
from harness import addrs, emu, make_image

aes.declare_alcyon("AES_ROM_CT_MOUSE", None, (vdi.IMAGE_ARG, vdi.WORD_ARG))
CTRL = aes.header_constants("ctrl.h")
GRAB, RELEASE = CTRL["CT_MOUSE_GRAB"], CTRL["CT_MOUSE_RELEASE"]
THROUGH = gsx.THROUGH

# Entered directly, `link a6,#-4` saves A6 just under the sentinel's slot, and the never-written word is the low word of
# the longword local below it.
SAVED_FRAME_POINTER_BYTES = aes.LONG_BYTES
STALE_COUNT_AT = emu.STACK_TOP - SAVED_FRAME_POINTER_BYTES - aes.WORD_BYTES
CT_MOUSE_STALE_COUNT = CTRL["CT_MOUSE_STALE_COUNT"]   # what the C hands in its place (`ctrl.c`)
STALE_GARBAGE = 0x5A3C                 # ...and a stack word that is not it
CONTRL_COUNT_DROP = ((aes.AES_GSX_N_INTIN, aes.AES_GSX_N_INTIN + aes.WORD_BYTES,
                      "ct_mouse's re-show hands gsx_ncode two words where it takes three: contrl[3] is its frame's "
                      "never-written word, stack garbage the C cannot know"),)


def stale_count(value):
    return {STALE_COUNT_AT: struct.pack(">H", value)}


def run(grab, machine, **kwargs):
    return aes.run_function("AES_ROM_CT_MOUSE", (grab,), machine, hook=gsx.vdi_hook, **kwargs)


def grabbed(machine):
    """The machine the ROM's OWN grab over `machine` leaves (its run continued from), as the release's start — derived,
    so a battery's rows never rest on a differential of the grab (`test_a_grab_*` prove that one)."""
    final, writes, _regs = emu.run(make_image(aes.staged("AES_ROM_CT_MOUSE", (GRAB,), machine)), addrs.AES_ROM_CT_MOUSE)
    return case.continued_from(machine, final, writes)


def shown():
    return gsx.shown_machine()


def hidden():
    return gsx.machine()


def fields(result):
    return {name: result.field("AES", name) for name in ("GL_MOUSE_SHOWN", "GL_MOFF", "CT_MOUSE_SHOWN", "CT_MOUSE_NEST")}


# ---- the grab --------------------------------------------------------------------------------------------------------
@THROUGH
def test_a_grab_with_the_cursor_shown_keeps_it_shown(through_line_f):
    result = run(GRAB, shown(), through_line_f=through_line_f)
    assert fields(result) == {"GL_MOUSE_SHOWN": 1, "GL_MOFF": 0, "CT_MOUSE_SHOWN": 1, "CT_MOUSE_NEST": 0}


@THROUGH
def test_a_grab_with_the_cursor_hidden_shows_it(through_line_f):
    result = run(GRAB, hidden(), through_line_f=through_line_f)
    assert fields(result) == {"GL_MOUSE_SHOWN": 1, "GL_MOFF": 0, "CT_MOUSE_SHOWN": 0, "CT_MOUSE_NEST": 1}


def test_a_grab_sets_the_arrow():
    """gsx_mfset hands the VDI the arrow's form: its first word — the hot spot's x — is in intin[0] after it."""
    result = run(GRAB, hidden())
    arrow = case.long_in(result.final, aes.AES_AD_ARMICE)
    assert result.word(aes.AES_GSX_INTIN) == case.word_in(result.final, arrow)


# ---- the release -----------------------------------------------------------------------------------------------------
def test_a_release_after_a_hidden_grab_hides_it_again():
    result = run(RELEASE, grabbed(hidden()))
    assert fields(result) == {"GL_MOUSE_SHOWN": 0, "GL_MOFF": 1, "CT_MOUSE_SHOWN": 0, "CT_MOUSE_NEST": 1}


@pytest.mark.parametrize("garbage", (STALE_GARBAGE, 0xFFFF), ids=("a stack word", "-1"))
def test_a_release_after_a_shown_grab_shows_it_with_a_stale_count(garbage):
    """The re-show arm: contrl[3] is the stack's word — dropped by name — and nothing else is let go."""
    result = run(RELEASE, merge_pokes(grabbed(shown()), stale_count(garbage)),
                 dropped_windows=aes.LINE_F_MASK_WINDOW + CONTRL_COUNT_DROP)
    assert fields(result) == {"GL_MOUSE_SHOWN": 1, "GL_MOFF": 0, "CT_MOUSE_SHOWN": 1, "CT_MOUSE_NEST": 0}
    assert result.word(aes.AES_GSX_N_INTIN) == garbage, "the ROM's contrl[3] is the stack's word"


def test_a_release_after_a_shown_grab_compares_whole_over_the_c_s_word():
    """...and the same arm with the stack holding the C's word: compared with nothing let go."""
    run(RELEASE, merge_pokes(grabbed(shown()), stale_count(CT_MOUSE_STALE_COUNT)))


@THROUGH
def test_a_release_through_its_callers_word(through_line_f):
    run(RELEASE, grabbed(hidden()), through_line_f=through_line_f)


# ---- the registry ----------------------------------------------------------------------------------------------------
ROWS = {
    "a grab, the cursor shown": (GRAB, shown),
    "a grab, the cursor hidden: shown": (GRAB, hidden),
    "a release after a hidden grab": (RELEASE, lambda: grabbed(hidden())),
    "a release after a shown grab: re-shown": (RELEASE, lambda: merge_pokes(grabbed(shown()),
                                                                           stale_count(CT_MOUSE_STALE_COUNT))),
}
for _label, (_grab, _machine) in ROWS.items():
    aes.register(_label, "AES_ROM_CT_MOUSE", (_grab,), _machine(), hook=gsx.vdi_hook)
