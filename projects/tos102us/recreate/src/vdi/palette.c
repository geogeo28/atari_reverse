/* palette.c — vs_color and vq_color: a VDI colour set into the shifter, and read back.
 *
 * Both are HAND-WRITTEN 68000 in the ROM ($fd2dd2..$fd2f21), not Alcyon C, and both keep TWO records
 * of a colour: what the application ASKED for, per mille per gun, in LINEA_REQ_COL (three words a
 * colour), and what the shifter REALIZED, three bits a gun, in the palette register the VDI index maps
 * to (VDI_MAP_COL). vq_color answers either, by intin[1].
 *
 * THE INDEX BOUND IS A BYTE COMPARE (`cmp.b d4,d0`) against the highest index for the plane count
 * (VDI_PEN_MASKS), but everything after it indexes with the whole WORD — so $8000 passes as colour 0
 * and is colour 0 throughout (its six-byte row wraps to 0 inside `mulu.w`), and $ff01 passes as
 * colour 1 and then reads a pen and a REQ_COL row far outside both tables. Far enough, for thirty
 * low-resolution indexes, that the palette store folds past the top of the bus into the exception
 * vectors — and from $1600 up, that the REQ_COL row lies below address 0, in the I/O page's
 * undecoded gap: vq_color READS it there (a declared I/O read, pinned), and vs_color's store to it
 * bus-errors on iron where the oracle drops it, which no differential can compare (unpinned).
 *
 * MONOCHROME (one plane) is its own arm in both. vs_color does not map the index at all: it rounds
 * each gun to black, keep, or white ($fd2e6e), and only an all-black or all-white request writes
 * register 0 — with the INDEX itself or its complement, the shifter's invert bit being bit 0 of it.
 * Every grey leaves the register alone.
 *
 * WHAT SHIPS IS `palette.S`, the ROM's own instructions — `vdi/transcribed.h` says so, and Tier 3's
 * mechanism (T) holds it at the bar: this C is what Tier 1's host differential proves, and it measures
 * over the 1.10 bar against hand 68000 that keeps no frame and saves one register, so the target build
 * carries the transcription (pinned byte for byte, `test_vdi_color.py`) — the user's rule for the
 * hand-written loops. The numbers both share are `vdi/palette.h`.
 */
#include <stdint.h>

#include "hw.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "vdi/inquire.h"
#include "vdi/palette.h"
#include "vdi/vdi.h"
#include "vdi/transcribed.h"

#define WORD_BYTES 2
#define GUNS       PALETTE_GUNS

/* The highest VDI index the plane count allows, as a byte — the ROM indexes the table with the
 * plane count sign-extended. */
static uint8_t pen_mask(const uint8_t *image)
{
    return image[VDI_PEN_MASKS + sign_ext16(be16(image + LINEA_PLANES))];
}

static int monochrome(const uint8_t *image)
{
    return be16(image + LINEA_PLANES) == PALETTE_MONO_PLANES;
}

/* EVERY ADDRESS BELOW IS AN ADDRESS REGISTER'S, a base plus a sign-extended word, and it reaches the
 * machine through the 68000's 24 address pins: folded, then RAM or the I/O page by where the fold
 * lands. So a requested row below address 0 (index $1600 and up) is a store into the I/O page, and a
 * pen whose doubled offset passes $7dc0 carries a palette store past $ffffff into low RAM — the
 * exception vectors at $40.. — both through indexes the byte bound lets by. */
static void bus_write16(uint8_t *image, uint32_t address, uint16_t value)
{
    address &= OS_BUS_ADDR_MASK;
    if (os_io_is_page(address))
        hw_write16(address, value);
    else
        wr16(image + address, value);
}

static uint16_t bus_read16(const uint8_t *image, uint32_t address)
{
    address &= OS_BUS_ADDR_MASK;
    return os_io_is_page(address) ? io_read16(address) : be16(image + address);
}

/* Where colour `index`'s three requested words are: `mulu.w #6` then `adda.w`, so the row WRAPS in a
 * word and is sign-extended. */
static uint32_t requested_row(uint16_t index)
{
    return LINEA_REQ_COL + word_index(index, PALETTE_REQ_COL_ROW_BYTES);
}

/* The palette register colour `index` is shown in: its VDI_MAP_COL pen, whose LOW BYTE alone is
 * masked (`and.b`) before it is doubled into an offset from $ff8240. */
static uint32_t palette_register(const uint8_t *image, uint16_t index, uint8_t mask)
{
    uint16_t pen = be16(image + (uint32_t)(VDI_MAP_COL + word_index(index, WORD_BYTES)));

    pen = set_low_byte(pen, (uint8_t)pen & mask);
    return SHIFTER_PALETTE + word_index(pen, PALETTE_ENTRY_BYTES);
}

/* $fd2dd2's gun: per mille, clamped to 0..1000 by SIGNED compares, to a three-bit level — rounded. */
static uint16_t shifter_level(int16_t per_mille)
{
    if (per_mille < 0)
        per_mille = 0;
    if (per_mille > PALETTE_PER_MILLE_MAX)
        per_mille = PALETTE_PER_MILLE_MAX;
    return (uint16_t)(per_mille + PALETTE_LEVEL_ROUNDING) / PALETTE_PER_MILLE_PER_LEVEL;
}

/* $fd2e6e — the monochrome gun: black, kept as given, or white — which is what makes the sum below
 * say "neither black nor white" for every grey. SIGNED compares, so a negative gun is black. */
