r"""LOADING A PROGRAM — `Pexec` modes 3 and 0 end to end, and the loader under them ($fc85ea).
`src/gemdos/pexec_load.c`, `src/gemdos/process.c`, over `test/fs_pexec.py`'s programs.

    $fc81b0  jsr   $fc6d14        ; sfirst(name, 0, no DTA): EFILNF before anything is cut
    $fc84d0  bsr   $fc85ea        ; the loader, into the basepage mode 5's half just cut
    $fc84e2  bsr   $fc8092        ; ...and on its error, the CHILD released
    $fc85f6  jsr   $fc75f2        ; Fopen(name, <the high half of the caller's D5>)
    $fc8626  cmpi.w #$601a        ; the magic, and EPLFMT
    $fc8702  cmp.l                ; the BSS against what TEXT and DATA leave: ENSMEM
    $fc8786  jsr   $fc7cce        ; Fseek over the symbol table, the answer ignored
    $fc87b8  ...                  ; the first fixup, and each chunk, checked against TEXT+DATA
    $fc884c  jsr   $fc4b7c        ; the TPA past DATA cleared, all of it
    $fc8858  jsr   $fc56c6        ; Fclose — on this arm only

THREE CASE SHAPES. The LOOKUP is `Pexec`'s own arm before the termination record it arms, so a
missing program is a whole-function differential of `$fc817a`. Everything past it is the SLICE at
`$fc8242` (`test/gemdos_process.py`): mode 3 whole to its `rts`, and mode 0 either returning its load's
error or GOING — a checkpoint at the `jsr` into the trap epilogue. And the loader at its own address,
over a basepage a real `Pexec(5)` cut (`fs_pexec.created`, carried by `gemdos_fs.continued`).

Every run compares the whole image, which for a load is the whole TPA: the basepage, the relocated
TEXT and DATA, the BSS and everything the clear reaches, the pool, the handle table, the OFD the open
built and the cache the reads went through. What a case asserts on top is the claim it is ABOUT.
"""
import struct

import pytest

from harness import BASE_IMAGE, addrs, emu, make_image

import case
import fs_dir as d
import fs_file as ff
import fs_io as io
import fs_pexec as px
import gemdos_fs as fs
import gemdos_memory as gm
import gemdos_process as process

LOAD, GO = process.PEXEC_LOAD, process.PEXEC_LOAD_AND_GO
EACCDN = fs.GEMDOS_EACCDN
ENHNDL = process.GEMDOS_ENHNDL


def loaded_bytes(result, one):
    """TEXT and DATA as the run left them."""
    return result.after(px.TEXT, len(one.text) + len(one.data))


def hitpa(result, basepage=px.BASEPAGE):
    return result.long(basepage + addrs.BASEPAGE_HITPA)


def end_of_data(one):
    return px.TEXT + len(one.text) + len(one.data)


def block_owner(result, start):
    return next(md.owner for md in gm.allocated_list(result.final) if md.start == start)


# ================================================================================================
# The lookup — `$fc817a`'s own arm, before its record
# ================================================================================================

def _lookup_pokes(mode, name):
    return {**px.machine(name=None), **d.text(name),
            **process.pexec_args(mode, d.TEXT_AT, process.COMMAND_TAIL_AT, process.ENVIRONMENT_AT)}


def _lookup(mode, name):
    return io.run(addrs.GEMDOS_PEXEC,
                  lambda lib, buf: lib.gemdos_pexec(buf, mode, d.TEXT_AT, process.COMMAND_TAIL_AT,
                                                    process.ENVIRONMENT_AT),
                  _lookup_pokes(mode, name))


@pytest.mark.parametrize("mode", (LOAD, GO))
@pytest.mark.parametrize("name,why", (
    ("A:\\NOPE.PRG", "a name the directory has not got"),
    ("A:\\NOPE\\HELLO.PRG", "a directory the path has not got — EFILNF too"),
    ("A:\\SECRET.PRG", "a HIDDEN program: `sfirst`'s attribute 0 widens to plain, read-only and archived"),
))
def test_a_program_the_lookup_cannot_find_is_efilnf_before_anything_is_cut(mode, name, why):
    """`sfirst(name, 0, 0)` and `tst.w d0`: any miss, before the record is saved or a byte of memory cut —
    so the pool and the handle table come out as they went in."""
    result = _lookup(mode, name)
    assert result.info["ret"] == px.EFILNF, why
    assert gm.free_list(result.final) == gm.free_list(make_image(result.staged)), why
    assert not px.open_handles(result), why


