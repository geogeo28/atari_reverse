"""EVERY ROM ADDRESS THE VDI's C AND `.S` USE AS A VALUE — enumerated, and held to the sources.

The census, its KINDS and what each owes a rebuilt ROM are `rom_data.py`'s; this is the VDI's table. Its RETURN_SITEs
are the instructions after a ROM caller's `jsr` to the GEMDOS door, which the host build hands the door so
LINEA_RETSAV holds what the ROM's `jsr` leaves (`vdi/workstation.h`): the shipped door is the `.S`, which parks its own
caller's address, and the glue drops the argument.

`test_the_census_is_the_list` is the surface: a new use of a ROM address anywhere in `src/vdi/` — or in the CODE of an
`include/vdi/` header, keyed `vdi/<name>.h` — reds until it is listed with its kind, and
`test_a_table_s_kind_is_where_it_lies` holds each TABLE / REGION_TABLE to the byte-pinned regions.
"""
import rom_data
from rom_data import CODE, DISTANCE, REGION_TABLE, RETURN_SITE, TABLE, WAIT_SITE

VDI = rom_data.component("vdi")
ROM_ADDRESSES_AS_DATA = {
    "attributes.c": {"VDI_HATCHES_LOWER": TABLE, "VDI_HATCHES_UPPER": TABLE,
                     "VDI_PATTERNS_LOWER": TABLE, "VDI_PATTERNS_UPPER": TABLE, "VDI_PATTERN_HOLLOW": TABLE,
                     "VDI_PATTERN_SOLID": TABLE},
    "blit.S": {"VDI_MAP_COL": TABLE},
    # BLIT_EDGE_MASK_TABLE ($fd1304) is inside cpu_blit's region, read by cpu_blit's own C core.
    "blit.c": {"BLIT_EDGE_MASK_TABLE": REGION_TABLE, "LINEA_ROM_CPU_BLIT": CODE, "VDI_MAP_COL": TABLE},
    # The entries: the Line-A handler's font table (the three ROM faces), the two primitives whose C ships and so have
    # no `.S` entry for its opcode table to name ($a009 v_show_c, $a00f contour fill), and the dispatcher the `trap #2`
    # entry `jsr`s, whose C ships. The dispatcher reads the VDI's opcode tables in place — tables of CODE addresses,
    # every one a function a rebuilt ROM owes the table its linked address — and the handler's twin its own table.
    "entry.S": {"FONT_ROM_6X6": TABLE, "FONT_ROM_8X8": TABLE, "FONT_ROM_8X16": TABLE, "LINEA_ROM_CONTOUR_FILL": CODE,
                "VDI_ROM_V_SHOW_C": CODE, "VDI_ROM_DISPATCH": CODE},
    "entry.c": {"LINEA_OPCODE_TABLE": REGION_TABLE, "VDI_OPCODE_TABLE": TABLE, "VDI_OPCODE_TABLE_EXT": TABLE},
    # The graphic cursor's two arms, whose `jmp` names v_show_c and v_hide_c: their C ships, so the addresses stay the
    # ROM's own, CODE values a rebuilt ROM owes an entry with the VDI function's convention.
    "escape.S": {"VDI_ROM_V_HIDE_C": CODE, "VDI_ROM_V_SHOW_C": CODE},
    "fill.c": {"LINEA_ROM_SEEDABORT_DEFAULT": CODE, "VDI_FILL_PEN_MASKS": TABLE, "VDI_MAP_COL": TABLE,
               "VDI_REV_MAP_COL": TABLE},
    "helpers.c": {"LINE_STYLE_SOLID": TABLE, "VDI_PATTERN_SOLID": TABLE, "VDI_SINE_TABLE": TABLE},
    "inquire.c": {"FONT_ROM_6X6": TABLE, "VDI_REV_MAP_COL": TABLE, "VDI_SCRPT2_DEFAULT": TABLE},
    # $a000's twin answers the two tables of the region `entry.S` transcribes; the `.S` answers its own.
    "linea.c": {"LINEA_FONT_TABLE": REGION_TABLE, "LINEA_OPCODE_TABLE": REGION_TABLE},
    # v_pline's style masks and v_pmarker's shape pointers (the shapes themselves, $fd3664.., are read through them).
    "lines.c": {"VDI_LINE_STYLES": TABLE, "VDI_MARKER_SHAPES": TABLE},
    "mouse.S": {"VDI_MAP_COL": TABLE},
    # BIOS_BCONSTAT / BIOS_BCONIN: the D0 the BIOS dispatcher would have jumped with, handed to its C core.
    "mouse.c": {"BIOS_BCONIN": CODE, "BIOS_BCONSTAT": CODE, "VDI_DEFAULT_MOUSE_FORM": TABLE,
                "VDI_INITMOUS_PARAMS": TABLE, "VDI_MAP_COL": TABLE, "VDI_ROM_DEFAULT_USER_CUR": CODE,
                "VDI_ROM_MOUSE_ISR": CODE, "VDI_ROM_USER_VECTOR_DEFAULT": CODE, "VDI_ROM_VBL_DRAW_CURSOR": CODE,
                "VDI_LOCATOR_WAIT_SITE": WAIT_SITE, "VDI_CHOICE_WAIT_SITE": WAIT_SITE, "VDI_STRING_WAIT_SITE": WAIT_SITE},
    "palette.S": {"VDI_MAP_COL": TABLE},
    # ...the palette pair's own two tables, inside its region and read by its C cores.
    "palette.c": {"VDI_MAP_COL": TABLE, "VDI_PEN_MASKS": REGION_TABLE, "VDI_VQ_COLOR_LEVELS": REGION_TABLE},
    "raster.c": {"LINEA_ROM_CPU_HLINE": CODE, "LINEA_ROM_CPU_RECT_FILL": CODE, "LINEA_ROM_CPU_VLINE": CODE,
                 "RASTER_CONCAT_SHIFT_TABLE": REGION_TABLE, "RASTER_FRINGE_MASK_TABLE": REGION_TABLE,
                 "RASTER_PLANE_OPCODES": REGION_TABLE},
    # USER_TIM's default and the tick installed as etv_timer, and the two palettes handed to Setpalette. The tick's
    # shipped address is `screen.S`'s `vdi_rom_timer_tick`; USER_TIM's default is the bare `rts` ending $fca648,
    # which nothing ships yet — a rebuilt ROM owes it one (STATUS, "Not reconstructed").
    "screen.c": {"VDI_PALETTE_LOW": TABLE, "VDI_PALETTE_MEDIUM": TABLE, "VDI_ROM_NOP": CODE,
                 "VDI_ROM_TIMER_TICK": CODE},
    # The ROM 6x6's header: read, put in the ring's first slot, and vst_font's fallback.
    "text.c": {"FONT_ROM_6X6": TABLE},
    # The `lea` of raster.S's fringe table, spelt as raster.S's entry plus the table's distance from it.
    "text_raster.S": {"LINEA_ROM_LINE_PLANE_WORDS": DISTANCE, "RASTER_FRINGE_MASK_TABLE": DISTANCE},
    "text_raster.c": {"LINEA_ROM_CPU_FAST_TEXT": CODE, "LINEA_ROM_CPU_TEXTBLT": CODE,
                      "RASTER_FRINGE_MASK_TABLE": REGION_TABLE, "TEXT_FAST_ARM_TABLE": REGION_TABLE,
                      "TEXT_GROUP_BYTES_TABLE": REGION_TABLE, "TEXT_OP_INDEX_TABLE": REGION_TABLE,
                      "TEXT_OP_MASKED_TABLE": REGION_TABLE, "TEXT_OP_WHOLE_TABLE": REGION_TABLE},
    # The workstations: the device tables' defaults, the ROM fonts' headers v_opnwk copies, init_wk's defaults, and
    # the three return sites the GEMDOS door parks.
    "workstation.c": {"FONT_ROM_8X16": TABLE, "FONT_ROM_8X8": TABLE, "VDI_DEV_TAB_DEFAULT": TABLE,
                      "VDI_INQ_TAB_DEFAULT": TABLE, "VDI_LINE_STYLES": TABLE,
                      "VDI_MAX_VERTICES_DEFAULT": TABLE, "VDI_SCRPT2_DEFAULT": TABLE, "VDI_SIZ_TAB_DEFAULT": TABLE,
                      "VDI_UD_PATTERN_DEFAULT": TABLE, "VDI_OPNVWK_MALLOC_RETURN": RETURN_SITE,
                      "VDI_CLSVWK_MFREE_RETURN": RETURN_SITE, "VDI_CLSWK_MFREE_RETURN": RETURN_SITE},
    # ---- header inlines, compiled into each file that calls them ----
    # vdi_mapped_colour: the MAP_COL lookup attributes.c's colour setters and workstation.c's open share.
    "vdi/attributes.h": {"VDI_MAP_COL": TABLE},
}

def census():
    """`{file: {token}}`: every ROM address a VDI source or header uses as a value (`rom_data.census`)."""
    return rom_data.census(VDI)


def test_the_census_is_the_list():
    assert census() == rom_data.listed(ROM_ADDRESSES_AS_DATA)


def test_a_table_s_kind_is_where_it_lies():
    """A REGION_TABLE lies inside a byte-pinned region and a TABLE outside every one."""
    assert rom_data.kind_mismatches(VDI, ROM_ADDRESSES_AS_DATA) == []
