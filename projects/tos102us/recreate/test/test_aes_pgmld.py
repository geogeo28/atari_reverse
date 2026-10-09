"""pgmld `$fe39bc` (`src/aes/gemdosif.c`, and `gemdosif.S` on target): a program loaded and its block cut to size —
hand 68000 over `__DOS`.

    pgmld(handle, name, &basepage):
        Pexec(3, name, "", 0)          -> error: return -1
        *basepage = D0
        Mshrink(0, D0, 256 + p_tlen + p_dlen + p_blen)   -> error: return -1;  else return 1

Its two answers are D0's whole longword (`moveq`); its caller reads the word (`$fe4342 move.w d0,-2(a6)`,
`cmpi.w #-1`). The `1` is dos_sfirst's own `moveq #1,d0 / rts` at `$fe3a08`, branched into.

EVERY CASE OVER THE RECORDING, SCRIPTED TRAP (`aes_gemdosif.GEMDOS`): the two calls with their whole frames — Pexec's
mode, name, TAIL and environment; Mshrink's reserved word, block and size — the site each parks, the verdict.
The basepage Pexec "answers" is one this battery stages: THREE LENGTHS IN A BLOCK OF THE BAND, a labelled ARGUMENT
CLASS (no program is loaded: GEMDOS's own Pexec and Mshrink are the GEMDOS batteries').

WHAT REACHES IT TODAY: nothing of the post-boot machine — its one caller is the accessory loader (`$fe433e`, band 5's
wave 3), which runs while GEM starts. OWED on the accessory machine: that call, through the ROM's real Pexec of a
real `.ACC` on the staged disk.
"""
import struct

import pytest

from harness import BASE_IMAGE, addrs, bench_tier3, emu
from recreate_kit import rom_bench

import aes
import aes_event
import aes_gemdosif as gd
import aes_shell as shell
import case
import test_aes_gsx_transcription as frames
import transcription
import vdi
import vdi_helpers
from case import merge_pokes

PGMLD = gd.PGMLD
GEMDOSIF = aes.header_constants("gemdosif.h")
LOADED, FAILED = GEMDOSIF["PGMLD_LOADED"], GEMDOSIF["PGMLD_FAILED"]
PEXEC, MSHRINK = gd.PEXEC, gd.MSHRINK
THROUGH = pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
ARGUMENT_CLASS = "ARGUMENT CLASS (a staged basepage's three lengths)"
PEXEC_LOAD = 3                          # Pexec's mode: load, do not start ($fe39c6 `move.l #$004b0003,-(sp)`)
EMPTY_TAIL = addrs.AES_PGMLD_EMPTY_TAIL
GEMDOS_OK = 0
ENSMEM, EFILNF, EGSBF = -39, -33, -67   # no memory, file not found, Mshrink's "cannot grow"
A_HANDLE = 7                            # what the loader opened the file with: never read
NAME_AT = gd.PATH_AT
OUT_AT = aes.RECTS_AT                   # where the caller keeps the basepage's address
BASEPAGE = gd.BASEPAGE_AT
NAME = merge_pokes(shell.text(NAME_AT, "A:\\CONTROL.ACC", gd.PATH_BYTES))
STALE_OUT = {OUT_AT: vdi.STALE_LONG.to_bytes(aes.LONG_BYTES, "big")}


def basepage(text, data, bss):
    """The staged basepage: FILLed, its three lengths set."""
    raw = bytearray([vdi.FILL]) * gd.BASEPAGE_BYTES
    for at, value in ((addrs.BASEPAGE_TLEN, text), (addrs.BASEPAGE_DLEN, data), (addrs.BASEPAGE_BLEN, bss)):
        raw[at:at + aes.LONG_BYTES] = struct.pack(">I", value & aes.LONG_MASK)
    return {BASEPAGE: bytes(raw)}


