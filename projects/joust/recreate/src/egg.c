/* egg.c — Joust's egg subsystem: update_eggs @ 0x12606, update_egg_draw @ 0x1285c and
 * update_egg_physics @ 0x12a2a.
 *
 * THE THREE ARE ONE ROUTINE, and the reconstruction has to be written that way because the original
 * links them with jumps that cross function boundaries in both directions:
 *
 *   * update_eggs walks object_table; the slot advance at 0x12612 is the loop's only exit;
 *   * seven of its branches leave by jumping FORWARD into update_egg_draw — three at its head
 *     (0x1285c) and four at its erase/draw/commit tail (0x128c0) — and the animation jump table
 *     adds the two-instruction stub at 0x12854, which only draws. update_egg_draw itself ends
 *     `jmp 0x12612`, i.e. straight back into that loop advance;
 *   * update_eggs calls update_egg_physics with `bsr`, and the platform-edge branch ends
 *     `adda.w #$4,a7 ; bra.w 0x1285c` — it THROWS AWAY its own return address and tail-jumps into
 *     update_egg_draw, which then returns to the loop advance on its behalf.
 *
 * So there is exactly one `rts` in the whole subsystem (0x1261e, the loop running out of slots), and
 * A7 balances because the discarded return address is the `bsr`'s own. Entering the original at
 * update_egg_physics or update_egg_draw therefore runs the REST OF THE OBJECT LOOP before it comes
 * back — which is what the two `g_update_egg_*` glues below reproduce, and what their differential
 * tests actually compare.
 *
 * In C the three jump targets become an exit code (`enum egg_slot_exit`) that update_eggs_from acts
 * on, and update_egg_physics reports its tail jump the same way. Nothing here needs a machine stack.
 *
 * The egg sub-record lives at object + 0x1e..0x34; a slot whose OBJ_EGG_STATE is 0 carries no egg.
 * States above EGG_STATE_READY are in flight (physics + gravity), EGG_STATE_LAVA is the death fall,
 * and everything below is an animation frame dispatched through the egg_sprite_ptrs jump table.
 */
#include "machine.h"
#include "addrs.h"
#include "joust.h"
#include "object.h"   /* the platform tables, the two egg blits, test_overlap, EGG_STATE_LAVA */
#include "egg.h"

/* Where a slot's processing ends. The three non-trivial values are the three addresses the original
 * jumps to; the loop advance at 0x12612 is EGG_SLOT_NEXT. */
enum egg_slot_exit {
    EGG_SLOT_NEXT,        /* -> 0x12612: on to the next object */
    EGG_SLOT_DRAW,        /* -> 0x1285c: update_egg_draw's head, which re-derives draw_dst */
    EGG_SLOT_REDRAW,      /* -> 0x128c0: its erase / draw / commit tail, draw_dst already set */
    EGG_SLOT_DRAW_ONLY,   /* -> 0x12854: draw the sprite and nothing else */
};

/* Whether update_egg_physics came back through its `rts` or threw its return address away. */
enum egg_physics_exit { EGG_PHYSICS_RETURNED, EGG_PHYSICS_TAIL_JUMPED };

/* The playfield is 320 pixels wide and x wraps around it. */
#define EGG_X_WRAP  0x140u
#define EGG_X_LAST  0x13fu

/* ============================================================ update_egg_physics @ 0x12a2a =====
 *
 * Three passes over the playfield's static description, in order: the landable boxes
 * (platform_table), then the platform bitmaps as a pixel-collision surface (platform_sprites), then
 * — only if a bitmap was hit — the bump boxes at the platforms' ends (platform_edge_table).
 */

#define EGG_LANDING_Y_BIAS      0xcu  /* `sub.w #$c`: the landing probe sits 12 rows above egg_y */
#define EGG_REST_Y_OFFSET       0xcu  /* and the egg is then drawn 12 rows below the platform top */
#define EGG_EDGE_Y_BIAS         7u    /* `subq.w #7`: the bump probe sits 7 rows above egg_y */
#define EGG_EDGE_REST_ABOVE     5u    /* snapped onto an edge box, the egg draws 5 rows below its top */
#define EGG_EDGE_Y_STEP         4u    /* the downward shove a positive EDGE_Y_PUSH applies */
#define EGG_EDGE_X_STEP         4u    /* and the sideways one EDGE_X_PUSH applies */
#define EGG_ROLL_SPEED_MAX      4     /* |OBJ_EGG_DX| never exceeds this while rolling off an edge */
#define EGG_FALL_SPEED_MAX      4     /* nor does OBJ_EGG_DY while falling */
#define EGG_ROLL_TIMER_PERIOD   4u
#define EGG_FALL_TIMER_PERIOD   6u
#define EGG_HIT_BOX_COLS        2u    /* the egg sprite is two cells wide */
#define PLATFORM_NEEDS_REDRAW   1u    /* platform_present: >0 means repaint me (see names.txt) */

