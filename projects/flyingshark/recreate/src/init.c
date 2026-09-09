/* src/init.c — Flying Shark's boot chain, its file loader, the palette wrappers, the two resets and
 * the frame loop.
 *
 * `include/init.h` carries the addresses and the argument for each slice's span. What is worth
 * saying once, here, is what the TOS MODEL supplies and what it cannot:
 *
 *   * XBIOS `Physbase` and `Kbdvbase` have no `os_*` door in the kit. The oracle answers them with
 *     `OS_SCREEN_BASE` and `OS_KBDVBASE`, and this file asks for them through `include/init.h`'s
 *     `fs_physbase()` and `fs_kbdvbase()` — one seam per call for an on-target build to shadow,
 *     rather than a constant spelt in the middle of a routine. The gap is a row in STATUS.md's
 *     "Follow-ups the kit should absorb".
 *   * `Setpalette`, `Setscreen` and `Vsync` touch no image byte; they are ORDERED EVENTS the
 *     harness compares, which is what separates a reconstruction that installs a palette from one
 *     that silently drops it (kit `include/os.h`, "the XBIOS VIDEO AND COLOUR GROUP").
 *   * `move.w #$2700,sr` / `move.w #$2300,sr` @ 0x14ca8 and 0x14cce mask and unmask the interrupts
 *     around the two vector installs. The model has no interrupt to mask and the oracle runs
 *     supervisor throughout, so there is nothing for a reconstruction to say: the pair is left out
 *     of the C deliberately rather than by oversight.
 *   * `movea.l #$19094,a7` @ 0x14bee moves the program onto its OWN supervisor stack. The candidate
 *     is C and has no machine stack to move, so the ORACLE's trap frames land in the game's stack
 *     band and the candidate's do not — `test_init.py` excludes exactly the band the oracle
 *     descended into, and says how it measures it.
 */
#include <stdint.h>

#include "machine.h"
#include "os.h"

#include "common.h"   /* `const_word` and `copy_longs`, the two idioms this file shares */
#include "entity.h"
#include "frontend.h"
#include "globals.h"
#include "hud.h"
#include "init.h"
#include "irq.h"
#include "player.h"
#include "scroll.h"
#include "sound.h"
#include "sprite.h"
#include "weapons.h"

/* ================================================================================================
 * load_file @ 0x10bfa and probe_disc @ 0x10c4c
 * ============================================================================================= */

/* Copy a record's destination and length into the loader's two scratch longwords, and answer where
 * its DOS path starts. Both routines below open the file this way, and the copy is not incidental:
 * `load_file`'s `Fread` reads its arguments back OUT of those globals rather than out of registers,
 * so a reconstruction that kept them in locals would leave two longwords unwritten. */
static uint32_t stage_file_record(uint8_t *image, uint32_t record) {
    wr32(image + A_load_dest, be32(image + addr_add(record, FILE_REC_DEST)));
    wr32(image + A_load_len, be32(image + addr_add(record, FILE_REC_LEN)));
    return addr_add(record, FILE_REC_NAME);
}

/* load_file @ 0x10bfa — Fopen / Fread / Fclose one asset record, with NO ERROR CHECK AT ALL.
 *
 * A failed `Fopen` yields a negative handle, the `Fread` that follows simply fails, and the routine
 * returns as if it had loaded the file. That is the original's behaviour and it is reproduced: the
 * disc-presence handshake is `probe_disc`'s separate job. The handle reaches `Fclose` through the
 * WORD at `A_load_file_handle`, so a handle above 0x7fff would be closed as a negative one — which
 * the model's handles (6 and up) never are. */
void load_file(uint8_t *image, uint32_t record) {
    uint32_t name = stage_file_record(image, record);
    int32_t handle = os_fopen(image, name);

    wr16(image + A_load_file_handle, (uint16_t)handle);
    os_fread(image, (uint16_t)handle, be32(image + A_load_len), be32(image + A_load_dest));
    os_fclose(image, be16(image + A_load_file_handle));
}

