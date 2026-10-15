"""THE DESK'S DISK UTILITIES (`src/desk/deskdisk.c`; band 6 wave 4, group G2, unit N): Format, the disk copy, their
dialog and their helpers — HELD AT TIER 1 AT THE ARRIVALS OF ROM RUNS, LINKED, AND NOTHING BOUND.

  * EVERY CASE IS AN ARRIVAL (`aes_deskarrive.arrival`): a chain of the hands stopped at the routine's first
    instruction, its arguments read off the frame the ROM's caller pushed. Where no chain makes the machine an arm
    needs, the case is A LABELLED ARGUMENT CLASS, said in its id (the routine over an arrival's machine — its own, or
    another routine's, `over` — with other arguments). Never a poke but a LAID staging, said in the id.
  * A ROUTINE THAT YIELDS (a binding of unit D, fm_do, fm_alert, crit_err's alert) is a ROW THAT SWITCHES, held
    through the companion, its waits ended by its WAKE (`aes_deskfun`'s: a key typed, a button clicked — the same hand
    the ROM's run in place takes in); one that never yields is the kit's plain differential.
  * FORMAT AND THE COPY REACH GEMDOS: unit C's recorder replaying the ROM's own run in place (`REPLAYED`, in the id).
  * D0 AT RETURN: compared at its width where the C answers one; the void routines' D0 (a callee's leftover) is read
    by no ROM caller (`aes_deskbind.answer_readers`): a counted divergence.
  * UNBOUND: no function of a blob but a routine held at Tier 1 refers to the cores; their Line-F table entries stay
    the ROM's; no registry names one.
"""
import functools
import struct
from collections import namedtuple

import pytest

import aes
import aes_boot
import aes_desk
import aes_deskarrive as da
import aes_deskbind as db
import aes_deskdisk as dd
import aes_deskfun as fun
import aes_event
import case
import opcodes as op
import vdi
from aes_desk import SCAN_A, SCAN_RETURN

import layouts

# THE UNIT'S CONSTANTS, imported from its header (and `desk/deskglobals.h`), never re-spelt
D = layouts.parse_constants((db.GLOBALS_HEADER, aes.INCLUDE / "desk" / "deskdisk.h"), known={**vdi.CONSTANTS, **aes.CONSTANTS})

# ---- THE CHAINS (slice H's, `aes_desk`) and the wakes --------------------------------------------------------------
FORMAT_UP, FORMATTED, COPY_UP, COPIED = aes_desk.FORMAT_UP, aes_desk.FORMATTED, aes_desk.COPY_UP, aes_desk.COPIED
NOT_THE_SAME_TYPE = aes_desk.NOT_THE_SAME_TYPE      # (this group's chain: a single-sided disk in drive B:)
LAST_STEP = -1                          # the step that leaves the dialog up: each chain's last
RETURN_KEY = fun.keys_typed(SCAN_RETURN)
EXIT_CLICKED = fun.clicked(fun.alert_button_point("EXIT"), LAST_STEP)      # (its text padded: "  EXIT  ")


def both(first, second):
    """Two wakes, one after the other: the second's idles counted on from the first's last."""
    def at_idle(chain):
        before = first.at_idle(chain)
        return {**before, **{len(before) + idle: hand for idle, hand in second.at_idle(chain).items()}}
    return fun.Wake(at_idle, lambda chain: (*first.receptions(chain), *second.receptions(chain)))


