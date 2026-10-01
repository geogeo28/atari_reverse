"""EVERY ROM ADDRESS THE AES USES AS A VALUE — its C's, and its ROM text's, each enumerated and held to its source.

(a) THE SOURCES (`ROM_ADDRESSES_AS_DATA`): every ROM address a `src/aes/` source or an `include/aes/` header uses as a
value, by file and KIND — `rom_data.py`'s census and kinds, the VDI's (`test_vdi_rom_data.py`) over the AES's files.
The AES's RETURN_SITEs are the instructions after a GEMDOS glue call's `bsr __DOS` (or its caller's `jsr`), which
the C STORES where the ROM's glue parks them (AES_TRAP1_RETURN, AES_DOS_RETURN) so RAM holds what the ROM's leaves:
the C returns by `rts` and never jumps through them.

(b) THE ROM TEXT (`CODE_IMMEDIATES`, `PC_RELATIVE_DATA`): every instruction of the AES's text ($fd9eca..$fee8ff) whose
operand NAMES ROM CODE as a value — `pea`, `move.l #`, `movea.l #`, `lea`, `cmp.l #` of a routine's address — with the
routine that holds it. Each is an obligation the port of its routine inherits: the C must
use that routine's ROM address (and a rebuilt ROM, its own linked one) — the fork functions, the walkers' routines,
the vectors the start-up installs. A ported row names the file whose C now owes it, and that file's census (a) lists
the value as CODE. Every pc-relative DATA reference into the text is listed too, by kind: a TEXT_TABLE (a table or a
string inside the text, which a C port spells as its own data) or CODE_BYTES — an instruction's own bytes READ OR
WRITTEN AS DATA: gr_watchbox, gr_rubbox and gr_dragbox read the immediates of two `move.l #` in gr_setup and
gr_draw, and the Line-F handler writes its own `movem` mask. A rebuilt ROM that re-lays those instructions changes
what they read. No obligation while the C uses the value; every one is an order to keep in mind.

THE SURFACES: a new ROM address in an AES source reds (a) until it is listed with its kind; a new immediate naming
AES code, a new pc-relative data reference, or a ROM value outside the text that is not AES data reds (b). Both
directions are proved to see a planted one (`test_a_planted_*`).

CONCURRENT WORK: each file's rows are its author's — a slice adding an AES source adds its file's entry here, and a
slice porting a routine of (b) names its file in that row's `owed_by`.
"""
import shutil
import struct
from collections import namedtuple

from harness import addrs

import aes
import rom_data
from rom_data import CODE, DISTANCE, RETURN_SITE, TABLE

AES = rom_data.component("aes")

