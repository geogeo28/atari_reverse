/* text_raster.c — the TEXT RASTER: $a008 TextBlt and v_gtext's byte-aligned fast path, and the CPU bodies
 * behind drawing vectors 9 and 5.
 *
 *   $fcee54 $a008 textblt          A6 = the Line-A base, A5/A6 pushed          -> vector 9 ($fd1df6)
 *   $fcf96a fast_text_try          x on a byte and inside the clip, else 0    -> vector 5 ($fd1cc4)
 *
 * TEXTBLT COPIES ONE GLYPH — the DELX x DELY rectangle at (SOURCEX, SOURCEY) of the font form FBASE,
 * FWIDTH bytes a line — to (DESTX, DESTY) on the screen, in TEXT_FG, and advances DESTX (or DESTY, when
 * rotated) past it. It is the ROM's longest hand-written routine, and it reads as four layers:
 *
 *   * THE BLIT ($fd2268): per plane, a logic op chosen by the write mode and that plane's colour bits,
 *     run over the rows BOTTOM TO TOP by one of four row loops — one screen word a row, two, or a run of
 *     words with the glyph shifted right or left into place. The loops do not call the op: they `jsr` a
 *     FRAGMENT by its offset from `TEXT_FRAGMENTS`, and an EFFECT is a fragment put in front of the op
 *     (thicken, lighten, skew) that does its part of the word and jumps on to the fragment it replaced.
 *     Here that is `run_fragments`, a loop over the chain the frame's offset words spell.
 *   * THE PRE-PASS ($fd1f6e): rotation, outlining and a clipped italic cannot be done on the screen, so
 *     the glyph is first blitted — one plane, `TEXT_SCRATCH_WRITE_MODE`, thickened and skewed on the way
 *     — into the workstation's scratch buffer, which then becomes the source.
 *   * THE TRANSFORMS of a scratch copy: scaling by the DDA ($fd2b54, before the pre-pass), outlining
 *     ($fd2c9a) and rotation by a quarter or a half turn ($fd29da). Each writes into the half of the
 *     buffer the last one did not (`select_scratch`).
 *   * THE FRAME: DESTX/DESTY/DELX/DELY, STYLE, WRT_MODE and SKEWMASK are saved on entry and restored on
 *     the way out, and the advance is computed from the restored values. SOURCEX/SOURCEY, XACC_DDA and the
 *     scratch buffer are NOT restored — a pre-pass leaves the source at (0, 0).
 *
 * `struct textblt` is the ROM's `link a5,#-84` frame, field by field, and `struct row` the registers the
 * row loops hand a fragment. The loops keep the ROM's REGISTER lifetimes where they are observable: the
 * mask a one-word row runs under is set once and carried from row to row, the source long a multi-word
 * loop shifts is carried across rows, and the skew step between rows ($fd2944) chooses which of the two
 * multi-word loops runs the next row — the ROM's MUTUAL BRANCH ($fd2580 <-> $fd261c), spelt as the
 * direction one loop reads each row.
 *
 * THE FAST PATH draws a string of 8-pixel glyphs straight from a byte-per-character form, a byte a
 * plane, when x is on a byte; `$fcf96a` refuses what its conservative clip test does not pass. Its
 * body's first `dbf`, on the row count, JUMPS INTO ITS OWN CHARACTER LOOP'S `dbf` — the count is taken
 * less one before the loop, and a row count of 0 falls into an `rts` that returns THROUGH THE A6 THE
 * BODY PUSHED (a crash on the machine), which halts here.
 *
 * NOT REACHED BY ANY STAGED CASE, and written to the ROM's arithmetic regardless: a row count of 0 in
 * the multi-word loops (`subq.w #1 / beq` runs 65,536 rows) and a plane count of 0 (65,536 planes).
 *
 * A WRITE MODE OF 20 OR MORE indexes the op tables' own neighbours (the byte table runs on into "Dave
 * StaUgas loves Bea Hablig"). Where both slots it lands on are ops, it draws; it HALTS here on an odd
 * index (the ROM's address error) and on a slot, once a row runs it, that names no op — an effect
 * fragment's offset included, which the ROM runs over a frame it never set.
 */
#include <stdint.h>

#include "machine.h"
#include "recreate.h"
#include "addrs.h"
#include "m68k_idioms.h"
#include "ram_vector.h"
#include "vdi/vdi.h"
#include "vdi/helpers.h"
#include "vdi/raster.h"
#include "vdi/text_raster.h"
#include "vdi/transcribed.h"

#define PIXEL_IN_GROUP_MASK   15u       /* x & 15 */
#define GROUP_SHIFT           4         /* x >> 4 */
#define WORD_BITS             16
#define WORD_BYTES            2
#define LONG_BYTES            4
#define LEFTMOST_BIT          0x8000u
#define SHIFT_LEFTWARD        0x8000u   /* the shift word's flag: the source moves LEFT into place */
#define WHOLE_WORD            0xffffu
#define LOW_BYTE              0x00ffu
#define HIGH_BYTE             0xff00u
#define LAST_BIT_IN_WORD      15        /* `15 - shift`, the shift's mirror for the next word */
#define ROW_WORD_PAD          2         /* a scratch row is rounded up a word past its pixels */
#define SCALE_HALVED_WIDTH    3         /* a scaled row's bytes: width / 8 words, doubled ($fd2b96) */

/* ---- small machine idioms -------------------------------------------------------------------------- */

static inline uint16_t word_of(uint32_t value) { return (uint16_t)value; }
static inline uint16_t high_word(uint32_t value) { return (uint16_t)(value >> WORD_BITS); }
static inline uint32_t word_pair(uint16_t high, uint16_t low) { return (uint32_t)high << WORD_BITS | low; }

/* `lsl.l Dn,Dm` / `lsr.l`: the count modulo 64, and 32 or more shifts everything out. */
static inline uint32_t lsl_long(uint32_t value, uint16_t count)
{
    unsigned bits = count & M68K_SHIFT_COUNT_MASK;

    return bits < M68K_LONG_BITS ? value << bits : 0;
}

static inline uint32_t lsr_long(uint32_t value, uint16_t count)
{
    unsigned bits = count & M68K_SHIFT_COUNT_MASK;

    return bits < M68K_LONG_BITS ? value >> bits : 0;
}

/* `ori #$10,ccr / roxr.w #1,Dn`: the word shifted right with a 1 in; `*fell_out` is the bit shifted out. */
static inline uint16_t shift_in_one(uint16_t word, int *fell_out)
{
    *fell_out = word & 1;
    return (uint16_t)((word >> 1) | LEFTMOST_BIT);
}

/* ...followed by `bcc` over `move.w #$8000,Dn`: when bit 0 fell out, the lone left bit instead. */
static inline uint16_t step_mask_right(uint16_t word, int *fell_out)
{
    uint16_t shifted = shift_in_one(word, fell_out);

    return *fell_out ? LEFTMOST_BIT : shifted;
}

/* `mulu.w`: both factors unsigned words, the product a long. */
static inline uint32_t mulu_word(uint16_t left, uint16_t right)
{
    return (uint32_t)left * right;
}

/* A fringe mask by an index doubled IN A WORD and sign-extended, as the blit's `(a2,Dn.w)` reads it — where
 * raster.c's `fringe_mask` indexes unsigned: an index of $4000 or more reads BELOW the table here. */
static inline uint16_t signed_fringe_mask(const uint8_t *image, uint16_t index)
{
    return be16(image + RASTER_FRINGE_MASK_TABLE + (int16_t)(uint16_t)(index * RASTER_FRINGE_MASK_ENTRY_BYTES));
}

/* A word offset of a pixel column: `lsr.w #4` then doubled in a word. */
static inline uint16_t column_bytes(uint16_t x)
{
    return (uint16_t)((x >> GROUP_SHIFT) * WORD_BYTES);
}

/* A row of a glyph `width` pixels wide, in bytes, rounded up a word as the scratch buffer keeps it. */
static inline uint16_t padded_row_bytes(uint16_t width)
{
    return (uint16_t)(column_bytes(width) + ROW_WORD_PAD);
}

/* ---- the frame ----------------------------------------------------------------------------------------
 * `link a5,#-84`, by the offsets the ROM reaches each field at. */
