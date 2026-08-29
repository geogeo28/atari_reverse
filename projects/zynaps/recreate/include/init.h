/* init.h — the boot prologue and the level-section flow in src/init.c. Subsystem: init.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 *
 * THIS SUBSYSTEM IS A FLOW, NOT A SET OF FUNCTIONS. `_start` @ 0x10000 never returns, and neither
 * does the section chain it ends in: 0x10814 falls into 0x1083a, which either falls into the asset
 * load or branches to 0x10b6e, which runs on into the frame loop at 0x10f4e. There is not an `rts`
 * between them, and ../../names.txt names only the entry (`fn 0x10000 _start`); the rest are `bra`
 * targets with `cmt` lines.
 *
 * So each routine here is a SLICE — a named address range the differential enters at and stops at,
 * `docs/agent-playbook.md` §5's checkpoint-PC and mid-entry-slice techniques — and each carries the
 * range it covers in its own comment. The slice names are THIS RECONSTRUCTION'S, proposed for the
 * map in ../out/names_init.txt rather than assumed; a reader grepping ../../names.txt for one will
 * not find it, and that is what the proposal file is for.
 *
 * WHAT THE SLICES DO NOT COVER is written up in STATUS.md rather than papered over: the two
 * `ikbd_send_cmd` calls (0x1001c, 0x10024) busy-wait on the ACIA at $fffc00, which the kit does not
 * model; the Line-A opcode at 0x10010 traps in the oracle; and three stretches call routines other
 * subsystems own and have not ported yet.
 */
#ifndef ZYNAPS_INIT_H
#define ZYNAPS_INIT_H

#include <stdint.h>

/* ================================================================================================
 * The 68000 exception vectors `_start` installs, and the TOS one it saves first. Both vector
 * addresses are BELOW the 0x10000 load base and inside the image, so the two stores are ordinary
 * diffable memory — unlike everything else this file touches at hardware addresses.
 * ============================================================================================= */
#define A_vector_vbl      0x70u   /* `move.l #$10776,$70.l` — names.txt `vbl_isr` */
#define A_vector_timer_b 0x120u   /* `move.l #$10782,$120.l` — names.txt `timer_b_isr` */
#define A_vbl_isr        0x10776u
#define A_timer_b_isr    0x10782u
#define A_saved_tos_vbl_vector 0x195d0u   /* names.txt — where the TOS vector is parked */

/* ================================================================================================
 * THE SHIFTER MODE BYTE IS NOT AN IMAGE BYTE, exactly as include/video.h's palette and screen-base
 * writes are not. `_start` selects low resolution with `andi.b #$fc,$ff8260` — a read-modify-write
 * of a register at an address far above the 1 MiB image — so off target there is nothing to store
 * to and the sink below records the request instead. What it can record is the MASK and the fact
 * that the write happened; what it cannot record is the byte that came back from the read, because
 * the oracle has no shifter to read from either. $ff8260 gets no `A_*` name for that reason: there
 * is no address here for anything to reach, and a name would read as one.
 * ============================================================================================= */
#define SHIFTER_MODE_RESOLUTION_MASK 0xfcu   /* `andi.b #$fc` — clears the two resolution bits */

/* ================================================================================================
 * The boot sequence's own data. `_start` reads every graphic through `load_file` (src/fileio.c)
 * from the 0-terminated lowercase filename table at 0x19686, so each slice's table below is a list
 * of (filename address, destination, length) triples read off the `lea`/`move.l` triples above each
 * `bsr`.
 * ============================================================================================= */
#define A_filename_zynpic_pic   0x19692u  /* names.txt, and the six below it likewise */
#define A_filename_power_dat    0x1969du
#define A_filename_alien_dat    0x196b0u
#define A_filename_myship_dat   0x196bbu
#define A_filename_status_pi1   0x196c6u
#define A_filename_bullet_dat   0x196d1u
#define A_filename_explode_dat  0x196dcu
#define A_filename_mother_dat   0x196e8u
#define A_filename_gemgraf_dat  0x196f4u
#define A_filename_spinners_dat 0x19700u
#define A_filename_missile_dat  0x1970du
#define A_filename_gndtarg1_dat 0x19734u
#define A_filename_rocket_dat   0x19758u
#define A_filename_lev_map      0x197d9u
#define A_filename_zyn_dat      0x197e2u

/* WHICH BYTE OF EACH FILENAME THE SECTION FLOW PATCHES. The variant letter or digit is written into
 * the string where it lies (`move.b <table>(a0,d0.w),$196b5.l` and its four siblings), so the text
 * segment is program STATE here and not read-only data — which is why the asset slice's diff covers
 * the filename table as well as the buffers it fills. Each offset is the index of the variable
 * character inside its own name: "alien_.dat", "mother_.dat", "missile_.dat", "lev_.map",
 * "zyn_.dat". */
#define FILENAME_ALIEN_VARIANT    5u
#define FILENAME_MOTHER_VARIANT   6u
#define FILENAME_MISSILE_VARIANT  7u
#define FILENAME_LEV_VARIANT      3u
#define FILENAME_ZYN_VARIANT      3u

