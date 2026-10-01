"""AES gemgsxif's workstation half — `src/aes/gsxif.c`, through `test/aes_gsx.py`'s door (signatures:
`test_aes_gsxif.py`).

    gsx_init      gsx_wsopen; gsx_start; gsx_setmb_aes; vq_mouse; xrat, yrat = ptsout[0..1]
    gsx_wsopen    intin[0..9] = 1, intin[10] = 2, intin[0] = gl_restype; v_opnwk(intin, &gl_handle, gl_ws);
                  gl_restype = 3, 2 if work_out[0] = 319, else 4 if work_out[1] = 399; gl_rschange = 0; gl_graphic = 1
    v_opnwk       pb.intin, pb.intout, pb.ptsout = the caller's arrays (ptsout 90 bytes into work_out); VDI 1 (row 3);
                  *handle = contrl[6]; the three pointers back
    gsx_start     seven caches -1; the clip; the screen's size and planes; vqt_attributes; vst_height twice; the cells
                  and the box (`divs.w`, `muls.w`); vsl_type 7, vsl_width 1, vsl_udsty $ffff; five GRECTs; $c844
    gsx_graphic   nothing if gl_graphic is the mode; else escape 2 + gsx_setmb_aes, or escape 3 + gsx_resetmb
    gsx_setmb     vex_butv(button), vex_motv(motion), the routines displaced kept in $c7fc / $c91c
    gsx_resetmb   ...put back;  gsx_escapes: contrl[5], VDI 5;  gsx_wsclose: VDI 2
    ratinit       v_show_c(0); gl_moff = 0
    gsx_tick      vex_timv(routine); *old = contrl[9..10]; D0 = intout[0]

THE ATTRIBUTION PASS IS OFF for every case here that reaches a VDI function writing what the pass would turn
against it, each MEASURED (`UNPOISONED` marks them): escape 2, v_exit_cur (the console's cursor address and state
vector ARE what it writes, `test/vdi_escape.py`'s reason — poisoned, the host's console refuses the address the pass
makes; escape 3 keeps the pass), the OS traps under v_opnwk, v_clswk and vex_timv (they frame below `savptr`, which
the pass inverts — `test_vdi_attr_vectors.py`'s reason: poisoned, the ROM's run never reaches its `rts`), and
gsx_start's vst_height calls, which read the block's PTSIN as the call before left it (`test_aes_gsx.py`'s reason:
poisoned, both sides read the I/O page). What stands in: every word each routine stores is staged STALE first
(`stale`), so a skipped store still differs. Every other case keeps the pass.
"""
import pytest

from harness import BASE_IMAGE, addrs

import aes
import aes_gsx as gsx
import case
import gemdos
import test_aes_gsx as atoms
import test_aes_gsxif as leaves
import vdi
import vdi_escape
import vdi_helpers
import vdi_screen as screen
import vdi_workstation as ws
from case import merge_pokes

THROUGH = gsx.THROUGH
WORD_BYTES, LONG_BYTES = aes.WORD_BYTES, aes.LONG_BYTES
UNPOISONED = vdi.READS_A_POINTER_IT_WRITES
INTIN, PTSOUT = aes.AES_GSX_INTIN, aes.AES_GSX_PTSOUT


def linea_long(result, name):
    return result.long(vdi.field("LINEA", name).at)


# ---- the mouse's routines ---------------------------------------------------------------------------------------
# What the routines are before the AES takes them, and after it gives them back: the VDI's defaults ($fca870, the
# `rts` v_opnwk installs in both), as the snapshot's $c7fc / $c91c keep them.
VDI_DEFAULT_ROUTINE = case.long_in(BASE_IMAGE, aes.AES_OLD_BUTTON)
assert case.long_in(BASE_IMAGE, aes.AES_OLD_MOTION) == VDI_DEFAULT_ROUTINE
DEFAULT_ROUTINES = vdi.linea_pokes(USER_BUT=VDI_DEFAULT_ROUTINE, USER_MOT=VDI_DEFAULT_ROUTINE)
STALE_OLD = aes.stale_fields("OLD_BUTTON", "OLD_MOTION")
OTHER_BUTTON, OTHER_MOTION = 0x0012_3456, 0x0065_4320      # routines no vex call ever sees, so each store shows
for _name in ("USER_BUT", "USER_MOT"):
    vdi.declare_case_field(vdi.field("LINEA", _name).at, LONG_BYTES, f"the mouse routine ({_name}) the AES exchanges")
for _name in ("OLD_BUTTON", "OLD_MOTION", "GL_GRAPHIC", "GL_RESTYPE", "GL_RSCHANGE"):
    aes.declare_case_field(aes.field("AES", _name).at, aes.field("AES", _name).width, "gemgsxif's workstation state")