def test_the_loader_opens_the_hidden_program_the_lookup_refuses():
    """...and the other half of that disagreement: the loader's `Fopen` searches every file attribute, so
    handed the same name directly it loads it. `Pexec` never gets that far."""
    result = px.load(px.created(), name="SECRET")
    assert result.info["ret"] == 0
    assert loaded_bytes(result, px.BY_NAME["SECRET"]) == px.relocated(
        px.HELLO_TEXT + px.HELLO_DATA, px.HELLO_FIXUPS, px.TEXT)


# ================================================================================================
# Mode 3 — a program loaded and relocated
# ================================================================================================

def test_mode_3_loads_and_relocates_a_program_and_answers_its_basepage():
    """Every fixup of the stream — three in TEXT, one in DATA — has the TEXT base added, and nothing else
    of TEXT or DATA moves. The symbol table is skipped: its bytes, read as a stream, would fix a longword
    every two bytes."""
    result = px.pexec(LOAD, px.HELLO)
    assert result.info["ret"] == px.BASEPAGE
    assert loaded_bytes(result, px.HELLO) == px.relocated(px.HELLO_TEXT + px.HELLO_DATA, px.HELLO_FIXUPS,
                                                          px.TEXT)


def test_the_basepage_publishes_each_segment_s_base_and_length():
    """One loop over the three lengths: each base is the one before plus its length, from the end of the
    basepage."""
    result = px.pexec(LOAD, px.HELLO)
    tlen, dlen, blen = len(px.HELLO_TEXT), len(px.HELLO_DATA), px.HELLO.bss
    assert px.segments(result) == (px.TEXT, tlen, px.TEXT + tlen, dlen, px.TEXT + tlen + dlen, blen)


def test_the_whole_tpa_past_data_is_cleared_not_just_the_bss():
    """`$fc4b7c(end, end + room)`: from the end of DATA to `p_hitpa`, which is the relocation buffer and
    the BSS and everything past both — over a TPA staged dirty."""
    result = px.pexec(LOAD, px.HELLO)
    end = end_of_data(px.HELLO)
    assert hitpa(result) - end > process.BASEPAGE_BYTES, "the clear never reached its block arm"
    assert not any(result.after(end, hitpa(result) - end))


def test_the_file_is_closed_and_the_blocks_stay_the_caller_s():
    """The one arm that closes the file; and mode 3 hands the basepage BACK, so the TPA is charged to the
    caller and `p_run` has not moved."""
    result = px.pexec(LOAD, px.HELLO)
    assert not px.open_handles(result)
    assert block_owner(result, px.BASEPAGE) == ff.P_RUN
    assert result.long(addrs.GEMDOS_P_RUN) == ff.P_RUN


def test_a_program_with_no_relocation_loads_as_the_file_holds_it():
    """A first offset of 0: nothing after it is read."""
    one = px.BY_NAME["PLAIN"]
    result = px.pexec(LOAD, one)
    assert result.info["ret"] == px.BASEPAGE
    assert loaded_bytes(result, one) == one.text + one.data


def test_a_first_fixup_at_text_zero_cannot_be_said():
    """The same 0 is the stream's "no relocation": a program whose first fixup is TEXT+0 is loaded with
    NEITHER of its fixups applied."""
    one = px.BY_NAME["ZERO"]
    result = px.pexec(LOAD, one)
    assert loaded_bytes(result, one) == one.text + one.data


def test_a_distance_over_254_is_carried_by_skip_bytes_that_fix_nothing():
    one = px.BY_NAME["FAR"]
    assert px.PRG_SKIP in one.relocation[px.LONG_BYTES:-1]
    result = px.pexec(LOAD, one)
    assert loaded_bytes(result, one) == px.relocated(one.text, (0x002, 0x2f8), px.TEXT)


