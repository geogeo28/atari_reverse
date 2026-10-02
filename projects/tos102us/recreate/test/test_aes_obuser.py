"""The object draw path's leaves — `src/aes/obuser.c`: ob_format $fe99a4, ob_user $fe9a46, far_call $fddec6.

    ob_format(just, raw, tmplt, out)    raw[0] == '@' → raw[0] := NUL; n := strlen(tmplt), r := strlen(raw); out[n] := NUL;
                                        OB_FORMAT_RIGHT → all three from their last bytes back; per template byte: '_' →
                                        the raw text's next byte, or '_' once it is spent; any other byte copied
    ob_user(tree, obj, rect, userblk, curr, new)
                                        PARMBLK in the frame: tree, obj, (curr, new) one longword, rc_copy(rect),
                                        gsx_gclip, ub_parm — then far_call(ub_code, &PARMBLK); D0 the routine's
    far_call(code, parm)                `move.l parm,-(sp) / jsr (code)`; D0 the routine's

ALL ALCYON, each a Line-F call returning by a Line-F return (the mask word dropped, `aes.run_function`'s default).

ob_format's REAL DATA is every editable text field of the snapshot's two resources — the AES's file selector and the
desk's dialogs — merged into just_draw's own buffers (`aes/objdraw.h`: AES_RAWSTR, the ODD AES_TMPLT, AES_FMTSTR), as
just_draw's lstcpys leave them. Every raw text in both resources starts '@' (the mark of an empty field), so a raw text
that does NOT is seeded by the ROM's own writer: the desk's inf_sset ($fecfb2) run on the oracle over the real field.

ob_user's routine is an application's — no snapshot tree holds a G_USERDEF — so it is staged (`test/aes_obuser.py`): a
68000 routine copying the PARMBLK it is handed into a compared log and answering a chosen D0, over a real object of the
selector and the snapshot's own clip.
"""
import pytest

from harness import BASE_IMAGE, make_image

import aes
import aes_obuser as user
import case
import vdi
from case import merge_pokes
from opcodes import DROP_STACK_LONG
from test_aes_gemgraf import GRAF
from test_aes_objtext import tedinfo, text_of

OB_FORMAT, OB_USER, FAR_CALL = "AES_ROM_OB_FORMAT", "AES_ROM_OB_USER", "AES_ROM_FAR_CALL"
L, W, IMAGE = vdi.LONG_ARG, vdi.WORD_ARG, vdi.IMAGE_ARG
aes.declare_alcyon(OB_FORMAT, None, (IMAGE, W, L, L, L))
aes.declare_alcyon(OB_USER, aes.LONG_ANSWER, (IMAGE, L, W, L, L, W, W))
aes.declare_alcyon(FAR_CALL, aes.LONG_ANSWER, (IMAGE, L, L))

# just_draw's three buffers, which every ob_format call of its passes (and the AES's text globals beside them).
RAW, TMPLT, OUT = aes.AES_RAWSTR, aes.AES_TMPLT, aes.AES_FMTSTR
BUFFER_BYTES = aes.AES_TEXT_BUFFER_BYTES
for _buffer, _why in ((RAW, "ob_format's raw text"), (TMPLT, "ob_format's template"), (OUT, "ob_format's output")):
    aes.declare_case_field(_buffer, BUFFER_BYTES, _why)
STALE_OUT = {OUT: bytes([vdi.FILL]) * BUFFER_BYTES}
LEFT, RIGHT, CENTRED = 0, aes.OB_FORMAT_RIGHT, GRAF["GSX_JUST_CENTRE"]      # TE_LEFT, TE_RIGHT, TE_CNTR
EMPTY_MARK, PLACEHOLDER = bytes([aes.OB_FORMAT_EMPTY_MARK]), bytes([aes.OB_FORMAT_PLACEHOLDER])
NUL = b"\x00"


