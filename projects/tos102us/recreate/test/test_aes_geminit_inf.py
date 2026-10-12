r"""THE INF READER (`src/aes/geminit.c`: gem_read_inf, `$fda408`) AT TIER 1, OVER THE RECORDER — every arm of it, the
ROM's routine against the C over one machine (`aes_geminit.reader_machine`: the recording, scripted `trap #1` that lays
the file's bytes at the read).

    buffer = dos_alloc(2048); sh_get(buffer, 2048)
    if (isdrive() && usable) {
        drive = dos_gdrv(); dos_chdir("\\"); handle = dos_open("DESKTOP.INF", 0)
        if (DOS_ERR) { if (isdrive() & 4) { dos_sdrv(2); dos_chdir("\\"); handle = dos_open("DESKTOP.INF", 0) } else DOS_ERR = 1 }
        if (!DOS_ERR) { count = dos_read(handle, 2048, buffer); dos_close(handle); read = 1; dos_sdrv(drive) }
        else rom_ram(3, buffer, 0)
    } else rom_ram(3, buffer, 0)
    if (read) { buffer[(int)count] = 0; ...the first `#E`: its second pair (below) }
    sh_put(buffer, 2048); dos_free(buffer); return read

AN ARGUMENT CLASS, EVERY CASE: the post-boot machine with the three words the reader reads staged (the usable-disk
word, the pending change, the device in use) and GEMDOS scripted — the reader's own arrival is the boot's, where the
ROM's GEMDOS is real (slice B's rows: no file / a file). What is held here is what a boot cannot choose: a C: without
the file, a read that fails, a count past the block, every shape of the `#E` line.

THE SURFACES. The differential compares the megabyte — the block, its guards, the shell's GEM buffer, the two device
words, the glue's words AND THE LEDGER: every call's function, its frame's own bytes and the two return longwords the
glue had parked at it, in order, on both shores. Each test then says what the ROM did, off the same run.

NOT RUN: Malloc refusing (the reader carries on with a block at 0 and copies 2,048 bytes over the vector page — the
recording trap's own vector with them: no machine).
"""
import pytest

from harness import BASE_IMAGE, addrs

import aes
import aes_gemdosif
import aes_geminit as gi
import case
import gemdos

GEMINIT = gi.GEMINIT
BLOCK, BYTES = gi.BLOCK_AT, gi.INF_BUFFER_BYTES
MALLOC, MFREE, DGETDRV, DSETDRV, DSETPATH = gi.MALLOC, gi.MFREE, gi.DGETDRV, gi.DSETDRV, gi.DSETPATH
FOPEN, FREAD, FCLOSE = gi.FOPEN, gi.FREAD, gi.FCLOSE
ROOT, NAME = GEMINIT["AES_INF_ROOT"], GEMINIT["AES_INF_NAME"]
ROOT_OF_C, NAME_OF_C = GEMINIT["AES_INF_ROOT_OF_C"], GEMINIT["AES_INF_NAME_OF_C"]
DRIVE_A, DRIVE_B, DRIVE_C = 0, 1, 2
A_AND_B, A_B_AND_C = 0b011, 0b111       # the drive map Dsetdrv answers
HANDLE = gi.HANDLE
EFILNF, EIHNDL = -33, -37
NO_ERROR = 0
# The ROM's own default INF, as rom_ram's part 3 lays it into the block: what the shell's buffer holds after a call
# that read no file. Read off the ROM's run below (`test_with_no_file_...`), never spelt.
DEVICE_IN_USE = 2                       # staged, each case's own unless it says
READ, NOT_READ = GEMINIT["INF_READ"], GEMINIT["INF_NOT_READ"]


def _long(value):
    return value & aes.LONG_MASK


def to_the_open(drive=DRIVE_A, drive_map=A_AND_B, handle=HANDLE):
    """The script, and the calls expected, from the block to the first open: `(answers, calls)`."""
    answers = [BLOCK, drive, drive_map, drive, NO_ERROR, _long(handle)]
    made = [gi.call(MALLOC, ("l", BYTES)), gi.call(DGETDRV), gi.call(DSETDRV, ("w", drive)), gi.call(DGETDRV),
            gi.call(DSETPATH, ("l", ROOT)), gi.call(FOPEN, ("l", NAME), ("w", 0))]
    return answers, made


