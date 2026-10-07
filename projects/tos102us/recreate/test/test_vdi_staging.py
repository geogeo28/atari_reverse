"""The VDI door's own claims (`test/vdi.py`), and the facts `include/vdi/*.h` states about THIS ROM and
THIS snapshot — held against both rather than trusted, so a header that drifts reddens here instead
of inside some function's differential.
"""
import random
import struct

import pytest

import harness
from harness import BASE_IMAGE, addrs, emu, make_image

import case
import gemdos_fs
import routines
import staging
import vdi
from opcodes import JSR_ABSOLUTE_LONG


def rom_long(address):
    return case.long_in(BASE_IMAGE, address)


# ---- the window ------------------------------------------------------------------------------------

def test_the_window_is_dead_ram_in_this_snapshot():
    """The window is COMPARED image, so live bytes there would be the desktop's, not a case's."""
    window = bytes(BASE_IMAGE[vdi.WINDOW_AT:vdi.WINDOW_AT + vdi.WINDOW_BYTES])
    assert window == bytes(len(window))


def test_the_window_is_clear_of_every_other_tenant():
    """Above the declared case band and the file system's window, below the oracle's stack guard."""
    assert staging.SCRATCH + staging.SCRATCH_BYTES <= vdi.WINDOW_AT
    assert gemdos_fs.SPAN.hi <= vdi.WINDOW_AT
    assert vdi.WINDOW_AT + vdi.WINDOW_BYTES <= emu.STACK_GUARD_LO


# ---- the Line-A block and its vectors, as the boot left them -----------------------------------------

def test_the_line_a_exception_and_a000_are_where_the_headers_say():
    assert case.long_in(BASE_IMAGE, addrs.VECTOR_LINE_A) == addrs.LINEA_ROM_DISPATCH
    assert rom_long(vdi.LINEA_OPCODE_TABLE) == addrs.LINEA_ROM_INIT


def test_the_ten_drawing_vectors_hold_the_cpu_set():
    """The boot always installs the CPU set; LINEA_BLIT_MODE says so and both table pointers name
    the two ROM tables — the state every core's `require_cpu_routine` is checked against."""
    assert case.long_in(BASE_IMAGE, vdi.LINEA_CPU_SET_PTR) == vdi.LINEA_CPU_SET
    assert case.long_in(BASE_IMAGE, vdi.LINEA_BLITTER_SET_PTR) == vdi.LINEA_BLITTER_SET
    assert not case.word_in(BASE_IMAGE, vdi.LINEA_BLIT_MODE) & vdi.LINEA_BLIT_MODE_BLITTER_MASK
    for slot in range(vdi.LINEA_VECTOR_COUNT):
        offset = slot * vdi.LONG_BYTES
        assert case.long_in(BASE_IMAGE, vdi.LINEA_VECTORS + offset) == rom_long(vdi.LINEA_CPU_SET + offset)
    assert vdi.LINEA_VECTOR_TEXTBLT == vdi.LINEA_VECTORS + (vdi.LINEA_VECTOR_COUNT - 1) * vdi.LONG_BYTES


# Atari's published displacement of the block's last documented field, SEEDABORT — the anchor that
# says the absolute addresses in `linea.h` are the published layout and not merely self-consistent.
PUBLISHED_SEEDABORT_OFFSET = 118


def test_the_console_names_the_line_a_fields_it_shares():
    """`linea.h` aliases two console names and extends the console's range by three words; the
    published layout says where each sits relative to the block, and so does this."""
    assert (vdi.LINEA_PLANES, vdi.LINEA_WIDTH) == (vdi.LINEA_BASE, vdi.LINEA_BASE + vdi.WORD_BYTES)
    assert vdi.LINEA_BYTES_LIN == vdi.LINEA_BASE - vdi.WORD_BYTES
    assert vdi.LINEA_SEEDABORT - vdi.LINEA_BASE == PUBLISHED_SEEDABORT_OFFSET


