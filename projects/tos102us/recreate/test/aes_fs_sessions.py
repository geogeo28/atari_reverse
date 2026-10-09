r"""THE FILE SELECTOR's SESSIONS — fs_input ($fe7d90) run whole, as a user drives it (`test_aes_fs_input*.py`).

A SESSION is fs_input(path, selection, &button) over `aes_fslib.fs_input_machine` taken through a SCHEDULE: what the
user does at each of the selector's WAITS (the ev_multi calls fm_do and gr_slidebox's drag loop make, counted from 0
— `aes_event.Waits`), every one an interrupt the ROM's own ISRs deliver there: a key through the BIOS's keyboard
handler, the mouse moved and the button pressed or released through the VDI's mouse interrupt. A wait with no row takes
nothing: the button still down from a TOUCHEXIT object's press, the wait is answered at once and the object pressed
again — an arrow HELD. A TOUCHEXIT press ends fm_do with the button down, so the release comes with the next thing the
user does (alone it is nothing the wait asks for).

WHERE THE USER CLICKS is read off the selector's own tree: an object's place on the screen by the ROM's ob_offset over
the session's machine (`Places`).

GEMDOS under a session is REPLAYED (`aes_fslib.session_script`): derived from the ROM's own run of the same session
over the staged disk.

A SESSION THE USER IS WAITED FOR IN (`Woken`): a wait at which nothing has arrived BLOCKS — the machine leaves by the
dispatcher — and what the user then does is taken where the machine waits for it, at the dispatcher's IDLE: the
selector is woken through the dispatcher and goes on, to its return. On both shores it is ONE RETURNING RUN (a row
that switches, `aes_event.woken_row`): the ROM's through its own dispatcher, the C's through the host's model with
the door bound (Tier 1), our build's through its own dsptch (Tier 3).
"""
import functools
from collections import namedtuple

from harness import BASE_IMAGE

import aes
import aes_event
import aes_fslib as fsl
import test_aes_fmdo as fmdo

FS = fsl.FS
SELECTOR = fsl.SELECTOR
FIRST_NAME, ROWS = fsl.FIRST_NAME, fsl.ROWS
CLOSER, TITLE, FILE_BOX, SLIDER, ELEVATOR = (FS["FS_CLOSER"], FS["FS_TITLE"], FS["FS_FILE_BOX"], FS["FS_SLIDER"],
                                             FS["FS_ELEVATOR"])
UP_ARROW, DOWN_ARROW, OK, CANCEL = fsl.UP_ARROW, fsl.DOWN_ARROW, FS["FS_OK"], FS["FS_CANCEL"]
press, release, move_to, double_click = aes_event.press, aes_event.release, aes_event.move_to, aes_event.double_click
RETURN = aes_event.key(aes_event.RETURN_KEY)
UP, ESCAPE, BACKSPACE, TAB = (aes_event.key(code) for code in (fmdo.UP, fmdo.ESCAPE, fmdo.BACKSPACE, fmdo.TAB))
SHORT, MIDDLE, LONG, LONGER = (fsl.SESSION_INSNS, fsl.MIDDLE_SESSION_INSNS, fsl.LONG_SESSION_INSNS,
                               fsl.LONGER_SESSION_INSNS)

ROOT_PATH, folder = fsl.ROOT_PATH, fsl.folder
MIXED, SHUFFLED, ONE = folder("MIXED"), folder("SHUFFLED"), folder("ONE")
# The rows MIXED lists first, by the object each is in: its three folders, then its files in order.
AUTO_ROW, TOOLS_ROW, ZOO_ROW, A_C_ROW, AB_TXT_ROW = range(FIRST_NAME, FIRST_NAME + 5)
EMPTY_ROW = FIRST_NAME + 2              # ...and in ONE, whose one name leaves every other row empty
INSIDE = 2                              # pixels inside an object's edge: on it, off its border


def typed(text):
    """A key per character of `text`, in order."""
    return [aes_event.key(aes_event.scancode_of(character)) for character in text]


class Places:
    """Where the selector's objects are on the screen over `machine`: the ROM's own ob_offset (`fmdo.middle_of`)."""

    def __init__(self, machine):
        self._machine, self._middles = machine, {}

    def middle(self, index):
        """The object's middle — asked of the ROM once for these places."""
        if index not in self._middles:
            self._middles[index] = fmdo.middle_of(SELECTOR, index, onto=self._machine)
        return self._middles[index]

    def corner(self, index):
        """The object's top left corner."""
        placed, (x, y) = aes.read_object(BASE_IMAGE, SELECTOR, index), self.middle(index)
        return x - placed["WIDTH"] // 2, y - placed["HEIGHT"] // 2

    def click(self, index):
        """A click on `index`: the mouse moved onto its middle, the left button pressed."""
        return move_to(*self.middle(index)), press

    def twice(self, index):
        """...and a double click on it."""
        return move_to(*self.middle(index)), double_click

    def beside_the_rows(self):
        """A point of the list's box left of its rows: the box itself (object 6) is all ob_find meets there."""
        left, _top = self.corner(FILE_BOX)
        return left + INSIDE, self.middle(FILE_BOX)[1]

    def track(self, down):
        """A point of the slider's track `down` pixels below its top."""
        _left, top = self.corner(SLIDER)
        return self.middle(SLIDER)[0], top + down


