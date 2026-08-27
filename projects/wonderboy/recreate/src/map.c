/* map.c — the collision map: $10a2 and $1170 (step left and right against it), $13be/$13c8 (the
 * cell lookup itself), $1400 and $1492 (settle onto a platform tile, and onto a block or ledge),
 * $1334 (the fall pass that drives both of those) and $1af0 (stamp a 2x2 block into it).
 *
 * WHAT THE MAP IS. The same shape as the background map WB_MAP_ROW_STRIDE heads: a word of bytes
 * per row, then one byte per cell, a cell being WB_MAP_CELL_PIXELS square. Turning an actor's pixel
 * position into a cell pointer is five instructions the two probes spell identically —
 * `asr.w #4` on each axis, `mulu.w` the row by the stride, `add.w` the column, and a
 * `lea WB_COLLISION_MAP_CELLS(base, index.w)` — and `cell_pointer` below is that block.
 *
 * WHY THAT BLOCK IS BOTH INLINE AND A FUNCTION OF ITS OWN. $13c8 IS the block, as a routine the
 * game calls; it is reconstructed here too, and the copy inside actor_step_left_against_map is not
 * a second spelling of it — both go through the one `collision_map`/`cell_pointer`/`pixel_to_cell`
 * pair below. The probe INLINES it because the probe's own write set is what makes the block
 * observable: a memory differential can see the arithmetic only where a byte comes of it. $13c8
 * writes NO memory at all, so it became verifiable only when the kit's oracle began reporting every
 * register a routine leaves — a6, d2, d3 and d7, which is the whole of what it hands its callers,
 * as well as the d0/d1 by-products it used to report alone.
 *
 * THE ONE PLACE THE PAIR OF MAPS IS NOT SYMMETRIC, and it is this file's finding. $10a2 selects
 * between WB_COLLISION_MAP_A32 and WB_COLLISION_MAP_DEFAULT for the CELL LOOKUP, and then reads the
 * row stride it walks up and down with from `move.w $23494.l,d7` — WB_COLLISION_MAP_DEFAULT's own
 * word, unconditionally, whichever map the lookup used. Reproduced rather than tidied: in the A32
 * mode the ground test above and below the cell is taken at the OTHER map's row pitch. Two cases in
 * test/test_map.py seed the two strides apart so that a "fixed" port fails — and since $1170 jumps
 * INTO that same instruction, the asymmetry is the right-hand probe's as well.
 *
 * $1492 ENCLOSES actor_accelerate_fall, AND THAT IS WHY IT IS WRITTEN AS A CALL. The 32 bytes of
 * $14d6 sit INSIDE $1492's span ($1492..$1513, 130 bytes; Ghidra reports 98 for $1492 because it
 * subtracts them), and $1492 reaches them TWICE: `blt.w $14d6` at $14c0, and the not-taken
 * `beq.w $14f6` at $14d2 falling straight in. Both arms then leave through $14d6's own `rts` at
 * $14f4, which is one of $1492's two exits — the other being its landing arm's at $1512. So the
 * enclosure is not an overlap to be represented: it is a routine whose not-found arm IS another
 * routine, and it is written here as `actor_accelerate_fall(...); return;` at both sites, exactly
 * as $13be is written as a prelude that calls $13c8 and as the two probes share the tail below.
 * test/test_map.py pins the whole 130 bytes, with the enclosed 32 asserted as
 * actor_accelerate_fall's own — so 130 = 98 + 32 fails there if either number moves.
 *
 * THE TWO PROBES END IN ONE PIECE OF CODE, WHICH IS WHY THE TAIL IS A FUNCTION HERE. $1170 has no
 * `rts`: both of its exits are `bra.w $111a`, thirteen instructions inside $10a2's body. A scan of
 * the whole image finds exactly three branches to $111a — $1112 in $10a2 and $11fc/$1204 in $1170 —
 * and no `bsr` or `jsr` at all, so the ground test below is shared code and gets ONE spelling here.
 * The heads are NOT shared: $1170 adds where $10a2 subtracts, and its clamp arm is a different
 * mechanism (a scroll limit read out of memory, against the unshifted probe) rather than the same
 * one with a sign in it.
 *
 * THREE SEMANTICS FROM docs/m68k-disassembly.md, all of them live here:
 *   * `mulu.w` writes the WHOLE 32-bit product, and the `add.w` after it touches only the low word
 *     — so the product's high half survives into the d1 this routine hands back.
 *   * `lea d16(An,Dn.w)` sign-extends the index's LOW WORD, so a cell index past $7fff addresses
 *     BELOW the map rather than far above it.
 *   * `adda.w` (the stamp's row step) sign-extends its operand as well.
 * And one from the same page's other half: `cmpi.w #$10,d7 / blt` is a signed comparison of the
 * OPERAND, while `tst.w d3 / bpl` really is the wrapped value's own sign bit.
 *
 * THE CELL GOES THROUGH bus.h AND THE RECORD NO LONGER DOES, AND THE DIFFERENCE IS WHO PROVED IT.
 * Two address families here are unbounded, and they are unbounded for different reasons:
 *   * the CELL, and it is the ARGUMENT that is unbounded rather than the arithmetic. `cell_pointer`
 *     returns `map + WB_COLLISION_MAP_CELLS + sign_ext16(index)`, and a sign-extended WORD index
 *     moves a base of $1d338 or $23494 by at most ±32768 — so its own result cannot leave a 1 MB
 *     image. What can is the a6 the two SETTLE routines are entered with: they take the cell from a
 *     caller, `cell_is` then steps it by a stride read out of memory, and `scene_clear_marker_pair`
 *     next door takes one straight out of WB_SCENE_MARKER_CELL_PTR. Every cell access below is
 *     therefore still `bus_read_byte`, and that guard is SEMANTIC: it is computed from coordinates
 *     and can leave the image.
 *   * the RECORD, which used to be most of this file and is now none of it. `actor` is an address
 *     register a caller supplies; nothing between the caller's `movea.l` and the field access bounds
 *     it, and test_behavior.py drives a record at $fffff0 on purpose — so the record is proved ONCE,
 *     by whoever knows its address, and every routine here takes the `ActorRecord` that came of it
 *     (include/actor_view.h). Each keeps its published `(image, actor, ...)` name as a DOOR that
 *     opens the view for a caller who has none; src/behavior.c's handlers already hold the record
 *     their own door proved and call the `_body` half directly, which is what makes this phase two
 *     of that change rather than a second copy of it.
 * Musashi puts either on a 24-BIT bus, and off the image the shim answers zero for every address
 * but the SEVEN hardware ones bus.h enumerates — so `bus_read_byte` is the oracle's answer on that
 * set and not on the modeled one, which bus.h states at its own width rather than being summarised
 * here. An unguarded index into the buffer is neither: it reads the host heap, agreeing with the
 * oracle only by luck and taking the process down when the page is not mapped. Batch 43 phase C
 * measured it — the whole 6,138-case suite run on an image with PROT_NONE either side crashed in
 * three cases, in `actor_step_right_against_map` here (the record) and in `scene_run_frame` in
 * src/scene.c (a descriptor), and nowhere else.
 *
 * ON TARGET IT IS A MODELLING DECISION AND NOT A NO-OP. A real ST answers an address outside the
 * game's 1 MB with real RAM, or with the $ff8000 I/O page where the shim has a model and this has
 * none — so a computed read there returns 0 and a computed write is dropped where the machine would
 * do neither. No on-target surface would show it; ../STATUS.md records that unpinned rather than
 * claiming otherwise.
 */
