"""The IMAGE MODEL: that `test/conftest.py`'s post-load fixture is what Flying Shark's own boot
chain builds, and that the harness's fixed regions do not sit on top of it.

Nothing else in this project can be trusted until this file is green, because every differential
case is staged on that image. The fixture is a REPLAY of the original — three slices of the game's
own code run under the oracle (`conftest.py`'s docstring has them) — so what is left to pin is that
each slice is entered where it is claimed to be, that the parts of the chain the replay cannot keep
are the routine's own arithmetic, and that the whole thing agrees with an independent transcription:

* **the load** — the relocated TEXT + DATA in the image are the `.PRG`'s own bytes, sliced out of the
  file and fixed up by this test rather than by the loader, and the segment bounds
  `include/globals.h` states are the ones its header states;
* **the ring** — running the real `boot_init` @ 0x14bee must derive the nine screen pointers
  `conftest.ring_pointers()` derives, at the model's own Physbase; and running its arithmetic alone,
  entered past the `Physbase` trap, must derive them at a Physbase of the case's choosing, including
  one whose base is not already 256-aligned. The fixture then re-places them at the harness's
  Physbase, which is the one part of the chain the replay does not keep;
* **the loads** — running the real `load_file` @ 0x10bfa on each of the seven records the boot chain
  feeds it, one staged file at a time, must place the same bytes at the same address the fixture
  holds them at;
* **the relocation** — running the real sprite-directory fix-up @ 0x112c2 over an image holding the
  raw A\\SPRITES.cru bytes must produce the fixture's 256 pointers and its four restore-list
  terminators;
* **the second opinion** — the fixture and `conftest.install_boot_state`'s hand transcription must
  agree over the WHOLE image outside three named bands. When they do not, the replay is right.

...and then the free-space census: that the screen ring, `test/abi.py`'s scratch map, the program
and the TOS model's staged-file table are four disjoint regions.
"""
import sys

import pytest

import abi
import conftest
import emu
import harness

import loader
from test_constants import check_entry_prologues, check_mirrors

# `include/globals.h`'s memory model, mirrored here; MIRRORS at the bottom pins each one equal.
FS_LOAD_BASE = 0x10000
FS_TEXT_BYTES = 0x59f4
FS_DATA_BYTES = 0x6442
FS_BSS_BYTES = 0x3f0a8
FS_DATA_BASE = 0x159f4
FS_BSS_BASE = 0x1be36
FS_PROGRAM_END = 0x5aede
A_stack_top = 0x19094
A_saved_super_ssp = 0x19014
A_sprite_bank = 0x1be36
A_tile_banks = 0x38928
TILE_BANK_BYTES = 0x8000
TILE_BANKS = 4
A_level_map_cols = 0x16432
A_sound_module_file = 0x58928
A_sound_module = 0x58944
SOUND_MODULE_HEADER_BYTES = 28
A_entity_arena = 0x59984
ENTITY_SLOTS = 91
ENTITY_STRIDE = 58
MODULE_OVER_ARENA_BYTES = 9
SCREEN_RING_BYTES = 0x1f900
SCREEN_BYTES = 0x7d00

# ---- the addresses this file drives, beyond the slices conftest.py declares ----------------------
ENTRY_LOAD_FILE = 0x10bfa            # `movem.l d0-d7/a0-a6,-(a7)` — a0 -> a file record
ENTRY_SPRITE_RELOC = 0x112c2         # `lea $1be36,a0` — init_load_assets' directory fix-up
# `subi.l #$1f900,d0` @ 0x14c26 — boot_init's ring arithmetic, entered one instruction PAST its XBIOS
# `Physbase` trap so that d0 is the case's own choice, and stopped at the `movea.l #$16304,a0`
# @ 0x14c9e that sets up the load after it.
ENTRY_RING_ARITHMETIC = 0x14c26
STOP_RING_ARITHMETIC = 0x14c9e
# A Physbase whose ring base is NOT already 256-aligned, so the `clr.b d0` @ 0x14c40 changes the
# answer: 0x7f8ab - 0x1f900 + 0x100 = 0x600ab, which the rounding takes down to 0x60000. Every
# Physbase the fixture itself uses is aligned, so without a case at an unaligned one the masking
# half of the formula is transcribed and never checked.
UNALIGNED_PHYSBASE = 0x7f8ab
# The directory fix-up is `dbf`-bounded at 256 iterations of three instructions, plus four stores.
SPRITE_RELOC_MAX_INSNS = 10_000

# `load_file` @ 0x10bfa takes its record in A0 (`../names.txt`: `proto 0x10bfa record@A0`).
LOAD_FILE_RECORD_REG = "a0"

