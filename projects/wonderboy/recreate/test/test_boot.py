"""Differential battery for the BOOT CHAIN's first reconstructed tranche (src/boot.c, src/stage.c).

The boot chain is everything from the PRG entry to the `jmp $4a0` that starts the frame loop.
../STATUS.md's batch 44 phase A carries its inventory — 57 routines, machine-checked by
test_boot_inventory.py — and this file verifies the ten this phase reconstructed: nine that are pure
memory, and `clear_palette`, which is pure shifter and so is pinned by what it does NOT write.

WHAT IS PINNED, AND BY WHICH CASES
  * the three block movers (`copy_longs`, `copy_screen`, `clear_both_screens`), on their own
    geometry and on the boot's own operands;
  * `bg_tile_install` and `sprites_cru_install` — THE TWO BOOT PRODUCTS — on the game's own shipped
    resource files, depacked by the game's own depacker, so what is compared is the real tile bank
    and the real sprite cells rather than a synthetic stand-in;
  * the four cell copiers, each entered directly with its own widths and counts;
  * that the copier dispatch table holds the four entries src/boot.c dispatches on, and that no
    shipped descriptor of any stage selects anything but those four (the census that makes
    WB_SPRITE_CRU_UNKNOWN_COPIER a guard on unreachable input rather than an invented branch).

KNOWINGLY NOT PINNED
  * `clear_palette`'s SIXTEEN WRITES, exactly as `set_palette`'s are not (test_stage.py says why at
    length): WB_SHIFTER_PALETTE is off the loaded image, so the oracle drops every one of them. What
    a case can show is that both sides leave the image alone and that a0 comes back where the eight
    post-incremented `clr.l`s leave it. The kit-side remedy — a dropped-hardware-write ledger — is
    registered in ../STATUS.md and is not this batch's work.
  * `bg_tile_install`'s SECOND run. It rewrites the index it read, so running it twice is not the
    same operation twice; nothing in the game does, and no case here claims anything about it.
  * WB_SPRITE_CRU_UNKNOWN_COPIER itself is unreachable and so is verified by census rather than by a
    differential: the original `jsr`s through whatever longword the table held, which is not
    behaviour a port can reproduce and not a run the oracle survives.
"""
import ctypes
import functools

import pytest

import copylock
import harness
import leaf
from layout import wb

import depack_rad                                              # noqa: E402  (harness put tools/ on
import emu                                                     # noqa: E402   sys.path)
import loader                                                  # noqa: E402
import prg_dis                                                 # noqa: E402

BIN = harness.PRG.resolve().parents[2]                # projects/wonderboy/bin (PRG: bin/disk1/AUTO)
DISK2 = "disk2_repaired"

LONGWORD_LEN = 4
WORD_LEN = 2

SCREEN_LOW = wb("SCREEN_LOW")
SCREEN_HIGH = wb("SCREEN_HIGH")
SCREEN_BYTES = wb("SCREEN_BYTES")
SCREEN_CLEAR_LONGS = wb("SCREEN_CLEAR_LONGS")
SCREEN_COPY_LONGS = wb("SCREEN_COPY_LONGS")
SHIFTER_PALETTE = wb("SHIFTER_PALETTE")
PALETTE_ROW_BYTES = wb("PALETTE_ROW_BYTES")
PALETTE_COLOURS = wb("PALETTE_COLOURS")

# Two scratch buffers clear of the program (which ends at $218d0) and of the kit's staged-file table.
# test_rad_depack.py lays its two out at the same pair of addresses for the same reasons.
SRC_AT = 0x40000
DST_AT = 0x80000
POISON = 0x5a                     # what a destination holds before the case runs, so a byte the
                                  # reconstruction never wrote cannot pass by already being right


def _bytes_at(offset, count, seed):
    """`count` deterministic bytes — a source a case can tell apart from anything else in the image."""
    return bytes(((offset + i) * 7 + seed * 31) & 0xff for i in range(count))


def _check_scratch(span):
    """Refuse a case whose scratch buffers overlap each other, the program, or the kit's file table.

    test_rad_depack.py guards its own pair this way and this battery inherited the ADDRESSES without
    the protection — the gap a reviewer found. It matters because both sides of a differential would
    be corrupted IDENTICALLY by such an overlap and the case would come back green.
    """
    assert loader.PROGRAM_END <= SRC_AT, (
        f"SWB.PRG reaches {loader.PROGRAM_END:#x}, past the source buffer at {SRC_AT:#x}")
    assert SRC_AT + span <= DST_AT, (
        f"{span} bytes at {SRC_AT:#x} reach the destination buffer at {DST_AT:#x}")
    assert DST_AT + span <= harness.OS_FS_TABLE, (
        f"{span} bytes at {DST_AT:#x} reach the TOS model's staged-file table at "
        f"{harness.OS_FS_TABLE:#x}")


# --- the entry pins -----------------------------------------------------------------------------
# Each routine's first instruction, so a wrong address in ../names.txt or in include/wonderboy.h
# fails HERE rather than as a puzzling diff. Every one is read out of the loaded image.
ENTRY_INSNS = {
    "copy_longs": b"\x22\xd8",                                   # move.l (a0)+,(a1)+
    "copy_screen": b"\x30\x3c\x1f\x3f",                          # move.w #$1f3f,d0
    "clear_both_screens": b"\x41\xf9\x00\x07\x00\x00",           # lea $70000.l,a0
    "clear_palette": b"\x41\xf9\x00\xff\x82\x40",                # lea $ff8240.l,a0
    "bg_tile_install": b"\x41\xf9\x00\x02\x1e\x90",              # lea $21e90.l,a0
    "sprites_cru_install": b"\x4b\xf9\x00\x02\x48\x98",          # lea $24898.l,a5
    "sprite_cru_copy_5w": b"\x36\xd8",                           # move.w (a0)+,(a3)+
    "sprite_cru_copy_10w": b"\x26\xd8",                          # move.l (a0)+,(a3)+
    "sprite_cru_copy_15w": b"\x36\xd8",
    "sprite_cru_copy_20w": b"\x26\xd8",
    # ...and the load path above the disk seam (batch 44 phase B)
    "load_resource_by_index": b"\x2f\x08",                        # move.l a0,-(a7)
    "stage_actors_init": b"\x41\xf9\x00\x00\x99\x6c",             # lea $996c.l,a0
    "actor_apply_stage_side": b"\x4a\x79\x00\x00\xe7\x0e",         # tst.w $e70e.l
    "stage_sequence_advance": b"\x42\x78\x6e\xf0",                # clr.w $6ef0.w
    "stage_sequence_resource": b"\x70\x00",                      # moveq #0,d0
    "stage_sequence_apply_row": b"\x4a\x28\x00\x02",              # tst.b 2(a0)
}


@pytest.mark.parametrize("name", sorted(ENTRY_INSNS))
def test_the_entry_point_is_the_instruction_this_battery_believes_is_there(name):
    entry = leaf.entry_of(name)
    want = ENTRY_INSNS[name]
    assert bytes(harness.BASE_IMAGE[entry:entry + len(want)]) == want, (
        f"{name} @ {entry:#x} does not start with {want.hex()} — the name map and this battery "
        f"disagree about where it is")


def test_the_screen_pair_and_the_clear_that_crosses_them_agree():
    """WB_SCREEN_CLEAR_LONGS is NOT two screens: it is derived here from the two buffer addresses so
    a reader cannot take the routine's `move.w #$3f3f` for a pair of 32000-byte clears.

    WB_SCREEN_BYTES is cross-pinned against the header's own canonical pair for the reason
    atari/wonderboy_main.c states about the same number: two independent 32000s in one project drift,
    and the on-target frame comparison depends on the other one.
    """
    assert SCREEN_BYTES == wb("SCREEN_LINE") * wb("SCREEN_SCANLINES"), (
        "WB_SCREEN_BYTES and WB_SCREEN_LINE * WB_SCREEN_SCANLINES disagree")
    assert SCREEN_CLEAR_LONGS * LONGWORD_LEN == SCREEN_HIGH + SCREEN_BYTES - SCREEN_LOW
    assert SCREEN_COPY_LONGS * LONGWORD_LEN == SCREEN_BYTES
    assert (SCREEN_LOW, SCREEN_HIGH) == leaf.SCREEN_BUFFERS, (
        "the header's buffer pair and leaf.py's disagree")


# --- copy_longs ($f93c) and copy_screen ($f938) --------------------------------------------------
# Two instructions and four; what a case has to pin is the COUNT convention (`dbf` runs one more
# time than its operand says) and that the two overlapping-buffer directions behave as the 68000's
# ascending `move.l (a0)+,(a1)+` does rather than as a memmove.

_COPY_LONGS = leaf.register_glue("copy_longs", [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint16])
_COPY_SCREEN = leaf.register_glue("copy_screen", [ctypes.c_uint32, ctypes.c_uint32])

# One `move.l` + one `dbf` per longword, plus the `rts` and the runner's sentinel.
COPY_INSN_PER_LONG = 2


def _run_copy_longs(case, src, dst, count_minus_1, seed=0):
    longs = count_minus_1 + 1
    span = longs * LONGWORD_LEN
    _check_scratch(span)
    what = f"copy_longs {case}"
    # POISON FIRST, THEN SEED. The two OVERLAP cases deliberately place dst inside src, and
    # `harness.make_image` applies pokes in insertion order with no overlap check — so writing the
    # source first let the poison overwrite 28 of its 32 distinct bytes, leaving the case to compare
    # two mostly-constant buffers. That is the discriminating power POISON exists to provide,
    # destroyed by the poison itself. Poisoning the destination first and seeding over it keeps
    # every source byte distinct; the bytes of the destination that the source does NOT cover stay
    # poisoned, which is what the attribution pass needs.
    pokes = {dst: bytes([POISON]) * span, src: _bytes_at(src, span, seed)}
    info = leaf.run("copy_longs", _COPY_LONGS(src, dst, count_minus_1), [(dst, span)], what,
                    regs={"a0": src, "a1": dst, "d0": count_minus_1, "_pokes": pokes},
                    max_insns=longs * COPY_INSN_PER_LONG + 1 + leaf.RUNNER_SENTINEL_INSN)
    assert info["regs"]["a0"] == src + span, (
        f"{what}: the original left a0 at {info['regs']['a0']:#x}, so it did not copy {longs} "
        f"longwords")
    assert info["regs"]["a1"] == dst + span
    return info


@pytest.mark.parametrize("count_minus_1", [0, 1, 7, 0x31f])
def test_copy_longs_moves_one_more_longword_than_its_operand_says(count_minus_1):
    """Including $31f, which is the boot's own operand at $e634/$e658 — the 3200-byte save and
    restore that straddle the overlay depack."""
    _run_copy_longs(f"{count_minus_1} + 1 longwords", SRC_AT, DST_AT, count_minus_1)


def test_copy_longs_overlapping_upwards_re_reads_what_it_just_wrote():
    """dst four bytes ABOVE src: an ascending `move.l (a0)+,(a1)+` smears the first longword through
    the whole run, where a memmove would preserve the source. The original's behaviour, and the case
    that would catch a port written with memcpy/memmove."""
    _run_copy_longs("dst one longword above src", SRC_AT, SRC_AT + LONGWORD_LEN, 7, seed=1)


