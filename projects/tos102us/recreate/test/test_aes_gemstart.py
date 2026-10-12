"""GEMSTART as the target build ships it (`src/aes/gemstart.S`) — gem_entry and gem_gemdos_call as the ROM's own bytes
(`$fd9eca..$fd9ffb`), and what gem_entry copies — the Line-F handler and the call table's first 38 bytes — as DATA
(`$fee8c2..$fee925`).

FIVE CLAIMS HOLD IT.
  * THE TEXT'S BYTES are the ROM's, every word but SEVEN longwords, on BOTH blobs: the handler gem_entry copies (this
    file's own data region), its three `jsr`s (rom_rsc_init through a thunk, size_theglo and gem_main as the C they
    are) and the three routines it stores BY VALUE (`irq.S`'s bare `rts` and tick glue, `trapdoor.S`'s ub_trampoline).
  * THE COPIED HUNDRED BYTES are the ROM's with NO word relocated (ruling W4-R3: the Line-F call table stays the
    ROM's) — its `movea.l #$fee900` and nine and a half ROM addresses, which nothing of a build executes: no word of
    a blob outside the region names the handler but gem_entry's one operand.
  * THE SEVEN ARE THE ROM'S OWN LIST: every operand of the region that names a routine or a table of GEM's text is
    one of them, read off the ROM's instructions — a `lea` left the ROM's would be an eighth, and reds.
  * WHAT THE PINS DO NOT REACH IS HELD BESIDE THEM: the source's symbols tile its text; the thunk is its shape into
    `aes_rom_rsc_init`; the table's lengths are the build's; gemstart is its own kind of the build contract.
  * gem_gemdos_call BEHAVES AS THE ROM'S — the image and the WHOLE REGISTER FILE, through Tier 3's transcription
    relation on both blobs, over a recording, scripted `trap #1`: the frame GEMDOS reads is its caller's, the answer's
    word is kept, and a negative LONGWORD alone is an error. AN ARGUMENT CLASS (ruling W4-R14): its four ROM callers
    are the shell's utilities, band 6's.

NOT HELD HERE — gem_entry BY A RUN. It is entered by no call and never returns; what it does is slice B's, on the
our-boot machine (the blob laid at the pre-init stop): its arrivals at rom_rsc_init, at the loop's top and at
gem_main, the `$2c` test's two arms, THEGLO cleared. Until then every instruction of it is held by the byte pin alone.
"""
import struct
import subprocess
from pathlib import Path

import pytest

from harness import BASE_IMAGE, addrs, emu, make_image
from recreate_kit.rom_bench import RomBench

import abi
import aes
import aes_gemdosif
import aes_geminit as gi
import aes_switch as switch
import aes_trapdoor as door
import case
import rom_data
import test_aes_rom_data as rom_census
import transcription
import vdi
from case import merge_pokes
from opcodes import DROP_STACK_BYTES, JSR_ABSOLUTE_LONG, PUSH_RETURN_PC, PUSH_STACK_LONG, PUSH_WORD_IMMEDIATE, RTS
from transcription import ABSOLUTE, Relocated

LONG_BYTES, WORD_BYTES = aes.LONG_BYTES, aes.WORD_BYTES
RECREATE = Path(__file__).resolve().parents[1]
ENTRIES = transcription.GEMSTART_ENTRIES
GEM_ENTRY, GEMDOS_CALL, HANDLER = "aes_rom_gem_entry", "aes_rom_gem_gemdos_call", "aes_rom_linef_handler"
RSC_INIT_THUNK = "gemstart_to_aes_rom_rsc_init"
REGION = transcription.pinned_region(addrs.AES_ROM_GEM_ENTRY, addrs.AES_ROM_GEM_ENTRY_END, "AES_ROM_GEM_ENTRY",
                                     ("AES_ROM_GEM_GEMDOS_CALL",))