# v_contourfill's first instruction after its `link a6,#d16` is `move.l #imm,<abs>.l`: opcode word,
# immediate longword, then the absolute destination.
LINK_BYTES = 4
MOVE_LONG_IMMEDIATE_TO_ABSOLUTE = 0x23FC


def test_contour_fill_installs_the_seedabort_default():
    """v_contourfill stores `LINEA_ROM_SEEDABORT_DEFAULT` — `moveq #0,d0 / rts` — in SEEDABORT ($fd08e4)."""
    store = addrs.VDI_ROM_V_CONTOURFILL + LINK_BYTES
    assert vdi.rom_word(store) == MOVE_LONG_IMMEDIATE_TO_ABSOLUTE
    assert rom_long(store + vdi.WORD_BYTES) == addrs.LINEA_ROM_SEEDABORT_DEFAULT
    assert rom_long(store + vdi.WORD_BYTES + vdi.LONG_BYTES) == vdi.LINEA_SEEDABORT


# ---- the workstation, the fonts, the dispatch ---------------------------------------------------------

def test_the_physical_workstation_is_the_whole_list():
    assert case.long_in(BASE_IMAGE, vdi.LINEA_CUR_WORK) == vdi.VDI_PHYS_WORK
    assert vdi.workstation(BASE_IMAGE, "HANDLE") == vdi.VDI_PHYS_HANDLE
    assert vdi.workstation(BASE_IMAGE, "NEXT") == 0
    assert vdi.WS_YMX_CLIP + vdi.WORD_BYTES == vdi.WS_BYTES


@pytest.mark.parametrize("record", sorted(vdi.RECORD_BYTES))
def test_every_field_lies_inside_its_record(record):
    size = vdi.RECORD_BYTES[record]
    for name, spec in vdi.FIELDS[record].items():
        assert spec.at + spec.width * (spec.count or 1) <= size, f"{record}_{name} runs past the record"


def test_the_font_ring_and_the_line_a_font_table():
    ring = vdi.linea(BASE_IMAGE, "FONT_RING")
    assert ring[vdi.LINEA_FONT_RING_SYSTEM] == vdi.FONT_ROM_6X6
    assert ring[vdi.LINEA_FONT_RING_BUILTIN] == vdi.FONT_RAM_8X8
    assert ring[-1] == 0
    assert vdi.read_field(BASE_IMAGE, "FONT", "NEXT", vdi.FONT_RAM_8X8) == vdi.FONT_RAM_8X16
    table = [rom_long(vdi.LINEA_FONT_TABLE + slot * vdi.LONG_BYTES)
             for slot in range(vdi.LINEA_FONT_TABLE_ENTRIES + 1)]
    assert table == [vdi.FONT_ROM_6X6, vdi.FONT_ROM_8X8, vdi.FONT_ROM_8X16, 0], "and a zero longword after"


def test_a_rom_font_s_offset_table_follows_its_header():
    """The 90-byte header: the 6x6 font's offset table starts at header + FONT_HEADER_BYTES."""
    assert vdi.read_field(BASE_IMAGE, "FONT", "OFF_TABLE", vdi.FONT_ROM_6X6) == \
        vdi.FONT_ROM_6X6 + vdi.FONT_HEADER_BYTES


# v_opnwk's high-resolution patches of the two RAM headers ($fcb7a6..$fcb7be): `move.w #imm,<abs>.l`,
# then `eori.w`/`ori.w #imm,<abs>.l` — each instruction's absolute operand is at +4, after its opcode
# word and immediate word. The sites are the RAM header's base plus the field, and nothing spells them.
PATCH_OPERAND = 4
FONT_PATCHES = ((0xfcb7a6, vdi.FONT_RAM_8X8, "POINT"), (0xfcb7ae, vdi.FONT_RAM_8X16, "POINT"),
                (0xfcb7b6, vdi.FONT_RAM_8X8, "FLAGS"), (0xfcb7be, vdi.FONT_RAM_8X16, "FLAGS"))


