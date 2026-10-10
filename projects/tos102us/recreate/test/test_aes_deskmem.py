"""THE DESK'S MEMORY (`src/aes/deskmem.c`): size_theglo `$fee800`, desk_alloc `$fee80a` and desk_free `$fee870`.

    size_theglo():  return 5387                       THEGLO's words less one: gem_entry's `dbmi` count
    desk_alloc():   desk globals = dos_alloc(19094), cleared;  three more of 512, 920 and 16000;
                    userdef stack = dos_alloc(1024) + 1024
    desk_free():    dos_free(globals[14206]); dos_free(globals[14202]); desk_rsrc_free() — A YIELD —;
                    userdef stack -= 1024, freed; the 512; the globals; the 920; the 16000

WHAT REACHES EACH TODAY:
  * size_theglo reads nothing and stores nothing: any machine. gem_entry's own call (`$fd9f72`) is OWED on the
    pre-init machine.
  * desk_alloc and desk_free run round the desk, in sh_main (`$feb1da`, `$feb1e8`): desk_alloc before the snapshot's
    desk started, desk_free only once the desk RETURNS (which no run reaches yet). Here:
      - desk_alloc over the post-boot machine with GEMDOS SCRIPTED (the blocks answered are free RAM of the snapshot)
        and over REAL GEMDOS — the ROM's glue into the ROM's Malloc, ours into the reconstructed memory manager — on
        a machine whose desk is still up: the blocks are then five MORE of the TPA. A labelled ARGUMENT CLASS (no
        ROM caller calls it with the desk's blocks standing); OWED on sh_main's own machine.
      - desk_free over THE RUNNING DESK'S OWN BLOCKS — the pointers the snapshot holds, the two in the desk's globals
        written by the desk itself — with GEMDOS scripted, so the ledger says which block each call frees and
        nothing of the running desk is really given back. It leaves by the dispatcher (the binding's yield): a row
        that switches. OWED: the desk's own return (sh_main `$feb1e8`), on a machine where deskmain returns.
"""
import functools

import pytest

from harness import BASE_IMAGE, addrs, emu, make_image

import aes
import aes_event
import aes_gemdosif as gd
import aes_resource as rs
import aes_switching as switching
import case
import gemdos_fs
import vdi
from case import merge_pokes

SIZE_THEGLO, DESK_ALLOC, DESK_FREE = "AES_ROM_SIZE_THEGLO", "AES_ROM_DESK_ALLOC", "AES_ROM_DESK_FREE"
aes.declare_alcyon(SIZE_THEGLO, aes.WORD_ANSWER, ())
aes.declare_alcyon(DESK_ALLOC, None, (vdi.IMAGE_ARG,))
aes.declare_alcyon(DESK_FREE, None, (vdi.IMAGE_ARG,))
MEM = aes.header_constants("deskmem.h")
THROUGH = pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
MALLOC, MFREE = gd.MALLOC, gd.MFREE
SHELL = aes.SHELL_PD
Premise, Priced = switching.Premise, switching.Priced
BENCH, SHIPPED = "bench", "bench_shipped"
ARGUMENT_CLASS = "ARGUMENT CLASS (the desk's blocks still standing)"
GLOBALS, BLOCK_512, BLOCK_920, BLOCK_16000, USERDEF_STACK = (
    aes.AES_DESK_GLOBALS, MEM["AES_DESK_BLOCK_512"], MEM["AES_DESK_BLOCK_920"], MEM["AES_DESK_BLOCK_16000"],
    aes.AES_USERDEF_STACK)
POINTERS = (GLOBALS, BLOCK_512, BLOCK_920, BLOCK_16000, USERDEF_STACK)      # in desk_alloc's order
SIZES = (MEM["DESK_GLOBALS_BYTES"], MEM["DESK_BLOCK_512_BYTES"], MEM["DESK_BLOCK_920_BYTES"],
         MEM["DESK_BLOCK_16000_BYTES"], MEM["USERDEF_STACK_BYTES"])
