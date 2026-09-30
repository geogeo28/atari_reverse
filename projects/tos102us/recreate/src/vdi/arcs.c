/* arcs.c — ARCS, ELLIPSES and ROUNDED BOXES: the workers of the GDP's curve arms.
 *
 *   $fcc914 clc_pts   the point at LINEA_GDP_ANGLE on the ellipse (XC, YC, XRAD, YRAD) into ptsin word `point`
 *   $fcc79e clc_arc   the curve: nothing when clipping is on and its box misses the clip rectangle, else
 *                     N_STEPS + 1 points from BEG_ANG to END_ANG (a pie's centre after them), through
 *                     v_pline for an arc, plygn for everything else
 *   $fcc62e gdp_arc   GDP 2/3: the angles from intin, the radius from ptsin[6], the y radius by the aspect
 *   $fcc714 gdp_ell   GDP 6/7: the angles from intin, the centre and both radii from ptsin[0..3]
 *   $fcc284 gdp_rbox  GDP 8/9: the box's corners sorted into X1..Y2, a quarter-round of five points at each,
 *                     outlined (8) in the line attributes — polyline or wline — or filled through plygn (9)
 *
 * All Alcyon C, and it keeps every value in the arc scratch at its absolute address (`vdi/linea.h`): the ROM
 * re-reads each one where its C names it — the centre at every store of a rounded-box corner — so the C does
 * too, and a PTSIN laid over the scratch reads what the ROM would. What a reader checks the C against:
 *   * the ANGLES ARE NOT NORMALISED: gdp_arc/gdp_ell take intin's as they come, only the sweep is lifted by a
 *     turn when negative; isin/icos bring an angle over 3600 down, and a negative one reads below their table;
 *   * the sweep is split by smul_div(DEL_ANG, step, N_STEPS), each point from START — and the LAST point is at
 *     END_ANG itself, not at START + DEL_ANG (the two differ when the arm's end angle is past a turn);
 *   * clc_arc leaves contrl[1] at the point count and N_STEPS one up for a pie; plygn and v_pline read them;
 *   * the rounded box's quarter-round is built in ptsin[0..9] and its upper-right corner written OVER it last.
 */
#include <stdint.h>

#include "machine.h"
#include "addrs.h"
#include "vdi/vdi.h"
#include "vdi/helpers.h"
#include "vdi/attributes.h"
#include "vdi/fill.h"
#include "vdi/lines.h"
#include "vdi/arcs.h"

/* The quarter-round's three inner points, at these angles between 90 and 0 degrees ($fcc350, $fcc394, $fcc3d8). */
#define ROUND_ANGLE_UPPER     675
#define ROUND_ANGLE_MIDDLE    450
#define ROUND_ANGLE_LOWER     225
#define ROUND_WORDS           (VDI_RBOX_CORNER_POINTS * VDI_POINT_WORDS)
#define HALF_DIVISOR          2          /* the box's half-sizes, `divs.w #2` */

static inline int16_t word_sum(int16_t left, int16_t right)
{
    return (int16_t)(uint16_t)((uint16_t)left + (uint16_t)right);
}

static inline int16_t word_difference(int16_t left, int16_t right)
{
    return (int16_t)(uint16_t)((uint16_t)left - (uint16_t)right);
}

/* ================================================================================================
 * The curve.
 * ============================================================================================= */

/* $fcc914 — clc_pts: the point at ANGLE on the ellipse, (XC + XRAD cos, YC - YRAD sin), into ptsin words
 * `point` and `point` + 1 — PTSIN read once, the scratch re-read after the x is stored. */
void vdi_clc_pts(uint8_t *image, int16_t point)
{
    uint32_t at = word_entry(linea_pointer(image, LINEA_PTSIN), point);
    int16_t along = vdi_smul_div(vdi_icos(image, ram_word(image, LINEA_GDP_ANGLE)), ram_word(image, LINEA_GDP_XRAD),
                                 VDI_TRIG_SCALE);

    set_ram_word(image, at, (uint16_t)word_sum(along, ram_word(image, LINEA_GDP_XC)));
    along = vdi_smul_div(vdi_isin(image, ram_word(image, LINEA_GDP_ANGLE)), ram_word(image, LINEA_GDP_YRAD),
                         VDI_TRIG_SCALE);
    set_ram_word(image, at + VDI_POINT_Y, (uint16_t)word_difference(ram_word(image, LINEA_GDP_YC), along));
}

