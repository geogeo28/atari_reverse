"""AES gsx2 ($fecb5a) and the VDI binding's atoms (gemgsxif) — `src/aes/gsx.c`, through `test/aes_gsx.py`'s door.

    gsx2        pb[0] = contrl; D0 = $73, D1 = pb; trap #2                        (the bridge, `aes/gsx.h`)
    gsx_ncode   contrl[0,1] = op, n_ptsin (one longword); contrl[3] = n_intin; contrl[6] = gl_handle; jmp gsx2
    gsx_1code   intin[0] = value; gsx_ncode(op, 0, 1)
    gsx_moff    if !gl_moff: v_hide_c, PTSIN back, gl_mouse_shown = 0;  gl_moff += 1
    gsx_mon     gl_moff -= 1 (a word); if zero: v_show_c(1), gl_mouse_shown = 1
    wrappers    their words into intin/ptsin, PTSIN at the caller's points and contrl[7..10] at its MFDBs for the
                one call (the 3-byte rows of $fe8bdc), PTSIN put back at the AES's ptsin after it
    vst_height  ptsin = (0, h); then ptsout's four words through the four pointers, each read after the store before
    gsx_fix     the MFDB's address stored, then 0: the screen's size from work_out, its planes; else a one-plane form

Every atom is hand 68000 returning by `rts`, so the Line-F mask word is never stored; each is also entered through
its callers' own Line-F word once. Every case runs in the cursor-hidden machine unless it says otherwise, and the
WHOLE image is compared — the screen included — against the ROM's VDI on one side and the VDI's C cores on the other.
"""
import pytest

from harness import BASE_IMAGE, addrs, make_image
from recreate_kit.os_map import OS_BUS_ADDR_MASK

import aes
import aes_gsx as gsx
import case
import vdi
import vdi_gtext
import vdi_helpers
from case import merge_pokes

IMAGE, WORD, LONG = vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.LONG_ARG
SIGNATURES = {
    "AES_ROM_GSX2": (aes.WORD_ANSWER, (IMAGE,)),
    "AES_ROM_GSX_NCODE": (aes.WORD_ANSWER, (IMAGE, WORD, WORD, WORD)),
    "AES_ROM_GSX_1CODE": (aes.WORD_ANSWER, (IMAGE, WORD, WORD)),
    "AES_ROM_GSX_MOFF": (None, (IMAGE,)),
    "AES_ROM_GSX_MON": (None, (IMAGE,)),
    "AES_ROM_V_PLINE": (aes.WORD_ANSWER, (IMAGE, WORD, LONG)),
    "AES_ROM_VS_CLIP": (aes.WORD_ANSWER, (IMAGE, WORD, LONG)),
    "AES_ROM_VST_HEIGHT": (aes.WORD_ANSWER, (IMAGE, WORD, LONG, LONG, LONG, LONG)),
    "AES_ROM_VR_RECFL": (aes.WORD_ANSWER, (IMAGE, LONG, LONG)),
    "AES_ROM_VRO_CPYFM": (aes.WORD_ANSWER, (IMAGE, WORD, LONG, LONG, LONG)),
    "AES_ROM_VRT_CPYFM": (aes.WORD_ANSWER, (IMAGE, WORD, LONG, LONG, LONG, WORD, WORD)),
    "AES_ROM_VRN_TRNFM": (aes.WORD_ANSWER, (IMAGE, LONG, LONG)),
    "AES_ROM_VSL_WIDTH": (aes.WORD_ANSWER, (IMAGE, WORD)),
    "AES_ROM_GSX_FIX": (None, (IMAGE, LONG, LONG, WORD, WORD)),
}
for _name, (_restype, _argtypes) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, _argtypes)

THROUGH = pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
SCREEN = vdi.SCREEN
INTIN, PTSIN, PTSOUT = aes.AES_GSX_INTIN, aes.AES_GSX_PTSIN, aes.AES_GSX_PTSOUT
POINTS, ANSWERS = gsx.POINTS_AT, gsx.ANSWERS_AT
AES_HANDLE = case.word_in(BASE_IMAGE, aes.AES_GL_HANDLE)
UNKNOWN_HANDLE = AES_HANDLE + 7         # no workstation of the snapshot's has it


def screen_changed(result):
    """Whether the run changed the screen its case staged — a drawing case's evidence that it drew at all."""
    return vdi_gtext.screen_changed(result, make_image(result.staged))


def contrl_of(result):
    """contrl[0, 1, 3, 6] as the call left them: the words the binding writes."""
    return tuple(result.field("AES", name) for name in ("GSX_OPCODE", "GSX_N_PTSIN", "GSX_N_INTIN", "GSX_HANDLE"))


def ptsin_pointer(result):
    return result.field("AES", "GSX_PB_PTSIN")