# ---- the snapshot's editable text fields ---------------------------------------------------------------------------
def desk_tree(index):
    return aes.resource_tree(index, application_global=aes.AES_DESK_APP_GLOBAL)


SELECTOR = aes.resource_tree(0)
# The desk's file, disk and folder information dialogs (read from their templates), and its tree 6, which holds the
# desk's other 38-placeholder field.
DESK_INFO, DESK_DISK, DESK_FOLDER, DESK_TREE_6 = desk_tree(1), desk_tree(2), desk_tree(3), desk_tree(6)


def string_at(image, at):
    """The NUL-ended string at `at`, its NUL left off."""
    return text_of(image, at)[:-len(NUL)]


def field(tree, index, image=BASE_IMAGE):
    """(te_just, raw text, template) of an editable text object."""
    te = tedinfo(tree, index, image)
    return (aes.read_field(image, "TE", "JUST", te), string_at(image, aes.read_field(image, "TE", "PTEXT", te)),
            string_at(image, aes.read_field(image, "TE", "PTMPLT", te)))


# (tree, object): the selector's directory path (38 placeholders) and selection (8.3), one of its drive rows, and the
# desk's name/size/date/time fields — left- and right-justified, a template with text round its placeholders.
REAL_FIELDS = {
    "the selector's path": (SELECTOR, 2),
    "the selector's selection": (SELECTOR, 3),
    "a selector drive row": (SELECTOR, 12),
    "the desk's file name": (DESK_INFO, 2),
    "the desk's size, right": (DESK_INFO, 3),
    "the desk's date, right": (DESK_INFO, 4),
    "the desk's time, right": (DESK_INFO, 5),
    "the desk's drive letter": (DESK_DISK, 2),
    "the desk's 38-placeholder field": (DESK_TREE_6, 3),
}


def seeded_raw(tree, index, text):
    """The raw text the desk's inf_sset leaves in the field for `text` (`aes_obuser.seeded_raw_pokes`)."""
    (raw,) = user.seeded_raw_pokes(tree, index, text).values()
    return raw[:-len(NUL)]


# (tree, object, text): fields as the desk fills them. A name exactly the template's placeholders long, a size shorter
# than its right-justified field and one longer, a time the field's width.
SEEDED_FIELDS = {
    "a file name": (DESK_INFO, 2, b"README  TXT"),
    "a short size, right": (DESK_INFO, 3, b"12345"),
    "a size too long, right": (DESK_INFO, 3, b"1234567890"),
    "a time, right": (DESK_INFO, 5, b"0930am"),
    "a folder's name": (DESK_FOLDER, 2, b"AUTO"),
}


def buffers(raw, tmplt):
    """just_draw's buffers as its lstcpys leave them: the raw text and template copied in, the output STALE."""
    return merge_pokes({RAW: raw + NUL, TMPLT: tmplt + NUL}, STALE_OUT)


def model(image, just, raw, tmplt, out):
    """ob_format over a COPY of `image`, byte by byte in the ROM's order (so an overlap reads what it stored): `{address:
    byte}` of every byte it stored, as the memory holds it after. Addresses on the 24-bit bus; every step a longword
    sum."""
    memory = bytearray(image)
    stored = set()

    def at(address):
        return address & 0xFFFFFF

    def store(address, value):
        memory[at(address)] = value
        stored.add(at(address))

    def length(address):
        n = 0
        while memory[at(address + n)]:
            n += 1
        return n
    if memory[at(raw)] == EMPTY_MARK[0]:
        store(raw, 0)
    template_length, raw_length = length(tmplt), length(raw)
    store(out + template_length, 0)
    step = 1
    if just == RIGHT:
        step = -1
        out, tmplt, raw = out + template_length - 1, tmplt + template_length - 1, raw + raw_length - 1
    template_end, raw_end = tmplt + step * template_length, raw + step * raw_length
    while tmplt != template_end:
        if memory[at(tmplt)] != PLACEHOLDER[0]:
            store(out, memory[at(tmplt)])
        elif raw != raw_end:
            store(out, memory[at(raw)])
            raw += step
        else:
            store(out, PLACEHOLDER[0])
        out, tmplt = out + step, tmplt + step
    return {address: memory[address] for address in stored}


