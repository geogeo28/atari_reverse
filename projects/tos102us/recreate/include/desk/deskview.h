/* desk/deskview.h — THE DESK'S WINDOWS: THE VIEW AND ITS LAYOUT LEAVES (`src/desk/deskview.c`; band 6 wave 1b, unit L):
 * twenty-two routines `$fe2a7c..$fe387b` of the ROM's desk, seventeen of them ported in wave 1b. Alcyon C in the ROM,
 * each a `link`, a Line-F return. NAMES: the published GEM desktop's (DESKWIN), each read from its body.
 *
 *   THE VIEW.
 *     $fe2a7c win_view(view, sort)                the view (icons / text) and the sort kept, an item's extent, its
 *                                                 spacing, its pitch and the columns across the desk set
 *     $fe2b64 win_start()                         obj_init, the icon view, every window free, none counted
 *   THE WINDOW LIST (four WNODEs in the desk's 920-byte block, `aes/deskmem.h`).
 *     $fe2ba2 win_alloc(obid)                     the next window: its root object, its pitch, its GEM window; the
 *                                                 WNODE, or 0
 *     $fe2c5c win_free(window)                    the GEM window deleted, the WNODE and its root object freed
 *     $fe2cb8 win_find(handle)                    the WNODE of the GEM window `handle`, or 0
 *     $fe2cf4 win_top(window)                     its root put on top; its drive and path made current
 *     $fe2d46 win_ontop()                         the WNODE whose root is on top (a root of some size), its drive and
 *                                                 path made current; or 0
 *     $fe2dc8 win_cnt(level)                      the WNODE index of the root `level` places along the list
 *     $fe2dfc win_ith(level)                      ...its WNODE
 *   THE LAYOUT LEAVES.
 *     $fe2e12 win_ocalc(window, wfit, hfit, &first)   the view's columns and rows over its files, the part that
 *                                                     fits, the scroll kept inside it; the first file shown out
 *     $fe36fa win_shwall()                        every open window sent the desk's own redraw of its work area
 *     $fe2f0a win_icalc(file)                     the file's ANODE found (a folder's, or a file's) and kept
 *     $fe2f68 win_bldview(window, x, y, w, h)     THE VIEW BUILDER: the window's root at the rectangle, each file it
 *                                                 shows an item object under it — a G_ICON over a copy of its icon,
 *                                                 or the desk's G_USERDEF line —, the sliders' sizes and places set
 *     $fe3760 win_isel(tree, root, current)       the next SELECTED child of `root` after `current`; or 0
 *     $fe37c4 win_iname(object)                   an icon's text: its ICONBLK's ib_ptext
 *     $fe37ee win_sinfo(window)                   the window's info line: the bytes and the files of its path
 *     $fe384c win_sname(window)                   the window's name: its path to the first `*`, a blank at each end
 *
 * WHAT THE C ANSWERS: as `desk/deskwin.h` says — GEM's VOID routines are `void` here, the word the ROM leaves a
 * NAMED, COUNTED DIVERGENCE (`test/test_desk_view.py`).
 */
#ifndef TOS102US_DESK_DESKVIEW_H
#define TOS102US_DESK_DESKVIEW_H

#include "aes/objects.h"
#include "desk/deskfpd.h"
#include "desk/deskglobals.h"

/* ---- the view (its fields of the desk's globals, g_num .. g_xytext, and V_ICON / V_TEXT: `desk/deskglobals.h`) -------- */
/* The text view's item: a line of 43 cells at 320 pixels across, else 45, and a space of none there, else two cells
 * less a pixel; the icon view's space beside an item 8 pixels where the screen is over 300 lines, else none. */
#define LOW_RES_WIDTH         320        /* ($fe2a9e cmpi.w #320,$980a)                                         */
#define TEXT_CELLS_LOW_RES    43         /* ($fe2aa8 moveq #43,d0)                                              */
#define TEXT_CELLS            45         /* ($fe2aac moveq #45,d0)                                              */
#define TALL_SCREEN_LINES     300        /* ($fe2afe cmpi.w #300,$c78e)                                         */
#define ICON_SPACE_TALL       8          /* ($fe2b0c moveq #8,d0)                                               */
#define ITEM_SPACE_UNDER      2          /* ($fe2adc, $fe2b12 move.w #2)                                        */

