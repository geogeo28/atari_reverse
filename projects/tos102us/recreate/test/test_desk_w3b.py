"""BAND 6 W3b — deskmain `$fe272e` IN C AND FLIPPED (`src/desk/desktop.c`, target-only: the user's R3, the orchestrator's
O1), its prep's pins held at the flip (the W3b cut's §7; `aes_desk_w3b.py`). What is held:

  * THE NAMES read off the ROM (O8): the three return sites deskmain's Line-F calls park, and the pointer pair it
    stores beside a_cmd / a_tail (`desk/deskglobals.h`: a_fcb1 / a_fcb2);
  * deskmain's SIGNATURE, TARGET-ONLY (O1), its table entry ITS THUNK on both blobs, and sh_main's desk door bound to
    that very thunk (O2) — the generator holding it the ROM's binds both back (the negative case);
  * THE HARNESS READING deskmain OFF THE DOOR'S BINDING — the our-boot's checkpoint and stop, the served door, who-ran,
    the start-up reading — at the thunk;
  * ITS ROWS (O3 / O7): A TARGET-ONLY ROW THAT SWITCHES OF THE PARKED KIND at each arrival (the user's ruling of
    2026-10-28: "a new target-only row kind that ends at the first idle"), from deskmain's entry to the desk's first
    idle — and the kind's own pins: a row of it whose ROM run returns, a run of it that never parks, one of another
    routine, one with a companion, each refused by name; the register check skipped for that kind alone;
  * U1 (a)'s LABEL: the ROM's deskmain loop in each desk turn of a ROM-booted row, pinned by its cycles;
  * THE ARMS NO ROW REACHES, by name (U2, O6).
"""
import ast
import inspect
import re
import textwrap
import types

import pytest

from harness import BASE_IMAGE, addrs, bench_tier3, make_image

import aes
import aes_boot
import aes_desk
import aes_desk_turns_pinned
import aes_desk_w3a as w3a
import aes_desk_w3b as w3b
import aes_deskarrive as da
import aes_event
import aes_ourboot as ob
import aes_stack
import aes_switching
import case
import rom_data
import routines
import test_desk_disk                           # noqa: F401  (the built-ins' rows: a re-entry's screen manager's provenance)
import test_desk_util                           # noqa: F401
import transcription
import vdi
from recreate_kit import rom_bench

DESKMAIN, ENTRY = w3b.DESKMAIN, w3b.DESKMAIN_ENTRY
INCLUDE = rom_data.RECREATE / "include" / "desk"
LINE_F_CALL_BYTES = aes.WORD_BYTES
LINE_F_MASK = 0xF000                    # a Line-F call word: `$F000 | the table entry's byte offset`
NEXT_ROUTINE = 0xFE2A7C                 # the AES map's next start after deskmain (846 bytes: the W3b cut's §1.1)


def _generator():
    import test_aes_desk_ours
    return test_aes_desk_ours._the_generator()


def _the_registry():
    """Every battery's rows (`test_boot_snapshot`) — imported where a test asks after all of them, not at the module's top:
    the registry imports this module, whose rows it registers."""
    import test_boot_snapshot   # noqa: F401
    return aes_event.every_switching_row()


def _blobs():
    tier3 = bench_tier3()
    return {"bench": tier3.RomBench(), "bench_shipped": tier3.shipped_bench()}


# ---- THE NAMES (O8) ---------------------------------------------------------------------------------------------------------------
def test_each_return_site_is_the_word_after_its_line_f_call_inside_deskmain():
    """Each return site of `desk/desktop.h`'s W3b block is the word after a Line-F call word of the routine named, inside
    deskmain's ROM body — read off the ROM's bytes."""
    constants = rom_data.constants_of(INCLUDE / "desktop.h")
    assert {name: constants[name] for name in w3b.RETURN_SITES} == {
        "AES_DESKMAIN_BLITMODE_ASKED_RETURN": 0xFE28EC, "AES_DESKMAIN_BLITMODE_SET_RETURN": 0xFE2946,
        "AES_DESKMAIN_GDRV_RETURN": 0xFE2A52}
    for name, callee in w3b.RETURN_SITES.items():
        site = constants[name]
        assert ENTRY < site < NEXT_ROUTINE, name
        word = case.word_in(BASE_IMAGE, site - LINE_F_CALL_BYTES)
        assert word & LINE_F_MASK == LINE_F_MASK, name
        assert case.long_in(BASE_IMAGE, aes.AES_LINEF_TABLE + (word & ~LINE_F_MASK)) == getattr(addrs, callee), name


# The four instructions of deskmain that store the pair ($fe27ba..$fe27c6): `lea d16(a5),a0` / `move.l a0,d16(a5)`.
LEA_A5_A0, MOVE_A0_TO_A5 = 0x41ED, 0x2B48


def test_the_fcb_pair_is_what_deskmain_stores_beside_a_cmd_and_a_tail():
    """a_fcb1 := g_fcb1 and a_fcb2 := g_fcb2: the names' offsets are the four instructions' displacements, in order."""
    constants = rom_data.constants_of(INCLUDE / "deskglobals.h")
    words = [case.word_in(BASE_IMAGE, at) for at in range(0xFE27BA, 0xFE27CA, aes.WORD_BYTES)]
    assert words == [LEA_A5_A0, constants["DESK_G_FCB1"], MOVE_A0_TO_A5, constants["DESK_A_FCB1"],
                     LEA_A5_A0, constants["DESK_G_FCB2"], MOVE_A0_TO_A5, constants["DESK_A_FCB2"]]
    assert constants["DESK_A_FCB1"] - constants["DESK_G_FCB1"] == constants["DESK_A_FCB2"] - constants["DESK_G_FCB2"] == 36


# ---- THE SIGNATURE, FLIPPED (O1, O2) ----------------------------------------------------------------------------------------------
def test_deskmain_is_declared_target_only_and_flipped_on_both_blobs():
    """`() -> word`, the image first; target-only (no host core); in the kind's routines; held by the generator no
    longer — its table entry its thunk — and on both blobs its core called by its own thunk (`aes_deskarrive.flipped`)."""
    generator = _generator()
    assert w3a.W3B == (DESKMAIN,) and DESKMAIN in w3a.TARGET_ONLY_ROUTINES and DESKMAIN not in w3a.W3A
    assert (vdi.ALCYON[DESKMAIN].restype, vdi.frame_argtypes(DESKMAIN)) == (aes.WORD_ANSWER, ())
    assert DESKMAIN in vdi.TARGET_ONLY and vdi.takes_image(DESKMAIN) and w3a.host_twin_of(DESKMAIN) is None
    assert DESKMAIN not in generator.held_back() and DESKMAIN in generator.thunked_routines()
    assert {(entry.verdict, entry.symbol) for entry in generator.entries() if entry.target == ENTRY} == {
        (generator.OURS_THROUGH_A_THUNK, generator.thunk_symbol(DESKMAIN))}
    for blob in _blobs().values():
        da.flipped(blob, (DESKMAIN,))


