"""The VDI's `trap #2` entry ($fc9f9e) and its dispatcher ($fca9f6): `src/vdi/entry.c` (`test/vdi_entry.py` says how).

    vdi_entry     movem.l d1-a6 / a2 = contrl, a4 = the caller's ptsin, the five pointers into Line-A with PTSIN
                  the copy at VDI_PTSIN_COPY / n = contrl[1]: 2n words (a WORD), capped unsigned at 1024 — the cap
                  writing 512 into the caller's contrl[1] — copied / jsr $fca9f6 / contrl[1] = n through
                  LINEA_CONTRL read again / movem back / d0.w = VDI_RESULT
    vdi_dispatch  a5 = CONTRL / handle, opcode read / contrl[2], contrl[4], VDI_RESULT cleared / unless 1 or 100:
                  the list from the physical record walked for the handle (none: return), CUR_WORK and the copies /
                  1..39 through $fd372c, 100..131 through $fd37c8, signed; anything else called nothing

THE LIST IS BUILT, NOT STAGED: the machine the virtual-workstation chain leaves (`test_vdi_workstation_virtual.py`,
five opens and a close), whose handles run 1, 2, 4, 3, 3 — v_opnvwk's duplicate included — each record given a write
mode and clip of its own, as vswr_mode and vs_clip would, so a copy from the wrong record is a wrong word.
"""
import os

import re

import pytest

from harness import addrs, emu, make_image

import aes_switch as switch
import case
import gemdos
import test_vdi_workstation_virtual as virtual
import transcription
import vdi
import vdi_entry as entry
import vdi_helpers
import vdi_workstation as ws
from case import merge_pokes

# ---- the machine ------------------------------------------------------------------------------------------------
CHAIN = virtual.ORACLE_CHAIN["open E"]
CHAIN_RECORDS = [at for at, _handle in ws.list_of(vdi.make_image(CHAIN.left))]
CHAIN_HANDLES = [handle for _at, handle in ws.list_of(vdi.make_image(CHAIN.left))]
assert CHAIN_HANDLES == [1, 2, 4, 3, 3], "the chain no longer leaves v_opnvwk's duplicate handle"
FIRST_OF_THE_THREES = CHAIN_RECORDS[3]
UNKNOWN_HANDLE = 5


def distinct_records():
    """Each record on the chain's list given its own write mode and clip rectangle (vswr_mode, vs_clip)."""
    fields = {}
    for index, at in enumerate(CHAIN_RECORDS):
        fields = merge_pokes(fields, vdi.field_pokes("WS", at, WRT_MODE=index % 4, CLIP=index & 1, XMN_CLIP=index,
                                                     YMN_CLIP=2 * index, XMX_CLIP=300 - index, YMX_CLIP=190 - index))
    return fields


LIST = merge_pokes(CHAIN.left, distinct_records())


def nop_over(handle, machine=LIST, **kwargs):
    return entry.run_dispatch(entry.dispatch_pokes(addrs.VDI_ROM_NOP_OPCODE, handle, machine, **kwargs), entry.NOP)


def assert_made_current(result, work):
    """CUR_WORK and every copy the dispatcher makes are `work`'s — `vdi.dispatcher_copies`, the mirror every other
    battery stages from, which this holds to the C (and the ROM) that makes them."""
    assert result.linea("CUR_WORK") == work
    for at, data in vdi.dispatcher_copies(result.final, work).items():
        assert result.after(at, len(data)) == data, f"{at:#x} is not the copy of the current record"


def assert_untouched(result):
    """Nothing the lookup would have stored: CUR_WORK and every copy still stale."""
    for at, data in entry.stale_dispatch().items():
        if at != vdi.VDI_RESULT:
            assert result.after(at, len(data)) == data, f"{at:#x} was stored with no workstation found"


def assert_cleared(result, contrl_at=vdi.CONTRL_AT):
    assert result.word(contrl_at + vdi.CONTRL_N_PTSOUT) == 0 and result.word(contrl_at + vdi.CONTRL_N_INTOUT) == 0
    assert result.word(vdi.VDI_RESULT) == 0


# ==== vdi_dispatch: the lookup ======================================================================================

@pytest.mark.parametrize("position", (0, 1, 2), ids=("the physical record", "one link", "two links"))
def test_the_handle_is_found_along_the_list_and_made_current(position):
    result, calls = nop_over(CHAIN_HANDLES[position])
    assert calls == [addrs.VDI_ROM_NOP]
    assert_cleared(result)
    assert_made_current(result, CHAIN_RECORDS[position])


def test_of_two_records_with_one_handle_the_first_on_the_list_wins():
    """v_opnvwk's duplicate: the walk stops at the FIRST 3, three links along, and never sees the second."""
    result, _calls = nop_over(3)
    assert_made_current(result, FIRST_OF_THE_THREES)


def test_an_unknown_handle_walks_the_whole_list_and_returns_having_called_nothing():
    """$fcaa3c: the last WS_NEXT is 0 — no record current, no copy, no call; the clears already made."""
    result, calls = nop_over(UNKNOWN_HANDLE)
    assert calls == []
    assert_cleared(result)
    assert_untouched(result)