#include <stdint.h>

#include "actor.h"          /* $1492's not-found arm IS actor_accelerate_fall — see below */
#include "actor_view.h"      /* the record its caller proved: every FIELD access below goes here */
#include "bus.h"            /* every CELL — a computed address — is still addressed through this */
#include "machine.h"
#include "map.h"
#include "wonderboy.h"

/* WB_STATE_FLAG_A32 as the probes read it: a `beq` over the A32 arm, so this is the NONZERO reading
 * `followed_actor_record` uses and not the sign test `project_actor_list` uses on the same word.
 * $1170 tests the same word a SECOND time for its clamp ($118c and $11b6), and nothing between the
 * two writes it, so both tests here are this one predicate. */
static int state_flag_a32(const uint8_t *image) {
    return be16(image + WB_STATE_FLAG_A32) != 0;
}

/* Which map that flag names. */
static uint32_t collision_map(const uint8_t *image) {
    return state_flag_a32(image) ? WB_COLLISION_MAP_A32 : WB_COLLISION_MAP_DEFAULT;
}

/* The cell at (column, row) of `map`, plus the whole register the original leaves the arithmetic in
 * — d1 in $10a2, d3 in $13c8. Both routines hand that register on as well as the pointer, so it is
 * an output here rather than a local: the `mulu.w` product's HIGH half over the cell index. */
static uint32_t cell_pointer(const uint8_t *image, uint32_t map, uint16_t column, uint16_t row,
                             uint32_t *cell_index, unsigned *extend) {
    uint32_t product = (uint32_t)be16(image + map) * row;       /* `mulu.w` — the WHOLE 32 bits */
    uint16_t index = (uint16_t)(product + column);              /* `add.w` — the low word only */

    /* `mulu.w` leaves X alone, so the `add.w` at $10da/$11a8 is this block's one X-writer — and on
     * the left probe's edge arm it is the LAST one the routine runs, so the tail inherits it. NULL
     * from $13c8, which has no consumer for the flag. */
    if (extend != NULL)
        *extend = word_add_extend((uint16_t)product, column);
    *cell_index = set_low_word(product, index);
    return addr_add(map, WB_COLLISION_MAP_CELLS + sign_ext16(index));
}

/* One pixel coordinate into the cell it falls in: `asr.w #4`, an ARITHMETIC shift, so a position
 * left of the map's origin names a negative column rather than a huge positive one. */
static uint16_t pixel_to_cell(uint16_t pixels) {
    return (uint16_t)((int16_t)pixels >> WB_MAP_CELL_SHIFT);
}