/* ---- the window list ------------------------------------------------------------------------------------------------- */
#define DESK_WINDOWS          4          /* NUM_WNODES                          ($fe2cea cmp.w #4,d7)           */
/* The window positions the INF keeps (DESK_G_WINDOW_SAVES: one record a window, its rectangle first). */
#define WINDOW_SAVE_BYTES     136        /* ($fe2bc4 muls.w #136,d0)                                            */
#define WINDOW_KIND_ALL       (-1)       /* wind_create's kind: every gadget    ($fe2c3a move.w #-1,-(sp))      */
#define WINDOW_NONE           (-1)       /* wind_create's refusal               ($fe2c46 cmpi.w #-1,6(a5))      */
/* A WNODE: one of the desk's four windows. */
#define WNODE_FLAGS           4          /* word                                ($fe2bf4 clr.w 4(a5))           */
#define WNODE_ID              6          /* word: its GEM window's handle       ($fe2cd0 6(a0,d1.l))            */
#define WNODE_OBID            8          /* word: the icon it was opened from   ($fe2bf8)                       */
#define WNODE_ROOT            10         /* word: its root object               ($fe2bfe)                       */
#define WNODE_CVCOL           12         /* word: the first column shown        ($fe2c02)                       */
#define WNODE_CVROW           14         /* word: the first row shown           ($fe2c06)                       */
#define WNODE_PNCOL           16         /* word: the columns shown             ($fe2c14)                       */
#define WNODE_PNROW           18         /* word: the rows shown                ($fe2c22)                       */
#define WNODE_VNCOL           20         /* word: the view's columns            ($fe2c26)                       */
#define WNODE_VNROW           22         /* word: the view's rows               ($fe2c2a)                       */
#define WNODE_PATH            24         /* long: its PNODE                     ($fe2e26 movea.l 24(a5),a0)     */
#define WNODE_NAME            28         /* bytes: its name, " A:\PATH\ "       ($fe385e lea 28(a5),a3)         */
#define WNODE_NAME_DRIVE      29         /* byte: the name's drive letter       ($fe2d38 move.b 29(a0),d0)      */
#define WNODE_NAME_PATH       32         /* bytes: the name past " A:\"         ($fe2d2e addi.l #32,(sp))       */
#define WNODE_INFO            149        /* bytes: its info line                ($fe3840 addi.l #149,(sp))      */
#define WNODE_BYTES           230        /* ($fe2ccc muls.w #230,d1)                                            */
/* The name a cartridge's window bears: no drive, no path to make current. ROM data. */
#define CARTRIDGE_NAME        0xfef560   /* "Cartridge" ($fe2d1c move.l #$fef560,-(sp))                         */
/* win_free's objc_order: the root put first among its siblings (under every window); win_top's: last (on top). */
#define ORDER_BOTTOM          1          /* ($fe2c92 move.w #1,(sp))                                            */
#define ORDER_TOP             (-1)       /* ($fe2cf8 move.w #-1,(sp))                                           */

/* ---- a PNODE (a path a window shows) and its FNODEs: `desk/deskfpd.h` (unit G's), and the two fields only the info
 * line reads ---------------------------------------------------------------------------------------------------------- */
#define PATH_FILE_COUNT       134        /* word: a PNODE's files               ($fe380e move.w 134(a0))        */
#define PATH_FILE_BYTES       136        /* long: ...and their bytes            ($fe3804 move.l 136(a0))        */

/* ---- win_icalc: a file's ANODE (deskact's app_afind) ------------------------------------------------------------- */
#define FILE_ANODE            34         /* long: f_pa, the file's ANODE         ($fe2f3e move.l d0,34(a5))     */
#define FILE_ISAPP            38         /* word: f_isap, app_afind's answer out ($fe2f1e addi.l #38,(sp))      */
#define AFIND_NOT_ON_THE_DESK 0          /* app_afind's isdesk                   ($fe2f34 clr.w -(sp))          */
#define AFIND_BY_NAME         (-1)       /* ...its object: none, the name decides ($fe2f54 move.w #-1,-(sp))    */
/* (app_afind's types AT_ISFILE / AT_ISFOLD, and the two icon words of an ANODE win_bldview reads, a_aicon / a_dicon:
 * `desk/deskglobals.h`.) */

/* ---- win_bldview: each file of the view an object of the window's root ------------------------------------------- */
#define ITEM_STATE            0x0040     /* every item's ob_state: WHITEBAK      ($fe3040 move.w #64,15912(a0)) */
#define ITEM_FLAGS            0          /* ...its ob_flags                      ($fe3050 clr.w 15910(a0))      */
/* The text view's items: G_USERDEF objects, each over a USERBLK of the desk's (DESK_G_USERBLKS; its UB_CODE / UB_PARM
 * `aes/objects.h`'s) — the desk's draw code, the FNODE's fields from f_attr on. */
