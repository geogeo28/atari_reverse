"""THE FORM LIBRARY's event-free half (`src/aes/fmlib.c`): the alert string split and the alert tree laid out (gemfmalt),
the fields and the default button found and a form key handled (gemfmlib), and the keyboard queue fm_do flushes.

    fm_strbrk(tree, str, obj, &idx, &n, &maxlen)   from str[*idx] to the section's ']': each line into ob_spec of obj,
            obj+1, ... — '|' ends one; a delimiter doubled is itself; past 31 characters the line ends and the rest is
            skipped to its delimiter; the byte after a line's end decides whether the section goes on.
            *idx := past the ']'; *n := lines; *maxlen := the longest line's length
    fm_parse(tree, str, &icon, &nmsg, &mlen, &nbut, &blen)   *icon := str[1] - '0'; idx := 4; strbrk(obj 2); idx++;
            strbrk(obj 7); ++*blen
    fm_build(tree, icon, nmsg, mlen, nbut, blen)   the alert tree laid out in cells, every object unlinked then the
            icon, the lines and the buttons added under the root, the buttons SELECTABLE|EXIT, the last LASTOB too
    find_obj(tree, start, which)   FORWARD / BACKWARD from start to an EDITABLE, DEFLT from the root to a DEFAULT, any
            other `which` the first EDITABLE from the root; the walk ends at LASTOB or below 0; start if none
    fm_inifld(tree, fld)           fld, or for 0 find_obj(tree, 0, FORWARD)
    fm_keybd(tree, obj, &key, &new)  table $fefa30: shift-Tab/Up BACKWARD, Tab/Down FORWARD, Return/Enter DEFLT from
            the root — *key := 0, *new := find_obj; a DEFAULT found: ob_change(SELECTED, drawn), answers 0; else 1
    dq(queue)                      count--, the front key taken (the front round the ring of 8), answered
    fq()                           while gl_cda's queue holds a key, dq it

THE DATA IS THE SNAPSHOT's: every alert string of both resources (the AES's own error alerts and the desk's), the AES's
alert tree (its line and button buffers as the last alert left them), every dialog of both resources for the field
walks and the keys. fm_build is handed what the ROM's own fm_parse of each alert answers, over the tree that parse
left. A key queue is the event layer's: PD0 running as the scheduler makes it (`aes_event.pd0_running`), keys in the
keyboard's ring (`aes_event.keys`) polled into its queue by the head of every ev_multi — chkkbd, then forker. A
string or tree an application hands in (form_alert's string, an objc tree) is staged in the window.
"""
import functools
import signal

import pytest

from harness import BASE_IMAGE, addrs, make_image

import aes
import aes_event
import aes_objdraw as od
import case
import test_aes_grwait as grwait
import test_aes_ob_draw as obdraw
import vdi
import vdi_helpers
import vdi_screen
from case import merge_pokes

L, W, IMAGE = vdi.LONG_ARG, vdi.WORD_ARG, vdi.IMAGE_ARG
STRBRK, PARSE, BUILD = "AES_ROM_FM_STRBRK", "AES_ROM_FM_PARSE", "AES_ROM_FM_BUILD"
FIND_OBJ, INIFLD, KEYBD = "AES_ROM_FIND_OBJ", "AES_ROM_FM_INIFLD", "AES_ROM_FM_KEYBD"
DQ, FQ = "AES_ROM_DQ", "AES_ROM_FQ"
SIGNATURES = {
    STRBRK: (None, (IMAGE, L, L, W, L, L, L)),
    PARSE: (None, (IMAGE, L, L, L, L, L, L, L)),
    BUILD: (None, (IMAGE, L, W, W, W, W, W)),
    FIND_OBJ: (aes.WORD_ANSWER, (IMAGE, L, W, W)),
    INIFLD: (aes.WORD_ANSWER, (IMAGE, L, W)),
    KEYBD: (aes.WORD_ANSWER, (IMAGE, L, W, L, L)),
    DQ: (aes.WORD_ANSWER, (IMAGE, L)),
    FQ: (None, (IMAGE,)),
}
for _name, (_restype, _argtypes) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, _argtypes)

FM = aes.header_constants("fmlib.h")
FORWARD, BACKWARD, DEFLT = FM["FMD_FORWARD"], FM["FMD_BACKWARD"], FM["FMD_DEFLT"]
LINE_CHARACTERS = FM["ALERT_LINE_CHARACTERS"]
FIRST_LINE, FIRST_BUTTON = FM["ALERT_FIRST_LINE"], FM["ALERT_FIRST_BUTTON"]
FIRST_LINE_AT = FM["ALERT_FIRST_LINE_AT"]
GO_ON, DONE = FM["FM_KEYBD_GO_ON"], FM["FM_KEYBD_DONE"]   # fm_keybd's answer: the form goes on, or is done
TREES = od.trees()
ALERT_TREE = TREES["alert"]
SELECTOR = TREES["selector"]
PATH_FIELD, NAME_FIELD = 2, 3           # the selector's two fields: its path and its selection
EDITABLE, DEFAULT = od.FLAG_BITS["EDITABLE"], od.FLAG_BITS["DEFAULT"]
# fm_build's last button: SELECTABLE | EXIT, and the tree's end (`aes/fmlib.h` ALERT_LAST_BUTTON_FLAGS).
LAST_BUTTON_FLAGS = od.FLAG_BITS["SELECTABLE"] | od.FLAG_BITS["EXIT"] | aes.OB_FLAG_LASTOB
NUL = b"\x00"


# ---- the answers, the strings and trees a case hands in, and the C's frames: staged STALE ----------------------------
# fm_parse's five answer words (the locals of fm_alert's frame it is handed); fm_strbrk's three; fm_keybd's key and
# object words (fm_do's locals) — each its own word, so a store into the wrong one shows.
ANSWER_WORDS = 10
(ICON_AT, LINES_AT, LINE_LENGTH_AT, BUTTONS_AT, BUTTON_LENGTH_AT, INDEX_AT, COUNT_AT, LONGEST_AT, KEY_AT,
 NEXT_AT) = (aes.RECTS_AT + word * aes.WORD_BYTES for word in range(ANSWER_WORDS))
