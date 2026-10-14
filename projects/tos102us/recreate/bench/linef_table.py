"""THE LINE-F CALL TABLE OF OURS — `src/aes/lineftable.S`, GENERATED: the table and the thunks behind it.

    python bench/linef_table.py src/aes/lineftable.S     # rewrites the checked-in file (only when its text changes)

GEM's own code calls itself by Line-F words: `$F000 | offset` is a CALL through the longword at that offset of the
ROM's table (`AES_LINEF_TABLE`, `$fee900`: 658 entries), which the handler gem_entry copies to RAM indexes by ONE
operand (`aes_rom_linef_handler + LINEF_TABLE_OPERAND`). The desk — band 6's, the ROM's own text until each routine is
ported — reaches the AES through that table and nothing else, and reaches ITSELF through it too. So a table of ours
is the opening the ROM's desk runs over our AES by, and the desk's flip registry afterwards: one entry a routine.

THE VERDICT OF AN ENTRY IS DERIVED, never listed — from the ROM's own longword and what this build DECLARES for the
routine it names (`entries`):

  * OURS, NATIVE — the routine has an entry of the build that is entered as the ROM's is: a byte-pinned `.S`
    (`include/transcribed.h`'s rows; the switch's, the trap door's and gemstart's tables in `test/transcription.py`).
    The longword is that symbol. It comes FIRST: a transcribed routine has a C twin too, and what ships is the `.S`.
  * OURS, THROUGH A THUNK — the routine has a C core with a declared Alcyon signature (`vdi.declare_alcyon`: the one
    statement every battery pushes its frame by). No C core is Line-F-callable — a ROM caller pushes WORDS and
    LONGWORDS, GCC reads a longword slot an argument, the image base first — so the longword is a generated thunk
    (`linef_to_<core>`) that re-pushes the caller's frame as GCC's and `jsr`s the core. One thunk a core, however
    many entries name it. The thunk is `bench/shipped_glue.py`'s Alcyon body run backwards.
  * THE ROM'S — everything else: the ROM's own longword, as the data it is. Band 6's routines, each until it is ported
    — and the two routines of ours NO ROM CALLER MAY ENTER (`ENTERED_BY_OURS_ALONE`: the shell's loop and its command
    arm, whose desk door counts the C frames above it).

A HOST ARGUMENT (`declare_alcyon`'s `host_arguments`: the return site a GEMDOS glue entry parks) is the one C argument
no frame carries. The thunk hands THE REAL ONE: its own return address — the word after the caller's Line-F call word,
which is what the ROM's glue pops there.

NOTHING IS BOUND BY THIS FILE (band 6 wave 0, slice T): the table and its thunks are LINKED into both blobs, and no
word of a blob names them. The operand that would — gemstart.S's EIGHTH relocation — is DECLARED PENDING below
(`PENDING_BINDING`) and made by slice B; until then a machine reaches the table through a LABELLED STAGING alone
(`test/test_aes_lineftable.py` lays the operand in its own machines).

WHY THE `.S` IS CHECKED IN AND NOT MADE BY THE BUILD: kit.mk sweeps `src/*/*.S` when make READS the makefile, and the
census, the build contract's lists and the kept derivations' tree key read the sources at import — a file a rule made
later would be missing from each. And an entry's verdict moves only at a FLIP: the generated file's diff is that
flip's record. `test_aes_lineftable.py` holds the checked-in text EQUAL to `text()`, so it is never edited by hand.
"""
import importlib
import sys
from collections import namedtuple
from pathlib import Path

RECREATE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RECREATE.parents[2] / "tools"))     # reverse/tools — the shared recreate kit
sys.path.insert(0, str(RECREATE / "test"))                 # ...and the declarations the table derives from

from recreate_kit import project                           # noqa: E402
project.load(RECREATE)

