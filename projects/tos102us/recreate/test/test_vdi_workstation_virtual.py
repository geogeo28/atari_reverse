"""The VIRTUAL workstations and the close of the physical one (`src/vdi/workstation.c`).

    v_opnvwk (100, $fcd612)  Malloc(308); 0 -> contrl[6] = 0. Else from the physical record, handle 1: while the
                             record stood on holds the handle, handle + 1 and step on (stop at the last); link the
                             new record AFTER the one stopped at, make it current, contrl[6] and its handle; init_wk
    v_clsvwk (101, $fcd6a4)  handle 1: nothing. Else find the record whose WS_NEXT has the current's handle, point
                             it past the current, Mfree(current)
    v_clswk (2, $fcb998)     every record after the physical one Mfree'd in list order through LINEA_CUR_WORK
                             (left 0; the physical WS_NEXT left as it was); restore_timer_mouse

GEMDOS IS THE ROM's ON ONE SIDE AND THE RECONSTRUCTION'S ON THE OTHER (`test/vdi_workstation.py`,
`through_gemdos`), and the LIST IS BUILT, never staged: a chain of real calls, each run over the machine the last
one left (`case.continued`) — three opens, the middle one closed, and two opens more. That chain is what reaches
the ROM's handle bug by itself: with 3 closed out of 1, 2, 3, 4, the walk stops at the 4 and appends a 3 after it,
and the open after that stops at the 4 again and inserts a SECOND 3 between it and the first.

Malloc failing is a pool with no free block (`gemdos_memory.stage`). There is no handle exhaustion to stage: the
walk counts up a word for every record it passes, and the list cannot hold 65,535 of them.

THE TIER 3 ROWS are the chain's machines again, over the STAGED `trap #1` (`vdi_workstation.through_staged_trap`),
each a differential of its own below, and each dropping LINEA_RETSAV from its Tier 3 compare alone.
"""
import functools
from collections import namedtuple

from harness import addrs

import case
import gemdos
import gemdos_memory as mem
import vdi
import vdi_helpers
import vdi_screen as screen
import vdi_workstation as ws
from case import merge_pokes

H = ws.WORKSTATION_H


def call_over(name, previous, at=vdi.VDI_PHYS_WORK):
    """`addrs.<name>` called over the machine `previous` stages, with the record at `at` as the dispatcher leaves it
    current (the physical one for the opens, which are served without a lookup), and RETSAV stale."""
    work = vdi.dispatched_pokes(at, onto=previous)
    intin = ws.GEM_INTIN if name == ws.OPNVWK else ()
    return merge_pokes(vdi.function_pokes(name, intin, workstation_pokes=work), vdi_helpers.RETSAV_STALE)


def current(result):
    return result.linea("CUR_WORK")


# The TPA the opens are answered from, FILLed, so each fresh record's every unwritten byte reads as one no store made.
FRESH_TPA = {ws.TPA_AT: bytes([vdi.FILL]) * (ws.TPA_RECORDS * vdi.WS_BYTES)}
# THE CHAIN: (step, function, the step whose record it closes). Three opens, the middle one closed, two opens more.
CHAIN = (("open A", ws.OPNVWK, None), ("open B", ws.OPNVWK, None), ("open C", ws.OPNVWK, None),
         ("close B", ws.CLSVWK, "open B"), ("open D", ws.OPNVWK, None), ("open E", ws.OPNVWK, None))


# One step's staging, the machine it left (as the next step's pokes), the record it left current, and — for the
# differential chain — its Result.
Step = namedtuple("Step", "pokes left current result")


def played(run):
    """The chain, each step over the machine the one before left: `run(name, pokes)` answers a `Step` less its
    staging. Answers `{step: Step}`."""
    steps, previous = {}, FRESH_TPA
    for step, name, closing in CHAIN:
        pokes = call_over(name, previous, steps[closing].current if closing else vdi.VDI_PHYS_WORK)
        steps[step] = Step(pokes, *run(name, pokes))
        previous = steps[step].left
    return steps


def oracle_step(name, pokes):
    left = ws.oracle_continued(name, pokes)
    return left, case.long_in(vdi.make_image(left), vdi.LINEA_CUR_WORK), None


