"""AES gemmnlib, the MENU LIBRARY — `src/aes/mnlib.c` (`aes/mnlib.h`); its event-layer calls through the event door
(`test/aes_event.py`), every object drawn through `test_aes_ob_draw.py`'s doors (the VDI's cores, just_draw's).

    rect_change(t, mo, o, f)     ob_actxywh(t, o, &mo->rect); mo->leave = f
    do_chg(t, i, b, s, r, c)     st = t[i].state; c && st & DISABLED: 0;  s ? st |= b : st &= ~b;
                                 r ? gsx_sclip(&gl_rzero); ob_change(t, i, st, r); 1
    menu_set(t, l, c, s)         l == -1 || l == c: 0; else do_chg(t, l, SELECTED, s, 1, 1)
    menu_sr(s, t, m)             gsx_sclip(&gl_rzero); r = ob_actxywh(t, m); r.x--, r.w += 2, r.h += 2;
                                 s ? bb_save(&r) : bb_restore(&r)
    menu_down(t, ti)             m = t[t[0].tail].head, then ti - 3 ob_nexts; do_chg(t, ti, SELECTED, 1, 1, 1) ?
                                 menu_sr(1, t, m), ob_draw(t, m, 8); m
    mn_do(&ti, &it)              ct_mouse(1); until done: one ev_multi per pass (the bar, a dropped title, an item, off
                                 the menu), the titles/items/drop-downs changed to follow the mouse; ct_mouse(0)
    mn_bar(t, show)              show: gl_mntree, the screen manager's wait rect, the owner's pid (a longword), the
                                 desk menu rebuilt with the accessories, the bar drawn; or none; ++gl_mnclicks;
                                 post_button(ctl_pd, 1, 1)
    mn_clsda()                   ap_sendmsg(AC_CLOSE) to each registered accessory
    mn_register(pid, name)       -1: pd_nameit(rlr, copy of name), 1; else a slot (pid, name), its index, or -1 full
    pd_nameit(pd, name)          pd->name: 8 blanks, then name copied up to its '.'

THE MACHINES are the scheduler's own (`aes_event.machine`): PD0 RUNNING (woken by a key) for what an application calls
— menu_bar, menu_icheck / ienable / tnormal (do_chg), menu_register, appl_exit's mn_clsda — with the cursor hidden (an
application's graf_mouse(M_OFF)) or SHOWN (`aes_event.shown_machine`: what the dispatcher's menu_bar arm, which hides
nothing, runs over); and PD1, the SCREEN MANAGER, RUNNING for mn_do, which only it calls — woken by the mouse onto the
menu bar (on the "View" title), then, as the machine can, the mouse MOVED (`aes_event.mouse_moved_to`) or the button
PRESSED (`aes_event.pressed`) by interrupts while it runs. PD1's machines are PD1 as switchto leaves it, not as its control manager reaches mn_do: in
between, ctlmgr takes the screen lock (wm_update(1)), which nothing on mn_do's path reads. The accessories are
REGISTERED by the ROM's own mn_register runs (a pid of an existing process: no accessory is loaded in the snapshot,
and a message to a pid with no PD spins in the ROM's ap_rdwr). The menu is the desk's, gl_mntree; every tree object
read is the snapshot's, but for an item given a CHILD (`ITEM_WITH_A_CHILD`, out of the desk's own spare objects).

mn_do's WAITS. A pass's ev_multi is answered at once only by what the machine already holds: a mouse static and a
button static make every pass after the first ask for what pass 1 just saw change. Pass 1 is pinned whole, and a pass
nothing satisfies is REFUSED by the door (would block), the C held to the ROM's own run where it blocks (the whole
image, at dsptch). Every LATER pass is reached as the machine reaches it: by
INTERRUPTS while mn_do waits — the mouse moved, the button pressed or released by the ROM's own interrupt code at the
entry of a pass's ev_multi, on both shores (`aes_event.interrupted`) — the mouse onto a title while pass 1 waits on the
bar, an item chosen, a DISABLED item clicked, the menu left and entered again, title to title, the click on a title and
the drag to an item, the DISABLED-alone title's busy loop left.

EVERY PASS THAT BLOCKS IS TAKEN ON THROUGH ITS WAKE (`aes_event.blocked_then_woken`): the interrupt delivered WHILE
mn_do IS BLOCKED, at the dispatcher's idle — the screen manager parked by OUR dispatcher on our shore and woken
through it — the menu left and a click off it ending the call. One of them with THE DESK'S TURN inside mn_do's
wait (a key the desk waits for: the ROM's own desktop runs, a FOREIGN WINDOW the door call is open across); it and
the dearest are priced rows that SWITCH.

UNPINNED, with the reason: menu_bar's desk box height counted in gl_hchar, not gl_wchar (the mutant bar-height-wchar).
The two differ only on a machine whose character cell is not 8 x 8 — high resolution's 8 x 16 — and every machine here
is the snapshot's low-resolution one. A high-resolution workstation composed over it (the ROM's own gsx_wsopen(high) +
gsx_start laid onto the low-resolution boot) is a mixed machine no real ST produces: measured, mn_bar's run over it
writes 216 bytes BELOW the screen base ($f7ec8..$f7fd6, two 105-byte runs 160 apart: a low-resolution stride), over
the desktop's stack under _memtop that test_boot_snapshot's MASK holds noisy. A genuine resolution switch is not
derivable: Setscreen with a resolution change halts the model (console_reinit is not reconstructed).
"""
import functools

import pytest

from harness import BASE_IMAGE, addrs, make_image

import aes
import aes_event
import aes_gsx as gsx
import aes_objdraw as od
import case
import test_aes_ob_draw as obdraw
import vdi
from case import merge_pokes
from test_aes_gsx import screen_changed
from test_aes_wmlib import rom_derived

L, W, I = vdi.LONG_ARG, vdi.WORD_ARG, vdi.IMAGE_ARG
SIGNATURES = {
    "AES_ROM_RECT_CHANGE": (None, (I, L, L, W, W)),
    "AES_ROM_DO_CHG": (aes.WORD_ANSWER, (I, L, W, W, W, W, W)),
    "AES_ROM_MENU_SET": (aes.WORD_ANSWER, (I, L, W, W, W)),
    "AES_ROM_MENU_SR": (None, (I, W, L, W)),
    "AES_ROM_MENU_DOWN": (aes.WORD_ANSWER, (I, L, W)),
    "AES_ROM_MN_DO": (aes.WORD_ANSWER, (I, L, L)),
    "AES_ROM_MN_BAR": (None, (I, L, W)),
    "AES_ROM_MN_CLSDA": (None, (I,)),
    "AES_ROM_MN_REGISTER": (aes.WORD_ANSWER, (I, W, L)),
    "AES_ROM_PD_NAMEIT": (None, (I, L, L)),
}
for _name, (_restype, _argtypes) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, _argtypes)
(RECT_CHANGE, DO_CHG, MENU_SET, MENU_SR, MENU_DOWN, MN_DO, MN_BAR, MN_CLSDA, MN_REGISTER, PD_NAMEIT) = SIGNATURES