struct textblt {
    uint16_t scratch_half;          /*  -2: SCRPT2 when the next scratch copy goes in the second half */
    uint32_t source;                /*  -6: the source form: FBASE, or a scratch copy */
    uint16_t source_step;           /* -12: the source's bytes a row, negated while the rows run upward */
    uint16_t dest_step;             /* -14: the destination's bytes a row, likewise */
    uint16_t width;                 /* -16: the blit's width in pixels */
    uint16_t height;                /* -18: ...and its rows */
    uint16_t source_bit;            /* -20: the source's first pixel in its word */
    uint16_t dest_bit;              /* -22: ...and the destination's */
    uint16_t middle_words;          /* -24: whole words between a multi-word row's two edge words */
    uint8_t thicken_left;           /* -25: the thicken fragments' word countdown */
    uint8_t thicken_words;          /* -26: ...and what it is reloaded with */
    uint16_t thicken_edge;          /* -28: the mask the thickened glyph's last word is cut to */
    uint16_t right_mask;            /* -30 */
    uint16_t left_mask;             /* -32 */
    uint16_t carry_mask;            /* -34: the bits of a shifted word that belong to the word before */
    uint16_t shift;                 /* -36: the source-to-destination shift, SHIFT_LEFTWARD set = left */
    uint16_t row_loop;              /* -38: TEXT_ROWS_* */
    uint16_t op_right;              /* -40: the fragment for a two-word row's second word */
    uint16_t op_first;              /* -42: ...for a one- or two-word row's first word */
    uint16_t op_edge;               /* -44: ...for a multi-word row's first and last words */
    uint16_t thicken_first_next;    /* -46: the fragment each effect fragment jumps on to */
    uint16_t lighten_first_next;    /* -48 */
    uint16_t skew_first_next;       /* -50 */
    uint16_t thicken_edge_next;     /* -52 */
    uint16_t lighten_edge_next;     /* -54 */
    uint16_t op_middle;             /* -56: ...for a multi-word row's middle words */
    uint16_t thicken_middle_next;   /* -58 */
    uint16_t lighten_middle_next;   /* -60 */
    uint16_t weight;                /* -62: the thickening in pixels, 0 when not thickening */
    uint16_t lighten_mask;          /* -64: LITEMASK, rotated a row at a time */
    uint16_t skew_mask;             /* -66: SKEWMASK, rotated a row at a time; LEFTMOST_BIT unskewed */
    uint16_t thicken_spill;         /* -68: the bits a thickened word smeared into the next */
    uint16_t fg_bits;               /* -70: TEXT_FG, a plane's bit spent at a time */
    uint16_t bg_bits;               /* -72: TEXT_BG, likewise */
    uint16_t planes_left;           /* -74 */
    uint16_t group_bytes;           /* -76: the destination's bytes to the next word of the same plane */
    uint16_t scaled_width;          /* -78 */
    uint16_t scaled_height;         /* -80 */
    uint16_t swapped_axes;          /* -82: a quarter turn swapped the two scaled sizes */
    uint16_t scaled_accumulator;    /* -84: XACC_DDA after the width's DDA */
    /* ...and three fields that are not the ROM's: the op the plane's index chose (index / 2), where
     * `find_op` looks first — the ROM jumps to a fragment by its offset and needs no search at all — and
     * the two op-table SLOTS it read, the masked and the whole fragment every chain of effects ends in. */
    unsigned plane_op;
    uint16_t masked_slot;
    uint16_t whole_slot;
};

/* ---- the fragments ------------------------------------------------------------------------------------
 * The registers a row loop hands a fragment. Only low words reach the screen; the high words are kept
 * because the ROM's swaps move them into the low ones. */
struct row {
    uint32_t spill;                 /* D0: the shifted source long; its low word is past this word */
    uint32_t glyph;                 /* D1: this word's source bits, and the op's answer */
    uint32_t mask;                  /* D2: the pixels of this word the op may change */
    uint16_t screen;                /* D4: the destination word */
    uint8_t *word;                  /* A1: where the answer goes — the skew fragment can move it */
};

/* BitBlt's sixteen logic ops, in the ROM's order (TEXT_OP_*_TABLE): an op's four bits are its truth
 * table — the answer where the source and the destination pixel are both set, where only the source is,
 * where only the destination is, and where neither is. */
enum op_truth { OP_BOTH = 1, OP_SOURCE_ONLY = 2, OP_DEST_ONLY = 4, OP_NEITHER = 8 };

static uint16_t logic_op(unsigned op, uint16_t source, uint16_t dest)
{
    uint16_t result = 0;

    if (op & OP_BOTH)
        result |= source & dest;
    if (op & OP_SOURCE_ONLY)
        result |= source & (uint16_t)~dest;
    if (op & OP_DEST_ONLY)
        result |= (uint16_t)~source & dest;
    if (op & OP_NEITHER)
        result |= (uint16_t)~(source | dest);
    return result;
}

/* The op an op FRAGMENT's offset names, and whether it is the masked one — the op inside D2, the screen
 * outside it — or the whole-word one: its place in either table, tried first at the op this plane's
 * index chose (`plane_op`), which is where every write mode 0..19 finds it. */
static int find_op(const uint8_t *image, uint16_t fragment, unsigned first_guess, unsigned *op)
{
    unsigned tried, candidate;

    for (tried = 0; tried < TEXT_OP_COUNT; tried++) {
        candidate = (first_guess + tried) % TEXT_OP_COUNT;
        if (be16(image + TEXT_OP_MASKED_TABLE + candidate * WORD_BYTES) == fragment) {
            *op = candidate;
            return 1;
        }
        if (be16(image + TEXT_OP_WHOLE_TABLE + candidate * WORD_BYTES) == fragment) {
            *op = candidate;
            return 0;
        }
    }
    recreate_not_reconstructed("TextBlt: an op-table slot naming no op (a write mode past 19)");
}

static void apply_op(const uint8_t *image, const struct textblt *frame, uint16_t fragment, struct row *row)
{
    unsigned op;
    int masked = find_op(image, fragment, frame->plane_op, &op);
    uint16_t result = logic_op(op, word_of(row->glyph), row->screen);

    if (masked) {
        uint16_t mask = word_of(row->mask);

        result = (uint16_t)((row->screen & (uint16_t)~mask) | (result & mask));
    }
    row->glyph = set_low_word(row->glyph, result);
}

/* `swap d1 / clr.w d1`, then `weight` times `lsr.l #1 / or.l`: the word smeared right by the weight, on
 * into the word after it. Answers the smeared word; `*spill` gets what ran into the next. */
static uint16_t smear(uint16_t glyph, uint16_t weight, uint16_t *spill)
{
    uint32_t wide = (uint32_t)glyph << WORD_BITS;
    uint32_t shifted = wide;
    uint16_t count;

    for (count = weight; count != 0; count--) {
        shifted >>= 1;
        wide |= shifted;
    }
    *spill = word_of(wide);
    return high_word(wide);
}

/* $fd2784 — THICKEN, a one- or two-word row's first word: the glyph and its spill cut to the masks the
 * weight will smear them into, then smeared right across the pair. On a skewed row about to step
 * (SKEWMASK's bit 0), the edge mask moves a pixel right first. */
static uint16_t thicken_first(struct textblt *frame, struct row *row)
{
    uint16_t edge = frame->thicken_edge;
    uint32_t room, smeared;
    uint16_t count;
    int fell_out;

    row->glyph = set_low_word(row->glyph, word_of(row->glyph) & word_of(row->mask));
    if (frame->skew_mask & 1) {
        edge = step_mask_right(edge, &fell_out);
        frame->thicken_edge = edge;
    }
    if ((int16_t)frame->middle_words >= 0 && edge < frame->right_mask) {
        row->spill = set_low_word(row->spill, word_of(row->spill) & edge);
    } else {
        row->spill = set_low_word(row->spill, 0);
        row->glyph = set_low_word(row->glyph, word_of(row->glyph) & edge);
    }
    room = lsl_long(word_pair(word_of(row->mask), frame->right_mask), frame->weight);
    smeared = word_pair(word_of(row->glyph) & high_word(room), word_of(row->spill) & word_of(room));
    for (count = frame->weight; count != 0; count--) {
        row->spill = smeared >> 1;
        smeared |= row->spill;
    }
    row->spill = set_low_word(row->spill, word_of(smeared));
    row->glyph = m68k_swap(smeared);
    return frame->thicken_first_next;
}

/* $fd27ea — THICKEN, a middle word: the word the thickening ends in is cut to the edge mask, and each
 * word takes the smear the one before spilled into it. */
static uint16_t thicken_middle(struct textblt *frame, struct row *row)
{
    uint16_t glyph = word_of(row->glyph), spill;

    if (--frame->thicken_left == 0)
        glyph &= frame->thicken_edge;
    glyph = (uint16_t)(smear(glyph, frame->weight, &spill) | frame->thicken_spill);
    frame->thicken_spill = spill;
    row->glyph = set_low_word(row->glyph, glyph);
    return frame->thicken_middle_next;
}

/* $fd283c — a skewed row's edge word recounts the words the thickening reaches, with the right mask and
 * the edge mask each a pixel further right. Only the count and the edge are kept. */
static void thicken_recount(struct textblt *frame, uint16_t *edge)
{
    uint16_t words = (uint16_t)(frame->middle_words + 2);
    uint16_t right;
    int fell_out;

    right = step_mask_right(frame->right_mask, &fell_out);
    if (fell_out)
        words++;
    if (frame->left_mask == 1)
        words--;
    *edge = step_mask_right(*edge, &fell_out);
    if (right >= *edge)
        words++;
    frame->thicken_edge = *edge;
    frame->thicken_words = (uint8_t)words;
}

/* $fd281c — THICKEN, a multi-word row's first or last word: counts the row's words down, cuts the one
 * the thickening ends in, and at a row's first word (the countdown run out) reloads the count. */
static uint16_t thicken_edge(struct textblt *frame, struct row *row)
{
    uint16_t edge = frame->thicken_edge;
    uint16_t glyph = word_of(row->glyph), spill;
    int8_t left = (int8_t)--frame->thicken_left;

    if (left > 0) {
        if (--frame->thicken_left == 0)
            glyph &= edge;
        glyph &= frame->left_mask;
    } else {
        glyph = left < 0 ? 0 : glyph & edge;
        if ((int16_t)frame->skew_mask >= 0)
            thicken_recount(frame, &edge);
        frame->thicken_left = frame->thicken_words;
    }
    glyph = (uint16_t)(smear(glyph, frame->weight, &spill) | frame->thicken_spill);
    frame->thicken_spill = spill;
    row->glyph = set_low_word(row->glyph, glyph & word_of(row->mask));
    return frame->thicken_edge_next;
}

