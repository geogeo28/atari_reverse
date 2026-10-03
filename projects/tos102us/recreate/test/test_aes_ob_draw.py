"""AES ob_draw ($fea028) and ob_change ($fea38e) — just_draw's two callers (`src/aes/obdraw.c`) — over the SNAPSHOT's OWN
TREES (`test/aes_objdraw.py`), the whole image compared, the screen included.

    ob_draw(tree, obj, depth): last := obj ? tree[obj].ob_next : -1; parent := get_par(tree, obj)
      parent != -1: ob_offset(tree, parent, &x, &y)  else x, y := 0 (one `clr.l`)
      gsx_moff; everyobj(tree, obj, last, just_draw BY VALUE, x, y, depth); gsx_mon
    ob_change(tree, obj, new, redraw): ob_sst; state == new or spec == -1: nothing
      ob_state := new; !redraw: nothing more
      ob_offset(tree, obj, &t.x, &t.y); gsx_moff; th := max(th, 0)
      USERDEF: ob_user(tree, obj, &t, spec, state, new) (its answer unread), redraw := 0
      else not ICON and (state ^ new) & SELECTED: bb_fill(XOR, solid, t inset by th — x,y as ONE packed longword), redraw := 0
      redraw: just_draw(tree, obj, t.x, t.y);  gsx_mon

ob_draw's DOOR. ob_draw hands everyobj just_draw BY VALUE; on the host that value is the ROM address and the case's hook
serves it with the C core (`just_draw_door`, the rectangle lists' MKRECT_HOOK shape) — on target, `src/aes/obdraw.S`'s
Alcyon entry, which only Tier 3 runs (and which its (V) rule needs: the ROM's just_draw inside our build is refused).

THE MACHINE IS THE SNAPSHOT's OWN FONT (`aes_objdraw.SNAPSHOT_FONT`): a tree's first label finds the small font the desk
last drew in, and sets the IBM font itself. That first label READS the parameter block's PTSIN before any call points
it, and a later box's wrapper stores it back — under the attribution pass the VDI is then handed $ff673b, so those draws
run UNPOISONED (`aes_objdraw.PTSIN_READ_FIRST`, measured per tree). The pass still sees every tree REDRAWN — the machine
the ROM's own first draw leaves, the IBM font cached in the AES and the VDI alike (`redrawn`) — but the menu bar, whose
redraw still makes a label its first VDI call (LABEL_FIRST_WHEN_REDRAWN), and the trees whose first draw makes no label
first (the windows, the desk's icons).

A full draw runs long: the selector's is 256,140 ROM instructions, past the oracle's default cap (OB_DRAW_INSNS).
"""
import functools

import pytest

from harness import BASE_IMAGE, addrs, emu, make_image

import aes
import aes_gsx as gsx
import aes_objdraw as od
import aes_obuser as obuser
import case
import vdi
from case import merge_pokes
from opcodes import DROP_STACK_LONG
from test_aes_gsx import screen_changed

OB_DRAW, OB_CHANGE = "AES_ROM_OB_DRAW", "AES_ROM_OB_CHANGE"
aes.declare_alcyon(OB_DRAW, None, (vdi.IMAGE_ARG, vdi.LONG_ARG, vdi.WORD_ARG, vdi.WORD_ARG))
aes.declare_alcyon(OB_CHANGE, None, (vdi.IMAGE_ARG, vdi.LONG_ARG, vdi.WORD_ARG, vdi.WORD_ARG, vdi.WORD_ARG))

TREES = od.trees()
SELECTED = od.STATE_BITS["SELECTED"]
CHECKED = od.STATE_BITS["CHECKED"]
DISABLED = od.STATE_BITS["DISABLED"]
# The depth GEM's callers hand objc_draw (MAX_DEPTH), which the AES's own dialogs pass too.
MAX_DEPTH = 8
REDRAW, NO_REDRAW = 1, 0

