"""The utility layer's MEMORY and STRING helpers (`src/aes/strings.c`) — what their batteries share: the signatures,
the bands their strings and buffers are staged in, and a reader for what a run left there.

Hand 68000 in the ROM, called like Alcyon C over a frame of words and longwords and returning by `rts`, so each is
run through `aes.run_function` — DIRECT (the Tier 3 row) and THROUGH LINE-F by its own call word (the door) — and no
case of them stores the Line-F mask word. Every string is NUL-terminated where it is staged, and every buffer a routine
writes is staged STALE first (`STALE_BYTE`), so a byte the C leaves unwritten differs from the ROM's even where the
attribution pass would not reach it.
"""
import aes
import staging
from aes import LONG_ANSWER, WORD_ANSWER
from case import merge_pokes
from vdi import IMAGE_ARG, LONG_ARG, WORD_ARG

# `aes/strings.h`'s constants, which the C and the `.S` read: parsed, so a case's number is the header's.
CONSTANTS = aes.header_constants("strings.h")
MERGE_SLOT_BYTES = CONSTANTS["MERGE_SLOT_BYTES"]


# ---- the signatures, in frame (push) order ------------------------------------------------------------------------
SIGNATURES = {
    "AES_ROM_MUL_DIV": (WORD_ANSWER, (WORD_ARG, WORD_ARG, WORD_ARG)),
    "AES_ROM_SET_CONTRL_PTR": (None, (IMAGE_ARG, LONG_ARG)),
    "AES_ROM_GET_CONTRL_PTR2": (None, (IMAGE_ARG, LONG_ARG)),
    "AES_ROM_MIN": (WORD_ANSWER, (WORD_ARG, WORD_ARG)),
    "AES_ROM_MAX": (WORD_ANSWER, (WORD_ARG, WORD_ARG)),
    "AES_ROM_TOUPPER": (WORD_ANSWER, (WORD_ARG,)),
    "AES_ROM_LMUL": (LONG_ANSWER, (LONG_ARG, LONG_ARG)),
    "AES_ROM_LDIV": (LONG_ANSWER, (IMAGE_ARG, LONG_ARG, LONG_ARG)),
    "AES_ROM_LSTCPY": (WORD_ANSWER, (IMAGE_ARG, LONG_ARG, LONG_ARG)),
    "AES_ROM_XSTRPIX": (WORD_ANSWER, (IMAGE_ARG, LONG_ARG, LONG_ARG)),
    "AES_ROM_WSET": (None, (IMAGE_ARG, LONG_ARG, WORD_ARG, WORD_ARG)),
    "AES_ROM_XSTRPIX_N": (None, (IMAGE_ARG, LONG_ARG, LONG_ARG, WORD_ARG)),
    "AES_ROM_WCOPY": (None, (IMAGE_ARG, LONG_ARG, LONG_ARG, WORD_ARG)),
    "AES_ROM_WFILL": (None, (IMAGE_ARG, LONG_ARG, WORD_ARG, WORD_ARG)),
    "AES_ROM_LSTRLEN": (WORD_ANSWER, (IMAGE_ARG, LONG_ARG)),
    "AES_ROM_LBCOPY": (None, (IMAGE_ARG, LONG_ARG, LONG_ARG, WORD_ARG)),
    "AES_ROM_MOVS": (None, (IMAGE_ARG, WORD_ARG, LONG_ARG, LONG_ARG)),
    "AES_ROM_BFILL": (None, (IMAGE_ARG, WORD_ARG, WORD_ARG, LONG_ARG)),
    "AES_ROM_STRLEN": (WORD_ANSWER, (IMAGE_ARG, LONG_ARG)),
    "AES_ROM_STREQ": (WORD_ANSWER, (IMAGE_ARG, LONG_ARG, LONG_ARG)),
    "AES_ROM_STRCPY": (LONG_ANSWER, (IMAGE_ARG, LONG_ARG, LONG_ARG)),
    "AES_ROM_STRSCN": (LONG_ANSWER, (IMAGE_ARG, LONG_ARG, LONG_ARG, WORD_ARG)),
    "AES_ROM_STRCAT": (LONG_ANSWER, (IMAGE_ARG, LONG_ARG, LONG_ARG)),
    "AES_ROM_SCASB": (LONG_ANSWER, (IMAGE_ARG, LONG_ARG, WORD_ARG)),
    "AES_ROM_STRCHK": (WORD_ANSWER, (IMAGE_ARG, LONG_ARG, LONG_ARG)),
    "AES_ROM_FMT_STR": (None, (IMAGE_ARG, LONG_ARG, LONG_ARG)),
    "AES_ROM_UNFMT_STR": (None, (IMAGE_ARG, LONG_ARG, LONG_ARG)),
    "AES_ROM_MERGE_STR": (None, (IMAGE_ARG, LONG_ARG, LONG_ARG, LONG_ARG)),
    "AES_ROM_WILDCMP": (WORD_ANSWER, (IMAGE_ARG, LONG_ARG, LONG_ARG)),
}
for _name, (_restype, _argtypes) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, _argtypes)

