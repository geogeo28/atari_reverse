"""THE PROCESS SWITCH as the target build ships it (`src/aes/switch.S`): gemdosif's dsptch, spl7_save, spl_restore,
cli, sti, gotopgm, savestate and switchto as the ROM's own bytes, and gemdisp's disp as the ROM's own instruction
stream.

THREE CLAIMS HOLD IT.
  * ITS BYTES. The gemdosif region `$fe387c..$fe395b` is the ROM's, every word but ONE — dsptch's `jmp`, which goes
    to our disp where the ROM's goes to its own — on BOTH blobs. disp is the ROM's stream instruction by instruction
    (`transcription.assert_stream`): its six Line-F call words NAMED, each a `jsr` of the entry that stands for the
    routine the ROM's table reaches, and its short branches following the four bytes each `jsr` adds.
  * ITS BEHAVIOUR, through Tier 3's transcription relation — the image and the WHOLE register file, both shores
    entered with one register file by a caller staged in the machine (`aes_switch`, THE STAGED CALLERS): the
    brackets; savestate as disp enters it, where the UDA's context block is compared byte for byte; switchto over the
    machine savestate left, which gives every register back.
  * WHAT IS DEAD IS PROVED DEAD, from the ROM's own bytes: the Line-F return behind disp's last call (switchto ends in
    `rte` on every path), and savestate's arm under the dispatcher's guard (disp is entered by dsptch's `jmp` alone,
    past dsptch's own test of the guard; savestate by disp alone).

LABELLED, AND WHY: dsptch's bare `rts` under the guard is THE LEVER's arm — no process runs with the guard set
(`aes/switch.h`); it is held here because the snapshot's own state reaches it, and no row prices it. gotopgm runs
over A STAGED BASEPAGE — a poked field and one staged instruction: the accessory loader that makes a real one is not
reconstructed yet, and its row waits for it.
"""
import struct
import types

import pytest

from harness import BASE_IMAGE, addrs, emu, make_image
from recreate_kit.rom_bench import RomBench

import aes
import aes_event
import aes_switch as switch
import case
import derived
import rom_data
import transcription
from case import merge_pokes
from opcodes import RTE, RTS
from transcription import ABSOLUTE, CallWord, Relocated

LONG_BYTES, WORD_BYTES = aes.LONG_BYTES, aes.WORD_BYTES
ENTRIES = transcription.SWITCH_ENTRIES
DISP = switch.DISP
SPL7_SAVE, SPL_RESTORE, CLI, STI = switch.SPL7_SAVE, switch.SPL_RESTORE, switch.CLI, switch.STI
GOTOPGM, SAVESTATE, SWITCHTO = switch.GOTOPGM, switch.SAVESTATE, switch.SWITCHTO
# The region's routines after its first, in the ROM's order: each where the ROM has it, counted from spl7_save's
# entry (dsptch's own carries the name the C calls, `aes_dsptch`, which the naming rule does not derive).
AFTER_SPL7_SAVE = (SPL_RESTORE, CLI, STI, GOTOPGM, SAVESTATE, SWITCHTO)
REGION = transcription.pinned_region(addrs.AES_ROM_DSPTCH, transcription.SWITCH_REGION_END, SPL7_SAVE, AFTER_SPL7_SAVE)
DSPTCH_S_JMP_OPERAND = addrs.AES_ROM_DSPTCH + ENTRIES["aes_dsptch"].bytes - LONG_BYTES
RELOCATED = {
    DSPTCH_S_JMP_OPERAND: Relocated(ABSOLUTE, None, "dsptch's `jmp` into disp, where our disp is linked",
                                    thunk="aes_rom_disp"),
}
# disp's six Line-F call words IN THE ROM'S ORDER, each with the ROM routine its table entry reaches and the entry
# our `jsr` names: the two halves of the switch (this file's own bytes) and the thunks of the four C routines
# (`switch.S`). WHERE each lies is read off the ROM — the words of disp that are no 68000 instruction.
CALLS_IN_ORDER = (
    CallWord(SAVESTATE, "aes_rom_savestate"), CallWord("AES_ROM_DISP_ACT", "disp_to_aes_disp_act"),
    CallWord("AES_ROM_MWAIT_ACT", "disp_to_aes_mwait_act"), CallWord("AES_ROM_FORKER", "disp_to_aes_forker"),
    CallWord("AES_ROM_IDLE", "disp_to_aes_idle"), CallWord(SWITCHTO, "aes_rom_switchto"),
)
STREAM_CALLS = len(CALLS_IN_ORDER)
CALL_WORDS_AT = tuple(at for at, text in rom_data.instructions(addrs.AES_ROM_DISP, addrs.AES_ROM_DISP_END) if text is None)
assert len(CALL_WORDS_AT) == STREAM_CALLS and CALL_WORDS_AT[-1] == addrs.AES_ROM_DISP_SWITCHTO
assert addrs.AES_ROM_DISP_LOOP in CALL_WORDS_AT, "disp's loop begins at its call of forker"
SAVESTATE_S_CALL_WORD_AT = CALL_WORDS_AT[0]
STREAM = transcription.stream(addrs.AES_ROM_DISP, addrs.AES_ROM_DISP_END, "aes_rom_disp",
                              dict(zip(CALL_WORDS_AT, CALLS_IN_ORDER)))
