/* desk/deskwin.h — THE DESK'S WINDOW OBJECTS AND ITS PROGRAM LEAVES (`src/desk/deskwin.c`; band 6 wave 1b, unit I):
 * twenty-one routines `$fe0776..$fe1067` of the ROM's desk, sixteen of them ported in wave 1b. Alcyon C in the ROM,
 * each a `link`, a Line-F return. NAMES: the published GEM desktop's (DESKOBJ, DESKPRO, DESKWIN), each read from its
 * body.
 *
 *   THE SCREEN'S OBJECTS (deskobj): one tree of 133 objects in the desk's globals — the root, its five children
 *   (the desktop's and the four windows' roots), and from object 6 on the icons each window shows.
 *     $fe0776 obj_init()                              every object unlinked, the root the screen's size, its five
 *                                                     children added
 *     $fe0840 obj_walloc(x, y, w, h)                  the first window root of no size (2..5) given the rectangle;
 *                                                     the object, or 0
 *     $fe08b4 obj_wfree(object, x, y, w, h)           a window root given the rectangle, its icons unlinked
 *     $fe0942 obj_ialloc(parent, x, y, w, h)          the first unlinked icon object (6..132) added under `parent`;
 *                                                     the object, or 0
 *   THE PROGRAM LEAVES (deskpro).
 *     $fe09cc pro_chdir(drive, path)                  the drive and the path made current (99: none, the glue's
 *                                                     verdict cleared); 1
 *     $fe0a7c pro_cmd(command, tail, unread, byte)    the command and the tail kept for the launch, the tail's
 *                                                     count byte the caller's; 1
 *     $fe0b26 pro_exec(isgraf, isover, command, tail) the hourglass, then shel_write: its answer
 *     $fe0b56 desk_rsrc_load()                        the desk's resource: rom_ram's part 1 over the desk's global[]; 1
 *     $fe0b6e ini_tree(answer, index)                 rsrc_gaddr of a tree; its answer
 *     $fe0b86 ini_str(index)                          a free string copied into the desk's long-string buffer; the
 *                                                     buffer's address
 *   THE WINDOW LEAVES (deskwin).
 *     $fe0c9a do_wredraw(window, x, y, w, h)          the window's objects drawn over its rectangle list, clipped to
 *                                                     the caller's rectangle and the screen, the cursor hidden
 *     $fe0d5a get_xywh(tree, object, &x, &y, &w, &h)  an object's four words out
 *     $fe0db8 get_spec(tree, object)                  an object's ob_spec
 *     $fe0dce do_xyfix(&x, &y)                        a window's corner put on a 16-pixel column, below the desk's top
 *     $fe0f36 zoom_closed(close, window, x, y)        the window closed (where asked) and a box shrunk to the icon
 *     $fe0f9c do_wfull(window)                        the window made full, or back to its previous size
 *
 * WHAT THE C ANSWERS (ruling W3-R5's kind: NOT DECIDED HERE). The ROM's routine returns by its Line-F word with D0
 * as its last instruction left it. Where GEM's routine is VOID the C is `void` — the most direct C — and the word
 * the ROM leaves (a callee's, or its own last store's) is a NAMED, COUNTED DIVERGENCE the battery holds
 * (`test/test_desk_win.py`), with who reads it (`aes_deskbind.answer_readers`).
 *
 * THE DESK's GLOBALS: one block the desk allocates at its start (`AES_DESK_GLOBALS`, `aes/aes.h`), every field an
 * offset into it, named by the field of GEM's GLOBES it holds — all of them in `desk/deskglobals.h`.
 */
#ifndef TOS102US_DESK_DESKWIN_H
#define TOS102US_DESK_DESKWIN_H

#include "aes/objects.h"
#include "desk/deskglobals.h"

/* ---- the screen's objects (g_screen, the tree inline: `desk/deskglobals.h`) ------------------------------------------- */
#define DESK_SCREEN_OBJECTS   133        /* NUM_SOBS                            ($fe07c8 cmp.w #133,d7)         */
#define DESK_ROOT_CHILDREN    5          /* the desktop's root and the windows' ($fe0838 cmp.w #5,d7)           */
#define DESK_FIRST_WINDOW_ROOT 2         /* ...the windows' from object 2 on: obj_walloc's `d7 + 1` from 1       */
#define DESK_FIRST_ICON_OBJECT 6         /* WOBS_START                          ($fe0950 moveq #6,d7)           */
/* The two sample objects obj_init copies (gl_sampob): the root's, and every child's. ROM data. */
#define DESK_SAMPLE_ROOT      0xfef5ec   /* ($fe07d6 move.l #$fef5ec,-(sp))                                     */
#define DESK_SAMPLE_CHILD     0xfef604   /* ($fe081a move.l #$fef604,-(sp))                                     */

/* (The launch's command and tail, g_cmd / g_tail, and ini_str's g_lngstr: `desk/deskglobals.h`.) */

/* ---- pro_chdir ------------------------------------------------------------------------------------------------------- */
#define DESK_NO_DRIVE         99         /* "no drive": nothing made current    ($fe09d8 cmpi.w #99,8(a6))      */
/* Its path is built in the desk's 512-byte block (`aes/deskmem.h`, AES_DESK_BLOCK_512) from byte 256: a backslash,
 * the caller's path, cut at its first blank or `*` (`aes/strings.h`: $fe0a2c cmpi.b #32, $fe0a3e cmpi.b #42). */
