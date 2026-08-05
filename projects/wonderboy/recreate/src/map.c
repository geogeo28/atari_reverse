/* map.c — the collision map: $10a2 (step left against it), $1400 (settle onto a platform tile)
 * and $1af0 (stamp a 2x2 block into it).
 *
 * WHAT THE MAP IS. The same shape as the background map WB_MAP_ROW_STRIDE heads: a word of bytes
 * per row, then one byte per cell, a cell being WB_MAP_CELL_PIXELS square. Turning an actor's pixel
 * position into a cell pointer is five instructions the two probes spell identically —
 * `asr.w #4` on each axis, `mulu.w` the row by the stride, `add.w` the column, and a
 * `lea WB_COLLISION_MAP_CELLS(base, index.w)` — and `cell_pointer` below is that block.
 *
 * THE ONE PLACE THE PAIR OF MAPS IS NOT SYMMETRIC, and it is this file's finding. $10a2 selects
 * between WB_COLLISION_MAP_A32 and WB_COLLISION_MAP_DEFAULT for the CELL LOOKUP, and then reads the
 * row stride it walks up and down with from `move.w $23494.l,d7` — WB_COLLISION_MAP_DEFAULT's own
 * word, unconditionally, whichever map the lookup used. Reproduced rather than tidied: in the A32
 * mode the ground test above and below the cell is taken at the OTHER map's row pitch. Two cases in
 * test/test_map.py seed the two strides apart so that a "fixed" port fails.
 *
 * THREE SEMANTICS FROM docs/m68k-disassembly.md, all of them live here:
 *   * `mulu.w` writes the WHOLE 32-bit product, and the `add.w` after it touches only the low word
 *     — so the product's high half survives into the d1 this routine hands back.
 *   * `lea d16(An,Dn.w)` sign-extends the index's LOW WORD, so a cell index past $7fff addresses
 *     BELOW the map rather than far above it.
 *   * `adda.w` (the stamp's row step) sign-extends its operand as well.
 * And one from the same page's other half: `cmpi.w #$10,d7 / blt` is a signed comparison of the
 * OPERAND, while `tst.w d3 / bpl` really is the wrapped value's own sign bit.
 */
#include <stdint.h>

#include "machine.h"
#include "map.h"
#include "wonderboy.h"

/* Which map WB_STATE_FLAG_A32 names. A `beq` over the A32 arm, so this is the NONZERO reading
 * `followed_actor_record` uses and not the sign test `project_actor_list` uses on the same word. */
static uint32_t collision_map(const uint8_t *image) {
    if (be16(image + WB_STATE_FLAG_A32) != 0)
        return WB_COLLISION_MAP_A32;
    return WB_COLLISION_MAP_DEFAULT;
}

/* The cell at (column, row) of `map`, plus the 32-bit `mulu.w` product the original leaves in d1.
 * Both probes need the product as well as the pointer, because it is half of what they return. */
static uint32_t cell_pointer(const uint8_t *image, uint32_t map, uint16_t column, uint16_t row,
                             uint32_t *row_product) {
    uint32_t product = (uint32_t)be16(image + map) * row;       /* `mulu.w d2,d1` — unsigned */
    uint16_t index = (uint16_t)(product + column);              /* `add.w d0,d1` — low word only */

    *row_product = product;
    return addr_add(map, WB_COLLISION_MAP_CELLS + sign_ext16(index));
}

/* One pixel coordinate into the cell it falls in: `asr.w #4`, an ARITHMETIC shift, so a position
 * left of the map's origin names a negative column rather than a huge positive one. */
static uint16_t pixel_to_cell(uint16_t pixels) {
    return (uint16_t)((int16_t)pixels >> WB_MAP_CELL_SHIFT);
}

/* The three tests $10a2's tail runs on the cells above and below the one it stopped at. `offset` is
 * the original's d7, used as a sign-extended word index off the cell pointer. */
static int cell_is(const uint8_t *image, uint32_t cell, uint16_t offset, uint8_t tile) {
    return image[addr_add(cell, sign_ext16(offset))] == tile;
}