/* The one spot on the playfield where a settled egg is nudged left instead of becoming hatchable —
 * presumably because a rider hatching there would be stuck.
 *
 * NOT FULLY PINNED, and the shipped data is why: reaching the test at all needs a platform to have
 * claimed the egg at y == EGG_STUCK_SPOT_Y, and the only such platform (platform_table[3]) starts at
 * x = 0x110. So the differential pins X_MIN only to within [0x10e, 0x110] — moving it to 0x111 is
 * caught, moving it to 0x110 or 0x10f is not. X_MAX and Y are pinned exactly. */
#define EGG_STUCK_SPOT_Y      0x65
#define EGG_STUCK_SPOT_X_MIN  0x10e
#define EGG_STUCK_SPOT_X_MAX  0x118
#define EGG_STUCK_SPOT_NUDGE  0xffffu   /* `move.w #$ffff`: roll one pixel left per frame */

/* Is `probe` inside the {y0,y1,x0,x1} box at `record`? Both platform_table and platform_edge_table
 * open with that box and both are tested with the same four signed word compares, so the shared
 * helper is the original's own shape rather than an invented abstraction. */
static int box_contains(const uint8_t *image, uint32_t record, int16_t probe_y, int16_t probe_x) {
    return probe_y >= (int16_t)be16(image + record + PLAT_Y0)
        && probe_y <= (int16_t)be16(image + record + PLAT_Y1)
        && probe_x >= (int16_t)be16(image + record + PLAT_X0)
        && probe_x <= (int16_t)be16(image + record + PLAT_X1);
}

/* 0x12a68 — the egg has come to rest on `platform`. Stop it, bounce off whatever vertical speed is
 * left, and once it is completely still declare it hatchable. */
static void egg_settle(uint8_t *image, uint32_t object, uint32_t platform, uint32_t present) {
    wr32(image + A_draw_src, A_egg_sprite_still);
    image[object + OBJ_EGG_STATE] = EGG_STATE_RESTING;
    image[present] = PLATFORM_NEEDS_REDRAW;
    /* `move.w (a1),draw_y ; addi.w #$c,draw_y` — folded; the intermediate is never read, and
     * platform_table is static data that cannot alias draw_y. */
    wr16(image + A_draw_y, (uint16_t)(be16(image + platform + PLAT_Y0) + EGG_REST_Y_OFFSET));

    if ((int16_t)be16(image + object + OBJ_EGG_DY) < 0) return;   /* still on the way up */

    /* Roll friction: every EGG_ROLL_TIMER_PERIOD frames the horizontal speed steps one toward 0. */
    if (--image[object + OBJ_EGG_ROLL_TIMER] == 0) {
        image[object + OBJ_EGG_ROLL_TIMER] = EGG_ROLL_TIMER_PERIOD;
        int16_t roll = (int16_t)be16(image + object + OBJ_EGG_DX);
        if (roll > 0) wr16(image + object + OBJ_EGG_DX, (uint16_t)(roll - 1));
        else if (roll < 0) wr16(image + object + OBJ_EGG_DX, (uint16_t)(roll + 1));
    }
    image[object + OBJ_EGG_FALL_TIMER] = EGG_FALL_TIMER_PERIOD;

    /* The bounce: `subq.w #1 ; neg.w`, so a fall of n comes back as -(n - 1) and dies out. */
    int16_t fall = (int16_t)be16(image + object + OBJ_EGG_DY);
    if (fall != 0) {
        fall = (int16_t)(0u - (uint16_t)(fall - 1));
        wr16(image + object + OBJ_EGG_DY, (uint16_t)fall);
        if (fall != 0) return;
    }
    if (be16(image + object + OBJ_EGG_DX) != 0) return;

    if ((int16_t)be16(image + object + OBJ_EGG_Y) == EGG_STUCK_SPOT_Y
        && (int16_t)be16(image + object + OBJ_EGG_X) >= EGG_STUCK_SPOT_X_MIN
        && (int16_t)be16(image + object + OBJ_EGG_X) <= EGG_STUCK_SPOT_X_MAX) {
        wr16(image + object + OBJ_EGG_DX, EGG_STUCK_SPOT_NUDGE);
        return;
    }
    image[object + OBJ_EGG_STATE] = EGG_STATE_READY;
}

