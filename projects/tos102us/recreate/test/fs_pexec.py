r"""`Pexec`'s LOADER staging — synthesised GEMDOS-format PRGs on the staged RAM disk, and the machine
`Pexec` loads them into (`test_gemdos_process_pexec_load.py`).

WHAT IS REAL HERE is the file. Every program is built byte for byte in the GEMDOS format
`include/gemdos/pexec_load.h` describes — the 28-byte header, TEXT, DATA, a symbol table, then the
relocation stream — and written onto `test/fs_dir.py`'s tree as an ordinary file: a root entry and a
cluster chain in both FATs, laid by `fs_dir.directory_tree` exactly as it lays a directory's chain (a
file's clusters and a directory's are the same bytes to the disk). Nothing hands the loader an OFD or a
handle; it opens the file by name, through the ROM's own `Fopen`.

WHAT IS SHAPED is the memory it loads into. `Pexec` cuts the TPA as the WHOLE largest free block, and
the snapshot's one free block spans the staging band, the RAM disk and the stack — so a case re-cuts the
pool (`gemdos_memory.stage`) into a small FREE block at its bottom, which the environment and the TPA
are cut from, and a USED rest charged to the desktop. The TPA's size is the case's own input: it is what
decides whether a BSS fits and how the relocation stream is chunked.

AND ONE REGISTER. The loader's `Fopen` mode is the high half of the trapping caller's D5
(`include/gemdos/pexec_load.h`), which the ORACLE has in the register and our core reads out of the
trap entry's saved frame — so every case stages both, one value in two places, at the frame the
snapshot's `p_run` already points at. Poked alone, that D5 stands where `GEMDOS_SAVED_FRAME_D5` says,
which is the offset our core reads too; `trap_frame` is the case that does not take the header's word
for it — the whole frame as the ROM's own trap entry builds it.
"""
import ctypes
import struct
from collections import namedtuple
from pathlib import Path

from harness import BASE_IMAGE, _lib, addrs, emu, make_image

import abi
import case
import fs_dir as d
import fs_io as io
import gemdos
import gemdos_fs as fs
import gemdos_memory as gm
import gemdos_process as process
import trap

LOADER_HEADER = Path(__file__).resolve().parents[1] / "include" / "gemdos" / "pexec_load.h"
PEXEC_LOAD = addrs.parse(LOADER_HEADER)
PRG_MAGIC = PEXEC_LOAD["PRG_MAGIC"]
PRG_HEADER_BYTES = PEXEC_LOAD["PRG_HEADER_BYTES"]
PRG_SKIP = PEXEC_LOAD["PRG_RELOCATION_SKIP"]
PRG_SKIP_DISTANCE = PEXEC_LOAD["PRG_SKIP_DISTANCE"]
PRG_END = PEXEC_LOAD["PRG_RELOCATION_END"]
EPLFMT = PEXEC_LOAD["GEMDOS_EPLFMT"]
ENSMEM = process.GEMDOS_ENSMEM
EFILNF = process.GEMDOS_EFILNF

for _symbol in ("gemdos_pexec", "gemdos_pexec_create", "gemdos_pexec_load"):
    getattr(_lib, _symbol).restype = ctypes.c_uint32

LONG = ">I"
LONG_BYTES = struct.calcsize(LONG)
# A longword in TEXT or DATA that a fixup is aimed at holds an OFFSET into the program — what a linker
# leaves for the loader to turn into an address by adding the TEXT base.
POINTER = ">I"


# ---- a program --------------------------------------------------------------------------------------

def relocation_stream(offsets):
    """The stream that fixes the longwords at `offsets` (ascending, from TEXT): the first as a longword,
    then each distance as bytes — a 1 for every 254 it has to be carried over — and the 0 that ends it."""
    if not offsets:
        return struct.pack(LONG, 0)
    stream = bytearray(struct.pack(LONG, offsets[0]))
    for before, after in zip(offsets, offsets[1:]):
        distance = after - before
        while distance > PRG_SKIP_DISTANCE:
            stream.append(PRG_SKIP)
            distance -= PRG_SKIP_DISTANCE
        stream.append(distance)
    return bytes(stream) + bytes([PRG_END])


