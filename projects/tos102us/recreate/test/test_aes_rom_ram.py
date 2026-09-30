"""AES rom_ram ($fee5c8) — the ROM's own resources handed out of the RAM copy start-up made: `src/aes/resource.c`.

    entry = rsc_table + 6 * part (muls.w): {address, length}
    part 3 (DESKTOP.INF):   LBCOPY(p, address, length); length       part 2 (the desk's icons): LBCOPY(p, address, n); n
    part 4 (...the rest):   LBCOPY(p, address + n, length - n); length - n
    part 0 / 1 / 5 (the AES's, the desk's, the format dialogs' resource) — and below 0, the AES's:
        first request (its flag 1, then 0): rs_global = p, rs_hdr = address; do_rsfix(address, length);
            the global[] p kept; the desk's and the format dialogs' rs_fixit(p)
        after: the kept global[] into p; the desk's desktop (tree 0) sized to the screen, through the desk's own
            rsrc_gaddr binding — rs_sglobal of its global[], get_addr, dsptch
    part 6 on: nothing — D0 still the entry's address

THE CAPTURED MACHINE is the check again. Every part's entry is the snapshot's own table; the AES's and the desk's
resources are relocated in the snapshot (their flags clear, 2 and 0) while the format dialogs' is NOT (its flag 1):
its first request is the snapshot's own next move, and a staged flag of 1 over a FRESH copy of the desk's or the AES's
replays the start-up's, whose result the snapshot holds.
"""
import pytest

from harness import BASE_IMAGE

import aes
import aes_resource as rs
import case
import test_aes_resource_fix as fix
import vdi
import vdi_helpers
from case import merge_pokes

ROM_RAM = "AES_ROM_ROM_RAM"
aes.declare_alcyon(ROM_RAM, aes.WORD_ANSWER, (vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.LONG_ARG, vdi.WORD_ARG))

GLOBAL_BYTES = aes.AES_GLOBAL_WORDS * aes.WORD_BYTES
TABLE_BYTES = rs.ROM_RSC_PARTS * rs.ROM_RSC_ENTRY_BYTES
for _at, _size, _why in ((aes.AES_RSC_TABLE, TABLE_BYTES, "rom_ram's table of the resource parts"),
                         *((at, aes.WORD_BYTES, "a resource part's first-request flag")
                           for at in (aes.AES_RSC_AES_FRESH, aes.AES_RSC_DESK_FRESH, aes.AES_RSC_FORMAT_FRESH)),
                         *((at, GLOBAL_BYTES, "a resource part's kept global[]")
                           for at in (aes.AES_RSC_AES_GLOBAL, aes.AES_RSC_DESK_GLOBAL, aes.AES_RSC_FORMAT_GLOBAL)),
                         (rs.DESK_GLOBAL, GLOBAL_BYTES, "the desk's global[]"),
                         (rs.GEM_GLOBAL, GLOBAL_BYTES, "the AES's global[]")):
    aes.declare_case_field(_at, _size, _why)


def part(index, image=BASE_IMAGE):
    """Part `index`'s `(address, length)`, as the snapshot's table holds it."""
    entry = aes.AES_RSC_TABLE + index * rs.ROM_RSC_ENTRY_BYTES
    return case.long_in(image, entry + rs.ROM_RSC_ADDRESS), case.word_in(image, entry + rs.ROM_RSC_BYTES)


def rom_ram(index, pointer, size=0, pokes=None, **kwargs):
    return rs.run(ROM_RAM, (index, pointer, size), pokes, **kwargs)


STALE_PART = {rs.PART_AT: bytes([vdi.FILL]) * rs.PART_BYTES}
DESK_ICONS_BYTES = part(rs.ROM_RSC_DESK_ICONS_TAIL)[1]


# ---- the copied parts ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_the_default_desktop_inf_is_copied_whole(through_line_f):
    address, length = part(rs.ROM_RSC_DESKTOP_INF)
    result = rom_ram(rs.ROM_RSC_DESKTOP_INF, rs.PART_AT, 0x7777, STALE_PART, through_line_f=through_line_f)
    assert result.after(rs.PART_AT, length) == bytes(BASE_IMAGE[address:address + length])
    assert result.after(rs.PART_AT, 8) == b"#a000000"
    assert result.final[rs.PART_AT + length] == vdi.FILL
    assert result.answer() == length