# THE ATTRIBUTION PASS IS OFF for a call whose wrapper does NOT set PTSIN and still hands the VDI points — vst_height
# and vsl_width, the table's rows with points: the VDI reads the block's PTSIN as the machine left it, and the wrapper
# stores it only AFTER the call — so the pass, which inverts every byte the ROM's run stored before the run, hands the
# VDI $ffff673b and both sides read the I/O page (measured: the oracle refuses 2-4 unmodelled reads; every other case
# here runs poisoned). What stands in for the pass: each wrapper's `a PTSIN left elsewhere` case, whose staged PTSIN
# differs from the one the call stores back.
#
# THE PASS IS VACUOUS ON gsx_moff's AND gsx_mon's CALL ARMS, though it runs: gl_moff is an input and an output of both,
# so the pass inverts the nest (0 -> $ffff, 1 -> $fffe) and the ROM's poisoned run takes the COUNTER-ONLY path, storing
# nothing the call arm would (measured: PTSIN ends the same on both sides). What pins those arms is staging alone — a
# case that stages every word the arm stores to something else: PTSIN elsewhere and the flag stale for v_hide_c, intin
# and the flag stale for v_show_c.
PTSIN_READ_BEFORE_IT_IS_PUT_BACK = vdi.READS_A_POINTER_IT_WRITES


# ---- the bridge -----------------------------------------------------------------------------------------------------
def vsl_color_pokes(colour):
    """contrl and intin of a vsl_color call on the AES's own handle, as gsx_1code would leave them for gsx2."""
    return merge_pokes(aes.field_pokes("AES", GSX_OPCODE=addrs.VDI_ROM_VSL_COLOR_OPCODE, GSX_N_PTSIN=0, GSX_N_INTIN=1,
                                       GSX_HANDLE=AES_HANDLE), {INTIN: vdi.pack_words(colour)})


@THROUGH
def test_gsx2_stores_the_contrl_pointer_and_traps(through_line_f):
    """The block's contrl pointer staged stale: gsx2 stores it, and the VDI call it carries (vsl_color 3) lands."""
    result = gsx.run_gsx("AES_ROM_GSX2", (), merge_pokes(vsl_color_pokes(3), aes.field_pokes("AES", GSX_PB_CONTRL=vdi.STALE_LONG)),
                         through_line_f=through_line_f)
    assert result.field("AES", "GSX_PB_CONTRL") == aes.AES_GSX_CONTRL
    assert result.info["ret"] & 0xFFFF == result.answer() & 0xFFFF      # the candidate's answer, the ROM's D0


def test_gsx2_draws_a_polyline_staged_by_hand():
    """A drawing call through the bare gsx2: contrl and the block's PTSIN staged as v_pline's wrapper would."""
    pokes = merge_pokes(aes.field_pokes("AES", GSX_OPCODE=addrs.VDI_ROM_V_PLINE_OPCODE, GSX_N_PTSIN=2, GSX_N_INTIN=0,
                                        GSX_HANDLE=AES_HANDLE, GSX_PB_PTSIN=POINTS), gsx.points_pokes(10, 20, 200, 120))
    assert screen_changed(gsx.run_gsx("AES_ROM_GSX2", (), pokes))


def test_a_handle_no_workstation_has_calls_nothing():
    """The VDI's own refusal arm, reached through the AES: contrl[6] naming no open workstation returns having called
    nothing — the dispatcher's walk, run on both shores."""
    pokes = merge_pokes(vsl_color_pokes(3), aes.field_pokes("AES", GSX_HANDLE=UNKNOWN_HANDLE))
    gsx.run_gsx("AES_ROM_GSX2", (), pokes)


# Both hops of the trap are RAM; a case that repoints either is refused by name on the host — never served by the
# reconstructed VDI as if the vector still named it.
@pytest.mark.parametrize("vector, hop", ((addrs.VECTOR_TRAP_GEM, "vector $88"), (addrs.SYSVAR_VDI_ENTRY, "SYSVAR_VDI_ENTRY")),
                         ids=("trap #2 vector", "SYSVAR_VDI_ENTRY"))
def test_a_repointed_hop_halts_the_bridge_on_the_host(vector, hop):
    pokes = merge_pokes(gsx.machine(vsl_color_pokes(3)), {vector: (gsx.BAND_AT).to_bytes(aes.LONG_BYTES, "big")})
    returncode, stderr, _image = vdi_helpers.refusal_over("aes_gsx2", pokes, read_back=False)
    assert returncode != 0 and hop in stderr and "the AES's trap #2" in stderr, stderr


def test_the_snapshot_s_hops_are_the_ones_the_bridge_checks():
    assert case.long_in(BASE_IMAGE, addrs.VECTOR_TRAP_GEM) == addrs.GEM_TRAP2
    assert case.long_in(BASE_IMAGE, addrs.SYSVAR_VDI_ENTRY) == addrs.GEM_TRAP2_VDI_DOOR


# ---- gsx_ncode and gsx_1code: every attribute call the AES's graphics make, end to end ---------------------------
# (opcode, value): one intin word each, through gsx_1code — the call shape gsx_attr, gsx_start and bb_fill make.
ONE_WORD_CALLS = {
    "vsl_type 7 (user)": (addrs.VDI_ROM_VSL_TYPE_OPCODE, 7),
    "vsl_color 2": (addrs.VDI_ROM_VSL_COLOR_OPCODE, 2),
    "vst_color 3": (addrs.VDI_ROM_VST_COLOR_OPCODE, 3),
    "vsf_interior 2 (pattern)": (addrs.VDI_ROM_VSF_INTERIOR_OPCODE, 2),
    "vsf_style 4": (addrs.VDI_ROM_VSF_STYLE_OPCODE, 4),
    "vsf_color 1": (addrs.VDI_ROM_VSF_COLOR_OPCODE, 1),
    "vswr_mode 3 (XOR)": (addrs.VDI_ROM_VSWR_MODE_OPCODE, 3),
    "vsl_udsty $5555": (addrs.VDI_ROM_VSL_UDSTY_OPCODE, 0x5555),
    "v_show_c 1 over the hidden cursor": (addrs.VDI_ROM_V_SHOW_C_OPCODE, 1),
}


