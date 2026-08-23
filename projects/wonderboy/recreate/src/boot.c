/* boot.c — the BOOT CHAIN's block movers and its two resource installers.
 *
 * The boot chain is everything between the PRG entry and the `jmp $4a0` that starts the frame loop:
 * the relocator, the video and vector setup, the title and credits screens, the resource loads, the
 * depacks, and the two routines that turn a loaded file into something the engine can draw from.
 * ../STATUS.md's batch 44 phase A carries the inventory — which of its 57 routines are
 * reconstructed, which are not, and where the boundaries are. This file holds the first tranche.
 *
 * WHAT IS HERE AND WHY THESE. Every routine below is PURE MEMORY: no hardware register, no OS call,
 * no disk. That is what makes them differentiable at all — the rest of the boot chain is the raw
 * WD1772/DMA driver, the FAT12 layer above it, and the Copylock, none of which the memory
 * differential can see. `clear_palette` is the one boot routine that touches hardware and it lives
 * beside `set_palette` in src/stage.c, because the two share one shifter sink.
 *
 * THE TWO INSTALLERS ARE THE POINT. `bg_tile_install` and `sprites_cru_install` are the routines
 * recreate/atari/gen_image.py has named since batch 43 phase A as the reason the staged image cannot
 * be computed host-side: they are what turn TILEDATA.RAD and SPRITES.CRU into the tile bank at
 * WB_TILE_BITMAPS and the sprite cells at WB_SPRITE_CRU_CELLS. Their differentials run on the
 * game's own shipped files, so what is compared is the real product and not a synthetic one.
 */
#include "boot.h"

#include "bus.h"
#include "machine.h"
#include "wonderboy.h"

/* `move.l (a0)+,(a1)+` run `longs` times, with both cursors left where the post-increments leave
 * them. THREE routines below are this loop — `copy_longs`, the tile installer's bitmap copy and the
 * cell copiers' longword half — and it is shared rather than spelt three times for one reason worth
 * stating: it is ASCENDING and it is NOT a memmove. With the destination above the source it
 * re-reads bytes it has just written and smears the first longword through the whole run, which is
 * what the 68000 does and what test/test_boot.py pins in both overlap directions. Written out three
 * times, that property would hold in two of them by coincidence, and the first person to "optimise
 * the tile copy with memcpy" would break only the copy nothing pins.
 *
 * The cursors are POINTERS because that is what the original's address registers are: every caller
 * spends the advanced value, either as its own return or as the next iteration's source. */
static void copy_long_run(uint8_t *image, uint32_t *src, uint32_t *dst, unsigned longs) {
    while (longs-- != 0) {
        bus_write_long(image, *dst, bus_read_long(image, *src));
        *src = addr_add(*src, 4);
        *dst = addr_add(*dst, 4);
    }
}

/* $f93c. `move.l (a0)+,(a1)+ / dbf d0` — count_minus_1 + 1 longwords, which is why every caller
 * presets d0 rather than passing a length. TWO callers in the original, both the boot's 3200-byte
 * saves either side of the overlay depack ($e634 and $e658, d0 = $31f); `copy_screen` falls into it
 * with the count preset. `sprites_cru_install` is NOT one of them — its slide is an inline
 * `move.l (a1)+,(a0)+ / dbf` at $e88c and calling this from there is a factoring of THIS port. */
void copy_longs(uint8_t *image, uint32_t src, uint32_t dst, uint16_t count_minus_1) {
    copy_long_run(image, &src, &dst, (unsigned)count_minus_1 + 1);
}

/* $f938. Two instructions: the count, then the fall-through into `copy_longs`. One caller, the
 * boot's `lea $78000,a0 / lea $70000,a1 / bsr $f938` at $e59a — the credits screen copied down onto
 * the buffer the shifter is showing. */
void copy_screen(uint8_t *image, uint32_t src, uint32_t dst) {
    copy_longs(image, src, dst, (uint16_t)(WB_SCREEN_COPY_LONGS - 1));
}

