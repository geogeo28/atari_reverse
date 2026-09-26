"""The dispatcher's two DEVICE arms — `src/gemdos/dispatch.c` serving a call itself, no handler reached.

    $fc9aca  cmpi.w #61 / #60        Fopen or Fcreate: the name against the six at $fd32d6, each through
    $fc9af4  jsr $fc7e94 (5, name, "CON:")    `gemdos_strneq` over FIVE bytes — the NUL included — so a
    ...                                        name matches whole and in one of two cases; a match answers
    $fc9b1a  move.l #$ffff,-42(a6)             the handle as an unsigned WORD ($ffff/$fffe/$fffd)
    $fc99b4  tst.l -46(a6) / bge             an argument HANDLE that resolved NEGATIVE — a device:
    $fc99ce  cmpi.w #63                        Fread: `tst.w 4(a0)` (a count of 64 KB or more answers 0),
    $fc99fe  jsr $fc8fc6                         one character read and echoed, or the line editor
    $fc9a24  jsr $fc9226                         ($fc9226) into the buffer for any other count;
    $fc9a32  cmpi.w #64                        Fwrite: the same test, then each byte SIGN-EXTENDED to
    $fc9a74  jsr $fc8e3c                         the console's TAB expander, or to `Bconout` for AUX:/PRN:,
    $fc9a94  jsr $fc4eac (Bconout)               answering the count as a signed word; anything else — an
    $fc9ac0  clr.l d0                            `Fseek` on a device — answers 0.

Every case is a SLICE differential (`dispatch_io.run`): our dispatcher, with the leaf bound but required
NOT to be called where the arm answers by itself.
"""
import pytest

from harness import BASE_IMAGE, addrs

import dispatch_io as dio
import fs_create as fc
import fs_dir as d
import fs_file as ff
import fs_open as fo
import gemdos
import gemdos_console as console
import gemdos_fs as fs

FOPEN, FCREATE = fs.FOPEN, fs.FCREATE
FREAD_FN, FWRITE_FN, FSEEK_FN = addrs.GEMDOS_FREAD_FN, addrs.GEMDOS_FWRITE_FN, addrs.GEMDOS_FSEEK_FN
CON, AUX, PRN = console.HANDLE_CON, console.HANDLE_AUX, console.HANDLE_PRN
STDIN, STDOUT = addrs.GEMDOS_STDIN, addrs.GEMDOS_STDOUT
WORD_MASK = 0xFFFF
BUFFER = gemdos.long_words(fs.USER_AT)


def _device_word(handle):
    """What the device-name arm answers: the handle as an unsigned word, high half clear."""
    return handle & WORD_MASK


# ---- the device-name arm --------------------------------------------------------------------------------
# All six names, read out of the ROM rather than typed, each with the handle its pair answers.
DEVICE_NAMES = tuple(
    (bytes(BASE_IMAGE[at:at + addrs.GEMDOS_DEVICE_NAME_BYTES - 1]).decode(), handle)
    for index, handle in enumerate((CON, AUX, PRN))
    for at in (addrs.GEMDOS_DEVICE_NAMES
               + (addrs.GEMDOS_DEVICE_NAME_SPELLINGS * index + spelling) * addrs.GEMDOS_DEVICE_NAME_BYTES
               for spelling in range(addrs.GEMDOS_DEVICE_NAME_SPELLINGS)))


def _open_words(mode=fs.OPEN_MODE_READ):
    return (*gemdos.long_words(fo.NAME_AT), mode)


def _fopen(name, extra=None):
    return dio.run(FOPEN.selector, _open_words(), fo.staging(name, extra), leaves=(FOPEN,))


def _fcreate(name):
    return dio.run(FCREATE.selector, (*gemdos.long_words(d.TEXT_AT), fs.ATTR_NONE), fc.staged(name), leaves=(FCREATE,))


def test_the_rom_spells_each_device_twice_upper_case_first():
    assert [name for name, _handle in DEVICE_NAMES] == ["CON:", "con:", "AUX:", "aux:", "PRN:", "prn:"]


