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

#include <stddef.h>         /* NULL — the two wrappers below drop the probes' X report */
#include <stdint.h>

#include "actor_view.h"     /* ActorRecord: what every routine here takes, and what a door proves */

/* THE PROBES REPORT A THIRD THING, AND IT IS A CONDITION-CODE BIT: the 68000 X flag they leave.
 *
 * `exit_extend` is that bit, a PURE OUTPUT — neither probe ever passes the caller's X through,
 * because no path through either head reaches a branch before an X-writer (`sub.w 14(a0),d0` at
 * $10ac and `add.w 14(a0),d0` at $117a are each the fifth instruction and both are unconditional),
 * so whatever X the caller arrived with is gone before the routine can act on it.
 *
 * WHAT IT CAN CARRY is the SHARED TAIL's, three arms: two compute a value of their own out of the
 * row stride (`neg.w d7` and `add.w d7,d7`), and the middle one writes no flag at all and hands out
 * whichever of the FOUR body bits the path left — src/map.c's `map_ground_under_cell` and the two
 * commits above it are where the per-arm model lives.
 *
 * WHO READS IT: src/player.c's walk ($ec8), and through it the frame's `bsr $1208` — the X the
 * weapon's `sbcd` at $1260 folds in is the walk's exit X, and on the walk's probing paths it is
 * this one (include/player.h, ../STATUS.md's batch 41 phase E). PASS NULL when the caller does not
 * model the flag: the two wrappers at the foot of this file do, and so do the eight direct call
 * statements in src/behavior.c. THE REASON IS THAT NOTHING DOWNSTREAM READS THE BIT, not that
 * something overwrites it — the two helpers those rows feed it to (`actor_toggle_side_flag` $2b82
 * and `actor_turn_and_launch` $2b8e) contain no X-writer at all, so whether the probe's bit
 * survives to the dispatcher is a per-handler question no case here asks and no case here needs to.
 */

/* --- EVERY ROUTINE HERE IS TWO: A DOOR AND A BODY ----------------------------------------------
 *
 * The collision map's probes and settles all work on ONE actor record, and every field of it used to
 * be a `field_*` call — mask to 24 bits, bound against the image, index. include/actor_view.h proves
 * a record ONCE, in the door its caller was entered through; so each routine below is published
 * twice:
 *
 *   * `name(image, actor, ...)` — THE DOOR. The original's own register interface, what test_map.py
 *     binds by name, and what a caller holding only an address calls. It opens the view, runs the
 *     body and closes it.
 *   * `name_body(image, record, ...)` — THE BODY, for a caller that has ALREADY proved this record:
 *     src/behavior.c's handlers, each entered through a door of its own, and src/player.c's frame.
 *     `image` stays because the CELLS, the two map bases and the level's limit word are not record
 *     fields. ONLY THE THREE BODIES A SECOND MODULE CALLS ARE DECLARED HERE — the two probes' and
 *     the fall's. The two settles' and the two cell lookups' are reached from src/map.c alone, so
 *     they are `static` there and only their doors are published; a `_body` declared here that
 *     nobody outside could call would be interface nothing holds up.
 *
 * A CALLER MUST NOT OPEN A SECOND DOOR ON A RECORD IT ALREADY HOLDS — two views on the slow arm are
 * two scratches, and the second is filled from an image the first has not given back to yet
 * (include/actor_view.h). Hold the record, call the body.
 *
 * THE TWO CELL LOOKUPS KEEP THEIR `const uint8_t *image`, which is the whole claim their plates
 * make: they write no memory at all. They are opened through `actor_view_open_reading`, the door
 * that discards the const in one place and marks the view as having nothing to give back
 * (include/actor_view.h). Everything else here writes the record and takes the image as it is.
 */

/* $10a2 — step `actor` LEFT by `step` pixels, refusing to enter a WB_MAP_TILE_BLOCK cell, and
 * report what is under the cell it stopped on.
 *
 * `actor` is the original's a0 and `step` its d7 (only the low word is read). The result is its
 * d0: WB_MAP_STEP_CLEAR when the very first probe was already clear, WB_MAP_STEP_BLOCKED when it
 * had to back off — but in the HIGH byte of d0's low word it also carries the probe's own map
 * column, which is what `set_low_byte` below reproduces. `ground` receives d1, whose low word is
 * the WB_MAP_GROUND_*_BIT set and whose high word is the row product `mulu.w` left there.
 * `exit_extend` receives the X flag, per the paragraph above.
 *
 * FORTY-ONE `bsr` callers — the same count as $1170 below, the two being called in pairs by the
 * arms of a direction test; only actor_fall_and_settle $1334 has more, 46. */
uint32_t actor_step_left_against_map(uint8_t *image, uint32_t actor, uint32_t step,
                                     uint32_t *ground, unsigned *exit_extend);
