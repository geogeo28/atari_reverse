"""The dispatcher's REDIRECTED arms — a character-device call whose standard handle `Fforce` pointed at
a FILE, served by `$fd328a`'s 19-entry table instead of by the handler (`src/gemdos/dispatch.c`).

    $fc9786  move.b $30(p_run,d1.w),d0 / ext.w     the standard handle the descriptor names
    $fc979e  ble $fc98fe                           ...still a device: rewrite, and call the handler
    $fc98e8  subq.w #1 / cmp.w #18 / bhi           ...a FILE: jump through the table by selector - 1
    $fc97b6  Fread(h, 1, -14(a6))                  Cconin, Cauxin, Crawcin, Cnecin: a byte, sign-extended
    $fc97dc  Fwrite(h, 1, <char word>:$7ef4)       Cconout, Cauxout, Cprnout — through the WRONG pointer
    $fc97fa  Fwrite(h, 1, p) per byte              Cconws
    $fc982c  Fread / $fc5078 Fwrite(1, 1, p) ...   Cconrs: read, ECHO through a nested GEMDOS call, CR ends
    $fc98dc  move.l #255,d0                        Cconis, Cconos, Cprnos, Cauxis, Cauxos: always ready
    $fc97aa  (Crawio)                              DEAD: Crawio's descriptor is 0, so nothing looks

`Fread` and `Fwrite` are called BY ADDRESS here, not through the dispatch table, so a case binds no
handler — except the redirected `Cconrs`, whose echo is a whole nested dispatch and reaches `Fwrite`'s
handler when stdout is a file too.
"""
import pytest

from harness import addrs, emu, make_image

import dispatch_io as dio
import fs_file as ff
import fs_io as io
import gemdos
import gemdos_console as console
import gemdos_fs as fs

FILE = ff.A_HANDLE
LONG_MASK = fs.LONG_MASK


def _span_at(position, *standards):
    """SPAN.DAT open on the first handle record at `position`, and each of the standard handles named in
    `standards` ("stdin", "stdout", ...) redirected to it."""
    return {**dio.open_span(position), **console.handles(**{standard: FILE for standard in standards})}


def _ofd_position(result, at=io.OFD_AT):
    return fs.ofd_field(result.final, at, "pos")


# ---- the read arm ----------------------------------------------------------------------------------------
READERS = (
    ("Cconin", addrs.GEMDOS_CCONIN_FN, "stdin"),
    ("Cauxin", addrs.GEMDOS_CAUXIN_FN, "stdaux"),
    ("Crawcin", addrs.GEMDOS_CRAWCIN_FN, "stdin"),
    ("Cnecin", addrs.GEMDOS_CNECIN_FN, "stdin"),
)
# A position whose ramp byte has bit 7 set, so the answer shows the sign extension.
HIGH_BYTE_AT = 0x80 - fs.SPAN_SEED


@pytest.mark.parametrize("what,selector,standard", READERS, ids=lambda arg: str(arg))
def test_a_redirected_read_is_one_byte_of_the_file_sign_extended(what, selector, standard):
    result = dio.run(selector, (), _span_at(HIGH_BYTE_AT, standard))
    assert result.info["ret"] == 0xFFFF_FF80, what
    assert _ofd_position(result) == HIGH_BYTE_AT + 1, what
    assert not gemdos.HANDLER_CALLS, f"{what} reached its handler"


# What the frame byte `-14(a6)` held before an `Fread` that moved nothing: the ROM's own stack, and our
# build's host slot for it, both staged with it.
STALE = 0x9C
STALE_BYTE = {gemdos.DISPATCHER_FRAME_AT + addrs.GEMDOS_DISPATCH_REDIRECTED_BYTE_LOCAL: bytes([STALE]),
              fs.CONSTANTS["GEMDOS_HOST_SLOT_REDIRECTED_BYTE"]: bytes([STALE])}


def test_a_redirected_read_at_the_end_of_the_file_answers_the_stale_frame_byte():
    """ROM BUG: `Fread`'s answer is never looked at, so at the end of the file the answer is whatever
    the frame byte already held — sign-extended as if it had been read."""
    result = dio.run(addrs.GEMDOS_CCONIN_FN, (), {**_span_at(fs.SPAN_BYTES, "stdin"), **STALE_BYTE})
    assert result.info["ret"] == 0xFFFF_FF00 | STALE
    assert _ofd_position(result) == fs.SPAN_BYTES