/* probe_disc @ 0x10c4c — is disc A in the drive?
 *
 * IT IGNORES ITS CALLER'S A0: the record is always `A_file_rec_sprites_cru`, loaded by its own
 * `lea` @ 0x10c50, so the probe is "can A\SPRITES.cru be opened?" and nothing else. The answer is
 * the WHOLE longword `Fopen` returned, which is why callers test it with `bpl`/`bmi`.
 *
 * THE NEGATIVE ARM CANNOT BE RUN OFF TARGET. An `Fopen` of a name the harness has not staged is a
 * REFUSAL on both sides — it sinks the oracle's whole run and tallies against the candidate — so a
 * case for "the disc is out" is a case the model throws away rather than one it answers -1 to. The
 * guard is reconstructed anyway, because on target it is what stops a `Fclose` of a bad handle;
 * STATUS.md's "Unpinned on target" carries it. */
void probe_disc(uint8_t *image) {
    uint32_t name = stage_file_record(image, A_file_rec_sprites_cru);
    int32_t handle = os_fopen(image, name);

    wr32(image + A_disc_probe_result, (uint32_t)handle);
    if (handle < 0)
        return;
    os_fclose(image, (uint16_t)handle);
}

/* ================================================================================================
 * The three palette wrappers @ 0x111a6 / 0x111be / 0x111d6
 * ============================================================================================= */
void set_palette_black(uint8_t *image) { (void)image; os_setpalette(A_palette_black); }
void set_palette_game(uint8_t *image)  { (void)image; os_setpalette(A_palette_game); }
void set_palette_title(uint8_t *image) { (void)image; os_setpalette(A_palette_title); }

/* ================================================================================================
 * boot_init @ 0x14bee — SLICE [0x14bee, 0x14d06)
 * ============================================================================================= */

/* The nine screen pointers, @ 0x14c26..0x14c98. The arithmetic is `include/globals.h`'s constants,
 * one per instruction, and the two READ-BACKS are the original's: `screen_ring_base_raw` is stored
 * and immediately re-read @ 0x14c34, and every ring slot but the first re-reads
 * `screen_ring_base` rather than keeping it in a register.
 *
 * `README.md`, "Where the screen ring goes", is why the values this leaves are OUTSIDE the image:
 * the model's Physbase is 0x8000 and the first thing done to it is a subtraction that underflows.
 * The stores themselves land in the image and are diffed; only the addresses they hold are unusable,
 * which is what `test/conftest.py` re-places afterwards.
 *
 * PHYSBASE IS A PARAMETER AND NOT `fs_physbase()` READ HERE, because the ROUNDING is only
 * observable at a Physbase the model cannot answer with. Every Physbase the fixture uses is already
 * 256-aligned, so dropping the mask changes nothing and survives the whole battery; entering the
 * ORIGINAL at 0x14c26 with d0 in the case's hands is what drives it, and that entry is
 * `g_derive_screen_ring` below (`test_init.py`, the unaligned-Physbase case). */
void derive_screen_ring(uint8_t *image, uint32_t physbase) {
    uint32_t base, cursor;

    wr32(image + A_screen_ring_base_raw, addr_sub(physbase, SCREEN_RING_BYTES));
    base = (be32(image + A_screen_ring_base_raw) + SCREEN_RING_ALIGN)
           & ~(uint32_t)(SCREEN_RING_ALIGN - 1);       /* `addi.l #$100,d0 / clr.b d0`: STRICTLY up */
    wr32(image + A_screen_ring_base, base);

    cursor = addr_add(base, SCREEN_RING_0_OFF);        /* the one slot that does NOT re-read */
    wr32(image + A_screen_ring, cursor);
    wr32(image + A_screen_prev1, cursor);

    cursor = addr_add(be32(image + A_screen_ring_base), SCREEN_RING_1_OFF);
    wr32(image + A_screen_ring_1, cursor);
    wr32(image + A_screen_draw, cursor);

    cursor = addr_add(be32(image + A_screen_ring_base), SCREEN_RING_2_OFF);
    wr32(image + A_screen_ring_2, cursor);

    cursor = addr_add(be32(image + A_screen_ring_base), SCREEN_RING_3_OFF);
    wr32(image + A_screen_prev2, cursor);
    wr32(image + A_screen_ring_3, cursor);
}

