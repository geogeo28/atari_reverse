r"""The POST-LOAD IMAGE every differential case stages on, REPLAYED FROM THE ORIGINAL once a session.

WHY IT EXISTS. `harness.BASE_IMAGE` is `../bin/FLYSHARK.PRG` laid down at load_base: TEXT, DATA and
a bss of zeroes. That is not the machine any frame-loop routine runs on. Before `main` reaches its
loop the program has done two things nothing in the .PRG can supply:

  * `boot_init` @ 0x14bee derives NINE screen pointers from XBIOS `Physbase` and loads the sound
    module off the disc;
  * `init_load_assets` @ 0x11212 loads the title picture and copies it to the screen, then loads the
    sprite bank, the level-1 tile banks and the level map, and RELOCATES the sprite directory in
    place.

A case staged on BASE_IMAGE therefore runs against zeroed tile banks, a zeroed sprite bank and null
screen pointers. It comes back green, about a machine that never exists at run time.

HOW IT IS BUILT: BY RUNNING THE ORIGINAL, not by transcribing it. `post_load_image` is what the
game's own code leaves behind after TWO slices under the oracle, each with the files that slice
reads staged for the TOS model:

  1. `boot_init` 0x14bee -> STOP_BOOT_SLICE, with A\MODULE.BAK staged;
  2. `init_load_assets` 0x11212 -> its `rts`, with ALL EIGHT files staged — the title picture and
     its 32,000-byte copy to `Physbase - 0x80`, then the four tile banks, the level map and the
     sprite bank, whose directory it relocates in place.

WHY TWO AND NOT ONE. `boot_init` ends by calling `Kbdvbase` and storing through its answer, which
lands in the model's own poked-input block, so slice 1 stops one instruction short of that pair and
the fixture supplies the ring itself (below).

WHY SLICE 2 IS NOT ITSELF SPLIT — it used to be. The model stages files in ONE window, and at the
kit's default that window is too small for this boot's eight files, so `init_load_assets` was
replayed as two sub-slices around the staging: the title picture on its own, then the other seven
entered at 0x112ac. `project.toml`'s `fs_base` moves the window down — that comment is the one
canonical statement of the arithmetic, and nothing here restates it — so the eight fit at once and
the sub-slice seam is gone. With it goes the one thing the fixture could not say, `main`'s own boot
slice, which is a ✅ row now.
`test_image_model.py::test_the_staged_file_window_holds_the_whole_boot` measures the window rather
than believing it, so one that SHRANK fails there rather than in a `stage_files` assertion nobody
could read.

THE ONE THING THE REPLAY DOES NOT KEEP is where the screen ring lands. `boot_init` derives it from
XBIOS `Physbase`, the model answers `OS_SCREEN_BASE` (0x8000), and `subi.l #$1f900,d0` underflows —
so the replayed pointers address memory outside the image entirely. `install_screen_ring` therefore
re-writes those nine longwords with the SAME ROUTINE'S ARITHMETIC at a Physbase the harness chooses
(`abi.SCREEN_RING_PHYSBASE`, whose docstring argues the choice), between slice 1 and slice 2.
`test_image_model.py` pins the arithmetic against the real routine and the placement against `abi`.

WHAT IT DOES NOT HOLD, and why each is deliberate:

  * **the staged files themselves.** The FS table and the staging area are restored to BASE_IMAGE's
    zeroes at the end: they are the harness's scaffolding, not the game's memory, and a case that
    stages its own files pokes them fresh.
  * **anything `init_new_game` @ 0x112fa does.** This image is the one that routine is ENTERED on,
    which is where `init_load_assets` returns to `main` — see `post_new_game_image` below.
  * **TOS's real $70 vector.** `boot_init` copies whatever the machine had at $70 into the `jmp`
    operand at `A_vbl_chain_vector`, and the modeled machine has 0 — so the fixture holds 0 where an
    Atari holds TOS's own level-4 handler. Any reconstruction of `vbl_handler`'s chain tail is
    therefore unpinned on target; STATUS.md carries the row.
  * **the IKBD command `Bconout(4, $14)`** @ 0x14ce0 and the `Kbdvbase` joyvec install
    @ 0x14ce4..0x14cfe: slice 1 stops before them. The first writes no image byte (it is an entry in
    the kit's OS event ledger); the second would write the game's handler into KBDVBASE+0x18, inside
    the model's own poked-input block. `tos_joyvec_handler` is dead code anyway
    (../notes/frontend.md §4).

SESSION-SCOPED AND READ-ONLY, and handed out as `bytes` rather than a `bytearray`, so a case that
means to poke it has to say so — `bytearray(post_load_image)`, or `_pokes` in the differential's
`regs`.
"""
import functools
import os
import random
from pathlib import Path

import pytest

import abi
import emu
import harness

REC = Path(__file__).resolve().parents[1]
# The extracted contents of disc A. `../notes/loader.md` has the carve if this folder is ever lost.
DISK_DIR = REC.parent / "bin" / "disk" / "A"

