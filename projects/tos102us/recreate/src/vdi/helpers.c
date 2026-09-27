/* helpers.c — the VDI's PURE HELPERS: arithmetic, clipping and scaling leaves, small copies, and
 * `vr_trnfm` (`vdi/helpers.h` says how each is called).
 *
 * Most of them are hand 68000 in the ROM (`vec_len`, `sort_words`, `smul_div`, `clc_dda`, `act_siz`,
 * `clamp_mouse`, `font_byteswap`, `get_kbshift`, `gemdos_call`, `vr_trnfm`); the rest are Alcyon C.
 * Either way they are ported to C here — which is what Tier 1 proves — instruction for instruction where
 * the WIDTH of an operation decides the answer: a word that wraps, a compare that is signed, a divide
 * that overflows and leaves its register alone. The hand ones whose C measures over the Tier 3 bar also
 * ship as the ROM's own instructions, `helpers.S`, whose header says which and why.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "addrs.h"
#include "host_slot.h"
#include "gemdos/gemdos.h"
#include "vdi/vdi.h"
#include "vdi/font.h"
#include "vdi/helpers.h"

#define WORD_BYTES 2

/* ================================================================================================
 * The arithmetic.
 * ============================================================================================= */

/* $fc9ffc — the length of (dx, dy): the integer square root of dx^2 + dy^2 by BISECTION between the
 * powers of two either side of it. The sum is an unsigned longword (two `muls.w` squares, `add.l`); its
 * top bit's position halved gives the root's low bound, and twice that the high — which is $10000 for
 * a sum of 2^30 or more and so `subq.w #1` makes it $ffff. The search stops on an exact square or when
 * the bounds are adjacent, answering the LOW one: the root rounded down.
 *
 * It clobbers D3 and D4, and D4 is an Alcyon caller's register variable: harmless only because every
 * chain that reaches it — v_pline and wline, through arrow ($fcd0fa) and do_arrow ($fcd196) — holds
 * nothing in either across the call. The host cannot see a register, so that is recorded, not reproduced. */
#define VEC_LEN_HIGH_HALF 0x10000u      /* ($fca010 cmp.l #65536): the log search starts in the high word */

int16_t vdi_vec_len(int16_t dx, int16_t dy)
{
    uint32_t square = (uint32_t)((int32_t)dx * dx) + (uint32_t)((int32_t)dy * dy);
    uint16_t top, exponent, low, high;

    if (square == 0)
        return 0;
    top = (uint16_t)square;
    exponent = 0;
    if (square >= VEC_LEN_HIGH_HALF) {
        top = (uint16_t)(square >> M68K_WORD_BITS);
        exponent = M68K_WORD_BITS;
    }
    while (top != 1) {
        exponent++;
        top >>= 1;
    }
    low = asl_word_by(1, (uint16_t)((int16_t)exponent >> 1));
    high = (uint16_t)(low + low);
    if (high == 0)
        high--;
    for (;;) {
        uint16_t gap = (uint16_t)(high - low);
        uint16_t middle;
        uint32_t middle_square;

        if (gap == 1)
            return (int16_t)low;
        middle = (uint16_t)((int16_t)gap >> 1) + low;
        middle_square = (uint32_t)middle * middle;
        if (middle_square > square)
            high = middle;
        else if (middle_square < square)
            low = middle;
        else
            return (int16_t)middle;
    }
}

/* $fca164 — a bubble sort of `count` signed words at `array`, in place: `count - 1` passes over the
 * WHOLE array, each swapping every adjacent pair out of order (`cmp.w (a0),d2 / ble`, so equal words
 * stay). Fewer than two words is no pass at all — the `subq.w #2` borrows. $a006 sorts its scanline's
 * crossings with it. */
#define SORT_MINIMUM_WORDS 2

void vdi_sort_words(uint8_t *image, uint32_t count, uint32_t array)
{
    uint16_t last_pair = (uint16_t)((uint16_t)count - SORT_MINIMUM_WORDS);   /* both `dbf` counts */
    uint16_t pass = last_pair;

    if ((uint16_t)count < SORT_MINIMUM_WORDS)
        return;
    do {
        uint8_t *at = image + array;
        uint16_t pair = last_pair;

        do {
            int16_t left = (int16_t)be16(at);

            at += WORD_BYTES;
            CURSOR_BARRIER(at);
            if (left > (int16_t)be16(at)) {
                wr16(at - WORD_BYTES, be16(at));
                wr16(at, (uint16_t)left);
            }
        } while (pair-- != 0);
    } while (pass-- != 0);
}