COPY_CLICKED = fun.clicked(fun.dialog_button_point("COPY"), -2)     # COPY's chains: the dialog up before their last step
FORMAT_CLICKED = fun.clicked(fun.dialog_button_point("FORMAT"), LAST_STEP)
FORMAT_ALERT_EXIT = both(both(FORMAT_CLICKED, RETURN_KEY), EXIT_CLICKED)
DOUBLE_SIDED_CLICKED = fun.clicked(fun.dialog_button_point("Double Sided"), LAST_STEP)
DOUBLE_FORMAT_ALERT_EXIT = both(DOUBLE_SIDED_CLICKED, FORMAT_ALERT_EXIT)
A_TYPED_EXIT = both(fun.keys_typed(SCAN_A), EXIT_CLICKED)
# (the fix pass) A LABEL OF ELEVEN LETTERS typed into Format's field, then FORMAT: the root's label entry whole
LABEL_FORMAT_ALERT_EXIT = both(fun.keys_typed(*(SCAN_A,) * D["FORMAT_LABEL_BYTES"]), FORMAT_ALERT_EXIT)
COPY_THEN_RETURN = both(COPY_CLICKED, RETURN_KEY)
WAKE_NAMED = {RETURN_KEY: "Return", EXIT_CLICKED: "the dialog's EXIT clicked",
              COPY_THEN_RETURN: "the dialog's COPY clicked, then Return",
              FORMAT_ALERT_EXIT: "the dialog's FORMAT clicked, Return at the space alert, then EXIT clicked",
              DOUBLE_FORMAT_ALERT_EXIT: "Double Sided clicked, FORMAT clicked, Return at the space alert, then EXIT clicked",
              A_TYPED_EXIT: "'A' typed (into the label's field), then EXIT clicked",
              LABEL_FORMAT_ALERT_EXIT: "eleven 'A's typed (the label), FORMAT clicked, Return at the space alert, then EXIT clicked"}
FORMAT_INSNS = 7_000_000                # a disk formatted, its alert answered: 1,214,433 measured
LABEL_FORMAT_INSNS = 8_000_000          # ...its label typed first: 1,481,821 measured (the margin's five times)
COPY_DISK_INSNS = 13_000_000            # the copy of a disk's 80 tracks, read and written, read back: 2,577,519 measured
REFUSED_COPY_INSNS = 2_000_000          # the copy refused, its alert answered: 335,644 measured
COPY_TRACKS_INSNS = 4_000_000           # copy_tracks' write of 80 tracks, each read back: the bar drawn 80 times

Case = namedtuple("Case", "name chain wake nth why arguments over laid replayed budget yields xbios unheld spaced switches "
                         "answered", defaults=(None, 0, None, None, None, None, False, None, True, False, (), False, True, None))
Case.__doc__ = """One case: `name` at the `nth` arrival (from 0) of `chain`, its waits ended by `wake` (a Wake named in
WAKE_NAMED; None: it returns without one). AN ARGUMENT CLASS has a `why` and `arguments` (a tuple, or `arrival ->
tuple`), over the arrival of `over` (another routine; None: its own). `laid`: `(what, arrival -> pokes)`, a labelled
staging over the arrival. `replayed`: GEMDOS replayed from the run in place to the return (the id says so). `yields`
False: the plain differential. `xbios`: the floppy (its XBIOS and BIOS calls) replayed from the run in place
(`aes_deskdisk.FLOPPY_REPLAYED`, in the id; `unheld` its frame words no C has). `spaced`: GEMDOS replayed with Format's
Dfree and the DISKINFO its run in place filled (`aes_deskdir.DFREE_FILLED`; `SPACED`, in the id). `switches` False: a row
(its VDI served in its child) whose run never reaches the dispatcher (util_redraw: sh_draw draws, no binding).
`answered`: `Replayed -> Replayed`, the floppy's answers of a labelled class (said with `laid`)."""
SPACED = "and Dfree's DISKINFO, its run's"


def label(each):
    where = f"arrival {each.nth} of {each.chain}" + (f" (at {each.over})" if each.over else "")
    said = (f"ARGUMENT CLASS ({each.why}), over " if each.why else "") + where
    said += f" [{dd._dd.REPLAYED_ANSWERS}]" if each.replayed else ""
    said += f" [{dd._dd.REPLAYED_ANSWERS}; {SPACED}]" if each.spaced else ""
    said += f" [{dd.FLOPPY_REPLAYED}]" if each.xbios else ""
    said += f" [{da.LAID}: {each.laid[0]}]" if each.laid else ""
    return said + (f"; {WAKE_NAMED[each.wake]}" if each.wake else "")


