"""How a case enters GEMDOS — the shared shape every `trap #1` battery in this project reads.

THREE ENTRIES, because GEMDOS is three layers and a case may need any of them:

* `trap.caller(selector, args)` and friends stage a CALLER and enter the trap #1 entry ($fc4f6e)
  through a hand-built exception frame. That is the only way to reach an exception handler, and the
  builders are `test/trap.py`'s under their own names — the frame a GEMDOS caller pushes is the same
  frame a BIOS caller pushes, word for word. What this module adds is the two shapes that are
  GEMDOS's own (`trap_caller`, `supervisor_caller_with_a_user_stack`) and a way to spell a LONG
  argument as the two words a caller really pushes.
* `dispatch_pokes(selector, words)` enters the C DISPATCHER ($fc94e4, or its slice at $fc973e)
  directly, with a `jsr` frame whose one argument is a pointer to the caller's own words. The words
  themselves are staged in this module's band, so a case can read back anything a handler wrote into
  them.
* a LEAF is an ordinary Alcyon stack-args routine and needs nothing from here: `case.word_args()`
  puts its arguments where `8(a6)` will find them. `long_words()` below is for the several GEMDOS
  leaves whose argument is a longword rather than a word.

WHAT A GEMDOS CALL LEAVES BEHIND, which is the fact every battery here has to know: the trap entry
frames the calling process's registers into ITS OWN BASEPAGE (`p_run`) and onto the caller's own
stack, rather than into the shared save area the BIOS entry uses. `process_frame()` below is that
layout, read out of the running machine rather than spelt, and `PROCESS_FRAME_FIELDS` is the span a
case has to declare to `test_boot_snapshot.py`.

THE HANDLER CALL IS A HOOK OFF TARGET. The dispatch table's handler longwords are ROM addresses and
the candidate is host code over a byte array, so `src/gemdos/dispatch.c` transfers control through
`recreate_call_gemdos_handler`, which `bind_handlers()` here binds to the reconstruction of whatever
handler the case's selector names. Keyed BY ADDRESS, exactly as `test/isr.py`'s vector hook is, so a
case whose selector reaches a handler nothing bound fails by naming it.
"""
import ctypes
import struct

from harness import (BASE_IMAGE, _lib, addrs, arm_candidate, candidate_image,
                     differential, emu, make_image, report)

import abi
import case
import staging
import trap
from opcodes import LOAD_ADDRESS_IMMEDIATE, SET_USER_STACK, TRAP_GEMDOS

# ---- the band this module owns, inside the one `staging.py` describes ---------------------------
# `trap.py` took +0x800..+0xc00 and `isr.py` the top from +0xd00; the pointer-argument batteries fill
# the bottom as far as +0x400. This is the gap between them, and it is deliberately half of what is
# free: the character-device and memory-manager waves need staging of their own.
GEMDOS_BAND_BYTES = 0x200
GEMDOS_BAND = staging.band(0x400, GEMDOS_BAND_BYTES, "test/gemdos.py")

# Where a DIRECT-ENTRY case puts the caller's words — the function number first, then the arguments,
# which is what the trap entry's `lea 50(frame),a0` hands the dispatcher. In COMPARED image rather
# than in the dropped stack band, so that a handler writing back into its own argument list (the
# redirected `Cconrs` does) is a fact the diff can see.
ARGUMENTS_AT = GEMDOS_BAND
ARGUMENTS_BYTES = 0x40
# ...and the second half, for a case that needs a buffer a GEMDOS call points at.
BUFFER_AT = GEMDOS_BAND + ARGUMENTS_BYTES
BUFFER_BYTES = GEMDOS_BAND_BYTES - ARGUMENTS_BYTES

WORD_BYTES = 2


def long_words(value):
    """A LONGWORD argument as the two words a caller pushes, high half first.

    GEMDOS takes longwords where the BIOS takes words — `Fsetdta(dta)`, `Super(ssp)`, `Pexec`'s three
    pointers — and every caller builder in this project pushes WORDS. Pushing `(high, low)` in that
    order lays the longword down big-endian, which is what makes `move.l 2(a0),d1` read it back.
    """
    return ((value >> 16) & 0xFFFF, value & 0xFFFF)


