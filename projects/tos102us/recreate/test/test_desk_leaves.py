r"""THE DESK'S LEAVES FILED IN AES MODULES, AT TIER 1 — band 6 wave 1a, unit O (`src/desk/deskleaf.c`): thirteen
entries of the DOS glue, gemgraf's gsx_pline, app_alloc and app_free, gsx_hardcopy and the BIOS door trp13.

FLIPPED SINCE BAND 6 SLICE F1 (ruling W6-R1, the user's): both blobs link the eighteen cores, and every Line-F table
entry that names one of the routines is OURS — seventeen thunks, trp13's two its `.S` (`FLIPPED`, below) — so the ROM's
desk calls them on every machine of ours (held there by `test_aes_desk_ours.py`). Tier 1 here is the routine against the
ROM's own routine on the host library — at THE ARRIVALS the hands' chains make (`aes_deskleaves.py` says how a case is taken at one, and
what is staged over it: the scripted trap and a frame laid before the call, EACH SAID IN THE CASE'S ID — `SCRIPTED`,
`FRAME_LAID`, `LAST_CALL_TRAP`, `DRIVER_REPLAYED`) and, where no chain reaches an arm, over a LABELLED ARGUMENT CLASS.
SEVENTEEN OF THE EIGHTEEN HAVE AN ARRIVAL; gsx_hardcopy has none (its printer is a device the model has not).

WHAT A ROM CALLER IS LEFT (D0, A0), per routine, is held as far as a C function has it: D0 at the declared width,
compared on every case, and held equal to the ROM's own run IN PLACE at every arrival. What it has not is NAMED AND
COUNTED (`D0_BEYOND_THE_ANSWER`; A0 by `test_a0_at_return_is_the_address_the_glue_returned_through…`): never silently
equal, never silently dropped.

THE BIOS DOOR SHIPS AS ITS SIXTEEN ROM BYTES (`src/desk/trp13.S`, a row of the transcribed table as trp14's is): pinned
here on both blobs and held to the ROM at the door's three arrivals through the transcription relation — its Tier 3 rows;
`aes_trp13` is its Tier-1 twin. AND EVERY BLOB CASE AT AN ARRIVAL IS A ROW (`ROWS`, at the end).
"""
import contextlib
import functools
import struct
import sys
from pathlib import Path

import pytest

from harness import BASE_IMAGE, addrs, emu

import aes
import aes_desk
import aes_deskbind
import aes_deskleaves as dl
import aes_event
import aes_gsx as gsx
import aes_shell as shell
import case
import gemdos_fs as fs
import isr
import layouts
import routines
import test_aes_gsx_transcription as frames
import transcription
import vdi
import vdi_escape
from case import merge_pokes
from opcodes import BSR_W, RTS

BENCH = Path(__file__).resolve().parents[1] / "bench"


def _linef_table():
    """`bench/linef_table.py` — imported HERE, never at the module's top: it imports every battery's registry
    (`test_boot_snapshot`), and this module registers rows of its own (`ROWS`, below), so an import at the top would
    splat the registry before this module's rows are in it (band 6 slice F1)."""
    if str(BENCH) not in sys.path:
        sys.path.insert(0, str(BENCH))
    import linef_table
    return linef_table

WORD_BYTES, LONG_BYTES = aes.WORD_BYTES, aes.LONG_BYTES
RECREATE = Path(__file__).resolve().parents[1]
LEAF = layouts.parse_constants((aes.INCLUDE / "desk" / "deskglobals.h", aes.INCLUDE / "desk" / "deskleaf.h"), known=aes.CONSTANTS)
At = dl.At
SENTINEL = emu.SENTINEL
# GEMDOS's error numbers, as the headers that reconstruct GEMDOS name them (signed longwords).
_GEMDOS_ERRORS = {**addrs.parse(aes.INCLUDE / "gemdos" / "fs.h"), **addrs.parse(aes.INCLUDE / "gemdos" / "process.h"),
                  "GEMDOS_EIHNDL": addrs.GEMDOS_EIHNDL}
EFILNF, EPTHNF, EACCDN, EIHNDL, EDRIVE, ENMFIL = (aes.signed(_GEMDOS_ERRORS[f"GEMDOS_{name}"], bits=32)
                                                  for name in ("EFILNF", "EPTHNF", "EACCDN", "EIHNDL", "EDRIVE", "ENMFIL"))
assert (EFILNF, EPTHNF, EACCDN, EIHNDL, EDRIVE, ENMFIL) == (-33, -34, -36, -37, -46, -49)
GEMDOS_OK = 0
CARRIAGE_RETURN, LINE_FEED = 0x0d, 0x0a
GEM_DOS_HOP = 0xfe39b6                  # the glue's `jmp __DOS`: what every entry's own `bsr` reaches
JMP_ABSOLUTE_LONG = 0x4ef9              # jmp     <xxx>.l

# ---- THE CHAINS' ARRIVALS ---------------------------------------------------------------------------------------------------
SAVE_DESKTOP = "Options > Save Desktop, Return"
SHOW_INFO = "A: File > Show Info, Return"
NEW_FOLDER = "folder: File > New Folder, 'A', Return"
COPY_INTO_THE_FOLDER = "folder: the file dragged onto it, Return"
DELETE_THE_FILE = "file: dragged to the trash, OK"
DELETE_THE_FOLDER = "folder: dragged to the trash, OK"
SHOW_THE_FILE = "file: shown, a key at its end"
OPEN_A = "A: opened"
DRAG_A = "drive A: dragged to the trash, Return"
# ...and the chains of the dialogs' less-trodden buttons (the fix pass: the second review's finding 1)
RENAME_THE_FILE = "file: File > Show Info, Backspace, 'A', Return (renamed)"
MAKE_IT_READ_ONLY = aes_desk.READ_ONLY_FILE
DELETE_REFUSED = "file: read-only, dragged to the trash, OK — access denied, Return"
REMOVE_THE_DRIVE = "A: Options > Install Disk Drive, Remove pressed"
INSTALL_A_DRIVE = "A: Options > Install Disk Drive, 'C' typed, Install pressed"
# The entries that trap once through GEMDOS over a frame the ledger records whole, each where a chain's step enters it.
GLUE_ARRIVALS = {
    "dos_write: Save Desktop writes DESKTOP.INF": At(dl.DOS_WRITE, SAVE_DESKTOP, 3),
    "dos_gdir: Save Desktop asks the current path": At(dl.DOS_GDIR, SAVE_DESKTOP, 3),
    "dos_create: Save Desktop creates DESKTOP.INF": At(dl.DOS_CREATE, SAVE_DESKTOP, 3),
    "dos_create: a file copied into a folder": At(dl.DOS_CREATE, COPY_INTO_THE_FOLDER, 3),
    "dos_mkdir: New Folder": At(dl.DOS_MKDIR, NEW_FOLDER, 4),
    "dos_avail: a file copy sizes its buffer": At(dl.DOS_AVAIL, COPY_INTO_THE_FOLDER, 2),
    "dos_delete: a file dragged to the trash": At(dl.DOS_DELETE, DELETE_THE_FILE, 3),
    "dos_rmdir: a folder dragged to the trash": At(dl.DOS_RMDIR, DELETE_THE_FOLDER, 3),
    "dos_rawcio: the viewer's carriage return": At(dl.DOS_RAWCIO, SHOW_THE_FILE, 0),
    "dos_rawcio: the viewer's line feed": At(dl.DOS_RAWCIO, SHOW_THE_FILE, 0, 2),
    "dos_rename: Show Info renames the file": At(dl.DOS_RENAME, RENAME_THE_FILE, 5),
    "dos_chmod: Show Info makes the file read-only": At(dl.DOS_CHMOD, MAKE_IT_READ_ONLY, 4),
    "dos_delete: a read-only file dragged to the trash — GEMDOS answers EACCDN": At(dl.DOS_DELETE, DELETE_REFUSED, 3),
}
# WHAT IS STAGED OVER AN ARRIVAL'S MEGABYTE, EACH SAID IN THE ID OF EVERY CASE THAT STAGES IT:
SCRIPTED = "GEMDOS SCRIPTED: the recording trap answers the ROM's own run's answers"
FRAME_LAID = "THE FRAME GEMDOS FILLS LAID before the call"
LAST_CALL_TRAP = "GEMDOS A TRAP THAT KEEPS ITS LAST CALL"
DRIVER_REPLAYED = "THE ROM'S DISK DRIVER REPLAYED for the C"
STALE = "the glue's four words stale"


def answers_in_place(at):
    return [trap.answer for trap in dl.ran_at(at).traps]


def return_parked(name):
    """What an entry leaves in AES_DOS_RETURN entered directly: the harness's sentinel where it parks its caller's
    return, else whatever the machine held."""
    return SENTINEL if name in dl.PARKS_ITS_CALLER_S_RETURN else None


# What each such entry parks in AES_TRAP1_RETURN: the site its own `bsr __DOS` returns to.
GLUE_SITE = {dl.DOS_WRITE: addrs.AES_DOS_READ_TRAP_RETURN, dl.DOS_GDIR: addrs.AES_DOS_GDIR_TRAP_RETURN,
             dl.DOS_MKDIR: addrs.AES_DOS_MKDIR_TRAP_RETURN, dl.DOS_SETDT: addrs.AES_DOS_SETDT_TRAP_RETURN,
             dl.DOS_LABEL: addrs.AES_DOS_LABEL_TRAP_RETURN, dl.DOS_RENAME: addrs.AES_DOS_RENAME_TRAP_RETURN,
             **{name: addrs.AES_DOS_TRAP_RETURN for name in (dl.DOS_RAWCIO, dl.DOS_CHMOD, dl.DOS_DELETE, dl.DOS_RMDIR, dl.DOS_CREATE)}}
NOTHING_PARKED = (dl.DOS_AVAIL, dl.DOS_SPACE)       # `trap #1` itself: no site, no verdict


def test_the_sites_the_entries_park_are_where_their_own_bsr_returns():
    """Each site is the instruction after a `bsr` of the hop `$fe39b6` in the entry's own body — and the five through
    `$fe3c28` share that tail's."""
    for name, site in GLUE_SITE.items():
        word = case.word_in(BASE_IMAGE, site - LONG_BYTES)
        displacement = aes.signed(case.word_in(BASE_IMAGE, site - WORD_BYTES))
        assert word == BSR_W and site - WORD_BYTES + displacement == GEM_DOS_HOP, f"{name}: no `bsr.w $fe39b6` ends at {site:#x}"
    assert case.long_in(BASE_IMAGE, GEM_DOS_HOP + WORD_BYTES) == addrs.AES_ROM_GEM_DOS_TRAP
    assert case.word_in(BASE_IMAGE, GEM_DOS_HOP) == JMP_ABSOLUTE_LONG


def expected_verdict(name, answer, before):
    """`[AES_DOS_RETURN, AES_TRAP1_RETURN, AES_DOS_ERR, AES_DOS_AX]` after `name` whose one trap answered `answer`,
    over a machine that held `before` there — `__DOS`'s verdict, nothing for the two that trap by themselves."""
    if name in NOTHING_PARKED:
        return list(before)
    parked = return_parked(name)
    return [before[0] if parked is None else parked, GLUE_SITE[name], int(aes.signed(answer, bits=32) < 0), answer & aes.WORD_MASK]


def dos_words(ram):
    return [aes.read_field(ram, "AES", field) for field in dl.DOS_FIELDS]


def scripted_ids(labels):
    """The ids of cases that stage the scripted trap over an arrival: each says so."""
    return [f"{label} [{SCRIPTED}]" for label in labels]


AS_LEFT_OR_STALE = pytest.mark.parametrize("stale", (False, True), ids=("as the chain left the glue's words", STALE))