/* $fca186 — `multiplicand * multiplier / divisor`, rounded: the 32-bit `muls.w` product through ONE
 * `divs.w`, then the quotient moved one step away from zero — in the direction the product and the
 * divisor's signs agree on — when twice the remainder reaches the divisor.
 *
 * TWO THINGS THE ROM DOES THAT "ROUND HALF AWAY FROM ZERO" DOES NOT, both kept:
 *   * it reads the remainder as the high word of the NEGATED whole register (`neg.l`), which for a
 *     negative remainder over a nonzero quotient word is |remainder| - 1 — so a negative product rounds
 *     a half DOWN where a positive one rounds it up;
 *   * a quotient too big for a word leaves `divs.w`'s register unchanged, so the "quotient" is then the
 *     product's low word and the "remainder" its high word.
 * A divisor of 0 takes vector 5 (`vdi/helpers.h`'s divide). */
int16_t vdi_smul_div(int16_t multiplicand, int16_t multiplier, int16_t divisor)
{
    int32_t product = (int32_t)multiplicand * multiplier;
    int16_t direction = product < 0 ? -1 : 1;
    uint32_t divided = m68k_divs_w((uint32_t)product, (uint16_t)divisor);
    uint16_t bound = (uint16_t)divisor;
    uint32_t magnitude = (int32_t)divided < 0 ? (uint32_t)-divided : divided;
    uint16_t twice_remainder;

    if (divisor < 0) {
        direction = (int16_t)-direction;
        bound = (uint16_t)-bound;
    }
    twice_remainder = (uint16_t)((magnitude >> M68K_WORD_BITS) * 2);
    if ((int16_t)twice_remainder >= (int16_t)bound)
        return (int16_t)(uint16_t)((uint16_t)divided + (uint16_t)direction);
    return (int16_t)(uint16_t)divided;
}

/* ================================================================================================
 * The sine table.
 * ============================================================================================= */

/* $fcab68 — sin(angle) x 32767, the angle in TENTHS OF A DEGREE: folded into the first quadrant by the
 * five-arm switch at `VDI_ISIN_SWITCH` (quadrant = angle / 900), looked up at whole degrees in
 * `VDI_SINE_TABLE` (91 steps and a repeated last entry), interpolated linearly across the tenths, and
 * negated for the lower half. An angle over 3600 is first brought down by whole turns.
 *
 * A NEGATIVE angle is not folded: its quotient misses every arm (`cmp.w #4 / bhi` is unsigned) and its
 * NEGATIVE whole-degree index reads the ROM BELOW the table — kept, since nothing refuses it. */
#define TENTHS_PER_QUARTER    900
#define TENTHS_PER_HALF       1800
#define TENTHS_PER_TURN       3600
#define TENTHS_PER_DEGREE     10
#define LOWER_HALF_FIRST_QUADRANT 2     /* quadrants past 1 are negated ($fcac32 cmpi.w #1 / ble) */

enum { QUADRANT_FIRST, QUADRANT_SECOND, QUADRANT_THIRD, QUADRANT_FOURTH, QUADRANT_FULL_TURN };

/* `movea.w` then `adda.l`: the index is sign-extended BEFORE it is doubled, and the next entry's `+ 1`
 * is an address-register add — so neither wraps as a word. */
static int16_t sine_entry(const uint8_t *image, int32_t degree)
{
    return (int16_t)be16(image + (uint32_t)(VDI_SINE_TABLE + degree * WORD_BYTES));
}