def test_copy_longs_overlapping_downwards_is_a_clean_slide():
    """dst four bytes BELOW src — the direction `sprites_cru_install`'s own slide uses, where the
    ascending copy is safe and the tail of the source is gone by the end."""
    _run_copy_longs("dst one longword below src", SRC_AT + LONGWORD_LEN, SRC_AT, 7, seed=2)


def test_copy_screen_copies_the_boot_s_own_screen():
    """`lea $78000,a0 / lea $70000,a1 / bsr $f938` at $e59a — the credits screen brought down onto
    the buffer the shifter is showing. The count is the routine's own, not this case's."""
    what = "copy_screen $78000 -> $70000"
    pokes = {SCREEN_HIGH: _bytes_at(SCREEN_HIGH, SCREEN_BYTES, 3),
             SCREEN_LOW: bytes([POISON]) * SCREEN_BYTES}
    info = leaf.run("copy_screen", _COPY_SCREEN(SCREEN_HIGH, SCREEN_LOW),
                    [(SCREEN_LOW, SCREEN_BYTES)], what,
                    regs={"a0": SCREEN_HIGH, "a1": SCREEN_LOW, "_pokes": pokes},
                    max_insns=1 + SCREEN_COPY_LONGS * COPY_INSN_PER_LONG + 1
                    + leaf.RUNNER_SENTINEL_INSN)
    written = set(leaf.program_writes(info))
    assert len(written) == SCREEN_BYTES, (
        f"{what}: the original wrote {len(written)} bytes, not the {SCREEN_BYTES} of one screen")


# --- clear_both_screens ($f926) -------------------------------------------------------------------

def test_clear_both_screens_clears_both_buffers_and_the_gap_between_them():
    """The one case, and its point is the SPAN: the run does not stop at the low buffer's last byte,
    it carries on through the 768 bytes of slack and ends at the top of the high one."""
    what = "clear_both_screens"
    span = SCREEN_CLEAR_LONGS * LONGWORD_LEN
    pokes = {SCREEN_LOW: bytes([POISON]) * span}
    info = leaf.run("clear_both_screens", leaf.image_glue("clear_both_screens"),
                    [(SCREEN_LOW, span)], what, regs={"_pokes": pokes},
                    # `lea` and `move.w` set up, then `clr.l`/`dbf` per longword, then `rts`.
                    max_insns=2 + SCREEN_CLEAR_LONGS * COPY_INSN_PER_LONG + 1
                    + leaf.RUNNER_SENTINEL_INSN)
    written = leaf.program_writes(info)
    assert set(written) == set(range(SCREEN_LOW, SCREEN_LOW + span)), (
        f"{what}: the original wrote {len(written)} bytes over "
        f"[{min(written):#x},{max(written) + 1:#x}), not the whole span "
        f"[{SCREEN_LOW:#x},{SCREEN_LOW + span:#x})")
    assert info["regs"]["a0"] == SCREEN_LOW + span


# --- clear_palette ($e7f4) -------------------------------------------------------------------------

CLEAR_PALETTE_LONGS = PALETTE_ROW_BYTES // LONGWORD_LEN
_CLEAR_PALETTE = leaf.bind("clear_palette", leaf.IMAGE_ARG, ctypes.c_uint32)


def test_clear_palette_writes_no_image_byte_and_leaves_the_cursor_past_the_registers():
    """The whole surface. See this file's banner, and test_stage.py's set_palette section for the
    same hole argued at length — the sixteen writes go somewhere the differential cannot see."""
    what = "clear_palette"
    info = leaf.run("clear_palette", lambda _lib, image: _CLEAR_PALETTE(image), [], what,
                    max_insns=1 + CLEAR_PALETTE_LONGS + 1 + leaf.RUNNER_SENTINEL_INSN)
    written = leaf.program_writes(info)
    assert written == {}, (
        f"{what}: the original wrote {len(written)} image byte(s), e.g. {min(written):#x} — this "
        f"routine's whole output is off the image")
    after = SHIFTER_PALETTE + PALETTE_ROW_BYTES
    assert info["regs"]["a0"] == after, (
        f"{what}: the original left a0 at {info['regs']['a0']:#x}, not {after:#x} — the eight "
        f"post-incremented `clr.l`s did not cover the sixteen registers")
    assert info["ret"] == after, (
        f"{what}: the reconstruction returned {info['ret']:#x}, not {after:#x}")


def test_the_palette_registers_are_off_the_image_so_the_clear_is_dropped():
    """WHY the case above can require an EMPTY write set — a fact about the address, not a lucky
    observation. Same assertion test_stage.py makes about the same registers."""
    assert SHIFTER_PALETTE & wb("BUS_ADDR_MASK") >= harness.IMAGE_SIZE


# --- the four cell copiers ($e92c / $e938 / $e948 / $e95e) ---------------------------------------
# Four unrolled widths of one loop. Entered directly here, with their own registers, so each one's
# width and count convention is pinned before `sprites_cru_install` composes them.

COPIER_WORDS = {"sprite_cru_copy_5w": wb("SPRITE_CRU_WORDS_5"),
                "sprite_cru_copy_10w": wb("SPRITE_CRU_WORDS_10"),
                "sprite_cru_copy_15w": wb("SPRITE_CRU_WORDS_15"),
                "sprite_cru_copy_20w": wb("SPRITE_CRU_WORDS_20")}

_COPIERS = {name: leaf.register_glue(name, [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint16],
                                     ctypes.c_uint32)
            for name in COPIER_WORDS}


def _run_copier(name, count_minus_1, seed):
    words = COPIER_WORDS[name]
    cells = count_minus_1 + 1
    span = cells * words * WORD_LEN
    _check_scratch(span)
    what = f"{name} x {cells}"
    pokes = {SRC_AT: _bytes_at(SRC_AT, span, seed), DST_AT: bytes([POISON]) * span}
    # One `move` per operand plus the `dbf`: an odd width leads with a word and then copies pairs.
    per_cell = words // 2 + (words & 1) + 1
    info = leaf.run(name, _COPIERS[name](SRC_AT, DST_AT, count_minus_1), [(DST_AT, span)], what,
                    regs={"a0": SRC_AT, "a3": DST_AT, "d1": count_minus_1, "_pokes": pokes},
                    max_insns=cells * per_cell + 1 + leaf.RUNNER_SENTINEL_INSN)
    assert info["ret"] == DST_AT + span, (
        f"{what}: the reconstruction returned {info['ret']:#x}, not the {DST_AT + span:#x} the "
        f"post-incremented writes leave in a3")
    assert info["regs"]["a3"] == DST_AT + span, (
        f"{what}: the original left a3 at {info['regs']['a3']:#x}")
    assert info["regs"]["a0"] == SRC_AT + span
    return info


@pytest.mark.parametrize("name", sorted(COPIER_WORDS))
@pytest.mark.parametrize("count_minus_1", [0, 2, 61])
def test_a_copier_moves_its_own_width_that_many_times(name, count_minus_1):
    """61 is the largest count any shipped descriptor carries (the census below), 0 the smallest a
    `dbf` can express, and 2 an ordinary middle."""
    _run_copier(name, count_minus_1, seed=count_minus_1)


def test_the_copiers_widths_are_five_ten_fifteen_and_twenty():
    """Derived from the entry table rather than restated: the four are 5, 10, 15 and 20 words, and
    the two ODD ones are the two that lead with a `move.w`."""
    assert sorted(COPIER_WORDS.values()) == [5, 10, 15, 20]
    for name, words in COPIER_WORDS.items():
        leads_with_a_word = ENTRY_INSNS[name] == b"\x36\xd8"
        assert leads_with_a_word == bool(words & 1), (
            f"{name} copies {words} words but its first instruction is "
            f"{ENTRY_INSNS[name].hex()}")


def test_the_dispatch_table_holds_the_four_entries_the_port_dispatches_on():
    """src/boot.c looks the copier up by the LONGWORD the table holds, not by the selector byte, so
    those four longwords are load-bearing constants. Read out of the loaded image here, so an entry
    that moved fails as this assertion instead of as a wrong-width copy."""
    table = wb("SPRITE_CRU_COPY_TABLE")
    want = [wb("SPRITE_CRU_COPY_5W"), wb("SPRITE_CRU_COPY_10W"),
            wb("SPRITE_CRU_COPY_15W"), wb("SPRITE_CRU_COPY_20W")]
    got = [int.from_bytes(harness.BASE_IMAGE[table + i * 4:table + i * 4 + 4], "big")
           for i in range(wb("SPRITE_CRU_COPIERS"))]
    assert got == want, f"the table at {table:#x} holds {[hex(g) for g in got]}"
    assert want == [leaf.entry_of(n) for n in
                    ("sprite_cru_copy_5w", "sprite_cru_copy_10w",
                     "sprite_cru_copy_15w", "sprite_cru_copy_20w")], (
        "the header's four copier addresses and ../names.txt disagree")


# --- bg_tile_install ($e67e) ----------------------------------------------------------------------
# THE FIRST OF THE TWO BOOT PRODUCTS. Its inputs are two depacked resources, so a case has to build
# what the boot would have built: the OVERLAY at WB_STAGE_START_PTR_VALUE (which carries the tile
# index at WB_TILE_INDEX_TABLE) and TILEDATA.RAD at WB_TILE_BANK. Both are depacked by
# tools/depack_rad.py, the HOST reimplementation the game's own rad_depack is pinned against
# (test_rad_depack.py's 45 cases, plus notes/rad_differential.py) — and either way the same bytes go
# to both sides of this differential, so what is being tested here is the installer.
#
# IT HAS NO `rts`, so the run stops at the checkpoint $e6c6 where the body falls through into the
# boot's continuation. That is NOT the ambiguous shape leaf.run_reaching exists for: there is no
# return to be confused with the checkpoint, because the routine has none. The coverage assertion
# below is still made, because it says the TAIL loop ran and not merely that the run stopped.

# `lea $217d8.l,a1` at $e63e — where every OVALAY*.RAD depacks. Scraped rather than re-typed since
# batch 44 phase C gave the operand a name: src/boot.c's stage slice spends the same address.
OVERLAY_AT = wb("OVERLAY_DEPACK_DEST")
TILE_BANK = wb("TILE_BANK")
TILE_BITMAPS = wb("TILE_BITMAPS")
TILE_BITMAP_LEN = wb("TILE_BITMAP_LEN")
TILE_INDEX_TABLE = wb("TILE_INDEX_TABLE")
TILE_INSTALL_COUNT = wb("TILE_INSTALL_COUNT")
TILE_INSTALL_END = wb("TILE_INSTALL_END")
TILE_INSTALL_FALLTHROUGH = wb("TILE_INSTALL_FALLTHROUGH")   # the continuation it drops into
TILE_INSTALL_TAIL_BRANCH = 0xe6c4      # the second loop's `bne.s` — the witness that it ran
# Per tile: six set-up instructions, four `dbf` passes of eight `move.l`, then four to close.
TILE_INSTALL_INSN_PER_TILE = 6 + 4 * 9 + 4
TILE_INSTALL_INSN_CAP = (3 + TILE_INSTALL_COUNT * TILE_INSTALL_INSN_PER_TILE
                         + (TILE_INSTALL_END - TILE_INSTALL_COUNT) * 4 + leaf.RUNNER_SENTINEL_INSN)


