/* init.c — the boot prologue and the level-section flow.
 *
 * include/init.h's header comment says why every routine here is a SLICE of one long chain rather
 * than a function with an `rts`, and what the chain does not cover. Each slice below states the
 * address range it is, so a reader can put the ranges end to end and see the gaps.
 *
 * Almost nothing here is new work: the slices are ORCHESTRATION, composed out of leaves other
 * files already verified — `load_file` (src/fileio.c), the sprite builders (src/sprite.c), the
 * block copy (src/util.c), the map unpacker and the tile decoder (src/scroll.c), the screen flip
 * and the palette upload (src/video.c), the sound trigger (src/sound.c). What the slices add is the
 * ORDER, the addresses, and the per-section table lookups that pick which file gets loaded where.
 */
#include "input.h"    /* ikbd_send_cmd — the boot and the front end both use it */
#include "machine.h"
#include "hw.h"        /* the kit's hardware write ledger — include/init.h says what it pins */
#include "os.h"
#include "sched.h"    /* sched_wait8 / sched_poll8 — every busy-wait below reads its byte
                       * through one of these; STATUS.md names the six slices that have one */

#include "entity.h"
#include "fileio.h"
#include "init.h"
#include "irq.h"
#include "enemy.h"
#include "highscore.h"
#include "hud.h"
#include "mothership.h"
#include "rng.h"
#include "scroll.h"
#include "sound.h"
#include "sprite.h"
#include "player.h"
#include "score.h"
#include "text.h"
#include "util.h"
#include "video.h"
#include "weapon.h"

/* How many rows one of this file's constant address tables holds. Six loops here walk such a
 * table, and `sizeof x / sizeof x[0]` spelt out six times pushed four `for` headers onto two
 * lines apiece, with the bound on a different line from the body it guards. */
#define TABLE_ENTRIES(table) (sizeof (table) / sizeof (table)[0])

/* ================================================================================================
 * THE ONE THING THE KIT'S WRITE LEDGER CANNOT HOLD. include/init.h states the argument: the store
 * to $ff8260 is compared like every other hardware store, but its VALUE is `0 & mask` on both sides
 * because the oracle's read of that register answers a fabricated 0 — so the mask itself would
 * survive any mutation. This one byte is the sink that catches that, and it is all the sink is.
 *
 * `set_palette_title` used to need a count here too, since it wrote no image byte and deleting the
 * call left the differential green. It writes eight ledgered longwords now, so the ledger is what
 * makes that a red and the count is gone.
 * ============================================================================================= */
static uint8_t g_shifter_mode_mask;

void init_shifter_sink_reset(void) {
    g_shifter_mode_mask = 0;
}

uint8_t init_shifter_mode_mask_written(void) { return g_shifter_mode_mask; }

/* `andi.b #$fc,$ff8260` — select low resolution. */
static void shifter_select_low_resolution(void) {
    g_shifter_mode_mask = SHIFTER_MODE_RESOLUTION_MASK;
    /* The value is `0 & mask`, i.e. 0, because SHIFTER_MODE_UNMODELED_READ is what the oracle's read
     * of this register answers. That is the RIGHT store off target and the WRONG one on the machine,
     * where the `andi.b` preserves six bits it here clears — include/init.h states the residual and
     * says a Zynaps build for the real Atari must not ship this expression. */
    hw_write8(HW_SHIFTER_MODE, SHIFTER_MODE_UNMODELED_READ & SHIFTER_MODE_RESOLUTION_MASK);
}

/* ================================================================================================
 * boot_enter_supervisor — `_start` @ 0x10000, bytes 0x10000..0x1000f.
 *
 * `clr.l -(a7) / move.w #$20,-(a7) / trap #1 / adda.l #$6,a7 / movea.l d0,a7`: GEMDOS Super(0),
 * and then the program adopts the OLD SUPERVISOR STACK as its own stack. names.txt's comment on
 * 0x10000 records that this is why Ghidra reads D0 as the stack pointer for the whole of `_start`.
 *
 * IT WRITES NO IMAGE BYTE. The three pushes land in the stack band the differential already drops,
 * the trap is served from the model, and the stack switch is a register move — so the slice's whole
 * observable effect is the token in D0, which is what the case compares. That the program then RUNS
 * on that stack is a residual no image differential can reach; STATUS.md records it.
 * ============================================================================================= */
uint32_t boot_enter_supervisor(void) {
    uint32_t token = 0;

    os_super(OS_SUPER_ENTER, &token);
    return token;
}

/* ================================================================================================
 * boot_save_vbl_vector — `_start` bytes 0x10012..0x1001b.
 *
 * `move.l $70.l,$195d0.l`, and it is the whole slice: park TOS's vertical-blank vector so the game
 * can put it back. Both addresses are inside the image (the vector page sits below the 0x10000 load
 * base), so unlike everything else the boot touches this is ordinary diffable memory.
 *
 * IT STARTS AT 0x10012 AND NOT AT 0x10010, because 0x10010 is a Line-A opcode ($a00a, hide the
 * mouse pointer) that the oracle takes as an exception. The reconstruction models it as a no-op —
 * there is no mouse pointer on any surface this project compares — and STATUS.md records that it is
 * modelled rather than verified.
 * ============================================================================================= */
void boot_save_vbl_vector(uint8_t *image) {
    wr32(image + A_saved_tos_vbl_vector, be32(image + A_vector_vbl));
}

/* ================================================================================================
 * boot_load_title_assets — `_start` bytes 0x1002c..0x101b9.
 *
 * The boot's first block of real work, and the longest stretch of `_start` the harness can run end
 * to end: fix the two framebuffers at their hard-coded addresses, read the title picture straight
 * into the back buffer, drop the shifter into low resolution, install the game's own VBL and
 * Timer B handlers, start the title tune, show the picture, upload its palette, and then read and
 * reshape seven more graphics.
 *
 * IT STARTS AT 0x1002c, after the two `ikbd_send_cmd` calls at 0x1001c and 0x10024, AND BOTH OF THE
 * REASONS THE CUTS WERE HERE ARE GONE. Those calls busy-wait on the ACIA status at $fffc00, which
 * the kit had no read for; it is a seeded read slot now, so the spin leaves on its first poll on
 * both sides and `ikbd_send_cmd` itself is verified (src/input.c). The slice ENDS at 0x101ba
 * because that is where the ninth file would be opened and the staged-file table held eight; it
 * holds `harness.OS_FS_SLOTS` now, which is thirty-two — more than this whole boot opens.
 *
 * So the two cuts are where a wave stopped, not where the harness does. STATUS.md's rows for
 * 0x1001c and 0x101ba say what each range needs; neither is blocked.
 * ============================================================================================= */
/* The two framebuffers, hard-coded rather than allocated — names.txt's comment on 0x1002c: this is
 * what makes Zynaps need a 512 KB machine and what makes test/abi.py's scratch map avoid the hole. */
#define BOOT_SCREEN_BACK  0x70300u
#define BOOT_SCREEN_FRONT 0x78000u

/* `moveq #$b,d1` — the tune the title screen starts with. */
#define BOOT_TITLE_TUNE 0x0bu
/* `sound_start` also takes D0, and at this call site D0 is whatever the last GEMDOS Fclose left
 * there — the picture load two instructions earlier. Fclose answers 0 on success, both in the kit's
 * model (`os_fclose` in os.h) and on TOS, so the channel is 0 and this names where the 0 is from
 * rather than pretending the call site chose it. */
#define BOOT_SOUND_CHANNEL_FROM_FCLOSE 0u

/* Where the two loads that feed later work land, and how long they are. The ship block's address is
 * ONE fact used twice — the load's destination and the seventh de-interleave's in-place pair — so
 * it is named once here rather than written out three times. */
#define BOOT_POWER_GAUGE_DST   0x607beu
#define BOOT_POWER_GAUGE_BYTES 0x400u
#define BOOT_SHIP_SOURCE       0x577feu
#define BOOT_SHIP_SOURCE_BYTES 0xaf0u

/* The seven `ship_sprite_deinterleave` calls at 0x100c6..0x10132, as (source, destination). The
 * last rewrites the myship.dat block in place, which is the in-place shape src/sprite.c's comment
 * calls out. */
static const struct { uint32_t src, dst; } BOOT_SHIP_FRAMES[] = {
    { 0x5815eu, 0x5c2feu }, { 0x57fceu, 0x5b67eu }, { 0x57e3eu, 0x5a9feu },
    { 0x57caeu, 0x59d7eu }, { 0x57b1eu, 0x590feu }, { 0x5798eu, 0x5847eu },
    { BOOT_SHIP_SOURCE, BOOT_SHIP_SOURCE },
};

/* GEMGRAF.DAT's block, which the load below fills and the bank build in the NEXT slice preshifts in
 * place — one address used by two slices, so it is named once here rather than written twice. */
#define BOOT_GEMGRAF_BANK 0x5f3beu

/* The five loads at 0x10136..0x101a0, as (filename, destination, length). The four before them are
 * spelt out in the body because each is followed by work that reads what it just loaded. */
static const struct { uint32_t name, dst, length; } BOOT_LATE_LOADS[] = {
    { A_filename_status_pi1,   0x41eaeu, 0x2120u },
    { A_filename_bullet_dat,   0x6e6eeu, 0x0050u },
    { A_filename_explode_dat,  0x5cf7eu, 0x0780u },
    { A_filename_gemgraf_dat,  BOOT_GEMGRAF_BANK, 0x0280u },
    { A_filename_spinners_dat, 0x6115eu, 0x0140u },
};

/* The bank `_start` builds out of spinners.dat at 0x101a4..0x101b6 — four 0x50-byte frames, in
 * place, into four eight-slot preshift banks. */
#define BOOT_SPINNER_BANK   0x6115eu
#define BOOT_SPINNER_FRAME_BYTES 0x50u
#define BOOT_SPINNER_FRAMES 4u

