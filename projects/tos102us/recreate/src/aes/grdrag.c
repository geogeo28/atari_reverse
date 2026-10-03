/* grdrag.c — the box loops that follow the mouse until the button rises (`aes/grdrag.h`): gr_wait (gr_draw and gr_xdraw
 * folded), gr_clamp (its fragment $fe86c2 folded), gr_rubwind, gr_rubbox, gr_dragbox and gr_slidebox — hand 68000 in
 * the ROM, ported over its own order. The wait is gr_stilldn's (`aes/grwait.h`), through the event door; the screen
 * lock round each loop is wm_update's (`aes/wmupdate.h`).
 *
 * THE ROM'S LOCALS ARE ITS SAVED REGISTERS: each routine hands on the address of words its own `movem` saved
 * registers in — gr_draw's summed box, gr_rubwind's box, gr_dragbox's mouse, box and offset, gr_slidebox's two
 * rectangles — and gr_clamp of the four bytes it reserved. Each is a C local here, a host slot off target
 * (`host_slot.h`), read back where the ROM reads it. Every word sum is a word that wraps, every compare signed.
 *
 * gl_rzero BY VALUE: gr_rubbox and gr_dragbox read gr_wait's `move.l #$9b30` immediate ($fe8586) as data; the C hands
 * the value (`aes/grdrag.h`).
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/gemgraf.h"
#include "aes/grdrag.h"
#include "aes/grwait.h"
#include "aes/gsx.h"
#include "aes/gsxif.h"
#include "aes/objects.h"
#include "aes/objops.h"
#include "aes/rect.h"
#include "aes/strings.h"
#include "aes/wmupdate.h"

/* rc_equal's answer flipped in its low bit ($fe858c bchg #0,d0): a second box unless `offset` is gl_rzero's. */
#define SECOND_BOX_FLIP       1

/* $fe8532 + $fe8564, folded — gr_xdraw: the cursor hidden, `box` XORed by gsx_xbox, and with `two_boxes` a second box
 * at `box` + `offset`, word by word (the offset's word first, `move.w (a5)+,d0; add.w (a4)+,d0`) into the words gr_draw's
 * `movem` saved D0/D1 in; the cursor shown. */
static void gr_xdraw(uint8_t *image, uint16_t two_boxes, uint32_t box, uint32_t offset)
{
    aes_gsx_moff(image);
    aes_gsx_xbox(image, box);
    if (two_boxes) {
        uint16_t sum_local[GRECT_WORDS];
        _Static_assert(sizeof sum_local == HOST_SLOT_AES_GR_DRAW_RECT_BYTES, "gr_draw's summed box, its slot");
        uint32_t sum = host_slot_claim(AES_GR_DRAW_RECT, sum_local);
        int32_t word;

        for (word = 0; word < GRECT_WORDS; word++) {
            uint16_t moved_by = bus_word(image, word_entry(offset, word));

            wr16(image + word_entry(sum, word), (uint16_t)(moved_by + bus_word(image, word_entry(box, word))));
        }
        aes_gsx_xbox(image, sum);
        host_slot_release(AES_GR_DRAW_RECT);
    }
    aes_gsx_mon(image);
}

/* $fe8576 — one step of a drag: `box` drawn (and its offset twin, unless `offset` holds gl_rzero's words), gr_stilldn's
 * wait for the mouse to leave the pixel at (`mouse_x`, `mouse_y`) or the button to rise, the box drawn away.
 * gr_stilldn's answer: 1 the button still down. */
uint16_t aes_gr_wait(uint8_t *image, uint32_t box, uint32_t offset, int16_t mouse_x, int16_t mouse_y)
{
    uint16_t two_boxes = (uint16_t)aes_rc_equal(image, AES_GL_RZERO, offset) ^ SECOND_BOX_FLIP;
    uint16_t still_down;

    gr_xdraw(image, two_boxes, box, offset);
    still_down = aes_gr_stilldn(image, GR_WAIT_LEAVE, mouse_x, mouse_y, GR_WAIT_SIZE, GR_WAIT_SIZE);
    gr_xdraw(image, two_boxes, box, offset);
    return still_down;
}

/* $fe86c2, folded: one axis's size — the mouse's distance from `origin`, plus one, at least `minimum` (`cmp.w`,
 * signed) — stored through `size_out`. */
