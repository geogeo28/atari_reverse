"""THE OBJECT EDITOR — ob_edit $fe9678 (`src/aes/obedit.c`) and the cursor it draws, curfld $fe948a and pxl_rect
$fe941c, over the snapshot's own editable fields (the text helpers are `test_aes_ob_edit_text.py`).

    ob_edit(tree, obj, key, &idx, kind)   kind 0 (EDSTART) or obj <= 0: 1, nothing done
        ob_getsp(tree, obj, &edblk); lstcpy the template, the raw text, the validation string (stretched to te_tmplen by
        its last character); ob_format into fmtstr
        EDINIT: *idx := strlen(raw)
        EDCHAR: ob_stfn(*idx, &start, &finish); curfld(start, 0) — the cursor off; then by the key (table $fefb70):
            ESC *idx := 0, raw[0] := NUL;   BS (*idx > 0) --*idx, ob_delit;   DEL (*idx <= txtlen - 2) ob_delit;
            LEFT (*idx > 0) --*idx;   RIGHT (strlen(raw) > *idx) ++*idx;
            a typed key: past txtlen - 2 the index and start step back; its low byte checked against valid[*idx] —
            taken: ins_char, ++*idx; not: when it is a template literal ahead (scan_to_end), the raw text blank-filled
            to it and ended there, *idx := its place
            then lstcpy(te_ptext, raw); a changed field: ob_format, ob_stfn(*idx, &nstart, &nfinish), curfld(min(start,
            nstart), max(finish, nfinish) - that) when not 0 — the stretch redrawn
        every kind: curfld(find_pos(tmplt, *idx), 0) — the cursor drawn; answers 1
    curfld(tree, obj, pos, n)   pxl_rect(pos, &c); n: c.w += (n-1) cells, else gsx_attr(line, XOR, black), c.y -= 3,
                                c.h += 6; gsx_gclip(&saved); gsx_sclip(&c); n: ob_draw(tree, obj, 0) else gsx_cline down
                                the cell; gsx_sclip(&saved)
    pxl_rect(tree, obj, pos, &r) ob_actxywh(&t); gr_just(edblk's just, font, template, t.w, t.h, &t); r := (pos cells
                                right of t.x, t.y, one cell)

THE FIELDS ARE THE SNAPSHOT's: every editable of the AES's file selector and the desk's dialogs (`EDITABLES`), their
TEDINFOs, templates and validation strings as the resource holds them, a raw text as the desk's own inf_sset sets one
(`aes_obuser.seeded_raw_pokes`). An EDCHAR case starts where fm_do's EDINIT leaves the field — the ROM's own ob_edit
EDINIT run, continued from (`initialised`) — so the cursor it takes off is one the ROM drew; the few that do not are an
application's objc_edit(EDCHAR) with no EDINIT before it, a state its caller reaches too, and say so.

THE MACHINE is just_draw's (`aes_objdraw.machine`: the AES's cursor hidden, the IBM font cached — a dialog is drawn
before fm_do edits it); the cursor and every redraw are compared on the screen. curfld's redraw is ob_draw's, served by
`test_aes_ob_draw.doors` (the VDI's door and just_draw's by value). The editor's buffers and the C's frames are staged
STALE, so a store the C skips reads as that where the ROM read its own.
"""
import pytest

from harness import BASE_IMAGE

import aes
import boot_snapshot
import aes_objdraw as od
import aes_obuser as obuser
import case
import test_aes_ob_draw as obdraw
import vdi
from case import merge_pokes
from test_aes_gsx import screen_changed
from test_aes_oblib_walk import INDIRECT

L, W, IMAGE = vdi.LONG_ARG, vdi.WORD_ARG, vdi.IMAGE_ARG
OB_EDIT, CURFLD, PXL_RECT = "AES_ROM_OB_EDIT", "AES_ROM_CURFLD", "AES_ROM_PXL_RECT"
SIGNATURES = {
    OB_EDIT: (aes.WORD_ANSWER, (IMAGE, L, W, W, L, W)),
    CURFLD: (None, (IMAGE, L, W, W, W)),
    PXL_RECT: (None, (IMAGE, L, W, W, L)),
    # the text helpers (`test_aes_ob_edit_text.py`)
    "AES_ROM_OB_GETSP": (None, (IMAGE, L, W, L)),
    "AES_ROM_SCAN_TO_END": (aes.WORD_ANSWER, (IMAGE, L, W, W)),
    "AES_ROM_INS_CHAR": (None, (IMAGE, L, W, W, W)),
    "AES_ROM_FIND_POS": (aes.WORD_ANSWER, (IMAGE, L, W)),
    "AES_ROM_INSTR": (aes.WORD_ANSWER, (IMAGE, W, L)),
    "AES_ROM_CHECK": (aes.WORD_ANSWER, (IMAGE, L, W)),
    "AES_ROM_OB_STFN": (None, (IMAGE, W, L, L)),
    "AES_ROM_OB_DELIT": (aes.WORD_ANSWER, (IMAGE, W)),
}
for _name, (_restype, _argtypes) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, _argtypes)

EDSTART, EDINIT, EDCHAR, EDEND = aes.OB_EDIT_START, aes.OB_EDIT_INIT, aes.OB_EDIT_CHAR, aes.OB_EDIT_END
ESCAPE, BACKSPACE, DELETE = aes.OB_EDIT_KEY_ESCAPE, aes.OB_EDIT_KEY_BACKSPACE, aes.OB_EDIT_KEY_DELETE
LEFT, RIGHT = aes.OB_EDIT_KEY_LEFT, aes.OB_EDIT_KEY_RIGHT
TREES = od.trees()
SELECTOR = TREES["selector"]
NUL = b"\x00"


def key(character, scan=0):
    """A typed key's word as the BIOS hands it: its scan code high, its character low."""
    return scan << 8 | ord(character)


# ---- the editor's globals and the C's frames, staged STALE --------------------------------------------------------
BUFFERS = ("EDBLK", "RAWSTR", "TMPLT", "VALSTR", "FMTSTR")
_VALSTR = aes.field("AES", "VALSTR")
aes.declare_case_field(_VALSTR.at, _VALSTR.width * _VALSTR.count, "ob_edit's VALSTR")

