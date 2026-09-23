"""ENDING A PROCESS — `Pterm` ($fc8028), `Pterm0` ($fc8086), `Ptermres` ($fc7fd8) and the release
routine all three reach ($fc8092). `src/gemdos/process.c`.

    $fc803e  jsr   $fc4eac            ; Setexc($102, -1) — the TERMINATE VECTOR, read not written
    $fc8048  jsr   $fc4f0a            ; ...and called, with its own value as its argument
    $fc804e  jsr   $fc5092            ; the Mega ST battery clock, re-read (absent on a plain ST)
    $fc805a  move.l 36(a5),p_run      ; the PARENT becomes the running process...
    $fc8064  bsr   $fc8092            ; ...and everything the child owned is given back
    $fc8072  move.l d0,104(a0)        ; the exit code, into the PARENT's own D0 save slot
    $fc8076  jsr   $fc4fe8            ; the trap entry's EPILOGUE. Control does not come back.

NONE OF THE THREE RETURNS, so every case here is a CHECKPOINT: the ORIGINAL is stopped at that last
`jsr` and the host build of the core returns the exit code it has just planted
(`test/gemdos_process.py`, which says why, and why these rows are VERIFIED but UNPRICED).

WHAT THE CASES STAGE is a SECOND PROCESS — a basepage inside a TPA re-cut out of the snapshot's own
free block, with the memory descriptor charged to it, the snapshot's own basepage as its parent, and
whatever handles and directories the case is about. That is what makes "give back what this process
owns" a claim with two answers: the child's blocks move and the desktop's fourteen do not.

THE ONE THING `Pterm` DOES NOT DO is longjmp. The record at `$7ef4` is real and the dispatcher arms
it, but what jumps to it is the file system's critical-error abort ($fc5986 and four more), which
the dispatcher answers by comparing the value against `E_CHNG`. `Pterm` leaves through the epilogue
and `test_pterm_leaves_the_termination_record_alone` is what says so.
"""
import ctypes
import struct

import pytest

from harness import BASE_IMAGE, _lib, addrs, emu, make_image

import case
import gemdos
import gemdos_memory
import gemdos_process as process
import isr

for _name in ("gemdos_pterm", "gemdos_pterm0", "gemdos_ptermres"):
    getattr(_lib, _name).restype = ctypes.c_uint32
_lib.gemdos_release_process.restype = None
_lib.gemdos_resync_clock.restype = None

P_RUN = gemdos.BASEPAGE
A_DEVICE = -1
A_DIRECTORY_NODE = 2                    # what the captured machine's own process holds for drive A
ANOTHER_DIRECTORY_NODE = 1

# The exit codes the cases drive, and the one that matters: `clr.l d0 / move.w` ZERO-extends, so
# `Pterm(-1)` hands the parent $0000ffff where a sign extension would have handed it $ffffffff.
EXIT_CODES = (0, 1, 0x7FFF, 0xFFFF, 0x8000)


# ================================================================================================
# $fc5092 — the Mega ST battery clock
# ================================================================================================

def resync_pokes():
    return dict(gemdos.machine())


# Which pair of digits each field of the two DOS words is, and how far the pair is shifted once it
# is a number. The seconds are not shifted at all — the DOS time word counts TWO-SECOND units, which
# is the ROM's `asr.w #1`. Read off `src/gemdos/process.c`, whose own names these are.
CLOCK_FIELDS = (
    ("year", 0, addrs.GEMDOS_DATE_YEAR_SHIFT), ("month", 2, addrs.GEMDOS_DATE_MONTH_SHIFT),
    ("day", 4, 0), ("hour", 7, addrs.GEMDOS_TIME_HOUR_SHIFT),
    ("minute", 9, addrs.GEMDOS_TIME_MINUTE_SHIFT), ("second", 11, None),
)
DIGIT_TENS = 10


def _field(digits, at):
    return digits[at] * DIGIT_TENS + digits[at + 1]


