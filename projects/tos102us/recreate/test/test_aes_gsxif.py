"""AES gemgsxif's mouse state, save-under buffer, mouse form and blits — `src/aes/gsxif.c`, through `test/aes_gsx.py`'s
door (the workstation half is `test_aes_gsxif_workstation.py`).

    gr_mkstate     *mx = xrat; *my = yrat; *mstate = button; *kstate = kstate   (a pc-relative table of the four)
    gsx_mxmy       *mx = xrat; *my = yrat;            gsx_button: D0 = button
    gsx_malloc     gsx_fix(&gl_tmp, 0, 0, 0); gl_tmp.fd_addr = dos_alloc($3400)
    gsx_mfree      dos_free(gl_tmp.fd_addr)  (dos_free parks $fe87b8, the word after its Line-F call)
    gsx_mret       *paddr = gl_tmp.fd_addr; *plen = gl_mlen
    gsx_mfset      gsx_moff; 37 words of the form -> *$c844 one at a time; vsc_form (row 0); gsx_mon
    gsx_mfsave     a0 = $a000 - $358 (M_POS_HX); $9560 = a0; lbcopy($9564, a0, 74)
    gsx_mfrestore  lbcopy(*$9560, $9564, 74)
    bb_set         x widened to whole words (`lsr.w`), gl_tmp a standard form that wide, the two corner arrays,
                   gsx_fix(screen mfdb), gsx_moff, vro_cpyfm(S_ONLY, ptsin, src, dst), gsx_mon
    bb_save        bb_set(rect, ptsin, ptsin+8, &gl_src, &gl_src, &gl_tmp);  bb_restore: the corners and MFDBs swapped

Every routine is hand 68000 returning by `rts`; each with a Line-F call word is also entered through it once. Every
case runs in the door's machine (the AES's cursor hidden by the ROM's own gsx_moff) unless it says the snapshot's
(`shown_machine`), and the WHOLE image is compared, the screen included.
"""
import re
from pathlib import Path

import pytest

from harness import BASE_IMAGE, addrs

import aes
import aes_gsx as gsx
import case
import vdi
import vdi_helpers
from case import merge_pokes
from test_aes_resource_dos import DOS_FIELDS, EIMBA, GEMDOS_OK, STALE_DOS

IMAGE, WORD, LONG = vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.LONG_ARG
SIGNATURES = {
    # the leaves and the save-under buffer (this battery)
    "AES_ROM_GR_MKSTATE": (None, (IMAGE, LONG, LONG, LONG, LONG)),
    "AES_ROM_GSX_MXMY": (None, (IMAGE, LONG, LONG)),
    "AES_ROM_GSX_BUTTON": (aes.WORD_ANSWER, (IMAGE,)),
    "AES_ROM_GSX_MALLOC": (None, (IMAGE,)),
    "AES_ROM_GSX_MFREE": (None, (IMAGE,)),
    "AES_ROM_GSX_MRET": (None, (IMAGE, LONG, LONG)),
    "AES_ROM_GSX_MFSET": (None, (IMAGE, LONG)),
    "AES_ROM_GSX_MFSAVE": (None, (IMAGE,)),
    "AES_ROM_GSX_MFRESTORE": (None, (IMAGE,)),
    "AES_ROM_BB_SET": (None, (IMAGE, WORD, WORD, WORD, WORD, LONG, LONG, LONG, LONG, LONG)),
    "AES_ROM_BB_SAVE": (None, (IMAGE, LONG)),
    "AES_ROM_BB_RESTORE": (None, (IMAGE, LONG)),
    # the workstation half (`test_aes_gsxif_workstation.py`)
    "AES_ROM_GSX_INIT": (None, (IMAGE,)),
    "AES_ROM_GSX_WSOPEN": (None, (IMAGE,)),
    "AES_ROM_V_OPNWK": (None, (IMAGE, LONG, LONG, LONG)),
    "AES_ROM_GSX_START": (None, (IMAGE,)),
    "AES_ROM_GSX_GRAPHIC": (None, (IMAGE, WORD)),
    "AES_ROM_GSX_SETMB_AES": (None, (IMAGE,)),
    "AES_ROM_GSX_SETMB": (None, (IMAGE, LONG, LONG, LONG)),
    "AES_ROM_GSX_RESETMB": (None, (IMAGE,)),
    "AES_ROM_GSX_ESCAPES": (None, (IMAGE, WORD)),
    "AES_ROM_GSX_WSCLOSE": (None, (IMAGE,)),
    "AES_ROM_RATINIT": (None, (IMAGE,)),
    "AES_ROM_GSX_TICK": (aes.WORD_ANSWER, (IMAGE, LONG, LONG)),
}
for _name, (_restype, _argtypes) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, _argtypes)

THROUGH = gsx.THROUGH
WORD_BYTES, LONG_BYTES = aes.WORD_BYTES, aes.LONG_BYTES
ANSWERS = gsx.ANSWERS_AT
STALE_ANSWERS = gsx.STALE_ANSWERS