# ---- the file records the boot chain feeds `load_file` @ 0x10bfa --------------------------------
#
# A record is [dest.l][len.l][ASCIZ DOS path], and ALL THREE FIELDS ARE READ OUT OF THE IMAGE
# (`file_record` below) rather than restated here: both longwords are relocated, so the image is the
# only place they are true — which is also what makes `include/globals.h`'s A_tile_banks and friends
# checkable against the binary. Only the record's ADDRESS and the file's name ON DISC are named
# here, the latter because the DOS path's case is not the extracted folder's (`A\SPRITES.cru` is
# `SPRITES.CRU` on disc).
A_file_rec_flyshk_neo = 0x162ee
A_file_rec_module_bak = 0x16304
A_file_rec_sprites_cru = 0x1631a
A_file_rec_level_map = 0x16330
A_file_rec_hsc_0 = 0x16346
A_file_rec_hsc_1 = 0x1635a
A_file_rec_hsc_2 = 0x1636e
A_file_rec_hsc_3 = 0x16382

# In boot order: MODULE.BAK first (boot_init), then level 0's five files in `load_level_assets`'s
# own order (HSC_0, the map, HSC_1, HSC_2, HSC_3 — see 0x10332..0x10400), then SPRITES.cru. The
# title picture is NOT here: it is the one file the asset slice must run without, and it has its own
# record and its own slice.
BOOT_LOADS = (
    (A_file_rec_module_bak,  "MODULE.BAK"),
    (A_file_rec_hsc_0,       "HSC_0.DAT"),
    (A_file_rec_level_map,   "LEVEL1.MAP"),
    (A_file_rec_hsc_1,       "HSC_1.DAT"),
    (A_file_rec_hsc_2,       "HSC_2.DAT"),
    (A_file_rec_hsc_3,       "HSC_3.DAT"),
    (A_file_rec_sprites_cru, "SPRITES.CRU"),
)
TITLE_LOAD = (A_file_rec_flyshk_neo, "FLY_SHK.NEO")

# `include/globals.h`'s record layout, which `file_record` reads a record with.
FILE_REC_DEST = 0
FILE_REC_LEN = 4
FILE_REC_NAME = 8

# ---- the boot chain's other addresses, as `../names.txt` spells them ----------------------------
A_saved_super_ssp = 0x19014
A_vbl_chain_vector = 0x11650      # the OPERAND of the `jmp $1164e.l` that ends `vbl_handler`
A_sprite_bank = 0x1be36
A_sprite_restore_lists = 0x18014
A_level0_assets_loaded = 0x176ea  # `st $176ea` @ 0x112b2, once the level-0 assets are in

VECTOR_VBL = 0x70                 # 68000 autovector 4
VECTOR_ACIA = 0x118               # MFP channel 6 = the IKBD/MIDI ACIA
FN_VBL_HANDLER = 0x11636
FN_ACIA_IKBD_ISR = 0x14218

# `init_load_assets`' sprite-directory relocation, @ 0x112c2..0x112d6.
SPRITE_RECORDS = 256
SPRITE_RECORD_BYTES = 20
# ...and its four restore-list terminators, @ 0x112e0..0x112f2.
SPRITE_RESTORE_LISTS = 4
SPRITE_RESTORE_LIST_BYTES = 0x200
SPRITE_RESTORE_FIRST_ENTRY = 2
SPRITE_RESTORE_TERMINATOR = 0xffff

# ---- the slices the replay runs, and where each stops -------------------------------------------
ENTRY_BOOT_INIT = 0x14bee            # `movea.l #$19094,a7`
ENTRY_INIT_LOAD_ASSETS = 0x11212     # `bsr.s $111d6` — set_palette_title, then the whole of it
ENTRY_INIT_NEW_GAME = 0x112fa        # `move.w $176ac,$176c6`
ENTRY_INIT_STAGE_STATE = 0x1139a     # `move.w #$1,$1775e`

# ONE ADDRESS TWO BATTERIES NAME, which is why it is here rather than in either. 0x1054a is where
# the attract screen's stage start ends and the jingle begins: `test_frontend.py` runs
# `title_attract_start_tune` FROM it and stops the prescroll AT it, and `test_scroll.py` stops the
# same prescroll there under its `title` parametrisation. Declared and pinned once (ENTRY_PROLOGUES
# below), so the two cannot drift apart.
ENTRY_ATTRACT_START_TUNE = 0x1054a   # `move.w #$4,d0 / bsr.w music_play`

# Slice 1's checkpoint: `clr.l d0` @ 0x14cd2, the instruction after `move.w #$2300,sr`. It is the
# last point at which boot_init has touched nothing but the image — the very next instructions are
# the IKBD `Bconout` and the `Kbdvbase` pair, and the latter would store into the model's own
# poked-input block.
STOP_BOOT_SLICE = 0x14cd2
# `init_new_game` ends `bra.w enter_title` @ 0x11394 — it never returns to `main`, so its slice
# stops at the branch rather than at an `rts`.
STOP_INIT_NEW_GAME = 0x11394

# Loose enough not to be tuning knobs, tight enough that a runaway is still caught. The title slice
# copies 8,000 longwords in a `dbf` loop (~16k instructions) and the asset slice runs seven more
# `Fread`s, each of which is one modeled trap rather than a loop.
BOOT_SLICE_MAX_INSNS = 50_000
LOAD_SLICE_MAX_INSNS = 200_000
# `init_stage_state` falls through `difficulty_apply_fire_rates` into `start_level`, which loads
# five files and PRESCROLLS a whole screen of terrain — `prescroll_frames + 1` whole frames.
START_LEVEL_MAX_INSNS = 40_000_000
# `emu.run`'s "no checkpoint": the run ends where the routine itself returns.
STOP_AT_RTS = 0

