/* desk/deskbind.h — THE DESK'S AES BINDINGS (`src/desk/deskbind.c`): the forty routines `$fddde6..$fde4ff` the desk
 * calls the AES through, and the one leaf of its own they call (`$fe1bdc`, desk_wait).
 *
 * WHAT A BINDING IS. The desk is linked INTO the AES: where an application traps (`trap #2`, the marshal, the opcode
 * switch) the desk calls the implementation itself — and then does by hand what the trap's way out would have done:
 * `dsptch()`, a yield. So a binding is `ret = the AES routine(its arguments); dsptch(); return ret;`, its arguments
 * re-pushed in the implementation's order, a GRECT the caller passed BY VALUE handed on BY THE ADDRESS OF THE CALLER'S
 * OWN WORDS, an answer the implementation writes through one pointer copied out through the caller's several.
 *
 * WHAT A ROM CALLER READS IN D0, AND WHERE THE C HAS NONE (ruling W3-R5's kind: NOT DECIDED HERE). Each binding below
 * stores the word the implementation left in D0 and answers it after the yield. SEVEN of the implementations are
 * `void` in C (ob_center, gr_mkstate, mn_bar, ob_order, ob_add, ob_draw, ob_change): their bindings are `void` here —
 * the most direct C — and the word the ROM's binding answers is a NAMED, COUNTED DIVERGENCE the battery holds
 * (`test/test_desk_bind.py`), never silently equal. FOUR MORE answer no word of their own at all (graf_mouse,
 * graf_rubbox, graf_growbox, graf_shrinkbox: the ROM's leave whatever dsptch left). wm_delete's and wm_calc's
 * leftovers are their cores' own answers already (`aes/wmlib.h`).
 *
 * THE EVENT DOOR. The bindings are OUTSIDE the event layer: ev_multi, ev_button and ap_rdwr are called through
 * `aes/evdoor.h`'s wrappers, as the opcode switch's arms call them.
 *
 * NAMES: GEM's own binding names (the published desktop's DESKBIND), each read from its body.
 */
#ifndef TOS102US_DESK_DESKBIND_H
#define TOS102US_DESK_DESKBIND_H

#include "aes/evdoor.h"
#include "aes/gemgraf.h"

/* gl_apid: the desk's own process id, kept by its appl_init. */
#define AES_GL_APID           0xc790     /* word                                ($fdde48 move.w 28(a0),$c790)   */
/* What the desk's appl_init stores at the head of its global[] — ONE LONGWORD, the two words THE OTHER WAY ROUND from
 * the AES's own appl_init (`aes/gemsuper.h`: $01200001): global[0], the version's place, holds 1 and global[1], the
 * count's, holds $0120. A ROM behaviour, reproduced. */
#define DESK_GLOBAL_HEAD      0x00010120 /* ($fdddf6 move.l #$00010120,(a0))                                    */
/* appl_init's, appl_bvset's and appl_exit's answer: done. */
#define DESK_BIND_DONE        1          /* ($fdde50, $fdde68, $fddea2 moveq #1,d0)                             */

/* The cursor forms desk_wait asks graf_mouse for. */
#define DESK_CURSOR_ARROW     0          /* ($fe1bee clr.w -(sp))                                               */
#define DESK_CURSOR_HOURGLASS 2          /* ($fe1be8 move.w #2,-(sp))                                           */
#define DESK_NO_FORM          0          /* ...and the form's address it hands with either ($fe1be0 clr.l (sp)) */

/* THE BINDINGS' FRAME: the words a binding hands an implementation BY ADDRESS — its caller's own argument words in
 * the ROM (a GRECT, a MOBLK), or a local of its `link` (the answer words). One layout for all of them: a binding
 * calls no other binding while it holds any (desk_wait's graf_mouse is over before form_do's implementation runs).
 * evnt_multi's is the widest: the six answer words, then its two mouse rectangles. */
#define BIND_ANSWERS          0          /* words: ev_multi's six, ev_button's and wm_get's four, ob_center's GRECT */
/* ...of ev_multi's six, the two behind the four every answering binding copies out (the mouse, the buttons, the
 * shift keys): the key and the clicks, by their index ($fddf5e -12(a6), $fddf66 -10(a6): the fifth and the sixth). */