Program = namedtuple("Program", "name attr text data bss symbols relocation file tpa")


def program(name, text, data=b"", bss=0, symbols=b"", relocation=None, fixups=(), *, attr=fs.ATTR_NONE,
            magic=PRG_MAGIC, flags=0, absflag=0, lengths=None, cut=None, tpa=None):
    """A `.PRG`: the header, TEXT, DATA, the symbol table and the relocation stream, as its file's bytes.

    `relocation` is the raw stream (a longword, then bytes); by default it is `relocation_stream(fixups)`.
    `lengths` overrides the four the header CLAIMS — (tlen, dlen, blen, slen) — so a header can say more
    than the file holds; `cut` truncates the file to that many bytes. `tpa` is the TPA the case gives it,
    or `TPA_BYTES`."""
    relocation = relocation_stream(list(fixups)) if relocation is None else relocation
    claimed = lengths or (len(text), len(data), bss, len(symbols))
    header = struct.pack(">HIIIIIIH", magic, *claimed, 0, flags, absflag)
    assert len(header) == PRG_HEADER_BYTES
    file = header + text + data + symbols + relocation
    return Program(name, attr, text, data, bss, symbols, relocation, file[:cut], tpa or TPA_BYTES)


def pointers(length, targets, seed):
    """`length` bytes of a segment: a ramp keyed on `seed` (so a byte out of place is a wrong byte), with
    the longword at each offset in `targets` holding the offset it POINTS AT — `{at: points_at}`."""
    segment = bytearray(fs.body(seed, length))
    for at, points_at in targets.items():
        struct.pack_into(POINTER, segment, at, points_at)
    return bytes(segment)


# How big a TPA a case gets: the basepage, every program below, its relocation buffer and a BSS, with
# more than one 256-byte block left over so the clear's block arm runs.
TPA_BYTES = 0x800

# ---- the programs on the disk -------------------------------------------------------------------------
# Every one is a GEMDOS-format file in the root, from the first cluster past the last one `fs_dir`'s tree uses.
FIRST_PROGRAM_CLUSTER = max(cluster for chain, _entries in d.DIRECTORIES for cluster in chain) + 1
TEXT_SEED, DATA_SEED, SYMBOL_SEED = 0x21, 0x61, 0x91

# The ordinary program: TEXT with three pointers into itself and DATA, DATA with one back into TEXT, a
# BSS, and a symbol table the loader must skip — whose bytes would be a relocation stream of their own
# (every one of them a small non-zero distance) if the `Fseek` over it were missing.
HELLO_TEXT = pointers(0x40, {0x04: 0x30, 0x10: 0x44, 0x2c: 0x00}, TEXT_SEED)
HELLO_DATA = pointers(0x10, {0x08: 0x3c}, DATA_SEED)
HELLO_FIXUPS = (0x04, 0x10, 0x2c, 0x48)
HELLO_SYMBOLS = bytes([2]) * 0x1c
HELLO = program("HELLO", HELLO_TEXT, HELLO_DATA, 0x40, HELLO_SYMBOLS, fixups=HELLO_FIXUPS)

WILD_FIXUPS = (0x04, 0x04 + TPA_BYTES)          # the second is past the TPA's end

