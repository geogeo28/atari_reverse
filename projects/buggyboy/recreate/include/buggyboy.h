/* buggyboy.h — reconstruction cores + their image glue.
 *
 * Each function has two parts:
 *   - a *core* that works on idiomatic C types (the readable reconstruction);
 *   - a *glue* g_<name>(image, regs...) that unpacks the core's inputs from the flat
 *     image at their real addresses, calls the core, and lets it write back. The glue
 *     is the function's I/O contract; the differential harness diffs the whole image.
 */
#ifndef BB_BUGGYBOY_H
#define BB_BUGGYBOY_H

#include <stdint.h>

/* ---- score (add_score @ 0x1580a) ---- */
#define SCORE_DIGITS 6
void score_add(uint8_t *score, char *score_str, const uint8_t *delta, int game_over);
void g_add_score(uint8_t *image, uint32_t delta_ptr);            /* A1 -> 6-byte delta */

/* ---- screen fills (clear_screen @ 0x12e38, fill_span/fill_rect chain @ 0x12e56..) ---- */
#define SCREEN_BYTES   32000        /* 320x200x4bpp: 2000 * 16-byte writes */
#define FILL_CELL      8            /* one 16-pixel, 4-plane colour cell; also color_pairs stride */
#define SCREEN_CELLS   (SCREEN_BYTES / FILL_CELL)  /* 4000: whole draw buffer in fill cells */
#define ROW_STRIDE     160          /* bytes per scanline (0xa0) */
void screen_clear(uint8_t *buf);
void screen_fill_span(uint8_t *dst, const uint8_t *pattern, unsigned cells);
void screen_fill_rect(uint8_t *dst, const uint8_t *pattern, unsigned cells, unsigned rows);
void g_clear_screen(uint8_t *image);
void g_fill_screen(uint8_t *image, uint32_t color_index);       /* D1 colour */
void g_fill_words(uint8_t *image, uint32_t color_index, uint32_t cell_count_m1);   /* D1, D2 */
void g_fill_span(uint8_t *image, uint32_t dst_offset, uint32_t color_index, uint32_t cell_count_m1);
void g_fill_rect(uint8_t *image, uint32_t dst_offset, uint32_t color_index,
                 uint32_t cells_m1, uint32_t rows_m1);           /* D0, D1, D3, D4 */

/* ---- text glyph blitters (shared body @ 0x5a2c; draw_text/_row, draw_hud_gauge0/_bar) ----
 * The string is character *pairs*; each pair packs two 1bpp FONT_GLYPHS entries into one
 * 8-byte, 4-plane cell (char1's word: hi->mask, lo->ink; char2's two row bytes likewise).
 * A 0 first byte ends the string; a 0 second byte draws one final cell then stops. The four
 * entries differ only in which inputs are preset:
 *   draw_text       D0 dst offset (+buffer), D1 colour, A3 string; count preset to 0x13
 *   draw_text_row   as draw_text but D5 supplies the cell count-1
 *   draw_hud_gauge0 A0 absolute dst, D1 colour, D5 count-1, A3 string
 *   draw_hud_bar    A0 absolute dst, D2/D3 fill preset, A3 string; count preset to 0x13 */
#define TEXT_CELL_ROWS  8       /* rows blitted per character cell */
void g_draw_text(uint8_t *image, uint32_t dst_off, uint32_t color_idx, uint32_t str_ptr);
void g_draw_text_row(uint8_t *image, uint32_t dst_off, uint32_t color_idx,
                     uint32_t cells_m1, uint32_t str_ptr);
void g_draw_hud_gauge0(uint8_t *image, uint32_t dst, uint32_t color_idx,
                       uint32_t cells_m1, uint32_t str_ptr);
void g_draw_hud_bar(uint8_t *image, uint32_t dst, uint32_t fill_lo, uint32_t fill_hi, uint32_t str_ptr);
/* draw_text returning the advanced A3 (past the 0-pair terminator), for callers chaining labels. */
uint32_t draw_text_chain(uint8_t *image, uint32_t dst_off, uint32_t color_idx, uint32_t str_ptr);

/* ---- number blitter (draw_num @ 0x15a86) ---- Digits are single string bytes (0 ends it);
 * each digit's 15-row sprite is pre-rendered into buf_c and indexed by num_glyph_tbl. Colour
 * is NOT masked to 0xf (unlike text). draw_num_thunk presets the cell count to 0x13. */