# ---- this battery's band of the AES window -------------------------------------------------------------------------
BAND_OFFSET = 0x1700                    # in the gap between aes_shell's band and aes_strings'
BAND_BYTES = 0x100
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES, "test/test_aes_gsxif*.py: forms, work arrays")
FORM_AT = BAND_AT                       # a mouse form, GSX_MOUSE_FORM_BYTES
WORK_IN_AT = FORM_AT + 0x50             # v_opnwk's intin, 11 words
WORK_OUT_AT = WORK_IN_AT + 0x20         # ...its work_out, AES_GL_WS_WORDS words
assert FORM_AT + aes.GSX_MOUSE_FORM_BYTES <= WORK_IN_AT
assert WORK_OUT_AT + aes.AES_GL_WS_WORDS * WORD_BYTES <= BAND_AT + BAND_BYTES


# ---- the fields the cases reach outside the window (`aes.declare_case_field`) -----------------------------------------
for _name in ("XRAT", "YRAT", "BUTTON", "KSTATE", "GL_MLEN", "GSX_SUBFUNCTION", "GL_WS"):
    _field = aes.field("AES", _name)
    aes.declare_case_field(_field.at, _field.width * (_field.count or 1), f"gemgsxif's {_name}")
aes.declare_case_field(aes.AES_GSX_INTIN, aes.GSX_MOUSE_FORM_BYTES, "intin, where gsx_mfset copies a form")
aes.declare_case_field(aes.AES_GSX_INTOUT, 2 * WORD_BYTES, "intout's first words, gsx_tick's answer")
for _name in ("M_HID_CT", "USER_TIM"):
    _field = vdi.field("LINEA", _name)
    vdi.declare_case_field(_field.at, _field.width * (_field.count or 1), f"the Line-A {_name} gemgsxif's cases stage")
vdi.declare_case_field(vdi.field("LINEA", "M_POS_HX").at, aes.GSX_MOUSE_FORM_BYTES, "the Line-A mouse form gsx_mfsave saves")


# ---- the mouse state ----------------------------------------------------------------------------------------------
# Four words no two alike, staged over the snapshot's, so every answer is told from every other.
STATE = {"XRAT": 0x0123, "YRAT": 0x0456, "BUTTON": 0x0002, "KSTATE": 0x0008}
STATE_POKES = aes.field_pokes("AES", **STATE)
STATE_FIELDS = tuple(aes.field("AES", name).at for name in STATE)


def answer_pointers(count):
    return tuple(ANSWERS + index * WORD_BYTES for index in range(count))


@THROUGH
def test_gr_mkstate_answers_the_four_words(through_line_f):
    result = gsx.run_gsx("AES_ROM_GR_MKSTATE", answer_pointers(4), merge_pokes(STALE_ANSWERS, STATE_POKES),
                         through_line_f=through_line_f)
    assert result.words(ANSWERS, 4) == list(STATE.values())


def test_gr_mkstate_reads_each_word_after_the_store_before_it():
    """The ORDER, every link: the first three pointers are the NEXT state word's own (x at yrat, y at the button,
    the button at the shift state), so each word read is the one the store before it just wrote — all four answers
    are xrat. A word read early would be its own staged value."""
    pointers = (*STATE_FIELDS[1:], ANSWERS)
    result = gsx.run_gsx("AES_ROM_GR_MKSTATE", pointers, merge_pokes(STALE_ANSWERS, STATE_POKES))
    assert [result.word(at) for at in pointers] == [STATE["XRAT"]] * 4


def test_gr_mkstate_s_pointers_are_put_on_the_bus():
    result = gsx.run_gsx("AES_ROM_GR_MKSTATE", tuple(at | aes.BUS_TAG for at in answer_pointers(4)),
                         merge_pokes(STALE_ANSWERS, STATE_POKES))
    assert result.words(ANSWERS, 4) == list(STATE.values())


def test_gr_mkstate_through_an_odd_pointer_is_an_address_error_on_the_host():
    gsx.odd_pointer_refused("aes_gr_mkstate", [gsx.pointer(at) for at in (ANSWERS, ANSWERS + 2, ANSWERS + 5, ANSWERS + 6)])


@THROUGH
def test_gsx_mxmy_answers_the_mouse_s_position(through_line_f):
    result = gsx.run_gsx("AES_ROM_GSX_MXMY", answer_pointers(2), merge_pokes(STALE_ANSWERS, STATE_POKES),
                         through_line_f=through_line_f)
    assert result.words(ANSWERS, 2) == [STATE["XRAT"], STATE["YRAT"]]


def test_gsx_mxmy_reads_y_after_storing_x():
    """x's pointer at yrat: the y answered is the x just stored."""
    result = gsx.run_gsx("AES_ROM_GSX_MXMY", (STATE_FIELDS[1], ANSWERS), merge_pokes(STALE_ANSWERS, STATE_POKES))
    assert result.word(ANSWERS) == STATE["XRAT"]


def test_gsx_mxmy_s_pointers_are_put_on_the_bus():
    result = gsx.run_gsx("AES_ROM_GSX_MXMY", tuple(at | aes.BUS_TAG for at in answer_pointers(2)), STATE_POKES)
    assert result.words(ANSWERS, 2) == [STATE["XRAT"], STATE["YRAT"]]