#define BIND_MULTI_ANSWER_KEY 4
#define BIND_MULTI_ANSWER_CLICKS 5
#define BIND_FIRST_RECT       0          /* bytes[GRECT_BYTES]: a binding's first rectangle argument             */
#define BIND_SECOND_RECT      GRECT_BYTES /* bytes[GRECT_BYTES]: ...and its second (form_dial, the two boxes)    */
#define BIND_FORM             0          /* long: the bit image rs_gaddr answers graf_mouse ($fde0be -4(a6))     */
#define BIND_MULTI_MOUSE1     12         /* words[EV_MOBLK_WORDS]: evnt_multi's first rectangle ($fddf32 16(a6))  */
#define BIND_MULTI_MOUSE2     22         /* words[EV_MOBLK_WORDS]: ...and its second ($fddf2a 26(a6))            */
#define BIND_FRAME_BYTES      32         /* evnt_multi's: 12 + 10 + 10                                           */
#define BIND_RECT_PAIR_BYTES  (2 * GRECT_BYTES)
#define BIND_FORM_BYTES       4

#ifndef __ASSEMBLER__
#include <stdint.h>

int16_t aes_desk_appl_init(uint8_t *image);                                                           /* $fddde6 */
int16_t aes_desk_appl_bvset(uint8_t *image, int16_t disks, int16_t hard_disks);                       /* $fdde54 */
int16_t aes_desk_appl_exit(uint8_t *image);                                                           /* $fdde6c */
uint16_t aes_desk_appl_write(uint8_t *image, int16_t process, int16_t length, uint32_t message);      /* $fddea6 */
uint16_t aes_desk_evnt_multi(uint8_t *image, int16_t flags, int16_t clicks, int16_t mask, int16_t state,
                             int16_t leave1, int16_t x1, int16_t y1, int16_t w1, int16_t h1,
                             int16_t leave2, int16_t x2, int16_t y2, int16_t w2, int16_t h2,
                             uint32_t message, int16_t timer_low, int16_t timer_high,
                             uint32_t mouse_x_out, uint32_t mouse_y_out, uint32_t buttons_out, uint32_t keys_out,
                             uint32_t key_out, uint32_t clicks_out);                                  /* $fdded8 */
uint16_t aes_desk_evnt_button(uint8_t *image, int16_t clicks, int16_t mask, int16_t state, uint32_t mouse_x_out,
                              uint32_t mouse_y_out, uint32_t buttons_out, uint32_t keys_out);         /* $fddf82 */
int16_t aes_desk_evnt_dclick(uint8_t *image, int16_t rate, int16_t set);                              /* $fddfc2 */
int16_t aes_desk_form_do(uint8_t *image, uint32_t tree, int16_t start);                               /* $fddfda */
uint16_t aes_desk_form_dial(uint8_t *image, int16_t type, int16_t little_x, int16_t little_y, int16_t little_w,
                            int16_t little_h, int16_t big_x, int16_t big_y, int16_t big_w, int16_t big_h); /* $fddffa */
int16_t aes_desk_form_alert(uint8_t *image, int16_t default_button, uint32_t string);                 /* $fde022 */
int16_t aes_desk_form_error(uint8_t *image, int16_t code);                                            /* $fde03e */
void aes_desk_form_center(uint8_t *image, uint32_t tree, uint32_t x_out, uint32_t y_out, uint32_t w_out,
                          uint32_t h_out);                                                            /* $fde054 */
void aes_desk_graf_mouse(uint8_t *image, int16_t number, uint32_t form);                              /* $fde094 */
void aes_desk_graf_rubbox(uint8_t *image, int16_t x, int16_t y, int16_t min_width, int16_t min_height,
                          uint32_t width_out, uint32_t height_out);                                   /* $fde122 */
void aes_desk_graf_mkstate(uint8_t *image, uint32_t mouse_x_out, uint32_t mouse_y_out, uint32_t buttons_out,
                           uint32_t keys_out);                                                        /* $fde142 */
void aes_desk_graf_growbox(uint8_t *image, int16_t from_x, int16_t from_y, int16_t from_w, int16_t from_h,
                           int16_t to_x, int16_t to_y, int16_t to_w, int16_t to_h);                   /* $fde16a */
