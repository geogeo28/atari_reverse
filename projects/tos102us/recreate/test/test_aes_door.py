"""The AES door's own claims (`test/aes.py`), and the facts `include/aes/*.h` and the addrs.h AES block state about
THIS ROM and THIS snapshot — held against both rather than trusted, so a header that drifts reddens here instead of
inside some function's differential.
"""
import pytest

from harness import BASE_IMAGE, addrs, emu

import aes
import case
import gemdos_fs
import staging
import vdi
from isr import long_in_snapshot, word_in_snapshot
from opcodes import CMP_L_IMMEDIATE_D0, JSR_ABSOLUTE_LONG, LINE_F, MOVEA_L_IMMEDIATE_A0, PUSH_LONG_IMMEDIATE

LINEF_RETURN_MOVEM = 0x4CDF          # movem.l (sp)+,<mask>: the word whose mask the handler patches
LEA_PC_RELATIVE_A0 = 0x41FA          # lea <d16>(pc),a0: how the handler finds that word
SIGN_BIT_OF_A_SHORT_ADDRESS = 0x8000  # `pea (xxx).w` sign-extends an address from this bit up


# ---- the window --------------------------------------------------------------------------------------------------

def test_the_window_is_dead_ram_in_this_snapshot():
    window = bytes(BASE_IMAGE[aes.WINDOW_AT:aes.WINDOW_AT + aes.WINDOW_BYTES])
    assert window == bytes(len(window))


def test_the_window_is_clear_of_every_other_tenant():
    """Above the case band, the file system's window and the VDI's, below the oracle's stack guard."""
    assert staging.SCRATCH + staging.SCRATCH_BYTES <= aes.WINDOW_AT
    assert gemdos_fs.SPAN.hi <= aes.WINDOW_AT
    assert vdi.WINDOW_AT + vdi.WINDOW_BYTES <= aes.WINDOW_AT
    assert aes.WINDOW_AT + aes.WINDOW_BYTES <= emu.STACK_GUARD_LO


# ---- the fields ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("record", sorted(aes.RECORD_BYTES))
def test_every_field_lies_inside_its_record(record):
    size = aes.RECORD_BYTES[record]
    assert aes.FIELDS[record], f"{record} has no tagged field"
    for name, spec in aes.FIELDS[record].items():
        assert spec.at + spec.width * (spec.count or 1) <= size, f"{record}_{name} runs past the record"


@pytest.mark.parametrize("record,name", (("OB", "BYTES"), ("OB", "NIL"), ("AES", "THEGLO"), ("AES", "PD_TABLE"),
                                         ("AES", "LINEF_TABLE"), ("PD", "BYTES"), ("OB", "NO_SUCH")))
def test_a_name_that_is_not_a_field_is_refused(record, name):
    with pytest.raises(KeyError, match=f"{record}_{name}"):
        aes.field_pokes(record, aes.TREE_AT, **{name: 0})


def test_a_value_wider_than_its_field_is_refused():
    with pytest.raises(ValueError, match="OB_X"):
        aes.object_pokes(aes.TREE_AT, 0, X=0x1_0000)


def test_a_poke_running_out_of_its_band_is_refused():
    with pytest.raises(AssertionError, match="not inside one band"):
        aes.field_pokes("PD", aes.RECTS_AT + aes.RECTS_BYTES - aes.WORD_BYTES - aes.PD_NAME, NAME=bytes(aes.PD_NAME_BYTES))


