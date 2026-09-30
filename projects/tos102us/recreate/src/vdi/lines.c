/* lines.c — POLYLINES and MARKERS: v_pline, v_pmarker, and the Alcyon geometry of a wide line.
 *
 *   $fcb9e0 v_pline     opcode 6: LN_MASK and COLBIT from the workstation, then a one-pixel polyline and its
 *                       arrowheads, or wline
 *   $fcba7a v_pmarker   opcode 7: each point's marker shape as solid one-pixel polylines through v_pline
 *   $fcca86 cir_dda     the quarter circle of a WS_LINE_WIDTH disc, rows in the device's aspect
 *   $fccba0 wline       each segment a filled quadrilateral WS_LINE_WIDTH across, and a disc at each joint
 *   $fccd92 perp_off    a direction turned into the quarter circle's point perpendicular to it
 *   $fccf4e do_circ     one disc of the quarter circle: a horizontal line a row, each clipped
 *   $fcd0fa arrow       the arrowheads WS_LINE_BEG/END ask for, drawn with the line pulled back under them
 *   $fcd196 do_arrow    one arrowhead: the first point far enough away, a filled triangle, the line shortened
 *
 * All Alcyon C. What a reader checks the C against:
 *   * A LENGTH THAT CROSSES AXES IS SCALED BY DEV_TAB's PIXEL SIZE, word by word (`muls.w` then `ext.l`: the
 *     product's LOW WORD, sign-extended, is what is divided), through smul_div elsewhere;
 *   * THE WIDE LINE AND THE ARROWHEAD BORROW THE FILL ATTRIBUTES (s_fa_attr / r_fa_attr): a solid outlined
 *     fill in the line colour — so every polygon plygn fills here is also outlined, which leaves the CALLER's
 *     contrl[1] at 5 after a wide segment (4 corners + plygn's closing point) and at the marker's last
 *     polyline's point count after v_pmarker;
 *   * wline and arrow leave the Line-A copies s_fa_attr made (PATPTR, PATMSK, MULTIFILL, LN_MASK) as they are,
 *     and v_pmarker leaves LINEA_CLIP set: the next dispatch re-copies them.
 */
#include <stdint.h>

#include "machine.h"
#include "addrs.h"
#include "host_slot.h"
#include "m68k_idioms.h"
#include "vdi/vdi.h"
#include "vdi/helpers.h"
#include "vdi/raster.h"
#include "vdi/fill.h"
#include "vdi/lines.h"

/* What v_pmarker borrows the line fields as: the solid style, the thin width, plain ends ($fcbaa6..$fcbaba),
 * and clipping on ($fcbabe). */
#define SOLID_STYLE_INDEX    0
#define CLIP_ON              1
#define ARROW_END_BIT        1u         /* WS_LINE_BEG/END: bit 0 asks for an arrowhead ($fcba60 and.w #1) */
/* do_circ's first quarter-circle row is the centre line; the rest go out a row at a time both ways. */
#define CENTRE_ROW           0
#define HALF_DIVISOR         2          /* every halving is `divs.w #2` */
#define SMALLEST_OFFSET_START 0x7fff    /* perp_off's best error so far starts at the largest word ($fccde4) */
#define LAST_ROW_FLOOR       1          /* ...and gives up at the last row once x is down to this ($fcce84) */

/* ---- small shapes the routines share ---------------------------------------------------------------- */

/* Word `index` of the quarter circle, the index a WORD doubled then sign-extended into the address
 * (`asl.w #1` / `ext.l`)... */
static inline uint32_t quarter_circle_row(int16_t index)
{
    return LINEA_Q_CIRCLE + word_index((uint16_t)index, VDI_WORD_BYTES);
}

static inline int16_t quarter_circle(const uint8_t *image, int16_t index)
{
    return ram_word(image, quarter_circle_row(index));
}

/* The device's pixel aspect, DEV_TAB[3] and [4], which every aspect scaling here reads fresh. */
static inline int16_t device_pixel_width(const uint8_t *image)
{
    return table_word(image, LINEA_DEV_TAB, VDI_DEV_TAB_PIXEL_WIDTH_INDEX);
}

static inline int16_t device_pixel_height(const uint8_t *image)
{
    return table_word(image, LINEA_DEV_TAB, VDI_DEV_TAB_PIXEL_HEIGHT_INDEX);
}