@pytest.mark.parametrize("button, motion", ((addrs.AES_ROM_BUTTON_GLUE, addrs.AES_ROM_MOTION_GLUE),
                                            (OTHER_BUTTON, OTHER_MOTION)), ids=("the AES's glue", "two others"))
def test_gsx_setmb_installs_both_routines_and_keeps_what_they_displaced(button, motion):
    result = gsx.run_gsx("AES_ROM_GSX_SETMB", (button, motion, vdi.STALE_LONG), merge_pokes(DEFAULT_ROUTINES, STALE_OLD))
    assert (linea_long(result, "USER_BUT"), linea_long(result, "USER_MOT")) == (button, motion)
    assert (result.field("AES", "OLD_BUTTON"), result.field("AES", "OLD_MOTION")) == (VDI_DEFAULT_ROUTINE,) * 2


def test_gsx_setmb_reads_each_displaced_routine_after_its_own_call():
    """The button's old routine is contrl[9..10] after vex_butv, the motion's after vex_motv: two different routines
    staged in, two different ones kept — one read early, or late, would keep the other's."""
    pokes = merge_pokes(vdi.linea_pokes(USER_BUT=OTHER_BUTTON, USER_MOT=OTHER_MOTION), STALE_OLD)
    result = gsx.run_gsx("AES_ROM_GSX_SETMB", (addrs.AES_ROM_BUTTON_GLUE, addrs.AES_ROM_MOTION_GLUE, 0), pokes)
    assert (result.field("AES", "OLD_BUTTON"), result.field("AES", "OLD_MOTION")) == (OTHER_BUTTON, OTHER_MOTION)


def test_gsx_setmb_aes_installs_the_aes_s_interrupt_glue():
    result = gsx.run_gsx("AES_ROM_GSX_SETMB_AES", (), merge_pokes(DEFAULT_ROUTINES, STALE_OLD))
    assert (linea_long(result, "USER_BUT"), linea_long(result, "USER_MOT")) == (addrs.AES_ROM_BUTTON_GLUE,
                                                                                addrs.AES_ROM_MOTION_GLUE)
    assert result.field("AES", "OLD_BUTTON") == VDI_DEFAULT_ROUTINE


def test_gsx_resetmb_puts_the_displaced_routines_back():
    """The snapshot's: the AES's glue installed, the VDI's defaults kept — two different olds staged, so a swap shows."""
    pokes = aes.field_pokes("AES", OLD_BUTTON=OTHER_BUTTON, OLD_MOTION=OTHER_MOTION)
    result = gsx.run_gsx("AES_ROM_GSX_RESETMB", (), pokes)
    assert (linea_long(result, "USER_BUT"), linea_long(result, "USER_MOT")) == (OTHER_BUTTON, OTHER_MOTION)


# ---- the escapes and the graphics mode --------------------------------------------------------------------------
STALE_SUBFUNCTION = aes.stale_fields("GSX_SUBFUNCTION")


V_EXIT_CUR, V_ENTER_CUR, VQ_CHCELLS = (vdi_escape.ARMS[name] for name in ("V_EXIT_CUR", "V_ENTER_CUR", "VQ_CHCELLS"))
POISON_OF_ESCAPE = {V_EXIT_CUR: UNPOISONED, V_ENTER_CUR: {}}


@THROUGH
@pytest.mark.parametrize("escape", (V_EXIT_CUR, V_ENTER_CUR), ids=("v_exit_cur", "v_enter_cur"))
def test_gsx_escapes_makes_the_escape(escape, through_line_f):
    """The snapshot's console: the screen cleared, the alpha cursor locked (2) or shown (3)."""
    result = gsx.run_gsx("AES_ROM_GSX_ESCAPES", (escape,), STALE_SUBFUNCTION, through_line_f=through_line_f,
                         **POISON_OF_ESCAPE[escape])
    assert result.field("AES", "GSX_SUBFUNCTION") == escape
    assert atoms.contrl_of(result) == (addrs.VDI_ROM_ESCAPE_OPCODE, 0, 0, atoms.AES_HANDLE)


def test_gsx_escapes_of_an_inquiry_the_vdi_answers():
    """vq_chcells, which answers rows and columns: an escape that only answers, so the pass runs."""
    result = gsx.run_gsx("AES_ROM_GSX_ESCAPES", (VQ_CHCELLS,), STALE_SUBFUNCTION)
    assert result.field("AES", "GSX_SUBFUNCTION") == VQ_CHCELLS


GRAPHIC, ALPHA = aes.GSX_GRAPHIC, aes.GSX_ALPHA