# ---- THEGLO, as gem_main carves it: each table's offset and stride read out of the instruction the header cites ----
CITED_IMMEDIATES = (
    # (the address of the immediate in the ROM, its width, the value the header derives from it)
    (0xfda06c, vdi.LONG_BYTES, aes.AES_THEGLO),
    (0xfee806, vdi.WORD_BYTES, aes.AES_THEGLO_WORDS - 1),
    (0xfd9fb4, vdi.LONG_BYTES, aes.AES_UDA1 - aes.AES_THEGLO),
    (0xfda15a, vdi.WORD_BYTES, aes.AES_UDA1 - aes.AES_THEGLO),
    (0xfda162, vdi.WORD_BYTES, aes.AES_UDA2 - aes.AES_THEGLO),
    (0xfda16a, vdi.WORD_BYTES, aes.AES_UDA1_STACK_TOP - aes.AES_THEGLO),
    (0xfda172, vdi.WORD_BYTES, aes.AES_UDA2_STACK_TOP - aes.AES_THEGLO),
    (0xfda144, vdi.LONG_BYTES, aes.AES_PD_TABLE - aes.AES_THEGLO),
    (0xfda13c, vdi.WORD_BYTES, aes.PD_BYTES),
    (0xfda150, vdi.WORD_BYTES, aes.AES_PD_COUNT),
    (0xfda132, vdi.LONG_BYTES, aes.AES_CDA_TABLE - aes.AES_THEGLO),
    (0xfda12a, vdi.WORD_BYTES, aes.CDA_BYTES),
    (0xfda0c2, vdi.LONG_BYTES, aes.AES_EVB_TABLE - aes.AES_THEGLO),
    (0xfda0aa, vdi.WORD_BYTES, aes.EVB_BYTES),
    (0xfda0d0, vdi.WORD_BYTES, aes.AES_EVB_COUNT),
    (0xfe4b40, vdi.LONG_BYTES, aes.AES_FORK_QUEUE - aes.AES_THEGLO),
    (0xfe4b4c, vdi.WORD_BYTES, aes.AES_FORK_ENTRIES),
    (0xfe5a98, vdi.LONG_BYTES, aes.AES_ORECT_POOL - aes.AES_THEGLO),
    (0xfe5a78, vdi.WORD_BYTES, aes.ORECT_BYTES),
    (0xfe5aa6, vdi.WORD_BYTES, aes.AES_ORECT_COUNT),
    (0xfeb494, vdi.LONG_BYTES, aes.AES_WINDOWS - aes.AES_THEGLO),
    (0xfeb488, vdi.WORD_BYTES, aes.WIN_BYTES),
    (0xfea5a8, vdi.WORD_BYTES, aes.OB_BYTES),
    (0xfd9f38, vdi.LONG_BYTES, aes.LINEF_COPY_BYTES),
    (0xfd9f48, vdi.WORD_BYTES, aes.LINEF_COPY_WORDS - 1),
)


@pytest.mark.parametrize("at,width,value", CITED_IMMEDIATES, ids=[f"${at:x}" for at, _w, _v in CITED_IMMEDIATES])
def test_a_table_s_place_and_stride_are_the_rom_s_immediate(at, width, value):
    immediate = long_in_snapshot(at) if width == vdi.LONG_BYTES else word_in_snapshot(at)
    assert immediate == value


def test_the_tables_tile_theglo_and_the_windows_end_inside_its_clear():
    """The three UDAs, then PDs, CDAs, EVBs, the fork queue and the ORECT pool back to back; each UDA's stack top 4
    bytes below what follows it; the windows' eight records inside the words gem_main clears."""
    stack_gap = vdi.LONG_BYTES
    assert aes.AES_UDA1_STACK_TOP + stack_gap == aes.AES_UDA2 and aes.AES_UDA2_STACK_TOP + stack_gap == aes.AES_PD_TABLE
    assert aes.AES_PD_TABLE + aes.AES_PD_COUNT * aes.PD_BYTES == aes.AES_CDA_TABLE
    assert aes.AES_CDA_TABLE + aes.AES_PD_COUNT * aes.CDA_BYTES == aes.AES_EVB_TABLE
    assert aes.AES_EVB_TABLE + aes.AES_EVB_COUNT * aes.EVB_BYTES == aes.AES_FORK_QUEUE
    assert aes.AES_FORK_QUEUE + aes.AES_FORK_ENTRIES * aes.FORK_ENTRY_BYTES == aes.AES_ORECT_POOL
    assert aes.AES_WINDOWS + aes.AES_WINDOW_COUNT * aes.WIN_BYTES <= aes.AES_THEGLO + aes.AES_THEGLO_WORDS * vdi.WORD_BYTES
    assert aes.PD_QUEUE + aes.PD_QUEUE_BYTES == aes.PD_BYTES
    assert aes.UDA_REGS + aes.UDA_REG_COUNT * vdi.LONG_BYTES == aes.UDA_A6


# ---- the snapshot's scheduler state, which every case stages over -------------------------------------------------

