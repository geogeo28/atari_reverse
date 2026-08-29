/* hud.c — the status panel's blits.
 *
 * The panel is the bottom 53 rows of the frame and is drawn into BOTH buffers, so the player sees
 * it whichever page the shifter is showing. Every routine here writes at an address its own
 * instructions carry as a literal, and none of them clips: the block goes where it goes.
 *
 * The graphics are bss (POWER.DAT, SMLOGOS.DAT, LIFEGRA.DAT, ZYNLOGO.DAT and the three strips
 * `_start` carves out of STATUS.PI1), so every test stages the real bytes — see hud.h.
 */
#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif

#include "machine.h"
#include "hud.h"
#include "highscore.h"
#include "irq.h"
#include "score.h"
#include "sound.h"
#include "text.h"
#include "video.h"

/* ================================================================================================
 * The shape all the panel blits share: `movem.l (src)+,<list>` once, then the same list stored into
 * each destination, and every destination steps a whole screen row.
 *
 * THE WHOLE ROW IS READ BEFORE ANY OF IT IS STORED, which is what `movem` does and what an
 * interleaved copy would not — the defect `blit_graphic_block`'s overlap cases caught (STATUS.md,
 * video). It is only observable when a destination overlaps the source, which these routines'
 * literal addresses never arrange; transcribed as written rather than as what a case can reach.
 * ============================================================================================= */
/* The two bounds this helper cannot express in its own signature, stated once and asserted below:
 * the panel is only ever drawn into the two framebuffers, and the widest `movem` list here is
 * `#$07fe`, ten longwords. Both are stack-array sizes, so an overrun would smash the candidate's
 * own frame rather than the emulated image — invisible to the byte diff AND to `make guarded`,
 * which bounds the image and not the host stack. */
#define PANEL_BLIT_DESTINATIONS 2u
#define PANEL_MAX_ROW_BYTES 40u

static void blit_rows_from_stream(uint8_t *image, uint32_t source, const uint32_t *destinations,
                                  unsigned destination_count, unsigned rows, unsigned row_bytes) {
    uint32_t cursor[PANEL_BLIT_DESTINATIONS];

#ifdef RECREATE_HOST_DIFFERENTIAL
    /* HOST-ONLY, the way the kit prescribes (kit.mk: "asserted where there is a process to abort").
     * An on-target build has nothing to abort into and no `__assert_fail` to call. */
    assert(destination_count <= PANEL_BLIT_DESTINATIONS && row_bytes <= PANEL_MAX_ROW_BYTES);
#endif
    for (unsigned i = 0; i < destination_count; i++)
        cursor[i] = destinations[i];
    for (unsigned row = 0; row < rows; row++) {
        uint8_t buffered[PANEL_MAX_ROW_BYTES];

        for (unsigned byte = 0; byte < row_bytes; byte++)
            buffered[byte] = image[addr_add(source, byte)];
        source = addr_add(source, row_bytes);
        for (unsigned i = 0; i < destination_count; i++) {
            for (unsigned byte = 0; byte < row_bytes; byte++)
                image[addr_add(cursor[i], byte)] = buffered[byte];
            cursor[i] = addr_add(cursor[i], SCREEN_ROW_BYTES);
        }
    }
}

/* Both framebuffers at the same panel offset, in the order the panel routines store them: the back
 * buffer first. */
static void panel_destinations(uint32_t offset, uint32_t *destinations) {
    destinations[0] = addr_add(A_screen_back_buffer, offset);
    destinations[1] = addr_add(A_screen_front_buffer, offset);
}

/* One of the three panel strips stamped into ONE buffer at `offset`, and the address it went to —
 * which the player strip needs, because the shifted digit lands on the bytes just written. */
static uint32_t stamp_panel_strip(uint8_t *image, uint32_t buffer, uint32_t source, uint32_t offset,
                                  unsigned row_bytes) {
    uint32_t destination = addr_add(buffer, offset);

    blit_rows_from_stream(image, source, &destination, 1, PANEL_STRIP_ROWS, row_bytes);
    return destination;
}