@pytest.mark.parametrize("instruction,header,name", FONT_PATCHES)
def test_v_opnwk_patches_the_ram_font_headers_by_field(instruction, header, name):
    assert rom_long(instruction + PATCH_OPERAND) == header + vdi.field("FONT", name).at


SHIFTER_LEVELS = 8          # three bits of an ST palette component
PER_MILLE_FULL = 1000


def test_the_vq_color_level_table_runs_zero_to_a_thousand():
    levels = [vdi.rom_word(vdi.VDI_VQ_COLOR_LEVELS + i * vdi.WORD_BYTES) for i in range(SHIFTER_LEVELS)]
    assert levels[0] == 0 and levels[-1] == PER_MILLE_FULL and levels == sorted(levels)


TRAP_2_ARM_HEAD_BYTES = 0x10           # the arm tests D0 twice before its `jsr`


def test_the_vdi_entry_is_what_the_trap_2_arm_calls():
    """`SYSVAR_VDI_ENTRY`'s routine calls `VDI_ROM_ENTRY` by `jsr <abs.l>` within its first few words."""
    routine = case.long_in(BASE_IMAGE, addrs.SYSVAR_VDI_ENTRY)
    assert JSR_ABSOLUTE_LONG + addrs.VDI_ROM_ENTRY.to_bytes(4, "big") in \
        bytes(BASE_IMAGE[routine:routine + TRAP_2_ARM_HEAD_BYTES])


# ---- the opcode convention (`addrs.h`, "A VDI FUNCTION IS REACHED BY OPCODE") ---------------------------

def opcode_slot(opcode):
    """The address of the longword `$fca9f6`'s tables hold for `opcode`."""
    if vdi.VDI_OPCODE_FIRST <= opcode <= vdi.VDI_OPCODE_LAST:
        return vdi.VDI_OPCODE_TABLE + (opcode - vdi.VDI_OPCODE_FIRST) * vdi.LONG_BYTES
    assert vdi.VDI_OPCODE_EXT_FIRST <= opcode <= vdi.VDI_OPCODE_EXT_LAST, f"{opcode} is served by neither table"
    return vdi.VDI_OPCODE_TABLE_EXT + (opcode - vdi.VDI_OPCODE_EXT_FIRST) * vdi.LONG_BYTES


def escape_arm(subfunction):
    """Escape's arm for contrl[5]: a WORD offset from the table itself ($fc4290)."""
    assert 0 <= subfunction <= vdi.VDI_ESCAPE_LAST
    offset = struct.unpack(">h", bytes(BASE_IMAGE[vdi.VDI_ESCAPE_TABLE + subfunction * vdi.WORD_BYTES:][:2]))[0]
    return vdi.VDI_ESCAPE_TABLE + offset


def gdp_arm(subfunction):
    """The GDP's arm for contrl[5]: a longword of its switch table, indexed from 1 ($fcbbfe)."""
    assert vdi.VDI_GDP_FIRST <= subfunction <= vdi.VDI_GDP_LAST
    return rom_long(vdi.VDI_GDP_SWITCH + (subfunction - vdi.VDI_GDP_FIRST) * vdi.LONG_BYTES)


SUB_DISPATCHERS = {addrs.VDI_ROM_ESCAPE_OPCODE: escape_arm, addrs.VDI_ROM_GDP_OPCODE: gdp_arm}
OPCODE_SUFFIX = "_OPCODE"


def opcode_claims():
    """`[(routine name, opcode, subfunction or None)]` for every VDI `_OPCODE` / `_OPCODE_<k>` in addrs.h (the AES's
    are held to the AES dispatcher's table by `test_aes_door.py`)."""
    claims = []
    for name in dir(addrs):
        routine, marker, _extra = name.partition(OPCODE_SUFFIX)
        if marker and routines.is_routine(routine, routines.VDI_COMPONENT_PREFIXES) and hasattr(addrs, routine) and (name == routine + OPCODE_SUFFIX
                                                   or name.startswith(routine + OPCODE_SUFFIX + "_")):
            claims.append((routine, getattr(addrs, name), getattr(addrs, routine + "_SUBFUNCTION", None)))
    return sorted(claims)