/* 0x12a2a — the landing pass. Returns non-zero once a platform has claimed the egg, which ends the
 * whole routine. */
static int egg_lands_on_a_platform(uint8_t *image, uint32_t object) {
    uint32_t present = A_platform_present;
    for (uint32_t platform = A_platform_table; platform != A_platform_table_END;
         platform += PLAT_RECORD, present++) {
        if (image[present] == 0) continue;                      /* absent this wave */
        int16_t probe_y = (int16_t)(be16(image + object + OBJ_EGG_Y) - EGG_LANDING_Y_BIAS);
        if (!box_contains(image, platform, probe_y, (int16_t)be16(image + object + OBJ_EGG_X)))
            continue;
        egg_settle(image, object, platform, present);
        return 1;
    }
    return 0;
}

/* 0x12b18 — the egg, as hit_box_a. Re-staged on every pass of the loop below, as the original does
 * (it reloads A1/A2 at the top of each). */
static void stage_egg_hit_box(uint8_t *image, uint32_t object) {
    wr32(image + A_hit_box_a + HB_DST, be32(image + object + OBJ_EGG_DST));
    wr32(image + A_hit_box_a + HB_SRC, be32(image + object + OBJ_EGG_SRC));
    wr16(image + A_hit_box_a + HB_COLS, EGG_HIT_BOX_COLS);
    image[A_hit_box_a + HB_SHIFT] = image[object + OBJ_EGG_SHIFT];
    image[A_hit_box_a + HB_ROWS] = image[object + OBJ_EGG_ROWS];
    wr16(image + A_hit_box_a + HB_Y, be16(image + object + OBJ_EGG_Y));
}

/* 0x12b4a — one platform bitmap, as hit_box_b. Note the row count: the original walks the record
 * with `(a3)+` and reads a BYTE one past PSPR_ROWS, i.e. the low half of that word. */
static void stage_platform_hit_box(uint8_t *image, uint32_t sprite) {
    uint32_t offset = be32(image + sprite + PSPR_DST_OFF);
    image[A_hit_box_b + HB_ROWS] = image[sprite + PSPR_ROWS + 1];
    wr16(image + A_hit_box_b + HB_COLS, be16(image + sprite + PSPR_COLS));
    wr32(image + A_hit_box_b + HB_SRC, be32(image + sprite + PSPR_SRC));
    image[A_hit_box_b + HB_SHIFT] = 0;
    /* `move.l (a3),dst ; add.l screen_base,dst` — folded; screen_base cannot alias hit_box_b. */
    wr32(image + A_hit_box_b + HB_DST, offset + be32(image + A_screen_base));
    /* divu_w reproduces DIVU.W's overflow case, where the destination is left UNCHANGED — so an
     * offset past 0xa00000 stores its own low word as the scanline instead of a quotient. */
    wr16(image + A_hit_box_b + HB_Y, (uint16_t)divu_w(offset, SCREEN_ROW_BYTES));
}

/* 0x12b06 — the pixel-collision pass over the platform bitmaps. Returns non-zero on the first hit. */
static int egg_hits_a_platform_sprite(uint8_t *image, uint32_t object) {
    for (uint32_t sprite = A_platform_sprites; sprite != A_platform_sprites_END;
         sprite += PSPR_RECORD) {
        stage_egg_hit_box(image, object);          /* staged even when the platform is absent */
        if (image[be32(image + sprite + PSPR_PRESENT)] == 0) continue;
        stage_platform_hit_box(image, sprite);
        test_overlap(image);
        if (image[A_collision_hit] != 0) return 1;
    }
    return 0;
}

/* 0x12bcc — the vertical half of an edge bump. */
static void egg_edge_push_y(uint8_t *image, uint32_t edge) {
    int8_t push = (int8_t)image[edge + EDGE_Y_PUSH];
    if (push == 0) return;
    wr32(image + A_draw_src, A_egg_sprite_still);
    if (push > 0) {
        wr16(image + A_draw_y, (uint16_t)(be16(image + A_draw_y) + EGG_EDGE_Y_STEP));
        return;
    }
    /* Snapped onto the box's top edge (`move.w (a1),draw_y ; addq.w #5` — folded). */
    wr16(image + A_draw_y, (uint16_t)(be16(image + edge + PLAT_Y0) + EGG_EDGE_REST_ABOVE));
}

/* The rolling speed's response to a sideways bump: step it one toward `limit`, but flip its sign
 * first if it was rolling the other way. `subq.w #1 ; neg.w` (and its mirror) is what makes a
 * reversal lose a pixel of speed, which is why the two steps cannot simply be one add. */