def test_the_snapshot_s_own_list_is_the_physical_record_alone():
    result, _calls = nop_over(vdi.VDI_PHYS_HANDLE, machine=None)
    assert_made_current(result, vdi.VDI_PHYS_WORK)


def test_the_handle_is_compared_as_a_whole_word():
    """A handle whose low byte is a record's (the physical one's 1) matches nothing: `cmp.w`, not `cmp.b`."""
    result, calls = nop_over(0x0100 | vdi.VDI_PHYS_HANDLE)
    assert calls == []
    assert_untouched(result)


def test_a_handle_with_a_high_byte_is_matched_as_a_whole_word():
    """...and the other way round: a record holding $0101 is found for $0101, its high byte compared too."""
    handle = 0x0100 | vdi.VDI_PHYS_HANDLE
    machine = merge_pokes(LIST, vdi.field_pokes("WS", CHAIN_RECORDS[1], HANDLE=handle))
    result, calls = nop_over(handle, machine)
    assert calls == [addrs.VDI_ROM_NOP]
    assert_made_current(result, CHAIN_RECORDS[1])


def test_the_counts_are_cleared_before_the_walk_reads_a_record_they_lie_over():
    """contrl laid 32 bytes into the second record, so contrl[4] IS that record's WS_HANDLE: cleared first, the walk
    no longer finds the record by the handle contrl[6] asked for, and goes on to the next that has it — none."""
    second = CHAIN_RECORDS[1]
    contrl_at = second + vdi.WS_HANDLE - vdi.CONTRL_N_INTOUT
    pokes = merge_pokes(entry.dispatch_pokes(addrs.VDI_ROM_NOP_OPCODE, CHAIN_HANDLES[1], LIST, contrl_at=contrl_at),
                        {contrl_at + vdi.CONTRL_N_INTOUT: vdi.pack_words(CHAIN_HANDLES[1])})
    assert vdi.make_image(pokes)[second + vdi.WS_HANDLE + 1] == CHAIN_HANDLES[1], "the record holds the handle asked"
    result, calls = entry.run_dispatch(pokes, entry.NOP)
    assert result.workstation("HANDLE", second) == 0
    assert calls == []
    assert_untouched(result)


def test_contrl_2_is_cleared_before_the_walk_reads_a_record_it_lies_over():
    """The same with contrl[2] as the physical record's WS_HANDLE: cleared first, handle 1 matches no record."""
    contrl_at = vdi.VDI_PHYS_WORK + vdi.WS_HANDLE - vdi.CONTRL_N_PTSOUT
    pokes = merge_pokes(entry.dispatch_pokes(addrs.VDI_ROM_NOP_OPCODE, vdi.VDI_PHYS_HANDLE, contrl_at=contrl_at),
                        {contrl_at + vdi.CONTRL_N_PTSOUT: vdi.pack_words(vdi.VDI_PHYS_HANDLE)})
    result, calls = entry.run_dispatch(pokes, entry.NOP)
    assert calls == []
    assert_untouched(result)


# The ROM reads contrl[0] and contrl[6] BEFORE it clears contrl[2], contrl[4] and VDI_RESULT ($fcaa04..$fcaa12):
# contrl laid so that one of the two words it reads IS VDI_RESULT shows that order — the caller's word, not the 0.
@pytest.mark.parametrize("read", (vdi.CONTRL_HANDLE, vdi.CONTRL_OPCODE), ids=("the handle", "the opcode"))
def test_the_handle_and_the_opcode_are_read_before_vdi_result_is_cleared(read):
    contrl_at = vdi.VDI_RESULT - read
    pokes = entry.dispatch_pokes(addrs.VDI_ROM_NOP_OPCODE, vdi.VDI_PHYS_HANDLE, contrl_at=contrl_at)
    assert vdi.make_image(pokes)[vdi.VDI_RESULT:vdi.VDI_RESULT + vdi.WORD_BYTES] != bytes(vdi.WORD_BYTES)
    result, calls = entry.run_dispatch(pokes, entry.NOP)
    assert calls == [addrs.VDI_ROM_NOP]
    assert result.linea("CUR_WORK") == vdi.VDI_PHYS_WORK
    assert result.word(vdi.VDI_RESULT) == 0


RECORD_OVER_RESULT = vdi.VDI_RESULT - vdi.WS_HANDLE


def test_vdi_result_is_cleared_before_the_walk_reads_a_handle_on_it():
    """A record linked behind the physical one whose WS_HANDLE IS VDI_RESULT: cleared to 0 first, it is found for
    handle 0 — which no record held when the call was made."""
    machine = merge_pokes(vdi.field_pokes("WS", vdi.VDI_PHYS_WORK, NEXT=RECORD_OVER_RESULT),
                          vdi.field_pokes("WS", RECORD_OVER_RESULT, NEXT=0, CUR_FONT=vdi.FONT_AT),
                          vdi.font_pokes(FLAGS=0))
    pokes = entry.dispatch_pokes(addrs.VDI_ROM_NOP_OPCODE, 0, machine)
    assert vdi.make_image(pokes)[vdi.VDI_RESULT:vdi.VDI_RESULT + vdi.WORD_BYTES] != bytes(vdi.WORD_BYTES), "stale"
    result, calls = entry.run_dispatch(pokes, entry.NOP)
    assert calls == [addrs.VDI_ROM_NOP]
    assert result.linea("CUR_WORK") == RECORD_OVER_RESULT