def test_gsx_mxmy_through_an_odd_pointer_is_an_address_error_on_the_host():
    gsx.odd_pointer_refused("aes_gsx_mxmy", [gsx.pointer(ANSWERS), gsx.pointer(ANSWERS + 3)])


@THROUGH
@pytest.mark.parametrize("buttons", (0, 1, 3, 0x8001), ids=("none", "left", "both", "a stray high bit"))
def test_gsx_button_answers_the_buttons_word(buttons, through_line_f):
    result = gsx.run_gsx("AES_ROM_GSX_BUTTON", (), aes.field_pokes("AES", BUTTON=buttons), through_line_f=through_line_f)
    assert result.answer() & 0xFFFF == buttons


# ---- the save-under buffer ----------------------------------------------------------------------------------------
MALLOC, MFREE = addrs.GEMDOS_MALLOC_FN, addrs.GEMDOS_MFREE_FN
SNAPSHOT_BUFFER = aes.read_field(BASE_IMAGE, "AES", "GL_TMP")[:LONG_BYTES]
SNAPSHOT_BUFFER_AT = int.from_bytes(bytes(SNAPSHOT_BUFFER), "big")      # the block the boot's own Malloc answered
STALE_TMP = {aes.AES_GL_TMP: bytes([case.SLACK_FILL]) * aes.AES_MFDB_BYTES}
aes.declare_case_field(aes.AES_GL_TMP, aes.AES_MFDB_BYTES, "gl_tmp, the save-under buffer's MFDB")


def trap_machine(answer, pokes=None):
    """The door's machine with GEMDOS's `trap #1` pointed at the staged recording handler answering `answer`, every
    field the glue parks STALE."""
    return gsx.machine(merge_pokes(STALE_DOS, pokes, vdi_helpers.staged_gemdos_trap_pokes(answer)))


def trap_hook(answer):
    """...and its doors: the VDI's functions and the handler's host twin."""
    return aes.doors(gsx.vdi_hook, vdi_helpers.staged_gemdos_hook(answer))


def through_the_recording_trap(name, arguments, answer, pokes=None, **kwargs):
    """`name` over `trap_machine`, its GEMDOS call taken by the recording handler on the ROM's side and its host twin
    on ours — the ordered ledger compared. UNPOISONED: the trap reads its ledger's pointer and writes it back, which
    the pass would hand the host twin wild (`test_aes_resource_dos.py`'s measured reason); every field the glue parks
    is staged STALE instead."""
    return aes.run_function(name, arguments, trap_machine(answer, pokes), hook=trap_hook(answer),
                            **vdi.READS_A_POINTER_IT_WRITES, **kwargs)


def screen_mfdb(address):
    """gsx_fix's screen MFDB from the snapshot's workstation, at `address`."""
    work = aes.read_field(BASE_IMAGE, "AES", "GL_WS")
    width = work[0] + 1
    return (address, width, work[1] + 1, width >> 4, 0, aes.read_field(BASE_IMAGE, "AES", "GL_NPLANES"))


# (the block Malloc answers, gl_tmp's address after it, AES_DOS_ERR after it): an odd block rounded up, none a failure.
ALLOCATIONS = {
    "the snapshot's block": (SNAPSHOT_BUFFER_AT, SNAPSHOT_BUFFER_AT, aes.STALE_WORD),
    "an odd block": (SNAPSHOT_BUFFER_AT + 1, SNAPSHOT_BUFFER_AT + 2, aes.STALE_WORD),
    "no memory": (0, 0, 1),
}


@THROUGH
@pytest.mark.parametrize("block, address, failed", ALLOCATIONS.values(), ids=ALLOCATIONS)
def test_gsx_malloc_makes_gl_tmp_the_screen_s_and_mallocs_its_buffer(block, address, failed, through_line_f):
    result = through_the_recording_trap("AES_ROM_GSX_MALLOC", (), block, STALE_TMP, through_line_f=through_line_f)
    assert vdi_helpers.trapped_calls(result.final) == [(MALLOC, aes.GSX_SAVE_BUFFER_BYTES)]
    assert gsx.mfdb_of(result, aes.AES_GL_TMP) == screen_mfdb(address)
    assert result.field("AES", "DOS_ERR") == failed


@THROUGH
@pytest.mark.parametrize("answer, failed", ((GEMDOS_OK, 0), (EIMBA, 1)), ids=("freed", "EIMBA"))
def test_gsx_mfree_frees_gl_tmp_s_buffer_parking_its_own_return(answer, failed, through_line_f):
    """dos_free parks its CALLER's return: gsx_mfree's, the word after its Line-F call — however gsx_mfree was
    entered."""
    result = through_the_recording_trap("AES_ROM_GSX_MFREE", (), answer, through_line_f=through_line_f)
    assert vdi_helpers.trapped_calls(result.final) == [(MFREE, SNAPSHOT_BUFFER_AT)]
    assert [result.field("AES", name) for name in DOS_FIELDS] == [aes.AES_GSX_MFREE_RETURN, addrs.AES_DOS_TRAP_RETURN,
                                                                  failed, answer & 0xFFFF]


MLEN = 0x0001_2345                      # gl_mlen, which nothing in the AES writes: staged, so its read shows