def test_the_door_binds_deskmain_as_the_table_does_and_holding_it_moves_both_back(monkeypatch):
    """O2: sh_main's door `jsr`s what the generated header binds deskmain to — ITS THUNK, on both blobs (the very thunk
    the table's entry names) — and the generator holding deskmain again (the prep's DECLARED_NOT_LINKED line put back)
    binds the door AND the entry to the ROM's routine (the negative case)."""
    generator = _generator()
    thunk = generator.thunk_symbol(DESKMAIN)
    assert transcription.DESK_DOOR_CALLERS[DESKMAIN] == "aes_sh_main" and thunk in transcription.DESK_DOOR_THUNKS
    assert f"#define {generator.DOOR_BOUND_PREFIX}{DESKMAIN} {thunk} " in generator.door_text()
    for blob in _blobs().values():
        at = blob.entry(thunk)
        assert transcription.desk_door_bindings(blob.elf)[ENTRY] == at and transcription.desk_door_thunked(blob.elf)[at] == ENTRY
    monkeypatch.setattr(generator, "DECLARED_NOT_LINKED", {**generator.DECLARED_NOT_LINKED, DESKMAIN: "held again (the test's)"})
    assert DESKMAIN not in generator.thunked_routines()
    assert f"#define {generator.DOOR_BOUND_PREFIX}{DESKMAIN} {DESKMAIN} " in generator.door_text()
    assert {entry.verdict for entry in generator.entries() if entry.target == ENTRY} == {generator.THE_ROM_S}


# ---- THE HARNESS READS deskmain OFF THE DOOR ---------------------------------------------------------------------------------------
A_THUNK = 0x123456                      # a stand-in for the door's thunk: where a flipped blob's door would enter deskmain


def test_the_harness_stands_where_the_door_enters_deskmain_its_thunk_once_flipped(monkeypatch):
    """The our-boot's checkpoints at deskmain stand AT_THE_DESK_DOOR; on both blobs that is DESKMAIN'S THUNK since the
    flip — the our-boot's stop (`aes_boot.deskmain_entry`), the checkpoint (`aes_ourboot.our_address`), the start-up
    reading's call out of the build (`aes_stack.the_desk_door_of`) — and the served door reads the thunk as deskmain.
    A blob whose door entered nothing for it (the prep's) stands at the ROM's address (the negative case)."""
    checkpoints = {*ob.THE_FIRST_PASS, *ob.THE_TEARDOWN_AND_THE_SECOND_PASS, *ob.A_BUILT_IN_PASS}
    at_the_desk = {each for each in checkpoints if each.what == ob.DESKMAIN_ENTERED}
    assert at_the_desk == {ob.Checkpoint(ob.DESKMAIN_ENTERED, ENTRY, ob.AT_THE_DESK_DOOR)}
    thunk = _generator().thunk_symbol(DESKMAIN)
    for blob in _blobs().values():
        ours = aes_boot.ours_of(blob)
        assert aes_boot.deskmain_entry(ours) == ob.our_address(*at_the_desk, blob) == blob.entry(thunk) != ENTRY
        assert aes_boot.routine_at(ours, blob.entry(thunk)) == ENTRY
        assert set(dict(ours.desk_door).values()) == set(aes_boot.SERVED_ROUTINES)
    held = ours._replace(desk_door=tuple((at, rom) for at, rom in ours.desk_door if rom != ENTRY))
    assert aes_boot.deskmain_entry(held) == ENTRY
    flipped = ours._replace(desk_door=(*held.desk_door, (A_THUNK, ENTRY)))
    assert aes_boot.deskmain_entry(flipped) == A_THUNK and aes_boot.routine_at(flipped, A_THUNK) == ENTRY
    assert aes_boot.deskmain_entry(None) == ENTRY and aes_boot.routine_at(None, A_THUNK) == A_THUNK
    elf = _blobs()["bench_shipped"].elf
    monkeypatch.setattr(transcription, "desk_door_thunked", lambda _elf: {A_THUNK: ENTRY})
    assert aes_stack.the_desk_door_of(elf)[A_THUNK] == aes_stack.DESKMAIN


def _stopped_at(at, call, ours):
    """A stand-in boot of a machine whose blob is `ours`, stopped at `at` in supervisor state, its return address the
    word after the shell's Line-F call word `call` — what the served door is handed."""
    sp = w3b.SP_AT_ITS_ENTRY
    ram = bytearray(sp + aes.LONG_BYTES)
    ram[sp:] = (call + aes.WORD_BYTES).to_bytes(aes.LONG_BYTES, "big")
    return types.SimpleNamespace(registers={"pc": at, "isp": sp, "sr": aes_boot.SR_SUPERVISOR}, idle=None, ram=bytes(ram),
                                 takeover=None, our_boot=types.SimpleNamespace(ours=ours))


def test_the_served_door_stands_at_a_flipped_built_in_s_thunk_as_its_routine_and_refuses_a_second_arrival_there():
    """THE SERVED DOOR READS THE DESK DOOR'S BINDING (review RW3P's R01 / R02): on each blob the four built-ins are
    entered at their thunks (F4's flip) — a boot stopped at one is vetted as standing at that routine (`routine_at`),
    and a served run's second arrival there is refused by the routine's name; no ROM address of a thunked routine is
    watched in its place."""
    for blob in _blobs().values():
        ours = aes_boot.ours_of(blob)
        door = dict(ours.desk_door)
        assert set(aes_boot.SERVED_ROUTINES) <= set(door.values())
        watched = aes_boot.second_arrivals_refused(ours, None)
        assert set(door) <= set(watched) and not set(door.values()) & set(watched)
        for thunk, routine in door.items():
            name, call = aes_boot.SERVED_ROUTINES[routine]
            assert watched[thunk][0] == name
            with pytest.raises(aes_boot.Refused, match=re.escape(f"THE RUN ARRIVED AT {name} AGAIN")):
                watched[thunk][1](None, None)
            stopped = _stopped_at(thunk, call, ours)
            assert aes_boot._vet_stands_at_a_served_entry(stopped) == (name, routine, call + aes.WORD_BYTES)