#define USERBLK_BYTES         8          /* ($fe3070 asl.w #3,d1)                                               */
#define AES_DESK_USERDEF_CODE 0x8c32     /* long: the desk's draw code's address ($fe3094 move.l $8c32,5580(a0)) */
/* The icon view's items: G_ICON objects, each over an ICONBLK of the desk's (DESK_G_ICONS) — a copy of the icon's
 * template (DESK_MASK_ICONBLKS), its text the file's name; and the icon each object shows, kept (DESK_G_INDEX). */
/* The window's sliders: their sizes and places in thousandths. */
#define SLIDER_SCALE          1000       /* ($fe31e2 move.w #1000,-(sp))                                        */
/* THE BUILDER'S PART OF THE VIEW'S FRAME: the file cursor win_ocalc answers into, then the two words of wind_get's
 * answers it keeps (the slider's size, and one word all three others are answered into). */
#define BLDVIEW_FIRST_FILE    0          /* long                                ($fe2f8e -4(a6))               */
#define BLDVIEW_SLIDER        4          /* word                                ($fe3222 -26(a6))              */
#define BLDVIEW_UNREAD        6          /* word                                ($fe320a -16(a6))              */

/* ---- the info line ---------------------------------------------------------------------------------------------------- */
#define STINFOST              0          /* the free string of the info line's template ($fe381c clr.w -(sp)), its
                                          * address kept in DESK_G_ALERT                                         */
/* merge_str's parameters (`aes/strings.h`, a longword slot each): the bytes, then the count — a WORD in the second
 * slot's first half, as %W reads it. Its own `link` locals in the ROM: -6(a6) and -2(a6). */
#define SINFO_SIZE            0          /* long                                ($fe3804 move.l ...,-6(a6))     */
#define SINFO_COUNT           4          /* word                                ($fe380e move.w ...,-2(a6))     */
/* THE VIEW'S FRAME — the words a routine of the unit hands on BY ADDRESS, its `link` locals in the ROM: win_sinfo's
 * parameters (6 bytes), win_shwall's work area. ONE layout: no routine of the unit calls another while it holds it. */
#define VIEW_FRAME_BYTES      GRECT_BYTES /* win_shwall's -8(a6) rectangle, the widest                          */

#ifndef __ASSEMBLER__
#include <stdint.h>

void aes_win_view(uint8_t *image, int16_t view, int16_t sort);                                        /* $fe2a7c */
void aes_win_start(uint8_t *image);                                                                   /* $fe2b64 */
uint32_t aes_win_alloc(uint8_t *image, int16_t obid);                                                  /* $fe2ba2 */
void aes_win_free(uint8_t *image, uint32_t window);                                                    /* $fe2c5c */
uint32_t aes_win_find(uint8_t *image, int16_t handle);                                                 /* $fe2cb8 */
void aes_win_top(uint8_t *image, uint32_t window);                                                     /* $fe2cf4 */
uint32_t aes_win_ontop(uint8_t *image);                                                               /* $fe2d46 */
int16_t aes_win_cnt(uint8_t *image, int16_t level);                                                    /* $fe2dc8 */
uint32_t aes_win_ith(uint8_t *image, int16_t level);                                                   /* $fe2dfc */
void aes_win_ocalc(uint8_t *image, uint32_t window, int16_t wfit, int16_t hfit, uint32_t first_out);   /* $fe2e12 */
void aes_win_icalc(uint8_t *image, uint32_t file);                                                     /* $fe2f0a */
void aes_win_bldview(uint8_t *image, uint32_t window, int16_t x, int16_t y, int16_t w, int16_t h);      /* $fe2f68 */
void aes_win_shwall(uint8_t *image);                                                                  /* $fe36fa */
int16_t aes_win_isel(uint8_t *image, uint32_t tree, int16_t root, int16_t current);                    /* $fe3760 */
uint32_t aes_win_iname(uint8_t *image, int16_t object);                                                /* $fe37c4 */
void aes_win_sinfo(uint8_t *image, uint32_t window);                                                   /* $fe37ee */
void aes_win_sname(uint8_t *image, uint32_t window);                                                   /* $fe384c */
#endif

#endif /* TOS102US_DESK_DESKVIEW_H */