# THE INSTRUCTION BUDGET: MEASURED, the longest ROM run of this battery is the selector's whole draw at 256,140
# instructions (`test_the_budget_covers_the_longest_draw` re-measures it), past the oracle's default 200,000 — the budget
# is twice that.
OB_DRAW_MEASURED_INSNS = 256_140
OB_DRAW_INSNS = 2 * OB_DRAW_MEASURED_INSNS


# ---- the door: just_draw handed by value -------------------------------------------------------------------------------
def doors(userdef=None):
    """The VDI's door and just_draw's (`aes.walkers`), opened together — and, for a tree carrying a USERDEF staged by
    `aes_objdraw.userdef_pokes`, its routine answering `userdef` (one register-carrying hook serves both)."""
    routines_ = aes.walkers(od.JUST_DRAW)
    if userdef is not None:
        routines_[obuser.USERDEF_AT] = obuser.userdef_routine(userdef)
    return aes.doors(gsx.vdi_hook, aes.alcyon_object_hook(routines_))


# ---- the machines --------------------------------------------------------------------------------------------------------
machine = od.snapshot_font_machine      # the door's machine with the snapshot's own font cached, `onto` over it


@functools.cache
def redrawn(tree):
    """The machine the ROM's own ob_draw of `tree` leaves — every font, attribute and clip as its first draw set them,
    contrl[0..3] stale again: the state a second draw of the same tree (a window's redraw) starts from."""
    staged, final, writes = od.rom_run(OB_DRAW, (tree, aes.OB_ROOT, MAX_DEPTH), machine(), max_insns=OB_DRAW_INSNS)
    return merge_pokes(case.continued_from(staged, final, writes), gsx.CONTRL_STALE)


def clipped(rect, onto):
    """`onto` with the clip set to `rect` (x, y, w, h) by the ROM's own gsx_sclip (the AES's four words and the
    VDI's), continued from — the clip a window's redraw hands objc_draw. The GRECT sits in the door's GRECT band."""
    pokes = merge_pokes(onto, {aes.RECTS_AT: vdi.pack_words(*rect)})
    return merge_pokes(od.clip_set_by_the_rom(aes.RECTS_AT, pokes), gsx.CONTRL_STALE)


# ---- the runs -----------------------------------------------------------------------------------------------------------
# THE C's FRAMES STAGED STALE. The ROM's locals are stored before they are read — the root's position by one `clr.l`, the
# rest by ob_sst and ob_offset — so a C that skipped one of those stores reads STALE where the ROM read its own.
STALE_SLOTS = merge_pokes(aes.stale_host_slot("AES_OB_DRAW_POSITION"), aes.stale_host_slot("AES_OB_CHANGE_FRAME"))


def ob_draw(tree, index=aes.OB_ROOT, depth=MAX_DEPTH, pokes=None, *, onto=None, userdef=None, **kwargs):
    staged = merge_pokes(machine() if onto is None else onto, STALE_SLOTS, pokes)
    return aes.run_function(OB_DRAW, (tree, index, depth), staged, hook=doors(userdef), max_insns=OB_DRAW_INSNS,
                            **kwargs)


def ob_change(tree, index, new_state, redraw=REDRAW, pokes=None, *, onto=None, userdef=None, **kwargs):
    staged = merge_pokes(machine() if onto is None else onto, STALE_SLOTS, pokes)
    return aes.run_function(OB_CHANGE, (tree, index, new_state, redraw), staged, hook=doors(userdef), **kwargs)


# ---- ob_draw: every tree the snapshot holds, whole --------------------------------------------------------------------
# (tree, poisoned): a first draw is poisoned only where its first VDI call is no label (measured: every other tree's first
# draw hands the VDI $ff673b under the pass). The desk's tree 0 IS the menu bar (gl_mntree), drawn once.
WHOLE_TREES = {
    "the file selector": ("selector", False),
    "the alert, unbuilt": ("alert", False),
    "the menu bar": ("menu", False),
    "the desk's icons": ("desk icons", True),
    "the window tree": ("windows", True),
    **{f"the desk's dialog {index}": (f"desk tree {index}", False) for index in range(1, 14)},
}