COPIED = transcription.pinned_region(addrs.AES_ROM_LINEF_HANDLER, addrs.AES_ROM_LINEF_COPY_END, "AES_ROM_LINEF_HANDLER")
# THE SEVEN OPERANDS THAT NAME OUR BUILD, each by the instruction that holds it (its operand lies one word in).
COPIES_THE_HANDLER_AT = 0xFD9F4A
CALLS_RSC_INIT_AT, CALLS_SIZE_THEGLO_AT, CALLS_GEM_MAIN_AT = 0xFD9F5E, 0xFD9F72, 0xFD9FBE
THE_GLUE_S_ANCHOR, THE_TRAP_DOOR_S_ANCHOR = "AES_ROM_BUTTON_GLUE", "AES_ROM_TRAP2"
ANCHOR_OF_A_VALUE = {"aes_rom_justretf": THE_GLUE_S_ANCHOR, "aes_rom_tick_glue": THE_GLUE_S_ANCHOR,
                     "aes_rom_ub_trampoline": THE_TRAP_DOOR_S_ANCHOR}


def _operand(instruction):
    return instruction + WORD_BYTES


RELOCATED = {
    _operand(COPIES_THE_HANDLER_AT): Relocated(ABSOLUTE, "AES_ROM_LINEF_HANDLER", "the handler gem_entry copies: this file's own data"),
    _operand(CALLS_RSC_INIT_AT): Relocated(ABSOLUTE, None, "rom_rsc_init ships as C", thunk=RSC_INIT_THUNK),
    _operand(CALLS_SIZE_THEGLO_AT): Relocated(ABSOLUTE, None, "size_theglo ships as C, and takes nothing", thunk="aes_size_theglo"),
    _operand(CALLS_GEM_MAIN_AT): Relocated(ABSOLUTE, None, "gem_main ships as C: its target entry takes nothing", thunk="aes_rom_gem_main"),
    **{_operand(site): Relocated(ABSOLUTE, ANCHOR_OF_A_VALUE[symbol], f"{symbol} stored by value, where its `.S` lays it out")
       for site, symbol in gi.STORED_BY_VALUE.items()},
}
# What each relocated operand must hold, as a symbol of the blob asked: the same seven on either blob.
NAMED_BY_OPERAND = {_operand(COPIES_THE_HANDLER_AT): HANDLER, _operand(CALLS_RSC_INIT_AT): RSC_INIT_THUNK,
                    _operand(CALLS_SIZE_THEGLO_AT): "aes_size_theglo", _operand(CALLS_GEM_MAIN_AT): "aes_rom_gem_main",
                    **{_operand(site): symbol for site, symbol in gi.STORED_BY_VALUE.items()}}
# ...and the ROM address the ROM's own operand names there.
THE_ROM_NAMES = {_operand(COPIES_THE_HANDLER_AT): addrs.AES_ROM_LINEF_HANDLER, _operand(CALLS_RSC_INIT_AT): addrs.AES_ROM_ROM_RSC_INIT,
                 _operand(CALLS_SIZE_THEGLO_AT): addrs.AES_ROM_SIZE_THEGLO, _operand(CALLS_GEM_MAIN_AT): addrs.AES_ROM_GEM_MAIN,
                 **{_operand(site): getattr(addrs, symbol.upper()) for site, symbol in gi.STORED_BY_VALUE.items()}}
SOURCE_S_SYMBOLS = (GEM_ENTRY, GEMDOS_CALL, RSC_INIT_THUNK, HANDLER)
BLOBS = switch.BLOBS


@pytest.fixture(scope="module", params=BLOBS.values(), ids=BLOBS)
def blob(request):
    return RomBench(request.param)


# ---- the bytes ----------------------------------------------------------------------------------------------------------
def test_gemstart_s_text_is_the_rom_s_bytes_but_for_the_seven_operands_that_name_our_build():
    """THE BYTE PIN: every word of `$fd9eca..$fd9ffb` the ROM's — the first stack's `movea.l #$898e,sp`, the `$2c`
    test and its `beq`, the clear's `move.w d1,(a0)+ / dbmi d0`, gem_gemdos_call whole — and the seven that are not
    exactly where this build links what each names."""
    transcription.assert_transcribed(REGION, relocated=RELOCATED)


