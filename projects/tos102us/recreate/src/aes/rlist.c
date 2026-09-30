/* rlist.c — the RECTANGLE LISTS (`aes/rlist.h`): the ORECT pool's free list, and the cut that breaks a window's
 * visible rectangles round the rectangle newrect set (gemrlist, `$fe5a62..$fe5d9b`).
 *
 * A window's visible area is a linked list of ORECTs from one pool of 80; newrect cuts every other window's list by
 * the new window's rectangle (everyobj calling mkrect per window), and brkrct replaces each listed rectangle the cut
 * overlaps by the up-to-four pieces round it that stay visible, handing the rectangle back to the free list.
 *
 * NOTHING CHECKS THE POOL: get_orect answers 0 when the free list is empty, and mkpiece builds its piece THERE — at
 * address 0 — and links it on. The C does the same, so an exhausted pool is the ROM's machine on both sides.
 *
 * Every field is read at the moment the ROM reads it, after every store the ROM made before it: a piece taken off the
 * free list may be the very rectangle being cut when the list is corrupt, and the batteries lay them over each other.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/objects.h"
#include "aes/rlist.h"
#include "aes/strings.h"

/* A field of the ORECT at `orect`, reached as the ROM reaches it — `d16(An)` off the pointer it holds, the offset
 * summed and then put on the bus (`m68k_idioms.h`). The pointers are carried as the values stored, top byte and all;
 * only a dereference drops it. */
static inline uint32_t orect_link(uint8_t *image, uint32_t orect)
{
    return bus_long(image, orect + ORECT_LINK);
}

static inline void set_orect_link(uint8_t *image, uint32_t orect, uint32_t link)
{
    set_bus_long(image, orect + ORECT_LINK, link);
}

static inline int16_t orect_word(uint8_t *image, uint32_t orect, uint32_t field)
{
    return (int16_t)bus_word(image, orect + field);
}

static inline void set_orect_word(uint8_t *image, uint32_t orect, uint32_t field, int16_t value)
{
    set_bus_word(image, orect + field, (uint16_t)value);
}

/* The far edge on one axis: the origin plus the extent, a WORD sum that wraps (`add.w`). */
static inline int16_t orect_far(uint8_t *image, uint32_t orect, uint32_t origin_field, uint32_t extent_field)
{
    return (int16_t)(orect_word(image, orect, origin_field) + orect_word(image, orect, extent_field));
}

static inline uint32_t free_orects(const uint8_t *image)
{
    return be32(image + AES_ORECT_FREE);
}

static inline void set_free_orects(uint8_t *image, uint32_t orect)
{
    wr32(image + AES_ORECT_FREE, orect);
}

/* $fe5a62 — the pool onto an emptied free list, ORECT 0 first, so the last is the head. Every link is written, and
 * whatever lists the windows held are gone with them: the head is re-read from RAM on each pass, as the ROM does. */
void aes_or_start(uint8_t *image)
{
    int16_t index;

    set_free_orects(image, 0);
    for (index = 0; index < AES_ORECT_COUNT; index++) {
        uint32_t orect = table_entry(AES_ORECT_POOL, index, ORECT_BYTES);

        set_orect_link(image, orect, free_orects(image));
        set_free_orects(image, orect);
    }
}

/* $fe5aac — the free list's head, unlinked: its link becomes the head. An empty list answers 0 and stores nothing. */
uint32_t aes_get_orect(uint8_t *image)
{
    uint32_t orect = free_orects(image);

    if (orect)
        set_free_orects(image, orect_link(image, orect));
    return orect;
}

/* $fe5acc — the piece of `rect` on `side` of `cut`, from the free list and linked to `rect`: first the rows the two
 * share at `rect`'s width, then the side's own edges. Each edge is read after the stores before it, and the common
 * height is taken from the piece's y as stored. A side past the four leaves the common piece. */
