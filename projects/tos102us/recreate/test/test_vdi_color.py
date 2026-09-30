"""VDI vs_color (14, $fd2dd2) and vq_color (26, $fd2e84) — the palette pair: `src/vdi/palette.c`.

Both are hand-written 68000. A colour lives in TWO places: what was REQUESTED, per mille per gun, in
LINEA_REQ_COL (three words a colour, stored as given), and what the shifter REALIZED, three bits a gun,
in the palette register VDI_MAP_COL maps the index to. vs_color writes both; vq_color answers either.

THE EXPECTATIONS ARE COMPUTED HERE, out of the ROM's own tables in the snapshot (VDI_MAP_COL,
VDI_PEN_MASKS, VDI_VQ_COLOR_LEVELS) and the arithmetic the asm spells — so a case says what the ROM
does as well as that both shores agree on it.

THE PALETTE IS NOT IN THE IMAGE. A store is a ledgered hardware write (`hw_writes`), a read is a
DECLARED register (`io_seed`, both bytes — `test_xbios_setcolor.py`'s rule), and a read nobody
declared refuses the case, which is itself the claim that the requested arm reads no register.
"""
import pytest

from harness import BASE_IMAGE, addrs
from recreate_kit import os_map

import case
import transcription
import vdi

SET = "VDI_ROM_VS_COLOR"
GET = "VDI_ROM_VQ_COLOR"
WORD = vdi.WORD_BYTES
GUNS = vdi.VDI_REQ_COL_COMPONENTS
ROW_BYTES = GUNS * WORD
PER_MILLE_MAX = 1000
INVALID = 0xFFFF
# The plane counts of the ST's three resolutions; low is the snapshot's own.
LOW, MEDIUM, MONO = 4, 2, 1
# A plane count no resolution has, whose table byte is 0: only index 0 passes, through the colour arm.
THREE_PLANES = 3
REALIZED = 1
REQUESTED = 0


def word_index(entry, entry_bytes):
    """`mulu.w`/`add.w` then a `.w` index: the product wraps in a word and is sign-extended."""
    return vdi.signed_word((entry * entry_bytes) & 0xFFFF)


def pen_mask(planes):
    return BASE_IMAGE[vdi.VDI_PEN_MASKS + planes]


def on_the_bus(address):
    """An address register's address as the 68000's 24 pins put it on the bus."""
    return address & os_map.OS_BUS_ADDR_MASK


def register_of(index, planes):
    """The palette register colour `index` is shown in: its MAP_COL pen, low byte masked, doubled —
    folded, so a pen whose doubled offset passes $7dc0 is a word of low RAM, not a register."""
    pen = vdi.rom_word(vdi.VDI_MAP_COL + word_index(index, WORD))
    pen = (pen & 0xFF00) | (pen & pen_mask(planes))
    return on_the_bus(addrs.SHIFTER_PALETTE + word_index(pen, addrs.PALETTE_ENTRY_BYTES))


def requested_row(index):
    return on_the_bus(vdi.LINEA_REQ_COL + word_index(index, ROW_BYTES))


def in_io_page(address):
    return address >= os_map.OS_HW_IO_PAGE


def shifter_level(per_mille):
    return (min(max(vdi.signed_word(per_mille), 0), PER_MILLE_MAX) + 72) // 143


def shifter_word(guns):
    red, green, blue = (shifter_level(gun) for gun in guns)
    return red << 8 | green << 4 | blue


def mono_level(per_mille):
    value = vdi.signed_word(per_mille)
    return 0 if value < 142 else value if value < 858 else PER_MILLE_MAX


def declared(register, value):
    """The two `io_seed` bytes of one palette register."""
    return {register: value >> 8, register + 1: value & 0xFF}


def machine(planes=LOW, onto=None):
    """The physical workstation, dispatched, with LINEA_PLANES = `planes` (the snapshot's is 4)."""
    return vdi.merge_pokes(vdi.dispatched_pokes(onto=onto), vdi.linea_pokes(PLANES=planes))


def set_pokes(index, guns, planes=LOW, onto=None):
    return vdi.call_pokes(addrs.VDI_ROM_VS_COLOR_OPCODE, intin=(index, *guns),
                          workstation_pokes=machine(planes, onto))


def get_pokes(index, realized, planes=LOW, onto=None):
    return vdi.call_pokes(addrs.VDI_ROM_VQ_COLOR_OPCODE, intin=(index, realized),
                          workstation_pokes=machine(planes, onto))