@pytest.mark.parametrize("name, poisoned", WHOLE_TREES.values(), ids=WHOLE_TREES)
def test_a_whole_tree(name, poisoned):
    result = ob_draw(TREES[name], **({} if poisoned else od.PTSIN_READ_FIRST))
    assert result.field("AES", "GL_MOFF") == gsx.NEST_HIDDEN
    if name != "desk icons":                    # the desk's icons are already on the screen, drawn over themselves
        assert screen_changed(result)


# ...and the one tree whose REDRAW still makes a label its first VDI call (measured): the menu bar, its first title.
LABEL_FIRST_WHEN_REDRAWN = {"menu"}


@pytest.mark.parametrize("name", [name for name, _poisoned in WHOLE_TREES.values()], ids=list(WHOLE_TREES))
def test_a_whole_tree_redrawn(name):
    """...and drawn again over what the first draw left (the IBM font cached in the AES and the VDI): POISONED."""
    tree = TREES[name]
    ob_draw(tree, onto=redrawn(tree), **(od.PTSIN_READ_FIRST if name in LABEL_FIRST_WHEN_REDRAWN else {}))


BAND = TREES["desktop band"]


def band_screens(start, depth, onto):
    """The desktop band drawn from `start` to `depth` over `onto` with each of two commands as sh_draw leaves them."""
    return od.band_screens(lambda pokes, **kwargs: ob_draw(BAND, start, depth, pokes=pokes, onto=onto, **kwargs))


@pytest.mark.parametrize("start, depth", ((aes.OB_ROOT, 1), (od.BAND_TEXT, 0)),
                         ids=("the launch path: the root, depth 1", "the one-object pass: the TEXT"))
def test_the_desktop_band_as_sh_draw_draws_it(start, depth):
    """The AES's tree 2 (no LASTOB) as sh_draw ($feada0) draws it: its TEXT's te_ptext the shell's buffer, the clip the
    whole screen — from the root to depth 1 (the launch path, $feb1a8..) and the TEXT alone ($feaddc): two commands,
    two screens."""
    screens = band_screens(start, depth, od.sh_draw_machine())
    assert screens[0] != screens[1]


def test_the_desktop_band_s_text_lies_above_the_desktop_s_clip():
    """...which is why the clip is sh_draw's: under the snapshot's own (the desktop, below the bar) the TEXT, in the
    bar's row, is cut whole — its string never read, two commands one screen."""
    screens = band_screens(aes.OB_ROOT, MAX_DEPTH, machine())
    assert screens[0] == screens[1]


def test_the_root_s_own_next_is_never_read():
    """From the root the walk ends nowhere (-1), whatever its ob_next holds — an application's tree pointer into
    another's objects can carry one: here the desk's dialog 12 with its root's ob_next staged 3, drawn whole."""
    tree = TREES["desk tree 12"]
    result = ob_draw(tree, pokes=aes.object_pokes(tree, aes.OB_ROOT, NEXT=3), **od.PTSIN_READ_FIRST)
    assert screen_changed(result)


def test_the_budget_covers_the_longest_draw():
    """OB_DRAW_MEASURED_INSNS is the selector's draw, as the ROM runs it now."""
    pokes = aes.staged(OB_DRAW, (TREES["selector"], aes.OB_ROOT, MAX_DEPTH), machine())
    _final, _writes, regs = emu.run(make_image(pokes), addrs.AES_ROM_OB_DRAW, max_insns=OB_DRAW_INSNS)
    assert regs["ninsns"] == OB_DRAW_MEASURED_INSNS


# ---- ob_draw: a subtree, the depth, the clip ---------------------------------------------------------------------------
# The selector is three levels deep: its scroll bar (7) holds the slider's track (10), which holds the slider (11).
SELECTOR = TREES["selector"]
SCROLL_BAR, TRACK, SLIDER, FILE_LIST = 7, 10, 11, 6


@pytest.mark.parametrize("index", (SCROLL_BAR, TRACK, SLIDER, FILE_LIST),
                         ids=("the scroll bar: its parent the root, a sibling after it",
                              "the track: two levels down, its next its parent",
                              "the slider: three levels down, alone",
                              "the file list: nine children"))