/* The trivial reject: the ellipse's bounding box wholly left of, right of, above or below the clip rectangle
 * (word sums, signed compares, the edges inside). */
static int misses_the_clip(const uint8_t *image)
{
    int16_t xc = ram_word(image, LINEA_GDP_XC), xrad = ram_word(image, LINEA_GDP_XRAD);
    int16_t yc = ram_word(image, LINEA_GDP_YC), yrad = ram_word(image, LINEA_GDP_YRAD);

    return word_sum(xc, xrad) < ram_word(image, LINEA_XMINCL) || word_difference(xc, xrad) > ram_word(image, LINEA_XMAXCL)
           || word_sum(yc, yrad) < ram_word(image, LINEA_YMINCL) || word_difference(yc, yrad) > ram_word(image, LINEA_YMAXCL);
}

/* contrl[5], re-read through the held CONTRL at every test as the ROM's `cmpi.w #n,10(a5)` does. */
static inline int16_t gdp_number(const uint8_t *image, uint32_t contrl)
{
    return ram_word(image, contrl + CONTRL_SUBFUNCTION);
}

/* contrl[1] = N_STEPS + 1, the curve's points (and a pie's centre). */
static void store_point_count(uint8_t *image, uint32_t contrl)
{
    set_ram_word(image, contrl + CONTRL_N_PTSIN, (uint16_t)word_sum(ram_word(image, LINEA_GDP_N_STEPS), 1));
}

/* clc_arc past its trivial reject, the ptsin word index stepped a point at a time ($fcc832 `addq #2`). CONTRL
 * and PTSIN are loaded once, after the points (`movea.l` into A5/A4).
 * Kept out of line so the reject's early return saves none of the registers the curve's loop needs. */
static __attribute__((noinline)) void draw_arc(uint8_t *image)
{
    int16_t step, point = 0;
    uint32_t contrl, ptsin;

    set_ram_word(image, LINEA_GDP_ANGLE, ram_uword(image, LINEA_GDP_BEG_ANG));
    set_ram_word(image, LINEA_GDP_START, ram_uword(image, LINEA_GDP_ANGLE));
    vdi_clc_pts(image, point);
    for (step = 1; step < ram_word(image, LINEA_GDP_N_STEPS); step++) {
        int16_t swept = vdi_smul_div(ram_word(image, LINEA_GDP_DEL_ANG), step, ram_word(image, LINEA_GDP_N_STEPS));

        point = word_sum(point, VDI_POINT_WORDS);
        set_ram_word(image, LINEA_GDP_ANGLE, (uint16_t)word_sum(swept, ram_word(image, LINEA_GDP_START)));
        vdi_clc_pts(image, point);
    }
    point = word_sum(point, VDI_POINT_WORDS);
    set_ram_word(image, LINEA_GDP_ANGLE, ram_uword(image, LINEA_GDP_END_ANG));
    vdi_clc_pts(image, point);

    contrl = linea_pointer(image, LINEA_CONTRL);
    ptsin = linea_pointer(image, LINEA_PTSIN);
    store_point_count(image, contrl);
    if (gdp_number(image, contrl) == VDI_GDP_PIE || gdp_number(image, contrl) == VDI_GDP_ELLIPTICAL_PIE) {
        add_ram_word(image, LINEA_GDP_N_STEPS, 1);
        point = word_sum(point, VDI_POINT_WORDS);
        set_ram_word(image, word_entry(ptsin, point), ram_uword(image, LINEA_GDP_XC));
        set_ram_word(image, word_entry(ptsin, point) + VDI_POINT_Y, ram_uword(image, LINEA_GDP_YC));
        store_point_count(image, contrl);
    }
    if (gdp_number(image, contrl) == VDI_GDP_ARC || gdp_number(image, contrl) == VDI_GDP_ELLIPTICAL_ARC)
        vdi_v_pline(image);
    else
        vdi_plygn(image);
}

