/* fill.c — POLYGONS and FILLS: the scanline polygon fill, the VDI geometry over it, and the contour fill.
 *
 *   $fca05e $a006 filled_poly  one row: where the closed polygon's edges cross Y1, sorted, filled in pairs
 *   $fcbf16 clip_line          Cohen-Sutherland on X1,Y1..X2,Y2, the cut points by smul_div
 *   $fcbe8c polyline           contrl[1] points through $a003, each segment clipped when CLIP
 *   $fcc0ea plygn              the polygon closed, $a006 up its rows, then the perimeter in the fill colour
 *   $fcbbc0 v_fillarea         opcode 9: plygn
 *   $fd08f4 $a00f contour_fill a seed fill over a queue of spans, with $fcfb54 fill_span, $fcfb66 end_pts,
 *                              $fd0dc8 crunch_queue, $fd0e22 get_seed; $fd08e0 v_contourfill (103) and
 *                              $fd0fde v_get_pixel (105)
 *
 * $a006, fill_span and end_pts are hand 68000; the rest is Alcyon C, which keeps every contour-fill
 * variable at its absolute address (`vdi/fill.h`) — so does this, because each is compared image.
 *
 * THREE ROM FACTS a reader checks the C against:
 *   * PLYGN FILLS ROWS maxy DOWN TO miny + 1, never miny itself — the half-open crossing rule makes the
 *     top vertex's row empty anyway — and a polygon clipped at the top starts from YMINCL - 1 raised to
 *     at least 1, so rows 0 and 1 are never filled from a clip there. With a perimeter it INCREMENTS the
 *     caller's contrl[1] for the closing point and leaves it so.
 *   * END_PTS RUNS OVER THE SEED PIXEL'S OWN COLOUR, not up to the search colour: the span it answers is
 *     the run of pixels matching the one at (x, y), however the fill was asked for; SEED_TYPE only
 *     decides whether that run is fillable (`vdi/fill.h`).
 *   * THE CONTOUR FILL'S FIRST PASS goes UP: the seed row starts the walk with no direction flag, and the
 *     record queued for it carries the DOWN flag, so it is filled a second time when that record is taken.
 */
#include <stdint.h>

#include "machine.h"
#include "addrs.h"
#include "m68k_idioms.h"
#include "staged_call.h"
#include "vdi/vdi.h"
#include "vdi/helpers.h"
#include "vdi/raster.h"
#include "vdi/fill.h"
#include "vdi/transcribed.h"

#define PIXEL_IN_GROUP_MASK  15u
#define LEFTMOST_PIXEL_BIT   0x8000u
#define RIGHTMOST_PIXEL_BIT  0x0001u
#define PERIMETER_ON         1          /* WS_FILL_PER is tested for exactly 1 ($fcc252 cmpi.w #1) */
#define PERIMETER_STYLE      0xffff     /* the outline is solid ($fcc25a) */
#define CLIPPED_TOP_ROW_MIN  1          /* ($fcc1b2 cmpi.w #1) */
#define SEED_THE_SEED_COLOUR 1          /* VDI_FILL_SEED_TYPE's two values ($fd0986, $fd09bc) */
#define SEED_UP_TO_A_COLOUR  0
#define GO_DOWN              1          /* VDI_FILL_DIRECTION ($fd0b50) */
#define GO_UP                (-1)
/* v_get_pixel's answer: the pixel value, and its VDI colour index through REV_MAP_COL — where a set
 * monochrome pixel and a medium-res pixel of 3 both index as 15, the device's last pen ($fd1014). */
#define GET_PIXEL_WORDS      2
#define MONO_PLANES          1
#define MEDIUM_PLANES        2
#define MEDIUM_LAST_PEN      3
#define REV_MAP_LAST_INDEX   15

/* ---- the words this file keeps in RAM --------------------------------------------------------------- */

/* A queue word's address — see `vdi/fill.h`. The index is a LONG: the ROM takes a queue variable with
 * `movea.w` and steps it in the address register (`subq.w #3,a0`, `addq.w #1,a0` are whole-register adds),
 * so QTOP $8002 less 3 reaches below the queue — wrapping on the 24-bit bus — not 64K above it. That lands
 * in $ff16fc..$ff1704, where the machine takes a bus error: the only index a word would not hold is one no
 * case can stage (unpinned, `test_vdi_fill_contour.py`). */
static inline uint32_t queue_word(int32_t index)
{
    return bus_address(word_entry(VDI_FILL_QUEUE, index));
}

static inline int16_t queued(const uint8_t *image, int32_t index)
{
    return ram_word(image, queue_word(index));
}


/* ================================================================================================
 * $a006 and the polygon.
 * ============================================================================================= */

/* The x where the edge (x1, y1)..(x2, y2) crosses row `row`: x1 + (2dx * (row - y1) / dy) / 2, the
 * halving rounded away from zero on the quotient's own sign ($fca09c..$fca0ba).
 *
 * A QUOTIENT PAST A WORD — reachable with coordinates 32,768 apart, whose word differences wrap — leaves
 * the `muls.w` product in the register and `bpl` testing the sign of the whole 32-bit PRODUCT, which
 * `muls.w` left in N (`m68k_divs_w_v`), while the halving works on its low word. The two signs
 * differ only where it matters: an even word halves alike on both paths EXCEPT $8000, whose `neg.w` is
 * itself — a product >= 0 with the low word $8000 halves to $c000, where the word's sign would give $4000. */