for _at in POINTERS:
    aes.declare_case_field(_at, aes.LONG_BYTES, "a block of the desk's memory")


# ---- size_theglo -------------------------------------------------------------------------------------------------------
def test_size_theglo_answers_theglo_s_words_less_one():
    """Called by `jsr` (gem_entry `$fd9f72`; no Line-F word names it). 5387: the clear that follows stores D0 + 1
    words from THEGLO up (`move.w d1,(a0)+ / dbmi d0`), every byte of it."""
    result = aes.run_function(SIZE_THEGLO, (), aes.leaf_machine())
    assert result.answer() == aes.AES_THEGLO_WORDS - 1 == 5387
    assert aes.stored_nothing(result)
    assert not aes.line_f_call_sites(SIZE_THEGLO)


# ---- desk_alloc ---------------------------------------------------------------------------------------------------------
# THE BLOCKS THE SCRIPT ANSWERS: free RAM of the snapshot (held so below), the globals' staged FILLed — with a byte
# past it — so the clear shows, and how far.
# (Above Tier 3's blob, below the staged RAM disk — `test_the_scripted_blocks_are_free_ram_of_the_snapshot`. Only the
# globals' block is ever written; the other four are addresses desk_alloc keeps and never follows.)
ARENA = 0x60000
BLOCKS = (ARENA, ARENA + 0x4C00, ARENA + 0x4E00, ARENA + 0x5200, ARENA + 0x5600)
ARENA_END = BLOCKS[-1] + 0x400
GLOBALS_FILL = 0x5C
FILLED_GLOBALS = {ARENA: bytes([GLOBALS_FILL]) * (SIZES[0] + 2)}
STALE_POINTERS = {at: vdi.STALE_LONG.to_bytes(aes.LONG_BYTES, "big") for at in POINTERS}


def test_the_scripted_blocks_are_free_ram_of_the_snapshot():
    assert not any(BASE_IMAGE[ARENA:ARENA_END])
    assert BLOCKS[0] + SIZES[0] + 2 <= BLOCKS[1] and list(BLOCKS) == sorted(BLOCKS) and not any(block & 1 for block in BLOCKS)
    assert ARENA_END <= gemdos_fs.IMAGE_AT, "below the staged RAM disk"


def alloc(answers=BLOCKS, **kwargs):
    return gd.run_scripted(DESK_ALLOC, (), answers, merge_pokes(STALE_POINTERS, FILLED_GLOBALS), **kwargs)


def test_desk_alloc_over_five_blocks_returns__held_in_a_child():
    """FIRST, AND IN A CHILD: a twin that halted where every block is granted (its refusal of a refused first block
    turned round) would bring the suite down with no verdict. Here it is a child that did not return."""
    machine = gd.scripted_machine(BLOCKS, merge_pokes(STALE_POINTERS, FILLED_GLOBALS))
    returncode, stderr, image = aes_event.refusal(DESK_ALLOC, machine, (), bind=gd.FRESH_CHILD_DOORS)
    assert returncode == 0 and len(gd.calls(image)) == len(SIZES), stderr


@THROUGH
def test_desk_alloc_asks_for_its_five_blocks_in_order_and_keeps_each(through_line_f):
    """Five Mallocs — 19094, 512, 920, 16000, 1024 bytes — each block kept in its own longword, the userdef stack's
    as its TOP (the block + 1024); the globals, and only the globals, cleared: 19094 bytes, not one more."""
    result = alloc(through_line_f=through_line_f)
    assert gd.calls(result.final) == [gd.call(MALLOC, ("l", size)) for size in SIZES]
    assert [result.long(at) for at in POINTERS] == [*BLOCKS[:4], BLOCKS[4] + SIZES[4]]
    assert result.after(ARENA, SIZES[0]) == bytes(SIZES[0])
    assert result.after(ARENA + SIZES[0], 2) == bytes([GLOBALS_FILL]) * 2
    assert result.field("AES", "DOS_ERR") == aes.STALE_WORD, "a success leaves DOS_ERR as it was"


