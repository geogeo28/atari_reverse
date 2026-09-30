/* rect.c — the AES's rectangle helpers (`aes/rect.h`). Hand 68000 in the ROM, ported to C over its own ORDER and
 * its own WIDTHS: every sum is a word that wraps, every compare signed, and the second GRECT is written in place.
 */
#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
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
 * model serves. So the HOST refuses one — a bound the differential cannot state — rather than read past its image
 * (`test_aes_rect.py` pins the refusal and the last GRECT that fits); the target's bus wraps it on its own. */
static inline uint8_t *grect_at(uint8_t *image, uint32_t rect)
{
    uint32_t at = bus_dereference(rect);

#ifdef RECREATE_HOST_DIFFERENTIAL
    assert(at <= OS_BUS_ADDR_MASK + 1 - GRECT_BYTES);
#endif
    return image + at;
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