def differential_step(name, pokes):
    result = ws.through_gemdos(name, pokes)
    return case.continued(result), current(result), result


@functools.cache
def chain():
    """{step: Result} of the chain, each a differential of its own."""
    return {step: played_step.result for step, played_step in played(differential_step).items()}


def record(step):
    return current(chain()[step])


def close_over(previous, at):
    return ws.through_gemdos(ws.CLSVWK, call_over(ws.CLSVWK, previous, at))


def test_the_first_open_takes_handle_2_and_links_after_the_physical_record():
    result = chain()["open A"]
    a = current(result)
    assert a == ws.TPA_AT, "GEMDOS answered from the snapshot's free block"
    assert result.contrl(vdi.CONTRL_HANDLE) == ws.FIRST_VIRTUAL_HANDLE
    assert ws.list_of(result.final) == [(vdi.VDI_PHYS_WORK, vdi.VDI_PHYS_HANDLE), (a, ws.FIRST_VIRTUAL_HANDLE)]
    assert result.workstation("FILL_PER", a) == 1, "init_wk set the new record up"
    assert result.contrl(vdi.CONTRL_N_INTOUT) == vdi.VDI_DEV_TAB_WORDS
    assert result.linea("RETSAV") == H["VDI_OPNVWK_MALLOC_RETURN"]


def test_each_open_appends_the_next_handle():
    assert ws.handles(chain()["open C"]) == [1, 2, 3, 4]


def test_closing_the_middle_record_unlinks_it_and_gives_it_back():
    result = chain()["close B"]
    b = record("open B")
    assert ws.list_of(result.final) == [(vdi.VDI_PHYS_WORK, 1), (record("open A"), 2), (record("open C"), 4)]
    assert result.linea("RETSAV") == H["VDI_CLSVWK_MFREE_RETURN"]
    assert b not in {descriptor.start for descriptor in mem.allocated_list(result.final)}


def test_an_open_over_the_gap_takes_its_handle_but_appends_after_the_record_it_stopped_at():
    """1, 2, 4: the walk stops ON the 4 (3 is not its handle) and links the new record after it — 1, 2, 4, 3."""
    assert ws.handles(chain()["open D"]) == [1, 2, 4, 3]


def test_the_open_after_that_takes_the_same_handle_again():
    """...and stops on the 4 again, which now has a next: the second 3 is INSERTED between the 4 and the first 3."""
    result = chain()["open E"]
    records = [at for at, _handle in ws.list_of(result.final)]
    assert ws.handles(result) == [1, 2, 4, 3, 3]
    assert records == [vdi.VDI_PHYS_WORK, record("open A"), record("open C"), record("open E"), record("open D")]


def test_malloc_failing_answers_handle_0_and_changes_nothing_else():
    exhausted = mem.stage([(mem.USED, mem.SNAPSHOT_FREE_MD.length)], rover_span=None).pokes
    stale = vdi.linea_pokes(CUR_WORK=vdi.VIRTUAL_WORK_AT)
    result = ws.through_gemdos(ws.OPNVWK, merge_pokes(call_over(ws.OPNVWK, exhausted), stale))
    assert result.contrl(vdi.CONTRL_HANDLE) == 0
    assert current(result) == vdi.VIRTUAL_WORK_AT
    assert result.workstation("NEXT") == 0
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 0, "init_wk never ran"


def test_the_physical_workstation_is_never_closed_as_a_virtual_one():
    result = close_over({}, vdi.VDI_PHYS_WORK)
    assert result.linea("RETSAV") == vdi_helpers.RETSAV_STALE_VALUE
    assert result.workstation("NEXT") == 0


def test_closing_the_only_virtual_record_empties_the_list():
    opened = chain()["open A"]
    result = close_over(case.continued(opened), current(opened))
    assert ws.list_of(result.final) == [(vdi.VDI_PHYS_WORK, 1)]


def test_closing_the_last_record_walks_past_two():
    """4 out of 1, 2, 3, 4: the walk crosses two links before the record whose WS_NEXT holds handle 4."""
    opened = chain()["open C"]
    result = close_over(case.continued(opened), current(opened))
    assert ws.handles(result) == [1, 2, 3]