void g_draw_num(uint8_t *image, uint32_t dst_off, uint32_t color_idx,
                uint32_t cells_m1, uint32_t str_ptr);       /* D0, D1, D5, A3 */
void g_draw_num_thunk(uint8_t *image, uint32_t dst_off, uint32_t color_idx, uint32_t str_ptr);

/* ---- results-screen block blitters (draw_result_row/col @ 0x15016..) ----
 * Both copy a source block from buf_c (A1 offset) to buffer[flip_idx] + D0; no colour index.
 * col tiles a 7-row 16-byte column 5x across; row stacks a 32-row 4-word transparency blit
 * 3x down (mask = D & ~(A|B|C) from the four source words). */
void g_draw_result_row(uint8_t *image, uint32_t dst_off, uint32_t src_off);   /* D0, A1 */
void g_draw_result_col(uint8_t *image, uint32_t dst_off, uint32_t src_off);   /* D0, A1 */
void g_draw_dashboard(uint8_t *image, uint32_t dst_off);                      /* D0; src = buf_c fixed */
void g_init_leg_dash(uint8_t *image);                                         /* builds per-leg dashboard graphic; no args */
void g_draw_leg_results(uint8_t *image);                                      /* leg-results screen; no args */

/* ---- intermission-screen block blitter (intermission_poll @ 0x12914) ----
 * Table-driven plain block copy of 9 rectangles from buf_c to the draw buffer (no input, despite
 * the name); the misclassification is noted in HARNESS.md. */
void g_intermission_poll(uint8_t *image);

/* ---- masked buggy / foreground sprites (draw_fg_sprite .. draw_buggy @ 0x1518a..) ----
 * draw_buggy_wheels is the shared blit body: A0 dst, A1 src (into buf_c), D4 rows-1; each row
 * is 4 transparency cells, dst/src stepping one scanline up per row. */
void g_draw_buggy_wheels(uint8_t *image, uint32_t dst, uint32_t src, uint32_t rows_m1);
void g_draw_fg_sprite(uint8_t *image);   /* foreground buggy sprite; spin/curve gate + anim table */
void g_draw_buggy_lo(uint8_t *image, uint32_t buffer);   /* A6 = draw buffer; lower body, 2 sub-sprites */
void g_draw_buggy_hi(uint8_t *image, uint32_t dst_base); /* A2 = dst base; lean overlay (OR-blit) */

/* ---- divider + text panels (draw_divider @ 0x126e6, draw_panel2/3/5 @ 0x1271c..) ----
 * draw_divider = filled rect + two vertical lines. Each panel draws the divider then a fixed
 * set of labels from one concatenated ASCII buffer (draw_text chains A3). No args. */
void g_draw_divider(uint8_t *image);
void g_draw_panel2(uint8_t *image);
void g_draw_panel3(uint8_t *image);
void g_draw_panel5(uint8_t *image);
void g_draw_results_screen(uint8_t *image);   /* race-end results screen orchestrator; no args */

/* ---- road perspective (build_road_geometry @ 0x11f4c) ---- */
void g_build_road_geometry(uint8_t *image);

/* ---- object sprite blitters (blit_obj_* @ 0x10bdc..) ---- */
#define OBJ_FULL_CELLS 10       /* full-width fill: 10 * 16-byte writes = one 160-byte scanline */
#define OBJ_ROW_UP     0xa0     /* 160 bytes: one scanline up (sprites drawn bottom to top) */
/* Glue register map: A6 buf_base, D2 width, D3 row_offset, D4 x, D5/D6 fill, D7 rows-1.
 * near: fixed x, column drawn up the screen.  far: x slants by one per row. */
uint32_t g_blit_obj_Ln(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t row_offset,
                       uint32_t x, uint32_t fill_lo, uint32_t fill_hi, uint32_t rows_minus1);
void     g_blit_obj_Rn(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t row_offset,
                       uint32_t x, uint32_t fill_lo, uint32_t fill_hi, uint32_t rows_minus1);
uint32_t g_blit_obj_Lf(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t row_offset,
                       uint32_t x, uint32_t fill_lo, uint32_t fill_hi, uint32_t rows_minus1);
void     g_blit_obj_Rf(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t row_offset,
                       uint32_t x, uint32_t fill_lo, uint32_t fill_hi, uint32_t rows_minus1);