#define CHDIR_PATH            256        /* ($fe0a02 move.b #92,256(a0))                                        */
#define CHDIR_PATH_ROOT       '\\'
#define CHDIR_PATH_TEXT       (CHDIR_PATH + 1)  /* ($fe0a0c addi.l #257,(sp))                                    */
#define PRO_DONE              1          /* pro_chdir's, pro_cmd's and desk_rsrc_load's answer (`moveq #1,d0`) */

/* ---- pro_exec ------------------------------------------------------------------------------------------------------- */
#define SHEL_WRITE_EXECUTE    1          /* shel_write's doexec                 ($fe0b40 move.w #1,-(sp))       */

/* ---- the window leaves ----------------------------------------------------------------------------------------------- */
/* (do_wredraw's root where no window is named: the desktop's root object, `desk/deskglobals.h`'s DESKTOP_ROOT.) */
#define REDRAW_DEPTH          8          /* objc_draw's depth: MAX_DEPTH         ($fe0d16 move.w #8,-(sp))       */
#define WINDOW_DESKTOP        0          /* window 0, the desktop: do_xyfix's wind_get ($fe0df2 clr.w -(sp))    */
/* do_xyfix's column: a corner's x put on a multiple of 16, the next one where it lies past the middle of its own. */
#define XYFIX_COLUMN_MASK     0xfff0     /* ($fe0e14 and.w #-16,d0)                                             */
#define XYFIX_IN_COLUMN_MASK  0x000f     /* ($fe0e04 and.w #15,d0)                                              */
#define XYFIX_COLUMN          16         /* ($fe0e24 add.w #16,d0)                                              */
#define XYFIX_HALF_COLUMN     8          /* ($fe0e0a cmpi.w #8,(a5))                                            */

/* THE WINDOW LEAVES' FRAME — the words a leaf hands an AES binding or a rectangle routine BY ADDRESS, its own `link`
 * locals in the ROM. ONE layout for the unit: no routine of it calls another of it while it holds the frame. The
 * widest is do_wfull's three rectangles. */
#define WIN_FRAME_FIRST_RECT  0          /* bytes[GRECT_BYTES]: a GRECT a binding answers into, or the clip     */
#define WIN_FRAME_SECOND_RECT GRECT_BYTES
#define WIN_FRAME_THIRD_RECT  (2 * GRECT_BYTES)
#define WIN_FRAME_BYTES       (3 * GRECT_BYTES)   /* do_wfull's: -8(a6), -16(a6), -24(a6)                        */
#define WIN_FRAME_STRING      0          /* long: the free string's address rsrc_gaddr answers ($fe0b8a -4(a6)) */

#ifndef __ASSEMBLER__
#include <stdint.h>

void aes_obj_init(uint8_t *image);                                                                    /* $fe0776 */
int16_t aes_obj_walloc(uint8_t *image, int16_t x, int16_t y, int16_t w, int16_t h);                    /* $fe0840 */
void aes_obj_wfree(uint8_t *image, int16_t object, int16_t x, int16_t y, int16_t w, int16_t h);        /* $fe08b4 */
int16_t aes_obj_ialloc(uint8_t *image, int16_t parent, int16_t x, int16_t y, int16_t w, int16_t h);    /* $fe0942 */
int16_t aes_pro_chdir(uint8_t *image, int16_t drive, uint32_t path);                                   /* $fe09cc */
int16_t aes_pro_cmd(uint8_t *image, uint32_t command, uint32_t tail, int16_t unread, int16_t tail_byte); /* $fe0a7c */
int16_t aes_pro_exec(uint8_t *image, int16_t isgraf, int16_t isover, uint32_t command, uint32_t tail);  /* $fe0b26 */
int16_t aes_desk_rsrc_load(uint8_t *image);                                                           /* $fe0b56 */
int16_t aes_ini_tree(uint8_t *image, uint32_t answer, int16_t index);                                  /* $fe0b6e */
uint32_t aes_ini_str(uint8_t *image, int16_t index);                                                   /* $fe0b86 */
void aes_do_wredraw(uint8_t *image, int16_t window, int16_t x, int16_t y, int16_t w, int16_t h);        /* $fe0c9a */
void aes_get_xywh(uint8_t *image, uint32_t tree, int16_t object, uint32_t x_out, uint32_t y_out, uint32_t w_out,
                  uint32_t h_out);                                                                     /* $fe0d5a */
uint32_t aes_get_spec(uint8_t *image, uint32_t tree, int16_t object);                                  /* $fe0db8 */
void aes_do_xyfix(uint8_t *image, uint32_t x_inout, uint32_t y_inout);                                 /* $fe0dce */
void aes_zoom_closed(uint8_t *image, int16_t close, int16_t window, int16_t icon_x, int16_t icon_y);   /* $fe0f36 */
void aes_do_wfull(uint8_t *image, int16_t window);                                                     /* $fe0f9c */
#endif

#endif /* TOS102US_DESK_DESKWIN_H */