def test_closing_the_second_of_two_3s_unlinks_the_first():
    """1, 2, 4, 3, 3: the walk stops at the FIRST record whose next holds a 3 — the 4 — and points it past the record
    being closed, the SECOND 3, which is last: the first 3 falls off the list, still allocated, and the second is freed."""
    opened = chain()["open E"]
    first, second = record("open E"), record("open D")
    result = close_over(case.continued(opened), second)
    assert ws.list_of(result.final) == [(vdi.VDI_PHYS_WORK, 1), (record("open A"), 2), (record("open C"), 4)]
    allocated = {descriptor.start for descriptor in mem.allocated_list(result.final)}
    assert first in allocated and second not in allocated


def test_malloc_is_asked_for_a_whole_record():
    """The one word v_opnvwk hands GEMDOS, seen by the candidate's Malloc handler (the pool rounds 307 up to 308 as
    well, so the pool alone could not tell them apart)."""
    seen = []
    malloc = vdi_helpers.GEMDOS_HANDLERS[gemdos.rom_handler(addrs.GEMDOS_MALLOC_FN)]

    def spy(buf, arguments, argument_bytes):
        seen.append(case.long_in(bytes(buf[arguments:arguments + vdi.LONG_BYTES]), 0))
        return malloc(buf, arguments, argument_bytes)

    ws.through_the_door(ws.OPNVWK, call_over(ws.OPNVWK, FRESH_TPA),
                        {**vdi_helpers.GEMDOS_HANDLERS, gemdos.rom_handler(addrs.GEMDOS_MALLOC_FN): spy},
                        dropped_windows=vdi_helpers.GEMDOS_DOOR_WINDOWS)
    assert seen == [vdi.WS_BYTES]


# ---- v_clswk ------------------------------------------------------------------------------------------------------

def clswk_over(previous):
    """v_clswk over `previous`, with restore_timer_mouse's world staged as the screen battery's close stages it."""
    return ws.through_gemdos(ws.CLSWK, call_over(ws.CLSWK, merge_pokes(previous, screen.restore_pokes())))


def test_v_clswk_gives_every_virtual_record_back_in_list_order():
    """Four records — the chain's end — each Mfree'd; LINEA_CUR_WORK walked to 0, and the physical record's
    WS_NEXT still naming the first of them; then the timer given back."""
    opened = chain()["open E"]
    freed = [at for at, _handle in ws.list_of(opened.final)][1:]
    result = clswk_over(case.continued(opened))
    assert current(result) == 0
    assert result.workstation("NEXT") == freed[0]
    assert not set(freed) & {descriptor.start for descriptor in mem.allocated_list(result.final)}
    assert result.linea("RETSAV") == H["VDI_CLSWK_MFREE_RETURN"]
    assert result.long(addrs.SYSVAR_ETV_TIMER) == screen.SNAPSHOT_NEXT_TIM


def test_v_clswk_with_no_virtual_record_only_gives_the_timer_back():
    result = clswk_over(vdi.linea_pokes(CUR_WORK=vdi.VDI_PHYS_WORK))
    assert current(result) == vdi.VDI_PHYS_WORK
    assert result.linea("RETSAV") == vdi_helpers.RETSAV_STALE_VALUE
    assert result.long(addrs.SYSVAR_ETV_TIMER) == screen.SNAPSHOT_NEXT_TIM


# ---- the registry -------------------------------------------------------------------------------------------------
# PRICED where no GEMDOS call is made: the physical record's refused close, and v_clswk with none open (whose cost is
# restore_timer_mouse's clear). Every row that takes the `trap #1` is priced over the STAGED handler, answering what
# the real GEMDOS answered there, with LINEA_RETSAV dropped from its Tier 3 compare (`vdi_workstation.py` says why).
# The chained rows' staging is the ORACLE's chain (`played(oracle_step)`), which the differential chain above proves.
ORACLE_CHAIN = played(oracle_step)
vdi.register("vdi_v_clsvwk, the physical workstation", addrs.VDI_ROM_V_CLSVWK, call_over(ws.CLSVWK, {}))
vdi.register("vdi_v_clswk, none open", addrs.VDI_ROM_V_CLSWK,
             call_over(ws.CLSWK, merge_pokes(vdi.linea_pokes(CUR_WORK=vdi.VDI_PHYS_WORK), screen.restore_pokes())))