@AS_LEFT_OR_STALE
@pytest.mark.parametrize("label", GLUE_ARRIVALS, ids=scripted_ids(GLUE_ARRIVALS))
def test_a_glue_entry_at_its_arrival_makes_the_rom_s_call_and_leaves_what_the_rom_s_run_in_place_leaves(label, stale):
    """AT THE ARRIVAL, SCRIPTED: one trap — the ROM's function over the frame its caller pushed — both returns parked
    before it, `__DOS`'s verdict, D0. And D0 is what THE ROM'S OWN RUN IN PLACE left its caller (the real GEMDOS, the
    real disk): the scripted answer is that run's."""
    at = GLUE_ARRIVALS[label]
    arrived, ran = dl.arrival(at), dl.ran_at(at)
    (trap,) = ran.traps
    layers = (dl.STALE_DOS,) if stale else ()
    result = dl.held(arrived, *layers, answers=[trap.answer])
    function, frame = trap.function, trap.frame[:dl.FRAME_BYTES[trap.function]]
    assert dl.calls(result.final) == [(function, frame.ljust(dl.GEMDOS.recorded_bytes, b"\0"))], "the frame of the run in place"
    before = dos_words(dl.megabyte(arrived, *layers)[0])
    assert dl.verdict(result) == expected_verdict(at.routine, trap.answer, before)
    if at.routine not in NOTHING_PARKED:
        assert dl.sites_parked_at(result.final) == [tuple(dl.verdict(result)[:2])], "parked BEFORE the trap"
    in_place = ran.returned.registers["d0"]
    if at.routine == dl.DOS_MKDIR:
        assert result.answer() == aes.signed(in_place & aes.WORD_MASK)
    else:
        assert result.long_answer() == in_place
    if not stale and at.routine not in NOTHING_PARKED and at.routine != dl.DOS_MKDIR:
        assert dos_words(ran.returned.ram)[2:] == dl.verdict(result)[2:], "the verdict the run in place left"


def test_the_arrivals_are_the_frames_the_rom_s_callers_push():
    """What the chains hand, read off the arrivals: the INF's handle and length, drive 1's path buffer, an attribute
    word of 0, the viewer's two characters — and each return site is the word after a Line-F call of the routine."""
    for label, at in GLUE_ARRIVALS.items():
        arrived = dl.arrival(at)
        sites = {site + WORD_BYTES for sites in aes.line_f_call_sites(at.routine).values() for site in sites}
        assert arrived.return_site in sites, f"{label}: returns to {arrived.return_site:#x}, after no Line-F call of it"
    assert dl.arrival(GLUE_ARRIVALS["dos_rawcio: the viewer's carriage return"]).arguments == (CARRIAGE_RETURN,)
    assert dl.arrival(GLUE_ARRIVALS["dos_rawcio: the viewer's line feed"]).arguments == (LINE_FEED,)
    handle, count, _buffer = dl.arrival(GLUE_ARRIVALS["dos_write: Save Desktop writes DESKTOP.INF"]).arguments
    assert handle >= addrs.GEMDOS_FIRST_FILE_HANDLE and count > 0
    assert dl.arrival(GLUE_ARRIVALS["dos_gdir: Save Desktop asks the current path"]).arguments[0] == 1, "drive A:, from 1"


READ_ONLY = 1                           # a file's read-only attribute bit (`gemdos/fs.h`: GEMDOS_ATTR_READ_ONLY)


def test_the_new_arrivals_are_show_info_s_two_acts_on_a_file_and_a_delete_gemdos_refuses():
    """THE THREE ARRIVALS THE DIALOGS' LESS-TRODDEN BUTTONS GIVE (the second review's finding 1: two of them were
    labelled classes on the leaf machine): Show Info's edited name is Frename(the file's path, the same with its last
    character an A), answered 0; its Read-Only button Fattrib(the path, set, the read-only bit), answered the
    attribute; and a read-only file dragged to the trash is Fdelete ANSWERED EACCDN by the ROM's own GEMDOS over the
    ROM's own disk — the glue's failing arm at an arrival, AES_DOS_ERR 1 in the run in place."""
    renamed, attributed, refused = (GLUE_ARRIVALS[label] for label in list(GLUE_ARRIVALS)[-3:])
    old, new = dl.arrival(renamed).arguments
    ram = dl.arrival(renamed).boot.ram
    assert (aes_desk.text_at(ram, old), aes_desk.text_at(ram, new)) == (f"A:\\{aes_desk.THE_INF}", f"A:\\{aes_desk.THE_RENAMED}")
    assert answers_in_place(renamed) == [GEMDOS_OK]
    name, set_them, attributes = dl.arrival(attributed).arguments
    assert (aes_desk.text_at(dl.arrival(attributed).boot.ram, name), set_them, attributes) == (f"A:\\{aes_desk.THE_INF}", 1, READ_ONLY)
    assert answers_in_place(attributed) == [READ_ONLY]
    assert answers_in_place(refused) == [EACCDN & aes.LONG_MASK]
    assert dos_words(dl.ran_at(refused).returned.ram)[2:] == [1, EACCDN & aes.WORD_MASK]


# ---- the glue's entries over LABELLED ARGUMENT CLASSES: the arms no chain's GEMDOS answers ---------------------------------------
A_NAME, ANOTHER = b"A:\\OLD.TXT\0", b"A:\\NEW.TXT\0"
# THE HOST'S TRAP REACHES THE RECONSTRUCTED DISPATCHER, which resolves Fwrite's handle before it calls the handler: the
# handle a case writes to is staged OPEN for it (`aes_shell.OPEN_FOR_THE_HOST` says so of Fread's) — the ROM's side,
# whose scripted handler stands in for the whole of GEMDOS, reads it not at all.
A_HANDLE = shell.SCRIPTED_HANDLE
TEXTS = merge_pokes({dl.TEXT_AT: A_NAME.ljust(dl.TEXT_BYTES, b"\0")}, {dl.OTHER_TEXT_AT: ANOTHER.ljust(dl.TEXT_BYTES, b"\0")},
                    shell.OPEN_FOR_THE_HOST)
TAGGED = dl.TEXT_AT | aes.BUS_TAG       # a pointer with a top byte: handed GEMDOS as it is
# (the routine, its arguments, the call the ledger records)
ENTRIES = {
    "dos_write": (dl.DOS_WRITE, (A_HANDLE, 0x0200, dl.TEXT_AT), dl.call(dl.FWRITE, ("w", A_HANDLE), ("l", 0x0200), ("l", dl.TEXT_AT))),
    "dos_write, a count with its top bit (zero-extended)": (
        dl.DOS_WRITE, (A_HANDLE, 0x8001, dl.TEXT_AT), dl.call(dl.FWRITE, ("w", A_HANDLE), ("l", 0x0000_8001), ("l", dl.TEXT_AT))),
    "dos_gdir": (dl.DOS_GDIR, (3, dl.OUT_AT), dl.call(dl.DGETPATH, ("l", dl.OUT_AT), ("w", 3))),
    "dos_rename": (dl.DOS_RENAME, (dl.TEXT_AT, dl.OTHER_TEXT_AT),
                   dl.call(dl.FRENAME, ("w", 0), ("l", dl.TEXT_AT), ("l", dl.OTHER_TEXT_AT))),
    "dos_rename, names with a top byte": (dl.DOS_RENAME, (TAGGED, dl.OTHER_TEXT_AT | aes.BUS_TAG),
                                          dl.call(dl.FRENAME, ("w", 0), ("l", TAGGED), ("l", dl.OTHER_TEXT_AT | aes.BUS_TAG))),
    "dos_rawcio, a key asked for": (dl.DOS_RAWCIO, (0x00ff,), dl.call(dl.CRAWIO, ("w", 0x00ff))),
    "dos_rawcio, a word with a high byte": (dl.DOS_RAWCIO, (0x1241,), dl.call(dl.CRAWIO, ("w", 0x1241))),
    "dos_chmod, set": (dl.DOS_CHMOD, (dl.TEXT_AT, 1, 0x21), dl.call(dl.FATTRIB, ("l", dl.TEXT_AT), ("w", 1), ("w", 0x21))),
    "dos_chmod, asked": (dl.DOS_CHMOD, (TAGGED, 0, 0x1200), dl.call(dl.FATTRIB, ("l", TAGGED), ("w", 0), ("w", 0x1200))),
    "dos_delete": (dl.DOS_DELETE, (dl.TEXT_AT,), dl.call(dl.FDELETE, ("l", dl.TEXT_AT))),
    "dos_rmdir": (dl.DOS_RMDIR, (TAGGED,), dl.call(dl.DDELETE, ("l", TAGGED))),
    "dos_create": (dl.DOS_CREATE, (dl.TEXT_AT, 0x0001), dl.call(dl.FCREATE, ("l", dl.TEXT_AT), ("w", 1))),
    "dos_create, an attribute word with a high byte": (dl.DOS_CREATE, (dl.TEXT_AT, 0x1220), dl.call(dl.FCREATE, ("l", dl.TEXT_AT), ("w", 0x1220))),
    "dos_avail": (dl.DOS_AVAIL, (), dl.call(dl.MALLOC, ("l", 0xFFFF_FFFF))),
}
ANSWERS = {"done": GEMDOS_OK, "a handle": 6, "an error": EACCDN, "a large long": 0x000D_8000, "the least long": 0x8000_0000}
THROUGH = pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
LINE_F_RETURN_SITE = aes.LINE_F_CALLER_AT + len(b"\x58\x8f") + WORD_BYTES        # past the caller's drop and its call word


def site_parked(through_line_f):
    return LINE_F_RETURN_SITE if through_line_f else SENTINEL


def test_the_line_f_caller_s_return_site_is_the_word_after_its_call_word():
    pokes = aes.line_f_caller_pokes(dl.DOS_DELETE)
    (at, code), = pokes.items()
    assert at == aes.LINE_F_CALLER_AT and case.word_in(code, LINE_F_RETURN_SITE - at - WORD_BYTES) == aes.line_f_call_word(dl.DOS_DELETE)


@THROUGH
@pytest.mark.parametrize("answered", ANSWERS)
@pytest.mark.parametrize("which", ENTRIES)
def test_a_glue_entry_traps_with_its_caller_s_frame_parks_and_answers_the_trap__an_argument_class(which, answered, through_line_f):
    """A LABELLED ARGUMENT CLASS (the leaf machine, the scripted trap): ONE trap, the function over the frame its
    caller pushed and nothing of the stack above it; the returns parked before it; D0 the trap's whole longword; the
    verdict — the LONG's sign, the answer's low word."""
    (name, arguments, recorded), answer = ENTRIES[which], ANSWERS[answered]
    hosts = (site_parked(through_line_f),) * vdi.ALCYON[name].host_arguments
    result = dl.scripted(name, arguments, [answer], TEXTS, through_line_f=through_line_f, host_arguments=hosts)
    assert dl.calls(result.final) == [recorded]
    assert result.long_answer() == answer & aes.LONG_MASK
    stale = [vdi.STALE_LONG, vdi.STALE_LONG, aes.STALE_WORD, aes.STALE_WORD]
    expected = expected_verdict(name, answer & aes.LONG_MASK, stale)
    if name in dl.PARKS_ITS_CALLER_S_RETURN:
        expected[0] = site_parked(through_line_f)
    assert dl.verdict(result) == expected
    assert dl.sites_parked_at(result.final) == [tuple(expected[:2])]


# (Dcreate's answer, AES_DOS_ERR, AES_DOS_AX, dos_mkdir's word)
MKDIR = {"made": (GEMDOS_OK, 0, 0, 1), "EACCDN: AES_DOS_AX 5": (EACCDN, 1, 5, 0), "another error": (EPTHNF, 1, EPTHNF & aes.WORD_MASK, 0),
         "a positive long whose word is EACCDN: 5, and done": (0x0001_FFDC, 0, 5, 1),
         "a negative long whose word is 0": (0x8000_0000, 1, 0, 0)}


@THROUGH
@pytest.mark.parametrize("answered", MKDIR)
def test_dos_mkdir_answers_the_verdict_turned_round_and_says_access_denied_as_5__an_argument_class(answered, through_line_f):
    """Dcreate(path); the verdict is the LONG's sign and the answer its opposite; EACCDN is a WORD compare, made
    whatever the verdict."""
    answer, failed, ax, word = MKDIR[answered]
    result = dl.scripted(dl.DOS_MKDIR, (TAGGED,), [answer], TEXTS, through_line_f=through_line_f)
    assert dl.calls(result.final) == [dl.call(dl.DCREATE, ("l", TAGGED))]
    assert result.answer() == word
    assert dl.verdict(result) == [vdi.STALE_LONG, addrs.AES_DOS_MKDIR_TRAP_RETURN, failed, ax]