# ==== vdi_dispatch: the copies ===================================================================================

@pytest.mark.parametrize("interior,multifill,expected", ((vdi.VDI_INTERIOR_USER, 1, 1), (vdi.VDI_INTERIOR_USER, 0, 0),
                                                         (vdi.VDI_INTERIOR_HATCH, 1, 0)))
def test_multifill_is_copied_for_the_user_interior_alone(interior, multifill, expected):
    machine = merge_pokes(LIST, vdi.field_pokes("WS", CHAIN_RECORDS[2], FILL_STYLE=interior, MULTIFILL=multifill))
    result, _calls = nop_over(CHAIN_HANDLES[2], machine)
    assert result.linea("MULTIFILL") == expected


@pytest.mark.parametrize("flags", (0, vdi.FONT_FLAG_MONOSPACE_MASK, 0xFFFF), ids=("proportional", "mono", "every flag"))
def test_mono_status_is_the_current_font_s_monospace_bit(flags):
    """The font a GDOS face made current (vst_font): its FLAGS through the CUR_FONT just copied."""
    machine = merge_pokes(LIST, vdi.font_pokes(FLAGS=flags), vdi.field_pokes("WS", CHAIN_RECORDS[1], CUR_FONT=vdi.FONT_AT))
    result, _calls = nop_over(CHAIN_HANDLES[1], machine)
    assert result.linea("MONO_STATUS") == flags & vdi.FONT_FLAG_MONOSPACE_MASK


# THE ORDER, over records laid across what the dispatcher STORES — which no open makes: `vdi_entry.overlay_pokes` says
# why, and models the ROM's sequence. Each placement below (a record address, and whether its interior is the user's,
# so MULTIFILL is a copy) was found by `vdi_entry.search_order_placements`; between them they tell every adjacent
# pair of the ROM's steps apart but one — the two stores of WS_CLIP, one value read once, which commute everywhere.
ORDER_PLACEMENTS = ((0x16DE, False), (0x16E8, False), (0x1704, False), (0x2586, False), (0x25CA, False),
                    (0x26C4, False), (0x26F2, False), (0x27B6, True), (0x27CA, False), (0x288C, False), (0x28A2, False),
                    (0x28A4, False), (0x28A6, False), (0x29A8, True), (0x29BC, False), (0x29C0, False), (0x29C8, True),
                    (0x29E4, False), (0x29EE, False))
COMMUTING_PAIRS = [1]
_LOWEST = min((at for at, _user in ORDER_PLACEMENTS), default=vdi.LINEA_BLOCK_START)
_HIGHEST = max((at for at, _user in ORDER_PLACEMENTS), default=vdi.LINEA_BLOCK_START) + vdi.WS_BYTES
vdi.declare_case_field(_LOWEST, max(_HIGHEST, vdi.LINEA_BLOCK_END) - _LOWEST,
                       "the records laid over the dispatcher's destinations, below and past the Line-A block")


def test_the_rom_makes_its_stores_in_the_order_the_model_steps_through():
    """What the placements below rest on: the model's steps (`vdi.DISPATCH_STEPS`, the one list every mirror folds)
    ARE the ROM's. Its first store to each destination, in the order the oracle logged them — every step's, the two
    of WS_CLIP's one value included, so no pair of the mirror can be exchanged unseen."""
    steps = vdi.DISPATCH_STEPS
    step_of = {step.destination + offset: index for index, step in enumerate(steps) for offset in range(step.width)}
    pokes = entry.dispatch_pokes(addrs.VDI_ROM_NOP_OPCODE, CHAIN_HANDLES[2], LIST)
    _final, writes, left = emu.run(make_image(pokes), addrs.VDI_ROM_DISPATCH, {})
    assert not left["writes_truncated"]
    order = []
    for address in writes:              # insertion order: each byte's first store
        index = step_of.get(address)
        if index is not None and index not in order:
            order.append(index)
    assert order == list(range(len(steps))), [hex(steps[index].destination) for index in order]
    unstepped = sorted(set(writes) - set(step_of) - set(BEFORE_THE_LOOKUP) - set(range(emu.STACK_GUARD_LO, emu.STACK_TOP)))
    assert not unstepped, f"the ROM stores {[hex(at) for at in unstepped]}, which no step of the list makes"


# The stores the dispatcher makes BEFORE the lookup, and so outside the steps: contrl[2], contrl[4] and VDI_RESULT.
BEFORE_THE_LOOKUP = [at + offset for at in (vdi.CONTRL_AT + vdi.CONTRL_N_PTSOUT, vdi.CONTRL_AT + vdi.CONTRL_N_INTOUT,
                                            vdi.VDI_RESULT) for offset in range(vdi.WORD_BYTES)]


# THE SEARCH the placements came from is under a minute of the model alone, so it runs on request: RUN_SLOW=1.
SLOW = pytest.mark.skipif(not os.environ.get("RUN_SLOW"), reason="the placement search; RUN_SLOW=1 runs it")