# ---- THE ROWS (O3, O7): ONE AT EACH ARRIVAL, OF THE PARKED KIND (the user's ruling of 2026-10-28) -----------------------------------
# THE FIVE RE-ENTRIES, UNPRICED BY NAME (THE USER'S RULING of 2026-10-28, quoted at `UNPRICED_RULING`): a re-entry's
# bring-up enters the screen manager, so its row would run with the screen manager OURS (FLIP 4's standing rule:
# `aes_takeover`) — and the machine after a built-in stands it where NO HISTORY OF OURS IS KNOWN TO LEAVE IT: no
# registered row's ROM run changes it into that state (measured: the built-ins' own rows start in it and run no turn of
# it), and the chain that did is no call our build can be run over. The refusal is the pinned reason
# (`aes_desk_w3b.NO_PROVENANCE`, `test_an_unpriced_arrival_is_refused_by_name`); the campaign walks hold their
# correctness (`test_aes_desk_ours.py`: deskmain's re-entry runs on every such chain of our shore); the bring-up is
# priced by the five first entries.
UNPRICED_RULING = ('"Unpriced by name": the 5 re-entry rows (viewer, Format EXIT, copy EXIT, two after a print) held UNPRICED '
                   'BY NAME (keep the NO_PROVENANCE refusal as the pinned reason); the campaign walks hold their correctness; '
                   'the bring-up priced by the 5 first-entry rows')
UNPRICED_BY_NAME = {label: w3b.NO_PROVENANCE for label, (_where, kind) in w3b.ARRIVALS.items() if kind == w3b.RE_ENTRY}
ROWS_AT = tuple(label for label in w3b.ARRIVALS if label not in UNPRICED_BY_NAME)
ROWS = {aes_switching.row_name(row): row for row in map(w3b.register_at_the_flip, ROWS_AT)}
FIRST_ENTRIES, RE_ENTRIES = 5, 5


def test_the_rows_are_five_first_entries_and_five_re_entries_two_of_them_on_the_printer_machine():
    kinds = [kind for _where, kind in w3b.ARRIVALS.values()]
    assert (kinds.count(w3b.FIRST_ENTRY), kinds.count(w3b.RE_ENTRY)) == (FIRST_ENTRIES, RE_ENTRIES)
    assert set(w3b.BOOTS) <= {w3b.THE_DESK_ALONE, *aes_desk.MACHINES} and all(chain in aes_desk.CHAINS for chain in w3b.RE_ENTRIES)


@pytest.mark.parametrize("label", w3b.ARRIVALS)
def test_each_row_s_arrival_is_the_shell_s_call_on_the_rom_s_stack_and_idles_before_deskmain_returns(label):
    arrived = w3b.vet_an_arrival(label)
    assert arrived.arguments == () and arrived.name == DESKMAIN


def test_an_arrival_elsewhere_is_refused_by_name(monkeypatch):
    """THE VET'S NEGATIVE CASE: the same machine with its return address not sh_main's — refused by the row's name."""
    label = next(iter(w3b.ARRIVALS))
    arrived = w3b.arrival(label)
    monkeypatch.setattr(w3b, "arrival", lambda _label: arrived._replace(returns_to=w3b.RETURNS_TO_SH_MAIN + aes.WORD_BYTES))
    with pytest.raises(AssertionError, match=re.escape(f"{label}: {w3b.NOT_THE_SHELL_S_CALL}")):
        w3b.vet_an_arrival(label)


def test_an_arrival_whose_run_returns_before_an_idle_is_refused_by_name(monkeypatch):
    """...AND THE IDLE PREMISE'S (review RW3P's R05): the same machine, the ROM's run from it standing in as one that
    returns from deskmain (a boot where `aes_deskarrive.returned_in_place` answers None at an idle) — refused by the
    row's name, for that reason."""
    label = next(iter(w3b.ARRIVALS))
    returned = w3b.arrival(label).boot
    monkeypatch.setattr(w3b.da, "returned_in_place", lambda _arrived: returned)
    with pytest.raises(AssertionError, match=re.escape(f"{label}: {w3b.RETURNS_BEFORE_AN_IDLE}")):
        w3b.vet_an_arrival(label)


def test_registering_a_row_of_deskmain_is_refused_by_name_while_it_is_held(monkeypatch):
    """REGISTERED AT THE FLIP: with the generator holding deskmain (the prep's state, crafted), a row is refused by its
    name before anything is registered."""
    label = next(iter(ROWS_AT))
    monkeypatch.setattr(w3b, "_held_back", lambda: {DESKMAIN: "held (the test's)"})
    with pytest.raises(AssertionError, match=re.escape(f"{label}: {w3b.STILL_HELD}")):
        w3b.register_at_the_flip(label)


# ---- U1 (a): THE DESK PARKED IN THE ROM'S OWN deskmain FRAME ------------------------------------------------------------------------
# THE ROWS WHOSE BATTERY HOLDS NO TURN OF THEIRS ON A BLOB (`vet_its_turns` is called by test_aes_ctlmgr.py's and
# test_aes_evlib_woken.py's alone, measured): held here — their turns' triples, whose turns they are, and the deskmain
# loop in each, asked of the measurement itself as well as through `vet_its_turns`.
VETTED_HERE = [name for name in aes_desk_turns_pinned.PINNED if not name.startswith(("aes_rom_ctlmgr", "aes_ap_rdwr", "aes_ev_block"))]
# U1's "eight" — the rows whose turns over our AES are pinned — are SEVEN DESK-TURN ROWS and ct_msgup's, whose one turn
# is ANOTHER PROCESS'S (the accessory's), not the desk's: the label's class is the seven. Which row is the other is
# read off its measured turn's owner (below), not named.
DESK_TURN_ROWS, ANOTHER_PROCESS_S_ROWS = 7, 1


def test_the_label_s_rows_are_the_desk_turn_rows_each_turn_pinned_by_the_loop_s_cycles():
    """The rows pinned to run the ROM's deskmain loop are seven of the eight whose turns over our AES are pinned (U1's);
    the eighth's owner is read where it is measured: a figure per turn (the same count on each blob), none zero."""
    parked, turns = aes_desk_turns_pinned.PARKED_IN_THE_ROM_S_DESKMAIN, aes_desk_turns_pinned.PINNED
    assert set(parked) <= set(turns) and (len(parked), len(turns) - len(parked)) == (DESK_TURN_ROWS, ANOTHER_PROCESS_S_ROWS)
    assert set(turns) - set(parked) <= set(VETTED_HERE), "a row left out of the label whose turns' owner nothing here reads"
    for name, cycles in parked.items():
        assert {len(each) for each in turns[name].values()} == {len(cycles)} and all(cycles), name


