"""The object editor's TEXT helpers (`src/aes/obedit.c`; ob_edit itself, curfld and pxl_rect are
`test_aes_ob_edit.py`, which declares every signature):

    ob_getsp(tree, obj, ted)        flags := ob_flags; spec := ob_spec; INDIRECT (flags' high byte, bit 0): spec := *spec;
                                    lbcopy(ted, spec, 28)
    scan_to_end(tmplt, idx, chr)    while (*p && *p != chr) if (*p++ == '_') idx++; answers idx
    ins_char(str, pos, chr, room)   n := strlen(str); str[n..pos+1] := str[n-1..pos]; str[pos] := chr;
                                    str[room > n + 1 ? n + 1 : room - 1] := NUL
    find_pos(tmplt, idx)            past idx placeholders (on past the NUL if need be), then on to the next '_' or NUL
    instr(chr, set)                 1 when chr lies in the set: single characters and "a..z" ranges, SIGNED bytes
    check(&chr, valid)              table $fefb10: 'X' 1; 'x' 1, *chr upcased; the others instr(*chr, rs_str(set)) —
                                    rs_str first — upcased but for '9', 'a', 'n'; anything else 0
    ob_stfn(idx, &start, &finish)   *start := find_pos(tmplt, idx); *finish := find_pos(tmplt, strlen(raw))
    ob_delit(idx)                   raw[idx]: strcpy(&raw[idx+1] down over &raw[idx]), 0; else 1

REAL DATA: the snapshot's own templates, validation strings and raw texts (`test_aes_ob_edit.EDITABLES` and every
other FTEXT/FBOXTEXT of its trees), the AES resource's own validation sets (rs_str 4..12). The editor's buffers
(AES_RAWSTR, the ODD AES_TMPLT) are staged as ob_edit's lstcpys leave them; a case that hands a pointer of its own
stages its string in the blocks band.
"""
import pytest

from harness import BASE_IMAGE

import aes
import aes_objdraw as od
import case
import vdi
from case import merge_pokes
from test_aes_ob_edit import (DESK_NAME, DESK_SIZE, INDIRECT, LONGEST_TEMPLATE, LONGEST_TEXT, NUL, PATH, SELECTION,
                              SELECTOR, TIME, TREES, field_text, indirect_pokes, tedinfo_of)

GETSP, SCAN_TO_END, INS_CHAR = "AES_ROM_OB_GETSP", "AES_ROM_SCAN_TO_END", "AES_ROM_INS_CHAR"
FIND_POS, INSTR, CHECK = "AES_ROM_FIND_POS", "AES_ROM_INSTR", "AES_ROM_CHECK"
OB_STFN, OB_DELIT = "AES_ROM_OB_STFN", "AES_ROM_OB_DELIT"
RAW, TMPLT, VALSTR = aes.AES_RAWSTR, aes.AES_TMPLT, aes.AES_VALSTR
BUFFER_BYTES = aes.AES_TEXT_BUFFER_BYTES
STRING_AT = aes.BLOCKS_AT                           # a string a case hands by its own pointer
TEDINFO_AT = aes.BLOCKS_AT + 0x100                  # ob_getsp's copy, when not AES_EDBLK
ANSWERS_AT = aes.RECTS_AT                           # ob_stfn's start and finish, check's character
STALE = bytes([vdi.FILL])


def run(name, arguments, pokes=None, **kwargs):
    return aes.run_function(name, arguments, aes.leaf_machine(onto=pokes), **kwargs)


def buffers(raw=None, tmplt=None):
    """The editor's raw text and template as ob_edit's lstcpys leave them, each followed by stale bytes."""
    pokes = {}
    for at, text in ((RAW, raw), (TMPLT, tmplt)):
        if text is not None:
            pokes[at] = text + NUL + STALE * (BUFFER_BYTES - len(text) - 1)
    return pokes


def text_fields():
    """`{name: (tree, index)}`: every TEXT-like object of the snapshot's trees whose template is a string."""
    found = {}
    for name, tree in TREES.items():
        for index in od.link_order(tree):
            if od.object_type(tree, index) in (aes.G_FTEXT, aes.G_FBOXTEXT):
                found[f"{name} {index}"] = (tree, index)
    return found


