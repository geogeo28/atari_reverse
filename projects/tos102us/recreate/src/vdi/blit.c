/* blit.c — the BIT-BLOCK TRANSFER: the CPU engine behind drawing vector 4, its two Line-A front ends, and
 * the three VDI functions over them.
 *
 *   $fd1038 the engine: the fast copy $fd1352, the aligners and logic ops threaded through $fd1694..$fd19db
 *   $fd0346 $a00e copy_raster: a BITBLT block built on its own stack from two MFDBs, ptsin and intin
 *   $fd05fc $a007 bitblt: the caller's block in A6, its far corners computed and stored into it
 *   $fcb5aa vro_cpyfm (109) / $fcb5dc vrt_cpyfm (121): ptsin's corners sorted, COPY_TRAN, then $a00e
 *   $fcb614 vr_recfl (114): ptsin's corners sorted, the fill colour into COLBIT, then $a005
 *
 * THE ENGINE IS THREADED CODE. After its setup it never calls a routine per word: a row is a chain of
 * `jmp`s through three registers — A4 the row's first fragment, A3 the next one, A2 the logic op, whose
 * three entries `(a2)`, `8(a2)` and `22(a2)` draw a middle word, the first word and the last word — and
 * two ROM tables pick the fragments: $fd1278 the op, and $fd1168 (or $fd1158, one destination word) the
 * ALIGNER, by four bits of geometry. The C keeps that shape: `ALIGNERS` is $fd1168 as data, and the
 * engine's registers are `struct engine`'s fields, each named for what it holds.
 *
 * WHAT AN ALIGNER DOES is make one destination word out of the source words it overlaps. It keeps the
 * last two source words in a 32-bit LATCH (D0) and the unrotated pair in a CARRY (D1), and rotates the
 * latch so the destination word lands in its low half — left or right, and the short way round (16 - n
 * for a shift of 8 or more). The four bits that pick one: bit 0, the source's bit is LEFT of the
 * destination's (a right shift); bit 1, the shift is 8 or more; bit 2, the copy runs BACKWARDS (the
 * source's first word is at a lower address than the destination's, so it starts at the bottom right,
 * where a forward copy would overwrite source words before reading them); bit 3, the source and
 * destination spans differ by an odd number of words — which decides whether the row's first word needs
 * one source word or two, and whether its last needs one more.
 *
 * THE LATCH'S STALE HIGH HALF IS MODELLED. The fragments that read ONE source word for the first
 * destination word swap the latch's high half — whatever the last row, or the setup, left there — into
 * the low one, where the edge mask discards it so long as the source and destination rectangles are the
 * same size. $a00e's unclipped arm takes the two from ptsin independently, and backwards the stale bits
 * then reach the screen. Nothing else stale ever does: the ops rewrite only the low half, which the next
 * load replaces, and the carry is always rewritten before it is read (op 3's first word parks the old
 * destination word in its low half, which the next fragment overwrites) — so neither is modelled.
 *
 * THE RUNAWAY COUNTS are the ROM's arithmetic: a height or plane count of 0 on the aligned path
 * (`subq.w` / `beq`: 65,536 of them), and a fast copy whose source is narrower than two words (`dbf` from a
 * negative MIDDLE_COUNT: 65,535 or 65,536 middle words) — a memory smash over real strides, staged whole
 * over destination strides of 0. An op past 15 is a wild jump through the words after the op table, and
 * halts.
 *
 * THE BLOCK IS READ AGAIN AS THE ENGINE RUNS, and a destination over it changes what follows: the fast
 * copy re-reads MIDDLE_COUNT before every row, the no-source rows test it afresh every plane, and every
 * plane re-tests P_ADDR for its `and` — a pattern pointer a caller's P_NXPL steps to 0 draws unpatterned.
 */
#include <stdint.h>

#include "machine.h"
#include "recreate.h"
#include "addrs.h"
#include "m68k_idioms.h"
#include "ram_vector.h"
#include "vdi/vdi.h"
#include "vdi/attributes.h"
#include "vdi/raster.h"
#include "vdi/blit.h"
#include "vdi/transcribed.h"

#define GROUP_SHIFT          4          /* x >> 4 (`lsr.w #4`: the x is UNSIGNED here) */
#define PIXEL_IN_GROUP_MASK  15u
#define LONG_HALF_BITS       16         /* `swap`: a register's two words exchanged */
#define WHOLE_WORD           0xffffu
#define SHIFT_THE_SHORT_WAY  8          /* a shift of 8 or more rotates by 16 - n the other way ($fd1094) */
#define PIXELS_PER_WORD      16
#define CORNERS_BYTES        8          /* one rectangle of ptsin: x1, y1, x2, y2 */
#define COLBIT_PLANES        4          /* COLBIT0..COLBIT3 */

/* $fd1168's index bits ($fd107e..$fd10d4) */
#define ALIGN_SHIFT_RIGHT    1u         /* the source bit is left of the destination bit */
#define ALIGN_SHORT_WAY      2u         /* ...by 8 or more: rotate by 16 - n */
#define ALIGN_BACKWARDS      4u
#define ALIGN_ODD_SPANS      8u         /* the spans differ by an odd number of words */
#define ALIGN_SINGLE_WORD_MASK 3u       /* $fd1158's index: the shift bits alone */

/* ---- the frame: the BITBLT block as the NEGATIVE half of A6's frame --------------------------------- */

static inline uint8_t *block_field(uint8_t *frame, unsigned field)
{
    return frame - BITBLT_BYTES + field;
}

static inline uint16_t frame_word(uint8_t *frame, unsigned field)
{
    return be16(block_field(frame, field));
}

static inline uint32_t frame_long(uint8_t *frame, unsigned field)
{
    return be32(block_field(frame, field));
}

static inline void set_frame_word(uint8_t *frame, unsigned field, uint16_t value)
{
    wr16(block_field(frame, field), value);
}

static inline void set_frame_long(uint8_t *frame, unsigned field, uint32_t value)
{
    wr32(block_field(frame, field), value);
}

/* A form address as the bus sees it: the engine's addresses are 32-bit sums, and the 68000 drives 24. */
static inline uint8_t *bus(uint8_t *image, uint32_t address)
{
    return image + bus_address(address);
}

/* ---- the geometry both paths share -------------------------------------------------------------- */

/* One form as the block describes it: its base and the three strides, source or destination. */
struct form_fields {
    unsigned base, next_word, next_line;
};