static inline int16_t edge_crossing(int16_t x1, int16_t y1, int16_t x2, int16_t dy, int16_t row)
{
    uint16_t twice_dx = (uint16_t)((x2 - x1) * 2);
    int32_t product = m68k_muls_w(twice_dx, (uint16_t)(row - y1));
    int overflowed;
    uint16_t quotient = (uint16_t)m68k_divs_w_v((uint32_t)product, (uint16_t)dy, &overflowed);
    int negative = overflowed ? product < 0 : (int16_t)quotient < 0;
    int16_t half;

    if (negative)
        half = (int16_t)-(uint16_t)((int16_t)(uint16_t)(-quotient + 1) >> 1);
    else
        half = (int16_t)((int16_t)(uint16_t)(quotient + 1) >> 1);
    return (int16_t)(half + x1);
}

/* One pair of crossings through $a004, the ends CLIPPED to XMINCL..XMAXCL when `clipped`: X1/X2 are
 * stored first, and a pair wholly outside is skipped with them stored ($fca112..$fca15e). */
static void fill_pair(uint8_t *image, int16_t left, int16_t right, int clipped)
{
    int16_t bound;

    wr16(image + LINEA_X1, (uint16_t)left);
    wr16(image + LINEA_X2, (uint16_t)right);
    if (clipped) {
        bound = ram_word(image, LINEA_XMINCL);
        if (left < bound) {
            if (right < bound)
                return;
            wr16(image + LINEA_X1, (uint16_t)bound);
        }
        bound = ram_word(image, LINEA_XMAXCL);
        if (right > bound) {
            if (left > bound)
                return;
            wr16(image + LINEA_X2, (uint16_t)bound);
        }
    }
    linea_hline(image);
}

/* $fca05e — $a006 filled_poly: row Y1 of the polygon ptsin holds, contrl[1] edges from point i to i + 1
 * — so the caller has CLOSED it, point contrl[1] = point 0. An edge crosses when Y1 - y1 and Y1 - y2
 * differ in sign bit (half-open: its lower end counts, its upper does not); a horizontal edge never
 * does. The crossings are sorted and filled in pairs, an odd last one dropped. Unclipped in y — plygn
 * clips the rows — and clipped in x only when CLIP. */
TRANSCRIBED_CORE
void linea_filled_poly(uint8_t *image)
{
    uint16_t edges = (uint16_t)contrl_word(image, CONTRL_N_PTSIN);
    uint32_t point = linea_pointer(image, LINEA_PTSIN);
    uint32_t crossing = VDI_SCRATCH;
    uint16_t count, pairs;
    int clipped;

    wr16(image + LINEA_GDP_FILL_INT, 0);
    do {                                            /* `subq.w #1` / `dbf`: 0 edges is 65,536 */
        int16_t x1 = ram_word(image, point), y1 = ram_word(image, point + VDI_POINT_Y);
        int16_t x2 = ram_word(image, point + VDI_POINT_BYTES), y2 = ram_word(image, point + VDI_POINT_BYTES + VDI_POINT_Y);
        int16_t dy = (int16_t)(y2 - y1);

        if (dy != 0) {
            int16_t row = ram_word(image, LINEA_Y1);
            int16_t from_first = (int16_t)(row - y1);

            if ((int16_t)(from_first ^ (int16_t)(row - y2)) < 0) {
                set_ram_word(image, crossing, edge_crossing(x1, y1, x2, dy, row));
                crossing += VDI_WORD_BYTES;
                wr16(image + LINEA_GDP_FILL_INT, (uint16_t)(be16(image + LINEA_GDP_FILL_INT) + 1));
            }
        }
        point += VDI_POINT_BYTES;
    } while (--edges != 0);

    count = be16(image + LINEA_GDP_FILL_INT);
    if (count == 0)
        return;
    vdi_sort_words(image, count, VDI_SCRATCH);
    pairs = (uint16_t)((int16_t)be16(image + LINEA_GDP_FILL_INT) >> 1);
    clipped = be16(image + LINEA_CLIP) != 0;
    crossing = VDI_SCRATCH;
    do {                                            /* one crossing is `dbf` from -1: 65,536 pairs */
        fill_pair(image, ram_word(image, crossing), ram_word(image, crossing + VDI_WORD_BYTES), clipped);
        crossing += 2 * VDI_WORD_BYTES;
    } while (--pairs != 0);
}

/* The point at `at` as X1,Y1 (or X2,Y2 at `LINEA_X2`). */
static void load_end(uint8_t *image, uint32_t end, uint32_t at)
{
    wr16(image + end, be16(image + at));
    wr16(image + end + (LINEA_Y1 - LINEA_X1), be16(image + at + VDI_POINT_Y));
}

/* $fcbf16 — clip_line: X1,Y1..X2,Y2 cut to the clip rectangle in place, one end at a time — the first
 * end while it is outside, by its LOWEST outcode bit — until both are in (answer 1) or both are outside
 * one edge (answer 0). The cut end's other coordinate is smul_div(d_other, edge - start, d_this) plus
 * the start, stored BEFORE the edge itself. */