@pytest.mark.parametrize("blob", ("bench", "bench_shipped"))
@pytest.mark.parametrize("name", VETTED_HERE)
def test_each_desk_turn_row_no_battery_vets_holds_its_pinned_turns_and_its_loop_on_each_blob(name, blob):
    """...and, of the measurement itself: a row is in the label exactly when one of its turns is THE DESK'S, and each
    turn over our AES runs the pinned cycles of the loop (none, a row not in the label)."""
    held, on = _the_registry()[name], _blobs()[blob]
    measured, _watch, _foreign = aes_switching.measured_on(on, held.row)
    aes_switching.vet_its_turns(name, on, measured)
    over_our_aes = [turn for turn in measured.turns if turn.whose in aes_switching.TEXT_OVER_OUR_AES]
    parked = aes_desk_turns_pinned.PARKED_IN_THE_ROM_S_DESKMAIN.get(name)
    assert (parked is not None) == any(turn.whose == aes_switching.THE_DESK_S for turn in over_our_aes), name
    assert tuple(turn.in_deskmain for turn in over_our_aes) == (parked or (0,) * len(over_our_aes)), name
    # (...and OUR shore's loop, measured since the flip: the same, the desk parked in the ROM's deskmain frame on these
    # rows' machines — the ROM's own; 0 only where a door machine parks it in OUR deskmain: ctlmgr's two, not vetted here)
    ours = (0,) * len(over_our_aes) if name in aes_desk_turns_pinned.OURS_IN_OUR_DESKMAIN else (parked or (0,) * len(over_our_aes))
    assert tuple(turn.ours_in_deskmain for turn in over_our_aes) == ours, name


def test_the_tally_s_span_is_deskmain_s_and_the_label_is_said_only_once_it_is_flipped(monkeypatch):
    tier3 = bench_tier3()
    assert tier3.DESKMAIN_ROM_SPAN == (ENTRY, NEXT_ROUTINE) and tier3.DESKMAIN_IS_FLIPPED == (ENTRY in aes_desk.flipped())
    turn = tier3.Turn(10, 20, 0, 0, 0, aes_switching.THE_DESK_S, 132, 132)
    assert tier3.DESKMAIN_IS_FLIPPED
    assert tier3.PARKED_IN_THE_ROM_S_DESKMAIN in tier3._parked_of(turn) and "132" in tier3._parked_of(turn)
    ours = turn._replace(ours_in_deskmain=0)        # ...parked in OUR deskmain (a door machine: the user's window)
    assert tier3.PARKED_IN_DESKMAIN_OURS_AGAINST_THE_ROM_S in tier3._parked_of(ours) and "loop 132" in tier3._parked_of(ours)
    assert tier3._parked_of(turn._replace(in_deskmain=0)) == ""
    monkeypatch.setattr(tier3, "DESKMAIN_IS_FLIPPED", False)
    assert tier3._parked_of(turn) == ""


def test_a_desk_turn_running_the_loop_other_than_pinned_is_refused_by_the_row_s_name(monkeypatch):
    """The label's hold (`aes_switching.vet_the_desk_parked_in_the_rom_s_deskmain`), on stand-in measurements: a pinned
    row's turns as pinned pass, one cycle off is refused; a row not pinned passes with none and is refused with any."""
    tier3, (name, cycles) = bench_tier3(), next(iter(aes_desk_turns_pinned.PARKED_IN_THE_ROM_S_DESKMAIN.items()))

    def measured(each):
        return type("Measured", (), {"turns": tuple(tier3.Turn(1, 1, 0, 0, 0, aes_switching.THE_DESK_S, c) for c in each)})
    aes_switching.vet_the_desk_parked_in_the_rom_s_deskmain(name, measured(cycles))
    refused = re.escape(aes_switching.A_TURN_IN_THE_ROM_S_DESKMAIN_UNPINNED)
    with pytest.raises(AssertionError, match=refused):
        aes_switching.vet_the_desk_parked_in_the_rom_s_deskmain(name, measured((cycles[0] + 1, *cycles[1:])))
    aes_switching.vet_the_desk_parked_in_the_rom_s_deskmain("a row of this test's", measured((0,)))
    with pytest.raises(AssertionError, match=refused):
        aes_switching.vet_the_desk_parked_in_the_rom_s_deskmain("a row of this test's", measured((132,)))


A_LOOP_S_CYCLES = 133                   # a stand-in desk turn's cycles of the ROM's deskmain loop


def test_a_desk_turn_running_the_loop_unpinned_is_refused_where_its_row_is_vetted(monkeypatch):
    """`vet_its_turns` HOLDS THE LABEL ITSELF (review RW3P's R06), over A STAND-IN ROW: its one desk turn pinned, its
    deskmain loop not — refused by name; the loop pinned, passed."""
    tier3, who = bench_tier3(), "a stand-in row of this test's"
    blob = tier3.shipped_bench()
    turn = (1000, 1000, 0)
    monkeypatch.setitem(aes_desk_turns_pinned.PINNED, who, {blob.elf.parent.name: (turn,)})
    measured = types.SimpleNamespace(turns=(tier3.Turn(*turn, 0, 0, aes_switching.THE_DESK_S, A_LOOP_S_CYCLES),))
    with pytest.raises(AssertionError, match=re.escape(aes_switching.A_TURN_IN_THE_ROM_S_DESKMAIN_UNPINNED)):
        aes_switching.vet_its_turns(who, blob, measured)
    monkeypatch.setitem(aes_desk_turns_pinned.PARKED_IN_THE_ROM_S_DESKMAIN, who, (A_LOOP_S_CYCLES,))
    aes_switching.vet_its_turns(who, blob, measured)