static const struct form_fields SOURCE_FORM = { BITBLT_S_FORM, BITBLT_S_NXWD, BITBLT_S_NXLN };
static const struct form_fields DESTINATION_FORM = { BITBLT_D_FORM, BITBLT_D_NXWD, BITBLT_D_NXLN };

/* $fd1326 / $fd133c — the word of `form` holding (x, y), plane 0. `*group` gets the (x >> 4) * NXWD
 * product, which the ROM leaves in D0. */
static uint32_t form_word(uint8_t *frame, const struct form_fields *form, uint16_t x, uint16_t y, uint32_t *group)
{
    *group = m68k_muls_w((uint16_t)(x >> GROUP_SHIFT), frame_word(frame, form->next_word));
    return frame_long(frame, form->base) + *group + m68k_muls_w(y, frame_word(frame, form->next_line));
}

/* The word difference `span * NXWD - NXLN` ($fd10ae `muls.w` then `sub.w`): how far a row's far end is
 * from the next row's near end, before the direction's sign. */
static uint16_t row_wrap(uint8_t *frame, const struct form_fields *form, uint16_t span)
{
    return (uint16_t)(m68k_muls_w(span, frame_word(frame, form->next_word)) - frame_word(frame, form->next_line));
}

static inline uint16_t edge_mask(const uint8_t *image, unsigned pixels)
{
    return be16(image + BLIT_EDGE_MASK_TABLE + pixels * BLIT_EDGE_MASK_ENTRY_BYTES);
}

/* $fd12e2 — the destination row's two edge masks, by the block's D_XMIN / D_XMAX: the left one (every
 * pixel from x min on) in the low word, the right one (every pixel up to x max) in the high word. */
static uint32_t edge_masks(const uint8_t *image, uint8_t *frame)
{
    uint16_t right = edge_mask(image, (frame_word(frame, BITBLT_D_XMAX) & PIXEL_IN_GROUP_MASK) + 1);
    uint16_t left = (uint16_t)~edge_mask(image, frame_word(frame, BITBLT_D_XMIN) & PIXEL_IN_GROUP_MASK);

    return (uint32_t)right << LONG_HALF_BITS | left;
}

/* ---- the fast copy, $fd1352 ------------------------------------------------------------------------ */

/* The masked copy of one word ($fd13c4 `eor / and / eor`): the mask's pixels from the source. */
static inline void copy_word_under(uint8_t *image, uint32_t source, uint32_t destination, uint16_t mask)
{
    uint16_t old = be16(bus(image, destination));

    wr16(bus(image, destination), (uint16_t)(((be16(bus(image, source)) ^ old) & mask) ^ old));
}

/* A plain source copy, bit-aligned: every row word by word, plane after plane — the planes OUTER, and
 * S_START / D_START stepped and stored after EVERY plane, the last included. Word counts are the
 * SOURCE's, MIDDLE_COUNT re-read out of the block before every row ($fd13f2) — a destination row over
 * the block changes the next row's width. Backwards when the source is below the destination in memory. */
static void fast_copy(uint8_t *image, uint8_t *frame, uint16_t source_span, uint16_t destination_span)
{
    uint16_t source_step = frame_word(frame, BITBLT_S_NXWD), destination_step = frame_word(frame, BITBLT_D_NXWD);
    uint16_t source_wrap = row_wrap(frame, &SOURCE_FORM, source_span);
    uint16_t destination_wrap = row_wrap(frame, &DESTINATION_FORM, destination_span);
    uint16_t planes = frame_word(frame, BITBLT_PLANE_CT);
    uint32_t group, source, destination, masks;

    set_frame_word(frame, BITBLT_MIDDLE_COUNT, (uint16_t)(source_span - 2));
    source = form_word(frame, &SOURCE_FORM, frame_word(frame, BITBLT_S_XMIN), frame_word(frame, BITBLT_S_YMIN), &group);
    destination = form_word(frame, &DESTINATION_FORM, frame_word(frame, BITBLT_D_XMIN),
                            frame_word(frame, BITBLT_D_YMIN), &group);
    if (source < destination) {
        source = form_word(frame, &SOURCE_FORM, frame_word(frame, BITBLT_S_XMAX), frame_word(frame, BITBLT_S_YMAX), &group);
        destination = form_word(frame, &DESTINATION_FORM, frame_word(frame, BITBLT_D_XMAX),
                                frame_word(frame, BITBLT_D_YMAX), &group);
        source_step = (uint16_t)-source_step;
        destination_step = (uint16_t)-destination_step;
    } else {
        source_wrap = (uint16_t)-source_wrap;
        destination_wrap = (uint16_t)-destination_wrap;
    }
    masks = edge_masks(image, frame);
    if ((int16_t)source_step < 0)
        masks = m68k_swap(masks);
    set_frame_long(frame, BITBLT_S_START, source);
    set_frame_long(frame, BITBLT_D_START, destination);
    while (planes-- != 0) {
        uint16_t rows = frame_word(frame, BITBLT_B_HT);

        while (rows-- != 0) {
            uint16_t middle = frame_word(frame, BITBLT_MIDDLE_COUNT);

            copy_word_under(image, source, destination, (uint16_t)masks);
            do {
                source += sign_ext16(source_step);
                destination += sign_ext16(destination_step);
                wr16(bus(image, destination), be16(bus(image, source)));
            } while (middle-- != 0);
            source += sign_ext16(source_step);
            destination += sign_ext16(destination_step);
            copy_word_under(image, source, destination, (uint16_t)(masks >> LONG_HALF_BITS));
            source += sign_ext16(source_wrap);
            destination += sign_ext16(destination_wrap);
        }
        source = frame_long(frame, BITBLT_S_START) + sign_ext16(frame_word(frame, BITBLT_S_NXPL));
        destination = frame_long(frame, BITBLT_D_START) + sign_ext16(frame_word(frame, BITBLT_D_NXPL));
        set_frame_long(frame, BITBLT_S_START, source);
        set_frame_long(frame, BITBLT_D_START, destination);
    }
}

/* ---- the aligned path: the engine's registers, and the fragments they are threaded through ---------- */

enum rotation_way { ROTATE_LEFT, ROTATE_RIGHT };

/* How a fragment pairs the word it has just read (in the latch's low half) with the one before it. */
enum pairing {
    PAIR_SWAPPING_LATCH,        /* `swap d0 / move.l d0,d1`: the new word high, the old low */
    PAIR_SWAPPING_CARRY,        /* `move.l d0,d1 / swap d1`: the new word low, the old high */
};