/* `move.l (aN)+,(aM)+` in a `dbf` loop, which the panel does in two places: snapshotting the built
 * panel to its master and installing the front end's palette. The cursor wraps in 32 bits the way
 * the 68000's address ALU does. (`src/scroll.c`'s `copy_longs` is the same loop, but `static` to
 * that file; the shared home for it is the kit's machine.h — see STATUS.md.) */
static void copy_longwords(uint8_t *image, uint32_t source, uint32_t destination,
                           unsigned longwords) {
    for (unsigned i = 0; i < longwords; i++) {
        wr32(image + destination, be32(image + source));
        source = addr_add(source, sizeof(uint32_t));
        destination = addr_add(destination, sizeof(uint32_t));
    }
}

/* A pointer out of one of the two icon tables. The cursor byte is `ext.w`-ed before the `lsl.w #2`,
 * so a byte at or above 0x80 reads a longword BELOW the table — inside the .PRG's own text, where
 * the "pointer" is whatever instruction happens to sit there. Faithful; the game writes 0..4 and
 * 0..5. */
static uint32_t icon_frame(const uint8_t *image, uint32_t table, uint8_t cursor) {
    uint16_t entry = (uint16_t)(sign_ext8(cursor) * ICON_TABLE_ENTRY_BYTES);

    return be32(image + addr_add(table, sign_ext16(entry)));
}

/* ================================================================================================
 * hud_draw_logo_anim @ 0x1452c — the two-frame ZYNAPS logo at the panel's left edge
 * ============================================================================================= */

/* The frame byte is TOGGLED FIRST and then read back, so the frame drawn is the new one; and it is
 * re-masked with `and.b #$1` after the toggle, which matters because nothing else bounds the byte.
 *
 * The source is not one run of 40 bytes a row: it is five 8-byte columns 0x100 apart, each holding
 * its own 32 rows, and the blit interleaves them back into one screen row. So the frame is stored
 * column-major and the cursor steps by ONE cell (8 bytes) a row, not by the row's 40. */
void hud_draw_logo_anim(uint8_t *image) {
    uint32_t destinations[PANEL_BLIT_DESTINATIONS];
    uint32_t frame;

    image[A_panel_logo_frame] ^= 1u;
    frame = addr_add(A_smlogos_frames,
                     (image[A_panel_logo_frame] & (LOGO_ANIM_FRAMES - 1u)) * LOGO_ANIM_FRAME_BYTES);
    panel_destinations(LOGO_ANIM_OFFSET, destinations);
    for (unsigned row = 0; row < LOGO_ANIM_ROWS; row++) {
        uint8_t buffered[LOGO_ANIM_CELLS * LOGO_ANIM_CELL_BYTES];

        /* THE WHOLE ROW IS GATHERED BEFORE EITHER STORE, exactly as the file's other blits do it:
         * the original reads all ten longwords into D1-D7/A3-A5 and only then runs its two
         * `movem.l #$38fe` stores. Only an overlapping destination could tell the two apart, and
         * these addresses are literals — but the interleaved form is what the reconstruction of
         * `blit_graphic_block` got wrong once, so it is not left to a reader to re-derive. */
        for (unsigned cell = 0; cell < LOGO_ANIM_CELLS; cell++) {
            uint32_t source = addr_add(frame, cell * LOGO_ANIM_CELL_STRIDE);

            for (unsigned byte = 0; byte < LOGO_ANIM_CELL_BYTES; byte++)
                buffered[cell * LOGO_ANIM_CELL_BYTES + byte] = image[addr_add(source, byte)];
        }
        for (unsigned i = 0; i < PANEL_BLIT_DESTINATIONS; i++) {
            for (unsigned byte = 0; byte < sizeof buffered; byte++)
                image[addr_add(destinations[i], byte)] = buffered[byte];
            destinations[i] = addr_add(destinations[i], SCREEN_ROW_BYTES);
        }
        frame = addr_add(frame, LOGO_ANIM_CELL_BYTES);
    }
}

/* Register map: none — the routine takes no argument and clobbers D0/A0-A2. */
void g_hud_draw_logo_anim(uint8_t *image) {
    hud_draw_logo_anim(image);
}