@THROUGH
@pytest.mark.parametrize("mode", (GRAPHIC, ALPHA, 0xFFFF), ids=("graphics", "alpha", "-1"))
def test_gsx_graphic_in_the_mode_held_does_nothing(mode, through_line_f):
    """A WORD compare: gl_graphic staged equal to the mode asked (-1 as $ffff) — no escape, no exchange."""
    pokes = merge_pokes(STALE_SUBFUNCTION, aes.field_pokes("AES", GL_GRAPHIC=mode))
    result = gsx.run_gsx("AES_ROM_GSX_GRAPHIC", (aes.signed(mode),), pokes, through_line_f=through_line_f)
    assert result.field("AES", "GSX_SUBFUNCTION") == aes.STALE_WORD


@THROUGH
def test_gsx_graphic_into_alpha_mode_shows_the_alpha_cursor_and_gives_the_mouse_back(through_line_f):
    """What the shell does before a TOS program: escape 3 (the screen cleared, the cursor on), the routines the AES
    displaced put back."""
    pokes = merge_pokes(STALE_SUBFUNCTION, aes.field_pokes("AES", GL_GRAPHIC=GRAPHIC))
    result = gsx.run_gsx("AES_ROM_GSX_GRAPHIC", (ALPHA,), pokes, through_line_f=through_line_f)
    assert result.field("AES", "GL_GRAPHIC") == ALPHA and result.field("AES", "GSX_SUBFUNCTION") == V_ENTER_CUR
    assert linea_long(result, "USER_BUT") == VDI_DEFAULT_ROUTINE


def test_gsx_graphic_compares_the_whole_word():
    """gl_graphic $0100 and the mode 0: their low bytes agree, their words do not — so it is a change, into alpha."""
    pokes = merge_pokes(STALE_SUBFUNCTION, aes.field_pokes("AES", GL_GRAPHIC=0x0100))
    result = gsx.run_gsx("AES_ROM_GSX_GRAPHIC", (ALPHA,), pokes)
    assert result.field("AES", "GL_GRAPHIC") == ALPHA and result.field("AES", "GSX_SUBFUNCTION") == V_ENTER_CUR


@pytest.mark.parametrize("mode", (GRAPHIC, 2), ids=("1", "any other word but 0"))
def test_gsx_graphic_back_into_graphics_takes_the_mouse(mode):
    """...and back: escape 2, the AES's glue in, the VDI's defaults kept."""
    pokes = merge_pokes(STALE_SUBFUNCTION, STALE_OLD, DEFAULT_ROUTINES, aes.field_pokes("AES", GL_GRAPHIC=ALPHA))
    result = gsx.run_gsx("AES_ROM_GSX_GRAPHIC", (mode,), pokes, **UNPOISONED)
    assert result.field("AES", "GL_GRAPHIC") == mode and result.field("AES", "GSX_SUBFUNCTION") == V_EXIT_CUR
    assert linea_long(result, "USER_BUT") == addrs.AES_ROM_BUTTON_GLUE
    assert result.field("AES", "OLD_BUTTON") == VDI_DEFAULT_ROUTINE


def test_alpha_then_graphics_is_the_aes_s_mouse_again():
    """A SEQUENCE through `case.continued`: into alpha mode from the snapshot, back into graphics from where it
    ended — the AES's glue installed again, the defaults it gave back kept again."""
    alpha = gsx.run_gsx("AES_ROM_GSX_GRAPHIC", (ALPHA,), aes.field_pokes("AES", OLD_BUTTON=VDI_DEFAULT_ROUTINE,
                                                                        OLD_MOTION=VDI_DEFAULT_ROUTINE))
    graphic = gsx.run_gsx("AES_ROM_GSX_GRAPHIC", (GRAPHIC,), onto=merge_pokes(case.continued(alpha), STALE_OLD),
                          **UNPOISONED)
    assert linea_long(graphic, "USER_MOT") == addrs.AES_ROM_MOTION_GLUE
    assert graphic.field("AES", "OLD_MOTION") == VDI_DEFAULT_ROUTINE


# ---- the cursor and the tick ---------------------------------------------------------------------------------------
@THROUGH
def test_ratinit_shows_the_cursor_and_clears_the_nest(through_line_f):
    """The door's machine (the VDI's depth 1, the AES's nest 1): v_show_c(0) takes the depth to 0 and draws."""
    result = gsx.run_gsx("AES_ROM_RATINIT", (), {INTIN: vdi.pack_words(aes.STALE_WORD)}, through_line_f=through_line_f)
    assert result.field("AES", "GL_MOFF") == 0 and result.word(INTIN) == 0
    assert atoms.screen_changed(result)


def test_ratinit_over_a_nest_of_two():
    """v_show_c(0) shows the cursor WHATEVER the VDI's depth (it takes the depth to 1 first, $fcb136): staged 2, it
    ends 0 and drawn — and the AES's nest is 0 too."""
    pokes = merge_pokes(vdi.linea_pokes(M_HID_CT=2), aes.field_pokes("AES", GL_MOFF=2))
    result = gsx.run_gsx("AES_ROM_RATINIT", (), pokes)
    assert result.field("AES", "GL_MOFF") == 0 and vdi.linea(result.final, "M_HID_CT") == 0
    assert atoms.screen_changed(result)


