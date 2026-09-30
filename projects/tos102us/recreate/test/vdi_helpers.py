"""What the VDI's PURE-HELPER batteries share (`src/vdi/helpers.c`): the Alcyon call door and a band.

AN ALCYON C CALL is what most of these helpers are: the caller pushes WORD arguments (an Alcyon `int`
is 16 bits) and reads the answer out of D0's LOW WORD — every call site moves D0.w on, and none reads
the high word (`vdi/helpers.h`). So `run_call` stages the words where `jsr` leaves them for the ROM
(`case.word_args`), calls the C core with the same values as C arguments, and compares D0 at
`WORD_RESULT` bits. The THREE REGISTER ROUTINES (`sort_words`, `clamp_mouse`, `get_kbshift`) go through
`vdi.declare_primitive` / `vdi.run_primitive` instead, which is the one register map `bench/tier3.py`
reads too.

`bench/tier3.py` DERIVES its `CALL` entries for the Alcyon calls from the signatures below (`vdi.ALCYON`),
decoding each argument out of the same frame at the offset the widths before it add up to — so the two
halves of the one fact are stated once.
"""
import ctypes
import functools
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from harness import BASE_IMAGE, LIB, _lib, addrs, emu

import abi
import case
import gemdos
import routines
import transcription
import vdi
from vdi import IMAGE_ARG, LONG_ARG, LONG_BYTES, WORD_ARG, WORD_BYTES, WORD_RESULT
from opcodes import DROP_STACK_BYTES, LOAD_IMMEDIATE, PUSH_RETURN_PC, PUSH_STACK_LONG, RTE, RTS

# `vdi/helpers.h`'s own constants — the scaler's markers — parsed as `test/vdi.py` parses its headers.
CONSTANTS = addrs.parse(Path(__file__).resolve().parents[1] / "include" / "vdi" / "helpers.h",
                        known={**addrs.ADDRS, **vdi.CONSTANTS})
sys.modules[__name__].__dict__.update(CONSTANTS)

# The C signature of every ALCYON core `src/vdi/helpers.c` reconstructs, declared through `vdi.declare_alcyon`
# (the one registry `bench/tier3.py` and the shipped build's glue read). The words are declared SIGNED where
# the C is `int16_t` — Apple's arm64 ABI leaves a caller to extend a short argument, so a value passed
# without its declared type would reach the core as the wrong word.
for _name, _restype, _argtypes in (
        ("VDI_ROM_VEC_LEN", ctypes.c_uint16, (WORD_ARG, WORD_ARG)),
        ("VDI_ROM_SMUL_DIV", ctypes.c_uint16, (WORD_ARG, WORD_ARG, WORD_ARG)),
        ("VDI_ROM_ISIN", ctypes.c_uint16, (IMAGE_ARG, WORD_ARG)),
        ("VDI_ROM_ICOS", ctypes.c_uint16, (IMAGE_ARG, WORD_ARG)),
        ("VDI_ROM_CLIP_CODE", ctypes.c_uint16, (IMAGE_ARG, WORD_ARG, WORD_ARG)),
        ("VDI_ROM_CLC_NSTEPS", None, (IMAGE_ARG,)),
        ("VDI_ROM_QUAD_XFORM", None, (IMAGE_ARG, WORD_ARG, WORD_ARG, WORD_ARG, LONG_ARG, LONG_ARG)),
        ("VDI_ROM_CLC_DDA", ctypes.c_uint16, (IMAGE_ARG, WORD_ARG, WORD_ARG)),
        ("VDI_ROM_ACT_SIZ", ctypes.c_uint16, (IMAGE_ARG, WORD_ARG)),
        ("VDI_ROM_COPY_NAME", None, (IMAGE_ARG, LONG_ARG, LONG_ARG)),
        ("VDI_ROM_FONT_BYTESWAP", None, (IMAGE_ARG,)),
        ("VDI_ROM_S_FA_ATTR", None, (IMAGE_ARG,)),
        ("VDI_ROM_R_FA_ATTR", None, (IMAGE_ARG,))):
    vdi.declare_alcyon(_name, _restype, _argtypes)
