/* raster.c — the Line-A PIXEL and SCANLINE primitives, and the CPU bodies behind drawing vectors 6..8.
 *
 *   $fca1b8 concat          (x, y) -> the group's screen offset, the pixel's bit
 *   $fcface $a001 put_pixel / $fcfb16 $a002 get_pixel
 *   $fca57e $a004 hline, and its two MID-FUNCTION entries $fca58a / $fca5a2 -> vector 8 ($fd1ae0)
 *   $fcfc56 $a005 filled rectangle, clipped                                  -> vector 6 ($fd1b16)
 *   $fca1ea $a003 line: horizontal -> $fca5a2; vertical -> vector 7 ($fd19dc); else a Bresenham here
 *   $fca3f4 line_plane_words, the per-plane code the line bodies run
 *
 * THE ROM IS HAND-WRITTEN 68000 and three of its tricks are the things to read the C against:
 *
 *   * ONE SET OF ARMS DRAWS EVERY SPAN. The hline and rectangle bodies jump into the same four
 *     write-mode arms ($fd1b0e's table), each of which draws one row across every plane: the left word
 *     under its fringe mask, `words - 1` whole middle words, the right word under its own — or the left
 *     word alone, both masks ANDed, when the span is inside one group. `span_row` is those arms.
 *   * THE LINE BODIES EXECUTE CODE THEY BUILD ON THE STACK. `$fca3f4` writes one `and.w d0,(a5)+` or
 *     `or.w d1,(a5)+` per plane — clear or set, by that plane's COLBIT — and a `jmp (a3)`, into a 20-byte
 *     buffer below SP, and every "draw this pixel in the colour" is a `jmp` into it. Here that is a bit
 *     mask of the planes to set (`colour_planes`); the buffer itself is scratch in the band every
 *     differential drops, and `linea_line_plane_words` reconstructs it for its own sake.
 *   * THE LINE STYLE IS A ROTATING WORD. Each pixel spends LN_MASK's top bit (`rol.w #1`), and the
 *     routine stores LN_MASK back rotated by the pixel count BEFORE it draws, so the next segment of a
 *     polyline picks the pattern up where this one left off. A horizontal line hands the UNALIGNED style
 *     word to the span arms as a one-row pattern — its dashes are fixed to the screen's 16-pixel grid,
 *     not to the line's start.
 *
 * The write modes (`raster.h`): REPLACE draws the colour where the pattern/style is 1 and colour 0
 * where it is 0; TRANSPARENT draws the colour where it is 1 and leaves the rest; REVERSE is TRANSPARENT
 * over the inverted pattern; XOR flips every plane where it is 1 and IGNORES the colour. A mode past 3
 * sends the ROM through its jump tables' neighbours into code that is not an arm, so it halts here.
 *
 * NOT REACHED BY ANY STAGED CASE, and written to the ROM's arithmetic regardless: a span whose right
 * group is left of its left one (X1 > X2 across groups — the ROM's word counts then run ~65,536 words
 * past the row, a memory smash), a rectangle with Y2 < Y1 unclipped (~65,536 rows), a plane count of 0
 * anywhere (every plane loop is `subq.w #1` / `dbf`: 65,536 passes — get_pixel reads 128 KB below the
 * pixel) or past 8 in the spans. Past 8 planes elsewhere IS staged: concat's shift, get_pixel's word,
 * and the line bodies' early return.
 */
#include <stdint.h>

#include "machine.h"
#include "recreate.h"
#include "addrs.h"
#include "m68k_idioms.h"
#include "ram_vector.h"
#include "vdi/vdi.h"
#include "vdi/raster.h"
#include "vdi/transcribed.h"

#define PIXEL_IN_GROUP_MASK  15u        /* x & 15: the pixel's column in its 16-pixel group */
#define GROUP_SHIFT          4          /* x >> 4 (`asr.w #4`): its group */
#define LEFTMOST_PIXEL_BIT   0x8000u    /* column 0's bit */
#define WHOLE_WORD           0xffffu    /* a middle word of a span: every pixel */
#define STYLE_PIXEL_BIT      0x8000u    /* the style bit `rol.w #1` spends on the next pixel */
#define PLANE_WORD_BYTES     SCREEN_PLANE_WORD_BYTES
#define POINT_Y              2          /* ptsin[1]: a point's y, a word after its x */

