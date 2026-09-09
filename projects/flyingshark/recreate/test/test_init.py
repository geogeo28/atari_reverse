"""Differential tests for src/init.c: the boot chain, the file loader, the three palette wrappers,
the per-game and per-stage resets, and one pass of `main`'s frame loop.

THIS BATTERY VERIFIES THE ROUTINES `test/conftest.py` REPLAYS. The fixture every other case in the
project runs on is built by putting `boot_init` and `init_load_assets` under the ORACLE; what is
here is the other half — the same routines' RECONSTRUCTIONS, diffed against the same original. So
the two files describe one machine from two sides, and a divergence between them shows up as a case
here rather than as a fixture nobody re-derives.

FOUR THINGS ARE PARTICULAR TO THIS SLICE.

(1) THE BOOT CHAIN MOVES THE STACK ONTO THE GAME'S OWN. `movea.l #$19094,a7` @ 0x14bee puts the
oracle's trap frames inside the PROGRAM, well above the harness's stack guard, and the candidate is
C and pushes nothing — so `boot_init`'s two cases exclude exactly the band the oracle descended
into and `test_the_boot_stack_band_is_the_one_the_oracle_really_used` pins its depth.

(2) TWO XBIOS CALLS HAVE NO `os_*` DOOR. `Physbase` and `Kbdvbase` are answered by the shim with
`OS_SCREEN_BASE` and `OS_KBDVBASE`, and `src/init.c` reads those two constants out of the same
`os.h` the shim does. `test_the_two_undoored_xbios_answers_are_the_models_own` is what says the C is
reading the model's number rather than one it chose.

(3) A PALETTE WRAPPER WRITES NO IMAGE BYTE AT ALL. Its whole effect is an ordered OS EVENT, which
`harness.differential` compares on every run — so those three cases are verified by the ledger and
by nothing else, and a reconstruction that dropped the call would be caught there.

(4) THE FRAME LOOP IS THE INTEGRATION TEST OF THE WHOLE PORT. `frame_loop_once` calls forty-five
verified cores in the original's order, and each case diffs one whole frame — four screens, 223
display records, the entity arena, the HUD and the sound module — of a level THE ORIGINAL STARTED.
See "the frame loop" below for how the worlds are staged and which arms they deliberately do not
reach.
"""
import ctypes
import pickle
import random
import re

import pytest

import abi
import conftest
import emu
import test_constants
import harness

abi.declare_glue("g_probe_disc", "g_set_palette_black", "g_set_palette_game",
                 "g_set_palette_title", "g_boot_init", "g_entry_stub",
                 "g_init_load_assets_title", "g_init_load_assets_sprites", "g_init_new_game",
                 "g_init_stage_state", "g_clear_actor_arrays", "g_frame_loop_once",
                 "g_init_load_assets", "g_main_boot")
# THE TWO FRONTEND GLUES THE BOOT COMPOSITION NEEDS, and the only place this battery reaches out of
# its own subsystem: `main`'s third `bsr` is reached by an `rts` from the title screen, so the case
# that runs the whole boot has to run the title screen too. `test_frontend.py` is where both are
# verified; here they are called, as `src/init.c` would call them if a C function could unwind.
abi.declare_glue("g_title_attract_loop")
abi.declare_glue("g_enter_title", result=ctypes.c_uint32)
abi.declare_glue("g_load_file", "g_derive_screen_ring", args=1)

# ---- the routines, and where each slice stops ---------------------------------------------------
ENTRY_ENTRY_STUB = 0x10000
ENTRY_BOOT_INIT = 0x14bee
STOP_BOOT_INIT = 0x14d06          # `bra.w main` — boot_init never returns
# ...and the ring derivation ALONE, entered one instruction past the XBIOS `Physbase` that fills D0
# and stopped at the `movea.l` that sets up the sound module's load. Entering here is what puts the
# Physbase in a case's hands: `boot_init` can only ever be run at the model's own answer.
ENTRY_RING_ARITHMETIC = 0x14c26   # `subi.l #$1f900,d0`
STOP_RING_ARITHMETIC = 0x14c9e    # `movea.l #$16304,a0`, after the ninth store
# A Physbase whose ring base is NOT already 256-aligned, so the `clr.b d0` @ 0x14c40 changes the
# answer: 0x7f8ab - 0x1f900 + 0x100 = 0x600ab, which the rounding takes down to 0x60000.
UNALIGNED_PHYSBASE = 0x7f8ab

ENTRY_LOAD_FILE = 0x10bfa
ENTRY_PROBE_DISC = 0x10c4c
ENTRY_SET_PALETTE_BLACK = 0x111a6
ENTRY_SET_PALETTE_GAME = 0x111be
ENTRY_SET_PALETTE_TITLE = 0x111d6

ENTRY_INIT_LOAD_ASSETS_TITLE = 0x11212
STOP_INIT_LOAD_ASSETS_TITLE = 0x1127e    # `bra.s $112ac`, over the patched-out disc-prompt block
ENTRY_INIT_LOAD_ASSETS_SPRITES = 0x112b2 # `st $176ea`, after the frontend's load_level_assets call

ENTRY_INIT_NEW_GAME = 0x112fa
STOP_INIT_NEW_GAME = 0x11394             # `bra.w enter_title` — it never returns to `main`
ENTRY_INIT_STAGE_STATE = 0x1139a
STOP_INIT_STAGE_DISPATCH = 0x11438       # `beq.w $12cb6`, the difficulty dispatch

ENTRY_CLEAR_ACTOR_ARRAYS = 0x115e2

ENTRY_MAIN = 0x15750                     # `bsr.w init_load_assets` — the program's first call
# `bsr.w init_stage_state` @ 0x15758. It is where `main`'s boot slice STOPS and, in the whole-boot
# case below, the instruction the title screen's own `rts` comes back to.
STOP_MAIN_THIRD_CALL = 0x15758
ENTRY_ENTER_TITLE = 0x1030e              # where `init_new_game` branches; the boot slice's stop
ENTRY_FRAME_LOOP = 0x1575c               # the loop's top, and `include/init.h`'s FRAME_LOOP_TOP
STOP_FRAME_LOOP = 0x15816                # `bra.w $1575c` — one pass ends here
# The two carry sites the frame loop's register inputs are measured at (`src/init.c`).
STOP_FRAME_AT_PLAYER_PUBLISH = 0x15774
STOP_FRAME_AT_BOMB_BLAST_STEP = 0x157d4

# ---- mirrors of include/init.h (MIRROR_HEADER below) and of the headers it reads ----------------
A_load_file_handle = 0x17774
A_load_dest = 0x17776
A_load_len = 0x1777a
A_disc_probe_result = 0x17692
A_palette_title = 0x16274
A_palette_game = 0x16294
A_palette_black = 0x162b4
BOOT_SETSCREEN_LOG = 0x70000
BOOT_SETSCREEN_PHYS = 0x78000
BOOT_RESOLUTION_LOW = 0
VECTOR_VBL = 0x70
FN_VBL_HANDLER = 0x11636
A_vbl_chain_vector = 0x11650
IKBD_CMD_JOYSTICK_EVENT_REPORTING = 0x14
KBDVBASE_JOYVEC = 0x18
A_saved_tos_joyvec = 0x19098
FN_TOS_JOYVEC_HANDLER = 0x141fa
NEO_PALETTE_OFFSET = 4
TITLE_COPY_OFFSET = 0x80
TITLE_COPY_LONGS = 0x1f40
A_level0_assets_loaded = 0x176ea
GAME_OVER_DELAY_FRAMES = 0x50
NAME_ENTRY_TIMEOUT = 0x32
CONST_WORD_ZERO = 0                # include/hud.h
NEW_GAME_LIVES_INDEX = 5
STAGE_SCROLL_POS_SEED = 0x2e
A_keep_enemy_fire_inhibit = 0x177cb
A_unread_word_176a2 = 0x176a2
A_unread_word_176a8 = 0x176a8
FRAME_LOOP_TOP = 0x1575c
FRAME_LOOP_CALLS = 45
FRAME_BLAST_SCRATCH_D0 = 0
FRAME_TEXT_X_D1 = 0
FRAME_TEXT_Y_D2 = 0

# The state `init_new_game` and `init_stage_state` write, named rather than poked as bare hex — and
# mirrored below, so a header that moved one fails by name instead of leaving this battery poking a
# stale address and still green. Each comment names the header the address is DECLARED in.
A_const_words_0123 = 0x176ac       # include/hud.h — the table four of init_new_game's stores read
A_weapon_level = 0x17714           # include/weapons.h
A_spawn_script_cursor = 0x17754    # include/weapons.h
A_item_bomb_spawned = 0x176a6      # include/weapons.h
A_bomb_falling = 0x176ee           # include/weapons.h
A_bomb_exploding = 0x176f0         # include/weapons.h
A_bomb_path_cursor = 0x176f2       # include/weapons.h
A_key_last_scancode = 0x17781      # include/irq.h
A_key_bits = 0x17780               # include/irq.h — the ACIA handler's keyboard state
A_blast_step = 0x176ec             # include/weapons.h
A_joy0_state = 0x1777e             # include/irq.h
A_player_script_fire_enable = 0x1770c  # include/player.h
A_landing_bomb_cash_timer = 0x176c0    # include/player.h
A_death_anim_cursor = 0x176f6      # include/player.h
A_game_over_flag = 0x1769a         # include/player.h
A_player_script_timer = 0x176c4    # include/player.h
A_landing_shadow_timer = 0x17740   # include/player.h
A_takeoff_shadow_timer = 0x1773e   # include/player.h
A_shadow_offset = 0x1773c          # include/player.h
A_level_distance = 0x1779a         # include/scroll.h
A_scroll_fine = 0x16430            # include/scroll.h
A_music_suspend_flag = 0x176a4     # include/sound.h
A_bonus_life_awarded_0 = 0x176c6   # include/hud.h — seven flags, BONUS_LIFE_FLAG_BYTES apart
BONUS_LIFE_THRESHOLDS = 7          # include/hud.h
BONUS_LIFE_FLAG_BYTES = 2          # include/hud.h
A_name_entry_timeout = 0x176de     # include/hud.h
A_hiscore_beaten = 0x176e4         # include/hud.h
A_name_entry_first_pass = 0x176d6  # include/frontend.h
A_item_pickup_pending = 0x176c2    # include/entity.h
A_game_over_delay = 0x176aa        # include/player.h
A_level_loop_flag_1 = 0x1769c      # include/player.h
A_level_loop_flag_2 = 0x1769e      # include/player.h
A_level_loop_flag_3 = 0x176a0      # include/player.h