STALE_ANSWERS = {aes.RECTS_AT: vdi.pack_words(*[aes.STALE_WORD] * ANSWER_WORDS)}
STALE_SLOTS = merge_pokes(aes.stale_host_slot("AES_FM_PARSE_INDEX"), aes.stale_host_slot("AES_FM_BUILD_RECTS"))
STRING_AT = aes.BLOCKS_AT                          # an application's alert string...
STRING_BYTES = 0x40                                # ...and its room
LINES_BUFFER_AT = STRING_AT + STRING_BYTES         # an application's tree's line buffers
# The most bytes a section writes from a line's or a button's buffer: the cap's characters and the NUL (a button's
# buffer is 11 bytes, so a longer button runs into the next one's).
CAPPED_TEXT_BYTES = LINE_CHARACTERS + 1


def machine(onto=None):
    """An event-free routine's machine (`aes.leaf_machine`): the answers and the C's frames stale, `onto` over it."""
    return aes.leaf_machine(onto=merge_pokes(STALE_ANSWERS, STALE_SLOTS, onto))


def run(name, arguments, pokes=None, **kwargs):
    return aes.run_function(name, arguments, machine(pokes), **kwargs)


def answer_words(result, *places):
    return [aes.signed(result.word(at)) for at in places]


# ---- the alert strings of both resources ------------------------------------------------------------------------------
def alert_strings(application_global=None):
    """`{index: address}`: every free string of a resource (the AES's own when None) that is an alert, "[n][..][..]"."""
    header = aes.resource_header(application_global=application_global)
    table = header + case.word_in(BASE_IMAGE, header + aes.RSH_FRSTR)
    found = {}
    for index in range(case.word_in(BASE_IMAGE, header + aes.RSH_NSTRING)):
        at = case.long_in(BASE_IMAGE, table + index * aes.LONG_BYTES)
        if BASE_IMAGE[at] == ord("["):
            found[index] = at
    return found


def string_at(at, image=BASE_IMAGE):
    return bytes(image[at:image.index(0, at)])


ALERTS = {**{f"AES string {index}": at for index, at in alert_strings().items()},
          **{f"desk string {index}": at for index, at in alert_strings(aes.AES_DESK_APP_GLOBAL).items()}}


def _declare_case_fields():
    """The spans these cases read outside the window: the alert strings and the alert tree's line and button buffers
    (which fm_strbrk writes)."""
    for name, at in ALERTS.items():
        aes.declare_case_field(at, len(string_at(at)) + 1, f"the {name}, an alert")
    first = od.object_long(ALERT_TREE, FIRST_LINE, "SPEC")
    last = od.object_long(ALERT_TREE, FM["ALERT_OBJECTS"] - 1, "SPEC")
    aes.declare_case_field(first, last + CAPPED_TEXT_BYTES - first, "the alert tree's line and button buffers")


_declare_case_fields()


# ---- fm_parse over every real alert, and fm_strbrk under it -----------------------------------------------------------
PARSE_ANSWERS = (ICON_AT, LINES_AT, LINE_LENGTH_AT, BUTTONS_AT, BUTTON_LENGTH_AT)


def parse(string, tree=ALERT_TREE, pokes=None, **kwargs):
    return run(PARSE, (tree, string, *PARSE_ANSWERS), pokes, **kwargs)


def sections(text):
    """The message lines and the buttons of a well-formed alert, as the AES writes them: no delimiter doubled, each line
    within the cap."""
    _icon, message, buttons = text[1:-1].split(b"][")
    return message.split(b"|"), buttons.split(b"|")


@pytest.mark.parametrize("name", sorted(ALERTS))
def test_fm_parse_over_each_real_alert(name):
    """The icon, the lines and the buttons — each line in its object's buffer — and the longest of each."""
    text = string_at(ALERTS[name])
    lines, buttons = sections(text)
    result = parse(ALERTS[name])
    assert answer_words(result, *PARSE_ANSWERS) == [text[1] - ord("0"), len(lines), max(map(len, lines)), len(buttons),
                                                     max(map(len, buttons)) + 1]
    for index, line in enumerate(lines + buttons):
        at = od.object_long(ALERT_TREE, (FIRST_LINE + index) if index < len(lines) else
                            FIRST_BUTTON + index - len(lines), "SPEC")
        assert string_at(at, result.final) == line


# UNPOISONED WHERE MEASURED: the index word fm_strbrk reads first is one it stores last, so the attribution pass hands
# both runs its inverse — a walk from tens of bytes below the string through the tree band's zeros, whose lines run on
# through the ob_specs of the objects past the tree until one points ABOVE RAM, where the C refuses the store by name
# (`m68k_idioms.h`) and the oracle's is lost. Measured case by case, poison forced on: the cases that pass it are left
# POISONED, and only those it ends that way (`steers=True`) opt out. Every answer word and line buffer is staged with
# bytes the run changes (stale words, the last alert's text), so a store the C skipped still shows on the plain compare.
INDEX_STEERS_THE_PASS = {"poison": False}


def strbrk(text, object=FIRST_LINE, start=FIRST_LINE_AT, tree=ALERT_TREE, pokes=None, **kwargs):
    """fm_strbrk of an application's string `text` (in the blocks band), from `start`, into `tree`'s `object` on."""
    staged = merge_pokes({STRING_AT: text + NUL}, {INDEX_AT: vdi.pack_words(start)}, pokes)
    return run_strbrk((tree, STRING_AT, object, INDEX_AT, COUNT_AT, LONGEST_AT), staged, **kwargs)


def run_strbrk(arguments, pokes, *, steers=False, **kwargs):
    """fm_strbrk called directly: POISONED, or not where its inverted index is measured to steer the pass off RAM
    (`steers`, above). fm_parse's cases run it POISONED under them, its index there a frame local the pass never
    inverts."""
    return run(STRBRK, arguments, pokes, **(INDEX_STEERS_THE_PASS if steers else {}), **kwargs)


def line_of(result, object, tree=ALERT_TREE):
    return string_at(case.long_in(result.final, tree + object * aes.OB_BYTES + aes.OB_SPEC), result.final)


LONG = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"       # 36 characters: past the cap