@pytest.mark.parametrize("call", sorted(ONE_WORD_CALLS))
def test_gsx_1code_makes_a_one_word_call(call):
    opcode, value = ONE_WORD_CALLS[call]
    result = gsx.run_gsx("AES_ROM_GSX_1CODE", (opcode, value))
    assert contrl_of(result) == (opcode, 0, 1, AES_HANDLE)
    assert result.word(INTIN) == value & 0xFFFF


@THROUGH
def test_gsx_1code_through_its_callers_word(through_line_f):
    result = gsx.run_gsx("AES_ROM_GSX_1CODE", (addrs.VDI_ROM_VSWR_MODE_OPCODE, 2), through_line_f=through_line_f)
    assert contrl_of(result) == (addrs.VDI_ROM_VSWR_MODE_OPCODE, 0, 1, AES_HANDLE)


TEXT = b"GEM"
# (opcode, points, words, pokes): the frame-built calls — no arguments, an inquiry answering intout and ptsout, and a
# text call with its points and characters staged where the AES keeps them.
NCODE_CALLS = {
    "vqt_attributes": (addrs.VDI_ROM_VQT_ATTRIBUTES_OPCODE, 0, 0, None),
    "vq_mouse": (addrs.VDI_ROM_VQ_MOUSE_OPCODE, 0, 0, None),
    "vsl_udsty, one word": (addrs.VDI_ROM_VSL_UDSTY_OPCODE, 0, 1, {INTIN: vdi.pack_words(0xF0F0)}),
    "v_gtext, three characters": (addrs.VDI_ROM_V_GTEXT_OPCODE, 1, len(TEXT),
                                  {INTIN: vdi.pack_words(*TEXT), PTSIN: vdi.pack_words(40, 60)}),
}


@pytest.mark.parametrize("call", sorted(NCODE_CALLS))
def test_gsx_ncode_fills_contrl_and_calls(call):
    opcode, points, words, pokes = NCODE_CALLS[call]
    result = gsx.run_gsx("AES_ROM_GSX_NCODE", (opcode, points, words), pokes)
    assert contrl_of(result) == (opcode, points, words, AES_HANDLE)


@THROUGH
def test_gsx_ncode_through_its_callers_word(through_line_f):
    result = gsx.run_gsx("AES_ROM_GSX_NCODE", (addrs.VDI_ROM_VQT_ATTRIBUTES_OPCODE, 0, 0), through_line_f=through_line_f)
    assert contrl_of(result) == (addrs.VDI_ROM_VQT_ATTRIBUTES_OPCODE, 0, 0, AES_HANDLE)


def test_gsx_ncode_reads_the_handle_after_storing_contrl():
    """The AES's handle is read when contrl[6] is written — a handle of 0 is the VDI's no-workstation arm."""
    result = gsx.run_gsx("AES_ROM_GSX_NCODE", (addrs.VDI_ROM_VQT_ATTRIBUTES_OPCODE, 0, 0),
                         aes.field_pokes("AES", GL_HANDLE=0))
    assert contrl_of(result)[3] == 0


def test_gsx_ncode_counts_are_words_that_go_negative():
    """Alcyon `int`s: a count of -1 is stored as $ffff — and as contrl[1] the VDI caps it at 512 points, unsigned."""
    result = gsx.run_gsx("AES_ROM_GSX_NCODE", (addrs.VDI_ROM_VQT_ATTRIBUTES_OPCODE, 0, -1), None)
    assert result.field("AES", "GSX_N_INTIN") == 0xFFFF


# ---- gsx_moff / gsx_mon: the AES's own hide nest over the VDI's ---------------------------------------------------
def nest_pokes(nest):
    return aes.field_pokes("AES", GL_MOFF=nest, GL_MOUSE_SHOWN=aes.STALE_WORD)


@THROUGH
def test_gsx_moff_hides_a_shown_cursor(through_line_f):
    """The snapshot's drawn arrow: v_hide_c restores its background from the save block, and the nest becomes 1."""
    result = gsx.run_gsx("AES_ROM_GSX_MOFF", (), nest_pokes(gsx.NEST_SHOWN), onto=gsx.shown_machine(),
                         through_line_f=through_line_f)
    assert result.field("AES", "GL_MOFF") == 1 and result.field("AES", "GL_MOUSE_SHOWN") == 0
    assert screen_changed(result)
    assert ptsin_pointer(result) == PTSIN


def test_gsx_moff_puts_back_a_ptsin_left_elsewhere():
    """The hide arm ($fe8a7c's call through $fe8bb6) puts PTSIN back — staged elsewhere, as the poison pass cannot
    (it steers the ROM onto the counter path): a hide that skipped the store-back leaves the staged pointer."""
    pokes = merge_pokes(nest_pokes(gsx.NEST_SHOWN), aes.field_pokes("AES", GSX_PB_PTSIN=POINTS))
    result = gsx.run_gsx("AES_ROM_GSX_MOFF", (), pokes, onto=gsx.shown_machine())
    assert ptsin_pointer(result) == PTSIN and result.field("AES", "GL_MOUSE_SHOWN") == 0