/* $f926. One `clr.l (a0)+` run from WB_SCREEN_LOW. It is NOT two clears of WB_SCREEN_BYTES: the
 * count runs to the top of the HIGH buffer, so the 768 bytes between the buffers go with them. */
void clear_both_screens(uint8_t *image) {
    uint32_t at = WB_SCREEN_LOW;
    for (unsigned remaining = WB_SCREEN_CLEAR_LONGS; remaining != 0; remaining--) {
        bus_write_long(image, at, 0);
        at = addr_add(at, 4);
    }
}

/* $e67e. THE TILE INSTALLER — see WB_TILE_BANK in include/wonderboy.h for what it is for.
 *
 * THE INDEX IS READ BEFORE IT IS OVERWRITTEN, and the two happen at the same entry: `move.w (a0),d1`
 * takes the tile the overlay asked for, and after the copy `move.w d0,(a0)+` puts this entry's own
 * position there. So the pass is idempotent on the SECOND run only in the sense that the table is
 * then the identity — the bitmaps are re-copied from wherever the identity points, which is not
 * where they came from. Nothing in the game runs it twice.
 *
 * THE SOURCE INDEX IS A LONGWORD SHIFT ON A ZERO-EXTENDED WORD. `clr.l d1 / move.w (a0),d1 /
 * lsl.l #7,d1` reaches WB_TILE_BITMAP_LEN * 65535, so a large index names a real address well past
 * the depacked bank rather than a wrapped one; the bus helpers answer such a read the way the
 * oracle's shim does. The shipped overlays reach 660, which is inside the bank. */
void bg_tile_install(uint8_t *image) {
    uint32_t entry = WB_TILE_INDEX_TABLE;      /* a0 */
    uint32_t bitmap = WB_TILE_BITMAPS;         /* a2, filling upwards */
    uint16_t position = 0;                     /* d0 */

    do {
        /* The original spells the copy as eight unrolled `move.l (a1)+,(a2)+` under a four-iteration
         * `dbf`, which is these WB_TILE_BITMAP_LEN bytes in the same order. */
        uint32_t source = addr_add(WB_TILE_BANK,
                                   (uint32_t)bus_read_word(image, entry) << WB_BG_BUILD_TILE_SHIFT);
        copy_long_run(image, &source, &bitmap, WB_TILE_BITMAP_LEN / 4);
        bus_write_word(image, entry, position);
        entry = addr_add(entry, 2);
        position++;
    } while (position != WB_TILE_INSTALL_COUNT);

    /* The tail: eight more entries given their own position, with no bitmap behind them. */
    do {
        bus_write_word(image, entry, position);
        entry = addr_add(entry, 2);
        position++;
    } while (position != WB_TILE_INSTALL_END);
}

/* $e92c / $e938 / $e948 / $e95e — the four cell copiers `sprites_cru_install` dispatches through.
 * They are four unrolled widths of one loop, so they share one body here and differ only in their
 * word count. An ODD count leads with `move.w (a0)+,(a3)+` and then copies longwords, which is the
 * 68000's own way of moving an odd number of words and is what makes 5 and 15 different code from
 * 10 and 20 rather than the same code with a different constant.
 *
 * Each returns the ADVANCED destination, which is the one register the caller keeps: `a3` walks on
 * across every copier call of the whole install, while `a0` is reloaded from the next descriptor. */
static uint32_t sprite_cru_copy(uint8_t *image, uint32_t src, uint32_t dst,
                                uint16_t count_minus_1, unsigned words) {
    for (unsigned remaining = (unsigned)count_minus_1 + 1; remaining != 0; remaining--) {
        if (words & 1u) {
            bus_write_word(image, dst, bus_read_word(image, src));
            src = addr_add(src, 2);
            dst = addr_add(dst, 2);
        }
        copy_long_run(image, &src, &dst, words / 2);
    }
    return dst;
}

uint32_t sprite_cru_copy_5w(uint8_t *image, uint32_t src, uint32_t dst, uint16_t count_minus_1) {
    return sprite_cru_copy(image, src, dst, count_minus_1, WB_SPRITE_CRU_WORDS_5);
}