PROGRAMS = (
    HELLO,
    # No relocation at all: a first offset of 0, and nothing after it is read.
    program("PLAIN", HELLO_TEXT, HELLO_DATA, 0x40),
    # A fixup more than 254 bytes past the one before, so the stream carries it with 1 bytes.
    program("FAR", pointers(0x300, {0x002: 0x10, 0x2f8: 0x20}, TEXT_SEED), fixups=(0x002, 0x2f8)),
    # ...and one that reaches the TPA's last longword in DATA with an ODD-length TEXT+DATA, which starts
    # the clear on an odd byte.
    program("ODD", HELLO_TEXT + b"\x4e", HELLO_DATA, 0x10, fixups=(0x04,)),
    program("NOTPRG", HELLO_TEXT, magic=0x601b),
    # Headers that claim more TEXT than the file holds: the read stops short and nothing checks it. With
    # the absolute flag that is the whole load; without it the relocation offset is read at the file's
    # end, reads nothing, and the loader relocates by whatever its frame local held.
    program("SHORT", HELLO_TEXT, HELLO_DATA, fixups=(0x04,), lengths=(0x200, 0x10, 0, 0), absflag=1),
    program("TRUNC", HELLO_TEXT, HELLO_DATA, fixups=(0x04,), lengths=(0x200, 0x10, 0, 0)),
    # The absolute flag: TEXT and DATA read, and NOTHING relocated, cleared or closed.
    program("ABS", HELLO_TEXT, HELLO_DATA, 0x40, fixups=HELLO_FIXUPS, absflag=1),
    # The program flags TOS 1.02 reads and ignores — fast-load among them, so the TPA is still cleared.
    program("FLAGS", HELLO_TEXT, HELLO_DATA, 0x40, fixups=HELLO_FIXUPS, flags=0x7),
    # A symbol table the header OVERCLAIMS: the `Fseek` past it is ERANGE and ignored, the cursor stays
    # where the TEXT+DATA read left it — which is where this file's relocation really starts.
    program("OVERSYM", HELLO_TEXT, HELLO_DATA, fixups=HELLO_FIXUPS, lengths=(0x40, 0x10, 0, 0x400)),
    # First fixups outside TEXT+DATA: at its end (refused), before its start (refused, signed), and two
    # bytes short of its end (admitted — the longword it fixes runs into the relocation buffer).
    program("ATEND", HELLO_TEXT, HELLO_DATA, fixups=(0x50,)),
    program("BEFORE", HELLO_TEXT, HELLO_DATA, relocation=struct.pack(LONG, 0xFFFF_FFFE) + b"\0"),
    program("STRADDLE", HELLO_TEXT, HELLO_DATA, fixups=(0x4e,)),
    # A fixup INSIDE the one chunk that walks the cursor past DATA and the TPA: nothing checks it.
    program("WILD", HELLO_TEXT, HELLO_DATA, fixups=WILD_FIXUPS),
    # A stream with no 0 at its end: it simply runs out.
    program("NOEND", HELLO_TEXT, HELLO_DATA, 0x40, relocation=relocation_stream(list(HELLO_FIXUPS))[:-1]),
    # A fixup on every longword of TEXT and DATA past the first: a stream long enough to be read in
    # several chunks through a TPA with only a few bytes to spare.
    program("MANY", pointers(0x40, {at: at for at in range(4, 0x40, 4)}, TEXT_SEED), HELLO_DATA,
            fixups=range(4, 0x50, 4)),
    # ...and one whose cursor is walked past DATA by SKIP bytes alone, which fix nothing and are checked
    # by nothing until the chunk they are in runs out.
    program("WALK", HELLO_TEXT, HELLO_DATA, relocation=struct.pack(LONG, 4) + bytes([PRG_SKIP] * 3 + [4, PRG_END])),
    # A first fixup at TEXT+0 cannot be said: a first offset of 0 is "no relocation", and the stream
    # after it is never read.
    program("ZERO", HELLO_TEXT, HELLO_DATA, fixups=(0x00, 0x04)),
    program("LOCKED", HELLO_TEXT, HELLO_DATA, 0x40, fixups=HELLO_FIXUPS, attr=fs.GEMDOS_ATTR_READ_ONLY),
    program("SECRET", HELLO_TEXT, HELLO_DATA, 0x40, fixups=HELLO_FIXUPS, attr=fs.GEMDOS_ATTR_HIDDEN),
)
BY_NAME = {one.name: one for one in PROGRAMS}


