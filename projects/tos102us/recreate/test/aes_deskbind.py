"""THE DESK'S AES BINDINGS AT THEIR ARRIVALS — the signatures, the arrivals and the rows of `test_desk_bind.py`
(`src/desk/deskbind.c`: the forty routines `$fddde6..$fde4ff` and desk_wait `$fe1bdc`; band 6 wave 1a, unit D).

HELD AT TIER 1, NOTHING BOUND. No routine here has a table entry, a registry row or a price: each is the C core
against the ROM's own routine on the host library, over A MACHINE A ROM RUN MADE.

  * AN ARRIVAL (`arrival`) is a chain of the hands (`aes_desk.CHAINS`: a user's acts on the ROM's own machine) — or
    the DESKTOP.INF machine's own boot — STOPPED AT THE BINDING'S FIRST INSTRUCTION, where the desk's own caller calls
    it: `aes_boot.continued(..., until=)` over each step whose profile says the routine was entered, and from that
    stop to the next arrival for the n-th. What it holds: every byte of RAM there, the registers, the frame the
    desk's caller pushed (the arguments are READ OFF IT, by the binding's declared signature) and the address the call
    returns to. Nothing is poked.
  * A CASE is the ROM's binding and its C twin FROM THAT ENTRY, on the harness's stack, as a handler's arrival is
    (`aes_gemctrl`): every binding but two ends on `dsptch`, so every case is A ROW THAT SWITCHES (`row_of`, `held`:
    `aes_switching.companion` — the C through the host's scheduler held to the ROM's scheduled run with NOTHING
    dropped), a door user's where its routine reaches the event layer. The two leaves that never yield (appl_init,
    appl_bvset) are plain differentials (`plain`).
  * THE ROM'S OWN RUN IN PLACE (`returned_in_place`): the machine continued from the arrival to the address the call
    returns to, on the desk's own stack — what the binding leaves its ROM caller in D0 and A0 there.
  * WHAT THE C ANSWERS AND WHAT IT DOES NOT (`answer_class`): held to the ROM's D0.w, or one of two named
    divergences; WHO READS A BINDING'S ANSWER is read off every call site of the ROM's text (`answer_readers`).
"""
import bisect
import functools
import re
import struct
import sys
from collections import namedtuple
from pathlib import Path

from harness import BASE_IMAGE, addrs

import aes
import aes_boot
import aes_desk
import aes_event
import aes_gemctrl
import aes_switching as switching
import case
import layouts
import rom_data
import routines
import transcription
import vdi

BUS = aes_boot.BUS
WORD, LONG, IMAGE = vdi.WORD_ARG, vdi.LONG_ARG, vdi.IMAGE_ARG
WORD_BYTES, LONG_BYTES = aes.WORD_BYTES, aes.LONG_BYTES
RECT = (WORD,) * 4
MOBLK = (WORD,) * 5
PREFIX = "AES_ROM_DESK_"
# The bindings' own header's constants (`include/desk/deskbind.h`), read as every AES header's are.
HEADER = Path(__file__).resolve().parents[1] / "include" / "desk" / "deskbind.h"
CONSTANTS = layouts.parse_constants((HEADER,), known={**vdi.CONSTANTS, **aes.CONSTANTS})
# THE DESK'S ONE HOME (`include/desk/deskglobals.h`): its globals' offsets, an ANODE's layout, the desktop's root, the
# views and the sort keys — what every unit's battery reads them by, never a number spelt again.
GLOBALS_HEADER = HEADER.parent / "deskglobals.h"
DESK_GLOBALS = layouts.parse_constants((GLOBALS_HEADER,), known={**vdi.CONSTANTS, **aes.CONSTANTS})

