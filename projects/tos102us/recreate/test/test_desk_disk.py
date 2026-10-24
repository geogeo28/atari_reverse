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
import aes_desksupp
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


def _layers_of(each):
    """What the case lays over its arrival's machine: GEMDOS replayed (with Dfree's DISKINFO), the floppy replayed."""
    arrived, layers = arrival_of(each), []
    if each.replayed:
        layers.append(fun.engine_replayed(each.wake)[1](arrived))
    if each.spaced:
        layers.append(dd._dd.replayed(spaced_replay(each)))
    if each.xbios:
        layers.append(dd.floppy_staged(floppy_calls(each)))
    return layers


def pokes_of(each):
    return case.merge_pokes(da.machine_of(arrival_of(each)), *_layers_of(each))


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


# ---- FLIPPED (band 6 slice F4): the unit whole ------------------------------------------------------------------------------
def test_the_unit_is_flipped(blob):
    """THE FLIP PIN of the ten (`aes_deskarrive.flipped`: each core called by its own thunk of the table, its entry ours
    through it — Format's and the copy's by sh_cmd's desk door too); none held (`aes_deskdisk.UNIT_N_WAVE_4_HELD_AT_F4`)."""
    assert not dd.UNIT_N_WAVE_4_HELD_AT_F4
    da.flipped(blob, dd.UNIT_N_WAVE_4)


# ---- band 6 slice F4: THE UNIT'S ROWS — every case at an arrival registered -------------------------------------------------
# OVER ITS TIER 1 CASE'S OWN STAGING (the orchestrator's ruling (c) at F3, stage 1's row kind): the arrival's megabyte
# whole but the harness's window (`aes_deskarrive.row_machine_of`), Format's and the copy's GEMDOS replayed from the
# ROM's own run in place (`REPLAYED` in the row's name; with Dfree's DISKINFO where Format formats) and the floppy's
# XBIOS / BIOS calls where the run reaches the device (`FLOPPY REPLAYED`, its doors the row's child's), the case's wake at
# the row's idles.
#   * A ROW THAT SWITCHES wherever the run enters a process: A DOOR USER where its run calls a rebound entry of the
#     event layer (MEASURED, the table's second count: the dialogs and alerts — util_show's three, util_error's, Format's
#     four, the copy's three), one WITH NO DOOR else (util_open's, util_show's three draws, util_bars', copy_tracks').
#   * util_redraw's two are PLAIN ROWS: no process is entered (sh_draw draws; no binding) — MEASURED: registered as a row
#     that switches it is refused by name, "enters no process". It draws, so it is the event layer's plain kind
#     (`aes_event.register`, drawing: savptr in the band, its companion binding the VDI's cores and the tree walk's
#     routines, as the no-door fork serves them — `aes.walkers`).
#   * A RUN PAST THE DEFAULT DERIVATION MARGIN DECLARES ITS TIER 1 CASE'S OWN BUDGET (the user's ruling of 2026-10-21):
#     Format's three formats, the copy's two, copy_tracks' two.
#   * AES_BIOS_RETURN NAMED BY NATURE where the run reaches the BIOS through the floppy (`aes_desksupp.BIOS_DOOR_PARKED`,
#     R9's kind — drive_check's): the shipped glue's `jsr` parks its own return where the ROM's door parks its caller's.
# The classes stay Tier 1's: fat_swap and fat_mark, reached by no run of the device model (no disk of it has a bad
# sector), are FLIPPED ⚠️ VERIFIED-BUT-UNPRICED (the user's standing rule, after the measurement: STATUS).
AT_ARRIVALS = {name: each for name, each in BY_LABEL.items() if not each.why}
_NO_DOOR = ((dd.UTIL_OPEN, FORMAT_UP, None, 0), (dd.UTIL_OPEN, COPY_UP, None, 0), (dd.UTIL_SHOW, FORMATTED, None, 0),
            (dd.UTIL_SHOW, FORMATTED, None, 1), (dd.UTIL_SHOW, COPIED, None, 2), (dd.UTIL_BARS, FORMATTED, None, 0),
            (dd.UTIL_BARS, COPIED, None, 0), (dd.COPY_TRACKS, COPIED, None, 0), (dd.COPY_TRACKS, COPIED, None, 1))