def dos_words(digits):
    """The DOS date and time words the ROM builds out of thirteen BCD digits.

    THE FIELDS ARE ADDED, NOT OR-ED, which is the ROM's own `add.w` and is why this is arithmetic
    rather than a bit layout: two digits can spell a number wider than its field — a minute of 60 is
    what the probe itself leaves behind here — and the carry into the field above is part of the
    answer.
    """
    date = time = 0
    for name, at, shift in CLOCK_FIELDS:
        value = _field(digits, at)
        if name in ("year", "month", "day"):
            date = (date + (value << shift)) & 0xFFFF
        elif shift is None:
            time = (time + (value >> 1)) & 0xFFFF
        else:
            time = (time + (value << shift)) & 0xFFFF
    return date, time


@pytest.mark.parametrize("what,digits", (
    ("the ROM's own build date, at noon", process.A_TIME),
    ("a reading that shares no free digit with it", process.ANOTHER_TIME),
), ids=lambda arg: arg if isinstance(arg, str) else "")
def test_a_battery_clock_is_read_into_gemdos_s_own_date_and_time_words(what, digits):
    """THIRTEEN REGISTERS, READ TWICE, AND SIX PAIRS OF BCD DIGITS TURNED INTO TWO DOS WORDS. Which
    register is which digit (the year's tens are register 25, the seconds' units register 1), the
    two-second granularity of the time word, and the five field shifts — all of it at once, at two
    readings that share no digit.

    The expectation is computed from what the MODEL serves rather than from what the case asked for,
    which `test/gemdos_process.py` explains: three of the thirteen registers are write-through and
    read back the probe's own bytes, because the kit's I/O map has no bank selector and the real
    chip's do.
    """
    served = process.served(digits)
    info = process.run(addrs.GEMDOS_RESYNC_CLOCK,
                       lambda lib, buf: lib.gemdos_resync_clock(buf), resync_pokes(),
                       io_seed=process.battery_clock(digits), width=case.NO_RESULT)
    date, time = dos_words(served)
    assert case.written(info, addrs.GEMDOS_TIME, 2) == time
    assert case.written(info, addrs.GEMDOS_DATE, 2) == date


def test_the_two_readings_do_not_share_a_digit():
    """...which is what makes the pair above a claim about every field rather than about one. Said
    as a test so a later edit that made the two readings agree somewhere fails here, where the reason
    is written down, rather than quietly weakening the case above."""
    shared = [index for index, (a, b) in enumerate(zip(process.served(process.A_TIME),
                                                       process.served(process.ANOTHER_TIME)))
              if a == b]
    assert shared == [9, 10, 12], (
        "the two clock readings agree on a digit the probe does not force — one of them has stopped "
        "separating a field. 9, 10 and 12 are the three the probe's own write-through bytes fix.")


def test_the_clock_is_read_twice_and_the_two_readings_are_compared():
    """The ROM reads the whole chip into `$e94`, again into `$ea1`, and compares thirteen digits —
    because the clock can tick between two register reads and leave a time that never existed. Both
    buffers are ordinary low RAM, so the differential sees them: what the case can say is that the
    chip was read TWICE (26 digit reads, plus the probe's four) and that both buffers hold the same
    thirteen digits afterwards."""
    pokes = resync_pokes()
    info = process.run(addrs.GEMDOS_RESYNC_CLOCK,
                       lambda lib, buf: lib.gemdos_resync_clock(buf), pokes,
                       io_seed=process.battery_clock(), width=case.NO_RESULT)
    final = case.final_image(info, pokes)
    assert final[0x0E94:0x0E94 + 13] == final[0x0EA1:0x0EA1 + 13]
    assert len(case.hardware_reads(info)) == 2 * process.RTC_DIGITS + 4


