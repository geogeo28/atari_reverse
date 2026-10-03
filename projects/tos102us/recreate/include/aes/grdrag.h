/* aes/grdrag.h — the box loops that FOLLOW THE MOUSE until the button rises (`src/aes/grdrag.c`): gr_wait, the one
 * step every loop takes — the box XORed, gr_stilldn's wait for the mouse to move or the button to rise, the box XORed
 * away — and the loops over it: gr_rubwind / gr_rubbox (a box's corner stretched), gr_dragbox (a box moved inside
 * another) and gr_slidebox (an object dragged along its parent, answered in thousandths), with gr_clamp, the size the
 * mouse makes. Hand 68000 in the ROM, ported over its own order; the wait reaches the event layer through gr_stilldn
 * (`aes/grwait.h`) and the event door.
 *
 * The ROM's gr_rubbox and gr_dragbox hand gr_wait its `poff` by reading gr_wait's own `move.l #$9b30` immediate at
 * $fe8586 AS DATA (`test_aes_rom_data.py`, CODE_BYTES): here it is gl_rzero BY VALUE, the one address that immediate
 * holds.
 */
#ifndef TOS102US_AES_GRDRAG_H
#define TOS102US_AES_GRDRAG_H

#include <stdint.h>

/* gr_wait's wait: for the mouse to LEAVE a one-pixel rectangle at the corner it is handed, or the button to rise
 * ($fe8594 moveq #1,d0: the flag and both sizes). */
#define GR_WAIT_LEAVE         1
#define GR_WAIT_SIZE          1
/* gr_rubwind's and gr_dragbox's gr_setup colour: the word they pushed for wm_update(1) — still on the stack, which
 * gr_setup reads as its argument ($fe85b8 move.w 8(sp),(sp)). */
#define GR_DRAG_COLOUR        1
/* gr_dragbox's gr_clamp: the box's corner moved on by one each way ($fe8664 moveq #1, add.w / swap / add.l) and no
 * minimum ($fe8662 clr.l), so the mouse's offset into the box, at least 0. */
#define GR_DRAG_CORNER_STEP   1
#define GR_DRAG_NO_MINIMUM    0
/* gr_slidebox's answer: the elevator's place along its track in thousandths ($fe8754 move.w #1000). */
#define GR_SLIDE_SCALE        1000

/* gr_clamp's frame local: the mouse's x, y, which gsx_mxmy fills ($fe86dc subq.l #4,sp). */
#define GR_MOUSE_WORDS        2
/* gr_dragbox's frame locals whose address it hands on, in the frame's own order from the mouse up (`host_slot.h`). */
#define GR_DRAGBOX_MOUSE      0          /* words[2]: x, y — gsx_mxmy's          ($fe8670 lea 20(sp),a0)        */
#define GR_DRAGBOX_BOX        4          /* words[4]: the GRECT dragged          ($fe8652 lea 6(sp),a0)         */
#define GR_DRAGBOX_OFFSET     12         /* words[2]: the mouse's x, y in the box ($fe865a addq.l #2,a0)        */
#define GR_DRAGBOX_FRAME_BYTES 16
/* gr_slidebox's: the object's GRECT relative to its parent (saved D0/D1), then the parent's on the screen (D2/D3). */
#define GR_SLIDEBOX_OBJECT    0          /* words[4]                             ($fe8708 movea.l sp,a5)        */
#define GR_SLIDEBOX_TRACK     8          /* words[4]                             ($fe870a lea 8(sp),a6)         */
#define GR_SLIDEBOX_RECTS_BYTES 16

uint16_t aes_gr_wait(uint8_t *image, uint32_t box, uint32_t offset, int16_t mouse_x, int16_t mouse_y);  /* $fe8576 */
void aes_gr_clamp(uint8_t *image, int16_t x, int16_t y, int16_t min_width, int16_t min_height, uint32_t width_out,
                  uint32_t height_out);                                                                 /* $fe86dc */
void aes_gr_rubwind(uint8_t *image, int16_t x, int16_t y, int16_t min_width, int16_t min_height, uint32_t offset,
                    uint32_t width_out, uint32_t height_out);                                           /* $fe85de */
void aes_gr_rubbox(uint8_t *image, int16_t x, int16_t y, int16_t min_width, int16_t min_height, uint32_t width_out,
                   uint32_t height_out);                                                                /* $fe85c6 */
void aes_gr_dragbox(uint8_t *image, int16_t width, int16_t height, int16_t x, int16_t y, uint32_t bound,
                    uint32_t x_out, uint32_t y_out);                                                    /* $fe8640 */
int16_t aes_gr_slidebox(uint8_t *image, uint32_t tree, int16_t parent, int16_t object, int16_t vertical);
                                                                                                        /* $fe86fa */

#endif /* TOS102US_AES_GRDRAG_H */