# (text, the lines, the three answers or None, whether its index steers the poisoned pass off RAM)
@pytest.mark.parametrize("text, lines, answers, steers", (
    (b"[1][" + LONG + b"|two][OK]", [LONG[:LINE_CHARACTERS], b"two"], (len(b"[1][" + LONG + b"|two]"), 2,
                                                                       LINE_CHARACTERS), True),
    (b"[1][a||b|c]]d][OK]", [b"a|b", b"c]d"], None, True),
    (b"[1][" + LONG[:LINE_CHARACTERS] + b"||x][OK]", [LONG[:LINE_CHARACTERS], b"", b"x"], None, True),
    (b"[1][" + LONG + b"]][OK]", [LONG[:LINE_CHARACTERS]], None, True),
    (b"[1][" + LONG[:LINE_CHARACTERS - 2] + b"]]x][OK]", [LONG[:LINE_CHARACTERS - 2] + b"]x"], None, True),
    (b"[1][" + LONG[:LINE_CHARACTERS - 1] + b"]]x][OK]", [LONG[:LINE_CHARACTERS - 1] + b"]"], None, True),
    (b"[1][]x][OK]", [b""], None, False),
    (b"[1][ab\x00]x", [b"ab"], None, False),
    (b"[1][a|b|c|d|e|f][OK]", [b"a", b"b", b"c", b"d", b"e", b"f"], None, True),
), ids=("a line past the cap: 31 kept, the rest skipped", "doubled delimiters: each itself, once",
        "a doubled '|' right at the cap: its second a delimiter, an empty line after",
        "a doubled ']' past the cap: it ends the section", "a doubled ']' two short of the cap: itself",
        "a doubled ']' one short of the cap: itself, the next character capped", "an empty section",
        "a NUL inside: the byte after it decides",
        "six lines: one past the alert's five"))
def test_fm_strbrk(text, lines, answers, steers):
    result = strbrk(text, steers=steers)
    assert [line_of(result, FIRST_LINE + index) for index in range(len(lines))] == lines
    count = answer_words(result, COUNT_AT)[0]
    assert count == len(lines)
    if answers is not None:
        assert tuple(answer_words(result, INDEX_AT, COUNT_AT, LONGEST_AT)) == answers


def test_fm_strbrk_s_index_past_a_capped_line_points_at_its_delimiter_s_follower():
    """Past the cap, the skip stops ON the delimiter; the index then steps past it and the one after is read."""
    result = strbrk(b"[1][" + LONG + b"][OK]", steers=True)
    assert answer_words(result, INDEX_AT)[0] == len(b"[1][" + LONG + b"]")


# ORDER. The three answers are stored last, in turn: laid over one word, the longest is left; laid over the first line's
# own buffer, the index lands after the line is written.
def test_fm_strbrk_stores_index_count_and_longest_in_that_order():
    result = run_strbrk((ALERT_TREE, STRING_AT, FIRST_LINE, INDEX_AT, INDEX_AT, INDEX_AT),
                        {STRING_AT: b"[1][abc|de][OK]" + NUL, INDEX_AT: vdi.pack_words(FIRST_LINE_AT)})
    assert answer_words(result, INDEX_AT) == [3]


def test_fm_strbrk_stores_the_count_after_the_index():
    """The index and the count laid over one word, the longest apart: the count is left."""
    result = run_strbrk((ALERT_TREE, STRING_AT, FIRST_LINE, INDEX_AT, INDEX_AT, LONGEST_AT),
                        {STRING_AT: b"[1][abc|de][OK]" + NUL, INDEX_AT: vdi.pack_words(FIRST_LINE_AT)})
    assert answer_words(result, INDEX_AT) == [2]


def test_fm_strbrk_a_single_separator_before_the_end_starts_one_more_line():
    """"a|]": the '|' is followed by the ']' — the separator, not its follower, is what the next line is tested by, so
    an empty line follows before the section ends."""
    result = strbrk(b"[1][a|][OK]")
    assert answer_words(result, COUNT_AT) == [2] and line_of(result, FIRST_LINE + 1) == b""


def test_fm_strbrk_ends_a_capped_line_before_it_skips():
    """An application's line buffer lying over its own string so that the capped line's NUL lands on the '|' after it:
    the NUL is stored before the skip reads the string, so the skip runs past it to the ']' — one line, not two."""
    text = b"[1][" + LONG + b"|xy][OK]"
    separator = text.index(b"|")
    line = STRING_AT + separator - LINE_CHARACTERS
    pokes = merge_pokes(application_tree({FIRST_LINE: line}),
                        {STRING_AT: text + NUL, INDEX_AT: vdi.pack_words(FIRST_LINE_AT)})
    result = run_strbrk((aes.TREE_AT, STRING_AT, FIRST_LINE, INDEX_AT, COUNT_AT, LONGEST_AT), pokes, steers=True)
    assert answer_words(result, COUNT_AT) == [1]


def test_fm_strbrk_stores_the_index_after_the_lines():
    line = od.object_long(ALERT_TREE, FIRST_LINE, "SPEC")
    result = run_strbrk((ALERT_TREE, STRING_AT, FIRST_LINE, line, COUNT_AT, LONGEST_AT),
                        {STRING_AT: b"[1][abcdef][OK]" + NUL, line: vdi.pack_words(FIRST_LINE_AT)}, steers=True)
    assert result.word(line) == len(b"[1][abcdef]")


APPLICATION_LINE_BYTES = 0x18          # an application's line buffers: nine in the blocks band past its string


def application_buffer(index):
    return LINES_BUFFER_AT + (index - 1) * APPLICATION_LINE_BYTES


def application_tree(specs):
    """An application's alert tree: ten objects, object n's ob_spec `specs[n]` (its own line buffer by default)."""
    objects = [aes.node(None)] + [aes.node(0, SPEC=specs.get(index, application_buffer(index)))
                                  for index in range(1, FM["ALERT_OBJECTS"])]
    return aes.tree_pokes(objects)


def test_fm_parse_reads_the_buttons_after_the_lines_are_written():
    """An application's tree whose first line lies over its own string's button section: the message is written there
    first, and the buttons read back are the message's ("XY"), the string's NUL and the byte after it ending them."""
    text = b"[1][XY][AB]" + NUL + bytes([FM["ALERT_SECTION_END"]])
    buttons_at = STRING_AT + text.index(b"AB")
    pokes = merge_pokes(application_tree({FIRST_LINE: buttons_at}), {STRING_AT: text})
    result = parse(STRING_AT, aes.TREE_AT, pokes)
    assert answer_words(result, BUTTONS_AT) == [2] and string_at(application_buffer(FIRST_BUTTON), result.final) == b"XY"