@THROUGH
def test_gsx_mret_answers_the_buffer_and_gl_mlen(through_line_f):
    pokes = merge_pokes(STALE_ANSWERS, aes.field_pokes("AES", GL_MLEN=MLEN))
    result = gsx.run_gsx("AES_ROM_GSX_MRET", (ANSWERS, ANSWERS + LONG_BYTES), pokes, through_line_f=through_line_f)
    assert (result.long(ANSWERS), result.long(ANSWERS + LONG_BYTES)) == (SNAPSHOT_BUFFER_AT, MLEN)


def test_gsx_mret_reads_gl_mlen_after_storing_the_address():
    """The address's pointer AT gl_mlen: the length answered is the address just stored."""
    pokes = merge_pokes(STALE_ANSWERS, aes.field_pokes("AES", GL_MLEN=MLEN))
    result = gsx.run_gsx("AES_ROM_GSX_MRET", (aes.AES_GL_MLEN, ANSWERS), pokes)
    assert result.long(ANSWERS) == SNAPSHOT_BUFFER_AT


def test_gsx_mret_s_pointers_are_put_on_the_bus():
    result = gsx.run_gsx("AES_ROM_GSX_MRET", (ANSWERS | aes.BUS_TAG, (ANSWERS + LONG_BYTES) | aes.BUS_TAG), STALE_ANSWERS)
    assert result.long(ANSWERS) == SNAPSHOT_BUFFER_AT


def test_gsx_mret_through_an_odd_pointer_is_an_address_error_on_the_host():
    gsx.odd_pointer_refused("aes_gsx_mret", [gsx.pointer(ANSWERS), gsx.pointer(ANSWERS + LONG_BYTES + 1)])


# ---- the mouse form ----------------------------------------------------------------------------------------------
# `test/aes.py`'s parse binds literals and aliases, no expression (an evaluator in `tools/addrs.py` would newly bind
# ~25 defines across every component), so `gsxif.h`'s GSX_MOUSE_FORM_WORDS is spelt ONCE here, and the gl_ws word
# counts kept literal for the parse are sums of the VDI's table sizes: both held to the headers by the test below.
FORM_WORDS = aes.GSX_MOUSE_FORM_BYTES // vdi.VDI_WORD_BYTES
GSXIF_H = Path(__file__).resolve().parents[1] / "include" / "aes" / "gsxif.h"


def test_the_sizes_the_parse_cannot_bind_are_the_headers():
    define = re.search(r"^#define GSX_MOUSE_FORM_WORDS\s+(\(.*\))$", GSXIF_H.read_text(), re.MULTILINE)
    assert define, "gsxif.h no longer defines GSX_MOUSE_FORM_WORDS on one line: re-read it and FORM_WORDS"
    assert define.group(1) == "(GSX_MOUSE_FORM_BYTES / VDI_WORD_BYTES)", "FORM_WORDS no longer spells the header's"
    assert aes.GSX_WS_CHMINH == vdi.VDI_DEV_TAB_WORDS + vdi.VDI_SIZ_TAB_MIN_CHAR_HEIGHT_INDEX
    assert aes.GSX_WS_CHMAXH == vdi.VDI_DEV_TAB_WORDS + vdi.VDI_SIZ_TAB_MAX_CHAR_HEIGHT_INDEX
    assert aes.AES_GL_WS_WORDS == vdi.VDI_DEV_TAB_WORDS + vdi.VDI_SIZ_TAB_WORDS


# A form whose words are all different: the hot spot (1, 2), one plane, colours 0 and 1, a diagonal and its mask.
HOT_SPOT_AND_COLOURS = (1, 2, 1, 0, 1)
FORM = (*HOT_SPOT_AND_COLOURS, *(word for row in range(16) for word in (0xC000 >> row | 0x8000 >> row, 0x8000 >> row)))
assert len(FORM) == FORM_WORDS
FORM_POKES = {FORM_AT: vdi.pack_words(*FORM)}
STALE_INTIN = {aes.AES_GSX_INTIN: vdi.pack_words(*[aes.STALE_WORD] * FORM_WORDS)}


@THROUGH
def test_gsx_mfset_copies_the_form_and_sets_it(through_line_f):
    """In the door's machine (nest 1) the hide and the show only count: the form lands in intin and vsc_form
    takes it into the Line-A block."""
    result = gsx.run_gsx("AES_ROM_GSX_MFSET", (FORM_AT,), merge_pokes(FORM_POKES, STALE_INTIN), through_line_f=through_line_f)
    assert result.words(aes.AES_GSX_INTIN, FORM_WORDS) == list(FORM)
    assert result.words(vdi.field("LINEA", "M_POS_HX").at, 2) == list(HOT_SPOT_AND_COLOURS[:2])
    assert result.field("AES", "GL_MOFF") == gsx.NEST_HIDDEN


def test_gsx_mfset_copies_every_word_none_alike():
    """FORM's last two words are alike (its diagonal's last row): here the 32 rows' words all differ, so a copy that
    dropped or repeated any word — the 37th, copied after the loop of pairs, included — shows."""
    form = (*HOT_SPOT_AND_COLOURS, *range(0x0101, 0x0101 + FORM_WORDS - len(HOT_SPOT_AND_COLOURS)))
    result = gsx.run_gsx("AES_ROM_GSX_MFSET", (FORM_AT,), merge_pokes({FORM_AT: vdi.pack_words(*form)}, STALE_INTIN))
    assert result.words(aes.AES_GSX_INTIN, FORM_WORDS) == list(form)


