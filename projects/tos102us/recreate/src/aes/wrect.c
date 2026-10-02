/* wrect.c — a WINDOW's rectangles (`aes/wrect.h`): where each GRECT lives (w_getxptr), one read out (w_getsize), and
 * newrect, which hands a window's visible-rectangle list back to the ORECT pool and rebuilds it as one rectangle —
 * the window's own, border and all — after cutting every window below it in the tree by that rectangle.
 *
 * newrect is the rectangle lists' entry (`src/aes/rlist.c`): it sets gl_mkrect and walks the window tree with everyobj,
 * handing it mkrect BY ITS ROM ADDRESS, as the ROM's `move.l #$fe5c9a,-(sp)` does — a ROM code address used as a value
 * (`test/test_aes_rom_data.py`, CODE: a rebuilt ROM owes everyobj its own mkrect's linked address).
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/objects.h"
#include "aes/oblib.h"
#include "aes/rect.h"
#include "aes/rlist.h"
#include "aes/wrect.h"

#define START_POSITION        0          /* everyobj's starting x and y: the window tree's own origin ($fe5d66 clr.l) */

/* $feb4be — the address of rectangle `which` of window `window` (`aes/wrect.h`'s WS_*), both indices signed words
 * (`muls.w`). An index past WS_TRUE — compared UNSIGNED (`cmp.w #4; bhi`), so a negative one too — matches no arm and
 * the ROM leaves by the return with D0 as the switch left it: `which` in the LOW word, its caller's D0 in the high
 * word, which no C caller can name. No caller hands one (each passes a constant, or wind_get's 0..3); the C answers
 * the low word with a clear high word. */
uint32_t aes_w_getxptr(int16_t which, int16_t window)
{
    switch ((uint16_t)which) {
    case WS_FULL:
        return window_record(window) + WIN_FULL;
    case WS_CURR:
    case WS_TRUE:
        return object_address(AES_WINDOW_TREE, window, OB_X);
    case WS_PREV:
        return window_record(window) + WIN_PREV;
    case WS_WORK:
        return window_record(window) + WIN_WORK;
    default:
        return (uint16_t)which;
    }
}

/* $feb53e — rectangle `which` of `window` copied into the GRECT at `rect` (rc_copy, two longwords); WS_TRUE's then
 * grown by the border, w and h each — only when both, READ BACK from `rect` after the copy, are non-zero: each a
 * word `addq` that wraps. */
void aes_w_getsize(uint8_t *image, int16_t which, int16_t window, uint32_t rect)
{
    aes_rc_copy(image, aes_w_getxptr(which, window), rect);
    if (which == WS_TRUE && bus_word(image, rect + GRECT_W) && bus_word(image, rect + GRECT_H)) {
        set_bus_word(image, rect + GRECT_W, (uint16_t)(bus_word(image, rect + GRECT_W) + W_BORDER));
        set_bus_word(image, rect + GRECT_H, (uint16_t)(bus_word(image, rect + GRECT_H) + W_BORDER));
    }
}

/* The list that starts at `orect`, onto the free list whole: its last ORECT's link takes the free head and the head
 * becomes `orect`. The walk follows the links as stored (no bound — a cyclic list hangs the ROM too). */
static void free_orect_list(uint8_t *image, uint32_t orect)
{
    uint32_t last = orect, next;

    while ((next = bus_long(image, last + ORECT_LINK)) != 0)
        last = next;
    set_bus_long(image, last + ORECT_LINK, be32(image + AES_ORECT_FREE));
    wr32(image + AES_ORECT_FREE, orect);
}

/* $fe5cee — everyobj's callback for window `window` of the window tree `tree` (the object index IS the handle): its
 * list freed and its record's list emptied and WIN_BROKEN cleared; gl_mkrect := its WS_TRUE rectangle; and when that
 * has an area (w and h both non-zero, as w_getsize left them), gl_mkrect's link cleared, every window the tree walk
 * reaches BEFORE `window` cut by it (everyobj from the root, stopping on `window`, mkrect per window), and the
 * window's list rebuilt as ONE fresh ORECT holding the same rectangle — read again by w_getsize, so a cut that moved
 * the window's own object would show. The list head is read once, into the frame, as the ROM keeps it. */
void aes_newrect(uint8_t *image, uint32_t tree, int16_t window)
{
    uint32_t record = window_record(window);
    uint32_t list = bus_long(image, record + WIN_RLIST);
    uint32_t orect;

    if (list)
        free_orect_list(image, list);
    set_bus_long(image, record + WIN_RLIST, 0);
    set_bus_word(image, record + WIN_FLAGS, (uint16_t)(bus_word(image, record + WIN_FLAGS) & ~WIN_BROKEN));
    aes_w_getsize(image, WS_TRUE, window, AES_GL_MKRECT + ORECT_X);
    if (!be16(image + AES_GL_MKRECT + ORECT_W) || !be16(image + AES_GL_MKRECT + ORECT_H))
        return;
    wr32(image + AES_GL_MKRECT + ORECT_LINK, 0);
    aes_everyobj(image, tree, OB_ROOT, window, AES_ROM_MKRECT, START_POSITION, START_POSITION, NEWRECT_WALK_DEPTH);
    orect = aes_get_orect(image);
    set_bus_long(image, orect + ORECT_LINK, 0);
    aes_w_getsize(image, WS_TRUE, window, orect + ORECT_X);
    set_bus_long(image, record + WIN_RLIST, orect);
}
