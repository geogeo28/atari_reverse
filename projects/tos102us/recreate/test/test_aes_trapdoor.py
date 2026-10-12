"""THE TRAP DOOR as the target build ships it (`src/aes/trapdoor.S`) — ITS BYTES: `trap #2`'s handler, its way out and
ub_trampoline as the ROM's own (`$fe3ea6..$fe3f5d`), and gemsuper's aes_entry as the ROM's own instruction stream.
(What it DOES is `test_aes_trapdoor_rows.py`'s: the arms and the round trip run from real arrivals on both blobs.)

FOUR CLAIMS HOLD IT.
  * THE REGION'S BYTES are the ROM's, every word but FIVE longwords, on BOTH blobs: the four `jsr`s of the mask
    brackets, which go to `switch.S`'s two, and the `movea.l #` of aes_entry, which names the stream below.
  * aes_entry IS THE ROM'S STREAM instruction by instruction (`transcription.assert_stream`): its three Line-F call
    words NAMED, each a `jsr` of the entry that stands for the routine the ROM's table reaches — the marshal's thunk,
    the dispatcher's entry, the way out — and its one short branch following the four bytes the first `jsr` adds.
  * WHAT THE PINS DO NOT REACH IS HELD BESIDE THEM: the source's symbols tile its text with nothing between, before
    or after; the thunk is its shape into `aes_marshal`; the table's lengths are the build's.
  * WHAT IS DEAD IS PROVED DEAD, from the ROM's own bytes: the way out never returns (so aes_entry's Line-F return
    and the instruction after the handler's `jsr (a0)` are never executed as a return), and it is reached from one
    place.

INSTALLED BY THE BUILD'S OWN TAKES SINCE THE NARROW DOOR FLIP (band 5 wave 3, slice F): `gemdosif.S`'s install_trap2
and retake store THIS handler (their operand is `aes_rom_trap2`, relocated in their own pin), and the relocation
registry maps it (`aes_event.GEM_TRAP_VECTOR`). WHO STILL NAMES THE ROM'S DOOR is said as a list, not left to be
found, and it is EMPTY: the same two takes' C TWINS (`gemdosif.c`) moved with them, and no word of a blob names the
ROM's door.
"""
import subprocess
from pathlib import Path

import pytest

from harness import BASE_IMAGE, addrs
from recreate_kit.rom_bench import RomBench

import aes
import aes_switch as switch
import aes_trapdoor as door
import case
import rom_data
import test_aes_rom_data as rom_census
import transcription
from opcodes import RTE, RTS
from transcription import ABSOLUTE, CallWord, Relocated

LONG_BYTES, WORD_BYTES = aes.LONG_BYTES, aes.WORD_BYTES
RECREATE = Path(__file__).resolve().parents[1]
ENTRIES = transcription.TRAPDOOR_ENTRIES
HANDLER, WAY_OUT, UB, ENTRY = door.HANDLER_SYMBOL, door.WAY_OUT_SYMBOL, door.UB_SYMBOL, door.ENTRY_SYMBOL
REGION_S_ENTRIES = (HANDLER, WAY_OUT, UB)
REGION = transcription.pinned_region(door.REGION_LO, door.REGION_HI, "AES_ROM_TRAP2",
                                     ("AES_ROM_TRAP2_EXIT", "AES_ROM_UB_TRAMPOLINE"))
# THE FIVE OPERANDS THAT NAME OUR BUILD, each by the instruction that holds it (its operand lies one word in): the
# mask brackets' four calls — two in the AES arm, two in the way out — and aes_entry by value.
SPL7_SAVE_CALLS, SPL_RESTORE_CALLS = (0xFE3ECA, 0xFE3F0C), (0xFE3EF2, 0xFE3F36)
ENTRY_BY_VALUE_AT = 0xFE3F00
UB_S_CALL_AT = 0xFE3F50                 # ...and the one that still names the ROM: the desk's draw code (band 6)
THE_SWITCH_S_ANCHOR = "AES_ROM_SPL7_SAVE"


def _operand(instruction):
    return instruction + WORD_BYTES