void boot_load_title_assets(uint8_t *image) {
    wr32(image + A_screen_back, BOOT_SCREEN_BACK);
    wr32(image + A_screen_front, BOOT_SCREEN_FRONT);
    /* One whole frame into whichever buffer `screen_back` now names — `SCREEN_BYTES` is video.h's,
     * and the `move.l #$7d00,d1` above the `bsr` is that number. */
    load_file(image, A_filename_zynpic_pic, be32(image + A_screen_back), SCREEN_BYTES);

    shifter_select_low_resolution();
    /* `move.w #$2700,sr` around the two installs — the status register is not an image byte either,
     * and masking interrupts has no counterpart under a harness that runs no interrupt. */
    wr32(image + A_vector_vbl, A_vbl_isr);
    wr32(image + A_vector_timer_b, A_timer_b_isr);

    sound_start(image, BOOT_TITLE_TUNE, BOOT_SOUND_CHANNEL_FROM_FCLOSE);
    screen_flip_buffers(image);
    set_palette_title(image);        /* `bsr set_palette_title` — sixteen ledgered colour registers */

    load_file(image, A_filename_power_dat, BOOT_POWER_GAUGE_DST, BOOT_POWER_GAUGE_BYTES);
    /* 0x1009e sets up a lev1.map load into A_map_unpacked and then overwrites all three registers
     * at 0x100b0 without a `bsr` between them. It is DEAD CODE in the original — the level map is
     * loaded by the section flow below — and is left out rather than transcribed as a load that
     * never happens. */
    load_file(image, A_filename_myship_dat, BOOT_SHIP_SOURCE, BOOT_SHIP_SOURCE_BYTES);

    for (unsigned frame = 0; frame < TABLE_ENTRIES(BOOT_SHIP_FRAMES); frame++)
        ship_sprite_deinterleave(image, BOOT_SHIP_FRAMES[frame].src, BOOT_SHIP_FRAMES[frame].dst);

    for (unsigned load = 0; load < TABLE_ENTRIES(BOOT_LATE_LOADS); load++)
        load_file(image, BOOT_LATE_LOADS[load].name, BOOT_LATE_LOADS[load].dst,
                  BOOT_LATE_LOADS[load].length);

    sprite_bank_build_preshift8(image, BOOT_SPINNER_BANK, BOOT_SPINNER_BANK,
                                BOOT_SPINNER_FRAME_BYTES, BOOT_SPINNER_FRAMES - 1);
}

/* ================================================================================================
 * boot_configure_ikbd — `_start` bytes 0x1001c..0x1002b.
 *
 * Two commands to the keyboard controller and nothing else, which joins `boot_save_vbl_vector`
 * above to `boot_load_title_assets` below. Neither writes an image byte: what they leave behind is
 * two ledgered stores to the ACIA's data port, in order, which is exactly what the case compares.
 *
 * THE SECOND ONE IS WHY THE FRONT END WORKS AT ALL. 0x15 takes the joysticks out of auto-reporting,
 * so a stick's state arrives only when the game asks with 0x16 — and every wait on `A_joystick_state`
 * in this file is a `ikbd_send_cmd(0x16)` followed by a poll of the byte the reply's packet lands in.
 * ============================================================================================= */
void boot_configure_ikbd(void) {
    ikbd_send_cmd(IKBD_CMD_DISABLE_MOUSE);
    ikbd_send_cmd(IKBD_CMD_JOYSTICK_INTERROGATE_MODE);
}

/* ================================================================================================
 * boot_load_gameplay_assets — `_start` bytes 0x101ba..0x104c7.
 *
 * Fourteen more files and every bank built out of them: the shots, the explosions, the weapon-bar
 * icons, the font, the two logos, and the ship's fourteen preshifted frames. It is the longest slice
 * in the boot and it is all composition — every leaf it calls is verified in `fileio`, `sprite` and
 * `util`, and what this proves is the ORDER and the addresses.
 * ============================================================================================= */
/* The two destinations a builder below reads back, so each is one fact rather than two literals. */
#define BOOT_GUNSIGHT_SPRITE 0x6a61eu
#define BOOT_BULLET_BANK     0x62a5eu

static const struct { uint32_t name, dst, length; } BOOT_GAMEPLAY_LOADS[] = {
    { A_filename_smallexp_dat, 0x61b5eu,              0x03c0u },
    { A_filename_newbuls2_dat, BOOT_BULLET_BANK,      0x0078u },
    { A_filename_seeker2_dat,  A_shot_sprite_steered, 0x0370u },
    { A_filename_alseek_dat,   A_shot_sprite_seeker,  0x0370u },
    { A_filename_altexpl_dat,  A_puff_sprite,         0x0500u },
    { A_filename_newbomb_dat,  A_bomb_sprite,         0x0050u },
    { A_filename_gunsight_dat, BOOT_GUNSIGHT_SPRITE,  0x005au },
    { A_filename_sweap_dat,    0x6a8eeu,              0x0820u },  /* hud.h's A_hud_powerup_icons
                                                                   * points into this block */
    { A_filename_ssweap_dat,   0x6b10eu,              0x0360u },  /* ...and A_hud_weapon_icons here */
    { A_filename_smlogos_dat,  A_smlogos_frames,      0x0a00u },
    { A_filename_extchars_dat, A_font_glyphs,         0x0780u },
    { A_filename_lifegra_dat,  A_life_icons,          0x00a0u },
    { A_filename_zynlogo_dat,  A_zynaps_logo,         0x1800u },
    { A_filename_hewlogo_dat,  A_hewson_logo,         0x0600u },
};

/* The two `sprite_preshift8_2px` calls the loads are followed by, in place. */
#define BOOT_BOMB_FRAME_BYTES     0x50u
#define BOOT_GUNSIGHT_FRAME_BYTES 0x5au

/* ...and the four eight-slot banks, as (block, frame bytes, frames). Each `bsr` is preceded by a
 * `move.w #n,d7` that is the frame count less one, which is how the builder takes it. */
static const struct { uint32_t block; uint32_t frame_bytes, frames; } BOOT_SPRITE_BANKS[] = {
    { A_shot_sprite_steered, 0x6eu, 8u },
    { A_puff_sprite,         0xa0u, 8u },
    { A_shot_sprite_seeker,  0x6eu, 8u },
    { BOOT_BULLET_BANK,      0x1eu, 4u },
};

/* THE TWO FRAME SPREADS, and they are one shape written twice rather than twenty addresses. Each is
 * five `copy_block_words` calls stepping DOWN a run of frames and down a run of four-frame banks, so
 * the source moves by one frame and the destination by four each time. The last destination of each
 * spread is the SECOND call's source, which is a consequence of the two strides and not a
 * coincidence — and it is why the order is load-bearing: call 2 reads the block before call 5
 * overwrites it. */
#define BOOT_SPREAD_FRAMES 5u
#define BOOT_BANK_FRAMES   4u
#define BOOT_EXPLOSION_SMALL_TOP 0x61e7eu   /* the highest of the five source frames... */
#define BOOT_EXPLOSION_SMALL_BANK_TOP 0x627deu   /* ...and of the five destination banks */
#define BOOT_EXPLOSION_SMALL_FRAME_BYTES 0xa0u
#define BOOT_EXPLOSION_LARGE_TOP 0x5d5beu
#define BOOT_EXPLOSION_LARGE_BANK_TOP 0x5e87eu
#define BOOT_EXPLOSION_LARGE_FRAME_BYTES 0x140u

/* The two twelve-entry pointer tables, and the frame width each one's sprites are. */
#define BOOT_EXPLOSION_SMALL_PRESHIFT_BYTES 0xa0u
#define BOOT_EXPLOSION_LARGE_PRESHIFT_BYTES 0x50u

/* One more four-frame bank, built out of the GEMGRAF.DAT block the slice above loaded. Its four
 * frames of 0xa0 are exactly that load's 0x280 bytes. */
#define BOOT_GEMGRAF_FRAME_BYTES 0xa0u
#define BOOT_GEMGRAF_FRAMES 4u

/* The ship's own frames: fourteen of them, SHIP_SPRITE_GAP apart, each preshifted in place. The
 * gap is include/sprite.h's — the same 0x640 the de-interleaver above steps by. */
#define BOOT_SHIP_PRESHIFT_FRAMES 14u
#define BOOT_SHIP_FRAME_BYTES 0xc8u

/* ...and the homing shot's, one `sprite_preshift8_2px` on its own at the very end. */
#define BOOT_HOMING_SHOT_FRAME_BYTES 0x50u

static void boot_spread_frames_over_banks(uint8_t *image, uint32_t top_frame, uint32_t top_bank,
                                          uint32_t frame_bytes) {
    for (unsigned frame = 0; frame < BOOT_SPREAD_FRAMES; frame++)
        copy_block_words(image, addr_add(top_frame, (uint32_t)-(int32_t)(frame * frame_bytes)),
                         addr_add(top_bank,
                                  (uint32_t)-(int32_t)(frame * frame_bytes * BOOT_BANK_FRAMES)),
                         frame_bytes);
}

/* `movea.l (a2)+,a0 / movea.l a0,a1 / bsr sprite_preshift4_4px / dbf` — the table holds the frame
 * ADDRESSES, so each entry is preshifted in place at wherever it points. */
static void boot_preshift_frame_table(uint8_t *image, uint32_t table, uint16_t frame_bytes) {
    for (unsigned entry = 0; entry < EXPLOSION_FRAME_PTRS; entry++) {
        uint32_t frame = be32(image + addr_add(table, entry * (uint32_t)sizeof(uint32_t)));

        sprite_preshift4_4px(image, frame, frame, frame_bytes);
    }
}

