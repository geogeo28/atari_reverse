"""BAND 6 W3b's PREP — deskmain `$fe272e` declared, held the ROM's, and the harness made ready for its flip (the W3b cut's
§7; `aes_desk_w3b.py`). NOTHING FLIPS HERE: every product is HEAD's. What is held:

  * THE NAMES read off the ROM (O8): the three return sites deskmain's Line-F calls park, and the pointer pair it
    stores beside a_cmd / a_tail (`desk/deskglobals.h`: a_fcb1 / a_fcb2);
  * deskmain's SIGNATURE, TARGET-ONLY (O1), and the generator HOLDING ITS ENTRY THE ROM'S (DECLARED_NOT_LINKED) — and
    its flip moving the desk door with the table (O2: sh_main's `jsr` bound by the generated header, as the built-ins');
  * THE HARNESS READING deskmain OFF THE DOOR'S BINDING — the our-boot's checkpoint and stop, the served door, who-ran's
    cut, the start-up reading — the same addresses while held, the thunk once flipped;
  * ITS ROWS' ARRIVALS (O3 / O7), each vetted on the ROM's machine now, registered at the flip and refused before it;
  * U1 (a)'s LABEL: the ROM's deskmain loop in each desk turn of a ROM-booted row, pinned by its cycles.
"""
import re
import types

import pytest

from harness import BASE_IMAGE, addrs, bench_tier3

import aes
import aes_boot
import aes_desk
import aes_desk_turns_pinned
import aes_desk_w3a as w3a
import aes_desk_w3b as w3b
import aes_event
import aes_ourboot as ob
import aes_stack
import aes_switching
import case
import rom_data
import routines
import test_boot_snapshot                       # noqa: F401  (the registry: every row the turns are held on)
import transcription
import vdi

DESKMAIN, ENTRY = w3b.DESKMAIN, w3b.DESKMAIN_ENTRY
INCLUDE = rom_data.RECREATE / "include" / "desk"
LINE_F_CALL_BYTES = aes.WORD_BYTES
LINE_F_MASK = 0xF000                    # a Line-F call word: `$F000 | the table entry's byte offset`
NEXT_ROUTINE = 0xFE2A7C                 # the AES map's next start after deskmain (846 bytes: the W3b cut's §1.1)


def _generator():
    import test_aes_desk_ours
    return test_aes_desk_ours._the_generator()


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


# ---- THE SIGNATURE, HELD (O1, O2) -------------------------------------------------------------------------------------------------
def test_deskmain_is_declared_target_only_and_held_the_rom_s_and_no_blob_links_a_core():
    """`() -> word`, the image first; target-only (no host core); in the kind's routines; held by the generator
    (DECLARED_NOT_LINKED) — its table entry the ROM's, no thunk — and no blob links `aes_deskmain`."""
    generator = _generator()
    assert w3a.W3B == (DESKMAIN,) and DESKMAIN in w3a.TARGET_ONLY_ROUTINES and DESKMAIN not in w3a.W3A
    assert (vdi.ALCYON[DESKMAIN].restype, vdi.frame_argtypes(DESKMAIN)) == (aes.WORD_ANSWER, ())
    assert DESKMAIN in vdi.TARGET_ONLY and vdi.takes_image(DESKMAIN) and w3a.host_twin_of(DESKMAIN) is None
    assert DESKMAIN in generator.DECLARED_NOT_LINKED and DESKMAIN not in generator.thunked_routines()
    assert {entry.verdict for entry in generator.entries() if entry.target == ENTRY} == {generator.THE_ROM_S}
    for blob in _blobs().values():
        assert routines.core_symbol(DESKMAIN) not in {symbol.name for symbol in transcription.symbol_table(blob.elf)}


def test_the_door_binds_deskmain_as_the_table_does_and_its_flip_moves_both(monkeypatch):
    """O2: sh_main's door `jsr`s what the generated header binds deskmain to — the ROM's routine today, on both blobs —
    and the generator with deskmain no longer held thunks its entry AND binds the door to that very thunk."""
    generator = _generator()
    assert transcription.DESK_DOOR_CALLERS[DESKMAIN] == "aes_sh_main"
    assert f"#define {generator.DOOR_BOUND_PREFIX}{DESKMAIN} {DESKMAIN} " in generator.door_text()
    for blob in _blobs().values():
        assert transcription.desk_door_bindings(blob.elf)[ENTRY] == ENTRY and ENTRY not in transcription.desk_door_thunked(blob.elf).values()
    monkeypatch.setattr(generator, "DECLARED_NOT_LINKED", {name: why for name, why in generator.DECLARED_NOT_LINKED.items() if name != DESKMAIN})
    thunk = generator.thunk_symbol(DESKMAIN)
    assert DESKMAIN in generator.thunked_routines() and thunk in transcription.DESK_DOOR_THUNKS
    assert f"#define {generator.DOOR_BOUND_PREFIX}{DESKMAIN} {thunk} " in generator.door_text()
    assert {entry.symbol for entry in generator.entries() if entry.target == ENTRY} == {thunk}