def test_an_odd_block_is_rounded_up_before_it_is_kept():
    """dos_alloc's rounding reaches each pointer: an odd block from Malloc is kept as the even address above it —
    and the userdef stack's top is 1024 above THAT."""
    odd = (*BLOCKS[:1], BLOCKS[1] + 1, BLOCKS[2], BLOCKS[3] + 1, BLOCKS[4] + 1)
    result = alloc(odd)
    assert [result.long(at) for at in POINTERS] == [BLOCKS[0], BLOCKS[1] + 2, BLOCKS[2], BLOCKS[3] + 2, BLOCKS[4] + 2 + SIZES[4]]


def test_the_userdef_stack_s_top_is_a_longword_sum_of_whatever_malloc_answered():
    """ARGUMENT CLASS (a scripted Malloc answering an address with a top byte: no GEMDOS of a 24-bit machine does).
    `addi.l #1024,$8c3a`: the top is the block's whole longword plus 1024 — no bus mask."""
    tagged = BLOCKS[4] | aes.BUS_TAG
    assert alloc((*BLOCKS[:4], tagged)).long(USERDEF_STACK) == tagged + SIZES[4]


@pytest.mark.parametrize("refused", (1, 2, 3, 4), ids=("the 512", "the 920", "the 16000", "the userdef stack"))
def test_a_block_malloc_refuses_is_kept_as_null_and_nothing_is_checked(refused):
    """A ROM BEHAVIOUR, KEPT: no answer is tested. A refused block is stored as the NULL it is (dos_alloc sets
    AES_DOS_ERR) and desk_alloc goes on to the next — a refused userdef stack is kept as a TOP of $400, in the
    vector page. (A refused FIRST block is another matter: the two tests below.)"""
    answers = tuple(0 if index == refused else block for index, block in enumerate(BLOCKS))
    result = alloc(answers)
    kept = [result.long(at) for at in POINTERS]
    expected = [*answers[:4], answers[4] + SIZES[4]]
    assert kept == expected and len(gd.calls(result.final)) == len(SIZES)
    assert result.field("AES", "DOS_ERR") == 1


REFUSED_FIRST = (0, *BLOCKS[1:])
SPIN_INSNS = 400_000                    # past the 19,094-byte clear and the four calls a run that returned would make


def test_the_rom_s_desk_alloc_never_returns_from_a_refused_first_block():
    """A ROM BEHAVIOUR, PINNED AS IT IS: the globals' pointer NULL, the clear runs over the vector page — `trap #1`'s
    vector with it — and the next Malloc traps to address 0. The ROM's own run does not reach its `rts`."""
    staged = aes.staged(DESK_ALLOC, (), gd.scripted_machine(REFUSED_FIRST, merge_pokes(STALE_POINTERS, FILLED_GLOBALS)))
    with pytest.raises(RuntimeError, match="did not reach rts"):
        emu.run(make_image(staged), addrs.AES_ROM_DESK_ALLOC, {}, max_insns=SPIN_INSNS)
    # ...and the trap it is lost in is the SECOND Malloc's: the vector is one of the bytes the clear zeroes
    assert addrs.VECTOR_TRAP_GEMDOS + aes.LONG_BYTES <= SIZES[0]


def test_the_twin_refuses_a_refused_first_block_by_name():
    """...so the host twin, whose image takes no vector, HALTS BY NAME there rather than return with the page
    zeroed — an outcome the machine does not have (F1). In a child, the scripted GEMDOS bound."""
    machine = gd.scripted_machine(REFUSED_FIRST, merge_pokes(STALE_POINTERS, FILLED_GLOBALS))
    returncode, stderr, image = aes_event.refusal(DESK_ALLOC, machine, (), bind=gd.FRESH_CHILD_DOORS)
    assert returncode != 0 and "desk_alloc" in stderr and "never returns" in stderr, stderr
    assert gd.calls(image) == [gd.call(MALLOC, ("l", SIZES[0]))], "halted after the one Malloc, before the clear"
    vectors = addrs.VECTOR_TRAP_GEMDOS + aes.LONG_BYTES
    assert bytes(image[:vectors]) == bytes(make_image(machine)[:vectors]), "the vector page as staged: nothing cleared"