static void egg_roll_toward(uint8_t *image, uint32_t object, int step, int limit) {
    int16_t roll = (int16_t)be16(image + object + OBJ_EGG_DX);
    if (roll == 0) return;
    if ((step > 0) == (roll > 0)) {                       /* already rolling that way */
        if (roll == limit) return;
        wr16(image + object + OBJ_EGG_DX, (uint16_t)(roll + step));
        return;
    }
    wr16(image + object + OBJ_EGG_DX, (uint16_t)(0u - (uint16_t)(roll + step)));
}

/* 0x12bfc — the horizontal half of an edge bump: pick the rolling sprite, shove draw_x one step
 * around the playfield's wrap, and spin the egg up in that direction. */
static void egg_edge_push_x(uint8_t *image, uint32_t object, uint32_t edge) {
    int8_t push = (int8_t)image[edge + EDGE_X_PUSH];
    if (push == 0) return;

    if (push > 0) {
        wr32(image + A_draw_src, A_egg_sprite_roll_right);
        int16_t x = (int16_t)(be16(image + object + OBJ_EGG_X) + EGG_EDGE_X_STEP);
        if (x > (int16_t)EGG_X_LAST) x = (int16_t)(x - EGG_X_WRAP);
        wr16(image + A_draw_x, (uint16_t)x);
        egg_roll_toward(image, object, 1, EGG_ROLL_SPEED_MAX);
        return;
    }
    wr32(image + A_draw_src, A_egg_sprite_roll_left);
    /* `subq.w #4 ; bge` tests N==V, i.e. the MATHEMATICAL sign of egg_x - 4, not the sign of the
     * truncated word. Modelled because that is what the instruction does, but UNREACHABLE here and
     * therefore unpinned: the only egg_x values that overflow a `subq.w #4` are 0x8000..0x8003, and
     * the box test above has already required egg_x (signed) >= some edge box's x0, all of which are
     * non-negative. A plain 16-bit subtract would pass the whole battery. */
    int32_t x = (int16_t)be16(image + object + OBJ_EGG_X) - (int32_t)EGG_EDGE_X_STEP;
    if (x < 0) x += EGG_X_WRAP;
    wr16(image + A_draw_x, (uint16_t)x);
    egg_roll_toward(image, object, -1, -EGG_ROLL_SPEED_MAX);
}

/* 0x12b8c — the egg touched a platform bitmap, so find which bump box it is in and push it out.
 * Returns non-zero if a box claimed it, which is the tail-jump exit. */
static int egg_bumps_off_an_edge(uint8_t *image, uint32_t object) {
    image[object + OBJ_EGG_STATE] = EGG_STATE_RESTING;   /* set even if no box matches */
    for (uint32_t edge = A_platform_edge_table; edge != A_platform_edge_table_END;
         edge += EDGE_RECORD) {
        int16_t probe_y = (int16_t)(be16(image + object + OBJ_EGG_Y) - EGG_EDGE_Y_BIAS);
        if (!box_contains(image, edge, probe_y, (int16_t)be16(image + object + OBJ_EGG_X)))
            continue;

        wr16(image + object + OBJ_EGG_DY, 0);
        image[object + OBJ_EGG_FALL_TIMER] = EGG_FALL_TIMER_PERIOD;
        egg_edge_push_y(image, edge);
        egg_edge_push_x(image, object, edge);
        /* `adda.w 10(a1),a2` — the index is added SIGN-EXTENDED; the shipped table holds 0..7. */
        image[A_platform_present + sign_ext16(be16(image + edge + EDGE_PLATFORM))] =
            PLATFORM_NEEDS_REDRAW;
        return 1;
    }
    return 0;
}

/* update_egg_physics(object = A0) @ 0x12a2a.
 *
 * Lands the egg on a platform, or bumps it off a platform's edge, or leaves it falling. The bump
 * path does not return: it discards the caller's return address and tail-jumps into
 * update_egg_draw, which is what EGG_PHYSICS_TAIL_JUMPED reports.
 */
static enum egg_physics_exit update_egg_physics(uint8_t *image, uint32_t object) {
    if (egg_lands_on_a_platform(image, object)) return EGG_PHYSICS_RETURNED;
    if (!egg_hits_a_platform_sprite(image, object)) return EGG_PHYSICS_RETURNED;
    return egg_bumps_off_an_edge(image, object) ? EGG_PHYSICS_TAIL_JUMPED : EGG_PHYSICS_RETURNED;
}

/* ============================================================== update_egg_draw @ 0x1285c ===== */

/* 0x128d4 — draw the staged sprite and record what was drawn, so the next frame's erase can undo
 * exactly this. Every field of the draw scratch is copied into the egg sub-record. */
