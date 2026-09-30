/* rect.c — the AES's rectangle helpers (`aes/rect.h`). Hand 68000 in the ROM, ported to C over its own ORDER and
 * its own WIDTHS: every sum is a word that wraps, every compare signed, and the second GRECT is written in place.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "transcribed.h"
#include "aes/objects.h"
#include "aes/rect.h"

/* An empty `asm` that clobbers memory: what the compiler knows of every word is forgotten, so the next read of one
 * is a read. The ROM re-reads nothing it can keep in a register, but it keeps its first answer on the STACK
 * (`move.w sr,-(sp)`) where C can only keep it in a register; recomputing it from the words the pass stored costs
 * three reads and frees that register (see `aes_rc_intersect`). */
#define REREAD_STORED_WORDS() __asm__ volatile("" ::: "memory")

static inline int16_t grect_word(const uint8_t *rect, uint32_t field)
{
    return (int16_t)be16(rect + field);
}

/* One axis of the intersection: the larger origin and the smaller far edge (each edge a WORD sum, which wraps),
 * stored into `rect` as origin then extent — the extent the far edge less the origin, wrapped too. The answer is
 * whether the axis is non-empty, and it is the `ble` after the ROM's `sub.w`: the far edge GREATER than the origin
 * as a signed compare with the overflow folded in, not the stored extent's sign ($fecd44, $fecd74).
 *
 * The origin is SETTLED in a register before the far edge is formed, as the ROM forms them — D0, then D1 and D2:
 * left free, GCC forms all four edge words at once and holds a register more across the whole routine. */
static inline int axis_overlaps(const uint8_t *clip, uint8_t *rect, uint32_t origin_field, uint32_t extent_field)
{
    int16_t origin = grect_word(rect, origin_field);
    int16_t far_edge;

    if (origin < grect_word(clip, origin_field))
        origin = grect_word(clip, origin_field);
    REGISTER_BARRIER(origin, REGISTER_BARRIER_DATA_CLASS);
    far_edge = (int16_t)(grect_word(rect, origin_field) + grect_word(rect, extent_field));
    if (far_edge > (int16_t)(grect_word(clip, origin_field) + grect_word(clip, extent_field)))
        far_edge = (int16_t)(grect_word(clip, origin_field) + grect_word(clip, extent_field));
    wr16(rect + origin_field, (uint16_t)origin);
    wr16(rect + extent_field, (uint16_t)(far_edge - origin));
    return far_edge > origin;
}

/* A GRECT pointer held as the ROM holds it: put on the bus ONCE, each word then a displacement from it. The ROM's
 * `d16(An)` would wrap a GRECT straddling the top of the 24-bit bus word by word; re-wrapping each word here measured
 * 1.25-1.43 at Tier 3 against the bar's 1.10, and the ROM can be handed such a GRECT only in the I/O page, which no
 * model serves. So the HOST refuses one by name (`bus_span`, whose odd-address refusal is the 68000's address error)
 * — a bound the differential cannot state — rather than read past its image (`test_aes_rect.py` pins the refusal and
 * the last GRECT that fits); the target's bus wraps it on its own. */
static inline uint8_t *grect_at(uint8_t *image, uint32_t rect)
{
    return image + bus_span(rect, GRECT_BYTES);
}

/* $fecca6 — r_get: the four words of `rect` out through four pointers, each word read and stored before the next is
 * read (`move.w (a0)+,(a1)`, four times) — so an answer word laid over a later field of `rect` is read back as
 * stored. */
TRANSCRIBED_CORE
void aes_r_get(uint8_t *image, uint32_t rect, uint32_t x_out, uint32_t y_out, uint32_t w_out, uint32_t h_out)
{
    const uint8_t *from = grect_at(image, rect);

    set_bus_word(image, x_out, be16(from + GRECT_X));
    set_bus_word(image, y_out, be16(from + GRECT_Y));
    set_bus_word(image, w_out, be16(from + GRECT_W));
    set_bus_word(image, h_out, be16(from + GRECT_H));
}

/* $feccbe — r_set: `rect` := (x, y, w, h). The ROM loads the four frame words as TWO LONGWORDS (`movem.l 4(sp),a0-a2`)
 * and stores them as two (`movem.l a1-a2,(a0)`): x and y together, then w and h. */
TRANSCRIBED_CORE
void aes_r_set(uint8_t *image, uint32_t rect, int16_t x, int16_t y, int16_t w, int16_t h)
{
    uint8_t *to = grect_at(image, rect);

    wr32(to + GRECT_X, (uint32_t)(uint16_t)x << M68K_WORD_BITS | (uint16_t)y);
    wr32(to + GRECT_W, (uint32_t)(uint16_t)w << M68K_WORD_BITS | (uint16_t)h);
}

/* $feccca — rc_copy: the GRECT at `from` into `to`, as two longwords each read and stored in turn
 * (`move.l (a0)+,(a1)+`): a `to` laid one longword above `from` copies the first longword twice. */
TRANSCRIBED_CORE
void aes_rc_copy(uint8_t *image, uint32_t from, uint32_t to)
{
    const uint8_t *source = grect_at(image, from);
    uint8_t *destination = grect_at(image, to);

    wr32(destination + GRECT_X, be32(source + GRECT_X));
    wr32(destination + GRECT_W, be32(source + GRECT_W));
}

/* $feccd6 — inside: 1 when the point (x, y) lies in `rect` — at or past its origin and short of its far edges, each
 * far edge a WORD sum and every compare signed (`blt`/`bge` to the shared tails). */
