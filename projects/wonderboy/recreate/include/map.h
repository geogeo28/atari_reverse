/* map.h — the collision map the actors walk on: the two step probes ($10a2 leftward, $1170
 * rightward), the cell lookup they are built on ($13be/$13c8), the platform settle ($1400) and the
 * 2x2 tile stamp ($1af0).
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
 * FORTY-ONE `bsr` callers — the same count as $1170 below, the two being called in pairs by the
 * arms of a direction test; only actor_fall_and_settle $1334 has more, 46. */
uint32_t actor_step_left_against_map(uint8_t *image, uint32_t actor, uint32_t step,
                                     uint32_t *ground);

/* $1170 — step `actor` RIGHT by `step` pixels, refusing to enter a WB_MAP_TILE_BLOCK cell, and
 * refusing to take its right edge past the level's own.
 *
 * The same register interface as $10a2 above (a0, d7, out through d0 and d1), and the same ground
 * flags: its two exits both `bra.w` INTO $10a2's tail rather than returning, so the d1 they hand
 * back is computed by the same instructions and carries the same asymmetry. What differs is the
 * walk. The probe is `x + 14(a0) + d7` rather than `x - 14(a0) - d7`, and instead of the left
 * probe's sign test there is a CLAMP: WB_BG_SCROLL_LIMIT_X + WB_BG_SCROLL_LIMIT_BIAS (or the bias
 * alone while WB_STATE_FLAG_A32 is set — that mode has no limit word) compared against the
 * UNSHIFTED probe, and an actor past it is parked with its right edge on the limit.
 *
 * So d0's low word under the outcome byte is NOT always a map column here: it is the column when
 * the walk ran its step out, the LIMIT when the compare committed the move, and the PARKED x when
 * the clamp fired — and on that last path the byte is a literal WB_MAP_STEP_BLOCKED rather than
 * the walk's own verdict. Three of the callers read that whole low word ($41ae, $4cf4, $4e98),
 * eleven read the byte alone and the rest overwrite d0 unread.
 *
 * FORTY-ONE `bsr` callers and nothing else — no `jsr`, no `jmp`. No caller reads d1 on its
 * straight-line continuation, but the reconstruction hands it back because the shared tail computes
 * it and $10a2's interface is that pair. */
uint32_t actor_step_right_against_map(uint8_t *image, uint32_t actor, uint32_t step,
                                      uint32_t *ground);

/* The registers $13c8 takes and leaves, which is the whole of its interface — it writes no memory.
 * Register map: cell = a6, sub_cell = d2, cell_index = d3, span = d7, column = d0, row = d1.
 *
 * EVERY FIELD IS IN AND OUT, because every write the routine makes is a WORD write into a longword
 * register and the caller's high half survives it. Only two fields are pure outputs: `cell`, which
 * a `lea` replaces, and `cell_index`, which a `mulu.w` writes all 32 bits of. The one value read on
 * the way in is `column`'s LOW WORD — the pixel x the caller has already computed. */
typedef struct {
    uint32_t cell;          /* the cell's address: map + WB_COLLISION_MAP_CELLS + the index,
                             * SIGN-EXTENDED, so an index past $7fff addresses below the map */
    uint32_t sub_cell;      /* the pixel x's position WITHIN its cell (& WB_MAP_CELL_MASK) */
    uint32_t cell_index;    /* the row x stride product, with the cell index in its low word */
    uint32_t span;          /* twice WB_ACTOR_HALF_WIDTH: the footprint's whole width in pixels */
    uint32_t column;        /* in: the pixel x. out: the map column it falls in (`asr.w #4`) */
    uint32_t row;           /* the map row WB_ACTOR_Y falls in, by the same signed shift */
} map_cell_probe;

/* $13c8 — look `probe->column`'s pixel x up in whichever collision map WB_STATE_FLAG_A32 names, and
 * fill in the cell, the sub-cell, the index, the span and the two coordinates. ONE `bsr` caller
 * ($1344, which passes the actor's own x), plus the fall-through below. */
void actor_map_cell_lookup(const uint8_t *image, uint32_t actor, map_cell_probe *probe);

