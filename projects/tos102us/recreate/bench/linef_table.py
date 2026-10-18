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

BOUND SINCE BAND 6's SLICE B0 (ruling W6-R1): the one word of a blob that names the table is gemstart.S's EIGHTH
relocation — the operand of the Line-F handler gem_entry copies — so every machine of ours dispatches the ROM's desk's
Line-F calls through this table (the registry's table kind, `aes_event.LINEF_TABLE_SLOT`, maps `$cc24` at a run's
entry and in a takeover's door). An entry's verdict still moves only at a flip.

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

# (gemstart.S's EIGHTH RELOCATION, declared pending here by slice T as `PENDING_BINDING`, is MADE since slice B0: the
# handler's operand names `aes_linef_table` in both blobs, and the registry maps `$cc24` — no declaration is pending.)


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
# thunk could be made — and its entry STAYS THE ROM'S BY DECLARATION until its flip slice (W6-R1, the user's: the table
# bound first, then the desk's routines flip, bottom-up). Held at Tier 1 meanwhile; a routine leaves this list at its
# flip, and the generated file's diff is that flip's record. `{routine: why}`. (Wave 1a's two units, O and D, flipped
# at band 6 slice F1.)
LINKED_AND_NOT_FLIPPED = {}
# ---- unit D: FLIPPED at band 6 slice F1 — the desk's forty bindings and desk_wait, each thunked, BUT THREE HELD (the slice's
# brief holds back a routine whose flip needs what the cut does not have; `aes_deskbind.HELD_AT_F1` says each) — TWO since
# band 6 slice F2 ----
# (appl_exit, held at F1 for its price alone, FLIPPED at band 6 slice F2 as ⚠️ VERIFIED-BUT-UNPRICED — the user's ruling of
# 2026-10-17: no row kind reaches its arrivals, whose screen manager stands where no history of ours reaches.)
LINKED_AND_NOT_FLIPPED.update({
    "AES_ROM_DESK_EVNT_MULTI": "unit D: evnt_multi, held at band 6 slice F1 — flipped, ctlmgr's live-frame staging refuses "
                               "first (our C binding has no `link a6`: the desk's frame chain differs at $a288 / $a2bc), "
                               "and behind it the answer words it copies out for events that did not occur ($a34e "
                               "clicks_out, $a350 key_out) are each shore's residue — both harness pieces made at slice H2 "
                               "(`aes_ctlmgr.the_desk_s_text`, `aes_ctlmgr.ResidueCopies`): it flips at F2c",
    "AES_ROM_DESK_OBJC_DRAW": "unit D: objc_draw, held at band 6 slice F1 — its C walks the tree (just_draw), and a row that "
                              "switches with no door was modelled with no walked routine served; the fork's walk made at "
                              "slice H2 (`aes_switch._served_with_no_door`), its rows priced and measured on both blobs (the "
                              "F1 probe's refusal was the kit's own bench's): it flips at F2c"})
# ---- unit O: FLIPPED at band 6 slice F1 — its seventeen C cores thunked, trp13 a row of the transcribed table (native) ----
# ---- end of band 6 wave 1a's ----
# ---- band 6 wave 1b: one `.update({...})` PER UNIT inside its group's own block, the group's names only ----
# (BAND 6 SLICE F2 flips these by group: each group takes its flipped names out of its OWN block's lines and leaves the
# ones it holds there with the reason it holds them — no group edits another's block; `src/aes/lineftable.S` is then
# made again by this generator, never merged by hand.)
# ---- band 6 wave 1b, group G1 (units I `src/desk/deskwin.c`, L `src/desk/deskview.c`) ----
# FLIPPED at band 6 slice F2 (stage 1) but four: a routine flips once every C callee of it is flipped (the cut's rule —
# flipped alone, a caller of a held core breaks the converse invariant and the unbound pin), so each of these waits for
# its callee's slice (`aes_deskwin.HELD_AT_F2` says the same). Unit L's three held at stage 1 (win_icalc, win_bldview,
# win_shwall: stage artifacts of the groups' parallel flips) FLIPPED at slice F2b.
LINKED_AND_NOT_FLIPPED.update({"AES_ROM_DO_WREDRAW": "unit I: do_wredraw, held at band 6 slice F2 — its C calls the objc_draw "
                                                     "binding, held at slice F1 (F2c, after H2)"})
# ---- end of group G1's ----
# ---- band 6 wave 1b, group G2 (units A `src/desk/deskapp.c`, K `src/desk/desktop.c`, J `src/desk/desksupp.c`) ----
# FLIPPED at band 6 slice F2 (stage 2) but two, i_find and men_update; i_find (a stage artifact of the groups' parallel
# flips) FLIPPED at slice F2b, men_update HELD there by a measured reason (`aes_desktop.HELD_AT_F2` says the same).
LINKED_AND_NOT_FLIPPED.update({
    "AES_ROM_MEN_UPDATE": "unit K: men_update, held at band 6 slice F2b — MEASURED: flipped, ctlmgr's two desk-turn rows "
                          "are refused by the desk's live-frames vet (its C leaves other dead bytes than the ROM's at "
                          "$a2a6..$a2b3, inside the held evnt_multi binding's frame under the desk's wait: that binding's "
                          "unwritten locals) — out of the compare once the binding flips (slice H2's pieces): it flips with "
                          "evnt_multi at F2c"})
# ---- end of group G2's ----
# ---- band 6 wave 1b, group G3 (units B `src/desk/deskact.c`, G `src/desk/deskfpd.c`) ----
# FLIPPED at band 6 slice F2 (stage 2): unit G whole, unit B but five. HELD, unit B's five below: a routine flips once
# every C callee of it is flipped — gr_isdown's C calls unit D's evnt_multi, still held (`aes_deskbind.HELD_AT_F1`), and
# gr_bwait calls gr_isdown; act_chg, act_allchg and move_drvicon call unit I's do_wredraw (held for objc_draw) —
# flipped, each would be a bound referrer of a held core (F2c's, after the harness slice H2;
# `aes_deskact.UNIT_B_HELD_AT_F2` says the same).
LINKED_AND_NOT_FLIPPED.update({
    "AES_ROM_GR_ISDOWN": "unit B: gr_isdown, held at band 6 slice F2 — its C calls unit D's evnt_multi, held at slice F1 (F2c, "
                         "after H2)",
    "AES_ROM_GR_BWAIT": "unit B: gr_bwait, held at band 6 slice F2 — its C calls gr_isdown, held (F2c)",
    "AES_ROM_ACT_CHG": "unit B: act_chg, held at band 6 slice F2 — its C calls unit I's do_wredraw, held for objc_draw (F2c)",
    "AES_ROM_ACT_ALLCHG": "unit B: act_allchg, held at band 6 slice F2 — its C calls unit I's do_wredraw, held for objc_draw (F2c)",
    "AES_ROM_MOVE_DRVICON": "unit B: move_drvicon, held at band 6 slice F2 — its C calls unit I's do_wredraw, held for objc_draw "
                            "(F2c)"})
# ---- end of group G3's ----
# ---- band 6 wave 1b, group G4 (units C `src/desk/deskdir.c`, H `deskfun.c`, E `deskusr.c`, F `deskinf.c`) ----
# (FLIPPED at band 6 slice F2, stage 1: unit C's ten others, units H, E and F whole — eighteen. HELD, unit C's four
# below: each calls unit D's objc_draw, still the ROM's (`aes_deskbind.HELD_AT_F1`), or a routine that does — a flipped
# routine whose C calls a held core is a bound referrer of it (`aes_deskbind.bound_referrers`) and breaks the converse
# invariant on our shore; F2c's, after the harness slice H2.)
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_DESK_{routine}": "unit C: a dialog's drawing, held at band 6 slice F2 — its C calls unit D's "
                               "objc_draw (held) or a routine that does: flipped, it would be a bound referrer of a held core"
                               for routine in ("DRAW_DIAL", "DO_NAMECON", "SHOW_DIAL", "DRAW_FLD")})