@functools.cache
def arrival_of(each):
    arrived = da.arrival(each.over or each.name, each.chain, each.nth)
    if each.budget:                     # (the run in place's segments take the row's own budget: a copy's is long)
        arrived = arrived._replace(budget=max(arrived.budget, each.budget))
    if each.laid:
        arrived = da._laid_over(arrived, each.laid[1](arrived))
    if not each.why:
        return arrived
    arguments = each.arguments(arrived) if callable(each.arguments) else each.arguments
    return arrived._replace(name=each.name, arguments=tuple(arguments))


def receptions_of(each):
    return each.wake.receptions(each.chain) if each.wake else ()


@functools.cache
def floppy_calls(each):
    """The ROM's own run in place's XBIOS and BIOS calls (`aes_deskdisk.floppy_in_place`), its wakes taken in — a
    class's answers made its own (`answered`)."""
    replayed = dd.floppy_in_place(arrival_of(each), receptions_of(each))
    return each.answered(replayed) if each.answered else replayed


@functools.cache
def spaced_replay(each):
    """GEMDOS's run in place, Dfree's DISKINFO captured (`aes_deskdir.DFREE_FILLED`)."""
    return dd.in_place(arrival_of(each), receptions_of(each), captures=dd._dd.DFREE_FILLED)


def pokes_of(each):
    arrived = arrival_of(each)
    layers = []
    if each.replayed:
        layers.append(fun.engine_replayed(each.wake)[1](arrived))
    if each.spaced:
        layers.append(dd._dd.replayed(spaced_replay(each)))
    if each.xbios:
        layers.append(dd.floppy_staged(floppy_calls(each)))
    return case.merge_pokes(da.machine_of(arrived), *layers)


def doors_of(each, row):
    """The row's child's doors: the routine's declared ones, and the XBIOS's where it is replayed."""
    if not each.xbios:
        return row
    import aes_switch
    source = aes_event.CHILD_DOORS.get(each.name, "") + dd.floppy_door_source(floppy_calls(each), each.unheld)
    return row._replace(door=aes_switch.DoorUser(True, source))


def tier_1(each):
    """THE CASE: a row that switches (`aes_event.woken_row`, through the companion), its waits ended by its wake — the
    C core through the host's scheduler held to the ROM's routine from the same entry — or the plain differential."""
    arrived, pokes = arrival_of(each), pokes_of(each)
    answered = vdi.ALCYON[each.name].restype is not None
    if not each.yields:
        return aes.run_function(each.name, arrived.arguments, pokes, answer_compared=answered)
    at_idle = each.wake.at_idle(each.chain) if each.wake else {}
    row = doors_of(each, aes_event.woken_row(label(each), each.name, arrived.arguments, lambda: pokes, at_idle, None,
                                             objects=True, answered=answered, budget=each.budget))
    ran, the_rom_s = da.held(row), da.the_rom_s_run(row)
    assert bool(the_rom_s.idles) == (each.wake is not None), f"{label(each)}: the ROM's run idles {the_rom_s.idles} time(s)"
    if each.switches:
        assert ran.entered and ran.entered[-1] == aes.SHELL_PD, f"{label(each)}: the run does not end in the desk's own process"
    else:
        assert not ran.entered, f"{label(each)}: the run switches"
    return ran


FORTY = D["UTIL_BAR_HALF_TRACKS"]
BPB_BFLAGS_LOW_BYTE, FAT16 = D["BPB_BFLAGS_LOW_BYTE"], 1 << D["BPB_FAT16_BIT"]


def _drive_a_record(arrived):
    """Drive A:'s record of the floppy driver's — the BPB its Getbpb answers (`aes_boot.driver_record`)."""
    return aes_boot.driver_record(aes_boot.Machine(arrived.boot).image())