static void egg_draw_and_record(uint8_t *image, uint32_t object) {
    draw_egg_sprite(image, object);
    wr32(image + object + OBJ_EGG_DST, be32(image + A_draw_dst));
    wr32(image + object + OBJ_EGG_SRC, be32(image + A_draw_src));
    image[object + OBJ_EGG_ROWS] = image[A_draw_rows];
    image[object + OBJ_EGG_SHIFT] = image[A_draw_shift];
    wr16(image + object + OBJ_EGG_X, be16(image + A_draw_x));
    wr16(image + object + OBJ_EGG_Y, be16(image + A_draw_y));
}

/* 0x128c0 — erase the previous sprite, then draw and record the new one. An egg that has never been
 * drawn has nothing to erase; it says so with EGG_SPAWN_UNDRAWN, which is cleared here. */
static void egg_redraw(uint8_t *image, uint32_t object) {
    if (image[object + OBJ_EGG_SPAWN_FLAGS] & EGG_SPAWN_UNDRAWN)
        image[object + OBJ_EGG_SPAWN_FLAGS] ^= EGG_SPAWN_UNDRAWN;   /* bchg */
    else
        erase_egg_sprite(image, object);
    egg_draw_and_record(image, object);
}

/* update_egg_draw(object = A0) @ 0x1285c — turn the pending (draw_x, draw_y) into a screen address
 * and put the egg there.
 *
 * If the address, source, height and shift all match what the record already holds, the sprite is
 * about to be redrawn exactly where it already is, so the erase is skipped altogether (and so is
 * the EGG_SPAWN_UNDRAWN handling, which only the 0x128c0 entry reaches).
 */
static void update_egg_draw(uint8_t *image, uint32_t object) {
    uint16_t shift;
    wr32(image + A_draw_dst, pos_to_screen(image, be16(image + A_draw_x),
                                           be16(image + A_draw_y), &shift));
    image[A_draw_shift] = (uint8_t)shift;   /* `move.w (a7)+,d0 ; move.b d0,draw_shift` */

    if (image[object + OBJ_EGG_SHIFT] == image[A_draw_shift]
        && image[object + OBJ_EGG_ROWS] == image[A_draw_rows]
        && be32(image + object + OBJ_EGG_SRC) == be32(image + A_draw_src)
        && be32(image + object + OBJ_EGG_DST) == be32(image + A_draw_dst)) {
        egg_draw_and_record(image, object);
        return;
    }
    egg_redraw(image, object);
}

/* =================================================================== update_eggs @ 0x12606 ===== */

#define EGG_MAX_LIVE_OBJECTS  8   /* `cmpi.b #$8` on live_object_count — a SIGNED byte compare */

/* Hatch geometry. The rider is launched from whichever side of the screen the egg is nearer, and
 * lands at one of three fixed altitudes chosen from the egg's own height. */
#define HATCH_X_MID          0xa0u   /* `cmpi.w #$a0` + bcc: an UNSIGNED half-screen test */
#define HATCH_X_RIGHT        0x130u
#define HATCH_TARGET_Y_BIAS  0xeu    /* the rider steers to egg_y - 14 */
#define HATCH_Y_LOW_BAND     0x3c    /* egg_y <= this: rise to HATCH_Y_TOP */
#define HATCH_Y_MID_BAND     0x96    /* egg_y <= this: HATCH_Y_MID, unless it is also >= ... */
#define HATCH_Y_MID_HIGH     0x6e    /* ... this, which sends it to HATCH_Y_TOP after all */
#define HATCH_Y_TOP          0xau
#define HATCH_Y_MID          0x32u
#define HATCH_Y_BOTTOM       0x78u
#define HATCH_WALK_ANIM      3u      /* the walk timers the new rider starts with */
#define HATCH_WALK_STEP      5u
#define HATCH_MOUNT_ARMED    0xffu   /* OBJ_HATCH_MOUNT, read by update_objects @ 0x124fc */

/* The bounce-up frame is drawn taller and higher by the same four rows: 0x1273c adds them to
 * draw_rows and 0x12742's `subi.l #$280` lifts draw_dst by the matching four scanlines. */
#define EGG_BOUNCE_UP_ROWS   4u

/* 0x12620 — stage the draw scratch from the egg sub-record, before anything looks at the state. */
static void stage_egg_draw_scratch(uint8_t *image, uint32_t object) {
    wr32(image + A_draw_src, be32(image + object + OBJ_EGG_SRC));
    wr32(image + A_draw_dst, be32(image + object + OBJ_EGG_DST));
    wr16(image + A_draw_x, be16(image + object + OBJ_EGG_X));
    wr16(image + A_draw_y, be16(image + object + OBJ_EGG_Y));
    image[A_draw_rows] = image[object + OBJ_EGG_ROWS];
    image[A_draw_shift] = image[object + OBJ_EGG_SHIFT];
}