/* The row BOTH probes take their cell from: `move.w 2(a0),d1 / subq.w #1,d1 / asr.w #4,d1`. The
 * pixel above the actor's y, so a record standing exactly on a cell boundary probes the row it is
 * standing in rather than the one below it. */
static uint16_t actor_probe_row(ActorRecord record) {
    return pixel_to_cell((uint16_t)(rec_w(record, WB_ACTOR_Y) - 1));
}

/* The three tests the shared tail runs on the cells above and below the one a probe stopped at.
 * `offset` is the original's d7, used as a sign-extended word index off the cell pointer. */
static int cell_is(const uint8_t *image, uint32_t cell, uint16_t offset, uint8_t tile) {
    return bus_read_byte(image, addr_add(cell, sign_ext16(offset))) == tile;
}

/* $111a — the ground test both probes end in, and the d1 they both hand back: the
 * WB_MAP_GROUND_*_BIT set over the row product's high half, which `clr.w d1` leaves alone.
 *
 * ONE spelling because it is one piece of code — see this file's header for the three branches that
 * reach it. The stride it steps by is WB_COLLISION_MAP_DEFAULT's whichever map the cell came out
 * of, which is why it takes the cell as an address rather than as a (map, index) pair.
 *
 * AND IT IS WHERE THE PROBES' EXIT X IS DECIDED, one value per arm, because this tail holds the
 * last arithmetic either routine runs. `*extend` is IN AND OUT for that reason — the middle arm
 * writes no X at all and hands the caller's own bit straight back out, which is the only path on
 * which anything the probe BODY computed survives (include/map.h). Everything else here —
 * `move.w`, `clr.w`, `cmpi.b`, `ori.w`, `rts` — leaves X alone.
 *
 * IT IS THE ONE X POINTER IN THIS FILE THAT IS MANDATORY, and deliberately: `cell_pointer` and the
 * two public probes take a NULL for a caller that does not model the flag, but a tail that is
 * in-and-out has no meaning without one, and its three callers are the two probes' own exits. A
 * NULL guard here would be a branch no case could drive. */
static uint32_t map_ground_under_cell(const uint8_t *image, uint32_t cell, uint32_t cell_index,
                                      unsigned *extend) {
    uint16_t stride = be16(image + WB_COLLISION_MAP_DEFAULT);
    uint16_t flags;

    if (bus_read_byte(image, cell) == WB_MAP_TILE_BLOCK) {
        /* `neg.w d7`: the cell is a block, so the question is whether the one ABOVE it is too. And
         * NEG sets X the way `0 - d7` would, i.e. on every stride but a zero one. */
        uint16_t above = (uint16_t)-stride;
        *extend = word_sub_extend(0, stride);
        flags = cell_is(image, cell, above, WB_MAP_TILE_BLOCK) ? 0 : WB_MAP_GROUND_HEAD_BIT;
    } else if (cell_is(image, cell, stride, WB_MAP_TILE_BLOCK)
               || cell_is(image, cell, stride, WB_MAP_TILE_LEDGE)) {
        /* The two `cmpi.b`/`beq` pairs at $113c and $1146 are this arm's whole body, so `*extend`
         * is left holding what the probe's own last arithmetic put there. */
        flags = 0;
    } else {
        uint16_t two_rows = (uint16_t)(stride + stride);        /* `add.w d7,d7` */
        *extend = word_add_extend(stride, stride);
        flags = WB_MAP_GROUND_NEAR_BIT;
        if (!cell_is(image, cell, two_rows, WB_MAP_TILE_BLOCK)
            && !cell_is(image, cell, two_rows, WB_MAP_TILE_LEDGE))
            flags |= WB_MAP_GROUND_FAR_BIT;
    }
    return set_low_word(cell_index, flags);
}

/* $1116 `sub.w d7,(a0)` and $1200 `add.w d7,(a0)` — the move each probe commits on its non-edge
 * exits, and the tail's entry X on those paths: the WORD borrow or carry out of the record's own x.
 * The left probe reaches its one from two places, which is why this is a function; the right one is
 * here beside it because a named commit and an anonymous inlined twin would read as two different
 * instructions rather than as the mirror pair they are. */
static void step_left_commit(ActorRecord record, uint16_t remaining, unsigned *extend) {
    uint16_t x = (uint16_t)rec_w(record, WB_ACTOR_X);

    rec_set_w(record, WB_ACTOR_X, (uint16_t)(x - remaining));
    *extend = word_sub_extend(x, remaining);
}

static void step_right_commit(ActorRecord record, uint16_t remaining, unsigned *extend) {
    uint16_t x = (uint16_t)rec_w(record, WB_ACTOR_X);

    rec_set_w(record, WB_ACTOR_X, (uint16_t)(x + remaining));
    *extend = word_add_extend(x, remaining);
}

/* What both probes do on the way out, at all three of their exits: run the shared tail on the cell
 * they stopped at, and publish the X it leaves to a caller that asked for one. */
static void probe_report(const uint8_t *image, uint32_t cell, uint32_t cell_index,
                         unsigned *extend, uint32_t *ground, unsigned *exit_extend) {
    *ground = map_ground_under_cell(image, cell, cell_index, extend);
    if (exit_extend != NULL)
        *exit_extend = *extend;
}