def _fat_mark(cluster, value):
    """fat_mark's arguments: `cluster`, `value`, drive A:'s BPB, and as the FAT the utility tree's bytes (RAM of many
    values, so the twelve bits kept show)."""
    return lambda a: (cluster & aes.WORD_MASK, value & aes.WORD_MASK, _drive_a_record(a),
                      case.long_in(a.boot.ram, D["AES_DESK_UTIL_TREE"]) & db.BUS)


def _fat16_flag(arrived):
    at = _drive_a_record(arrived) + BPB_BFLAGS_LOW_BYTE
    return {at: bytes((arrived.boot.ram[at] | FAT16,))}


# FLOPFMT'S BAD SECTORS (no disk of the device model has one): Flopfmt of track BAD_TRACK answering -16, its list LAID at
# the buffer's head — the format's first Malloc, as the run in place got it — two sectors whose clusters are even and
# odd (the formatted disk's data from record 12, two sectors a cluster: records 48 and 51, clusters 20 and 21).
BAD_TRACK, BAD_SECTORS = 5, (4, 7)
FLOPFMT_BAD_SECTORS = D["FLOPFMT_BAD_SECTORS"]


def _bad_sectors_listed(wake):
    def laid(arrived):
        buffer = dd.in_place(arrived, wake.receptions(arrived.chain)).answers[0] & db.BUS
        return {buffer: struct.pack(f">{len(BAD_SECTORS) + 1}H", *BAD_SECTORS, 0)}
    return laid


def _bad_track_answers(side):
    """The run's floppy with Flopfmt of BAD_TRACK on `side` answering bad sectors — and the FATs' Rwabs writes' bytes
    UNHELD at their calls (`aes_deskdisk.WRITTEN_UNHELD`: the class marks clusters the run in place did not; the root,
    written first, stays held, and the FAT the last write leaves in the buffer is held by the end state)."""
    def answers(replayed):
        xbios = tuple(call._replace(answer=FLOPFMT_BAD_SECTORS & aes.LONG_MASK)
                      if call.words[0] == dd.FLOPFMT_FN and (call.words[dd.FLOPFMT_TRACK_WORD],
                                                              call.words[dd.FLOPFMT_SIDE_WORD]) == (BAD_TRACK, side)
                      else call for call in replayed.xbios)
        writes = [nth for nth, call in enumerate(replayed.bios) if dd.rwabs_written_by(call)]
        bios = tuple(call._replace(pointed=dd.WRITTEN_UNHELD) if nth in writes[1:] else call
                     for nth, call in enumerate(replayed.bios))
        return replayed._replace(xbios=xbios, bios=bios)
    return answers


# THE FORMAT BUFFER STALE (the fix pass, reviewer B's F1): on neither shore does a driver write the buffer (the ROM's
# run in place's Flopfmt leaves a track and its verify there), so a buffer of zeros hides a C that clears too few of
# the root's / FATs' words — LAID stale at the arrival (the first Malloc, as the run in place got it), the root and
# FAT writes' bytes then held to the run's at their calls.
FORMAT_BUFFER_BYTES = D["FORMAT_BUFFER_BYTES"]


def _format_buffer_stale(wake):
    def laid(arrived):
        buffer = dd.in_place(arrived, wake.receptions(arrived.chain)).answers[0] & db.BUS
        return {buffer: bytes((vdi.STALE_WORD & aes.BYTE_MASK,)) * FORMAT_BUFFER_BYTES}
    return laid


