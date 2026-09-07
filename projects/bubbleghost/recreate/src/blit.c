/* blit.c — Bubble Ghost's RAW blitters: the `move.l (a3)+,(a2)+` copies and the 32x32 tile draw.
 *
 * Ten routines, one shape. Every one of them is a straight-line copy between two addresses the
 * program keeps in its own globals — the two screens `init_gem_and_screens` @ 0x10118 stores, and
 * the six GHOST.DAT banks `load_level_pictures` @ 0x1396c allocates — with no OS call in the body.
 * That is what makes them the first thing in this program a differential can run.
 *
 * The other drawing family is NOT here. `save_sprite_backgrounds` @ 0x1342e, `draw_sprites` @
 * 0x134f6 and `restore_sprite_backgrounds` @ 0x135d2 are three `vro_cpyfm` pairs each, and the
 * kit's TOS model refuses the VDI trap they reach; STATUS.md records them as residuals rather than
 * as reconstructions nobody ran.
 *
 * THREE OF THE TEN ARE SLICES of a routine whose remainder traps (docs/agent-playbook.md §5):
 * `build_sprite_bank_prepare` is the raw prefix of `build_sprite_bank` @ 0x132ec,
 * `draw_room_tile_to_stage` is one iteration of `draw_room_to_stage` @ 0x13a08 (whose loop reads
 * the mouse through the VDI once per tile), and `room_wipe_in_slide` is the whole slide loop of
 * `room_wipe_in` @ 0x13b1e (whose prologue and epilogue call the sound engine). Each is entered at
 * its own PC by the battery, so what is verified is exactly the raw part.
 */
#include "machine.h"

#include "blit.h"
#include "common.h"     /* LONG_BYTES, muls_ext_w, and the copy run every loop here is built of:
                         * copy_one_longword, UNROLLED_RUN and copy_longs_ascending */
#include "gameplay.h"   /* the object and room records these routines draw FROM */
#include "sound.h"      /* the three key-offs and the trigger `room_wipe_in` is wrapped in */

/* One `move.l (a3),(a2) / subq #4,a3 / subq #4,a2`. The copy comes FIRST and the two steps after
 * it, which is the ascending step's own shape mirrored — and it is what keeps each copy addressing
 * through a cursor rather than through the previous one's displacement. Written the other way round
 * (step, then copy) GCC spends `lea -4(a3),a1 / lea -4(a2),a0 / move.l -4(a3),-4(a2)` — 44 cycles a
 * longword against this shape's 36 — which gives back most of what the run came here for. */
static inline void copy_one_longword_descending(const uint8_t **from, uint8_t **to) {
    wr32(*to, be32(*from));
    *from -= LONG_BYTES;
    *to -= LONG_BYTES;
    CURSOR_BARRIER(*from);
    CURSOR_BARRIER(*to);
}

/* ...and the `move.l (a3),(a2) / subq.w #4,a3 / subq.w #4,a2` run `room_wipe_in` uses instead:
 * both cursors start at the LAST longword and walk down, which is what makes a move onto a span
 * overlapping four scanlines further on come out right. The three instructions are the original's
 * own; what this port saves is its `dbf`, amortised over COPY_RUN_UNROLL copies instead of paid per
 * longword. Why the cursors are barriered and the block spelt out is `include/common.h`'s. */
static void copy_longs_descending(uint8_t *image, uint32_t src, uint32_t dst, uint32_t longs) {
    const uint8_t *from = image + src;
    uint8_t *to = image + dst;

    UNROLLED_RUN(longs, copy_one_longword_descending(&from, &to));
}

/* THE TILE BLIT, and it is the same instructions in all four routines that draw one: 32 passes of
 * four `move.l`s — one 32-pixel four-plane row — with the source running on and the destination
 * stepping to the next scanline (`adda.w #$90` after the four auto-increments). The four are spelt
 * out rather than run through `copy_longs_ascending`, because a run of four is all loop control:
 * this is the whole of the row, and the loop closes around the row and not around a longword. The
 * row count is a WORD, which is what the original counts rows in (`move.w #$1f,d0`) and what makes
 * the close a `subq.w` (4 cycles) rather than a `subq.l` (8). It does NOT buy the original's `dbf`:
 * GCC 16.1 emits no `dbf` anywhere in this object, so the close is 14 cycles against its 10. */
