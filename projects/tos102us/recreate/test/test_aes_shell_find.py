r"""The shell's FILE FINDING — sh_name ($feae04), sh_envrn ($feae36), sh_path ($feaf1e), sh_find ($feafbe):
`src/aes/shell_find.c` — and the GEMDOS glue under it: dos_sfirst ($fe3a1c), dos_open ($fe3a52), dos_read ($fe3a78),
dos_lseek ($fe3a9a), dos_sdta ($fe3c06), dos_close ($fe3c0a): `src/aes/gemdosif.c`.

    sh_name(p):         past p's last `\` or `:`, scanning back from its NUL — or p itself
    sh_envrn(&a, s):    copy 50 bytes of the environment to $9b70, byte 5 := `;`; scan for a byte equal to s[0] whose
                        next strlen(s)-1 bytes equal s+1; *a = past them, or 0. D0.w = the length, or (ext.w) s[0]
    sh_path(n, d, nm):  e = sh_envrn("PATH="); skip n `;`-elements; copy one to d, `\` unless it ends `\` or `:`, nm
    sh_find(spec, r):   Fsetdta($b89a); path := spec; Fsfirst(path, 5) — not there (AES_DOS_AX 2, 18, 3): first `\` +
                        path, then sh_path(1..) with spec's name part — until found, another error, or PATH runs out;
                        found: spec := path, r(path) if r; answer !AES_DOS_ERR, read after r

`test/aes_shell.py` says how each `trap #1` is answered: REAL GEMDOS over the staged disk for the paths a disk can
take, the SCRIPTED trap for the arms only a GEMDOS answer no disk gives reaches, and for every Tier 3 row.
"""
import struct

import pytest

from harness import BASE_IMAGE, addrs, emu

import aes
import aes_shell as sh
import case
import fs_dir
import gemdos_fs as fs
import gemdos_process as process
import vdi
import vdi_helpers
from case import merge_pokes
from opcodes import DROP_STACK_LONG

SHELL = sh.SHELL
SEPARATOR, DRIVE_SEPARATOR, PATH_SEPARATOR = SHELL["SH_DIRECTORY_SEPARATOR"], SHELL["SH_DRIVE_SEPARATOR"], SHELL["SH_PATH_SEPARATOR"]
SCRATCH, SCRATCH_BYTES = aes.AES_SH_SCRATCH, aes.AES_SH_SCRATCH_BYTES
PATH_BUFFER = aes.AES_SH_PATH_BUFFER
DTA = aes.AES_RS_STRING                     # sh_find's DTA is rs_str's buffer
DTA_BYTES = 44                              # what Fsfirst fills: the search's 21 bytes, attribute, time, date, length, name
aes.declare_case_field(DTA, DTA_BYTES, "sh_find's DTA, rs_str's buffer")
FIND_ATTRIBUTES = SHELL["SH_FIND_ATTRIBUTES"]
NO_ROUTINE = SHELL["SH_FIND_NO_ROUTINE"]
# GEMDOS's errors as the signed longs D0 carries: the headers' values.
EFILNF, ENMFIL, EPTHNF, EACCDN, EIHNDL, ERANGE = (aes.signed(code, 32) for code in (
    process.GEMDOS_EFILNF, fs.GEMDOS_ENMFIL, fs.GEMDOS_EPTHNF, fs.GEMDOS_EACCDN, addrs.GEMDOS_EIHNDL, fs.GEMDOS_ERANGE))
GEMDOS_OK = 0
# The glue's AES_DOS_AX for an Fsfirst or Fopen that found nothing (`aes/gemdosif.h`), and the word sh_find retries on.
AX_NO_MORE_FILES = sh.GEMDOSIF["DOS_AX_NO_MORE_FILES"]
AX_FILE_NOT_FOUND = sh.GEMDOSIF["DOS_AX_FILE_NOT_FOUND"]
AX_PATH_NOT_FOUND = sh.GEMDOSIF["DOS_AX_PATH_NOT_FOUND"]
# rs_readit's first read: the resource header.
HEADER_BYTES = aes.RSH_BYTES
# The AES's own environment, as the capture holds it, and PATH's element 1 of it.
AES_ENVIRONMENT = ("PATH=", "A:\\")
# The return address a dos_sdta/dos_close call parks: the run's own sentinel entered directly, the word after the call
# word in the Line-F caller.
LINE_F_RETURN_SITE = aes.LINE_F_CALLER_AT + len(DROP_STACK_LONG) + aes.WORD_BYTES
STALE_ANSWER = {sh.ANSWER_AT: struct.pack(">I", vdi.STALE_LONG)}
STALE_SCRATCH = {SCRATCH: bytes([vdi.FILL]) * SCRATCH_BYTES}
STALE_DTA = {DTA: bytes([vdi.FILL]) * DTA_BYTES}


def c_string(image, at, limit=sh.TEXT_BYTES):
    """The NUL-ended string at `at` in `image` (a run's `final`)."""
    return bytes(image[at:at + limit]).split(b"\0")[0].decode("latin-1")


# ---- sh_name ---------------------------------------------------------------------------------------------------------
# No GEMDOS: the leaf machine, POISONED.
def name_of(path, at=sh.SPEC_AT, *, through_line_f=False, before=b""):
    """sh_name over `path` at `at`, with `before` staged in the bytes just below it."""
    pokes = merge_pokes(sh.text(at, path), {at - len(before): before} if before else None)
    return aes.run_function(sh.SH_NAME, (at,), aes.leaf_machine(onto=pokes), through_line_f=through_line_f)


NAMES = {
    "a full path": ("A:\\FOLDER\\NAME.RSC", len("A:\\FOLDER\\")),
    "a drive and a name": ("B:NAME.RSC", len("B:")),
    "a name alone": ("NAME.RSC", 0),
    "empty": ("", 0),
    "a directory": ("A:\\FOLDER\\", len("A:\\FOLDER\\")),
    "the root": ("\\", 1),
    "the last separator wins": ("A:\\X:Y\\Z", len("A:\\X:Y\\")),
}


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("path, skip", NAMES.values(), ids=NAMES)
def test_sh_name_answers_past_the_last_separator(path, skip, through_line_f):
    assert name_of(path, through_line_f=through_line_f).long_answer() == sh.SPEC_AT + skip