# The four thunks under disp's `jsr`s into C, in the source's order: each one's shape and the C it enters.
THUNKS = {"disp_to_aes_disp_act": (switch.ONE_LONG_THUNK, "aes_disp_act"),
          "disp_to_aes_mwait_act": (switch.ONE_LONG_THUNK, "aes_mwait_act"),
          "disp_to_aes_forker": (switch.IMAGE_ONLY_THUNK, "aes_forker"),
          "disp_to_aes_idle": (switch.IMAGE_ONLY_THUNK, "aes_idle")}
GEMDOSIF_S_ENTRIES = ("aes_dsptch", "aes_rom_spl7_save", "aes_rom_spl_restore", "aes_rom_cli", "aes_rom_sti",
                      "aes_rom_gotopgm", "aes_rom_savestate", "aes_rom_switchto")
BLOBS = switch.BLOBS


@pytest.fixture(scope="module", params=BLOBS.values(), ids=BLOBS)
def blob(request):
    return RomBench(request.param)


# ---- the bytes ----------------------------------------------------------------------------------------------------------
def test_the_region_is_the_rom_s_bytes_but_for_dsptch_s_jmp():
    """THE BYTE PIN: every word of `$fe387c..$fe395b` the ROM's, and the one that is not — the operand of dsptch's
    `jmp` — exactly where our disp is linked."""
    transcription.assert_transcribed(REGION, relocated=RELOCATED)


def test_the_region_is_the_same_bytes_on_both_blobs(blob):
    """...and on the shipped configuration's blob too: every byte the ROM's but that operand's, which names its disp."""
    start = blob.entry("aes_dsptch")
    ours = bytes(blob.blob[start - blob.base:start - blob.base + REGION.hi - REGION.lo])
    theirs = bytes(BASE_IMAGE[REGION.lo:REGION.hi])
    operand = DSPTCH_S_JMP_OPERAND - REGION.lo
    assert ours[:operand] == theirs[:operand] and ours[operand + LONG_BYTES:] == theirs[operand + LONG_BYTES:]
    assert ours[operand:operand + LONG_BYTES] == blob.entry("aes_rom_disp").to_bytes(LONG_BYTES, "big")


def test_disp_is_the_rom_s_stream_its_six_call_words_made_jsrs(blob):
    """THE STREAM PIN, on both blobs: instruction by instruction the ROM's disp — the six substitutions named, no
    other Line-F word in it, every branch the ROM's own to the instruction the ROM's goes to."""
    assert len(STREAM.calls) == STREAM_CALLS
    transcription.assert_stream(STREAM, blob)