# ---- THE HARNESS READS deskmain OFF THE DOOR ---------------------------------------------------------------------------------------
A_THUNK = 0x123456                      # a stand-in for the door's thunk: where a flipped blob's door would enter deskmain


def test_the_harness_stands_where_the_door_enters_deskmain_the_rom_s_address_while_held(monkeypatch):
    """The our-boot's checkpoints at deskmain stand AT_THE_DESK_DOOR; on both blobs that is the ROM's address today —
    the our-boot's stop and who-ran's cut (`aes_boot.deskmain_entry`), the checkpoint (`aes_ourboot.our_address`), the
    start-up reading's call out of the build (`aes_stack.the_desk_door_of`). A blob whose door enters a thunk moves
    each to it, and the served door reads the thunk as deskmain."""
    checkpoints = {*ob.THE_FIRST_PASS, *ob.THE_TEARDOWN_AND_THE_SECOND_PASS, *ob.A_BUILT_IN_PASS}
    at_the_desk = {each for each in checkpoints if each.what == ob.DESKMAIN_ENTERED}
    assert at_the_desk == {ob.Checkpoint(ob.DESKMAIN_ENTERED, ENTRY, ob.AT_THE_DESK_DOOR)}
    for blob in _blobs().values():
        ours = aes_boot.ours_of(blob)
        assert aes_boot.deskmain_entry(ours) == ob.our_address(*at_the_desk, blob) == ENTRY
        assert ENTRY not in dict(ours.desk_door).values() and set(dict(ours.desk_door).values()) <= set(aes_boot.SERVED_ROUTINES)
    flipped = ours._replace(desk_door=(*ours.desk_door, (A_THUNK, ENTRY)))
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
        assert set(aes_boot.SERVED_ROUTINES) - {ENTRY} <= set(door.values())
        watched = aes_boot.second_arrivals_refused(ours, None)
        assert set(door) <= set(watched) and not set(door.values()) & set(watched)
        for thunk, routine in door.items():
            name, call = aes_boot.SERVED_ROUTINES[routine]
            assert watched[thunk][0] == name
            with pytest.raises(aes_boot.Refused, match=re.escape(f"THE RUN ARRIVED AT {name} AGAIN")):
                watched[thunk][1](None, None)
            stopped = _stopped_at(thunk, call, ours)
            assert aes_boot._vet_stands_at_a_served_entry(stopped) == (name, routine, call + aes.WORD_BYTES)


# ---- THE ROWS' ARRIVALS (O3, O7) ---------------------------------------------------------------------------------------------------
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


@pytest.mark.parametrize("label", w3b.ARRIVALS)
def test_registering_a_row_of_deskmain_is_refused_by_name_while_it_is_held(label):
    """REGISTERED AT THE FLIP: while the generator holds deskmain, each row is refused by its name — and none is."""
    with pytest.raises(AssertionError, match=re.escape(f"{label}: {w3b.STILL_HELD}")):
        w3b.register_at_the_flip(label)
    assert not [name for name, held in aes_event.TARGET_ONLY_SWITCHING_ROWS.items() if held.row.name == DESKMAIN]


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
    held, on = aes_event.every_switching_row()[name], _blobs()[blob]
    measured, _watch, _foreign = aes_switching.measured_on(on, held.row)
    aes_switching.vet_its_turns(name, on, measured)
    over_our_aes = [turn for turn in measured.turns if turn.whose in aes_switching.TEXT_OVER_OUR_AES]
    parked = aes_desk_turns_pinned.PARKED_IN_THE_ROM_S_DESKMAIN.get(name)
    assert (parked is not None) == any(turn.whose == aes_switching.THE_DESK_S for turn in over_our_aes), name
    assert tuple(turn.in_deskmain for turn in over_our_aes) == (parked or (0,) * len(over_our_aes)), name


def test_the_tally_s_span_is_deskmain_s_and_the_label_is_said_only_once_it_is_flipped(monkeypatch):
    tier3 = bench_tier3()
    assert tier3.DESKMAIN_ROM_SPAN == (ENTRY, NEXT_ROUTINE) and tier3.DESKMAIN_IS_FLIPPED == (ENTRY in aes_desk.flipped())
    turn = tier3.Turn(10, 20, 0, 0, 0, aes_switching.THE_DESK_S, 132)
    assert tier3._parked_of(turn) == "" or tier3.DESKMAIN_IS_FLIPPED
    monkeypatch.setattr(tier3, "DESKMAIN_IS_FLIPPED", True)
    assert tier3.PARKED_IN_THE_ROM_S_DESKMAIN in tier3._parked_of(turn) and "132" in tier3._parked_of(turn)
    assert tier3._parked_of(turn._replace(in_deskmain=0)) == ""


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