@pytest.mark.parametrize("routine,opcode,subfunction", opcode_claims())
def test_a_vdi_routine_is_the_table_entry_it_claims_to_be(routine, opcode, subfunction):
    """Read from the ROM's opcode tables — and, for an arm, from its sub-dispatcher's table — so a wrong
    address, opcode or sub-function in `addrs.h` reds here."""
    served = rom_long(opcode_slot(opcode))
    if subfunction is None:
        assert served == getattr(addrs, routine)
        return
    assert opcode in SUB_DISPATCHERS, f"{routine}_SUBFUNCTION under opcode {opcode}, which has no sub-dispatcher"
    assert SUB_DISPATCHERS[opcode](subfunction) == getattr(addrs, routine)


def test_the_shared_stub_serves_its_four_opcodes():
    assert [claim for claim in opcode_claims() if claim[0] == "VDI_ROM_NOP"] == \
        [("VDI_ROM_NOP", opcode, None) for opcode in (4, 10, 27, 34)]


@pytest.mark.parametrize("subfunction", range(vdi.VDI_ESCAPE_LAST + 1))
def test_every_escape_arm_is_rom_code(subfunction):
    assert addrs.ROM_BASE <= escape_arm(subfunction) < addrs.ROM_BASE + addrs.ROM_BYTES


# ---- F1: the dispatcher's copies, held against the ROM's own dispatcher -------------------------------
A_HANDLE = 7
UNSERVED_OPCODE = 50        # past both tables' ranges: the dispatcher copies and then calls nothing
DISTINCT_WORD = 0x1100      # ...plus the copy's index: a value per field, none the snapshot holds
DISTINCT_LONG = 0x0007_1100
A_MULTIFILL = 0x0333


def distinctive_workstation(user_interior, mono):
    """A virtual workstation, linked behind the physical one, whose every copied field holds a value of
    its own — and a staged font whose FLAGS decide MONO_STATUS."""
    values = {}
    for index, (_destination, name) in enumerate(vdi.DISPATCH_COPIES):
        spec = vdi.field("WS", name)
        values[name] = (DISTINCT_LONG if spec.width == vdi.LONG_BYTES else DISTINCT_WORD) + index
    values.update(CUR_FONT=vdi.FONT_AT, MULTIFILL=A_MULTIFILL,
                  FILL_STYLE=vdi.VDI_INTERIOR_USER if user_interior else vdi.VDI_INTERIOR_USER - 1)
    flags = vdi.FONT_FLAG_MONOSPACE_MASK if mono else 0
    linked_font = vdi.merge_pokes(vdi.font_pokes(FLAGS=flags),
                                  vdi.field_pokes("WS", vdi.VDI_PHYS_WORK, NEXT=vdi.VIRTUAL_WORK_AT))
    return vdi.virtual_workstation(A_HANDLE, onto=linked_font, **values)


def dispatcher_run(staged):
    """The ROM's own dispatcher over `staged`, called with an opcode it serves nothing for."""
    pokes = vdi.merge_pokes(staged, vdi.pointer_pokes(),
                            {vdi.CONTRL_AT: vdi.contrl(UNSERVED_OPCODE, handle=A_HANDLE)})
    final, _writes, _regs = emu.run(make_image(pokes), addrs.VDI_ROM_DISPATCH, {})
    return final