# ---- entering through the trap #1 entry ---------------------------------------------------------
# THE CALLERS THEMSELVES ARE `trap.py`'S, and a battery here calls them there. The frame a `trap #1`
# caller pushes is the frame a `trap #13` caller pushes — the function number word, the arguments
# under it, and the processor's own SR/PC above — so `trap.caller`, `trap.user_mode_caller`,
# `trap.user_stack`, `trap.caller_cost` and the addresses they stage at are used under their own
# names. Only the two shapes that are GEMDOS's OWN are here: a real `trap #1`, and the supervisor
# caller that has planted a user stack pointer first, which nothing but `Super` needs.


def trap_caller(selector, args=()):
    """A caller through a REAL `trap #1`, which can only ever reach the ROM's own entry through the
    machine's vector table — so it is the CONTROL the hand-built frame is checked against, never a
    way to run the reconstruction."""
    return trap.trap_caller(selector, args, opcode=TRAP_GEMDOS)


def supervisor_caller_with_a_user_stack(selector, args=()):
    """A SUPERVISOR caller that has planted a user stack pointer first.

    `Super(ssp)` from supervisor mode compares the two stack pointers and carries the caller's return
    address across to the user one when they differ — so the arm cannot be run by a caller that has
    left USP wherever the oracle's reset put it, which is address 0. The two-instruction prologue is
    `trap.user_mode_caller`'s own, and the rest is the ordinary supervisor caller: nothing is pushed
    between them, so the frame the caller builds is at the same depth either way.
    """
    return LOAD_ADDRESS_IMMEDIATE + trap.longword(trap.USER_STACK_AT) + SET_USER_STACK \
        + trap.caller(selector, args)


# ---- entering the dispatcher directly ------------------------------------------------------------

def argument_list(selector, words=()):
    """The caller's own words, staged at `ARGUMENTS_AT`: the function number, then the arguments.

    This is what the trap entry hands the dispatcher, and what `8(a6)` points at inside it. `words`
    are the argument WORDS in the order the caller pushed them, so a longword argument is its
    `long_words()` pair.
    """
    packed = struct.pack(f">{1 + len(words)}H", selector & 0xFFFF,
                         *(value & 0xFFFF for value in words))
    assert len(packed) <= ARGUMENTS_BYTES, "the staged argument list no longer fits its band"
    return {ARGUMENTS_AT: packed}


def dispatch_pokes(selector, words=(), pokes=None):
    """...and the whole poke set for a direct entry into `$fc94e4` or `$fc973e`: the words above,
    plus the POINTER to them where the dispatcher's own `8(a6)` will find it.

    `abi.FIRST_ARG` is that slot because `emu.run` plants a `jsr` frame at `emu.STACK_TOP`, which is
    exactly the frame the trap entry's `move.l a0,-(sp) / jsr` leaves.
    """
    return {**argument_list(selector, words), abi.FIRST_ARG: trap.longword(ARGUMENTS_AT),
            **(pokes or {})}


# ---- entering the dispatcher's SLICE, past the record it arms -------------------------------------
# `$fc973e` is inside a frame, so a case cannot simply enter there: `emu.run` forces A7 to
# `emu.STACK_TOP` and the dispatcher's locals live at negative displacements off an A6 that nothing
# has set — its pushes would land on top of them. A three-instruction trampoline opens the frame the
# ROM's own prologue opens and stands the one local in it that the arms past the record read back:
#
#     link    a6,#-54                 the dispatcher's own frame, from the harness's stack top
#     move.w  #<selector>,-34(a6)     ...and the selector its prologue had already decoded
#     jmp     $fc973e
#
# `link` leaves 8(a6) at `abi.FIRST_ARG` and the saved A6 and the sentinel where the closing
# `unlk`/`rts` need them, so the slice ends the run exactly as a whole routine does.
LINK_A6 = 0x4E56                        # link    a6,#<d16>
MOVE_W_IMMEDIATE_FRAME = 0x3D7C         # move.w  #<imm>,<d16>(a6)
JMP_ABSOLUTE_LONG = 0x4EF9              # jmp     <long>.l
# ...and what each of the three costs on a 68000, which is what a slice row's ORIGINAL column
# carries and our build — called as a C function — never runs. MEASURED rather than read off the
# tables: `test_gemdos_dispatch.py` and `test_gemdos_process_pexec.py` each drive their own
# trampoline under the oracle and hold the sum below to it.
LINK_CYCLES = 16
MOVE_W_IMMEDIATE_FRAME_CYCLES = 16
JMP_ABSOLUTE_LONG_CYCLES = 12