@pytest.mark.parametrize("name,handle", DEVICE_NAMES, ids=lambda arg: str(arg))
def test_fopen_of_a_device_name_answers_its_handle_and_calls_no_leaf(name, handle):
    """Every name, so the walk crosses all three pairs and both spellings of each."""
    result = _fopen(name)
    assert result.info["ret"] == _device_word(handle)
    assert not gemdos.HANDLER_CALLS, "the device-name arm called the file system's leaf"


@pytest.mark.parametrize("name,handle", DEVICE_NAMES[::2], ids=lambda arg: str(arg))
def test_fcreate_of_a_device_name_answers_the_same(name, handle):
    result = _fcreate(name)
    assert result.info["ret"] == _device_word(handle)
    assert not gemdos.HANDLER_CALLS


@pytest.mark.parametrize("name,why", (
    ("Con:", "mixed case: neither spelling"),
    ("CONX", "a near miss in the fourth byte"),
    ("CON:X", "...and in the fifth: the NUL is compared too"),
    ("CON", "a prefix of the name, whose NUL meets the colon"),
    ("A:CON:", "a drive prefix: no longer the whole name"),
    ("PRN", "the LAST pair's prefix, so every pair is compared and missed"),
))
def test_any_other_name_goes_on_to_the_leaf(name, why):
    result = _fopen(name)
    assert result.info["ret"] == fo.EFILNF, why
    assert [call[0] for call in gemdos.HANDLER_CALLS] == [FOPEN.entry], why


# ---- the device arm: Fwrite -------------------------------------------------------------------------------

def _io_words(handle, count, buffer=BUFFER):
    return (handle & WORD_MASK, *gemdos.long_words(count), *buffer)


def _fwrite_staging(handle, data, pokes, count=None):
    """An `Fwrite` of `data` from the user buffer — `count` bytes of it, `len(data)` unless said — as
    `(words, pokes)`: what a case runs and a row registers."""
    count = len(data) if count is None else count
    return _io_words(handle, count), {**fs.user_buffer(data), **pokes}


def _fwrite(handle, data, pokes, count=None, **seeds):
    return dio.run(FWRITE_FN, *_fwrite_staging(handle, data, pokes, count), **seeds)


def _column(result):
    return result.word(console.column_slot(console.DEVICE_CONSOLE))


@pytest.mark.parametrize("handle,why", (
    (CON, "the device handle itself"),
    (STDOUT, "stdout, which the snapshot's process holds as the console"),
))
def test_fwrite_to_the_console_writes_through_the_tab_expander(handle, why):
    result = _fwrite(handle, b"Hi\t!", dio.console_machine())
    assert result.info["ret"] == 4, why
    # Three columns in, "Hi" to five, the TAB to the stop at eight, "!" to nine.
    assert _column(result) == addrs.CON_TAB_WIDTH + 1, why
    assert not gemdos.HANDLER_CALLS


def _column_of_the_machine():
    return int.from_bytes(dio.console_machine()[console.column_slot(console.DEVICE_CONSOLE)], "big")


def test_fwrite_sign_extends_each_byte_so_a_high_byte_moves_no_column():
    """`move.b (a0),d0 / ext.w d0`: $e9 arrives as $ffe9, which `device_put`'s signed test takes for a
    control code — the column stays where it was."""
    result = _fwrite(CON, b"\xe9", dio.console_machine())
    assert result.info["ret"] == 1
    assert _column(result) == _column_of_the_machine()


@pytest.mark.parametrize("handle,machine", ((AUX, dio.RS232), (PRN, dio.PRINTER)), ids=("aux", "prn"))
def test_fwrite_to_aux_or_prn_goes_straight_to_bconout(handle, machine):
    pokes, seeds = machine
    result = _fwrite(handle, b"abc", pokes, **seeds)
    assert result.info["ret"] == 3
    assert gemdos.bios_call_site(result.info) == addrs.BIOS_RETURN_DEVICE_WRITE


def test_a_handle_record_naming_a_device_is_served_by_the_arm():
    """`Fdup` of a standard handle leaves a record whose value is the device (`src/gemdos/handles.c`):
    the resolution answers it negative and the arm writes to AUX: just as for -2 itself."""
    pokes, seeds = dio.RS232
    result = _fwrite(ff.A_HANDLE, b"xy", {**pokes, **ff.handle_naming(AUX)}, **seeds)
    assert result.info["ret"] == 2