def test_a_desk_turn_whose_deskmain_loop_ran_otherwise_on_the_two_shores_is_refused_by_the_row_s_name():
    """THE TURN'S HOLD, beside its other three (`tier3._vet_the_desk_s_turn_alike`): crafted tallies, alike but the
    deskmain loop's cycles — ours one cycle off the ROM's run — refused; alike, passed."""
    tier3 = bench_tier3()
    mine = [0] * tier3.OUR_TALLY_LENGTH
    its = [0] * (tier3.THE_ROM_S_TALLY_DESKMAIN + 1)
    mine[tier3.TALLY_OUR_DESKMAIN] = its[tier3.THE_ROM_S_TALLY_DESKMAIN] = 784
    tier3._vet_the_desk_s_turn_alike("a row of this test's", 0, mine, its)
    mine[tier3.TALLY_OUR_DESKMAIN] += 1
    with pytest.raises(AssertionError, match="ran 785 cycles of the ROM's deskmain on ours and 784 on the ROM's"):
        tier3._vet_the_desk_s_turn_alike("a row of this test's", 0, mine, its)


def test_a_desk_turn_parked_in_our_deskmain_that_ran_the_rom_s_loop_on_ours_is_refused_by_name():
    """...AND ON A DOOR MACHINE (the desk parked in OUR deskmain: the user's window of 2026-10-28) the hold is another:
    the ROM's loop runs on its shore alone — crafted tallies, ours 0 against the ROM's 710, passed; one cycle of the
    ROM's deskmain on ours, refused by name."""
    tier3 = bench_tier3()
    mine = [0] * tier3.OUR_TALLY_LENGTH
    its = [0] * (tier3.THE_ROM_S_TALLY_DESKMAIN + 1)
    its[tier3.THE_ROM_S_TALLY_DESKMAIN] = 710
    tier3._vet_the_desk_s_turn_alike("a row of this test's", 0, mine, its, in_our_deskmain=True)
    mine[tier3.TALLY_OUR_DESKMAIN] = 1
    with pytest.raises(AssertionError, match=re.escape(tier3.OUR_DESKMAIN_RAN_THE_ROM_S)):
        tier3._vet_the_desk_s_turn_alike("a row of this test's", 0, mine, its, in_our_deskmain=True)


# ---- THE ROWS, REGISTERED (the flip) ------------------------------------------------------------------------------------------------
def test_every_held_arrival_is_a_target_only_row_of_the_parked_kind_with_no_answer_and_no_budget():
    """ONE ROW AT EACH ARRIVAL BUT THOSE UNPRICED BY NAME: registered target-only and switching (`aes_event.TARGET_ONLY_SWITCHING_
    ROWS`), of the parked kind (its ROM run ends at the desk's first idle: `Switches.parks`), its answer not compared,
    its stagings and the XBIOS door's park said; none declares a budget — each run inside the default derivation margin
    (held where each is derived)."""
    assert set(ROWS_AT) | set(UNPRICED_BY_NAME) == set(w3b.ARRIVALS) and not set(ROWS_AT) & set(UNPRICED_BY_NAME)
    assert len(ROWS_AT) == len(UNPRICED_BY_NAME) == FIRST_ENTRIES
    registered = aes_event.TARGET_ONLY_SWITCHING_ROWS
    assert set(ROWS) <= set(registered) and len(ROWS) == len(ROWS_AT)
    for name, row in ROWS.items():
        held = registered[name]
        assert row.ends_at_its_first_idle and held.switches.parks and not row.answered and row.budget is None, name
        assert w3b.STAGED_AS in row.label and tuple(row.also_dropped) == w3b.XBIOS_DOOR_PARKED, name
    assert {name for name, held in registered.items() if held.row.name == DESKMAIN} == set(ROWS)


def test_an_unpriced_arrival_is_refused_by_name():
    """...AND EACH ARRIVAL UNPRICED BY NAME (the user's ruling), refused where its row would be made — for its stated
    reason, the pinned one."""
    for label, why in UNPRICED_BY_NAME.items():
        with pytest.raises(AssertionError, match=re.escape(f"{label}: {why}")):
            w3b.screen_manager_s_provenance(label)


def test_the_told_handler_tells_the_scripted_trap_s_own_frame_sizes():
    """ONE SOURCE OF A FRAME'S SIZE: every function the band's handler tells that the scripted trap knows is told its
    `aes_shell.FRAME_BYTES` — Dgetdrv's NONE among them (the bring-up makes it; recorded six bytes deep it is the
    caller's stack) — and the shared replay's tellings are kept, that one added."""
    import aes_desksupp as ds
    import aes_shell as sh
    known = {function: size for function, size in w3b.TOLD_ARGUMENT_BYTES.items() if function in sh.FRAME_BYTES}
    assert known == {function: sh.FRAME_BYTES[function] for function in known}
    assert w3b.TOLD_ARGUMENT_BYTES == {**ds.REPLAY_ARGUMENT_BYTES, addrs.GEMDOS_DGETDRV_FN: 0}
    assert addrs.GEMDOS_DGETDRV_FN not in ds.REPLAY_ARGUMENT_BYTES


@pytest.mark.parametrize("name", sorted(ROWS))
def test_each_row_parks_in_the_event_layer_s_wait_on_both_blobs_and_reads_no_blitter(name, blob):
    """THE ROW MEASURED ON `blob` (`aes_switching.measured_on`: every hold of a row that switches, its run ended where
    the desk parks): our run ends parked INSIDE the event layer's ev_multi (`aes_event.DoorStops.parked`), its last
    door call — the same entries, in order, as the ROM's run's (held there: `tier3.vet_the_same_door_calls`), and
    the ROM's run leaves the Options box ending at Print Screen — THE BLITTER-PRESENT ARM UNPINNED BY NAME (O6: Blitmode
    is answered by the staged XBIOS's stub, no blitter)."""
    held = aes_event.TARGET_ONLY_SWITCHING_ROWS[name]
    _measured, watch, _foreign = aes_switching.measured_on(blob, held.row)
    assert watch.inner is not None and watch.inner.parked_in == addrs.AES_ROM_EV_MULTI == watch.inner.closed_at[-1], name
    final = aes_switching._replayed(held.row, held.pokes)[2]
    menu = case.long_in(final, (case.long_in(final, aes.AES_DESK_GLOBALS) & aes.OS_BUS_ADDR_MASK) + w3b.DESK_MENU_TREE)
    tail = case.word_in(final, (menu & aes.OS_BUS_ADDR_MASK) + w3b.OPTIONS_BOX * w3b.OB_BYTES + w3b.OB_TAIL)
    assert tail == w3b.OPTN_PRINT_SCREEN, f"{name}: {BLITTER_PRESENT_ARM}"