from harness import BASE_IMAGE, addrs                      # noqa: E402
import aes                                                 # noqa: E402
import case                                                # noqa: E402
import routines                                            # noqa: E402
# Every battery, so every Alcyon signature is declared before a verdict asks for one (`bench/shipped_glue.py`'s import,
# for its reason): a table derived over half the declarations would leave the rest of the entries the ROM's in silence.
import test_boot_snapshot                                  # noqa: E402,F401
import transcription                                       # noqa: E402
import vdi                                                 # noqa: E402

SOURCE = RECREATE / "src" / "aes" / "lineftable.S"
TABLE_SYMBOL = transcription.LINEF_TABLE_SYMBOL
THUNK_PREFIX = transcription.LINEF_THUNK_PREFIX
ENTRIES = aes.AES_LINEF_TABLE_ENTRIES
LINE_F_CALL = 0xF000                    # a call word: `LINE_F_CALL | the entry's byte offset`
LONG_BYTES = vdi.LONG_BYTES

OURS_NATIVE, OURS_THROUGH_A_THUNK, THE_ROM_S = "ours, native", "ours, through a thunk", "the ROM's"
Entry = namedtuple("Entry", "index target verdict symbol routine")
Entry.__doc__ = """One entry of the table: its `index` (its call word is `call_word(index)`), the ROM routine the
ROM's table names there (`target`), the `verdict`, the blob `symbol` our longword is (None: the ROM's own address)
and the `addrs.h` name of the `routine` a thunk's core is declared under (None for every other verdict)."""

# gemstart.S's EIGHTH RELOCATION, DECLARED AND NOT MADE (the wave-2/3 groundwork pattern, by name): the operand of the
# handler gem_entry copies. It STAYS THE ROM'S in every shipped byte until slice B binds it — that is ruling W6-R1,
# the user's — and with it go the registry's table kind (`$cc24`, the blob's 658 slots) and every row that changes
# shore. Declared HERE and not in `aes_event.DECLARED_NOT_YET_MAPPED_AT_TIER3`: five tests and STATUS.md pin that
# registry's pending list EMPTY, and a line of slice T's must change no existing test.
Pending = namedtuple("Pending", "what symbol offset holds will_hold waits_for")
PENDING_BINDING = Pending(
    "the call table's address in the Line-F handler gem_entry copies (`movea.l #$fee900,a0`, `$fee8d6`)",
    "aes_rom_linef_handler", aes.LINEF_TABLE_OPERAND, aes.AES_LINEF_TABLE, TABLE_SYMBOL,
    "band 6 wave 0, slice B (THE BINDING: ruling W6-R1 is the user's)")


def call_word(index):
    """The Line-F word that calls entry `index`."""
    return LINE_F_CALL | index * LONG_BYTES


def rom_table():
    """The ROM's own table: the routine each of its entries names."""
    return [case.long_in(BASE_IMAGE, aes.AES_LINEF_TABLE + index * LONG_BYTES) for index in range(ENTRIES)]


def native_entries():
    """`{the ROM routine: the build's entry that is entered as the ROM's is}` — every byte-pinned `.S` entry: the
    transcribed table's rows, and the switch's, the trap door's and gemstart's."""
    native = {getattr(addrs, transcription.transcription_routine(entry)): entry for entry in transcription.TRANSCRIBED}
    for table in (transcription.SWITCH_ENTRIES, transcription.TRAPDOOR_ENTRIES, transcription.GEMSTART_ENTRIES):
        for entry, row in table.items():
            assert native.setdefault(row.rom, entry) == entry, f"${row.rom:x} is two entries of the build"
    return native


def every_declaration_made():
    """EVERY MODULE THAT DECLARES A SIGNATURE, IMPORTED — the registry's import reaches all but two (measured:
    `aes_shmain`, sh_main's and sh_cmd's; `test_aes_crit_err`), and a verdict must not turn on which test module
    happened to be imported first: found by the call they make, not listed."""
    for module in sorted(RECREATE.glob("test/*.py")):
        if "declare_alcyon(" in module.read_text() and module.stem not in sys.modules:
            importlib.import_module(module.stem)