def test_the_source_holds_its_entries_its_thunks_and_nothing_else(blob):
    """WHAT THE PINS DO NOT REACH, held: `switch.S`'s symbols — the region's eight routines, disp, the four thunks —
    lie END TO END in each blob with nothing between them and nothing after the last but the assembler's fill; and
    each thunk is its shape into the C its name says (`aes_switch.vet_a_thunk`)."""
    switch.vet_laid_end_to_end(blob, (*GEMDOSIF_S_ENTRIES, "aes_rom_disp", *THUNKS))
    for thunk, (shape, body) in THUNKS.items():
        switch.vet_a_thunk(blob, thunk, shape, body)
    assert set(THUNKS) == ENTRIES["aes_rom_disp"].exits - set(ENTRIES)


def test_a_thunk_that_calls_another_routine_or_bytes_outside_a_symbol_are_refused(blob):
    """THE TWO VETS' OWN REDS: a thunk held to another body, or to another shape; and a run of symbols that leaves
    one out (its bytes then lie between two of the others, in no symbol of the run)."""
    with pytest.raises(AssertionError, match="is not its shape into aes_mwait_act"):
        switch.vet_a_thunk(blob, "disp_to_aes_disp_act", switch.ONE_LONG_THUNK, "aes_mwait_act")
    with pytest.raises(AssertionError, match="is not its shape into aes_forker"):
        switch.vet_a_thunk(blob, "disp_to_aes_forker", switch.ONE_LONG_THUNK, "aes_forker")
    without_one = tuple(name for name in (*GEMDOSIF_S_ENTRIES, "aes_rom_disp", *THUNKS) if name != "aes_rom_disp")
    with pytest.raises(AssertionError, match="is where the one before it ends"):
        switch.vet_laid_end_to_end(blob, without_one)


def test_an_instruction_after_the_last_thunk_is_refused(blob):
    """...and the same blob with an `rts` where the assembler's fill lies after the source's last thunk — two bytes
    of no symbol: refused, where the fill itself is let be."""
    last = next(symbol for symbol in transcription.symbol_table(blob.elf) if symbol.name == list(THUNKS)[-1])
    after = last.start + last.size - blob.base
    assert bytes(blob.blob[after:after + len(RTS)]) == switch.ASSEMBLER_FILL, "the premise: the fill, as the assembler lays it"
    with_an_rts = types.SimpleNamespace(elf=blob.elf, base=blob.base,
                                        blob=bytes(blob.blob[:after]) + RTS + bytes(blob.blob[after + len(RTS):]))
    with pytest.raises(AssertionError, match="lie bytes of no symbol"):
        switch.vet_laid_end_to_end(with_an_rts, (*GEMDOSIF_S_ENTRIES, "aes_rom_disp", *THUNKS))


def _disp_s_stream_with(calls=None, hi=addrs.AES_ROM_DISP_END):
    """disp's stream DECLARED OTHERWISE than it is: other call words, or another end."""
    return transcription.stream(addrs.AES_ROM_DISP, hi, "aes_rom_disp", STREAM.calls if calls is None else calls)


@pytest.fixture
def declared_for_this_test_alone():
    """The streams a test DECLARES are its own: the registry is put back as the test ends (six false declarations of
    disp stayed in it for the worker's life — six lies for whoever next reads the registry whole)."""
    declared = list(transcription.STREAMS)
    yield
    transcription.STREAMS[:] = declared