# Pexec's frame is the one of the glue wider than the GEMDOS words' slot: the host keeps it in a slot of its own, staged
# FILLED, so a field of the frame the C failed to lay reads as fill in the ledger (the ROM's frame is on its stack).
DIRTY_FRAME = aes.stale_host_slot("AES_PGMLD_WORDS", fill=vdi.FILL)


def pgmld(answers, lengths=(0x1234, 0x56, 0x789), *, name=NAME_AT, out=OUT_AT, handle=A_HANDLE, **kwargs):
    return gd.run_scripted(PGMLD, (handle, name, out), answers, merge_pokes(NAME, STALE_OUT, DIRTY_FRAME, basepage(*lengths)),
                           **kwargs)


def pexec(name=NAME_AT):
    return gd.call(PEXEC, ("w", PEXEC_LOAD), ("l", name), ("l", EMPTY_TAIL), ("l", 0))


def mshrink(kept, block=BASEPAGE):
    return gd.call(MSHRINK, ("w", 0), ("l", block), ("l", kept))


def parked(result):
    return result.long(aes.AES_TRAP1_RETURN)


def verdict(result):
    return result.field("AES", "DOS_ERR"), result.field("AES", "DOS_AX")


def test_a_failed_pexec_ends_the_twin_at_once__held_in_a_child():
    """FIRST, AND IN A CHILD: a twin that went on past Pexec's failure would read a basepage at a negative address —
    the host's bus guard ends the process, which in this one brings the suite down with no verdict. Here it is a child
    that did not return: the twin answers -1 and exits clean, one Pexec made."""
    machine = gd.scripted_machine([ENSMEM], merge_pokes(NAME, STALE_OUT, basepage(1, 2, 3)))
    returncode, stderr, image = aes_event.refusal(PGMLD, machine, (A_HANDLE, NAME_AT, OUT_AT), bind=gd.FRESH_CHILD_DOORS,
                                                  answered=True)
    assert returncode == 0 and vdi_helpers.answer_in(stderr) == FAILED & aes.WORD_MASK, stderr
    assert gd.calls(image) == [pexec()]


def test_the_tail_pgmld_hands_pexec_is_a_zero_word_of_the_rom_s_text():
    assert case.word_in(BASE_IMAGE, EMPTY_TAIL) == 0 and addrs.AES_ROM_PGMLD - EMPTY_TAIL == 8


@THROUGH
def test_pgmld_loads_stores_the_basepage_and_shrinks_its_block_to_the_program_s_size(through_line_f):
    """Pexec(3) over the name, the EMPTY tail and no environment; the basepage stored through the caller's pointer;
    Mshrink(0, basepage, 256 + text + data + bss); 1 answered. The site parked is the SECOND call's."""
    result = pgmld([BASEPAGE, GEMDOS_OK], through_line_f=through_line_f)
    assert gd.calls(result.final) == [pexec(), mshrink(256 + 0x1234 + 0x56 + 0x789)]
    assert [trap1 for _dos, trap1 in gd.sites_parked_at(result.final)] == [addrs.AES_PGMLD_PEXEC_RETURN, addrs.AES_PGMLD_MSHRINK_RETURN]
    assert (result.answer(), result.long(OUT_AT)) == (LOADED, BASEPAGE)
    assert parked(result) == addrs.AES_PGMLD_MSHRINK_RETURN and verdict(result) == (0, 0)


@THROUGH
@pytest.mark.parametrize("error", (ENSMEM, EFILNF, 0x8000_0000), ids=("ENSMEM", "EFILNF", "the least long"))
def test_a_pexec_that_fails_answers_minus_1_and_goes_no_further(error, through_line_f):
    """A negative LONG from Pexec: -1, the caller's pointer NOT stored through, no Mshrink; the site parked Pexec's."""
    result = pgmld([error], through_line_f=through_line_f)
    assert gd.calls(result.final) == [pexec()]
    assert (result.answer(), result.long(OUT_AT)) == (FAILED, vdi.STALE_LONG)
    assert parked(result) == addrs.AES_PGMLD_PEXEC_RETURN and verdict(result) == (1, error & aes.WORD_MASK)