def declared_cores():
    """`{the ROM routine: its `addrs.h` name}` for every routine whose C core has a declared Alcyon signature."""
    every_declaration_made()
    declared = {}
    for name in vdi.ALCYON:
        address = getattr(addrs, name)
        assert declared.setdefault(address, name) == name, f"${address:x} is declared twice: {declared[address]}, {name}"
    return declared


# THE TWO ROUTINES OF OURS THE TABLE DOES NOT OFFER, each with a declared signature a thunk could follow: the shell's
# loop and its command arm. Their calls of the ROM's desk go through the desk door, which holds the ROM's own stack
# depth by COUNTING THE C FRAMES between gem_main and the door (`test_aes_shell_door.py`: sh_cmd is called from
# sh_main's own body and from nowhere else) — a ROM caller's frame under them would be a depth nobody counted. And
# none exists: every Line-F call of either lies in a routine that is ours already (gem_main's of sh_main, sh_main's of
# sh_cmd — `test_aes_lineftable.py` holds that off the ROM's text). So their entries stay THE ROM'S, dead on a machine
# of ours, until the desk door goes with its last ROM callee.
ENTERED_BY_OURS_ALONE = {
    "AES_ROM_SH_MAIN": "the shell's loop: called by gem_main alone, which is ours",
    "AES_ROM_SH_CMD": "the shell's command arm: called by sh_main alone, which is ours",
}

# ---- band 6 wave 1a ----
# THE ROUTINES OF BAND 6 THAT ARE WRITTEN, LINKED AND NOT YET FLIPPED: each has a C core and a declared signature — a
# thunk could be made — and its entry STAYS THE ROM'S BY DECLARATION until the band's opening is ruled (W6-R1: the
# table bound first, or the desk ported against the ROM's AES and the table last). Held at Tier 1 meanwhile; a
# routine leaves this list at its flip, and the generated file's diff is that flip's record. `{routine: why}`.
LINKED_AND_NOT_FLIPPED = {}
# ---- unit D: the desk's AES bindings and desk_wait (`src/desk/deskbind.c`, `test/aes_deskbind.py`) ----
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_DESK_{binding}": "unit D: a binding of the desk's, held at Tier 1 at its arrivals" for binding in (
    "APPL_INIT", "APPL_BVSET", "APPL_EXIT", "APPL_WRITE", "EVNT_MULTI", "EVNT_BUTTON", "EVNT_DCLICK", "FORM_DO", "FORM_DIAL",
    "FORM_ALERT", "FORM_ERROR", "FORM_CENTER", "GRAF_MOUSE", "GRAF_RUBBOX", "GRAF_MKSTATE", "GRAF_GROWBOX", "GRAF_SHRINKBOX",
    "MENU_TNORMAL", "MENU_BAR", "MENU_ICHECK", "MENU_IENABLE", "OBJC_OFFSET", "OBJC_ORDER", "OBJC_FIND", "OBJC_ADD", "OBJC_DRAW",
    "OBJC_CHANGE", "RSRC_GADDR", "SHEL_WRITE", "SHEL_GET", "SHEL_PUT", "WIND_CLOSE", "WIND_DELETE", "WIND_FIND", "WIND_UPDATE",
    "WIND_CREATE", "WIND_OPEN", "WIND_GET", "WIND_SET", "WIND_CALC", "WAIT")})
# ---- end of unit D's ----
# ---- unit O: the desk's leaves filed in AES modules (`src/desk/deskleaf.c`, `test/aes_deskleaves.py`) ----
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_{leaf}": "unit O: a desk-only leaf filed in an AES module, held at Tier 1 at its arrivals" for leaf in (
    "GSX_PLINE", "APP_ALLOC", "APP_FREE", "DOS_WRITE", "DOS_GDIR", "DOS_MKDIR", "DOS_SETDT", "DOS_LABEL", "DOS_SPACE", "DOS_RENAME",
    "DOS_AVAIL", "DOS_RAWCIO", "DOS_CHMOD", "DOS_DELETE", "DOS_RMDIR", "DOS_CREATE", "GSX_HARDCOPY", "TRP13")})