SUPER_CALLER_AT = BUFFER_AT + 0x80      # the stub `supervisor_caller_with_a_user_stack` stages
TRAMPOLINE_AT = BUFFER_AT + BUFFER_BYTES - 0x20
TRAMPOLINE_BYTES = 0x10
assert TRAMPOLINE_AT + TRAMPOLINE_BYTES <= GEMDOS_BAND + GEMDOS_BAND_BYTES

# Where the dispatcher's stack pointer stands once that `link` has run, which is the one thing a case
# needs in order to read back the ARGUMENT WORDS it pushed in front of a handler: `link` saves A6 at
# `STACK_TOP - 4` and drops the stack by the frame, and nothing between `$fc973e` and the `jsr`
# pushes anything else.
DISPATCHER_FRAME_AT = emu.STACK_TOP - 4
DISPATCHER_SP = DISPATCHER_FRAME_AT - addrs.GEMDOS_DISPATCH_FRAME_BYTES


def slice_trampoline(target, frame_bytes, selector=None):
    """A slice stub and what it COSTS: `(bytes, (instructions, cycles))`.

    TWO SHAPES, and `selector` is what picks between them. Given one, this is the three instructions
    above — the dispatcher's, which needs the selector its own prologue had already decoded standing
    in the frame, at the dispatcher's own local offset. Without one it is the two a routine whose
    locals nothing past the entry reads needs: `Pexec` past its record is that
    (`test/gemdos_process.py`).

    ONE BUILDER FOR BOTH, because `bench/tier3.py` reads the cost off it per trampoline: two builders
    meant two hand-written cost constants, and a stub whose shape changed without its number is a row
    netted by an entry nobody ran.
    """
    stub = struct.pack(">Hh", LINK_A6, -frame_bytes)
    insns, cycles = 1, LINK_CYCLES
    if selector is not None:
        stub += struct.pack(">HHH", MOVE_W_IMMEDIATE_FRAME, selector & 0xFFFF,
                            addrs.GEMDOS_DISPATCH_SELECTOR_LOCAL)
        insns, cycles = insns + 1, cycles + MOVE_W_IMMEDIATE_FRAME_CYCLES
    stub += struct.pack(">HI", JMP_ABSOLUTE_LONG, target)
    return stub, (insns + 1, cycles + JMP_ABSOLUTE_LONG_CYCLES)


def dispatcher_trampoline(selector):
    """...and this module's own use of it: `$fc973e`, entered with `selector` in the frame."""
    stub, cost = slice_trampoline(addrs.GEMDOS_DISPATCH_SELECTOR,
                                  addrs.GEMDOS_DISPATCH_FRAME_BYTES, selector=selector)
    assert len(stub) <= TRAMPOLINE_BYTES, "the slice trampoline outgrew the band reserved for it"
    return stub, cost


def slice_pokes(selector, words=(), pokes=None):
    """...and the whole poke set for a slice case: the trampoline, the argument list and the
    pointer to it."""
    return {TRAMPOLINE_AT: dispatcher_trampoline(selector)[0],
            **dispatch_pokes(selector, words, pokes)}


def rom_descriptor(selector):
    """The ARGUMENT DESCRIPTOR the ROM's own table holds for `selector`, read out of the captured
    image — which is what makes a claim about "the three selectors with bit 7" a claim about this
    ROM rather than a list somebody typed."""
    return case.word_in(BASE_IMAGE, addrs.GEMDOS_FUNCTION_TABLE
                        + selector * addrs.GEMDOS_RECORD_BYTES
                        + addrs.GEMDOS_RECORD_DESCRIPTOR)


def rom_handler(selector):
    """...and the HANDLER longword the same record holds — the ROM address the dispatcher `jsr`s and
    therefore the key `bind_handlers` is keyed by."""
    return case.long_in(BASE_IMAGE, addrs.GEMDOS_FUNCTION_TABLE
                        + selector * addrs.GEMDOS_RECORD_BYTES)