# ---- the write arm --------------------------------------------------------------------------------------
WRITERS = (
    ("Cconout", addrs.GEMDOS_CCONOUT_FN, "stdout"),
    ("Cauxout", addrs.GEMDOS_CAUXOUT_FN, "stdaux"),
    ("Cprnout", addrs.GEMDOS_CPRNOUT_FN, "stdprn"),
)
WRITE_AT = 1100                         # mid-file, mid-cluster: cluster 5, byte 76 of its first sector
WRITE_CLOFF = WRITE_AT % fs.CLUSTER_BYTES
MARKER = 0x5A


@pytest.mark.parametrize("what,selector,standard", WRITERS, ids=lambda arg: str(arg))
def test_a_redirected_write_writes_the_byte_its_broken_pointer_names(what, selector, standard):
    """ROM BUG: the buffer pointer is the character WORD over the `setjmp` call's leftover $7ef4, so
    `Cconout('\\n')` writes the byte at $0a7ef4 — staged here as `MARKER` — and not a line feed."""
    pokes = {**_span_at(WRITE_AT, standard), dio.LINE_FEED_BUFFER: bytes([MARKER])}
    result = dio.run(selector, (addrs.CON_LF,), pokes)
    assert result.info["ret"] == 1, what
    assert dio.written(result, WRITE_CLOFF + 1)[WRITE_CLOFF] == MARKER, what
    assert _ofd_position(result) == WRITE_AT + 1, what


# A character word whose HIGH byte is set: the pointer it forms is $010a7ef4, which a 68000 cannot put on
# its 24-bit bus.
HIGH_BYTE_LINE_FEED = 0x0100 | addrs.CON_LF


def test_the_broken_pointer_is_a_24_bit_bus_address():
    """The address lines above A23 do not exist, so `Cconout($010a)` writes from $0a7ef4, the same byte
    `Cconout('\\n')` does — and the reconstruction must name that byte, not one 16 MB past its image."""
    pokes = {**_span_at(WRITE_AT, "stdout"), dio.LINE_FEED_BUFFER: bytes([MARKER])}
    result = dio.run(addrs.GEMDOS_CCONOUT_FN, (HIGH_BYTE_LINE_FEED,), pokes)
    assert result.info["ret"] == 1
    assert dio.written(result, WRITE_CLOFF + 1)[WRITE_CLOFF] == MARKER


CCONWS_WORDS = gemdos.long_words(fs.USER_AT)


def _cconws_pokes(text):
    """`text` and its NUL in the user buffer, and stdout redirected to SPAN.DAT at `WRITE_AT`."""
    return {**_span_at(WRITE_AT, "stdout"), **fs.user_buffer(text + b"\0")}


def test_cconws_writes_each_byte_with_its_own_fwrite():
    text = b"abc"
    result = dio.run(addrs.GEMDOS_CCONWS_FN, CCONWS_WORDS, _cconws_pokes(text))
    assert result.info["ret"] == 1, "the last Fwrite's answer"
    assert dio.written(result, WRITE_CLOFF + len(text))[WRITE_CLOFF:] == text
    assert _ofd_position(result) == WRITE_AT + len(text)


def test_cconws_of_an_empty_string_answers_what_the_table_jump_left_in_d0():
    """Nothing in the arm writes D0, so the answer is the record address the lookup computed with its low
    word replaced by the jump's byte index: `$fd30b0` under `(9 - 1) * 4`."""
    result = dio.run(addrs.GEMDOS_CCONWS_FN, CCONWS_WORDS, _cconws_pokes(b""))
    record = addrs.GEMDOS_FUNCTION_TABLE + addrs.GEMDOS_CCONWS_FN * addrs.GEMDOS_RECORD_BYTES
    assert result.info["ret"] == (record & 0xFFFF_0000) | (addrs.GEMDOS_CCONWS_FN - 1) * 4
    assert _ofd_position(result) == WRITE_AT


# ---- the status arm -------------------------------------------------------------------------------------

@pytest.mark.parametrize("what,selector,standard", (
    ("Cconis", addrs.GEMDOS_CCONIS_FN, "stdin"),
    ("Cconos", addrs.GEMDOS_CCONOS_FN, "stdout"),
    ("Cprnos", addrs.GEMDOS_CPRNOS_FN, "stdprn"),
    ("Cauxis", addrs.GEMDOS_CAUXIS_FN, "stdaux"),
    ("Cauxos", addrs.GEMDOS_CAUXOS_FN, "stdaux"),
), ids=lambda arg: str(arg))
def test_a_redirected_status_call_is_always_ready(what, selector, standard):
    result = dio.run(selector, (), _span_at(0, standard))
    assert result.info["ret"] == addrs.GEMDOS_REDIRECTED_READY, what


