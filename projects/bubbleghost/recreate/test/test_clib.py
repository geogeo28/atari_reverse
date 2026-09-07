"""Differential battery for the Alcyon/DRI C runtime — src/clib.c.

WHAT MAKES THIS SUBSYSTEM DIFFERENT from the game's own code is that most of it answers in a
REGISTER or on the CALLER'S STACK rather than in memory the diff can see. Three shapes handle that:

  * a routine whose whole answer is D0 (`c_strlen`, `c_getfdmode`, `c_malloc`) is checked by
    comparing the candidate glue's return against the oracle's D0 as well as diffing the image;
  * `c_ldiv` and `c_lmul` answer through their caller's own argument slots, which lie in the band
    the differential drops as stack — those are entered through a poked stub that files the answers
    at `abi.RESULT` (see `abi.c_call_pokes`);
  * the floating-point package answers in memory, which is why it is the part with a real fuzz:
    thousands of random doubles through add/sub/mul/div and the conversions, compared as BYTES.
    Comparing host floats would prove nothing here — the package keeps 32 mantissa bits, not 53.

TRAPS. A reconstruction cannot trap, so every wrapper writes the three trampoline save slots and
calls the kit's model of the call itself. Those three slots are what verifies `gemdos_trap` and
`xbios_trap`: the RET_* constant a wrapper files says WHICH trap site ran, so a case can tell a
binary read (one Fread) from a text one (several) by the return address left behind.
"""
import ctypes
import random
import struct
import zlib

import pytest

import abi
import emu
import harness
from harness import report

# ---- entry addresses (../out/prg_dis.txt, at load base 0x10000) ---------------------------------
ENTRY_CRT0_SETUP_ARGS = 0x10116
ENTRY_C_STRLEN = 0x1683e
ENTRY_C_STRCMP = 0x167fc
ENTRY_C_LDIV = 0x158fe
ENTRY_C_LMUL = 0x15970
ENTRY_C_SETFDMODE = 0x15cae
ENTRY_C_CLEARFDMODE = 0x15cfa
ENTRY_C_GETFDMODE = 0x15d36
ENTRY_C_MORECORE = 0x15af2
ENTRY_C_MALLOC = 0x15b54
ENTRY_C_FREE = 0x15bfe
ENTRY_GEMDOS_MALLOC = 0x15c82
ENTRY_GEMDOS_MFREE = 0x15c98
ENTRY_GEMDOS_MALLOC_OR_FAIL = 0x167c8
ENTRY_XBIOS_TRAP = 0x15e3c
ENTRY_C_OPEN = 0x15d64
ENTRY_C_CREAT = 0x14c7a
ENTRY_C_CLOSE = 0x14c3c
ENTRY_C_READ = 0x1667c
ENTRY_FP_PACK_FLOAT = 0x15132
ENTRY_FP_CMP = 0x15190
ENTRY_FP_DIV = 0x151d0
ENTRY_FP_MUL = 0x1524e
ENTRY_FP_SUB = 0x152e0
ENTRY_FP_ADD = 0x152fa
ENTRY_FP_PACK_DOUBLE = 0x15394
ENTRY_FP_DISPATCH = 0x153fe
ENTRY_FP_ACC_LOAD_LONG = 0x154b0
ENTRY_FP_ACC_TO_LONG = 0x154c0
ENTRY_FP_FLOAT_TO_DOUBLE = 0x154d0
ENTRY_FP_DOUBLE_TO_LONG = 0x1550a
ENTRY_FP_LONG_TO_DOUBLE = 0x15552
ENTRY_C_FCLOSE = 0x14d72
ENTRY_C_FFLUSH = 0x14dc4
ENTRY_C_FILBUF = 0x14e80
ENTRY_C_FLSBUF = 0x14fb0
ENTRY_C_PUTC = 0x150ee
ENTRY_C_FCVT = 0x15588
ENTRY_C_FOPEN = 0x156e2
ENTRY_C_FREAD = 0x15878
ENTRY_C_LSEEK = 0x159dc
ENTRY_C_FMT_INTEGER = 0x15e74
ENTRY_C_FMT_FLOAT = 0x15fe0
ENTRY_C_FMT_GETNUM = 0x161b8
ENTRY_C_DOPRNT = 0x1620c
ENTRY_C_VFPRINTF = 0x16496
ENTRY_C_PRINTF = 0x164c2
ENTRY_C_SPRINTF = 0x164d8
ENTRY_C_FPUTS = 0x164ee
ENTRY_C_CONIN = 0x16518
ENTRY_C_CONOUT_WRITE = 0x16b5e
ENTRY_C_WRITE = 0x16c04

# ---- mirrors of include/clib.h (pinned by test_constants.py) ------------------------------------
A_C_ERRNO = 0x1ea6e
A_C_MALLOC_FREELIST = 0x1ea70
A_C_MALLOC_SENTINEL = 0x1ea74
A_FP_OP_TABLE = 0x1ea7e
A_FP_ACC = 0x1ea9a
A_FP_SUB_SIGN_FLAG = 0x1eaa2
A_FP_CCR = 0x1eaa4
A_FD_MODE_TABLE = 0x1e93e
A_TRAP_SAVED_RET = 0x1e932
A_TRAP_SAVED_A2 = 0x1e936
A_TRAP_SAVED_A1 = 0x1e93a
A_CREAT_DEVICE_NAMES = 0x251c6
A_OPEN_DEVICE_NAMES = 0x251ec

MALLOC_GRANULE = 6
FREE_HEADER_BYTES = 6
FREE_OFF_SIZE = 4
MORECORE_QUANTUM_GRANULES = 0x418
FD_MODE_SLOTS = 0x4c
FD_MODE_ENTRY = 4
FD_MODE_BINARY = 0x2000
FD_DEVICE_CON = 0x8300
FD_DEVICE_AUX = 0x82ff
FD_DEVICE_PRT = 0x82fe
DEVICE_NAME_STRIDE = 6
OPEN_MODE_TRUNCATE = 0x0001
# The truncating arm's two extra trap sites. Restated and pinned even though only the arm's FIRST
# call is runnable under the model: a wrong return PC in a read-verified transcription is exactly
# what nothing else would ever look at.
RET_C_OPEN_TRUNC_FCREATE = 0x15de6
RET_C_OPEN_TRUNC_FCLOSE = 0x15df2
OPEN_MODE_WRITE = 0x0002
RET_GEMDOS_MALLOC = 0x15c92
RET_GEMDOS_MFREE = 0x15ca8
RET_GEMDOS_MALLOC_OR_FAIL = 0x167e0
RET_C_CLOSE_FCLOSE = 0x14c64
RET_C_CREAT_FCREATE = 0x14cc2
RET_C_OPEN_FOPEN = 0x15e0a
RET_C_READ_FREAD_FIRST = 0x166fe
RET_C_READ_FREAD_REFILL = 0x16762

A_C_IOB = 0x1eb08
A_C_STDOUT = 0x1eb1c
A_C_UNBUF_CHARS = 0x1eabc
A_C_BUFSIZ = 0x1eb06
A_C_FOPEN_SLOT_HINT = 0x1ea7a
A_C_CONIN_READ_POS = 0x1e8de
A_C_CONIN_LENGTH = 0x1e8e0
A_C_CONIN_BUFFER = 0x1e8e2
A_CRLF = 0x2520a
A_FCVT_TEN = 0x1eab4
A_FCVT_MAX_DIGITS = 0x1eaa6
A_FMT_FLOAT_ZERO = 0x251fe
A_FMT_FLOAT_EXPONENT_FORMAT = 0x25206
CLIB_SCRATCH_BASE = 0x000ffb00
C_VFPRINTF_BUFFER_BYTES = 256
C_FCVT_DOUBLE_BYTES = 8
C_EXPONENT_ARGS_BYTES = 6
C_FCVT_DIGITS_MAX = 64
C_FCVT_DIGITS_OVERHEAD = 3

C_IOB_SLOTS = 73
C_IOB_STRIDE = 20
C_IOB_END = 0x1f0bc
FILE_OFF_PTR = 0
FILE_OFF_CNT = 4
FILE_OFF_BASE = 6
FILE_OFF_FLAGS = 10
FILE_OFF_FD = 12
FILE_OFF_OFFSET = 14
FILE_OFF_BUFSIZ = 18
FILE_READ = 0x0001
FILE_WRITE = 0x0002
FILE_APPEND = 0x0004
FILE_UNBUFFERED = 0x0008
FILE_MYBUF = 0x0010
FILE_EOF = 0x0020
FILE_ERR = 0x0040
FILE_DIRTY = 0x0080
FILE_LINEBUF = 0x0100
FMT_NO_PRECISION = 0x0100
CRLF_BYTES = 2

RET_C_FILBUF_FSEEK = 0x14f28
RET_C_LSEEK_FSEEK = 0x15a06
RET_C_WRITE_FWRITE_RUN = 0x16cc8
RET_C_WRITE_FWRITE_CRLF = 0x16cfe
RET_C_WRITE_FWRITE_TAIL = 0x16d60
RET_C_CONOUT_CR = 0x16b7e
RET_C_CONOUT_BYTE = 0x16b96
RET_C_CONIN_CRAWCIN = 0x1654a

# ---- values the harness itself decides ----------------------------------------------------------
# A1 and A2 as the case hands them to a wrapper: two constants a wrong save slot cannot match by
# accident, and nothing dereferences either.
CALLER_A1 = 0x0a1a1a1a
CALLER_A2 = 0x0a2a2a2a

# What `xbios_trap` files as its return address when the ORACLE enters it directly: the harness's
# own `rts` sentinel is what sits on the stack, and the trampoline pops it into A_trap_saved_ret.
SENTINEL_RETURN = emu.SENTINEL

# The status register the kit's Musashi core runs a case at, above the condition codes. `fp_cmp`
# stores the WHOLE SR, so a reconstruction has to be told this half — and it is a pin rather than a
# guess: a wrong value reddens every fp_cmp case in the file.
FP_CMP_STATUS_HIGH = 0x2700

# fp_dispatch's own stack local, the eight bytes at -10(a6) it widens a short/long/float source
# into. `link a6,#$fff6` after a `jsr` from the harness's entry frame puts A6 at STACK_TOP - 4.
FP_DISPATCH_FRAME_LOCAL = emu.STACK_TOP - 14
# ...and the frame `fp_pack_double` unwinds when it is entered DIRECTLY. It is a tail, not a
# function: it pops ten saved registers and then `unlk a6`, so A6 has to name a frame whose saved
# link points the `rts` back at the sentinel. STACK_TOP - 4 is that frame.
PACK_DOUBLE_FRAME = emu.STACK_TOP - 4

SCRATCH = abi.SCRATCH
GUARD = abi.GUARD_BYTES

_lib = harness._lib
for _name, _args, _ret in (
    ("g_crt0_setup_args", [ctypes.c_void_p, ctypes.c_uint32], None),
    ("g_c_strlen", [ctypes.c_void_p, ctypes.c_uint32], ctypes.c_uint32),
    ("g_c_strcmp", [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32], ctypes.c_int32),
    ("g_c_ldiv", [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32], None),
    ("g_c_lmul", [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32], None),
    ("g_c_setfdmode", [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32], None),
    ("g_c_clearfdmode", [ctypes.c_void_p, ctypes.c_uint32], None),
    ("g_c_getfdmode", [ctypes.c_void_p, ctypes.c_uint32], ctypes.c_uint32),
    ("g_c_malloc", [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32],
     ctypes.c_uint32),
    ("g_c_free", [ctypes.c_void_p, ctypes.c_uint32], None),
    ("g_c_morecore", [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32],
     ctypes.c_uint32),
    ("g_gemdos_malloc", [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32],
     ctypes.c_uint32),
    ("g_gemdos_mfree", [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32],
     ctypes.c_uint32),
    ("g_gemdos_malloc_or_fail",
     [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32], ctypes.c_uint32),
    ("g_xbios_physbase", [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32],
     ctypes.c_uint32),
    ("g_c_open", [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
                  ctypes.c_uint32], ctypes.c_int32),
    ("g_c_creat", [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
                   ctypes.c_uint32], ctypes.c_int32),
    ("g_c_close", [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32],
     ctypes.c_int32),
    ("g_c_read", [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
                  ctypes.c_uint32, ctypes.c_uint32], ctypes.c_int32),
    ("g_fp_pack_double", [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32], None),
    ("g_fp_pack_float", [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32], None),
    ("g_fp_long_to_double", [ctypes.c_void_p, ctypes.c_uint32], None),
    ("g_fp_float_to_double", [ctypes.c_void_p, ctypes.c_uint32], None),
    ("g_fp_double_to_long", [ctypes.c_void_p, ctypes.c_uint32], None),
    ("g_fp_acc_load_long", [ctypes.c_void_p, ctypes.c_uint32], None),
    ("g_fp_acc_to_long", [ctypes.c_void_p], ctypes.c_uint32),
    ("g_fp_add", [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32], None),
    ("g_fp_sub", [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32], None),
    ("g_fp_mul", [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32], None),
    ("g_fp_div", [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32], None),
    ("g_fp_cmp", [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32], None),
    ("g_fp_dispatch", [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
                       ctypes.c_uint32, ctypes.c_uint32], None),
    ("g_c_fopen", [ctypes.c_void_p] + [ctypes.c_uint32] * 4, ctypes.c_uint32),
    ("g_c_fclose", [ctypes.c_void_p] + [ctypes.c_uint32] * 3, ctypes.c_int32),
    ("g_c_fflush", [ctypes.c_void_p] + [ctypes.c_uint32] * 3, ctypes.c_int32),
    ("g_c_filbuf", [ctypes.c_void_p] + [ctypes.c_uint32] * 3, ctypes.c_int32),
    ("g_c_flsbuf", [ctypes.c_void_p] + [ctypes.c_uint32] * 4, ctypes.c_int32),
    ("g_c_putc", [ctypes.c_void_p] + [ctypes.c_uint32] * 4, ctypes.c_int32),
    ("g_c_fread", [ctypes.c_void_p] + [ctypes.c_uint32] * 6, ctypes.c_int32),
    ("g_c_lseek", [ctypes.c_void_p] + [ctypes.c_uint32] * 5, ctypes.c_int32),
    ("g_c_write", [ctypes.c_void_p] + [ctypes.c_uint32] * 5, ctypes.c_int32),
    ("g_c_conout_write", [ctypes.c_void_p] + [ctypes.c_uint32] * 4, None),
    ("g_c_conin", [ctypes.c_void_p] + [ctypes.c_uint32] * 3, ctypes.c_int32),
    ("g_c_fmt_getnum", [ctypes.c_void_p, ctypes.c_uint32], ctypes.c_int32),
    ("g_c_fmt_integer", [ctypes.c_void_p] + [ctypes.c_uint32] * 5, None),
    ("g_c_fmt_float", [ctypes.c_void_p] + [ctypes.c_uint32] * 7, None),
    ("g_c_fcvt", [ctypes.c_void_p] + [ctypes.c_uint32] * 5, None),
    ("g_c_doprnt", [ctypes.c_void_p] + [ctypes.c_uint32] * 4, ctypes.c_int32),
    ("g_c_sprintf", [ctypes.c_void_p] + [ctypes.c_uint32] * 4, ctypes.c_int32),
    ("g_c_fputs", [ctypes.c_void_p] + [ctypes.c_uint32] * 4, None),
    ("g_c_vfprintf", [ctypes.c_void_p] + [ctypes.c_uint32] * 6, ctypes.c_int32),
    ("g_c_printf", [ctypes.c_void_p] + [ctypes.c_uint32] * 5, ctypes.c_int32),
    ("g_c_unlink", [ctypes.c_void_p] + [ctypes.c_uint32] * 3, ctypes.c_int32),
    ("g_c_auxout_write", [ctypes.c_void_p] + [ctypes.c_uint32] * 4, None),
    ("g_c_prtout_write", [ctypes.c_void_p] + [ctypes.c_uint32] * 4, None),
    ("g_c_exit_pterm", [ctypes.c_void_p] + [ctypes.c_uint32] * 3, None),
    ("g_c_exit", [ctypes.c_void_p] + [ctypes.c_uint32] * 3, None),
):
    getattr(_lib, _name).argtypes = _args
    getattr(_lib, _name).restype = _ret


def run(entry, glue, pokes=None, regs=None, poison=False, max_insns=200_000):
    """One differential — `abi.run_with_a4`, which also clears the candidate's Malloc mirror.

    Kept as a name of its own only because `check` below wants a positional shape; everything it
    does lives in `test/abi.py` so that a battery cannot be written without it.
    """
    return abi.run_with_a4(entry, glue, pokes=pokes, regs=regs, poison=poison,
                           max_insns=max_insns)


def check(entry, glue, pokes=None, regs=None, poison=False, note="", max_insns=200_000):
    diffs, info = run(entry, glue, pokes, regs, poison, max_insns)
    assert not diffs, f"{note}\n{report(diffs)}"
    return info


def check_d0_low_word(info, note=""):
    """The oracle's D0 low word against the candidate glue's answer.

    ONLY the low word, for the routines that return a `short`: the original writes D0's low half and
    leaves its high half holding whatever the last subroutine put there, which a reconstruction
    expressed as a C `int16_t` cannot and should not reproduce.
    """
    assert (info["ret"] & 0xffff) == (info["regs"]["d0"] & 0xffff), (
        f"{note}: cand={info['ret'] & 0xffff:#06x} oracle={info['regs']['d0'] & 0xffff:#06x}")


def check_d0_long(info, note=""):
    """...and the whole longword, for the routines that return one."""
    assert (info["ret"] & 0xffffffff) == info["regs"]["d0"], (
        f"{note}: cand={info['ret'] & 0xffffffff:#010x} oracle={info['regs']['d0']:#010x}")


def noise_around(rng, addr, payload):
    """`payload` at `addr` with GUARD bytes of noise either side, as one poke.

    The noise is what turns "wrote one byte too far" into a difference: most of what these routines
    touch is bss, which the image already holds as zeroes, so a clear or a copy that overran would
    otherwise write zeroes over zeroes and the diff would stay empty (abi.seed_spans says the same).
    """
    return {addr - GUARD: rng.randbytes(GUARD) + bytes(payload) + rng.randbytes(GUARD)}


# ================================================================================================
# crt0_setup_args @ 0x10116 — the runtime's argv hook, which is a bare `rts`
# ================================================================================================

# The command tail the crt0 pushes for it (`pea 128(a0)`), which it never reads.
CRT0_COMMAND_TAIL = SCRATCH


def test_crt0_setup_args_writes_nothing():
    """A two-byte routine, and the CLAIM is that it is two bytes: it writes no memory at all.

    The byte diff alone would be vacuous here — two programs that both do nothing agree — so the
    ORACLE'S WRITE-SET is what carries the case. An `rts` writes nothing, and a version of this
    routine that had been mis-identified (the argv parser it stubs out really does write) would show
    as writes the reconstruction did not make.
    """
    rng = random.Random(ENTRY_CRT0_SETUP_ARGS)
    pokes = abi.merge_pokes(noise_around(rng, CRT0_COMMAND_TAIL, b"GHOST.PRG\0"),
                            abi.stack_args((4, CRT0_COMMAND_TAIL)))
    info = check(ENTRY_CRT0_SETUP_ARGS,
                 lambda lib, buf: lib.g_crt0_setup_args(buf, CRT0_COMMAND_TAIL),
                 pokes=pokes, note="crt0_setup_args")
    assert not info["writes"], (
        f"the original wrote {len(info['writes'])} byte(s); it is supposed to be one `rts`")


# ================================================================================================
# c_strlen @ 0x1683e and c_strcmp @ 0x167fc
# ================================================================================================

@pytest.mark.parametrize("text", (b"", b"A", b"A:GHOST.DEM", b"\xff\x80\x7f", bytes(range(1, 200))))
def test_c_strlen(text):
    rng = random.Random(len(text))
    pokes = noise_around(rng, SCRATCH, text + b"\0")
    info = check(ENTRY_C_STRLEN, lambda lib, buf: lib.g_c_strlen(buf, SCRATCH),
                 pokes=abi.merge_pokes(pokes, abi.stack_args((4, SCRATCH))),
                 note=f"strlen({text!r})")
    check_d0_long(info, f"strlen({text!r})")
    assert info["ret"] == len(text)


# The signed byte compare is the point of the high-bit pairs: `move.b / ext.w` makes 0xff rank BELOW
# 'A', so an unsigned reconstruction returns the opposite sign for the last two rows.
@pytest.mark.parametrize("left,right", (
    (b"CON:", b"CON:"),
    (b"CON:", b"AUX:"),
    (b"AUX:", b"CON:"),
    (b"", b""),
    (b"", b"A"),
    (b"A", b""),
    (b"A:GHOST.DAT", b"A:GHOST.DEM"),
    (b"\xff", b"A"),
    (b"A", b"\xff"),
    (b"\x80\x01", b"\x80\x02"),
))
def test_c_strcmp(left, right):
    rng = random.Random(len(left) * 31 + len(right))
    pokes = noise_around(rng, SCRATCH, left + b"\0")
    pokes = abi.merge_pokes(pokes, noise_around(rng, SCRATCH + 0x100, right + b"\0"))
    info = check(ENTRY_C_STRCMP,
                 lambda lib, buf: lib.g_c_strcmp(buf, SCRATCH, SCRATCH + 0x100),
                 pokes=abi.merge_pokes(pokes, abi.stack_args((4, SCRATCH), (4, SCRATCH + 0x100))),
                 note=f"strcmp({left!r}, {right!r})")
    check_d0_low_word(info, f"strcmp({left!r}, {right!r})")


def test_c_strcmp_matches_the_device_names_the_library_ships():
    """The three names c_open and c_creat intercept, against the copies the linker emitted.

    Two copies, at A_creat_device_names and A_open_device_names, and this is what says they really
    do hold the same three strings — a fact both file-layer cores depend on.
    """
    for index, name in enumerate((b"CON:", b"AUX:", b"PRT:")):
        for table in (A_CREAT_DEVICE_NAMES, A_OPEN_DEVICE_NAMES):
            at = table + index * DEVICE_NAME_STRIDE
            assert bytes(harness.BASE_IMAGE[at:at + len(name) + 1]) == name + b"\0"


# ================================================================================================
# c_ldiv @ 0x158fe and c_lmul @ 0x15970 — answered through the caller's own argument slots
# ================================================================================================

def case_seed(note):
    """A seed derived from a case's own note, STABLE ACROSS RUNS.

    `hash()` is salted for `str` and `bytes` (PYTHONHASHSEED), so seeding a case's guard noise with
    `hash(note)` draws different noise every run and a failure cannot be reproduced from the note the
    report prints. `zlib.crc32` is a fixed function of the bytes, so it can. (`hash()` of an int or a
    float IS stable, which is why the numeric seeds elsewhere in this file are left alone.)
    """
    return zlib.crc32(note.encode("utf-8")) & 0xffff