def ob_format(just, pokes, raw=RAW, tmplt=TMPLT, out=OUT, **kwargs):
    return aes.run_function(OB_FORMAT, (just, raw, tmplt, out), aes.leaf_machine(onto=pokes), **kwargs)


def assert_modelled(result, just, raw=RAW, tmplt=TMPLT, out=OUT):
    """The run's memory where the model wrote: every byte the model's merge moved, as the ROM's run left it."""
    staged = make_image(result.staged)
    expected = model(staged, just, raw, tmplt, out)
    moved = sorted(address for address, byte in expected.items() if byte != staged[address])
    assert moved, "the model wrote nothing"
    assert {a: result.final[a] for a in moved} == {a: expected[a] for a in moved}


# ---- ob_format over real data --------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(REAL_FIELDS))
def test_ob_format_merges_each_real_field(name):
    """Each raw text starts '@', so it is cleared and the merge runs with it spent: every placeholder stays '_', and
    the template's other bytes are copied — right-justified fields walked from their ends."""
    just, raw, tmplt = field(*REAL_FIELDS[name])
    assert raw[:1] == EMPTY_MARK
    result = ob_format(just, buffers(raw, tmplt))
    assert string_at(result.final, OUT) == tmplt
    assert result.after(RAW, 1) == NUL
    assert_modelled(result, just)


@pytest.mark.parametrize("name", sorted(SEEDED_FIELDS))
def test_ob_format_merges_a_raw_text_the_desk_set(name):
    tree, index, text = SEEDED_FIELDS[name]
    just, _raw, tmplt = field(tree, index)
    raw = seeded_raw(tree, index, text)
    assert raw == text and raw[:1] != EMPTY_MARK
    result = ob_format(just, buffers(raw, tmplt))
    assert_modelled(result, just)


def test_a_left_field_fills_its_placeholders_from_the_left():
    result = ob_format(LEFT, buffers(b"AUTO", b"Folder Name: ________.___"))
    assert string_at(result.final, OUT) == b"Folder Name: AUTO____.___"


def test_a_right_field_fills_its_placeholders_from_the_right_and_drops_what_does_not_fit():
    result = ob_format(RIGHT, buffers(b"1234567890", b"Size:  ________"))
    assert string_at(result.final, OUT) == b"Size:  34567890"
    result = ob_format(RIGHT, buffers(b"12345", b"Size:  ________"))
    assert string_at(result.final, OUT) == b"Size:  ___12345"


def test_a_centred_field_is_merged_as_a_left_one():
    """Only OB_FORMAT_RIGHT walks backwards: TE_CNTR (the BOXTEXT just_draw centres) merges from the left."""
    result = ob_format(CENTRED, buffers(b"AB", b"__.__"))
    assert string_at(result.final, OUT) == b"AB.__"


@pytest.mark.parametrize("just", (0x0101, 5, -1), ids=("$0101: its low byte 1", "5: its low bit set", "-1"))
def test_only_the_whole_word_1_merges_from_the_right(just):
    """ob_format tells OB_FORMAT_RIGHT apart by a WORD compare ($fe99de cmpi.w #1,8(a6)): an application's te_just whose
    low byte or low bits match it, but whose word does not, merges from the left."""
    result = ob_format(just, buffers(b"12", b"__:__"))
    assert string_at(result.final, OUT) == b"12:__"


def test_only_a_leading_at_sign_empties_the_raw_text():
    result = ob_format(LEFT, buffers(b"A@B", b"____"))
    assert string_at(result.final, OUT) == b"A@B_"
    assert string_at(result.final, RAW) == b"A@B"