# ---- end of group G4's ----
# ---- end of band 6 wave 1b's ----
# ---- band 6 wave 2: one `.update({...})` PER UNIT inside its group's own block, the group's names only ----
# ---- band 6 wave 2, group G1 (units C `src/desk/deskdir.c`, F `deskinf.c`, E `deskusr.c`) ----
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_DESK_{routine}": "unit C: the copy engine, held at Tier 1 at its arrivals, GEMDOS replayed"
                               for routine in ("D_DOFCOPY", "D_DOOP", "DIR_OP")})
LINKED_AND_NOT_FLIPPED.update({"AES_ROM_DESK_INF_FOLDER": "unit F: Show Info's count of a folder, held at Tier 1 at its arrivals"})
LINKED_AND_NOT_FLIPPED.update({"AES_ROM_DESK_DR_CODE": "unit E: a text-view line drawn, held at Tier 1 at its arrivals"})
# ---- end of group G1's wave-2 ----
# ---- band 6 wave 2, group G2 (units H `src/desk/deskfun.c`, G `deskfpd.c`, M `deskutil.c`) ----
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_{routine}": "unit G: a path closed or read, held at Tier 1 at its arrivals" for routine in (
    "PN_CLOSE", "PN_ACTIVE")})
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_DESK_FUN_{routine}": "unit H: an operation's driver, held at Tier 1 at its arrivals"
                               for routine in ("REBLD", "MKDIR", "OP", "DDST", "WDST", "WIN2WIN", "WIN2DESK", "DISK", "DESK2WIN",
                                               "D2DESK", "DRAG")})
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_{routine}": "unit M: the cartridge's directory search, held at Tier 1 over argument classes"
                               for routine in ("CART_SFIRST", "CART_SNEXT")})
