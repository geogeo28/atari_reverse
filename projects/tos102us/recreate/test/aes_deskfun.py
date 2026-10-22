"""THE DESK'S ALERT AND ITS MESSAGE TO ITSELF — unit H of band 6 wave 1b, group G4 (`src/desk/deskfun.c`,
`test/test_desk_fun.py`): fun_alert `$fdfd58` and fun_msg `$fdfda6`, their declared Alcyon frames and the unit's list.
Both end on a binding of unit D: every case is a row that switches (`aes_deskarrive`)."""
import aes
import vdi

WORD, LONG, IMAGE = vdi.WORD_ARG, vdi.LONG_ARG, vdi.IMAGE_ARG
FUN_ALERT, FUN_MSG = "AES_ROM_DESK_FUN_ALERT", "AES_ROM_DESK_FUN_MSG"
# `{routine: (the core's answer, its frame in push order)}`
SIGNATURES = {
    FUN_ALERT: (aes.WORD_ANSWER, (WORD, WORD, LONG)),
    FUN_MSG: (aes.WORD_ANSWER, (WORD,) * 7),
}
for _name, (_restype, _frame) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
UNIT_H = tuple(SIGNATURES)
# ---- band 6 wave 2, group G2 (unit H) ---- the unit's wave-2 routines: their own signatures and list, so wave
# 1b's UNIT_H (and its count) stays as it is
P = "AES_ROM_DESK_FUN_"
FUN_REBLD, FUN_MKDIR, FUN_OP, FUN_DDST, FUN_WDST = (P + short for short in ("REBLD", "MKDIR", "OP", "DDST", "WDST"))
FUN_WIN2WIN, FUN_WIN2DESK, FUN_DISK, FUN_DESK2WIN = (P + short for short in ("WIN2WIN", "WIN2DESK", "DISK", "DESK2WIN"))
FUN_D2DESK, FUN_DRAG = P + "D2DESK", P + "DRAG"
SIGNATURES_WAVE_2 = {
    FUN_REBLD: (None, (LONG,)),
    FUN_MKDIR: (aes.WORD_ANSWER, (LONG,)),
    FUN_OP: (aes.WORD_ANSWER, (WORD, LONG)),
    FUN_DDST: (aes.WORD_ANSWER, (LONG, LONG, WORD)),
    FUN_WDST: (aes.WORD_ANSWER, (LONG, LONG, LONG, LONG)),
    FUN_WIN2WIN: (None, (WORD, WORD, WORD)),
    FUN_WIN2DESK: (None, (WORD, WORD)),
    FUN_DISK: (aes.WORD_ANSWER, (WORD, LONG, LONG, LONG, WORD)),
    FUN_DESK2WIN: (None, (WORD, WORD)),
    FUN_D2DESK: (aes.WORD_ANSWER, (WORD,)),
    FUN_DRAG: (aes.WORD_ANSWER, (WORD, WORD, WORD, WORD)),
}
for _name, (_restype, _frame) in SIGNATURES_WAVE_2.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
UNIT_H_WAVE_2 = tuple(SIGNATURES_WAVE_2)
# FLIPPED at band 6 slice F3 (stage 2) but two: fun_d2desk and fun_drag HELD to stage 3 (each calls unit I's pro_run,
# flipped at stage 2 by its other author — the cut's split).
UNIT_H_WAVE_2_HELD_AT_F3 = (FUN_D2DESK, FUN_DRAG)
UNIT_H_WAVE_2_FLIPPED = tuple(name for name in UNIT_H_WAVE_2 if name not in UNIT_H_WAVE_2_HELD_AT_F3)
# THE DRIVERS THAT REACH GEMDOS (pn_active's searches, Dcreate, the copy engine's calls) take it, on both shores, from
# unit C's recorder replaying the ROM's own run in place (`aes_deskdir`'s ENGINE, `in_place`, `replayed` — group G1's):
# a row's child binds its twins.
from collections import namedtuple

import aes_event as _event
import aes_deskdir as _dd

REACH_GEMDOS = (FUN_REBLD, FUN_MKDIR, FUN_OP, FUN_DDST, FUN_WDST, FUN_WIN2WIN, FUN_WIN2DESK, FUN_DISK, FUN_DESK2WIN, FUN_DRAG)
for _name in REACH_GEMDOS:
    _event.declare_child_doors(_name, _dd.ENGINE_CHILD_DOORS)