A_stack_top = 0x19094              # include/globals.h
A_saved_super_ssp = 0x19014        # include/globals.h
A_entity_arena = 0x59984           # include/globals.h
A_player_bullet_arena = 0x5ae22    # include/weapons.h — the arena the three shot slots point at
PLAYER_SHOT_SLOTS = 3              # include/weapons.h — three shots of PLAYER_SHOT_BULLETS each,
PLAYER_SHOT_BULLETS = 5            # include/weapons.h   which is the arena's fifteen records
PLAYER_BULLET_BYTES = 8            # include/weapons.h
PLAYER_BULLET_STATE = 6            # include/weapons.h
FS_PROGRAM_END = 0x5aede           # include/globals.h
A_sprite_bank = 0x1be36            # include/globals.h
A_max_weapon_flag = 0x177ca        # include/hud.h
A_lives = 0x17712                  # include/player.h
A_enemy_fire_inhibit = 0x17706             # include/player.h
A_joy1_state = 0x1777f             # include/irq.h
JOY_FIRE_BIT = 7                   # include/hud.h
A_vbl_tick = 0x17720               # include/irq.h
A_scroll_pos = 0x17758             # include/scroll.h
A_level_number = 0x1642a           # include/player.h
A_level_just_started = 0x17696     # include/player.h
SHIFTER_SYNC_50HZ = 1 << 1         # include/sound.h

HW_SHIFTER_SYNC = 0xff820a         # os.h's OS_HW_SHIFTER_SYNC, the machine-speed byte
BSR_W_OPCODE = 0x6100              # `bsr.w`, the only instruction in the frame loop's body
# The KIT's own KBDVBASE struct, read out of its header rather than restated: `harness.py` mirrors
# most of `os.h` into Python but not this one, and it is where `boot_init`'s joyvec store lands.
OS_KBDVBASE = test_constants.defines("../../../tools/recreate_kit/include/os.h")["OS_KBDVBASE"]
FUZZ_CHUNKS = 4

# `boot_init`'s stack: `movea.l #$19094,a7` and then the trap pushes of Super, Setscreen, Physbase,
# `load_file`'s `movem.l` and its three GEMDOS calls, Bconout and Kbdvbase. The deepest the oracle
# reaches is A_stack_top - this, MEASURED and then pinned by
# `test_the_boot_stack_band_is_the_one_the_oracle_really_used` — a band chosen loosely would drop
# bytes from the diff that were never stack.
# What TOS's own joyvec slot is seeded with, so that `boot_init`'s save of it into
# `A_saved_tos_joyvec` copies something rather than 0 over 0. Any non-zero longword serves; this one
# is not a valid address, which is the point — nothing may follow it.
TOS_JOYVEC_SENTINEL = 0xfeedface
A_cheat_used_flag = 0x176d4        # include/hud.h — `clr.w $176d4` @ 0x14d00, the boot chain's last store

# Sixteen ST colour words: the block XBIOS Setpalette is pointed at.
PALETTE_BYTES = 32

BOOT_STACK_DEPTH = 0x52
BOOT_STACK_BAND = (A_stack_top - BOOT_STACK_DEPTH, A_stack_top)


def _boot_pokes(post_load_image):
    """A\\MODULE.BAK staged, which is the only file the boot chain opens."""
    pokes, _handles = harness.stage_files(
        [conftest.staged_load(post_load_image, *conftest.BOOT_LOADS[0])])
    return pokes


def _boot_case(post_load_image, entry, glue, extra_pokes=None, note=""):
    pokes = _boot_pokes(post_load_image)
    pokes.update(extra_pokes or {})
    return abi.run_case(entry, glue, pokes=pokes, stop_pc=STOP_BOOT_INIT,
                        exclude=[BOOT_STACK_BAND],
                        max_insns=conftest.BOOT_SLICE_MAX_INSNS, note=note)


# =================================================================================================
# boot_init @ 0x14bee — SLICE [0x14bee, 0x14d06) — and entry_stub @ 0x10000 over the same span
# =================================================================================================


def test_boot_init_builds_the_machine_the_fixture_is_made_of(post_load_image):
    """The whole routine: the supervisor token, the nine screen pointers, the sound module, the two
    exception vectors, the IKBD command and TOS's displaced joystick callback.

    It runs on the POST-LOAD image, so it is re-doing work the fixture's own replay already did —
    which is the point of running it here rather than on the bare .PRG: every store it makes is
    compared against the original's on a machine where most of them are already at their final
    value, and the two that are NOT (the chain operand, which the fixture leaves holding
    `vbl_handler`'s own address, and the module's bytes) are the ones a reconstruction could most
    easily get wrong.
    """
    _boot_case(post_load_image, ENTRY_BOOT_INIT, lambda lib, buf: lib.g_boot_init(buf))


def test_the_boot_stack_band_is_the_one_the_oracle_really_used(post_load_image):
    """`BOOT_STACK_DEPTH` is measured, not guessed: the exclude band must be exactly the stack.

    An exclude band suspends the byte-for-byte guarantee over its range, and the harness only checks
    that the band reaches the stack — a band twice as deep would still pass while hiding any store
    the routine made below it. So the depth is pinned against the oracle's own `min_a7` here, and a
    boot chain that pushed one byte more fails by name rather than silently widening what nobody
    compares.
    """
    info = _boot_case(post_load_image, ENTRY_BOOT_INIT, lambda lib, buf: lib.g_boot_init(buf))
    assert info["regs"]["min_a7"] == BOOT_STACK_BAND[0], (
        f"the oracle's deepest stack pointer is {info['regs']['min_a7']:#x}, but the band excluded "
        f"from the diff starts at {BOOT_STACK_BAND[0]:#x}")


def test_entry_stub_is_the_branch_into_the_boot_chain(post_load_image):
    """The .PRG's entry point, over the same span, entered one `bra.w` earlier.

    The branch itself stores nothing, so what this adds over the case above is that the operand at
    0x10002 really names `boot_init`: a wrong one would run the 44-byte plaintext banner at 0x10004
    as instructions rather than reach a checkpoint at all.
    """
    _boot_case(post_load_image, ENTRY_ENTRY_STUB, lambda lib, buf: lib.g_entry_stub(buf))


def test_the_two_undoored_xbios_answers_are_the_models_own():
    """`Physbase` and `Kbdvbase` have no `os_*` door, so `src/init.c` reads two `os.h` constants.

    THE DIFFERENTIAL IS THE PIN for both — the ring values and the joyvec store land at addresses
    derived from them, and a C that read a different number would differ there. What this adds is
    the two facts a diff could not state: that the Physbase the C reads is the one the shim answers
    (`harness.OS_SCREEN_BASE`, the same constant), and that `OS_KBDVBASE` is read out of the KIT's
    own header rather than restated here — so a kit that moved the struct fails by name instead of
    quietly putting the joyvec slot somewhere the model serves as poked input.
    """
    kit_os_h = test_constants.defines("../../../tools/recreate_kit/include/os.h")
    assert kit_os_h["OS_SCREEN_BASE"] == harness.OS_SCREEN_BASE, (
        "the shim's Physbase answer and harness.py's mirror of it have drifted")
    joyvec = OS_KBDVBASE + KBDVBASE_JOYVEC
    assert joyvec + 4 <= harness.OS_CON_PENDING, (
        f"the KBDVBASE joyvec slot at {joyvec:#x} has reached the harness-poked input block, which "
        f"make_image refuses to poke and the model would then be serving as game memory")


@pytest.mark.parametrize("physbase,rounding_matters",
                         ((abi.SCREEN_RING_PHYSBASE, False),
                          (harness.OS_SCREEN_BASE, False),
                          (UNALIGNED_PHYSBASE, True)),
                         ids=("harness", "model", "unaligned"))
def test_the_ring_derivation_rounds_at_a_physbase_the_model_cannot_answer_with(physbase,
                                                                              rounding_matters):
    """`derive_screen_ring`'s MASK, driven against the oracle at a Physbase that exercises it.

    EVERY PHYSBASE THE MODEL CAN ANSWER WITH IS ALREADY 256-ALIGNED once the `subi.l #$1f900` and
    the `addi.l #$100` are done with it, so dropping `& ~0xff` from the C leaves every other case in
    this battery green (measured 2026-09-07 — the same hole `test_image_model.py` found on the
    transcription side). `boot_init` itself can only ever run at `OS_SCREEN_BASE`; entering at
    0x14c26 puts D0 in the case's hands, and `g_derive_screen_ring` is the same entry on the
    candidate's side.

    The nine longwords are poisoned first, so a candidate that derived none of them could not pass
    on the values the post-load fixture already holds.
    """
    raw = (physbase - conftest.SCREEN_RING_BYTES) & 0xffffffff
    assert bool((raw + conftest.SCREEN_RING_ALIGN) & (conftest.SCREEN_RING_ALIGN - 1)) \
        == rounding_matters, (
        f"{physbase:#x} no longer says what this case was parametrised to say about the `clr.b`")
    pokes = {address: b"\xde\xad\xbe\xef" for address in conftest.ring_pointers(physbase)}
    abi.run_case(ENTRY_RING_ARITHMETIC, lambda lib, buf: lib.g_derive_screen_ring(buf, physbase),
                 pokes=pokes, regs={"d0": physbase}, stop_pc=STOP_RING_ARITHMETIC,
                 note=f"Physbase {physbase:#x}")