void boot_init(uint8_t *image) {
    uint32_t old_stack_pointer = 0;
    uint32_t joyvec_slot;

    os_super(OS_SUPER_ENTER, &old_stack_pointer);
    wr32(image + A_saved_super_ssp, old_stack_pointer);   /* stored @ 0x14bfe and never read back */

    /* Two bases the next lines throw away; the RESOLUTION is what this call is for (include/init.h).
     * The model's `os_setscreen` ledgers the LOGICAL base alone, so only the first argument here is
     * differentially visible — STATUS.md's "Unpinned on target" carries the other two. */
    os_setscreen(BOOT_SETSCREEN_LOG, BOOT_SETSCREEN_PHYS, BOOT_RESOLUTION_LOW);
    derive_screen_ring(image, fs_physbase());             /* XBIOS Physbase, as the model answers it */

    load_file(image, A_file_rec_module_bak);               /* the sound driver, and the only file */

    /* The two vectors, installed with interrupts masked (the `move.w #$2700,sr` pair the model has
     * nothing to say about). The chain operand goes in FIRST, so `vbl_handler` has somewhere to
     * jump to the moment $70 names it. */
    wr32(image + A_vbl_chain_vector, be32(image + VECTOR_VBL));
    wr32(image + VECTOR_VBL, FN_VBL_HANDLER);
    wr32(image + VECTOR_ACIA, FN_ACIA_IKBD_ISR);

    /* IKBD command $14: report joystick events. This is what makes the ACIA send the $FE/$FF
     * prefixed packets `acia_ikbd_isr` decodes, and it is an ordered OS EVENT rather than a store. */
    os_ikbd_out(IKBD_CMD_JOYSTICK_EVENT_REPORTING);

    /* ...and TOS's own joystick callback, replaced by one the ACIA handler has already made
     * unreachable. The saved vector at `A_saved_tos_joyvec` is written and never read. */
    joyvec_slot = addr_add(fs_kbdvbase(), KBDVBASE_JOYVEC);
    wr32(image + A_saved_tos_joyvec, be32(image + joyvec_slot));
    wr32(image + joyvec_slot, FN_TOS_JOYVEC_HANDLER);

    wr16(image + A_cheat_used_flag, 0);                    /* `clr.w $176d4` @ 0x14d00 */
}

/* entry_stub @ 0x10000 — the .PRG's entry point, which is `bra.w boot_init` and nothing else.
 *
 * The 44 bytes after it at 0x10004 are the plaintext banner "PROGRAMMING BY PRIME SOFTWARE & IMAGES
 * DESIGN", which is data sitting in the middle of TEXT. */
void entry_stub(uint8_t *image) { boot_init(image); }

/* ================================================================================================
 * init_load_assets @ 0x11212 — the two slices `include/init.h` argues for
 * ============================================================================================= */

/* [0x11212, 0x1127e): the title picture.
 *
 * A\FLY_SHK.NEO is loaded to `A_sprite_bank` — the sprite bank's own address, which the second
 * slice then overwrites with A\SPRITES.cru — and the picture is copied from there to
 * `Physbase - 0x80`. The offset is the NEOchrome header's own length, so the header lands just
 * below the screen and the 32,000 pixel bytes land exactly on it.
 *
 * THE PALETTE IS INSTALLED TWICE, from the same address, with a `Physbase` and a `Setscreen`
 * between them. Both calls are made and both are in the event ledger. */