static void clamp_axis(uint8_t *image, int16_t mouse, int16_t origin, int16_t minimum, uint32_t size_out)
{
    int16_t size = (int16_t)(mouse - origin + 1);

    set_bus_word(image, size_out, (uint16_t)(size < minimum ? minimum : size));
}

/* $fe86dc — the size the mouse makes a box at (`x`, `y`): gsx_mxmy into the four bytes it reserved, then each axis
 * clamped to its minimum, the width first. */
void aes_gr_clamp(uint8_t *image, int16_t x, int16_t y, int16_t min_width, int16_t min_height, uint32_t width_out,
                  uint32_t height_out)
{
    uint16_t mouse_local[GR_MOUSE_WORDS];
    _Static_assert(sizeof mouse_local == HOST_SLOT_AES_GR_CLAMP_MOUSE_BYTES, "gr_clamp's mouse, its slot");
    uint32_t mouse = host_slot_claim(AES_GR_CLAMP_MOUSE, mouse_local);

    aes_gsx_mxmy(image, word_entry(mouse, 0), word_entry(mouse, 1));
    clamp_axis(image, (int16_t)be16(image + word_entry(mouse, 0)), x, min_width, width_out);
    clamp_axis(image, (int16_t)be16(image + word_entry(mouse, 1)), y, min_height, height_out);
    host_slot_release(AES_GR_CLAMP_MOUSE);
}

/* $fe85de — a box stretched from (`x`, `y`) by its corner, at least `min_width` x `min_height`, until the button rises:
 * the screen locked round it and XOR drawing set up; each step gr_clamp's size, then gr_wait at the corner (its height's
 * sum taken first) with `offset`'s twin; the size out through `width_out` / `height_out`. */
void aes_gr_rubwind(uint8_t *image, int16_t x, int16_t y, int16_t min_width, int16_t min_height, uint32_t offset,
                    uint32_t width_out, uint32_t height_out)
{
    uint16_t box_local[GRECT_WORDS];
    _Static_assert(sizeof box_local == HOST_SLOT_AES_GR_RUBWIND_RECT_BYTES, "gr_rubwind's box, its slot");
    uint32_t box = host_slot_claim(AES_GR_RUBWIND_RECT, box_local);
    int16_t corner_x, corner_y;

    aes_wm_update(image, WM_BEG_UPDATE);
    aes_gr_setup(image, GR_DRAG_COLOUR);
    wr16(image + box + GRECT_X, (uint16_t)x);
    wr16(image + box + GRECT_Y, (uint16_t)y);
    wr16(image + box + GRECT_W, 0);
    wr16(image + box + GRECT_H, 0);
    do {
        aes_gr_clamp(image, (int16_t)be16(image + box + GRECT_X), (int16_t)be16(image + box + GRECT_Y), min_width,
                     min_height, box + GRECT_W, box + GRECT_H);
        corner_y = (int16_t)(be16(image + box + GRECT_Y) + be16(image + box + GRECT_H) - 1);
        corner_x = (int16_t)(be16(image + box + GRECT_X) + be16(image + box + GRECT_W) - 1);
    } while (aes_gr_wait(image, box, offset, corner_x, corner_y));
    set_bus_word(image, width_out, be16(image + box + GRECT_W));
    set_bus_word(image, height_out, be16(image + box + GRECT_H));
    aes_wm_update(image, WM_END_UPDATE);
    host_slot_release(AES_GR_RUBWIND_RECT);
}

/* $fe85c6 — gr_rubwind with no twin box: gl_rzero's address (`aes/grdrag.h`). */
void aes_gr_rubbox(uint8_t *image, int16_t x, int16_t y, int16_t min_width, int16_t min_height, uint32_t width_out,
                   uint32_t height_out)
{
    aes_gr_rubwind(image, x, y, min_width, min_height, AES_GL_RZERO, width_out, height_out);
}

/* $fe8640 — a `width` x `height` box at (`x`, `y`) dragged by the mouse inside `bound` until the button rises: the
 * screen locked round it and XOR drawing set up; the mouse's offset into the box taken once (gr_clamp from the corner
 * one further on, no minimum); each step the box put where the mouse less that offset is, kept inside `bound`
 * (rc_constrain), and gr_wait at the mouse; the box's corner out through `x_out` / `y_out`. */