uint32_t sprite_cru_copy_10w(uint8_t *image, uint32_t src, uint32_t dst, uint16_t count_minus_1) {
    return sprite_cru_copy(image, src, dst, count_minus_1, WB_SPRITE_CRU_WORDS_10);
}

uint32_t sprite_cru_copy_15w(uint8_t *image, uint32_t src, uint32_t dst, uint16_t count_minus_1) {
    return sprite_cru_copy(image, src, dst, count_minus_1, WB_SPRITE_CRU_WORDS_15);
}

uint32_t sprite_cru_copy_20w(uint8_t *image, uint32_t src, uint32_t dst, uint16_t count_minus_1) {
    return sprite_cru_copy(image, src, dst, count_minus_1, WB_SPRITE_CRU_WORDS_20);
}

/* The dispatch at $e8f0..$e8fc, kept as a lookup of the TABLE LONGWORD rather than of the selector
 * byte: `movea.l 0(a1,d0.w),a1 / jsr (a1)` jumps to whatever that longword holds, so a case that
 * moved an entry — or a port that scaled the index wrong — has to show up here and not be absorbed
 * by a `switch` on the byte. A longword that is none of the four is the one thing this port cannot
 * reproduce: the original `jsr`s through it. See WB_SPRITE_CRU_UNKNOWN_COPIER for why no shipped
 * input reaches that, and test/test_boot.py for the census that says so. */
#define SPRITE_CRU_NO_COPIER 0u   /* no copier moves zero words, so 0 cannot be a real width */

static unsigned sprite_cru_copier_words(uint32_t copier) {
    static const struct { uint32_t entry; unsigned words; } COPIERS[WB_SPRITE_CRU_COPIERS] = {
        {WB_SPRITE_CRU_COPY_5W,  WB_SPRITE_CRU_WORDS_5},
        {WB_SPRITE_CRU_COPY_10W, WB_SPRITE_CRU_WORDS_10},
        {WB_SPRITE_CRU_COPY_15W, WB_SPRITE_CRU_WORDS_15},
        {WB_SPRITE_CRU_COPY_20W, WB_SPRITE_CRU_WORDS_20},
    };
    for (unsigned i = 0; i < WB_SPRITE_CRU_COPIERS; i++)
        if (COPIERS[i].entry == copier)
            return COPIERS[i].words;
    return SPRITE_CRU_NO_COPIER;
}

/* $e87c. See WB_SPRITE_CRU_LOAD in include/wonderboy.h for the shape of the file and the walk.
 *
 * THE STAGE ROW IS 16-BIT ARITHMETIC ADDED AS A LONGWORD. `clr.l d0 / move.w $bd88,d0` zero-extends,
 * and every step after it (`subq.w #6`, `subq.w #1`, `lsl.w #6`) is a WORD operation that cannot
 * carry into the half that was cleared — so `adda.l d0,a4` adds a zero-extended 16-bit product.
 * A stage number of 0 therefore indexes row -1 as $ffc0 and reads the mask words 64 KB ABOVE the
 * table, not below it. No shipped level_seq_table entry produces one.
 *
 * THE LAST GROUP IS ONE SLOT, not sixteen: `tst.w d5 / beq` skips the inner count when the outer
 * `dbf` is on its final pass. That is the whole reason the descriptor count is
 * (WB_SPRITE_CRU_GROUPS - 1) * WB_SPRITE_CRU_GROUP_SLOTS + 1 and not a round multiple.
 *
 * THE DESCRIPTOR'S POINTER IS READ AND REWRITTEN IN DIFFERENT SPACES. It arrives as an offset from
 * WB_SPRITE_CRU_BODY (the file body) and leaves as an offset from WB_RESOURCE_TABLE (the relocation
 * base `resource_table_relocate` at $fe1e later adds back). The two constants are 64 bytes and one
 * table apart, and swapping them is invisible to anything but the cells' own bytes.
 *
 * The `cmpa.l #$44000,a3` at $e8fe is DEAD — a `bra.w` follows it and nothing reads the flags. It is
 * not reproduced, and it is the only instruction of the routine that is not. */
