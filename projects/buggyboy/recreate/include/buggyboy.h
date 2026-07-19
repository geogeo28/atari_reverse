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

/* A few glue functions are pure no-ops in the differential harness (their real effect is hardware
 * I/O the oracle models elsewhere), but the standalone Atari PRG (render/atari/) must do the real
 * work. Marking those defs weak lets the PRG link supply strong overrides; the harness .so has a
 * single definition either way, so its verified behaviour is unchanged. */
#define BB_WEAK __attribute__((weak))

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
void g_flip_screen(uint8_t *image);      /* page-flip: video base + Vsync (hardware); toggles flip_idx */

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
uint32_t draw_hud_bar_chain(uint8_t *image, uint32_t dst, uint32_t fill_lo, uint32_t fill_hi, uint32_t str_ptr);
/* Chain variants used by draw_hud: report the advanced dst (A0) via *end_dst and return the
 * advanced string cursor (A3), so consecutive gauge0/bar draws thread both registers. */
uint32_t draw_hud_gauge0_chain(uint8_t *image, uint32_t dst, uint32_t color_idx, uint32_t cells_m1,
                               uint32_t str_ptr, uint32_t *end_dst);
uint32_t draw_hud_bar_chain_dst(uint8_t *image, uint32_t dst, uint32_t fill_lo, uint32_t fill_hi,
                                uint32_t str_ptr, uint32_t *end_dst);
void g_draw_hud(uint8_t *image);   /* full HUD: speed/time digits, dashboard sprite, gauges, crash fx */
/* draw_text returning the advanced A3 (past the 0-pair terminator), for callers chaining labels. */
uint32_t draw_text_chain(uint8_t *image, uint32_t dst_off, uint32_t color_idx, uint32_t str_ptr);

/* ---- number blitter (draw_num @ 0x15a86) ---- Digits are single string bytes (0 ends it);
 * each digit's 15-row sprite is pre-rendered into buf_c and indexed by num_glyph_tbl. Colour
 * is NOT masked to 0xf (unlike text). draw_num_thunk presets the cell count to 0x13. */
void g_draw_num(uint8_t *image, uint32_t dst_off, uint32_t color_idx,
                uint32_t cells_m1, uint32_t str_ptr);       /* D0, D1, D5, A3 */
void g_draw_num_thunk(uint8_t *image, uint32_t dst_off, uint32_t color_idx, uint32_t str_ptr);

/* ---- crash / game-over HUD effect (hud.c) ---- A6 = draw buffer. */
void g_draw_crash_fx(uint8_t *image, uint32_t buffer);

/* ---- results-screen block blitters (draw_result_row/col @ 0x15016..) ----
 * Both copy a source block from buf_c (A1 offset) to buffer[flip_idx] + D0; no colour index.
 * col tiles a 7-row 16-byte column 5x across; row stacks a 32-row 4-word transparency blit
 * 3x down (mask = D & ~(A|B|C) from the four source words). */
void g_draw_result_row(uint8_t *image, uint32_t dst_off, uint32_t src_off);   /* D0, A1 */
void g_draw_result_col(uint8_t *image, uint32_t dst_off, uint32_t src_off);   /* D0, A1 */
void g_draw_dashboard(uint8_t *image, uint32_t dst_off);                      /* D0; src = buf_c fixed */
void g_init_leg_dash(uint8_t *image);                                         /* builds per-leg dashboard graphic; no args */
void g_probe_collision(uint8_t *image);                                       /* advances the dashboard marker one track step; no args */
void g_draw_leg_labels(uint8_t *image);                                       /* draws per-leg dashboard labels, then probe_collision; no args */
void g_draw_leg_results(uint8_t *image);                                      /* leg-results screen; no args */

/* ---- intermission-screen block blitter (intermission_poll @ 0x12914) ----
 * Table-driven plain block copy of 9 rectangles from buf_c to the draw buffer (no input, despite
 * the name); the misclassification is noted in HARNESS.md. */