@pytest.mark.parametrize("just", (LEFT, RIGHT), ids=("left", "right"))
def test_an_empty_template_only_terminates_the_output(just):
    """No template byte: `out[0]` := NUL and the walk ends before its first byte — right-justified, its pointers stepped
    back one below each buffer and never used."""
    result = ob_format(just, buffers(b"ABC", b""))
    assert result.after(OUT, 2) == NUL + bytes([vdi.FILL])


# ---- ob_format's ORDER: what each overlap reads back -------------------------------------------------------------
def test_the_at_sign_is_cleared_before_the_template_is_measured():
    """The raw text IS the template: clearing its '@' empties the template too, so nothing is merged — a template
    measured first would have copied four bytes."""
    at = aes.BLOCKS_AT
    result = ob_format(LEFT, merge_pokes({at: b"@___" + NUL}, STALE_OUT), raw=at, tmplt=at)
    assert result.after(OUT, 1) == NUL
    assert_modelled(result, LEFT, raw=at, tmplt=at)


def test_a_forward_merge_reads_the_template_byte_it_just_stored():
    """The output one byte above the template: each byte stored is the template's NEXT byte, read after — so the
    template's first byte runs through the whole field ("X___" → "XXXX"), and its NUL, stored first, lies past it."""
    at = aes.BLOCKS_AT
    result = ob_format(LEFT, merge_pokes({at: b"X___" + NUL}, buffers(b"", b"")), raw=RAW, tmplt=at, out=at + 1)
    assert string_at(result.final, at) == b"XXXXX"
    assert_modelled(result, LEFT, raw=RAW, tmplt=at, out=at + 1)


def test_the_output_s_nul_is_stored_after_the_raw_text_is_measured():
    """The output's NUL lands on the raw text's third byte AFTER its length was taken: the walk still counts five raw
    bytes, and reads the NUL it stored as the third ("AB\\0DE" merged)."""
    at = aes.BLOCKS_AT
    result = ob_format(LEFT, merge_pokes({at: b"ABCDE" + NUL}, buffers(b"", b"_____")), raw=at, out=at + 2 - 5)
    assert_modelled(result, LEFT, raw=at, out=at + 2 - 5)


def test_a_right_merge_over_its_own_raw_text():
    """Right-justified, the output laid over the raw text one byte lower: each byte the walk stores is one the raw walk
    has already passed — or is about to read."""
    at = aes.BLOCKS_AT
    result = ob_format(RIGHT, merge_pokes({at: b"12345" + NUL}, buffers(b"", b"__:___")), raw=at, out=at - 1)
    assert_modelled(result, RIGHT, raw=at, out=at - 1)


# ---- ob_format: the 24-bit bus, and the Line-F door ----------------------------------------------------------------
@pytest.mark.parametrize("just", (LEFT, RIGHT), ids=("left", "right"))
def test_ob_format_puts_all_three_pointers_on_the_24_bit_bus(just):
    pokes = buffers(b"123", b"Size: _____")
    result = ob_format(just, pokes, raw=RAW | aes.BUS_TAG, tmplt=TMPLT | aes.BUS_TAG, out=OUT | aes.BUS_TAG)
    expected = ob_format(just, pokes)
    assert result.after(OUT, BUFFER_BYTES) == expected.after(OUT, BUFFER_BYTES)


# ob_format's two call words: ob_edit's ($f92c, the door's default — the most callers) and just_draw's ($f13c).
CALL_WORDS = sorted(aes.line_f_call_sites(OB_FORMAT))


@pytest.mark.parametrize("word", CALL_WORDS, ids=[f"${word:04x}" for word in CALL_WORDS])
@pytest.mark.parametrize("name", ("the selector's path", "the desk's size, right"))
def test_ob_format_through_line_f(name, word, monkeypatch):
    monkeypatch.setattr(aes, "line_f_call_word", lambda _name: word)
    just, raw, tmplt = field(*REAL_FIELDS[name])
    result = ob_format(just, buffers(raw, tmplt), through_line_f=True)
    assert result.word(aes.LINE_F_CALLER_AT + len(DROP_STACK_LONG)) == word, "the caller makes the call by this word"
    assert string_at(result.final, OUT) == tmplt