def test_a_mshrink_that_fails_answers_minus_1_with_the_basepage_stored():
    result = pgmld([BASEPAGE, EGSBF])
    assert (result.answer(), result.long(OUT_AT)) == (FAILED, BASEPAGE)
    assert verdict(result) == (1, EGSBF & aes.WORD_MASK)


def test_the_answers_are_whole_longwords():
    """`moveq #1,d0` and `moveq #-1,d0`: D0's high word is the answer's too, on the ROM's own runs."""
    for answers, expected in (([BASEPAGE, GEMDOS_OK], 1), ([ENSMEM], 0xFFFF_FFFF)):
        assert pgmld(answers).long_answer() == expected


@pytest.mark.parametrize("lengths, kept", (
    ((0, 0, 0), 256), ((0xFFFF_FF00, 0, 0), 0), ((0x7FFF_FFFF, 0x7FFF_FFFF, 2), 256), ((1, 2, 4), 263)),
    ids=("no program at all: the basepage", "a sum that wraps to 0", "three lengths that wrap", "odd: not rounded"))
def test_the_size_kept_is_a_longword_sum_of_the_basepage_and_the_three_lengths(lengths, kept):
    """ARGUMENT CLASS. `move.l #256,d0 / add.l 12(a0) / add.l 20(a0) / add.l 28(a0)`: 32-bit, unrounded, unchecked."""
    result = pgmld([BASEPAGE, GEMDOS_OK], lengths)
    assert gd.calls(result.final)[1] == mshrink(kept)


def test_a_positive_long_whose_word_is_negative_is_a_basepage():
    """The verdict is the LONG's sign: a block at $8000 (its word negative) is a load, read through and shrunk."""
    at = 0x0000_8000
    assert at + gd.BASEPAGE_BYTES < aes.AES_THEGLO and not any(BASE_IMAGE[at:at + 0x20])
    lengths = merge_pokes({at + addrs.BASEPAGE_TLEN: struct.pack(">I", 0x10), at + addrs.BASEPAGE_DLEN: struct.pack(">I", 0x20),
                           at + addrs.BASEPAGE_BLEN: struct.pack(">I", 0x40)})
    result = gd.run_scripted(PGMLD, (A_HANDLE, NAME_AT, OUT_AT), [at, GEMDOS_OK], merge_pokes(NAME, STALE_OUT, lengths))
    assert result.answer() == LOADED and gd.calls(result.final)[1] == mshrink(256 + 0x70, at)


def test_the_pointers_are_handed_on_as_given():
    """The name reaches GEMDOS top byte and all; the basepage is stored through the caller's pointer on the bus."""
    result = pgmld([BASEPAGE, GEMDOS_OK], name=NAME_AT | aes.BUS_TAG, out=OUT_AT | aes.BUS_TAG)
    assert gd.calls(result.final)[0] == pexec(NAME_AT | aes.BUS_TAG) and result.long(OUT_AT) == BASEPAGE


def test_the_basepage_is_stored_before_its_lengths_are_read():
    """ARGUMENT CLASS (the caller's pointer naming the basepage's OWN text-length field). `move.l d0,(a0)` comes
    before `add.l 12(a0),d0`: the length read is then the basepage's address, just stored — and the size kept says
    so."""
    out = BASEPAGE + addrs.BASEPAGE_TLEN
    result = pgmld([BASEPAGE, GEMDOS_OK], out=out)
    assert result.long(out) == BASEPAGE and gd.calls(result.final)[1] == mshrink(256 + BASEPAGE + 0x56 + 0x789)