/* $13be — the same lookup for the actor's LEFT EDGE: d0 := x - half_width, with d0 and d1 cleared
 * as longs first. It has no `rts` and falls straight through into $13c8, exactly as text_plot_char
 * falls into text_plot_glyph, so it is written as the prelude calling it. Two `bsr` callers, $13ae
 * and $13b6. */
void actor_map_cell_from_actor_x(const uint8_t *image, uint32_t actor, map_cell_probe *probe);

/* $1400 — scan the `span` pixels of map from `cell` for a WB_MAP_TILE_PLATFORM cell and, if one is
 * found close enough vertically, stand `actor` on WB_PLATFORM_Y; otherwise start it falling.
 *
 * `cell`, `span` and `subcell` are the original's a6, d7 and d2 — the three `map_cell_probe` fields
 * of the same name, which $13c8 hands over. Reached by `bra.w` from $13ba, so its rts returns to
 * $1334's own caller. */
void actor_settle_on_platform(uint8_t *image, uint32_t actor, uint32_t cell, uint32_t span,
                              uint32_t subcell);

/* $1492 — $1400's sibling: scan the same footprint for a WB_MAP_TILE_BLOCK or WB_MAP_TILE_LEDGE
 * cell instead of a WB_MAP_TILE_PLATFORM one, and stand `actor` on the cell boundary if one is
 * there. Same register interface (a0, a6, d7, d2) and the same `cmpi.w #$10,d7` signed step.
 *
 * WHAT IS DIFFERENT, AND WHY THIS IS NOT $1400 WITH A TILE ARGUMENT. Three things, and each is a
 * different mechanism rather than a different constant:
 *   * TWO tile codes are accepted at every test, not one, so the scan's loop test and both of its
 *     sub-cell tests are a PAIR of `cmpi.b`s.
 *   * The landing arm parks the actor by MASKING its own y (`andi.w #$fff0,2(a0)` — the top of
 *     whatever cell it is in) instead of on WB_PLATFORM_Y, and it raises no
 *     WB_ACTOR_FLAGS2_LANDED_BIT and applies no vertical band test at all.
 *   * The not-found arm is `actor_accelerate_fall` — the WHOLE of it, which is why this routine's
 *     body physically ENCLOSES that one (see src/map.c).
 *
 * ONE caller, the `bsr.w` at $13b2 inside actor_fall_and_settle, plus its own `bra.s` loop-back. */
void actor_settle_on_tile_1_or_2(uint8_t *image, uint32_t actor, uint32_t cell, uint32_t span,
                                 uint32_t subcell);

/* $1334 — the tier above all of the above: add the record's own WB_ACTOR_SPEED to its y and settle
 * it against the map. FORTY-SIX `bsr` callers and no `jsr`/`jmp`.
 *
 * It takes the record in a0 and nothing else, and it has NO `rts` on its main path: it ends in
 * `bra.w $1400`, so actor_settle_on_platform's own `rts` returns to this routine's caller. Two of
 * its four exits are its own (`rts` at $1362 and at $1380); the other two are that one and
 * actor_accelerate_fall's, reached through $1492.
 *
 * THE PLAYER-ONLY HEAD. For a WB_ACTOR_TYPE_PLAYER record only, the cell under the record's OWN x
 * (not its left edge — $1344 enters actor_map_cell_lookup directly with `move.w (a0),d0`) is
 * tested against WB_MAP_TILE_33, and the three WB_TILE_33_* words are raised or cleared by it.
 * While WB_TILE_33_MODE is set on such a cell the routine returns at once, so nothing below runs.
 *
 * THE CELL THE TWO SETTLES SCAN IS TAKEN AFTER THE y MOVE, not before — and TWICE, because
 * $1492's landing arm may itself have moved y between the two `bsr $13be` sites. */
void actor_fall_and_settle(uint8_t *image, uint32_t actor);

/* $1af0 — stamp four consecutive tile codes into the map as a 2x2 block, at the cell the record
 * WB_RECORD_PTR_10420 points at names. Three callers; no register argument at all. */
void map_stamp_block(uint8_t *image);

#endif /* WONDERBOY_MAP_H */