int16_t vdi_clip_line(uint8_t *image)
{
    for (;;) {
        int16_t second = vdi_clip_code(image, ram_word(image, LINEA_X2), ram_word(image, LINEA_Y2));
        int16_t first = vdi_clip_code(image, ram_word(image, LINEA_X1), ram_word(image, LINEA_Y1));
        int16_t outside, dx, dy, x1, y1;
        uint32_t x_at, y_at;

        if ((first | second) == 0)
            return 1;
        if (first & second)
            return 0;
        outside = first ? first : second;
        x_at = first ? LINEA_X1 : LINEA_X2;
        y_at = first ? LINEA_Y1 : LINEA_Y2;
        x1 = ram_word(image, LINEA_X1);
        y1 = ram_word(image, LINEA_Y1);
        dx = (int16_t)(ram_word(image, LINEA_X2) - x1);
        dy = (int16_t)(ram_word(image, LINEA_Y2) - y1);
        if (outside & OUTCODE_LEFT) {
            int16_t edge = ram_word(image, LINEA_XMINCL);

            set_ram_word(image, y_at, (int16_t)(vdi_smul_div(dy, (int16_t)(edge - x1), dx) + ram_word(image, LINEA_Y1)));
            set_ram_word(image, x_at, ram_word(image, LINEA_XMINCL));
        } else if (outside & OUTCODE_RIGHT) {
            int16_t edge = ram_word(image, LINEA_XMAXCL);

            set_ram_word(image, y_at, (int16_t)(vdi_smul_div(dy, (int16_t)(edge - x1), dx) + ram_word(image, LINEA_Y1)));
            set_ram_word(image, x_at, ram_word(image, LINEA_XMAXCL));
        } else if (outside & OUTCODE_ABOVE) {
            int16_t edge = ram_word(image, LINEA_YMINCL);

            set_ram_word(image, x_at, (int16_t)(vdi_smul_div(dx, (int16_t)(edge - y1), dy) + ram_word(image, LINEA_X1)));
            set_ram_word(image, y_at, ram_word(image, LINEA_YMINCL));
        } else if (outside & OUTCODE_BELOW) {
            int16_t edge = ram_word(image, LINEA_YMAXCL);

            set_ram_word(image, x_at, (int16_t)(vdi_smul_div(dx, (int16_t)(edge - y1), dy) + ram_word(image, LINEA_X1)));
            set_ram_word(image, y_at, ram_word(image, LINEA_YMAXCL));
        }
    }
}

/* $fcbe8c — polyline: contrl[1] points, segment by segment through $a003, each clipped first when CLIP
 * (a segment clipped away is not drawn). LSTLIN is 0 until the LAST segment and left 1 after it. */
void vdi_polyline(uint8_t *image)
{
    uint32_t point;
    int16_t segments;

    wr16(image + LINEA_LSTLIN, 0);                  /* before the count: a contrl laid over it reads 0 */
    point = linea_pointer(image, LINEA_PTSIN);
    segments = (int16_t)(contrl_word(image, CONTRL_N_PTSIN) - 1);
    for (; segments > 0; segments--) {
        if (segments == 1)
            wr16(image + LINEA_LSTLIN, 1);
        load_end(image, LINEA_X1, point);
        point += VDI_POINT_BYTES;
        load_end(image, LINEA_X2, point);
        if (be16(image + LINEA_CLIP) == 0 || vdi_clip_line(image))
            linea_line(image);
    }
}

/* plygn's rows: the lowest and highest y of contrl[1] points, into FILL_MAXY / FILL_MINY. */
static void polygon_rows(uint8_t *image, uint32_t points)
{
    int16_t first = ram_word(image, points + VDI_POINT_Y);
    int16_t left = (int16_t)(contrl_word(image, CONTRL_N_PTSIN) - 1);
    uint32_t y_at = points + VDI_POINT_BYTES + VDI_POINT_Y;

    set_ram_word(image, LINEA_GDP_FILL_MINY, first);
    set_ram_word(image, LINEA_GDP_FILL_MAXY, first);
    for (; left > 0; left--) {
        int16_t y = ram_word(image, y_at);

        y_at += VDI_POINT_BYTES;
        if (y < ram_word(image, LINEA_GDP_FILL_MINY))
            set_ram_word(image, LINEA_GDP_FILL_MINY, y);
        else if (y > ram_word(image, LINEA_GDP_FILL_MAXY))
            set_ram_word(image, LINEA_GDP_FILL_MAXY, y);
    }
}

/* ...clipped to YMINCL..YMAXCL: 0 when the polygon misses them. The top is clipped to the row ABOVE
 * YMINCL, since the rows filled stop short of FILL_MINY, and never above row 1. */
static int clip_polygon_rows(uint8_t *image)
{
    int16_t edge = ram_word(image, LINEA_YMINCL);

    if (ram_word(image, LINEA_GDP_FILL_MINY) < edge) {
        if (ram_word(image, LINEA_GDP_FILL_MAXY) < edge)
            return 0;
        set_ram_word(image, LINEA_GDP_FILL_MINY, (int16_t)(ram_word(image, LINEA_YMINCL) - 1));
        if (ram_word(image, LINEA_GDP_FILL_MINY) < CLIPPED_TOP_ROW_MIN)
            set_ram_word(image, LINEA_GDP_FILL_MINY, CLIPPED_TOP_ROW_MIN);
    }
    edge = ram_word(image, LINEA_YMAXCL);
    if (ram_word(image, LINEA_GDP_FILL_MAXY) > edge) {
        if (ram_word(image, LINEA_GDP_FILL_MINY) > edge)
            return 0;
        set_ram_word(image, LINEA_GDP_FILL_MAXY, ram_word(image, LINEA_YMAXCL));
    }
    return 1;
}

/* $fcc0ea — plygn: the polygon of contrl[1] points in the fill colour — its rows, clipped when CLIP,
 * each through $a006 from the lowest up, after the closing point is written at ptsin[contrl[1]] — and,
 * when WS_FILL_PER is exactly 1, its outline: solid, one point more (contrl[1] + 1, stored and LEFT). */