def test_sh_name_stops_at_the_path_s_start_and_reads_nothing_below_it():
    """A separator just BELOW the path is not reached: the scan's `cmpa.l; bcs` ends it at the first byte."""
    at = sh.SPEC_AT + 2
    assert name_of("NAME", at, before=b"\\:").long_answer() == at


def test_sh_name_keeps_the_pointer_s_top_byte():
    """The bytes are read through the 24-bit bus; the answer is the register, top byte and all."""
    result = aes.run_function(sh.SH_NAME, (sh.SPEC_AT | aes.BUS_TAG,),
                              aes.leaf_machine(onto=sh.text(sh.SPEC_AT, "A:\\NAME")))
    assert result.long_answer() == (sh.SPEC_AT + len("A:\\")) | aes.BUS_TAG


# ---- sh_envrn --------------------------------------------------------------------------------------------------------
def envrn(search, strings=AES_ENVIRONMENT, *, answer=sh.ANSWER_AT, search_at=sh.SPEC_AT, through_line_f=False,
          pokes=None):
    """sh_envrn over `strings` as the environment, its answer stored at `answer` (staged STALE)."""
    staged = merge_pokes(sh.environment(*strings) if strings is not None else None, sh.text(sh.SPEC_AT, search),
                         STALE_ANSWER, STALE_SCRATCH, pokes)
    return sh.run_leaf(sh.SH_ENVRN, (answer, search_at), staged, through_line_f=through_line_f)


def copied(strings):
    """The environment as sh_envrn copies it: 50 bytes, byte 5 a `;`."""
    raw = bytearray(sh.text(sh.ENVIRONMENT_AT, b"".join(s.encode("latin-1") + b"\0" for s in strings))[sh.ENVIRONMENT_AT])
    raw = raw[:SCRATCH_BYTES]
    raw[SHELL["SH_ENVRN_PATCHED_BYTE"]] = PATH_SEPARATOR
    return bytes(raw)


def model_envrn(search, strings):
    """`(found, word)`: the scan as the ROM makes it, over the copy (a short name: the frame's buffers apart)."""
    env, length = copied(strings), len(search) - 1
    cursor, skipping = 0, False
    while True:
        character = env[cursor] if cursor < len(env) else BASE_IMAGE[SCRATCH + cursor]
        cursor += 1
        if skipping and character == 0:
            skipping, character = False, 0xFF
            continue
        word = aes.signed(ord(search[0]), 8)
        if ord(search[0]) != character:
            skipping = True
        else:
            rest = bytes(env[cursor:cursor + length]) if cursor + length <= len(env) else None
            if rest == search[1:].encode("latin-1"):
                return SCRATCH + cursor + length, length
            word = 0
        if character == 0:
            return 0, word


ENVRN_CASES = {
    "PATH= in the AES's own": ("PATH=", AES_ENVIRONMENT),
    "not there": ("HOME=", AES_ENVIRONMENT),
    "the second string": ("TERM=", ("PATH=", "A:\\", "TERM=VT52")),
    "a first byte matches, the rest not": ("PATX=", AES_ENVIRONMENT),
    "inside a value: not anchored": ("BIN", ("PATH=", "A:\\BIN")),
    "the patch joins the first two strings": ("PATH=", ("AB=CD", "PATH=X:\\")),
    "an empty environment": ("PATH=", ("",)),
    "a name of one byte": ("A", ("PATH=", "A:\\")),
    "a first byte above $7f, sign-extended into the word": ("\xe9T=", ("PATH=", "A:\\")),
}


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("search, strings", ENVRN_CASES.values(), ids=ENVRN_CASES)
def test_sh_envrn_finds_a_value_where_its_scan_does(search, strings, through_line_f):
    result = envrn(search, strings, through_line_f=through_line_f)
    found, word = model_envrn(search, strings)
    assert result.long(sh.ANSWER_AT) == found
    assert result.answer() == word
    assert result.after(SCRATCH, SCRATCH_BYTES) == copied(strings)


def test_sh_envrn_s_copy_runs_past_the_environment_s_end():
    """Fifty bytes whatever the environment's length: a short one is followed by what the band holds after it."""
    result = envrn("ZZZ=", ("A=1",))
    assert result.after(SCRATCH, SCRATCH_BYTES) == copied(("A=1",))
    assert result.long(sh.ANSWER_AT) == 0


# A name longer than the frame's first buffer runs into the compare buffer and the locals after it, which the ROM
# then reads back — every one of these is a frame overrun the C reproduces byte for byte (`aes/shell.h`).
LONG_NAMES = {
    "16, into the compare buffer": "ABCDEFGHIJKLMNO=",
    "20, its terminator in the character slot": "ABCDEFGHIJKLMNOPQRS=",
    "22, the copy over the length": "ABCDEFGHIJKLMNOPQRSTU=",
    "30": "ABCDEFGHIJKLMNOPQRSTUVWXYZ012=",
    "31, the longest: its terminator on the saved A6's top byte": "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123=",
}
LONGEST_SEARCH = LONG_NAMES["31, the longest: its terminator on the saved A6's top byte"]
PAST_THE_LONGEST_SEARCH = LONGEST_SEARCH[:-1] + "4="


@pytest.mark.parametrize("found", (True, False), ids=("there", "not there"))
@pytest.mark.parametrize("search", LONG_NAMES.values(), ids=LONG_NAMES)
def test_sh_envrn_over_a_long_name_overruns_its_frame_as_the_rom_does(search, found):
    strings = ("PATH=", search + "VALUE") if found else ("PATH=", "A:\\", search[0] + "X")
    envrn(search, strings)