@pytest.mark.parametrize("handle", (0, -1, 0x1234))
def test_the_handle_is_not_read(handle):
    assert gd.calls(pgmld([BASEPAGE, GEMDOS_OK], handle=handle).final) == [pexec(), mshrink(256 + 0x1234 + 0x56 + 0x789)]


def test_pexec_s_site_is_parked_before_mshrink_s():
    """THE FIRST PARK, which the second overwrites: the ROM's own run stopped where Pexec comes back."""
    pokes = aes.staged(PGMLD, (A_HANDLE, NAME_AT, OUT_AT), gd.scripted_machine([BASEPAGE, 0], merge_pokes(NAME, basepage(1, 2, 3))))
    final, _writes, _regs = emu.run(vdi.make_image(pokes), addrs.AES_ROM_PGMLD, {}, stop_pc=addrs.AES_PGMLD_PEXEC_RETURN)
    assert case.long_in(final, aes.AES_TRAP1_RETURN) == addrs.AES_PGMLD_PEXEC_RETURN


# ---- the registry -------------------------------------------------------------------------------------------------------------
# THE C TWIN'S ROWS. ONE LONGWORD DIFFERS BY NATURE ON TARGET, and is dropped by name: THE COMMAND TAIL'S ADDRESS in
# the frame Pexec is trapped with, which the ledger records — the address of a zero word, in the ROM's own text
# (`$fe39b4`, `pea` pc-relative) on the ROM's shore and on the host; the twin compiled for the target hands a zero
# word of its own. ACCEPTED AS A KIND ONLY BECAUSE IT IS MAPPED AND SYMMETRIC (ruling R-3): our run stores the
# ledger's bytes too (Tier 3's rule), WHAT OUR POINTER NAMES is held below on both blobs — a zero word inside the
# blob — and its companion is the host differential with nothing dropped (the host hands the ROM's address).
TAIL_IN_THE_LEDGER = gd.LEDGER.first + 2 * aes.WORD_BYTES + aes.LONG_BYTES      # entry 0: the function, the mode, the name
TAIL_DROP = ((TAIL_IN_THE_LEDGER, TAIL_IN_THE_LEDGER + aes.LONG_BYTES,
              "pgmld's command tail: the address of a zero word — the ROM's text's at $fe39b4, the C twin's own on "
              "target; MAPPED (held on both blobs: the pointer names a zero word of the blob) and symmetric"),)
_MACHINE = merge_pokes(NAME, STALE_OUT, basepage(0x1234, 0x56, 0x789))
LOADED_AND_SHRUNK, MSHRINK_REFUSES = f"{ARGUMENT_CLASS}: loaded and shrunk", f"{ARGUMENT_CLASS}: Mshrink refuses"
PEXEC_REFUSES = "Pexec refuses"
ROWS = {LOADED_AND_SHRUNK: [BASEPAGE, GEMDOS_OK], PEXEC_REFUSES: [EFILNF], MSHRINK_REFUSES: [BASEPAGE, EGSBF]}
ARGUMENTS = (A_HANDLE, NAME_AT, OUT_AT)
# THE ARM WHERE Pexec FAILS IS OVER THE BAR AS C: 80 cycles more than the ROM's 716 (1.11); the two arms that reach
# Mshrink are 1.02 (`gemdosif.c` has what was tried). So pgmld SHIPS AS THE ROM'S OWN INSTRUCTIONS (`gemdosif.S`,
# byte-pinned by `test_aes_gemdosif_transcription.py`), every row of which the table prices below.
# THE ONE RULE FOR THE C TWIN OF A ROUTINE THAT SHIPS AS ITS `.S` (`recreate/README.md`, "What ships as the ROM's own
# instructions"): a twin's row OVER the bar is in the table, verdict `transcribed`, held to its `.S` rows
# (`tier3.ships_within_bar`); a twin's row UNDER the bar would print with no verdict — and read as C that ships —
# so it is registered VERIFIED AND UNPRICED, listed in the census with its number, and held here (below).
IN_THE_TABLE = (PEXEC_REFUSES,)
REGISTERED = {label: gd.register_scripted(label, PGMLD, ARGUMENTS, answers, _MACHINE, dropped=TAIL_DROP,
                                          priced=label in IN_THE_TABLE) for label, answers in ROWS.items()}