uint32_t actor_step_left_against_map_body(uint8_t *image, ActorRecord record, uint32_t step,
                                          uint32_t *ground, unsigned *exit_extend) {
    uint16_t remaining = (uint16_t)step;                /* d7 */
    uint8_t outcome = WB_MAP_STEP_CLEAR;                /* d6 */
    uint32_t cell;                                      /* a6 */
    uint32_t cell_index;                                /* d1, before its low word is cleared */
    uint16_t column;                                    /* d0's low word at the moment it is read */
    /* The modelled X. It is written before it is ever read — `cell_pointer`'s `add.w` runs on every
     * turn of the loop — and only the LAST write before an exit can matter, so the five X-writers
     * above that `add.w` ($10ac, $10b0, $10b4, $10ba, $10bc) are not modelled: each is overwritten
     * inside its own iteration. Same for the `subq.w #1,d7` at $10fa, which is followed by $1116 on
     * one arm and by the loop's own head on the other. */
    unsigned extend = 0;

    for (;;) {
        uint16_t probe = (uint16_t)(rec_w(record, WB_ACTOR_X)
                                    - rec_w(record, WB_ACTOR_HALF_WIDTH)
                                    - remaining);       /* d3, kept for its SIGN */
        column = pixel_to_cell(probe);
        cell = cell_pointer(image, collision_map(image), column, actor_probe_row(record),
                            &cell_index, &extend);

        if (bus_read_byte(image, cell) != WB_MAP_TILE_BLOCK) {
            /* `tst.w d3 / bpl` — the wrapped probe's own sign bit, not a comparison. */
            if ((int16_t)probe >= 0) {
                step_left_commit(record, remaining, &extend);
                break;
            }
            /* Off the map's left edge: park the actor against it, and report blocked. `move.w
             * 14(a0),(a0)` and the `move.b #$0,d0` below it write no X, so this is the one exit
             * that carries `cell_pointer`'s `add.w` into the tail. */
            rec_set_w(record, WB_ACTOR_X, (uint16_t)rec_w(record, WB_ACTOR_HALF_WIDTH));
            outcome = WB_MAP_STEP_BLOCKED;
            break;
        }

        outcome = WB_MAP_STEP_BLOCKED;
        /* One pixel less of step and try again — and on an EXACT zero the routine still commits the
         * (now zero) move, so the x word is written on every path out of this loop. */
        if (--remaining == 0) {
            step_left_commit(record, remaining, &extend);
            break;
        }
        if ((uint16_t)rec_w(record, WB_ACTOR_TYPE) == WB_ACTOR_TYPE_PLAYER)
            rec_set_b(record, WB_ACTOR_FIELD_22, 0);
    }

    /* `move.b d6,d0` replaces only the low byte of a d0 whose low word still holds the column. */
    probe_report(image, cell, cell_index, &extend, ground, exit_extend);
    return set_low_byte(column, outcome);
}

/* $1170 — the same walk the other way, and NOT a parametrisation of it. Its head flips both signs
 * (`add.w 14(a0),d0 / add.w d7,d0`), and where $10a2 tests the probe's own sign and parks the actor
 * at its half-width, this one compares the UNSHIFTED probe against a limit it reads out of memory
 * and parks the actor's right EDGE on it. Only the ground test above is shared.
 *
 * THE TWO EXITS LEAVE DIFFERENT THINGS IN d0's LOW WORD, and both are results:
 *   * $1200 (`move.b d6,d0`) — the outcome byte over the probe's own map column when the walk ran
 *     its step down to zero, and over the CLAMP LIMIT when the compare sent it here.
 *   * $11f8 (`move.b #$0,d0`) — a LITERAL zero over the x the routine just parked, so a first probe
 *     that was clear still comes back WB_MAP_STEP_BLOCKED when it was past the limit.
 * Of the forty-one callers, eleven read the outcome BYTE (`tst.b d0`), three read the whole low
 * word — $41ae, $4cf4 and $4e98, which is what makes the high byte a result and not a leftover —
 * and the remaining twenty-seven overwrite d0 without reading it. None reads d1. */