# A session: the path and the selection handed in, what the user does at each wait (`waits(places)`: `{wait: an
# interrupt or a tuple of them}`), the budget it declares, what it must hand back — the button word, the path, the
# selection — whether the cursor is shown, and whether it BLOCKS: a session cut short, the user doing nothing at its
# last wait — the selector then waits for ever, and both shores are compared as it stands there.
Session = namedtuple("Session", "path selection waits budget button path_out file_out shown blocks",
                     defaults=(None, None, None, False, False))


def schedule(steps):
    """`steps` — what the user does at each wait in turn, None for a wait that takes nothing — as a `waits(places)`:
    each step an interrupt, a tuple of them, or a callable of the session's `Places` answering one."""
    def waits(places):
        resolved = {}
        for wait, step in enumerate(steps):
            if step is None:
                continue
            parts = step if isinstance(step, (tuple, list)) else (step,)
            taken = []
            for part in parts:
                answered = part(places) if getattr(part, "asks_places", False) else part
                taken += answered if isinstance(answered, (tuple, list)) else [answered]
            resolved[wait] = tuple(taken)
        return resolved
    return waits


def _asking(function):
    function.asks_places = True
    return function


def click(index):
    return _asking(lambda places: places.click(index))


def twice(index):
    return _asking(lambda places: places.twice(index))


def at(point, *interrupts):
    """The mouse moved to `point(places)`, then `interrupts`."""
    return _asking(lambda places: (move_to(*point(places)), *interrupts))


@functools.cache
def machine_of(session):
    """`(the real-disk machine, the replayed one, the script)` of `session`: the script derived from the ROM's own run
    of it over the staged disk (`aes_fslib.session_script`: its answers, the functions called, that run's memory)."""
    real = fsl.fs_input_machine(session.path, session.selection, shown=session.shown)
    script = fsl.session_script(real, interrupts_of(session, real), session.budget, blocks=session.blocks)
    return real, fsl.replay_machine(real, script.answers), script


def interrupts_of(session, machine):
    return aes_event.Waits(session.waits(Places(machine)))


# What the child of each session taken in this process PRINTED of its VDI calls, with the deliveries it ran under:
# `{session: (the digest, delivered)}`. A session's C runs in ONE child per process — every child of fs_input prints
# the digest as it exits — so the case that holds the session's draws to the ROM's reads it here where the session was
# taken already, and runs a child of its own only where it was not (another worker took it).
_DREW = {}


def taken(session, **kwargs):
    """`session` on both shores (`aes_fslib.session`): the C held to the ROM over GEMDOS replayed — to its return, or
    for one that blocks to the entry of the wait nothing ends, where the C is refused as a call that would block."""
    real, replayed, _script = machine_of(session)
    held = fsl.session(replayed, interrupts_of(session, real), session.budget, **kwargs)
    assert held.returned != session.blocks
    if held.returned:
        _DREW[session] = (fsl.vdi_digest_in(held.stderr), held.delivered)
    return held


def drawn_as_the_rom_draws(session):
    """Every VDI call the C makes over `session` is the ROM's, in order (`aes_fslib.vet_the_draws`): the C's as its
    child printed them — the child `taken` ran in this process, or one run here for it
    (`aes_fslib.vet_the_draws_of_a_child_of_its_own`)."""
    real, replayed, _script = machine_of(session)
    if session not in _DREW:
        return fsl.vet_the_draws_of_a_child_of_its_own(replayed, interrupts_of(session, real), session.budget)
    ours, delivered = _DREW[session]
    return fsl.vet_the_draws(ours, replayed, delivered, session.budget)


# ---- A SESSION THE USER IS WAITED FOR IN ---------------------------------------------------------------------------------
# `at_waits(places)`: what the user has done by the entry of each wait (a session's own `waits`); `at_idles(places)`:
# what is done WHILE THE SELECTOR WAITS, at each idle of the dispatcher in turn (`schedule`, as a session's waits are
# written); `same`: THE SAME USER NEVER WAITED FOR — the returning `Session` in which every one of those interrupts is
# taken at a wait's entry instead. `budget`: the woken run's own, where it is not `same`'s class. `running`: a
# zero-argument maker of ANOTHER machine whose running process makes the call (`aes_fslib.fs_input_machine`'s) — one
# in which the selector is kept waiting by more than the user (the screen's lock held by the screen manager's menu).
# WHY `same`: GEMDOS under the woken run is replayed from `same`'s script. A wake changes WHEN the selector learns of a
# key or a click, never which GEMDOS calls it then makes (GEMDOS reads no interrupt's state) — and that is HELD, not
# assumed: the woken run makes exactly the script's calls, in order, to its last, EACH HANDED THE FRAME THE SCRIPT'S
# ANSWER WAS GIVEN TO (`vet_its_gemdos_calls`: the function numbers alone would pass a selector that searched another
# path, or freed another block, and was answered as if it had not) — and, WHERE IT RUNS OVER `same`'S OWN MACHINE
# (`running is None`), leaves the selector, the strings handed back and the screen as `same`'s run over the staged
# disk leaves them (`vet_it_ends_as_never_waited_for`). THE END-STATE PROPERTY IS CLAIMED FOR NO OTHER MACHINE: a
# session over `running`'s (the screen manager's menu, the mouse moved to it and off it) ends on another screen by
# nature — what it differs by is pinned as the stated difference where the session is held
# (`spans_differing_from_never_waited_for`), not asked to be nothing.
Woken = namedtuple("Woken", "at_waits at_idles same budget running", defaults=(None, None))
WOKEN_WHILE_IT_WAITS = "the user waited for: woken through the dispatcher"