/* $fd28b2 / $fd28c6 / $fd28d2 — LIGHTEN: the glyph under the rotating LITEMASK. The first-word fragment
 * cuts the spill too and rotates the mask; a multi-word row's loop rotates it itself. */
static uint16_t lighten_first(struct textblt *frame, struct row *row)
{
    row->glyph = set_low_word(row->glyph, word_of(row->glyph) & frame->lighten_mask);
    row->spill = set_low_word(row->spill, word_of(row->spill) & frame->lighten_mask);
    frame->lighten_mask = rotate_left16(frame->lighten_mask, 1);
    return frame->lighten_first_next;
}

static uint16_t lighten_middle(struct textblt *frame, struct row *row)
{
    row->glyph = set_low_word(row->glyph, word_of(row->glyph) & frame->lighten_mask);
    return frame->lighten_middle_next;
}

static uint16_t lighten_edge(struct textblt *frame, struct row *row)
{
    row->glyph = set_low_word(row->glyph, word_of(row->glyph) & frame->lighten_mask);
    return frame->lighten_edge_next;
}

/* The shift the row after a one-pixel skew is read with: one more to the right, one fewer to the left —
 * and a left shift of 0 turns into a right shift of 1 ($fd28fe, $fd2916). */
static inline uint16_t skewed_shift(uint16_t shift)
{
    if ((int16_t)shift >= 0)
        return (uint16_t)(shift + 1);
    return (shift & LOW_BYTE) ? (uint16_t)(shift - 1) : 1;
}

/* $fd28de — SKEW, a two-word row's first word: when SKEWMASK's top bit rotates out, the glyph, its spill
 * and both masks move a pixel right. A left mask shifted to nothing means the glyph has left this word:
 * the store moves to the plane's next word, which is re-read, the right mask becomes the left — and the
 * low word of the shifted pair, still in D1, is what the op stores there. */
static uint16_t skew_first(struct textblt *frame, struct row *row)
{
    int stepped = (frame->skew_mask & LEFTMOST_BIT) != 0;

    frame->skew_mask = rotate_left16(frame->skew_mask, 1);
    if (!stepped)
        return frame->skew_first_next;
    row->glyph = word_pair(word_of(row->glyph), word_of(row->spill)) >> 1;
    row->mask = word_pair(word_of(row->mask), frame->right_mask) >> 1;
    frame->right_mask = word_of(row->mask);
    row->mask = m68k_swap(row->mask);
    frame->left_mask = word_of(row->mask);
    if (word_of(row->mask) == 0) {
        frame->right_mask = 0;
        row->mask = m68k_swap(row->mask);
        frame->left_mask = word_of(row->mask);
        row->word += (int16_t)frame->group_bytes;
        row->screen = be16(row->word);
        frame->shift = (uint16_t)((LAST_BIT_IN_WORD - frame->shift) | SHIFT_LEFTWARD);
        row->spill = set_low_word(row->spill, frame->shift);
        return frame->skew_first_next;
    }
    frame->shift = skewed_shift(frame->shift);
    row->spill = set_low_word(row->spill, word_of(row->glyph));
    row->glyph = m68k_swap(row->glyph);
    return frame->skew_first_next;
}

/* `jsr (a3,a4.w)` with A3 = TEXT_FRAGMENTS: an effect fragment and those it jumps on to, then the op the
 * chain ends in — `op_slot`, the value the op table gave. A write mode past 19 can land that slot on an
 * EFFECT's offset (mode 44's is lighten's edge word), which the ROM runs over a frame it never set, and
 * with the effect's own style spins forever (its `_next` is the slot itself): the slot is taken as the op
 * whatever it names, and `find_op` refuses one that is not. */
static void run_fragments(const uint8_t *image, struct textblt *frame, uint16_t fragment, uint16_t op_slot,
                          struct row *row)
{
    for (;;) {
        if (fragment == op_slot) {
            apply_op(image, frame, fragment, row);
            return;
        }
        switch (fragment) {
        case TEXT_FRAGMENT_THICKEN_FIRST:  fragment = thicken_first(frame, row); break;
        case TEXT_FRAGMENT_THICKEN_MIDDLE: fragment = thicken_middle(frame, row); break;
        case TEXT_FRAGMENT_THICKEN_EDGE:   fragment = thicken_edge(frame, row); break;
        case TEXT_FRAGMENT_LIGHTEN_FIRST:  fragment = lighten_first(frame, row); break;
        case TEXT_FRAGMENT_LIGHTEN_MIDDLE: fragment = lighten_middle(frame, row); break;
        case TEXT_FRAGMENT_LIGHTEN_EDGE:   fragment = lighten_edge(frame, row); break;
        case TEXT_FRAGMENT_SKEW:           fragment = skew_first(frame, row); break;
        default:
            recreate_not_reconstructed("TextBlt: an effect chain that never reaches its op slot");
        }
    }
}

/* ---- the row loops ----------------------------------------------------------------------------------- */

/* The source long at `source` shifted into the destination's place, and its high word the glyph. */
static inline void load_shifted(const struct textblt *frame, const uint8_t *source, struct row *row)
{
    uint32_t pair = be32(source);

    row->spill = (frame->shift & SHIFT_LEFTWARD) ? lsl_long(pair, frame->shift) : lsr_long(pair, frame->shift);
    row->glyph = set_low_word(row->glyph, high_word(row->spill));
}

/* $fd2506 — one screen word a row, under the mask the loop was entered with (never reloaded). */
static void rows_one_word(const uint8_t *image, struct textblt *frame, const uint8_t *source, struct row *row)
{
    uint16_t rows;

    for (rows = frame->height; rows != 0; rows--) {
        row->screen = be16(row->word);
        load_shifted(frame, source, row);
        run_fragments(image, frame, frame->op_first, frame->masked_slot, row);
        wr16(row->word, word_of(row->glyph));
        source += (int16_t)frame->source_step;
        row->word += (int16_t)frame->dest_step;
    }
}

/* $fd2534 — two screen words a row: the first under LEFT_MASK, then the spill under RIGHT_MASK in the
 * plane's next word. */
static void rows_two_words(const uint8_t *image, struct textblt *frame, const uint8_t *source, struct row *row)
{
    uint16_t rows;

    for (rows = frame->height; rows != 0; rows--) {
        int16_t next_word;

        row->screen = be16(row->word);
        load_shifted(frame, source, row);
        row->mask = set_low_word(row->mask, frame->left_mask);
        run_fragments(image, frame, frame->op_first, frame->masked_slot, row);
        wr16(row->word, word_of(row->glyph));
        row->glyph = set_low_word(row->glyph, word_of(row->spill));
        next_word = (int16_t)frame->group_bytes;
        row->screen = be16(row->word + next_word);
        row->mask = set_low_word(row->mask, frame->right_mask);
        run_fragments(image, frame, frame->op_right, frame->masked_slot, row);
        wr16(row->word + next_word, word_of(row->glyph));
        source += (int16_t)frame->source_step;
        row->word += (int16_t)frame->dest_step;
    }
}

/* One row of the multi-word loops ($fd2580 left, $fd261c right). The first word's source is a long
 * shifted LEFT — or a word shifted RIGHT with the previous long's high word below it — and each word
 * after it is the next source word shifted the same way, its bits below CARRY_MASK completed by the
 * word before's. */
static void multi_row(const uint8_t *image, struct textblt *frame, const uint8_t *source, struct row *row,
                      int leftward)
{
    uint16_t middles = frame->middle_words;
    uint16_t group = frame->group_bytes;

    if (leftward) {
        row->spill = be32(source);
        source += LONG_BYTES;
        row->screen = be16(row->word);
        row->spill = lsl_long(row->spill, frame->shift);
    } else {
        row->spill = word_pair(be16(source), high_word(row->spill));
        source += WORD_BYTES;
        row->screen = be16(row->word);
        row->spill = lsr_long(row->spill, frame->shift);
    }
    row->glyph = set_low_word(row->glyph, high_word(row->spill));
    row->mask = set_low_word(row->mask, frame->left_mask);
    run_fragments(image, frame, frame->op_edge, frame->masked_slot, row);
    wr16(row->word, word_of(row->glyph));
    row->word += (int16_t)group;
    row->mask = set_low_word(row->mask, frame->carry_mask);
    for (;;) {
        uint16_t carried = word_of(row->spill) & word_of(row->mask);
        uint16_t next = be16(source);

        source += WORD_BYTES;
        if (leftward)
            row->spill = lsl_long(word_pair(word_of(row->glyph), next), frame->shift);
        else
            row->spill = lsr_long(word_pair(next, word_of(row->spill)), frame->shift);
        row->glyph = set_low_word(row->glyph,
                                  (uint16_t)((high_word(row->spill) & (uint16_t)~word_of(row->mask)) ^ carried));
        row->screen = be16(row->word);
        if (middles == 0)
            break;
        run_fragments(image, frame, frame->op_middle, frame->whole_slot, row);
        wr16(row->word, word_of(row->glyph));
        row->word += (int16_t)group;
        middles--;
    }
    row->mask = set_low_word(row->mask, frame->right_mask);
    run_fragments(image, frame, frame->op_edge, frame->masked_slot, row);
    wr16(row->word, word_of(row->glyph));
}