BLITTER_PRESENT_ARM = ("THE BLITTER-PRESENT ARM, UNPINNED BY NAME (O6): every row's Blitmode is answered by the staged XBIOS's stub "
                       "(no blitter), so the Options box's relink to the Blitter item, its check and Blitmode(the preference) run "
                       "on no row; the walks' machines have no blitter either")
DEAD_ARMS = {
    "deskmain's D0 = 0 on a resolution change (set_defdrv, isdrive, dos_gdrv, drive_check, $8992)":
        "UNPINNED BY NAME (U2 (a)): no chain makes a resolution change; the served rows' \"deskmain served 0\" stand in "
        "for what its caller does, and W4-R6's `$8992` limit is permanent",
    "deskmain's D0 = 0 on app_start's failure": "UNPINNED BY NAME (U2 (a)): no machine's INF fails app_start",
    "the blitter-present arm": BLITTER_PRESENT_ARM,
}


def test_the_arms_no_row_reaches_are_named():
    assert len(DEAD_ARMS) == 3 and all(why.startswith("UNPINNED BY NAME") or why == BLITTER_PRESENT_ARM for why in DEAD_ARMS.values())


# ---- THE PARKED KIND'S OWN PINS (the user's ruling of 2026-10-28), each refused by name ------------------------------------------------
def _a_returning_target_only_row():
    """A target-only row that switches AND RETURNS (stage 3's first), unregistered: the kind's negative cases' subject."""
    import test_desk_w3a_stage3 as stage_3
    return next(iter(stage_3.ROWS.values()))


def test_a_row_of_the_parked_kind_whose_rom_run_returns_is_refused_by_name():
    row = _a_returning_target_only_row()._replace(ends_at_its_first_idle=True)
    with pytest.raises(AssertionError, match=re.escape(aes_switching.A_PARKED_ROW_WHOSE_RUN_RETURNS)):
        aes_switching.settled(row)


def test_a_row_of_another_kind_whose_rom_run_parks_is_refused_by_name():
    """...and the converse: deskmain's row NOT declared parked — its ROM run idles, never returning: refused as every
    row whose run does not return is."""
    row = next(iter(ROWS.values()))._replace(ends_at_its_first_idle=False)
    with pytest.raises(AssertionError, match="the ROM's scheduled run does not return"):
        aes_switching.settled(row)


def test_a_run_of_the_parked_kind_that_never_parked_is_refused_by_name():
    """A WATCH OF THE KIND whose run ended without parking (crafted: no idle made) — refused by name where it is vetted."""
    watch = aes_switching.the_rom_s(aes_event.Switches({}, 1, aes.SHELL_PD, polls=1, parks=True))
    with pytest.raises(aes_switching.Refused, match=re.escape(aes_switching.A_PARKED_RUN_NEVER_PARKED)):
        watch.vet_ended("a crafted run")


def test_a_run_of_the_parked_kind_that_parked_after_another_count_of_idles_and_polls_is_refused():
    """...and one that PARKED, but after another number of idles and polls than the ROM's run plus its last idle
    (crafted: one idle in the ROM's run, so two to park; parked at once, no idle made, no poll) — refused where it is
    vetted."""
    watch = aes_switching.the_rom_s(aes_event.Switches({}, 1, aes.SHELL_PD, polls=1, parks=True))
    watch.ended_parked = 0
    with pytest.raises(aes_switching.Refused, match="the run parked after 0 idle\\(s\\) and 0 poll\\(s\\), where the ROM's own parks after 2 and 1"):
        watch.vet_ended("a crafted run")


def test_a_run_that_parks_outside_every_door_call_is_refused_by_name():
    with pytest.raises(AssertionError, match=re.escape(aes_event.PARKED_OUTSIDE_EVERY_CALL)):
        aes_event.DoorStops(aes_event.ENTRIES, aes_event.ROM_RETURNS, blocks=False).parked()


def test_a_parked_row_of_another_routine_or_with_a_companion_is_refused_by_name():
    """THE KIND IS deskmain's AND TARGET-ONLY: a row of it of another routine refused where it is registered and in the
    census; registered with a companion (`aes_switching.register_row`), refused."""
    other = _a_returning_target_only_row()._replace(ends_at_its_first_idle=True)
    with pytest.raises(AssertionError, match=re.escape(w3a.A_PARKED_ROW_OF_ANOTHER_ROUTINE)):
        w3a.register_target_only_switching(other)
    with pytest.raises(AssertionError, match=re.escape(aes_switching.A_PARKED_ROW_WITH_A_COMPANION)):
        aes_switching.register_row(next(iter(ROWS.values())))
    registries = w3a.the_registries()
    name, held = next(iter(registries.switching_target_only.items()))
    crafted = {**registries.switching_target_only,
               name: held._replace(row=held.row._replace(name=other.name, ends_at_its_first_idle=True))}
    assert f"{name}: {w3a.A_PARKED_ROW_OF_ANOTHER_ROUTINE}" in w3a.census_refusals(registries._replace(switching_target_only=crafted))


def test_the_register_check_is_skipped_for_the_parked_kind_alone(monkeypatch):
    """THE RULING'S ONE EXEMPTION (`tier3.RomBench._measure_parked`): the kit's callee-saved check runs for a returning
    row's measurement and NOT for a parked one's — counted where the kit makes it — and the parked path refuses, by
    name, a run that is not of the kind."""
    tier3, checked = bench_tier3(), []
    monkeypatch.setattr(rom_bench, "vet_callee_saved", lambda symbol, regs: checked.append(symbol))
    blob = tier3.shipped_bench()
    aes_switching.measured_on(blob, _a_returning_target_only_row())
    assert checked, "the premise: a returning row's measurement checks the callee-saved file"
    checked.clear()
    aes_switching.measured_on(blob, next(iter(ROWS.values())))
    assert not checked, "a parked row's measurement checked a register file it cannot restore"
    with pytest.raises(AssertionError, match=re.escape(tier3.NOT_A_PARKED_RUN)):
        blob._measure_parked(ENTRY, routines.core_symbol(DESKMAIN), watch=None)


