"""AES just_draw ($fe9a88) — one object of a tree drawn — over the SNAPSHOT's OWN TREES (`test/aes_objdraw.py`): the type
x state cells real data reaches, each drawn where ob_offset puts it, the whole image compared, the screen included.
The cells no tree carries are staged on real objects in `test_aes_just_draw_staged.py`.

    ob_sst; HIDETREE or spec -1: nothing.  t.x, t.y := x, y
    clip on (gl_wclip and gl_hclip): t grown by 3 (OUTLINED) or 3|border| must touch it, else nothing
    STRING: straight to its label.  Else: tmode, tcol := 1; a text's TEDINFO copied (AES_EDBLK), its colour cracked;
      $fefba0: BOX/IBOX/BOXCHAR crack the spec's colour -> BUTTON (re-tested: black border, white hollow) -> the
      box: a border gr_box when it has one, and but for IBOX the fill (gr_rect inside the border's inward part);
      gsx_attr(text, tmode, tcol);
      $fefbcc: FTEXT/FBOXTEXT ob_format -> BOXCHAR its character -> TEXT/BOXTEXT gr_gtext; IMAGE gsx_blt; ICON
      gr_gicon (SELECTED then cleared); USERDEF ob_user (its answer the state)
    STRING/TITLE/BUTTON: the label (xstrpix into intin), centred down — and across, a BUTTON's — in the IBM font
    any state: OUTLINED, the border's inward part (or its magnitude), SHADOWED, CHECKED, CROSSED, DISABLED, SELECTED

The REAL cells (`aes_objdraw.census`): BOX with borders 2/1/0/-1 and OUTLINED dialog roots; IBOX; BOXCHAR (borders 1,
-1); BUTTON (borders -1/-2/-3); BOXTEXT; FBOXTEXT left and right; IMAGE; ICON; STRING plain, DISABLED (the menu's
separators and greyed items) and CHECKED; TITLE. SELECTED is never in a tree at rest but every AES flow sets it with
ob_change — a button pressed, a title dropped, an icon picked — so a case sets it as ob_change does ($fea3ee): real.
"""
import pytest

from harness import BASE_IMAGE, make_image

import aes
import aes_gsx as gsx
import aes_objdraw as od
import case
import test_aes_gemgraf as gemgraf
import vdi
from aes_objdraw import real
from case import merge_pokes
from test_aes_gsx import screen_changed

TREES = od.trees()
SELECTED = od.STATE_BITS["SELECTED"]


# ---- the real cells, each object drawn where ob_offset puts it -----------------------------------------------------
# (tree, object): the census's cells, one object each — and a few twice, where a second one reaches another arm.
REAL = {
    "an outlined dialog root: a box, border 2": real("selector", 0),
    "an outlined dialog root, the desk's": real("desk tree 1", 0),
    "a box, border 1": real("selector", 6),
    "a box, border 1, a pattern": real("selector", 10),
    "a box, border -1: a menu's drop-down": od.DROP_DOWN,
    "a box, no border": real("desktop band", 0),
    "a BOXCHAR, border -1": real("selector", 4),
    "a BOXCHAR, border 1": real("selector", 8),
    "a default exit BUTTON: border -3": od.EXIT_BUTTON,
    "an exit BUTTON: border -2": real("selector", 22),
    "a radio BUTTON: border -1": real("desk tree 1", 8),
    "a BOXTEXT, centred, border -1": real("selector", 5),
    "an FBOXTEXT, left: an empty raw text": real("selector", 2),
    "an FBOXTEXT, right": real("desk tree 1", 3),
    "an IMAGE: the desk's About logo": real("desk tree 4", 1),
    "a STRING": real("selector", 1),
    "a STRING wider than its box": real("desk tree 4", 10),
    "a CHECKED STRING: a menu item": od.MENU_ITEM,
}


@pytest.mark.parametrize("tree, index", REAL.values(), ids=REAL)
def test_a_real_object(tree, index):
    assert screen_changed(od.draw(tree, index))


# ...and the ones that draw nothing the screen shows: an IBOX with no border (no fill either), a box with no size (the
# desk's spare slots), a label of one space (transparent).
INVISIBLE = {
    "an IBOX: nothing but its state": real("menu", 2),
    "a box with no size": real("desk icons", 2),
    "a STRING of one space": real("desk tree 4", 5),
}


@pytest.mark.parametrize("tree, index", INVISIBLE.values(), ids=INVISIBLE)
def test_a_real_object_that_shows_nothing(tree, index):
    assert not screen_changed(od.draw(tree, index))


# The DISABLED menu items — greyed commands and the separators — draw their label, then dim it: the label reads PTSIN
# before the DISABLED fill points it back (`aes_objdraw.PTSIN_READ_FIRST`).
@pytest.mark.parametrize("index", (18, 20), ids=("a greyed item", "a separator"))
def test_a_disabled_menu_item(index):
    tree = TREES["menu"]
    result = od.draw(tree, index, **od.PTSIN_READ_FIRST)
    assert screen_changed(result)


