/* desk/deskact.h — THE DESK'S HIT TESTS AND ICON DRAGS, unit B (`src/desk/deskact.c`): the routines `$fdc080..$fdcc29`
 * of band 6 wave 1b — which object a point or a rectangle touches, the outlines a drag carries, the states of the
 * icons it changes — and app_afind, the ANODE an icon or a file's name is shown by, filed among them. Band 6 wave 2
 * (group G4) adds the three wave 1b left: gr_drgplns `$fdc57a` (the drag's loop), act_bsclick `$fdcc2a` (a click's
 * selection) and act_bdown `$fdcd34` (a press: a drag, or a rubber box).
 *
 * NAMES: the published GEM desktop's (DESKACT, and DESKAPP's app_afind), each read from its body.
 *
 * WHAT A ROM CALLER READS IN D0 WHERE THE C ANSWERS NOTHING: the void routines here (gr_accobs, move_drvicon,
 * gr_extent, gr_obalign, gr_plns, act_allchg; wave 2's gr_drgplns and act_bsclick) leave their last callee's or
 * instruction's D0 in the ROM — counted and read by no caller (`test/test_desk_act.py`).
 */
#ifndef TOS102US_DESK_DESKACT_H
#define TOS102US_DESK_DESKACT_H

#include "aes/objects.h"
#include "desk/deskglobals.h"

/* (The desk's globals these routines read, an ANODE's layout, the desktop's root and the two views:
 * `desk/deskglobals.h`.) */

/* What app_afind answers through `isapp` for a file's name: matched as the node's data, or as its application. */
#define APP_AFIND_DATA        0          /* ($fdc0d4 clr.w (a4))                                               */
#define APP_AFIND_APPLICATION 1          /* ($fdc0e8 move.w #1,(a4))                                           */

/* ---- the hit tests ----------------------------------------------------------------------------------------------- */
#define DESK_TEXT_LINE_CHARS  45         /* a text view's line, in characters   ($fdc8f0 muls.w #45)           */
#define GR_OBFIND_DEPTH       2          /* objc_find's depth: the root's icons ($fdc116 move.w #2,-(sp))      */
#define GR_OBFIND_POINT_SIZE  1          /* act_chkobj's rectangle: the point   ($fdc132, $fdc136 #1)           */

/* ---- a drag's outlines --------------------------------------------------------------------------------------------- */
#define GR_ACCOBS_MAX         60         /* MAX_OBS: the icons whose corners are kept ($fdc24a cmp.w #60,d6)    */
#define GR_EXTENT_FAR         10000      /* the least corner's start            ($fdc3a8 move.w #10000,d5)     */
/* gr_isdown's evnt_multi: the button or the mouse leaving / entering the rectangle; one click of the left button
 * awaited UP (state 0). The answers it does not hand on lie in its own frame: */
#define GR_ISDOWN_CLICKS      1          /* ($fdc194 move.l #$00010001: the clicks and the mask)               */
#define GR_ISDOWN_MASK        1
#define GR_ISDOWN_STATE       0          /* ($fdc192 clr.w -(sp))                                              */
#define GR_ISDOWN_DOWN        1          /* the answer: no button event came — the button is still down ($fdc1b6) */
#define GR_ISDOWN_UP          0
#define GR_ISDOWN_CLICKS_ANSWER 0        /* word: evnt_multi's clicks answer    ($fdc15c -16(a6) — the 6th)    */
#define GR_ISDOWN_KEY_ANSWER  2          /* word: ...and its key                ($fdc164 -14(a6) — the 5th)    */
#define GR_ISDOWN_FRAME_BYTES 4
/* gr_bwait's: the mouse LEAVING a 2-pixel square round where the drag stands, and the four answers it reads none of. */
#define GR_BWAIT_LEAVE        1          /* ($fdc552 move.w #1,-(sp))                                          */
#define GR_BWAIT_BOX          2          /* ($fdc548 move.l #$00020002: the square's width and height)         */
#define GR_BWAIT_MOUSE_X      0          /* word                                ($fdc540 -10(a6))              */
#define GR_BWAIT_MOUSE_Y      2          /* word                                ($fdc53c -8(a6))               */
#define GR_BWAIT_BUTTON       4          /* word                                ($fdc538 -6(a6))               */
#define GR_BWAIT_KEYS         6          /* word                                ($fdc534 -4(a6))               */
#define GR_BWAIT_FRAME_BYTES  8