@pytest.mark.parametrize("nest", (1, 2, 0xFFFF), ids=("hidden once", "twice", "-1"))
def test_gsx_moff_only_counts_a_nest_already_open(nest):
    """Any non-zero nest — $ffff included — is counted, a WORD: -1 goes to 0 and nothing is called."""
    result = gsx.run_gsx("AES_ROM_GSX_MOFF", (), nest_pokes(nest))
    assert result.field("AES", "GL_MOFF") == (nest + 1) & 0xFFFF
    assert result.field("AES", "GL_MOUSE_SHOWN") == aes.STALE_WORD


@THROUGH
def test_gsx_mon_shows_the_cursor_when_the_nest_unwinds(through_line_f):
    """The hidden machine's nest of 1: v_show_c(1) redraws the arrow, the nest 0, the flag 1 — intin[0] and the flag
    staged stale, which the poison pass cannot do for this arm (it steers the ROM onto the counter path)."""
    pokes = merge_pokes({INTIN: vdi.pack_words(aes.STALE_WORD)}, aes.field_pokes("AES", GL_MOUSE_SHOWN=aes.STALE_WORD))
    result = gsx.run_gsx("AES_ROM_GSX_MON", (), pokes, through_line_f=through_line_f)
    assert result.field("AES", "GL_MOFF") == 0 and result.field("AES", "GL_MOUSE_SHOWN") == 1
    assert result.word(INTIN) == 1
    assert screen_changed(result)
    assert contrl_of(result) == (addrs.VDI_ROM_V_SHOW_C_OPCODE, 0, 1, AES_HANDLE)


@pytest.mark.parametrize("nest", (2, 0), ids=("twice", "none: wraps to -1"))
def test_gsx_mon_only_counts_while_the_nest_is_open(nest):
    """A nest of 2 counts to 1; a nest of 0 — an unmatched gsx_mon — wraps to $ffff, not zero, and shows nothing."""
    result = gsx.run_gsx("AES_ROM_GSX_MON", (), nest_pokes(nest))
    assert result.field("AES", "GL_MOFF") == (nest - 1) & 0xFFFF
    assert result.field("AES", "GL_MOUSE_SHOWN") == aes.STALE_WORD


def test_moff_then_mon_is_the_snapshot_s_cursor_again():
    """A SEQUENCE through `case.continued`: gsx_moff from the snapshot, gsx_mon from where it ended — the arrow drawn
    again where it was, both counters back."""
    hidden = gsx.run_gsx("AES_ROM_GSX_MOFF", (), onto=gsx.shown_machine())
    shown = gsx.run_gsx("AES_ROM_GSX_MON", (), onto=case.continued(hidden))
    assert shown.field("AES", "GL_MOFF") == 0
    base, end = SCREEN.base, SCREEN.base + SCREEN.bytes
    assert bytes(shown.final[base:end]) == bytes(BASE_IMAGE[base:end])


# ---- the wrappers ---------------------------------------------------------------------------------------------------
STALE_PTSIN = aes.field_pokes("AES", GSX_PB_PTSIN=vdi.STALE_LONG)
TRIANGLE = (20, 30, 120, 30, 70, 110, 20, 30)


@THROUGH
def test_v_pline_draws_through_the_caller_s_points(through_line_f):
    """PTSIN at the caller's points for the call, the AES's own after it; four points cross three segments."""
    result = gsx.run_gsx("AES_ROM_V_PLINE", (4, POINTS), merge_pokes(STALE_PTSIN, gsx.points_pokes(*TRIANGLE)),
                         through_line_f=through_line_f)
    assert contrl_of(result) == (addrs.VDI_ROM_V_PLINE_OPCODE, 4, 0, AES_HANDLE)
    assert ptsin_pointer(result) == PTSIN
    assert screen_changed(result)


def test_v_pline_s_points_pointer_is_put_on_the_bus():
    """The points pointer with a top byte, as an application's reaches the AES: stored as it is, the VDI drops it."""
    result = gsx.run_gsx("AES_ROM_V_PLINE", (2, POINTS | aes.BUS_TAG), gsx.points_pokes(10, 20, 200, 120))
    assert screen_changed(result)


def test_v_pline_over_the_aes_s_own_ptsin():
    """The caller's points ARE the AES's ptsin (gr_box hands it so): the same pointer stored, then stored back."""
    result = gsx.run_gsx("AES_ROM_V_PLINE", (2, PTSIN), {PTSIN: vdi.pack_words(5, 5, 300, 180)})
    assert ptsin_pointer(result) == PTSIN and screen_changed(result)


@THROUGH
def test_vs_clip_sets_the_workstation_s_clip(through_line_f):
    result = gsx.run_gsx("AES_ROM_VS_CLIP", (1, POINTS), merge_pokes(STALE_PTSIN, gsx.points_pokes(16, 24, 135, 83)),
                         through_line_f=through_line_f)
    assert contrl_of(result) == (addrs.VDI_ROM_VS_CLIP_OPCODE, 2, 1, AES_HANDLE)
    assert result.word(INTIN) == 1 and ptsin_pointer(result) == PTSIN


def test_vs_clip_off():
    result = gsx.run_gsx("AES_ROM_VS_CLIP", (0, POINTS), gsx.points_pokes(0, 0, 319, 199))
    assert result.word(INTIN) == 0