def test_the_probe_writes_three_registers_before_it_reads_anything():
    """The ordered write ledger, which is the whole of what a store to a chip leaves: the mode
    register set to 9, then the two halves of the pattern, in that order and at those addresses —
    and then, once the chip has answered, the reset register, the run mode and the test register."""
    info = process.run(addrs.GEMDOS_RESYNC_CLOCK,
                       lambda lib, buf: lib.gemdos_resync_clock(buf), resync_pokes(),
                       io_seed=process.A_BATTERY_CLOCK, width=case.NO_RESULT)
    mode_at = process.RTC_BASE + process.RTC_MODE
    assert case.hardware_writes(info)[:6] == [
        (mode_at, process.RTC_MODE_PROBE),
        (process.PROBE_HIGH_AT, process.PROBE_PATTERN_HIGH),
        (process.PROBE_LOW_AT, process.PROBE_PATTERN_LOW),
        (process.RESET_AT, process.RTC_RESET_VALUE),
        (mode_at, process.RTC_MODE_RUN),
        (process.RTC_BASE + process.RTC_TEST, 0)]


@pytest.mark.parametrize("what,seed", (
    ("no chip at all", {process.PROBE_HIGH_AT: 0x00, process.PROBE_LOW_AT: 0x00}),
    ("the high half only", {process.PROBE_HIGH_AT: 0x0A, process.PROBE_LOW_AT: 0x00}),
    ("the low half only", {process.PROBE_HIGH_AT: 0x00, process.PROBE_LOW_AT: 0x05}),
    ("the right nibbles in the wrong register", {process.PROBE_HIGH_AT: 0x05,
                                                 process.PROBE_LOW_AT: 0x0A}),
), ids=lambda arg: arg if isinstance(arg, str) else "")
def test_a_machine_with_no_battery_clock_does_nothing_at_all(what, seed):
    """A claim about the ORACLE, and one of only two in this file — `test/gemdos_process.py` says
    why: a declaration that a store does not reach is the one form the kit's I/O map has not got, so
    the plain ST this snapshot was taken on cannot be the machine a DIFFERENTIAL runs over.

    What the claim still separates is the four ways the probe can fail: the routine comes back
    having written nothing but the three probe registers, and three of these four declarations get
    one half of the pattern right.
    """
    _final, writes, regs = emu.run(make_image(resync_pokes()), addrs.GEMDOS_RESYNC_CLOCK,
                                   {"a5": 0}, io_seed=seed)
    assert regs["ninsns"] > 0
    assert addrs.GEMDOS_TIME not in writes and addrs.GEMDOS_DATE not in writes
    assert len(regs["hw_writes"]) == 3, "the absent arm made the present arm's stores"


# ================================================================================================
# $fc8092 — everything a process owns, given back
# ================================================================================================

def release(child, pokes=None):
    staged = {**child.pokes, **case.long_args(child.basepage), **(pokes or {})}
    return process.run(addrs.GEMDOS_RELEASE_PROCESS,
                       lambda lib, buf: lib.gemdos_release_process(buf, child.basepage),
                       staged, width=case.NO_RESULT), staged


def test_the_release_puts_the_process_s_memory_back_on_the_free_list():
    """The fourth of the routine's four loops, and the one with a list to walk: every descriptor
    whose `m_own` names the process is unlinked from the ALLOCATED list and inserted into the free
    one, where it coalesces with its neighbour. The desktop's own fourteen are left alone."""
    child = process.stage_child(blocks=1)
    info, pokes = release(child)
    final = case.final_image(info, pokes)

    assert not process.owned_blocks(final, child.basepage), "a block the process owned survived it"
    assert len(gemdos_memory.allocated_list(final)) == len(gemdos_memory.allocated_list()), (
        "the desktop's own allocated blocks did not survive the release")
    assert len(gemdos_memory.free_list(final)) == 1, (
        "the freed TPA did not coalesce back into the block it was cut from")