# ---- where the cases stage ----------------------------------------------------------------------------------------
# THE BAND: the top 2 KB of the AES's window — two string buffers, a template and its parameters, and the staged
# callers of the transcriptions.
BAND_BYTES = 0x800
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + aes.WINDOW_BYTES - BAND_BYTES, BAND_BYTES,
                         "test/aes_strings.py: strings, buffers, templates and callers")
BUFFER_BYTES = 0x200                        # a 256-word row, or a string past the byte counters' wrap
SOURCE_AT = BAND_AT
DESTINATION_AT = SOURCE_AT + BUFFER_BYTES
TEMPLATE_AT = DESTINATION_AT + BUFFER_BYTES
TEMPLATE_BYTES = 0x80
PARAMETERS_AT = TEMPLATE_AT + TEMPLATE_BYTES
PARAMETERS_BYTES = 0x40
ARGUMENT_STRINGS_AT = PARAMETERS_AT + PARAMETERS_BYTES      # the strings a template's %S slots point at
ARGUMENT_STRINGS_BYTES = 0x80
ANSWER_AT = ARGUMENT_STRINGS_AT + ARGUMENT_STRINGS_BYTES     # a longword a routine answers through
CALLERS_AT = ANSWER_AT + 0x10                                # the transcriptions' staged callers, to the band's end
assert CALLERS_AT < BAND_AT + BAND_BYTES

# THE LONG LOOPS: a count from $8000 up — which the byte loops count UNSIGNED and lbcopy's backward loop SIGNED — and
# a word loop whose zero count runs 65536 passes (128 KB stored) need more than any AES band holds: they take the shared
# whole bank above the stack band (`staging.WHOLE_BANK_AT`), dead in the snapshot (`test_boot_snapshot.py` holds it).
WHOLE_BANK_AT = staging.WHOLE_BANK_AT
WHOLE_BANK_BYTES = staging.WHOLE_BANK_BYTES

STALE_BYTE = 0xA5
NUL = b"\0"


def text(at, string):
    """`string` (bytes or str) at `at`, NUL-terminated."""
    data = string.encode("latin-1") if isinstance(string, str) else bytes(string)
    return {at: data + NUL}


def stale(at, length):
    """`length` stale bytes at `at`: a buffer a routine writes, staged so its every unwritten byte shows."""
    return {at: bytes([STALE_BYTE]) * length}


def buffers(source=b"", destination=None, *, source_at=SOURCE_AT, destination_at=DESTINATION_AT):
    """The two string buffers: `source`, NUL-ended, and a stale destination — with the string `destination`, NUL-ended,
    over its start when one is given (an empty one is a lone NUL)."""
    over = text(destination_at, destination) if destination is not None else None
    return merge_pokes(stale(destination_at, BUFFER_BYTES), over, text(source_at, source))


def string_in(image, at, limit=0x10000):
    """The NUL-ended string at `at` in `image`, as bytes."""
    end = bytes(image[at:at + limit]).index(0)
    return bytes(image[at:at + end])


def run(name, arguments, pokes=None, **kwargs):
    """`addrs.<name>` over the frame of `arguments`, staged over `pokes` (`aes.run_function`)."""
    return aes.run_function(name, arguments, pokes or {}, **kwargs)


def register(label, name, arguments, pokes=None, **kwargs):
    """...and the same as a Tier 3 row (`aes.register`)."""
    return aes.register(label, name, arguments, pokes or {}, **kwargs)

# The contrl[] pointer slots a case stages, outside the window (`aes.declare_case_field`).
aes.declare_case_field(aes.AES_GSX_CONTRL_PTR, 2 * aes.LONG_BYTES, "contrl[7..10], the two pointer slots")
aes.declare_case_field(aes.AES_LDIV_REMAINDER, aes.LONG_BYTES, "ldiv's remainder, staged stale")