void boot_load_gameplay_assets(uint8_t *image) {
    for (unsigned load = 0; load < TABLE_ENTRIES(BOOT_GAMEPLAY_LOADS); load++)
        load_file(image, BOOT_GAMEPLAY_LOADS[load].name, BOOT_GAMEPLAY_LOADS[load].dst,
                  BOOT_GAMEPLAY_LOADS[load].length);

    sprite_preshift8_2px(image, A_bomb_sprite, A_bomb_sprite, BOOT_BOMB_FRAME_BYTES);
    sprite_preshift8_2px(image, BOOT_GUNSIGHT_SPRITE, BOOT_GUNSIGHT_SPRITE,
                         BOOT_GUNSIGHT_FRAME_BYTES);
    for (unsigned bank = 0; bank < TABLE_ENTRIES(BOOT_SPRITE_BANKS); bank++)
        sprite_bank_build_preshift8(image, BOOT_SPRITE_BANKS[bank].block,
                                    BOOT_SPRITE_BANKS[bank].block,
                                    BOOT_SPRITE_BANKS[bank].frame_bytes,
                                    BOOT_SPRITE_BANKS[bank].frames - 1);

    boot_spread_frames_over_banks(image, BOOT_EXPLOSION_SMALL_TOP, BOOT_EXPLOSION_SMALL_BANK_TOP,
                                  BOOT_EXPLOSION_SMALL_FRAME_BYTES);
    boot_spread_frames_over_banks(image, BOOT_EXPLOSION_LARGE_TOP, BOOT_EXPLOSION_LARGE_BANK_TOP,
                                  BOOT_EXPLOSION_LARGE_FRAME_BYTES);

    boot_preshift_frame_table(image, A_explosion_small_frame_ptrs,
                              BOOT_EXPLOSION_SMALL_PRESHIFT_BYTES);
    boot_preshift_frame_table(image, A_explosion_large_frame_ptrs,
                              BOOT_EXPLOSION_LARGE_PRESHIFT_BYTES);

    sprite_bank_build_preshift8(image, BOOT_GEMGRAF_BANK, BOOT_GEMGRAF_BANK,
                                BOOT_GEMGRAF_FRAME_BYTES, BOOT_GEMGRAF_FRAMES - 1);
    for (unsigned frame = 0; frame < BOOT_SHIP_PRESHIFT_FRAMES; frame++) {
        uint32_t block = addr_add(BOOT_SHIP_SOURCE, frame * SHIP_SPRITE_GAP);

        sprite_preshift8_2px(image, block, block, BOOT_SHIP_FRAME_BYTES);
    }
    sprite_preshift8_2px(image, A_shot_sprite_homing, A_shot_sprite_homing,
                         BOOT_HOMING_SHOT_FRAME_BYTES);
}

/* ================================================================================================
 * boot_install_ikbd_isr — `_start` bytes 0x104c8..0x104ff.
 *
 * The keyboard's own vector, installed with the ACIA handler's three globals cleared FIRST so that
 * a byte arriving between this store and the first frame lands somewhere that means something. The
 * two `move.w #$27xx,sr` around the store are a CPU register and not an image byte; the harness runs
 * no interrupt, so masking them has no counterpart here.
 *
 * The scancode byte is cleared TWICE — once inside the masked window and once after it — and then
 * `tst.b`ed with the flags thrown away. Both are transcribed: the second clear is a store the diff
 * covers, and the `tst` is the one instruction in the slice with no effect at all.
 * ============================================================================================= */
void boot_install_ikbd_isr(uint8_t *image) {
    wr32(image + A_ikbd_packet_ptr, A_ikbd_joystick_state);
    image[A_ikbd_packet_remaining] = 0;
    image[A_key_scancode] = 0;
    wr32(image + A_vector_acia, A_ikbd_acia_isr);
    image[A_key_scancode] = 0;
    screen_flip_buffers(image);
}

/* ================================================================================================
 * boot_front_end_prologue — `_start` bytes 0x10500..0x1051f.
 *
 * What runs before the title screen, and it is not the same on the two occasions the boot reaches
 * it. The first time through a session `game_initialised` is still 0, so the panel master has not
 * been built and the tune is not restarted; every later time — after a game ends and the flow comes
 * back round — it is 1 and both happen. The answer says which arm ran.
 *
 * The two word clears before the gate land inside the player records the boot's own tail rewrites;
 * include/init.h says what is and is not known about them.
 * ============================================================================================= */
unsigned boot_front_end_prologue(uint8_t *image) {
    wr16(image + addr_add(A_player_records, BOOT_PREATTRACT_CLEAR_A), 0);
    wr16(image + addr_add(A_player_records, BOOT_PREATTRACT_CLEAR_B), 0);
    if (image[A_game_initialised] == 0)
        return 0;

    status_panel_build_master(image);
    sound_start(image, BOOT_TITLE_TUNE, BOOT_SOUND_CHANNEL_FROM_DBF);
    return 1;
}

/* ================================================================================================
 * boot_stage_frontend_screens — `_start` bytes 0x10524..0x105c5.
 *
 * Both framebuffers wiped, the status panel stamped into each of them out of the master, and then
 * three strips of that panel carved back out for the repaints to stamp again. Every address and
 * every figure is include/hud.h's or include/video.h's; the loops are this file's.
 *
 * THE CLEAR READS THE POINTERS AND THE STAMP DOES NOT, and that asymmetry is the original's:
 * `movea.l $1797e.l,a0` for the wipe, then `lea $70300,a0` for the panel. Both reach the same memory
 * today, because the boot fixed both pointers to those two literals a hundred instructions ago —
 * but they are two different instructions and a slice that spelt them the same way would agree with
 * the original only for as long as nothing moved the pointers.
 * ============================================================================================= */
/* The three strips, as (screen offset, destination, bytes per row). include/hud.h owns all six
 * figures — these are the same offsets `status_panel_redraw_all` stamps them BACK to. */
static const struct { uint32_t offset, dst, row_bytes; } BOOT_PANEL_SNAPSHOTS[] = {
    { HISCORE_STRIP_OFFSET, A_hiscore_panel_strip, PANEL_STRIP_ROW_BYTES },
    { SCORE_STRIP_OFFSET,   A_score_panel_strip,   PANEL_STRIP_ROW_BYTES },
    { PLAYER_STRIP_OFFSET,  A_player_panel_strip,  PLAYER_STRIP_ROW_BYTES },
};

/* `move.l (a0)+,(a1)+` n times, and this is the THIRD copy of it in the project — src/hud.c's
 * `copy_longwords` and src/scroll.c's `copy_longs` are the other two. Deliberate and not free: both
 * of those are other agents' files and cannot be shared without editing them, and the alternative —
 * routing a boot slice through a `hud` entry point the original never calls — would be worse. The
 * three already disagree about the 32-bit address wrap, which is what makes the merge worth doing;
 * STATUS.md has the row, with the count, so it happens on purpose. */
static void boot_copy_longwords(uint8_t *image, uint32_t src, uint32_t dst, uint32_t longwords) {
    for (uint32_t lword = 0; lword < longwords; lword++)
        wr32(image + addr_add(dst, lword * (uint32_t)sizeof(uint32_t)),
             be32(image + addr_add(src, lword * (uint32_t)sizeof(uint32_t))));
}

static void boot_snapshot_panel_strip(uint8_t *image, uint32_t offset, uint32_t dst,
                                      uint32_t row_bytes) {
    for (unsigned row = 0; row < PANEL_STRIP_ROWS; row++)
        boot_copy_longwords(image,
                            addr_add(BOOT_SCREEN_FRONT, addr_add(offset, row * SCREEN_ROW_BYTES)),
                            addr_add(dst, row * row_bytes),
                            row_bytes / (uint32_t)sizeof(uint32_t));
}

void boot_stage_frontend_screens(uint8_t *image) {
    image[A_game_initialised] = 1;

    /* `clr.l (a0)+ / clr.l (a1)+` in ONE loop over both buffers, which is why this is not two
     * `screen_clear` calls: the same bytes end up cleared, but the interleave is the instruction.
     *
     * BOTH POINTERS ARE LATCHED BEFORE THE LOOP, because `movea.l $1797e.l,a0` is outside it: a
     * buffer whose 32000 bytes cover the pointer words themselves would zero them mid-wipe, and a
     * body re-reading them each pass would then start clearing from 0 where the original carries on
     * from the address it latched. No case drives that today; the loop is written the way the
     * instructions are so that none has to. */
    uint32_t back = be32(image + A_screen_back);
    uint32_t front = be32(image + A_screen_front);

    for (unsigned lword = 0; lword < SCREEN_BYTES / sizeof(uint32_t); lword++) {
        wr32(image + addr_add(back, lword * (uint32_t)sizeof(uint32_t)), 0);
        wr32(image + addr_add(front, lword * (uint32_t)sizeof(uint32_t)), 0);
    }

    /* `move.l (a2),(a0)+ / move.l (a2)+,(a1)+` — ONE source cursor feeding both buffers, so the
     * panel lands identically in each. */
    boot_copy_longwords(image, A_panel_master, addr_add(BOOT_SCREEN_BACK, PANEL_TOP_OFFSET),
                        PANEL_MASTER_LONGWORDS);
    boot_copy_longwords(image, A_panel_master, addr_add(BOOT_SCREEN_FRONT, PANEL_TOP_OFFSET),
                        PANEL_MASTER_LONGWORDS);

    for (unsigned strip = 0; strip < TABLE_ENTRIES(BOOT_PANEL_SNAPSHOTS); strip++)
        boot_snapshot_panel_strip(image, BOOT_PANEL_SNAPSHOTS[strip].offset,
                                  BOOT_PANEL_SNAPSHOTS[strip].dst,
                                  BOOT_PANEL_SNAPSHOTS[strip].row_bytes);
}

/* ================================================================================================
 * boot_program_timer_b — `_start` bytes 0x105c6..0x1062d.
 *
 * The MFP, step one: the menu VBL on the $70 vector, the in-game pair installed, Timer B stopped,
 * pen 0 blanked, ONE FRAME WAITED FOR, and then Timer B's period written. The slice stops on that
 * write and not after the read-back spin below it — include/init.h says why the spin cannot be run.
 *
 * THE WAIT IS THE FIRST PHASE-8 SITE IN THIS PROJECT. `move.b #$1,$198ab` then `tst.b $198ab / bne`:
 * the flag is set here and cleared by a VBL handler that no off-target run executes, so the byte is
 * a SCHEDULED store the case declares and `sched_wait8` is how this side counts the same iterations
 * the oracle does (kit TRAP_MODEL.md, Phase 8).
 * ============================================================================================= */
#define BOOT_VSYNC_WAIT_SITE 0x1061eu   /* the `tst.b $198ab` the original re-reads the flag at */
#define BOOT_VSYNC_WAIT_SITE_RASTER 0x10648u   /* ...and the second wait's own */

/* `move.b #$1,$198ab` then spin until a VBL clears it — the whole of "wait one frame".
 *
 * IT RETURNS THE WAIT'S VERDICT because sched.h requires it ("A CALLER MUST HONOUR THE 0"): a wait
 * the case's schedule never released has tallied a refusal, and the behaviour past it is undefined,
 * so a caller inside a loop must leave rather than go round again. The straight-line callers ignore
 * it — there is nothing after them to protect — and `attract_wait_for_start` does not. */
static int boot_wait_one_frame(uint8_t *image, uint32_t site_pc) {
    image[A_vsync_flag] = 1;
    return sched_wait8(image, A_vsync_flag, 0, site_pc);
}