# ---- THE SIGNATURES: `{binding: (the C core's answer, its frame's arguments in push order)}` ---------------------------------
# `None` where the core answers nothing: a binding of a `void` implementation (VOID_ANSWERS) or one whose ROM routine
# stores no answer of its own (NO_ANSWER_OF_ITS_OWN).
SIGNATURES = {
    "APPL_INIT": (aes.WORD_ANSWER, ()),
    "APPL_BVSET": (aes.WORD_ANSWER, (WORD, WORD)),
    "APPL_EXIT": (aes.WORD_ANSWER, ()),
    "APPL_WRITE": (aes.WORD_ANSWER, (WORD, WORD, LONG)),
    "EVNT_MULTI": (aes.WORD_ANSWER, (WORD, WORD, WORD, WORD, *MOBLK, *MOBLK, LONG, WORD, WORD, *(LONG,) * 6)),
    "EVNT_BUTTON": (aes.WORD_ANSWER, (WORD, WORD, WORD, *(LONG,) * 4)),
    "EVNT_DCLICK": (aes.WORD_ANSWER, (WORD, WORD)),
    "FORM_DO": (aes.WORD_ANSWER, (LONG, WORD)),
    "FORM_DIAL": (aes.WORD_ANSWER, (WORD, *RECT, *RECT)),
    "FORM_ALERT": (aes.WORD_ANSWER, (WORD, LONG)),
    "FORM_ERROR": (aes.WORD_ANSWER, (WORD,)),
    "FORM_CENTER": (None, (LONG, *(LONG,) * 4)),
    "GRAF_MOUSE": (None, (WORD, LONG)),
    "GRAF_RUBBOX": (None, (WORD, WORD, WORD, WORD, LONG, LONG)),
    "GRAF_MKSTATE": (None, (LONG,) * 4),
    "GRAF_GROWBOX": (None, (*RECT, *RECT)),
    "GRAF_SHRINKBOX": (None, (*RECT, *RECT)),
    "MENU_TNORMAL": (aes.WORD_ANSWER, (LONG, WORD, WORD)),
    "MENU_BAR": (None, (LONG, WORD)),
    "MENU_ICHECK": (aes.WORD_ANSWER, (LONG, WORD, WORD)),
    "MENU_IENABLE": (aes.WORD_ANSWER, (LONG, WORD, WORD)),
    "OBJC_OFFSET": (aes.WORD_ANSWER, (LONG, WORD, LONG, LONG)),
    "OBJC_ORDER": (None, (LONG, WORD, WORD)),
    "OBJC_FIND": (aes.WORD_ANSWER, (LONG, WORD, WORD, WORD, WORD)),
    "OBJC_ADD": (None, (LONG, WORD, WORD)),
    "OBJC_DRAW": (None, (LONG, WORD, WORD, *RECT)),
    "OBJC_CHANGE": (None, (LONG, WORD, WORD, *RECT, WORD, WORD)),
    "RSRC_GADDR": (aes.WORD_ANSWER, (WORD, WORD, LONG)),
    "SHEL_WRITE": (aes.WORD_ANSWER, (WORD, WORD, WORD, LONG, LONG)),
    "SHEL_GET": (aes.WORD_ANSWER, (LONG, WORD)),
    "SHEL_PUT": (aes.WORD_ANSWER, (LONG, WORD)),
    "WIND_CLOSE": (aes.WORD_ANSWER, (WORD,)),
    "WIND_DELETE": (aes.WORD_ANSWER, (WORD,)),
    "WIND_FIND": (aes.WORD_ANSWER, (WORD, WORD)),
    "WIND_UPDATE": (aes.WORD_ANSWER, (WORD,)),
    "WIND_CREATE": (aes.WORD_ANSWER, (WORD, *RECT)),
    "WIND_OPEN": (aes.WORD_ANSWER, (WORD, *RECT)),
    "WIND_GET": (aes.WORD_ANSWER, (WORD, WORD, *(LONG,) * 4)),
    "WIND_SET": (aes.WORD_ANSWER, (WORD, WORD, *RECT)),
    "WIND_CALC": (aes.WORD_ANSWER, (WORD, WORD, *RECT, *(LONG,) * 4)),
    "WAIT": (None, (WORD,)),
}
BINDINGS = tuple(PREFIX + short for short in SIGNATURES)
# ---- band 6 slice F1 ---- THE THREE BINDINGS HELD WHEN THE UNIT FLIPPED (`linef_table.LINKED_AND_NOT_FLIPPED`), each because
# its flip needs what the cut does not have (the slice's brief: such a routine stays held, reported) — TWO SINCE SLICE F2:
#   * (appl_exit — at both its arrivals (the viewer's `file: shown`, a launch) the screen manager stands parked where no
#     history of our build is known to leave it, so a row's takeover there is refused by name (`aes_takeover`): no row
#     of it can be priced. FLIPPED AT SLICE F2 AS ⚠️ VERIFIED-BUT-UNPRICED, the user's ruling of 2026-10-17:
#     `VERIFIED_UNPRICED_AT_F2`, below);
#   * evnt_multi — the desk parks in it, and its flip breaks TWO things, in this order (the F1 fix pass; both owed):
#     (1) THE LIVE-FRAME STAGING REFUSES FIRST: ctlmgr's rows lay the desk's live frames as the ROM's binding leaves
#     them (`aes_ctlmgr.lay_the_desk_s_live_frames`), and our C binding has no `link a6` — the desk's frame chain on
#     our machine is not the ROM's at `$a288` / `$a2bc` (measured: all eleven ctlmgr rows refused there). Owed: that
#     staging taught a flipped binding standing below deskmain's frame;
#     (2) BEHIND IT, THE ANSWER WORDS' RESIDUE: it copies ALL SIX answer words out to deskmain's frame after the yield,
#     the words of events that did not occur being each shore's frame residue (`$a34e` clicks_out, `$a350` key_out
#     under a menu wake — residue on both shores, no byte our C writes otherwise than the ROM's binding does; measured
#     `$a34f` `$01` / `$00` once (1) was taught). Owed: a by-nature class for those words, held two ways as the
#     unread D0/A0 class is — by reading (deskmain reads them under MU_BUTTON / MU_KEYBD alone) and by a run.
#     BOTH PIECES MADE AT SLICE H2 (the flip lands at F2c): (1) the desk's frames read over its text LESS ITS FLIPPED
#     ROUTINES' (`aes_ctlmgr.the_desk_s_text`), so under a flipped binding they begin at its caller's call; (2) the
#     words the ROM's binding copies out of answer words no store of its run reached (`aes_ctlmgr.ResidueCopies`, read
#     off each run where its binding copies them — the ROM's, and our C's once flipped — and excused only where both
#     runs copied residue and each end still holds it; by reading, the ROM's binding writes none of them before it parks);
#   * objc_draw — it yields by its own `dsptch` alone (no door entry: no door user), and a row that switches with no
#     door is modelled with no walked routine served (`aes_switch.modelled`): its C walks the tree through just_draw
#     (`$fe9a88`), which that fork does not stage — every one of its four rows' companions is refused there by name.
#     THE FIX PASS SERVED THAT FORK THE WALK (the event layer's binding with `aes.walkers()` beside its handed
#     routines, ~10 lines: every companion then passes, the table prices the four rows 0.81-0.84 and form_dial's INFO-1
#     0.84, nothing else moves) and found the flip needs ONE THING MORE: each of those five rows' second differential
#     on both blobs (`aes_switching.measured_on`, the battery's whole-run pin) is refused — our run leaves 27 (bench) /
#     33 (shipped) bytes on the dispatcher's stack BELOW the registered drop (`$8b34..` / `$8b2a..`; by its words a
#     BIOS trap's frame, PC `$fca7d4`), which the registrar derives only where the ROM's run stores. Tier 1 holds each
#     case (the door child serves the walk). AT SLICE H2: the fork's walk MADE (`aes_switch._served_with_no_door`), and
#     the "one thing more" MEASURED TO BE NONE — that refusal was the F1 script's instrument, the kit's own bench
#     (`isr.blob_named`), which puts nothing back; the battery's and the table's bench (`tier3.RomBench`) give our
#     dispatcher's stack back over the frames our run pushed, and the bytes are the idle's keyboard poll's BIOS frame,
#     the ROM's run's own at its drop's low end (`test_desk_bind.test_the_idle_s_key_poll_…`). Held until, and FLIPPED
#     at, slice F2c (both): none held since.
HELD_AT_F1 = ()
# ---- band 6 slice F2 (group G4) ---- A BINDING FLIPPED WITH NO ROW: ⚠️ VERIFIED-BUT-UNPRICED (the user's ruling of
# 2026-10-17: a routine faithful at Tier 1 whose arrivals no row kind reaches — as crit_err's and gem_entry's), each with
# why; Tier 1 holds its cases and the our-shore walk its flip (who-ran, the converse invariant).
VERIFIED_UNPRICED_AT_F2 = {
    PREFIX + "APPL_EXIT": "no row kind reaches its arrivals: at both (the viewer's `file: shown`, a launch) the screen manager "
                          "stands parked where no history of our build is known to leave it — every row's takeover there is "
                          "refused by name (`aes_takeover`)"}