void vdi_plygn(uint8_t *image)
{
    uint32_t points = linea_pointer(image, LINEA_PTSIN);
    uint32_t closing;

    set_fill_colour_bits(image);
    wr16(image + LINEA_LSTLIN, 0);
    polygon_rows(image, points);
    if (be16(image + LINEA_CLIP) && !clip_polygon_rows(image))
        return;
    points = linea_pointer(image, LINEA_PTSIN);
    closing = word_entry(points, (int16_t)(contrl_word(image, CONTRL_N_PTSIN) * 2));
    copy_point(image, closing, points);
    wr16(image + LINEA_Y1, be16(image + LINEA_GDP_FILL_MAXY));
    while (ram_word(image, LINEA_Y1) > ram_word(image, LINEA_GDP_FILL_MINY)) {
        wr16(image + LINEA_GDP_FILL_INT, 0);
        linea_filled_poly(image);
        wr16(image + LINEA_Y1, (uint16_t)(be16(image + LINEA_Y1) - 1));
    }
    if (current_work_word(image, WS_FILL_PER) != PERIMETER_ON)
        return;
    wr16(image + LINEA_LN_MASK, PERIMETER_STYLE);
    set_contrl_word(image, CONTRL_N_PTSIN, (uint16_t)(contrl_word(image, CONTRL_N_PTSIN) + 1));
    vdi_polyline(image);
}

/* $fcbbc0 — v_fillarea (opcode 9): plygn over the call's points. */
void vdi_v_fillarea(uint8_t *image)
{
    vdi_plygn(image);
}

/* ================================================================================================
 * The contour fill.
 * ============================================================================================= */

/* $fcfb54 — fill_span: x1..x2 on row y in the fill pattern, through $a004's patterned entry. */
TRANSCRIBED_CORE
void linea_fill_span(uint8_t *image, int16_t x1, int16_t x2, int16_t y)
{
    linea_hline_patterned(image, (uint16_t)x1, (uint16_t)y, (uint16_t)x2);
}

/* The colour of one pixel, read as the ROM reads it: A5 stepped by `step` (`adda.w a3,a5`), then the planes
 * LAST FIRST with `-(a5)`, each bit shifted into a WORD (`addx.w`) — so past 16 planes the first ones read are
 * shifted out ($fcfbae). A5 is left where the reads leave it, which is back where it started only when the
 * step is the bytes read: see `end_pts_step`. */
static uint16_t pixel_colour(const uint8_t *image, uint32_t *at, uint16_t bit, uint16_t planes, uint32_t step)
{
    uint32_t word = *at + step;
    uint16_t colour = 0;

    do {                                            /* `dbf` from PLANES - 1: 0 planes is 65,536 */
        word -= VDI_WORD_BYTES;
        colour = (uint16_t)((colour << 1) | ((be16(image + bus_address(word)) & bit) != 0));
    } while (--planes != 0);
    *at = word;
    return colour;
}

/* end_pts' group step: `movea.w d3,a3` / `adda.w a3,a3` / `adda.w a3,a5` — PLANES * 2 SIGN-EXTENDED FROM A
 * WORD, so PLANES $4000..$7fff step BACK 32K or more, and every read then leaves A5 64K lower than it found it
 * (PLANES 0: 128K, its 65,536 reads). A caller-writable Line-A field reaches it. */
static uint32_t end_pts_step(uint16_t planes)
{
    return sign_ext16((uint16_t)(planes * VDI_WORD_BYTES));
}

/* Where end_pts' walk is: A5 (the ROM's own register, stepped as it steps it), the pixel's bit, the x reached. */
struct walk {
    uint32_t at;
    uint16_t bit;
    int16_t x;
};

/* $fcfb66 — end_pts: the run of pixels on row y the colour of (x, y), found by walking out from it —
 * rightwards while the colour holds and x has not passed XMAXCL, then leftwards likewise to XMINCL — its
 * right end stored at `xright_at` FIRST, then its left at `xleft_at`. Answers whether the run is
 * fillable: its colour against SEARCH_COLOR, flipped by SEED_TYPE. A row outside YMINCL..YMAXCL answers
 * 0 and stores nothing — the top tested by `bmi` on the word difference, the bottom by `bgt`. x is not
 * tested: the walk starts wherever it is. The walk steps a GROUP at a time through memory, so a run
 * reaching past the screen's side reads on into the next or previous row. Rightwards a new group is one
 * step more before the read; leftwards the read itself falls into it, one step fewer. */