void g_intermission_poll(uint8_t *image);
void g_draw_intermission(uint8_t *image);   /* scrolling between-legs screen (hi-score/times/credits) */
void g_fade_step(uint8_t *image);           /* one intermission step: backdrop + header, falls into draw_intermission */

/* intermission @ 0x127a0 — the attract-mode loop (never returns except on abort). The phase-slice
 * helpers are the loop bodies, exposed so each is diffable by entering the oracle at its PC. */
void g_intermission(uint8_t *image);
int  g_int_stepA(uint8_t *image);           /* Phase-A body: 0 continue, 1 abort, 2 break-to-B */
void g_int_phaseB_leg(uint8_t *image);      /* Phase-B leg-select advance -> leg_index */
int  g_int_stepD_counter(uint8_t *image);   /* Phase-D dwell/leg counter: 0 draw, 1 advance, 2 restart */

/* init_playfield @ 0x12af6 — the leg-select / playfield-init loop; returns only when a leg starts.
 * g_init_playfield_nav is the joystick-navigation slice (0x2c00 tail), exposed so it is diffable by
 * entering the oracle at its PC (the loop itself never returns except on a leg start). */
void g_init_playfield(uint8_t *image);
void g_init_playfield_nav(uint8_t *image);
int  g_init_playfield_fire(uint8_t *image);   /* fresh-fire edge: 1 = start the selected leg, 0 = keep waiting */

/* ---- masked buggy / foreground sprites (draw_fg_sprite .. draw_buggy @ 0x1518a..) ----
 * draw_buggy_wheels is the shared blit body: A0 dst, A1 src (into buf_c), D4 rows-1; each row
 * is 4 transparency cells, dst/src stepping one scanline up per row. */
void g_draw_buggy_wheels(uint8_t *image, uint32_t dst, uint32_t src, uint32_t rows_m1);
void g_draw_fg_sprite(uint8_t *image);   /* foreground buggy sprite; spin/curve gate + anim table */
void g_draw_buggy_lo(uint8_t *image, uint32_t buffer);   /* A6 = draw buffer; lower body, 2 sub-sprites */
void g_draw_buggy_hi(uint8_t *image, uint32_t dst_base); /* A2 = dst base; lean overlay (OR-blit) */
void g_draw_buggy(uint8_t *image);                       /* player car: body + hi overlay + lo body; no args */
void g_draw_checkpoint_anim(uint8_t *image);             /* checkpoint-banner scroll within buf_c; no args */

/* ---- divider + text panels (draw_divider @ 0x126e6, draw_panel2/3/5 @ 0x1271c..) ----
 * draw_divider = filled rect + two vertical lines. Each panel draws the divider then a fixed
 * set of labels from one concatenated ASCII buffer (draw_text chains A3). No args. */
void g_draw_divider(uint8_t *image);
void g_draw_panel2(uint8_t *image);
void g_draw_panel3(uint8_t *image);
void g_draw_panel5(uint8_t *image);
void g_draw_results_screen(uint8_t *image);   /* race-end results screen orchestrator; no args */
void g_update_highscore(uint8_t *image);      /* rank/shift/insert the new score; checkpoint-verified */
void g_hiscore_gameover(uint8_t *image);      /* update_highscore miss tail: results redraw + game-over jingle */
void g_hiscore_name_entry(uint8_t *image);    /* update_highscore made tail: name-entry jingle + initials screen */
void g_hiscore_name_entry_jingle(uint8_t *image);  /* just the 0x12450 name-entry jingle (directed test seam) */
int  g_hiscore_countdown(uint8_t *image);     /* name-entry countdown tick + "TIME nn" render; 1 if timed out */
void g_hiscore_charstep(uint8_t *image, uint32_t name_ptr);   /* name-entry per-frame char select (up/down) */
void g_init_scoretable(uint8_t *image);       /* write the default high-score table (5 legs x 9 rows) */

/* ---- per-leg / gameplay orchestrators (gameplay.c) ---- */
void g_init_leg(uint8_t *image);              /* reset all per-leg state at the start of a leg; no args */