def _depacked(path):
    data = path.read_bytes()
    return bytes(depack_rad.depack(data, depack_rad.parse_header(data)))


def _rad_files(directory):
    return sorted((BIN / directory).glob("*.RAD"))


OVERLAYS = [p for p in _rad_files(DISK2) if p.name.startswith("OVALAY")]
OVERLAY_COUNT = 37                     # the OVALAY* set on disk 2, recorded so a partial checkout
                                       # shrinks this battery loudly instead of silently. NOT the 39
                                       # .RAD files test_rad_depack.py counts there: that total also
                                       # takes in DATADISK.RAD and TILEDATA.RAD, neither of which
                                       # carries a tile index
TILEDATA = BIN / DISK2 / "TILEDATA.RAD"


def test_the_resource_corpus_is_the_one_these_cases_were_written_for():
    """A glob over a directory that is not there returns nothing rather than raising, and a battery
    that collected zero cases is not a pass. test_rad_depack.py records its corpus for the same
    reason."""
    assert len(OVERLAYS) == OVERLAY_COUNT, (
        f"{len(OVERLAYS)} OVALAY*.RAD under {BIN / DISK2}, not the recorded {OVERLAY_COUNT}")
    assert TILEDATA.is_file(), f"{TILEDATA} is missing — nothing to install tiles out of"


@functools.lru_cache(maxsize=None)
def _tile_bank():
    """TILEDATA.RAD depacked once. 84,608 bytes, and every case wants the same ones."""
    return _depacked(TILEDATA)


def _run_tile_install(overlay_path, poison=False):
    overlay = _depacked(overlay_path)
    bank = _tile_bank()
    bitmaps_len = TILE_INSTALL_COUNT * TILE_BITMAP_LEN
    index_len = TILE_INSTALL_END * WORD_LEN
    what = f"bg_tile_install with {overlay_path.name}"
    pokes = {OVERLAY_AT: overlay, TILE_BANK: bank,
             TILE_BITMAPS: bytes([POISON]) * bitmaps_len}
    with leaf.pc_coverage():
        info = leaf.run("bg_tile_install", leaf.image_glue("bg_tile_install"),
                        [(TILE_BITMAPS, bitmaps_len), (TILE_INDEX_TABLE, index_len)], what,
                        regs={"_pokes": pokes}, poison=poison,
                        stop_pc=TILE_INSTALL_FALLTHROUGH, max_insns=TILE_INSTALL_INSN_CAP)
    assert emu.cov_visited(TILE_INSTALL_TAIL_BRANCH), (
        f"{what}: the run stopped at {TILE_INSTALL_FALLTHROUGH:#x} without executing the tail "
        f"loop's branch at {TILE_INSTALL_TAIL_BRANCH:#x}")
    written = leaf.program_writes(info)
    assert len(written) == bitmaps_len + index_len, (
        f"{what}: the original wrote {len(written)} bytes, not the {bitmaps_len} of the tile bank "
        f"plus the {index_len} of the index")
    return info


@pytest.mark.parametrize("path", OVERLAYS, ids=[p.name for p in OVERLAYS])
def test_every_shipped_overlay_installs_its_tiles_identically(path):
    """The whole OVALAY* corpus — one case per shipped index table, so the tile ORDER the installer
    packs the bank in is exercised by every arrangement the game ships rather than by one. The count
    is OVERLAY_COUNT and is not restated here: a second spelling of it is how the wrong one (39, the
    whole .RAD set) survived its own correction."""
    _run_tile_install(path)


def test_the_smallest_overlay_installs_under_the_attribution_pass():
    """One poisoned run, for the same reason test_rad_depack.py poisons its two smallest: it stops
    the case passing on a byte the reconstruction never wrote. One file rather than the corpus,
    because every overlay drives the same two write paths."""
    _run_tile_install(min(OVERLAYS, key=lambda p: p.stat().st_size), poison=True)


def test_the_index_leaves_as_the_identity():
    """What the routine is FOR, stated as a property rather than left implicit in the byte diff:
    the table arrives naming arbitrary tiles and leaves naming positions 0..127, which is what makes
    the packed bank the one the scroll engine can index directly."""
    path = min(OVERLAYS, key=lambda p: p.stat().st_size)
    overlay = _depacked(path)
    before = [int.from_bytes(overlay[TILE_INDEX_TABLE - OVERLAY_AT + i * WORD_LEN:][:WORD_LEN],
                             "big") for i in range(TILE_INSTALL_END)]
    assert before != list(range(TILE_INSTALL_END)), (
        f"{path.name}'s index is ALREADY the identity, so this case would pass without the routine "
        f"doing anything")
    _, after = leaf.run_candidate_only(
        leaf.image_glue("bg_tile_install"),
        {OVERLAY_AT: overlay, TILE_BANK: _tile_bank()})
    got = [int.from_bytes(after[TILE_INDEX_TABLE + i * WORD_LEN:][:WORD_LEN], "big")
           for i in range(TILE_INSTALL_END)]
    assert got == list(range(TILE_INSTALL_END)), (
        f"{path.name}: the index does not leave as the identity; first mismatch at "
        f"{next(i for i in range(TILE_INSTALL_END) if got[i] != i)}")


# --- sprites_cru_install ($e87c) --------------------------------------------------------------------
# THE SECOND BOOT PRODUCT, and the larger one: 279,034 bytes of SPRITES.CRU turned into the sprite
# cells the blitters read. Its input is the file RAW — the boot loads it to WB_SPRITE_CRU_LOAD and
# never depacks it — so a case seeds the shipped bytes and a stage number and compares everything.

CRU_PATH = BIN / DISK2 / "SPRITES.CRU"


@functools.lru_cache(maxsize=None)
def _cru_bytes():
    """The shipped SPRITES.CRU, read once. 279,034 bytes, and every case below wants all of them."""
    return CRU_PATH.read_bytes()
CRU_LOAD = wb("SPRITE_CRU_LOAD")
CRU_BYTES = 279034                     # the shipped file's length, recorded for the corpus check
RESOURCE_HEADER = wb("RESOURCE_HEADER")
RESOURCE_TABLE = wb("RESOURCE_TABLE")
CRU_SLIDE_BYTES = wb("SPRITE_CRU_SLIDE_LONGS") * LONGWORD_LEN
CRU_CELLS = wb("SPRITE_CRU_CELLS")
CRU_MASK_TABLE = wb("SPRITE_CRU_MASK_TABLE")
CRU_MASK_SHIFT = wb("SPRITE_CRU_MASK_SHIFT")
CRU_FIRST_DESC = wb("SPRITE_CRU_FIRST_DESC")
CRU_GROUPS = wb("SPRITE_CRU_GROUPS")
CRU_GROUP_SLOTS = wb("SPRITE_CRU_GROUP_SLOTS")
CRU_DESC_COPIER = wb("SPRITE_CRU_DESC_COPIER")
CRU_DESC_COUNT = wb("SPRITE_CRU_DESC_COUNT")
CRU_RECORD_BYTES = wb("RESOURCE_RECORD_BYTES")
CRU_INSTALLED = wb("SPRITE_CRU_INSTALLED")
STAGE_NUMBER = wb("STAGE_NUMBER")
STAGE_BCD_LIMIT = wb("STAGE_NUMBER_BCD_LIMIT")
STAGE_BCD_CARRY = wb("STAGE_NUMBER_BCD_CARRY")
CRU_INSN_CAP = 4_000_000

# The stage numbers the SHIPPED level sequence actually produces — level_seq_table[n][3], which
# $e61a copies into WB_STAGE_NUMBER just before the boot reaches this routine. Taken from the image
# so the battery runs the stages the game runs and not a range invented here.
LEVEL_SEQ_TABLE = wb("LEVEL_SEQ_INDEX") + WORD_LEN   # the table starts where the index word ends
LEVEL_SEQ_ENTRIES = 35                # one per OVALAY* file, ../../notes/architecture.md's §3
LEVEL_SEQ_RECORD = 8                  # `lsl.l #3,d0` at $e5d2 — the dispatcher's own scale
LEVEL_SEQ_STAGE_FIELD = 3             # entry[3] -> WB_STAGE_NUMBER at $e61a
SHIPPED_STAGES = sorted({harness.BASE_IMAGE[LEVEL_SEQ_TABLE + n * LEVEL_SEQ_RECORD
                                            + LEVEL_SEQ_STAGE_FIELD]
                         for n in range(LEVEL_SEQ_ENTRIES)})


@functools.lru_cache(maxsize=None)
def _slid_image_bytes():
    """The descriptor table as the routine's own first act leaves it: the file's first
    WB_SPRITE_CRU_SLIDE_LONGS longwords moved down over WB_RESOURCE_HEADER."""
    return _cru_bytes()[:CRU_SLIDE_BYTES]


@functools.lru_cache(maxsize=None)
def _walk_descriptors(stage):
    """(selector, count_minus_1) for every descriptor `stage`'s mask MARKS, and None for every one
    it does not — re-derived from the 68000 listing at $e89e..$e916, NOT from src/boot.c.

    It exists to BOUND the write set and to census the selectors. It never checks a byte the
    differential checks; the oracle does that.
    """
    table = _slid_image_bytes()
    row = stage - STAGE_BCD_CARRY if stage > STAGE_BCD_LIMIT else stage
    mask_at = CRU_MASK_TABLE + (((row - 1) << CRU_MASK_SHIFT) & 0xffff)   # a4
    walk = []
    descriptor = CRU_FIRST_DESC                                                 # a5, table-relative
    for group in range(CRU_GROUPS, 0, -1):
        bits = int.from_bytes(harness.BASE_IMAGE[mask_at:mask_at + WORD_LEN], "big")
        mask_at += WORD_LEN
        for _ in range(1 if group == 1 else CRU_GROUP_SLOTS):
            bits = ((bits << 1) | (bits >> 15)) & 0xffff
            walk.append((table[descriptor + CRU_DESC_COPIER], table[descriptor + CRU_DESC_COUNT])
                        if bits & 1 else None)
            descriptor += CRU_RECORD_BYTES
    return walk


CRU_SELECTOR_WORDS = {0: wb("SPRITE_CRU_WORDS_5"), 1: wb("SPRITE_CRU_WORDS_10"),
                      2: wb("SPRITE_CRU_WORDS_15"), 3: wb("SPRITE_CRU_WORDS_20")}


def _cell_bytes(stage):
    return sum((count + 1) * CRU_SELECTOR_WORDS[selector] * WORD_LEN
               for selector, count in filter(None, _walk_descriptors(stage)))


def test_the_sprite_file_is_the_one_these_cases_were_written_for():
    assert CRU_PATH.is_file() and CRU_PATH.stat().st_size == CRU_BYTES, (
        f"{CRU_PATH} is {CRU_PATH.stat().st_size if CRU_PATH.is_file() else 'missing'} bytes, not "
        f"the recorded {CRU_BYTES}")
    assert SHIPPED_STAGES, "level_seq_table yielded no stage numbers"