def test_desk_alloc_through_real_gemdos_takes_five_more_blocks_of_the_tpa():
    """ARGUMENT CLASS (the desk's own blocks still standing). The ROM's glue into the ROM's Malloc, ours into the
    reconstructed memory manager: five blocks of the captured machine's free memory, each where GEMDOS put it (its
    own records compared whole), none of them one of the running desk's, the first cleared."""
    result = gd.run_real(DESK_ALLOC, (), STALE_POINTERS)
    kept = [result.long(at) for at in POINTERS]
    standing = {case.long_in(BASE_IMAGE, at) for at in POINTERS}
    assert all(kept) and not set(kept) & standing and len(set(kept)) == len(kept)
    assert result.after(kept[0], SIZES[0]) == bytes(SIZES[0])
    assert kept[4] - SIZES[4] > kept[3], "the userdef stack's block lies past the 16000's: what is kept is its top"


# ---- desk_free: a row that switches -------------------------------------------------------------------------------------
# THE RUNNING DESK'S OWN BLOCKS, as the snapshot holds them: desk_alloc's five pointers, and the two the desk wrote
# into its globals.
DESK = case.long_in(BASE_IMAGE, GLOBALS)
FIRST_FREED = case.long_in(BASE_IMAGE, DESK + MEM["DESK_G_FIRST_FREED"])
SECOND_FREED = case.long_in(BASE_IMAGE, DESK + MEM["DESK_G_SECOND_FREED"])
SNAPSHOT_STACK_TOP = case.long_in(BASE_IMAGE, USERDEF_STACK)
# What desk_free frees, in its order.
FREED_IN_ORDER = (FIRST_FREED, SECOND_FREED, rs.DESK_HEADER, SNAPSHOT_STACK_TOP - SIZES[4],
                  case.long_in(BASE_IMAGE, BLOCK_512), DESK, case.long_in(BASE_IMAGE, BLOCK_920),
                  case.long_in(BASE_IMAGE, BLOCK_16000))
RETURN_SITES = (addrs.AES_DESK_FREE_FIRST_RETURN, addrs.AES_DESK_FREE_SECOND_RETURN, addrs.AES_RS_FREE_MFREE_RETURN,
                addrs.AES_DESK_FREE_STACK_RETURN, addrs.AES_DESK_FREE_C82E_RETURN, addrs.AES_DESK_FREE_GLOBALS_RETURN,
                addrs.AES_DESK_FREE_C85E_RETURN, addrs.AES_DESK_FREE_C67A_RETURN)
GEMDOS_OK, EIMBA = 0, -40 & aes.LONG_MASK
ALL_FREED = "the running desk's eight blocks freed in order, a yield after the resource's"
ALL_REFUSED = "GEMDOS refuses every block (EIMBA): the same eight calls, the same yield"


def _desk_running(answer):
    return functools.cache(lambda: gd.scripted_over(aes_event.machine(), [answer] * len(FREED_IN_ORDER)))


def _row(label, answer):
    """A row that switches and traps: no door user (it makes no door call) — its Tier 1 fork binds the scripted
    GEMDOS by the row's own `child_doors`."""
    return switching.SwitchingRow(label, DESK_FREE, (), _desk_running(answer), {}, answered=False, child_doors=gd.CHILD_DOORS,
                                  x_flag_differs=answer == GEMDOS_OK)