for _short, (_restype, _frame) in SIGNATURES.items():
    aes.declare_alcyon(PREFIX + _short, _restype, (IMAGE, *_frame))

# THE ROM'S BINDING STORES D0 AFTER AN IMPLEMENTATION THAT IS `void` IN C: `{binding: the implementation}` — each case
# of one is a counted divergence (the module's docstring; the remedy is a ruling's, not this battery's).
VOID_ANSWERS = {
    "FORM_CENTER": "AES_ROM_OB_CENTER", "GRAF_MKSTATE": "AES_ROM_GR_MKSTATE", "MENU_BAR": "AES_ROM_MN_BAR",
    "OBJC_ORDER": "AES_ROM_OB_ORDER", "OBJC_ADD": "AES_ROM_OB_ADD", "OBJC_DRAW": "AES_ROM_OB_DRAW",
    "OBJC_CHANGE": "AES_ROM_OB_CHANGE"}
# ...and the bindings whose ROM routine stores NO answer: D0 at their return is whatever dsptch left.
NO_ANSWER_OF_ITS_OWN = ("GRAF_MOUSE", "GRAF_RUBBOX", "GRAF_GROWBOX", "GRAF_SHRINKBOX", "WAIT")
# The two that never reach the dispatcher: plain differentials.
NEVER_YIELD = ("APPL_INIT", "APPL_BVSET")
assert set(VOID_ANSWERS) | set(NO_ANSWER_OF_ITS_OWN) == {short for short, (restype, _f) in SIGNATURES.items() if restype is None}