def test_the_slide_ends_exactly_where_the_cells_begin():
    """Not a coincidence worth leaving unstated: the table the routine slides down finishes on the
    first byte of the cell area, so the whole routine's write set is ONE contiguous band."""
    assert RESOURCE_HEADER + CRU_SLIDE_BYTES == CRU_CELLS


@pytest.mark.parametrize("stage", SHIPPED_STAGES)
def test_every_shipped_stage_installs_its_sprites_identically(stage):
    """One case per stage number the shipped level sequence produces. Each drives a different mask
    row, so a different set of descriptors is marked and a different total of cells is laid down."""
    what = f"sprites_cru_install stage {stage}"
    cells = _cell_bytes(stage)
    span = CRU_SLIDE_BYTES + cells
    pokes = {CRU_LOAD: _cru_bytes(),
             STAGE_NUMBER: stage.to_bytes(WORD_LEN, "big")}
    info = leaf.run("sprites_cru_install", leaf.image_glue("sprites_cru_install", ctypes.c_uint32),
                    [(RESOURCE_HEADER, span)], what,
                    regs={"_pokes": pokes}, poison=False, max_insns=CRU_INSN_CAP)
    assert info["ret"] == CRU_INSTALLED, (
        f"{what}: the reconstruction reported {info['ret']}, not WB_SPRITE_CRU_INSTALLED — it met a "
        f"dispatch table longword that is none of the four copiers")
    assert info["regs"]["a3"] == CRU_CELLS + cells, (
        f"{what}: the original left a3 at {info['regs']['a3']:#x}, not the {CRU_CELLS + cells:#x} "
        f"the listing-derived walk expects — the two disagree about which descriptors are marked")


def test_no_shipped_descriptor_selects_a_copier_that_does_not_exist():
    """THE CENSUS THAT MAKES WB_SPRITE_CRU_UNKNOWN_COPIER A GUARD ON UNREACHABLE INPUT.

    `movea.l 0(a1,d0.w),a1 / jsr (a1)` is an UNBOUNDED dispatch: the selector byte is scaled by four
    and read out of a four-entry table, so a byte above 3 fetches a longword from beyond it and the
    original jumps through whatever that is. The port cannot reproduce that and the oracle cannot
    survive it, so the refusal is verified by showing no shipped input reaches it — over every stage
    the level sequence produces and every descriptor its mask marks, not over a sample.
    """
    seen = set()
    for stage in SHIPPED_STAGES:
        marked = [d for d in _walk_descriptors(stage) if d is not None]
        assert marked, f"stage {stage} marks no descriptor at all, so it censuses nothing"
        seen.update(selector for selector, _ in marked)
    assert seen <= set(CRU_SELECTOR_WORDS), (
        f"a shipped descriptor selects copier(s) {sorted(seen - set(CRU_SELECTOR_WORDS))}, which the "
        f"table does not have — WB_SPRITE_CRU_UNKNOWN_COPIER is REACHABLE and this port refuses a "
        f"branch the game takes")
    assert seen == set(CRU_SELECTOR_WORDS), (
        f"only copiers {sorted(seen)} are ever selected, so the differential above never exercises "
        f"{sorted(set(CRU_SELECTOR_WORDS) - seen)}")


def test_the_walk_covers_every_descriptor_the_masks_can_mark():
    """The group geometry, machine-checked: the LAST group runs one slot and not sixteen, which is
    why the count is not a round multiple. A port that missed the `tst.w d5 / beq` would walk 15
    descriptors too many and run off the end of the table."""
    expected = (CRU_GROUPS - 1) * CRU_GROUP_SLOTS + 1
    for stage in SHIPPED_STAGES:
        assert len(_walk_descriptors(stage)) == expected


def test_the_level_sequence_table_is_where_this_battery_thinks_it_is():
    """SHIPPED_STAGES decides which stages the whole sprites_cru_install battery runs, so its base
    address needs a second source like every other derived literal here. `$216c0` is the byte after
    the index word, and the table's last entry must end exactly where the relocator's stub begins."""
    assert LEVEL_SEQ_TABLE == 0x216c0
    assert LEVEL_SEQ_TABLE + LEVEL_SEQ_ENTRIES * LEVEL_SEQ_RECORD == leaf.entry_of(
        "startup_relocate_and_run"), (
        "the 35 eight-byte entries do not end where startup_relocate_and_run begins, so either the "
        "base, the count or the stride is wrong")
    assert SHIPPED_STAGES, "level_seq_table yielded no stage numbers"


def test_the_two_literal_addresses_equal_their_derivations():
    """WB_SPRITE_CRU_LOAD, WB_SPRITE_CRU_BODY and WB_SPRITE_CRU_MASK_STRIDE are spelt as literals so
    test/layout.py can scrape them, which means each is a SECOND source for a number the parts below
    it already give. Cross-pinned here so the two spellings cannot drift — the failure mode
    tools/hw_portability.py was written for, in miniature."""
    assert CRU_LOAD == RESOURCE_HEADER + wb("SPRITE_CRU_LOAD_OFF")
    assert wb("SPRITE_CRU_BODY") == CRU_LOAD + wb("SPRITE_CRU_FILE_HEADER")
    assert wb("SPRITE_CRU_MASK_STRIDE") == 1 << CRU_MASK_SHIFT
    assert wb("SPRITE_CRU_UNMARKED") == CRU_CELLS - RESOURCE_TABLE, (
        "the constant an UNMARKED descriptor is given is not the cell base's own offset")


def test_an_out_of_range_selector_is_refused_rather_than_dispatched():
    """THE REFUSAL ARM, DRIVEN — and it has to be candidate-only, which is the whole point of it.

    `movea.l 0(a1,d0.w),a1 / jsr (a1)` scales the descriptor's selector byte by four into a
    four-entry table, so a byte of 4 fetches the longword AT $e92c — the first copier's own first
    two instructions, `36d8 26d8` = $36d826d8 — and the original jumps there. That is not a run the
    oracle survives and not behaviour a port can reproduce, so there is no differential to be had;
    what CAN be shown is that the reconstruction refuses instead of inventing a width.

    IT EXISTS BECAUSE THE MUTATION SWEEP SAID SO. With no case here, `if (words ==
    SPRITE_CRU_NO_COPIER) return WB_SPRITE_CRU_UNKNOWN_COPIER;` could be deleted — or turned into
    "pretend it was the 5-word copier" — and the whole suite stayed green (measured: one SURVIVOR in
    batch 44 phase A's second sweep round). The census two cases up says no shipped input reaches
    this; that makes the arm unreachable, not unwritten, and an unreachable arm nothing pins is an
    arm the next edit silently changes.
    """
    stage = SHIPPED_STAGES[0]
    marked = [i for i, d in enumerate(_walk_descriptors(stage)) if d is not None]
    assert marked, f"stage {stage} marks nothing, so there is no descriptor to corrupt"
    # The FIRST marked descriptor, so the refusal happens with as little of the walk behind it as
    # possible — and the case is about the arm, not about how far the walk got.
    descriptor = RESOURCE_HEADER + CRU_FIRST_DESC + marked[0] * CRU_RECORD_BYTES
    # Its selector byte lives in the SLID copy, so the poke goes into the file at the offset the
    # slide brings down to that address.
    selector_in_file = CRU_LOAD + (descriptor - RESOURCE_HEADER) + CRU_DESC_COPIER
    out_of_range = wb("SPRITE_CRU_COPIERS")           # 4 — the first index past the table
    pokes = {CRU_LOAD: _cru_bytes(), STAGE_NUMBER: stage.to_bytes(WORD_LEN, "big"),
             selector_in_file: bytes([out_of_range])}
    ret, _ = leaf.run_candidate_only(leaf.image_glue("sprites_cru_install", ctypes.c_uint32), pokes)
    assert ret == wb("SPRITE_CRU_UNKNOWN_COPIER"), (
        f"a selector of {out_of_range} returned {ret}, not WB_SPRITE_CRU_UNKNOWN_COPIER — the port "
        f"dispatched on a table entry that is not one of the four copiers")
    # ...and the control, so the case cannot pass because EVERY run returns the refusal.
    clean = {CRU_LOAD: _cru_bytes(), STAGE_NUMBER: stage.to_bytes(WORD_LEN, "big")}
    ret_clean, _ = leaf.run_candidate_only(
        leaf.image_glue("sprites_cru_install", ctypes.c_uint32), clean)
    assert ret_clean == CRU_INSTALLED, (
        f"the same stage WITHOUT the poked selector returned {ret_clean}, so this case would pass "
        f"whether or not the poke did anything")


def test_the_longword_an_out_of_range_selector_fetches_is_not_a_copier():
    """WHY 4 is the right corruption, read out of the image rather than asserted: the longword one
    entry past the table is the first copier's own instruction bytes, which is none of the four."""
    table = wb("SPRITE_CRU_COPY_TABLE")
    past = table + wb("SPRITE_CRU_COPIERS") * LONGWORD_LEN
    fetched = int.from_bytes(harness.BASE_IMAGE[past:past + LONGWORD_LEN], "big")
    assert fetched not in (wb("SPRITE_CRU_COPY_5W"), wb("SPRITE_CRU_COPY_10W"),
                           wb("SPRITE_CRU_COPY_15W"), wb("SPRITE_CRU_COPY_20W")), (
        f"the longword at {past:#x} IS one of the four copiers, so a selector of 4 would dispatch "
        f"normally and the case above would prove nothing")
    assert past == wb("SPRITE_CRU_COPY_5W"), (
        "the table no longer ends where the first copier begins, so this case's reasoning is stale")


# =================================================================================================
# THE LOAD PATH ABOVE THE DISK SEAM (batch 44 phase B)
#
# `disk_load_file` ($5e7c) is the lowest routine of the boot chain whose inputs are FILE-SHAPED — a
# twelve-character DOS name in a0, a destination in a1 — and the 1,644 bytes it reaches are the raw
# WD1772/DMA driver and the FAT12 layer above it. test_boot_inventory.py's census is what says the
# boot chain crosses that seam EXACTLY ONCE, at `jsr $5e7c.w` inside `load_resource_by_index`; the
# band is a declared boundary and the port calls the kit's `disk_read_file` across it.
#
# SO THE ORACLE HAS TO PERFORM THE SAME SUBSTITUTION, and that is what SEAM_STUB below is: the same
# open-read-close, hand-assembled as GEMDOS traps and poked over `disk_load_file`. Both sides then go
# through the kit's staged-file model, whose WHOLE state — the table, the cursors, the open flags and
# the bytes — lives inside the image, so the ordinary byte diff is what holds the C statement of the
# substitution and the 68000 one equal. Nothing here is taken on trust because the seam was declared.
#
# WHAT THAT DOES AND DOES NOT PIN, with TWO exclusions and not one. Differentially it pins the index
# scaling, the row address, the two retry longwords, the Copylock guard on both arms, and the file
# landing whole at its destination. It does NOT pin:
#   * the four bytes of the `jsr` itself — that is the seam, and substituting it is the point;
#   * THE ERROR ARM, which no differential in this file covers. The staged-file model answers served
#     or REFUSED and a refusal sinks the run, so the oracle cannot be made to return a negative
#     `disk_load_file` at all; both of that arm's cases are candidate-only and say so where they sit,
#     ~280 lines down. An earlier revision of this banner said "every byte except the four of the
#     `jsr`", which contradicted the file's own scoping of exactly that arm.
# Neither exclusion covers the original's FDC driver, which is unpinned by declaration — the point of
# calling it a boundary rather than a to-do.
# =================================================================================================