/* $fd2944 — between two rows of a skewed multi-word blit: when the bit SKEWMASK rotates out is CLEAR —
 * the opposite of the two-word fragment's test ($fd28e2 `bcc` over the step, $fd2948 `bcc` to it) —
 * every mask moves a pixel right and the shift follows; a left mask shifted to nothing moves the rows on
 * a word. Answers whether the next row runs the LEFT loop. */
static int skew_step(struct textblt *frame, uint8_t **row_start)
{
    int stepped = (frame->skew_mask & LEFTMOST_BIT) == 0;
    uint16_t shift, left;
    int fell_out;

    frame->skew_mask = rotate_left16(frame->skew_mask, 1);
    if (!stepped)
        return (frame->shift & SHIFT_LEFTWARD) != 0;
    frame->carry_mask = shift_in_one(frame->carry_mask, &fell_out);
    if (frame->right_mask == WHOLE_WORD) {
        frame->middle_words++;
        frame->right_mask = LEFTMOST_BIT;
    } else {
        frame->right_mask = shift_in_one(frame->right_mask, &fell_out);
    }
    shift = frame->shift;
    if ((shift & LOW_BYTE) == 0)
        frame->carry_mask = LEFTMOST_BIT;
    left = frame->left_mask >> 1;
    if (left == 0) {
        frame->left_mask = WHOLE_WORD;
        frame->middle_words--;
        *row_start += (int16_t)frame->group_bytes;
        frame->shift = (uint16_t)((LAST_BIT_IN_WORD - shift) | SHIFT_LEFTWARD);
        return 1;
    }
    frame->left_mask = left;
    frame->shift = skewed_shift(shift);
    return (shift & SHIFT_LEFTWARD) && (shift & LOW_BYTE);
}

/* $fd2580 / $fd261c — a run of words a row, rows counted by `subq.w #1 / beq`: after each row the
 * thicken spill is dropped, LITEMASK rotates, and a skewed blit takes its step. */
static void rows_multi(const uint8_t *image, struct textblt *frame, const uint8_t *source, struct row *row)
{
    uint16_t rows = frame->height;
    int leftward = frame->row_loop == TEXT_ROWS_LEFT;

    for (;;) {
        uint8_t *start = row->word;

        multi_row(image, frame, source, row, leftward);
        source += (int16_t)frame->source_step;
        row->word = start + (int16_t)frame->dest_step;
        frame->thicken_spill = 0;
        if (--rows == 0)
            return;
        frame->lighten_mask = rotate_left16(frame->lighten_mask, 1);
        if (ram_uword(image, LINEA_STYLE) & VDI_STYLE_SKEW_MASK)
            leftward = skew_step(frame, &row->word);
    }
}

/* ---- one blit: the masks, the ops, the planes ($fd2268) -------------------------------------------------- */

/* $fd2268 — the masks and the row loop for a blit of WIDTH pixels from SOURCE_BIT to DEST_BIT. */
static void blit_masks(const uint8_t *image, struct textblt *frame)
{
    uint16_t shift = (uint16_t)(frame->dest_bit - frame->source_bit);
    uint16_t span_index = shift;
    uint16_t end, edge_index, middles = WHOLE_WORD, right = 0, count;

    if ((int16_t)shift < 0) {
        shift = (uint16_t)(-shift | SHIFT_LEFTWARD);
        span_index = (uint16_t)(span_index + WORD_BITS);
    }
    frame->shift = shift;
    frame->carry_mask = (uint16_t)~signed_fringe_mask(image, span_index);
    frame->left_mask = signed_fringe_mask(image, frame->dest_bit);
    end = (uint16_t)(frame->dest_bit + frame->width);
    edge_index = (uint16_t)((end - frame->weight) & PIXEL_IN_GROUP_MASK);
    frame->thicken_edge = (uint16_t)~signed_fringe_mask(image, edge_index);
    frame->skew_mask = LEFTMOST_BIT;
    if (end <= TEXT_ONE_WORD_SPAN) {
        frame->left_mask &= (uint16_t)~signed_fringe_mask(image, end);
        frame->row_loop = TEXT_ROWS_ONE_WORD;
    } else {
        uint16_t last;

        frame->row_loop = TEXT_ROWS_TWO_WORDS;
        middles = (uint16_t)((end >> GROUP_SHIFT) - 1);
        if (middles != 0 || (uint16_t)(frame->source_bit + frame->width) >= TEXT_TWO_WORD_SOURCE_SPAN)
            frame->row_loop = (shift & SHIFT_LEFTWARD) ? TEXT_ROWS_LEFT : TEXT_ROWS_RIGHT;
        last = end & PIXEL_IN_GROUP_MASK;
        if (last == 0) {
            middles--;
            last = WORD_BITS;
        }
        right = (uint16_t)~signed_fringe_mask(image, last);
    }
    frame->middle_words = middles;
    frame->right_mask = right;
    count = (uint16_t)(middles + 2);
    if (right >= frame->thicken_edge)
        count++;
    frame->thicken_words = frame->thicken_left = (uint8_t)count;
}

/* $fd233c — this plane's op: WRT_MODE * 4 + its colour bit * 2 + its background bit indexes a byte, the
 * op * 2, which indexes both fragment tables. The byte replaces only the index's low byte — and past mode
 * 19 it can leave it ODD, a word read at an odd address: the ROM's address error, a halt here. */
static void choose_ops(const uint8_t *image, struct textblt *frame)
{
    uint16_t index = ram_uword(image, LINEA_WRT_MODE);
    uint16_t fragment;

    index = (uint16_t)(index << 1 | (frame->fg_bits & 1));
    frame->fg_bits >>= 1;
    index = (uint16_t)(index << 1 | (frame->bg_bits & 1));
    frame->bg_bits >>= 1;
    index = (uint16_t)((index & HIGH_BYTE) | image[TEXT_OP_INDEX_TABLE + (int16_t)index]);
    if (index & 1)
        recreate_not_reconstructed("TextBlt: an odd op index ($fd2350 `movea.w (pc,d0.w)`: an address error)");
    frame->plane_op = (index / WORD_BYTES) % TEXT_OP_COUNT;
    fragment = be16(image + TEXT_OP_MASKED_TABLE + (int16_t)index);
    frame->op_right = frame->op_first = frame->op_edge = frame->masked_slot = fragment;
    frame->op_middle = frame->whole_slot = be16(image + TEXT_OP_WHOLE_TABLE + (int16_t)index);
}

/* $fd2424 — the effect fragments STYLE asks for, each put in front of the fragments it replaces: lighten
 * nearest the op, then thicken, then skew. An italic row needs two words, and one that spills past
 * sixteen pixels a run of them. */
static void choose_effects(const uint8_t *image, struct textblt *frame, uint16_t style)
{
    if (style & VDI_STYLE_LIGHTEN_MASK) {
        frame->lighten_mask = ram_uword(image, LINEA_LITEMASK);
        frame->lighten_first_next = frame->op_first;
        frame->op_first = TEXT_FRAGMENT_LIGHTEN_FIRST;
        frame->lighten_edge_next = frame->op_edge;
        frame->op_edge = TEXT_FRAGMENT_LIGHTEN_EDGE;
        frame->lighten_middle_next = frame->op_middle;
        frame->op_middle = TEXT_FRAGMENT_LIGHTEN_MIDDLE;
    }
    if (style & VDI_STYLE_THICKEN_MASK) {
        frame->thicken_spill = 0;
        frame->thicken_first_next = frame->op_first;
        frame->op_first = TEXT_FRAGMENT_THICKEN_FIRST;
        frame->thicken_edge_next = frame->op_edge;
        frame->op_edge = TEXT_FRAGMENT_THICKEN_EDGE;
        frame->thicken_middle_next = frame->op_middle;
        frame->op_middle = TEXT_FRAGMENT_THICKEN_MIDDLE;
    }
    if (style & VDI_STYLE_SKEW_MASK) {
        frame->skew_mask = ram_uword(image, LINEA_SKEWMASK);
        frame->skew_first_next = frame->op_first;
        frame->op_first = TEXT_FRAGMENT_SKEW;
        if (frame->row_loop == TEXT_ROWS_ONE_WORD) {
            frame->middle_words = 0;
            frame->row_loop = TEXT_ROWS_TWO_WORDS;
        } else if (frame->row_loop == TEXT_ROWS_TWO_WORDS && frame->width > TEXT_ONE_WORD_SPAN) {
            frame->row_loop = (frame->shift & SHIFT_LEFTWARD) ? TEXT_ROWS_LEFT : TEXT_ROWS_RIGHT;
        }
    }
}

/* $fd24d0 — one plane: the row loop from the bottom row at `source` / `dest`. */
static void blit_plane(const uint8_t *image, struct textblt *frame, const uint8_t *source, uint8_t *dest,
                       struct row *row)
{
    row->mask = set_low_word(row->mask, frame->left_mask);
    row->word = dest;
    switch (frame->row_loop) {
    case TEXT_ROWS_ONE_WORD:  rows_one_word(image, frame, source, row); break;
    case TEXT_ROWS_TWO_WORDS: rows_two_words(image, frame, source, row); break;
    default:                  rows_multi(image, frame, source, row); break;
    }
}

/* $fd2268..$fd2502 — the blit, plane by plane: the op re-chosen for each plane's colour bits, and — for
 * italics, whose row loops move the masks — the masks recomputed too. */