# ---- the nine screen pointers boot_init derives from Physbase ------------------------------------
SCREEN_RING_BYTES = 0x1f900
SCREEN_RING_ALIGN = 0x100
SCREEN_RING_SLOTS = 4
SCREEN_RING_0_OFF = 0x7800
SCREEN_RING_1_OFF = 0xfa00
SCREEN_RING_2_OFF = 0x17700
SCREEN_RING_3_OFF = 0x1f400
A_screen_ring_base_raw = 0x163fa
A_screen_ring = 0x16406
A_screen_ring_1 = 0x1640a
A_screen_ring_2 = 0x1640e
A_screen_ring_3 = 0x16412
A_screen_draw = 0x16416
A_screen_prev1 = 0x1641a
A_screen_prev2 = 0x1641e
A_screen_ring_base = 0x16422

# The four rotating bases, in the order boot_init stores them.
RING_SLOT_POINTERS = (
    (A_screen_ring,   SCREEN_RING_0_OFF),   # `adda.l #$7800,a0`  @ 0x14c4a — row 192
    (A_screen_ring_1, SCREEN_RING_1_OFF),   # `adda.l #$fa00,a0`  @ 0x14c62 — row 400
    (A_screen_ring_2, SCREEN_RING_2_OFF),   # `adda.l #$17700,a0` @ 0x14c7a — row 600
    (A_screen_ring_3, SCREEN_RING_3_OFF),   # `adda.l #$1f400,a0` @ 0x14c8c — row 800
)
# ...and the three cursors it seeds from the same three offsets, sharing the `adda` that made each.
SEEDED_POINTERS = (
    (A_screen_draw,  SCREEN_RING_1_OFF),    # `move.l a0,$16416` @ 0x14c6e — ring[1]
    (A_screen_prev1, SCREEN_RING_0_OFF),    # `move.l a0,$1641a` @ 0x14c56 — ring[0]
    (A_screen_prev2, SCREEN_RING_3_OFF),    # `move.l a0,$1641e` @ 0x14c92 — ring[3]
)
SCREEN_POINTERS = RING_SLOT_POINTERS + SEEDED_POINTERS

# `init_load_assets` copies the title picture to `Physbase - TITLE_COPY_OFFSET`, so the NEO file's
# 128-byte header lands just below the screen and its pixels land exactly on it: `suba.l #$80,a1`
# @ 0x11268 and `move.w #$1f3f,d7 / move.l (a0)+,(a1)+ / dbf` @ 0x1126e..0x11274.
TITLE_COPY_OFFSET = 0x80
TITLE_COPY_BYTES = 0x1f40 * 4

_LONG = 4
_U32 = 0xffffffff


def ring_pointers(physbase):
    """{address: value} for the nine longwords `boot_init` derives from `physbase`.

    boot_init's own arithmetic, one line per instruction:

        screen_ring_base_raw = Physbase - 0x1f900          ; subi.l @ 0x14c26
        screen_ring_base     = (raw + 0x100) & ~0xff       ; addi.l / clr.b @ 0x14c3a
        ring[i]              = screen_ring_base + offset   ; adda.l @ 0x14c4a ...

    Note the rounding is STRICTLY up: `clr.b` clears the low byte of raw + 0x100, so an already
    aligned raw base still gains 0x100. Everything is taken mod 2^32 because the 68000's is —
    which is not academic, since the model's own Physbase (OS_SCREEN_BASE = 0x8000) underflows.
    """
    raw = (physbase - SCREEN_RING_BYTES) & _U32
    base = (raw + SCREEN_RING_ALIGN) & _U32 & ~(SCREEN_RING_ALIGN - 1)
    values = {A_screen_ring_base_raw: raw, A_screen_ring_base: base}
    values.update({address: (base + offset) & _U32 for address, offset in SCREEN_POINTERS})
    return values


def install_screen_ring(image, physbase):
    """Re-place the ring the replay derived from the model's underflowing Physbase.

    The module docstring argues why this one part of the boot chain is the harness's choice rather
    than the replay's; `abi.py` argues the address it chooses.
    """
    for address, value in ring_pointers(physbase).items():
        image[address:address + _LONG] = value.to_bytes(_LONG, "big")
    return image


# Long enough for the longest path in the table ("A\FLY_SHK.NEO") and its NUL, and short enough that
# a record whose terminator went missing yields an over-long name `harness.stage_files` refuses by
# name (its own OS_FS_NAME limit is the same 16) rather than one that runs into the next record.
_MAX_DOS_PATH = 16


def file_record(image, record):
    """(destination, length, DOS path) for one `load_file` record, read out of the loaded image."""
    def long_at(offset):
        return int.from_bytes(image[record + offset:record + offset + _LONG], "big")

    name = bytes(image[record + FILE_REC_NAME:record + FILE_REC_NAME + _MAX_DOS_PATH])
    return long_at(FILE_REC_DEST), long_at(FILE_REC_LEN), name.split(b"\0")[0].decode("ascii")


@functools.lru_cache(maxsize=None)
def _disk_file(name):
    """One whole file off disc A, read once per process — every slice and several tests ask."""
    return DISK_DIR.joinpath(name).read_bytes()