def entry_of(short):
    return getattr(addrs, PREFIX + short)


# ---- AN ARRIVAL ---------------------------------------------------------------------------------------------------------------------
Arrival = namedtuple("Arrival", "short chain nth boot arguments returns_to ends_at budget")
Arrival.__doc__ = """The chain `chain` of the hands (or a boot: a key of BOOTS) stopped at its `nth` arrival (from 0) at the binding
`short`'s entry: the `Boot` there (its megabyte, its registers), the `arguments` the desk's caller pushed — read off
the frame by the binding's signature, words as unsigned — and the address the call `returns_to`; `ends_at`: the named
stop the step it was met in ends at (None: an idle), and that step's `budget`."""
THE_BOOT = "the boot of the DESKTOP.INF machine"
THE_ACCESSORY_BOOT = "the boot of the accessory machine (two accessories, the first with a menu entry)"
# A BOOT AN ARRIVAL IS MET IN: `{its name: () -> (the pre-init machine, its disk)}`.
BOOTS = {
    THE_BOOT: lambda: (aes_boot.inf_preinit(), aes_boot.inf_disk_of()),
    THE_ACCESSORY_BOOT: lambda: (aes_boot.accessory_preinit(),
                                 aes_boot.accessory_disk_of(*aes_gemctrl.ACCESSORY_MODES[aes_gemctrl.TWO_WINDOWS])),
}


def _steps_as_walked(chain_name):
    """`[(the boot a step began from, what it received, the stop it began at, the stop it ends at, its budget, its
    Stepped)]` for the chain's own steps, as `aes_desk.walked` took them."""
    chain = aes_desk.CHAINS[chain_name]
    machine = aes_desk.MACHINES[chain.after]() if chain.after in aes_desk.MACHINES else aes_desk.walked(chain.after).machine
    taken, stands_at = [], None
    for step, done in zip(chain.steps, aes_desk.walked(chain_name).steps):
        ends_at = aes_desk.STOPS[step.until] if step.until else None
        taken.append((machine.boot, tuple(step.hand(machine)), stands_at, ends_at, step.budget, done))
        machine, stands_at = aes_boot.Machine(done.boot), ends_at
    return taken


def _frame_arguments(short, ram, sp):
    """The arguments of `short` off the frame above the return address at `sp`."""
    arguments, at = [], sp + LONG_BYTES
    for argtype in SIGNATURES[short][1]:
        arguments.append(case.word_in(ram, at) if argtype is WORD else case.long_in(ram, at))
        at += vdi.ARG_BYTES[argtype]
    return tuple(arguments)


def stack_pointer(boot):
    """The stack pointer the stopped CPU runs on: the supervisor's (the AES and the desk run in supervisor state)."""
    assert boot.registers["sr"] & aes_boot.SR_SUPERVISOR, "the desk's code is reached in supervisor state"
    return boot.registers["isp"] & BUS


def _arrived(short, chain_name, nth, boot, ends_at, budget):
    sp = stack_pointer(boot)
    return Arrival(short, chain_name, nth, boot, _frame_arguments(short, boot.ram, sp), case.long_in(boot.ram, sp) & BUS,
                   ends_at, budget)


def _within_a_step(short, chain_name, first, ends_at, budget, found, count):
    """`found` grown by the arrivals at `short` from the first one's boot on, to the step's own end (where `continued`
    refuses the next by name: the machine idles, or — a step that ends at a named stop — spends its budget)."""
    entry = entry_of(short)
    found.append(_arrived(short, chain_name, len(found), first, ends_at, budget))
    while len(found) < count and ends_at is None:
        try:
            following = aes_boot.continued(found[-1].boot, (), budget, entry, entry)
        except aes_boot.Refused:
            return
        found.append(_arrived(short, chain_name, len(found), following, ends_at, budget))