/* Does the workstation at `work` ask for an arrowhead at either end? */
static inline int asks_for_arrows(const uint8_t *image, uint32_t work)
{
    return ((work_word(image, work, WS_LINE_BEG) | work_word(image, work, WS_LINE_END)) & ARROW_END_BIT) != 0;
}

/* ...and the same word with its index SIGN-EXTENDED first (`vdi/vdi.h`'s `word_entry`), which parts from the
 * word doubling above from 16,384 on. */
static inline uint32_t quarter_circle_entry(int32_t index)
{
    return word_entry(LINEA_Q_CIRCLE, index);
}

/* `tst.w` / `bmi` / `neg.w`: -32768 stays itself. */
static inline int16_t word_abs(int16_t value)
{
    return value < 0 ? (int16_t)-(uint16_t)value : value;
}

/* `sub.w` / `blt` / `neg.w`: `high - low`, negated when `high` is the SMALLER — a true signed compare (N ^ V),
 * so a difference that overflows a word is left as it wrapped, negative or not. */
static inline int16_t word_distance(int16_t high, int16_t low)
{
    uint16_t difference = (uint16_t)((uint16_t)high - (uint16_t)low);

    return (int16_t)(high < low ? (uint16_t)-difference : difference);
}

/* `ext.l` then `divs.w`: a word's quotient by `divisor` (the register left unchanged on overflow). */
static inline int16_t word_quotient(int16_t dividend, int16_t divisor)
{
    return quotient_word(m68k_divs_w((uint32_t)(int32_t)dividend, (uint16_t)divisor));
}

/* `muls.w` / `ext.l` / `divs.w`: `value * multiplier`'s LOW WORD over `divisor`. */
static inline int16_t scaled_word(int16_t value, int16_t multiplier, int16_t divisor)
{
    return word_quotient((int16_t)m68k_muls_w((uint16_t)value, (uint16_t)multiplier), divisor);
}

static inline void store_point(uint8_t *image, uint32_t at, int16_t x, int16_t y)
{
    wr16(image + at, (uint16_t)x);
    wr16(image + at + VDI_POINT_Y, (uint16_t)y);
}

/* ================================================================================================
 * The quarter circle.
 * ============================================================================================= */

/* The circle's octant by the midpoint rule, radius `radius` = (width + 1) / 2: Q[y] = x out to the 45°
 * row, and the mirror Q[x] = y — the ROM's order, `lower` then `upper`, the later store winning where they
 * are the same word ($fccaee..$fccb26). */
/* The midpoint (Bresenham) circle's decision variable, kept ×4 so it stays integral: it starts at 3 - 2r,
 * and a step straight across adds 4·row + 6, a step that also moves in a row adds 4·(row - radius) + 10. */
#define MIDPOINT_START          3
#define MIDPOINT_RADIUS_WEIGHT  2
#define MIDPOINT_ROW_WEIGHT     4
#define MIDPOINT_ACROSS_STEP    6
#define MIDPOINT_DIAGONAL_STEP  10

static void circle_octants(uint8_t *image, int16_t radius)
{
    int16_t row = 0;
    int16_t error = (int16_t)(MIDPOINT_START - radius * MIDPOINT_RADIUS_WEIGHT);
    uint32_t upper = quarter_circle_row(radius);
    uint32_t lower = quarter_circle_row(0);

    while (row < radius) {
        wr16(image + upper, (uint16_t)row);
        wr16(image + lower, (uint16_t)radius);
        if (error < 0) {
            error = (int16_t)(error + row * MIDPOINT_ROW_WEIGHT + MIDPOINT_ACROSS_STEP);
        } else {
            error = (int16_t)(error + (row - radius) * MIDPOINT_ROW_WEIGHT + MIDPOINT_DIAGONAL_STEP);
            upper -= VDI_WORD_BYTES;
            radius--;
        }
        lower += VDI_WORD_BYTES;
        row++;
    }
    if (row == radius)
        wr16(image + quarter_circle_entry(row), (uint16_t)row);
}

/* $fcca86 — cir_dda: the quarter circle for WS_LINE_WIDTH. NUM_QC_LINES = width * pixel width / pixel
 * height / 2 + 1 rows, each the AVERAGE of the octant's rows it spans once the octant is squeezed into the
 * device's aspect — built in place, so a row reads octant words the rows before it have not yet
 * overwritten. A pixel height of 0, or a row that spans none (a device wider than it is tall), divides by
 * zero: vector 5 on the 68000. */