ROWS_WITH_NO_DOOR = frozenset(name for name, each in AT_ARRIVALS.items() if (each.name, each.chain, each.wake, each.nth) in _NO_DOOR)
PLAIN_ROWS = frozenset(name for name, each in AT_ARRIVALS.items() if not each.switches)


def _parks_the_bios_door(each):
    """Format's formats and the copy's copies: their floppy replayed reaches the BIOS (Rwabs, Getbpb)."""
    return bool(each.xbios) and each.name in (dd.FORMAT, dd.COPY_DISK)


def _row_pokes(each):
    """...and a row's: the same layers over the arrival's megabyte but the harness's window."""
    return case.merge_pokes(da.row_machine_of(arrival_of(each)), *_layers_of(each))


def _registered(name):
    each, pokes = AT_ARRIVALS[name], _row_pokes(AT_ARRIVALS[name])
    arrived, answered = arrival_of(each), vdi.ALCYON[each.name].restype is not None
    if name in PLAIN_ROWS:     # (it draws: its companion binds the VDI's cores and the walked routines, `aes_event.door_hook`)
        return aes_event.register(label(each), each.name, arrived.arguments, pokes, drawing=True, objects=aes.walkers(),
                                  answer_compared=answered, door_user=False)
    at_idle = each.wake.at_idle(each.chain) if each.wake else {}
    row = doors_of(each, aes_event.woken_row(label(each), each.name, arrived.arguments, lambda: pokes, at_idle, None,
                                             objects=True, answered=answered, budget=each.budget))
    if _parks_the_bios_door(each):
        row = row._replace(also_dropped=aes_desksupp.BIOS_DOOR_PARKED)
    if name in ROWS_WITH_NO_DOOR:
        row = row._replace(door=None, child_doors=row.door.doors)
    return aes_event.register_woken(row)