def test_the_snapshot_is_inside_the_dispatcher_s_idle_loop():
    """Nothing running, the guard set, both processes waiting — PD0 the shell, PD1 the screen manager — nothing woken
    and nothing forked."""
    assert long_in_snapshot(aes.AES_RLR) == aes.SNAPSHOT_RLR
    assert BASE_IMAGE[aes.AES_INDISP] == aes.AES_INDISP_SET
    assert tuple(aes.list_of(BASE_IMAGE, aes.AES_NRL)) == aes.SNAPSHOT_NOT_READY
    assert aes.list_of(BASE_IMAGE, aes.AES_DRL) == []
    assert word_in_snapshot(aes.AES_FORK_COUNT) == 0
    assert bytes(BASE_IMAGE[aes.SCREEN_MANAGER_PD + aes.PD_NAME:][:aes.PD_NAME_BYTES]) == b"SCRENMGR"
    for index, pd in enumerate(aes.SNAPSHOT_NOT_READY):
        assert aes.read_field(BASE_IMAGE, "PD", "PID", pd) == index
        assert aes.read_field(BASE_IMAGE, "PD", "STAT", pd) == aes.PD_STAT_WAITING
        assert aes.read_field(BASE_IMAGE, "PD", "UDA", pd) == (aes.AES_THEGLO, aes.AES_UDA1)[index]


def test_the_leaf_machine_stages_the_shell_running_over_the_snapshot_s_guard():
    assert aes.leaf_machine() == {aes.AES_RLR: aes.SHELL_PD.to_bytes(vdi.LONG_BYTES, "big"),
                                  aes.AES_INDISP: bytes([aes.AES_INDISP_SET])}


# ---- Line-F: the vector, the RAM copy and the word it patches ---------------------------------------------------

def test_line_f_points_at_the_ram_copy_of_the_rom_handler():
    """$2c names the copy, and the copy is the ROM's 100 bytes but for the one word every masked return rewrites."""
    assert long_in_snapshot(addrs.VECTOR_LINE_F) == aes.AES_LINEF_COPY
    copy = bytes(BASE_IMAGE[aes.AES_LINEF_COPY:aes.AES_LINEF_COPY + aes.LINEF_COPY_BYTES])
    rom = bytes(BASE_IMAGE[addrs.AES_ROM_LINEF_HANDLER:addrs.AES_ROM_LINEF_HANDLER + aes.LINEF_COPY_BYTES])
    mask = aes.LINEF_MASK_OFFSET
    assert copy[:mask] == rom[:mask] and copy[mask + vdi.WORD_BYTES:] == rom[mask + vdi.WORD_BYTES:]
    assert aes.SNAPSHOT_MASK_WORD == case.word_in(copy, mask)


def test_the_mask_word_is_the_one_the_handler_s_lea_names():
    """`lea mask(pc),a0` before the patch: its target is the movem's mask word, at the header's offset."""
    lea = next(at for at in range(addrs.AES_ROM_LINEF_HANDLER, addrs.AES_ROM_LINEF_HANDLER + aes.LINEF_COPY_BYTES, 2)
               if word_in_snapshot(at) == LEA_PC_RELATIVE_A0)
    target = lea + vdi.WORD_BYTES + aes.signed(word_in_snapshot(lea + vdi.WORD_BYTES))
    assert target == addrs.AES_ROM_LINEF_HANDLER + aes.LINEF_MASK_OFFSET
    assert word_in_snapshot(target - vdi.WORD_BYTES) == LINEF_RETURN_MOVEM
    assert aes.AES_LINEF_MASK_WORD == aes.AES_LINEF_COPY + aes.LINEF_MASK_OFFSET


def test_the_call_table_ends_where_the_header_says():
    """Its last entry is code; the longword after it is not an address in the ROM."""
    last = aes.AES_LINEF_TABLE + (aes.AES_LINEF_TABLE_ENTRIES - 1) * vdi.LONG_BYTES
    assert addrs.GEM_TRAP2 <= long_in_snapshot(last) < aes.AES_LINEF_TABLE
    assert not addrs.GEM_TRAP2 <= long_in_snapshot(last + vdi.LONG_BYTES) < aes.AES_LINEF_TABLE


# ob_offset's two call words and every site of each, read out of the GEM text: $f208 at the desk's binding and three
# AES callers (the dispatcher's arm 44 among them), $f154 at the object library's own three (ob_find, ob_change).
OB_OFFSET_CALL_SITES = {0xF208: (0xFDE278, 0xFE47B2, 0xFE609C, 0xFE802C),
                        0xF154: (0xFEA070, 0xFEA404, 0xFEA506)}


def test_ob_offset_s_call_word_is_the_one_most_of_its_callers_use():
    """$f208, four callers to $f154's three — both words reach the same code by the same handler path."""
    assert aes.line_f_call_sites("AES_ROM_OB_OFFSET") == OB_OFFSET_CALL_SITES
    assert aes.line_f_call_word("AES_ROM_OB_OFFSET") == 0xF208
    assert all(word & ~aes.LINEF_OFFSET_MASK == LINE_F for word in OB_OFFSET_CALL_SITES)