# ---- dos_setdt, dos_label, dos_space: a frame of their own handed GEMDOS by address -------------------------------------------
SETDT_AT = At(dl.DOS_SETDT, COPY_INTO_THE_FOLDER, 3)
LABEL_AT = At(dl.DOS_LABEL, SHOW_INFO, 2)
SPACE_AT = At(dl.DOS_SPACE, SHOW_INFO, 2)
LABEL_FRAME_BYTES, LABEL_DTA, DTA_NAME = LEAF["LABEL_FRAME_BYTES"], LEAF["LABEL_DTA"], LEAF["DTA_NAME"]
DFREE_BYTES = LEAF["DFREE_BYTES"]
FA_VOLUME_LABEL = LEAF["FA_VOLUME_LABEL"]


def frame_in_place(at, frame_bytes):
    """A routine's whole `link` frame as its run in place left it where its LAST trap returned: what GEMDOS laid there."""
    arrived, ran = dl.arrival(at), dl.ran_at(at)
    top = arrived.boot.registers["isp"] - LONG_BYTES            # under the return address: the saved A6
    return bytes(ran.traps[-1].boot.ram[top - frame_bytes:top])


def staged_over_the_arrival(*stagings):
    """A case of one, whose ID says what it stages over its arrival's megabyte."""
    return pytest.mark.parametrize("staged", [stagings], ids=[" + ".join(stagings)])


@pytest.mark.parametrize("stale", (False, True), ids=(f"as the chain left the glue's words [{SCRIPTED}]", f"{STALE} [{SCRIPTED}]"))
def test_dos_setdt_at_its_arrival_sets_the_stamp_from_its_caller_s_own_words(stale):
    """A file copy stamps the copy: Fdatime(&the two words its caller pushed, the handle, 1) — the C is pointed at
    the same four bytes, and D0 and the verdict are the run in place's."""
    arrived, ran = dl.arrival(SETDT_AT), dl.ran_at(SETDT_AT)
    (trap,) = ran.traps
    result = dl.held(arrived, *((dl.STALE_DOS,) if stale else ()), answers=[trap.answer])
    handle, stamp = arrived.arguments
    assert dl.GEMDOS.seen == [dl.the_rom_s_pointed_at(trap, arrived.boot.ram)] == [(dl.FDATIME, struct.pack(">I", stamp), struct.pack(">HH", handle, 1))]
    assert dl.calls(result.final) == [dl.call(dl.FDATIME)], "the ledger records nothing of a frame that begins with a stack address"
    assert result.long_answer() == ran.returned.registers["d0"] == trap.answer
    assert dl.verdict(result)[1:] == [addrs.AES_DOS_SETDT_TRAP_RETURN, 0, trap.answer & aes.WORD_MASK]


def test_gemdos_leaves_dos_setdt_s_caller_s_two_words_byte_swapped__the_rom_s_run_in_place():
    """A ROM BEHAVIOUR (GEMDOS's, met through the glue), read off the run in place: Fdatime turns the stamp's two words
    to the disk's byte order WHERE THEY LIE and, setting, never turns them back — and where they lie is dos_setdt's
    caller's own argument words. The caller drops them unread (`$fdd444 addq.l #6,sp`); a C caller's are a copy."""
    arrived, ran = dl.arrival(SETDT_AT), dl.ran_at(SETDT_AT)
    stamp_at = arrived.boot.registers["isp"] + LONG_BYTES + WORD_BYTES
    before, after = arrived.boot.ram[stamp_at:stamp_at + LONG_BYTES], ran.returned.ram[stamp_at:stamp_at + LONG_BYTES]
    assert after == bytes((before[1], before[0], before[3], before[2])) != before
    assert int.from_bytes(ran.traps[0].frame[:LONG_BYTES], "big") == stamp_at


@THROUGH
@pytest.mark.parametrize("answer, failed", ((GEMDOS_OK, 0), (EIHNDL, 1)), ids=("done", "EIHNDL"))
def test_dos_setdt_hands_the_stamp_by_address_with_the_handle_and_a_1__an_argument_class(answer, failed, through_line_f):
    stamp = 0x6B2A_1D4F
    result = dl.scripted(dl.DOS_SETDT, (0x1207, stamp), [answer], through_line_f=through_line_f)
    assert dl.GEMDOS.seen == [(dl.FDATIME, struct.pack(">I", stamp), struct.pack(">HH", 0x1207, 1))]
    assert result.long_answer() == answer & aes.LONG_MASK
    assert dl.verdict(result) == [vdi.STALE_LONG, addrs.AES_DOS_SETDT_TRAP_RETURN, failed, answer & aes.WORD_MASK]


def label_frame(name=b"", fill=0xA5):
    """dos_label's frame as GEMDOS leaves it: the DTA's name at its place, the rest `fill`."""
    frame = bytearray([fill]) * LABEL_FRAME_BYTES
    frame[LABEL_DTA + DTA_NAME:LABEL_DTA + DTA_NAME + len(name) + 1] = name + b"\0"
    return bytes(frame)


LABEL_OUT_STALE = {dl.OUT_AT: bytes([vdi.FILL]) * dl.OUT_BYTES}
FRAME_LAID = "the frame GEMDOS fills laid before the call"


def label_seen(letter):
    return [(dl.FSETDTA, b"", b""), (dl.FSFIRST, letter + b":\\*.*", struct.pack(">H", FA_VOLUME_LABEL))]


@staged_over_the_arrival(SCRIPTED, FRAME_LAID)
def test_dos_label_at_its_arrival_finds_the_disk_s_label_and_copies_it_out(staged):
    """Show Info of drive A: — SCRIPTED, and the frame GEMDOS filled in the run in place LAID BEFORE THE CALL: the
    DTA set to its own frame, Fsfirst(the root's every name, 8), the DTA's name copied out through the caller's pointer, 1."""
    arrived, ran = dl.arrival(LABEL_AT), dl.ran_at(LABEL_AT)
    frame = frame_in_place(LABEL_AT, LABEL_FRAME_BYTES)
    result = dl.held(arrived, dl.frame_laid(dl.DOS_LABEL, frame), answers=[trap.answer for trap in ran.traps])
    drive, name_out = arrived.arguments
    assert dl.GEMDOS.seen == [dl.the_rom_s_pointed_at(trap) for trap in ran.traps] == label_seen(bytes([0x40 + drive]))
    name = frame[LABEL_DTA + DTA_NAME:].split(b"\0")[0]
    assert name and result.after(name_out, len(name) + 1) == name + b"\0" == bytes(ran.returned.ram[name_out:name_out + len(name) + 1])
    assert result.long_answer() == ran.returned.registers["d0"] == 1
    assert dl.verdict(result)[1:] == [addrs.AES_DOS_LABEL_TRAP_RETURN, 0, 0] == [addrs.AES_DOS_LABEL_TRAP_RETURN, *dos_words(ran.returned.ram)[2:]]


def test_dos_label_leaves_the_process_s_dta_naming_its_own_dead_frame__the_rom_s_run_in_place():
    """A ROM BEHAVIOUR, read off the run in place: Fsetdta is handed the frame's own DTA and it is never set back —
    where dos_label has returned, the running process's DTA (its basepage's) still names that dead frame."""
    arrived, ran = dl.arrival(LABEL_AT), dl.ran_at(LABEL_AT)
    dta = arrived.boot.registers["isp"] - LONG_BYTES - LABEL_FRAME_BYTES + LABEL_DTA
    basepage = case.long_in(ran.returned.ram, addrs.GEMDOS_P_RUN)
    assert case.long_in(ran.returned.ram, basepage + addrs.BASEPAGE_DTA) == dta < ran.returned.registers["isp"]
    assert int.from_bytes(ran.traps[0].frame[:LONG_BYTES], "big") == dta and ran.traps[0].function == dl.FSETDTA


# (Fsfirst's answer, the label in the DTA, dos_label's answer, AES_DOS_ERR, AES_DOS_AX)
LABELS = {
    "a label": (GEMDOS_OK, b"SYSTEM", 1, 0, 0),
    "an eleven-character label": (GEMDOS_OK, b"ELEVENCHARS", 1, 0, 0),
    "none: EFILNF": (EFILNF, b"STALE", 0, 1, 1),
    "none: ENMFIL": (ENMFIL, b"STALE", 0, 1, 1),
    "a positive long whose word is not 0: none": (0x0001_0001, b"STALE", 0, 1, 1),
    "a negative long whose word is 0: found, AES_DOS_ERR 1": (0x8000_0000, b"ODD", 1, 1, 0),
    "a word whose low byte is 0 and high byte is not: none": (0x0000_0100, b"STALE", 0, 1, 1),
}
DRIVES = {"A:": (1, b"A"), "P:": (16, b"P"), "a drive word with a high byte: its low byte alone": (0x1203, b"C"),
          "a byte sum that wraps": (0x00C5, b"\x05")}


@pytest.mark.parametrize("drive", DRIVES)
@pytest.mark.parametrize("answered", LABELS)
def test_dos_label_searches_the_root_for_a_label_and_answers_whether_it_found_one__an_argument_class(answered, drive):
    """A LABELLED ARGUMENT CLASS (the leaf machine, the scripted trap, the frame GEMDOS fills LAID BEFORE THE CALL):
    found is the answer's WORD being 0 — the name copied out, NUL and all, and 1; else 0 with AES_DOS_ERR and
    AES_DOS_AX both 1 whatever GEMDOS said, and nothing copied. The drive's letter is a BYTE sum."""
    (answer, name, found, failed, ax), (number, letter) = LABELS[answered], DRIVES[drive]
    result = dl.scripted(dl.DOS_LABEL, (number, dl.OUT_AT), [0x00FD_0001, answer],
                         merge_pokes(LABEL_OUT_STALE, dl.frame_laid(dl.DOS_LABEL, label_frame(name))))
    assert dl.GEMDOS.seen == label_seen(letter)
    assert result.long_answer() == found
    assert dl.verdict(result) == [vdi.STALE_LONG, addrs.AES_DOS_LABEL_TRAP_RETURN, failed, ax]
    copied = name + b"\0" if found else b""
    assert result.after(dl.OUT_AT, dl.OUT_BYTES) == copied + bytes([vdi.FILL]) * (dl.OUT_BYTES - len(copied))


def dfree(free, total, sector, cluster):
    return struct.pack(">IIII", free, total, sector, cluster)


@staged_over_the_arrival(SCRIPTED, FRAME_LAID)
def test_dos_space_at_its_arrival_answers_the_disk_s_size_and_free_space(staged):
    """Show Info of drive A: — SCRIPTED, Dfree's four longwords of the run in place LAID BEFORE THE CALL: both sizes
    through the caller's two pointers, 1; nothing parked, no verdict."""
    arrived, ran = dl.arrival(SPACE_AT), dl.ran_at(SPACE_AT)
    answers = frame_in_place(SPACE_AT, DFREE_BYTES)
    free, total, sector, cluster = struct.unpack(">IIII", answers)
    result = dl.held(arrived, dl.frame_laid(dl.DOS_SPACE, answers), answers=[ran.traps[0].answer])
    drive, total_out, avail_out = arrived.arguments
    assert dl.GEMDOS.seen == [dl.the_rom_s_pointed_at(ran.traps[0])] == [(dl.DFREE, b"", struct.pack(">H", drive))]
    assert (result.long(total_out), result.long(avail_out)) == (total * sector * cluster, free * sector * cluster)
    assert (case.long_in(ran.returned.ram, total_out), case.long_in(ran.returned.ram, avail_out)) == (total * sector * cluster, free * sector * cluster)
    assert result.long_answer() == ran.returned.registers["d0"] == 1
    assert dl.verdict(result) == dos_words(arrived.boot.ram), "the glue's four words as the chain left them: dos_space stores none"


# (Dfree's free, total, sector bytes, sectors a cluster; the total and the free space dos_space answers)
SPACES = {
    "a floppy": ((351, 711, 512, 2), 711 * 1024, 351 * 1024),
    "the low words alone are read": ((0x0002_0003, 0x0005_0007, 0x0011_0200, 0x0013_0002), 7 * 1024, 3 * 1024),
    "a cluster of 64 KB: its bytes' low word is 0": ((10, 20, 0x8000, 2), 0, 0),
    "a cluster product past 16 bits keeps its low word": ((3, 5, 0x4001, 4), 5 * 4, 3 * 4),
    "word operands at their top": ((0xFFFF, 0xFFFF, 0xFFFF, 1), 0xFFFF * 0xFFFF, 0xFFFF * 0xFFFF),
}