def _clusters_for(length):
    return max(1, -(-length // fs.CLUSTER_BYTES))


def _layout(programs):
    """`{name: first cluster}` and the chains, one program after another from FIRST_PROGRAM_CLUSTER."""
    first, chains, cluster = {}, [], FIRST_PROGRAM_CLUSTER
    for one in programs:
        chain = tuple(range(cluster, cluster + _clusters_for(len(one.file))))
        first[one.name] = chain[0]
        chains.append((chain, [one.file]))
        cluster += len(chain)
    assert cluster <= fs.FIRST_DATA_CLUSTER + fs.DATA_CLUSTERS, "the programs outgrew the staged disk"
    return first, chains


FIRST_CLUSTER, _CHAINS = _layout(PROGRAMS)
PROGRAM_ROWS = tuple((one.name, "PRG", one.attr, FIRST_CLUSTER[one.name], len(one.file), False)
                     for one in PROGRAMS)
DISK = d.directory_tree(d.ROOT + [fs.staged_dirent(*row) for row in PROGRAM_ROWS],
                        d.DIRECTORIES + tuple(_CHAINS))


def path(name):
    return f"A:\\{name}.PRG"


# ---- the machine it is loaded into -----------------------------------------------------------------------

# The environment `Pexec` copies (the process battery's, an odd length) — measured the ROM's way, so a
# case knows how much of the free block it takes before the TPA is cut from the rest.
ENVIRONMENT = b"PATH=A:\\\0TOSTEST=1\0\0"
ENVIRONMENT_BLOCK = len(ENVIRONMENT) + (len(ENVIRONMENT) & 1)
COMMAND_TAIL = bytes([5]) + b"HELLO"


def pool(tpa_bytes):
    """The snapshot's free block re-cut: the environment's block and a TPA of `tpa_bytes` FREE at its
    bottom, the rest USED — and the FREE bytes DIRTY (`SLACK_FILL`), because the snapshot leaves them zero
    and a clear over zeroes, or a segment read that stopped short over them, would move nothing."""
    free = ENVIRONMENT_BLOCK + tpa_bytes
    staged = gm.stage([(gm.FREE, free), (gm.USED, gm.SNAPSHOT_FREE_MD.length - free)], rover_span=0)
    return {**staged.pokes, gm.SNAPSHOT_FREE_MD.start: bytes([fs.SLACK_FILL]) * free}


# Where the basepage `Pexec` cuts will be: the TPA is the free block past the environment's.
BASEPAGE = gm.SNAPSHOT_FREE_MD.start + ENVIRONMENT_BLOCK
TEXT = BASEPAGE + process.BASEPAGE_BYTES

# THE D5 FRAME: the trap entry's saved frame the snapshot's `p_run` points at, and D5's slot in it.
CALLER_FRAME = case.long_in(BASE_IMAGE, gemdos.BASEPAGE + addrs.BASEPAGE_SAVED_FRAME)
CALLER_D5_AT = CALLER_FRAME + addrs.GEMDOS_SAVED_FRAME_D5
# A D5 whose high half is a WRITE mode — any non-zero word is one to `open`'s read-only test.
WRITING_D5 = 0x0001_2345
READING_D5 = 0x0000_2345


def caller_d5(d5):
    """The D5 the trap entry saved, poked where our core reads it; the oracle gets it in the register."""
    return {CALLER_D5_AT: struct.pack(LONG, d5)}


def trap_frame(d5, d4):
    """THE D5 FRAME AS THE ROM WRITES IT: a `Pexec(3)` caller entering with `d5` and `d4`, run through the
    ORIGINAL's trap entry up to the dispatcher, and the fifty bytes of register frame it built read out
    whole — `{CALLER_FRAME: bytes}`, moved to where the snapshot's `p_run` points, because the entry
    builds it on the run's own stack, which the next run reuses. The layout inside is the ROM's, so a
    reader one slot off takes D4 where it wanted D5. (`src/gemdos/trap1.S` is that entry byte for byte,
    held to it by Tier 3's second differential; the dispatcher between it and `Pexec` never touches D5.)"""
    words = (process.PEXEC_LOAD, *gemdos.long_words(d.TEXT_AT), *gemdos.long_words(process.COMMAND_TAIL_AT),
             *gemdos.long_words(process.ENVIRONMENT_AT))
    staged = {trap.CALLER_AT: trap.caller(addrs.GEMDOS_PEXEC_FN, words), abi.FIRST_ARG: trap.longword(addrs.GEMDOS_TRAP1)}
    final, _writes, _regs = emu.run(make_image(staged), trap.CALLER_AT, {**trap.ENTRY_REGS, "d4": d4, "d5": d5},
                                    stop_pc=addrs.GEMDOS_DISPATCH)
    frame = case.long_in(final, gemdos.BASEPAGE + addrs.BASEPAGE_SAVED_FRAME)
    return {CALLER_FRAME: bytes(final[frame:frame + addrs.GEMDOS_SAVED_FRAME_BYTES])}


def machine(tpa_bytes=TPA_BYTES, d5=READING_D5, pokes=None, name=None, frame=None):
    """The tree with the programs on it in drive A:, the name's text, the re-cut pool, `Pexec`'s two
    blocks and the D5 frame — `frame` (`trap_frame`) whole, or else `d5` poked alone — then the case's own
    `pokes`: what `fs_io.run` stages from."""
    return d.staged({**DISK, **(d.text(path(name)) if name else {}), **pool(tpa_bytes),
                     process.ENVIRONMENT_AT: ENVIRONMENT, process.COMMAND_TAIL_AT: COMMAND_TAIL + b"\0",
                     **(frame or caller_d5(d5)), **(pokes or {})})


# ---- `Pexec` past its record, modes 3 and 0 ------------------------------------------------------------

def pexec_pokes(mode, one, tpa_bytes=None, d5=READING_D5, pokes=None, frame=None):
    return {**machine(tpa_bytes or one.tpa, d5, pokes, one.name, frame), **process.slice_trampoline(),
            **process.pexec_args(mode, d.TEXT_AT, process.COMMAND_TAIL_AT, process.ENVIRONMENT_AT)}


def pexec_glue(mode):
    return lambda lib, buf: lib.gemdos_pexec_create(buf, mode, d.TEXT_AT, process.COMMAND_TAIL_AT,
                                                    process.ENVIRONMENT_AT)


def pexec(mode, one, tpa_bytes=None, d5=READING_D5, pokes=None, frame=None):
    """`Pexec(mode)` of `one` entered at the slice, run to its `rts` — every mode-3 case, and a mode-0
    case whose load FAILS, which returns before it can go."""
    return io.run(process.SLICE_TRAMPOLINE_AT, pexec_glue(mode), pexec_pokes(mode, one, tpa_bytes, d5, pokes, frame),
                  regs={"d5": d5})


def pexec_and_go(one, tpa_bytes=None, d5=READING_D5, pokes=None):
    """`Pexec(0)` of `one`, which loads and GOES: a CHECKPOINT at the `jsr` into the trap epilogue, with
    no claim about D0 (`test_gemdos_process_pexec.py`'s `run_mode_4` says why)."""
    glue = pexec_glue(process.PEXEC_LOAD_AND_GO)

    def go(lib, buf):
        glue(lib, buf)          # ...its answer DROPPED: the case is `NO_RESULT`, which refuses a glue returning one

    return io.run(process.SLICE_TRAMPOLINE_AT, go, pexec_pokes(process.PEXEC_LOAD_AND_GO, one, tpa_bytes, d5, pokes),
                  regs={"d5": d5}, stop_pc=process.PEXEC_EPILOGUE_CALL, width=case.NO_RESULT)


def register_pexec(label, mode, one, tpa_bytes=None, d5=READING_D5, pokes=None):
    """...and a mode-3 case as a Tier 3 row."""
    return io.register(label, process.SLICE_TRAMPOLINE_AT, pexec_pokes(mode, one, tpa_bytes, d5, pokes),
                       regs={"d5": d5})


# ---- the loader at its own address, over a basepage `Pexec(5)` really cut --------------------------------

LOADER_FRAME = ">II"                    # name, basepage


def created(tpa_bytes=TPA_BYTES, d5=READING_D5, name="HELLO"):
    """`Pexec(5)` run for real — the ORIGINAL's basepage, environment and pool, which the loader case
    then starts from (`gemdos_fs.continued`)."""
    staged = {**machine(tpa_bytes, d5, None, name), **process.slice_trampoline(),
              **process.pexec_args(process.PEXEC_CREATE_BASEPAGE, 0, process.COMMAND_TAIL_AT,
                                   process.ENVIRONMENT_AT)}
    result = io.run(process.SLICE_TRAMPOLINE_AT, pexec_glue(process.PEXEC_CREATE_BASEPAGE), staged)
    assert result.info["ret"] == BASEPAGE
    return fs.continued(result)


def load_pokes(start, d5=READING_D5, name=None):
    """`start` with the loader's frame, the name `name`'s path if it is another than the one `start`
    staged, and the D5 frame to match `d5`."""
    return {**start, **(d.text(path(name)) if name else {}), **caller_d5(d5),
            **case.args(LOADER_FRAME, d.TEXT_AT, BASEPAGE)}


def load(start, d5=READING_D5, name=None):
    """`$fc85ea` over `start` (`created()`), entered with `d5`. Glued by hand, not through
    `gemdos_fs.routine`: the core also takes the D5 its caller left, which its frame does not carry."""
    return io.run(addrs.GEMDOS_PEXEC_LOAD,
                  lambda lib, buf: lib.gemdos_pexec_load(buf, d.TEXT_AT, BASEPAGE, d5),
                  load_pokes(start, d5, name), regs={"d5": d5})


def register_load(label, start, d5=READING_D5):
    """...and a loader case as a Tier 3 row."""
    return io.register(label, addrs.GEMDOS_PEXEC_LOAD, load_pokes(start, d5), regs={"d5": d5})


# ---- reading a load back ----------------------------------------------------------------------------------

def relocated(segment, fixups, base, at=0):
    """What `segment` (loaded at offset `at` of the program) holds once every fixup inside it has had the
    TEXT base added."""
    out = bytearray(segment)
    for offset in fixups:
        inside = offset - at
        if 0 <= inside <= len(out) - LONG_BYTES:
            struct.pack_into(LONG, out, inside, (struct.unpack_from(LONG, out, inside)[0] + base) & fs.LONG_MASK)
    return bytes(out)


def segments(result, basepage=BASEPAGE):
    """The six longwords the loader publishes: (tbase, tlen, dbase, dlen, bbase, blen)."""
    return struct.unpack(">6I", result.after(basepage + addrs.BASEPAGE_TBASE, 6 * LONG_BYTES))


def open_handles(result):
    """The handle records still claimed after a run: `(handle, owner)`."""
    return [(handle, process.descriptor(result.final, handle).owner)
            for handle in range(addrs.GEMDOS_FIRST_FILE_HANDLE,
                                addrs.GEMDOS_FIRST_FILE_HANDLE + process.GEMDOS_HANDLE_COUNT)
            if process.descriptor(result.final, handle).owner]


# ---- what the orchestrator needs ----------------------------------------------------------------------------
CASE_FIELDS = ((CALLER_D5_AT, LONG_BYTES, "the trapping caller's saved D5, whose high half is the loader's Fopen mode"),)