static void blit(uint8_t *image, struct textblt *frame, const uint8_t *source, uint8_t *dest)
{
    struct row row = {0, 0, 0, 0, dest};

    blit_masks(image, frame);
    for (;;) {
        uint16_t style;

        choose_ops(image, frame);
        style = ram_uword(image, LINEA_STYLE);
        if (style)
            choose_effects(image, frame, style);
        blit_plane(image, frame, source, dest, &row);
        dest += WORD_BYTES;
        if (--frame->planes_left == 0)
            return;
        if (ram_uword(image, LINEA_STYLE) & VDI_STYLE_SKEW_MASK)
            blit_masks(image, frame);
    }
}

/* ---- the scratch buffer and its transforms ------------------------------------------------------------ */

/* $fd2c7c — the half of the scratch buffer the next copy goes in: the first, then SCRPT2 on, in turn. */
static uint32_t select_scratch(const uint8_t *image, struct textblt *frame)
{
    uint32_t buffer = be32(image + LINEA_SCRTCHP);

    if (frame->scratch_half != 0) {
        buffer += (uint32_t)(int32_t)(int16_t)frame->scratch_half;
        frame->scratch_half = 0;
    } else {
        frame->scratch_half = ram_uword(image, LINEA_SCRPT2);
    }
    return buffer;
}

/* $fd2ade — the copy at `copy` is the source from its first pixel on. */
static void source_is_copy(uint8_t *image, struct textblt *frame, uint32_t copy)
{
    set_ram_word(image, LINEA_SOURCEX, 0);
    set_ram_word(image, LINEA_SOURCEY, 0);
    frame->source = copy;
}

/* $fd2c1c — one source row scaled across into the scratch row at `*dest`: the DDA restarts at XACC_DDA
 * for every row, and each source pixel spends it once — shrinking, a carry places the pixel; enlarging,
 * the pixel is placed once and a carry places it again. A placed pixel is its colour, set or clear. */
static void scale_row(const uint8_t *image, const struct textblt *frame, const uint8_t *source, uint8_t **dest,
                      uint16_t first_bit, int enlarge, uint16_t row_bytes)
{
    uint16_t increment = ram_uword(image, LINEA_DDA_INC);
    uint16_t accumulator = ram_uword(image, LINEA_XACC_DDA);
    uint16_t source_mask = first_bit, out_bit = LEFTMOST_BIT, out = 0, pixel_word;
    uint16_t remaining = (uint16_t)(frame->width - 1);
    uint8_t *write = *dest;

    pixel_word = be16(source);
    source += WORD_BYTES;
    for (;;) {
        int set = (pixel_word & source_mask) != 0;
        unsigned placed = word_add_extend(accumulator, increment) + (enlarge != 0);

        accumulator = (uint16_t)(accumulator + increment);
        for (; placed != 0; placed--) {
            if (set)
                out |= out_bit;
            out_bit = rotate_right16(out_bit, 1);
            if (out_bit == LEFTMOST_BIT) {
                wr16(write, out);
                write += WORD_BYTES;
                out = 0;
            }
        }
        if (remaining-- == 0)
            break;
        source_mask = rotate_right16(source_mask, 1);
        if (source_mask == LEFTMOST_BIT) {
            pixel_word = be16(source);
            source += WORD_BYTES;
        }
    }
    wr16(write, out);
    *dest += (int16_t)row_bytes;
}

/* $fd2b54 — SCALING, before anything else: the glyph at (SOURCEX, SOURCEY) redrawn into the scratch
 * buffer through the DDA, down the rows (each source row once per carry — twice enlarging) and across
 * each row (`scale_row`). DELX/DELY become the scaled size and XACC_DDA the width's DDA left over. */
static void scale(uint8_t *image, struct textblt *frame)
{
    uint16_t source_x = ram_uword(image, LINEA_SOURCEX);
    int enlarge = ram_uword(image, LINEA_T_SCLSTS) & VDI_SCALE_UP_MASK;
    uint16_t increment = ram_uword(image, LINEA_DDA_INC);
    const uint8_t *source;
    uint16_t first_bit, row_bytes, rows, accumulator, columns, scaled_width;
    uint8_t *dest;

    frame->source_bit = source_x & PIXEL_IN_GROUP_MASK;
    source = image + frame->source + (int16_t)column_bytes(source_x)
             + mulu_word(ram_uword(image, LINEA_SOURCEY), frame->source_step);
    first_bit = (uint16_t)(LEFTMOST_BIT >> frame->source_bit);
    frame->height = ram_uword(image, LINEA_DELY);
    frame->width = ram_uword(image, LINEA_DELX);
    dest = image + select_scratch(image, frame);
    row_bytes = (uint16_t)(((frame->width >> SCALE_HALVED_WIDTH) * WORD_BYTES) + ROW_WORD_PAD);
    frame->dest_step = row_bytes;
    accumulator = VDI_DDA_ACCUMULATOR_START;
    rows = (uint16_t)(frame->height - 1);
    do {
        int carried = word_add_extend(accumulator, increment);

        accumulator = (uint16_t)(accumulator + increment);
        if (carried)
            scale_row(image, frame, source, &dest, first_bit, enlarge, row_bytes);
        if (enlarge)
            scale_row(image, frame, source, &dest, first_bit, enlarge, row_bytes);
        source += (int16_t)frame->source_step;
    } while (rows-- != 0);
    accumulator = ram_uword(image, LINEA_XACC_DDA);
    scaled_width = 0;
    for (columns = ram_uword(image, LINEA_DELX); columns != 0; columns--) {
        scaled_width = (uint16_t)(scaled_width + word_add_extend(accumulator, increment) + (enlarge != 0));
        accumulator = (uint16_t)(accumulator + increment);
    }
    set_ram_word(image, LINEA_XACC_DDA, accumulator);
    set_ram_word(image, LINEA_DELX, scaled_width);
    set_ram_word(image, LINEA_DELY, frame->scaled_height);
    frame->source_step = frame->dest_step;
    source_is_copy(image, frame, be32(image + LINEA_SCRTCHP));
}

/* ---- rotation ------------------------------------------------------------------------------------------ */

/* The sixteen bits of a word in the opposite order (`lsr.w #1 / roxl.w #1` sixteen times). */
static inline uint16_t reversed_bits(uint16_t word)
{
    uint16_t reversed = 0;
    unsigned bit;

    for (bit = 0; bit < WORD_BITS; bit++) {
        reversed = (uint16_t)(reversed << 1 | (word & 1));
        word >>= 1;
    }
    return reversed;
}

/* $fd2aec — a HALF TURN into the scratch copy at `copy`: each source row's words bit-reversed and laid
 * down from the copy's END backwards, so the rows come out bottom first and each row right to left.
 * SOURCEY is not read (the rows start at SOURCEX's word of the form's first row); SOURCEX becomes where
 * the glyph now starts in its first word. */
static void rotate_half_turn(uint8_t *image, struct textblt *frame, const uint8_t *source, uint32_t copy,
                             uint16_t rows)
{
    uint16_t row_bytes = padded_row_bytes((uint16_t)(ram_uword(image, LINEA_DELX) + frame->source_bit - 1));
    uint16_t last_word = (uint16_t)((row_bytes >> 1) - 1);
    uint8_t *dest = image + copy + mulu_word(row_bytes, rows);

    frame->dest_step = row_bytes;
    for (; rows != 0; rows--) {
        const uint8_t *read = source;
        uint16_t words = last_word;

        do {
            dest -= WORD_BYTES;
            wr16(dest, reversed_bits(be16(read)));
            read += WORD_BYTES;
        } while (words-- != 0);
        source += (int16_t)frame->source_step;
    }
    frame->source_step = frame->dest_step;
    frame->source = copy;
    set_ram_word(image, LINEA_SOURCEX, (uint16_t)(-(ram_uword(image, LINEA_SOURCEX)
                                                      + ram_uword(image, LINEA_DELX)) & PIXEL_IN_GROUP_MASK));
    set_ram_word(image, LINEA_SOURCEY, 0);
}

/* $fd29da — ROTATION into the scratch buffer. A half turn is `rotate_half_turn`. A quarter turn reads the
 * glyph a COLUMN at a time into the copy's rows — 90 degrees from the source's top row with the copy's
 * rows laid bottom up, 270 (and any other angle) from its bottom row with them laid top down — and then
 * DELX and DELY, and the two scaled sizes, change places. At 90 degrees the source's first row is where
 * the form's is: SOURCEY is not read. */