def test_a_subtree_starts_at_its_parent_s_offset(index):
    """fs_ redraws one part of the selector (`ob_draw(tree, part, MAX_DEPTH)`): the walk starts where ob_offset puts
    the part's parent and ends at the part's ob_next."""
    assert screen_changed(ob_draw(SELECTOR, index, **od.PTSIN_READ_FIRST))


@pytest.mark.parametrize("depth", (0, 1, 2, 3), ids=lambda depth: f"depth {depth}")
def test_the_depth_bounds_the_walk(depth):
    """The selector from its root, `depth` levels below it at most: 0 the root alone, 3 the slider too."""
    assert screen_changed(ob_draw(SELECTOR, depth=depth, **od.PTSIN_READ_FIRST))


@pytest.mark.parametrize("rect", ((40, 60, 100, 50), (0, 100, 320, 4), (300, 11, 20, 189)),
                         ids=("a window's corner over the list", "a strip across every column", "the right edge alone"))
def test_a_clip_cutting_the_tree(rect):
    """A clip that cuts the dialog: objects outside it skipped by just_draw's test, the rest drawn cut by the VDI."""
    assert screen_changed(ob_draw(SELECTOR, onto=clipped(rect, machine()), **od.PTSIN_READ_FIRST))


def test_a_clip_missing_the_tree_draws_nothing():
    """A clip above the dialog: every object's test fails, and only the cursor's nest moves."""
    result = ob_draw(SELECTOR, onto=clipped((0, 11, 320, 8), machine()))
    assert od.drawn_nothing(result)


def test_a_userdef_in_a_drawn_tree():
    """A tree holding an application's USERDEF (a real button made one): everyobj reaches just_draw, just_draw the
    routine through ob_user, the routine's answer the state drawn."""
    tree, index = TREES["desk tree 1"], 10
    result = ob_draw(tree, pokes=od.userdef_pokes(tree, index, SELECTED), userdef=SELECTED, **od.PTSIN_READ_FIRST)
    logged = obuser.logged_parmblk(result.final)
    assert logged["tree"] == tree and logged["object"] == index


# ---- ob_draw: the doors -------------------------------------------------------------------------------------------------
@gsx.THROUGH
def test_ob_draw_through_its_call_word(through_line_f):
    """objc_draw's arm and the AES's own callers call ob_draw by `$f200`."""
    tree = TREES["windows"]
    ob_draw(tree, through_line_f=through_line_f)


def test_ob_draw_over_the_shown_cursor():
    """The snapshot's own cursor shown: ob_draw's gsx_moff hides it (v_hide_c), its gsx_mon shows it back."""
    result = ob_draw(TREES["windows"], onto=gsx.shown_machine(od.SNAPSHOT_FONT))
    assert result.field("AES", "GL_MOFF") == gsx.NEST_SHOWN


def test_ob_draw_puts_the_tree_on_the_bus():
    ob_draw(TREES["windows"] | aes.BUS_TAG)


# ---- ob_change ------------------------------------------------------------------------------------------------------------
BUTTON = od.EXIT_BUTTON
TITLE = (TREES["menu"], 3)                                  # the desk menu's first title, border 1
ICON = od.TRASH
ROOT = (SELECTOR, aes.OB_ROOT)                              # an outlined dialog root, border 2
MENU_ITEM = od.MENU_ITEM
# The menu bar's titles are changed under the whole screen's clip, as mn_do draws the bar — the clip sh_draw draws the
# desktop's band under too, over the same font: one machine, named for the caller here.
MENU_BAR_MACHINE = od.sh_draw_machine()


def state_of(tree, index):
    return od.object_word(BASE_IMAGE, tree, index, "STATE") & 0xFFFF


@pytest.mark.parametrize("tree, index, new_state, onto", (
    (*BUTTON, SELECTED, None),
    (*TITLE, SELECTED, MENU_BAR_MACHINE),
    (*ROOT, SELECTED | od.STATE_BITS["OUTLINED"], None),
), ids=("fm_do's button pressed: the whole box inverted (border -3 counts 0)",
        "mn_do's title dropped: inverted inside its border of 1",
        "a dialog root selected: inside its border of 2"))
