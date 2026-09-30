"""AES resource addressing — rs_obfix's cell fix-up and rsrc_gaddr's switch: `src/aes/resource.c`.

    fix_chpos(p, is_x):  w = *p; cells = w & $ff; off = w >> 8, less 256 above 128;
                         *p = (is_x && cells == 80 ? gl_width : cells * (is_x ? gl_wchar : gl_hchar)) + off
    rs_obfix(tree, obj): fix_chpos over ob_x, ob_y, ob_width, ob_height (x-like, y-like alternately); D0 = 1
    get_sub(i, s, n):    rs_hdr + (unsigned) header word s + i * n (muls.w)
    get_addr(type, i):   rsrc_gaddr's switch over 17 types, -1 past them (an unsigned word)
    fix_long(p):         *p += rs_hdr unless *p == -1; fix_ptr = fix_long(get_addr); fix_nptrs over i = n..0
    rs_sglobal(g):       rs_global = g; rs_hdr = g[7..8]
    rs_gaddr(g, t, i, &a) / rs_saddr(g, t, i, v)

Seeded with the snapshot's own resources — the AES's (its global[] AES_RS_SYSTEM_GLOBAL names) and the desk's — as
the captured machine holds them relocated, and with an application's resource built by shape where neither reaches an
arm (neither has an ICONBLK). Every routine is entered DIRECTLY (the row Tier 3 prices) and THROUGH LINE-F.
"""
import pytest

from harness import BASE_IMAGE, emu, make_image

from recreate_kit.os_map import OS_BUS_ADDR_MASK

import aes
import aes_resource as rs
import case
import routines
import vdi_helpers
from case import merge_pokes

GEM, DESK = rs.GEM_GLOBAL, rs.DESK_GLOBAL
GEM_COUNTS = rs.header_words(rs.GEM_HEADER)
DESK_COUNTS = rs.header_words(rs.DESK_HEADER)
COORDINATE_AT = aes.RECTS_AT
ANSWER_AT = aes.RECTS_AT + 0x10

# ---- fix_chpos ------------------------------------------------------------------------------------------------------
GL_WIDTH, GL_WCHAR, GL_HCHAR = (case.word_in(BASE_IMAGE, at) for at in (aes.AES_GL_WIDTH, aes.AES_GL_WCHAR,
                                                                          aes.AES_GL_HCHAR))
for _at in (aes.AES_GL_WIDTH, aes.AES_GL_WCHAR, aes.AES_GL_HCHAR):
    aes.declare_case_field(_at, aes.WORD_BYTES, "the screen metrics rs_obfix's cases stage")
FULL_WIDTH = 80


def cells_word(cells, offset):
    return (offset << 8) | cells


def model_chpos(word, is_x, width=GL_WIDTH, wchar=GL_WCHAR, hchar=GL_HCHAR):
    cells, offset = word & 0xFF, word >> 8
    if is_x and cells == FULL_WIDTH:
        pixels = width
    else:
        pixels = cells * (wchar if is_x else hchar)
    if offset > 128:
        offset -= 256
    return (pixels + offset) & 0xFFFF


def fix_chpos(word, is_x, pokes=None, at=COORDINATE_AT, **kwargs):
    return rs.run(rs.FIX_CHPOS, (at, is_x), merge_pokes({COORDINATE_AT: word.to_bytes(2, "big")}, pokes), **kwargs)


# Every arm's edge: the cells either side of 80 and at the byte's ends; the offset at 0, 127, 128 (still positive),
# 129 (the first negative) and 255 (-1).
CELLS = (0, 1, 79, FULL_WIDTH, 81, 255)
OFFSETS = (0, 1, 127, 128, 129, 255)


@pytest.mark.parametrize("is_x", (1, 0), ids=("x-like", "y-like"))
@pytest.mark.parametrize("offset", OFFSETS)
@pytest.mark.parametrize("cells", CELLS)
def test_a_coordinate_is_cells_times_the_cell_plus_a_signed_offset(cells, offset, is_x):
    word = cells_word(cells, offset)
    assert fix_chpos(word, is_x).word(COORDINATE_AT) == model_chpos(word, is_x)