/* One entry of $fd1168: the row's first fragment (A4) and the middle loop (A3) that goes with it. */
struct aligner {
    uint8_t first_reads;        /* 2: the whole first fragment; 1: its entry past the first read */
    uint8_t pairing;
    uint8_t way;
    uint8_t last_reads;         /* the middle loop's exit reads one more source word for the last */
    uint8_t last_swaps;         /* ...and swaps the latch before the last word ($fd1796) */
};

static const struct aligner ALIGNERS[] = {
    { 2, PAIR_SWAPPING_LATCH, ROTATE_LEFT,  0, 1 },   /*  0 $fd16f6 $fd1792 */
    { 1, PAIR_SWAPPING_CARRY, ROTATE_RIGHT, 1, 0 },   /*  1 $fd16ea $fd1764 */
    { 2, PAIR_SWAPPING_CARRY, ROTATE_RIGHT, 0, 1 },   /*  2 $fd16e4 $fd178c */
    { 1, PAIR_SWAPPING_LATCH, ROTATE_LEFT,  1, 1 },   /*  3 $fd16fc $fd1772 */
    { 1, PAIR_SWAPPING_CARRY, ROTATE_LEFT,  1, 0 },   /*  4 $fd16d8 $fd1756 */
    { 2, PAIR_SWAPPING_LATCH, ROTATE_RIGHT, 0, 1 },   /*  5 $fd16c0 $fd1780 */
    { 1, PAIR_SWAPPING_LATCH, ROTATE_RIGHT, 1, 1 },   /*  6 $fd16c6 $fd1748 */
    { 2, PAIR_SWAPPING_CARRY, ROTATE_LEFT,  0, 1 },   /*  7 $fd16d2 $fd1786 */
    { 2, PAIR_SWAPPING_LATCH, ROTATE_LEFT,  1, 1 },   /*  8 $fd16f6 $fd1772 */
    { 1, PAIR_SWAPPING_CARRY, ROTATE_RIGHT, 0, 1 },   /*  9 $fd16ea $fd178c */
    { 2, PAIR_SWAPPING_CARRY, ROTATE_RIGHT, 1, 0 },   /* 10 $fd16e4 $fd1764 */
    { 1, PAIR_SWAPPING_LATCH, ROTATE_LEFT,  0, 1 },   /* 11 $fd16fc $fd1792 */
    { 2, PAIR_SWAPPING_CARRY, ROTATE_LEFT,  1, 0 },   /* 12 $fd16d2 $fd1756 */
    { 1, PAIR_SWAPPING_LATCH, ROTATE_RIGHT, 0, 1 },   /* 13 $fd16c6 $fd1780 */
    { 2, PAIR_SWAPPING_LATCH, ROTATE_RIGHT, 1, 1 },   /* 14 $fd16c0 $fd1748 */
    { 1, PAIR_SWAPPING_CARRY, ROTATE_LEFT,  0, 1 },   /* 15 $fd16d8 $fd1786 */
};
/* ...and $fd1158, for a row that is ONE destination word whose source is one word too: a word rotate,
 * by the shift bits alone ($fd16b0 `rol.w`, $fd16b8 `ror.w`). */
static const uint8_t SINGLE_WORD_WAYS[] = { ROTATE_LEFT, ROTATE_RIGHT, ROTATE_RIGHT, ROTATE_LEFT };

struct engine {
    uint8_t *image;
    uint8_t *frame;
    uint32_t source;            /* A0 */
    uint32_t destination;       /* A1 */
    uint32_t latch;             /* D0 */
    uint32_t carry;             /* D1 */
    uint16_t source_step;       /* D2: S_NXWD, negated backwards */
    uint16_t destination_step;  /* D3 */
    uint16_t rotation;          /* D4 */
    uint16_t middle_left;       /* D5's low word */
    uint16_t rows_left;         /* D5's high word */
    uint32_t masks;             /* D6: the mask in use low, the row's other end high */
    uint16_t pattern_row;       /* D7's high word: the pattern row's byte offset */
    uint16_t pattern_word;      /* D7's low word */
    const struct aligner *aligner;
    int single_word;            /* the row is one destination word ($fd112e) — the source ops' setup verdict */
    int word_rotate;            /* ...and one source word: $fd1158's word rotate */
    uint8_t word_rotate_way;
    int loads_pattern;          /* P_ADDR set at setup: $fd1694 heads every row (A4 and A5 exchanged) */
    int patterned;              /* THIS plane's P_ADDR set ($fd1234): its op entered one instruction early,
                                   `and.w d7,d0` — a P_ADDR stepped to 0 loads rows but ANDs nothing */
    unsigned op;                /* A2 */
};

static inline void rotate_latch(struct engine *engine, unsigned way)
{
    engine->latch = way == ROTATE_LEFT ? rotate_left32(engine->latch, engine->rotation)
                                       : rotate_right32(engine->latch, engine->rotation);
}

/* `move.w (a0),d0` */
static inline void read_source(struct engine *engine)
{
    engine->latch = set_low_word(engine->latch, be16(bus(engine->image, engine->source)));
}

/* The step every aligner fragment ends in: a source word read, paired with the one before, rotated. */
static void pair_next_word(struct engine *engine)
{
    const struct aligner *aligner = engine->aligner;

    read_source(engine);
    if (aligner->pairing == PAIR_SWAPPING_LATCH) {
        engine->latch = m68k_swap(engine->latch);
        engine->carry = engine->latch;
    } else {
        engine->carry = m68k_swap(engine->latch);
    }
    rotate_latch(engine, aligner->way);
}

/* A4's fragment: the row's first destination word into the latch's low half. */
static void load_first_word(struct engine *engine)
{
    if (engine->word_rotate) {
        uint16_t word = be16(bus(engine->image, engine->source));

        engine->latch = set_low_word(engine->latch, engine->word_rotate_way == ROTATE_LEFT
                                                        ? rotate_left16(word, engine->rotation)
                                                        : rotate_right16(word, engine->rotation));
        return;
    }
    if (engine->aligner->first_reads == 2) {
        read_source(engine);
        engine->source += sign_ext16(engine->source_step);
        engine->latch = m68k_swap(engine->latch);
    }
    pair_next_word(engine);
}