uint32_t sprites_cru_install(uint8_t *image) {
    /* $e88c: slide the file's table down over WB_RESOURCE_HEADER. The original spells this loop
     * INLINE (`move.l (a1)+,(a0)+ / dbf`); calling `copy_longs` is this port's factoring of it, not
     * a call the 68000 makes. Forward copy with dst below src,
     * so the tail of the source is gone by the time the copy ends — which is fine here and is why
     * the descriptors below are read from the DESTINATION. */
    copy_longs(image, WB_SPRITE_CRU_LOAD, WB_RESOURCE_HEADER,
               (uint16_t)(WB_SPRITE_CRU_SLIDE_LONGS - 1));

    uint16_t row = (uint16_t)bus_read_word(image, WB_STAGE_NUMBER);
    if ((int16_t)row > (int16_t)WB_STAGE_NUMBER_BCD_LIMIT)
        row = (uint16_t)(row - WB_STAGE_NUMBER_BCD_CARRY);
    /* UNSIGNED throughout: `row` promotes to `int`, so a stage number of 0 would make this
     * `(-1) << 6` — undefined behaviour in C, on exactly the path the comment above describes as
     * indexing row -1. The 68000 wraps in 16 bits and so must this. */
    row = (uint16_t)(((unsigned)row - 1u) << WB_SPRITE_CRU_MASK_SHIFT);

    uint32_t mask = addr_add(WB_SPRITE_CRU_MASK_TABLE, row);   /* a4 */
    uint32_t cell = WB_SPRITE_CRU_CELLS;                       /* a3 */
    uint32_t descriptor = addr_add(WB_RESOURCE_HEADER, WB_SPRITE_CRU_FIRST_DESC);  /* a5 */

    for (unsigned group = WB_SPRITE_CRU_GROUPS; group != 0; group--) {
        uint16_t bits = bus_read_word(image, mask);            /* d7 */
        mask = addr_add(mask, 2);
        unsigned slots = (group == 1) ? 1 : WB_SPRITE_CRU_GROUP_SLOTS;
        for (unsigned slot = 0; slot < slots; slot++) {
            /* `rol.w #1,d7 / bcc`: the bit rotated out of the top is both the carry and the new
             * bit 0, and CARRY SET is the marked arm. */
            bits = (uint16_t)((bits << 1) | (bits >> 15));
            if ((bits & 1u) == 0) {
                bus_write_long(image, descriptor, WB_SPRITE_CRU_UNMARKED);
            } else {
                uint32_t source = addr_add(bus_read_long(image, descriptor), WB_SPRITE_CRU_BODY);
                bus_write_long(image, descriptor, cell - WB_RESOURCE_TABLE);
                uint32_t copier = bus_read_long(
                    image, addr_add(WB_SPRITE_CRU_COPY_TABLE,
                                    (uint16_t)(field_b(image, descriptor, WB_SPRITE_CRU_DESC_COPIER)
                                               << 2)));
                unsigned words = sprite_cru_copier_words(copier);
                /* REFUSE HERE rather than flagging and walking on. The original would `jsr` through
                 * that longword and never come back, so there is nothing after this point to be
                 * faithful TO — and a port that carried a flag to the end of the loop would lay
                 * every remaining marked sprite's cells at the same unadvanced address and stamp the
                 * same offset into each of their descriptors: hundreds of fabricated writes past the
                 * point it already knew it could not model the run. The one descriptor longword
                 * written just above STAYS written, because the original writes it before it reads
                 * the selector at all. */
                if (words == SPRITE_CRU_NO_COPIER)
                    return WB_SPRITE_CRU_UNKNOWN_COPIER;
                cell = sprite_cru_copy(image, source, cell,
                                       field_b(image, descriptor, WB_SPRITE_CRU_DESC_COUNT), words);
            }
            descriptor = addr_add(descriptor, WB_RESOURCE_RECORD_BYTES);
        }
    }
    return WB_SPRITE_CRU_INSTALLED;
}
