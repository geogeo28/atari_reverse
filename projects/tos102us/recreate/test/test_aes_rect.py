"""AES rc_intersect ($fecd22) — the rectangle layer's worked example: `src/aes/rect.c`.

    per axis:  origin = max(rect.o, clip.o); far = min(rect.o + rect.e, clip.o + clip.e)   (word sums, signed compares)
               rect.o = origin; rect.e = far - origin; the flags of that `sub.w` saved (`move sr`)
    D0.w = both axes' `sub.w` said far > origin (`ble` on each, the x axis's flags popped off the stack)

Hand 68000 in the ROM — the utility layer both the AES and the desk call, returning by `rts` through the helpers'
shared tails — so a Line-F CALL reaches it and no Line-F RETURN leaves it: the mask word is never stored, and its
drop in the door drops nothing (the case that says so is here). Seeded with the snapshot's own rectangles: the desktop
window's current and full GRECTs (`aes/aes.h`'s WIN_CURR / WIN_FULL of window 0), the ones wm_calc and the redraw
clip against each other.
"""
import pytest

from harness import BASE_IMAGE
from recreate_kit.os_map import OS_BUS_ADDR_MASK

import aes
import case
import routines
import vdi
import vdi_helpers
from case import merge_pokes

NAME = "AES_ROM_RC_INTERSECT"
CORE = routines.core_symbol(NAME)
aes.declare_alcyon(NAME, aes.WORD_ANSWER, (vdi.IMAGE_ARG, vdi.LONG_ARG, vdi.LONG_ARG))

DESKTOP_CURR = aes.AES_WINDOWS + aes.WIN_CURR
DESKTOP_FULL = aes.AES_WINDOWS + aes.WIN_FULL
CLIP_AT = aes.RECTS_AT
RECT_AT = aes.RECTS_AT + aes.GRECT_BYTES


def rect_of(image, at):
    """A GRECT back as four signed words."""
    return tuple(aes.signed(aes.read_field(image, "GRECT", name, at)) for name in ("X", "Y", "W", "H"))


def signed_rect(rect):
    """A staged GRECT's four values as the signed words the machine holds."""
    return tuple(aes.signed(value) for value in rect)


def model(clip, rect):
    """The intersection as the ROM computes it, axis by axis: (the stored GRECT, the answer)."""
    def axis(clip_origin, clip_extent, origin, extent):
        far = min(aes.signed(origin + extent), aes.signed(clip_origin + clip_extent))
        near = max(origin, clip_origin)
        return near, aes.signed(far - near), far > near
    x, w, across = axis(clip[0], clip[2], rect[0], rect[2])
    y, h, down = axis(clip[1], clip[3], rect[1], rect[3])
    return (x, y, w, h), int(across and down)


def intersect(clip, rect, **kwargs):
    """rc_intersect of two staged GRECTs."""
    pokes = merge_pokes(aes.grect_pokes(CLIP_AT, *clip), aes.grect_pokes(RECT_AT, *rect))
    return aes.run_function(NAME, (CLIP_AT, RECT_AT), aes.leaf_machine(onto=pokes), **kwargs)


# (clip, rect): every branch of every min and max on both axes, both answers, and the words that wrap.
SHAPES = {
    "rect inside clip": ((0, 0, 320, 200), (10, 20, 30, 40)),
    "clip inside rect": ((10, 20, 30, 40), (0, 0, 320, 200)),
    "overlap to the lower right": ((0, 0, 100, 100), (50, 60, 100, 100)),
    "overlap to the upper left": ((50, 60, 100, 100), (0, 0, 100, 100)),
    "disjoint across, overlapping down": ((0, 0, 10, 100), (20, 0, 10, 100)),
    "overlapping across, disjoint down": ((0, 0, 100, 10), (0, 20, 100, 10)),
    "edges touching": ((0, 0, 10, 10), (10, 10, 10, 10)),
    "negative origins": ((-50, -40, 100, 80), (-80, -10, 60, 30)),
    "a far edge that wraps negative": ((0, 0, 0x7000, 0x7000), (0x7000, 0x7000, 0x2000, 0x2000)),
    "an extent that overflows but overlaps": ((-0x7000, -0x7000, 0xE000, 0xE000), (-0x7000, -0x7000, 0xE000, 0xE000)),
}


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_the_second_rectangle_is_cut_to_the_intersection(shape, through_line_f):
    clip, rect = SHAPES[shape]
    result = intersect(clip, rect, through_line_f=through_line_f)
    stored, answer = model(clip, rect)
    assert rect_of(result.final, RECT_AT) == stored
    assert result.answer() == answer
    assert rect_of(result.final, CLIP_AT) == signed_rect(clip), "the clip is only read"


def test_the_answer_is_the_signed_compare_not_the_stored_extent_s_sign():
    """$9000 to $7000: the extent stored is $e000, negative as a word, and the axis is still non-empty — the `ble`
    after `sub.w` folds the overflow in, where a test of the stored extent would answer 0."""
    stored, answer = model(*SHAPES["an extent that overflows but overlaps"])
    assert stored[2] < 0 and answer == 1
    assert intersect(*SHAPES["an extent that overflows but overlaps"]).answer() == 1