@pytest.mark.parametrize("pointer", ("answer", "search_at"))
def test_sh_envrn_s_pointers_are_on_the_24_bit_bus(pointer):
    default = {"answer": sh.ANSWER_AT, "search_at": sh.SPEC_AT}[pointer]
    result = envrn("PATH=", **{pointer: default | aes.BUS_TAG})
    assert result.long(sh.ANSWER_AT) == SCRATCH + len("PATH=")


# A name of 256 bytes and more: lstcpy's count is a byte, and wraps to a length the frame would hold.
WRAPPING_NAME = "N" * 260 + "="


@pytest.mark.parametrize("search, halt", ((PAST_THE_LONGEST_SEARCH, "a name"), ("", "a compare"),
                                          (WRAPPING_NAME, "a name")),
                         ids=("32 bytes", "empty", "261 bytes, its count wrapped"))
def test_sh_envrn_halts_where_the_rom_overwrites_its_own_frame(search, halt):
    """Past its 46 bytes and the saved A6's top byte the ROM writes over the rest of its saved A6, and runs on — a name
    of 32 bytes or more, or an empty one (its length less one, -1, copies 65,535 bytes at the first NUL): the C halts by
    name, conservatively (`aes/shell.h`) — a long name on the name's own bound, before any compare."""
    pokes = merge_pokes(sh.environment(*AES_ENVIRONMENT), sh.text(aes.BLOCKS_AT, search, aes.BLOCKS_BYTES))
    returncode, stderr, _image = vdi_helpers.refusal_over(
        "aes_sh_envrn", pokes, arguments=(("ctypes.c_uint32", hex(sh.ANSWER_AT)), ("ctypes.c_uint32", hex(aes.BLOCKS_AT))),
        read_back=False)
    assert returncode != 0 and f"sh_envrn: {halt}" in stderr and "frame" in stderr


@pytest.mark.parametrize("search", (LONGEST_SEARCH, "PATH="), ids=("31 bytes", "PATH="))
def test_sh_envrn_halts_on_no_name_its_frame_holds(search):
    """...and the other side of that bound, in a child too, so a bound one byte short is a failed assertion here
    rather than a halt that ends the worker — its slot staged FILLed, so a saved-A6 byte the C failed to stage halts."""
    pokes = merge_pokes(sh.DIRTY_FRAMES, sh.environment("PATH=", search + "X"), sh.text(sh.SPEC_AT, search))
    returncode, stderr, _image = vdi_helpers.refusal_over(
        "aes_sh_envrn", pokes, arguments=(("ctypes.c_uint32", hex(sh.ANSWER_AT)), ("ctypes.c_uint32", hex(sh.SPEC_AT))),
        read_back=False)
    assert returncode == 0, stderr


# A COMPARE OVER A REWRITTEN LENGTH: a 23-byte name's first compare copies 22 bytes of the environment over the frame up
# to its length word, which the environment rewrites to 31 — so the next compare copies 31 bytes, its last onto the
# saved A6's top byte. The copy as laid out (scratch offsets): a first match at 0, a `\0` at 2 to end the skip, a second
# match at 3; the new length at 21; a cursor at 30 that the second copy writes, pointing at two NULs which end the scan;
# and at 34 the byte the second copy lands on the saved A6's top byte.
REWRITTEN_LENGTH_NAME = "Z" + "abcdefghijklmnopqrstu" + "="
REWRITTEN_LENGTH_FIRST, REWRITTEN_LENGTH_SKIP_END, REWRITTEN_LENGTH_SECOND = 0, 2, 3
REWRITTEN_LENGTH_AT, REWRITTEN_LENGTH = 21, 31
REWRITTEN_CURSOR_AT, REWRITTEN_CURSOR_TO = 30, 21
ONTO_THE_SAVED_A6_AT = 34
REWRITTEN_LENGTH_FILL = b"y"


def rewritten_length_environment(onto_the_saved_a6):
    raw = bytearray(REWRITTEN_LENGTH_FILL * SCRATCH_BYTES)
    for at, byte in ((REWRITTEN_LENGTH_FIRST, ord("Z")), (REWRITTEN_LENGTH_SKIP_END, 0), (REWRITTEN_LENGTH_SECOND, ord("Z")),
                     (ONTO_THE_SAVED_A6_AT, onto_the_saved_a6)):
        raw[at] = byte
    raw[REWRITTEN_LENGTH_AT:REWRITTEN_LENGTH_AT + aes.WORD_BYTES] = struct.pack(">H", REWRITTEN_LENGTH)
    raw[REWRITTEN_CURSOR_AT:REWRITTEN_CURSOR_AT + aes.LONG_BYTES] = struct.pack(">I", SCRATCH + REWRITTEN_CURSOR_TO)
    return (bytes(raw).decode("latin-1"),)


def test_sh_envrn_s_compare_over_a_rewritten_length_serves_a_0_on_the_saved_a6():
    result = envrn(REWRITTEN_LENGTH_NAME, rewritten_length_environment(0))
    assert result.long(sh.ANSWER_AT) == 0


def test_sh_envrn_halts_on_a_compare_landing_a_byte_on_the_saved_a6():
    strings = rewritten_length_environment(REWRITTEN_LENGTH_FILL[0])
    pokes = merge_pokes(sh.environment(*strings), sh.text(sh.SPEC_AT, REWRITTEN_LENGTH_NAME))
    returncode, stderr, _image = vdi_helpers.refusal_over(
        "aes_sh_envrn", pokes, arguments=(("ctypes.c_uint32", hex(sh.ANSWER_AT)), ("ctypes.c_uint32", hex(sh.SPEC_AT))),
        read_back=False)
    assert returncode != 0 and "sh_envrn: a compare" in stderr


# ---- sh_path ---------------------------------------------------------------------------------------------------------
# D6: sh_path tests its CALLER's D6 when an element is empty (`shell_find.c`). Every application path enters it with
# the dispatcher's ($fe5da8 moveq #1,d6 — rsrc_load to rs_load, rs_readit and sh_find; shel_find to sh_find; none sets
# D6 before the call), so every case enters with that 1. sh_main's own sh_find ($feb27e) inherits a D6 no C can see:
# the one divergence, pinned on the ROM's side below.
D6_FROM_THE_DISPATCHER = {"d6": 1}