uint32_t actor_step_right_against_map_body(uint8_t *image, ActorRecord record, uint32_t step,
                                           uint32_t *ground, unsigned *exit_extend) {
    uint16_t remaining = (uint16_t)step;                /* d7 */
    uint8_t outcome = WB_MAP_STEP_CLEAR;                /* d6 */
    uint32_t cell;                                      /* a6 */
    uint32_t cell_index;                                /* d1, before its low word is cleared */
    uint16_t reported;                                  /* d0's low word under the outcome byte */
    /* The modelled X — see $10a2 above. This head has ONE X-writer that routine does not, the
     * `addi.w #$f0,d0` at $11ca, and it is left out for the same reason as the five above $11a8:
     * both arms below it write X again before the tail ($11d4's `sub.w` on the clamp, $1200's
     * `add.w` on the commit), so its carry reaches no exit. */
    unsigned extend = 0;

    for (;;) {
        uint16_t probe = (uint16_t)(rec_w(record, WB_ACTOR_X)
                                    + rec_w(record, WB_ACTOR_HALF_WIDTH)
                                    + remaining);       /* d3, kept UNSHIFTED for the compare */
        reported = pixel_to_cell(probe);
        cell = cell_pointer(image, collision_map(image), reported, actor_probe_row(record),
                            &cell_index, &extend);

        if (bus_read_byte(image, cell) != WB_MAP_TILE_BLOCK) {
            /* Where the actor's right edge stops. In the A32 mode there is no limit word at all
             * (`clr.w d0`), so the edge stops at the bias alone; otherwise the level's own right
             * edge, WB_BG_SCROLL_LIMIT_X being that number less one WB_BG_SCROLL_LIMIT_BIAS. */
            reported = (uint16_t)((state_flag_a32(image) ? 0 : be16(image + WB_BG_SCROLL_LIMIT_X))
                                  + WB_BG_SCROLL_LIMIT_BIAS);
            /* `cmp.w d3,d0 / bge` — a SIGNED comparison of the two operands, so a probe that
             * wrapped past $7fff reads as behind the limit rather than beyond it. */
            if ((int16_t)reported >= (int16_t)probe)
                break;
            /* Past it: park x so the actor's right edge sits ON the limit, and report blocked
             * whatever the walk had decided. `sub.w 14(a0),d0` at $11d4 is this arm's last
             * arithmetic — the `move.w d0,(a0)` and `move.b #$0,d0` under it write no X. */
            {
                uint16_t half_width = (uint16_t)rec_w(record, WB_ACTOR_HALF_WIDTH);

                extend = word_sub_extend(reported, half_width);
                reported = (uint16_t)(reported - half_width);
            }
            rec_set_w(record, WB_ACTOR_X, reported);
            probe_report(image, cell, cell_index, &extend, ground, exit_extend);
            return set_low_byte(reported, WB_MAP_STEP_BLOCKED);
        }

        outcome = WB_MAP_STEP_BLOCKED;
        /* One pixel less of step and try again — and on an EXACT zero the routine still commits the
         * (now zero) move, so the x word is written on every path out of this loop. */
        if (--remaining == 0)
            break;
        if ((uint16_t)rec_w(record, WB_ACTOR_TYPE) == WB_ACTOR_TYPE_PLAYER)
            rec_set_b(record, WB_ACTOR_FIELD_22, 0);
    }

    /* `add.w d7,(a0)` at $1200 — the other exits' last arithmetic, and the tail's entry X on both
     * of them (the `move.b d6,d0` below it writes no flag). */
    step_right_commit(record, remaining, &extend);
    probe_report(image, cell, cell_index, &extend, ground, exit_extend);
    return set_low_byte(reported, outcome);
}

/* $13c8 — the block above as the routine the game calls, and NOTHING else: it stores nothing, and
 * every one of its results is a register `probe` names. See include/map.h for the register map and
 * for which fields it reads on the way in.
 *
 * Every write it makes is a WORD write into a longword register (`move.w`, `andi.w`, `asr.w`,
 * `add.w`), so each field's entry HIGH half survives into the result — `set_low_word` is that. The
 * two exceptions are the two pure outputs: `cell`, which a `lea` replaces outright, and
 * `cell_index`, whose `mulu.w` writes all 32 bits over whatever the caller had there. */
static void actor_map_cell_lookup_body(const uint8_t *image, ActorRecord record,
                                       map_cell_probe *probe) {
    uint16_t pixel_x = (uint16_t)probe->column;         /* d0's low word — the one value read in */

    /* `move.w d0,d2 / andi.w #$f,d2` runs BEFORE the shift, so the sub-cell is the position within
     * a cell of the pixel column the caller handed over. */
    probe->sub_cell = set_low_word(probe->sub_cell, pixel_x & WB_MAP_CELL_MASK);
    probe->column = set_low_word(probe->column, pixel_to_cell(pixel_x));
    probe->row = set_low_word(probe->row,
                              pixel_to_cell((uint16_t)rec_w(record, WB_ACTOR_Y)));
    /* NULL for the X: this routine's interface is the `map_cell_probe` registers, and no caller of
     * $13c8 reads the flag its `add.w` leaves. */
    probe->cell = cell_pointer(image, collision_map(image), (uint16_t)probe->column,
                               (uint16_t)probe->row, &probe->cell_index, NULL);
    /* `move.w 14(a0),d7 / add.w d7,d7` — the footprint's whole width, as a word. */
    probe->span = set_low_word(probe->span,
                               (uint16_t)(2u * (uint16_t)rec_w(record, WB_ACTOR_HALF_WIDTH)));
}

static void actor_map_cell_from_actor_x_body(const uint8_t *image, ActorRecord record,
                                             map_cell_probe *probe) {
    /* `moveq #$0,d0 / move.l d0,d1` clear both as LONGS, which is why no caller entering here ever
     * sees the surviving high halves a standalone $13c8 hands back in d0 and d1. */
    probe->column = (uint16_t)(rec_w(record, WB_ACTOR_X) - rec_w(record, WB_ACTOR_HALF_WIDTH));
    probe->row = 0;

    actor_map_cell_lookup_body(image, record, probe);
}