STALE_BUFFERS = {spec.at: bytes([vdi.FILL]) * (spec.width * (spec.count or 1))
                 for spec in (aes.field("AES", name) for name in BUFFERS)}
STALE_SLOTS = merge_pokes(*(aes.stale_host_slot(role) for role in ("AES_PXL_RECT_FIELD", "AES_CURFLD_RECTS",
                                                                     "AES_OB_EDIT_FRAME")),
                          obdraw.STALE_SLOTS, od.STALE_FRAME)
# The index word the caller hands by address: fm_do's local, objc_edit's intout[1].
INDEX_AT = aes.RECTS_AT


def index_pokes(index):
    return {INDEX_AT: vdi.pack_words(index & 0xFFFF)}


def machine(onto=None):
    """just_draw's machine (the cursor hidden, the IBM font cached), the buffers and frames stale, `onto` over it."""
    return od.machine(merge_pokes(STALE_BUFFERS, STALE_SLOTS, onto))


# ---- the snapshot's editable fields --------------------------------------------------------------------------------
def tedinfo_of(tree, index, image=BASE_IMAGE):
    return od.object_long(tree, index, "SPEC", image)


def field_text(tree, index, name, image=BASE_IMAGE):
    """A TEDINFO string of a field (`name` PTEXT, PTMPLT or PVALID) — the TEDINFO the snapshot's tree names — in
    `image`, its NUL left off."""
    at = aes.read_field(image, "TE", name, tedinfo_of(tree, index))
    return bytes(image[at:image.index(0, at)])


EDITABLE = 1 << aes.OB_FLAG_EDITABLE_BIT   # OB_FLAGS: the fields fm_do edits (the selector's path and selection, ...)


def editables():
    """`{name: (tree, index)}`: every FBOXTEXT/FTEXT of the snapshot's trees fm_do edits (EDITABLE set)."""
    found = {}
    for name, tree in TREES.items():
        for index in od.link_order(tree):
            flags = od.object_word(BASE_IMAGE, tree, index, "FLAGS")
            if od.object_type(tree, index) in (aes.G_FTEXT, aes.G_FBOXTEXT) and flags & EDITABLE:
                found[f"{name} {index}"] = (tree, index)
    return found


EDITABLES = editables()
PATH = (SELECTOR, 2)                    # 38 placeholders, 'P'
SELECTION = (SELECTOR, 3)               # "________.___", 'F'


# The VDI's door and just_draw's (curfld's redraw is an ob_draw), opened for every case.
DOORS = obdraw.doors()


def edit(tree, index, character, kind, start_index=None, pokes=None, *, onto=None, **kwargs):
    """ob_edit of `tree`'s object `index` over `machine()` (or `onto`), the index word `start_index` (None: as `onto`
    leaves it), `pokes` laid on it — the C's frames stale whatever the machine."""
    staged = merge_pokes(machine() if onto is None else onto, STALE_SLOTS,
                         None if start_index is None else index_pokes(start_index), pokes)
    return aes.run_function(OB_EDIT, (tree, index, character, INDEX_AT, kind), staged, hook=DOORS, **kwargs)


def answer_index(result):
    return aes.signed(result.word(INDEX_AT))


def initialised(tree, index, pokes=None, onto=None):
    """The machine fm_do's EDINIT leaves the field in — the ROM's own ob_edit(EDINIT) run over `machine()` (or
    `onto`) with `pokes`, continued from: the cursor drawn at the raw text's end, the index there."""
    staged, final, writes = od.rom_run(OB_EDIT, (tree, index, 0, INDEX_AT, EDINIT),
                                       merge_pokes(machine() if onto is None else onto, index_pokes(aes.STALE_WORD),
                                                   pokes))
    return case.continued_from(staged, final, writes)


def typed(tree, index, keys, pokes=None, onto=None):
    """...and then `keys` edited in one by one (`typed_on`)."""
    return typed_on(tree, index, keys, initialised(tree, index, pokes, onto))


def typed_on(tree, index, keys, machine_):
    """`keys` edited in one by one by the ROM's own ob_edit(EDCHAR) over `machine_`, each run continued from."""
    for one in keys:
        staged, final, writes = od.rom_run(OB_EDIT, (tree, index, one, INDEX_AT, EDCHAR), machine_)
        machine_ = case.continued_from(staged, final, writes)
    return machine_


def raw_text(result, tree, index):
    """The field's raw text after a run: its te_ptext, as ob_edit copies the edit back."""
    return field_text(tree, index, "PTEXT", result.final)


def seeded(tree, index, text):
    """The field's raw text `text`, as the desk's inf_sset sets it."""
    return obuser.seeded_raw_pokes(tree, index, text)


# ---- EDSTART, and an object at or below the root: nothing ---------------------------------------------------------
@pytest.mark.parametrize("tree, index, kind", ((*PATH, EDSTART), (SELECTOR, aes.OB_ROOT, EDINIT), (SELECTOR, -1, EDCHAR),
                                               (SELECTOR, -0x8000, EDEND)),
                         ids=("EDSTART", "the root", "object -1", "object -32768"))
def test_nothing_is_done(tree, index, kind):
    result = edit(tree, index, key("a"), kind, start_index=3)
    assert result.answer() == 1 and aes.stored_nothing(result)


# ---- EDINIT -------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(EDITABLES))
def test_edinit_over_each_real_field(name):
    """Every raw text the resources hold starts '@' — empty: the index 0, the cursor drawn at the template's first
    placeholder."""
    tree, index = EDITABLES[name]
    result = edit(tree, index, 0, EDINIT, start_index=aes.STALE_WORD)
    assert result.answer() == 1 and answer_index(result) == 0 and screen_changed(result)


SEEDED = {
    "the path, a full one": (*PATH, b"A:\\GAMES\\ARCADES\\SHOOTERS\\VERTICAL\\*.*"[:37]),
    "the selection, a name": (*SELECTION, b"README  TXT"),
    "the desk's name field, short": (TREES["desk tree 1"], 2, b"AUTO"),
    "the desk's 38-character field": (TREES["desk tree 6"], 3, b"ANY TEXT AT ALL"),
}


