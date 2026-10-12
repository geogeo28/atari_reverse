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
gr_wait, and the Line-F handler writes its own `movem` mask. A rebuilt ROM that re-lays those instructions changes
what they read. No obligation while the C uses the value; every one is an order to keep in mind.

THE SURFACES: a new ROM address in an AES source reds (a) until it is listed with its kind; a new immediate naming
AES code, a new pc-relative data reference, or a ROM value outside the text that is not AES data reds (b). Both
directions are proved to see a planted one (`test_a_planted_*`).

CONCURRENT WORK: each file's rows are its author's — a slice adding an AES source adds its file's entry here, and a
slice porting a routine of (b) names its file in that row's `owed_by`.
"""
import re
import shutil
import struct
from collections import namedtuple

from harness import BASE_IMAGE, _lib, addrs

import aes
import case
import rom_data
import routines
import transcription
from rom_data import CODE, DISTANCE, REGION_TABLE, RETURN_SITE, TABLE

AES = rom_data.component("aes")

# ---- (a) the sources --------------------------------------------------------------------------------------------
ROM_ADDRESSES_AS_DATA = {
    # The `trap #2` door's two hops the graphics bridge checks before it calls the VDI's C twin (`require_cpu_routine`):
    # the AES's handler in vector $88 and the VDI door it chains through $8c2a — and the `$a000` bridge's one, the
    # VDI's Line-A dispatcher in vector $28.
    "aes/gsx.h": {"GEM_TRAP2": CODE, "GEM_TRAP2_VDI_DOOR": CODE, "LINEA_ROM_DISPATCH": CODE},
    # The glue's parked return sites: __DOS's own (dos_free, dos_sdta, dos_close) and the four calls' `bsr __DOS`.
    # ...isdrive's two (its `bsr`s of dos_gdrv and dos_sdrv, parked through $fe3c28), pgmld's two and the empty command
    # tail it hands Pexec (a zero word of the text, inside pgmld's pinned region: a TEXT_TABLE of (b), row $fe39be;
    # the HOST's twin alone names it — the `.S` hands its own, the target's C a zero word of its own) — and the two handlers the vector
    # takes install BY VALUE: the AES's trap #2 handler and crit_err, the ROM's addresses on the host. On target
    # crit_err's is the build's own entry (`ALCYON_ROUTINE`; rows $fe3c8e, $fe3cb6 of (b)); the trap door's is the
    # build's own too since the narrow door flip (`ALCYON_ROUTINE`, and the `.S`'s two operands: rows $fe3c78,
    # $fe3c84 — `test_aes_trapdoor.py` holds that no word of a blob names the ROM's door). And crit_err's table,
    # which the twin reads in place — a row below it included, as the ROM's index reads it.
    "gemdosif.c": {"AES_DOS_TRAP_RETURN": RETURN_SITE, "AES_DOS_SFIRST_TRAP_RETURN": RETURN_SITE,
                   "AES_DOS_OPEN_TRAP_RETURN": RETURN_SITE, "AES_DOS_READ_TRAP_RETURN": RETURN_SITE,
                   "AES_DOS_LSEEK_TRAP_RETURN": RETURN_SITE, "AES_DOS_SNEXT_TRAP_RETURN": RETURN_SITE,
                   "AES_ISDRIVE_GDRV_RETURN": RETURN_SITE, "AES_ISDRIVE_SDRV_RETURN": RETURN_SITE,
                   "AES_PGMLD_PEXEC_RETURN": RETURN_SITE, "AES_PGMLD_MSHRINK_RETURN": RETURN_SITE,
                   "AES_PGMLD_EMPTY_TAIL": REGION_TABLE, "GEM_TRAP2": CODE, "AES_ROM_CRIT_ERR": CODE,
                   "AES_ROM_CRIT_ERR_ALERTS": REGION_TABLE},
    # (`gemdosif.S` names NO ROM address since the narrow door flip: the trap door's operand is `trapdoor.S`'s label
    # and crit_err's the file's own, each a `Relocated` of its pin.)
    # set_defdrv's two return sites from dos_sdrv, and desk_free's seven from dos_free (host arguments, as rsrc_free's).
    "deskleaf.c": {"AES_SET_DEFDRV_C_RETURN": RETURN_SITE, "AES_SET_DEFDRV_A_RETURN": RETURN_SITE},
    "deskmem.c": {"AES_DESK_FREE_FIRST_RETURN": RETURN_SITE, "AES_DESK_FREE_SECOND_RETURN": RETURN_SITE,
                  "AES_DESK_FREE_STACK_RETURN": RETURN_SITE, "AES_DESK_FREE_C82E_RETURN": RETURN_SITE,
                  "AES_DESK_FREE_GLOBALS_RETURN": RETURN_SITE, "AES_DESK_FREE_C85E_RETURN": RETURN_SITE,
                  "AES_DESK_FREE_C67A_RETURN": RETURN_SITE},
    # The `bsr.w` to the shared OB_ADDR helper, spelt as its displacement from each routine's own entry
    # (`BSR_W_TO_OB_ADDR`): a distance inside the optimize region the `.S` transcribes.
    "optimize.S": {"AES_ROM_FS_SGET": DISTANCE, "AES_ROM_FS_SSET": DISTANCE, "AES_ROM_INF_FLDSET": DISTANCE,
                   "AES_ROM_INF_GINDEX": DISTANCE, "AES_ROM_INF_WHAT": DISTANCE},
    # The ROM's resource bundle start-up copies, and rsrc_free's and rs_readit's return sites from dos_free and
    # dos_close (host arguments).
    "resource.c": {"AES_RSC_BUNDLE": TABLE, "AES_RS_FREE_MFREE_RETURN": RETURN_SITE,
                   "AES_RS_READIT_CLOSE_RETURN": RETURN_SITE},
    # gsx_setmb_aes hands vex_butv/vex_motv the AES's interrupt glue by its ROM address on the host (rows $fe884a/$fe8844
    # of (b)); on target, the glue the build links (`irq.S`). gsx_mfree's dos_free parks the word after its Line-F call.
    "gsxif.c": {"AES_ROM_BUTTON_GLUE": CODE, "AES_ROM_MOTION_GLUE": CODE, "AES_GSX_MFREE_RETURN": RETURN_SITE},
    # sh_find's return site from dos_sdta (a host argument, as rsrc_free's).
    "shell_find.c": {"AES_SH_FIND_SDTA_RETURN": RETURN_SITE},
    # newrect hands everyobj mkrect by its ROM address on the host ($fe5d68 `move.l #$fe5c9a,-(sp)`, row (b) below); on
    # target, its Alcyon entry (`wmupdate.S`).
    "wrect.c": {"AES_ROM_MKRECT": CODE},
    # draw_change hands everyobj newrect the same way ($fec146 `move.l #$fe5cee,-(sp)`, row (b) below).
    "wmupdate.c": {"AES_ROM_NEWRECT": CODE},
    # ob_draw's own walk hands its visit just_draw's ROM address on the host, the hook's key ($fea08c `move.l
    # #$fe9a88,-(sp)`, row (b) below); on target the visit calls the C just_draw and the address names nothing.
    "obdraw.c": {"AES_ROM_JUST_DRAW": CODE},
    # (`aes/evdoor.h` names NO ROM address as a value any more, and has no row: every entry is REBOUND — its wrapper
    # spelt through EVDOOR_REBOUND, which names no ROM routine on target; off it the address is only the hook's key
    # and the marker's value, pasted from the entry's name — and the call table its hop check named went with the
    # check, band 4 wave 3's retirement. An entry `jsr`ed at its ROM address again would red the census below.)
    # eralert's two tables, read in place (an error past them reads on, as the ROM's does), and the bell's Bconout: the
    # D0 the BIOS dispatcher would have jumped with, handed to its C core off target (`bios/bcon.h`).
    "fmdo.c": {"AES_ERALERT_STRINGS": TABLE, "AES_ERALERT_LEVELS": TABLE, "BIOS_BCONOUT": CODE},
    # The file selector's four strings and its redraw list, read in place, and its return sites through $fe3c28 —
    # fs_active's from dos_sdta and from the bell's Cconout, fs_input's six from dos_free (host arguments, as sh_find's).
    "fslib.c": {"AES_FS_DEFAULT_PATH": TABLE, "AES_FS_TITLE_TAIL": TABLE, "AES_FS_REDRAWN": TABLE,
                "AES_FS_FIRST_TITLE": TABLE, "AES_FS_EVERY_NAME": TABLE,
                "AES_FS_ACTIVE_SDTA_RETURN": RETURN_SITE, "AES_FS_ACTIVE_BELL_RETURN": RETURN_SITE,
                "AES_FS_INPUT_NAMES_ONLY_FREE_RETURN": RETURN_SITE, "AES_FS_INPUT_NAMES_FREE_RETURN_NO_DTA": RETURN_SITE,
                "AES_FS_INPUT_INDEX_FREE_RETURN_NO_DTA": RETURN_SITE, "AES_FS_INPUT_DTA_FREE_RETURN": RETURN_SITE,
                "AES_FS_INPUT_INDEX_FREE_RETURN": RETURN_SITE, "AES_FS_INPUT_NAMES_FREE_RETURN": RETURN_SITE},
    # ev_dclick's table of the five double-click rates' milliseconds, read in place — and, for a rate outside 0..4,
    # the ROM words round it, as the ROM's own index reads them.
    "evlib.c": {"AES_DCLICK_MS_TABLE": TABLE},
    # The FORK FUNCTIONS' addresses, a queue entry's code: what the ROM's own interrupts queue and the host's forkq
    # callers store — off target; on target each is the function's own entry (`staged_call.h`'s ALCYON_ROUTINE). Three
    # of the four: mchange is queued by the motion vector's glue (`irq.S`, which pushes the function's own entry) and
    # by a playback (`aes/aptape.h`, below).
    "aes/evfork.h": {"AES_ROM_KCHANGE": CODE, "AES_ROM_BCHANGE": CODE, "AES_ROM_TCHANGE": CODE},
    # ...the fourth, which a PLAYBACK queues from C (ap_tplay's mouse record; ap_trecd compares against all four) — and
    # the routine that draws nothing, which ap_tplay hands the VDI as its cursor and its motion routine: off target
    # the ROM's addresses, on target `aes_mchange_fork` and `aes_rom_justretf` (ALCYON_ROUTINE).
    "aes/aptape.h": {"AES_ROM_MCHANGE": CODE, "AES_ROM_JUSTRETF": CODE},
    # The opcode switch's graf_growbox and graf_shrinkbox arms NAME THEIR ROUTINE BY VALUE for the one `jsr (a0)` both
    # share (rows $fe6216 / $fe621e of (b)): off target the ROM's addresses, which the C's call resolves to the two
    # cores; on target the routines' own entries, called through the value (ALCYON_ROUTINE).
    "gemsuper.c": {"AES_ROM_GR_GROWBOX": CODE, "AES_ROM_GR_SHRINKBOX": CODE},
    # hctl_window's table of WM_ARROWED's actions by gadget — nine words past the text, read in place by the gadget's
    # index as the ROM's own `adda.l #$fef7d0` reads them (its other table, the seventeen gadget arms' addresses at
    # $fef7e2, is the C's `switch`: no value of it is named).
    "gemctrl.c": {"AES_ARROW_ACTIONS": TABLE},
    # ictlmgr hands pstart ctlmgr TWICE BY VALUE — where the process begins, and its load address (rows $fe4a7e /
    # $fe4a8c of (b)): off target the ROM's address, on target the build's entry `aes_rom_ctlmgr` (ALCYON_ROUTINE) —
    # and the process's name, the ROM's own string past the text, read in place by pd_nameit.
    "ctlmgr.c": {"AES_ROM_CTLMGR": CODE, "AES_SCRENMGR_NAME": TABLE},
    # ---- band 5 wave 3, slice L: the accessory loader ---- the thirteen return sites its Line-F calls of the glue park,
    # gotopgm handed pstart by value (row $fe437c of (b): the build's own entry on target), and the ROM's four strings —
    # C:'s root and pattern, then the kept search's (data outside every pinned region).
    "loader.c": {"AES_SNDCLI_CLOSE_RETURN": RETURN_SITE, "AES_LDACCS_GDRV_RETURN": RETURN_SITE,
                 "AES_LDACCS_SDTA_RETURN": RETURN_SITE, "AES_LDACCS_SDRV_C_RETURN": RETURN_SITE,
                 "AES_LDACCS_CHDIR_OF_C_RETURN": RETURN_SITE, "AES_LDACCS_SDRV_BACK_RETURN": RETURN_SITE,
                 "AES_LDACCS_CHDIR_RETURN": RETURN_SITE, "AES_LDACCS_FREE_RETURN": RETURN_SITE,
                 "AES_FREE_ACCS_FIRST_ENV_RETURN": RETURN_SITE, "AES_FREE_ACCS_FIRST_RETURN": RETURN_SITE,
                 "AES_FREE_ACCS_ENV_RETURN": RETURN_SITE, "AES_FREE_ACCS_BASEPAGE_RETURN": RETURN_SITE,
                 "AES_FREE_ACCS_PD_RETURN": RETURN_SITE, "AES_ROM_GOTOPGM": CODE,
                 "AES_ACC_ROOT_OF_C": TABLE, "AES_ACC_PATTERN_OF_C": TABLE, "AES_ACC_ROOT": TABLE, "AES_ACC_PATTERN": TABLE},
    # ---- end of slice L's ----
    # ---- band 5 wave 3, slice T: the trap door (`trapdoor.S`) --------------------------------------------------------
    # ub_trampoline's `jsr` of the desk's G_USERDEF draw code ($fe3f50), the ROM's own operand: band 6's routine, and
    # the one word of the door's region that still names the ROM (`test_aes_trapdoor.py`).
    "trapdoor.S": {"AES_ROM_DESK_USERDEF": CODE},
    # ---- end of slice T's block --------------------------------------------------------------------------------------
    # ---- band 5 wave 4, slice I: gemstart and geminit ----------------------------------------------------------------
    # WHAT gem_entry COPIES, carried as the ROM's own data (ruling W4-R3: the Line-F call table stays the ROM's): the
    # handler's `movea.l #$fee900` — the table's address, inside the region the `.S` pins — and the table's first nine
    # entries with the high word of its tenth, ROM routines' addresses nothing of a build executes or reads
    # (`test_aes_gemstart.py` pins the hundred bytes with NO relocation). gem_entry's own four by-value operands (rows
    # $fd9f4a, $fd9f86, $fd9f92, $fd9f9e of (b)) are NOT here: each is the build's symbol, a `Relocated` of its pin.
    "gemstart.S": {"AES_LINEF_TABLE": REGION_TABLE, "AES_ROM_GSX_1CODE": CODE, "AES_ROM_BB_FILL": CODE,
                   "AES_ROM_GSX_TCALC": CODE, "AES_ROM_GR_JUST": CODE, "AES_ROM_GSX_TBLT": CODE, "AES_ROM_GSX_ATTR": CODE,
                   "AES_ROM_GSX_BLT": CODE, "AES_ROM_GSX_MOFF": CODE, "AES_ROM_GR_INSIDE": CODE, "AES_ROM_GSX_BOX": CODE},
    # The INF reader's seven return sites (its Line-F calls of the glue park them: host arguments, as the loader's) and
    # the ROM's four strings it hands the glue — the root and the file's name, once for the current drive and once for
    # C: (data past the text, outside every pinned region).
    "geminit.c": {"AES_READ_INF_GDRV_RETURN": RETURN_SITE, "AES_READ_INF_CHDIR_RETURN": RETURN_SITE,
                  "AES_READ_INF_SDRV_C_RETURN": RETURN_SITE, "AES_READ_INF_CHDIR_OF_C_RETURN": RETURN_SITE,
                  "AES_READ_INF_CLOSE_RETURN": RETURN_SITE, "AES_READ_INF_SDRV_BACK_RETURN": RETURN_SITE,
                  "AES_READ_INF_FREE_RETURN": RETURN_SITE, "AES_INF_ROOT": TABLE, "AES_INF_NAME": TABLE,
                  "AES_INF_ROOT_OF_C": TABLE, "AES_INF_NAME_OF_C": TABLE},
    # ---- end of slice I's block --------------------------------------------------------------------------------------
    # ---- band 5 wave 4, slice SH: the shell's loop and the desk door ----------------------------------------------------
    # THE DESK DOOR'S FIVE (`aes/deskdoor.h`): the ROM's own deskmain and the desk's four built-ins, each called at
    # its ROM address — on target the operand of the build's ONE `jsr` of it (`bench/tier3.py`,
    # ROM_CALLS_OWED_TO_A_LATER_BAND), off it the door hook's key. Band 6's, until each has a body of ours. deskmain's
    # is spelt in the header's own wrapper; the four are the arguments sh_cmd hands the door.
    "aes/deskdoor.h": {"AES_ROM_DESKMAIN": CODE},
    # ...and sh_main's and sh_cmd's own: sh_show handed sh_find by value (row $feb272 of (b): off target the ROM's
    # address, the hook's key; on target the build's entry, `ALCYON_ROUTINE`), the return site sh_main's Getrez parks
    # through trp14 (a host argument), and the ROM's string sh_cmd's `$fd` heads the command line with, read in place.
    "shell.c": {"AES_ROM_DESK_SHOW_FILE": CODE, "AES_ROM_DESK_PRINT_FILE": CODE, "AES_ROM_DESK_FORMAT": CODE,
                "AES_ROM_DESK_COPY_DISK": CODE, "AES_ROM_SH_SHOW": CODE, "AES_SH_MAIN_GETREZ_RETURN": RETURN_SITE,
                "AES_SH_PRINTING_TEXT": TABLE},
    # ---- end of slice SH's block ---------------------------------------------------------------------------------------
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
    # (owed by the file that SHIPS: the transcription, whose two trap-door operands are still the ROM's — the rule
    # below. crit_err's two are the build's own since wave 3: the `.S`'s operand a `Relocated` of its pin, the
    # twins' an ALCYON_ROUTINE of `gemdosif.c`, which the rows now name.)
    0xFE3C78: Immediate(0xFE3EA6, "install_trap2: the AES's `trap #2` handler into vector $88", "gemdosif.c"),
    0xFE3C84: Immediate(0xFE3EA6, "retake: the same handler into $88 again, then the critic's install", "gemdosif.c"),
    0xFE3C8E: Immediate(0xFE3CBE, "retake: the critical-error handler, Setexc($101)", "gemdosif.c"),
    0xFE3CB6: Immediate(0xFE3CBE, "takeerr: the critical-error handler installed", "gemdosif.c"),
    0xFE3F00: Immediate(0xFE65AA, "gem_trap2_aes: aes_entry, into A0"),
    0xFE437C: Immediate(0xFE38B0, "sndcli: gotopgm, where an accessory's process begins (pstart's first, psetup's PC)", "loader.c"),
    0xFE4A7E: Immediate(0xFE49D2, "ictlmgr: ctlmgr as the screen manager's load address (pstart's third)", "ctlmgr.c"),
    0xFE4A8C: Immediate(0xFE49D2, "ictlmgr: ...and as where its process begins (pstart's first, psetup's PC)", "ctlmgr.c"),
    0xFE5D68: Immediate(addrs.AES_ROM_MKRECT, "newrect: mkrect, everyobj's routine", "wrect.c"),
    0xFE6216: Immediate(0xFE8340, "aes_dispatch, its graf_growbox arm: gr_growbox, into A0 for `jsr (a0)`", "gemsuper.c"),
    0xFE621E: Immediate(0xFE837A, "aes_dispatch, its graf_shrinkbox arm: gr_shrinkbox, the same", "gemsuper.c"),
    0xFE6698: Immediate(0xFED424, "ap_tplay: the bare `rts` as a vex routine (set_contrl_ptr)", "aes/aptape.h"),
    0xFE66B6: Immediate(0xFED424, "ap_tplay: ...and again", "aes/aptape.h"),
    0xFE8844: Immediate(addrs.AES_ROM_MOTION_GLUE, "gsx_setmb_aes: the mouse-motion interrupt glue, for vex_motv", "gsxif.c"),
    0xFE884A: Immediate(addrs.AES_ROM_BUTTON_GLUE, "gsx_setmb_aes: the button interrupt glue, for vex_butv", "gsxif.c"),
    0xFEA08C: Immediate(addrs.AES_ROM_JUST_DRAW, "ob_draw: just_draw, everyobj's routine", "obdraw.c"),
    0xFEB272: Immediate(0xFEADDC, "sh_main: sh_find's optional routine", "shell.c"),
    0xFEC146: Immediate(addrs.AES_ROM_NEWRECT, "draw_change: newrect, everyobj's routine", "wmupdate.c"),
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
    0xFE84CA: PcRelative(0xFE85B2, CODE_BYTES, "gr_watchbox: gr_setup's `move.l #` immediate, read (grwait.c: its value)"),
    0xFE85CE: PcRelative(0xFE8586, CODE_BYTES, "gr_rubbox: gr_wait's `move.l #` immediate, read (grdrag.c: its value)"),
    0xFE869C: PcRelative(0xFE8586, CODE_BYTES, "gr_dragbox: ...the same immediate, read (grdrag.c: its value)"),
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
    """A row of (b) a port now owes names its file — BY ITS KEY IN CENSUS (a): a source's name, a header's
    `aes/<name>.h` — whose census lists the routine as CODE."""
    constants = {key: rom_data.constants_of(path) for key, path in AES.scanned().items()}
    for site, row in CODE_IMMEDIATES.items():
        if row.owed_by is None:
            continue
        codes = {constants[row.owed_by][name] for name, kind in ROM_ADDRESSES_AS_DATA[row.owed_by].items() if kind == CODE}
        assert row.value in codes, f"${site:x}: {row.owed_by} does not list ${row.value:x} as CODE"


# A BY-VALUE SITE A TRANSCRIPTION CARRIES AS THE ROM'S OWN OPERAND IS RIGHT ONLY WHILE ITS TARGET HAS NO BODY OF
# OURS. A `.S` that ships the ROM's bytes ships the ROM's ADDRESS of whatever an immediate names (gemdosif.S: the
# AES's `trap #2` handler and crit_err, installed into the vectors); the day the build links its own entry for that
# routine — a `.S` transcription or a C core — the vector must hold THAT, the operand becomes the build's symbol and
# the byte pin a `Relocated` at the site. Nothing else would say so: the pin stays green on the ROM's bytes.
def entries_of_ours_for(target, symbols=None, cores=None):
    """The entries the build has for the ROM routine at `target`: a `.S` transcription's in the bench's blob
    (`symbols`), a C core's in the candidate library (`cores`: a `hasattr`) — under every routine name `addrs.h`
    gives that address."""
    symbols = transcription.bench().symbols if symbols is None else symbols
    cores = _lib if cores is None else cores
    names = [name for name in dir(addrs) if getattr(addrs, name) == target and routines.is_routine(name, (routines.AES_PREFIX,))]
    return sorted({name.lower() for name in names if name.lower() in symbols}
                  | {routines.core_symbol(name) for name in names if hasattr(cores, routines.core_symbol(name))})


def test_a_site_a_transcription_owes_names_a_routine_the_build_has_no_body_of():
    """Every row of (b) owed by a `.S` is held to it: its target has no entry of ours. THE DAY ONE LANDS this reds by
    site — relocate the operand in the `.S`, declare the `Relocated` in its pin, and take the row's `.S` out of the
    ROM-address census (a). NONE IS OWED BY A `.S` TODAY: crit_err's two were relocated in wave 3 (slice G) and the
    trap door's two at the narrow door flip (slice F; the list that excused them while the door was linked and not
    installed, `LINKED_AND_INSTALLED_AT_THE_FLIP`, is gone with it)."""
    owed = {site: row for site, row in CODE_IMMEDIATES.items() if row.owed_by and row.owed_by.endswith(".S")}
    assert not owed, f"a `.S` names a ROM routine by value again: {sorted(map(hex, owed))}"
    linked = {f"${site:x}": entries_of_ours_for(row.value) for site, row in owed.items() if entries_of_ours_for(row.value)}
    assert not linked, f"the `.S` still installs the ROM's address of a routine the build now has: {linked}"


def test_no_transcription_spells_the_rom_s_trap_door_or_crit_err():
    """ITS RED, off the sources: `gemdosif.S` — the one `.S` that installs handlers by value — spells neither ROM
    address; an operand put back (`#GEM_TRAP2`) is found by the token."""
    source = (transcription.BENCH_ELF.parents[2] / "src" / "aes" / "gemdosif.S").read_text()
    code = "\n".join(line.split("/*")[0] for line in source.split(" */", 1)[1].splitlines())
    assert "aes_rom_trap2" in code and "aes_rom_crit_err" in code
    assert not {"GEM_TRAP2", "AES_ROM_TRAP2", "AES_ROM_CRIT_ERR"} & set(re.findall(r"#(\w+)", code))


def test_that_rule_sees_an_entry_of_either_kind():
    """ITS RED: retake has both a `.S` entry and a C core — and so, since wave 3, has crit_err (which is why its two
    sites are relocated); the trap door has its `.S` entry alone (slice T: linked, declared above until the flip
    installs it). Each kind is seen alone."""
    assert entries_of_ours_for(addrs.AES_ROM_RETAKE) == ["aes_retake", "aes_rom_retake"]
    assert entries_of_ours_for(addrs.AES_ROM_CRIT_ERR) == ["aes_crit_err", "aes_rom_crit_err"]
    assert entries_of_ours_for(addrs.GEM_TRAP2) == ["aes_rom_trap2"]
    no_core = object()
    assert entries_of_ours_for(addrs.AES_ROM_CRIT_ERR, symbols={}, cores=no_core) == []
    assert entries_of_ours_for(addrs.AES_ROM_CRIT_ERR, symbols={"aes_rom_crit_err": 0}, cores=no_core) == ["aes_rom_crit_err"]
    assert entries_of_ours_for(addrs.AES_ROM_CRIT_ERR, symbols={}) == ["aes_crit_err"]


# ---- AN ENTRY'S KIND IS WHAT THE ROM'S TEXT SAYS IT IS (T8) -----------------------------------------------------------
# The census (a) lists each ROM address with its kind, and nothing read the kind back: a RETURN_SITE relabelled CODE
# passed. Held here for the addresses inside the AES's text (the BIOS's and the VDI's are their components'):
#   * a RETURN_SITE is the instruction AFTER A CALL — a `bsr`, a `jsr`, a `trap`, or a Line-F CALL word (even);
#   * CODE is A ROUTINE'S ENTRY — the instruction after an unconditional exit: `rts`, `rte`, `jmp`, `bra`, or a
#     Line-F RETURN word (odd).
_CALLS = re.compile(r"(?:bsr[sw]?|jsr|trap)\b")
_EXITS = re.compile(r"(?:rts|rte|jmp|bra[sw]?)\b")
LINE_F_RETURN_BIT = 1


def _before(address):
    """`(is `address` an instruction's start, the instruction before it: its address and text — None a Line-F word)`."""
    listing = rom_data.instructions(TEXT_LO, TEXT_HI)
    starts = [start for start, _text in listing]
    if address not in starts:
        return False, None, None
    return (True, *listing[starts.index(address) - 1])


def kind_in_the_text(address):
    """RETURN_SITE, CODE or None: what the instruction before `address` makes of it (above)."""
    at_a_start, before, text = _before(address)
    if not at_a_start:
        return None
    if text is None:
        return CODE if case.word_in(BASE_IMAGE, before) & LINE_F_RETURN_BIT else RETURN_SITE
    return RETURN_SITE if _CALLS.match(text) else CODE if _EXITS.match(text) else None


def test_a_listed_address_is_of_the_kind_the_text_makes_it():
    constants = {key: rom_data.constants_of(path) for key, path in AES.scanned().items()}
    wrong = {(key, name): (kind, kind_in_the_text(constants[key][name]))
             for key, table in ROM_ADDRESSES_AS_DATA.items() for name, kind in table.items()
             if kind in (CODE, RETURN_SITE) and TEXT_LO <= constants[key][name] < TEXT_HI
             and kind_in_the_text(constants[key][name]) != kind}
    assert not wrong, f"listed as one kind, and the ROM's text makes it another: {wrong}"


def test_a_relabelled_entry_is_told_apart():
    """ITS RED: a return site is no routine's entry and an entry no return site; an address inside an instruction
    is neither."""
    assert kind_in_the_text(addrs.AES_DOS_TRAP_RETURN) == RETURN_SITE != CODE == kind_in_the_text(addrs.AES_ROM_KCHANGE)
    assert kind_in_the_text(addrs.AES_DESK_FREE_FIRST_RETURN) == RETURN_SITE, "after a Line-F call word"
    assert kind_in_the_text(addrs.AES_ROM_MKRECT) == CODE, "after a Line-F return word"
    assert kind_in_the_text(addrs.AES_DOS_TRAP_RETURN - aes.WORD_BYTES) is None


def _the_c_routine_holding(site):
    """The `addrs.h` name of THE AES ROUTINE WITH A C CORE whose ROM body holds the instruction at `site`, or None: the
    nearest entry at or below it that the candidate library exports a core of, where its body — to its one exit
    (`rom_body`) — reaches the site. A routine between the two that is not C ends the nearer one's body first."""
    from test_aes_evfork_interrupted import rom_body

    in_c = {getattr(addrs, name): name for name in dir(addrs)
            if routines.is_routine(name, (routines.AES_PREFIX,)) and hasattr(_lib, routines.core_symbol(name))}
    at_or_below = [entry for entry in in_c if entry <= site]
    if not at_or_below:
        return None
    entry = max(at_or_below)
    last_instruction, _length, _text = rom_body(entry)[-1]
    return in_c[entry] if site <= last_instruction else None