void vdi_cir_dda(uint8_t *image)
{
    int16_t width = work_word(image, current_work(image), WS_LINE_WIDTH);
    int16_t pixel_width = device_pixel_width(image);
    int16_t pixel_height = device_pixel_height(image);
    int16_t start = 0, line;
    uint32_t out = LINEA_Q_CIRCLE;

    set_ram_word(image, LINEA_NUM_QC_LINES,
                 (uint16_t)(word_quotient(scaled_word(width, pixel_width, pixel_height), HALF_DIVISOR) + 1));
    set_ram_word(image, LINEA_LINE_CW, (uint16_t)width);
    circle_octants(image, word_quotient((int16_t)(width + 1), HALF_DIVISOR));

    for (line = 0; line < ram_word(image, LINEA_NUM_QC_LINES); line++) {
        /* The octant row under the line's far edge, line + 1/2 in the device's aspect, worked doubled. */
        int16_t end = word_quotient(scaled_word((int16_t)(line * HALF_DIVISOR + 1), pixel_height, pixel_width),
                                    HALF_DIVISOR);
        int16_t sum = 0, row;
        uint32_t at = quarter_circle_row(start);

        for (row = start; end >= row; row++, at += VDI_WORD_BYTES)
            sum = (int16_t)(sum + ram_word(image, at));
        wr16(image + out, (uint16_t)word_quotient(sum, (int16_t)(end - start + 1)));
        out += VDI_WORD_BYTES;
        start = (int16_t)(end + 1);
    }
}

/* $fccd92 — perp_off: the offset (x, y) at `x_at` / `y_at` turned into the quarter-circle point (Q[row], row)
 * most nearly perpendicular to it — the one whose cross product with it, Q[row]·|y| - row·|x| in WORDS, is
 * smallest in magnitude, ties going to the point nearer the diagonal — and folded back into the offset's
 * own quadrant in place. The walk runs along the circle's edge from (Q[0], 0) and stops at the first point
 * no better than the last.
 *
 * A first cross product of exactly 32,767 is compared with the two best-point locals BEFORE anything is
 * stored in them — stack garbage in the ROM; this C starts them at (0, 0). */
void vdi_perp_off(uint8_t *image, uint32_t x_at, uint32_t y_at)
{
    int16_t x = ram_word(image, x_at), y = ram_word(image, y_at);
    int16_t quadrant = x >= 0 ? (y >= 0 ? 1 : 4) : (y >= 0 ? 2 : 3);
    int16_t direction_local[2];
    uint32_t direction = host_slot_claim(VDI_PERP_DIRECTION, direction_local);
    int16_t across, along, best = SMALLEST_OFFSET_START, best_x = 0, best_row = 0;
    int16_t edge_x = quarter_circle(image, CENTRE_ROW), row = CENTRE_ROW;

    _Static_assert(sizeof direction_local == HOST_SLOT_VDI_PERP_DIRECTION_BYTES, "two words");
    vdi_quad_xform(image, quadrant, ram_word(image, x_at), ram_word(image, y_at), direction, direction + VDI_WORD_BYTES);
    across = ram_word(image, direction);
    along = ram_word(image, direction + VDI_WORD_BYTES);
    host_slot_release(VDI_PERP_DIRECTION);
    for (;;) {
        int16_t error = word_distance((int16_t)m68k_muls_w((uint16_t)edge_x, (uint16_t)along),
                                      (int16_t)m68k_muls_w((uint16_t)row, (uint16_t)across));

        if (error > best)
            break;
        if (error == best && word_distance(edge_x, row) >= word_distance(best_x, best_row))
            break;
        best = error;
        best_x = edge_x;
        best_row = row;
        if (row == (int16_t)(ram_word(image, LINEA_NUM_QC_LINES) - 1)) {
            if (edge_x == LAST_ROW_FLOOR)
                break;
            edge_x--;
        } else if (ram_word(image, quarter_circle_entry((int32_t)row + 1)) >= (int16_t)(edge_x - 1)) {
            row++;
            edge_x = ram_word(image, quarter_circle_entry(row));
        } else {
            edge_x--;
        }
    }
    vdi_quad_xform(image, quadrant, best_x, best_row, x_at, y_at);
}