/* The title picture is read as one whole 320x200 four-plane frame, so its length is `SCREEN_BYTES`
 * (include/video.h) and not a second 0x7d00 written out here. */

/* THE TWO LEVEL READS ARE CAPS, NOT LENGTHS — include/scroll.h's note on `A_tile_set_base` is the
 * one home for that finding, and these are the two figures it names. The map cap is 0x3840, which
 * happens to equal `MAP_COLUMNS * MAP_COLUMN_BYTES` and must NOT be written as that product: the
 * unpacked map's size and the compressed stream's read cap are two different facts that agree by
 * accident (the twelve shipped LEV*.MAP files are 4,118 to 8,718 bytes). */
#define SECTION_MAP_READ_CAP      0x3840u
#define SECTION_TILE_SET_READ_CAP 0xea60u

/* ================================================================================================
 * The level-section flow's own globals and its sixteen per-section tables.
 * ============================================================================================= */
#define A_level_section        0x19895u  /* names.txt — 0..15, the section being played */
#define A_level_section_loaded 0x19913u  /* names.txt — the section whose assets are in RAM */
#define A_asteroid_section_flag 0x198fdu /* names.txt # ctx */
#define A_mothership_index     0x1987cu  /* names.txt */
#define A_section_ground_target_flag 0x19897u  /* names.txt */
#define A_palette_next         0x19f66u  /* names.txt — the 32-byte row the next section fades to */
#define A_palette_per_section_table 0x18fe4u   /* names.txt — 16 rows of 32 bytes */
/* The ONE 32-byte row an asteroid-field section takes, instead of a row of the table above:
 * `movem.l $19638,#$00ff` straight into `A_palette_next`. names.txt names it. */
#define A_palette_asteroid 0x19638u

#define SECTION_COUNT 0x10u              /* `cmpi.b #$10,$19895` + wrap to 0 */
#define SECTION_TYPE_ASTEROID 0x71u      /* `cmp.b #$71,d0` — 'q' in the section-type table */
#define SECTION_PALETTE_BYTES 0x20u      /* `lsl.l #5,d0` then `movem.l` of eight longwords */

/* The sixteen-byte per-section tables, all indexed by `A_level_section`. names.txt names all but
 * the last two; those two are this reconstruction's names, proposed in ../out/names_init.txt. */
#define A_alien_variant_table   0x197fcu
#define A_alien2_variant_table  0x1980cu
#define A_mothership_variant_table 0x1981cu
#define A_missile_variant_table 0x197ebu
#define A_section_param_a_table 0x1982cu
#define A_section_param_b_table 0x1983cu
#define A_section_type_table    0x1984cu
#define A_zyn_variant_table     0x1985cu
#define A_section_palette_index_table 0x1986cu
/* Indexed by the PALETTE index above rather than by the section, and the flag it yields decides
 * which ground-target graphic the section loads. No `var` line in ../../names.txt. */
#define A_ground_target_by_palette_table 0x19898u
/* Two per-section bytes the flow copies out for other subsystems to read; neither is named in
 * ../../names.txt and neither is read by anything this slice covers, so the names say WHERE they
 * come from and claim nothing about what they mean. */
#define A_section_param_a       0x1990fu
#define A_section_param_b       0x19910u

/* `sub.b #$31,d1` — the mothership variant table holds ASCII digits, and the index the game keeps
 * beside the filename is that digit less '1'. */
#define MOTHERSHIP_VARIANT_DIGIT_BASE 0x31u

/* ================================================================================================
 * The section restart prologue's own resets.
 *
 * Most of what the 0xd0 bytes at 0x10b6e touch belongs to other subsystems and is included from
 * their headers — the entity table and the ship records (player), the asteroid records and the
 * squadron counters (enemy), the two launch counters and the death flags (weapon), the panel and
 * the PREPARE FOR COMBAT banner (hud), the boss-ready flag (mothership). Only the three below have
 * no home anywhere, and `../out/globals.tsv` gives none of them an owner, so the house rule that
 * whoever reads it names it puts them here. The first two are BORROWED BY SUBJECT rather than by
 * the file — a keyboard byte and a boss byte in the boot header — and STATUS.md's "## Borrowed
 * globals" carries both debts. The third item below is not a global at all and needs no home.
 * ============================================================================================= */
#define A_key_scancode 0x19685u        /* names.txt — the ACIA ISR's last scancode (irq by subject) */
#define A_mothership_pending 0x198afu  /* names.txt — mothership by subject */
/* NOT A GLOBAL AT ALL, and that is the finding: `clr.b $17de0` is `A_entity_gunsight` (weapon.h,
 * 0x17dd2 = entity slot 19) plus `ENTITY_ALIVE`. The sweep before it clears slots 0..17, so the
 * stray clear skips slot 18 and takes slot 19 — which leaves the ship's SHADOW record, slot 18, as
 * the one entity the prologue does not kill. */

/* The two positions the prologue parks the ship's pair at. The SPRITE it points them back to is
 * `BOOT_SHIP_SOURCE` (src/init.c) and the stride to the shadow's is `include/sprite.h`'s
 * SHIP_SPRITE_GAP — the same 0x640 the boot's de-interleaver uses, and names.txt's own "frame
 * stride 0x640" on 0x111f4 — so neither is a constant of this file. */