def validation_set(string):
    """The AES resource's free string `string` (STNUM..STLANUM), as rs_str copies it."""
    header = aes.resource_header()
    table = header + case.word_in(BASE_IMAGE, header + aes.RSH_FRSTR)
    at = case.long_in(BASE_IMAGE, table + string * aes.LONG_BYTES)
    return bytes(BASE_IMAGE[at:BASE_IMAGE.index(0, at)])


FIELDS = text_fields()
TEMPLATES = {name: field_text(*field, "PTMPLT") for name, field in FIELDS.items()}


# ---- ob_getsp -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("field", (PATH, DESK_SIZE, (TREES["desk tree 12"], 2)), ids=("the path", "a size", "a name"))
def test_ob_getsp_copies_the_tedinfo(field):
    result = run(GETSP, (*field, aes.AES_EDBLK), {aes.AES_EDBLK: STALE * aes.TE_BYTES})
    at = tedinfo_of(*field)
    assert result.after(aes.AES_EDBLK, aes.TE_BYTES) == bytes(BASE_IMAGE[at:at + aes.TE_BYTES])


def test_ob_getsp_follows_an_indirect_spec():
    result = run(GETSP, (*SELECTION, TEDINFO_AT), indirect_pokes(*SELECTION))
    at = tedinfo_of(*SELECTION)
    assert result.after(TEDINFO_AT, aes.TE_BYTES) == bytes(BASE_IMAGE[at:at + aes.TE_BYTES])


@pytest.mark.parametrize("flags", (0x0001, 0x0200, INDIRECT | 0x0008), ids=("the low byte's bit 0", "the high byte's bit 1",
                                                                            "INDIRECT with EDITABLE"))
def test_only_the_high_byte_s_bit_0_is_indirect(flags):
    """$0001 (SELECTABLE) and $0200 leave the spec the TEDINFO; INDIRECT follows it — through the snapshot's
    longword there, a staged pointer to the TEDINFO."""
    tree, index = SELECTION
    pokes = merge_pokes(od.flags_pokes(tree, index, flags), {aes.BLOCKS_AT: tedinfo_of(tree, index).to_bytes(4, "big")})
    if flags & INDIRECT:
        pokes = merge_pokes(pokes, od.spec_pokes(tree, index, aes.BLOCKS_AT))
    result = run(GETSP, (tree, index, TEDINFO_AT), pokes)
    at = tedinfo_of(tree, index)
    assert result.after(TEDINFO_AT, aes.TE_BYTES) == bytes(BASE_IMAGE[at:at + aes.TE_BYTES])


def test_ob_getsp_puts_its_pointers_on_the_bus():
    """The tree, the copy and an INDIRECT spec's longword each with a top byte."""
    pokes = merge_pokes(od.flags_pokes(*SELECTION, INDIRECT), od.spec_pokes(*SELECTION, aes.BLOCKS_AT | aes.BUS_TAG),
                        {aes.BLOCKS_AT: (tedinfo_of(*SELECTION) | aes.BUS_TAG).to_bytes(4, "big")})
    run(GETSP, (SELECTOR | aes.BUS_TAG, SELECTION[1], TEDINFO_AT | aes.BUS_TAG), pokes)


# ---- scan_to_end ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("template, start, character, expected", (
    (b"________.___", 0, ord("."), 8), (b"________.___", 3, ord("."), 11), (b"__:__ __", 0, ord(":"), 2),
    (b"__:__ __", 1, ord(" "), 5), (b"________.___", 0, ord("|"), 11), (b"", 4, ord("."), 4),
    (b"__/__/__", 0, 0x412F, 2), (b"Name:  ________.___", 0, ord(":"), 0),
), ids=("the dot from 0", "the dot from 3", "the colon", "the blank", "absent: the end", "an empty template",
        "the character's high byte ignored", "a literal before the placeholders"))
def test_scan_to_end(template, start, character, expected):
    result = run(SCAN_TO_END, (STRING_AT, start, character), {STRING_AT: template + NUL})
    assert result.answer() == expected


def test_scan_to_end_puts_the_template_on_the_bus():
    result = run(SCAN_TO_END, (STRING_AT | aes.BUS_TAG, 0, ord(".")), {STRING_AT: b"___.__" + NUL})
    assert result.answer() == 3


def test_scan_to_end_through_its_call_word():
    run(SCAN_TO_END, (TMPLT, 0, ord(".")), buffers(tmplt=b"________.___"), through_line_f=True)