/* ================================================================================================
 * hud_draw_powerup_icon @ 0x1459c — the 32x26 icon the power-up bar's cursor selects
 * ============================================================================================= */

void hud_draw_powerup_icon(uint8_t *image) {
    uint32_t destinations[PANEL_BLIT_DESTINATIONS];
    uint32_t frame = icon_frame(image, A_hud_powerup_icons, image[A_powerup_cursor]);

    panel_destinations(POWERUP_ICON_OFFSET, destinations);
    blit_rows_from_stream(image, frame, destinations, PANEL_BLIT_DESTINATIONS, POWERUP_ICON_ROWS,
                          POWERUP_ICON_ROW_BYTES);
}

/* Register map: none in, D0/D1-D4/D7/A0-A2 clobbered. */
void g_hud_draw_powerup_icon(uint8_t *image) {
    hud_draw_powerup_icon(image);
}

/* ================================================================================================
 * hud_draw_weapon_icon @ 0x145da — the 16x18 weapon glyph, in the left or the right cell
 * ============================================================================================= */

/* D0 chooses the cell and is then OVERWRITTEN by the icon index, which is why the argument is only
 * tested for zero: `tst.b d0` before the load. */
void hud_draw_weapon_icon(uint8_t *image, uint8_t right_cell) {
    uint32_t offset = WEAPON_ICON_OFFSET + (right_cell ? WEAPON_ICON_RIGHT_CELL_BYTES : 0u);
    uint32_t destinations[PANEL_BLIT_DESTINATIONS];
    uint32_t frame = icon_frame(image, A_hud_weapon_icons, image[A_powerup_active_slot]);

    panel_destinations(offset, destinations);
    blit_rows_from_stream(image, frame, destinations, PANEL_BLIT_DESTINATIONS, WEAPON_ICON_ROWS,
                          WEAPON_ICON_ROW_BYTES);
}

/* Register map: D0.b = the cell (0 = left at x=128, nonzero = right at x=160). Only the low BYTE is
 * tested, so junk above it cannot move the glyph. */
void g_hud_draw_weapon_icon(uint8_t *image, uint32_t cell_reg) {
    hud_draw_weapon_icon(image, (uint8_t)cell_reg);
}

/* ================================================================================================
 * draw_power_gauge @ 0x137ca — one of four 64x8 POWER.DAT frames, by shield level
 * ============================================================================================= */

/* THE CLAMP IS A SIGNED BYTE COMPARE and it WRITES THE LEVEL BACK, so a level of 4 or more is both
 * drawn as 3 and stored as 3. A level with bit 7 set is negative and so passes the `blt` unclamped,
 * which indexes 0x100 bytes below the frames for every step below zero — the game's own writer
 * keeps the byte in 0..4, and test_hud.py says which values leave the image.
 *
 * This is also the one panel routine that reads the buffer POINTERS rather than carrying the
 * buffers as literals. */
void draw_power_gauge(uint8_t *image) {
    uint32_t destinations[PANEL_BLIT_DESTINATIONS];
    uint16_t level;
    uint32_t frame;

    if ((int8_t)image[A_power_gauge_display] >= (int8_t)POWER_GAUGE_FRAMES)
        image[A_power_gauge_display] = POWER_GAUGE_FRAMES - 1u;
    /* `ext.w` then `mulu.w`: the product is UNSIGNED 16x16, so a negative level scales its own low
     * word and the frame lands 0xff.... bytes on rather than below the table. */
    level = (uint16_t)sign_ext8(image[A_power_gauge_display]);
    frame = addr_add(A_power_gauge_frames, (uint32_t)level * POWER_GAUGE_FRAME_BYTES);
    destinations[0] = addr_add(be32(image + A_screen_back), POWER_GAUGE_OFFSET);
    destinations[1] = addr_add(be32(image + A_screen_front), POWER_GAUGE_OFFSET);
    blit_rows_from_stream(image, frame, destinations, PANEL_BLIT_DESTINATIONS, POWER_GAUGE_ROWS,
                          POWER_GAUGE_ROW_BYTES);
}