# ---- where the replay and the transcription are allowed to differ --------------------------------
#
# THE GAME'S OWN STACK. `boot_init` opens `movea.l #$19094,a7` and then makes four trap calls, whose
# argument pushes and return frames land just below `A_stack_top` — inside the bss, and the harness
# has no guard band there because it is not the harness's stack. The band is bounded below by the
# saved-SSP longword the routine itself writes.
BOOT_STACK_BAND = (A_saved_super_ssp + 4, A_stack_top)
# THE LOADER'S SCRATCH, which `load_file` fills in and the transcription does not model:
# load_file_handle.w, load_dest.l, load_len.l — one contiguous run of ten bytes at 0x17774. The
# replay carries the last load's values; a handle out of the staged-file model would be a number
# about the harness rather than about the game, which is why the transcription has none.
LOADER_SCRATCH_BAND = (0x17774, 0x1777e)
# THE TITLE PICTURE, copied to `Physbase - TITLE_COPY_OFFSET` by the slice that loads it. It lands in
# the model's own framebuffer, which no frame-loop routine reads; the transcription skips the whole
# file for that reason, and the replay necessarily carries it.
TITLE_COPY_BAND = (harness.OS_SCREEN_BASE - conftest.TITLE_COPY_OFFSET,
                   harness.OS_SCREEN_BASE - conftest.TITLE_COPY_OFFSET + conftest.TITLE_COPY_BYTES)


def _loaded_image(pokes=None):
    """An image built from the .PRG AS LOADED, plus `pokes` = {address: bytes}.

    NOT `harness.make_image()`, and the difference is the point of this file: `make_image` builds on
    whatever `set_base_image` installed, and `conftest.py`'s autouse fixture installs the POST-LOAD
    image. That is the right default for a differential and exactly wrong for a boot-chain pin — a
    run staged on the fixture would be running the boot chain over a machine that had already
    booted, and would agree with it having proved nothing. (Measured: the `$70` vector pin came
    back holding `vbl_handler` because the fixture had already installed it.)
    """
    image = bytearray(harness.BASE_IMAGE)
    for address, data in (pokes or {}).items():
        assert address + len(data) <= len(image), f"a poke at {address:#x} runs past the image"
        image[address:address + len(data)] = data
    return image


def _staged(files):
    """An image on the .PRG as loaded, with `files` = [(dos path, bytes)] staged for the TOS model."""
    pokes, handles = harness.stage_files(files)
    return _loaded_image(pokes), handles


def _outside(allowed, length):
    """The (lo, hi) spans of [0, length) that no span in `allowed` covers, in address order."""
    gaps, cursor = [], 0
    for lo, hi in sorted(allowed):
        if lo > cursor:
            gaps.append((cursor, min(lo, length)))
        cursor = max(cursor, hi)
    if cursor < length:
        gaps.append((cursor, length))
    return gaps


def _differing(left, right, allowed):
    """The addresses at which `left` and `right` differ, outside every (lo, hi) span in `allowed`.

    Compared span by span with `bytes.__eq__` rather than byte by byte in Python: the whole point is
    that the two agree, and the agreeing case is 1 MiB of memcmp instead of a million comparisons.
    Only a span that really differs is then walked to name its addresses.
    """
    left, right = bytes(left), bytes(right)
    return [address
            for lo, hi in _outside(allowed, len(left)) if left[lo:hi] != right[lo:hi]
            for address in range(lo, hi) if left[address] != right[address]]


# ==================================================== the load


def test_the_loaded_image_holds_the_prgs_own_text_and_data():
    """`harness.BASE_IMAGE` over [load_base, DATA end) must be the .PRG's TEXT+DATA, relocated.

    Built INDEPENDENTLY OF THE LOADER: the segments are sliced straight out of the file after its
    28-byte header and every fixup in the relocation table is applied here, by this test. Comparing
    a second `loader.load_image()` against the first could only ever have said the loader was
    deterministic — a segment placed 0x1c bytes out, or a fixup applied at the wrong offset, agrees
    with itself perfectly.
    """
    prg = harness.PRG.read_bytes()
    head = loader.prg_dis.parse_header(prg)
    assert (head["tlen"], head["dlen"], head["blen"]) == (FS_TEXT_BYTES, FS_DATA_BYTES, FS_BSS_BYTES)
    assert loader.LOAD_BASE == FS_LOAD_BASE and loader.PROGRAM_END == FS_PROGRAM_END

    segments = bytearray(prg[loader.prg_dis.HEADER_LEN:
                             loader.prg_dis.HEADER_LEN + FS_TEXT_BYTES + FS_DATA_BYTES])
    fixups = loader.prg_dis.parse_reloc(prg, head)
    assert fixups, "the .PRG's relocation table is empty — nothing would be fixed up here"
    for offset in fixups:
        patched = int.from_bytes(segments[offset:offset + 4], "big") + FS_LOAD_BASE
        segments[offset:offset + 4] = (patched & 0xffffffff).to_bytes(4, "big")
    assert bytes(harness.BASE_IMAGE[FS_LOAD_BASE:FS_LOAD_BASE + len(segments)]) == bytes(segments)