def run(name, pokes, **seeds):
    return vdi.run_function(name, pokes, **seeds)


def hw_writes(result):
    return result.info["regs"]["hw_writes"]


# Sixteen DISTINCT requests, one per colour, each gun a different per-mille, so a row written to the
# wrong place or a gun to the wrong slot reads wrong. Every value is in 0..1000.
def request(index):
    return tuple((index * 61 + gun * 337) % (PER_MILLE_MAX + 1) for gun in range(GUNS))


# A REQ_COL table no two rows of which agree (the snapshot's repeats 0 and 1000 across colours).
STAGED_REQUESTS = [word for index in range(vdi.VDI_MAP_COL_ENTRIES) for word in request(index)]


# ==== vs_color =======================================================================================

@pytest.mark.parametrize("index", range(vdi.VDI_MAP_COL_ENTRIES))
def test_each_colour_is_stored_as_requested_and_written_to_its_mapped_register(index):
    guns = request(index)
    result = run(SET, set_pokes(index, guns))
    assert result.words(requested_row(index), GUNS) == list(guns)
    assert hw_writes(result) == [(register_of(index, LOW), 2, shifter_word(guns))]


# Per-mille values at every edge the ROM's arithmetic has: the SIGNED clamps (-1, $8000, 1001, $7fff),
# and each side of each rounding step `(v + 72) / 143` — 70/71 is level 0/1, 928/929 is 6/7.
PER_MILLE_EDGES = ((0, 70, 71), (213, 214, 356), (357, 928, 929), (1000, 1001, 0x7FFF),
                   (0xFFFF, 0x8000, 500), (142, 285, 857))


@pytest.mark.parametrize("guns", PER_MILLE_EDGES)
def test_each_gun_is_clamped_and_rounded_to_three_bits_but_stored_as_given(guns):
    result = run(SET, set_pokes(5, guns))
    assert result.words(requested_row(5), GUNS) == list(guns), "REQ_COL keeps the request UNCLAMPED"
    assert hw_writes(result) == [(register_of(5, LOW), 2, shifter_word(guns))]


# Indexes the bound refuses — its LOW BYTE is over 15 — which change nothing at all.
REFUSED_LOW_RES = (16, 0xFF, 0x0110, 0x7FFF, 0xFFFF)


@pytest.mark.parametrize("index", REFUSED_LOW_RES)
def test_an_index_over_the_bound_writes_nothing(index):
    result = run(SET, set_pokes(index, request(3)))
    assert hw_writes(result) == []
    assert not any(vdi.LINEA_REQ_COL <= at < vdi.LINEA_SIZ_TAB for at in result.info["writes"])


# ...and the ones it LETS THROUGH because it compares a byte: $8000 is colour 0 throughout (its row
# wraps to 0 in the word product), and $ff01 is colour 1 to the bound but then reads a pen out of the
# ROM below MAP_COL (7) and stores its request 0x5fa bytes below LINEA_REQ_COL. $ff00 reads the pen
# $8003 there, whose HIGH byte `and.b` leaves alone and the doubling then wraps out of the word — so
# it is register 3, as $8003 masked whole would be: no decoded register tells the two apart.
ALIASED = ((0x8000, 0), (0xFF01, None), (0xFF00, None))


@pytest.mark.parametrize("index,alias", ALIASED)
def test_the_bound_is_a_byte_compare_and_the_word_indexes_on(index, alias):
    guns = request(9)
    result = run(SET, set_pokes(index, guns))
    if alias is not None:
        assert (requested_row(index), register_of(index, LOW)) == (requested_row(alias), register_of(alias, LOW))
    assert result.words(requested_row(index), GUNS) == list(guns)
    assert hw_writes(result) == [(register_of(index, LOW), 2, shifter_word(guns))]


@pytest.mark.parametrize("index", range(4))
def test_medium_resolution_masks_the_pen_to_two_planes(index):
    """MAP_COL[1] is pen 15, which two planes show as register 3."""
    guns = request(index)
    result = run(SET, set_pokes(index, guns, planes=MEDIUM))
    assert hw_writes(result) == [(register_of(index, MEDIUM), 2, shifter_word(guns))]
    assert result.words(requested_row(index), GUNS) == list(guns)