def run_candidate_only(call, pokes=None, handlers=None, io_seed=None):
    """Run `call(lib, buf)` on a freshly armed candidate with NO oracle, and answer `(ret, image)`.

    For the two claims in this wave that no differential can make, because the arm runs into
    something the ORIGINAL would do and the reconstruction deliberately does not: the dispatcher's
    fall-through to a FILE handler (the ROM's own `Fread`, which is the file system's), and
    `Pexec`'s copy of the outer termination record (the ROM arms a new one two instructions later,
    which is the hole `test_gemdos_dispatch.py` measures). The ORACLE's half of each is its own
    case; this is the CANDIDATE's, and without it those arms have no case at all on this side.

    `arm_candidate` is the same block `harness.differential` runs before each of its candidate
    passes — public for exactly this (`harness.py`), so a hand copy here cannot go stale.
    """
    bind_handlers(handlers or {})
    buf = candidate_image(make_image(pokes))
    arm_candidate(io_seed=io_seed)
    _new_pass()
    returned = call(_lib, buf)
    assert _lib.g_os_refusal_count() == 0, (
        f"the candidate made {_lib.g_os_refusal_count()} refused os_* call(s) — this run proves "
        f"nothing; declare the addresses it read")
    assert_every_handler_was_bound()
    return returned, bytes(buf)


def run_slice(selector, words=(), pokes=None, handlers=None):
    """One dispatch, entered at `$fc973e` through the trampoline, with `handlers` bound.

    ONE POLICY FOR EVERY SLICE CASE, which is why this is here and not in a battery: two copies had
    drifted into two — one poisoned and reported an unbound handler, the other did neither — so
    whether a case would notice the reconstruction SKIPPING a store, or answering a handler nobody
    staged with a fabricated 0, depended on which module its author copied from. Poisoning is on
    (these are whole-function runs over staged image) and the unbound-handler ledger is always
    reported.
    """
    bind_handlers(handlers or {})
    staged = slice_pokes(selector, words, pokes)

    def glue(lib, buf):
        return lib.gemdos_dispatch_selector(buf, ARGUMENTS_AT)

    diffs, info = differential(TRAMPOLINE_AT, {"a5": 0, "_pokes": staged}, recording(glue),
                               poison=True)
    assert not diffs, report(diffs)
    assert_every_handler_was_bound()
    case.assert_result_is_d0(info)
    return info


# HOW A TIER 3 ROW GETS FROM THAT TRAMPOLINE BACK TO THE ROUTINE IT IS ABOUT. `bench/tier3.py` looks
# a row's `CALL` entry up by the ROM routine its ENTRY belongs to, and a slice case's entry is a stub
# in this band — so the registry needs the same mapping `test/isr.py` gives its handler trampolines.
ROUTINE_OF_TRAMPOLINE = {TRAMPOLINE_AT: addrs.GEMDOS_DISPATCH_SELECTOR}

# ...and what the trampoline COSTS, out of the one builder above rather than written down beside it:
# `link` + `move.w #imm,<d16>(a6)` + `jmp <long>.l`, which
# `test_gemdos_dispatch.py::test_the_slice_trampoline_costs_what_its_rows_are_net_of` measures.
SLICE_ENTRY_COST = dispatcher_trampoline(0)[1]


def pushed_arguments(final, argument_bytes):
    """The words the dispatcher copied in front of the handler, read back out of the run's stack.

    They sit directly below `DISPATCHER_SP`, which is the only place they can: the four argument
    arms push and then `jsr`, with nothing in between. In the band the diff drops, so this is a
    claim a battery makes about the ORACLE's run rather than a compared byte.
    """
    return [int.from_bytes(bytes(final[at:at + WORD_BYTES]), "big")
            for at in range(DISPATCHER_SP - argument_bytes, DISPATCHER_SP, WORD_BYTES)]


