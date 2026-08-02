/* text.h — the game's glyph plotter, $bf4e..$c030 (src/text.c).
 *
 * TWO ENTRY POINTS INTO ONE ROUTINE, which is how the original is built: $bf4e has no `rts` at all.
 * Its four instructions turn a character code into a glyph pointer and it then FALLS THROUGH into
 * $bf5e, so $bf5e's `rts` is what returns to $bf4e's caller — exactly what `text_plot_char` calling
 * `text_plot_glyph` and returning its result is. $bf5e keeps a name of its own because eight `bsr`
 * sites in $bd8a enter it directly, with a glyph pointer they already hold.
 *
 * Every address and every geometry constant is in wonderboy.h, which both languages read.
 */
#ifndef WONDERBOY_TEXT_H
#define WONDERBOY_TEXT_H

#include <stdint.h>

/* $bf5e — plot the WB_TEXT_GLYPH_BYTES at `glyph` into the WB_TEXT_BUFFER_LINE-wide 4-plane buffer
 * at `cursor`, and return the cursor of the next 8-pixel cell. `glyph` is the original's a0 and
 * `cursor` its a1, in and out. */
uint32_t text_plot_glyph(uint8_t *image, uint32_t glyph, uint32_t cursor);

/* $bf4e — the same, for a character `code` (the original's d0) indexed into WB_TEXT_GLYPH_TABLE. */
uint32_t text_plot_char(uint8_t *image, uint32_t code, uint32_t cursor);

#endif /* WONDERBOY_TEXT_H */