@functools.cache
def arrivals(short, chain_name, count=1):
    """THE FIRST `count` ARRIVALS OF THE CHAIN `chain_name` AT THE BINDING `short`, over its steps in order — each
    step whose profile says the binding's first instruction ran is stopped at its first arrival there, and from that
    stop at the next, to the step's end. (A step that ends at a named stop gives its first arrival alone: nothing
    ends a run from there but its budget.) Fewer than `count` where the chain arrives fewer times. A key of BOOTS:
    that machine's own boot, stopped at its first arrival (`aes_boot.booted(until=)`)."""
    entry, found = entry_of(short), []
    if chain_name in BOOTS:
        boot = aes_boot.booted(*BOOTS[chain_name](), until=entry)
        return (_arrived(short, chain_name, 0, boot, None, aes_boot.BOOT_INSNS),)
    for boot, received, stands_at, ends_at, budget, done in _steps_as_walked(chain_name):
        if len(found) < count and entry in aes_desk.cycles_at(done.profile):
            _within_a_step(short, chain_name, aes_boot.continued(boot, received, budget, entry, stands_at), ends_at, budget,
                           found, count)
    return tuple(found)


def arrival(short, chain_name, nth=0):
    """The chain's `nth` arrival at the binding — refused by name where it arrives fewer times."""
    found = arrivals(short, chain_name, nth + 1)
    if len(found) <= nth:
        raise aes_boot.Refused(f"the chain {chain_name!r} arrives at the desk's {short.lower()} {len(found)} time(s): no "
                               f"arrival {nth}")
    return found[nth]


def returned_in_place(arrived):
    """THE ROM'S OWN RUN OF THE BINDING IN PLACE, from the arrival to the address its caller's call returns to, on the
    desk's own stack: the `Boot` there (D0 and A0 as the binding leaves them its ROM caller) — None where the machine
    idles first (a binding that waits for a hand)."""
    try:
        boot = aes_boot.continued(arrived.boot, (), arrived.budget, arrived.returns_to, entry_of(arrived.short))
    except aes_boot.Refused:
        return None
    assert stack_pointer(boot) == stack_pointer(arrived.boot) + LONG_BYTES, (
        f"{label_of(arrived)}: the run reached {arrived.returns_to:#x} on another frame than the arrival's own return")
    return boot


# ---- A CASE: the binding from its arrival, both shores ---------------------------------------------------------------------------
def machine_of(arrived):
    """The arrival's megabyte as a case's pokes — whole but the harness's window, which it holds as the snapshot does
    (`aes_desk.arrival_s_machine`: since band 6 slice F1 a case is a row too, and a row may poke no byte of a blob's span)."""
    return aes_desk.arrival_s_machine(arrived.boot.ram)


def label_of(arrived):
    return f"arrival {arrived.nth} of {arrived.chain!r} at the desk's {arrived.short.lower()}"


def row_of(arrived, at_idle=None, at_calls=None, label=None, answered=None):
    """THE ROW THAT SWITCHES a case of a yielding binding is (`aes_event.woken_row`, its door bound, its C's tree walks
    served): over the arrival's machine, its wait ended by `at_idle` / `at_calls`. `answered` False for a case whose
    answer is A NAMED DIVERGENCE (the caller's: `answer_class`); by default whether the core answers a word at all."""
    pokes = machine_of(arrived)
    if answered is None:
        answered = SIGNATURES[arrived.short][0] is not None
    return aes_event.woken_row(label or label_of(arrived), PREFIX + arrived.short, arrived.arguments, lambda: pokes,
                               at_idle or {}, at_calls, objects=True, answered=answered)


def held(row):
    """TIER 1 of a yielding binding's case: `aes_switching.companion`, nothing dropped. Its `CompanionRun`."""
    return switching.companion(row)


def the_rom_s_run(row):
    """THE ROM'S OWN SCHEDULED RUN of the row over its settled machine: `.d0` what the binding leaves its caller,
    `.memory` the megabyte, `.entered` the processes its dispatcher entered, `.idles`."""
    return switching.scheduled(row, switching.settled(row).pokes)


def plain(arrived, **kwargs):
    """...and of a leaf that never yields: the kit's differential over the arrival's megabyte. Its `aes.Result`."""
    return aes.run_function(PREFIX + arrived.short, arrived.arguments, machine_of(arrived), **kwargs)