void aes_gr_dragbox(uint8_t *image, int16_t width, int16_t height, int16_t x, int16_t y, uint32_t bound,
                    uint32_t x_out, uint32_t y_out)
{
    uint16_t frame_local[GR_DRAGBOX_FRAME_BYTES / sizeof(uint16_t)];
    _Static_assert(sizeof frame_local == HOST_SLOT_AES_GR_DRAGBOX_FRAME_BYTES, "gr_dragbox's frame, its slot");
    uint32_t frame = host_slot_claim(AES_GR_DRAGBOX_FRAME, frame_local);
    uint32_t mouse = frame + GR_DRAGBOX_MOUSE, box = frame + GR_DRAGBOX_BOX, offset = frame + GR_DRAGBOX_OFFSET;
    int16_t left, top;

    aes_wm_update(image, WM_BEG_UPDATE);
    aes_gr_setup(image, GR_DRAG_COLOUR);
    wr16(image + box + GRECT_X, (uint16_t)x);
    wr16(image + box + GRECT_Y, (uint16_t)y);
    wr16(image + box + GRECT_W, (uint16_t)width);
    wr16(image + box + GRECT_H, (uint16_t)height);
    aes_gr_clamp(image, (int16_t)(x + GR_DRAG_CORNER_STEP), (int16_t)(y + GR_DRAG_CORNER_STEP), GR_DRAG_NO_MINIMUM,
                 GR_DRAG_NO_MINIMUM, word_entry(offset, 0), word_entry(offset, 1));
    do {
        aes_gsx_mxmy(image, word_entry(mouse, 0), word_entry(mouse, 1));
        left = (int16_t)(be16(image + word_entry(mouse, 0)) - be16(image + word_entry(offset, 0)));
        top = (int16_t)(be16(image + word_entry(mouse, 1)) - be16(image + word_entry(offset, 1)));
        wr16(image + box + GRECT_X, (uint16_t)left);
        wr16(image + box + GRECT_Y, (uint16_t)top);
        aes_rc_constrain(image, bound, box);
    } while (aes_gr_wait(image, box, AES_GL_RZERO, (int16_t)be16(image + word_entry(mouse, 0)),
                         (int16_t)be16(image + word_entry(mouse, 1))));
    set_bus_word(image, x_out, be16(image + box + GRECT_X));
    set_bus_word(image, y_out, be16(image + box + GRECT_Y));
    aes_wm_update(image, WM_END_UPDATE);
    host_slot_release(AES_GR_DRAGBOX_FRAME);
}

/* $fe86fa — `object` dragged inside its `parent` (gr_dragbox, from where it is on the screen — its relative corner plus
 * the parent's, word by word); its place along the parent — the y axis if `vertical`, else x — answered in thousandths
 * of the room it has (mul_div), or 0 when it has none. */
int16_t aes_gr_slidebox(uint8_t *image, uint32_t tree, int16_t parent, int16_t object, int16_t vertical)
{
    uint16_t rects_local[GR_SLIDEBOX_RECTS_BYTES / sizeof(uint16_t)];
    _Static_assert(sizeof rects_local == HOST_SLOT_AES_GR_SLIDEBOX_RECTS_BYTES, "gr_slidebox's rectangles, their slot");
    uint32_t rects = host_slot_claim(AES_GR_SLIDEBOX_RECTS, rects_local);
    uint32_t moved = rects + GR_SLIDEBOX_OBJECT, track = rects + GR_SLIDEBOX_TRACK;
    uint32_t axis = vertical ? GRECT_Y - GRECT_X : 0;
    int16_t place, room;

    aes_ob_actxywh(image, tree, parent, track);
    aes_ob_relxywh(image, tree, object, moved);
    aes_gr_dragbox(image, (int16_t)be16(image + moved + GRECT_W), (int16_t)be16(image + moved + GRECT_H),
                   (int16_t)(be16(image + moved + GRECT_X) + be16(image + track + GRECT_X)),
                   (int16_t)(be16(image + moved + GRECT_Y) + be16(image + track + GRECT_Y)), track,
                   moved + GRECT_X, moved + GRECT_Y);
    place = (int16_t)(be16(image + moved + GRECT_X + axis) - be16(image + track + GRECT_X + axis));
    room = (int16_t)(be16(image + track + GRECT_W + axis) - be16(image + moved + GRECT_W + axis));
    host_slot_release(AES_GR_SLIDEBOX_RECTS);
    return room ? aes_mul_div(place, GR_SLIDE_SCALE, room) : 0;
}