@SLOW
def test_the_placements_are_what_the_search_finds():
    """ORDER_PLACEMENTS and COMMUTING_PAIRS are `vdi_entry.search_order_placements`'s answer today: a step added,
    dropped or moved in `vdi.DISPATCH_STEPS` re-runs the search rather than leaving a hand-copied list behind."""
    chosen, uncovered = entry.search_order_placements()
    assert sorted(chosen) == sorted(ORDER_PLACEMENTS)
    assert uncovered == COMMUTING_PAIRS


def test_the_placements_tell_every_pair_of_steps_apart_but_the_clip_s_two():
    told = set().union(*(entry.pairs_told_apart(at, user) for at, user in ORDER_PLACEMENTS))
    assert sorted(set(range(len(vdi.DISPATCH_STEPS) - 1)) - told) == COMMUTING_PAIRS


@pytest.mark.parametrize("at,user_interior", ORDER_PLACEMENTS,
                         ids=[f"{at:#x}{', user' if user else ''}" for at, user in ORDER_PLACEMENTS])
def test_a_record_over_the_destinations_is_copied_in_the_rom_s_order(at, user_interior):
    result, calls = entry.run_dispatch(entry.overlay_pokes(at, user_interior), entry.NOP)
    assert calls == [addrs.VDI_ROM_NOP]
    assert result.linea("CUR_WORK") == at
    assert result.linea("CUR_FONT") == vdi.FONT_AT, "the model steered the copies to the staged font"
    assert result.linea("MONO_STATUS") == vdi.FONT_FLAG_MONOSPACE_MASK


# Records whose CUR_FONT field only PARTLY overlaps LINEA_CUR_FONT (a word below it, a word above): the copy's store
# changes half the field, so the record read again after it names another font than the one LINEA_CUR_FONT holds.
PART_OVER_CUR_FONT = (vdi.LINEA_CUR_FONT - vdi.WS_CUR_FONT - vdi.WORD_BYTES,
                      vdi.LINEA_CUR_FONT - vdi.WS_CUR_FONT + vdi.WORD_BYTES)


@pytest.mark.parametrize("at", PART_OVER_CUR_FONT, ids=[f"{at:#x}" for at in PART_OVER_CUR_FONT])
def test_mono_status_is_read_through_linea_cur_font_not_the_record(at):
    pokes = entry.overlay_pokes(at)
    assert pokes is not None, f"a record at {at:#x} can no longer be steered to the staged font"
    result, calls = entry.run_dispatch(pokes, entry.NOP)
    assert calls == [addrs.VDI_ROM_NOP]
    assert result.linea("CUR_FONT") == vdi.FONT_AT
    assert result.workstation("CUR_FONT", at) != vdi.FONT_AT, "the record names another font after the store"
    assert result.linea("MONO_STATUS") == vdi.FONT_FLAG_MONOSPACE_MASK


# ==== vdi_dispatch: the opcode ranges ============================================================================
# Opcodes past both tables (and 0, and negative ones) make the workstation current and call nothing.
UNSERVED = (0, 40, 99, 132, -1, -0x8000, 0x7FFF)


@pytest.mark.parametrize("opcode", UNSERVED)
def test_an_opcode_outside_both_tables_calls_nothing_after_the_copies(opcode):
    result, calls = nop_over_opcode(opcode)
    assert calls == []
    assert_made_current(result, CHAIN_RECORDS[2])


def nop_over_opcode(opcode):
    return entry.run_dispatch(entry.dispatch_pokes(opcode, CHAIN_HANDLES[2], LIST), entry.NOP)


# The last of each table, and the first of the second, end to end: the ROM's function against its C, run where the
# dispatcher's `jsr` lands. (1 and 100 are the opens, below.)
ALIGNMENT, FONTINFO, PERIMETER = "VDI_ROM_VST_ALIGNMENT", "VDI_ROM_VQT_FONTINFO", "VDI_ROM_VSF_PERIMETER"


def end_to_end(name, intin=(), at=vdi.VDI_PHYS_WORK, machine=None):
    """`addrs.<name>`'s call on the record at `at` over `machine`, entered at the dispatcher with the copies stale."""
    return entry.over_a_call(vdi.function_pokes(name, intin, workstation_pokes=vdi.dispatched_pokes(at, onto=machine)))


@pytest.mark.parametrize("name,intin", ((ALIGNMENT, (2, 5)), (FONTINFO, ()), (PERIMETER, (0x0100,))))
def test_the_edges_of_the_tables_reach_their_functions(name, intin):
    result, calls = entry.run_dispatch(end_to_end(name, intin), entry.function(name))
    assert calls == [getattr(addrs, name)]
    assert result.linea("CUR_WORK") == vdi.VDI_PHYS_WORK, "the function's own stores are the differential's to compare"


def test_a_virtual_workstation_s_call_lands_in_its_record():
    """vsf_perimeter on the second record: the dispatcher made it current, and the function's store lands in it."""
    machine = merge_pokes(LIST, vdi.field_pokes("WS", CHAIN_RECORDS[1], FILL_PER=vdi.STALE_WORD))
    result, _calls = entry.run_dispatch(end_to_end(PERIMETER, (1,), CHAIN_RECORDS[1], machine), entry.function(PERIMETER))
    assert result.contrl(vdi.CONTRL_HANDLE) == CHAIN_HANDLES[1]
    assert result.workstation("FILL_PER", CHAIN_RECORDS[1]) == 1