/* road-walk variants: A6 buf_base, D2 width, D5/D6 fill; x per row from road_width_tbl + ramp */
#define OBJ_ROAD_START_OFF 0x3480   /* draw buffer offset where the road band begins */
#define OBJ_ROAD_ROWS      0x54     /* max scanline rows walked (84) */
void g_blit_obj_Ln2(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t fill_lo, uint32_t fill_hi);
void g_blit_obj_Rn2(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t fill_lo, uint32_t fill_hi);
void g_blit_obj_Lf2(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t fill_lo, uint32_t fill_hi);
void g_blit_obj_Rf2(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t fill_lo, uint32_t fill_hi);

/* ---- OS wrappers (GEMDOS/BIOS/XBIOS glue); see os.h for the shared trap model ---- */
void g_xbios_setscreen(uint8_t *image);
void g_xbios_setpalette(uint8_t *image, uint32_t palette_ptr);   /* A0 -> 16-word palette */
void g_set_rez(uint8_t *image, uint32_t mode);                   /* D0.b -> config, then XBIOS 0x19 */
void g_read_joystick(uint8_t *image);                            /* IKBD poll: send 0x16; no image effect */
void g_gem_aes(uint8_t *image);                                  /* trap #2 AES (D0=0xc8, D1=&aes_pblk) */
void g_gem_vdi(uint8_t *image);                                  /* trap #2 VDI (D0=0x73, D1=&vdi_pblk) */
void g_start(uint8_t *image);                                    /* entry: GEM init, verified @ checkpoint 0x100d4 */
void g_main(uint8_t *image);                                     /* driver init (Malloc + buffers), verified @ 0x10144 */
void g_load_graphics(uint8_t *image);                            /* file loader, verified @ checkpoint 0x121f2 */
void g_unpack_graphics(uint8_t *image);                          /* GRAPHICS.GRA decompressor, verified @ 0x10720 */
void g_build_sprite_shifts(uint8_t *image, uint32_t count);      /* D5 = sprite count-1 */
void g_build_sprite_shifts_msk(uint8_t *image, uint32_t dst_off, uint32_t src_off, uint32_t count); /* D0, D1, D5 */

/* ---- sound-driver leaves (sound.c) ---- */
void g_TURNOFF(uint8_t *image);
void g_EGOFF(uint8_t *image);
void g_INITFX(uint8_t *image, uint32_t fx_id);                   /* D0 = effect id */
void g_INITTUNE(uint8_t *image, uint32_t tune_id);               /* D0 = tune id */
/* per-frame note-stream steppers: A0 = voice record, A3 = SND_STATE (D0 is scratch, hi=0).
 * snd_voice_a is the +1-voice-stride entry alias that falls into the snd_voice_b body. */
void g_snd_voice_b(uint8_t *image, uint32_t rec);
void g_snd_voice_a(uint8_t *image, uint32_t rec);
/* per-frame voice DSP: A0 = voice record, A1 = mod-table base, A2 = volume-out cursor,
 * A3 = SND_STATE; returns the tone period (D1). snd_stub is the +1-voice-stride entry alias. */
uint32_t g_snd_cmd_handler(uint8_t *image, uint32_t rec, uint32_t mod_tab, uint32_t out);
uint32_t g_snd_stub(uint8_t *image, uint32_t rec, uint32_t mod_tab, uint32_t out);
/* REFRESH @0x1b086 — 50 Hz VBL driver. Updates voice/EG/FX state in the image and appends the
 * frame's PSG (reg,val) writes to psg_reg/psg_val (up to cap); returns the write count. */
uint32_t g_REFRESH(uint8_t *image, uint8_t *psg_reg, uint8_t *psg_val, uint32_t cap);

/* ---- course-event engine (events.c) ---- */
void g_evt_collision(uint8_t *image);
void g_play_event_tune(uint8_t *image, uint32_t tune);           /* D0 = tune id */
void g_evt_flag_gate(uint8_t *image, uint32_t slot, uint32_t obj_type);   /* D5, D6 */
void g_evt_score_msg(uint8_t *image, uint32_t d6, uint32_t d7);
void g_handle_marker(uint8_t *image, uint32_t fx_id);            /* D0 = effect id */

#endif /* BB_BUGGYBOY_H */