/* $fd1708..$fd1746: the next word along, source and destination both. */
static void load_middle_word(struct engine *engine)
{
    engine->source += sign_ext16(engine->source_step);
    engine->destination += sign_ext16(engine->destination_step);
    engine->latch = engine->carry;
    pair_next_word(engine);
}

/* The middle loop's exit ($fd174c..$fd1798): the last word is either one more source word, or what the
 * last rotate left in the latch's HIGH half. */
static void load_last_word(struct engine *engine)
{
    if (engine->aligner->last_reads) {
        engine->source += sign_ext16(engine->source_step);
        engine->latch = engine->carry;
        read_source(engine);
        rotate_latch(engine, engine->aligner->way);
    }
    if (engine->aligner->last_swaps)
        engine->latch = m68k_swap(engine->latch);
    engine->destination += sign_ext16(engine->destination_step);
}

/* $fd1694 — the row's pattern word, and the row after it. */
static void load_pattern_row(struct engine *engine)
{
    uint8_t *frame = engine->frame;
    uint16_t offset = engine->pattern_row & frame_word(frame, BITBLT_P_MASK);

    engine->pattern_row = (uint16_t)(engine->pattern_row + frame_word(frame, BITBLT_P_NXLN));
    engine->pattern_word = be16(bus(engine->image, frame_long(frame, BITBLT_P_ADDR) + sign_ext16(offset)));
}

/* ---- the sixteen logic ops ($fd17e2..$fd19db) ----------------------------------------------------- */

static inline int reads_source(unsigned op)
{
    return !(BLIT_NO_SOURCE_OPS_SET >> op & 1);
}

static uint16_t logic_op(unsigned op, uint16_t source, uint16_t old)
{
    switch (op) {
    case BLIT_OP_ZERO:          return 0;
    case BLIT_OP_S_AND_D:       return source & old;
    case BLIT_OP_S_AND_NOT_D:   return source & (uint16_t)~old;
    case BLIT_OP_S:             return source;
    case BLIT_OP_NOT_S_AND_D:   return (uint16_t)~source & old;
    case BLIT_OP_S_XOR_D:       return source ^ old;
    case BLIT_OP_S_OR_D:        return source | old;
    case BLIT_OP_NOR:           return (uint16_t)~(source | old);
    case BLIT_OP_XNOR:          return (uint16_t)~(source ^ old);
    case BLIT_OP_NOT_D:         return (uint16_t)~old;
    case BLIT_OP_S_OR_NOT_D:    return source | (uint16_t)~old;
    case BLIT_OP_NOT_S:         return (uint16_t)~source;
    case BLIT_OP_NOT_S_OR_D:    return (uint16_t)~source | old;
    case BLIT_OP_NAND:          return (uint16_t)~(source & old);
    default:                    return WHOLE_WORD;         /* BLIT_OP_ONE; BLIT_OP_D never gets here */
    }
}

/* The op on the destination word, whole (`(a2)`) or under the mask in use (`8(a2)`, `22(a2)`) — the
 * pattern word ANDed into the source first when there is one. The fragments also leave D0's low word
 * complemented, masked or rebuilt on the way, which is not modelled: nothing reads it before the next
 * load replaces it, and the one stale half a fragment does read is the HIGH one, which no op touches. */
static void apply_op(struct engine *engine, int masked)
{
    uint8_t *word = bus(engine->image, engine->destination);
    uint16_t old = be16(word);
    uint16_t source = (uint16_t)engine->latch;
    uint16_t mask = (uint16_t)engine->masks;
    uint16_t result;

    if (engine->patterned)
        source &= engine->pattern_word;
    result = logic_op(engine->op, source, old);
    wr16(word, masked ? (uint16_t)((result & mask) | (old & (uint16_t)~mask)) : result);
}

/* $fd17a6 — the next row, or false when this plane's rows are spent. */
static int next_row(struct engine *engine, int reads)
{
    if (--engine->rows_left == 0)
        return 0;
    if (reads)
        engine->source += sign_ext16(frame_word(engine->frame, BITBLT_S_WRAP));
    engine->destination += sign_ext16(frame_word(engine->frame, BITBLT_D_WRAP));
    return 1;
}

/* A row past its first word: the middle words whole (`dbf`: MIDDLE_COUNT of them), then the last under
 * the other end's mask, the masks swapped round it. `reads` is the source ops' walk; the three ops
 * that read no source step the destination alone ($fd17be). */
static void rest_of_row(struct engine *engine, int reads)
{
    while (engine->middle_left-- != 0) {
        if (reads) {
            load_middle_word(engine);
        } else {
            engine->destination += sign_ext16(engine->destination_step);
        }
        apply_op(engine, 0);
    }
    if (reads) {
        load_last_word(engine);
    } else {
        engine->destination += sign_ext16(engine->destination_step);
    }
    engine->masks = m68k_swap(engine->masks);
    apply_op(engine, 1);
    engine->masks = m68k_swap(engine->masks);
    engine->middle_left = frame_word(engine->frame, BITBLT_MIDDLE_COUNT);
}

/* One plane's rows (`jsr (a4)`). `reads`: an op that reads the source, through its aligner and the
 * pattern; the others ($fd12b8) write the destination alone. `single_word`: one destination word a row. */
static void plane_rows(struct engine *engine, int reads, int single_word)
{
    do {
        if (reads) {
            if (engine->loads_pattern)
                load_pattern_row(engine);
            load_first_word(engine);
        }
        apply_op(engine, 1);
        if (!single_word)
            rest_of_row(engine, reads);
    } while (next_row(engine, reads));
}

/* $fd1206 — the plane's op: OP_TAB by this plane's foreground and background bits, each spent out of
 * the block (`lsr.w` in memory), the foreground's the high bit of the index. */
static unsigned plane_op(uint8_t *frame)
{
    uint16_t foreground = frame_word(frame, BITBLT_FG_COL), background = frame_word(frame, BITBLT_BG_COL);
    unsigned index = (foreground & 1u) << 1 | (background & 1u);

    set_frame_word(frame, BITBLT_FG_COL, foreground >> 1);
    set_frame_word(frame, BITBLT_BG_COL, background >> 1);
    return *block_field(frame, BITBLT_OP_TAB + index);
}

/* The setup of the aligned path ($fd1076..$fd1204): the aligner, the start of each form, the row wraps
 * and the edge masks — the start at the bottom right, and every step negated, when BACKWARDS. */