def test_fm_strbrk_reads_each_line_s_buffer_when_the_line_begins():
    """The first line written over the second line's ob_spec (its low three bytes): the second line goes where the
    first one's text points."""
    redirected = LINES_BUFFER_AT + (FM["ALERT_OBJECTS"] - 1) * APPLICATION_LINE_BYTES
    address = redirected.to_bytes(aes.LONG_BYTES, "big")
    assert address[0] == 0 and 0 not in address[1:]
    second_spec = aes.TREE_AT + (FIRST_LINE + 1) * aes.OB_BYTES + aes.OB_SPEC
    pokes = merge_pokes(application_tree({FIRST_LINE: second_spec + 1}),
                        {STRING_AT: b"[1][" + address[1:] + b"|xy][OK]" + NUL,
                         INDEX_AT: vdi.pack_words(FIRST_LINE_AT)})
    result = run_strbrk((aes.TREE_AT, STRING_AT, FIRST_LINE, INDEX_AT, COUNT_AT, LONGEST_AT), pokes)
    assert result.after(redirected, 3) == b"xy" + NUL


def test_fm_strbrk_signed_index():
    """The index a SIGNED word: -2 reads two bytes below the string."""
    pokes = {STRING_AT - 2: b"ab]" + NUL, INDEX_AT: vdi.pack_words(-2 & 0xFFFF)}
    result = run_strbrk((ALERT_TREE, STRING_AT, FIRST_LINE, INDEX_AT, COUNT_AT, LONGEST_AT), pokes)
    assert answer_words(result, INDEX_AT, COUNT_AT) == [1, 1]


def test_fm_parse_and_fm_strbrk_put_their_pointers_on_the_bus():
    at = ALERTS["AES string 19"]
    run(PARSE, (ALERT_TREE | aes.BUS_TAG, at | aes.BUS_TAG, *(place | aes.BUS_TAG for place in PARSE_ANSWERS)))
    run_strbrk((ALERT_TREE | aes.BUS_TAG, STRING_AT | aes.BUS_TAG, FIRST_LINE, INDEX_AT | aes.BUS_TAG,
                COUNT_AT | aes.BUS_TAG, LONGEST_AT | aes.BUS_TAG),
               {STRING_AT: b"[1][ab|c][OK]" + NUL, INDEX_AT: vdi.pack_words(FIRST_LINE_AT)}, steers=True)


def test_fm_parse_of_an_application_s_alert_past_the_tree():
    """form_alert's string with six lines and four buttons: the sixth line goes into the first button's buffer, the
    fourth button into object 10 — the tree after the alert's (the ROM caps neither)."""
    text = b"[3][one|two|three|four|five|six][A|B|C|D]"
    result = parse(STRING_AT, pokes={STRING_AT: text + NUL})
    assert answer_words(result, LINES_AT, BUTTONS_AT) == [6, 4]


# PAST OBJECT 10, A LINE STORED ABOVE RAM. Object 11 — an application's fifth button, or its tenth message line — is AES
# tree 2's object 1, whose ob_spec is a G_BOX colour word read as the line's address: ABOVE RAM ($ff1100). The ROM's
# store is lost there (the oracle drops it; an ST loses it or takes a bus error) where the host image's would land, so
# the C refuses that store BY NAME (`m68k_idioms.h`) — pinned in a child. Up to object 10 (a colour word of $1143, low
# RAM: the four buttons above) the ROM's run is reproduced byte for byte.
PAST_RAM_OBJECT = FIRST_BUTTON + 4
LONG_BYTES_BELOW_THE_TOP = addrs.ST_RAM_BYTES - aes.LONG_BYTES - aes.WORD_BYTES   # a line's buffer clear of the last word
TOP_OF_RAM_REFUSAL = ("recreate: not reconstructed: a store at or above the top of RAM (ST_RAM_BYTES): the oracle drops "
                      "it, an ST loses it or takes a bus error")
# (the string, the answer word that counts the section, its count as the ROM's run answers it)
PAST_RAM = {"five buttons": (b"[3][one][A|B|C|D|E]", BUTTONS_AT, 5),
            "ten lines": (b"[1][1|2|3|4|5|6|7|8|9|10][OK]", LINES_AT, 10)}


def test_the_alert_tree_s_object_11_points_above_ram():
    assert od.object_long(ALERT_TREE, PAST_RAM_OBJECT, "SPEC") >= addrs.ST_RAM_BYTES


@pytest.mark.parametrize("text, count_at, count", PAST_RAM.values(), ids=PAST_RAM)
def test_fm_parse_refuses_a_line_stored_above_ram(text, count_at, count):
    """The ROM's own fm_parse runs on past the store it loses, counting every line; the C halts at that store."""
    pokes = machine({STRING_AT: text + NUL})
    arguments = (ALERT_TREE, STRING_AT, *PARSE_ANSWERS)
    _staged, final, _writes = od.rom_run(PARSE, arguments, pokes)
    assert aes.signed(case.word_in(final, count_at)) == count
    returncode, stderr, _image = vdi_helpers.refusal_over(
        "aes_fm_parse", pokes, arguments=tuple(("ctypes.c_uint32", hex(value)) for value in arguments), read_back=False)
    assert returncode == -signal.SIGABRT and TOP_OF_RAM_REFUSAL in stderr.splitlines(), (returncode, stderr)


def test_the_screen_lies_below_the_top_of_ram():
    """The bound the refusal draws leaves every store the console and the VDI make in RAM."""
    assert case.long_in(BASE_IMAGE, addrs.SYSVAR_V_BAS_AD) + vdi_screen.SCREEN_BYTES <= addrs.ST_RAM_BYTES


# ...and the bound itself, a byte at a time and a word at a time: an application's tree whose first line's buffer is
# the last bytes of RAM (fm_strbrk's line, then its NUL), and fm_strbrk's answer word laid in RAM's last word.
ONE_LETTER = b"[1][a][OK]"
LAST_WORD = addrs.ST_RAM_BYTES - aes.WORD_BYTES