# (case, function, the machine, what the staged `trap #1` answers). The opens: the first, and the worst realistic —
# the duplicate insert, whose walk passes three records and stops on one that has a next; Malloc refused. The closes:
# the middle one, and the last of four (two links walked); v_clswk freeing four.
TRAP_ROWS = (
    ("vdi_v_opnvwk, the first", ws.OPNVWK, ORACLE_CHAIN["open A"].pokes, ORACLE_CHAIN["open A"].current),
    ("vdi_v_opnvwk, a second 3 inserted", ws.OPNVWK, ORACLE_CHAIN["open E"].pokes, ORACLE_CHAIN["open E"].current),
    ("vdi_v_opnvwk, Malloc refused", ws.OPNVWK, call_over(ws.OPNVWK, vdi.linea_pokes(CUR_WORK=vdi.VIRTUAL_WORK_AT)), 0),
    ("vdi_v_clsvwk, the middle one", ws.CLSVWK, ORACLE_CHAIN["close B"].pokes, ws.GEMDOS_OK),
    ("vdi_v_clsvwk, the last of four", ws.CLSVWK,
     call_over(ws.CLSVWK, ORACLE_CHAIN["open C"].left, ORACLE_CHAIN["open C"].current), ws.GEMDOS_OK),
    ("vdi_v_clswk, four open", ws.CLSWK,
     call_over(ws.CLSWK, merge_pokes(ORACLE_CHAIN["open E"].left, screen.restore_pokes())), ws.GEMDOS_OK),
)


# Every call the staged handler must have been trapped with, in order, per function: Malloc(308); Mfree of the current
# record (v_clsvwk); Mfree of each virtual record in list order (v_clswk).
def _expected_traps(name, pokes):
    if name == ws.OPNVWK:
        return [(addrs.GEMDOS_MALLOC_FN, vdi.WS_BYTES)]
    image = vdi.make_image(pokes)
    if name == ws.CLSVWK:
        return [(addrs.GEMDOS_MFREE_FN, case.long_in(image, vdi.LINEA_CUR_WORK))]
    return [(addrs.GEMDOS_MFREE_FN, record) for record, _handle in ws.list_of(image)[1:]]


def _proved_over_the_staged_trap(label, name, pokes, answer):
    """The registered trap row `label`, run as a differential with nothing dropped: RETSAV parked with the ROM's
    return site, and the handler's ledger — every call, the function and the longword — the same on both sides and
    the calls the ROM makes."""
    result = ws.through_staged_trap(name, pokes, answer)
    registered, = (row for row in vdi.CASES if row[0] == label)
    assert vdi.make_image(registered[3]) == vdi.make_image(result.staged), "the row is not the machine proved here"
    assert vdi_helpers.trapped_calls(result.final) == _expected_traps(name, pokes), label
    assert result.linea("RETSAV") != vdi_helpers.RETSAV_STALE_VALUE, "the door parked its return"
    return result


# Each row's `_proved_over_the_staged_trap` is its registered companion, which `test_tier3.py` runs.
for _label, _name, _pokes, _answer in TRAP_ROWS:
    vdi.register(_label, getattr(addrs, _name), merge_pokes(_pokes, vdi_helpers.staged_gemdos_trap_pokes(_answer)),
                 dropped=ws.RETSAV_DROPPED,
                 undropped=functools.partial(_proved_over_the_staged_trap, _label, _name, _pokes, _answer))


def test_the_registered_rows_stage_the_chain_the_differentials_prove():
    """The rows above are staged from the ORACLE's chain (importable before any build); this holds it to the chain
    of differentials step for step, so each row is a machine a proved run left."""
    proved = played(differential_step)
    assert {step: played_step.pokes for step, played_step in ORACLE_CHAIN.items()} == \
        {step: played_step.pokes for step, played_step in proved.items()}