TICK_ROUTINE = addrs.AES_ROM_TICK_GLUE     # the routine the AES's start-up hands vex_timv
OTHER_TIMER = 0x0034_5678               # a displaced routine whose two words differ from each other and the period
TICK_POKES = merge_pokes(gemdos.machine(), {leaves.ANSWERS: vdi.pack_words(*[aes.STALE_WORD] * 2)},
                         {aes.AES_GSX_INTOUT: vdi.pack_words(aes.STALE_WORD, aes.STALE_WORD)})


@THROUGH
def test_gsx_tick_installs_the_timer_routine_and_answers_the_period(through_line_f):
    old_routine = vdi.linea(BASE_IMAGE, "USER_TIM")
    result = gsx.run_gsx("AES_ROM_GSX_TICK", (TICK_ROUTINE, leaves.ANSWERS), merge_pokes(
        TICK_POKES, vdi.linea_pokes(USER_TIM=vdi.STALE_LONG)), through_line_f=through_line_f, **UNPOISONED)
    assert linea_long(result, "USER_TIM") == TICK_ROUTINE and result.long(leaves.ANSWERS) == vdi.STALE_LONG
    assert result.answer() & 0xFFFF == case.word_in(BASE_IMAGE, addrs.SYSVAR_TIMR_MS)
    assert old_routine != vdi.STALE_LONG


@pytest.mark.parametrize("offset, half", ((-WORD_BYTES, "low"), (0, "high")), ids=("over intout[-1..0]", "at intout"))
def test_gsx_tick_reads_intout_after_storing_the_old_routine(offset, half):
    """The ORDER: `old` laid over intout, so the word answered is half the routine just stored there — not the
    period vex_timv answered."""
    result = gsx.run_gsx("AES_ROM_GSX_TICK", (TICK_ROUTINE, aes.AES_GSX_INTOUT + offset), merge_pokes(
        TICK_POKES, vdi.linea_pokes(USER_TIM=OTHER_TIMER)), **UNPOISONED)
    expected = OTHER_TIMER & 0xFFFF if half == "low" else OTHER_TIMER >> 16
    assert result.answer() & 0xFFFF == expected


def test_gsx_tick_s_pointer_is_put_on_the_bus():
    result = gsx.run_gsx("AES_ROM_GSX_TICK", (TICK_ROUTINE, leaves.ANSWERS | aes.BUS_TAG), TICK_POKES, **UNPOISONED)
    assert result.long(leaves.ANSWERS) == vdi.linea(BASE_IMAGE, "USER_TIM")


def test_gsx_tick_through_an_odd_pointer_is_an_address_error_on_the_host():
    """The child binds no VDI function, so the call is made on a handle no workstation has — the dispatcher's arm
    that calls nothing (`test_aes_gsx.py`'s arrangement) — and the old routine is stored after it."""
    gsx.odd_pointer_refused("aes_gsx_tick", [gsx.pointer(TICK_ROUTINE), gsx.pointer(leaves.ANSWERS + 1)],
                            merge_pokes(TICK_POKES, aes.field_pokes("AES", GL_HANDLE=atoms.UNKNOWN_HANDLE)))


# ---- the workstation: v_opnwk, gsx_wsopen, gsx_start, gsx_init, gsx_wsclose ----------------------------------------
# Every machine that opens: the OS traps v_opnwk takes framed in the dropped band, the shifter's mode declared.
OPEN_POKES = screen.trap_pokes()
WORKSTATION_FIELDS = ("GL_HANDLE", "GL_RESTYPE", "GL_RSCHANGE", "GL_GRAPHIC")
# (the device code staged in gl_restype, the shifter's mode, the device code it is left): each resolution's own.
RESOLUTIONS = {
    "low (the snapshot's)": (aes.GSX_RESTYPE_LOW, addrs.SHIFTER_MODE_LOW, aes.GSX_RESTYPE_LOW),
    "medium": (aes.GSX_RESTYPE_MEDIUM, addrs.SHIFTER_MODE_MEDIUM, aes.GSX_RESTYPE_MEDIUM),
    "high": (aes.GSX_RESTYPE_HIGH, addrs.SHIFTER_MODE_HIGH, aes.GSX_RESTYPE_HIGH),
}


# Device 1, "the current mode", in each: the workstation opens in the shifter's mode and gl_restype is SET from the
# size answered — a code different from the one staged, so the store shows (in RESOLUTIONS it is the same word).
KEEP_THE_MODE = 1