ROWS = {name: _registered(name) for name in AT_ARRIVALS}
# ---- THE ROWS' PINS — DATA, MEASURED by the table's own measurement (`aes_switching.priced_by_the_table`) and by each
# blob's second differential (`aes_switching.measured_on`), from the rows as registered (a recorded run, never by hand).
DOOR_USERS_PRICED_WAVE_4 = {
    "aes_desk_util_show, arrival 0 of A: File > Format, the warning's OK (the FORMAT dialog); the dialog's EXIT clicked":
        ((231970, 315776), (180932, 236928), 7, (0, 0, 0)),
    "aes_desk_util_show, arrival 0 of drive A: dragged onto drive B:, the alert's OK (the DISKCOPY dialog); Return":
        ((120854, 163288), (100396, 130114), 5, (0, 0, 0)),
    "aes_desk_util_show, arrival 0 of A: File > Format, the warning's OK (the FORMAT dialog); 'A' typed (into the label's field), then EXIT clicked":
        ((313958, 437384), (245152, 330938), 8, (0, 0, 0)),
    "aes_desk_format, arrival 0 of A: File > Format, the warning's OK (the FORMAT dialog) [GEMDOS REPLAYED: the ROM's own run in place — its answers]; the dialog's EXIT clicked":
        ((292864, 540650), (241826, 461802), 7, (0, 0, 0)),
    "aes_desk_copy_disk, arrival 0 of drive A: dragged onto drive B:, the alert's OK (the DISKCOPY dialog) [GEMDOS REPLAYED: the ROM's own run in place — its answers]; Return":
        ((182212, 388844), (161754, 355670), 5, (0, 0, 0)),
    "aes_desk_util_error, arrival 0 of a single-sided disk in drive B:, drive A: dragged onto it, OK, COPY clicked (not the same type); Return":
        ((178186, 267308), (157372, 233456), 7, (0, 0, 0)),
    "aes_desk_format, arrival 0 of A: File > Format, the warning's OK (the FORMAT dialog) [GEMDOS REPLAYED: the ROM's own run in place — its answers; and Dfree's DISKINFO, its run's] [THE ROM'S FLOPPY REPLAYED: each XBIOS / BIOS call held to its run in place's, the run's answer]; the dialog's FORMAT clicked, Return at the space alert, then EXIT clicked":
        ((2317842, 3484280), (2196446, 3294444), 21, (0, 0, 0)),
    "aes_desk_format, arrival 0 of A: File > Format, the warning's OK (the FORMAT dialog) [GEMDOS REPLAYED: the ROM's own run in place — its answers; and Dfree's DISKINFO, its run's] [THE ROM'S FLOPPY REPLAYED: each XBIOS / BIOS call held to its run in place's, the run's answer] [LAID: the format buffer stale where the driver's track would lie]; eleven 'A's typed (the label), FORMAT clicked, Return at the space alert, then EXIT clicked":
        ((3258128, 4859348), (2941484, 4366114), 32, (0, 0, 0)),
    "aes_desk_format, arrival 0 of A: File > Format, the warning's OK (the FORMAT dialog) [GEMDOS REPLAYED: the ROM's own run in place — its answers; and Dfree's DISKINFO, its run's] [THE ROM'S FLOPPY REPLAYED: each XBIOS / BIOS call held to its run in place's, the run's answer]; Double Sided clicked, FORMAT clicked, Return at the space alert, then EXIT clicked":
        ((2506996, 3812106), (2351938, 3570466), 23, (0, 0, 0)),
    "aes_desk_copy_disk, arrival 0 of a disk in drive B:, drive A: dragged onto it, OK, COPY clicked (copied) [GEMDOS REPLAYED: the ROM's own run in place — its answers] [THE ROM'S FLOPPY REPLAYED: each XBIOS / BIOS call held to its run in place's, the run's answer]; the dialog's COPY clicked, then Return":
        ((6002042, 7930590), (5930546, 7818568), 12, (0, 0, 0)),
    "aes_desk_copy_disk, arrival 0 of a single-sided disk in drive B:, drive A: dragged onto it, OK, COPY clicked (not the same type) [GEMDOS REPLAYED: the ROM's own run in place — its answers] [THE ROM'S FLOPPY REPLAYED: each XBIOS / BIOS call held to its run in place's, the run's answer]; the dialog's COPY clicked, then Return":
        ((404008, 722276), (332156, 609576), 14, (0, 0, 0)),
}
DOOR_USERS_WHOLE_RUN_WAVE_4 = {
    "aes_desk_util_show, arrival 0 of A: File > Format, the warning's OK (the FORMAT dialog); the dialog's EXIT clicked":
        {"bench": (1650886, 1601830), "bench_shipped": (1650886, 1589580)},
    "aes_desk_util_show, arrival 0 of drive A: dragged onto drive B:, the alert's OK (the DISKCOPY dialog); Return":
        {"bench": (977178, 953112), "bench_shipped": (977178, 948176)},
    "aes_desk_util_show, arrival 0 of A: File > Format, the warning's OK (the FORMAT dialog); 'A' typed (into the label's field), then EXIT clicked":
        {"bench": (1938882, 1863438), "bench_shipped": (1938882, 1843708)},
    "aes_desk_format, arrival 0 of A: File > Format, the warning's OK (the FORMAT dialog) [GEMDOS REPLAYED: the ROM's own run in place — its answers]; the dialog's EXIT clicked":
        {"bench": (1928592, 1718020), "bench_shipped": (1928592, 1705790)},
    "aes_desk_copy_disk, arrival 0 of drive A: dragged onto drive B:, the alert's OK (the DISKCOPY dialog) [GEMDOS REPLAYED: the ROM's own run in place — its answers]; Return":
        {"bench": (1256168, 1070368), "bench_shipped": (1256168, 1065452)},
    "aes_desk_util_error, arrival 0 of a single-sided disk in drive B:, drive A: dragged onto it, OK, COPY clicked (not the same type); Return":
        {"bench": (2002220, 1938216), "bench_shipped": (2002220, 1930406)},
    "aes_desk_format, arrival 0 of A: File > Format, the warning's OK (the FORMAT dialog) [GEMDOS REPLAYED: the ROM's own run in place — its answers; and Dfree's DISKINFO, its run's] [THE ROM'S FLOPPY REPLAYED: each XBIOS / BIOS call held to its run in place's, the run's answer]; the dialog's FORMAT clicked, Return at the space alert, then EXIT clicked":
        {"bench": (13022938, 12094960), "bench_shipped": (13022938, 12074612)},
    "aes_desk_format, arrival 0 of A: File > Format, the warning's OK (the FORMAT dialog) [GEMDOS REPLAYED: the ROM's own run in place — its answers; and Dfree's DISKINFO, its run's] [THE ROM'S FLOPPY REPLAYED: each XBIOS / BIOS call held to its run in place's, the run's answer] [LAID: the format buffer stale where the driver's track would lie]; eleven 'A's typed (the label), FORMAT clicked, Return at the space alert, then EXIT clicked":
        {"bench": (16237278, 15026578), "bench_shipped": (16237278, 14917442)},
    "aes_desk_format, arrival 0 of A: File > Format, the warning's OK (the FORMAT dialog) [GEMDOS REPLAYED: the ROM's own run in place — its answers; and Dfree's DISKINFO, its run's] [THE ROM'S FLOPPY REPLAYED: each XBIOS / BIOS call held to its run in place's, the run's answer]; Double Sided clicked, FORMAT clicked, Return at the space alert, then EXIT clicked":
        {"bench": (13466018, 12403140), "bench_shipped": (13466018, 12382452)},
    "aes_desk_copy_disk, arrival 0 of a disk in drive B:, drive A: dragged onto it, OK, COPY clicked (copied) [GEMDOS REPLAYED: the ROM's own run in place — its answers] [THE ROM'S FLOPPY REPLAYED: each XBIOS / BIOS call held to its run in place's, the run's answer]; the dialog's COPY clicked, then Return":
        {"bench": (28613844, 27302514), "bench_shipped": (28613844, 27320148)},
    "aes_desk_copy_disk, arrival 0 of a single-sided disk in drive B:, drive A: dragged onto it, OK, COPY clicked (not the same type) [GEMDOS REPLAYED: the ROM's own run in place — its answers] [THE ROM'S FLOPPY REPLAYED: each XBIOS / BIOS call held to its run in place's, the run's answer]; the dialog's COPY clicked, then Return":
        {"bench": (3389578, 3121892), "bench_shipped": (3389578, 3107622)},
}
NO_DOOR_PREMISES_WAVE_4 = {
    "aes_desk_util_open, arrival 0 of A: File > Format, the warning's OK (the FORMAT dialog)":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e), None, ()),
    "aes_desk_util_open, arrival 0 of drive A: dragged onto drive B:, the alert's OK (the DISKCOPY dialog)":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e), None, ()),
    "aes_desk_util_show, arrival 0 of A: File > Format, OK, FORMAT clicked (formatted)":
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    "aes_desk_util_show, arrival 1 of A: File > Format, OK, FORMAT clicked (formatted)":
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    "aes_desk_util_show, arrival 2 of a disk in drive B:, drive A: dragged onto it, OK, COPY clicked (copied)":
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    "aes_desk_util_bars, arrival 0 of A: File > Format, OK, FORMAT clicked (formatted)":
        ((), 0, 0xae5e, (0xae5e, 0xae5e), None, ()),
    "aes_desk_util_bars, arrival 0 of a disk in drive B:, drive A: dragged onto it, OK, COPY clicked (copied)":
        ((), 0, 0xae5e, (0xae5e, 0xae5e), None, ()),
    "aes_desk_copy_tracks, arrival 0 of a disk in drive B:, drive A: dragged onto it, OK, COPY clicked (copied) [THE ROM'S FLOPPY REPLAYED: each XBIOS / BIOS call held to its run in place's, the run's answer]":
        ((), 0, 0xae5e, (0xae5e,) * 80, 0x0, ()),
    "aes_desk_copy_tracks, arrival 1 of a disk in drive B:, drive A: dragged onto it, OK, COPY clicked (copied) [THE ROM'S FLOPPY REPLAYED: each XBIOS / BIOS call held to its run in place's, the run's answer]":
        ((), 0, 0xae5e, (0xae5e,) * 80, 0x0, ()),
}
NO_DOOR_PRICED_WAVE_4 = {
    "aes_desk_util_open, arrival 0 of A: File > Format, the warning's OK (the FORMAT dialog)":
        ((54486, 215898), None, None, (0, 0, 0)),
    "aes_desk_util_open, arrival 0 of drive A: dragged onto drive B:, the alert's OK (the DISKCOPY dialog)":
        ((54486, 215898), None, None, (0, 0, 0)),
    "aes_desk_util_show, arrival 0 of A: File > Format, OK, FORMAT clicked (formatted)":
        ((44290, 55926), None, None, (0, 0, 0)),
    "aes_desk_util_show, arrival 1 of A: File > Format, OK, FORMAT clicked (formatted)":
        ((17148, 22328), None, None, (0, 0, 0)),
    "aes_desk_util_show, arrival 2 of a disk in drive B:, drive A: dragged onto it, OK, COPY clicked (copied)":
        ((17148, 22328), None, None, (0, 0, 0)),
    "aes_desk_util_bars, arrival 0 of A: File > Format, OK, FORMAT clicked (formatted)":
        ((51992, 67672), None, None, (0, 0, 0)),
    "aes_desk_util_bars, arrival 0 of a disk in drive B:, drive A: dragged onto it, OK, COPY clicked (copied)":
        ((72410, 91336), None, None, (0, 0, 0)),
    "aes_desk_copy_tracks, arrival 0 of a disk in drive B:, drive A: dragged onto it, OK, COPY clicked (copied) [THE ROM'S FLOPPY REPLAYED: each XBIOS / BIOS call held to its run in place's, the run's answer]":
        ((1355358, 1762416), None, None, (0, 0, 0)),
    "aes_desk_copy_tracks, arrival 1 of a disk in drive B:, drive A: dragged onto it, OK, COPY clicked (copied) [THE ROM'S FLOPPY REPLAYED: each XBIOS / BIOS call held to its run in place's, the run's answer]":
        ((1394230, 1793198), None, None, (0, 0, 0)),
}
NO_DOOR_WHOLE_RUN_WAVE_4 = {
    "aes_desk_util_open, arrival 0 of A: File > Format, the warning's OK (the FORMAT dialog)":
        {"bench": (258260, 99160), "bench_shipped": (258260, 99056)},
    "aes_desk_util_open, arrival 0 of drive A: dragged onto drive B:, the alert's OK (the DISKCOPY dialog)":
        {"bench": (258260, 99160), "bench_shipped": (258260, 99056)},
    "aes_desk_util_show, arrival 0 of A: File > Format, OK, FORMAT clicked (formatted)":
        {"bench": (590918, 585216), "bench_shipped": (590918, 585050)},
    "aes_desk_util_show, arrival 1 of A: File > Format, OK, FORMAT clicked (formatted)":
        {"bench": (78262, 75066), "bench_shipped": (78262, 75102)},
    "aes_desk_util_show, arrival 2 of a disk in drive B:, drive A: dragged onto it, OK, COPY clicked (copied)":
        {"bench": (78250, 75054), "bench_shipped": (78250, 75090)},
    "aes_desk_util_bars, arrival 0 of A: File > Format, OK, FORMAT clicked (formatted)":
        {"bench": (630968, 621710), "bench_shipped": (630968, 621556)},
    "aes_desk_util_bars, arrival 0 of a disk in drive B:, drive A: dragged onto it, OK, COPY clicked (copied)":
        {"bench": (762800, 753188), "bench_shipped": (762800, 752406)},
    "aes_desk_copy_tracks, arrival 0 of a disk in drive B:, drive A: dragged onto it, OK, COPY clicked (copied) [THE ROM'S FLOPPY REPLAYED: each XBIOS / BIOS call held to its run in place's, the run's answer]":
        {"bench": (6252208, 5984116), "bench_shipped": (6252208, 5991582)},
    "aes_desk_copy_tracks, arrival 1 of a disk in drive B:, drive A: dragged onto it, OK, COPY clicked (copied) [THE ROM'S FLOPPY REPLAYED: each XBIOS / BIOS call held to its run in place's, the run's answer]":
        {"bench": (6285750, 6025498), "bench_shipped": (6285750, 6033022)},
}
ROWS_MADE, PLAIN_MADE, NO_DOOR_MADE, BUDGETED, PARKED = 22, 2, 9, 7, 5