# A negative element counts its word down through 65,535 skips, each a read of the NUL it stops at.
LONG_WAY_ROUND = 1_000_000


def path(which, strings=AES_ENVIRONMENT, name="APP.RSC", *, through_line_f=False, path_buffer=PATH_BUFFER,
         name_at=sh.SPEC_AT):
    staged = merge_pokes(sh.environment(*strings), sh.text(sh.SPEC_AT, name), sh.working_path(), STALE_SCRATCH,
                         {DTA: bytes([vdi.FILL]) * DTA_BYTES})
    return sh.run_leaf(sh.SH_PATH, (which, path_buffer, name_at), staged, regs=D6_FROM_THE_DISPATCHER,
                       through_line_f=through_line_f, max_insns=LONG_WAY_ROUND)


PATHS = {
    "element 1 of the AES's own": (1, AES_ENVIRONMENT, "A:\\APP.RSC", 2),
    "past the last": (2, AES_ENVIRONMENT, None, 0),
    "no PATH at all": (1, ("HOME=", "A:\\"), None, 0),
    "an element without its `\\`": (1, ("PATH=", "A:\\SUBDIR"), "A:\\SUBDIR\\APP.RSC", 2),
    "an element ending in `:`": (1, ("PATH=", "B:"), "B:APP.RSC", 2),
    "the second of two": (2, ("PATH=", "A:\\X;B:\\Y\\"), "B:\\Y\\APP.RSC", 3),
    "element 0: the empty one the patch makes": (0, AES_ENVIRONMENT, "\\APP.RSC", 1),
    "an empty element between two": (2, ("PATH=", "A:\\;;B:\\"), "\\APP.RSC", 3),
    "a negative element: the word counts down the long way": (-1, AES_ENVIRONMENT, None, 0),
}


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("which, strings, built, answer", PATHS.values(), ids=PATHS)
def test_sh_path_builds_an_element_and_the_name(which, strings, built, answer, through_line_f):
    result = path(which, strings, through_line_f=through_line_f)
    assert result.answer() == answer
    if built is not None:
        assert c_string(result.final, PATH_BUFFER) == built
    else:
        assert result.after(PATH_BUFFER, 2) == b"\0" + bytes([vdi.FILL]), "nothing copied"
    assert c_string(result.final, DTA) == "PATH=", "rs_str copies the PATH string over sh_find's DTA"


def test_sh_path_s_pointers_are_on_the_24_bit_bus():
    result = path(1, path_buffer=PATH_BUFFER | aes.BUS_TAG, name_at=sh.SPEC_AT | aes.BUS_TAG)
    assert c_string(result.final, PATH_BUFFER) == "A:\\APP.RSC"


# THE ROM ALONE, entered with a frame pointer of the kind the AES's own stacks hold (UDA0's, below its top AES_UDA1):
# what no differential can show, because the C cannot take or hand back its caller's registers.
CALLER_A6 = 0xA2F4
assert CALLER_A6 < aes.AES_UDA1
ADDRESS_BUS_MASK = 0x00FF_FFFF


def rom_alone(name, pokes, arguments, regs=None):
    """`name` on the ROM's side only, over the leaf machine and `pokes`: `(final image, registers)`."""
    image = vdi.make_image(merge_pokes(aes.leaf_machine(onto=pokes), vdi.alcyon_frame(name, *arguments)))
    final, _writes, registers = emu.run(image, getattr(addrs, name), {"a6": CALLER_A6, **(regs or {})},
                                        max_insns=LONG_WAY_ROUND)
    return final, registers


def test_sh_path_s_empty_element_takes_its_caller_s_d6_on_the_rom():
    """THE DIVERGENCE: entered with a `\\` in D6 — what sh_main's own sh_find ($feb27e) may inherit — the ROM adds no
    `\\` to an empty element; the C, which cannot see its caller's D6, takes the dispatcher's 1 and adds it (above)."""
    pokes = merge_pokes(sh.environment("PATH=", "A:\\;;B:\\"), sh.text(sh.SPEC_AT, "APP.RSC"), sh.working_path())
    final, registers = rom_alone(sh.SH_PATH, pokes, (2, PATH_BUFFER, sh.SPEC_AT), regs={"d6": SEPARATOR})
    assert c_string(final, PATH_BUFFER) == "APP.RSC"
    assert registers["d0"] & 0xFFFF == 3


# ---- the glue, over the scripted trap -------------------------------------------------------------------------------
def glue(name, arguments, answers, *, through_line_f=False, pokes=None):
    host = ()
    if name in (sh.DOS_SDTA, sh.DOS_CLOSE):
        host = (LINE_F_RETURN_SITE if through_line_f else emu.SENTINEL,)
    return sh.run_scripted(name, arguments, answers, pokes, through_line_f=through_line_f, host_arguments=host)


HANDLE = sh.SCRIPTED_HANDLE


def verdict(result):
    return [result.field("AES", name) for name in sh.DOS_FIELDS]


SFIRSTS = {    # (GEMDOS's answer, dos_sfirst's, AES_DOS_ERR, AES_DOS_AX)
    "found": (GEMDOS_OK, 1, 0, 0),
    "EFILNF": (EFILNF, 0, 1, AX_NO_MORE_FILES),
    "ENMFIL": (ENMFIL, 0, 1, AX_NO_MORE_FILES),
    "EPTHNF is left as it is": (EPTHNF, 0, 1, EPTHNF & 0xFFFF),
    "a positive long, its word 0: found": (0x0001_0000, 1, 0, 0),
    "a negative long, its word 0: found, and failed": (-0x1_0000, 1, 1, 0),
    "a positive long whose word is ENMFIL": (ENMFIL & 0xFFFF, 0, 0, AX_NO_MORE_FILES),
    "3, as no disk answers": (-0x1_0000 | AX_PATH_NOT_FOUND, 0, 1, AX_PATH_NOT_FOUND),
}


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("gemdos, answer, failed, ax", SFIRSTS.values(), ids=SFIRSTS)
def test_dos_sfirst_words_its_verdict(gemdos, answer, failed, ax, through_line_f):
    result = glue(sh.DOS_SFIRST, (sh.SPEC_AT | aes.BUS_TAG, FIND_ATTRIBUTES), [gemdos], through_line_f=through_line_f)
    assert sh.calls(result.final) == [(addrs.GEMDOS_FSFIRST_FN, sh.frame(("l", sh.SPEC_AT | aes.BUS_TAG),
                                                                         ("w", FIND_ATTRIBUTES)))]
    assert result.answer() == answer
    assert verdict(result) == [vdi.STALE_LONG, addrs.AES_DOS_SFIRST_TRAP_RETURN, failed, ax]