def disk_bytes(name, length):
    """The first `length` bytes of one file on disc A — what GEMDOS `Fread(handle, length, dest)`
    transfers. Several records ask for more than the file holds (A\\LEVEL1.MAP's 0x1388 against a
    3,664-byte file) and one asks for one byte less (A\\MODULE.BAK), so the short side wins here
    exactly as `os_fread` makes it win in the model."""
    return _disk_file(name)[:length]


def staged_load(image, record, disk_name):
    """(DOS path, bytes) for one BOOT_LOADS row, ready for `harness.stage_files` — the REAL bytes.

    Its twin is `seeded_load` below, and which of the two a case wants is a real question rather
    than a flag: see that docstring.
    """
    _dest, length, dos_path = file_record(image, record)
    return dos_path, disk_bytes(disk_name, length)


def seeded_bytes(length, seed):
    """`length` pseudo-random bytes from `seed` — file content of a test's OWN choosing.

    Deterministic, because a case that stages random bytes has to stage the same random bytes on
    every run and on every xdist worker: `random.Random(seed)` is the whole of that.
    """
    rng = random.Random(seed)
    return bytes(rng.randrange(0x100) for _ in range(length))


def seeded_load(image, record, disk_name, seed):
    """`staged_load`'s twin: the same DOS path and the same LENGTH, with content nothing else holds.

    TWO NAMED HELPERS AND NOT A `seeded=` FLAG, because the choice between them is the case's whole
    argument. The post-load fixture ALREADY HOLDS the real files at their destinations, so a case
    staged with `staged_load` cannot separate a reconstruction that read a file from one that read
    nothing at all — content of the test's own choosing is what makes an `Fread` visible. The other
    way round, a case that RENDERS from what it staged (the whole-boot run draws terrain out of
    A\\LEVEL1.MAP and the tile banks) needs the real bytes: a map header of noise sends the
    scroller's own cursor arithmetic somewhere the game never goes.

    THE LENGTH IS THE FILE'S AND NOT THE RECORD'S, which is `staged_load`'s rule and matters here
    too: several records ask for more than their file holds, and GEMDOS's short read is the only
    thing between `load_file` and an overrun of the loader's own scratch longwords.
    """
    dos_path, real = staged_load(image, record, disk_name)
    return dos_path, seeded_bytes(len(real), seed)


def _run_slice(image, loads, entry, stop_pc, max_insns):
    """Run one slice of the boot chain on `image`, with exactly `loads`' files staged for it.

    The staged-file region is reset to BASE_IMAGE's zeroes first, so a slice sees its own files and
    nothing another slice left in the table — the model answers `Fopen` from that table, and a stale
    entry would be a file the game could open at a moment it cannot.

    The DOS paths are read out of the records in the image the slice starts from. `load_level_assets`
    patches the level and bank DIGITS into those records before opening them (@ 0x10346..0x1036e), so
    a slice that ran for a level other than 0 would ask the model for a name nothing staged — and be
    refused by name rather than served the wrong file.
    """
    staged = bytearray(image)
    staged[harness.OS_FS_TABLE:harness.OS_IMAGE_SIZE] = \
        harness.BASE_IMAGE[harness.OS_FS_TABLE:harness.OS_IMAGE_SIZE]
    pokes, _handles = harness.stage_files([staged_load(image, *load) for load in loads])
    for address, data in pokes.items():
        staged[address:address + len(data)] = data
    # A slice that does not reach its checkpoint raises out of emu.run, so reaching the end of this
    # function is itself the assertion that all three ran.
    final, _writes, _regs = emu.run(staged, entry, stop_pc=stop_pc, max_insns=max_insns)
    return bytearray(final)


def replay_boot_init(image):
    """Slice 1: the real `boot_init`, stopped before the `Kbdvbase` pair. Its ring is the MODEL's."""
    return _run_slice(image, [BOOT_LOADS[0]], ENTRY_BOOT_INIT, STOP_BOOT_SLICE, BOOT_SLICE_MAX_INSNS)


def replay_load_assets(image):
    """Slice 2: the real `init_load_assets`, WHOLE, with all eight of its files staged at once.

    One slice because `project.toml`'s `fs_base` makes the model's staging window big enough to hold
    them (the module docstring has the arithmetic). It used to be two, entered at 0x112ac for the
    second, and the seam it left is why `main`'s boot slice had no row until the window moved.
    """
    return _run_slice(image, (TITLE_LOAD,) + BOOT_LOADS, ENTRY_INIT_LOAD_ASSETS, STOP_AT_RTS,
                      LOAD_SLICE_MAX_INSNS)


def _without_staged_files(image):
    """The harness's scaffolding taken back out: the FS table and the staging area, as loaded."""
    image[harness.OS_FS_TABLE:harness.OS_IMAGE_SIZE] = \
        harness.BASE_IMAGE[harness.OS_FS_TABLE:harness.OS_IMAGE_SIZE]
    return bytes(image)