void init_load_assets_title(uint8_t *image) {
    uint32_t physbase;

    set_palette_title(image);
    load_file(image, A_file_rec_flyshk_neo);
    os_setpalette(addr_add(A_sprite_bank, NEO_PALETTE_OFFSET));

    physbase = fs_physbase();                        /* saved on the stack @ 0x11234, popped @ 0x11266 */
    os_setscreen(physbase, physbase, BOOT_RESOLUTION_LOW);
    os_setpalette(addr_add(A_sprite_bank, NEO_PALETTE_OFFSET));

    copy_longs(image, A_sprite_bank, addr_sub(physbase, TITLE_COPY_OFFSET), TITLE_COPY_LONGS);
}

/* [0x112b2, 0x112f8]: the sprite bank, and the two fix-ups that make it usable.
 *
 * A\SPRITES.cru is read RAW over the title picture, and its 256-record directory then has to be
 * relocated in place: each record's first longword is a FILE-RELATIVE offset in the file and an
 * ABSOLUTE address in memory, so the bank's own base is added to all 256 of them.
 *
 * The four terminators are the other fix-up: each of the four sprite restore lists is given an
 * end marker at its SECOND word rather than its first, which is where the list's cursor starts. */
void init_load_assets_sprites(uint8_t *image) {
    unsigned index;

    image[A_level0_assets_loaded] = SCC_TRUE;        /* `st $176ea` — one byte, not a word */
    load_file(image, A_file_rec_sprites_cru);

    for (index = 0; index < SPRITE_RECORDS; index++) {
        uint32_t record = addr_add(A_sprite_bank, index * SPRITE_RECORD_BYTES);
        wr32(image + record, addr_add(be32(image + record), A_sprite_bank));
    }
    for (index = 0; index < SPRITE_RESTORE_LISTS; index++) {
        uint32_t entry = addr_add(A_sprite_restore_lists,
                                  index * SPRITE_RESTORE_LIST_BYTES + SPRITE_RESTORE_FIRST_ENTRY);
        wr16(image + entry, SPRITE_RESTORE_TERMINATOR);
    }
}

/* init_load_assets @ 0x11212, WHOLE: the two slices above, and the level-0 asset load between them.
 *
 * `clr.w d0 / bsr.w load_level_assets` @ 0x112ac is the frontend subsystem's routine and was
 * unported when the two slices were cut, which is why they were cut. Level 0 is a `clr.w`, so the
 * boot always loads the FIRST stage's five files; a later stage's come from `start_level`.
 *
 * The `bra.s $112ac` @ 0x1127e that joins the two skips 0x11280..0x112aa, a disc prompt whose head
 * was overwritten with that branch (../names.txt @ 0x1127e). This is a single-disc build.
 */
void init_load_assets(uint8_t *image) {
    init_load_assets_title(image);          /* [0x11212, 0x1127e) */
    load_level_assets(image, 0);            /* `clr.w d0 / bsr.w $10332` @ 0x112ac */
    init_load_assets_sprites(image);        /* [0x112b2, its `rts`) */
}

/* ================================================================================================
 * main @ 0x15750 — SLICE [0x15750, 0x15758), the boot's own two calls
 * ============================================================================================= */

/* Everything `main` does before control leaves for the title screen, which is its first two `bsr`s.
 *
 * THE SECOND ONE NEVER COMES BACK. `init_new_game` ends `bra.w enter_title` (its own slice stops at
 * that branch), so the title flow runs off THIS call's stack frame and the third `bsr` @ 0x15758 is
 * reached only when `title_attract_loop`'s `rts` returns into it. A C function cannot express that
 * unwind, so the third call is not here; `test_init.py` composes the whole path — these two calls,
 * `enter_title`, the attract screen and the fire button — in one case that runs the ORIGINAL's own
 * branches from 0x15750 and stops at 0x15758.
 *
 * The name is not `main` because that name belongs to the C runtime; `../names.txt` @ 0x15750 is
 * where the routine is called `main`, and `include/init.h` says so beside the prototype.
 */
void main_boot(uint8_t *image) {
    init_load_assets(image);                /* `bsr.w $11212` @ 0x15750 */
    init_new_game(image);                   /* `bsr.w $112fa` @ 0x15754 */
}