TRANSCRIBED_CORE
int16_t linea_end_pts(uint8_t *image, int16_t x, int16_t y, uint32_t xleft_at, uint32_t xright_at)
{
    uint16_t planes;
    uint32_t step;
    uint16_t seed_colour, colour, answer;
    struct walk seed, walk;
    int16_t edge;

    if (word_difference_is_negative((uint16_t)y, be16(image + LINEA_YMINCL)) || y > ram_word(image, LINEA_YMAXCL))
        return 0;
    planes = be16(image + LINEA_PLANES);
    step = end_pts_step(planes);
    seed.at = be32(image + SYSVAR_V_BAS_AD) + (uint32_t)concat_offset(image, (uint16_t)x, (uint16_t)y);
    seed.bit = (uint16_t)(LEFTMOST_PIXEL_BIT >> ((uint16_t)x & PIXEL_IN_GROUP_MASK));
    seed.x = x;
    walk = seed;
    seed_colour = pixel_colour(image, &walk.at, walk.bit, planes, step);

    colour = seed_colour;
    edge = ram_word(image, LINEA_XMAXCL);
    while (colour == seed_colour && walk.x <= edge) {
        walk.x++;
        walk.bit = rotate_right16(walk.bit, 1);
        if (walk.bit == LEFTMOST_PIXEL_BIT)
            walk.at += step;
        colour = pixel_colour(image, &walk.at, walk.bit, planes, step);
    }
    set_ram_word(image, xright_at, (int16_t)(walk.x - 1));

    walk = seed;                                    /* `movea.l a2,a5`: the group, not where the reads left A5 */
    colour = seed_colour;
    edge = ram_word(image, LINEA_XMINCL);
    while (colour == seed_colour && walk.x >= edge) {
        walk.x--;
        walk.bit = rotate_left16(walk.bit, 1);
        colour = pixel_colour(image, &walk.at, walk.bit, planes,
                              walk.bit == RIGHTMOST_PIXEL_BIT ? 0 : step);
    }
    set_ram_word(image, xleft_at, (int16_t)(walk.x + 1));

    answer = be16(image + VDI_FILL_SEED_TYPE);
    if (seed_colour != be16(image + VDI_FILL_SEARCH_COLOR))
        answer ^= 1;
    return (int16_t)answer;
}

/* ---- SEEDABORT: the RAM vector the contour fill asks, once a pass, whether to stop ----------------
 * v_contourfill points it at the ROM's `moveq #0,d0 / rts` (LINEA_ROM_SEEDABORT_DEFAULT), which is
 * answered here as what it does; anything else is a program's routine, called as the ROM calls it —
 * `movea.l SEEDABORT,a0 / jsr (a0)`, D0.w the answer — through `staged_call.h`'s register-carrying shape,
 * A0 loaded with the routine as the ROM's `movea.l` leaves it. What the ROM's D0/D1 hold at the `jsr` is
 * what the fill last computed in them, which no build hands the routine (0 here): a staged routine that
 * read them would diverge, rightly. */
#define SEEDABORT_DEFAULT_ANSWER 0

/* Out of line, because the routine owes this caller no register (`staged_call.h`): the callee-saved set it
 * clobbers is saved here, on the path that calls, rather than in every crunch_queue. */
static __attribute__((noinline)) int16_t call_seedabort(uint8_t *image, uint32_t routine)
{
    uint32_t registers[STAGED_REGISTERS] = {[STAGED_A0] = routine};

    call_vector_registers(image, routine, registers);
    return (int16_t)registers[STAGED_D0];
}

static int16_t seed_abort(uint8_t *image)
{
    uint32_t routine = be32(image + LINEA_SEEDABORT);

    if (routine == LINEA_ROM_SEEDABORT_DEFAULT)
        return SEEDABORT_DEFAULT_ANSWER;
    return call_seedabort(image, routine);
}

/* $fd0dc8 — crunch_queue: drop the EMPTY records off the queue's top; if that leaves the taker at or
 * past the top, start it again at the bottom and ask SEEDABORT whether the fill is DONE. The test of
 * queue[QTOP - 3] comes before the bound, so an empty queue reads the word under it. */
void linea_crunch_queue(uint8_t *image)
{
    while (queued(image, ram_word(image, VDI_FILL_QTOP) - VDI_FILL_RECORD_WORDS) == (int16_t)VDI_FILL_EMPTY
           && ram_word(image, VDI_FILL_QTOP) > ram_word(image, VDI_FILL_QBOTTOM))
        set_ram_word(image, VDI_FILL_QTOP, (int16_t)(ram_word(image, VDI_FILL_QTOP) - VDI_FILL_RECORD_WORDS));
    if (ram_word(image, VDI_FILL_QPTR) >= ram_word(image, VDI_FILL_QTOP)) {
        set_ram_word(image, VDI_FILL_QPTR, ram_word(image, VDI_FILL_QBOTTOM));
        set_ram_word(image, VDI_FILL_DONE, seed_abort(image));
    }
}

static inline void set_queued(uint8_t *image, int32_t index, int16_t value)
{
    set_ram_word(image, queue_word(index), value);
}

static inline void advance(uint8_t *image, uint32_t at, int16_t by)
{
    set_ram_word(image, at, (int16_t)(ram_word(image, at) + by));
}

/* get_seed's search of the queue for a record of the same row and direction starting where this run
 * does — a span another pass has already queued. Answers whether it found one, QTMP left at it; else QHOLE
 * is left at the first empty record passed (-1 when none). */
static int queued_twin(uint8_t *image, int16_t y, uint32_t xleft_at)
{
    set_ram_word(image, VDI_FILL_QTMP, ram_word(image, VDI_FILL_QBOTTOM));
    set_ram_word(image, VDI_FILL_QHOLE, (int16_t)VDI_FILL_EMPTY);
    for (; ram_word(image, VDI_FILL_QTMP) < ram_word(image, VDI_FILL_QTOP);
         advance(image, VDI_FILL_QTMP, VDI_FILL_RECORD_WORDS)) {
        int16_t record = ram_word(image, VDI_FILL_QTMP);

        if (queued(image, record + 1) == ram_word(image, xleft_at)
            && queued(image, record) != (int16_t)VDI_FILL_EMPTY
            && (int16_t)(queued(image, record) ^ VDI_FILL_DOWN_FLAG) == y)
            return 1;
        if (queued(image, record) == (int16_t)VDI_FILL_EMPTY && ram_word(image, VDI_FILL_QHOLE) == (int16_t)VDI_FILL_EMPTY)
            set_ram_word(image, VDI_FILL_QHOLE, record);
    }
    return 0;
}