def install_boot_state(image, physbase):
    """THE TRANSCRIPTION the replay replaced, kept as a second opinion and nothing else.

    Every store the boot chain leaves behind, written out by hand in boot order with the instruction
    that makes each. `test_image_model.py::test_the_replay_and_the_transcription_agree` diffs it
    against `post_load_image` over the WHOLE image outside three named bands, so a store one side
    invented, misplaced or dropped fails by address. When they disagree the REPLAY is right — it is
    the program's own code — and this list is what gets fixed. (It has been: `A_level0_assets_loaded`
    is here because the replay wrote it and the transcription did not.)

      1. `A_saved_super_ssp`   0x19014   `move.l d0,$19014`   @ 0x14bfe  — GEMDOS Super(0)'s result,
                                         which the TOS model answers with `harness.OS_SUPER_TOKEN`
      2. the nine screen-ring longwords, `ring_pointers()`         @ 0x14c2e .. 0x14c98
      3. `A_sound_module_file` 0x58928   `bsr.w load_file`    @ 0x14ca4  — A\\MODULE.BAK, whole
      4. `A_vbl_chain_vector`  0x11650   `move.l $70,$11650`  @ 0x14cac  — the operand of the `jmp`
                                         at 0x1164e; the model's $70 holds 0
      5. vector $70            0x00070   `move.l a0,$70`      @ 0x14cbc  — `vbl_handler` @ 0x11636
      6. vector $118           0x00118   `move.l a0,$118`     @ 0x14cc8  — `acia_ikbd_isr` @ 0x14218
      7. `A_tile_banks`+0..3   0x38928   `bsr.w load_file` x4 in `load_level_assets` @ 0x10332 — the
                                         four A\\HSC_n.DAT banks for level 0, back to back
      8. `A_level_map_cols`    0x16432   `bsr.w load_file`    @ 0x103b6 — A\\LEVEL1.MAP
      9. `A_level0_assets_loaded` 0x176ea `st $176ea`         @ 0x112b2
     10. `A_sprite_bank`       0x1be36   `bsr.w load_file`    @ 0x112be — A\\SPRITES.cru, RAW
     11. the 256 sprite-directory pointers, `addi.l #$1be36,(a0) / lea 20(a0),a0 / dbf`
                                                              @ 0x112cc..0x112d6
     12. four `move.w #$ffff,n(a0)` terminators into `A_sprite_restore_lists` @ 0x112e0 .. 0x112f2

    The three bands it does NOT reproduce, all of them the replay's and none of them the game's
    lasting state: the game's own stack below 0x19094 (boot_init's trap frames), `load_file`'s
    scratch at 0x17774, and the title picture copied to `Physbase - TITLE_COPY_OFFSET`, which lands
    in the model's own framebuffer and which no frame-loop routine reads.
    """
    def put_long(address, value):
        image[address:address + _LONG] = value.to_bytes(_LONG, "big")

    put_long(A_saved_super_ssp, harness.OS_SUPER_TOKEN)                              # 1
    install_screen_ring(image, physbase)                                             # 2
    for record, disk_name in BOOT_LOADS:                                             # 3, 7, 8, 10
        dest, length, _dos_path = file_record(image, record)
        data = disk_bytes(disk_name, length)
        image[dest:dest + len(data)] = data
    put_long(A_vbl_chain_vector, int.from_bytes(image[VECTOR_VBL:VECTOR_VBL + _LONG], "big"))   # 4
    put_long(VECTOR_VBL, FN_VBL_HANDLER)                                             # 5
    put_long(VECTOR_ACIA, FN_ACIA_IKBD_ISR)                                          # 6
    image[A_level0_assets_loaded] = 0xff                                             # 9
    for index in range(SPRITE_RECORDS):                                              # 11
        slot = A_sprite_bank + index * SPRITE_RECORD_BYTES
        offset = int.from_bytes(image[slot:slot + _LONG], "big")
        put_long(slot, (offset + A_sprite_bank) & _U32)
    for index in range(SPRITE_RESTORE_LISTS):                                        # 12
        entry = (A_sprite_restore_lists + index * SPRITE_RESTORE_LIST_BYTES
                 + SPRITE_RESTORE_FIRST_ENTRY)
        image[entry:entry + 2] = SPRITE_RESTORE_TERMINATOR.to_bytes(2, "big")
    return image


# THE THREE BUILDERS ARE PLAIN FUNCTIONS AND THE FIXTURES BELOW ARE THIN. `../gen_readme_assets.py`
# stages exactly this chain and is not a pytest run, so it calls these three by name; a fixture body
# would have made it either re-implement the chain or reach in through private names, and both were
# tried before this shape (README.md, "The image model", is the one description of what they build).


def post_load():
    """The image `init_load_assets` @ 0x11212 RETURNS on: the module docstring's two slices."""
    image = replay_boot_init(bytearray(harness.BASE_IMAGE))
    install_screen_ring(image, abi.SCREEN_RING_PHYSBASE)
    return _without_staged_files(replay_load_assets(image))


def post_new_game(image):
    """...and the image after `init_new_game` @ 0x112fa, stopped at its `bra.w enter_title`."""
    final, _writes, _regs = emu.run(bytearray(image), ENTRY_INIT_NEW_GAME,
                                    stop_pc=STOP_INIT_NEW_GAME, max_insns=LOAD_SLICE_MAX_INSNS)
    return _without_staged_files(bytearray(final))


def started_level(image, loads=None, stop_pc=STOP_AT_RTS):
    """...and a STAGE the original started: `init_stage_state` @ 0x1139a, with `loads` staged.

    It is not a slice. The run follows the routine's own dispatch through
    `difficulty_apply_fire_rates` into `start_level`, which loads the level's five files, installs
    the level record, seeds the map cursor and prescrolls the whole screen in with the palette
    black — so the world it leaves is the game's, down to the terrain in all four screens.

    `stop_pc` is the caller's because `start_level` ends `bra.w music_play`: run to the `rts` and
    the stage's tune is playing, stop at 0x1156a and it is not.
    """
    return _without_staged_files(_run_slice(image, BOOT_LOADS if loads is None else loads,
                                            ENTRY_INIT_STAGE_STATE, stop_pc, START_LEVEL_MAX_INSNS))