def test_gsx_mfset_over_the_snapshot_s_drawn_cursor():
    """The snapshot's shown cursor: hidden (its background restored), the form set, the new one drawn."""
    result = gsx.run_gsx("AES_ROM_GSX_MFSET", (FORM_AT,), FORM_POKES, onto=gsx.shown_machine())
    assert result.field("AES", "GL_MOFF") == gsx.NEST_SHOWN and result.field("AES", "GL_MOUSE_SHOWN") == 1
    base, end = vdi.SCREEN.base, vdi.SCREEN.base + vdi.SCREEN.bytes
    assert bytes(result.final[base:end]) != bytes(BASE_IMAGE[base:end])


def test_gsx_mfset_copies_one_word_at_a_time_forward():
    """The ORDER: the form two bytes BELOW where it is copied to, so each word read after the first is the word the
    copy just wrote — the first word everywhere. A copy that read ahead, or ran backwards, would copy the form."""
    source = aes.AES_GSX_INTIN - WORD_BYTES
    result = gsx.run_gsx("AES_ROM_GSX_MFSET", (source,), STALE_INTIN)
    first = case.word_in(BASE_IMAGE, source)
    assert result.words(aes.AES_GSX_INTIN, FORM_WORDS) == [first] * FORM_WORDS


def test_gsx_mfset_copies_to_where_ad_intin_points():
    """AES_AD_INTIN staged elsewhere: the form is copied THERE (vsc_form reading intin's stale words), so the
    destination is read from ad_intin, not spelt as intin. That the ROM reads it after gsx_moff no case can show — in
    the door's machine the hide only counts, and nothing gsx_moff or v_hide_c writes reaches $c844 — so reading it
    first is an equivalent mutant."""
    pokes = merge_pokes(FORM_POKES, STALE_INTIN, aes.field_pokes("AES", AD_INTIN=gsx.form_at(0)),
                        {gsx.form_at(0): bytes(gsx.FORM_BYTES)})
    result = gsx.run_gsx("AES_ROM_GSX_MFSET", (FORM_AT,), pokes)
    assert result.words(gsx.form_at(0), FORM_WORDS)[:16] == list(FORM)[:16]


def test_gsx_mfset_copies_through_a_tagged_destination_on_the_bus():
    """AES_AD_INTIN with a top byte: the copy goes where the bus puts it — intin — and vsc_form reads it there."""
    pokes = merge_pokes(FORM_POKES, STALE_INTIN, aes.field_pokes("AES", AD_INTIN=aes.AES_GSX_INTIN | aes.BUS_TAG))
    result = gsx.run_gsx("AES_ROM_GSX_MFSET", (FORM_AT,), pokes)
    assert result.words(aes.AES_GSX_INTIN, FORM_WORDS) == list(FORM)


def test_gsx_mfset_s_form_pointer_is_put_on_the_bus():
    result = gsx.run_gsx("AES_ROM_GSX_MFSET", (FORM_AT | aes.BUS_TAG,), merge_pokes(FORM_POKES, STALE_INTIN))
    assert result.words(aes.AES_GSX_INTIN, FORM_WORDS) == list(FORM)


def test_gsx_mfset_of_an_odd_form_is_an_address_error_on_the_host():
    gsx.odd_pointer_refused("aes_gsx_mfset", [gsx.pointer(FORM_AT + 1)], FORM_POKES)


LINEA_FORM = vdi.field("LINEA", "M_POS_HX").at
STALE_SAVE = aes.field_pokes("AES", MFORM_AT=vdi.STALE_LONG, MFORM_SAVE=[case.SLACK_FILL] * aes.GSX_MOUSE_FORM_BYTES)
# A form saved over the snapshot's (FORM's words), and where it was taken from: what gsx_mfrestore puts back.
RESTORE_POKES = aes.field_pokes("AES", MFORM_AT=LINEA_FORM, MFORM_SAVE=list(vdi.pack_words(*FORM)))
aes.declare_case_field(aes.AES_MFORM_AT, LONG_BYTES + aes.GSX_MOUSE_FORM_BYTES, "gsx_mfsave's form and its place")


@THROUGH
def test_gsx_mfsave_keeps_the_line_a_form_and_where_it_lives(through_line_f):
    result = gsx.run_gsx("AES_ROM_GSX_MFSAVE", (), STALE_SAVE, through_line_f=through_line_f)
    assert result.field("AES", "MFORM_AT") == LINEA_FORM
    assert result.after(aes.AES_MFORM_SAVE, aes.GSX_MOUSE_FORM_BYTES) == bytes(
        BASE_IMAGE[LINEA_FORM:LINEA_FORM + aes.GSX_MOUSE_FORM_BYTES])


