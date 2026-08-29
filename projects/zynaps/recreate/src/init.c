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
#include "machine.h"
#include "hw.h"        /* the kit's hardware write ledger — include/init.h says what it pins */
#include "os.h"

#include "entity.h"
#include "fileio.h"
#include "init.h"
#include "enemy.h"
#include "hud.h"
#include "mothership.h"
#include "scroll.h"
#include "sound.h"
#include "sprite.h"
#include "player.h"
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

/* The five loads at 0x10136..0x101a0, as (filename, destination, length). The four before them are
 * spelt out in the body because each is followed by work that reads what it just loaded. */
static const struct { uint32_t name, dst, length; } BOOT_LATE_LOADS[] = {
    { A_filename_status_pi1,   0x41eaeu, 0x2120u },
    { A_filename_bullet_dat,   0x6e6eeu, 0x0050u },
    { A_filename_explode_dat,  0x5cf7eu, 0x0780u },
    { A_filename_gemgraf_dat,  0x5f3beu, 0x0280u },
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