@pytest.fixture(scope="session")
def post_load_image():
    """`post_load()`, once a session.

    `main` @ 0x15750 is `bsr init_load_assets / bsr init_new_game / bsr init_stage_state` and then
    its frame loop, so this is the machine the SECOND of those is entered on — the last image the
    boot chain reaches before any game state exists, and the base every differential runs on.
    """
    return post_load()


@pytest.fixture(scope="session")
def post_new_game_image(post_load_image):
    """...and the image AFTER `init_new_game`, for a routine that runs on a started game.

    `init_new_game` resets the per-game state and ends by calling `clear_actor_arrays` @ 0x115e2,
    which byte-clears 0x59984..0x5aede — so this image has the entity arena zeroed, including the
    MODULE_OVER_ARENA_BYTES the sound module's load leaves over the arena's FIRST record
    (`include/globals.h`, "THE SOUND MODULE OVERLAPS THE ARENA"). It is NOT the differential's base:
    the base is the image above, and a battery whose routine runs on a started game asks for this
    one by name.

    Nothing it runs opens a file, so the slice stages none. It stops at the `bra.w enter_title` the
    routine ends with rather than at an `rts`: `init_new_game` does not return to `main` itself, it
    falls into the title flow, whose own `rts` is what eventually comes back.
    """
    return post_new_game(post_load_image)


# =================================================================================================
# The two STAGED WORLDS the whole-frame batteries share, and the one build the whole run does
# =================================================================================================
#
# THREE BATTERIES ASKED FOR THE SAME MACHINE and each built its own: `test_entity.py` ran the spawn
# script 6,000 times, `test_weapons.py` 3,000, and both derived their pokes with a private copy of
# the same byte scan. A session fixture is per PROCESS, and `-n auto` is one process per core, so
# what looked like "once a session" was really once per core per battery. It is built here once and
# CACHED ACROSS THE WORKERS, so `make test` pays for the replay exactly once.

# ---- the two agents the ATTRACT LOOP runs under -------------------------------------------------
#
# TWO BATTERIES DRIVE THAT LOOP — `test_frontend.py` over `title_attract_loop` and `test_init.py`
# over the whole boot behind it — and each built the same schedule from its own copy of the same
# four constants, under two different names for the VBL budget. One builder here instead, so the
# two cannot describe different agents while claiming to run the same loop.
TITLE_FIRE_WAIT_PC = 0x1056a        # include/frontend.h — the `btst #7,$1777f` the poll re-reads at
RENDER_FRAME_VBL_WAIT_PC = 0x1479c  # src/sprite.c — where `render_frame` re-reads the VBL counter
RENDER_FRAME_VBL_BUDGET = 3         # include/sprite.h — the count that arm waits for
A_vbl_tick = 0x17720                # include/irq.h
A_joy1_state = 0x1777f              # include/irq.h
JOY_FIRE_BIT = 7                    # include/hud.h


def attract_schedule(fire_at, frames):
    """The stick coming down at the `fire_at`th poll, and the VBL counter reaching its budget once
    per attract frame.

    `render_frame` CLEARS the counter at the end of every frame, so each frame's wait needs an
    arrival of its own rather than one store standing for all of them.

    The schedule is its own positive control: the kit sinks a run in which a scheduled store never
    came due, so a loop that quietly stopped after one pass fails here rather than merely comparing
    less (`tools/recreate_kit/include/os.h`, "WAIT SITES").
    """
    return [{"pc": TITLE_FIRE_WAIT_PC, "nth": fire_at, "addr": A_joy1_state, "width": 1,
             "value": 1 << JOY_FIRE_BIT}] \
        + [{"pc": RENDER_FRAME_VBL_WAIT_PC, "nth": frame + 1, "addr": A_vbl_tick, "width": 4,
            "value": RENDER_FRAME_VBL_BUDGET} for frame in range(frames)]


A_spawn_script_ptr = 0x17770        # `movea.l $17770,a0` @ 0x12fc4
A_spawn_script_cursor = 0x17754     # `adda.l $17754,a0` @ 0x12fca
A_scroll_pos = 0x17758              # `move.w $17758,d0` @ 0x12fd8, the trigger the script compares
A_level1_script = 0x1b350           # level 1's record in `A_level_records`, which `start_level` installs
ENTRY_SPAWN_SCRIPT_STEP = 0x12fc4
SPAWN_MAX_INSNS = 200_000
# 6,000 steps is scroll_pos 0..0x2ee0, sixty of level 1's spawn records — the count `test_entity.py`
# chose, and a superset of the 3,000 `test_weapons.py` used. ONE COUNT, so the two batteries verify
# against the same world and a case that only passes on the thinner one fails where it is written.
SPAWN_STEPS = 6000
# Under a fifth of the arena live is not a world worth verifying a whole-frame pass against.
SPAWN_MIN_LIVE_SLOTS = 20