# ---- THE CASES --------------------------------------------------------------------------------------------------------
CASES = (
    # util_open: Format's and the copy's
    Case(dd.UTIL_OPEN, FORMAT_UP), Case(dd.UTIL_OPEN, COPY_UP),
    # util_show: Format's dialog run to its EXIT; the copy's to Return (EXIT, its default)
    Case(dd.UTIL_SHOW, FORMAT_UP, EXIT_CLICKED), Case(dd.UTIL_SHOW, COPY_UP, RETURN_KEY),
    Case(dd.UTIL_SHOW, FORMAT_UP, A_TYPED_EXIT),
    # Format and the copy left by EXIT (GEMDOS replayed: the Mallocs, the three Mfrees)
    Case(dd.FORMAT, FORMAT_UP, EXIT_CLICKED, replayed=True),
    Case(dd.COPY_DISK, COPY_UP, RETURN_KEY, replayed=True),
    # util_show drawing alone: Format's progress box, a step of its bar; a step of the copy's read bar
    Case(dd.UTIL_SHOW, FORMATTED), Case(dd.UTIL_SHOW, FORMATTED, nth=1), Case(dd.UTIL_SHOW, COPIED, nth=2),
    # util_bars: Format's (80 tracks), the copy's (the disk's 80); a disk of 40 (the step doubled: no disk of ours)
    Case(dd.UTIL_BARS, FORMATTED), Case(dd.UTIL_BARS, COPIED),
    Case(dd.UTIL_BARS, FORMATTED, why="a disk of 40 tracks: the step doubled", arguments=lambda a: (*a.arguments[:2], FORTY)),
    # util_redraw: before Format's space alert, before the copy's refusal
    Case(dd.UTIL_REDRAW, FORMATTED, switches=False), Case(dd.UTIL_REDRAW, NOT_THE_SAME_TYPE, switches=False),
    # util_error: the copy's disks of two types (the alert, Return); the other alert (no run of the device model fails:
    # a class over that arrival's machine). Its negative error, GEM's critical-error alert, is UNPINNED (below)
    Case(dd.UTIL_ERROR, NOT_THE_SAME_TYPE, RETURN_KEY),
    Case(dd.UTIL_ERROR, NOT_THE_SAME_TYPE, RETURN_KEY, why="a failure's 1: \"an error has occurred\"",
         arguments=lambda a: (D["FORMAT_FAILED"], a.arguments[1])),
    # fat_swap, fat_mark: no run formats a bad sector — classes over util_redraw's arrival in Format (its FAT laid out)
    Case(dd.FAT_SWAP, FORMATTED, over=dd.UTIL_REDRAW, why="a word of distinct bytes", arguments=(D["AES_DESK_UTIL_TREE"],),
         yields=False),
    *(Case(dd.FAT_MARK, FORMATTED, over=dd.UTIL_REDRAW, why=why, arguments=_fat_mark(cluster, value), yields=False)
      for why, cluster, value in (("an even cluster of a 12-bit FAT", 4, -1), ("an odd one", 5, -1),
                                  ("a negative cluster: its offset sign-extended", -4, -1),
                                  ("its unread word other than Format's -1", 7, 0x1234))),
    Case(dd.FAT_MARK, FORMATTED, over=dd.UTIL_REDRAW, why="a 16-bit FAT's cluster", arguments=_fat_mark(9, -1), yields=False,
         laid=("drive A:'s BPB flags: a 16-bit FAT", _fat16_flag)),
    Case(dd.FAT_MARK, FORMATTED, over=dd.UTIL_REDRAW, why="a 16-bit FAT's negative cluster", arguments=_fat_mark(-3, -1),
         yields=False, laid=("drive A:'s BPB flags: a 16-bit FAT", _fat16_flag)),
    # Format's FORMAT: drive A: formatted (single-sided, the dialog's default), its space alerted, then EXIT. Its
    # Flopwrs' filler (words 3, 4: its -4(a6), never written) UNHELD — named
    Case(dd.FORMAT, FORMAT_UP, FORMAT_ALERT_EXIT, spaced=True, xbios=True, budget=FORMAT_INSNS,
         unheld=((dd.FLOPWR_FN, 3), (dd.FLOPWR_FN, 4))),
    # ...with a label of eleven letters typed, over a stale buffer (the fix pass: what Rwabs writes, held whole)
    Case(dd.FORMAT, FORMAT_UP, LABEL_FORMAT_ALERT_EXIT, spaced=True, xbios=True, budget=LABEL_FORMAT_INSNS,
         unheld=((dd.FLOPWR_FN, 3), (dd.FLOPWR_FN, 4)),
         laid=("the format buffer stale where the driver's track would lie", _format_buffer_stale(LABEL_FORMAT_ALERT_EXIT))),
    # ...and its bad sectors listed and their clusters marked in the FAT (fat_mark, fat_swap): a class
    Case(dd.FORMAT, FORMAT_UP, FORMAT_ALERT_EXIT, spaced=True, xbios=True, budget=FORMAT_INSNS,
         unheld=((dd.FLOPWR_FN, 3), (dd.FLOPWR_FN, 4)), why=f"Flopfmt of track {BAD_TRACK} answers bad sectors; the FAT writes' bytes unheld at their calls",
         arguments=lambda a: a.arguments, answered=_bad_track_answers(0),
         laid=(f"the bad sectors {BAD_SECTORS} at the buffer's head", _bad_sectors_listed(FORMAT_ALERT_EXIT))),
    # ...double-sided (Double Sided clicked first: two sides a track, the skew 2, Protobt's type 3); its bad sectors on
    # the second side (a class)
    Case(dd.FORMAT, FORMAT_UP, DOUBLE_FORMAT_ALERT_EXIT, spaced=True, xbios=True, budget=FORMAT_INSNS,
         unheld=((dd.FLOPWR_FN, 3), (dd.FLOPWR_FN, 4))),
    Case(dd.FORMAT, FORMAT_UP, DOUBLE_FORMAT_ALERT_EXIT, spaced=True, xbios=True, budget=FORMAT_INSNS,
         unheld=((dd.FLOPWR_FN, 3), (dd.FLOPWR_FN, 4)),
         why=f"Flopfmt of track {BAD_TRACK}, side 1 answers bad sectors; the FAT writes' bytes unheld at their calls",
         arguments=lambda a: a.arguments, answered=_bad_track_answers(1),
         laid=(f"the bad sectors {BAD_SECTORS} at the buffer's head", _bad_sectors_listed(DOUBLE_FORMAT_ALERT_EXIT))),
    # the copy's COPY: a disk copied, then EXIT (Return, its default); two disks of other types refused (the alert's OK)
    Case(dd.COPY_DISK, COPIED, COPY_THEN_RETURN, replayed=True, xbios=True, budget=COPY_DISK_INSNS),
    Case(dd.COPY_DISK, NOT_THE_SAME_TYPE, COPY_THEN_RETURN, replayed=True, xbios=True, budget=REFUSED_COPY_INSNS),
    # copy_tracks: the copy's read of its 80 tracks, and their write (each written track read back)
    Case(dd.COPY_TRACKS, COPIED, xbios=True, budget=COPY_TRACKS_INSNS),
    Case(dd.COPY_TRACKS, COPIED, nth=1, xbios=True, budget=COPY_TRACKS_INSNS),
)
BY_LABEL = {f"{each.name} — {label(each)}": each for each in CASES}
assert len(BY_LABEL) == len(CASES), "two cases of one id"