# ---- the two opens: served with NO lookup, so an unknown handle still reaches them ------------------------------
def test_v_opnwk_is_called_whatever_the_handle():
    """The handle is the stale word v_opnwk's own staging leaves (`vdi_workstation.opnwk_pokes`): no record has it,
    and the open still runs — the lookup, and its silent return, are skipped for opcode 1."""
    staged = merge_pokes(ws.opnwk_pokes(), {vdi.VDI_RESULT: entry.WORD.pack(vdi.STALE_WORD),
                                            vdi.CONTRL_AT + vdi.CONTRL_N_PTSOUT: entry.WORD.pack(vdi.STALE_WORD)})
    result, calls = entry.run_dispatch(staged, entry.function(ws.OPNWK), io_seed=ws.opnwk_io(0),
                                       **vdi.READS_A_POINTER_IT_WRITES)
    assert calls == [addrs.VDI_ROM_V_OPNWK]
    assert result.contrl(vdi.CONTRL_HANDLE) == vdi.VDI_PHYS_HANDLE


def opnvwk_pokes():
    """The chain's first open, over the staged `trap #1`, with contrl[6] a handle no record has."""
    step = virtual.ORACLE_CHAIN["open A"]
    staged = merge_pokes(step.pokes, vdi_helpers.staged_gemdos_trap_pokes(step.current),
                         {vdi.CONTRL_AT + vdi.CONTRL_HANDLE: vdi.pack_words(UNKNOWN_HANDLE),
                          vdi.VDI_RESULT: entry.WORD.pack(vdi.STALE_WORD)})
    return staged, step.current


def test_v_opnvwk_is_called_whatever_the_handle():
    staged, record = opnvwk_pokes()
    with gemdos.bound_handlers(vdi_helpers.staged_gemdos_handlers(record)):
        result, calls = entry.run_dispatch(staged, entry.function(ws.OPNVWK), recording=gemdos.recording,
                                           **ws.UNPOISONED)
    assert calls == [addrs.VDI_ROM_V_OPNVWK]
    assert result.contrl(vdi.CONTRL_HANDLE) == ws.FIRST_VIRTUAL_HANDLE
    assert vdi_helpers.trapped_calls(result.final) == [(addrs.GEMDOS_MALLOC_FN, vdi.WS_BYTES)]


# ==== vdi_dispatch: its call of the function is its LAST ACT, and keeps no register ================================
# `call_vector_as_the_last_act` (`staged_call.h`): GCC is told the `jsr` changes D0, D1, A0, A1 — and a VDI function
# may change any register. That is sound only while NOTHING of the dispatcher's is live across the call in a register
# GCC believes kept, and only towards callers that need none kept: read off both blobs' own instructions.
_THE_CALL = "jsr %a0@"
_POPS_OR_RETURNS = re.compile(r"^(?:rts|movel %sp@\+,%[ad]\d|moveal %sp@\+,%a\d|moveml %sp@\+,\S+|addq[lw] #\d,%sp|lea %sp@\(\d+\),%sp)$")
_A_BRANCH_ALWAYS = re.compile(r"^(?:bra[swl]?|jra) ([0-9a-f]+) ")


def _after_each_call_of_the_function(blob):
    """For each `jsr (a0)` of `blob`'s vdi_dispatch: the instructions executed after it, to the `rts`, an
    unconditional branch followed."""
    body = switch.listed_functions(blob.elf)["vdi_dispatch"]
    at_index = {at: index for index, (at, _text) in enumerate(body)}
    runs = []
    for index, (_at, text) in enumerate(body):
        if text != _THE_CALL:
            continue
        after, here = [], index + 1
        while body[here][1] != "rts":
            jumped = _A_BRANCH_ALWAYS.match(body[here][1])
            here = at_index[int(jumped.group(1), 16)] if jumped else here + 1
            after += [] if jumped else [body[here - 1][1]]
        runs.append(after + ["rts"])
    return runs


def test_the_dispatcher_s_call_of_the_function_is_its_last_act_on_both_blobs(blob):
    """After each of the dispatcher's two `jsr (a0)` — one per table — the build does nothing but pop what its own
    prologue pushed and return: no register read, none moved, nothing stored. A value GCC kept in a call-saved
    register across the call (which a VDI function may have changed) would show here as an instruction of another kind."""
    runs = _after_each_call_of_the_function(blob)
    assert len(runs) == 2, f"vdi_dispatch calls a function at {len(runs)} places: one per opcode table was expected"
    for after in runs:
        assert all(_POPS_OR_RETURNS.match(text) for text in after), after
    # ...and the call is the bare `jsr`: no register saved round it (44 bytes under every VDI function when it was).
    body = [text for _at, text in switch.listed_functions(blob.elf)["vdi_dispatch"]]
    assert not [text for text in body if text.startswith("moveml ")], "the dispatcher saves a register file again"


