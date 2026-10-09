"""THE OPCODE SWITCH'S CALLS — what `src/aes/gemsuper.c` (aes_dispatch, aes_marshal) is proved over
(`test_aes_gemsuper.py`).

A CALL OF THE SWITCH IS A CALL OF ONE OF ITS ROUTINES, MARSHALLED. Every routine an arm calls has a battery of its
own, whose registered rows are the ROM's own calls of it over machines the ROM's own runs made. So an arm's case is
not written here: it is LIFTED from one of those rows (`lifted`) — the same machine, the same interrupts, the same
arguments, turned back into the int_in and addr_in a program would have handed the trap for the arm to make that very
call (`ARMS`: one row an arm, the inverse of what its instructions read). What a lifted call adds to its routine's
row is the arm: the words it reads, the answer pointers it hands on INTO int_out, the answer it keeps.

TWO ENTRIES. `at_the_switch` stages a call for $fe5d9c — the arrays in the band below, compared memory;
`at_the_marshal` for $fe64e6 — the program's parameter block, control and arrays in the band, the copies in the
marshal's own frame (the stack band on the ROM's shore, a host slot on the C's).

TWO STYLES OF ARM, by what its routine is (`src/aes/gemsuper.c`, WHO CALLS WHAT):
  * a DOOR USER's (`style` DOOR): the routine is band 3's C, or one of the door's entries called through its wrapper —
    the event door bound, every frame it is handed held to the ROM's (`aes_event.run_guarded`);
  * the EVENT LAYER'S OWN (`style` LAYER): ev_keybd, ev_mouse, ev_mesag, ev_timer, ev_dclick, ap_find and the tape are
    no door entries; they reach the entries by their cores, so the door's hook is asked nothing
    (`aes_event.run_layer_case`).
"""
import functools
import struct
from collections import namedtuple

from harness import BASE_IMAGE, addrs, emu, make_image

import abi
import aes
import aes_event
import aes_fslib
import aes_shell
import aes_switch
import aes_switching
import case
import routines
import vdi
import vdi_helpers
from case import merge_pokes

GEMSUPER = aes.header_constants("gemsuper.h")
EVDOOR = aes.header_constants("evdoor.h")
DISPATCH, MARSHAL = "AES_ROM_DISPATCH", "AES_ROM_MARSHAL"
# aes_dispatch(opcode, global, int_in, int_out, addr_in): D0.w the call's answer. aes_marshal(parameter block): no D0
# its caller reads.
aes.declare_alcyon(DISPATCH, aes.WORD_ANSWER, (vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.LONG_ARG, vdi.LONG_ARG, vdi.LONG_ARG,
                                               vdi.LONG_ARG))
aes.declare_alcyon(MARSHAL, None, (vdi.IMAGE_ARG, vdi.LONG_ARG))
WORD, LONG, BUS = aes.WORD_BYTES, aes.LONG_BYTES, aes_event.OS_BUS_ADDR_MASK

# ---- the band: a program's parameter block and its arrays ------------------------------------------------------------
BAND_OFFSET, BAND_BYTES = 0x3000, 0x200
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES,
                         "test/aes_gemsuper.py: a program's parameter block, its control and its arrays")
ARRAY_ROOM = 0x40                       # each array's room: 32 words, 16 longwords — past every count a case hands
CONTROL_AT = BAND_AT
BLOCK_AT = CONTROL_AT + 0x10
ADDR_OUT_AT = BLOCK_AT + 0x18
GLOBAL_AT = ADDR_OUT_AT + 0x8
INT_IN_AT = GLOBAL_AT + 0x20
INT_OUT_AT = INT_IN_AT + ARRAY_ROOM
ADDR_IN_AT = INT_OUT_AT + ARRAY_ROOM
TEXT_AT = ADDR_IN_AT + ARRAY_ROOM       # a string a case hands by address
TEXT_ROOM = BAND_AT + BAND_BYTES - TEXT_AT
PARAMETER_BLOCK = struct.Struct(">6I")  # control, global, int_in, int_out, addr_in, addr_out
assert PARAMETER_BLOCK.size <= ADDR_OUT_AT - BLOCK_AT
assert aes.AES_GLOBAL_WORDS * WORD <= INT_IN_AT - GLOBAL_AT and TEXT_ROOM >= 0x40
STALE = aes.STALE_WORD                  # an answer word before the call: one never written shows
STALE_LONG = aes.words_long(STALE, STALE)
INT_OUT_WORDS = (GEMSUPER["MARSHAL_INT_IN"] - GEMSUPER["MARSHAL_INT_OUT"]) // WORD      # 7: the marshal's array
DONE = GEMSUPER["AES_ANSWER_DONE"]


words = vdi.pack_words                  # big-endian words, each masked to sixteen bits: the suite's one packer


def longs(*values):
    return struct.pack(f">{len(values)}I", *(value & aes.LONG_MASK for value in values))


def words_at(image, pointer, count):
    """`count` words `pointer` reaches through the 24-bit bus — a rectangle or a MOBLK a routine is handed by address,
    which its arm reads IN PLACE in int_in."""
    at = pointer & BUS
    return struct.unpack(f">{count}H", bytes(image[at:at + count * WORD]))


# ---- A CALL: what a program hands the trap -----------------------------------------------------------------------------
# `opcode`; `int_in` (words) and `addr_in` (longwords); `int_out`: how many answer words the program asks back (its
# control's count: the opcode's own, as the bindings hand it); `global_at`: its global[] — the band's by default, a
# resource call's own; `staged`: what else the call's machine holds (a string, a tree).
Call = namedtuple("Call", "opcode int_in addr_in int_out global_at staged", defaults=((), (), 1, GLOBAL_AT, None))