def test_the_stream_kind_refuses_what_it_is_for(declared_for_this_test_alone):
    """THE COMPARATOR'S OWN REDS, each a declaration of disp's stream that is not the truth: a call word nobody
    named; a named address that holds none; a call word named for ANOTHER ROUTINE than the ROM's table reaches; one
    named for another entry of ours (the bytes then differ); a stream run on into the Line-F RETURN; and one cut short
    (our symbol is longer than it says)."""
    first, *rest = sorted(STREAM.calls)
    with pytest.raises(AssertionError, match="every one is named, and nothing else is"):
        transcription.assert_stream(_disp_s_stream_with({at: STREAM.calls[at] for at in rest}))
    with pytest.raises(AssertionError, match="every one is named, and nothing else is"):
        transcription.assert_stream(_disp_s_stream_with({**STREAM.calls, first - WORD_BYTES: STREAM.calls[first]}))
    with pytest.raises(AssertionError, match="reaches .* through the ROM's table, not AES_ROM_SWITCHTO"):
        transcription.assert_stream(_disp_s_stream_with({**STREAM.calls, first: CallWord(SWITCHTO, "aes_rom_savestate")}))
    with pytest.raises(AssertionError, match="a Line-F call.* holds"):
        transcription.assert_stream(_disp_s_stream_with({**STREAM.calls, first: CallWord(SAVESTATE, "aes_rom_switchto")}))
    with pytest.raises(AssertionError, match="is a Line-F RETURN"):
        transcription.assert_stream(_disp_s_stream_with(
            {**STREAM.calls, addrs.AES_ROM_DISP_END: CallWord(SWITCHTO, "aes_rom_switchto")},
            hi=addrs.AES_ROM_DISP_END + WORD_BYTES))
    with pytest.raises(AssertionError, match="an instruction more, or the stream cut short"):
        transcription.assert_stream(_disp_s_stream_with(
            {at: call for at, call in STREAM.calls.items() if at != addrs.AES_ROM_DISP_SWITCHTO},
            hi=addrs.AES_ROM_DISP_SWITCHTO))


def test_a_stream_no_battery_declares_is_refused():
    with pytest.raises(AssertionError, match="held as a stream no battery declares"):
        transcription.assert_stream(transcription.Stream(addrs.AES_ROM_DISP, addrs.AES_ROM_DISP_END, "aes_rom_disp", {}))


def test_the_registry_of_streams_holds_what_the_batteries_declared_and_nothing_a_test_did():
    """...and the registry is the batteries' own declarations — disp's — whichever tests ran before this one."""
    assert transcription.STREAMS == [STREAM]


@pytest.mark.parametrize("entry", sorted(ENTRIES))
def test_each_entry_of_the_table_is_where_and_what_the_table_says(entry, blob):
    """THE TABLE (`transcription.SWITCH_ENTRIES`) against the build: a byte-exact entry is as long as the ROM's
    routine and lies where the ROM has it in its region's layout; disp is the stream's length, its `jsr`s in."""
    row = ENTRIES[entry]
    sized = {symbol.name: symbol.size for symbol in transcription.symbol_table(blob.elf)}[entry]
    if entry == "aes_rom_disp":
        assert sized == row.bytes + STREAM_CALLS * (transcription.JSR_BYTES - WORD_BYTES)
        return
    assert sized == row.bytes, f"{entry} is {sized} bytes, the ROM's routine {row.bytes}"
    anchor = "aes_dsptch" if REGION.lo <= row.rom < REGION.hi else "aes_rom_button_glue"
    assert blob.entry(entry) - blob.entry(anchor) == row.rom - ENTRIES[anchor].rom


def test_the_table_s_exits_are_the_symbols_the_pins_name():
    """An entry's EXITS — what its bytes name of our build where the ROM's name the ROM's — are exactly its pin's:
    dsptch's one relocation, disp's six call words. (The glue's are held to its own pin, `test_aes_irq.py`.) So no
    entry of the switch reaches the AES's ROM text: nothing in the table names a ROM address to go to."""
    assert ENTRIES["aes_dsptch"].exits == {relocation.thunk for relocation in RELOCATED.values()}
    assert ENTRIES["aes_rom_disp"].exits == {call.symbol for call in STREAM.calls.values()}
    for entry in GEMDOSIF_S_ENTRIES[1:]:
        assert not ENTRIES[entry].exits