def test_a_repointed_line_a_vector_halts_the_bridge_on_the_host():
    """$a000's one hop is RAM: a case that repoints vector $28 is refused by name, never served by the C twin."""
    pokes = gsx.machine({addrs.VECTOR_LINE_A: gsx.BAND_AT.to_bytes(LONG_BYTES, "big")})
    returncode, stderr, _image = vdi_helpers.refusal_over("aes_gsx_mfsave", pokes, read_back=False)
    assert returncode != 0 and "vector $28" in stderr and "the AES's $a000" in stderr, stderr
    assert f"${addrs.LINEA_ROM_DISPATCH:x}" in stderr, "the message names the routine the bridge checks for"


def test_the_snapshot_s_line_a_vector_is_the_one_the_bridge_checks():
    assert case.long_in(BASE_IMAGE, addrs.VECTOR_LINE_A) == addrs.LINEA_ROM_DISPATCH


@THROUGH
def test_gsx_mfrestore_puts_the_saved_form_back(through_line_f):
    result = gsx.run_gsx("AES_ROM_GSX_MFRESTORE", (), RESTORE_POKES, through_line_f=through_line_f)
    assert result.words(LINEA_FORM, FORM_WORDS) == list(FORM)


def test_gsx_mfsave_then_gsx_mfrestore_round_trips_a_changed_form():
    """A SEQUENCE through `case.continued`: saved, the Line-A form overwritten (as gsx_mfset would), restored."""
    saved = gsx.run_gsx("AES_ROM_GSX_MFSAVE", (), STALE_SAVE)
    restored = gsx.run_gsx("AES_ROM_GSX_MFRESTORE", (), onto=merge_pokes(case.continued(saved),
                                                                         {LINEA_FORM: vdi.pack_words(*FORM)}))
    assert restored.after(LINEA_FORM, aes.GSX_MOUSE_FORM_BYTES) == bytes(
        BASE_IMAGE[LINEA_FORM:LINEA_FORM + aes.GSX_MOUSE_FORM_BYTES])


# ---- the blits: bb_set, bb_save, bb_restore -------------------------------------------------------------------------
# A drop-down's rectangle as the menus save it: x not on a word (21 -> the word at 16), its right edge in a seventh
# word (120 -> 112 pixels, 7 words); and one exactly on words. gl_tmp's buffer is the snapshot's own Malloc'd block.
MENU = (21, 11, 100, 60)
ALIGNED = (32, 40, 32, 16)
STALE_BLIT = merge_pokes({aes.AES_GL_TMP + vdi.field("MFDB", "W").at: vdi.pack_words(*[aes.STALE_WORD] * 4)},
                         {aes.AES_GSX_PTSIN: vdi.pack_words(*[aes.STALE_WORD] * 8)}, gsx.GL_MFDBS_STALE)
RECT = aes.RECTS_AT


def rect_pokes(rect):
    return aes.grect_pokes(RECT, *rect)


def widened(rect):
    """bb_set's arithmetic: (the left pixel, the width in words) of `rect` widened to whole words."""
    x, _y, width, _height = rect
    first, last = (x & 0xFFFF) >> 4, ((width + x - 1) & 0xFFFF) >> 4
    return first << 4, (last - first + 1) & 0xFFFF


def blit_corners(rect):
    """ptsin's eight words after a bb_save of `rect`: the screen's corners, then the form's."""
    _x, y, _width, height = rect
    left, words = widened(rect)
    return [left, y, left + words * 16 - 1, y + height - 1, 0, 0, words * 16 - 1, height - 1]


def tmp_size(result):
    """gl_tmp's W, H, WDWIDTH and STAND: what bb_set sizes it by."""
    return gsx.mfdb_of(result, aes.AES_GL_TMP)[1:5]


@THROUGH
@pytest.mark.parametrize("rect", (MENU, ALIGNED), ids=("a menu's, across seven words", "on words"))
def test_bb_save_copies_the_screen_under_a_rectangle_into_gl_tmp(rect, through_line_f):
    result = gsx.run_gsx("AES_ROM_BB_SAVE", (RECT,), merge_pokes(STALE_BLIT, rect_pokes(rect)), through_line_f=through_line_f)
    _left, words = widened(rect)
    assert tmp_size(result) == (words * 16, rect[3], words, 1)
    assert result.words(aes.AES_GSX_PTSIN, 8) == blit_corners(rect)
    assert result.after(SNAPSHOT_BUFFER_AT, 64) != bytes(BASE_IMAGE[SNAPSHOT_BUFFER_AT:SNAPSHOT_BUFFER_AT + 64])
    assert vdi.read_field(result.final, "MFDB", "ADDR", aes.AES_GL_SRC) == 0


def test_bb_save_with_the_snapshot_s_cursor_shown():
    """The realistic machine for a drop-down: the arrow drawn — hidden round the copy (v_hide_c), shown after."""
    result = gsx.run_gsx("AES_ROM_BB_SAVE", (RECT,), merge_pokes(STALE_BLIT, rect_pokes(MENU)), onto=gsx.shown_machine())
    assert result.field("AES", "GL_MOFF") == gsx.NEST_SHOWN and result.field("AES", "GL_MOUSE_SHOWN") == 1