# ---- the dispatcher's table, and every `_OPCODE` the addrs.h AES block pairs a routine with ---------------------------
def arm_of(opcode):
    return long_in_snapshot(addrs.AES_OPCODE_TABLE + (opcode - addrs.AES_OPCODE_FIRST) * vdi.LONG_BYTES)


ARMS = sorted({arm_of(opcode) for opcode in range(addrs.AES_OPCODE_FIRST, addrs.AES_OPCODE_LAST + 1)})
# The first tst.w of the arms' shared ladder, where the last arm's span ends.
LADDER = 0xfe64d2


def arm_span(opcode):
    arm = arm_of(opcode)
    return arm, min([start for start in ARMS if start > arm] + [LADDER])


def calls_in(lo, hi):
    """Every routine a span Line-F-calls or loads with `movea.l #`, scanned word by word."""
    named = set()
    for at in range(lo, hi, vdi.WORD_BYTES):
        word = word_in_snapshot(at)
        if aes.line_f_target(word) is not None:
            named.add(aes.line_f_target(word))
        if word == MOVEA_L_IMMEDIATE_A0:
            named.add(long_in_snapshot(at + vdi.WORD_BYTES))
    return named


PAIRS = sorted((name[:name.index("_OPCODE")], getattr(addrs, name)) for name in dir(addrs)
               if name.startswith("AES_ROM_") and "_OPCODE" in name)


@pytest.mark.parametrize("routine,opcode", PAIRS, ids=[f"{r}/{o}" for r, o in PAIRS])
def test_an_aes_routine_is_what_its_opcode_s_arm_calls(routine, opcode):
    assert addrs.AES_OPCODE_FIRST <= opcode <= addrs.AES_OPCODE_LAST
    assert getattr(addrs, routine) in calls_in(*arm_span(opcode)), f"arm {opcode} does not call {routine}"


DEFAULT_ARM_OPCODES = 48      # the table's gaps, counted in the ROM


def test_every_gap_in_the_table_is_the_default_arm():
    """48 opcodes the dispatcher serves with an alert and -1."""
    gaps = [opcode for opcode in range(addrs.AES_OPCODE_FIRST, addrs.AES_OPCODE_LAST + 1)
            if arm_of(opcode) == addrs.AES_ROM_DEFAULT_ARM]
    assert len(gaps) == DEFAULT_ARM_OPCODES and not {opcode for _routine, opcode in PAIRS} & set(gaps)


# ---- the staging: a tree by shape, and the snapshot's own ------------------------------------------------------------

RESOURCE_TREES = 3            # the AES's own resource: the file selector, and two more
FILE_SELECTOR_OBJECTS = 25


def test_the_snapshot_s_resource_trees_are_the_aes_s_own():
    """rsrc_gaddr's path, off the AES's own global[]: three trees, the first the file selector's 25 objects — and
    every tree ends on OB_FLAG_LASTOB, which is what the model's `tree_length` stops at."""
    header = aes.resource_header()
    assert case.word_in(BASE_IMAGE, header + aes.RSH_NTREE) == RESOURCE_TREES
    assert aes.resource_tree(0) == header + case.word_in(BASE_IMAGE, header + aes.RSH_OBJECT)
    assert aes.tree_length(aes.resource_tree(0)) == FILE_SELECTOR_OBJECTS
    assert all(aes.tree_length(aes.resource_tree(index)) for index in range(RESOURCE_TREES))


def test_a_tree_staged_by_shape_is_linked_as_the_snapshot_s_is():
    """The file selector re-staged from its PARENTS alone reproduces every next/head/tail the ROM's resource has."""
    tree = aes.resource_tree(0)
    count = aes.tree_length(tree)
    objects = [aes.node(None if index == aes.OB_ROOT else aes.parent_of(tree, index)) for index in range(count)]
    staged = vdi.make_image(aes.tree_pokes(objects))
    for index in range(count):
        for name in ("NEXT", "HEAD", "TAIL"):
            assert aes.read_field(staged, "OB", name, aes.TREE_AT + index * aes.OB_BYTES) == \
                aes.read_field(BASE_IMAGE, "OB", name, tree + index * aes.OB_BYTES), (index, name)