def test_g_wlastsel_stands_zero_at_every_arrival_so_the_bring_up_s_store_of_it_is_equivalent():
    """THE BRING-UP'S `g_wlastsel := 0` STORES OVER A ZERO ON ALL DATA (review RW3F's A2: NAMED EQUIVALENT, not a hole a
    seed could reach): sh_main's desk_alloc clears the desk's 19,094-byte globals (`bfill`, `aes/deskmem.c`) right
    before every deskmain entry, and no routine the bring-up calls before that store writes the word (its writers are
    hndl_msg, hndl_button, do_wopen and desksupp's top-window step — each after it) [read]; the word, measured zero at
    each of the ten arrivals, first entries and re-entries alike."""
    offset = rom_data.constants_of(INCLUDE / "deskglobals.h")["DESK_G_WLASTSEL"]
    for label in w3b.ARRIVALS:
        memory = make_image(da.row_machine_of(w3b.arrival(label)))
        desk = case.long_in(memory, aes.AES_DESK_GLOBALS) & aes.OS_BUS_ADDR_MASK
        assert desk and case.word_in(memory, desk + offset) == 0, label


THE_RETURN_S_TWO_VETS = {"vet_callee_saved", "_vet_return_value"}     # what the parked measure leaves out of the kit's
THE_PARKED_MEASURE_S_OWN = {"_parks"}                                   # ...and what it adds: its refusal of another run