def test_every_block_the_process_owns_goes_back_and_only_those():
    """Two blocks, driven so the walk has to keep going after the first one it unlinks — and a third
    span left owned by the RUNNING process, which must still be there afterwards."""
    child = process.stage_child(blocks=2)
    kept = child.staged.used[1]
    extra = {kept.md + addrs.MD_OWNER: struct.pack(">I", P_RUN)}
    child = child._replace(pokes={**child.pokes, **extra})

    info, pokes = release(child)
    final = case.final_image(info, pokes)
    assert not process.owned_blocks(final, child.basepage)
    assert kept.md in [block.at for block in process.owned_blocks(final, P_RUN)], (
        "the release took a block the DESKTOP owned")
    assert len(gemdos_memory.allocated_list(final)) == len(gemdos_memory.allocated_list()) + 1, (
        "the desktop's own blocks and the one it was given did not both survive")


def test_a_standard_handle_naming_a_descriptor_is_closed_before_the_table_is_walked():
    """THE ORDER OF THE FIRST TWO LOOPS IS A CLAIM. `p_uft` is closed first, and closing the last
    holder of a descriptor ZEROES ITS OWNER — so by the time the second loop looks for descriptors
    this process owns, that one is no longer one of them. A release that walked the table first
    would close it twice."""
    handle = addrs.GEMDOS_FIRST_FILE_HANDLE
    child = process.stage_child(handles=(-1, -1, -2, -3, handle, 0))
    child = child._replace(pokes={**child.pokes,
                                  **process.descriptor_poke(handle, A_DEVICE, child.basepage)})
    info, pokes = release(child)
    final = case.final_image(info, pokes)

    assert process.descriptor(final, handle).owner == 0
    assert process.descriptor(final, handle).references == 0
    # ...and it was closed ONCE: a second `Fclose` would have wrapped the count to $ffff.
    assert case.written(info, process.descriptor_at(handle) + process.HANDLE_REFCOUNT, 2) == 0


def test_a_descriptor_the_process_owns_but_no_handle_names_is_closed_by_the_table_walk():
    """...and the second loop's own reason to exist: a descriptor `Fdup` made and nothing `Fforce`d
    into `p_uft`. Driven with TWO holders, so what the walk leaves is a count of one rather than a
    freed slot — which is the only way to see that it called `Fclose` rather than zeroing it."""
    handle = 30
    child = process.stage_child()
    child = child._replace(pokes={**child.pokes,
                                  **process.descriptor_poke(handle, A_DEVICE, child.basepage,
                                                            references=2)})
    info, pokes = release(child)
    assert case.written(info, process.descriptor_at(handle) + process.HANDLE_REFCOUNT, 2) == 1
    assert process.descriptor(case.final_image(info, pokes), handle).owner == child.basepage


def test_a_descriptor_the_process_owns_that_names_nothing_answers_eihndl_and_survives():
    """A PROCESS THAT `Fdup`ED AN UNUSED SLOT, ending. `Fdup(4)` on a `p_uft` byte of 0 leaves a
    descriptor whose value is 0 and whose owner is the process, and the table walk below reaches it
    like any other — but `Fclose` of a handle that names NOTHING answers EIHNDL without storing
    anything ($fc51c0 answers 0; `src/gemdos/handles.c`), so the slot stays owned and counted while
    every other thing the process owned goes back.

    It is the arm a reconstruction is most likely to get wrong, because it looks like a close and
    is not one: the release reaches it whenever a program duplicates a standard handle it never
    opened, which the captured machine's own `p_uft[4]` and `p_uft[5]` are.
    """
    handle = 40
    child = process.stage_child(blocks=1)
    child = child._replace(pokes={**child.pokes,
                                  **process.descriptor_poke(handle, 0, child.basepage)})
    info, pokes = release(child)
    final = case.final_image(info, pokes)

    left = process.descriptor(final, handle)
    assert left.owner == child.basepage, "a descriptor naming nothing was released anyway"
    assert left.references == 1, "...or its count was dropped by a close that never happened"
    assert not process.owned_blocks(final, child.basepage), (
        "the release stopped at the refused handle instead of going on to the memory")