enum { CONCAT_D0, CONCAT_D1 };          /* the order `test_vdi_raster_pixel.py` declares concat's answer in */

/* What one plane word of a span becomes, by write mode and that plane's colour bit. */
enum plane_op { OP_CLEAR, OP_REPLACE, OP_SET, OP_RESET, OP_TOGGLE };

static inline uint32_t screen_base(const uint8_t *image)
{
    return be32(image + SYSVAR_V_BAS_AD);
}

static inline uint16_t fringe_mask(const uint8_t *image, unsigned index)
{
    return be16(image + RASTER_FRINGE_MASK_TABLE + index * RASTER_FRINGE_MASK_ENTRY_BYTES);
}

/* `exg`: the line is drawn from its left end. */
static inline void swap_words(int16_t *left, int16_t *right)
{
    int16_t held = *left;

    *left = *right;
    *right = held;
}

/* A plane loop is `subq.w #1` then `dbf`: N planes make N passes, and 0 makes 65,536. */
static inline int more_planes(uint16_t *planes_left)
{
    return --*planes_left != 0;
}

/* $fca1b8 — concat, for C callers: y * BYTES_LIN, plus the x's group scaled from 16 pixels to its bytes
 * by the ROM's shift table — which is why only 1, 2, 4 and 8 planes come out right. Past 8 planes the
 * index runs into the code after the table, and `asr.w` takes that byte modulo 64: 13 or 18 planes
 * shift by 16 or more, leaving only x's sign. The ROM's `ext.l` / `asr.w` / `add.l` is spelt as an
 * `asr.l` of the sign-extended word, which leaves the same long for every count — and costs what the
 * ROM's shift does on target, where a word shift would cost GCC a register. */
int32_t concat_offset(const uint8_t *image, uint16_t x, uint16_t y)
{
    uint16_t shift = image[RASTER_CONCAT_SHIFT_TABLE + ram_word(image, LINEA_PLANES)];
    int32_t group_bytes = asr_long_by((int16_t)(x & ~PIXEL_IN_GROUP_MASK), shift);

    return m68k_muls_w(y, be16(image + LINEA_BYTES_LIN)) + group_bytes;
}

/* $fca1b8 — concat as a primitive: D1 = the offset, D0's low word = x & 15 (its high word untouched).
 * It also leaves D2's HIGH word holding x's sign (`ext.l d2` before a word-sized restore), which no
 * caller reads and this contract does not declare. */
TRANSCRIBED_CORE
uint32_t linea_concat(uint8_t *image, uint32_t x_register, uint32_t y_register, uint32_t *results)
{
    results[CONCAT_D0] = (x_register & ~(uint32_t)WHOLE_WORD) | (x_register & PIXEL_IN_GROUP_MASK);
    results[CONCAT_D1] = (uint32_t)concat_offset(image, (uint16_t)x_register, (uint16_t)y_register);
    return results[CONCAT_D0];
}

/* The screen word holding plane 0 of (x, y), and the pixel's bit in it — $a001/$a002's opening. */
static inline uint8_t *pixel_group(uint8_t *image, uint16_t x, uint16_t y, uint16_t *bit)
{
    *bit = (uint16_t)(LEFTMOST_PIXEL_BIT >> (x & PIXEL_IN_GROUP_MASK));
    return image + screen_base(image) + concat_offset(image, x, y);
}

/* The point ptsin[0] names. */
static inline const uint8_t *first_point(const uint8_t *image)
{
    return image + be32(image + LINEA_PTSIN);
}

/* $fcface — $a001 put_pixel: intin[0]'s bits, plane 0 first, into ptsin[0]'s pixel. No clipping. */
TRANSCRIBED_CORE
void linea_put_pixel(uint8_t *image)
{
    const uint8_t *point = first_point(image);
    uint16_t bit;
    uint8_t *word = pixel_group(image, be16(point), be16(point + POINT_Y), &bit);
    uint16_t colour = be16(image + be32(image + LINEA_INTIN));
    uint16_t planes = be16(image + LINEA_PLANES);

    do {
        uint16_t pixels = be16(word);

        wr16(word, (colour & 1) ? pixels | bit : pixels & (uint16_t)~bit);
        colour = rotate_right16(colour, 1);
        word += PLANE_WORD_BYTES;
    } while (more_planes(&planes));
}