def strbrk_at_the_top(line, longest_at=LONGEST_AT):
    """fm_strbrk of ONE_LETTER over that tree: `(arguments, pokes, returncode, stderr)` — the last two its C's run in a
    child."""
    pokes = merge_pokes(application_tree({FIRST_LINE: line}),
                        {STRING_AT: ONE_LETTER + NUL, INDEX_AT: vdi.pack_words(FIRST_LINE_AT)})
    arguments = (aes.TREE_AT, STRING_AT, FIRST_LINE, INDEX_AT, COUNT_AT, longest_at)
    types = ("ctypes.c_uint32", "ctypes.c_uint32", "ctypes.c_int16", "ctypes.c_uint32", "ctypes.c_uint32", "ctypes.c_uint32")
    returncode, stderr, _image = vdi_helpers.refusal_over(
        "aes_fm_strbrk", machine(pokes), arguments=tuple(zip(types, map(hex, arguments))), read_back=False)
    return arguments, pokes, returncode, stderr


@pytest.mark.parametrize("line, longest_at", ((LAST_WORD, LONGEST_AT), (LONG_BYTES_BELOW_THE_TOP, LAST_WORD)),
                         ids=("a line in RAM's last two bytes", "the longest's word RAM's last"))
def test_fm_strbrk_stores_up_to_the_top_of_ram(line, longest_at):
    """No refusal (in a child first, so a bound one byte short is a failed assertion, not a dead worker), then the
    differential."""
    arguments, pokes, returncode, stderr = strbrk_at_the_top(line, longest_at)
    assert returncode == 0, stderr
    result = run_strbrk(arguments, pokes)
    assert result.after(line, len(b"a" + NUL)) == b"a" + NUL


@pytest.mark.parametrize("line, longest_at", ((addrs.ST_RAM_BYTES - 1, LONGEST_AT), (LONG_BYTES_BELOW_THE_TOP,
                                                                                      addrs.ST_RAM_BYTES)),
                         ids=("a line's NUL on the first byte past RAM", "the longest's word past RAM"))
def test_fm_strbrk_refuses_a_store_past_the_top_of_ram(line, longest_at):
    _arguments, _pokes, returncode, stderr = strbrk_at_the_top(line, longest_at)
    assert returncode == -signal.SIGABRT and TOP_OF_RAM_REFUSAL in stderr.splitlines(), (returncode, stderr)


def test_fm_parse_an_icon_digit_is_signed():
    """str[1] sign-extended: a byte $c0 gives -112."""
    result = parse(STRING_AT, pokes={STRING_AT: b"[\xc0][a][OK]" + NUL})
    assert answer_words(result, ICON_AT) == [0xC0 - 0x100 - ord("0")]


def test_fm_parse_reads_the_button_length_back_to_count_it_one_more():
    """The longest button's answer word laid over the lines' answer: the first fm_strbrk stores the line count there,
    the second the longest button's length over it, which is then read back and counted one more."""
    result = run(PARSE, (ALERT_TREE, STRING_AT, ICON_AT, LINES_AT, LINE_LENGTH_AT, BUTTONS_AT, LINES_AT),
                 {STRING_AT: b"[1][a|b|c][OKAY]" + NUL})
    assert answer_words(result, LINES_AT) == [len(b"OKAY") + 1]


# ---- fm_build over what the ROM's own fm_parse answers ----------------------------------------------------------------
@functools.cache
def parsed(at):
    """The machine the ROM's own fm_parse of the alert string at `at` leaves (continued from) and its five answers."""
    staged, final, writes = od.rom_run(PARSE, (ALERT_TREE, at, *PARSE_ANSWERS), machine())
    return case.continued_from(staged, final, writes), [aes.signed(case.word_in(final, place)) for place in PARSE_ANSWERS]


def build(at, pokes=None, **kwargs):
    onto, (icon, lines, line_length, buttons, button_length) = parsed(at)
    return aes.run_function(BUILD, (ALERT_TREE, int(icon != 0), lines, line_length, buttons, button_length),
                            merge_pokes(onto, STALE_SLOTS, pokes), **kwargs)


@pytest.mark.parametrize("name", sorted(ALERTS))
def test_fm_build_over_each_real_alert(name):
    """The tree relinked: the root's children the icon (when there is one), the lines, the buttons; the last button
    the tree's end."""
    result = build(ALERTS[name])
    _onto, (icon, lines, _length, buttons, _width) = parsed(ALERTS[name])
    last = FIRST_BUTTON + buttons - 1
    assert result.object(ALERT_TREE, 0)["TAIL"] == last
    assert result.object(ALERT_TREE, last)["FLAGS"] == LAST_BUTTON_FLAGS
    assert (result.object(ALERT_TREE, 0)["HEAD"] == FM["ALERT_ICON_OBJECT"]) == (icon != 0)


@functools.cache
def application_parsed(text):
    """...and an application's string (form_alert's), staged in the blocks band."""
    staged, final, writes = od.rom_run(PARSE, (ALERT_TREE, STRING_AT, *PARSE_ANSWERS), machine({STRING_AT: text + NUL}))
    return case.continued_from(staged, final, writes), [aes.signed(case.word_in(final, place)) for place in PARSE_ANSWERS]


@pytest.mark.parametrize("text", (
    b"[0][no icon|two lines][OK]",
    b"[1][" + LONG + b"][A]",
    b"[3][one|two|three|four|five|six][A|B|C|D]",
    b"[2][a][" + b"W" * 12 + b"|" + b"X" * 12 + b"|" + b"Y" * 12 + b"]",
), ids=("no icon", "one capped line, one button", "six lines and four buttons: past the tree",
        "three buttons wider than the lines"))
def test_fm_build_of_an_application_s_alert(text):
    onto, (icon, lines, line_length, buttons, button_length) = application_parsed(text)
    aes.run_function(BUILD, (ALERT_TREE, int(icon != 0), lines, line_length, buttons, button_length),
                     merge_pokes(onto, STALE_SLOTS))


def test_fm_build_puts_the_tree_on_the_bus():
    onto, (icon, lines, line_length, buttons, button_length) = parsed(ALERTS["AES string 19"])
    aes.run_function(BUILD, (ALERT_TREE | aes.BUS_TAG, int(icon != 0), lines, line_length, buttons, button_length),
                     merge_pokes(onto, STALE_SLOTS))


# ---- find_obj and fm_inifld over every dialog of both resources --------------------------------------------------------
def dialogs():
    """`{name: tree}`: every tree of the snapshot that ends on a LASTOB object — the dialogs, the selector, the alert."""
    found = {}
    for name, tree in TREES.items():
        try:
            aes.tree_length(tree)
        except AssertionError:
            continue
        found[name] = tree
    return found