int16_t vdi_isin(const uint8_t *image, int16_t angle)
{
    int16_t quadrant, degree, tenths, sine;
    uint32_t divided;

    while (angle > TENTHS_PER_TURN)
        angle = (int16_t)(angle - TENTHS_PER_TURN);
    quadrant = quotient_word(m68k_divs_w((uint32_t)(int32_t)angle, TENTHS_PER_QUARTER));
    switch (quadrant) {
    case QUADRANT_SECOND:
        angle = (int16_t)(TENTHS_PER_HALF - angle);
        break;
    case QUADRANT_THIRD:
        angle = (int16_t)(angle - TENTHS_PER_HALF);
        break;
    case QUADRANT_FOURTH:
        angle = (int16_t)(TENTHS_PER_TURN - angle);
        break;
    case QUADRANT_FULL_TURN:
        angle = (int16_t)(angle - TENTHS_PER_TURN);
        break;
    default:
        break;
    }
    divided = m68k_divs_w((uint32_t)(int32_t)angle, TENTHS_PER_DEGREE);
    degree = quotient_word(divided);
    tenths = remainder_word(divided);
    sine = sine_entry(image, degree);
    if (tenths != 0) {
        /* `muls.w` then `ext.l`: the product's LOW word, sign-extended, is what is divided. */
        int16_t step = (int16_t)(uint16_t)(sine_entry(image, (int32_t)degree + 1) - sine);
        int16_t scaled = (int16_t)(uint16_t)(step * tenths);

        sine = (int16_t)(uint16_t)(sine + quotient_word(m68k_divs_w((uint32_t)(int32_t)scaled, TENTHS_PER_DEGREE)));
    }
    if (quadrant >= LOWER_HALF_FIRST_QUADRANT)
        sine = (int16_t)(uint16_t)-sine;
    return sine;
}

/* $fcac4c — cos(angle) = isin(angle + 900), with at most ONE turn taken off the sum (isin takes the
 * rest). The sum wraps as a word. */
int16_t vdi_icos(const uint8_t *image, int16_t angle)
{
    angle = (int16_t)(uint16_t)(angle + TENTHS_PER_QUARTER);
    if (angle > TENTHS_PER_TURN)
        angle = (int16_t)(angle - TENTHS_PER_TURN);
    return vdi_isin(image, angle);
}

/* ================================================================================================
 * Clipping and the GDP's geometry.
 * ============================================================================================= */

/* $fcc092 — the Cohen-Sutherland outcode of (x, y) against the Line-A clip rectangle: left or right,
 * plus above or below, signed compares, inclusive edges. */
#define OUTCODE_LEFT          1
#define OUTCODE_RIGHT         2
#define OUTCODE_ABOVE         4
#define OUTCODE_BELOW         8

int16_t vdi_clip_code(const uint8_t *image, int16_t x, int16_t y)
{
    int16_t code = 0;

    if (x < (int16_t)be16(image + LINEA_XMINCL))
        code = OUTCODE_LEFT;
    else if (x > (int16_t)be16(image + LINEA_XMAXCL))
        code = OUTCODE_RIGHT;
    if (y < (int16_t)be16(image + LINEA_YMINCL))
        code += OUTCODE_ABOVE;
    else if (y > (int16_t)be16(image + LINEA_YMAXCL))
        code += OUTCODE_BELOW;
    return code;
}

/* $fcc6b4 — how many segments an arc or ellipse is drawn in: a quarter of the larger radius, held to
 * 32..128. Signed throughout (`asr.w`, `bge`/`ble`). */
#define N_STEPS_RADIUS_SHIFT  2
#define N_STEPS_MIN           32
#define N_STEPS_MAX           128

void vdi_clc_nsteps(uint8_t *image)
{
    int16_t xrad = (int16_t)be16(image + LINEA_GDP_XRAD);
    int16_t yrad = (int16_t)be16(image + LINEA_GDP_YRAD);
    int16_t steps = (int16_t)((xrad > yrad ? xrad : yrad) >> N_STEPS_RADIUS_SHIFT);

    if (steps < N_STEPS_MIN)
        steps = N_STEPS_MIN;
    else if (steps > N_STEPS_MAX)
        steps = N_STEPS_MAX;
    wr16(image + LINEA_GDP_N_STEPS, (uint16_t)steps);
}

/* $fcced6 — (x, y) carried into `quadrant` 1..4 by sign: x kept in 1 and 4, negated in 2 and 3; y kept
 * in 1 and 2, negated in 3 and 4. Any other quadrant stores nothing through either pointer. Two C
 * switches in the ROM, which is what Ghidra could not decompile. */
enum { QUAD_FIRST = 1, QUAD_SECOND, QUAD_THIRD, QUAD_FOURTH };