def test_any_nonzero_flag_is_x_like():
    """`tst.w` of the flag: 2 is x-like, full width included."""
    word = cells_word(FULL_WIDTH, 3)
    assert fix_chpos(word, 2).word(COORDINATE_AT) == model_chpos(word, 1)


@pytest.mark.parametrize("wchar,hchar", ((0x8000, 0xFFF8), (0x0400, 0x0101)), ids=("negative cells", "wrapping"))
def test_the_product_is_the_low_word_of_a_signed_multiply(wchar, hchar):
    """Cell sizes no screen has, which `muls.w` takes as signed and whose product's high word is dropped."""
    metrics = aes.field_pokes("AES", GL_WCHAR=wchar, GL_HCHAR=hchar)
    for is_x in (1, 0):
        word = cells_word(255, 200)
        assert fix_chpos(word, is_x, metrics).word(COORDINATE_AT) == model_chpos(word, is_x, wchar=wchar, hchar=hchar)


def test_a_full_width_is_the_screen_s_width_whatever_the_cell():
    metrics = aes.field_pokes("AES", GL_WIDTH=640, GL_WCHAR=3)
    assert fix_chpos(cells_word(FULL_WIDTH, 255), 1, metrics).word(COORDINATE_AT) == 639


def test_the_coordinate_pointer_is_put_on_the_24_bit_bus():
    word = cells_word(12, 130)
    assert fix_chpos(word, 0, at=COORDINATE_AT | aes.BUS_TAG).word(COORDINATE_AT) == model_chpos(word, 0)


def test_a_coordinate_through_line_f():
    word = cells_word(7, 1)
    assert fix_chpos(word, 1, through_line_f=True).word(COORDINATE_AT) == model_chpos(word, 1)


# ---- rs_obfix -------------------------------------------------------------------------------------------------------
def fresh_object_pokes(index, at=aes.TREE_AT, count=1):
    """`count` objects of the desk's resource from `index` on, as the ROM holds them — in cells — at `at`."""
    source = rs.DESK_FRESH_AT + DESK_COUNTS["object"] + index * aes.OB_BYTES
    return {at: rs.rom_bytes(source, count * aes.OB_BYTES)}


def coordinates(image, tree, index):
    return [case.word_in(image, tree + index * aes.OB_BYTES + aes.OB_X + 2 * i) for i in range(4)]


def model_obfix(image, tree, index):
    return [model_chpos(word, i % 2 == 0) for i, word in enumerate(coordinates(image, tree, index))]


def obfix(tree, index, pokes, **kwargs):
    return rs.run(rs.RS_OBFIX, (tree, index), pokes, **kwargs)


# The desk's objects as the file has them: its first tree's root (a full-width 80), and objects deeper in, whose
# coordinates carry pixel offsets in their high bytes.
@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("index", (0, 1, 5, 40, 171))
def test_an_object_of_the_desk_s_resource_as_the_rom_holds_it(index, through_line_f):
    pokes = fresh_object_pokes(index)
    result = obfix(aes.TREE_AT, 0, pokes, through_line_f=through_line_f)
    assert coordinates(result.final, aes.TREE_AT, 0) == model_obfix(make_image(pokes), aes.TREE_AT, 0)
    assert result.answer() == 1, "the toggle's last `moveq #1`: intout[0]"


def test_the_object_index_is_signed_and_scaled_by_the_record():
    """Object -1 of a tree one record up is the record below it (`muls.w #24`, then `add.l`); object 2 of the tree
    is two records on."""
    pokes = fresh_object_pokes(3, count=3)
    image = make_image(pokes)
    result = obfix(aes.TREE_AT + aes.OB_BYTES, -1, pokes)
    assert coordinates(result.final, aes.TREE_AT, 0) == model_obfix(image, aes.TREE_AT, 0)
    assert coordinates(obfix(aes.TREE_AT, 2, pokes).final, aes.TREE_AT, 2) == model_obfix(image, aes.TREE_AT, 2)


