"""The USERDEF door: the 68000 routine a case stages as a USERBLK's `ub_code` (or hands far_call), and its host twin.

ob_user ($fe9a46) builds a PARMBLK in its own frame and calls the USERBLK's routine over its ADDRESS through far_call
($fddec6) — `move.l <parm>,-(sp) / jsr (a0)`, the routine's D0 answered back as the object's new state. The PARMBLK's
address differs between the shores (the ROM's stack, the host slot `HOST_SLOT_AES_OB_USER_PARMBLK`), so the routine
records its CONTENTS, never its pointer: `userdef_routine` copies the 30 bytes into a compared LOG and answers a
chosen D0. `pointer_logger` is far_call's own: it logs the longword it is called over (a value, the same on both
shores) and answers the same way.

Off target both reach `staged_call.h`'s call_alcyon_pointer through the register-carrying hook
(`aes.alcyon_object_hook`): the pushed longword in A0's slot, the answer handed back in D0's.

ONE module for every battery that reaches a G_USERDEF (ob_user's own, just_draw's, ob_change's): `userdef_pokes` and
`userdef_hook` stage the routine at `USERDEF_AT` with its log STALE, `logged_parmblk` reads the log back by field.

...and for every battery that merges an editable text (ob_format's own, just_draw's): `seeded_raw_pokes`, the raw text
the ROM's own writer leaves in a real field.
"""
import struct

from harness import BASE_IMAGE, addrs, emu, make_image

import aes
import isr
import vdi
from case import merge_pokes
from test_aes_objtext import INF_SSET, tedinfo, text_of
from opcodes import DBF_D1, LOAD_IMMEDIATE, MOVE_B_A0_TO_A1, MOVEA_L_STACK_A0, RTS

# The band: the routines and their log, in the gap above test_aes_rect_transcription's callers.
BAND_OFFSET = 0x12C0
BAND_BYTES = 0x140
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES, "test/aes_obuser.py: USERDEF routines and their log")
LOG_AT = BAND_AT                                   # the PARMBLK's bytes, or far_call's longword
LOG_BYTES = aes.PARM_BYTES
ROUTINE_SLOT_BYTES = 0x40
USERDEF_AT = LOG_AT + -(-LOG_BYTES // aes.LONG_BYTES) * aes.LONG_BYTES     # past the log, longword-aligned
POINTER_LOGGER_AT = USERDEF_AT + ROUTINE_SLOT_BYTES
assert LOG_AT + LOG_BYTES <= USERDEF_AT and POINTER_LOGGER_AT + ROUTINE_SLOT_BYTES <= BAND_AT + BAND_BYTES

FIRST_ARGUMENT = 4                                 # the routine's 4(sp): the longword far_call pushed
DBF_TO_PREVIOUS_WORD = -4                          # `dbf` back over the one-word copy before it
STALE_LOG = {LOG_AT: bytes([vdi.FILL]) * LOG_BYTES}


def userdef_routine(answer):
    """(68000 bytes, host effect) of the USERDEF routine: the PARMBLK its 4(sp) names copied byte by byte into the log,
    then D0 := `answer`."""
    code = (vdi.pack_words(MOVEA_L_STACK_A0, FIRST_ARGUMENT) + LOAD_IMMEDIATE["a1"] + struct.pack(">I", LOG_AT)
            + LOAD_IMMEDIATE["d1"] + struct.pack(">I", LOG_BYTES - 1)
            + vdi.pack_words(MOVE_B_A0_TO_A1, DBF_D1, DBF_TO_PREVIOUS_WORD) + isr.answer_d0(answer) + RTS)
    assert len(code) <= ROUTINE_SLOT_BYTES

    def effect(buf, registers):
        parmblk = registers[isr.REGISTER["a0"]]
        isr.poke(buf, LOG_AT, bytes(buf[parmblk:parmblk + LOG_BYTES]))
        isr.set_d0(registers, answer)
    return code, effect


def pointer_logger(answer):
    """(68000 bytes, host effect) of far_call's routine: the longword it is called over into the log, D0 := `answer`."""
    code, effect = isr.frame_long_logger(LOG_AT, answer)
    assert len(code) <= ROUTINE_SLOT_BYTES
    return code, effect


def userdef_pokes(answer, onto=None):
    """The USERDEF routine answering `answer` at USERDEF_AT, its log STALE, over `onto`."""
    code, _effect = userdef_routine(answer)
    return merge_pokes(onto, {USERDEF_AT: code}, STALE_LOG)


def userdef_hook(answer):
    """...and its host twin, as `aes.run_function`'s `hook` (or one of `aes.doors`)."""
    return aes.alcyon_object_hook({USERDEF_AT: userdef_routine(answer)})


def pointer_logger_pokes(answer, onto=None):
    code, _effect = pointer_logger(answer)
    return merge_pokes(onto, {POINTER_LOGGER_AT: code}, STALE_LOG)


def pointer_logger_hook(answer):
    return aes.alcyon_object_hook({POINTER_LOGGER_AT: pointer_logger(answer)})


def logged_parmblk(image):
    """The PARMBLK the routine logged, by field (`aes/objects.h`'s PARM_*, at their tagged widths, named in lower
    case): a word signed, a GRECT as its four signed words."""
    logged = {}
    for name, spec in aes.FIELDS["PARM"].items():
        value = aes.read_field(image, "PARM", name, LOG_AT)
        if spec.count:
            value = struct.unpack(f">{len(value) // aes.WORD_BYTES}h", bytes(value))
        elif spec.width == aes.WORD_BYTES:
            value = aes.signed(value)
        logged[name.lower()] = value
    return logged


def logged_long(image):
    """The longword far_call's routine logged."""
    return struct.unpack(">I", bytes(image[LOG_AT:LOG_AT + aes.LONG_BYTES]))[0]


# ---- an editable text's raw text, as the desk sets it ------------------------------------------------------------
# Every raw text in both resources starts '@' (an empty field), so a raw text that does NOT is seeded by the ROM's own
# writer: the desk's inf_sset ($fecfb2) run on the oracle over the real field — fs_sset ($fecf84) lstcpy's the text it
# is handed into the TEDINFO's te_ptext.
def seeded_raw_pokes(tree, index, text):
    """`{te_ptext: the raw text and its NUL}` as inf_sset leaves object `index`'s field for `text`."""
    at = aes.BLOCKS_AT
    final, _writes, regs = emu.run(make_image(aes.staged(INF_SSET, (tree, index, at),
                                                         aes.leaf_machine(onto={at: text + b"\0"}))),
                                   addrs.AES_ROM_INF_SSET)
    assert not regs.get("writes_truncated"), "inf_sset's run overflowed the write ledger"
    raw = aes.read_field(final, "TE", "PTEXT", tedinfo(tree, index))
    assert aes.read_field(BASE_IMAGE, "TE", "PTEXT", tedinfo(tree, index)) == raw, "inf_sset moved the field's te_ptext"
    return {raw: text_of(final, raw)}