void vdi_quad_xform(uint8_t *image, int16_t quadrant, int16_t x, int16_t y, uint32_t x_out, uint32_t y_out)
{
    if (quadrant == QUAD_FIRST || quadrant == QUAD_FOURTH)
        wr16(image + x_out, (uint16_t)x);
    else if (quadrant == QUAD_SECOND || quadrant == QUAD_THIRD)
        wr16(image + x_out, (uint16_t)-x);
    if (quadrant == QUAD_FIRST || quadrant == QUAD_SECOND)
        wr16(image + y_out, (uint16_t)y);
    else if (quadrant == QUAD_THIRD || quadrant == QUAD_FOURTH)
        wr16(image + y_out, (uint16_t)-y);
}

/* ================================================================================================
 * The text scaler.
 * ============================================================================================= */

/* $fcedd0 — the DDA increment that scales a font of `actual` lines to `requested`, and its direction
 * into LINEA_T_SCLSTS. Down (requested <= actual): requested/actual as a fraction of 65536, a request
 * of 0 taken as 1. Up: the EXCESS over actual as that fraction — or, when the excess is not less than
 * actual (twice the size or more), VDI_DDA_DOUBLE.
 *
 * EQUAL SIZES ANSWER 0, not "no scaling": 65536 * actual / actual does not fit `divu.w`'s word, so the
 * register is left as the shifted dividend, whose low word is 0. An `actual` of 0 on the way down
 * divides by zero (`vdi/helpers.h`).
 *
 * WHICH ARMS THE ROM REACHES. The one caller ($fce088, vst_height's font search) passes the chosen
 * font's FORM_HEIGHT as `actual` and the caller's ptsin[1] as `requested`, and branches ROUND the call
 * when the two are equal ($fce076 `cmp.w 40(a4),d6 / beq`): the equal-size arm is ROM-UNREACHABLE, and
 * so is an `actual` of 0 or below, which no font the ROM has carries. A `requested` of 0 or below IS
 * reachable — it is a word the application hands vst_height. The cases pin every arm regardless: the
 * routine is the ROM's, and a caller of the `.S` could reach them. */
int16_t vdi_clc_dda(uint8_t *image, int16_t actual, int16_t requested)
{
    uint16_t numerator;

    if (requested > actual) {
        wr16(image + LINEA_T_SCLSTS, VDI_SCALE_UP);
        numerator = (uint16_t)(requested - actual);
        if ((int16_t)numerator >= actual)
            return (int16_t)VDI_DDA_DOUBLE;
    } else {
        wr16(image + LINEA_T_SCLSTS, VDI_SCALE_DOWN);
        numerator = requested == 0 ? 1 : (uint16_t)requested;
    }
    return quotient_word(m68k_divu_w((uint32_t)numerator << M68K_WORD_BITS, (uint16_t)actual));
}

/* $fcee02 — `size` stepped through the DDA LINEA_DDA_INC holds: a half-full word accumulator gains the
 * increment `size` times, and each CARRY out of it is one more line. Scaling up adds one line besides
 * per step; scaling down answers at least 1. VDI_DDA_DOUBLE doubles instead, and a size below 1 (the
 * `subq.w #1` goes negative) answers 0 in either direction. */
int16_t vdi_act_siz(const uint8_t *image, int16_t size)
{
    uint16_t increment = be16(image + LINEA_DDA_INC);
    uint16_t accumulator = VDI_DDA_ACCUMULATOR_START;
    uint16_t scaled = 0;
    uint16_t step = (uint16_t)(size - 1);      /* the `dbf` count */

    if (increment == VDI_DDA_DOUBLE)
        return (int16_t)(uint16_t)(size + size);
    if ((int16_t)step < 0)
        return 0;
    if (be16(image + LINEA_T_SCLSTS) & VDI_SCALE_UP_MASK) {
        do {
            accumulator = (uint16_t)(accumulator + increment);
            if (accumulator < increment)
                scaled++;
            scaled++;
        } while (step-- != 0);
        return (int16_t)scaled;
    }
    do {
        accumulator = (uint16_t)(accumulator + increment);
        if (accumulator < increment)
            scaled++;
    } while (step-- != 0);
    return scaled == 0 ? 1 : (int16_t)scaled;
}

/* ================================================================================================
 * The small copies.
 * ============================================================================================= */

/* $fce0ee — a font's name, FONT_NAME_BYTES of it, byte by byte and forwards. */
void vdi_copy_name(uint8_t *image, uint32_t source, uint32_t destination)
{
    const uint8_t *from = image + source;
    uint8_t *to = image + destination;
    uint16_t bytes = FONT_NAME_BYTES;

    COUNT_BARRIER(bytes);
    do {
        *to++ = *from++;
        CURSOR_BARRIER(from);
        CURSOR_BARRIER(to);
    } while (--bytes != 0);
}