def test_an_odd_length_text_and_data_starts_the_clear_on_an_odd_byte():
    """`btst #0` then one `move.b`: the BSS starts odd and its first byte is cleared on its own."""
    one = px.BY_NAME["ODD"]
    result = px.pexec(LOAD, one)
    end = end_of_data(one)
    assert end & 1 and px.segments(result)[4] == end
    assert not any(result.after(end, hitpa(result) - end))


def test_the_program_flags_are_read_and_ignored():
    """TOS 1.02 reads the longword and then the flags into ONE local and looks at neither: a fast-load
    program's TPA is cleared all the same."""
    one = px.BY_NAME["FLAGS"]
    result = px.pexec(LOAD, one)
    end = end_of_data(one)
    assert loaded_bytes(result, one) == px.relocated(one.text + one.data, px.HELLO_FIXUPS, px.TEXT)
    assert not any(result.after(end, hitpa(result) - end))


def test_a_symbol_table_past_the_end_of_the_file_is_an_ignored_erange():
    """The `Fseek` over an OVERCLAIMED symbol table fails, and the cursor stays where the TEXT+DATA read
    left it — which is where this file's relocation stream really is, so it loads right."""
    one = px.BY_NAME["OVERSYM"]
    result = px.pexec(LOAD, one)
    assert result.info["ret"] == px.BASEPAGE
    assert loaded_bytes(result, one) == px.relocated(one.text + one.data, px.HELLO_FIXUPS, px.TEXT)


def test_a_stream_with_no_end_byte_simply_runs_out():
    one = px.BY_NAME["NOEND"]
    result = px.pexec(LOAD, one)
    assert result.info["ret"] == px.BASEPAGE
    assert loaded_bytes(result, one) == px.relocated(one.text + one.data, px.HELLO_FIXUPS, px.TEXT)


def test_a_first_fixup_two_bytes_short_of_data_s_end_fixes_across_it():
    """`bcs` against the END of DATA, so a first fixup at end-2 is admitted — and the longword it adds to
    runs two bytes into the relocation buffer, which still holds the TPA's own bytes. The carry out of
    that low half reaches DATA's last word; the stream and the clear then overwrite the other half."""
    one = px.BY_NAME["STRADDLE"]
    result = px.pexec(LOAD, one)
    before = struct.unpack(">I", one.data[-2:] + bytes([fs.SLACK_FILL]) * 2)[0]
    assert result.after(end_of_data(one) - 2, 2) == struct.pack(">I", (before + px.TEXT) & fs.LONG_MASK)[:2]


def test_a_fixup_inside_a_chunk_is_applied_past_the_tpa_unchecked():
    """The bound is checked at the first fixup and between chunks, never at a fixup: this stream's second
    one lands past `p_hitpa`, outside the TPA altogether, and is applied there."""
    one = px.BY_NAME["WILD"]
    result = px.pexec(LOAD, one)
    wild = px.TEXT + px.WILD_FIXUPS[-1]
    assert wild >= hitpa(result)
    assert result.long(wild) == (case.long_in(BASE_IMAGE, wild) + px.TEXT) & fs.LONG_MASK


def test_skip_bytes_walk_the_cursor_past_data_unchecked_inside_a_chunk():
    """...and three SKIP bytes carry it past DATA with no fixup and so no check; the fixup after them
    lands inside the TPA's clear and is wiped with it."""
    one = px.BY_NAME["WALK"]
    result = px.pexec(LOAD, one)
    assert result.info["ret"] == px.BASEPAGE


# ---- the relocation stream in chunks ------------------------------------------------------------------

MANY = px.BY_NAME["MANY"]
MANY_FIXUPS = range(4, 0x50, 4)
MANY_STREAM = len(MANY.relocation) - px.LONG_BYTES     # the bytes after the first offset, the 0 included


def _tpa_leaving(one, room):
    return process.BASEPAGE_BYTES + len(one.text) + len(one.data) + room


@pytest.mark.parametrize("room", (4, 5, MANY_STREAM - 1, MANY_STREAM),
                         ids=("chunks of 4", "chunks of 5", "the 0 alone in the last chunk", "one exact chunk"))