@pytest.mark.parametrize("answer", (GEMDOS_OK, EDRIVE), ids=("Dfree done", "Dfree refuses: never read"))
@pytest.mark.parametrize("which", SPACES)
def test_dos_space_multiplies_words__an_argument_class(which, answer):
    """A LABELLED ARGUMENT CLASS (the leaf machine, the scripted trap, Dfree's answers LAID BEFORE THE CALL): the ROM's
    arithmetic is three `mulu.w` — the low word of each longword, and the low word of the cluster's bytes — and its
    answer is 1 whatever Dfree said; the glue's four words are left as they were."""
    fields, total, avail = SPACES[which]
    stale_out = {dl.OUT_AT: bytes([vdi.FILL]) * dl.OUT_BYTES}
    result = dl.scripted(dl.DOS_SPACE, (0x1202, dl.OUT_AT, dl.OUT_AT + LONG_BYTES), [answer],
                         merge_pokes(stale_out, dl.frame_laid(dl.DOS_SPACE, dfree(*fields))))
    assert dl.GEMDOS.seen == [(dl.DFREE, b"", struct.pack(">H", 0x1202))]
    assert (result.long(dl.OUT_AT), result.long(dl.OUT_AT + LONG_BYTES), result.long_answer()) == (total, avail, 1)
    assert dl.verdict(result) == [vdi.STALE_LONG, vdi.STALE_LONG, aes.STALE_WORD, aes.STALE_WORD]


# ---- gsx_pline -----------------------------------------------------------------------------------------------------------------
PLINE_ARRIVALS = {"a drive's icon pressed: its outline drawn": At(dl.GSX_PLINE, DRAG_A, 0),
                  "...carried: the outline moved": At(dl.GSX_PLINE, DRAG_A, 1),
                  "a file's icon pressed": At(dl.GSX_PLINE, DELETE_THE_FILE, 0)}
PTSIN = aes.AES_GSX_PTSIN


@pytest.mark.parametrize("label", PLINE_ARRIVALS)
def test_gsx_pline_at_its_arrival_draws_the_outline_a_drag_carries(label):
    """AT THE ARRIVAL, the machine's own VDI on both shores: the icon's outline points moved by the mouse's offset into
    ptsin and drawn dotted — the megabyte, the screen in it, compared whole."""
    arrived = dl.arrival(PLINE_ARRIVALS[label])
    x, y, count, points = arrived.arguments
    result = dl.held(arrived, hook=gsx.vdi_hook)
    outline = [struct.unpack(">hh", arrived.boot.ram[points + 4 * nth:points + 4 * nth + 4]) for nth in range(count)]
    moved = [((px + x) & aes.WORD_MASK, (py + y) & aes.WORD_MASK) for px, py in outline]
    assert count > 2 and [struct.unpack(">HH", result.after(PTSIN + 4 * nth, 4)) for nth in range(count)] == moved
    assert result.answer() == aes.signed(dl.ran_at(PLINE_ARRIVALS[label]).returned.registers["d0"] & aes.WORD_MASK)


POINTS = {dl.TEXT_AT: vdi.pack_words(10, 20, 100, 20, 100, 90, 10, 90, 10, 20)}
PTSIN_STALE = {PTSIN: vdi.pack_words(*[aes.STALE_WORD] * 12)}
# (x, y, count): how many of the staged points are moved into ptsin
PLINES = {"five points": (3, 4, 5), "offsets that wrap a word": (0x7FFF, 0xFFF0, 3), "two points": (0, 0, 2),
          "one point: copied, no segment drawn": (5, 6, 1), "none": (5, 6, 0), "a negative count: none": (5, 6, 0xFFFF)}


@THROUGH
@pytest.mark.parametrize("which", PLINES)
def test_gsx_pline_moves_count_points_into_ptsin_and_draws_them__an_argument_class(which, through_line_f):
    """A LABELLED ARGUMENT CLASS (the leaf machine's screen, staged points): each point a longword copied, then its x
    and y moved by WORD sums; `count` a signed word; what follows ptsin's used part untouched."""
    x, y, count = PLINES[which]
    result = gsx.run_gsx(dl.GSX_PLINE, (x, y, count, dl.TEXT_AT), merge_pokes(POINTS, PTSIN_STALE), through_line_f=through_line_f)
    moved = max(aes.signed(count), 0)
    expected = []
    for nth in range(6):
        px, py = struct.unpack(">HH", POINTS[dl.TEXT_AT][4 * nth:4 * nth + 4]) if nth < moved else (None, None)
        expected.append(((px + x) & aes.WORD_MASK, (py + y) & aes.WORD_MASK) if nth < moved else (aes.STALE_WORD, aes.STALE_WORD))
    assert [struct.unpack(">HH", result.after(PTSIN + 4 * nth, 4)) for nth in range(6)] == expected


# ---- app_alloc, app_free -------------------------------------------------------------------------------------------------------
DESK_GLOBALS = aes.AES_DESK_GLOBALS
FREE_LIST, IN_USE = LEAF["DESK_ANODES_FREE"], LEAF["DESK_ANODES_IN_USE"]
ALLOC_ARRIVALS = {"the INF's first line: the list in use empty": At(dl.APP_ALLOC, SHOW_THE_FILE, 1),
                  "...its second: a node in use": At(dl.APP_ALLOC, SHOW_THE_FILE, 1, 2),
                  "...its fifth": At(dl.APP_ALLOC, SHOW_THE_FILE, 1, 5)}
# ...and THE TAIL'S ARM: the Install Disk Drive dialog's Install, whose caller (`$fdf210`) hands 0
TAIL_ARRIVAL = At(dl.APP_ALLOC, INSTALL_A_DRIVE, 4)
# app_free's: the dialog's Remove of drive A:, whose ANODE is the list in use's LAST (the INF's first line)
FREE_ARRIVAL = At(dl.APP_FREE, REMOVE_THE_DRIVE, 3)
# EVERY STORE OF THE TWO IS TO A LONGWORD THE ROUTINE HAS READ FIRST (a list's head, a node's link): the attribution
# pass would invert a pointer the next instruction follows.
LISTS_STEER = {"poison": False}


def lists(ram):
    """`(the free list, the list in use)` of the desk's ANODEs in the megabyte `ram`, each node's address in order."""
    desk = case.long_in(ram, DESK_GLOBALS) & dl.BUS
    found = []
    for head in (FREE_LIST, IN_USE):
        chain, node = [], case.long_in(ram, desk + head)
        while node and len(chain) < 64:
            chain.append(node)
            node = case.long_in(ram, node & dl.BUS)
        found.append(chain)
    return tuple(found)


@pytest.mark.parametrize("label", ALLOC_ARRIVALS)
def test_app_alloc_at_its_arrival_takes_the_free_list_s_first_node_to_the_head_of_the_list_in_use(label):
    """The desk reads DESKTOP.INF again once the viewer is done: each line's ANODE is the free list's first, pushed at
    the head of the list in use (every caller the chains reach passes 1) — and the node is D0, the run in place's."""
    at = ALLOC_ARRIVALS[label]
    arrived, ran = dl.arrival(at), dl.ran_at(at)
    free, in_use = lists(arrived.boot.ram)
    assert arrived.arguments == (1,) and len(in_use) == at.nth - 1 and free
    result = dl.held(arrived, **LISTS_STEER)
    assert lists(result.final) == (free[1:], [free[0], *in_use]) == lists(ran.returned.ram)
    assert result.long_answer() == free[0] == ran.returned.registers["d0"]


def with_argument(arrived, *arguments, routine=None):
    """AN ARGUMENT CLASS over an arrival's machine: the same megabyte, other arguments than its caller pushed — and,
    where said, ANOTHER ROUTINE of the unit entered over it."""
    return arrived._replace(arguments=arguments, routine=routine or arrived.routine)


def with_the_lists(arrived, **heads):
    """...and one whose megabyte has a list's head laid (`free=`, `in_use=`): a labelled staging."""
    desk = case.long_in(arrived.boot.ram, DESK_GLOBALS) & dl.BUS
    names = {"free": FREE_LIST, "in_use": IN_USE}
    return {desk + names[which]: struct.pack(">I", head) for which, head in heads.items()}


FIFTH = ALLOC_ARRIVALS["...its fifth"]


def test_app_alloc_at_the_install_dialog_s_arrival_links_the_node_at_the_tail():
    """THE TAIL'S ARM AT AN ARRIVAL (the second review's finding 1: it was a labelled class): Install Disk Drive's
    Install, its caller `$fdf210` handing 0 — the free list's first node goes BEHIND THE LAST of the nine in use, its
    own link cleared; the lists and D0 the run in place's."""
    arrived, ran = dl.arrival(TAIL_ARRIVAL), dl.ran_at(TAIL_ARRIVAL)
    free, in_use = lists(arrived.boot.ram)
    assert arrived.arguments == (0,) and arrived.return_site in {site + WORD_BYTES for site in call_sites(dl.APP_ALLOC)}
    result = dl.held(arrived, **LISTS_STEER)
    assert lists(result.final) == (free[1:], [*in_use, free[0]]) == lists(ran.returned.ram)
    assert result.long_answer() == free[0] == ran.returned.registers["d0"] and result.long(free[0] & dl.BUS) == 0


@pytest.mark.parametrize("to_head", (1, 0x0100), ids=("1", "0x0100: a word whose low byte is 0"))
def test_app_alloc_takes_any_word_but_0_for_the_head__an_argument_class(to_head):
    """A LABELLED ARGUMENT CLASS (every caller hands 0 or 1): the Install arrival's machine, the argument a word with
    no bit in its low byte (`tst.w`: the head) — and 1 beside it."""
    arrived = dl.arrival(TAIL_ARRIVAL)
    free, in_use = lists(arrived.boot.ram)
    result = dl.held(with_argument(arrived, to_head), **LISTS_STEER)
    assert lists(result.final) == (free[1:], [free[0], *in_use]) and result.long_answer() == free[0]


def test_app_alloc_asked_for_the_tail_of_an_empty_list_makes_the_node_its_head__an_argument_class():
    """A LABELLED ARGUMENT CLASS (no chain empties the list in use: the INF's lines fill it before any dialog can
    install): the first arrival's lists (none in use), the argument 0."""
    arrived = dl.arrival(ALLOC_ARRIVALS["the INF's first line: the list in use empty"])
    free, in_use = lists(arrived.boot.ram)
    result = dl.held(with_argument(arrived, 0), **LISTS_STEER)
    assert not in_use and lists(result.final) == (free[1:], [free[0]]) and result.long_answer() == free[0]


@pytest.mark.parametrize("to_head", (0, 1, 0x8000))
def test_app_alloc_with_no_node_free_answers_0_and_stores_nothing__an_argument_class(to_head):
    """A LABELLED ARGUMENT CLASS: the fifth arrival's machine with THE FREE LIST'S HEAD LAID 0 (thirty-two lines of an
    INF would empty it; the chains' has fewer)."""
    arrived = dl.arrival(FIFTH)
    result = dl.held(with_argument(arrived, to_head), with_the_lists(arrived, free=0), **LISTS_STEER)
    assert result.long_answer() == 0 and aes.stored_nothing(result)
    assert lists(result.final) == ([], lists(arrived.boot.ram)[1])


def test_app_free_at_the_remove_arrival_unlinks_the_last_node_and_pushes_it_on_the_free_list():
    """AT AN ARRIVAL (the second review's finding 1: there was none): Install Disk Drive's Remove of drive A:, whose
    node is the LAST of the nine in use — the node before it relinked to nothing, the node the free list's head; the
    lists the run in place's. And D0: the C answers nothing, the ROM's leaves THE NODE BEFORE (a named divergence,
    counted with the others: `test_d0_beyond_the_declared_answer…`)."""
    arrived, ran = dl.arrival(FREE_ARRIVAL), dl.ran_at(FREE_ARRIVAL)
    free, in_use = lists(arrived.boot.ram)
    (node,) = arrived.arguments
    assert node == in_use[-1] and arrived.return_site in {site + WORD_BYTES for site in call_sites(dl.APP_FREE)}
    result = dl.held(arrived, **LISTS_STEER)
    assert lists(result.final) == ([node, *free], in_use[:-1]) == lists(ran.returned.ram)
    assert ran.returned.registers["d0"] == in_use[-2]


