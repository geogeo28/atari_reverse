/* world.c — Joust's world layer: what the riders land on, fall into and are grabbed by.
 *
 * Seven mechanisms live here, and they only meet at the screen:
 *
 *   draw_platforms         repaints the platforms sprites have overdrawn,
 *   raise_floor            walks the lava surface up one scanline at a time,
 *   dissolve_platforms     eats away the platforms that vanish between waves,
 *   animate_ground_shrink  burns the ground in from both ends over waves 3-4,
 *   flash_spawn_pad        flashes the pad a rider is materialising on,
 *   troll_erase_hand /     undraw and draw the lava troll's hand (its driver, lava_troll, is
 *   troll_draw_hand        not reconstructed yet — see recreate/STATUS.md),
 *   start_death_anim       arms the sprite a killed rider leaves behind.
 *
 * As everywhere in this reconstruction, faithfulness beats correctness: where the original is odd
 * (raise_floor paints two 40-byte strips of a 160-byte scanline and leaves the gaps alone) the
 * oddity is reproduced and commented, not fixed.
 */
#include "machine.h"
#include "world.h"

/* =================================================================================================
 * Shared cell primitives.
 * ============================================================================================= */

/* AND one 16-bit mask into all four of a cell's bitplane words — the erase half of every sprite
 * blit here.
 *
 * KNOWN DUPLICATE: src/draw.c carries the same two primitives as `mask_cell` and `or_plane`, and
 * `or_plane` is verbatim. They are `static` there, so collapsing the copies means un-static-ing
 * them and declaring them in draw.h — a change to the drawing layer, which this reconstruction
 * does not own. Flagged for that layer rather than papered over here. */
static void and_cell(uint8_t *image, uint32_t cell, uint16_t mask) {
    for (unsigned plane = 0; plane < CELL_PLANE_WORDS; plane++)
        wr16(image + cell + plane * 2u, (uint16_t)(be16(image + cell + plane * 2u) & mask));
}

/* OR one plane's pixels into a cell. */
static void or_plane(uint8_t *image, uint32_t cell, unsigned plane, uint16_t pixels) {
    uint32_t at = cell + plane * 2u;
    wr16(image + at, (uint16_t)(be16(image + at) | pixels));
}

/* A 16-bit value in BOTH halves of a longword. The original builds these with a `move.l` followed
 * by a `move.w` at the same address: the long read fills the high half and the word read replaces
 * the low half with the very same word (`move.l 6(a1),d5 ; move.w 6(a1),d5`). */
static uint32_t dup16(uint16_t value) { return ((uint32_t)value << 16) | value; }

/* =================================================================================================
 * draw_platforms @ 0x1052e — the repair pass that puts the platforms back.
 * ============================================================================================= */

/* The two platforms the game keeps in lockstep: each pair is the two halves of one structure, so
 * they must appear and disappear together. Whichever countdown is further along wins — a SIGNED
 * byte compare, so the spent -1 latch loses to any live count. */
static const unsigned char PLATFORM_MIRRORED_PAIRS[][2] = {{2, 3}, {6, 7}};

static void sync_platform_pair(uint8_t *image, unsigned lo, unsigned hi) {
    int8_t lo_count = (int8_t)image[A_platform_present + lo];
    int8_t hi_count = (int8_t)image[A_platform_present + hi];

    if (hi_count > lo_count) image[A_platform_present + lo] = (uint8_t)hi_count;
    else if (hi_count < lo_count) image[A_platform_present + hi] = (uint8_t)lo_count;
}

/* Each platform_sprites record points at its own platform_present byte. A count above zero means
 * "this platform still needs redrawing": OR the bitmap back over whatever has been drawn on top of
 * it, and tick the count down. Reaching zero latches to -1 rather than stopping at 0, so the slot
 * reads as "done" (<= 0) until something arms it again.
 *
 * The original also loads the record's PSPR_SRC into d0 here and never uses it (`move.l 8(a6),d0`
 * at 0x10588); the value is re-fetched from the record when it is pushed. Dead, so not reproduced.
 *
 * blit_or is called in its register form rather than through an argument block. The original does
 * build one on the machine stack, and blit.c models the original's per-row re-read of `cols` from
 * it — but only a destination that overlapped that block could tell the two apart, and the block
 * lives on the oracle's own stack, in the band the differential drops.
 */