# ---- far_call ------------------------------------------------------------------------------------------------------
PARM = 0x0012_3456
ANSWERS = {"zero": 0, "SELECTED": 1 << aes.OB_STATE_SELECTED_BIT, "a whole longword": 0x8765_0003}


def far_call(code, parm, answer, **kwargs):
    return aes.run_function(FAR_CALL, (code, parm), aes.leaf_machine(onto=user.pointer_logger_pokes(answer)),
                            hook=user.pointer_logger_hook(answer), **kwargs)


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("answer", sorted(ANSWERS))
def test_far_call_calls_the_routine_over_its_longword_and_answers_its_d0(answer, through_line_f):
    result = far_call(user.POINTER_LOGGER_AT, PARM, ANSWERS[answer], through_line_f=through_line_f)
    assert user.logged_long(result.final) == PARM
    assert result.long_answer() == ANSWERS[answer]


def test_far_call_jumps_through_24_address_lines_and_pushes_its_longword_whole():
    """A code pointer with a top byte reaches the routine below it; the longword pushed keeps its own."""
    result = far_call(user.POINTER_LOGGER_AT | aes.BUS_TAG, PARM | aes.BUS_TAG, 1)
    assert user.logged_long(result.final) == PARM | aes.BUS_TAG


# ---- ob_user -------------------------------------------------------------------------------------------------------
USERBLK = aes.BLOCKS_AT
RECT = aes.RECTS_AT
UB_PARM = 0x00AB_CDEF
OBJECT = 3                                          # the selector's selection field, as the USERDEF's host object
SCREEN_RECT = (40, 59, 96, 8)                       # a GRECT on the screen, every word distinct
SNAPSHOT_CLIP = tuple(aes.signed(case.word_in(BASE_IMAGE, at))
                      for at in (aes.AES_GL_XCLIP, aes.AES_GL_YCLIP, aes.AES_GL_WCLIP, aes.AES_GL_HCLIP))
CURR, NEW = 0, 1 << aes.OB_STATE_SELECTED_BIT


def ob_user_pokes(answer, code=user.USERDEF_AT, parm=UB_PARM, rect=SCREEN_RECT, onto=None):
    return aes.leaf_machine(onto=user.userdef_pokes(answer, merge_pokes(
        aes.userblk_pokes(USERBLK, CODE=code, PARM=parm), aes.grect_pokes(RECT, *rect), onto)))


def ob_user(answer, *, tree=SELECTOR, rect=RECT, userblk=USERBLK, curr=CURR, new=NEW, pokes=None, **kwargs):
    return aes.run_function(OB_USER, (tree, OBJECT, rect, userblk, curr, new), pokes or ob_user_pokes(answer),
                            hook=user.userdef_hook(answer), **kwargs)


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("answer", sorted(ANSWERS))
def test_ob_user_hands_the_routine_its_parmblk_and_answers_its_d0(answer, through_line_f):
    result = ob_user(ANSWERS[answer], through_line_f=through_line_f)
    assert user.logged_parmblk(result.final) == {"tree": SELECTOR, "object": OBJECT, "prevstate": CURR, "currstate": NEW,
                                                 "rect": SCREEN_RECT, "clip": SNAPSHOT_CLIP, "parm": UB_PARM}
    assert result.long_answer() == ANSWERS[answer]


def test_ob_user_hands_on_the_two_states_as_given():
    """The state words as its caller pushed them — ob_change's old and new, just_draw's the same one twice — signed."""
    result = ob_user(0, curr=-2, new=0x7F)
    logged = user.logged_parmblk(result.final)
    assert (logged["prevstate"], logged["currstate"]) == (-2, 0x7F)