/* $fcfaac — the font form at LINEA_FBASE turned into 68000 byte order: every word's two bytes swapped,
 * for FWIDTH x DELY bytes. `mulu.w` then `lsr.w`: only the product's LOW WORD is halved, and the
 * `subq.w #1` + `dbf` makes a count of 0 — a form under two bytes, or a product that is a multiple of
 * $20000 — 65536 words. An odd product leaves its last byte alone. */
#define BYTE_ROTATION 8

void vdi_font_byteswap(uint8_t *image)
{
    uint16_t form_bytes = (uint16_t)((uint32_t)be16(image + LINEA_FWIDTH) * be16(image + LINEA_DELY));
    uint16_t word_count = (uint16_t)((form_bytes >> 1) - 1);      /* the `dbf` count */
    uint8_t *word = image + be32(image + LINEA_FBASE);

    do {
        wr16(word, rotate_right16(be16(word), BYTE_ROTATION));
        word += WORD_BYTES;
        CURSOR_BARRIER(word);
    } while (word_count-- != 0);
}

/* ================================================================================================
 * The register routines the mouse and the keyboard use.
 * ============================================================================================= */

/* $fcfedc — the mouse position held to the screen: each of D0/D1 below 0 becomes 0 and past
 * DEV_TAB's last column/row becomes it, signed, as words. mouse_isr calls it on each side of the
 * program's USER_MOT. */
enum { CLAMP_RESULT_X, CLAMP_RESULT_Y };

static uint32_t clamp_word(uint32_t coordinate, int16_t last)
{
    if ((int16_t)coordinate < 0)
        return set_low_word(coordinate, 0);
    if ((int16_t)coordinate > last)
        return set_low_word(coordinate, (uint16_t)last);
    return coordinate;
}

uint32_t vdi_clamp_mouse(const uint8_t *image, uint32_t x, uint32_t y, uint32_t *results)
{
    int16_t last_x = (int16_t)be16(image + LINEA_DEV_TAB + VDI_DEV_TAB_MAX_X_INDEX * WORD_BYTES);
    int16_t last_y = (int16_t)be16(image + LINEA_DEV_TAB + VDI_DEV_TAB_MAX_Y_INDEX * WORD_BYTES);

    results[CLAMP_RESULT_X] = clamp_word(x, last_x);
    results[CLAMP_RESULT_Y] = clamp_word(y, last_y);
    return results[CLAMP_RESULT_X];
}

/* $fca648 — vq_key_s's answer: the four modifier keys' bits (the two shifts, Control, Alternate) of
 * KBSHIFT, below Caps Lock. `move.b` then `andi.w`: D0's low word, over the caller's high word. */
#define KBSHIFT_MODIFIER_KEYS_MASK ((1u << KBSHIFT_CAPSLOCK_BIT) - 1)   /* ($fca64e andi.w #15) */

uint32_t vdi_get_kbshift(const uint8_t *image, uint32_t entry_d0)
{
    return set_low_word(entry_d0, (uint16_t)(image[KBSHIFT] & KBSHIFT_MODIFIER_KEYS_MASK));
}

/* ================================================================================================
 * GEMDOS from inside the VDI.
 * ============================================================================================= */

/* $fcfa9c — the VDI's `trap #1` door: `move.l (sp)+,LINEA_RETSAV / trap #1 / move.l LINEA_RETSAV,-(sp)
 * / rts`. It PARKS its own return address so the trap finds the caller's words at (sp), and returns
 * through whatever the longword holds after it — which is why it is not re-entrant, and why nothing
 * that runs under the trap may touch LINEA_RETSAV (nothing GEMDOS's `Malloc` or `Mfree` reaches does).
 *
 * THE TWO BUILDS TAKE THE TRAP TWO WAYS, `src/gemdos/console.c`'s arrangement one component along: on
 * target the trap is the machine's own, over a frame of the function word and its longword; off target
 * there is no trap to take, so the words go into a host slot and the GEMDOS dispatcher is called on
 * them directly — its handler then through the hook a case binds. The parked longword is the
 * caller's ROM return site on both. The TARGET branch is UNEXERCISED: no differential runs it
 * (`test_vdi_helpers_gemdos.py` says why), and the shipped build links `helpers.S` in this core's
 * place (`vdi/transcribed.h`). */