def test_the_region_is_the_routines_end_to_end():
    """The table's lengths tile the region: each routine ends where the next begins, the last on switchto's `rte` —
    and what follows it in the ROM (`$fe395c`, a test-and-set no call word reaches) is not transcribed."""
    at = REGION.lo
    for entry in GEMDOSIF_S_ENTRIES:
        assert ENTRIES[entry].rom == at, f"{entry} begins at {ENTRIES[entry].rom:#x}, the routine before it ends at {at:#x}"
        at += ENTRIES[entry].bytes
    assert at == REGION.hi == addrs.AES_ROM_SWITCHTO_RTE + len(RTE)
    assert bytes(BASE_IMAGE[addrs.AES_ROM_SWITCHTO_RTE:REGION.hi]) == RTE


# ---- what is dead, proved from the ROM's bytes ----------------------------------------------------------------------------
LEAVES = ("rts", "rte", "rtr", "jmp", "jsr", "bsr", "trap")


def _instructions_of(lo, hi):
    return rom_data.instructions(lo, hi)


def test_switchto_never_returns_so_disp_s_line_f_return_is_dead():
    """switchto's body holds NO branch and no return but its last instruction, an `rte`: whoever calls it is never
    come back to. disp's Line-F return ($fe4e00) lies behind its call of switchto and nothing branches to it — the
    stream ends before it (`STREAM`), and nothing is lost."""
    body = _instructions_of(addrs.AES_ROM_SWITCHTO, REGION.hi)
    *before, (last_at, last) = body
    assert (last_at, last) == (addrs.AES_ROM_SWITCHTO_RTE, "rte")
    transfers = [(at, text) for at, text in before
                 if text is None or text.split()[0].startswith("b") or text.split()[0] in LEAVES]
    assert not transfers, f"switchto transfers control before its `rte`: {transfers}"
    disp = _instructions_of(addrs.AES_ROM_DISP, addrs.AES_ROM_DISP_END + WORD_BYTES)
    assert disp[-1] == (addrs.AES_ROM_DISP_END, None) and disp[-2] == (addrs.AES_ROM_DISP_SWITCHTO, None)
    into_the_return = [at for at, text in disp[:-1] if text and f"{addrs.AES_ROM_DISP_END:#x}" in text]
    assert not into_the_return, f"disp branches to its own return at {into_the_return}"


def test_savestate_s_arm_under_the_guard_is_dead():
    """savestate tests the dispatcher's guard and, if it is set, unwinds disp's frame and `rte`s ($fe38e6..$fe38ea).
    NO MACHINE REACHES THAT ARM, by the ROM's own structure: savestate is called from ONE place — disp's first call —
    and disp is entered from ONE place — dsptch's `jmp`, which dsptch takes only past its own test of the same guard
    ($fe3882 `beq`), with nothing between the two tests that writes it. Our `.S` carries the arm as bytes; no case
    enters it."""
    assert list(aes.line_f_call_sites(SAVESTATE).values()) == [(SAVESTATE_S_CALL_WORD_AT,)], "one call word, one site"
    assert aes.line_f_call_sites(DISP) == {}, "disp has no call word: it is no entry of the Line-F table's users"
    guard = f"{aes.AES_INDISP:#x}"
    named = [at for at, text in rom_data.instructions(*aes.AES_TEXT)
             if text and (f"{addrs.AES_ROM_DISP:#x}" in text or f"{addrs.AES_ROM_SAVESTATE:#x}" in text)]
    assert named == [DSPTCH_S_JMP_OPERAND - WORD_BYTES], (
        f"instructions of the AES's text that name disp or savestate by address: {[f'{at:#x}' for at in named]}")
    savestate = _instructions_of(addrs.AES_ROM_SAVESTATE, addrs.AES_ROM_SWITCHTO)
    its_test = next(nth for nth, (_at, text) in enumerate(savestate) if text.startswith("tstb") and guard in text)
    between = (_instructions_of(addrs.AES_ROM_DSPTCH, addrs.AES_ROM_SPL7_SAVE)
               + _instructions_of(addrs.AES_ROM_DISP, SAVESTATE_S_CALL_WORD_AT) + savestate[:its_test + 1])
    writers = [(at, text) for at, text in between if text and guard in text and not text.startswith("tstb")]
    assert not writers, f"the guard is written between dsptch's test of it and savestate's: {writers}"


