"""AES resource RELOCATION — what a load runs over a resource file: `src/aes/resource.c`.

    fix_trindex():   global[5..6] = the tree table; fix_long of every tree pointer, ntree-1..0 (count read after)
    fix_objects():   every object: rs_obfix(obj, 0); fix_long(&ob_spec) unless G_BOX, G_IBOX, G_BOXCHAR
    fix_tedinfo():   every TEDINFO: fix_ptr text, template (each fixed one's length + 1 into te_txtlen/te_tmplen), valid
    do_rsfix(h, n):  global[7..8] = h; global[9] = n; fix_trindex; fix_tedinfo; fix_nptrs over the ICONBLKs' three
                     pointers, the BITBLKs', the free strings and images — each count from rs_hdr, not h
    rs_fixit(g):     rs_sglobal(g); fix_objects()

THE STRONG CHECK IS THE CAPTURED MACHINE. The ROM's own two resources are held in the ROM unrelocated and were
relocated by these very routines at start-up, into the RAM the snapshot captured: a FRESH copy out of the ROM, staged
where the start-up relocated it and run through the relocation again, must come out as the snapshot has it — the
differential holds the C to the ROM's run, and the run is held to the machine, byte for byte, but for the few fields
the AES and the desk have edited since (named below). An application's resource, built by shape, reaches what neither
of the ROM's does: ICONBLKs, and a text or template pointer of -1.
"""
import pytest

from harness import BASE_IMAGE, make_image

import aes
import aes_resource as rs
import case
import vdi
from case import merge_pokes

GEM, DESK = rs.GEM_GLOBAL, rs.DESK_GLOBAL
HOMES = {GEM: (rs.GEM_HEADER, rs.GEM_BYTES, rs.GEM_PART_BYTES), DESK: (rs.DESK_HEADER, rs.DESK_BYTES, rs.DESK_PART_BYTES)}
IDS = {GEM: "the AES's", DESK: "the desk's"}


def counts(global_):
    return rs.header_words(HOMES[global_][0])


def section(global_, name, element_bytes, count_name):
    """`(address, bytes)` of a section of `global_`'s resource as the snapshot has it."""
    header = HOMES[global_][0]
    return header + counts(global_)[name], counts(global_)[count_name] * element_bytes


def snapshot_bytes(at, length):
    return bytes(BASE_IMAGE[at:at + length])


# WHAT THE MACHINE HAS EDITED SINCE THE LOAD, BYTE by byte — (object, byte offset), every one a word field's LOW byte
# (measured: a fresh copy relocated and fixed differs from the snapshot in exactly these 17 bytes, and in no high byte):
#   * the file selector's root centred by form_center ($fe92ae stores ob_y): 1 byte;
#   * the desk's menu bar trimmed to the screen (ob_tail and ob_height of its title bar 8 and drop-down box 36, ob_next of
#     their last children 9 and 42): 6 bytes;
#   * its menu items DISABLED (ob_state $08: 18, 19, 21, 22, 23, 25, 37, 38) or CHECKED ($04: 29, 32) by the desk: 10.
LOW = aes.OB_WORD_LOW_BYTE
EDITED_SINCE = {
    GEM: {(0, aes.OB_Y + LOW)},
    DESK: {(8, aes.OB_TAIL + LOW), (8, aes.OB_HEIGHT + LOW), (9, aes.OB_NEXT + LOW), (36, aes.OB_TAIL + LOW),
           (36, aes.OB_HEIGHT + LOW), (42, aes.OB_NEXT + LOW),
           *((index, aes.OB_STATE + LOW) for index in (18, 19, 21, 22, 23, 25, 29, 32, 37, 38))},
}


def edited_bytes(global_):
    """Every byte of `EDITED_SINCE` for `global_`, as addresses."""
    objects, _ = section(global_, "object", aes.OB_BYTES, "nobs")
    return {objects + index * aes.OB_BYTES + offset for index, offset in EDITED_SINCE[global_]}


def assert_as_the_snapshot_has_it(result, at, length, global_):
    """The bytes `[at, at + length)` of the run's end equal the snapshot's but for EXACTLY the bytes edited since that
    lie among them: each of those differs, and nothing else does."""
    differing = {address for address in range(at, at + length) if result.final[address] != BASE_IMAGE[address]}
    edited = {address for address in edited_bytes(global_) if at <= address < at + length}
    assert differing == edited, (sorted(hex(address) for address in differing - edited),
                                 sorted(hex(address) for address in edited - differing))