# ...and `gemdos_call`, whose frame is (function.w, argument.l) and whose C takes one more first: the RETURN SITE
# the ROM finds on the stack under that frame (its caller's `jsr`), which the host build has no stack to hold. It
# is the one host argument (`vdi.declare_alcyon`), so a C caller's glue pushes the frame alone.
vdi.declare_alcyon("VDI_ROM_GEMDOS_CALL", LONG_ARG, (IMAGE_ARG, LONG_ARG, vdi.UWORD_ARG, LONG_ARG), host_arguments=1)

# ...and the host signatures of the cores that are NOT Alcyon calls: the three REGISTER ROUTINES, whose
# contracts are declared below and held to these by `test_tier3.py`.
REGISTER_SIGNATURES = {
    "vdi_sort_words": (None, (IMAGE_ARG, LONG_ARG, LONG_ARG)),
    "vdi_clamp_mouse": (LONG_ARG, (IMAGE_ARG, LONG_ARG, LONG_ARG, ctypes.POINTER(LONG_ARG))),
    "vdi_get_kbshift": (LONG_ARG, (IMAGE_ARG, LONG_ARG)),
}
for _symbol, (_restype, _argtypes) in REGISTER_SIGNATURES.items():
    getattr(_lib, _symbol).restype = _restype
    getattr(_lib, _symbol).argtypes = list(_argtypes)

# THE REGISTER ROUTINES' CONTRACTS, declared in this SHARED module rather than in the battery that runs
# each, so `bench/tier3.py` — which builds its calls from `vdi.PRIMITIVES` — sees them whichever battery
# was imported first.
vdi.declare_primitive("VDI_ROM_SORT_WORDS", arguments=("d0", "a0"))
vdi.declare_primitive("VDI_ROM_CLAMP_MOUSE", arguments=("d0", "d1"), results=("d0", "d1"))
vdi.declare_primitive("VDI_ROM_GET_KBSHIFT", arguments=("d0",), results=("d0",))
# ...and the one core with no Tier 3 C row: `vdi_gemdos_call`'s cases are registered UNPRICED
# (`test_vdi_helpers_gemdos.py` says why).
UNPRICED_CORES = ("vdi_gemdos_call",)


def core(name):
    """The C core of `addrs.<name>`: `VDI_ROM_SMUL_DIV` -> `vdi_smul_div` (`routines.core_symbol`, which is how
    `bench/tier3.py` derives the symbol too)."""
    return getattr(_lib, routines.core_symbol(name))


def uses_image(name):
    """Whether the core's first argument is the image (every one but the two pure arithmetic ones)."""
    return vdi.ALCYON[name].argtypes[:1] == (IMAGE_ARG,)


def run_call(name, frame, arguments=(), pokes=None, **kwargs):
    """The Alcyon helper `addrs.<name>`, entered by `jsr` with the argument `frame` (`case.args`-style
    pokes at `abi.FIRST_ARG`) over `pokes`, against its core called with `arguments` — the same values
    as C arguments. Answers a `vdi.Result`; `kwargs` are `case.run`'s."""
    function = core(name)
    returns = vdi.ALCYON[name].restype
    staged = vdi.merge_pokes(pokes, frame)

    def glue(_lib_, buf):
        return function(buf, *arguments) if uses_image(name) else function(*arguments)

    info = case.run(getattr(addrs, name), {"_pokes": staged}, glue,
                    width=WORD_RESULT if returns is not None else case.NO_RESULT, **kwargs)
    return vdi.Result(info, staged)


def answer(result):
    """The word a helper answered, as the signed Alcyon `int` its caller reads."""
    return struct.unpack(">h", struct.pack(">H", result.info["regs"]["d0"] & 0xFFFF))[0]


IMAGE_BYTES = len(BASE_IMAGE)
FRESH_IMAGE = f"buf = (ctypes.c_uint8 * {IMAGE_BYTES})()"
CHILD_SECONDS = 60      # how long a child is given before `subprocess.TimeoutExpired` ends it