def test_the_tree_pointer_is_put_on_the_24_bit_bus():
    pokes = fresh_object_pokes(0)
    result = obfix(aes.TREE_AT | aes.BUS_TAG, 0, pokes)
    assert coordinates(result.final, aes.TREE_AT, 0) == model_obfix(make_image(pokes), aes.TREE_AT, 0)


def test_each_coordinate_is_stored_before_the_next_is_fixed():
    """The ORDER, which only an overlap shows: an object laid so that its ob_x IS gl_wchar. x is fixed first — cells
    times the cell, the cell being x itself — and stored; the WIDTH, fixed third, is then multiplied by the stored x."""
    tree = aes.AES_GL_WCHAR - aes.OB_X
    x_word = cells_word(3, 0)
    pokes = aes.field_pokes("AES", GL_WCHAR=x_word)
    result = obfix(tree, 0, pokes)
    fixed_x = model_chpos(x_word, 1, wchar=x_word)
    assert result.word(aes.AES_GL_WCHAR) == fixed_x
    width_word = case.word_in(BASE_IMAGE, aes.AES_GL_WCHAR + 4)
    assert result.word(aes.AES_GL_WCHAR + 4) == model_chpos(width_word, 1, wchar=fixed_x)


# ---- get_sub and get_addr -------------------------------------------------------------------------------------------
def get_sub(index, section, size, pokes=None, **kwargs):
    return rs.run(rs.GET_SUB, (index, section, size), merge_pokes(rs.current(GEM), pokes), **kwargs)


@pytest.mark.parametrize("section", range(1, 10))
def test_an_element_of_every_section_of_the_aes_s_resource(section):
    size = 12
    result = get_sub(3, section, size)
    offset = case.word_in(BASE_IMAGE, rs.GEM_HEADER + 2 * section)
    assert result.long_answer() == rs.GEM_HEADER + offset + 3 * size


@pytest.mark.parametrize("index,size", ((-2, 24), (5, -4), (-300, -300), (0x7FFF, 0x7FFF)),
                         ids=("negative index", "negative size", "both negative", "the largest product"))
def test_the_element_is_a_signed_word_product(index, size):
    result = get_sub(index, 1, size)
    offset = case.word_in(BASE_IMAGE, rs.GEM_HEADER + 2)
    assert result.long_answer() == (rs.GEM_HEADER + offset + index * size) & 0xFFFFFFFF


def test_the_section_offset_is_unsigned_and_the_section_index_signed():
    """A header staged by shape: section 1's offset word $9000 is added as 36,864, not subtracted; section -1 reads
    the word BELOW the header (`movea.w`, `adda.w`)."""
    header = aes.BLOCKS_AT + 0x10
    pokes = merge_pokes(rs.current(GEM, header), {header - 2: b"\x01\x02", header: b"\x00\x00\x90\x00"})
    assert get_sub(1, 1, 4, pokes).long_answer() == header + 0x9000 + 4
    assert get_sub(0, -1, 4, pokes).long_answer() == header + 0x0102


def test_a_tagged_header_keeps_its_top_byte_in_the_answer():
    """rs_hdr with a top byte: the offset word is read through 24 bits, and the answer — `add.l` of the header — keeps
    the tag, as the register does."""
    pokes = rs.current(GEM, rs.GEM_HEADER | aes.BUS_TAG)
    result = get_sub(1, 1, aes.OB_BYTES, pokes)
    offset = case.word_in(BASE_IMAGE, rs.GEM_HEADER + 2)
    assert result.long_answer() == (rs.GEM_HEADER | aes.BUS_TAG) + offset + aes.OB_BYTES