void draw_platforms(uint8_t *image) {
    for (unsigned pair = 0; pair < sizeof PLATFORM_MIRRORED_PAIRS / sizeof *PLATFORM_MIRRORED_PAIRS;
         pair++)
        sync_platform_pair(image, PLATFORM_MIRRORED_PAIRS[pair][0], PLATFORM_MIRRORED_PAIRS[pair][1]);

    uint32_t record = A_platform_sprites;
    for (unsigned n = 0; n < PLATFORM_COUNT; n++, record += PSPR_RECORD) {
        uint32_t present = be32(image + record + PSPR_PRESENT);
        if ((int8_t)image[present] <= 0) continue;

        uint8_t left = (uint8_t)(image[present] - 1u);       /* subq.b #1,(a0) */
        image[present] = left ? left : PLATFORM_SPENT;

        blit_or(image,
                be32(image + A_screen_base) + be32(image + record + PSPR_DST_OFF),
                be32(image + record + PSPR_SRC),
                be16(image + record + PSPR_COLS),
                be16(image + record + PSPR_ROWS));
    }
}

void g_draw_platforms(uint8_t *image) { draw_platforms(image); }

/* =================================================================================================
 * raise_floor @ 0x1757a — the lava creeping up the screen.
 * ============================================================================================= */

/* playfield_bottom is the screen address of the lava surface, and any sprite drawn down to it dies.
 * wave_manager owes the floor a number of rows at the start of each of the opening waves; this pays
 * one off every FLOOR_STEP_FRAMES calls, moving the surface up a scanline and recolouring what it
 * just exposed.
 *
 * Only two 5-cell strips of the 20-cell scanline are painted: cells 0-4 (x 0-79) and cells 15-19
 * (x 240-319). That is not an oversight — the ground platform (platform 0, 12 cells from cell 4)
 * covers x 64-255, so the strips are the lava the ground leaves exposed plus one cell of overlap at
 * each end: cell 4 and cell 15 are painted despite sitting under the ground. Whole cells are what
 * the two calls can address, so the middle 10 cells are skipped and the edge cells are not.
 */
void raise_floor(uint8_t *image) {
    if (image[A_floor_rows_left] == 0) return;
    if (--image[A_floor_step_timer] != 0) return;     /* subq.b: a byte counter, so 0 wraps to 255 */

    image[A_floor_rows_left]--;
    image[A_floor_step_timer] = FLOOR_STEP_FRAMES;

    uint32_t surface = be32(image + A_playfield_bottom) - SCREEN_ROW_BYTES;
    wr32(image + A_playfield_bottom, surface);
    paint_floor_row(image, surface);
    paint_floor_row(image, surface + FLOOR_PAINT_ADVANCE + FLOOR_SECOND_STRIP);
}

void g_raise_floor(uint8_t *image) { raise_floor(image); }

/* =================================================================================================
 * flash_spawn_pad @ 0x13628 — the flash on the pad a rider materialises on.
 * ============================================================================================= */

/* Every platform bitmap carries a colour-4 trapezoidal pad baked into its top three rows, at
 * exactly the cell and pixel offset the matching spawn_points record names. This routine repaints
 * that pad — three row masks, shifted to the record's pixel phase — in a flat colour taken from
 * A_spawn_pad_colors, so the pad flashes while the rider forms. Two of the eight entries are
 * colour 0, which blanks the pad rather than lighting it.
 *
 * The flash is not quite the baked pad: it tapers 30/26/22 pixels over its three rows where the
 * baked pad tapers 30/28/24, so rows 1-2 of the flash sit one pixel inside it. Measured off the
 * bitmaps, not derived — do not "correct" either figure to match the other.
 *
 * Register map: a0 = the object, d0 = its flags, d1 = the flash phase then the pixel shift,
 * d2 = the plane-select byte, a1 = the spawn point, a2 = the pattern, a3 = the destination cell.
 * The phase is normally the rider's step timer mod 4; on phase 1 a flagged object substitutes the
 * low three bits of its flags instead, which is how the last four colours are ever reached.
 */