def test_the_caller_s_pointer_is_put_on_the_bus():
    """A tagged pointer: the copy (LBCOPY's) and the global[] handed back (wcopy's) both land 24 bits down, and a
    resource's first request stores it into rs_global AS IT IS."""
    address, length = part(rs.ROM_RSC_DESKTOP_INF)
    copied = rom_ram(rs.ROM_RSC_DESKTOP_INF, rs.PART_AT | aes.BUS_TAG, 0, STALE_PART)
    assert copied.after(rs.PART_AT, length) == bytes(BASE_IMAGE[address:address + length])
    handed = rom_ram(rs.ROM_RSC_AES, rs.APP_GLOBAL | aes.BUS_TAG, 0, STALE_GLOBAL)
    kept = aes.AES_RSC_AES_GLOBAL
    assert handed.after(rs.APP_GLOBAL, GLOBAL_BYTES) == bytes(BASE_IMAGE[kept:kept + GLOBAL_BYTES])
    first = rom_ram(rs.ROM_RSC_FORMAT, rs.DESK_GLOBAL | aes.BUS_TAG, 0)
    assert first.long(aes.AES_RS_GLOBAL) == rs.DESK_GLOBAL | aes.BUS_TAG
    assert first.long(rs.DESK_GLOBAL + aes.AES_GLOBAL_PMEM) == FORMAT_ADDRESS


@pytest.mark.parametrize("size", (0, 1, 0x100, rs.PART_BYTES), ids=("none", "one", "a buffer", "three"))
def test_the_desk_s_icons_are_copied_size_bytes_of(size):
    address, _ = part(rs.ROM_RSC_DESK_ICONS)
    result = rom_ram(rs.ROM_RSC_DESK_ICONS, rs.PART_AT, size, STALE_PART)
    assert result.after(rs.PART_AT, size) == bytes(BASE_IMAGE[address:address + size])
    assert result.answer() == size


@pytest.mark.parametrize("size", (DESK_ICONS_BYTES - 0x100, DESK_ICONS_BYTES - 1, DESK_ICONS_BYTES),
                         ids=("the last 256", "the last byte", "none"))
def test_the_rest_of_the_desk_s_icons_is_copied_past_size_bytes(size):
    """Part 4 is part 2's entry again: `size` bytes skipped (zero-extended), the rest copied, and its length the
    answer."""
    address, length = part(rs.ROM_RSC_DESK_ICONS_TAIL)
    result = rom_ram(rs.ROM_RSC_DESK_ICONS_TAIL, rs.PART_AT, size, STALE_PART)
    rest = length - size
    assert result.after(rs.PART_AT, rest) == bytes(BASE_IMAGE[address + size:address + length])
    assert result.answer() == rest


@pytest.mark.parametrize("index", (6, 7, 0x7FFF), ids=("6", "7", "the largest"))
def test_a_part_past_the_last_is_nothing_but_its_entry_s_address(index):
    """`muls.w #6`: the entry is formed, read and left in D0 — nothing stored."""
    result = rom_ram(index, rs.PART_AT, 0, STALE_PART)
    assert result.answer() == aes.signed(aes.AES_RSC_TABLE + 6 * index)
    assert result.after(rs.PART_AT, rs.PART_BYTES) == STALE_PART[rs.PART_AT]


# ---- the resources, requested again ----------------------------------------------------------------------------------
STALE_GLOBAL = {rs.APP_GLOBAL: bytes([vdi.FILL]) * rs.GLOBAL_BYTES}


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("index,kept", ((rs.ROM_RSC_AES, aes.AES_RSC_AES_GLOBAL), (-1, aes.AES_RSC_AES_GLOBAL),
                                        (-0x8000, aes.AES_RSC_AES_GLOBAL)), ids=("the AES's", "-1", "the least"))
def test_the_aes_s_resource_again_hands_its_global_back(index, kept, through_line_f):
    """The AES's flag is 2 in the snapshot, not 1: the request is not its first, and the kept global[] goes into the
    caller's. A part BELOW 0 is the AES's too (`blt` the desk)."""
    result = rom_ram(index, rs.APP_GLOBAL, 0, STALE_GLOBAL, through_line_f=through_line_f)
    assert result.after(rs.APP_GLOBAL, GLOBAL_BYTES) == bytes(BASE_IMAGE[kept:kept + GLOBAL_BYTES])
    assert result.answer() == 0, "wcopy's count, run down"