/* 0x12716 — the animation jump table: pick this state's sprite and its handler.
 *
 * The index is (state - 1) * 8 with the decrement done as `subq.b`, so state 0 would index 0xff.
 * Three of the shipped table's records are all-zero, and the original would `jmp 0` on them; none is
 * reachable from a state the game itself produces (only state 4 could, and nothing writes it). The
 * reconstruction cannot follow a jump to address 0, so it treats an unrecognised handler as "on to
 * the next object"; test_egg.py pins which records are null and which handlers exist.
 */
static enum egg_slot_exit egg_dispatch_animation(uint8_t *image, uint32_t object) {
    uint8_t state = image[object + OBJ_EGG_STATE];
    uint32_t record = A_egg_sprite_ptrs + (uint32_t)((uint8_t)(state - 1u)) * EGG_PTR_RECORD;

    wr32(image + A_draw_src, be32(image + record + EGG_PTR_SRC));
    switch (be32(image + record + EGG_PTR_HANDLER)) {
    case EGG_HANDLER_DRAW_ONLY: return EGG_SLOT_DRAW_ONLY;
    case EGG_HANDLER_REDRAW:    return EGG_SLOT_REDRAW;
    default:                    return EGG_SLOT_NEXT;
    }
}

/* 0x12832 — step one frame down the animation. Reaching either end mark clears the egg. */
static enum egg_slot_exit egg_animation_step(uint8_t *image, uint32_t object) {
    uint8_t state = --image[object + OBJ_EGG_STATE];
    if (state != EGG_STATE_HATCHING && state != EGG_STATE_DEATH_END)
        return egg_dispatch_animation(image, object);
    image[object + OBJ_EGG_STATE] = 0;
    erase_egg_sprite(image, object);
    return EGG_SLOT_NEXT;
}

/* 0x127c0 — the altitude the hatched rider is placed at, from the egg's own height.
 *
 * The middle band writes HATCH_Y_MID and then overwrites it with HATCH_Y_TOP for its upper part.
 * Both stores are reproduced because that is what the original does, but the differential CANNOT
 * see the difference: it compares final memory, and the discarded first store leaves none. Making
 * it conditional passes the whole battery. */
static void hatch_place_rider_y(uint8_t *image, uint32_t object) {
    int16_t egg_y = (int16_t)be16(image + object + OBJ_EGG_Y);
    if (egg_y <= HATCH_Y_LOW_BAND) {
        wr16(image + object + OBJ_Y, HATCH_Y_TOP);
        return;
    }
    if (egg_y > HATCH_Y_MID_BAND) {
        wr16(image + object + OBJ_Y, HATCH_Y_BOTTOM);
        return;
    }
    wr16(image + object + OBJ_Y, HATCH_Y_MID);
    if (egg_y >= HATCH_Y_MID_HIGH) wr16(image + object + OBJ_Y, HATCH_Y_TOP);
}

/* 0x12762 — the egg hatches: the slot stops being an egg and becomes a rider.
 *
 * The rider's flags word is built from OBJ_EGG_SPAWN_FLAGS, so it inherits the rider type in the low
 * bits and — if the egg was never drawn — OBJ_FLAG_RESPAWN, which shares bit 7 with
 * EGG_SPAWN_UNDRAWN. OBJ_FLAG_DEAD is added on top (`bset #13,d0`) — the rider is not on the
 * playfield yet, and update_objects clears the bit when it places it — and the respawn branch of
 * render_object_body is what actually puts it on screen. Note the hatch sets bit 13 ALONE: it is
 * not a death, so world.h's OBJ_FLAG_REMOVED (bit 12) stays clear. Every rider hatches at
 * speed_type1, whatever its type.
 */
static enum egg_slot_exit egg_hatch(uint8_t *image, uint32_t object) {
    image[object + OBJ_HATCH_MOUNT] = HATCH_MOUNT_ARMED;
    image[object + OBJ_STEP_TIMER] = HATCH_WALK_STEP;
    image[object + OBJ_ANIM_TIMER] = HATCH_WALK_ANIM;
    wr16(image + object + OBJ_VY, 0);