def test_what_gem_entry_copies_is_the_rom_s_hundred_bytes_with_no_word_relocated():
    """THE SECOND PIN, and no excuse in it: the handler's `movea.l #$fee900,a0` and the call table's first nine and a
    half longwords are the ROM's addresses (ruling W4-R3) — and the region is exactly what the copy takes."""
    transcription.assert_transcribed(COPIED, relocated=RELOCATED)
    assert not [at for at in RELOCATED if COPIED.lo <= at < COPIED.hi]
    assert COPIED.hi - COPIED.lo == aes.LINEF_COPY_BYTES == 2 * aes.header_constants("aes.h")["LINEF_COPY_WORDS"]
    assert case.long_in(BASE_IMAGE, COPIED.lo + aes.LINEF_TABLE_OPERAND) == aes.AES_LINEF_TABLE


def test_both_regions_are_the_same_bytes_on_both_blobs(blob):
    """...and on the shipped configuration's blob too: every byte the ROM's but the seven operands, each naming THAT
    blob's symbol."""
    ours = transcription.bytes_of(blob, REGION.anchor, REGION.lo, REGION.hi - REGION.lo)
    theirs = bytes(BASE_IMAGE[REGION.lo:REGION.hi])
    at = 0
    for operand, symbol in sorted(NAMED_BY_OPERAND.items()):
        offset = operand - REGION.lo
        assert ours[at:offset] == theirs[at:offset], f"the text differs from the ROM's before the operand at ${operand:x}"
        assert ours[offset:offset + LONG_BYTES] == blob.entry(symbol).to_bytes(LONG_BYTES, "big"), (
            f"the operand at ${operand:x} does not name this blob's {symbol}")
        at = offset + LONG_BYTES
    assert ours[at:] == theirs[at:]
    assert transcription.bytes_of(blob, COPIED.anchor, COPIED.lo, COPIED.hi - COPIED.lo) == bytes(BASE_IMAGE[COPIED.lo:COPIED.hi])


def test_the_seven_operands_are_every_word_of_the_text_that_names_gem_s_code():
    """THE LIST IS THE ROM'S OWN: every instruction of the region whose operand NAMES A ROUTINE OR A TABLE OF GEM'S
    TEXT — an immediate, an absolute `lea`, a `jsr` — is one of the seven relocated, and names what the pin says. A
    `lea` left the ROM's would be an operand of this list the pin holds EQUAL to the ROM's: refused there."""
    naming = {_operand(operand.site): operand.value for operand in rom_data.text_operands(REGION.lo, REGION.hi)
              if not operand.pc_relative and aes.AES_TEXT[0] <= operand.value < aes.AES_TEXT[1]}
    calls = {_operand(at): int(text.split()[-1], 16) for at, text in rom_data.instructions(REGION.lo, REGION.hi)
             if text and text.startswith("jsr 0x")}
    assert {**naming, **calls} == THE_ROM_NAMES and set(THE_ROM_NAMES) == set(RELOCATED)
    assert len(RELOCATED) == 7


def test_the_by_value_sites_are_the_census_s_rows_of_gem_entry():
    """...AND THE CENSUS'S (`test_aes_rom_data.CODE_IMMEDIATES`): its four rows of gem_entry are the handler it copies
    and the three it stores — each relocated here, each owed by no C file (gem_entry has no C core), and none listed
    as a ROM address `gemstart.S` still uses (census (a) lists the copied table's alone)."""
    rows = {site: row.value for site, row in rom_census.CODE_IMMEDIATES.items() if REGION.lo <= site < REGION.hi}
    assert rows == {COPIES_THE_HANDLER_AT: addrs.AES_ROM_LINEF_HANDLER,
                    **{site: THE_ROM_NAMES[_operand(site)] for site in gi.STORED_BY_VALUE}}
    assert all(rom_census.CODE_IMMEDIATES[site].owed_by is None for site in rows)
    used = set(rom_census.ROM_ADDRESSES_AS_DATA["gemstart.S"])
    assert not used & {"AES_ROM_LINEF_HANDLER", "AES_ROM_JUSTRETF", "AES_ROM_TICK_GLUE", "AES_ROM_UB_TRAMPOLINE",
                       "AES_ROM_ROM_RSC_INIT", "AES_ROM_SIZE_THEGLO", "AES_ROM_GEM_MAIN"}