def test_a_descriptor_another_process_owns_is_left_alone():
    """The `cmpa.l 4(a0),a5` that makes the walk a walk BY OWNER: same table, same call, and a
    descriptor the desktop owns comes out untouched."""
    handle = 30
    child = process.stage_child()
    child = child._replace(pokes={**child.pokes,
                                  **process.descriptor_poke(handle, A_DEVICE, P_RUN,
                                                            references=2)})
    info, _pokes = release(child)
    assert process.descriptor_at(handle) + process.HANDLE_REFCOUNT not in info["writes"]


@pytest.mark.parametrize("curdir", ((A_DIRECTORY_NODE,),
                                    (A_DIRECTORY_NODE, ANOTHER_DIRECTORY_NODE, 0, 0, 1),
                                    (0,) * 15 + (A_DIRECTORY_NODE,)))
def test_every_directory_the_process_held_has_its_reference_count_dropped(curdir):
    """The third loop, over all sixteen `p_curdir` bytes: a ZERO entry is "no directory" and is
    skipped, and anything else decrements the shared count. Driven with an entry in the last slot,
    so the loop's own bound is a claim, and with the same node held twice — which drops the count
    twice, because the ROM counts holders and not processes."""
    child = process.stage_child(curdir=curdir)
    info, pokes = release(child)
    final = case.final_image(info, pokes)

    for node in set(curdir) - {0}:
        assert process.directory_refcount(final, node) \
            == (process.directory_refcount(BASE_IMAGE, node) - curdir.count(node)) & 0xFF


def test_a_negative_directory_entry_decrements_below_the_table():
    """No bound is applied, and this is the ROM's own shape rather than an accident: the byte is
    sign-extended with `ext.w` and used as an address displacement, so entry -1 reaches the byte
    BEFORE the table. Reproduced rather than clamped (`src/gemdos/process.c`)."""
    child = process.stage_child(curdir=(0xFF,))
    info, _pokes = release(child)
    below = addrs.GEMDOS_CURDIR_REFCOUNTS - 1
    assert case.written(info, below, 1) == ((BASE_IMAGE[below] - 1) & 0xFF)


# ================================================================================================
# $fc8028 / $fc8086 / $fc7fd8 — the three terminators
# ================================================================================================

def terminator_pokes(child, status_args, vector=None, extra=None):
    return {**child.pokes, **gemdos.machine(), **status_args,
            **process.terminate_vector_poke(vector if vector is not None
                                            else process.TERMINATE_ROUTINE_AT),
            **(extra or {})}


def run_pterm(child, status, routines=None, pokes=None):
    routines = routines if routines is not None else process.terminate_routine()
    staged = {**terminator_pokes(child, case.word_arg(status)), **isr.routine_pokes(routines),
              **(pokes or {})}
    return process.run(addrs.GEMDOS_PTERM, lambda lib, buf: lib.gemdos_pterm(buf, status), staged,
                       stop_pc=process.PTERM_EPILOGUE_CALL, routines=routines,
                       io_seed=process.A_BATTERY_CLOCK), staged


@pytest.mark.parametrize("status", EXIT_CODES)
def test_pterm_plants_the_exit_code_in_the_parent_s_own_save_slot(status):
    """`clr.l d0 / move.w 8(a6),d0` and then `move.l d0,104(a0)` — where `a0` is `p_run`, which is
    the PARENT by then. So the code a process exits with arrives in the parent's own D0 save slot,
    and the epilogue's `movem.l $68(a5),d0/a3-a6` is what hands it to whoever called the parent's
    GEMDOS call.

    THE WORD IS ZERO-EXTENDED, which $ffff and $8000 are here to say: `Pterm(-1)` reports $0000ffff.
    """
    child = process.stage_child()
    info, _pokes = run_pterm(child, status)
    assert info["regs"]["d0"] == status
    assert case.written(info, P_RUN + addrs.BASEPAGE_SAVED_D0, 4) == status