def the_read(count, handle=HANDLE, drive=DRIVE_A, drive_map=A_AND_B):
    """...the read, the close and the drive put back."""
    return ([_long(count), NO_ERROR, drive_map],
            [gi.call(FREAD, ("w", handle), ("l", BYTES), ("l", BLOCK)), gi.call(FCLOSE, ("w", handle)),
             gi.call(DSETDRV, ("w", drive))])


THE_FREE = ([NO_ERROR], [gi.call(MFREE, ("l", BLOCK))])


def road(*legs):
    answers, made = [], []
    for leg_answers, leg_calls in legs:
        answers += leg_answers
        made += leg_calls
    return answers, made


def read_road(text, count=None, drive=DRIVE_A, handle=HANDLE):
    """A file of `text` on the current drive, read: `(answers, calls)`."""
    read = the_read(len(text) if count is None else count, handle & aes.WORD_MASK, drive & aes.WORD_MASK)
    return road(to_the_open(drive=drive, handle=handle), read, THE_FREE)


def block_after(result):
    return result.after(BLOCK, BYTES)


def guards_after(result):
    return result.after(BLOCK - gi.GUARD_BYTES, gi.GUARD_BYTES), result.after(BLOCK + BYTES, gi.GUARD_BYTES)


UNTOUCHED_GUARD = bytes([gi.GUARD_FILL]) * gi.GUARD_BYTES


def shell_buffer_after(result):
    return result.after(aes.AES_SHELL_GEM_BUFFER, BYTES)


SHELL_BUFFER_BEFORE = bytes(BASE_IMAGE[aes.AES_SHELL_GEM_BUFFER:aes.AES_SHELL_GEM_BUFFER + BYTES])


def expected_block(text, count=None):
    """The block where a file of `text` was read and nothing rewritten: the text over the shell's buffer's copy, a NUL
    where the count says (inside the block)."""
    count = len(text) if count is None else count
    block = bytearray(SHELL_BUFFER_BEFORE)
    block[:len(text)] = text
    if 0 <= count < BYTES:
        block[count] = 0
    return bytes(block)


# ---- no file is read ------------------------------------------------------------------------------------------------------
def _no_file_cases():
    blank = road(([BLOCK, DRIVE_A, 0], [gi.call(MALLOC, ("l", BYTES)), gi.call(DGETDRV), gi.call(DSETDRV, ("w", DRIVE_A))]), THE_FREE)
    first, opened = to_the_open(handle=EFILNF)
    no_c = road((first, opened), ([DRIVE_A, A_AND_B], [gi.call(DGETDRV), gi.call(DSETDRV, ("w", DRIVE_A))]), THE_FREE)
    c_too = road((first, opened), ([DRIVE_A, A_B_AND_C, A_B_AND_C, NO_ERROR, _long(EFILNF)],
                                   [gi.call(DGETDRV), gi.call(DSETDRV, ("w", DRIVE_A)), gi.call(DSETDRV, ("w", DRIVE_C)),
                                    gi.call(DSETPATH, ("l", ROOT_OF_C)), gi.call(FOPEN, ("l", NAME_OF_C), ("w", 0))]), THE_FREE)
    return {
        "the drive map's word is 0": (blank, {}),
        "the drive map's HIGH word alone is set (a word test)": (
            road(([BLOCK, DRIVE_A, 0x0003_0000], blank[1][:3]), THE_FREE), {}),
        "the disk is not usable": (road(([BLOCK, DRIVE_A, A_AND_B], blank[1][:3]), THE_FREE), {"usable": 0}),
        "no file on the drive, and no C:": (no_c, {}),
        "no file on the drive, and the second map's bit 18 alone would be a C: (a word test, ARGUMENT CLASS: no GEMDOS answers it)": (
            road((first, opened), ([DRIVE_A, A_AND_B | 1 << DRIVE_C << aes.HIGH_WORD_SHIFT], no_c[1][-3:-1]), THE_FREE), {}),
        "no file on the drive, nor on C:": (c_too, {}),
    }