@pytest.mark.parametrize("name", sorted(SEEDED))
def test_edinit_puts_the_index_at_the_raw_text_s_end(name):
    tree, index, text = SEEDED[name]
    result = edit(tree, index, 0, EDINIT, start_index=aes.STALE_WORD, pokes=seeded(tree, index, text))
    assert answer_index(result) == len(text)


# ---- EDCHAR over a field fm_do's EDINIT left ------------------------------------------------------------------------
def edit_key(tree, index, character, pokes=None, *, keys=(), **kwargs):
    """`character` edited into the field as fm_do edits it: after the ROM's own EDINIT (over `pokes`) and `keys`."""
    return edit(tree, index, character, EDCHAR, onto=typed(tree, index, keys, pokes), **kwargs)


DESK_NAME = (TREES["desk tree 1"], 2)                       # "Name:  ________.___", 'F'
DESK_SIZE = (TREES["desk tree 1"], 3)                       # "Size in bytes:  ________", '9', right-justified
DRIVE_LETTER = (TREES["desk tree 7"], 2)                    # "Drive Identifier: _", 'a', te_txtlen 2
ICON_LABEL = (TREES["desk tree 7"], 3)                      # "Icon Label: ____________", 'X'
FILE_ROW = (SELECTOR, 12)                                   # "_ ________.___ ", "xF"
TIME = (TREES["desk tree 1"], 5)                            # "__:__ __", "9999aa", right-justified


@pytest.mark.parametrize("field, character, text", (
    (PATH, key("a"), b"A"),
    (SELECTION, key("r", 0x13), b"R"),
    (DESK_NAME, key("1", 0x02), b"1"),
    (ICON_LABEL, key("q"), b"q"),
    (FILE_ROW, key("b"), b"B"),
    (DRIVE_LETTER, key("c"), b"c"),
), ids=("'P' upcases", "'F' upcases", "'F' takes a digit", "'X' takes it as typed", "'x' upcases", "'a' keeps it"))
def test_a_typed_character_taken_into_an_empty_field(field, character, text):
    result = edit_key(*field, character)
    assert raw_text(result, *field) == text and answer_index(result) == 1


@pytest.mark.parametrize("field, character", (
    (SELECTION, key("|")), (DESK_SIZE, key("x")), (DRIVE_LETTER, key("1")), (TIME, key("p")),
), ids=("'F' refuses '|'", "'9' refuses a letter", "'a' refuses a digit", "'9' refuses a letter, right-justified"))
def test_a_refused_character_changes_nothing(field, character):
    result = edit_key(*field, character, pokes=seeded(*field, b"12"))
    assert raw_text(result, *field) == b"12"


def test_a_typed_character_inserted_mid_text():
    """LEFT twice, then a character: inserted before the last two, the rest moved up (ins_char)."""
    result = edit_key(*SELECTION, key("x"), pokes=seeded(*SELECTION, b"ABCD"), keys=(LEFT, LEFT))
    assert raw_text(result, *SELECTION) == b"ABXCD" and answer_index(result) == 3


def test_a_character_past_the_last_place_replaces_the_last():
    """The selection full (11 of te_txtlen 12): the index past txtlen - 2 steps back and the character replaces the
    last — ins_char ends the string at te_txtlen - 1."""
    result = edit_key(*SELECTION, key("z"), pokes=seeded(*SELECTION, b"README  TXT"))
    assert raw_text(result, *SELECTION) == b"README  TXZ" and answer_index(result) == 11


def test_a_refused_character_past_the_last_place_steps_forward_again():
    """...a refused one: the index stepped back and forward again, the frame's start left stepped back."""
    result = edit_key(*SELECTION, key("|"), pokes=seeded(*SELECTION, b"README  TXT"))
    assert raw_text(result, *SELECTION) == b"README  TXT" and answer_index(result) == 11


# The AES's save-under buffer (gl_tmp's fd_addr, the block the boot's Malloc answered): the screen bytes a menu or an
# alert saved, any value — inside the 64 KB find_pos's word-wide place reaches around AES_TMPLT.
SAVE_UNDER_AT = int.from_bytes(bytes(aes.read_field(BASE_IMAGE, "AES", "GL_TMP")[:aes.LONG_BYTES]), "big")
WIDEST_INDEX = 0x7FFF
# The ROM's run below, measured; over the snapshot's own bytes — 447 placeholders in those 64 KB, so 73 times round —
# it is 35,836,288 instructions and the case 33 s.
# THE WALK CROSSES BYTES NO TWO CAPTURES AGREE ON, AND THE CASE STAGES THEM. find_pos's word-wide place reaches the
# 64 KB round AES_TMPLT, low RAM among them — and so eight of the regions `tools/boot_snapshot.py`'s MASK names as
# capture-variant (OS scratch, dead stack frames). A byte there that happens to be a placeholder ($5f) costs the walk
# nine instructions (twelve in one region; `A_PLACEHOLDER_COSTS_THE_WALK`, held on any capture):
# one capture had one at `$74df` (1,944,402), most have none (1,944,393), one kept set has two.
# (It is not the snapshot's phase: both counts were seen at `savptr` `$93a`.) So the masked bytes the walk crosses
# are DECLARED AND STAGED — zeroed, no placeholder among them — and the count is exact over any capture.
# WHY THE MASK'S OWN TEST DID NOT SAY SO: `test_boot_snapshot`'s noise sweep runs the REGISTERED rows and compares
# what each LEAVES; this case is no registered row (two million instructions: a test of its own), and a placeholder
# more in the walk moves the count and nothing the run stores.
FIND_POS_REACHES = 0x8000               # a signed word either side of AES_TMPLT
UNSTEP_MEASURED_INSNS = 1_944_393
UNSTEP_INSNS = 2 * UNSTEP_MEASURED_INSNS


def the_masked_bytes_the_walk_crosses():
    """`{address: zeros}` for every byte of the snapshot's MASK inside find_pos's reach round AES_TMPLT."""
    lo, hi = aes.AES_TMPLT - FIND_POS_REACHES, aes.AES_TMPLT + FIND_POS_REACHES
    crossed = {}
    for address, length, _why in boot_snapshot.MASK:
        start, end = max(address, lo), min(address + length, hi)
        if start < end:
            crossed[start] = bytes(end - start)
    return crossed