def test_the_segment_bounds_are_the_headers_own_arithmetic():
    """`include/globals.h`'s three boundaries, re-derived from the header rather than restated."""
    assert FS_LOAD_BASE + FS_TEXT_BYTES == FS_DATA_BASE
    assert FS_DATA_BASE + FS_DATA_BYTES == FS_BSS_BASE
    assert FS_BSS_BASE + FS_BSS_BYTES == FS_PROGRAM_END == loader.PROGRAM_END
    assert A_sprite_bank == FS_BSS_BASE, "A\\SPRITES.cru is loaded to the first byte of the bss"


def test_the_bss_the_loader_leaves_is_all_zeroes():
    """The positive control for the fixture: everything it installs into the bss lands on zeroes.

    Without this, "the fixture differs from BASE_IMAGE" below would be satisfied by a .PRG that
    shipped its tile banks in the file — and every claim about what the boot chain writes would be
    about bytes that were already there. `test_the_fixture_is_not_the_bare_image` counts the
    fixture's non-zero bss bytes, which is only the same as "bytes it changed" because of this.
    """
    assert not any(harness.BASE_IMAGE[FS_BSS_BASE:FS_PROGRAM_END])


def test_the_entity_arena_fills_the_bss_up_to_the_next_array():
    """91 records of 58 bytes ends exactly where `../names.txt` puts `player_bullet_arena`.

    The one piece of arithmetic in `include/globals.h` that is not a header field, and the one a
    later `include/entity.h` will index by — so it is worth holding rather than believing.
    """
    assert A_entity_arena + ENTITY_SLOTS * ENTITY_STRIDE == 0x5ae22
    assert A_entity_arena + ENTITY_SLOTS * ENTITY_STRIDE < FS_PROGRAM_END


def test_the_sound_module_base_is_the_files_own_header_arithmetic():
    """`A_sound_module` = `A_sound_module_file` + the header of the .PRG that A\\MODULE.BAK IS.

    The game calls the module through `lea $58944,a0` and never strips the header, so that 28 is a
    fact about the FILE. Read out of A\\MODULE.BAK's own header rather than restated, so a module
    rebuilt with a different header length fails here rather than in a sound battery's diff.
    """
    assert A_sound_module == A_sound_module_file + SOUND_MODULE_HEADER_BYTES
    assert loader.prg_dis.HEADER_LEN == SOUND_MODULE_HEADER_BYTES
    _dest, length, _path = conftest.file_record(harness.BASE_IMAGE, conftest.A_file_rec_module_bak)
    module = loader.prg_dis.parse_header(conftest.disk_bytes("MODULE.BAK", length))
    assert module["tlen"] + module["dlen"] > 0, "A\\MODULE.BAK does not parse as a .PRG"


def test_the_sound_module_overlaps_the_entity_arena_by_nine_bytes(post_load_image,
                                                                 post_new_game_image):
    """`include/globals.h`, "THE SOUND MODULE OVERLAPS THE ARENA": the size, and both sides of it.

    Pinned so that an arena or a record that MOVES fails by name here rather than by nine silent
    bytes in a sound table nobody reads twice. Both images are asserted, because the whole claim is
    that the overlap exists after the load and is gone after `clear_actor_arrays` @ 0x115e2 — a
    fixture that had zeroed the arena for its own reasons would satisfy half of it.
    """
    _dest, length, _path = conftest.file_record(harness.BASE_IMAGE, conftest.A_file_rec_module_bak)
    assert A_sound_module_file + length - A_entity_arena == MODULE_OVER_ARENA_BYTES
    overlap = slice(A_entity_arena, A_entity_arena + MODULE_OVER_ARENA_BYTES)
    module_tail = conftest.disk_bytes("MODULE.BAK", length)[-MODULE_OVER_ARENA_BYTES:]
    assert bytes(post_load_image[overlap]) == module_tail
    assert any(module_tail), "the overlap is all zeroes, so neither half of this case says anything"
    assert not any(post_new_game_image[overlap]), (
        "init_new_game left the module's tail over entity slot 0 — clear_actor_arrays @ 0x115e2 "
        "byte-clears 0x59984..0x5aede and is what makes the overlap harmless")