def refusal(symbol, argtypes, arguments, *, prelude=FRESH_IMAGE, seconds=CHILD_SECONDS):
    """What the host core `symbol` says when called with `arguments` in a CHILD process, where its
    refusal — `recreate_not_reconstructed`, an `abort()` — can end the run without ending pytest's.
    `arguments` is Python source; `prelude` is the statements before the call, which bind `buf` (a fresh
    image by default). Answers `(returncode, stderr)`; a child still running after `seconds` is killed and
    raises `subprocess.TimeoutExpired`."""
    probe = (f"import ctypes, mmap; lib = ctypes.CDLL({str(LIB)!r}); {prelude}; "
             f"lib.{symbol}.argtypes = [{', '.join(argtypes)}]; lib.{symbol}({arguments})")
    run = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=seconds)
    return run.returncode, run.stderr


def _io_declaration(io_seed):
    """The child's `g_io_reset` call declaring the I/O bytes `io_seed` ({address: byte}), encoded as `case.run`
    encodes them — routed by `emu.seed_split`, all three columns from `emu.io_seed_entries`. The child installs
    that one table alone, so a Phase-7 named slot or a declared sequence, which have installers of their own,
    is refused rather than dropped."""
    named, declared, sequences = emu.seed_split(None, io_seed)
    assert not named and not sequences, (
        f"refusal_over installs plain I/O bytes only, not the named slots {named} or the sequences {sequences}")
    addresses, values, writeback = emu.io_seed_entries(declared)
    count = len(addresses)
    return (f"lib.g_io_reset((ctypes.c_uint32 * {count})(*{list(addresses)}), (ctypes.c_uint8 * {count})(*{list(values)}), "
            f"(ctypes.c_uint8 * {count})(*{list(writeback)}), {count})")


def refusal_over(symbol, pokes, io_seed=None, *, seconds=CHILD_SECONDS, read_back=True):
    """What the host core `symbol(image)` says over the image `pokes` stage, with the I/O bytes `io_seed`
    declared, in a CHILD process (`refusal`) — and the image AS THE CHILD LEFT IT: the child's `buf` is a
    SHARED mapping of the staged image's file, so every store the core made before it halted is still there
    for the caller to read. Answers `(returncode, stderr, image)`; a caller that reads no byte of the image
    passes `read_back=False` and is answered None for it, rather than the whole machine read back."""
    image = bytes(vdi.make_image(pokes))
    assert len(image) == IMAGE_BYTES
    with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as handle:
        handle.write(image)
    try:
        prelude = (f"image_file = open({handle.name!r}, 'r+b'); "
                   f"buf = (ctypes.c_uint8 * {IMAGE_BYTES}).from_buffer(mmap.mmap(image_file.fileno(), {IMAGE_BYTES}))")
        if io_seed:
            prelude += f"; {_io_declaration(io_seed)}"
        returncode, stderr = refusal(symbol, ["ctypes.c_void_p"], "buf", prelude=prelude, seconds=seconds)
        return returncode, stderr, Path(handle.name).read_bytes() if read_back else None
    finally:
        Path(handle.name).unlink()


# ---- the band these batteries stage buffers in ----------------------------------------------------
# A kilobyte at +$1000 of the VDI's window: above the bands `test/vdi.py` lays from its base, below
# `test/vdi_raster.py`'s at +$1800 — `vdi.SPAN` refuses an overlap either way — and laid out as below.
BAND_OFFSET = 0x1000
BAND_BYTES = 0x400
BAND_AT = vdi.SPAN.band(BAND_OFFSET, BAND_BYTES, "test/vdi_helpers.py: words, names and forms")
SORT_AT = BAND_AT                               # sort_words' array, 16 words
ANSWERS_AT = BAND_AT + 0x20                     # quad_xform's two answer words
NAME_AT = BAND_AT + 0x40                        # a font name and room to copy it to, 0x80
FONT_FORM_AT = BAND_AT + 0xC0                   # a font form to byte-swap, 0x40
FRAME_CALLER_AT = BAND_AT + 0x100               # the Alcyon transcriptions' staged caller (below)
TRAP_HANDLER_AT = BAND_AT + 0x120               # ...and gemdos_call's staged `trap #1` handler
TRAP_LEDGER_AT = BAND_AT + 0x140                # ...and the words it records
RASTER_FORM_BYTES = 0x100
SOURCE_FORM_AT = BAND_AT + 0x200                # vr_trnfm's two raster forms
DESTINATION_FORM_AT = SOURCE_FORM_AT + RASTER_FORM_BYTES