def test_pterm_makes_the_parent_the_running_process_and_releases_the_child():
    """The two halves that have to happen in this order: `p_run` becomes `p_parent` BEFORE the
    release, so a descriptor the release allocates could not be charged to a process that is over.

    What the case can see is the end state — the parent running, the child's memory back on the free
    list, and its directory reference given up.
    """
    child = process.stage_child(curdir=(A_DIRECTORY_NODE,))
    info, pokes = run_pterm(child, 0)
    final = case.final_image(info, pokes)

    assert case.written(info, addrs.GEMDOS_P_RUN, 4) == P_RUN
    assert not process.owned_blocks(final, child.basepage)
    assert process.directory_refcount(final, A_DIRECTORY_NODE) \
        == process.directory_refcount(BASE_IMAGE, A_DIRECTORY_NODE) - 1


def test_pterm_calls_the_terminate_vector_before_anything_else():
    """`Setexc($102, -1)` and then a call through what came back. The staged routine leaves a byte,
    so BOTH shores really transfer control — the oracle through the 68000 stub in the image and the
    candidate through `staged_call.h`'s hook (`test/isr.py`, whose installer this shares)."""
    child = process.stage_child()
    info, _pokes = run_pterm(child, 0)
    assert case.written(info, process.TERMINATE_WITNESS_AT, 1) == process.WITNESS
    assert isr.CALLS == [(process.TERMINATE_ROUTINE_AT, process.TERMINATE_ROUTINE_AT)], (
        "the candidate did not call the terminate vector, or called it with the wrong argument")


def test_the_terminate_vector_is_read_and_not_replaced():
    """`Setexc`'s handler argument is -1, which its own `bmi` reads as "report only" — so $408 comes
    out of `Pterm` holding exactly what it went in holding. The one thing that could have written it
    is the call this routine makes through it."""
    child = process.stage_child()
    info, pokes = run_pterm(child, 0)
    assert process.TERMINATE_VECTOR_AT not in info["writes"]
    assert case.long_in(case.final_image(info, pokes), process.TERMINATE_VECTOR_AT) \
        == process.TERMINATE_ROUTINE_AT


def test_the_terminate_routine_is_entered_with_the_vector_as_its_own_argument():
    """$fc4f0a is `move.l 4(sp),-(sp) / rts`, so the routine runs with the VECTOR'S OWN VALUE at
    4(sp) — an Alcyon artefact of `(*f)()` against a first-argument stack slot, reproduced rather
    than simplified. A staged routine that reports its own 4(sp) is the only way to see it."""
    child = process.stage_child()
    seen_at = process.TERMINATE_WITNESS_AT

    def effect(buf, argument):
        isr.poke(buf, seen_at, struct.pack(">I", argument))

    routines = {process.TERMINATE_ROUTINE_AT:
                (isr.store_frame_long(seen_at) + b"\x4e\x75", effect)}
    info, _pokes = run_pterm(child, 0, routines=routines)
    assert case.written(info, seen_at, 4) == process.TERMINATE_ROUTINE_AT


def test_pterm_runs_on_the_captured_machine_s_own_terminate_vector():
    """The arm with no staging at all: `$408` as the snapshot has it, which is the bare `rts` at
    `$fc0670` TOS installs at boot. This is the `Pterm` every program on an unmodified machine
    really makes, and the reconstruction reaches it through the same hook with nothing to do."""
    child = process.stage_child()
    routines = process.rom_terminate_routine()
    staged = {**child.pokes, **gemdos.machine(), **case.word_arg(0)}
    info = process.run(addrs.GEMDOS_PTERM, lambda lib, buf: lib.gemdos_pterm(buf, 0), staged,
                       stop_pc=process.PTERM_EPILOGUE_CALL, routines=routines,
                       io_seed=process.A_BATTERY_CLOCK)
    assert info["regs"]["d0"] == 0
    assert isr.CALLS == [(isr.long_in_snapshot(process.TERMINATE_VECTOR_AT),
                          isr.long_in_snapshot(process.TERMINATE_VECTOR_AT))]