# ---- (a) the sources --------------------------------------------------------------------------------------------
ROM_ADDRESSES_AS_DATA = {
    # The `trap #2` door's two hops the graphics bridge checks before it calls the VDI's C twin (`require_cpu_routine`):
    # the AES's handler in vector $88 and the VDI door it chains through $8c2a — and the `$a000` bridge's one, the
    # VDI's Line-A dispatcher in vector $28.
    "aes/gsx.h": {"GEM_TRAP2": CODE, "GEM_TRAP2_VDI_DOOR": CODE, "LINEA_ROM_DISPATCH": CODE},
    # The glue's parked return sites: __DOS's own (dos_free, dos_sdta, dos_close) and the four calls' `bsr __DOS`.
    "gemdosif.c": {"AES_DOS_TRAP_RETURN": RETURN_SITE, "AES_DOS_SFIRST_TRAP_RETURN": RETURN_SITE,
                   "AES_DOS_OPEN_TRAP_RETURN": RETURN_SITE, "AES_DOS_READ_TRAP_RETURN": RETURN_SITE,
                   "AES_DOS_LSEEK_TRAP_RETURN": RETURN_SITE},
    # The `bsr.w` to the shared OB_ADDR helper, spelt as its displacement from each routine's own entry
    # (`BSR_W_TO_OB_ADDR`): a distance inside the optimize region the `.S` transcribes.
    "optimize.S": {"AES_ROM_FS_SGET": DISTANCE, "AES_ROM_FS_SSET": DISTANCE, "AES_ROM_INF_FLDSET": DISTANCE,
                   "AES_ROM_INF_GINDEX": DISTANCE, "AES_ROM_INF_WHAT": DISTANCE},
    # The ROM's resource bundle start-up copies, and rsrc_free's and rs_readit's return sites from dos_free and
    # dos_close (host arguments).
    "resource.c": {"AES_RSC_BUNDLE": TABLE, "AES_RS_FREE_MFREE_RETURN": RETURN_SITE,
                   "AES_RS_READIT_CLOSE_RETURN": RETURN_SITE},
    # gsx_setmb_aes hands vex_butv/vex_motv the AES's interrupt glue by its ROM address (rows $fe884a/$fe8844 of (b)), and
    # gsx_mfree's dos_free parks the word after its Line-F call.
    "gsxif.c": {"AES_ROM_BUTTON_GLUE": CODE, "AES_ROM_MOTION_GLUE": CODE, "AES_GSX_MFREE_RETURN": RETURN_SITE},
    # sh_find's return site from dos_sdta (a host argument, as rsrc_free's).
    "shell_find.c": {"AES_SH_FIND_SDTA_RETURN": RETURN_SITE},
    # newrect hands everyobj mkrect by its ROM address ($fe5d68 `move.l #$fe5c9a,-(sp)`, row (b) below).
    "wrect.c": {"AES_ROM_MKRECT": CODE},
}


def test_the_census_is_the_list():
    assert rom_data.census(AES) == rom_data.listed(ROM_ADDRESSES_AS_DATA)


def test_a_table_s_kind_is_where_it_lies():
    """A REGION_TABLE lies inside a byte-pinned region and a TABLE outside every one."""
    assert rom_data.kind_mismatches(AES, ROM_ADDRESSES_AS_DATA) == []


def test_a_planted_use_in_a_source_is_found(tmp_path):
    """The census sees a use it was not told of: a scratch component holding one source that hands a routine's ROM
    address on, and one header inline that names it — both found, by file and name; the comment naming it is not."""
    sources, headers = tmp_path / "src", tmp_path / "include" / "aes"
    sources.mkdir()
    headers.mkdir(parents=True)
    (sources / "planted.c").write_text("/* AES_ROM_NEWRECT */\nvoid f(void) { g(AES_ROM_NEWRECT); }\n")
    (headers / "planted.h").write_text("static inline unsigned h(void) { return 0xfe5c9a; }\n")
    found = rom_data.census(rom_data.Component(sources, headers))
    assert found == {"planted.c": {"AES_ROM_NEWRECT"}, "aes/planted.h": {"0xfe5c9a"}}


# ---- (b) the ROM text ---------------------------------------------------------------------------------------------
TEXT_LO, TEXT_HI = aes.AES_TEXT
# Past the text: the Line-F call table, the strings and the Alcyon switch tables — the AES's own data, which a rebuilt
# ROM lays where it lays its text. Below it, only the resource bundle start-up copies (census (a): TABLE).
DATA_LO, DATA_HI = aes.AES_LINEF_TABLE, rom_data.ROM_HI
DATA_BELOW_THE_TEXT = {aes.header_constants("resource.h")["AES_RSC_BUNDLE"]}