/* $fcfb16 — $a002 get_pixel: ptsin[0]'s colour index in D0, read from the LAST plane down. `addx.w`
 * builds it in a WORD, so past 16 planes the planes read first are shifted out of it. */
TRANSCRIBED_CORE
uint32_t linea_get_pixel(uint8_t *image)
{
    const uint8_t *point = first_point(image);
    uint16_t bit;
    const uint8_t *group = pixel_group(image, be16(point), be16(point + POINT_Y), &bit);
    uint16_t planes = be16(image + LINEA_PLANES);
    const uint8_t *word = group + (int16_t)(planes * PLANE_WORD_BYTES);
    uint16_t colour = 0;

    do {
        word -= PLANE_WORD_BYTES;
        colour = (colour << 1) | ((be16(word) & bit) != 0);
    } while (more_planes(&planes));
    return colour;
}

/* ---- the span arms ($fd1bae..$fd1cc3), shared by the hline and rectangle bodies ----------------- */

/* One row of a span, as the arms' registers hold it. */
struct span {
    uint8_t *first;             /* A1: plane 0 of the left word */
    const uint8_t *pattern;     /* A0: this row's pattern word, plane 0 */
    int16_t pattern_stride;     /* A2: 0, or a multi-plane pattern's plane size */
    uint16_t left_mask;         /* D4 */
    uint16_t right_mask;        /* D6 */
    uint16_t words;             /* D2: groups past the left one — 0 is the left word alone */
    uint16_t group_bytes;       /* D0: PLANES words, the distance to the next group's same plane */
    uint16_t planes;
};

static inline uint16_t plane_op(uint16_t pixels, uint16_t mask, uint16_t pattern, enum plane_op op)
{
    switch (op) {
    case OP_CLEAR:   return pixels & (uint16_t)~mask;
    case OP_REPLACE: return (pixels & (uint16_t)~mask) | (pattern & mask);
    case OP_SET:     return pixels | (pattern & mask);
    case OP_RESET:   return pixels & (uint16_t)~(pattern & mask);
    default:         return pixels ^ (pattern & mask);      /* OP_TOGGLE */
    }
}

static inline void apply_word(uint8_t *word, uint16_t mask, uint16_t pattern, enum plane_op op)
{
    wr16(word, plane_op(be16(word), mask, pattern, op));
}

/* One plane of the row: the left word, then — `subq.w #1,d5 / bcs` twice before a `dbf d5` — the
 * middle words and the right one. The span's fields come in as values: read through the struct, every
 * store to the screen (a `uint8_t *`) would make the compiler read them again. */
static inline __attribute__((always_inline))
void plane_run(uint8_t *word, uint16_t left_mask, uint16_t right_mask, uint16_t words, uint16_t group_bytes,
               uint16_t pattern, enum plane_op op)
{
    uint16_t middle;

    apply_word(word, left_mask, pattern, op);
    if (words == 0)
        return;
    for (middle = (uint16_t)(words - 1); middle != 0; middle--) {
        word += group_bytes;
        apply_word(word, WHOLE_WORD, pattern, op);
    }
    word += group_bytes;
    apply_word(word, right_mask, pattern, op);
}

/* Every plane of the row, the op by that plane's COLBIT; `invert` is REVERSE's `not.w d3`. */
static inline __attribute__((always_inline))
void span_planes(const uint8_t *image, const struct span *span, uint16_t invert,
                 enum plane_op if_clear, enum plane_op if_set)
{
    uint8_t *word = span->first;
    const uint8_t *pattern = span->pattern;
    const uint8_t *colour = image + LINEA_COLBIT0;
    int16_t pattern_stride = span->pattern_stride;
    uint16_t left_mask = span->left_mask, right_mask = span->right_mask;
    uint16_t words = span->words, group_bytes = span->group_bytes;
    uint16_t planes = span->planes;

    do {
        uint16_t pattern_word = be16(pattern) ^ invert;

        if (be16(colour))
            plane_run(word, left_mask, right_mask, words, group_bytes, pattern_word, if_set);
        else
            plane_run(word, left_mask, right_mask, words, group_bytes, pattern_word, if_clear);
        pattern += pattern_stride;
        colour += PLANE_WORD_BYTES;
        word += PLANE_WORD_BYTES;
    } while (more_planes(&planes));
}