static void aligned_setup(struct engine *engine, uint16_t source_span, uint16_t destination_span, int16_t shift)
{
    uint8_t *frame = engine->frame;
    unsigned index = (unsigned)((source_span - destination_span) & 1) * ALIGN_ODD_SPANS;
    uint16_t distance = (uint16_t)shift;
    uint16_t source_wrap = row_wrap(frame, &SOURCE_FORM, source_span);
    uint16_t destination_wrap = row_wrap(frame, &DESTINATION_FORM, destination_span);
    uint32_t group;

    set_frame_word(frame, BITBLT_MIDDLE_COUNT, (uint16_t)(destination_span - 1));
    if (shift < 0) {
        distance = (uint16_t)-shift;
        index |= ALIGN_SHIFT_RIGHT;
    }
    if (shift != 0 && distance >= SHIFT_THE_SHORT_WAY) {
        index |= ALIGN_SHORT_WAY;
        distance = (uint16_t)(PIXELS_PER_WORD - distance);
    }
    engine->rotation = distance;
    engine->source = form_word(frame, &SOURCE_FORM, frame_word(frame, BITBLT_S_XMIN), frame_word(frame, BITBLT_S_YMIN),
                               &group);
    set_frame_word(frame, BITBLT_P_INDEX, frame_word(frame, BITBLT_D_YMIN));
    engine->destination = form_word(frame, &DESTINATION_FORM, frame_word(frame, BITBLT_D_XMIN),
                                    frame_word(frame, BITBLT_D_YMIN), &engine->latch);
    if (engine->source < engine->destination || (engine->source == engine->destination && shift < 0)) {
        index |= ALIGN_BACKWARDS;
        engine->source = form_word(frame, &SOURCE_FORM, frame_word(frame, BITBLT_S_XMAX),
                                   frame_word(frame, BITBLT_S_YMAX), &group);
        set_frame_word(frame, BITBLT_P_INDEX, frame_word(frame, BITBLT_D_YMAX));
        engine->destination = form_word(frame, &DESTINATION_FORM, frame_word(frame, BITBLT_D_XMAX),
                                        frame_word(frame, BITBLT_D_YMAX), &engine->latch);
        set_frame_word(frame, BITBLT_P_NXLN, (uint16_t)-frame_word(frame, BITBLT_P_NXLN));
    } else {
        source_wrap = (uint16_t)-source_wrap;
        destination_wrap = (uint16_t)-destination_wrap;
    }
    set_frame_word(frame, BITBLT_S_WRAP, source_wrap);
    set_frame_word(frame, BITBLT_D_WRAP, destination_wrap);
    engine->masks = edge_masks(engine->image, frame);
    engine->source_step = frame_word(frame, BITBLT_S_NXWD);
    engine->destination_step = frame_word(frame, BITBLT_D_NXWD);
    if (index & ALIGN_BACKWARDS) {
        engine->masks = m68k_swap(engine->masks);
        engine->source_step = (uint16_t)-engine->source_step;
        engine->destination_step = (uint16_t)-engine->destination_step;
    }
    set_frame_long(frame, BITBLT_S_START, engine->source);
    set_frame_long(frame, BITBLT_D_START, engine->destination);
    engine->aligner = &ALIGNERS[index];
    engine->single_word = (int16_t)frame_word(frame, BITBLT_MIDDLE_COUNT) < 0;
    engine->word_rotate = 0;
    if (engine->single_word) {
        /* both edges in the one word; D0 keeps the masks the other way round */
        engine->latch = m68k_swap(engine->masks);
        engine->masks = set_low_word(engine->masks, (uint16_t)(engine->masks & engine->latch));
        engine->word_rotate = !(index & ALIGN_ODD_SPANS);
        engine->word_rotate_way = SINGLE_WORD_WAYS[index & ALIGN_SINGLE_WORD_MASK];
    }
}

/* $fd11e8 — a pattern: its first row is the start row's y times the (unsigned) row step. */
static void pattern_setup(struct engine *engine)
{
    uint8_t *frame = engine->frame;
    uint16_t step = frame_word(frame, BITBLT_P_NXLN);

    engine->loads_pattern = frame_long(frame, BITBLT_P_ADDR) != 0;
    if (!engine->loads_pattern)
        return;
    if ((int16_t)step < 0)
        step = (uint16_t)-step;
    engine->latch = m68k_muls_w(step, frame_word(frame, BITBLT_P_INDEX));
    set_frame_word(frame, BITBLT_P_INDEX, (uint16_t)engine->latch);
}

static void aligned_copy(uint8_t *image, uint8_t *frame, uint16_t source_span, uint16_t destination_span,
                         int16_t shift)
{
    struct engine engine;

    engine.image = image;
    engine.frame = frame;
    engine.carry = 0;
    engine.pattern_row = 0;
    engine.pattern_word = 0;
    engine.patterned = 0;
    aligned_setup(&engine, source_span, destination_span, shift);
    pattern_setup(&engine);
    for (;;) {
        uint32_t pattern;

        engine.op = plane_op(frame);
        if (engine.op >= BLIT_OP_COUNT)
            recreate_not_reconstructed("the blit engine: an op past 15 jumps through the words after $fd1278");
        engine.rows_left = frame_word(frame, BITBLT_B_HT);
        engine.middle_left = frame_word(frame, BITBLT_MIDDLE_COUNT);
        if (reads_source(engine.op)) {
            /* a plane whose P_ADDR is 0 keeps the row offset the last plane left ($fd1238 skips the reload) */
            engine.patterned = frame_long(frame, BITBLT_P_ADDR) != 0;
            if (engine.patterned)
                engine.pattern_row = frame_word(frame, BITBLT_P_INDEX);
            plane_rows(&engine, 1, engine.single_word);
        } else if (engine.op != BLIT_OP_D) {
            /* the no-source rows test MIDDLE_COUNT afresh each plane ($fd12ce `tst.w d5`) */
            plane_rows(&engine, 0, (int16_t)engine.middle_left < 0);
        }
        set_frame_word(frame, BITBLT_PLANE_CT, (uint16_t)(frame_word(frame, BITBLT_PLANE_CT) - 1));
        if (frame_word(frame, BITBLT_PLANE_CT) == 0)
            return;
        engine.source = frame_long(frame, BITBLT_S_START) + sign_ext16(frame_word(frame, BITBLT_S_NXPL));
        set_frame_long(frame, BITBLT_S_START, engine.source);
        engine.destination = frame_long(frame, BITBLT_D_START) + sign_ext16(frame_word(frame, BITBLT_D_NXPL));
        set_frame_long(frame, BITBLT_D_START, engine.destination);
        pattern = frame_long(frame, BITBLT_P_ADDR);
        engine.latch = pattern;
        if (pattern != 0)
            set_frame_long(frame, BITBLT_P_ADDR, pattern + sign_ext16(frame_word(frame, BITBLT_P_NXPL)));
    }
}