#ifdef RECREATE_HOST_DIFFERENTIAL
static uint32_t gemdos_trap_word_long(uint8_t *image, uint16_t function, uint32_t argument)
{
    uint8_t words_local[HOST_SLOT_VDI_GEMDOS_WORDS_BYTES];
    uint32_t words = host_slot_claim(VDI_GEMDOS_WORDS, words_local);
    uint32_t result;

    wr16(image + words, function);
    wr32(image + words + GEMDOS_ARGUMENT_WORD, argument);
    result = gemdos_dispatch(image, words);
    host_slot_release(VDI_GEMDOS_WORDS);
    return result;
}
#else
/* The trap entry restores D1-A6 from the frame it builds, so D0 is all it changes. */
static uint32_t gemdos_trap_word_long(uint8_t *image, uint16_t function, uint32_t argument)
{
    register uint32_t result __asm__("d0");

    (void)image;
    __asm__ volatile ("move.l %1,-(%%sp)\n\t"
                      "move.w %2,-(%%sp)\n\t"
                      "trap #1\n\t"
                      "addq.l #6,%%sp"
                      : "=d"(result)
                      : "d"(argument), "d"(function)
                      : "memory", "cc");
    return result;
}
#endif

uint32_t vdi_gemdos_call(uint8_t *image, uint32_t return_site, uint16_t function, uint32_t argument)
{
    wr32(image + LINEA_RETSAV, return_site);
    return gemdos_trap_word_long(image, function, argument);
}

/* ================================================================================================
 * The fill attributes a filled outline borrows.
 * ============================================================================================= */

/* $fcd056 — before an arrowhead or a wide line's end is FILLED as a polygon: the fill colour, the
 * perimeter flag and the two line-end styles of the CURRENT workstation saved into the GDP scratch; the
 * fill drawn in the line's colour, outlined, solid (a one-row pattern, no multi-plane fill); the line
 * style solid; and the line's ends plain, so the outline does not draw arrowheads of its own. In the
 * ROM's order, which only shows when the workstation overlaps the Line-A block. */
#define LINE_STYLE_SOLID      VDI_LINE_STYLES    /* the table's first mask ($fcd064) */
#define PERIMETER_ON          1                  /* ($fcd084 move.w #1)              */
#define LINE_END_SQUARE       0                  /* ($fcd0b0 clr.w)                  */

void vdi_s_fa_attr(uint8_t *image)
{
    uint32_t work = current_work(image);

    wr16(image + LINEA_LN_MASK, be16(image + LINE_STYLE_SOLID));
    wr16(image + LINEA_GDP_SAVED_FILL_COLOR, be16(image + work + WS_FILL_COLOR));
    wr16(image + work + WS_FILL_COLOR, be16(image + work + WS_LINE_COLOR));
    wr16(image + LINEA_GDP_SAVED_FILL_PER, be16(image + work + WS_FILL_PER));
    wr16(image + work + WS_FILL_PER, PERIMETER_ON);
    wr32(image + LINEA_PATPTR, VDI_PATTERN_SOLID);
    wr16(image + LINEA_PATMSK, 0);
    wr16(image + LINEA_MULTIFILL, 0);
    wr16(image + LINEA_GDP_SAVED_BEG_STYLE, be16(image + work + WS_LINE_BEG));
    wr16(image + LINEA_GDP_SAVED_END_STYLE, be16(image + work + WS_LINE_END));
    wr16(image + work + WS_LINE_BEG, LINE_END_SQUARE);
    wr16(image + work + WS_LINE_END, LINE_END_SQUARE);
}

/* $fcd0c2 — ...and the four put back. The Line-A pattern and line style are NOT: the dispatcher copies
 * the workstation's own into Line-A on the next call. */
void vdi_r_fa_attr(uint8_t *image)
{
    uint32_t work = current_work(image);

    wr16(image + work + WS_FILL_COLOR, be16(image + LINEA_GDP_SAVED_FILL_COLOR));
    wr16(image + work + WS_FILL_PER, be16(image + LINEA_GDP_SAVED_FILL_PER));
    wr16(image + work + WS_LINE_BEG, be16(image + LINEA_GDP_SAVED_BEG_STYLE));
    wr16(image + work + WS_LINE_END, be16(image + LINEA_GDP_SAVED_END_STYLE));
}