void boot_program_timer_b(uint8_t *image) {
    wr32(image + A_vector_vbl, A_vbl_menu);
    image[A_starfield_layer2_phase] = 0;
    image[A_starfield_layer3_countdown] = STARFIELD_LAYER3_PERIOD;
    hw_write8(HW_MFP_IERA, 0);

    wr32(image + A_vector_vbl, A_vbl_isr);
    wr32(image + A_vector_timer_b, A_timer_b_isr);
    hw_write8(HW_MFP_TIMER_B_CONTROL, MFP_TIMER_B_STOPPED);
    shifter_clear_pen0();

    (void)boot_wait_one_frame(image, BOOT_VSYNC_WAIT_SITE);
    hw_write8(HW_MFP_TIMER_B_DATA, MFP_TIMER_B_PERIOD_PLAIN);
}

/* ================================================================================================
 * boot_program_raster_timer — `_start` bytes 0x10638..0x1066b.
 *
 * Step two, and it undoes most of step one: Timer B is started at the plain period, ANOTHER frame is
 * waited for, and then the raster-split pair is installed and the period rewritten. The slice again
 * stops on the period write, before the spin that reads it back.
 * ============================================================================================= */
void boot_program_raster_timer(uint8_t *image) {
    hw_write8(HW_MFP_TIMER_B_CONTROL, MFP_TIMER_B_EVENT_COUNT);
    (void)boot_wait_one_frame(image, BOOT_VSYNC_WAIT_SITE_RASTER);

    wr32(image + A_vector_vbl, A_vbl_menu);
    wr32(image + A_vector_timer_b, A_timer_b_raster_isr);
    hw_write8(HW_MFP_TIMER_B_DATA, MFP_TIMER_B_PERIOD_RASTER);
}

/* ================================================================================================
 * boot_enable_interrupts — `_start` bytes 0x10676..0x106a1, ending in the `bra.w` to 0x10792.
 *
 * Timer B restarted at the raster period, and then four MFP registers opened up: Timer B in A's
 * enable and mask, the keyboard ACIA in B's. It writes no image byte at all — the whole slice is
 * five ledgered hardware stores, in order, which is what the case compares.
 *
 * THE TWO `bset`s HAVE `mfp_ack_timer_b`'s RESIDUAL. They are read-modify-writes of registers the
 * seeded read model does not name, so the read half answers a fabricated 0 and both sides store a
 * bare bit rather than the bit ON TOP of whatever the MFP held. include/irq.h states the rule once.
 * ============================================================================================= */
void boot_enable_interrupts(void) {
    hw_write8(HW_MFP_TIMER_B_CONTROL, MFP_TIMER_B_EVENT_COUNT);
    hw_write8(HW_MFP_IERA, MFP_IER_TIMER_B);
    hw_write8(HW_MFP_IMRA, MFP_IER_TIMER_B);
    hw_write8(HW_MFP_IERB, 1u << MFP_ACIA_CHANNEL_BIT);
    hw_write8(HW_MFP_IMRB, 1u << MFP_ACIA_CHANNEL_BIT);
}

/* ================================================================================================
 * boot_new_game_records — `_start` bytes 0x10792..0x10813.
 *
 * A fresh game: two player records built from immediates, one of them cut back to no lives when the
 * menu chose a single player, and then the LIVE record's fields copied out into the globals the rest
 * of the game reads. It falls straight into `section_advance`, so 0x10814 is both its exit and that
 * slice's entry.
 *
 * WHAT THE TWO RECORDS DISAGREE ABOUT IS THE POINT. Player 1's section byte is 0xff and player 2's
 * is 0 — see include/init.h — so the `addi.b #$1` at the top of `section_advance` turns the copied
 * 0xff into section 0 and the game starts at the first section.
 * ============================================================================================= */
/* The two records, spelt as the immediates the original stores rather than as a loop over a
 * template: they differ in one field, and a template plus a fix-up would hide which. */
static void boot_write_player_record(uint8_t *image, uint32_t record, uint8_t section) {
    wr32(image + addr_add(record, PLAYER_RECORD_SCORE), 0);
    image[addr_add(record, PLAYER_RECORD_LIVES)] = PLAYER_RECORD_START_LIVES;
    image[addr_add(record, PLAYER_RECORD_SECTION)] = section;
    wr32(image + addr_add(record, PLAYER_RECORD_MAP_PTR), A_map_unpacked);
    image[addr_add(record, PLAYER_RECORD_POWERUP)] = 0;
    image[addr_add(record, PLAYER_RECORD_WEAPON)] = PLAYER_RECORD_START_WEAPON;
    image[addr_add(record, PLAYER_RECORD_SPEED)] = 0;
    image[addr_add(record, PLAYER_RECORD_PAD)] = 0;
}

void boot_new_game_records(uint8_t *image) {
    uint32_t live = A_player_records;

    boot_write_player_record(image, A_player_records, PLAYER_RECORD_START_SECTION);
    boot_write_player_record(image, addr_add(A_player_records, PLAYER_RECORD_BYTES), 0);
    /* One player means player 2 starts dead, which is what stops the flow ever switching to them. */
    if (image[A_player_count] == ATTRACT_PLAYERS_ONE)
        image[addr_add(A_player_records, PLAYER_RECORD_BYTES + PLAYER_RECORD_LIVES)] = 0;
    image[A_current_player_index] = 0;

    wr32(image + A_player_score_bcd, be32(image + addr_add(live, PLAYER_RECORD_SCORE)));
    image[A_lives] = image[addr_add(live, PLAYER_RECORD_LIVES)];
    image[A_level_section] = image[addr_add(live, PLAYER_RECORD_SECTION)];
    image[A_powerup_cursor] = image[addr_add(live, PLAYER_RECORD_POWERUP)];
    image[A_weapon_power_level] = image[addr_add(live, PLAYER_RECORD_WEAPON)];
    image[A_ship_speed_level] = image[addr_add(live, PLAYER_RECORD_SPEED)];
}

/* ================================================================================================
 * section_advance — 0x10814..0x10838, reached by `bra.w` from three places in the frame chain
 * (names.txt's comments on 0x12846, 0x128ea and 0x12934).
 *
 * Rewind the map to the level's first column, step the section on, and wrap it at sixteen. It falls
 * straight into the gate below, so 0x1083a is both its exit and that slice's entry.
 * ============================================================================================= */
void section_advance(uint8_t *image) {
    wr32(image + A_map_ptr, A_map_unpacked);
    image[A_level_section]++;
    if (image[A_level_section] == SECTION_COUNT)
        image[A_level_section] = 0;
}

/* ================================================================================================
 * section_reload_needed — 0x1083a..0x10858.
 *
 * The one decision in the chain: are this section's assets already in RAM? If they are, the flow
 * jumps straight to the section start at 0x10b6e and this slice writes nothing at all; if they are
 * not, it records the section as loaded, clears the PREPARE FOR COMBAT banner, and falls into the
 * asset load.
 *
 * IT HAS TWO EXITS AND THEY ARE DIFFERENT ADDRESSES, so the two arms are two cases with two
 * checkpoints rather than one case with a branch — 0x1085a for the reload arm and 0x10b6e for the
 * jump. The answer is the return value so a case can check WHICH exit as well as the bytes.
 * ============================================================================================= */
unsigned section_reload_needed(uint8_t *image) {
    if (image[A_level_section_loaded] == image[A_level_section])
        return 0;
    image[A_level_section_loaded] = image[A_level_section];
    image[A_show_prepare_for_combat] = 0;
    return 1;
}

/* ================================================================================================
 * section_load_assets — 0x10862..0x10b6c.
 *
 * Everything this level section needs, chosen out of nine sixteen-byte tables indexed by the
 * section number. THE FILENAMES ARE PATCHED IN PLACE: the variant letter or digit is stored into
 * the string in the text segment (`move.b <table>(a0,d0.w),$196b5.l` and four siblings) and the
 * load then opens whatever the string now says. So the text segment is program state here, the
 * differential covers it, and a case that got a table index wrong would open a different file.
 *
 * IT STARTS AT 0x10862, after the `bsr`s at 0x1085a and 0x1085e — those two are their own slice,
 * `section_reload_intro_screens` below.
 *
 * BOTH ARMS ARE COVERED. A section whose type byte is 'q' branches at 0x109e2 to 0x10a3e, and FOUR
 * of the sixteen take it (the section-type table's four 'q' entries, pinned by test_init.py's
 * ASTEROID_SECTION_COUNT). The two arms share this routine's whole first half and then diverge
 * completely, so the answer names which one ran.
 * ============================================================================================= */
/* The two alien banks. Both are four 0xa0-byte frames built into an eight-slot preshift bank, and
 * both are read through THE SAME filename — the variant letter is patched between the two loads. */
#define SECTION_ALIEN_BANK_A 0x54ffeu
#define SECTION_ALIEN_BANK_B 0x563feu
#define SECTION_ALIEN_BYTES 0x280u
#define SECTION_ALIEN_FRAME_BYTES 0xa0u
#define SECTION_ALIEN_FRAMES 4u

/* The boss sprite is read onto the buffer `mothership_sprite_expand` reads as ITS source, so the
 * destination is include/mothership.h's `A_mothership_sprite_source` and not a second 0x5ed7e here
 * — that this load's target and that expander's input are one address is a fact worth stating. */
#define SECTION_MOTHER_BYTES 0x640u

/* The missile graphic and the four 0x5a-byte frames the flow makes out of it. The two copies at
 * 0x1095e and 0x10974 SHARE ONE SOURCE CURSOR: `copy_block_words` leaves A0 one past the last word
 * it read and the second call sets only A1, so the second frame is copied from where the first
 * stopped. That is the instruction sequence and it is what the two destinations below say. */
#define SECTION_MISSILE_SRC   0x60bbeu
#define SECTION_MISSILE_BYTES 0x168u
#define SECTION_MISSILE_FRAME_BYTES 0x5au
#define SECTION_MISSILE_COPY_SRC 0x60c72u
#define SECTION_MISSILE_FRAME_1 0x60c18u
#define SECTION_MISSILE_FRAME_2 0x60e8eu
#define SECTION_MISSILE_FRAME_3 0x60ee8u
static const uint32_t SECTION_MISSILE_COPY_DST[] = { SECTION_MISSILE_FRAME_2,
                                                     SECTION_MISSILE_FRAME_3 };