RELOCATED = {
    **{_operand(site): Relocated(ABSOLUTE, THE_SWITCH_S_ANCHOR, "a `jsr` of spl7_save, where `switch.S` lays it out")
       for site in SPL7_SAVE_CALLS},
    **{_operand(site): Relocated(ABSOLUTE, THE_SWITCH_S_ANCHOR, "a `jsr` of spl_restore, where `switch.S` lays it out")
       for site in SPL_RESTORE_CALLS},
    _operand(ENTRY_BY_VALUE_AT): Relocated(ABSOLUTE, None, "aes_entry by value, into A0: where our stream is linked",
                                           thunk=ENTRY),
}
# What each relocated operand must hold, as a symbol of the blob asked: the same five on either blob.
NAMED_BY_OPERAND = {**{_operand(site): "aes_rom_spl7_save" for site in SPL7_SAVE_CALLS},
                    **{_operand(site): "aes_rom_spl_restore" for site in SPL_RESTORE_CALLS},
                    _operand(ENTRY_BY_VALUE_AT): ENTRY}
# aes_entry's three Line-F call words IN THE ROM'S ORDER, each with the ROM routine its table entry reaches and the
# entry our `jsr` names. WHERE each lies is read off the ROM — the words of aes_entry that are no 68000 instruction.
CALLS_IN_ORDER = (CallWord("AES_ROM_MARSHAL", door.MARSHAL_THUNK), CallWord("AES_ROM_DSPTCH", "aes_dsptch"),
                  CallWord("AES_ROM_TRAP2_EXIT", WAY_OUT))
CALL_WORDS_AT = tuple(at for at, text in rom_data.instructions(door.ENTRY, door.ENTRY_END) if text is None)
assert len(CALL_WORDS_AT) == len(CALLS_IN_ORDER), "aes_entry makes three Line-F calls and its stream ends on the third"
assert CALL_WORDS_AT[-1] == door.ENTRY_END - WORD_BYTES
STREAM = transcription.stream(door.ENTRY, door.ENTRY_END, ENTRY, dict(zip(CALL_WORDS_AT, CALLS_IN_ORDER)))
SOURCE_S_SYMBOLS = (*REGION_S_ENTRIES, ENTRY, door.MARSHAL_THUNK)
BLOBS = switch.BLOBS


@pytest.fixture(scope="module", params=BLOBS.values(), ids=BLOBS)
def blob(request):
    return RomBench(request.param)


# ---- the bytes ----------------------------------------------------------------------------------------------------------
def test_the_region_is_the_rom_s_bytes_but_for_the_five_operands_that_name_our_build():
    """THE BYTE PIN: every word of `$fe3ea6..$fe3f5d` the ROM's, and the five that are not exactly where the mask
    brackets and our aes_entry are linked — ub_trampoline's `jsr` of the desk's draw code among the words EQUAL."""
    transcription.assert_transcribed(REGION, relocated=RELOCATED)


def test_the_region_is_the_same_bytes_on_both_blobs(blob):
    """...and on the shipped configuration's blob too: every byte the ROM's but those five operands, each naming
    THAT blob's entry."""
    ours = transcription.bytes_of(blob, REGION.anchor, REGION.lo, REGION.hi - REGION.lo)
    theirs = bytes(BASE_IMAGE[REGION.lo:REGION.hi])
    at = 0
    for operand, symbol in sorted(NAMED_BY_OPERAND.items()):
        offset = operand - REGION.lo
        assert ours[at:offset] == theirs[at:offset], f"the region differs from the ROM's before the operand at ${operand:x}"
        assert ours[offset:offset + LONG_BYTES] == blob.entry(symbol).to_bytes(LONG_BYTES, "big"), (
            f"the operand at ${operand:x} does not name this blob's {symbol}")
        at = offset + LONG_BYTES
    assert ours[at:] == theirs[at:]