/* $fcc79e — clc_arc. */
void vdi_clc_arc(uint8_t *image)
{
    if (ram_word(image, LINEA_CLIP) != 0 && misses_the_clip(image))
        return;
    draw_arc(image);
}

/* ================================================================================================
 * The arms' workers.
 * ============================================================================================= */

/* BEG_ANG and END_ANG from intin[0] and [1] (INTIN read once), and DEL_ANG their difference, a turn added
 * when it is negative — gdp_arc's and gdp_ell's common opening ($fcc636..$fcc662, $fcc71c..$fcc748). */
static void angles_from_intin(uint8_t *image)
{
    uint32_t intin = linea_pointer(image, LINEA_INTIN);

    set_ram_word(image, LINEA_GDP_BEG_ANG, ram_uword(image, intin));
    set_ram_word(image, LINEA_GDP_END_ANG, ram_uword(image, intin + VDI_WORD_BYTES));
    set_ram_word(image, LINEA_GDP_DEL_ANG, (uint16_t)word_difference(ram_word(image, LINEA_GDP_END_ANG),
                                                                     ram_word(image, LINEA_GDP_BEG_ANG)));
    if (ram_word(image, LINEA_GDP_DEL_ANG) < 0)
        add_ram_word(image, LINEA_GDP_DEL_ANG, VDI_TENTHS_PER_TURN);
}

/* The ptsin index of the arc's radius: the fourth point's x. */
#define ARC_RADIUS_WORD       6          /*                                     ($fcc670 12(a5))    */

/* $fcc62e — gdp_arc: a circular arc or pie, PTSIN held from the radius's read to the centre's. */
void vdi_gdp_arc(uint8_t *image)
{
    uint32_t ptsin;

    angles_from_intin(image);
    ptsin = linea_pointer(image, LINEA_PTSIN);
    set_ram_word(image, LINEA_GDP_XRAD, ram_uword(image, word_entry(ptsin, ARC_RADIUS_WORD)));
    set_ram_word(image, LINEA_GDP_YRAD, (uint16_t)vdi_aspect_y_radius(image));
    vdi_clc_nsteps(image);
    set_ram_word(image, LINEA_GDP_XC, ram_uword(image, ptsin));
    set_ram_word(image, LINEA_GDP_YC, ram_uword(image, ptsin + VDI_POINT_Y));
    vdi_clc_arc(image);
}

/* $fcc714 — gdp_ell: an elliptical arc or pie, (xc, yc, xrad, yrad) = ptsin[0..3]; in normalised
 * coordinates the y radius is taken as DEV_TAB's last row less it. */
void vdi_gdp_ell(uint8_t *image)
{
    angles_from_intin(image);
    vdi_ellipse_from_ptsin(image, linea_pointer(image, LINEA_PTSIN));
    vdi_clc_nsteps(image);
    vdi_clc_arc(image);
}

/* ================================================================================================
 * The rounded box.
 * ============================================================================================= */

/* The corner radii: XRAD the screen's last column / 64 and YRAD that in the aspect, each held to the box's
 * half-size — `half_width` = (X2 - X1) / 2, `half_height` = (Y1 - Y2) / 2 (Y1 is the LOWER edge). */
static void corner_radii(uint8_t *image, int16_t half_width, int16_t half_height)
{
    int16_t radius = (int16_t)(table_word(image, LINEA_DEV_TAB, VDI_DEV_TAB_MAX_X_INDEX) >> VDI_RBOX_RADIUS_SHIFT);

    set_ram_word(image, LINEA_GDP_XRAD, (uint16_t)radius);
    if (ram_word(image, LINEA_GDP_XRAD) > half_width)
        set_ram_word(image, LINEA_GDP_XRAD, (uint16_t)half_width);
    set_ram_word(image, LINEA_GDP_YRAD, (uint16_t)vdi_aspect_y_radius(image));
    if (ram_word(image, LINEA_GDP_YRAD) > half_height)
        set_ram_word(image, LINEA_GDP_YRAD, (uint16_t)half_height);
}