# vst_height: the four answers through four pointers, read out of ptsout one store at a time.
def answer_pointers(at=ANSWERS):
    return tuple(at + index * aes.WORD_BYTES for index in range(4))


@THROUGH
@pytest.mark.parametrize("height", (6, 13), ids=("the small font's", "the large font's"))
def test_vst_height_answers_through_its_four_pointers(height, through_line_f):
    pokes = merge_pokes({ANSWERS: vdi.pack_words(*[aes.STALE_WORD] * 4)})
    result = gsx.run_gsx("AES_ROM_VST_HEIGHT", (height, *answer_pointers()), pokes, through_line_f=through_line_f,
                         **PTSIN_READ_BEFORE_IT_IS_PUT_BACK)
    assert result.words(ANSWERS, 4) == result.words(PTSOUT, 4)
    assert result.words(PTSIN, 2) == [0, height]


def test_vst_height_reads_each_answer_after_the_store_before_it():
    """The ORDER, which only an overlap shows, for every link of the four: the pointers CHAIN through ptsout — the
    first is ptsout[1], the second ptsout[2], the third ptsout[3] — so each answer handed out is the word the store
    before it just wrote, and all four are the FIRST word. Any answer read early is its own ptsout word instead."""
    pointers = (*(PTSOUT + index * aes.WORD_BYTES for index in (1, 2, 3)), ANSWERS)
    result = gsx.run_gsx("AES_ROM_VST_HEIGHT", (13, *pointers), {ANSWERS: vdi.pack_words(*[aes.STALE_WORD] * 4)},
                         **PTSIN_READ_BEFORE_IT_IS_PUT_BACK)
    first = result.word(PTSOUT)
    assert result.words(PTSOUT, 4) == [first] * 4 and result.word(ANSWERS) == first


def test_vst_height_s_pointers_are_put_on_the_bus():
    result = gsx.run_gsx("AES_ROM_VST_HEIGHT", (6, *(at | aes.BUS_TAG for at in answer_pointers())), None,
                         **PTSIN_READ_BEFORE_IT_IS_PUT_BACK)
    assert result.words(ANSWERS, 4) == result.words(PTSOUT, 4)


def test_an_odd_answer_pointer_is_an_address_error_on_the_host():
    """A word stored at an odd address is the 68000's address error, which the oracle's Musashi does not raise: the
    host refuses it by name (`m68k_idioms.h`'s bus family). The child binds no VDI function, so the call is made on
    a handle no workstation has — the dispatcher's arm that calls nothing — and the answers are stored after it."""
    pointers = (ANSWERS + 1, *answer_pointers()[1:])
    arguments = (("ctypes.c_int16", "6"), *(("ctypes.c_uint32", str(at)) for at in pointers))
    pokes = gsx.machine(aes.field_pokes("AES", GL_HANDLE=UNKNOWN_HANDLE))
    returncode, stderr, _image = vdi_helpers.refusal_over("aes_vst_height", pokes, arguments=arguments, read_back=False)
    assert returncode != 0 and "address error" in stderr, stderr


@THROUGH
def test_vr_recfl_fills_with_its_mfdb_carried(through_line_f):
    pokes = merge_pokes(STALE_PTSIN, gsx.points_pokes(40, 50, 90, 80),
                        aes.field_pokes("AES", GSX_CONTRL_PTR=vdi.STALE_LONG))
    result = gsx.run_gsx("AES_ROM_VR_RECFL", (POINTS, gsx.mfdb_at(0)), pokes, through_line_f=through_line_f)
    assert contrl_of(result) == (addrs.VDI_ROM_VR_RECFL_OPCODE, 2, 1, AES_HANDLE)
    assert result.long(aes.AES_GSX_CONTRL_PTR) == gsx.mfdb_at(0)
    assert screen_changed(result)


def test_vr_recfl_s_pointers_are_put_on_the_bus():
    """Both pointers with a top byte: the points the VDI reads through the bus, and the MFDB pointer stored into
    contrl[7..8] AS IT IS — where it stays after the call."""
    pokes = merge_pokes(gsx.points_pokes(40, 50, 90, 80), vdi.mfdb_pokes(gsx.mfdb_at(0), **SCREEN_MFDB))
    result = gsx.run_gsx("AES_ROM_VR_RECFL", (POINTS | aes.BUS_TAG, gsx.mfdb_at(0) | aes.BUS_TAG), pokes)
    assert result.long(aes.AES_GSX_CONTRL_PTR) == gsx.mfdb_at(0) | aes.BUS_TAG
    assert screen_changed(result)


# The blits: the screen as an MFDB (address 0), and a one-plane form in memory.
SCREEN_MFDB = {"ADDR": 0}
FORM_WIDTH, FORM_HEIGHT = 16, 8
DESKTOP_Y = 40                          # a row of the desktop's pattern: not one colour across a form's width
FORM_WORDS = (0xF00F, 0x0FF0, 0xAAAA, 0x5555, 0xFFFF, 0x0000, 0x8001, 0x7FFE)


def form_mfdb(slot, address, *, stand=0, planes=1):
    return vdi.mfdb_pokes(gsx.mfdb_at(slot), ADDR=address, W=FORM_WIDTH, H=FORM_HEIGHT, WDWIDTH=1, STAND=stand,
                          NPLANES=planes)