/* The four frames the preshift pass walks are the loaded block, the frame beside it in the file,
 * and the two the copies above just made — the same addresses, named once. */
static const uint32_t SECTION_MISSILE_PRESHIFT[] = { SECTION_MISSILE_SRC, SECTION_MISSILE_FRAME_1,
                                                     SECTION_MISSILE_FRAME_2,
                                                     SECTION_MISSILE_FRAME_3 };

/* The ground-target graphic: one 0x280-byte file into four 0xa0-byte frames, three of them copied
 * out of the loaded block and all four preshifted. Each copy names both ends, so unlike the missile
 * pair above there is no shared cursor here. */
#define SECTION_GROUND_DST 0x62e1eu
#define SECTION_GROUND_BYTES 0x280u
#define SECTION_GROUND_FRAME_BYTES 0xa0u
#define SECTION_GROUND_FRAME_1 0x6331eu
#define SECTION_GROUND_FRAME_2 0x6381eu
#define SECTION_GROUND_FRAME_3 0x63d1eu
static const struct { uint32_t src, dst; } SECTION_GROUND_COPIES[] = {
    { 0x62ebeu, SECTION_GROUND_FRAME_1 },
    { 0x62f5eu, SECTION_GROUND_FRAME_2 },
    { 0x62ffeu, SECTION_GROUND_FRAME_3 },
};
/* The loaded block plus the three the copies above just made — the same addresses, named once. */
static const uint32_t SECTION_GROUND_PRESHIFT[] = { SECTION_GROUND_DST, SECTION_GROUND_FRAME_1,
                                                    SECTION_GROUND_FRAME_2,
                                                    SECTION_GROUND_FRAME_3 };

/* `lea $4b3be,a0 / move.w #$7,d0 / clr.l (a0)+` — the tile set's first eight longwords are zeroed
 * once it is loaded, so tile 0 is a blank tile whatever the artwork put there. */
#define SECTION_BLANK_TILE_BYTES 0x20u

/* `move.b $19895,d0 / ext.w d0 / move.b (a0,d0.w),d1` — one per-section table byte, at the current
 * section. The index is SIGN-EXTENDED at all six sites this stands for, so a section byte with bit 7
 * set would read 128 bytes BELOW the table rather than 128 above it. Nothing drives the byte there —
 * `section_advance` keeps it under SECTION_COUNT — but it is the instruction, and the same idiom is
 * transcribed the same way for the palette index and the restart table below. */
static uint8_t section_table_byte(const uint8_t *image, uint32_t table) {
    return image[addr_add(table, sign_ext8(image[A_level_section]))];
}

/* Patching the letter and loading the bank are separate helpers because of the FIRST bank only: the
 * original patches its letter, writes four unrelated bytes, and only then opens the file, so one
 * `load_alien_bank(table, dst)` would have to reorder those four stores. The second bank's pair IS
 * adjacent and could be folded — it is spelt the same way so the two loads read as one shape. */
static void section_patch_alien_variant(uint8_t *image, uint32_t variant_table) {
    image[A_filename_alien_dat + FILENAME_ALIEN_VARIANT] =
        section_table_byte(image, variant_table);
}

/* `movem.l (a0),#$00ff` then `movem.l #$00ff,$19f66` — eight longwords, one whole colour row. Both
 * arms of the asset load end with it; only the row they take differs. */
static void publish_section_palette(uint8_t *image, uint32_t row) {
    for (unsigned pair = 0; pair < SECTION_PALETTE_BYTES / PALETTE_LONG_BYTES; pair++)
        wr32(image + A_palette_next + PALETTE_LONG_BYTES * pair,
             be32(image + addr_add(row, PALETTE_LONG_BYTES * pair)));
}

static void section_build_alien_bank(uint8_t *image, uint32_t bank) {
    load_file(image, A_filename_alien_dat, bank, SECTION_ALIEN_BYTES);
    sprite_bank_build_preshift8(image, bank, bank, SECTION_ALIEN_FRAME_BYTES,
                                SECTION_ALIEN_FRAMES - 1);
}

unsigned section_load_assets(uint8_t *image) {
    uint8_t mothership_variant;
    uint8_t palette_index;

    section_patch_alien_variant(image, A_alien_variant_table);
    image[A_section_param_a] = section_table_byte(image, A_section_param_a_table);
    image[A_section_param_b] = section_table_byte(image, A_section_param_b_table);
    mothership_variant = section_table_byte(image, A_mothership_variant_table);
    image[A_filename_mother_dat + FILENAME_MOTHER_VARIANT] = mothership_variant;
    image[A_mothership_index] = (uint8_t)(mothership_variant - MOTHERSHIP_VARIANT_DIGIT_BASE);
    section_build_alien_bank(image, SECTION_ALIEN_BANK_A);

    section_patch_alien_variant(image, A_alien2_variant_table);
    section_build_alien_bank(image, SECTION_ALIEN_BANK_B);

    load_file(image, A_filename_mother_dat, A_mothership_sprite_source, SECTION_MOTHER_BYTES);

    image[A_filename_missile_dat + FILENAME_MISSILE_VARIANT] =
        section_table_byte(image, A_missile_variant_table);
    load_file(image, A_filename_missile_dat, SECTION_MISSILE_SRC, SECTION_MISSILE_BYTES);
    {
        uint32_t copy_src = SECTION_MISSILE_COPY_SRC;   /* A0, carried between the two copies */

        for (unsigned copy = 0; copy < TABLE_ENTRIES(SECTION_MISSILE_COPY_DST); copy++) {
            unsigned words = copy_block_words(image, copy_src, SECTION_MISSILE_COPY_DST[copy],
                                              SECTION_MISSILE_FRAME_BYTES);
            copy_src = addr_add(copy_src, words * 2u);
        }
    }
    for (unsigned frame = 0; frame < TABLE_ENTRIES(SECTION_MISSILE_PRESHIFT); frame++)
        sprite_preshift4_4px(image, SECTION_MISSILE_PRESHIFT[frame],
                             SECTION_MISSILE_PRESHIFT[frame], SECTION_MISSILE_FRAME_BYTES);

    /* 0x109de's `cmp.b #$71,d0` and 0x109e2's `beq`. THE ASTEROID ARM SKIPS THE MAP ENTIRELY: no
     * level file, no tile set, no ground target — one sprite file, the flag the map arm clears, and
     * a fixed palette row instead of a per-section one. It reaches the same 0x10b6e the map arm
     * falls through to, and the answer says which of the two ran because they disagree about
     * `$198fd`, which `section_start_prefill` reads. */
    if (section_table_byte(image, A_section_type_table) == SECTION_TYPE_ASTEROID) {
        asteroids_load_and_build(image);
        image[A_asteroid_section_flag] = 1;
        publish_section_palette(image, A_palette_asteroid);
        return 0;
    }

    image[A_asteroid_section_flag] = 0;
    image[A_filename_lev_map + FILENAME_LEV_VARIANT] =
        section_table_byte(image, A_section_type_table);
    load_file(image, A_filename_lev_map, A_tile_set_base, SECTION_MAP_READ_CAP);
    map_rle_decompress(image);
    image[A_filename_zyn_dat + FILENAME_ZYN_VARIANT] =
        section_table_byte(image, A_zyn_variant_table);
    load_file(image, A_filename_zyn_dat, A_tile_set_base, SECTION_TILE_SET_READ_CAP);

    /* The palette index is a table byte that indexes TWO tables in turn: the ground-target flag and
     * the palette row itself. It reaches both through `ext.w`/`ext.l` on the byte, so a table entry
     * with bit 7 set would index BELOW both tables; the shipped sixteen run 0 to 0x0c. */
    palette_index = section_table_byte(image, A_section_palette_index_table);
    image[A_section_ground_target_flag] =
        image[addr_add(A_ground_target_by_palette_table, sign_ext8(palette_index))];
    publish_section_palette(image, addr_add(A_palette_per_section_table,
                                            sign_ext8(palette_index) * SECTION_PALETTE_BYTES));

    load_file(image, image[A_section_ground_target_flag] ? A_filename_gndtarg1_dat
                                                         : A_filename_rocket_dat,
              SECTION_GROUND_DST, SECTION_GROUND_BYTES);
    for (unsigned copy = 0; copy < TABLE_ENTRIES(SECTION_GROUND_COPIES); copy++)
        copy_block_words(image, SECTION_GROUND_COPIES[copy].src, SECTION_GROUND_COPIES[copy].dst,
                         SECTION_GROUND_FRAME_BYTES);
    for (unsigned frame = 0; frame < TABLE_ENTRIES(SECTION_GROUND_PRESHIFT); frame++)
        sprite_preshift8_2px(image, SECTION_GROUND_PRESHIFT[frame], SECTION_GROUND_PRESHIFT[frame],
                             SECTION_GROUND_FRAME_BYTES);

    for (unsigned pair = 0; pair < SECTION_BLANK_TILE_BYTES / PALETTE_LONG_BYTES; pair++)
        wr32(image + A_tile_set_base + PALETTE_LONG_BYTES * pair, 0);
    return 1;
}

/* ================================================================================================
 * section_reload_intro_screens — 0x1085a..0x10862.
 *
 * Two `bsr`s and nothing else, between the reload gate and the asset load: put the PLAYER n screen
 * up and repaint the whole status panel. Both are `hud`'s and both are verified, so this slice is
 * pure composition — what it proves is the ORDER, which is observable because the intro screen ends
 * in `screen_flip_buffers` and the panel repaint then draws into the buffer that flip chose.
 * ============================================================================================= */
void section_reload_intro_screens(uint8_t *image) {
    player_intro_screen(image);
    status_panel_redraw_all(image);
}

/* ================================================================================================
 * section_restart_prologue — 0x10b6e..0x10c4e.
 *
 * The per-life reset every section start runs through, reached either by falling out of the asset
 * load or by the reload gate's `beq` when the assets were already in RAM. It sets the PREPARE FOR
 * COMBAT banner, shows the same two front-end screens the slice above does, and then clears 0xd0
 * bytes' worth of state belonging to five other subsystems — which is why this file includes their
 * headers rather than restating any address.
 *
 * WHAT SURVIVES IS AS DELIBERATE AS WHAT DOES NOT. The alive-byte sweep runs slots 0..17 and the
 * `clr.b $17de0` after it is the GUNSIGHT's alive byte (slot 19), so slot 18 — the ship's shadow
 * record — is the one entity left alive. The type-byte sweep is six slots, not eighteen: only the
 * player's own shot slots are retyped.
 * ============================================================================================= */