@pytest.mark.parametrize("index", (6, 7, 8), ids=("the trash", "drive A", "drive B"))
def test_a_desk_icon(index):
    """The desk's three icons, in the small font their labels are drawn in (the snapshot's own cache)."""
    tree = TREES["desk icons"]
    result = od.draw(tree, index, at=od.ICON_PLACE, onto=od.snapshot_font_machine())
    assert screen_changed(result)
    # the ICONBLK's copy, its two GRECTs moved to the screen by the object's corner
    x, y = od.ICON_PLACE
    spec = od.object_long(tree, index, "SPEC")
    staged = [aes.signed(word) for word in result.words(spec + aes.IB_XICON, 2)]
    assert [aes.signed(word) for word in result.words(aes.AES_IB + aes.IB_XICON, 2)] == [staged[0] + x, staged[1] + y]


def test_a_menu_title_redrawn_in_its_place_is_the_snapshot_s_own():
    """A TITLE, as mn_bar draws it: in the menu bar, the clip the whole screen, the IBM font cached as the ROM caches
    it. Redrawn where it stands, it writes the screen and leaves exactly the pixels the snapshot shows — the bar's own
    label, in its own font (one drawn in the small font differs)."""
    tree, index = real("menu", 3)
    result = od.draw(tree, index, onto=od.screen_clip_machine())
    assert od.redrawn_as_it_stands(result), vdi.screen_diff(make_image(result.staged), result.final)


def test_a_menu_title_drawn_elsewhere_under_the_whole_screen_s_clip():
    """...and moved down onto the desktop's pattern, the same title shows."""
    tree, index = real("menu", 3)
    assert screen_changed(od.draw(tree, index, at=(od.screen_origin(BASE_IMAGE, tree, index)[0], od.ICON_PLACE[1]),
                                  onto=od.screen_clip_machine()))


# ---- the font the default machine caches -------------------------------------------------------------------------------
def pixels_drawn(staged, final):
    """`{address: byte}` of every screen byte a run changed."""
    base = vdi.SCREEN.base
    return {at: final[at] for at in range(base, base + vdi.SCREEN.bytes) if final[at] != staged[at]}


def rom_text(at, onto):
    """The ROM's own gsx_tblt of IBM text ("GEM" in intin) at `at` over `onto`: (staged, final, writes)."""
    return od.rom_run(od.TBLT, (od.FONT_IBM, *at, len(GEM)), merge_pokes(onto, gemgraf.TEXT_IN_INTIN))


GEM = b"GEM"
assert gemgraf.TEXT_IN_INTIN == {gemgraf.INTIN: vdi.pack_words(*GEM)}


def test_the_ibm_font_cached_is_the_vdi_s_face():
    """`aes_objdraw.IBM_FONT_CACHED` is a state the ROM reaches: IBM text drawn over it is drawn as it is after the ROM's
    own first IBM text (vst_height(IBM) made, gl_font 3) — gl_font 3 staged alone, over the VDI's small font, draws it
    in the small font (gl_font's only writers keep it true to the VDI's face: $fdaace, $fdad4a)."""
    staged, final, writes = rom_text((40, 60), od.snapshot_font_machine())
    after_the_first = merge_pokes(case.continued_from(staged, final, writes), gsx.CONTRL_STALE)
    second = rom_text((40, 120), after_the_first)
    over_the_default = rom_text((40, 120), od.machine())
    assert pixels_drawn(make_image(second[0]), second[1]) == \
        pixels_drawn(make_image(over_the_default[0]), over_the_default[1])


# ---- SELECTED, as ob_change sets it ----------------------------------------------------------------------------------
@pytest.mark.parametrize("tree, index, font", (
    (*od.EXIT_BUTTON, od.IBM_FONT_CACHED),
    (*real("menu", 3), od.IBM_FONT_CACHED),
    (*od.TRASH, od.SNAPSHOT_FONT),
    (*real("selector", 2), od.IBM_FONT_CACHED),
    (*real("selector", 5), od.IBM_FONT_CACHED),
), ids=("a pressed button", "a dropped title", "a picked icon: its colours swapped, SELECTED cleared", "a picked field",
        "a picked BOXTEXT: its border outward, the text's GRECT left unshrunk"))
def test_a_selected_object(tree, index, font):
    pokes = od.state_pokes(tree, index, SELECTED)
    onto = od.screen_clip_machine() if tree == TREES["menu"] else od.machine(font=font)
    at = od.ICON_PLACE if tree == TREES["desk icons"] else None
    unpoisoned = od.PTSIN_READ_FIRST if tree == TREES["menu"] else {}      # the title's label is drawn first
    result = od.draw(tree, index, pokes, at=at, onto=onto, **unpoisoned)
    assert screen_changed(result)


# ---- the early returns ----------------------------------------------------------------------------------------------
def test_an_object_outside_the_clip_draws_nothing():
    """The alert's icon as the resource holds it, before fm_alert places it: at (0, 0), no size — above the clip."""
    tree, index = real("alert", 1)
    result = od.draw(tree, index)
    assert not screen_changed(result)