# ---- WHAT THE ROM'S BINDING LEAVES ITS CALLER IN D0, AND WHERE THE C DOES NOT ----------------------------------------------------
# A case's answer is HELD (the companion compares the core's word with the ROM's D0.w) or is one of two NAMED
# DIVERGENCES, each counted by the battery and held to BE one (the two words differ, or the C has none):
#   * NO WORD IN C: the binding of a `void` implementation (VOID_ANSWERS);
#   * THE NESTED RELEASE'S LEFTOVER: wm_open and wm_set end on wm_update(END), and where the desk holds the screen's
#     lock ALREADY (it brackets its own work in wind_update) the ROM's unsync answers THE D0 IT WAS ENTERED WITH —
#     wm_opcl's w_setsize's address, wm_set's last word — which no C has (`aes/wmupdate.h`: the cores answer 0). On
#     wm_set it shows on the arms whose last call before the release leaves a non-zero word (WF_NEWDESK's store).
HELD, NO_WORD_IN_C, NESTED_RELEASE = "held", "no word in C (a void implementation)", "the nested release's leftover"
WMLIB = aes.header_constants("wmlib.h")
WMUPDATE = aes.header_constants("wmupdate.h")
SET_ARMS_THAT_LEAVE_A_WORD = (WMLIB["WF_NEWDESK"],)


def lock_depth(arrived):
    """How deep the screen's lock is held where the binding is called (wind_spb's count)."""
    return case.word_in(arrived.boot.ram, WMUPDATE["AES_WIND_SPB"] + WMUPDATE["SPB_COUNT"])


def answer_class(arrived):
    """WHICH OF THE THREE the case's answer is (above)."""
    if arrived.short in VOID_ANSWERS:
        return NO_WORD_IN_C
    nested = lock_depth(arrived) > 0
    if nested and (arrived.short == "WIND_OPEN" or arrived.short == "WIND_SET" and arrived.arguments[1] in SET_ARMS_THAT_LEAVE_A_WORD):
        return NESTED_RELEASE
    return HELD


# ---- WHO READS A BINDING'S ANSWER, BY READING THE CALLERS -------------------------------------------------------------------------
# From the instruction after every call of a binding the paths of the ROM's GEM text are followed — both arms of a
# conditional branch, a `bra` to its target — until D0 is READ (an operand that uses it: a `move.w d0,…`, a `tst`, a
# `cmp`), OVERWRITTEN (a `move` / `moveq` / `clr` into it), or the path reaches A CALL (D0 is an Alcyon callee's scratch:
# no callee is handed it) or THE ROUTINE'S RETURN — where the caller's own answer IS the binding's D0, and the question
# is asked again of every caller of that routine. A STORE COUNTS AS A READ (whether the local is used later is not
# followed): the reading errs toward "read".
# A BYTE MOVE INTO D0 IS NO OVERWRITE OF THE ANSWER (a word): the word's high byte lives on, so the path is followed
# on — and an `ext.w d0` behind it, which reads the byte just written and nothing of the answer, is what makes the
# word new (the ROM's three such pairs: `$fe1ca4`, `$fdb6f8`, `$fed9ec`).
READ, NOT_READ, RETURNED, LOST = "read", "not read", "returned as the caller's own answer", "the path leaves the listing"
BYTE_MOVE, EXTEND_THE_BYTE = "moveb", "extw"
_BRANCH = re.compile(r"^(b(?:ra|hi|ls|cc|cs|ne|eq|vc|vs|pl|mi|ge|lt|gt|le)[swl]?|db\w+) (?:%d\d,)?0x([0-9a-f]+)$")
_CALLS = re.compile(r"^(?:jsr|bsr[swl]?) 0x([0-9a-f]+)$")
_OVERWRITES_D0 = ("move", "lea")
D0 = "%d0"


@functools.cache
def _gem_text():
    """`({address: (length, text, the routine a call names or None, is it a return)}, {routine: [call sites]})` of
    the ROM's GEM text (`linef_dis.sweep`: a Line-F word one word, a call or a return)."""
    listed, calls = {}, {}
    for at, length, text in rom_data.linef_dis.sweep(*aes.AES_TEXT):
        word = case.word_in(BASE_IMAGE, at)
        called = aes.line_f_target(word) if text is None else None
        direct = _CALLS.match(text or "")
        if direct:
            called = int(direct.group(1), 16)
        returns = text is None and called is None or text == "rts"
        listed[at] = (length, text or "", called, returns)
        if called is not None:
            calls.setdefault(called, []).append(at)
    return listed, calls


def _routine_holding(at):
    starts = aes_desk.inventoried()
    return starts[bisect.bisect_right(starts, at) - 1]