def test_a_stream_longer_than_the_room_left_is_read_in_chunks(room):
    """The stream is read into the TPA past DATA, `room` bytes at a time; a chunk read EXACTLY full is
    followed by another, checked against TEXT+DATA first. Every fixup lands however the stream is cut."""
    result = px.pexec(LOAD, MANY, tpa_bytes=_tpa_leaving(MANY, room))
    assert result.info["ret"] == px.BASEPAGE
    assert loaded_bytes(result, MANY) == px.relocated(MANY.text + MANY.data, MANY_FIXUPS, px.TEXT)


def test_a_cursor_past_data_at_a_chunk_boundary_is_eplfmt():
    """WALK's skip bytes, read two at a time: the first chunk walks the cursor past DATA, and the check
    before the second refuses it."""
    one = px.BY_NAME["WALK"]
    result = px.pexec(LOAD, one, tpa_bytes=_tpa_leaving(one, 2))
    assert result.info["ret"] == px.EPLFMT


# ================================================================================================
# What the loader refuses, and what a refusal leaves behind
# ================================================================================================

def test_a_bad_magic_is_eplfmt_with_the_file_left_open_and_the_tpa_left_allocated():
    """Two leaks in one refusal. The loader returns with its file OPEN, the handle charged to the caller;
    and the release of the CHILD gives back what the child owns — which in mode 3 is not its TPA or its
    environment, both charged to the caller. Nothing is published in the basepage."""
    result = px.pexec(LOAD, px.BY_NAME["NOTPRG"])
    assert result.info["ret"] == px.EPLFMT
    assert px.open_handles(result) == [(ff.A_HANDLE, ff.P_RUN)]
    assert block_owner(result, px.BASEPAGE) == ff.P_RUN
    assert px.segments(result) == (0,) * 6


@pytest.mark.parametrize("name", ("ATEND", "BEFORE"))
def test_a_first_fixup_outside_text_and_data_is_eplfmt_after_the_segments_are_published(name):
    """At the end of DATA (`bcs`, so equal is out) and before TEXT (`blt`, signed: an offset of -2). The
    basepage is filled and TEXT and DATA read before the stream is looked at, and neither is undone."""
    one = px.BY_NAME[name]
    result = px.pexec(LOAD, one)
    assert result.info["ret"] == px.EPLFMT
    assert px.segments(result)[0] == px.TEXT
    assert loaded_bytes(result, one) == one.text + one.data
    assert px.open_handles(result) == [(ff.A_HANDLE, ff.P_RUN)]


def test_a_bss_that_does_not_fit_is_ensmem_before_anything_is_read():
    tpa = _tpa_leaving(px.HELLO, px.HELLO.bss - 2)
    result = px.pexec(LOAD, px.HELLO, tpa_bytes=tpa)
    assert result.info["ret"] == px.ENSMEM
    assert px.segments(result) == (0,) * 6
    assert px.open_handles(result) == [(ff.A_HANDLE, ff.P_RUN)]


def test_a_bss_that_exactly_fits_loads():
    result = px.pexec(LOAD, px.HELLO, tpa_bytes=_tpa_leaving(px.HELLO, px.HELLO.bss))
    assert result.info["ret"] == px.BASEPAGE