uint32_t actor_step_left_against_map(uint8_t *image, uint32_t actor, uint32_t step,
                                     uint32_t *ground) {
    uint16_t remaining = (uint16_t)step;                /* d7 */
    uint8_t outcome = WB_MAP_STEP_CLEAR;                /* d6 */
    uint32_t cell;                                      /* a6 */
    uint32_t row_product;                               /* d1, before its low word is cleared */
    uint16_t column;                                    /* d0's low word at the moment it is read */
    uint16_t flags;

    for (;;) {
        uint16_t probe = (uint16_t)(be16(image + addr_add(actor, WB_ACTOR_X))
                                    - be16(image + addr_add(actor, WB_ACTOR_HALF_WIDTH))
                                    - remaining);       /* d3, kept for its SIGN */
        column = pixel_to_cell(probe);
        cell = cell_pointer(image, collision_map(image), column,
                            pixel_to_cell((uint16_t)(be16(image + addr_add(actor, WB_ACTOR_Y)) - 1)),
                            &row_product);

        if (image[cell] != WB_MAP_TILE_BLOCK) {
            /* `tst.w d3 / bpl` — the wrapped probe's own sign bit, not a comparison. */
            if ((int16_t)probe >= 0) {
                wr16(image + addr_add(actor, WB_ACTOR_X),
                     (uint16_t)(be16(image + addr_add(actor, WB_ACTOR_X)) - remaining));
                break;
            }
            /* Off the map's left edge: park the actor against it, and report blocked. */
            wr16(image + addr_add(actor, WB_ACTOR_X),
                 be16(image + addr_add(actor, WB_ACTOR_HALF_WIDTH)));
            outcome = WB_MAP_STEP_BLOCKED;
            break;
        }

        outcome = WB_MAP_STEP_BLOCKED;
        /* One pixel less of step and try again — and on an EXACT zero the routine still commits the
         * (now zero) move, so the x word is written on every path out of this loop. */
        if (--remaining == 0) {
            wr16(image + addr_add(actor, WB_ACTOR_X),
                 (uint16_t)(be16(image + addr_add(actor, WB_ACTOR_X)) - remaining));
            break;
        }
        if (be16(image + addr_add(actor, WB_ACTOR_TYPE)) == WB_ACTOR_TYPE_PLAYER)
            image[addr_add(actor, WB_ACTOR_FIELD_22)] = 0;
    }

    /* The stride the ground test steps by is WB_COLLISION_MAP_DEFAULT's, whichever map was walked
     * above — see this file's header. */
    uint16_t stride = be16(image + WB_COLLISION_MAP_DEFAULT);

    if (image[cell] == WB_MAP_TILE_BLOCK) {
        /* `neg.w d7`: the cell is a block, so the question is whether the one ABOVE it is too. */
        uint16_t above = (uint16_t)-stride;
        flags = cell_is(image, cell, above, WB_MAP_TILE_BLOCK) ? 0 : WB_MAP_GROUND_HEAD_BIT;
    } else if (cell_is(image, cell, stride, WB_MAP_TILE_BLOCK)
               || cell_is(image, cell, stride, WB_MAP_TILE_LEDGE)) {
        flags = 0;
    } else {
        uint16_t two_rows = (uint16_t)(stride + stride);        /* `add.w d7,d7` */
        flags = WB_MAP_GROUND_NEAR_BIT;
        if (!cell_is(image, cell, two_rows, WB_MAP_TILE_BLOCK)
            && !cell_is(image, cell, two_rows, WB_MAP_TILE_LEDGE))
            flags |= WB_MAP_GROUND_FAR_BIT;
    }

    /* `clr.w d1` clears the low word and leaves the product's high one; `move.b d6,d0` replaces
     * only the low byte of a d0 whose low word still holds the column. */
    *ground = set_low_word(row_product, flags);
    return set_low_byte(column, outcome);
}