EXCESS_AS_C = 80
# The two arms out of the table, on the bench's blob: the ROM's cycles, ours, net of the entry (1.02 each).
UNDER_THE_BAR_AS_C = {LOADED_AND_SHRUNK: (1562, 1588), MSHRINK_REFUSES: (1562, 1590)}


def test_the_dropped_longword_is_the_tail_s_place_in_the_ledger():
    """...read off the ROM's own run: the four bytes dropped hold `$fe39b4`."""
    result = pgmld([BASEPAGE, GEMDOS_OK])
    assert result.long(TAIL_IN_THE_LEDGER) == EMPTY_TAIL


def _c_row(label):
    """The C twin's bench row of the case `label`: the table's own where it is in the table, made the same way —
    with its one named drop — where it is not."""
    tier3 = bench_tier3()
    if label in IN_THE_TABLE:
        return tier3.row_named(("aes_pgmld", label))
    return tier3._row(REGISTERED[label])._replace(dropped=TAIL_DROP)


@pytest.mark.parametrize("label", UNDER_THE_BAR_AS_C)
def test_the_twin_s_arms_out_of_the_table_are_the_rom_s_on_the_bench_s_blob_and_under_the_bar(label):
    """THE NUMBERS THE TABLE DOES NOT PRINT: each arm's second differential (the image but the tail's address, the
    answer, the registers) and its cycles, pinned — under the bar, which is why it has no row."""
    tier3 = bench_tier3()
    measured = tier3.measure(_c_row(label), tier3.RomBench())
    assert (measured.original_net, measured.recreate_net) == UNDER_THE_BAR_AS_C[label]
    assert measured.ratio <= tier3.TIER3_FUNCTION_BAR


@pytest.mark.parametrize("label", ROWS)
def test_on_the_bench_s_blob_the_tail_the_twin_hands_pexec_is_a_zero_word_of_its_own(label):
    """WHAT THE DROP EXCUSES, VETTED: the C twin's run of the row leaves, where the ROM's leaves `$fe39b4`, the
    address of A ZERO WORD INSIDE THE BLOB — an empty command tail of its own."""
    tier3 = bench_tier3()
    blob, row = tier3.RomBench(), _c_row(label)
    ours = blob._call(vdi.make_image(row.pokes), row.symbol, row.args).image
    tail = case.long_in(ours, TAIL_IN_THE_LEDGER)
    assert blob.base <= tail < blob.base + len(blob.blob), f"{label}: the tail {tail:#x} is not this build's"
    assert case.word_in(ours, tail) == 0


def test_the_arm_where_pexec_fails_is_over_the_bar_as_c_and_reads_transcribed():
    """THE TWIN'S NUMBER ON THAT ARM, pinned as the excess no handler's weight dilutes — 80 cycles more than the
    ROM's — over the bar, and carried by the `.S` rows alone: the table's own verdict for it is `transcribed`."""
    tier3 = bench_tier3()
    row = _c_row(PEXEC_REFUSES)
    measured = tier3.measure(row, tier3.RomBench())
    assert measured.recreate_net - measured.original_net == EXCESS_AS_C, (measured.original_net, measured.recreate_net)
    assert measured.ratio > tier3.TIER3_FUNCTION_BAR
    no_leaf_rule = None                 # the dispatch cost the LEAF RULE reads: (T) answers before it is asked
    assert tier3.verdict(row, measured, no_leaf_rule, lambda each: tier3.measure(each, tier3.RomBench())) == "transcribed"