void flash_spawn_pad(uint8_t *image, uint32_t object, uint32_t flags) {
    uint32_t phase = image[object + OBJ_STEP_TIMER] & SPAWN_PAD_PHASE_MASK;
    if (phase == SPAWN_PAD_PHASE_ALT && (flags & SPAWN_PAD_ALT_FLAG))
        phase = flags & SPAWN_PAD_COLOR_MASK;
    uint32_t plane_select = image[A_spawn_pad_colors + phase];

    /* The respawn path parks the spawn point's byte offset in the rider's velocity field. */
    uint32_t spawn = A_spawn_points + sign_ext16(be16(image + object + OBJ_VY));
    uint32_t shift = image[spawn + SPAWN_SHIFT];
    uint32_t dst = be32(image + A_screen_base) + sign_ext16(be16(image + spawn + SPAWN_DST_OFF));

    for (unsigned cell = 0; cell < SPAWN_PAD_CELLS; cell++) {
        uint32_t pattern = A_spawn_pad_pattern + cell * SPAWN_PAD_CELL_STRIDE;
        blit_pattern_rows(image, dst, plane_select,
                          lsr32(be32(image + pattern), shift),
                          lsr32(be32(image + pattern + SPAWN_PAD_ROW_STRIDE), shift),
                          lsr32(be32(image + pattern + 2u * SPAWN_PAD_ROW_STRIDE), shift));
        dst += CELL_BYTES;
    }
}

void g_flash_spawn_pad(uint8_t *image, uint32_t object, uint32_t flags) {
    flash_spawn_pad(image, object, flags);
}

/* =================================================================================================
 * troll_erase_hand @ 0x149b8 and troll_draw_hand @ 0x14a32 — the lava troll's hand.
 * ============================================================================================= */

/* Both blit a two-cell-wide sprite, one row per scanline, and both stop the moment the destination
 * reaches the lava surface — playfield_bottom is re-read on EVERY row, so a floor that rises
 * mid-blit truncates the hand. The row counters are signed words: a count of 0 or less draws
 * nothing, unlike the byte counters in blit.c where 0 means 256.
 *
 * Both read draw_shift and draw_rows (and their troll_prev_* mirrors) as WORDS. addrs.h records
 * why that matters: the rider blitters read the same two addresses as BYTES, i.e. as the high half
 * of the word these two read, so each subsystem must read exactly the width its own instruction does.
 */

/* Is this row's destination still above the lava? `movea.l playfield_bottom,a3 ; subq.w #8,a3 ;
 * cmpa.l a3,a1 ; bcc` — an UNSIGNED compare against one cell short of the surface. */
static int row_is_above_lava(const uint8_t *image, uint32_t dst) {
    return dst < be32(image + A_playfield_bottom) - CELL_BYTES;
}

/* Undo the frame troll_draw_hand last put on screen, by ANDing its silhouette mask out. The mask
 * sits SPR_MASK_OFF into the sprite, the same layout the ground-animation sprites use (draw.h).
 *
 * Register map: a2 = the mask cursor, a1 = the running destination, d4 = shift, d7 = rows. */
void troll_erase_hand(uint8_t *image) {
    uint32_t src = be32(image + A_troll_prev_src);
    uint32_t dst = be32(image + A_troll_prev_dst);
    uint32_t shift = be16(image + A_troll_prev_shift);
    uint16_t rows = be16(image + A_troll_prev_rows);

    /* Nothing moved since the last frame, so the hand already on screen is the right one: erasing
     * it here would leave a hole that this frame's draw pass fills back in identically. */
    if (src == be32(image + A_draw_src) && dst == be32(image + A_draw_dst)
        && shift == be16(image + A_draw_shift))
        return;

    uint32_t mask = src + SPR_MASK_OFF;
    dst += be32(image + A_screen_base);

    for (int16_t row = 0; row < (int16_t)rows; row++) {
        if (!row_is_above_lava(image, dst)) return;

        /* ROTATED, not shifted: the bits leaving the trailing cell's word re-enter the leading
         * cell's, which is what makes one longword cover both cells of a shifted sprite. */
        uint32_t bits = ror32(be32(image + mask), shift);
        mask += TROLL_MASK_ROW_BYTES;

        and_cell(image, dst + CELL_BYTES, (uint16_t)bits);
        and_cell(image, dst, (uint16_t)(bits >> 16));
        dst += SCREEN_ROW_BYTES;
    }
}

void g_troll_erase_hand(uint8_t *image) { troll_erase_hand(image); }