void section_restart_prologue(uint8_t *image) {
    image[A_show_prepare_for_combat] = 1;
    section_reload_intro_screens(image);

    for (unsigned slot = 0; slot < SECTION_RESTART_KILL_SLOTS; slot++)
        image[addr_add(A_entity_table, slot * ENTITY_STRIDE) + ENTITY_ALIVE] = 0;
    image[A_entity_gunsight + ENTITY_ALIVE] = 0;
    for (unsigned slot = 0; slot < PLAYER_SHOT_SLOTS; slot++)
        image[addr_add(A_entity_table, slot * ENTITY_STRIDE) + ENTITY_TYPE] = 0;
    for (unsigned slot = 0; slot < SECTION_RESTART_ASTEROID_RECORDS; slot++)
        image[addr_add(A_asteroid_records, slot * ENTITY_STRIDE) + ENTITY_ALIVE] = 0;

    wr16(image + A_player_record + ENTITY_X, SECTION_RESTART_SHIP_X);
    wr16(image + A_player_record + ENTITY_Y, SECTION_RESTART_SHIP_Y);
    wr16(image + A_ship_record_shadow + ENTITY_X, SECTION_RESTART_SHADOW_X);
    wr16(image + A_ship_record_shadow + ENTITY_Y, SECTION_RESTART_SHIP_Y);

    image[A_death_event_flags] = 0;
    image[A_missile_launch_counter] = SECTION_RESTART_LAUNCH_STOCK;
    image[A_bomb_launch_counter] = SECTION_RESTART_LAUNCH_STOCK;
    for (unsigned mark = 0; mark < SQUADRON_MARKS; mark++)
        image[A_squadron_kill_counters + mark] = 0;
    image[A_key_scancode] = 0;
    image[A_explosion_group_active_bits] = 0;
    image[A_scroll_frozen] = 0;
    image[A_mothership_ready] = 0;
    image[A_mothership_pending] = 0;

    /* The pair's sprites and heights, written LAST and from a second `lea` of the same record. */
    wr32(image + A_player_record + ENTITY_SPRITE, BOOT_SHIP_SOURCE);
    wr32(image + A_ship_record_shadow + ENTITY_SPRITE,
         addr_add(BOOT_SHIP_SOURCE, SHIP_SPRITE_GAP));
    wr16(image + A_player_record + ENTITY_HEIGHT, SECTION_RESTART_SHIP_ROWS);
    wr16(image + A_ship_record_shadow + ENTITY_HEIGHT, SECTION_RESTART_SHIP_ROWS);
}

/* ================================================================================================
 * section_start_prefill — 0x10c4e..0x10d94.
 *
 * Two steps, and the second is the whole reason the scroller exists. First the map is seeked to
 * this section's restart point: the word table at `A_section_restart_table` is scanned BACKWARDS
 * from the section's own entry for the last offset at or below where the map cursor already is, and
 * `map_ptr` / `map_offset` / `scroll_pos` are set from it. Then 160 columns of backdrop are
 * pre-rendered into the eight off-screen pages with the display hidden — page 0 decodes a fresh
 * tile column and advances the map, pages 1..7 re-emit the same column two pixels further along
 * each time, which is exactly the eight sub-cell phases the ring blits then scroll through.
 *
 * IT STARTS AT 0x10c4e and not at 0x10b6e. The 0xd0 bytes before it reset globals belonging to five
 * other subsystems, and two of the routines it calls (`player_intro_screen`, the panel repaint) are
 * unported; STATUS.md carries that stretch as the gap it is.
 * ============================================================================================= */
/* The scroller reads the map cursor from `map_ptr` and hands the emitters a column of the page the
 * `map_page` byte names, at the `map_column` phase — `lsl.l #2` into the pointer table, `lsl.l #3`
 * into the page. Both shifts are the table's own stride and are written as such. */
#define MAP_PAGE_POINTER_BYTES 4u

void section_start_prefill(uint8_t *image) {
    uint32_t cursor = be32(image + A_map_ptr);
    /* `ext.w d7 / lsl.w #3,d7` then a `(a0,d7.w)` index: the section byte is sign-extended twice
     * over, so a section past 0x7f would scan below the table. The flow keeps it under 0x10. */
    uint32_t restart = addr_add(A_section_restart_table,
                                sign_ext16((uint16_t)(sign_ext8(image[A_level_section])
                                                      * SECTION_RESTART_ENTRY_BYTES)));
    uint32_t offset;

    if ((int32_t)cursor >= (int32_t)SECTION_REWIND_FLOOR)
        cursor = addr_add(cursor, (uint32_t)-(int32_t)SECTION_REWIND_BYTES);

    /* `lea -2(a0),a0` and NOT a step through the entry's own four words: the base pointer walks
     * back two bytes a time while the section index stays put, so the scan runs from this section's
     * slot down through the sections before it.
     *
     * WHAT TERMINATES IT is the table's own shape and nothing in the code: every section's
     * four-word group descends to a final 0x0000, and a candidate of `A_map_unpacked + 0` satisfies
     * `<= cursor` for any cursor at or above the map's base. A cursor BELOW the map's base — which
     * no case seeds and no caller produces, since `section_advance` sets it to exactly the base —
     * would walk off the front of the table on both sides, and the oracle's own answer to that is a
     * `max_insns` timeout rather than a diff. Recorded so the shape is the argument rather than the
     * unbounded loop being an oversight. */
    for (;;) {
        uint32_t candidate = addr_add(A_map_unpacked,
                                      sign_ext16(be16(image + addr_add(restart, 0))));

        if ((int32_t)candidate <= (int32_t)cursor) {
            wr32(image + A_map_ptr, candidate);
            offset = candidate - A_map_unpacked;
            break;
        }
        restart = addr_add(restart, (uint32_t)-2);
    }
    wr32(image + A_map_offset, offset);
    /* `divu.w #$24,d6 / and.l #$ffff,d6 / lsl.l #3,d6` — the column index times one cell's bytes.
     * `divu` leaves the remainder in the high half, which the mask drops. What keeps the quotient
     * inside a word is that every restart word is NON-NEGATIVE, not that the map is small: `offset`
     * is an unsigned subtraction, so one negative table entry would make it about 4 G, and a 68000
     * `divu.w` that overflows sets V and leaves D6 UNCHANGED where this computes a masked quotient.
     * The shipped table's words are all positive; a future edit that changed that would diverge
     * here, and it is the SIGN to look at, not the size. */
    wr32(image + A_scroll_pos, ((offset / MAP_COLUMN_BYTES) & 0xffffu) * SCROLL_PHASE_STEP);

    if (image[A_asteroid_section_flag] != 0)
        return;                      /* an asteroid section has no backdrop to pre-render */

    image[A_scroll_prefill_hide_screen] = 1;
    for (unsigned column = 0; column < SECTION_PREFILL_COLUMNS; column++) {
        uint32_t page = be32(image + addr_add(A_map_page_table,
                                             (uint32_t)image[A_map_page] * MAP_PAGE_POINTER_BYTES));
        uint32_t edge = addr_add(be32(image + A_screen_back), SCROLL_WINDOW_BYTES);
        uint32_t page_column = addr_add(page, (uint32_t)image[A_map_column] * SCROLL_PHASE_STEP);

        wr32(image + A_map_page_ptr, page);
        if (image[A_map_page] == 0) {
            /* Page 0 decodes a fresh tile column and moves the map on; `map_offset` is republished
             * from the cursor BEFORE the decode, so it names the column about to be drawn. */
            uint32_t cursor_now = be32(image + A_map_ptr);

            wr32(image + A_map_offset, cursor_now - A_map_unpacked);
            wr32(image + A_map_ptr,
                 scroll_emit_tile_column(image, edge, page_column, cursor_now));
        } else {
            scroll_emit_column_shift2(image, A_scroll_col_workspace, page_column, edge);
        }
        image[A_map_page]++;
        if (image[A_map_page] == MAP_PAGES) {
            image[A_map_page] = 0;
            image[A_map_column]++;
            if (image[A_map_column] == SCROLL_PHASES)
                image[A_map_column] = 0;
        }
    }
}

/* ================================================================================================
 * section_start_tail — 0x10d96..0x10f4d, the last stretch before the frame loop.
 *
 * Three jobs, in this order: seek the two event scripts to wherever the restart point put the map,
 * reset the per-life shelf, and then WAIT FOR THE PLAYER. The wait is the interesting half — the
 * game asks the keyboard controller for the joysticks on every pass and spins on the byte
 * `ikbd_acia_isr` writes the reply into, so nothing off target moves it and the case declares the
 * store (kit TRAP_MODEL.md, Phase 8).
 * ============================================================================================= */
#define SECTION_TAIL_FIRE_WAIT_SITE 0x10f2au   /* the `tst.b $19681` the original re-reads it at */

/* `clr.l d6 / move.w (a0),d6 / cmp.l d6,d7 / blt` — is this entry's map offset at or behind the
 * cursor? The offset is a WORD read into a cleared longword, so it is unsigned; the compare that
 * follows is a SIGNED longword one against a cursor the caller has already biased. */
static int script_entry_is_behind(const uint8_t *image, uint32_t entry, uint32_t cursor) {
    /* THE WALK'S ONLY BOUND, and it is the HARNESS's rather than the original's. Neither scan has a
     * terminator of its own — each runs until an entry's offset passes the cursor, which the shipped
     * tables always provide — so a cursor larger than any 16-bit offset would walk off the end of
     * the image. On the oracle that is an instruction-cap timeout and the case is thrown away; on
     * this side it would be a read past the buffer, which crashes the worker and reports nothing.
     * Stopping at the edge makes the two sides fail the same harmless way. */
    if (!os_in_image(entry, sizeof(uint16_t)))
        return 0;
    return (int32_t)cursor >= (int32_t)(uint32_t)be16(image + entry);
}

/* `ext.w d1 / lsl.w #2,d1 / movea.l (a0,d1.w),a0` — the same sign-extend-then-index idiom
 * `section_table_byte` above uses, one width up: a table byte with bit 7 set would fetch a pointer
 * from BELOW the table. The shipped indices are 0..0x0f. */
static uint32_t script_table_entry(const uint8_t *image, uint32_t table, uint8_t index) {
    return be32(image + addr_add(table, sign_ext16((uint16_t)(sign_ext8(index)
                                                              * SCRIPT_TABLE_ENTRY_BYTES))));
}

