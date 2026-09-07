/* display_list.h — THE THREE RECORD ARRAYS `render_frame` @ 0x14446 READS AND WRITES, FROZEN.
 *
 * Every subsystem that publishes something on screen writes a display record; only `render_frame`
 * reads one. Every subsystem that draws leaves dirt; only `render_frame` repairs it. So the layouts
 * below are what a dozen unrelated routines have to agree on, and they are frozen HERE, in one
 * block nobody adds to — `../README.md`, "FREEZE a shared record layout in one block", and
 * `docs/agent-playbook.md` §11 for the argument. A publisher includes this header to learn where
 * a field is; it does not restate one, and it does not extend this file.
 *
 * THE ONLY PERMITTED EDIT is upgrading a field's tag from `names.txt, unpinned` to
 * `pinned by <test>`, in the same change that ports the routine which pins it. "Append in offset
 * order" is the rule that looks right and is not: inserting at an offset is not appending.
 *
 * WHAT IS NOT HERE. `A_sprite_restore_lists`, `SPRITE_RESTORE_LISTS`, `SPRITE_RESTORE_LIST_BYTES`,
 * `SPRITE_RESTORE_FIRST_ENTRY` and `SPRITE_RESTORE_TERMINATOR` are the memory model's — the boot
 * chain places the four lists and writes their terminators, so `include/globals.h` owns them and
 * this file adds only the six-byte RECORD inside one. Likewise the sprite bank's own 20-byte
 * directory record, which is `include/sprite.h`'s.
 */
#ifndef FS_DISPLAY_LIST_H
#define FS_DISPLAY_LIST_H

#include "globals.h"

/* ---- the display list: 223 six-byte records at 0x177ce ---------------------------------------
 *
 * `render_frame` walks it twice per frame with `lea $177ce,a6` @ 0x1447e / @ 0x1469c and
 * `lea 6(a6),a6 / cmpa.l #$17d08,a6 / blt` @ 0x145b6 and @ 0x14756 — which is where the stride,
 * the base and the one-past-the-end limit below are read off. `clear_display_list` @ 0x115a8
 * byte-clears the same span.
 */
#define A_display_list       0x177ceu /* `lea $177ce.l,a6` @ 0x1447e — pinned by test_sprite.py */
#define A_display_list_end   0x17d08u /* `cmpa.l #$17d08,a6` @ 0x145ba — one past the last record */
#define DISPLAY_REC_BYTES    6u       /* `lea 6(a6),a6` @ 0x145b6 — pinned by test_sprite.py */
#define DISPLAY_LIST_RECORDS 223u     /* = (A_display_list_end - A_display_list) / DISPLAY_REC_BYTES */

#define DISPLAY_REC_X      0u  /* WORD, screen x BEFORE the sprite record's own draw offset;
                                * `move.w (a6),d0 / add.w 8(a4),d0` @ 0x1444c — pinned by
                                * test_sprite.py::test_render_frame_draws_one_pass_a_sprite */
#define DISPLAY_REC_Y      2u  /* WORD, screen y, likewise; `move.w 2(a6),d1 / add.w 10(a4),d1`
                                * @ 0x144be — pinned by the same case */
#define DISPLAY_REC_FRAME  4u  /* BYTE, an UNSIGNED index into the sprite bank's 256-record
                                * directory: `clr.w d0 / move.b 4(a6),d0` then *20 @ 0x144a8 —
                                * pinned by test_sprite.py::test_render_frame_draws_one_pass_a_sprite */
#define DISPLAY_REC_ACTIVE 5u  /* BYTE, the pass gate; `tst.b 5(a6)` @ 0x14496 and @ 0x146a2 —
                                * pinned by test_render_frame_passes_are_selected_by_the_active_byte */

/* The three states the active byte has, as the two `tst.b`s read it. Pass A is `bpl` -> skip, so
 * the pass-A set is every byte with bit 7 SET; pass B is `bmi` -> skip AND `beq` -> skip, so it is
 * 0x01..0x7f. The game writes 0xff and 1 (`../notes/gameplay.md` §3.1); the ranges are the code's. */