THROUGH = gsx.THROUGH
MENU = od.trees()["menu"]
NIL = aes.OB_NIL
SELECTED, CHECKED, DISABLED = (od.STATE_BITS[name] for name in ("SELECTED", "CHECKED", "DISABLED"))
# The desk's menu: four titles over four drop-downs (`test_the_desk_menu_is_what_the_cases_say`).
TITLES = {"Desk": 3, "File": 4, "View": 5, "Options": 6}
DROP_DOWNS = {"Desk": 8, "File": 17, "View": 28, "Options": 36}
CHECKED_ITEM, PLAIN_ITEM, DISABLED_ITEM = 29, 30, 18
ROOT_OF_THE_DROP_DOWNS = 7
THE_DESK_INFO = 9                       # the desk menu's own first item, the one mn_bar always adds back
JUST_DRAW = aes.walkers(od.JUST_DRAW)
# AN ITEM WITH A CHILD — a pattern sample in a drawing program's Fill menu, a key's label: ordinary resource data, and
# why menu_down draws a drop-down 8 deep. Staged out of the desk's own SPARE objects — File's two items past its
# drop-down's tail, which no sibling chain reaches (`test_the_desk_menu_is_what_the_cases_say`): the first made the only
# child of View's plain item, on the item's right half — a G_BOX filled with a pattern (its own text is a blank, which
# would draw nothing to see).
SPARE_ITEMS = (26, 27)
CHILD_X = 64                            # the plain item is 128 pixels wide: its right half
SAMPLE_SPEC = 0x00001171                # a G_BOX's spec: no border; colour word $1171 — fill pattern 7, colour 1
ITEM_WITH_A_CHILD = merge_pokes(aes.object_pokes(MENU, PLAIN_ITEM, HEAD=SPARE_ITEMS[0], TAIL=SPARE_ITEMS[0]),
                                aes.object_pokes(MENU, SPARE_ITEMS[0], NEXT=PLAIN_ITEM, TYPE=aes.G_BOX,
                                                 SPEC=SAMPLE_SPEC, X=CHILD_X, Y=0, WIDTH=CHILD_X))