def blit_pokes(source, destination, *corners):
    return merge_pokes(STALE_PTSIN, aes.field_pokes("AES", GSX_CONTRL_PTR=vdi.STALE_LONG, GSX_CONTRL_PTR2=vdi.STALE_LONG),
                       source, destination, gsx.points_pokes(*corners))


# The three blits as (arguments, pokes): ONE source for each case below and its registered row.
_FORM = gsx.form_at(0)
SCREEN_TO_SCREEN = ((3, POINTS, gsx.mfdb_at(0), gsx.mfdb_at(1)),
                    blit_pokes(vdi.mfdb_pokes(gsx.mfdb_at(0), **SCREEN_MFDB), vdi.mfdb_pokes(gsx.mfdb_at(1), **SCREEN_MFDB),
                               0, 0, 31, 15, 100, 100, 131, 115))
FORM_ONTO_THE_SCREEN = ((1, POINTS, gsx.mfdb_at(0), gsx.mfdb_at(1), 2, 5),
                        merge_pokes(blit_pokes(form_mfdb(0, _FORM), vdi.mfdb_pokes(gsx.mfdb_at(1), **SCREEN_MFDB),
                                               0, 0, FORM_WIDTH - 1, FORM_HEIGHT - 1,
                                               64, 64, 64 + FORM_WIDTH - 1, 64 + FORM_HEIGHT - 1),
                                    {_FORM: vdi.pack_words(*FORM_WORDS)}))
STANDARD_TO_DEVICE = ((gsx.mfdb_at(0), gsx.mfdb_at(1)),
                      merge_pokes(form_mfdb(0, _FORM, stand=1), form_mfdb(1, gsx.form_at(1)),
                                  {_FORM: vdi.pack_words(*FORM_WORDS)}, {gsx.form_at(1): bytes(gsx.FORM_BYTES)}))


@THROUGH
def test_vro_cpyfm_screen_to_screen(through_line_f):
    arguments, pokes = SCREEN_TO_SCREEN
    result = gsx.run_gsx("AES_ROM_VRO_CPYFM", arguments, pokes, through_line_f=through_line_f)
    assert contrl_of(result) == (addrs.VDI_ROM_VRO_CPYFM_OPCODE, 4, 1, AES_HANDLE)
    assert (result.long(aes.AES_GSX_CONTRL_PTR), result.long(aes.AES_GSX_CONTRL_PTR2)) == (gsx.mfdb_at(0), gsx.mfdb_at(1))
    assert screen_changed(result)


def test_vro_cpyfm_screen_into_a_form():
    """The save-under shape bb_save makes: a screen rectangle into a form in memory, its MFDB pointers on the bus."""
    form = gsx.form_at(0)
    pokes = blit_pokes(vdi.mfdb_pokes(gsx.mfdb_at(0), **SCREEN_MFDB),
                       vdi.mfdb_pokes(gsx.mfdb_at(1), ADDR=form, W=FORM_WIDTH, H=FORM_HEIGHT, WDWIDTH=1, STAND=0,
                                      NPLANES=SCREEN.planes),
                       0, DESKTOP_Y, FORM_WIDTH - 1, DESKTOP_Y + FORM_HEIGHT - 1, 0, 0, FORM_WIDTH - 1, FORM_HEIGHT - 1)
    pokes = merge_pokes(pokes, {form: bytes(gsx.FORM_BYTES)})
    result = gsx.run_gsx("AES_ROM_VRO_CPYFM", (3, POINTS, gsx.mfdb_at(0) | aes.BUS_TAG, gsx.mfdb_at(1) | aes.BUS_TAG),
                         pokes)
    assert result.after(form, gsx.FORM_BYTES) != bytes(gsx.FORM_BYTES)


@THROUGH
def test_vrt_cpyfm_a_one_plane_form_onto_the_screen(through_line_f):
    """gsx_blt's icon shape: a monochrome form drawn in two colours."""
    arguments, pokes = FORM_ONTO_THE_SCREEN
    pokes = merge_pokes(pokes, {INTIN: vdi.pack_words(*[aes.STALE_WORD] * 3)})
    result = gsx.run_gsx("AES_ROM_VRT_CPYFM", arguments, pokes, through_line_f=through_line_f)
    assert contrl_of(result) == (addrs.VDI_ROM_VRT_CPYFM_OPCODE, 4, 3, AES_HANDLE)
    assert result.words(INTIN, 3) == [1, 2, 5]
    assert screen_changed(result)


@THROUGH
def test_vrn_trnfm_a_standard_form_to_the_device_s(through_line_f):
    destination = gsx.form_at(1)
    arguments, pokes = STANDARD_TO_DEVICE
    pokes = merge_pokes(pokes, aes.field_pokes("AES", GSX_CONTRL_PTR=vdi.STALE_LONG, GSX_CONTRL_PTR2=vdi.STALE_LONG))
    result = gsx.run_gsx("AES_ROM_VRN_TRNFM", arguments, pokes, through_line_f=through_line_f)
    assert contrl_of(result) == (addrs.VDI_ROM_VR_TRNFM_OPCODE, 0, 0, AES_HANDLE)
    assert result.after(destination, gsx.FORM_BYTES) != bytes(gsx.FORM_BYTES)