/* The seven instructions BOTH settles spell to decide whether the footprint reaches ONE cell
 * further than the scan walked: `moveq #$0,d0 / move.w d7,d0 / asr.w #1,d0 / neg.w d0 /
 * andi.w #$f,d0 / cmp.w d0,d2 / blt`. The actor's own position within its cell (d2) has to be at
 * least as far in as what is left of the span puts it.
 *
 * ONE spelling because it is the same seven instructions in both bodies. The SCANS above it are
 * NOT shared: $1400 tests one tile code at each of its three sites and $1492 tests a PAIR, which is
 * a different shape rather than a different constant, and a walk taking a predicate would be an
 * abstraction neither original has. */
static int footprint_reaches_next_cell(uint32_t subcell, uint16_t remaining) {
    uint16_t edge = (uint16_t)(-(int16_t)((int16_t)remaining >> 1)) & WB_MAP_CELL_MASK;

    return (int16_t)(uint16_t)subcell >= (int16_t)edge;
}

/* `bclr #4,8(a0)` then `bclr #1,8(a0)` — TWO byte read-modify-writes over the same flags byte, and
 * BOTH settle arms spell exactly that pair ($1480/$1486 and $1502/$1508). Written as two calls
 * because that is what the instructions are: an earlier draft of this helper collapsed them into one
 * masked store, which no surface here can see today but is not what the original does. What
 * separates the two arms is WB_ACTOR_FLAGS2, which only $1400 touches. */
static void clear_falling_and_launched(ActorRecord record) {
    rec_flag_clear(record, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FALLING_BIT);
    rec_flag_clear(record, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_LAUNCHED_BIT);
}

/* `always_inline` because `actor_fall_and_settle_body` is its one hot caller and the call is SIX
 * arguments — the image, both halves of the record, the cell, the span and the sub-cell — pushed and
 * torn down once per fall, six falls a frame. GCC declines it at -O3 on its own (it takes the sibling
 * settle and both cell lookups and leaves this one out of line), and forcing it is MEASURED, not
 * assumed: one profile run each way on the same tree, buying frame cycles for bytes of this file's
 * object. ../STATUS.md, "## Performance", carries both figures — one place, so they cannot drift
 * apart from the run that produced them. */
static inline __attribute__((always_inline))
uint32_t actor_settle_on_platform_body(uint8_t *image, ActorRecord record, uint32_t cell,
                                       uint32_t span, uint32_t subcell) {
    uint32_t cursor = cell;                             /* a6 */
    uint16_t remaining = (uint16_t)span;                /* d7 */
    int on_platform;

    /* Walk the footprint a whole cell at a time. `cmpi.w #$10,d7 / blt` is a SIGNED comparison of
     * the operand, so a negative span never enters the loop at all. */
    while (bus_read_byte(image, cursor) != WB_MAP_TILE_PLATFORM
           && (int16_t)remaining >= (int16_t)WB_MAP_CELL_PIXELS) {
        cursor = addr_add(cursor, 1);
        remaining = (uint16_t)(remaining - WB_MAP_CELL_PIXELS);
    }
    on_platform = bus_read_byte(image, cursor) == WB_MAP_TILE_PLATFORM;

    if (!on_platform && footprint_reaches_next_cell(subcell, remaining)) {
        cursor = addr_add(cursor, 1);
        on_platform = bus_read_byte(image, cursor) == WB_MAP_TILE_PLATFORM;
    }

    if (on_platform) {
        int16_t actor_y = rec_w(record, WB_ACTOR_Y);
        int16_t top = (int16_t)(be16(image + WB_PLATFORM_Y) - WB_PLATFORM_Y_ABOVE);

        /* `cmp.w d1,d0 / bgt` then `addq.w #6,d0 / cmp.w 2(a0),d0 / blt`: the actor lands only from
         * inside the band [top, top + WB_PLATFORM_Y_BAND], both ends signed comparisons of the
         * operands rather than of a difference. */
        if (!(top > actor_y) && !((int16_t)(top + WB_PLATFORM_Y_BAND) < actor_y)) {
            rec_set_w(record, WB_ACTOR_Y,
                      (uint16_t)(be16(image + WB_PLATFORM_Y) - WB_PLATFORM_STAND_OFFSET));
            rec_flag_set(record, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT);
            rec_flag_set(record, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_LANDED_BIT);
            clear_falling_and_launched(record);
            rec_set_b(record, WB_ACTOR_SPEED, 0);
            return set_low_word(span, remaining);
        }
    }

    /* Nothing to stand on. A record that is still marked supported is left alone — only one that
     * has already lost its footing starts falling. */
    if (!rec_flag_is_set(record, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT))
        rec_flag_set(record, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_FALLING_BIT);
    rec_flag_clear(record, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_LANDED_BIT);
    return set_low_word(span, remaining);
}

/* The pair of tile codes $1492 accepts, spelled at all three of its test sites as
 * `cmpi.b #$1,(a6) / beq` followed by `cmpi.b #$2,(a6) / beq` — the same two codes the ground test
 * in the probes' tail accepts, and the reason this routine is not $1400 with a tile argument. */