def test_the_five_operands_are_every_word_of_the_region_that_names_aes_code():
    """THE LIST IS THE ROM'S OWN: every instruction of the region whose operand NAMES A ROUTINE OF THE AES'S TEXT is
    one of the five relocated — or ub_trampoline's call of the desk's draw code, the one word that stays the ROM's
    (band 6: the census `test_aes_rom_data.py` lists it for `trapdoor.S`, CODE)."""
    naming = {_operand(operand.site): operand.value for operand in rom_data.text_operands(REGION.lo, REGION.hi)
              if not operand.pc_relative and aes.AES_TEXT[0] <= operand.value < aes.AES_TEXT[1]}
    calls = {_operand(at): int(text.split()[-1], 16) for at, text in rom_data.instructions(REGION.lo, REGION.hi)
             if text and text.startswith("jsr 0x")}
    named = {**naming, **calls}
    assert set(named) == set(RELOCATED) | {_operand(UB_S_CALL_AT)}
    assert named[_operand(UB_S_CALL_AT)] == addrs.AES_ROM_DESK_USERDEF
    assert named[_operand(ENTRY_BY_VALUE_AT)] == addrs.AES_ROM_ENTRY
    assert {named[_operand(site)] for site in SPL7_SAVE_CALLS} == {addrs.AES_ROM_SPL7_SAVE}
    assert {named[_operand(site)] for site in SPL_RESTORE_CALLS} == {addrs.AES_ROM_SPL_RESTORE}
    assert rom_census.ROM_ADDRESSES_AS_DATA["trapdoor.S"] == {"AES_ROM_DESK_USERDEF": rom_census.CODE}


def test_aes_entry_is_the_rom_s_stream_its_three_call_words_made_jsrs(blob):
    """THE STREAM PIN, on both blobs: instruction by instruction the ROM's aes_entry — the three substitutions named,
    no other Line-F word in it, its one branch the ROM's own to the instruction the ROM's goes to."""
    transcription.assert_stream(STREAM, blob)


def test_the_registry_of_streams_holds_this_battery_s_one():
    assert [declared for declared in transcription.STREAMS if declared.symbol == ENTRY] == [STREAM]


def test_every_stream_of_the_registry_is_one_of_the_two_batteries_declarations():
    """THE CENSUS THE TWO BATTERIES MAKE TOGETHER (wave 3's review, A-F11): each holds "the declarations of MY symbol
    are my one" — so a stream declared under a THIRD symbol (a test's own, leaked; a new battery's, unread) would be
    seen by neither. With both batteries' modules imported, the registry is exactly their two, whoever ran before."""
    import test_aes_switch
    assert sorted(transcription.STREAMS, key=lambda declared: declared.lo) == sorted(
        [STREAM, test_aes_switch.STREAM], key=lambda declared: declared.lo), "a stream no battery of the two declares, or one declared twice"


def test_the_source_holds_its_entries_its_thunk_and_nothing_else(blob):
    """WHAT THE PINS DO NOT REACH, held: `trapdoor.S`'s symbols — the region's three routines, aes_entry, the thunk —
    lie END TO END in each blob with nothing between them and nothing after the last but the assembler's fill; and
    the thunk is one longword's shape into `aes_marshal` (`aes_switch.vet_a_thunk`)."""
    switch.vet_laid_end_to_end(blob, SOURCE_S_SYMBOLS)
    switch.vet_a_thunk(blob, door.MARSHAL_THUNK, switch.ONE_LONG_THUNK, "aes_marshal")
    assert {door.MARSHAL_THUNK} == ENTRIES[ENTRY].exits - set(ENTRIES) - set(transcription.SWITCH_ENTRIES)


def test_a_thunk_into_another_routine_and_a_run_of_symbols_that_leaves_one_out_are_refused(blob):
    """THE TWO VETS' OWN REDS on this source: the thunk held to another body; the run without aes_entry (its bytes
    then lie between two of the others, in no symbol of the run)."""
    with pytest.raises(AssertionError, match="is not its shape into aes_dispatch"):
        switch.vet_a_thunk(blob, door.MARSHAL_THUNK, switch.ONE_LONG_THUNK, "aes_dispatch")
    with pytest.raises(AssertionError, match="is where the one before it ends"):
        switch.vet_laid_end_to_end(blob, tuple(name for name in SOURCE_S_SYMBOLS if name != ENTRY))


@pytest.mark.parametrize("variable", ("BENCH_CFLAGS", "SHIPPED_CFLAGS"))
def test_no_byte_of_the_source_lies_ahead_of_its_first_symbol(variable, tmp_path):
    """WHAT THE END-TO-END VET CANNOT SEE IN A LINKED BLOB, held on the source's OWN OBJECT under each blob's flags:
    the first instruction of `trapdoor.S` is its handler's."""
    (source,) = map(Path, transcription.trapdoor_sources())
    made = tmp_path / "trapdoor.o"
    subprocess.run(["m68k-elf-gcc", *transcription.make_variable(RECREATE, variable), "-c", str(source), "-o", str(made)],
                   cwd=RECREATE, check=True, capture_output=True)
    assert switch.first_symbol_offsets([made]) == {made: (HANDLER, 0)}