Immediate = namedtuple("Immediate", "value owner owed_by", defaults=(None,))
# The instruction whose operand names the routine: the routine named, the routine holding the instruction ("ctx" =
# named from its callers and callees, not a body read), and — once ported — the file whose C owes it.
CODE_IMMEDIATES = {
    0xFD9F4A: Immediate(0xFEE8C2, "gem_entry: the Line-F handler's ROM body, copied into its RAM block"),
    0xFD9F86: Immediate(0xFED424, "gem_entry: a bare `rts`, into $947a"),
    0xFD9F92: Immediate(addrs.AES_ROM_TICK_GLUE, "gem_entry: interrupt glue, into $947e"),
    0xFD9F9E: Immediate(0xFE3F3E, "gem_entry: into $8c32"),
    0xFE3C78: Immediate(0xFE3EA6, "install_trap2: the AES's `trap #2` handler into vector $88"),
    0xFE3C84: Immediate(0xFE3EA6, "$fe3c84 (ctx): the same handler into $88 again, then the critic's install"),
    0xFE3C8E: Immediate(0xFE3CBE, "$fe3c84 (ctx): the critical-error handler, Setexc($101)"),
    0xFE3CB6: Immediate(0xFE3CBE, "$fe3cac (ctx): the critical-error handler reinstalled"),
    0xFE3F00: Immediate(0xFE65AA, "gem_trap2_aes: aes_entry, into A0"),
    0xFE437C: Immediate(0xFE38B0, "$fe42e8 (ctx, the accessory loader): gotopgm pushed"),
    0xFE4A7E: Immediate(0xFE49D2, "$fe4a6a (ctx, ctlmgr)"),
    0xFE4A8C: Immediate(0xFE49D2, "$fe4a6a (ctx, ctlmgr), pushed"),
    0xFE5D68: Immediate(addrs.AES_ROM_MKRECT, "newrect: mkrect, everyobj's routine", "wrect.c"),
    0xFE6216: Immediate(0xFE8340, "the dispatcher's graf_growbox arm (ctx): gr_growbox"),
    0xFE621E: Immediate(0xFE837A, "the dispatcher's graf_shrinkbox arm (ctx): gr_shrinkbox"),
    0xFE6698: Immediate(0xFED424, "ap_tplay: the bare `rts` as a vex routine (set_contrl_ptr)"),
    0xFE66B6: Immediate(0xFED424, "ap_tplay: ...and again"),
    0xFE8844: Immediate(addrs.AES_ROM_MOTION_GLUE, "gsx_setmb_aes: the mouse-motion interrupt glue, for vex_motv", "gsxif.c"),
    0xFE884A: Immediate(addrs.AES_ROM_BUTTON_GLUE, "gsx_setmb_aes: the button interrupt glue, for vex_butv", "gsxif.c"),
    0xFEA08C: Immediate(0xFE9A88, "ob_draw: just_draw, everyobj's routine"),
    0xFEB272: Immediate(0xFEADDC, "sh_main: sh_find's optional routine"),
    0xFEC146: Immediate(addrs.AES_ROM_NEWRECT, "$fec0ca (ctx, gemwmlib's window-change redraw): newrect, everyobj's"),
    0xFED5A6: Immediate(0xFE38B0, "$fed554 (ctx): gotopgm pushed"),
}
# The sixteen fork-function immediates are `aes.FORK_FUNCTION_IMMEDIATES` (each with its routine there), folded in
# here: forkq's callers, forker's recorder and ap_trecd are all the event layer's.

TEXT_TABLE, CODE_BYTES = "TEXT_TABLE", "CODE_BYTES"
PcRelative = namedtuple("PcRelative", "target kind owner")
PC_RELATIVE_DATA = {
    0xFDAD1E: PcRelative(0xFDAD74, TEXT_TABLE, "gsx_tblt: the font block for font 3"),
    0xFDAD28: PcRelative(0xFDAD8C, TEXT_TABLE, "gsx_tblt: ...for font 5"),
    0xFE39BE: PcRelative(0xFE39B4, TEXT_TABLE, "$fe39bc (ctx, Pexec glue): the empty tail string, a zero word"),
    0xFE3B20: PcRelative(0xFE3B64, TEXT_TABLE, "$fe3b02 (ctx, desk): the `:\\*.*` search suffix"),
    0xFE84CA: PcRelative(0xFE85B2, CODE_BYTES, "gr_watchbox: gr_setup's `move.l #` immediate, read"),
    0xFE85CE: PcRelative(0xFE8586, CODE_BYTES, "gr_rubbox: gr_draw's (ctx) `move.l #` immediate, read"),
    0xFE869C: PcRelative(0xFE8586, CODE_BYTES, "gr_dragbox: ...the same immediate, read"),
    0xFE8768: PcRelative(0xFE8780, TEXT_TABLE, "gr_mkstate: its table of RAM addresses"),
    0xFE8BBA: PcRelative(0xFE8BDC, TEXT_TABLE, "the gsx op table, three bytes a row"),
    0xFEE8EE: PcRelative(0xFEE8F8, CODE_BYTES, "linef_handler: its own `movem` mask, WRITTEN (in its RAM copy)"),
}