# ==================================================== the boot slice


@pytest.fixture(scope="module")
def boot_slice():
    """What the REAL `boot_init` leaves at STOP_BOOT_SLICE — the fixture's own first slice, run
    again here so the pins below are on the routine and not on the fixture's copy of its result."""
    return conftest.replay_boot_init(bytearray(harness.BASE_IMAGE))


def test_the_boot_slice_derives_the_ring_from_its_own_physbase(boot_slice):
    """THE PIN UNDER `conftest.ring_pointers`: nine longwords, against the routine that makes them.

    The oracle's XBIOS `Physbase` answers `OS_SCREEN_BASE`, so this compares the fixture's formula
    at THAT Physbase — not at the one the fixture uses. What is pinned is the arithmetic; where the
    harness then puts the ring is `abi.SCREEN_RING_PHYSBASE`, and the census below is what makes
    that placement legal. The two are deliberately separate: a single test that did both could be
    satisfied by a formula that happened to agree at one input.
    """
    expected = conftest.ring_pointers(harness.OS_SCREEN_BASE)
    actual = {address: int.from_bytes(boot_slice[address:address + 4], "big")
              for address in expected}
    assert actual == expected, (
        "boot_init's nine screen pointers are not conftest.ring_pointers()'s — "
        + ", ".join(f"{a:#x}: {actual[a]:#010x} vs {expected[a]:#010x}"
                    for a in sorted(expected) if actual[a] != expected[a]))
    assert len(conftest.RING_SLOT_POINTERS) == conftest.SCREEN_RING_SLOTS, (
        "boot_init keeps SCREEN_RING_SLOTS rotating bases and conftest lists a different number, "
        "so the comparison above covers only the ones it lists")
    # ...and the model's Physbase really does underflow, which is the whole reason the fixture
    # re-places the ring instead of taking this answer. A day when it stops is a day to re-read
    # abi.py's placement argument rather than to quietly keep the workaround.
    assert expected[conftest.A_screen_ring_base_raw] > harness.OS_SCREEN_BASE


@pytest.mark.parametrize("physbase,rounding_matters",
                         ((abi.SCREEN_RING_PHYSBASE, False), (UNALIGNED_PHYSBASE, True)),
                         ids=("aligned", "unaligned"))
def test_the_ring_arithmetic_is_the_originals_at_a_physbase_of_our_own(physbase,
                                                                      rounding_matters):
    """THE `clr.b`'S OWN PIN: the real arithmetic, driven at a Physbase the model cannot answer.

    The case above runs the whole routine, and can only ever run it at `OS_SCREEN_BASE` — whose ring
    base is already 256-aligned, as the harness's chosen one is. So the ROUNDING half of the formula
    goes unexercised there: dropping the mask from `conftest.ring_pointers` leaves both of them
    unchanged and the suite green (measured 2026-09-07). Entering `boot_init` one instruction past
    its `Physbase` trap puts d0 in the case's hands, so the mask can be pinned against the
    instruction that performs it rather than against the transcription of it.
    """
    raw = (physbase - conftest.SCREEN_RING_BYTES) & 0xffffffff
    assert bool((raw + conftest.SCREEN_RING_ALIGN) & (conftest.SCREEN_RING_ALIGN - 1)) \
        == rounding_matters, (
        f"{physbase:#x} no longer says what this case was parametrised to say about the `clr.b`")
    final, _writes, _regs = emu.run(_loaded_image(), ENTRY_RING_ARITHMETIC, regs={"d0": physbase},
                                    stop_pc=STOP_RING_ARITHMETIC)
    expected = conftest.ring_pointers(physbase)
    actual = {address: int.from_bytes(final[address:address + 4], "big") for address in expected}
    assert actual == expected, (
        f"boot_init's ring arithmetic at Physbase {physbase:#x} is not conftest.ring_pointers()'s — "
        + ", ".join(f"{a:#x}: {actual[a]:#010x} vs {expected[a]:#010x}"
                    for a in sorted(expected) if actual[a] != expected[a]))