/* $fd1038 — the engine, both paths, over the block at `frame - 76`. The x edges come in registers, and
 * everything else — the y edges too — out of the block. */
static void cpu_blit(uint8_t *image, uint8_t *frame, uint16_t source_x_min, uint16_t destination_x_min,
                     uint16_t source_x_max, uint16_t destination_x_max)
{
    uint16_t source_span = (uint16_t)((source_x_max >> GROUP_SHIFT) - (source_x_min >> GROUP_SHIFT));
    uint16_t destination_span = (uint16_t)((destination_x_max >> GROUP_SHIFT) - (destination_x_min >> GROUP_SHIFT));
    int16_t shift = (int16_t)((source_x_min & PIXEL_IN_GROUP_MASK) - (destination_x_min & PIXEL_IN_GROUP_MASK));

    if (shift == 0 && frame_long(frame, BITBLT_FG_COL) == 0 && *block_field(frame, BITBLT_OP_TAB) == BLIT_OP_S
        && (uint16_t)(source_span + destination_span) >= BLIT_FAST_SPAN_WORDS && frame_long(frame, BITBLT_P_ADDR) == 0) {
        fast_copy(image, frame, source_span, destination_span);
        return;
    }
    aligned_copy(image, frame, source_span, destination_span, shift);
}

TRANSCRIBED_CORE
void linea_cpu_blit(uint8_t *image, uint32_t source_x_min, uint32_t destination_x_min, uint32_t source_x_max,
                    uint32_t destination_x_max, uint32_t frame)
{
    cpu_blit(image, bus(image, frame), (uint16_t)source_x_min, (uint16_t)destination_x_min, (uint16_t)source_x_max,
             (uint16_t)destination_x_max);
}

/* The block's far corners in, and the engine through vector 4 — both front ends' last step. */
static void enter_engine(uint8_t *image, uint8_t *frame)
{
    require_cpu_routine(image, LINEA_VECTOR_BITBLT, LINEA_ROM_CPU_BLIT, "a blit front end: the bit-block vector");
    cpu_blit(image, frame, frame_word(frame, BITBLT_S_XMIN), frame_word(frame, BITBLT_D_XMIN),
             frame_word(frame, BITBLT_S_XMAX), frame_word(frame, BITBLT_D_XMAX));
}

/* ---- $a007 ------------------------------------------------------------------------------------------- */

/* $fd05fc — $a007 bitblt: the caller's block, its far corners = the near ones + B_WD / B_HT - 1, STORED
 * into the block, then the engine — which leaves its working words there too. */
TRANSCRIBED_CORE
void linea_bitblt(uint8_t *image, uint32_t block)
{
    uint8_t *frame = bus(image, block + BITBLT_BYTES);
    uint16_t below = (uint16_t)(frame_word(frame, BITBLT_B_HT) - 1);
    uint16_t across = (uint16_t)(frame_word(frame, BITBLT_B_WD) - 1);

    set_frame_word(frame, BITBLT_S_XMAX, (uint16_t)(frame_word(frame, BITBLT_S_XMIN) + across));
    set_frame_word(frame, BITBLT_S_YMAX, (uint16_t)(frame_word(frame, BITBLT_S_YMIN) + below));
    set_frame_word(frame, BITBLT_D_XMAX, (uint16_t)(frame_word(frame, BITBLT_D_XMIN) + across));
    set_frame_word(frame, BITBLT_D_YMAX, (uint16_t)(frame_word(frame, BITBLT_D_YMIN) + below));
    enter_engine(image, frame);
}

/* ---- $a00e ------------------------------------------------------------------------------------------- */

/* A form as an MFDB gives it: a null base is the SCREEN, PLANES deep and WIDTH bytes a line (the
 * Line-A fields — not BYTES_LIN); any other, its own planes and `wdwidth * 2 * planes` (`mulu.w`). */
struct form {
    uint32_t base;
    uint16_t planes;
    uint16_t line_bytes;
};

static struct form mfdb_form(uint8_t *image, uint32_t mfdb)
{
    struct form form;

    form.base = be32(bus(image, mfdb + MFDB_ADDR));
    if (form.base == 0) {
        form.base = be32(image + SYSVAR_V_BAS_AD);
        form.planes = be16(image + LINEA_PLANES);
        form.line_bytes = be16(image + LINEA_WIDTH);
    } else {
        form.planes = be16(bus(image, mfdb + MFDB_NPLANES));
        form.line_bytes = (uint16_t)((uint16_t)(be16(bus(image, mfdb + MFDB_WDWIDTH)) * 2) * (uint32_t)form.planes);
    }
    return form;
}

/* A transparent copy's colour, intin[index]: past the device's colours (`bmi` on the difference, so by
 * its SIGN BIT) it is 1, and then it is mapped to its pen. */
static uint16_t transparent_pen(const uint8_t *image, unsigned index)
{
    uint16_t colour = (uint16_t)intin_word(image, index);
    uint16_t colours = be16(image + LINEA_DEV_TAB + VDI_DEV_TAB_COLOURS_INDEX * VDI_WORD_BYTES);

    if (!((colour - colours) & SIGN_BIT16))
        colour = 1;
    return be16(image + (uint32_t)(VDI_MAP_COL + sign_ext16((uint16_t)(colour * VDI_WORD_BYTES))));
}

/* The four ops of a mode that uses them, OP_TAB order (fg * 2 + bg): only the entries the mode's
 * colours can reach are STORED — the rest of the block's OP_TAB is whatever the stack held. */
