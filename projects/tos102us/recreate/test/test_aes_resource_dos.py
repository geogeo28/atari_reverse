"""AES rsrc_free ($feaa58) and rom_rsc_init ($fee4de) — the resource layer's two GEMDOS calls: `src/aes/resource.c` — and
the AES's GEMDOS glue they make them through, dos_alloc ($fe3bba) and dos_free ($fe3c26): `src/aes/gemdosif.c`.

    rs_free(g):       rs_global = g; dos_free(g[7..8]); !DOS_ERR
        dos_free($fe3c26): its caller's return parked in AES_DOS_RETURN, `__DOS`'s own in AES_TRAP1_RETURN;
                           Mfree; DOS_AX = D0.w; DOS_ERR = D0 < 0
    rom_rsc_init():   b = dos_alloc(17218); LBCOPY(b, the ROM's bundle, 17218); the six parts' table from its five
                      offsets; the three resources' flags 1
        dos_alloc($fe3bba): Malloc(n rounded up to even); 0 -> DOS_ERR = 1; the block rounded up to even

Every GEMDOS call is taken by the STAGED recording trap (`vdi_helpers`: the `trap #1` vector pointed at a handler that
appends each call's function and longword to a ledger and answers a staged D0) on the ROM's side, and by its host twin
on ours — so the WHOLE ORDERED CALL LIST is compared, with the parked return sites and DOS_ERR/DOS_AX. The Malloc is
answered with the block the snapshot's own boot got: the copy lands where the snapshot holds it, and the table comes
out as the snapshot's.
"""
import pytest

from harness import BASE_IMAGE, _lib, addrs, emu

import aes
import aes_resource as rs
import case
import routines
import vdi
import vdi_helpers
from case import merge_pokes
from opcodes import DROP_STACK_LONG

RS_FREE = "AES_ROM_RS_FREE"
ROM_RSC_INIT = "AES_ROM_ROM_RSC_INIT"
DOS_ALLOC = "AES_ROM_DOS_ALLOC"
DOS_FREE = "AES_ROM_DOS_FREE"
aes.declare_alcyon(RS_FREE, aes.WORD_ANSWER, (vdi.IMAGE_ARG, vdi.LONG_ARG))
aes.declare_alcyon(ROM_RSC_INIT, None, (vdi.IMAGE_ARG,))
aes.declare_alcyon(DOS_ALLOC, aes.LONG_ANSWER, (vdi.IMAGE_ARG, vdi.LONG_ARG))
# dos_free parks its caller's return address, which no frame carries: the host build is handed it (a host argument).
aes.declare_alcyon(DOS_FREE, aes.LONG_ANSWER, (vdi.IMAGE_ARG, vdi.LONG_ARG, vdi.LONG_ARG), host_arguments=1)

MFREE, MALLOC = addrs.GEMDOS_MFREE_FN, addrs.GEMDOS_MALLOC_FN
DOS_FIELDS = ("DOS_RETURN", "TRAP1_RETURN", "DOS_ERR", "DOS_AX")
for _name in DOS_FIELDS:
    aes.declare_case_field(aes.field("AES", _name)[0], aes.field("AES", _name)[1], "the AES's GEMDOS glue's parking")
STALE_DOS = aes.field_pokes("AES", DOS_RETURN=vdi.STALE_LONG, TRAP1_RETURN=vdi.STALE_LONG, DOS_ERR=aes.STALE_WORD,
                            DOS_AX=aes.STALE_WORD)
GEMDOS_OK = 0
EIMBA = -40 & 0xFFFFFFFF                 # Mfree of a block GEMDOS never handed out


# THE ATTRIBUTION PASS IS OFF (`vdi.READS_A_POINTER_IT_WRITES`) for EVERY case here. The recording trap every case goes
# through reads its ledger's pointer and writes it back, so the pass — which inverts every stored byte first — hands the
# host twin a wild pointer. Unbounded, that store landed in host memory: poisoned runs CRASHED the worker, or corrupted
# it and passed (two false greens under xdist). The twin now refuses it by name (`vdi_helpers.recording_trap_handler`),
# so forced on, all 29 fail cleanly instead — still red, which is why the opt-out stays. What stands in:
# every field the glue parks is staged STALE (`STALE_DOS`), and so are rom_rsc_init's table and flags, so a skipped
# store shows.
def run(name, arguments, pokes, answer, **kwargs):
    staged = merge_pokes(STALE_DOS, pokes, vdi_helpers.staged_gemdos_trap_pokes(answer))
    return rs.run(name, arguments, staged, hook=vdi_helpers.staged_gemdos_hook(answer),
                  **vdi.READS_A_POINTER_IT_WRITES, **kwargs)


