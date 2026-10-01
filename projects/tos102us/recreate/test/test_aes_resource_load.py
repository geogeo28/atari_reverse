r"""LOADING A RESOURCE FILE — rs_readit ($feaae2) and rs_load ($feac5c, rsrc_load): `src/aes/resource.c`.

    rs_readit(g, name):  shell buffer := name; sh_find(it, 0) or answer 0; rs_global := g; h = dos_open(it, 0);
                         read 36 bytes of header into $c86c; n = its rsh_rssize; rs_hdr := dos_alloc(n);
                         seek 0; read n bytes into rs_hdr; do_rsfix(rs_hdr, n) — each step only while AES_DOS_ERR is
                         clear; then dos_close(h) whatever happened; answer !AES_DOS_ERR
    rs_load(g, name):    rs_readit; if it read one, rs_fixit(g)

REAL FILES over REAL GEMDOS (`test/aes_shell.py`): the ROM's own resources as its bundle stores them — the AES's, the
desk's — and an application's built by shape, found as given, down PATH, or not at all; a header claiming nothing and a
file cut short of its header's length. The SCRIPTED trap answers what no disk does: an open, a read, a Malloc that
fails — and prices the full load at Tier 3, the file's bytes staged where the script's Malloc answers (a scripted read
moves nothing).
"""
import struct

import pytest

from harness import addrs

import aes
import aes_resource as rs
import aes_shell as sh
import gemdos_process as process
import vdi
from case import merge_pokes

GLOBAL = rs.APP_GLOBAL
HEADER_COPY = aes.AES_RS_HEADER_COPY
STALE_HEADER_COPY = {HEADER_COPY: bytes([vdi.FILL]) * aes.RSH_BYTES}
STALE_RESOURCE = rs.STALE_GLOBALS
EFILNF, EIHNDL = aes.signed(process.GEMDOS_EFILNF, 32), aes.signed(addrs.GEMDOS_EIHNDL, 32)
GEMDOS_OK = 0
# Where the snapshot's GEMDOS answers the load's Malloc — the first fit of its free list, measured by the real runs
# below — and where the scripted rows stage the file the script's read stands for.
FIRST_FIT = 0x1_DDE2
SCRIPTED_HANDLE = sh.SCRIPTED_HANDLE
# The caller's global[] FILLed but its header slot (global[7..8]): the first fit, all zero in the snapshot — a resource
# of nothing — so an rs_fixit made after a failed load relocates nothing, and is seen by what it stores rather than by
# a wild pointer.
STALE_GLOBAL = merge_pokes({GLOBAL: bytes([vdi.FILL]) * rs.GLOBAL_BYTES},
                           {GLOBAL + aes.AES_GLOBAL_PMEM: struct.pack(">I", FIRST_FIT)})


def machine(name, pokes=None):
    return merge_pokes(sh.spec(name), sh.working_path(), STALE_GLOBAL, STALE_HEADER_COPY, STALE_RESOURCE, pokes)


def load(routine, name, strings=None, *, through_line_f=False, tag=0):
    """`routine` over the staged disk; `tag` a top byte on both its pointers."""
    pokes = machine(name, sh.environment(*strings) if strings else None)
    return sh.run_real(routine, (GLOBAL | tag, sh.SPEC_AT | tag), pokes, through_line_f=through_line_f,
                       max_insns=LOAD_INSNS)


# The desk's file relocated, through real GEMDOS: ~150,000 instructions on the ROM's side.
LOAD_INSNS = 2_000_000


def model_header(contents):
    return dict(zip(rs.HEADER_FIELDS, struct.unpack(f">{len(rs.HEADER_FIELDS)}H", contents[:aes.RSH_BYTES])))


def loaded_where(result):
    """`(header, length)` the load left in the caller's global[]: global[7..8], global[9]."""
    return result.long(GLOBAL + aes.AES_GLOBAL_PMEM), result.word(GLOBAL + aes.AES_GLOBAL_LMEM)


FILES = {    # (the spec, the environment, the file's bytes)
    "the AES's own, as given": ("GEM.RSC", None, sh.GEM_FILE),
    "the desk's, with ICONBLKs": ("A:\\DESK.RSC", None, sh.DESK_FILE),
    "an application's, down PATH": ("APP.RSC", ("PATH=", "A:\\SUBDIR"), sh.APP_FILE),
}