def open_machine(device, mode, pokes=None):
    """`(pokes, io_seed)`: the door's machine with gl_restype `device` over a shifter in `mode`, `pokes` over it."""
    return merge_pokes(OPEN_POKES, aes.field_pokes("AES", GL_RESTYPE=device), pokes), ws.opnwk_io(mode)


def wsopen_intin(device):
    """gsx_wsopen's intin: GSX_OPEN_WORDS attribute words, the device code over the first, then the coordinates'."""
    return [device, *[aes.GSX_OPEN_ATTRIBUTE] * (aes.GSX_OPEN_WORDS - 1), aes.GSX_OPEN_COORDINATES]


@pytest.mark.parametrize("device, mode, restype", RESOLUTIONS.values(), ids=RESOLUTIONS)
def test_gsx_wsopen_opens_the_physical_workstation(device, mode, restype):
    """No Line-F word calls it — gsx_init reaches it by `bsr` — so it is entered directly alone."""
    pokes, io_seed = open_machine(device, mode, merge_pokes(
        aes.field_pokes("AES", GL_HANDLE=aes.STALE_WORD, GL_RSCHANGE=aes.STALE_WORD, GL_GRAPHIC=ALPHA),
        aes.stale_fields("GL_WS"), {INTIN: vdi.pack_words(*[aes.STALE_WORD] * 12)}))
    result = gsx.run_gsx("AES_ROM_GSX_WSOPEN", (), pokes, io_seed=io_seed, **UNPOISONED)
    assert [result.field("AES", name) for name in WORKSTATION_FIELDS[1:]] == [restype, 0, GRAPHIC]
    assert result.words(INTIN, 12) == [*wsopen_intin(device), aes.STALE_WORD]
    assert result.field("AES", "GL_HANDLE") == vdi.VDI_PHYS_HANDLE


@pytest.mark.parametrize("device, mode, restype", RESOLUTIONS.values(), ids=RESOLUTIONS)
def test_gsx_wsopen_sets_gl_restype_from_the_size_answered(device, mode, restype):
    pokes, io_seed = open_machine(KEEP_THE_MODE, mode, aes.field_pokes("AES", GL_RSCHANGE=aes.STALE_WORD, GL_GRAPHIC=ALPHA))
    result = gsx.run_gsx("AES_ROM_GSX_WSOPEN", (), pokes, io_seed=io_seed, **UNPOISONED)
    assert result.field("AES", "GL_RESTYPE") == restype != KEEP_THE_MODE


WORK_IN, WORK_OUT = leaves.WORK_IN_AT, leaves.WORK_OUT_AT
STALE_WORK_OUT = {WORK_OUT: vdi.pack_words(*[aes.STALE_WORD] * aes.AES_GL_WS_WORDS)}
OPEN_INTIN = {WORK_IN: vdi.pack_words(*wsopen_intin(aes.GSX_RESTYPE_LOW))}


def test_v_opnwk_points_the_block_at_the_caller_s_arrays_for_the_one_call():
    pokes, io_seed = open_machine(aes.GSX_RESTYPE_LOW, addrs.SHIFTER_MODE_LOW, merge_pokes(OPEN_INTIN, STALE_WORK_OUT,
                                                                         gsx.STALE_ANSWERS))
    result = gsx.run_gsx("AES_ROM_V_OPNWK", (WORK_IN, leaves.ANSWERS, WORK_OUT), pokes, io_seed=io_seed, **UNPOISONED)
    assert result.word(leaves.ANSWERS) == vdi.VDI_PHYS_HANDLE
    assert result.words(WORK_OUT, 2) == [319, 199]
    assert [result.field("AES", name) for name in ("GSX_PB_INTIN", "GSX_PB_INTOUT", "GSX_PB_PTSOUT", "GSX_PB_PTSIN")] == [
        aes.AES_GSX_INTIN, aes.AES_GSX_INTOUT, aes.AES_GSX_PTSOUT, aes.AES_GSX_PTSIN]


def test_v_opnwk_answers_the_handle_before_putting_the_pointers_back():
    """The ORDER: the handle's pointer at the low word of the block's INTOUT pointer — stored, then overwritten by
    the pointer put back. Put back first, the handle would be left in it."""
    pokes, io_seed = open_machine(aes.GSX_RESTYPE_LOW, addrs.SHIFTER_MODE_LOW, merge_pokes(OPEN_INTIN, STALE_WORK_OUT))
    handle_at = aes.field("AES", "GSX_PB_INTOUT").at + WORD_BYTES
    result = gsx.run_gsx("AES_ROM_V_OPNWK", (WORK_IN, handle_at, WORK_OUT), pokes, io_seed=io_seed, **UNPOISONED)
    assert result.field("AES", "GSX_PB_INTOUT") == aes.AES_GSX_INTOUT