@THROUGH
@pytest.mark.parametrize("width", (1, 3), ids=("1", "3"))
def test_vsl_width_sets_the_line_width(width, through_line_f):
    result = gsx.run_gsx("AES_ROM_VSL_WIDTH", (width,), {PTSIN: vdi.pack_words(aes.STALE_WORD, aes.STALE_WORD)},
                         through_line_f=through_line_f, **PTSIN_READ_BEFORE_IT_IS_PUT_BACK)
    assert contrl_of(result) == (addrs.VDI_ROM_VSL_WIDTH_OPCODE, 1, 0, AES_HANDLE)
    assert result.words(PTSIN, 2) == [width, 0]


# The two wrappers that never point PTSIN anywhere: (the routine, its arguments, the words staged where PTSIN was left).
PTSIN_LEFT_ELSEWHERE = {
    "vst_height": ("AES_ROM_VST_HEIGHT", (13, *answer_pointers()), gsx.points_pokes(0, 9)),
    "vsl_width": ("AES_ROM_VSL_WIDTH", (3,), gsx.points_pokes(5, 0)),
}


@pytest.mark.parametrize("name, arguments, points", PTSIN_LEFT_ELSEWHERE.values(), ids=PTSIN_LEFT_ELSEWHERE)
def test_a_ptsin_left_elsewhere_is_read_and_put_back(name, arguments, points):
    """vst_height and vsl_width never point PTSIN anywhere, so a PTSIN a caller left elsewhere is what the VDI reads
    (its words staged there) — and the AES's own is stored back after the call: a skipped store-back differs from the
    staged pointer."""
    pokes = merge_pokes(aes.field_pokes("AES", GSX_PB_PTSIN=POINTS), points)
    result = gsx.run_gsx(name, arguments, pokes, **PTSIN_READ_BEFORE_IT_IS_PUT_BACK)
    assert ptsin_pointer(result) == PTSIN


# ---- gsx_fix ------------------------------------------------------------------------------------------------------
def mfdb_of(result, at):
    return tuple(vdi.read_field(result.final, "MFDB", name, at) for name in ("ADDR", "W", "H", "WDWIDTH", "STAND", "NPLANES"))


STALE_MFDB = {gsx.mfdb_at(0): bytes([case.SLACK_FILL]) * aes.AES_MFDB_BYTES}
WORD_ZERO_FORM = 0x10000                # a form's address with its low word 0 (stored, never read through)


def fix(mfdb, address, bytes_across, height, pokes=None, **kwargs):
    return gsx.run_gsx("AES_ROM_GSX_FIX", (mfdb, address, bytes_across, height), merge_pokes(STALE_MFDB, pokes), **kwargs)


@THROUGH
def test_gsx_fix_of_the_screen(through_line_f):
    """Address 0: the screen's width and height from work_out[0..1] + 1, a word width of width / 16, its planes."""
    result = fix(gsx.mfdb_at(0), 0, 0, 0, through_line_f=through_line_f)
    work = aes.read_field(BASE_IMAGE, "AES", "GL_WS")
    width = work[0] + 1
    assert mfdb_of(result, gsx.mfdb_at(0)) == (0, width, work[1] + 1, width >> 4, 0, aes.read_field(BASE_IMAGE, "AES", "GL_NPLANES"))


@pytest.mark.parametrize("bytes_across, height", ((2, 16), (40, 200), (0x2000, -1), (0x1FFF, 3)),
                         ids=("an icon", "a screen's", "a width that wraps to 0", "the widest that does not"))
def test_gsx_fix_of_a_form(bytes_across, height):
    """A form: eight pixels a byte and a word width of that / 16, each a WORD that wraps; one plane, device format."""
    result = fix(gsx.mfdb_at(0), gsx.form_at(0), bytes_across, height)
    width = (bytes_across << 3) & 0xFFFF
    assert mfdb_of(result, gsx.mfdb_at(0)) == (gsx.form_at(0), width, height & 0xFFFF, width >> 4, 0, 1)


def test_gsx_fix_tests_the_whole_address_longword():
    """`move.l (a0)+,(a2)+; bne`: a form at $10000, whose low word is 0, is a form — not the screen."""
    result = fix(gsx.mfdb_at(0), WORD_ZERO_FORM, 2, 16)
    assert mfdb_of(result, gsx.mfdb_at(0)) == (WORD_ZERO_FORM, 16, 16, 1, 0, 1)


def test_gsx_fix_tests_the_address_before_the_bus_drops_its_top_byte():
    """`bne` on all 32 bits: an address of $5a000000 — bus address 0 — is a FORM, not the screen."""
    result = fix(gsx.mfdb_at(0), aes.BUS_TAG, 2, 16)
    assert mfdb_of(result, gsx.mfdb_at(0)) == (aes.BUS_TAG, 16, 16, 1, 0, 1)


def test_gsx_fix_s_mfdb_pointer_is_put_on_the_bus():
    result = fix(gsx.mfdb_at(0) | aes.BUS_TAG, 0, 0, 0)
    assert mfdb_of(result, gsx.mfdb_at(0))[0] == 0