DISK_LOAD_FILE = wb("DISK_LOAD_FILE")
# The seam routine's extent, DERIVED from its own neighbour rather than transcribed: the stub is
# poked over these bytes and an assertion that it fits is worth nothing if the number can drift.
DISK_LOAD_FILE_BYTES = leaf.entry_of("fat_calc_data_start") - DISK_LOAD_FILE
GEMDOS_HEADER_LEN = 28            # prg_dis.decode takes a FILE offset, not an image one
RESOURCE_FILE_TABLE = wb("RESOURCE_FILE_TABLE")
RESOURCE_FILE_ROW_SHIFT = wb("RESOURCE_FILE_ROW_SHIFT")
RESOURCE_FILE_COUNT = wb("RESOURCE_FILE_COUNT")
RESOURCE_LOAD_BUFFER = wb("RESOURCE_LOAD_BUFFER")
LOAD_RETRY_INDEX = wb("LOAD_RETRY_INDEX")
LOAD_RETRY_DEST = wb("LOAD_RETRY_DEST")
LOAD_OK = wb("LOAD_OK")
LOAD_COPYLOCK_RAN = wb("LOAD_COPYLOCK_RAN")
LOAD_DISK_ERROR = wb("LOAD_DISK_ERROR")
COPYLOCK_ARM_FLAG = wb("COPYLOCK_ARM_FLAG")
COPYLOCK_ARM_FLAG_LEN = wb("COPYLOCK_ARM_FLAG_LEN")
JOY1_STATE = wb("JOY1_STATE")

LEVEL_SEQ_TABLE = wb("LEVEL_SEQ_TABLE")
LEVEL_SEQ_ROWS = wb("LEVEL_SEQ_ROWS")
LEVEL_SEQ_INDEX = wb("LEVEL_SEQ_INDEX")
LEVEL_SEQ_RECORD_BYTES = wb("LEVEL_SEQ_RECORD_BYTES")
LEVEL_SEQ_OVERLAY = wb("LEVEL_SEQ_OVERLAY")
LEVEL_SEQ_SECOND_LOAD = wb("LEVEL_SEQ_SECOND_LOAD")
LEVEL_SEQ_SIDE = wb("LEVEL_SEQ_SIDE")
LEVEL_SEQ_STAGE = wb("LEVEL_SEQ_STAGE")
STAGE_SECOND_LOAD_FLAG = wb("STAGE_SECOND_LOAD_FLAG")
STAGE_SIDE_FLAG = wb("STAGE_SIDE_FLAG")
STAGE_NUMBER = wb("STAGE_NUMBER")
LIFE_RESTART_ENTRY_C26 = wb("LIFE_RESTART_ENTRY_C26")
ACTOR_PLATFORM_RIDDEN = wb("ACTOR_PLATFORM_RIDDEN")
STATE_FLAG_SET = wb("STATE_FLAG_SET")
RESOURCE_FIRST_OVERLAY = wb("RESOURCE_FIRST_OVERLAY")

ACTOR_TABLES = (wb("ACTOR_TABLE_DEFAULT"), wb("ACTOR_TABLE_A30"), wb("ACTOR_TABLE_A32"))
ACTOR_FOLLOWED = (wb("ACTOR_FOLLOWED_DEFAULT"), wb("ACTOR_FOLLOWED_A32"))


# --- the seam stub: the substitution, stated in 68000 ---------------------------------------------
# One `Fopen`, one `Fread` for more than any file holds, one `Fclose`, and 0 or -1 in d0 — which is
# `disk_load_file`'s own contract (0 on success, negative on error) and NOT a byte count, because a
# byte count is something the original never hands its caller.
#
# THE STUB IS PINNED BY DECODE, not by a comment. `test_the_seam_stub_is_the_gemdos_calls_it_claims`
# runs prg_dis over these bytes and requires the mnemonics — an encoder slip here would otherwise
# express itself as a puzzling image diff a long way from its cause.
_STUB_FOPEN = 0x3d
_STUB_FREAD = 0x3f
_STUB_FCLOSE = 0x3e
TRAP_1 = b"\x4e\x41"                 # the GEMDOS trap all three calls go through
# The same "more than any file holds" the port passes (tools/recreate_kit/src/disk.c's
# DISK_READ_TO_EOF), so the two statements of the substitution ask the model the same question.
_STUB_READ_TO_EOF = harness.OS_IMAGE_SIZE


BMI_S_OPCODE = 0x6b00               # `bmi.s <d8>`, as leaf.bcc_s takes its condition


def _seam_stub():
    """`disk_load_file`'s bytes replaced by the GEMDOS substitution the port makes. a0 = name,
    a1 = destination, d0 = 0 / -1 out; d1 and the stack are the stub's own.

    Assembled through `leaf.asm`, which owns the label pass and the short-branch displacement rule
    (`leaf.bcc_s`, `leaf.BRANCH_EXTENSION`). An earlier revision hand-rolled both, and the copy could
    only branch FORWARD — so the stub silently could not have grown a loop, and the `2` in
    "counted from the byte after the branch word" existed twice."""
    return leaf.asm(0, [
        b"\x2f\x09",                              #        move.l a1,-(a7)   save the destination
        b"\x42\x67",                              #        clr.w -(a7)       Fopen mode 0
        b"\x2f\x08",                              #        move.l a0,-(a7)
        b"\x3f\x3c" + leaf.word(_STUB_FOPEN),
        TRAP_1,
        b"\x4f\xef\x00\x08",                      #        lea 8(a7),a7
        b"\x22\x5f",                              #        movea.l (a7)+,a1  the destination back
        b"\x4a\x80",                              #        tst.l d0
        leaf.bcc_s(BMI_S_OPCODE, "fail"),
        b"\x32\x00",                              #        move.w d0,d1      the handle
        b"\x2f\x09",                              #        move.l a1,-(a7)   Fread buf
        b"\x2f\x3c" + leaf.longword(_STUB_READ_TO_EOF),
        b"\x3f\x01",                              #        move.w d1,-(a7)
        b"\x3f\x3c" + leaf.word(_STUB_FREAD),
        TRAP_1,
        b"\x4f\xef\x00\x0c",                      #        lea 12(a7),a7
        b"\x2f\x00",                              #        move.l d0,-(a7)   keep the byte count
        b"\x3f\x01",                              #        move.w d1,-(a7)
        b"\x3f\x3c" + leaf.word(_STUB_FCLOSE),
        TRAP_1,
        b"\x58\x8f",                              #        addq.l #4,a7
        b"\x20\x1f",                              #        move.l (a7)+,d0   ...and test it
        b"\x4a\x80",                              #        tst.l d0
        leaf.bcc_s(BMI_S_OPCODE, "fail"),
        leaf.moveq(0, 0),                         #        moveq #0,d0       DISK_READ_OK
        leaf.RTS,
        leaf.lab("fail"),
        b"\x70\xff",                              # fail:  moveq #-1,d0
        leaf.RTS,
    ])


SEAM_STUB = _seam_stub()
# The stub's own instruction count, plus the ten of load_resource_by_index around it and a margin
# for the two `trap`s. Stated so `max_insns` stays a cap and not a formality.
SEAM_INSN_CAP = 64


# The kit's staged-file area, as a length: the model lays files contiguously from OS_FS_STAGING and
# refuses one that would reach the stack guard. It bounds which of the boot's resources can be
# staged at all — the size case below and test_boot_chain.py's sprite prefix both spend it, and a
# second derivation is exactly what would drift the day the model grew a per-file header.
STAGING_CAPACITY = emu.STACK_GUARD_LO - harness.OS_FS_STAGING


def seam_pokes(files):
    """Poke dict for a run's staged files: the stub over the seam, and each `(name, data)` in the
    model. A case that wants the Copylock armed adds the flag itself, because it also has to add the
    entry stub.

    It takes a LIST because test_boot_chain.py's composed slices load two and three files apiece,
    and a second spelling of the substitution's poke shape is exactly what would drift the day the
    stub's address or the staging convention moved."""
    stage_pokes, _ = harness.stage_files(files)
    return {DISK_LOAD_FILE: SEAM_STUB, **stage_pokes}


def test_the_seam_stub_is_the_gemdos_calls_it_claims():
    """Decode the substitution rather than trust the comment beside it. A hand-assembled stub is the
    one input to a differential that nothing else checks: it is not read out of the image, so a
    wrong opcode or displacement expresses itself as a puzzling diff inside the routine under test.

    Also pins that it FITS. `disk_load_file` is 138 bytes and the stub is poked over its first
    bytes; a longer one would spill into `fat_calc_data_start`, which is inside the boundary and so
    is code no case would notice being clobbered."""
    at, decoded = 0, []
    while at < len(SEAM_STUB):
        length, text = prg_dis.decode(bytes(GEMDOS_HEADER_LEN) + SEAM_STUB, GEMDOS_HEADER_LEN + at,
                                      0)
        assert not text.startswith("dc.w"), f"the stub does not decode at byte {at}: {text}"
        decoded.append(text)
        at += length
    assert at == len(SEAM_STUB), "the stub's last instruction runs past its own end"
    traps = [i for i, text in enumerate(decoded) if text.startswith("trap")]
    assert len(traps) == 3, f"the substitution makes {len(traps)} traps, not the Fopen/Fread/Fclose 3"
    for want in (f"move.w #${_STUB_FOPEN:x},-(a7)", f"move.w #${_STUB_FREAD:x},-(a7)",
                 f"move.w #${_STUB_FCLOSE:x},-(a7)"):
        assert want in decoded, f"the stub never pushes {want}"
    assert f"move.l #${_STUB_READ_TO_EOF:x},-(a7)" in decoded, (
        "the stub's Fread count is not the DISK_READ_TO_EOF the port passes, so the two statements "
        "of the substitution ask the model different questions")
    assert len(SEAM_STUB) <= DISK_LOAD_FILE_BYTES, (
        f"the {len(SEAM_STUB)}-byte stub does not fit disk_load_file's {DISK_LOAD_FILE_BYTES}")