def test_boot_init_over_the_bare_loaded_image(post_load_image):
    """The same routine on an image whose vector page and screen pointers are still ZERO.

    `post_load_image` already carries every store the boot chain makes, so a reconstruction that
    made none of them would agree with the oracle on most of them anyway. Poking the whole of the
    boot chain's output back to zero is what separates "wrote it" from "it was already there" for
    the vectors and the ring, without needing the attribution pass (which cannot run here: the
    oracle's own stack band is excluded).
    """
    zeroed = {VECTOR_VBL: bytes(4), conftest.VECTOR_ACIA: bytes(4),
              A_vbl_chain_vector: bytes(4), A_saved_super_ssp: bytes(4),
              A_saved_tos_joyvec: bytes(4),
              # ...and the two the routine COPIES rather than computes, seeded non-zero. Zeroing
              # these would zero the SOURCE as well as the destination, which is what made the save
              # at 0x14cf8 and the `clr.w` at 0x14d00 invisible: both write 0 over 0 (measured).
              OS_KBDVBASE + KBDVBASE_JOYVEC: TOS_JOYVEC_SENTINEL.to_bytes(4, "big"),
              A_cheat_used_flag: b"\x5a\xa5"}
    for address in conftest.ring_pointers(abi.SCREEN_RING_PHYSBASE):
        zeroed[address] = bytes(4)
    _boot_case(post_load_image, ENTRY_BOOT_INIT, lambda lib, buf: lib.g_boot_init(buf),
               extra_pokes=zeroed, note="entered on a zeroed boot state")


# =================================================================================================
# load_file @ 0x10bfa and probe_disc @ 0x10c4c
# =================================================================================================
#
# EVERY RECORD IS LOADED WITH CONTENT THE IMAGE DOES NOT ALREADY HOLD. The post-load fixture has all
# seven files at their destinations already, so staging the REAL bytes would make a reconstruction
# that never copied anything agree with the oracle over every byte. The staged content is therefore
# pseudo-random, of the record's own length, which makes the `Fread` visible.

# The eight records, and the file on disc A each names. The disc name is not the DOS path — the
# path's case is not the extracted folder's — so `conftest`'s own two tables are what map between
# them, and this is their union in record order.
RECORD_DISC_NAMES = dict((conftest.TITLE_LOAD,) + conftest.BOOT_LOADS)
ALL_RECORDS = (conftest.A_file_rec_flyshk_neo, conftest.A_file_rec_module_bak,
               conftest.A_file_rec_sprites_cru, conftest.A_file_rec_level_map,
               conftest.A_file_rec_hsc_0, conftest.A_file_rec_hsc_1,
               conftest.A_file_rec_hsc_2, conftest.A_file_rec_hsc_3)


def _staged_record(post_load_image, record, seed):
    """(pokes, dest, data) for one record staged with content of this test's own choosing.

    THE LENGTH IS THE FILE'S, NOT THE RECORD'S, and the difference is not academic:
    A\\LEVEL1.MAP's record asks for 0x1388 bytes to 0x16432, which would run to 0x177ba — over
    `load_dest`, `load_len` and `load_file_handle`, the loader's own three scratch longwords. The
    real file is 3,664 bytes and GEMDOS's short read is the only thing between the routine and
    closing a handle it has just overwritten with map data. `test_a_records_length_can_exceed_its
    _files` is the case that states it.

    AND IT IS WHY NOTHING PINS `load_file`'s RE-READ of the handle: the routine passes `Fread` the
    handle out of D0 and `Fclose` the WORD at `A_load_file_handle`, two spellings of one value that
    can only differ on a load that overwrote the word. Such a load exists — a full-length
    A\\LEVEL1.MAP — but the overrun reaches `A_load_file_handle` (0x17774) BEFORE `A_load_dest`
    (0x17776), so the `Fclose` that follows is given a scrap of map data and the model refuses the
    whole run rather than differing. The re-read is written as the original writes it and is
    unpinnable, not merely unpinned.
    """
    dest, _record_length, _dos_path = conftest.file_record(post_load_image, record)
    dos_path, data = conftest.seeded_load(post_load_image, record, RECORD_DISC_NAMES[record], seed)
    pokes, _handles = harness.stage_files([(dos_path, data)])
    return pokes, dest, data


@pytest.mark.parametrize("record", ALL_RECORDS)
def test_load_file_reads_each_record_to_its_own_destination(post_load_image, record):
    """All eight asset records, each with its own staged content.

    The records' destinations and lengths are read OUT OF THE IMAGE — both longwords are relocated,
    so the image is the only place they are true — which is what makes this a test of the routine
    rather than of a transcription of the table.
    """
    pokes, _dest, _data = _staged_record(post_load_image, record, seed=record)
    abi.run_case(ENTRY_LOAD_FILE, lambda lib, buf: lib.g_load_file(buf, record),
                 pokes=pokes, regs={"a0": record}, note=f"record {record:#x}")


def test_a_records_length_can_exceed_its_files(post_load_image):
    """A\\LEVEL1.MAP asks for 0x1388 bytes and the file holds 3,664: the short read is what stops
    the load, and here it is what stops the loader overwriting its OWN state.

    0x16432 + 0x1388 runs to 0x177ba, which covers `A_load_dest`, `A_load_len` and
    `A_load_file_handle` — so a full-length A\\LEVEL1.MAP would leave `load_file` closing whatever
    the map's last bytes happened to be. The arithmetic is asserted here rather than merely
    observed, because it is a property of the SHIPPED data and a level map that grew would break the
    routine that loads it.
    """
    destination, record_length, _path = conftest.file_record(post_load_image,
                                                             conftest.A_file_rec_level_map)
    on_disc = len(conftest.disk_bytes(RECORD_DISC_NAMES[conftest.A_file_rec_level_map],
                                      record_length))
    assert on_disc < record_length, "A\\LEVEL1.MAP now fills its record; the short read is gone"
    assert destination + on_disc <= A_load_file_handle, "the real load already reaches the loader"
    assert destination + record_length > A_load_file_handle, (
        "the record no longer overruns the loader's scratch, so this case says nothing")

    pokes, _dest, _data = _staged_record(post_load_image, conftest.A_file_rec_level_map, seed=1)
    abi.run_case(ENTRY_LOAD_FILE,
                 lambda lib, buf: lib.g_load_file(buf, conftest.A_file_rec_level_map),
                 pokes=pokes, regs={"a0": conftest.A_file_rec_level_map})


def test_load_file_attribution(post_load_image):
    """Poison the loader's three scratch longwords and the head of the destination."""
    record = conftest.A_file_rec_module_bak
    pokes, _dest, _data = _staged_record(post_load_image, record, seed=2)
    abi.run_case(ENTRY_LOAD_FILE, lambda lib, buf: lib.g_load_file(buf, record),
                 pokes=pokes, regs={"a0": record}, poison=True)


@pytest.mark.parametrize("caller_a0", ALL_RECORDS)
def test_probe_disc_ignores_its_callers_record(post_load_image, caller_a0):
    """The probe always opens A\\SPRITES.cru, whatever A0 holds — its own `lea` @ 0x10c50.

    Driving A0 with every one of the eight records is what makes that a tested claim: a
    reconstruction that used the caller's record would load a different name for seven of them and,
    the file not being staged, would be REFUSED rather than merely differ.
    """
    pokes, _dest, _data = _staged_record(post_load_image, conftest.A_file_rec_sprites_cru, seed=3)
    pokes[A_disc_probe_result] = b"\xff\xff\xff\xff"
    abi.run_case(ENTRY_PROBE_DISC, lambda lib, buf: lib.g_probe_disc(buf),
                 pokes=pokes, regs={"a0": caller_a0}, note=f"a0={caller_a0:#x}")


def test_probe_disc_answers_a_whole_longword(post_load_image):
    """Callers test the result with `bpl`/`bmi`, so the WORD half of a handle would not do.

    The probe stores `Fopen`'s whole D0; poisoning the four bytes is what says all four are written
    rather than the low two over a stale high half.
    """
    pokes, _dest, _data = _staged_record(post_load_image, conftest.A_file_rec_sprites_cru, seed=4)
    abi.run_case(ENTRY_PROBE_DISC, lambda lib, buf: lib.g_probe_disc(buf),
                 pokes=pokes, regs={"a0": conftest.A_file_rec_sprites_cru}, poison=True)


# =================================================================================================
# the three palette wrappers @ 0x111a6 / 0x111be / 0x111d6
# =================================================================================================


@pytest.mark.parametrize("entry,glue_name,table", (
    (ENTRY_SET_PALETTE_BLACK, "g_set_palette_black", A_palette_black),
    (ENTRY_SET_PALETTE_GAME, "g_set_palette_game", A_palette_game),
    (ENTRY_SET_PALETTE_TITLE, "g_set_palette_title", A_palette_title),
))
def test_a_palette_wrapper_is_its_setpalette_and_nothing_else(entry, glue_name, table):
    """Each wrapper writes NO image byte: the ordered OS EVENT is the whole surface.

    `harness.differential` compares that stream on every run, so a reconstruction that dropped the
    call, made two, or named a different table is separable here and nowhere else — the image is
    identical either way.
    """
    abi.run_case(entry, lambda lib, buf: getattr(lib, glue_name)(buf),
                 note=f"{glue_name} -> {table:#x}")


def test_the_three_palettes_are_three_different_tables():
    """A wrapper that named its neighbour's table would pass every case above.

    The event carries the ADDRESS, so the three are separable only while the three addresses differ
    — which they do, sixteen words apart, and this is what would notice if `include/init.h` came to
    spell one of them as another.
    """
    tables = (A_palette_black, A_palette_game, A_palette_title)
    assert len(set(tables)) == len(tables), "two wrappers name the same table"
    colours = [bytes(harness.BASE_IMAGE[table:table + PALETTE_BYTES]) for table in tables]
    assert len(set(colours)) == len(colours), (
        "two of the three palettes hold the same sixteen words, so the event's address is the only "
        "thing separating them and this file's addresses could be wrong in a way nothing shows")
    assert colours[0] == bytes(PALETTE_BYTES), (
        "palette_black is meant to be sixteen ZERO colour words")