    uint32_t flags = image[object + OBJ_EGG_SPAWN_FLAGS] | OBJ_FLAG_DEAD;
    uint16_t speed = be16(image + A_speed_type1);
    if (be16(image + object + OBJ_EGG_X) < HATCH_X_MID) {       /* unsigned: `bcc` */
        wr16(image + object + OBJ_VX, (uint16_t)(0u - (uint32_t)speed));   /* folded `move ; neg` */
        wr16(image + object + OBJ_X, 0);
    } else {
        wr16(image + object + OBJ_VX, speed);
        wr16(image + object + OBJ_X, HATCH_X_RIGHT);
        flags |= OBJ_FLAG_FACING_RIGHT;
    }
    wr16(image + object + OBJ_TARGET_VX, be16(image + object + OBJ_VX));
    /* `move.w egg_y,target_y ; subi.w #$e,target_y` — folded. */
    wr16(image + object + OBJ_TARGET_Y,
         (uint16_t)(be16(image + object + OBJ_EGG_Y) - HATCH_TARGET_Y_BIAS));
    hatch_place_rider_y(image, object);
    wr16(image + object + OBJ_FLAGS, (uint16_t)flags);

    /* The egg state becomes the spawn-flags byte, i.e. the rider type — which is also this frame's
     * animation frame, and next frame's jump-table index. */
    image[object + OBJ_EGG_STATE] = image[object + OBJ_EGG_SPAWN_FLAGS];
    int8_t type = (int8_t)image[object + OBJ_EGG_SPAWN_FLAGS];
    if (type < EGG_SPAWN_TYPE_MID)       wr32(image + A_draw_src, A_rider_sprite_type1);
    else if (type == EGG_SPAWN_TYPE_MID) wr32(image + A_draw_src, A_rider_sprite_type2);
    else                                 wr32(image + A_draw_src, A_rider_sprite_type3);
    return EGG_SLOT_REDRAW;
}

/* 0x12734 — every state below EGG_STATE_READY: an animation frame, the hatch, or the one frame that
 * is drawn four rows higher than the rest. */
static enum egg_slot_exit egg_animate(uint8_t *image, uint32_t object) {
    uint8_t state = image[object + OBJ_EGG_STATE];
    if (state == EGG_STATE_BOUNCE_UP) {
        image[A_draw_rows] += EGG_BOUNCE_UP_ROWS;
        wr32(image + A_draw_dst,
             be32(image + A_draw_dst) - EGG_BOUNCE_UP_ROWS * SCREEN_ROW_BYTES);
        wr16(image + A_draw_y, (uint16_t)(be16(image + A_draw_y) - EGG_BOUNCE_UP_ROWS));
        return egg_animation_step(image, object);
    }
    if ((int8_t)state < (int8_t)EGG_STATE_HATCH) return egg_dispatch_animation(image, object);
    if ((int8_t)state > (int8_t)EGG_STATE_HATCH) return egg_animation_step(image, object);
    return egg_hatch(image, object);
}

/* 0x126fa — the egg has settled and is hatchable. It waits for a free object slot, then starts the
 * hatch animation and claims that slot up front. */
static enum egg_slot_exit egg_ready_to_hatch(uint8_t *image, uint32_t object) {
    if ((int8_t)image[A_live_object_count] < EGG_MAX_LIVE_OBJECTS
        && --image[object + OBJ_EGG_HATCH_TIMER] == 0) {
        image[object + OBJ_EGG_STATE] = EGG_STATE_HATCHING;
        image[A_live_object_count]++;
    }
    return egg_dispatch_animation(image, object);
}

/* 0x126d2 — the egg is sinking into the lava. draw_egg_sprite set this state and rewrote draw_rows
 * to the rows that fitted above the lava line; each frame drops the sprite one scanline and one row
 * further until nothing is left, at which point the egg is erased and the slot cleared. */
static enum egg_slot_exit egg_sink_into_lava(uint8_t *image, uint32_t object) {
    if (--image[A_draw_rows] != 0) {
        wr16(image + A_draw_y, (uint16_t)(be16(image + A_draw_y) + 1u));
        wr32(image + A_draw_dst, be32(image + A_draw_dst) + SCREEN_ROW_BYTES);
        return EGG_SLOT_REDRAW;
    }
    image[object + OBJ_EGG_STATE] = 0;
    erase_egg_sprite(image, object);
    return EGG_SLOT_NEXT;
}

/* 0x12668 — the egg is in flight: physics first, then gravity and one step of motion.
 *
 * Both moves are `add.w` followed by `bge`, which tests N==V — the MATHEMATICAL sign of the sum, not
 * the sign of the stored word. Hence the 32-bit arithmetic here.
 */