# ---- the behaviour: Tier 3's transcription relation -----------------------------------------------------------------------
def _uda_of(pd, pokes):
    return switch.uda_of(pd, make_image(pokes))


@derived.kept
def _saved():
    """THE MACHINE savestate LEAVES — the ROM's own, run as disp runs it for the running process over
    `aes_event.machine()` with the transcription's register file: PD0's context in its UDA, the guard counted, the
    `rte` frame under the run's stack top (its SR word the one byte pair of the run's stack the machine keeps: it is
    the frame the UDA names). What switchto is then entered over."""
    machine = aes_event.machine()
    entered = switch.entered_with_a_uda(switch.SAVESTATE_CALLER, _uda_of(aes.SHELL_PD, machine), machine)
    pokes = transcription.transcription_pokes(SAVESTATE, entered.pokes, entered.caller)
    final, _writes, _regs = emu.run(make_image(pokes), entered.caller.at, dict(transcription.DIRTY))
    frame = bytes(final[switch.PARKED_FRAME_AT:switch.PARKED_FRAME_AT + WORD_BYTES])
    return merge_pokes(aes_event.as_pokes(final, without=case.STACK_BAND, upto=addrs.ST_RAM_BYTES),
                       {switch.PARKED_FRAME_AT: frame})


def _a_staged_basepage():
    """A STAGED BASEPAGE, labelled: the running process's PD_LDADDR POKED at a basepage of this battery's whose text
    is ONE instruction, the run's end. No machine the snapshot's scheduler makes has a program gotopgm could enter —
    the accessory loader that makes one is not reconstructed yet."""
    return merge_pokes(aes_event.machine(),
                       aes.field_pokes("PD", aes.SHELL_PD, LDADDR=switch.BASEPAGE_AT),
                       {switch.BASEPAGE_AT + addrs.BASEPAGE_TBASE: struct.pack(">I", switch.PROGRAM_AT),
                        switch.PROGRAM_AT: switch.END_THE_RUN})


def _plain(pokes):
    return switch.SwitchCase(transcription.PLAIN_CALLER, pokes)


def _savestate_for(pd, pokes, tag=0):
    return switch.entered_with_a_uda(switch.SAVESTATE_CALLER, _uda_of(pd, pokes) | tag, pokes)


# (routine, shape) -> the staged case, made when asked: each machine a ROM run's (the scheduler's running process;
# what savestate's own run leaves), but the one labelled.
CASES = {
    (SPL7_SAVE, "a running process"): lambda: _plain(aes_event.machine()),
    (SPL_RESTORE, "the word spl7_save parked"): lambda: _plain(aes_event.machine()),
    (CLI, "a running process"): lambda: _plain(aes_event.machine()),
    (STI, "a running process"): lambda: _plain(aes_event.machine()),
    (SAVESTATE, "the desk's, as disp enters it"): lambda: _savestate_for(aes.SHELL_PD, aes_event.machine()),
    (SAVESTATE, "the screen manager's"):
        lambda: _savestate_for(aes.SCREEN_MANAGER_PD, aes_event.screen_manager_running()),
    (SAVESTATE, "the UDA on the bus"): lambda: _savestate_for(aes.SHELL_PD, aes_event.machine(), aes.BUS_TAG),
    (SWITCHTO, "the process savestate just saved"):
        lambda: switch.entered_with_a_uda(switch.SWITCHTO_CALLER, _uda_of(aes.SHELL_PD, _saved()), _saved()),
    (SWITCHTO, "the UDA on the bus"):
        lambda: switch.entered_with_a_uda(switch.SWITCHTO_CALLER, _uda_of(aes.SHELL_PD, _saved()) | aes.BUS_TAG, _saved()),
}
TIER_1_ONLY = {
    (GOTOPGM, "a staged basepage (a poked field, one staged instruction)"): lambda: _plain(_a_staged_basepage()),
}