/* Register map: none in; D0/D1-D7/A0/A1/A5/A6 clobbered. */
void g_draw_power_gauge(uint8_t *image) {
    draw_power_gauge(image);
}

/* ================================================================================================
 * draw_lives_icons @ 0x134ca — six slots at row 167, full while the player still has the life
 * ============================================================================================= */

/* The two glyphs are back to back in LIFEGRA.DAT and both are 8 rows of four plane bytes. Which one
 * a slot draws is a SIGNED BYTE compare of `lives - 1` against the slot's 1-based number, so slot i
 * is full while lives >= i + 2 and a `lives` of 0 leaves every slot empty (0 - 1 = -1). */
static uint32_t life_icon_for_slot(uint8_t lives, unsigned slot) {
    int8_t remaining = (int8_t)(lives - 1u);
    int8_t slot_number = (int8_t)(slot + 1u);

    return remaining < slot_number ? A_life_icons + LIFE_ICON_BYTES : A_life_icons;
}

/* One 8x8 icon into BOTH buffers at once, from one read of each source byte: `move.b (a1),(a0)` and
 * the three planes after it write the front buffer, then the same four bytes go to the back with
 * `(a1)+`. A byte per plane, the planes two apart. */
static void blit_life_icon(uint8_t *image, uint32_t source, uint32_t front, uint32_t back) {
    for (unsigned row = 0; row < LIFE_ICON_ROWS; row++) {
        for (unsigned plane = 0; plane < SCREEN_PLANES; plane++) {
            uint8_t bits = image[addr_add(source, plane)];

            image[addr_add(front, plane * PLANE_STRIDE)] = bits;
            image[addr_add(back, plane * PLANE_STRIDE)] = bits;
        }
        source = addr_add(source, LIFE_ICON_ROW_BYTES);
        front = addr_add(front, SCREEN_ROW_BYTES);
        back = addr_add(back, SCREEN_ROW_BYTES);
    }
}

/* A0 (the front buffer's row) and A2 (the back's) are SAVED AND RESTORED around each slot, so every
 * slot's cell is computed from the row base rather than from where the last one left off — which is
 * why the column is what advances between slots and the pointers are not. */
void draw_lives_icons(uint8_t *image) {
    uint32_t front_row = addr_add(A_screen_front_buffer, LIVES_ROW_OFFSET);
    uint32_t back_row = addr_add(A_screen_back_buffer, LIVES_ROW_OFFSET);
    uint8_t lives = image[A_lives];

    for (unsigned slot = 0; slot < LIVES_ICONS; slot++) {
        uint16_t column = (uint16_t)(LIVES_FIRST_COLUMN + slot);

        blit_life_icon(image, life_icon_for_slot(lives, slot),
                       text_cell_address(front_row, column), text_cell_address(back_row, column));
    }
    image[A_panel_redraw_mask] &= (uint8_t)~(1u << PANEL_REDRAW_LIVES_BIT);
}

/* Register map: none in; D1 walks the column and D3/D5/D6/D7 and A0-A2 are all clobbered. */
void g_draw_lives_icons(uint8_t *image) {
    draw_lives_icons(image);
}

/* ================================================================================================
 * draw_player_digit_shifted @ 0x13568 — the panel's player number, half a cell to the right
 * ============================================================================================= */

/* WORD OPERATIONS, NOT BYTE ONES, and that is the whole reason this exists beside draw_char: the
 * glyph is rotated PLAYER_DIGIT_SHIFT pixels inside a 16-pixel group, so it straddles two character
 * cells and each plane is read-modified-written a word at a time.
 *
 * The mask word starts at 0xffff rather than 0: `move.w #$ffff,d1` and then the glyph's AND byte
 * over its low half, so after the rotate the four pixels the glyph does not cover are ones and the
 * background there survives. The plane words start from `clr.w`, so their rotate brings in zeroes.
 *
 * The glyph index is `player + 1` as a BYTE add before the `ext.w`, so a player index of 0xff draws
 * glyph 0 rather than glyph 0x100. */
