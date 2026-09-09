/* frontend.h — Bubble Ghost's GEM binding, its boot-time screen/workstation setup, the sprite
 * protocol built on `vro_cpyfm`, and the file loaders.
 *
 * THE ONE FACT THAT ORGANISES THIS SUBSYSTEM: Bubble Ghost is a GEM application. It opens a virtual
 * workstation and draws its text, its bonus bar and its 32x32 sprites through the VDI
 * (`../notes/frontend.md` §1). The twelve VDI entry points and the four AES ones below are the
 * standard DRI binding — each fills the parameter block's `contrl`/`intin`/`ptsin` arrays from its
 * C arguments and jumps to the one routine of its subsystem that traps. They are what
 * `include/blit.h`'s three slices and the HUD painters were cut around; porting them unblocks both.
 *
 * WHAT THE TRAP BECOMES. A reconstruction cannot execute `trap #2`, so `vdi_call` @ 0x168d4 and
 * `gem_aes` @ 0x149b6 park the caller's A1/A2 exactly as the original does and then call the kit's
 * GEM model over the SAME parameter block in the SAME image (`os_vdi`/`os_aes`,
 * tools/recreate_kit/include/os.h; TRAP_MODEL.md phases 11-13). Both sides therefore run one
 * implementation of the VDI over one block, and every pixel it draws is image state the byte diff
 * covers.
 *
 * THIS SUBSYSTEM OWNS the two parameter blocks and their arrays, the workstation handle, the
 * screen/palette pointers XBIOS hands back, the sprite-bank pointer tables and the file loaders'
 * buffers. Globals it READS but does not own are reached by including the owning header:
 * `include/blit.h` for the two screens, the GHOST.DAT banks and the two sprite MFDBs;
 * `include/gameplay.h` for the room number, the ghost and bubble the sprite protocol draws and the
 * live score; `include/clib.h` for the trap trampoline's save slots and the C library's cores. The
 * INPUT BLOCK the mouse and key polls fill is this subsystem's own and is defined below.
 *
 * WHAT VERIFIES EACH ROUTINE is ../STATUS.md's "Verified — frontend" section, one row each.
 *
 * THE RECORD BLOCKS BELOW ARE FROZEN, as `include/gameplay.h`'s and `include/sound.h`'s are
 * (docs/agent-playbook.md §11). Several agents port routines against them at once, so nobody adds a
 * field: the offset a routine needs is already named. The frozen sets here are the parameter
 * blocks' index sets (`VDI_*`, `AES_*`), `vro_cpyfm`'s eight-word rectangle (`BLIT_PXY_*`) and the
 * three stack-frame layouts (`INIT_FRAME_*`, `HISCORE_FRAME_*`/`HALL_FRAME_*`, `SAVE_FRAME_*`).
 * Every line carries its PROVENANCE — the instruction the index or displacement was read off — and
 * the only permitted edit is upgrading an `unpinned` note to a test name in the same change that
 * ports the routine which pins it.
 *
 * A STACK-FRAME layout is provenance of a different kind and is tagged as such: its displacements
 * are `n(a6)` in the ROUTINE that owns the frame, and the differential drops the stack band, so
 * what pins one is the case that hands both sides the same frame base (../STATUS.md's residual).
 */
#ifndef BG_FRONTEND_H
#define BG_FRONTEND_H

#include <stdint.h>

#include "blit.h"    /* the tile geometry a sprite cell IS, and the two screens */
#include "clib.h"    /* CallerAddressRegisters, the trap save slots, and the C library's cores */
#include "common.h"  /* GlobalsBase and word_at_base, for the base-register reads below */

/* ================================================================================================
 * The VDI parameter block — `vdi_call` @ 0x168d4 and the twelve entry points that fill it
 *
 * `vdi_pblock` is five longwords of array pointers, and it sits at the very first bytes of BSS.
 * Four of them are only ever written by `v_opnvwk`'s tail and by the two entry points that lend the
 * VDI a CALLER'S array for the duration of one call (`vr_recfl`, `vro_cpyfm`) — so a run entered
 * below `init_gem_and_screens` starts with the four still zero, which is what the loaded image
 * holds, and a case that means an open workstation stages them.
 * ============================================================================================= */

#define A_vdi_pblock    0x1e8cau  /* long[5]: contrl, intin, ptsin, intout, ptsout */
#define A_vdi_contrl    0x236f0u  /* word[]: [0] opcode, [1] #ptsin, [3] #intin, [6] handle,
                                   * [7..8] source MFDB, [9..10] destination MFDB */
#define A_vdi_intin     0x235f0u
#define A_vdi_ptsin     0x234f0u
#define A_vdi_intout    0x233f0u
#define A_vdi_ptsout    0x232f0u
#define A_vdi_handle    0x232eeu  /* word: the handle `v_opnvwk` returns, first argument of every
                                   * entry point below. It sits immediately under `ptsout` */

/* ...and the handle READ out of it, which every drawing call in this program passes and none of them
 * computes. Here rather than as a `static` in each caller: `src/frontend.c` and `src/gameplay.c` had
 * grown a private copy each under the same name, which is the shape a third copy starts from. */
static inline int16_t vdi_handle(const uint8_t *image) {
    return (int16_t)be16(image + A_vdi_handle);
}

/* ...and the same read for a caller that already holds the base — `word_at_base` beside `word_at`,
 * and named `_at_base` because that is what the two in `include/common.h` and
 * `trap_save_registers_at_base` are called.
 *
 * WHAT IT IS WORTH, off `m68k-elf-objdump -d` rather than from the cycle tables: the image form
 * needs the address in a register, so GCC spends one `movea.l #<address>,%an` and then reads the
 * handle through the two-register index — 44 cycles across `frame_poll_input`'s two reads against
 * 24 here — and the register it burns is one more the prologue's `movem` saves and restores.
 * `sprite_copy`'s three callers take it for the same reason (../STATUS.md's wave 7b). */
static inline int16_t vdi_handle_at_base(GlobalsBase globals) {
    return word_at_base(globals, A_vdi_handle);
}
#define A_vdi_work_in   0x2377au  /* word[11] `init_gem_and_screens` fills: ten 1s and a 2 */
#define A_vdi_work_out  0x23708u  /* word[57]: 45 intout entries then 6 ptsout PAIRS, which is what
                                   * `v_opnvwk` points the two output arrays at (+0 and +0x5a) */

/* Where `v_opnvwk` lends the VDI the caller's `work_out` as its ptsout array: 45 words on from its
 * head, which is `OS_VDI_WORK_OUT_INTS` words and the `add.l #$5a,d0` @ 0x169b4. */
#define VDI_WORK_OUT_PTSOUT_OFFSET 0x5au

/* `contrl` word indices this binding writes, and the `ptsin`/`intout`/`ptsout` slots it reads back.
 * The kit's os.h names the same contrl indices for its own model; these are the game's spelling of
 * the ones its wrappers touch, and the two agree by inspection rather than by inclusion — a
 * `VDI_CONTRL_*` re-definition here would be a second home for os.h's constant. */
#define VDI_PTSIN_X          0u   /* `move.w …,-6698(a4)` = ptsin[0]: v_gtext's x, and the word
                                   * `vst_height` clears @ 0x16900 without using */