/* The GROUND script's scan, which reads nothing out of the entries it walks past. */
static uint32_t ground_script_seek(const uint8_t *image, uint32_t script, uint32_t cursor) {
    while (script_entry_is_behind(image, script, cursor))
        script = addr_add(script, SCRIPT_ENTRY_BYTES);
    return script;
}

/* The WAVE script's, which does: every entry it walks past whose payload names one of the two
 * squadron opcodes leaves the flag in that state, so the flag ends up as the LAST such entry before
 * the restart point set it. Any other payload is walked past without effect. */
static uint32_t wave_script_seek(uint8_t *image, uint32_t script, uint32_t cursor) {
    while (script_entry_is_behind(image, script, cursor)) {
        uint8_t op = (uint8_t)(be16(image + addr_add(script, SCRIPT_ENTRY_PAYLOAD)) >> 8);

        if (op == SCRIPT_OP_SQUADRON_SPAWN_ON)
            image[A_squadron_spawn_enabled] = 1;
        else if (op == SCRIPT_OP_SQUADRON_SPAWN_OFF)
            image[A_squadron_spawn_enabled] = 0;
        script = addr_add(script, SCRIPT_ENTRY_BYTES);
    }
    return script;
}

/* `tst.b $19681 / bpl` — the loop leaves when bit 7, the fire button, is SET. That is a SIGN test
 * and not the equality `sched_wait8` wraps, so the poll and its cap are spelt here; the cap is the
 * kit's own, and it is OFF TARGET ONLY for include/input.h's reason.
 *
 * `rand16` inside the loop is what makes the number of passes observable: the generator state moves
 * once per iteration, so a port that spun a different number of times differs in the image as well
 * as in the poll count the harness compares. */
static void section_tail_wait_for_fire(uint8_t *image) {
    for (uint32_t poll = 0; ; poll++) {
        rand16(image);
        ikbd_send_cmd(IKBD_CMD_INTERROGATE_JOYSTICKS);
        if ((int8_t)sched_poll8(image, A_joystick_state, SECTION_TAIL_FIRE_WAIT_SITE) < 0)
            return;
#ifndef OS_NO_REFUSAL_TALLY
        if (poll + 1 >= OS_SCHED_POLL_MAX) {
            os_refused(0);
            return;
        }
#endif
    }
}

/* The per-life shelf, 0x10e4c..0x10f18. Every address is its owner's header's; the order is the
 * original's, including the two writes to `A_powerup_active_slot` that straddle the icon draw — it
 * is cleared, the icon is drawn from the cleared value, and only then is it set to 1. */
static void section_tail_reset_shelf(uint8_t *image) {
    /* `move.b #$1,14(a2)` and `#$1,58(a2)` off the player record: the ship and the SHADOW one
     * ENTITY_STRIDE after it, both brought back to life for the new section. */
    image[addr_add(A_player_record, ENTITY_ALIVE)] = 1;
    image[addr_add(A_player_record, ENTITY_STRIDE + ENTITY_ALIVE)] = 1;

    image[A_powerup_active_slot] = 0;
    hud_draw_weapon_icon(image, 1);      /* `move.b #$1,d0` — the RIGHT cell of the weapon pair */

    image[A_active_count_type32] = 0;
    image[A_active_count_bombs] = 0;
    image[A_active_count_seekers] = 0;
    image[A_active_bullets] = 0;
    image[A_shield_level] = 0;
    image[A_selected_weapon] = SECTION_TAIL_WEAPON_SLOTS;
    image[A_powerup_active_slot] = SECTION_TAIL_POWERUP_SLOT;
    wr16(image + A_shield_decay_timer, POWERUP_DECAY_TICKS);
    wr16(image + A_weapon_decay_timer, POWERUP_DECAY_TICKS);
    wr16(image + A_speed_decay_timer, POWERUP_DECAY_TICKS);
    image[A_power_gauge_display] = 0;
    image[A_panel_redraw_mask] = SECTION_TAIL_PANEL_MASK;
    wr16(image + A_panel_logo_countdown, SECTION_TAIL_LOGO_TICKS);
    image[A_powerup_flash_cursor] = 0;
    image[A_explosion_group_active_bits] = 0;
    image[A_mothership_wave_clear_count] = 0;
    image[A_seeker_lock_target_index] = 0;
    wr32(image + A_mothership_phase_timer, 0);
    image[A_ground_spawn_rnd_param] = SECTION_TAIL_GROUND_RND;
    image[A_boss_sequence_active] = 0;
    image[A_missile_lock_a] = 0;
    image[A_missile_lock_b] = 0;

    draw_lives_icons(image);
    image[A_enemy_seeker_cooldown] = SECTION_TAIL_GRACE_TICKS;
    image[A_section_end_delay_counter] = SECTION_TAIL_END_DELAY;
    status_panel_redraw_all(image);
}

void section_start_tail(uint8_t *image) {
    /* `move.l $18242,d7 / sub.l #$478ae,d7 / add.l #$24,d7` — the map cursor as an OFFSET, one
     * column on, which is what makes an entry sitting exactly at the cursor count as behind it. */
    uint32_t cursor = addr_add(be32(image + A_map_ptr) - A_map_unpacked, MAP_COLUMN_BYTES);
    uint8_t section = image[A_level_section];
    uint8_t palette_index = section_table_byte(image, A_section_palette_index_table);

    image[A_scroll_prefill_hide_screen] = 0;
    image[A_squadron_spawn_enabled] = 0;
    for (unsigned flag = 0; flag < SLOT_DIR_FLAGS_BYTES; flag++)
        image[A_slot_dir_flags + flag] = 0;

    /* THE TWO TABLES TAKE TWO DIFFERENT INDICES — the ground script's is the section's PALETTE byte
     * and the wave script's is the section number — which is what a candidate indexing both the same
     * way gets wrong on every section whose two indices differ. */
    wr32(image + A_ground_script_cursor,
         ground_script_seek(image, script_table_entry(image, A_event_script_a_table, palette_index),
                            cursor));
    wr32(image + A_wave_script_cursor,
         wave_script_seek(image, script_table_entry(image, A_event_script_b_table, section),
                          cursor));

    section_tail_reset_shelf(image);

    image[A_joystick_state] = 0;
    section_tail_wait_for_fire(image);
    /* D0 at this `bsr` is still the 0x16 the interrogate loop above put there — the send leaves it
     * alone and `rand16` only sets the word below it — so that byte is the channel. Named for where
     * it comes from rather than pretended to be a choice, exactly as BOOT_SOUND_CHANNEL_FROM_DBF is. */
    sound_start(image, SECTION_TAIL_SECTION_START_SFX, SECTION_TAIL_SOUND_CHANNEL_FROM_D0);

    /* `movem.l $19f66,#$00ff / movem.l #$00ff,$19f46` — the whole 32-byte row the next section
     * fades to, copied into the shadow the menu VBL uploads from. */
    boot_copy_longwords(image, A_palette_next, A_menu_palette,
                        SECTION_PALETTE_BYTES / PALETTE_LONG_BYTES);
    image[A_mothership_offscreen] = 0;
}

/* ================================================================================================
 * title_attract_loop — 0x12ac2..0x12c74, in four slices.
 *
 * `../names.txt` gives this an `fn` line, so unlike the boot chain it really is one routine with an
 * `rts` — but it cannot be run end to end for the boot's own reason: its prologue programs the MFP's
 * Timer B data register and then spins reading it back, twice, and the kit's seeded read model
 * refuses a read of an address the run itself has just written. So the prologue is two slices that
 * stop on the period write, and the body is a third and a fourth.
 * ============================================================================================= */
#define ATTRACT_VSYNC_WAIT_SITE_SETUP  0x12afau  /* the three `tst.b $198ab` the loop re-reads at */
#define ATTRACT_VSYNC_WAIT_SITE_ARMED  0x12b24u
#define ATTRACT_VSYNC_WAIT_SITE_FRAME  0x12bbcu
#define ATTRACT_KEY_1_WAIT_SITE 0x12c36u  /* `cmpi.b #$2,$19685` */
#define ATTRACT_KEY_2_WAIT_SITE 0x12c42u  /* `cmpi.b #$3,$19685` — a SECOND read of the same byte */
#define ATTRACT_FIRE_WAIT_SITE  0x12c5eu  /* `tst.b $19681` */

/* 0x12ac2..0x12b09 — the in-game handler pair back on their vectors, Timer B stopped, one frame
 * waited for, and the first of the two periods written. */
void attract_program_timer_b(uint8_t *image) {
    hw_write8(HW_MFP_IERA, 0);
    wr32(image + A_vector_vbl, A_vbl_isr);
    wr32(image + A_vector_timer_b, A_timer_b_isr);
    hw_write8(HW_MFP_TIMER_B_CONTROL, MFP_TIMER_B_STOPPED);
    shifter_clear_pen0();

    (void)boot_wait_one_frame(image, ATTRACT_VSYNC_WAIT_SITE_SETUP);
    hw_write8(HW_MFP_TIMER_B_DATA, MFP_TIMER_B_PERIOD_ATTRACT_SETUP);
}

/* 0x12b14..0x12b47 — Timer B started, another frame waited for, and then attract mode's OWN pair
 * installed with the period the colour bars run at. */
void attract_program_rasterbar_timer(uint8_t *image) {
    hw_write8(HW_MFP_TIMER_B_CONTROL, MFP_TIMER_B_EVENT_COUNT);
    (void)boot_wait_one_frame(image, ATTRACT_VSYNC_WAIT_SITE_ARMED);

    wr32(image + A_vector_vbl, A_attract_vbl_isr);
    wr32(image + A_vector_timer_b, A_attract_rasterbar_isr);
    hw_write8(HW_MFP_TIMER_B_DATA, MFP_TIMER_B_PERIOD_ATTRACT_BARS);
}

/* 0x12b52..0x12bb3 — the interrupts opened up, the bar list built out of its seven-group pattern,
 * the front-end palette uploaded, and the title page drawn behind it all. */