DIALOGS = dialogs()


def flagged(tree, mask):
    return [index for index in range(aes.tree_length(tree))
            if aes.read_field(BASE_IMAGE, "OB", "FLAGS", tree + index * aes.OB_BYTES) & mask]


def find_obj_cases():
    """(name, start, which) for every dialog: FORWARD from the root and from each field, BACKWARD from each field and
    from the last object, DEFLT, and a `which` none of the three names (3, -1)."""
    cases = []
    for name, tree in sorted(DIALOGS.items()):
        last = aes.tree_length(tree) - 1
        for start in sorted({0, *flagged(tree, EDITABLE)}):
            cases.append((name, start, FORWARD))
        for start in sorted({last, *flagged(tree, EDITABLE)}):
            cases.append((name, start, BACKWARD))
        cases += [(name, 0, DEFLT), (name, 5, 3), (name, 1, -1)]
    return cases


@pytest.mark.parametrize("name, start, which", find_obj_cases())
def test_find_obj(name, start, which):
    run(FIND_OBJ, (DIALOGS[name], start, which))


def test_find_obj_answers_the_start_when_nothing_is_found():
    """The desk's tree 2 has no EDITABLE: FORWARD from 3 walks to its LASTOB and answers 3."""
    result = run(FIND_OBJ, (TREES["desk tree 2"], 3, FORWARD))
    assert result.answer() == 3


def test_find_obj_backward_stops_below_the_root():
    """BACKWARD from the selector's path (2) to the root and below: no EDITABLE before it, the walk ends at -1."""
    result = run(FIND_OBJ, (SELECTOR, PATH_FIELD, BACKWARD))
    assert result.answer() == PATH_FIELD


def test_find_obj_starts_from_a_negative_object_backward():
    """BACKWARD from 0: object -1, the walk never starts."""
    assert run(FIND_OBJ, (SELECTOR, 0, BACKWARD)).answer() == 0


def test_find_obj_tests_lastob_after_the_flag():
    """The selector's last object (24) made EDITABLE: it is found before its LASTOB ends the walk."""
    last = aes.tree_length(SELECTOR) - 1
    flags = aes.read_object(BASE_IMAGE, SELECTOR, last)["FLAGS"]
    result = run(FIND_OBJ, (SELECTOR, grwait.OK, FORWARD), od.flags_pokes(SELECTOR, last, flags | EDITABLE))
    assert result.answer() == last


def test_find_obj_and_fm_inifld_put_the_tree_on_the_bus():
    assert run(FIND_OBJ, (SELECTOR | aes.BUS_TAG, 0, FORWARD)).answer() == PATH_FIELD
    assert run(INIFLD, (SELECTOR | aes.BUS_TAG, 0)).answer() == PATH_FIELD


@pytest.mark.parametrize("name", sorted(DIALOGS))
def test_fm_inifld_of_field_0_is_the_first_editable(name):
    tree = DIALOGS[name]
    result = run(INIFLD, (tree, 0))
    assert result.answer() == (flagged(tree, EDITABLE) or [0])[0]


@pytest.mark.parametrize("field", (3, -1, 0x7FFF), ids=("a field", "-1", "$7fff"))
def test_fm_inifld_keeps_a_field_it_is_handed(field):
    assert run(INIFLD, (SELECTOR, field)).answer() == field


# ---- fm_keybd over the dialogs: every key it knows, and one it does not ----------------------------------------------
KEYS = {"shift-Tab": FM["FM_KEY_BACKTAB"], "Tab": FM["FM_KEY_TAB"], "Return": FM["FM_KEY_RETURN"],
        "Up": FM["FM_KEY_UP"], "Down": FM["FM_KEY_DOWN"], "Enter": FM["FM_KEY_ENTER"]}
OTHER_KEYS = {"Undo": 0x6100, "'a'": 0x1E61, "no key": 0, "Escape": 0x011B}
DOORS = obdraw.doors()                 # ob_change's redraw: the VDI's door and just_draw's by value


def keybd_machine(key, pokes=None, key_at=KEY_AT):
    """fm_keybd's machine as fm_do runs it: just_draw's (the cursor hidden, the IBM font cached), the key in fm_do's
    word, the object word and ob_change's frames stale."""
    return merge_pokes(od.machine(), STALE_ANSWERS, obdraw.STALE_SLOTS, {key_at: vdi.pack_words(key)}, pokes)


def keybd(tree, object, key, pokes=None, *, key_at=KEY_AT, next_at=NEXT_AT, **kwargs):
    return aes.run_function(KEYBD, (tree, object, key_at, next_at), keybd_machine(key, pokes, key_at), hook=DOORS,
                            **kwargs)


def keybd_cases():
    cases = []
    for name, tree in sorted(DIALOGS.items()):
        fields = flagged(tree, EDITABLE)
        start = fields[0] if fields else 0
        cases += [(name, start, key) for key in KEYS]
        if len(fields) > 1:
            cases += [(name, fields[-1], key) for key in ("Tab", "shift-Tab")]
    return cases


@pytest.mark.parametrize("name, object, key", keybd_cases())
def test_fm_keybd(name, object, key):
    """A known key is taken (its word cleared) and the object it reaches stored; Return and Enter select and draw the
    default button and end the form when there is one."""
    tree = DIALOGS[name]
    result = keybd(tree, object, KEYS[key])
    assert result.word(KEY_AT) == 0
    defaults = flagged(tree, DEFAULT)
    if key in ("Return", "Enter"):
        assert answer_words(result, NEXT_AT) == [defaults[0] if defaults else 0]
        assert result.answer() == (DONE if defaults else GO_ON)
    else:
        assert result.answer() == GO_ON


@pytest.mark.parametrize("key", sorted(OTHER_KEYS))
def test_fm_keybd_leaves_any_other_key(key):
    result = keybd(SELECTOR, PATH_FIELD, OTHER_KEYS[key])
    assert result.answer() == GO_ON and result.word(KEY_AT) == OTHER_KEYS[key] and result.word(NEXT_AT) == aes.STALE_WORD