# ---- dos_alloc and dos_free, entered directly and through Line-F -----------------------------------------------------
# Every case over the recording trap answering a staged D0, so the whole ordered ledger is compared: the size each asks
# for, and what the glue made of the answer.
def alloc(bytes_, answer, **kwargs):
    return run(DOS_ALLOC, (bytes_,), None, answer, **kwargs)


# (size asked, the block the trap answers, the size Malloc is handed, dos_alloc's answer): the size and the block each
# rounded up to even — a longword sum, so $ffffffff asks for 0 and an odd $ffffffff block answers 0.
ALLOCATIONS = {
    "even, an even block": (0x100, 0x2_0000, 0x100, 0x2_0000),
    "odd, an odd block": (0x101, 0x2_0001, 0x102, 0x2_0002),
    "the bundle's 17218 bytes": (17218, 0x2_0000, 17218, 0x2_0000),
    "all of it ($ffffffff, the size Malloc reports the pool by)": (0xFFFF_FFFF, 0xFFFF_FFFF, 0, 0),
}


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("asked, block, handed, answered", ALLOCATIONS.values(), ids=ALLOCATIONS)
def test_dos_alloc_rounds_the_size_and_the_block_up_to_even(asked, block, handed, answered, through_line_f):
    result = alloc(asked, block, through_line_f=through_line_f)
    assert vdi_helpers.trapped_calls(result.final) == [(MALLOC, handed)]
    assert result.long_answer() == answered
    assert result.field("AES", "DOS_ERR") == aes.STALE_WORD, "a success leaves DOS_ERR as it was"


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_dos_alloc_s_failure_sets_dos_err_and_answers_0(through_line_f):
    """No memory (Malloc answers 0): AES_DOS_ERR := 1, and the 0 answered as it is — the arm rom_rsc_init never
    checks, reached here directly."""
    result = alloc(0x101, 0, through_line_f=through_line_f)
    assert vdi_helpers.trapped_calls(result.final) == [(MALLOC, 0x102)]
    assert (result.long_answer(), result.field("AES", "DOS_ERR")) == (0, 1)


# dos_free's parked return address is the one its caller's `jsr` (or the Line-F handler's return) left: the run's own
# sentinel entered directly, the word after the call word in the Line-F caller.
LINE_F_RETURN_SITE = aes.LINE_F_CALLER_AT + len(DROP_STACK_LONG) + aes.WORD_BYTES


def free(block, answer, *, through_line_f=False):
    return_site = LINE_F_RETURN_SITE if through_line_f else emu.SENTINEL
    machine = aes.staged(DOS_FREE, (block,), aes.leaf_machine(onto=merge_pokes(
        STALE_DOS, vdi_helpers.staged_gemdos_trap_pokes(answer))), through_line_f=through_line_f)
    core = getattr(_lib, routines.core_symbol(DOS_FREE))

    def glue(_lib, buf):
        return core(buf, return_site, block)
    with vdi_helpers.staged_gemdos_hook(answer)() as bound:
        info = case.run(aes.entry_of(DOS_FREE, through_line_f), {"_pokes": machine}, bound.recording(glue),
                        width=case.FULL_D0, dropped_windows=aes.LINE_F_MASK_WINDOW, **vdi.READS_A_POINTER_IT_WRITES)
    return aes.Result(info, machine)


# (the block, what Mfree answers, AES_DOS_ERR): the error is the LONG's sign, AES_DOS_AX its low word.
FREES = {
    "a block GEMDOS took": (0x2_0000, GEMDOS_OK, 0),
    "an odd block, EIMBA": (0x2_0001, EIMBA, 1),
    "a positive long whose word is negative": (0x2_0000, 0x0000_8000, 0),
    "a tagged block": (0x2_0000 | aes.BUS_TAG, GEMDOS_OK, 0),
}


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("block, answer, failed", FREES.values(), ids=FREES)
def test_dos_free_parks_both_returns_and_answers_the_trap(block, answer, failed, through_line_f):
    result = free(block, answer, through_line_f=through_line_f)
    assert vdi_helpers.trapped_calls(result.final) == [(MFREE, block)]
    assert result.long_answer() == answer
    return_site = LINE_F_RETURN_SITE if through_line_f else emu.SENTINEL
    assert [result.field("AES", name) for name in DOS_FIELDS] == [return_site, addrs.AES_DOS_TRAP_RETURN, failed,
                                                                  answer & 0xFFFF]