# ---- end of group G2's wave-2 ----
# ---- band 6 wave 2, group G3 (units I `src/desk/deskwin.c`, J `desksupp.c`, K `desktop.c`, L `deskview.c`) ----
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_{routine}": "unit I: an opener of the desk's windows, held at Tier 1 at its arrivals"
                               for routine in ("PRO_RUN", "DESK_CLEAR", "DESK_VERIFY", "DO_WOPEN")})
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_{routine}": "unit L: a scroll or rebuild of the desk's windows, held at Tier 1 at its arrivals"
                               for routine in ("WIN_BLT", "WIN_SLIDE", "WIN_ARROW", "WIN_SRTALL", "WIN_BDALL")})
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_{routine}": "unit J: an opener or closer of the desk's windows, held at Tier 1 at its arrivals"
                               for routine in ("DO_DIROPEN", "DO_DOPEN", "DO_FOPEN", "DESK_DO_FORMAT", "CLOSE_WINDOW",
                                               "CLOSE_FOLDER", "FUN_CLOSE")})
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_{routine}": "unit K: a helper of the desk's main loop, held at Tier 1 at its arrivals"
                               for routine in ("HNDL_KBD", "CNX_GET")})
# ---- end of group G3's wave-2 ----
# ---- band 6 wave 2, group G4 (units A `src/desk/deskapp.c`, B `deskact.c`) ----
LINKED_AND_NOT_FLIPPED.update({name: "unit A: DESKTOP.INF parsed and written, held at Tier 1 at their arrivals"
                               for name in ("AES_ROM_APP_START", "AES_ROM_APP_SAVE")})
LINKED_AND_NOT_FLIPPED.update({name: "unit B: the drag's loop and the button's handlers, held at Tier 1 at their arrivals"
                               for name in ("AES_ROM_GR_DRGPLNS", "AES_ROM_ACT_BSCLICK", "AES_ROM_ACT_BDOWN")})
# ---- end of group G4's wave-2 ----
# ---- end of band 6 wave 2's ----
# ---- band 6 wave 4: one `.update({...})` PER UNIT inside its group's own block, the group's names only. The show /
# print engine's eight `bsr`-only parts are static C inside the engine (ruling R-W4-5): no entry of theirs here, nor
# in LINKED_HELD_NO_TABLE_ENTRY ----
# ---- band 6 wave 4, group G1 (unit M `src/desk/deskutil.c`) ----
LINKED_AND_NOT_FLIPPED.update({name: "unit M: the show / print engine's two built-ins, held at Tier 1 at their arrivals"
                               for name in ("AES_ROM_DESK_SHOW_FILE", "AES_ROM_DESK_PRINT_FILE")})
# ---- end of group G1's wave-4 ----
# ---- band 6 wave 4, group G2 (unit N `src/desk/deskdisk.c`) ----
LINKED_AND_NOT_FLIPPED.update({f"AES_ROM_DESK_{routine}": "unit N: the disk utilities, held at Tier 1 at their arrivals"
                               for routine in ("UTIL_OPEN", "UTIL_SHOW", "UTIL_REDRAW", "FAT_SWAP", "UTIL_BARS", "UTIL_ERROR",
                                               "FAT_MARK", "COPY_TRACKS", "FORMAT", "COPY_DISK")})
# ---- end of group G2's wave-4 ----
# ---- end of band 6 wave 4's ----

# ---- band 6 wave 2 (ruling R-W2-4) ----
# THE ROUTINES WRITTEN, LINKED AND HELD UNBOUND THAT HAVE NO ENTRY OF THE TABLE: reached by VALUE only — `$fde844`, the
# desk's G_USERDEF draw code, by ub_trampoline's `jsr` (trapdoor.S's pinned operand) — so the generator has no verdict
# of theirs to hold back; their binding is that operand's relocation. Held unbound all the same: the desk's one unbound
# pin (`test/aes_deskbind.py`'s `held_cores`) holds them with LINKED_AND_NOT_FLIPPED, and `test_aes_lineftable.py`
# counts them in their unit's list. `{routine: why}`.
LINKED_HELD_NO_TABLE_ENTRY = {}
# ---- band 6 wave 2, group G1 (unit E) ----
LINKED_HELD_NO_TABLE_ENTRY.update({"AES_ROM_DESK_USERDEF": "unit E: the text view's G_USERDEF draw, reached by value from "
                                                           "ub_trampoline; held at Tier 1 at its arrivals"})
# ---- end of group G1's wave-2 ----
# ---- end of band 6 wave 2's (R-W2-4) ----


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
 * A KIND OF ITS OWN (`atari/target.mk`: LINEFTABLE_SOURCES): target-only, no ROM instruction, no row. BOUND (band 6
 * slice B0): the one word of a build that names `aes_linef_table` is the operand of the handler gem_entry copies
 * (`gemstart.S`), so every machine of ours dispatches the ROM's desk's Line-F calls through this table.
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