# The arms of app_free no chain's Remove reaches, over the fifth INF-parse arrival's lists: the head (the INF's LAST
# line's node — an application's, which no dialog removes) and a node on no list; and A MIDDLE NODE — the arm of the
# Remove arrival above with a non-zero link to relink, REACHABLE IN PRINCIPLE (drive B:'s Remove), NO CHAIN YET.
FREED = {"the head": lambda free, in_use: in_use[0],
         "a middle node (reachable in principle: drive B:'s Remove, no chain yet)": lambda free, in_use: in_use[2],
         "a node on no list in use (the free list's second)": lambda free, in_use: free[1]}


def freed(which):
    """`(the arrival's machine, the lists, the node)`: the fifth arrival's lists and one of their nodes."""
    arrived = dl.arrival(FIFTH)
    free, in_use = lists(arrived.boot.ram)
    return arrived, free, in_use, FREED[which](free, in_use)


@THROUGH
@pytest.mark.parametrize("which", FREED)
def test_app_free_unlinks_the_node_and_pushes_it_on_the_free_list__an_argument_class(which, through_line_f):
    """A LABELLED ARGUMENT CLASS (the arms the Remove arrival does not take): THE LISTS AS THE ROM'S OWN INF PARSE LEFT
    THEM at its fifth app_alloc, and one of their nodes handed. The node leaves the list in use — the head moved on,
    or the node before it relinked; one on no such list unlinks nothing — and becomes the free list's head."""
    arrived, free, in_use, node = freed(which)
    result = dl.held(with_argument(arrived, node, routine=dl.APP_FREE), through_line_f=through_line_f, **LISTS_STEER)
    assert lists(result.final)[1] == [each for each in in_use if each != node]
    assert result.long((case.long_in(arrived.boot.ram, DESK_GLOBALS) & dl.BUS) + FREE_LIST) == node
    assert result.long(node & dl.BUS) == free[0], "its link names the free list's old head (which was the node's own next, for the free list's second)"


# ---- gsx_hardcopy ----------------------------------------------------------------------------------------------------------------
@contextlib.contextmanager
def hardcopy_doors():
    """The candidate's VDI calls served by the VDI's own cores, and the dump routine `scr_dump` names by its twin."""
    with isr.staged_routines({**gsx.vdi_functions(), **vdi_escape.dump_routines()}) as hook:
        yield hook


@THROUGH
@pytest.mark.parametrize("dumpflg", (0, 0xFFFF), ids=("no dump pending", "_dumpflg -1"))
def test_gsx_hardcopy_is_the_vdi_s_escape_17_which_is_xbios_scrdmp__an_argument_class(dumpflg, through_line_f):
    """A LABELLED ARGUMENT CLASS — THE PRINTER IS A DEVICE THE MODEL HAS NOT: `scr_dump` names A STAGED ROUTINE that
    reports `_dumpflg` and counts its calls (`vdi_escape`'s), where the machine's own is the ROM's dump to the
    parallel port. What is held: contrl[5] 17, VDI 5 through the trap, Scrdmp's routine called ONCE."""
    pokes = merge_pokes(vdi_escape.hardcopy_pokes(dumpflg), aes.stale_fields("GSX_SUBFUNCTION", "GSX_OPCODE"))
    result = aes.run_function(dl.GSX_HARDCOPY, (), aes.leaf_machine(onto=pokes), hook=hardcopy_doors, poison=False,
                              through_line_f=through_line_f)
    assert result.field("AES", "GSX_SUBFUNCTION") == vdi_escape.ARMS["V_HARDCOPY"] == 17
    assert result.field("AES", "GSX_OPCODE") == addrs.VDI_ROM_ESCAPE_OPCODE
    assert result.after(vdi_escape.DUMP_REPORT + WORD_BYTES, 1) == b"\x01", "the dump routine ran once"


# ---- trp13: the BIOS door ----------------------------------------------------------------------------------------------------------
FORCED_CHANGE = "Rwabs(0, NULL, 2, 0, A:): the media change forced"
DOOR_ARRIVALS = {"Drvmap: a drive opened, its letter checked against the map": At(dl.TRP13, OPEN_A, 0),
                 FORCED_CHANGE: At(dl.TRP13, OPEN_A, 0, 2),
                 "Bconout(CON:, a character): the viewer's text": At(dl.TRP13, SHOW_THE_FILE, 0)}
BIOS_RETURN = aes.AES_BIOS_RETURN
savptr_frame = dl.savptr_frame          # (its home: `aes_deskleaves`, shared with unit M's engine cases)


def replayed_driver(arrived, ran, made):
    """THE ROM'S DISK DRIVER REPLAYED FROM THE RUN IN PLACE, for the C: `{BIOS function: effect}` — each call kept in
    `made`, answered the run in place's D0, and THE BYTES THAT RUN'S BIOS CHANGED outside the stack LAID (the
    driver's own media-change byte)."""
    trap = ran.traps[0]
    changed = [(at, trap.boot.ram[at]) for at in range(0, 0x8000) if trap.boot.ram[at] != arrived.boot.ram[at]]

    def effect(function):
        def answered(buf, rwflag, buffer, count, recno, dev):
            made.append((function, rwflag, buffer, count, recno, dev))
            for at, byte in changed:
                if not savptr_frame(arrived.boot.ram)[0][0] <= at < savptr_frame(arrived.boot.ram)[0][1]:
                    buf[at] = byte
            return aes.signed(trap.answer, bits=32)
        return answered
    return {function: effect(function) for function in (addrs.BIOS_RWABS_FN, addrs.BIOS_GETBPB_FN)}


def refused_by_the_door(refused):
    return f"the door's C asked the disk vectors for BIOS function(s) {sorted(set(refused))}, which this case does not serve"


@pytest.mark.parametrize("label", DOOR_ARRIVALS, ids=[f"{label} [{DRIVER_REPLAYED}]" if label == FORCED_CHANGE else label for label in DOOR_ARRIVALS])
def test_the_bios_door_at_its_arrival_parks_its_return_and_answers_the_bios(label):
    """AT THE ARRIVAL, THE MACHINE'S OWN BIOS under the ROM's door: Drvmap and Bconout the BIOS routines' own C cores
    under ours; the forced media change — the ROM's floppy driver, which is not ours — REPLAYED FROM THE RUN IN PLACE
    for the C (its answer, the bytes it changed: a labelled class). The return parked, D0 the BIOS's, and the megabyte
    — the console's screen in it — but the BIOS's own save frame."""
    at = DOOR_ARRIVALS[label]
    arrived, ran = dl.arrival(at), dl.ran_at(at)
    made = []
    hook = lambda: fs.DISK_HOOK.staged(replayed_driver(arrived, ran, made), refused_by_the_door)         # noqa: E731
    result = dl.held(arrived, hook=hook, poison=False, dropped_windows=(*aes.LINE_F_MASK_WINDOW, *savptr_frame(arrived.boot.ram)))
    assert result.long(BIOS_RETURN) == SENTINEL
    assert result.long_answer() == ran.returned.registers["d0"] == ran.traps[0].answer
    function, *words = arrived.arguments
    if function == addrs.BIOS_RWABS_FN:
        rwflag, high, low, count, recno, dev = (word & aes.WORD_MASK for word in words)
        assert made == [(addrs.BIOS_RWABS_FN, rwflag, high << 16 | low, count, recno, dev)] == [(4, 0, 0, 2, 0, 0)]
    else:
        assert not made and function in (addrs.BIOS_DRVMAP_FN, addrs.BIOS_BCONOUT_FN)


RAW_CONSOLE = 5                         # the BIOS's device 5: a character drawn as its glyph, no control code obeyed


def test_the_bios_door_hands_bconout_its_device_then_its_character__an_argument_class():
    """A LABELLED ARGUMENT CLASS: the viewer's Bconout arrival, ITS MACHINE, THE CHARACTER 5 in place of the text's —
    a number that is a device too (the raw console's). Bconout(CON:, 5) leaves another screen than Bconout(5, 2):
    the megabyte, the console's screen in it, tells the two words' order."""
    at = DOOR_ARRIVALS["Bconout(CON:, a character): the viewer's text"]
    arrived = dl.arrival(at)
    function, device, _character, *stale = arrived.arguments
    result = dl.held(with_argument(arrived, function, device, RAW_CONSOLE, *stale), poison=False,
                     dropped_windows=(*aes.LINE_F_MASK_WINDOW, *savptr_frame(arrived.boot.ram)))
    assert (function, device) == (addrs.BIOS_BCONOUT_FN, 2) and result.long(BIOS_RETURN) == SENTINEL


def test_the_door_s_arrivals_are_the_three_shapes_the_chains_callers_push():
    """Drvmap's frame is the function word ALONE — the six words the C is handed past it are its caller's stack, as
    they lie; the forced change is Rwabs's whole frame; the viewer's is Bconout(2, a character)."""
    drvmap, forced, conout = (dl.arrival(at).arguments for at in DOOR_ARRIVALS.values())
    assert drvmap[0] == addrs.BIOS_DRVMAP_FN and forced == (addrs.BIOS_RWABS_FN, 0, 0, 0, 2, 0, 0)
    assert conout[:2] == (addrs.BIOS_BCONOUT_FN, 2) and 0 < conout[2] < 0x100


def disk_door(made):
    """The staged RAM disk's driver for the C, each call kept in `made`."""
    def kept(function, effect):
        def called(buf, *arguments):
            made.append((function, *arguments))
            return effect(buf, *arguments)
        return called
    return lambda: fs.DISK_HOOK.staged({function: kept(function, effect) for function, effect in fs.DRIVER.items()}, refused_by_the_door)


# (the frame past the function: six words; the disk call the C makes)
SECTOR_AT = fs.USER_AT
DISK_FRAMES = {
    "Getbpb(B:) — the format's and the copy's shape": ((addrs.BIOS_GETBPB_FN, 1, 0x1111, 0x2222, 0x3333, 0x4444, 0x5555),
                                                      (addrs.BIOS_GETBPB_FN, 0, 0, 0, 0, 1)),
    "Rwabs(read, a buffer, 1 sector, record 5, A:)": (
        (addrs.BIOS_RWABS_FN, 0, SECTOR_AT >> 16, SECTOR_AT & aes.WORD_MASK, 1, fs.ROOT_RECORD, 0),
        (addrs.BIOS_RWABS_FN, 0, SECTOR_AT, 1, fs.ROOT_RECORD, 0)),
    "Rwabs(write, the same)": (
        (addrs.BIOS_RWABS_FN, 1, SECTOR_AT >> 16, SECTOR_AT & aes.WORD_MASK, 2, fs.DATA_RECORD, 0),
        (addrs.BIOS_RWABS_FN, 1, SECTOR_AT, 2, fs.DATA_RECORD, 0)),
    # (no sector moves: what is held is the buffer's longword as the driver is handed it — its two words differ)
    "Rwabs(read, a buffer whose two words differ, NO sector)": (
        (addrs.BIOS_RWABS_FN, 0, 0x0001, 0x2344, 0, fs.ROOT_RECORD, 0), (addrs.BIOS_RWABS_FN, 0, 0x0001_2344, 0, fs.ROOT_RECORD, 0)),
}