@pytest.mark.parametrize("user_interior", (False, True))
@pytest.mark.parametrize("mono", (False, True))
def test_dispatched_pokes_are_what_the_rom_dispatcher_leaves(user_interior, mono):
    """Every copy `dispatched_pokes` stages is the byte the ROM's dispatcher stores, over a workstation
    whose fields all differ from the snapshot's — so a copy the mirror lacks or gets wrong is a byte here."""
    staged = distinctive_workstation(user_interior, mono)
    final = dispatcher_run(staged)
    for at, data in vdi.dispatcher_copies(make_image(staged), vdi.VIRTUAL_WORK_AT).items():
        assert bytes(final[at:at + len(data)]) == data, f"the dispatcher left {at:#x} other than the mirror"
        assert bytes(make_image(staged)[at:at + len(data)]) == data, f"{at:#x}: staged is not the mirror"
    assert vdi.linea(final, "MULTIFILL") == (A_MULTIFILL if user_interior else 0)
    assert vdi.linea(final, "MONO_STATUS") == (vdi.FONT_FLAG_MONOSPACE_MASK if mono else 0)


A_FEW_SEEDS = range(4)
RUNS_OF_A_RANDOM_MACHINE = 60
LONGEST_RANDOM_RUN = 9
ADDRESSES_ASKED = 4000
ANOTHER_BASE_S_WRT_MODE = 3


def _a_random_machine(chosen):
    """Pokes as `merge_pokes` answers them — runs in address order, none overlapping — above the system's own
    variables (a random font pointer in the workstation's record would send both spellings off the image alike)."""
    places = [chosen.randrange(vdi.WINDOW_AT, addrs.ST_RAM_BYTES - LONGEST_RANDOM_RUN) for _each in range(RUNS_OF_A_RANDOM_MACHINE)]
    return case.merge_pokes(*({at: chosen.randbytes(chosen.randint(1, LONGEST_RANDOM_RUN))} for at in places))


@pytest.mark.parametrize("seed", A_FEW_SEEDS)
def test_a_machine_read_off_its_pokes_is_the_image_they_make(seed):
    """`dispatched_pokes` reads the workstation's fields off the pokes laid over the base image, where it once built
    the image (and a copy of it to store into): every byte read that way is `make_image`'s — inside a run, at its
    two ends, between runs, off the base — and a byte stored is read back; and the pokes it answers are the ones the
    image-built spelling answers. Under another base image too (`harness.set_base_image`)."""
    chosen = random.Random(seed)
    machine = _a_random_machine(chosen)
    another = make_image(vdi.field_pokes("WS", vdi.VDI_PHYS_WORK, WRT_MODE=ANOTHER_BASE_S_WRT_MODE))
    another[vdi.WINDOW_AT:addrs.ST_RAM_BYTES] = bytes(byte ^ 0x5A for byte in another[vdi.WINDOW_AT:addrs.ST_RAM_BYTES])
    for base in (None, bytes(another)):
        previous = harness.set_base_image(base) if base else None
        try:
            image, read = make_image(machine), vdi._LaidOverTheBase(machine)
            edges = [at + nudge for start, data in machine.items() for at in (start, start + len(data)) for nudge in (-1, 0)]
            for at in [*edges, *(chosen.randrange(addrs.ST_RAM_BYTES) for _each in range(ADDRESSES_ASKED))]:
                assert read[at] == image[at], f"{at:#x}"
            read[edges[0]] = image[edges[0]] ^ 0xFF
            assert read[edges[0]] == image[edges[0]] ^ 0xFF and read[edges[0] + 1] == image[edges[0] + 1]
            staged = case.merge_pokes(machine, vdi.field_pokes("WS", vdi.VDI_PHYS_WORK, FILL_STYLE=2))
            by_the_image = case.merge_pokes(staged, vdi.dispatcher_copies(make_image(staged), vdi.VDI_PHYS_WORK))
            assert vdi.dispatched_pokes(onto=machine, FILL_STYLE=2) == by_the_image
            if base:                    # ...a field no poke stages is the base's IN FORCE, not the snapshot's
                assert vdi.linea(make_image(by_the_image), "WRT_MODE") == ANOTHER_BASE_S_WRT_MODE
        finally:
            if base:
                harness.set_base_image(previous)