static int transparent_ops(uint8_t *frame, uint16_t mode, uint16_t foreground, uint16_t background)
{
    uint8_t *ops = block_field(frame, BITBLT_OP_TAB);

    switch (mode) {
    case BLIT_MODE_REPLACE:
        set_frame_word(frame, BITBLT_BG_COL, background);
        set_frame_word(frame, BITBLT_FG_COL, foreground);
        ops[0] = BLIT_OP_ZERO;
        ops[1] = BLIT_OP_NOT_S;
        ops[2] = BLIT_OP_S;
        ops[3] = BLIT_OP_ONE;
        return 1;
    case BLIT_MODE_TRANSPARENT:
        ops[0] = BLIT_OP_NOT_S_AND_D;
        ops[2] = BLIT_OP_S_OR_D;
        set_frame_word(frame, BITBLT_BG_COL, 0);
        set_frame_word(frame, BITBLT_FG_COL, foreground);
        return 1;
    case BLIT_MODE_XOR:
        set_frame_word(frame, BITBLT_BG_COL, 0);
        set_frame_word(frame, BITBLT_FG_COL, 0);
        ops[0] = BLIT_OP_S_XOR_D;
        return 1;
    case BLIT_MODE_REVERSE:
        ops[0] = BLIT_OP_S_AND_D;
        ops[1] = BLIT_OP_NOT_S_OR_D;
        set_frame_word(frame, BITBLT_FG_COL, 0);
        set_frame_word(frame, BITBLT_BG_COL, background);
        return 1;
    default:
        return 0;
    }
}

/* $fd0544 — the clipped corners, against the clip rectangle: a near edge before the clip moves the
 * source's with it, the far edges are the near ones plus the SOURCE's size, cut at the clip. False
 * when nothing is left — a width or height of 0 or less as `addq.w #1 / ble` sees it, which is the
 * difference's sign. */
static int clipped_corners(uint8_t *image, uint8_t *frame, uint32_t ptsin)
{
    int16_t source_x = (int16_t)be16(bus(image, ptsin)), destination_x = (int16_t)be16(bus(image, ptsin + 8));
    int16_t source_y, destination_y, destination_x_max, destination_y_max;
    int16_t clip_x = (int16_t)be16(image + LINEA_XMINCL), clip_y;
    uint16_t across, below;

    if (destination_x < clip_x) {
        source_x = (int16_t)(source_x + clip_x - destination_x);
        destination_x = clip_x;
    }
    set_frame_word(frame, BITBLT_S_XMIN, (uint16_t)source_x);
    set_frame_word(frame, BITBLT_D_XMIN, (uint16_t)destination_x);
    destination_x_max = (int16_t)(be16(bus(image, ptsin + 4)) - source_x + destination_x);
    if (destination_x_max > (int16_t)be16(image + LINEA_XMAXCL))
        destination_x_max = (int16_t)be16(image + LINEA_XMAXCL);
    source_y = (int16_t)be16(bus(image, ptsin + 2));
    destination_y = (int16_t)be16(bus(image, ptsin + 10));
    clip_y = (int16_t)be16(image + LINEA_YMINCL);
    if (destination_y < clip_y) {
        source_y = (int16_t)(source_y + clip_y - destination_y);
        destination_y = clip_y;
    }
    set_frame_word(frame, BITBLT_S_YMIN, (uint16_t)source_y);
    set_frame_word(frame, BITBLT_D_YMIN, (uint16_t)destination_y);
    destination_y_max = (int16_t)(be16(bus(image, ptsin + 6)) - source_y + destination_y);
    if (destination_y_max > (int16_t)be16(image + LINEA_YMAXCL))
        destination_y_max = (int16_t)be16(image + LINEA_YMAXCL);
    across = (uint16_t)(destination_x_max - destination_x);
    if ((int16_t)across < 0)
        return 0;
    below = (uint16_t)(destination_y_max - destination_y);
    set_frame_word(frame, BITBLT_B_HT, (uint16_t)(below + 1));
    if ((int16_t)below < 0)
        return 0;
    set_frame_word(frame, BITBLT_S_XMAX, (uint16_t)(across + source_x));
    set_frame_word(frame, BITBLT_S_YMAX, (uint16_t)(below + source_y));
    set_frame_word(frame, BITBLT_D_XMAX, (uint16_t)destination_x_max);
    set_frame_word(frame, BITBLT_D_YMAX, (uint16_t)destination_y_max);
    return 1;
}

/* $fd04fc — the corners as ptsin gives them: the source's two and the destination's two, NOT checked
 * against each other — the destination's size is its own, and the height the source's. (Both arms store
 * B_WD as well, the clipped one to test it with `addq.w #1 / ble`; nothing past $a00e reads it, so the
 * C keeps only the test.) */
static void given_corners(uint8_t *image, uint8_t *frame, uint32_t ptsin)
{
    static const unsigned corner_fields[] = { BITBLT_S_XMIN, BITBLT_S_YMIN, BITBLT_S_XMAX, BITBLT_S_YMAX,
                                              BITBLT_D_XMIN, BITBLT_D_YMIN, BITBLT_D_XMAX, BITBLT_D_YMAX };
    unsigned corner;

    for (corner = 0; corner < sizeof corner_fields / sizeof corner_fields[0]; corner++)
        set_frame_word(frame, corner_fields[corner], be16(bus(image, ptsin + corner * VDI_WORD_BYTES)));
    set_frame_word(frame, BITBLT_B_HT, (uint16_t)(frame_word(frame, BITBLT_S_YMAX) - frame_word(frame, BITBLT_S_YMIN) + 1));
}

/* The block's forms, strides and ops out of the two MFDBs and intin — false when the ROM gives up: a
 * destination that is not 1, 2 or 4 planes, a transparent source that is not one plane, an opaque copy
 * between different depths or with an op past 15, a transparent mode past 4. */