def test_the_boot_slice_really_wrote_the_things_it_is_pinned_on(boot_slice):
    """The positive control for the replay's first slice, which an inert run would pass.

    `boot_init` chains, installs and loads; if the run had stopped at its first instruction the
    comparisons around it would hold vacuously, since the fixture would then be compared against the
    image it was built from.
    """
    def long_at(address):
        return int.from_bytes(boot_slice[address:address + 4], "big")

    assert long_at(A_saved_super_ssp) == harness.OS_SUPER_TOKEN
    assert long_at(conftest.VECTOR_VBL) == conftest.FN_VBL_HANDLER
    assert long_at(conftest.VECTOR_ACIA) == conftest.FN_ACIA_IKBD_ISR
    assert long_at(conftest.A_vbl_chain_vector) == 0, (
        "the model has no TOS vector at $70, so the `jmp` operand boot_init copies there is 0 — "
        "see conftest.py, 'what it does not hold'")
    _dest, length, _path = conftest.file_record(harness.BASE_IMAGE, conftest.A_file_rec_module_bak)
    module = conftest.disk_bytes("MODULE.BAK", length)
    assert bytes(boot_slice[A_sound_module_file:A_sound_module_file + len(module)]) == module


# ==================================================== the replay itself


def test_the_staging_window_is_why_the_replay_is_split():
    """The arithmetic `conftest.py` splits `init_load_assets` on, held rather than believed.

    The model stages every file in one window and the seven the boot chain loads nearly fill it, so
    the title picture cannot be staged beside them and the replay runs two sub-slices. That is a
    limit, not a preference: if the window ever grew past both, this case is the one that says the
    split can go — and if the files ever grew past the window, it is the one that says the fixture
    cannot be built this way at all, rather than leaving a `stage_files` assertion to say it.
    """
    window = emu.STACK_GUARD_LO - harness.OS_FS_STAGING
    staged = [conftest.staged_load(harness.BASE_IMAGE, *load) for load in conftest.BOOT_LOADS]
    seven = sum(len(data) for _path, data in staged)
    _path, title = conftest.staged_load(harness.BASE_IMAGE, *conftest.TITLE_LOAD)
    assert seven <= window, (
        f"the {len(staged)} boot files are {seven} bytes and the staging window "
        f"[{harness.OS_FS_STAGING:#x}, {emu.STACK_GUARD_LO:#x}) is {window} — the asset slice "
        f"cannot stage them all, so the replay cannot be built")
    assert seven + len(title) > window, (
        f"A\\FLY_SHK.NEO's {len(title)} bytes now fit beside the other {seven}, with {window} of "
        f"window: `init_load_assets` no longer has to be replayed in two sub-slices, and "
        f"conftest.ENTRY_LEVEL0_ASSETS can go")


def test_the_replay_and_the_transcription_agree(post_load_image):
    """THE FIXTURE'S SECOND OPINION: the replayed image against `conftest.install_boot_state`.

    An exhaustive difference rather than a list of spot checks: every byte the two disagree on must
    lie in one of three NAMED bands — the game's own stack, the loader's scratch, and the title
    picture in the model's framebuffer, all three of them things the transcription deliberately does
    not model. A store one side invented, misplaced or dropped fails here BY ADDRESS, which is what
    a list of spot checks could never do.

    WHEN THEY DISAGREE THE REPLAY IS RIGHT: it is the program's own code, and the transcription is a
    reading of it. That is not hypothetical — `A_level0_assets_loaded` (`st $176ea` @ 0x112b2) is in
    `install_boot_state` because this case found the transcription had missed it.
    """
    expected = conftest.install_boot_state(bytearray(harness.BASE_IMAGE), abi.SCREEN_RING_PHYSBASE)
    allowed = (BOOT_STACK_BAND, LOADER_SCRATCH_BAND, TITLE_COPY_BAND)
    differing = _differing(post_load_image, expected, allowed)
    assert not differing, (
        f"the replayed fixture and conftest.install_boot_state's transcription differ at "
        f"{len(differing)} byte(s) outside the named bands, the first at {differing[0]:#x} "
        f"(replay {post_load_image[differing[0]]:#04x}, transcription {expected[differing[0]]:#04x})"
        f" — the REPLAY is the truth; find the store the transcription is missing")


def test_the_replay_carries_the_title_picture_the_transcription_skips(post_load_image):
    """The positive control for the widest allowed band: something really is copied into it.

    TITLE_COPY_BAND is 32,000 bytes of the diff above waved through, so a slice that silently failed
    to run the copy loop would make that case easier to pass rather than harder.

    The band's WIDTH is held by two facts and not by the loop count alone, because a NEOchrome
    picture ends in zeroes and the transcription's zeroes agree with them: the copy is exactly one
    screen (`SCREEN_BYTES`), and one screen plus the 128-byte NEO header the copy starts from is
    exactly what A\\FLY_SHK.NEO's record asks Fread for — which is the whole "the header lands just
    below the screen and the pixels land on it" arrangement (`../names.txt`, `cmt 0x11212`).
    """
    lo, hi = TITLE_COPY_BAND
    _dest, length, _path = conftest.file_record(harness.BASE_IMAGE, conftest.A_file_rec_flyshk_neo)
    assert conftest.TITLE_COPY_BYTES == SCREEN_BYTES
    assert conftest.TITLE_COPY_OFFSET + SCREEN_BYTES == length
    assert bytes(post_load_image[lo:hi]) == conftest.disk_bytes("FLY_SHK.NEO", length)[:hi - lo]
    assert hi <= FS_LOAD_BASE, "the title copy reaches into the program, which it must not"