/* A radius's projection at `angle`: smul_div(trig(angle), the radius at `radius`, 32767). */
static int16_t projected(const uint8_t *image, int16_t trig, uint32_t radius)
{
    return vdi_smul_div(trig, ram_word(image, radius), VDI_TRIG_SCALE);
}

/* The quarter-round's five (dx, dy) offsets from 90 degrees to 0 into ptsin[0..9], stored in order through
 * the one PTSIN (`move.w ...,(a5)+`), each radius re-read at its use. */
static void quarter_round(uint8_t *image)
{
    static const int16_t inner_angles[] = { ROUND_ANGLE_UPPER, ROUND_ANGLE_MIDDLE, ROUND_ANGLE_LOWER };
    uint32_t at = linea_pointer(image, LINEA_PTSIN);
    unsigned index;

    set_ram_word(image, at, 0);
    set_ram_word(image, at + VDI_WORD_BYTES, ram_uword(image, LINEA_GDP_YRAD));
    at += VDI_POINT_BYTES;
    for (index = 0; index < sizeof inner_angles / sizeof inner_angles[0]; index++, at += VDI_POINT_BYTES) {
        set_ram_word(image, at, (uint16_t)projected(image, vdi_icos(image, inner_angles[index]), LINEA_GDP_XRAD));
        set_ram_word(image, at + VDI_WORD_BYTES,
                     (uint16_t)projected(image, vdi_isin(image, inner_angles[index]), LINEA_GDP_YRAD));
    }
    set_ram_word(image, at, ram_uword(image, LINEA_GDP_XRAD));
    set_ram_word(image, at + VDI_WORD_BYTES, 0);
}

/* How a corner places a quarter-round offset about the centre: `add.w` it, or `sub.w` it from the centre. */
enum offset_sign { ADDED, SUBTRACTED };

/* One word of a corner: the centre word at `centre` — re-read at every store, as the ROM re-reads it — with
 * the quarter-round's word `from` added or subtracted, into ptsin word `to`. */
static void corner_word(uint8_t *image, uint32_t ptsin, int16_t to, int16_t from, uint32_t centre, enum offset_sign sign)
{
    int16_t offset = ram_word(image, word_entry(ptsin, from));

    set_ram_word(image, word_entry(ptsin, to),
                 (uint16_t)(sign == SUBTRACTED ? word_difference(ram_word(image, centre), offset)
                                               : word_sum(offset, ram_word(image, centre))));
}

/* One corner, its five points from ptsin word `first` on: the quarter-round walked FORWARD (x from word
 * 2k, y from 2k + 1, x stored first) or BACKWARD (from its last point, y stored first), each word placed
 * about XC / YC by its sign. */
enum walk { FORWARD, BACKWARD };

static void corner(uint8_t *image, uint32_t ptsin, int16_t first, enum walk walk, enum offset_sign x_sign,
                   enum offset_sign y_sign)
{
    int16_t to = first, point;

    for (point = 0; point < VDI_RBOX_CORNER_POINTS; point++, to = word_sum(to, VDI_POINT_WORDS)) {
        if (walk == FORWARD) {
            corner_word(image, ptsin, to, (int16_t)(point * VDI_POINT_WORDS), LINEA_GDP_XC, x_sign);
            corner_word(image, ptsin, (int16_t)(to + 1), (int16_t)(point * VDI_POINT_WORDS + 1), LINEA_GDP_YC, y_sign);
        } else {
            int16_t from = (int16_t)(ROUND_WORDS - point * VDI_POINT_WORDS - 1);

            corner_word(image, ptsin, (int16_t)(to + 1), from, LINEA_GDP_YC, y_sign);
            corner_word(image, ptsin, to, (int16_t)(from - 1), LINEA_GDP_XC, x_sign);
        }
    }
}

/* The outline's line attributes from the workstation at `work` — the style mask and the colour bits — then
 * the 21 points as a one-pixel polyline or a wide one. */