# ---- reaching the BIOS: the `trap #13` frame this wave declares -----------------------------------
#
# THE ONE THING A CASE HERE DECLARES THAT NO OTHER BATTERY IN THIS PROJECT DOES: `savptr`.
#
# A GEMDOS routine reaches the BIOS through `GEMDOS_BIOS_TRAMPOLINE`, which takes the machine's own
# `trap #13`; the ROM's trap dispatcher then pushes a 46-byte register-save frame below `savptr`
# ($4a2) and pops it again on the way out. The HOST build of the reconstruction calls `bios_bconout`
# and its siblings directly (`include/bcon.h`) — there is no trap, so there is no frame — and those
# 46 bytes are the one part of the image the two sides cannot agree about.
#
# They are not excluded from the comparison. `savptr` is an ordinary writable system variable, so a
# case POKES IT into the band the differential already drops — the run's own stack band — exactly as
# it pokes a random seed or a ring's head. The frame then lands in memory that is scratch for both
# sides by construction, and every other byte of the image is compared as usual, the BIOS driver's
# own writes included.
#
# TWO THINGS KEEP THAT HONEST, and both are the harness's rather than this file's prose:
#
#   * the frame's bytes are POKED (`FRAME_FILL`), because `harness._stray_stack_writes` refuses any
#     oracle write in the lower half of the dropped band that the case did not declare. So the
#     declaration is checked, and a frame landing anywhere else in the band reddens;
#   * ONE frame deep is a claim, and it is the same check that holds it: these routines make their
#     BIOS calls one after another, never nested, so nothing ever pushes a second frame. A day when
#     something does is a stray write naming the address, not a silent pass.
#
# AND NOTHING THAT STAGES THIS MAY POISON. `case.run`'s attribution pass pre-inverts every byte the
# oracle wrote and re-runs both cores — and the oracle writes `savptr` itself, twice, on every one of
# these calls. An inverted `savptr` sends the ROM's next save frame to an address the case never
# chose and never staged, so the pass would fail for a reason that is about the pass. What stands in
# for it is staging: `FILL` is written under every field a case expects the routine to store.

# Far enough below `emu.STACK_TOP` that the run's own frames (a leaf, the editor, the trampoline and
# the 68000's exception frame — a few dozen bytes) never reach it, and far enough above
# `emu.STACK_GUARD_LO` that the whole frame stays inside the band `harness.diff_spans()` drops.
SAVPTR_BELOW_TOP = 0x600
SAVPTR_AT = emu.STACK_TOP - SAVPTR_BELOW_TOP
FRAME_AT = SAVPTR_AT - addrs.TRAP_SAVE_FRAME_BYTES
FRAME_FILL = 0x5A

# Said as assertions rather than as the paragraph above: "far enough" stops being true when a
# constant on either side moves, and nothing reads prose. Below: the whole frame is inside the
# dropped band. Above: it is clear of the depth `emu.STACK_SCRATCH` says a call frame may reach,
# which is also the cutoff `_stray_stack_writes` uses, so the frame is declared rather than free.
assert emu.STACK_GUARD_LO <= FRAME_AT
assert SAVPTR_AT <= emu.STACK_TOP - emu.STACK_SCRATCH

# A byte no field these routines write can be left holding: attribution, in place of the poison pass
# above. $A5 is `vt52.CANARY`'s value for the same reason.
FILL = 0xA5


def machine(pokes=None):
    """`savptr` where the frame belongs, the trampoline's return slot filled, and the case's own.

    The trampoline slot is filled rather than left alone for the attribution reason above: it is a
    longword EVERY GEMDOS routine that reaches the BIOS stores, and the snapshot's own value there
    would otherwise be one a skipped store could hide behind.
    """
    return {addrs.SYSVAR_SAVPTR: struct.pack(">I", SAVPTR_AT),
            FRAME_AT: bytes([FRAME_FILL]) * addrs.TRAP_SAVE_FRAME_BYTES,
            addrs.GEMDOS_BIOS_RETURN_SLOT: bytes([FILL]) * 4,
            **(pokes or {})}


# The trampoline's own opcode, so that the longword a run parks can be checked to BE a return from
# a `jsr` to it rather than taken on trust. `4eb9` is `jsr <abs.l>`.
JSR_ABSOLUTE_LONG = b"\x4e\xb9"
JSR_BYTES = len(JSR_ABSOLUTE_LONG) + 4
JSR_TRAMPOLINE = JSR_ABSOLUTE_LONG + addrs.GEMDOS_BIOS_TRAMPOLINE.to_bytes(4, "big")