# THE ATTRIBUTION PASS IS OFF for fix_tedinfo and do_rsfix (`vdi.READS_A_POINTER_IT_WRITES`): each fixes a
# TEDINFO's text and template pointers and then counts the string THROUGH the pointer it stored, so the pass —
# which inverts every stored byte before the run — sends the count into the I/O page (measured: $fff3cd, $ffe2e3;
# forced on, 17 of their 18 cases go red). The one it serves keeps it (`POISONED`: the TEDINFO laid over the header,
# whose strings are counted from a pointer no pass inverts into the I/O page). What stands in for it elsewhere: every
# length word the relocation sets is staged STALE (`stale_lengths`), so a skipped store shows, and every pointer the
# relocation fixes starts as the file's offset, never as its own answer.
UNPOISONED = {rs.FIX_TEDINFO: vdi.READS_A_POINTER_IT_WRITES, rs.DO_RSFIX: vdi.READS_A_POINTER_IT_WRITES}
POISONED = {"poison": True}


LENGTH_OF = {aes.TE_PTEXT: aes.TE_TXTLEN, aes.TE_PTMPLT: aes.TE_TMPLEN}


def stale_lengths(global_):
    """te_txtlen and te_tmplen of `global_`'s TEDINFOs STALE — each whose string pointer the file sets, that is: the
    relocation leaves the length of a -1 pointer as the file has it (the AES's TEDINFO 12 has all three -1)."""
    header, source = (rs.GEM_HEADER, rs.GEM_FRESH_AT) if global_ == GEM else (rs.DESK_HEADER, rs.DESK_FRESH_AT)
    first = counts(global_)["tedinfo"]
    stale = aes.STALE_WORD.to_bytes(2, "big")
    return {header + first + index * aes.TE_BYTES + length: stale
            for index in range(counts(global_)["nted"]) for pointer, length in LENGTH_OF.items()
            if case.long_in(BASE_IMAGE, source + first + index * aes.TE_BYTES + pointer) != rs.RS_NO_ADDRESS}


def run(name, arguments, pokes, **kwargs):
    return rs.run(name, arguments, pokes, **{**UNPOISONED.get(name, {}), **kwargs})


def fresh_run(name, arguments, global_, pokes=None, **kwargs):
    staged = merge_pokes(rs.fresh(global_), stale_lengths(global_), pokes)
    return run(name, arguments, staged, **kwargs)


# ---- fix_trindex --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("global_", (GEM, DESK), ids=IDS.get)
def test_the_tree_table_is_relocated_as_the_snapshot_has_it(global_, through_line_f):
    result = fresh_run(rs.FIX_TRINDEX, (), global_, aes.field_pokes("AES", RS_INDEX=aes.STALE_WORD),
                       through_line_f=through_line_f)
    assert_as_the_snapshot_has_it(result, *section(global_, "trindex", aes.LONG_BYTES, "ntree"), global_)
    ptree = global_ + aes.AES_GLOBAL_PTREE
    assert result.long(ptree) == case.long_in(BASE_IMAGE, ptree)


def test_the_tree_count_is_read_after_the_table_is_stored():
    """The ORDER: an application's global[] laid so that its global[5..6] IS the header's ntree word and the word
    after. The table's address is stored there first, so the count read is its HIGH word ($000e) — fourteen tree
    pointers fixed where the file has two, reading on past the table into the objects."""
    resource, layout = rs.application_resource()
    global_ = rs.APP_HEADER + aes.RSH_NTREE - aes.AES_GLOBAL_PTREE
    result = rs.run(rs.FIX_TRINDEX, (), merge_pokes(resource, rs.current(global_, rs.APP_HEADER)))
    table = rs.APP_HEADER + layout["trindex"]
    assert result.long(rs.APP_HEADER + aes.RSH_NTREE) == table
    fixed = (rs.APP_HEADER + aes.RSH_NTREE) >> 16
    for tree in range(fixed):
        original = case.long_in(make_image(resource), table + 4 * tree)
        expected = original if original == rs.RS_NO_ADDRESS else (original + rs.APP_HEADER) & 0xFFFFFFFF
        assert result.long(table + 4 * tree) == expected