# ---- ins_char ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text, at, character, room, expected", (
    (b"ABCD", 2, ord("x"), 12, b"ABxCD"), (b"ABCD", 4, ord("x"), 12, b"ABCDx"), (b"ABCD", 0, ord("x"), 12, b"xABCD"),
    (b"ABCD", 2, ord("x"), 5, b"ABxC"), (b"ABCD", 2, ord("x"), 6, b"ABxCD"), (b"", 0, ord("x"), 2, b"x"),
    (b"ABCD", 2, 0x4178, 12, b"ABxCD"), (b"ABCD", 2, ord("x"), 0, b"ABxCD"), (b"ABCD", 2, ord("x"), -1, b"ABxCD"),
), ids=("mid", "at the end", "at the start", "the room one short: the last dropped", "the room exact",
        "into an empty one", "the character's high byte ignored", "no room: the NUL a byte BEFORE the string",
        "a negative room, compared SIGNED: the NUL two bytes before"))
def test_ins_char(text, at, character, room, expected):
    result = run(INS_CHAR, (STRING_AT + 1, at, character, room), {STRING_AT: b"#" + text + NUL + STALE * 4})
    assert bytes(result.final[STRING_AT + 1:result.final.index(0, STRING_AT)]) == expected or room <= 0


def test_ins_char_at_a_negative_place_moves_bytes_before_the_string():
    """`at` -2: the loop runs down to -1, storing below the string, and the character lands two bytes before it."""
    run(INS_CHAR, (STRING_AT + 4, -2, ord("x"), 12), {STRING_AT: b"0123ABCD" + NUL})


def test_ins_char_puts_the_string_on_the_bus():
    result = run(INS_CHAR, (STRING_AT | aes.BUS_TAG, 1, ord("x"), 12), {STRING_AT: b"ABCD" + NUL + STALE * 4})
    assert bytes(result.final[STRING_AT:result.final.index(0, STRING_AT)]) == b"AxBCD"


def test_ins_char_through_its_call_word():
    """ob_edit and fs_back call it by `$f858`."""
    run(INS_CHAR, (RAW, 1, ord("x"), 12), buffers(raw=b"AB"), through_line_f=True)


# ---- find_pos ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(TEMPLATES))
@pytest.mark.parametrize("index", (0, 1, 8, 11))
def test_find_pos_over_each_real_template(name, index):
    """Every template the snapshot holds, from the first raw place to past its placeholders: the template is the ODD
    AES_TMPLT, the bytes after it ob_edit's validation copy's stale."""
    run(FIND_POS, (TMPLT, index), buffers(tmplt=TEMPLATES[name]))


@pytest.mark.parametrize("template, index, expected", (
    (b"________.___", 8, 9), (b"________.___", 0, 0), (b"Name:  ________.___", 0, 7), (b"__:__ __", 2, 3),
    (b"__:__ __", 6, 8), (b"no placeholder", 0, 14),
), ids=("over a literal to the extension", "the first", "past the literal head", "past the colon",
        "every placeholder passed: the NUL", "none at all"))
def test_find_pos(template, index, expected):
    result = run(FIND_POS, (TMPLT, index), buffers(tmplt=template))
    assert result.answer() == expected


def test_find_pos_reads_on_past_the_nul_for_a_place_beyond_the_template():
    """Index 6 over "__.__" (four placeholders): the first walk passes the NUL and counts the placeholders of whatever
    follows (here a second string), then stops at the next."""
    result = run(FIND_POS, (STRING_AT, 6), {STRING_AT: b"__.__" + NUL + b"a_b_c_" + NUL})
    assert result.answer() == 11


@pytest.mark.parametrize("index", (-1, -0x8000), ids=("-1", "-32768"))
def test_find_pos_of_a_negative_index_walks_nothing(index):
    result = run(FIND_POS, (TMPLT, index), buffers(tmplt=b"AB__"))
    assert result.answer() == 2


def test_find_pos_puts_the_template_on_the_bus():
    """Index 2: both walks read through the tagged pointer — the second over the literal '.' to the next placeholder."""
    result = run(FIND_POS, (STRING_AT | aes.BUS_TAG, 2), {STRING_AT: b"__.___" + NUL})
    assert result.answer() == 3


def test_find_pos_through_its_call_word():
    run(FIND_POS, (TMPLT, 3), buffers(tmplt=b"________.___"), through_line_f=True)