/* OR this frame's hand in, when the state word says the hand is out at all.
 *
 * Register map: d0 = the troll state, a1 = the sprite cursor, a2 = the running destination,
 * d6 = shift, d7 = rows, d2-d5 = the four planes' shifted pixels. Every plane of a row is read
 * before any of it is written, as in the original — which is observable when a hand is drawn over
 * its own source. */
void troll_draw_hand(uint8_t *image, uint32_t state) {
    if (!(state & TROLL_STATE_HAND_OUT)) return;

    uint32_t src = be32(image + A_draw_src);
    uint32_t dst = be32(image + A_draw_dst) + be32(image + A_screen_base);
    uint32_t shift = be16(image + A_draw_shift);
    uint16_t rows = be16(image + A_draw_rows);

    for (int16_t row = 0; row < (int16_t)rows; row++) {
        if (!row_is_above_lava(image, dst)) return;

        /* `move.l k(a1),dn ; clr.w dn ; lsr.l d6,dn`: one plane word in the high half, so the bits
         * shifted out of the leading cell land in the low half — the trailing cell's contribution. */
        uint32_t pixels[CELL_PLANE_WORDS];
        for (unsigned plane = 0; plane < CELL_PLANE_WORDS; plane++)
            pixels[plane] = lsr32((uint32_t)be16(image + src + plane * 2u) << 16, shift);

        for (unsigned plane = 0; plane < CELL_PLANE_WORDS; plane++)
            or_plane(image, dst + CELL_BYTES, plane, (uint16_t)pixels[plane]);
        for (unsigned plane = 0; plane < CELL_PLANE_WORDS; plane++)
            or_plane(image, dst, plane, (uint16_t)(pixels[plane] >> 16));

        src += CELL_BYTES;
        dst += SCREEN_ROW_BYTES;
    }
}

void g_troll_draw_hand(uint8_t *image, uint32_t state) { troll_draw_hand(image, state); }

/* =================================================================================================
 * start_death_anim @ 0x14098 — arming the sprite a killed rider leaves behind.
 * ============================================================================================= */

#define DEATH_SPRITE_RISE  0x280u  /* four scanlines: the dismount starts above the rider */
#define DEATH_SPRITE_ROWS  9u
#define DEATH_EGG_STATE_P1     0x19u
#define DEATH_EGG_STATE_OTHER  0x20u
#define DEATH_SCORE_HUNDREDS   5u  /* addq.b #5 — 500 points */

/* Reuses the rider's egg slot as the death sprite's: the egg record is pointed at the dismount
 * bitmap, one four-scanline hop above where the rider was last drawn, and given the rider's own
 * pixel phase. Nothing is respawned here — that is render_object_body's bit-7 branch.
 *
 * Register map: a0 = the object, d0 = its flags in and out, d5 = screen_base. */
uint32_t start_death_anim(uint8_t *image, uint32_t object, uint32_t flags) {
    flags |= OBJ_FLAG_DEAD | OBJ_FLAG_REMOVED;
    image[object + OBJ_EGG_CHAIN] = 0;

    /* Clamped, not clipped: a death sprite that would start above the framebuffer is drawn at the
     * rider's own last position instead (`cmp.l 42(a0),d5 ; blt`, a SIGNED compare).
     *
     * The original computes this IN PLACE — `move.l 20(a0),42(a0)`, `subi.l #$280,42(a0)`, and only
     * then reads screen_base and compares it against what OBJ_EGG_DST now holds — where the local
     * below collapses those three memory accesses into one write. The two diverge only if the
     * longword at object + OBJ_EGG_DST overlaps A_screen_base, so that the in-place writes change
     * what the compare then reads: object 0x10db1..0x10db7 (0x10dde - 0x2a is the exact alias, and
     * a partial overlap either side of it diverges too). Every one of those is below A_object_table
     * at 0x10f36, so no caller can produce one. Collapsed deliberately: the faithful three-write
     * form would be harder to read for a case the game cannot reach. */
    uint32_t rider_dst = be32(image + object + OBJ_PREV_DST);
    uint32_t death_dst = rider_dst - DEATH_SPRITE_RISE;
    if ((int32_t)be32(image + A_screen_base) >= (int32_t)death_dst) death_dst = rider_dst;
    wr32(image + object + OBJ_EGG_DST, death_dst);

    image[object + OBJ_EGG_SHIFT] = image[object + OBJ_PREV_SHIFT];
    image[object + OBJ_EGG_ROWS] = DEATH_SPRITE_ROWS;

    int is_player1 = object == A_object_table;
    image[object + OBJ_EGG_STATE] = is_player1 ? DEATH_EGG_STATE_P1 : DEATH_EGG_STATE_OTHER;
    wr32(image + object + OBJ_EGG_SRC, is_player1 ? A_death_sprite_p1 : A_death_sprite_other);

    image[object + OBJ_SCORE_PENDING] += DEATH_SCORE_HUNDREDS;
    return flags;
}