static int cell_is_ground(const uint8_t *image, uint32_t cell) {
    /* Two reads because the original is two `cmpi.b`s over the same (a6). Nothing writes between
     * them and no surface here can tell one read from two, so this is transcription and not a pin. */
    return bus_read_byte(image, cell) == WB_MAP_TILE_BLOCK
           || bus_read_byte(image, cell) == WB_MAP_TILE_LEDGE;
}

static uint32_t actor_settle_on_tile_1_or_2_body(uint8_t *image, ActorRecord record, uint32_t cell,
                                                uint32_t span, uint32_t subcell) {
    uint32_t cursor = cell;                             /* a6 */
    uint16_t remaining = (uint16_t)span;                /* d7 */
    int on_ground;

    while (!cell_is_ground(image, cursor)
           && (int16_t)remaining >= (int16_t)WB_MAP_CELL_PIXELS) {
        cursor = addr_add(cursor, 1);
        remaining = (uint16_t)(remaining - WB_MAP_CELL_PIXELS);
    }
    on_ground = cell_is_ground(image, cursor);

    if (!on_ground && footprint_reaches_next_cell(subcell, remaining)) {
        cursor = addr_add(cursor, 1);
        on_ground = cell_is_ground(image, cursor);
    }

    /* Nothing underfoot: the arm is the WHOLE of actor_accelerate_fall, whose 32 bytes sit inside
     * this routine's own span and whose `rts` is this routine's other exit. */
    if (!on_ground) {
        actor_accelerate_fall_body(record);
        return set_low_word(span, remaining);
    }

    /* `andi.w #$fff0,2(a0)`: parked on the top of whichever cell the record is in — its own y
     * masked, and not a platform word read out of memory as $1400's landing arm does. Nothing
     * here touches WB_ACTOR_FLAGS2, which is the other half of what separates the two arms. */
    rec_set_w(record, WB_ACTOR_Y,
              (uint16_t)(rec_w(record, WB_ACTOR_Y) & (uint16_t)~WB_MAP_CELL_MASK));
    rec_flag_set(record, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SUPPORTED_BIT);
    clear_falling_and_launched(record);
    rec_set_b(record, WB_ACTOR_SPEED, 0);
    return set_low_word(span, remaining);
}

/* $1334's player-only head: raise or clear the three WB_TILE_33_* words from the cell under the
 * record's own x, and report whether the pass below it should run at all. */
static int tile_33_head_lets_the_fall_run(uint8_t *image, ActorRecord record,
                                          map_cell_probe *probe) {
    /* `moveq #$0,d0 / move.l d0,d1 / move.w (a0),d0` — the record's OWN x with no half-width taken
     * off it, which is why this is the one site in the image entering $13c8 rather than $13be. */
    probe->column = (uint16_t)rec_w(record, WB_ACTOR_X);
    probe->row = 0;
    actor_map_cell_lookup_body(image, record, probe);

    if (bus_read_byte(image, probe->cell) == WB_MAP_TILE_33) {
        wr16(image + WB_TILE_33_FLAG, WB_TILE_33_FLAG_RAISED);
        return be16(image + WB_TILE_33_MODE) == 0;      /* `tst.w / beq` over the `rts` at $1362 */
    }

    wr16(image + WB_TILE_33_MODE, 0);
    wr16(image + WB_TILE_33_STEP, 0);
    wr16(image + WB_TILE_33_FLAG, 0);
    return 1;
}

uint32_t actor_fall_and_settle_body(uint8_t *image, ActorRecord record, uint32_t entry_span) {
    /* The probe's four other REGISTER fields come in as whatever the caller left in d2/d3 and are
     * overwritten before anything reads them, so zeroing them here changes no memory the routine
     * writes — only registers it does not own (test/test_map.py states those against the oracle).
     * `span` IS seeded, because it is d7 and this routine now hands d7 back: the settles write only
     * its low word, so the caller's high half survives all the way out. */
    map_cell_probe probe = {0};
    uint16_t speed;                                     /* d1: a byte zero-extended into a long */
    uint16_t y;                                         /* d0 */

    probe.span = entry_span;

    /* Both early exits hand back `probe.span` and not `entry_span`, because the PLAYER-ONLY head
     * has its own `bsr $13c8` and that lookup ends `move.w 14(a0),d7 / add.w d7,d7`. So a record
     * that leaves through either `rts` still carries the footprint width when the head ran. */
    if ((uint16_t)rec_w(record, WB_ACTOR_TYPE) == WB_ACTOR_TYPE_PLAYER
        && !tile_33_head_lets_the_fall_run(image, record, &probe))
        return probe.span;

    /* `btst #0,8(a0) / beq` over an `rts`: a record under actor_start_motion_at_speed's own
     * control is left alone entirely — this is bit 0's one reader in the tier. */
    if (rec_flag_is_set(record, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_MOVING_BIT))
        return probe.span;

    speed = rec_b(record, WB_ACTOR_SPEED);
    y = (uint16_t)(rec_w(record, WB_ACTOR_Y) + speed);
    rec_set_w(record, WB_ACTOR_Y, y);

    /* `btst #1,9(a0) / bne` then `andi.w #$f,d0 / cmp.w d1,d0 / ble`: the ground scan runs when the
     * record is already landed, or when this frame's step carried it into a new cell — the new y's
     * position within its cell being no further in than the step that produced it. The comparison
     * is signed, but neither operand can reach the sign bit: d0 is masked to a nibble and d1 is a
     * byte over a `moveq`-cleared long. */
    if (rec_flag_is_set(record, WB_ACTOR_FLAGS2, WB_ACTOR_FLAGS2_LANDED_BIT)
        || (int16_t)(y & WB_MAP_CELL_MASK) <= (int16_t)speed) {
        actor_map_cell_from_actor_x_body(image, record, &probe);
        actor_settle_on_tile_1_or_2_body(image, record, probe.cell, probe.span, probe.sub_cell);
    } else {
        actor_accelerate_fall_body(record);
    }

    /* Looked up AGAIN rather than reused, and this is why $13be is called twice: $1492's scan
     * CONSUMES a6 and d7 — it walks the cursor along and counts the span down — so handing $1400
     * what $1492 left would start it partway through the footprint with a span of nothing. */
    actor_map_cell_from_actor_x_body(image, record, &probe);
    return actor_settle_on_platform_body(image, record, probe.cell, probe.span, probe.sub_cell);
}