# =================================================================================================
# init_load_assets @ 0x11212 — the title slice and the sprite slice
# =================================================================================================


def test_the_title_slice_loads_the_picture_and_copies_it_to_the_screen(post_load_image):
    """[0x11212, 0x1127e): the palette, the NEO file, its palette, the Setscreen and the 32,000-byte
    copy to `Physbase - 0x80`.

    The picture is staged with content of this test's own choosing, so the copy is visible: the
    fixture already holds A\\SPRITES.cru at the same destination, and staging the real NEO would
    leave a reconstruction that copied nothing agreeing over the whole band.
    """
    pokes, _dest, _data = _staged_record(post_load_image, conftest.A_file_rec_flyshk_neo, seed=5)
    abi.run_case(ENTRY_INIT_LOAD_ASSETS_TITLE,
                 lambda lib, buf: lib.g_init_load_assets_title(buf), pokes=pokes,
                 stop_pc=STOP_INIT_LOAD_ASSETS_TITLE, max_insns=conftest.LOAD_SLICE_MAX_INSNS)


def test_the_title_copy_is_a_whole_frame_below_the_screen():
    """The copy's geometry, stated once here and read by nothing else: 32,000 bytes is one whole
    320x200 four-plane frame, and the 0x80 offset is a NEOchrome header's own length.

    `test/conftest.py` states the same two facts for the fixture's exclusion band, so this is
    CLAUDE.md §5's cross-file pin: one fact, two places, held equal by a test rather than by care.
    """
    assert TITLE_COPY_LONGS * 4 == conftest.TITLE_COPY_BYTES
    assert TITLE_COPY_OFFSET == conftest.TITLE_COPY_OFFSET
    assert TITLE_COPY_LONGS * 4 == 32000


def test_the_sprite_slice_loads_the_bank_and_relocates_its_directory(post_load_image):
    """[0x112b2, 0x112f8]: the flag, the bank, 256 relocated record pointers, four terminators.

    Staged content again, and here it matters twice: the relocation ADDS the bank's base to a
    longword read out of the file, so a run over the real bank would be adding it to pointers the
    fixture has already relocated once — a different arithmetic from the one the routine performs on
    a freshly loaded file.
    """
    pokes, _dest, _data = _staged_record(post_load_image, conftest.A_file_rec_sprites_cru, seed=6)
    pokes[A_level0_assets_loaded] = b"\x00"
    # The four terminators the boot chain has ALREADY written into the fixture: without poking them
    # away, a reconstruction that wrote none of them agrees over all four (measured 2026-09-07).
    for index in range(conftest.SPRITE_RESTORE_LISTS):
        pokes[conftest.A_sprite_restore_lists + index * conftest.SPRITE_RESTORE_LIST_BYTES
              + conftest.SPRITE_RESTORE_FIRST_ENTRY] = b"\x12\x34"
    abi.run_case(ENTRY_INIT_LOAD_ASSETS_SPRITES,
                 lambda lib, buf: lib.g_init_load_assets_sprites(buf), pokes=pokes,
                 max_insns=conftest.LOAD_SLICE_MAX_INSNS)


def test_the_patched_out_disc_prompt_block_is_unreachable():
    """0x11280..0x112aa is DEAD CODE the shipped binary branches over, and its first word is not
    even an instruction.

    `include/init.h` says so and `src/init.c` reconstructs neither the prompt nor the `probe_disc`
    call inside it. The claim is checkable: the slice's last instruction is a `bra.s` whose target
    is past the block, and the first word of the block is a line-F opcode.
    """
    branch = bytes(harness.BASE_IMAGE[STOP_INIT_LOAD_ASSETS_TITLE:STOP_INIT_LOAD_ASSETS_TITLE + 2])
    assert branch[0] == 0x60, "0x1127e is no longer a `bra.s`"
    target = STOP_INIT_LOAD_ASSETS_TITLE + 2 + branch[1]
    assert target == ENTRY_INIT_LOAD_ASSETS_SPRITES - 6, (
        f"the branch goes to {target:#x}, not to the `clr.w d0` before the sprite slice")
    dead_word = int.from_bytes(bytes(harness.BASE_IMAGE[0x11280:0x11282]), "big")
    assert dead_word >> 12 == 0xf, (
        f"the first word of the patched-out block is {dead_word:#06x}, which is a real instruction")


# =================================================================================================
# init_new_game @ 0x112fa and init_stage_state @ 0x1139a
# =================================================================================================


@pytest.mark.parametrize("max_weapon", (0x00, 0x01, 0xff))
def test_init_new_game_resets_the_per_game_state(post_load_image, max_weapon):
    """The whole slice, with the "J H" cheat flag clear and set.

    The flag is the routine's ONE branch: with it set, the weapon level and the word beside it
    survive a new game, which is what makes the cheat a cheat. Both arms are driven, and the two
    words are poked to a value the reset would visibly change.
    """
    pokes = {A_max_weapon_flag: bytes([max_weapon]),
             A_weapon_level: b"\x00\x04",        # a level the reset would visibly take away
             A_unread_word_176a2: b"\x5a\xa5"}
    abi.run_case(ENTRY_INIT_NEW_GAME, lambda lib, buf: lib.g_init_new_game(buf), pokes=pokes,
                 stop_pc=STOP_INIT_NEW_GAME, max_insns=conftest.LOAD_SLICE_MAX_INSNS,
                 note=f"max_weapon_flag={max_weapon:#04x}")


@pytest.mark.parametrize("max_weapon", (0x00, 0xff))
@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_init_new_game_over_random_prior_state(chunk, max_weapon):
    """Every word the reset writes, poked to junk first, sharded so `-n auto` spreads them.

    TWELVE OF ITS STORES WERE 0 OVER 0 WITHOUT THIS. The words are zero in the shipped `.PRG` and
    nothing in the boot chain writes them, so a reconstruction that dropped any of the six extra
    bonus-life flags, the three loop flags, `name_entry_first_pass`, `hiscore_beaten` or
    `item_pickup_pending` was indistinguishable from one that kept them (measured 2026-09-07). A
    reset is nothing but stores; verifying one from a machine that is already reset proves nothing.
    """
    written = [addr for addr in (A_level_loop_flag_1, A_level_loop_flag_2, A_level_loop_flag_3,
                                 A_game_over_delay, A_level_number, A_weapon_level,
                                 A_unread_word_176a2, A_name_entry_first_pass, A_hiscore_beaten,
                                 A_name_entry_timeout, A_lives, A_item_pickup_pending)]
    written += [A_bonus_life_awarded_0 + flag * BONUS_LIFE_FLAG_BYTES
                for flag in range(BONUS_LIFE_THRESHOLDS)]
    rng = random.Random(0x11e60 + chunk)
    for _ in range(4):
        pokes = {address: bytes([rng.randrange(0x100), rng.randrange(0x100)])
                 for address in written}
        pokes[A_max_weapon_flag] = bytes([max_weapon])
        abi.run_case(ENTRY_INIT_NEW_GAME, lambda lib, buf: lib.g_init_new_game(buf), pokes=pokes,
                     stop_pc=STOP_INIT_NEW_GAME, max_insns=conftest.LOAD_SLICE_MAX_INSNS,
                     note=f"max_weapon_flag={max_weapon:#04x}")


def test_init_new_game_reads_its_immediates_out_of_the_constant_table(post_load_image):
    """Four of its stores take their value from `A_const_words_0123` rather than from an immediate.

    Rewriting the table is what turns that from a comment into a test: a reconstruction that
    compiled 0 and 5 in would keep writing 0 and 5 while the original writes whatever the table now
    holds. The table is initialised DATA and nothing at run time writes it, so this is contract
    coverage and the STATUS row says so.
    """
    pokes = {A_const_words_0123: b"\x11\x11" + b"\x22\x22" * 4 + b"\x33\x33"}
    abi.run_case(ENTRY_INIT_NEW_GAME, lambda lib, buf: lib.g_init_new_game(buf), pokes=pokes,
                 stop_pc=STOP_INIT_NEW_GAME, max_insns=conftest.LOAD_SLICE_MAX_INSNS)


@pytest.mark.parametrize("keep_enemy_fire_inhibit", (0x00, 0x01, 0xff))
def test_init_stage_state_resets_the_per_stage_state(post_new_game_image, new_game_pokes,
                                                     keep_enemy_fire_inhibit):
    """The whole slice, over a started GAME, with the one guarded store on both arms.

    `keep_enemy_fire_inhibit` is written nowhere in the image, so its set arm is CONTRACT coverage: the
    game can only ever reach the clear. Both are driven because the flag is one `st` away from
    mattering, and `enemy_fire_inhibit` is poked non-zero so the two arms differ.
    """
    pokes = dict(new_game_pokes)
    pokes[A_keep_enemy_fire_inhibit] = bytes([keep_enemy_fire_inhibit])
    pokes[A_enemy_fire_inhibit] = b"\x00\x01"
    abi.run_case(ENTRY_INIT_STAGE_STATE, lambda lib, buf: lib.g_init_stage_state(buf), pokes=pokes,
                 stop_pc=STOP_INIT_STAGE_DISPATCH,
                 note=f"keep_enemy_fire_inhibit={keep_enemy_fire_inhibit:#04x}")


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_init_stage_state_over_random_prior_state(new_game_pokes, chunk):
    """Every word the reset writes, poked to junk first, sharded so `-n auto` spreads them.

    A reset verified only from a machine whose state is already zero cannot tell a store that
    happened from one that did not — which is the whole failure mode of a routine that is nothing
    but stores.
    """
    written = (A_key_last_scancode, A_joy1_state, A_joy0_state,
               A_player_script_fire_enable, A_level_distance, A_unread_word_176a8,
               A_item_bomb_spawned, A_music_suspend_flag, A_scroll_fine,
               A_landing_bomb_cash_timer, A_death_anim_cursor, A_enemy_fire_inhibit, A_game_over_flag,
               A_player_script_timer, A_bomb_falling, A_bomb_exploding,
               A_landing_shadow_timer, A_takeoff_shadow_timer, A_shadow_offset, A_scroll_pos)
    # THE TWO `clr.l` STORES GET FOUR BYTES, not two: the low word of each is 0 in the image and
    # `init_new_game` never touches it, so a two-byte poke leaves a `clr.l` -> `clr.w` mutation
    # writing 0 over 0 (measured 2026-09-07).
    written_long = (A_spawn_script_cursor, A_bomb_path_cursor)
    rng = random.Random(0x11175 + chunk)
    for _ in range(6):
        pokes = dict(new_game_pokes)
        for address in written:
            pokes[address] = bytes([rng.randrange(0x100), rng.randrange(0x100)])
        for address in written_long:
            pokes[address] = bytes(rng.randrange(0x100) for _ in range(4))
        pokes[A_keep_enemy_fire_inhibit] = bytes([rng.choice([0, 0xff])])
        abi.run_case(ENTRY_INIT_STAGE_STATE, lambda lib, buf: lib.g_init_stage_state(buf),
                     pokes=pokes, stop_pc=STOP_INIT_STAGE_DISPATCH)