@functools.cache
def _replayed_machine_of(woken):
    """The machine `woken` runs over: `same`'s replayed one — or `running`'s process making the same call over the
    same disk, GEMDOS replayed from the same script (GEMDOS answers by the disk and its own arena, which no state of
    the AES reaches: held where the row is taken, `vet_its_gemdos_calls`)."""
    _real, replayed, script = machine_of(woken.same)
    if woken.running is None:
        return replayed
    same = woken.same
    return fsl.replay_machine(fsl.fs_input_machine(same.path, same.selection, running=woken.running()), script.answers)


@functools.cache
def woken_row(woken, label=WOKEN_WHILE_IT_WAITS):
    """`woken` as a row that switches (`aes_event.woken_row`): fs_input over `same`'s replayed machine, the session's
    interrupts at its waits, the wakes at the dispatcher's idles, under the budget it declares."""
    places = Places(machine_of(woken.same)[0])
    return aes_event.woken_row(label, fsl.INPUT, fsl.ARGUMENTS, functools.partial(_replayed_machine_of, woken),
                               woken.at_idles(places), aes_event.Waits(woken.at_waits(places)), objects=True,
                               budget=woken.budget or woken.same.budget)


def vet_its_gemdos_calls(woken, image):
    """THE SCRIPT IS THE WOKEN RUN'S OWN: the GEMDOS calls the run that left `image` made (the replay's ledger) are
    the script's, function for function, to its last — a call more, fewer or other and the answers it was given were
    another call's — AND FRAME FOR FRAME: each was handed the bytes the script's call was (the path searched, the
    block freed, the DTA named), so each answer is the ROM's own GEMDOS's TO THAT CALL."""
    made = fsl.replay_calls(image)
    script = machine_of(woken.same)[2]
    assert tuple(call.function for call in made) == script.functions, (
        f"the woken session called GEMDOS {[f'{call.function:#x}' for call in made]} where the script it was answered "
        f"from is of {[f'{function:#x}' for function in script.functions]}")
    other = [f"call {nth} ({call.function:#x}): handed {call.frame.hex()}, the script's {frame.hex()}"
             for nth, (call, frame) in enumerate(zip(made, fsl.frames_as_recorded(script))) if call.frame != frame]
    assert not other, (f"the woken session handed GEMDOS other frames than the calls its script's answers were given "
                       f"to: {'; '.join(other)}")


def spans_differing_from_never_waited_for(woken, image, visible):
    """The spans of `visible` (`(address, size)`: the selector's own memory, what it hands back, the screen) over
    which `image` is NOT what `same`'s ROM run over the staged disk left: their addresses, in order."""
    script = machine_of(woken.same)[2]
    return [at for at, size in visible if bytes(image[at:at + size]) != script.memory[at:at + size]]


def vet_it_ends_as_never_waited_for(woken, image, visible):
    """...AND IT ENDS AS THE SAME USER NEVER WAITED FOR ENDS: over `visible`, `image` is what `same`'s ROM run over
    the staged disk left. CLAIMED ONLY OF A SESSION OVER `same`'S OWN MACHINE (`woken.running is None`): asked of one
    over another machine it is refused as a question, not answered."""
    assert woken.running is None, (
        "a session over another machine than `same`'s is not claimed to end as `same` ends: pin what it differs by "
        "(`spans_differing_from_never_waited_for`)")
    differ = [f"{at:#x}" for at in spans_differing_from_never_waited_for(woken, image, visible)]
    assert not differ, f"the woken session differs from the same user never waited for in the spans at {differ}"


def held_through_its_wake(woken, visible):
    """`woken` AT TIER 1 (`aes_event.held_through_its_wake`): the C through the host's model, the door bound, held to
    the ROM's own run through its dispatcher — and that run's premises held on the image they share. The
    `aes_switching.CompanionRun`."""
    ran = aes_event.held_through_its_wake(woken_row(woken))
    vet_its_gemdos_calls(woken, ran.image)
    vet_it_ends_as_never_waited_for(woken, ran.image, visible)
    return ran