uint32_t aes_mkpiece(uint8_t *image, int16_t side, uint32_t cut, uint32_t rect)
{
    uint32_t piece = aes_get_orect(image);

    set_orect_link(image, piece, rect);
    set_orect_word(image, piece, ORECT_X, orect_word(image, rect, ORECT_X));
    set_orect_word(image, piece, ORECT_W, orect_word(image, rect, ORECT_W));
    set_orect_word(image, piece, ORECT_Y, aes_max(orect_word(image, rect, ORECT_Y), orect_word(image, cut, ORECT_Y)));
    set_orect_word(image, piece, ORECT_H,
                   (int16_t)(aes_min(orect_far(image, rect, ORECT_Y, ORECT_H), orect_far(image, cut, ORECT_Y, ORECT_H))
                             - orect_word(image, piece, ORECT_Y)));
    switch (side) {
    case ORECT_PIECE_ABOVE:
        set_orect_word(image, piece, ORECT_Y, orect_word(image, rect, ORECT_Y));
        set_orect_word(image, piece, ORECT_H,
                       (int16_t)(orect_word(image, cut, ORECT_Y) - orect_word(image, rect, ORECT_Y)));
        break;
    case ORECT_PIECE_LEFT:
        set_orect_word(image, piece, ORECT_W,
                       (int16_t)(orect_word(image, cut, ORECT_X) - orect_word(image, rect, ORECT_X)));
        break;
    case ORECT_PIECE_RIGHT:
        set_orect_word(image, piece, ORECT_X, orect_far(image, cut, ORECT_X, ORECT_W));
        set_orect_word(image, piece, ORECT_W,
                       (int16_t)(orect_far(image, rect, ORECT_X, ORECT_W) - orect_far(image, cut, ORECT_X, ORECT_W)));
        break;
    case ORECT_PIECE_BELOW:
        set_orect_word(image, piece, ORECT_Y, orect_far(image, cut, ORECT_Y, ORECT_H));
        set_orect_word(image, piece, ORECT_H,
                       (int16_t)(orect_far(image, rect, ORECT_Y, ORECT_H) - orect_far(image, cut, ORECT_Y, ORECT_H)));
        break;
    }
    return piece;
}

/* $fe5ba8 — `rect`, the ORECT after `prior` in its list, cut by `cut`: when the two overlap (signed word edges, every
 * far edge a wrapped sum), the pieces of `rect` round the cut — decided ALL FOUR before the first is made — are linked
 * in after `prior` in the order above/left/right/below, the last of them takes `rect`'s link, and `rect` goes onto the
 * free list. The answer is the last ORECT linked (`prior` itself when no piece is left), or 0 when they do not overlap
 * and nothing is touched. */
uint32_t aes_brkrct(uint8_t *image, uint32_t cut, uint32_t rect, uint32_t prior)
{
    int16_t leaves[ORECT_PIECE_SIDES];
    int16_t side;

    if (orect_far(image, rect, ORECT_X, ORECT_W) <= orect_word(image, cut, ORECT_X)
        || orect_far(image, cut, ORECT_X, ORECT_W) <= orect_word(image, rect, ORECT_X)
        || orect_far(image, rect, ORECT_Y, ORECT_H) <= orect_word(image, cut, ORECT_Y)
        || orect_far(image, cut, ORECT_Y, ORECT_H) <= orect_word(image, rect, ORECT_Y))
        return 0;
    leaves[ORECT_PIECE_ABOVE] = orect_word(image, cut, ORECT_Y) > orect_word(image, rect, ORECT_Y);
    leaves[ORECT_PIECE_LEFT] = orect_word(image, cut, ORECT_X) > orect_word(image, rect, ORECT_X);
    leaves[ORECT_PIECE_RIGHT] = orect_far(image, cut, ORECT_X, ORECT_W) < orect_far(image, rect, ORECT_X, ORECT_W);
    leaves[ORECT_PIECE_BELOW] = orect_far(image, cut, ORECT_Y, ORECT_H) < orect_far(image, rect, ORECT_Y, ORECT_H);
    for (side = ORECT_PIECE_ABOVE; side < ORECT_PIECE_SIDES; side++) {
        if (leaves[side]) {
            uint32_t piece = aes_mkpiece(image, side, cut, rect);

            set_orect_link(image, prior, piece);
            prior = piece;
        }
    }
    set_orect_link(image, prior, orect_link(image, rect));
    set_orect_link(image, rect, free_orects(image));
    set_free_orects(image, rect);
    return prior;
}

/* $fe5c9a — everyobj's callback for each window of the window tree (the object index IS the window handle; the tree
 * is not read): the window's list cut by AES_GL_MKRECT, rectangle by rectangle, the list head read as an ORECT whose
 * link it is. A rectangle cut marks the window WIN_BROKEN and the walk goes on after its last piece — the pieces are
 * never cut again; one the cut misses is stepped over. The window index is a signed word (`muls.w #56`). */
void aes_mkrect(uint8_t *image, uint32_t tree, int16_t window)
{
    uint32_t record = table_entry(AES_WINDOWS, window, WIN_BYTES);
    uint32_t prior = record + WIN_RLIST;
    uint32_t rect = orect_link(image, prior);

    (void)tree;
    while (rect) {
        uint32_t last_piece = aes_brkrct(image, AES_GL_MKRECT, rect, prior);

        if (last_piece) {
            set_bus_word(image, record + WIN_FLAGS, (uint16_t)(bus_word(image, record + WIN_FLAGS) | WIN_BROKEN));
            prior = last_piece;
        } else {
            prior = rect;
        }
        rect = orect_link(image, prior);
    }
}