static int build_block(uint8_t *image, uint8_t *frame, uint16_t mode)
{
    uint32_t contrl = linea_pointer(image, LINEA_CONTRL);
    struct form source = mfdb_form(image, be32(bus(image, contrl + CONTRL_POINTER_A)));
    struct form destination = mfdb_form(image, be32(bus(image, contrl + CONTRL_POINTER_B)));
    uint16_t source_next_word = (uint16_t)(source.planes * VDI_WORD_BYTES);
    uint16_t destination_next_word = (uint16_t)(destination.planes * VDI_WORD_BYTES);
    uint16_t source_next_plane = VDI_WORD_BYTES;

    if (!(BLIT_PLANE_COUNTS_SET >> (destination.planes & BLIT_BTST_REGISTER_MASK) & 1))
        return 0;
    set_frame_word(frame, BITBLT_PLANE_CT, destination.planes);
    set_frame_word(frame, BITBLT_S_NXWD, source_next_word);
    set_frame_word(frame, BITBLT_D_NXWD, destination_next_word);
    set_frame_word(frame, BITBLT_S_NXLN, source.line_bytes);
    set_frame_word(frame, BITBLT_D_NXLN, destination.line_bytes);
    set_frame_long(frame, BITBLT_S_FORM, source.base);
    set_frame_long(frame, BITBLT_D_FORM, destination.base);
    if (be16(image + LINEA_COPY_TRAN)) {
        uint16_t background, foreground;

        if (source_next_word != VDI_WORD_BYTES)
            return 0;
        source_next_plane = 0;                               /* every plane from the one source plane */
        background = transparent_pen(image, 2);
        foreground = transparent_pen(image, 1);
        if (!transparent_ops(frame, mode, foreground, background))
            return 0;
    } else {
        if (mode >= BLIT_OP_COUNT || destination_next_word != source_next_word)
            return 0;
        set_frame_word(frame, BITBLT_BG_COL, 0);
        set_frame_word(frame, BITBLT_FG_COL, 0);
        *block_field(frame, BITBLT_OP_TAB) = (uint8_t)mode;
    }
    set_frame_word(frame, BITBLT_S_NXPL, source_next_plane);
    set_frame_word(frame, BITBLT_D_NXPL, VDI_WORD_BYTES);
    return 1;
}

/* intin[0]'s bit 4: the pattern at PATPTR, 16 rows of one word, each plane its own 16 when MULTIFILL. */
static void pattern_fields(const uint8_t *image, uint8_t *frame, uint16_t mode)
{
    uint32_t pattern = 0;

    if (mode & 1u << BLIT_PATTERN_MODE_BIT) {
        pattern = be32(image + LINEA_PATPTR);
        set_frame_word(frame, BITBLT_P_NXPL, be16(image + LINEA_MULTIFILL) ? RASTER_MULTIFILL_PLANE_BYTES : 0);
        set_frame_word(frame, BITBLT_P_NXLN, BLIT_PATTERN_ROW_BYTES);
        set_frame_word(frame, BITBLT_P_MASK, BLIT_PATTERN_INDEX_MASK);
    }
    set_frame_long(frame, BITBLT_P_ADDR, pattern);
}

/* $fd0346 — $a00e copy_raster: the MFDBs at contrl[7..10], the rectangles in ptsin (source then
 * destination), intin[0] the op (opaque) or the mode (COPY_TRAN, colours intin[1] and [2]). Clipped only
 * when CLIP is on AND the destination is the screen. contrl[2] and contrl[4] cleared, done or not. */
TRANSCRIBED_CORE
void linea_copy_raster(uint8_t *image)
{
    /* `link a6,#-76`: the ROM's block is whatever the stack held, and so is this one — left so, because
     * no byte the engine stores depends on it: the one field read before it is stored, P_NXLN (negated
     * going backwards with no pattern), is read by nothing after; the OP_TAB entries a mode leaves unset
     * are ones its colours cannot index. (Zeroing it would also make GCC call `memset`, which the
     * freestanding 68000 build does not have.) */
    uint8_t block[BITBLT_BYTES];
    uint8_t *frame = block + BITBLT_BYTES;
    uint16_t mode = (uint16_t)intin_word(image, 0);
    uint32_t ptsin;
    int drawn;

    pattern_fields(image, frame, mode);
    if (build_block(image, frame, (uint16_t)(mode & ~(1u << BLIT_PATTERN_MODE_BIT)))) {
        uint32_t destination_mfdb = be32(bus(image, linea_pointer(image, LINEA_CONTRL) + CONTRL_POINTER_B));

        ptsin = linea_pointer(image, LINEA_PTSIN);
        if (be16(image + LINEA_CLIP) && be32(bus(image, destination_mfdb + MFDB_ADDR)) == 0) {
            drawn = clipped_corners(image, frame, ptsin);
        } else {
            given_corners(image, frame, ptsin);
            drawn = 1;
        }
        if (drawn)
            enter_engine(image, frame);
    }
    answer_points(image, 0);
    answer_words(image, 0);
}

/* ---- the VDI functions ------------------------------------------------------------------------------- */

/* vro_cpyfm / vrt_cpyfm: both of ptsin's rectangles sorted (x ascending, y ascending), then $a00e. */
static void copy_form(uint8_t *image, uint16_t transparent)
{
    vdi_arb_corner(image, linea_pointer(image, LINEA_PTSIN), VDI_CORNERS_Y_ASCENDING);
    vdi_arb_corner(image, linea_pointer(image, LINEA_PTSIN) + CORNERS_BYTES, VDI_CORNERS_Y_ASCENDING);
    wr16(image + LINEA_COPY_TRAN, transparent);
    linea_copy_raster(image);
}

/* $fcb5aa — vro_cpyfm (109): an opaque copy, intin[0] the op. */
void vdi_vro_cpyfm(uint8_t *image)
{
    copy_form(image, 0);
}

/* $fcb5dc — vrt_cpyfm (121): a transparent copy of a one-plane source, intin[0] the mode. */
void vdi_vrt_cpyfm(uint8_t *image)
{
    copy_form(image, WHOLE_WORD);
}

/* $fcb614 — vr_recfl (114): ptsin's rectangle sorted, the workstation's fill colour spread into COLBIT
 * (bit n for plane n, 0/1/2/4/8 as every VDI caller stores it), the corners into X1..Y2 — read and
 * stored one by one — and $a005, which clips it and draws it in the write mode and pattern the
 * dispatcher copied. */
void vdi_vr_recfl(uint8_t *image)
{
    uint16_t colour;
    uint32_t corner;
    unsigned plane, word;

    vdi_arb_corner(image, linea_pointer(image, LINEA_PTSIN), VDI_CORNERS_Y_ASCENDING);
    colour = be16(image + current_work(image) + WS_FILL_COLOR);
    for (plane = 0; plane < COLBIT_PLANES; plane++)
        wr16(image + LINEA_COLBIT0 + plane * VDI_WORD_BYTES, colour & (uint16_t)(1u << plane));
    corner = linea_pointer(image, LINEA_PTSIN);
    for (word = 0; word < CORNERS_BYTES / VDI_WORD_BYTES; word++)
        wr16(image + LINEA_X1 + word * VDI_WORD_BYTES, be16(bus(image, corner + word * VDI_WORD_BYTES)));
    linea_filled_rect(image);
}