# ---- the TRANSCRIPTIONS (`src/vdi/helpers.S`) ------------------------------------------------------
# `transcription.run_transcription` enters both sides at a staged caller that jumps through the routine longword
# at `abi.FIRST_ARG` with the sentinel under it — which is a register routine's `jsr`, but leaves an
# ALCYON routine reading the routine's own address where its first argument should be. So the Alcyon
# helpers get a caller of their own: the argument words are staged ABOVE that longword
# (`FRAME_ARGUMENTS_AT`) and the caller pushes two longwords of them, calls, and drops them — a `jsr`
# with an eight-byte frame, which is every one of these routines' (three words at most). It touches no
# register, and what it costs comes off both columns.
FRAME_ARGUMENTS_AT = abi.FIRST_ARG + LONG_BYTES
FRAME_ARGUMENT_BYTES = 2 * LONG_BYTES
_FROM_ENTRY_SP = 12        # the second argument longword, from the caller's entry SP: sentinel, routine, first
_TO_RETURN = 8             # `pea` to the `lea` after the `rts`, from the `pea`'s own extension word
_TO_ROUTINE = 16           # the routine longword once the two arguments and the return are pushed
FRAME_CALLER_STUB = (PUSH_STACK_LONG + struct.pack(">h", _FROM_ENTRY_SP)      # the second longword
                     + PUSH_STACK_LONG + struct.pack(">h", _FROM_ENTRY_SP)    # ...then the first, now as far up
                     + PUSH_RETURN_PC + struct.pack(">h", _TO_RETURN)
                     + PUSH_STACK_LONG + struct.pack(">h", _TO_ROUTINE)
                     + RTS                                                   # into the routine
                     + DROP_STACK_BYTES + struct.pack(">h", FRAME_ARGUMENT_BYTES)
                     + RTS)
FRAME_CALLER = transcription.staged_caller(FRAME_CALLER_AT, FRAME_CALLER_STUB, (7, 128))


def frame_pokes(frame):
    """A `case.args`-style frame (at `abi.FIRST_ARG`) moved up to where the frame caller reads it."""
    (at, data), = frame.items()
    assert at == abi.FIRST_ARG and len(data) <= FRAME_ARGUMENT_BYTES
    return {FRAME_ARGUMENTS_AT: data}


def _entered(pokes, frame):
    """The caller a transcription goes through — the frame caller for an Alcyon `frame`, `vdi`'s own
    otherwise — and the pokes with that frame where it reads it."""
    if frame is None:
        return transcription.PLAIN_CALLER, pokes
    return FRAME_CALLER, vdi.merge_pokes(pokes, frame_pokes(frame))


def run_transcription(name, pokes, regs=None, frame=None, **kwargs):
    """`transcription.run_transcription`, entered through the frame caller when the routine takes an Alcyon `frame`."""
    caller, staged = _entered(pokes, frame)
    return transcription.run_transcription(name, staged, regs, caller=caller, **kwargs)


def register_transcription(name, label, pokes, regs=None, frame=None):
    """...and the same as a Tier 3 row."""
    caller, staged = _entered(pokes, frame)
    return transcription.register_transcription(name, label, staged, regs, caller=caller)