OPENS = {    # (GEMDOS's answer, dos_open's, AES_DOS_ERR, AES_DOS_AX)
    "a handle": (6, 6, 0, 6),
    "EFILNF: 0, and 2": (EFILNF, 0, 1, AX_FILE_NOT_FOUND),
    "EACCDN: 0, the word left": (EACCDN, 0, 1, EACCDN & 0xFFFF),
    "a positive long whose word is EFILNF": (EFILNF & 0xFFFF, EFILNF & 0xFFFF, 0, AX_FILE_NOT_FOUND),
}


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("gemdos, answer, failed, ax", OPENS.values(), ids=OPENS)
def test_dos_open_answers_the_handle_or_0(gemdos, answer, failed, ax, through_line_f):
    result = glue(sh.DOS_OPEN, (sh.SPEC_AT, 2), [gemdos], through_line_f=through_line_f)
    assert sh.calls(result.final) == [(addrs.GEMDOS_FOPEN_FN, sh.frame(("l", sh.SPEC_AT), ("w", 2)))]
    assert result.long_answer() == answer & 0xFFFF_FFFF
    assert verdict(result) == [vdi.STALE_LONG, addrs.AES_DOS_OPEN_TRAP_RETURN, failed, ax]


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("count", (HEADER_BYTES, 0x8000, 0xFFFF), ids=("36", "$8000", "$ffff"))
def test_dos_read_widens_its_count_unsigned(count, through_line_f):
    """The count a WORD zero-extended ($fe3a82 moveq #0; move.w): $8000 asks for 32,768, not -32,768."""
    result = glue(sh.DOS_READ, (HANDLE, count, sh.SPEC_AT), [count], through_line_f=through_line_f)
    assert sh.calls(result.final) == [(addrs.GEMDOS_FREAD_FN, sh.frame(("w", HANDLE), ("l", count), ("l", sh.SPEC_AT)))]
    assert result.long_answer() == count
    assert verdict(result) == [vdi.STALE_LONG, addrs.AES_DOS_READ_TRAP_RETURN, 0, count]


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("answer", (0, ERANGE), ids=("at 0", "ERANGE"))
def test_dos_lseek_moves_the_handle_and_mode_under_the_offset(answer, through_line_f):
    result = glue(sh.DOS_LSEEK, (HANDLE, 1, 0x1234_5678), [answer], through_line_f=through_line_f)
    assert sh.calls(result.final) == [(addrs.GEMDOS_FSEEK_FN, sh.frame(("l", 0x1234_5678), ("w", HANDLE), ("w", 1)))]
    assert result.long_answer() == answer & 0xFFFF_FFFF
    assert verdict(result) == [vdi.STALE_LONG, addrs.AES_DOS_LSEEK_TRAP_RETURN, int(answer < 0), answer & 0xFFFF]


# dos_open's name reaches the reconstructed dispatcher's device-name test (`src/gemdos/dispatch.c` device_named,
# through gemdos_strneq) before the scripted handler, so its case also holds that test reading through the bus.
@pytest.mark.parametrize("name, arguments, answer, function, recorded", (
    (sh.DOS_READ, (HANDLE, HEADER_BYTES, sh.SPEC_AT | aes.BUS_TAG), HEADER_BYTES, addrs.GEMDOS_FREAD_FN,
     (("w", HANDLE), ("l", HEADER_BYTES), ("l", sh.SPEC_AT | aes.BUS_TAG))),
    (sh.DOS_OPEN, (sh.SPEC_AT | aes.BUS_TAG, 2), HANDLE, addrs.GEMDOS_FOPEN_FN,
     (("l", sh.SPEC_AT | aes.BUS_TAG), ("w", 2)))), ids=("dos_read's buffer", "dos_open's name"))
def test_the_glue_traps_with_a_pointer_as_its_caller_pushed_it(name, arguments, answer, function, recorded):
    """The glue dereferences nothing: GEMDOS is handed the longword, top byte and all."""
    result = glue(name, arguments, [answer])
    assert sh.calls(result.final) == [(function, sh.frame(*recorded))]
    assert result.long_answer() == answer


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("name, function, argument, kind", (
    (sh.DOS_SDTA, addrs.GEMDOS_FSETDTA_FN, DTA | aes.BUS_TAG, "l"),
    (sh.DOS_CLOSE, addrs.GEMDOS_FCLOSE_FN, 6, "w")), ids=("dos_sdta", "dos_close"))
@pytest.mark.parametrize("answer", (GEMDOS_OK, EIHNDL), ids=("done", "EIHNDL"))
def test_the_glue_through_fe3c28_parks_both_returns(name, function, argument, kind, answer, through_line_f):
    """The caller's return address in AES_DOS_RETURN — the run's sentinel, or the word after the Line-F caller's call
    word — and `__DOS`'s own in AES_TRAP1_RETURN; Fclose's frame is ONE word (the ledger records it alone)."""
    result = glue(name, (argument,), [answer], through_line_f=through_line_f)
    assert sh.calls(result.final) == [(function, sh.frame((kind, argument)))]
    assert result.long_answer() == answer & 0xFFFF_FFFF
    return_site = LINE_F_RETURN_SITE if through_line_f else emu.SENTINEL
    assert verdict(result) == [return_site, addrs.AES_DOS_TRAP_RETURN, int(answer < 0), answer & 0xFFFF]


