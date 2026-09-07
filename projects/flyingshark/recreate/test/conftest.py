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
game's own code leaves behind after three slices under the oracle, each with the files that slice
reads staged for the TOS model:

  1. `boot_init` 0x14bee -> STOP_BOOT_SLICE, with A\MODULE.BAK staged;
  2. `init_load_assets` 0x11212 -> STOP_TITLE_COPY, with A\FLY_SHK.NEO staged — the title picture,
     its palette and the 32,000-byte copy to `Physbase - 0x80`;
  3. `init_load_assets` ENTRY_LEVEL0_ASSETS -> its `rts`, with the OTHER SEVEN files staged — the
     four tile banks, the level map, the sprite bank, and the sound module the model still needs a
     slot for.

WHY THREE SLICES AND NOT ONE. The model stages files in ONE window, `OS_FS_STAGING` up to the stack
guard = 258,048 bytes. The seven files of BOOT_LOADS are 256,423 bytes and fit with 1,625 to spare;
A\FLY_SHK.NEO's 32,128 do not fit beside them, so the title slice stages it alone and the asset
slice re-stages without it. `test_image_model.py::test_the_staging_window_is_why_the_replay_is_split`
pins that arithmetic, so a window that grew would show up as a test to delete rather than as a split
nobody could explain. Slice 1 is separate for a different reason: it stops one instruction short of
the `Kbdvbase` pair, which would write into the model's own poked-input block.

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
ENTRY_INIT_LOAD_ASSETS = 0x11212     # `bsr.s $111d6` — set_palette_title, then the title picture
# `clr.w d0` @ 0x112ac, where the title slice's `bra.s` was going: level 0's assets, the sprite bank
# and the directory fix-up. Entering HERE rather than following the `bra` is what splits the staging.
ENTRY_LEVEL0_ASSETS = 0x112ac
ENTRY_INIT_NEW_GAME = 0x112fa        # `move.w $176ac,$176c6`

# Slice 1's checkpoint: `clr.l d0` @ 0x14cd2, the instruction after `move.w #$2300,sr`. It is the
# last point at which boot_init has touched nothing but the image — the very next instructions are
# the IKBD `Bconout` and the `Kbdvbase` pair, and the latter would store into the model's own
# poked-input block.
STOP_BOOT_SLICE = 0x14cd2
# Slice 2's checkpoint: the `bra.s $112ac` @ 0x1127e, one instruction past the title copy loop. The
# disc-prompt block it branches over (0x11280..0x112aa) is patched out in the shipped binary.
STOP_TITLE_COPY = 0x1127e
# `init_new_game` ends `bra.w enter_title` @ 0x11394 — it never returns to `main`, so its slice
# stops at the branch rather than at an `rts`.
STOP_INIT_NEW_GAME = 0x11394

# Loose enough not to be tuning knobs, tight enough that a runaway is still caught. The title slice
# copies 8,000 longwords in a `dbf` loop (~16k instructions) and the asset slice runs six `Fread`s,
# each of which is one modeled trap rather than a loop.
BOOT_SLICE_MAX_INSNS = 50_000
LOAD_SLICE_MAX_INSNS = 200_000
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
    """(DOS path, bytes) for one BOOT_LOADS row, ready for `harness.stage_files`."""
    _dest, length, dos_path = file_record(image, record)
    return dos_path, disk_bytes(disk_name, length)


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
    """Slices 2 and 3: the real `init_load_assets`, split by the model's one staging window."""
    image = _run_slice(image, [TITLE_LOAD], ENTRY_INIT_LOAD_ASSETS, STOP_TITLE_COPY,
                       LOAD_SLICE_MAX_INSNS)
    return _run_slice(image, BOOT_LOADS, ENTRY_LEVEL0_ASSETS, STOP_AT_RTS, LOAD_SLICE_MAX_INSNS)


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


@pytest.fixture(scope="session")
def post_load_image():
    """The image `init_load_assets` @ 0x11212 RETURNS on: the module docstring's three slices.

    `main` @ 0x15750 is `bsr init_load_assets / bsr init_new_game / bsr init_stage_state` and then
    its frame loop, so this is the machine the SECOND of those is entered on — the last image the
    boot chain reaches before any game state exists, and the base every differential runs on.
    """
    image = replay_boot_init(bytearray(harness.BASE_IMAGE))
    install_screen_ring(image, abi.SCREEN_RING_PHYSBASE)
    return _without_staged_files(replay_load_assets(image))


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
    final, _writes, _regs = emu.run(bytearray(post_load_image), ENTRY_INIT_NEW_GAME,
                                    stop_pc=STOP_INIT_NEW_GAME, max_insns=LOAD_SLICE_MAX_INSNS)
    return _without_staged_files(bytearray(final))


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
# belong to the irq subsystem's header when that lands, and they are already pinned against the
# ORIGINAL rather than against a second spelling — `test_the_boot_slice_really_wrote_the_things_it_
# is_pinned_on` asserts the real boot chain wrote each handler at each vector, and the replay/
# transcription diff catches a chain-operand address that names the wrong longword. So is
# A_level0_assets_loaded, which is the frontend's flag and is pinned the same way.
MIRRORS = (
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
)

ENTRY_PROLOGUES = {
    # movea.l #$19094,a7 / clr.l -(a7)
    "ENTRY_BOOT_INIT": "2e7c0001909442a7",
    # bsr.s $111d6 / movea.l #$162ee,a0
    "ENTRY_INIT_LOAD_ASSETS": "61c2207c000162ee",
    # clr.w d0 / bsr.w $10332
    "ENTRY_LEVEL0_ASSETS": "42406100f082",
    # move.w $176ac,$176c6
    "ENTRY_INIT_NEW_GAME": "33f9000176ac000176c6",
}

STOP_PROLOGUES = {
    # clr.l d0 / move.w #$14,-(a7) -- the IKBD command push slice 1 deliberately stops before
    "STOP_BOOT_SLICE": "42803f3c0014",
    # bra.s $112ac, then the first six bytes of the patched-out disc-prompt block it branches over
    # (a line-F word and a `move.w #$777,$ff8256`) -- pinned too, so this is eight bytes like the
    # rest rather than a two-byte branch that many addresses could match
    "STOP_TITLE_COPY": "602cf97a33fc0777",
    # bra.w $1030e / rts -- init_new_game falls into enter_title instead of returning, so the `rts`
    # after the branch is unreachable
    "STOP_INIT_NEW_GAME": "6000ef784e75",
}
