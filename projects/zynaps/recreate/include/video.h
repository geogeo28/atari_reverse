/* video.h — the screen buffers, the shifter sink, and the clear/blit leaves in src/video.c.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 *
 * THE SHIFTER IS NOT AN IMAGE BYTE, AND IS PINNED ANYWAY. Zynaps publishes its display buffer at
 * $ff8201/$ff8203 and its colours at $ff8240, both far above the 1 MiB image the differential
 * compares, so the oracle DROPS every store to them and no byte diff can see one. Two reconstructed
 * routines here make those stores because the original makes them — `screen_flip_buffers` and
 * `set_palette_title` — and both go through the kit's `hw_write8`/`hw_write32`
 * (tools/recreate_kit/include/hw.h), whose ordered (address, width, value) ledger
 * `harness.differential` compares against the oracle's entry for entry. A short upload, the wrong
 * register, the two base bytes swapped and a missing store are all reds; there is no residual left
 * for STATUS.md to carry here.
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
 * are laid over the same store once the game proper starts (`asteroids_load_and_build` @ 0x156ac
 * builds six 0x1e00-byte banks here, 0xb400 bytes = two playfields, reaching into scroll page 1,
 * and passes bank 0 to `asteroid_preshift_bank` at 0x1571a), so the address is one buffer under
 * two uses, not two. */
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
 * THE SHIFTER'S OWN GEOMETRY, and this header is its one home — `include/irq.h`'s handlers write
 * the same registers and take these from here. The colour row is counted in LONGWORDS because that
 * is the width the original writes it in (`movem.l #$00ff,$ff8240.l` stores eight longs over the
 * sixteen 16-bit registers), and the width is part of what the write ledger compares rather than an
 * implementation choice.
 * ============================================================================================= */
#define HW_PALETTE_BASE 0xff8240u   /* the sixteen colour registers, one word each */
#define PALETTE_PENS      16u       /* ...how many of them there are... */
#define PALETTE_PEN_BYTES  2u       /* ...so one pen is a word... */
#define PALETTE_LONG_BYTES 4u       /* ...and the upload's own unit is two of them */
/* The eight longwords one whole row goes up as. Kept as the original's own count rather than
 * as the product above, for PLAYFIELD_BYTES's reason — test_constants.py's scraper reads
 * literals, not expressions — and test_video.py pins the two equal. */
#define SHIFTER_PALETTE_PAIRS 8u
/* The screen base's TWO BYTES (bits 15-8 and 23-16 of the address; an STF's base register has no
 * low byte), in the order the original writes them: $ff8203 then $ff8201. */
#define HW_SCREEN_BASE_MID  0xff8203u
#define HW_SCREEN_BASE_HIGH 0xff8201u

/* ================================================================================================
 * Prototypes.
 * ============================================================================================= */
/* ---- the shifter stores, which src/irq.c's handlers make as well as this file's two routines ----
 *
 * They live here because the shifter's registers do (see the header comment): five routines across
 * two subsystems write the same colour block, and one register block has one set of stores. Each is
 * one instruction of the original and the WIDTH is part of it — the row goes up as eight `move.l`s,
 * a single bar colour as one `move.w` — which is what the kit's write ledger compares.
 *
 * ON TARGET, `hw_write*` becomes the real store of its own width and these compile unchanged; the
 * kit's src/hw.c is what a target build leaves out (tools/recreate_kit/include/hw.h).
 */
/* Eight longwords over the sixteen colour registers, from the shadow at `shadow`. */
void shifter_upload_palette_longs(const uint8_t *image, uint32_t shadow);
/* `move.w <colour>,$ff8240 + 2*pen` — one pen, the attract bars' own shape. */
void shifter_write_pen(unsigned pen, uint16_t colour);
/* `clr.w $ff8240` — force pen 0 to black. */
void shifter_clear_pen0(void);

void screen_clear(uint8_t *image, uint32_t buffer);
void screen_flip_buffers(uint8_t *image);
void clear_backdrop_page0(uint8_t *image);
void blit_graphic_block(uint8_t *image, uint32_t src, uint32_t dst, uint16_t last_row);
void playfield_clear(uint8_t *image);
void set_palette_title(uint8_t *image);

#endif /* ZYNAPS_VIDEO_H */