# =================================================================================================
# clear_actor_arrays @ 0x115e2
# =================================================================================================


def test_clear_actor_arrays_clears_to_the_end_of_the_program(post_load_image):
    """0x59984..0x5aedd, over an arena seeded non-zero — including the nine bytes A\\MODULE.BAK's
    load leaves over entity slot 0 (`include/globals.h`).

    The guard byte below the arena is what pins the START, and the program's own last byte pins the
    END: the loop's limit is `FS_PROGRAM_END` exclusive, and it is a DO-WHILE, so a reconstruction
    that made it a while-loop would still be right here and wrong for an empty range.
    """
    rng = random.Random(0xac70)
    span = FS_PROGRAM_END - A_entity_arena
    # A guard byte at BOTH ends. The one ABOVE the limit is what pins where the loop STOPS: the byte
    # at FS_PROGRAM_END is 0 in the image, so a `<=` bound would clear 0 over 0 and survive
    # (measured 2026-09-07).
    pokes = {A_entity_arena - 1: bytes(rng.randrange(1, 0x100) for _ in range(span + 2))}
    abi.run_case(ENTRY_CLEAR_ACTOR_ARRAYS, lambda lib, buf: lib.g_clear_actor_arrays(buf),
                 pokes=pokes)


def test_clear_actor_arrays_attribution(post_load_image):
    """Poison the arena: a candidate that cleared nothing would stay canary over an already-zero
    fixture, which is what `post_load_image` mostly is."""
    abi.run_case(ENTRY_CLEAR_ACTOR_ARRAYS, lambda lib, buf: lib.g_clear_actor_arrays(buf),
                 poison=True)


# =================================================================================================
# the frame loop @ 0x1575c — SLICE [0x1575c, 0x15816)
# =================================================================================================
#
# THE WORLD IS THE ORIGINAL'S OWN. `init_stage_state` @ 0x1139a is run under the oracle with level
# 0's files staged, which falls through `difficulty_apply_fire_rates` into `start_level` and leaves
# a stage started, prescrolled and ready — and then the ORIGINAL'S OWN FRAME LOOP is run for as many
# frames as the world needs. Nothing in the staging writes a game byte itself.
#
# EACH FRAME IS ENTERED WITH `vbl_tick` AT THE BUDGET, so `render_frame` takes its `Vsync` arm
# instead of spinning. The spin is the sprite battery's business (it needs an external agent's
# store, and one arrival per frame would make a whole-loop schedule) and it changes nothing else the
# frame does. `test_sprite.py::test_render_frame_waits_out_the_rest_of_its_frame_budget` is where
# the other arm lives.
#
# TWO ARMS THE VERIFIED FRAMES DO NOT REACH, and both leave the loop by UNWINDING THE STACK rather
# than returning — which a C function cannot express and a one-pass slice cannot contain:
# `read_player_input`'s abort key, and `level_progress_check`'s level-advance. A third,
# `restart_level_at_checkpoint`, is reached through the player's death and branches back to the
# loop's top — so a frame in which the player dies runs TWO passes on the oracle side and one on the
# candidate's. `_stage_frames` refuses to hand out such a frame, by watching the life count.

# The joystick script the staged frames are driven with: fire every fourth frame and nothing else.
# Holding a direction steers the plane into the scenery, and a plane that dies restarts the stage.
FRAME_FIRE_PERIOD = 4
FRAME_JOYSTICK_FIRE = 0x80
# ...and the keyboard's bomb button, `key_bits` bit 5 (`src/player.c`'s KEY_BOMB_BIT), held from the
# frame after the busy window closes so that the frames after it have a bomb in the air and then a
# blast going off. It is held rather than tapped because `bomb_drop` is guarded on both in-flight
# flags: a held key drops one bomb, and the next only once the blast has retired.
FRAME_KEY_BOMB = 1 << 5
BOMB_HELD_FROM = 182
# A frame of a started stage costs about 27,000 instructions; the cap is loose enough not to be a
# tuning knob and tight enough that a frame which fell into a wait loop is still caught.
FRAME_MAX_INSNS = 2_000_000

# ---- ONE PLAY-THROUGH, THREE WINDOWS ------------------------------------------------------------
#
# Every whole-frame case runs on a frame of the SAME continuous game, and the windows are slices of
# it. Three reasons, in order of weight: a world is then never the product of a replay some other
# case did not make; the frames of one window are the frames the previous window's own play produced;
# and the replay is paid for once per `make test` rather than once per window per xdist worker.
FRAME_WINDOW_LENGTH = 4
FRAME_WINDOWS = {
    # the stage as `start_level` leaves it: the plane is still on its take-off script and nothing
    # is alive, so what these verify is the loop's SHAPE — all forty-five calls over a real ring
    "quiet": 0,
    # far enough in that level 1's first formation is alive and the plane's shots are in the air
    "busy": 178,
    # ...and far enough past BOMB_HELD_FROM that the bomb has fallen and its blast is going off
    "blast": 190,
}
# What each window has to MEAN, measured over its own frames (2026-09-07). A floor of "more than
# nothing" would let a window drift to a single straggler and still call itself busy.
FRAME_BUSY_MIN_LIVE_SLOTS = 2     # level 1's first formation is a PAIR
FRAME_BUSY_MIN_BULLETS = 1        # firing every fourth frame keeps one or two bullets in the air
FRAME_BLAST_MIN_STEP = 1          # ...and the blast is between its first step and its last
FRAME_BLAST_MAX_STEP = 0xe        # `include/weapons.h`'s BLAST_LAST_STEP, where it retires


def _joystick_byte(frame):
    """The stick byte frame `frame` of the staged play-through is driven with."""
    return FRAME_JOYSTICK_FIRE if frame % FRAME_FIRE_PERIOD == 0 else 0


def _key_bits_byte(frame):
    """...and its `key_bits`, which is the ACIA handler's byte and nothing in the loop writes."""
    return FRAME_KEY_BOMB if frame >= BOMB_HELD_FROM else 0


def _frame_input_pokes(frame):
    """The three bytes a frame of the staged play-through is entered with.

    ONE DEFINITION FOR BOTH SIDES: the oracle-only replay that builds the worlds and the
    differential that verifies one of them enter each frame identically, so a case cannot verify a
    frame of a different play-through than the one its world came from.
    """
    return {A_vbl_tick: conftest.RENDER_FRAME_VBL_BUDGET.to_bytes(4, "big"),
            A_joy1_state: bytes([_joystick_byte(frame)]),
            A_key_bits: bytes([_key_bits_byte(frame)])}


def _run_one_frame(image, frame):
    """One pass of the ORIGINAL's frame loop over `image`, at this frame's declared input."""
    image = bytearray(image)
    for address, data in _frame_input_pokes(frame).items():
        image[address:address + len(data)] = data
    final, _writes, _regs = emu.run(image, ENTRY_FRAME_LOOP, stop_pc=STOP_FRAME_LOOP,
                                    max_insns=FRAME_MAX_INSNS)
    return bytearray(final)


@pytest.fixture(scope="session")
def started_level_image(post_new_game_image, tmp_path_factory):
    """A stage the ORIGINAL started: `conftest.started_level`, cached across the xdist workers.

    It runs `init_stage_state` @ 0x1139a to the `rts` it ends on, following the routine's own
    dispatch through `difficulty_apply_fire_rates` into `start_level` — which loads level 0's
    assets, installs the level record, seeds the map cursor and prescrolls the whole screen in with
    the palette black. So the world every frame case runs on is the game's, down to the terrain in
    all four screens.
    """
    return conftest.built_once_per_run(tmp_path_factory, "started_level.img",
                                       lambda: conftest.started_level(post_new_game_image))


def _stage_frames(started, windows):
    """{name: [image, ...]} — `windows`' frames, all cut from ONE run of the original's own loop.

    THE LIFE COUNT IS WATCHED rather than assumed: the player's death runs
    `restart_level_at_checkpoint`, which branches back to the loop's top instead of returning — so
    the oracle would make two passes where the candidate makes one, and the case would fail for a
    reason that is not about the reconstruction. A window that reached one is a window to move, and
    this says so rather than producing it.
    """
    lives = int.from_bytes(bytes(started[A_lives:A_lives + 2]), "big")
    worlds = {name: [] for name in windows}
    image = started
    for frame in range(max(windows.values()) + FRAME_WINDOW_LENGTH):
        for name, first in windows.items():
            if first <= frame < first + FRAME_WINDOW_LENGTH:
                worlds[name].append(image)
        image = _run_one_frame(image, frame)
        now = int.from_bytes(bytes(image[A_lives:A_lives + 2]), "big")
        assert now == lives, (
            f"the plane died on frame {frame}, so that frame restarts the stage and runs the loop "
            f"twice; move the windows (FRAME_WINDOWS) rather than verifying them")
    return worlds