def test_gsx_fix_reads_work_out_after_storing_the_address():
    """The ORDER, which only an overlap shows: an MFDB laid two bytes below work_out, so its address longword covers
    work_out[0]. The address (0) is stored first and the width read after it: 0 + 1, where the snapshot's 319 + 1
    would be read first. And fd_w then lands ON work_out[1], so the height read after it is that width, plus one."""
    at = aes.AES_GL_WS - aes.WORD_BYTES
    result = gsx.run_gsx("AES_ROM_GSX_FIX", (at, 0, 0, 0), None)
    assert vdi.read_field(result.final, "MFDB", "W", at) == 1
    assert vdi.read_field(result.final, "MFDB", "H", at) == 2


def test_gsx_fix_reads_the_planes_after_its_stores():
    """...and the screen arm's LAST read: an MFDB laid AT gl_nplanes, so its address longword (0) covers the planes.
    `move.w $c914,(a2)` is the arm's last access, so the planes stored are that 0 — read first, they would be the
    snapshot's."""
    at = aes.AES_GL_NPLANES
    result = gsx.run_gsx("AES_ROM_GSX_FIX", (at, 0, 0, 0), None)
    assert vdi.read_field(result.final, "MFDB", "NPLANES", at) == 0


def test_an_odd_mfdb_is_an_address_error_on_the_host():
    returncode, stderr = vdi_helpers.refusal("aes_gsx_fix", ["ctypes.c_void_p", "ctypes.c_uint32", "ctypes.c_uint32",
                                                             "ctypes.c_int16", "ctypes.c_int16"],
                                             f"buf, {gsx.mfdb_at(0) + 1}, 0, 0, 0")
    assert returncode != 0 and "address error" in stderr, stderr


def test_an_mfdb_past_the_top_of_the_bus_is_refused_on_the_host():
    top = OS_BUS_ADDR_MASK + 1 - aes.WORD_BYTES
    returncode, stderr = vdi_helpers.refusal("aes_gsx_fix", ["ctypes.c_void_p", "ctypes.c_uint32", "ctypes.c_uint32",
                                                             "ctypes.c_int16", "ctypes.c_int16"],
                                             f"buf, {top}, 0, 0, 0")
    assert returncode != 0 and "past the top of the 24-bit bus" in stderr, stderr


# ---- the registry ---------------------------------------------------------------------------------------------------
# Every atom priced on its realistic shapes — each VDI-reaching one by mechanism (V) (`bench/tier3.py`: its own
# cycles against the AES text's and the Line-F handler's, the VDI both sides run from the ROM's bytes in neither) —
# and each entered once through its callers' Line-F word (verified, unpriced).
_TRIANGLE = gsx.points_pokes(*TRIANGLE)
_ROWS = {
    "vsl_color 3, contrl staged": ("AES_ROM_GSX2", (), vsl_color_pokes(3)),
    "vqt_attributes": ("AES_ROM_GSX_NCODE", (addrs.VDI_ROM_VQT_ATTRIBUTES_OPCODE, 0, 0), None),
    "v_gtext, three characters": ("AES_ROM_GSX_NCODE", NCODE_CALLS["v_gtext, three characters"][:3],
                                  NCODE_CALLS["v_gtext, three characters"][3]),
    "vswr_mode 3": ("AES_ROM_GSX_1CODE", ONE_WORD_CALLS["vswr_mode 3 (XOR)"], None),
    "the nest already open": ("AES_ROM_GSX_MOFF", (), nest_pokes(1)),
    "the nest still open": ("AES_ROM_GSX_MON", (), nest_pokes(2)),
    "the nest unwound: v_show_c": ("AES_ROM_GSX_MON", (), None),
    "a triangle": ("AES_ROM_V_PLINE", (4, POINTS), _TRIANGLE),
    "on, a rectangle": ("AES_ROM_VS_CLIP", (1, POINTS), gsx.points_pokes(16, 24, 135, 83)),
    "the large font's": ("AES_ROM_VST_HEIGHT", (13, *answer_pointers()), None),
    "a rectangle": ("AES_ROM_VR_RECFL", (POINTS, gsx.mfdb_at(0)), gsx.points_pokes(40, 50, 90, 80)),
    "screen to screen": ("AES_ROM_VRO_CPYFM", *SCREEN_TO_SCREEN),
    "a form onto the screen": ("AES_ROM_VRT_CPYFM", *FORM_ONTO_THE_SCREEN),
    "standard to device": ("AES_ROM_VRN_TRNFM", *STANDARD_TO_DEVICE),
    "3": ("AES_ROM_VSL_WIDTH", (3,), None),
    "the screen": ("AES_ROM_GSX_FIX", (gsx.mfdb_at(0), 0, 0, 0), STALE_MFDB),
    "an icon's form": ("AES_ROM_GSX_FIX", (gsx.mfdb_at(0), _FORM, 2, 16), STALE_MFDB),
}
for _label, (_name, _arguments, _pokes) in _ROWS.items():
    gsx.register(_label, _name, _arguments, _pokes)
gsx.register("the snapshot's cursor: v_hide_c", "AES_ROM_GSX_MOFF", (), None, onto=gsx.shown_machine())
_LINE_F_ROWS = ("vsl_color 3, contrl staged", "vqt_attributes", "vswr_mode 3", "the nest already open",
                "the nest unwound: v_show_c", "a triangle", "on, a rectangle", "the large font's", "a rectangle",
                "screen to screen", "a form onto the screen", "standard to device", "3", "the screen")
for _label in _LINE_F_ROWS:
    _name, _arguments, _pokes = _ROWS[_label]
    gsx.register(_label, _name, _arguments, _pokes, through_line_f=True)