void aes_desk_graf_shrinkbox(uint8_t *image, int16_t from_x, int16_t from_y, int16_t from_w, int16_t from_h,
                             int16_t to_x, int16_t to_y, int16_t to_w, int16_t to_h);                 /* $fde182 */
int16_t aes_desk_menu_tnormal(uint8_t *image, uint32_t tree, int16_t title, int16_t normal);          /* $fde19a */
void aes_desk_menu_bar(uint8_t *image, uint32_t tree, int16_t show);                                  /* $fde1d4 */
int16_t aes_desk_menu_icheck(uint8_t *image, uint32_t tree, int16_t item, int16_t check);             /* $fde1f0 */
int16_t aes_desk_menu_ienable(uint8_t *image, uint32_t tree, int16_t item, int16_t enable);           /* $fde21a */
int16_t aes_desk_objc_offset(uint8_t *image, uint32_t tree, int16_t object, uint32_t x_out, uint32_t y_out); /* $fde264 */
void aes_desk_objc_order(uint8_t *image, uint32_t tree, int16_t object, int16_t position);            /* $fde28c */
int16_t aes_desk_objc_find(uint8_t *image, uint32_t tree, int16_t object, int16_t depth, int16_t x, int16_t y); /* $fde2a8 */
void aes_desk_objc_add(uint8_t *image, uint32_t tree, int16_t parent, int16_t child);                 /* $fde2cc */
void aes_desk_objc_draw(uint8_t *image, uint32_t tree, int16_t object, int16_t depth, int16_t clip_x, int16_t clip_y,
                        int16_t clip_w, int16_t clip_h);                                              /* $fde2e8 */
void aes_desk_objc_change(uint8_t *image, uint32_t tree, int16_t object, int16_t reserved, int16_t clip_x,
                          int16_t clip_y, int16_t clip_w, int16_t clip_h, int16_t new_state, int16_t redraw); /* $fde30e */
int16_t aes_desk_rsrc_gaddr(uint8_t *image, int16_t type, int16_t index, uint32_t answer);            /* $fde354 */
int16_t aes_desk_shel_write(uint8_t *image, int16_t doexec, int16_t isgem, int16_t isover, uint32_t command,
                            uint32_t tail);                                                           /* $fde376 */
int16_t aes_desk_shel_get(uint8_t *image, uint32_t buffer, int16_t bytes);                            /* $fde39e */
int16_t aes_desk_shel_put(uint8_t *image, uint32_t data, int16_t bytes);                              /* $fde3ba */
uint16_t aes_desk_wind_close(uint8_t *image, int16_t window);                                         /* $fde3d6 */
uint16_t aes_desk_wind_delete(uint8_t *image, int16_t window);                                        /* $fde3ec */
int16_t aes_desk_wind_find(uint8_t *image, int16_t x, int16_t y);                                     /* $fde402 */
uint16_t aes_desk_wind_update(uint8_t *image, int16_t code);                                          /* $fde41a */
int16_t aes_desk_wind_create(uint8_t *image, int16_t kind, int16_t x, int16_t y, int16_t w, int16_t h); /* $fde430 */
uint16_t aes_desk_wind_open(uint8_t *image, int16_t window, int16_t x, int16_t y, int16_t w, int16_t h); /* $fde450 */
uint16_t aes_desk_wind_get(uint8_t *image, int16_t window, int16_t field, uint32_t first_out, uint32_t second_out,
                           uint32_t third_out, uint32_t fourth_out);                                  /* $fde470 */
uint16_t aes_desk_wind_set(uint8_t *image, int16_t window, int16_t field, int16_t first, int16_t second,
                           int16_t third, int16_t fourth);                                            /* $fde4ac */
int16_t aes_desk_wind_calc(uint8_t *image, int16_t type, int16_t kind, int16_t x, int16_t y, int16_t w, int16_t h,
                           uint32_t x_out, uint32_t y_out, uint32_t w_out, uint32_t h_out);           /* $fde4cc */
/* ...and the desk's own leaf the form_do binding calls first (unit K's by address; here because the binding cannot
 * be C without it): the cursor made the hourglass, or the arrow again. */
void aes_desk_wait(uint8_t *image, int16_t busy);                                                     /* $fe1bdc */
#endif

#endif /* TOS102US_DESK_DESKBIND_H */