def test_the_resource_table_rows_are_the_filenames_the_substitution_needs():
    """Every row of WB_RESOURCE_FILE_TABLE is a NUL-terminated 8.3 name that fits the model's name
    field, so the seam can be handed the same pointer `fat_find_dir_entry` is.

    AND TWO ROWS ARE SPACE-PADDED, WHICH IS WHERE THE TWO SIDES OF THE SUBSTITUTION DIFFER. FAT12
    pads a short stem to eight characters, so `CREDITS .RAD` and `SPRITES .CRU` carry an INTERNAL
    space. The kit's staged-file model has no path syntax and matches the bytes, so off target the
    row goes to `os_fopen` untranslated and the harness stages it under exactly that name. GEMDOS
    does have a path syntax and a space is a real character in it, so the ON-TARGET backend
    (`atari/wonderboy_backend.c`'s `gemdos_name`) drops spaces before `Fopen`, and `atari/smoke.py`
    stages the drive by the same rule.

    THE SET IS PINNED RATHER THAN THE PROPERTY, because the property is what an earlier draft of this
    case got wrong: it asserted `name == name.strip()`, which is TRUE of an internal space, and the
    error was found by running on a real machine instead. A third padded row appearing must fail
    here — and it would be a row the on-target rule handles and this comment no longer describes."""
    names = []
    for index in range(RESOURCE_FILE_COUNT):
        row = RESOURCE_FILE_TABLE + (index << RESOURCE_FILE_ROW_SHIFT)
        raw = bytes(harness.BASE_IMAGE[row:row + (1 << RESOURCE_FILE_ROW_SHIFT)])
        assert b"\x00" in raw, f"row {index} at {row:#x} has no terminator: {raw!r}"
        name = raw[:raw.index(b"\x00")].decode("ascii")
        assert len(name) < harness.OS_FS_NAME, f"{name!r} will not fit the model's name field"
        assert name == name.strip(), f"row {index} is {name!r} — outer padding, not an 8.3 name"
        names.append(name)
    padded = {index: name for index, name in enumerate(names) if " " in name}
    assert padded == {wb("RESOURCE_CREDITS"): "CREDITS .RAD",
                      wb("RESOURCE_SPRITES_CRU"): "SPRITES .CRU"}, (
        f"the space-padded rows are {padded}, not the two the on-target backend's `gemdos_name` and "
        f"atari/smoke.py's staging rule are written for")
    assert names[wb("RESOURCE_TITLESCR")] == "TITLESCR.RAD"
    assert names[wb("RESOURCE_CREDITS")] == "CREDITS .RAD"
    assert names[wb("RESOURCE_TILEDATA")] == "TILEDATA.RAD"
    assert names[wb("RESOURCE_SPRITES_CRU")] == "SPRITES .CRU"
    assert names[wb("RESOURCE_DATADISK")] == "DATADISK.RAD"
    overlays = names[RESOURCE_FIRST_OVERLAY:wb("RESOURCE_TILEDATA")]
    assert len(overlays) == LEVEL_SEQ_ROWS and all(n.startswith("OVALAY") for n in overlays), (
        f"the {len(overlays)} rows between CREDITS and TILEDATA are not all overlays: {overlays}")


# --- load_resource_by_index ($e782), across the seam -----------------------------------------------

_LOAD_RESOURCE = leaf.register_glue("load_resource_by_index", [ctypes.c_uint32] * 2,
                                    ctypes.c_uint32)


def _load_allowed(dest, span):
    """Every band `load_resource_by_index` may write: the file's landing place, the two retry
    longwords, the Copylock's flag, and the model's own table entry for the staged file — the last
    of which is exactly what makes the substitution comparable, since it is in the image."""
    return [(dest, span), (LOAD_RETRY_INDEX, LONGWORD_LEN), (LOAD_RETRY_DEST, LONGWORD_LEN),
            (COPYLOCK_ARM_FLAG, COPYLOCK_ARM_FLAG_LEN),
            (harness.OS_FS_TABLE, harness.OS_FS_ENTRY)]


def _run_load(index, name, data, dest, poison=False):
    what = f"load_resource_by_index({index}, {dest:#x}) -> {name}"
    assert dest + len(data) <= harness.OS_FS_TABLE, (
        f"{len(data)} bytes at {dest:#x} reach the staged-file table at {harness.OS_FS_TABLE:#x}")
    pokes = seam_pokes([(name, data)])
    before = harness.make_image(pokes)
    info = leaf.run("load_resource_by_index", _LOAD_RESOURCE(index, dest),
                    _load_allowed(dest, len(data)), what,
                    regs={"d0": index, "a1": dest, "_pokes": pokes}, poison=poison,
                    max_insns=SEAM_INSN_CAP)
    after, _, _ = emu.run(bytearray(before), leaf.entry_of("load_resource_by_index"),
                          {"d0": index, "a1": dest}, max_insns=SEAM_INSN_CAP)
    # copylock.py's own docstring names THIS differential as the one that must ask by hand: a run
    # driven through `differential` gets no witness, because `differential` does not hand back the
    # image the witness compares against.
    copylock.assert_did_not_execute(before, after, leaf.entry_of("load_resource_by_index"))
    assert bytes(after[dest:dest + len(data)]) == data, (
        f"{what}: the ORACLE's own run did not land the file whole, so this case is comparing two "
        f"sides of a substitution that does not work")
    return info


def test_the_title_screen_loads_across_the_seam():
    """THE ROUND'S HEADLINE, and the load the on-target boot needs: index 0 with the boot's own
    destination, over the shipped 16,620-byte TITLESCR.RAD."""
    info = _run_load(wb("RESOURCE_TITLESCR"), "TITLESCR.RAD",
                     (BIN / "disk1" / "TITLESCR.RAD").read_bytes(), RESOURCE_LOAD_BUFFER)
    assert info["ret"] == LOAD_OK, f"the port reported {info['ret']}, not WB_LOAD_OK"


@pytest.mark.parametrize("index,name,where", [
    (wb("RESOURCE_TITLESCR"), "TITLESCR.RAD", "disk1"),
    (wb("RESOURCE_CREDITS"), "CREDITS .RAD", "disk1"),
    (wb("RESOURCE_DATADISK"), "DATADISK.RAD", DISK2),
    (wb("RESOURCE_TILEDATA"), "TILEDATA.RAD", DISK2),
])
def test_every_boot_resource_that_fits_the_model_loads_across_the_seam(index, name, where):
    """The boot's own four named loads, each at its own index — so the index scaling is exercised by
    the values the game really passes and not by one of them.

    SPRITES.CRU IS THE FIFTH AND IS NOT HERE. Its 279,034 bytes are larger than the whole staging
    area the model has to lay files in, so it cannot be staged at all; the boundary between "this
    load is pinned" and "this one is not" is a size, and it is stated rather than left as a gap."""
    # The HOST path, not the GEMDOS one. It looks like the backend's `gemdos_name` and smoke.py's
    # staging rule and is neither: the extracted corpus on this machine is named `CREDITS.RAD`, so
    # this drops the FAT pad to find a FILE, while those two drop it to satisfy a path syntax. The
    # name STAGED into the model keeps its space, because that is what the game's table holds.
    data = (BIN / where / name.replace(" ", "")).read_bytes()
    info = _run_load(index, name, data, RESOURCE_LOAD_BUFFER)
    assert info["ret"] == LOAD_OK


def test_the_smallest_boot_resource_loads_under_the_attribution_pass():
    """One poisoned run, so the case cannot pass on a destination byte the reconstruction never
    wrote. DATADISK.RAD because it is the smallest of the four and every one drives the same path."""
    _run_load(wb("RESOURCE_DATADISK"), "DATADISK.RAD",
              (BIN / DISK2 / "DATADISK.RAD").read_bytes(), RESOURCE_LOAD_BUFFER, poison=True)


def test_the_load_is_repeated_at_a_destination_the_boot_never_uses():
    """The destination is a PARAMETER, and every case above passes the same one. A second address
    separates "the port writes where it was told" from "the port writes where the boot happens to
    want", which the boot's own operand cannot."""
    _run_load(wb("RESOURCE_DATADISK"), "DATADISK.RAD",
              (BIN / DISK2 / "DATADISK.RAD").read_bytes(), DST_AT)


@pytest.mark.parametrize("armed", [0xffff, 1, 0x8000])
def test_the_first_load_of_the_boot_runs_the_copylock_and_disarms_it(armed):
    """THE ARMED ARM. `tst.w copylock_arm_flag / jsr copylock_entry / clr.w copylock_arm_flag` — the
    protection runs on the FIRST resource load and never again, and the port reports which arm it
    took because it cannot reproduce what the call does.

    THREE ARMED VALUES, because `tst.w` is a test against ZERO and not against $ffff. The game only
    ever writes $ffff, so a port that compared for equality would be green on every shipped path —
    which is exactly what a mutation sweep found, and what $0001 and $8000 are here to stop.

    The oracle only survives this because test/copylock.py has poked an `rts` over the blob, so the
    run carries that module's witness: what is compared is the game's memory and not a trace
    decryptor's leavings. Stub.ENTRY_RTS and not DISARM — DISARM is the state this case is trying to
    reach, so disarming it up front would be testing the other arm."""
    data = (BIN / DISK2 / "DATADISK.RAD").read_bytes()
    pokes = {**seam_pokes([("DATADISK.RAD", data)]),
             COPYLOCK_ARM_FLAG: armed.to_bytes(COPYLOCK_ARM_FLAG_LEN, "big"),
             **copylock.stub_pokes(copylock.Stub.ENTRY_RTS)}
    before = harness.make_image(pokes)
    entry = leaf.entry_of("load_resource_by_index")
    info = leaf.run("load_resource_by_index",
                    _LOAD_RESOURCE(wb("RESOURCE_DATADISK"), RESOURCE_LOAD_BUFFER),
                    _load_allowed(RESOURCE_LOAD_BUFFER, len(data)),
                    f"load_resource_by_index with copylock_arm_flag = {armed:#x}",
                    regs={"d0": wb("RESOURCE_DATADISK"), "a1": RESOURCE_LOAD_BUFFER,
                          "_pokes": pokes}, poison=False, max_insns=SEAM_INSN_CAP)
    after, _, _ = emu.run(bytearray(before), entry,
                          {"d0": wb("RESOURCE_DATADISK"), "a1": RESOURCE_LOAD_BUFFER},
                          max_insns=SEAM_INSN_CAP)
    copylock.assert_did_not_execute(before, after, entry)
    assert info["ret"] == LOAD_COPYLOCK_RAN, (
        f"the port reported {info['ret']}, not WB_LOAD_COPYLOCK_RAN — it did not take the armed arm")
    assert bytes(after[COPYLOCK_ARM_FLAG:COPYLOCK_ARM_FLAG + COPYLOCK_ARM_FLAG_LEN]) \
        == copylock.DISARMED, "the original left the flag armed, so the guard would run twice"


def test_an_index_of_0x1000_wraps_to_row_zero_and_loads_the_title_screen():
    """THE SCALED INDEX IS USED AS A WORD. `lsl.l #4` on $1000 gives $10000, and the `lea`'s brief
    extension word selects `d0.w` — so the high half is dropped and the row is the table's FIRST,
    which is TITLESCR.RAD. A port that kept 32 bits would address 64 KB above the table.

    A real differential and not a census: the wrapped row IS a staged filename, so the model can
    serve it and both sides can be compared."""
    data = (BIN / "disk1" / "TITLESCR.RAD").read_bytes()
    info = _run_load(1 << (16 - RESOURCE_FILE_ROW_SHIFT), "TITLESCR.RAD", data,
                     RESOURCE_LOAD_BUFFER)
    assert info["ret"] == LOAD_OK


