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

void show_presentation(uint8_t *image, CallerAddressRegisters saved);
void load_demo(uint8_t *image, CallerAddressRegisters saved);
void load_presentation(uint8_t *image, CallerAddressRegisters saved);
void load_level_pictures(uint8_t *image, CallerAddressRegisters saved);
void load_hiscores(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);

#endif /* BG_FRONTEND_H */