void attract_build_colour_bars(uint8_t *image) {
    uint32_t pattern = A_attract_bar_pattern;
    uint32_t pair = A_backdrop_page0;
    uint16_t hue = 0;

    hw_write8(HW_MFP_TIMER_B_CONTROL, MFP_TIMER_B_EVENT_COUNT);
    hw_write8(HW_MFP_IERA, MFP_IER_TIMER_B);
    hw_write8(HW_MFP_IMRA, MFP_IER_TIMER_B);

    /* Each group is (repeats - 1, scanlines) and emits that many identical-height bars, each one a
     * step further round the hue ramp. The ramp carries ACROSS the groups — `d3` is cleared once,
     * before the outer loop — and what it ends at is parked for the scroll below to carry on from. */
    for (unsigned group = 0; group < ATTRACT_BAR_GROUPS; group++) {
        unsigned bars = loop_passes((uint16_t)(be16(image + pattern) + 1u), COUNT_MASK_WORD);
        uint16_t scanlines = be16(image + addr_add(pattern, PALETTE_PEN_BYTES));

        pattern = addr_add(pattern, 2u * PALETTE_PEN_BYTES);
        for (unsigned bar = 0; bar < bars; bar++) {
            /* The count comes out of the image, so a pattern word of 0xffff would emit 65536 pairs
             * and write a quarter of a megabyte from `A_backdrop_page0`. The shipped pattern emits
             * seventeen (`test_the_bar_pattern_emits_more_pairs_than_the_scroll_moves` reads that
             * back off the image); this is the bound that keeps a seeded one from crashing the
             * worker where the oracle would simply run out of instructions. */
            if (!os_in_image(pair, ATTRACT_BAR_PAIR_BYTES))
                break;
            wr16(image + pair, scanlines);
            wr16(image + addr_add(pair, ATTRACT_BAR_COLOUR), hue);
            pair = addr_add(pair, ATTRACT_BAR_PAIR_BYTES);
            hue = (uint16_t)((hue + ATTRACT_HUE_STEP) & ATTRACT_HUE_MASK);
        }
    }
    wr16(image + A_attract_bar_hue, hue);

    shifter_upload_palette_longs(image, A_palette_frontend);
    title_screen_draw(image);
    image[A_attract_page_toggle] = 0;
}

/* Every second frame the whole colour column moves down one pair and a fresh hue goes in at the
 * top. Spelt downward because each store overwrites the source of the store after it — the
 * direction is the algorithm, exactly as src/irq.c's `rotate_cycle_words` is. */
static void attract_scroll_bar_colours(uint8_t *image) {
    uint32_t colour = addr_add(A_backdrop_page0, ATTRACT_BAR_COLOUR
                               + ATTRACT_BAR_SCROLL_PAIRS * ATTRACT_BAR_PAIR_BYTES);
    uint16_t hue;

    for (unsigned pair = 0; pair < ATTRACT_BAR_SCROLL_PAIRS; pair++) {
        wr16(image + colour,
             be16(image + addr_add(colour, (uint32_t)-(int32_t)ATTRACT_BAR_PAIR_BYTES)));
        colour = addr_add(colour, (uint32_t)-(int32_t)ATTRACT_BAR_PAIR_BYTES);
    }
    hue = be16(image + A_attract_bar_hue);
    wr16(image + colour, hue);
    wr16(image + A_attract_bar_hue, (uint16_t)((hue + ATTRACT_HUE_STEP) & ATTRACT_HUE_MASK));
}

/* The page behind the bars alternates, and the swap re-enters the loop BELOW the frame wait rather
 * than at the top — so the frame a page changes on has no vsync wait of its own. */
static void attract_next_page(uint8_t *image) {
    image[A_attract_page_toggle] ^= 1u;
    if (image[A_attract_page_toggle] != 0)
        role_of_honour_screen(image);
    else
        title_screen_draw(image);
    wr16(image + A_attract_page_timer, ATTRACT_PAGE_FRAMES);
}

/* 0x12bb4..0x12c74 — the loop, and its three exits.
 *
 * FOUR WAIT SITES, which is the kit's whole allowance, and every one of them is a read of a byte
 * `ikbd_acia_isr` writes or a VBL clears: the frame flag, the key byte twice (the two compares are
 * two reads, at two addresses), and the joystick. Nothing off target moves any of them, so each is a
 * declared store and the harness compares this side's polls against the oracle's arrivals site by
 * site.
 *
 * THE PLAYER COUNT IS SET TO TWO ON EVERY PASS and cut to one by two of the three exits, which is
 * why a candidate that only wrote it on the exits would still agree: the write is inside the loop.
 */
void attract_wait_for_start(uint8_t *image) {
    /* THE CAP IS NOT OPTIONAL HERE, and it is not the original's: every exit below is a
     * `sched_poll8`, so a candidate whose compare is wrong — or a mutant of one — would spin for
     * ever and the suite would HANG rather than come back red, which is worse evidence. It is
     * OFF TARGET ONLY for include/input.h's reason, and it is the kit's own bound so this loop and
     * `section_tail_wait_for_fire` give up after the same number of frames. */
    for (uint32_t frame = 0; ; frame++) {
        if (!boot_wait_one_frame(image, ATTRACT_VSYNC_WAIT_SITE_FRAME))
            return;                      /* the frame wait was refused; sched.h: honour the 0 */

        image[A_attract_bar_scroll_timer]--;
        if (image[A_attract_bar_scroll_timer] == 0) {
            image[A_attract_bar_scroll_timer] = ATTRACT_BAR_SCROLL_PERIOD;
            attract_scroll_bar_colours(image);
        }
        /* The list the Timer B walks is a COPY, taken once a frame, so the handler never sees the
         * scroll half done. include/irq.h owns the destination. */
        boot_copy_longwords(image, A_backdrop_page0, A_attract_raster_list, ATTRACT_BAR_LIST_LONGS);

        wr16(image + A_attract_page_timer, (uint16_t)(be16(image + A_attract_page_timer) - 1u));
        if (be16(image + A_attract_page_timer) == 0)
            attract_next_page(image);

        rand16(image);
        image[A_player_count] = ATTRACT_PLAYERS_DEFAULT;
        if (sched_poll8(image, A_key_scancode, ATTRACT_KEY_1_WAIT_SITE) == KEY_SCANCODE_1) {
            image[A_player_count] = ATTRACT_PLAYERS_ONE;
            return;
        }
        if (sched_poll8(image, A_key_scancode, ATTRACT_KEY_2_WAIT_SITE) == KEY_SCANCODE_2)
            return;   /* ...and the count stays at the two the pass above just wrote */

        ikbd_send_cmd(IKBD_CMD_INTERROGATE_JOYSTICKS);
        /* `move.w #$64,d7 / dbf d7,*` sits here: 101 passes of an empty loop, waiting for the
         * controller's reply to arrive. It touches no memory and is not reconstructed. */
        if ((int8_t)sched_poll8(image, A_joystick_state, ATTRACT_FIRE_WAIT_SITE) < 0) {
            image[A_player_count] = ATTRACT_PLAYERS_ONE;
            return;
        }
#ifndef OS_NO_REFUSAL_TALLY
        if (frame + 1 >= OS_SCHED_POLL_MAX) {
            os_refused(0);
            return;
        }
#endif
    }
}

/* ================================================================================================
 * Glue. None of these slices takes a register argument — every address they touch is an immediate
 * or comes out of a global — so the glue is a pass-through, except where the slice's answer is a
 * register rather than memory.
 * ============================================================================================= */
uint32_t g_boot_enter_supervisor(uint8_t *image) {
    (void)image;                     /* Super(0) reads and writes no image byte */
    return boot_enter_supervisor();
}

void g_boot_save_vbl_vector(uint8_t *image) {
    boot_save_vbl_vector(image);
}

/* The mask sink is cleared before the call rather than accumulated, so one case's mask can never
 * stand in for the next one's. */
void g_boot_load_title_assets(uint8_t *image) {
    init_shifter_sink_reset();
    boot_load_title_assets(image);
}

void g_section_advance(uint8_t *image) {
    section_advance(image);
}

/* Returns 1 when the flow falls into the asset load and 0 when it jumps to the section start. */
uint32_t g_section_reload_needed(uint8_t *image) {
    return section_reload_needed(image);
}

/* Returns 1 when the whole map-section path ran, 0 when the section's type byte sent the original
 * into `asteroids_load_and_build` — the arm this reconstruction stops at. */
uint32_t g_section_load_assets(uint8_t *image) {
    return section_load_assets(image);
}

void g_section_reload_intro_screens(uint8_t *image) {
    section_reload_intro_screens(image);
}

void g_section_restart_prologue(uint8_t *image) {
    section_restart_prologue(image);
}

void g_section_start_prefill(uint8_t *image) {
    section_start_prefill(image);
}

/* The IKBD send takes its command in D0, but the two calls this slice makes are its own immediates
 * — so like every other slice here the glue is a pass-through. */
void g_boot_configure_ikbd(uint8_t *image) {
    (void)image;                     /* both commands are ledgered stores, not image bytes */
    boot_configure_ikbd();
}

void g_boot_load_gameplay_assets(uint8_t *image) {
    boot_load_gameplay_assets(image);
}

void g_boot_install_ikbd_isr(uint8_t *image) {
    boot_install_ikbd_isr(image);
}

/* Returns 1 when the panel master was rebuilt and the tune restarted, 0 on the session's first
 * pass — the two arms of `tst.b $1991c`. */
uint32_t g_boot_front_end_prologue(uint8_t *image) {
    return boot_front_end_prologue(image);
}

void g_boot_stage_frontend_screens(uint8_t *image) {
    boot_stage_frontend_screens(image);
}

void g_boot_program_timer_b(uint8_t *image) {
    boot_program_timer_b(image);
}

void g_boot_program_raster_timer(uint8_t *image) {
    boot_program_raster_timer(image);
}

void g_boot_enable_interrupts(uint8_t *image) {
    (void)image;                     /* five ledgered hardware stores and no image byte at all */
    boot_enable_interrupts();
}

void g_boot_new_game_records(uint8_t *image) {
    boot_new_game_records(image);
}

void g_section_start_tail(uint8_t *image) {
    section_start_tail(image);
}

void g_attract_program_timer_b(uint8_t *image) {
    attract_program_timer_b(image);
}

void g_attract_program_rasterbar_timer(uint8_t *image) {
    attract_program_rasterbar_timer(image);
}

void g_attract_build_colour_bars(uint8_t *image) {
    attract_build_colour_bars(image);
}

void g_attract_wait_for_start(uint8_t *image) {
    attract_wait_for_start(image);
}