# ---- a RECORDING TRAP HANDLER, for the one transcription that takes a trap ---------------------------
# gemdos_call's `.S` cannot be compared with the ROM through the real GEMDOS (`test_vdi_helpers_gemdos.py`
# says why), so its rows point the trap's RAM vector at this instead: it APPENDS the caller's function word
# and longword, out of the exception frame, to a LEDGER at `TRAP_LEDGER_AT`, answers `TRAP_ANSWER` (or the
# answer a case stages) in D0 and returns — the same on both sides. The ledger is a pointer to its next free
# entry, then the entries: a routine that traps several times (v_clswk's Mfree per record) leaves every call,
# in order, where a single slot would keep the last alone and let a wrong one before it through.
PUSH_A0 = b"\x2f\x08"                       # move.l  a0,-(sp)
POP_A0 = b"\x20\x5f"                        # movea.l (sp)+,a0
MOVEA_L_ABSOLUTE_A0 = b"\x20\x79"           # movea.l <xxx>.l,a0
MOVE_L_STACK_TO_A0_POSTINC = b"\x20\xef"    # move.l  <d16>(sp),(a0)+
MOVE_W_STACK_TO_A0_POSTINC = b"\x30\xef"    # move.w  <d16>(sp),(a0)+
STORE_A0_ABSOLUTE = b"\x23\xc8"             # move.l  a0,<xxx>.l
FRAME_WORDS_AT = LONG_BYTES + addrs.TRAP_EXCEPTION_FRAME_BYTES     # the caller's words: above the saved A0, SR and PC
TRAP_ANSWER = 0x0001_2340
TRAP_ENTRY_BYTES = WORD_BYTES + LONG_BYTES  # one call: the function word, the longword
TRAP_LEDGER_ENTRIES = 8                     # more calls than any routine here makes
TRAP_ENTRIES_AT = TRAP_LEDGER_AT + LONG_BYTES
TRAP_LAST_ENTRY_AT = TRAP_ENTRIES_AT + (TRAP_LEDGER_ENTRIES - 1) * TRAP_ENTRY_BYTES
TRAP_LEDGER_BYTES = LONG_BYTES + TRAP_LEDGER_ENTRIES * TRAP_ENTRY_BYTES
assert TRAP_LEDGER_AT + TRAP_LEDGER_BYTES <= SOURCE_FORM_AT


def trap_handler_stub(answer=TRAP_ANSWER):
    """The recording handler's instructions, answering `answer` in D0 and leaving every other register as found."""
    return (PUSH_A0 + MOVEA_L_ABSOLUTE_A0 + struct.pack(">I", TRAP_LEDGER_AT)
            + MOVE_L_STACK_TO_A0_POSTINC + struct.pack(">h", FRAME_WORDS_AT)
            + MOVE_W_STACK_TO_A0_POSTINC + struct.pack(">h", FRAME_WORDS_AT + LONG_BYTES)
            + STORE_A0_ABSOLUTE + struct.pack(">I", TRAP_LEDGER_AT) + POP_A0
            + LOAD_IMMEDIATE["d0"] + struct.pack(">I", answer)
            + RTE)


assert TRAP_HANDLER_AT + len(trap_handler_stub()) <= TRAP_LEDGER_AT


def recording_trap_pokes(vector, answer=TRAP_ANSWER):
    """`vector` pointed at the recording handler, which is staged with its ledger empty and its entries FILLed —
    answering `answer` (a caller that goes on to use D0 stages the value the real call would have answered)."""
    return {vector: struct.pack(">I", TRAP_HANDLER_AT), TRAP_HANDLER_AT: trap_handler_stub(answer),
            TRAP_LEDGER_AT: struct.pack(">I", TRAP_ENTRIES_AT)
            + bytes([vdi.FILL]) * (TRAP_LEDGER_BYTES - LONG_BYTES)}


def recording_trap_handler(function, answer=TRAP_ANSWER):
    """The recording handler's HOST TWIN, as a `gemdos.bound_handlers` entry for `function`: the same entry appended
    to the same ledger, and the same answer — so a differential compares every call each side trapped with.

    The ledger's pointer is READ OUT OF THE IMAGE and stored through, so it is bounded first: `buf` is a raw C pointer,
    and a pointer the attribution pass inverted (the ROM's stub stores it back, so it is an output) would send the
    store into host memory. Out of the ledger it is refused by name — the hook fails the case (`address_hook`)."""
    def handler(buf, arguments, _argument_bytes):
        at = case.long_in(buf, TRAP_LEDGER_AT)
        assert TRAP_ENTRIES_AT <= at <= TRAP_LAST_ENTRY_AT, (
            f"the trap ledger's pointer {at:#x} is outside the ledger ({TRAP_ENTRIES_AT:#x}..{TRAP_LAST_ENTRY_AT:#x}): "
            f"the host twin refuses to store through it")
        stores = {at: struct.pack(">HI", function, case.long_in(buf, arguments)),
                  TRAP_LEDGER_AT: struct.pack(">I", at + TRAP_ENTRY_BYTES)}
        for store_at, data in stores.items():
            for offset, byte in enumerate(data):     # byte by byte: `buf` is a C pointer, which takes no slice store
                buf[store_at + offset] = byte
        return answer
    return handler