/* One word of the record at QTMP, then QTMP one word on: `addq.w #1` in memory, re-read by `movea.w`. */
static void queue_at_qtmp_and_step(uint8_t *image, int16_t value)
{
    set_queued(image, ram_word(image, VDI_FILL_QTMP), value);
    advance(image, VDI_FILL_QTMP, 1);
}

/* $fd0e22 — get_seed: the fillable run through (x, y & ROW_MASK) — `y` carrying the direction the fill
 * will go on in — QUEUED, answering 1. Answers 0 when the fill is DONE, when the run is not fillable,
 * when its twin (the same row going the OTHER way, from the same left end) is already queued — which is
 * two passes meeting: the run is drawn here, the twin taken, and *collide set — and when the queue is
 * full, which also makes the fill DONE. *collide is cleared first. QTMP is RE-READ wherever the ROM
 * re-reads it — after the span is drawn, between the record's three stores — since a staged screen or
 * queue can lie over it. */
int16_t linea_get_seed(uint8_t *image, int16_t x, int16_t y, uint32_t xleft_at, uint32_t xright_at,
                       uint32_t collide_at)
{
    set_ram_word(image, collide_at, 0);
    if (ram_word(image, VDI_FILL_DONE))
        return 0;
    if (linea_end_pts(image, x, (int16_t)(y & VDI_FILL_ROW_MASK), xleft_at, xright_at) == 0)
        return 0;
    if (queued_twin(image, y, xleft_at)) {
        linea_fill_span(image, ram_word(image, xleft_at), ram_word(image, xright_at), (int16_t)(y & VDI_FILL_ROW_MASK));
        set_queued(image, ram_word(image, VDI_FILL_QTMP), (int16_t)VDI_FILL_EMPTY);
        if ((int16_t)(ram_word(image, VDI_FILL_QTMP) + VDI_FILL_RECORD_WORDS) == ram_word(image, VDI_FILL_QTOP))
            linea_crunch_queue(image);
        set_ram_word(image, collide_at, 1);
        return 0;
    }
    if (ram_word(image, VDI_FILL_QHOLE) == (int16_t)VDI_FILL_EMPTY) {
        advance(image, VDI_FILL_QTOP, VDI_FILL_RECORD_WORDS);
        if (ram_word(image, VDI_FILL_QTOP) > VDI_FILL_QUEUE_LAST) {
            set_ram_word(image, VDI_FILL_DONE, 1);
            set_ram_word(image, collide_at, 0);
            return 0;
        }
    } else {
        set_ram_word(image, VDI_FILL_QTMP, ram_word(image, VDI_FILL_QHOLE));
    }
    queue_at_qtmp_and_step(image, y);
    queue_at_qtmp_and_step(image, ram_word(image, xleft_at));
    set_queued(image, ram_word(image, VDI_FILL_QTMP), ram_word(image, xright_at));
    return 1;
}

/* The word at `high_at` above the one at `low_at`: `cmp.w` then `bgt`/`blt`, a TRUE signed compare (N ^ V),
 * not the sign of the wrapped difference — the two part for a span wider than 32,767 pixels. */
static int word_above(const uint8_t *image, uint32_t high_at, uint32_t low_at)
{
    return ram_word(image, high_at) > ram_word(image, low_at);
}

/* The seeds a filled span leaves ($fd0b44..$fd0dae): its neighbour row in DIRECTION across the span,
 * and where that row's run reaches PAST the span's ends, the filled row itself going back the other way
 * under the overhang — turning again for as long as each turn-back overhangs in its turn. */