# ---- the table, and the build contract ------------------------------------------------------------------------------------
@pytest.mark.parametrize("entry", sorted(ENTRIES))
def test_each_entry_of_the_table_is_where_and_what_the_table_says(entry, blob):
    """THE TABLE (`transcription.TRAPDOOR_ENTRIES`) against the build: a byte-exact entry is as long as the ROM's
    routine and lies where the ROM has it in the region's layout; aes_entry is the stream's length, its `jsr`s in."""
    row = ENTRIES[entry]
    start, end = door.text_spans(blob)[entry]
    size = end - start
    if entry == ENTRY:
        assert size == row.bytes + len(CALLS_IN_ORDER) * (transcription.JSR_BYTES - WORD_BYTES)
        return
    assert size == row.bytes, f"{entry} is {size} bytes, the ROM's routine {row.bytes}"
    assert blob.entry(entry) == door.in_the_region(blob, row.rom)


def test_the_table_s_exits_are_the_symbols_the_pins_name():
    """An entry's EXITS — what its bytes name of our build where the ROM's name the ROM's — are exactly its pin's:
    the relocations that lie in its bytes, the stream's three call words. ub_trampoline has none: its one call is
    still the ROM's (above)."""
    for entry in REGION_S_ENTRIES:
        row = ENTRIES[entry]
        assert row.exits == {NAMED_BY_OPERAND[at] for at in NAMED_BY_OPERAND if row.rom <= at < row.rom + row.bytes}
    assert ENTRIES[ENTRY].exits == {call.symbol for call in STREAM.calls.values()}
    assert not ENTRIES[UB].exits


def test_the_region_is_the_three_routines_end_to_end():
    """The table's lengths tile the region: the handler to the instruction after its `jsr (a0)`, the way out to its
    `rte`, ub_trampoline to its `rts` — and what follows in the ROM (signal, `$fe3f5e`: Alcyon C) is not here."""
    at = REGION.lo
    for entry in REGION_S_ENTRIES:
        assert ENTRIES[entry].rom == at, f"{entry} begins at {ENTRIES[entry].rom:#x}, the routine before it ends at {at:#x}"
        at += ENTRIES[entry].bytes
    assert at == REGION.hi
    assert bytes(BASE_IMAGE[door.WAY_OUT_RTE:door.WAY_OUT_RTE + len(RTE)]) == RTE and door.WAY_OUT_RTE + len(RTE) == door.UB_TRAMPOLINE
    assert bytes(BASE_IMAGE[REGION.hi - len(RTS):REGION.hi]) == RTS


def test_the_trap_door_is_its_own_kind_of_the_build_contract():
    """`trapdoor.S` is no transcription (no row, no C twin, no thunk generated over an entry), no Alcyon entry and —
    while it is linked and not installed — no source of the switch's: listed apart, as make expands the lists."""
    lists = {name: transcription.make_variable(RECREATE, name)
             for name in ("TRAPDOOR_SOURCES", "SWITCH_SOURCES", "TRANSCRIBED_SOURCES", "ALCYON_ENTRY_SOURCES")}
    ours = lists["TRAPDOOR_SOURCES"]
    assert [Path(source).name for source in ours] == ["trapdoor.S"]
    assert [Path(source).resolve() for source in ours] == [Path(source).resolve() for source in transcription.trapdoor_sources()]
    for other in ("SWITCH_SOURCES", "TRANSCRIBED_SOURCES", "ALCYON_ENTRY_SOURCES"):
        assert not set(ours) & set(lists[other]), f"trapdoor.S is also listed in {other}"
    entries = set(ENTRIES)
    assert not entries & (set(transcription.TRANSCRIBED) | set(transcription.ALCYON_ENTRIES) | set(transcription.SWITCH_ENTRIES))
    assert not entries & {transcription.transcribed_core(entry) for entry in transcription.TRANSCRIBED}


# ---- what is dead, proved from the ROM's bytes ----------------------------------------------------------------------------
TRANSFERS = ("rts", "rte", "rtr", "jmp", "jsr", "bsr", "trap")