def test_the_line_f_caller_is_one_place_whatever_it_calls():
    """A row's entry is the same whichever routine it calls and whatever was staged before it; the call word is the
    routine's own, and `pea (SENTINEL).w` pushes the sentinel unchanged only while it is below the sign bit."""
    get_par, rc_intersect = (aes.line_f_caller_pokes(name) for name in ("AES_ROM_GET_PAR", "AES_ROM_RC_INTERSECT"))
    assert set(get_par) == set(rc_intersect) == {aes.LINE_F_CALLER_AT}
    assert get_par != rc_intersect
    assert emu.SENTINEL < SIGN_BIT_OF_A_SHORT_ADDRESS


def test_the_blocks_an_ob_spec_points_at_are_staged_by_field():
    """A G_TEXT-style object whose spec names a staged TEDINFO, and a G_USERDEF-style one whose spec names a staged
    USERBLK: each read back through the object, at the header's offsets."""
    tedinfo, userblk = aes.BLOCKS_AT, aes.BLOCKS_AT + aes.TE_BYTES
    pokes = case.merge_pokes(aes.tree_pokes([aes.node(None), aes.node(0, SPEC=tedinfo), aes.node(0, SPEC=userblk)]),
                             aes.tedinfo_pokes(tedinfo, PTEXT=0x12345678, TXTLEN=11),
                             aes.userblk_pokes(userblk, CODE=0xFE3F3E, PARM=0xABCD),
                             aes.iconblk_pokes(userblk + aes.UB_BYTES, PTEXT=0x100))
    image = vdi.make_image(pokes)
    assert aes.read_field(image, "TE", "TXTLEN", aes.read_object(image, aes.TREE_AT, 1)["SPEC"]) == 11
    assert aes.read_field(image, "UB", "CODE", aes.read_object(image, aes.TREE_AT, 2)["SPEC"]) == 0xFE3F3E
    assert aes.read_field(image, "IB", "PTEXT", userblk + aes.UB_BYTES) == 0x100


# ---- the fork queue: ROM CODE ADDRESSES its callers queue as values ------------------------------------------------
PUSH_LONG_IMMEDIATE_WORD = case.word_in(PUSH_LONG_IMMEDIATE, 0)
MOVE_L_IMMEDIATE_TO_FRAME = 0x2D7C   # move.l #<imm>,<d16>(a6): ap_tplay's store into its local fcode
IMMEDIATE_USES = (PUSH_LONG_IMMEDIATE_WORD, MOVE_L_IMMEDIATE_TO_FRAME, CMP_L_IMMEDIATE_D0)
PUSH_BYTES = len(PUSH_LONG_IMMEDIATE) + vdi.LONG_BYTES
FORK_FUNCTIONS = {function for _site, function in aes.FORK_FUNCTION_IMMEDIATES}
PUSHED = [site for site, _function in aes.FORK_FUNCTION_IMMEDIATES if word_in_snapshot(site) == PUSH_LONG_IMMEDIATE_WORD]


def calls_forkq(at):
    """Does the instruction at `at` call forkq — by Line-F, or by `jsr` (the interrupt-side glue)?"""
    word = word_in_snapshot(at)
    if word == case.word_in(JSR_ABSOLUTE_LONG, 0):
        return long_in_snapshot(at + vdi.WORD_BYTES) == addrs.AES_ROM_FORKQ
    return aes.line_f_target(word) == addrs.AES_ROM_FORKQ


def gem_text_words():
    return range(addrs.AES_ROM_GEM_ENTRY, aes.AES_LINEF_TABLE, vdi.WORD_BYTES)


@pytest.mark.parametrize("site,function", aes.FORK_FUNCTION_IMMEDIATES,
                         ids=[f"${site:x}" for site, _f in aes.FORK_FUNCTION_IMMEDIATES])
def test_a_fork_function_is_named_by_an_immediate(site, function):
    assert word_in_snapshot(site) in IMMEDIATE_USES and long_in_snapshot(site + vdi.WORD_BYTES) == function


def test_every_immediate_naming_a_fork_function_is_enumerated():
    """Any longword of the GEM text equal to a fork function's address is one of the listed instructions' own."""
    named = sorted(at - vdi.WORD_BYTES for at in gem_text_words() if long_in_snapshot(at) in FORK_FUNCTIONS)
    assert named == [site for site, _function in aes.FORK_FUNCTION_IMMEDIATES]


def test_every_forkq_call_queues_an_enumerated_function():
    """Every call of forkq in the GEM text follows a listed push — or is ap_tplay's, of the local it stores three of
    them into."""
    calls = [at for at in gem_text_words() if calls_forkq(at)]
    assert sorted(calls) == sorted([site + PUSH_BYTES for site in PUSHED] + [aes.FORKQ_CALL_OF_A_LOCAL])