@pytest.mark.parametrize("index", (4, 15))
def test_medium_resolution_refuses_what_low_resolution_takes(index):
    assert hw_writes(run(SET, set_pokes(index, request(index), planes=MEDIUM))) == []


def test_a_plane_count_of_zero_reads_the_byte_before_the_table():
    """VDI_PEN_MASKS is indexed by the plane count ITSELF, so 0 reads the `rts` in front of the table
    ($75) — and 0 is not 1, so it is the colour arm, not the monochrome one."""
    assert pen_mask(0) == 0x75
    result = run(SET, set_pokes(5, request(5), planes=0))
    assert hw_writes(result) == [(register_of(5, 0), 2, shifter_word(request(5)))]


def test_a_plane_count_whose_mask_is_zero_takes_colour_0_only():
    """VDI_PEN_MASKS[3] is 0 — no ST has three planes, and the table answers anyway."""
    assert pen_mask(THREE_PLANES) == 0
    assert hw_writes(run(SET, set_pokes(1, request(1), planes=THREE_PLANES))) == []
    result = run(SET, set_pokes(0, request(2), planes=THREE_PLANES))
    assert hw_writes(result) == [(addrs.SHIFTER_PALETTE, 2, shifter_word(request(2)))]


# The monochrome arm: each gun black (< 142, negatives included), kept, or white (>= 858). Only an
# all-black request writes register 0 — with the INDEX — and only an all-white one, with its complement.
MONO_REQUESTS = (
    ((0, 0, 0), "black"), ((141, 0xFFFF, 100), "black"), ((0x8000, 5, 141), "black"),
    ((1000, 1000, 1000), "white"), ((858, 999, 0x7FFF), "white"),
    ((142, 0, 0), None), ((857, 1000, 1000), None), ((0, 1000, 0), None), ((500, 500, 500), None),
)


@pytest.mark.parametrize("index", (0, 1))
@pytest.mark.parametrize("guns,shade", MONO_REQUESTS)
def test_monochrome_writes_register_0_only_for_black_or_white(index, guns, shade):
    assert (shade == "black") == (sum(map(mono_level, guns)) == 0)
    result = run(SET, set_pokes(index, guns, planes=MONO))
    expected = {"black": index, "white": ~index & 0xFFFF, None: None}[shade]
    assert hw_writes(result) == ([] if expected is None else [(addrs.SHIFTER_PALETTE, 2, expected)])
    assert result.words(requested_row(index), GUNS) == list(guns)


@pytest.mark.parametrize("index", (2, 0x0110))
def test_monochrome_refuses_an_index_past_1(index):
    assert hw_writes(run(SET, set_pokes(index, (0, 0, 0), planes=MONO))) == []


def test_monochrome_writes_the_unmapped_index_itself():
    """$8000 passes the byte bound as 0 and is written to register 0 AS $8000 — the mono arm never
    maps the index through MAP_COL, and complements the whole word for white."""
    assert hw_writes(run(SET, set_pokes(0x8000, (0, 0, 0), planes=MONO))) == [(addrs.SHIFTER_PALETTE, 2, 0x8000)]
    assert hw_writes(run(SET, set_pokes(0x8000, (1000,) * GUNS, planes=MONO))) == [(addrs.SHIFTER_PALETTE, 2, 0x7FFF)]


@pytest.mark.parametrize("planes", (LOW, MONO))
def test_each_gun_is_read_after_the_one_before_it_is_stored(planes):
    """THE ORDER, which only an overlap can show: intin laid over REQ_COL so that intin[2] IS the row's
    first word. The ROM stores red there before it reads green, so green is the red just stored; a
    reconstruction that read all three guns first would store the staged word instead. Colour 1, the
    highest one monochrome takes."""
    index = 1
    row = vdi.LINEA_REQ_COL + index * ROW_BYTES
    intin_at = row - 2 * WORD                           # intin[2] = row[0], intin[3] = row[1]
    staged = list(STAGED_REQUESTS)
    staged[index * GUNS - 2:index * GUNS] = [index, 111]   # intin[0] = the index, intin[1] = red
    onto = vdi.linea_pokes(REQ_COL=staged)
    pokes = vdi.merge_pokes(set_pokes(index, (), planes=planes, onto=onto), vdi.linea_pokes(INTIN=intin_at))
    result = run(SET, pokes)
    assert result.words(row, GUNS) == [111, 111, 111]


# ==== vq_color =======================================================================================