def _names_the_dispatcher(text, blob):
    """`text` calls, jumps to or takes the address of `blob`'s vdi_dispatch — by its symbol, or by THE ROM'S address,
    which the transcribed entry spells and the staging (as a linked ROM would) lands in the blob's C."""
    return "<vdi_dispatch>" in text or f"{addrs.VDI_ROM_DISPATCH:x} <" in text


def test_the_entry_s_c_twin_keeps_every_register_round_the_dispatcher_as_the_rom_s_entry_does(blob):
    """The dispatcher gives the callee-saved registers back as a VDI function left them, so its C caller — the
    entry's twin — saves them all round its call (the ROM entry's own `movem.l d1-a6`): `movem` / the image pushed /
    `jsr vdi_dispatch` / the pop / `movem`, read off BOTH blobs (the shipped one links the twin weak, beside the
    entry's own instructions: were it ever the one entered, it keeps them there too)."""
    body = [text for _at, text in switch.listed_functions(blob.elf)["vdi_entry"]]
    call = next(index for index, text in enumerate(body) if text.startswith("jsr ") and _names_the_dispatcher(text, blob))
    assert body[call - 2] == "moveml %d2-%d7/%a2-%fp,%sp@-" and body[call + 2] == "moveml %sp@+,%d2-%d7/%a2-%fp", body[call - 2:call + 3]


def test_the_dispatcher_has_its_two_entries_for_callers_and_no_other_on_either_blob(blob):
    """THE CONTRACT'S OTHER HALF, HELD: a caller of `vdi_dispatch` gets D2-D7 / A2-A6 back as a VDI function left
    them, so every caller must need none kept. Each blob's listing names the dispatcher at exactly two places — the
    entry's C twin (inside its `movem` pair, above) and the transcribed entry, which has saved D1-A6 — and nowhere
    else, as a call, a jump or an address taken. A third caller in C would be handed registers GCC believes kept."""
    named = [(function, text) for function, body in switch.listed_functions(blob.elf).items() for _at, text in body
             if _names_the_dispatcher(text, blob)]
    assert sorted(function for function, _text in named) == ["vdi_entry", "vdi_rom_entry"], named
    assert all(text.startswith("jsr ") for _function, text in named), named
    rom_entry = [text for _at, text in switch.listed_functions(blob.elf)["vdi_rom_entry"]]
    call = next(index for index, text in enumerate(rom_entry) if _names_the_dispatcher(text, blob))
    assert "moveml %d1-%fp,%sp@-" in rom_entry[:call] and "moveml %sp@+,%d1-%fp" in rom_entry[call:]


# ==== vdi_entry ==================================================================================================
# Point counts: none (no copy), one, as many as the caller's band holds; the cap's three sides (1022, 1024 and 1026
# words — 2n is always even); a count whose doubled WORD wraps to 0 or 2 (no cap, and a copy of 0 or 2 words); and
# two whose doubled word is past the cap only UNSIGNED ($4000 -> $8000, and $ffff -> $fffe).
POINTS_IN_BAND = vdi.PTSIN_BYTES // vdi.VDI_POINT_BYTES
COUNTS = (0, 1, POINTS_IN_BAND - 1, entry.CAP_POINTS - 1, entry.CAP_POINTS, entry.PAST_THE_CAP, 0x8000, 0x8001, 0x4000, 0xFFFF)
CAP_WORDS = entry.CAP_WORDS


def words_copied(points):
    words = 2 * points & 0xFFFF
    return min(words, CAP_WORDS)


def source_for(points):
    """Where a count's points are staged: the caller's band while they fit, the screen (a declared field) past it."""
    return vdi.PTSIN_AT if words_copied(points) * vdi.WORD_BYTES + 4 <= vdi.PTSIN_BYTES else vdi.SCREEN.base


@pytest.mark.parametrize("points", COUNTS)
def test_the_caller_s_points_are_copied_capped_and_the_count_given_back(points):
    source = source_for(points)
    result, calls = entry.run_entry(entry.entry_pokes(addrs.VDI_ROM_NOP_OPCODE, points, source=source), entry.NOP)
    copied = words_copied(points)
    assert calls == [addrs.VDI_ROM_NOP]
    assert result.after(vdi.VDI_PTSIN_COPY, copied * vdi.WORD_BYTES) == entry.ramp(copied)
    if copied < CAP_WORDS:
        assert result.after(vdi.VDI_PTSIN_COPY + copied * vdi.WORD_BYTES, vdi.WORD_BYTES) == bytes([vdi.FILL]) * 2
    assert result.contrl(vdi.CONTRL_N_PTSIN) == points, "the caller's count is given back"
    assert [result.linea(name) for name in vdi.POINTER_VARIABLES] == [
        vdi.CONTRL_AT, vdi.INTIN_AT, vdi.VDI_PTSIN_COPY, vdi.INTOUT_AT, vdi.PTSOUT_AT]
    assert result.info["regs"]["d0"] & 0xFFFF == 0, "VDI_RESULT, cleared by the dispatcher"