/* --- THE DOORS -------------------------------------------------------------------------------
 *
 * Everything above takes the `ActorRecord` its caller proved. These seven are the published names —
 * what include/map.h declares, what test_map.py binds through ctypes, and what a caller holding only
 * the record's ADDRESS calls — and each is the same routine entered through a door that proves the
 * record once. src/behavior.c's handlers do NOT come through here: they already hold the record
 * their own door proved and call the `_body` half, because two doors on one record would be two
 * scratches (include/actor_view.h). */
ACTOR_DOOR_RETURNING_SIG(uint32_t, actor_step_left_against_map,
                         (uint8_t *image, uint32_t actor, uint32_t step, uint32_t *ground,
                          unsigned *exit_extend),
                         (image, record, step, ground, exit_extend))

ACTOR_DOOR_RETURNING_SIG(uint32_t, actor_step_right_against_map,
                         (uint8_t *image, uint32_t actor, uint32_t step, uint32_t *ground,
                          unsigned *exit_extend),
                         (image, record, step, ground, exit_extend))

ACTOR_DOOR_READING_VOID_SIG(actor_map_cell_lookup,
                            (const uint8_t *image, uint32_t actor, map_cell_probe *probe),
                            (image, record, probe))

ACTOR_DOOR_READING_VOID_SIG(actor_map_cell_from_actor_x,
                            (const uint8_t *image, uint32_t actor, map_cell_probe *probe),
                            (image, record, probe))

ACTOR_DOOR_RETURNING_SIG(uint32_t, actor_settle_on_platform,
                         (uint8_t *image, uint32_t actor, uint32_t cell, uint32_t span,
                          uint32_t subcell),
                         (image, record, cell, span, subcell))

ACTOR_DOOR_RETURNING_SIG(uint32_t, actor_settle_on_tile_1_or_2,
                         (uint8_t *image, uint32_t actor, uint32_t cell, uint32_t span,
                          uint32_t subcell),
                         (image, record, cell, span, subcell))

ACTOR_DOOR_RETURNING_SIG(uint32_t, actor_fall_and_settle,
                         (uint8_t *image, uint32_t actor, uint32_t entry_span),
                         (image, record, entry_span))

void map_stamp_block(uint8_t *image) {
    uint32_t record = be32(image + WB_RECORD_PTR_10420);
    uint16_t cell = (uint16_t)(bus_read_word(image, addr_add(record, WB_RECORD_10420_CELL))
                               + WB_STAMP_CELL_BIAS);
    /* The base is WB_MAP_ROW_STRIDE's own address — the stride word — and the bias above is what
     * carries the cursor past it onto cell 0, exactly as WB_COLLISION_MAP_CELLS does. */
    uint32_t at = addr_add(WB_MAP_ROW_STRIDE, sign_ext16(cell));
    /* The tile-set select reads the descriptor's KIND word: the second set is the one a boss-defeat
     * scene stamps. src/scene.c branches on the same word — see WB_SCENE_KIND. */
    uint8_t tile = bus_read_word(image, addr_add(record, WB_SCENE_KIND)) == WB_SCENE_KIND_BOSS_DEFEAT
                   ? WB_STAMP_TILES_SECOND : WB_STAMP_TILES_FIRST;

    bus_write_byte(image, at, tile);
    bus_write_byte(image, addr_add(at, 1), (uint8_t)(tile + 1));
    at = addr_add(at, sign_ext16(be16(image + WB_MAP_ROW_STRIDE)));      /* `adda.w`, sign-extended */
    bus_write_byte(image, at, (uint8_t)(tile + 2));
    bus_write_byte(image, addr_add(at, 1), (uint8_t)(tile + 3));
}
