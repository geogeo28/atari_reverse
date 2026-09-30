"""AES scrp_read/scrp_write ($feac80/$feac94), shel_read/shel_write/shel_get/shel_put ($feaca8..$fead40) and rs_str
($fea6e6) — the copies between a caller's buffer and the AES's own: `src/aes/shell_buf.c`, `src/aes/resource.c`.

    sc_read(p)  = lstcpy(p, scrap path)            sc_write(p) = lstcpy(scrap path, p)       D0 as lstcpy left it
    sh_read(c, t):  LBCOPY(c, *shell_buffer, 128); LBCOPY(t, *shell_tail, 128); 1
    sh_write(doex, isgem, isover, c, t):  the two copies back; sh_doexec = doex; sh_isdef = sh_dodef = 0;
                                          sh_isgem = isgem != 0; 1
    sh_get(b, n) = LBCOPY(b, gem buffer, n); 1     sh_put(d, n) = LBCOPY(gem buffer, d, n); 1
    rs_str(n):  rsrc_gaddr(the AES's global[], R_STRING, n) copied into AES_RS_STRING, its answer

Seeded with the snapshot's own: the shell's GEM buffer holds the DESKTOP.INF text, and the AES's resource its thirty
free strings (alerts, validation templates, three empty). The shell's command line and tail and the scrap path are
empty in the capture, so a case stages text there. The copies are the utility layer's (`aes/strings.h`, their own
battery); what these hold is WHICH buffer goes where, how many bytes, and the flags.
"""
import pytest

from harness import BASE_IMAGE

import aes
import aes_resource as rs
import case
import vdi
from case import merge_pokes

SC_READ = "AES_ROM_SC_READ"
SC_WRITE = "AES_ROM_SC_WRITE"
SH_READ = "AES_ROM_SH_READ"
SH_WRITE = "AES_ROM_SH_WRITE"
SH_GET = "AES_ROM_SH_GET"
SH_PUT = "AES_ROM_SH_PUT"
RS_STR = "AES_ROM_RS_STR"
for _name, _argtypes in ((SC_READ, (vdi.LONG_ARG,)), (SC_WRITE, (vdi.LONG_ARG,)),
                         (SH_READ, (vdi.LONG_ARG, vdi.LONG_ARG)),
                         (SH_WRITE, (vdi.WORD_ARG, vdi.WORD_ARG, vdi.WORD_ARG, vdi.LONG_ARG, vdi.LONG_ARG)),
                         (SH_GET, (vdi.LONG_ARG, vdi.WORD_ARG)), (SH_PUT, (vdi.LONG_ARG, vdi.WORD_ARG))):
    aes.declare_alcyon(_name, aes.WORD_ANSWER, (vdi.IMAGE_ARG, *_argtypes))
aes.declare_alcyon(RS_STR, aes.LONG_ANSWER, (vdi.IMAGE_ARG, vdi.WORD_ARG))

LINE = aes.AES_SHELL_LINE_BYTES
COMMAND = case.long_in(BASE_IMAGE, aes.AES_SHELL_BUFFER)
TAIL = case.long_in(BASE_IMAGE, aes.AES_SHELL_TAIL)
SCRAP_PATH_BYTES = 0x80                  # more than any path a case stages
GEM_BUFFER_BYTES = 0x400                 # the DESKTOP.INF text's room, as the desk reads and writes it
STRING_BYTES = 0x100                     # AES_RS_STRING's room: the longest free string is 167 bytes
for _at, _size, _why in ((COMMAND, LINE, "the shell's command line"), (TAIL, LINE, "the shell's command tail"),
                         (aes.AES_SCRAP_PATH, SCRAP_PATH_BYTES, "the scrap directory's path"),
                         (aes.AES_SHELL_GEM_BUFFER, GEM_BUFFER_BYTES, "the shell's GEM buffer: DESKTOP.INF"),
                         (aes.AES_RS_STRING, STRING_BYTES, "rs_str's copy of a free string"),
                         *((at, aes.WORD_BYTES, "shel_write's flags") for at in
                           (aes.AES_SH_DOEXEC, aes.AES_SH_ISGEM, aes.AES_SH_DODEF, aes.AES_SH_ISDEF))):
    aes.declare_case_field(_at, _size, _why)