static void rotate(uint8_t *image, struct textblt *frame)
{
    uint16_t source_x = ram_uword(image, LINEA_SOURCEX);
    uint16_t source_y = ram_uword(image, LINEA_SOURCEY);
    uint16_t angle = ram_uword(image, LINEA_CHUP);
    uint16_t step = frame->source_step;
    uint16_t row_bytes, columns, source_mask, held;
    const uint8_t *source;
    uint8_t *dest;
    uint32_t copy;

    frame->source_bit = source_x & PIXEL_IN_GROUP_MASK;
    source = image + frame->source + (int16_t)column_bytes(source_x);
    frame->width = ram_uword(image, LINEA_DELX);
    frame->height = ram_uword(image, LINEA_DELY);
    copy = select_scratch(image, frame);
    if (angle == TEXT_ROTATION_180) {
        rotate_half_turn(image, frame, source, copy, frame->height);
        return;
    }
    if (angle != TEXT_ROTATION_90) {
        frame->source_step = (uint16_t)-frame->source_step;
        source += mulu_word((uint16_t)(source_y + frame->height - 1), step);
    }
    row_bytes = padded_row_bytes(ram_uword(image, LINEA_DELY));
    frame->dest_step = row_bytes;
    dest = image + copy;
    if (angle != TEXT_ROTATION_270) {
        frame->dest_step = (uint16_t)-row_bytes;
        dest += mulu_word(row_bytes, (uint16_t)(ram_uword(image, LINEA_DELX) - 1));
    }
    source_mask = (uint16_t)(LEFTMOST_BIT >> frame->source_bit);
    for (columns = frame->width; columns != 0; columns--) {
        const uint8_t *read = source;
        uint8_t *write = dest;
        uint16_t out_bit = LEFTMOST_BIT, out = 0, rows;

        for (rows = frame->height; rows != 0; rows--) {
            if (be16(read) & source_mask)
                out |= out_bit;
            out_bit = rotate_right16(out_bit, 1);
            if (out_bit == LEFTMOST_BIT) {
                wr16(write, out);
                write += WORD_BYTES;
                out = 0;
            }
            read += (int16_t)frame->source_step;
        }
        wr16(write, out);
        dest += (int16_t)frame->dest_step;
        source_mask = rotate_right16(source_mask, 1);
        if (source_mask == LEFTMOST_BIT)
            source += WORD_BYTES;
    }
    held = ram_uword(image, LINEA_DELX);
    frame->width = ram_uword(image, LINEA_DELY);
    set_ram_word(image, LINEA_DELX, frame->width);
    frame->height = held;
    set_ram_word(image, LINEA_DELY, held);
    held = frame->scaled_height;
    frame->scaled_height = frame->scaled_width;
    frame->scaled_width = held;
    frame->swapped_axes = 1;
    frame->source_step = angle == TEXT_ROTATION_90 ? (uint16_t)-frame->dest_step : frame->dest_step;
    source_is_copy(image, frame, copy);
}

/* ---- outlining ----------------------------------------------------------------------------------------- */

static inline uint32_t with_low_byte(uint32_t value, uint8_t byte)
{
    return (value & ~(uint32_t)LOW_BYTE) | byte;
}

/* A word of the outline: every pixel whose 3x3 neighbourhood — the row `above`, the row `current` and the
 * row `below`, each a long already rotated into place — is not all one colour, less the pixels the
 * glyph itself sets ($fd2cba..$fd2d04). */
static inline uint16_t outline_word(uint32_t above, uint32_t current, uint32_t below)
{
    uint32_t right = rotate_right32(current, 1), further = rotate_right32(right, 1);
    uint32_t edges = (above ^ current) | rotate_left32(above ^ right, 1) | rotate_left32(above ^ further, 2)
                     | (below ^ current) | rotate_left32(below ^ right, 1) | rotate_left32(below ^ further, 2)
                     | (current ^ right) | rotate_left32(further ^ right, 2);

    return high_word(edges);
}

/* One row of the outline. The row above is the buffer's first row, which holds the ORIGINAL of the row
 * last outlined: each word of it is replaced by the current row's original as that is overwritten. */
static void outline_row(uint8_t *above, uint8_t *current, const uint8_t *below, uint16_t last_word)
{
    uint32_t below_long = be32(below) >> 1;
    uint8_t before_above = 0, before_current = 0;

    do {
        uint32_t above_long = rotate_right32(with_low_byte(be32(above), before_above), 1);
        uint16_t original = be16(current);
        uint16_t edges = outline_word(above_long, with_low_byte(be32(current), before_current), below_long);

        below += WORD_BYTES;
        below_long = rotate_right32(with_low_byte(be32(below), below[-1]), 1);
        wr16(current, (uint16_t)((original ^ edges) & edges));
        current += WORD_BYTES;
        before_above = (uint8_t)be16(above);
        wr16(above, original);
        above += WORD_BYTES;
        before_current = (uint8_t)original;
    } while (last_word-- != 0);
}

/* $fd2c9a — OUTLINING the scratch copy at `buffer` in place, DELY rows from its second, `row_bytes` a row:
 * the last row is outlined with itself as the row below. */
static void outline(uint8_t *image, const struct textblt *frame, uint32_t buffer, uint16_t row_bytes)
{
    uint8_t *above = image + buffer;
    uint8_t *current = above + (int16_t)row_bytes;
    uint8_t *below = current + (int16_t)row_bytes;
    uint16_t last_word = (uint16_t)((row_bytes >> 1) - 1);
    uint16_t remaining = ram_uword(image, LINEA_DELY);

    while (remaining-- != 0) {
        outline_row(above, current, below, last_word);
        current = below;
        below += (int16_t)frame->source_step;
        if (remaining == 1)
            below = current;
    }
}

/* ---- the pre-pass ------------------------------------------------------------------------------------- */

/* $fd1f6e — the glyph blitted, thickened and skewed, into the scratch buffer: one plane, colour 1 on 0,
 * `TEXT_SCRATCH_WRITE_MODE`. For an outline it lands one pixel in from a cleared border, and the copy is
 * then outlined. DELX (and DELY, outlined) become the copy's size, the source the copy, and the effects
 * done here leave STYLE. */
static void prepass(uint8_t *image, struct textblt *frame, uint16_t offsets)
{
    uint16_t source_x = ram_uword(image, LINEA_SOURCEX);
    uint16_t weight = ram_uword(image, LINEA_WEIGHT);
    uint16_t width = ram_uword(image, LINEA_DELX), rows, style, row_bytes, saved_mode, saved_style;
    uint32_t below, fill, buffer;
    const uint8_t *source;

    frame->source_bit = source_x & PIXEL_IN_GROUP_MASK;
    frame->height = ram_uword(image, LINEA_DELY);
    below = mulu_word((uint16_t)(ram_uword(image, LINEA_SOURCEY) + frame->height - 1), frame->source_step);
    frame->source_step = (uint16_t)-frame->source_step;
    source = image + frame->source + (int16_t)column_bytes(source_x) + below;
    if (ram_uword(image, LINEA_STYLE) & VDI_STYLE_THICKEN_MASK) {
        width = (uint16_t)(width + weight);
        frame->weight = weight;
    }
    frame->dest_bit = 0;
    rows = ram_uword(image, LINEA_DELY);
    style = ram_uword(image, LINEA_STYLE);
    if (style & VDI_STYLE_OUTLINE_MASK) {
        width = (uint16_t)(width + TEXT_OUTLINE_BLIT_WIDTH);
        frame->dest_bit++;
        add_ram_word(image, LINEA_DELY, TEXT_OUTLINE_GROWTH);
        rows = (uint16_t)(rows + TEXT_OUTLINE_BLIT_WIDTH);
    }
    frame->width = width;
    width = (uint16_t)(width + offsets);
    set_ram_word(image, LINEA_DELX, width);
    row_bytes = padded_row_bytes(width);
    frame->dest_step = (uint16_t)-row_bytes;
    fill = mulu_word(row_bytes, (uint16_t)(rows - 1));
    buffer = select_scratch(image, frame);
    if (style & (VDI_STYLE_OUTLINE_MASK | VDI_STYLE_SKEW_MASK)) {
        uint16_t words = (uint16_t)((uint16_t)(fill + row_bytes) >> 1);
        uint8_t *clear = image + buffer;

        for (; words != 0; words--, clear += WORD_BYTES)
            wr16(clear, 0);
        if (style & VDI_STYLE_OUTLINE_MASK) {
            frame->width = (uint16_t)(frame->width - TEXT_OUTLINE_BLIT_WIDTH);
            add_ram_word(image, LINEA_DELX, WHOLE_WORD);
            fill = set_low_word(fill, (uint16_t)(fill - row_bytes));
        }
    }
    saved_mode = ram_uword(image, LINEA_WRT_MODE);
    saved_style = ram_uword(image, LINEA_STYLE);
    set_ram_word(image, LINEA_WRT_MODE, TEXT_SCRATCH_WRITE_MODE);
    frame->fg_bits = 1;
    frame->bg_bits = 0;
    frame->planes_left = 1;
    frame->group_bytes = WORD_BYTES;
    set_ram_word(image, LINEA_STYLE, saved_style & TEXT_PREPASS_APPLIED);
    blit(image, frame, source, image + buffer + (int16_t)word_of(fill));
    set_ram_word(image, LINEA_STYLE, saved_style);
    set_ram_word(image, LINEA_WRT_MODE, saved_mode);
    frame->source_step = row_bytes;
    frame->source = buffer;
    if (ram_uword(image, LINEA_STYLE) & VDI_STYLE_OUTLINE_MASK) {
        frame->source += sign_ext16(row_bytes);
        outline(image, frame, buffer, row_bytes);
    }
    set_ram_word(image, LINEA_SOURCEX, 0);
    set_ram_word(image, LINEA_SOURCEY, 0);
    set_ram_word(image, LINEA_STYLE, ram_uword(image, LINEA_STYLE) & (uint16_t)~TEXT_PREPASS_APPLIED);
}

/* ---- clipping ------------------------------------------------------------------------------------------ */

/* One axis of $fd1ed4's test, before anything is drawn: 0 when `at` .. `at + size - 1` misses min..max.
 * `*cut` counts the ends the clip will cut. */