def _calls_made_by(function):
    """Every name `function`'s source calls (an attribute's last name; its nested functions' calls included)."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    return {call.func.attr if isinstance(call.func, ast.Attribute) else call.func.id
            for call in ast.walk(tree) if isinstance(call, ast.Call) and isinstance(call.func, (ast.Attribute, ast.Name))}


def test_the_parked_measure_makes_every_call_the_kit_s_measure_makes_but_its_return_s_two_vets():
    """THE COPY CANNOT DRIFT (review RW3F's B4): `tier3.RomBench._measure_parked` is the kit's `measure` body less its
    return's two vets (no kit edit, the user's ruling) — so every call the kit's `measure` makes, the parked one makes
    too, but those two, and the parked one adds only its refusal. A vet the kit adds to `measure` later, or one the copy
    drops (the blob's pokes, today), reds here by its name."""
    kit, parked = _calls_made_by(rom_bench.RomBench.measure), _calls_made_by(bench_tier3().RomBench._measure_parked)
    assert THE_RETURN_S_TWO_VETS <= kit and THE_PARKED_MEASURE_S_OWN <= parked
    assert kit - THE_RETURN_S_TWO_VETS == parked - THE_PARKED_MEASURE_S_OWN, (
        sorted(kit - THE_RETURN_S_TWO_VETS - parked), sorted(parked - THE_PARKED_MEASURE_S_OWN - kit))


# ---- THE TWO BUILDS' deskmain FRAMES UNDER THE PARKED DESK — A BY-NATURE WINDOW, BY ADDRESS (THE USER'S RULING of 2026-10-28,
# `aes_ctlmgr.DESKMAIN_FRAMES_RULING`): on the door machines where sh_main enters OUR deskmain, and there alone ----------------------
def _ctlmgr():
    import aes_ctlmgr
    _the_registry()                     # (every woken and handled row registered)
    return aes_ctlmgr


def _the_two_machines(woken, blob):
    import aes_ctlmgr as cm
    from harness import make_image
    return make_image({0: cm.our_machine(woken, blob)}), make_image({0: cm.the_rom_s_machine(woken)})


# measured: ctlmgr's woken rows' machines (`aes_gemctrl`'s four behind the door: the desk alone, the two accessories with
# every gadget, the menu-hiding accessory, the two six-way waiters — the ruling's "3 machines" — the same window,
# [$a2c0, $a364), on all four, over TWO distinct contents of the desk's stack: the desk alone's, and one the three
# accessory machines share [measured, `scratchpad/b6/W3b/FLIP/scope/machines.py`]), and its rows
THE_WINDOW_S_MACHINES, THE_WINDOW_S_ROWS = 4, 11


@pytest.mark.parametrize("blob", ("bench", "bench_shipped"))
def test_the_window_stands_on_the_woken_rows_four_door_machines_alone_its_span_derived(blob):
    """THE WINDOW'S CENSUS: of ctlmgr's woken rows (`aes_ctlmgr.ROWS`), EVERY ONE stands on a door machine whose desk is
    parked in OUR deskmain — four machines, eleven rows — its window read off the two machines (the desk's live frames'
    bottom on the ROM's, to the slot of the return into sh_main) and the same on each machine; refused on every other
    machine: the ROM-booted machine beside itself (no thunk of ours under the slot), and each first entry's (the desk not
    yet parked)."""
    cm, on = _ctlmgr(), _blobs()[blob]
    machines = set()
    for name, woken in cm.ROWS.items():
        ours, rom = _the_two_machines(woken, on)
        window = cm.deskmain_frames_window(ours, rom, on)
        assert window is not None, f"{name}: the premise — a woken row's machine parks the desk in our deskmain"
        lo, top = cm.the_desk_s_live_frames(rom, on)
        assert window[0] == lo and window[1] < top and case.long_in(rom, window[1]) & aes.OS_BUS_ADDR_MASK == cm.DESKMAIN_RETURNS_TO
        machines.add(woken.machine)
        assert cm.deskmain_frames_window(rom, rom, on) is None, f"{name}: the ROM's machine beside itself has no window"
    assert (len(cm.ROWS), len(machines)) == (THE_WINDOW_S_ROWS, THE_WINDOW_S_MACHINES)
    for label in ROWS_AT:                              # ...no desk parked in our deskmain at deskmain's first entry
        machine = w3b.arrival(label).boot.ram
        try:
            assert cm.deskmain_frames_window(machine, machine, on) is None, label
        except aes_boot.Refused:                        # (no frame of the desk's parked there at all)
            pass


@pytest.mark.parametrize("blob", ("bench", "bench_shipped"))
def test_the_window_is_the_two_builds_deskmain_frames_and_nothing_else_differs(blob):
    """WHAT THE WINDOW EXCUSES, MEASURED: on each of the four machines the two builds' bytes differ inside it (the window
    is needed) — and from its top, the slot of the return into sh_main, to UDA0's top they differ only in DEAD bytes the
    standing staging lays (`lay_the_desk_s_live_frames`: every frame link and return above the window equal, refused by
    name otherwise) — so nothing beyond the deskmain frames is widened."""
    cm, on = _ctlmgr(), _blobs()[blob]
    for name, woken in cm.ROWS.items():
        ours, rom = _the_two_machines(woken, on)
        lo, hi = cm.deskmain_frames_window(ours, rom, on)
        assert any(ours[at] != rom[at] for at in range(lo, hi)), f"{name}: a window that excuses nothing"
        laid = bytearray(ours)
        cm.lay_the_desk_s_live_frames(laid, rom, on)
        top = cm.the_desk_s_live_frames(rom, on)[1]
        assert bytes(laid[hi:top]) == bytes(rom[hi:top]) and bytes(laid[lo:hi]) == bytes(ours[lo:hi]), name


A_BYTE_WIDER_THAN_THE_WINDOW = {
    "a byte below it: its callee's frame, under the desk's lowest (PD0's stack, held per shore)": (-1, 0),
    "a byte above it: the slot of the return into sh_main, the ROM's text's on both shores (compared)": (0, 1),
}


@pytest.mark.parametrize("edge", A_BYTE_WIDER_THAN_THE_WINDOW)
def test_the_window_is_pinned_exact_at_both_edges_a_byte_wider_lies_outside_its_class(edge):
    """THE WINDOW IS PINNED EXACT AT BOTH EDGES (with the census's `window[0]` and the return slot at `window[1]`; a byte
    wider fails them): it is COMPUTED, never declared, so there is no declared span a refusal could be handed — what is
    held here is WHY a byte wider would not be the class, measured on a woken row's machines: below the window's bottom
    lies the desk's lowest frame's own link — its callee's, not the desk's (outside the desk's live frames,
    `the_desk_s_live_frames`); its top is the slot of the return into sh_main, which holds that return on both shores
    (equal: compared, never excused)."""
    cm, on = _ctlmgr(), _blobs()["bench_shipped"]
    woken = next(iter(cm.ROWS.values()))
    ours, rom = _the_two_machines(woken, on)
    lo, hi = cm.deskmain_frames_window(ours, rom, on)
    below, above = A_BYTE_WIDER_THAN_THE_WINDOW[edge]
    if below:
        assert lo + below < cm.the_desk_s_live_frames(rom, on)[0], "a byte below the window lies outside the desk's live frames"
    else:
        assert bytes(ours[hi:hi + above]) == bytes(rom[hi:hi + above]) and case.long_in(rom, hi) & aes.OS_BUS_ADDR_MASK == cm.DESKMAIN_RETURNS_TO


FILLS = ((0xA5,), (0x5A,))


def _the_words_the_harness_reads(ours, rom, blob, window):
    """The bytes of the window THE HARNESS ITSELF reads to find the desk's frames and the window (never the machine's
    run, where the desk sleeps through it): each link and return of the ROM's desk chain inside it, and our thunk's
    return under the slot of the return into sh_main — left unfilled, so the filler tells what the RUNS read."""
    cm = _ctlmgr()
    lo, hi = window
    uda = case.long_in(rom, aes.SHELL_PD + aes.PD_UDA) & aes.OS_BUS_ADDR_MASK
    chain, frame = [], case.long_in(rom, uda + aes.UDA_A6) & aes.OS_BUS_ADDR_MASK
    while uda <= frame < hi:            # ...the whole chain from the parked A6 up, those of its words inside the window kept
        chain.append(frame)
        frame = case.long_in(rom, frame) & aes.OS_BUS_ADDR_MASK
    words = [at for frame in chain for at in (frame, frame + aes.LONG_BYTES)] + [hi - cm.THUNK_RETURN_ABOVE_THE_SLOT]
    # (the filler bytes laid over the window, on both shores: two, each the other's complement)
    return {at + offset for at in words for offset in range(aes.LONG_BYTES) if lo <= at + offset < hi}


def _woken_rows_the_desk_sleeps_through():
    """The woken rows whose ROM run enters no desk (its frames dead for the run): where the noise pin applies."""
    cm = _ctlmgr()
    return sorted(name for name, woken in cm.ROWS.items() if aes.SHELL_PD not in cm.made(woken).entered)


def _the_runs_ends(monkeypatch, blob, woken, filler):
    """The two runs' final memories of `woken` on `blob` (`tier3.idle_to_idle_on`), the window laid with `filler` on
    both shores' machines where given."""
    import aes_ctlmgr as cm
    tier3 = bench_tier3()
    ends = []
    real = tier3._run_to_its_next_idle

    def keeping(image, watch, on):
        ran = real(image, watch, on)
        ends.append(bytes(ran.memory[:addrs.ST_RAM_BYTES]))
        return ran
    monkeypatch.setattr(tier3, "_run_to_its_next_idle", keeping)
    if filler is not None:
        ours, rom = _the_two_machines(woken, blob)
        lo, hi = cm.deskmain_frames_window(ours, rom, blob)
        kept = _the_words_the_harness_reads(ours, rom, blob, (lo, hi))
        for maker in ("the_rom_s_machine", "our_machine"):
            made = getattr(cm, maker)

            def filled(*args, made=made):
                ram = bytearray(made(*args))
                for at in range(lo, hi):
                    if at not in kept:
                        ram[at] = filler
                return bytes(ram)
            monkeypatch.setattr(cm, maker, filled)
    tier3.idle_to_idle_on(blob, cm.row_name(woken), woken)
    return ends, (lo, hi) if filler is not None else None


@pytest.mark.parametrize("blob", ("bench", "bench_shipped"))
def test_nothing_reads_the_window_s_bytes_where_the_desk_sleeps_through_the_run(blob, monkeypatch):
    """THE STANDING FILLER-BYTE PIN (as THE_USERDEF_STACK's): a woken row whose run enters no desk, run again with the
    window laid with filler bytes on BOTH shores' machines — $A5, then its complement $5A — leaves every byte outside
    the window as the unfilled run does, on both shores and both blobs: no build's run reads what the window held. (A
    row whose run ENTERS the desk is no such row: the desk resumes in those very frames — they are live, and its turn
    is compared — `aes_desk_turns_pinned`: the U1 rows.)"""
    cm, on = _ctlmgr(), _blobs()[blob]
    names = _woken_rows_the_desk_sleeps_through()
    assert names, "the premise: a woken row the desk sleeps through"
    woken = cm.ROWS[names[0]]
    plain, _ = _the_runs_ends(monkeypatch, on, woken, None)
    for (filler,) in FILLS:
        monkeypatch.undo()
        filled, (lo, hi) = _the_runs_ends(monkeypatch, on, woken, filler)
        for shore, (unfilled, laid) in zip(("the ROM's", "ours"), zip(plain, filled)):
            moved = [f"{at:#x}" for at in range(len(unfilled)) if unfilled[at] != laid[at] and not lo <= at < hi]
            assert not moved, f"{shore} run, filler {filler:#x}: bytes outside the window moved {moved[:8]}"