void draw_player_digit_shifted(uint8_t *image, uint32_t cell) {
    uint16_t glyph = (uint16_t)sign_ext8((uint8_t)(image[A_current_player_index]
                                                   + PLAYER_DIGIT_GLYPH_BIAS));
    uint32_t source = addr_add(A_font_glyphs, (uint32_t)glyph * GLYPH_BYTES);

    for (unsigned row = 0; row < GLYPH_ROWS; row++) {
        uint16_t mask = rotate_left16((uint16_t)(0xff00u | image[source]), PLAYER_DIGIT_SHIFT);

        source = addr_add(source, 1);
        for (unsigned plane = 0; plane < SCREEN_PLANES; plane++) {
            uint16_t bits = rotate_left16(image[source], PLAYER_DIGIT_SHIFT);

            source = addr_add(source, 1);
            wr16(image + cell, (uint16_t)(be16(image + cell) & mask));
            wr16(image + cell, (uint16_t)(be16(image + cell) | bits));
            cell = addr_add(cell, PLANE_STRIDE);
        }
        cell = addr_add(cell, PLAYER_DIGIT_ROW_ADVANCE);
    }
}

/* Register map: A0 = the word-aligned cell the digit's top-left plane lands in. A0 is NOT restored —
 * it comes back eight rows down — but both call sites reload it with their own `lea`. */
void g_draw_player_digit_shifted(uint8_t *image, uint32_t cell) {
    draw_player_digit_shifted(image, cell);
}

/* ================================================================================================
 * draw_score_panel @ 0x136c8 — the SCORE strip and the eight digits beside it
 * ============================================================================================= */

/* IT HAS NO `rts` OF ITS OWN: the routine sets up draw_bcd_number's arguments and runs off its own
 * end into it at 0x136f6, so the digits below are drawn by a fall-through rather than by a `bsr`. */
void draw_score_panel(uint8_t *image, uint32_t buffer) {
    stamp_panel_strip(image, buffer, A_score_panel_strip, SCORE_STRIP_OFFSET,
                      PANEL_STRIP_ROW_BYTES);
    draw_bcd_number(image, addr_add(buffer, SCORE_DIGITS_OFFSET), SCORE_RIGHTMOST_COLUMN,
                    be32(image + A_player_score_bcd));
}

/* Register map: A6 = the screen buffer to draw into. */
void g_draw_score_panel(uint8_t *image, uint32_t buffer) {
    draw_score_panel(image, buffer);
}

/* ================================================================================================
 * status_panel_build_master @ 0x129aa — stamp the three strips, then snapshot the whole panel
 * ============================================================================================= */

/* THE BUFFER IS THE `lea $78000` LITERAL, not either pointer: this runs once inside `_start`, and
 * its real output is the 8480-byte master at A_panel_master that every later repaint stamps back.
 *
 * The player strip is copied with two `move.l`s a row where the other two use a `movem`, which is
 * the same eight bytes; the two differ only if source and destination overlap, and every one of
 * these six addresses is a literal, so no case can arrange that. */
void status_panel_build_master(uint8_t *image) {
    stamp_panel_strip(image, A_screen_front_buffer, A_score_panel_strip, SCORE_STRIP_OFFSET,
                      PANEL_STRIP_ROW_BYTES);
    stamp_panel_strip(image, A_screen_front_buffer, A_player_panel_strip, PLAYER_STRIP_OFFSET,
                      PLAYER_STRIP_ROW_BYTES);
    stamp_panel_strip(image, A_screen_front_buffer, A_hiscore_panel_strip, HISCORE_STRIP_OFFSET,
                      PANEL_STRIP_ROW_BYTES);
    copy_longwords(image, addr_add(A_screen_front_buffer, PANEL_TOP_OFFSET), A_panel_master,
                   PANEL_MASTER_LONGWORDS);
}

/* Register map: none in; D0 and A0-A4 clobbered. */
void g_status_panel_build_master(uint8_t *image) {
    status_panel_build_master(image);
}

/* ================================================================================================
 * status_panel_redraw_all @ 0x135bc — the whole panel, in both buffers
 * ============================================================================================= */