static enum egg_slot_exit egg_in_flight(uint8_t *image, uint32_t object) {
    if (update_egg_physics(image, object) == EGG_PHYSICS_TAIL_JUMPED) return EGG_SLOT_DRAW;

    if (--image[object + OBJ_EGG_FALL_TIMER] == 0) {
        image[object + OBJ_EGG_FALL_TIMER] = EGG_FALL_TIMER_PERIOD;
        int16_t fall = (int16_t)be16(image + object + OBJ_EGG_DY);
        if (fall != EGG_FALL_SPEED_MAX) wr16(image + object + OBJ_EGG_DY, (uint16_t)(fall + 1));
    }

    int32_t x = (int16_t)be16(image + A_draw_x) + (int16_t)be16(image + object + OBJ_EGG_DX);
    wr16(image + A_draw_x, (uint16_t)x);
    if (x < 0) wr16(image + A_draw_x, (uint16_t)(x + EGG_X_WRAP));
    else if ((int16_t)be16(image + A_draw_x) >= (int16_t)EGG_X_WRAP)
        wr16(image + A_draw_x, (uint16_t)(be16(image + A_draw_x) - EGG_X_WRAP));

    int32_t y = (int16_t)be16(image + A_draw_y) + (int16_t)be16(image + object + OBJ_EGG_DY);
    wr16(image + A_draw_y, (uint16_t)y);
    if (y < 0) {
        wr16(image + A_draw_y, 0);                                  /* stop at the top of the screen */
        int16_t fall = (int16_t)be16(image + object + OBJ_EGG_DY);
        if (fall < 0) wr16(image + object + OBJ_EGG_DY, (uint16_t)(0u - (uint16_t)fall));
    }
    return EGG_SLOT_DRAW;
}

/* 0x1260c — one object slot's egg, from the state test to whichever jump target ends it. */
static enum egg_slot_exit update_egg_slot(uint8_t *image, uint32_t object) {
    stage_egg_draw_scratch(image, object);
    uint8_t state = image[object + OBJ_EGG_STATE];
    if (state == EGG_STATE_LAVA) return egg_sink_into_lava(image, object);
    if (state == EGG_STATE_READY) return egg_ready_to_hatch(image, object);
    /* `blt` on a byte compare: a state of 0x80 or more counts as BELOW EGG_STATE_READY.
     *
     * UNPINNED, and unpinnable: those are the only states an unsigned compare would route
     * differently, and the original cannot survive one — egg_dispatch_animation would index the
     * jump table past its end, where no record holds either handler, and `jmp (a2)` would leave the
     * program. So no run that distinguishes the two compares can be diffed at all. */
    if ((int8_t)state < (int8_t)EGG_STATE_READY) return egg_animate(image, object);
    return egg_in_flight(image, object);
}

/* The object loop from `object` on — 0x12606 enters it at the table's head, and every tail jump in
 * the subsystem re-enters it at 0x12612 with the current slot already done. */
static void update_eggs_from(uint8_t *image, uint32_t object) {
    for (; object != A_object_table_END; object += OBJ_SIZE) {
        if (image[object + OBJ_EGG_STATE] == 0) continue;
        switch (update_egg_slot(image, object)) {
        case EGG_SLOT_NEXT:                                          break;
        case EGG_SLOT_DRAW:        update_egg_draw(image, object);    break;
        case EGG_SLOT_REDRAW:      egg_redraw(image, object);         break;
        case EGG_SLOT_DRAW_ONLY:   draw_egg_sprite(image, object);    break;
        }
    }
}

/* update_eggs() @ 0x12606 — drive every slot's egg sub-record for one frame. */
void update_eggs(uint8_t *image) {
    update_eggs_from(image, A_object_table);
}

/* ------------------------------------------------------------------------------------- glue ---
 *
 * The two entry points below are reached by jumps inside the subsystem, never by a call, so the
 * original resumes the OBJECT LOOP on the way out rather than returning to its caller. Entering the
 * oracle at either address runs that continuation too, and these glues run it on the candidate — the
 * chain is the I/O contract, not an extra the test could opt out of.
 */

void g_update_eggs(uint8_t *image) {
    update_eggs(image);
}

void g_update_egg_draw(uint8_t *image, uint32_t object) {
    update_egg_draw(image, object);
    update_eggs_from(image, object + OBJ_SIZE);   /* its `jmp 0x12612` */
}

void g_update_egg_physics(uint8_t *image, uint32_t object) {
    if (update_egg_physics(image, object) == EGG_PHYSICS_RETURNED) return;
    update_egg_draw(image, object);               /* the discarded return address, then 0x1285c */
    update_eggs_from(image, object + OBJ_SIZE);
}