def test_the_fixture_carries_no_staged_files(post_load_image):
    """The harness's scaffolding is taken back out, so no case inherits an open-able file.

    The model answers `Fopen` out of the table at OS_FS_TABLE; a fixture that left the boot chain's
    seven entries there would let a case open a file the machine it models has not staged, and the
    candidate — which has no table at all — could not.
    """
    table = slice(harness.OS_FS_TABLE, harness.OS_IMAGE_SIZE)
    assert bytes(post_load_image[table]) == bytes(harness.BASE_IMAGE[table])


# ==================================================== the loads


@pytest.mark.parametrize("record,disk_name", conftest.BOOT_LOADS,
                         ids=[name for _record, name in conftest.BOOT_LOADS])
def test_load_file_places_each_record_where_the_fixture_does(record, disk_name, post_load_image):
    """THE PIN UNDER THE FILE PLACEMENTS: the real `load_file`, one staged file at a time.

    One file per run, entered at `load_file` itself, so what is pinned is the ROUTINE rather than the
    slice of the boot chain that happens to call it — and so a wrong `include/globals.h` address
    fails here by name. Each run reads its record's destination and length out of the image exactly
    as the routine does.
    """
    dest, length, dos_path = conftest.file_record(harness.BASE_IMAGE, record)
    data = conftest.disk_bytes(disk_name, length)
    image, _handles = _staged([(dos_path, data)])
    final, _writes, _regs = emu.run(image, ENTRY_LOAD_FILE, regs={LOAD_FILE_RECORD_REG: record})
    assert bytes(final[dest:dest + len(data)]) == data, f"{dos_path} did not land at {dest:#x}"
    assert any(data), f"{disk_name} is all zeroes, so this case would pass over an inert load"
    # ...and the fixture carries what the load left, EXCEPT the one span `init_load_assets`
    # rewrites afterwards: A\SPRITES.cru's 256-record directory, whose pointers it relocates in
    # place (@ 0x112cc). That span is the next section's, and skipping it here rather than
    # comparing a shorter file keeps every other record's check whole-file.
    skip = (conftest.SPRITE_RECORDS * conftest.SPRITE_RECORD_BYTES
            if record == conftest.A_file_rec_sprites_cru else 0)
    assert bytes(post_load_image[dest + skip:dest + len(data)]) == data[skip:], (
        f"the fixture does not carry {dos_path} at {dest + skip:#x}")


def test_the_records_name_the_addresses_globals_h_states():
    """`include/globals.h`'s file destinations, read back out of the (relocated) records.

    The two longwords of a record both carry relocation entries, so the image is the only place
    they are true — and a header that restated one wrongly would otherwise be believed by every
    core compiled against it.
    """
    destinations = {name: conftest.file_record(harness.BASE_IMAGE, record)[0]
                    for record, name in conftest.BOOT_LOADS}
    assert destinations["MODULE.BAK"] == A_sound_module_file
    assert destinations["SPRITES.CRU"] == A_sprite_bank
    assert destinations["LEVEL1.MAP"] == A_level_map_cols
    banks = [destinations[f"HSC_{n}.DAT"] for n in range(TILE_BANKS)]
    assert banks == [A_tile_banks + n * TILE_BANK_BYTES for n in range(TILE_BANKS)], (
        f"the four HSC banks are not {TILE_BANKS} contiguous {TILE_BANK_BYTES:#x}-byte slots from "
        f"A_tile_banks — read them out of the relocated records at "
        f"{conftest.A_file_rec_hsc_0:#x}..{conftest.A_file_rec_hsc_3:#x}, which is the only place "
        f"they are true, and correct include/globals.h to match")


def test_the_sprite_bank_ends_exactly_where_the_tile_banks_begin():
    """A\\SPRITES.cru's 0x1caf2 bytes fill 0x1be36..0x38928 with nothing to spare.

    Worth holding because it is what makes the bss layout self-checking: a sprite bank one record
    longer would silently overwrite tile 0, and no differential of a sprite routine would see it.
    """
    _dest, length, _path = conftest.file_record(harness.BASE_IMAGE, conftest.A_file_rec_sprites_cru)
    assert A_sprite_bank + length == A_tile_banks