/* ---- the state changes --------------------------------------------------------------------------------------------- */
/* act_chkobj's two rectangles: the icon's / the line's (`t`) and the one tested against it (`m`). */
#define ACT_CHKOBJ_TESTED     0          /* bytes[GRECT_BYTES]: m               ($fdc876 lea -18(a6),a3)       */
#define ACT_CHKOBJ_OBJECT     GRECT_BYTES /* bytes[GRECT_BYTES]: t              ($fdc8fa -10(a6))              */
#define ACT_CHKOBJ_FRAME_BYTES (2 * GRECT_BYTES)
#define MOVE_DRVICON_REDRAWN  0          /* do_wredraw's window: the desktop's  ($fdc358 clr.w -(sp))          */
#define ACT_CHG_FRAME_BYTES   GRECT_BYTES /* the object's rectangle on the screen ($fdc9f4 lea -10(a6),a3)    */
#define ACT_CHG_OBJC_CHANGE_UNREAD 0     /* objc_change's word between the object and the clip ($fdca82 clr.w) */
#define ACT_CHG_NO_REDRAW     0          /* ...and its redraw flag              ($fdca78 clr.w (sp))           */
#define ACT_CHG_REFUSED       0          /* a disabled object, the check asked  ($fdca1c clr.w d0)             */
#define ACT_CHG_DONE          1          /* ($fdcab8 moveq #1,d0)                                              */
/* act_allchg's two: the extent of what changed (`a`), and one icon's rectangle (`o`). */
#define ACT_ALLCHG_EXTENT     0          /* bytes[GRECT_BYTES]                  ($fdcac8 lea -20(a6),a3)       */
#define ACT_ALLCHG_OBJECT     GRECT_BYTES /* bytes[GRECT_BYTES]                 ($fdcac4 lea -12(a6),a4)       */
#define ACT_ALLCHG_FRAME_BYTES (2 * GRECT_BYTES)

/* ---- band 6 wave 2: the drag's loop and the button's two handlers --------------------------------------------------- */
/* gr_drgplns: the outline XORed (line colour 1) over the whole screen's clip; the icons' rectangle's frame and the
 * words the loop hands on BY ADDRESS — laid in ONE slot as the ROM's frame lays them (-56..-30(a6)), then the two
 * argument words graf_mkstate writes in place (8/10(a6): its own arguments, read back). */
#define DRGPLNS_OUTLINE_COLOUR 1         /* ($fdc604 move.w #1,(sp))                                            */
#define DRGPLNS_OUTLINE_EXTENT 0         /* bytes[GRECT_BYTES]: gr_extent of the outline ($fdc594 -56(a6))      */
#define DRGPLNS_ICONS_RECT    8          /* bytes[GRECT_BYTES]: ...of the icons' corners, grown by it ($fdc5a6 -48) */
#define DRGPLNS_FNODE         16         /* long: i_find's FNODE answer          ($fdc7ae -40(a6))             */
#define DRGPLNS_IS_APP        20         /* word: ...and its is-a-program        ($fdc7a6 -36(a6))             */
#define DRGPLNS_KEYS          22         /* word: graf_mkstate's keys            ($fdc614 -34(a6))             */
#define DRGPLNS_BUTTON        24         /* word: ...and its button              ($fdc61c -32(a6))             */
#define DRGPLNS_MOUSE_X       26         /* word: in_mx, the argument graf_mkstate writes ($fdc62c 8(a6))      */
#define DRGPLNS_MOUSE_Y       28         /* word: in_my                          ($fdc624 10(a6))              */
#define DRGPLNS_FRAME_BYTES   30
#define DRGPLNS_NO_OBJECT     0          /* the object lit last: none            ($fdc5f8 clr.w -22(a6))        */
/* act_bdown: a press on no icon starts a rubber box from a 6 by 6 square; a press on a selected icon drags the
 * selection, its outline the view's (the desktop's root is always icons). What it answers: the window the drag let
 * go over, or ACT_BDOWN_NOTHING where none was (or the drop is no move: onto itself, or a desktop icon put down).
 * Its frame's words handed on BY ADDRESS in ONE slot — the box, the drop's corner and window, the button, the
 * selection's count — and the three argument words evnt_button writes in place (16/18/20(a6), read by no one). */