@pytest.mark.parametrize("name", BY_LABEL)
def test_a_routine_of_the_unit_from_its_arrival_is_the_rom_s(name):
    """THE CASE (`tier_1`) — and where GEMDOS is replayed, THE CALLS THE C MADE ARE THE ROM'S RUN'S OWN."""
    each = BY_LABEL[name]
    ran = tier_1(each)
    if each.replayed or each.spaced:
        made = tuple(function for function, _frame in dd._dd.engine_calls(ran.image))
        assert made == dd.in_place(arrival_of(each), each.wake.receptions(each.chain) if each.wake else ()).functions


# ---- WHAT THE CASES COVER ----------------------------------------------------------------------------------------------
ARRIVALS, CLASSES = 22, 11


def test_every_routine_of_the_unit_has_a_case_and_those_a_run_reaches_one_at_an_arrival():
    """Each of the ten has a case; each a run reaches has one AT AN ARRIVAL of its own — fat_swap and fat_mark (a bad
    sector, which no disk of the device model has) only classes, over Format's laid out FAT."""
    at_its_own = {each.name for each in CASES if not each.why}
    assert {each.name for each in CASES} == set(dd.UNIT_N_WAVE_4)
    assert set(dd.UNIT_N_WAVE_4) - at_its_own == {dd.FAT_SWAP, dd.FAT_MARK}
    assert (sum(not each.why for each in CASES), sum(bool(each.why) for each in CASES)) == (ARRIVALS, CLASSES)