def stub_case(calls, results, note, glue, poison=False, extra=None):
    """Drive `calls` from a poked stub and hand back the differential's info.

    `results` is how many longword slots the stub files, so the case can seed noise over exactly
    those and no more — an unseeded slot the candidate forgot to write would match the oracle's by
    holding the same zeroes. `extra` is anything else the run needs staged (the zero-divide vector
    below is the only user).
    """
    rng = random.Random(case_seed(note))
    pokes = abi.merge_pokes(
        abi.c_call_pokes(calls),
        noise_around(rng, abi.RESULT, rng.randbytes(results * abi.RESULT_SLOT_BYTES)),
        extra or {})
    return check(abi.STUB, glue, pokes=pokes, note=note, poison=poison)


def ldiv_case(divisor, dividend, poison=False, extra=None):
    note = f"c_ldiv(divisor={divisor:#x}, dividend={dividend:#x})"
    return stub_case([{"routine": ENTRY_C_LDIV,
                       "args": [(4, divisor), (4, dividend)],
                       "answers": [("stack", 0), ("stack", 1)],
                       "pop": 0}], 2, note,
                     lambda lib, buf: lib.g_c_ldiv(buf, divisor, dividend, abi.RESULT),
                     poison=poison, extra=extra)


def lmul_case(left, right, poison=False):
    note = f"c_lmul({left:#x}, {right:#x})"
    return stub_case([{"routine": ENTRY_C_LMUL,
                       "args": [(4, left), (4, right)],
                       "answers": [("stack", 0)],
                       # c_lmul EATS four of its own eight bytes of argument on the way out
                       # (`move.l (a7)+,(a7)`), so the one answer above balances the stack alone.
                       "pop": 0}], 1, note,
                     lambda lib, buf: lib.g_c_lmul(buf, left, right, abi.RESULT),
                     poison=poison)


@pytest.mark.parametrize("divisor,dividend", (
    (1, 0), (1, 1), (1, 0x7fffffff), (3, 10), (10, 3), (7, 0xfffffff9),
    (0xffffffff, 10), (0xfffffff6, 0xfffffff6), (0x1234, 0x3fffffff), (0x3ffffffe, 0x3fffffff),
))
def test_c_ldiv_edges(divisor, dividend):
    ldiv_case(divisor, dividend, poison=True)


# ---- the zero divisor, and the machine fact it depends on ---------------------------------------
# `c_ldiv` opens `move.l 8(a6),d2 / bne`, and the fall-through is `divu.w #$0,d0` — a DELIBERATE
# zero-divide exception — followed by `clr.l d0 / clr.l d1` and the two stores. So the answer is 0/0
# provided the machine's vector 5 returns, and the harness's image has no vector 5 at all: $14 is
# zero, so the oracle's CPU takes the exception to the vector page and the run is refused.
#
# THAT THE VECTOR RETURNS IS MEASURED, not assumed. A GEMDOS program run under Hatari on the TOS ROM
# reports $14 = $e00d68 and comes back from a user-mode `divu.w #0` with D0 untouched (../STATUS.md,
# "Verified — clib", records the probe). These cases declare the same machine by pointing $14 at an
# `rte`, which is an input like any other — given identically to both sides, and written by neither.
TOS_VEC_ZERO_DIVIDE = 0x0014
ZERO_DIVIDE_HANDLER = abi.SCRATCH + 0x800   # clear of the string and fp buffers below SCRATCH+0x800
OPCODE_RTE = bytes.fromhex("4e73")


def zero_divide_vector():
    """$14 pointing at an `rte`, i.e. the machine TOS leaves behind."""
    return {TOS_VEC_ZERO_DIVIDE: abi.long(ZERO_DIVIDE_HANDLER), ZERO_DIVIDE_HANDLER: OPCODE_RTE}


@pytest.mark.parametrize("dividend", (0, 5, 0xffffffff))
def test_c_ldiv_by_zero_stores_zero_over_both_slots(dividend):
    """The branch the shift-and-subtract loop below never sees.

    Without it the C is not merely inexact but non-terminating: `for (bit = 1; divisor < dividend;)`
    never advances a zero divisor, so `(0, 5)` spins for ever and `(0, 0)` falls straight through
    and answers a quotient of 1.
    """
    info = ldiv_case(0, dividend, extra=zero_divide_vector())
    answers = bytes(info["writes"][abi.result_slot(0) + i]
                    for i in range(2 * abi.RESULT_SLOT_BYTES))
    assert answers == bytes(2 * abi.RESULT_SLOT_BYTES), (
        f"the ORACLE filed {answers.hex()} for c_ldiv(0, {dividend:#x}), not two zero longwords")


def test_c_ldiv_by_zero_is_unrunnable_without_that_vector():
    """...and the declaration is load-bearing: with $14 as the loader leaves it, nothing is verified.

    This is what keeps the case above honest. The oracle takes the exception to address 0 and
    executes the vector page, which reaches the `rts` the case is diffed at only by accident — so
    the run has to FAIL, and the two shapes it can fail in are both accepted here because both are
    the kit's answer to the same thing and neither is this reconstruction's:

      * a REFUSAL, while the walk over the vector page reaches a call the model does not serve;
      * an OS EVENT STREAM MISMATCH, once it does — the walk reaches a GEMDOS `Pterm`, which
        Phase 13 now models as the process ending, and the candidate (which never divides by zero
        at all) files no such event.

    Either way the pair of cases gets revisited rather than quietly diverging if the kit grows a
    model for the vector itself: this would then go green and fail by name.
    """
    with pytest.raises((RuntimeError, AssertionError),
                       match="unmodeled OS behaviour|did not reach|OS event streams differ"):
        ldiv_case(0, 5)


@pytest.mark.parametrize("left,right", (
    (0, 0), (1, 1), (0, 0x7fffffff), (0x10000, 0x10000), (0xffff, 0xffff),
    (0xfffffffb, 7), (7, 0xfffffffb), (0xfffffffb, 0xfffffffb), (0x12345678, 0x9abc),
    (0x80000000, 1), (0x7fffffff, 2),
))
def test_c_lmul_edges(left, right):
    lmul_case(left, right, poison=True)


CHUNKS = 8


@pytest.mark.parametrize("chunk", range(CHUNKS))
def test_c_ldiv_lmul_fuzz(chunk):
    """Random magnitudes through both. Chunk-SEEDED (see `abi.shard`), so the suite runs CHUNKS x 24
    pairs through each routine rather than splitting one list of 24.

    THE DIVISOR IS KEPT BELOW 0x40000000 IN MAGNITUDE, and the dividend with it. c_ldiv's alignment
    loop shifts the divisor left until it reaches the dividend and has no overflow guard, so a
    dividend the divisor cannot reach without losing its top bit spins for ever — which is the
    original's own behaviour and is recorded in ../STATUS.md rather than being tested here.
    """
    rng = random.Random(0xd1f + chunk)
    for _ in range(24):
        divisor = rng.randrange(1, 0x40000000) * rng.choice((1, -1)) & 0xffffffff
        dividend = rng.randrange(0, 0x40000000) * rng.choice((1, -1)) & 0xffffffff
        ldiv_case(divisor, dividend)
        lmul_case(rng.randrange(0, 1 << 32), rng.randrange(0, 1 << 32))


# ================================================================================================
# The fd-mode side table
# ================================================================================================

def fd_table_poke(rng, entries):
    """The whole 76-slot table, `A_c_errno` immediately above it, and the longword above that.

    THE THREE ARE CONSECUTIVE and each is here for its own reason. The table is the case's input;
    `A_c_malloc_freelist`'s high word is what `c_getfdmode`'s exhausted search reads instead of a
    mode, so it is staged with noise rather than a plausible zero; and `A_c_errno` between them is
    staged with noise because every routine in the file layer STORES it and the post-init image
    holds a zero there — so a reconstruction that skipped the store would leave a zero matching a
    zero (measured: deleting `c_close`'s errno store survived the whole suite before this).
    """
    table = bytearray(FD_MODE_SLOTS * FD_MODE_ENTRY)
    for slot, (handle, mode) in enumerate(entries):
        table[slot * FD_MODE_ENTRY:slot * FD_MODE_ENTRY + 4] = struct.pack(">HH", handle, mode)
    return {A_FD_MODE_TABLE: bytes(table),
            A_C_ERRNO: rng.randbytes(2),
            A_C_MALLOC_FREELIST: rng.randbytes(4)}


@pytest.mark.parametrize("entries,handle,mode", (
    ((), 6, 0),
    ((), 6, FD_MODE_BINARY),
    (((6, 0),), 7, FD_MODE_BINARY),
    (((6, 0), (7, FD_MODE_BINARY)), FD_DEVICE_CON, 0),
    (tuple((h, FD_MODE_BINARY) for h in range(1, FD_MODE_SLOTS + 1)), 9, FD_MODE_BINARY),
))
def test_c_setfdmode(entries, handle, mode):
    """...including a FULL table, where the record is silently dropped."""
    rng = random.Random(len(entries))
    pokes = abi.merge_pokes(fd_table_poke(rng, entries), abi.stack_args((2, handle), (2, mode)))
    check(ENTRY_C_SETFDMODE, lambda lib, buf: lib.g_c_setfdmode(buf, handle, mode),
          pokes=pokes, note=f"setfdmode({handle:#x}, {mode:#x}) over {len(entries)} entries")


@pytest.mark.parametrize("handle", (6, 7, FD_DEVICE_CON, 0, 0x1234))
def test_c_clearfdmode(handle):
    rng = random.Random(handle)
    entries = ((6, FD_MODE_BINARY), (7, 0), (FD_DEVICE_CON, FD_MODE_BINARY), (6, 0))
    pokes = abi.merge_pokes(fd_table_poke(rng, entries), abi.stack_args((2, handle)))
    check(ENTRY_C_CLEARFDMODE, lambda lib, buf: lib.g_c_clearfdmode(buf, handle),
          pokes=pokes, note=f"clearfdmode({handle:#x})")


@pytest.mark.parametrize("handle", (6, 7, FD_DEVICE_CON, 0x4321))
def test_c_getfdmode(handle):
    """A handle in the table, and one that is NOT — which reads past the table's end.

    The miss is the case worth having: the word it lands on is the high half of
    A_c_malloc_freelist, and this poke gives that longword random contents so a reconstruction that
    answered a plausible 0 instead would be caught.
    """
    rng = random.Random(handle * 7)
    entries = ((6, FD_MODE_BINARY), (7, 0), (FD_DEVICE_CON, 0x1234))
    pokes = abi.merge_pokes(fd_table_poke(rng, entries), abi.stack_args((2, handle)))
    info = check(ENTRY_C_GETFDMODE, lambda lib, buf: lib.g_c_getfdmode(buf, handle),
                 pokes=pokes, note=f"getfdmode({handle:#x})")
    check_d0_low_word(info, f"getfdmode({handle:#x})")


# ================================================================================================
# The allocator — gemdos_malloc / gemdos_mfree / gemdos_malloc_or_fail / c_morecore / c_malloc /
# c_free, and with them the two trap trampolines
# ================================================================================================

def trap_slot_noise(rng):
    """`abi.trap_slot_noise` over THIS battery's own `A_trap_saved_ret`.

    The adjacency the shared helper relies on is asserted here, where the three addresses are
    restated and pinned to `include/clib.h`."""
    assert A_TRAP_SAVED_A2 == A_TRAP_SAVED_RET + 4 and A_TRAP_SAVED_A1 == A_TRAP_SAVED_RET + 8
    return abi.trap_slot_noise(rng, A_TRAP_SAVED_RET)


def caller_registers():
    return {"a1": CALLER_A1, "a2": CALLER_A2}


# GEMDOS's "how big is the LARGEST FREE BLOCK?" query, spelt as the caller pushes it. It is the one
# Malloc argument whose answer is a SIZE rather than an address, and it moves neither side's bump
# pointer (tools/recreate_kit/include/os.h, beside `os_malloc`).
MALLOC_LARGEST_FREE = 0xffffffff