def test_every_case_at_an_arrival_is_a_row_and_its_pins_are_the_rows():
    """EVERY CASE AT AN ARRIVAL A ROW — util_redraw's plain, the rest rows that switch, through their door or with none
    as measured; every routine a run reaches with a row (fat_swap and fat_mark none: no run reaches them); each pin dict
    exactly the rows of its kind; the BIOS park named on exactly the rows whose floppy reaches the BIOS."""
    import aes_switching
    switching = {name: row for name, row in ROWS.items() if name not in PLAIN_ROWS}
    assert {AT_ARRIVALS[name].name for name in ROWS} == set(dd.UNIT_N_WAVE_4) - {dd.FAT_SWAP, dd.FAT_MARK}
    assert (len(ROWS), len(PLAIN_ROWS), len(ROWS_WITH_NO_DOOR)) == (ROWS_MADE, PLAIN_MADE, NO_DOOR_MADE)
    assert all(AT_ARRIVALS[name].name == dd.UTIL_REDRAW for name in PLAIN_ROWS)
    door_users = {aes_switching.row_name(row) for row in switching.values() if row.door}
    no_door = {aes_switching.row_name(row) for row in switching.values() if not row.door}
    assert set(DOOR_USERS_PRICED_WAVE_4) == set(DOOR_USERS_WHOLE_RUN_WAVE_4) == door_users
    assert set(NO_DOOR_PREMISES_WAVE_4) == set(NO_DOOR_PRICED_WAVE_4) == set(NO_DOOR_WHOLE_RUN_WAVE_4) == no_door
    parked = {name for name, row in switching.items() if row.also_dropped}
    assert parked == {name for name in switching if _parks_the_bios_door(AT_ARRIVALS[name])} and len(parked) == PARKED
    assert all(switching[name].also_dropped == aes_desksupp.BIOS_DOOR_PARKED for name in parked)