# ---- THE `.S`: what the target ships ---------------------------------------------------------------------------------------
# Held to the ROM through Tier 3's transcription relation — the whole image, the whole register file, NOTHING DROPPED —
# over the same three arms. THE THREE ADDRESSES OF ITS OWN TEXT pgmld leaves in RAM are MAPPED, not blanked
# (`aes_event.TEXT_SITES`, read by `tier3.code_relocations`): the two sites `__DOS` parks in AES_TRAP1_RETURN, which
# the recording trap copies into its ledger at each call, and the command tail's address in Pexec's recorded frame.
# This battery declares where its ledger can hold them; the registry already names AES_TRAP1_RETURN.
LEDGER_SITES = gd.TRAP1_SITES_IN_THE_LEDGER
assert TAIL_IN_THE_LEDGER == gd.PEXEC_TAILS_IN_THE_LEDGER[0] and set(LEDGER_SITES) <= set(aes_event.TEXT_SITE_SLOTS)
S_ENTRY = transcription.transcription_symbol(PGMLD)
S_ROWS = {label: frames.register(label, PGMLD, ARGUMENTS, gd.scripted_machine(answers, _MACHINE))
          for label, answers in ROWS.items()}


def _s_row(label):
    return bench_tier3().row_named((S_ENTRY, label))


@pytest.mark.parametrize("label", ROWS)
def test_the_transcription_behaves_as_the_rom_with_its_own_sites_mapped(label, blob):
    """Both blobs hold the one `.S`: the image whole and the register file whole, the three text addresses mapped
    ROM <-> ours — and the mapping is NOT VACUOUS: the row's own run, unmapped, holds this build's sites."""
    tier3 = bench_tier3()
    tier3._measure_transcription(_s_row(label), blob)
    assert tier3.text_site_relocation(blob.elf, S_ENTRY).keys() == set(aes_event.TEXT_SITE_SYMBOLS)


@pytest.mark.parametrize("label", ROWS)
def test_what_the_transcription_parks_is_its_own_text_site_for_site(label, blob):
    """WHAT THE MAPPING STANDS ON, read off OUR run before anything is mapped back (the kit's own `_call`, past
    Tier 3's): AES_TRAP1_RETURN and the ledger hold the `.S`'s OWN return sites — each the instruction after its
    `bsr` of the hop — and Pexec's frame the `.S`'s own zero word."""
    row, placed = _s_row(label), bench_tier3()._placed(blob.elf)
    sites = [placed[aes_event.TEXT_SITE_SYMBOLS[rom]] for rom in (addrs.AES_PGMLD_PEXEC_RETURN, addrs.AES_PGMLD_MSHRINK_RETURN)]
    ours = rom_bench.RomBench._call(blob, vdi.make_image(row.pokes), row.symbol, args=(blob.entry(row.symbol),),
                                    entry_at=row.entry, seed_regs=[row.regs[name] for name in emu.REPORTED_REGS]).image
    made = len(ROWS[label])
    assert [case.long_in(ours, at) for at in LEDGER_SITES[:made]] == sites[:made]
    assert case.long_in(ours, aes.AES_TRAP1_RETURN) == sites[made - 1]
    tail = case.long_in(ours, TAIL_IN_THE_LEDGER)
    assert tail == placed[aes_event.TEXT_SITE_SYMBOLS[EMPTY_TAIL]] and case.word_in(ours, tail) == 0


def test_a_text_site_left_unmapped_is_refused_by_name(blob, monkeypatch):
    """THE RED of the mapping: with the registry's entry for one site taken away, the same row is refused by name
    at the first thing that holds it — A0, where `__DOS`'s `jmp (a0)` left it (the register file is compared before
    the image, which holds it twice more). The relation drops nothing."""
    tier3 = bench_tier3()
    less = {rom: site for rom, site in aes_event.TEXT_SITE_SYMBOLS.items() if rom != addrs.AES_PGMLD_PEXEC_RETURN}
    monkeypatch.setattr(aes_event, "TEXT_SITES", aes_event.TEXT_SITES._replace(symbols=less))
    tier3.text_site_relocation.cache_clear()
    try:
        with pytest.raises(AssertionError, match=rf"a0 {addrs.AES_PGMLD_PEXEC_RETURN:#x} -> "):
            tier3._measure_transcription(_s_row(PEXEC_REFUSES), blob)
    finally:
        tier3.text_site_relocation.cache_clear()