NO_FILE = _no_file_cases()
# The devices a no-file case is run with: neither is what the ROM's default INF asks ((its pair & 3) + 1), so a reader
# that acted on the default's `#E` line would change the device — and with a change pending it would rewrite the line.
NO_FILE_STATES = {"no change pending": {"device": 4}, "a change pending": {"device": 4, "change_pending": 1}}
# THE SHELL'S BUFFER BEFORE A NO-FILE CASE: not the snapshot's — that IS the ROM's default (the boot read no file), so
# the default laid over it would show nothing — but a text of the case's own, with a screen line of its own too.
OTHER_TEXT = (b"#Q other\r\n#E 9B 17\r\n" * (BYTES // 20 + 1))[:BYTES]
OTHER_BUFFER = {aes.AES_SHELL_GEM_BUFFER: OTHER_TEXT}
DEFAULT_INF_BYTES = gi.default_inf_bytes(BASE_IMAGE)


@pytest.mark.parametrize("state", NO_FILE_STATES)
@pytest.mark.parametrize("label", NO_FILE)
def test_argument_class_with_no_file_read_the_rom_s_default_goes_to_the_shell_s_buffer_and_no_line_is_acted_on(label, state):
    """THE `read` GATE ($fda4d2): the block is the shell's buffer's copy WITH THE ROM'S OWN INF OVER ITS HEAD (rom_ram's
    part 3, as long as the part is), the shell's buffer the block's copy, the answer 0 — and the two device words are
    as they were, though the default holds a `#E` line of its own and the text behind it another."""
    (answers, made), machine = NO_FILE[label]
    staged = {**machine, **NO_FILE_STATES[state]}
    result = gi.run_reader(answers, pokes=OTHER_BUFFER, **staged)
    assert result.answer() == NOT_READ and gi.calls(result) == made
    block = block_after(result)
    assert 0 < DEFAULT_INF_BYTES < BYTES
    assert block[:DEFAULT_INF_BYTES] == SHELL_BUFFER_BEFORE[:DEFAULT_INF_BYTES] != OTHER_TEXT[:DEFAULT_INF_BYTES], (
        "the ROM's default — what the boot's own reader left the snapshot, which read no file either")
    assert block[DEFAULT_INF_BYTES:] == OTHER_TEXT[DEFAULT_INF_BYTES:] and shell_buffer_after(result) == block
    assert b"#E " in block[:DEFAULT_INF_BYTES], "the ROM's default INF has a screen line: a reader that acted on it would show"
    assert (result.word(gi.RESTYPE), result.word(gi.RSCHANGE)) == (staged["device"], staged.get("change_pending", 0))
    assert guards_after(result) == (UNTOUCHED_GUARD, UNTOUCHED_GUARD)


def test_the_default_s_own_screen_line_asks_another_device_than_the_no_file_cases_run_with():
    """...WHICH IS WHAT MAKES THAT A TEST: the default's `#E` line's second pair, read as the reader would, asks a
    device the no-file cases do not run with."""
    default = SHELL_BUFFER_BEFORE[:DEFAULT_INF_BYTES]
    pair = int(default[default.index(b"#E") + 1 + GEMINIT["INF_SECOND_PAIR"]:][:2], 16)
    asked = (pair & GEMINIT["INF_PAIR_DEVICE_BITS"]) + 1
    assert all(state["device"] != asked for state in NO_FILE_STATES.values())


def test_argument_class_a_c_without_the_file_is_left_the_current_drive():
    """BEHAVIOUR (c): the retry sets the drive to C: ($fda468) and nothing sets it back where C:'s open fails too —
    the last Dsetdrv of the run is C:'s."""
    (answers, made), machine = NO_FILE["no file on the drive, nor on C:"]
    result = gi.run_reader(answers, **machine)
    set_drives = [frame for function, frame in gi.calls(result) if function == DSETDRV]
    assert set_drives[-1] == gi.call(DSETDRV, ("w", DRIVE_C))[1]
    assert made[-1][0] == MFREE and made[-2][0] == FOPEN


def test_argument_class_with_no_c_the_glue_s_verdict_is_set_by_hand():
    """`move.w #1,$98ec` ($fda486): isdrive's own two calls cleared the verdict the failed open left — the reader
    puts it back, and reads no file through the handle of an open that failed."""
    (answers, made), machine = NO_FILE["no file on the drive, and no C:"]
    result = gi.run_reader(answers, **machine)
    assert FREAD not in [function for function, _frame in gi.calls(result)]
    assert result.word(aes.AES_DOS_ERR) == 0, "...and the free's own verdict is what is left"


# ---- a file is read ---------------------------------------------------------------------------------------------------------
PLAIN = b"#a000000\r\n#b001000\r\n#d                                             \r\n"
SCREEN_LINE = b"#E 9B %s\r\n"


def with_pair(pair, before=PLAIN, after=b"#W 00 00 0C 01 1D 0E 08 @\r\n"):
    return before + SCREEN_LINE % pair + after


def pair_at(text, nth=0):
    """Where the `nth` screen line's second pair lies in `text`."""
    at = -1
    for _ in range(nth + 1):
        at = text.index(b"#E", at + 1)
    return at + 1 + GEMINIT["INF_SECOND_PAIR"]


def test_argument_class_a_file_with_no_screen_line_is_read_into_the_shell_s_buffer_whole():
    answers, made = read_road(PLAIN)
    result = gi.run_reader(answers, PLAIN)
    assert result.answer() == READ and gi.calls(result) == made
    assert block_after(result) == expected_block(PLAIN) == shell_buffer_after(result)
    assert (result.word(gi.RESTYPE), result.word(gi.RSCHANGE)) == (DEVICE_IN_USE, 0)


def test_argument_class_the_seven_sites_the_reader_s_calls_park_are_the_words_after_its_line_f_calls():
    """THE RETURN SITES, each at ITS call (the ledger's parked longword), on the longest road — the C: retry that
    reads: the drive asked, the root, C: set, C:'s root, the close, the drive back, the block freed."""
    first, opened = to_the_open(handle=EFILNF)
    retry = ([DRIVE_A, A_B_AND_C, A_B_AND_C, NO_ERROR, HANDLE],
             [gi.call(DGETDRV), gi.call(DSETDRV, ("w", DRIVE_A)), gi.call(DSETDRV, ("w", DRIVE_C)),
              gi.call(DSETPATH, ("l", ROOT_OF_C)), gi.call(FOPEN, ("l", NAME_OF_C), ("w", 0))])
    answers, made = road((first, opened), retry, the_read(len(PLAIN)), THE_FREE)
    result = gi.run_reader(answers, PLAIN)
    assert result.answer() == READ and gi.calls(result) == made and len(made) == gi.CALLS_RECORDED - 1
    sites = [dos for dos, _trap in gi.parked(result)]
    by_call = {3: addrs.AES_READ_INF_GDRV_RETURN, 4: addrs.AES_READ_INF_CHDIR_RETURN, 8: addrs.AES_READ_INF_SDRV_C_RETURN,
               9: addrs.AES_READ_INF_CHDIR_OF_C_RETURN, 12: addrs.AES_READ_INF_CLOSE_RETURN,
               13: addrs.AES_READ_INF_SDRV_BACK_RETURN, 14: addrs.AES_READ_INF_FREE_RETURN}
    assert {nth: sites[nth] for nth in by_call} == by_call
    for site in by_call.values():
        assert aes.line_f_target(case.word_in(BASE_IMAGE, site - aes.WORD_BYTES)) is not None, f"${site:x} follows no Line-F call"


@pytest.mark.parametrize("drive, handle", ((DRIVE_B, 7), (0x1234_0001, 0x0001_0007)),
                         ids=("drive B:, handle 7", "a high word on each answer: the reader keeps the WORD"))
def test_argument_class_the_drive_and_the_handle_are_kept_as_words(drive, handle):
    """`move.w d0,-8(a6)` / `move.w d0,d6` ($fda43e, $fda456): the drive set back and the handle read and closed are
    the answers' low words."""
    answers, made = read_road(PLAIN, drive=drive, handle=handle)
    result = gi.run_reader(answers, PLAIN, handle=handle & aes.WORD_MASK)
    assert result.answer() == READ and gi.calls(result) == made


# The second pair's cases with NO CHANGE PENDING: `(the pair's two characters, the device in use, the device asked,
# the answer)`. The device asked is (pair & 3) + 1: bit 2 and every higher one are dropped.
ASKS = {
    "the pair asks the device in use": (b"11", 2, 2, NOT_READ),
    "it asks another": (b"11", 3, 2, READ),
    "its bit 2 is no part of the device (16 asks 3, not 7)": (b"16", 3, 3, NOT_READ),
    "...nor are its high bits (FC asks 1)": (b"FC", 2, 1, READ),
    "an unset pair (ff -> -1) asks 4": (b"FF", 2, 4, READ),
    "no hex digits at all: 0, which asks 1": (b"zz", 1, 1, NOT_READ),
}


@pytest.mark.parametrize("label", ASKS)
def test_argument_class_the_screen_line_s_second_pair_asks_for_a_device(label):
    """NO CHANGE PENDING ($fda528..$fda544): (pair & 3) + 1 is handed app_reschange — the device word and the change
    word set where it differs, the answer 0 where it does not — and the text is not touched."""
    pair, device, asked, answer = ASKS[label]
    text = with_pair(pair)
    answers, made = read_road(text)
    result = gi.run_reader(answers, text, device=device)
    assert result.answer() == answer and gi.calls(result) == made
    assert (result.word(gi.RESTYPE), result.word(gi.RSCHANGE)) == (asked, int(asked != device))
    assert block_after(result) == expected_block(text) == shell_buffer_after(result)


def test_argument_class_only_the_first_screen_line_is_acted_on_where_no_change_is_pending():
    text = with_pair(b"11", after=SCREEN_LINE % b"12")
    answers, _made = read_road(text)
    result = gi.run_reader(answers, text, device=4)
    assert (result.answer(), result.word(gi.RESTYPE)) == (READ, 2), "the second line's 3 was not asked"


@pytest.mark.parametrize("device", (1, 2, 3, 0x12, 0x22), ids=lambda device: f"device {device:#x}" + (
    ", ARGUMENT CLASS (no device of the machine's): the WHOLE word is ORed in" if device > 4 else ""))
def test_argument_class_with_a_change_pending_the_pair_is_rewritten_with_the_device_in_use(device):
    """A CHANGE PENDING ($fda50e..$fda526): the pair's high digit kept, its low the device in use less one, as two
    hex digits and a blank — the device word and the change word as they were, the answer 1. THE WHOLE WORD of
    `device - 1` is ORed in (`$fda51e or.w d0,(sp)`): `$12` cannot tell that from its low nibble (`$90 | $11` and
    `$90 | $01` are one byte), `$22` can (`$b1`)."""
    text = with_pair(b"9A")
    answers, _made = read_road(text)
    result = gi.run_reader(answers, text, device=device, change_pending=1)
    rewritten = bytearray(expected_block(text))
    rewritten[pair_at(text):pair_at(text) + 3] = b"%02X " % ((0x90 | (device - 1)) & 0xFF)
    assert result.answer() == READ and block_after(result) == bytes(rewritten) == shell_buffer_after(result)
    assert (result.word(gi.RESTYPE), result.word(gi.RSCHANGE)) == (device, 1)


def test_argument_class_with_a_change_pending_every_screen_line_is_rewritten():
    """THE CURSOR STAYS ON THE PAIR (scan_2's answer is dropped, `$fda502`): the scan goes on from the pair just
    rewritten and a second `#E` line is rewritten like the first."""
    text = with_pair(b"11", after=SCREEN_LINE % b"F0" + b"#Z\r\n")
    answers, _made = read_road(text)
    result = gi.run_reader(answers, text, device=3, change_pending=1)
    after = block_after(result)
    assert (after[pair_at(text, 0):][:3], after[pair_at(text, 1):][:3]) == (b"12 ", b"F2 ")
    assert result.answer() == READ


def test_argument_class_a_mark_that_is_no_screen_line_is_stepped_over_and_a_double_mark_is_one():
    """`#` then anything but `E` ($fda4f2..$fda4f8): the byte behind the mark is looked at again as itself — so `##E`
    is a screen line, and `#e` is not."""
    text = b"#e 00 00\r\n##E 9B 12\r\n"
    answers, _made = read_road(text)
    result = gi.run_reader(answers, text, device=1)
    assert (result.answer(), result.word(gi.RESTYPE)) == (READ, 3)


# ---- behaviour (b): where the text is ended ---------------------------------------------------------------------------------
def test_argument_class_a_whole_block_s_read_puts_the_nul_one_byte_past_the_block():
    text = (PLAIN * (gi.INF_BUFFER_BYTES // len(PLAIN) + 1))[:BYTES]
    answers, _made = read_road(text)
    result = gi.run_reader(answers, text)
    below, above = guards_after(result)
    assert above == b"\0" + UNTOUCHED_GUARD[1:] and below == UNTOUCHED_GUARD
    assert block_after(result) == text == shell_buffer_after(result)


def test_argument_class_a_read_that_fails_puts_the_nul_below_the_block_and_the_shell_s_own_text_is_scanned():
    """THE READ'S VERDICT IS NOT ASKED ($fda4a4): a failed read's count — a negative WORD — ends "the text" below the
    block, the answer is 1 all the same, and what is scanned is what sh_get copied: the desk's own INF, whose `#E`
    line is acted on."""
    answers, made = read_road(b"", count=EIHNDL)
    result = gi.run_reader(answers, None, device=4)
    below, above = guards_after(result)
    assert below == UNTOUCHED_GUARD[:EIHNDL] + b"\0" + UNTOUCHED_GUARD[EIHNDL + 1:] and above == UNTOUCHED_GUARD
    assert gi.calls(result) == made and block_after(result) == SHELL_BUFFER_BEFORE
    line = SHELL_BUFFER_BEFORE.index(b"#E")
    asked = (int(SHELL_BUFFER_BEFORE[line + 1 + GEMINIT["INF_SECOND_PAIR"]:][:2], 16) & GEMINIT["INF_PAIR_DEVICE_BITS"]) + 1
    assert asked != 4 and (result.answer(), result.word(gi.RESTYPE), result.word(gi.RSCHANGE)) == (READ, asked, 1)


def test_argument_class_a_read_that_answers_no_byte_ends_the_text_at_the_block_s_first_byte_and_nothing_is_scanned():
    """A READ ANSWERING 0, ARGUMENT CLASS (an empty DESKTOP.INF: no kept disk holds one): the NUL goes to the block's
    first byte, the answer is 1 all the same, and no line is acted on — the shell's buffer's own `#E` line lies behind
    the NUL, unread."""
    answers, made = read_road(b"", count=0)
    result = gi.run_reader(answers, b"", device=4)
    assert gi.calls(result) == made and guards_after(result) == (UNTOUCHED_GUARD, UNTOUCHED_GUARD)
    assert block_after(result) == b"\0" + SHELL_BUFFER_BEFORE[1:] == shell_buffer_after(result)
    assert b"#E" in SHELL_BUFFER_BEFORE and (result.answer(), result.word(gi.RESTYPE), result.word(gi.RSCHANGE)) == (READ, 4, 0)


def test_argument_class_the_count_is_a_signed_word_of_the_read_s_answer():
    """`movea.w d7,a1` ($fda4de): a count with a high word ends the text by its low word alone."""
    text = PLAIN[:9]
    answers, _made = read_road(text, count=0x0001_0000 | len(text))
    result = gi.run_reader(answers, text)
    assert block_after(result) == expected_block(text) and guards_after(result) == (UNTOUCHED_GUARD, UNTOUCHED_GUARD)


def test_argument_class_a_screen_line_at_the_text_s_end_steps_over_the_nul():
    """THE FIVE BYTES ARE SKIPPED UNREAD ($fda4fa): `#E` as the text's last two bytes — the pair read is what the
    block held behind the NUL (the shell's buffer's copy), and is acted on."""
    text = b"#a\r\n#E"
    behind = bytearray(SHELL_BUFFER_BEFORE)
    pair = len(text) - 1 + GEMINIT["INF_SECOND_PAIR"]
    behind[pair:pair + 2] = b"12"
    answers, _made = read_road(text)
    result = gi.run_reader(answers, text, device=1, pokes={aes.AES_SHELL_GEM_BUFFER: bytes(behind)})
    assert (result.answer(), result.word(gi.RESTYPE)) == (READ, 3)


# ---- the harness's own reds ----------------------------------------------------------------------------------------------
def test_the_differential_sees_a_file_laid_on_the_rom_s_shore_alone(monkeypatch):
    """THE LAID TEXT IS ON THE SURFACE: with the host's twin of the read answering and laying nothing — the plain
    recorder's — the two blocks differ, and the differential says so."""
    plain_twin = aes_gemdosif.Recorder.twin(gi.RECORDER, FREAD)
    monkeypatch.setitem(gi.HANDLERS, gemdos.rom_handler(FREAD), plain_twin)
    answers, _made = read_road(PLAIN)
    with pytest.raises(AssertionError, match="shell_gem_buffer"):
        gi.run_reader(answers, PLAIN)


def test_the_longest_road_fits_the_ledger_and_a_script_too_long_is_refused():
    with pytest.raises(AssertionError, match="too few"):
        gi.RECORDER.script.staged(b"\0" * aes.LONG_BYTES * (gi.CALLS_RECORDED + 1))