def test_ob_user_hands_on_the_clip_as_it_stands():
    """A staged clip, every word distinct, read at the call — gsx_gclip's four words."""
    clip = aes.field_pokes("AES", GL_XCLIP=7, GL_YCLIP=-9 & 0xFFFF, GL_WCLIP=300, GL_HCLIP=0)
    result = ob_user(0, pokes=ob_user_pokes(0, onto=clip))
    assert user.logged_parmblk(result.final)["clip"] == (7, -9, 300, 0)


def test_ob_user_reads_its_pointers_through_24_address_lines_and_hands_on_its_values_whole():
    """The GRECT, the USERBLK and the routine reached with top bytes; the tree and ub_parm — values, never addressed
    here — handed to the routine with theirs."""
    result = ob_user(1, tree=SELECTOR | aes.BUS_TAG, rect=RECT | aes.BUS_TAG, userblk=USERBLK | aes.BUS_TAG,
                     pokes=ob_user_pokes(1, code=user.USERDEF_AT | aes.BUS_TAG, parm=UB_PARM | aes.BUS_TAG))
    logged = user.logged_parmblk(result.final)
    assert (logged["tree"], logged["parm"], logged["rect"]) == (SELECTOR | aes.BUS_TAG, UB_PARM | aes.BUS_TAG,
                                                                 SCREEN_RECT)
    assert result.long_answer() == 1


# ---- Tier 3: every routine's worst realistic row, and one each through its frame -----------------------------------
for _name in ("the selector's path", "the desk's size, right", "the desk's file name"):
    _just, _raw, _tmplt = field(*REAL_FIELDS[_name])
    aes.register(_name, OB_FORMAT, (_just, RAW, TMPLT, OUT), aes.leaf_machine(onto=buffers(_raw, _tmplt)))
for _name in ("a file name", "a size too long, right"):
    _tree, _index, _text = SEEDED_FIELDS[_name]
    _just, _raw, _tmplt = field(_tree, _index)
    aes.register(f"{_name}, set by the desk", OB_FORMAT, (_just, RAW, TMPLT, OUT),
                 aes.leaf_machine(onto=buffers(seeded_raw(_tree, _index, _text), _tmplt)))
# The dearest shape: every placeholder taking the raw-copy arm — the selector's path field holding a path as long as
# its 38 placeholders, as fs_input sets one.
FULL_PATH = b"A:\\GAMES\\ARCADES\\SHOOTERS\\VERTICAL\\*.*"
_just, _raw, _tmplt = field(*REAL_FIELDS["the selector's path"])
assert len(FULL_PATH) == _tmplt.count(PLACEHOLDER) == len(_tmplt)
aes.register("the selector's path, a full path", OB_FORMAT, (_just, RAW, TMPLT, OUT),
             aes.leaf_machine(onto=buffers(FULL_PATH, _tmplt)))
aes.register("an empty template", OB_FORMAT, (LEFT, RAW, TMPLT, OUT), aes.leaf_machine(onto=buffers(b"ABC", b"")))
aes.register("the selector's path", OB_FORMAT, (LEFT, RAW, TMPLT, OUT),
             aes.leaf_machine(onto=buffers(*field(*REAL_FIELDS["the selector's path"])[1:])), through_line_f=True)
aes.register("a logger answering SELECTED", FAR_CALL, (user.POINTER_LOGGER_AT, PARM),
             aes.leaf_machine(onto=user.pointer_logger_pokes(NEW)), hook=user.pointer_logger_hook(NEW))
aes.register("a USERDEF on the selector answering SELECTED", OB_USER, (SELECTOR, OBJECT, RECT, USERBLK, CURR, NEW),
             ob_user_pokes(NEW), hook=user.userdef_hook(NEW))
aes.register("a USERDEF on the selector", OB_USER, (SELECTOR, OBJECT, RECT, USERBLK, CURR, NEW), ob_user_pokes(NEW),
             through_line_f=True)