def text_operands(rom=rom_data.ROM_IMAGE):
    return rom_data.text_operands(TEXT_LO, TEXT_HI, rom)


def code_immediates(rom=rom_data.ROM_IMAGE):
    """`{site: value}`: every absolute operand of the text that names the text — a routine's address as a value."""
    return {operand.site: operand.value for operand in text_operands(rom)
            if not operand.pc_relative and TEXT_LO <= operand.value < TEXT_HI}


def listed_immediates():
    """`{site: value}`: the table and the fork functions."""
    return {**{site: row.value for site, row in CODE_IMMEDIATES.items()}, **dict(aes.FORK_FUNCTION_IMMEDIATES)}


def test_every_immediate_naming_aes_code_is_listed():
    assert code_immediates() == listed_immediates()


def test_the_fork_functions_are_folded_in_not_copied():
    assert not set(CODE_IMMEDIATES) & {site for site, _function in aes.FORK_FUNCTION_IMMEDIATES}


def test_every_other_rom_value_the_text_names_is_aes_data():
    """Every absolute operand naming the ROM outside the text: the AES's data past it, or the resource bundle."""
    stray = {(hex(operand.site), hex(operand.value)) for operand in text_operands()
             if not operand.pc_relative and not TEXT_LO <= operand.value < TEXT_HI
             and not DATA_LO <= operand.value < DATA_HI and operand.value not in DATA_BELOW_THE_TEXT}
    assert stray == set()


def test_every_pc_relative_data_reference_is_listed():
    found = {operand.site: operand.value for operand in text_operands() if operand.pc_relative}
    assert found == {site: row.target for site, row in PC_RELATIVE_DATA.items()}


def test_code_bytes_are_an_instruction_s_own_operand():
    """Each CODE_BYTES target lies inside the instruction that begins one word before it (an immediate, a `movem`
    mask) — the bytes ARE code, not a table the sweep happened to decode."""
    starts = [address for address, _text in rom_data.instructions(TEXT_LO, TEXT_HI)]
    following = dict(zip(starts, starts[1:]))
    for site, row in PC_RELATIVE_DATA.items():
        if row.kind == CODE_BYTES:
            instruction = row.target - aes.WORD_BYTES
            assert row.target < following.get(instruction, instruction), f"${site:x}: ${row.target:x} is not an operand"


def test_a_ported_row_is_its_file_s_code():
    """A row of (b) a port now owes names its file, whose census (a) lists the routine as CODE."""
    constants = {path.name: rom_data.constants_of(path) for path in AES.scanned().values()}
    for site, row in CODE_IMMEDIATES.items():
        if row.owed_by is None:
            continue
        codes = {constants[row.owed_by][name] for name, kind in ROM_ADDRESSES_AS_DATA[row.owed_by].items() if kind == CODE}
        assert row.value in codes, f"${site:x}: {row.owed_by} does not list ${row.value:x} as CODE"


def test_a_planted_immediate_naming_aes_code_is_found(tmp_path):
    """The scan sees an immediate it was not told of: gr_setup's `move.l #$98a4,-(sp)` ($fe85b0) made to push
    just_draw — in a copy of the ROM — is the one new row."""
    planted, site, routine = tmp_path / "planted.img", 0xFE85B0, 0xFE9A88
    shutil.copyfile(rom_data.ROM_IMAGE, planted)
    with planted.open("r+b") as image:
        image.seek(site + aes.WORD_BYTES - rom_data.ROM_LO)
        image.write(struct.pack(">I", routine))
    found = code_immediates(planted)
    assert {at: value for at, value in found.items() if listed_immediates().get(at) != value} == {site: routine}