def _transfers(lo, hi):
    """The instructions of [lo, hi) that can leave the straight line: a branch, a call, a return, a Line-F word."""
    return [(at, text) for at, text in rom_data.instructions(lo, hi)
            if text is None or text.split()[0].startswith("b") or text.split()[0] in TRANSFERS]


def test_the_way_out_never_returns_so_aes_entry_s_line_f_return_is_dead():
    """The way out's body holds no branch and no return but its last instruction, an `rte` — and two calls, of the
    mask brackets, which come back to it: whoever calls it is never come back to. aes_entry's Line-F return
    (`$fe65c2`) lies behind its call of the way out and nothing branches to it: the stream ends before it."""
    *before, last = _transfers(door.WAY_OUT, door.UB_TRAMPOLINE)
    assert last == (door.WAY_OUT_RTE, "rte")
    assert [at for at, _text in before] == [SPL7_SAVE_CALLS[1], SPL_RESTORE_CALLS[1]], f"the way out leaves early: {before}"
    for bracket in (addrs.AES_ROM_SPL7_SAVE, addrs.AES_ROM_SPL_RESTORE):
        assert [text for _at, text in _transfers(bracket, bracket + transcription.SWITCH_ENTRIES[
            transcription.transcription_symbol(_name_of(bracket))].bytes)] == ["rts"]
    stream = rom_data.instructions(door.ENTRY, door.ENTRY_END + WORD_BYTES)
    assert stream[-1] == (door.ENTRY_END, None) and stream[-2] == (CALL_WORDS_AT[-1], None)
    into_the_return = [at for at, text in stream[:-1] if text and f"{door.ENTRY_END:#x}" in text]
    assert not into_the_return, f"aes_entry branches to its own return at {into_the_return}"


def _name_of(bracket):
    return {addrs.AES_ROM_SPL7_SAVE: "AES_ROM_SPL7_SAVE", addrs.AES_ROM_SPL_RESTORE: "AES_ROM_SPL_RESTORE"}[bracket]


def test_the_handler_s_call_of_aes_entry_is_never_returned_from():
    """aes_entry leaves by its call of the way out on every path — its only other transfers are the branch round the
    marshal and its two calls before — so the handler's `jsr (a0)` is never returned from: the way out lies behind
    it by the ROM's LAYOUT, not by a fall-through, and it is entered by aes_entry's call alone."""
    transfers = _transfers(door.ENTRY, door.ENTRY_END)
    assert [at for at, _text in transfers] == [CALL_WORDS_AT[0] - 3 * WORD_BYTES, *CALL_WORDS_AT]
    assert transfers[0][1].startswith("bnes") and f"{CALL_WORDS_AT[1]:#x}" in transfers[0][1], "the branch round the marshal"
    assert list(aes.line_f_call_sites("AES_ROM_TRAP2_EXIT").values()) == [(CALL_WORDS_AT[-1],)], "one call word, one site"
    last_of_the_handler = rom_data.instructions(door.HANDLER, door.WAY_OUT)[-1]
    assert last_of_the_handler == (door.WAY_OUT - WORD_BYTES, "jsr %a0@")


def test_aes_entry_is_named_by_the_handler_alone_and_the_door_by_the_sites_the_census_lists():
    """WHO NAMES THE DOOR IN THE ROM, off the census of its code immediates: aes_entry by ONE instruction, the
    handler's own (relocated above); the handler by install_trap2 and retake (`gemdosif.S`: the two operands the
    narrow door flip re-pointed at `aes_rom_trap2`); ub_trampoline by gem_entry (wave 4)."""
    naming = {site: row.value for site, row in rom_census.CODE_IMMEDIATES.items()
              if any(row.value == entry.rom for entry in ENTRIES.values())}
    assert naming == {0xFD9F9E: addrs.AES_ROM_UB_TRAMPOLINE, 0xFE3C78: addrs.AES_ROM_TRAP2, 0xFE3C84: addrs.AES_ROM_TRAP2,
                      ENTRY_BY_VALUE_AT: addrs.AES_ROM_ENTRY}
    assert aes.line_f_call_sites("AES_ROM_ENTRY") == {} == aes.line_f_call_sites("AES_ROM_TRAP2")