@pytest.fixture(scope="session")
def frame_worlds(post_load_image, started_level_image, tmp_path_factory):
    """`{window: [pokes per frame]}` for FRAME_WINDOWS, built once per `make test`.

    The worlds travel as POKES because a staged image cannot be handed to `differential()` — the
    autouse base-image fixture owns that (README.md) — and they are pickled into the run's shared
    directory for the same reason `conftest.staged_world_pokes` is: a session fixture is per
    PROCESS, so under `-n auto` "once a session" would be once per core.
    """
    def build():
        return pickle.dumps({
            name: [conftest.byte_run_pokes(post_load_image, world) for world in frames]
            for name, frames in _stage_frames(started_level_image, FRAME_WINDOWS).items()})

    return pickle.loads(bytes(conftest.built_once_per_run(tmp_path_factory, "frame_worlds.pickle",
                                                          build)))


def _staged_image(post_load_image, pokes):
    """`post_load_image` with one staged frame's pokes applied — what a case READS a world through."""
    image = bytearray(post_load_image)
    for address, data in pokes.items():
        image[address:address + len(data)] = data
    return image


def _frame_case(frame_worlds, window, index):
    """One frame of `window`, entered with the input the staged play-through gives THAT frame.

    Keyed on the ABSOLUTE frame number: `_stage_frames` drives the input from `first + index`, so an
    index-keyed byte here would run a frame of a different play-through than the one the world came
    from. Both sides still get the same bytes either way — what it would cost is the claim that this
    is frame `first + index` of one continuous game.
    """
    frame = FRAME_WINDOWS[window] + index
    pokes = dict(frame_worlds[window][index])
    pokes.update(_frame_input_pokes(frame))
    abi.run_case(ENTRY_FRAME_LOOP, lambda lib, buf: lib.g_frame_loop_once(buf), pokes=pokes,
                 stop_pc=STOP_FRAME_LOOP, max_insns=FRAME_MAX_INSNS,
                 hw_seed={HW_SHIFTER_SYNC: SHIFTER_SYNC_50HZ}, note=f"{window} frame {frame}")


@pytest.mark.parametrize("index", range(FRAME_WINDOW_LENGTH))
def test_a_whole_frame_of_a_stage_that_has_just_started(frame_worlds, index):
    """One pass of the frame loop, four frames running, over the stage's opening.

    THIS IS THE INTEGRATION TEST OF THE WHOLE PORT: forty-five verified cores called in the
    original's order, and the diff covers everything they touch — the four screens in the ring, the
    223 display records, the entity arena, the HUD's digits, the sound module's state and the PSG's
    register stream.
    """
    _frame_case(frame_worlds, "quiet", index)


@pytest.mark.parametrize("index", range(FRAME_WINDOW_LENGTH))
def test_a_whole_frame_with_enemies_alive_and_shots_in_the_air(frame_worlds, index):
    """The same pass over a world the original scrolled 178 frames into.

    What it adds is the arms an opening frame never takes: live entities to move, publish and test
    for collisions, the player's own bullets in flight, and a spawn script that fires.
    """
    _frame_case(frame_worlds, "busy", index)


@pytest.mark.parametrize("index", range(FRAME_WINDOW_LENGTH))
def test_a_whole_frame_with_the_smart_bomb_going_off(frame_worlds, index):
    """...and over the frames the BOMB CHAIN's active arms run in, which no other window reaches.

    Four of the forty-five return at their first guard on every quiet and busy frame — the bomb is
    neither falling nor exploding — so `bomb_fall_step`'s path walk, `bomb_publish`'s record,
    `bomb_blast_step`'s object-list wipe, its explosion effect and its four offset points, and
    `bomb_blast_vs_entities`' sweep are all outside those windows. This is also the one window in
    which `FRAME_BLAST_SCRATCH_D0` is CONSUMED rather than merely carried: on a frame with nothing
    exploding, `bomb_blast_step` returns before it indexes anything with it.
    """
    _frame_case(frame_worlds, "blast", index)


@pytest.mark.parametrize("window", tuple(FRAME_WINDOWS))
def test_a_frame_entered_the_way_a_stage_restart_leaves_one(frame_worlds, window):
    """`level_just_started` SET on entry, which is the state `restart_level_at_checkpoint` leaves.

    The loop's own store is the last thing it does — `clr.w $17696` @ 0x15810 — and it is invisible
    on every ordinary frame, because the flag is already zero and clearing it changes nothing. So
    the mutation that drops it SURVIVED the whole battery until this case existed (measured
    2026-09-07). It also drives the one arm `read_player_input` gates on the flag: with it set, the
    pause and abort keys are skipped for that frame.
    """
    pokes = dict(frame_worlds[window][0])
    pokes.update(_frame_input_pokes(FRAME_WINDOWS[window]))
    pokes[A_level_just_started] = b"\xff\xff"
    abi.run_case(ENTRY_FRAME_LOOP, lambda lib, buf: lib.g_frame_loop_once(buf), pokes=pokes,
                 stop_pc=STOP_FRAME_LOOP, max_insns=FRAME_MAX_INSNS,
                 hw_seed={HW_SHIFTER_SYNC: SHIFTER_SYNC_50HZ},
                 note=f"{window} entered with level_just_started set")


def test_the_busy_window_really_has_a_live_world(post_load_image, frame_worlds):
    """A window that quietly held nothing would make the four cases above duplicates.

    BOTH CLAIMS THE DOCSTRING MAKES ARE ASSERTED, and both floors are the measurement rather than a
    round number: level 1's first formation is a PAIR, and the plane's fire every fourth frame keeps
    one or two bullets in the air over the window (2 live slots and 1-2 bullets at frames 178..181,
    measured 2026-09-07). A floor of "more than nothing" would let the window drift to a single
    straggler and still call itself busy.
    """
    image = _staged_image(post_load_image, frame_worlds["busy"][0])
    live = sum(1 for slot in range(conftest.ENTITY_SLOTS)
               if image[A_entity_arena + slot * conftest.ENTITY_STRIDE + conftest.ENTITY_ACTIVE:
                        A_entity_arena + slot * conftest.ENTITY_STRIDE
                        + conftest.ENTITY_ACTIVE + 2] != b"\0\0")
    in_flight = sum(1 for bullet in range(PLAYER_SHOT_SLOTS * PLAYER_SHOT_BULLETS)
                    if image[A_player_bullet_arena + bullet * PLAYER_BULLET_BYTES
                             + PLAYER_BULLET_STATE:
                             A_player_bullet_arena + bullet * PLAYER_BULLET_BYTES
                             + PLAYER_BULLET_STATE + 2] != b"\0\0")
    assert live >= FRAME_BUSY_MIN_LIVE_SLOTS, (
        f"the busy window's first frame has {live} live entity slots, not "
        f"{FRAME_BUSY_MIN_LIVE_SLOTS} — move FRAME_WINDOWS['busy'] forward until the level's own "
        f"spawn script has put a whole formation in the arena")
    assert in_flight >= FRAME_BUSY_MIN_BULLETS, (
        f"the busy window's first frame has {in_flight} bullets in flight, not "
        f"{FRAME_BUSY_MIN_BULLETS} — the joystick script's fire is not reaching the arena")


def test_the_blast_window_really_has_a_blast_going_off(post_load_image, frame_worlds):
    """...and the same positive control for the bomb window, on EVERY frame of it.

    A window that had drifted one bomb-cycle either way would hold a bomb still falling, or nothing
    at all, and the four cases above would be the busy ones again — green, and about a machine in
    which four of the forty-five calls return at their first guard. `bomb_exploding` is the flag
    those four guard on, and `blast_step` says where in the blast's fifteen steps each frame is.
    """
    for index in range(FRAME_WINDOW_LENGTH):
        frame = FRAME_WINDOWS["blast"] + index
        image = _staged_image(post_load_image, frame_worlds["blast"][index])
        exploding = int.from_bytes(bytes(image[A_bomb_exploding:A_bomb_exploding + 2]), "big")
        step = int.from_bytes(bytes(image[A_blast_step:A_blast_step + 2]), "big")
        assert exploding != 0, (
            f"frame {frame} enters with `bomb_exploding` clear, so `bomb_blast_step` and the three "
            f"calls around it return at their first guard — move FRAME_WINDOWS['blast'] to a frame "
            f"the bomb held from {BOMB_HELD_FROM} is really going off in")
        assert FRAME_BLAST_MIN_STEP <= step <= FRAME_BLAST_MAX_STEP, (
            f"frame {frame} is at blast step {step:#x}, outside the blast's own "
            f"{FRAME_BLAST_MIN_STEP:#x}..{FRAME_BLAST_MAX_STEP:#x}")


def test_the_frame_loops_register_carries_are_what_the_original_leaves(post_load_image,
                                                                      frame_worlds):
    """`include/init.h`'s three FRAME_* constants, MEASURED at the two call sites that read them.

    `bomb_blast_step` indexes its offset table with the HIGH WORD of a D0 its own code never sets,
    and `player_publish` passes D1 and D2 to the game-over banner's text script — so all three are
    inputs the loop supplies by accident, and a reconstruction has to supply the same ones. The
    oracle is stopped AT each call site and its registers read, over every staged frame, so a change
    in any predecessor fails here rather than as an unexplained byte in a frame diff.

    THE BLAST WINDOW IS WHY THE D0 FIGURE IS WORTH MEASURING. Its LOW word is not zero on any staged
    frame — 0x9d and 0xd3..0xd5 are what the predecessors leave there — and it is the high word
    alone that reaches `A_blast_offset_tbl`, because `bomb_blast_step`'s own `move.w $176ec,d0`
    overwrites the low one before the `adda.l`. Measured 2026-09-07: the high word is 0 on all
    twelve staged frames, the four in which the blast really consumes it included.
    """
    for window, first in FRAME_WINDOWS.items():
        for index, pokes in enumerate(frame_worlds[window]):
            image = _staged_image(post_load_image, pokes)
            for address, data in _frame_input_pokes(first + index).items():
                image[address:address + len(data)] = data
            _final, _writes, at_publish = emu.run(bytearray(image), ENTRY_FRAME_LOOP,
                                                  stop_pc=STOP_FRAME_AT_PLAYER_PUBLISH,
                                                  max_insns=FRAME_MAX_INSNS)
            _final, _writes, at_blast = emu.run(bytearray(image), ENTRY_FRAME_LOOP,
                                                stop_pc=STOP_FRAME_AT_BOMB_BLAST_STEP,
                                                max_insns=FRAME_MAX_INSNS)
            note = f"{window} frame {first + index}"
            assert at_publish["d1"] == FRAME_TEXT_X_D1, f"{note}: D1"
            assert at_publish["d2"] == FRAME_TEXT_Y_D2, f"{note}: D2"
            assert at_blast["d0"] >> 16 == FRAME_BLAST_SCRATCH_D0 >> 16, f"{note}: D0 high"