#define VDI_PTSIN_Y          1u   /* `move.w 10(a6),-6696(a4)` @ 0x16904: the requested height */
#define VDI_HEIGHT_CHAR_W    0u   /* vst_height's four ptsout answers, in the order it copies them
                                   * out: `-7210(a4)` @ 0x16928 (= ptsout[0]), */
#define VDI_HEIGHT_CHAR_H    1u   /* `-7208(a4)` @ 0x16930, */
#define VDI_HEIGHT_CELL_W    2u   /* `-7206(a4)` @ 0x16938, */
#define VDI_HEIGHT_CELL_H    3u   /* `-7204(a4)` @ 0x16940 */
#define VDI_MOUSE_X          0u   /* `-7210(a4)` @ 0x16a4e: vq_mouse's two ptsout answers, */
#define VDI_MOUSE_Y          1u   /* `-7208(a4)` @ 0x16a56 (its button mask is intout[0]) */

/* `v_opnvwk` hands the VDI eleven intin entries — `move.w #$b` @ 0x169c8 — which is `work_in`'s
 * ten 1s plus the coordinate-system word behind them. */
#define V_OPNVWK_WORK_IN_WORDS 11u

/* ================================================================================================
 * The AES parameter block — `gem_aes` @ 0x149b6 and `aes_crysif` @ 0x14b2e
 *
 * `aes_crysif(opcode)` is the whole AES binding: it puts the opcode in `control[0]`, copies the
 * (n_intin, n_intout, n_addrin) triple for that opcode out of a three-byte-per-opcode table in the
 * TEXT segment into `control[1..3]`, traps, and answers `int_out[0]`.
 * ============================================================================================= */

/* IN THE TEXT SEGMENT, so it is deliberately not an `A_*` name: that family means a global in the
 * BSS or the DATA above it, and `test_constants.py` refuses an `A_*` outside that window. */
#define AES_CONTROL_TABLE 0x149d2u   /* 3 signed bytes per opcode, starting at opcode 10 */
#define A_aes_ap_id     0x1f0bcu  /* word: appl_init's answer */
#define A_aes_pblock    0x1f0beu  /* long: -> the six pointers below, which is what gem_aes traps on */
#define A_aes_p_control 0x1f0c2u  /* long[6]: control, global, int_in, int_out, addr_in, addr_out */
#define A_aes_p_global  0x1f0c6u
#define A_aes_p_int_in  0x1f0cau
#define A_aes_p_int_out 0x1f0ceu
#define A_aes_p_addr_in 0x1f0d2u
#define A_aes_p_addr_out 0x1f0d6u
#define A_aes_addr_out  0x1f0dau
#define A_aes_addr_in   0x1f0e2u
#define A_aes_int_out   0x1f0eeu
#define A_aes_int_in    0x1f0feu
#define A_aes_global    0x1f120u
#define A_aes_control   0x1f140u

#define AES_TABLE_FIRST_OPCODE 10u /* the table starts at appl_init; `sub.w #$a,d0` @ 0x14b3c */
#define AES_TABLE_STRIDE        3u /* `muls.w #$3,d0` @ 0x14b40 — n_intin, n_intout, n_addrin */
#define AES_CONTROL_OPCODE      0u /* control[0], the AES's own slot — the VDI's `contrl` has the
                                    * opcode there too, but they are different records */
#define AES_CONTROL_FIRST_COUNT 1u /* control[0] is the opcode; the triple lands in [1..3] */
#define AES_CONTROL_COUNT_SLOTS 4u /* `cmpi.w #$4,-2(a6)` — the loop's exclusive bound */

/* graf_handle's four `int_out` answers, in the order it copies them out — and `int_out[0]`, which
 * it answers in D0, is the handle itself (`move.w -24108(a4),d0` @ 0x14c16). */
#define AES_HANDLE_CHAR_W 1u  /* `move.w -24106(a4),(a0)` @ 0x14bfa, a0 = 8(a6) */
#define AES_HANDLE_CHAR_H 2u  /* `-24104(a4)` @ 0x14c02, a0 = 12(a6) */
#define AES_HANDLE_CELL_W 3u  /* `-24102(a4)` @ 0x14c0a, a0 = 16(a6) */
#define AES_HANDLE_CELL_H 4u  /* `-24100(a4)` @ 0x14c12, a0 = 20(a6) */

/* ================================================================================================
 * The input block — what `vq_mouse` @ 0x16a26, `vq_key_s` @ 0x16a5e and the `Crawio(0xff)` poll
 * leave for the rest of the program
 *
 * FIVE CONSECUTIVE WORDS, and they are this subsystem's because the routines that fill them are.
 * The two VDI polls take their out-parameters as ARGUMENTS — `draw_room_to_stage` and
 * `game_frame_update`'s poll pass these five addresses — so the binding itself needs no name for
 * them; the READERS do. `src/gameplay.c` includes this header for them (the mouse scaling, the
 * facing latches and the blow's shift gate), which is the migration ../STATUS.md's "Borrowed
 * globals" table predicted, now made.
 * ============================================================================================= */

#define A_key_raw           0x23114u /* BYTE: the last `Crawio(0xff)`. Written by
                                      * `game_frame_update` @ 0x1238e — a writer in another
                                      * subsystem, but one word of THIS block */
#define A_key_shift_state   0x23116u /* word: vq_key_s's `intout[0]` */
#define A_mouse_y           0x23118u /* word: vq_mouse `ptsout[1]` */
#define A_mouse_x           0x2311au /* word: vq_mouse `ptsout[0]` */
#define A_mouse_buttons     0x2311cu /* word: vq_mouse `intout[0]` */

/* ================================================================================================
 * `init_gem_and_screens` @ 0x10118 — the boot-time workstation and screen setup
 * ============================================================================================= */

#define A_screen_rez        0x23146u /* word: XBIOS Getrez's answer, stored and never read again */
#define A_super_arg         0x22f6cu /* long: what is handed to GEMDOS Super. Never written by this
                                      * routine — it passes on whatever the longword already holds,
                                      * which on a cold boot is the bss zero, i.e. Super(0) */
#define A_super_saved_ssp   0x22f70u /* long: Super(0)'s answer, handed back to leave supervisor */
#define A_conterm_addr_w    0x22f6au /* word: 0x484, built as a word... */
#define A_conterm_addr_l    0x22f66u /* long: ...then sign-extended to a long and dereferenced */

#define CONTERM_ADDRESS     0x484u   /* TOS's `conterm` byte: clearing it kills key click and bell */
#define WORK_IN_ONES        10u      /* `cmpi.w #$a` @ 0x1013e: work_in[0..9] = 1 */
#define WORK_IN_COORD_SLOT  10u      /* ...and work_in[10] = 2, "raster coordinates" */
#define WORK_IN_COORD_RASTER 2u

/* The two GEMDOS/XBIOS selectors this subsystem reaches directly, plus the return addresses the
 * trampoline files for each site. A selector is the word the caller pushes; the trampoline itself
 * is `include/clib.h`'s, and `../STATUS.md` says why its three save slots are the whole of what a
 * reconstruction can reproduce about a trap. */