/* The four arms, by WRT_MODE. XOR's never reads COLBIT, so it is one op whatever the colour. */
static void span_row(const uint8_t *image, const struct span *span, uint16_t write_mode)
{
    switch (write_mode) {
    case RASTER_MODE_REPLACE:
        span_planes(image, span, 0, OP_CLEAR, OP_REPLACE);
        break;
    case RASTER_MODE_TRANSPARENT:
        span_planes(image, span, 0, OP_RESET, OP_SET);
        break;
    case RASTER_MODE_XOR:
        span_planes(image, span, 0, OP_TOGGLE, OP_TOGGLE);
        break;
    case RASTER_MODE_REVERSE:
        span_planes(image, span, WHOLE_WORD, OP_RESET, OP_SET);
        break;
    default:
        recreate_not_reconstructed("span arms: a write mode past 3 jumps past $fd1b0e's four arms");
    }
}

/* The left group, the groups past it and the two fringe masks of x1..x2 — `$fca5a2` and `$fcfc9c`
 * alike: in one group the right mask is folded into the left. */
struct fringes {
    uint16_t left_group;
    uint16_t words;
    uint16_t left_mask;
    uint16_t right_mask;
};

static inline struct fringes span_fringes(const uint8_t *image, uint16_t x1, uint16_t x2)
{
    struct fringes fringes;

    fringes.left_group = (uint16_t)((int16_t)x1 >> GROUP_SHIFT);
    fringes.words = (uint16_t)(((int16_t)x2 >> GROUP_SHIFT) - (int16_t)fringes.left_group);
    fringes.left_mask = fringe_mask(image, x1 & PIXEL_IN_GROUP_MASK);
    fringes.right_mask = (uint16_t)~fringe_mask(image, (x2 & PIXEL_IN_GROUP_MASK) + 1);
    if (fringes.words == 0)
        fringes.left_mask &= fringes.right_mask;
    return fringes;
}

/* ---- $a004 and the hline body ---------------------------------------------------------------------- */

/* $fd1ae0 — vector 8's CPU body: one row at y from the left group, the pattern word at `pattern`
 * (the next plane's `pattern_stride` bytes on). D0 = stride, D1 = left group, D2 = words past it,
 * D4/D6 = the fringe masks, D5 = y, A0 = pattern. The front ends reach it through `cpu_hline`, inlined;
 * `linea_cpu_hline` is the same body as a primitive of its own. */
static inline void cpu_hline(uint8_t *image, int16_t pattern_stride, uint16_t left_group, uint16_t words,
                             uint16_t left_mask, uint16_t y, uint16_t right_mask, uint32_t pattern)
{
    struct span span;

    span.planes = be16(image + LINEA_PLANES);
    span.group_bytes = (uint16_t)(span.planes * PLANE_WORD_BYTES);
    span.first = image + screen_base(image) + m68k_muls_w(y, be16(image + LINEA_BYTES_LIN))
                 + m68k_muls_w(left_group, span.group_bytes);
    span.pattern = image + pattern;
    span.pattern_stride = pattern_stride;
    span.left_mask = left_mask;
    span.right_mask = right_mask;
    span.words = words;
    span_row(image, &span, be16(image + LINEA_WRT_MODE));
}

TRANSCRIBED_CORE
void linea_cpu_hline(uint8_t *image, uint32_t pattern_stride, uint32_t left_group, uint32_t words,
                     uint32_t left_mask, uint32_t y, uint32_t right_mask, uint32_t pattern)
{
    cpu_hline(image, (int16_t)pattern_stride, (uint16_t)left_group, (uint16_t)words, (uint16_t)left_mask,
              (uint16_t)y, (uint16_t)right_mask, pattern);
}

/* $fca5a2 — $a004 past its pattern: x1 (D4) .. x2 (D6) on row y (D5) through the pattern word at A0,
 * stride D0. $a003's horizontal arm enters here with its style word as the pattern. */
static inline void hline_span(uint8_t *image, uint16_t x1, uint16_t y, uint16_t x2, uint32_t pattern,
                              int16_t pattern_stride)
{
    struct fringes fringes = span_fringes(image, x1, x2);

    require_cpu_routine(image, LINEA_VECTOR_HLINE, LINEA_ROM_CPU_HLINE, "$a004: the hline vector");
    cpu_hline(image, pattern_stride, fringes.left_group, fringes.words, fringes.left_mask, y,
              fringes.right_mask, pattern);
}