DESKTOP_WORDS = ((0, aes.OB_WIDTH), (1, aes.OB_WIDTH), (0, aes.OB_HEIGHT), (1, aes.OB_HEIGHT), (7, aes.OB_WIDTH),
                 (7, aes.OB_HEIGHT))
DESKTOP = case.long_in(BASE_IMAGE, rs.DESK_HEADER + rs.header_words(rs.DESK_HEADER)["trindex"])


def stale_desktop():
    return {DESKTOP + index * aes.OB_BYTES + field: aes.STALE_WORD.to_bytes(2, "big") for index, field in DESKTOP_WORDS}


def desktop_words(image):
    return [case.word_in(image, DESKTOP + index * aes.OB_BYTES + field) for index, field in DESKTOP_WORDS]


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_the_desk_s_resource_again_sizes_the_desktop_as_the_snapshot_has_it(through_line_f):
    """The desk's flag is 0: its global[] handed back into the caller's, and the desktop's six words — staged STALE —
    stored as the snapshot holds them (320 x 200 over 8 x 8 cells); the globals left as the desk's binding set them."""
    pokes = merge_pokes(STALE_GLOBAL, stale_desktop(), rs.STALE_GLOBALS)
    result = rom_ram(rs.ROM_RSC_DESK, rs.APP_GLOBAL, 0, pokes, through_line_f=through_line_f)
    kept = aes.AES_RSC_DESK_GLOBAL
    assert result.after(rs.APP_GLOBAL, GLOBAL_BYTES) == bytes(BASE_IMAGE[kept:kept + GLOBAL_BYTES])
    assert desktop_words(result.final) == desktop_words(BASE_IMAGE)
    assert (result.long(aes.AES_RS_GLOBAL), result.long(aes.AES_RS_HDR)) == (rs.DESK_GLOBAL, rs.DESK_HEADER)
    assert result.answer() == desktop_words(BASE_IMAGE)[-1]


@pytest.mark.parametrize("wchar,hchar,ncols", ((16, 16, 40), (8, 16, 80), (0xFFF0, 0x8000, 3)),
                         ids=("medium cells", "high resolution", "negative cells"))
def test_the_desktop_follows_the_screen_s_metrics(wchar, hchar, ncols):
    metrics = aes.field_pokes("AES", GL_WCHAR=wchar, GL_HCHAR=hchar, GL_NCOLS=ncols)
    result = rom_ram(rs.ROM_RSC_DESK, rs.DESK_GLOBAL, 0, merge_pokes(metrics, stale_desktop()))
    width = (aes.signed(wchar) * ncols) & 0xFFFF
    rows = aes.signed(hchar)
    assert desktop_words(result.final) == [width, width, (rows * 25) & 0xFFFF, (rows + 2) & 0xFFFF, width,
                                           (rows * 24) & 0xFFFF]


def test_the_desktop_is_sized_through_the_desk_s_own_global_not_the_caller_s():
    """The binding reaches the desktop through the desk's global[] whatever `pointer` names: the caller's gets the
    kept global[], and the sizing still lands in the desk's tree."""
    result = rom_ram(rs.ROM_RSC_DESK, rs.APP_GLOBAL, 0, merge_pokes(STALE_GLOBAL, stale_desktop()))
    assert desktop_words(result.final) == desktop_words(BASE_IMAGE)


def test_outside_the_dispatcher_the_desk_s_binding_is_not_reconstructed():
    """The binding's dsptch enters disp when AES_INDISP is clear, which the port refuses by name — the host halts
    rather than one build switching process. The ROM's side of it is disp's (not a leaf's), so no oracle runs here:
    the core is called in a child over a CLEAR image, whose AES_INDISP is 0 and whose part 1 is a re-request."""
    code, stderr = vdi_helpers.refusal("aes_rom_ram", ["ctypes.c_void_p", "ctypes.c_int16", "ctypes.c_uint32",
                                                       "ctypes.c_int16"], f"buf, {rs.ROM_RSC_DESK}, {rs.DESK_GLOBAL}, 0")
    assert code != 0 and "disp and the process switch are not reconstructed" in stderr