@pytest.mark.parametrize("index", range(vdi.VDI_MAP_COL_ENTRIES))
def test_the_requested_colour_is_the_req_col_row(index):
    result = run(GET, get_pokes(index, REQUESTED, onto=vdi.linea_pokes(REQ_COL=STAGED_REQUESTS)))
    assert result.intout(1 + GUNS) == [index, *request(index)]
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 1 + GUNS


def test_the_requested_colour_is_the_row_as_stored_unclamped():
    """REQ_COL holds what vs_color was GIVEN, and vq_color does not clamp it on the way out."""
    staged = list(STAGED_REQUESTS)
    staged[2 * GUNS:3 * GUNS] = [0xFFFF, 0x7FFF, 1001]
    result = run(GET, get_pokes(2, REQUESTED, onto=vdi.linea_pokes(REQ_COL=staged)))
    assert result.intout(1 + GUNS) == [2, 0xFFFF, 0x7FFF, 1001]


@pytest.mark.parametrize("realized", (REQUESTED, REALIZED))
@pytest.mark.parametrize("index", REFUSED_LOW_RES)
def test_an_index_over_the_bound_answers_minus_one_and_nothing_else(index, realized):
    result = run(GET, get_pokes(index, realized))
    assert result.intout(1 + GUNS) == [INVALID] + [vdi.FILL * 0x101] * GUNS
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 1 + GUNS, "the count is written first, whatever follows"


def realized_word(index):
    """A register value per colour: three distinct levels, and bit 3 of every gun SET — the STE's
    fourth bit, which the ROM's `and.w #14` after each rotate never sees."""
    return 0x0888 | (index % 8) << 8 | (index * 3 % 8) << 4 | (7 - index % 8)


def levels_of(word):
    table = [vdi.rom_word(vdi.VDI_VQ_COLOR_LEVELS + WORD * level) for level in range(8)]
    return [table[word >> shift & 7] for shift in (8, 4, 0)]


@pytest.mark.parametrize("index", range(vdi.VDI_MAP_COL_ENTRIES))
def test_the_realized_colour_is_read_from_the_mapped_register(index):
    register = register_of(index, LOW)
    value = realized_word(index)
    result = run(GET, get_pokes(index, REALIZED), io_seed=declared(register, value))
    assert result.intout(1 + GUNS) == [index, *levels_of(value)]
    assert result.info["regs"]["io_events"] == [(register, 2, value)]


def test_the_level_table_is_the_rounded_eighths_of_1000():
    assert levels_of(0x0777) == [PER_MILLE_MAX] * GUNS
    assert [vdi.rom_word(vdi.VDI_VQ_COLOR_LEVELS + WORD * level) for level in range(8)] == \
        [0, 142, 285, 428, 571, 714, 857, 1000]


@pytest.mark.parametrize("flag", (1, 0x0100, 0x8000, 0xFFFF))
def test_any_nonzero_flag_word_asks_for_the_realized_colour(flag):
    """`tst.w`: a flag whose only bit is in the high byte is still 'realized'."""
    register = register_of(6, LOW)
    result = run(GET, get_pokes(6, flag), io_seed=declared(register, 0x0123))
    assert result.intout(1 + GUNS) == [6, *levels_of(0x0123)]


@pytest.mark.parametrize("index", range(4))
def test_medium_resolution_reads_the_two_plane_register(index):
    register = register_of(index, MEDIUM)
    result = run(GET, get_pokes(index, REALIZED, planes=MEDIUM), io_seed=declared(register, realized_word(index)))
    assert result.intout(1 + GUNS) == [index, *levels_of(realized_word(index))]


# Monochrome answers all-white or all-black from bit 0 of (index ^ register 0): the shifter's invert.
@pytest.mark.parametrize("index", (0, 1))
@pytest.mark.parametrize("register_0", (0x0000, 0x0001, 0x0FFE, 0xFFFF))
def test_monochrome_realized_is_bit_0_of_the_index_against_register_0(index, register_0):
    result = run(GET, get_pokes(index, REALIZED, planes=MONO), io_seed=declared(addrs.SHIFTER_PALETTE, register_0))
    level = PER_MILLE_MAX if (index ^ register_0) & 1 else 0
    assert result.intout(1 + GUNS) == [index, level, level, level]