static void blit_tile_32x32(uint8_t *image, uint32_t src, uint32_t dst) {
    const uint8_t *from = image + src;
    uint8_t *to = image + dst;
    uint16_t rows = TILE_PIXELS;

    _Static_assert(TILE_ROW_BYTES == 4 * LONG_BYTES, "a tile row is the original's four `move.l`s");
    COUNT_BARRIER(rows);
    do {
        copy_one_longword(&from, &to);
        copy_one_longword(&from, &to);
        copy_one_longword(&from, &to);
        copy_one_longword(&from, &to);
        to += TILE_ROW_DEST_STEP_BYTES;
        CURSOR_BARRIER(to);
    } while (--rows != 0);
}

static uint32_t screen_back(const uint8_t *image) { return be32(image + A_screen_back); }
static uint32_t screen_phys(const uint8_t *image) { return be32(image + A_screen_phys); }

/* dat_bank[index] — an ordinary `longword_slot`, so a bank number out of range wraps. */
static uint32_t dat_bank(const uint8_t *image, int16_t index) {
    return be32(image + longword_slot(A_dat_bank, index));
}

/* The GHOST.DAT tile `tile` lives at bank `tile / 60`, entry `tile % 60`. Both routines that draw a
 * tile named by a data table compute it with `divs.w #$3c` and a `muls`/`sub.w` back. */
static uint32_t tile_source(const uint8_t *image, int16_t tile) {
    int16_t bank = (int16_t)(tile / (int16_t)TILES_PER_BANK);
    int16_t entry = (int16_t)(tile - (int16_t)(bank * (int16_t)TILES_PER_BANK));
    return addr_add(dat_bank(image, bank), muls_ext_w(entry, (int32_t)TILE_BYTES));
}

/* ================================================================================================
 * The four whole-region copies. Each is one `dbf` loop over `move.l (a3)+,(a2)+` and nothing else;
 * what distinguishes them is which band of the screen the frame loop has just changed.
 * ============================================================================================= */

/* One `move.l #$0,(a3)+` — `clear_physical_screen`'s whole body, and this file's only fill. GCC
 * spells it `clr.l (a0)+`, which the 68000 reads before it writes: 20 cycles, the same as the
 * original's own `move.l #$0,(a3)+` and 8 more than a zero held in a register would cost. Parity
 * with the original is the target and this is a cold path, so the register is not worth the read. */
static inline void store_zero_longword(uint8_t **to) {
    wr32(*to, 0);
    *to += LONG_BYTES;
    CURSOR_BARRIER(*to);
}

/* clear_physical_screen @ 0x10efe — the visible screen only, and only the 192 rows a picture
 * covers. Called before the presentation and each text card. */
void clear_physical_screen(uint8_t *image) {
    uint8_t *to = image + screen_phys(image);

    UNROLLED_RUN(CLEARED_SCREEN_BYTES / LONG_BYTES, store_zero_longword(&to));
}

/* present_room @ 0x13286 — the whole room area, work buffer to screen, once per frame. */
void present_room(uint8_t *image) {
    copy_longs_ascending(image, screen_back(image), screen_phys(image), ROOM_BYTES / LONG_BYTES);
}

/* present_hud_row @ 0x13224 — the tile row below the room, once on entering a room. */
void present_hud_row(uint8_t *image) {
    copy_longs_ascending(image, addr_add(screen_back(image), ROOM_BYTES),
                         addr_add(screen_phys(image), ROOM_BYTES),
                         TILE_ROW_SCREEN_BYTES / LONG_BYTES);
}

/* present_score_strip @ 0x131f0 — just the band the counters sit in, after a score change. */
void present_score_strip(uint8_t *image) {
    copy_longs_ascending(image, addr_add(screen_back(image), SCORE_STRIP_OFFSET),
                         addr_add(screen_phys(image), SCORE_STRIP_OFFSET),
                         SCORE_STRIP_BYTES / LONG_BYTES);
}

/* stage_to_work @ 0x13258 — the staged room straight into the work buffer, with no wipe. The demo
 * player and the hall of fame use this where the game itself uses `room_wipe_in`. */