def get_addr(aes_type, index, pokes=None, *, global_=GEM, **kwargs):
    return rs.run(rs.GET_ADDR, (aes_type, index), merge_pokes(rs.current(global_), pokes), **kwargs)


def assert_modelled(result, aes_type, index):
    assert result.long_answer() == rs.model_get_addr(result.final, aes_type, index)
    return result.long_answer()


ALL_TYPES = range(rs.R_LAST_TYPE + 1)


@pytest.mark.parametrize("aes_type", ALL_TYPES)
def test_every_type_over_the_aes_s_resource(aes_type):
    """Element 1 of every type: the file selector's second object, the second TEDINFO, the second free string ..."""
    assert_modelled(get_addr(aes_type, 1), aes_type, 1)


@pytest.mark.parametrize("aes_type", ALL_TYPES)
def test_every_type_over_the_desk_s_resource(aes_type):
    """The desk's last tree, its last object, its last TEDINFO and string: every element index the file counts."""
    last = {rs.R_TREE: DESK_COUNTS["ntree"] - 1, rs.R_OBJECT: DESK_COUNTS["nobs"] - 1, rs.R_OBSPEC: DESK_COUNTS["nobs"] - 1,
            rs.R_STRING: DESK_COUNTS["nstring"] - 1, rs.R_FRSTR: DESK_COUNTS["nstring"] - 1}.get(aes_type, 0)
    assert_modelled(get_addr(aes_type, last, global_=DESK), aes_type, last)


def test_a_tree_is_read_through_the_tree_table_and_the_index_stored():
    """R_TREE reads global[5..6]'s table, and leaves the byte offset in AES_RS_INDEX (`lsl.w #2`)."""
    result = get_addr(rs.R_TREE, 2)
    assert result.long_answer() == aes.resource_tree(2)
    assert result.word(aes.AES_RS_INDEX) == 8


def test_a_tree_s_byte_offset_is_a_signed_word():
    """Tree $3fff: its byte offset $fffc is read back with `movea.w`, -4 — the longword BELOW the table (staged in a
    global[] whose tree table is a staged one). Unsigned, it would read 64 KB above it."""
    table = aes.BLOCKS_AT + 0x20
    marker = 0x00E0_1234
    pokes = merge_pokes(rs.application_global(), {rs.APP_GLOBAL + aes.AES_GLOBAL_PTREE: table.to_bytes(4, "big")},
                        {table - 4: marker.to_bytes(4, "big")})
    result = get_addr(rs.R_TREE, 0x3FFF, pokes, global_=rs.APP_GLOBAL)
    assert result.long_answer() == marker
    assert result.word(aes.AES_RS_INDEX) == 0xFFFC


@pytest.mark.parametrize("aes_type", (rs.R_LAST_TYPE + 1, 0x7FFF, 0x8000, 0xFFFF), ids=("17", "$7fff", "$8000", "-1"))
def test_a_type_past_the_last_answers_no_address(aes_type):
    """`cmp.w #16; bhi`: UNSIGNED, so a negative type is past the last too."""
    result = get_addr(aes_type, 0)
    assert result.long_answer() == rs.RS_NO_ADDRESS
    assert result.word(aes.AES_RS_INDEX) == case.word_in(BASE_IMAGE, aes.AES_RS_INDEX), "only R_TREE stores it"


def test_an_address_through_line_f():
    assert_modelled(get_addr(rs.R_TEPVALID, 2, through_line_f=True), rs.R_TEPVALID, 2)