def test_selected_moved_inverts_in_place(tree, index, new_state, onto):
    result = ob_change(tree, index, new_state, onto=onto)
    assert od.object_word(result.final, tree, index, "STATE") & 0xFFFF == new_state and screen_changed(result)


def test_selected_moved_back():
    """...and the button released: SELECTED cleared, the box inverted back."""
    tree, index = BUTTON
    ob_change(tree, index, 0, pokes=od.state_pokes(tree, index, SELECTED))


def test_an_icon_is_redrawn_whole():
    """The desk's icon picked: no inversion — just_draw draws it SELECTED (its colours swapped)."""
    tree, index = ICON
    assert screen_changed(ob_change(tree, index, SELECTED, onto=machine()))


@pytest.mark.parametrize("tree, index, start, new_state", (
    (*MENU_ITEM, None, 0),
    (*BUTTON, None, DISABLED),
    (*BUTTON, SELECTED, SELECTED | 0x100),
), ids=("a menu item unchecked", "a button disabled", "a state's HIGH byte changed (a word compare)"))
def test_another_change_is_redrawn_whole(tree, index, start, new_state):
    """Any change but SELECTED's: the object redrawn by just_draw over its new state — stored BEFORE the draw reads it.
    `start` is the state staged first (None: the tree's own)."""
    pokes = None if start is None else od.state_pokes(tree, index, start)
    ob_change(tree, index, new_state, pokes=pokes, **od.PTSIN_READ_FIRST)


def test_selected_and_another_bit_moved_only_inverts():
    """SELECTED and DISABLED set at once: SELECTED's inversion alone is drawn — the DISABLED dither is not."""
    tree, index = BUTTON
    result = ob_change(tree, index, SELECTED | DISABLED)
    assert od.object_word(result.final, tree, index, "STATE") & 0xFFFF == SELECTED | DISABLED


@pytest.mark.parametrize("answer", (0, SELECTED), ids=("answering 0", "answering SELECTED"))
def test_a_userdef_is_handed_to_its_routine(answer):
    """An application's USERDEF: its routine called over a PARMBLK (the old state, the new) and its answer UNREAD —
    nothing inverted, nothing redrawn."""
    tree, index = BUTTON
    result = ob_change(tree, index, SELECTED, pokes=od.userdef_pokes(tree, index, answer), userdef=answer)
    logged = obuser.logged_parmblk(result.final)
    assert (logged["prevstate"], logged["currstate"]) == (0, SELECTED)


def test_the_unchanged_state_does_nothing():
    """A state already `new`: not stored, the cursor untouched."""
    tree, index = MENU_ITEM
    result = ob_change(tree, index, state_of(tree, index))
    assert od.drawn_nothing(result) and aes.AES_GL_MOFF not in result.info["writes"]


def test_no_spec_does_nothing():
    """An object whose ob_spec is -1: nothing stored."""
    tree, index = BUTTON
    result = ob_change(tree, index, SELECTED, pokes=od.spec_pokes(tree, index, -1))
    assert od.object_word(result.final, tree, index, "STATE") == 0 and od.drawn_nothing(result)


def test_no_redraw_only_stores():
    """menu_icheck's call (`redraw` 0): the state stored, nothing drawn and the cursor untouched."""
    tree, index = MENU_ITEM
    result = ob_change(tree, index, 0, NO_REDRAW)
    assert state_of(tree, index) and not od.object_word(result.final, tree, index, "STATE")
    assert od.drawn_nothing(result)


REDRAW_HIGH_BYTE_ONLY = 0x0100


def test_a_redraw_word_with_its_high_byte_alone_set_is_a_redraw():
    """`tst.w 16(a6)`: a redraw of $0100 is non-zero, the object redrawn — the WORD tested, not its low byte."""
    tree, index = BUTTON
    assert screen_changed(ob_change(tree, index, SELECTED, REDRAW_HIGH_BYTE_ONLY))