def _operands(text):
    mnemonic, _space, operands = text.partition(" ")
    return mnemonic, [part.strip() for part in re.split(r",(?![^(]*\))", operands)] if operands else []


def _followed(at, seen, listed=None, low_byte_is_new=False):
    """`{(verdict, where)}` of the paths from the instruction at `at` — of the ROM's GEM text, or of `listed` (a
    listing a test hands). `low_byte_is_new`: a byte move has written D0's low byte on this path (above)."""
    listed = _gem_text()[0] if listed is None else listed
    verdicts = set()
    while at in listed and at not in seen:
        seen.add(at)
        length, text, called, returns = listed[at]
        mnemonic, operands = _operands(text)
        if called is not None:
            return verdicts | {(NOT_READ, at)}
        if returns:
            return verdicts | {(RETURNED, _routine_holding(at))}
        if any(D0 in operand for operand in operands):
            stored_into = operands[-1] == D0 and not any(D0 in each for each in operands[:-1])
            if mnemonic == BYTE_MOVE and stored_into:
                low_byte_is_new, at = True, at + length
                continue
            overwritten = (mnemonic.startswith(_OVERWRITES_D0) and stored_into or mnemonic.startswith("clr") and operands == [D0]
                           or mnemonic == EXTEND_THE_BYTE and operands == [D0] and low_byte_is_new)
            return verdicts | {(NOT_READ if overwritten else READ, at)}
        branch = _BRANCH.match(text)
        if branch and branch.group(1).startswith("bra"):
            at = int(branch.group(2), 16)
            continue
        if branch:
            verdicts |= _followed(int(branch.group(2), 16), seen, listed, low_byte_is_new)
        elif mnemonic == "jmp":
            return verdicts | {(LOST, at)}
        at += length
    return verdicts | ({(LOST, at)} if at not in listed else set())


def listed_at(at):
    """`(length, text)` of the instruction of the ROM's GEM text at `at`."""
    return _gem_text()[0][at][:2]


def answer_readers(routine, through=()):
    """WHERE THE ROM READS THE ANSWER OF `routine` (an address — a binding's, or any routine's the GEM text calls: unit
    O's four whose C answers less than D0 are asked here too): `{the reading instruction's address}`, through every
    caller that returns it as its own — refused by name where a path leaves the listing."""
    _listed, calls = _gem_text()
    readers = set()
    for site in calls.get(routine, ()):
        for verdict, where in _followed(site + _gem_text()[0][site][0], set()):
            assert verdict != LOST, f"${routine:x}'s answer: the path from its call at ${site:x} leaves the listing at ${where:x}"
            if verdict == READ:
                readers.add(where)
            elif verdict == RETURNED and where not in through:
                readers |= answer_readers(where, (*through, routine))
    return readers


def call_sites(short):
    """Every call of the binding in the ROM's GEM text."""
    return calls_of(entry_of(short))


def calls_of(routine):
    """Every call of the routine at `routine` in the ROM's GEM text, by the calling instruction's address."""
    return tuple(_gem_text()[1].get(routine, ()))


# ---- LINKED AND UNBOUND: THE ONE PIN OF EVERY UNIT OF THE DESK ---------------------------------------------------------------
# The desk is held unbound AS ONE (band 6 wave 1b's fix pass): a desk routine calls another desk routine in C by design
# (a group's routine its importers', unit D's bindings, unit O's leaves), so a unit's pin asks not "who outside my file
# refers to my cores" but "does anything that RUNS — anything outside the unbound desk — refer to a core of the desk".
# Every unit's pin asks it of every held core: a bound caller of any one reds them all.
BENCH = Path(__file__).resolve().parents[1] / "bench"


def _linef_table():
    sys.path.insert(0, str(BENCH))
    import linef_table                  # HERE, not at the module's top: the generator imports every battery's registry
    return linef_table


def held_cores():
    """The C cores of the routines LINKED AND NOT FLIPPED (`linef_table.LINKED_AND_NOT_FLIPPED`) — and of those linked
    and held with NO ENTRY OF THE TABLE to hold (`linef_table.LINKED_HELD_NO_TABLE_ENTRY`, R-W2-4)."""
    linef_table = _linef_table()
    return frozenset(routines.core_symbol(name)
                     for name in (*linef_table.LINKED_AND_NOT_FLIPPED, *linef_table.LINKED_HELD_NO_TABLE_ENTRY))