def bios_call_site(info):
    """WHERE the run's last BIOS call returned to, checked against the ROM's own instruction stream.

    `GEMDOS_BIOS_TRAMPOLINE` pops its return address into `GEMDOS_BIOS_RETURN_SLOT` before taking
    the trap, so the longword left there names the instruction after a `jsr` to it. The
    reconstruction stores the same longword from a named constant on both builds, and this is what
    says that constant is really such a site: the six bytes before it must be that `jsr`.

    A KeyError here means the run reached the BIOS not at all, which is a case's claim in its own
    right — `test_cconis_answers_yes_for_a_record_gemdos_itself_queued_and_asks_no_one` makes the
    opposite one by checking the address is absent from the write ledger.
    """
    from harness import BASE_IMAGE

    site = case.written_long(info, addrs.GEMDOS_BIOS_RETURN_SLOT)
    assert bytes(BASE_IMAGE[site - JSR_BYTES:site]) == JSR_TRAMPOLINE, (
        f"{site:#x} is not the address after a `jsr GEMDOS_BIOS_TRAMPOLINE` — the reconstruction "
        f"parked a return site the ROM has no call at")
    return site


# ---- the running process -------------------------------------------------------------------------

def basepage():
    """`p_run` in the captured snapshot — the basepage of whatever the desktop was running.

    Read out of the machine rather than written down, for `trap.save_area_top`'s reason: it is state
    the boot and the desktop set, and a case that spelt it would be describing another machine the
    day the snapshot moved.
    """
    from harness import BASE_IMAGE

    return case.long_in(BASE_IMAGE, addrs.GEMDOS_P_RUN)


BASEPAGE = basepage()

# Every field this wave's cases READ or POKE, as (address, bytes, what) — the shape
# `test_boot_snapshot.py`'s `CASE_FIELDS` takes, which is how the snapshot's mask is checked against
# the bytes a case actually rests on. The process register frame the trap entry builds is the widest.
PROCESS_FRAME_FIELDS = (
    (BASEPAGE + addrs.BASEPAGE_DTA, 4, "the DTA pointer Fgetdta reports and Fsetdta stores"),
    (BASEPAGE + addrs.BASEPAGE_HANDLES, addrs.BASEPAGE_STANDARD_HANDLES,
     "the standard handles the dispatcher's redirection consults"),
    (BASEPAGE + addrs.BASEPAGE_CURDRV, 1, "the current drive Dgetdrv reports and Dsetdrv stores"),
    (BASEPAGE + addrs.BASEPAGE_SAVED_D0,
     addrs.BASEPAGE_SAVED_FRAME + 4 - addrs.BASEPAGE_SAVED_D0,
     "the process register frame the trap #1 entry builds"),
)


# ...and the fields that are not in the basepage: GEMDOS's own clock words, the call counter and the
# termination record. One tuple with the four above, so the orchestrator splats one name.
CASE_FIELDS = PROCESS_FRAME_FIELDS + (
    # Declared for the WHOLE wave rather than per group: the console leaves read it for their
    # standard handle and `gemdos_md_alloc` stamps it into `m_own`, and one span in two group
    # modules is two widths to keep right.
    (addrs.GEMDOS_P_RUN, 4, "the pointer to the running process's basepage"),
    (addrs.GEMDOS_DATE, 2, "GEMDOS's own date word, which Tgetdate reports and Tsetdate stores"),
    (addrs.GEMDOS_TIME, 2, "...and its time word"),
    (addrs.GEMDOS_CALL_DEPTH, 2, "the call counter the dispatcher clears and bumps"),
    (addrs.GEMDOS_TERMINATION_JMPBUF, 12, "the process-termination record the dispatcher arms"),
)


def dta_poke(dta):
    """Put a DTA pointer in the running process's basepage."""
    return {BASEPAGE + addrs.BASEPAGE_DTA: trap.longword(dta)}


def current_drive_poke(drive):
    """...and a current drive, as the single byte the basepage keeps it in."""
    return {BASEPAGE + addrs.BASEPAGE_CURDRV: bytes([drive & 0xFF])}