# ==================================================== the relocation


def test_the_sprite_directory_relocation_is_the_originals(post_load_image):
    """THE PIN UNDER THE DIRECTORY AND THE RESTORE LISTS: the real fix-up loop @ 0x112c2.

    Entered at the `lea` that starts it and run to `init_load_assets`' own `rts`, so the four
    restore-list terminators after the loop are in the same run. The image it starts from carries
    A\\SPRITES.cru placed by hand — not by the fixture — so this compares the fixture's relocated
    directory against the original's, rather than against itself.
    """
    _dest, length, _path = conftest.file_record(harness.BASE_IMAGE, conftest.A_file_rec_sprites_cru)
    raw = conftest.disk_bytes("SPRITES.CRU", length)
    image = _loaded_image({A_sprite_bank: raw})
    final, _writes, _regs = emu.run(image, ENTRY_SPRITE_RELOC, max_insns=SPRITE_RELOC_MAX_INSNS)

    directory = conftest.SPRITE_RECORDS * conftest.SPRITE_RECORD_BYTES
    assert bytes(final[A_sprite_bank:A_sprite_bank + directory]) == \
        bytes(post_load_image[A_sprite_bank:A_sprite_bank + directory])
    lists = conftest.SPRITE_RESTORE_LISTS * conftest.SPRITE_RESTORE_LIST_BYTES
    base = conftest.A_sprite_restore_lists
    assert bytes(final[base:base + lists]) == bytes(post_load_image[base:base + lists])
    # ...and there are exactly FOUR lists, which is a fact about the original and not about the
    # constant: a fixture that wrote two would otherwise compare only the two spans it wrote.
    stride, first = conftest.SPRITE_RESTORE_LIST_BYTES, conftest.SPRITE_RESTORE_FIRST_ENTRY
    for index in range(conftest.SPRITE_RESTORE_LISTS):
        at = base + index * stride + first
        assert int.from_bytes(final[at:at + 2], "big") == conftest.SPRITE_RESTORE_TERMINATOR
    beyond = base + conftest.SPRITE_RESTORE_LISTS * stride + first
    assert final[beyond:beyond + 2] == harness.BASE_IMAGE[beyond:beyond + 2], (
        "the routine wrote a fifth restore-list terminator — there are four stores at "
        "0x112e0..0x112f2 and SPRITE_RESTORE_LISTS says so")
    # ...and it really relocated: record 0's pointer must have gained the bank's base address.
    before = int.from_bytes(raw[:4], "big")
    after = int.from_bytes(final[A_sprite_bank:A_sprite_bank + 4], "big")
    assert after == before + A_sprite_bank != before


# ==================================================== the fixture itself


def test_the_fixture_is_not_the_bare_image(post_load_image):
    """The positive control: the boot state really was installed, and into the bss.

    Every equality above is between two things this file builds, so a fixture that silently
    installed nothing at all would satisfy several of them by agreeing with a run that also did
    nothing. Counted as NON-ZERO bytes, which is the same as "bytes it changed" because
    `test_the_bss_the_loader_leaves_is_all_zeroes` holds the loaded bss at zero.
    """
    bss = post_load_image[FS_BSS_BASE:FS_PROGRAM_END]
    changed = len(bss) - bss.count(0)
    # The four tile banks alone are 128 KB of non-zero pixel data, so the bar below is far under
    # what a working fixture changes and is not a tuning knob.
    assert changed > 100_000, f"the fixture changed only {changed} bss bytes"


def test_every_differential_starts_from_the_post_load_image(post_load_image):
    """The autouse fixture's own surface: `harness.make_image()` must be the post-load image.

    Without it a battery that forgot to stage its case would run against zeroed tile banks and a
    null screen ring, and go green about a machine that never exists at run time — which is exactly
    the failure the fixture exists to make unforgettable, and which nothing else here would notice.
    """
    assert bytes(harness.make_image()) == post_load_image
    assert bytes(harness.make_image()) != bytes(harness.BASE_IMAGE)


def test_the_fixture_places_the_ring_where_abi_says(post_load_image):
    """...and the ring the fixture installed is the one the census below is about."""
    installed = {address: int.from_bytes(post_load_image[address:address + 4], "big")
                 for address in conftest.ring_pointers(abi.SCREEN_RING_PHYSBASE)}
    assert installed == conftest.ring_pointers(abi.SCREEN_RING_PHYSBASE)
    assert installed[conftest.A_screen_ring_base] == abi.SCREEN_RING_BASE


# ==================================================== the free-space census