/* The row `row` of a disc of the quarter circle at (x, y), `row` above or below it: X1..X2 on Y1 = Y2,
 * drawn through $a003 if any of it survives clip_line — which is asked whatever CLIP says ($fccf66..). */
static void disc_row(uint8_t *image, int16_t x, int16_t y, int16_t index)
{
    uint32_t half = quarter_circle_row(index);

    wr16(image + LINEA_X1, (uint16_t)(x - ram_word(image, half)));
    wr16(image + LINEA_X2, (uint16_t)(ram_word(image, half) + x));
    wr16(image + LINEA_Y2, (uint16_t)y);
    wr16(image + LINEA_Y1, (uint16_t)y);
    if (vdi_clip_line(image))
        linea_line(image);
}

/* $fccf4e — do_circ: the disc at (x, y), NUM_QC_LINES rows each way, centre row first, then above and below
 * a row at a time. Nothing when NUM_QC_LINES is not positive. */
void vdi_do_circ(uint8_t *image, int16_t x, int16_t y)
{
    int16_t row;

    if (ram_word(image, LINEA_NUM_QC_LINES) <= 0)
        return;
    disc_row(image, x, y, CENTRE_ROW);
    for (row = 1; row < ram_word(image, LINEA_NUM_QC_LINES); row++) {
        disc_row(image, x, (int16_t)(y - row), row);
        disc_row(image, x, (int16_t)(y + row), row);
    }
}

/* ================================================================================================
 * The wide line.
 * ============================================================================================= */

/* The offset from a wide segment's centre line to one of its long sides, for the segment (dx, dy): the
 * quarter circle's widest row or its centre row for an upright or a flat segment, else the direction
 * turned through 90° in the device's aspect and handed to perp_off in `offset` (x, then y). */
static void segment_offset(uint8_t *image, int16_t dx, int16_t dy, uint32_t offset)
{
    int16_t pixel_width, pixel_height, turned_x;

    if (dx == 0) {
        store_point(image, offset, quarter_circle(image, CENTRE_ROW), 0);
        return;
    }
    if (dy == 0) {
        store_point(image, offset, 0, (int16_t)(ram_word(image, LINEA_NUM_QC_LINES) - 1));
        return;
    }
    pixel_width = device_pixel_width(image);
    pixel_height = device_pixel_height(image);
    turned_x = vdi_smul_div((int16_t)-dy, pixel_height, pixel_width);
    store_point(image, offset, turned_x, vdi_smul_div(dx, pixel_width, pixel_height));
    vdi_perp_off(image, offset, offset + VDI_WORD_BYTES);
}

/* Where a wide segment runs, and the frame words it is built in. */
struct segment {
    int16_t x0, y0, x1, y1;
    uint32_t offset;            /* the offset's two words */
    uint32_t corners;           /* the quadrilateral plygn fills */
    uint32_t caller_points;     /* LINEA_PTSIN as wline found it, put back after each fill */
};

/* The segment as the quadrilateral its offset makes, filled through plygn over its corners — LINEA_PTSIN
 * pointed at them for the call and back at the caller's points after. */
static void fill_segment(uint8_t *image, const struct segment *segment)
{
    int16_t x0 = segment->x0, y0 = segment->y0, x1 = segment->x1, y1 = segment->y1;
    int16_t across = ram_word(image, segment->offset), down = ram_word(image, segment->offset + VDI_WORD_BYTES);
    uint32_t corners = segment->corners;

    set_contrl_word(image, CONTRL_N_PTSIN, VDI_WIDE_CORNER_COUNT);
    wr32(image + LINEA_PTSIN, corners);
    store_point(image, corners, (int16_t)(x0 + across), (int16_t)(y0 + down));
    store_point(image, corners + VDI_POINT_BYTES, (int16_t)(x0 - across), (int16_t)(y0 - down));
    store_point(image, corners + 2 * VDI_POINT_BYTES, (int16_t)(x1 - across), (int16_t)(y1 - down));
    store_point(image, corners + 3 * VDI_POINT_BYTES, (int16_t)(x1 + across), (int16_t)(y1 + down));
    vdi_plygn(image);
    wr32(image + LINEA_PTSIN, segment->caller_points);
}