void actor_settle_on_platform(uint8_t *image, uint32_t actor, uint32_t cell, uint32_t span,
                              uint32_t subcell) {
    uint32_t cursor = cell;                             /* a6 */
    uint16_t remaining = (uint16_t)span;                /* d7 */
    int on_platform;

    /* Walk the footprint a whole cell at a time. `cmpi.w #$10,d7 / blt` is a SIGNED comparison of
     * the operand, so a negative span never enters the loop at all. */
    while (image[cursor] != WB_MAP_TILE_PLATFORM
           && (int16_t)remaining >= (int16_t)WB_MAP_CELL_PIXELS) {
        cursor = addr_add(cursor, 1);
        remaining = (uint16_t)(remaining - WB_MAP_CELL_PIXELS);
    }
    on_platform = image[cursor] == WB_MAP_TILE_PLATFORM;

    if (!on_platform) {
        /* The leftover span decides whether the footprint reaches into ONE more cell: the actor's
         * own position within its cell (d2) has to be at least as far in as the leftover puts it. */
        uint16_t edge = (uint16_t)(-(int16_t)((int16_t)remaining >> 1)) & WB_MAP_CELL_MASK;
        if ((int16_t)(uint16_t)subcell >= (int16_t)edge) {
            cursor = addr_add(cursor, 1);
            on_platform = image[cursor] == WB_MAP_TILE_PLATFORM;
        }
    }

    if (on_platform) {
        int16_t actor_y = (int16_t)be16(image + addr_add(actor, WB_ACTOR_Y));
        int16_t top = (int16_t)(be16(image + WB_PLATFORM_Y) - WB_PLATFORM_Y_ABOVE);

        /* `cmp.w d1,d0 / bgt` then `addq.w #6,d0 / cmp.w 2(a0),d0 / blt`: the actor lands only from
         * inside the band [top, top + WB_PLATFORM_Y_BAND], both ends signed comparisons of the
         * operands rather than of a difference. */
        if (!(top > actor_y) && !((int16_t)(top + WB_PLATFORM_Y_BAND) < actor_y)) {
            uint8_t *flags = image + addr_add(actor, WB_ACTOR_FLAGS);

            wr16(image + addr_add(actor, WB_ACTOR_Y),
                 (uint16_t)(be16(image + WB_PLATFORM_Y) - WB_PLATFORM_STAND_OFFSET));
            *flags |= (uint8_t)(1u << WB_ACTOR_FLAG_SUPPORTED_BIT);
            image[addr_add(actor, WB_ACTOR_FLAGS2)] |= (uint8_t)(1u << WB_ACTOR_FLAGS2_LANDED_BIT);
            *flags &= (uint8_t)~((1u << WB_ACTOR_FLAG_FALLING_BIT)
                                 | (1u << WB_ACTOR_FLAG_LAUNCHED_BIT));
            image[addr_add(actor, WB_ACTOR_SPEED)] = 0;
            return;
        }
    }

    /* Nothing to stand on. A record that is still marked supported is left alone — only one that
     * has already lost its footing starts falling. */
    if (!(image[addr_add(actor, WB_ACTOR_FLAGS)] & (1u << WB_ACTOR_FLAG_SUPPORTED_BIT)))
        image[addr_add(actor, WB_ACTOR_FLAGS)] |= (uint8_t)(1u << WB_ACTOR_FLAG_FALLING_BIT);
    image[addr_add(actor, WB_ACTOR_FLAGS2)] &= (uint8_t)~(1u << WB_ACTOR_FLAGS2_LANDED_BIT);
}

void map_stamp_block(uint8_t *image) {
    uint32_t record = be32(image + WB_RECORD_PTR_10420);
    uint16_t cell = (uint16_t)(be16(image + addr_add(record, WB_RECORD_10420_CELL))
                               + WB_STAMP_CELL_BIAS);
    /* The base is WB_MAP_ROW_STRIDE's own address — the stride word — and the bias above is what
     * carries the cursor past it onto cell 0, exactly as WB_COLLISION_MAP_CELLS does. */
    uint32_t at = addr_add(WB_MAP_ROW_STRIDE, sign_ext16(cell));
    uint8_t tile = (be16(image + addr_add(record, WB_RECORD_10420_VARIANT))
                    == WB_STAMP_VARIANT_SELECTOR) ? WB_STAMP_TILES_SECOND : WB_STAMP_TILES_FIRST;

    image[at] = tile;
    image[addr_add(at, 1)] = (uint8_t)(tile + 1);
    at = addr_add(at, sign_ext16(be16(image + WB_MAP_ROW_STRIDE)));      /* `adda.w`, sign-extended */
    image[at] = (uint8_t)(tile + 2);
    image[addr_add(at, 1)] = (uint8_t)(tile + 3);
}