def test_the_scripted_handler_records_what_the_rom_s_glue_traps_with():
    """The handler under the ROM's own glue, Fclose's one word: what it records and answers is the handler's, not a
    claim about the C."""
    pokes = merge_pokes(sh.scripted_pokes([5]), vdi.alcyon_frame(sh.DOS_CLOSE, 9))
    final, _writes, regs = emu.run(vdi.make_image(pokes), addrs.AES_ROM_DOS_CLOSE, {})
    assert sh.calls(final) == [(addrs.GEMDOS_FCLOSE_FN, sh.frame(("w", 9)))]
    assert regs["d0"] == 5


# ---- sh_find over REAL GEMDOS -----------------------------------------------------------------------------------------
def find(name, strings=None, *, routine=None, through_line_f=False, pokes=None, spec_at=sh.SPEC_AT):
    """sh_find over the staged disk, `name` the spec, `strings` the environment (the AES's own if None)."""
    staged = merge_pokes(sh.spec(name), sh.working_path(), STALE_DTA, STALE_SCRATCH,
                         sh.environment(*strings) if strings else None,
                         sh.routine_pokes(routine) if routine else None, pokes)
    routines = sh.ROUTINES[routine] if routine else None
    at = sh.routine_at(routine) if routine else NO_ROUTINE
    return sh.run_real(sh.SH_FIND, (spec_at, at), staged, through_line_f=through_line_f, routines=routines,
                       regs=D6_FROM_THE_DISPATCHER)


# SUBDIR as the current directory: a DND for it as a search makes one, the process's p_curdir naming it.
SUBDIR_DND = fs_dir.dnd(fs_dir.SUBDIR_DND_AT, "SUBDIR", fs.SUBDIR_CLUSTER, fs.ROOT_DND_AT, fs.ROOT_OFD_AT,
                        fs.ROOT_INDEX["SUBDIR"])
IN_SUBDIR = merge_pokes(SUBDIR_DND, fs.current_directory_poke(sh.io.DRIVE, sh.CURRENT_NODE, fs_dir.SUBDIR_DND_AT))

FINDS = {    # (spec, environment, extra pokes, answer, the spec after)
    "as given": ("GEM.RSC", None, None, 1, "GEM.RSC"),
    "a path as given": ("A:\\SUBDIR\\APP.RSC", None, None, 1, "A:\\SUBDIR\\APP.RSC"),
    "at the root": ("GEM.RSC", None, IN_SUBDIR, 1, "\\GEM.RSC"),
    "down PATH": ("APP.RSC", ("PATH=", "A:\\SUBDIR"), None, 1, "A:\\SUBDIR\\APP.RSC"),
    "down PATH's second element": ("APP.RSC", ("PATH=", "A:\\;A:\\SUBDIR\\"), None, 1, "A:\\SUBDIR\\APP.RSC"),
    "nowhere: the root and all of PATH tried": ("NOPE.RSC", None, None, 0, "NOPE.RSC"),
    # This GEMDOS's Fsfirst answers EFILNF for a directory that is not there, a drive that is not, a file used as a
    # directory — so the walk goes on past such an element; only the scripted trap reaches an error that stops it.
    "past a PATH element naming no directory": ("APP.RSC", ("PATH=", "A:\\NODIR;A:\\SUBDIR"), None, 1,
                                                "A:\\SUBDIR\\APP.RSC"),
}


@pytest.mark.parametrize("spec, strings, pokes, answer, after", FINDS.values(), ids=FINDS)
def test_sh_find_looks_as_given_at_the_root_then_down_path(spec, strings, pokes, answer, after):
    result = find(spec, strings, pokes=pokes)
    assert result.answer() == answer
    assert c_string(result.final, sh.SPEC_AT) == after
    assert result.long(gemdos_basepage_dta()) == DTA


def gemdos_basepage_dta():
    return sh.gemdos.BASEPAGE + addrs.BASEPAGE_DTA


MOVED_PATH = sh.ENVIRONMENT_AT          # a case that keeps the AES's own environment leaves this band free


def test_sh_find_takes_the_name_part_from_the_path_buffer_s_address():
    """sh_name is handed $bb3e itself, not AES_SH_PATH_POINTER's value: with the pointer moved, the spec is copied where it
    points and the name part still read out of $bb3e — here the stale "OLD.RSC", which the PATH walk then tries."""
    moved = merge_pokes(aes.field_pokes("AES", SH_PATH_POINTER=MOVED_PATH), sh.text(MOVED_PATH, "", 0x40),
                        sh.working_path("OLD.RSC"))
    result = find_scripted("GEM.RSC", [EFILNF, EFILNF, EFILNF], pokes=moved)
    assert c_string(result.final, MOVED_PATH) == "A:\\OLD.RSC"


def test_sh_find_s_spec_is_on_the_24_bit_bus():
    """The spec, read and written back through the bus. Its ROUTINE has no such case, being unreachable with a top byte:
    every ROM caller passes 0 (rs_readit's `clr.l`) or sh_main's #$feaddc, and the C hands the hook the longword as
    given where the 68000's `jsr (a0)` would mask it."""
    result = find("GEM.RSC", pokes=IN_SUBDIR, spec_at=sh.SPEC_AT | aes.BUS_TAG)
    assert result.answer() == 1
    assert c_string(result.final, sh.SPEC_AT) == "\\GEM.RSC"


def test_sh_find_through_line_f():
    assert find("APP.RSC", ("PATH=", "A:\\SUBDIR"), through_line_f=True).answer() == 1


@pytest.mark.parametrize("routine, answer", (("logger", 1), ("setter", 0)), ids=("logger", "a routine setting DOS_ERR"))
def test_sh_find_hands_the_path_it_found_to_its_routine(routine, answer):
    """The routine is called over the working path's POINTER (AES_SH_PATH_POINTER's value); the answer is AES_DOS_ERR as the
    routine leaves it."""
    result = find("GEM.RSC", routine=routine)
    assert result.long(sh.LOG_AT) == case.long_in(BASE_IMAGE, aes.AES_SH_PATH_POINTER)
    assert result.answer() == answer