static void seed_neighbours(uint8_t *image)
{
    set_ram_word(image, VDI_FILL_DIRECTION, (ram_word(image, VDI_FILL_OLDY) & VDI_FILL_DOWN_FLAG) ? GO_DOWN : GO_UP);
    set_ram_word(image, VDI_FILL_GOTSEED,
                 linea_get_seed(image, ram_word(image, VDI_FILL_OLDXLEFT),
                                (int16_t)(ram_word(image, VDI_FILL_OLDY) + ram_word(image, VDI_FILL_DIRECTION)),
                                VDI_FILL_NEWXLEFT, VDI_FILL_NEWXRIGHT, VDI_FILL_COLLISION));
    set_ram_word(image, VDI_FILL_LEFTDIRECTION, ram_word(image, VDI_FILL_DIRECTION));
    set_ram_word(image, VDI_FILL_LEFTSEED, ram_word(image, VDI_FILL_GOTSEED));
    set_ram_word(image, VDI_FILL_LEFTCOLLISION, ram_word(image, VDI_FILL_COLLISION));
    set_ram_word(image, VDI_FILL_LEFTOLDY, ram_word(image, VDI_FILL_OLDY));

    /* the overhang to the LEFT */
    while ((int16_t)(ram_word(image, VDI_FILL_OLDXLEFT) - 1) > ram_word(image, VDI_FILL_NEWXLEFT)
           && (ram_word(image, VDI_FILL_LEFTSEED) || ram_word(image, VDI_FILL_LEFTCOLLISION))) {
        set_ram_word(image, VDI_FILL_XLEFT, ram_word(image, VDI_FILL_OLDXLEFT));
        while (word_above(image, VDI_FILL_XLEFT, VDI_FILL_NEWXLEFT)) {
            advance(image, VDI_FILL_XLEFT, -1);
            set_ram_word(image, VDI_FILL_LEFTSEED,
                         linea_get_seed(image, ram_word(image, VDI_FILL_XLEFT),
                                        (int16_t)(ram_word(image, VDI_FILL_LEFTOLDY) ^ VDI_FILL_DOWN_FLAG),
                                        VDI_FILL_XLEFT, VDI_FILL_XRIGHT, VDI_FILL_LEFTCOLLISION));
        }
        set_ram_word(image, VDI_FILL_OLDXLEFT, ram_word(image, VDI_FILL_NEWXLEFT));
        if ((int16_t)(ram_word(image, VDI_FILL_NEWXLEFT) - 1) > ram_word(image, VDI_FILL_XLEFT)
            && (ram_word(image, VDI_FILL_LEFTSEED) || ram_word(image, VDI_FILL_LEFTCOLLISION))) {
            set_ram_word(image, VDI_FILL_NEWXLEFT, ram_word(image, VDI_FILL_XLEFT));
            advance(image, VDI_FILL_LEFTOLDY, ram_word(image, VDI_FILL_LEFTDIRECTION));
            set_ram_word(image, VDI_FILL_LEFTDIRECTION, (int16_t)-ram_word(image, VDI_FILL_LEFTDIRECTION));
            set_ram_word(image, VDI_FILL_LEFTOLDY, (int16_t)(ram_word(image, VDI_FILL_LEFTOLDY) ^ VDI_FILL_DOWN_FLAG));
        }
    }

    /* the rest of the neighbour row, and the overhang to the RIGHT */
    while (word_above(image, VDI_FILL_OLDXRIGHT, VDI_FILL_NEWXRIGHT)) {
        advance(image, VDI_FILL_NEWXRIGHT, 1);
        set_ram_word(image, VDI_FILL_GOTSEED,
                     linea_get_seed(image, ram_word(image, VDI_FILL_NEWXRIGHT),
                                    (int16_t)(ram_word(image, VDI_FILL_OLDY) + ram_word(image, VDI_FILL_DIRECTION)),
                                    VDI_FILL_XLEFT, VDI_FILL_NEWXRIGHT, VDI_FILL_COLLISION));
    }
    while ((int16_t)(ram_word(image, VDI_FILL_OLDXRIGHT) + 1) < ram_word(image, VDI_FILL_NEWXRIGHT)
           && (ram_word(image, VDI_FILL_GOTSEED) || ram_word(image, VDI_FILL_COLLISION))) {
        set_ram_word(image, VDI_FILL_XRIGHT, ram_word(image, VDI_FILL_OLDXRIGHT));
        while (word_above(image, VDI_FILL_NEWXRIGHT, VDI_FILL_XRIGHT)) {
            advance(image, VDI_FILL_XRIGHT, 1);
            set_ram_word(image, VDI_FILL_GOTSEED,
                         linea_get_seed(image, ram_word(image, VDI_FILL_XRIGHT),
                                        (int16_t)(ram_word(image, VDI_FILL_OLDY) ^ VDI_FILL_DOWN_FLAG),
                                        VDI_FILL_XLEFT, VDI_FILL_XRIGHT, VDI_FILL_COLLISION));
        }
        set_ram_word(image, VDI_FILL_OLDXRIGHT, ram_word(image, VDI_FILL_NEWXRIGHT));
        if ((int16_t)(ram_word(image, VDI_FILL_NEWXRIGHT) + 1) < ram_word(image, VDI_FILL_XRIGHT)
            && (ram_word(image, VDI_FILL_GOTSEED) || ram_word(image, VDI_FILL_COLLISION))) {
            set_ram_word(image, VDI_FILL_NEWXRIGHT, ram_word(image, VDI_FILL_XRIGHT));
            advance(image, VDI_FILL_OLDY, ram_word(image, VDI_FILL_DIRECTION));
            set_ram_word(image, VDI_FILL_DIRECTION, (int16_t)-ram_word(image, VDI_FILL_DIRECTION));
            set_ram_word(image, VDI_FILL_OLDY, (int16_t)(ram_word(image, VDI_FILL_OLDY) ^ VDI_FILL_DOWN_FLAG));
        }
    }
}

/* Take the next record, round-robin from QPTR past the empty ones, into OLDY/OLDXLEFT/OLDXRIGHT —
 * crunching the queue when that took the top one. */
static void take_record(uint8_t *image)
{
    int16_t record;

    while (queued(image, ram_word(image, VDI_FILL_QPTR)) == (int16_t)VDI_FILL_EMPTY) {
        advance(image, VDI_FILL_QPTR, VDI_FILL_RECORD_WORDS);
        if (ram_word(image, VDI_FILL_QPTR) == ram_word(image, VDI_FILL_QTOP))
            set_ram_word(image, VDI_FILL_QPTR, ram_word(image, VDI_FILL_QBOTTOM));
    }
    record = ram_word(image, VDI_FILL_QPTR);
    set_ram_word(image, VDI_FILL_OLDY, queued(image, record));
    set_queued(image, record, (int16_t)VDI_FILL_EMPTY);
    set_ram_word(image, VDI_FILL_OLDXLEFT, queued(image, (int16_t)(record + 1)));
    set_ram_word(image, VDI_FILL_OLDXRIGHT, queued(image, (int16_t)(record + 2)));
    set_ram_word(image, VDI_FILL_QPTR, (int16_t)(record + VDI_FILL_RECORD_WORDS));
    if (ram_word(image, VDI_FILL_QPTR) == ram_word(image, VDI_FILL_QTOP))
        linea_crunch_queue(image);
}

