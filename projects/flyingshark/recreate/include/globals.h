/* Flying Shark's RUN-TIME memory model: the one place a core or a test names the boundaries of the
 * program, the screen ring the harness places, the addresses the boot chain loads its files to, and
 * the two big arrays every subsystem walks.
 *
 * NOTHING ELSE BELONGS HERE. A subsystem's own globals live in the header of the subsystem that
 * owns the data (README.md, "Adding a function"); this header is what those headers include to say
 * where the sections are.
 *
 * PROVENANCE. Every segment figure is read off the .PRG header (`../out/prg_dis.txt`, first block:
 * text 0x59f4, data 0x6442, bss 0x3f0a8, 1563 relocs), and every `A_*` address is a `var` line in
 * ../names.txt at load base 0x10000. The instruction that establishes each run-time value is named
 * beside it; `test/test_image_model.py` re-derives the segment bounds from the header and runs the
 * program's own `boot_init` to pin the ring arithmetic, so this header cannot go stale.
 *
 * EVERY DEFINE HERE IS READ by the fixture that REPLAYS the boot chain (`test/conftest.py`) or by a
 * pin in `test/test_image_model.py`. That is the standing rule for this file rather than a
 * coincidence: a memory-model constant nobody reads is a claim nothing checks, and the subsystem
 * headers (`include/scroll.h`, `include/entity.h`, ...) are where a value's first real consumer
 * declares it. The map header's `rows`/`data` fields and the screen's row stride were deleted for
 * that reason — they are the scroll subsystem's to define when it lands.
 */
#ifndef FS_GLOBALS_H
#define FS_GLOBALS_H

/* ---- the program's own segments ---------------------------------------------------------- */

#define FS_LOAD_BASE     0x10000u   /* project.toml's load_base; ../names.txt assumes it */
#define FS_TEXT_BYTES    0x59f4u    /* .PRG header tlen: 0x10000 opens `bra.w boot_init` */
#define FS_DATA_BYTES    0x6442u    /* ...dlen: the score tables, the file records, the map buffer */
#define FS_BSS_BYTES     0x3f0a8u   /* ...blen: the tile banks, the sound module, the entity arena */

#define FS_DATA_BASE     0x159f4u   /* = FS_LOAD_BASE + FS_TEXT_BYTES */
#define FS_BSS_BASE      0x1be36u   /* = FS_DATA_BASE + FS_DATA_BYTES, and the sprite bank's home */
#define FS_PROGRAM_END   0x5aedeu   /* = FS_BSS_BASE + FS_BSS_BYTES, one past the last byte;
                                     * equals loader.PROGRAM_END */

/* The game's OWN supervisor stack, `movea.l #$19094,a7` @ 0x14bee, growing DOWN toward the
 * saved SSP longword at 0x19014. Recorded because boot_init's own trap pushes land in it; the
 * differential's cases run on the kit's stack (emu.STACK_TOP) instead. */
#define A_saved_super_ssp 0x19014u  /* `move.l d0,$19014` @ 0x14bfe — Super(0)'s result, never read */
#define A_stack_top       0x19094u

/* ---- the screen ring ----------------------------------------------------------------------
 * `boot_init` @ 0x14bee builds a 0x1f900-byte CIRCULAR framebuffer immediately below Physbase and
 * keeps four bases inside it; the game scrolls by moving a base, not by moving pixels. The
 * arithmetic below is that routine's, one constant per instruction — see README.md, "The image
 * model", for where the harness puts the ring and why.
 */
#define SCREEN_RING_BYTES  0x1f900u /* `subi.l #$1f900,d0` @ 0x14c26 — 808 rows of 160 bytes */
#define SCREEN_RING_ALIGN  0x100u   /* `addi.l #$100,d0 / clr.b d0` @ 0x14c3a: round the base UP to
                                     * 256, because the shifter's base register ($ffff8201/8203)
                                     * holds only the high two bytes of the address */