ROWS = {ALL_FREED: _row(ALL_FREED, GEMDOS_OK), ALL_REFUSED: _row(ALL_REFUSED, EIMBA)}
PREMISES = {label: Premise((), 0, SHELL, (SHELL,), None) for label in ROWS}
# BOTH ROWS ARE REGISTERED (`aes_switching.register_row`). The row where GEMDOS frees the blocks DECLARES ITS X FLAG
# (`aes_switching.THE_X_FLAG_ALONE`): the yield inside the desk's rsrc_free binding follows GCC's `seq` / `neg` over
# rs_free's answer (`test_aes_deskleaf.py` has the three REDs of the declaration).
REGISTERED = {switching.row_name(row): row for row in map(switching.register_row, ROWS.values())}
# @PINS-BEGIN (measured: scratch `b5/H/pins.py`)
WHOLE_RUN = {
    "the running desk's eight blocks freed in order, a yield after the resource's":
        {BENCH: (19440, 17232), SHIPPED: (19440, 17352)},
    'GEMDOS refuses every block (EIMBA): the same eight calls, the same yield':
        {BENCH: (19464, 17230), SHIPPED: (19464, 17350)},
}
PRICED = {
    "the running desk's eight blocks freed in order, a yield after the resource's":
        Priced((6938, 9302), None, None, (0, 0, 0)),   # 0.75
    'GEMDOS refuses every block (EIMBA): the same eight calls, the same yield':
        Priced((6936, 9326), None, None, (0, 0, 0)),   # 0.74
}
# @PINS-END


def test_the_snapshot_holds_the_blocks_desk_alloc_left_and_the_desk_s_own_two():
    """THE ROM-RUN STATE desk_free is run over: five pointers the boot's desk_alloc stored — every one even, in the
    TPA, the userdef stack's a TOP (1024 above a block) — and two blocks the desk itself named in its globals."""
    image = make_image(_desk_running(GEMDOS_OK)())
    assert all(case.long_in(image, at) == case.long_in(BASE_IMAGE, at) for at in POINTERS)
    assert all(block and not block & 1 and block < addrs.ST_RAM_BYTES for block in FREED_IN_ORDER)
    assert len(set(FREED_IN_ORDER)) == len(FREED_IN_ORDER) == 8


@pytest.mark.parametrize("label", ROWS)
def test_the_rom_s_own_run_frees_the_eight_blocks_in_its_order(label):
    """THE PREMISE: eight Mfrees — the desk's two, the desk's resource (inside the binding, before its yield), the
    userdef stack by its block's START (the kept top taken back by 1024, IN MEMORY: the longword is left holding
    the start), the 512, the globals, the 920, the 16000 — the desk resumed once; the globals' pointer and the
    others left as they were (nothing is cleared)."""
    the_rom_s = switching.vet_the_premise(ROWS[label], PREMISES[label])
    assert gd.calls(the_rom_s.memory) == [gd.call(MFREE, ("l", block)) for block in FREED_IN_ORDER]
    assert case.long_in(the_rom_s.memory, USERDEF_STACK) == SNAPSHOT_STACK_TOP - SIZES[4]
    assert all(case.long_in(the_rom_s.memory, at) == case.long_in(BASE_IMAGE, at) for at in POINTERS[:4])
    assert case.long_in(the_rom_s.memory, aes.AES_DOS_RETURN) == RETURN_SITES[-1]


@pytest.mark.parametrize("label", ROWS)
def test_desk_free_taken_through_the_host_s_scheduler_is_the_rom_s(label):
    """TIER 1 (`aes_switching.companion`, nothing dropped; the scripted trap bound in the same child): the same
    eight ledger entries, the userdef stack's longword, the last return site parked, every byte outside the run's
    own stack the ROM's."""
    ran = switching.companion(ROWS[label])
    assert ran.entered == (SHELL,)
    assert gd.calls(ran.image) == [gd.call(MFREE, ("l", block)) for block in FREED_IN_ORDER]
    assert gd.sites_parked_at(ran.image) == [(site, addrs.AES_DOS_TRAP_RETURN) for site in RETURN_SITES], (
        "each free parks ITS OWN site before it traps — the ledger holds all eight, the image only the last")


