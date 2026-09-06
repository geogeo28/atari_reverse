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

import pytest

import abi
import emu
import harness
from harness import report

# ---- entry addresses (../out/prg_dis.txt, at load base 0x10000) ---------------------------------
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
OPEN_MODE_WRITE = 0x0002
RET_GEMDOS_MALLOC = 0x15c92
RET_GEMDOS_MFREE = 0x15ca8
RET_GEMDOS_MALLOC_OR_FAIL = 0x167e0
RET_C_CLOSE_FCLOSE = 0x14c64
RET_C_CREAT_FCREATE = 0x14cc2
RET_C_OPEN_FOPEN = 0x15e0a
RET_C_READ_FREAD_FIRST = 0x166fe
RET_C_READ_FREAD_REFILL = 0x16762

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

def stub_case(calls, results, note, glue, poison=False, extra=None):
    """Drive `calls` from a poked stub and hand back the differential's info.

    `results` is how many longword slots the stub files, so the case can seed noise over exactly
    those and no more — an unseeded slot the candidate forgot to write would match the oracle's by
    holding the same zeroes. `extra` is anything else the run needs staged (the zero-divide vector
    below is the only user).
    """
    rng = random.Random(hash(note) & 0xffff)
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
    """...and the declaration is load-bearing: with $14 as the loader leaves it, the run is refused.

    This is what keeps the case above honest. The oracle takes the exception to address 0 and
    executes the vector page, so it never reaches the `rts` — and if the kit ever grows a model for
    the vector, this reddens and the pair of cases gets revisited rather than quietly diverging.
    """
    with pytest.raises(RuntimeError, match="unmodeled OS behaviour|did not reach"):
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
    """The trampolines' three save slots under noise, so a wrapper that failed to write one is a
    difference rather than a zero matching a zero. They are consecutive longwords in that order."""
    assert A_TRAP_SAVED_A2 == A_TRAP_SAVED_RET + 4 and A_TRAP_SAVED_A1 == A_TRAP_SAVED_RET + 8
    return {A_TRAP_SAVED_RET: rng.randbytes(12)}


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


def staged(files, open_slots=()):
    """`harness.stage_files`, with the named slots marked already open.

    `os_fread` refuses a handle whose slot is closed, and a case that enters `c_read` directly never
    ran the `c_open` that would have opened it — so the flag is part of the world the case stages.
    """
    pokes, handles = harness.stage_files(files)
    for slot in open_slots:
        key = harness.OS_FS_TABLE + slot * harness.OS_FS_ENTRY
        entry = bytearray(pokes[key])
        entry[harness.OS_FS_OFF_OPEN:harness.OS_FS_OFF_OPEN + 4] = (1).to_bytes(4, "big")
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
    rng = random.Random(hash(note) & 0xffff)
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
    """
    rng = random.Random(0x9f0)
    for mantissa, exponent in ((0, 0), (0xff, 0x40), (0x80000000, 0x7f), (0x80000200, 0x7f),
                               (0x800002ff, 0x7f), (0xffffffff, 0xfe), (0x40000000, 0x01)):
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
# The cross-file pins this battery carries (README.md, "Adding a function", step 4)
# ================================================================================================

MIRRORS = (
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
)

# SIXTEEN BYTES, not the usual eight. Five of the floating-point routines open with the identical
# `link a6,#$0 / movem.l #$ffc0,-(a7) / movea.l …(a6),aN` — fp_add, fp_sub, fp_mul, fp_div and
# fp_long_to_double — and the two fd-mode walkers differ only in a branch displacement, so a shorter
# prologue would let one stand for another and a mistyped entry would run the wrong routine and
# still come back clean.
ENTRY_PROLOGUES = {
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
}