int16_t aes_inside(uint8_t *image, int16_t x, int16_t y, uint32_t rect)
{
    const uint8_t *at = grect_at(image, rect);

    if (x < grect_word(at, GRECT_X) || y < grect_word(at, GRECT_Y))
        return 0;
    if (x >= (int16_t)(grect_word(at, GRECT_X) + grect_word(at, GRECT_W)))
        return 0;
    return y < (int16_t)(grect_word(at, GRECT_Y) + grect_word(at, GRECT_H));
}

/* $fecd0c — rc_equal: 1 when the two GRECTs hold the same four words, compared as two longwords (`cmpm.l`); the
 * second pair is read only when the first matched. */
TRANSCRIBED_CORE
int16_t aes_rc_equal(uint8_t *image, uint32_t first, uint32_t second)
{
    const uint8_t *one = grect_at(image, first);
    const uint8_t *other = grect_at(image, second);

    return be32(one + GRECT_X) == be32(other + GRECT_X) && be32(one + GRECT_W) == be32(other + GRECT_W);
}

/* $fecd22 — `rect` cut down to its intersection with `clip`: x and w stored before y and h are read, so a `clip`
 * laid over `rect` reads the x pass's stores. BOTH axes are computed and stored whatever the first found; the
 * answer is 1 only when both are non-empty. The ROM loads the two pointers ONCE (`movem.l 4(sp),a0-a1`) and reaches
 * every word as a displacement from them, so the C holds them too (`grect_at`).
 *
 * THE X AXIS's ANSWER IS RECOMPUTED FROM ITS OWN STORES, after the y pass, rather than kept: rect.x is the origin
 * and rect.w the far edge less it, so their word sum IS the far edge, and nothing the y pass does can reach either
 * (it stores rect.y and rect.h alone). Kept in a register, it costs a second saved register and GCC's
 * set/negate/and tail: 1.12-1.13 on an empty intersection, against the bar's 1.10. */
int16_t aes_rc_intersect(uint8_t *image, uint32_t clip, uint32_t rect)
{
    const uint8_t *clip_at = grect_at(image, clip);
    uint8_t *rect_at = grect_at(image, rect);

    axis_overlaps(clip_at, rect_at, GRECT_X, GRECT_W);
    REREAD_STORED_WORDS();
    if (!axis_overlaps(clip_at, rect_at, GRECT_Y, GRECT_H))
        return 0;
    return (int16_t)(grect_word(rect_at, GRECT_X) + grect_word(rect_at, GRECT_W)) > grect_word(rect_at, GRECT_X);
}

/* One axis of the union: the smaller origin and the larger far edge (word sums, signed compares), both formed from
 * the axis's reads before either is stored, then stored origin first. A tie takes `from`'s origin and `into`'s far
 * edge, equal values either way. */
static inline void axis_union(const uint8_t *from, uint8_t *into, uint32_t origin_field, uint32_t extent_field)
{
    int16_t origin = grect_word(into, origin_field);
    int16_t far_edge = (int16_t)(grect_word(into, origin_field) + grect_word(into, extent_field));
    int16_t from_far_edge = (int16_t)(grect_word(from, origin_field) + grect_word(from, extent_field));

    if (origin >= grect_word(from, origin_field))
        origin = grect_word(from, origin_field);
    if (far_edge <= from_far_edge)
        far_edge = from_far_edge;
    wr16(into + origin_field, (uint16_t)origin);
    wr16(into + extent_field, (uint16_t)(far_edge - origin));
}

/* $fecd8c — rc_union: `into` grown to cover `from` too, x and w stored before the y pass reads — so a `from` laid
 * one word below `into` (its y over into's x) reads the x pass's stores. */
TRANSCRIBED_CORE
void aes_rc_union(uint8_t *image, uint32_t from, uint32_t into)
{
    const uint8_t *source = grect_at(image, from);
    uint8_t *target = grect_at(image, into);

    axis_union(source, target, GRECT_X, GRECT_W);
    axis_union(source, target, GRECT_Y, GRECT_H);
}

/* One axis of the constraint, in the ROM's order: the origin pulled up to the container's (stored only when the
 * container's is not below it), THEN the container's far edge formed — its extent read after that store — and, when
 * the rectangle's far edge (re-read) passes it, the origin pulled back to it less the rectangle's extent. The
 * extent itself is never changed: a rectangle wider than its container ends with its far edge on the container's. */
static inline void axis_constrain(const uint8_t *container, uint8_t *rect, uint32_t origin_field, uint32_t extent_field)
{
    int16_t origin = grect_word(container, origin_field);
    int16_t far_edge;

    if (origin >= grect_word(rect, origin_field))
        wr16(rect + origin_field, (uint16_t)origin);
    far_edge = (int16_t)(origin + grect_word(container, extent_field));
    if (far_edge < (int16_t)(grect_word(rect, origin_field) + grect_word(rect, extent_field)))
        wr16(rect + origin_field, (uint16_t)(far_edge - grect_word(rect, extent_field)));
}

/* $fecde4 — rc_constrain: `rect` moved (never resized) to lie inside `container`, x then y. */
TRANSCRIBED_CORE
void aes_rc_constrain(uint8_t *image, uint32_t container, uint32_t rect)
{
    const uint8_t *bounds = grect_at(image, container);
    uint8_t *moved = grect_at(image, rect);

    axis_constrain(bounds, moved, GRECT_X, GRECT_W);
    axis_constrain(bounds, moved, GRECT_Y, GRECT_H);
}