def test_the_answer_is_what_the_function_left_in_vdi_result():
    """vsm_height answers one point and sets VDI_RESULT: ptsin[1], the height, read out of the COPY."""
    staged = entry.over_a_call(vdi.function_pokes("VDI_ROM_VSM_HEIGHT", workstation_pokes=vdi.dispatched_pokes()))
    staged = merge_pokes(staged, entry.entry_pokes(addrs.VDI_ROM_VSM_HEIGHT_OPCODE, 1))
    result, calls = entry.run_entry(staged, entry.function("VDI_ROM_VSM_HEIGHT"))
    assert calls == [addrs.VDI_ROM_VSM_HEIGHT]
    assert result.info["regs"]["d0"] & 0xFFFF == vdi.VDI_RESULT_SET


def test_the_cap_is_in_the_caller_s_contrl_while_the_function_runs():
    """v_pline over 513 points: it reads contrl[1] — 512 during the call, the copy's last point its last — and the
    caller's 513 is back after it. A cap left out of contrl[1] would draw a 513th point from past the copy."""
    points = entry.PAST_THE_CAP
    staged = entry.over_a_call(vdi.function_pokes("VDI_ROM_V_PLINE", workstation_pokes=vdi.dispatched_pokes()))
    staged = merge_pokes(staged, entry.entry_pokes(addrs.VDI_ROM_V_PLINE_OPCODE, points, source=vdi.SCREEN.base,
                                                   source_words=0),
                         {vdi.SCREEN.base: vdi.pack_words(*(value for index in range(points)
                                                            for value in (10 + index % 4, 20 + index * 3 % 5)))})
    result, calls = entry.run_entry(staged, entry.function("VDI_ROM_V_PLINE"))
    assert calls == [addrs.VDI_ROM_V_PLINE]
    assert result.contrl(vdi.CONTRL_N_PTSIN) == points


def test_the_copy_reads_the_count_the_cap_already_wrote():
    """The caller's ptsin IS its contrl: the cap stores 512 into contrl[1] BEFORE the copy reads that word."""
    points = 600
    staged = entry.entry_pokes(addrs.VDI_ROM_NOP_OPCODE, points, source=vdi.CONTRL_AT, source_words=0)
    result, _calls = entry.run_entry(staged, entry.NOP)
    assert result.word(vdi.VDI_PTSIN_COPY + vdi.CONTRL_N_PTSIN) == vdi.VDI_PTSIN_CAP_POINTS


def test_the_copy_runs_forwards_over_a_ptsin_just_below_it():
    """The caller's ptsin one word BELOW the copy: `move.w (a4)+,(a3)+` reads each word it stored a step before, so
    the copy is the first word repeated. A copy run backwards would move the caller's words up one."""
    source = vdi.VDI_PTSIN_COPY - vdi.WORD_BYTES
    points = 2
    words = (0x1111, 0x2222, 0x3333, 0x4444, 0x5555)
    staged = merge_pokes(entry.entry_pokes(addrs.VDI_ROM_NOP_OPCODE, points, source_words=0,
                                           block=entry.block_pokes(ptsin=source)),
                         {source: vdi.pack_words(*words)})
    result, calls = entry.run_entry(staged, entry.NOP)
    assert calls == [addrs.VDI_ROM_NOP]
    copied = 2 * points
    assert result.after(vdi.VDI_PTSIN_COPY, copied * vdi.WORD_BYTES) == vdi.pack_words(*[words[0]] * copied)


# $8200 points: the doubled word wraps to EXACTLY the copy's 1024 words — the cap's boundary, not past it — so no
# cap is written, and the copy of the caller's own contrl reads the count as the caller gave it.
AT_THE_CAP = 0x8200


def test_a_count_whose_doubled_word_is_the_cap_itself_writes_no_cap():
    staged = entry.entry_pokes(addrs.VDI_ROM_NOP_OPCODE, AT_THE_CAP, source=vdi.CONTRL_AT, source_words=0)
    result, _calls = entry.run_entry(staged, entry.NOP)
    assert result.word(vdi.VDI_PTSIN_COPY + vdi.CONTRL_N_PTSIN) == AT_THE_CAP


def test_a_block_over_the_line_a_pointers_is_read_after_each_store():
    """The parameter block AT LINEA_BASE: its first longword is PLANES and WIDTH, every later one the Line-A pointer
    the entry has just stored — so intin is contrl, ptsin is contrl too (and is copied from), intout and ptsout the
    copy."""
    planes_width = vdi.linea_pokes(PLANES=vdi.CONTRL_AT >> 16, WIDTH=vdi.CONTRL_AT & 0xFFFF)
    staged = merge_pokes(entry.entry_pokes(addrs.VDI_ROM_NOP_OPCODE, 2, source_words=0, block={}), planes_width)
    result, _calls = entry.run_entry(staged, entry.NOP, d1=vdi.LINEA_BASE)
    assert [result.linea(name) for name in vdi.POINTER_VARIABLES] == [
        vdi.CONTRL_AT, vdi.CONTRL_AT, vdi.VDI_PTSIN_COPY, vdi.VDI_PTSIN_COPY, vdi.VDI_PTSIN_COPY]
    assert result.after(vdi.VDI_PTSIN_COPY, 8) == vdi.pack_words(addrs.VDI_ROM_NOP_OPCODE, 2, vdi.STALE_WORD, 0)