# ---- instr ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("character, members, expected", (
    (ord("5"), b"0..9", 1), (ord("a"), b"0..9", 0), (ord("*"), b"0..9a..zA..Z\x80..\xff\\?*:._", 1),
    (ord("_"), b"0..9a..zA..Z\x80..\xff\\?*:._", 1), (0xE9, b"a..zA..Z \x80..\xff", 1), (0xC5, b"\xc2..\xdc", 1),
    (ord(" "), b"A..Z \x80", 1), (ord("."), b"A..Z", 0), (ord("."), b".", 1), (ord("Z"), b"A..Z", 1),
    (ord("@"), b"A..Z", 0), (ord("["), b"A..Z", 0), (0x4135, b"0..9", 1), (0, b"0..9", 0), (ord("x"), b"", 0),
), ids=("a digit", "a letter is no digit", "STPATH's '*'", "STPATH's '_'", "an accented letter", "a signed range",
        "a single character after a range", "'.' not a range's", "a lone '.'", "a range's last", "below a range",
        "above a range", "the character's high byte ignored", "NUL", "an empty set"))
def test_instr(character, members, expected):
    result = run(INSTR, (character, STRING_AT), {STRING_AT: members + NUL})
    assert result.answer() == expected


@pytest.mark.parametrize("character, members, expected", (
    (ord("A"), b" ..\xff", 0), (0xE0, b"\x80.. ", 1), (0x7F, b"\x80.. ", 0),
), ids=("$20..$ff is EMPTY signed", "$80..$20 holds $e0", "...but not $7f"))
def test_instr_compares_signed_bytes(character, members, expected):
    result = run(INSTR, (character, STRING_AT), {STRING_AT: members + NUL})
    assert result.answer() == expected


def test_a_range_ending_the_set_reads_on_past_its_nul():
    """"a.." with nothing after: the range's last is the NUL, and the walk goes on past it into the next string."""
    result = run(INSTR, (ord("q"), STRING_AT), {STRING_AT: b"a.." + NUL + b"q" + NUL})
    assert result.answer() == 1


def test_instr_puts_the_set_on_the_bus():
    run(INSTR, (ord("5"), STRING_AT | aes.BUS_TAG), {STRING_AT: b"0..9" + NUL})


def test_instr_through_its_call_word():
    run(INSTR, (ord("5"), STRING_AT), {STRING_AT: b"0..9" + NUL}, through_line_f=True)


# ---- check ---------------------------------------------------------------------------------------------------------
CHARACTER_AT = ANSWERS_AT
VALIDATIONS = {name: chr(getattr(aes, f"VALID_{name}"))
               for name in ("DIGIT", "ALPHA", "FILE", "ALPHANUMERIC", "PATH", "ANY", "LOWER_ALPHA", "LOWER_FILE",
                            "LOWER_ALPHANUMERIC", "LOWER_PATH", "ANY_UPPER")}
TYPED = b"5aZ :*_\xe9|"                             # a digit, both cases, a blank, path punctuation, accented, a bar


@pytest.mark.parametrize("valid", sorted(VALIDATIONS))
@pytest.mark.parametrize("character", list(TYPED), ids=lambda c: f"${c:02x}")
def test_check(valid, character):
    result = run(CHECK, (CHARACTER_AT, ord(VALIDATIONS[valid])), {CHARACTER_AT: bytes([character])})
    assert result.answer() in (0, 1)


@pytest.mark.parametrize("valid", (0, ord("#"), 0x80 | ord("9"), 0x4139, 0x4158, 0x4178),
                         ids=("NUL", "'#'", "$b9", "$4139: '9'", "$4158: 'X'", "$4178: 'x'"))
def test_check_reads_the_validation_character_s_low_byte(valid):
    """No set: 0 — but a WORD whose low byte names one is that one ('9' takes the digit, 'X' and 'x' anything)."""
    result = run(CHECK, (CHARACTER_AT, valid), {CHARACTER_AT: b"5"})
    assert result.answer() == (1 if valid & 0xFF in (ord("9"), ord("X"), ord("x")) else 0)


def test_check_reads_the_character_after_rs_str():
    """The character laid on rs_str's buffer (AES_RS_STRING): rs_str copies the set there first, and the character
    checked is the set's first — '0' of "0..9"."""
    result = run(CHECK, (aes.AES_RS_STRING, ord("9")), {aes.AES_RS_STRING: b"x"})
    assert result.answer() == 1


def test_check_puts_the_character_on_the_bus():
    result = run(CHECK, (CHARACTER_AT | aes.BUS_TAG, ord("F")), {CHARACTER_AT: b"q"})
    assert result.after(CHARACTER_AT, 1) == b"Q"