def test_an_index_past_0x7ff_names_a_row_below_the_table_because_the_word_is_signed():
    """...AND THE WORD IS SIGNED. $800 scales to $8000, which `d0.w` sign-extends to -32768, so the
    row is 32 KB BELOW WB_RESOURCE_FILE_TABLE and not above it. The two mistakes a port can make
    here — the wrong width and the wrong signedness — differ only past this index, so this is the
    case that separates them, and it needs the difference to be REACHABLE: the name is SEEDED at the
    address the original's own `lea` computes, which is the discipline batch 38's unbounded dispatch
    established (seed an entry the original really jumps to, do not assert about one it cannot).

    THE PREMISE IS ASSERTED, not assumed: if the seeded row were not below the table this case would
    pass while proving nothing about the sign."""
    below = RESOURCE_FILE_TABLE - 0x8000
    assert below < RESOURCE_FILE_TABLE and loader.PROGRAM_END > below >= 0, (
        f"{below:#x} is not a seedable address below the table, so this case cannot run")
    name = "SIGNED  .ROW"
    data = (BIN / DISK2 / "DATADISK.RAD").read_bytes()
    index = 0x8000 >> RESOURCE_FILE_ROW_SHIFT
    pokes = {**seam_pokes([(name, data)]), below: name.encode("ascii") + b"\x00"}
    what = f"load_resource_by_index({index:#x}) -> the row at {below:#x}"
    info = leaf.run("load_resource_by_index", _LOAD_RESOURCE(index, DST_AT),
                    _load_allowed(DST_AT, len(data)) + [(below, len(name) + 1)], what,
                    regs={"d0": index, "a1": DST_AT, "_pokes": pokes}, poison=False,
                    max_insns=SEAM_INSN_CAP)
    assert info["ret"] == LOAD_OK, (
        f"{what}: the port reported {info['ret']} — it did not reach the row the original's `lea` "
        f"computes, so its index arithmetic is not the 68000's")


# --- the stage's actors ($e710 / $e768) -----------------------------------------------------------

_APPLY_SIDE = leaf.register_glue("actor_apply_stage_side", [ctypes.c_uint32])

# $e710's three `actor_table_reset` calls plus the two records' four stores each. Each reset walks 19
# records marking them free, which is what makes the cap a geometry statement rather than a guess.
ACTOR_TABLE_RECORDS = 19
ACTOR_RECORD_BYTES = wb("ACTOR_RECORD_BYTES")
ACTOR_TABLE_SPAN = ACTOR_TABLE_RECORDS * ACTOR_RECORD_BYTES
STAGE_ACTORS_INSN_CAP = 3 * ACTOR_TABLE_RECORDS * 16 + 64


# POISON is 0x5a = 0b01011010, which already has BIT 3 SET. A case that seeds only the poison can
# therefore not tell `bset #3` from a no-op — it observes the CLEARING arm and nothing else, which is
# what an earlier revision of the case below did while its docstring claimed otherwise. Both
# polarities are seeded, and the pair is derived from POISON so it cannot drift away from it.
SIDE_BIT_SEEDS = (POISON, POISON & ~(1 << wb("ACTOR_FLAG_SIDE_BIT")))


def test_the_poison_alone_cannot_observe_the_side_bit_being_raised():
    """The premise of the seeding above, asserted rather than commented: if POISON ever changed to a
    value with bit 3 clear, the second seed would become the redundant one and this pair would stop
    being a pair. Either way the case below needs one of each, and this is what says so."""
    bit = 1 << wb("ACTOR_FLAG_SIDE_BIT")
    assert len({seed & bit for seed in SIDE_BIT_SEEDS}) == 2, (
        f"the two seeds {[hex(s) for s in SIDE_BIT_SEEDS]} agree on bit "
        f"{wb('ACTOR_FLAG_SIDE_BIT')}, so one arm of actor_apply_stage_side writes what was already "
        f"there and is unobservable")


@pytest.mark.parametrize("seed", SIDE_BIT_SEEDS)
@pytest.mark.parametrize("side", [0, STATE_FLAG_SET, 1, 0x8000])
@pytest.mark.parametrize("record", ACTOR_FOLLOWED)
def test_the_stage_side_flag_sets_or_clears_the_side_bit(record, side, seed):
    """`tst.w stage_side_flag` is a WORD test against zero, not a test of a particular value — so
    $0001 and $8000 raise the bit exactly as $ffff does. Both records, because the routine takes the
    one it acts on in a0 and a port that ignored the parameter would pass on one of them. And BOTH
    SEEDS, because the bit has to be observed changing in each direction — see SIDE_BIT_SEEDS."""
    what = (f"actor_apply_stage_side({record:#x}) with stage_side_flag = {side:#x} over a flags byte "
            f"of {seed:#x}")
    pokes = {STAGE_SIDE_FLAG: side.to_bytes(WORD_LEN, "big"),
             record + wb("ACTOR_FLAGS"): bytes([seed])}
    leaf.run("actor_apply_stage_side", _APPLY_SIDE(record),
             [(record + wb("ACTOR_FLAGS"), 1)], what,
             regs={"a0": record, "_pokes": pokes})


def _run_stage_actors_init(side, poison=False):
    what = f"stage_actors_init with stage_side_flag = {side:#x}"
    pokes = {STAGE_SIDE_FLAG: side.to_bytes(WORD_LEN, "big")}
    for table in ACTOR_TABLES:
        pokes[table] = bytes([POISON]) * ACTOR_TABLE_SPAN
    allowed = [(table, ACTOR_TABLE_SPAN) for table in ACTOR_TABLES]
    return leaf.run("stage_actors_init", leaf.image_glue("stage_actors_init"), allowed, what,
                    regs={"_pokes": pokes}, poison=poison, max_insns=STAGE_ACTORS_INSN_CAP)


@pytest.mark.parametrize("side", [0, STATE_FLAG_SET])
def test_the_stage_s_actors_are_built_from_nothing(side):
    """All three tables emptied and both followed records given the entry shape, over a table
    poisoned first — so a field the reconstruction never wrote cannot pass by already being right.
    Both arms of the side flag, because the last thing the routine does is apply it twice."""
    info = _run_stage_actors_init(side)
    written = leaf.program_writes(info)
    assert set(leaf.merge_bands(written)) == {(table, ACTOR_TABLE_SPAN) for table in ACTOR_TABLES}, (
        f"the original wrote {leaf.merge_bands(written)}, not the three whole tables — so either a "
        f"reset stopped short or the followed records are not inside the tables this case poisons")


def test_the_stage_s_actors_are_built_under_the_attribution_pass():
    """One poisoned run. It is the case that would catch a port whose two passes ran the other way
    round, since actor_table_reset's zeroes would then land ON TOP of the three fields."""
    _run_stage_actors_init(STATE_FLAG_SET, poison=True)


def test_the_a30_table_gets_no_followed_record():
    """THE ASYMMETRY: three tables, two shaped records. Asked of the RUN's own write values rather
    than of the constants — an earlier revision asserted that the A30 table's slot 12 was not one of
    the two followed addresses, which FOLLOWS from the three tables being distinct and so could not
    fail. What can fail is the count of records the original leaves carrying the entry type."""
    slot = wb("ACTOR_FOLLOWED_SLOT") * ACTOR_RECORD_BYTES
    assert ACTOR_FOLLOWED == (wb("ACTOR_TABLE_DEFAULT") + slot, wb("ACTOR_TABLE_A32") + slot), (
        "WB_ACTOR_FOLLOWED_* are no longer slot WB_ACTOR_FOLLOWED_SLOT of their tables")
    written = leaf.program_writes(_run_stage_actors_init(STATE_FLAG_SET))
    shaped = [table + record * ACTOR_RECORD_BYTES
              for table in ACTOR_TABLES for record in range(ACTOR_TABLE_RECORDS)
              if _word_written(written, table + record * ACTOR_RECORD_BYTES + wb("ACTOR_TYPE"))
              == wb("ACTOR_TYPE_PLAYER")]
    assert shaped == list(ACTOR_FOLLOWED), (
        f"the original left WB_ACTOR_TYPE_PLAYER in {[hex(a) for a in shaped]}, not in the two "
        f"followed records — so either A30 got one or one of the other two did not")


def _word_written(written, at):
    """The WORD the oracle's write set left at `at`. Every byte of these tables is written by the
    run (actor_table_reset covers them), so a missing byte is a real failure and not a gap."""
    return (written[at] << 8) | written[at + 1]


# --- the per-stage dispatcher ($e5ba / $e5d8 / $e5fe) ----------------------------------------------
# One straight-line block with `bsr load_resource_by_index` in the middle of it, so it is entered in
# three places and diffed in three. Each piece's `stop_pc` is the next piece's entry.

_SEQ_RESOURCE = leaf.register_glue("stage_sequence_resource", [ctypes.c_uint32], ctypes.c_uint32)
_SEQ_APPLY = leaf.register_glue("stage_sequence_apply_row", [ctypes.c_uint32])
# THE THREE PIECES INTERLEAVE rather than following one another: `stage_sequence_resource`'s three
# instructions sit INSIDE `stage_sequence_advance`'s run, between the row arithmetic and the two
# WB_STAGE_SECOND_LOAD_FLAG stores. They write nothing, so running the whole of $e5ba..$e5f2 diffs
# the advance correctly; entering at $e5d8 diffs the index computation on its own.
SEQ_ADVANCE_END = wb("SEQ_ADVANCE_END")
SEQ_RESOURCE_END = wb("SEQ_RESOURCE_END")
SEQ_APPLY_END = wb("SEQ_APPLY_END")


def _row_of(index):
    return LEVEL_SEQ_TABLE + index * LEVEL_SEQ_RECORD_BYTES


@pytest.mark.parametrize("reentry", [0, 1])
@pytest.mark.parametrize("index", [0, 1, LEVEL_SEQ_ROWS - 1])
def test_the_dispatcher_takes_its_row_and_steps_the_index(index, reentry):
    """$e5ba..$e5f2 over the shipped table, at both arms of WB_LIFE_RESTART_ENTRY_C26.

    THE RE-ENTRY ARM IS WHAT STOPS THE SECOND LOAD RUNNING TWICE: `clr.b` unconditionally, then the
    row's byte only while that word is zero. A port that wrote the row's byte either way would put
    the boot back through SPRITES.CRU — and the Copylock with it — every time a life is lost."""
    what = f"stage_sequence_advance at row {index}, reentry {reentry}"
    pokes = {LEVEL_SEQ_INDEX: index.to_bytes(WORD_LEN, "big"),
             LIFE_RESTART_ENTRY_C26: reentry.to_bytes(WORD_LEN, "big"),
             STAGE_SECOND_LOAD_FLAG: bytes([POISON]),
             ACTOR_PLATFORM_RIDDEN: bytes([POISON]) * WORD_LEN}
    info = leaf.run("stage_sequence_advance",
                    leaf.image_glue("stage_sequence_advance", ctypes.c_uint32),
                    [(ACTOR_PLATFORM_RIDDEN, WORD_LEN), (LEVEL_SEQ_INDEX, WORD_LEN),
                     (STAGE_SECOND_LOAD_FLAG, 1)], what,
                    regs={"_pokes": pokes}, stop_pc=SEQ_ADVANCE_END)
    assert info["ret"] == _row_of(index), (
        f"{what}: the port returned {info['ret']:#x} as the row, not {_row_of(index):#x}")
    assert info["regs"]["a0"] == _row_of(index), (
        f"{what}: the ORIGINAL left a0 at {info['regs']['a0']:#x}, so this case's row model is "
        f"wrong and the two halves below would be diffed against the wrong record")