@pytest.mark.parametrize("realized", (REQUESTED, REALIZED))
@pytest.mark.parametrize("index,alias", ALIASED)
def test_vq_color_passes_the_same_byte_bound_and_answers_the_index_whole(index, alias, realized):
    register = register_of(index, LOW)
    seeds = {"io_seed": declared(register, 0x0531)} if realized else {}
    result = run(GET, get_pokes(index, realized), **seeds)
    expected = levels_of(0x0531) if realized else list(vdi.rom_word(requested_row(index) + WORD * gun)
                                                         for gun in range(GUNS))
    assert result.intout(1 + GUNS) == [index, *expected]


def test_the_requested_row_is_read_and_answered_a_word_at_a_time():
    """THE ORDER, over intout laid on colour 9's REQ_COL row: the index lands on row[0], and each
    `move.w (a1)+,(a0)+` then reads the word the one before it just wrote — so the row reads the index
    four times. Reading the three words first would answer the staged row instead."""
    index = 9
    row = vdi.LINEA_REQ_COL + index * ROW_BYTES
    onto = vdi.linea_pokes(REQ_COL=STAGED_REQUESTS)
    pokes = vdi.merge_pokes(get_pokes(index, REQUESTED, onto=onto), vdi.linea_pokes(INTOUT=row))
    assert run(GET, pokes).words(row, 1 + GUNS) == [index] * (1 + GUNS)


def test_contrl_is_written_before_intin_is_read():
    """THE ORDER: intin laid over contrl[4]. The ROM stores the count (4) and THEN reads the index —
    so the index it answers is 4, whatever the staged word was."""
    pokes = vdi.merge_pokes(get_pokes(9, REQUESTED, onto=vdi.linea_pokes(REQ_COL=STAGED_REQUESTS)),
                            vdi.linea_pokes(INTIN=vdi.CONTRL_AT + vdi.CONTRL_N_INTOUT))
    result = run(GET, pokes)
    assert result.intout(1 + GUNS) == [1 + GUNS, *request(1 + GUNS)]


# ==== the 24-bit bus: indexes the byte bound lets by, whose addresses leave both tables =============
# Every address here is an address register's, a base plus a sign-extended word, put on the bus by 24
# pins. The pen of a whole-word index can double to an offset past $7dc0, which carries a palette
# store past $ffffff into LOW RAM — the exception vectors at $40.. — and a REQ_COL row of index $1600
# or more lies below address 0, which is the I/O page.
def low_res_indexes():
    return (index for index in range(0x10000) if index & 0xFF <= pen_mask(LOW))


FOLDED_INTO_RAM = [index for index in low_res_indexes() if not in_io_page(register_of(index, LOW))]
ROW_BELOW_ZERO = [index for index in low_res_indexes() if in_io_page(requested_row(index))]
# ...and the ones vs_color can be run on: a row below 0 is in the page's UNDECODED gap (no row reaches
# the MFP or the ACIA), where the ROM's store bus-errors on iron and the oracle drops it — a write
# neither shore can compare, so the store is exercised by vq_color's READ of the same row instead.
STORED_INTO_RAM = [index for index in FOLDED_INTO_RAM if index not in ROW_BELOW_ZERO]
# os.h's OS_HW_IO_INTERNAL/MFP/ACIA bounds: the three blocks of the page a device answers in.
DECODED_BLOCKS = ((0xFF8000, 0xFF8FFF), (0xFFFA00, 0xFFFAFF), (0xFFFC00, 0xFFFCFF))
VECTORS_REACHED = range(0x40, 0x60, WORD)   # exception vectors 16..23, where the folded stores land


def test_the_folds_are_the_ones_the_review_found():
    assert len(FOLDED_INTO_RAM) == 30 and {0x2F00, 0x3400, 0x1603, 0x3907} <= set(FOLDED_INTO_RAM)
    assert {register_of(index, LOW) for index in FOLDED_INTO_RAM} <= set(VECTORS_REACHED)
    assert ROW_BELOW_ZERO[0] == 0x1600
    row_words = [requested_row(index) + gun * WORD for index in ROW_BELOW_ZERO for gun in range(GUNS)]
    assert not any(first <= word <= last for word in row_words for first, last in DECODED_BLOCKS)


@pytest.mark.parametrize("index", STORED_INTO_RAM, ids=hex)
def test_a_palette_store_past_the_top_of_the_bus_lands_in_low_ram(index):
    guns = request(index & 0xF)
    result = run(SET, set_pokes(index, guns))
    assert hw_writes(result) == []
    assert result.word(register_of(index, LOW)) == shifter_word(guns)
    assert result.words(requested_row(index), GUNS) == list(guns)