# ---- end of unit O's ----
# ---- end of band 6 wave 1a's ----
# ---- band 6 wave 1b: one `.update({...})` PER UNIT inside its group's own block, the group's names only ----
# ---- band 6 wave 1b, group G1 (units I `src/desk/deskwin.c`, L `src/desk/deskview.c`) ----
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_{routine}": "unit I: the desk's window objects and program leaves, held at Tier 1 at its arrivals"
                               for routine in ("OBJ_INIT", "OBJ_WALLOC", "OBJ_WFREE", "OBJ_IALLOC", "PRO_CHDIR", "PRO_CMD", "PRO_EXEC",
                                               "DESK_RSRC_LOAD", "INI_TREE", "INI_STR", "DO_WREDRAW", "GET_XYWH", "GET_SPEC", "DO_XYFIX",
                                               "ZOOM_CLOSED", "DO_WFULL")})
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_{routine}": "unit L: the desk's view and its layout leaves, held at Tier 1 at its arrivals"
                               for routine in ("WIN_VIEW", "WIN_START", "WIN_ALLOC", "WIN_FREE", "WIN_FIND", "WIN_TOP", "WIN_ONTOP",
                                               "WIN_CNT", "WIN_ITH", "WIN_OCALC", "WIN_ICALC", "WIN_BLDVIEW", "WIN_SHWALL", "WIN_ISEL",
                                               "WIN_INAME", "WIN_SINFO", "WIN_SNAME")})
# ---- end of group G1's ----
# ---- band 6 wave 1b, group G2 (units A `src/desk/deskapp.c`, K `src/desk/desktop.c`, J `src/desk/desksupp.c`) ----
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_{routine}": "unit A: the desk's application list, held at Tier 1 at its arrivals" for routine in (
    "SCAN_STR", "SAVE_STR", "APP_PARSE", "APP_TRAN", "APP_RDICON", "APP_GETFH", "SNAP_DISK", "APP_REVIT", "APP_PATH_SAVE", "APP_PATH_RESTORE",
    "APP_BLDDESK")})
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_{routine}": "unit K: the desk's main loop's helpers, held at Tier 1 at their arrivals" for routine in (
    "I_FIND", "MEN_LIST", "MEN_UPDATE", "DO_VIEWMENU", "CNX_PUT")})
LINKED_AND_NOT_FLIPPED.update({"AES_ROM_DRIVE_CHECK": "unit J: drive_check, held at Tier 1 at its arrivals, its floppy driver replayed"})
# ---- end of group G2's ----
# ---- band 6 wave 1b, group G3 (units B `src/desk/deskact.c`, G `src/desk/deskfpd.c`) ----
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_{routine}": "unit B: a hit test or drag of the desk's, held at Tier 1 at its arrivals" for routine in (
    "APP_AFIND", "GR_OBFIND", "GR_ISDOWN", "GR_ACCOBS", "GR_EXTENT", "GR_OBALIGN", "GR_PLNS", "GR_BWAIT", "ACT_CHKOBJ",
    "MOVE_DRVICON", "ACT_CHG", "ACT_ALLCHG")})
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_{routine}": "unit G: a path or file node routine of the desk's, held at Tier 1 at its arrivals" for routine in (
    "FN_INIT", "PN_INIT", "FPD_START", "FPD_BLDSPEC", "FPD_PARSE", "FPD_OFIND", "FPD_ELIST", "FN_FREE", "FL_FREE", "FN_ALLOC",
    "PN_ALLOC", "PN_FREE", "PN_OPEN", "PN_FCOMP", "PN_COMP", "PN_SORT")})