def test_each_value_is_stored_where_the_rom_stores_it():
    """The three `lea`s' stores, off the ROM's own instructions: the bare `rts` into AES_DRWADDR, the tick glue into
    the longword gem_main hands vex_timv, ub_trampoline into the desk's G_USERDEF slot — the three slots the
    relocation registry maps the day a build's gem_entry runs."""
    listed = dict(rom_data.instructions(REGION.lo, REGION.hi))
    following = sorted(listed)
    for site, slot in gi.STORED_INTO.items():
        store = following[following.index(site) + 1]
        assert listed[site].startswith("lea 0x") and listed[store] == f"movel %a0,{slot:#x}", f"${site:x}: {listed[store]}"


def test_no_word_of_a_blob_names_the_rom_s_gemstart_and_one_names_the_handler_s_copy_source(blob):
    """WHO NAMES GEMSTART BY VALUE: no word of a blob names the ROM's gem_entry or gem_gemdos_call (the BIOS's
    `exec_os` and the AES basepage do, in RAM: the machine's, not a build's) nor the ROM's handler — the one word
    that names an address of the copied hundred bytes is THEIR OWN, the handler's `movea.l #$fee900` (the ROM's call
    table, ruling W4-R3) —; and this blob's handler is named by ONE longword, gem_entry's operand."""
    longs = {blob.base + offset: int.from_bytes(blob.blob[offset:offset + LONG_BYTES], "big")
             for offset in range(0, len(blob.blob) - LONG_BYTES + 1, WORD_BYTES)}
    naming_the_rom = {at: value for at, value in longs.items()
                      if any(row.rom <= value < row.rom + row.bytes for row in ENTRIES.values())}
    assert naming_the_rom == {blob.entry(HANDLER) + aes.LINEF_TABLE_OPERAND: aes.AES_LINEF_TABLE}, (
        f"a word of the blob names the ROM's gemstart: { {hex(at): hex(value) for at, value in naming_the_rom.items()} }")
    holding = [at for at, value in longs.items() if value == blob.entry(HANDLER)]
    assert holding == [blob.entry(GEM_ENTRY) + _operand(COPIES_THE_HANDLER_AT) - REGION.lo]


def test_the_usable_disk_word_a_build_s_gem_entry_leaves_is_not_zero(blob):
    """A GATE OF THE BUILD'S LAYOUT (`aes_geminit.THE_ROM_S_USABLE_WORD`): `$8992` lies in the first stack, and what
    is left there when gem_main runs is THE LOW WORD OF THE RETURN ADDRESS of gem_entry's `jsr` of size_theglo — the
    ROM's `$9f78`; a build's, wherever it links that instruction. The reader and the loader test it for non-zero:
    a build linked with that instruction at a multiple of 64 KB would boot as from an unusable disk. (And the word
    differs between the shores by nature: a class of the our-boot machine, slice B's.)
    ...OR THE LOW WORD OF AN INTERRUPTED PC (the integration's finding): the first stack is in use, at mask 3, from
    that return to the `movea.l a6,sp` that leaves it, and an exception frame taken at its top lays the PC it
    interrupted over the same four bytes — the machine's own captures hold `$9f80` / `$9f82`, the clear loop's two
    instructions. So the gate is the whole stretch: NO INSTRUCTION of it at a multiple of 64 KB."""
    assert bytes(BASE_IMAGE[gi.SIZE_THEGLO_CALLED_AT:gi.SIZE_THEGLO_CALLED_AT + WORD_BYTES]) == JSR_ABSOLUTE_LONG
    returns_to = blob.entry(GEM_ENTRY) + gi.SIZE_THEGLO_RETURNS_TO - REGION.lo
    assert gi.SIZE_THEGLO_CALLED_AT == CALLS_SIZE_THEGLO_AT and gi.THE_ROM_S_USABLE_WORD == 0x9F78
    assert returns_to & aes.WORD_MASK, f"gem_entry's `jsr` of size_theglo returns to {returns_to:#x}: its low word is the usable-disk word, and is 0"
    assert gi.DISK_USABLE + WORD_BYTES == gi.GEMSTART["GEM_FIRST_STACK"] + gi.GEMSTART["GEM_SUPER_FRAME_BYTES"]
    assert case.word_in(BASE_IMAGE, gi.LEAVES_THE_FIRST_STACK_AT) == gi.MOVEA_L_A6_SP, "the premise: where the ROM's gem_entry takes PD0's stack"
    on_the_first_stack = range(returns_to, returns_to + gi.LEAVES_THE_FIRST_STACK_AT - gi.SIZE_THEGLO_RETURNS_TO + WORD_BYTES, WORD_BYTES)
    assert all(at & aes.WORD_MASK for at in on_the_first_stack), (
        f"an instruction of gem_entry's stretch on the first stack links at a multiple of 64 KB "
        f"([{on_the_first_stack[0]:#x}, {on_the_first_stack[-1]:#x}]): an interrupt taken there leaves the usable-disk word 0")