# ---- the resources' FIRST requests: the format dialogs' is the snapshot's next; the others replayed ------------------
FORMAT_ADDRESS, FORMAT_LENGTH = part(rs.ROM_RSC_FORMAT)
FORMAT_COUNTS = rs.header_words(FORMAT_ADDRESS)
aes.declare_case_field(FORMAT_ADDRESS, FORMAT_LENGTH, "the format dialogs' resource, unrelocated in the snapshot")


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_the_format_dialogs_first_request_relocates_them_in_place(through_line_f):
    """As the format utility makes it ($fed88e: the desk's global[]): the resource relocated where it lies — every
    tree pointer, TEDINFO pointer and object spec an address inside it — the global[] kept, the flag cleared, and
    the objects fixed (rs_fixit's answer)."""
    result = rom_ram(rs.ROM_RSC_FORMAT, rs.DESK_GLOBAL, 0, through_line_f=through_line_f)
    assert result.word(aes.AES_RSC_FORMAT_FRESH) == 0
    assert result.long(rs.DESK_GLOBAL + aes.AES_GLOBAL_PMEM) == FORMAT_ADDRESS
    assert result.word(rs.DESK_GLOBAL + aes.AES_GLOBAL_LMEM) == FORMAT_LENGTH
    kept = aes.AES_RSC_FORMAT_GLOBAL
    assert result.after(kept, GLOBAL_BYTES) == result.after(rs.DESK_GLOBAL, GLOBAL_BYTES)
    tree = result.long(FORMAT_ADDRESS + FORMAT_COUNTS["trindex"])
    assert tree == FORMAT_ADDRESS + FORMAT_COUNTS["object"]
    assert result.long(rs.DESK_GLOBAL + aes.AES_GLOBAL_PTREE) == FORMAT_ADDRESS + FORMAT_COUNTS["trindex"]
    for index in range(FORMAT_COUNTS["nted"]):
        text = result.long(FORMAT_ADDRESS + FORMAT_COUNTS["tedinfo"] + index * aes.TE_BYTES + aes.TE_PTEXT)
        assert FORMAT_ADDRESS <= text < FORMAT_ADDRESS + FORMAT_LENGTH


def test_the_format_dialogs_second_request_hands_their_global_back():
    """The run after the first, chained: the flag now clear, the kept global[] handed into another caller's."""
    first = rom_ram(rs.ROM_RSC_FORMAT, rs.DESK_GLOBAL, 0)
    second = rom_ram(rs.ROM_RSC_FORMAT, rs.APP_GLOBAL, 0, merge_pokes(case.continued(first), STALE_GLOBAL))
    assert second.after(rs.APP_GLOBAL, GLOBAL_BYTES) == first.after(aes.AES_RSC_FORMAT_GLOBAL, GLOBAL_BYTES)
    assert second.answer() == 0


# The kept global[]s FILLed: the snapshot's already hold what a replayed first request copies into them, so a C that
# skipped the copy would otherwise leave the right bytes behind.
STALE_KEPT_GLOBALS = {kept: bytes([vdi.FILL]) * GLOBAL_BYTES for kept in (aes.AES_RSC_DESK_GLOBAL, aes.AES_RSC_AES_GLOBAL)}


