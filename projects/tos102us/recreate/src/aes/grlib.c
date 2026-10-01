/* grlib.c — the AES's box animations that never wait on an event (`aes/gemgraf.h`): gr_setup, gr_scale, gr_stepcalc,
 * gr_xor, gr_movebox, gr_growbox and gr_shrinkbox — hand 68000 in the ROM, ported over its own order. The ones that
 * block in evnt_multi (gr_watchbox, gr_rubbox, gr_dragbox, gr_slidebox and their helpers) are not here.
 *
 * THE ROM'S LOCALS ARE ITS SAVED REGISTERS. gr_movebox hands gr_scale three pointers into the words its own `movem`
 * saved D1 and D2 in, and gr_growbox / gr_shrinkbox hand gr_stepcalc five into their saved D2-D4 (through the
 * fragment $fe831e, folded below): each set of words is a C local here, standing in through `host_slot.h` off
 * target, read back in the ROM's order. gr_xor STEPS its own frame's GRECT in place, and hands gsx_xbox its address.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/gemgraf.h"
#include "aes/gsx.h"
#include "aes/gsxif.h"
#include "aes/objects.h"
#include "vdi/vdi.h"

#define NO_CORNERS            0          /* gr_movebox's gr_xor: the whole box  ($fe8456 clr.w -(sp), and d4.hi) */
#define CORNERS               1          /* gr_growbox's: its corners           ($fe8352 moveq #1)             */
#define GROWS                 1          /* ...and grown by its step each time  */
#define MOVES                 0

/* gr_movebox's three words — gr_scale's count and the two steps — in the order its saved D1/D2 hold them. */
enum { MOVE_COUNT, MOVE_X_STEP, MOVE_Y_STEP, MOVE_WORDS };
/* gr_growbox's five — gr_stepcalc's centre, count and steps — in its saved D2-D4's order. */
enum { GROW_CENTRE_X, GROW_CENTRE_Y, GROW_COUNT, GROW_X_STEP, GROW_Y_STEP, GROW_WORDS };

/* One of those words, read back from where it was stored. */
static inline int16_t saved_word(const uint8_t *image, uint32_t words, int32_t index)
{
    return (int16_t)be16(image + word_entry(words, index));
}

/* `neg.w` when negative: a WORD, so -32768 stays itself. */
static inline int16_t word_magnitude(int16_t value)
{
    return value < 0 ? (int16_t)(uint16_t)-(uint16_t)value : value;
}

/* `dbf`: the counter a word, counted down, the loop left when it passes 0 to -1 — a count of N runs N + 1 times. */
#define DBF_EXPIRED           ((uint16_t)-1)

static inline int dbf_continues(uint16_t *counter)
{
    *counter = (uint16_t)(*counter - 1);
    return *counter != DBF_EXPIRED;
}

/* $fe85b0 — gr_setup: the clip the whole screen (gl_rscreen), and XOR in `colour` (gsx_attr, the line's).
 * gr_watchbox ($fe84ca, still the ROM's) reads this routine's `move.l #$98a4` immediate at $fe85b2 AS DATA: a ROM
 * rebuilt with this C at $fe85b0 must keep those bytes, or port watchbox with the value (the census's CODE_BYTES row). */
void aes_gr_setup(uint8_t *image, int16_t colour)
{
    aes_gsx_sclip(image, AES_GL_RSCREEN);
    aes_gsx_attr(image, GSX_TEXT_LINE, GSX_MODE_XOR, colour);
}

/* $fe8472 — gr_scale: gr_setup in black, then the STEPS a distance takes — the bits of x + y shifted out (`lsr.w`,
 * unsigned) less one — out through `count`, and each axis's step: its distance / the steps (`divs.w`), at least 1,
 * or 1 for no steps at all, through `x_step` and `y_step`. D0 is the x step. */
uint16_t aes_gr_scale(uint8_t *image, int16_t x_distance, int16_t y_distance, uint32_t count, uint32_t x_step,
                      uint32_t y_step)
{
    uint16_t sum = (uint16_t)(x_distance + y_distance);
    int16_t steps = -1, x_each = GROW_MINIMUM_STEP, y_each = GROW_MINIMUM_STEP, each;

    aes_gr_setup(image, GROW_COLOUR);
    do {
        steps++;
        sum >>= 1;
    } while (sum);
    set_bus_word(image, count, (uint16_t)steps);
    if (steps) {
        each = quotient_word(m68k_divs_w((uint32_t)(int32_t)x_distance, (uint16_t)steps));
        if (each > x_each)
            x_each = each;
        each = quotient_word(m68k_divs_w((uint32_t)(int32_t)y_distance, (uint16_t)steps));
        if (each > y_each)
            y_each = each;
    }
    set_bus_word(image, x_step, (uint16_t)x_each);
    set_bus_word(image, y_step, (uint16_t)y_each);
    return (uint16_t)x_each;
}