# ---- rsrc_free ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("global_", (rs.GEM_GLOBAL, rs.DESK_GLOBAL), ids=("the AES's", "the desk's"))
def test_rsrc_free_mfrees_the_header_and_answers_it_went(global_, through_line_f):
    result = run(RS_FREE, (global_,), rs.STALE_GLOBALS, GEMDOS_OK, through_line_f=through_line_f)
    assert vdi_helpers.trapped_calls(result.final) == [(MFREE, rs.header_of(global_))]
    assert result.answer() == 1
    assert [result.field("AES", name) for name in DOS_FIELDS] == [addrs.AES_RS_FREE_MFREE_RETURN,
                                                                  addrs.AES_DOS_TRAP_RETURN, 0, GEMDOS_OK]
    assert result.long(aes.AES_RS_GLOBAL) == global_
    assert result.long(aes.AES_RS_HDR) == case.long_in(rs.STALE_GLOBALS[aes.AES_RS_HDR], 0), "rs_hdr is not touched"


@pytest.mark.parametrize("answer,failed", ((EIMBA, 1), (0x0000_8000, 0), (0x8000_0000, 1), (5, 0)),
                         ids=("EIMBA", "a positive long, its word negative", "the least long", "positive"))
def test_rsrc_free_s_answer_is_the_long_s_sign(answer, failed):
    """DOS_ERR is the LONG's sign (`tst.l d0; bge`) and DOS_AX its low word: $00008000 is no error."""
    result = run(RS_FREE, (rs.GEM_GLOBAL,), None, answer)
    assert (result.field("AES", "DOS_ERR"), result.field("AES", "DOS_AX")) == (failed, answer & 0xFFFF)
    assert result.answer() == 1 - failed


def test_rsrc_free_reads_the_header_through_the_global_just_stored():
    """A global[] pointer with a top byte is stored as it is and read through 24 bits; one laid so that its
    global[7..8] IS AES_RS_GLOBAL frees the global pointer itself."""
    result = run(RS_FREE, (rs.DESK_GLOBAL | aes.BUS_TAG,), None, GEMDOS_OK)
    assert vdi_helpers.trapped_calls(result.final) == [(MFREE, rs.DESK_HEADER)]
    over = aes.AES_RS_GLOBAL - aes.AES_GLOBAL_PMEM
    result = run(RS_FREE, (over,), None, GEMDOS_OK)
    assert vdi_helpers.trapped_calls(result.final) == [(MFREE, over)]


# ---- rom_rsc_init ---------------------------------------------------------------------------------------------------
SNAPSHOT_BUNDLE = case.long_in(BASE_IMAGE, aes.AES_RSC_TABLE) - rs.BUNDLE_OFFSET_COUNT * rs.WORD_BYTES
TABLE_BYTES = rs.ROM_RSC_PARTS * rs.ROM_RSC_ENTRY_BYTES
STALE_TABLE = {aes.AES_RSC_TABLE: bytes([vdi.FILL]) * TABLE_BYTES}
FLAGS = ("RSC_DESK_FRESH", "RSC_FORMAT_FRESH", "RSC_AES_FRESH")
BUNDLE = bytes(BASE_IMAGE[rs.BUNDLE:rs.BUNDLE + rs.AES_RSC_BUNDLE_BYTES])


def model_table(bundle):
    """The six parts `(address, length)` rom_rsc_init records for a copy at `bundle`."""
    offsets = rs.BUNDLE_OFFSETS
    parts = [(bundle + rs.BUNDLE_OFFSET_COUNT * rs.WORD_BYTES, offsets[0] - rs.BUNDLE_OFFSET_COUNT)]
    parts += [(bundle + (offsets[i - 1] & ~1), offsets[i] - offsets[i - 1]) for i in (1, 2, 3)]
    parts += [parts[2], (bundle + (offsets[3] & ~1), offsets[4] - offsets[3])]
    return [(address & 0xFFFFFFFF, length & 0xFFFF) for address, length in parts]


def table_of(image):
    return [(case.long_in(image, aes.AES_RSC_TABLE + part * rs.ROM_RSC_ENTRY_BYTES),
             case.word_in(image, aes.AES_RSC_TABLE + part * rs.ROM_RSC_ENTRY_BYTES + rs.ROM_RSC_BYTES))
            for part in range(rs.ROM_RSC_PARTS)]


# The block the copy lands in, staged FILLed: the snapshot's own copy of the bundle is there, so a copy one byte short
# would otherwise leave the right byte behind.
aes.declare_case_field(SNAPSHOT_BUNDLE, rs.AES_RSC_BUNDLE_BYTES, "the snapshot's copy of the ROM's resource bundle")
STALE_BLOCK = {SNAPSHOT_BUNDLE: bytes([vdi.FILL]) * rs.AES_RSC_BUNDLE_BYTES}