def test_the_y_pass_reads_the_x_pass_s_stores():
    """The ORDER, which only an overlap shows: the clip laid one word BELOW the rectangle, so clip.y is rect.x and
    clip.h is rect.w — both stored by the x pass. rect (10, 0, 50, 70) under a clip.x of 20: the x pass stores x 20
    and w 0, and the y pass then clips 0..70 to 20..20 — y 20, h 0. Read before the stores it would be y 10, h 50."""
    clip_at = RECT_AT - aes.WORD_BYTES
    pokes = merge_pokes(aes.grect_pokes(RECT_AT, 10, 0, 50, 70), aes.field_pokes("GRECT", clip_at, X=20))
    result = aes.run_function(NAME, (clip_at, RECT_AT), aes.leaf_machine(onto=pokes))
    assert rect_of(result.final, RECT_AT) == (20, 20, 0, 0)
    assert result.answer() == 0


def test_both_pointers_are_put_on_the_24_bit_bus():
    """The clip and the rectangle pointers with a top byte, as an application's GRECTs reach the AES: both addressed
    through 24 bits."""
    clip, rect = SHAPES["overlap to the lower right"]
    pokes = merge_pokes(aes.grect_pokes(CLIP_AT, *clip), aes.grect_pokes(RECT_AT, *rect))
    result = aes.run_function(NAME, (CLIP_AT | aes.BUS_TAG, RECT_AT | aes.BUS_TAG), aes.leaf_machine(onto=pokes))
    assert rect_of(result.final, RECT_AT) == model(clip, rect)[0]


# THE BUS TOP: a GRECT is held as ONE bus address and its words reached as displacements from it (`rect.c`'s
# `grect_at`), so the host refuses a GRECT straddling the top of the 24-bit bus rather than read past its image — the
# ROM would wrap it word by word, and can be handed one only in the I/O page, which no model serves.
LAST_GRECT_THAT_FITS = OS_BUS_ADDR_MASK + 1 - aes.GRECT_BYTES
CORE_ARGTYPES = ["ctypes.c_void_p", "ctypes.c_uint32", "ctypes.c_uint32"]


@pytest.mark.parametrize("at", (LAST_GRECT_THAT_FITS + aes.WORD_BYTES, LAST_GRECT_THAT_FITS + aes.GRECT_H))
def test_a_rectangle_straddling_the_top_of_the_bus_is_refused_on_the_host(at):
    for clip, rect in ((CLIP_AT, at), (at, RECT_AT)):
        returncode, stderr = vdi_helpers.refusal(CORE, CORE_ARGTYPES, f"buf, {clip}, {rect}")
        assert returncode != 0 and "past the top of the 24-bit bus" in stderr, stderr


def test_the_last_rectangle_below_the_top_of_the_bus_is_served():
    """The bound's other side: a GRECT whose last word is the bus's last word runs, as clip and as rect."""
    returncode, stderr = vdi_helpers.refusal(CORE, CORE_ARGTYPES, f"buf, {LAST_GRECT_THAT_FITS}, {LAST_GRECT_THAT_FITS}")
    assert returncode == 0, stderr


def test_a_rectangle_with_itself_is_unchanged():
    result = aes.run_function(NAME, (RECT_AT, RECT_AT), aes.leaf_machine(onto=aes.grect_pokes(RECT_AT, 3, 4, 5, 6)))
    assert rect_of(result.final, RECT_AT) == (3, 4, 5, 6) and result.answer() == 1


def test_the_desktop_window_s_rectangles_over_the_snapshot():
    """Real data: the window's current area clipped to its full area, in place — (0, 11, 320, 189) inside
    (0, 0, 320, 200)."""
    result = aes.run_function(NAME, (DESKTOP_FULL, DESKTOP_CURR), aes.leaf_machine())
    assert rect_of(result.final, DESKTOP_CURR) == model(rect_of(BASE_IMAGE, DESKTOP_FULL), rect_of(BASE_IMAGE, DESKTOP_CURR))[0]
    assert result.answer() == 1


def test_the_mask_word_is_never_stored():
    """A hand-68000 routine returns by `rts`: the call's handler path runs, the return's does not."""
    result = intersect(*SHAPES["rect inside clip"], through_line_f=True)
    assert aes.AES_LINEF_MASK_WORD not in result.info["writes"]
    assert case.word_in(result.final, aes.AES_LINEF_MASK_WORD) == aes.SNAPSHOT_MASK_WORD


# ---- the registry: every shape priced. The dearest in cycles is `clip inside rect` (all four replacements); the
# worst RATIO is an empty x axis beside a non-empty y (the ROM leaves by its first `ble`, the C recomputes x's answer
# from its stores only once y is known non-empty) ----
for _shape in sorted(SHAPES):
    _clip, _rect = SHAPES[_shape]
    aes.register(_shape, NAME, (CLIP_AT, RECT_AT),
                 aes.leaf_machine(onto=merge_pokes(aes.grect_pokes(CLIP_AT, *_clip), aes.grect_pokes(RECT_AT, *_rect))))
aes.register("the desktop window", NAME, (DESKTOP_FULL, DESKTOP_CURR), aes.leaf_machine())
_clip, _rect = SHAPES["clip inside rect"]
aes.register("clip inside rect", NAME, (CLIP_AT, RECT_AT),
             aes.leaf_machine(onto=merge_pokes(aes.grect_pokes(CLIP_AT, *_clip), aes.grect_pokes(RECT_AT, *_rect))),
             through_line_f=True)