@THROUGH
def test_bb_restore_puts_a_saved_rectangle_back(through_line_f):
    """A SEQUENCE: saved, the screen under it overwritten, restored — the snapshot's pixels again."""
    saved = gsx.run_gsx("AES_ROM_BB_SAVE", (RECT,), merge_pokes(STALE_BLIT, rect_pokes(MENU)))
    left, words = widened(MENU)
    rows = range(MENU[1], MENU[1] + MENU[3])
    line_bytes = vdi.SCREEN.bytes_per_line
    scribbled = {vdi.SCREEN.base + row * line_bytes: bytes([0x3C]) * line_bytes for row in rows}
    restored = gsx.run_gsx("AES_ROM_BB_RESTORE", (RECT,), onto=merge_pokes(case.continued(saved), scribbled),
                           through_line_f=through_line_f)
    first = vdi.SCREEN.base + MENU[1] * line_bytes + left // 16 * vdi.SCREEN.planes * WORD_BYTES
    span = words * vdi.SCREEN.planes * WORD_BYTES
    for row in range(MENU[3]):
        at = first + row * line_bytes
        assert restored.after(at, span) == bytes(BASE_IMAGE[at:at + span]), f"row {row}"


def test_bb_save_s_rectangle_pointer_is_put_on_the_bus():
    result = gsx.run_gsx("AES_ROM_BB_SAVE", (RECT | aes.BUS_TAG,), merge_pokes(STALE_BLIT, rect_pokes(MENU)))
    assert result.words(aes.AES_GSX_PTSIN, 8) == blit_corners(MENU)


def test_an_odd_rectangle_is_an_address_error_on_the_host():
    gsx.odd_pointer_refused("aes_bb_save", [gsx.pointer(RECT + 1)], rect_pokes(MENU))


BB_SAVE_ARGUMENTS = (aes.AES_GSX_PTSIN, aes.AES_GSX_PTSIN + 4 * WORD_BYTES, aes.AES_GL_SRC, aes.AES_GL_SRC, aes.AES_GL_TMP)


def test_bb_set_writes_the_form_s_corners_before_the_screen_s():
    """The ORDER, which only an overlap shows: both corner arrays the SAME ptsin, so the screen's corners — stored
    last — are what vro_cpyfm reads as its source, the form's rectangle staged sane in ptsin[4..7]."""
    _left, words = widened(MENU)
    pokes = merge_pokes(STALE_BLIT, {aes.AES_GSX_PTSIN + 4 * WORD_BYTES: vdi.pack_words(0, 0, words * 16 - 1, MENU[3] - 1)})
    result = gsx.run_gsx("AES_ROM_BB_SET", (*MENU, aes.AES_GSX_PTSIN, aes.AES_GSX_PTSIN, aes.AES_GL_SRC, aes.AES_GL_SRC,
                                           aes.AES_GL_TMP), pokes)
    assert result.words(aes.AES_GSX_PTSIN, 4) == blit_corners(MENU)[:4]


def test_bb_set_sizes_gl_tmp_before_writing_the_form_s_corners():
    """The ORDER, which only an overlap shows: the form's corners laid over gl_tmp's size words (from fd_w on), so the
    corners — stored after the size — are what is left there. The copy itself goes screen to screen through gl_dst
    (the snapshot's screen MFDB), the form's rectangle staged sane in ptsin[4..7]."""
    _left, words = widened(MENU)
    form_corners = aes.AES_GL_TMP + vdi.field("MFDB", "W").at
    pokes = merge_pokes(STALE_BLIT, {aes.AES_GSX_PTSIN + 4 * WORD_BYTES: vdi.pack_words(0, 0, words * 16 - 1, MENU[3] - 1)})
    result = gsx.run_gsx("AES_ROM_BB_SET", (*MENU, aes.AES_GSX_PTSIN, form_corners, aes.AES_GL_DST, aes.AES_GL_DST,
                                           aes.AES_GL_DST), pokes)
    assert result.words(form_corners, 4) == [0, 0, words * 16 - 1, MENU[3] - 1]


# A rectangle left of the screen, inside one word: x = -8 is word $0fff (`lsr.w`), its left pixel $fff0 — which the
# VDI then copies from.
def test_bb_set_s_arithmetic_is_words_left_of_the_screen():
    rect = (-8, 20, 4, 8)
    left, words = widened(rect)
    result = gsx.run_gsx("AES_ROM_BB_SET", (*rect, *BB_SAVE_ARGUMENTS), STALE_BLIT)
    assert result.words(aes.AES_GSX_PTSIN, 1) == [left & 0xFFFF]
    assert vdi.read_field(result.final, "MFDB", "WDWIDTH", aes.AES_GL_TMP) == words


# The LOGICAL shifts (`lsr.w`), told from arithmetic ones by a right edge past $7fff: x = $7ff8 is word $07ff and its
# last pixel $8007 word $0800 — two words; shifted arithmetically the last is $f800 and the count wraps to $f002. (A
# rectangle STRADDLING x = 0 — first word $0fff, last 0 — would tell them apart too, but the ROM then copies a form
# $f00x words wide, past the oracle's instruction cap: that arm stays unpinned by a run.)
@pytest.mark.parametrize("rect", ((0x7FF8, 20, 16, 1), (0x7FF0, 20, 32, 4)), ids=("one row", "four rows"))
def test_bb_set_s_words_are_logical_past_the_sign_bit(rect):
    _left, words = widened(rect)
    result = gsx.run_gsx("AES_ROM_BB_SET", (*rect, *BB_SAVE_ARGUMENTS), STALE_BLIT)
    assert vdi.read_field(result.final, "MFDB", "WDWIDTH", aes.AES_GL_TMP) == words == 2