def test_a_row_s_declared_budget_is_its_tier_1_case_s_own():
    """EACH ROW THAT SWITCHES DECLARES ITS TIER 1 CASE'S OWN BUDGET — not merely one the rule admits — and none where its
    case declares none."""
    switching = {name: row for name, row in ROWS.items() if name not in PLAIN_ROWS}
    assert {name: row.budget for name, row in switching.items()} == {name: AT_ARRIVALS[name].budget for name in switching}
    assert sum(bool(row.budget) for row in switching.values()) == BUDGETED


def test_an_unneeded_budget_on_a_plain_row_is_refused_by_name_by_aes_deskarrive():
    """A NAMED PLAIN ROW'S BUDGET IS HELD (the user's ruling of 2026-10-23): `aes_deskarrive.register_row` forwards it to
    `aes.register`, which refuses by the row's name one the oracle's own cap already covers — util_redraw's run, some
    thousands of instructions — before anything is registered."""
    registered = len(aes.CASES)
    with pytest.raises(AssertionError, match=r"a plain row's declared budget refused — .* the oracle's own cap .* covers it"):
        da.register_row(da.Case(dd.UTIL_REDRAW, FORMATTED, yields=False), answered=False,
                        budget=aes_event.DIFFERENTIAL_INSNS * aes_event.DERIVATION_MARGIN)
    assert len(aes.CASES) == registered