TRANSCRIBED_CORE
void linea_hline_span(uint8_t *image, uint32_t x1, uint32_t y, uint32_t x2, uint32_t pattern,
                      uint32_t pattern_stride)
{
    hline_span(image, (uint16_t)x1, (uint16_t)y, (uint16_t)x2, pattern, (int16_t)pattern_stride);
}

/* $fca58a — $a004 past its coordinate load: the pattern row y & PATMSK, and a multi-plane pattern's
 * stride. The contour fill enters here with its own x1 (D4), y (D5), x2 (D6). */
static inline void hline_patterned(uint8_t *image, uint16_t x1, uint16_t y, uint16_t x2)
{
    uint16_t row_bytes = (uint16_t)((y & be16(image + LINEA_PATMSK)) * PLANE_WORD_BYTES);
    uint32_t pattern = be32(image + LINEA_PATPTR) + sign_ext16(row_bytes);
    int16_t stride = be16(image + LINEA_MULTIFILL) ? RASTER_MULTIFILL_PLANE_BYTES : 0;

    hline_span(image, x1, y, x2, pattern, stride);
}

TRANSCRIBED_CORE
void linea_hline_patterned(uint8_t *image, uint32_t x1, uint32_t y, uint32_t x2)
{
    hline_patterned(image, (uint16_t)x1, (uint16_t)y, (uint16_t)x2);
}

/* $fca57e — $a004 hline: X1..X2 on row Y1 in the fill pattern, unclipped. */
TRANSCRIBED_CORE
void linea_hline(uint8_t *image)
{
    hline_patterned(image, be16(image + LINEA_X1), be16(image + LINEA_Y1), be16(image + LINEA_X2));
}

/* ---- $a005 and the rectangle body -------------------------------------------------------------------- */

/* $fd1b16 — vector 6's CPU body: rows y1 (D5) .. y2 (D7) of the span D0/D1/D4/D6 ($fd1ae0's
 * registers), the pattern row stepping by one and wrapping PAST PATMSK — a compare, not a mask, so a
 * PATMSK that is not 2^n - 1 cycles through PATMSK + 1 rows. Each row after the first is WIDTH bytes on,
 * where the first was placed by BYTES_LIN. */
static inline void cpu_rect_fill(uint8_t *image, uint16_t left_group, uint16_t words, uint16_t left_mask,
                                 uint16_t y1, uint16_t right_mask, uint16_t y2)
{
    struct span span;
    uint16_t write_mode = be16(image + LINEA_WRT_MODE);
    uint16_t rows_left = (uint16_t)(y2 - y1);
    uint16_t pattern_mask = be16(image + LINEA_PATMSK);
    int16_t pattern_last = (int16_t)(pattern_mask * PLANE_WORD_BYTES);
    uint16_t pattern_row = (uint16_t)((y1 & pattern_mask) * PLANE_WORD_BYTES);
    const uint8_t *patterns = image + be32(image + LINEA_PATPTR);
    uint8_t *row;
    int32_t row_step;

    span.planes = be16(image + LINEA_PLANES);
    span.group_bytes = (uint16_t)(span.planes * PLANE_WORD_BYTES);
    /* the arms step A1 past the planes, and the frame's `WIDTH - planes * 2` takes it to the next row */
    row_step = span.group_bytes + (int16_t)(be16(image + LINEA_WIDTH) - span.group_bytes);
    row = image + screen_base(image) + m68k_muls_w(y1, be16(image + LINEA_BYTES_LIN))
          + 2 * m68k_muls_w(left_group, span.planes);
    span.pattern_stride = be16(image + LINEA_MULTIFILL) ? RASTER_MULTIFILL_PLANE_BYTES : 0;
    span.left_mask = left_mask;
    span.right_mask = right_mask;
    span.words = words;
    for (;;) {
        span.first = row;
        span.pattern = patterns + (int16_t)pattern_row;
        span_row(image, &span, write_mode);
        if (rows_left-- == 0)
            return;
        pattern_row += PLANE_WORD_BYTES;
        if ((int16_t)pattern_row > pattern_last)
            pattern_row = 0;
        row += row_step;
    }
}