def test_a_block_the_desk_named_is_freed_as_its_globals_hold_it_odd_or_not():
    """ARGUMENT CLASS (the desk's second pointer staged ODD in its globals: the running desk's own are even, as
    every block Malloc answers is). desk_free hands Mfree the longword as it reads it — nothing rounds it — on both
    shores, through the host's scheduler."""
    odd = SECOND_FREED | 1
    staged = {DESK + MEM["DESK_G_SECOND_FREED"]: odd.to_bytes(aes.LONG_BYTES, "big")}
    row = switching.SwitchingRow("ARGUMENT CLASS: the desk's second block odd", DESK_FREE, (),
                                 functools.cache(lambda: merge_pokes(_desk_running(GEMDOS_OK)(), staged)), {},
                                 answered=False, child_doors=gd.CHILD_DOORS)
    ran = switching.companion(row)
    assert gd.calls(ran.image)[:2] == [gd.call(MFREE, ("l", FIRST_FREED)), gd.call(MFREE, ("l", odd))]


@pytest.mark.parametrize("nth", range(len(RETURN_SITES)))
def test_each_free_parks_its_own_return_site(nth):
    """THE EIGHT SITES, which the run's end shows only the last of: the ROM's own run stopped where its `nth` free
    comes back holds, in AES_DOS_RETURN, that very site — desk_free's seven, and rs_free's own for the resource —
    and the ledger the `nth + 1` frees made so far."""
    from harness import emu
    row = ROWS[ALL_FREED]
    final, _writes, _regs = emu.run(make_image(switching._staged(row)), switching._entry(row), {}, stop_pc=RETURN_SITES[nth])
    assert case.long_in(final, aes.AES_DOS_RETURN) == RETURN_SITES[nth]
    assert gd.calls(final) == [gd.call(MFREE, ("l", block)) for block in FREED_IN_ORDER[:nth + 1]]


def test_every_row_is_registered_and_pinned():
    assert set(REGISTERED) <= set(aes_event.SWITCHING_ROWS)
    assert ROWS.keys() == WHOLE_RUN.keys() == PRICED.keys()
    assert not any(aes_event.SWITCHING_ROWS[name].row.door for name in REGISTERED), "no door user: it makes no door call"


def test_the_two_shores_differ_in_the_x_flag_alone_where_the_blocks_are_freed(blob):
    """THE MEASUREMENT the freed row's declaration stands on: with nothing declared it is refused at `$8995` alone,
    `$00 -> $10`; the refused row declares nothing and its byte is equal (its blob vet, below)."""
    assert [row.x_flag_differs for row in ROWS.values()] == [True, False]
    with pytest.raises(AssertionError, match=r"1 byte\(s\), first 0x8995 \(0x00 -> 0x10\)"):
        switching.measured_on(blob, ROWS[ALL_FREED]._replace(x_flag_differs=False))


@pytest.mark.parametrize("label", ROWS)
def test_a_row_really_switches_on_both_blobs(label, blob):
    """THE SECOND DIFFERENTIAL OF THE REAL SWITCH, whole: the image, the answer, the registers back after the wake,
    the idles and the cycles pinned — the arm where GEMDOS freed the block among them."""
    switching.vet_on_a_blob(blob, ROWS[label], PREMISES[label], switching.NO_WINDOW, WHOLE_RUN[label])


@pytest.mark.parametrize("label", ROWS)
def test_the_table_prices_a_row(label):
    switching.vet_the_table_s_price(ROWS[label], PRICED[label])


# ---- the registry -----------------------------------------------------------------------------------------------------------
aes.register("5387", SIZE_THEGLO, (), aes.leaf_machine())
gd.register_scripted("five blocks", DESK_ALLOC, (), BLOCKS, merge_pokes(STALE_POINTERS, FILLED_GLOBALS))
gd.register_scripted("the userdef stack refused", DESK_ALLOC, (), (*BLOCKS[:4], 0), merge_pokes(STALE_POINTERS, FILLED_GLOBALS))
