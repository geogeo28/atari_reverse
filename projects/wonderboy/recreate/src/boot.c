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
 * beside `set_palette` in src/stage.c, because it IS `set_palette` with a zero for a source. (The
 * reason given here through batch 44 phase E — "because the two share one shifter sink" — is
 * RETRACTED: the sink is ../include/shifter.h's and every file reaches it, so sharing it is no
 * longer a reason for anything to live anywhere.)
 *
 * THE TWO INSTALLERS ARE THE POINT. `bg_tile_install` and `sprites_cru_install` are the routines
 * recreate/atari/gen_image.py has named since batch 43 phase A as the reason the staged image cannot
 * be computed host-side: they are what turn TILEDATA.RAD and SPRITES.CRU into the tile bank at
 * WB_TILE_BITMAPS and the sprite cells at WB_SPRITE_CRU_CELLS. Their differentials run on the
 * game's own shipped files, so what is compared is the real product and not a synthetic one.
 */
#include "boot.h"

#include "actor.h"
#include "bus.h"
#include "disk.h"
#include "machine.h"
#include "rad.h"
#include "shifter.h"  /* the base publish and the credits pen — the port's one sink */
#include "sound.h"
#include "stage.h"
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

/* ================================================================================================
 * THE LOAD PATH ABOVE THE DISK SEAM (batch 44 phase B)
 *
 * Everything below this line runs ABOVE `disk_load_file` ($5e7c) — the lowest routine of the boot
 * chain whose inputs are file-shaped. That routine and the 1,644 bytes it reaches are a declared
 * BOUNDARY (../STATUS.md batch 44 phase B; the census that says the boot chain crosses it exactly
 * once is in test/test_boot_inventory.py), and `load_resource_by_index` calls the kit's
 * `disk_read_file` across it. Off target that is the staged-file model; on target it is GEMDOS.
 * ================================================================================================ */

/* $e782. THE SINGLE ENTRY POINT FOR ALL DISK LOADING — seven call sites in the image.
 *
 * THE ROW IS ALREADY A FILENAME, which is most of what makes the seam cheap. `lsl.l #4,d0 /
 * lea WB_RESOURCE_FILE_TABLE,a0 / lea (a0,d0.w),a0` lands on sixteen bytes holding a NUL-terminated
 * "NNNNNNNN.EEE", and `fat_find_dir_entry` compares exactly those twelve characters (skipping the
 * dot at [8]) against a FAT12 directory entry. So the same pointer this port hands `disk_read_file`
 * is the one the original hands its own reader.
 *
 * IT IS NOT QUITE FREE, AND THE EXCEPTION IS TWO ROWS. FAT12 space-pads a short stem to eight
 * characters, so `CREDITS .RAD` and `SPRITES .CRU` carry an INTERNAL space. The kit's staged-file
 * model matches bytes and has no path syntax, so off target the row goes through untranslated;
 * GEMDOS has a path syntax in which a space is a real character, so the ON-TARGET backend drops
 * spaces before `Fopen`. That is a difference between the two statements of the substitution, it
 * lives entirely below this seam, and it is pinned as a SET in test/test_boot.py — an earlier
 * revision of this banner claimed no translation at all, and the machine disagreed.
 *
 * THE INDEX IS SCALED AS A LONGWORD AND USED AS A WORD. `lsl.l #4` reaches past 16 bits, but the
 * `lea`'s brief extension word selects `d0.w` and SIGN-EXTENDS it — so an index of $1000 names the
 * table itself and an index of $0800 names 32 KB BELOW it. No caller produces either; the shipped
 * indices are 0..$27 and `stage_sequence_resource` below cannot exceed $ff.
 *
 * TWO IMAGE WRITES BEFORE THE LOAD, ALWAYS: d0 and a1 into WB_LOAD_RETRY_INDEX/_DEST. They exist for
 * the error path's retry and are written whether or not it is taken.
 *
 * WHAT THIS PORT DECLINES TO MODEL, and it is one thing: the error arm's INTERACTIVE RETRY. On a
 * negative return the original turns colour 0 red, clears WB_JOY1_STATE, spins until the IKBD
 * handler makes it negative, restores d0/a1 and loads again. The spin is an interrupt-driven wait
 * whose release is not this run's to schedule, and the colour is off-image. What IS an image write
 * is the `clr.b` — so the port makes that write and returns WB_LOAD_DISK_ERROR at WB_LOAD_ERROR_WAIT,
 * which is where test/test_boot.py stops the oracle. Reported rather than retried, because a port
 * that looped here would be inventing a second load the case never asked for.
 *
 * THE ARMED ARM RUNS THE COPYLOCK, which cannot be ported and is not stubbed here either: the port
 * reports WB_LOAD_COPYLOCK_RAN and clears the flag, which is what the original does either side of
 * the call. The oracle reaches the same state only because test/copylock.py has poked an `rts` over
 * the blob — so a case on this arm owes the witness that the protection really did not execute, and
 * copylock.py's own docstring names this differential as the one that must call it by hand. */