#define DISPLAY_ACTIVE_PASS_A_BIT     0x80u /* the bit the two `tst.b`s branch on */
#define DISPLAY_ACTIVE_HIDDEN         0x00u /* neither pass draws it */
#define DISPLAY_ACTIVE_UNDER_SCENERY  0xffu /* pass A: drawn, then the overlay tiles repaint OVER it */
#define DISPLAY_ACTIVE_ON_TOP         0x01u /* pass B: drawn last, over everything */
#define DISPLAY_ACTIVE_ON_TOP_MAX     0x7fu /* ...and the largest byte `bmi` still lets into pass B */

/* ---- one record inside a sprite restore list --------------------------------------------------
 *
 * `render_frame` appends `move.w d0,(a5)+ / move.w d2,(a5)+ / move.w d7,(a5)+` @ 0x1451e (pass A)
 * and @ 0x1472c (pass B), and the replay reads `move.w (a5),d0` / `move.w 2(a5),d0` /
 * `move.w 4(a5),d7` with `lea 6(a5),a5` @ 0x1492a..0x14958. The list ENDS at the first record whose
 * CLASS word is negative — `move.w 2(a5),d0 / bmi` @ 0x1494a — which is why `include/globals.h`'s
 * SPRITE_RESTORE_FIRST_ENTRY is 2 and not 0, and why render_frame's own terminator store is
 * `move.w #$ffff,2(a5)` @ 0x14764 rather than `(a5)`.
 */
#define SPRITE_RESTORE_REC_BYTES  6u
#define SPRITE_RESTORE_OFFSET     0u /* WORD, SIGNED: the byte offset of the sprite's top-left group
                                      * from a screen base. Added with `adda.w` @ 0x14938, so a
                                      * sprite clipped at the left edge carries a NEGATIVE offset.
                                      * pinned by test_sprite.py::test_render_frame_restore_record */
#define SPRITE_RESTORE_CLASS      2u /* WORD: the sprite's width class 0..3, or RESTORE_CLASS_W16 (4)
                                      * where a right-edge clip narrowed it; 0xffff terminates.
                                      * pinned by test_sprite.py::test_render_frame_restore_record */
#define SPRITE_RESTORE_ROWS       4u /* WORD: the CLIPPED row count, as a `dbf` count (rows - 1).
                                      * pinned by test_sprite.py::test_render_frame_restore_record */

/* ---- the tile repair grid: one word per 32x32 map cell on screen, at 0x17e0c ------------------
 *
 * Pass A copies the OVERLAY tile id of every cell a sprite touches out of `map_row_ptr` into the
 * matching word here (`move.b 1(a3,d0.w),1(a2,d0.w)` @ 0x14550 and its three neighbours), and the
 * repaint pass drains it, clearing each word as it goes (`clr.w -2(a0)` @ 0x145de). The word index
 * is the MAP's: 10 cells to a row, two bytes each, so one index walks the map and the grid alike.
 */
#define A_tile_repair_grid     0x17e0cu /* `lea $17e0c.l,a2` @ 0x14544 — pinned by test_sprite.py */
#define TILE_REPAIR_COLUMNS    10u      /* `cmpi.w #$14,d0` @ 0x14688 over a byte cursor: 10 words */
#define TILE_REPAIR_ROW_BYTES  20u      /* ...the same 0x14, as the map's own row stride */
/* The id sits in the LOW byte of the word, because the map cell's overlay is its ODD byte and the
 * copy is `move.b 1(a3,d0.w),1(a2,d0.w)` — the high byte of a grid word is never written and the
 * drain reads the whole word (`move.w (a0)+,d2` @ 0x145d8). */
#define TILE_REPAIR_ID_BYTE    1u

#endif /* FS_DISPLAY_LIST_H */
