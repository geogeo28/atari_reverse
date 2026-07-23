/* flow.h — the between-legs flow's draw surfaces (recreate's intermission.c / results.c cores).
 *
 * Slice A of the between-legs flow: the four draw functions that paint the intermission and results
 * screens, ported onto remaster's native models. The FLOW that sequences them (the attract loop's
 * phases A-D) is slice B; these are the host-verified drawing cores it will call.
 *
 *   rm_intermission_poll  a 9-entry table-driven block copy from buf_c into the draw buffer
 *   rm_draw_intermission  the scrolling hi-score / leg-time / credits screen
 *   rm_draw_leg_results   the per-leg results screen (result panels, labels, digits, dashboard)
 *   rm_fade_step          one between-legs backdrop frame: fill + poll + header + intermission
 *
 * They reuse the shared primitives: rm_glyph_run / rm_num_run (text.h) for the paired-glyph text and
 * digit-sprite runs, cell_transp (plane.h) for the masked result blit, and the rm_fill_* family
 * (fill.h) for the background fills. Asset tables come from the arena (buf_c graphics, buf_a strings)
 * or program-data / persistent-state windows, following the established adapter split.
 */
#ifndef RM_FLOW_H
#define RM_FLOW_H

#include <stdint.h>
#include "screen.h"

/* The intermission screen's assets (draw_intermission + fade_step + the poll leaf).
 *
 * `highscore` is the between-legs mutable game state — update_highscore writes it, so it is modelled
 * as a persistent buffer (like hud_text), seeded from init_scoretable's default table; the flow slice
 * owns its updates. Everything else is const: arena graphics (poll_src / num_sprites from buf_c),
 * buf_a strings (leg_names), and program-data layout tables / strings (sec1_tbl / sec3_tbl / credits /
 * header_str / poll_blits / num_glyph_tbl / font / color_pairs). */
typedef struct {
    const uint8_t *color_pairs;    /* 16 colours x 8-byte fill (text tint + fade backdrop) */
    const uint8_t *font;           /* 1bpp glyph table (16 bytes/char) */
    const uint8_t *num_sprites;    /* pre-rendered digit/letter sprites (buf_c + 0xbb80) */
    const uint8_t *num_glyph_tbl;  /* per-char word byte-offset into num_sprites */
    const uint8_t *poll_src;       /* block-copy source (buf_c + 0x32c80) */
    const uint8_t *poll_blits;     /* 9 x {src_off:w, dst_off:w, dims:w} control table (program data) */
    const uint8_t *header_str;     /* fade_step copyright header string (program data) */
    const uint8_t *sec1_tbl;       /* section-1 layout: 15 x {base,dst_add,max_rows,colour,str_off} */
    const uint8_t *sec3_tbl;       /* section-3 layout: 3 x the same 5-word entry */
    const uint8_t *credits;        /* section-3 credit strings (program data) */
    const uint8_t *leg_names;      /* section-2 scrolling leg-name sprites (buf_a + 0x884) */
    const uint8_t *highscore;      /* persistent hi-score table (section-1 strings) */
} RmIntermissionAssets;

/* The per-leg results screen's assets. `gfx` is the buf_c base (result panels + dashboard index it by
 * absolute offset); `leg_palette` points AT the per-row colour byte for leg 0 and is indexed [i - leg]
 * (recreate's `suba.w leg` cursor); the rest are buf_a strings and program-data. */
typedef struct {
    const uint8_t *color_pairs;
    const uint8_t *font;
    const uint8_t *num_sprites;
    const uint8_t *num_glyph_tbl;
    const uint8_t *gfx;            /* buf_c base; result/dashboard src offsets are absolute into it */
    const uint8_t *title;          /* row-1 concatenated label strings (program data) */
    const uint8_t *leg_palette;    /* per-row colour bytes, indexed [i - leg] (cursor at leg 0) */
    const uint8_t *row_names;      /* row-2 per-leg label strings (buf_a + 0x848) */
    const uint8_t *leg_digits;     /* leg time/score digit string (buf_a + 0x884) */
} RmResultsAssets;

/* 9-entry table-driven block copy from `src` (buf_c + 0x32c80) into fb at +0x990. */
void rm_intermission_poll(Framebuffer *fb, const uint8_t *src, const uint8_t *blits);

/* The scrolling hi-score / leg-time / credits screen at vertical scroll `int_scroll`. */
void rm_draw_intermission(Framebuffer *fb, const RmIntermissionAssets *a, int16_t int_scroll);

/* One between-legs backdrop frame: fill(6) + poll + header + draw_intermission. */
void rm_fade_step(Framebuffer *fb, const RmIntermissionAssets *a, int16_t int_scroll);

/* The per-leg results screen for leg `leg` (0-4). */
void rm_draw_leg_results(Framebuffer *fb, const RmResultsAssets *a, uint16_t leg);

#endif /* RM_FLOW_H */