@pytest.mark.parametrize("count,answer,why", (
    (0x0001_0003, 0, "a count of 64 KB and more: its high word is not 0, so 0 and nothing written"),
    (0x0000_8000, 0xFFFF_8000, "a count whose low word is negative: the loop never runs, the count answers"),
    (0, 0, "a count of 0"),
))
def test_fwrite_counts_are_one_signed_word(count, answer, why):
    result = _fwrite(CON, b"never", dio.console_machine(), count=count)
    assert result.info["ret"] == answer, why
    assert _column(result) == _column_of_the_machine(), why


# ---- the device arm: Fread --------------------------------------------------------------------------------
A_KEY = 0x001E_0061                     # 'a', its scancode above it
B_KEY = 0x0030_0062
RETURN = 0x001C_0000 | addrs.CON_CR


def _fread(handle, count, pokes):
    return dio.run(FREAD_FN, _io_words(handle, count), {**fs.user_buffer(), **pokes})


@pytest.mark.parametrize("handle,key,why", (
    (CON, A_KEY, "the device handle itself"),
    (STDIN, A_KEY, "stdin, which the snapshot's process holds as the console"),
    (CON, RETURN, "a CR, which is a character here: the line editor would have ended on it"),
), ids=("con", "stdin", "cr"))
def test_fread_of_one_byte_takes_a_record_and_stores_its_low_byte(handle, key, why):
    result = _fread(handle, 1, dio.keys_queued(key, B_KEY))
    assert result.info["ret"] == 1, why
    assert result.after(fs.USER_AT, 2) == bytes([key & 0xFF, fs.SLACK_FILL]), why
    assert console.queue_state(result.final, console.DEVICE_CONSOLE)[0] == 1, "the second key is still queued"


def test_fread_of_more_runs_the_line_editor_into_the_buffer_itself():
    """No length prefix: the characters land at the buffer's first byte and the count is the answer."""
    result = _fread(CON, 10, dio.keys_queued(A_KEY, B_KEY, RETURN))
    assert result.info["ret"] == 2
    assert result.after(fs.USER_AT, 3) == b"ab" + bytes([fs.SLACK_FILL])


def test_fread_of_64_kb_and_more_answers_0_and_reads_nothing():
    result = _fread(CON, 0x0001_0001, dio.keys_queued(A_KEY))
    assert result.info["ret"] == 0
    assert console.queue_state(result.final, console.DEVICE_CONSOLE)[0] == 1


# An offset whose low word is 0, so that a reconstruction serving `Fseek` as an `Fwrite` would find a count
# there it could write, and answer.
FSEEK_ON_THE_CONSOLE = (*gemdos.long_words(0x0001_0000), CON & WORD_MASK, 0)


def test_fseek_on_a_device_answers_0():
    result = dio.run(FSEEK_FN, FSEEK_ON_THE_CONSOLE, {})
    assert result.info["ret"] == 0
    assert not gemdos.HANDLER_CALLS


# ---- the registry ------------------------------------------------------------------------------------------

# THE SHORT ROWS are registered beside the long ones on purpose: the arm has a FIXED cost — the dispatch,
# the resolution, the count test — that a row of several bytes amortises, and a row kept under the bar
# only by its length would hide it. One byte is the character-at-a-time idiom a program really uses.
AUX_WRITES = (
    ("Fwrite to AUX:", b"abc", None),
    ("Fwrite of one byte to AUX:", b"a", None),
    ("Fwrite of nothing to AUX:", b"a", 0),
    ("Fwrite of 64 KB to AUX:", b"a", 0x0001_0001),
)


def _register_all():
    dio.register("Fopen of PRN:", FOPEN.selector, _open_words(), fo.staging("prn:"))
    dio.register("Fwrite to the console", FWRITE_FN, *_fwrite_staging(CON, b"Hi\t!", dio.console_machine()))
    for label, data, count in AUX_WRITES:
        dio.register(label, FWRITE_FN, *_fwrite_staging(AUX, data, dio.RS232[0], count), **dio.RS232[1])
    dio.register("Fseek on the console", FSEEK_FN, FSEEK_ON_THE_CONSOLE, {})
    dio.register("Fread of a line", FREAD_FN, _io_words(CON, 10),
                 {**fs.user_buffer(), **dio.keys_queued(A_KEY, B_KEY, RETURN)})


_register_all()