def test_an_object_cut_by_the_clip_draws_its_part():
    """A drop-down box straddling the clip's top edge: drawn, the VDI cutting what lies above."""
    tree, index = od.DROP_DOWN
    assert screen_changed(od.draw(tree, index, at=(64, 5)))


# The clip test's growth, at its edge: the object placed so its GRECT ends `growth` pixels above the clip's top — the
# grown copy's bottom then lands ON the clip's first row, which still touches (gsx_chkclip's `blt`) — and one pixel
# higher, where it does not and nothing is drawn. (object, growth): a border of 1 (3 x 1), an outline (3, whatever the
# border: the root's is 2), and an outline staged on a box with no border (3, not 3 x 0).
CLIP_Y = case.word_in(BASE_IMAGE, aes.AES_GL_YCLIP)
CLIP_EDGE = {
    "a border of 1": (real("selector", 6), 3, None),
    "an outlined root, border 2": (real("desk tree 1", 0), 3, None),
    "an outlined box with no border": (real("menu", 1), 3, "OUTLINED"),
}


@pytest.mark.parametrize("short", (0, 1), ids=("reaching the clip", "a pixel short"))
@pytest.mark.parametrize("tree, index, growth, state", [(*o, g, s) for o, g, s in CLIP_EDGE.values()], ids=CLIP_EDGE)
def test_the_clip_test_grows_the_grect(tree, index, growth, state, short):
    height = od.object_word(BASE_IMAGE, tree, index, "HEIGHT")
    pokes = od.state_pokes(tree, index, od.STATE_BITS[state]) if state else None
    result = od.draw(tree, index, pokes, at=(16, CLIP_Y - growth - height - short))
    assert od.drawn_nothing(result) == bool(short)


def test_the_clip_off_skips_the_test():
    """Clipping off (gsx_sclip of an empty GRECT leaves gl_wclip 0): no test, the alert's unplaced icon drawn at
    (0, 0) — nothing to blit, but the call made."""
    tree, index = real("alert", 1)
    od.draw(tree, index, aes.field_pokes("AES", GL_WCLIP=0))
    od.draw(tree, index, aes.field_pokes("AES", GL_HCLIP=0))


# ---- the label ---------------------------------------------------------------------------------------------------------
def test_a_label_changes_the_font():
    """A STRING drawn over the snapshot's own cache (the small font): gsx_tblt sets the IBM font first."""
    tree, index = real("selector", 1)
    result = od.draw(tree, index, onto=od.snapshot_font_machine(), **od.PTSIN_READ_FIRST)
    assert result.field("AES", "GL_FONT") == od.FONT_IBM and screen_changed(result)


# ---- the doors: Line-F, the cursor shown, a tagged tree -----------------------------------------------------------------
@gsx.THROUGH
@pytest.mark.parametrize("tree, index", (real("selector", 0), od.EXIT_BUTTON), ids=("a dialog root", "a button"))
def test_through_ob_change_s_call_word(tree, index, through_line_f):
    assert screen_changed(od.draw(tree, index, through_line_f=through_line_f))


@pytest.mark.parametrize("tree, index, font", (
    (*real("selector", 0), od.IBM_FONT_CACHED),
    (*real("desk tree 4", 1), od.IBM_FONT_CACHED),
    (*real("desk icons", 7), od.SNAPSHOT_FONT),
), ids=("a dialog root's lines", "an image's blit", "an icon's blits"))
def test_over_the_snapshot_s_shown_cursor(tree, index, font):
    """The cursor shown (the snapshot's): every gr_box, gsx_blt and gsx_cline hides it round itself."""
    at = od.ICON_PLACE if tree == TREES["desk icons"] else None
    result = od.draw(tree, index, at=at, onto=gsx.shown_machine(font))
    assert result.field("AES", "GL_MOFF") == gsx.NEST_SHOWN and screen_changed(result)


def test_the_tree_s_pointer_is_put_on_the_bus():
    tree, index = od.EXIT_BUTTON
    assert screen_changed(od.draw(tree | aes.BUS_TAG, index, at=od.screen_origin(BASE_IMAGE, tree, index)))


# ---- the registry --------------------------------------------------------------------------------------------------------
_ROWS = {
    "an outlined dialog root": (real("selector", 0), None),
    "a default exit button": (od.EXIT_BUTTON, None),
    "a BOXCHAR": (real("selector", 4), None),
    "an FBOXTEXT path field": (real("selector", 2), None),
    "an FBOXTEXT, right": (real("desk tree 1", 3), None),
    "a BOXTEXT": (real("selector", 5), None),
    "an image": (real("desk tree 4", 1), None),
    "a string": (real("selector", 1), None),
    "a checked menu item": (od.MENU_ITEM, None),
    "an icon": (od.TRASH, od.snapshot_font_machine()),
    "a box outside the clip": (real("alert", 1), None),
    "a menu's drop-down": (od.DROP_DOWN, None),
}
for _label, ((_tree, _index), _onto) in _ROWS.items():
    od.register(_label, _tree, _index, onto=_onto)
od.register("a default exit button", *od.EXIT_BUTTON, through_line_f=True)