def test_fm_keybd_a_key_with_its_high_bit_is_not_a_tab():
    """$8f09: the key's word sign-extended to the table's longs — no match, though its low bits are Tab's."""
    assert keybd(SELECTOR, PATH_FIELD, 0x8F09).answer() == GO_ON


def test_fm_keybd_return_searches_from_the_root():
    """Return from the selector's selection: the default (OK) is found from the root, whatever the field."""
    assert answer_words(keybd(SELECTOR, NAME_FIELD, KEYS["Return"]), NEXT_AT) == [grwait.OK]


def test_fm_keybd_return_with_no_default_goes_on():
    """An application's dialog with no DEFAULT button (the selector's OK made a plain exit): Return is taken, the walk
    answers the root (0) and nothing is selected — the form goes on."""
    flags = aes.read_object(BASE_IMAGE, SELECTOR, grwait.OK)["FLAGS"]
    result = keybd(SELECTOR, PATH_FIELD, KEYS["Return"], od.flags_pokes(SELECTOR, grwait.OK, flags & ~DEFAULT))
    assert result.answer() == GO_ON and result.word(KEY_AT) == 0 and answer_words(result, NEXT_AT) == [0]


def test_fm_keybd_clears_the_key_before_it_searches():
    """The key's word laid over the next object's flags (an application's tree whose object 3 carries Tab's word as its
    flags, EDITABLE among them): cleared first, object 3 is no longer a field and the walk goes on to 4."""
    objects = [aes.node(None)] + [aes.node(0) for _ in range(3)] + [aes.node(0, FLAGS=EDITABLE | aes.OB_FLAG_LASTOB)]
    pokes = merge_pokes(aes.tree_pokes(objects), aes.object_pokes(aes.TREE_AT, 3, FLAGS=KEYS["Tab"]))
    key_at = aes.TREE_AT + 3 * aes.OB_BYTES + aes.OB_FLAGS
    result = keybd(aes.TREE_AT, 2, KEYS["Tab"], pokes, key_at=key_at)
    assert answer_words(result, NEXT_AT) == [4]


def test_fm_keybd_reads_the_default_back_through_the_object_word():
    """The object word laid over the key's: both stores land in one word, and the default selected is the one read
    back — the second store's."""
    result = keybd(SELECTOR, PATH_FIELD, KEYS["Return"], next_at=KEY_AT)
    assert result.answer() == DONE and answer_words(result, KEY_AT) == [grwait.OK]


def test_fm_keybd_puts_its_pointers_on_the_bus():
    aes.run_function(KEYBD, (SELECTOR | aes.BUS_TAG, PATH_FIELD, KEY_AT | aes.BUS_TAG, NEXT_AT | aes.BUS_TAG),
                     keybd_machine(KEYS["Return"]), hook=DOORS)


# ---- dq and fq over the running process's key queue, as the event layer fills it --------------------------------------
KEY_A, KEY_B, KEY_C = 0x1E, 0x30, 0x2E                 # make codes: a, b, c


def polled(machine_, *scancodes):
    """`machine_` with `scancodes` typed (`aes_event.keys`) and each polled into the keyboard owner's queue as the head
    of every ev_multi polls one ($fe69c8): the ROM's chkkbd, then its forker (`aes_event.derived`)."""
    for scancode in scancodes:
        machine_ = merge_pokes(machine_, aes_event.keys(scancode, onto=machine_))
        for routine in (addrs.AES_ROM_CHKKBD, addrs.AES_ROM_FORKER):
            written, _final, _regs = aes_event.derived(routine, machine_)
            machine_ = merge_pokes(machine_, written)
    return machine_


def flushed(machine_):
    """...and the queue flushed by the ROM's own fq, as fm_do's start flushes it."""
    written, _final, _regs = aes_event.derived(addrs.AES_ROM_FQ, machine_)
    return merge_pokes(machine_, written)


@functools.cache
def queued(count, flushed_first=0):
    """PD0 running with `count` keys queued — after `flushed_first` keys were queued and flushed, which moves the
    ring's front on by as many."""
    machine_ = aes_event.pd0_running()
    if flushed_first:
        machine_ = flushed(polled(machine_, *[KEY_A] * flushed_first))
    return polled(machine_, *([KEY_A, KEY_B, KEY_C] * 3)[:count])


# The running process's queue: gl_cda as switchto leaves it for PD0, at the CDA's queue.
RUNNING_QUEUE = case.long_in(make_image(aes_event.pd0_running()), aes.AES_GL_CDA) + FM["CDA_KEY_QUEUE"]
aes.declare_case_field(RUNNING_QUEUE, FM["CQUEUE_BYTES"], "the running process's key queue")
QUEUE_COUNTS = (("none queued", 0, 0), ("one", 1, 0), ("three", 3, 0), ("a full queue", 8, 0),
                ("the front round the ring", 2, 7))


# UNPOISONED, measured: the count fq loops on is the word it leaves 0, so the attribution pass hands both runs $ffff —
# 65,535 keys dequeued, past the run's cap. The count and the front are staged by the event layer with values the run
# changes, so a store the C skipped shows on the plain compare.
COUNT_STEERS_THE_PASS = {"poison": False}


@pytest.mark.parametrize("count, flushed_first", [row[1:] for row in QUEUE_COUNTS], ids=[row[0] for row in QUEUE_COUNTS])
def test_fq(count, flushed_first):
    result = run(FQ, (), queued(count, flushed_first), **COUNT_STEERS_THE_PASS)
    assert result.word(RUNNING_QUEUE + FM["CQUEUE_COUNT"]) == 0


# THE KEYBOARD'S OWNER IS NOT ALWAYS THE RUNNING PROCESS: chkkbd queues into gl_kowner's queue, fq flushes gl_cda's. The
# keyboard handed to the screen manager the way fm_own hands it to a dialog's process — the ROM's own ct_chgown(PD1,
# gl_rfull) — while PD0 runs (an accessory's alert while the application holds the keyboard has this shape), then keys
# polled into PD1's queue by the ROM's chkkbd and forker.
KOWNER = aes.AES_GL_KOWNER
OWNER_QUEUE = case.long_in(BASE_IMAGE, aes.SCREEN_MANAGER_PD + aes.PD_CDA) + FM["CDA_KEY_QUEUE"]
aes.declare_case_field(OWNER_QUEUE, FM["CQUEUE_BYTES"], "the screen manager's key queue")
KEYS_TYPED_FOR_THE_OWNER = 3