def _arrays(call):
    """A call's arrays in the band, EVERY WORD PAST WHAT THE CALL HANDS STALE: an arm that read one word, or one
    pointer, further than its own reads that — never a zero that happens to be what its routine was handed."""
    stale_words, stale_longs = [STALE] * (ARRAY_ROOM // WORD), [STALE_LONG] * (ARRAY_ROOM // LONG)
    return merge_pokes(call.staged, {INT_IN_AT: words(*stale_words), ADDR_IN_AT: longs(*stale_longs),
                                     INT_OUT_AT: words(*stale_words)},
                       {INT_IN_AT: words(*call.int_in), ADDR_IN_AT: longs(*call.addr_in)},
                       {GLOBAL_AT: words(*[STALE] * aes.AES_GLOBAL_WORDS)} if call.global_at == GLOBAL_AT else None)


def at_the_switch(call, machine):
    """`(arguments, pokes)` of `call` made AT THE SWITCH ($fe5d9c) over `machine`: its arrays in the band, the answer
    words stale."""
    return ((call.opcode, call.global_at, INT_IN_AT, INT_OUT_AT, ADDR_IN_AT), merge_pokes(machine, _arrays(call)))


def control_of(call, counts=None):
    """The control array of `call`: its opcode and counts — or the `counts` a case hands in their place (int_in's,
    int_out's, addr_in's)."""
    n_int_in, n_int_out, n_addr_in = counts or (len(call.int_in), call.int_out, len(call.addr_in))
    return words(call.opcode, n_int_in, n_int_out, n_addr_in, 1 if call.opcode == addrs.AES_ROM_RS_GADDR_OPCODE else 0)


def at_the_marshal(call, machine, counts=None):
    """`(arguments, pokes)` of `call` made AT THE MARSHAL ($fe64e6): the parameter block, the control and the arrays
    in the band, addr_out[0] stale."""
    block = PARAMETER_BLOCK.pack(CONTROL_AT, call.global_at, INT_IN_AT, INT_OUT_AT, ADDR_IN_AT, ADDR_OUT_AT)
    return ((BLOCK_AT,), merge_pokes(machine, _arrays(call), {CONTROL_AT: control_of(call, counts), BLOCK_AT: block,
                                                              ADDR_OUT_AT: longs(STALE_LONG)}))


def int_out(image, count=INT_OUT_WORDS):
    """The program's int_out after a call, as signed words."""
    return [aes.signed(word) for word in words_at(image, INT_OUT_AT, count)]


# ---- THE ARMS: a routine's call, turned back into the call of the switch that makes it ---------------------------------
# `{the routine an arm calls: lift(arguments, image) -> Call}` — `arguments` the routine's own frame as its battery's
# row hands it, `image` that row's machine (a pointer the arm takes INSIDE int_in is read through). An answer
# pointer of the row is dropped: the arm hands the routine a place in int_out instead.
DOOR, LAYER = "a door user's", "the event layer's own"
OPCODE = {name[:-len("_OPCODE")]: getattr(addrs, name) for name in dir(addrs)
          if name.startswith("AES_ROM_") and name.endswith("_OPCODE")}
# The six opcodes `addrs.h` pairs with no routine, READ OFF THE ROM'S TABLE — the one opcode whose entry is the arm's
# address — never off the header the C switches on (`test_aes_gemsuper.py` holds the header to these): a wrong
# number there must fail a call, not re-aim it.
ARMS_OF_NO_ONE_ROUTINE = {"APPL_INIT": 0xFE5DB2, "APPL_READ": 0xFE5DF2, "APPL_EXIT": 0xFE5E40, "MENU_TEXT": 0xFE5FEE,
                          "GRAF_HANDLE": 0xFE6266, "GRAF_MOUSE": 0xFE628E}


def _opcode_of_the_arm_at(arm):
    opcode, = (opcode for opcode in range(addrs.AES_OPCODE_FIRST, addrs.AES_OPCODE_LAST + 1)
               if case.long_in(BASE_IMAGE, addrs.AES_OPCODE_TABLE + (opcode - addrs.AES_OPCODE_FIRST) * LONG) == arm)
    return opcode


APPL_INIT, APPL_READ, APPL_EXIT, MENU_TEXT, GRAF_HANDLE, GRAF_MOUSE = (
    _opcode_of_the_arm_at(arm) for arm in ARMS_OF_NO_ONE_ROUTINE.values())
MENU_ICHECK, MENU_IENABLE, MENU_TNORMAL = (addrs.AES_ROM_DO_CHG_OPCODE, addrs.AES_ROM_DO_CHG_OPCODE_32,
                                           addrs.AES_ROM_DO_CHG_OPCODE_33)
# The opcodes whose arm calls the event layer's own routines by their cores (the module's docstring).
LAYER_OPCODES = frozenset(OPCODE[f"AES_ROM_{name}"] for name in ("AP_FIND", "AP_TPLAY", "AP_TRECD", "EV_KEYBD", "EV_MOUSE",
                                                                 "EV_MESAG", "EV_TIMER", "EV_DCLICK"))
NO_RECTANGLE = (0,) * aes.EV_MOBLK_WORDS


class Unread(int):
    """A word of a binding's int_in THE ROM'S ARM NEVER READS (objc_change's int_in[1], graf_watchbox's int_in[0]):
    handed STALE, so an arm that read it reads no convenient zero — and the one kind of word the guard that every
    word an arm reads takes two values across its cases does not ask about (`test_aes_gemsuper.py`)."""


UNREAD = Unread(STALE)
IENABLE_REDRAWS = 1 << 15              # menu_ienable's item, its top bit: the bar redrawn (`$fe5f86 andi.w #$8000`)
RECT_WORDS = aes.GRECT_BYTES // WORD


def style_of(opcode):
    return LAYER if opcode in LAYER_OPCODES else DOOR


def _clip(image):
    """The clip `image` holds, as objc_draw's and objc_change's int_in hand one: set again, it is the clip it was."""
    return tuple(case.word_in(image, at) for at in (aes.AES_GL_XCLIP, aes.AES_GL_YCLIP, aes.AES_GL_WCLIP, aes.AES_GL_HCLIP))


def _moblk(image, pointer):
    return words_at(image, pointer, aes.EV_MOBLK_WORDS) if pointer else NO_RECTANGLE


def _ap_rdwr(a, _image):
    code, process, length, buffer = a
    return Call(APPL_READ if code == EVDOOR["AP_RDWR_READ"] else OPCODE["AES_ROM_AP_RDWR"], (process, length), (buffer,))


def _ev_multi(a, image):
    flags, mouse1, mouse2, timer, button, message, _answers = a
    return Call(OPCODE["AES_ROM_EV_MULTI"],
                (flags, aes.high_word(button), button >> aes.BUTTON_PARM_MASK_SHIFT & aes.BUTTON_PARM_BYTE,
                 button & aes.BUTTON_PARM_BYTE, *_moblk(image, mouse1), *_moblk(image, mouse2),
                 timer & aes.WORD_MASK, aes.high_word(timer)), (message,), 7)


def _do_chg(a, _image):
    tree, item, bits, set_, redraw, check_disabled = a
    shape = (bits, bool(redraw), bool(check_disabled))
    if shape == (GEMSUPER["MENU_CHECKED"], False, False):
        return Call(MENU_ICHECK, (item, set_), (tree,))
    if bits == GEMSUPER["MENU_DISABLED"] and not check_disabled and set_ in (0, 1):
        return Call(MENU_IENABLE, (item | (IENABLE_REDRAWS if redraw else 0), 0 if set_ else 1), (tree,))
    if shape == (GEMSUPER["MENU_SELECTED"], True, True) and set_ in (0, 1):
        return Call(MENU_TNORMAL, (item, 0 if set_ else 1), (tree,))
    return None                         # a call of do_chg no arm makes (the menu library's own)


def _graf_mouse_of(number):
    return lambda a, _image: Call(GRAF_MOUSE, (number,), tuple(a[:1]))


def _simple(name, words_of, addresses_of=lambda a: (), answers=1, global_of=None):
    """An arm that pushes its routine's words out of int_in and its pointers out of addr_in."""
    def lift(a, image):
        return Call(OPCODE[name], tuple(words_of(a, image)), tuple(addresses_of(a)), answers,
                    global_of(a) if global_of else GLOBAL_AT)
    return lift


def _w(*indices):
    return lambda a, _image: tuple(a[index] for index in indices)


def _p(*indices):
    return lambda a: tuple(a[index] for index in indices)


ARMS = {
    "AES_ROM_AP_RDWR": _ap_rdwr,
    "AES_ROM_AP_FIND": _simple("AES_ROM_AP_FIND", _w(), _p(0)),
    "AES_ROM_AP_TPLAY": _simple("AES_ROM_AP_TPLAY", _w(1, 2), _p(0)),
    "AES_ROM_AP_TRECD": _simple("AES_ROM_AP_TRECD", _w(1), _p(0)),
    "AES_ROM_EV_KEYBD": _simple("AES_ROM_EV_KEYBD", _w()),
    "AES_ROM_EV_BUTTON": _simple("AES_ROM_EV_BUTTON", _w(0, 1, 2), answers=5),
    "AES_ROM_EV_MOUSE": _simple("AES_ROM_EV_MOUSE", lambda a, image: _moblk(image, a[0]), answers=5),
    "AES_ROM_EV_MESAG": _simple("AES_ROM_EV_MESAG", _w(), _p(0)),
    "AES_ROM_EV_TIMER": _simple("AES_ROM_EV_TIMER", lambda a, _image: (a[0] & aes.WORD_MASK, aes.high_word(a[0]))),
    "AES_ROM_EV_MULTI": _ev_multi,
    "AES_ROM_EV_DCLICK": _simple("AES_ROM_EV_DCLICK", _w(0, 1)),
    "AES_ROM_MN_BAR": _simple("AES_ROM_MN_BAR", _w(1), _p(0)),
    "AES_ROM_DO_CHG": _do_chg,
    "AES_ROM_MN_REGISTER": _simple("AES_ROM_MN_REGISTER", _w(0), _p(1)),
    "AES_ROM_OB_ADD": _simple("AES_ROM_OB_ADD", _w(1, 2), _p(0)),
    "AES_ROM_OB_DELETE": _simple("AES_ROM_OB_DELETE", _w(1), _p(0)),
    "AES_ROM_OB_DRAW": _simple("AES_ROM_OB_DRAW", lambda a, image: (a[1], a[2], *_clip(image)), _p(0)),
    "AES_ROM_OB_FIND": _simple("AES_ROM_OB_FIND", _w(1, 2, 3, 4), _p(0)),
    "AES_ROM_OB_OFFSET": _simple("AES_ROM_OB_OFFSET", _w(1), _p(0), answers=3),
    "AES_ROM_OB_ORDER": _simple("AES_ROM_OB_ORDER", _w(1, 2), _p(0)),
    "AES_ROM_OB_EDIT": _simple("AES_ROM_OB_EDIT", lambda a, image: (a[1], a[2], *words_at(image, a[3], 1), a[4]), _p(0),
                               answers=2),
    "AES_ROM_OB_CHANGE": _simple("AES_ROM_OB_CHANGE", lambda a, image: (a[1], UNREAD, *_clip(image), a[2], a[3]), _p(0)),
    "AES_ROM_FM_DO": _simple("AES_ROM_FM_DO", _w(1), _p(0)),
    "AES_ROM_FM_DIAL": _simple("AES_ROM_FM_DIAL", lambda a, image: (a[0], *words_at(image, a[1], RECT_WORDS),
                                                                    *words_at(image, a[2], RECT_WORDS))),
    "AES_ROM_FM_ALERT": _simple("AES_ROM_FM_ALERT", _w(0), _p(1)),
    "AES_ROM_FM_ERROR": _simple("AES_ROM_FM_ERROR", _w(0)),
    "AES_ROM_OB_CENTER": _simple("AES_ROM_OB_CENTER", _w(), _p(0), answers=5),
    "AES_ROM_FM_KEYBD": _simple("AES_ROM_FM_KEYBD", lambda a, image: (a[1], *words_at(image, a[2], 1),
                                                                      *words_at(image, a[3], 1)), _p(0), answers=3),
    "AES_ROM_FM_BUTTON": _simple("AES_ROM_FM_BUTTON", _w(1, 2), _p(0), answers=2),
    "AES_ROM_GR_RUBBOX": _simple("AES_ROM_GR_RUBBOX", _w(0, 1, 2, 3), answers=3),
    "AES_ROM_GR_DRAGBOX": _simple("AES_ROM_GR_DRAGBOX", lambda a, image: (*a[:4], *words_at(image, a[4], RECT_WORDS)),
                                  answers=3),
    "AES_ROM_GR_MOVEBOX": _simple("AES_ROM_GR_MOVEBOX", _w(0, 1, 2, 3, 4, 5)),
    "AES_ROM_GR_GROWBOX": _simple("AES_ROM_GR_GROWBOX", lambda a, image: (*words_at(image, a[0], RECT_WORDS),
                                                                          *words_at(image, a[1], RECT_WORDS))),
    "AES_ROM_GR_SHRINKBOX": _simple("AES_ROM_GR_SHRINKBOX", lambda a, image: (*words_at(image, a[0], RECT_WORDS),
                                                                              *words_at(image, a[1], RECT_WORDS))),
    "AES_ROM_GR_WATCHBOX": _simple("AES_ROM_GR_WATCHBOX", lambda a, _image: (UNREAD, a[1], a[2], a[3]), _p(0)),
    "AES_ROM_GR_SLIDEBOX": _simple("AES_ROM_GR_SLIDEBOX", _w(1, 2, 3), _p(0)),
    "AES_ROM_GSX_MOFF": _graf_mouse_of(GEMSUPER["GRAF_MOUSE_HIDE"]),
    "AES_ROM_GSX_MON": _graf_mouse_of(GEMSUPER["GRAF_MOUSE_SHOW"]),
    "AES_ROM_GSX_MFSET": _graf_mouse_of(GEMSUPER["GRAF_MOUSE_USER_FORM"]),
    "AES_ROM_GR_MKSTATE": _simple("AES_ROM_GR_MKSTATE", _w(), answers=5),
    "AES_ROM_SC_READ": _simple("AES_ROM_SC_READ", _w(), _p(0)),
    "AES_ROM_SC_WRITE": _simple("AES_ROM_SC_WRITE", _w(), _p(0)),
    "AES_ROM_FS_INPUT": _simple("AES_ROM_FS_INPUT", _w(), _p(0, 1), answers=2),
    "AES_ROM_WM_CREATE": _simple("AES_ROM_WM_CREATE", lambda a, image: (a[0], *words_at(image, a[1], RECT_WORDS))),
    "AES_ROM_WM_OPEN": _simple("AES_ROM_WM_OPEN", lambda a, image: (a[0], *words_at(image, a[1], RECT_WORDS))),
    "AES_ROM_WM_CLOSE": _simple("AES_ROM_WM_CLOSE", _w(0)),
    "AES_ROM_WM_DELETE": _simple("AES_ROM_WM_DELETE", _w(0)),
    "AES_ROM_WM_GET": _simple("AES_ROM_WM_GET", _w(0, 1), answers=5),
    "AES_ROM_WM_SET": _simple("AES_ROM_WM_SET", lambda a, image: (a[0], a[1], *words_at(image, a[2], RECT_WORDS))),
    "AES_ROM_WM_FIND": _simple("AES_ROM_WM_FIND", _w(0, 1)),
    "AES_ROM_WM_UPDATE": _simple("AES_ROM_WM_UPDATE", _w(0)),
    "AES_ROM_WM_CALC": _simple("AES_ROM_WM_CALC", _w(0, 1, 2, 3, 4, 5), answers=5),
    "AES_ROM_RS_LOAD": _simple("AES_ROM_RS_LOAD", _w(), _p(1), global_of=lambda a: a[0]),
    "AES_ROM_RS_FREE": _simple("AES_ROM_RS_FREE", _w(), global_of=lambda a: a[0]),
    "AES_ROM_RS_GADDR": _simple("AES_ROM_RS_GADDR", _w(1, 2), global_of=lambda a: a[0]),
    "AES_ROM_RS_SADDR": _simple("AES_ROM_RS_SADDR", _w(1, 2), _p(3), global_of=lambda a: a[0]),
    "AES_ROM_RS_OBFIX": _simple("AES_ROM_RS_OBFIX", _w(1), _p(0)),
    "AES_ROM_SH_READ": _simple("AES_ROM_SH_READ", _w(), _p(0, 1)),
    "AES_ROM_SH_WRITE": _simple("AES_ROM_SH_WRITE", _w(0, 1, 2), _p(3, 4)),
    "AES_ROM_SH_GET": _simple("AES_ROM_SH_GET", _w(1), _p(0)),
    "AES_ROM_SH_PUT": _simple("AES_ROM_SH_PUT", _w(1), _p(0)),
    "AES_ROM_SH_FIND": _simple("AES_ROM_SH_FIND", _w(), _p(0)),
    "AES_ROM_SH_ENVRN": _simple("AES_ROM_SH_ENVRN", _w(), _p(0, 1)),
}
# The routines an arm calls that have a row of their own to lift, by the address a row is entered at.
ROUTINE_AT = {getattr(addrs, name): name for name in ARMS}


# ---- LIFTING: a routine's registered row as the call of the switch that makes it -----------------------------------------
# What a routine's row IS decides how its lifted call is run and registered:
#   RETURNS      a direct row whose run returns with nothing delivered;
#   INTERRUPTED  a door user's row taken through interrupts at its door calls (`aes_event.INTERRUPTED_ROWS`);
#   SWITCHES     a row that blocks and is woken through the dispatcher (`aes_event.SWITCHING_ROWS`).
RETURNS, INTERRUPTED, SWITCHES = "returns", "interrupted", "switches"
Lifted = namedtuple("Lifted", "source kind routine arguments call machine row")


def _frame_of(routine, pokes):
    """The frame a registered row of `routine` stages, read back as its arguments."""
    layout = struct.Struct(">" + "".join(vdi.FRAME_FORMATS[argtype] for argtype in vdi.frame_argtypes(routine)))
    image = make_image(pokes)
    return layout.unpack(bytes(image[abi.FIRST_ARG:abi.FIRST_ARG + layout.size]))


@functools.cache
def lifted(source):
    """THE REGISTERED ROW `source` OF A ROUTINE AN ARM CALLS, LIFTED: a `Lifted` — the row's kind, its routine and
    arguments, the `Call` of the switch that makes that call, and its `machine` (a zero-argument builder, as a row
    that switches keeps one)."""
    kind, routine, arguments, machine, row = _source(source)
    call = ARMS[routine](vdi.as_signed(routine, arguments), make_image(machine()))
    assert call is not None, f"{source}: a call of {routine} no arm of the switch makes"
    return Lifted(source, kind, routine, arguments, call, machine, row)


def label_of(lift, entry=DISPATCH):
    """A call's label: the opcode and the row it is lifted from — or a special call's own."""
    said = lift.source if is_special(lift) else f"opcode {lift.call.opcode}, as {lift.source}"
    return said if entry == DISPATCH else f"marshalled: {said}"


def staged(lift, entry=DISPATCH, counts=None):
    """`(arguments, pokes)` of the lifted call at `entry`."""
    if entry == MARSHAL:
        return at_the_marshal(lift.call, lift.machine(), counts)
    return at_the_switch(lift.call, lift.machine())


# A call that switches with no row of its own to take its deliveries from (appl_exit's yield): nothing is delivered.
NOTHING_DELIVERED = aes_switching.SwitchingRow(None, None, (), None, {})


def switching_row(lift, entry=DISPATCH):
    """A lifted row that switches, as the switch's (or the marshal's) own `SwitchingRow`: the same deliveries at the
    same idles — the arm adds no wait. The switch always answers; the marshal answers nothing. A DOOR USER's arm
    binds the door in its modelled run (`aes_switch.DoorUser`), as its routine's own row does where it has one."""
    assert lift.kind == SWITCHES, lift.source
    arguments, _pokes = staged(lift, entry)
    woken = lift.row if isinstance(lift.row, aes_switching.SwitchingRow) else NOTHING_DELIVERED

    def machine():
        return staged(lift, entry)[1]
    door = (woken.door or aes_switch.DoorUser(objects=True)) if style_of(lift.call.opcode) == DOOR else None
    return aes_switching.SwitchingRow(label_of(lift, entry), entry, arguments, machine, woken.at_idle, entry == DISPATCH,
                                      woken.at_calls, door, woken.at_polls, woken.budget)


def core_of(entry):
    return routines.core_symbol(entry)


# ---- THE CALLS NO ROUTINE'S ROW GIVES: an arm that is inline, or that makes its routine's call its own way ----------------
# Each over the machine of a row that holds what the arm needs (`over`), with the `Call` made from that row's own
# arguments (`call(arguments)`): the menu tree and one of its items, the running desk, the alert's key in the ring.
A_TEXT = b"Text\0"                      # shorter than every item's own: the copy stays inside the item's string
A_SYSTEM_FORM = 2                       # graf_mouse's busy bee: the system resource's bit image 5
NO_FORM_NUMBER = 258                    # above graf_mouse's last number: nothing is done
# `call(arguments)` makes the call from the row's own arguments — or `again(call)` from the row's own LIFTED call
# (its words or pointers changed: `with_words`, `top_bytes`).
Special = namedtuple("Special", "label over call kind again", defaults=(None, RETURNS, None))
A_CLIP = (200, 60, 96, 24)              # inside the screen, across the desk dialog: what is drawn is cut to it
A_KEY, A_NEXT_OBJECT = 0x1E61, 7        # 'a': no key fm_keybd moves by — and a next object unlike a stale word
SIX_TELLING_WORDS = (40, 24, 30, 50, 180, 110)      # a box, where from, where to: no two alike, none the row's own
OTHER_SHEL_WRITE_WORDS = (0, 0, 2)      # shel_write's doex, isgr, iscr: none the row's — and NOT a GEM program (a flag)


def with_words(changed):
    """`again` for a call made once more with `{index: word}` of int_in its own."""
    def again(call):
        assert all(index < len(call.int_in) for index in changed), (call, changed)
        return call._replace(int_in=tuple(changed.get(index, word) for index, word in enumerate(call.int_in)))
    return again


def top_bytes(call):
    """`again` for a call made once more with A TOP BYTE ON EVERY POINTER of addr_in (`aes.BUS_TAG`): another value
    of each longword, which the 68000's bus drops — the arm hands it on whole, its routine reaches the same bytes."""
    assert call.addr_in, call
    return call._replace(addr_in=tuple(pointer | aes.BUS_TAG for pointer in call.addr_in))


def with_a_top_byte(source):
    return f"a top byte on every pointer of {source}"
OFF_THE_WINDOW_ACROSS, ON_THE_WINDOW = (300, 60), (150, 40)     # read off the ROM's wm_find over the row's window
NO_SUCH_TYPE = 17                       # past R_FRIMG (16): rs_gaddr and rs_saddr answer 0
GEMDOS_REFUSES = -40 & aes.LONG_MASK   # EIMBA, an invalid block: what Mfree answers a block it never gave
RSRC_FREE_REFUSED = "rsrc_free: GEMDOS refuses the block, 0 answered"
THE_MENU_S = "aes_do_chg, menu_icheck: a check taken off"
THE_NO_TIMER_S = "aes_ev_multi, the left held, the right clicked while the process was busy: the click record's buttons"
EVNT_MULTI = {name.removeprefix("EVNT_MULTI_"): value for name, value in GEMSUPER.items() if name.startswith("EVNT_MULTI_")}
THE_DESK_RUNNING = "aes_gr_mkstate, four answers"
THE_ALERT_S = "aes_fm_show, Bad Function #, no values (an unimplemented call's)"
FIRST, LAST = addrs.AES_OPCODE_FIRST, addrs.AES_OPCODE_LAST
# The default arm's opcodes: a gap of the table and its last, one past each end of the range, the two ends of a
# word — below 10 the ROM's `sub.w #10` wraps, and `bhi` is unsigned — and an arm's opcode with a bit above its byte
# (the opcode is compared as the WORD it is).
NO_SUCH_CALLS = {"a gap of the table (16)": 16, "the table's last gap (119)": 119,
                 "one below the range (9)": FIRST - 1, "one above it (126)": LAST + 1, "opcode 0": 0,
                 "opcode -1": 0xFFFF, "the largest positive word": 0x7FFF, "the most negative word": 0x8000,
                 "opcode -10": 0xFFF6,
                 "10 + 256: appl_init's opcode above a byte": FIRST + 0x100,
                 "10 with the sign bit: appl_init's opcode below zero": FIRST | 0x8000}
SPECIALS = (
    Special("appl_init", THE_DESK_RUNNING, lambda a: Call(APPL_INIT)),
    Special("graf_handle", THE_DESK_RUNNING, lambda a: Call(GRAF_HANDLE, int_out=5)),
    Special("menu_text: an item's text replaced", THE_MENU_S,
            lambda a: Call(MENU_TEXT, (a[1],), (a[0], TEXT_AT), staged={TEXT_AT: A_TEXT})),
    Special("graf_mouse: one of the AES's own forms", "aes_gsx_mfset, the cursor hidden",
            lambda a: Call(GRAF_MOUSE, (A_SYSTEM_FORM,))),
    Special("graf_mouse: a number past the last, nothing done", "aes_gsx_mfset, the cursor hidden",
            lambda a: Call(GRAF_MOUSE, (NO_FORM_NUMBER,))),
    *(Special(f"no such call: {label}", THE_ALERT_S, functools.partial(lambda opcode, a: Call(opcode), opcode))
      for label, opcode in NO_SUCH_CALLS.items()),
    # ...and calls whose WORDS tell neighbours apart where the routine's own rows hand two the same:
    Special("objc_draw: clipped to a rectangle of the caller's own", "aes_ob_draw, a desk dialog",
            lambda a: Call(OPCODE["AES_ROM_OB_DRAW"], (a[1], a[2], *A_CLIP), (a[0],))),
    Special("menu_icheck: a DISABLED item checked all the same", "aes_do_chg, menu_ienable: enabled, redrawn",
            lambda a: Call(MENU_ICHECK, (a[1], 1), (a[0],))),
    Special("form_keybd: a key it does not move by, the next object handed back as it came",
            "aes_fm_keybd, a key it does not move by", lambda a: Call(OPCODE["AES_ROM_FM_KEYBD"], (a[1], A_KEY, A_NEXT_OBJECT), (a[0],), 3)),
    Special("graf_movebox: six words, each its own", "aes_gr_movebox, down and right",
            lambda a: Call(OPCODE["AES_ROM_GR_MOVEBOX"], SIX_TELLING_WORDS)),
    Special("wind_find: a point whose x is off the window and whose y is on it", "aes_wm_find, a window's",
            lambda a: Call(OPCODE["AES_ROM_WM_FIND"], OFF_THE_WINDOW_ACROSS)),
    Special("wind_find: a point on the window, off it turned round", "aes_wm_find, a window's",
            lambda a: Call(OPCODE["AES_ROM_WM_FIND"], ON_THE_WINDOW)),
    Special("rsrc_gaddr: a type past the last, no address", "aes_rs_gaddr, a tree",
            lambda a: Call(OPCODE["AES_ROM_RS_GADDR"], (NO_SUCH_TYPE, a[2]), global_at=a[0])),
    Special("rsrc_saddr: a type past the last, nothing stored", "aes_rs_saddr, an ob_spec",
            lambda a: Call(OPCODE["AES_ROM_RS_SADDR"], (NO_SUCH_TYPE, a[2]), (a[3],), global_at=a[0])),
    Special(RSRC_FREE_REFUSED, "aes_rs_free, the desk's",
            lambda a: Call(OPCODE["AES_ROM_RS_FREE"], global_at=a[0],
                           staged=vdi_helpers.staged_gemdos_trap_pokes(GEMDOS_REFUSES))),
    Special("shel_write: not a GEM program, no word the row's", "aes_sh_write, both lines",
            lambda a: Call(OPCODE["AES_ROM_SH_WRITE"], OTHER_SHEL_WRITE_WORDS, (a[3], a[4]))),
)
# ---- A SECOND VALUE FOR EVERY WORD AN ARM READS ------------------------------------------------------------------------------
# An arm whose every case hands it ONE value of a word is not held to READING that word: a switch that pushed the
# constant instead passes (`test_aes_gemsuper.py` holds the rule over every arm: each word of int_in and each longword
# of addr_in an arm reads takes at least two values across the arm's cases, `Unread` words aside). Where the arm's
# routine has another registered row, that row is lifted (RETURNING, below). Where it has none, the call is made
# AGAIN over the same ROM-made machine with words of its own — a program's arguments, which no run makes — or with a
# top byte on its pointers (`top_bytes`).
THE_WRITE_S = "aes_ap_rdwr, a write that serves the process waiting to read"
THE_READ_S = "aes_ap_rdwr, a read of a full pipe"
THE_SELECTOR_S_RING = "aes_fm_do, Return in the ring"
TWO_WINDOWS = "aes_wm_close, the lower window"
THE_UPPER_WINDOW = 2                    # the handle the ROM's second wm_create answers
THE_DESK_S_WINDOW = 0
HALF_A_PIPE = 8                         # bytes: half of the sixteen a full pipe's rows read and write
THE_SCREEN_MANAGER = 1                  # its process id
RIGHT_BUTTON = 2
A_RECTANGLE_THE_MOUSE_IS_OUT_OF = (1, 4, 4, 2, 2)      # a MOBLK: leaving (1) the screen's corner — true at once
ANOTHER_ITEM, ANOTHER_TITLE = 30, 5     # of the menu tree: a plain item, the View title (`test_aes_mnlib.py`)
ANOTHER_TEXT_AT = TEXT_AT + 0x10
A_SECOND_FIELD = 3                      # of the selector's tree: its other editable field (`test_aes_ob_edit.py` edits 2 and 3)
ANOTHER_CHILD = 12                      # another object of the selector's tree than the row's own 11
THE_SCROLL_BAR, ITS_TRACK = 7, 10       # of the selector's tree (`test_aes_ob_draw.py`, `test_aes_objects_find.py`)
ANOTHER_RATE = 3                        # evnt_dclick's: the rows set, and ask, rate 0
A_TALLER_BOX = 28                       # graf_dragbox's height: the rows' boxes are all 20 high
WIND_CALC_RECT = 2                      # wind_calc's int_in: the request, the kind, then the rectangle
THE_FIRST = 0                           # rsrc_gaddr's and rsrc_saddr's index: the rows ask the second
TWO_OTHER_BOXES = (70, 45, 24, 24, 30, 25, 240, 150)   # a little box and a big one, no word the rows' own
ANOTHER_WINDOW_S = (0x0003, 24, 36, 180, 90)            # wind_create's kind and rectangle
ANOTHER_PLACE = (44, 52, 120, 60)
ANOTHER_LONG = 0x00654321               # what rsrc_saddr stores: no address of anything
A_SHORTER_BUFFER = 100                  # bytes of shel_get's and shel_put's 256
A_SECOND_OBJECT = 1                     # rsrc_obfix: the object after the row's own, staged as that one is


def _object_staged_again(lift_machine):
    """`{address: bytes}`: the row's one staged object (`aes.TREE_AT`) laid again as the object after it."""
    image = make_image(lift_machine())
    return {aes.TREE_AT + A_SECOND_OBJECT * aes.OB_BYTES: bytes(image[aes.TREE_AT:aes.TREE_AT + aes.OB_BYTES])}


SECOND_VALUES = (
    Special("appl_read: half of a full pipe", THE_READ_S, again=with_words({1: HALF_A_PIPE})),
    Special("appl_write: half a message, to the screen manager", THE_WRITE_S,
            again=with_words({0: THE_SCREEN_MANAGER, 1: HALF_A_PIPE})),
    Special("evnt_button: the right button up, as it is", "aes_ev_button, the button up, as waited for",
            again=with_words({1: RIGHT_BUTTON})),
    Special("evnt_mouse: a rectangle the mouse is out of, to leave", "aes_ev_mouse, the mouse in the rectangle it is to enter",
            lambda a: Call(OPCODE["AES_ROM_EV_MOUSE"], A_RECTANGLE_THE_MOUSE_IS_OUT_OF, int_out=5)),
    Special("evnt_multi: the second rectangle, left at once", THE_NO_TIMER_S,
            again=with_words({EVNT_MULTI["FLAGS"]: EVDOOR["EV_MU_M2"],
                              **{EVNT_MULTI["MOUSE2"] + index: word for index, word in enumerate(A_RECTANGLE_THE_MOUSE_IS_OUT_OF)}})),
    Special("menu_ienable: disabled, not redrawn", THE_MENU_S, lambda a: Call(MENU_IENABLE, (ANOTHER_ITEM, 0), (a[0],))),
    Special("menu_tnormal: a title that is normal, made normal", THE_MENU_S,
            lambda a: Call(MENU_TNORMAL, (ANOTHER_TITLE, 1), (a[0],))),
    Special("menu_text: another item's text, from another place, a top byte on both pointers", THE_MENU_S,
            lambda a: Call(MENU_TEXT, (ANOTHER_ITEM,), (a[0] | aes.BUS_TAG, ANOTHER_TEXT_AT | aes.BUS_TAG),
                           staged={ANOTHER_TEXT_AT: A_TEXT})),
    # (evnt_dclick's two rows hand the rate 0, and objc_find's row from the slider's track finds what a search from
    # the root finds: the SWEEP's finding — two values of a word are not yet two answers)
    Special("evnt_dclick: another rate set", "aes_ev_dclick, a rate set", again=with_words({0: ANOTHER_RATE})),
    Special("objc_find: a file line's point, searched from the scroll bar: not found", "aes_ob_find, a file line, two levels",
            again=with_words({0: THE_SCROLL_BAR})),
    Special("objc_add: another child", "aes_ob_add, to the box of nine", again=with_words({1: ANOTHER_CHILD})),
    Special("objc_change: clipped to a rectangle of the caller's own", "aes_ob_change, a button pressed",
            again=with_words(dict(enumerate(A_CLIP, GEMSUPER["OBJC_CHANGE_CLIP"])))),
    Special("form_do: begun in the second field", THE_SELECTOR_S_RING, again=with_words({0: A_SECOND_FIELD})),
    Special("form_dial: FMD_GROW between two other boxes", "aes_fm_dial, FMD_GROW",
            again=with_words(dict(enumerate(TWO_OTHER_BOXES, GEMSUPER["FORM_DIAL_LITTLE"])))),
    Special("form_keybd: Tab in the second field", "aes_fm_keybd, Tab", again=with_words({0: A_SECOND_FIELD})),
    Special("graf_dragbox: a taller box", "aes_gr_dragbox, below and right of the mouse: it jumps to it",
            again=with_words({1: A_TALLER_BOX})),
    Special("graf_growbox: between two other boxes", "aes_gr_growbox, an icon to a window",
            again=with_words(dict(enumerate(TWO_OTHER_BOXES)))),
    Special("graf_shrinkbox: between two other boxes", "aes_gr_shrinkbox, a window to an icon",
            again=with_words(dict(enumerate(TWO_OTHER_BOXES)))),
    Special("graf_slidebox: the track in the scroll bar", "aes_gr_slidebox, at the top, the mouse outside: 0",
            again=with_words({0: THE_SCROLL_BAR, 1: ITS_TRACK})),
    Special("wind_create: another kind, another rectangle", "aes_wm_create, the first free window",
            again=with_words(dict(enumerate(ANOTHER_WINDOW_S)))),
    # (wm_open of a window that is open already, or of the desk's, does not return on the ROM: the one machine a
    # second handle opens over is wind_delete's row's, whose windows are created and not yet open)
    Special("wind_open: another handle, at another place", "aes_wm_delete, a window",
            lambda a: Call(OPCODE["AES_ROM_WM_OPEN"], (THE_UPPER_WINDOW, *ANOTHER_PLACE))),
    Special("wind_close: the upper of two windows", TWO_WINDOWS, again=with_words({0: THE_UPPER_WINDOW})),
    Special("wind_delete: the upper of two windows", TWO_WINDOWS,
            lambda a: Call(OPCODE["AES_ROM_WM_DELETE"], (THE_UPPER_WINDOW,))),
    Special("wind_get: the desk's work area", "aes_wm_get, WF_WORKXYWH", again=with_words({0: THE_DESK_S_WINDOW})),
    Special("wind_calc: round another rectangle", "aes_wm_calc, every gadget's border",
            again=with_words(dict(enumerate(ANOTHER_PLACE, WIND_CALC_RECT)))),
    Special("rsrc_gaddr: the first tree", "aes_rs_gaddr, a tree", again=with_words({1: THE_FIRST})),
    Special("rsrc_saddr: another long, at the first", "aes_rs_saddr, an ob_spec",
            again=lambda call: with_words({1: THE_FIRST})(call)._replace(addr_in=(ANOTHER_LONG,))),
    Special("rsrc_obfix: the second object", "aes_rs_obfix, a desk object",
            again=lambda call: top_bytes(with_words({0: A_SECOND_OBJECT})(call))),
    Special("shel_get: less than the whole buffer", "aes_sh_get, a whole buffer",
            again=lambda call: top_bytes(with_words({0: A_SHORTER_BUFFER})(call))),
    Special("shel_put: less than the whole buffer", "aes_sh_put, a whole buffer",
            again=lambda call: top_bytes(with_words({0: A_SHORTER_BUFFER})(call))),
    *(Special(with_a_top_byte(source), source, again=top_bytes) for source in (
        THE_READ_S, THE_WRITE_S, "aes_ap_find, the screen manager", "aes_ev_mesag, a message in the pipe", THE_NO_TIMER_S,
        "aes_fm_alert, an application's: no icon, one button, Return",
        "aes_mn_bar, shown, no accessory", "aes_do_chg, menu_icheck: a check taken off",
        "aes_do_chg, menu_ienable: enabled, redrawn", "aes_do_chg, menu_tnormal: a title selected",
        "aes_mn_register, the running process named", "aes_ob_add, to the box of nine", "aes_ob_delete, the head of 11",
        "aes_ob_find, depth 0, the root only", "aes_ob_offset, the deepest, four levels",
        "aes_ob_order, the first of 11 to the tail", THE_SELECTOR_S_RING, "aes_fm_keybd, Tab", "aes_gr_watchbox, Cancel",
        "aes_gr_slidebox, low, the mouse above it in the track: it jumps up",
        "aes_gsx_mfset, the cursor shown: hidden, set, drawn", "aes_sc_read, a path", "aes_sc_write, a long path",
        "aes_sh_read, both lines", "aes_sh_write, both lines", "aes_sh_envrn, PATH= in the AES's own environment")),
)
# The second object rsrc_obfix is handed is staged where the call is made (`special`): the row's own, laid again.
STAGED_WITH_THE_CALL = {"rsrc_obfix: the second object": _object_staged_again}


# TWO LABELLED ARGUMENT CLASSES — machines no ROM run made, each staged to tell apart what the captured machine
# holds alike (`run`'s `onto`), and Tier 1's alone:
#   * THE SCREEN'S METRICS OF ANOTHER WORKSTATION: this machine's character cell is as wide as it is high and its
#     workstation handle is 1, the answer every arm of no answer gives — graf_handle's five words staged each its own;
#   * A MENU ITEM ABOVE 32,767: menu_text multiplies the item UNSIGNED (`$fe6008 mulu.w #24`), so item $8000 of a
#     tree is the object 786,432 bytes above it — staged there, an ob_spec that points at a string's room.
ARGUMENT_CLASS_METRICS = "ARGUMENT CLASS (the screen's metrics of another workstation)"
TELLING_METRICS = {aes.header_constants("gsx.h")["AES_GL_HANDLE"]: words(3), aes.AES_GL_WCHAR: words(6),
                   aes.AES_GL_HCHAR: words(9), aes.header_constants("gsxif.h")["AES_GL_WBOX"]: words(13),
                   aes.AES_GL_HBOX: words(17)}
ARGUMENT_CLASS_FAR_ITEM = "ARGUMENT CLASS (a menu tree with an item above 32,767)"
A_FAR_ITEM = 0x8000
AN_ITEM_S_TEXT_AT = TEXT_AT + 0x20     # where the far item's ob_spec points: the string menu_text copies over


def far_item(tree):
    """The far item's object, staged: free RAM of the snapshot 786,432 bytes above `tree`, its ob_spec alone."""
    at = (tree & BUS) + A_FAR_ITEM * aes.OB_BYTES + aes.OB_SPEC
    assert at + LONG <= addrs.ST_RAM_BYTES and not any(BASE_IMAGE[at:at + LONG]), "the far item's place is free RAM"
    return {at: longs(AN_ITEM_S_TEXT_AT), AN_ITEM_S_TEXT_AT: bytes([case.SLACK_FILL]) * (TEXT_ROOM - 0x20)}


# appl_exit LEAVES BY THE DISPATCHER on every arm (all_run's yield): rows that switch, with nothing delivered — the
# caller is ready and is resumed. Over a desk with no accessory and an empty pipe; with a message left in its pipe
# (drained); and with accessories registered, whose AC_CLOSE mn_clsda writes — into the caller's own pipe too.
APPL_EXITS = (
    Special("appl_exit: no accessory, the pipe empty", "aes_mn_clsda, no accessory", lambda a: Call(APPL_EXIT), SWITCHES),
    Special("appl_exit: a message left in the pipe, read away", "aes_ev_mesag, a message in the pipe",
            lambda a: Call(APPL_EXIT), SWITCHES),
    Special("appl_exit: two accessories told to close, the caller's own message read away",
            "aes_mn_clsda, two: PD0 and the screen manager", lambda a: Call(APPL_EXIT), SWITCHES),
)


def _source(source):
    """A registered row as `(kind, routine, arguments, machine builder, the row)`."""
    if source in aes_event.SWITCHING_ROWS:
        row = aes_event.SWITCHING_ROWS[source].row
        return SWITCHES, row.name, tuple(row.arguments), row.machine, row
    if source in aes_event.INTERRUPTED_ROWS:
        row = aes_event.INTERRUPTED_ROWS[source]
        return INTERRUPTED, row.name, tuple(row.arguments), functools.partial(dict, row.pokes), row
    row = case.registered_case(source)
    _name, entry, _regs, pokes, *_seeds = row
    routine = ROUTINE_AT.get(entry) or next(name for name in vdi.ALCYON if getattr(addrs, name) == entry)
    return RETURNS, routine, _frame_of(routine, pokes), functools.partial(dict, pokes), row


@functools.cache
def special(label):
    """The special call `label` as a `Lifted`: over its row's machine, the call its own."""
    made = next(each for each in (*SPECIALS, *SECOND_VALUES, *APPL_EXITS) if each.label == label)
    kind, routine, arguments, machine, row = _source(made.over)
    assert kind == RETURNS, f"{label}: over a row that returns"
    call = made.again(lifted(made.over).call) if made.again else made.call(vdi.as_signed(routine, arguments))
    if label in STAGED_WITH_THE_CALL:
        call = call._replace(staged=merge_pokes(call.staged, STAGED_WITH_THE_CALL[label](machine)))
    return Lifted(label, made.kind, routine, arguments, call, machine, row)


def is_special(lift):
    """Is `lift` a call named by a label of its own (a special, a count, a call held at the dispatcher) — not by the
    row it is lifted from?"""
    return lift.source in LABELS_OF_THEIR_OWN


# ---- EVERY ARM'S CALLS ---------------------------------------------------------------------------------------------------
# THE ROWS LIFTED, by the name each has in its own battery's registry (a row renamed there reds this module's import
# by that name). RETURNING: every arm with a call that returns, one row or a few an arm — each arm's own instructions
# are a handful, and its routine's battery holds the routine. WOKEN: the arms whose routine waits, each through a
# wake its routine's battery found (the same deliveries at the same idles: an arm adds no wait).
RETURNING = (
    "aes_ap_rdwr, a read of a full pipe",                                           # 11 appl_read
    "aes_ap_rdwr, a write that serves the process waiting to read",                 # 12 appl_write
    "aes_ap_find, the screen manager", "aes_ap_find, none of that name",            # 13
    "aes_ev_keybd, a key queued",                                                   # 20
    "aes_ev_button, the button down, as waited for",                                # 21
    "aes_ev_button, the button up, as waited for",                                  # ...its mask and state apart
    "aes_ev_mouse, the mouse in the rectangle it is to enter",                      # 22
    "aes_ev_mesag, a message in the pipe",                                          # 23
    "aes_ev_multi, the fork queue full of moves run while the process was busy, a timer of no time",       # 25, a timer
    "aes_ev_multi, the left held, the right clicked while the process was busy: the click record's buttons",   # ...none
    "aes_ev_dclick, a rate set", "aes_ev_dclick, the rate asked",                   # 26
    "aes_mn_bar, shown, no accessory", "aes_mn_bar, hidden",                        # 30
    "aes_do_chg, menu_icheck: a check taken off",                                   # 31
    "aes_do_chg, menu_ienable: enabled, redrawn",                                   # 32
    "aes_do_chg, menu_tnormal: a title selected",                                   # 33
    "aes_do_chg, a DISABLED item checked for: left alone",                          # ...and a DISABLED one, left alone
    "aes_mn_register, the running process named",                                   # 35
    "aes_mn_register, all six taken",                                               # ...answering no slot
    "aes_ob_add, to the box of nine",                                               # 40
    "aes_ob_delete, the head of 11",                                                # 41
    "aes_ob_draw, a desk dialog",                                                   # 42
    "aes_ob_find, a file line, two levels", "aes_ob_find, depth 0, the root only",  # 43
    "aes_ob_find, the slider, three levels",
    "aes_ob_offset, the deepest, four levels",                                      # 44
    "aes_ob_order, the first of 11 to the tail",                                    # 45
    "aes_ob_edit, EDINIT, a full path", "aes_ob_edit, a character into the empty path",    # 46
    "aes_ob_change, a button pressed", "aes_ob_change, a menu item unchecked",      # 47
    "aes_fm_do, Return in the ring",                                                # 50
    "aes_fm_dial, FMD_START", "aes_fm_dial, FMD_GROW", "aes_fm_dial, FMD_SHRINK", "aes_fm_dial, FMD_FINISH",   # 51
    "aes_fm_alert, an application's: no icon, one button, Return",                  # 52
    "aes_fm_error, code 2, Return",                                                 # 53
    "aes_ob_center, the file selector",                                             # 54
    "aes_fm_keybd, Return, the default drawn", "aes_fm_keybd, Tab",                 # 55
    "aes_fm_button, the TOUCHEXIT arrow", "aes_fm_button, the arrow, two clicks",   # 56
    "aes_gr_rubbox, stretched to the mouse", "aes_gr_rubbox, the mouse left of the box",   # 70
    "aes_gr_dragbox, below and right of the mouse: it jumps to it",                 # 71
    "aes_gr_movebox, down and right",                                               # 72
    "aes_gr_growbox, an icon to a window",                                          # 73
    "aes_gr_shrinkbox, a window to an icon",                                        # 74
    "aes_gr_watchbox, Cancel",                                                      # 75
    "aes_gr_slidebox, low, the mouse above it in the track: it jumps up",           # 76
    "aes_gsx_moff, the snapshot's cursor: v_hide_c", "aes_gsx_mon, the nest unwound: v_show_c",    # 78: 256, 257
    "aes_gsx_mfset, the cursor shown: hidden, set, drawn",                          # 78: 255, the caller's form
    "aes_gr_mkstate, four answers",                                                 # 79
    "aes_sc_read, a path", "aes_sc_write, a long path",                             # 80, 81
    "aes_wm_create, the first free window", "aes_wm_create, every window in use",   # 100
    "aes_wm_open, a created window",                                                # 101
    "aes_wm_close, the top window",                                                 # 102
    "aes_wm_delete, a window",                                                      # 103
    "aes_wm_get, WF_WORKXYWH", "aes_wm_get, WF_TOP",                                # 104
    "aes_wm_set, moved",                                                            # 105
    "aes_wm_find, a window's", "aes_wm_find, of nothing",                           # 106
    "aes_wm_update, the lock taken",                                                # 107
    "aes_wm_calc, every gadget's border", "aes_wm_calc, no gadget's work area",     # 108
    "aes_rs_gaddr, a tree",                                                         # 112
    "aes_rs_saddr, an ob_spec",                                                     # 113
    "aes_rs_obfix, a desk object",                                                  # 114
    "aes_sh_read, both lines",                                                      # 120
    "aes_sh_write, both lines",                                                     # 121
    "aes_sh_get, a whole buffer", "aes_sh_put, a whole buffer",                     # 122, 123
    "aes_sh_envrn, PATH= in the AES's own environment",                             # 125
    # ...AND THE ROWS THAT GIVE A WORD ITS SECOND VALUE (the section above):
    "aes_ob_add, a file line added to a leaf",                                      # 40: the parent
    "aes_ob_delete, the tail of 11",                                                # 41
    "aes_ob_draw, the selector's scroll bar", "aes_ob_draw, the selector's root alone",    # 42: the object, the depth
    "aes_ob_find, from the slider's track, its parents summed",                     # 43: the object to start at
    "aes_ob_offset, the root",                                                      # 44
    "aes_ob_order, a middle one after the last by count",                           # 45: the object, its new place
    "aes_ob_edit, a dot jumping to the extension", "aes_ob_edit, a digit, right-justified",   # 46: field, index, tree
    "aes_ob_change, a button disabled", "aes_ob_change, no redraw",                 # 47: the state, the redraw flag
    "aes_fm_alert, an application's: three buttons, Return",                        # 52: the default, the string
    "aes_fm_error, code 4, Return",                                                 # 53
    "aes_ob_center, the menu tree, not outlined",                                   # 54
    "aes_fm_button, a radio button: its group put down",                            # 56: another tree
    "aes_gr_rubbox, held at the minimum",                                           # 70
    "aes_gr_dragbox, outside the bound: pulled in",                                 # 71: the bound
    "aes_gr_dragbox, wider than the bound: past its left edge",                     # ...and the box's width
    "aes_gr_watchbox, OK, drawn normal while inside",                               # 75: the two states
    "aes_gr_slidebox, across, one pixel of room",                                   # 76: the direction
    "aes_wm_set, top: a covered window (a title bar)",                              # 105: the field
    "aes_wm_set, drawing released over an area",                                    # ...the handle, the four values
)
# THE ARMS WHOSE ROUTINE TRAPS INTO GEMDOS (rsrc_load, rsrc_free, shel_find, fsel_input): each lifted from a row its
# battery runs over a SCRIPTED or REPLAYED trap, with that battery's own door for the C's side (`GEMDOS_DOORS`: a
# zero-argument builder of the row's hook, as `aes.register` takes one).
GEMDOS = "a routine that traps into GEMDOS"
GEMDOS_OK = 0                           # what the recording trap answers rsrc_free's Mfree
# shel_find's door: the scripted trap, AND THE HANDED-ROUTINE DOOR BOUND TO NOTHING — the arm hands sh_find no
# routine, so a call of one (through `call_alcyon_pointer`'s hook) is refused by name; left unbound, the hook's call
# is nobody's and a C that handed sh_find addr_in[1] for a routine passed.
SHEL_FIND_S_DOOR = aes.doors(aes_shell.scripted_hook, aes.alcyon_object_hook({}))
GEMDOS_DOORS = {
    "aes_rs_load, the header's read fails": lambda: aes_shell.scripted_hook,                        # 110
    "aes_rs_free, the desk's": lambda: vdi_helpers.staged_gemdos_hook(GEMDOS_OK),                   # 111
    "aes_sh_find, found as given": lambda: SHEL_FIND_S_DOOR,                                        # 124
    "aes_sh_find, not there: the root and PATH tried": lambda: SHEL_FIND_S_DOOR,
    # ...and the path on which sh_find CALLS a routine it is handed: the arm hands it none (`clr.l (sp)`), whatever
    # addr_in[1] holds
    "aes_sh_find, found with sh_main's kind of routine, a logger": lambda: SHEL_FIND_S_DOOR,
    RSRC_FREE_REFUSED: lambda: vdi_helpers.staged_gemdos_hook(GEMDOS_REFUSES),
    "aes_fs_input, no memory: the names refused": aes_fslib.replay_doors,                           # 90
}
# ...and each of them that takes a pointer, again with a top byte on it (the section of second values).
TOP_BYTES_THROUGH_GEMDOS = ("aes_rs_load, the header's read fails", "aes_sh_find, found as given",
                            "aes_fs_input, no memory: the names refused")
GEMDOS_DOORS.update({with_a_top_byte(source): GEMDOS_DOORS[source] for source in TOP_BYTES_THROUGH_GEMDOS})
SECOND_VALUES += tuple(Special(with_a_top_byte(source), source, again=top_bytes) for source in TOP_BYTES_THROUGH_GEMDOS)
WOKEN = (
    "aes_ap_rdwr, a read of its empty pipe, blocked; woken by the screen manager's own write (the menu chain)",    # 11
    "aes_ap_tplay, none of four records played: a count of 0",                      # 14: the one yield
    "aes_ap_tplay, a wait and a press played: no mouse record",                     # ...a timer record waited out
    "aes_ap_trecd, one record, a key's",                                            # 15
    "aes_ev_keybd, no key queued, blocked; woken by Return",                        # 20
    "aes_ev_button, a press waited for, blocked; woken by it",                      # 21
    "aes_ev_mouse, the mouse in the rectangle it is to leave, blocked; woken by its leaving",    # 22
    "aes_ev_mesag, no message, blocked; woken by the screen manager's own write (the menu chain)",   # 23
    "aes_ev_timer, a time of five ticks, blocked; run out by them",                 # 24
    "aes_ev_multi, blocked and woken — a key wakes: a key, none queued",            # 25
    "aes_ev_multi, blocked and woken — the ticks wake: a message and a timer",
    "aes_ev_multi, blocked and woken — a writer wakes: a message, none in the pipe",
    "aes_fm_do, nothing typed: the first wait blocked; woken by Return",            # 50
    "aes_fm_alert, no button the default: Return taken, the next wait blocked; the second button clicked while it waits",
    "aes_fm_button, the button held down, OK not under the mouse: the watch blocked; woken by the rise",   # 56
    "aes_gr_rubbox, the corner at the mouse; stretched, then released",             # 70
    "aes_gr_dragbox, held at the mouse; moved, then released",                      # 71
    "aes_gr_watchbox, blocked three times: the mouse in, out again, then the rise: 0",   # 75
    "aes_gr_slidebox, the elevator held; dragged down, then released",              # 76
    "aes_wm_update, the lock handed to the screen manager, which waits for it: a yield inside unsync's call",   # 107
    # ...and the wakes whose WORDS tell an arm's reads apart — a button wait whose clicks, mask and state differ, both
    # rectangles asked, a timer with no message, a recording that answers 0:
    "aes_ap_trecd, a count of 0, ended at once: nothing recorded",
    "aes_ev_button, a double click waited for, blocked; woken by the two presses",
    "aes_ev_multi, blocked and woken — the ticks wake: a timer",
    "aes_ev_multi, blocked and woken — a double click wakes: a double click",
    "aes_ev_multi, blocked and woken — a release wakes: the button up, which is down",
    "aes_ev_multi, blocked and woken — leaving wakes: two rectangles",
    "aes_ev_multi, blocked and woken — entering wakes: the second rectangle alone",
)
# ...A WAKE'S CALL MADE AGAIN with words of its own (the section of second values), over the same machine and taken
# through the same deliveries — the ROM's own run of it says whether they still wake it (`Again`: the wake's row,
# what is changed in its lifted call). A tape's SPEED shows only after its first yield, so that call is a wake like
# any other, priced:
Again = namedtuple("Again", "label over again")
HALF_SPEED = 50                         # appl_tplay's scale, a percentage: the rows play at 100
WOKEN_AGAIN = (
    Again("appl_tplay: at half speed, a top byte on its records", "aes_ap_tplay, a wait and a press played: no mouse record",
          lambda call: top_bytes(with_words({1: HALF_SPEED})(call))),
)
# ...AND THE CALLS HELD AT THE DISPATCHER ALONE, which wait where their rows do and are held THERE — the whole image
# at the first switch, the wait's record among it — and no further. NONE IS A ROW: a timer above 65,535 ticks is
# never woken by a case, and a row's run returns (`aes_event.register_row`); each is another value of words a priced
# wake of the same arm already runs on both blobs.
A_LONG_TIME = (7, 1)                    # 65,543 ticks, low word first: the high word is not zero
HELD_AT_THE_DISPATCHER = (
    Again("evnt_timer: a time above 65,535 ticks", "aes_ev_timer, a time of five ticks, blocked; run out by them",
          with_words(dict(enumerate(A_LONG_TIME)))),
    Again("evnt_multi: a timer above 65,535 ticks", "aes_ev_multi, blocked and woken — the ticks wake: a timer",
          with_words(dict(enumerate(A_LONG_TIME, EVNT_MULTI["TIME_LOW"])))),
    Again("appl_trecord: a top byte on its buffer", "aes_ap_trecd, one record, a key's", top_bytes),
    Again("appl_read: the screen manager's empty pipe",
          "aes_ap_rdwr, a read of its empty pipe, blocked; woken by the screen manager's own write (the menu chain)",
          with_words({0: THE_SCREEN_MANAGER})),
)
# ...and the door users' rows TAKEN THROUGH INTERRUPTS at their door calls, which return (`aes_event.interrupted`).
THROUGH_INTERRUPTS = (
    "aes_fm_do, OK clicked, released on it",                                        # 50
    "aes_fm_alert, the third of three buttons clicked",                             # 52
    "aes_gr_dragbox, moved, the cursor shown",                                      # 71
    "aes_gr_slidebox, the elevator dragged down",                                   # 76
)


def style(lift):
    """How a call's C goes out: through a GEMDOS door of its routine's battery, the event door, or by no door."""
    return GEMDOS if lift.source in GEMDOS_DOORS else style_of(lift.call.opcode)


# THE BINDING OF A DOOR USER'S ARM: the event door, the VDI's cores (the polled ones with them) and every routine a
# tree walk is handed — whatever THIS arm's routine reaches of them (`aes_event.door_hook`).
def walked():
    return aes.walkers()


def gemdos_hook(lift):
    return GEMDOS_DOORS[lift.source]()


# ---- THE DIFFERENTIALS ---------------------------------------------------------------------------------------------------
def run(lift, entry=DISPATCH, counts=None, onto=None):
    """THE TIER 1 DIFFERENTIAL OF A CALL THAT RETURNS, at `entry`, by its style: a door user's C FIRST IN A CHILD and
    then against the ROM with every frame the door is handed compared (`aes_event.run_guarded`); the event layer's
    own through its layer's door (`run_layer_case`); a GEMDOS routine's through its battery's. `onto`: pokes laid
    over the call's machine. An `aes.Result`."""
    arguments, pokes = staged(lift, entry, counts)
    pokes = merge_pokes(pokes, onto)
    how = style(lift)
    if how == GEMDOS:           # the C first in a fork made inside the open pass: a core that spins fails by name
        return aes.run_function(entry, arguments, pokes, hook=gemdos_hook(lift), poison=False,
                                first=aes_event.forked_inside_its_pass(entry, arguments))
    if how == LAYER:
        return aes_event.run_layer_case(entry, arguments, pokes, hook=aes_event.EVENT_LAYER_HOOKS)
    return aes_event.run_guarded(entry, arguments, pokes, drawing=True, objects=walked())


def through_interrupts(lift, entry=DISPATCH):
    """...of a door user's call TAKEN THROUGH ITS ROW'S INTERRUPTS (`aes_event.interrupted`: the C in a child, held
    to the ROM's run; then the bench's second differential)."""
    assert lift.kind == INTERRUPTED and style(lift) == DOOR, lift.source
    arguments, pokes = staged(lift, entry)
    return aes_event.interrupted(entry, arguments, pokes, lift.row.interrupts, objects=True, budget=lift.row.budget)


# ---- THE ROWS ---------------------------------------------------------------------------------------------------------------
def register_returning(lift, entry=DISPATCH, counts=None):
    """One priced row of a call that returns, by its style's own registrar. Its name in the registry."""
    arguments, pokes = staged(lift, entry, counts)
    label, how = label_of(lift, entry), style(lift)
    if how == GEMDOS:
        aes.register(label, entry, arguments, pokes, hook=gemdos_hook(lift))
    elif how == LAYER:
        aes_event.register_row(label, entry, arguments, pokes, hook=aes_event.EVENT_LAYER_HOOKS)
    else:
        aes_event.register(label, entry, arguments, pokes, drawing=True, objects=walked())
    return f"{core_of(entry)}, {label}"


# WHICH CALLS ARE PRICED, AND WHERE. AT THE SWITCH: every call that returns but the default arm's — its nine opcodes
# are one arm and one alert, priced by two (a gap of the table, a word below the range) — and every wake. AT THE
# MARSHAL: one call an arm FAMILY (the copy round the switch is one routine whatever the arm), the two arms that
# call nothing (where the copy's own cost is the whole of the row), the two that call a door entry by its wrapper
# (two counts), rsrc_gaddr (the marshal's own addr_out arm), the default arm, and three wakes.
PRICED_NO_SUCH_CALLS = ("no such call: a gap of the table (16)", "no such call: opcode -1")
MARSHALLED = (
    "appl_init", "graf_handle",
    "aes_ap_find, the screen manager",                                              # appl
    "aes_ap_rdwr, a read of a full pipe",                                           # ...by a door entry's wrapper
    "aes_ev_keybd, a key queued",                                                   # evnt, the event layer's own
    "aes_ev_multi, the left held, the right clicked while the process was busy: the click record's buttons",
    "aes_do_chg, menu_icheck: a check taken off",                                   # menu
    "aes_ob_offset, the deepest, four levels",                                      # objc
    "aes_fm_dial, FMD_START",                                                       # form
    "aes_gr_mkstate, four answers",                                                 # graf
    "aes_sc_read, a path",                                                          # scrp
    "aes_fs_input, no memory: the names refused",                                   # fsel
    "aes_wm_get, WF_WORKXYWH",                                                      # wind
    "aes_rs_gaddr, a tree",                                                         # rsrc, and addr_out
    "aes_sh_envrn, PATH= in the AES's own environment",                             # shel
    "no such call: a gap of the table (16)",
)
WOKEN_AT_THE_MARSHAL = (
    "aes_ev_keybd, no key queued, blocked; woken by Return",
    "aes_ev_multi, blocked and woken — a writer wakes: a message, none in the pipe",
    "appl_exit: no accessory, the pipe empty",
)


def call_of(name):
    """The call `name` — a label of its own (a special's, a wake made again), or the registered row it is lifted from."""
    if any(name == each.label for each in (*WOKEN_AGAIN, *HELD_AT_THE_DISPATCHER)):
        return made_again(name)
    return special(name) if any(name == each.label for each in (*SPECIALS, *SECOND_VALUES, *APPL_EXITS)) else lifted(name)


def returning():
    """`{label: Lifted}`: every call that RETURNS, at the switch — the specials, the lifted rows, the GEMDOS arms'."""
    specials = [each.label for each in (*SPECIALS, *SECOND_VALUES)]
    lifted_through_gemdos = [source for source in GEMDOS_DOORS if source not in specials]
    made = [special(label) for label in specials] + [lifted(source) for source in (*RETURNING, *lifted_through_gemdos)]
    labelled = {label_of(lift): lift for lift in made}
    assert len(labelled) == len(made), "two calls of one label"
    return labelled


def woken():
    """`{label: SwitchingRow}`: every call that SWITCHES, at the switch — the lifted wakes, those made again, and
    appl_exit's."""
    names = (*WOKEN, *(each.label for each in WOKEN_AGAIN), *(each.label for each in APPL_EXITS))
    rows = [switching_row(call_of(name)) for name in names]
    return {row.label: row for row in rows}


def made_again(label):
    """The wake's call made again `label` (`Again`) as a `Lifted`: its wake's row, the call and the label its own."""
    made = next(each for each in (*WOKEN_AGAIN, *HELD_AT_THE_DISPATCHER) if each.label == label)
    lift = lifted(made.over)
    return lift._replace(source=label, call=made.again(lift.call))


def wake_made_again(label):
    """The registered row of the routine's own wake a call made again is made over, by that row's name."""
    return next(each.over for each in (*WOKEN_AGAIN, *HELD_AT_THE_DISPATCHER) if each.label == label)


def held_at_the_dispatcher():
    """`{label: SwitchingRow}`: the calls held at the dispatcher alone — each its wake's row, the call its own."""
    return {made.label: switching_row(made_again(made.label)) for made in HELD_AT_THE_DISPATCHER}


def woken_at_the_marshal():
    rows = [switching_row(call_of(name), MARSHAL) for name in WOKEN_AT_THE_MARSHAL]
    return {row.label: row for row in rows}


def register():
    """EVERY PRICED ROW, REGISTERED — after the batteries whose rows are lifted (`test_aes_gemsuper.py` imports
    them). `(the returning rows' names, {label: the rows that switch})`."""
    names = [register_returning(lift) for lift in returning().values()
             if not lift.source.startswith("no such call") or lift.source in PRICED_NO_SUCH_CALLS]
    names += [register_returning(call_of(name), MARSHAL) for name in MARSHALLED]
    names += register_counts()
    switching = {row.label: aes_switching.register_row(row) for row in (*woken().values(), *woken_at_the_marshal().values())}
    return tuple(names), switching


# ---- THE COUNTS: a control whose counts are not its arrays' ---------------------------------------------------------------
# The marshal copies as many words as the control SAYS (`src/aes/gemsuper.c`, THE COUNTS). Each case here is a call AT
# THE MARSHAL whose counts are handed beside it (`counts`: int_in's, int_out's, addr_in's), over a row's machine;
# every one stays INSIDE the marshal's frame, where the C's copy is the ROM's own.
Counted = namedtuple("Counted", "label over call counts")
SIXTEEN_WORDS = tuple(range(0x1101, 0x1111))    # int_in full, each word telling
MKSTATE, SCRP_READ, FIND = OPCODE["AES_ROM_GR_MKSTATE"], OPCODE["AES_ROM_SC_READ"], OPCODE["AES_ROM_AP_FIND"]
STALE_TEXT = {TEXT_AT: bytes([case.SLACK_FILL]) * TEXT_ROOM}
TWO_TELLING_LONGS = (0x11112222, 0x33334444)
THE_SCREEN_MANAGER_S_NAME = "aes_ap_find, the screen manager"
SEVENTEENTH_IS_THE_OPCODE = "int_in of 17 words: the seventeenth is the opcode the switch is called with"
NINETEENTH_IS_INT_OUT_S_COUNT = "int_in of 19 words: the nineteenth is how many words of int_out go back"
TWENTIETH_IS_ADDR_IN_S_COUNT = "int_in of 20 words: the twentieth is addr_in's count"
THIRD_LONG_IN_THE_ANSWERS = "addr_in of 3 longwords: the third lands in the answer words"
FOURTEENTH_LONG_IS_THE_OPCODE = "addr_in of 14 longwords: the last one's low word is the opcode"
FIFTEENTH_LONG_IS_INT_OUT_S_COUNT = "addr_in of 15 longwords, the frame's last room: the fifteenth is int_out's count"
ADDR_OUT_BY_THE_COPIED_OPCODE = "rsrc_gaddr's opcode with a seventeenth word: addr_out is not written"
INT_IN_COMES_BACK = "int_out of 27 words: the program's own int_in and control come back"
NOTHING_ASKED_BACK = "int_out of no word: the program's is left alone, the answer too"
A_COUNT_DOUBLED_IN_A_WORD = "addr_in's count $8001: doubled in a word, one longword"
A_COUNT_DOUBLED_TO_NOTHING = "addr_in's count $8000: doubled in a word, nothing copied"
COUNTS = (
    Counted(SEVENTEENTH_IS_THE_OPCODE, THE_DESK_RUNNING,
            lambda call: Call(GRAF_HANDLE, (*SIXTEEN_WORDS, MKSTATE), int_out=5), (17, 5, 0)),
    Counted(NINETEENTH_IS_INT_OUT_S_COUNT, THE_DESK_RUNNING,
            lambda call: Call(GRAF_HANDLE, (*SIXTEEN_WORDS, MKSTATE, 19, 5)), (19, 1, 0)),
    Counted(TWENTIETH_IS_ADDR_IN_S_COUNT, THE_DESK_RUNNING,
            lambda call: Call(GRAF_HANDLE, (*SIXTEEN_WORDS, SCRP_READ, 20, 1, 1), (TEXT_AT,), staged=STALE_TEXT), (20, 1, 0)),
    Counted(THIRD_LONG_IN_THE_ANSWERS, THE_SCREEN_MANAGER_S_NAME,
            lambda call: Call(FIND, (), (*call.addr_in, *TWO_TELLING_LONGS)), (0, 2, 3)),
    Counted(FOURTEENTH_LONG_IS_THE_OPCODE, THE_DESK_RUNNING,
            lambda call: Call(FIND, (), (*[STALE_LONG] * 13, MKSTATE)), (0, 5, 14)),
    Counted(INT_IN_COMES_BACK, THE_DESK_RUNNING, lambda call: Call(GRAF_HANDLE, SIXTEEN_WORDS), (16, 27, 0)),
    Counted(NOTHING_ASKED_BACK, THE_DESK_RUNNING, lambda call: Call(GRAF_HANDLE), (0, 0, 0)),
    Counted(FIFTEENTH_LONG_IS_INT_OUT_S_COUNT, THE_DESK_RUNNING,
            lambda call: Call(FIND, (), (*[STALE_LONG] * 13, MKSTATE, 5)), (0, 1, 15)),
    Counted(ADDR_OUT_BY_THE_COPIED_OPCODE, "aes_rs_gaddr, a tree",
            lambda call: call._replace(int_in=(*SIXTEEN_WORDS, GRAF_HANDLE)), (17, 5, 0)),
    Counted(A_COUNT_DOUBLED_IN_A_WORD, THE_SCREEN_MANAGER_S_NAME, lambda call: call, (0, 1, 0x8001)),
    Counted(A_COUNT_DOUBLED_TO_NOTHING, THE_SCREEN_MANAGER_S_NAME, lambda call: call, (0, 1, 0x8000)),
)
# THE THREE LARGEST COPIES THAT STAY IN THE FRAME ARE PRICED ROWS too: on target the frame is a GCC local, and a store
# past it is a store into GCC's own saved registers that no host run can see — both blobs run the copy that fills
# int_in's room (20 words), addr_in's (15 longwords) and int_out's (27 words).
PRICED_COUNTS = (TWENTIETH_IS_ADDR_IN_S_COUNT, FIFTEENTH_LONG_IS_INT_OUT_S_COUNT, INT_IN_COMES_BACK)

# ...AND PAST THE FRAME lie the saved A6 and the return address (`src/aes/gemsuper.c`, THE COUNTS). The two copies IN
# would store over them: `(the call, its counts, the words of the C's refusal)` — the first count past the room, and
# the largest a word holds (on target a copy of 128 KB, refused before a byte of it moves).
FRAME_BYTES = GEMSUPER["MARSHAL_FRAME_BYTES"]
INT_IN_ROOM, ADDR_IN_ROOM, INT_OUT_ROOM = ((FRAME_BYTES - GEMSUPER[f"MARSHAL_{array}"]) // WORD
                                           for array in ("INT_IN", "ADDR_IN", "INT_OUT"))
HOST_INT_OUT_ROOM = INT_OUT_ROOM + GEMSUPER["MARSHAL_HOST_CALLER_BYTES"] // WORD
A_WORD_S_MOST = aes.WORD_MASK
PAST_THE_FRAME = {
    "int_in of 21 words": (Call(GRAF_HANDLE, (*SIXTEEN_WORDS, GRAF_HANDLE, INT_IN_ROOM + 1, 0, 0, 0)), (INT_IN_ROOM + 1, 1, 0),
                           "more than 20 words of int_in"),
    "int_in of 65,535 words": (Call(GRAF_HANDLE, SIXTEEN_WORDS), (A_WORD_S_MOST, 1, 0), "more than 20 words of int_in"),
    "addr_in of 16 longwords": (Call(GRAF_HANDLE, (), (0,) * (ADDR_IN_ROOM // 2 + 1)), (0, 1, ADDR_IN_ROOM // 2 + 1),
                                "more than 15 longwords of addr_in"),
    "addr_in of 32,767 longwords": (Call(GRAF_HANDLE, (), (0,) * 16), (0, 1, A_WORD_S_MOST >> 1),
                                    "more than 15 longwords of addr_in"),
    # ...and the copy BACK, which only reads: refused OFF TARGET ALONE, past the words the host slot models.
    "int_out of 36 words, off target": (Call(GRAF_HANDLE), (0, HOST_INT_OUT_ROOM + 1, 0),
                                        "more than 35 words of int_out OFF TARGET"),
}


@functools.cache
def counted(label):
    """The count case `label` as a `(Lifted, counts)`: over its row's machine, the call made from that row's own."""
    made = next(each for each in (*COUNTS, *READ_PAST_THE_FRAME) if each.label == label)
    kind, routine, arguments, machine, row = _source(made.over)
    call = made.call(lifted(made.over).call if ROUTINE_AT.get(getattr(addrs, routine)) else None)
    return Lifted(label, kind, routine, arguments, call, machine, row), made.counts


# WHERE THE MARSHAL'S FRAME LIES on each shore of a case entered at it: the ROM's `link` saves A6 just below the
# return address the run was entered over; the C's is its host slot. What a case stages THERE is the stack as some
# earlier call left it — a LABELLED ARGUMENT CLASS: the one thing of these cases no ROM run made.
THE_ROM_S_FRAME_AT = abi.FIRST_ARG - LONG - LONG - FRAME_BYTES
OUR_FRAME_AT = aes.HOST_SLOTS["HOST_SLOT_AES_MARSHAL_FRAME"]
ARGUMENT_CLASS = "ARGUMENT CLASS (the supervisor stack as an earlier call left it)"


def stack_left(at, data):
    """`data` at offset `at` of the marshal's frame, on both shores: stale stack under a call."""
    return {THE_ROM_S_FRAME_AT + at: data, OUR_FRAME_AT + at: data}


# ---- int_out PAST THE FRAME: the copy back that hands the program its caller's stack ------------------------------------------
# More than 27 words of int_out and the ROM's copy back runs on past the frame, READING: the saved A6, the return
# address, the marshal's argument (the parameter block's address) and whatever the stack holds above — and returns as
# ever. Reproduced (`src/aes/gemsuper.c`), and by nature the words are EACH BUILD'S OWN:
#   * ON TARGET (both blobs): GCC's frame has above it the saved A6, OUR return address, the image pointer and then
#     the block's address — where the ROM's has the block's address straight after the return address;
#   * OFF TARGET the frame is a host slot with no stack above it: the slot's last sixteen bytes are A MODEL of the
#     caller's words, STAGED BY THE CASE (`a_caller_s_words`) as the ROM's own frame has them on a case entered at the
#     marshal. A LABELLED ARGUMENT CLASS, as `stack_left` is: what a caller left above the frame is no state a ROM
#     run of the marshal makes.
# Each over evnt_multi's call that returns: sixteen words in, one pointer, seven answers — every word of the frame the
# copy back reads is one the call wrote, so nothing stale rides along.
ARGUMENT_CLASS_CALLER = "ARGUMENT CLASS (the words a caller leaves above the marshal's frame)"
A_CASE_S_A6 = 0                         # the A6 a case enters the ROM with: no case seeds one
SAVED_A6_AT = FRAME_BYTES                # where the model begins: the ROM's frame has its saved A6 straight above it
FIRST_PAST_THE_FRAME = "int_out of 28 words: the first past the frame, the saved A6's high word"
THROUGH_THE_ARGUMENT = "int_out of 35 words: the saved A6, the return address and the words of the arguments"
READ_PAST_THE_FRAME = (
    Counted(FIRST_PAST_THE_FRAME, THE_NO_TIMER_S, lambda call: call, (16, INT_OUT_ROOM + 1, 1)),
    Counted(THROUGH_THE_ARGUMENT, THE_NO_TIMER_S, lambda call: call, (16, HOST_INT_OUT_ROOM, 1)),
)


def a_caller_s_words(arguments, pokes):
    """THE MODEL, staged at the host slot's tail: what the ROM's frame has above it on the same case — the A6 the
    case enters with, the harness's return address, then the argument and the longword above it as the case's own
    stack holds them."""
    image = make_image(aes.staged(MARSHAL, arguments, pokes))
    above = bytes(image[abi.FIRST_ARG:abi.FIRST_ARG + 2 * LONG])
    return {OUR_FRAME_AT + SAVED_A6_AT: longs(A_CASE_S_A6, emu.SENTINEL) + above}


def int_out_word_at(index):
    return INT_OUT_AT + index * WORD


# WHAT A BLOB'S RUN OF THOSE ROWS DIFFERS IN, BY NATURE, from the ROM's (Tier 3's drops, each compared by the row's
# companion — the host differential over the model — and vetted on each blob: `test_aes_gemsuper.py`):
THE_SAVED_A6_S = ("the A6 the marshal's `link` saved, copied back past the frame: its CALLER's — the ROM's run is entered "
                  "with the case's registers, our build's with the bench's callee-saved seeds")
THE_ARGUMENTS_ = ("the words above the return address, copied back past the frame: the ROM's frame has the parameter "
                  "block's address there, GCC's the image pointer and then the block's address")
PAST_THE_FRAME_DROPS = {
    FIRST_PAST_THE_FRAME: ((int_out_word_at(INT_OUT_ROOM), int_out_word_at(INT_OUT_ROOM + 1), THE_SAVED_A6_S),),
    THROUGH_THE_ARGUMENT: ((int_out_word_at(INT_OUT_ROOM), int_out_word_at(INT_OUT_ROOM + 2), THE_SAVED_A6_S),
                           (int_out_word_at(INT_OUT_ROOM + 4), int_out_word_at(HOST_INT_OUT_ROOM), THE_ARGUMENTS_)),
}


def staged_past_the_frame(label):
    """`(arguments, pokes)` of a call whose copy back reads past the frame, the model staged."""
    lift, counts = counted(label)
    arguments, pokes = staged(lift, MARSHAL, counts)
    return arguments, merge_pokes(pokes, a_caller_s_words(arguments, pokes))


def register_counts():
    """The priced rows of the counts: the three largest copies inside the frame, and the two that read past it (with
    their drops). Their names in the registry."""
    names = [register_returning(counted(label)[0], MARSHAL, counted(label)[1]) for label in PRICED_COUNTS]
    for label in PAST_THE_FRAME_DROPS:
        arguments, pokes = staged_past_the_frame(label)
        aes_event.register(f"marshalled: {label}", MARSHAL, arguments, pokes, drawing=True, objects=walked(),
                           also_dropped=PAST_THE_FRAME_DROPS[label])
        names.append(f"{core_of(MARSHAL)}, marshalled: {label}")
    return names


# Every call named by a label of its own (`is_special`).
LABELS_OF_THEIR_OWN = frozenset(each.label for each in (*SPECIALS, *SECOND_VALUES, *APPL_EXITS, *WOKEN_AGAIN,
                                                        *HELD_AT_THE_DISPATCHER, *COUNTS, *READ_PAST_THE_FRAME))