def _frame_loop_call_targets():
    """The target of every `bsr.w` between the loop's top and its `bra`, off the loaded image.

    The displacement is SIGNED — every one of these calls goes backwards — which is why it is
    sign-extended here rather than added raw: unsigned, all forty-five targets land past the end of
    the program and every name lookup below would miss in the same way.
    """
    targets, address = [], ENTRY_FRAME_LOOP
    while address < STOP_FRAME_LOOP - 6:
        opcode = int.from_bytes(bytes(harness.BASE_IMAGE[address:address + 2]), "big")
        if opcode != BSR_W_OPCODE:
            break
        displacement = int.from_bytes(bytes(harness.BASE_IMAGE[address + 2:address + 4]),
                                      "big", signed=True)
        targets.append(address + 2 + displacement)
        address += 4
    assert address == STOP_FRAME_LOOP - 6, (
        f"the calls end at {address:#x}; the `clr.w level_just_started` should follow them")
    return targets


def test_the_frame_loop_makes_the_forty_five_calls_this_file_makes():
    """Every `bsr.w` between the loop's top and its `bra`, read out of the loaded image."""
    targets = _frame_loop_call_targets()
    assert len(targets) == FRAME_LOOP_CALLS, (
        f"the loop makes {len(targets)} `bsr.w` calls, not FRAME_LOOP_CALLS ({FRAME_LOOP_CALLS})")
    assert len(set(targets)) == FRAME_LOOP_CALLS, "a routine is called twice in one pass"


def test_frame_loop_once_calls_those_routines_in_that_order():
    """`src/init.c`'s call list against the ORIGINAL's, name by name and in order.

    THE BYTE DIFF CANNOT DO THIS. Two of the forty-five calls are invisible to every frame a case
    can stage — `level2_scenery_effect_gate` returns at once outside level 2, and a dropped
    `count_game_frame` would show — and any two neighbours that happen to commute on a given frame
    are interchangeable to it as well. Both mutations SURVIVED the whole battery until this case
    existed (measured 2026-09-07). So the order is pinned where it is written: the C's calls are
    read out of `src/init.c` and matched against `../names.txt`'s name for each `bsr` target.

    It is a SOURCE pin and not a behavioural one, and it is worth exactly what it says — that the
    reconstruction names the same routines in the same order. That the routines themselves are right
    is the other forty-five sections of STATUS.md.
    """
    named = {}
    for line in (conftest.REC.parent / "names.txt").read_text().splitlines():
        match = re.match(r"fn 0x([0-9a-f]+)\s+(\S+)", line)
        if match:
            named[int(match.group(1), 16)] = match.group(2)

    expected = [named.get(target) for target in _frame_loop_call_targets()]
    assert all(expected), (
        "../names.txt has no `fn` line for "
        + ", ".join(f"{t:#x}" for t, n in zip(_frame_loop_call_targets(), expected) if not n))

    body = (conftest.REC / "src" / "init.c").read_text()
    body = body[body.index("void frame_loop_once"):]
    body = body[:body.index("\n}\n")]
    called = re.findall(r"^    ([a-z_0-9]+)\(image[,)]", body, re.M)
    assert called == expected, (
        "src/init.c's frame_loop_once calls\n  " + " ".join(called)
        + "\nbut the original's forty-five `bsr.w`s name\n  " + " ".join(expected))


# =================================================================================================
# main @ 0x15750 — SLICE [0x15750, 0x15758), and the whole boot behind it
# =================================================================================================
#
# THE ROW THIS CLOSES WAS TWO MODEL BLOCKERS, and both are gone. (1) `init_load_assets` opens EIGHT
# files and the model stages files in ONE window, which at the kit's default is too small for them —
# so the routine could not even be REPLAYED in one run, let alone diffed. `project.toml`'s `fs_base`
# moves the window down; that comment carries the arithmetic, and
# `test_image_model.py::test_the_staged_file_window_holds_the_whole_boot` measures it.
# (2) `init_new_game` never returns: it ends `bra.w enter_title`, so the third `bsr` @ 0x15758 is
# reached only when `title_attract_loop`'s own `rts` comes back to it. That is still true and still
# inexpressible in C — so `main_boot` is the first two calls, and the case below composes the rest.

MAIN_BOOT_MAX_INSNS = 1_000_000
# The whole boot draws the title screen's 108-frame prescroll and then the attract frames the fire
# button interrupts, so it is the most expensive run in the suite by an order of magnitude.
WHOLE_BOOT_MAX_INSNS = 30_000_000
ENTER_TITLE_ATTRACT = 1            # `include/frontend.h`'s enum: level 0's assets already loaded
WHOLE_BOOT_FIRE_AT = 3             # the poll the button comes down on: two attract frames first
WHOLE_BOOT_FRAMES = WHOLE_BOOT_FIRE_AT - 1
# The seed the eight staged files' content is drawn from — `main`'s own entry, so that a reader can
# see where the bytes came from and no other battery can draw the same ones by accident.
BOOT_STAGE_SEED = 0x15750


def _stage(staged):
    pokes, _handles = harness.stage_files(staged)
    return pokes


def _boot_pokes_seeded(post_load_image):
    """All eight of `init_load_assets`' files staged with bytes of this test's OWN choosing, so that
    a reconstruction which opened nothing could not agree over a fixture that already holds the real
    ones. `conftest.seeded_load` is where the choice between this and its twin below is argued."""
    return _stage([conftest.seeded_load(post_load_image, record, RECORD_DISC_NAMES[record],
                                        BOOT_STAGE_SEED + index)
                   for index, record in enumerate(ALL_RECORDS)])


def _boot_pokes_real(post_load_image):
    """...and the same eight with their REAL bytes, which the whole-boot case needs: the title
    screen renders terrain out of `A\\LEVEL1.MAP` and the tile banks, and a map header of noise
    would send the scroller's own cursor arithmetic somewhere the game never goes."""
    return _stage([conftest.staged_load(post_load_image, record, RECORD_DISC_NAMES[record])
                   for record in ALL_RECORDS])


def test_main_boots_the_program(post_load_image):
    """[0x15750, 0x15758): `bsr init_load_assets` and `bsr init_new_game`, diffed where the second
    of them branches into the title screen instead of returning.

    Every file is staged with content of this test's own choosing, so both the eight `Fread`s and
    the sprite directory's relocation are visible over a fixture that already holds the real ones.
    """
    abi.run_case(ENTRY_MAIN, lambda lib, buf: lib.g_main_boot(buf),
                 pokes=_boot_pokes_seeded(post_load_image),
                 stop_pc=ENTRY_ENTER_TITLE, max_insns=MAIN_BOOT_MAX_INSNS)


def test_the_whole_boot_reaches_the_stage_start_the_fire_button_asks_for(post_load_image):
    """THE PROGRAM FROM ITS FIRST INSTRUCTION TO THE FIRST STAGE, in one differential.

    `main` @ 0x15750 loads the assets, resets the game, branches into `enter_title`, prescrolls the
    attract screen, draws two attract frames, takes the fire button and `rts`es — back to the third
    `bsr` @ 0x15758, which is where this stops. Nothing in the case says where one routine ends and
    the next begins: the oracle runs the original's own branches and the candidate runs five cores
    in the order the exit codes put them in.

    IT IS THE ONLY CASE THAT CROSSES THE STACK UNWIND. `init_new_game` never returns and
    `title_attract_loop`'s `rts` is what eventually comes back, so no C function can hold this
    path; the composition is here, in the test, where the seam is visible.

    The schedule is its own positive control — the kit sinks a run in which a scheduled store never
    came due, so "the button comes down at the THIRD arrival at the poll, and the VBL counter
    reaches its budget once per attract frame" is asserted by the case existing rather than by a
    counter nobody reads. One fire store and two VBL stores, not five arrivals.
    The files are staged with their REAL bytes, because this run RENDERS from them.
    """
    def candidate(lib, buf):
        lib.g_main_boot(buf)
        assert lib.g_enter_title(buf) == ENTER_TITLE_ATTRACT
        lib.g_title_attract_loop(buf)

    pokes = _boot_pokes_real(post_load_image)
    pokes[A_joy1_state] = b"\x00"
    pokes[A_vbl_tick] = (0).to_bytes(4, "big")
    abi.run_case(ENTRY_MAIN, candidate, pokes=pokes, stop_pc=STOP_MAIN_THIRD_CALL,
                 max_insns=WHOLE_BOOT_MAX_INSNS,
                 schedule=conftest.attract_schedule(WHOLE_BOOT_FIRE_AT, WHOLE_BOOT_FRAMES),
                 note="main -> title -> fire -> the third init")


# =================================================================================================
# the addresses and constants this battery names
# =================================================================================================