uint32_t load_resource_by_index(uint8_t *image, uint32_t index, uint32_t dest) {
    bus_write_long(image, WB_LOAD_RETRY_INDEX, index);
    bus_write_long(image, WB_LOAD_RETRY_DEST, dest);

    uint32_t scaled = index << WB_RESOURCE_FILE_ROW_SHIFT;
    uint32_t name = addr_add(WB_RESOURCE_FILE_TABLE, sign_ext16(scaled));

    if (disk_read_file(image, name, dest) != DISK_READ_OK) {
        bus_write_byte(image, WB_JOY1_STATE, 0);
        return WB_LOAD_DISK_ERROR;
    }
    if (bus_read_word(image, WB_COPYLOCK_ARM_FLAG) == 0)
        return WB_LOAD_OK;
    bus_write_word(image, WB_COPYLOCK_ARM_FLAG, 0);
    return WB_LOAD_COPYLOCK_RAN;
}

/* $e768. Two `bsr` callers, both in `stage_actors_init`, and WB_STAGE_SIDE_FLAG's ONLY reader. */
void actor_apply_stage_side(uint8_t *image, uint32_t record) {
    if (bus_read_word(image, WB_STAGE_SIDE_FLAG) != 0)
        flag_set(image, record, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
    else
        flag_clear(image, record, WB_ACTOR_FLAGS, WB_ACTOR_FLAG_SIDE_BIT);
}

/* $e710. The stage's actors, from nothing: empty all three tables, then give the two FOLLOWED
 * records — slot WB_ACTOR_FOLLOWED_SLOT of the default table and of the A32 one — the shape the
 * player enters a stage with. The A30 table has no followed record and gets none.
 *
 * THE THREE FIELDS ARE WRITTEN OVER A RECORD `actor_table_reset` HAS ALREADY ZEROED, so the order of
 * the two passes is load-bearing: reversing them would leave the type at 0. */
void stage_actors_init(uint8_t *image) {
    static const uint32_t TABLES[] = {WB_ACTOR_TABLE_DEFAULT, WB_ACTOR_TABLE_A30,
                                      WB_ACTOR_TABLE_A32};
    static const uint32_t FOLLOWED[] = {WB_ACTOR_FOLLOWED_DEFAULT, WB_ACTOR_FOLLOWED_A32};

    for (unsigned i = 0; i < sizeof TABLES / sizeof TABLES[0]; i++)
        actor_table_reset(image, TABLES[i]);

    for (unsigned i = 0; i < sizeof FOLLOWED / sizeof FOLLOWED[0]; i++) {
        set_field_w(image, FOLLOWED[i], WB_ACTOR_TYPE, WB_ACTOR_TYPE_PLAYER);
        set_field_w(image, FOLLOWED[i], WB_ACTOR_HALF_WIDTH, WB_STAGE_ENTRY_HALF_WIDTH);
        set_field_w(image, FOLLOWED[i], WB_ACTOR_SIZE_SECOND, WB_STAGE_ENTRY_SIZE_SECOND);
        actor_apply_stage_side(image, FOLLOWED[i]);
    }
}

/* $e5ba..$e5f2 — see boot.h for why the dispatcher is three functions and not one.
 *
 * THE ROW IS THE PRE-INCREMENT VALUE, AND THE STORE HAPPENS FIRST. `move.w $216be,d0` takes the old
 * index into d0, `addq.w #1,$216be` steps the word in memory, and only then does the shift scale d0
 * — so the row is the index the run ARRIVED with, and a run that fails after this point has already
 * consumed it. Reading the word back after the store would name the NEXT row. */
uint32_t stage_sequence_advance(uint8_t *image) {
    bus_write_word(image, WB_ACTOR_PLATFORM_RIDDEN, 0);

    uint16_t at = bus_read_word(image, WB_LEVEL_SEQ_INDEX);
    bus_write_word(image, WB_LEVEL_SEQ_INDEX, (uint16_t)(at + 1));
    /* `lsl.l #3` on a zero-extended word, indexed as `d0.w` — the same longword-scale/word-index
     * pairing load_resource_by_index has, and with the same sign extension past row 4095. */
    uint32_t row = addr_add(WB_LEVEL_SEQ_TABLE,
                            sign_ext16((uint32_t)at * WB_LEVEL_SEQ_RECORD_BYTES));

    /* CLEARED UNCONDITIONALLY, then set only on the first entry to the stage. A re-entry (a life
     * lost, WB_LIFE_RESTART_ENTRY_C26 nonzero) leaves it zero, which is what stops the boot's
     * SPRITES.CRU load — and the protection with it — running a second time. */
    bus_write_byte(image, WB_STAGE_SECOND_LOAD_FLAG, 0);
    if (bus_read_word(image, WB_LIFE_RESTART_ENTRY_C26) == 0)
        bus_write_byte(image, WB_STAGE_SECOND_LOAD_FLAG,
                       field_b(image, row, WB_LEVEL_SEQ_SECOND_LOAD));
    return row;
}

uint32_t stage_sequence_resource(uint8_t *image, uint32_t row) {
    /* `addq.b #2,d0` over a zero-extended byte: the sum is taken in EIGHT bits and the upper 24 of
     * d0 stay zero, so $ff + 2 is 1 and not $101. */
    return (uint8_t)(field_b(image, row, WB_LEVEL_SEQ_OVERLAY) + WB_RESOURCE_FIRST_OVERLAY);
}

void stage_sequence_apply_row(uint8_t *image, uint32_t row) {
    bus_write_word(image, WB_STAGE_SIDE_FLAG,
                   field_b(image, row, WB_LEVEL_SEQ_SIDE) != 0 ? WB_STATE_FLAG_SET : 0);
    /* `clr.w d0 / move.b 3(a0),d0 / move.w d0,$bd88` — a zero-extended BYTE, so the stage number is
     * never negative however the row is filled. */
    bus_write_word(image, WB_STAGE_NUMBER, field_b(image, row, WB_LEVEL_SEQ_STAGE));
}


/* ================================================================================================
 * THE BOOT CHAIN COMPOSED (batch 44 phases C and E)
 *
 * Everything above this line is a routine the boot CALLS. The four below are the boot ITSELF — the
 * straight-line runs of those calls that lie between $e4e6's prologue and the `jmp $4a0.w` that
 * starts the frame loop, plus the data-disk prompt the ESC ending unwinds into, which falls through
 * into that same prologue. Nothing here is new behaviour: every callee was reconstructed in phase A or
 * B, or in batches 12/26 for src/stage.c's. What these add is the ORDER and the OPERANDS, which is
 * exactly what an inventory of individually-verified leaves cannot state.
 *
 * WHERE THE CUTS FALL, AND WHY THERE. The boot breaks three times for a FIRE WAIT — `clr.b
 * WB_JOY1_STATE`, then `tst.b / bpl` until the IKBD handler makes the byte negative and `tst.b /
 * bmi` until it is positive again. That is a spin on a byte no instruction of the run writes, so it
 * is the shim's and the schedule model's business and not C's (../atari/README.md §13), and the
 * waits are therefore the natural boundaries: each function starts where a wait ended and stops
 * where the next one begins. WB_BOOT_TITLE_AT/_END and their three pairs in include/wonderboy.h are
 * those addresses, and test/test_boot_chain.py enters and stops the oracle at exactly them. The
 * PROMPT slice ends at a FOURTH wait of the same shape ($e4d6), which is cut the same way.
 *
 * WHAT IS NOT HERE, and it is one block: the PROLOGUE at $e4e6..$e510 — `video_set_lowres_50hz`,
 * `clear_palette`, `clear_both_screens`, the MFP timer masks, the vbl vector and two `move.w #imm,sr`.
 * Two of its six steps ARE reconstructed (the palette clear and the screen clear), and they are
 * still left out, because the other four are privileged hardware setup a C function cannot make and
 * splitting the block would leave the shim holding two halves of one prologue. WHAT ../atari/'s
 * title build ACTUALLY DOES with it is a shorter list and is stated there rather than assumed here:
 * it makes the palette and screen clears and publishes the video mode, and it DECLARES the rest as
 * deviations — the MFP timer masks are not made and the vbl vector it installs is its own, not
 * $716 (atari/README.md §13's deviation list). The differential ranges below start at $e512, past
 * all six, either way.
 *
 * WHAT EACH SLICE REPORTS. One of the WB_LOAD_* codes, and it is out of band for the same reason
 * `load_resource_by_index`'s are — the original leaves d0 holding whatever its last call left and
 * nothing reads it. A refused load STOPS the slice where it happened: the original would be sitting
 * in the error arm's interactive retry (see load_resource_by_index above) and everything after that
 * point would be inflating a buffer the file never arrived in, so carrying on would be inventing a
 * run rather than reproducing one.
 * ================================================================================================ */

/* One of a slice's loads, and what the slice makes of the answer. Returns whether the chain may go
 * on — it may not once the seam has refused — and raises `*report` to WB_LOAD_COPYLOCK_RAN for the
 * load that took the armed arm, so a slice with three loads still has one code to hand back.
 *
 * A REFUSAL DISCARDS THE FOLD, deliberately: the caller returns WB_LOAD_DISK_ERROR outright rather
 * than a code meaning "the protection ran and then a load was refused". There is one code to give
 * and the refusal is the one the caller has to act on.
 *
 * WHAT A WB_LOAD_DISK_ERROR RETURN LEAVES BEHIND, since the code itself says none of it. TWO
 * residues, and neither is recoverable from the other:
 *   1. WB_COPYLOCK_ARM_FLAG MAY BE LEFT ARMED. `load_resource_by_index` clears it on exactly one
 *      path — the load that was armed AND was served — and its error return never touches it. So a
 *      refused load that the slice had armed returns with $ffff still standing (boot_title_screen's
 *      only load, and boot_load_stage's SPRITES.CRU load, are both of that kind). A CLEARED flag is
 *      no better as evidence: it reads the same whether the guard ran or nothing ever armed it.
 *   2. WB_LEVEL_SEQ_INDEX HAS ALREADY BEEN STEPPED in boot_load_stage, because $e5ba's
 *      `stage_sequence_advance` consumes the row before the first load is asked for.
 *
 * SO A RETRY MUST NOT BE A SECOND CALL TO THE SLICE. The original retries the same load IN PLACE,
 * inside `load_resource_by_index`'s interactive error arm, and can therefore never skip a sequence
 * row nor arm a load it did not mean to. A caller that instead retried by RE-ENTERING one of these
 * functions owes both residues first — put WB_LEVEL_SEQ_INDEX back, and disarm the flag. Nothing
 * here does that for it; the stop is a declared deviation and stays one. */
static int load_or_stop(uint8_t *image, uint32_t index, uint32_t dest, uint32_t *report) {
    uint32_t result = load_resource_by_index(image, index, dest);

    if (result == WB_LOAD_COPYLOCK_RAN)
        *report = result;
    return result != WB_LOAD_DISK_ERROR;
}

/* $e494..$e4d4. THE DATA-DISK PROMPT — the fourth slice, and the one the boot never runs.
 *
 * WHO REACHES IT, AND IT IS THREE PLACES. The shipped image holds exactly three `jmp $e494.l` and
 * they are three different endings sharing one destination — an earlier revision of this plate
 * counted one, and named the wrong one:
 *
 *   $598   `game_key_actions`' ESC arm (../include/game.h's WB_KEY_ACTIONS_QUIT), and the only one
 *          of the three that fades the music first: `jsr 84(a0)` at $594 is snd_start_fadeout
 *   $bdc   `player_pending_event_gate`'s game-over box expiring, after `lea 4(a7),a7` at $bd8
 *          discards ONE return address — and with NO fade; the two instructions are adjacent
 *   $700e  `actor_behavior_type61`'s message sequence reaching its terminator, after
 *          `movea.l #$80000,a7` throws the whole stack away. The Copylock failure path enters that
 *          same sequence, which is why $700e is reached on two quite different occasions
 *
 * NONE OF THEM IS AN EXIT: the picture goes up, the player presses fire at $e4d6, and the wait
 * FALLS THROUGH into $e4e6 — the boot continuation — which draws the title again. Every one of the
 * three restarts the game.
 *
 * TWO EXTENTS AND THEY ARE NOT THE SAME NUMBER. `boot_prompt_screen` reconstructs $e494..$e4d4, the
 * SLICE — up to and including `set_palette` at $e4d0. The routine's PROMPT HALF runs to $e4e4,
 * because $e4d6..$e4e4 is the fire wait, which is hardware and stays the shim's; $e4e4 is where the
 * fall-through happens. (Ghidra's function at $e494 is 632 bytes because it swallows the boot
 * continuation beyond that; ../names.txt cmt 0xe494 has that census.)
 *
 * THE SCREEN BASE IS PUBLISHED HERE AND NOWHERE ELSE IN THE FOUR SLICES. `move.b #$7,$ff8201.l /
 * move.b #$80,$ff8203.l` is WB_PROMPT_SCREEN_BASE, i.e. WB_SCREEN_HIGH, which is the buffer the
 * depack two calls later fills — so the picture is shown out of the buffer it lands in and no copy
 * is needed, where `boot_credits_screen` inflates into the same buffer and copies down because the
 * shifter is pointed at the other one. It goes through the port's ONE shifter sink
 * (../include/shifter.h): the address is off the loaded image, the oracle drops the write and the
 * on-target arm performs it, and a second copy of that arm in this file is what the shared module
 * avoids. WHICH REGISTERS AND WHICH BYTES is decoded out of the shipped instructions in
 * test/test_boot_chain.py, so the write's identity is pinned even while its happening is not.
 *
 * THE CLEAR COMES FIRST. `bsr.w $e7f4` is `clear_palette`, before the base and before the load, so
 * the screen the base is about to show is black until `set_palette` puts this picture's own row up.
 * It writes no image byte, which is why nothing below it can observe the order. */
uint32_t boot_prompt_screen(uint8_t *image) {
    uint32_t report = WB_LOAD_OK;

    (void)clear_palette(image);
    shifter_screen_base_write((uint8_t)(WB_PROMPT_SCREEN_BASE >> 16),
                              (uint8_t)(WB_PROMPT_SCREEN_BASE >> 8));
    if (!load_or_stop(image, WB_RESOURCE_DATADISK, WB_RESOURCE_LOAD_BUFFER, &report))
        return WB_LOAD_DISK_ERROR;
    (void)rad_depack(image, WB_RESOURCE_LOAD_BUFFER, WB_PROMPT_DEPACK_DEST);
    (void)set_palette(image, WB_PROMPT_PALETTE_SRC);
    return report;
}

/* $e512..$e550. THE FIRST PICTURE, and the first load of the run.
 *
 * THE PROTECTION IS ARMED HERE AND NOWHERE EARLIER. `move.w #$ffff,$e7cc.l` at $e51e is what makes
 * the load below take `load_resource_by_index`'s armed arm, so this slice reports
 * WB_LOAD_COPYLOCK_RAN on every run in which the seam serves the file — which is the port's way of
 * saying the blob would have executed, since it cannot be reproduced. ../atari/'s SMOKE_TITLE build
 * deliberately does NOT arm it and says why; a differential of this function does, because the
 * original does.
 *
 * THE DEPACK IS AIMED WB_RAD_PICTURE_PREFIX BELOW THE SCREEN, which is what puts the picture in
 * WB_SCREEN_LOW without a copy: the file inflates to a prefix and exactly one screen, and the
 * palette row the next call reads is inside that prefix. Both are cross-pinned in
 * test/test_boot_chain.py rather than argued here.
 *
 * THE SOUND REQUEST IS PART OF THE SLICE. `move.w #$8,d0 / lea $17adc.l,a0 / jsr (a0)` is stub 0 of
 * the sound module — snd_play_song — and it is the one call here that leaves state a later frame
 * reads. */
uint32_t boot_title_screen(uint8_t *image) {
    uint32_t report = WB_LOAD_OK;

    bus_write_word(image, WB_COPYLOCK_ARM_FLAG, WB_STATE_FLAG_SET);
    if (!load_or_stop(image, WB_RESOURCE_TITLESCR, WB_RESOURCE_LOAD_BUFFER, &report))
        return WB_LOAD_DISK_ERROR;
    (void)rad_depack(image, WB_RESOURCE_LOAD_BUFFER, WB_TITLE_DEPACK_DEST);
    (void)set_palette(image, WB_TITLE_PALETTE_SRC);
    snd_play_song(image, WB_TITLE_SONG);
    return report;
}

/* $e562..$e5a2. THE CREDITS, AND THE NEW GAME.
 *
 * IT INFLATES ONTO THE OTHER BUFFER AND THEN COPIES DOWN. The depack is aimed at
 * WB_CREDITS_DEPACK_DEST, so the picture lands in WB_SCREEN_HIGH, and `copy_screen` moves it to
 * WB_SCREEN_LOW — the buffer the shifter was pointed at by the prologue. The title slice needed no
 * such copy because its own depack landed in WB_SCREEN_LOW directly; this one cannot inflate there,
 * because that is where the title picture the player is still looking at is.
 *
 * `game_restart_reset` IS A NEW GAME, not a redraw: it clears WB_LEVEL_SEQ_INDEX, so the stage slice
 * below starts at row 0. THE ORDER OF IT AND THE COPY IS THE LISTING'S AND IS NOT PINNED, which was
 * measured rather than assumed — swapping them is a surviving mutant (../STATUS.md, batch 44 phase
 * C). It draws the lives into BOTH screen buffers at the same offsets and the copy makes the two
 * equal either way, so reset-then-copy ends on identical memory. Faithful order, unpinnable claim.
 *
 * THE PEN IS THE ONE THING NO DIFFERENTIAL CAN SEE. `move.w #$77,$ff8254.l` raises colour register
 * WB_CREDITS_PROMPT_PEN after the picture's own palette has been set, and it goes through
 * src/stage.c's sink for `set_palette`'s reason: the address is off the loaded image, the oracle
 * drops the write, and the on-target arm performs it. What a case CAN show is that neither side
 * leaves an image byte behind for it, and test/test_boot_chain.py says exactly that and no more. */
uint32_t boot_credits_screen(uint8_t *image) {
    uint32_t report = WB_LOAD_OK;

    if (!load_or_stop(image, WB_RESOURCE_CREDITS, WB_RESOURCE_LOAD_BUFFER, &report))
        return WB_LOAD_DISK_ERROR;
    (void)rad_depack(image, WB_RESOURCE_LOAD_BUFFER, WB_CREDITS_DEPACK_DEST);
    (void)set_palette(image, WB_CREDITS_PALETTE_SRC);
    copy_screen(image, WB_SCREEN_HIGH, WB_SCREEN_LOW);
    game_restart_reset(image);
    shifter_palette_write(WB_CREDITS_PROMPT_PEN, WB_CREDITS_PROMPT_COLOUR);
    return report;
}

/* $e5ba..$f8b4. THE PER-STAGE LOAD — every stage the game plays is entered through this.
 *
 * IT ENDS IN A TRANSFER AND NOT IN A RETURN. $e6fc's `bsr.w $f89e` never comes back: $f89e loads the
 * hinge's three registers, calls it, and `jmp $4a0.w`s into game_main_loop. So the two instructions
 * after that `bsr` — $e700's `move.b #$ff,$c030.l` and $e708's own `jmp $4a0.w` — are unreachable,
 * and they are not reproduced. The C returns instead, which is the port's statement of "the original
 * would be in the frame loop now"; its caller is what jumps.
 *
 * THE SAVE AND RESTORE AROUND THE OVERLAY DEPACK ARE ABOUT ONE TABLE. WB_RESOURCE_HEADER lies past
 * the program's last byte and arrives from disk (../../names.txt's cmt 0x24898): the signature byte
 * `resource_table_relocate` guards on, the record count, and WB_RESOURCE_TABLE's records — which
 * `sprites_cru_install` has filled with the stage's sprite cells. The overlay inflates over
 * $217d8..$254c0, which CROSSES that table, so the WB_RESOURCE_TABLE_SAVE_LONGS longwords are parked
 * at WB_RESOURCE_TABLE_SAVE and put straight back. Whatever the overlay put there is discarded,
 * unread; on the first stage of a run the parked bytes are the RAM's own, and it is SPRITES.CRU,
 * loaded a few instructions later, that fills the table for the first time.
 *
 * TILEDATA.RAD IS LOADED INTO THE BACKGROUND BUFFER. `lea $44000.l,a1` is WB_BG_BUFFER_BASE, which
 * the hinge's first builder will draw the stage's window into at the end of this same slice — so the
 * packed file is parked in the one large buffer whose contents are about to be overwritten anyway.
 * The two uses are the same address and are spelt as the one constant.
 *
 * THE SECOND LOAD IS THE STAGE'S SPRITES, AND IT IS GATED. WB_STAGE_SECOND_LOAD_FLAG comes out of the
 * sequence row, but only on a FIRST entry — `stage_sequence_advance` leaves it zero whenever
 * WB_LIFE_RESTART_ENTRY_C26 is set — so a life lost re-enters the stage without reloading
 * SPRITES.CRU. THE PROTECTION GOES WITH IT: $e6dc's arming is INSIDE the gate, so an arm that is not
 * taken never arms and never runs the guard. A MAJORITY of the game's own 35 sequence rows carry a
 * zero in that byte and take the same arm on a FIRST entry — so the one-load arm is the ordinary
 * case and not an edge one, which an earlier revision of this banner had backwards. The count lives
 * in test/test_boot_chain.py's SHIPPED_ONE_LOAD_ROWS, which measures it off the table; a number in
 * prose that nothing counts is a number that drifts.
 *
 * THE `clr.w` AT $e6ec IS WHAT MAKES THE RE-ENTRY ARM ONE-SHOT: the flag that suppressed the load is
 * taken down once the stage is built, so the NEXT stage loads its sprites again. */
uint32_t boot_load_stage(uint8_t *image) {
    uint32_t report = WB_LOAD_OK;
    uint32_t row = stage_sequence_advance(image);

    if (!load_or_stop(image, stage_sequence_resource(image, row), WB_RESOURCE_LOAD_BUFFER, &report))
        return WB_LOAD_DISK_ERROR;
    stage_sequence_apply_row(image, row);

    copy_longs(image, WB_RESOURCE_HEADER, WB_RESOURCE_TABLE_SAVE,
               (uint16_t)(WB_RESOURCE_TABLE_SAVE_LONGS - 1));
    (void)rad_depack(image, WB_RESOURCE_LOAD_BUFFER, WB_OVERLAY_DEPACK_DEST);
    copy_longs(image, WB_RESOURCE_TABLE_SAVE, WB_RESOURCE_HEADER,
               (uint16_t)(WB_RESOURCE_TABLE_SAVE_LONGS - 1));

    if (!load_or_stop(image, WB_RESOURCE_TILEDATA, WB_BG_BUFFER_BASE, &report))
        return WB_LOAD_DISK_ERROR;
    (void)rad_depack(image, WB_BG_BUFFER_BASE, WB_TILE_BANK);
    bg_tile_install(image);

    if (bus_read_byte(image, WB_STAGE_SECOND_LOAD_FLAG) != 0) {
        bus_write_word(image, WB_COPYLOCK_ARM_FLAG, WB_STATE_FLAG_SET);
        if (!load_or_stop(image, WB_RESOURCE_SPRITES_CRU, WB_SPRITE_CRU_LOAD, &report))
            return WB_LOAD_DISK_ERROR;
        (void)sprites_cru_install(image);
    }

    bus_write_word(image, WB_LIFE_RESTART_ENTRY_C26, 0);
    stage_actors_init(image);
    resource_table_relocate(image);
    stage_reset_state(image);
    /* $f89e's three `lea`s, in the hinge's own argument order: map (a0), start (a1), tiles (a6).
     * The start record IS the head of the overlay just inflated at WB_OVERLAY_DEPACK_DEST. */
    stage_load_window(image, WB_MAP_ROW_STRIDE, WB_OVERLAY_DEPACK_DEST, WB_TILE_BITMAPS);
    return report;
}