# ---- what the pins do not reach ------------------------------------------------------------------------------------------
def test_the_source_holds_its_entries_its_thunk_its_data_and_nothing_else(blob):
    """`gemstart.S`'s symbols — gem_entry, gem_gemdos_call, the thunk, the copied data — lie END TO END in each blob
    with nothing between them and nothing after the last but the assembler's fill; and the thunk is the image base's
    shape into `aes_rom_rsc_init` (`aes_switch.vet_a_thunk`)."""
    switch.vet_laid_end_to_end(blob, SOURCE_S_SYMBOLS)
    switch.vet_a_thunk(blob, RSC_INIT_THUNK, switch.IMAGE_ONLY_THUNK, "aes_rom_rsc_init")


def test_a_thunk_into_another_routine_and_a_run_of_symbols_that_leaves_one_out_are_refused(blob):
    with pytest.raises(AssertionError, match="is not its shape into aes_gem_read_inf"):
        switch.vet_a_thunk(blob, RSC_INIT_THUNK, switch.IMAGE_ONLY_THUNK, "aes_gem_read_inf")
    with pytest.raises(AssertionError, match="is where the one before it ends"):
        switch.vet_laid_end_to_end(blob, tuple(name for name in SOURCE_S_SYMBOLS if name != RSC_INIT_THUNK))


@pytest.mark.parametrize("variable", ("BENCH_CFLAGS", "SHIPPED_CFLAGS"))
def test_no_byte_of_the_source_lies_ahead_of_its_first_symbol(variable, tmp_path):
    """The first instruction of `gemstart.S` is gem_entry's, on the source's OWN OBJECT under each blob's flags."""
    (source,) = map(Path, transcription.gemstart_sources())
    made = tmp_path / "gemstart.o"
    subprocess.run(["m68k-elf-gcc", *transcription.make_variable(RECREATE, variable), "-c", str(source), "-o", str(made)],
                   cwd=RECREATE, check=True, capture_output=True)
    assert switch.first_symbol_offsets([made]) == {made: (GEM_ENTRY, 0)}


@pytest.mark.parametrize("entry", sorted(ENTRIES))
def test_each_entry_of_the_table_is_where_and_what_the_table_says(entry, blob):
    """THE TABLE (`transcription.GEMSTART_ENTRIES`) against the build: each entry as long as the ROM's bytes of it
    and where the ROM has it in its region's layout."""
    row = ENTRIES[entry]
    start, end = door.text_spans(blob)[entry]
    assert end - start == row.bytes, f"{entry} is {end - start} bytes, the ROM's {row.bytes}"
    region = COPIED if entry == HANDLER else REGION
    assert start == blob.entry(transcription.transcription_symbol(region.anchor)) + row.rom - region.lo