def test_the_device_cases_name_their_device_class():
    """A case over a device machine says so in its id: the formatter's and drive B:'s runs are replayed (FLOPPY
    REPLAYED) — and the copy's chains are DRIVE_B machines (`aes_boot`'s label, on the walked machine's devices)."""
    for chain in (COPIED, NOT_THE_SAME_TYPE):
        assert aes_boot.DRIVE_B in aes_desk.walked(chain).machine.boot.devices
    assert aes_boot.THE_FORMATTER in aes_desk.walked(FORMATTED).machine.boot.devices
    for each in CASES:
        if each.chain in (COPIED, NOT_THE_SAME_TYPE, FORMATTED) and each.name in (dd.FORMAT, dd.COPY_DISK, dd.COPY_TRACKS):
            assert each.xbios, f"{label(each)}: a device run, not replayed"


# ---- D0 -------------------------------------------------------------------------------------------------------------------
VOID = [name for name, (restype, _frame) in dd.SIGNATURES_WAVE_4.items() if restype is None]
READERS = {dd.COPY_TRACKS: 2, dd.FAT_SWAP: 0, dd.FORMAT: 0, dd.COPY_DISK: 0}
VOID_CASES = 21


def test_no_caller_in_the_rom_reads_what_a_void_routine_leaves_in_d0_and_who_reads_the_others():
    """D0 (`aes_deskbind.answer_readers`): the six void routines' D0 — a callee's leftover — is read by no instruction
    of the ROM; of the four that answer, copy_tracks' is read by the copy's two calls (`tst.w d0`), fat_swap's, Format's
    and the copy's by none (each held to the ROM's word all the same)."""
    assert {name: db.answer_readers(da.entry_of(name)) for name in VOID} == {name: set() for name in VOID}
    assert {name: len(db.answer_readers(da.entry_of(name))) for name in READERS} == READERS


def test_the_cases_whose_d0_the_c_does_not_have_are_counted():
    """THE COUNT: the cases of the void routines, whose ROM D0 no C has (a counted, named divergence)."""
    assert sum(each.name in VOID for each in CASES) == VOID_CASES


# ---- WHAT THE ROM DOES THAT NO C HAS -------------------------------------------------------------------------------------
FAT_MARK_CALL_SITE = 0xfedd4a           # format's Line-F call of fat_mark (read: $fed912's listing), `addq.l #8,sp` after it
POPPED = op.ADDQ_L_8_SP


def test_fat_mark_s_store_into_its_argument_slot_is_read_back_by_no_caller():
    """fat_mark's 12-bit arm STORES into its argument slot 10(a6) (its own frame's caller's half: `$fee3e0`, `$fee3ee`):
    its one caller, Format, pops the four words at once (`addq.l #8,sp`) and reads none of them."""
    from harness import BASE_IMAGE
    assert [at for sites in aes.line_f_call_sites(dd.FAT_MARK).values() for at in sites] == [FAT_MARK_CALL_SITE]
    assert case.word_in(BASE_IMAGE, FAT_MARK_CALL_SITE + aes.WORD_BYTES) == POPPED


# ---- LINKED AND UNBOUND ----------------------------------------------------------------------------------------------------
def test_the_unit_is_linked_and_unbound(blob):
    """UNBOUND (`aes_deskarrive.unbound`): every core linked, nothing of the blob outside the unbound desk refers to a
    held core, their table entries the ROM's, no registry names one."""
    da.unbound(blob, dd.UNIT_N_WAVE_4)