def test_the_inverted_corner_carries_into_x():
    """The corner moved in by the border as ONE longword: a root at y -2 with a border of 2 reaches y 0 by a carry out
    of the low word, which moves x a pixel right (`swap` / `add.l`)."""
    tree, index = ROOT
    result = ob_change(tree, index, SELECTED | od.STATE_BITS["OUTLINED"], pokes=aes.object_pokes(tree, index, Y=0xFFFE))
    assert screen_changed(result)


# ---- ob_change: the doors ----------------------------------------------------------------------------------------------------
# ob_change's two call words: the AES's callers' ($f214) and gr_watchbox's ($f098).
CHANGE_CALL_WORDS = sorted(aes.line_f_call_sites(OB_CHANGE))


@pytest.mark.parametrize("word", CHANGE_CALL_WORDS, ids=lambda word: f"${word:04x}")
def test_ob_change_through_each_call_word(word, monkeypatch):
    monkeypatch.setattr(aes, "line_f_call_word", lambda _name: word)
    tree, index = BUTTON
    result = ob_change(tree, index, SELECTED, through_line_f=True)
    assert result.word(aes.LINE_F_CALLER_AT + len(DROP_STACK_LONG)) == word and screen_changed(result)


def test_ob_change_over_the_shown_cursor():
    tree, index = BUTTON
    result = ob_change(tree, index, SELECTED, onto=gsx.shown_machine(od.SNAPSHOT_FONT))
    assert result.field("AES", "GL_MOFF") == gsx.NEST_SHOWN and screen_changed(result)


def test_ob_change_puts_the_tree_on_the_bus():
    tree, index = BUTTON
    ob_change(tree | aes.BUS_TAG, index, SELECTED)


# ---- the registry --------------------------------------------------------------------------------------------------------
# Every ROM run a row makes stays under the oracle's default cap, which the bench and the snapshot sweeps run at: the
# selector's whole draw (256,140) cannot be a row, and is priced in the report instead.
def register_draw(label, tree, index=aes.OB_ROOT, depth=MAX_DEPTH, pokes=None, *, onto=None, through_line_f=False):
    staged = merge_pokes(machine() if onto is None else onto, pokes)
    aes.register(label, OB_DRAW, (tree, index, depth), staged, through_line_f=through_line_f, hook=doors())


def register_change(label, tree, index, new_state, redraw=REDRAW, pokes=None, *, onto=None, userdef=None,
                    through_line_f=False):
    staged = merge_pokes(machine() if onto is None else onto, pokes)
    aes.register(label, OB_CHANGE, (tree, index, new_state, redraw), staged, through_line_f=through_line_f,
                 hook=doors(userdef))


register_draw("the menu bar", TREES["menu"])
register_draw("a desk dialog", TREES["desk tree 1"])
register_draw("a desk dialog redrawn", TREES["desk tree 1"], onto=redrawn(TREES["desk tree 1"]))
register_draw("the desk's icons", TREES["desk icons"])
register_draw("the window tree", TREES["windows"])
register_draw("the alert, unbuilt", TREES["alert"])
register_draw("the selector's scroll bar", SELECTOR, SCROLL_BAR)
register_draw("the selector's root alone", SELECTOR, depth=0)
register_draw("the selector cut by a window's corner", SELECTOR, onto=clipped((40, 60, 100, 50), machine()))
register_draw("the window tree", TREES["windows"], through_line_f=True)
register_change("a button pressed", *BUTTON, SELECTED)
register_change("a title dropped", *TITLE, SELECTED, onto=MENU_BAR_MACHINE)
register_change("an icon picked", *ICON, SELECTED)
register_change("a menu item unchecked", *MENU_ITEM, 0)
register_change("a button disabled", *BUTTON, DISABLED)
register_change("the state unchanged", *MENU_ITEM, state_of(*MENU_ITEM))
register_change("no redraw", *MENU_ITEM, 0, NO_REDRAW)
register_change("a USERDEF answering SELECTED", *BUTTON, SELECTED, pokes=od.userdef_pokes(*BUTTON, SELECTED),
                userdef=SELECTED)
register_change("a button pressed", *BUTTON, SELECTED, through_line_f=True)