BUFFER, SECOND = rs.BUFFER_AT, rs.SECOND_BUFFER_AT


def text(content, length):
    """`content` NUL-padded — then FILLed — to `length` bytes, so a copy one byte short or long shows."""
    padded = content + b"\0"
    return padded + bytes([vdi.FILL]) * (length - len(padded))


def run(name, arguments, pokes=None, **kwargs):
    return rs.run(name, arguments, pokes, **kwargs)


# ---- scrp_read / scrp_write -----------------------------------------------------------------------------------------
PATHS = (b"C:\\CLIPBRD", b"", b"A:\\" + b"FOLDER\\" * 15)


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("path", PATHS, ids=("a path", "empty", "a long path"))
def test_scrp_read_copies_the_scrap_path_out(path, through_line_f):
    pokes = {aes.AES_SCRAP_PATH: text(path, SCRAP_PATH_BYTES), BUFFER: text(b"stale", rs.BUFFER_BYTES)}
    result = run(SC_READ, (BUFFER,), pokes, through_line_f=through_line_f)
    assert result.after(BUFFER, len(path) + 1) == path + b"\0"
    assert result.final[BUFFER + len(path) + 1] == pokes[BUFFER][len(path) + 1], "not a byte past the NUL"


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("path", PATHS, ids=("a path", "empty", "a long path"))
def test_scrp_write_copies_the_path_in(path, through_line_f):
    pokes = {BUFFER: text(path, rs.BUFFER_BYTES), aes.AES_SCRAP_PATH: text(b"OLD:\\SCRAP\\PATH", SCRAP_PATH_BYTES)}
    result = run(SC_WRITE, (BUFFER,), pokes, through_line_f=through_line_f)
    assert result.after(aes.AES_SCRAP_PATH, len(path) + 1) == path + b"\0"


def test_the_scrap_path_pointer_is_put_on_the_bus():
    pokes = {BUFFER: text(PATHS[0], rs.BUFFER_BYTES)}
    assert run(SC_WRITE, (BUFFER | aes.BUS_TAG,), pokes).after(aes.AES_SCRAP_PATH, len(PATHS[0])) == PATHS[0]
    pokes = {aes.AES_SCRAP_PATH: text(PATHS[0], SCRAP_PATH_BYTES), BUFFER: text(b"stale", rs.BUFFER_BYTES)}
    assert run(SC_READ, (BUFFER | aes.BUS_TAG,), pokes).after(BUFFER, len(PATHS[0]) + 1) == PATHS[0] + b"\0"


# ---- shel_read / shel_write -----------------------------------------------------------------------------------------
LINE_TEXT = bytes(range(1, LINE + 1))                     # every byte of the 128 distinct, none a NUL
TAIL_TEXT = bytes(range(0xFF, 0xFF - LINE, -1))                 # ...and a second run, falling


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_shel_read_copies_both_128_byte_lines_out(through_line_f):
    pokes = {COMMAND: LINE_TEXT, TAIL: TAIL_TEXT, BUFFER: text(b"", rs.BUFFER_BYTES), SECOND: text(b"", rs.BUFFER_BYTES)}
    result = run(SH_READ, (BUFFER, SECOND), pokes, through_line_f=through_line_f)
    assert (result.after(BUFFER, LINE), result.after(SECOND, LINE)) == (LINE_TEXT, TAIL_TEXT)
    assert result.final[BUFFER + LINE] == vdi.FILL, "128 bytes, not one more"
    assert result.answer() == 1


def test_shel_read_copies_the_command_line_first():
    """The ORDER: the caller's tail buffer laid over the shell's own command line — the line is read out before the
    tail is copied over it."""
    pokes = {COMMAND: LINE_TEXT, TAIL: TAIL_TEXT}
    result = run(SH_READ, (BUFFER, COMMAND), pokes)
    assert (result.after(BUFFER, LINE), result.after(COMMAND, LINE)) == (LINE_TEXT, TAIL_TEXT)


STALE_FLAGS = aes.field_pokes("AES", SH_DOEXEC=aes.STALE_WORD, SH_ISGEM=aes.STALE_WORD, SH_DODEF=aes.STALE_WORD,
                              SH_ISDEF=aes.STALE_WORD)


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("doexec,isgem,isover", ((1, 1, 0), (0, 0, 1), (-2, 0x0100, -1)),
                         ids=("launch a GEM program", "none, isover set", "any words"))