def test_pterm_leaves_the_termination_record_alone():
    """`Pterm` DOES NOT LONGJMP, which is worth a case because everything about the record's name
    says it should. The record at `$7ef4` is the dispatcher's, the file system's critical-error
    abort is what jumps to it, and `Pterm` leaves through the epilogue — so the twelve bytes come
    out of this run exactly as they went in."""
    child = process.stage_child()
    info, _pokes = run_pterm(child, 0)
    assert not any(addrs.GEMDOS_TERMINATION_JMPBUF <= address
                   < addrs.GEMDOS_TERMINATION_JMPBUF + 12 for address in info["writes"])


def test_pterm0_is_pterm_of_zero():
    """Three instructions — `clr.w (sp) / bsr $fc8028` — and the whole of GEMDOS selector 0. The
    exit code is 0 whatever the caller's argument word held, which is what the case drives: the
    staged word is not 0."""
    child = process.stage_child()
    staged = {**terminator_pokes(child, case.word_arg(0x1234)),
              **isr.routine_pokes(process.terminate_routine())}
    info = process.run(addrs.GEMDOS_PTERM0, lambda lib, buf: lib.gemdos_pterm0(buf), staged,
                       stop_pc=process.PTERM_EPILOGUE_CALL, routines=process.terminate_routine(),
                       io_seed=process.A_BATTERY_CLOCK)
    assert info["regs"]["d0"] == 0
    assert case.written(info, P_RUN + addrs.BASEPAGE_SAVED_D0, 4) == 0


# ---- Ptermres --------------------------------------------------------------------------------------

KEEP = 0x800                            # what a resident program asks to keep of its own TPA


def run_ptermres(child, keep, status):
    routines = process.terminate_routine()
    staged = {**terminator_pokes(child, case.args(">IH", keep, status)),
              **isr.routine_pokes(routines)}
    return process.run(addrs.GEMDOS_PTERMRES,
                       lambda lib, buf: lib.gemdos_ptermres(buf, keep, status), staged,
                       stop_pc=process.PTERM_EPILOGUE_CALL, routines=routines,
                       io_seed=process.A_BATTERY_CLOCK), staged


def test_ptermres_shrinks_the_process_s_own_tpa_first():
    """`Mshrink(p_run, keep)` — the block that STARTS at the basepage, which is the process's own
    TPA, trimmed to the length the caller wants kept. The remainder goes back on the free list the
    ordinary way, so what is left resident is exactly `keep` bytes."""
    child = process.stage_child(tpa_bytes=process.CHILD_TPA_BYTES)
    info, pokes = run_ptermres(child, KEEP, 0)
    final = case.final_image(info, pokes)

    assert case.written(info, child.staged.used[0].md + addrs.MD_LENGTH, 4) == KEEP
    remainder = [block for block in gemdos_memory.free_list(final)
                 if block.start == child.basepage + KEEP]
    assert remainder or gemdos_memory.free_list(final)[0].start == child.basepage + KEEP, (
        "the part of the TPA that was not kept did not go back on the free list")


def test_ptermres_leaves_the_kept_block_on_NEITHER_list():
    """THE WHOLE OF WHAT "STAY RESIDENT" MEANS, and the one place `Ptermres` and `Pterm` differ: the
    kept block's descriptor is unlinked from the ALLOCATED list and handed back to the RECORD POOL —
    not inserted into the free list. So the memory survives with no owner and on no list, and
    nothing will ever hand it out again.

    The pair with `test_the_release_puts_the_process_s_memory_back_on_the_free_list` above is the
    claim: same process, same blocks, two different destinations.
    """
    child = process.stage_child(blocks=2)
    info, pokes = run_ptermres(child, KEEP, 0)
    final = case.final_image(info, pokes)
    kept = child.staged.used[0].md

    assert not process.owned_blocks(final, child.basepage), "a block stayed on the allocated list"
    assert not [block for block in gemdos_memory.free_list(final)
                if block.start == child.basepage], "the kept block went back on the FREE list"
    assert kept in gemdos_memory.recycled_descriptors(final), (
        "the kept block's descriptor was not returned to the pool")