void stage_to_work(uint8_t *image) {
    uint32_t work = screen_back(image);
    copy_longs_ascending(image, addr_add(work, -ROOM_BYTES), work, ROOM_BYTES / LONG_BYTES);
}

/* ================================================================================================
 * The tile draws.
 * ============================================================================================= */

/* draw_tile_bank_screen @ 0x1369a — paint a whole 60-tile bank onto the work buffer as a 10 x 6
 * grid. The source cursor is never reset, so the tiles land in bank order; `build_sprite_bank`
 * relies on that to grab each cell back by position. */
void draw_tile_bank_screen(uint8_t *image) {
    uint32_t src = dat_bank(image, (int16_t)be16(image + A_bank_index));
    uint32_t work = screen_back(image);

    for (int16_t tile_row = 0; tile_row < (int16_t)BANK_TILE_ROWS; tile_row++) {
        for (int16_t tile_col = 0; tile_col < (int16_t)ROOM_TILE_COLS; tile_col++) {
            uint32_t dst = addr_add(work, muls_ext_w(tile_col, (int32_t)TILE_ROW_BYTES));
            dst = addr_add(dst, muls_ext_w(tile_row, (int32_t)TILE_ROW_SCREEN_BYTES));
            blit_tile_32x32(image, src, dst);
            src = addr_add(src, TILE_BYTES);
        }
    }
}

/* draw_hud_row_tiles @ 0x13712 — the ten fixed HUD tiles into the row below the room. */
void draw_hud_row_tiles(uint8_t *image) {
    uint32_t src = addr_add(dat_bank(image, (int16_t)HUD_TILE_BANK),
                            HUD_FIRST_TILE_IN_BANK * TILE_BYTES);
    uint32_t work = screen_back(image);

    for (int16_t tile_col = 0; tile_col < (int16_t)ROOM_TILE_COLS; tile_col++) {
        uint32_t dst = addr_add(work, muls_ext_w(tile_col, (int32_t)TILE_ROW_BYTES));
        blit_tile_32x32(image, src, addr_add(dst, ROOM_BYTES));
        src = addr_add(src, TILE_BYTES);
    }
}

/* objects_animate_and_draw @ 0x1376e — tick and redraw the current room's ten object slots, every
 * frame, straight into the work buffer. An object is therefore part of the background as far as the
 * sprite save/restore and the collision probe are concerned (../notes/gameplay.md, §4 and §6). */
void objects_animate_and_draw(uint8_t *image) {
    int16_t room = (int16_t)be16(image + A_room_number);
    uint32_t room_objects = addr_add(A_object_table,
                                     (uint32_t)((int32_t)room * (int32_t)OBJECT_ROOM_STRIDE));
    uint32_t work = screen_back(image);

    for (int16_t slot = 0; slot < (int16_t)OBJECT_SLOTS; slot++) {
        uint32_t object = addr_add(room_objects,
                                   sign_ext16((uint32_t)(slot * (int32_t)OBJECT_STRIDE)));
        if ((int16_t)be16(image + object + OBJECT_TILE) < 0)
            continue;                                   /* -1 = an empty slot */

        /* The countdown is decremented on every frame the slot is live, and the frame steps on the
         * frame whose PRE-decrement value was already 0 — so a reload of n shows a new frame every
         * n+1 frames, and a reload of 0 every frame. The -1 the decrement leaves behind is
         * immediately overwritten by the reload, which is why only the reload is stored here. */
        int16_t countdown = (int16_t)be16(image + object + OBJECT_COUNTDOWN);
        wr16(image + object + OBJECT_COUNTDOWN, (uint16_t)(countdown - 1));
        if (countdown != 0)
            continue;
        wr16(image + object + OBJECT_COUNTDOWN, be16(image + object + OBJECT_RELOAD));

        int16_t frame = (int16_t)be16(image + object + OBJECT_FRAME);
        wr16(image + object + OBJECT_FRAME, (uint16_t)(frame + 1));
        if (frame == (int16_t)(be16(image + object + OBJECT_FRAME_COUNT) - 1))
            wr16(image + object + OBJECT_FRAME, 0);

        /* The tile drawn is base + the frame JUST stored, so a slot that wrapped draws frame 0. */
        uint32_t src = tile_source(image, (int16_t)be16(image + object + OBJECT_TILE));
        src = addr_add(src, muls_ext_w((int16_t)be16(image + object + OBJECT_FRAME),
                                       (int32_t)TILE_BYTES));

        uint32_t dst = addr_add(work, muls_ext_w((int16_t)be16(image + object + OBJECT_X),
                                                 (int32_t)TILE_ROW_BYTES));
        dst = addr_add(dst, muls_ext_w((int16_t)be16(image + object + OBJECT_Y),
                                       (int32_t)TILE_ROW_SCREEN_BYTES));
        blit_tile_32x32(image, src, dst);
    }
}