def fresh_first_request(global_, flag):
    """A fresh copy of `global_`'s resource where the start-up relocated it, its part's flag 1 again, and the kept
    global[]s stale."""
    return merge_pokes(rs.fresh(global_), aes.field_pokes("AES", **{flag: 1}), STALE_KEPT_GLOBALS)


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_the_desk_s_first_request_replays_the_start_up_as_the_snapshot_has_it(through_line_f):
    """A FRESH copy of the desk's resource where the start-up relocated it and its flag 1 again: relocated and fixed
    as the snapshot has it (but the fields edited since), its global[] as the snapshot's, and kept.

    THE ATTRIBUTION PASS IS OFF here alone (`vdi.READS_A_POINTER_IT_WRITES`; measured: poisoned, the ROM's run does not
    return within the oracle's 200,000 instructions, in both entries): the desk's relocation reads back the pointers
    it has just stored — fix_tedinfo counts each string through the one it fixed, as in `test_aes_resource_fix.py` —
    and inverted by the pass they lead the walk astray. The format dialogs' and the AES's replays keep the pass."""
    pokes = fresh_first_request(rs.DESK_GLOBAL, "RSC_DESK_FRESH")
    result = rom_ram(rs.ROM_RSC_DESK, rs.DESK_GLOBAL, 0, pokes, through_line_f=through_line_f,
                     **vdi.READS_A_POINTER_IT_WRITES)
    fix.assert_as_the_snapshot_has_it(result, rs.DESK_HEADER, rs.DESK_BYTES, rs.DESK_GLOBAL)
    assert result.after(rs.DESK_GLOBAL, GLOBAL_BYTES) == bytes(BASE_IMAGE[rs.DESK_GLOBAL:rs.DESK_GLOBAL + GLOBAL_BYTES])
    assert result.after(aes.AES_RSC_DESK_GLOBAL, GLOBAL_BYTES) == result.after(rs.DESK_GLOBAL, GLOBAL_BYTES)
    assert result.word(aes.AES_RSC_DESK_FRESH) == 0


def test_the_aes_s_first_request_relocates_but_leaves_the_objects():
    """The AES's first request, replayed over a fresh copy: every pointer section as the snapshot has it — the
    objects are NOT fixed here (no rs_fixit for part 0: gem_main fixes them itself) and stay in cells."""
    pokes = fresh_first_request(rs.GEM_GLOBAL, "RSC_AES_FRESH")
    result = rom_ram(rs.ROM_RSC_AES, rs.GEM_GLOBAL, 0, pokes)
    counts = rs.header_words(rs.GEM_HEADER)
    objects = rs.GEM_HEADER + counts["object"]
    fix.assert_as_the_snapshot_has_it(result, rs.GEM_HEADER, objects - rs.GEM_HEADER, rs.GEM_GLOBAL)
    fresh_objects = pokes[rs.GEM_HEADER][counts["object"]:counts["object"] + counts["nobs"] * aes.OB_BYTES]
    assert result.after(objects, len(fresh_objects)) == fresh_objects
    assert result.after(aes.AES_RSC_AES_GLOBAL, GLOBAL_BYTES) == result.after(rs.GEM_GLOBAL, GLOBAL_BYTES)
    assert result.answer() == 0


# ---- the registry ---------------------------------------------------------------------------------------------------
# The worst realistic row: the desk's first request, the whole relocation of its 9 KB resource. Its cheapest: a part
# past the last.
aes.register("the default DESKTOP.INF", ROM_RAM, (rs.ROM_RSC_DESKTOP_INF, rs.PART_AT, 0), aes.leaf_machine())
aes.register("the desk's icons, three buffers", ROM_RAM, (rs.ROM_RSC_DESK_ICONS, rs.PART_AT, rs.PART_BYTES),
             aes.leaf_machine())
aes.register("the rest of the desk's icons", ROM_RAM, (rs.ROM_RSC_DESK_ICONS_TAIL, rs.PART_AT, DESK_ICONS_BYTES - rs.PART_BYTES),
             aes.leaf_machine())
aes.register("past the last part", ROM_RAM, (6, rs.PART_AT, 0), aes.leaf_machine())
aes.register("the AES's again", ROM_RAM, (rs.ROM_RSC_AES, rs.APP_GLOBAL, 0), aes.leaf_machine())
aes.register("the desk's again, the desktop sized", ROM_RAM, (rs.ROM_RSC_DESK, rs.DESK_GLOBAL, 0),
             aes.leaf_machine(onto=stale_desktop()))
aes.register("the format dialogs' first", ROM_RAM, (rs.ROM_RSC_FORMAT, rs.DESK_GLOBAL, 0), aes.leaf_machine())
aes.register("the desk's first, replayed", ROM_RAM, (rs.ROM_RSC_DESK, rs.DESK_GLOBAL, 0),
             aes.leaf_machine(onto=fresh_first_request(rs.DESK_GLOBAL, "RSC_DESK_FRESH")))
aes.register("the AES's first, replayed", ROM_RAM, (rs.ROM_RSC_AES, rs.GEM_GLOBAL, 0),
             aes.leaf_machine(onto=fresh_first_request(rs.GEM_GLOBAL, "RSC_AES_FRESH")))