def test_shel_write_copies_both_lines_in_and_sets_the_requests(doexec, isgem, isover, through_line_f):
    pokes = merge_pokes(STALE_FLAGS, {BUFFER: LINE_TEXT, SECOND: TAIL_TEXT})
    result = run(SH_WRITE, (doexec, isgem, isover, BUFFER, SECOND), pokes, through_line_f=through_line_f)
    assert (result.after(COMMAND, LINE), result.after(TAIL, LINE)) == (LINE_TEXT, TAIL_TEXT)
    flags = [result.field("AES", name) for name in ("SH_DOEXEC", "SH_ISDEF", "SH_DODEF", "SH_ISGEM")]
    assert flags == [doexec & 0xFFFF, 0, 0, int(isgem != 0)]
    assert result.answer() == 1


def test_shel_write_s_pointers_are_put_on_the_bus():
    pokes = merge_pokes(STALE_FLAGS, {BUFFER: LINE_TEXT, SECOND: TAIL_TEXT})
    result = run(SH_WRITE, (1, 0, 0, BUFFER | aes.BUS_TAG, SECOND | aes.BUS_TAG), pokes)
    assert (result.after(COMMAND, LINE), result.after(TAIL, LINE)) == (LINE_TEXT, TAIL_TEXT)


def test_shel_read_s_pointers_are_put_on_the_bus():
    pokes = {COMMAND: LINE_TEXT, TAIL: TAIL_TEXT}
    result = run(SH_READ, (BUFFER | aes.BUS_TAG, SECOND | aes.BUS_TAG), pokes)
    assert (result.after(BUFFER, LINE), result.after(SECOND, LINE)) == (LINE_TEXT, TAIL_TEXT)


# The shell's OWN pointers (AES_SHELL_BUFFER, AES_SHELL_TAIL) are longwords in RAM a program's shel_write never sets,
# but stored with a top byte they reach their buffers through 24 bits all the same, on the way out and in.
TAGGED_SHELL_POINTERS = aes.field_pokes("AES", SHELL_BUFFER=COMMAND | aes.BUS_TAG, SHELL_TAIL=TAIL | aes.BUS_TAG)


def test_the_shell_s_stored_pointers_are_put_on_the_bus():
    result = run(SH_READ, (BUFFER, SECOND), merge_pokes(TAGGED_SHELL_POINTERS, {COMMAND: LINE_TEXT, TAIL: TAIL_TEXT}))
    assert (result.after(BUFFER, LINE), result.after(SECOND, LINE)) == (LINE_TEXT, TAIL_TEXT)
    pokes = merge_pokes(TAGGED_SHELL_POINTERS, STALE_FLAGS, {BUFFER: LINE_TEXT, SECOND: TAIL_TEXT})
    result = run(SH_WRITE, (1, 0, 0, BUFFER, SECOND), pokes)
    assert (result.after(COMMAND, LINE), result.after(TAIL, LINE)) == (LINE_TEXT, TAIL_TEXT)


# ---- shel_get / shel_put --------------------------------------------------------------------------------------------
INF_TEXT = bytes(BASE_IMAGE[aes.AES_SHELL_GEM_BUFFER:aes.AES_SHELL_GEM_BUFFER + rs.BUFFER_BYTES])


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("count", (0, 1, 80, rs.BUFFER_BYTES - 1), ids=("none", "one", "a line", "a whole buffer"))
def test_shel_get_copies_the_desktop_inf_text_out(count, through_line_f):
    pokes = {BUFFER: text(b"", rs.BUFFER_BYTES)}
    result = run(SH_GET, (BUFFER, count), pokes, through_line_f=through_line_f)
    assert result.after(BUFFER, count) == INF_TEXT[:count]
    assert result.final[BUFFER + count] == pokes[BUFFER][count], "`count` bytes, not one more"
    assert result.answer() == 1


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("count", (0, 1, rs.BUFFER_BYTES), ids=("none", "one", "a whole buffer"))
def test_shel_put_copies_the_caller_s_text_in(count, through_line_f):
    data = bytes((index * 7 + 3) & 0xFF for index in range(rs.BUFFER_BYTES))
    result = run(SH_PUT, (BUFFER, count), {BUFFER: data}, through_line_f=through_line_f)
    assert result.after(aes.AES_SHELL_GEM_BUFFER, count) == data[:count]
    assert result.final[aes.AES_SHELL_GEM_BUFFER + count] == BASE_IMAGE[aes.AES_SHELL_GEM_BUFFER + count]