def standard_handles_poke(handles):
    """...and the six standard handles, as signed bytes. `handles` may be shorter than six; what it
    does not name is left as the snapshot has it."""
    return {BASEPAGE + addrs.BASEPAGE_HANDLES + index: bytes([value & 0xFF])
            for index, value in enumerate(handles)}


def date_poke(date):
    """GEMDOS's own date word, which is the whole input of `Tgetdate`."""
    return {addrs.GEMDOS_DATE: trap.word(date)}


def time_poke(time):
    """...and its time word, `Tgettime`'s."""
    return {addrs.GEMDOS_TIME: trap.word(time)}


# ---- the two host hooks --------------------------------------------------------------------------
# `src/gemdos/dispatch.c` calls a HANDLER it cannot execute, and `src/gemdos/leaves.c` publishes the
# clock through a `trap #14` it cannot take. Both are bound here, once per process, to the shape
# `test/isr.py` binds its vector hook in: a ctypes trampoline the module holds for the process's
# lifetime, dispatching by address, recording what it was asked for so that a case can refuse a call
# nothing staged.

CALL_HANDLER = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.POINTER(ctypes.c_uint8),
                                ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint16)
PUBLISH_CLOCK = ctypes.CFUNCTYPE(None, ctypes.POINTER(ctypes.c_uint8),
                                 ctypes.c_uint16, ctypes.c_uint16)

_HANDLERS = {}          # ROM handler address -> handler(buf, arguments, argument_bytes) -> result
# The ordered (handler, arguments, argument_bytes) of ONE candidate run — the PLAIN pass's, which is
# the one every claim is about. A differential with `poison` on runs the candidate twice, and the
# attribution pass's calls are not the case's: poisoning an output can steer the reconstruction down
# another arm entirely, so an accumulating list would hold a mixture nobody could read. `test/isr.py`
# splits its vector calls the same way and for the same reason.
HANDLER_CALLS = []
_PASSES = []            # every pass's list, the first of which IS `HANDLER_CALLS`
UNBOUND_CALLS = []      # ...and the handlers nothing bound, which a case reports as its own failure
CLOCK_PUBLICATIONS = []  # (date, time) — the door `recreate/STATUS.md` records as not reconstructed


def _new_pass():
    """Start recording a candidate run — `recording()` below is how a battery reaches it, since the
    glue is the only place that knows where one pass ends and the next begins."""
    _PASSES.append(HANDLER_CALLS if not _PASSES else [])
    return _PASSES[-1]


def recording(glue):
    """`glue` with a fresh call list per candidate run — see `_PASSES`."""
    def one_pass(lib, buf):
        _new_pass()
        return glue(lib, buf)
    return one_pass


def _call_handler(buf, handler, arguments, argument_bytes):
    # A ctypes callback cannot raise through to its C caller, so a refusal is RECORDED here and the
    # battery reports it (`assert_every_handler_was_bound` below). A call from OUTSIDE a pass is one
    # of those: nothing staged anything, so answering it with the last case's handler would be the
    # worst answer available.
    if not _PASSES:
        UNBOUND_CALLS.append(handler)
        return 0
    if len(_PASSES[-1]) < case.CALLS_MAX:
        _PASSES[-1].append((handler, arguments, argument_bytes))
    effect = _HANDLERS.get(handler)
    if effect is None:
        UNBOUND_CALLS.append(handler)
        return 0
    return effect(buf, arguments, argument_bytes)


def _publish_clock(_buf, date, time):
    CLOCK_PUBLICATIONS.append((date, time))


_HANDLER_HOOK = CALL_HANDLER(_call_handler)
_CLOCK_HOOK = PUBLISH_CLOCK(_publish_clock)
ctypes.c_void_p.in_dll(_lib, "recreate_call_gemdos_handler").value = \
    ctypes.cast(_HANDLER_HOOK, ctypes.c_void_p).value
ctypes.c_void_p.in_dll(_lib, "recreate_publish_clock").value = \
    ctypes.cast(_CLOCK_HOOK, ctypes.c_void_p).value