def test_pokes_laid_in_another_order_are_not_read_by_their_place():
    """...the reader's premise, held where it is relied on: pokes that are not `merge_pokes`' own (address order) are
    refused by name rather than read wrong."""
    with pytest.raises(AssertionError, match="laid in another order"):
        vdi._LaidOverTheBase({0x200: b"\x01", 0x100: b"\x02"})


def test_a_call_stages_the_copies_not_just_the_record():
    """The shape F1 closed: WRT_MODE staged in the RECORD reaches LINEA_WRT_MODE, which is what the
    rasterizers read."""
    image = make_image(vdi.call_pokes(addrs.VDI_ROM_VSF_PERIMETER_OPCODE,
                                      workstation_pokes=vdi.dispatched_pokes(WRT_MODE=2)))
    assert vdi.linea(image, "WRT_MODE") == 2 != vdi.linea(BASE_IMAGE, "WRT_MODE")


# ---- F2: pokes merge byte by byte ------------------------------------------------------------------

def test_a_field_at_offset_zero_does_not_replace_the_record():
    """CHUP is WS +0: staged with a virtual workstation, it changes two bytes, not all 308."""
    image = make_image(vdi.virtual_workstation(A_HANDLE, CHUP=900))
    assert vdi.workstation(image, "CHUP", at=vdi.VIRTUAL_WORK_AT) == 900
    for name in ("CLIP", "WRT_MODE", "YMX_CLIP"):
        assert vdi.workstation(image, name, at=vdi.VIRTUAL_WORK_AT) == vdi.workstation(BASE_IMAGE, name)


# A pixel sharing its WORD with the screen's first address — the key a whole-screen clear is staged
# under, which a merge by key would REPLACE — and a pixel the snapshot's desktop has coloured.
FIRST_WORD_PIXEL = (1, 0)
DESKTOP_PIXEL = (200, 100)


def test_a_pixel_drawn_onto_a_cleared_screen_keeps_the_clear():
    assert vdi.read_pixel(BASE_IMAGE, *DESKTOP_PIXEL) != 0, "the check needs a pixel the clear changes"
    image = make_image(vdi.pixel_pokes({FIRST_WORD_PIXEL: 5}, onto=vdi.clear_screen_pokes()))
    assert vdi.read_pixel(image, *FIRST_WORD_PIXEL) == 5
    assert vdi.read_pixel(image, *DESKTOP_PIXEL) == 0 and vdi.read_pixel(image, 0, 0) == 0


def test_merge_pokes_later_layers_win_byte_by_byte():
    assert case.merge_pokes({0x100: b"\x01\x02\x03\x04"}, {0x102: b"\xaa"}) == {0x100: b"\x01\x02\xaa\x04"}


# ---- F3: names are fields, at their declared width ---------------------------------------------------

@pytest.mark.parametrize("record,name", (("LINEA", "VECTOR_COUNT"), ("LINEA", "BASE"), ("LINEA", "OPCODE_TABLE"),
                                         ("LINEA", "SAVE_BLOCK_BYTES"), ("WS", "BYTES"), ("FONT", "HEADER_BYTES"),
                                         ("LINEA", "BLIT_MODE_BLITTER_MASK"), ("LINEA", "NO_SUCH")))
def test_a_name_that_is_not_a_field_is_refused(record, name):
    with pytest.raises(KeyError, match=f"{record}_{name}"):
        vdi.field_pokes(record, 0, **{name: 0})


def test_a_value_wider_than_its_field_is_refused():
    with pytest.raises(ValueError, match="LINEA_WRT_MODE"):
        vdi.linea_pokes(WRT_MODE=0x1_0000)
    with pytest.raises(ValueError, match="WS_UD_PATRN"):
        vdi.field_pokes("WS", vdi.VIRTUAL_WORK_AT, UD_PATRN=[0] * 65)


def test_a_long_field_is_staged_whole():
    assert vdi.linea_pokes(PATPTR=0x7000) == {vdi.LINEA_PATPTR: b"\x00\x00\x70\x00"}