def test_sh_find_calls_no_routine_when_it_finds_nothing():
    result = find("NOPE.RSC", routine="logger")
    assert result.long(sh.LOG_AT) == vdi.STALE_LONG


# ---- sh_find over the SCRIPTED trap: the answers no disk gives --------------------------------------------------------
# Every script opens with Fsetdta's answer; each Fsfirst then answers the next. The AES's own environment: the walk is
# as given, the root, PATH element 1 ("A:\\" + the name part), and element 2 — none, which ends it.
SETDTA_ANSWER = GEMDOS_OK


def find_scripted(name, fsfirsts, strings=None, *, pokes=None):
    staged = merge_pokes(sh.spec(name), sh.working_path(), STALE_DTA, STALE_SCRATCH,
                         sh.environment(*strings) if strings else None, pokes)
    return sh.run_scripted(sh.SH_FIND, (sh.SPEC_AT, NO_ROUTINE), [SETDTA_ANSWER, *fsfirsts], staged,
                           regs=D6_FROM_THE_DISPATCHER)


def fsfirsts_tried(result):
    """The paths each Fsfirst was handed, by the working path's pointer: the ledger's frames."""
    return [frame for function, frame in sh.calls(result.final) if function == addrs.GEMDOS_FSFIRST_FN]


SCRIPTS = {    # (Fsfirst's answers, how many it made, sh_find's answer)
    "found as given": ([GEMDOS_OK], 1, 1),
    "not there anywhere": ([EFILNF, EFILNF, EFILNF], 3, 0),
    "ENMFIL is retried too": ([ENMFIL, ENMFIL, GEMDOS_OK], 3, 1),
    "AES_DOS_AX 3 is retried": ([-0x1_0000 | AX_PATH_NOT_FOUND, GEMDOS_OK], 2, 1),
    "an error not retried ends the search": ([EFILNF, EPTHNF], 2, 0),
    "a positive answer is no error: found": ([0x0000_0005], 1, 1),
    "a word of 0 in a negative long: failed, and not retried": ([-0x1_0000], 1, 0),
}


@pytest.mark.parametrize("fsfirsts, made, answer", SCRIPTS.values(), ids=SCRIPTS)
def test_sh_find_retries_only_on_not_there(fsfirsts, made, answer):
    result = find_scripted("GEM.RSC", fsfirsts)
    assert len(fsfirsts_tried(result)) == made
    assert result.answer() == answer


def test_sh_find_s_walk_tries_the_root_then_path_s_element_1():
    """Not there: the working path is as given, then `\\` + it, then "A:\\" + the name part — what it holds at the
    end is the last try."""
    result = find_scripted("FOLDER\\GEM.RSC", [EFILNF, EFILNF, EFILNF])
    assert c_string(result.final, PATH_BUFFER) == "A:\\GEM.RSC"
    assert c_string(result.final, SCRATCH) == "PATH=;A:\\", "the root's try was built in the scratch sh_envrn then copies over"
    assert c_string(result.final, sh.SPEC_AT) == "FOLDER\\GEM.RSC", "not found: the spec is not written"


# A NAME PART longer than sh_find's 14-byte buffer runs into its locals: the name pointer, then the first-try flag and
# the PATH index, which the walk rewrites under it — and sh_path then copies the name out of the frame as it stands.
NAME_PARTS = {
    "13 bytes, the buffer's last": "ABCDEFGH.RSCX",
    "17, over the name pointer": "ABCDEFGHIJKLM.RSC",
    "19, its NUL under the first-try flag": "ABCDEFGHIJKLMNO.RSC",
    "21, the frame's last byte": "ABCDEFGHIJKLMNOPQ.RSC",
    "22, the longest: its NUL on the saved A6's top byte": "ABCDEFGHIJKLMNOPQR.RSC",
}
assert [len(name) for name in NAME_PARTS.values()] == [13, 17, 19, 21, 22]
LONGEST_NAME_PART = NAME_PARTS["22, the longest: its NUL on the saved A6's top byte"]
PAST_THE_LONGEST_NAME_PART = "ABCDEFGHIJKLMNOPQRS.RSC"


@pytest.mark.parametrize("name_part", NAME_PARTS.values(), ids=NAME_PARTS)
def test_sh_find_s_name_part_overruns_its_frame_as_the_rom_s_does(name_part):
    result = find_scripted(name_part, [EFILNF, EFILNF, EFILNF])
    assert c_string(result.final, PATH_BUFFER).startswith("A:\\")


def test_sh_find_does_not_halt_on_the_longest_name_part_its_frame_holds():
    """22 bytes fill the frame, their NUL on the saved A6's top byte: no halt — in a child, so a bound one byte short
    fails here."""
    pokes = merge_pokes(sh.DIRTY_FRAMES, sh.spec(LONGEST_NAME_PART), sh.working_path(), sh.scripted_pokes([0]))
    returncode, stderr = sh.refusal_with_a_null_gemdos("aes_sh_find", pokes, (sh.SPEC_AT, NO_ROUTINE))
    assert returncode == 0, stderr


def test_sh_find_halts_on_a_name_part_past_its_frame():
    """23 bytes and more store a byte of the name on the saved A6's top byte and the NUL past it: the C halts by name
    — after Fsetdta, which the child answers through a hook that records nothing."""
    pokes = merge_pokes(sh.spec(PAST_THE_LONGEST_NAME_PART), sh.working_path(), sh.scripted_pokes([0]))
    returncode, stderr = sh.refusal_with_a_null_gemdos("aes_sh_find", pokes, (sh.SPEC_AT, NO_ROUTINE))
    assert returncode != 0 and "sh_find" in stderr and "frame" in stderr