@THROUGH
@pytest.mark.parametrize("which", DISK_FRAMES)
def test_the_bios_door_hands_the_disk_calls_their_whole_frame__an_argument_class(which, through_line_f):
    """A LABELLED ARGUMENT CLASS (the leaf machine, THE STAGED RAM DISK behind the three disk vectors, `gemdos_fs`'s:
    the ROM's BIOS dispatches into its stubs, the C into its twin): Getbpb's and Rwabs's frames as the desk's format
    and copy push them — the BPB's address, a sector read into the caller's buffer, two written from it."""
    arguments, expected = DISK_FRAMES[which]
    made = []
    machine = aes.leaf_machine(onto=fs.machine(merge_pokes(fs.user_buffer(bytes(range(256)) * 4), {BIOS_RETURN: struct.pack(">I", vdi.STALE_LONG)})))
    result = aes.run_function(dl.TRP13, arguments, machine, hook=disk_door(made), poison=False, through_line_f=through_line_f,
                              host_arguments=(site_parked(through_line_f),))
    assert made == [expected]
    assert result.long(BIOS_RETURN) == site_parked(through_line_f)
    if arguments[0] == addrs.BIOS_GETBPB_FN:
        assert result.long_answer() == fs.BPB_AT
    elif not arguments[4]:
        assert result.after(SECTOR_AT, fs.SECTOR_BYTES) == (bytes(range(256)) * 2), "no sector asked for, none moved"
    elif arguments[1]:
        assert result.after(fs.IMAGE_AT + fs.DATA_RECORD * fs.SECTOR_BYTES, 1024) == (bytes(range(256)) * 4)
    else:
        assert result.after(SECTOR_AT, fs.SECTOR_BYTES) == fs.DISK[fs.ROOT_RECORD * fs.SECTOR_BYTES:][:fs.SECTOR_BYTES]


def test_the_door_s_c_halts_by_name_over_a_function_the_desk_does_not_ask():
    """Off target the door serves the four BIOS functions the desk's callers name; any other halts by name, in a child."""
    import vdi_helpers
    returncode, stderr, _image = vdi_helpers.refusal_over(
        "aes_trp13", aes.leaf_machine(), arguments=(("ctypes.c_uint32", hex(SENTINEL)), ("ctypes.c_int16", "1"),
                                                   *[("ctypes.c_int16", "0")] * dl.TRP13_ARGUMENT_WORDS), read_back=False)
    assert returncode != 0 and "trp13" in stderr and "Drvmap" in stderr, stderr


# ---- WHAT A ROM CALLER IS LEFT: D0 beyond the declared answer, and A0 — NAMED, COUNTED ------------------------------------------
# D0 BEYOND THE ANSWER. dos_mkdir answers a WORD (`move.w d1,d0 / eori.w #1,d0`): the high word of the ROM's D0 is still
# Dcreate's. app_free and gsx_hardcopy answer nothing in C: the ROM's leave what their last instruction held (app_free
# the node before the freed one, or its caller's D0; gsx_hardcopy the VDI trap's). gsx_pline answers gsx_xline's word.
# NO ROM CALLER READS ANY OF THEM (`aes_deskbind.answer_readers` at every site: `test_no_rom_caller_reads_...`).
D0_BEYOND_THE_ANSWER = {dl.DOS_MKDIR: "D0's high word: Dcreate's answer's",
                        dl.GSX_PLINE: "D0's high word: gsx_xline's leftover (gsx_1code's)",
                        dl.APP_FREE: "all of D0: the node before the freed one, or its caller's own D0 (the head freed)",
                        dl.GSX_HARDCOPY: "all of D0: the VDI trap's"}
# A0. Every entry of the glue returns with A0 THE ADDRESS IT RETURNED THROUGH — `__DOS`'s parked site, or (through
# `$fe3c28` and dos_rename) its caller's own return address; dos_label's and dos_space's hold a pointer of their own
# (the copied name's end, the first answer pointer); trp13 the BIOS's leftover. A C function owes its caller no A0:
# NONE OF THE EIGHTEEN HOLDS IT, and the glue's thirteen arrivals below count what the ROM's leave.
EVERY_ARRIVAL = {**GLUE_ARRIVALS, "dos_setdt": SETDT_AT, "dos_label": LABEL_AT, "dos_space": SPACE_AT,
                 **PLINE_ARRIVALS, **ALLOC_ARRIVALS, "app_alloc, the tail": TAIL_ARRIVAL, "app_free": FREE_ARRIVAL, **DOOR_ARRIVALS}


def test_d0_beyond_the_declared_answer_is_a_named_counted_divergence_at_the_arrivals():
    """NAMED, COUNTED: at the arrivals of the routines whose C answers less than a longword, how many times the ROM's
    own run in place left D0 bits the C does not answer SET — dos_mkdir's one (Dcreate answered 0: the high word 0),
    gsx_pline's three (none) and app_free's one (THE NODE BEFORE THE FREED ONE: one of the five). gsx_hardcopy, the
    one routine of the unit no chain reaches, has no arrival."""
    beyond = {}
    for label, at in EVERY_ARRIVAL.items():
        restype = vdi.ALCYON[at.routine].restype
        if restype is aes.LONG_ANSWER:
            assert at.routine not in D0_BEYOND_THE_ANSWER
            continue
        assert at.routine in D0_BEYOND_THE_ANSWER, f"{at.routine} answers less than D0 and names no divergence"
        left = dl.ran_at(at).returned.registers["d0"]
        beyond[label] = left if restype is None else left >> 16
    assert len(beyond) == 5 and [label for label, high in beyond.items() if high] == ["app_free"], beyond
    assert {at.routine for at in EVERY_ARRIVAL.values()} == set(dl.UNIT_O) - {dl.GSX_HARDCOPY}


def test_a0_at_return_is_the_address_the_glue_returned_through__the_rom_s_runs_in_place():
    """NAMED, COUNTED: over the arrivals, the ROM's A0 at return — the parked site for the entries that `bsr` to
    `__DOS`, the caller's own return address for those that park it (through `$fe3c28`, and dos_rename). Thirteen of
    the glue's arrivals (all but dos_avail's, and dos_label's and dos_space's, whose A0 is a pointer of their own);
    the C holds none of them. No ROM caller reads A0 behind a call: A READING, not a test (the 39 sites' first
    instructions were read for it by unit O)."""
    through_the_tail = (dl.DOS_RAWCIO, dl.DOS_DELETE, dl.DOS_RMDIR, dl.DOS_CREATE, dl.DOS_CHMOD, dl.DOS_RENAME)
    counted = 0
    for label, at in {**GLUE_ARRIVALS, "dos_setdt": SETDT_AT}.items():
        if at.routine == dl.DOS_AVAIL:
            continue
        arrived, a0 = dl.arrival(at), dl.ran_at(at).returned.registers["a0"]
        assert a0 == (arrived.return_site if at.routine in through_the_tail else GLUE_SITE[at.routine]), label
        counted += 1
    assert counted == 13


# WHO READS D0 behind each Line-F call of a routine whose D0 the C does not hold whole: unit D's reading of every call
# site (`aes_deskbind.answer_readers`: both arms of every branch to a read, an overwrite or a call of D0, and through a
# caller that returns it) — not one instruction behind the call (the second review's finding 8: at `$fdf390` that
# instruction leaves D0 live, and D0 dies three instructions on).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "aes_map"))
import linef_dis                        # noqa: E402


@functools.cache
def call_sites(name):
    """The Line-F calls of `addrs.<name>` THAT ARE INSTRUCTIONS, in address order: `aes.line_f_call_sites` reads every
    even word of the GEM text and so counts an operand that happens to be the call word (`$fddc46`, `$fe1d2e`: the
    low halves of two string addresses) — each candidate is held to lie on an instruction boundary of the routine
    that holds it, read from that routine's start (`linef_dis.sweep`)."""
    def is_an_instruction(site):
        start = max(start for start in aes_desk.inventoried() if start <= site)
        return any(at == site and text is None for at, _length, text in linef_dis.sweep(start, site + WORD_BYTES))
    return tuple(sorted(site for found in aes.line_f_call_sites(name).values() for site in found if is_an_instruction(site)))


def test_no_rom_caller_reads_d0_behind_a_call_of_the_four_whose_c_answers_less():
    """BY READING EVERY PATH, at every Line-F site of dos_mkdir (four), gsx_pline, app_free and gsx_hardcopy (one
    each): `aes_deskbind.answer_readers` finds NO instruction that reads D0 before a call, an overwrite or the
    routine's return (and through the callers that return it) — the sites its listing holds are the sites this
    battery holds to an instruction boundary. Its teeth: the same reading finds unit D's nine read answers
    (`test_desk_bind.py`)."""
    sites = {name: call_sites(name) for name in D0_BEYOND_THE_ANSWER}
    assert {name: len(found) for name, found in sites.items()} == {dl.DOS_MKDIR: 4, dl.GSX_PLINE: 1, dl.APP_FREE: 1, dl.GSX_HARDCOPY: 1}
    for name, found in sites.items():
        routine = getattr(addrs, name)
        assert tuple(sorted(aes_deskbind.calls_of(routine))) == found
        assert aes_deskbind.answer_readers(routine) == set(), f"{name}'s D0 is read"
    assert aes_deskbind.answer_readers(addrs.AES_ROM_DESK_OBJC_FIND), "the reading's teeth: objc_find's answer IS read"


def test_the_unit_s_routines_are_called_from_the_desk_s_text_alone_at_thirty_nine_sites():
    """THE CALLERS, read off the ROM: every Line-F call of a routine of the unit lies in the desk's own text or its
    utilities' (band 6's: the ROM's until each is ported) — none in a routine bands 0-5 own."""
    sites = sorted(site for name in dl.UNIT_O for site in call_sites(name))
    assert len(sites) == 39
    assert all(any(lo <= site < hi for lo, hi in (aes_desk.DESK_TEXT, aes_desk.UTILITY_TEXT)) for site in sites)