/* ---- road perspective (build_road_geometry @ 0x11f4c) ---- */
void g_build_road_geometry(uint8_t *image);
void g_set_screen_offset(uint8_t *image);      /* set the buf_c road-scroll offset from the leg's scroll table */
void g_wait_vbl_set_offset(uint8_t *image);    /* 51x Vsync then set_screen_offset */
void g_blit_road_scroll(uint8_t *image);       /* horizontal fine-scroll of the road playfield to the screen */
void g_draw_ground(uint8_t *image, uint32_t buffer);  /* A6 = draw buffer; fill the ground/horizon band */
void g_render_road(uint8_t *image);   /* pseudo-3D road rasterizer @0x19144 (idiomatic default; thunk 0x15af6 is an alias) */
void g_render_road_machine(uint8_t *image); /* byte-exact machine-model anchor (src/machine/road.c) */

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
/* draw_object @0x1087e — A6 = draw buffer; scans road_width_tbl, computes edges, dispatches the blits. */
void g_draw_object(uint8_t *image, uint32_t buffer);

/* draw_object_list @0x1306e — per-frame object display-list dispatcher (register-glue). A5 list
 * stream, A3 flag stream, A6 draw buffer, D4 outer row count-1, D6 record byte offset, D1 colour. */
void g_draw_object_list(uint8_t *image, uint32_t a5, uint32_t a3, uint32_t a6,
                        uint32_t d4_outer, uint32_t d6, uint32_t d1_in);

/* draw_game_objects @0x12ef6 — per-frame scene/object draw orchestrator; a6 = draw buffer (derived).
 * Advances marker/anim/bonus state, then draws ground, fg sprite, roadside objects, object, buggy. */
void g_draw_game_objects(uint8_t *image);
/* Test-only: the deterministic prefix of draw_game_objects (marker/anim/bonus), for checkpoint diff. */
void g_draw_game_objects_prefix(uint8_t *image);

/* draw_frame @0x12e22 — whole-frame render: build_road_geometry, render_road, blit_road_scroll,
 * draw_game_objects, draw_hud (pure sequential wrapper, no args). */
void g_draw_frame(uint8_t *image);

/* game_update @0x1110e — the per-frame in-race game-logic driver (root orchestrator). No args;
 * reads input + game state globals, returns each frame. */
void g_game_update(uint8_t *image);

/* Test glue: run one event-jump-table handler in isolation (idx -> target, entered at its PC). */
void g_gu_dispatch_event(uint8_t *image, uint32_t idx, uint32_t d5, uint32_t d6, uint32_t d7);

/* Test glue: sections G/H/I of the course-advance tail (@0x118b6), for the directed jingle tests. */
void g_game_update_fx_and_events(uint8_t *image);

/* blit_objshift @0x14680 — sub-pixel (fine-x shifted) 4-plane masked sprite blitter (leaf).
 * Register map: D0 x, D1 colour index, D4 rows-1, A0 dst scanline base, A1 src stream, A3 -> stride word. */
void g_blit_objshift(uint8_t *image, uint32_t x, uint32_t color, uint32_t rows_m1,
                     uint32_t dst, uint32_t src, uint32_t stride_ptr);

/* 0x144ac entry — the "0x90" width family of the same engine (base draws two straddle cells; reaches
 * the LEFT-2/RIGHT-2 ladder rungs dead from the 0x14680 entry). Same register ABI as g_blit_objshift. */
void g_blit_objshift_w2(uint8_t *image, uint32_t x, uint32_t color, uint32_t rows_m1,
                        uint32_t dst, uint32_t src, uint32_t stride_ptr);

/* blit_objshift2 @0x13ed6 — the SECOND sub-pixel masked sprite blitter (leaf; disassembly-driven).
 * Two-word mask ~(w0|w1), plain shifted-OR copy, no color_pairs. Register map: D0 x, D4 rows-1,
 * A0 dst scanline base, A1 src sprite stream. See BLIT_OBJSHIFT2_SPEC.md. */