def test_an_element_through_line_f():
    offset = case.word_in(BASE_IMAGE, rs.GEM_HEADER + aes.RSH_BITBLK)
    result = get_sub(2, aes.RSH_BITBLK // 2, aes.BI_BYTES, through_line_f=True)
    assert result.long_answer() == rs.GEM_HEADER + offset + 2 * aes.BI_BYTES


# ---- fix_long, fix_ptr, fix_nptrs ------------------------------------------------------------------------------------
SLOT_AT = aes.RECTS_AT + 0x20


def fix_long(value, pokes=None, *, at=SLOT_AT, header=rs.GEM_HEADER, **kwargs):
    staged = merge_pokes(rs.current(GEM, header), {SLOT_AT: value.to_bytes(4, "big")}, pokes)
    return rs.run(rs.FIX_LONG, (at,), staged, **kwargs)


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_an_offset_becomes_an_address(through_line_f):
    result = fix_long(0x1234, through_line_f=through_line_f)
    assert result.long(SLOT_AT) == rs.GEM_HEADER + 0x1234
    assert result.answer() == 1


@pytest.mark.parametrize("value", (rs.RS_NO_ADDRESS, 0xFFFFFFFE, 0), ids=("-1 is left", "-2 is not", "zero is not"))
def test_only_minus_one_is_left_alone(value):
    result = fix_long(value)
    fixed = value == rs.RS_NO_ADDRESS
    assert result.long(SLOT_AT) == (value if fixed else (value + rs.GEM_HEADER) & 0xFFFFFFFF)
    assert result.answer() == (0 if fixed else 1)


def test_the_pointer_is_put_on_the_bus_and_a_tagged_header_carried():
    result = fix_long(0x40, at=SLOT_AT | aes.BUS_TAG, header=rs.GEM_HEADER | aes.BUS_TAG)
    assert result.long(SLOT_AT) == (rs.GEM_HEADER | aes.BUS_TAG) + 0x40


def test_the_offset_is_read_before_the_header():
    """The slot laid over rs_hdr itself: the offset read is the header, and so is the addend — twice the header."""
    result = rs.run(rs.FIX_LONG, (aes.AES_RS_HDR,), rs.current(GEM))
    assert result.long(aes.AES_RS_HDR) == 2 * rs.GEM_HEADER


def fix_ptr(aes_type, index, pokes, **kwargs):
    return rs.run(rs.FIX_PTR, (aes_type, index), pokes, **kwargs)


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_a_pointer_get_addr_names_is_fixed(through_line_f):
    """TEDINFO 1's template of the AES's resource, as the ROM holds it: an offset, made the snapshot's address."""
    pokes = rs.fresh(GEM)
    slot = rs.GEM_HEADER + GEM_COUNTS["tedinfo"] + aes.TE_BYTES + aes.TE_PTMPLT
    result = fix_ptr(rs.R_TEPTMPLT, 1, pokes, through_line_f=through_line_f)
    assert result.long(slot) == case.long_in(BASE_IMAGE, slot)
    assert result.answer() == 1


def fix_nptrs(last, aes_type, pokes, **kwargs):
    return rs.run(rs.FIX_NPTRS, (last, aes_type), pokes, **kwargs)


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_every_free_string_of_the_aes_s_resource_as_the_snapshot_has_it(through_line_f):
    pokes = rs.fresh(GEM)
    table = rs.GEM_HEADER + GEM_COUNTS["frstr"]
    result = fix_nptrs(GEM_COUNTS["nstring"] - 1, rs.R_FRSTR, pokes, through_line_f=through_line_f)
    length = GEM_COUNTS["nstring"] * aes.LONG_BYTES
    assert result.after(table, length) == bytes(BASE_IMAGE[table:table + length])


@pytest.mark.parametrize("last", (0, -1, -0x8000), ids=("one", "none", "none, the least word"))
def test_the_count_is_the_last_element_and_signed(last):
    pokes = rs.fresh(GEM)
    table = rs.GEM_HEADER + GEM_COUNTS["frstr"]
    result = fix_nptrs(last, rs.R_FRSTR, pokes)
    fixed = last + 1 if last >= 0 else 0
    assert result.after(table, fixed * 4) == bytes(BASE_IMAGE[table:table + fixed * 4])
    unfixed = table + fixed * 4
    assert result.after(unfixed, 4) == pokes[rs.GEM_HEADER][unfixed - rs.GEM_HEADER:unfixed - rs.GEM_HEADER + 4]


# ---- rs_sglobal, rs_gaddr, rs_saddr ---------------------------------------------------------------------------------
STALE_GLOBALS = rs.STALE_GLOBALS


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("global_", (GEM, DESK, DESK | aes.BUS_TAG), ids=("the AES's", "the desk's", "tagged"))
def test_a_global_makes_its_resource_current(global_, through_line_f):
    result = rs.run(rs.RS_SGLOBAL, (global_,), STALE_GLOBALS, through_line_f=through_line_f)
    assert result.long(aes.AES_RS_GLOBAL) == global_
    assert result.long(aes.AES_RS_HDR) == rs.header_of(global_ & OS_BUS_ADDR_MASK)


def test_the_header_is_read_through_the_global_just_stored():
    """A global[] laid so that its global[7..8] IS AES_RS_GLOBAL: the header read is the global just stored."""
    global_ = aes.AES_RS_GLOBAL - aes.AES_GLOBAL_PMEM
    result = rs.run(rs.RS_SGLOBAL, (global_,), STALE_GLOBALS)
    assert result.long(aes.AES_RS_HDR) == global_


def gaddr(global_, aes_type, index, pokes=None, answer=ANSWER_AT, **kwargs):
    staged = merge_pokes(STALE_GLOBALS, {ANSWER_AT: aes.STALE_WORD.to_bytes(2, "big") * 2}, pokes)
    return rs.run(rs.RS_GADDR, (global_, aes_type, index, answer), staged, **kwargs)


@pytest.mark.parametrize("aes_type", (*ALL_TYPES, rs.R_LAST_TYPE + 1, 0xFFFF))
def test_rsrc_gaddr_answers_every_type_through_its_pointer(aes_type):
    result = gaddr(DESK, aes_type, 1)
    stored = result.long(ANSWER_AT)
    assert stored == rs.model_get_addr(result.final, aes_type, 1)
    assert result.answer() == int(stored != rs.RS_NO_ADDRESS)


def test_rsrc_gaddr_s_pointers_are_put_on_the_bus():
    result = gaddr(GEM | aes.BUS_TAG, rs.R_TREE, 0, answer=ANSWER_AT | aes.BUS_TAG)
    assert result.long(ANSWER_AT) == aes.resource_tree(0)


def test_rsrc_gaddr_through_line_f():
    assert gaddr(GEM, rs.R_OBSPEC, 4, through_line_f=True).answer() == 1


def test_rsrc_gaddr_reads_its_answer_back():
    """The answer pointer laid over rs_hdr: the address is stored there, and read back to be compared."""
    result = gaddr(GEM, rs.R_STRING, 0, answer=aes.AES_RS_HDR)
    assert result.long(aes.AES_RS_HDR) == rs.model_get_addr(BASE_IMAGE, rs.R_STRING, 0)
    assert result.answer() == 1


def saddr(global_, aes_type, index, value, pokes=None, **kwargs):
    return rs.run(rs.RS_SADDR, (global_, aes_type, index, value), merge_pokes(STALE_GLOBALS, pokes), **kwargs)


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_rsrc_saddr_stores_at_the_address_named(through_line_f):
    """A new ob_spec for the desk's object 3 — the address R_OBSPEC names."""
    result = saddr(DESK, rs.R_OBSPEC, 3, 0x0012_3456, through_line_f=through_line_f)
    assert result.long(rs.model_get_addr(result.final, rs.R_OBSPEC, 3)) == 0x0012_3456
    assert result.answer() == 1


def test_rsrc_saddr_stores_nothing_for_no_address():
    """Past the last type: the globals set, and nothing stored (the stack band's own writes aside)."""
    result = saddr(DESK, rs.R_LAST_TYPE + 1, 3, 0x0012_3456)
    assert result.answer() == 0
    stored = {at for at in result.info["writes"] if at < emu.STACK_TOP - emu.STACK_SCRATCH}
    assert stored <= {*range(aes.AES_RS_GLOBAL, aes.AES_RS_GLOBAL + 4), *range(aes.AES_RS_HDR, aes.AES_RS_HDR + 4),
                      *range(aes.AES_LINEF_MASK_WORD, aes.AES_LINEF_MASK_WORD + 2)}


def test_rsrc_saddr_stores_on_the_24_bit_bus():
    """An application's header with a top byte: the address formed carries it, and the store lands 24 bits down."""
    resource, layout = rs.application_resource()
    pokes = merge_pokes(resource, rs.application_global(rs.APP_HEADER | aes.BUS_TAG))
    result = saddr(rs.APP_GLOBAL, rs.R_FRSTR, 1, 0x0000_7777, pokes)
    assert result.long(rs.APP_HEADER + layout["frstr"] + 4) == 0x7777


# THE BUS TOP: a tree-table entry is an application's data, so rsrc_saddr's R_TREE store can be aimed at the last
# bytes of the bus. The 68000 takes an address error for the odd one and wraps the even one's second word to $000000;
# the host refuses both BY NAME (`m68k_idioms.h`, `bus_span`) rather than store past its 16 MB image.
SADDR_ARGTYPES = ["ctypes.c_void_p", "ctypes.c_uint32", "ctypes.c_int16", "ctypes.c_int16", "ctypes.c_uint32"]
BUS_TOP_TREES = {"odd, the bus's last byte": (OS_BUS_ADDR_MASK, "the 68000's address error"),
                 "even, its last longword but two bytes": (OS_BUS_ADDR_MASK - 1, "past the top of the 24-bit bus")}


@pytest.mark.parametrize("tree, named", BUS_TOP_TREES.values(), ids=BUS_TOP_TREES)
def test_rsrc_saddr_at_the_top_of_the_bus_is_refused_on_the_host(tree, named):
    table = rs.APP_HEADER
    prelude = (f"{vdi_helpers.FRESH_IMAGE}; import struct; "
               f"struct.pack_into('>I', buf, {rs.APP_GLOBAL + aes.AES_GLOBAL_PTREE}, {table}); "
               f"struct.pack_into('>I', buf, {rs.APP_GLOBAL + aes.AES_GLOBAL_PMEM}, {rs.APP_HEADER}); "
               f"struct.pack_into('>I', buf, {table}, {tree})")
    returncode, stderr = vdi_helpers.refusal(routines.core_symbol(rs.RS_SADDR), SADDR_ARGTYPES,
                                             f"buf, {rs.APP_GLOBAL}, {rs.R_TREE}, 0, 0x12345678", prelude=prelude)
    assert returncode != 0 and named in stderr, stderr


def test_a_free_string_s_pointer_read_across_the_bus_top_is_refused_on_the_host():
    """A READ at the bus top is refused as a store is: a header whose free strings' offset puts string 0's table entry
    at $fffffe, the bus's last word — get_addr's R_STRING longword would run past the 16 MB image. The entry sits just
    past the header's own offset word, so the header's reads all fit below it."""
    bus_last_word = OS_BUS_ADDR_MASK - (aes.WORD_BYTES - 1)
    entry_offset = aes.RSH_FRSTR + aes.WORD_BYTES
    header = bus_last_word - entry_offset
    prelude = (f"{vdi_helpers.FRESH_IMAGE}; import struct; "
               f"struct.pack_into('>I', buf, {aes.AES_RS_HDR}, {header}); "
               f"struct.pack_into('>H', buf, {header + aes.RSH_FRSTR}, {entry_offset})")
    returncode, stderr = vdi_helpers.refusal(routines.core_symbol(rs.GET_ADDR), ["ctypes.c_void_p", "ctypes.c_int16", "ctypes.c_int16"],
                                             f"buf, {rs.R_STRING}, 0", prelude=prelude)
    assert returncode != 0 and "past the top of the 24-bit bus" in stderr, stderr


def test_rsrc_saddr_of_no_address_touches_no_bus_on_the_host():
    """...and its other side: a type naming no address ($ffffffff, which as a store would be the odd refusal above)
    returns 0 before any store — run in a child, so a store the C made anyway would be refused there by name."""
    prelude = (f"{vdi_helpers.FRESH_IMAGE}; import struct; "
               f"struct.pack_into('>I', buf, {rs.APP_GLOBAL + aes.AES_GLOBAL_PMEM}, {rs.APP_HEADER})")
    returncode, stderr = vdi_helpers.refusal(routines.core_symbol(rs.RS_SADDR), SADDR_ARGTYPES,
                                             f"buf, {rs.APP_GLOBAL}, {rs.R_LAST_TYPE + 1}, 0, 0x12345678", prelude=prelude)
    assert returncode == 0, stderr


# ---- the registry ---------------------------------------------------------------------------------------------------
# DIRECT rows priced; the worst realistic of each: fix_chpos's multiply with a negative offset; rs_obfix of a desk
# object; get_addr's deepest arm (a TEDINFO's field: a recursion, then get_sub) and its cheapest (a type past the last);
# fix_nptrs over all 30 of the AES's free strings.
aes.register("x-like, cells times the cell, a negative offset", rs.FIX_CHPOS, (COORDINATE_AT, 1),
             aes.leaf_machine(onto={COORDINATE_AT: cells_word(79, 255).to_bytes(2, "big")}))
aes.register("full width", rs.FIX_CHPOS, (COORDINATE_AT, 1),
             aes.leaf_machine(onto={COORDINATE_AT: cells_word(80, 0).to_bytes(2, "big")}))
aes.register("a desk object", rs.RS_OBFIX, (aes.TREE_AT, 0), aes.leaf_machine(onto=fresh_object_pokes(5)))
aes.register("an element", rs.GET_SUB, (3, 1, aes.OB_BYTES), aes.leaf_machine(onto=rs.current(GEM)))
for _type, _label in ((rs.R_TREE, "a tree"), (rs.R_TEPVALID, "a TEDINFO's field"), (rs.R_STRING, "a free string"),
                      (rs.R_LAST_TYPE + 1, "past the last type")):
    aes.register(_label, rs.GET_ADDR, (_type, 1), aes.leaf_machine(onto=rs.current(GEM)))
aes.register("an offset", rs.FIX_LONG, (SLOT_AT,), aes.leaf_machine(onto=merge_pokes(rs.current(GEM), {SLOT_AT: b"\0\0\1\0"})))
aes.register("a template", rs.FIX_PTR, (rs.R_TEPTMPLT, 1), aes.leaf_machine(onto=rs.fresh(GEM)))
aes.register("the AES's 30 free strings", rs.FIX_NPTRS, (GEM_COUNTS["nstring"] - 1, rs.R_FRSTR),
             aes.leaf_machine(onto=rs.fresh(GEM)))
aes.register("the desk's", rs.RS_SGLOBAL, (DESK,), aes.leaf_machine(onto=STALE_GLOBALS))
aes.register("a TEDINFO's field", rs.RS_GADDR, (DESK, rs.R_TEPVALID, 1, ANSWER_AT), aes.leaf_machine(onto=STALE_GLOBALS))
aes.register("a tree", rs.RS_GADDR, (DESK, rs.R_TREE, 1, ANSWER_AT), aes.leaf_machine(onto=STALE_GLOBALS))
aes.register("an ob_spec", rs.RS_SADDR, (DESK, rs.R_OBSPEC, 3, 0x123456), aes.leaf_machine(onto=STALE_GLOBALS))
aes.register("a TEDINFO's field", rs.GET_ADDR, (rs.R_TEPVALID, 1), aes.leaf_machine(onto=rs.current(GEM)),
             through_line_f=True)
