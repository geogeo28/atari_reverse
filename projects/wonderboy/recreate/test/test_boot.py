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

import harness
import leaf
from layout import wb

import depack_rad                                              # noqa: E402  (harness put tools/ on
import emu                                                     # noqa: E402   sys.path)
import loader                                                  # noqa: E402

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

OVERLAY_AT = 0x217d8                   # `lea $217d8.l,a1` at $e63e — where every OVALAY*.RAD depacks
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