def test_util_redraw_s_plain_rows_are_not_door_users():
    """util_redraw's two PLAIN ROWS, registered through the event layer's drawing kind, call no rebound entry: they are
    not in the door users' census's list (`aes_event.DOOR_USER_ROWS`)."""
    plain = {ROWS[name][0] for name in PLAIN_ROWS}
    assert len(plain) == PLAIN_MADE and not plain & set(aes_event.DOOR_USER_ROWS)


@pytest.mark.parametrize("name", NO_DOOR_PREMISES_WAVE_4)
def test_a_row_with_no_door_has_its_premise_on_the_rom_s_run(name):
    import aes_deskapp
    aes_deskapp.vet_the_premise(name, NO_DOOR_PREMISES_WAVE_4)


@pytest.mark.parametrize("name", NO_DOOR_WHOLE_RUN_WAVE_4)
def test_a_row_with_no_door_is_parked_and_woken_by_our_dispatcher_on_both_blobs(name, blob):
    import aes_deskapp
    aes_deskapp.vet_on_a_blob(blob, name, NO_DOOR_PREMISES_WAVE_4, NO_DOOR_PRICED_WAVE_4, NO_DOOR_WHOLE_RUN_WAVE_4)


@pytest.mark.parametrize("name", NO_DOOR_PRICED_WAVE_4)
def test_a_row_with_no_door_is_priced_as_pinned_and_under_the_bar(name):
    import aes_deskapp
    aes_deskapp.vet_the_price(name, NO_DOOR_PRICED_WAVE_4)
