/* overlay.h — the full-screen text the run's flow needs: the title, and what happens between
 * sectors.
 *
 * DESIGN 15 gives the first playable a title screen, a death screen, a SECTOR CLEAR overlay and a
 * RUN COMPLETE screen. None of them existed until QA played the game and found that dying and
 * clearing a sector both did nothing at all (QA.md defects 1, 2 and 3).
 *
 * THIS DUPLICATES hud.c's PLANAR GLYPH WRITER AND SHOULD NOT, and the reason it does is scheduling:
 * hud.c is being rewritten by the art pass as this lands, so the two cannot be merged yet. The
 * writer here is the same eight-pixel, no-shift, one-byte-per-plane routine; when hud.c settles,
 * the right move is to export its draw_text/draw_glyph and delete this file's copies.
 */
#ifndef BLACKICE_OVERLAY_H
#define BLACKICE_OVERLAY_H

#include <stdint.h>

/* The pens DESIGN 3 reserves for exactly this: white for the text a wall may never wear, and the
 * void the overlays sit on. */
#define OVERLAY_PEN_TEXT    12      /* #FFFFFF, RESERVED — no wall texture may use it */
#define OVERLAY_PEN_DIM     3       /* #2299CC, cyan 3, for the second line */
#define OVERLAY_PEN_ALERT   13      /* #FF7722, the reserved hostile accent */
#define OVERLAY_PEN_VOID    0

/* Blank the 3D window (the top SCREEN_WINDOW_LINES lines), leaving the HUD strip alone. */
void overlay_clear(uint8_t *screen);

/* One line of 8x8 glyphs at a whole-byte x. Returns the pen x after the string. */
int overlay_text(uint8_t *screen, int x, int y, const char *text, uint8_t pen);

/* The same, centred on the 320-pixel screen and snapped to an 8-pixel boundary. */
void overlay_centre(uint8_t *screen, int y, const char *text, uint8_t pen);

/* MM:SS from a tick count at SIM_HZ, into `out` (six bytes are enough). */
void overlay_format_clock(char *out, uint16_t ticks);

/* A right-aligned decimal, `digits` wide, space padded. */
void overlay_format_number(char *out, uint16_t value, int digits);

#endif /* BLACKICE_OVERLAY_H */