static int16_t mono_level(int16_t per_mille)
{
    if (per_mille < PALETTE_MONO_BLACK_BELOW)
        return 0;
    if (per_mille < PALETTE_MONO_WHITE_FROM)
        return per_mille;
    return PALETTE_PER_MILLE_MAX;
}

/* One gun of a request: read from intin, stored into the REQ_COL row as given — and read only AFTER
 * the gun before it was stored, which is what intin laid over the row shows. */
static int16_t store_gun(uint8_t *image, uint32_t requested, const uint8_t *intin, unsigned gun)
{
    uint16_t per_mille = be16(intin + (1 + gun) * WORD_BYTES);

    bus_write16(image, requested + gun * WORD_BYTES, per_mille);
    return (int16_t)per_mille;
}

/* $fd2e44 — the monochrome arm: register 0 gets the index when all three guns are black, its
 * complement when all three are white, and nothing otherwise. */
static void set_mono(uint8_t *image, uint32_t requested, const uint8_t *intin, uint16_t index)
{
    int16_t sum = 0;

    for (unsigned gun = 0; gun < GUNS; gun++)
        sum += mono_level(store_gun(image, requested, intin, gun));
    if (sum == 0)
        hw_write16(SHIFTER_PALETTE, index);
    else if (sum == PALETTE_WHITE_SUM)
        hw_write16(SHIFTER_PALETTE, (uint16_t)~index);
}

/* $fd2dd2 — vs_color (14): intin[0] = index, intin[1..3] = red, green, blue per mille. An index over
 * the plane count's bound changes nothing; otherwise the request is stored as given and the register
 * written. It answers nothing. */
TRANSCRIBED_CORE
void vdi_vs_color(uint8_t *image)
{
    const uint8_t *intin = image + linea_pointer(image, LINEA_INTIN);
    uint16_t index = be16(intin);
    uint8_t mask = pen_mask(image);
    uint32_t requested;
    uint16_t colour = 0;

    if ((uint8_t)index > mask)
        return;
    requested = requested_row(index);
    if (monochrome(image)) {
        set_mono(image, requested, intin, index);
        return;
    }
    for (unsigned gun = 0; gun < GUNS; gun++)
        colour = (uint16_t)(colour << PALETTE_GUN_BITS) | shifter_level(store_gun(image, requested, intin, gun));
    bus_write16(image, palette_register(image, index, mask), colour);
}

/* $fd2e84 — vq_color (26): intin[0] = index, intin[1] = 0 for the colour REQUESTED, anything else for
 * the colour REALIZED. contrl[4] = 4 first, whatever follows; an index over the bound answers -1 in
 * intout[0] and nothing else. Otherwise intout[0] is the index as given (the whole word), then three
 * per-mille words:
 *   requested  — LINEA_REQ_COL's row, whatever vs_color stored (unclamped);
 *   realized   — the register's three-bit guns through VDI_VQ_COLOR_LEVELS (0, 142, ... 1000); on one
 *                plane, 1000 on all three guns when bit 0 of (index ^ register 0) is set, else 0. */
static void answer_three(uint8_t *intout, uint16_t red, uint16_t green, uint16_t blue)
{
    wr16(intout, red);
    wr16(intout + WORD_BYTES, green);
    wr16(intout + 2 * WORD_BYTES, blue);
}

/* The requested row, a word read and a word answered in turn (`move.w (a1)+,(a0)+` three times) —
 * which intout laid over the row shows. */
static void answer_requested(const uint8_t *image, uint8_t *intout, uint16_t index)
{
    uint32_t requested = requested_row(index);

    for (unsigned gun = 0; gun < GUNS; gun++)
        wr16(intout + gun * WORD_BYTES, bus_read16(image, requested + gun * WORD_BYTES));
}

static void answer_realized(const uint8_t *image, uint8_t *intout, uint16_t index, uint8_t mask)
{
    uint16_t shown;

    if (monochrome(image)) {
        uint16_t inverted = (index ^ io_read16(SHIFTER_PALETTE)) >> PALETTE_MONO_INVERT_BIT & 1;
        uint16_t level = inverted ? PALETTE_PER_MILLE_MAX : 0;
        answer_three(intout, level, level, level);
        return;
    }
    shown = bus_read16(image, palette_register(image, index, mask));
    for (unsigned gun = 0; gun < GUNS; gun++) {
        unsigned level = shown >> (PALETTE_GUN_BITS * (GUNS - 1 - gun)) & PALETTE_GUN_LEVEL_MASK;
        wr16(intout + gun * WORD_BYTES, be16(image + VDI_VQ_COLOR_LEVELS + level * WORD_BYTES));
    }
}

TRANSCRIBED_CORE
void vdi_vq_color(uint8_t *image)
{
    const uint8_t *intin;
    uint16_t index;
    uint16_t realized;
    uint8_t *intout;
    uint8_t mask;

    answer_words(image, PALETTE_VQ_COLOR_INTOUT_WORDS);
    intin = image + linea_pointer(image, LINEA_INTIN);
    index = be16(intin);
    realized = be16(intin + WORD_BYTES);
    intout = image + linea_pointer(image, LINEA_INTOUT);
    mask = pen_mask(image);
    if ((uint8_t)index > mask) {
        wr16(intout, (uint16_t)PALETTE_INVALID);
        return;
    }
    wr16(intout, index);
    intout += WORD_BYTES;
    if (realized)
        answer_realized(image, intout, index, mask);
    else
        answer_requested(image, intout, index);
}