def test_the_table_s_exits_are_the_symbols_the_pin_names():
    """gem_entry's EXITS are its pin's seven; gem_gemdos_call and the copied data name nothing of the build."""
    assert ENTRIES[GEM_ENTRY].exits == set(NAMED_BY_OPERAND.values())
    assert not ENTRIES[GEMDOS_CALL].exits and not ENTRIES[HANDLER].exits
    assert ENTRIES[GEM_ENTRY].rom + ENTRIES[GEM_ENTRY].bytes == ENTRIES[GEMDOS_CALL].rom == addrs.AES_ROM_GEM_GEMDOS_CALL
    assert ENTRIES[GEMDOS_CALL].rom + ENTRIES[GEMDOS_CALL].bytes == REGION.hi == addrs.AES_ROM_INI_DLONGS
    assert bytes(BASE_IMAGE[REGION.hi - len(RTS):REGION.hi]) == RTS


def test_gemstart_is_its_own_kind_of_the_build_contract():
    """`gemstart.S` is no transcription (no row, no C twin, no thunk generated over an entry), no Alcyon entry, no
    source of the switch's or the trap door's: listed apart, as make expands the lists."""
    lists = {name: transcription.make_variable(RECREATE, name) for name in (
        "GEMSTART_SOURCES", "TRAPDOOR_SOURCES", "SWITCH_SOURCES", "TRANSCRIBED_SOURCES", "ALCYON_ENTRY_SOURCES")}
    ours = lists["GEMSTART_SOURCES"]
    assert [Path(source).name for source in ours] == ["gemstart.S"]
    assert [Path(source).resolve() for source in ours] == [Path(source).resolve() for source in transcription.gemstart_sources()]
    for other in ("TRAPDOOR_SOURCES", "SWITCH_SOURCES", "TRANSCRIBED_SOURCES", "ALCYON_ENTRY_SOURCES"):
        assert not set(ours) & set(lists[other]), f"gemstart.S is also listed in {other}"
    entries = set(ENTRIES)
    assert not entries & (set(transcription.TRANSCRIBED) | set(transcription.ALCYON_ENTRIES) | set(transcription.SWITCH_ENTRIES)
                          | set(transcription.TRAPDOOR_ENTRIES))
    assert not entries & {transcription.transcribed_core(entry) for entry in transcription.TRANSCRIBED}


def test_gem_entry_is_entered_by_no_call_and_never_returns():
    """WHY IT IS ASSEMBLY, read off the ROM: no Line-F word and no `jsr` or `bsr` of GEM's text names gem_entry; its
    only way out of the loop is the `bra` back to its top — no `rts`, no `rte` before gem_gemdos_call's; and it loads
    the stack pointer itself, twice by `movea.l`."""
    assert aes.line_f_call_sites("AES_ROM_GEM_ENTRY") == {}
    body = rom_data.instructions(REGION.lo, addrs.AES_ROM_GEM_GEMDOS_CALL)
    assert not [at for at, text in body if text and text.split()[0] in ("rts", "rte", "rtr")]
    last_at, last = body[-1]
    assert last.startswith("bras") and int(last.split()[-1], 16) == CALLS_SIZE_THEGLO_AT, "the loop: back to size_theglo's call"
    assert [text for _at, text in body if text and text.endswith(",%sp") and text.startswith("moveal")] == [
        f"moveal #{gi.GEMSTART['GEM_FIRST_STACK']},%sp", "moveal %fp,%sp"]
    calls_of_it = [at for at, text in rom_data.instructions(*aes.AES_TEXT)
                   if text and text.split()[0] in ("jsr", "bsr", "bsrs", "bsrw", "jmp") and f"{addrs.AES_ROM_GEM_ENTRY:#x}" in text]
    assert not calls_of_it and last_at == addrs.AES_ROM_GEM_GEMDOS_CALL - WORD_BYTES