/* ================================================================================================
 * init_new_game @ 0x112fa — SLICE [0x112fa, 0x11394)
 * ============================================================================================= */

/* The seven "this extra-life threshold has already paid out" flags. The FIRST is written from
 * `A_const_words_0123`'s zero word and the other six with `clr.w`, which is two spellings of the
 * same thing and both are reproduced — the differential cannot tell them apart, but a reader of the
 * disassembly beside this can. */
static void clear_bonus_life_flags(uint8_t *image) {
    unsigned index;

    wr16(image + A_bonus_life_awarded_0, const_word(image, CONST_WORD_ZERO));
    for (index = 1; index < BONUS_LIFE_THRESHOLDS; index++)
        wr16(image + addr_add(A_bonus_life_awarded_0, index * BONUS_LIFE_FLAG_BYTES), 0);
}

void init_new_game(uint8_t *image) {
    clear_bonus_life_flags(image);

    wr16(image + A_level_loop_flag_1, 0);
    wr16(image + A_level_loop_flag_2, 0);
    wr16(image + A_level_loop_flag_3, 0);
    wr16(image + A_game_over_delay, GAME_OVER_DELAY_FRAMES);
    wr16(image + A_level_number, const_word(image, CONST_WORD_ZERO));

    /* The "J H" cheat's flag keeps the weapon level across a new game, which is what makes it a
     * cheat: without it both this and the word beside it are cleared. */
    if (image[A_max_weapon_flag] == 0) {
        wr16(image + A_weapon_level, const_word(image, CONST_WORD_ZERO));
        wr16(image + A_unread_word_176a2, 0);
    }

    wr16(image + A_name_entry_first_pass, 0);
    wr16(image + A_hiscore_beaten, 0);
    wr16(image + A_name_entry_timeout, NAME_ENTRY_TIMEOUT);
    wr16(image + A_lives, const_word(image, NEW_GAME_LIVES_INDEX));
    wr16(image + A_item_pickup_pending, 0);

    score_reset(image);
    clear_display_list(image);
    clear_actor_arrays(image);
    /* `bra.w enter_title` @ 0x11394 — the routine never returns to `main`, and the slice ends here. */
}

/* ================================================================================================
 * init_stage_state @ 0x1139a — SLICE [0x1139a, 0x11438)
 * ============================================================================================= */
void init_stage_state(uint8_t *image) {
    image[A_key_last_scancode] = 0;      /* three BYTE clears: the raw scancode and both sticks */
    image[A_joy1_state] = 0;
    image[A_joy0_state] = 0;

    wr32(image + A_spawn_script_cursor, 0);
    wr16(image + A_player_script_fire_enable, 0);
    wr16(image + A_level_distance, 0);
    wr16(image + A_unread_word_176a8, 0);
    wr16(image + A_item_bomb_spawned, 0);
    wr16(image + A_music_suspend_flag, 0);

    wr16(image + A_scroll_fine, SCROLL_FINE_SEED);
    wr16(image + A_landing_bomb_cash_timer, STAGE_BOMB_CASH_PERIOD);
    wr16(image + A_death_anim_cursor, 0);

    /* The one guarded store. `keep_enemy_fire_inhibit` is written NOWHERE in the image, so the clear
     * always runs — reproduced as the test the original makes rather than folded away, because the
     * flag is one `st` away from mattering and a remaster would notice. */
    if (image[A_keep_enemy_fire_inhibit] == 0)
        wr16(image + A_enemy_fire_inhibit, 0);

    wr16(image + A_game_over_flag, 0);
    wr16(image + A_player_script_timer, 0);
    wr16(image + A_bomb_falling, 0);
    wr16(image + A_bomb_exploding, 0);
    wr32(image + A_bomb_path_cursor, 0);          /* `clr.l`: the cursor is a longword */

    wr16(image + A_landing_shadow_timer, STAGE_LANDING_SHADOW);
    wr16(image + A_takeoff_shadow_timer, STAGE_TAKEOFF_SHADOW);
    wr16(image + A_shadow_offset, STAGE_SHADOW_OFFSET);
    wr16(image + A_scroll_pos, STAGE_SCROLL_POS_SEED);
    /* `tst.b hard_mode / beq.w $12cb6 / bra.w $12cc8` — a DISPATCH into the two entries of
     * `difficulty_apply_fire_rates`, each of which falls into `start_level`. The slice ends at the
     * `beq.w`, so the test is inside it and neither branch is. */
}