/* ================================================================================================
 * The three slices.
 * ============================================================================================= */

/* One 32x32 cell of the MFDB pair build_sprite_bank hands to `vro_cpyfm` for every grab. */
static void set_sprite_cell_mfdb(uint8_t *image, uint32_t mfdb) {
    wr16(image + mfdb + MFDB_WIDTH, TILE_PIXELS);
    wr16(image + mfdb + MFDB_HEIGHT, TILE_PIXELS);
    wr16(image + mfdb + MFDB_WDWIDTH, MFDB_SPRITE_WDWIDTH);
    wr16(image + mfdb + MFDB_STANDARD, 0);
    wr16(image + mfdb + MFDB_PLANES, SCREEN_PLANES);
}

/* build_sprite_bank @ 0x132ec, its raw prefix [0x132ec, 0x13330): paint bank 0 over the work buffer
 * and describe a 32x32 cell to the VDI in both directions. The remainder — 60 iterations of
 * `c_malloc(512)` + `vro_cpyfm` grabbing one cell into it — is the VDI residual (STATUS.md). */
void build_sprite_bank_prepare(uint8_t *image) {
    wr16(image + A_bank_index, 0);          /* bank 0 = GHOST.DAT tiles 0..59: ghost and bubble */
    draw_tile_bank_screen(image);
    set_sprite_cell_mfdb(image, A_mfdb_src);
    set_sprite_cell_mfdb(image, A_mfdb_dst);
}

/* draw_room_to_stage @ 0x13a08, one iteration of its 5 x 10 loop, [0x13a38, 0x13afa): compose one
 * tile of the current room's map into the staging area a room's worth below the work buffer. The
 * loop's other statement is a `vq_mouse` per tile — this file's slice stops short of it, and
 * `src/frontend.c` composes the two into the whole routine.
 *
 * ANSWERS THE A2 IT LEAVES: the 32-row `move.l (a3)+,(a2)+` run ends exactly one tile band past the
 * destination, and the next cell's `vq_mouse` parks that in the trampoline's save slot. */
uint32_t draw_room_tile_to_stage(uint8_t *image, int16_t tile_row, int16_t tile_col) {
    int16_t room = (int16_t)be16(image + A_room_number);
    uint32_t map_row = addr_add(A_room_table,
                                (uint32_t)((int32_t)room * (int32_t)ROOM_STRIDE));
    map_row = addr_add(map_row, (uint32_t)((int32_t)tile_row * (int32_t)ROOM_MAP_ROW_BYTES));
    uint32_t cell = addr_add(map_row,
                             sign_ext16((uint32_t)(tile_col * (int32_t)ROOM_MAP_CELL_BYTES)));

    uint32_t src = tile_source(image, (int16_t)be16(image + cell));
    uint32_t dst = addr_add(screen_back(image), muls_ext_w(tile_col, (int32_t)TILE_ROW_BYTES));
    dst = addr_add(dst, muls_ext_w(tile_row, (int32_t)TILE_ROW_SCREEN_BYTES));
    dst = addr_add(dst, -(uint32_t)ROOM_BYTES);
    blit_tile_32x32(image, src, dst);
    return addr_add(dst, TILE_ROW_SCREEN_BYTES);
}