def test_v_opnwk_s_handle_pointer_is_put_on_the_bus():
    pokes, io_seed = open_machine(aes.GSX_RESTYPE_LOW, addrs.SHIFTER_MODE_LOW, merge_pokes(OPEN_INTIN, STALE_WORK_OUT, gsx.STALE_ANSWERS))
    result = gsx.run_gsx("AES_ROM_V_OPNWK", (WORK_IN, leaves.ANSWERS | aes.BUS_TAG, WORK_OUT), pokes, io_seed=io_seed,
                         **UNPOISONED)
    assert result.word(leaves.ANSWERS) == vdi.VDI_PHYS_HANDLE


# The ARRAY pointers go into the block as they come, top byte and all, and the VDI's open reads work_in and answers
# work_out through them on the 24-bit bus.
@pytest.mark.parametrize("work_in_tag, work_out_tag", ((aes.BUS_TAG, 0), (0, aes.BUS_TAG), (aes.BUS_TAG, aes.BUS_TAG)),
                         ids=("work_in", "work_out", "both"))
def test_v_opnwk_s_array_pointers_are_put_on_the_bus(work_in_tag, work_out_tag):
    pokes, io_seed = open_machine(aes.GSX_RESTYPE_LOW, addrs.SHIFTER_MODE_LOW, merge_pokes(OPEN_INTIN, STALE_WORK_OUT,
                                                                         gsx.STALE_ANSWERS))
    result = gsx.run_gsx("AES_ROM_V_OPNWK", (WORK_IN | work_in_tag, leaves.ANSWERS, WORK_OUT | work_out_tag), pokes,
                         io_seed=io_seed, **UNPOISONED)
    assert result.word(leaves.ANSWERS) == vdi.VDI_PHYS_HANDLE
    assert result.words(WORK_OUT, 2) == [319, 199]
    assert [result.field("AES", name) for name in ("GSX_PB_INTIN", "GSX_PB_INTOUT")] == [aes.AES_GSX_INTIN,
                                                                                       aes.AES_GSX_INTOUT]


# Everything gsx_start writes, STALE first.
START_FIELDS = ("GL_LCOLOR", "GL_TCOLOR", "GL_DEAD_CACHE", "GL_MODE", "GL_FONT", "GL_PATT", "GL_FIS", "GL_XCLIP",
                "GL_YCLIP", "GL_WCLIP", "GL_HCLIP", "GL_WIDTH", "GL_HEIGHT", "GL_NPLANES", "GL_WPTSCHAR", "GL_HPTSCHAR",
                "GL_WCHAR", "GL_HCHAR", "GL_WSPTSCHAR", "GL_HSPTSCHAR", "GL_WSCHAR", "GL_HSCHAR", "GL_NCOLS",
                "GL_NROWS", "GL_HBOX", "GL_WBOX", "GL_RSCREEN", "GL_RFULL", "GL_RZERO", "GL_RMENU", "GL_RCENTER",
                "AD_INTIN")
for _name in START_FIELDS:
    _spec = aes.field("AES", _name)
    aes.declare_case_field(_spec.at, _spec.width * (_spec.count or 1), "a screen metric gsx_start sets")
STALE_START = aes.stale_fields(*START_FIELDS)


def grect(result, name):
    """A GRECT field's four words."""
    return result.words(aes.field("AES", name).at, 4)


@THROUGH
def test_gsx_start_sets_the_screen_s_metrics(through_line_f):
    """The snapshot's low-resolution workstation, 320 x 200 in 16 colours — its current font the one the AES's icon
    text last chose, so the cells are that font's."""
    result = gsx.run_gsx("AES_ROM_GSX_START", (), STALE_START, through_line_f=through_line_f, **UNPOISONED)
    assert all(result.field("AES", name) == 0xFFFF for name in START_FIELDS[:7])
    assert [result.field("AES", name) for name in ("GL_WIDTH", "GL_HEIGHT", "GL_NPLANES")] == [320, 200, 4]
    assert result.field("AES", "GL_NCOLS") == 320 // result.field("AES", "GL_WCHAR")
    assert result.field("AES", "GL_NROWS") == 200 // result.field("AES", "GL_HCHAR")
    hbox, wbox = result.field("AES", "GL_HBOX"), result.field("AES", "GL_WBOX")
    assert grect(result, "GL_RFULL") == [0, hbox, 320, 200 - hbox]
    assert grect(result, "GL_RCENTER") == [(320 - wbox) >> 1, (200 - 2 * hbox) >> 1, wbox, hbox]
    assert result.field("AES", "AD_INTIN") == INTIN