# ---- gem_gemdos_call, by the transcription relation ------------------------------------------------------------------------
# THE CALLER: a frame of the function word (and, for one case, a word above it) pushed, the return to its own tail
# pushed, the routine entered through the longword at abi.FIRST_ARG — the ROM's or the blob's — and the frame dropped:
#     move.w #<word>,-(sp) ... / pea back(pc) / move.l <slot>(sp),-(sp) / rts / back: lea <frame>(sp),sp / rts
# So the return address gem_gemdos_call parks is the CALLER's own, the same on both shores.
CALLERS_OFFSET, CALLERS_BYTES, CALLER_STRIDE = 0x2E40, 0x40, 0x20
CALLERS_AT = aes.SPAN.claim(aes.WINDOW_AT + CALLERS_OFFSET, CALLERS_BYTES, "test/test_aes_gemstart.py: gem_gemdos_call's frame callers")
CALLERS = transcription.CallerPool(CALLERS_AT, CALLERS_AT + CALLERS_BYTES, CALLER_STRIDE, grow="CALLERS_BYTES")
PUSH_WORD_COST, PEA_COST, PUSH_SLOT_COST, RTS_COST, DROP_COST = (1, 12), (1, 16), (1, 24), (1, 16), (1, 8)
TAIL = DROP_STACK_BYTES + struct.pack(">h", 0) + RTS         # the tail's size: `lea <d16>(sp),sp / rts`


def frame_caller(words):
    """The caller that pushes `words` (the last pushed is the function word) — built once per frame, registered."""
    def build():
        frame_bytes = len(words) * WORD_BYTES
        pushes = b"".join(PUSH_WORD_IMMEDIATE + struct.pack(">H", word) for word in words)
        enter = (PUSH_RETURN_PC + struct.pack(">h", WORD_BYTES + len(PUSH_STACK_LONG) + WORD_BYTES + len(RTS))
                 + PUSH_STACK_LONG + struct.pack(">h", abi.FIRST_ARG - emu.STACK_TOP + frame_bytes + LONG_BYTES) + RTS)
        tail = DROP_STACK_BYTES + struct.pack(">h", frame_bytes) + RTS
        costs = (*[PUSH_WORD_COST] * len(words), PEA_COST, PUSH_SLOT_COST, RTS_COST, DROP_COST, RTS_COST)
        return pushes + enter + tail, tuple(map(sum, zip(*costs)))
    return CALLERS.staged(tuple(words), build)


DGETDRV, DSETDRV = aes_gemdosif.DGETDRV, aes_gemdosif.DSETDRV
STALE = merge_pokes(aes_gemdosif.STALE_DOS, {aes.AES_GEMDOS_RETURN: vdi.STALE_LONG.to_bytes(LONG_BYTES, "big")})
A_DRIVE = 0x0003
# `(the frame's words as pushed, the trap's answer)`: both signs of the longword, a word that is negative in a
# positive longword, and a frame with a word of its own above the function.
ANSWERS = {
    "a positive answer": ((DGETDRV,), 0x0000_0002),
    "zero": ((DGETDRV,), 0),
    "a negative longword: an error": ((DGETDRV,), 0xFFFF_FFDF),
    "a positive longword whose WORD is negative: no error": ((DGETDRV,), 0x0001_8000),
    "the most negative": ((DGETDRV,), 0x8000_0000),
    "a frame of two words: GEMDOS reads the caller's own": ((A_DRIVE, DSETDRV), 0x0000_0007),
}


def staged_call(label):
    """`(the case's caller, its pokes with the ROM's routine entered)`."""
    words, answer = ANSWERS[label]
    caller = frame_caller(words)
    pokes = merge_pokes(STALE, aes_gemdosif.scripted_pokes([answer]))
    return caller, transcription.transcription_pokes("AES_ROM_GEM_GEMDOS_CALL", pokes, caller)


def run_gemdos_call(blob, label):
    """The case through the TRANSCRIPTION relation on `blob`: the image and the whole register file held equal."""
    caller, pokes = staged_call(label)
    return blob.measure_transcription(caller.at, GEMDOS_CALL, dict(transcription.DIRTY), pokes=pokes, shared_entry=caller.cost)