def bind_handlers(handlers):
    """Bind `{rom_handler_address: effect}` for the runs a case is about to make, and clear the
    ledgers. `effect(buf, arguments, argument_bytes)` returns the handler's D0.

    The binding is global because the hook is a symbol in the `.so`, so a battery binds what it
    needs immediately before each case rather than once at import — which is also what keeps two
    batteries from silently sharing one table under `pytest -n auto`.
    """
    _HANDLERS.clear()
    _HANDLERS.update(handlers)
    _PASSES.clear()
    HANDLER_CALLS.clear()
    UNBOUND_CALLS.clear()
    CLOCK_PUBLICATIONS.clear()


def assert_every_handler_was_bound():
    """...and the refusal the callback could not raise: a handler the candidate reached that nothing
    staged. A case that hits this proved nothing — the reconstruction was answered with a 0."""
    assert not UNBOUND_CALLS, (
        f"the candidate called GEMDOS handler(s) "
        f"{', '.join(f'{handler:#x}' for handler in sorted(set(UNBOUND_CALLS)))} that no case bound "
        f"— bind them with `gemdos.bind_handlers`, or the run was answered with a fabricated 0")


def assert_the_clock_was_not_published():
    """The `Tsetdate`/`Tsettime` door: XBIOS `Settime` is not reconstructed, so a case that reached
    it is a case about a routine half of which does not exist (`recreate/STATUS.md`)."""
    assert not CLOCK_PUBLICATIONS, (
        f"the candidate published the clock {CLOCK_PUBLICATIONS} — XBIOS Settime is NOT "
        f"reconstructed, so this case has no oracle-side counterpart it could be compared against")


# ---- the registry ---------------------------------------------------------------------------------
# `test_boot_snapshot.VERIFIED_CASES` is the orchestrator's; a battery here appends its rows to
# `CASES` below, in that file's own seven-or-eight-field shape — the eighth is `stop_pc`, 0 for a
# routine that reaches its own `rts` — so that the splat is mechanical. The
# TRANSCRIPTION rows are separate for `trap.py`'s reason: `$fc4f6e` is proved by
# `RomBench.measure_transcription` and a C core by `harness.differential`, which are two relations.

CASES = []
TRANSCRIPTIONS = []
# ...and the cases that are VERIFIED but cannot be PRICED, which is a third list because
# `bench/tier3.py` fails on a `VERIFIED_CASES` row it cannot make a row for. A case belongs here when
# its differential is a CHECKPOINT — Tier 3 runs both sides to the routine's own `rts`, and a case
# that stops short of one has no second column. EMPTY as this wave lands: `Dsetdrv` was its only
# member, and it is priced now that the target build takes the ROM's own `trap #13` for the BIOS
# call it ends with (`src/gemdos/leaves.c`). The list stays because the next such routine will want
# it, and the claims that are about the CASE rather than about the table splat it
# (`test_boot_snapshot.py`).
UNPRICED = []


def register(name, entry, regs, pokes, psg_seed=None, io_seed=None, schedule=(), priced=True):
    """One `VERIFIED_CASES` row, recorded and returned so a battery can drive the same tuple.

    `priced=False` puts it in `UNPRICED` instead — same tuple, and still a case the snapshot mask
    has to be checked against, but no Tier 3 row (see above, and the battery that says why).
    """
    row = (name, entry, dict(regs), dict(pokes), psg_seed, io_seed, schedule)
    (CASES if priced else UNPRICED).append(row)
    return row


# How a transcription row names itself in the Tier 3 table, keyed by the blob symbol — `trap.LABELS`
# for this entry, which is what `bench/tier3.py`'s `_transcription_row` reads.
LABELS = {"gemdos_trap1": "GEMDOS trap #1"}


def register_transcription(name, symbol, caller_at, regs, pokes, cost):
    """...and one `trap.CASES`-shaped row for the trap #1 entry, whose relation is the second
    differential of Tier 3's numerator rather than `harness.differential`."""
    row = (name, symbol, caller_at, dict(regs), dict(pokes), cost)
    TRANSCRIPTIONS.append(row)
    return row


def entry_pokes(symbol, stub_at, stub, staged=None):
    """The pokes a staged-caller case makes: the stub, and the ENTRY it is to jump through, which is
    read off `addrs` from the blob symbol so that the two cannot name different handlers."""
    return {stub_at: stub, abi.FIRST_ARG: trap.longword(getattr(addrs, symbol.upper())),
            **(staged or {})}