def trapped_calls(image):
    """The ledger in `image` as `[(function, longword), ...]`, in the order the calls were made."""
    count, spare = divmod(case.long_in(image, TRAP_LEDGER_AT) - TRAP_ENTRIES_AT, TRAP_ENTRY_BYTES)
    assert not spare and 0 <= count <= TRAP_LEDGER_ENTRIES, "the ledger's pointer is not one the handler leaves"
    entries = (TRAP_ENTRIES_AT + index * TRAP_ENTRY_BYTES for index in range(count))
    return [(case.word_in(image, at), case.long_in(image, at + WORD_BYTES)) for at in entries]


# ---- the GEMDOS DOOR as every battery through it stages it (`test_vdi_helpers_gemdos.py` says why each is so) ----
# LINEA_RETSAV STALE, so a door that skipped its park shows: the value a case reads back when no call was made.
RETSAV_STALE_VALUE = vdi.STALE_LONG
RETSAV_STALE = vdi.linea_pokes(RETSAV=RETSAV_STALE_VALUE)
# The door's three documented windows (`case.run`'s `dropped_windows`: only what the ROM's run stores in each).
BASEPAGE = case.long_in(BASE_IMAGE, addrs.GEMDOS_P_RUN)
SAVE_AREA_END = addrs.BASEPAGE_SAVED_FRAME + LONG_BYTES
GEMDOS_STACK_DEPTH = 0x100                       # deeper than Malloc's or Mfree's frames reach
TERMINATION_RECORD_BYTES = 12
GEMDOS_DOOR_WINDOWS = (
    (BASEPAGE + addrs.BASEPAGE_SAVED_D0, BASEPAGE + SAVE_AREA_END,
     "p_run's register-save area, written by the trap entry the host build has no counterpart for"),
    (addrs.GEMDOS_SUPERVISOR_STACK - GEMDOS_STACK_DEPTH, addrs.GEMDOS_SUPERVISOR_STACK,
     "GEMDOS's own stack: the ROM dispatcher's frames, which the host build's C does not have"),
    (addrs.GEMDOS_TERMINATION_JMPBUF, addrs.GEMDOS_TERMINATION_JMPBUF + TERMINATION_RECORD_BYTES,
     "the termination record, which src/gemdos/dispatch.c omits"),
)


def _memory_handler(core):
    """A `Malloc`/`Mfree` handler: its one longword argument, from where the dispatcher left it."""
    return lambda buf, arguments, _argument_bytes: core(buf, case.long_in(buf, arguments))


_lib.gemdos_malloc.restype = ctypes.c_uint32
_lib.gemdos_mfree.restype = ctypes.c_uint32
# The CANDIDATE's side of a real `trap #1`: the dispatcher's Malloc and Mfree bound to the reconstructed memory manager.
GEMDOS_HANDLERS = {gemdos.rom_handler(addrs.GEMDOS_MALLOC_FN): _memory_handler(_lib.gemdos_malloc),
                   gemdos.rom_handler(addrs.GEMDOS_MFREE_FN): _memory_handler(_lib.gemdos_mfree)}


def staged_gemdos_trap_pokes(answer=TRAP_ANSWER):
    """The `trap #1` vector pointed at the recording handler, answering `answer`, with LINEA_RETSAV stale."""
    return vdi.merge_pokes(RETSAV_STALE, recording_trap_pokes(addrs.VECTOR_TRAP_GEMDOS, answer))


def staged_gemdos_handlers(answer=TRAP_ANSWER):
    """...and its host twin for the two calls the VDI makes."""
    return {gemdos.rom_handler(function): recording_trap_handler(function, answer)
            for function in (addrs.GEMDOS_MALLOC_FN, addrs.GEMDOS_MFREE_FN)}


def staged_gemdos_hook(answer=TRAP_ANSWER):
    """...bound as the door `aes.run_function`'s `hook` opens, once per run."""
    return functools.partial(gemdos.bound_handlers, staged_gemdos_handlers(answer))