def init(answer, **kwargs):
    pokes = merge_pokes(STALE_BLOCK, STALE_TABLE, aes.field_pokes("AES", **{flag: aes.STALE_WORD for flag in FLAGS}))
    return run(ROM_RSC_INIT, (), pokes, answer, **kwargs)


def test_the_bundle_is_copied_where_the_snapshot_has_it_and_its_table_is_the_snapshot_s():
    """Malloc answered with the block the snapshot's boot got: the ROM's bundle copied over it, byte for byte, the
    six parts' table — staged STALE — as the snapshot holds it, and the three flags 1 (the snapshot's are 2, 0, 1).
    Entered DIRECTLY only: gem_entry calls it by `jsr` ($fd9eca), and no Line-F word names it."""
    result = init(SNAPSHOT_BUNDLE)
    assert vdi_helpers.trapped_calls(result.final) == [(MALLOC, rs.AES_RSC_BUNDLE_BYTES)]
    assert result.after(SNAPSHOT_BUNDLE, len(BUNDLE)) == BUNDLE
    assert table_of(result.final) == table_of(BASE_IMAGE) == model_table(SNAPSHOT_BUNDLE)
    assert [result.field("AES", flag) for flag in FLAGS] == [1, 1, 1]


def test_an_odd_block_is_rounded_up():
    result = init(SNAPSHOT_BUNDLE - 1)
    assert table_of(result.final) == table_of(BASE_IMAGE)
    assert result.field("AES", "DOS_ERR") == aes.STALE_WORD, "a success leaves DOS_ERR as it was"


# NOT PINNED THROUGH rom_rsc_init: a FAILED Malloc — it does not check it, and copies the bundle to address 0: over the
# vector page, the Line-F vector ($2c) included, so its own Line-F return then runs the bundle's bytes on the ROM's side
# (measured: no `rts` in 200,000 instructions). dos_alloc's own failure arm is pinned DIRECTLY above.


# ---- the registry ---------------------------------------------------------------------------------------------------
# dos_alloc's rows: both roundings, neither, and the failure arm — the WORST (1.0993, just under the bar): the C's store
# of DOS_ERR is image-relative, `$98ec` too far for a d16 displacement (46 cycles against the ROM's absolute
# `move.w #1,$98ec`, 20), and no faithful spelling of the C reaches the absolute form. dos_free's C takes the return
# site no frame carries (a host argument), so its cases above are verified and it has no Tier 3 row — priced inside
# rs_free's.
aes.register("an odd size, an odd block", DOS_ALLOC, (0x101,),
             aes.leaf_machine(onto=merge_pokes(STALE_DOS, vdi_helpers.staged_gemdos_trap_pokes(0x2_0001))),
             hook=vdi_helpers.staged_gemdos_hook(0x2_0001))
aes.register("even", DOS_ALLOC, (0x100,),
             aes.leaf_machine(onto=merge_pokes(STALE_DOS, vdi_helpers.staged_gemdos_trap_pokes(0x2_0000))),
             hook=vdi_helpers.staged_gemdos_hook(0x2_0000))
aes.register("no memory", DOS_ALLOC, (0x100,),
             aes.leaf_machine(onto=merge_pokes(STALE_DOS, vdi_helpers.staged_gemdos_trap_pokes(0))),
             hook=vdi_helpers.staged_gemdos_hook(0))
aes.register("the desk's", RS_FREE, (rs.DESK_GLOBAL,),
             aes.leaf_machine(onto=merge_pokes(STALE_DOS, vdi_helpers.staged_gemdos_trap_pokes(GEMDOS_OK))),
             hook=vdi_helpers.staged_gemdos_hook(GEMDOS_OK))
aes.register("the snapshot's own block", ROM_RSC_INIT, (),
             aes.leaf_machine(onto=merge_pokes(STALE_DOS, STALE_TABLE, vdi_helpers.staged_gemdos_trap_pokes(SNAPSHOT_BUNDLE))),
             hook=vdi_helpers.staged_gemdos_hook(SNAPSHOT_BUNDLE))
# ...and dos_free itself, VERIFIED AND UNPRICED at its own entry (the host argument above): swept with the registry
# and listed in the census `test_tier3.UNPRICED_AT_A_ROM_ENTRY` — band 5 wave 1's rule for every such twin.
aes.ROWS.register(f"{routines.core_symbol(DOS_FREE)}, Mfree of a block (a host argument: its caller's return site)",
                  addrs.AES_ROM_DOS_FREE, aes.staged(DOS_FREE, (0x2_0000,), aes.leaf_machine(onto=merge_pokes(
                      STALE_DOS, vdi_helpers.staged_gemdos_trap_pokes(GEMDOS_OK)))), priced=False)