# ---- fix_objects --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("global_", (GEM, DESK), ids=IDS.get)
def test_every_object_is_fixed_as_the_snapshot_has_it(global_, through_line_f):
    """All 38 of the AES's objects, all 172 of the desk's: coordinates in pixels, ob_specs addresses."""
    result = fresh_run(rs.FIX_OBJECTS, (), global_, through_line_f=through_line_f)
    assert_as_the_snapshot_has_it(result, *section(global_, "object", aes.OB_BYTES, "nobs"), global_)


def test_a_colour_spec_is_left_and_every_other_fixed():
    """The application's objects: G_BOX, G_IBOX and G_BOXCHAR keep their colour words — G_IBOX's with an extended
    type in ob_type's high byte, which is masked off — a spec of -1 is left, and the rest become addresses."""
    resource, layout = rs.application_resource()
    pokes = merge_pokes(resource, rs.application_global(), rs.current(rs.APP_GLOBAL, rs.APP_HEADER))
    result = rs.run(rs.FIX_OBJECTS, (), pokes)
    before = make_image(pokes)
    objects = rs.APP_HEADER + layout["object"]
    for index in range(layout["nobs"]):
        spec_at = objects + index * aes.OB_BYTES + aes.OB_SPEC
        kind = case.word_in(before, objects + index * aes.OB_BYTES + aes.OB_TYPE) & aes.OB_TYPE_MASK
        spec = case.long_in(before, spec_at)
        left = kind in (aes.G_BOX, aes.G_IBOX, aes.G_BOXCHAR) or spec == rs.RS_NO_ADDRESS
        assert result.long(spec_at) == (spec if left else spec + rs.APP_HEADER), index


def test_the_answer_is_object_0_s_last_step():
    """D0 as the LAST object fixed — object 0 — left it: fix_long's 0 for a spec of -1 on a type that is not a colour
    (object 0 staged a G_STRING with no string), where rs_obfix's `moveq #1` came before it."""
    resource, layout = rs.application_resource()
    object_0 = rs.APP_HEADER + layout["object"]
    pokes = merge_pokes(resource, rs.application_global(), rs.current(rs.APP_GLOBAL, rs.APP_HEADER),
                        aes.object_pokes(object_0, 0, TYPE=rs.G_STRING, SPEC=rs.RS_NO_ADDRESS))
    assert rs.run(rs.FIX_OBJECTS, (), pokes).answer() == 0
    assert rs.run(rs.RS_FIXIT, (rs.APP_GLOBAL,), pokes).answer() == 0


# ---- fix_tedinfo --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("global_", (GEM, DESK), ids=IDS.get)
def test_every_tedinfo_is_fixed_as_the_snapshot_has_it(global_, through_line_f):
    """13 and 26 TEDINFOs: three pointers each, and the two lengths counted through the pointers just fixed."""
    result = fresh_run(rs.FIX_TEDINFO, (), global_, through_line_f=through_line_f)
    assert_as_the_snapshot_has_it(result, *section(global_, "tedinfo", aes.TE_BYTES, "nted"), global_)


@pytest.mark.parametrize("missing", ("TE_PTEXT", "TE_PTMPLT", None), ids=("no text", "no template", "both"))
def test_a_missing_string_keeps_its_length(missing):
    """A text or template pointer of -1 is left, and its length word with it; the other is still counted."""
    resource, layout = rs.application_resource()
    tedinfo = rs.APP_HEADER + layout["tedinfo"]
    stale = aes.STALE_WORD.to_bytes(2, "big")
    pokes = merge_pokes(resource, rs.application_global(), rs.current(rs.APP_GLOBAL, rs.APP_HEADER),
                        {tedinfo + aes.TE_TXTLEN: stale, tedinfo + aes.TE_TMPLEN: stale},
                        {tedinfo + getattr(aes, missing): b"\xff" * 4} if missing else None)
    result = run(rs.FIX_TEDINFO, (), pokes)
    for pointer, length in (("TE_PTEXT", aes.TE_TXTLEN), ("TE_PTMPLT", aes.TE_TMPLEN)):
        text = result.long(tedinfo + getattr(aes, pointer))
        if pointer == missing:
            assert (text, result.word(tedinfo + length)) == (rs.RS_NO_ADDRESS, aes.STALE_WORD)
        else:
            string = bytes(result.final[text:text + 64]).split(b"\0")[0]
            assert result.word(tedinfo + length) == len(string) + 1