# ---- NOBODY NAMES THE ROM'S DOOR ANY MORE, since the narrow door flip ----------------------------------------------------------
# Every even longword of a blob that names an address INSIDE the ROM's bytes of an entry of the door: NONE.
#   * install_trap2's and retake's operand in `gemdosif.S` (the ROM's sites $fe3c78, $fe3c84) name THE BUILD'S OWN
#     HANDLER, on both blobs: held here from the blob's own bytes;
#   * and so do their C TWINS (`gemdosif.c`: `gem_trap2_handler`, `ALCYON_ROUTINE`) — linked on the bench blob, and
#     on the shipped one the weak bodies a thunk of the same name stands over. (They HAD to move with the `.S`: a
#     twin that stores the ROM's handler over a machine that did not come with it is refused by the registry's own
#     vet on its `(T)` rows — `tier3.vet_no_slot_names_the_rom`.)
# (The graphics bridge's check of vector $88, `aes/gsx.h`, is host-only: it compiles to no word of a blob.) What is
# left of the door's by-value sites is gem_entry's `lea` of ub_trampoline — wave 4's, in no blob yet.
# A word that names the ROM's door reds here.
VECTOR_TAKE_SITES = (0xFE3C78, 0xFE3C84)
THE_TAKES_REGION_S_ANCHOR = "AES_ROM_RESTORE_TRAP2"
THEIR_C_TWINS = ("aes_install_trap2", "aes_retake")


def _door_entry_named(value):
    return next((name for name, row in ENTRIES.items() if row.rom <= value < row.rom + row.bytes), None)


def _words_naming_the_rom_s_door(blob):
    """`{address in blob: the door's entry named}` over every even longword of `blob`."""
    return {blob.base + offset: _door_entry_named(int.from_bytes(blob.blob[offset:offset + LONG_BYTES], "big"))
            for offset in range(0, len(blob.blob) - LONG_BYTES + 1, WORD_BYTES)
            if _door_entry_named(int.from_bytes(blob.blob[offset:offset + LONG_BYTES], "big"))}


def test_no_word_of_a_blob_names_the_rom_s_door_and_the_takes_store_the_build_s_own_handler(blob):
    assert not _words_naming_the_rom_s_door(blob), "a word of the blob names the ROM's door: who stores it, and into what?"
    handler = blob.entry(HANDLER).to_bytes(LONG_BYTES, "big")
    takes = blob.entry(transcription.transcription_symbol(THE_TAKES_REGION_S_ANCHOR)) - getattr(addrs, THE_TAKES_REGION_S_ANCHOR)
    for site in VECTOR_TAKE_SITES:
        operand = takes + _operand(site) - blob.base
        assert blob.blob[operand:operand + LONG_BYTES] == handler, f"the take at ${site:x} does not store `{HANDLER}`"
    # ...and the twins: each body holds the handler's address once (the bench blob sizes them; the shipped blob's weak
    # bodies are counted with the `.S`'s two — four words a blob, wherever the linker laid them)
    holding = [offset for offset in range(0, len(blob.blob) - LONG_BYTES + 1, WORD_BYTES)
               if blob.blob[offset:offset + LONG_BYTES] == handler]
    assert len(holding) == len(VECTOR_TAKE_SITES) + len(THEIR_C_TWINS)
    if blob.elf == transcription.BENCH_ELF:
        twins = [door.text_spans(blob)[twin] for twin in THEIR_C_TWINS]
        in_the_twins = [at for at in holding if any(lo <= blob.base + at < hi for lo, hi in twins)]
        assert len(in_the_twins) == len(THEIR_C_TWINS)


def test_that_scan_sees_a_planted_word():
    """ITS RED: a blob of sixteen bytes holding the ROM's way out's address at an even offset is found, by entry."""
    planted = addrs.AES_ROM_TRAP2_EXIT.to_bytes(LONG_BYTES, "big")
    assert _door_entry_named(addrs.AES_ROM_TRAP2_EXIT) == WAY_OUT and _door_entry_named(door.ENTRY_END) is None
    assert _door_entry_named(int.from_bytes(planted, "big") + WORD_BYTES) == WAY_OUT
    assert _door_entry_named(case.long_in(BASE_IMAGE, _operand(ENTRY_BY_VALUE_AT))) == ENTRY
