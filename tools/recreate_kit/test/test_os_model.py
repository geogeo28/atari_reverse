"""Pin the model surfaces of TRAP_MODEL.md's Phases 11-13 — the raster core, the VDI/AES opcodes,
the off-image OS event ledger, GEMDOS's console calls and Fseek, and the candidate's Malloc arena —
kit-side, on BOTH doors onto each of them.

The model (TRAP_MODEL.md, Phases 11-13) is one shared implementation, `src/gem.c` over
`src/raster.c`, compiled into the oracle and into every candidate. So the interesting failures are
not "the two transcriptions disagree" — there is only one — but:

* **the drawing is wrong in the same way on both sides**, which no differential can see, because
  both sides would run the same wrong code. That is what the RASTER REFERENCE below is for: a second
  implementation of the ST device format and of the sixteen logic operations, written from the
  format's own definition rather than from raster.c, so the C has something to disagree with.
* **the two DOORS disagree** — `oracle/shim.c`'s `trap #2` decode against `os.h`'s `os_gem_trap()`
  wrapper — which is per-side code. `os_model_probe.c` drives both in one process, once per modeled
  opcode, and the last cases here compare what each wrote and what each ledgered.
* **a ledger entry is missing or misordered**, which is likewise invisible to the image diff.

The obstacle is the usual one (`test_psg_model.py` states it in full): this directory binds no
project, and `harness`/`emu` both load a candidate `.so` at import, so the model is unreachable from
Python here. The probe drives it in C instead.
"""
import sys

from pathlib import Path

import pytest

from probe_build import compile_probe, run_probe

KIT = Path(__file__).resolve().parents[1]
PROBE_SRC = Path(__file__).with_name("os_model_probe.c")
# The CANDIDATE-side files the probe needs beyond the oracle's own sources: the event ledger it reads
# back, the refusal tally os.h's wrappers route through, and the Malloc arena the last cases compare
# against the shim's. (src/gem.c and src/raster.c are already in probe_build.ORACLE_SRC — they are
# SHARED, linked into the oracle too — so adding them here would be a duplicate definition.)
CANDIDATE_SRC = (KIT / "src" / "os_log.c", KIT / "src" / "os_refusal.c", KIT / "src" / "os_heap.c")

sys.path.insert(0, str(KIT.parent))                   # reverse/tools, so `recreate_kit` imports
from recreate_kit import os_map   # noqa: E402  (importable with nothing built, unlike harness/emu)

# The probe's raster geometry, and the screen's. Spelt here because the reference below has to lay
# out the same bytes; the probe prints every raster it used, so nothing else is shared.
RASTER_SIDE, RASTER_WDWIDTH, PLANES = 16, 1, 4
SCREEN_W, SCREEN_H, SCREEN_WDWIDTH = 320, 200, 20
FONT_W = FONT_H = 8

# The event kinds live in os_map for this file's sake: it runs in a bare checkout and cannot import
# harness, so they were spelt here as literals until they moved. test_os_memory_map.py pins them to
# os.h through that same mirror.
EVENT_CONOUT = os_map.OS_EVENT_CONOUT
EVENT_IKBD = os_map.OS_EVENT_IKBD
EVENT_GEM_MOUSE = os_map.OS_EVENT_GEM_MOUSE
EVENT_CURSOR = os_map.OS_EVENT_VDI_CURSOR
RASTER_OP_S_ONLY_INDEX = 3           # include/raster.h's RASTER_OP_S_ONLY: a plain copy

# ---- the reference implementation --------------------------------------------------------------
# The sixteen VDI logic operations, written out one per line rather than derived from a truth-table
# index. That is the point: raster.c computes them with one shift, and a reference that used the
# same trick would agree with a wrong shift as readily as with a right one.
LOGIC_OPS = (
    lambda s, d: 0,
    lambda s, d: s & d,
    lambda s, d: s & (1 - d),
    lambda s, d: s,
    lambda s, d: (1 - s) & d,
    lambda s, d: d,
    lambda s, d: s ^ d,
    lambda s, d: s | d,
    lambda s, d: 1 - (s | d),
    lambda s, d: 1 - (s ^ d),
    lambda s, d: 1 - d,
    lambda s, d: s | (1 - d),
    lambda s, d: 1 - s,
    lambda s, d: (1 - s) | d,
    lambda s, d: 1 - (s & d),
    lambda s, d: 1,
)