def test_check_through_its_call_word():
    run(CHECK, (CHARACTER_AT, ord("F")), {CHARACTER_AT: b"q"}, through_line_f=True)


# ---- ob_stfn -------------------------------------------------------------------------------------------------------
STALE_ANSWERS = {ANSWERS_AT: vdi.pack_words(aes.STALE_WORD, aes.STALE_WORD)}


@pytest.mark.parametrize("field, raw, index", ((SELECTION, b"README", 2), (DESK_NAME, b"AUTO", 4), (TIME, b"12", 0),
                                               (PATH, b"", 0)),
                         ids=("the selection", "the desk's name", "a time, right", "an empty path"))
def test_ob_stfn(field, raw, index):
    result = run(OB_STFN, (index, ANSWERS_AT, ANSWERS_AT + 2),
                 merge_pokes(buffers(raw=raw, tmplt=field_text(*field, "PTMPLT")), STALE_ANSWERS))
    assert [aes.signed(result.word(ANSWERS_AT + offset)) for offset in (0, 2)] != [aes.STALE_WORD] * 2


def test_ob_stfn_measures_the_raw_text_after_storing_the_start():
    """The start laid over the raw text's first two bytes: storing it shortens or lengthens the text the finish is
    measured from (start 0: "\\0\\0" — empty)."""
    result = run(OB_STFN, (0, RAW, ANSWERS_AT), buffers(raw=b"ABCD", tmplt=b"________"))
    assert aes.signed(result.word(ANSWERS_AT)) == 0


def test_ob_stfn_with_one_answer_for_both():
    result = run(OB_STFN, (1, ANSWERS_AT, ANSWERS_AT), buffers(raw=b"ABC", tmplt=b"__.__"))
    assert aes.signed(result.word(ANSWERS_AT)) == 4


def test_ob_stfn_puts_its_pointers_on_the_bus_and_through_its_call_word():
    pokes = merge_pokes(buffers(raw=b"AB", tmplt=b"____"), STALE_ANSWERS)
    run(OB_STFN, (1, ANSWERS_AT | aes.BUS_TAG, (ANSWERS_AT + 2) | aes.BUS_TAG), pokes)
    run(OB_STFN, (1, ANSWERS_AT, ANSWERS_AT + 2), pokes, through_line_f=True)


# ---- ob_delit ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("raw, index, answer, expected", (
    (b"ABCD", 1, 0, b"ACD"), (b"ABCD", 3, 0, b"ABC"), (b"ABCD", 4, 1, b"ABCD"), (b"", 0, 1, b""),
    (b"ABCD", 0, 0, b"BCD"),
), ids=("mid", "the last", "at the end: nothing", "an empty text", "the first"))
def test_ob_delit(raw, index, answer, expected):
    result = run(OB_DELIT, (index,), buffers(raw=raw))
    assert result.answer() == answer and bytes(result.final[RAW:result.final.index(0, RAW)]) == expected


def test_ob_delit_at_a_negative_index_deletes_the_byte_before_the_buffer():
    """Index -1: the byte below AES_RAWSTR is tested and, non-zero there, the raw text is copied down over it."""
    run(OB_DELIT, (-1,), merge_pokes(buffers(raw=b"AB"), {RAW - 1: b"\x07"}))


def test_ob_delit_through_its_call_word():
    run(OB_DELIT, (1,), buffers(raw=b"ABC"), through_line_f=True)


# ---- the registry: Tier 3's candidate rows --------------------------------------------------------------------------
PATH_TEMPLATE = field_text(*PATH, "PTMPLT")
LONG_TEXT = b"A:\\GAMES\\ARCADES\\SHOOTERS\\VERTICAL\\*."
NOWHERE = ord("|")                                  # in no validation set, so every set is walked whole
for _label, _field in (("the path", PATH), ("the desk's size", DESK_SIZE)):
    aes.register(_label, GETSP, (*_field, aes.AES_EDBLK), aes.leaf_machine())
aes.register("an INDIRECT selection", GETSP, (*SELECTION, aes.AES_EDBLK), aes.leaf_machine(onto=indirect_pokes(*SELECTION)))
aes.register("the path", GETSP, (*PATH, aes.AES_EDBLK), aes.leaf_machine(), through_line_f=True)
aes.register("the dot, from the head", SCAN_TO_END, (TMPLT, 0, ord(".")), aes.leaf_machine(onto=buffers(tmplt=b"________.___")))
aes.register("absent: the whole path's template", SCAN_TO_END, (TMPLT, 0, ord(".")),
             aes.leaf_machine(onto=buffers(tmplt=PATH_TEMPLATE)))