# The arena the replay fills, mirrored from `include/globals.h`, plus the one record field the live
# count reads (`include/entity.h`'s, and the only field this file needs to know about).
A_entity_arena = 0x59984
ENTITY_SLOTS = 91
ENTITY_STRIDE = 58
ENTITY_ACTIVE = 14

# The block the byte scan below compares whole before it looks at single bytes. The staged worlds
# differ from the base in a few dozen short runs out of a megabyte, so nearly every block is
# identical and one `==` retires 4,096 addresses.
_POKE_SCAN_BLOCK = 4096


def byte_run_pokes(base, staged):
    """{address: bytes} for every run of bytes in which `staged` differs from `base`.

    A staged image cannot be handed to `differential()` directly — the autouse fixture below owns
    the base image, deliberately (README.md) — so the difference travels as ordinary pokes.

    The block compare is not decoration: a byte-at-a-time scan of the whole image is the single most
    expensive thing in the fixtures above it, and the two images differ in a handful of runs.
    """
    pokes, run_start, at, size = {}, None, 0, len(base)
    while at < size:
        end = min(at + _POKE_SCAN_BLOCK, size)
        if base[at:end] == staged[at:end]:
            if run_start is not None:
                pokes[run_start] = bytes(staged[run_start:at])
                run_start = None
            at = end
            continue
        for address in range(at, end):
            differs = base[address] != staged[address]
            if differs and run_start is None:
                run_start = address
            elif not differs and run_start is not None:
                pokes[run_start] = bytes(staged[run_start:address])
                run_start = None
        at = end
    if run_start is not None:
        pokes[run_start] = bytes(staged[run_start:])
    assert all(address >= harness.OS_POKE_BLOCK_END for address in pokes), (
        "a staged image differs inside the model's poked-input block, which make_image refuses")
    return pokes


def built_once_per_run(tmp_path_factory, name, build):
    """`build()`'s bytes, computed by the FIRST xdist worker to need them and read by the rest.

    `tmp_path_factory.getbasetemp()` is per worker; its PARENT is the one directory the whole run
    shares, which is pytest-xdist's own place for exactly this. The winner writes a scratch file
    named after its pid and `os.replace`s it into position — atomic, so a reader never sees a
    half-written image, and a loser simply replaces a byte-identical file. There is no lock and none
    is needed: the work is deterministic, so the only cost of two workers racing is that both did it.
    """
    cached = tmp_path_factory.getbasetemp().parent / name
    if cached.is_file():
        return bytearray(cached.read_bytes())
    built = build()
    scratch = cached.with_suffix(f".{os.getpid()}")
    scratch.write_bytes(bytes(built))
    os.replace(scratch, cached)
    return built


def _spawn_the_world(post_new_game_image):
    """Level 1's script installed the way `start_level` @ 0x11440 installs it, and then the game's
    own `spawn_script_step` @ 0x12fc4 run once per two pixels of scroll — exactly as the frame loop
    calls it. NOTHING HERE WRITES AN ENTITY RECORD: every live slot is the shape the game's own
    descriptors, formation tables and movement scripts produce, which is what a hand-poked world
    can never be.

    `emu.run` returns a bytearray it allocated, so the loop carries that forward rather than copying
    a megabyte per step. The TOS model's file band is restored ONCE, after the loop: the routine
    makes no trap, so nothing inside the replay can disturb it, and the restore is there to keep the
    band out of the poke set rather than to keep the run honest.
    """
    image = bytearray(post_new_game_image)
    image[A_spawn_script_ptr:A_spawn_script_ptr + 4] = A_level1_script.to_bytes(4, "big")
    image[A_spawn_script_cursor:A_spawn_script_cursor + 4] = bytes(4)
    for step in range(SPAWN_STEPS):
        image[A_scroll_pos:A_scroll_pos + 2] = (2 * step).to_bytes(2, "big")
        image, _writes, _regs = emu.run(image, ENTRY_SPAWN_SCRIPT_STEP, max_insns=SPAWN_MAX_INSNS)
    image[harness.OS_FS_TABLE:harness.OS_IMAGE_SIZE] = \
        harness.BASE_IMAGE[harness.OS_FS_TABLE:harness.OS_IMAGE_SIZE]
    return image


@pytest.fixture(scope="session")
def new_game_pokes(post_load_image, post_new_game_image):
    """`init_new_game`'s machine as pokes: the arena zeroed and the per-game state reset."""
    return byte_run_pokes(post_load_image, post_new_game_image)


@pytest.fixture(scope="session")
def staged_world_pokes(post_load_image, post_new_game_image, tmp_path_factory):
    """A POPULATED arena the ORIGINAL filled, as pokes. See `_spawn_the_world`."""
    image = built_once_per_run(tmp_path_factory, "staged_world.img",
                                lambda: _spawn_the_world(post_new_game_image))
    live = sum(1 for slot in range(ENTITY_SLOTS)
               if image[A_entity_arena + slot * ENTITY_STRIDE + ENTITY_ACTIVE:
                        A_entity_arena + slot * ENTITY_STRIDE + ENTITY_ACTIVE + 2] != b"\0\0")
    assert live > SPAWN_MIN_LIVE_SLOTS, (
        f"the spawn replay left only {live} live slots — a world this thin would verify the "
        f"whole-frame passes over an arena that is nearly all inactive")
    return byte_run_pokes(post_load_image, image)