/* $fccba0 — wline: contrl[1] points WS_LINE_WIDTH wide, when there are at least two — the quarter circle
 * rebuilt if the width changed, the arrowheads drawn first (which pull the ends in), then in the fill
 * attributes' solid outline: a disc at the start when WS_LINE_BEG was nonzero, and per segment its filled
 * quadrilateral and a disc at its far end — at every joint, and at the last point when WS_LINE_END was
 * nonzero. A segment of no length is skipped, its end not taken as the next start (it is the same point). */
void vdi_wline(uint8_t *image)
{
    int16_t points = contrl_word(image, CONTRL_N_PTSIN);
    uint32_t work, cursor;
    int16_t index;
    int16_t offset_local[2];
    uint8_t corners_local[(VDI_WIDE_CORNER_COUNT + 1) * VDI_POINT_BYTES];      /* the corners and the closing point */
    struct segment segment;

    _Static_assert(sizeof offset_local == HOST_SLOT_VDI_WIDE_OFFSET_BYTES, "two words");
    _Static_assert(sizeof corners_local == HOST_SLOT_VDI_WIDE_CORNERS_BYTES, "the corners' host slot");
    if (points < 2)
        return;
    work = current_work(image);
    if (work_word(image, work, WS_LINE_WIDTH) != ram_word(image, LINEA_LINE_CW))
        vdi_cir_dda(image);
    if (asks_for_arrows(image, work))
        vdi_arrow(image);
    vdi_s_fa_attr(image);
    cursor = segment.caller_points = linea_pointer(image, LINEA_PTSIN);
    segment.x0 = caller_word(image, cursor);
    segment.y0 = caller_word(image, cursor + VDI_POINT_Y);
    cursor += VDI_POINT_BYTES;
    if (ram_word(image, LINEA_GDP_SAVED_BEG_STYLE))
        vdi_do_circ(image, segment.x0, segment.y0);
    segment.offset = host_slot_claim(VDI_WIDE_OFFSET, offset_local);
    segment.corners = host_slot_claim(VDI_WIDE_CORNERS, corners_local);
    for (index = 1; index < points; index++, cursor += VDI_POINT_BYTES) {
        int16_t dx, dy;

        segment.x1 = caller_word(image, cursor);
        segment.y1 = caller_word(image, cursor + VDI_POINT_Y);
        dx = (int16_t)(segment.x1 - segment.x0);
        dy = (int16_t)(segment.y1 - segment.y0);
        if (dx == 0 && dy == 0)
            continue;
        segment_offset(image, dx, dy, segment.offset);
        fill_segment(image, &segment);
        if (index < points - 1 || ram_word(image, LINEA_GDP_SAVED_END_STYLE))
            vdi_do_circ(image, segment.x1, segment.y1);
        segment.x0 = segment.x1;
        segment.y0 = segment.y1;
    }
    host_slot_release(VDI_WIDE_CORNERS);
    host_slot_release(VDI_WIDE_OFFSET);
    vdi_r_fa_attr(image);
}

/* ================================================================================================
 * The arrowheads.
 * ============================================================================================= */

/* The arrowhead's length along the line: 8 for a one-pixel line, else three widths less one. */
static int16_t arrow_length(const uint8_t *image)
{
    int16_t width = work_word(image, current_work(image), WS_LINE_WIDTH);

    return width == VDI_THIN_LINE_WIDTH ? VDI_ARROW_LENGTH_THIN
                               : (int16_t)(m68k_muls_w((uint16_t)width, VDI_ARROW_LENGTH_PER_WIDTH) - 1);
}

/* `value` * `share` / `length`, as a fraction of VDI_ARROW_SCALE, then of `extent`: the ROM's two smul_divs. */
static int16_t along(int16_t extent, int16_t value, int16_t share, int16_t length)
{
    return vdi_smul_div(extent, vdi_smul_div(value, share, length), VDI_ARROW_SCALE);
}

/* Where do_arrow's walk stopped: the end point, the point reached and the step between points, the
 * arrowhead's length, and the direction and distance to the point reached (y in x's aspect). */
struct arrow_walk {
    uint32_t point_at, reached, stride;
    int16_t length, dx, dy, distance;
};

/* The arrowhead for a walk that reached a point far enough away: filled through plygn with contrl[1] = 3
 * (the caller's put back), then the end point pulled back to its base and every point walked past moved onto
 * it. Out of line so the walk, which is all a too-short line runs, saves only the registers it uses. */