def the_rom_s_run(label):
    """...and the ROM's own run of it: `(the image it left, its register file)`."""
    caller, pokes = staged_call(label)
    final, _writes, registers = emu.run(make_image(pokes), caller.at, dict(transcription.DIRTY))
    return final, registers


@pytest.mark.parametrize("label", ANSWERS)
def test_gem_gemdos_call_is_the_rom_s_over_a_recorded_trap(label, blob):
    """THE (T) CASE, on both blobs: the image and the whole register file the ROM's, at the ROM's own cost."""
    assert run_gemdos_call(blob, label).ratio == pytest.approx(1.0), "the ROM's own instructions: one cost"


@pytest.mark.parametrize("label", ANSWERS)
def test_what_the_rom_s_gem_gemdos_call_does(label):
    """...AND WHAT THAT IS, off the ROM's run of the same case: the return address parked is the caller's own tail;
    the trap was taken over the caller's frame (the ledger's entry: the function, then its word); AES_DOS_AX the
    answer's word; AES_DOS_ERR 1 for a negative LONGWORD alone; D0 the answer, every other register as it was."""
    words, answer = ANSWERS[label]
    caller = frame_caller(words)
    final, registers = the_rom_s_run(label)
    assert case.long_in(final, aes.AES_GEMDOS_RETURN) == caller.at + len(caller.stub) - len(TAIL)
    function, *arguments = reversed(words)
    assert aes_gemdosif.calls(final) == [aes_gemdosif.call(function, *(("w", word) for word in arguments))]
    assert case.word_in(final, aes.AES_DOS_AX) == answer & aes.WORD_MASK
    assert case.word_in(final, aes.AES_DOS_ERR) == int(answer >= 0x8000_0000)
    assert registers["d0"] == answer and transcription.changed_from_dirty(registers) == {"d0"}


THE_ROM_S_GEMDOS_CALL = (addrs.AES_ROM_GEM_GEMDOS_CALL, addrs.AES_ROM_GEM_ENTRY_END)


def test_who_ran_gem_gemdos_call_on_each_shore(blob):
    """WHO RAN, by the cycle profile: the ROM's own run of a case spends its cycles in the ROM's routine and none in
    the blob's; and the two shores of the relation together spend IN THE ROM'S ROUTINE exactly what the ROM's run
    alone does — our shore not one cycle there — and the same count in the blob's own bytes, which are the same
    instructions."""
    label = "a negative longword: an error"
    ours = (blob.entry(GEMDOS_CALL), blob.entry(GEMDOS_CALL) + ENTRIES[GEMDOS_CALL].bytes)
    emu.prof_reset()
    emu.prof_enable(True)
    try:
        the_rom_s_run(label)
        alone = emu.prof_cycles(*THE_ROM_S_GEMDOS_CALL)
        assert alone > 0 and not emu.prof_cycles(*ours), "the ROM's run: in its own routine, never in the blob's"
        emu.prof_reset()
        run_gemdos_call(blob, label)
        assert emu.prof_cycles(*THE_ROM_S_GEMDOS_CALL) == alone, "our shore spent cycles in the ROM's gem_gemdos_call"
        assert emu.prof_cycles(*ours) == alone, "our shore did not run the blob's own gem_gemdos_call whole"
    finally:
        emu.prof_enable(False)
        emu.prof_reset()


@pytest.mark.parametrize("label", ANSWERS)
def test_each_frame_caller_costs_what_it_declares(label):
    transcription.assert_caller_cost(frame_caller(ANSWERS[label][0]))


def test_the_relation_sees_a_routine_that_is_not_the_rom_s(blob):
    """ITS RED: the case's caller entering ANOTHER entry of the build as "gem_gemdos_call" — the bare `rts`, which
    traps nothing and stores no verdict — is refused by the relation: D0, which the trap never answered."""
    caller, pokes = staged_call("a negative longword: an error")
    with pytest.raises(AssertionError, match="left a different register file than the original: d0"):
        blob.measure_transcription(caller.at, "aes_rom_justretf", dict(transcription.DIRTY), pokes=pokes, shared_entry=caller.cost)
