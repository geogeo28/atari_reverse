/* boot_stub.c — the whole of the rebuilt ROM's behaviour, for now.
 *
 * IT IS A TOOLCHAIN PROOF, NOT AN OS. Its job is to close the loop
 * m68k-elf-gcc -> ELF at 0xFC0000 -> 192 KB image -> `hatari --tos` -> a picture a host can check,
 * so that every component the recreate lands afterwards has somewhere to land. It sizes no memory,
 * installs no vectors, services no trap and never returns: it points the shifter at a fixed screen
 * address, loads a palette, paints sixteen horizontal colour bands and spins.
 *
 * WHAT THAT MAKES THE PICTURE. Sixteen bands of a known pen order is a pattern no partial failure
 * produces by accident: a wrong screen base shows the bands offset or absent, a wrong palette shows
 * the right shapes in the wrong colours, and a machine that never reached here shows Hatari's blank
 * surface (one colour, which is exactly what hatari_headless.distinct_colours counts).
 *
 * THE PALETTE LOOP MET BUG CLASS 6 ON ITS FIRST BUILD, which is the fourth independent sighting in
 * this workspace (docs/on-target-execution.md; Joust's palette loop, the BLACK ICE spike, BLACK
 * ICE again, this). `palette[pen] = STUB_PALETTE[pen]` over sixteen constant-addressed registers
 * folded to one instruction — `move.w (%a0)+,(%a0,%d0.l)`, with %d0 pre-biased by
 * $ffff8240 - STUB_PALETTE — and the 68000 computes a MOVE's destination effective address AFTER
 * the source's postincrement, so every pen landed one register high and the sixteenth write went
 * to $ffff8260, the RESOLUTION register, carrying pen 15's 0x555. The machine then displayed
 * low-resolution data in medium resolution: vertical red/green stripes instead of sixteen bands,
 * with nothing wrong in the C and nothing wrong in the geometry. `opaque()` below is the documented
 * fix; `volatile` is NOT one, because the fold is a choice of addressing mode and GCC still emits
 * exactly the one store the source asked for.
 */
#include <stdint.h>
#include "romdefs.h"

/* Sixteen visibly different $0RGB values — three bits a component, so 0..7 per channel. Pen 0 is
 * black because it is also the border colour, which keeps the ST's screen a recognisable rectangle
 * inside Hatari's capture. */
static const uint16_t STUB_PALETTE[BAND_COUNT] = {
    0x000, 0x700, 0x070, 0x007, 0x770, 0x707, 0x077, 0x777,
    0x400, 0x040, 0x004, 0x440, 0x404, 0x044, 0x333, 0x555,
};

/* A word of a bitplane is all-ones where the pen has that bit set and all-zeros where it does not,
 * so a whole row of one pen is these four words repeated across the row. */
#define PLANE_WORD_SET   0xFFFFu
#define PLANE_WORD_CLEAR 0x0000u

/* Launder a pointer through an empty asm constraint so the optimiser cannot see the constant it
 * came from, and therefore cannot fold a copy that uses it into one addressing mode. */
static void *opaque(void *pointer)
{
    __asm__("" : "+a"(pointer));
    return pointer;
}

static void load_palette(void)
{
    volatile uint16_t *palette = opaque((void *)PALETTE);
    int pen;

    for (pen = 0; pen < BAND_COUNT; pen++)
        palette[pen] = STUB_PALETTE[pen];
}

static void point_shifter_at_screen(void)
{
    *(volatile uint8_t *)VIDEO_BASE_HIGH = (uint8_t)(STUB_SCREEN_BASE >> 16);
    *(volatile uint8_t *)VIDEO_BASE_MID  = (uint8_t)(STUB_SCREEN_BASE >> 8);
    *(volatile uint8_t *)SYNC_MODE       = STUB_SYNC_MODE;
    *(volatile uint8_t *)SHIFTER_RES     = SHIFTER_RES_LOW;
}

/* One screen row filled with `pen`, written as the four interleaved plane words per 16-pixel group
 * that ST low resolution asks for. */
static void paint_row(uint16_t *row, int pen)
{
    int group, plane;

    for (group = 0; group < SCREEN_GROUPS_PER_ROW; group++)
        for (plane = 0; plane < SCREEN_PLANES; plane++)
            row[group * SCREEN_PLANES + plane] =
                (pen >> plane) & 1 ? PLANE_WORD_SET : PLANE_WORD_CLEAR;
}

/* Walked band by band rather than row by row with a `row / BAND_ROWS`: a 32-bit divide by a
 * constant is a call to a libgcc helper on the 68000, and a ROM with no C runtime linked has
 * nothing to call. */
static void paint_bands(void)
{
    uint16_t *row = (uint16_t *)STUB_SCREEN_BASE;
    int band, line;

    for (band = 0; band < BAND_COUNT; band++) {
        /* 200 rows over 16 bands leaves a remainder of eight, and the last band absorbs it rather
         * than the picture losing its bottom eight rows to pen 0. */
        int lines = (band == BAND_COUNT - 1) ? SCREEN_HEIGHT - band * BAND_ROWS : BAND_ROWS;

        for (line = 0; line < lines; line++) {
            paint_row(row, band);
            row += SCREEN_ROW_BYTES / 2;
        }
    }
}

void stub_boot(void)
{
    point_shifter_at_screen();
    load_palette();
    paint_bands();
    for (;;)
        ;                       /* the stub owns the machine from here; there is nothing to return to */
}