/* ================================================================================================
 * clear_actor_arrays @ 0x115e2
 * ============================================================================================= */

/* Byte-clear everything from the entity arena to the end of the program.
 *
 * The loop is a DO-WHILE — `clr.b (a0)+ / cmpa.l #$5aede,a0 / blt` — so it clears at least one byte
 * however the limits compare, and it stops at `FS_PROGRAM_END` exclusive. That limit is the .PRG's
 * own end, which is why the span is spelt from `include/globals.h`'s two segment figures rather
 * than as a length. */
void clear_actor_arrays(uint8_t *image) {
    uint32_t cursor = A_entity_arena;

    do {
        image[cursor] = 0;
        cursor = addr_add(cursor, 1);
    } while ((int32_t)cursor < (int32_t)FS_PROGRAM_END);
}

/* ================================================================================================
 * frame_loop_once @ 0x1575c — SLICE [0x1575c, 0x15816), ONE pass of `main`'s endless loop
 *
 * Forty-five `bsr.w`s in the order the original makes them, and then the one store the loop makes
 * for itself. `include/init.h` names the count; the order is the whole content of this function, so
 * it is written out call by call rather than driven from a table — a table would be a second place
 * to read the order from and would hide the three register carries below.
 *
 * THREE REGISTERS THE LOOP CARRIES INTO TWO OF THESE CALLS, and the values are `include/init.h`'s
 * FRAME_* constants:
 *   * `bomb_blast_step` @ 0x157d4 indexes `A_blast_offset_tbl` with the WHOLE of D0 while loading
 *     only its low word (`src/weapons.c`), so its high word is `bomb_publish`'s leftover;
 *   * `player_publish` @ 0x15774 passes D1 and D2 to the game-over banner's text script
 *     (`src/player.c`), and they are whatever `read_player_input` left.
 * `test_init.py::test_the_frame_loops_register_carries_are_what_the_original_leaves` reads all
 * three out of the ORACLE at those two call sites, so the constants are measured rather than
 * assumed and a change in any predecessor fails there by name.
 *
 * TWO OF THE FORTY-FIVE CAN LEAVE THE LOOP ALTOGETHER, by unwinding the stack rather than
 * returning: `read_player_input`'s abort key (`adda.l #$40,a7 / bra game_over_hiscore_check`) and
 * `level_progress_check`'s level-advance arm (`addq.l #4,a7 / bra.w $15758`). Neither is reachable
 * from a frame this function can be verified over — the first needs the abort key held, the second
 * needs the stage's end scroll position — and a C function cannot express either. The STATUS row
 * says which arms the verified frames therefore do not cover.
 * ============================================================================================= */