/* The colour the fill works against: the seed pixel's own when intin[0] is negative (fill the region of
 * that colour), else intin[0]'s pen masked to the planes (fill up to that colour). 0 when intin[0] is
 * not below DEV_TAB[13], the colour count. */
static int choose_search_colour(uint8_t *image)
{
    int16_t index = intin_word(image, 0);
    uint16_t pen, mask;

    set_ram_word(image, VDI_FILL_SEARCH_COLOR, index);
    if (table_word(image, LINEA_DEV_TAB, VDI_DEV_TAB_COLOURS_INDEX) <= index)
        return 0;
    if (index < 0) {
        set_ram_word(image, VDI_FILL_SEARCH_COLOR, (int16_t)linea_get_pixel(image));
        set_ram_word(image, VDI_FILL_SEED_TYPE, SEED_THE_SEED_COLOUR);
        return 1;
    }
    pen = be16(image + word_entry(VDI_MAP_COL, index));
    mask = be16(image + word_entry(VDI_FILL_PEN_MASKS,
                                   (int32_t)table_word(image, LINEA_INQ_TAB, VDI_INQ_TAB_PLANES_INDEX) - 1));
    set_ram_word(image, VDI_FILL_SEARCH_COLOR, (int16_t)(pen & mask));
    set_ram_word(image, VDI_FILL_SEED_TYPE, SEED_UP_TO_A_COLOUR);
    return 1;
}

/* $fd08f4 — $a00f contour_fill: from ptsin[0], inside the clip rectangle, fill in the fill colour and
 * pattern every span reachable by rows (4-connected runs) — see `choose_search_colour` for which. The
 * seed's run is queued going DOWN and the walk starts from it going UP; each record taken is filled and
 * seeds its neighbours, until the queue empties, SEEDABORT answers nonzero or the queue fills. */
void linea_contour_fill(uint8_t *image)
{
    int16_t x = ptsin_word(image, 0);
    int16_t y;

    set_ram_word(image, VDI_FILL_XLEFT, x);
    set_ram_word(image, VDI_FILL_OLDY, ptsin_word(image, 1));
    y = ram_word(image, VDI_FILL_OLDY);
    if (x < ram_word(image, LINEA_XMINCL) || x > ram_word(image, LINEA_XMAXCL)
        || y < ram_word(image, LINEA_YMINCL) || y > ram_word(image, LINEA_YMAXCL))
        return;
    if (!choose_search_colour(image))
        return;
    set_fill_colour_bits(image);
    wr16(image + LINEA_LSTLIN, 0);
    set_ram_word(image, VDI_FILL_GOTSEED, linea_end_pts(image, ram_word(image, VDI_FILL_XLEFT),
                                                      ram_word(image, VDI_FILL_OLDY), VDI_FILL_OLDXLEFT,
                                                      VDI_FILL_OLDXRIGHT));
    set_ram_word(image, VDI_FILL_QBOTTOM, 0);
    set_ram_word(image, VDI_FILL_QPTR, 0);
    set_ram_word(image, VDI_FILL_QTOP, VDI_FILL_RECORD_WORDS);
    set_queued(image, 0, (int16_t)(ram_word(image, VDI_FILL_OLDY) | VDI_FILL_DOWN_FLAG));
    set_queued(image, 1, ram_word(image, VDI_FILL_OLDXLEFT));
    set_queued(image, 2, ram_word(image, VDI_FILL_OLDXRIGHT));
    set_ram_word(image, VDI_FILL_DONE, 0);
    if (ram_word(image, VDI_FILL_GOTSEED) == 0)
        return;
    for (;;) {
        seed_neighbours(image);
        if (ram_word(image, VDI_FILL_QTOP) == ram_word(image, VDI_FILL_QBOTTOM))
            return;
        take_record(image);
        if (ram_word(image, VDI_FILL_DONE))
            return;
        linea_fill_span(image, ram_word(image, VDI_FILL_OLDXLEFT), ram_word(image, VDI_FILL_OLDXRIGHT),
                        (int16_t)(ram_word(image, VDI_FILL_OLDY) & VDI_FILL_ROW_MASK));
    }
}

/* $fd08e0 — v_contourfill (opcode 103): $a00f with SEEDABORT at the ROM's never-abort routine. */
void vdi_v_contourfill(uint8_t *image)
{
    wr32(image + LINEA_SEEDABORT, LINEA_ROM_SEEDABORT_DEFAULT);
    linea_contour_fill(image);
}

/* $fd0fde — v_get_pixel (opcode 105): ptsin[0]'s pixel value in intout[0] and its VDI colour index in
 * intout[1], then contrl[4] = 2. intout[0] is stored BEFORE the planes are read, so an intout laid over
 * INQ_TAB[4] decides the index by the value just stored. */
void vdi_v_get_pixel(uint8_t *image)
{
    uint16_t value = (uint16_t)linea_get_pixel(image);
    uint32_t intout = linea_pointer(image, LINEA_INTOUT);
    int16_t planes;

    wr16(image + intout, value);
    planes = table_word(image, LINEA_INQ_TAB, VDI_INQ_TAB_PLANES_INDEX);
    if ((planes == MONO_PLANES && value != 0) || (planes == MEDIUM_PLANES && value == MEDIUM_LAST_PEN))
        value = REV_MAP_LAST_INDEX;
    wr16(image + intout + VDI_WORD_BYTES, be16(image + word_entry(VDI_REV_MAP_COL, (int16_t)value)));
    answer_words(image, GET_PIXEL_WORDS);
}