void g_blit_objshift2(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t dst, uint32_t src);

/* roadside-object sprite draw-handler family @ 0x14620 / 0x1465c / 0x14664 (+ tail 0x14676).
 * These derive blit geometry from a per-object descriptor record (A2 = rec+0xa) + view_flags, set
 * the per-row stride/mode word at 0x18cb0, and call blit_objshift. See BLIT_OBJSPRITE_SPEC.md.
 *   hi:  D0 x, D1 colour, D2 width(=0xa0), D4 rows seed, D7 vertical offset, A0 dst, A1 src, A2 rec+0xa.
 *   dbl: same register contract as hi (draws twice, colour preserved for the tail pass).
 *   lo:  D0 x, D1 colour, D4 rows-1, A1 src, A2 rec+0xa, A6 draw-buffer base. */
void g_draw_obj_sprite_hi(uint8_t *image, uint32_t x, uint32_t colour, uint32_t width,
                          uint32_t rows_seed, uint32_t voff, uint32_t dst, uint32_t src,
                          uint32_t rec_cursor);
void g_draw_obj_handler_dbl(uint8_t *image, uint32_t x, uint32_t colour, uint32_t width,
                            uint32_t rows_seed, uint32_t voff, uint32_t dst, uint32_t src,
                            uint32_t rec_cursor);
void g_draw_obj_handler_lo(uint8_t *image, uint32_t x, uint32_t colour, uint32_t rows_m1,
                           uint32_t src, uint32_t rec_cursor, uint32_t base);

/* Shared object-sprite blit engine @ 0x131f6..0x13df8 (disassembly-driven). One parameterized
 * fine-x-shifted 4-plane masked blitter (4-word mask ~(w0|w1|w2|~w3), plain shifted-OR copy, no
 * color_pairs) with ~18 alternate entry points. See OBJ_BLIT_ENGINE_SPEC.md. Register maps in
 * names.txt (proto lines). The bare prologue heads select the width family:
 *   t4 @0x131f6 -> 0x80, w88 @0x133b6 -> 0x88, t2 @0x1352c -> 0x90, t1 @0x13642 -> 0x98.
 * D0 x, D4 rows-1, A0 dst scanline base, A1 src sprite stream. */
void g_objsprite_t4(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t dst, uint32_t src);
void g_objsprite_t2(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t dst, uint32_t src);
void g_objsprite_t1(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t dst, uint32_t src);
void g_objsprite_w88(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t dst, uint32_t src);
/* t53 @0x13204: ALT ENTRY skipping the fine-x calc; caller pre-sets d0=aligned_col, d6=shl, d7=shr. */
void g_objsprite_t53(uint8_t *image, uint32_t aligned_col, uint32_t shl, uint32_t shr,
                     uint32_t rows_m1, uint32_t dst, uint32_t src);
/* a6-relative wrappers (a0 = a6 + word@--a2) then a width prologue: t34->0x88, t33->0x90, t32->0x98. */
void g_objsprite_t34(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t a6, uint32_t a2, uint32_t src);
void g_objsprite_t33(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t a6, uint32_t a2, uint32_t src);
void g_objsprite_t32(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t a6, uint32_t a2, uint32_t src);
/* view-transform wrappers (helper 0x145fc then a width prologue): t39->0x88, t38->0x90, t37->0x98.
 * A6 object base, A1 src, A2 rec cursor (predecremented by the transform); reads A_view_flags +
 * the A_obj_view_xform table. */
void g_objsprite_t39(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t a6, uint32_t a1, uint32_t a2);
void g_objsprite_t38(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t a6, uint32_t a1, uint32_t a2);
void g_objsprite_t37(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t a6, uint32_t a1, uint32_t a2);
/* scan-table x-build wrappers then a width prologue: t42->0x90, t41->0x98. A6 base, A2 record
 * cursor, A4/A5 scan-table bases, A1 src; reads A_obj_scan_off. */