static void rbox_outline(uint8_t *image, uint32_t work)
{
    set_line_attributes(image, work);
    if (work_word(image, work, WS_LINE_WIDTH) == VDI_THIN_LINE_WIDTH)
        vdi_polyline(image);
    else
        vdi_wline(image);
}

/* Where each corner's five points start, in ptsin words. */
#define LOWER_RIGHT_FIRST     10         /*                                     ($fcc444 moveq #10) */
#define LOWER_LEFT_FIRST      20         /*                                     ($fcc498 moveq #20) */
#define UPPER_LEFT_FIRST      30         /*                                     ($fcc4f0 moveq #30) */
#define UPPER_RIGHT_FIRST     0          /* over the quarter-round itself       ($fcc548 clr.w d6)  */
#define CLOSING_WORD          ((VDI_RBOX_POINTS - 1) * VDI_POINT_WORDS) /* the first point again ($fcc58e 80(a5)) */

/* $fcc284 — gdp_rbox: the rounded box ptsin[0..1] / [2..3] name. */
void vdi_gdp_rbox(uint8_t *image)
{
    uint32_t ptsin = linea_pointer(image, LINEA_PTSIN), contrl;

    vdi_arb_corner(image, ptsin, VDI_CORNERS_Y_DESCENDING);
    ptsin = linea_pointer(image, LINEA_PTSIN);
    set_ram_word(image, LINEA_X1, ram_uword(image, ptsin));
    set_ram_word(image, LINEA_Y1, ram_uword(image, word_entry(ptsin, 1)));
    set_ram_word(image, LINEA_X2, ram_uword(image, word_entry(ptsin, 2)));
    set_ram_word(image, LINEA_Y2, ram_uword(image, word_entry(ptsin, 3)));
    corner_radii(image, (int16_t)(word_difference(ram_word(image, LINEA_X2), ram_word(image, LINEA_X1)) / HALF_DIVISOR),
                 (int16_t)(word_difference(ram_word(image, LINEA_Y1), ram_word(image, LINEA_Y2)) / HALF_DIVISOR));
    quarter_round(image);

    ptsin = linea_pointer(image, LINEA_PTSIN);
    set_ram_word(image, LINEA_GDP_XC, (uint16_t)word_difference(ram_word(image, LINEA_X2), ram_word(image, LINEA_GDP_XRAD)));
    set_ram_word(image, LINEA_GDP_YC, (uint16_t)word_difference(ram_word(image, LINEA_Y1), ram_word(image, LINEA_GDP_YRAD)));
    corner(image, ptsin, LOWER_RIGHT_FIRST, BACKWARD, ADDED, ADDED);
    set_ram_word(image, LINEA_GDP_XC, (uint16_t)word_sum(ram_word(image, LINEA_X1), ram_word(image, LINEA_GDP_XRAD)));
    corner(image, ptsin, LOWER_LEFT_FIRST, FORWARD, SUBTRACTED, ADDED);
    set_ram_word(image, LINEA_GDP_YC, (uint16_t)word_sum(ram_word(image, LINEA_Y2), ram_word(image, LINEA_GDP_YRAD)));
    corner(image, ptsin, UPPER_LEFT_FIRST, BACKWARD, SUBTRACTED, SUBTRACTED);
    set_ram_word(image, LINEA_GDP_XC, (uint16_t)word_difference(ram_word(image, LINEA_X2), ram_word(image, LINEA_GDP_XRAD)));
    corner(image, ptsin, UPPER_RIGHT_FIRST, FORWARD, ADDED, SUBTRACTED);
    copy_point(image, word_entry(ptsin, CLOSING_WORD), ptsin);

    contrl = linea_pointer(image, LINEA_CONTRL);
    set_ram_word(image, contrl + CONTRL_N_PTSIN, VDI_RBOX_POINTS);
    if (gdp_number(image, contrl) == VDI_GDP_ROUNDED_BOX)
        rbox_outline(image, current_work(image));
    else
        vdi_plygn(image);
}