@pytest.mark.parametrize("index", range(wb("LEVEL_SEQ_ROWS")))
def test_every_shipped_sequence_row_names_a_resource_and_a_stage(index):
    """The corpus case: all 35 rows, through both halves the load sits between. What it exercises
    that a single row cannot is the SPREAD of the four bytes — every overlay ordinal the game ships,
    both values of the side byte, and every stage number `level_seq_table` produces."""
    row = _row_of(index)
    what = f"stage_sequence_resource on row {index}"
    info = leaf.run("stage_sequence_resource", _SEQ_RESOURCE(row), [], what,
                    regs={"a0": row}, stop_pc=SEQ_RESOURCE_END)
    # THE IMAGE DIFF IS VACUOUS HERE — the routine writes nothing, so `leaf.run` comparing two
    # untouched images proves nothing about it. Its whole output is d0, and the comparison that
    # means something is the candidate's return against the ORACLE'S OWN register.
    assert info["ret"] == info["regs"]["d0"], (
        f"{what}: the port returned {info['ret']:#x} and the original left d0 at "
        f"{info['regs']['d0']:#x}")
    assert RESOURCE_FIRST_OVERLAY <= info["ret"] < wb("RESOURCE_TILEDATA"), (
        f"row {index} names resource {info['ret']}, which is not one of the overlays")
    pokes = {STAGE_SIDE_FLAG: bytes([POISON]) * WORD_LEN,
             STAGE_NUMBER: bytes([POISON]) * WORD_LEN}
    leaf.run("stage_sequence_apply_row", _SEQ_APPLY(row),
             [(STAGE_SIDE_FLAG, WORD_LEN), (STAGE_NUMBER, WORD_LEN)],
             f"stage_sequence_apply_row on row {index}",
             regs={"a0": row, "_pokes": pokes}, stop_pc=SEQ_APPLY_END)


def test_the_overlay_ordinal_is_added_in_eight_bits():
    """`addq.b #2,d0` on a zero-extended byte, so $fe wraps to 0 rather than reaching row 256.
    No shipped row does it — the census above says every ordinal is small — so this is driven on a
    POKED row, which is what makes the wrap reachable at all rather than merely arguable."""
    row = _row_of(0)
    for ordinal, want in ((0, RESOURCE_FIRST_OVERLAY), (0xfd, 0xff), (0xfe, 0), (0xff, 1)):
        pokes = {row + LEVEL_SEQ_OVERLAY: bytes([ordinal])}
        info = leaf.run("stage_sequence_resource", _SEQ_RESOURCE(row), [],
                        f"stage_sequence_resource on a poked ordinal of {ordinal:#x}",
                        regs={"a0": row, "_pokes": pokes},
                        stop_pc=SEQ_RESOURCE_END)
        assert info["ret"] == info["regs"]["d0"] == want, (
            f"an ordinal of {ordinal:#x} gave {info['ret']:#x} with the original at "
            f"{info['regs']['d0']:#x}, not {want:#x} — the port's add is not an eight-bit one")


# --- the error arm: why it is CANDIDATE-ONLY, and what still pins it -------------------------------
#
# THE MODEL HAS EXACTLY TWO ANSWERS AND "THE DISK SAID NO" IS NOT ONE OF THEM. os.h's staged-file
# model serves a call or REFUSES it, and a refusal sets the shim's `g_unmodeled` so `emu.run` raises
# before any comparison happens. That is right — it is what stops a loader reading a file nobody
# staged from being falsely verified — but it means the oracle cannot be made to return a NEGATIVE
# `disk_load_file` result, so the arm the original takes on a disk error has no differential
# available to it. Not "hard"; unavailable.
#
# So the arm is driven candidate-only, and the case owes the reader what that is worth: it compares
# the port against a second statement of the original's own two instructions, which is weaker than
# the oracle and stronger than nothing. THE REMEDY IS A KIT CHANGE and is registered in ../STATUS.md:
# a staged name declared PRESENT BUT UNREADABLE, which is the one answer the two-valued model lacks.

def test_a_load_the_seam_refuses_clears_joy1_state_and_reports_the_error():
    """`clr.b joy1_state` is the error arm's only image write — the red colour 0 beside it is off the
    image, and the interactive retry after it is a spin this port declines to model.

    THE PREMISE IS THE REFUSAL, and it is staged by staging NOTHING: the poke dict carries no file at
    all, so `os_fopen` finds no entry for TITLESCR.RAD's row and refuses. The control below is what
    says the refusal is doing the work rather than the arm being the port's only answer."""
    pokes = {JOY1_STATE: bytes([POISON])}
    ret, image = leaf.run_candidate_only(_LOAD_RESOURCE(wb("RESOURCE_TITLESCR"), DST_AT), pokes)
    assert ret == LOAD_DISK_ERROR, (
        f"a load with nothing staged returned {ret}, not WB_LOAD_DISK_ERROR — the port did not take "
        f"the error arm, so neither of this case's claims is about that arm")
    assert image[JOY1_STATE] == 0, (
        f"the error arm left joy1_state at {image[JOY1_STATE]:#x}, so it did not make the one image "
        f"write the original makes before it starts waiting for fire")
    # ...and the control, so the case cannot pass because every run reports the error.
    data = (BIN / DISK2 / "DATADISK.RAD").read_bytes()
    served, image = leaf.run_candidate_only(_LOAD_RESOURCE(wb("RESOURCE_DATADISK"), DST_AT),
                                            {**seam_pokes([("DATADISK.RAD", data)]), **pokes})
    assert served == LOAD_OK and image[JOY1_STATE] == POISON, (
        f"the same call WITH the file staged returned {served} and left joy1_state at "
        f"{image[JOY1_STATE]:#x} — so this case would pass whether or not the refusal did anything")


def test_a_read_that_leaves_the_image_is_a_failed_load_and_not_a_successful_one():
    """The seam's OTHER failure, which is a different branch of tools/recreate_kit/src/disk.c: the
    file OPENS and the READ refuses. `os_fread` refuses a copy that would run off the end of the
    image, so a destination near the top reaches it — and it is the only way to reach it, since
    every other refusal happens at the `Fopen`.

    Without this the `got < 0` arm is unreachable and a port that returned DISK_READ_OK regardless
    would be green, which a mutation sweep demonstrated."""
    data = (BIN / DISK2 / "DATADISK.RAD").read_bytes()
    over_the_top = harness.OS_IMAGE_SIZE - len(data) // 2
    ret, _ = leaf.run_candidate_only(_LOAD_RESOURCE(wb("RESOURCE_DATADISK"), over_the_top),
                                     seam_pokes([("DATADISK.RAD", data)]))
    assert ret == LOAD_DISK_ERROR, (
        f"a {len(data)}-byte read at {over_the_top:#x} — which runs {len(data) // 2} bytes past the "
        f"{harness.OS_IMAGE_SIZE:#x} image — returned {ret}, not WB_LOAD_DISK_ERROR")


def test_the_one_boot_resource_the_model_cannot_stage_is_the_one_named():
    """WHY FOUR LOADS AND NOT FIVE, measured rather than asserted. `SPRITES.CRU` is larger than the
    whole staging area the model has to lay files in, so it cannot be staged at all and its load has
    no differential. The boundary between "pinned" and "not" is a SIZE, and a case is where a size
    belongs — prose would drift the day the staging area moved.

    It also checks the complement: every OTHER boot resource DOES fit, so "four" is not four
    arbitrary files but the whole of what is stageable."""
    sizes = {"TITLESCR.RAD": (BIN / "disk1" / "TITLESCR.RAD").stat().st_size,
             "CREDITS.RAD": (BIN / "disk1" / "CREDITS.RAD").stat().st_size,
             "TILEDATA.RAD": (BIN / DISK2 / "TILEDATA.RAD").stat().st_size,
             "DATADISK.RAD": (BIN / DISK2 / "DATADISK.RAD").stat().st_size,
             "SPRITES.CRU": (BIN / DISK2 / "SPRITES.CRU").stat().st_size}
    too_big = sorted(name for name, size in sizes.items() if size > STAGING_CAPACITY)
    assert too_big == ["SPRITES.CRU"], (
        f"the boot resources that do not fit the model's {STAGING_CAPACITY} bytes of staging are "
        f"{too_big}, not the one ../STATUS.md names")


@pytest.mark.parametrize("at,offset", [(0x1000, -0x8000), (0x1fff, -8), (0x2000, 0)])
def test_the_sequence_index_is_scaled_as_a_longword_and_indexed_as_a_signed_word(at, offset):
    """`lsl.l #3` then `lea 0(a0,d0.w)` — the SAME pairing `load_resource_by_index` has, and the
    banner in src/boot.c claims they are the same rule. That claim had no case: the shipped table has
    35 rows, so nothing drove an index whose scaled value leaves sixteen bits, and deleting the sign
    extension was green across the whole suite. The three indices here are where the two mistakes a
    port can make diverge — $1000 scales to exactly $8000 and reads NEGATIVE, $1fff is the last row
    below that, and $2000 wraps to the table itself.

    A REAL DIFFERENTIAL, not a census: the routine READS the row it computes (`move.b 1(a0)` into
    stage_second_load_flag), so wherever the address lands the original fetches a byte from it and
    the port must fetch the same one. `offset` is this case's independent model of the arithmetic —
    computed here from the 68000's rule rather than taken from the port."""
    what = f"stage_sequence_advance at a sequence index of {at:#x}"
    row = (LEVEL_SEQ_TABLE + offset) & (harness.OS_IMAGE_SIZE - 1)
    assert offset == 0 or row != LEVEL_SEQ_TABLE, f"{what}: this index does not move the row at all"
    pokes = {LEVEL_SEQ_INDEX: at.to_bytes(WORD_LEN, "big"),
             LIFE_RESTART_ENTRY_C26: bytes(WORD_LEN),
             STAGE_SECOND_LOAD_FLAG: bytes([POISON]),
             ACTOR_PLATFORM_RIDDEN: bytes([POISON]) * WORD_LEN}
    info = leaf.run("stage_sequence_advance",
                    leaf.image_glue("stage_sequence_advance", ctypes.c_uint32),
                    [(ACTOR_PLATFORM_RIDDEN, WORD_LEN), (LEVEL_SEQ_INDEX, WORD_LEN),
                     (STAGE_SECOND_LOAD_FLAG, 1)], what,
                    regs={"_pokes": pokes}, stop_pc=SEQ_ADVANCE_END)
    assert info["ret"] == info["regs"]["a0"] == row, (
        f"{what}: the port returned {info['ret']:#x} and the original left a0 at "
        f"{info['regs']['a0']:#x}; the 68000's own arithmetic gives {row:#x}")