@pytest.mark.parametrize("size", (0, 1, 2, 0x1770, 0x7800, 0x40000, MALLOC_LARGEST_FREE))
def test_gemdos_malloc(size):
    """The wrapper forwards to the model and leaves the three save slots as its trace.

    A REQUEST is answered with the arena's base, the first block of a run that starts rewound. The
    last size is the QUERY rather than a request: both sides answer the free window
    (`heap_limit - heap_base`, project.toml's two keys) and allocate nothing, which is the one case
    here that would survive a wrapper spelling the arena's arithmetic itself instead of forwarding
    to the model.
    """
    rng = random.Random(size)
    pokes = abi.merge_pokes(trap_slot_noise(rng), abi.stack_args((4, size)))
    info = check(ENTRY_GEMDOS_MALLOC,
                 lambda lib, buf: lib.g_gemdos_malloc(buf, size, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"gemdos_malloc({size:#x})")
    check_d0_long(info, f"gemdos_malloc({size:#x})")
    expected = (emu.HEAP_LIMIT - harness.OS_HEAP_BASE if size == MALLOC_LARGEST_FREE
                else harness.OS_HEAP_BASE)
    assert info["ret"] == expected


@pytest.mark.parametrize("block", (0, harness.OS_HEAP_BASE, 0xdeadbee0))
def test_gemdos_mfree(block):
    rng = random.Random(block & 0xffff)
    pokes = abi.merge_pokes(trap_slot_noise(rng), abi.stack_args((4, block)))
    info = check(ENTRY_GEMDOS_MFREE,
                 lambda lib, buf: lib.g_gemdos_mfree(buf, block, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"gemdos_mfree({block:#x})")
    check_d0_long(info, f"gemdos_mfree({block:#x})")


@pytest.mark.parametrize("size", (0, 6, 0x1860, 0xfffe))
def test_gemdos_malloc_or_fail(size):
    rng = random.Random(size + 1)
    pokes = abi.merge_pokes(trap_slot_noise(rng), abi.stack_args((2, size)))
    info = check(ENTRY_GEMDOS_MALLOC_OR_FAIL,
                 lambda lib, buf: lib.g_gemdos_malloc_or_fail(buf, size, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"malloc_or_fail({size:#x})")
    check_d0_long(info, f"malloc_or_fail({size:#x})")


def test_xbios_trap():
    """The XBIOS trampoline, exercised through XBIOS Physbase (0x02).

    The ORACLE enters the trampoline directly, so the return address it parks is the harness's own
    `rts` sentinel — which is exactly the point: the slot holds whatever was on the stack, and the
    candidate is told the same value rather than deriving one.
    """
    rng = random.Random(0x8105)
    pokes = abi.merge_pokes(trap_slot_noise(rng), abi.stack_args((2, 0x02)))
    info = check(ENTRY_XBIOS_TRAP,
                 lambda lib, buf: lib.g_xbios_physbase(buf, CALLER_A1, CALLER_A2, SENTINEL_RETURN),
                 pokes=pokes, regs=caller_registers(), note="xbios_trap(Physbase)")
    check_d0_long(info, "xbios_trap(Physbase)")
    assert info["ret"] == harness.OS_SCREEN_BASE


# ---- free-list arenas ---------------------------------------------------------------------------
ARENA = SCRATCH + 0x1000        # clear of the string/stub cases above
ARENA_BYTES = 0x3000


def arena_pokes(rng, blocks, roving):
    """A free list laid out in ARENA. `blocks` is [(granules, is_free), ...], consecutive.

    Every block gets a header — a `next` longword and a size word in granules — and the FREE ones
    are chained in ascending order, circularly. An allocated block's `next` is left as noise, since
    nothing reads it until c_free overwrites it. Returns (pokes, [addresses]).
    """
    pokes = {ARENA - GUARD: rng.randbytes(ARENA_BYTES + 2 * GUARD)}
    addresses, at = [], ARENA
    for granules, _free in blocks:
        addresses.append(at)
        at += granules * MALLOC_GRANULE
    assert at <= ARENA + ARENA_BYTES, "the arena laid out longer than the span seeded around it"

    free = [addresses[i] for i, (_g, is_free) in enumerate(blocks) if is_free]
    assert free, "an arena with no free block has no list for the roving pointer to name"
    body = bytearray(pokes[ARENA - GUARD])
    for index, (granules, is_free) in enumerate(blocks):
        offset = addresses[index] - ARENA + GUARD
        if is_free:
            successor = free[(free.index(addresses[index]) + 1) % len(free)]
            body[offset:offset + 4] = successor.to_bytes(4, "big")
        body[offset + FREE_OFF_SIZE:offset + FREE_OFF_SIZE + 2] = granules.to_bytes(2, "big")
    pokes[ARENA - GUARD] = bytes(body)
    pokes[A_C_MALLOC_FREELIST] = free[roving % len(free)].to_bytes(4, "big")
    return pokes, addresses


def test_c_malloc_initialises_an_empty_list():
    """The very first allocation: a zero root self-initialises to the sentinel, then calls morecore.

    This is the case that ties the allocator to the trap model — the whole chain c_malloc ->
    c_morecore -> gemdos_malloc_or_fail -> the GEMDOS trampoline runs, and the save slots come back
    holding RET_GEMDOS_MALLOC_OR_FAIL.
    """
    rng = random.Random(0xc0ffee)
    pokes = trap_slot_noise(rng)
    pokes = abi.merge_pokes(pokes, {A_C_MALLOC_FREELIST: (0).to_bytes(4, "big")})
    pokes = abi.merge_pokes(pokes, abi.stack_args((2, 0x40)))
    info = check(ENTRY_C_MALLOC,
                 lambda lib, buf: lib.g_c_malloc(buf, 0x40, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note="c_malloc on an empty list")
    check_d0_long(info, "c_malloc on an empty list")


@pytest.mark.parametrize("size", (0, 1, 5, 6, 7, 0x40, 0x400))
def test_c_malloc_over_an_arena(size):
    """First fit over a list with an exact-size block, a larger one and a too-small one."""
    rng = random.Random(size)
    blocks = ((4, True), (0x10, False), (0x0b, True), (0x30, True), (0x20, False), (0x100, True))
    pokes, _addresses = arena_pokes(rng, blocks, roving=0)
    pokes = abi.merge_pokes(pokes, trap_slot_noise(rng), abi.stack_args((2, size)))
    info = check(ENTRY_C_MALLOC,
                 lambda lib, buf: lib.g_c_malloc(buf, size, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_malloc({size:#x})")
    check_d0_long(info, f"c_malloc({size:#x})")


@pytest.mark.parametrize("victim", (1, 4))
@pytest.mark.parametrize("roving", (0, 1, 2))
def test_c_free_over_an_arena(victim, roving):
    """Return an allocated block, from each of the three places the roving pointer can be.

    Block 1 sits between two free blocks and coalesces BOTH ways; block 4 has a free neighbour only
    below it. Which one the search starts from changes the walk, not the answer.
    """
    rng = random.Random(victim * 16 + roving)
    blocks = ((4, True), (0x10, False), (0x0b, True), (0x30, True), (0x20, False), (0x100, True))
    pokes, addresses = arena_pokes(rng, blocks, roving)
    payload = addresses[victim] + FREE_HEADER_BYTES
    pokes = abi.merge_pokes(pokes, abi.stack_args((4, payload)))
    check(ENTRY_C_FREE, lambda lib, buf: lib.g_c_free(buf, payload),
          pokes=pokes, note=f"c_free(block {victim}, roving {roving})")


@pytest.mark.parametrize("granules", (1, 0x417, 0x418, 0x419, 0x830))
def test_c_morecore(granules):
    """Rounding up to whole quanta, the Malloc, and the c_free that links the block in."""
    rng = random.Random(granules)
    blocks = ((4, True), (0x10, False), (0x0b, True))
    pokes, _addresses = arena_pokes(rng, blocks, roving=0)
    pokes = abi.merge_pokes(pokes, trap_slot_noise(rng), abi.stack_args((2, granules)))
    info = check(ENTRY_C_MORECORE,
                 lambda lib, buf: lib.g_c_morecore(buf, granules, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_morecore({granules:#x})")
    check_d0_long(info, f"c_morecore({granules:#x})")


ALLOCATOR_FUZZ_CASES = 16      # per chunk; the chunks are SEEDED, so the suite runs CHUNKS x this
ALLOCATOR_FUZZ_MIN_PER_ARM = 4  # ...and neither arm may collapse to a handful by chance


def _fuzz_arena(rng):
    """A random partition of ARENA with at least one free block AND at least one allocated one.

    Both are required rather than hoped for: a list with no free block has nothing for the roving
    pointer to name (`arena_pokes` refuses it), and one with no ALLOCATED block has nothing for
    `c_free` to return — which used to make the free arm `continue` silently, so a chunk could run
    sixteen mallocs and no frees and still report as a fuzz of both.
    """
    count = rng.randrange(3, 9)
    blocks = [(rng.randrange(2, 0x60), rng.random() < 0.5) for _ in range(count)]
    for wanted in (True, False):
        if all(free != wanted for _g, free in blocks):
            index = rng.randrange(count)
            blocks[index] = (blocks[index][0], wanted)   # this block's OWN size, not block 0's
    return tuple(blocks)


@pytest.mark.parametrize("chunk", range(CHUNKS))
def test_allocator_fuzz(chunk):
    """Random arenas through a random alloc-or-free. Chunk-SEEDED, not chunk-partitioned.

    The arena is PARTITIONED rather than assembled, so every block really does abut its neighbour —
    which is what makes c_free's two coalescing arms reachable — and each is marked free or
    allocated at random, so the list the routine walks is a different shape every case.
    """
    rng = random.Random(0xa11c + chunk)
    ran = {"c_malloc": 0, "c_free": 0}
    for _ in range(ALLOCATOR_FUZZ_CASES):
        blocks = _fuzz_arena(rng)
        pokes, addresses = arena_pokes(rng, blocks, roving=rng.randrange(len(blocks)))
        pokes = abi.merge_pokes(pokes, trap_slot_noise(rng))
        if rng.random() < 0.5:
            size = rng.randrange(0, 0x300)
            ran["c_malloc"] += 1
            check(ENTRY_C_MALLOC,
                  lambda lib, buf, size=size: lib.g_c_malloc(buf, size, CALLER_A1, CALLER_A2),
                  pokes=abi.merge_pokes(pokes, abi.stack_args((2, size))), regs=caller_registers(),
                  note=f"fuzz c_malloc({size:#x}) over {blocks}")
        else:
            allocated = [i for i, (_g, free) in enumerate(blocks) if not free]
            payload = addresses[rng.choice(allocated)] + FREE_HEADER_BYTES
            ran["c_free"] += 1
            check(ENTRY_C_FREE,
                  lambda lib, buf, payload=payload: lib.g_c_free(buf, payload),
                  pokes=abi.merge_pokes(pokes, abi.stack_args((4, payload))),
                  note=f"fuzz c_free({payload:#x}) over {blocks}")
    assert min(ran.values()) >= ALLOCATOR_FUZZ_MIN_PER_ARM, (
        f"chunk {chunk} ran {ran} — a fuzz that names both routines has to drive both of them, and "
        f"a coin that lands this unevenly is a generator to look at rather than luck")


# ================================================================================================
# The low-level file layer
# ================================================================================================

DEM_NAME = "A:GHOST.DEM"
SCR_NAME = "A:GHOST.SCR"


def staged(files, open_slots=(), cursors=()):
    """`harness.stage_files`, with the named slots marked already open and their cursors placed.

    `os_fread` refuses a handle whose slot is closed, and a case that enters `c_read` directly never
    ran the `c_open` that would have opened it — so the flag is part of the world the case stages.

    `cursors` is (slot, position) pairs, and is what lets a case seek BACKWARDS: the model refuses a
    seek to a negative position rather than clamping it, so a stream whose buffer holds bytes the
    caller never took has to start from a cursor those bytes came from.
    """
    pokes, handles = harness.stage_files(files)
    positions = dict(cursors)
    for slot in set(open_slots) | set(positions):
        key = harness.OS_FS_TABLE + slot * harness.OS_FS_ENTRY
        entry = bytearray(pokes[key])
        if slot in open_slots:
            entry[harness.OS_FS_OFF_OPEN:harness.OS_FS_OFF_OPEN + 4] = (1).to_bytes(4, "big")
        if slot in positions:
            entry[harness.OS_FS_OFF_CURSOR:harness.OS_FS_OFF_CURSOR + 4] = (
                positions[slot].to_bytes(4, "big"))
        pokes[key] = bytes(entry)
    return pokes, handles


def path_poke(rng, name):
    return noise_around(rng, SCRATCH, name.encode("ascii") + b"\0")


@pytest.mark.parametrize("mode", (0, FD_MODE_BINARY, OPEN_MODE_WRITE,
                                  OPEN_MODE_WRITE | FD_MODE_BINARY))
def test_c_open_a_staged_file(mode):
    rng = random.Random(mode)
    pokes, _handles = staged([(DEM_NAME, b"demo bytes")])
    pokes = abi.merge_pokes(pokes, path_poke(rng, DEM_NAME), fd_table_poke(rng, ()),
                            trap_slot_noise(rng))
    pokes = abi.merge_pokes(pokes, abi.stack_args((4, SCRATCH), (2, mode)))
    info = check(ENTRY_C_OPEN,
                 lambda lib, buf: lib.g_c_open(buf, SCRATCH, mode, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_open({DEM_NAME!r}, {mode:#x})")
    check_d0_low_word(info, f"c_open({DEM_NAME!r}, {mode:#x})")


# `mode & 1` — the TRUNCATING open. Its four GEMDOS calls are Fdelete, Fcreate, Fclose and then the
# ordinary Fopen, and only the first is runnable here: `os_fdelete` CLEARS the staged slot's name,
# and `os_fcreate` refuses a name the harness has not declared ("the harness declares the
# filesystem", tools/recreate_kit/include/os.h) — so the create that follows the delete always
# refuses. The DELETE-FAILS arm is the half that runs, and it is the half with a branch in it;
# ../STATUS.md records the other three calls as read-verified with that exact blocker. Nothing in
# the game asks for this mode at all: `c_creat` requests OPEN_MODE_WRITE only.

def test_c_open_truncating_abandons_the_call_when_the_delete_fails():
    """A delete that answers EFILNF returns -1 without creating anything.

    The file the case names is NOT staged, so `c_unlink` answers -1 — which is the one input that
    separates the arm's first call from the three after it, and the only path through the arm the
    model can run to the `rts`.
    """
    rng = random.Random(0x571)
    pokes, _handles = staged([(SCR_NAME, b"a different file")])
    pokes = abi.merge_pokes(pokes, path_poke(rng, DEM_NAME), fd_table_poke(rng, ()),
                            trap_slot_noise(rng),
                            abi.stack_args((4, SCRATCH), (2, OPEN_MODE_TRUNCATE)))
    info = check(ENTRY_C_OPEN,
                 lambda lib, buf: lib.g_c_open(buf, SCRATCH, OPEN_MODE_TRUNCATE,
                                               CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note="c_open truncating a missing file")
    check_d0_low_word(info, "c_open truncating a missing file")
    assert info["ret"] & 0xffff == 0xffff


@pytest.mark.parametrize("name,handle", (("CON:", FD_DEVICE_CON), ("AUX:", FD_DEVICE_AUX),
                                         ("PRT:", FD_DEVICE_PRT)))
def test_c_open_a_pseudo_device(name, handle):
    """The three names never reach GEMDOS — and the trap save slots prove it: they stay as staged."""
    rng = random.Random(handle)
    pokes = abi.merge_pokes(path_poke(rng, name), fd_table_poke(rng, ()), trap_slot_noise(rng))
    pokes = abi.merge_pokes(pokes, abi.stack_args((4, SCRATCH), (2, FD_MODE_BINARY)))
    info = check(ENTRY_C_OPEN,
                 lambda lib, buf: lib.g_c_open(buf, SCRATCH, FD_MODE_BINARY, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_open({name!r})")
    check_d0_low_word(info, f"c_open({name!r})")
    assert info["ret"] & 0xffff == handle


@pytest.mark.parametrize("mode", (0, FD_MODE_BINARY))
def test_c_creat_a_staged_file(mode):
    """Fcreate truncates the staged file to zero length, which the FS table shows."""
    rng = random.Random(mode + 3)
    pokes, _handles = staged([(SCR_NAME, b"old high scores", 0x100)])
    pokes = abi.merge_pokes(pokes, path_poke(rng, SCR_NAME), fd_table_poke(rng, ()),
                            trap_slot_noise(rng))
    pokes = abi.merge_pokes(pokes, abi.stack_args((4, SCRATCH), (2, mode)))
    info = check(ENTRY_C_CREAT,
                 lambda lib, buf: lib.g_c_creat(buf, SCRATCH, mode, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_creat({SCR_NAME!r}, {mode:#x})")
    check_d0_low_word(info, f"c_creat({SCR_NAME!r}, {mode:#x})")


def test_c_creat_a_pseudo_device_goes_through_c_open():
    rng = random.Random(0xc0de)
    pokes = abi.merge_pokes(path_poke(rng, "CON:"), fd_table_poke(rng, ()), trap_slot_noise(rng))
    pokes = abi.merge_pokes(pokes, abi.stack_args((4, SCRATCH), (2, FD_MODE_BINARY)))
    info = check(ENTRY_C_CREAT,
                 lambda lib, buf: lib.g_c_creat(buf, SCRATCH, FD_MODE_BINARY, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note="c_creat('CON:')")
    check_d0_low_word(info, "c_creat('CON:')")
    assert info["ret"] & 0xffff == FD_DEVICE_CON


@pytest.mark.parametrize("handle", (6, 7, FD_DEVICE_CON, FD_DEVICE_PRT))
def test_c_close(handle):
    """A real handle reaches Fclose; a pseudo-handle returns 0 without touching the save slots."""
    rng = random.Random(handle * 3)
    pokes, _handles = staged([(DEM_NAME, b"demo"), (SCR_NAME, b"scores")], open_slots=(0, 1))
    pokes = abi.merge_pokes(pokes, fd_table_poke(rng, ((6, FD_MODE_BINARY), (handle, 0))),
                            trap_slot_noise(rng))
    pokes = abi.merge_pokes(pokes, abi.stack_args((2, handle)))
    info = check(ENTRY_C_CLOSE,
                 lambda lib, buf: lib.g_c_close(buf, handle, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_close({handle:#x})")
    check_d0_low_word(info, f"c_close({handle:#x})")


@pytest.mark.parametrize("length", (0, 1, 4, 16, 40))
def test_c_read_binary(length):
    """Binary mode: one Fread and the count, with no CR translation."""
    rng = random.Random(length)
    data = bytes(rng.randrange(256) for _ in range(32))
    pokes, handles = staged([(DEM_NAME, data)], open_slots=(0,))
    handle = handles[DEM_NAME]
    pokes = abi.merge_pokes(pokes, fd_table_poke(rng, ((handle, FD_MODE_BINARY),)),
                            trap_slot_noise(rng))
    pokes = abi.merge_pokes(pokes, noise_around(rng, SCRATCH, bytes(64)))
    pokes = abi.merge_pokes(pokes, abi.stack_args((2, handle), (4, SCRATCH), (2, length)))
    info = check(ENTRY_C_READ,
                 lambda lib, buf: lib.g_c_read(buf, handle, SCRATCH, length, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_read binary {length}")
    check_d0_low_word(info, f"c_read binary {length}")


@pytest.mark.parametrize("length,payload", (
    (8, b"abc\rdef\rghi\rjkl"),
    (16, b"\r\r\r\rabcdefghijkl"),
    (16, b"no carriage returns here at all"),
    (16, b"short\rfile"),                       # runs out mid-pass: the EOF arm
    (1, b"\rX"),
))
def test_c_read_text(length, payload):
    """Text mode: the CRs are dropped and the buffer is TOPPED UP by further Freads.

    The refill is what makes this more than a copy — the second and later Freads leave
    RET_C_READ_FREAD_REFILL in the trampoline's return slot and the write cursor in its A2 slot, so
    a reconstruction that read once and translated in place would differ there as well as in the
    bytes.
    """
    rng = random.Random(length * 101 + len(payload))
    pokes, handles = staged([(DEM_NAME, payload)], open_slots=(0,))
    handle = handles[DEM_NAME]
    pokes = abi.merge_pokes(pokes, fd_table_poke(rng, ((handle, 0),)), trap_slot_noise(rng))
    pokes = abi.merge_pokes(pokes, noise_around(rng, SCRATCH, bytes(64)))
    pokes = abi.merge_pokes(pokes, abi.stack_args((2, handle), (4, SCRATCH), (2, length)))
    info = check(ENTRY_C_READ,
                 lambda lib, buf: lib.g_c_read(buf, handle, SCRATCH, length, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_read text {length} {payload!r}")
    check_d0_low_word(info, f"c_read text {length} {payload!r}")



# ================================================================================================
# The console writers, and the low-level write and seek the buffered layer sits on
#
# THE SURFACE HERE IS PARTLY OFF-IMAGE. `c_conout_write` moves no memory at all: what it produces is
# the kit's ordered console-byte ledger (TRAP_MODEL.md, Phase 13), which `harness.differential`
# compares on every run without a case asking, plus the three trampoline save slots — and those are
# what say WHICH of its two Cconout sites ran last. Every case below therefore stages the slots with
# noise (`trap_slot_noise`), exactly as the file layer's do.
# ================================================================================================



@pytest.mark.parametrize("text,length", (
    (b"", 0),
    (b"A", 1),
    (b"hi\nthere\n", 9),
    (b"\n", 1),
    (b"partial write", 4),            # fewer bytes than the string holds
    (bytes(range(0x20, 0x80)), 0x60),  # every printable byte, none of them a newline
    (b"\x80\xff\x0a\x00", 4),          # high-bit bytes, and a NUL that is written like any other
))
def test_c_conout_write(text, length):
    """Every byte through GEMDOS Cconout, with a CR inserted before each newline."""
    rng = random.Random(len(text) * 31 + length)
    pokes = abi.merge_pokes(noise_around(rng, SCRATCH, text), trap_slot_noise(rng),
                            abi.stack_args((4, SCRATCH), (2, length)))
    check(ENTRY_C_CONOUT_WRITE,
          lambda lib, buf: lib.g_c_conout_write(buf, SCRATCH, length, CALLER_A1, CALLER_A2),
          pokes=pokes, regs=caller_registers(), note=f"c_conout_write({text!r}, {length})")


def test_c_conout_write_of_nothing_leaves_the_ledger_empty():
    """The count is tested BEFORE it is decremented, so a length of 0 writes nothing at all.

    Asserted rather than left to the diff: an empty ledger on both sides is what a routine that
    never ran also produces, so the case says which it means — and the SAME staging with length 1
    (above) does log, which is what makes the pair evidence.
    """
    rng = random.Random(0x0e)
    pokes = abi.merge_pokes(noise_around(rng, SCRATCH, b"A"), trap_slot_noise(rng),
                            abi.stack_args((4, SCRATCH), (2, 0)))
    info = check(ENTRY_C_CONOUT_WRITE,
                 lambda lib, buf: lib.g_c_conout_write(buf, SCRATCH, 0, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note="c_conout_write(_, 0)")
    assert len(check(ENTRY_C_CONOUT_WRITE,
                     lambda lib, buf: lib.g_c_conout_write(buf, SCRATCH, 1, CALLER_A1, CALLER_A2),
                     pokes=abi.merge_pokes(noise_around(rng, SCRATCH, b"A"), trap_slot_noise(rng),
                                           abi.stack_args((4, SCRATCH), (2, 1))),
                     regs=caller_registers(), note="c_conout_write(_, 1)")["regs"]["events"]) == 1
    assert info["regs"]["events"] == []


# ---- c_lseek -------------------------------------------------------------------------------
SEEK_FROM_START = 0
SEEK_FROM_CURRENT = 1
SEEK_FROM_END = 2


@pytest.mark.parametrize("offset,whence", (
    (0, SEEK_FROM_START),
    (5, SEEK_FROM_START),
    (0, SEEK_FROM_CURRENT),
    (0, SEEK_FROM_END),
    (-4, SEEK_FROM_END),
    (16, SEEK_FROM_START),      # into the reserved capacity, past the staged length
))
def test_c_lseek(offset, whence):
    """GEMDOS Fseek over the staged-file cursor, which the FS table then shows moved."""
    rng = random.Random(offset * 7 + whence)
    pokes, handles = staged([(DEM_NAME, b"0123456789", 0x20)], open_slots=(0,))
    handle = handles[DEM_NAME]
    pokes = abi.merge_pokes(pokes, trap_slot_noise(rng), fd_table_poke(rng, ()))
    pokes = abi.merge_pokes(pokes, abi.stack_args((2, handle), (4, offset), (2, whence)))
    info = check(ENTRY_C_LSEEK,
                 lambda lib, buf: lib.g_c_lseek(buf, handle, offset & 0xffffffff, whence,
                                                CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_lseek({offset}, {whence})")
    check_d0_long(info, f"c_lseek({offset}, {whence})")


@pytest.mark.parametrize("handle", (FD_DEVICE_CON, FD_DEVICE_AUX, FD_DEVICE_PRT))
def test_c_lseek_refuses_a_pseudo_handle(handle):
    """A negative handle is answered -1 without a trap: the save slots stay as staged."""
    rng = random.Random(handle)
    pokes = abi.merge_pokes(trap_slot_noise(rng),
                            abi.stack_args((2, handle), (4, 0), (2, SEEK_FROM_START)))
    info = check(ENTRY_C_LSEEK,
                 lambda lib, buf: lib.g_c_lseek(buf, handle, 0, SEEK_FROM_START,
                                                CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_lseek on {handle:#x}")
    check_d0_long(info, f"c_lseek on {handle:#x}")
    assert info["ret"] == -1


# ---- c_write -------------------------------------------------------------------------------

@pytest.mark.parametrize("text,length", (
    (b"", 0),
    (b"one line, no newline", 20),
    (b"a\nb\n", 4),
    (b"\n\n\n", 3),
    (b"trailing\n", 9),
    (b"only the first six", 6),
))
def test_c_write_binary(text, length):
    """Binary mode: one Fwrite of the whole span, and no CR/LF expansion."""
    rng = random.Random(len(text) + length * 3)
    pokes, handles = staged([(SCR_NAME, b"", 0x80)], open_slots=(0,))
    handle = handles[SCR_NAME]
    pokes = abi.merge_pokes(pokes, noise_around(rng, SCRATCH, text), trap_slot_noise(rng),
                            fd_table_poke(rng, ((handle, FD_MODE_BINARY),)))
    pokes = abi.merge_pokes(pokes, abi.stack_args((2, handle), (4, SCRATCH), (2, length)))
    info = check(ENTRY_C_WRITE,
                 lambda lib, buf: lib.g_c_write(buf, handle, SCRATCH, length,
                                                CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_write binary {text!r} {length}")
    check_d0_low_word(info, f"c_write binary {text!r} {length}")


@pytest.mark.parametrize("text,length", (
    (b"", 0),
    (b"no newlines here", 16),
    (b"a\nb\n", 4),
    (b"\nleading", 8),
    (b"trailing\n", 9),
    (b"\n\n\n\n", 4),
    (b"middle\nsplit", 12),
))
def test_c_write_text(text, length):
    """Text mode: a newline goes out as the two bytes of `A_crlf`, in an Fwrite of its own.

    The three sites leave different RET_* in the trampoline slot, so the run of bytes before a
    newline, the CR/LF pair and the tail are told apart by more than the file's contents.
    """
    rng = random.Random(len(text) * 17 + length)
    pokes, handles = staged([(SCR_NAME, b"", 0x80)], open_slots=(0,))
    handle = handles[SCR_NAME]
    pokes = abi.merge_pokes(pokes, noise_around(rng, SCRATCH, text), trap_slot_noise(rng),
                            fd_table_poke(rng, ((handle, 0),)))
    pokes = abi.merge_pokes(pokes, abi.stack_args((2, handle), (4, SCRATCH), (2, length)))
    info = check(ENTRY_C_WRITE,
                 lambda lib, buf: lib.g_c_write(buf, handle, SCRATCH, length,
                                                CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_write text {text!r} {length}")
    check_d0_low_word(info, f"c_write text {text!r} {length}")


def test_the_crlf_pair_c_write_expands_a_newline_to(post_init_image):
    """A_crlf really does hold CR then LF — the two bytes every text-mode newline costs."""
    assert bytes(post_init_image[A_CRLF:A_CRLF + CRLF_BYTES]) == b"\r\n"


@pytest.mark.parametrize("text,length", ((b"", 0), (b"CON:\n", 5), (b"no newline", 10)))
def test_c_write_to_the_console(text, length):
    """CON: is answered by c_conout_write before the fd-mode table is consulted at all."""
    rng = random.Random(length * 5 + len(text))
    pokes = abi.merge_pokes(noise_around(rng, SCRATCH, text), trap_slot_noise(rng),
                            fd_table_poke(rng, ()),
                            abi.stack_args((2, FD_DEVICE_CON), (4, SCRATCH), (2, length)))
    info = check(ENTRY_C_WRITE,
                 lambda lib, buf: lib.g_c_write(buf, FD_DEVICE_CON, SCRATCH, length,
                                                CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_write CON: {text!r}")
    check_d0_low_word(info, f"c_write CON: {text!r}")
    assert info["ret"] & 0xffff == length



# ================================================================================================
# The buffered FILE layer
#
# EVERY CASE STAGES THE WHOLE `c_iob` REGION, not just the record it means to use. The table, the
# per-record fallback bytes below it and `A_c_bufsiz` between them are consecutive, and staging them
# as ONE noise-filled span is what turns "wrote one record too far" into a difference — the post-init
# image holds most of that region as zeroes, where an overrun would write zeroes over zeroes.
# ================================================================================================

FILE_SLOT = 3                              # the first record after stdin/stdout/stderr
A_FILE = A_C_IOB + FILE_SLOT * C_IOB_STRIDE
FILE_BUFFER = SCRATCH + 0x200              # where a case puts a stream's buffer, clear of SCRATCH
FOPEN_MODE_STRING = SCRATCH + 0x100        # ...and the mode string it hands c_fopen


def file_record(ptr=0, cnt=0, base=0, flags=0, fd=0, offset=0, bufsiz=0):
    """One 20-byte FILE, in the field order include/clib.h freezes."""
    return struct.pack(">IHIHHIH", ptr, cnt & 0xffff, base, flags, fd & 0xffff, offset,
                       bufsiz & 0xffff)


# The three records `init_globals` establishes, restated so a case's own table looks like the
# program's rather than like an empty one — which is what makes `c_fopen` pick FILE_SLOT.
STDIO_RECORDS = (
    file_record(flags=FILE_READ | FILE_UNBUFFERED, fd=FD_DEVICE_CON),
    file_record(flags=FILE_WRITE | FILE_LINEBUF, fd=FD_DEVICE_CON, bufsiz=0x200),
    file_record(flags=FILE_WRITE | FILE_LINEBUF, fd=FD_DEVICE_CON, bufsiz=0x200),
)


def iob_poke(rng, record=None, bufsiz=0x200):
    """`A_c_unbuf_chars`, `A_c_bufsiz` and all 73 records as one span, with `record` at FILE_SLOT.

    The fallback bytes are seeded with NOISE because an unbuffered stream's whole buffer is one of
    them: a routine that wrote to the wrong slot would otherwise write a zero over a zero. The
    records after FILE_SLOT are left FREE (flags 0) rather than noisy, because `c_fopen` scans them
    and a noisy flags word would make every slot look busy.
    """
    length = A_C_IOB - A_C_UNBUF_CHARS + C_IOB_SLOTS * C_IOB_STRIDE
    span = bytearray(rng.randbytes(length + GUARD))
    span[A_C_BUFSIZ - A_C_UNBUF_CHARS:A_C_BUFSIZ - A_C_UNBUF_CHARS + 2] = abi.word(bufsiz)
    table = A_C_IOB - A_C_UNBUF_CHARS
    records = STDIO_RECORDS + ((record,) if record is not None else ())
    for slot in range(C_IOB_SLOTS):
        at = table + slot * C_IOB_STRIDE
        span[at:at + C_IOB_STRIDE] = records[slot] if slot < len(records) else file_record()
    return {A_C_UNBUF_CHARS: bytes(span)}


def buffered_case(rng, record, files=(), open_slots=(), buffer=b"", fd_modes=(), bufsiz=0x200,
                  hint=None, cursors=()):
    """The world every FILE-layer case stages: the table, the stream's buffer, the fd modes, files.

    `hint` is `A_c_fopen_slot_hint`, staged only where a case means to say something about it —
    the post-init image holds it as zero and nothing in the program ever writes it.
    """
    pokes, handles = staged(list(files), open_slots=open_slots, cursors=cursors)
    pokes = abi.merge_pokes(pokes, iob_poke(rng, record, bufsiz=bufsiz),
                            noise_around(rng, FILE_BUFFER, buffer),
                            fd_table_poke(rng, fd_modes), trap_slot_noise(rng))
    if hint is not None:
        pokes = abi.merge_pokes(pokes, {A_C_FOPEN_SLOT_HINT: abi.long(hint)})
    return pokes, handles


# ---- c_fflush ------------------------------------------------------------------------------

def test_c_fflush_refuses_a_slot_that_is_not_open():
    rng = random.Random(0xf1)
    pokes, _ = buffered_case(rng, file_record(flags=FILE_DIRTY))
    pokes = abi.merge_pokes(pokes, abi.stack_args((4, A_FILE)))
    info = check(ENTRY_C_FFLUSH,
                 lambda lib, buf: lib.g_c_fflush(buf, A_FILE, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note="c_fflush on a free slot")
    check_d0_low_word(info, "c_fflush on a free slot")
    assert info["ret"] & 0xffff == 0xffff


@pytest.mark.parametrize("content,flags,mode", (
    (b"", FILE_WRITE | FILE_DIRTY, FD_MODE_BINARY),
    (b"twelve bytes", FILE_WRITE | FILE_DIRTY, FD_MODE_BINARY),
    (b"a\nb\n", FILE_WRITE | FILE_DIRTY, 0),                       # the text expansion
    (b"appended", FILE_WRITE | FILE_DIRTY | FILE_APPEND, FD_MODE_BINARY),
    (b"read-write", FILE_READ | FILE_WRITE | FILE_DIRTY, FD_MODE_BINARY),
))
def test_c_fflush_writes_a_dirty_buffer(content, flags, mode):
    """A DIRTY buffer goes out through c_write, and the stream's file offset advances by it."""
    rng = random.Random(len(content) * 13 + flags)
    record = file_record(ptr=FILE_BUFFER + len(content), base=FILE_BUFFER, flags=flags,
                         fd=harness.OS_FS_FIRST_HANDLE, offset=0x40, bufsiz=0x20)
    pokes, handles = buffered_case(rng, record, files=[(SCR_NAME, b"", 0x80)], open_slots=(0,),
                                   buffer=content,
                                   fd_modes=((harness.OS_FS_FIRST_HANDLE, mode),))
    pokes = abi.merge_pokes(pokes, abi.stack_args((4, A_FILE)))
    info = check(ENTRY_C_FFLUSH,
                 lambda lib, buf: lib.g_c_fflush(buf, A_FILE, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(),
                 note=f"c_fflush dirty {content!r} flags={flags:#x}")
    check_d0_low_word(info, f"c_fflush dirty {content!r}")
    assert handles[SCR_NAME] == harness.OS_FS_FIRST_HANDLE


@pytest.mark.parametrize("unread", (0, 1, 7))
def test_c_fflush_rewinds_a_read_buffer(unread):
    """A clean read buffer is dropped, and the GEMDOS cursor seeks BACK over what was never read."""
    rng = random.Random(unread + 0x5ead)
    record = file_record(ptr=FILE_BUFFER + 3, cnt=unread, base=FILE_BUFFER, flags=FILE_READ,
                         fd=harness.OS_FS_FIRST_HANDLE, offset=0, bufsiz=0x20)
    pokes, _ = buffered_case(rng, record, files=[(DEM_NAME, b"0123456789", 0x20)],
                             open_slots=(0,), buffer=b"012", cursors=((0, 10),),
                             fd_modes=((harness.OS_FS_FIRST_HANDLE, FD_MODE_BINARY),))
    pokes = abi.merge_pokes(pokes, abi.stack_args((4, A_FILE)))
    info = check(ENTRY_C_FFLUSH,
                 lambda lib, buf: lib.g_c_fflush(buf, A_FILE, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_fflush read, {unread} unread")
    check_d0_low_word(info, f"c_fflush read, {unread} unread")


def test_c_fflush_of_a_console_stream_seeks_nothing():
    """`fd <= 0` skips the rewind — which is every pseudo-device, since their handles are negative."""
    rng = random.Random(0xc04)
    record = file_record(ptr=FILE_BUFFER + 2, cnt=5, base=FILE_BUFFER, flags=FILE_READ,
                         fd=FD_DEVICE_CON, bufsiz=0x20)
    pokes, _ = buffered_case(rng, record, buffer=b"ab")
    pokes = abi.merge_pokes(pokes, abi.stack_args((4, A_FILE)))
    check(ENTRY_C_FFLUSH, lambda lib, buf: lib.g_c_fflush(buf, A_FILE, CALLER_A1, CALLER_A2),
          pokes=pokes, regs=caller_registers(), note="c_fflush on CON:")


# ---- c_fclose ------------------------------------------------------------------------------

@pytest.mark.parametrize("flags", (
    FILE_READ,
    FILE_READ | FILE_MYBUF,
    FILE_WRITE | FILE_DIRTY | FILE_MYBUF,
    0,                                     # a free slot: c_fflush refuses and c_close never runs
))
def test_c_fclose(flags):
    """Flush, hand a GEMDOS-allocated buffer back, blank the record, close the handle."""
    rng = random.Random(flags * 3 + 1)
    record = file_record(ptr=FILE_BUFFER + 4, cnt=2, base=FILE_BUFFER, flags=flags,
                         fd=harness.OS_FS_FIRST_HANDLE, bufsiz=0x20)
    pokes, _ = buffered_case(rng, record, files=[(SCR_NAME, b"scores", 0x40)], open_slots=(0,),
                             buffer=b"four", cursors=((0, 6),),
                             fd_modes=((harness.OS_FS_FIRST_HANDLE, FD_MODE_BINARY),))
    pokes = abi.merge_pokes(pokes, abi.stack_args((4, A_FILE)))
    info = check(ENTRY_C_FCLOSE,
                 lambda lib, buf: lib.g_c_fclose(buf, A_FILE, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_fclose flags={flags:#x}")
    check_d0_low_word(info, f"c_fclose flags={flags:#x}")


# ---- c_filbuf ------------------------------------------------------------------------------

@pytest.mark.parametrize("flags,base,bufsiz", (
    (FILE_READ, 0, 0x10),                          # no buffer yet: GEMDOS Malloc supplies one
    (FILE_READ, FILE_BUFFER, 0x10),                # ...and one that is already there
    (FILE_READ | FILE_UNBUFFERED, 0, 0x10),        # the one-byte fallback slot, read one at a time
    (FILE_READ | FILE_LINEBUF, FILE_BUFFER, 0x10),  # line buffered: also one byte at a time
    (FILE_READ | FILE_WRITE, FILE_BUFFER, 4),
))
def test_c_filbuf(flags, base, bufsiz):
    """Refill and hand back the first byte, recording where in the file the buffer starts."""
    rng = random.Random(flags * 7 + bufsiz)
    record = file_record(ptr=base, base=base, flags=flags, fd=harness.OS_FS_FIRST_HANDLE,
                         offset=0x1234, bufsiz=bufsiz)
    pokes, _ = buffered_case(rng, record, files=[(DEM_NAME, b"abcdefghij", 0x20)],
                             open_slots=(0,), buffer=bytes(0x20),
                             fd_modes=((harness.OS_FS_FIRST_HANDLE, FD_MODE_BINARY),))
    pokes = abi.merge_pokes(pokes, abi.stack_args((4, A_FILE)))
    info = check(ENTRY_C_FILBUF,
                 lambda lib, buf: lib.g_c_filbuf(buf, A_FILE, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(),
                 note=f"c_filbuf flags={flags:#x} base={base:#x}")
    check_d0_low_word(info, f"c_filbuf flags={flags:#x}")


@pytest.mark.parametrize("flags", (FILE_READ | FILE_EOF, FILE_READ | FILE_ERR, FILE_WRITE))
def test_c_filbuf_refuses_a_stream_it_cannot_read(flags):
    """EOF or ERR is refused outright, and a write-only stream sets ERR and becomes one."""
    rng = random.Random(flags + 0xf1b)
    record = file_record(base=FILE_BUFFER, flags=flags, fd=harness.OS_FS_FIRST_HANDLE, bufsiz=0x10)
    pokes, _ = buffered_case(rng, record, files=[(DEM_NAME, b"abc", 0x10)], open_slots=(0,),
                             buffer=bytes(0x10),
                             fd_modes=((harness.OS_FS_FIRST_HANDLE, FD_MODE_BINARY),))
    pokes = abi.merge_pokes(pokes, abi.stack_args((4, A_FILE)))
    info = check(ENTRY_C_FILBUF,
                 lambda lib, buf: lib.g_c_filbuf(buf, A_FILE, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_filbuf refuses {flags:#x}")
    check_d0_low_word(info, f"c_filbuf refuses {flags:#x}")
    assert info["ret"] & 0xffff == 0xffff


def test_c_filbuf_at_end_of_file():
    """A read that returns nothing sets EOF and answers -1; a shorter one is not an error."""
    rng = random.Random(0xe0f)
    record = file_record(base=FILE_BUFFER, flags=FILE_READ, fd=harness.OS_FS_FIRST_HANDLE,
                         bufsiz=0x10)
    pokes, _ = buffered_case(rng, record, files=[(DEM_NAME, b"", 0x10)], open_slots=(0,),
                             buffer=bytes(0x10),
                             fd_modes=((harness.OS_FS_FIRST_HANDLE, FD_MODE_BINARY),))
    pokes = abi.merge_pokes(pokes, abi.stack_args((4, A_FILE)))
    info = check(ENTRY_C_FILBUF,
                 lambda lib, buf: lib.g_c_filbuf(buf, A_FILE, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note="c_filbuf at eof")
    check_d0_low_word(info, "c_filbuf at eof")
    assert info["ret"] & 0xffff == 0xffff


def test_c_filbuf_off_stride_record_lands_the_divs_w_remainder_in_the_high_word():
    """An UNBUFFERED stream whose record is not on the 20-byte stride, which is the only way to see
    `divs.w`'s remainder.

    `unbuffered_char_slot` divides `file - A_c_iob` by the stride with `divs.w` — quotient in the
    low word, REMAINDER IN THE HIGH — and the `adda.l` that follows adds the whole longword, so a
    record two bytes off the stride puts its one-byte buffer 0x20000 further up the image. No caller
    in the program passes such a pointer, so this case fabricates one; without it the quirk is
    transcription nobody has run (a mutation dropping the remainder survives the rest of the file).
    """
    rng = random.Random(0xd1f5)
    off_stride = A_FILE + 2
    record = file_record(base=0, flags=FILE_READ | FILE_UNBUFFERED,
                         fd=harness.OS_FS_FIRST_HANDLE, bufsiz=1)
    span = bytearray(iob_poke(rng)[A_C_UNBUF_CHARS])
    at = off_stride - A_C_UNBUF_CHARS
    span[at:at + C_IOB_STRIDE] = record
    pokes, _ = staged([(DEM_NAME, b"abcdef", 0x20)], open_slots=(0,))
    pokes = abi.merge_pokes(pokes, {A_C_UNBUF_CHARS: bytes(span)}, trap_slot_noise(rng),
                            fd_table_poke(rng, ((harness.OS_FS_FIRST_HANDLE, FD_MODE_BINARY),)),
                            abi.stack_args((4, off_stride)))
    info = check(ENTRY_C_FILBUF,
                 lambda lib, buf: lib.g_c_filbuf(buf, off_stride, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note="c_filbuf on an off-stride record")
    check_d0_low_word(info, "c_filbuf on an off-stride record")


# ---- c_flsbuf and c_putc ---------------------------------------------------------------------

@pytest.mark.parametrize("byte,flags,base,held", (
    (ord("x"), FILE_WRITE | FILE_LINEBUF, FILE_BUFFER, 2),      # room left: no flush at all
    (ord("\n"), FILE_WRITE | FILE_LINEBUF, FILE_BUFFER, 2),     # a newline flushes the line
    (ord("z"), FILE_WRITE | FILE_LINEBUF, FILE_BUFFER, 0x1f),   # a full buffer flushes too
    (ord("y"), FILE_WRITE | FILE_UNBUFFERED, FILE_BUFFER, 0),
    (ord("w"), FILE_WRITE, FILE_BUFFER, 3),                      # fully buffered: flush, then store
    (ord("v"), FILE_WRITE, 0, 0),                                # ...and one with no buffer yet
    (ord("u"), FILE_READ, FILE_BUFFER, 0),                       # not a write stream: ERR, -1
    (ord("t"), FILE_WRITE | FILE_ERR, FILE_BUFFER, 0),
))
def test_c_flsbuf(byte, flags, base, held):
    rng = random.Random(byte * 11 + flags + held)
    record = file_record(ptr=(base + held) if base else 0, base=base, flags=flags,
                         fd=harness.OS_FS_FIRST_HANDLE, bufsiz=0x20)
    pokes, _ = buffered_case(rng, record, files=[(SCR_NAME, b"", 0x100)], open_slots=(0,),
                             buffer=bytes(held),
                             fd_modes=((harness.OS_FS_FIRST_HANDLE, FD_MODE_BINARY),))
    pokes = abi.merge_pokes(pokes, abi.stack_args((2, byte), (4, A_FILE)))
    info = check(ENTRY_C_FLSBUF,
                 lambda lib, buf: lib.g_c_flsbuf(buf, byte, A_FILE, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(),
                 note=f"c_flsbuf({byte:#x}) flags={flags:#x} held={held}")
    check_d0_low_word(info, f"c_flsbuf({byte:#x}) flags={flags:#x}")


@pytest.mark.parametrize("count", (5, 1, 0))
def test_c_putc(count):
    """`cnt` is decremented before it is tested, so a count of 0 goes straight to c_flsbuf."""
    rng = random.Random(count + 0x9c)
    record = file_record(ptr=FILE_BUFFER + 2, cnt=count, base=FILE_BUFFER,
                         flags=FILE_WRITE | FILE_LINEBUF, fd=harness.OS_FS_FIRST_HANDLE,
                         bufsiz=0x20)
    pokes, _ = buffered_case(rng, record, files=[(SCR_NAME, b"", 0x100)], open_slots=(0,),
                             buffer=b"ab",
                             fd_modes=((harness.OS_FS_FIRST_HANDLE, FD_MODE_BINARY),))
    pokes = abi.merge_pokes(pokes, abi.stack_args((2, ord("Q")), (4, A_FILE)))
    info = check(ENTRY_C_PUTC,
                 lambda lib, buf: lib.g_c_putc(buf, ord("Q"), A_FILE, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_putc cnt={count}")
    check_d0_low_word(info, f"c_putc cnt={count}")


# ---- c_fread -------------------------------------------------------------------------------

@pytest.mark.parametrize("size,items,held,content", (
    (1, 4, 6, b"abcdefghij"),      # entirely out of the buffer already in hand
    (1, 8, 2, b"abcdefghij"),      # runs out and refills through c_filbuf
    (2, 3, 0, b"abcdefghij"),      # records wider than a byte
    (1, 20, 0, b"abc"),            # the file ends part-way: a partial record is not reported
    (1, 0, 4, b"abcdefghij"),      # nothing asked for
    (4, 2, 3, b"short"),           # ends mid-record, with a remainder the divide drops
))
def test_c_fread(size, items, held, content):
    rng = random.Random(size * 101 + items * 7 + held)
    record = file_record(ptr=FILE_BUFFER, cnt=held, base=FILE_BUFFER, flags=FILE_READ,
                         fd=harness.OS_FS_FIRST_HANDLE, bufsiz=8)
    pokes, _ = buffered_case(rng, record, files=[(DEM_NAME, content, 0x20)], open_slots=(0,),
                             buffer=content[:held] + bytes(8 - min(held, 8)),
                             fd_modes=((harness.OS_FS_FIRST_HANDLE, FD_MODE_BINARY),))
    pokes = abi.merge_pokes(pokes, noise_around(rng, SCRATCH, bytes(64)),
                            abi.stack_args((4, SCRATCH), (2, size), (2, items), (4, A_FILE)))
    info = check(ENTRY_C_FREAD,
                 lambda lib, buf: lib.g_c_fread(buf, SCRATCH, size, items, A_FILE,
                                                CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(),
                 note=f"c_fread({size}, {items}) held={held} {content!r}")
    check_d0_low_word(info, f"c_fread({size}, {items}) held={held}")


# ---- c_fopen -------------------------------------------------------------------------------

@pytest.mark.parametrize("mode,name", (
    ("br", DEM_NAME),          # the game's own two calls
    ("r", DEM_NAME),
    ("r+", DEM_NAME),
    ("w", SCR_NAME),
    ("bw", SCR_NAME),
    ("a", SCR_NAME),
    ("ba", SCR_NAME),
    ("w+", SCR_NAME),
))
def test_c_fopen(mode, name):
    """Parse the mode, claim FILE_SLOT, open or create, and record where the file cursor is."""
    rng = random.Random(len(mode) * 31 + len(name))
    pokes, _ = buffered_case(rng, None, files=[(name, b"0123456789", 0x40)],
                             buffer=bytes(0x20), fd_modes=(), hint=0)
    pokes = abi.merge_pokes(pokes, path_poke(rng, name),
                            noise_around(rng, FOPEN_MODE_STRING, mode.encode("ascii") + b"\0"))
    pokes = abi.merge_pokes(pokes, abi.stack_args((4, SCRATCH), (4, FOPEN_MODE_STRING)))
    info = check(ENTRY_C_FOPEN,
                 lambda lib, buf: lib.g_c_fopen(buf, SCRATCH, FOPEN_MODE_STRING,
                                                CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_fopen({name!r}, {mode!r})")
    check_d0_long(info, f"c_fopen({name!r}, {mode!r})")
    assert info["ret"] == A_FILE


@pytest.mark.parametrize("mode", ("x", "", "b", "+r", "R"))
def test_c_fopen_refuses_a_mode_it_does_not_know(mode):
    """Only r/w/a open anything, and only after an optional leading 'b' — so "rb" does not parse."""
    rng = random.Random(0xbad + len(mode))
    pokes, _ = buffered_case(rng, None, files=[(DEM_NAME, b"data", 0x20)], hint=0)
    pokes = abi.merge_pokes(pokes, path_poke(rng, DEM_NAME),
                            noise_around(rng, FOPEN_MODE_STRING, mode.encode("ascii") + b"\0"))
    pokes = abi.merge_pokes(pokes, abi.stack_args((4, SCRATCH), (4, FOPEN_MODE_STRING)))
    info = check(ENTRY_C_FOPEN,
                 lambda lib, buf: lib.g_c_fopen(buf, SCRATCH, FOPEN_MODE_STRING,
                                                CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_fopen mode {mode!r}")
    check_d0_long(info, f"c_fopen mode {mode!r}")
    assert info["ret"] == 0


def test_c_fopen_takes_the_slot_hint_when_one_is_set():
    """`A_c_fopen_slot_hint` short-circuits the scan — and is cleared on the way past.

    Nothing in this program ever sets it, so this is the only thing that exercises the arm; the
    hint names a LATER record than the scan would have picked, which is what tells the two apart.
    """
    rng = random.Random(0x81)
    hinted = A_C_IOB + 9 * C_IOB_STRIDE
    pokes, _ = buffered_case(rng, None, files=[(DEM_NAME, b"data", 0x20)], hint=hinted)
    pokes = abi.merge_pokes(pokes, path_poke(rng, DEM_NAME),
                            noise_around(rng, FOPEN_MODE_STRING, b"br\0"))
    pokes = abi.merge_pokes(pokes, abi.stack_args((4, SCRATCH), (4, FOPEN_MODE_STRING)))
    info = check(ENTRY_C_FOPEN,
                 lambda lib, buf: lib.g_c_fopen(buf, SCRATCH, FOPEN_MODE_STRING,
                                                CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note="c_fopen with a slot hint")
    check_d0_long(info, "c_fopen with a slot hint")
    assert info["ret"] == hinted


def test_c_fopen_refuses_a_hint_past_the_end_of_the_table():
    """The range check is applied to the hint as well as to the scan's result."""
    rng = random.Random(0x82)
    pokes, _ = buffered_case(rng, None, files=[(DEM_NAME, b"data", 0x20)], hint=C_IOB_END)
    pokes = abi.merge_pokes(pokes, path_poke(rng, DEM_NAME),
                            noise_around(rng, FOPEN_MODE_STRING, b"br\0"))
    pokes = abi.merge_pokes(pokes, abi.stack_args((4, SCRATCH), (4, FOPEN_MODE_STRING)))
    info = check(ENTRY_C_FOPEN,
                 lambda lib, buf: lib.g_c_fopen(buf, SCRATCH, FOPEN_MODE_STRING,
                                                CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note="c_fopen with an out-of-range hint")
    check_d0_long(info, "c_fopen with an out-of-range hint")
    assert info["ret"] == 0


def test_the_c_iob_record_the_program_itself_establishes(post_init_image):
    """The three records `init_globals` writes, against include/clib.h's field offsets.

    This is what pins the FROZEN record layout to the image rather than to a reading of the asm: a
    wrong stride or a wrong field offset makes at least one of the three disagree.
    """
    expected = (
        (FILE_READ | FILE_UNBUFFERED, FD_DEVICE_CON, 0),
        (FILE_WRITE | FILE_LINEBUF, FD_DEVICE_CON, 0x200),
        (FILE_WRITE | FILE_LINEBUF, FD_DEVICE_CON, 0x200),
    )
    for slot, (flags, fd, bufsiz) in enumerate(expected):
        at = A_C_IOB + slot * C_IOB_STRIDE
        record = bytes(post_init_image[at:at + C_IOB_STRIDE])
        assert struct.unpack(">H", record[FILE_OFF_FLAGS:FILE_OFF_FLAGS + 2])[0] == flags
        assert struct.unpack(">H", record[FILE_OFF_FD:FILE_OFF_FD + 2])[0] == fd
        assert struct.unpack(">H", record[FILE_OFF_BUFSIZ:FILE_OFF_BUFSIZ + 2])[0] == bufsiz
    assert A_C_STDOUT == A_C_IOB + C_IOB_STRIDE
    assert C_IOB_END == A_C_IOB + C_IOB_SLOTS * C_IOB_STRIDE
    assert struct.unpack(">H", bytes(post_init_image[A_C_BUFSIZ:A_C_BUFSIZ + 2]))[0] == 0x200


# ================================================================================================
# The software floating-point package
#
# Every case compares the eight RESULT BYTES, never a host float. The package keeps 32 mantissa
# bits where an IEEE double has 53, so "the same number to Python" and "the same bytes" are
# different questions and only the second one is the one being asked.
# ================================================================================================

FP_LEFT = SCRATCH               # the destination operand: read, and written back
FP_RIGHT = SCRATCH + 0x40       # the source: read, and its sign word flipped and restored by fp_sub

# The DATA constants the front end's two random-range computations divide, multiply and add by
# (../names.txt: const_random_range, const_11, const_5).
A_CONST_RANDOM_RANGE = 0x250ec
A_CONST_11 = 0x250f4
A_CONST_5 = 0x250fc

FP_OP_ADD_DOUBLE = 0x0800       # the four opcodes the whole program uses: an eight-byte source and
FP_OP_MUL_DOUBLE = 0x0802       # one of add / multiply / divide / compare
FP_OP_DIV_DOUBLE = 0x0803
FP_OP_CMP_DOUBLE = 0x0804
FP_OP_ADD_SHORT = 0x2000        # ...and the three widening source kinds, which nothing reaches but
FP_OP_ADD_LONG = 0x2800         # which fp_dispatch's own body still has to get right
FP_OP_ADD_FLOAT = 0x1000

# Doubles chosen to reach the package's own branches rather than to be interesting numbers: zero and
# negative zero (a zero EXPONENT is the package's only special case), values a power of two apart
# (the shift-and-add path), values 40 exponents apart (the "drop the smaller operand" path), a pair
# that cancels exactly, and two whose low mantissa bits are exactly the ones the package discards.
FP_SAMPLES = (
    0.0, -0.0, 1.0, -1.0, 0.5, 2.0, 16794009.0, 11.0, 5.0, 20.0, 2.977e-06,
    1.0000000596046448, 1e300, -1e300, 1e-300, 3.141592653589793, -2.718281828459045,
    65535.0, 1.0 / 3.0, 123456789.0,
)


def fp_operand_pokes(rng, left, right):
    """Both operands, each in its own noise-guarded eight bytes."""
    return noise_around(rng, FP_LEFT, left) | noise_around(rng, FP_RIGHT, right)


def fp_binary_case(entry, glue_name, left, right, note):
    rng = random.Random(case_seed(note))
    pokes = fp_operand_pokes(rng, left, right)
    pokes = abi.merge_pokes(pokes, {A_FP_SUB_SIGN_FLAG: rng.randbytes(2)})
    pokes = abi.merge_pokes(pokes, abi.stack_args((4, FP_LEFT), (4, FP_RIGHT)))
    return check(entry, lambda lib, buf: getattr(lib, glue_name)(buf, FP_LEFT, FP_RIGHT),
                 pokes=pokes, note=note)


@pytest.mark.parametrize("entry,glue_name", (
    (ENTRY_FP_ADD, "g_fp_add"), (ENTRY_FP_SUB, "g_fp_sub"),
    (ENTRY_FP_MUL, "g_fp_mul"), (ENTRY_FP_DIV, "g_fp_div"),
))
@pytest.mark.parametrize("left,right", (
    (1.0, 1.0), (1.0, -1.0), (0.0, 1.0), (1.0, 0.0), (0.0, 0.0), (-0.0, 1.0),
    (1.0, 1e-300), (1e300, 1.0), (16794009.0, 11.0), (5.0, 20.0), (1.0 / 3.0, 3.0),
))
def test_fp_arithmetic_edges(entry, glue_name, left, right):
    fp_binary_case(entry, glue_name, abi.double(left), abi.double(right),
                   f"{glue_name}({left!r}, {right!r})")


def test_fp_cmp_edges():
    """fp_cmp's only output is A_fp_ccr — the whole SR, condition codes and all."""
    for left, right in ((1.0, 1.0), (1.0, 2.0), (2.0, 1.0), (-1.0, 1.0), (1.0, -1.0),
                        (-1.0, -2.0), (0.0, -0.0), (1e300, 1e-300), (0.0, 0.0)):
        rng = random.Random(int(abs(left) + abs(right)) & 0xffff)
        pokes = fp_operand_pokes(rng, abi.double(left), abi.double(right))
        pokes = abi.merge_pokes(pokes, {A_FP_CCR: rng.randbytes(2)})
        pokes = abi.merge_pokes(pokes, abi.stack_args((4, FP_LEFT), (4, FP_RIGHT)))
        check(ENTRY_FP_CMP,
              lambda lib, buf: lib.g_fp_cmp(buf, FP_LEFT, FP_RIGHT, FP_CMP_STATUS_HIGH),
              pokes=pokes, note=f"fp_cmp({left!r}, {right!r})")


@pytest.mark.parametrize("value", FP_SAMPLES)
def test_fp_double_to_long(value):
    rng = random.Random(hash(value) & 0xffff)
    pokes = abi.merge_pokes(noise_around(rng, FP_LEFT, abi.double(value)),
                            abi.stack_args((4, FP_LEFT)))
    check(ENTRY_FP_DOUBLE_TO_LONG, lambda lib, buf: lib.g_fp_double_to_long(buf, FP_LEFT),
          pokes=pokes, note=f"fp_double_to_long({value!r})")


@pytest.mark.parametrize("value", (0, 1, -1, 2, -2, 255, 256, 0x7fffffff, -0x80000000,
                                   16794009, 0xffff, 0x10000, 0x123456))
def test_fp_long_to_double(value):
    rng = random.Random(value & 0xffff)
    pokes = noise_around(rng, FP_LEFT, struct.pack(">i", value) + rng.randbytes(4))
    pokes = abi.merge_pokes(pokes, abi.stack_args((4, FP_LEFT)))
    check(ENTRY_FP_LONG_TO_DOUBLE, lambda lib, buf: lib.g_fp_long_to_double(buf, FP_LEFT),
          pokes=pokes, note=f"fp_long_to_double({value})")


@pytest.mark.parametrize("value", (0.0, 1.0, -1.0, 0.5, 3.4e38, 1.2e-38, 3.14159, -0.0))
def test_fp_float_to_double(value):
    rng = random.Random(hash(value) & 0xffff)
    pokes = noise_around(rng, FP_LEFT, struct.pack(">f", value) + rng.randbytes(4))
    pokes = abi.merge_pokes(pokes, abi.stack_args((4, FP_LEFT)))
    check(ENTRY_FP_FLOAT_TO_DOUBLE, lambda lib, buf: lib.g_fp_float_to_double(buf, FP_LEFT),
          pokes=pokes, note=f"fp_float_to_double({value!r})")


@pytest.mark.parametrize("value", (0, 1, 0xffffff, 0x7fffffff, 0x80000000, 0xffffffff, 16794009))
def test_fp_acc_load_long(value):
    """The accumulator entry point: a longword in D0, widened in place at A_fp_acc."""
    rng = random.Random(value & 0xffff)
    pokes = {A_FP_ACC: rng.randbytes(8)}
    check(ENTRY_FP_ACC_LOAD_LONG, lambda lib, buf: lib.g_fp_acc_load_long(buf, value),
          pokes=pokes, regs={"d0": value}, note=f"fp_acc_load_long({value:#x})")


@pytest.mark.parametrize("value", FP_SAMPLES)
def test_fp_acc_to_long(value):
    rng = random.Random(hash(value) & 0xffff)
    pokes = {A_FP_ACC: abi.double(value)}
    info = check(ENTRY_FP_ACC_TO_LONG, lambda lib, buf: lib.g_fp_acc_to_long(buf),
                 pokes=pokes, note=f"fp_acc_to_long({value!r})")
    check_d0_long(info, f"fp_acc_to_long({value!r})")


def test_fp_pack_double_direct():
    """The shared tail, entered at its own first instruction with the operands in registers.

    It is a TAIL — it pops ten saved registers and unlinks a frame — so A6 has to name a frame whose
    saved link sends the `rts` back to the harness's sentinel; PACK_DOUBLE_FRAME is that.
    """
    rng = random.Random(0x9d0)
    for mantissa, exponent in ((0, 0), (0xff, 0x400), (0x80000000, 0x3ff), (0x80000100, 0x3ff),
                               (0x800002ff, 0x3ff), (0xffffffff, 0x7fe), (0x00000100, 0x010),
                               (0x40000000, 0x001), (0xfffffe00, 0x7ff)):
        pokes = noise_around(rng, FP_LEFT, rng.randbytes(8))
        check(ENTRY_FP_PACK_DOUBLE,
              lambda lib, buf, m=mantissa, e=exponent: lib.g_fp_pack_double(buf, FP_LEFT, m, e),
              pokes=pokes,
              regs={"d2": mantissa, "d3": exponent, "a0": FP_LEFT, "a6": PACK_DOUBLE_FRAME},
              note=f"fp_pack_double(mantissa={mantissa:#x}, exponent={exponent:#x})")


def test_fp_pack_float_direct():
    """The single-precision tail, entered at the `link a6,#$0` stub in front of its body.

    NOTHING IN THE PROGRAM CALLS IT — it is fp_op_table[6] and no call site asks for that opcode —
    so this battery is the only thing that ever runs it. Kept because the routine is real code in
    the shipped binary and a reconstruction that guessed at it would be unverified rather than
    absent.

    THE LAST TWO PAIRS DRIVE THE SHARED NORMALISE LOOP DEEP — 23 passes and 15 — because every
    other vector here takes it zero or one time, and the loop is where this tail's exponent
    arithmetic lives. The deep vectors used to exist only in `test_fp_pack_double_direct`, which
    covers the loop only while the two tails share one copy of it; the file's own note says they are
    transcribed separately so that each says what its own instructions say.
    """
    rng = random.Random(0x9f0)
    for mantissa, exponent in ((0, 0), (0xff, 0x40), (0x80000000, 0x7f), (0x80000200, 0x7f),
                               (0x800002ff, 0x7f), (0xffffffff, 0xfe), (0x40000000, 0x01),
                               (0x00000100, 0x10), (0x00010000, 0x40)):
        pokes = noise_around(rng, FP_LEFT, rng.randbytes(4))
        check(ENTRY_FP_PACK_FLOAT,
              lambda lib, buf, m=mantissa, e=exponent: lib.g_fp_pack_float(buf, FP_LEFT, m, e),
              pokes=pokes, regs={"d2": mantissa, "d3": exponent, "a0": FP_LEFT},
              note=f"fp_pack_float(mantissa={mantissa:#x}, exponent={exponent:#x})")


@pytest.mark.parametrize("opcode", (FP_OP_ADD_DOUBLE, FP_OP_MUL_DOUBLE, FP_OP_DIV_DOUBLE,
                                    FP_OP_CMP_DOUBLE, 0x0801))
def test_fp_dispatch_double_source(opcode):
    """The five table entries reachable with an eight-byte source, which is every one the game uses."""
    rng = random.Random(opcode)
    pokes = fp_operand_pokes(rng, abi.double(16794009.0), abi.double(11.0))
    pokes = abi.merge_pokes(pokes, {A_FP_SUB_SIGN_FLAG: rng.randbytes(2),
                                   A_FP_CCR: rng.randbytes(2)})
    pokes = abi.merge_pokes(pokes, abi.stack_args((2, opcode), (4, FP_LEFT), (4, FP_RIGHT)))
    check(ENTRY_FP_DISPATCH,
          lambda lib, buf: lib.g_fp_dispatch(buf, opcode, FP_LEFT, FP_RIGHT,
                                             FP_DISPATCH_FRAME_LOCAL, FP_CMP_STATUS_HIGH),
          pokes=pokes, note=f"fp_dispatch({opcode:#x})")


@pytest.mark.parametrize("opcode,source", (
    (FP_OP_ADD_SHORT, struct.pack(">h", -7)),
    (FP_OP_ADD_SHORT, struct.pack(">h", 1234)),
    (FP_OP_ADD_LONG, struct.pack(">i", -70000)),
    (FP_OP_ADD_LONG, struct.pack(">i", 16794009)),
    (FP_OP_ADD_FLOAT, struct.pack(">f", 2.5)),
    (FP_OP_ADD_FLOAT, struct.pack(">f", -1e20)),
))
def test_fp_dispatch_widens_its_source(opcode, source):
    """A short, a long or a single is widened into fp_dispatch's OWN STACK LOCAL first.

    That local lies in the band the differential drops as stack, so nothing compares it directly —
    what pins the widening is the destination the widened value is then added to.
    """
    rng = random.Random(opcode + len(source))
    pokes = fp_operand_pokes(rng, abi.double(1000.0), source + rng.randbytes(4))
    pokes = abi.merge_pokes(pokes, {A_FP_SUB_SIGN_FLAG: rng.randbytes(2)})
    pokes = abi.merge_pokes(pokes, abi.stack_args((2, opcode), (4, FP_LEFT), (4, FP_RIGHT)))
    check(ENTRY_FP_DISPATCH,
          lambda lib, buf: lib.g_fp_dispatch(buf, opcode, FP_LEFT, FP_RIGHT,
                                             FP_DISPATCH_FRAME_LOCAL, FP_CMP_STATUS_HIGH),
          pokes=pokes, note=f"fp_dispatch({opcode:#x}, {source.hex()})")


def test_fp_op_table_points_where_the_reconstruction_assumes(post_init_image):
    """src/clib.c's `switch` stands in for an indirect jump through A_fp_op_table.

    The table is written by `init_globals` and never again — which is why it is read off the
    POST-INIT image; the loaded .PRG holds seven zeroes there, and each entry points at the `jmp`
    island at the load base rather than at the routine — so this is what says the seven slots really
    do name add, sub, mul, div, cmp and the two packing tails, in that order.
    """
    expected = (ENTRY_FP_ADD, ENTRY_FP_SUB, ENTRY_FP_MUL, ENTRY_FP_DIV, ENTRY_FP_CMP,
                ENTRY_FP_PACK_DOUBLE, ENTRY_FP_PACK_FLOAT + 4)
    for index, routine in enumerate(expected):
        island = int.from_bytes(post_init_image[A_FP_OP_TABLE + index * 4:][:4], "big")
        assert post_init_image[island:island + 2] == b"\x4e\xf9", (
            f"fp_op_table[{index}] = {island:#x} is not a `jmp (xxx).l` island")
        target = int.from_bytes(post_init_image[island + 2:island + 6], "big")
        assert target == routine, f"fp_op_table[{index}] jumps to {target:#x}, not {routine:#x}"


@pytest.mark.parametrize("chunk", range(CHUNKS))
def test_fp_arithmetic_fuzz(chunk):
    """Random doubles through add, sub, multiply and divide, compared as BYTES.

    HALF THE OPERANDS ARE RAW 64-BIT PATTERNS rather than doubles Python would name. The package has
    no special cases for infinities, NaNs or denormals — a zero EXPONENT is the only value it tests
    for — so those patterns are ordinary inputs to it, and they are exactly the ones a reconstruction
    written from the arithmetic rather than from the instructions gets wrong.
    """
    rng = random.Random(0xf10a7 + chunk)
    entries = ((ENTRY_FP_ADD, "g_fp_add"), (ENTRY_FP_SUB, "g_fp_sub"),
               (ENTRY_FP_MUL, "g_fp_mul"), (ENTRY_FP_DIV, "g_fp_div"))
    for _ in range(24):
        left = (rng.randbytes(8) if rng.random() < 0.5
                else abi.double(rng.choice(FP_SAMPLES) * rng.uniform(-1e3, 1e3)))
        right = (rng.randbytes(8) if rng.random() < 0.5
                 else abi.double(rng.choice(FP_SAMPLES) * rng.uniform(-1e3, 1e3)))
        entry, glue_name = rng.choice(entries)
        fp_binary_case(entry, glue_name, left, right, f"fuzz {glue_name} {left.hex()} {right.hex()}")


@pytest.mark.parametrize("chunk", range(CHUNKS))
def test_fp_conversion_fuzz(chunk):
    """The three conversions over random bit patterns, likewise byte-compared."""
    rng = random.Random(0xc07f + chunk)
    for _ in range(24):
        for entry, glue_name, width in ((ENTRY_FP_DOUBLE_TO_LONG, "g_fp_double_to_long", 8),
                                        (ENTRY_FP_LONG_TO_DOUBLE, "g_fp_long_to_double", 8),
                                        (ENTRY_FP_FLOAT_TO_DOUBLE, "g_fp_float_to_double", 8)):
            payload = rng.randbytes(width)
            pokes = abi.merge_pokes(noise_around(rng, FP_LEFT, payload),
                                    abi.stack_args((4, FP_LEFT)))
            check(entry, lambda lib, buf, name=glue_name: getattr(lib, name)(buf, FP_LEFT),
                  pokes=pokes, note=f"fuzz {glue_name} {payload.hex()}")


# ================================================================================================
# The package in the shape the game actually uses it
# ================================================================================================

# `title_menu_loop` @ 0x115d6 computes its demo slideshow length as
# `Random() / 16794009 * 11 + 5` and the room it shows as `Random() / 16794009 * 34 + 1`, both
# through the accumulator and both truncated by fp_acc_to_long. The plate at 0x115d6 in
# ../names.txt states the ranges those give — 5..15 and 1..34 — and this is the composition that
# either holds them up or does not.
DEMO_LENGTH_CHAIN = ((FP_OP_DIV_DOUBLE, A_CONST_RANDOM_RANGE),
                     (FP_OP_MUL_DOUBLE, A_CONST_11),
                     (FP_OP_ADD_DOUBLE, A_CONST_5))
RANDOM_MAX = 0x00ffffff          # XBIOS Random is 24-bit; os.h's OS_RANDOM_MASK says the same


def demo_length_case(random_value):
    """One whole `Random() -> slideshow length` computation, oracle against candidate.

    The oracle runs it from a poked stub — five C calls in one run — because the chain's evidence is
    the accumulator it leaves and the longword it ends with, and no single call carries either.
    """
    calls = [{"routine": ENTRY_FP_ACC_LOAD_LONG, "args": [], "answers": [], "pop": 0}]
    calls += [{"routine": ENTRY_FP_DISPATCH,
               "args": [(2, opcode), (4, A_FP_ACC), (4, constant)],
               "answers": [], "pop": 0}                 # fp_dispatch pops its own ten bytes
              for opcode, constant in DEMO_LENGTH_CHAIN]
    calls += [{"routine": ENTRY_FP_ACC_TO_LONG, "args": [], "answers": [], "pop": 0}]

    def glue(lib, buf):
        lib.g_fp_acc_load_long(buf, random_value)
        for opcode, constant in DEMO_LENGTH_CHAIN:
            # The widen scratch is unused for an 0x08xx opcode — the source is already a double.
            lib.g_fp_dispatch(buf, opcode, A_FP_ACC, constant,
                              FP_DISPATCH_FRAME_LOCAL, FP_CMP_STATUS_HIGH)
        return lib.g_fp_acc_to_long(buf)

    rng = random.Random(random_value)
    pokes = abi.merge_pokes(abi.c_call_pokes(calls), {A_FP_ACC: rng.randbytes(8)})
    info = check(abi.STUB, glue, pokes=pokes, regs={"d0": random_value},
                 note=f"demo length from Random()={random_value:#x}")
    check_d0_long(info, f"demo length from Random()={random_value:#x}")
    return info["ret"]


@pytest.mark.parametrize("random_value", (0, 1, RANDOM_MAX, RANDOM_MAX // 2, 0x00abcdef, 16794008))
def test_demo_slideshow_length_chain(random_value):
    """The range the plate at 0x115d6 claims: 5..15, with 15 reachable only at the very top."""
    length = demo_length_case(random_value)
    assert 5 <= length <= 15, f"Random()={random_value:#x} gave {length}, outside 5..15"


def test_demo_slideshow_length_never_reaches_sixteen():
    """0xffffff / 16794009 is 0.9990, strictly below 1, and fp_acc_to_long TRUNCATES.

    So the top of the range is 5 + 10 = 15 and never 16 — which is the half of the plate's claim a
    single sample cannot make, and the reason the boundary gets its own case.
    """
    assert demo_length_case(RANDOM_MAX) == 15
    assert demo_length_case(0) == 5


def test_the_data_constants_the_demo_chain_divides_by(post_init_image):
    """The three DATA doubles DEMO_LENGTH_CHAIN names, against the bytes the binary ships.

    They are `../names.txt`'s const_random_range / const_11 / const_5 and belong to the front end
    rather than to this subsystem, so they are pinned here by VALUE rather than mirrored from a
    header this battery does not own. Note that two of them are not the round numbers they look
    like: the linker's own conversion left 16794009.000000015 and 11.000000000000002.
    """
    for address, value in ((A_CONST_RANDOM_RANGE, 16794009.000000015),
                           (A_CONST_11, 11.000000000000002),
                           (A_CONST_5, 5.0)):
        assert struct.unpack(">d", post_init_image[address:address + 8])[0] == value



# ================================================================================================
# The console reader
# ================================================================================================

CONIN_LINE_BYTES = 0x40         # how much of c_conin's line buffer a case stages and compares


def conin_poke(rng, read_pos=0, length=0, line=b""):
    """`A_c_conin_read_pos`, `A_c_conin_length` and the line buffer, as one noise-filled span.

    They are consecutive, and the buffer is bss the post-init image holds as zeroes — so a routine
    that stored one byte past where it should have would write a zero over a zero without the noise.
    """
    span = bytearray(rng.randbytes(4 + CONIN_LINE_BYTES))
    span[0:2] = abi.word(read_pos)
    span[2:4] = abi.word(length)
    span[4:4 + len(line)] = line
    return {A_C_CONIN_READ_POS: bytes(span)}


@pytest.mark.parametrize("keys,note", (
    ("a\r", "one character then RETURN"),
    ("\r", "an empty line"),
    ("ab\r", "two characters"),
    ("a\x08b\r", "a character rubbed out and replaced"),
    ("\x08\r", "BACKSPACE with nothing to rub out"),
    ("a\x1a", "the end-of-file character, which is stored and echoed"),
    ("\x1a", "...and one on its own, which reads back as -1"),
    ("\n\r", "a LINE FEED typed as an ordinary character"),
))
def test_c_conin_gathers_a_line(keys, note):
    """Gather a whole line through GEMDOS Crawcin, echoing through Cconout, then hand back one byte.

    The echoes are the surface: every one is an entry in the console-byte ledger, and each site
    files its own RET_* in the trampoline's return slot.
    """
    rng = random.Random(len(keys) * 41 + len(note))
    pokes = abi.merge_pokes(conin_poke(rng), trap_slot_noise(rng),
                            harness.console_keys(list(keys)),
                            abi.stack_args((2, FD_DEVICE_CON)))
    info = check(ENTRY_C_CONIN,
                 lambda lib, buf: lib.g_c_conin(buf, FD_DEVICE_CON, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_conin: {note}")
    check_d0_low_word(info, f"c_conin: {note}")


@pytest.mark.parametrize("read_pos,length,line", (
    (0, 3, b"abc"),
    (2, 3, b"abc"),
    (0, 2, b"a\x1a"),        # the end-of-file character in the buffer answers -1
    (1, 2, b"a\x1a"),
))
def test_c_conin_hands_back_a_line_already_gathered(read_pos, length, line):
    """With characters still unread it takes the next one and reads NOTHING from the console.

    No key is staged, so a reconstruction that gathered anyway would meet the model's refusal
    rather than fabricate a keystroke.
    """
    rng = random.Random(read_pos * 7 + length + len(line))
    pokes = abi.merge_pokes(conin_poke(rng, read_pos, length, line), trap_slot_noise(rng),
                            abi.stack_args((2, FD_DEVICE_CON)))
    info = check(ENTRY_C_CONIN,
                 lambda lib, buf: lib.g_c_conin(buf, FD_DEVICE_CON, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(),
                 note=f"c_conin buffered {line!r} at {read_pos}")
    check_d0_low_word(info, f"c_conin buffered {line!r} at {read_pos}")


def test_c_conin_ctrl_c_ends_the_program():
    """^C runs `c_exit`, which closes every open stream and terminates through GEMDOS Pterm.

    THE ORIGINAL FALLS THROUGH from this branch into the end-of-file test, and that fall-through is
    code the real machine never reaches — Pterm does not return — so the reconstruction returns
    instead. The model says the same thing from the other side: `os_pterm` LATCHES the event ledger,
    and anything appended after it is refused. This case is what runs the arm at all: nothing else
    in the suite types a ^C.
    """
    rng = random.Random(0x1c03)
    pokes = abi.merge_pokes(conin_poke(rng), iob_poke(rng), trap_slot_noise(rng),
                            fd_table_poke(rng, ()),
                            harness.console_keys([chr(CONIN_INTERRUPT)]),
                            abi.stack_args((2, FD_DEVICE_CON)))
    info = check(ENTRY_C_CONIN,
                 lambda lib, buf: lib.g_c_conin(buf, FD_DEVICE_CON, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note="c_conin: ^C")
    assert info["regs"]["events"][-1] == (OS_EVENT_PTERM, CONIN_EXIT_CODE), (
        f"the run did not end in Pterm({CONIN_EXIT_CODE}) — {info['regs']['events']}")


@pytest.mark.parametrize("handle", (FD_DEVICE_PRT, 6, 0))
def test_c_conin_refuses_every_handle_but_the_console_and_the_serial_port(handle):
    rng = random.Random(handle + 0xc1)
    pokes = abi.merge_pokes(conin_poke(rng), trap_slot_noise(rng), abi.stack_args((2, handle)))
    info = check(ENTRY_C_CONIN,
                 lambda lib, buf: lib.g_c_conin(buf, handle, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_conin({handle:#x})")
    check_d0_low_word(info, f"c_conin({handle:#x})")
    assert info["ret"] & 0xffff == 0xffff


# ================================================================================================
# The printf engine
#
# WHAT THE ENGINE ACTUALLY IMPLEMENTS, read off c_doprnt's own dispatch chain and fuzzed only over
# that: `%[-][0][width][.precision][l]` and then one of d u o x c s e f g. There is no `%%` (a `%`
# reaches the "unknown conversion" arm and is emitted as itself, which is the same output by a
# different route), no `+`/space flag, no `*` width, no `h`, and no `p`/`n`/`i`. `%g` is `%e`:
# c_fmt_float tests for 'f' and takes the exponent form for everything else.
#
# THE GAME ITSELF USES NONE OF THEM. Its one c_printf call (`main` @ 0x100dc) passes the
# "Please reboot in LOW REZ" message, which has no conversions at all — so every case below except
# that one is synthetic, and ../STATUS.md says so rather than implying play-tested coverage.
# ================================================================================================

DOPRNT_OUT = SCRATCH                 # where a case has the engine write
DOPRNT_FORMAT = SCRATCH + 0x300      # ...the format string it walks
DOPRNT_ARGS = SCRATCH + 0x400        # ...the argument list it reads
DOPRNT_TEXT = SCRATCH + 0x500        # ...and a string for %s to copy
DOPRNT_OUT_BYTES = 0x200

# The one format the program itself passes to c_printf, at 0(a4) — see `main` @ 0x100dc.
GAME_PRINTF_MESSAGE = b"\n\n Please reboot in LOW REZ... \n"

# D7 as c_doprnt's caller left it: what a format ending in a BARE `%` dispatches on, and what
# c_fmt_integer would use as a base. It is an INPUT here, given identically to both sides.
INHERITED_CONVERSION = 0x0064        # 'd', chosen because it is a conversion the engine knows


def printf_arguments(*values):
    """An argument list as the Alcyon compiler would have pushed it, after the format pointer.

    Each value is `(width, number)` with the width in bytes — 2 for a `short`, 4 for a `long` or a
    pointer — or `("double", x)` for the eight bytes a float conversion consumes. The WIDTH is what
    c_doprnt steps the list by, so it is stated rather than guessed from the value.
    """
    blob = b""
    for width, value in values:
        if width == "double":
            blob += abi.double(value)
        elif width == 2:
            blob += abi.word(value)
        else:
            blob += abi.long(value)
    return blob


def doprnt_pokes(rng, fmt, values, text=b"", out_bytes=DOPRNT_OUT_BYTES):
    """The world a c_doprnt / c_sprintf case stages: output, format, arguments and a %s string."""
    return abi.merge_pokes(
        noise_around(rng, DOPRNT_OUT, bytes(out_bytes)),
        noise_around(rng, DOPRNT_FORMAT, fmt + b"\0"),
        noise_around(rng, DOPRNT_ARGS, abi.long(DOPRNT_FORMAT) + printf_arguments(*values)),
        noise_around(rng, DOPRNT_TEXT, text + b"\0"))


# (format, argument list) — grouped by what each row is there to reach.
DOPRNT_CASES = (
    (b"", ()),
    (b"plain text, no conversions", ()),
    (GAME_PRINTF_MESSAGE, ()),
    (b"%d", ((2, 0),)),
    (b"%d", ((2, 1),)),
    (b"%d", ((2, -1),)),
    (b"%d", ((2, 32767),)),
    (b"%d", ((2, -32768),)),
    (b"%ld", ((4, 0x7fffffff),)),
    (b"%ld", ((4, -0x80000000),)),
    (b"%u", ((2, -1),)),                 # the sign extension is masked off again
    (b"%lu", ((4, 0xffffffff),)),        # ...and kept, for a long
    (b"%x", ((2, -1),)),
    (b"%lx", ((4, 0xdeadbeef),)),
    (b"%o", ((2, 8),)),
    (b"%lo", ((4, 0xffffffff),)),
    (b"%c", ((2, ord("Z")),)),
    (b"%c%c%c", ((2, ord("a")), (2, ord("b")), (2, ord("c")))),
    (b"%s", ((4, DOPRNT_TEXT),)),
    (b"%.3s", ((4, DOPRNT_TEXT),)),
    (b"%.0s", ((4, DOPRNT_TEXT),)),
    (b"%12s|", ((4, DOPRNT_TEXT),)),
    (b"%-12s|", ((4, DOPRNT_TEXT),)),
    (b"%6d|", ((2, 42),)),
    (b"%-6d|", ((2, 42),)),
    (b"%06d|", ((2, 42),)),
    (b"%06d|", ((2, -42),)),             # the sign is moved with the digits, not left behind
    (b"%2d|", ((2, 12345),)),            # a field too narrow for what it holds
    (b"score %d of %d", ((2, 7), (2, 9))),
    (b"%%", ()),                         # not an escape: the second % is an unknown conversion
    (b"%z", ()),                         # ...and so is anything else the chain does not name
    (b"literal % at the end", ()),
    (b"%f", (("double", 1.0),)),
    (b"%f", (("double", 0.0),)),
    (b"%f", (("double", -0.0),)),
    (b"%f", (("double", -1.5),)),
    (b"%.2f", (("double", 3.14159),)),
    (b"%.0f", (("double", 2.5),)),
    (b"%.7f", (("double", 0.001),)),
    (b"%f", (("double", 12345.678),)),
    (b"%e", (("double", 1.0),)),
    (b"%e", (("double", -12345.678),)),
    (b"%.3e", (("double", 0.000123),)),
    (b"%g", (("double", 1024.0),)),      # %g is %e: c_fmt_float only tests for 'f'
    (b"%10.2f|", (("double", -1.25),)),
    (b"%-10.2f|", (("double", -1.25),)),
)


@pytest.mark.parametrize("fmt,values", DOPRNT_CASES)
def test_c_doprnt(fmt, values):
    rng = random.Random(len(fmt) * 131 + len(values))
    pokes = abi.merge_pokes(doprnt_pokes(rng, fmt, values, text=b"a string"),
                            abi.stack_args((4, DOPRNT_OUT), (4, DOPRNT_ARGS)))
    info = check(ENTRY_C_DOPRNT,
                 lambda lib, buf: lib.g_c_doprnt(buf, DOPRNT_OUT, DOPRNT_ARGS,
                                                 INHERITED_CONVERSION, FP_CMP_STATUS_HIGH),
                 pokes=pokes, regs={"d7": INHERITED_CONVERSION, **caller_registers()},
                 note=f"c_doprnt({fmt!r}, {values})")
    check_d0_long(info, f"c_doprnt({fmt!r}, {values})")


@pytest.mark.parametrize("inherited", (0x64, 0x73, 0x66, 0x00))
def test_c_doprnt_dispatches_a_trailing_percent_on_the_caller_s_own_register(inherited):
    """A format ending in a bare `%` never loads a conversion character, so D7 decides what happens.

    The four values are 'd', 's', 'f' and 0 — an integer, a pointer, a double and an unknown — and
    each consumes a different number of argument bytes, which is what makes this more than a copy.
    It is a real branch of the routine, and the only way to reach it is to declare the register.
    """
    rng = random.Random(inherited + 0x7c)
    values = ((4, DOPRNT_TEXT), ("double", 1.0))
    pokes = abi.merge_pokes(doprnt_pokes(rng, b"end%", values, text=b"tail"),
                            abi.stack_args((4, DOPRNT_OUT), (4, DOPRNT_ARGS)))
    info = check(ENTRY_C_DOPRNT,
                 lambda lib, buf: lib.g_c_doprnt(buf, DOPRNT_OUT, DOPRNT_ARGS, inherited,
                                                 FP_CMP_STATUS_HIGH),
                 pokes=pokes, regs={"d7": inherited, **caller_registers()},
                 note=f"c_doprnt trailing %% with D7={inherited:#x}")
    check_d0_long(info, f"c_doprnt trailing %% with D7={inherited:#x}")


DOPRNT_FUZZ_CHUNKS = 8
DOPRNT_FUZZ_PER_CHUNK = 24
# The doubles the fuzz draws from, and NOT `FP_SAMPLES`: c_fcvt scales a value by ten until its
# binary exponent lands in [-3, 0], so 1e300 is three hundred `fp_div` passes — of the order of
# 100,000 instructions for ONE conversion, and a three-conversion format then runs past any sane
# cap. The extreme exponents get a case of their own below, with the cap raised and the cost said.
PRINTF_FP_SAMPLES = (0.0, -0.0, 1.0, -1.0, 0.5, 2.0, 11.0, 5.0, 20.0, 2.977e-06,
                     1.0000000596046448, 3.141592653589793, -2.718281828459045, 65535.0,
                     1.0 / 3.0, 123456789.0)
# Only what the engine implements: a format the fuzz builds out of these cannot ask for a conversion
# c_doprnt does not have (and `%z` above is the case that says what happens when one does).
FUZZ_CONVERSIONS = "duoxcsefg"


def _fuzz_format(rng):
    """One random format the engine really supports, and the argument list it consumes."""
    parts, values = [], []
    for _ in range(rng.randrange(1, 4)):
        parts.append(rng.choice(("", "-", "x", "..", " ")))
        flags = ("-" if rng.random() < 0.3 else "") + ("0" if rng.random() < 0.3 else "")
        width = str(rng.randrange(0, 14)) if rng.random() < 0.5 else ""
        precision = ("." + str(rng.randrange(0, 8))) if rng.random() < 0.4 else ""
        conversion = rng.choice(FUZZ_CONVERSIONS)
        is_long = conversion in "duox" and rng.random() < 0.4
        parts.append("%" + flags + width + precision + ("l" if is_long else "") + conversion)
        if conversion in "duox":
            values.append((4, rng.randrange(0, 1 << 32)) if is_long
                          else (2, rng.randrange(-0x8000, 0x8000)))
        elif conversion == "c":
            values.append((2, rng.randrange(0x20, 0x7f)))
        elif conversion == "s":
            values.append((4, DOPRNT_TEXT))
        else:
            values.append(("double", rng.choice(PRINTF_FP_SAMPLES)))
    return "".join(parts).encode("ascii"), tuple(values)


@pytest.mark.parametrize("chunk", range(DOPRNT_FUZZ_CHUNKS))
def test_c_doprnt_fuzz(chunk):
    """CHUNK-SEEDED (abi.shard's docstring tells the two shapes apart): each chunk draws its own."""
    rng = random.Random(0xd09 + chunk)
    for _ in range(DOPRNT_FUZZ_PER_CHUNK):
        fmt, values = _fuzz_format(rng)
        pokes = abi.merge_pokes(doprnt_pokes(rng, fmt, values, text=b"fuzzed string"),
                                abi.stack_args((4, DOPRNT_OUT), (4, DOPRNT_ARGS)))
        info = check(ENTRY_C_DOPRNT,
                     lambda lib, buf: lib.g_c_doprnt(buf, DOPRNT_OUT, DOPRNT_ARGS,
                                                     INHERITED_CONVERSION, FP_CMP_STATUS_HIGH),
                     pokes=pokes, regs={"d7": INHERITED_CONVERSION, **caller_registers()},
                     note=f"c_doprnt fuzz {fmt!r} {values}")
        check_d0_long(info, f"c_doprnt fuzz {fmt!r}")


@pytest.mark.parametrize("value", (1e300, 1e-300))
@pytest.mark.parametrize("conversion", (b"f", b"e"))
def test_c_doprnt_scales_an_extreme_exponent(conversion, value):
    """c_fcvt's scaling loop, run to its limit: about 300 `fp_div` or `fp_mul` passes per value.

    THE CAP IS RAISED FOR THESE AND SAID OUT LOUD rather than raised for the whole battery: at
    roughly 100,000 instructions a conversion they are the most expensive thing this file runs, and
    the fuzz above deliberately draws from a narrower set of doubles because of it.
    """
    # NOT `hash((conversion, value))`: `conversion` is `bytes`, whose hash is salted with
    # PYTHONHASHSEED — the guard noise would then differ every run and a failure could not be
    # reproduced from the case's own seed.
    rng = random.Random(conversion[0] * 3 + int(value != 0))
    fmt = b"%" + conversion
    values = (("double", value),)
    pokes = abi.merge_pokes(doprnt_pokes(rng, fmt, values),
                            abi.stack_args((4, DOPRNT_OUT), (4, DOPRNT_ARGS)))
    info = check(ENTRY_C_DOPRNT,
                 lambda lib, buf: lib.g_c_doprnt(buf, DOPRNT_OUT, DOPRNT_ARGS,
                                                 INHERITED_CONVERSION, FP_CMP_STATUS_HIGH),
                 pokes=pokes, regs={"d7": INHERITED_CONVERSION, **caller_registers()},
                 note=f"c_doprnt({fmt!r}, {value!r})", max_insns=1_500_000)
    check_d0_long(info, f"c_doprnt({fmt!r}, {value!r})")


# ---- the pieces c_doprnt is built from -------------------------------------------------------

GETNUM_CURSOR = SCRATCH + 0x600      # the `char **` c_fmt_getnum and c_fmt_integer advance


@pytest.mark.parametrize("text", (b"", b"0", b"7x", b"123", b"99999", b"65536", b"007", b"-3",
                                  b"\xff9", b" 5"))
def test_c_fmt_getnum(text):
    """The decimal number at the cursor, and the cursor left past it. Non-digits stop the scan —
    including a byte with bit 7 set, which the SIGN-extended compare puts below '0'."""
    rng = random.Random(len(text) * 5 + (text[0] if text else 0))
    pokes = abi.merge_pokes(noise_around(rng, SCRATCH, text + b"\0"),
                            {GETNUM_CURSOR: abi.long(SCRATCH)},
                            abi.stack_args((4, GETNUM_CURSOR)))
    info = check(ENTRY_C_FMT_GETNUM,
                 lambda lib, buf: lib.g_c_fmt_getnum(buf, GETNUM_CURSOR),
                 pokes=pokes, regs=caller_registers(), note=f"c_fmt_getnum({text!r})")
    check_d0_low_word(info, f"c_fmt_getnum({text!r})")


@pytest.mark.parametrize("conversion,is_long,value", (
    (ord("d"), 0, 0),
    (ord("d"), 0, 12345),
    (ord("d"), 0, -12345),
    (ord("d"), 1, 0x7fffffff),
    (ord("d"), 1, -0x7fffffff),
    (ord("u"), 0, -1),
    (ord("u"), 1, 0xfffffffe),
    (ord("o"), 0, 0o777),
    (ord("o"), 1, 0xffffffff),
    (ord("x"), 0, -1),
    (ord("x"), 1, 0xabcdef01),
    (ord("x"), 1, 0),
))
def test_c_fmt_integer(conversion, is_long, value):
    """One integer in the base its conversion names, digits emitted in reverse off a 20-word stack.

    `base_when_conversion_unknown` is the caller's D7, which from c_doprnt IS the conversion
    character; every case here passes the same value both ways, as the original does.
    """
    rng = random.Random(conversion * 7 + is_long * 3 + (value & 0xff))
    pokes = abi.merge_pokes(noise_around(rng, SCRATCH, bytes(0x40)),
                            {GETNUM_CURSOR: abi.long(SCRATCH)},
                            abi.stack_args((2, conversion), (2, is_long), (4, GETNUM_CURSOR),
                                           (4, value)))
    check(ENTRY_C_FMT_INTEGER,
          lambda lib, buf: lib.g_c_fmt_integer(buf, conversion, is_long, GETNUM_CURSOR,
                                               value & 0xffffffff, conversion),
          pokes=pokes, regs={"d7": conversion, **caller_registers()},
          note=f"c_fmt_integer({chr(conversion)}, long={is_long}, {value:#x})")


def test_c_fmt_integer_refuses_a_base_that_would_overrun_its_digit_array():
    """A CANDIDATE-ONLY case, for the same reason as the float precision below.

    The digit array is the original's own 20 words, and base 2 of a longword needs 32 — so the
    ORIGINAL overruns its `-40(a6)` frame here and carries on, which is not something a differential
    can be asked (and a base of 1 never terminates at all). Only the "unknown conversion" arm can
    produce such a base, and nothing in the program reaches it. The reconstruction refuses instead
    of writing outside `digits`, and the refusal TALLY is what this asserts.
    """
    image = (ctypes.c_uint8 * len(harness.BASE_IMAGE)).from_buffer_copy(harness.BASE_IMAGE)
    cursor = struct.pack(">I", SCRATCH)
    image[GETNUM_CURSOR:GETNUM_CURSOR + 4] = (ctypes.c_uint8 * 4)(*cursor)
    harness._lib.g_os_refusal_reset()
    _lib.g_c_fmt_integer(image, ord("q"), 0, GETNUM_CURSOR, 0x12345678, 2)
    assert harness._lib.g_os_refusal_count() != 0
    # ...and it stopped at the bound rather than past it: exactly FMT_DIGIT_SLOTS digits were taken
    # off the value, and none of them reached the output.
    assert struct.unpack(">I", bytes(image[GETNUM_CURSOR:GETNUM_CURSOR + 4]))[0] == SCRATCH


@pytest.mark.parametrize("base", (10, 8, 16, 2, 36))
def test_c_fmt_integer_takes_its_base_from_the_caller_when_the_conversion_is_unknown(base):
    """The `else` of the four-way chain leaves D7 alone, so the caller's register IS the base.

    c_doprnt never reaches it — its dispatch only sends d/u/o/x here — so this is the only thing
    that exercises the arm, and it is a register declaration rather than an argument the ABI has.
    Base 2 and base 36 are not bases this library can name; they are what the arm actually does.
    """
    rng = random.Random(base * 11)
    unknown = ord("q")
    value = 1234
    pokes = abi.merge_pokes(noise_around(rng, SCRATCH, bytes(0x40)),
                            {GETNUM_CURSOR: abi.long(SCRATCH)},
                            abi.stack_args((2, unknown), (2, 0), (4, GETNUM_CURSOR), (4, value)))
    check(ENTRY_C_FMT_INTEGER,
          lambda lib, buf: lib.g_c_fmt_integer(buf, unknown, 0, GETNUM_CURSOR, value, base),
          pokes=pokes, regs={"d7": base, **caller_registers()},
          note=f"c_fmt_integer with an unknown conversion and D7={base}")


FCVT_VALUE = SCRATCH + 0x700         # the eight bytes c_fcvt reads
FCVT_DIGITS = SCRATCH + 0x740        # ...the digits it writes
FCVT_DECIMAL_POINT = SCRATCH + 0x7c0  # ...and the power of ten they scale by


@pytest.mark.parametrize("value", (
    0.0, -0.0, 1.0, -1.0, 0.5, 2.0, 9.9999, 10.0, 0.001, 1234.5678, 1e6, 1e-6,
    3.141592653589793, 65535.0, 0.0625, 123456789.0,
))
@pytest.mark.parametrize("ndigits", (1, 7, 17))
def test_c_fcvt(value, ndigits):
    """A double as decimal digits plus an exponent — scaled by `A_fcvt_ten`, rounded on the digits.

    Compared as BYTES, like the rest of the floating-point package: it keeps 32 mantissa bits where
    an IEEE double has 53, so "the same number to Python" is a different question from "the same
    digits" and only the second is asked.
    """
    rng = random.Random(hash((value, ndigits)) & 0xffff)
    pokes = abi.merge_pokes(noise_around(rng, FCVT_VALUE, abi.double(value)),
                            noise_around(rng, FCVT_DIGITS, bytes(0x40)),
                            noise_around(rng, FCVT_DECIMAL_POINT, bytes(2)),
                            abi.stack_args((4, FCVT_VALUE), (4, FCVT_DIGITS),
                                           (4, FCVT_DECIMAL_POINT), (2, ndigits)))
    raw = struct.unpack(">II", abi.double(value))
    check(ENTRY_C_FCVT,
          lambda lib, buf: lib.g_c_fcvt(buf, raw[0], raw[1], FCVT_DIGITS, FCVT_DECIMAL_POINT,
                                        ndigits),
          pokes=pokes, regs=caller_registers(), note=f"c_fcvt({value!r}, {ndigits})")


def test_c_fcvt_refuses_a_negative_digit_count():
    """A CANDIDATE-ONLY case, and the third of this file's three out-of-bounds guards.

    The original's `dbf` runs 65536 times on a negative counter and its round then steps BELOW the
    caller's buffer — so there is nothing comparable to diff, only a write the reconstruction must
    not make. `c_fmt_float` refuses a precision that could produce one, so this is the only thing
    that exercises c_fcvt's own guard.
    """
    image = (ctypes.c_uint8 * len(harness.BASE_IMAGE)).from_buffer_copy(harness.BASE_IMAGE)
    raw = struct.unpack(">II", abi.double(1.5))
    harness._lib.g_os_refusal_reset()
    _lib.g_c_fcvt(image, raw[0], raw[1], FCVT_DIGITS, FCVT_DECIMAL_POINT, 0xffff)  # -1 as a word
    assert harness._lib.g_os_refusal_count() != 0
    assert bytes(image[FCVT_DIGITS:FCVT_DIGITS + 4]) == bytes(harness.BASE_IMAGE[
        FCVT_DIGITS:FCVT_DIGITS + 4]), "it wrote digits for a count it refused"


@pytest.mark.parametrize("conversion", (ord("f"), ord("e"), ord("g")))
@pytest.mark.parametrize("precision,value", (
    (FMT_NO_PRECISION, 1.0),        # "no precision given" — a real 256, read as six digits
    (0, 1.5),
    (2, 3.14159),
    (6, 0.0),
    (6, -0.0),
    (4, -2.5),
    (3, 0.000125),
    (7, 98765.4321),
))
def test_c_fmt_float(conversion, precision, value):
    """One double as %f or %e, through c_fcvt twice for %f and through c_sprintf for %e's exponent."""
    rng = random.Random(hash((conversion, precision, value)) & 0xffff)
    raw = struct.unpack(">II", abi.double(value))
    pokes = abi.merge_pokes(noise_around(rng, SCRATCH, bytes(0x80)),
                            {GETNUM_CURSOR: abi.long(SCRATCH)},
                            abi.stack_args((2, conversion), (2, precision), (4, GETNUM_CURSOR),
                                           (4, raw[0]), (4, raw[1])))
    check(ENTRY_C_FMT_FLOAT,
          lambda lib, buf: lib.g_c_fmt_float(buf, conversion, precision, GETNUM_CURSOR,
                                             raw[0], raw[1], INHERITED_CONVERSION,
                                             FP_CMP_STATUS_HIGH),
          pokes=pokes, regs={"d7": INHERITED_CONVERSION, **caller_registers()},
          note=f"c_fmt_float({chr(conversion)}, {precision}, {value!r})")


def test_the_scratch_the_reconstruction_uses_is_inside_the_dropped_stack_band():
    """`CLIB_SCRATCH_BASE` is not a program address, and this is what says where it may be.

    `c_fcvt`'s working double and `c_vfprintf`'s format buffer are frame locals in the original;
    the reconstruction has no frame in the image, so it names three spans instead. They must lie
    inside the band the differential DROPS — [STACK_GUARD_LO, IMAGE_SIZE) — or the two sides would
    be compared over memory the original never had; they must stay clear of the arguments a case
    pokes above STACK_TOP; and they must be at or above STACK_TOP - STACK_SCRATCH, which is where
    the kit stops reading a write as a call frame's own (`test_blit.py` pins its slice locals the
    same way). The derivation is pinned here rather than in MIRRORS because test_constants.py's
    scraper reads literals, not arithmetic (its `defines` docstring says so).
    """
    total = C_FCVT_DOUBLE_BYTES + C_EXPONENT_ARGS_BYTES + C_VFPRINTF_BUFFER_BYTES
    assert CLIB_SCRATCH_BASE == emu.STACK_TOP - emu.STACK_SCRATCH
    assert emu.STACK_GUARD_LO <= CLIB_SCRATCH_BASE
    # ...and the half a pin that only asserted the DROPPED band would miss: below
    # STACK_TOP - STACK_SCRATCH the kit reads a write as program output rather than as a frame's
    # own, and `harness._vet_...`'s stray-write check would call this scratch that.
    assert CLIB_SCRATCH_BASE >= emu.STACK_TOP - emu.STACK_SCRATCH
    assert CLIB_SCRATCH_BASE + total <= emu.STACK_TOP


def test_the_constants_the_float_formatter_reads(post_init_image):
    """`A_fcvt_ten`, `A_fcvt_max_digits` and the two DATA constants c_fmt_float names.

    The ten is ONE ULP HIGH — 0x4024000000000001, not 0x4024000000000000 — which is a property of
    the value init_globals writes and not a transcription slip, so it is asserted rather than
    described.
    """
    assert bytes(post_init_image[A_FCVT_TEN:A_FCVT_TEN + 8]) == bytes.fromhex("4024000000000001")
    assert struct.unpack(">h", bytes(post_init_image[A_FCVT_MAX_DIGITS:A_FCVT_MAX_DIGITS + 2]))[0] == 7
    assert bytes(post_init_image[A_FMT_FLOAT_ZERO:A_FMT_FLOAT_ZERO + 8]) == bytes(8)
    assert bytes(post_init_image[A_FMT_FLOAT_EXPONENT_FORMAT:
                                 A_FMT_FLOAT_EXPONENT_FORMAT + 3]) == b"%d\0"


# ---- the three entry points on top of c_doprnt -----------------------------------------------

def test_c_sprintf():
    """c_doprnt onto the caller's buffer, with the argument list starting at c_sprintf's SECOND
    argument — so the format string and the values after it are one list."""
    rng = random.Random(0x5f)
    fmt = b"[%s=%d]"
    pokes = abi.merge_pokes(noise_around(rng, DOPRNT_OUT, bytes(0x80)),
                            noise_around(rng, DOPRNT_FORMAT, fmt + b"\0"),
                            noise_around(rng, DOPRNT_TEXT, b"key\0"),
                            abi.stack_args((4, DOPRNT_OUT), (4, DOPRNT_FORMAT),
                                           (4, DOPRNT_TEXT), (2, 42)))
    args = abi.FIRST_ARG + 4          # c_sprintf's `pea 12(a6)`: its own second argument slot
    info = check(ENTRY_C_SPRINTF,
                 lambda lib, buf: lib.g_c_sprintf(buf, DOPRNT_OUT, args, INHERITED_CONVERSION,
                                                  FP_CMP_STATUS_HIGH),
                 pokes=pokes, regs={"d7": INHERITED_CONVERSION, **caller_registers()},
                 note="c_sprintf")
    check_d0_long(info, "c_sprintf")


@pytest.mark.parametrize("text,count", ((b"", 8), (b"hi", 8), (b"hi\n", 8), (b"overflowing", 3)))
def test_c_fputs(text, count):
    """Every byte through c_putc — so a full buffer flushes mid-string, through c_write."""
    rng = random.Random(len(text) * 3 + count)
    record = file_record(ptr=FILE_BUFFER, cnt=count, base=FILE_BUFFER,
                         flags=FILE_WRITE | FILE_LINEBUF, fd=harness.OS_FS_FIRST_HANDLE,
                         bufsiz=8)
    pokes, _ = buffered_case(rng, record, files=[(SCR_NAME, b"", 0x100)], open_slots=(0,),
                             buffer=bytes(8),
                             fd_modes=((harness.OS_FS_FIRST_HANDLE, FD_MODE_BINARY),))
    pokes = abi.merge_pokes(pokes, noise_around(rng, SCRATCH, text + b"\0"),
                            abi.stack_args((4, SCRATCH), (4, A_FILE)))
    check(ENTRY_C_FPUTS,
          lambda lib, buf: lib.g_c_fputs(buf, SCRATCH, A_FILE, CALLER_A1, CALLER_A2),
          pokes=pokes, regs=caller_registers(), note=f"c_fputs({text!r}, cnt={count})")


@pytest.mark.parametrize("append", (0, FILE_APPEND))
def test_c_fputs_across_several_flushes(append):
    """A string long enough to flush the stream more than once — which is what makes A1 visible.

    `c_write` asks `c_getfdmode`, and that leaves A1 one entry past the fd-mode table
    (= `A_c_errno`) — so from the FIRST flush onwards every later trap in the same c_fputs files
    that instead of the caller's A1. The append arm is the one that shows it: `c_fflush` seeks to
    the end BEFORE writing, so the second flush's Fseek is a trap whose save slot differs. A
    reconstruction that handed each `c_putc` the caller's register block unchanged is red here.
    """
    rng = random.Random(0xf0 + append)
    text = b"0123456789A"
    record = file_record(ptr=FILE_BUFFER, cnt=4, base=FILE_BUFFER,
                         flags=FILE_WRITE | FILE_DIRTY | append,
                         fd=harness.OS_FS_FIRST_HANDLE, bufsiz=4)
    pokes, _ = buffered_case(rng, record, files=[(SCR_NAME, b"", 0x200)], open_slots=(0,),
                             buffer=bytes(4), cursors=((0, 0),),
                             fd_modes=((harness.OS_FS_FIRST_HANDLE, FD_MODE_BINARY),))
    pokes = abi.merge_pokes(pokes, noise_around(rng, SCRATCH, text + b"\0"),
                            abi.stack_args((4, SCRATCH), (4, A_FILE)))
    check(ENTRY_C_FPUTS,
          lambda lib, buf: lib.g_c_fputs(buf, SCRATCH, A_FILE, CALLER_A1, CALLER_A2),
          pokes=pokes, regs=caller_registers(),
          note=f"c_fputs({text!r}) over several flushes, append={append:#x}")


# A precision the ORIGINAL does not survive either, so there is nothing to diff against — see the
# case below. 60 is the largest `c_fmt_float` accepts; 70 overflows the digit array; 65534 reaches
# `c_fmt_getnum`'s 16-bit wrap and arrives as -2.
@pytest.mark.parametrize("fmt,refused", ((b"%.60f", False), (b"%.61f", True),
                                         (b"%.70f", True), (b"%.65534f", True)))
def test_c_fmt_float_refuses_a_precision_its_digit_buffer_cannot_hold(fmt, refused):
    """A CANDIDATE-ONLY case, because the oracle cannot be asked this one.

    The precision in a format string reaches `c_fcvt` as a digit count, and the original writes
    those digits into its own 30-byte frame — so from about `%.27f` upwards the ORIGINAL smashes
    its own stack, and `%.65534f` asks it for a NEGATIVE count. There is no comparable answer to
    diff against. What the reconstruction must not do is write outside its own `digits` array,
    which in the harness's process is a crashed xdist worker rather than a red case; so it refuses,
    and the refusal TALLY is the surface this asserts.
    """
    image = (ctypes.c_uint8 * len(harness.BASE_IMAGE)).from_buffer_copy(harness.BASE_IMAGE)

    def poke(at, data):
        image[at:at + len(data)] = (ctypes.c_uint8 * len(data))(*data)

    poke(DOPRNT_FORMAT, fmt + b"\0")
    poke(DOPRNT_ARGS, abi.long(DOPRNT_FORMAT) + abi.double(3.14159))
    harness._lib.g_os_refusal_reset()
    written = _lib.g_c_doprnt(image, DOPRNT_OUT, DOPRNT_ARGS, INHERITED_CONVERSION,
                              FP_CMP_STATUS_HIGH)
    assert (harness._lib.g_os_refusal_count() != 0) is refused, f"{fmt!r}"
    assert (written == 0) is refused, f"{fmt!r} wrote {written} bytes"


@pytest.mark.parametrize("fmt,values", (
    (GAME_PRINTF_MESSAGE, ()),
    (b"%d/%d\n", ((2, 3), (2, 4))),
    (b"", ()),
))
def test_c_vfprintf(fmt, values):
    """Format into the 256-byte local, then push it at a stream through c_fputs.

    THE BUFFER ITSELF IS NOT COMPARED on either side — the original's is a frame local and the
    reconstruction's is `CLIB_SCRATCH_VFPRINTF_BUFFER`, both inside the band the differential drops
    as stack. What IS compared is what comes out of it: every byte reaches the FILE through c_putc.
    """
    rng = random.Random(len(fmt) * 29 + len(values))
    record = file_record(ptr=FILE_BUFFER, cnt=8, base=FILE_BUFFER,
                         flags=FILE_WRITE | FILE_LINEBUF, fd=harness.OS_FS_FIRST_HANDLE, bufsiz=8)
    pokes, _ = buffered_case(rng, record, files=[(SCR_NAME, b"", 0x200)], open_slots=(0,),
                             buffer=bytes(8),
                             fd_modes=((harness.OS_FS_FIRST_HANDLE, FD_MODE_BINARY),))
    pokes = abi.merge_pokes(pokes, noise_around(rng, DOPRNT_FORMAT, fmt + b"\0"),
                            noise_around(rng, DOPRNT_ARGS,
                                         abi.long(DOPRNT_FORMAT) + printf_arguments(*values)),
                            abi.stack_args((4, A_FILE), (4, DOPRNT_ARGS)))
    info = check(ENTRY_C_VFPRINTF,
                 lambda lib, buf: lib.g_c_vfprintf(buf, A_FILE, DOPRNT_ARGS, INHERITED_CONVERSION,
                                                   FP_CMP_STATUS_HIGH, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs={"d7": INHERITED_CONVERSION, **caller_registers()},
                 note=f"c_vfprintf({fmt!r})")
    check_d0_low_word(info, f"c_vfprintf({fmt!r})")


@pytest.mark.parametrize("fmt,values", (
    (GAME_PRINTF_MESSAGE, ()),
    (b"%s", ((4, DOPRNT_TEXT),)),
))
def test_c_printf(fmt, values):
    """c_vfprintf on `c_stdout`, which is a LINE-BUFFERED CON: stream — so what a case sees is the
    console-byte ledger, filled a line at a time through c_flsbuf -> c_fflush -> c_write."""
    rng = random.Random(len(fmt) + len(values) * 7)
    stdout = file_record(ptr=FILE_BUFFER, cnt=0x20, base=FILE_BUFFER,
                         flags=FILE_WRITE | FILE_LINEBUF, fd=FD_DEVICE_CON, bufsiz=0x20)
    table = bytearray(iob_poke(rng)[A_C_UNBUF_CHARS])
    at = A_C_STDOUT - A_C_UNBUF_CHARS          # c_stdout's record, inside that one staged span
    table[at:at + C_IOB_STRIDE] = stdout
    pokes = abi.merge_pokes({A_C_UNBUF_CHARS: bytes(table)}, trap_slot_noise(rng),
                            fd_table_poke(rng, ((FD_DEVICE_CON, 0),)),
                            noise_around(rng, FILE_BUFFER, bytes(0x20)),
                            noise_around(rng, DOPRNT_FORMAT, fmt + b"\0"),
                            noise_around(rng, DOPRNT_TEXT, b"printed\0"))
    pokes = abi.merge_pokes(pokes, abi.stack_args(
        *(((4, DOPRNT_FORMAT),) + tuple(
            (4, v) if w == 4 else (2, v) for w, v in values if w != "double"))))
    args = abi.FIRST_ARG               # c_printf's `pea 8(a6)`: its own first argument slot
    info = check(ENTRY_C_PRINTF,
                 lambda lib, buf: lib.g_c_printf(buf, args, INHERITED_CONVERSION,
                                                 FP_CMP_STATUS_HIGH, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs={"d7": INHERITED_CONVERSION, **caller_registers()},
                 note=f"c_printf({fmt!r})")
    check_d0_low_word(info, f"c_printf({fmt!r})")


# ================================================================================================
# The five wrappers the trap model used to block — c_unlink, c_auxout_write, c_prtout_write,
# c_exit_pterm and c_exit
#
# One GEMDOS call each: Fdelete (0x41), Cauxout (0x04), Cprnout (0x05) and Pterm (0x4c) twice over.
# None is reachable in play, and each has its own surface now: Fdelete edits the staged-file table
# and answers a code, the two character writers make an OS EVENT per byte, and Pterm makes one and
# LATCHES the ledger — so a reconstruction that ran on past it would be caught by the entries it
# could no longer append (tools/recreate_kit/include/os.h).
# ================================================================================================

ENTRY_C_EXIT_PTERM = 0x14d16
ENTRY_C_EXIT = 0x14d2c
ENTRY_C_UNLINK = 0x16868
ENTRY_C_AUXOUT_WRITE = 0x16ba8
ENTRY_C_PRTOUT_WRITE = 0x16bd6

CONIN_INTERRUPT = 0x03          # ^C — the library terminates the program here
CONIN_EXIT_CODE = 2
OS_EFILNF = -33                 # TOS's "file not found", which os_fdelete answers rather than refuses
OS_EVENT_PTERM = harness.OS_EVENT_PTERM     # the ledger kind a terminated run ends with


# ---- c_unlink ----------------------------------------------------------------------------------

@pytest.mark.parametrize("staged_name,answer", ((DEM_NAME, 0), (SCR_NAME, -1)))
def test_c_unlink(staged_name, answer):
    """Fdelete of a name the harness staged, and of one it did not.

    The second is not a refusal: the staged-file table IS the model's whole filesystem, so a name it
    does not carry is a name that does not exist, and the model gives TOS's own EFILNF for it. What
    the case pins is that both answers are the ones the wrapper turns into 0 and -1.
    """
    rng = random.Random(len(staged_name))
    pokes, _handles = staged([(staged_name, b"contents")])
    pokes = abi.merge_pokes(pokes, path_poke(rng, DEM_NAME), trap_slot_noise(rng),
                            abi.stack_args((4, SCRATCH)))
    info = check(ENTRY_C_UNLINK,
                 lambda lib, buf: lib.g_c_unlink(buf, SCRATCH, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_unlink with {staged_name} staged")
    check_d0_low_word(info, f"c_unlink with {staged_name} staged")
    assert info["ret"] & 0xffff == answer & 0xffff


def test_c_unlink_of_a_missing_file_records_efilnf():
    """The exact code, read off the oracle's own image."""
    rng = random.Random(0x6869)
    pokes, _handles = staged([(SCR_NAME, b"x")])
    pokes = abi.merge_pokes(pokes, path_poke(rng, DEM_NAME), trap_slot_noise(rng),
                            abi.stack_args((4, SCRATCH)))
    image, _writes, _regs = emu.run(harness.make_image(pokes), ENTRY_C_UNLINK,
                                    regs={"a4": abi.A4_BASE, **caller_registers()})
    assert abi.read_word(image, A_C_ERRNO, signed=True) == OS_EFILNF


def test_c_unlink_really_removes_the_staged_slot():
    """A deleted name is gone from the table, which is what makes a later `c_open` of it refuse."""
    rng = random.Random(0x686a)
    pokes, _handles = staged([(DEM_NAME, b"contents")])
    pokes = abi.merge_pokes(pokes, path_poke(rng, DEM_NAME), trap_slot_noise(rng),
                            abi.stack_args((4, SCRATCH)))
    image, _writes, _regs = emu.run(harness.make_image(pokes), ENTRY_C_UNLINK,
                                    regs={"a4": abi.A4_BASE, **caller_registers()})
    assert image[harness.OS_FS_TABLE] == 0, "the slot's name still starts with a byte, so it is not gone"


# ---- c_auxout_write and c_prtout_write ---------------------------------------------------------

AUXOUT_TEXTS = (
    (b"", 0),
    (b"A", 1),
    (b"AUX line\n", 9),
    (b"\x00\x80\xff\x0a", 4),          # a NUL, two high-bit bytes and a newline, none translated
    (b"more than asked for", 5),
)

CHARACTER_DEVICES = {
    "aux": (ENTRY_C_AUXOUT_WRITE, "g_c_auxout_write"),
    "prt": (ENTRY_C_PRTOUT_WRITE, "g_c_prtout_write"),
}


@pytest.mark.parametrize("text,length", AUXOUT_TEXTS)
@pytest.mark.parametrize("device", sorted(CHARACTER_DEVICES))
def test_character_device_write(device, text, length):
    """Every byte straight out, with no CR before a newline — which is what tells these two apart
    from `c_conout_write`, whose identical-looking loop inserts one."""
    entry, symbol = CHARACTER_DEVICES[device]
    rng = random.Random(len(text) * 13 + length + len(device))
    pokes = abi.merge_pokes(noise_around(rng, SCRATCH, text), trap_slot_noise(rng),
                            abi.stack_args((4, SCRATCH), (2, length)))
    check(entry, lambda lib, buf: getattr(lib, symbol)(buf, SCRATCH, length, CALLER_A1, CALLER_A2),
          pokes=pokes, regs=caller_registers(), note=f"{device} {text!r} {length}")


@pytest.mark.parametrize("device", sorted(CHARACTER_DEVICES))
def test_character_device_write_of_nothing_leaves_the_ledger_empty(device):
    """The count is tested BEFORE it is decremented, so a length of 0 writes nothing.

    Asserted rather than left to the diff, for `c_conout_write`'s reason: these two touch no image
    state at all, so an empty ledger on both sides is also what a routine that never ran produces.
    The same staging at length 1 logs exactly one entry, which is what makes the pair evidence.
    """
    entry, symbol = CHARACTER_DEVICES[device]
    rng = random.Random(0xa0 + len(device))

    def run_with(length):
        pokes = abi.merge_pokes(noise_around(rng, SCRATCH, b"A"), trap_slot_noise(rng),
                                abi.stack_args((4, SCRATCH), (2, length)))
        return check(entry,
                     lambda lib, buf: getattr(lib, symbol)(buf, SCRATCH, length, CALLER_A1,
                                                           CALLER_A2),
                     pokes=pokes, regs=caller_registers(), note=f"{device}(_, {length})")

    assert run_with(0)["regs"]["events"] == []
    assert len(run_with(1)["regs"]["events"]) == 1


@pytest.mark.parametrize("handle,text,length", ((FD_DEVICE_AUX, b"aux\n", 4),
                                                (FD_DEVICE_PRT, b"prt\n", 4),
                                                (FD_DEVICE_AUX, b"", 0)))
def test_c_write_to_a_character_device(handle, text, length):
    """...and `c_write`'s two arms that reach them, answered before the fd-mode table is consulted.

    The count they answer is the LENGTH ASKED FOR, exactly as CON:'s arm does — neither writer
    reports how much went out.
    """
    rng = random.Random(handle + length)
    pokes = abi.merge_pokes(noise_around(rng, SCRATCH, text), trap_slot_noise(rng),
                            fd_table_poke(rng, ()),
                            abi.stack_args((2, handle), (4, SCRATCH), (2, length)))
    info = check(ENTRY_C_WRITE,
                 lambda lib, buf: lib.g_c_write(buf, handle, SCRATCH, length,
                                                CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_write {handle:#x} {text!r}")
    check_d0_low_word(info, f"c_write {handle:#x} {text!r}")
    assert info["ret"] & 0xffff == length


# ---- c_exit_pterm and c_exit -------------------------------------------------------------------

@pytest.mark.parametrize("code", (0, 1, 2, 0xffff))
def test_c_exit_pterm(code):
    """One Pterm, and the trampoline's three slots as its trace.

    The oracle ends the run AT the trap — there is nothing after it to execute — and the candidate
    returns from `os_pterm`, which is the one place the two shores differ by construction. What is
    compared is the ledger entry and the save slots (tools/recreate_kit/include/os.h).
    """
    rng = random.Random(0x4d16 + code)
    pokes = abi.merge_pokes(trap_slot_noise(rng), abi.stack_args((2, code)))
    info = check(ENTRY_C_EXIT_PTERM,
                 lambda lib, buf: lib.g_c_exit_pterm(buf, code, CALLER_A1, CALLER_A2),
                 pokes=pokes, regs=caller_registers(), note=f"c_exit_pterm({code})")
    assert info["regs"]["events"] == [(OS_EVENT_PTERM, code)], (
        f"the oracle's ledger is {info['regs']['events']}, not one Pterm({code})")


# The flag combinations `c_exit` walks the table for. A slot is closed exactly when its flags carry
# FILE_READ or FILE_WRITE; the rows either side of that pair are what pin the mask being `& 3` and
# not `!= 0` — FILE_DIRTY alone is a busy-LOOKING record that must be left alone.
EXIT_TABLE_FLAGS = (
    (0, "every slot free"),
    (FILE_READ, "one slot open for reading"),
    (FILE_WRITE, "one open for writing"),
    (FILE_READ | FILE_WRITE, "one open for both"),
    (FILE_DIRTY, "one DIRTY but not open — the mask is & 3, not != 0"),
    (FILE_DIRTY | FILE_WRITE, "one dirty AND open, so its buffer is flushed on the way out"),
)


# The four bytes the dirty stream's buffer holds (`ptr - base` = 4), which `c_fflush` writes out
# through `c_write` on the way to the Pterm. The staged file starts EMPTY, so the staging area's
# first four bytes moving from what `stage_files` left to these is the whole evidence that the close
# really happened — the oracle's own ledger cannot be, since the run ends in a Pterm either way.
EXIT_FLUSHED_BYTES = b"tail"


def _c_exit_oracle_image(pokes):
    """The image ONE oracle run of `c_exit` leaves."""
    image, _writes, _regs = emu.run(harness.make_image(pokes), ENTRY_C_EXIT,
                                    regs={"a4": abi.A4_BASE, **caller_registers()})
    return image


def _staged_file_bytes(image, slot=0):
    """One staged file's contents, read through its own table entry rather than at a fixed offset —
    the flush writes at the GEMDOS CURSOR, which a case may have placed part-way in."""
    entry = harness.OS_FS_TABLE + slot * harness.OS_FS_ENTRY
    at = abi.read_long(image, entry + harness.OS_FS_OFF_STAGING)
    size = abi.read_long(image, entry + harness.OS_FS_OFF_CAPACITY)
    return bytes(image[at:at + size])


def _c_exit_staged_file(pokes, slot=0):
    """(before, after) for one staged file, across one oracle run of `c_exit`."""
    staged = harness.make_image(pokes)
    before = _staged_file_bytes(staged, slot)
    final, _writes, _regs = emu.run(staged, ENTRY_C_EXIT,
                                    regs={"a4": abi.A4_BASE, **caller_registers()})
    return before, _staged_file_bytes(final, slot)


@pytest.mark.parametrize("flags,note", EXIT_TABLE_FLAGS)
def test_c_exit_closes_every_open_stream(flags, note):
    """The 73-record walk, then Pterm. One record at FILE_SLOT carries `flags`; the rest are free.

    The stream is staged with a real file, a real handle and a real buffer, so a record that IS
    closed goes through `c_fclose` -> `c_fflush` -> `c_write` and leaves the staged file changed —
    which is what makes the difference between closing it and skipping it visible in the image as
    well as in the ledger.
    """
    rng = random.Random(0x4d2c + flags)
    # The stream is placed PART-WAY THROUGH a file that really has bytes in it, and its buffer holds
    # a few unread ones: a clean stream's flush seeks the cursor BACK over them, which the model
    # refuses on a negative position — so a case that staged an empty file would be thrown away
    # rather than run.
    pokes, handles = staged([(SCR_NAME, bytes(range(0x80)), 0x100)], open_slots=(0,),
                            cursors=((0, 0x40),))
    handle = handles[SCR_NAME]
    record = file_record(ptr=FILE_BUFFER + 4, cnt=0x10, base=FILE_BUFFER, flags=flags,
                         fd=handle, offset=0, bufsiz=0x200)
    pokes = abi.merge_pokes(pokes, iob_poke(rng, record), noise_around(rng, FILE_BUFFER, b"tail"),
                            fd_table_poke(rng, ((handle, FD_MODE_BINARY),)), trap_slot_noise(rng),
                            abi.stack_args((2, CONIN_EXIT_CODE)))
    check(ENTRY_C_EXIT,
          lambda lib, buf: lib.g_c_exit(buf, CONIN_EXIT_CODE, CALLER_A1, CALLER_A2),
          pokes=pokes, regs=caller_registers(), note=f"c_exit, {note}")
    # WHAT THE ORACLE'S LEDGER SAYS IS NOT EVIDENCE about the candidate — `check` already compares
    # the two streams — so the outcome read back here is the one the byte diff attributes only in
    # company with the whole image: whether the FILE'S OWN BYTES moved. A record that is dirty AND
    # open is flushed on the way out; every other flag set leaves the staged file alone.
    before, after = _c_exit_staged_file(pokes)
    if flags & FILE_DIRTY and flags & FILE_WRITE:
        assert EXIT_FLUSHED_BYTES in after and after != before, (
            f"c_exit, {note}: the stream was not flushed — the staged file is unchanged")
    else:
        assert after == before, (
            f"c_exit, {note}: a stream with no dirty buffer wrote to the file anyway")


def test_c_exit_closes_the_LAST_slot():
    """The walk's BOUND, not just its step: an open stream in record C_IOB_SLOTS - 1.

    Measured: with every case's stream at FILE_SLOT, a walk that stopped one record short passed
    the whole suite. The bound is `a3 < &c_iob[0] + 0x5b4` compared as a LONG, and this is the only
    case that reaches the record it admits last.
    """
    rng = random.Random(0x4d2e)
    pokes, handles = staged([(SCR_NAME, b"", 0x80)], open_slots=(0,))
    handle = handles[SCR_NAME]
    span = bytearray(iob_poke(rng, None)[A_C_UNBUF_CHARS])
    at = A_C_IOB - A_C_UNBUF_CHARS + (C_IOB_SLOTS - 1) * C_IOB_STRIDE
    span[at:at + C_IOB_STRIDE] = file_record(ptr=FILE_BUFFER + 4, cnt=0x10, base=FILE_BUFFER,
                                             flags=FILE_WRITE | FILE_DIRTY, fd=handle,
                                             bufsiz=0x200)
    pokes = abi.merge_pokes(pokes, {A_C_UNBUF_CHARS: bytes(span)},
                            noise_around(rng, FILE_BUFFER, b"last"),
                            fd_table_poke(rng, ((handle, FD_MODE_BINARY),)),
                            trap_slot_noise(rng), abi.stack_args((2, 0)))
    check(ENTRY_C_EXIT, lambda lib, buf: lib.g_c_exit(buf, 0, CALLER_A1, CALLER_A2),
          pokes=pokes, regs=caller_registers(), note="c_exit with the LAST slot open")
    before, after = _c_exit_staged_file(pokes)
    assert after != before and b"last" in after, (
        "the walk stopped before the last record — its stream was never flushed")


def test_c_exit_closes_more_than_one_stream():
    """Two open records, so the walk's ADVANCE is pinned as well as its test: a version that
    stopped at the first busy slot leaves the second stream's buffer unflushed."""
    rng = random.Random(0x4d2d)
    pokes, handles = staged([(SCR_NAME, b"", 0x80), (DEM_NAME, b"", 0x80)], open_slots=(0, 1))
    scr, dem = handles[SCR_NAME], handles[DEM_NAME]
    # Both records are DIRTY, so each flush WRITES rather than seeking back, and the two staged
    # files end up holding different bytes — which is the image evidence that both were closed.
    span = bytearray(iob_poke(rng, None)[A_C_UNBUF_CHARS])
    for slot, handle in ((FILE_SLOT, scr), (FILE_SLOT + 1, dem)):
        at = A_C_IOB - A_C_UNBUF_CHARS + slot * C_IOB_STRIDE
        span[at:at + C_IOB_STRIDE] = file_record(ptr=FILE_BUFFER + 4, cnt=0x1fc, base=FILE_BUFFER,
                                                 flags=FILE_WRITE | FILE_DIRTY, fd=handle,
                                                 bufsiz=0x200)
    pokes = abi.merge_pokes(pokes, {A_C_UNBUF_CHARS: bytes(span)},
                            noise_around(rng, FILE_BUFFER, b"tail"),
                            fd_table_poke(rng, ((scr, FD_MODE_BINARY), (dem, FD_MODE_BINARY))),
                            trap_slot_noise(rng), abi.stack_args((2, 0)))
    check(ENTRY_C_EXIT, lambda lib, buf: lib.g_c_exit(buf, 0, CALLER_A1, CALLER_A2),
          pokes=pokes, regs=caller_registers(), note="c_exit with two open streams")
    # BOTH staged files, so the walk's ADVANCE is read back and not only diffed: a version that
    # stopped at the first busy slot leaves the second file as `stage_files` left it.
    for slot in (0, 1):
        before, after = _c_exit_staged_file(pokes, slot)
        assert after != before and EXIT_FLUSHED_BYTES in after, (
            f"stream {slot} was not flushed on the way out")


# ================================================================================================
# The cross-file pins this battery carries (README.md, "Adding a function", step 4)
# ================================================================================================

MIRRORS = (
    ("CONIN_EXIT_CODE", "include/clib.h", "CONIN_EXIT_CODE"),
    ("CONIN_INTERRUPT", "include/clib.h", "CONIN_INTERRUPT"),
    ("A_C_ERRNO", "include/clib.h", "A_c_errno"),
    ("A_C_MALLOC_FREELIST", "include/clib.h", "A_c_malloc_freelist"),
    ("A_C_MALLOC_SENTINEL", "include/clib.h", "A_c_malloc_sentinel"),
    ("A_FP_OP_TABLE", "include/clib.h", "A_fp_op_table"),
    ("A_FP_ACC", "include/clib.h", "A_fp_acc"),
    ("A_FP_SUB_SIGN_FLAG", "include/clib.h", "A_fp_sub_sign_flag"),
    ("A_FP_CCR", "include/clib.h", "A_fp_ccr"),
    ("A_FD_MODE_TABLE", "include/clib.h", "A_fd_mode_table"),
    ("A_TRAP_SAVED_RET", "include/clib.h", "A_trap_saved_ret"),
    ("A_TRAP_SAVED_A2", "include/clib.h", "A_trap_saved_a2"),
    ("A_TRAP_SAVED_A1", "include/clib.h", "A_trap_saved_a1"),
    ("A_CREAT_DEVICE_NAMES", "include/clib.h", "A_creat_device_names"),
    ("A_OPEN_DEVICE_NAMES", "include/clib.h", "A_open_device_names"),
    ("MALLOC_GRANULE", "include/clib.h", "MALLOC_GRANULE"),
    ("FREE_HEADER_BYTES", "include/clib.h", "FREE_HEADER_BYTES"),
    ("FREE_OFF_SIZE", "include/clib.h", "FREE_OFF_SIZE"),
    ("MORECORE_QUANTUM_GRANULES", "include/clib.h", "MORECORE_QUANTUM_GRANULES"),
    ("FD_MODE_SLOTS", "include/clib.h", "FD_MODE_SLOTS"),
    ("FD_MODE_ENTRY", "include/clib.h", "FD_MODE_ENTRY"),
    ("FD_MODE_BINARY", "include/clib.h", "FD_MODE_BINARY"),
    ("FD_DEVICE_CON", "include/clib.h", "FD_DEVICE_CON"),
    ("FD_DEVICE_AUX", "include/clib.h", "FD_DEVICE_AUX"),
    ("FD_DEVICE_PRT", "include/clib.h", "FD_DEVICE_PRT"),
    ("DEVICE_NAME_STRIDE", "include/clib.h", "DEVICE_NAME_STRIDE"),
    ("OPEN_MODE_TRUNCATE", "include/clib.h", "OPEN_MODE_TRUNCATE"),
    ("RET_C_OPEN_TRUNC_FCREATE", "include/clib.h", "RET_C_OPEN_TRUNC_FCREATE"),
    ("RET_C_OPEN_TRUNC_FCLOSE", "include/clib.h", "RET_C_OPEN_TRUNC_FCLOSE"),
    ("OPEN_MODE_WRITE", "include/clib.h", "OPEN_MODE_WRITE"),
    ("RET_GEMDOS_MALLOC", "include/clib.h", "RET_GEMDOS_MALLOC"),
    ("RET_GEMDOS_MFREE", "include/clib.h", "RET_GEMDOS_MFREE"),
    ("RET_GEMDOS_MALLOC_OR_FAIL", "include/clib.h", "RET_GEMDOS_MALLOC_OR_FAIL"),
    ("RET_C_CLOSE_FCLOSE", "include/clib.h", "RET_C_CLOSE_FCLOSE"),
    ("RET_C_CREAT_FCREATE", "include/clib.h", "RET_C_CREAT_FCREATE"),
    ("RET_C_OPEN_FOPEN", "include/clib.h", "RET_C_OPEN_FOPEN"),
    ("RET_C_READ_FREAD_FIRST", "include/clib.h", "RET_C_READ_FREAD_FIRST"),
    ("RET_C_READ_FREAD_REFILL", "include/clib.h", "RET_C_READ_FREAD_REFILL"),
    ("FP_OP_ADD_SHORT", "include/clib.h", "FP_SOURCE_SHORT"),
    ("FP_OP_ADD_LONG", "include/clib.h", "FP_SOURCE_LONG"),
    ("FP_OP_ADD_FLOAT", "include/clib.h", "FP_SOURCE_FLOAT"),
    ("A_C_IOB", "include/clib.h", "A_c_iob"),
    ("A_C_STDOUT", "include/clib.h", "A_c_stdout"),
    ("A_C_UNBUF_CHARS", "include/clib.h", "A_c_unbuf_chars"),
    ("A_C_BUFSIZ", "include/clib.h", "A_c_bufsiz"),
    ("A_C_FOPEN_SLOT_HINT", "include/clib.h", "A_c_fopen_slot_hint"),
    ("A_C_CONIN_READ_POS", "include/clib.h", "A_c_conin_read_pos"),
    ("A_C_CONIN_LENGTH", "include/clib.h", "A_c_conin_length"),
    ("A_C_CONIN_BUFFER", "include/clib.h", "A_c_conin_buffer"),
    ("A_CRLF", "include/clib.h", "A_crlf"),
    ("A_FCVT_TEN", "include/clib.h", "A_fcvt_ten"),
    ("A_FCVT_MAX_DIGITS", "include/clib.h", "A_fcvt_max_digits"),
    ("A_FMT_FLOAT_ZERO", "include/clib.h", "A_fmt_float_zero"),
    ("A_FMT_FLOAT_EXPONENT_FORMAT", "include/clib.h", "A_fmt_float_exponent_format"),
    ("CLIB_SCRATCH_BASE", "include/clib.h", "CLIB_SCRATCH_BASE"),
    ("C_VFPRINTF_BUFFER_BYTES", "include/clib.h", "C_VFPRINTF_BUFFER_BYTES"),
    ("C_FCVT_DIGITS_OVERHEAD", "include/clib.h", "C_FCVT_DIGITS_OVERHEAD"),
    ("C_FCVT_DIGITS_MAX", "include/clib.h", "C_FCVT_DIGITS_MAX"),
    ("C_EXPONENT_ARGS_BYTES", "include/clib.h", "C_EXPONENT_ARGS_BYTES"),
    ("C_FCVT_DOUBLE_BYTES", "include/clib.h", "C_FCVT_DOUBLE_BYTES"),
    ("C_IOB_SLOTS", "include/clib.h", "C_IOB_SLOTS"),
    ("C_IOB_STRIDE", "include/clib.h", "C_IOB_STRIDE"),
    ("C_IOB_END", "include/clib.h", "C_IOB_END"),
    ("FILE_OFF_PTR", "include/clib.h", "FILE_OFF_PTR"),
    ("FILE_OFF_CNT", "include/clib.h", "FILE_OFF_CNT"),
    ("FILE_OFF_BASE", "include/clib.h", "FILE_OFF_BASE"),
    ("FILE_OFF_FLAGS", "include/clib.h", "FILE_OFF_FLAGS"),
    ("FILE_OFF_FD", "include/clib.h", "FILE_OFF_FD"),
    ("FILE_OFF_OFFSET", "include/clib.h", "FILE_OFF_OFFSET"),
    ("FILE_OFF_BUFSIZ", "include/clib.h", "FILE_OFF_BUFSIZ"),
    ("FILE_READ", "include/clib.h", "FILE_READ"),
    ("FILE_WRITE", "include/clib.h", "FILE_WRITE"),
    ("FILE_APPEND", "include/clib.h", "FILE_APPEND"),
    ("FILE_UNBUFFERED", "include/clib.h", "FILE_UNBUFFERED"),
    ("FILE_MYBUF", "include/clib.h", "FILE_MYBUF"),
    ("FILE_EOF", "include/clib.h", "FILE_EOF"),
    ("FILE_ERR", "include/clib.h", "FILE_ERR"),
    ("FILE_DIRTY", "include/clib.h", "FILE_DIRTY"),
    ("FILE_LINEBUF", "include/clib.h", "FILE_LINEBUF"),
    ("FMT_NO_PRECISION", "include/clib.h", "FMT_NO_PRECISION"),
    ("CRLF_BYTES", "include/clib.h", "CRLF_BYTES"),
    ("RET_C_FILBUF_FSEEK", "include/clib.h", "RET_C_FILBUF_FSEEK"),
    ("RET_C_LSEEK_FSEEK", "include/clib.h", "RET_C_LSEEK_FSEEK"),
    ("RET_C_WRITE_FWRITE_RUN", "include/clib.h", "RET_C_WRITE_FWRITE_RUN"),
    ("RET_C_WRITE_FWRITE_CRLF", "include/clib.h", "RET_C_WRITE_FWRITE_CRLF"),
    ("RET_C_WRITE_FWRITE_TAIL", "include/clib.h", "RET_C_WRITE_FWRITE_TAIL"),
    ("RET_C_CONOUT_CR", "include/clib.h", "RET_C_CONOUT_CR"),
    ("RET_C_CONOUT_BYTE", "include/clib.h", "RET_C_CONOUT_BYTE"),
    ("RET_C_CONIN_CRAWCIN", "include/clib.h", "RET_C_CONIN_CRAWCIN"),
)

# SIXTEEN BYTES, not the usual eight. Five of the floating-point routines open with the identical
# `link a6,#$0 / movem.l #$ffc0,-(a7) / movea.l …(a6),aN` — fp_add, fp_sub, fp_mul, fp_div and
# fp_long_to_double — and the two fd-mode walkers differ only in a branch displacement, so a shorter
# prologue would let one stand for another and a mistyped entry would run the wrong routine and
# still come back clean.
ENTRY_PROLOGUES = {
    "ENTRY_C_EXIT_PTERM": "4e5600003f2e00083f3c004c4eba1134",
    "ENTRY_C_EXIT": "4e56fffe2f0b41ec9bee26486016302b",
    "ENTRY_C_UNLINK": "4e5600002f2e00083f3c00414ebaf5e2",
    # TWENTY-FOUR BYTES for the two character writers: they are the identical loop over two
    # different GEMDOS selectors, and the selector is the first thing that tells them apart.
    "ENTRY_C_AUXOUT_WRITE": "4e5600006018206e000852ae0008101048803f003f3c0004",
    "ENTRY_C_PRTOUT_WRITE": "4e5600006018206e000852ae0008101048803f003f3c0005",
    # Only two of these bytes are the routine; the rest are `init_gem_and_screens` behind it, which
    # is what makes a sixteen-byte pin possible for a two-byte `rts`.
    "ENTRY_CRT0_SETUP_ARGS": "4e754e56fffa4eba4a763d40fffc426e",
    "ENTRY_C_STRLEN": "4e56000048e70030266e0008244b6000",
    "ENTRY_C_STRCMP": "4e56000048e70030266e0008246e000c",
    "ENTRY_C_LDIV": "4e56fffe48e7f000242e0008660a80fc",
    "ENTRY_C_LMUL": "4e56fffa2f00426efffe4aae00086c08",
    "ENTRY_C_SETFDMODE": "4e56fffe426efffe6036302efffee580",
    "ENTRY_C_CLEARFDMODE": "4e56fffe426efffe6026302efffee580",
    "ENTRY_C_GETFDMODE": "4e56fffe3f073e2e00083d7c0130fffe",
    "ENTRY_C_MORECORE": "4e56000048e701303e3c0418322e0008",
    "ENTRY_C_MALLOC": "4e56000048e701303e3c0001322e0008",
    "ENTRY_C_FREE": "4e56000048e70030202e00085d802640",
    "ENTRY_GEMDOS_MALLOC": "4e5600002f2e00083f3c00484eba01c8",
    "ENTRY_GEMDOS_MFREE": "4e5600002f2e00083f3c00494eba01b2",
    "ENTRY_GEMDOS_MALLOC_OR_FAIL": "4e56fffc302e0008c0bc0000ffff2f00",
    "ENTRY_XBIOS_TRAP": "29499a20294a9a1c295f9a184e4e226c",
    "ENTRY_C_OPEN": "4e56fffe486c02d22f2e00084eba0a8a",
    "ENTRY_C_CREAT": "4e56fffe486c02ac2f2e00084eba1b74",
    "ENTRY_C_CLOSE": "4e5600003f2e00084eba10b4548f0c6e",
    "ENTRY_C_READ": "4e56fffc48e70030266e000a302e000e",
    "ENTRY_FP_PACK_FLOAT": "4e5600002002c0bcffffff0066044243",
    "ENTRY_FP_CMP": "4e56000048e7f080206e000820182210",
    "ENTRY_FP_DIV": "4e56000048e7ffc0206e0008226e000c",
    "ENTRY_FP_MUL": "4e56000048e7ffc0206e00082410e182",
    "ENTRY_FP_SUB": "4e56000048e7ffc0226e000c303c8000",
    "ENTRY_FP_ADD": "4e56000048e7ffc0226e000c426c9b88",
    "ENTRY_FP_PACK_DOUBLE": "2002c0bcffffff006606428142826048",
    "ENTRY_FP_DISPATCH": "4e56fff648e7e080302e0008c07cff00",
    "ENTRY_FP_ACC_LOAD_LONG": "29409b80486c9b804eba0098584f4e75",
    "ENTRY_FP_ACC_TO_LONG": "486c9b804eba0044584f202c9b804e75",
    "ENTRY_FP_FLOAT_TO_DOUBLE": "4e56000048e7c080206e000842812010",
    "ENTRY_FP_DOUBLE_TO_LONG": "4e56000048e7e080206e00082210e181",
    "ENTRY_FP_LONG_TO_DOUBLE": "4e56000048e7ffc0206e000824106606",
    "ENTRY_C_FCLOSE": "4e5600002f0b266e00082f0b4eba0044",
    "ENTRY_C_FFLUSH": "4e56000048e70110266e0008302b000a",
    "ENTRY_C_FILBUF": "4e56fffc2f0b266e0008302b000ac07c",
    "ENTRY_C_FLSBUF": "4e56fffc2f0b266e000a426b0004302b",
    "ENTRY_C_PUTC": "4e560000206e000a5368000430280004",
    "ENTRY_C_FCVT": "4e56fff248e70730266e0008246e000c",
    "ENTRY_C_FOPEN": "4e56fffc48e70130266e000c426efffc",
    "ENTRY_C_FREAD": "4e56fffe48e70310266e00083e2e000e",
    "ENTRY_C_LSEEK": "4e56fff20c6e000000086c0a203cffff",
    "ENTRY_C_FMT_INTEGER": "4e56ffd648e70110266e000c426effd6",
    "ENTRY_C_FMT_FLOAT": "4e56ffde48e70310266e000c0c6e0100",
    "ENTRY_C_FMT_GETNUM": "4e56fffe426efffe6022302efffec1fc",
    "ENTRY_C_DOPRNT": "4e56ffe648e70330266e000c2d6e0008",
    "ENTRY_C_VFPRINTF": "4e56fefe2f2e000c486eff004ebafd68",
    "ENTRY_C_PRINTF": "4e560000486e0008486c9c024ebaffc6",
    "ENTRY_C_SPRINTF": "4e560000486e000c2f2e00084ebafd26",
    "ENTRY_C_FPUTS": "4e56000060182f2e000c206e000852ae",
    "ENTRY_C_CONIN": "4e56fffc0c6e830000086600013a302c",
    "ENTRY_C_CONOUT_WRITE": "4e5600006034206e000810104880b07c",
    "ENTRY_C_WRITE": "4e56fff248e70030266e000a244b41ec",
}
