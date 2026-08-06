/* rng.c — the game's PRNG ($68c6) and the per-stage draw over it ($e1f0). What ties the two
 * together, and the false green the generator carries under this oracle, are in rng.h.
 */
#include <stdint.h>

#include "machine.h"
#include "os.h"
#include "rng.h"
#include "wonderboy.h"

/* One counter's step. `addq.w #1 / cmpi.w #N / bne / clr.w` — so it is cleared when it REACHES its
 * limit, not modulo it: a counter seeded above `limit` never equals it and runs on to $ffff and
 * round. Only the counters' own three addresses can be seeded that way, and only by a test, but the
 * distinction is the whole difference between this and `(n + 1) % limit`. */
static uint16_t counter_step(uint8_t *image, uint32_t counter, uint16_t limit) {
    uint16_t stepped = (uint16_t)(be16(image + counter) + 1);
    if (stepped == limit)
        stepped = 0;
    wr16(image + counter, stepped);
    return stepped;
}

/* `move.b $ff8209.l,d0` — the shifter's video-address counter. It lies outside the image, where the
 * shim answers a read with zeros, so this is the same guarded read src/blit.c's off-image words go
 * through rather than a hardcoded 0: the address is what is stated, and the 0 follows from where it
 * is. rng.h says what that costs. */
static uint8_t video_counter_low(const uint8_t *image) {
    return os_in_image(WB_SHIFTER_VIDEO_COUNTER_LOW, 1)
           ? image[WB_SHIFTER_VIDEO_COUNTER_LOW] : (uint8_t)0;
}

uint32_t rng_next(uint8_t *image, uint32_t entry_d0) {
    uint16_t counter_a = counter_step(image, WB_RNG_COUNTER_A, WB_RNG_LIMIT_A);
    uint16_t counter_b = counter_step(image, WB_RNG_COUNTER_B, WB_RNG_LIMIT_B);
    uint16_t counter_c = counter_step(image, WB_RNG_COUNTER_C, WB_RNG_LIMIT_C);

    /* `clr.w d0 / move.b $ff8209.l,d0` zero-extends the port byte into a word BEFORE the `eor.w`,
     * so the tick's high byte survives the XOR untouched. */
    uint16_t entropy = (uint16_t)(video_counter_low(image) ^ be16(image + WB_FRAME_TICK_B39A));
    return set_low_word(entry_d0, (uint16_t)(entropy + counter_a + counter_b + counter_c));
}

uint32_t stage_random_kind8(uint8_t *image, uint32_t entry_d2) {
    /* `cmp.w #$9,d2 / ble / subq.w #6,d2` — a SIGNED word compare, and WB_STAGE_NUMBER is packed
     * BCD, so one tens carry is exactly 6. Then `subq.w #1` makes the row 0-based and `lsl.w #3`
     * scales it, all in the WORD half: a stage of 0 gives row -1 and reads BELOW the table, which is
     * what the original does. Every one of those is a `.w` op, so `entry_d2`'s HIGH half is never
     * written — and the `add.l` below is what lets it back in. */
    uint16_t stage = be16(image + WB_STAGE_NUMBER);
    if ((int16_t)stage > (int16_t)WB_STAGE_NUMBER_BCD_LIMIT)
        stage = (uint16_t)(stage - WB_STAGE_NUMBER_BCD_CARRY);
    uint32_t row = set_low_word(entry_d2,
                                (uint16_t)((uint16_t)(stage - 1) << WB_STAGE_KIND_ROW_SHIFT));

    /* `andi.l #$7,d0 / add.l d2,d0 / move.b 0(a2,d0.l),d0` — the draw is masked before it is added,
     * and both the add and the index are LONGWORD, so `row`'s inherited high half addresses the read
     * as much as the stage does. WB_BUS_ADDR_MASK is then the 68000's own last word on where that
     * lands: the address bus is 24 bits, so a sum above $ffffff comes back round rather than leaving
     * the machine. What is left off the bus is guarded like src/blit.c's off-image words — the shim
     * answers a read past the image with zeros, and only a caller with rubbish above d2's low word
     * can get there at all. */
    uint32_t at = addr_add(WB_STAGE_KIND_TABLE,
                           addr_add(rng_next(image, 0) & WB_STAGE_KIND_DRAW_MASK, row))
                  & WB_BUS_ADDR_MASK;
    uint8_t kind = os_in_image(at, 1) ? image[at] : (uint8_t)0;
    return kind & WB_STAGE_KIND_MASK;
}