class Raster:
    """An ST device-format raster: planes interleaved a 16-pixel word at a time, MSB leftmost.

    Written from the format's definition (docs/graphics-formats.md's interleaved low-resolution
    layout), not from include/raster.h's helpers.
    """

    def __init__(self, data, w, h, wdwidth, nplanes):
        self.data = bytearray(data)
        self.w, self.h, self.wdwidth, self.nplanes = w, h, wdwidth, nplanes

    def inside(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h

    def _byte_and_mask(self, x, y, plane):
        word_bytes = 2 * self.nplanes
        offset = y * self.wdwidth * word_bytes + (x // 16) * word_bytes + plane * 2
        bit = 15 - (x % 16)
        return offset + (0 if bit >= 8 else 1), 1 << (bit % 8)

    def bit(self, x, y, plane):
        offset, mask = self._byte_and_mask(x, y, plane)
        return 1 if self.data[offset] & mask else 0

    def set_bit(self, x, y, plane, value):
        offset, mask = self._byte_and_mask(x, y, plane)
        if value:
            self.data[offset] |= mask
        else:
            self.data[offset] &= 0xFF ^ mask

    def set_pixel(self, x, y, colour):
        for plane in range(self.nplanes):
            self.set_bit(x, y, plane, (colour >> plane) & 1)


def font_row(ch, row):
    """Row `row` of the model's synthetic glyph for `ch`: the character's byte rotated left."""
    n = row % FONT_H
    return ((ch << n) | (ch >> (FONT_H - n))) & 0xFF if n else ch


def expected_cpyfm(src_bytes, dst_bytes, op, rect):
    """What vro_cpyfm must leave in the destination raster.

    READ-ALL-THEN-WRITE: the source is `src_bytes` throughout, so nothing this writes can change
    what a later step reads. For two disjoint rasters that is simply what a copy is; for the OVERLAP
    cases — where the probe hands the same raster's bytes in as both arguments — it is the answer a
    real VDI produces by choosing its copy direction, which is what those cases are asking about.
    They therefore use only logic operations that ignore the destination bit (a plain copy), where
    "direction chosen" and "source read first" are the same answer.
    """
    sx1, sy1, sx2, sy2, dx, dy = rect
    sx1, sx2 = sorted((sx1, sx2))
    sy1, sy2 = sorted((sy1, sy2))
    src = Raster(src_bytes, RASTER_SIDE, RASTER_SIDE, RASTER_WDWIDTH, PLANES)
    dst = Raster(dst_bytes, RASTER_SIDE, RASTER_SIDE, RASTER_WDWIDTH, PLANES)
    for row in range(sy2 - sy1 + 1):
        for col in range(sx2 - sx1 + 1):
            sx, sy, tx, ty = sx1 + col, sy1 + row, dx + col, dy + row
            if not src.inside(sx, sy) or not dst.inside(tx, ty):
                continue
            for plane in range(PLANES):
                dst.set_bit(tx, ty, plane,
                            LOGIC_OPS[op](src.bit(sx, sy, plane), dst.bit(tx, ty, plane)))
    return bytes(dst.data)


# ---- the cases the probe runs, and their geometry ----------------------------------------------
# (logic op, source x1, y1, x2, y2, destination x, y). The sixteen aligned cases exercise the ops;
# the five below them exercise the addressing — a shift within a word, a copy that crosses a word
# boundary, and the three clipping shapes.
CPYFM_CASES = {f"op{op}": (op, 0, 0, RASTER_SIDE - 1, RASTER_SIDE - 1, 0, 0) for op in range(16)}
CPYFM_CASES.update({
    "shift3": (3, 0, 0, 7, 7, 3, 5),
    "shift13": (7, 2, 1, 9, 8, 13, 2),
    "clip_negative": (3, 0, 0, 7, 7, -4, -4),
    "clip_past_edge": (3, 0, 0, 7, 7, 12, 12),
    "reversed_rect": (3, 7, 7, 0, 0, 0, 0),
    # A destination entirely off its raster: every pixel is clipped, so the copy must move NOTHING
    # and return. The direction-chosen walk counts to an end rather than testing an ordering, so an
    # empty range that reached it would step past that end and never stop.
    "clip_entirely_out": (3, 0, 0, 7, 7, 20, 20),
})
# ...and the three OVERLAPPING copies, source and destination in ONE raster. A model that always ran
# top-left to bottom-right smears the source down (or across) the raster instead of moving it; these
# are the cases that say so, one per direction the choice has to get right.
OVERLAP_CASES = {
    "overlap_down": (3, 0, 0, 15, 11, 0, 4),
    "overlap_right": (3, 0, 0, 11, 15, 4, 0),
    "overlap_up": (3, 0, 4, 15, 15, 0, 0),
}
CPYFM_CASES.update(OVERLAP_CASES)
# ...and one the parametrized reference deliberately does NOT run: a rectangle far larger than
# either raster, which the reference would iterate 900 million times. It has its own case below.
HUGE_RECT_CLIPPED = (0, 0, RASTER_SIDE - 1, RASTER_SIDE - 1, 0, 0)

# The text and fill cases both draw on the screen and report a window of it: eight rows, two
# 16-pixel words wide, starting at word 1 (x = 16).
WINDOW_WORD0, WINDOW_WORDS = 1, 2
WINDOW_W = WINDOW_WORDS * 16
TEXT_X, TEXT_BASELINE, TEXT_COLOUR, TEXT = 16, 40, 5, "Hi"
RECFL_RECT, RECFL_COLOUR = (18, 41, 40, 44), 6


def window_raster(data):
    """A Raster over one reported screen window. The window is a contiguous run of whole interleaved
    words per row, so its bytes are themselves a device-format raster of `WINDOW_WORDS` words."""
    return Raster(data, WINDOW_W, FONT_H, WINDOW_WORDS, PLANES)


@pytest.fixture(scope="module")
def cases(tmp_path_factory):
    binary = compile_probe(PROBE_SRC, tmp_path_factory.mktemp("os_model"), extra_src=CANDIDATE_SRC)
    return run_probe(binary)


def raster_of(cases, name):
    """The bytes a case printed for one raster window, in address order."""
    printed = cases[name]["file"]
    assert printed, f"the probe printed no bytes for {name}"
    return bytes(printed[i] for i in range(len(printed)))


# Every opcode `src/gem.c` models, and the two doors each is driven through. The list is spelt here
# rather than derived from what the probe printed, so that an opcode added to the model without a
# row in the probe's table fails the count below instead of quietly going untested on one door.
DOOR_VDI_OPCODES = ("v_clrwk", "v_gtext", "vst_height", "vst_color", "vsf_interior", "vsf_style",
                    "vsf_color", "vswr_mode", "v_opnvwk", "v_clsvwk", "vro_cpyfm", "vr_recfl",
                    "v_show_c", "v_hide_c", "vq_mouse", "vq_key_s", "vs_clip")
DOOR_AES_OPCODES = ("appl_init", "appl_exit", "graf_handle", "graf_mouse")
DOOR_CASES = tuple(f"door_{name}" for name in DOOR_VDI_OPCODES + DOOR_AES_OPCODES)


def test_the_probe_ran_every_case(cases):
    """Guard the fixture: a probe that stopped printing would make every case below vacuous."""
    expected = set(CPYFM_CASES) | {
        "opnvwk", "opnvwk_work_in", "clsvwk", "vst_height", "vq_mouse", "vq_key_s", "vs_clip",
        "clrwk", "recfl", "gtext", "candidate_ledger",
        "vsf_color", "vsf_color_high", "vsf_color_negative", "vst_color", "vswr_mode",
        "vsf_interior", "vsf_style",
        "trap_cconout", "trap_cconws", "trap_cconws_unterminated", "trap_cconis_idle", "trap_cconis_key", "trap_crawcin",
        "trap_crawcin_idle", "trap_cnecin", "trap_fseek", "trap_bconout_ikbd",
        "trap_bconout_console", "trap_malloc", "candidate_malloc", "huge_rect",
        "trap_crawio_write", "trap_crawio_write_keeps_the_key", "trap_crawio_read", "console_walk",
        "console_flag_spelling",
        "wrapping_contrl", "wrapping_ptsout", "wrapping_intout",
        "recfl_off_bottom_right", "recfl_off_top_left", "recfl_hollow",
        "recfl_pattern", "recfl_hatch", "recfl_user",
    }
    expected |= {f"{door}_{side}" for door in DOOR_CASES for side in ("trap", "direct")}
    assert expected <= set(cases), f"the probe printed no scalars for {sorted(expected - set(cases))}"


# ---- the raster core ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(CPYFM_CASES))
def test_vro_cpyfm_matches_the_reference(cases, name):
    """Every logic operation, and every addressing shape, against the independent reference."""
    op, *rect = CPYFM_CASES[name]
    assert cases[name]["scalars"]["modeled"] == 1, f"{name}: the model refused a call it must serve"
    assert cases[name]["scalars"]["refusals"] == 0
    got = raster_of(cases, f"{name}_out")
    want = expected_cpyfm(raster_of(cases, f"{name}_src"), raster_of(cases, f"{name}_in"),
                          op, tuple(rect))
    assert got == want, (
        f"{name}: vro_cpyfm under logic op {op} wrote bytes the reference does not agree with\n"
        f"  model:     {got.hex(' ')}\n"
        f"  reference: {want.hex(' ')}")


def test_a_rectangle_larger_than_the_raster_copies_the_part_that_fits(cases):
    """A garbage source rectangle — four signed words off the emulated program's stack — must copy
    the part that fits and RETURN. That it returns at all is the assertion the probe having printed
    this case already makes: the model clips its LOOP bounds, and a per-pixel clip would iterate
    900 million times instead. What is checked here is that clipping the loop did not also lose the
    pixels that were in range."""
    assert cases["huge_rect"]["scalars"]["modeled"] == 1
    want = expected_cpyfm(raster_of(cases, "huge_rect_src"), raster_of(cases, "huge_rect_in"),
                          RASTER_OP_S_ONLY_INDEX, HUGE_RECT_CLIPPED)
    assert raster_of(cases, "huge_rect_out") == want


def test_a_clipped_copy_leaves_the_rest_of_the_destination_alone(cases):
    """The half of clipping the reference could satisfy by copying nothing: the pixels that ARE in
    range must still move. `clip_past_edge` puts an 8x8 source at (12,12) of a 16x16 raster, so a
    quarter of it lands and three quarters are dropped."""
    before, after = raster_of(cases, "clip_past_edge_in"), raster_of(cases, "clip_past_edge_out")
    assert before != after, "the clipped copy moved nothing at all — the case tests nothing"


# ---- v_opnvwk and the attribute calls -----------------------------------------------------------
@pytest.mark.parametrize("case", ("opnvwk", "opnvwk_work_in"))
def test_v_opnvwk_returns_the_handle_where_the_caller_reads_it(cases, case):
    """In contrl[6]: the DRI binding copies it back out of there, and a model that only filled
    intout would hand every program a workstation handle of whatever was in the block."""
    scalars = cases[case]["scalars"]
    assert scalars["modeled"] == 1
    assert scalars["handle"] == 1
    assert scalars["state_handle"] == 1


@pytest.mark.parametrize("case", ("opnvwk", "opnvwk_work_in"))
def test_v_opnvwk_reports_the_low_resolution_workstation(cases, case):
    scalars = cases[case]["scalars"]
    assert (scalars["max_x"], scalars["max_y"], scalars["colours"]) == (319, 199, 16)
    assert (scalars["ptsout_n"], scalars["intout_n"]) == (6, 45)


@pytest.mark.parametrize("case", ("opnvwk", "opnvwk_work_in"))
def test_v_opnvwk_zeroes_every_work_out_slot_it_reports(cases, case):
    """It claims 45 intout entries and 6 ptsout pairs, and fills three of them. The other 48 have to
    be WRITTEN, not left: the probe pre-fills both arrays, so a caller walking what the call says it
    wrote would otherwise read its own leftovers back as workstation attributes."""
    scalars = cases[case]["scalars"]
    assert (scalars["intout_middle"], scalars["intout_last"], scalars["ptsout_last"]) == (0, 0, 0)


@pytest.mark.parametrize("case, text, interior, style, fill", (
    ("opnvwk", 1, 1, 1, 1),                  # Bubble Ghost's own call: every work_in entry is 1
    ("opnvwk_work_in", 4, 0, 3, 7),          # ...and four distinct values, so a swapped slot shows
))
def test_v_opnvwk_installs_the_attributes_work_in_asked_for(cases, case, text, interior, style, fill):
    """A fresh image is all zeroes, which is not a workstation's state; OPENING one is what makes the
    attributes real — and the attributes are the CALLER's, out of work_in (os.h, VDI_WORK_IN_*)."""
    scalars = cases[case]["scalars"]
    assert scalars["text_colour"] == text
    assert scalars["fill_interior"] == interior
    assert scalars["fill_style"] == style
    assert scalars["fill_colour"] == fill
    assert scalars["refusals"] == 0


@pytest.mark.parametrize("case", ("opnvwk", "opnvwk_work_in"))
def test_v_opnvwk_installs_the_defaults_work_in_cannot_express(cases, case):
    """The writing mode, the text height and the clip flag have no work_in entry, so opening a
    workstation is what sets them — to the VDI's own defaults, whatever the caller passed."""
    scalars = cases[case]["scalars"]
    assert (scalars["write_mode"], scalars["text_height"], scalars["clip_on"]) == (1, 8, 0)


def test_v_clsvwk_clears_the_handle(cases):
    assert cases["clsvwk"]["scalars"] == {"modeled": 1, "state_handle": 0}


@pytest.mark.parametrize("name, asked, stored", (
    ("vsf_color", 11, 11),
    ("vsf_color_high", 99, 15),          # clamped to the pens the device has
    ("vsf_color_negative", 0xFFFD, 0),   # ...and at the other end: -3 as the caller pushed it
    ("vst_color", 13, 13),
    ("vswr_mode", 2, 2),
    ("vsf_interior", 2, 2),
    ("vsf_style", 4, 4),
))
def test_an_attribute_call_stores_and_echoes_what_it_set(cases, name, asked, stored):
    """Every attribute call answers with the value it actually set — which for a colour is the
    CLAMPED one, and a game reads it."""
    scalars = cases[name]["scalars"]
    assert scalars["modeled"] == 1
    assert scalars["stored"] == stored, f"{name}: asked {asked:#x}, stored {scalars['stored']}"
    assert scalars["echoed"] == stored, f"{name}: stored {stored} but echoed {scalars['echoed']}"
    assert scalars["intout_n"] == 1


def test_vst_height_answers_the_models_one_font(cases):
    scalars = cases["vst_height"]["scalars"]
    assert scalars["modeled"] == 1
    assert (scalars["char_w"], scalars["char_h"]) == (FONT_W, FONT_H)
    assert (scalars["cell_w"], scalars["cell_h"]) == (FONT_W, FONT_H)
    assert scalars["ptsout_n"] == 2
    assert scalars["requested"] == 6, "the requested height is recorded even though it changes nothing"


# ---- the queries --------------------------------------------------------------------------------
def test_vq_mouse_reports_the_poked_state_without_consuming_it(cases):
    scalars = cases["vq_mouse"]["scalars"]
    assert scalars["modeled"] == 1
    assert (scalars["x"], scalars["y"], scalars["buttons"]) == (137, 88, 1)
    assert (scalars["ptsout_n"], scalars["intout_n"]) == (1, 1)
    assert scalars["x_again"] == 137, (
        "a second vq_mouse read 0 — the model consumed the position, which no mouse driver does")


def test_vq_key_s_reports_the_poked_shift_state(cases):
    scalars = cases["vq_key_s"]["scalars"]
    assert (scalars["modeled"], scalars["state"], scalars["intout_n"]) == (1, 3, 1)


def test_vs_clip_stores_the_rectangle_normalised(cases):
    """The caller passed (60,30)-(10,20), corners the wrong way round; every later range test is a
    plain comparison, so the model orders them once here."""
    scalars = cases["vs_clip"]["scalars"]
    assert scalars["modeled"] == 1
    assert (scalars["on"], scalars["x1"], scalars["y1"], scalars["x2"], scalars["y2"]) == \
        (1, 10, 20, 60, 30)


def test_v_clrwk_clears_the_whole_screen(cases):
    scalars = cases["clrwk"]["scalars"]
    assert scalars["modeled"] == 1
    assert scalars["nonzero_bytes"] == 0


# ---- the two drawing calls that are not raster copies --------------------------------------------
def test_vr_recfl_fills_exactly_the_rectangle(cases):
    """Every pixel inside the rectangle takes the fill colour and every pixel outside it is
    untouched — the second half is what a fill one row or one word too generous fails."""
    before, after = window_raster(raster_of(cases, "recfl_in")), \
        window_raster(raster_of(cases, "recfl_out"))
    x1, y1, x2, y2 = RECFL_RECT
    want = Raster(before.data, before.w, before.h, before.wdwidth, before.nplanes)
    for y in range(y1, y2 + 1):
        for x in range(x1, x2 + 1):
            if want.inside(x - WINDOW_WORD0 * 16, y - TEXT_BASELINE):
                want.set_pixel(x - WINDOW_WORD0 * 16, y - TEXT_BASELINE, RECFL_COLOUR)
    assert bytes(after.data) == bytes(want.data)


@pytest.mark.parametrize("case, rect", (
    ("recfl_off_bottom_right", (-20, 195, 400, 250)),
    ("recfl_off_top_left", (-20, -5, 10, 3)),
))
def test_vr_recfl_clips_a_rectangle_that_runs_off_the_screen(cases, case, rect):
    """Two halves of one property. The PIXEL COUNT catches a fill one column too generous, which
    does not spill outside the framebuffer at all — it wraps onto another row, where a window would
    never look. The CANARY catches one row too generous, which writes outside the framebuffer and
    inside the image, where nothing faults and no pixel count would show it."""
    x1, y1, x2, y2 = rect
    kept_x = min(x2, SCREEN_W - 1) - max(x1, 0) + 1
    kept_y = min(y2, SCREEN_H - 1) - max(y1, 0) + 1
    assert cases[case]["scalars"]["modeled"] == 1
    assert cases[case]["scalars"]["pixels_set"] == kept_x * kept_y
    assert cases[case]["scalars"]["canary_damage"] == 0, (
        "the fill wrote outside the 32,000-byte framebuffer — inside the image, so nothing faulted")


def test_a_hollow_fill_paints_the_background_rather_than_the_fill_colour(cases):
    """The VDI's fill INTERIOR decides the colour before the fill colour does: HOLLOW paints colour
    0 and ignores the pen entirely. The case fills SOLID first and then hollow over the same
    rectangle, so "painted the background" is distinguishable from "did nothing"."""
    scalars = cases["recfl_hollow"]["scalars"]
    assert scalars["pixels_before"] > 0, "the solid fill painted nothing — the case tests nothing"
    assert scalars["modeled"] == 1
    assert scalars["pixels_after"] == 0


@pytest.mark.parametrize("case", ("recfl_pattern", "recfl_hatch", "recfl_user"))
def test_a_patterned_fill_is_refused_rather_than_filled_solid(cases, case):
    """Pattern, hatch and user-defined interiors each need a pattern table the model does not have.
    Filling them solid would draw pixels no real machine draws, so the call is refused by name and
    the rectangle is left alone (`test_os_refusal.py` pins the candidate-side tally)."""
    assert cases[case]["scalars"]["modeled"] == 0
    assert cases[case]["scalars"]["pixels_set"] == 0


def test_v_gtext_draws_the_synthetic_font_at_the_baseline(cases):
    """The glyph's eight rows sit at [y - 7, y] — the VDI's default alignment is left/baseline — and
    only the set bits are written, in the text colour."""
    before = window_raster(raster_of(cases, "gtext_in"))
    want = Raster(before.data, before.w, before.h, before.wdwidth, before.nplanes)
    for index, char in enumerate(TEXT):
        for row in range(FONT_H):
            bits = font_row(ord(char), row)
            for col in range(FONT_W):
                if bits & (0x80 >> col):
                    want.set_pixel(index * FONT_W + col, row, TEXT_COLOUR)
    assert raster_of(cases, "gtext_once") == bytes(want.data)


def test_v_gtext_is_idempotent(cases):
    """Drawing the same string over itself changes nothing. The model writes pixel VALUES rather
    than combining with what is there, so this is the property that says so."""
    assert raster_of(cases, "gtext_once") == raster_of(cases, "gtext_twice")


# ---- the off-image OS event ledger ---------------------------------------------------------------
def test_the_candidate_records_every_kind_of_event_in_order(cases):
    """v_hide_c, v_show_c, two console bytes, an IKBD command and graf_mouse — one stream, in the
    order they were made, because the order between them is a fact about the program too."""
    assert cases["candidate_ledger"]["ledger"] == [
        (EVENT_CURSOR, 0), (EVENT_CURSOR, 1),
        (EVENT_CONOUT, ord("H")), (EVENT_CONOUT, ord("i")),
        (EVENT_IKBD, 0x12), (EVENT_GEM_MOUSE, 256),
    ]
    assert cases["candidate_ledger"]["scalars"]["refusals"] == 0


# ---- the ORACLE's door: shim.c's own decode of each trap's stack frame ----------------------------
def test_the_trap_dispatch_logs_one_console_byte(cases):
    assert cases["trap_cconout"]["scalars"]["unmodeled"] == 0
    assert cases["trap_cconout"]["ledger"] == [(EVENT_CONOUT, ord("X"))]


def test_cconws_logs_every_byte_and_returns_the_count(cases):
    scalars = cases["trap_cconws"]["scalars"]
    assert (scalars["unmodeled"], scalars["d0"]) == (0, 3)
    assert cases["trap_cconws"]["ledger"] == [(EVENT_CONOUT, ord(c)) for c in "Ok!"]


def test_an_unterminated_cconws_is_refused_and_ledgers_nothing(cases):
    """A string with no NUL inside the image is refused rather than cut off at the edge — the model
    has no idea where it was meant to end. Its ledger must be EMPTY: a refused call leaves no trace
    on either side (the rule gem_dispatch follows when it drops an event a faulted call reported),
    and a walk that logged as it went would have pushed every byte it passed before finding out."""
    assert cases["trap_cconws_unterminated"]["scalars"]["unmodeled"] == 1
    assert cases["trap_cconws_unterminated"]["ledger"] == []


def test_cconis_answers_the_staged_key_without_consuming_it(cases):
    assert cases["trap_cconis_idle"]["scalars"]["d0"] == 0
    assert cases["trap_cconis_key"]["scalars"]["d0"] == 0xFFFFFFFF
    assert cases["trap_cconis_key"]["scalars"]["unmodeled"] == 0


@pytest.mark.parametrize("case", ("trap_crawcin", "trap_cnecin"))
def test_a_blocking_console_read_returns_the_staged_key(cases, case):
    """Crawcin and Cnecin are one model, so both return the whole longword Bconin would."""
    assert cases[case]["scalars"]["unmodeled"] == 0
    assert cases[case]["scalars"]["d0"] == 0x00230061


def test_a_blocking_console_read_with_no_key_is_refused(cases):
    """Never fabricated and never spun on: the real call waits, and there is nothing here to wait
    for, so the run is rejected instead."""
    assert cases["trap_crawcin_idle"]["scalars"]["unmodeled"] == 1


def test_crawio_writing_a_character_is_a_console_ledger_entry(cases):
    """Crawio's WRITE direction is console output and takes the same entry Cconout takes. Modeled as
    nothing, a reconstruction that prints through it is byte-identical to one that prints nothing."""
    scalars = cases["trap_crawio_write"]["scalars"]
    assert (scalars["unmodeled"], scalars["d0"]) == (0, 0)
    assert cases["trap_crawio_write"]["ledger"] == [(EVENT_CONOUT, ord("Z"))]


def test_crawio_writing_a_character_does_not_eat_the_staged_key(cases):
    """The two directions share one trap number, so servicing every Crawio as a read would let a
    program that prints a character swallow the keystroke a later read is waiting for."""
    assert cases["trap_crawio_write_keeps_the_key"]["scalars"]["still_pending"] == 1
    assert cases["trap_crawio_write_keeps_the_key"]["ledger"] == [(EVENT_CONOUT, ord("Z"))]


def test_crawio_reading_takes_the_staged_key_and_logs_nothing(cases):
    """...and the mirror half: a read is not console output."""
    scalars = cases["trap_crawio_read"]["scalars"]
    assert (scalars["unmodeled"], scalars["d0"]) == (0, 0x00230061)
    assert cases["trap_crawio_read"]["ledger"] == []


def test_a_staged_walk_of_keys_is_consumed_oldest_first(cases):
    """`harness.console_keys` stages more than one keystroke; the model hands them out in order and
    then refuses, exactly as an idle console always did. A queue that returned the head twice, or
    the newest first, is what this separates from a correct one."""
    scalars = cases["console_walk"]["scalars"]
    assert (scalars["key0"], scalars["key1"], scalars["key2"]) == (0x00110071, 0x00120077,
                                                                   0x00130065)
    assert scalars["still_pending"] == 0
    assert scalars["exhausted"] == 0, "a fourth read answered with something rather than refusing"
    assert scalars["refusals"] == 1


def test_a_pending_count_the_queue_cannot_hold_is_one_keystroke(cases):
    """OS_CON_PENDING's contract has always been "nonzero = a character is waiting", and a
    hand-written poke dict may put any nonzero longword there. The queue refines that field without
    replacing it, so a count it cannot hold is read as the older spelling and served as ONE key —
    which is what keeps the one-key path writing exactly the one word it always wrote, under a
    program whose own code covers this block."""
    scalars = cases["console_flag_spelling"]["scalars"]
    assert scalars["key"] == 0x00230061
    assert scalars["still_pending"] == 0
    assert scalars["exhausted"] == 0, "the follower in the queue was served, so the count was walked"
    assert scalars["refusals"] == 1


def test_fseek_moves_the_staged_files_cursor_and_returns_the_position(cases):
    scalars = cases["trap_fseek"]["scalars"]
    assert (scalars["unmodeled"], scalars["d0"], scalars["cursor"]) == (0, 4, 4)


def test_bconout_to_the_ikbd_is_a_ledger_entry(cases):
    assert cases["trap_bconout_ikbd"]["scalars"]["unmodeled"] == 0
    assert cases["trap_bconout_ikbd"]["ledger"] == [(EVENT_IKBD, 0x12)]


def test_bconout_to_any_other_device_is_refused(cases):
    """The model has no account of what receiving a byte does on the console, the printer, the
    serial line or MIDI, so it refuses rather than answering wrongly."""
    assert cases["trap_bconout_console"]["scalars"]["unmodeled"] == 1
    assert cases["trap_bconout_console"]["ledger"] == []


# ---- GEMDOS Malloc: two implementations of one bump allocator -----------------------------------
MALLOC_FIRST, MALLOC_SECOND = 5, 8
MALLOC_MOVED_BASE = 0x40000   # os_model_probe.c's, for the base-install case


def test_the_two_malloc_arenas_hand_out_the_same_blocks(cases):
    """The shim services the GEMDOS trap and src/os_heap.c serves a reconstruction, so a divergence
    here is a reconstruction allocating somewhere the original did not — invisible until the block's
    contents land at the wrong address."""
    base = cases["candidate_malloc"]["scalars"]["base"]
    second = cases["candidate_malloc"]["scalars"]["second"]
    assert cases["candidate_malloc"]["scalars"]["first"] == base
    assert second == base + MALLOC_FIRST + 1, (
        "the odd first request must round UP to a word before the second block starts")
    assert cases["trap_malloc"]["scalars"]["unmodeled"] == 0
    assert cases["trap_malloc"]["scalars"]["d0"] == second, (
        "the oracle's second Malloc and the candidate's answered different addresses")


def test_malloc_minus_one_answers_the_free_size_without_consuming_the_arena(cases):
    """GEMDOS's "how big is the largest free block?" query answers a SIZE — the window still free —
    and moves nothing. It used to fall out of the rounding as the arena BASE, which is a
    plausible-looking address and the wrong answer to the question."""
    scalars = cases["candidate_malloc"]["scalars"]
    assert scalars["query"] == scalars["limit"] - scalars["base"]
    assert scalars["after_query"] == scalars["base"], (
        "Malloc(-1) moved the bump pointer, so the next real allocation started past the base")


def test_the_arena_reset_rewinds_the_bump_pointer(cases):
    """What harness.arm_candidate calls before every run; without it the second case in a process
    allocates where the first left off while the oracle starts from the base."""
    scalars = cases["candidate_malloc"]["scalars"]
    assert scalars["after_reset"] == scalars["base"]


def test_installing_a_base_moves_the_arena_immediately(cases):
    """A project that moved its heap installs the base once at import, and `os_malloc` has to be in
    the new arena from that moment — not from the first `g_os_heap_reset`. Until it was, any
    allocation outside a harness-armed run came out of OS_HEAP_BASE_DEFAULT: the wrong arena
    entirely, and for a project whose program covers the default, on top of its own code."""
    assert cases["candidate_malloc"]["scalars"]["after_move"] == MALLOC_MOVED_BASE


def test_the_arena_has_a_ceiling_and_refuses_to_grow_past_it(cases):
    """A block handed out over the staged-file table is a plain image write on both sides, so the
    two corrupted runs compare EQUAL. The window's last block is served, the next request is
    refused, and the query then reports nothing free."""
    scalars = cases["candidate_malloc"]["scalars"]
    assert scalars["fills_the_window"] == scalars["base"]
    assert scalars["at_the_ceiling"] == scalars["limit"]
    assert scalars["query_at_the_ceiling"] == 0
    assert scalars["past_the_ceiling"] == 0, "GEMDOS answers a failed Malloc with 0"
    assert scalars["ceiling_refusals"] == 1


@pytest.mark.parametrize("case", ("wrapping_contrl", "wrapping_ptsout", "wrapping_intout"))
def test_a_parameter_block_that_wraps_the_address_space_is_refused(cases, case):
    """`contrl` = 0xfffffffe, and the same for the two output arrays. `base + index * 2` WRAPS in
    32-bit arithmetic and lands back in low memory, so a bounds test made after the wrap found the
    address inside the image, served the access, and wrote the harness's own staging area while
    reporting the call served. The sum is taken in 64 bits, so every one of these faults."""
    assert cases[case]["scalars"]["modeled"] == 0
    assert cases[case]["scalars"]["low_memory_damage"] == 0, (
        "the model wrote into low memory through a wrapped parameter-block pointer")


def test_every_modeled_opcode_has_a_two_door_case():
    """The count, so that an opcode added to `src/gem.c` cannot be tested on one door only.
    Seventeen VDI opcodes and four AES ones — TRAP_MODEL.md's Phase 12 table."""
    assert len(DOOR_CASES) == len(DOOR_VDI_OPCODES) + len(DOOR_AES_OPCODES) == 21


@pytest.mark.parametrize("door", DOOR_CASES)
def test_both_doors_onto_one_opcode_write_the_same_bytes(cases, door):
    """`trap #2` through the oracle's own stack-frame decode, and `os_gem_trap()` through os.h's
    wrapper, on the same parameter block and the same starting state. This is the property the whole
    shared-source arrangement exists for, and the only one a per-side decode could break — so it is
    asked of every opcode rather than of one."""
    assert cases[f"{door}_trap"]["scalars"]["unmodeled"] == 0, "the oracle refused a modeled opcode"
    assert cases[f"{door}_direct"]["scalars"]["modeled"] == 1
    assert cases[f"{door}_direct"]["scalars"]["refusals"] == 0
    assert cases[f"{door}_direct"]["scalars"]["differing_bytes"] == 0, (
        f"{door}: the trap door and the wrapper left different bytes behind")


@pytest.mark.parametrize("door", DOOR_CASES)
def test_both_doors_onto_one_opcode_record_the_same_events(cases, door):
    """The ledgers are the one thing the two doors do NOT share: shim.c keeps the oracle's and
    src/os_log.c keeps the candidate's, so v_show_c, v_hide_c and graf_mouse have a separate
    recording site on each side and only a case driving both can say they agree."""
    assert cases[f"{door}_trap"]["ledger"] == cases[f"{door}_direct"]["ledger"]


@pytest.mark.parametrize("door, entry", (
    ("door_v_show_c", (EVENT_CURSOR, 1)),
    ("door_v_hide_c", (EVENT_CURSOR, 0)),
    ("door_graf_mouse", (EVENT_GEM_MOUSE, 256)),
))
def test_the_three_off_image_gem_calls_are_ledgered_on_both_doors(cases, door, entry):
    """...and what they record. Equality above would be satisfied by two sides that both record
    NOTHING, which is exactly the reconstruction the ledger exists to catch."""
    assert cases[f"{door}_trap"]["ledger"] == [entry]
    assert cases[f"{door}_direct"]["ledger"] == [entry]


@pytest.mark.parametrize("door", DOOR_CASES)
def test_a_serviced_vdi_call_is_tallied_as_a_poked_input_call(cases, door):
    """Every VDI opcode reads or writes the VDI state block, which lives inside the harness-poked
    region — so shim.c tallies it exactly as it tallies a Bconin, and `emu._vet_no_poked_input_read`
    rejects such a run under a project whose program covers those addresses. The AES's four opcodes
    touch only the caller's own arrays and must NOT be tallied, or every GEM program would be
    refused under that overlap."""
    expected = 1 if door[len("door_"):] in DOOR_VDI_OPCODES else 0
    assert cases[f"{door}_trap"]["scalars"]["poked_input_calls"] == expected