#define RUBBER_BOX_MIN        6          /* ($fdcd80 move.w #6,(sp); $fdcd9e move.l #$60006)                    */
#define ACT_BDOWN_NOTHING     (-1)       /* ($fdcd52 move.w #-1,-8(a6))                                        */
#define ACT_BDOWN_BOX         0          /* bytes[GRECT_BYTES]: the rubber box   ($fdcd48 lea -28(a6),a3)       */
#define ACT_BDOWN_DROP_Y      8          /* word: gr_drgplns's corner, down      ($fdce50 -12(a6))             */
#define ACT_BDOWN_DROP_X      10         /* word: ...across                      ($fdce58 -10(a6))             */
#define ACT_BDOWN_DROP_WINDOW 12         /* word: ...and the window let go over  ($fdce4c -8(a6))              */
#define ACT_BDOWN_BUTTON      14         /* word: evnt_button's button           ($fdcedc -6(a6))              */
#define ACT_BDOWN_COUNT       16         /* word: gr_accobs's count              ($fdcdfa -4(a6))              */
#define ACT_BDOWN_MOUSE_X     18         /* word: in_mx, the argument evnt_button writes ($fdcee8 16(a6))       */
#define ACT_BDOWN_MOUSE_Y     20         /* word: in_my                          ($fdcee0 18(a6))              */
#define ACT_BDOWN_KEYS        22         /* word: keystate                       ($fdced4 20(a6))              */
#define ACT_BDOWN_FRAME_BYTES 24
#define ACT_BDOWN_CLICKS      1          /* evnt_button: one click of the left button, awaited up ($fdcef0 #$10001) */
#define ACT_BDOWN_MASK        1
#define ACT_BDOWN_STATE       0          /* ($fdceee clr.w -(sp))                                              */
/* act_bsclick: a click with a Shift key down toggles the icon alone (the keys' low two bits). */
#define SHIFT_KEYS            0x0003     /* ($fdcc42 btst #1 / $fdcc4a btst #0, 21(a6))                        */

#ifndef __ASSEMBLER__
#include <stdint.h>

uint32_t aes_app_afind(uint8_t *image, int16_t isdesk, int16_t type, int16_t obid, uint32_t name,
                       uint32_t isapp_out);                                                           /* $fdc080 */
int16_t aes_gr_obfind(uint8_t *image, uint32_t tree, int16_t root, int16_t mx, int16_t my);           /* $fdc0fa */
int16_t aes_gr_isdown(uint8_t *image, int16_t leave, int16_t x, int16_t y, int16_t w, int16_t h, uint32_t mouse_x_out,
                      uint32_t mouse_y_out, uint32_t buttons_out, uint32_t keys_out);                 /* $fdc152 */
void aes_gr_accobs(uint8_t *image, uint32_t tree, int16_t root, uint32_t count_out, uint32_t points); /* $fdc1ba */
void aes_gr_extent(uint8_t *image, int16_t count, uint32_t points, uint32_t rect);                    /* $fdc398 */
void aes_gr_obalign(uint8_t *image, int16_t count, int16_t x, int16_t y, uint32_t points);            /* $fdc458 */
void aes_gr_plns(uint8_t *image, int16_t x, int16_t y, int16_t count, uint32_t outline, int16_t icons,
                 uint32_t corners);                                                                   /* $fdc49a */
int16_t aes_gr_bwait(uint8_t *image, uint32_t rect, int16_t mx, int16_t my, int16_t count, uint32_t outline,
                     int16_t icons, uint32_t corners);                                                /* $fdc4fe */
int16_t aes_act_chkobj(uint8_t *image, uint32_t tree, int16_t root, int16_t obj, int16_t x, int16_t y, int16_t w,
                       int16_t h);                                                                    /* $fdc86e */
/* ...and the three that redraw through unit I's do_wredraw (`desk/deskwin.h`) or move a desktop icon through unit A's
 * snap_disk (`desk/deskapp.h`). */
void aes_move_drvicon(uint8_t *image, uint32_t tree, int16_t root, int16_t x, int16_t y, uint32_t corners); /* $fdc268 */
int16_t aes_act_chg(uint8_t *image, int16_t window, uint32_t tree, int16_t root, int16_t obj, uint32_t clip, int16_t value,
                    int16_t set, int16_t draw, int16_t check_disabled);                               /* $fdc9e4 */
void aes_act_allchg(uint8_t *image, int16_t window, uint32_t tree, int16_t root, int16_t except, uint32_t rect,
                    uint32_t clip, int16_t value, int16_t set, int16_t draw);                         /* $fdcabc */
/* ...and wave 2's: the drag's loop, the button's click and press (i_find, unit K's: `desk/desktop.h`). */
void aes_gr_drgplns(uint8_t *image, int16_t mx, int16_t my, uint32_t clip, int16_t count, uint32_t outline, int16_t icons,
                    uint32_t corners, uint32_t x_out, uint32_t y_out, uint32_t window_out, uint32_t object_out); /* $fdc57a */
void aes_act_bsclick(uint8_t *image, int16_t window, uint32_t tree, int16_t root, int16_t mx, int16_t my, int16_t keys,
                     uint32_t clip, int16_t double_click);                                            /* $fdcc2a */
int16_t aes_act_bdown(uint8_t *image, int16_t window, uint32_t tree, int16_t root, int16_t mx, int16_t my, int16_t keys,
                      uint32_t clip, uint32_t object_out);                                            /* $fdcd34 */
#endif

#endif /* TOS102US_DESK_DESKACT_H */