static int reaches_window(int16_t at, uint16_t size, int16_t min, int16_t max, uint16_t *cut)
{
    if (at < min) {
        (*cut)++;
        return (int16_t)(at + size) > min;
    }
    if (at > max)
        return 0;
    if ((int16_t)(at + size - 1) > max)
        (*cut)++;
    return 1;
}

/* One axis of $fd20b8's clip of the final blit: DEST, DEL and SOURCE of that axis cut to min..max; 0 when
 * nothing is left. */
static int clip_axis(uint8_t *image, uint32_t dest_field, uint32_t size_field, uint32_t source_field,
                     int16_t min, int16_t max)
{
    int16_t at = (int16_t)ram_uword(image, dest_field);

    if (at < min) {
        uint16_t size = ram_uword(image, size_field);
        int16_t end = (int16_t)(at + size);

        if (end <= min)
            return 0;
        set_ram_word(image, size_field, (uint16_t)(end - min));
        add_ram_word(image, source_field, (uint16_t)(size - (uint16_t)(end - min)));
        at = min;
        set_ram_word(image, dest_field, (uint16_t)at);
    }
    if (at > max)
        return 0;
    at = (int16_t)(at + ram_uword(image, size_field) - 1);
    if (at > max)
        add_ram_word(image, size_field, (uint16_t)-(uint16_t)(at - max));
    return 1;
}

/* ---- TextBlt ------------------------------------------------------------------------------------------- */

/* $fd215e — the final blit, onto the screen: the source from its bottom row up, to the destination's
 * bottom row (placed by concat), in every plane. */
static void blit_to_screen(uint8_t *image, struct textblt *frame)
{
    uint16_t planes = ram_uword(image, LINEA_PLANES);
    uint16_t source_x = ram_uword(image, LINEA_SOURCEX);
    uint16_t dest_x = ram_uword(image, LINEA_DESTX);
    uint16_t bottom;
    uint32_t below;
    const uint8_t *source;

    frame->fg_bits = ram_uword(image, LINEA_TEXT_FG);
    frame->bg_bits = ram_uword(image, LINEA_TEXT_BG);
    frame->planes_left = planes;
    frame->group_bytes = (uint16_t)((planes & HIGH_BYTE) | image[TEXT_GROUP_BYTES_TABLE + (int16_t)planes]);
    frame->source_bit = source_x & PIXEL_IN_GROUP_MASK;
    frame->height = ram_uword(image, LINEA_DELY);
    below = mulu_word((uint16_t)(frame->height + ram_uword(image, LINEA_SOURCEY) - 1), frame->source_step);
    frame->source_step = (uint16_t)-frame->source_step;
    source = image + frame->source + (int16_t)column_bytes(source_x) + below;
    frame->width = ram_uword(image, LINEA_DELX);
    bottom = (uint16_t)(ram_uword(image, LINEA_DESTY) + frame->height - 1);
    frame->dest_bit = dest_x & PIXEL_IN_GROUP_MASK;
    frame->dest_step = (uint16_t)-ram_uword(image, LINEA_WIDTH);
    blit(image, frame, source, image + be32(image + SYSVAR_V_BAS_AD) + concat_offset(image, dest_x, bottom));
}

/* $fd1e78..$fd1ed2 — the glyph's size on the screen before any clipping: thickened (unless monospaced),
 * italic, outlined, and turned. Stores the moved DESTX/DESTY of a half or quarter turn. */
static void effective_size(uint8_t *image, struct textblt *frame, uint16_t offsets, int16_t *x, int16_t *y,
                           uint16_t *width, uint16_t *height)
{
    uint16_t angle, held;

    frame->weight = 0;
    if (ram_uword(image, LINEA_STYLE) & VDI_STYLE_THICKEN_MASK) {
        uint16_t weight = ram_uword(image, LINEA_WEIGHT);

        if (weight == 0)
            set_ram_word(image, LINEA_STYLE, ram_uword(image, LINEA_STYLE) & (uint16_t)~VDI_STYLE_THICKEN_MASK);
        if (ram_uword(image, LINEA_MONO_STATUS) == 0)
            *width = (uint16_t)(*width + weight);
    }
    if (ram_uword(image, LINEA_STYLE) & VDI_STYLE_SKEW_MASK)
        *width = (uint16_t)(*width + offsets);
    if (ram_uword(image, LINEA_STYLE) & VDI_STYLE_OUTLINE_MASK) {
        *width = (uint16_t)(*width + TEXT_OUTLINE_GROWTH);
        *height = (uint16_t)(*height + TEXT_OUTLINE_GROWTH);
    }
    angle = ram_uword(image, LINEA_CHUP);
    if (angle == 0)
        return;
    if (angle == TEXT_ROTATION_180) {
        *x = (int16_t)(*x - *width);
        set_ram_word(image, LINEA_DESTX, (uint16_t)*x);
        return;
    }
    if (angle == TEXT_ROTATION_90) {
        *y = (int16_t)(*y - *width);
        set_ram_word(image, LINEA_DESTY, (uint16_t)*y);
    }
    held = *width;
    *width = *height;
    *height = held;
}

/* $fd1e2a — SCALED: the height through `act_siz`, the width through the same DDA from XACC_DDA — one
 * pixel per carry, and one more each enlarging. */
static void scaled_size(const uint8_t *image, struct textblt *frame, uint16_t *width, uint16_t *height)
{
    uint16_t accumulator = ram_uword(image, LINEA_XACC_DDA);
    uint16_t increment = ram_uword(image, LINEA_DDA_INC);
    int enlarge = ram_uword(image, LINEA_T_SCLSTS) & VDI_SCALE_UP_MASK;
    uint16_t scaled = 0, columns;

    frame->scaled_height = (uint16_t)vdi_act_siz(image, (int16_t)*height);
    *height = frame->scaled_height;
    for (columns = *width; columns != 0; columns--) {
        scaled = (uint16_t)(scaled + word_add_extend(accumulator, increment) + (enlarge != 0));
        accumulator = (uint16_t)(accumulator + increment);
    }
    frame->scaled_accumulator = accumulator;
    frame->scaled_width = scaled;
    *width = scaled;
}

/* $fd21fe — the advance: DESTX (or DESTY, turned) moved past the glyph, from the restored sizes — or the
 * scaled ones — outlined and thickened as the ROM counts them (an italic's offsets are not counted). */
static void advance(uint8_t *image, const struct textblt *frame, uint16_t width, uint16_t height)
{
    uint16_t angle = ram_uword(image, LINEA_CHUP);

    if (ram_uword(image, LINEA_SCALE)) {
        set_ram_word(image, LINEA_XACC_DDA, frame->scaled_accumulator);
        width = frame->scaled_width;
        if (frame->swapped_axes)
            width = frame->scaled_height;
    }
    (void)height;
    if (ram_uword(image, LINEA_STYLE) & VDI_STYLE_OUTLINE_MASK)
        width = (uint16_t)(width + TEXT_OUTLINE_GROWTH);
    if ((ram_uword(image, LINEA_STYLE) & VDI_STYLE_THICKEN_MASK) && ram_uword(image, LINEA_MONO_STATUS) == 0)
        width = (uint16_t)(width + ram_uword(image, LINEA_WEIGHT));
    if (angle == 0)
        add_ram_word(image, LINEA_DESTX, width);
    else if (angle == TEXT_ROTATION_90)
        add_ram_word(image, LINEA_DESTY, (uint16_t)-width);
    else if (angle == TEXT_ROTATION_180)
        add_ram_word(image, LINEA_DESTX, (uint16_t)-width);
    else
        add_ram_word(image, LINEA_DESTY, width);
}

/* Whether the effects this glyph asks for need the pre-pass: any of them turned, an outline, or an italic
 * the clip will cut ($fd1f4a). */
static int needs_prepass(const uint8_t *image, uint16_t cut)
{
    uint16_t effects = ram_uword(image, LINEA_STYLE) & TEXT_PREPASS_EFFECTS;

    if (effects == 0)
        return 0;
    return ram_uword(image, LINEA_CHUP) != 0 || ((effects & VDI_STYLE_SKEW_MASK) && cut != 0)
           || (effects & VDI_STYLE_OUTLINE_MASK);
}