@pytest.mark.parametrize("index", FOLDED_INTO_RAM, ids=hex)
def test_a_realized_colour_past_the_top_of_the_bus_is_read_from_low_ram(index):
    register = register_of(index, LOW)
    result = run(GET, get_pokes(index, REALIZED, onto={register: vdi.pack_words(realized_word(index))}))
    assert result.intout(1 + GUNS) == [index, *levels_of(realized_word(index))]
    assert result.info["regs"]["io_events"] == []


@pytest.mark.parametrize("index", (0x1600, 0x1603, ROW_BELOW_ZERO[-1]), ids=hex)
def test_a_requested_row_below_address_0_is_read_from_the_io_page(index):
    row = requested_row(index)
    words = request(index & 0xF)
    seeds = {}
    for gun, word in enumerate(words):
        seeds.update(declared(row + gun * WORD, word))
    result = run(GET, get_pokes(index, REQUESTED), io_seed=seeds)
    assert result.intout(1 + GUNS) == [index, *words]
    assert [at for at, _width, _value in result.info["regs"]["io_events"]] == [row + gun * WORD for gun in range(GUNS)]


# ==== the pair, in sequence ==========================================================================

@pytest.mark.parametrize("planes,index", ((LOW, 7), (MEDIUM, 2), (MONO, 1)))
def test_a_colour_set_reads_back_requested_and_realized(planes, index):
    """vs_color, then vq_color over the machine it ENDED in (`case.continued`) — both arms. The
    realized arm is declared the register the first run wrote, which is what the shifter latches."""
    guns = (1000, 1000, 1000) if planes == MONO else request(index)
    written = run(SET, set_pokes(index, guns, planes=planes))
    [(register, _width, value)] = hw_writes(written)
    after = vdi.merge_pokes(case.continued(written), get_pokes(index, REQUESTED, planes=planes))
    assert run(GET, after).intout(1 + GUNS) == [index, *guns]
    after = vdi.merge_pokes(case.continued(written), get_pokes(index, REALIZED, planes=planes))
    realized = run(GET, after, io_seed=declared(register, value)).intout(1 + GUNS)
    if planes == MONO:
        level = PER_MILLE_MAX if (index ^ value) & 1 else 0
        assert realized == [index, level, level, level]
    else:
        assert realized == [index, *levels_of(value)]


# ==== the TRANSCRIPTION: `src/vdi/palette.S`, the ROM's own instructions ============================
# The C above measures over the 1.10 bar against hand 68000 (see `bench/tier3.py`), so the target build
# ships the ROM's pair as `palette.S`. Two claims hold it: its WORDS are the ROM's, and it BEHAVES as
# the ROM over every arm above — image, whole register file, palette traffic — through Tier 3's
# transcription relation (`transcription.run_transcription`).
BLOCK_BYTES = 0x160                           # $fd2dd2..$fd2f31: both routines and both tables
REGION = transcription.pinned_region(addrs.VDI_ROM_VS_COLOR, addrs.VDI_ROM_VS_COLOR + BLOCK_BYTES, SET, (GET,))


def test_the_transcription_is_the_rom_s_bytes_exactly():
    """THE BYTE PIN: no word excused — the six `<op>.w #imm,Dn` GNU as would encode as CMPI/ADDI/ANDI are
    spelt as the ROM's words (`m68k_encodings.h`)."""
    transcription.assert_transcribed(REGION)