#define SECTION_RESTART_SHIP_X 0x40u
#define SECTION_RESTART_SHADOW_X 0x50u
#define SECTION_RESTART_SHIP_Y 0x64u
#define SECTION_RESTART_SHIP_ROWS 0x14u
/* TWO `move.w #$11,d0` + dbf sweeps, and their eighteens are UNRELATED facts that happen to agree:
 * the first is entity slots 0..17, which is one short of the 20-slot table (slot 18 survives, 19 is
 * cleared separately); the second is the WHOLE of `include/enemy.h`'s 6x3 `A_asteroid_records`
 * array. Two names, so a later change to either bound cannot move the other. The asteroid one is
 * named here only because that header belongs to another agent this wave — like SQUADRON_MARKS
 * below, it is a COUNT rather than an address, so STATUS.md's borrowed-globals table does not
 * cover it, and moving it beside the array it measures is the migration. */
#define SECTION_RESTART_KILL_SLOTS 18u
#define SECTION_RESTART_ASTEROID_RECORDS 18u
/* The FIRST `move.w #$5,d0` + dbf clears six TYPE bytes, and six is `include/weapon.h`'s
 * PLAYER_SHOT_SLOTS — the same six records, so it is read from there rather than named again. */
/* ...and the second is the length of `include/enemy.h`'s `A_squadron_kill_counters` array, named
 * here for the reason given above. */
#define SQUADRON_MARKS 6u
/* `move.b #$2` into EACH of the two launch counters — the number of launches they are restocked
 * with, NOT how many counters there are. The two figures are both 2 by coincidence. */
#define SECTION_RESTART_LAUNCH_STOCK 2u

/* ================================================================================================
 * The section restart search, and the page pre-fill that follows it.
 * ============================================================================================= */
#define A_section_restart_table 0x19e84u  /* names.txt — 4 words per section, scanned BACKWARDS */
#define SECTION_RESTART_ENTRY_BYTES 8u    /* `lsl.w #3,d7` — the stride into it */
#define A_scroll_pos            0x195ccu  /* names.txt — (map_offset / MAP_COLUMN_BYTES) * 8 */
#define A_map_offset            0x1823eu  /* names.txt — map_ptr less A_map_unpacked */
#define A_map_ptr               0x18242u  /* names.txt */
#define A_map_page              0x198a5u  /* names.txt — 0..7, which of the eight pages */
#define A_map_page_ptr          0x17986u  /* names.txt — the page that one names */
#define A_map_page_table        0x1798au  /* names.txt — the eight page pointers */
#define A_map_column            0x198a6u  /* names.txt — 0..19, the 16-pixel column phase */
#define MAP_PAGES 8u                      /* `cmpi.b #$8,$198a5` */
/* `cmp.l #$47b7e,d5` then `sub.l #$2d0,d5` — the map cursor is pulled back twenty columns before
 * the restart search, but only once it is past the level's twentieth column. */
#define SECTION_REWIND_FLOOR 0x47b7eu
#define SECTION_REWIND_BYTES 0x2d0u
#define SECTION_PREFILL_COLUMNS 0xa0u     /* `move.w #$9f,d7` + dbf — 160 columns pre-filled */

/* ================================================================================================
 * Prototypes. Each is one slice; the range it covers is in its comment in src/init.c.
 * ============================================================================================= */
uint32_t boot_enter_supervisor(void);
void boot_save_vbl_vector(uint8_t *image);
void boot_load_title_assets(uint8_t *image);
void section_advance(uint8_t *image);
unsigned section_reload_needed(uint8_t *image);
/* 1 when the whole map-section path ran, 0 when the section's type byte took the ASTEROID arm at
 * 0x109e2. Both arms are reconstructed now, so the answer names which one ran rather than which one
 * the reconstruction could follow — a case still checks it, because the two disagree about
 * `A_asteroid_section_flag` and `section_start_prefill` reads that byte. */
unsigned section_load_assets(uint8_t *image);
/* The two front-end calls at 0x1085a..0x10862, between the reload gate and the asset load. Named
 * for what it does rather than for where it sits; STATUS.md's row called it "the section-advance
 * tail", which is its position in the chain and not its job. */
void section_reload_intro_screens(uint8_t *image);
/* 0x10b6e..0x10c4e — the per-life reset every section start runs through, whether it reloaded
 * assets or not. */
void section_restart_prologue(uint8_t *image);
void section_start_prefill(uint8_t *image);

/* The boot's off-image publish ledger (see above): what the last `boot_load_title_assets` asked the
 * shifter for, how often, and how many title-palette uploads it made — the last of those being the
 * only call in the slice that writes no image byte, so a count is the only thing that can hold it. */
void init_shifter_sink_reset(void);
uint8_t init_shifter_mode_mask_written(void);
uint32_t init_shifter_mode_writes(void);
uint32_t init_palette_uploads(void);

#endif /* ZYNAPS_INIT_H */