def keyboard_handed_to_the_screen_manager(machine_):
    written, _final, _regs = aes_event.derived(
        addrs.AES_ROM_CT_CHGOWN, machine_, frame=aes_event.frame_of(("l", aes.SCREEN_MANAGER_PD), ("l", aes.AES_GL_RFULL)))
    return merge_pokes(machine_, written)


@pytest.mark.parametrize("own", (0, 2), ids=("none of its own", "two of its own"))
def test_fq_flushes_the_running_process_s_queue_not_the_keyboard_owner_s(own):
    """PD0 running with `own` keys queued, the keyboard then the screen manager's, and keys polled into ITS queue (as
    many as the ROM's own poll leaves there): fq empties PD0's (gl_cda's) and leaves PD1's as it was."""
    machine_ = polled(keyboard_handed_to_the_screen_manager(queued(own)), *[KEY_B] * KEYS_TYPED_FOR_THE_OWNER)
    before = make_image(machine_)
    queued_for_the_owner = case.word_in(before, OWNER_QUEUE + FM["CQUEUE_COUNT"])
    assert case.long_in(before, KOWNER) == aes.SCREEN_MANAGER_PD and queued_for_the_owner
    result = run(FQ, (), machine_, **COUNT_STEERS_THE_PASS)
    assert result.word(RUNNING_QUEUE + FM["CQUEUE_COUNT"]) == 0
    assert result.word(OWNER_QUEUE + FM["CQUEUE_COUNT"]) == queued_for_the_owner


def test_dq_puts_the_queue_on_the_bus():
    run(DQ, (RUNNING_QUEUE | aes.BUS_TAG,), queued(3))


@pytest.mark.parametrize("count, flushed_first", [row[1:] for row in QUEUE_COUNTS[1:]],
                         ids=[row[0] for row in QUEUE_COUNTS[1:]])
def test_dq(count, flushed_first):
    """The front key answered: 'a' (its ASCII low, its scan code high), whatever came before."""
    result = run(DQ, (RUNNING_QUEUE,), queued(count, flushed_first))
    assert result.answer() == KEY_A << 8 | ord("a")


# ---- the registry: Tier 3's rows (the worst realistic one of each routine measured, `make bench`) -----------------------
# Measured and left out, none any routine's worst: fm_strbrk of an empty message 0.83, fm_parse of one 0.77, fm_build of
# one line and one button with no icon 0.45, fq of one key 0.26.
def register(label, name, arguments, pokes, **kwargs):
    aes.register(label, name, arguments, machine(pokes), **kwargs)


def _register_rows():
    longest, shortest = max(ALERTS.values(), key=lambda at: len(string_at(at))), ALERTS["AES string 18"]
    for label, at in (("the longest alert", longest), ("the shortest alert", shortest)):
        register(label, PARSE, (ALERT_TREE, at, *PARSE_ANSWERS), None)
        register(f"{label}'s message", STRBRK, (ALERT_TREE, at, FIRST_LINE, INDEX_AT, COUNT_AT, LONGEST_AT),
                 {INDEX_AT: vdi.pack_words(FIRST_LINE_AT)})
        onto, (icon, lines, line_length, buttons, button_length) = parsed(at)
        aes.register(label, BUILD, (ALERT_TREE, int(icon != 0), lines, line_length, buttons, button_length),
                     merge_pokes(onto, STALE_SLOTS))
    register("a line past the cap", STRBRK, (ALERT_TREE, STRING_AT, FIRST_LINE, INDEX_AT, COUNT_AT, LONGEST_AT),
             {STRING_AT: b"[1][" + LONG + b"][OK]" + NUL, INDEX_AT: vdi.pack_words(FIRST_LINE_AT)})
    for label, tree, start, which in (("FORWARD, found next", SELECTOR, PATH_FIELD, FORWARD),
                                      ("BACKWARD, from the selector's last", SELECTOR, aes.tree_length(SELECTOR) - 1,
                                       BACKWARD),
                                      ("DEFLT, the desk's longest dialog", TREES["desk tree 13"], 0, DEFLT),
                                      ("FORWARD, none to the end", TREES["desk tree 13"], 0, FORWARD)):
        register(label, FIND_OBJ, (tree, start, which), None)
    register("field 0", INIFLD, (SELECTOR, 0), None)
    register("a field", INIFLD, (SELECTOR, NAME_FIELD), None)
    for label, key in (("Return, the default drawn", KEYS["Return"]), ("Tab", KEYS["Tab"]),
                       ("a key it does not move by", OTHER_KEYS["Undo"])):
        aes.register(label, KEYBD, (SELECTOR, PATH_FIELD, KEY_AT, NEXT_AT), keybd_machine(key), hook=DOORS)
    # ...and each through its call word: verified, unpriced.
    at = ALERTS["AES string 19"]
    register("an alert", PARSE, (ALERT_TREE, at, *PARSE_ANSWERS), None, through_line_f=True)
    register("an alert's message", STRBRK, (ALERT_TREE, at, FIRST_LINE, INDEX_AT, COUNT_AT, LONGEST_AT),
             {INDEX_AT: vdi.pack_words(FIRST_LINE_AT)}, through_line_f=True)
    onto, (icon, lines, line_length, buttons, button_length) = parsed(at)
    aes.register("an alert", BUILD, (ALERT_TREE, int(icon != 0), lines, line_length, buttons, button_length),
                 merge_pokes(onto, STALE_SLOTS), through_line_f=True)
    register("FORWARD", FIND_OBJ, (SELECTOR, PATH_FIELD, FORWARD), None, through_line_f=True)
    register("field 0", INIFLD, (SELECTOR, 0), None, through_line_f=True)
    aes.register("Return", KEYBD, (SELECTOR, PATH_FIELD, KEY_AT, NEXT_AT), keybd_machine(KEYS["Return"]), hook=DOORS,
                 through_line_f=True)
    register("three keys", DQ, (RUNNING_QUEUE,), queued(3), through_line_f=True)
    register("three keys", FQ, (), queued(3), through_line_f=True)
    register("one key", DQ, (RUNNING_QUEUE,), queued(1))
    register("the front round the ring", DQ, (RUNNING_QUEUE,), queued(2, 7))
    register("a full queue", FQ, (), queued(8))
    register("an empty queue", FQ, (), queued(0))


_register_rows()
