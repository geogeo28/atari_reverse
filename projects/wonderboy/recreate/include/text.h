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

#include "machine.h"
#include "wonderboy.h"

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

/* THE TWO STORES THAT ASK FOR A MESSAGE BOX, and why they are one inline here.
 *
 * `move.b #id,$c030.l / move.w #$32,$c034.l` is the whole of "post this message", and FOUR modules
 * spelt it: src/actor.c's slot spend, src/effects.c's grants, src/behavior.c's gold award and (batch
 * 40) src/player.c's two. Both of the earlier comments argued against sharing it — "a symbol across
 * three modules to save one `wr16`" — and at four copies that argument stops holding, for the reason
 * bus.h's record accessors give: a second copy is the one divergence nothing catches, since each
 * module's battery pins only its own routines and both stay green while one drifts.
 *
 * It is `static inline` in a header both already include, so it exports no symbol and the objection
 * costs nothing.
 *
 * THE LIFETIME-TAKING FORM IS HERE TOO, as of batch 41 phase C, and by the same argument at the same
 * threshold. src/scene.c wrote one for its own TEN call sites (its speech arm posts a lifetime of
 * zero) and the earlier revision of this plate listed it under "what is not here"; the gate at $b1a
 * then made it a SECOND module's, posting WB_DEATH_MESSAGE_LIFETIME rather than the default — so the
 * pair of stores has one body again and the default is expressed as one call rather than as a second
 * copy of the two writes.
 *
 * WHAT IS STILL NOT HERE: `type61_post_message`, which clears only the HIGH byte of the lifetime word
 * with a `clr.b`. That is not this pair of stores, and folding it in would hide that. */
static inline void text_post_message_for(uint8_t *image, uint8_t message, uint16_t lifetime) {
    image[WB_TEXT_REQUEST] = message;
    wr16(image + WB_TEXT_LIFETIME_REQUEST, lifetime);
}

static inline void text_post_message(uint8_t *image, uint8_t message) {
    text_post_message_for(image, message, WB_TEXT_LIFETIME_DEFAULT);
}

#endif /* WONDERBOY_TEXT_H */