THE_MASKED_REGIONS_CROSSED = 8          # of the snapshot's MASK, inside find_pos's reach on this machine
# WHAT ONE PLACEHOLDER COSTS THE WALK, instructions, by the masked region it lies in (in address order) — MEASURED:
# nine in seven of them (one more turn of the loop that counts it), twelve in the last, `$c7e1`.
A_PLACEHOLDER_COSTS_THE_WALK = (9, 9, 9, 9, 9, 9, 9, 12)


def the_unstepped_walk(under=None, over=None):
    """THE CASE'S RUN: the '|' refused at the widest index over the field seeded "AB", the save-under buffer all
    placeholders and THE MASKED BYTES THE WALK CROSSES STAGED. `under`: pokes laid on the machine BENEATH that
    staging (a capture's own noise); `over`: pokes laid above it (what the staging would otherwise hide)."""
    onto = merge_pokes(initialised(*SELECTION, seeded(*SELECTION, b"AB")), under)
    placeholders = bytes([aes.OB_FORMAT_PLACEHOLDER]) * aes.GSX_SAVE_BUFFER_BYTES
    staged = merge_pokes(the_masked_bytes_the_walk_crosses(), {SAVE_UNDER_AT: placeholders}, over)
    return edit(*SELECTION, key("|"), EDCHAR, start_index=WIDEST_INDEX, onto=onto, pokes=staged, max_insns=UNSTEP_INSNS)


def test_a_refused_character_at_the_widest_index_fills_from_the_unstepped_start():
    """An application's objc_edit index $7fff (int_in, any word): stepped back and the '|' refused, the index and the
    walk's start are stepped forward again — and scan_to_end's count from that start wraps the word, so the literal's
    place lies BELOW the last place and the fill runs (13 KB of blanks, as the ROM writes them), from where the start
    says. find_pos first walks 32,767 placeholders through the RAM round AES_TMPLT; the save-under buffer staged all
    placeholders (a saved screen of $5f bytes) brings that to three times round."""
    result = the_unstepped_walk()
    assert answer_index(result) < 0 and result.info["regs"]["ninsns"] == UNSTEP_MEASURED_INSNS


def test_the_walk_crosses_masked_bytes_and_every_one_is_staged():
    """THE DECLARATION, HELD: the reach round AES_TMPLT takes in eight regions of the MASK (so the premise of the
    staging is true), each staged byte is a masked one and none is a placeholder."""
    crossed = the_masked_bytes_the_walk_crosses()
    masked = {at for address, length, _why in boot_snapshot.MASK for at in range(address, address + length)}
    staged = {at for start, zeros in crossed.items() for at in range(start, start + len(zeros))}
    assert len(crossed) == THE_MASKED_REGIONS_CROSSED and staged <= masked and not any(any(zeros) for zeros in crossed.values())
    assert aes.OB_FORMAT_PLACEHOLDER != 0