# The band this battery stages in: two answer words, a MOBLK, and six accessories' names — in the window's free gap
# at +$3800 (test_aes_grdrag.py's band sits just past it, test_aes_wm_update.py's at +$3F00).
BAND_OFFSET = 0x3800
BAND_BYTES = 0x100
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES, "test/test_aes_mnlib.py: answers, a MOBLK, names")
TITLE_OUT, ITEM_OUT = BAND_AT, BAND_AT + aes.WORD_BYTES
MOBLK_OFFSET = 0x10                     # past the two answer words, a MOBLK
NAMES_OFFSET = 0x20                     # past the MOBLK, the accessories' names
NAME_STRIDE = 0x18                      # a name's room: "  Accessory n" and its NUL, rounded up
MOBLK_AT = BAND_AT + MOBLK_OFFSET
NAMES_AT = BAND_AT + NAMES_OFFSET
ACCESSORIES = tuple(f"  Accessory {slot}".encode() for slot in range(aes.MN_DA_SLOTS))
assert MOBLK_OFFSET + aes.EV_MOBLK_WORDS * aes.WORD_BYTES <= NAMES_OFFSET
assert NAMES_AT + aes.MN_DA_SLOTS * NAME_STRIDE <= BAND_AT + BAND_BYTES
STALE_BAND = {BAND_AT: vdi.pack_words(*[aes.STALE_WORD] * (NAMES_OFFSET // aes.WORD_BYTES))}

# The globals the cases read outside the window: the menu library's, and every process's name.
for _global in ("GL_CTWAIT_RECT", "GL_RMNACTV", "GL_MNPPD", "GL_DABOX", "GL_DAFIRST", "GL_DACNT", "DESK_PID", "DESK_ACC",
                "GL_MNCLICKS", "CTL_PD", "CT_MESSAGE"):
    _field = aes.field("AES", _global)
    aes.declare_case_field(_field.at, _field.width * (_field.count or 1), f"the menu library's {_global}")


def name_at(slot):
    return NAMES_AT + slot * NAME_STRIDE


def names_pokes(names=ACCESSORIES):
    return {name_at(slot): name + b"\0" for slot, name in enumerate(names)}


# ---- the machines -----------------------------------------------------------------------------------------------------
# What every machine carries over its running process: the snapshot's font cached, the band STALE, the names staged.
BAND_POKES = merge_pokes(od.SNAPSHOT_FONT, STALE_BAND, names_pokes())


@functools.cache
def running():
    """PD0 RUNNING, as the scheduler makes it (`aes_event.machine`), the cursor hidden."""
    return aes_event.machine(onto=BAND_POKES)


@functools.cache
def shown_running():
    """...the cursor SHOWN (`aes_event.shown_machine`): what the dispatcher's menu_bar arm, which hides nothing, runs
    over."""
    return aes_event.shown_machine(onto=BAND_POKES)


OFF_THE_BAR = (159, 99)                 # the snapshot's own mouse: on the desktop
RIGHT_OF_THE_TITLES = (280, 5)          # on the bar, past "Options": in THEBAR, out of THEACTIVE


@functools.cache
def _moved(x, y):
    return aes_event.mouse_moved_to(x, y, aes_event.screen_manager_running())


@functools.cache
def _pressed_over(woken):
    state = woken()
    return merge_pokes(state, aes_event.pressed(state))


@functools.cache
def screen_manager(at=None, pressed=False):
    """PD1 RUNNING — the screen manager, woken by the mouse on the "View" title — then the mouse MOVED to `at` and/or the
    left button PRESSED by interrupts while it runs."""
    woken = functools.partial(_moved, *at) if at else aes_event.screen_manager_running
    if pressed:
        woken = functools.partial(_pressed_over, woken)
    return aes_event.machine(woken, onto=BAND_POKES)


@functools.cache
def registered(*pids, onto=running):
    """`onto()` (PD0 running by default) with an accessory REGISTERED per pid of `pids` by the ROM's own mn_register,
    each named from the band (ACCESSORIES)."""
    state = onto()
    for slot, pid in enumerate(pids):
        state = rom_derived(addrs.AES_ROM_MN_REGISTER, aes_event.frame_of(("w", pid), ("l", name_at(slot))), state)
    return state


def children_of(parent):
    """`parent`'s children in the snapshot's menu, its sibling chain walked from its head back to it."""
    children, at = [], od.object_word(BASE_IMAGE, MENU, parent, "HEAD")
    while at != parent:
        children.append(at)
        at = od.object_word(BASE_IMAGE, MENU, at, "NEXT")
    return children


def test_the_desk_menu_is_what_the_cases_say():
    """The desk's menu as the snapshot holds it: the bar, the titles' box, four titles over four drop-downs under the
    root's last child — the desk menu's box its first, holding its own item alone (no accessory registered)."""
    assert [od.object_word(BASE_IMAGE, MENU, index, "HEAD") for index in (aes.MN_THEBAR, aes.MN_THEACTIVE)] == [2, 3]
    assert [od.object_word(BASE_IMAGE, MENU, index, "TYPE") & aes.OB_TYPE_MASK for index in TITLES.values()] == \
        [aes.G_TITLE] * len(TITLES)
    assert children_of(ROOT_OF_THE_DROP_DOWNS) == list(DROP_DOWNS.values())
    file_items = children_of(DROP_DOWNS["File"])
    assert SPARE_ITEMS[0] == file_items[-1] + 1 and not set(SPARE_ITEMS) & set(file_items)
    assert [od.object_word(BASE_IMAGE, MENU, spare, "NEXT") for spare in SPARE_ITEMS] == [NIL] * len(SPARE_ITEMS)
    assert od.object_word(BASE_IMAGE, MENU, PLAIN_ITEM, "HEAD") == NIL
    assert case.word_in(BASE_IMAGE, aes.AES_GL_DACNT) == 0
    assert od.object_word(BASE_IMAGE, MENU, DROP_DOWNS["Desk"], "HEAD") == THE_DESK_INFO


def test_the_screen_manager_s_machines_are_its_scheduler_s():
    """Every PD1 machine is a running process as switchto leaves one — a mouse moved or a button pressed by
    interrupts does not touch the scheduler's lists."""
    for at, pressed in ((None, False), (OFF_THE_BAR, False), (None, True), (OFF_THE_BAR, True)):
        image = make_image(screen_manager(at, pressed))
        assert aes_event.scheduler_state(image, aes.SCREEN_MANAGER_PD) == \
            aes_event.running_as_switchto_leaves_it(aes.SCREEN_MANAGER_PD)


# ---- rect_change ----------------------------------------------------------------------------------------------------------
STALE_MOBLK = {MOBLK_AT: vdi.pack_words(*[aes.STALE_WORD] * aes.EV_MOBLK_WORDS)}


def rect_change(tree, obj, leave, moblk=MOBLK_AT, pokes=None, **kwargs):
    return aes.run_function(RECT_CHANGE, (tree, moblk, obj, leave), merge_pokes(running(), STALE_MOBLK, pokes), **kwargs)


RECT_CHANGE_CASES = {
    "the titles' box, entered": (aes.MN_THEACTIVE, 0, (16, 0, 216, 11)),
    "the bar, left": (aes.MN_THEBAR, 1, (0, 0, 320, 10)),
    "a dropped title, left": (TITLES["View"], 1, (112, 0, 48, 11)),
    "an item, three levels down": (CHECKED_ITEM, 1, (112, 11, 128, 8)),
}


@pytest.mark.parametrize("obj, leave, rect", RECT_CHANGE_CASES.values(), ids=RECT_CHANGE_CASES)
def test_rect_change(obj, leave, rect):
    result = rect_change(MENU, obj, leave)
    assert [aes.signed(word) for word in result.words(MOBLK_AT, aes.EV_MOBLK_WORDS)] == [leave, *rect]


@THROUGH
def test_rect_change_through_its_callers_word(through_line_f):
    rect_change(MENU, aes.MN_THEACTIVE, 0, through_line_f=through_line_f)


def test_rect_change_puts_both_pointers_on_the_bus():
    result = rect_change(MENU | aes.BUS_TAG, aes.MN_THEBAR, 1, moblk=MOBLK_AT | aes.BUS_TAG)
    assert result.word(MOBLK_AT) == 1


def test_rect_change_stores_the_flag_after_the_rectangle():
    """THE ORDER: the MOBLK laid over the object's own x — its leave flag that word, its rectangle over the y, w and h
    ob_actxywh reads — so the flag is stored LAST, over the x ob_offset has already read."""
    moblk = MENU + PLAIN_ITEM * aes.OB_BYTES + aes.OB_X
    result = rect_change(MENU, PLAIN_ITEM, 1, moblk=moblk)
    assert result.word(moblk) == 1


# ---- do_chg, menu_set ------------------------------------------------------------------------------------------------------
def doors():
    return obdraw.doors()


def do_chg(item, bits, set_, redraw, check, tree=MENU, onto=None, **kwargs):
    return aes.run_function(DO_CHG, (tree, item, bits, set_, redraw, check), onto or running(), hook=doors(), **kwargs)


# A redraw of an item whose change is not SELECTED alone draws it WHOLE (ob_change), its label first: unpoisoned, as
# `aes_objdraw.PTSIN_READ_FIRST` says why (measured here too: the poisoned ROM run of the enabled item's redraw did not
# return within 200,000 instructions). Its stores are staged by the item's own state, which the C must store.
REDRAWN_WHOLE = {"menu_ienable: enabled, redrawn"}


def state_of(result, item, tree=MENU):
    return result.object(tree, item)["STATE"]


def snapshot_state(item):
    return od.object_word(BASE_IMAGE, MENU, item, "STATE") & 0xFFFF


# (item, bits, set, redraw, check disabled, answer): as the dispatcher's three arms hand them — menu_icheck (no redraw,
# no check), menu_ienable (a redraw by the item's top bit, no check), menu_tnormal (redraw, check) — and as menu_set
# does.
DO_CHG_CASES = {
    "menu_icheck: a check taken off": (CHECKED_ITEM, CHECKED, 0, 0, 0, 1),
    "menu_icheck: a check put on": (PLAIN_ITEM, CHECKED, 1, 0, 0, 1),
    "menu_ienable: enabled, redrawn": (DISABLED_ITEM, DISABLED, 0, 1, 0, 1),
    "menu_ienable: disabled, not redrawn": (PLAIN_ITEM, DISABLED, 1, 0, 0, 1),
    "menu_tnormal: a title selected": (TITLES["File"], SELECTED, 1, 1, 1, 1),
    "a DISABLED item checked for: left alone": (DISABLED_ITEM, SELECTED, 1, 1, 1, 0),
    "a DISABLED item not checked for: selected": (DISABLED_ITEM, SELECTED, 1, 0, 0, 1),
    "two bits at once, cleared": (CHECKED_ITEM, CHECKED | SELECTED, 0, 0, 1, 1),
    "the high byte too": (PLAIN_ITEM, 0x8000 | CHECKED, 1, 0, 0, 1),
}


@pytest.mark.parametrize("item, bits, set_, redraw, check, answer", DO_CHG_CASES.values(), ids=DO_CHG_CASES)
def test_do_chg(item, bits, set_, redraw, check, answer, request):
    unpoisoned = od.PTSIN_READ_FIRST if request.node.callspec.id in REDRAWN_WHOLE else {}
    result = do_chg(item, bits, set_, redraw, check, **unpoisoned)
    before = snapshot_state(item)
    expected = before if not answer else (before | bits if set_ else before & ~bits & 0xFFFF)
    assert (result.answer(), state_of(result, item)) == (answer, expected)


def test_do_chg_s_redraw_draws_under_no_clip():
    """A redraw sets the clip to gl_rzero first — no clip — and the title drawn selected changes the screen."""
    result = do_chg(TITLES["File"], SELECTED, 1, 1, 1)
    assert screen_changed(result)
    assert [result.field("AES", name) for name in ("GL_WCLIP", "GL_HCLIP")] == [0, 0]


@THROUGH
def test_do_chg_through_its_callers_word(through_line_f):
    do_chg(CHECKED_ITEM, CHECKED, 0, 0, 0, through_line_f=through_line_f)


def test_do_chg_puts_the_tree_on_the_bus():
    assert state_of(do_chg(PLAIN_ITEM, CHECKED, 1, 0, 0, tree=MENU | aes.BUS_TAG), PLAIN_ITEM) == CHECKED


def menu_set(last, current, set_, **kwargs):
    return aes.run_function(MENU_SET, (MENU, last, current, set_), running(), hook=doors(), **kwargs)


# (last, current, set, answer): nothing last, the same one, a title selected and deselected, a DISABLED item.
MENU_SET_CASES = {
    "nothing last": (NIL, TITLES["View"], 1, 0),
    "the same one": (TITLES["View"], TITLES["View"], 1, 0),
    "a title selected": (TITLES["View"], NIL, 1, 1),
    "an item deselected": (CHECKED_ITEM, PLAIN_ITEM, 0, 1),
    "a DISABLED item": (DISABLED_ITEM, NIL, 1, 0),
}


@pytest.mark.parametrize("last, current, set_, answer", MENU_SET_CASES.values(), ids=MENU_SET_CASES)
def test_menu_set(last, current, set_, answer):
    assert menu_set(last, current, set_).answer() == answer


@THROUGH
def test_menu_set_through_its_callers_word(through_line_f):
    menu_set(TITLES["View"], NIL, 1, through_line_f=through_line_f)


# ---- menu_sr, menu_down ------------------------------------------------------------------------------------------------------
STALE_SR_RECT = aes.stale_host_slot("AES_MENU_SR_RECT")


def menu_sr(save, menu, onto=None, tree=MENU, **kwargs):
    return aes.run_function(MENU_SR, (save, tree, menu), merge_pokes(onto or running(), STALE_SR_RECT), hook=doors(),
                            **kwargs)


@pytest.mark.parametrize("menu", DROP_DOWNS.values(), ids=DROP_DOWNS)
def test_menu_sr_saves_the_screen_under_a_drop_down(menu):
    result = menu_sr(1, menu)
    assert not screen_changed(result)


@functools.cache
def saved(menu):
    """`running()` continued from the ROM's own menu_sr saving the screen under drop-down `menu`, then the drop-down
    drawn by the ROM's ob_draw — what menu_down leaves, for a restore to take away."""
    state = rom_derived(addrs.AES_ROM_MENU_SR, aes_event.frame_of(("w", 1), ("l", MENU), ("w", menu)), running())
    return merge_pokes(rom_derived(addrs.AES_ROM_OB_DRAW, aes_event.frame_of(("l", MENU), ("w", menu),
                                                                              ("w", aes.MN_DRAW_DEPTH)), state),
                       gsx.CONTRL_STALE)


@pytest.mark.parametrize("menu", DROP_DOWNS.values(), ids=DROP_DOWNS)
def test_menu_sr_restores_the_screen_saved(menu):
    result = menu_sr(0, menu, onto=saved(menu))
    assert vdi.screen_of(result.final) == vdi.screen_of(make_image(running()))


@THROUGH
def test_menu_sr_through_its_callers_word(through_line_f):
    menu_sr(1, DROP_DOWNS["File"], through_line_f=through_line_f)


def test_menu_sr_puts_the_tree_on_the_bus():
    menu_sr(1, DROP_DOWNS["File"], tree=MENU | aes.BUS_TAG)


def menu_down(title, onto=None, tree=MENU, **kwargs):
    return aes.run_function(MENU_DOWN, (tree, title), merge_pokes(onto or running(), STALE_SR_RECT), hook=doors(),
                            **kwargs)


@pytest.mark.parametrize("title", TITLES, ids=TITLES)
def test_menu_down_drops_each_title_s_menu(title):
    """The walk from the first drop-down crosses `title - 3` siblings — none for the desk's, three for "Options"."""
    result = menu_down(TITLES[title])
    assert result.answer() == DROP_DOWNS[title]
    assert state_of(result, TITLES[title]) == SELECTED and screen_changed(result)


def test_menu_down_leaves_a_disabled_title_alone():
    """A title DISABLED (as menu_ienable leaves one): do_chg refuses it, so nothing is saved or drawn — its menu is
    still found and answered."""
    result = menu_down(TITLES["File"], onto=merge_pokes(running(), od.state_pokes(MENU, TITLES["File"], DISABLED)))
    assert result.answer() == DROP_DOWNS["File"] and not screen_changed(result)


def test_menu_down_draws_an_item_s_child():
    """The drop-down drawn 8 deep (MN_DRAW_DEPTH): an item's child is drawn with it."""
    result = menu_down(TITLES["View"], onto=merge_pokes(running(), ITEM_WITH_A_CHILD))
    assert result.answer() == DROP_DOWNS["View"] and screen_changed(result)


@THROUGH
def test_menu_down_through_its_callers_word(through_line_f):
    menu_down(TITLES["View"], through_line_f=through_line_f)


def test_menu_down_puts_the_tree_on_the_bus():
    assert menu_down(TITLES["File"], tree=MENU | aes.BUS_TAG).answer() == DROP_DOWNS["File"]


# ---- pd_nameit, mn_register ----------------------------------------------------------------------------------------------------
def name_of(image, pd=aes.SHELL_PD):
    return bytes(image[pd + aes.PD_NAME:pd + aes.PD_NAME + aes.PD_NAME_BYTES])


def cda_of(image, pd=aes.SHELL_PD):
    return bytes(image[pd + aes.PD_CDA:pd + aes.PD_CDA + aes.LONG_BYTES])


# (name, the PD's eight name bytes after, how many bytes of its CDA pointer the copy runs into): a program's file name,
# one without an extension, eight characters exactly, none — and one of nine before its dot: strscn ($fecec4) copies
# up to the stop character and writes NO NUL, so the ninth character alone lands on the CDA pointer's top byte (which
# the 24-bit bus ignores; a tenth would reach its address).
NAMES = {
    "a program's file": (b"CONTROL.ACC", b"CONTROL ", 0),
    "no extension": (b"EMPTY", b"EMPTY   ", 0),
    "eight exactly": (b"ABCDEFGH", b"ABCDEFGH", 0),
    "nine before the dot: the ninth on the CDA pointer's top byte": (b"ABCDEFGHI.ACC", b"ABCDEFGH", 1),
    "nothing": (b"", b"        ", 0),
}


@pytest.mark.parametrize("name, after, overrun", NAMES.values(), ids=NAMES)
def test_pd_nameit(name, after, overrun):
    staged = merge_pokes(running(), {name_at(0): name + b"\0"})
    result = aes.run_function(PD_NAMEIT, (aes.SHELL_PD, name_at(0)), staged)
    assert name_of(result.final) == after
    cda_before = cda_of(make_image(staged))
    assert cda_of(result.final) == name[aes.PD_NAME_BYTES:aes.PD_NAME_BYTES + overrun] + cda_before[overrun:]


@THROUGH
def test_pd_nameit_through_its_callers_word(through_line_f):
    aes.run_function(PD_NAMEIT, (aes.SHELL_PD, name_at(0)), merge_pokes(running(), {name_at(0): b"CONTROL.ACC\0"}),
                     through_line_f=through_line_f)


def test_pd_nameit_puts_both_pointers_on_the_bus():
    result = aes.run_function(PD_NAMEIT, (aes.SHELL_PD | aes.BUS_TAG, name_at(0) | aes.BUS_TAG),
                              merge_pokes(running(), {name_at(0): b"CONTROL.ACC\0"}))
    assert name_of(result.final) == b"CONTROL "


def mn_register(pid, name=name_at(0), onto=None, **kwargs):
    return aes.run_function(MN_REGISTER, (pid, name), onto or running(), **kwargs)


def test_mn_register_names_the_running_process():
    result = mn_register(aes.MN_REGISTER_PROCESS, onto=merge_pokes(running(), {name_at(0): b"CONTROL.ACC\0"}))
    assert result.answer() == aes.MN_REGISTER_NAMED and name_of(result.final) == b"CONTROL "


def test_mn_register_names_the_screen_manager_when_it_runs():
    """The process named is rlr's, whichever runs — PD1 here, as switchto leaves it. Not a realistic CALLER (the screen
    manager never calls menu_register; an accessory, a process of its own, does): a second running process, so the
    name is seen to follow rlr, not PD0."""
    result = mn_register(aes.MN_REGISTER_PROCESS, onto=merge_pokes(screen_manager(), {name_at(0): b"SCRMGR.PRG\0"}))
    assert name_of(result.final, aes.SCREEN_MANAGER_PD) == b"SCRMGR  "


def test_mn_register_s_copy_is_thirteen_characters_long():
    """The frame holds 14 bytes: a name of 13 characters and its NUL fill it, and only those reach pd_nameit."""
    result = mn_register(aes.MN_REGISTER_PROCESS, onto=merge_pokes(running(), {name_at(0): b"ABCDEFG.IJKLM\0"}))
    assert name_of(result.final) == b"ABCDEFG "


@pytest.mark.parametrize("taken", range(aes.MN_DA_SLOTS + 1), ids=lambda taken: f"{taken} taken")
def test_mn_register_takes_the_next_slot_until_six(taken):
    result = mn_register(0, onto=registered(*([0] * taken)))
    assert result.answer() == (taken if taken < aes.MN_DA_SLOTS else aes.MN_REGISTER_FULL)


@THROUGH
def test_mn_register_through_its_callers_word(through_line_f):
    mn_register(1, through_line_f=through_line_f)


def test_mn_register_puts_the_name_on_the_bus():
    result = mn_register(aes.MN_REGISTER_PROCESS, name=name_at(0) | aes.BUS_TAG,
                         onto=merge_pokes(running(), {name_at(0): b"CONTROL.ACC\0"}))
    assert name_of(result.final) == b"CONTROL "


def test_mn_register_keeps_a_slot_s_name_pointer_as_handed():
    """An accessory's slot keeps the pointer it was handed WHOLE, top byte and all (mn_bar copies it into an ob_spec)."""
    result = mn_register(1, name=name_at(0) | aes.BUS_TAG)
    assert result.long(aes.AES_DESK_ACC) == name_at(0) | aes.BUS_TAG


# ---- mn_bar, mn_clsda (through the event door) --------------------------------------------------------------------------
def door_run(name, values, pokes, **kwargs):
    """A door user's run, its C first in a child (`aes_event.run_guarded`), ob_draw's just_draw served."""
    return aes_event.run_guarded(name, values, pokes, drawing=True, objects=JUST_DRAW, **kwargs)


def mn_bar(show, onto=None, tree=MENU, **kwargs):
    return door_run(MN_BAR, (tree, show), onto or running(), **kwargs)


# (the registered pids, show, the machine the accessories are registered over): PD0 running with the cursor hidden (an
# application's graf_mouse(M_OFF)) or shown (the dispatcher's menu_bar arm hides nothing).
MN_BAR_CASES = {
    "shown, no accessory": ((), 1, running),
    "shown, one accessory": ((0,), 1, running),
    "shown, six accessories": ((0, 1, 0, 1, 0, 1), 1, running),
    "hidden": ((), 0, running),
    "shown, the cursor shown": ((0,), 1, shown_running),
    "hidden, the cursor shown": ((), 0, shown_running),
}


@pytest.mark.parametrize("pids, show, machine", MN_BAR_CASES.values(), ids=MN_BAR_CASES)
def test_mn_bar(pids, show, machine):
    result = mn_bar(show, onto=registered(*pids, onto=machine))
    assert result.long(aes.AES_GL_MNTREE) == (MENU if show else 0)
    assert result.word(aes.AES_GL_MNCLICKS) == 1
    if show:
        items = aes.MN_DESK_ITEMS + len(pids) if pids else aes.MN_DESK_ALONE
        assert result.object(MENU, DROP_DOWNS["Desk"])["HEIGHT"] == items * result.field("AES", "GL_HCHAR")


@functools.cache
def bar_hidden():
    """`running()` continued from the ROM's own mn_bar hiding the bar — the screen manager's rectangle the whole bar's
    (gl_rmenu) — so a bar shown again sets it back."""
    return rom_derived(addrs.AES_ROM_MN_BAR, aes_event.frame_of(("l", MENU), ("w", 0)), running())


def test_mn_bar_shown_again_after_hidden_sets_the_screen_manager_s_rectangle_back():
    before = make_image(bar_hidden())
    result = mn_bar(1, onto=bar_hidden())
    assert result.after(aes.AES_GL_RMNACTV, aes.GRECT_BYTES) != bytes(before[aes.AES_GL_RMNACTV:
                                                                             aes.AES_GL_RMNACTV + aes.GRECT_BYTES])


def test_mn_bar_rebuilds_the_desk_menu_with_the_accessories():
    pids = (0, 1)
    result = mn_bar(1, onto=registered(*pids))
    box = DROP_DOWNS["Desk"]
    items = [box + offset for offset in range(1, aes.MN_DESK_ITEMS + len(pids) + 1)]
    assert [result.object(MENU, item)["NEXT"] for item in items] == items[1:] + [box]
    assert [result.object(MENU, item)["SPEC"] for item in items[aes.MN_DESK_ITEMS:]] == [name_at(0), name_at(1)]
    assert result.word(aes.AES_GL_DAFIRST) == box + aes.MN_DAFIRST_PAST_BOX


def test_mn_bar_stores_its_owner_s_pid_as_a_longword():
    """ROM FINDING: the owner's pid stored sign-extended as a LONGWORD; the screen manager reads the WORD at the same
    address, the high half (`aes/mnlib.h`, AES_GL_MNPPD). Not a realistic CALLER (the screen manager never calls
    menu_bar; an accessory, a process of its own, would): PD1 running stands in for a non-zero owner's pid."""
    result = mn_bar(1, onto=screen_manager())
    assert result.long(aes.AES_GL_MNPPD) == 1


@THROUGH
def test_mn_bar_through_its_callers_word(through_line_f):
    mn_bar(1, through_line_f=through_line_f)


def test_mn_bar_puts_the_tree_on_the_bus():
    result = mn_bar(1, tree=MENU | aes.BUS_TAG)
    assert result.long(aes.AES_GL_MNTREE) == MENU | aes.BUS_TAG


def mn_clsda(onto, **kwargs):
    return aes_event.run_guarded(MN_CLSDA, (), onto, **kwargs)


# (the registered pids, the pipes' fill after): none; one to PD0's own pipe; one each to PD0 and the screen manager
# (whose parked waits are not a pipe read: it lands in its pipe too).
MN_CLSDA_CASES = {"no accessory": (), "one, PD0 itself": (0,), "two: PD0 and the screen manager": (0, 1)}


PIPES = (aes.SHELL_PD, aes.SCREEN_MANAGER_PD)
MESSAGE_BYTES = aes.MN_MESSAGE_BYTES


@pytest.mark.parametrize("pids", MN_CLSDA_CASES.values(), ids=MN_CLSDA_CASES)
def test_mn_clsda(pids):
    machine = registered(*pids)
    result = mn_clsda(machine)
    before = [aes.read_field(make_image(machine), "PD", "QUEUE_INDEX", pd) for pd in PIPES]
    after = [result.field("PD", "QUEUE_INDEX", pd) for pd in PIPES]
    assert [late - early for early, late in zip(before, after)] == [MESSAGE_BYTES * pids.count(pid) for pid in (0, 1)]


@THROUGH
def test_mn_clsda_through_its_callers_word(through_line_f):
    mn_clsda(registered(0), through_line_f=through_line_f)


# ---- mn_do (through the event door) --------------------------------------------------------------------------------------------
STALE_TRACK = aes.stale_host_slot("AES_MN_DO_FRAME")


def mn_do(onto, title_out=TITLE_OUT, item_out=ITEM_OUT, **kwargs):
    return door_run(MN_DO, (title_out, item_out), merge_pokes(onto, STALE_TRACK, STALE_SR_RECT), **kwargs)


# (the machine's mouse, pressed): every pass-1 arm the event layer answers — the mouse moved off the bar (the bar left:
# nothing found, nothing chosen), the button pressed on a title or off the bar (a click in the bar's own wait ends it).
MN_DO_CASES = {
    "the mouse moved off the bar": (OFF_THE_BAR, False),
    "the button pressed on a title": (None, True),
    "the button pressed off the bar": (OFF_THE_BAR, True),
}


@pytest.mark.parametrize("at, pressed", MN_DO_CASES.values(), ids=MN_DO_CASES)
def test_mn_do_ends_in_its_first_pass(at, pressed):
    result = mn_do(screen_manager(at, pressed))
    assert result.answer() == 0
    assert result.words(TITLE_OUT, 2) == [aes.STALE_WORD] * 2, "nothing chosen is stored"


@THROUGH
def test_mn_do_through_its_callers_word(through_line_f):
    mn_do(screen_manager(OFF_THE_BAR), through_line_f=through_line_f)


def test_mn_do_puts_its_answers_on_the_bus():
    mn_do(screen_manager(OFF_THE_BAR), title_out=TITLE_OUT | aes.BUS_TAG, item_out=ITEM_OUT | aes.BUS_TAG)


# The waits nothing in a static machine satisfies — each a pass the door refuses, in a child process: the mouse on a
# title drops its menu in pass 1 and pass 2 waits to LEAVE that title; the mouse on the bar past the titles waits in
# pass 1 to enter them.
DROPPED = {"Desk": (40, 5), "File": (88, 5), "View": aes_event.THE_VIEW_TITLE_S_POINT, "Options": (196, 5)}
MN_DO_BLOCKS = {**{f"{name} dropped, then waiting to leave it": (at, 2) for name, at in DROPPED.items()},
                "on the bar past the titles, waiting to enter them": (RIGHT_OF_THE_TITLES, 1)}


# ...and a title left SELECTED by an earlier choice and then DISABLED (menu_ienable): not DISABLED alone, so mn_do drops
# it — but do_chg refuses it, nothing is drawn, and pass 2 waits to leave it.
SELECTED_AND_DISABLED = od.state_pokes(MENU, TITLES["View"], SELECTED | DISABLED)
MN_DO_BLOCKS["View selected and disabled: taken, nothing drawn"] = (None, 2)


def blocked_machine(at):
    """A `MN_DO_BLOCKS` case's machine: the screen manager running with the mouse at `at` — or, with none, on the
    "View" title left SELECTED and DISABLED."""
    return merge_pokes(screen_manager(at), STALE_TRACK, STALE_SR_RECT, None if at else SELECTED_AND_DISABLED)


def mn_do_woken(label, machine, at_idle, at_calls=None):
    """mn_do over `machine()`, a call that BLOCKS, as a row that switches (`aes_event.woken_row`)."""
    return aes_event.woken_row(label, MN_DO, (TITLE_OUT, ITEM_OUT), machine, at_idle, at_calls, objects=True)


# WHAT ENDS A BLOCKED mn_do, delivered at the dispatcher's idles: the mouse off every menu (the title put back, the
# next pass waiting for it to come back or for a click), then a click there — nothing chosen. From the bar past the
# titles a title is entered first. AND FROM THE TITLE LEFT SELECTED AND DISABLED, ANOTHER TITLE FIRST: moved straight
# off the bar from it, the ROM's own mn_do does not return (measured: past 1.49 M instructions with a click
# delivered at either of its next two waits — it never idles again; recorded, not pinned further).
def _left_and_clicked_off(first_idle=0):
    return {first_idle: aes_event.move_to(*OFF_EVERY_MENU), first_idle + 1: aes_event.press}


def _wake_of_a_blocked_pass(label):
    if label == "on the bar past the titles, waiting to enter them":
        return {0: aes_event.move_to(*DROPPED["View"]), **_left_and_clicked_off(1)}
    if label == "View selected and disabled: taken, nothing drawn":
        return {0: aes_event.move_to(*DROPPED["File"]), **_left_and_clicked_off(1)}
    return _left_and_clicked_off()


@pytest.mark.parametrize("label", MN_DO_BLOCKS)
def test_mn_do_s_wait_nothing_satisfies_is_held_where_the_rom_s_blocks_and_woken(label):
    """Up to the wait that blocks, the C is the ROM's run where it blocks: the whole image at dsptch — the title
    selected, its menu drawn, the screen under it saved — and every frame handed the door, the MOBLKs read through
    their pointers. AND ON THROUGH THE WAKES, each at an idle of the dispatcher: the menu left, a click off it —
    mn_do answers 0, nothing chosen stored."""
    at, door_calls = MN_DO_BLOCKS[label]
    row = mn_do_woken(f"{label}; then left, a click off it", functools.partial(blocked_machine, at),
                      _wake_of_a_blocked_pass(label))
    taken, ran = aes_event.blocked_then_woken(row)
    assert len(taken.calls) == door_calls and ran.answer == 0
    assert [case.word_in(ran.image, out) for out in (TITLE_OUT, ITEM_OUT)] == [aes.STALE_WORD] * 2


def test_a_child_without_the_walkers_served_ends_by_name():
    """THE RED the child binding's `objects` exists for: without it, the child's first just_draw call — the drop-down's
    items — ends it by name (`aes_event.CHILD_OBJECT_REFUSED`), where an unbound hook would draw nothing and carry on."""
    machine = merge_pokes(screen_manager(DROPPED["File"]), STALE_TRACK, STALE_SR_RECT)
    ends_at_its_first_walk = aes_event.HeldElsewhere(
        "a RED of the child's own binding: it is ended by name at its first walked routine, before any door call — "
        "the same call with the walkers served is `test_mn_do_ends_in_its_first_pass`'s, frames, answers and images held")
    returncode, stderr, _image = aes_event.door_child(MN_DO, (TITLE_OUT, ITEM_OUT), machine, door_calls=ends_at_its_first_walk)
    assert returncode == aes_event.CHILD_OBJECT_REFUSED and f"{addrs.AES_ROM_JUST_DRAW:#x}" in stderr, stderr


# mn_do TAKEN THROUGH INTERRUPTS (`aes_event.interrupted`): the screen manager running with the mouse on a title (or on
# the bar), then the mouse MOVED and the button PRESSED or RELEASED by the ROM's own interrupt code at the entry of a
# pass's ev_multi — door call k is pass k + 1's wait. Points of the desk's menu (the drop-downs' box 11 pixels down):
ON_THE_CHECKED_ITEM = (150, 15)         # View's first item, CHECKED
ON_THE_PLAIN_ITEM = aes_event.VIEW_S_PLAIN_ITEM_S_POINT      # ...its second
ON_THE_PLAIN_ITEM_S_RIGHT_HALF = (184, 23)    # ...where ITEM_WITH_A_CHILD puts its child
ON_A_DISABLED_ITEM = (100, 15)          # File's first item, DISABLED
OFF_EVERY_MENU = (300, 150)
CHOSEN = 1                              # mn_do's answer for a title and item chosen
move_to, press, release = aes_event.move_to, aes_event.press, aes_event.release
DISABLED_ALONE = od.state_pokes(MENU, TITLES["File"], DISABLED)

# (where the mouse starts, pokes, {door call: interrupts}, returned, answer, (title, item) chosen or None)
MN_DO_INTERRUPTED = {
    "the mouse moved onto a title while pass 1 waits on the bar: dropped, then waiting to leave it": (
        RIGHT_OF_THE_TITLES, None, {0: move_to(*DROPPED["View"])}, False, None, None),
    "an item reached and clicked: chosen": (
        DROPPED["View"], None, {1: move_to(*ON_THE_CHECKED_ITEM), 2: press}, True, CHOSEN, ("View", CHECKED_ITEM)),
    "a DISABLED item clicked: nothing chosen, the title put back": (
        DROPPED["File"], None, {1: move_to(*ON_A_DISABLED_ITEM), 2: press}, True, 0, None),
    "the menu left, then a click off it": (
        DROPPED["View"], None, {1: move_to(*ON_THE_CHECKED_ITEM), 2: move_to(*OFF_EVERY_MENU), 3: press}, True, 0, None),
    "the menu left and entered again": (
        DROPPED["View"], None, {1: move_to(*ON_THE_CHECKED_ITEM), 2: move_to(*OFF_EVERY_MENU),
                                3: move_to(*ON_THE_PLAIN_ITEM)}, False, None, None),
    "from an item back onto its title": (
        DROPPED["View"], None, {1: move_to(*ON_THE_CHECKED_ITEM), 2: move_to(*DROPPED["View"])}, False, None, None),
    "title to title: one menu put back, the next dropped": (
        DROPPED["View"], None, {1: move_to(*DROPPED["File"])}, False, None, None),
    "the button pressed and released on the title: still waiting": (
        DROPPED["View"], None, {1: press, 2: release}, False, None, None),
    "pressed on the title, dragged to an item, released: chosen": (
        DROPPED["View"], None, {1: press, 2: move_to(*ON_THE_PLAIN_ITEM), 3: release}, True, CHOSEN, ("View", PLAIN_ITEM)),
    "the DISABLED-alone title's busy loop, left by the mouse": (
        DROPPED["File"], DISABLED_ALONE, {3: move_to(*OFF_THE_BAR)}, True, 0, None),
    "an item's child under the mouse: the item found, not the child": (
        DROPPED["View"], ITEM_WITH_A_CHILD, {1: move_to(*ON_THE_PLAIN_ITEM_S_RIGHT_HALF), 2: press}, True, CHOSEN,
        ("View", PLAIN_ITEM)),
}


def interrupted_machine(at, pokes):
    """An `MN_DO_INTERRUPTED` case's machine: the screen manager running with the mouse at `at`, `pokes` over it."""
    return merge_pokes(screen_manager(at), STALE_TRACK, STALE_SR_RECT, pokes)


@pytest.mark.parametrize("at, pokes, interrupts, returned, answer, chosen", MN_DO_INTERRUPTED.values(),
                         ids=MN_DO_INTERRUPTED)
def test_mn_do_taken_through_interrupts(at, pokes, interrupts, returned, answer, chosen):
    """The C and the ROM taken through the same interrupts at the same passes (`aes_event.interrupted`): the same
    return or block, the same answer, every frame handed the door, the whole image."""
    taken = aes_event.interrupted(MN_DO, (TITLE_OUT, ITEM_OUT), interrupted_machine(at, pokes), interrupts,
                                  objects=True)
    assert (taken.returned, taken.answer) == (returned, answer)
    stored = [case.word_in(taken.image, out) for out in (TITLE_OUT, ITEM_OUT)]
    assert stored == ([TITLES[chosen[0]], chosen[1]] if chosen else [aes.STALE_WORD] * 2)


STILL_WAITING = {label: (at, pokes, interrupts) for label, (at, pokes, interrupts, returned, _answer, _chosen)
                 in MN_DO_INTERRUPTED.items() if not returned}


@pytest.mark.parametrize("label", STILL_WAITING)
def test_mn_do_left_waiting_by_its_interrupts_is_woken_and_ended(label):
    """THE CASES ABOVE THAT END BLOCKED, TAKEN ON: the same interrupts at the same passes' entries, and then — while
    the last pass is blocked — the menu left and a click off it, at the dispatcher's idles (ONE derivation takes the
    interrupts at door calls and at idles): ONE PASS MORE — the wait the click ends — and mn_do returns 0 with nothing
    chosen, every frame handed, the whole image."""
    at, pokes, interrupts = STILL_WAITING[label]
    row = mn_do_woken(f"{label}; then left, a click off it", functools.partial(interrupted_machine, at, pokes),
                      _left_and_clicked_off(), interrupts)
    taken, ran = aes_event.blocked_then_woken(row)
    assert len(ran.calls) == len(taken.calls) + 1 and ran.answer == 0


# mn_do BLOCKED AND WOKEN, the shapes priced: an item reached and clicked with BOTH interrupts taken while a pass
# is blocked (the dearest returning shape, every wake through the dispatcher); and THE DESK'S TURN INSIDE mn_do's
# FIRST WAIT — Return, the key the desk's own evnt_multi waits for, typed while the screen manager is blocked on the
# bar: the dispatcher enters the DESK (the ROM's own desktop: a foreign window), which takes the key and waits
# again; then a title, the menu left, a click — and that turn TWICE, in two of mn_do's waits (two windows, each inside
# another door call: the one run in which a call's windows must be told from the next call's).
RETURN = aes_event.key(aes_event.RETURN_KEY)
ITEM_CHOSEN_WHILE_BLOCKED = "View dropped; an item reached, then clicked, each while a pass is blocked: chosen"
THE_DESK_S_TURN = "on the bar past the titles; the desk's turn (Return); then a title, the menu left, a click off it"
THE_DESK_S_TURN_TWICE = ("on the bar past the titles; the desk's turn (Return); a title; the desk's turn again, in the "
                         "next wait; the menu left, a click off it")
THE_DESK_TAKES_A_KEY = (aes.SHELL_PD,) * 4      # the desktop's own waits and yields over one key
MN_DO_WOKEN = {
    ITEM_CHOSEN_WHILE_BLOCKED: (DROPPED["View"], {0: aes_event.move_to(*ON_THE_CHECKED_ITEM), 1: aes_event.press},
                                CHOSEN, ("View", CHECKED_ITEM), (aes.SCREEN_MANAGER_PD,) * 2),
    THE_DESK_S_TURN: (RIGHT_OF_THE_TITLES, {0: RETURN, 1: aes_event.move_to(*DROPPED["View"]), **_left_and_clicked_off(2)},
                      0, None, THE_DESK_TAKES_A_KEY + (aes.SCREEN_MANAGER_PD,) * 3),
    # ...TWO FOREIGN WINDOWS IN ONE RUN, each inside another door call: the desk takes a key while mn_do waits on the
    # bar, and another while it waits under the dropped menu.
    THE_DESK_S_TURN_TWICE: (
        RIGHT_OF_THE_TITLES, {0: RETURN, 1: aes_event.move_to(*DROPPED["View"]), 2: RETURN, **_left_and_clicked_off(3)},
        0, None, THE_DESK_TAKES_A_KEY + (aes.SCREEN_MANAGER_PD,) + THE_DESK_TAKES_A_KEY + (aes.SCREEN_MANAGER_PD,) * 2),
}


def mn_do_woken_row(label):
    at, at_idle, _answer, _chosen, _entered = MN_DO_WOKEN[label]
    return mn_do_woken(label, functools.partial(interrupted_machine, at, None), at_idle)


@pytest.mark.parametrize("label", MN_DO_WOKEN)
def test_mn_do_blocked_and_woken_through_the_dispatcher(label):
    """...the answer, what is chosen, and WHO THE DISPATCHER ENTERS: the screen manager alone — or the desk first,
    four times (its own waits and yields over the key), before the screen manager is woken by the mouse."""
    _at, _at_idle, answer, chosen, entered = MN_DO_WOKEN[label]
    _taken, ran = aes_event.blocked_then_woken(mn_do_woken_row(label))
    assert (ran.answer, ran.entered) == (answer, entered)
    stored = [case.word_in(ran.image, out) for out in (TITLE_OUT, ITEM_OUT)]
    assert stored == ([TITLES[chosen[0]], chosen[1]] if chosen else [aes.STALE_WORD] * 2)


# ---- the registry --------------------------------------------------------------------------------------------------------------
def register(label, name, arguments, pokes, *, through_line_f=False):
    aes.register(label, name, arguments, pokes, through_line_f=through_line_f, hook=doors())


register("a title's rectangle", RECT_CHANGE, (MENU, MOBLK_AT, TITLES["View"], 1), merge_pokes(running(), STALE_MOBLK))
register("an item's rectangle", RECT_CHANGE, (MENU, MOBLK_AT, CHECKED_ITEM, 1), merge_pokes(running(), STALE_MOBLK))
for _label in ("menu_icheck: a check taken off", "menu_tnormal: a title selected", "menu_ienable: enabled, redrawn",
               "a DISABLED item checked for: left alone"):
    _item, _bits, _set, _redraw, _check, _answer = DO_CHG_CASES[_label]
    register(_label, DO_CHG, (MENU, _item, _bits, _set, _redraw, _check), running())
for _label in ("nothing last", "a title selected"):
    _last, _current, _set, _answer = MENU_SET_CASES[_label]
    register(_label, MENU_SET, (MENU, _last, _current, _set), running())
register("the File menu saved", MENU_SR, (1, MENU, DROP_DOWNS["File"]), merge_pokes(running(), STALE_SR_RECT))
register("the Options menu restored", MENU_SR, (0, MENU, DROP_DOWNS["Options"]),
         merge_pokes(saved(DROP_DOWNS["Options"]), STALE_SR_RECT))
for _title in ("Desk", "Options"):
    register(f"the {_title} menu dropped", MENU_DOWN, (MENU, TITLES[_title]), merge_pokes(running(), STALE_SR_RECT))
register("a program named", PD_NAMEIT, (aes.SHELL_PD, name_at(0)), merge_pokes(running(), {name_at(0): b"CONTROL.ACC\0"}))
register("eight characters, no extension", PD_NAMEIT, (aes.SHELL_PD, name_at(0)),
         merge_pokes(running(), {name_at(0): b"ABCDEFGH\0"}))
register("the running process named", MN_REGISTER, (aes.MN_REGISTER_PROCESS, name_at(0)),
         merge_pokes(running(), {name_at(0): b"CONTROL.ACC\0"}))
register("thirteen characters named", MN_REGISTER, (aes.MN_REGISTER_PROCESS, name_at(0)),
         merge_pokes(running(), {name_at(0): b"ABCDEFG.IJKLM\0"}))
register("an accessory's slot", MN_REGISTER, (0, name_at(0)), registered(0, 1))
register("all six taken", MN_REGISTER, (0, name_at(0)), registered(*([0] * aes.MN_DA_SLOTS)))
aes_event.register("shown again after hidden", MN_BAR, (MENU, 1), bar_hidden(), drawing=True, objects=JUST_DRAW)
for _label in ("shown, no accessory", "shown, six accessories", "hidden", "shown, the cursor shown"):
    _pids, _show, _machine = MN_BAR_CASES[_label]
    aes_event.register(_label, MN_BAR, (MENU, _show), registered(*_pids, onto=_machine), drawing=True,
                       objects=JUST_DRAW)
for _label in ("no accessory", "two: PD0 and the screen manager"):
    aes_event.register(_label, MN_CLSDA, (), registered(*MN_CLSDA_CASES[_label]))
for _label, (_at, _pressed) in MN_DO_CASES.items():
    aes_event.register(_label, MN_DO, (TITLE_OUT, ITEM_OUT), merge_pokes(screen_manager(_at, _pressed), STALE_TRACK,
                                                                         STALE_SR_RECT), drawing=True, objects=JUST_DRAW)
# ...and the worst realistic shape TAKEN THROUGH INTERRUPTS (`aes_event.register_interrupted`), measured by `make bench`
# over every returning case above: a DISABLED item clicked — the pass that finds it disabled and puts the title back —
# over the dearest uninterrupted row.
WORST_INTERRUPTED = "a DISABLED item clicked: nothing chosen, the title put back"
_at, _pokes, _interrupts, *_outcome = MN_DO_INTERRUPTED[WORST_INTERRUPTED]
aes_event.register_interrupted(WORST_INTERRUPTED, MN_DO, (TITLE_OUT, ITEM_OUT), interrupted_machine(_at, _pokes),
                               _interrupts, objects=True)
# ...and THE ROWS THAT SWITCH: mn_do blocked and woken — the second with the desk's turn inside its door call.
for _label in MN_DO_WOKEN:
    aes_event.register_woken(mn_do_woken_row(_label))
