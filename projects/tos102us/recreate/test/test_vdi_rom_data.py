"""EVERY ROM ADDRESS THE VDI's C AND `.S` USE AS A VALUE — enumerated, and held to the sources.

The reconstruction runs with the image based at 0, so `image + VDI_MAP_COL` reads the ROM's own table at its
1987 address and `wr32(... USER_BUT, VDI_ROM_USER_VECTOR_DEFAULT)` stores a 1987 code address. Both are right
against this ROM and both are OBLIGATIONS on a rebuilt one, which links its own code and data where its
linker puts them. So every such use is listed here, by file, with its KIND — which is what says what the ROM
build owes it (`../README.md`, "What ships as the ROM's own instructions"):

* TABLE — a data table outside every transcribed region, read in place: the ROM build keeps it at this
  address (its data band), or relocates every reference listed here;
* CODE — a routine's address as a value: stored in a RAM vector, compared with one (`require_cpu_routine`),
  or handed on as the dispatcher's D0. The ROM build must use the address the SHIPPED routine is linked at;
* REGION_TABLE — a table INSIDE a region a `.S` transcribes (a code region). The C that reads it is that
  region's own C core, which the ROM build does not link (`TRANSCRIBED_C_CORES`): harmless exactly while
  that stays true. A shipped C that read one would have to read the `.S`'s copy instead;
* DISTANCE — two ROM addresses subtracted, a distance inside one transcribed region, which relocation keeps;
* WAIT_SITE — a busy-wait's site, the scheduled-write model's key for counting the ROM's arrivals against the
  C's polls (`sched.h`). No obligation: the target's `sched.h` ignores it, since a machine has a PC.
* RETURN_SITE — the instruction after a ROM caller's `jsr` to the GEMDOS door, which the host build hands the
  door so LINEA_RETSAV holds what the ROM's `jsr` leaves (`vdi/workstation.h`). No obligation: the shipped door is
  the `.S`, which parks its own caller's address, and the glue drops the argument.

`test_the_census_is_the_list` is the surface: a new use of a ROM address anywhere in `src/vdi/` — or in the
CODE of an `include/vdi/` header, an inline that reads a table, keyed `vdi/<name>.h` — reds until it is listed
with its kind (a header inline is compiled into every file that calls it, and a call names the function, not
the table), and `test_a_table_s_kind_is_where_it_lies` holds each TABLE / REGION_TABLE to the
byte-pinned regions (`transcription.every_pinned_region`).
"""
import re
from pathlib import Path

from harness import addrs

import transcription
import vdi

RECREATE = Path(__file__).resolve().parents[1]
SOURCES = RECREATE / "src" / "vdi"
INCLUDE = RECREATE / "include"
VDI_HEADERS = INCLUDE / "vdi"
HEADERS = sorted((RECREATE / "include").glob("*.h")) + sorted((RECREATE / "include").glob("*/*.h"))
# The 68000's view of the ROM: 192 KB below the I/O page, which is where a VALUE is an obligation. The I/O
# page ($ff0000 up) is the machine's own address in any build.
ROM_LO, ROM_HI = 0xFC0000, 0xFF0000

TABLE, CODE, REGION_TABLE, DISTANCE, WAIT_SITE, RETURN_SITE = (
    "TABLE", "CODE", "REGION_TABLE", "DISTANCE", "WAIT_SITE", "RETURN_SITE")
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

_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)
_TOKEN = re.compile(r"\b0[xX][0-9a-fA-F]+\b|\b[A-Za-z_]\w*\b")


def _defines(path, known):
    """`path`'s `#define`s over `known` — `addrs.parse` refuses a file that has none, which a header of
    declarations or a source with no constants of its own is."""
    try:
        return {**known, **addrs.parse(path, known=known)}
    except RuntimeError:
        return known


def _constants():
    known = dict(vdi.CONSTANTS)
    for header in HEADERS:
        known = _defines(header, known)
    return known


def _value(token, constants):
    return int(token, 16) if token[:2].lower() == "0x" else constants.get(token)


def _scanned():
    """`{key: path}`: every VDI source by its name, and every VDI header by its `vdi/<name>.h`."""
    sources = {source.name: source for source in sorted(SOURCES.glob("*.[cS]"))}
    headers = {str(header.relative_to(INCLUDE)): header for header in sorted(VDI_HEADERS.glob("*.h"))}
    return {**sources, **headers}


def census():
    """`{file: {token}}`: every name or literal in a VDI source's or header's CODE (comments and `#define`
    lines left out, which name an address rather than use it) whose value is a ROM address."""
    known, found = _constants(), {}
    for key, path in _scanned().items():
        constants = _defines(path, known)
        code = "\n".join(line for line in _COMMENT.sub(" ", path.read_text()).splitlines()
                         if not line.lstrip().startswith("#define"))
        uses = {token for token in _TOKEN.findall(code)
                if isinstance(_value(token, constants), int) and ROM_LO <= _value(token, constants) < ROM_HI}
        if uses:
            found[key] = uses
    return found


def test_the_census_is_the_list():
    listed = {source: set(uses) for source, uses in ROM_ADDRESSES_AS_DATA.items()}
    assert census() == listed


def test_a_table_s_kind_is_where_it_lies():
    """A REGION_TABLE lies inside a byte-pinned region and a TABLE outside every one."""
    known, regions = _constants(), transcription.every_pinned_region()
    for source, uses in ROM_ADDRESSES_AS_DATA.items():
        constants = _defines(_scanned()[source], known)
        for name, kind in uses.items():
            inside = any(region.lo <= constants[name] < region.hi for region in regions)
            if kind in (TABLE, REGION_TABLE):
                assert inside == (kind == REGION_TABLE), f"{source}: {name} is a {kind}, but it lies " \
                                                         f"{'inside' if inside else 'outside'} every pinned region"