# ---- F4: a poke stays inside its own band ------------------------------------------------------------

def test_ptsin_is_bounded_by_the_array_it_writes():
    fits = vdi.PTSIN_BYTES // vdi.WORD_BYTES
    vdi.call_pokes(1, ptsin=(0,) * fits, ptsin_at=vdi.PTSIN_AT)
    with pytest.raises(AssertionError, match="ptsin"):
        vdi.call_pokes(1, ptsin=(0,) * (fits + 2), ptsin_at=vdi.PTSIN_AT)


def test_a_poke_running_out_of_its_band_is_refused():
    with pytest.raises(AssertionError, match="not inside one band"):
        vdi.fill_pattern_pokes(vdi.STUB_AT, [0xFFFF] * vdi.STUB_BYTES)


# ---- the screen ---------------------------------------------------------------------------------------

def test_the_screen_is_the_snapshot_s_low_resolution_framebuffer():
    geometry = vdi.SCREEN
    assert geometry.base == case.long_in(BASE_IMAGE, addrs.SYSVAR_V_BAS_AD)
    assert geometry.bytes_per_line == vdi.linea(BASE_IMAGE, "WIDTH")
    assert geometry.bytes_per_line * vdi.PIXELS_PER_GROUP == geometry.width * geometry.planes * vdi.WORD_BYTES
    assert geometry.base + geometry.bytes <= addrs.ST_RAM_BYTES


@pytest.mark.parametrize("x,y", ((0, 0), (15, 0), (16, 1), (159, 99), (319, 199)))
def test_a_staged_pixel_reads_back_and_leaves_its_neighbours(x, y):
    """Every colour at one pixel, over a screen whose other pixels keep the snapshot's colours."""
    for colour in range(1 << vdi.SCREEN.planes):
        image = make_image(vdi.pixel_pokes({(x, y): colour}))
        assert vdi.read_pixel(image, x, y) == colour
        neighbour = x ^ 1
        assert vdi.read_pixel(image, neighbour, y) == vdi.read_pixel(BASE_IMAGE, neighbour, y)


def test_the_screen_diff_names_the_pixels():
    before = make_image(vdi.clear_screen_pokes())
    after = make_image(vdi.pixel_pokes({(3, 4): 2, (300, 150): 1}, onto=vdi.clear_screen_pokes()))
    message = vdi.screen_diff(before, after)
    assert message.startswith("2 pixel(s) differ in x 3..300, y 4..150") and "(3,4): 0->2" in message
    assert vdi.screen_diff(before, before) == "the screens are identical"


# ---- the staging helpers ----------------------------------------------------------------------------

def test_call_pokes_leave_the_arrays_where_the_pointers_say():
    image = make_image(vdi.call_pokes(3, intin=(7, 8), ptsin=(1, 2, 3, 4)))
    assert [vdi.linea(image, name) for name in vdi.POINTER_VARIABLES] == \
        [vdi.CONTRL_AT, vdi.INTIN_AT, vdi.VDI_PTSIN_COPY, vdi.INTOUT_AT, vdi.PTSOUT_AT]
    words = lambda at, count: [case.word_in(image, at + i * vdi.WORD_BYTES) for i in range(count)]  # noqa: E731
    assert words(vdi.CONTRL_AT, vdi.CONTRL_HANDLE // vdi.WORD_BYTES + 1) == [3, 2, 0, 2, 0, 0, vdi.VDI_PHYS_HANDLE]
    assert words(vdi.VDI_PTSIN_COPY, 4) == [1, 2, 3, 4]


def test_a_virtual_call_names_its_handle():
    image = make_image(vdi.call_pokes(3, workstation_pokes=vdi.virtual_workstation(A_HANDLE)))
    assert case.word_in(image, vdi.CONTRL_AT + vdi.CONTRL_HANDLE) == A_HANDLE
    assert vdi.linea(image, "CUR_WORK") == vdi.VIRTUAL_WORK_AT