#define XBIOS_LOGBASE    3u
#define XBIOS_GETREZ     4u
#define XBIOS_SETSCREEN  5u
#define XBIOS_SETPALETTE 6u

/* What the model answers `Getrez` with. It is the kit's constant rather than this game's — the shim
 * leaves D0 at 0 for the whole Setscreen/Setpalette/Setcolor/Getrez group (TRAP_MODEL.md) — and
 * `test_frontend.py` pins it against a real oracle run rather than leaving it as a belief. Named
 * here because `main` @ 0x100dc branches on it: a non-zero resolution is the "Please reboot in LOW
 * REZ" path. */
#define XBIOS_GETREZ_LOW_RES 0u

#define RET_INIT_GETREZ         0x10184u /* the byte after each `jsr xbios_trap`/`jsr gemdos_trap` */
#define RET_INIT_LOGBASE_BACK   0x10192u
#define RET_INIT_LOGBASE_PHYS   0x101a6u
#define RET_INIT_SUPER_ENTER    0x101b8u
#define RET_INIT_SUPER_LEAVE    0x101e0u
#define RET_SHOW_PRESENTATION_SETPALETTE 0x10edcu
#define RET_SAVE_HISCORES_SETSCREEN_PHYS 0x120beu
#define RET_SAVE_HISCORES_SETSCREEN_BACK 0x12198u

/* `init_gem_and_screens`' own frame, whose locals are the four out-parameters it hands
 * `graf_handle` (all four the SAME word, whose value is then thrown away) and the two words it
 * files `appl_init`'s and `graf_handle`'s answers in. They lie in the band the differential drops
 * as stack, so the frame base is an argument of the core: see ../STATUS.md's residual. */
#define INIT_FRAME_SCRATCH_OUT  (-6)  /* -6(a6): the work_in fill's loop counter FIRST, and then
                                       * graf_handle's four out-parameters — the routine reuses one
                                       * word for both, and nothing reads either */
#define INIT_FRAME_AP_ID        (-4)  /* -4(a6): appl_init's answer */
#define INIT_FRAME_PHYS_HANDLE  (-2)  /* -2(a6): graf_handle's answer */

/* ================================================================================================
 * The screen and palette pointers, and the sprite bank
 * ============================================================================================= */

#define A_dat_palette   0x23122u /* long: the 16-word palette off the tail of GHOST.DAT */
#define A_pre_palette   0x23126u /* long: ...and the one off the tail of GHOST.PRE */

#define DAT_BANK_PRE    6u       /* `bank_index = 6` selects dat_bank[6], the GHOST.PRE picture */
#define PALETTE_BYTES   0x20u    /* 16 words, the tail of each picture file */

#define A_hall_scores   0x22f8cu /* long[5], sorted ASCENDING: [0] is the worst, [4] the best */
#define A_hall_rooms    0x22f78u /* long[5]: the room each entry reached, kept in step */

#define A_ghost_sprite  0x23028u /* long[47]: the 32x32 cells grabbed from GHOST.DAT tiles 0..46 */
#define A_bubble_sprite 0x22ff4u /* long[13]: ...and tiles 47..59. `build_sprite_bank` reaches this
                                  * table with the UNBIASED cell index, so the `lea` it uses is
                                  * A_bubble_sprite - SPRITE_BANK_BUBBLE_FIRST * 4 */
#define A_ghost_bg      0x230e8u /* long: the 32x32 patch saved from under the ghost */
#define A_bubble_bg     0x230e4u /* long: ...and from under the bubble */
#define A_blit_pxy      0x232d6u /* word[8]: vro_cpyfm's ptsin — src x1,y1,x2,y2 then dst x1,y1 and
                                  * the two words the copy does not read */

/* A SPRITE CELL IS A GHOST.DAT TILE, so its size, its side and how many fill a bank are
 * `include/blit.h`'s constants and are not renamed here: `c_malloc(TILE_BYTES)` per grab,
 * `TILES_PER_BANK` grabs, `ROOM_TILE_COLS` cells across the bank screen (which is what
 * `draw_tile_bank_screen` painted it as). The two below are this subsystem's own. */
#define SPRITE_BANK_BUBBLE_FIRST 47u    /* `cmpi.w #$2f` — cells 0..46 are the ghost's, 47..59 the
                                         * bubble's */
#define SPRITE_EXTENT (TILE_PIXELS - 1) /* `add.w #$1f`: the far corner of a TILE_PIXELS span, which
                                         * every `vro_cpyfm` rectangle in this file is built from */

/* `vro_cpyfm`'s eight-word rectangle, read off `save_sprite_backgrounds` @ 0x1342e, which fills all
 * eight in order from `A_blit_pxy` = `A4_BASE - 7236`. Every rectangle in this file is built from
 * these eight, and all eight are pinned by test_frontend.py's sprite-protocol cases. */
#define BLIT_PXY_SRC_X1 0u  /* `move.w -7976(a4),-7236(a4)` @ 0x1343e */
#define BLIT_PXY_SRC_Y1 1u  /* `-7234(a4)` @ 0x13444 */
#define BLIT_PXY_SRC_X2 2u  /* `-7232(a4)` @ 0x13452, the far corner: x1 + SPRITE_EXTENT */
#define BLIT_PXY_SRC_Y2 3u  /* `-7230(a4)` @ 0x1345e */
#define BLIT_PXY_DST_X1 4u  /* `clr.w -7228(a4)` @ 0x13462 — the grab's destination is the cell */
#define BLIT_PXY_DST_Y1 5u  /* `clr.w -7226(a4)` @ 0x13466 */
#define BLIT_PXY_DST_X2 6u  /* `move.w #$1f,-7224(a4)` @ 0x1346a */
#define BLIT_PXY_DST_Y2 7u  /* `move.w #$1f,-7222(a4)` @ 0x13470 */

#define VDI_MODE_S_ONLY 3u   /* a plain copy: the grab, the background save and its restore */
#define VDI_MODE_S_OR_D 7u   /* the transparent sprite draw — colour 0 is the sprites' background */

/* ================================================================================================
 * The file loaders
 *
 * All four open with `c_open(name, mode)` and RETRY until it succeeds. Under the kit's model an
 * unstaged name is a refused run rather than a negative handle (../STATUS.md, clib's residuals), so
 * the retry runs exactly once and the failure arm of each loader is read-verified.
 * ============================================================================================= */

#define A_demo_base     0x23160u /* long: the malloc'd GHOST.DEM image */
#define A_demo_cursor   0x23164u /* long: the replay cursor into it, += 6 per frame */

#define C_OPEN_MODE_READ_BINARY 0x2000u /* the three picture/demo loaders' mode word */
#define C_OPEN_MODE_READ_TEXT   0u      /* ...and `load_hiscores`', whose file is ASCII */