static __attribute__((noinline)) void draw_arrowhead(uint8_t *image, const struct arrow_walk *walk)
{
    uint32_t point_at = walk->point_at, reached = walk->reached;
    int16_t pixel_width = device_pixel_width(image);
    int16_t pixel_height = device_pixel_height(image);
    int16_t half = word_quotient(walk->length, HALF_DIVISOR);
    int16_t back_x = along(walk->length, walk->dx, VDI_ARROW_SCALE, walk->distance);
    int16_t back_y = along(walk->length, walk->dy, VDI_ARROW_SCALE, walk->distance);
    int16_t spread_x = along(half, walk->dy, -VDI_ARROW_SCALE, walk->distance);
    int16_t spread_y = along(half, walk->dx, VDI_ARROW_SCALE, walk->distance);
    int16_t saved_points;
    uint8_t triangle_local[(VDI_ARROW_CORNERS + 1) * VDI_POINT_BYTES];         /* the head and the closing point */
    uint32_t triangle, caller_points;

    _Static_assert(sizeof triangle_local == HOST_SLOT_VDI_ARROW_TRIANGLE_BYTES, "the arrowhead's host slot");
    back_y = vdi_smul_div(back_y, pixel_width, pixel_height);
    spread_y = vdi_smul_div(spread_y, pixel_width, pixel_height);

    saved_points = contrl_word(image, CONTRL_N_PTSIN);
    set_contrl_word(image, CONTRL_N_PTSIN, VDI_ARROW_CORNERS);
    /* Each corner re-reads the end point, after contrl[1] is stored — the ROM's order. */
    triangle = host_slot_claim(VDI_ARROW_TRIANGLE, triangle_local);
    wr16(image + triangle, (uint16_t)(ram_word(image, point_at) + spread_x - back_x));
    wr16(image + triangle + VDI_POINT_Y, (uint16_t)(ram_word(image, point_at + VDI_POINT_Y) + spread_y - back_y));
    wr16(image + triangle + VDI_POINT_BYTES, (uint16_t)(ram_word(image, point_at) - spread_x - back_x));
    wr16(image + triangle + VDI_POINT_BYTES + VDI_POINT_Y, (uint16_t)(ram_word(image, point_at + VDI_POINT_Y) - spread_y - back_y));
    copy_point(image, triangle + 2 * VDI_POINT_BYTES, point_at);
    caller_points = linea_pointer(image, LINEA_PTSIN);
    wr32(image + LINEA_PTSIN, triangle);
    vdi_plygn(image);
    wr32(image + LINEA_PTSIN, caller_points);
    host_slot_release(VDI_ARROW_TRIANGLE);
    set_contrl_word(image, CONTRL_N_PTSIN, (uint16_t)saved_points);

    add_ram_word(image, point_at, (uint16_t)-back_x);
    add_ram_word(image, point_at + VDI_POINT_Y, (uint16_t)-back_y);
    for (reached -= walk->stride; reached != point_at; reached -= walk->stride) {
        copy_point(image, reached, point_at);
    }
}

/* $fcd196 — do_arrow: an arrowhead at the point at `point_at`, pointing out of the line. It walks the
 * points from there `step` words at a time (contrl[1] - 1 of them at most) to the first whose distance —
 * y scaled into x's aspect — is at least the arrowhead's length; none, and nothing is drawn.
 *
 * With fewer than two points the walk tests a length it never computed — stack garbage in the ROM; its
 * callers only arrive so from v_pline's one-pixel path, and no case stages it. */
void vdi_do_arrow(uint8_t *image, uint32_t point_at, int16_t step)
{
    struct arrow_walk walk = {.point_at = point_at, .reached = point_at,
                              .stride = word_index((uint16_t)step, VDI_WORD_BYTES), .length = arrow_length(image)};
    int16_t points = contrl_word(image, CONTRL_N_PTSIN), walked;
    int16_t pixel_width = device_pixel_width(image);
    int16_t pixel_height = device_pixel_height(image);

    for (walked = 1; walked < points; walked++) {
        walk.reached += walk.stride;
        walk.dx = (int16_t)(ram_word(image, point_at) - ram_word(image, walk.reached));
        walk.dy = vdi_smul_div((int16_t)(ram_word(image, point_at + VDI_POINT_Y) - ram_word(image, walk.reached + VDI_POINT_Y)),
                               pixel_height, pixel_width);
        walk.distance = vdi_vec_len(word_abs(walk.dx), word_abs(walk.dy));
        if (walk.distance >= walk.length)
            break;
    }
    if (walk.distance >= walk.length)
        draw_arrowhead(image, &walk);
}

