/*
 * c2p.c - the reference chunky-to-planar + pixel double.  See c2p.h.
 *
 * Written for obvious correctness, not for speed: it is the oracle, so every
 * bit it sets has to be traceable to the format definition.
 */
#include "c2p.h"
#include "render.h"

#define PIXELS_PER_GROUP    16                      /* one 4-word planar group */
#define GROUP_BYTES         (SCREEN_PLANES * 2)
#define GROUPS_PER_LINE     (SCREEN_W / PIXELS_PER_GROUP)

static void build_planar_line(const uint8_t *chunky, uint16_t columns,
                              uint16_t row, uint8_t *line)
{
    uint16_t doubling = SCREEN_W / columns;
    uint16_t group;

    for (group = 0; group < GROUPS_PER_LINE; ++group) {
        uint16_t plane_bits[SCREEN_PLANES] = { 0, 0, 0, 0 };
        uint16_t n;
        uint16_t plane;

        for (n = 0; n < PIXELS_PER_GROUP; ++n) {
            uint16_t screen_x = (uint16_t)(group * PIXELS_PER_GROUP + n);
            uint8_t colour = chunky[RENDER_PIXEL_OFFSET(screen_x / doubling, row)];
            uint16_t mask = (uint16_t)(1u << (PIXELS_PER_GROUP - 1 - n));

            for (plane = 0; plane < SCREEN_PLANES; ++plane) {
                if ((colour >> plane) & 1) {
                    plane_bits[plane] |= mask;
                }
            }
        }
        for (plane = 0; plane < SCREEN_PLANES; ++plane) {
            uint8_t *word = line + group * GROUP_BYTES + plane * 2;

            word[0] = (uint8_t)(plane_bits[plane] >> 8);
            word[1] = (uint8_t)(plane_bits[plane] & 0xff);
        }
    }
}

void c2p_window(const uint8_t *chunky, uint16_t columns, uint8_t *planar)
{
    uint16_t row;

    for (row = 0; row < RENDER_H; ++row) {
        uint8_t *first = planar + (size_t)(row * 2) * SCREEN_BYTES_PER_LINE;
        uint16_t byte;

        build_planar_line(chunky, columns, row, first);
        /* Vertical doubling: the second line of the pair is identical, which is
         * why the 68000 version stores every word twice instead of running a
         * separate copy pass. */
        for (byte = 0; byte < SCREEN_BYTES_PER_LINE; ++byte) {
            first[SCREEN_BYTES_PER_LINE + byte] = first[byte];
        }
    }
}

uint8_t planar_pixel(const uint8_t *planar, uint16_t x, uint16_t y)
{
    const uint8_t *line = planar + (size_t)y * SCREEN_BYTES_PER_LINE;
    uint16_t group = (uint16_t)(x / PIXELS_PER_GROUP);
    uint16_t bit = (uint16_t)(PIXELS_PER_GROUP - 1 - (x % PIXELS_PER_GROUP));
    uint8_t colour = 0;
    uint16_t plane;

    for (plane = 0; plane < SCREEN_PLANES; ++plane) {
        const uint8_t *word = line + group * GROUP_BYTES + plane * 2;
        uint16_t value = (uint16_t)((word[0] << 8) | word[1]);

        if ((value >> bit) & 1) {
            colour |= (uint8_t)(1u << plane);
        }
    }
    return colour;
}