@pytest.mark.parametrize("device, mode", (RESOLUTIONS["medium"][:2], RESOLUTIONS["high"][:2]), ids=("medium", "high"))
def test_gsx_start_over_a_workstation_opened_in_another_resolution(device, mode):
    """A SEQUENCE: gsx_wsopen in medium (4 colours: 2 planes) or high (2: 1 plane, a 16-pixel font), then gsx_start
    from where it ended — every metric from a real workstation the reconstructed VDI opened too."""
    pokes, io_seed = open_machine(device, mode)
    opened = gsx.run_gsx("AES_ROM_GSX_WSOPEN", (), pokes, io_seed=io_seed, **UNPOISONED)
    result = gsx.run_gsx("AES_ROM_GSX_START", (), onto=merge_pokes(case.continued(opened), STALE_START), io_seed=io_seed,
                         **UNPOISONED)
    assert result.field("AES", "GL_NPLANES") == (2 if mode == addrs.SHIFTER_MODE_MEDIUM else 1)


@pytest.mark.parametrize("colours, planes", ((0, 0), (1, 0), (2, 1), (3, 1), (0x8000, 15)),
                         ids=("none", "one", "two", "three", "the top bit"))
def test_gsx_start_counts_planes_by_halving_the_colours(colours, planes):
    """`lsr.w` until zero, counting each halving that left any: a work_out[13] no workstation answers, staged — the
    loop's zero-trip, one-trip and fifteen-trip arms, and a count that is no power of two."""
    pokes = merge_pokes(STALE_START, ws_pokes(NCOLORS=colours))
    result = gsx.run_gsx("AES_ROM_GSX_START", (), pokes, **UNPOISONED)
    assert result.field("AES", "GL_NPLANES") == planes


def ws_pokes(**words):
    """gl_ws's words by their `aes/gsxif.h` index name less `GSX_WS_` (XRES=..., WPIXEL=...), staged."""
    return {aes.AES_GL_WS + aes.CONSTANTS["GSX_WS_" + name] * WORD_BYTES: vdi.pack_words(value)
            for name, value in words.items()}


def test_gsx_start_divides_the_cells_signed():
    """`ext.l` then `divs.w`: a work_out[0] past $7ffe makes a width that is NEGATIVE as a word, and the cells across
    are its signed quotient — an unsigned divide would answer a large positive count."""
    result = gsx.run_gsx("AES_ROM_GSX_START", (), merge_pokes(STALE_START, ws_pokes(XRES=0x9000)), **UNPOISONED)
    width, cell = result.field("AES", "GL_WIDTH"), result.field("AES", "GL_WCHAR")
    assert result.field("AES", "GL_NCOLS") == int(aes.signed(width) / cell) & 0xFFFF


def test_gsx_start_keeps_the_product_s_low_word_when_the_box_overflows():
    """The box's `divs.w` OVERFLOWING — a pixel 32767 microns high over one 1 micron wide: the quotient does not fit a
    word, so the 68000 leaves the register as it was, and gl_wbox is the product's low word."""
    result = gsx.run_gsx("AES_ROM_GSX_START", (), merge_pokes(STALE_START, ws_pokes(WPIXEL=1, HPIXEL=0x7FFF)),
                         **UNPOISONED)
    hbox = result.field("AES", "GL_HBOX")
    assert result.field("AES", "GL_WBOX") == (0x7FFF * hbox) & 0xFFFF


def test_a_zero_pixel_width_is_the_zero_divide_on_the_host():
    """work_out[3] = 0: the box's `divs.w` takes vector 5 on the 68000; the host refuses it by name. The child binds
    no VDI function, so every call is made on a handle no workstation has (the dispatcher's arm that calls nothing)."""
    pokes = gsx.machine(merge_pokes(ws_pokes(WPIXEL=0), aes.field_pokes("AES", GL_HANDLE=atoms.UNKNOWN_HANDLE),
                                    {PTSOUT: vdi.pack_words(6, 6, 8, 8)}))
    returncode, stderr, _image = vdi_helpers.refusal_over("aes_gsx_start", pokes, read_back=False)
    assert returncode != 0 and "divs.w by zero" in stderr, stderr


INIT_FIELDS = ("GL_HANDLE", "GL_RSCHANGE", "OLD_BUTTON", "OLD_MOTION", "XRAT", "YRAT")


@THROUGH
def test_gsx_init_opens_starts_and_takes_the_mouse(through_line_f):
    """The AES's start-up over the snapshot's machine, the mouse's routines the VDI's defaults as v_opnwk leaves
    them: the workstation reopened, the metrics set, the AES's glue in, the mouse's position read."""
    pokes, io_seed = open_machine(aes.GSX_RESTYPE_LOW, addrs.SHIFTER_MODE_LOW, merge_pokes(STALE_START, aes.stale_fields(*INIT_FIELDS)))
    result = gsx.run_gsx("AES_ROM_GSX_INIT", (), pokes, io_seed=io_seed, through_line_f=through_line_f, **UNPOISONED)
    assert linea_long(result, "USER_BUT") == addrs.AES_ROM_BUTTON_GLUE
    assert (result.field("AES", "XRAT"), result.field("AES", "YRAT")) == tuple(
        vdi.linea(result.final, name) for name in ("GCURX", "GCURY"))