/* $fcd0fa — arrow: in the fill attributes' solid outline, an arrowhead at the first point pointing back
 * along the line when WS_LINE_BEG asks for one, and at the last pointing forward when WS_LINE_END does. The
 * end arrowhead is found from the ORIGINAL first point — put back for it — and the first point is then left
 * where the start arrowhead moved it. */
void vdi_arrow(uint8_t *image)
{
    uint32_t points_at;
    int16_t first_x, first_y, moved_x, moved_y;

    vdi_s_fa_attr(image);
    points_at = linea_pointer(image, LINEA_PTSIN);
    first_x = moved_x = ram_word(image, points_at);
    first_y = moved_y = ram_word(image, points_at + VDI_POINT_Y);
    if (ram_word(image, LINEA_GDP_SAVED_BEG_STYLE) & ARROW_END_BIT) {
        vdi_do_arrow(image, points_at, VDI_ARROW_STEP_FORWARD);
        points_at = linea_pointer(image, LINEA_PTSIN);
        moved_x = ram_word(image, points_at);
        moved_y = ram_word(image, points_at + VDI_POINT_Y);
    }
    if (ram_word(image, LINEA_GDP_SAVED_END_STYLE) & ARROW_END_BIT) {
        store_point(image, points_at, first_x, first_y);
        vdi_do_arrow(image, points_at + word_index((uint16_t)contrl_word(image, CONTRL_N_PTSIN), VDI_POINT_BYTES) - VDI_POINT_BYTES,
                     VDI_ARROW_STEP_BACKWARD);
        points_at = linea_pointer(image, LINEA_PTSIN);
        store_point(image, points_at, moved_x, moved_y);
    }
    vdi_r_fa_attr(image);
}

/* ================================================================================================
 * The two functions.
 * ============================================================================================= */

/* The LN_MASK WS_LINE_INDEX names: VDI_LINE_STYLES' entry below VDI_LINE_STYLE_USER — the index SIGN-EXTENDED
 * before it is doubled (`movea.w` / `adda.l`), so a negative one reads below the table — else WS_UD_LS. */
static uint16_t line_style_mask(const uint8_t *image, uint32_t work)
{
    int16_t style = work_word(image, work, WS_LINE_INDEX);

    return style < VDI_LINE_STYLE_USER ? be16(image + word_entry(VDI_LINE_STYLES, style))
                                       : be16(image + work + WS_UD_LS);
}

/* Inlined into v_pline, as the ROM spells it there, and linked out of line for the rounded box's outline. */
inline __attribute__((always_inline)) void set_line_attributes(uint8_t *image, uint32_t work)
{
    set_ram_word(image, LINEA_LN_MASK, line_style_mask(image, work));
    set_colour_bits(image, (uint16_t)work_word(image, work, WS_LINE_COLOR));
}

/* $fcb9e0 — v_pline (opcode 6): LN_MASK from WS_LINE_INDEX — the ROM's style table below
 * VDI_LINE_STYLE_USER, a negative index reading the words before it — or WS_UD_LS; COLBIT from
 * WS_LINE_COLOR; then a width of exactly 1 is a polyline with any arrowheads drawn over it, and any other
 * width is wline. */
void vdi_v_pline(uint8_t *image)
{
    uint32_t work = current_work(image);

    set_line_attributes(image, work);
    if (work_word(image, work, WS_LINE_WIDTH) != VDI_THIN_LINE_WIDTH) {
        vdi_wline(image);
        return;
    }
    vdi_polyline(image);
    work = current_work(image);
    if (asks_for_arrows(image, work))
        vdi_arrow(image);
}

/* The five line fields v_pmarker borrows, as the ROM saves them into its frame: spelt out rather than walked
 * through a table of offsets, which costs a marker a loop the ROM never runs. */
struct line_fields {
    int16_t index, colour, width, begin, end;
};

static void save_line_fields(const uint8_t *image, uint32_t work, struct line_fields *saved)
{
    saved->index = work_word(image, work, WS_LINE_INDEX);
    saved->colour = work_word(image, work, WS_LINE_COLOR);
    saved->width = work_word(image, work, WS_LINE_WIDTH);
    saved->begin = work_word(image, work, WS_LINE_BEG);
    saved->end = work_word(image, work, WS_LINE_END);
}