/* Register ABI: a0 = object, d0 = flags in, D0 = flags out. An image diff cannot see D0, so the
 * oracle is entered through a stub that stores it to `result` and the glue writes the same
 * longword to the same address — the convention test/abi.py documents. */
void g_start_death_anim(uint8_t *image, uint32_t object, uint32_t flags, uint32_t result) {
    wr32(image + result, start_death_anim(image, object, flags));
}

/* =================================================================================================
 * animate_ground_shrink @ 0x175de — the ground burning in from both ends.
 * ============================================================================================= */

/* Two 18-row lava-flame sprites sit on the ground platform, one at each end, and every third call
 * they advance a frame and creep one pixel towards each other. On wave 3 the ground's landable
 * x range (platform 0's PLAT_X0/PLAT_X1, i.e. A_ground_x0/A_ground_x1) closes in with them, so the
 * ground really does get narrower rather than merely looking burnt. When the two flames have all
 * but met the whole thing sinks a scanline at a time and loses a row.
 *
 * The frame works on a COPY of the state block: the erase pass blits the live block (the frame
 * already on screen) while the draw pass blits the copy (this frame's), and only then is the copy
 * written back. That is why every step below moves `next` and every mask blit reads `live`.
 */

/* `move.l (0,src,d0.w),(0,dst,d0.w)` with d0 counting 0x18 down to 0 — the block, high word first. */
static void copy_ground_anim(uint8_t *image, uint32_t dst, uint32_t src) {
    for (int32_t off = (int32_t)GA_BLOCK_BYTES - 4; off >= 0; off -= 4)
        wr32(image + dst + off, be32(image + src + off));
}

static void advance_flame_frame(uint8_t *image, uint32_t flame) {
    uint32_t frame = be32(image + flame + SPR_SRC) + FLAME_FRAME_BYTES;
    if ((int32_t)frame >= (int32_t)FLAME_FRAME_END) frame = FLAME_FRAME_FIRST;
    wr32(image + flame + SPR_SRC, frame);
}

static void move_flame_rows(uint8_t *image, uint32_t left, uint32_t right, int32_t delta) {
    wr32(image + left + SPR_DST_OFF, be32(image + left + SPR_DST_OFF) + (uint32_t)delta);
    wr32(image + right + SPR_DST_OFF, be32(image + right + SPR_DST_OFF) + (uint32_t)delta);
}

/* Wave 3 only: both edges of the ground march inward one pixel, wrapping back to a fresh full
 * width once the right edge runs past GROUND_X1_WRAP. */
static void shrink_ground_x_range(uint8_t *image) {
    if ((int16_t)be16(image + A_ground_x1) >= GROUND_X1_WRAP) {
        wr16(image + A_ground_x1, GROUND_X1_RESET);
        wr16(image + A_ground_x0, GROUND_X0_RESET);
    }
    wr16(image + A_ground_x0, (uint16_t)(be16(image + A_ground_x0) + 1u));
    wr16(image + A_ground_x1, (uint16_t)(be16(image + A_ground_x1) - 1u));
}

/* A flame creeps one pixel of phase per step, and once the phase leaves the cell it rolls over into
 * a whole-cell step of the destination and starts again at the far edge. `cell_step` is which way
 * the destination moves; the cell-select word is cleared with it, so the newly entered cell is
 * drawn whole.
 *
 * The two directions test their rollover DIFFERENTLY, and not just by sign — see the two callers. */
static void roll_flame_over(uint8_t *image, uint32_t flame, int32_t cell_step, uint16_t new_phase) {
    wr32(image + flame + SPR_DST_OFF, be32(image + flame + SPR_DST_OFF) + (uint32_t)cell_step);
    wr16(image + flame + SPR_SHIFT, new_phase);
    wr16(image + flame + SPR_CELL_SELECT, 0);
}