def test_the_screen_ring_is_clear_of_the_program_and_the_staged_files():
    """THE PLACEMENT'S OWN CHECK. The ring is 0x27600 bytes of live game memory whose address the
    harness chose (`abi.py`, "where the harness puts the screen ring"), and the kit vets none of it:
    `_vet_os_memory_map` knows about the program, the heap and the file table, and knows nothing
    about a region a project invented. So this is the only thing between the ring and the program.
    """
    low, high = abi.SCREEN_RING_SPAN
    assert low == abi.SCREEN_RING_BASE
    assert high == low + SCREEN_RING_BYTES + SCREEN_BYTES, (
        "the span must cover the ring PLUS one frame read from its highest base — the four bases "
        "reach SCREEN_BYTES past the ring's top")
    assert low >= loader.PROGRAM_END, (
        f"the screen ring {low:#x} is inside the program, which ends at {loader.PROGRAM_END:#x}")
    assert high <= abi.STUB, (
        f"the screen ring reaches {high:#x}, into test/abi.py's scratch map at {abi.STUB:#x}")
    assert low >= harness.OS_HEAP_BASE or harness.OS_HEAP_BASE >= high, (
        "the modeled Malloc arena starts inside the ring")


def test_the_ring_placement_is_the_originals_arithmetic():
    """`abi.SCREEN_RING_BASE` must be what boot_init's formula gives for the chosen Physbase.

    Two spellings of one number — the address the census above is about, and the Physbase the
    fixture feeds the formula — so they are pinned equal rather than both maintained. The rounding
    is STRICTLY up, which is why the Physbase is 0x7f800 and not 0x7f900; a placement that assumed
    otherwise would put the ring 0x100 bytes from where every case reads it.
    """
    pointers = conftest.ring_pointers(abi.SCREEN_RING_PHYSBASE)
    assert pointers[conftest.A_screen_ring_base] == abi.SCREEN_RING_BASE
    assert (pointers[conftest.A_screen_ring_base_raw]
            == abi.SCREEN_RING_BASE - conftest.SCREEN_RING_ALIGN)


def test_this_files_own_pins():
    """`check_mirrors` and `check_entry_prologues` over THIS module and over `conftest`.

    Neither is a battery — there is no `src/image_model.c`, so `test_constants.py` discovers
    neither — and the memory model has to be pinned before any battery exists. `conftest.py`
    restates the same header constants to build the fixture with and names the four addresses the
    replay enters at, so both of its pin families are checked here too: without the first, a fixture
    relocating 128 sprite records instead of 256 would compare only the half it wrote, on both
    sides, and stay green; without the second, a slice could enter one instruction into a different
    routine and the replay would quietly build a different machine.
    """
    module = sys.modules[__name__]
    check_mirrors(module)
    check_entry_prologues(module)
    check_mirrors(conftest)
    check_entry_prologues(conftest)


# ==================================================== the pins this file declares
#
# Shaped like a battery's (README.md, "Adding a function") even though this is not one — there is no
# `src/image_model.c`, so `test_constants.py` does not discover it and these are checked above.

MIRRORS = (
    "FS_LOAD_BASE",
    "FS_TEXT_BYTES",
    "FS_DATA_BYTES",
    "FS_BSS_BYTES",
    "FS_DATA_BASE",
    "FS_BSS_BASE",
    "FS_PROGRAM_END",
    "A_stack_top",
    "A_saved_super_ssp",
    "A_sprite_bank",
    "A_tile_banks",
    "TILE_BANK_BYTES",
    "TILE_BANKS",
    "A_level_map_cols",
    "A_sound_module_file",
    "A_sound_module",
    "SOUND_MODULE_HEADER_BYTES",
    "A_entity_arena",
    "ENTITY_SLOTS",
    "ENTITY_STRIDE",
    "MODULE_OVER_ARENA_BYTES",
    "SCREEN_RING_BYTES",
    "SCREEN_BYTES",
)

ENTRY_PROLOGUES = {
    # movem.l d0-d7/a0-a6,-(a7) / move.l (a0)+,$17776
    "ENTRY_LOAD_FILE": "48e7fffe23d800017776",
    # lea $1be36,a0 / move.w #$ff,d0
    "ENTRY_SPRITE_RELOC": "41f90001be36303c00ff",
    # subi.l #$1f900,d0 / addq.l #2,a7
    "ENTRY_RING_ARITHMETIC": "04800001f900548f",
}

STOP_PROLOGUES = {
    # movea.l #$16304,a0 / bsr.w -- the A\MODULE.BAK load the ring arithmetic runs into
    "STOP_RING_ARITHMETIC": "207c000163046100",
}