/* One step of room_wipe_in's slide: move the staged room down four scanlines, then present the
 * part of the work buffer it has reached.
 *
 * The original spells the two cursors `screen_back + 0x63fc + 640*step - 0x6400` and the same with
 * 0x667c — which is the LAST longword of the staged room at this step, and the last longword of
 * where it is going, one WIPE_STEP_BYTES further on. The copy runs down from there, so the move
 * onto its own overlapping span comes out right.
 *
 * THE PRESENT'S LONGWORD COUNT IS A WORD, and that is the one thing here a 32-bit reconstruction
 * gets wrong. The original builds it as `move.l #$a0,d0 / move.w d7,d1 / addq.w #1,d1 /
 * mulu.w d1,d0 / subq.w #1,d0 / dbf d0` — a 32-bit product, then a WORD decrement and a `dbf` that
 * reads only the low word. So a step at or above 409, where 160 * (step + 1) passes 0x10000, copies
 * the low word's worth and not the product's: step 409 moves 64 longwords rather than 65,600, and
 * step -1 (the word 0xffff, which makes the product zero) moves the full 65,536. */
void room_wipe_in_step(uint8_t *image, int16_t step) {
    uint32_t work = screen_back(image);
    uint32_t src_last = addr_add(addr_add(work, -LONG_BYTES),
                                 muls_ext_w(step, (int32_t)WIPE_STEP_BYTES));
    unsigned presented_longs = loop_passes((uint16_t)((WIPE_STEP_BYTES / LONG_BYTES)
                                                      * (uint16_t)(step + 1)),
                                           COUNT_MASK_WORD);

    copy_longs_descending(image, src_last, addr_add(src_last, WIPE_STEP_BYTES),
                          ROOM_BYTES / LONG_BYTES);
    copy_longs_ascending(image, work, screen_phys(image), presented_longs);
}

/* room_wipe_in @ 0x13b1e, its slide loop [0x13b62, 0x13bda): 40 steps of the above, so the room
 * arrives from the top over 160 scanlines. */
void room_wipe_in_slide(uint8_t *image) {
    for (int16_t step = 0; step < (int16_t)WIPE_STEPS; step++)
        room_wipe_in_step(image, step);
}

/* ...and the whole of `room_wipe_in` @ 0x13b1e around it: every voice is keyed off, the slide's own
 * sound is triggered, and the voice it used is released again at the end. It used to be this
 * subsystem's residual — the sound engine was unported — and what verifies the composition is
 * `src/frontend.c`'s room-setup slice, which is the only caller. */
void room_wipe_in(uint8_t *image) {
    for (int16_t voice = 0; voice < (int16_t)SND_VOICES; voice++)
        sound_release_voice(image, voice);
    sound_play(image, sound_fx_definition(SND_FX_ROOM_WIPE), WIPE_SFX_VOICE,
               (int16_t)(word_at(image, A_sound_enabled) * WIPE_SFX_VOLUME), WIPE_SFX_NOTE,
               WIPE_SFX_PRIORITY);
    room_wipe_in_slide(image);
    sound_release_voice(image, WIPE_SFX_VOICE);
}

/* ================================================================================================
 * Glue. Alcyon/DRI C passes arguments on the stack (test/abi.py), so the oracle side of a case
 * pokes them at 4(A7) and the candidate side is handed the same values as C arguments here.
 * ============================================================================================= */

void g_clear_physical_screen(uint8_t *image) { clear_physical_screen(image); }
void g_present_room(uint8_t *image) { present_room(image); }
void g_present_hud_row(uint8_t *image) { present_hud_row(image); }
void g_present_score_strip(uint8_t *image) { present_score_strip(image); }
void g_stage_to_work(uint8_t *image) { stage_to_work(image); }
void g_draw_tile_bank_screen(uint8_t *image) { draw_tile_bank_screen(image); }
void g_draw_hud_row_tiles(uint8_t *image) { draw_hud_row_tiles(image); }
void g_objects_animate_and_draw(uint8_t *image) { objects_animate_and_draw(image); }
void g_build_sprite_bank_prepare(uint8_t *image) { build_sprite_bank_prepare(image); }
void g_room_wipe_in_slide(uint8_t *image) { room_wipe_in_slide(image); }

/* The two slices whose entry PC is inside a loop: the loop variables the oracle is entered with are
 * the arguments here. `tile_row`/`tile_col` are the routine's -4(a6)/-2(a6); `step` is its D7. */
uint32_t g_draw_room_tile_to_stage(uint8_t *image, uint32_t tile_row, uint32_t tile_col) {
    return draw_room_tile_to_stage(image, (int16_t)tile_row, (int16_t)tile_col);
}

void g_room_wipe_in_step(uint8_t *image, uint32_t step) {
    room_wipe_in_step(image, (int16_t)step);
}