/* One buffer's PLAYER strip and the shifted digit over it. The strip goes in with two `move.l`s a
 * row and the digit lands on the same eight bytes, so the ORDER is load-bearing: strip first.
 *
 * `buffer` IS A LITERAL AT EVERY CALL SITE, and that is the routine and not a convenience: the two
 * strip blits are `lea $7f238.l,a0` @ 0x135ca and `lea $77538.l,a0` @ 0x135f2, and so are the two
 * `lea`s that follow them into the digit. The hi-score strip four instructions later does read the
 * pointer (`movea.l $17982.l,a3` @ 0x13620), so `status_panel_redraw_all` genuinely mixes the two
 * — which is why this takes a buffer argument rather than reading one. */
static void redraw_player_strip(uint8_t *image, uint32_t buffer) {
    uint32_t strip = stamp_panel_strip(image, buffer, A_player_panel_strip, PLAYER_STRIP_OFFSET,
                                       PLAYER_STRIP_ROW_BYTES);

    draw_player_digit_shifted(image, strip);
}

/* ...and the same for the HI-SCORE strip and the eight digits beside it. */
static void redraw_hiscore_strip(uint8_t *image, uint32_t buffer) {
    stamp_panel_strip(image, buffer, A_hiscore_panel_strip, HISCORE_STRIP_OFFSET,
                      PANEL_STRIP_ROW_BYTES);
    draw_bcd_number(image, addr_add(buffer, HISCORE_DIGITS_OFFSET), HIGHSCORE_DIGITS_COLUMN,
                    be32(image + A_highscore_table));
}

/* Everything the panel shows, into whichever buffer each piece belongs in.
 *
 * HALF ITS PIECES READ THE BUFFER POINTERS AND HALF CARRY A BUFFER AS A LITERAL, and the split is
 * not tidy: the score panel and the hi-score strip take theirs from 0x1797e/0x17982, while the
 * PLAYER strip and the logo/icon/lives blits all address absolute RAM. So the two locals below
 * serve only the pieces that really read the pointers, and `redraw_player_strip` is handed the
 * literal bases instead.
 *
 * THE SCORE PANEL IS DRAWN TWICE INTO THE FRONT BUFFER, once at the top and once at the end, and
 * that is the routine rather than a transcription slip: the front buffer's copy goes in before the
 * logo and icon blits and again after them. The last call is a FALL-THROUGH into draw_score_panel
 * with A6 = the back buffer, so the routine has no `rts` of its own — draw_bcd_number's is its.
 *
 * The weapon glyph is drawn in both cells by setting the slot byte around each call: the RIGHT cell
 * with slot 0, then the LEFT cell with slot 1. Both writes to that byte are the routine's own
 * output and are in the diff.
 */
void status_panel_redraw_all(uint8_t *image) {
    uint32_t front = be32(image + A_screen_front);
    uint32_t back = be32(image + A_screen_back);

    draw_power_gauge(image);
    draw_score_panel(image, front);
    redraw_player_strip(image, A_screen_front_buffer);
    redraw_player_strip(image, A_screen_back_buffer);
    redraw_hiscore_strip(image, front);
    redraw_hiscore_strip(image, back);
    hud_draw_logo_anim(image);
    hud_draw_powerup_icon(image);
    image[A_powerup_active_slot] = 0;
    hud_draw_weapon_icon(image, 1);
    draw_lives_icons(image);
    image[A_powerup_active_slot] = 1;
    hud_draw_weapon_icon(image, 0);
    draw_score_panel(image, front);
    draw_score_panel(image, back);
}

/* Register map: none in; everything is clobbered. `draw_power_gauge` re-reads the two pointers
 * itself, so the ones cached here are only for the pieces that take a buffer. */
void g_status_panel_redraw_all(uint8_t *image) {
    status_panel_redraw_all(image);
}

/* ================================================================================================
 * The front-end screens
 * ============================================================================================= */

/* `movem.l $195f8,#$00ff` then `movem.l #$00ff,$19f46`: the front end's sixteen pens copied into
 * the shadow the menu VBL uploads, eight longwords at a time. Every screen that ends by showing
 * itself does this — the intro here, and both high-score screens. */
static void install_frontend_palette(uint8_t *image) {
    copy_longwords(image, A_palette_frontend, A_menu_palette, SHIFTER_PALETTE_PAIRS);
}