# THE ROM'S OWN RUN IN PLACE is unit C's walk (`aes_deskdir.in_place`: from each stand, the run to the next trap and
# the run to the routine's return, the nearer taken — the return's stack its own call's). (Wave 2's fix pass: this
# module's own copy was deleted — the two walks were measured identical on all 45 replayed cases of units C and H.)
in_place = _dd.in_place


# ---- THE WAKES: what ends a driver's waits, the same hand twice — as the row's interrupts, one an idle
# (`aes_event.woken_row`'s `at_idle`), and as the receptions the ROM's run in place takes in at its idles (`in_place`).
# A key typed is one idle of the row; a click is three (the mouse onto the button, pressed, let go) and one of the run
# in place (the hands' own reception, `aes_desk.A_CLICK`): what the replay is derived from is the ORDER OF THE TRAPS,
# which the number of idles does not move.
Wake = namedtuple("Wake", "at_idle receptions")
Wake.__doc__ = """`at_idle(chain) -> {idle: interrupt}` and `receptions(chain) -> (reception tuple, ...)`."""


def keys_typed(*scancodes):
    """A key per idle, each pressed and let go."""
    def at_idle(_chain):
        return {idle: _event.key(scancode) for idle, scancode in enumerate(scancodes)}

    def receptions(_chain):
        import aes_boot
        from aes_desk import KEY_RELEASED
        return tuple((aes_boot.ikbd(scancode), aes_boot.ikbd(scancode | KEY_RELEASED)) for scancode in scancodes)
    return Wake(at_idle, receptions)


def clicked(point_of, step):
    """A click at `point_of(machine)` — the machine the chain's step `step` left (where what is clicked is up)."""
    def point(chain):
        import aes_boot
        import aes_desk
        return point_of(aes_boot.Machine(aes_desk.walked(chain).steps[step].boot))

    def at_idle(chain):
        return {0: _event.move_to(*point(chain)), 1: _event.press, 2: _event.release}

    def receptions(chain):
        import aes_boot
        from aes_desk import A_CLICK
        return ((aes_boot.mouse_to(*point(chain)), *A_CLICK),)
    return Wake(at_idle, receptions)


def alert_button_point(text):
    """`machine -> the middle of the button reading `text` (its blanks aside) of the ALERT that is up`:
    `aes_desk.button_point`'s walk (a G_BUTTON shown by a tree the desk's live stack holds) over the alert's PADDED
    texts ("  OK  "), which `aes_desk._buttons_reading` matches only unpadded."""
    def point(machine):
        import aes_boot
        import aes_desk
        import case
        ram, bus = machine.ram, aes_boot.BUS
        parked = machine.long(machine.static_processes()[0].uda + aes.UDA_SUPER_SP) & bus
        held = {case.long_in(ram, at) & bus for at in range(parked, aes_desk.stacks(machine)[aes_desk.PD0_STACK][1] - 2, 2)}
        up = [shown for at in range(0, len(ram) - aes.OB_BYTES, 2)
              if ram[at + aes.OB_TYPE + 1] == aes.G_BUTTON and 0 < (case.long_in(ram, at + aes.OB_SPEC) & bus) < len(ram)
              and bytes(ram[case.long_in(ram, at + aes.OB_SPEC) & bus:][:16]).split(b"\0")[0].strip(b" ") == text.encode()
              for shown in aes_desk._trees_showing(ram, at, held)]
        assert len(up) == 1, f"{len(up)} alerts up hold a button reading {text!r}"
        x, y, width, height = aes_desk.box(ram, *up[0])
        return x + width // 2, y + height // 2
    return point


def dialog_button_point(text):
    """`machine -> the middle of the desk dialog's button reading `text``(`aes_desk.button_point`)."""
    def point(machine):
        import aes_desk
        return aes_desk.button_point(machine, text)
    return point


def engine_replayed(wake=None):
    """A case's `laid`: unit C's recorder over the ROM's own run in place from the arrival to its return (`in_place`) —
    `wake`'s receptions taken in at its idles —, said in the case's id."""
    return (_dd.REPLAYED, lambda arrived: _dd.replayed(in_place(arrived, wake.receptions(arrived.chain) if wake else ())))
# ---- end of group G2's wave-2 ----