@pytest.mark.parametrize("region", range(THE_MASKED_REGIONS_CROSSED))
def test_the_case_s_count_does_not_see_a_placeholder_a_capture_leaves_in_a_masked_byte(region):
    """THE STAGING IS USED, AND ITS PREMISE IS TRUE — on ANY capture, whether or not it holds such a byte itself
    (one did, at `$74df`; most do not, and on those a case that staged nothing counted the same): a placeholder
    planted in a masked byte BENEATH the case's staging leaves the count exact; the same byte planted OVER the
    staging costs the walk nine instructions (twelve in the last region). One byte of each masked region crossed."""
    start, zeros = sorted(the_masked_bytes_the_walk_crosses().items())[region]
    planted = {start + len(zeros) // 2: bytes([aes.OB_FORMAT_PLACEHOLDER])}
    assert the_unstepped_walk(under=planted).info["regs"]["ninsns"] == UNSTEP_MEASURED_INSNS
    assert the_unstepped_walk(over=planted).info["regs"]["ninsns"] == UNSTEP_MEASURED_INSNS + A_PLACEHOLDER_COSTS_THE_WALK[region]


@pytest.mark.parametrize("field, text, keys, character, expected, place", (
    (SELECTION, b"AB", (), key("."), b"AB      ", 8),
    (SELECTION, b"ABCDEFGH", (), key("."), b"ABCDEFGH", 8),
    (TIME, b"12", (), key(":"), b"12", 2),
    (DESK_NAME, b"", (), key(" "), b"", 0),
), ids=("a dot jumps to the extension", "a dot at the extension already", "a colon right-justified",
        "a blank before the first placeholder"))
def test_a_template_literal_typed_fills_up_to_it(field, text, keys, character, expected, place):
    """A refused character that is a literal of the template ahead (scan_to_end): the raw text blank-filled to its
    place and ended there — when that place lies before txtlen - 2."""
    result = edit_key(*field, character, pokes=seeded(*field, text), keys=keys)
    assert raw_text(result, *field) == expected and answer_index(result) == place


UP_ARROW = 0x4800                       # a key with no character: its low byte 0


@pytest.mark.parametrize("field", (PATH, ICON_LABEL), ids=("a 'P' field", "an 'X' field, which would take a NUL"))
def test_a_key_with_no_character_does_nothing(field):
    """Up arrow: its character NUL is never checked — an 'X' validation, which takes anything, would insert it."""
    result = edit_key(*field, UP_ARROW, pokes=seeded(*field, b"AB"))
    assert raw_text(result, *field) == b"AB" and answer_index(result) == 2


def test_an_unchanged_fresh_field_is_still_copied_back():
    """LEFT over a field EDINIT left — its raw text the resource's '@' mark: the copy back runs whatever the key did,
    and writes the text ob_format emptied."""
    tree, index = SELECTION
    assert field_text(tree, index, "PTEXT").startswith(b"@")
    result = edit_key(tree, index, LEFT)
    assert raw_text(result, tree, index) == b""


@pytest.mark.parametrize("text, keys, expected, place", (
    (b"ABC", (), b"", 0), (b"", (), b"", 0), (b"ABC", (LEFT,), b"", 0),
), ids=("a text", "an empty field: nothing to redraw", "the index mid-text"))
def test_escape_empties_the_field(text, keys, expected, place):
    result = edit_key(*PATH, ESCAPE, pokes=seeded(*PATH, text), keys=keys)
    assert raw_text(result, *PATH) == expected and answer_index(result) == place


@pytest.mark.parametrize("text, keys, expected, place", (
    (b"ABC", (), b"AB", 2), (b"ABC", (LEFT, LEFT, LEFT), b"ABC", 0), (b"ABC", (LEFT,), b"AC", 1),
), ids=("at the end", "at the start: nothing", "mid-text"))
def test_backspace(text, keys, expected, place):
    result = edit_key(*SELECTION, BACKSPACE, pokes=seeded(*SELECTION, text), keys=keys)
    assert raw_text(result, *SELECTION) == expected and answer_index(result) == place


@pytest.mark.parametrize("text, keys, expected", (
    (b"ABC", (LEFT, LEFT), b"AC"), (b"ABC", (), b"ABC"), (b"README  TXT", (), b"README  TXT"),
    (b"README  TXT", (LEFT,), b"README  TX"),
), ids=("mid-text", "at the end: nothing", "past the last place: nothing", "the last place"))
def test_delete(text, keys, expected):
    result = edit_key(*SELECTION, DELETE, pokes=seeded(*SELECTION, text), keys=keys)
    assert raw_text(result, *SELECTION) == expected


@pytest.mark.parametrize("character, keys, place", (
    (LEFT, (), 2), (LEFT, (LEFT, LEFT, LEFT), 0), (RIGHT, (), 3), (RIGHT, (LEFT,), 3),
), ids=("left", "left at the start", "right at the end", "right"))
def test_the_arrows_move_the_index(character, keys, place):
    result = edit_key(*SELECTION, character, pokes=seeded(*SELECTION, b"ABC"), keys=keys)
    assert answer_index(result) == place and raw_text(result, *SELECTION) == b"ABC"


def test_a_character_s_high_bit_is_kept():
    """$e9 (an accented letter, its key's scan code high): the key's whole low byte, which 'F' takes as typed."""
    result = edit_key(*SELECTION, 0x12E9)
    assert raw_text(result, *SELECTION) == b"\xe9"


def test_a_literal_landing_on_the_last_place_fills_nothing():
    """An application's shorter selection (te_txtlen 10, last place 8): the dot's place IS the last, and only a place
    BELOW it is filled to."""
    pokes = merge_pokes(seeded(*SELECTION, b"AB"), aes.tedinfo_pokes(tedinfo_of(*SELECTION), TXTLEN=10))
    result = edit_key(*SELECTION, key("."), pokes=pokes)
    assert raw_text(result, *SELECTION) == b"AB" and answer_index(result) == 2


# The index word laid where ob_delit's copy moves it: past the merged text in AES_FMTSTR (whose first 13 bytes ob_format
# writes for the selection), holding $0101 — the smallest word a text's bytes can make. The bytes from RAWSTR + $100 are
# AES_FMTSTR's past that merge: an earlier, longer field's merged text left them, so any are reachable there.
MOVED_INDEX_AT = aes.AES_RAWSTR + 0x102


def test_backspace_steps_the_index_before_deleting():
    """BS: the index stored one less ($0100), THEN the raw text's byte 256 deleted — a copy that moves the stored word
    down a byte; a delete before the store would move the old one. Over the ROM's own EDINIT, the stale AES_FMTSTR
    bytes laid on it."""
    onto = merge_pokes(initialised(*SELECTION), STALE_SLOTS,
                       {aes.AES_RAWSTR + 0x100: b"ZY\x01\x01X\x00"})
    aes.run_function(OB_EDIT, (*SELECTION, BACKSPACE, MOVED_INDEX_AT, EDCHAR), onto, hook=DOORS)


def test_a_right_justified_field_takes_digits_from_the_right():
    result = edit_key(*DESK_SIZE, key("7"), pokes=seeded(*DESK_SIZE, b"12"))
    assert raw_text(result, *DESK_SIZE) == b"127"


def test_a_word_of_keys_typed_in_turn():
    """Five keys, each the ROM's own ob_edit continued from, then a sixth compared."""
    result = edit_key(*SELECTION, key("t"), keys=(key("r"), key("e"), key("a"), key("d"), key(".")))
    assert raw_text(result, *SELECTION) == b"READ    T"


# ---- EDEND, and the kinds past it ------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", (EDEND, 4, 0x7FFF, -1), ids=("EDEND", "4", "$7fff", "-1"))
def test_every_other_kind_only_toggles_the_cursor(kind):
    """EDEND — and any kind but 0, 1 and 2, a WORD compared — draws the cursor at the index's place once more: in XOR,
    over the one EDINIT drew, it is taken off. The raw text is not copied back."""
    onto = initialised(*SELECTION, seeded(*SELECTION, b"AB"))
    result = edit(*SELECTION, key("q"), kind, onto=onto)
    assert raw_text(result, *SELECTION) == b"AB" and answer_index(result) == 2 and screen_changed(result)


def test_a_kind_whose_low_byte_is_edinit_s_is_not():
    """$0101: its low byte EDINIT's, but the WORD is compared — the index is not set."""
    result = edit(*SELECTION, 0, 0x0101, start_index=1, pokes=seeded(*SELECTION, b"AB"))
    assert answer_index(result) == 1


# ---- the copies: the validation stretched, an INDIRECT spec -----------------------------------------------------------
def test_the_validation_is_stretched_by_its_last_character():
    """"xF" over a 15-byte template: the 'F' repeated to te_tmplen (16), the NUL after."""
    result = edit(*FILE_ROW, 0, EDINIT, start_index=0)
    assert result.after(aes.AES_VALSTR, 17) == b"x" + b"F" * 15 + NUL


def test_an_empty_validation_is_not_stretched():
    """A validation string of no characters: nothing repeated (the loop's `copied > 0`), only the NUL."""
    tedinfo = tedinfo_of(*SELECTION)
    pokes = merge_pokes(aes.tedinfo_pokes(tedinfo, PVALID=aes.BLOCKS_AT), {aes.BLOCKS_AT: NUL})
    result = edit(*SELECTION, 0, EDINIT, start_index=0, pokes=pokes)
    assert result.after(aes.AES_VALSTR, 1) == NUL


@pytest.mark.parametrize("kind", (EDINIT, EDCHAR), ids=("EDINIT", "a typed key"))
@pytest.mark.parametrize("length", (255, 256))
def test_a_validation_of_255_characters_or_more_is_not_stretched(length, kind):
    """lstcpy counts in a BYTE: a long validation string (one several fields share) of 255 counts -1 and of 256 counts
    0, so neither is stretched (`copied > 0`) and its NUL lands at AES_VALSTR[count] — for 255 the byte BEFORE the
    buffer, the template's last."""
    tedinfo = tedinfo_of(*SELECTION)
    pokes = merge_pokes(aes.tedinfo_pokes(tedinfo, PVALID=aes.BLOCKS_AT), {aes.BLOCKS_AT: b"X" * length + NUL})
    if kind == EDINIT:
        result = edit(*SELECTION, 0, EDINIT, start_index=0, pokes=pokes)
    else:
        result = edit_key(*SELECTION, key("q"), pokes=pokes)
    assert result.after(aes.AES_VALSTR + aes.signed(length, 8), 1) == NUL


def indirect_pokes(tree, index, at=aes.BLOCKS_AT):
    """`index` made INDIRECT: its ob_spec the address of a longword naming its own TEDINFO."""
    flags = od.object_word(BASE_IMAGE, tree, index, "FLAGS") & 0xFFFF
    return merge_pokes(od.flags_pokes(tree, index, flags | INDIRECT), od.spec_pokes(tree, index, at),
                       {at: tedinfo_of(tree, index).to_bytes(aes.LONG_BYTES, "big")})


def test_an_indirect_spec_names_the_tedinfo():
    result = edit_key(*SELECTION, key("k"), pokes=indirect_pokes(*SELECTION))
    assert raw_text(result, *SELECTION) == b"K"


def test_the_template_is_copied_before_the_raw_text():
    """An application's te_ptext inside the editor's own template buffer: the template's copy lands first, so the raw
    text copied is the template's tail."""
    tree, index = SELECTION
    result = edit(tree, index, 0, EDINIT, start_index=0, pokes=aes.tedinfo_pokes(tedinfo_of(tree, index),
                                                                                PTEXT=aes.AES_TMPLT + 8))
    assert answer_index(result) == 4                        # ".___"


# ---- ORDER: what the index pointer reads back -------------------------------------------------------------------------
TXTLEN_COPY = aes.AES_EDBLK + aes.TE_TXTLEN


def test_the_index_is_read_after_the_tedinfo_is_copied():
    """The index word laid over the copy's te_txtlen: ob_getsp overwrites it (12) before the index is read — so the
    key lands past the last place — and the step back's store (11) is te_txtlen when ins_char is handed it: the text
    ends a byte short, the character dropped."""
    onto = initialised(*SELECTION, seeded(*SELECTION, b"README  TXT"))
    result = aes.run_function(OB_EDIT, (*SELECTION, key("z"), TXTLEN_COPY, EDCHAR), merge_pokes(onto, STALE_SLOTS),
                              hook=DOORS)
    assert raw_text(result, *SELECTION) == b"README  TX"


def test_edinit_s_index_is_read_back_after_it_is_stored():
    """The index word laid over the raw text's copy: EDINIT stores strlen into it, and the cursor's place is found
    from the word read back."""
    result = aes.run_function(OB_EDIT, (*SELECTION, 0, aes.AES_RAWSTR, EDINIT),
                              merge_pokes(machine(), seeded(*SELECTION, b"AB")), hook=DOORS)
    assert result.answer() == 1


def test_the_index_is_read_after_the_raw_text_is_copied_back():
    """The index word laid over the field's own raw text: the edit's copy back rewrites it before the redraw and the
    cursor read it. An application's objc_edit(EDCHAR) with no EDINIT before it (no cursor drawn to take off)."""
    text_at = aes.read_field(BASE_IMAGE, "TE", "PTEXT", tedinfo_of(*SELECTION))
    onto = merge_pokes(machine(), seeded(*SELECTION, b"\x00\x02CD"))
    result = aes.run_function(OB_EDIT, (*SELECTION, key("z"), text_at, EDCHAR), onto, hook=DOORS)
    assert result.answer() == 1


# ---- the 24-bit bus, and the Line-F door ------------------------------------------------------------------------------
def test_ob_edit_puts_its_pointers_on_the_bus():
    onto = typed(*SELECTION, ())
    result = aes.run_function(OB_EDIT, (SELECTOR | aes.BUS_TAG, SELECTION[1], key("q"), INDEX_AT | aes.BUS_TAG, EDCHAR),
                              merge_pokes(onto, STALE_SLOTS), hook=DOORS)
    assert raw_text(result, *SELECTION) == b"Q"


def tagged_strings(tree, index):
    """An application's TEDINFO for `index` whose three strings' pointers each carry a top byte."""
    tedinfo = tedinfo_of(tree, index)
    return aes.tedinfo_pokes(tedinfo, **{name: aes.read_field(BASE_IMAGE, "TE", name, tedinfo) | aes.BUS_TAG
                                         for name in ("PTEXT", "PTMPLT", "PVALID")})


@pytest.mark.parametrize("character", (None, key("a"), key("."), BACKSPACE), ids=("EDINIT", "a character", "a dot fill",
                                                                                  "BS"))
def test_ob_edit_puts_the_tedinfo_s_strings_on_the_bus(character):
    """The copies, the copy back to te_ptext and the redraw's gr_just over te_ptmplt, each through a tagged pointer."""
    pokes = merge_pokes(seeded(*SELECTION, b"AB"), tagged_strings(*SELECTION))
    if character is None:
        result = edit(*SELECTION, 0, EDINIT, start_index=0, pokes=pokes)
    else:
        result = edit_key(*SELECTION, character, pokes=pokes)
    assert result.answer() == 1


@pytest.mark.parametrize("kind", (EDINIT, EDCHAR), ids=("EDINIT", "EDCHAR"))
def test_ob_edit_through_its_call_word(kind):
    """fm_do, objc_edit's arm and the desk call ob_edit by `$f210`. EDCHAR as an application's objc_edit may make it,
    with no EDINIT before it."""
    edit(*SELECTION, key("q"), kind, start_index=0, through_line_f=True)


# ---- curfld and pxl_rect, over the copy ob_edit made ------------------------------------------------------------------
GETSP = "AES_ROM_OB_GETSP"
TITLE = (SELECTOR, 5)                                       # the selector's directory line: a BOXTEXT, centred
RECT_AT = aes.RECTS_AT + aes.LONG_BYTES                     # pxl_rect's answer GRECT, past the index word
STALE_RECT = {RECT_AT: vdi.pack_words(*[aes.STALE_WORD] * 4)}


def copied(tree, index, pokes=None):
    """The machine with `index`'s TEDINFO in AES_EDBLK as the ROM's own ob_getsp copies it — what curfld and pxl_rect
    read, always after ob_edit's copy."""
    staged, final, writes = od.rom_run(GETSP, (tree, index, aes.AES_EDBLK), machine(pokes))
    return merge_pokes(case.continued_from(staged, final, writes), STALE_SLOTS)


def pxl_rect(tree, index, position, rect=RECT_AT, *, onto=None, **kwargs):
    staged = merge_pokes(copied(tree, index) if onto is None else onto, STALE_RECT)
    return aes.run_function(PXL_RECT, (tree, index, position, rect), staged, hook=DOORS, **kwargs)


def curfld(tree, index, position, characters, *, onto=None, **kwargs):
    return aes.run_function(CURFLD, (tree, index, position, characters), copied(tree, index) if onto is None else onto,
                            hook=DOORS, **kwargs)


@pytest.mark.parametrize("field, position", (
    (PATH, 0), (PATH, 37), (DESK_SIZE, 3), (TITLE, 2), (SELECTION, -3), (SELECTION, 0x4000),
), ids=("left, the first cell", "left, the last", "right-justified", "centred", "a negative place",
        "a place whose product wraps the word"))
def test_pxl_rect(field, position):
    result = pxl_rect(*field, position)
    cell = [aes.signed(result.word(RECT_AT + offset)) for offset in range(4, 8, 2)]
    assert cell == [aes.signed(case.word_in(BASE_IMAGE, aes.AES_GL_WCHAR)),
                    aes.signed(case.word_in(BASE_IMAGE, aes.AES_GL_HCHAR))]


SMALL_FONT = aes.header_constants("gemgraf.h")["GSX_FONT_SMALL"]


@pytest.mark.parametrize("field", (PATH, TITLE), ids=("left", "centred"))
def test_pxl_rect_of_a_field_in_the_small_font(field):
    """An application's field in the small font (no snapshot TEDINFO uses it): gr_just measures the template in it."""
    onto = copied(*field, aes.tedinfo_pokes(tedinfo_of(*field), FONT=SMALL_FONT))
    pxl_rect(*field, 2, onto=onto)


def test_pxl_rect_reads_the_cell_width_again_after_storing_x():
    """The answer GRECT laid over gl_wchar: x is stored into it, then the width stored is gl_wchar read again — x."""
    result = pxl_rect(*PATH, 3, rect=aes.AES_GL_WCHAR)
    assert result.word(aes.AES_GL_WCHAR) == result.word(aes.AES_GL_WCHAR + 4)


@pytest.mark.parametrize("field, position", ((PATH, 0), (SELECTION, 8), (DESK_SIZE, 7), (TITLE, 1)),
                         ids=("the path's first cell", "the selection's dot", "right-justified", "centred"))
def test_curfld_draws_the_cursor(field, position):
    result = curfld(*field, position, 0)
    assert screen_changed(result)


def cursor_taken_off(tree, index, position, pokes=None, onto_copy=None):
    """The machine a stretch is redrawn in: ob_edit's — the ROM's own curfld having taken the cursor off at
    `position` (its line drawn, PTSIN pointed by the call), continued from — over the TEDINFO copy of `index` (or of
    the field `onto_copy` names)."""
    staged, final, writes = od.rom_run(CURFLD, (tree, index, position, 0), copied(*(onto_copy or (tree, index)), pokes))
    return merge_pokes(case.continued_from(staged, final, writes), STALE_SLOTS)


@pytest.mark.parametrize("position, characters", ((0, 1), (3, 8), (0, 38), (30, 20), (5, -2), (0, 0x0100)),
                         ids=("one cell", "eight cells", "the whole field", "past the field's end",
                              "a negative count: the clip's width shrinks", "$0100: tested as a word"))
def test_curfld_redraws_a_stretch(position, characters):
    """The field's object redrawn (ob_draw, depth 0) under a clip `characters` cells wide from `position`'s cell; the
    clip it found is set back. Over a raw text the edit left, so the stretch differs from the screen.

    UNPOISONED (`aes_objdraw.PTSIN_READ_FIRST`, measured): the redraw's text reads the parameter block's PTSIN pointer
    before this run's own calls store it, so the pass hands the VDI an inverted pointer into the I/O page. The same
    arm runs POISONED inside every EDCHAR case that redraws (`test_a_typed_character_*`, `test_escape_*`, ...), where
    the cursor's line points PTSIN earlier in the same run."""
    onto = cursor_taken_off(*PATH, position, seeded(*PATH, b"A:\\NEW\\*.*"))
    curfld(*PATH, position, characters, onto=onto, **od.PTSIN_READ_FIRST)


FILE_LIST = (SELECTOR, 6)                                   # nine file rows below it


def test_curfld_redraws_the_object_alone():
    """Depth 0: an object with children (the selector's file list, over its first row's TEDINFO copy) is drawn without
    them — its box over its rows. POISONED: a box draws no text, so nothing reads PTSIN before the run stores it."""
    onto = cursor_taken_off(*FILE_LIST, 0, onto_copy=FILE_ROW)
    curfld(*FILE_LIST, 0, 4, onto=onto)


@pytest.mark.parametrize("name", (CURFLD, PXL_RECT))
def test_through_the_call_word(name):
    arguments = (*SELECTION, 2, 0) if name == CURFLD else (*SELECTION, 2, RECT_AT)
    aes.run_function(name, arguments, merge_pokes(copied(*SELECTION), STALE_RECT), hook=DOORS, through_line_f=True)


def test_curfld_and_pxl_rect_put_their_pointers_on_the_bus():
    curfld(SELECTOR | aes.BUS_TAG, SELECTION[1], 2, 0, onto=copied(*SELECTION))
    pxl_rect(SELECTOR | aes.BUS_TAG, SELECTION[1], 2, RECT_AT | aes.BUS_TAG, onto=copied(*SELECTION))


# ---- the registry: Tier 3's candidate rows (the worst realistic one of each routine measured, `make bench`) ------------
FULL_PATH = b"A:\\GAMES\\ARCADES\\SHOOTERS\\VERTICAL\\*.*"
assert len(FULL_PATH) == field_text(*PATH, "PTMPLT").count(b"_")
FULL_PATH_POKES = seeded(*PATH, FULL_PATH[:-1])             # 37: one place left for a typed character
HOME = (LEFT,) * (len(FULL_PATH) - 1)
# An application's longest field: every place of the editor's 81-byte buffers a placeholder, 'X', a text one character
# short of full — worse than the snapshot's path (measured: own 0.80 against 0.76).
LONGEST_TEMPLATE = bytes([aes.OB_FORMAT_PLACEHOLDER]) * (aes.AES_TEXT_BUFFER_BYTES - 1)
LONGEST_VALID = bytes([aes.VALID_ANY])
LONGEST_TEXT = b"A" * (len(LONGEST_TEMPLATE) - 1)


def longest_field_pokes(tree, index):
    """`index`'s TEDINFO pointed at the longest field's strings, laid one after another in the blocks band."""
    template_at = aes.BLOCKS_AT
    valid_at = template_at + len(LONGEST_TEMPLATE + NUL)
    text_at = valid_at + len(LONGEST_VALID + NUL)
    lengths = len(LONGEST_TEMPLATE + NUL)
    return merge_pokes(aes.tedinfo_pokes(tedinfo_of(tree, index), PTMPLT=template_at, PVALID=valid_at, PTEXT=text_at,
                                         TMPLEN=lengths, TXTLEN=lengths),
                       {template_at: LONGEST_TEMPLATE + NUL + LONGEST_VALID + NUL + LONGEST_TEXT + NUL})


def register_edit(label, field, character, kind, pokes=None, *, keys=None, edited=None, start_index=0,
                  through_line_f=False):
    """An ob_edit row: over `machine()` with `pokes`, or — `keys` given — after fm_do's EDINIT and those keys, or over
    `edited`, the machine keys already left (`typed`), shared by several rows."""
    if edited is not None:
        staged = merge_pokes(edited, STALE_SLOTS)
    elif keys is None:
        staged = merge_pokes(machine(), STALE_SLOTS, index_pokes(start_index), pokes)
    else:
        staged = merge_pokes(typed(*field, keys, pokes), STALE_SLOTS)
    aes.register(label, OB_EDIT, (*field, character, INDEX_AT, kind), staged, through_line_f=through_line_f, hook=DOORS)


# A full path's head: HOME's keys but its last typed once, and the last added for the rows at the head itself — a prefix
# derived once rather than three times (37 ROM runs each).
_ONE_SHORT_OF_HOME = typed(*PATH, HOME[:-1], FULL_PATH_POKES)
_AT_HOME = typed_on(*PATH, HOME[-1:], _ONE_SHORT_OF_HOME)
register_edit("EDINIT, the empty path", PATH, 0, EDINIT)
register_edit("EDINIT, a full path", PATH, 0, EDINIT, FULL_PATH_POKES)
register_edit("EDEND, a full path", PATH, 0, EDEND, keys=(), pokes=FULL_PATH_POKES)
register_edit("a character into the empty path", PATH, key("a"), EDCHAR, keys=())
register_edit("a character at a full path's head", PATH, key("a"), EDCHAR, edited=_AT_HOME)
register_edit("ESC over a full path", PATH, ESCAPE, EDCHAR, keys=(), pokes=FULL_PATH_POKES)
register_edit("BS at a full path's head", PATH, BACKSPACE, EDCHAR, edited=_ONE_SHORT_OF_HOME)
register_edit("DEL at a full path's head", PATH, DELETE, EDCHAR, edited=_AT_HOME)
register_edit("a dot jumping to the extension", SELECTION, key("."), EDCHAR, keys=(), pokes=seeded(*SELECTION, b"AB"))
register_edit("a refused character past the last place", SELECTION, key("|"), EDCHAR, keys=(),
              pokes=seeded(*SELECTION, b"README  TXT"))
register_edit("LEFT", SELECTION, LEFT, EDCHAR, keys=(), pokes=seeded(*SELECTION, b"README  TXT"))
register_edit("a digit, right-justified", DESK_SIZE, key("7"), EDCHAR, keys=(), pokes=seeded(*DESK_SIZE, b"1234567"))
register_edit("EDSTART", PATH, 0, EDSTART)
register_edit("EDINIT, an application's 80-place field", PATH, 0, EDINIT, longest_field_pokes(*PATH))
# At its head by the index the application hands (objc_edit's int_in, any word) over fm_do's EDINIT, rather than 79
# LEFTs — 79 ROM runs more at every import (+0.5 s a worker, measured).
aes.register("a character at an 80-place field's head", OB_EDIT, (*PATH, key("a"), INDEX_AT, EDCHAR),
             merge_pokes(typed(*PATH, (), longest_field_pokes(*PATH)), STALE_SLOTS, index_pokes(0)), hook=DOORS)
register_edit("a character into the empty path", PATH, key("a"), EDCHAR, keys=(), through_line_f=True)
for _label, _field, _position in (("the path's first cell", PATH, 0), ("a size, right-justified", DESK_SIZE, 7),
                                  ("the selector's centred title", TITLE, 1)):
    aes.register(_label, PXL_RECT, (*_field, _position, RECT_AT), merge_pokes(copied(*_field), STALE_RECT), hook=DOORS)
    aes.register(f"the cursor at {_label}", CURFLD, (*_field, _position, 0), copied(*_field), hook=DOORS)
aes.register("the whole path redrawn", CURFLD, (*PATH, 0, len(FULL_PATH)), cursor_taken_off(*PATH, 0, FULL_PATH_POKES),
             hook=DOORS)
aes.register("one cell redrawn", CURFLD, (*PATH, 3, 1), cursor_taken_off(*PATH, 3, FULL_PATH_POKES), hook=DOORS)
aes.register("the path's first cell", PXL_RECT, (*PATH, 0, RECT_AT), merge_pokes(copied(*PATH), STALE_RECT), hook=DOORS,
             through_line_f=True)