#define A_name_ghost_dem 0x24fe0u /* `pea 198(a4)`  @ 0x10df2 */
#define A_name_ghost_pre 0x24fecu /* `pea 210(a4)`  @ 0x10e4c */
#define A_name_ghost_scr 0x25176u /* `pea 604(a4)`  @ 0x121a6 — what `load_hiscores` OPENS */
#define A_name_ghost_scr_creat 0x25156u /* `pea 572(a4)` @ 0x120d0 — a SECOND copy of the same
                                         * eleven bytes, which is what `save_hiscores` CREATES.
                                         * The C library's device-name tables are duplicated the
                                         * same way (`include/clib.h`'s two `*_device_names`) */
#define A_name_ghost_dat 0x251b2u /* `pea 664(a4)`  @ 0x13978 */

#define DEMO_FILE_BYTES     0x1770u /* `c_malloc(0x1770)`: 1,000 six-byte records */
#define PICTURE_BYTES       0x7800u /* one 320x192 four-plane picture = one 60-tile bank */
#define DAT_BANKS_FROM_FILE 6u      /* `cmpi.w #$6` — GHOST.DAT holds six of them */

/* `load_hiscores` — five (score, room) pairs of zero-padded ASCII digits, and the frame it parses
 * them in. The two buffers are stack locals, so like `init_gem_and_screens`' frame they are an
 * argument of the core rather than something it can name. */
#define HISCORE_SLOTS         5u
#define HISCORE_SCORE_DIGITS  6u
#define HISCORE_ROOM_DIGITS   2u
#define HISCORE_MISSING_ROOM  1u   /* every room reads as 1 when the file will not open */
/* The parse's radix is `include/gameplay.h`'s `DECIMAL_RADIX` — the same ten `itoa_padded` divides
 * by on the way out — rather than a second name for it here. */

/* FRAME LAYOUT (see this file's header): `load_hiscores`' own `link a6,#$ffea`, its two `pea`s. */
#define HISCORE_FRAME_SCORE_TEXT (-8)   /* `pea -8(a6)`: six digits, with the NUL at -2(a6) */
#define HISCORE_FRAME_ROOM_TEXT (-12)   /* `pea -12(a6)`: two digits, with the NUL at -10(a6) */

/* ================================================================================================
 * The hall of fame — `draw_hall_of_fame` @ 0x11dbc, `hiscore_insert_and_save` @ 0x11f84 and
 * `hiscore_submit_players` @ 0x11d6e
 *
 * Five (score, room) pairs and no names anywhere in the program. The two arrays are kept SORTED
 * ASCENDING, so slot 0 is the worst and slot 4 the best — which is why the screen is drawn from
 * slot 4 downward and why an insert only ever overwrites slot 0.
 * ============================================================================================= */

#define A_hiscore_candidate     0x22fa0u /* long: the score offered to the table */
#define A_hiscore_pending_score 0x2317eu /* long: ...and the pair that lands in slot 0 with it */
#define A_hiscore_pending_room  0x23192u /* word, widened to a long on the way in */
#define A_player_count          0x2316cu /* word: 0 until [1]/[2] is chosen, then 1 or 2 */
#define A_p2_score              0x23182u /* long */
#define A_p1_score              0x23186u /* long */
#define A_p2_max_room           0x23194u /* word */
#define A_p1_max_room           0x23196u /* word */

#define A_text_cell_h           0x22fb6u /* the four words `vst_height` answers through */
#define A_text_cell_w           0x22fb8u
#define A_text_char_h           0x22fbau
#define A_text_char_w           0x22fbcu

#define HISCORE_SORT_PASSES 5u  /* `cmpi.w #$5,-2(a6)`: five passes of four adjacent compares, so
                                 * a value inserted at slot 0 can walk the whole way to slot 4 */
#define HISCORE_SORT_COMPARES 4u
#define PLAYER_COUNT_TWO     2u

/* The hall-of-fame screen (`../notes/frontend.md` §4). One text height, three pens, and a row
 * pitch the loop counts DOWN from — so slot 4, the best, lands on the "SCORE 1:" row. */
#define HALL_TEXT_HEIGHT     6
#define HALL_PEN_LABEL      13
#define HALL_PEN_NUMBER      5
#define HALL_BACKDROP_ROOM   0   /* room 0 sits behind the start square and is drawn as the
                                  * backdrop; the menu's `[P]` check (0 < n < 36) is what stops a
                                  * player selecting it */
#define HALL_BASE_Y      0x72
#define HALL_ROW_PITCH     15    /* `muls.w #$f,d1` */
#define HALL_LABEL_X     0x38
#define HALL_HALL_X      0xc8
#define HALL_SCORE_X     0x80
#define HALL_ROOM_X      0xf8

/* The five "SCORE n:" labels are ten bytes apart in DATA, and "HALL:" follows them. */
#define A_text_score_labels 0x2511cu
#define TEXT_SCORE_LABEL_BYTES 10u
#define A_text_hall         0x2514eu

/* The five "SCORE n:" rows are drawn at these offsets ABOVE the base line, one per label, and the
 * offsets are written out rather than derived: the original spells five separate `sub.w #imm,d0`
 * with the last one `#$0`, so the pitch is a coincidence of the constants and not a loop. */
#define HALL_LABEL_Y_OFFSETS { 0x3c, 0x2d, 0x1e, 0xf, 0x0 }

/* FRAME LAYOUT: `draw_hall_of_fame`'s own `link a6,#$ffea` — two digit buffers, like
 * `load_hiscores`'. Both are pinned by the case that hands the two sides the same frame base. */
#define HALL_FRAME_SCORE_TEXT (-18)  /* `pea -18(a6)`: six digits from `itoa_padded` */
#define HALL_FRAME_ROOM_TEXT  (-22)  /* `pea -22(a6)`: two digits */

/* FRAME LAYOUT: `save_hiscores`' own `link a6,#$fff4` @ 0x1207a — ONE digit buffer, reused for both
 * fields, and the loop counter.
 *
 * THE COUNTER IS PART OF THE ROUTINE'S OUTPUT, which is why it is named here at all. Both
 * `graf_mouse` call sites push only the mode word and a zero word, so the `addr_in` LONG the AES
 * reads spans that zero and the counter above it — the mouse form is `(0 << 16) | slot`. That is
 * why the reconstruction keeps the counter in the image rather than in a C local. */
#define SAVE_FRAME_TEXT  (-8)   /* `pea -8(a6)`: six digits, then two, into the same bytes */
#define SAVE_FRAME_SLOT (-12)   /* `-12(a6)`: the loop counter, and the low word of both mouse
                                 * forms — pinned by the prologue slice, which is the only place
                                 * the FIRST form is observable */

#define SAVE_BANNER_X 0         /* v_gtext(handle, 0, 6, "Saving  HI-SCORES") */
#define SAVE_BANNER_Y 6
#define A_text_saving_banner 0x25162u
#define SETSCREEN_KEEP_RESOLUTION 0 /* `clr.w -(a7)`: the third argument at both call sites. -1
                                     * would mean "leave the resolution alone"; this game passes 0 */
#define C_CREAT_MODE_TEXT 0u    /* `clr.w -(a7)` @ 0x120ce: the file is ASCII and has no newline */

/* ================================================================================================
 * The front end's state machine — `title_menu_loop` @ 0x115d6 and `game_top_loop` @ 0x101e6
 *
 * These two ARE the program: `main` calls `game_top_loop` and never gets it back, and everything
 * else in this project is something one of them calls. `../notes/frontend.md` §2 draws the machine;
 * what is named below is only what the two routines reach that no other subsystem already names.
 *
 * NEITHER ROUTINE RETURNS TO ITS CALLER on the real machine — `game_top_loop` is a `do { … } while
 * (true)` and `title_menu_loop` only returns once a game has been chosen — so both are verified as
 * a chain of `stop_pc` SLICES, plus (for `title_menu_loop`) whole runs on the two key paths that do
 * return. ../STATUS.md's rows carry the `[start, end)` each case runs.
 *
 * BOTH KEEP THEIR LOCALS IN THE IMAGE rather than in C locals, for `save_hiscores`' reason
 * (`SAVE_FRAME_SLOT` above): a slice entered part-way through has to find the locals the earlier
 * part left, so the frame base is an argument and every local is named here. The bytes lie in the
 * band the differential drops, so what a case stages there is an input to both sides alike.
 * ============================================================================================= */

/* --- the three XBIOS calls the rest of this file did not already need --- */
#define XBIOS_SETCOLOR   7u      /* `move.w #$7,-(a7)` @ 0x10928 and @ 0x10bd4 */
#define XBIOS_RANDOM    17u      /* `move.w #$11,-(a7)` @ 0x1085a, 0x11ae6 and 0x11b30 */
#define XBIOS_VSYNC     37u      /* `move.w #$25,-(a7)` — three per slideshow frame @ 0x11bca.. */

/* --- the state the menu writes and `game_top_loop` reads --- */
#define A_practice_mode      0x2315cu /* word: set by `[P]`, and what makes a turn end after one
                                       * room (`game_top_loop` forces `lives = -1` on the exit) */
#define A_practice_grid_row  0x23158u /* word: where `[P]` found the level in `room_grid`... */
#define A_practice_grid_col  0x2315au /* ...and its column. THE SEARCH REUSES BOTH AS ITS OWN LOOP
                                       * COUNTERS WITH THE ROLES REVERSED — the outer loop counts in
                                       * `A_practice_grid_col` over grid ROWS — and the two are put
                                       * back the right way round from the frame at the end */
#define A_p2_turn            0x23168u /* word: the twin of `include/gameplay.h`'s `A_p1_turn`. A new
                                       * game starts with this one set, and the swap at the top of
                                       * each room makes player one go first */

/* --- the DATA-segment strings, in the order the two routines draw them --- */
#define A_text_game_over_p1   0x24f3cu /* `pea 34(a6-relative DATA)`: the two-player card's… */
#define A_text_player_one_out 0x24f50u /* …"G A M E    O V E R" over "P L A Y E R    O N E" */
#define A_text_game_over_p2   0x24f66u
#define A_text_player_two_out 0x24f7au
#define A_text_player_one_up  0x24f90u /* the handover card, drawn as the turn starts */
#define A_text_player_two_up  0x24fa6u
#define A_text_game_over      0x24fccu /* …and the one-player one, at the end of the whole game */
#define A_text_menu_game      0x24ff8u /* the four menu lines, at x = MENU_TEXT_X */
#define A_text_menu_practice  0x2501cu
#define A_text_menu_demo      0x25040u
#define A_text_menu_hall      0x25064u
#define A_text_one_player     0x25088u /* `[G]`'s two lines, at x = MENU_PLAYERS_X */
#define A_text_two_players    0x250a8u
#define A_text_enter_level    0x250c8u /* …and `[P]`'s one */

/* --- the six DATA doubles the two `Random()` scalings read (`../notes/frontend.md` §6) ---
 * The divisor appears TWICE at two addresses holding the same value; both are named because a call
 * site reads one address and not the other, and `../out/prg_dis.txt` is what says which. */
#define A_const_demo_length_divisor 0x250ecu /* 16794009.000000015 */
#define A_const_demo_length_scale   0x250f4u /* 11.0 -> a slideshow of 5..15 rooms */
#define A_const_demo_length_offset  0x250fcu /* 5.0 */
#define A_const_demo_room_divisor   0x25104u /* 16794009.000000015 again, at its own address */
#define A_const_demo_room_scale     0x2510cu /* 34.0 -> a room of 1..34: room 35 is unreachable */
#define A_const_demo_room_offset    0x25114u /* 1.0 */

/* --- the menu itself --- */
#define MENU_TEXT_HEIGHT      6   /* `vst_height(handle, 6)` — the hall of fame's height too */
#define MENU_PEN              1   /* `vst_color(handle, 1)` */
#define MENU_TEXT_X        0x18   /* the four "Press [x] …" lines… */
#define MENU_TEXT_Y_GAME   0x48   /* …one every MENU_TEXT_Y_PITCH scanlines */
#define MENU_TEXT_Y_PITCH  0x10
#define MENU_PLAYERS_X     0x28   /* `[G]`'s two lines */
#define MENU_PLAYERS_Y     0x58
#define MENU_LEVEL_X       0x18   /* …and `[P]`'s one */
#define MENU_LEVEL_Y       0x60

#define MENU_KEY_LOWER_A  0x60    /* `cmp.w #$60,d0 / ble`: a key ABOVE this is folded to upper… */
#define MENU_KEY_CASE_BIT 0x20    /* …by `subi.b #$20`, on the BYTE and not on the widened word */
#define MENU_DIGIT_ZERO   0x30    /* '0': both the player count and the two level digits */
#define MENU_LEVEL_TENS     10    /* `move.w #$a,d0 / muls.w tens,d0` */
#define MENU_LEVEL_LOWEST    0    /* `cmpi.w #$0 / ble`: a level must be strictly above 0… */
#define MENU_LEVEL_ABOVE  0x24    /* …and strictly below 36, which is what keeps room 0 out */

/* --- the `[D]` attract sequence (`../notes/frontend.md` §2) --- */
#define DEMO_RECORDS       0x3d4u /* `move.l #$3d4,-6(a6)`: 980 of the file's 1,000 records */
#define DEMO_RECORD_BYTES     6u  /* `addq.l #6` on the cursor, one byte per field below */
#define DEMO_FIELD_GHOST_X    0u  /* …each byte read SIGNED and scaled by the factor beside it */
#define DEMO_FIELD_GHOST_Y    1u
#define DEMO_FIELD_GHOST_TILE 2u
#define DEMO_FIELD_BUBBLE_X   3u
#define DEMO_FIELD_BUBBLE_Y   4u
#define DEMO_FIELD_BUBBLE_FRAME 5u
#define DEMO_SCALE_X          3   /* `muls.w #$3`: the record's unit is 3 pixels across… */
#define DEMO_SCALE_Y          2   /* …and 2 down */

#define DEMO_SLIDESHOW_FRAMES 0x1eu /* `move.l #$1e,-6(a6)`: 30 frames per slideshow room, each held
                                     * for THREE `Vsync`s — the only frame sync in the whole attract
                                     * sequence, and three separate calls rather than a loop because
                                     * the trampoline files a different return address for each */
#define DEMO_TITLE_POLLS  0x9088u   /* `move.l #$9088,-6(a6)`: 37,000 mouse polls on the title */
#define HALL_IDLE_POLLS    0x359u   /* `move.l #$359,-6(a6)`: 857 after the hall of fame */

#define MOUSE_BUTTON_LEFT     1   /* `cmpi.w #$1,mouse_buttons`: what aborts every attract loop */
#define DEMO_FIRST_ROOM       1   /* the replay is always of room 1 — the file has no room field */
#define MENU_SFX_NOTE_ONE_SHOT (-1) /* a NEGATIVE note tells `sound_play` to leave the tone at the
                                     * definition's own pitch rather than folding a MIDI note into
                                     * the period table (`src/sound.c`'s `note >= 0` gate) */

#define PUFF_VOICE            1   /* voice 1 is the GHOST'S BREATH everywhere — the demo
                                   * replay's puff and the game loop's blow alike, which is
                                   * why both end-of-room animations release it */
#define DEMO_PUFF_NOTE     0xfa
#define DEMO_POP_VOICE        2
#define MENU_AMBIENCE_VOICE   0
#define MENU_SFX_PRIORITY     5
#define MENU_AMBIENCE_VOLUME  8   /* `muls.w #$8,sound_enabled` — the room ambience's volume… */
#define MENU_LOUD_VOLUME    0xb   /* …and the louder one the pop and the title picture use */


/* FRAME LAYOUT: `title_menu_loop`'s own `link a6,#$fff0` @ 0x115d6. */
#define MENU_LOCAL_BYTES     16u  /* what the `link` reserves, which is where its callees' frames
                                   * start (see `CALL_FRAME_COST`) */
#define MENU_FRAME_KEY       (-1) /* BYTE: the key `Cnecin` answered, folded to upper case */
#define MENU_FRAME_DIGIT     (-2) /* BYTE: `[G]`'s player-count digit, less '0' */
#define MENU_FRAME_COUNTER   (-6) /* LONG: every attract loop's own countdown, one at a time */
#define MENU_FRAME_SLIDESHOW (-8) /* word: how many rooms the slideshow still owes */
#define MENU_FRAME_CHOSE    (-10) /* word: 0 redraws the menu, non-zero returns to `game_top_loop` */
#define MENU_FRAME_LEVEL    (-12) /* word: `[P]`'s parsed level, tens * 10 + units */
#define MENU_FRAME_FOUND_ROW (-14)/* word: where the grid search found it… */
#define MENU_FRAME_FOUND_COL (-16)/* …NEITHER OF WHICH IS INITIALISED. A level 1..35 always matches
                                   * exactly one cell of `room_grid`, so the pair is always written
                                   * before it is read; the original relies on that and so does this */

/* One `jsr` deep: the return address the call pushes, then the callee's own `link` saving A6. What
 * the callee's `link` RESERVES is its own business and is subtracted separately, because only a
 * chain of calls (the hall-of-fame submitter's) ever needs it. */
#define CALL_FRAME_COST       8u
#define SUBMIT_LOCAL_BYTES    0u  /* `link a6,#$0`    @ 0x11d6e */
#define INSERT_LOCAL_BYTES   10u  /* `link a6,#$fff6` @ 0x11f84 */

/* FRAME LAYOUT: `game_top_loop`'s own `link a6,#$fff6` @ 0x101e6. */
#define TOP_LOCAL_BYTES      10u
#define TOP_FRAME_ANIM_HOLD  (-4) /* LONG: the ending animation's two-state tile flip-flop */
#define TOP_FRAME_DELAY     (-10) /* LONG: the four text cards' busy-wait counter */

/* --- the boot sequence, once per run --- */
#define IKBD_MOUSE_OFF     0x12u  /* BIOS `Bconout(4, $12)`: "disable mouse reporting"… */
#define IKBD_MOUSE_RELATIVE 0x8u  /* …and "relative reporting on" once the picture is up. Device 4 is
                                   * the only one the model serves and `os_ikbd_out` takes the byte
                                   * alone, so the device itself is nowhere in this file */

/* --- one game, one turn, one room --- */
#define TOP_START_GRID_ROW    5   /* an ordinary game starts at grid (5, 4), which IS room 1 */
#define TOP_START_GRID_COL    4
#define TOP_LIVES_PER_TURN    5   /* `move.l #$5,-8050(a4)` */
#define TOP_DRIFT_SPEED_ON_ENTRY 0x12c /* `move.w #$12c,-8014(a4)`: the bubble's drift, per room */
#define A_ambient_sfx_countdown 0x22fc0u /* word: frames until the room's own ambience re-triggers.
                                          * Set to 1 as the room opens, decremented once a frame,
                                          * and re-rolled to 20..69 when it goes negative */
#define A_const_ambient_scale 0x24fbcu /* 2.9769999999999967e-06 */
#define A_const_ambient_offset 0x24fc4u /* 20.0 -> a countdown of 20..69 frames */
#define TOP_AMBIENCE_VOLUME   7   /* `muls.w #$7` on `sound_enabled`, one step below the menu's */
#define TOP_BONUS_BAR_FULL 0x13eu /* the bar's right end at the top of every room… */
#define TOP_BONUS_BAR_FLOOR 0x23u /* …and the left end it is emptied down to */
#define TOP_BONUS_STEP        5   /* `subq.w #5`: the tally's step, and the shrink's width */
#define TOP_BONUS_PER_STEP  100   /* `addi.l #$64` @ 0x10a74: what a column is worth on the "WELL
                                   * DONE" path, which is the one that pays double… */
#define TOP_BONUS_PER_STEP_EXIT 50 /* …and `addi.l #$32` @ 0x10c72, the ordinary room exit's half */
#define TOP_BONUS_TICK_RELOAD 2   /* `move.w #$2`: the bar steps once every three frames */
#define TOP_TALLY_NOTE_BASE 100   /* `move.w #$64,d0 / sub.w bonus_bar/4,d0`: the glissando */
#define TOP_TALLY_NOTE_DIVISOR 4
#define TOP_TALLY_VOLUME      8
#define TOP_TALLY_VOICE       2
#define TOP_TALLY_PRIORITY   10
#define TOP_ROOM_BONUS   0x1388   /* `move.w #$1388,d0`: 5,000 for a room… */
#define TOP_DEATH_PENALTY 0x1f4   /* …less 500 for each death in it */
#define TOP_LIVES_MAX         9   /* a spare life is awarded per room, capped here */

#define TOP_EXIT_RIGHT   0x120    /* `cmpi.w #$120,bubble_x`: the room's four exits, in the pixels
                                   * `../notes/frontend.md` §3 derives the play area from */
#define TOP_EXIT_BOTTOM   0x80
#define TOP_ENTRY_DIR_LEFT    0   /* the direction the NEXT room is entered from */
#define TOP_ENTRY_DIR_BOTTOM  1
#define TOP_ENTRY_DIR_RIGHT   2
#define TOP_ENTRY_DIR_TOP     3
#define TOP_ROOM_LAST      0x23   /* room 35, the last of the lap… */
#define TOP_WIN_X          0xc3   /* …which is won by taking the bubble past this x */

/* The "HALF WAY" rooms, which is what the entry-direction override at 0x1061e is really testing:
 * in PRACTICE mode a room is entered from whichever side its own number says, because there is no
 * previous room to have come from. Three ranges and five singletons, transcribed. */
#define TOP_PRACTICE_RIGHT_RANGES { { 1, 5 }, { 0xd, 0x11 }, { 0x19, 0x1d } }
#define TOP_PRACTICE_BOTTOM_ROOMS { 6, 0x12, 0x1e, 0xc, 0x18 }

/* The two room-35 objects the ending animation retires, which is how the door opens: the pair is
 * set to their "open" tiles and then to -1, the tile index `objects_animate_and_draw` skips. */
#define TOP_ENDING_OBJECT_A     3u
#define TOP_ENDING_OBJECT_B     4u
#define TOP_ENDING_TILE_A  0x14eu
#define TOP_ENDING_TILE_B  0x14fu
#define TOP_OBJECT_RETIRED 0xffffu

/* The ending walk, which is two loops over the same flip-flop: the ghost carried right to the door
 * and then down through it. */
#define TOP_ENDING_ANIM_FIRST    4  /* `cmpi.w #$b / bgt`: bubble_frame cycles 4..11 */
#define TOP_ENDING_ANIM_LAST    11
#define TOP_ENDING_HOLD          1  /* `move.l #$1,-4(a6)`: the tile flips every other frame */
#define TOP_ENDING_TILE_LOW   0x2d  /* the two ghost tiles the walk alternates between */
#define TOP_ENDING_TILE_HIGH  0x2e
#define TOP_ENDING_TILE_STEP     5  /* `subq.w #5`: the pop animation walks the ghost tile down */
#define TOP_ENDING_TILE_FLOOR    4
#define TOP_ENDING_WALK_TO   0x100  /* the ghost walks right until bubble_x reaches this… */
#define TOP_ENDING_FALL_TO 0xffe2   /* …and then falls until bubble_y passes -30 */
#define TOP_ENDING_PARK_X     0xa0  /* where the game-over animation parks the popped bubble */
#define TOP_ENDING_PARK_Y     0x40
#define TOP_ENDING_POP_FRAME     3  /* `move.w #$3,bubble_frame`: the popped bubble's own cell */
#define TOP_ENDING_FALL_FRAMES  10  /* `cmpi.w #$a`: ten frames of the ghost at the door */
#define TOP_ENDING_TILE_CEILING 0x28 /* `cmpi.w #$28 / bge`: above this the walk-down is skipped */
#define TOP_ENDING_PEN        0xf /* `Setcolor(15, $777)`: the ghost forced to white for both… */
#define TOP_ENDING_COLOUR  0x777  /* …end-of-room animations */
#define TOP_ENDING_VOICE         2
#define TOP_ENDING_VOLUME        9  /* `muls.w #$9` — the room exit's own trigger uses 8 */
#define TOP_ENDING_PRIORITY    10

#define TOP_CARD_X          0x58  /* the four text cards, which are drawn straight onto the… */
#define TOP_CARD_Y_TOP      0x58  /* …visible screen and held for TOP_CARD_DELAY iterations */
#define TOP_CARD_Y_BOTTOM   0x68
#define TOP_CARD_OUT_X      0x50
#define TOP_CARD_TURN_X     0x50
#define TOP_CARD_TURN_Y     0x60
#define TOP_CARD_DELAY  0x493e0u  /* `cmpi.l #$493e0`: 300,000 empty iterations */
#define TOP_HANDOVER_DELAY 0x186a0u /* …and 100,000 after the handover card */

/* --- the trampoline return addresses, one per `jsr xbios_trap` / `jsr gemdos_trap` site --- */
#define RET_MENU_SETPALETTE       0x11600u
#define RET_MENU_SETSCREEN_PHYS   0x11618u
#define RET_MENU_CRAWCIN          0x116b4u
#define RET_MENU_CCONIS           0x116beu
#define RET_MENU_CNECIN           0x116ccu
#define RET_MENU_SETSCREEN_BACK   0x116e4u
#define RET_MENU_G_SETSCREEN_PHYS 0x11724u
#define RET_MENU_G_CRAWCIN        0x11764u
#define RET_MENU_G_CCONIS         0x1176eu
#define RET_MENU_G_CNECIN         0x1177cu
#define RET_MENU_G_SETSCREEN_BACK 0x117c8u
#define RET_MENU_P_SETSCREEN_PHYS 0x11808u
#define RET_MENU_P_TENS_CRAWCIN   0x1182eu
#define RET_MENU_P_TENS_CCONIS    0x11838u
#define RET_MENU_P_TENS_CNECIN    0x11846u
#define RET_MENU_P_UNITS_CRAWCIN  0x1185cu
#define RET_MENU_P_UNITS_CCONIS   0x11866u
#define RET_MENU_P_UNITS_CNECIN   0x11874u
#define RET_MENU_P_SETSCREEN_BACK 0x1191au
#define RET_DEMO_LENGTH_RANDOM    0x11aeeu
#define RET_DEMO_ROOM_RANDOM      0x11b38u
#define RET_DEMO_VSYNC_A          0x11bd2u
#define RET_DEMO_VSYNC_B          0x11bdcu
#define RET_DEMO_VSYNC_C          0x11be6u
#define RET_HALL_SETPALETTE       0x11cd0u

#define RET_TOP_SETSCREEN_BACK    0x1022au
#define RET_TOP_P1_OUT_PHYS       0x103dcu
#define RET_TOP_P1_OUT_BACK       0x10436u
#define RET_TOP_P2_OUT_PHYS       0x1045cu
#define RET_TOP_P2_OUT_BACK       0x104b6u
#define RET_TOP_TURN_PHYS         0x104fau
#define RET_TOP_TURN_BACK         0x105dcu
#define RET_TOP_AMBIENCE_RANDOM   0x10862u
#define RET_TOP_ENDING_SETCOLOR   0x10930u
#define RET_TOP_EXIT_SETCOLOR     0x10bdcu
#define RET_TOP_GAME_OVER_PHYS    0x10d98u
#define RET_TOP_GAME_OVER_BACK    0x10ddau

/* ================================================================================================
 * Cores
 * ============================================================================================= */

/* HOW `CallerAddressRegisters` TRAVELS, and it is two different things spelt one way.
 *
 * BY VALUE is the default and covers everything below except the loaders. The routine files the
 * caller's A1/A2 in the trampoline's save slots, traps, and returns; nothing it does travels back,
 * so the caller's own register file is unchanged and there is nothing to report.
 *
 * BY POINTER is for a routine whose CALLEES leave A1 somewhere the caller's LATER traps then file.
 * The only such callees in this program are `c_read` and `c_write` (include/clib.h): both ask the
 * fd-mode table through `c_getfdmode`, which returns with A1 at `A_c_errno` and never restores it.
 * So the four loaders and `save_hiscores` — the routines that make several library calls in a row —
 * hold a `live` register block, hand it to each callee, and call the `_reporting` forms that record
 * A1 where the original leaves it. Getting that wrong is not cosmetic: fifteen cases redden when the
 * A1 `c_read` leaves is not tracked, and twelve on the writing side (../STATUS.md's mutation table).
 *
 * A routine here that neither traps twice nor calls the library takes the block BY VALUE, and one
 * that starts calling `c_read`/`c_write` must switch — the differential is what says so. */

/* --- the trap glue, and the two subsystems' entry points ---
 * Every one of them takes the CALLER'S A1/A2: the trampoline files whatever the register file holds
 * and nothing in these routines computes it (docs/agent-playbook.md §5, "a parameter"). */
void    vdi_call(uint8_t *image, CallerAddressRegisters saved);
void    gem_aes(uint8_t *image, uint32_t pblock, CallerAddressRegisters saved);

void    vdi_set_src_mfdb(uint8_t *image, uint32_t mfdb);
void    vdi_set_dst_mfdb(uint8_t *image, uint32_t mfdb);
void    vst_height(uint8_t *image, int16_t handle, int16_t height, uint32_t char_w, uint32_t char_h,
                   uint32_t cell_w, uint32_t cell_h, CallerAddressRegisters saved);
int16_t vst_color(uint8_t *image, int16_t handle, int16_t index, CallerAddressRegisters saved);
int16_t vsf_color(uint8_t *image, int16_t handle, int16_t index, CallerAddressRegisters saved);
void    v_opnvwk(uint8_t *image, uint32_t work_in, uint32_t handle_out, uint32_t work_out,
                 CallerAddressRegisters saved);
void    v_clrwk(uint8_t *image, int16_t handle, CallerAddressRegisters saved);
void    vq_mouse(uint8_t *image, int16_t handle, uint32_t buttons_out, uint32_t x_out,
                 uint32_t y_out, CallerAddressRegisters saved);
void    vq_key_s(uint8_t *image, int16_t handle, uint32_t state_out, CallerAddressRegisters saved);
void    v_gtext(uint8_t *image, int16_t handle, int16_t x, int16_t y, uint32_t text,
                CallerAddressRegisters saved);
void    vr_recfl(uint8_t *image, int16_t handle, uint32_t pxy, CallerAddressRegisters saved);
void    vro_cpyfm(uint8_t *image, int16_t handle, int16_t mode, uint32_t pxy, uint32_t src_mfdb,
                  uint32_t dst_mfdb, CallerAddressRegisters saved);

int16_t aes_crysif(uint8_t *image, int16_t opcode, CallerAddressRegisters saved);
int16_t appl_init(uint8_t *image, CallerAddressRegisters saved);
int16_t graf_handle(uint8_t *image, uint32_t char_w, uint32_t char_h, uint32_t cell_w,
                    uint32_t cell_h, CallerAddressRegisters saved);
void    graf_mouse(uint8_t *image, int16_t mode, uint32_t mform, CallerAddressRegisters saved);

/* --- boot-time setup --- */
void init_gem_and_screens(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);

/* --- the sprite protocol --- */
void build_sprite_bank_grab_cells(uint8_t *image, CallerAddressRegisters saved);
void save_sprite_backgrounds(uint8_t *image, CallerAddressRegisters saved);
void draw_sprites(uint8_t *image, CallerAddressRegisters saved);
void restore_sprite_backgrounds(uint8_t *image, CallerAddressRegisters saved);

/* --- the presentation screen and the file loaders --- */
uint32_t draw_room_to_stage_cell(uint8_t *image, int16_t tile_row, int16_t tile_col,
                                 CallerAddressRegisters live);
void draw_room_to_stage(uint8_t *image, CallerAddressRegisters saved);
void draw_hall_of_fame(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);
/* The three below thread `save_frame` down to `save_hiscores`, whose own A6 is the one frame in this
 * chain that a callee is handed the address of a local from (see `src/frontend.c`'s header). */
/* ...and they thread ONE register file by pointer: `save_hiscores` returns with A1 changed, and the
 * two-player arm's second offer files what the first left (see `src/frontend.c`). */
void save_hiscores_prologue(uint8_t *image, uint32_t frame, CallerAddressRegisters live);
void save_hiscores(uint8_t *image, uint32_t frame, CallerAddressRegisters *live);
void hiscore_insert_and_save(uint8_t *image, uint32_t save_frame, CallerAddressRegisters *live);
void hiscore_submit_players(uint8_t *image, uint32_t save_frame, CallerAddressRegisters *live);

/* THE FIVE CALLS EVERY ANIMATED FRAME OF THIS PROGRAM MAKES, in the order it makes them: the two
 * sprite patches lifted off the work buffer, the sprites drawn, the room shown, the patches put back,
 * and the room's objects ticked. Three subsystems run it — the front end's attract sequence and both
 * end-of-room animations, and `src/gameplay.c`'s death sequence — so it is spelt once, here, where
 * three of the five are declared and `include/blit.h` (above) declares the other two. */
static inline void animation_frame(uint8_t *image, CallerAddressRegisters saved) {
    save_sprite_backgrounds(image, saved);
    draw_sprites(image, saved);
    present_room(image);
    restore_sprite_backgrounds(image, saved);
    objects_animate_and_draw(image);
}

void show_presentation(uint8_t *image, CallerAddressRegisters saved);
void load_demo(uint8_t *image, CallerAddressRegisters saved);
void load_presentation(uint8_t *image, CallerAddressRegisters saved);
void load_level_pictures(uint8_t *image, CallerAddressRegisters saved);
void load_hiscores(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);

/* --- the front end's state machine ---
 * `frame` is the routine's OWN A6: both keep their locals in the image (see the section above), so
 * a mid-entry slice and a whole run are handed the same base. */
void demo_play_record(uint8_t *image, CallerAddressRegisters saved);
void demo_replay_from_record(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);
void menu_attract_sequence(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);
void menu_attract_slideshow(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);
void menu_attract_slideshow_room(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);
void menu_attract_title(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);
void menu_hall_of_fame(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);
void menu_draw(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);
int16_t menu_read_key_and_fold(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);
void menu_ask_player_count(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);
int16_t menu_read_player_count(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);
void menu_ask_practice_level(uint8_t *image, CallerAddressRegisters saved);
void menu_read_level_tens(uint8_t *image, CallerAddressRegisters saved);
void menu_read_level_units(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);
/* ...and the routine's opening, which threads ONE register file by pointer for `save_hiscores`'
 * reason above: the submitter it starts with returns with A1 changed. */
void title_menu_open(uint8_t *image, uint32_t frame, CallerAddressRegisters *live);

/* --- `game_top_loop` @ 0x101e6, slice by slice ---
 * The order they run in is `src/frontend.c`'s header comment for that section; the composition
 * itself is read-verified, because it does not terminate. */
void build_sprite_bank(uint8_t *image, CallerAddressRegisters saved);
void game_top_boot(uint8_t *image, uint32_t frame, CallerAddressRegisters *live);
void game_top_boot_tail(uint8_t *image, uint32_t frame, CallerAddressRegisters *live);
void game_top_free_voice_buffer(uint8_t *image);
void game_top_boot_arm(uint8_t *image, CallerAddressRegisters *live);
void game_new_game(uint8_t *image);
void game_turn_init(uint8_t *image);
void game_player_change(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);
void game_room_setup(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);
void game_room_frame_tail(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);
void game_ending_sequence(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);
void game_room_exit(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);
void game_end_of_turn(uint8_t *image);
void game_over_card(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);

#endif /* BG_FRONTEND_H */