@pytest.mark.parametrize("routine", (sh.RS_READIT, sh.RS_LOAD), ids=("rs_readit", "rs_load"))
@pytest.mark.parametrize("name, strings, contents", FILES.values(), ids=FILES)
def test_a_resource_file_is_read_whole_and_relocated(routine, name, strings, contents):
    """Read into the block the snapshot's GEMDOS hands out, its header and length into the caller's global[], its
    tree table relocated (global[5..6] and every tree pointer) — and the rest compared byte for byte, the objects'
    coordinates rs_load's alone."""
    result = load(routine, name, strings)
    header = model_header(contents)
    assert result.answer() == 1
    assert loaded_where(result) == (FIRST_FIT, header["rssize"])
    assert result.after(HEADER_COPY, aes.RSH_BYTES) == contents[:aes.RSH_BYTES]
    table = FIRST_FIT + header["trindex"]
    assert result.long(GLOBAL + aes.AES_GLOBAL_PTREE) == table
    assert [result.long(table + tree * aes.LONG_BYTES) for tree in range(header["ntree"])] == [
        FIRST_FIT + struct.unpack_from(">I", contents, header["trindex"] + tree * aes.LONG_BYTES)[0]
        for tree in range(header["ntree"])]
    assert [result.field("AES", field) for field in ("RS_GLOBAL", "RS_HDR")] == [GLOBAL, FIRST_FIT]


@pytest.mark.parametrize("routine", (sh.RS_READIT, sh.RS_LOAD), ids=("rs_readit", "rs_load"))
def test_a_file_not_found_is_not_opened_and_leaves_the_aes_s_own_resource_current(routine):
    """Nothing opened or read — but the walk down PATH asked rs_str for "PATH=", whose rs_sglobal made the AES's OWN
    resource current: the resource globals are the AES's, not the caller's and not as they were."""
    result = load(routine, "NOPE.RSC")
    assert result.answer() == 0
    assert [result.field("AES", field) for field in ("RS_GLOBAL", "RS_HDR")] == [rs.GEM_GLOBAL, rs.GEM_HEADER]
    assert result.after(HEADER_COPY, aes.RSH_BYTES) == bytes([vdi.FILL]) * aes.RSH_BYTES


@pytest.mark.parametrize("routine", (sh.RS_READIT, sh.RS_LOAD), ids=("rs_readit", "rs_load"))
def test_the_caller_s_pointers_are_on_the_24_bit_bus(routine):
    result = load(routine, "GEM.RSC", tag=aes.BUS_TAG)
    assert result.answer() == 1
    assert loaded_where(result) == (FIRST_FIT, model_header(sh.GEM_FILE)["rssize"])


@pytest.mark.parametrize("routine", (sh.RS_READIT, sh.RS_LOAD), ids=("rs_readit", "rs_load"))
def test_through_line_f(routine):
    assert load(routine, "GEM.RSC", through_line_f=True).answer() == 1


def test_a_header_claiming_nothing_loads_nothing_and_succeeds():
    """rsh_rssize 0: Malloc(0) — which this GEMDOS answers with a block — a read of 0 bytes, and a relocation of what
    the block held: the snapshot's free RAM, every count 0."""
    result = load(sh.RS_LOAD, "NOTHING.RSC")
    assert result.answer() == 1
    assert loaded_where(result) == (FIRST_FIT, 0)


def test_a_file_cut_short_of_its_header_reads_what_there_is():
    """A read that comes up short is no error: the load relocates the header's whole length over what it got."""
    result = load(sh.RS_LOAD, "CUT.RSC")
    assert result.answer() == 1
    assert loaded_where(result) == (FIRST_FIT, len(sh.GEM_FILE))
    assert result.after(FIRST_FIT + aes.RSH_BYTES, sh.CUT_BYTES - aes.RSH_BYTES) != sh.CUT_FILE[aes.RSH_BYTES:], \
        "relocated in place"


# ---- the SCRIPTED trap: the failures no disk gives --------------------------------------------------------------------
# A script: Fsetdta, Fsfirst (found), Fopen (the handle), then what the case says; every load ends in one Fclose.
FOUND = [GEMDOS_OK, GEMDOS_OK]


def scripted(routine, after_found, pokes=None, **kwargs):
    return sh.run_scripted(routine, (GLOBAL, sh.SPEC_AT), [*FOUND, *after_found], machine("GEM.RSC", pokes),
                           max_insns=LOAD_INSNS, **kwargs)


def functions(result):
    return [function for function, _frame in sh.calls(result.final)]


OPENED = [addrs.GEMDOS_FSETDTA_FN, addrs.GEMDOS_FSFIRST_FN, addrs.GEMDOS_FOPEN_FN]


def test_a_failed_open_closes_handle_0():
    """dos_open answers 0 when it failed, and the load closes whatever it answered."""
    result = scripted(sh.RS_READIT, [EFILNF, EIHNDL])
    assert sh.calls(result.final)[len(OPENED):] == [(addrs.GEMDOS_FCLOSE_FN, sh.frame(("w", 0)))]
    assert result.answer() == 0
    assert result.field("AES", "RS_GLOBAL") == GLOBAL, "made current before the open"


def test_a_failed_header_read_stops_before_the_malloc():
    result = scripted(sh.RS_READIT, [SCRIPTED_HANDLE, EIHNDL, GEMDOS_OK])
    assert functions(result) == [*OPENED, addrs.GEMDOS_FREAD_FN, addrs.GEMDOS_FCLOSE_FN]
    assert result.answer() == 0