/* The ZYNAPS logo's three strips. `blit_graphic_block` advances A6 by exactly one strip, and the
 * original loads A6 ONCE and lets the three calls chain — so strip i's source is the logo plus i
 * strips, which is what this computes instead of threading a cursor back out of the blit. */
void hud_blit_zynaps_logo(uint8_t *image, uint32_t buffer, uint32_t offset) {
    for (unsigned strip = 0; strip < LOGO_STRIPS; strip++)
        blit_graphic_block(image, addr_add(A_zynaps_logo, strip * LOGO_STRIP_BYTES),
                           addr_add(buffer, offset + strip * GRAPHIC_BLOCK_ROW_BYTES),
                           LOGO_STRIP_LAST_ROW);
}

/* ================================================================================================
 * player_intro_screen @ 0x13426 — PLAYER n, and PREPARE FOR COMBAT when the flag is set
 * ============================================================================================= */

/* THE DIGIT'S COLUMN IS draw_text_record's LEFTOVER. The record returns with D1 one column past its
 * last character and nothing reloads it, so "PLAYER" is followed by its number at exactly the
 * column the text ran out at — which is why the reconstruction has to take the column back from the
 * record rather than name one.
 *
 * The character is `player + 0x31`, added as a BYTE and then `ext.w`-ed, so a player index of 0xcf
 * or above wraps into the control characters draw_char forks on.
 */
void player_intro_screen(uint8_t *image) {
    uint32_t buffer = be32(image + A_screen_back);
    uint16_t column;

    sound_reset_psg(image);
    playfield_clear(image);
    wr16(image + A_palette_hw_shadow, 0);
    hud_blit_zynaps_logo(image, buffer, LOGO_INTRO_OFFSET);
    draw_text_record(image, buffer, A_msg_player, &column);
    draw_char(image, addr_add(buffer, PLAYER_NAME_ROW_OFFSET), column,
              (uint16_t)sign_ext8((uint8_t)(image[A_current_player_index]
                                            + PLAYER_DIGIT_CHAR_ZERO)));
    if (image[A_show_prepare_for_combat])
        draw_text_record(image, buffer, A_msg_prepare_for_combat, NULL);
    screen_flip_buffers(image);
    install_frontend_palette(image);
}

/* Register map: none in; everything is clobbered. */
void g_player_intro_screen(uint8_t *image) {
    player_intro_screen(image);
}

/* ================================================================================================
 * title_screen_draw @ 0x12a28 — the logos, the four credits and the 1/2-player menu
 * ============================================================================================= */

/* The Hewson logo is drawn from the SAME A6 the ZYNAPS strips left behind: three 64-row strips
 * exhaust ZYNLOGO.DAT and the next two 24-row ones fall into HEWLOGO.DAT, which `_start` loads
 * immediately after it. Spelt as its own address here (hud.h says why they are the same number).
 */
void title_screen_draw(uint8_t *image) {
    static const uint32_t credits[] = {
        A_msg_converted_by_microwish, A_msg_coding_howie, A_msg_graphics_pete_lyon,
        A_msg_music_and_sound_fx, A_msg_menu_one_or_two_players,
    };
    uint32_t buffer = be32(image + A_screen_back);

    screen_clear(image, buffer);
    hud_blit_zynaps_logo(image, buffer, LOGO_TITLE_OFFSET);
    for (unsigned strip = 0; strip < HEWSON_LOGO_STRIPS; strip++)
        blit_graphic_block(image, addr_add(A_hewson_logo, strip * HEWSON_STRIP_BYTES),
                           addr_add(buffer, HEWSON_LOGO_OFFSET
                                            + strip * GRAPHIC_BLOCK_ROW_BYTES),
                           HEWSON_STRIP_LAST_ROW);
    for (unsigned i = 0; i < sizeof credits / sizeof credits[0]; i++)
        draw_text_record(image, buffer, credits[i], NULL);
    screen_flip_buffers(image);
}

/* Register map: none in; everything is clobbered. */
void g_title_screen_draw(uint8_t *image) {
    title_screen_draw(image);
}