TRANSCRIBED_CORE
void linea_cpu_rect_fill(uint8_t *image, uint32_t left_group, uint32_t words, uint32_t left_mask,
                         uint32_t y1, uint32_t right_mask, uint32_t y2)
{
    cpu_rect_fill(image, (uint16_t)left_group, (uint16_t)words, (uint16_t)left_mask, (uint16_t)y1,
                  (uint16_t)right_mask, (uint16_t)y2);
}

/* One axis of `$fcfc56`'s clip: 0 when low..high misses min..max. The low end is clipped first, and
 * the high end is then tested against the CLIPPED low. */
static int clip_axis(int16_t *low, int16_t *high, int16_t min, int16_t max)
{
    if (*low < min) {
        if (*high < min)
            return 0;
        *low = min;
    }
    if (*high > max) {
        if (*low > max)
            return 0;
        *high = max;
    }
    return 1;
}

/* $fcfc56 — $a005 filled rectangle X1,Y1 .. X2,Y2 in the fill pattern. With CLIP on, the corners are
 * clipped and STORED BACK — on a miss too ($fcfc50), as far as the clip had got. */
TRANSCRIBED_CORE
void linea_filled_rect(uint8_t *image)
{
    int16_t x1 = ram_word(image, LINEA_X1), y1 = ram_word(image, LINEA_Y1);
    int16_t x2 = ram_word(image, LINEA_X2), y2 = ram_word(image, LINEA_Y2);
    struct fringes fringes;

    if (be16(image + LINEA_CLIP)) {
        int visible = clip_axis(&x1, &x2, ram_word(image, LINEA_XMINCL), ram_word(image, LINEA_XMAXCL))
                      && clip_axis(&y1, &y2, ram_word(image, LINEA_YMINCL), ram_word(image, LINEA_YMAXCL));

        wr16(image + LINEA_X1, (uint16_t)x1);
        wr16(image + LINEA_Y1, (uint16_t)y1);
        wr16(image + LINEA_X2, (uint16_t)x2);
        wr16(image + LINEA_Y2, (uint16_t)y2);
        if (!visible)
            return;
    }
    fringes = span_fringes(image, (uint16_t)x1, (uint16_t)x2);
    require_cpu_routine(image, LINEA_VECTOR_RECT_FILL, LINEA_ROM_CPU_RECT_FILL, "$a005: the rectangle vector");
    cpu_rect_fill(image, fringes.left_group, fringes.words, fringes.left_mask, (uint16_t)y1,
                  fringes.right_mask, (uint16_t)y2);
}

/* ---- $a003: the line bodies ------------------------------------------------------------------------ */

/* Bit p set: plane p's COLBIT is nonzero, so "draw the colour" SETS that plane's bit — the choice
 * `$fca3f4` bakes into its per-plane opcode words. */
static inline uint16_t colour_planes(const uint8_t *image, uint16_t planes)
{
    uint16_t set = 0;
    uint16_t plane;

    for (plane = 0; plane < planes; plane++)
        if (be16(image + LINEA_COLBIT0 + plane * PLANE_WORD_BYTES))
            set |= (uint16_t)(1u << plane);
    return set;
}

/* $fca3f4 — line_plane_words: D3 (PLANES) opcode words into the buffer at A2, each plane's clear or set
 * by its COLBIT, and the `jmp (a3)` that ends the run. */
TRANSCRIBED_CORE
void linea_line_plane_words(uint8_t *image, uint32_t planes, uint32_t buffer)
{
    uint8_t *word = image + buffer;
    const uint8_t *colour = image + LINEA_COLBIT0;
    uint16_t planes_left = (uint16_t)planes;

    do {
        unsigned opcode = be16(colour) ? RASTER_PLANE_OPCODE_SET : RASTER_PLANE_OPCODE_CLEAR;

        wr16(word, be16(image + RASTER_PLANE_OPCODES + opcode));
        word += PLANE_WORD_BYTES;
        colour += PLANE_WORD_BYTES;
    } while (more_planes(&planes_left));
    wr16(word, be16(image + RASTER_PLANE_OPCODES + RASTER_PLANE_OPCODE_END));
}

/* The pen a line body draws with: where it is, the style word it spends, and what a pixel does. */
struct pen {
    uint8_t *group;             /* plane 0 of the pixel's group */
    uint16_t bit;
    uint16_t style;             /* D2: the next pixel's style bit on top */
    uint16_t planes;
    uint16_t colour;            /* `colour_planes` */
    uint16_t write_mode;
};