def header_copy(contents):
    return {HEADER_COPY: contents[:aes.RSH_BYTES]}


def test_a_failed_malloc_stores_its_0_and_stops():
    """dos_alloc's 0 is STORED in rs_hdr before it is tested."""
    result = scripted(sh.RS_READIT, [SCRIPTED_HANDLE, aes.RSH_BYTES, 0, GEMDOS_OK], header_copy(sh.GEM_FILE))
    assert functions(result) == [*OPENED, addrs.GEMDOS_FREAD_FN, addrs.GEMDOS_MALLOC_FN, addrs.GEMDOS_FCLOSE_FN]
    assert result.field("AES", "RS_HDR") == 0
    assert result.answer() == 0


def test_a_failed_read_of_the_file_is_not_relocated():
    """The seek's answer is not checked; the read's is — and its failure leaves the block as it was."""
    pokes = merge_pokes(header_copy(sh.GEM_FILE), {FIRST_FIT: sh.GEM_FILE})
    result = scripted(sh.RS_LOAD, [SCRIPTED_HANDLE, aes.RSH_BYTES, FIRST_FIT, EIHNDL, EIHNDL, GEMDOS_OK], pokes)
    assert functions(result) == [*OPENED, addrs.GEMDOS_FREAD_FN, addrs.GEMDOS_MALLOC_FN, addrs.GEMDOS_FSEEK_FN,
                                 addrs.GEMDOS_FREAD_FN, addrs.GEMDOS_FCLOSE_FN]
    assert result.after(FIRST_FIT, len(sh.GEM_FILE)) == sh.GEM_FILE
    assert result.answer() == 0


def full_load(contents):
    """The script of a whole load of `contents`, staged where the script's Malloc answers."""
    answers = [SCRIPTED_HANDLE, aes.RSH_BYTES, FIRST_FIT, GEMDOS_OK, len(contents), GEMDOS_OK]
    return answers, merge_pokes(header_copy(contents), {FIRST_FIT: contents})


@pytest.mark.parametrize("routine", (sh.RS_READIT, sh.RS_LOAD), ids=("rs_readit", "rs_load"))
def test_the_scripted_whole_load_is_the_disk_s(routine):
    """The Tier 3 rows' script, which stands for a whole read: the calls, and their frames — the count a word, the seek
    from the start, the handle closed."""
    answers, pokes = full_load(sh.DESK_FILE)
    result = scripted(routine, answers, pokes)
    assert sh.calls(result.final)[len(OPENED):] == [
        (addrs.GEMDOS_FREAD_FN, sh.frame(("w", SCRIPTED_HANDLE), ("l", aes.RSH_BYTES), ("l", HEADER_COPY))),
        (addrs.GEMDOS_MALLOC_FN, sh.frame(("l", len(sh.DESK_FILE)))),
        (addrs.GEMDOS_FSEEK_FN, sh.frame(("l", 0), ("w", SCRIPTED_HANDLE), ("w", 0))),
        (addrs.GEMDOS_FREAD_FN, sh.frame(("w", SCRIPTED_HANDLE), ("l", len(sh.DESK_FILE)), ("l", FIRST_FIT))),
        (addrs.GEMDOS_FCLOSE_FN, sh.frame(("w", SCRIPTED_HANDLE)))]
    assert result.answer() == 1


aes.declare_case_field(FIRST_FIT, len(sh.DESK_FILE), "the block the snapshot's GEMDOS answers a load's Malloc with")


# ---- the registry ---------------------------------------------------------------------------------------------------
# Over the scripted trap. The WORST realistic load is a FAILED one: the header's read failing, after the find and the
# open — the C's own share of a load is the glue and the walk, where the ROM's is about level with it, and a whole load
# adds the relocation, where the C is about five times the ROM's speed and the ratio falls (0.19 for the desk's).
# So both are rows: the failure as the bar's, the desk's resource whole — the largest the ROM has (9,130 bytes;
# ICONBLKs, TEDINFOs, BITBLKs, free strings), staged where the script's Malloc answers — as the load it is for.
_ANSWERS, _POKES = full_load(sh.DESK_FILE)
for _routine in (sh.RS_READIT, sh.RS_LOAD):
    aes.register("the header's read fails", _routine, (GLOBAL, sh.SPEC_AT),
                 sh.scripted_machine([*FOUND, SCRIPTED_HANDLE, EIHNDL, GEMDOS_OK], machine("GEM.RSC")),
                 hook=sh.scripted_hook)
    aes.register("the desk's resource, whole", _routine, (GLOBAL, sh.SPEC_AT),
                 sh.scripted_machine([*FOUND, *_ANSWERS], machine("GEM.RSC", _POKES)), hook=sh.scripted_hook)
