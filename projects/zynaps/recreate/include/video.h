/* video.h — the screen buffers, the shifter sink, and the clear/blit leaves in src/video.c.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 *
 * THE SHIFTER IS NOT AN IMAGE BYTE. Zynaps publishes its display buffer at $ff8201/$ff8203 and its
 * colours at $ff8240, both far above the 1 MiB image the differential compares, so the kit's oracle
 * DROPS every write to them (tools/recreate_kit/include/hw.h models hardware READS and has no
 * `hw_write8` to mirror a write with). Two reconstructed routines here make those writes because the
 * original makes them — `screen_flip_buffers` and `set_palette_title` — and both go through the sink
 * below rather than storing to an address of their own. Off target the sink only RECORDS what was
 * written, which is what lets the differential compare the payload and the write count against the
 * registers the original hands the hardware (test/test_video.py's stubs); the writes themselves
 * remain unobservable, and STATUS.md carries that residual.
 */
#ifndef ZYNAPS_VIDEO_H
#define ZYNAPS_VIDEO_H

#include <stdint.h>

/* ================================================================================================
 * The two framebuffers. Zynaps hard-codes them at absolute RAM rather than asking XBIOS for one
 * (test/abi.py says why that matters to the scratch map); these two longwords hold which is which
 * and `screen_flip_buffers` swaps them.
 * ============================================================================================= */
#define A_screen_back    0x1797eu  /* names.txt — the buffer being drawn into */
#define A_screen_front   0x17982u  /* names.txt — the buffer the shifter is displaying */

/* names.txt has no name for it; `clear_backdrop_page0` @ 0x12fc2 is the routine that establishes
 * what it is — the front end's compose buffer, one playfield's worth of bytes. The asteroid banks
 * are laid over the same store once the game proper starts (`_start` @ 0x1571a passes it to
 * `asteroid_preshift_bank` as bank 0), so the address is one buffer under two uses, not two. */
#define A_backdrop_page0 0x1a8aeu

/* names.txt calls it `palette_boot` and records `palette_title` as the other reading; the routine
 * that uploads it is named for the second. # ctx — neither name is a confirmed body read. */
#define A_palette_boot   0x19618u

/* ================================================================================================
 * Screen geometry. A 320x200 four-plane ST frame is 32000 bytes at 160 bytes a row; the playfield
 * the scroller owns is the top 144 of those rows, and an off-screen scroll page is exactly one
 * playfield's worth (see scroll.h) — ONE number under one name rather than three copies of 0x5a00.
 * ============================================================================================= */
#define SCREEN_ROW_BYTES  160u
#define SCREEN_BYTES    32000u    /* `move.w #$1f3f,d0` + `clr.l (a0)+`: 8000 longs */
#define SCREEN_PIXELS_WIDE 320u   /* `cmp.w #$140,d0` in draw_sprite_masked */
#define PLAYFIELD_ROWS    144u
#define PLAYFIELD_BYTES 0x5a00u   /* 144 * 160 — `adda.l #$5a00,a6` in playfield_clear */
/* Where the playfield sits on the 200-row screen: `cmp.w #$20,d1` and `cmp.w #$b0,d3` are the two
 * clip edges every sprite blit tests against, and their difference is PLAYFIELD_ROWS. */
#define PLAYFIELD_TOP_Y    32u
#define PLAYFIELD_BOTTOM_Y (PLAYFIELD_TOP_Y + PLAYFIELD_ROWS)

/* `movem.l (a6)+,#$02fe` / `movem.l #$02fe,(a0)`: d1-d7 and a1, eight longwords — 32 pixels of a
 * four-plane row. */
#define GRAPHIC_BLOCK_ROW_BYTES 32u

/* ================================================================================================
 * The shifter sink (see the header comment). `pair` counts LONGWORDS of the colour row, because
 * that is the width the original writes it in: `movem.l #$00ff,$ff8240.l` stores eight longs over
 * the sixteen 16-bit colour registers.
 * ============================================================================================= */
#define SHIFTER_PALETTE_PAIRS 8u

void shifter_palette_write(unsigned pair, uint32_t colours);
/* The screen base as the TWO BYTES the hardware has (bits 15-8 and 23-16 of the address; an STF's
 * base register has no low byte), in the order the original writes them: $ff8203 then $ff8201. */
void shifter_screen_base_write(uint8_t mid, uint8_t high);

/* ================================================================================================
 * Prototypes.
 * ============================================================================================= */
void screen_clear(uint8_t *image, uint32_t buffer);
void screen_flip_buffers(uint8_t *image);
void clear_backdrop_page0(uint8_t *image);
void blit_graphic_block(uint8_t *image, uint32_t src, uint32_t dst, uint16_t last_row);
void playfield_clear(uint8_t *image);
void set_palette_title(uint8_t *image);

#endif /* ZYNAPS_VIDEO_H */