def test_the_twin_s_run_is_mapped_on_neither_blob():
    """...and the C twin's rows are left as they stand: it parks the ROM's own sites (data, as every C glue's are).
    ON THE SHIPPED BLOB TOO — `aes_pgmld` there is still the weak C twin: no C calls pgmld yet, so no thunk enters
    the `.S` under that name."""
    tier3 = bench_tier3()
    assert not tier3.text_site_relocation(tier3.BUILT_ELF, aes_event.TEXT_SITE_CORE)
    assert not tier3.text_site_relocation(transcription.SHIPPED_ELF, aes_event.TEXT_SITE_CORE)


def test_a_c_caller_of_pgmld_is_declared_where_its_sites_are_mapped():
    """THE DAY pgmld HAS A C CALLER (the accessory loader, wave 3): the pair is in the door's table — held to the
    build's own call graph by `test_transcribed.py`, and what the shipped blob's thunk is generated from — and that
    caller parks the `.S`'s sites on the shipped blob, so it must be named in `aes_event.TEXT_SITE_CALLERS` too."""
    callers = {caller for caller, core in transcription.C_CALLERS_OF_TRANSCRIBED_CORES if core == aes_event.TEXT_SITE_CORE}
    assert callers == set(aes_event.TEXT_SITE_CALLERS) == set(), "none yet: say so in both places when one lands"
    tier3 = bench_tier3()
    assert not tier3.text_site_relocation(transcription.SHIPPED_ELF, "aes_sh_tographic"), "a run that parks none is mapped nowhere"


def test_a_rom_text_site_left_in_a_register_is_refused_by_name():
    """THE REGISTERS' VET (the slots' rule): our run leaving the ROM's own site in A0 is a relocation un-applied."""
    tier3 = bench_tier3()
    mapping = tier3.text_site_relocation(tier3.BUILT_ELF, S_ENTRY)
    regs = dict.fromkeys(emu.REPORTED_REGS, 0)
    tier3.vet_no_register_names_the_rom(S_ENTRY, {**regs, "a0": mapping[addrs.AES_PGMLD_PEXEC_RETURN]}, mapping)
    with pytest.raises(AssertionError, match="ROM'S OWN text site 0xfe39ce in A0"):
        tier3.vet_no_register_names_the_rom(S_ENTRY, {**regs, "a0": addrs.AES_PGMLD_PEXEC_RETURN}, mapping)


def test_the_transcription_s_row_is_refused_where_our_run_leaves_the_rom_s_site_in_a0(blob, monkeypatch):
    """...AND THE VET IS ASKED OF EVERY RUN: our run made to leave THE ROM'S site in A0 — what a `.S` whose `bsr`
    was assembled against the ROM's layout would do — is refused by name. Without the vet it would PASS: the
    mapping leaves a ROM address alone, and the ROM's own run holds that very value."""
    made = rom_bench.RomBench._call

    def leaving_the_rom_s_site(self, image, symbol, *args, **kwargs):
        ours = made(self, image, symbol, *args, **kwargs)
        ours.regs["a0"] = addrs.AES_PGMLD_PEXEC_RETURN
        return ours
    monkeypatch.setattr(rom_bench.RomBench, "_call", leaving_the_rom_s_site)
    with pytest.raises(AssertionError, match="ROM'S OWN text site 0xfe39ce in A0"):
        bench_tier3()._measure_transcription(_s_row(PEXEC_REFUSES), blob)