void frame_loop_once(uint8_t *image) {
    count_game_frame(image);                     /* 0x1575c */
    anim_frame_ids_update(image);                /* 0x15760 */
    player_script_step(image);                   /* 0x15764 */
    level_progress_check(image);                 /* 0x15768 */
    music_restart_if_stopped(image);             /* 0x1576c */
    read_player_input(image);                    /* 0x15770 */
    player_publish(image, FRAME_TEXT_X_D1, FRAME_TEXT_Y_D2);   /* 0x15774 */
    player_bank_recentre(image);                 /* 0x15778 */
    spawn_script_step(image);                    /* 0x1577c */
    entities_move_all(image);                    /* 0x15780 */
    bigobj_overlap_depth_update(image);          /* 0x15784 */
    entity_hide_under_bigobj(image);             /* 0x15788 */
    items_move_all(image);                       /* 0x1578c */
    enemy_bombs_move(image);                     /* 0x15790 */
    items_pickup_check(image);                   /* 0x15794 */
    turrets_aim_all(image);                      /* 0x15798 */
    turrets_publish_all(image);                  /* 0x1579c */
    player_shot_slots_release(image);            /* 0x157a0 */
    enemies_fire_all(image);                     /* 0x157a4 */
    enemy_bullets_move(image);                   /* 0x157a8 */
    player_vs_enemy_bullets(image);              /* 0x157ac */
    enemy_bullets_publish(image);                /* 0x157b0 */
    player_vs_entities(image);                   /* 0x157b4 */
    player_bullets_move_all(image);              /* 0x157b8 */
    entities_publish_all(image);                 /* 0x157bc */
    bigobj_extra_parts_publish(image);           /* 0x157c0 */
    player_bullets_vs_entities(image);           /* 0x157c4 */
    player_bullets_publish_all(image);           /* 0x157c8 */
    bomb_fall_step(image);                       /* 0x157cc */
    bomb_publish(image);                         /* 0x157d0 */
    bomb_blast_step(image, FRAME_BLAST_SCRATCH_D0);            /* 0x157d4 */
    bomb_blast_publish(image);                   /* 0x157d8 */
    bomb_blast_vs_entities(image);               /* 0x157dc */
    items_publish(image);                        /* 0x157e0 */
    muzzle_flash_publish_all(image);             /* 0x157e4 */
    hud_publish_bomb_and_life_icons(image);      /* 0x157e8 */
    check_beat_hiscore(image);                   /* 0x157ec */
    hud_build_score_digits(image);               /* 0x157f0 */
    award_extra_life(image);                     /* 0x157f4 — answers the X flag; the loop drops it */
    scores_bcd_to_chars(image);                  /* 0x157f8 */
    hud_blank_leading_zeros(image);              /* 0x157fc */
    hud_build_labels(image);                     /* 0x15800 */
    scroll_advance(image);                       /* 0x15804 */
    level2_scenery_effect_gate(image);           /* 0x15808 */
    render_frame(image);                         /* 0x1580c */

    wr16(image + A_level_just_started, 0);       /* `clr.w $17696` @ 0x15810 */
}

/* ================================================================================================
 * The glue. Each takes the original's registers; the comment maps register -> role.
 * ============================================================================================= */

/* A0 = the asset record `load_file` opens. */
void g_load_file(uint8_t *image, uint32_t record) { load_file(image, record); }

/* No arguments. `probe_disc` is entered with A0 holding a record and reads its own instead. */
void g_probe_disc(uint8_t *image) { probe_disc(image); }
void g_set_palette_black(uint8_t *image) { set_palette_black(image); }
void g_set_palette_game(uint8_t *image) { set_palette_game(image); }
void g_set_palette_title(uint8_t *image) { set_palette_title(image); }
/* D0 = the Physbase the ring is derived from — `boot_init`'s own register at 0x14c26, one
 * instruction past the XBIOS call that filled it. */
void g_derive_screen_ring(uint8_t *image, uint32_t physbase) { derive_screen_ring(image, physbase); }

void g_boot_init(uint8_t *image) { boot_init(image); }
void g_entry_stub(uint8_t *image) { entry_stub(image); }
void g_init_load_assets_title(uint8_t *image) { init_load_assets_title(image); }
void g_init_load_assets_sprites(uint8_t *image) { init_load_assets_sprites(image); }
void g_init_new_game(uint8_t *image) { init_new_game(image); }
void g_init_stage_state(uint8_t *image) { init_stage_state(image); }
void g_clear_actor_arrays(uint8_t *image) { clear_actor_arrays(image); }
void g_init_load_assets(uint8_t *image) { init_load_assets(image); }
void g_main_boot(uint8_t *image) { main_boot(image); }
void g_frame_loop_once(uint8_t *image) { frame_loop_once(image); }