/* $fd1df6 — vector 9's CPU body. */
TRANSCRIBED_CORE
void linea_cpu_textblt(uint8_t *image)
{
    /* `link a5,#-84` over stack garbage, as the ROM's is: every field is stored before it is read — an
     * op-table slot naming an effect, whose fragment would read fields no effect set, halts instead
     * (`run_fragments`). Not zeroed: GCC would call `memset`, which the freestanding 68000 build lacks. */
    struct textblt frame;
    uint16_t saved_style = ram_uword(image, LINEA_STYLE);
    uint16_t saved_mode = ram_uword(image, LINEA_WRT_MODE);
    uint16_t saved_skew = ram_uword(image, LINEA_SKEWMASK);
    int16_t x = (int16_t)ram_uword(image, LINEA_DESTX), y = (int16_t)ram_uword(image, LINEA_DESTY);
    uint16_t width = ram_uword(image, LINEA_DELX), height = ram_uword(image, LINEA_DELY);
    uint16_t offsets = (uint16_t)(ram_uword(image, LINEA_L_OFF) + ram_uword(image, LINEA_R_OFF));
    int16_t saved_x = x, saved_y = y;
    uint16_t saved_width = width, saved_height = height, cut = 0;

    /* The frame fields the ROM clears ($fd1dfa, $fd1e26), and the two scaled sizes a turn swaps whether or
     * not they were computed (only a scaled glyph reads them back). */
    frame.scratch_half = 0;
    frame.swapped_axes = 0;
    frame.scaled_width = frame.scaled_height = 0;
    if (ram_uword(image, LINEA_SCALE))
        scaled_size(image, &frame, &width, &height);
    effective_size(image, &frame, offsets, &x, &y, &width, &height);
    if (ram_uword(image, LINEA_CLIP)
        && !(reaches_window(y, height, (int16_t)ram_uword(image, LINEA_YMINCL), (int16_t)ram_uword(image, LINEA_YMAXCL),
                            &cut)
             && reaches_window(x, width, (int16_t)ram_uword(image, LINEA_XMINCL),
                               (int16_t)ram_uword(image, LINEA_XMAXCL), &cut)))
        goto restore;
    frame.source_step = ram_uword(image, LINEA_FWIDTH);
    frame.source = be32(image + LINEA_FBASE);
    if (ram_uword(image, LINEA_SCALE))
        scale(image, &frame);
    if (needs_prepass(image, cut))
        prepass(image, &frame, offsets);
    if (ram_uword(image, LINEA_CHUP))
        rotate(image, &frame);
    if (ram_uword(image, LINEA_STYLE) & VDI_STYLE_THICKEN_MASK) {
        uint16_t weight = ram_uword(image, LINEA_WEIGHT);

        if (ram_uword(image, LINEA_MONO_STATUS) == 0)
            add_ram_word(image, LINEA_DELX, weight);
        frame.weight = weight;
    }
    if (ram_uword(image, LINEA_CLIP)
        && !(clip_axis(image, LINEA_DESTY, LINEA_DELY, LINEA_SOURCEY, (int16_t)ram_uword(image, LINEA_YMINCL),
                       (int16_t)ram_uword(image, LINEA_YMAXCL))
             && clip_axis(image, LINEA_DESTX, LINEA_DELX, LINEA_SOURCEX, (int16_t)ram_uword(image, LINEA_XMINCL),
                          (int16_t)ram_uword(image, LINEA_XMAXCL))))
        goto restore;
    blit_to_screen(image, &frame);
restore:
    set_ram_word(image, LINEA_DESTX, (uint16_t)saved_x);
    set_ram_word(image, LINEA_DELX, saved_width);
    set_ram_word(image, LINEA_DESTY, (uint16_t)saved_y);
    set_ram_word(image, LINEA_DELY, saved_height);
    set_ram_word(image, LINEA_SKEWMASK, saved_skew);
    set_ram_word(image, LINEA_WRT_MODE, saved_mode);
    set_ram_word(image, LINEA_STYLE, saved_style);
    advance(image, &frame, saved_width, saved_height);
}

/* $fcee54 — $a008 TextBlt: A6 = the Line-A base, and through vector 9. */
TRANSCRIBED_CORE
void linea_textblt(uint8_t *image)
{
    require_cpu_routine(image, LINEA_VECTOR_TEXTBLT, LINEA_ROM_CPU_TEXTBLT, "$a008: the TextBlt vector");
    linea_cpu_textblt(image);
}

/* ---- the fast path ---------------------------------------------------------------------------------------- */

/* Vector 5's byte arms, by their offsets in TEXT_FAST_ARM_TABLE: what one plane byte of a glyph row does
 * to the screen byte. */
enum fast_arm {
    FAST_ARM_COPY = 0x10,           /* replace, colour bit set */
    FAST_ARM_CLEAR = 0x22,          /* replace, clear */
    FAST_ARM_AND_NOT = 0x30,        /* transparent, clear */
    FAST_ARM_OR = 0x4a,             /* transparent, set */
    FAST_ARM_AND = 0x64,            /* reverse transparent, clear */
    FAST_ARM_OR_NOT = 0x7e,         /* reverse transparent, set */
    FAST_ARM_XOR = 0x9a             /* xor, either */
};

static inline uint8_t fast_arm_byte(uint16_t arm, uint8_t glyph, uint8_t screen)
{
    switch (arm) {
    case FAST_ARM_COPY:    return glyph;
    case FAST_ARM_CLEAR:   return 0;
    case FAST_ARM_AND_NOT: return (uint8_t)(screen & ~glyph);
    case FAST_ARM_OR:      return (uint8_t)(screen | glyph);
    case FAST_ARM_AND:     return (uint8_t)(screen & glyph);
    case FAST_ARM_OR_NOT:  return (uint8_t)(screen | (uint8_t)~glyph);
    case FAST_ARM_XOR:     return (uint8_t)(screen ^ glyph);
    default:
        recreate_not_reconstructed("the fast text body: a write mode past 3 jumps past $fd1d42's eight arms");
    }
}

/* $fd1cc4 — vector 5's CPU body: `characters` glyphs from intin, each eight pixels — one byte of the
 * form, FWIDTH bytes a row — at (x, y), `rows` rows high, a byte a plane. A glyph is the byte at its
 * character code in the form's row, and the next glyph goes in the plane group's other byte: the odd
 * byte, or the even byte of the next group. */
TRANSCRIBED_CORE
uint32_t linea_cpu_fast_text(uint8_t *image, uint32_t x, uint32_t y, uint32_t characters, uint32_t rows)
{
    int16_t group = (int16_t)word_of(x) >> GROUP_SHIFT;
    uint32_t odd_byte = (x >> TEXT_FAST_GLYPH_SHIFT) & 1;
    uint16_t planes = ram_uword(image, LINEA_PLANES);
    int32_t offset = (int32_t)((uint32_t)((int32_t)group * (int16_t)planes) * 2u + odd_byte)
                     + (int32_t)(int16_t)word_of(y) * (int16_t)ram_uword(image, LINEA_BYTES_LIN);
    uint8_t *glyph_at = image + be32(image + SYSVAR_V_BAS_AD) + offset;
    const uint8_t *form = image + be32(image + LINEA_FBASE);
    int16_t form_width = (int16_t)ram_uword(image, LINEA_FWIDTH);
    const uint8_t *codes = image + be32(image + LINEA_INTIN);
    int16_t line = (int16_t)ram_uword(image, LINEA_WIDTH);
    uint16_t mode_arm = (uint16_t)(ram_uword(image, LINEA_WRT_MODE) * WORD_BYTES);
    uint16_t last_row = (uint16_t)(word_of(rows) - 1), remaining = word_of(characters);

    if (word_of(rows) == 0)
        recreate_not_reconstructed("the fast text body: 0 rows return through the A6 it pushed ($fd1cf6)");
    while (remaining-- != 0) {
        const uint8_t *glyph = form + (int16_t)be16(codes);
        uint16_t colour = ram_uword(image, LINEA_TEXT_FG);
        uint8_t *plane_byte = glyph_at;
        uint16_t plane;

        codes += WORD_BYTES;
        for (plane = planes; plane != 0; plane--) {
            uint16_t index = (uint16_t)(mode_arm + ((colour & 1) ? TEXT_FAST_ARM_COLOUR_SET : 0));
            uint16_t arm = be16(image + TEXT_FAST_ARM_TABLE + (int16_t)index);
            const uint8_t *read = glyph;
            uint8_t *write = plane_byte;
            uint16_t row = last_row;

            colour = rotate_right16(colour, 1);
            do {
                *write = fast_arm_byte(arm, *read, *write);
                read += form_width;
                write += line;
            } while (row-- != 0);
            plane_byte += WORD_BYTES;
        }
        glyph_at++;
        if (((uintptr_t)(glyph_at - image) & 1) == 0)
            glyph_at += (int16_t)(uint16_t)((planes - 1) * WORD_BYTES);
    }
    return 1;
}

/* $fcf96a — fast_text_try, v_gtext's fast path: a string of eight-pixel glyphs whose x is on a byte, with
 * the clip on inside it by a test that refuses more than it needs to (the last row or column touching the
 * window's far edge refuses). Answers vector 5's 1, or 0 when refused — v_gtext then draws each glyph
 * with $a008. The characters are contrl[3]. */
TRANSCRIBED_CORE
uint32_t linea_fast_text(uint8_t *image)
{
    uint16_t x = ram_uword(image, LINEA_DESTX), y = ram_uword(image, LINEA_DESTY);
    uint16_t rows = ram_uword(image, LINEA_DELY);
    uint16_t characters = be16(image + be32(image + LINEA_CONTRL) + CONTRL_N_INTIN);

    if (x & TEXT_FAST_X_ALIGN_MASK)
        return 0;
    if (ram_uword(image, LINEA_CLIP)) {
        if ((int16_t)y < (int16_t)ram_uword(image, LINEA_YMINCL)
            || (int16_t)(y + rows) >= (int16_t)ram_uword(image, LINEA_YMAXCL)
            || (int16_t)x < (int16_t)ram_uword(image, LINEA_XMINCL)
            || (int16_t)((uint16_t)(characters << TEXT_FAST_GLYPH_SHIFT) + x) >= (int16_t)ram_uword(image, LINEA_XMAXCL))
            return 0;
    }
    require_cpu_routine(image, LINEA_VECTOR_FAST_TEXT, LINEA_ROM_CPU_FAST_TEXT, "fast_text_try: the fast text vector");
    return linea_cpu_fast_text(image, x, y, characters, rows);
}