/* `addq.w #1,12(a4) ; cmpi.w #$10,12(a4) ; blt` — the test is a separate compare against the value
 * as STORED, so the wrapped word is what decides: a phase of 0x7fff becomes 0x8000, which is
 * negative and therefore still below a cell's width. */
static void creep_flame_rightwards(uint8_t *image, uint32_t flame) {
    int16_t phase = (int16_t)(be16(image + flame + SPR_SHIFT) + 1u);
    wr16(image + flame + SPR_SHIFT, (uint16_t)phase);
    if (phase < (int16_t)CELL_PIXELS) return;
    roll_flame_over(image, flame, (int32_t)CELL_BYTES, 0);
}

/* `subq.w #1,24(a4) ; bge` — here the branch reads the flags of the SUBTRACTION itself, and `bge`
 * is N == V, which is the sign of the TRUE difference rather than of the wrapped word. So a phase
 * of 0x8000 rolls over (-32768 - 1 is negative) even though the stored result, 0x7fff, looks
 * positive. Testing the wrapped word instead gets that one value backwards. */
static void creep_flame_leftwards(uint8_t *image, uint32_t flame) {
    int32_t phase = (int16_t)be16(image + flame + SPR_SHIFT);
    wr16(image + flame + SPR_SHIFT, (uint16_t)(phase - 1));
    if (phase - 1 >= 0) return;
    roll_flame_over(image, flame, -(int32_t)CELL_BYTES, CELL_PIXELS - 1u);
}

void animate_ground_shrink(uint8_t *image) {
    if ((int16_t)be16(image + A_ground_anim + GA_ROWS_LATCH) <= 0) return;
    if (--image[A_ground_anim_timer] != 0) return;
    image[A_ground_anim_timer] = GROUND_ANIM_PERIOD;

    copy_ground_anim(image, A_ground_anim_next, A_ground_anim);

    uint32_t left = A_ground_anim_next + GA_FLAME_LEFT;
    uint32_t right = A_ground_anim_next + GA_FLAME_RIGHT;
    advance_flame_frame(image, left);
    advance_flame_frame(image, right);

    /* The gap is a longword subtraction the original then compares as a WORD (`cmpi.w #$60,d0`),
     * so only its low half decides — reproduced by the int16_t cast. */
    int16_t flame_gap = (int16_t)(be32(image + right + SPR_DST_OFF)
                                  - be32(image + left + SPR_DST_OFF));
    int16_t rows = (int16_t)be16(image + A_ground_anim_next + GA_ROWS);

    if (be16(image + right + SPR_SHIFT) == GROUND_SINK_SHIFT && flame_gap <= GROUND_SINK_GAP) {
        /* The flames have met: the burnt strip drops a scanline and loses a row of height. */
        move_flame_rows(image, left, right, (int32_t)SCREEN_ROW_BYTES);
        wr16(image + A_ground_anim_next + GA_ROWS, (uint16_t)(rows - 1));
        wr16(image + A_ground_anim_next + GA_ROWS_LATCH,
             be16(image + A_ground_anim_next + GA_ROWS));
    } else if (rows < GROUND_ROWS_MIN) {
        /* Too short to keep sinking: climb back up. The latch is deliberately NOT refreshed here,
         * so this branch cannot re-arm a routine whose latch has already run down. */
        move_flame_rows(image, left, right, -(int32_t)SCREEN_ROW_BYTES);
        wr16(image + A_ground_anim_next + GA_ROWS, (uint16_t)(rows + 1));
    } else if (image[A_wave_num] == GROUND_SHRINK_WAVE) {
        shrink_ground_x_range(image);
        creep_flame_rightwards(image, left);
        creep_flame_leftwards(image, right);
    }

    /* Erase from the LIVE block (what is on screen) and draw from the copy, each blit taking its
     * row count from the block it blits — re-read per call, as the original does. */
    for (unsigned flame = 0; flame < 2; flame++) {
        uint32_t at = flame ? GA_FLAME_RIGHT : GA_FLAME_LEFT;
        blit_sprite_mask(image, A_ground_anim + at, be16(image + A_ground_anim + GA_ROWS));
        blit_sprite(image, A_ground_anim_next + at, be16(image + A_ground_anim_next + GA_ROWS));
    }

    copy_ground_anim(image, A_ground_anim, A_ground_anim_next);
}