# ---- the frames' bound, on the ROM's side ------------------------------------------------------------------------------
# The byte past each frame is the top byte of the caller's saved A6 (`aes/shell.h`). At the C's longest input the ROM
# stores a 0 there and hands its caller back the A6 it had; one byte longer it hands back an A6 whose top byte is the
# input's — the same frame on a 24-bit bus, but not the register its caller had, and further still the frame pointer
# itself. The C halts from there on (the child tests above).
def find_alone(name):
    pokes = merge_pokes(sh.OPEN_FOR_THE_HOST, sh.scripted_pokes([SETDTA_ANSWER, EFILNF, EFILNF, EFILNF]), sh.spec(name),
                        sh.working_path())
    return rom_alone(sh.SH_FIND, pokes, (sh.SPEC_AT, NO_ROUTINE))


def envrn_alone(search):
    pokes = merge_pokes(sh.environment("PATH=", search + "VALUE"), sh.text(sh.SPEC_AT, search), STALE_ANSWER)
    return rom_alone(sh.SH_ENVRN, pokes, (sh.ANSWER_AT, sh.SPEC_AT))


def compare_alone(onto_the_saved_a6):
    pokes = merge_pokes(sh.environment(*rewritten_length_environment(onto_the_saved_a6)),
                        sh.text(sh.SPEC_AT, REWRITTEN_LENGTH_NAME), STALE_ANSWER)
    return rom_alone(sh.SH_ENVRN, pokes, (sh.ANSWER_AT, sh.SPEC_AT))


@pytest.mark.parametrize("run, longest", ((find_alone, LONGEST_NAME_PART), (envrn_alone, LONGEST_SEARCH), (compare_alone, 0)),
                         ids=("sh_find", "sh_envrn", "sh_envrn's compare"))
def test_the_rom_returns_its_caller_s_a6_at_the_longest_input(run, longest):
    _final, registers = run(longest)
    assert registers["a6"] == CALLER_A6


@pytest.mark.parametrize("run, longer", ((find_alone, PAST_THE_LONGEST_NAME_PART), (envrn_alone, PAST_THE_LONGEST_SEARCH),
                                         (compare_alone, REWRITTEN_LENGTH_FILL[0])),
                         ids=("sh_find", "sh_envrn", "sh_envrn's compare"))
def test_the_rom_returns_another_a6_one_byte_past_it(run, longer):
    _final, registers = run(longer)
    assert registers["a6"] != CALLER_A6 and registers["a6"] & ADDRESS_BUS_MASK == CALLER_A6


# ---- the registry ---------------------------------------------------------------------------------------------------
# Each routine's WORST realistic row, over the scripted trap where it makes a call: sh_find's walk that finds nothing
# (as given, the root, PATH's element 1 — every retry the AES's own environment makes) and its find at the first try;
# sh_envrn's scan of the whole of the AES's environment for a name it has not, and of the name sh_path asks for;
# dos_sfirst's two arms, "found" the worse and the common one. sh_find's find with sh_main's kind of routine — a logger
# — is the one row that runs call_alcyon_pointer's TARGET branch, so the bench's second differential pins its asm.
# dos_sdta and dos_close take the return site no frame carries (a host argument), so their cases above are verified
# and they have no row — priced inside sh_find's and rs_readit's.
# sh_name's per-byte back-scan is slower in the C than in the ROM, which only its Line-F strlen offsets: a name alone of
# 100 bytes, unregistered, measured 1.11 in a review probe. Its rows stay the names GEMDOS has, 8.3 and a path.
def _scripted_row(label, name, arguments, answers, pokes=None):
    aes.register(label, name, arguments, sh.scripted_machine(answers, pokes), hook=sh.scripted_hook)


for _label, _path in (("a full path", "A:\\FOLDER\\NAME.RSC"), ("a name alone, scanned whole", "DESKTOP.RSC")):
    aes.register(_label, sh.SH_NAME, (sh.SPEC_AT,), sh.text(sh.SPEC_AT, _path))
for _search in ("PATH=", "HOME="):
    aes.register(f"{_search} in the AES's own environment", sh.SH_ENVRN, (sh.ANSWER_AT, sh.SPEC_AT),
                 merge_pokes(sh.environment(*AES_ENVIRONMENT), sh.text(sh.SPEC_AT, _search), STALE_ANSWER))
aes.register("element 1 of the AES's own", sh.SH_PATH, (1, PATH_BUFFER, sh.SPEC_AT),
             merge_pokes(sh.environment(*AES_ENVIRONMENT), sh.text(sh.SPEC_AT, "APP.RSC"), sh.working_path()))
_FIND_POKES = merge_pokes(sh.spec("GEM.RSC"), sh.working_path(), STALE_DTA, STALE_SCRATCH)
_scripted_row("not there: the root and PATH tried", sh.SH_FIND, (sh.SPEC_AT, NO_ROUTINE),
              [SETDTA_ANSWER, EFILNF, EFILNF, EFILNF], _FIND_POKES)
_scripted_row("found as given", sh.SH_FIND, (sh.SPEC_AT, NO_ROUTINE), [SETDTA_ANSWER, GEMDOS_OK], _FIND_POKES)
aes.register("found with sh_main's kind of routine, a logger", sh.SH_FIND, (sh.SPEC_AT, sh.ROUTINE_AT),
             sh.scripted_machine([SETDTA_ANSWER, GEMDOS_OK], merge_pokes(_FIND_POKES, sh.routine_pokes("logger"))),
             hook=sh.scripted_hook_with("logger"))
_scripted_row("EFILNF", sh.DOS_SFIRST, (sh.SPEC_AT, FIND_ATTRIBUTES), [EFILNF])
_scripted_row("found", sh.DOS_SFIRST, (sh.SPEC_AT, FIND_ATTRIBUTES), [GEMDOS_OK])
_scripted_row("a handle", sh.DOS_OPEN, (sh.SPEC_AT, 0), [HANDLE])
_scripted_row("EFILNF", sh.DOS_OPEN, (sh.SPEC_AT, 0), [EFILNF])
_scripted_row("a header", sh.DOS_READ, (HANDLE, HEADER_BYTES, sh.SPEC_AT), [HEADER_BYTES])
_scripted_row("to the start", sh.DOS_LSEEK, (HANDLE, 0, 0), [GEMDOS_OK])