def test_the_text_is_fixed_before_the_template():
    """The ORDER, which only an overlap shows: an application's resource whose TEDINFO section is at offset 0 — its one
    TEDINFO IS the header. The text pointer is the header's first two words; the template pointer the next two, the
    TEDINFOs' own offset among them. Fixed first, the text is found at the offset as the file has it; the template,
    fixed next, rewrites that offset, so the validation pointer is looked for through the new one."""
    resource, layout = rs.application_resource()
    blob = bytearray(resource[rs.APP_HEADER])
    blob[aes.RSH_TEDINFO:aes.RSH_TEDINFO + 2] = b"\0\0"
    blob[aes.RSH_NTED:aes.RSH_NTED + 2] = b"\0\1"
    pokes = merge_pokes({rs.APP_HEADER: bytes(blob)}, rs.application_global(), rs.current(rs.APP_GLOBAL, rs.APP_HEADER))
    result = run(rs.FIX_TEDINFO, (), pokes, **POISONED)
    before = make_image(pokes)
    assert result.long(rs.APP_HEADER) == case.long_in(before, rs.APP_HEADER) + rs.APP_HEADER
    assert result.long(rs.APP_HEADER + aes.TE_PTMPLT) == case.long_in(before, rs.APP_HEADER + aes.TE_PTMPLT) + rs.APP_HEADER


def test_the_length_is_counted_through_the_pointer_as_stored():
    """A tagged header: every fixed pointer carries its top byte, and the length is counted through it on 24 bits."""
    resource, layout = rs.application_resource()
    tagged = rs.APP_HEADER | aes.BUS_TAG
    result = run(rs.FIX_TEDINFO, (), merge_pokes(resource, rs.application_global(tagged), rs.current(rs.APP_GLOBAL, tagged)))
    tedinfo = rs.APP_HEADER + layout["tedinfo"]
    assert result.long(tedinfo + aes.TE_PTEXT) == tagged + layout["text0"]
    assert result.word(tedinfo + aes.TE_TXTLEN) == len(b"TEXT") + 1


# ---- do_rsfix, and rs_fixit after it: the whole load's relocation ---------------------------------------------------
def load(global_, pokes=None, **kwargs):
    header, _, part_bytes = HOMES[global_]
    return fresh_run(rs.DO_RSFIX, (header, part_bytes), global_, pokes, **kwargs)


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("global_", (GEM, DESK), ids=IDS.get)
def test_the_rom_s_resource_is_relocated_then_fixed_as_the_snapshot_has_it(global_, through_line_f):
    """do_rsfix then rs_fixit, chained — the second run starts where the first ended: the whole resource, every
    byte, and the global[] (the header, the length, the tree table) as the start-up left them."""
    relocated = load(global_, through_line_f=through_line_f)
    fixed = rs.run(rs.RS_FIXIT, (global_,), case.continued(relocated), through_line_f=through_line_f)
    header, resource_bytes, _ = HOMES[global_]
    assert_as_the_snapshot_has_it(fixed, header, resource_bytes, global_)
    assert fixed.after(global_, rs.GLOBAL_WORDS * 2) == snapshot_bytes(global_, rs.GLOBAL_WORDS * 2)


def test_the_counts_are_the_current_header_s_not_the_argument_s():
    """do_rsfix handed an application's header while rs_hdr names the AES's fresh copy: the argument goes into the
    global[] as it is, and every pass is over the AES's resource."""
    resource, layout = rs.application_resource()
    result = run(rs.DO_RSFIX, (rs.APP_HEADER, 0x1234), merge_pokes(rs.fresh(GEM), resource))
    assert result.long(GEM + aes.AES_GLOBAL_PMEM) == rs.APP_HEADER
    assert result.word(GEM + aes.AES_GLOBAL_LMEM) == 0x1234
    frstr, length = section(GEM, "frstr", aes.LONG_BYTES, "nstring")
    assert result.after(frstr, length) == snapshot_bytes(frstr, length)
    assert result.after(rs.APP_HEADER, layout["rssize"]) == resource[rs.APP_HEADER]