aes.register("at a long text's head", INS_CHAR, (RAW, 0, ord("x"), len(LONG_TEXT) + 2),
             aes.leaf_machine(onto=buffers(raw=LONG_TEXT)))
aes.register("at its end", INS_CHAR, (RAW, 2, ord("x"), 12), aes.leaf_machine(onto=buffers(raw=b"AB")))
aes.register("the path's last place", FIND_POS, (TMPLT, len(PATH_TEMPLATE)), aes.leaf_machine(onto=buffers(tmplt=PATH_TEMPLATE)))
aes.register("an 80-place template's last place", FIND_POS, (TMPLT, len(LONGEST_TEMPLATE)),
             aes.leaf_machine(onto=buffers(tmplt=LONGEST_TEMPLATE)))
aes.register("the selection's first", FIND_POS, (TMPLT, 0), aes.leaf_machine(onto=buffers(tmplt=b"________.___")))
for _set in (aes.STNUM, aes.STANUM, aes.STPATH, aes.STLANUM):
    aes.register(f"'|' through set {_set}", INSTR, (NOWHERE, STRING_AT),
                 aes.leaf_machine(onto={STRING_AT: validation_set(_set) + NUL}))
for _label, _valid, _character in (("'P' refusing '|'", aes.VALID_PATH, NOWHERE),
                                   ("'N' refusing '|'", aes.VALID_ALPHANUMERIC, NOWHERE),
                                   ("'n' taking 'z'", aes.VALID_LOWER_ALPHANUMERIC, ord("z")),
                                   ("'x' upcasing", aes.VALID_ANY_UPPER, ord("q")), ("'X'", aes.VALID_ANY, ord("q")),
                                   ("an unknown one", ord("#"), ord("q"))):
    aes.register(_label, CHECK, (CHARACTER_AT, _valid), aes.leaf_machine(onto={CHARACTER_AT: bytes([_character])}))
aes.register("'F' taking 'q'", CHECK, (CHARACTER_AT, aes.VALID_FILE), aes.leaf_machine(onto={CHARACTER_AT: b"q"}),
             through_line_f=True)
aes.register("a full path", OB_STFN, (len(LONG_TEXT), ANSWERS_AT, ANSWERS_AT + 2),
             aes.leaf_machine(onto=merge_pokes(buffers(raw=LONG_TEXT, tmplt=PATH_TEMPLATE), STALE_ANSWERS)))
aes.register("an 80-place field, full", OB_STFN, (len(LONGEST_TEXT), ANSWERS_AT, ANSWERS_AT + 2),
             aes.leaf_machine(onto=merge_pokes(buffers(raw=LONGEST_TEXT, tmplt=LONGEST_TEMPLATE), STALE_ANSWERS)))
aes.register("an empty selection", OB_STFN, (0, ANSWERS_AT, ANSWERS_AT + 2),
             aes.leaf_machine(onto=merge_pokes(buffers(raw=b"", tmplt=b"________.___"), STALE_ANSWERS)))
aes.register("a long text's head", OB_DELIT, (0,), aes.leaf_machine(onto=buffers(raw=LONG_TEXT)))
aes.register("at the end", OB_DELIT, (2,), aes.leaf_machine(onto=buffers(raw=b"AB")))
for _name, _arguments, _pokes in ((SCAN_TO_END, (TMPLT, 0, ord(".")), buffers(tmplt=b"________.___")),
                                  (INS_CHAR, (RAW, 1, ord("x"), 12), buffers(raw=b"AB")),
                                  (FIND_POS, (TMPLT, 3), buffers(tmplt=b"________.___")),
                                  (INSTR, (ord("5"), STRING_AT), {STRING_AT: b"0..9" + NUL}),
                                  (OB_STFN, (1, ANSWERS_AT, ANSWERS_AT + 2), merge_pokes(buffers(raw=b"AB", tmplt=b"____"),
                                                                                        STALE_ANSWERS)),
                                  (OB_DELIT, (1,), buffers(raw=b"ABC"))):
    aes.register("through its call word", _name, _arguments, aes.leaf_machine(onto=_pokes), through_line_f=True)