void g_objsprite_t42(uint8_t *image, uint32_t rows_m1, uint32_t a6, uint32_t a2,
                     uint32_t a4, uint32_t a5, uint32_t src);
void g_objsprite_t41(uint8_t *image, uint32_t rows_m1, uint32_t a6, uint32_t a2,
                     uint32_t a4, uint32_t a5, uint32_t src);
/* bsr draw_obj_sprite_hi (0x14620, verified) then FALL THROUGH into a width prologue (a second
 * pass on the helper's renamed D3->D0/D5->D4/A0/A1): t3->0x88, t49->0x90, t16(=t17/43/48)->0x98.
 * Same register contract as draw_obj_sprite_hi. */
void g_objsprite_t3(uint8_t *image, uint32_t x, uint32_t colour, uint32_t width, uint32_t rows_seed,
                    uint32_t voff, uint32_t dst, uint32_t src, uint32_t rec_cursor);
void g_objsprite_t49(uint8_t *image, uint32_t x, uint32_t colour, uint32_t width, uint32_t rows_seed,
                     uint32_t voff, uint32_t dst, uint32_t src, uint32_t rec_cursor);
void g_objsprite_t16(uint8_t *image, uint32_t x, uint32_t colour, uint32_t width, uint32_t rows_seed,
                     uint32_t voff, uint32_t dst, uint32_t src, uint32_t rec_cursor);

/* ---- OS wrappers (GEMDOS/BIOS/XBIOS glue); see os.h for the shared trap model ---- */
void g_xbios_setscreen(uint8_t *image);
void g_xbios_setpalette(uint8_t *image, uint32_t palette_ptr);   /* A0 -> 16-word palette */
void g_xbios_setcolor(uint8_t *image, uint32_t index, uint32_t color);   /* XBIOS Setcolor: one reg; no image effect */
void g_poke_color_reg(uint8_t *image, int16_t reg_sel, uint16_t color);  /* mode-6 tunnel poke: 0xffff824c+reg_sel; no image effect */
void g_set_rez(uint8_t *image, uint32_t mode);                   /* D0.b -> config, then XBIOS 0x19 */
void g_read_joystick(uint8_t *image);                            /* IKBD poll: send 0x16; no image effect */
void g_vsync(void);                                              /* XBIOS Vsync: wait one vblank; no image effect */
void g_wait_music_off(uint8_t *image);                           /* spin until mzflag clears (tune ended); no image effect */
uint16_t g_console_scancode(uint8_t *image);                     /* GEMDOS Crawio(0xff): IKBD scancode, 0 if none */
uint16_t g_console_wait_char(uint8_t *image);                    /* GEMDOS Crawcin (fn 7): blocking raw ASCII read */
void g_read_input(uint8_t *image);                               /* joystick + keyboard-fallback -> input_state */
uint32_t g_check_abort(uint8_t *image);                          /* returns d0: 0x0d abort, else swap(Crawio) */
void g_install_handlers(uint8_t *image);                         /* Kbdvbase: save + patch mousevec/joyvec */
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
/* stop_music/_chk take the Dosound command-list image offset the original passes in A0 (one of the
 * A_dosound_* lists). Off-image: g_dosound is a no-op in the harness, the real XBIOS trap in the PRG. */
void g_dosound(uint8_t *image, uint32_t list_off);               /* XBIOS 32: play a YM command list */
void g_stop_music(uint8_t *image, uint32_t list_off);            /* silence the driver unless game-over; Dosound(list) */
void g_stop_music_chk(uint8_t *image, uint32_t list_off);        /* stop_music, gated on MZFLAG == 0 */
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
void g_evt_flag_gate_forced(uint8_t *image, uint32_t slot);              /* d7=6 variant @0x11c1a: gate skipped */
void g_evt_score_msg(uint8_t *image, uint32_t obj_flag_a, uint32_t obj_flag_b);
void g_handle_marker(uint8_t *image, uint32_t fx_id);            /* D0 = effect id */

#endif /* BB_BUGGYBOY_H */