def test_text_and_data_bigger_than_the_tpa_are_ensmem_through_a_signed_compare():
    """What is left is NEGATIVE, and a BSS of 0 is more than that."""
    one = px.BY_NAME["FAR"]
    result = px.pexec(LOAD, one, tpa_bytes=process.BASEPAGE_BYTES + len(one.text) // 2)
    assert result.info["ret"] == px.ENSMEM


def test_the_absolute_flag_loads_and_returns_without_relocating_clearing_or_closing():
    one = px.BY_NAME["ABS"]
    result = px.pexec(LOAD, one)
    end = end_of_data(one)
    assert result.info["ret"] == px.BASEPAGE
    assert loaded_bytes(result, one) == one.text + one.data
    assert result.after(end, 1) == bytes([fs.SLACK_FILL])
    assert px.open_handles(result) == [(ff.A_HANDLE, ff.P_RUN)]


def test_a_file_shorter_than_its_header_claims_loads_what_there_is():
    """No `Fread` answer is looked at: TEXT is claimed at $200 bytes, the file holds far less, and the
    load succeeds (this one absolute, so it ends there) with the claimed lengths published."""
    one = px.BY_NAME["SHORT"]
    result = px.pexec(LOAD, one)
    assert result.info["ret"] == px.BASEPAGE
    assert px.segments(result)[1] == 0x200
    assert result.after(px.TEXT, len(one.text) + len(one.data)) == one.text + one.data


# THE ROM LOADER'S FIRST-FIXUP LOCAL, `-38(a6)`, where a case entering the loader at its own address finds it:
# `emu.run` plants the return address at `emu.STACK_TOP` and the `link` saves A6 under it.
LOADER_FRAME_AT = emu.STACK_TOP - px.LONG_BYTES
FIRST_FIXUP_LOCAL = -38
# A first offset no TPA here reaches, and the one that means "no relocation".
STALE_OUTSIDE = 0x0008_0007
STALE_NONE = 0


@pytest.mark.parametrize("stale,expected", ((STALE_OUTSIDE, px.EPLFMT), (STALE_NONE, 0)),
                         ids=("a stale offset past TEXT+DATA", "a stale 0"))
def test_a_short_file_s_relocation_offset_is_a_frame_local_nothing_wrote(stale, expected):
    """AN ORACLE CLAIM, and the reason it cannot be a differential. Without the absolute flag the short
    file's relocation offset is read at the end of the file — `Fread` moves nothing — and the loader
    relocates by whatever its frame local `-38(a6)` already held. Entered at its own address, nothing the
    run does reaches that byte before the read, so the case STAGES it — and what it stages decides: an
    offset past TEXT+DATA is EPLFMT with the file left open, a 0 is a load with nothing relocated. Our
    core's local is a host slot with other bytes in it, so the two shores would differ by construction."""
    pokes = {**px.load_pokes(px.created(name="TRUNC")),
             LOADER_FRAME_AT + FIRST_FIXUP_LOCAL: struct.pack(px.LONG, stale)}
    final, _writes, regs = emu.run(make_image(fs.machine(io.engine(pokes))), addrs.GEMDOS_PEXEC_LOAD,
                                   {"a5": 0, "d5": px.READING_D5})
    assert regs["d0"] == expected
    if expected == px.EPLFMT:
        assert process.descriptor(final, ff.A_HANDLE).owner == ff.P_RUN


@pytest.mark.parametrize("d5,expected", ((px.READING_D5, px.BASEPAGE), (px.WRITING_D5, EACCDN)),
                         ids=("a caller D5 whose high half is 0", "one whose high half is not"))
def test_the_open_mode_is_the_high_half_of_the_caller_s_d5(d5, expected):
    """The loader's `Fopen` pushes no mode, and reads the high half of the D5 its own `movem` saved —
    the trapping caller's. So a READ-ONLY program loads or is EACCDN depending on a register the caller
    never meant to pass."""
    result = px.pexec(LOAD, px.BY_NAME["LOCKED"], d5=d5)
    assert result.info["ret"] == expected


@pytest.mark.parametrize("d5,d4,expected", ((px.READING_D5, px.WRITING_D5, px.BASEPAGE),
                                            (px.WRITING_D5, px.READING_D5, EACCDN)),
                         ids=("D5 reading, D4 writing", "D5 writing, D4 reading"))
def test_the_open_mode_is_read_out_of_the_frame_the_rom_s_trap_entry_built(d5, d4, expected):
    """The same claim with NOTHING of it poked at our own offset: the frame is the one the original's trap
    entry builds for a caller entering with these D4 and D5 (`fs_pexec.trap_frame`), and D4 beside D5
    holds the other mode — so a core reading the frame one slot off loads where the ROM refuses, or the
    other way about."""
    frame = px.trap_frame(d5, d4)
    assert frame[px.CALLER_FRAME][addrs.GEMDOS_SAVED_FRAME_D5 - addrs.GEMDOS_SAVED_REGISTER_BYTES:] \
        .startswith(struct.pack(">II", d4, d5)), "the ROM's frame does not hold D4 and D5 side by side"
    result = px.pexec(LOAD, px.BY_NAME["LOCKED"], d5=d5, frame=frame)
    assert result.info["ret"] == expected


def test_a_plain_program_opened_with_a_write_mode_still_loads():
    """...and a plain one loads either way, with the mode word stored in its OFD — which the image
    compare holds our core to."""
    assert px.pexec(LOAD, px.HELLO, d5=px.WRITING_D5).info["ret"] == px.BASEPAGE


def test_no_handle_for_the_program_is_enhndl_and_the_child_is_released():
    """`Fopen`'s own answer, sign-extended from its word, and the child's inherited directories given
    back: the release runs on every refusal."""
    result = px.pexec(LOAD, px.HELLO, pokes=process.full_table_poke(ff.SOMEBODY_ELSE))
    assert result.info["ret"] == ENHNDL
    for node in {BASE_IMAGE[ff.P_RUN + addrs.BASEPAGE_CURDIR + entry] for entry in range(addrs.BASEPAGE_CURDIR_ENTRIES)}:
        if node:
            assert process.directory_refcount(result.final, node) == process.directory_refcount(BASE_IMAGE, node)


# ================================================================================================
# Mode 0 — load and go
# ================================================================================================

def test_mode_0_loads_relocates_and_makes_the_child_the_running_process():
    """The checkpoint at the `jsr` into the trap epilogue: the program relocated, the child `p_run` with
    the caller its parent, and its stack's entry point the TEXT base."""
    result = px.pexec_and_go(px.HELLO)
    assert loaded_bytes(result, px.HELLO) == px.relocated(px.HELLO_TEXT + px.HELLO_DATA, px.HELLO_FIXUPS,
                                                          px.TEXT)
    assert result.long(addrs.GEMDOS_P_RUN) == px.BASEPAGE
    assert result.long(px.BASEPAGE + addrs.BASEPAGE_PARENT) == ff.P_RUN
    assert block_owner(result, px.BASEPAGE) == px.BASEPAGE
    assert result.long(process.child_entry_at(hitpa(result))) == px.TEXT


def test_a_mode_0_load_that_fails_gives_the_child_s_blocks_back():
    """...where mode 3's did not: mode 0 charged the TPA and the environment to the CHILD, so its release
    returns both to the free list. The file is left open either way, charged to the caller."""
    result = px.pexec(GO, px.BY_NAME["NOTPRG"])
    assert result.info["ret"] == px.EPLFMT
    assert not [md for md in gm.allocated_list(result.final) if md.owner == px.BASEPAGE]
    assert sum(md.length for md in gm.free_list(result.final)) == px.ENVIRONMENT_BLOCK + px.TPA_BYTES
    assert px.open_handles(result) == [(ff.A_HANDLE, ff.P_RUN)]


# ================================================================================================
# The loader at its own address
# ================================================================================================

def test_the_loader_over_a_basepage_pexec_5_cut():
    result = px.load(px.created())
    assert result.info["ret"] == 0
    assert loaded_bytes(result, px.HELLO) == px.relocated(px.HELLO_TEXT + px.HELLO_DATA, px.HELLO_FIXUPS,
                                                          px.TEXT)


def test_the_loader_answers_fopen_s_own_error_for_a_name_it_cannot_open():
    """The sign-extended word `Fopen` answered, as the loader's own answer — with nothing read."""
    result = px.load(px.created(), name="NOPE")
    assert result.info["ret"] == px.EFILNF
    assert px.segments(result) == (0,) * 6


def test_the_loader_s_open_mode_is_its_own_entry_d5():
    result = px.load(px.created(), d5=px.WRITING_D5, name="LOCKED")
    assert result.info["ret"] == EACCDN


# ---- the registry --------------------------------------------------------------------------------

def _register_all():
    io.register("gemdos_pexec, a program that is not there", addrs.GEMDOS_PEXEC, _lookup_pokes(LOAD, "A:\\NOPE.PRG"))
    px.register_pexec("gemdos_pexec_create, mode 3: a program relocated", LOAD, px.HELLO)
    px.register_pexec("gemdos_pexec_create, mode 3: the stream in chunks", LOAD, MANY,
                      tpa_bytes=_tpa_leaving(MANY, 4))
    px.register_pexec("gemdos_pexec_create, mode 3: not a program", LOAD, px.BY_NAME["NOTPRG"])
    px.register_load("gemdos_pexec_load, a program relocated", px.created())


_register_all()