void g_animate_ground_shrink(uint8_t *image) { animate_ground_shrink(image); }

/* =================================================================================================
 * dissolve_platforms @ 0x17438 — the platforms that vanish between waves.
 * ============================================================================================= */

/* wave_manager seeds effect_table with the platforms present in the old layout but not the new one.
 * Each slot then runs for DISSOLVE_FRAMES calls, eating its platform away from the BOTTOM-RIGHT
 * corner upwards: one row per call, with pseudo-random noise dripped a scanline down ahead of the
 * erase so the platform appears to crumble. The last frame lays no noise.
 *
 * The record carries the two cursors between calls rather than recomputing them, which is why the
 * first frame runs a whole extra pass just to walk them to the far corner.
 */

/* First frame: latch the platform's geometry into the slot, then sweep the bitmap forwards once to
 * leave EFF_SRC / EFF_DST pointing one row past the far corner — where the dissolve starts.
 *
 * That sweep is not free: it also ANDs a per-cell mask out of plane 2 of every cell it passes
 * (`not.w` the sprite's plane-2 word, OR its plane-3 word, AND into the screen's plane-2 word), so
 * the platform is knocked down to its plane-3 silhouette before it starts crumbling. */
static void dissolve_begin(uint8_t *image, uint32_t slot, uint16_t kind) {
    wr16(image + slot + EFF_TIMER, DISSOLVE_FRAMES);

    uint32_t sprite = DISSOLVE_SPRITE_BASE + sign_ext16((uint32_t)kind * PSPR_RECORD);
    wr32(image + slot + EFF_ROWS, be32(image + sprite + PSPR_ROWS));   /* rows AND cols, one move.l */

    uint32_t src = be32(image + sprite + PSPR_SRC);
    uint32_t row = be32(image + sprite + PSPR_DST_OFF) + be32(image + A_screen_base);
    uint32_t cursor = row;
    unsigned row_passes = loop_passes(be16(image + sprite + PSPR_ROWS), COUNT_MASK_BYTE);

    for (unsigned r = 0; r < row_passes; r++) {
        cursor = row;
        unsigned col_passes = loop_passes(be16(image + slot + EFF_COLS), COUNT_MASK_BYTE);

        for (unsigned c = 0; c < col_passes; c++) {
            uint16_t keep = (uint16_t)(~be16(image + src + DISSOLVE_PLANE23)
                                       | be16(image + src + DISSOLVE_PLANE3));
            uint32_t at = cursor + DISSOLVE_PLANE23;
            wr16(image + at, (uint16_t)(be16(image + at) & keep));
            src += CELL_BYTES;
            cursor += CELL_BYTES;
        }
        row += SCREEN_ROW_BYTES;
    }
    wr32(image + slot + EFF_SRC, src);
    wr32(image + slot + EFF_DST, cursor);
}

/* One cell's worth of crumble noise, harvested from the program's own bytes: a longword and three
 * words ORed together, all-ones if that happens to come out zero. It is staged through draw_src
 * (the shared sprite scratch) as a longword with the same word in both halves, exactly as the
 * original does — so the pattern is the same in the leading and trailing cell. */
static uint32_t dissolve_noise(uint8_t *image, uint32_t *noise_cursor) {
    uint32_t noise = *noise_cursor;
    uint16_t bits = (uint16_t)be32(image + noise);
    noise += 4;
    for (unsigned word = 0; word < 3; word++, noise += 2)
        bits |= be16(image + noise);
    if (bits == 0) bits = (uint16_t)~bits;
    *noise_cursor = noise;

    wr16(image + A_draw_src, bits);
    wr16(image + A_draw_src + 2u, bits);
    return be32(image + A_draw_src);
}

/* One row of the crumble, walked RIGHT to LEFT. All three cursors are threaded in and out: the
 * bitmap and screen ones because the record carries them across calls, the noise one because it
 * runs on through every row of every slot. */