# `Cconos` as the dispatcher's handler hook reaches it: no argument words.
CCONOS_LEAF = fs.Leaf(addrs.GEMDOS_CCONOS_FN, addrs.GEMDOS_CCONOS, "gemdos_cconos", ">")
# The device a standard handle of 0 becomes: 0 + 3, which to `Bcostat` is the IKBD's ACIA, TDRE set.
IKBD_TRANSMITTER_EMPTY = {"io_seed": {addrs.IKBD_ACIA_STATUS: addrs.ACIA_TRANSMIT_READY}}


def test_a_closed_standard_handle_is_not_a_file_to_the_redirection():
    """`Fclose(1)` leaves stdout's byte 0 (`src/gemdos/handles.c`), and the redirection's test is
    `ble` — so a `Cconos` after it is NOT answered "ready" by the table, but by its own handler, on
    device 0 + 3. Proved as the sequence a program makes: the close, then the call, from its end state."""
    closed = io.dispatch_slice(fs.FCLOSE, (addrs.GEMDOS_STDOUT,), {})
    assert closed.final[console.handle_slot("stdout")] == 0
    result = dio.run(addrs.GEMDOS_CCONOS_FN, (), fs.continued(closed), (CCONOS_LEAF,), **IKBD_TRANSMITTER_EMPTY)
    assert [call[0] for call in gemdos.HANDLER_CALLS] == [addrs.GEMDOS_CCONOS]
    assert result.info["ret"] == LONG_MASK, "Bcostat's own `ready`, not the table's $ff"


def test_crawio_is_never_redirected_its_descriptor_is_0():
    """The table's `Crawio` entry ($fc97aa) is DEAD: with stdin and stdout both a file, the original
    still reaches `Crawio`'s own handler — oracle-only, because that handler would then read a device
    number off the end of GEMDOS's three."""
    staged = gemdos.slice_pokes(addrs.GEMDOS_CRAWIO_FN, (addrs.GEMDOS_CRAWIO_READ,),
                                fs.machine(io.engine(_span_at(0, "stdin", "stdout"))))
    _final, _writes, regs = emu.run(make_image(staged), gemdos.TRAMPOLINE_AT, {"a5": 0},
                                    stop_pc=gemdos.rom_handler(addrs.GEMDOS_CRAWIO_FN))
    assert regs["ninsns"] > 0, "the run never reached Crawio's handler (`emu.run` refuses a missed checkpoint)"


# ---- Cconrs -----------------------------------------------------------------------------------------------
LINE = b"HI\r\nMORE"
MAXIMUM = 10
CCONRS = addrs.GEMDOS_CCONRS_FN
CCONRS_WORDS = gemdos.long_words(fs.USER_AT)
# A run that echoes dispatches once more per character; the oracle's default budget is not enough.
ECHO_BUDGET = 2_000_000


def _line_buffer(maximum):
    return fs.user_buffer(bytes([maximum]))


def _cconrs(pokes, maximum=MAXIMUM, leaves=()):
    return dio.run(CCONRS, CCONRS_WORDS, {**_line_buffer(maximum), **pokes}, leaves, max_insns=ECHO_BUDGET,
                   dropped=dio.NESTED_RECORD)


def _line(result, length):
    return result.after(fs.USER_AT + addrs.GEMDOS_CCONRS_TEXT, length)


def _stdin_short(text=LINE):
    return {**dio.short_text(text), **dio.open_short(), **console.handles(stdin=FILE)}


def test_cconrs_reads_to_the_cr_echoes_each_byte_and_swallows_the_lf():
    result = _cconrs({**_stdin_short(), **dio.console_machine()})
    assert result.info["ret"] == 0
    assert result.after(fs.USER_AT, 2) == bytes([MAXIMUM, 2])
    assert _line(result, 3) == b"HI\r", "the CR is stored, and not counted"
    assert _ofd_position(result) == 4, "the LF after it was read too"
    assert not gemdos.HANDLER_CALLS, "stdout is the console, so the echo reached no handler"


def test_the_echo_is_a_whole_dispatch_so_stdout_redirected_is_an_fwrite_too():
    """The echo resolves stdout afresh: redirected to SPAN.DAT, it is three `Fwrite`s through the
    dispatch table — our leaf, bound — writing "HI\\r" into that file."""
    pokes = {**_stdin_short(), **dio.open_span(WRITE_AT, ff.ANOTHER_HANDLE, io.OTHER_OFD_AT),
             **console.handles(stdout=ff.ANOTHER_HANDLE)}
    result = _cconrs(pokes, leaves=(fs.FWRITE,))
    assert result.after(fs.USER_AT, 2) == bytes([MAXIMUM, 2])
    assert [call[0] for call in gemdos.HANDLER_CALLS] == [fs.FWRITE.entry] * 3
    assert _ofd_position(result, io.OTHER_OFD_AT) == WRITE_AT + 3