uint32_t actor_step_left_against_map_body(uint8_t *image, ActorRecord record, uint32_t step,
                                          uint32_t *ground, unsigned *exit_extend);

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
                                      uint32_t *ground, unsigned *exit_extend);
uint32_t actor_step_right_against_map_body(uint8_t *image, ActorRecord record, uint32_t step,
                                           uint32_t *ground, unsigned *exit_extend);

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
 * $1334's own caller.
 *
 * RETURNS THE SPAN IT LEAVES IN d7 — what the scan below has counted the footprint down to. The
 * loop writes only d7's LOW WORD (`subi.w #$10,d7`), so the caller's high half comes back with it;
 * two behaviour handlers read the byte inside it (see actor_fall_and_settle below). */
uint32_t actor_settle_on_platform(uint8_t *image, uint32_t actor, uint32_t cell, uint32_t span,
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
 * ONE caller, the `bsr.w` at $13b2 inside actor_fall_and_settle, plus its own `bra.s` loop-back.
 * Returns the same counted-down span $1400 does, by the same loop. */
uint32_t actor_settle_on_tile_1_or_2(uint8_t *image, uint32_t actor, uint32_t cell, uint32_t span,
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
 * $1492's landing arm may itself have moved y between the two `bsr $13be` sites.
 *
 * AND IT HANDS d7 BACK, because two callers read a BYTE of it. `entry_span` is d7 on the way in and
 * comes back UNCHANGED on the two early exits (neither writes the register at all); on every other
 * path the return is $1400's counted-down span, whose low word is therefore below
 * WB_MAP_CELL_PIXELS for any non-negative footprint. Behaviour slots 3 and 6 then spell
 * `move.b #$2,d7`, which replaces only the low BYTE — so what they step by carries whatever this
 * routine left above it (src/behavior.c). */
uint32_t actor_fall_and_settle(uint8_t *image, uint32_t actor, uint32_t entry_span);
uint32_t actor_fall_and_settle_body(uint8_t *image, ActorRecord record, uint32_t entry_span);

/* What a call hands `entry_span` where nothing reads the register back. The value really is the
 * CALLER's own entry d7 — a death arm reaches the settle without $23b6 or $5c6e having run, and
 * `actor_behavior_type01_player`'s `bsr.w $1334` at $a5c inherits whatever the eight calls above it
 * left — and no memory depends on it: `move.w 14(a0),d7` at $13f8 replaces the low word before
 * anything reads it, and the two exits above that instruction read it not at all. Only src/behavior.c's
 * two walk arms hand over a value they can name.
 *
 * IT IS HERE RATHER THAN IN src/behavior.c, where it was through batch 41 phase E, because
 * src/player.c's frame is a second file that needs it and one literal in two files is one too many
 * (CLAUDE.md §5). This header declares the function it belongs to. */
#define WB_SETTLE_SPAN_UNREAD 0u

/* $1af0 — stamp four consecutive tile codes into the map as a 2x2 block, at the cell the record
 * WB_RECORD_PTR_10420 points at names. Three callers; no register argument at all. */
void map_stamp_block(uint8_t *image);


/* ONE PROBE WITH THE GROUND FLAGS AND THE X REPORT DROPPED — for the callers that have no use for
 * d1, which is most of them but NOT all: src/behavior.c has FOUR direction tests, eight call
 * statements between them, that reach `actor_step_*_against_map` DIRECTLY and feed the ground word
 * on to `actor_toggle_side_flag` or `actor_turn_and_launch`, and those keep their own `ground`
 * local. (Both counts are of the same thing and the header used to give only the first; they are
 * spelt together here because a census keyed off either one alone misses half the sites.) So the
 * claim is about these two wrappers' users, not about the tier.
 *
 * THEIR ONE MODULE IS src/behavior.c, as of batch 41 phase E. They were put here when it was two —
 * src/player.c's walk had six probe sites of its own — and that walk now reaches the probes through
 * `player_probe_step`, because it needs the X these two drop and it needs it at all six sites. They
 * stay here rather than moving back: TWENTY-FOUR call sites in behavior.c is reason enough for a
 * named wrapper, and phase F's frame will bring the X-reporting spelling back into a second module.
 * Same rule, and the same `static inline`, as bus.h's record accessors. */
static inline uint32_t step_left(uint8_t *image, ActorRecord record, uint32_t step) {
    uint32_t ground = 0;
    return actor_step_left_against_map_body(image, record, step, &ground, NULL);
}

static inline uint32_t step_right(uint8_t *image, ActorRecord record, uint32_t step) {
    uint32_t ground = 0;
    return actor_step_right_against_map_body(image, record, step, &ground, NULL);
}

#endif /* WONDERBOY_MAP_H */