def test_a_row_is_owed_by_a_file_exactly_when_its_routine_is_c():
    """THE RULE `owed_by` STANDS ON, which nothing held (ap_tplay's two rows stood "owed by nobody" beside its C): a
    row whose routine HAS A C CORE names the file whose C owes the value, and a row that names a file is of a
    routine that has one. A port that forgets its rows reds here, by site."""
    held_by = {site: _the_c_routine_holding(site) for site in CODE_IMMEDIATES}
    forgotten = {f"${site:x}": held_by[site] for site, row in CODE_IMMEDIATES.items() if held_by[site] and row.owed_by is None}
    assert not forgotten, f"rows of routines that are C, owed by nobody: {forgotten} — name the file (`owed_by`)"
    unported = {f"${site:x}": row.owed_by for site, row in CODE_IMMEDIATES.items() if row.owed_by and not held_by[site]}
    assert not unported, f"rows owed by a file whose routine has no C core: {unported}"


def test_the_routine_holding_a_site_is_read_off_the_rom_s_own_text():
    """...AND THAT RULE'S OWN RED: ap_tplay's first immediate lies in ap_tplay, which is C; the instruction after
    ap_tplay's exit lies in no C routine's body though an entry with a core stands below it (ap_tplay's own); and
    gem_entry's lie below every C core; ictlmgr's two lie in ictlmgr, C since band 5 wave 2, and NOT in ctlmgr, the
    entry below it, which never exits; the opcode switch's two lie in two of its ARMS — labels inside the one
    routine, 1,866 bytes to its one exit."""
    assert _the_c_routine_holding(0xFE6698) == "AES_ROM_AP_TPLAY" == _the_c_routine_holding(addrs.AES_ROM_AP_TPLAY)
    assert addrs.AES_ROM_AP_TPLAY < addrs.AES_ROM_AP_TRECD - aes.WORD_BYTES
    assert _the_c_routine_holding(addrs.AES_ROM_AP_TRECD - aes.WORD_BYTES) == "AES_ROM_AP_TPLAY"    # its exit, the last word
    assert _the_c_routine_holding(0xFD9F86) is None
    assert _the_c_routine_holding(0xFE4A7E) == "AES_ROM_ICTLMGR" == _the_c_routine_holding(0xFE4A8C)
    # ...and PAST THE NEAREST CORE'S EXIT IS NOBODY'S (the pin ictlmgr's rows held until it was C): ctlmgr's own entry
    # and its loop's top have a core below them — ct_chgown, the nearest — whose body ended before either.
    assert _the_c_routine_holding(addrs.AES_ROM_CTLMGR) is None and _the_c_routine_holding(addrs.AES_ROM_CTLMGR_LOOP) is None
    assert max(entry for entry in (getattr(addrs, name) for name in dir(addrs) if routines.is_routine(name, (routines.AES_PREFIX,))
                                   and hasattr(_lib, routines.core_symbol(name))) if entry <= addrs.AES_ROM_CTLMGR) == addrs.AES_ROM_CT_CHGOWN
    assert _the_c_routine_holding(0xFE6216) == "AES_ROM_DISPATCH" == _the_c_routine_holding(0xFE621E)    # two of its arms


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
