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
 * WHAT THE SLICES DO NOT COVER is written up in STATUS.md rather than papered over, and it is FIVE
 * SHORT RANGES now rather than three long ones. The Line-A opcode at 0x10010 traps in the oracle and
 * is modelled as a no-op; four `cmpi.b #$xx,$fffa21 / bne` read-back spins (two here, two in
 * `title_attract_loop`) READ a register the run itself has just written, which the kit's seeded read
 * model refuses as a stale seed and cannot serve — so the slices stop at the write and resume at the
 * instruction after the spin, twenty bytes in all. Every hardware STORE is inside a verified range.
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
 * stores are not. `_start` selects low resolution with `andi.b #$fc,$ff8260` — a read-modify-write
 * of a register far above the 1 MiB image — and the store half now goes through the kit's hardware
 * write ledger (`hw_write8`, tools/recreate_kit/include/hw.h), which compares the address, the
 * width and the value against the oracle's.
 *
 * WHAT THAT LEAVES, AND WHY THE MASK KEEPS A SINK OF ITS OWN. The oracle's READ of $ff8260 answers
 * a fabricated 0 — the address is not in the kit's seeded READ set — so both sides store `0 & mask`
 * and the stored value is 0 whatever the mask is. The ledger therefore holds that the store
 * happened, at that register, one byte wide; it cannot hold the mask. The one-byte sink declared at
 * the bottom of this header is what does, and that is the whole of what it is now for.
 *
 * IT IS ALSO AN ON-TARGET DEFECT, not merely an unpinned byte, and this is the place that says so.
 * `andi.b #$fc,$ff8260` preserves six bits of a register a Zynaps build for the real Atari would be
 * writing for real; storing `0 & mask` clears them. A target build must give the address a read —
 * the kit's seeded READ set, or its own code — rather than compile src/init.c's expression. The kit
 * states the general rule once, in tools/recreate_kit/include/hw.h ("WHAT THIS SEAM DOES NOT GIVE
 * YOU IS A READ-MODIFY-WRITE"); STATUS.md carries this instance.
 * ============================================================================================= */
#define HW_SHIFTER_MODE 0xff8260u            /* the resolution byte; a REGISTER, not an image address */
#define SHIFTER_MODE_RESOLUTION_MASK 0xfcu   /* `andi.b #$fc` — clears the two resolution bits */
/* What the oracle's read of an UNMODELED hardware register answers, which is the other operand of
 * the `andi.b` above. Named rather than written as a bare 0 because it is a fact about the harness
 * and not about the game: were $ff8260 ever added to the kit's seeded READ set, this is the line
 * that would become a `hw_read8` call. */
#define SHIFTER_MODE_UNMODELED_READ 0u

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
/* BORROWED: `A_key_scancode` is include/irq.h's now — `ikbd_acia_isr` is what writes it, and this
 * flow only clears it. It used to be defined here, borrowed by subject while nothing in the port
 * wrote it; STATUS.md's "## Borrowed globals" carries the debt the other way round now. */
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
 * boot_configure_ikbd — 0x1001c..0x1002c.
 *
 * Two commands to the keyboard controller, through `ikbd_send_cmd` (src/input.c). The second is the
 * one the whole front end depends on: it takes the joysticks OUT of auto-reporting, so a stick's
 * state only arrives when the game asks for it with 0x16 — which is what `title_attract_loop` and
 * the section-start tail do, and why `ikbd_acia_isr`'s packet path is entered at all.
 * ============================================================================================= */
#define IKBD_CMD_DISABLE_MOUSE 0x12u
#define IKBD_CMD_JOYSTICK_INTERROGATE_MODE 0x15u
/* `move.b #$16,d0` at 0x10f22 and `move.w #$16,d0` at 0x12c4e — the same command byte from two
 * different widths, since `ikbd_send_cmd` sends the low byte either way. */
#define IKBD_CMD_INTERROGATE_JOYSTICKS 0x16u

/* ================================================================================================
 * boot_load_gameplay_assets — 0x101ba..0x104c8: the other fourteen files, and the banks built from
 * them.
 *
 * The filename table at 0x19686 again (names.txt names every string). Unlike the section flow's,
 * none of these is patched: they are constants in the table and the loads read them as they stand.
 * ============================================================================================= */
#define A_filename_smallexp_dat 0x1971au
#define A_filename_newbuls2_dat 0x19727u
#define A_filename_seeker2_dat  0x19741u
#define A_filename_alseek_dat   0x19763u
#define A_filename_altexpl_dat  0x1976eu
#define A_filename_newbomb_dat  0x1977au
#define A_filename_gunsight_dat 0x19786u
#define A_filename_sweap_dat    0x19793u
#define A_filename_ssweap_dat   0x1979du
#define A_filename_smlogos_dat  0x197a8u
#define A_filename_extchars_dat 0x197b4u
#define A_filename_lifegra_dat  0x197c1u
#define A_filename_zynlogo_dat  0x19686u
#define A_filename_hewlogo_dat  0x197cdu

/* The two twelve-entry pointer tables the boot's last preshift pass walks. The FIRST is
 * include/enemy.h's `A_explosion_small_frame_ptrs`, included from there; the second has no owner —
 * ../out/globals.tsv files it under `sprite` and include/sprite.h does not name it, so the house
 * rule that whoever reads it names it puts it here and STATUS.md's "## Borrowed globals" carries the
 * debt. Both are read as tables of destinations, never dereferenced for their content. */
#define A_explosion_large_frame_ptrs 0x1922cu  /* names.txt # ctx */
#define EXPLOSION_FRAME_PTRS 12u               /* `move.w #$b,d6` + dbf, over both tables */

/* ================================================================================================
 * boot_install_ikbd_isr — 0x104c8..0x10500.
 *
 * The third vector the boot installs, and the only one that is not a VBL or a Timer B. It goes in
 * with the ACIA's own state cleared first, so a keystroke that arrives between the store and the
 * first frame lands in a buffer that means something. Every global here is include/irq.h's.
 * ============================================================================================= */
#define A_vector_acia   0x118u    /* `move.l #$14456,$118.l` — 68000 autovector 6 (the MFP) */
#define A_ikbd_acia_isr 0x14456u  /* names.txt; src/irq.c */

/* ================================================================================================
 * boot_front_end_prologue — 0x10500..0x10520, and the title/attract call it ends at.
 *
 * The boot reaches this twice over a session: the FIRST time `game_initialised` is still 0 and the
 * whole panel-master build is skipped, and every time after a game it is 1 and the panel is rebuilt
 * and the title tune restarted. The two arms are two checkpoints.
 * ============================================================================================= */
#define A_game_initialised 0x1991cu  /* names.txt — 0 on the very first pass, 1 for ever after */
#define A_player_count     0x1991du  /* names.txt — 1 or 2, chosen by the attract loop's menu */
#define A_player_records   0x19f02u  /* names.txt — two records, PLAYER_RECORD_BYTES apart */

/* `moveq #$b,d1` — the same title tune `boot_load_title_assets` starts, restarted here.
 * Its CHANNEL is D0, and at this call site D0 is whatever `status_panel_build_master` left: that
 * routine ends `move.l (a0)+,(a2)+ / dbf d0` and a `dbf` that falls through leaves its counter at
 * 0xffff, so the low byte is 0xff. src/sound.c's own battery drives that code, so this names where
 * the 0xff comes from rather than pretending the call site chose it. */
#define BOOT_SOUND_CHANNEL_FROM_DBF 0xffu

/* ================================================================================================
 * The two player records the boot tail builds, and the fields it copies out of the live one.
 *
 * Fourteen bytes each, and the ONE asymmetry between them is deliberate: player 1's section byte is
 * 0xff where player 2's is 0. `section_advance` increments the byte before it compares, so 0xff
 * becomes section 0 — which is how a fresh game starts at the first section without the boot ever
 * writing a 0 that a reload gate could mistake for "already loaded".
 * ============================================================================================= */
#define PLAYER_RECORD_BYTES 0x0eu
#define PLAYER_RECORD_SCORE      0x00u  /* .l — copied to score.h's A_player_score_bcd */
#define PLAYER_RECORD_LIVES      0x04u  /* .b — ...to hud.h's A_lives */
#define PLAYER_RECORD_SECTION    0x05u  /* .b — ...to A_level_section above */
#define PLAYER_RECORD_MAP_PTR    0x06u  /* .l — NOT copied out; the tail's `lea 4(a0),a0` skips it */
#define PLAYER_RECORD_POWERUP    0x0au  /* .b — ...to hud.h's A_powerup_cursor */
#define PLAYER_RECORD_WEAPON     0x0bu  /* .b — ...to player.h's A_weapon_power_level */
#define PLAYER_RECORD_SPEED      0x0cu  /* .b — ...to player.h's A_ship_speed_level */
/* Cleared by the build and read by nothing this reconstruction has ported, so it is named for its
 * OFFSET and not for a meaning: the last `clr.b (a0)+` of each record. */
#define PLAYER_RECORD_PAD        0x0du
#define PLAYER_RECORD_START_LIVES   3u
#define PLAYER_RECORD_START_SECTION 0xffu  /* player 1 only — see the note above */
#define PLAYER_RECORD_START_WEAPON  2u

/* The two word clears at 0x10500 and 0x10506. Both land INSIDE the records above — record 1's
 * power-up/weapon pair and record 2's map pointer — and the tail at 0x10792 overwrites all four
 * bytes before anything reads them, so what they are FOR is not recovered. Spelt as offsets from
 * the record base because that is where they land, and stated here rather than left as two bare
 * addresses that look like globals of their own. */
#define BOOT_PREATTRACT_CLEAR_A 0x0au
#define BOOT_PREATTRACT_CLEAR_B 0x16u

/* ================================================================================================
 * boot_program_timer_b / boot_program_raster_timer / boot_enable_interrupts — 0x105c6..0x1069e.
 *
 * The MFP is programmed in two steps and the second overwrites the first, which is the whole shape:
 * Timer B is started at one period with the plain handlers on it, the boot waits a frame, and then
 * it is restarted at another period with the raster-split pair. `vbl_menu` goes on the VBL both
 * times; between the two, `vbl_isr` / `timer_b_isr` are installed and then replaced.
 * ============================================================================================= */
#define HW_MFP_IERA     0xfffa07u  /* interrupt enable A; bit 0 is Timer B */
#define HW_MFP_IMRA     0xfffa13u  /* ...and its mask */
#define HW_MFP_IERB     0xfffa09u  /* interrupt enable B; bit 6 is the keyboard ACIA */
#define HW_MFP_IMRB     0xfffa15u  /* ...and its mask */
#define HW_MFP_TIMER_B_CONTROL 0xfffa1bu
#define HW_MFP_TIMER_B_DATA    0xfffa21u
#define MFP_IER_TIMER_B    0x01u   /* `move.b #$1,$fffa07` / `$fffa13` */
/* The bit `bset #6,$fffa09` and `$fffa15` set is include/irq.h's `MFP_ACIA_CHANNEL_BIT` — the same
 * MFP channel the ACIA handler acknowledges, so it is included from there rather than named twice. */
#define MFP_TIMER_B_STOPPED 0x00u  /* `move.b #$0,$fffa1b` */
#define MFP_TIMER_B_EVENT_COUNT 0x08u  /* `move.b #$8,$fffa1b` — count HBLs, not a prescaled clock */
/* The two Timer B periods, in scanlines. The first pair of handlers runs at 0xac and the raster
 * split at 0xc8, and the two are what the read-back spins between them confirm. */
#define MFP_TIMER_B_PERIOD_PLAIN  0xacu
#define MFP_TIMER_B_PERIOD_RASTER 0xc8u

#define A_vbl_menu             0x13c26u  /* names.txt; src/irq.c */
#define A_timer_b_raster_isr   0x106aeu  /* names.txt; src/irq.c */
#define A_starfield_layer2_phase     0x198a9u  /* names.txt */
#define A_starfield_layer3_countdown 0x198aau  /* names.txt */
#define STARFIELD_LAYER3_PERIOD 3u   /* `move.b #$3,$198aa` */

/* ================================================================================================
 * boot_stage_frontend_screens — 0x10524..0x105c6.
 *
 * Both framebuffers cleared, the panel stamped into each of them out of the master STATUS.PI1 has
 * been unpacked into, and then three strips of that panel carved back out for later repaints. Every
 * address and every geometry figure below belongs to include/hud.h, which owns the panel; only the
 * loop's own shape is this file's, and the one thing it needs to say is that the two buffers here
 * are the HARD-CODED addresses (`lea $70300,a0`) rather than the pointers `screen_back`/
 * `screen_front` hold — the boot has just fixed those to the same two values, so it is the same
 * memory either way, and the instruction is what is transcribed.
 * ============================================================================================= */

/* ================================================================================================
 * section_start_tail — 0x10d96..0x10f4e: the last stretch before the frame loop.
 *
 * Two script cursors are seeked to the section's own restart point, a shelf of per-life state is
 * reset, the panel is repainted, and then the game WAITS FOR THE PLAYER'S FIRE BUTTON — a poll of
 * the byte `ikbd_acia_isr` writes, with an `ikbd_send_cmd(0x16)` on every pass to ask for it.
 * ============================================================================================= */
/* The two event-script tables, each sixteen longword pointers into the script data. The FIRST is
 * indexed by the section's PALETTE index and the second by the section number — two different
 * indices into two tables of the same shape, which is the kind of thing a reader has to be told. */
#define A_event_script_a_table 0x182d2u  /* names.txt; indexed by A_section_palette_index_table's byte */
#define A_event_script_b_table 0x18306u  /* names.txt; indexed by A_level_section */
#define SCRIPT_TABLE_ENTRY_BYTES 4u      /* `lsl.w #2,d1` into both */
/* Each script entry is four bytes: a word offset into the map, then two bytes of payload. The scan
 * walks forward until the offset passes the cursor, so the tables are in ascending order. */
#define SCRIPT_ENTRY_BYTES 4u
#define SCRIPT_ENTRY_PAYLOAD 2u
/* The two payload opcodes the WAVE-script scan acts on as it walks past them — the second of the two
 * seeks, the one whose result lands in `A_wave_script_cursor`. 0x0c turns squadron spawning on and
 * 0x0d turns it off, so the flag ends up in whatever state the last entry BEFORE the restart point
 * left it. The GROUND scan reads nothing out of the entries it passes, and nothing else in either
 * walk has an effect. */
#define SCRIPT_OP_SQUADRON_SPAWN_ON  0x0cu
#define SCRIPT_OP_SQUADRON_SPAWN_OFF 0x0du
/* `add.l #$24,d7` — the scan compares against the map cursor one COLUMN on, so an entry exactly at
 * the cursor is already behind it. MAP_COLUMN_BYTES is include/scroll.h's. */

/* The per-life shelf this tail resets, in the order the original writes it. Everything with an
 * owner is included from that owner's header; the six below have none anywhere and
 * ../out/globals.tsv gives them no subsystem, so they are named here. */
#define A_slot_dir_flags        0x19673u  /* names.txt # ctx — 13 bytes, all cleared */
#define SLOT_DIR_FLAGS_BYTES    13u       /* `move.w #$c,d0` + dbf */
#define A_active_bullets        0x19909u  /* names.txt # ctx */
#define A_mothership_wave_clear_count 0x19915u  /* names.txt */
#define A_panel_logo_countdown  0x19dceu  /* names.txt # ctx */
#define A_powerup_flash_cursor  0x19dd4u  /* no names.txt line; .b, cleared here */
#define A_section_end_delay_counter 0x19ac0u    /* names.txt */

/* The values the shelf is reset TO. Each is one `move.b`/`move.w` immediate in the original. */
#define SECTION_TAIL_WEAPON_SLOTS 3u       /* `move.b #$3,$198b4` — the selected weapon */
#define SECTION_TAIL_POWERUP_SLOT 1u       /* `move.b #$1,$19906` */
/* The three `move.w #$3e8` into the gauge timers are include/player.h's POWERUP_DECAY_TICKS — the
 * same immediate the power-up arms in src/weapon.c refill the same three addresses with, so it is
 * included from there rather than given a second name here. */
#define SECTION_TAIL_PANEL_MASK   7u       /* `move.b #$7,$19904` — three elements want a repaint */
#define SECTION_TAIL_LOGO_TICKS   1u       /* `move.w #$1,$19dce` */
#define SECTION_TAIL_GROUND_RND   0x0au    /* `move.b #$a,$198c1` */
#define SECTION_TAIL_GRACE_TICKS  0x14u    /* `move.b #$14,$19abf` */
#define SECTION_TAIL_END_DELAY    0x32u    /* `move.b #$32,$19ac0` */
#define SECTION_TAIL_SECTION_START_SFX 0x27u   /* `moveq #$27,d1` into sound_start */
/* ...and the CHANNEL beside it, which is D0 still holding the interrogate command the fire loop
 * left there. Named for where it comes from rather than passed as an IKBD command at a sound call
 * site, exactly as BOOT_SOUND_CHANNEL_FROM_DBF is — and like that one, what it really claims is
 * only that it is neither 1 nor 2 (src/sound.c's `voice_for_channel`). */
#define SECTION_TAIL_SOUND_CHANNEL_FROM_D0 IKBD_CMD_INTERROGATE_JOYSTICKS
/* `move.b #$1,14(a2)` and `#$1,58(a2)` off the PLAYER record — the ship and its shadow, which are
 * ENTITY_ALIVE (0x0e) of the record and of the one 0x2c bytes after it. Spelt from
 * include/entity.h's field offset and stride rather than as two displacements. */

/* ================================================================================================
 * title_attract_loop — 0x12ac2..0x12c74, in four slices.
 *
 * The front end proper: colour bars painted by its own Timer B, the title and role-of-honour pages
 * alternating behind them, and a wait for key '1', key '2' or the fire button.
 * ============================================================================================= */
#define A_attract_vbl_isr        0x12c9eu  /* names.txt; src/irq.c */
#define A_attract_rasterbar_isr  0x12cc0u  /* names.txt; src/irq.c */
#define MFP_TIMER_B_PERIOD_ATTRACT_SETUP 0x00u  /* `move.b #$0,$fffa21` — the first of its two */
#define MFP_TIMER_B_PERIOD_ATTRACT_BARS  0x02u  /* ...and the one the bars actually run at */

/* THE BAR LIST IS BUILT IN THE BACKDROP'S PAGE 0 and copied to include/irq.h's
 * `A_attract_raster_list` every frame — one buffer under two uses in sequence, exactly as
 * include/video.h's A_backdrop_page0 note says of the asteroid banks. So the build's destination is
 * that address and not a fifth name for it. */
#define A_attract_bar_pattern  0x19f28u  /* names.txt — 7 groups of (repeats-1, scanlines) */
#define ATTRACT_BAR_GROUPS     7u        /* `move.w #$6,d4` + dbf */
#define ATTRACT_BAR_PAIR_BYTES 4u        /* one {scanlines, colour} pair */
#define ATTRACT_BAR_COLOUR     2u        /* ...and where the colour sits inside it */
#define ATTRACT_BAR_LIST_LONGS 0x29u     /* `move.w #$28,d0` + dbf — what is copied each frame */
/* The colour ramp: each pair's hue is the one before it plus 0x89, kept inside the shifter's three
 * 3-bit fields by the mask. `A_attract_bar_hue` carries it from one frame to the next. */
#define A_attract_bar_hue   0x19f20u     /* names.txt */
#define ATTRACT_HUE_STEP    0x89u
#define ATTRACT_HUE_MASK    0x777u
/* Every second frame the whole colour column scrolls down one pair and a fresh hue is written into
 * the first. Sixteen pairs move, which is fewer than the list holds. */
#define A_attract_bar_scroll_timer 0x198c6u  /* names.txt */
#define ATTRACT_BAR_SCROLL_PERIOD  2u        /* `move.b #$2,$198c6` */
#define ATTRACT_BAR_SCROLL_PAIRS   16u       /* `move.w #$f,d0` + dbf */
/* The page timer and the toggle that pick which screen is behind the bars. */
#define A_attract_page_timer  0x19f1eu   /* names.txt — frames until the page changes */
#define A_attract_page_toggle 0x199edu   /* names.txt — `eori.b #$1`: 0 = title, 1 = role of honour */
#define ATTRACT_PAGE_FRAMES   0x2eeu     /* `move.w #$2ee,$19f1e` */
/* The two scancodes the menu answers to, and the player count each chooses. */
#define KEY_SCANCODE_1 0x02u
#define KEY_SCANCODE_2 0x03u
#define ATTRACT_PLAYERS_DEFAULT 2u   /* `move.b #$2,$1991d` at the top of every pass */
#define ATTRACT_PLAYERS_ONE     1u   /* ...and what key '1' or the fire button chooses */

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
void boot_configure_ikbd(void);
void boot_load_gameplay_assets(uint8_t *image);
void boot_install_ikbd_isr(uint8_t *image);
/* 1 when the panel master was rebuilt and the tune restarted, 0 on the very first pass. Both arms
 * leave through the same address, so the answer is what a case checks WHICH ran by. */
unsigned boot_front_end_prologue(uint8_t *image);
void boot_stage_frontend_screens(uint8_t *image);
void boot_program_timer_b(uint8_t *image);
void boot_program_raster_timer(uint8_t *image);
void boot_enable_interrupts(void);
void boot_new_game_records(uint8_t *image);
void section_start_tail(uint8_t *image);
void attract_program_timer_b(uint8_t *image);
void attract_program_rasterbar_timer(uint8_t *image);
void attract_build_colour_bars(uint8_t *image);
/* The attract loop's body, 0x12bb4..0x12c74. It returns through the same `rts` whichever of the
 * three exits fired, and what it leaves behind is `A_player_count`. */
void attract_wait_for_start(uint8_t *image);

/* The one thing about the boot's hardware traffic the kit's write ledger cannot hold: the MASK the
 * `andi.b` applied (see the note above). Everything else the slice does off-image — that the store
 * happened, that the title palette went up, which register each landed in and how wide it was — is
 * ledgered and compared, so nothing else needs a sink. */
void init_shifter_sink_reset(void);
uint8_t init_shifter_mode_mask_written(void);

#endif /* ZYNAPS_INIT_H */