@pytest.mark.parametrize("name,shape", sorted({**CASES, **TIER_1_ONLY}), ids=lambda value: value)
def test_the_switch_s_routine_behaves_as_the_rom(name, shape):
    """The image and the whole register file, both shores entered by one staged caller with one register file."""
    entered = {**CASES, **TIER_1_ONLY}[(name, shape)]()
    transcription.run_transcription(name, entered.pokes, caller=entered.caller)


def test_savestate_stores_its_caller_s_whole_context_and_comes_back_on_the_dispatcher_s_stack():
    """WHAT THE RELATION COMPARED, read off the ROM's own run of the first case: the UDA holds the register file the
    run was entered with — D0..A5 in the block's order, A0 the one dsptch pushed, A6 the caller's — the address of the
    `rte` frame, and the user stack pointer; the guard is counted; and the run came back holding disp's frame
    pointer, the user stack pointer in A5 and its own return address in A0."""
    entered = CASES[(SAVESTATE, "the desk's, as disp enters it")]()
    pokes = transcription.transcription_pokes(SAVESTATE, entered.pokes, entered.caller)
    final, _writes, regs = emu.run(make_image(pokes), entered.caller.at, dict(transcription.DIRTY))
    uda = _uda_of(aes.SHELL_PD, entered.pokes)
    dirty = transcription.DIRTY
    block = struct.unpack(f">{aes.UDA_REG_COUNT}I", bytes(final[uda + aes.UDA_REGS:uda + aes.UDA_A6]))
    assert block == tuple(dirty[name] for name in emu.REPORTED_REGS[:aes.UDA_REG_COUNT])
    assert case.long_in(final, uda + aes.UDA_A6) == dirty["a6"]
    assert case.long_in(final, uda + aes.UDA_SUPER_SP) == switch.PARKED_FRAME_AT
    assert case.long_in(final, switch.PARKED_FRAME_AT + WORD_BYTES) == emu.SENTINEL
    assert final[aes.AES_INDISP] == make_image(entered.pokes)[aes.AES_INDISP] + 1 == aes.AES_INDISP_SET
    assert regs["a5"] == case.long_in(final, uda + aes.UDA_USER_SP)
    assert regs["a6"] == switch.PARKED_FRAME_AT - 2 * LONG_BYTES, "disp's frame pointer: under dsptch's A0"


def test_switchto_gives_back_every_register_savestate_took():
    """...and switchto, over that machine, ends the run through the frame with the WHOLE register file the first run
    was entered with, the guard cleared."""
    entered = CASES[(SWITCHTO, "the process savestate just saved")]()
    pokes = transcription.transcription_pokes(SWITCHTO, entered.pokes, entered.caller)
    final, _writes, regs = emu.run(make_image(pokes), entered.caller.at, {})
    assert {name: regs[name] for name in emu.REPORTED_REGS} == transcription.DIRTY
    assert final[aes.AES_INDISP] == 0


def test_dsptch_under_the_guard_is_a_bare_rts():
    """THE LEVER'S ARM, labelled: with the dispatcher's guard set dsptch returns at once, nothing stored — on both
    shores (the snapshot's own state, taken inside the dispatcher: no process runs with it)."""
    assert BASE_IMAGE[aes.AES_INDISP] == aes.AES_INDISP_SET
    pokes = merge_pokes({transcription.PLAIN_CALLER.at: transcription.PLAIN_CALLER.stub,
                         transcription.abi.FIRST_ARG: struct.pack(">I", addrs.AES_ROM_DSPTCH)})
    measured = transcription.bench().measure_transcription(
        transcription.PLAIN_CALLER.at, "aes_dsptch", dict(transcription.DIRTY), pokes=pokes,
        shared_entry=transcription.PLAIN_CALLER.cost)
    assert measured.ratio == 1.0


# Tier 3's rows: every routine's cases but the labelled ones.
for (_name, _shape), _case in sorted(CASES.items()):
    _entered = _case()
    transcription.register_transcription(_name, _shape, _entered.pokes, caller=_entered.caller)
