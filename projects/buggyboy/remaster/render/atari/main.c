/* main.c — Atari GEMDOS shim that runs remaster's HUD renderer on a real 68000.
 *
 * remaster renders only the HUD so far, so this stages a captured mid-race background + the HUD
 * assets (baked into hud_fixture.h by gen_hud_fixture.py), calls rm_draw_hud, dumps the painted
 * framebuffer to C:\SCREEN.BIN (a headless run byte-compares it to recreate's golden.bin), then
 * loads the palette and blits to the physical screen and waits for a key. See render/atari/README.md.
 */
#include <stdint.h>

#include "game.h"
#include "screen.h"
#include "hud_fixture.h"

void rm_draw_hud(const HudState *s, const HudAssets *a, Framebuffer *fb);

extern long Fcreate(const char *name, short attr);
extern long Fwrite(short handle, long count, void *buf);
extern long Fclose(short handle);
extern long Cconin(void);
extern long Physbase(void);
extern void Setpalette(const void *pal16);

/* freestanding libc the HUD core needs (we link -nostdlib) */
void *memcpy(void *d, const void *s, unsigned long n) {
    uint8_t *dp = d; const uint8_t *sp = s;
    while (n--) *dp++ = *sp++;
    return d;
}
void *memset(void *d, int c, unsigned long n) {
    uint8_t *dp = d;
    while (n--) *dp++ = (uint8_t)c;
    return d;
}

static Framebuffer fb;              /* BSS: the 32000-byte draw buffer */

void main(void) {
    static const HudState state = {
        .flag_seq_count = HUD_FLAG_SEQ_COUNT, .flag_seq_off = HUD_FLAG_SEQ_OFF,
        .dsp_color_scroll = HUD_DSP_COLOR_SCROLL, .crash_lap = HUD_CRASH_LAP,
        .speed = HUD_SPEED, .time_left = HUD_TIME_LEFT, .game_over = HUD_GAME_OVER,
    };
    const HudAssets assets = {
        .color_pairs    = fixture_color_pairs,
        .color_bar_mask = fixture_color_bar_mask,
        .color_bar_cidx = fixture_color_bar_cidx + CIDX_ZERO_OFF,   /* point at the cursor's zero */
        .fuel_mask      = fixture_fuel_mask,
        .font           = fixture_font,
        .gauge_str      = fixture_gauge_str,
        .dashboard_src  = fixture_dashboard_src,
    };

    memcpy(fb.px, fixture_background, SCREEN_BYTES);
    rm_draw_hud(&state, &assets, &fb);

    /* Dump the painted framebuffer so a headless run can byte-compare it to recreate's golden.bin. */
    long h = Fcreate("SCREEN.BIN", 0);
    if (h >= 0) {
        Fwrite((short)h, SCREEN_BYTES, fb.px);
        Fclose((short)h);
    }

    Setpalette(fixture_palette);
    memcpy((void *)Physbase(), fb.px, SCREEN_BYTES);
    Cconin();                       /* hold the screen until a key is pressed */
}