#define SCREEN_RING_0_OFF  0x7800u  /* `adda.l #$7800,a0`  @ 0x14c4a — row 192 */
#define SCREEN_RING_1_OFF  0xfa00u  /* `adda.l #$fa00,a0`  @ 0x14c62 — row 400 */
#define SCREEN_RING_2_OFF  0x17700u /* `adda.l #$17700,a0` @ 0x14c7a — row 600 */
#define SCREEN_RING_3_OFF  0x1f400u /* `adda.l #$1f400,a0` @ 0x14c8c — row 800 */
#define SCREEN_BYTES       0x7d00u  /* one 320x200 4-plane frame: 200 rows of 160 bytes. The row
                                     * STRIDE is the scroll subsystem's constant, not the model's */

#define A_screen_ring_base_raw 0x163fau /* `move.l d0,$163fa` @ 0x14c2e — Physbase - ring bytes */
#define A_screen_ring          0x16406u /* `move.l a0,$16406` @ 0x14c50 — ring[0]; four longwords */
#define A_screen_ring_1        0x1640au /* `move.l a0,$1640a` @ 0x14c68 */
#define A_screen_ring_2        0x1640eu /* `move.l a0,$1640e` @ 0x14c80 */
#define A_screen_ring_3        0x16412u /* `move.l a0,$16412` @ 0x14c98 */
#define A_screen_draw          0x16416u /* `move.l a0,$16416` @ 0x14c6e — seeded to ring[1] */
#define A_screen_prev1         0x1641au /* `move.l a0,$1641a` @ 0x14c56 — seeded to ring[0] */
#define A_screen_prev2         0x1641eu /* `move.l a0,$1641e` @ 0x14c92 — seeded to ring[3] */
#define A_screen_ring_base     0x16422u /* `move.l d0,$16422` @ 0x14c42 — the ring's low wrap limit
                                         * and the source of the clean rows scroll_step copies in */
#define SCREEN_RING_SLOTS      4u       /* A_screen_ring .. A_screen_ring_3 */

/* ---- what the boot chain loads, and where -------------------------------------------------
 * `load_file` @ 0x10bfa takes a0 -> an 8-byte [dest.l][length.l] record followed by the ASCIZ DOS
 * path; both longwords are RELOCATED, so the first is an absolute address at run time. The eight
 * records start at A_file_rec_flyshk_neo. `../notes/frontend.md` §3 has the table.
 */
#define A_file_rec_flyshk_neo  0x162eeu /* "A\FLY_SHK.NEO" -> A_sprite_bank, len 0x7d80 */
#define A_file_rec_module_bak  0x16304u /* "A\MODULE.BAK"  -> A_sound_module_file, len 0x1065 */
#define A_file_rec_sprites_cru 0x1631au /* "A\SPRITES.cru" -> A_sprite_bank, len 0x1caf2 */
#define A_file_rec_level_map   0x16330u /* "A\LEVEL1.MAP"  -> A_level_map_cols, len 0x1388 */
#define A_file_rec_hsc_0       0x16346u /* "A\HSC_0.DAT"   -> A_tile_banks + 0*TILE_BANK_BYTES */
#define A_file_rec_hsc_1       0x1635au /* "A\HSC_1.DAT"   -> ... + 1*TILE_BANK_BYTES */
#define A_file_rec_hsc_2       0x1636eu /* "A\HSC_2.DAT"   -> ... + 2*TILE_BANK_BYTES */
#define A_file_rec_hsc_3       0x16382u /* "A\HSC_3.DAT"   -> ... + 3*TILE_BANK_BYTES */
#define FILE_REC_DEST          0u       /* record +0: LONG destination address */
#define FILE_REC_LEN           4u       /* record +4: LONG byte count Fread asks for */
#define FILE_REC_NAME          8u       /* record +8: the ASCIZ path Fopen is given */

#define A_level_map_cols  0x16432u  /* LEVELn.MAP header word 0: tile columns (always 10), and the
                                     * record destination A\LEVEL1.MAP is read to */
/* The rest of the map header (rows, then the cells), how a CELL is read (base/overlay tile ids) and
 * what a row's stride is belong to the scroll subsystem, not to the memory model: they are in
 * include/scroll.h. */

#define A_tile_banks      0x38928u  /* the four HSC_n.DAT banks, back to back: one 128 KB atlas of
                                     * TILE_BANK_TILES*4 tiles addressed by a single byte id */