@pytest.mark.parametrize("maximum,length,position,why", (
    (1, 1, 1, "the maximum reached first: one byte, no CR"),
    (0, 0, 0, "a maximum of 0 reads nothing"),
))
def test_cconrs_stops_at_its_maximum(maximum, length, position, why):
    result = _cconrs({**_stdin_short(), **dio.console_machine()}, maximum=maximum)
    assert result.after(fs.USER_AT, 2) == bytes([maximum, length]), why
    assert _ofd_position(result) == position, why


def test_cconrs_at_the_end_of_the_file_stops_with_nothing():
    pokes = {**dio.short_text(LINE), **dio.open_short(fs.SHORT_BYTES), **console.handles(stdin=FILE)}
    result = _cconrs({**pokes, **dio.console_machine()})
    assert result.after(fs.USER_AT, 2) == bytes([MAXIMUM, 0])
    assert _ofd_position(result) == fs.SHORT_BYTES


SIGNED_MAXIMUM = 0x80
FIRST_CR = (addrs.CON_CR - fs.SPAN_SEED) & 0xFF      # where SPAN.DAT's ramp first reaches a CR: 205


def test_a_maximum_of_128_or_more_is_negative_and_does_not_bound_the_read():
    """ROM BUG: `move.b (a0),d0 / ext.w d0` — a maximum of 128 counts down from -128 and reaches 0 only
    after 65,536 reads, so the line runs to SPAN.DAT's first CR, 205 bytes in, past the 128 asked for.
    The console leaf's own `Cconrs` masks the same byte to 0..255. Echoed to SHORT.TXT."""
    pokes = {**dio.open_span(0), **console.handles(stdin=FILE),
             **dio.open_short(0, ff.ANOTHER_HANDLE, io.OTHER_OFD_AT), **console.handles(stdout=ff.ANOTHER_HANDLE)}
    result = _cconrs(pokes, maximum=SIGNED_MAXIMUM, leaves=(fs.FWRITE,))
    assert result.after(fs.USER_AT, 2) == bytes([SIGNED_MAXIMUM, FIRST_CR])
    assert _line(result, FIRST_CR) == fs.SPAN_BODY[:FIRST_CR]


def test_a_nested_echo_arms_the_record_with_its_own_frame():
    """What `dispatch_io.nested_record` reads is the ORIGINAL's nested `setjmp` and nothing else:
    an A6 and a stack pointer below the outer dispatcher's frame, and a resume address inside `$fc94e4`
    before its slice."""
    pokes = {**_line_buffer(MAXIMUM), **_stdin_short(), **dio.console_machine()}
    (frame, stack, resume), _poke = dio.nested_record(CCONRS, CCONRS_WORDS, pokes, ECHO_BUDGET)
    assert stack < frame < gemdos.DISPATCHER_SP
    assert addrs.GEMDOS_DISPATCH < resume < addrs.GEMDOS_DISPATCH_SELECTOR


# ---- the registry ------------------------------------------------------------------------------------------

def _register_all():
    dio.register("Cconin redirected to a file", addrs.GEMDOS_CCONIN_FN, (), _span_at(HIGH_BYTE_AT, "stdin"))
    dio.register("Cconout redirected to a file", addrs.GEMDOS_CCONOUT_FN, (addrs.CON_LF,),
                 {**_span_at(WRITE_AT, "stdout"), dio.LINE_FEED_BUFFER: bytes([MARKER])})
    dio.register("Cconws redirected to a file", addrs.GEMDOS_CCONWS_FN, CCONWS_WORDS, _cconws_pokes(b"abc"))
    dio.register("Cconws of an empty string redirected to a file", addrs.GEMDOS_CCONWS_FN, CCONWS_WORDS,
                 _cconws_pokes(b""))
    dio.register("Cconis redirected to a file", addrs.GEMDOS_CCONIS_FN, (), _span_at(0, "stdin"))
    pokes = {**_line_buffer(MAXIMUM), **_stdin_short(), **dio.console_machine()}
    dio.register("Cconrs redirected to a file", CCONRS, CCONRS_WORDS,
                 dio.record_mask(CCONRS, CCONRS_WORDS, pokes, ECHO_BUDGET))


_register_all()
