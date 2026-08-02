/* text.h — the game's message box: the driver at $bd8a and the glyph plotter below it (src/text.c).
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

/* $bd8a — the message box's whole per-frame lifecycle, and the plotter's only caller. Takes and
 * returns nothing: its three arms are picked by WB_TEXT_REQUEST and WB_TEXT_BOX_ACTIVE, and it
 * either composes a message into WB_TEXT_BUFFER or blits an already-composed one to
 * WB_SCREEN_BACK. game_main_loop's `jsr $bd8a.l` at $4fc is its one caller in the image. */
void text_run_message_box(uint8_t *image);

#endif /* WONDERBOY_TEXT_H */