#define TILE_BANK_BYTES   0x8000u   /* one HSC_n.DAT: the record length at A_file_rec_hsc_0 + 4 */
#define TILE_BANKS        4u       /* ...and how many of them load back to back */

#define A_sprite_bank     0x1be36u  /* SPRITES.cru, loaded RAW over the title picture. Equals
                                     * FS_BSS_BASE: the sprite bank IS the start of the bss */
#define SPRITE_RECORDS    256u      /* `move.w #$ff,d0` @ 0x112c8, a dbf count */
#define SPRITE_RECORD_BYTES 20u     /* `lea 20(a0),a0` @ 0x112d2 */
/* The rest of the 20-byte record — width class, height, draw offsets, hit box — is the sprite
 * subsystem's and goes in include/sprite.h. What the memory model owns is that the first longword
 * of each record is a file-relative offset the boot chain makes absolute (`addi.l #$1be36,(a0)`
 * @ 0x112cc), because that is what test/conftest.py's fixture reproduces. */

#define A_sprite_restore_lists 0x18014u /* `lea $18014,a0` @ 0x112da — four lists, one per screen */
#define SPRITE_RESTORE_LISTS   4u        /* ...one per rotating screen buffer: the four stores at
                                          * 0x112e0/0x112e6/0x112ec/0x112f2 and no fifth */
#define SPRITE_RESTORE_LIST_BYTES 0x200u /* the stride of the four `move.w #$ffff,n(a0)` stores at
                                          * 0x112e0/0x112e6/0x112ec/0x112f2 (+2, +0x202, ...) */
#define SPRITE_RESTORE_TERMINATOR 0xffffu /* the width word that ends a list */
#define SPRITE_RESTORE_FIRST_ENTRY 2u     /* the terminator goes at list + this, not at list + 0 */

#define A_sound_module_file 0x58928u /* A\MODULE.BAK read here WHOLE, its 28-byte .PRG header
                                      * included: `load_file(file_rec_module_bak)` @ 0x14ca4 */
#define A_sound_module      0x58944u /* = A_sound_module_file + SOUND_MODULE_HEADER_BYTES; every
                                      * entry the game uses is taken relative to this */
#define SOUND_MODULE_HEADER_BYTES 28u
/* The module's LENGTH is not restated here: it is the relocated longword at
 * A_file_rec_module_bak + FILE_REC_LEN, and the image is the only place it is true. */

/* ---- the two big arrays ------------------------------------------------------------------- */

#define A_entity_arena  0x59984u  /* 91 records of 58 bytes; the layout is the entity subsystem's,
                                   * and is in include/entity.h — the PLACEMENT is what this file
                                   * owns */
#define ENTITY_SLOTS    91u
#define ENTITY_STRIDE   58u

/* THE SOUND MODULE OVERLAPS THE ARENA, and by design of neither: A\MODULE.BAK's load runs
 * A_sound_module_file .. + the record's own 0x1065 length = 0x58928..0x5998d, which is
 * MODULE_OVER_ARENA_BYTES past A_entity_arena at 0x59984. `clear_actor_arrays` @ 0x115e2 then
 * byte-clears 0x59984..0x5aede, so on the real machine those bytes are ZERO from the first
 * `init_new_game` onward and the module never sees them again.
 *
 * What they are: the last 8 bytes of `sfx_table`'s record 12 (`sfx_table` = 0x598a2, 13 records of
 * 18 bytes — ../out/names_module.txt), plus the one byte the record reads past the module's TEXT.
 * The GAME is unaffected because nothing ever asks for sound effect 12: the six `jsr 1196(a0)`
 * sfx_start sites (0x12188, 0x121c4, 0x121dc, 0x121f4, 0x1294e, 0x13e42) pass 6, 10, 5, 2, 5 and 11.
 * A TOOL that reads the module's tables out of a post-load image gets record 12's tail, and out of a
 * post-`init_new_game` image gets zeroes; either way it is reading a record the game cannot reach.
 *
 * `test/test_image_model.py::test_the_sound_module_overlaps_the_entity_arena_by_nine_bytes` pins the
 * size, so an arena or a record that moves fails by name rather than by a silent nine bytes. */
#define MODULE_OVER_ARENA_BYTES 9u

#endif /* FS_GLOBALS_H */