@pytest.fixture(scope="session", autouse=True)
def _differential_base_image(post_load_image):
    """Install the post-load image as the memory EVERY differential starts from.

    `harness.differential()` builds its image from the kit's base rather than from a fixture, so a
    battery cannot hand it one per case — and a per-case argument would be forgettable in exactly
    the way that stays green (`harness.set_base_image`'s own docstring makes that argument). Autouse
    is therefore the mechanism: every case in the session runs on the image the boot chain leaves,
    and the loader's zeroed tile banks are never what a case is verified against.

    The previous base is restored on teardown so the session leaves the kit as it found it.
    """
    previous = harness.set_base_image(post_load_image)
    yield
    harness.set_base_image(previous)


# The constants above that `include/globals.h` also defines — the C is the source of truth and this
# is the copy, so CLAUDE.md §5's rule applies: pin them equal with a test. `test_image_model.py`
# runs `check_mirrors(conftest)` and `check_entry_prologues(conftest)` over this module. Without the
# first, a fixture that relocated 128 records instead of 256 would compare only the half it wrote,
# on both sides, and stay green.
#
# A_vbl_chain_vector, VECTOR_VBL/ACIA and the two handler entries are deliberately absent: they
# belong to `include/irq.h` and `include/init.h`, and they are already pinned against the
# ORIGINAL rather than against a second spelling — `test_the_boot_slice_really_wrote_the_things_it_
# is_pinned_on` asserts the real boot chain wrote each handler at each vector, and the replay/
# transcription diff catches a chain-operand address that names the wrong longword. So is
# A_level0_assets_loaded, which is the frontend's flag and is pinned the same way.
MIRRORS = (
    "A_entity_arena",
    "ENTITY_SLOTS",
    "ENTITY_STRIDE",
    ("ENTITY_ACTIVE", "include/entity.h", "ENTITY_ACTIVE"),
    "A_sprite_bank",
    "A_sprite_restore_lists",
    "A_saved_super_ssp",
    "A_file_rec_flyshk_neo",
    "A_file_rec_module_bak",
    "A_file_rec_sprites_cru",
    "A_file_rec_level_map",
    "A_file_rec_hsc_0",
    "A_file_rec_hsc_1",
    "A_file_rec_hsc_2",
    "A_file_rec_hsc_3",
    "FILE_REC_DEST",
    "FILE_REC_LEN",
    "FILE_REC_NAME",
    "SPRITE_RECORDS",
    "SPRITE_RECORD_BYTES",
    "SPRITE_RESTORE_LISTS",
    "SPRITE_RESTORE_LIST_BYTES",
    "SPRITE_RESTORE_FIRST_ENTRY",
    "SPRITE_RESTORE_TERMINATOR",
    "SCREEN_RING_BYTES",
    "SCREEN_RING_ALIGN",
    "SCREEN_RING_SLOTS",
    "SCREEN_RING_0_OFF",
    "SCREEN_RING_1_OFF",
    "SCREEN_RING_2_OFF",
    "SCREEN_RING_3_OFF",
    "A_screen_ring_base_raw",
    "A_screen_ring",
    "A_screen_ring_1",
    "A_screen_ring_2",
    "A_screen_ring_3",
    "A_screen_draw",
    "A_screen_prev1",
    "A_screen_prev2",
    "A_screen_ring_base",
    # `attract_schedule`'s four constants, each against the header that owns it.
    ("TITLE_FIRE_WAIT_PC", "include/frontend.h", "TITLE_FIRE_WAIT_PC"),
    ("RENDER_FRAME_VBL_WAIT_PC", "src/sprite.c", "RENDER_FRAME_VBL_WAIT_PC"),
    ("RENDER_FRAME_VBL_BUDGET", "include/sprite.h", "RENDER_FRAME_VBL_BUDGET"),
    ("A_vbl_tick", "include/irq.h", "A_vbl_tick"),
    ("A_joy1_state", "include/irq.h", "A_joy1_state"),
    ("JOY_FIRE_BIT", "include/hud.h", "JOY_FIRE_BIT"),
)

ENTRY_PROLOGUES = {
    # movea.l #$19094,a7 / clr.l -(a7)
    "ENTRY_BOOT_INIT": "2e7c0001909442a7",
    # bsr.s $111d6 / movea.l #$162ee,a0
    "ENTRY_INIT_LOAD_ASSETS": "61c2207c000162ee",
    # move.w $176ac,$176c6
    "ENTRY_INIT_NEW_GAME": "33f9000176ac000176c6",
    # move.w #$4,d0 / bsr.w $12588 / bsr.w -- the jingle, then the three lists
    "ENTRY_ATTRACT_START_TUNE": "303c0004610020386100",
    # movea.l $17770,a0 / adda.l $17754,a0
    "ENTRY_SPAWN_SCRIPT_STEP": "207900017770d1f900017754",
    # clr.b $17781 / clr.b $1777f -- init_stage_state, which falls through into start_level
    "ENTRY_INIT_STAGE_STATE": "42390001778142390001",
}

STOP_PROLOGUES = {
    # clr.l d0 / move.w #$14,-(a7) -- the IKBD command push slice 1 deliberately stops before
    "STOP_BOOT_SLICE": "42803f3c0014",
    # bra.w $1030e / rts -- init_new_game falls into enter_title instead of returning, so the `rts`
    # after the branch is unreachable
    "STOP_INIT_NEW_GAME": "6000ef784e75",
}