MIRROR_HEADER = "include/init.h"
MIRRORS = (
    "A_load_file_handle", "A_load_dest", "A_load_len", "A_disc_probe_result",
    "A_palette_title", "A_palette_game", "A_palette_black",
    "BOOT_SETSCREEN_LOG", "BOOT_SETSCREEN_PHYS", "BOOT_RESOLUTION_LOW",
    "VECTOR_VBL", "FN_VBL_HANDLER", "A_vbl_chain_vector",
    "IKBD_CMD_JOYSTICK_EVENT_REPORTING", "KBDVBASE_JOYVEC", "A_saved_tos_joyvec",
    "FN_TOS_JOYVEC_HANDLER",
    "NEO_PALETTE_OFFSET", "TITLE_COPY_OFFSET", "TITLE_COPY_LONGS", "A_level0_assets_loaded",
    "GAME_OVER_DELAY_FRAMES", "NAME_ENTRY_TIMEOUT", "NEW_GAME_LIVES_INDEX",
    ("CONST_WORD_ZERO", "include/hud.h", "CONST_WORD_ZERO"),
    "STAGE_SCROLL_POS_SEED", "A_keep_enemy_fire_inhibit",
    "A_unread_word_176a2", "A_unread_word_176a8",
    "FRAME_LOOP_TOP", "FRAME_LOOP_CALLS",
    "FRAME_BLAST_SCRATCH_D0", "FRAME_TEXT_X_D1", "FRAME_TEXT_Y_D2",
    ("A_stack_top", "include/globals.h", "A_stack_top"),
    ("A_saved_super_ssp", "include/globals.h", "A_saved_super_ssp"),
    ("A_entity_arena", "include/globals.h", "A_entity_arena"),
    ("A_player_bullet_arena", "include/weapons.h", "A_player_bullet_arena"),
    ("PLAYER_SHOT_SLOTS", "include/weapons.h", "PLAYER_SHOT_SLOTS"),
    ("PLAYER_SHOT_BULLETS", "include/weapons.h", "PLAYER_SHOT_BULLETS"),
    ("PLAYER_BULLET_BYTES", "include/weapons.h", "PLAYER_BULLET_BYTES"),
    ("PLAYER_BULLET_STATE", "include/weapons.h", "PLAYER_BULLET_STATE"),
    ("FS_PROGRAM_END", "include/globals.h", "FS_PROGRAM_END"),
    ("A_sprite_bank", "include/globals.h", "A_sprite_bank"),
    ("A_max_weapon_flag", "include/hud.h", "A_max_weapon_flag"),
    ("A_cheat_used_flag", "include/hud.h", "A_cheat_used_flag"),
    ("A_level_number", "include/player.h", "A_level_number"),
    ("A_level_just_started", "include/player.h", "A_level_just_started"),
    ("A_lives", "include/player.h", "A_lives"),
    ("A_enemy_fire_inhibit", "include/player.h", "A_enemy_fire_inhibit"),
    ("A_joy1_state", "include/irq.h", "A_joy1_state"),
    ("A_vbl_tick", "include/irq.h", "A_vbl_tick"),
    ("A_scroll_pos", "include/scroll.h", "A_scroll_pos"),
    ("A_const_words_0123", "include/hud.h", "A_const_words_0123"),
    ("A_weapon_level", "include/weapons.h", "A_weapon_level"),
    ("A_spawn_script_cursor", "include/weapons.h", "A_spawn_script_cursor"),
    ("A_item_bomb_spawned", "include/weapons.h", "A_item_bomb_spawned"),
    ("A_bomb_falling", "include/weapons.h", "A_bomb_falling"),
    ("A_bomb_exploding", "include/weapons.h", "A_bomb_exploding"),
    ("A_bomb_path_cursor", "include/weapons.h", "A_bomb_path_cursor"),
    ("A_key_last_scancode", "include/irq.h", "A_key_last_scancode"),
    ("A_key_bits", "include/irq.h", "A_key_bits"),
    ("A_blast_step", "include/weapons.h", "A_blast_step"),
    ("A_joy0_state", "include/irq.h", "A_joy0_state"),
    ("A_player_script_fire_enable", "include/player.h", "A_player_script_fire_enable"),
    ("A_landing_bomb_cash_timer", "include/player.h", "A_landing_bomb_cash_timer"),
    ("A_death_anim_cursor", "include/player.h", "A_death_anim_cursor"),
    ("A_game_over_flag", "include/player.h", "A_game_over_flag"),
    ("A_player_script_timer", "include/player.h", "A_player_script_timer"),
    ("A_landing_shadow_timer", "include/player.h", "A_landing_shadow_timer"),
    ("A_takeoff_shadow_timer", "include/player.h", "A_takeoff_shadow_timer"),
    ("A_shadow_offset", "include/player.h", "A_shadow_offset"),
    ("A_level_distance", "include/scroll.h", "A_level_distance"),
    ("A_scroll_fine", "include/scroll.h", "A_scroll_fine"),
    ("A_music_suspend_flag", "include/sound.h", "A_music_suspend_flag"),
    ("A_bonus_life_awarded_0", "include/hud.h", "A_bonus_life_awarded_0"),
    ("BONUS_LIFE_THRESHOLDS", "include/hud.h", "BONUS_LIFE_THRESHOLDS"),
    ("BONUS_LIFE_FLAG_BYTES", "include/hud.h", "BONUS_LIFE_FLAG_BYTES"),
    ("A_name_entry_timeout", "include/hud.h", "A_name_entry_timeout"),
    ("A_hiscore_beaten", "include/hud.h", "A_hiscore_beaten"),
    ("A_name_entry_first_pass", "include/frontend.h", "A_name_entry_first_pass"),
    ("A_item_pickup_pending", "include/entity.h", "A_item_pickup_pending"),
    ("A_game_over_delay", "include/player.h", "A_game_over_delay"),
    ("A_level_loop_flag_1", "include/player.h", "A_level_loop_flag_1"),
    ("A_level_loop_flag_2", "include/player.h", "A_level_loop_flag_2"),
    ("A_level_loop_flag_3", "include/player.h", "A_level_loop_flag_3"),
    ("SHIFTER_SYNC_50HZ", "include/sound.h", "SHIFTER_SYNC_50HZ"),
    ("JOY_FIRE_BIT", "include/hud.h", "JOY_FIRE_BIT"),
)

# Eight bytes or more each: this program's routines nearly all open `movem.l #$fffe,-(a7)` or a
# `lea` of an absolute long, so a shorter pin would match dozens of them. The three palette wrappers
# are identical for four bytes and separate only at the table address in their fifth.
ENTRY_PROLOGUES = {
    # bra.w $14bee, then the first four bytes of the banner at 0x10004 ("PROG")
    "ENTRY_ENTRY_STUB": "60004bec50524f47",
    # movea.l #$19094,a7 / clr.l -(a7)
    "ENTRY_BOOT_INIT": "2e7c0001909442a7",
    # movem.l #$fffe,-(a7) / move.l (a0)+,$17776
    "ENTRY_LOAD_FILE": "48e7fffe23d800017776",
    # movem.l #$fffe,-(a7) / lea $1631a,a0 -- its OWN record, not the caller's
    "ENTRY_PROBE_DISC": "48e7fffe41f90001631a",
    "ENTRY_SET_PALETTE_BLACK": "48e7fffe2f3c000162b4",
    "ENTRY_SET_PALETTE_GAME": "48e7fffe2f3c00016294",
    "ENTRY_SET_PALETTE_TITLE": "48e7fffe2f3c00016274",
    # bsr.s $111d6 / movea.l #$162ee,a0
    "ENTRY_INIT_LOAD_ASSETS_TITLE": "61c2207c000162ee",
    # st $176ea / movea.l #$1631a,a0
    "ENTRY_INIT_LOAD_ASSETS_SPRITES": "50f9000176ea207c0001",
    # move.w $176ac,$176c6
    "ENTRY_INIT_NEW_GAME": "33f9000176ac000176c6",
    # clr.b $17781 / clr.b $1777f
    "ENTRY_INIT_STAGE_STATE": "42390001778142390001",
    # movem.l #$fffe,-(a7) / lea $59984,a0
    "ENTRY_CLEAR_ACTOR_ARRAYS": "48e7fffe41f900059984",
    # bsr.w $11212 / bsr.w $112fa -- init_load_assets and init_new_game, main's own first two
    "ENTRY_MAIN": "6100bac06100bba46100",
    # st $17698 / bsr.w $111a6 -- the "just entered" flag, then set_palette_black
    "ENTRY_ENTER_TITLE": "50f90001769861000e90",
    # bsr.w $11654 / bsr.w $119fc -- the frame loop's first two calls
    "ENTRY_FRAME_LOOP": "6100bef66100c29a6100",
    # subi.l #$1f900,d0 / movea.l a7,a2 -- the ring arithmetic, past boot_init's Physbase
    "ENTRY_RING_ARITHMETIC": "04800001f900548f",
}

STOP_PROLOGUES = {
    # movea.l #$16304,a0 / bsr.w load_file -- the sound module's load, after the ninth ring store
    "STOP_RING_ARITHMETIC": "207c000163046100",
    # bra.w $15750 / movem.w (a5)+,#$0027 -- the first word of tile_blit_overlay_masked after it
    "STOP_BOOT_INIT": "60000a484c9d0027",
    # bra.s $112ac, then the first six bytes of the patched-out disc-prompt block it branches over
    "STOP_INIT_LOAD_ASSETS_TITLE": "602cf97a33fc0777",
    # bra.w $1030e / rts -- init_new_game falls into enter_title, so the `rts` is unreachable
    "STOP_INIT_NEW_GAME": "6000ef784e75",
    # beq.w $12cb6 / bra.w $12cc8 -- the difficulty dispatch the slice stops in front of
    "STOP_INIT_STAGE_DISPATCH": "6700187c6000188a",
    # bsr.w $1139a / bsr.w $11654 -- main's THIRD call, which only the attract loop's `rts` reaches
    "STOP_MAIN_THIRD_CALL": "6100bc406100bef66100",
    # bra.w $1575c / lea $38928,a1 -- tile_blit_unreferenced, the dead routine after the loop
    "STOP_FRAME_LOOP": "6000ff4443f90003",
    # bsr.w $13c96 / bsr.w $13baa -- the `bsr player_publish` the register probe stops in front of
    "STOP_FRAME_AT_PLAYER_PUBLISH": "6100e5206100e430",
    # bsr.w $10c8c / bsr.w $10d20 -- and the `bsr bomb_blast_step`
    "STOP_FRAME_AT_BOMB_BLAST_STEP": "6100b4b66100b546",
}