TRANSCRIBED = (
    (SET, "every gun at an edge", set_pokes(5, (70, 71, 0x8000)), None),
    (SET, "clamped high", set_pokes(12, (1001, 0x7FFF, 1000)), None),
    (SET, "refused", set_pokes(0x7FFF, request(3)), None),
    (SET, "aliased $ff01", set_pokes(0xFF01, request(9)), None),
    (SET, "medium", set_pokes(1, request(1), planes=MEDIUM), None),
    (SET, "three planes", set_pokes(0, request(2), planes=THREE_PLANES), None),
    (SET, "mono black", set_pokes(1, (141, 0xFFFF, 0), planes=MONO), None),
    (SET, "mono white", set_pokes(0, (858, 1000, 0x7FFF), planes=MONO), None),
    (SET, "mono grey", set_pokes(1, (142, 0, 0), planes=MONO), None),
    (GET, "requested", get_pokes(9, REQUESTED, onto=vdi.linea_pokes(REQ_COL=STAGED_REQUESTS)), None),
    (GET, "refused", get_pokes(16, REALIZED), None),
    (GET, "realized", get_pokes(13, REALIZED), declared(register_of(13, LOW), realized_word(13))),
    (GET, "realized medium", get_pokes(3, 0x0100, planes=MEDIUM), declared(register_of(3, MEDIUM), 0x0FFF)),
    (GET, "realized mono", get_pokes(1, REALIZED, planes=MONO), declared(addrs.SHIFTER_PALETTE, 0x0FFE)),
    (GET, "realized mono inverted", get_pokes(0, REALIZED, planes=MONO), declared(addrs.SHIFTER_PALETTE, 1)),
    (SET, "folded into low RAM", set_pokes(0x2F00, request(9)), None),
    (GET, "realized from low RAM", get_pokes(0x3907, REALIZED), None),
    (GET, "requested below address 0", get_pokes(0x1603, REQUESTED),
     {at: 0x5A for at in range(requested_row(0x1603), requested_row(0x1603) + ROW_BYTES)}),
)


@pytest.mark.parametrize("name,label,pokes,io_seed", TRANSCRIBED, ids=[f"{n[8:]}, {l}" for n, l, _p, _i in TRANSCRIBED])
def test_the_transcription_behaves_as_the_rom_over_every_arm(name, label, pokes, io_seed):
    del label
    transcription.run_transcription(name, pokes, io_seed=io_seed)


# ==== Tier 3: the worst realistic rows ===============================================================
vdi.register("vdi_vs_color, low res", addrs.VDI_ROM_VS_COLOR, set_pokes(7, (929, 356, 71)))
vdi.register("vdi_vs_color, mono white", addrs.VDI_ROM_VS_COLOR, set_pokes(1, (1000, 1000, 1000), planes=MONO))
vdi.register("vdi_vs_color, index refused", addrs.VDI_ROM_VS_COLOR, set_pokes(16, (0, 0, 0)))
vdi.register("vdi_vq_color, realized", addrs.VDI_ROM_VQ_COLOR, get_pokes(7, REALIZED),
             io_seed=declared(register_of(7, LOW), realized_word(7)))
vdi.register("vdi_vq_color, requested", addrs.VDI_ROM_VQ_COLOR, get_pokes(7, REQUESTED))
vdi.register("vdi_vq_color, mono realized", addrs.VDI_ROM_VQ_COLOR, get_pokes(1, REALIZED, planes=MONO),
             io_seed=declared(addrs.SHIFTER_PALETTE, 1))
vdi.register("vdi_vq_color, index refused", addrs.VDI_ROM_VQ_COLOR, get_pokes(16, REALIZED))
# ...and the same rows for the `.S` the target build ships.
transcription.register_transcription(SET, "low res", set_pokes(7, (929, 356, 71)))
transcription.register_transcription(SET, "mono white", set_pokes(1, (1000, 1000, 1000), planes=MONO))
transcription.register_transcription(SET, "index refused", set_pokes(16, (0, 0, 0)))
transcription.register_transcription(GET, "realized", get_pokes(7, REALIZED),
                                     io_seed=declared(register_of(7, LOW), realized_word(7)))
transcription.register_transcription(GET, "requested", get_pokes(7, REQUESTED))
transcription.register_transcription(GET, "mono realized", get_pokes(1, REALIZED, planes=MONO),
                                     io_seed=declared(addrs.SHIFTER_PALETTE, 1))
transcription.register_transcription(GET, "index refused", get_pokes(16, REALIZED))

# The REQ_COL rows $ff01 and $ff00 alias onto, below the table, which the aliasing cases read and write.
for _index in (0xFF01, 0xFF00):
    vdi.declare_case_field(requested_row(_index), ROW_BYTES, f"the REQ_COL row vs_color/vq_color index {_index:#x} reaches")
# ...and the low RAM the folded indexes reach: the palette word, and the row a stored one writes.
for _index in FOLDED_INTO_RAM:
    vdi.declare_case_field(register_of(_index, LOW), WORD, f"the low-RAM word palette index {_index:#x} folds onto")
for _index in STORED_INTO_RAM:
    vdi.declare_case_field(requested_row(_index), ROW_BYTES, f"the REQ_COL row vs_color index {_index:#x} reaches")