def unbound_closure(graph):
    """THE UNBOUND DESK in the call graph `graph`: the held cores, and every function ONLY THEY reach (a unit's static
    helper, a callee GCC kept out of line) — grown until it holds: a function that some function outside it refers to,
    or that nothing refers to, stays out."""
    unbound = set(held_cores())
    referrers = {}
    for function, targets in graph.items():
        for target in targets:
            referrers.setdefault(target, set()).add(function)
    grown = True
    while grown:
        held = {function for function, by in referrers.items() if function not in unbound and by and by <= unbound}
        grown, unbound = bool(held), unbound | held
    return frozenset(unbound)


# THE ONE CALL OF A HELD CORE FROM OUTSIDE THE UNBOUND DESK, DECLARED (band 6 slice B0, N1; the orchestrator's ruling
# R4): rom_ram's desk arm calls ini_tree as the ROM's does — the ROM's desk reaches it on a bound machine, and a halt
# there was a band-5 stand-in. GCC inlines the arm into `resource_part`: `{the referring function: the held cores}`.
# EMPTY SINCE BAND 6 SLICE F2: ini_tree flipped (unit I, group G1) — no core the arm calls is held, so nothing is
# exempted; `test_aes_rom_ram.py` holds the arm's call there, and the pin naming it were ini_tree held again.
REFERRED_BY_BAND_5 = {}
DESK_S_ARM, ITS_DESK_CALLEE = "resource_part", "aes_ini_tree"      # rom_ram's desk arm, and the desk core it calls


def bound_referrers(blob, names):
    """THE UNBOUND PIN, off `blob`'s own call graph (a call, a branch, an address taken): every core of `names` LINKED
    (refused by name where one is not) — and `{function: the held cores it refers to}` for every function OUTSIDE THE
    UNBOUND DESK (`unbound_closure`) that refers to ANY held core but as `REFERRED_BY_BAND_5` declares: none, while
    nothing is bound."""
    graph = transcription.call_graph(blob.elf)
    cores = {routines.core_symbol(name) for name in names}
    assert cores <= set(graph), f"not linked: {sorted(cores - set(graph))}"
    held, unbound = held_cores(), unbound_closure(graph)
    referred = {function: sorted(targets & held - set(REFERRED_BY_BAND_5.get(function, ())))
                for function, targets in graph.items() if function not in unbound}
    return {function: targets for function, targets in referred.items() if targets}


def _unbound_extents(blob):
    """`[(start, end)]` of the functions of the unbound desk in `blob`: their instructions, whose operands name the
    cores they call (a held core's `jsr` of another's absolute address)."""
    elf = blob.elf
    unbound = unbound_closure(transcription.call_graph(elf))
    labels = [(int(match.group(1), 16), match.group(2))
              for match in map(transcription.LISTED_FUNCTION.match, transcription.listing(elf).splitlines()) if match]
    nodes = transcription.nodes_of_labels(labels, transcription.symbol_origins(elf))
    ends = {symbol.start: symbol.start + symbol.size for symbol in transcription.symbol_table(elf) if symbol.size is not None}
    return [(address, ends[address]) for (address, _name), node in nodes.items() if node in unbound and address in ends]


def bound_longwords(blob, also=()):
    """...AND BY VALUE: the held cores (and the symbols `also`) whose address a longword of `blob`'s bytes holds, at
    every longword the link relocated (`transcription.address_longwords`: a table entry, a vector's holder; never an
    instruction's bytes that merely spell an address) — OUTSIDE THE INSTRUCTIONS OF THE UNBOUND DESK, where a held
    core's own `jsr abs.l` names its callee. None, while nothing is bound."""
    named = held_cores() | set(also)
    starts = {symbol.start: symbol.name for symbol in transcription.symbol_table(blob.elf) if symbol.name in named}
    assert set(starts.values()) == named, f"not linked: {sorted(named - set(starts.values()))}"
    extents, image = _unbound_extents(blob), blob.blob
    # (...and the band-5 functions REFERRED_BY_BAND_5 declares, each over the held cores it calls)
    sized = {symbol.name: symbol for symbol in transcription.symbol_table(blob.elf) if symbol.size}
    declared = [(sized[function].start, sized[function].start + sized[function].size, set(cores))
                for function, cores in REFERRED_BY_BAND_5.items() if function in sized]
    found = set()
    for at in sorted(transcription.address_longwords(blob.elf)):
        (value,) = struct.unpack_from(">I", image, at - blob.base)
        if value in starts and not any(lo <= at and at + LONG_BYTES <= hi for lo, hi in extents) and not any(
                lo <= at and at + LONG_BYTES <= hi and starts[value] in cores for lo, hi, cores in declared):
            found.add(starts[value])
    return sorted(found)