/* $fe82e6 — gr_stepcalc: where a box `width` x `height` sits centred in the GRECT — the halves' difference (`lsr.w`,
 * unsigned halves; the fragment $fe82d6, folded) out through `centre_x` / `centre_y` — gr_scale of those two words
 * READ BACK, then the GRECT's corner added to each in place. Every answer word is read from where it was stored:
 * pointers laid over each other chain. */
void aes_gr_stepcalc(uint8_t *image, int16_t width, int16_t height, uint32_t rect, uint32_t centre_x,
                     uint32_t centre_y, uint32_t count, uint32_t x_step, uint32_t y_step)
{
    int16_t centre_y_read;

    set_bus_word(image, centre_x, (uint16_t)((bus_word(image, rect + GRECT_W) >> 1) - ((uint16_t)width >> 1)));
    set_bus_word(image, centre_y, (uint16_t)((bus_word(image, rect + GRECT_H) >> 1) - ((uint16_t)height >> 1)));
    centre_y_read = (int16_t)bus_word(image, centre_y);
    aes_gr_scale(image, (int16_t)bus_word(image, centre_x), centre_y_read, count, x_step, y_step);
    set_bus_word(image, centre_x, (uint16_t)(bus_word(image, centre_x) + bus_word(image, rect + GRECT_X)));
    set_bus_word(image, centre_y, (uint16_t)(bus_word(image, centre_y) + bus_word(image, rect + GRECT_Y)));
}

/* $fe83be — gr_xor: the box at (x, y) — or its corners — drawn `count` + 1 times (`dbf`), each time stepped back by
 * (x_step, y_step) and, when it `grows`, widened by twice the step. The GRECT is the ROM's own FRAME, stepped in
 * place and handed to gsx_xbox / gsx_xcbox by address. */
void aes_gr_xor(uint8_t *image, int16_t corners, int16_t count, int16_t x, int16_t y, int16_t width, int16_t height,
                int16_t x_step, int16_t y_step, int16_t grows)
{
    uint16_t box_local[GRECT_WORDS];
    uint32_t box = host_slot_claim(AES_XOR_RECT, box_local);
    uint16_t left = (uint16_t)count;

    wr16(image + box + GRECT_X, (uint16_t)x);
    wr16(image + box + GRECT_Y, (uint16_t)y);
    wr16(image + box + GRECT_W, (uint16_t)width);
    wr16(image + box + GRECT_H, (uint16_t)height);
    do {
        if (corners)
            aes_gsx_xcbox(image, box);
        else
            aes_gsx_xbox(image, box);
        wr16(image + box + GRECT_X, (uint16_t)(be16(image + box + GRECT_X) - x_step));
        wr16(image + box + GRECT_Y, (uint16_t)(be16(image + box + GRECT_Y) - y_step));
        if (grows) {
            wr16(image + box + GRECT_W, (uint16_t)(be16(image + box + GRECT_W) + (uint16_t)(x_step + x_step)));
            wr16(image + box + GRECT_H, (uint16_t)(be16(image + box + GRECT_H) + (uint16_t)(y_step + y_step)));
        }
    } while (dbf_continues(&left));
    host_slot_release(AES_XOR_RECT);
}

/* $fe8402 — gr_movebox: a `width` x `height` box XORed from the source towards the destination — gr_scale of the
 * distances' magnitudes, each step's sign the direction's — and XORed along the same path again to take it away, the
 * cursor hidden round both. */
void aes_gr_movebox(uint8_t *image, int16_t width, int16_t height, int16_t source_x, int16_t source_y,
                    int16_t destination_x, int16_t destination_y)
{
    uint16_t steps_local[MOVE_WORDS];
    uint32_t steps = host_slot_claim(AES_MOVEBOX_STEPS, steps_local);
    int16_t down = (int16_t)(source_y - destination_y), across = (int16_t)(source_x - destination_x);
    int16_t count, x_step, y_step;
    unsigned pass;

    aes_gr_scale(image, word_magnitude(across), word_magnitude(down), word_entry(steps, MOVE_COUNT),
                 word_entry(steps, MOVE_X_STEP), word_entry(steps, MOVE_Y_STEP));
    count = saved_word(image, steps, MOVE_COUNT);
    x_step = saved_word(image, steps, MOVE_X_STEP);
    if (across < 0)
        x_step = (int16_t)-x_step;
    y_step = saved_word(image, steps, MOVE_Y_STEP);
    if (down < 0)
        y_step = (int16_t)-y_step;
    aes_gsx_moff(image);
    for (pass = 0; pass < GROW_STEPS_PASSES; pass++)
        aes_gr_xor(image, NO_CORNERS, count, source_x, source_y, width, height, x_step, y_step, MOVES);
    aes_gsx_mon(image);
    host_slot_release(AES_MOVEBOX_STEPS);
}