@pytest.mark.parametrize("status", (0, 0xFFFF))
def test_ptermres_ends_in_pterm(status):
    """The tail call: everything `Pterm` does happens, exit code and all. Driven at $ffff for the
    zero extension, which is the same claim one routine along."""
    child = process.stage_child()
    info, _pokes = run_ptermres(child, KEEP, status)
    assert info["regs"]["d0"] == status
    assert case.written(info, addrs.GEMDOS_P_RUN, 4) == P_RUN
    assert case.written(info, process.TERMINATE_WITNESS_AT, 1) == process.WITNESS

# ---- the registry --------------------------------------------------------------------------------
# The rows this battery contributes, built from the same constructors the cases drive.

def _register_all():
    child = process.stage_child(curdir=(A_DIRECTORY_NODE,))
    routines = process.terminate_routine()

    gemdos.register("gemdos_resync_clock, a battery clock", addrs.GEMDOS_RESYNC_CLOCK,
                    {"a5": 0}, resync_pokes(), io_seed=process.A_BATTERY_CLOCK)
    gemdos.register("gemdos_release_process", addrs.GEMDOS_RELEASE_PROCESS, {"a5": 0},
                    {**child.pokes, **case.long_args(child.basepage)})
    # ...and the three that DO NOT RETURN, which the seven-field registry cannot carry — see
    # `test/gemdos_process.py`, "the rows the registry cannot take yet".
    process.register_checkpoint(
        "gemdos_pterm", addrs.GEMDOS_PTERM, {"a5": 0},
        {**terminator_pokes(child, case.word_arg(1)), **isr.routine_pokes(routines)},
        process.PTERM_EPILOGUE_CALL, io_seed=process.A_BATTERY_CLOCK)
    process.register_checkpoint(
        "gemdos_pterm0", addrs.GEMDOS_PTERM0, {"a5": 0},
        {**terminator_pokes(child, case.word_arg(0x1234)), **isr.routine_pokes(routines)},
        process.PTERM_EPILOGUE_CALL, io_seed=process.A_BATTERY_CLOCK)
    process.register_checkpoint(
        "gemdos_ptermres", addrs.GEMDOS_PTERMRES, {"a5": 0},
        {**terminator_pokes(child, case.args(">IH", KEEP, 0)), **isr.routine_pokes(routines)},
        process.PTERM_EPILOGUE_CALL, io_seed=process.A_BATTERY_CLOCK)


_register_all()


def test_every_checkpoint_case_is_one_this_battery_drives():
    """The rows the registry cannot take yet are still rows about runs somebody makes, and this is
    what says so: each one names a routine this file has a case for, each stops at the `jsr` into
    the epilogue that is the reason it is here at all, and each really runs to it."""
    entries = {row[1] for row in process.CHECKPOINT_CASES}
    assert entries == {addrs.GEMDOS_PTERM, addrs.GEMDOS_PTERM0, addrs.GEMDOS_PTERMRES}
    assert all(row[-1] == process.PTERM_EPILOGUE_CALL for row in process.CHECKPOINT_CASES)
    for _name, entry, regs, pokes, _psg, io_seed, _sched, stop_pc in process.CHECKPOINT_CASES:
        _final, _writes, o_regs = emu.run(make_image(pokes), entry, regs, io_seed=io_seed,
                                          stop_pc=stop_pc)
        assert o_regs["io_unmodeled_reads"] == 0, "a registered case read an undeclared I/O byte"