static inline void paint_pixel(uint8_t *word, uint16_t bit, uint16_t planes, uint16_t set)
{
    do {
        uint16_t pixels = be16(word);

        wr16(word, (set & 1) ? pixels | bit : pixels & (uint16_t)~bit);
        set >>= 1;
        word += PLANE_WORD_BYTES;
    } while (more_planes(&planes));
}

static inline void toggle_pixel(uint8_t *word, uint16_t bit, uint16_t planes)
{
    do {
        wr16(word, be16(word) ^ bit);
        word += PLANE_WORD_BYTES;
    } while (more_planes(&planes));
}

/* One pixel: the style bit spent, then — REPLACE — the colour or colour 0; TRANSPARENT and REVERSE
 * (whose style was inverted once, `not.w d2`) the colour or nothing; XOR every plane or nothing. */
static inline void pen_pixel(struct pen *pen)
{
    int on = (pen->style & STYLE_PIXEL_BIT) != 0;

    pen->style = rotate_left16(pen->style, 1);
    if (pen->write_mode == RASTER_MODE_XOR) {
        if (on)
            toggle_pixel(pen->group, pen->bit, pen->planes);
    } else if (on) {
        paint_pixel(pen->group, pen->bit, pen->planes, pen->colour);
    } else if (pen->write_mode == RASTER_MODE_REPLACE) {
        paint_pixel(pen->group, pen->bit, pen->planes, 0);
    }
}

/* The x step: the bit moves right, and past column 15 (`ror.w` carries it round) into the next group. */
static inline void pen_step_right(struct pen *pen, uint16_t group_bytes)
{
    pen->bit = rotate_right16(pen->bit, 1);
    if (pen->bit == LEFTMOST_PIXEL_BIT)
        pen->group += group_bytes;
}

/* What both line bodies do before the first pixel: refuse a mode past 3, drop XOR's last pixel unless
 * LSTLIN says this is the polyline's last segment, and store LN_MASK rotated past this line's pixels.
 * Answers the `dbf` count — one less than the pixels. */
static inline uint16_t pen_start(uint8_t *image, struct pen *pen, uint16_t count)
{
    uint16_t style = be16(image + LINEA_LN_MASK);

    pen->write_mode = be16(image + LINEA_WRT_MODE);
    if (pen->write_mode > RASTER_MODE_REVERSE)
        recreate_not_reconstructed("$a003: a write mode past 3 jumps past the line bodies' tables");
    if (pen->write_mode == RASTER_MODE_XOR && be16(image + LINEA_LSTLIN) == 0)
        count--;
    wr16(image + LINEA_LN_MASK, rotate_left16(style, (uint16_t)(count + 1)));
    pen->style = pen->write_mode == RASTER_MODE_REVERSE ? (uint16_t)~style : style;
    return count;
}

static inline void pen_colour(const uint8_t *image, struct pen *pen, uint16_t planes, uint16_t x)
{
    pen->planes = planes;
    pen->colour = colour_planes(image, planes);
    pen->bit = (uint16_t)(LEFTMOST_PIXEL_BIT >> (x & PIXEL_IN_GROUP_MASK));
}

/* $fd19dc — vector 7's CPU body: the vertical line x1 (D4), y1 (D5) .. y2 (D7); D6 = x2 = x1 places
 * the group. Entered with D0 = 2 (see `raster.h`). Each row is WIDTH bytes from the last, where the
 * first was placed by BYTES_LIN. */
TRANSCRIBED_CORE
void linea_cpu_vline(uint8_t *image, uint32_t x1, uint32_t y1, uint32_t x2, uint32_t y2)
{
    uint16_t planes = be16(image + LINEA_PLANES);
    uint16_t group_bytes = (uint16_t)(planes * PLANE_WORD_BYTES);
    int16_t step = ram_word(image, LINEA_WIDTH);
    uint16_t count = (uint16_t)(y2 - y1);
    struct pen pen;

    if (planes > RASTER_LINE_PLANES_MAX)
        return;
    if ((int16_t)y2 < (int16_t)y1) {
        step = (int16_t)-step;
        count = (uint16_t)-count;
    }
    pen_colour(image, &pen, planes, (uint16_t)x1);
    pen.group = image + screen_base(image) + m68k_muls_w((uint16_t)((int16_t)x2 >> GROUP_SHIFT), group_bytes)
                + m68k_muls_w(be16(image + LINEA_BYTES_LIN), (uint16_t)y1);
    count = pen_start(image, &pen, count);
    do {
        pen_pixel(&pen);
        pen.group += step;
    } while (count-- != 0);
}