# ---- end of group G3's ----
# ---- band 6 wave 1b, group G4 (units C `src/desk/deskdir.c`, H `deskfun.c`, E `deskusr.c`, F `deskinf.c`) ----
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_DESK_{routine}": "unit C: the copy engine's helpers, held at Tier 1 at their arrivals" for routine in (
    "DRAW_DIAL", "DO_NAMECON", "HIDE_DIAL", "SHOW_DIAL", "DRAW_FLD", "ADD_PATH", "SUB_PATH", "ADD_FNAME", "DEL_FNAME", "GET_FNAME",
    "D_ERRMSG", "D_DOFDEL", "PATH_PART", "PAR_CHK")})
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_DESK_{routine}": "unit H: the desk's alert and its message to itself, held at Tier 1 at their arrivals"
                               for routine in ("FUN_ALERT", "FUN_MSG")})
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_DESK_{routine}": "unit E: the text view's line and its formatters, held at Tier 1 at their arrivals"
                               for routine in ("MY_ITOA", "FMT_TIME", "FMT_DATE", "OB_SFCB")})
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_DESK_{routine}": "unit F: an info dialog's fields, held at Tier 1 at their arrivals"
                               for routine in ("INF_FIELD", "INF_DTTMSZ")})
# ---- end of group G4's ----
# ---- end of band 6 wave 1b's ----


def thunk_symbol(routine):
    """The thunk a ROM caller's Line-F call of `routine` lands in."""
    return THUNK_PREFIX + routines.core_symbol(routine)


def entries():
    """The 658 entries, each with its verdict (the module's docstring)."""
    native, declared = native_entries(), declared_cores()
    made = []
    for index, target in enumerate(rom_table()):
        if target in native:
            made.append(Entry(index, target, OURS_NATIVE, native[target], None))
        elif target in declared and declared[target] not in ENTERED_BY_OURS_ALONE and declared[target] not in LINKED_AND_NOT_FLIPPED:
            made.append(Entry(index, target, OURS_THROUGH_A_THUNK, thunk_symbol(declared[target]), declared[target]))
        else:
            made.append(Entry(index, target, THE_ROM_S, None, None))
    return made


def thunked_routines():
    """Every routine a thunk is generated for, in the table's order of first use: one a core."""
    return list(dict.fromkeys(entry.routine for entry in entries() if entry.verdict == OURS_THROUGH_A_THUNK))


# ---- THE THUNK ----------------------------------------------------------------------------------------------------------
# Entered over the ROM caller's own frame: its return address at 0(sp), then the Alcyon arguments in push order. Each
# is pushed again, LAST FIRST, as the longword slot GCC reads it from — a WORD sign-extended (through A0: `movea.w`
# extends), a LONGWORD as it is; then the host arguments (the return address, re-read from where it now lies); then
# the image base, 0 on target. D0-D2/A0-A2 are an Alcyon caller's scratch, D3-D7/A3-A6 are kept by GCC's own
# convention, and D0 is answered as the core leaves it.
RETURN_ADDRESS_BYTES = LONG_BYTES
SLOT_BYTES = LONG_BYTES
ARGUMENT_NAMES = {vdi.WORD_ARG: "word", vdi.LONG_ARG: "long"}


def _push_of(argtype, displacement):
    """The instructions that push the frame's argument at `displacement(sp)` as a GCC slot. (A `uint16_t` argument
    would be zero-extended through D0: no routine of the table declares one, so none is spelt and one is REFUSED.)"""
    if argtype is vdi.LONG_ARG:
        return [f"move.l  {displacement}(%sp),-(%sp)"]
    assert argtype is vdi.WORD_ARG, f"no thunk shape pushes a {argtype}"
    return [f"movea.w {displacement}(%sp),%a0", "move.l  %a0,-(%sp)"]


def _push_of_the_return_site(pushed):
    """...and the caller's return address, from where it lies once `pushed` bytes are: at the stack pointer itself
    for a routine with no other argument (spelt `(sp)`, as the assembler would make it)."""
    if not pushed:
        return "move.l  (%sp),-(%sp)"
    return f"move.l  {pushed}(%sp),-(%sp)"