static void restore_line_fields(uint8_t *image, uint32_t work, const struct line_fields *saved)
{
    wr16(image + work + WS_LINE_INDEX, (uint16_t)saved->index);
    wr16(image + work + WS_LINE_COLOR, (uint16_t)saved->colour);
    wr16(image + work + WS_LINE_WIDTH, (uint16_t)saved->width);
    wr16(image + work + WS_LINE_BEG, (uint16_t)saved->begin);
    wr16(image + work + WS_LINE_END, (uint16_t)saved->end);
}

/* One polyline of a marker shape, its `count` offsets at `shape` scaled and placed at (x, y) in `points`,
 * drawn through v_pline with contrl[1] = `count` — left so. Answers where the shape goes on. */
static uint32_t marker_polyline(uint8_t *image, uint32_t shape, int16_t x, int16_t y, int16_t scale, uint32_t points)
{
    int16_t count = ram_word(image, shape), point;
    uint32_t at = points;

    shape += VDI_WORD_BYTES;
    set_contrl_word(image, CONTRL_N_PTSIN, (uint16_t)count);
    for (point = 0; point < count; point++, at += VDI_POINT_BYTES, shape += VDI_POINT_BYTES) {
        store_point(image, at, (int16_t)(m68k_muls_w(be16(image + shape), (uint16_t)scale) + x),
                    (int16_t)(m68k_muls_w(be16(image + shape + VDI_POINT_Y), (uint16_t)scale) + y));
    }
    vdi_v_pline(image);
    return shape;
}

/* $fcba7a — v_pmarker (opcode 7): at each of contrl[1] points, the shape WS_MARK_INDEX names, scaled by
 * WS_MARK_SCALE, as one-pixel solid polylines in WS_MARK_COLOR, clipped (LINEA_CLIP set, and left so) —
 * the line fields borrowed for it and put back after. contrl[1] is left at the last polyline's count. */
void vdi_v_pmarker(uint8_t *image)
{
    uint32_t work = current_work(image);
    struct line_fields saved;
    int16_t scale, markers, marker;
    uint32_t caller_points, cursor, points;
    uint8_t points_local[VDI_MARKER_POINTS_MAX * VDI_POINT_BYTES];            /* a marker polyline's points */

    _Static_assert(sizeof points_local == HOST_SLOT_VDI_MARKER_POINTS_BYTES, "the marker points' host slot");
    save_line_fields(image, work, &saved);
    wr16(image + work + WS_LINE_INDEX, SOLID_STYLE_INDEX);
    wr16(image + work + WS_LINE_COLOR, be16(image + work + WS_MARK_COLOR));
    wr16(image + work + WS_LINE_WIDTH, VDI_THIN_LINE_WIDTH);
    wr16(image + work + WS_LINE_BEG, VDI_LINE_END_SQUARE);
    wr16(image + work + WS_LINE_END, VDI_LINE_END_SQUARE);
    wr16(image + LINEA_CLIP, CLIP_ON);
    scale = work_word(image, work, WS_MARK_SCALE);
    markers = contrl_word(image, CONTRL_N_PTSIN);
    caller_points = cursor = linea_pointer(image, LINEA_PTSIN);
    points = host_slot_claim(VDI_MARKER_POINTS, points_local);
    wr32(image + LINEA_PTSIN, points);
    for (marker = 0; marker < markers; marker++, cursor += VDI_POINT_BYTES) {
        int16_t x = ram_word(image, cursor), y = ram_word(image, cursor + VDI_POINT_Y);
        int16_t index = work_word(image, current_work(image), WS_MARK_INDEX);
        uint32_t shape = be32(image + table_entry(VDI_MARKER_SHAPES, index, VDI_MARKER_SHAPE_ENTRY_BYTES));
        int16_t polylines = ram_word(image, shape), polyline;

        shape += VDI_WORD_BYTES;
        for (polyline = 0; polyline < polylines; polyline++)
            shape = marker_polyline(image, shape, x, y, scale, points);
    }
    wr32(image + LINEA_PTSIN, caller_points);
    host_slot_release(VDI_MARKER_POINTS);
    restore_line_fields(image, current_work(image), &saved);
}