/* $fca320 — $a003's DIAGONAL arm: a Bresenham from the left end, along the major axis. Y-major steps y
 * every pixel and x when the error is not negative; x-major steps x every pixel and y when it is not.
 * A slope of exactly 1 is x-major. */
static void line_diagonal(uint8_t *image, int16_t x1, int16_t y1, int16_t x2, int16_t y2)
{
    uint16_t planes = be16(image + LINEA_PLANES);
    uint16_t group_bytes = (uint16_t)(planes * PLANE_WORD_BYTES);
    int16_t step_y = ram_word(image, LINEA_WIDTH);
    int16_t dx, dy, major, minor, error, error_straight, error_diagonal;
    int y_major;
    uint16_t count;
    struct pen pen;

    if (planes > RASTER_LINE_PLANES_MAX)
        return;
    if (x2 < x1) {
        swap_words(&x1, &x2);
        swap_words(&y1, &y2);
    }
    dx = (int16_t)(x2 - x1);
    dy = (int16_t)(y2 - y1);
    if (y2 < y1) {
        dy = (int16_t)-dy;
        step_y = (int16_t)-step_y;
    }
    pen_colour(image, &pen, planes, (uint16_t)x1);
    pen.group = image + screen_base(image) + m68k_muls_w(be16(image + LINEA_BYTES_LIN), (uint16_t)y1)
                + m68k_muls_w((uint16_t)(x1 >> GROUP_SHIFT), group_bytes);
    y_major = dy > dx;
    major = y_major ? dy : dx;
    minor = y_major ? dx : dy;
    error_straight = (int16_t)(2 * minor);
    error = (int16_t)(error_straight - major);
    error_diagonal = (int16_t)(error - major);
    count = pen_start(image, &pen, (uint16_t)major);
    do {
        int diagonal = error >= 0;

        pen_pixel(&pen);
        error = (int16_t)(error + (diagonal ? error_diagonal : error_straight));
        if (y_major || diagonal)
            pen.group += step_y;
        if (!y_major || diagonal)
            pen_step_right(&pen, group_bytes);
    } while (count-- != 0);
}

/* $fca2e0 — $a003's HORIZONTAL arm: XOR drops the last pixel (unless LSTLIN) by moving X2 one toward X1
 * and STORING it; then the span through `$fca5a2` with LN_MASK itself as a one-row pattern, and LN_MASK
 * rotated by the pixel count afterwards. */
static void line_horizontal(uint8_t *image, int16_t x1, int16_t y, int16_t x2)
{
    uint16_t length;

    if (be16(image + LINEA_WRT_MODE) == RASTER_MODE_XOR && be16(image + LINEA_LSTLIN) == 0 && x1 != x2) {
        x2 = (int16_t)(x2 > x1 ? x2 - 1 : x2 + 1);
        wr16(image + LINEA_X2, (uint16_t)x2);
    }
    if (x2 < x1)
        swap_words(&x1, &x2);
    length = (uint16_t)(x2 - x1 + 1);
    hline_span(image, (uint16_t)x1, (uint16_t)y, (uint16_t)x2, LINEA_LN_MASK, 0);
    wr16(image + LINEA_LN_MASK, rotate_left16(be16(image + LINEA_LN_MASK), length));
}

/* $fca1ea — $a003 line X1,Y1 .. X2,Y2 in LN_MASK's style, unclipped. */
TRANSCRIBED_CORE
void linea_line(uint8_t *image)
{
    int16_t x1 = ram_word(image, LINEA_X1), y1 = ram_word(image, LINEA_Y1);
    int16_t x2 = ram_word(image, LINEA_X2), y2 = ram_word(image, LINEA_Y2);

    if (y1 == y2) {
        line_horizontal(image, x1, y1, x2);
        return;
    }
    if (x1 == x2) {
        require_cpu_routine(image, LINEA_VECTOR_VLINE, LINEA_ROM_CPU_VLINE, "$a003: the vertical line vector");
        linea_cpu_vline(image, (uint16_t)x1, (uint16_t)y1, (uint16_t)x2, (uint16_t)y2);
        return;
    }
    line_diagonal(image, x1, y1, x2, y2);
}