def test_shel_get_and_put_pointers_are_put_on_the_bus():
    assert run(SH_GET, (BUFFER | aes.BUS_TAG, 16)).after(BUFFER, 16) == INF_TEXT[:16]
    assert run(SH_PUT, (BUFFER | aes.BUS_TAG, 4), {BUFFER: b"#z01"}).after(aes.AES_SHELL_GEM_BUFFER, 4) == b"#z01"


# ---- rs_str ---------------------------------------------------------------------------------------------------------
GEM_STRINGS = rs.header_words(rs.GEM_HEADER)["nstring"]
STALE_STRING = {aes.AES_RS_STRING: text(b"", STRING_BYTES)}


def free_string(index, image=BASE_IMAGE):
    address = rs.model_get_addr(image, rs.R_STRING, index)
    return bytes(image[address:address + STRING_BYTES]).split(b"\0")[0]


@pytest.mark.parametrize("index", range(GEM_STRINGS))
def test_every_free_string_of_the_aes_s_resource(index):
    """All thirty, over globals left STALE (rs_str sets them): the alerts, the templates, the three empty ones."""
    result = run(RS_STR, (index,), merge_pokes(rs.STALE_GLOBALS, STALE_STRING))
    string = free_string(index)
    assert result.after(aes.AES_RS_STRING, len(string) + 1) == string + b"\0"
    assert result.long_answer() == aes.AES_RS_STRING
    assert (result.long(aes.AES_RS_GLOBAL), result.long(aes.AES_RS_HDR)) == (rs.GEM_GLOBAL, rs.GEM_HEADER)


def test_a_free_string_through_line_f():
    result = run(RS_STR, (13,), STALE_STRING, through_line_f=True)
    assert result.after(aes.AES_RS_STRING, 4) == b"[2][" and result.long_answer() == aes.AES_RS_STRING


def test_the_string_past_the_last_is_the_table_after():
    """String 30 of 30: its table entry is the free images' first — a BITBLK's address, copied as a string."""
    result = run(RS_STR, (GEM_STRINGS,), STALE_STRING)
    string = free_string(GEM_STRINGS)
    assert result.after(aes.AES_RS_STRING, len(string) + 1) == string + b"\0"


# ---- the registry ---------------------------------------------------------------------------------------------------
aes.register("a path", SC_READ, (BUFFER,), aes.leaf_machine(onto={aes.AES_SCRAP_PATH: text(PATHS[0], SCRAP_PATH_BYTES)}))
aes.register("a long path", SC_WRITE, (BUFFER,), aes.leaf_machine(onto={BUFFER: text(PATHS[2], rs.BUFFER_BYTES)}))
aes.register("both lines", SH_READ, (BUFFER, SECOND), aes.leaf_machine(onto={COMMAND: LINE_TEXT, TAIL: TAIL_TEXT}))
aes.register("both lines", SH_WRITE, (1, 1, 0, BUFFER, SECOND),
             aes.leaf_machine(onto=merge_pokes(STALE_FLAGS, {BUFFER: LINE_TEXT, SECOND: TAIL_TEXT})))
aes.register("a whole buffer", SH_GET, (BUFFER, rs.BUFFER_BYTES), aes.leaf_machine())
aes.register("a whole buffer", SH_PUT, (BUFFER, rs.BUFFER_BYTES), aes.leaf_machine(onto={BUFFER: LINE_TEXT * 2}))
aes.register("the longest alert", RS_STR, (16,), aes.leaf_machine(onto=merge_pokes(rs.STALE_GLOBALS, STALE_STRING)))
aes.register("an empty string", RS_STR, (20,), aes.leaf_machine(onto=merge_pokes(rs.STALE_GLOBALS, STALE_STRING)))