@THROUGH
def test_gsx_wsclose_closes_the_physical_workstation(through_line_f):
    pokes = merge_pokes(OPEN_POKES, aes.stale_fields("GSX_OPCODE"))
    result = gsx.run_gsx("AES_ROM_GSX_WSCLOSE", (), pokes, through_line_f=through_line_f, **UNPOISONED)
    assert atoms.contrl_of(result)[0] == addrs.VDI_ROM_V_CLSWK_OPCODE


# ---- the registry ---------------------------------------------------------------------------------------------------
# Every routine priced on its realistic shapes (mechanism (V): the VDI and the OS under it in neither column), each
# entered once through its callers' Line-F word where one calls it (verified, unpriced). The opens are the heaviest
# rows of the AES (v_opnwk ~400,000 cycles), priced once per resolution.
_LOW = open_machine(aes.GSX_RESTYPE_LOW, addrs.SHIFTER_MODE_LOW)
_ROWS = {
    ("AES_ROM_GSX_SETMB", "the AES's glue over the defaults"): (
        (addrs.AES_ROM_BUTTON_GLUE, addrs.AES_ROM_MOTION_GLUE, aes.AES_DRWADDR), merge_pokes(DEFAULT_ROUTINES, STALE_OLD), None),
    ("AES_ROM_GSX_SETMB_AES", "over the defaults"): ((), merge_pokes(DEFAULT_ROUTINES, STALE_OLD), None),
    ("AES_ROM_GSX_RESETMB", "the defaults back"): ((), None, None),
    ("AES_ROM_GSX_ESCAPES", "v_exit_cur"): ((V_EXIT_CUR,), STALE_SUBFUNCTION, None),
    ("AES_ROM_GSX_ESCAPES", "v_enter_cur"): ((V_ENTER_CUR,), STALE_SUBFUNCTION, None),
    ("AES_ROM_GSX_GRAPHIC", "the mode held"): ((GRAPHIC,), None, None),
    ("AES_ROM_GSX_GRAPHIC", "into alpha mode"): ((ALPHA,), aes.field_pokes("AES", GL_GRAPHIC=GRAPHIC), None),
    ("AES_ROM_GSX_GRAPHIC", "back into graphics"): ((GRAPHIC,), merge_pokes(STALE_OLD, DEFAULT_ROUTINES, aes.field_pokes(
        "AES", GL_GRAPHIC=ALPHA)), None),
    ("AES_ROM_RATINIT", "the cursor shown again"): ((), None, None),
    ("AES_ROM_GSX_TICK", "the AES's timer glue"): ((TICK_ROUTINE, leaves.ANSWERS), TICK_POKES, None),
    ("AES_ROM_GSX_WSCLOSE", "the physical workstation"): ((), OPEN_POKES, None),
    ("AES_ROM_GSX_START", "the snapshot's workstation"): ((), STALE_START, None),
}
for (_name, _label), (_arguments, _pokes, _io_seed) in _ROWS.items():
    gsx.register(_label, _name, _arguments, _pokes, io_seed=_io_seed)
for _label, (_device, _mode, _restype) in RESOLUTIONS.items():
    _pokes, _io_seed = open_machine(_device, _mode)
    gsx.register(_label, "AES_ROM_GSX_WSOPEN", (), _pokes, io_seed=_io_seed)
gsx.register("into the AES's arrays", "AES_ROM_V_OPNWK", (WORK_IN, leaves.ANSWERS, WORK_OUT),
             merge_pokes(_LOW[0], OPEN_INTIN, STALE_WORK_OUT), io_seed=_LOW[1])
gsx.register("the AES's start-up", "AES_ROM_GSX_INIT", (), merge_pokes(_LOW[0], STALE_START), io_seed=_LOW[1])
_LINE_F_ROWS = (("AES_ROM_GSX_ESCAPES", "v_exit_cur"), ("AES_ROM_GSX_GRAPHIC", "into alpha mode"),
                ("AES_ROM_RATINIT", "the cursor shown again"), ("AES_ROM_GSX_TICK", "the AES's timer glue"),
                ("AES_ROM_GSX_WSCLOSE", "the physical workstation"), ("AES_ROM_GSX_START", "the snapshot's workstation"))
for _key in _LINE_F_ROWS:
    _arguments, _pokes, _io_seed = _ROWS[_key]
    gsx.register(_key[1], _key[0], _arguments, _pokes, through_line_f=True, io_seed=_io_seed)
gsx.register("the AES's start-up", "AES_ROM_GSX_INIT", (), merge_pokes(_LOW[0], STALE_START), io_seed=_LOW[1],
             through_line_f=True)