# ---- THE BLOBS' CORES OVER THE SAME MACHINES: the kit's second differential — unbound, unpriced ---------------------------------
def stack_filled(word, depth=0x60):
    """A LABELLED STAGING for a routine that reads a frame of its own GEMDOS would have filled: the run's stack under
    its top filled with one WORD — the blob's frame lies where GCC put it, the ROM's where its `link` did, and a
    pattern of period two reads the same wherever either lies."""
    return {emu.STACK_TOP - depth: struct.pack(">H", word) * (depth // WORD_BYTES)}


def at_an_arrival(at, **case_s_own):
    """A blob case over the arrival `at`: its megabyte, the arguments its caller pushed, the run in place's answers."""
    arrived = dl.arrival(at)
    scripted = at.routine != dl.TRP13 and dl.TRAP_RETURNS[at.routine]
    return {"name": at.routine, "arguments": arrived.arguments, "ram": arrived.boot.ram,
            "answers": answers_in_place(at) if scripted else None, **case_s_own}


def on_the_blobs():
    """`{label: the case}` — one or more for each of the eighteen but gsx_hardcopy (its Scrdmp is a routine the case
    stages for the host alone)."""
    fifth = dl.arrival(FIFTH)
    _free, in_use = lists(fifth.boot.ram)
    return {
        **{label: at_an_arrival(at) for label, at in GLUE_ARRIVALS.items()},
        "dos_setdt: a file copied into a folder": at_an_arrival(SETDT_AT),
        "dos_label: Show Info, answered EFILNF (the frame is not read)": {**at_an_arrival(LABEL_AT), "answers": [EFILNF]},
        "dos_label: Show Info, found (the stack filled with 'A', NUL)": at_an_arrival(LABEL_AT, layers=(stack_filled(0x4100),)),
        "dos_space: Show Info (the stack filled with the word 3)": at_an_arrival(SPACE_AT, layers=(stack_filled(3),)),
        **{f"gsx_pline: {label}": at_an_arrival(at) for label, at in PLINE_ARRIVALS.items()},
        **{f"app_alloc: {label}": at_an_arrival(at, settles_the_mask=True) for label, at in ALLOC_ARRIVALS.items()},
        **{f"app_free (the fifth arrival's lists): {which}": {"name": dl.APP_FREE, "arguments": (node,), "ram": fifth.boot.ram,
                                                              "settles_the_mask": True}
           for which, node in (("the head", in_use[0]), ("a middle node", in_use[2]), ("the last", in_use[-1]))},
        "dos_rename (the leaf machine)": {"name": dl.DOS_RENAME, "arguments": (dl.TEXT_AT, dl.OTHER_TEXT_AT), "answers": [GEMDOS_OK], "layers": (TEXTS,)},
        "dos_rename (the leaf machine), refused": {"name": dl.DOS_RENAME, "arguments": (dl.TEXT_AT, dl.OTHER_TEXT_AT), "answers": [EACCDN], "layers": (TEXTS,)},
        "dos_chmod (the leaf machine)": {"name": dl.DOS_CHMOD, "arguments": (dl.TEXT_AT, 1, 0x21), "answers": [0x21], "layers": (TEXTS,)},
        "dos_mkdir (the leaf machine), EACCDN": {"name": dl.DOS_MKDIR, "arguments": (dl.TEXT_AT,), "answers": [EACCDN], "layers": (TEXTS,)},
        "app_alloc: Install Disk Drive's Install (the tail)": at_an_arrival(TAIL_ARRIVAL, settles_the_mask=True),
        "app_free: Install Disk Drive's Remove (the last)": at_an_arrival(FREE_ARRIVAL, settles_the_mask=True),
        **{f"trp13: {label}": at_an_arrival(at, dropped=savptr_frame(dl.arrival(at).boot.ram)) for label, at in DOOR_ARRIVALS.items()},
    }


ON_THE_BLOBS = ("dos_write: Save Desktop writes DESKTOP.INF", "dos_gdir: Save Desktop asks the current path",
                "dos_create: Save Desktop creates DESKTOP.INF", "dos_create: a file copied into a folder", "dos_mkdir: New Folder",
                "dos_avail: a file copy sizes its buffer", "dos_delete: a file dragged to the trash",
                "dos_rmdir: a folder dragged to the trash", "dos_rawcio: the viewer's carriage return",
                "dos_rawcio: the viewer's line feed", "dos_rename: Show Info renames the file", "dos_chmod: Show Info makes the file read-only",
                "dos_delete: a read-only file dragged to the trash — GEMDOS answers EACCDN", "dos_setdt: a file copied into a folder",
                "dos_label: Show Info, answered EFILNF (the frame is not read)",
                "dos_label: Show Info, found (the stack filled with 'A', NUL)", "dos_space: Show Info (the stack filled with the word 3)",
                "gsx_pline: a drive's icon pressed: its outline drawn", "gsx_pline: ...carried: the outline moved",
                "gsx_pline: a file's icon pressed", "app_alloc: the INF's first line: the list in use empty",
                "app_alloc: ...its second: a node in use", "app_alloc: ...its fifth",
                "app_free (the fifth arrival's lists): the head", "app_free (the fifth arrival's lists): a middle node",
                "app_free (the fifth arrival's lists): the last", "dos_rename (the leaf machine)",
                "dos_rename (the leaf machine), refused", "dos_chmod (the leaf machine)", "dos_mkdir (the leaf machine), EACCDN",
                "app_alloc: Install Disk Drive's Install (the tail)", "app_free: Install Disk Drive's Remove (the last)",
                "trp13: Drvmap: a drive opened, its letter checked against the map",
                "trp13: Rwabs(0, NULL, 2, 0, A:): the media change forced", "trp13: Bconout(CON:, a character): the viewer's text")


def blob_id(label):
    """A blob case's id: what it stages said — every glue entry's GEMDOS is the trap that keeps its last call."""
    return f"{label} [{LAST_CALL_TRAP}]" if label.startswith("dos_") else label


def test_the_blob_cases_are_the_ones_listed_and_leave_out_the_hardcopy_alone():
    assert tuple(on_the_blobs()) == ON_THE_BLOBS
    assert {case_s["name"] for case_s in on_the_blobs().values()} == set(dl.UNIT_O) - {dl.GSX_HARDCOPY}
    assert [label for label, case_s in on_the_blobs().items() if case_s.get("answers")] == [label for label in ON_THE_BLOBS if label.startswith("dos_")], (
        "the ids say which cases stage the trap that keeps its last call: the glue's, and only theirs")


# trp13's C TWIN SHIPS NOWHERE since its flip (a row of the transcribed table): the shipped blob's `aes_trp13` is the glue
# into the `.S`, which parks ITS OWN return in AES_BIOS_RETURN where the twin parks the site it is handed — trp14's twin's
# arrangement (`test_aes_trp14.py`). So the twin's blob cases run on the bench blob, which links it; the `.S` is held at
# the same arrivals by the transcription relation (`test_the_door_s_transcription_behaves_as_the_rom_…`, its rows).
THE_SHIPPED_BLOB = "the shipped blob"
ON_A_BLOB = [(label, blob_name) for label in ON_THE_BLOBS for blob_name in isr.BLOBS
             if not (on_the_blobs()[label]["name"] == dl.TRP13 and blob_name == THE_SHIPPED_BLOB)]


@pytest.mark.parametrize("label, blob_name", ON_A_BLOB, ids=[f"{blob_id(label)}-{blob_name}" for label, blob_name in ON_A_BLOB])
def test_a_blob_s_core_is_held_to_the_rom_s_routine_over_the_same_machine(label, blob_name):
    """THE TARGET ARMS RUN (`aes_deskleaves.on_a_blob`): the ROM's routine and the blob's core over one machine — an
    arrival's megabyte less the blob's span, or the leaf machine — held by the kit's second differential: D0 at the
    declared width, the megabyte, the streams; and the core ran (its cycles are its own, above the entry's). (Since the
    flip each such case of an arrival is a ROW too: `ROWS`, below.)"""
    measured = dl.on_a_blob(isr.blob_named(blob_name), **on_the_blobs()[label])
    assert measured.recreate_net > 0 and measured.original_net > 0


# ...AND THE GLUE INTO THE `.S` AS IT SHIPS (slice F1's fix pass): drive_check, Format and the copy reach the door through
# the shipped blob's `aes_trp13` thunk (`bench/shipped_glue.py`), which no bound path runs yet — so each arrival enters it
# here, a C call of the thunk ON THE SHIPPED BLOB held to the ROM's door by the same second differential. Beside the
# BIOS's save frame it leaves out AES_BIOS_RETURN alone: the `.S` parks the glue's return there, the ROM's door its own
# caller's (the declared divergence, `test_the_bios_door_s_parked_return_is_named_by_trp13_alone`).
GLUE_S_RETURN_PARKED = ((BIOS_RETURN, BIOS_RETURN + LONG_BYTES,
                         "AES_BIOS_RETURN: the `.S` parks the glue's return, the ROM's door its caller's — read by trp13 alone"),)


@pytest.mark.parametrize("label", DOOR_ARRIVALS)
def test_the_shipped_glue_into_the_door_is_held_to_the_rom_s_door(label):
    door_s = on_the_blobs()[f"trp13: {label}"]
    measured = dl.on_a_blob(isr.blob_named(THE_SHIPPED_BLOB), **{**door_s, "dropped": door_s["dropped"] + GLUE_S_RETURN_PARKED})
    assert measured.recreate_net > 0 and measured.original_net > 0


# (the entry's last GEMDOS call as the trap keeps it: the function, the frame's own words, the longword behind a pointer)
LAST_CALLS = {
    "dos_chmod (the leaf machine)": (dl.FATTRIB, (dl.TEXT_AT >> 16, dl.TEXT_AT & aes.WORD_MASK, 1, 0x21), None),
    "dos_rename (the leaf machine)": (dl.FRENAME, (0, dl.TEXT_AT >> 16, dl.TEXT_AT & aes.WORD_MASK, dl.OTHER_TEXT_AT >> 16,
                                                   dl.OTHER_TEXT_AT & aes.WORD_MASK), None),
    "dos_label: Show Info, answered EFILNF (the frame is not read)": (dl.FSFIRST, (FA_VOLUME_LABEL,), int.from_bytes(b"A:\\*", "big")),
}


@pytest.mark.parametrize("blob_name", tuple(isr.BLOBS))
def test_what_the_blob_cases_trap_with_is_kept_and_compared__the_rom_s_own_last_calls(blob_name):
    """THE TRAP KEEPS ITS LAST CALL in cells the megabyte compare reaches (`aes_deskleaves.last_call_trap`): a target
    arm that pushed its frame in another order would differ there. What the ROM's own run leaves in them, for three:
    Fattrib's name, flag and attributes; Frename's reserved word and two names; Fsfirst's attribute and the first
    four characters of the path it is pointed at. And dos_setdt's: the handle, the 1, and the stamp behind the pointer."""
    bench = isr.blob_named(blob_name)
    for label, expected in LAST_CALLS.items():
        assert dl.the_rom_s_last_call(bench, **on_the_blobs()[label]) == expected, label
    handle, stamp = dl.arrival(SETDT_AT).arguments
    assert dl.the_rom_s_last_call(bench, **on_the_blobs()["dos_setdt: a file copied into a folder"]) == (dl.FDATIME, (handle, 1), stamp)


# ---- FLIPPED (band 6 slice F1): linked into both blobs, and the table's entries the unit's ----------------------------------------
BLOBS = pytest.mark.parametrize("blob_name", tuple(isr.BLOBS))
def cores():
    """`{the core's symbol: its routine}` for the eighteen."""
    return {routines.core_symbol(name): name for name in dl.UNIT_O}


TRP13_ENTRY = transcription.transcription_symbol(dl.TRP13)
TRP13_ENTRIES = 2                       # the door has two entries in the ROM's table (`$f1a0`, `$f708`); every other routine one


@BLOBS
def test_both_blobs_link_the_eighteen_cores_and_the_table_reaches_seventeen_through_their_thunks(blob_name):
    """LINKED: every core is a sized function of the blob, and the door's `.S` entry is defined. FLIPPED: the
    seventeen thunked cores are each called by THEIR OWN THUNK of the table (`linef_to_<core>`), and no function of the
    unbound desk's but the unit's own reaches them otherwise — what calls them besides is the desk's C of later waves
    (held, wave 1b's) and the unit's own. The door's `.S` is reached by the table's two entries and, on the shipped
    blob, by the glue its C callers reach it through (`aes_trp13`: drive_check's, Format's, the copy's)."""
    blob = isr.blob_named(blob_name)
    defined = {symbol.name for symbol in transcription.symbol_table(blob.elf) if symbol.kind in "Tt"}
    assert set(cores()) <= defined and TRP13_ENTRY in defined
    graph = transcription.call_graph(blob.elf)
    thunked = set(cores()) - {routines.core_symbol(dl.TRP13)}
    for core in thunked:
        assert core in graph[_linef_table().THUNK_PREFIX + core], f"{core}'s thunk does not call it"
    assert not aes_deskbind.bound_referrers(blob, ()), "a function outside the unbound desk refers to a core still held"
    callers = sorted(caller for caller, callees in graph.items() if TRP13_ENTRY in callees)
    assert callers == (["aes_trp13"] if blob_name == THE_SHIPPED_BLOB else []), callers


@BLOBS
def test_no_longword_of_a_blob_outside_the_unbound_desk_holds_a_held_core_s_address(blob_name):
    """...and no held core is named BY VALUE (`aes_deskbind.bound_longwords`) outside the unbound desk's own
    instructions — the unit's own cores are no longer held: the table names its thunks and the door's `.S`."""
    assert not aes_deskbind.bound_longwords(isr.blob_named(blob_name))


def test_every_line_f_table_entry_that_names_a_routine_of_the_unit_is_ours():
    """THE TABLE'S VERDICT (`bench/linef_table.py`): the eighteen routines of the unit — nineteen entries, trp13's two
    — are OURS: seventeen THROUGH A THUNK of their core, and trp13's two NATIVE, its `.S` entry (a row of the
    transcribed table since the flip). None is held."""
    linef_table = _linef_table()
    assert not set(dl.UNIT_O) & set(linef_table.LINKED_AND_NOT_FLIPPED)
    of_the_unit = {getattr(addrs, name): name for name in dl.UNIT_O}
    entries = [entry for entry in linef_table.entries() if entry.target in of_the_unit]
    assert {of_the_unit[entry.target] for entry in entries} == set(dl.UNIT_O), "every routine of the unit has a Line-F word"
    assert len(entries) == len(dl.UNIT_O) - 1 + TRP13_ENTRIES and sum(entry.target == addrs.AES_ROM_TRP13 for entry in entries) == TRP13_ENTRIES
    for entry in entries:
        name = of_the_unit[entry.target]
        expected = ((linef_table.OURS_NATIVE, TRP13_ENTRY) if name == dl.TRP13
                    else (linef_table.OURS_THROUGH_A_THUNK, linef_table.thunk_symbol(name)))
        assert (entry.verdict, entry.symbol) == expected, f"{name}: {entry.verdict}, {entry.symbol}"


# ---- THE BIOS DOOR AS IT SHIPS: `src/desk/trp13.S`, its sixteen ROM bytes — A ROW OF THE TRANSCRIBED TABLE -----------
# By the rule (`include/transcribed.h`): its C twin measured over the bar — 1.355 / 1.253 / 1.053 at its three
# arrivals, +214 cycles a call (`aes_trp13`'s comment) — so it ships as the ROM's instructions, as trp14 does. Band 6
# wave 1a held it a kind of its own, linked and not entered; SINCE ITS FLIP (band 6 slice F1, N12) it is a row of the
# transcribed table, the Line-F table's two entries for it are the `.S` (native), and its C callers reach it on the
# shipped blob through glue.
TRP13_BYTES = 16
TRP13_REGION = transcription.pinned_region(addrs.AES_ROM_TRP13, addrs.AES_ROM_TRP13 + TRP13_BYTES, dl.TRP13)
# What a transcription case stages that the C's did not (trp14's arrangement): the BIOS's register save moved into the
# run's stack band — its saved return differs between the two shores' callers, and neither compares the band there.
SAVE_IN_THE_BAND = "THE BIOS'S REGISTER SAVE IN THE STACK BAND"


def test_the_door_s_transcription_is_the_rom_s_bytes_exactly_on_both_blobs():
    transcription.assert_transcribed(TRP13_REGION, relocated={})
    transcription.assert_the_shipped_blob_holds_the_same(TRP13_REGION)


def test_the_door_s_region_is_the_door_alone_and_trp14_follows_it():
    assert bytes(BASE_IMAGE[TRP13_REGION.hi - len(RTS):TRP13_REGION.hi]) == RTS
    assert bytes(BASE_IMAGE[TRP13_REGION.lo - len(RTS):TRP13_REGION.lo]) == RTS, "the routine before it ends in its own `rts`"
    assert TRP13_REGION.hi == addrs.AES_ROM_TRP14


def test_the_door_is_a_row_of_the_transcribed_table_and_its_source_a_transcription():
    """`atari/target.mk`'s TRANSCRIBED_SOURCES as make expands it names `src/desk/trp13.S` (by name: its file stays in the
    desk's directory), its one `.globl` the door's entry — A ROW of the transcribed table, its Tier 3 rows registered,
    and no other kind lists it."""
    names = ("TRANSCRIBED_SOURCES", "SWITCH_SOURCES", "TRAPDOOR_SOURCES", "GEMSTART_SOURCES", "LINEFTABLE_SOURCES", "ALCYON_ENTRY_SOURCES")
    lists = {name: transcription.make_variable(RECREATE, name) for name in names}
    ours = [source for source in lists["TRANSCRIBED_SOURCES"] if Path(source).name == "trp13.S"]
    assert [Path(source).resolve() for source in ours] == [(RECREATE / "src" / "desk" / "trp13.S").resolve()]
    assert not any(set(ours) & set(lists[other]) for other in names[1:])
    assert transcription.globl_entries(ours) == {TRP13_ENTRY} and transcription.TRANSCRIBED[TRP13_ENTRY] == ("d2", "a2")
    assert {row[0] for row in transcription.TRANSCRIPTIONS if row[1] == TRP13_ENTRY} == set(DOOR_ARRIVALS)


# THE DOOR'S PARKED RETURN UNDER A C CALLER ON THE SHIPPED BLOB — trp14's class (ruling R9's kind, the user's: declared):
# the glue's `jsr` into the `.S` makes the `.S` park THE GLUE'S return in AES_BIOS_RETURN, where the C twin parks the
# site its caller hands it. DECLARED, and PINNED as R9's is: the only instructions of the ROM that name the longword are
# trp13's own two — its park and, after its trap, its read of what it parked — so nothing reads what a call left there
# once the call has returned. (The scan's reach as R9's: absolute-long operands of the GEM text.)
BIOS_DOOR_PARKS_AT, BIOS_DOOR_READS_BACK_AT = addrs.AES_ROM_TRP13, addrs.AES_ROM_TRP13 + 8
MOVE_L_POP_TO_ABSOLUTE, MOVE_L_ABSOLUTE_PUSH, TRAP_13 = 0x23DF, 0x2F39, 0x4E4D


def test_the_bios_door_s_parked_return_is_named_by_trp13_alone():
    named = [at - WORD_BYTES for at in range(0, len(BASE_IMAGE) - LONG_BYTES + 1, WORD_BYTES)
             if case.long_in(BASE_IMAGE, at) == aes.AES_BIOS_RETURN and aes.AES_TEXT[0] <= at < aes.AES_TEXT[1]]
    assert named == [BIOS_DOOR_PARKS_AT, BIOS_DOOR_READS_BACK_AT]
    assert [case.word_in(BASE_IMAGE, at) for at in named] == [MOVE_L_POP_TO_ABSOLUTE, MOVE_L_ABSOLUTE_PUSH]
    assert case.word_in(BASE_IMAGE, BIOS_DOOR_READS_BACK_AT - WORD_BYTES) == TRAP_13


def door_case(at):
    """`(the staged caller, the machine)` of the door entered over the frame its arrival's caller pushed: the
    arrival's megabyte less the blob's span, the frame at the frame caller's place, the BIOS's save in the band."""
    arrived = dl.arrival(at)
    function, *words = arrived.arguments
    frame = vdi.pack_words(function, *words)
    frame += bytes(-len(frame) % LONG_BYTES)
    caller = frames.frame_caller(len(frame) // LONG_BYTES)
    machine = merge_pokes(dl.arrival_s_machine(arrived.boot.ram), aes_event.savptr_in_the_band(), {frames.FRAME_ARGUMENTS_AT: frame})
    return caller, machine


@pytest.mark.parametrize("label", DOOR_ARRIVALS, ids=[f"{label} [{SAVE_IN_THE_BAND}]" for label in DOOR_ARRIVALS])
def test_the_door_s_transcription_behaves_as_the_rom_at_the_chains_arrivals_and_costs_what_it_does(label):
    """THE `.S` AGAINST THE ROM'S DOOR through the transcription relation (the whole register file, the megabyte, the
    chip traffic), over the frame each arrival's caller pushed and THE MACHINE'S OWN BIOS — Drvmap, the forced media
    change through the ROM's floppy driver, Bconout to the console. And what the C twin could not: THE SAME CYCLES
    (the re-probe the rule expects: 1.00 at each, where the twin read 1.355 / 1.253 / 1.053). Its rows are these cases."""
    caller, machine = door_case(DOOR_ARRIVALS[label])
    measured = transcription.run_transcription(dl.TRP13, machine, caller=caller)
    assert measured.recreate_net == measured.original_net > 0


# ---- band 6 slice F1: THE UNIT'S ROWS ------------------------------------------------------------------------------------------
# THE FLIPPED LEAF'S ROW (the orchestrator's provisional ruling R6: the ROM's arrival machine, taken over at the arrival):
# EACH BLOB CASE OF AN ARRIVAL, REGISTERED. Its machine is the arrival's megabyte whole but the harness's window
# (`aes_deskleaves.row_pokes`; a LABELLED STAGING where the routine traps GEMDOS — the unit's recording trap scripted with
# the ROM's run in place's answers, `SCRIPTED`, said in the row's name — and the frame staged on the harness's stack;
# unit O's Tier 1 convention, in place of the blob cases' trap that keeps its last call); Tier 3 lays the blob and maps
# the registry's code slots at the entry (the table at `$cc24` and the door's: THE TAKEOVER), and prices the routine on
# its own cycles against the ROM's, the 1.10 bar. Argument classes (the leaf machine's, the fifth arrival's lists made
# other) stay Tier 1's.
#   * PRICED: every routine whose core takes no host argument, at each arrival its blob cases hold.
#   * VERIFIED AND UNPRICED (`aes_gemdosif.register_unpriced`): the six glue entries that take their caller's return site
#     — a host argument no frame carries, band 5's glue's class (`test_tier3.UNPRICED_AT_A_ROM_ENTRY`) — at the same
#     arrivals: the cases their thunks are entered by through the table (`test_aes_lineftable.py`, N15).
#   * trp13: its `.S` rows at its three arrivals (the transcription relation, the machine's own BIOS: `DOOR_ARRIVALS`),
#     and its C twin verified and unpriced at Drvmap's (trp14's arrangement: the case the table's native entry is
#     entered by).
#   * gsx_hardcopy: NO ARRIVAL (its printer's Scrdmp) — verified and unpriced over its argument class, the leaf machine
#     with Scrdmp's staged routine (the case its thunk is entered by), and priced nowhere.
HOSTED = set(dl.PARKS_ITS_CALLER_S_RETURN) - {dl.TRP13}
AT_AN_ARRIVAL = [label for label in ON_THE_BLOBS if on_the_blobs()[label].get("ram") is not None and not label.startswith("app_free (")
                 and on_the_blobs()[label]["name"] != dl.TRP13]


def row_label(label):
    """A row's label: the blob case's less its routine, the scripted trap said where it is staged."""
    said = f"{label} [{SCRIPTED}]" if on_the_blobs()[label].get("answers") else label
    return said.split(": ", 1)[1]


def _registered(label):
    spec = on_the_blobs()[label]
    name = spec["name"]
    pokes = dl.row_pokes(name, spec["arguments"], ram=spec.get("ram"), layers=spec.get("layers", ()), answers=spec.get("answers"),
                         settles_the_mask=spec.get("settles_the_mask", False))
    row_name = f"{routines.core_symbol(name)}, {row_label(label)}"
    answered = vdi.ALCYON[name].restype is not None
    return aes.ROWS.register(row_name, getattr(addrs, name), pokes, priced=name not in HOSTED, answered=answered)


ROWS = {label: _registered(label) for label in AT_AN_ARRIVAL}
DRVMAP_ARRIVAL = "Drvmap: a drive opened, its letter checked against the map"
for _label, _at in DOOR_ARRIVALS.items():
    _caller, _machine = door_case(_at)
    transcription.register_transcription(dl.TRP13, _label, _machine, caller=_caller)
_arrived = dl.arrival(DOOR_ARRIVALS[DRVMAP_ARRIVAL])
ROWS["trp13 (the C twin)"] = aes.ROWS.register(
    f"aes_trp13, {DRVMAP_ARRIVAL} (the C twin: a host argument, and the `.S` ships)", addrs.AES_ROM_TRP13,
    aes.staged(dl.TRP13, vdi.as_signed(dl.TRP13, _arrived.arguments),
               merge_pokes(dl.arrival_s_machine(_arrived.boot.ram), aes_event.savptr_in_the_band())), priced=False)
ROWS["gsx_hardcopy"] = aes.ROWS.register(
    "aes_gsx_hardcopy, ARGUMENT CLASS (no arrival: Scrdmp's staged routine, no dump pending)", addrs.AES_ROM_GSX_HARDCOPY,
    aes.staged(dl.GSX_HARDCOPY, (), aes.leaf_machine(onto=merge_pokes(vdi_escape.hardcopy_pokes(0),
                                                                      aes.stale_fields("GSX_SUBFUNCTION", "GSX_OPCODE")))),
    priced=False, answered=False)
PRICED_ROWS, UNPRICED_ROWS = 16, 11     # priced at arrivals; verified and unpriced (the six hosted's nine arrivals, trp13's twin, the hardcopy)


def test_the_unit_s_rows_are_its_blob_cases_at_arrivals_each_routine_one_at_least():
    """EVERY ROUTINE OF THE UNIT HAS A ROW: a priced one at an arrival (the eleven without a host argument but the
    hardcopy), a verified unpriced one (the six hosted glue entries, at their arrivals; trp13's twin; the hardcopy's
    class) — and trp13 its `.S` rows besides. The row names say every staging."""
    rows = {routine for routine in dl.UNIT_O for row in ROWS.values() if row[1] == getattr(addrs, routine)}
    assert rows == set(dl.UNIT_O)
    priced = [row for row in ROWS.values() if row in aes.ROWS.cases]
    assert (len(priced), len(ROWS) - len(priced)) == (PRICED_ROWS, UNPRICED_ROWS)
    assert {row[1] for row in priced} == {getattr(addrs, name) for name in set(dl.UNIT_O) - HOSTED - {dl.TRP13, dl.GSX_HARDCOPY}}
    assert all(f"[{SCRIPTED}]" in row[0] for row in ROWS.values() if row[0].startswith("aes_dos_"))