def test_contrl_over_the_line_a_pointers_is_counted_after_they_are_stored():
    """contrl at LINEA_CONTRL + 2: contrl[1] is the HIGH word of the intin pointer the entry has just stored — 7 — and
    contrl[2]/[4], which the dispatcher clears, are the low words of LINEA_INTIN and LINEA_PTSIN. Its opcode ($29a0)
    serves nothing and its handle (intout's low word) is no record's; the count goes back into LINEA_INTIN."""
    contrl_at = vdi.LINEA_CONTRL + vdi.WORD_BYTES
    staged = merge_pokes(entry.stale_dispatch(), entry.stale_entry(), entry.block_pokes(contrl=contrl_at),
                         {vdi.PTSIN_AT: entry.ramp(2 * (vdi.INTIN_AT >> 16))})
    result, calls = entry.run_entry(staged)
    assert calls == []
    assert result.linea("INTIN") == vdi.INTIN_AT & ~0xFFFF and result.linea("PTSIN") == vdi.VDI_PTSIN_COPY & ~0xFFFF
    assert result.after(vdi.VDI_PTSIN_COPY, 4 * (vdi.INTIN_AT >> 16)) == entry.ramp(2 * (vdi.INTIN_AT >> 16))


# The contrl array a function MOVES by writing over LINEA_CONTRL: vsf_perimeter's intout laid over the pointer's high
# word stores its 1 there, so the function's own contrl[4] and the entry's give-back both follow the pointer AFTER it.
OUTLINED = 1                    # what vsf_perimeter stores for any nonzero flag
MOVED_CONTRL = OUTLINED << 16 | entry.MOVED_CONTRL_AT & 0xFFFF
vdi.declare_case_field(MOVED_CONTRL, vdi.CONTRL_BYTES, "the contrl vsf_perimeter's intout moves LINEA_CONTRL onto")


def test_the_count_is_given_back_through_linea_contrl_read_again():
    call = entry.entry_pokes(addrs.VDI_ROM_VSF_PERIMETER_OPCODE, 3, contrl_at=entry.MOVED_CONTRL_AT,
                             block=entry.block_pokes(contrl=entry.MOVED_CONTRL_AT, intout=vdi.LINEA_CONTRL))
    staged = merge_pokes(end_to_end(PERIMETER, (OUTLINED,)), call, {MOVED_CONTRL: bytes([vdi.FILL]) * vdi.CONTRL_BYTES})
    result, _calls = entry.run_entry(staged, entry.function(PERIMETER))
    assert result.linea("CONTRL") == MOVED_CONTRL
    assert result.word(MOVED_CONTRL + vdi.CONTRL_N_PTSIN) == 3
    assert result.word(entry.MOVED_CONTRL_AT + vdi.CONTRL_N_PTSIN) == 3, "...and the caller's own never capped"


def test_the_pointers_top_byte_is_kept_and_not_driven():
    """Every pointer of the block with its top byte set: stored as given, dereferenced on 24 lines."""
    high = 0xA5 << 24
    block = entry.block_pokes(contrl=high | vdi.CONTRL_AT, intin=high | vdi.INTIN_AT, ptsin=high | vdi.PTSIN_AT,
                              intout=high | vdi.INTOUT_AT, ptsout=high | vdi.PTSOUT_AT)
    result, _calls = entry.run_entry(entry.entry_pokes(addrs.VDI_ROM_NOP_OPCODE, 4, block=block), entry.NOP)
    assert result.linea("CONTRL") == high | vdi.CONTRL_AT
    assert result.after(vdi.VDI_PTSIN_COPY, 16) == entry.ramp(8)


# ==== the rows Tier 3 prices ======================================================================================
# The dispatcher: the snapshot's list, and the WORST realistic one — the first of the duplicate 3s, three links along.
# The entry: a call of no points, and the most a real call copies (the cap), each dispatched into the `rts`.
vdi.register("vdi_dispatch, the physical workstation", addrs.VDI_ROM_DISPATCH,
             entry.dispatch_pokes(addrs.VDI_ROM_NOP_OPCODE))
vdi.register("vdi_dispatch, three links along", addrs.VDI_ROM_DISPATCH,
             entry.dispatch_pokes(addrs.VDI_ROM_NOP_OPCODE, 3, LIST))
vdi.register("vdi_dispatch, an unknown handle", addrs.VDI_ROM_DISPATCH,
             entry.dispatch_pokes(addrs.VDI_ROM_NOP_OPCODE, UNKNOWN_HANDLE, LIST))
_ENTRY_REGS = {"d0": entry.VDI_SELECTOR, "d1": vdi.PARAMETER_BLOCK_AT}
vdi.register("vdi_entry, no points", addrs.VDI_ROM_ENTRY, entry.entry_pokes(addrs.VDI_ROM_NOP_OPCODE), regs=_ENTRY_REGS)
vdi.register("vdi_entry, one point", addrs.VDI_ROM_ENTRY, entry.entry_pokes(addrs.VDI_ROM_NOP_OPCODE, 1),
             regs=_ENTRY_REGS)
vdi.register("vdi_entry, the cap", addrs.VDI_ROM_ENTRY,
             entry.entry_pokes(addrs.VDI_ROM_NOP_OPCODE, entry.PAST_THE_CAP, source=vdi.SCREEN.base), regs=_ENTRY_REGS)