static void dissolve_row(uint8_t *image, uint32_t slot, uint32_t *src, uint32_t *cursor,
                         uint32_t *noise) {
    unsigned col_passes = loop_passes(be16(image + slot + EFF_COLS), COUNT_MASK_BYTE);

    for (unsigned c = 0; c < col_passes; c++) {
        int lay_noise = be16(image + slot + EFF_TIMER) != DISSOLVE_LAST_FRAME;   /* re-read per cell */
        *src -= CELL_BYTES;
        *cursor -= CELL_BYTES;
        uint32_t cell = *cursor;

        /* The sprite's plane-3 word is the platform's silhouette; `covered` is the part of it the
         * screen still shows in both of the cell's high plane words. */
        uint16_t silhouette = be16(image + *src + DISSOLVE_PLANE3);
        uint32_t covered = dup16((uint16_t)(silhouette
                                            & be16(image + cell + DISSOLVE_PLANE23)
                                            & be16(image + cell + DISSOLVE_PLANE3)));

        if (lay_noise) {
            covered &= dissolve_noise(image, noise);
            /* Sprinkle onto the scanline below — planes 2-3 first, then planes 0-1 narrowed by
             * what this cell still holds, so the crumbs keep the platform's own colouring. */
            uint32_t below = cell + SCREEN_ROW_BYTES;
            wr32(image + below + DISSOLVE_PLANE23, be32(image + below + DISSOLVE_PLANE23) | covered);
            covered &= be32(image + cell);
            wr32(image + below, be32(image + below) | covered);
        }

        uint32_t erase = ~dup16(silhouette);
        wr32(image + cell, be32(image + cell) & erase);
        wr32(image + cell + DISSOLVE_PLANE23, be32(image + cell + DISSOLVE_PLANE23) & erase);
    }
}

/* The trailing pass: one more row's worth of cells, walked forwards from where the crumble stopped,
 * erased outright with no noise. It is what removes the row the previous call dripped onto.
 *
 * It erases with the sprite's PLANE-2 word, where the crumble above uses plane 3 — and it reads
 * `cols` only once, the loop-back landing past the fetch rather than on it. */
static void dissolve_trailing_row(uint8_t *image, uint32_t slot, uint32_t src, uint32_t cursor) {
    unsigned col_passes = loop_passes(be16(image + slot + EFF_COLS), COUNT_MASK_BYTE);

    for (unsigned c = 0; c < col_passes; c++) {
        uint32_t erase = ~dup16(be16(image + src + DISSOLVE_PLANE23));
        wr32(image + cursor, be32(image + cursor) & erase);
        wr32(image + cursor + DISSOLVE_PLANE23, be32(image + cursor + DISSOLVE_PLANE23) & erase);
        src += CELL_BYTES;
        cursor += CELL_BYTES;
    }
}

static void dissolve_slot(uint8_t *image, uint32_t slot) {
    uint32_t src = be32(image + slot + EFF_SRC);
    uint32_t row = be32(image + slot + EFF_DST);
    uint32_t cursor = row;
    uint32_t noise = be32(image + A_rng_ptr);
    unsigned row_passes = loop_passes(be16(image + slot + EFF_ROWS), COUNT_MASK_BYTE);

    for (unsigned r = 0; r < row_passes; r++) {
        cursor = row;
        dissolve_row(image, slot, &src, &cursor, &noise);
        row -= SCREEN_ROW_BYTES;
    }
    dissolve_trailing_row(image, slot, src, cursor);

    wr32(image + A_rng_ptr, noise);
    wr32(image + slot + EFF_DST, be32(image + slot + EFF_DST) + SCREEN_ROW_BYTES);

    uint16_t timer = (uint16_t)(be16(image + slot + EFF_TIMER) - 1u);
    wr16(image + slot + EFF_TIMER, timer);
    wr16(image + slot + EFF_KIND, timer);       /* a spent slot lands back on EFF_KIND == 0 */

    wr32(image + A_rng_ptr, be32(image + A_rng_ptr) + DISSOLVE_NOISE_ADVANCE);
    /* The mix argument is the row counter, which the `subq.b` loop above has just counted down to a
     * zero LOW byte — and rng_advance masks its argument with 0xfe, so it is always 0 here. */
    rng_advance(image, 0);
}

void dissolve_platforms(uint8_t *image) {
    for (uint32_t slot = A_effect_table; (int32_t)slot < (int32_t)A_effect_table_END;
         slot += EFF_RECORD) {
        uint16_t kind = be16(image + slot + EFF_KIND);
        if (kind == 0) continue;
        if (be16(image + slot + EFF_TIMER) == 0) dissolve_begin(image, slot, kind);
        dissolve_slot(image, slot);
    }
}

void g_dissolve_platforms(uint8_t *image) { dissolve_platforms(image); }