/* ================================================================================================
 * vr_trnfm: the raster form between the device's interleaved planes and GEM's standard ones.
 * ============================================================================================= */

/* A DEVICE form is `words` groups of `planes` words (plane 0 first in each); a STANDARD form is
 * `planes` runs of `words` words. Either is the other TRANSPOSED as a matrix of words, so both
 * directions are one transpose of `rows` x `columns` into `columns` x `rows`: device -> standard is
 * words x planes, standard -> device planes x words. All the counts are words (`dbf`), and the
 * standard form's stride is a sign-extended word (`adda.w`). */

/* $fd2db4 — into a SEPARATE buffer: row by row out of the source, each row down a column of the
 * destination. Both counts are `dbf`s entered at their test, so a count of 0 moves nothing. */
static void transpose_copy(uint8_t *image, uint32_t source, uint32_t destination, uint16_t columns, uint16_t rows)
{
    int16_t stride = (int16_t)(rows + rows);
    const uint8_t *from = image + source;
    uint8_t *column_top = image + destination;

    for (uint16_t row = rows; row-- != 0; column_top += WORD_BYTES) {
        uint8_t *to = column_top;

        for (uint16_t column = columns; column-- != 0;) {
            wr16(to, be16(from));
            from += WORD_BYTES;
            to += stride;
            CURSOR_BARRIER(from);
        }
    }
}

/* $fd2d80 — IN PLACE, by rotation: pass by pass the cursor steps over the words already in place
 * (`pass`, the pass's own remaining count, plus one), and each word it lands on is carried down to the
 * end of the run collected so far, the words between shifted up one to make room. The cursor for the
 * next pass continues from the last word moved. */
static void transpose_in_place(uint8_t *image, uint32_t base, uint16_t columns, uint16_t rows)
{
    uint8_t *cursor = image + base;

    if (rows == 0)
        return;
    for (uint16_t pass = columns; pass-- != 0;) {
        int32_t skip = 2 * (int32_t)(int16_t)pass + WORD_BYTES;
        uint16_t run = 0;
        uint8_t *last_moved = cursor;

        for (uint16_t row = (uint16_t)(rows - 1); row-- != 0;) {
            uint8_t *slot;
            uint16_t held;

            cursor += skip;
            held = be16(cursor);
            run = (uint16_t)(run + pass);
            slot = cursor;
            last_moved = cursor;
            for (uint16_t shift = run; shift-- != 0;) {
                last_moved = slot;
                slot -= WORD_BYTES;
                wr16(last_moved, be16(slot));
            }
            wr16(slot, held);
        }
        cursor = last_moved;
    }
}

/* $fd2d32 — vr_trnfm (opcode 110): the source MFDB (contrl[7..8]) turned into the other format at the
 * destination's address, and the DESTINATION MFDB's `stand` flag set to the format it now holds. Its
 * other fields are not written: GEM's caller fills them. The source's geometry and flag are read before
 * the destination's flag is stored, and both addresses after — the ROM's order. */
void vdi_vr_trnfm(uint8_t *image)
{
    uint32_t contrl = linea_pointer(image, LINEA_CONTRL);
    uint32_t source_mfdb = be32(image + contrl + CONTRL_POINTER_A);
    uint32_t destination_mfdb = be32(image + contrl + CONTRL_POINTER_B);
    uint16_t planes = be16(image + source_mfdb + MFDB_NPLANES);
    uint16_t words = (uint16_t)((uint32_t)be16(image + source_mfdb + MFDB_H) *
                                be16(image + source_mfdb + MFDB_WDWIDTH));
    int to_standard = be16(image + source_mfdb + MFDB_STAND) == 0;
    uint16_t columns = to_standard ? planes : words;
    uint16_t rows = to_standard ? words : planes;
    uint32_t source, destination;

    wr16(image + destination_mfdb + MFDB_STAND, to_standard ? MFDB_FORMAT_STANDARD : MFDB_FORMAT_DEVICE);
    source = be32(image + source_mfdb + MFDB_ADDR);
    destination = be32(image + destination_mfdb + MFDB_ADDR);
    if (source == destination)
        transpose_in_place(image, source, columns, rows);
    else
        transpose_copy(image, source, destination, columns, rows);
}