def test_a_tagged_header_argument_is_stored_as_it_is():
    """do_rsfix's header into global[7..8] with its top byte — a store, never dereferenced here."""
    header, _, part_bytes = HOMES[DESK]
    result = fresh_run(rs.DO_RSFIX, (header | aes.BUS_TAG, part_bytes), DESK)
    assert result.long(DESK + aes.AES_GLOBAL_PMEM) == header | aes.BUS_TAG


def test_rs_fixit_s_global_is_put_on_the_bus():
    result = fresh_run(rs.RS_FIXIT, (DESK | aes.BUS_TAG,), DESK)
    assert_as_the_snapshot_has_it(result, *section(DESK, "object", aes.OB_BYTES, "nobs"), DESK)
    assert result.long(aes.AES_RS_GLOBAL) == DESK | aes.BUS_TAG


def application_load(**shape):
    resource, layout = rs.application_resource(**shape)
    pokes = merge_pokes(resource, rs.application_global(), rs.current(rs.APP_GLOBAL, rs.APP_HEADER))
    return run(rs.DO_RSFIX, (rs.APP_HEADER, layout["rssize"]), pokes), make_image(pokes), layout


def test_an_application_s_icons_bitblks_strings_and_images_are_relocated():
    """Every pointer section do_rsfix passes over: each ICONBLK's mask, data and text, each BITBLK's data, each free
    string and image — an offset before, the header plus it after."""
    result, before, layout = application_load()
    pointers = [layout["iconblk"] + icon * aes.IB_BYTES + field for icon in range(layout["nib"])
                for field in (aes.IB_PMASK, aes.IB_PDATA, aes.IB_PTEXT)]
    pointers += [layout["bitblk"] + blk * aes.BI_BYTES + aes.BI_PDATA for blk in range(layout["nbb"])]
    pointers += [layout["frstr"] + 4 * string for string in range(layout["nstring"])]
    pointers += [layout["frimg"] + 4 * image for image in range(layout["nimages"])]
    for offset in pointers:
        at = rs.APP_HEADER + offset
        assert result.long(at) == case.long_in(before, at) + rs.APP_HEADER, hex(offset)
    assert result.word(rs.APP_GLOBAL + aes.AES_GLOBAL_LMEM) == layout["rssize"]


@pytest.mark.parametrize("shape", ({"icons": 0, "bitblks": 0, "images": 0, "strings": 1}, {"icons": 5, "texts": 4}),
                         ids=("empty sections", "more of each"))
def test_every_section_count_is_honoured(shape):
    result, before, layout = application_load(**shape)
    frstr = rs.APP_HEADER + layout["frstr"]
    for string in range(layout["nstring"]):
        assert result.long(frstr + 4 * string) == case.long_in(before, frstr + 4 * string) + rs.APP_HEADER


# ---- the registry -------------------------------------------------------------------------------------------------
# The worst realistic rows are the ROM's own resources as the start-up relocates them: the desk's is the larger.
for _global in (GEM, DESK):
    _label = f"{IDS[_global]} resource as the ROM holds it"
    aes.register(_label, rs.FIX_TRINDEX, (), aes.leaf_machine(onto=rs.fresh(_global)))
    aes.register(_label, rs.FIX_OBJECTS, (), aes.leaf_machine(onto=rs.fresh(_global)))
    aes.register(_label, rs.FIX_TEDINFO, (), aes.leaf_machine(onto=rs.fresh(_global)))
    aes.register(_label, rs.DO_RSFIX, (HOMES[_global][0], HOMES[_global][2]), aes.leaf_machine(onto=rs.fresh(_global)))
    aes.register(_label, rs.RS_FIXIT, (_global,), aes.leaf_machine(onto=rs.fresh(_global)))
aes.register("an application's resource, icons and all", rs.DO_RSFIX, (rs.APP_HEADER, 0x400),
             aes.leaf_machine(onto=merge_pokes(rs.application_resource()[0], rs.application_global(),
                                               rs.current(rs.APP_GLOBAL, rs.APP_HEADER))))
aes.register("the desk's resource as the ROM holds it", rs.DO_RSFIX, (rs.DESK_HEADER, rs.DESK_PART_BYTES),
             aes.leaf_machine(onto=rs.fresh(DESK)), through_line_f=True)