# Every pointer bb_set is handed, tagged with a top byte: the two corner arrays, the screen's MFDB, the copy's source
# and destination MFDBs (which the VDI's vro_cpyfm takes through the bus as well).
@pytest.mark.parametrize("tagged", ((0, 1), (2,), (3, 4)), ids=("the corners", "the screen MFDB", "source, destination"))
def test_bb_set_s_pointers_are_put_on_the_bus(tagged):
    arguments = [pointer | aes.BUS_TAG if index in tagged else pointer for index, pointer in enumerate(BB_SAVE_ARGUMENTS)]
    result = gsx.run_gsx("AES_ROM_BB_SET", (*MENU, *arguments), STALE_BLIT)
    assert result.words(aes.AES_GSX_PTSIN, 8) == blit_corners(MENU)


# ---- the registry ---------------------------------------------------------------------------------------------------
# Every routine priced on its realistic shapes — the worst included: the cursor SHOWN (the snapshot's) where a hide and
# a show reach the VDI — and each entered once through its callers' Line-F word (verified, unpriced). A row whose C
# reaches the VDI is priced by mechanism (V) (`bench/tier3.py`: its own cycles).
_ROWS = {
    ("AES_ROM_GR_MKSTATE", "four answers"): (answer_pointers(4), merge_pokes(STALE_ANSWERS, STATE_POKES), None),
    ("AES_ROM_GSX_MXMY", "both answers"): (answer_pointers(2), merge_pokes(STALE_ANSWERS, STATE_POKES), None),
    ("AES_ROM_GSX_BUTTON", "the left button"): ((), aes.field_pokes("AES", BUTTON=1), None),
    ("AES_ROM_GSX_MRET", "both answers"): ((ANSWERS, ANSWERS + LONG_BYTES), merge_pokes(STALE_ANSWERS,
                                                                                         aes.field_pokes("AES", GL_MLEN=MLEN)), None),
    ("AES_ROM_GSX_MFSET", "the cursor hidden"): ((FORM_AT,), merge_pokes(FORM_POKES, STALE_INTIN), None),
    ("AES_ROM_GSX_MFSET", "the cursor shown: hidden, set, drawn"): ((FORM_AT,), FORM_POKES, gsx.shown_machine()),
    ("AES_ROM_GSX_MFSAVE", "the snapshot's form"): ((), STALE_SAVE, None),
    ("AES_ROM_GSX_MFRESTORE", "a changed form"): ((), RESTORE_POKES, None),
    ("AES_ROM_BB_SAVE", "a menu's, the cursor hidden"): ((RECT,), merge_pokes(STALE_BLIT, rect_pokes(MENU)), None),
    ("AES_ROM_BB_SAVE", "a menu's, the cursor shown"): ((RECT,), merge_pokes(STALE_BLIT, rect_pokes(MENU)),
                                                        gsx.shown_machine()),
    ("AES_ROM_BB_RESTORE", "a menu's, the cursor shown"): ((RECT,), merge_pokes(STALE_BLIT, rect_pokes(MENU)),
                                                           gsx.shown_machine()),
    ("AES_ROM_BB_SET", "a menu's corners in ptsin"): ((*MENU, *BB_SAVE_ARGUMENTS), STALE_BLIT, None),
}
for (_name, _label), (_arguments, _pokes, _onto) in _ROWS.items():
    gsx.register(_label, _name, _arguments, _pokes, onto=_onto)
_LINE_F_ROWS = (("AES_ROM_GR_MKSTATE", "four answers"), ("AES_ROM_GSX_MXMY", "both answers"),
                ("AES_ROM_GSX_BUTTON", "the left button"), ("AES_ROM_GSX_MRET", "both answers"),
                ("AES_ROM_GSX_MFSET", "the cursor hidden"), ("AES_ROM_GSX_MFSAVE", "the snapshot's form"),
                ("AES_ROM_GSX_MFRESTORE", "a changed form"), ("AES_ROM_BB_SAVE", "a menu's, the cursor hidden"),
                ("AES_ROM_BB_RESTORE", "a menu's, the cursor shown"))
for _key in _LINE_F_ROWS:
    _arguments, _pokes, _onto = _ROWS[_key]
    gsx.register(_key[1], _key[0], _arguments, _pokes, onto=_onto, through_line_f=True)
# The two that take GEMDOS's `trap #1`, over the recording handler on both sides.
for _through in (False, True):
    aes.register("the snapshot's block", "AES_ROM_GSX_MALLOC", (), trap_machine(SNAPSHOT_BUFFER_AT, STALE_TMP),
                 through_line_f=_through, hook=trap_hook(SNAPSHOT_BUFFER_AT))
    aes.register("freed", "AES_ROM_GSX_MFREE", (), trap_machine(GEMDOS_OK), through_line_f=_through,
                 hook=trap_hook(GEMDOS_OK))