/* $fe831e, folded: gr_stepcalc of `from`'s size centred in `to`, its five answers into the words `steps` names. */
static void grow_steps(uint8_t *image, uint32_t from, uint32_t to, uint32_t steps)
{
    uint32_t size = bus_long(image, from + GRECT_W);

    aes_gr_stepcalc(image, (int16_t)(size >> M68K_WORD_BITS), (int16_t)size, to, word_entry(steps, GROW_CENTRE_X),
                    word_entry(steps, GROW_CENTRE_Y), word_entry(steps, GROW_COUNT), word_entry(steps, GROW_X_STEP),
                    word_entry(steps, GROW_Y_STEP));
}

/* $fe8340 — gr_growbox: `from` moved to the centre of `to` (gr_movebox), then its corners XORed there, grown step by
 * step out to `to`, and XORed back — `from`'s size and the five words read again for each pass. */
void aes_gr_growbox(uint8_t *image, uint32_t from, uint32_t to)
{
    uint16_t steps_local[GROW_WORDS];
    uint32_t steps = host_slot_claim(AES_GROWBOX_STEPS, steps_local);
    uint32_t size;
    unsigned pass;

    grow_steps(image, from, to, steps);
    aes_gr_movebox(image, (int16_t)bus_word(image, from + GRECT_W), (int16_t)bus_word(image, from + GRECT_H),
                   (int16_t)bus_word(image, from + GRECT_X), (int16_t)bus_word(image, from + GRECT_Y),
                   saved_word(image, steps, GROW_CENTRE_X), saved_word(image, steps, GROW_CENTRE_Y));
    aes_gsx_moff(image);
    for (pass = 0; pass < GROW_STEPS_PASSES; pass++) {
        size = bus_long(image, from + GRECT_W);
        aes_gr_xor(image, CORNERS, saved_word(image, steps, GROW_COUNT), saved_word(image, steps, GROW_CENTRE_X),
                   saved_word(image, steps, GROW_CENTRE_Y), (int16_t)(size >> M68K_WORD_BITS), (int16_t)size,
                   saved_word(image, steps, GROW_X_STEP), saved_word(image, steps, GROW_Y_STEP), GROWS);
    }
    aes_gsx_mon(image);
    host_slot_release(AES_GROWBOX_STEPS);
}

/* $fe837a — gr_shrinkbox: `to`'s corners XORed, shrunk step by step in to `from`'s size at its centre, and XORed
 * back; then the box moved from that centre to `from` (gr_movebox) — `to` and the five words read again for each
 * pass. */
void aes_gr_shrinkbox(uint8_t *image, uint32_t from, uint32_t to)
{
    uint16_t steps_local[GROW_WORDS];
    uint32_t steps = host_slot_claim(AES_GROWBOX_STEPS, steps_local);
    uint32_t size;
    int16_t y_step, x_step;
    unsigned pass;

    grow_steps(image, from, to, steps);
    aes_gsx_moff(image);
    for (pass = 0; pass < GROW_STEPS_PASSES; pass++) {
        y_step = (int16_t)-saved_word(image, steps, GROW_Y_STEP);
        x_step = (int16_t)-saved_word(image, steps, GROW_X_STEP);
        size = bus_long(image, to + GRECT_W);
        aes_gr_xor(image, CORNERS, saved_word(image, steps, GROW_COUNT),
                   (int16_t)bus_word(image, to + GRECT_X), (int16_t)bus_word(image, to + GRECT_Y),
                   (int16_t)(size >> M68K_WORD_BITS), (int16_t)size, x_step, y_step, GROWS);
    }
    aes_gsx_mon(image);
    aes_gr_movebox(image, (int16_t)bus_word(image, from + GRECT_W), (int16_t)bus_word(image, from + GRECT_H),
                   saved_word(image, steps, GROW_CENTRE_X), saved_word(image, steps, GROW_CENTRE_Y),
                   (int16_t)bus_word(image, from + GRECT_X), (int16_t)bus_word(image, from + GRECT_Y));
    host_slot_release(AES_GROWBOX_STEPS);
}