def thunk_body(routine):
    """The instructions of `routine`'s thunk, to its `rts`."""
    signature, framed = vdi.ALCYON[routine], vdi.frame_argtypes(routine)
    offsets, at = [], RETURN_ADDRESS_BYTES
    for argtype in framed:
        offsets.append(at)
        at += vdi.ARG_BYTES[argtype]
    body, pushed = [], 0
    for argtype, offset in reversed(list(zip(framed, offsets))):
        body += _push_of(argtype, offset + pushed)
        pushed += SLOT_BYTES
    for _host_argument in range(signature.host_arguments):      # the caller's return site, from where it now lies
        body.append(_push_of_the_return_site(pushed))
        pushed += SLOT_BYTES
    if vdi.takes_image(routine):
        body.append("pea     (0).w")
        pushed += SLOT_BYTES
    body.append(f"jsr     {routines.core_symbol(routine)}")
    if pushed:
        body.append(f"lea     {pushed}(%sp),%sp")
    return body + ["rts"]


def signature_text(routine):
    """`aes_ob_add(image, long, word, word)`: the core's call as the thunk makes it, for the generated comment."""
    signature = vdi.ALCYON[routine]
    hosts = ["the return site"] * signature.host_arguments
    arguments = (["image"] if vdi.takes_image(routine) else []) + hosts + [ARGUMENT_NAMES[a] for a in vdi.frame_argtypes(routine)]
    return f"{routines.core_symbol(routine)}({', '.join(arguments)})"


def _thunk_lines(routine):
    symbol = thunk_symbol(routine)
    return [f"/* ${getattr(addrs, routine):x}: {signature_text(routine)} */", f"    .type   {symbol},@function", f"{symbol}:",
            *(f"    {instruction}" for instruction in thunk_body(routine)), f"    .size   {symbol},.-{symbol}", ""]


# ---- THE FILE -----------------------------------------------------------------------------------------------------------
HEADER = """/* lineftable.S — THE LINE-F CALL TABLE OF OURS and the thunks behind it. GENERATED by bench/linef_table.py: do not edit
 * (`test/test_aes_lineftable.py` holds this text equal to the generator's).
 *
 * {entries} longwords, one for each entry of the ROM's table at `$fee900`: the build's own entry where it has one — a
 * byte-pinned `.S` entry as it is ({native}), or a thunk that re-pushes the ROM caller's Alcyon frame as the longword
 * slots a C core reads ({thunked}, {thunks} thunks) — and the ROM's own address in the rest ({rom}: band 6's routines, the
 * ROM's until each is ported).
 *
 * A KIND OF ITS OWN (`atari/target.mk`: LINEFTABLE_SOURCES): target-only, no ROM instruction, no row. LINKED AND NOT
 * BOUND: no word of a build names `aes_linef_table` — the handler gem_entry copies still loads the ROM's table
 * (`gemstart.S`; the operand is declared pending in the generator) — so nothing here runs but in a labelled staging.
 *
 * THE FILE ASKS FOR NO ALIGNMENT OF ITS OWN: the assembler rounds its text to a longword, as every source's, so what
 * links after it moves by its length and keeps its own place modulo four.
 */
    .text

    .globl  {table}
    .type   {table},@object
{table}:"""
TABLE_LINE_WIDTH = 44


def text():
    """The whole of `src/aes/lineftable.S`."""
    table, counts = entries(), {}
    for entry in table:
        counts[entry.verdict] = counts.get(entry.verdict, 0) + 1
    thunked = thunked_routines()
    lines = [HEADER.format(entries=len(table), native=counts[OURS_NATIVE], thunked=counts[OURS_THROUGH_A_THUNK],
                           thunks=len(thunked), rom=counts[THE_ROM_S], table=TABLE_SYMBOL)]
    for entry in table:
        longword = entry.symbol if entry.symbol is not None else f"{entry.target:#x}"
        lines.append(f"{'    .long   ' + longword:<{TABLE_LINE_WIDTH}}/* ${call_word(entry.index):04x}  ${entry.target:x}  {entry.verdict} */")
    lines += [f"    .size   {TABLE_SYMBOL},.-{TABLE_SYMBOL}", ""]
    for routine in thunked:
        lines += _thunk_lines(routine)
    return "\n".join(lines)


def main(argv):
    out = Path(argv[1]) if len(argv) > 1 else SOURCE
    made = text()
    if not out.exists() or out.read_text() != made:
        out.write_text(made)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
