/* map.h — the collision map the actors walk on: the leftward step probe ($10a2), the platform
 * settle ($1400) and the 2x2 tile stamp ($1af0).
 *
 * A SECOND map, laid out exactly like the background one: a word of bytes per row, then one byte
 * per WB_MAP_CELL_PIXELS-square cell. Two of them exist and WB_STATE_FLAG_A32 picks between them,
 * the same flag that picks the actor table. Every address and offset is a constant in
 * wonderboy.h, which both languages read; the arguments here are the original's REGISTERS.
 */
#ifndef WONDERBOY_MAP_H
#define WONDERBOY_MAP_H

#include <stdint.h>

/* $10a2 — step `actor` LEFT by `step` pixels, refusing to enter a WB_MAP_TILE_BLOCK cell, and
 * report what is under the cell it stopped on.
 *
 * `actor` is the original's a0 and `step` its d7 (only the low word is read). The result is its
 * d0: WB_MAP_STEP_CLEAR when the very first probe was already clear, WB_MAP_STEP_BLOCKED when it
 * had to back off — but in the HIGH byte of d0's low word it also carries the probe's own map
 * column, which is what `set_low_byte` below reproduces. `ground` receives d1, whose low word is
 * the WB_MAP_GROUND_*_BIT set and whose high word is the row product `mulu.w` left there.
 *
 * FORTY-ONE `bsr` callers, more than any other routine reconstructed in this project. $1170 is its
 * un-ported mirror, stepping the other way (`add.w 14(a0),d0 / add.w d7,d0`). */
uint32_t actor_step_left_against_map(uint8_t *image, uint32_t actor, uint32_t step,
                                     uint32_t *ground);

/* $1400 — scan the `span` pixels of map from `cell` for a WB_MAP_TILE_PLATFORM cell and, if one is
 * found close enough vertically, stand `actor` on WB_PLATFORM_Y; otherwise start it falling.
 *
 * `cell`, `span` and `subcell` are the original's a6, d7 and d2 — all three handed over by $13c8,
 * which is named but NOT reconstructed: the oracle reports the d0/d1 it also leaves (the probe's
 * column and row), but its LOAD-BEARING output — the map selected, the cell pointer, the span and
 * the sub-cell — is a6/d2/d3/d7, which it does not (see ../STATUS.md). Reached by `bra.w` from
 * $13ba, so its rts returns to $1334's own caller. */
void actor_settle_on_platform(uint8_t *image, uint32_t actor, uint32_t cell, uint32_t span,
                              uint32_t subcell);

/* $1af0 — stamp four consecutive tile codes into the map as a 2x2 block, at the cell the record
 * WB_RECORD_PTR_10420 points at names. Three callers; no register argument at all. */
void map_stamp_block(uint8_t *image);

#endif /* WONDERBOY_MAP_H */
