/* hud.h — the static 320x40 planar strip on screen lines SCREEN_WINDOW_LINES..SCREEN_H-1.
 *
 * DESIGN 15.1: the panel art is blitted once per screen buffer and the live fields are planar
 * writes at fixed positions, drawn at 1:1 (the strip is outside the c2p region, which is why an
 * 8x8 font is legible in it). Nothing here shifts: every field starts on an 8-pixel boundary, so a
 * glyph is one byte of each plane word and a fill is whole bytes.
 *
 * WHAT IS A HOOK AND WHAT IS REAL. Every field below is read from GameState (include/game.h) —
 * the trace meter, the throttle, integrity, cycles and the tokens are all real state now that the
 * game layer has landed. The one exception is `weapon`: DESIGN 18 defers the Spike, so there is one
 * weapon, the icon has one state, and nothing draws it yet.
 */
#ifndef BLACKICE_HUD_H
#define BLACKICE_HUD_H

#include <stdint.h>
#include "game_consts.h"

#define HUD_TOKEN_COUNT     3

typedef struct {
    const char *sector_name;    /* the level's name, drawn in the title bar */
    const char *message;        /* one line over the title bar, or NULL (DESIGN 15.1) */
    uint16_t    run_seconds;    /* the route timer, drawn as MM:SS */
    uint16_t    frame_ms;       /* measured frame time in whole milliseconds */
    uint8_t     trace_percent;  /* 0..100, from GameState.trace_milli */
    uint8_t     throttle;       /* THROTTLE_*, from GameState.throttle */
    uint8_t     integrity;      /* 0..100 */
    uint16_t    cycles;         /* 0..200 */
    uint8_t     tokens;         /* one bit per token, ALPHA in bit 0 */
    uint8_t     weapon;         /* 0 Buster, 1 Spike */
} HudState;

/* Blit the packed backdrop into one screen buffer. Call once per buffer, before any hud_draw. */
void hud_blit_backdrop(uint8_t *screen);

/* Mark a `shown` record as holding nothing, so the next hud_draw against it redraws every field. */
void hud_reset(HudState *shown);

/*
 * Redraw the fields of `state` that differ from `shown`, then update `shown` (DESIGN 15.1: only
 * fields whose value changed are redrawn). `shown` is what is on THAT screen buffer, so a double
 * buffered caller keeps one record per buffer.
 */
void hud_draw(uint8_t *screen, const HudState *state, HudState *shown);

#endif /* BLACKICE_HUD_H */
