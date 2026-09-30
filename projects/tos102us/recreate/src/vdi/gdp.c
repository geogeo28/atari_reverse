/* gdp.c — the GENERALIZED DRAWING PRIMITIVE: vdi_gdp ($fcbbcc, VDI opcode 11), Alcyon C in the ROM.
 *
 * contrl[5] picks the arm, read once into a frame word; out of 1..10 nothing is done. PTSIN and CUR_WORK
 * are loaded ONCE on entry (A5, A4) and the arms that read through them read through the held copies:
 *
 *   1  bar              vr_recfl; then, when WS_FILL_PER is exactly 1, its perimeter — LN_MASK solid, the
 *                       sorted corners (PTSIN reloaded) turned into a closed outline of five points, polyline
 *   2  arc, 3 pie       gdp_arc
 *   4  circle           XC, YC, XRAD = ptsin[0], [1], [4]; YRAD = XRAD in the aspect; a whole turn from 0
 *   5  ellipse          XC, YC, XRAD, YRAD = ptsin[0..3] (gdp_ell's reading); a whole turn ending at 0
 *   6, 7                gdp_ell
 *   8  rounded box      WS_LINE_BEG and WS_LINE_END cleared round gdp_rbox, so the outline has no arrowheads
 *   9  filled one       gdp_rbox
 *   10 justified text   d_justified
 *
 * A WHOLE TURN is the arc scratch clc_arc draws from: DEL_ANG 3600, BEG_ANG 0 and END_ANG 3600 for the circle
 * but 0 for the ellipse — the same last point either way — then clc_nsteps and clc_arc.
 *
 * What a reader checks the C against:
 *   * the ROM's switch table has ten entries and a range test in front of it ($fcbbec..$fcbbfa), so its own
 *     `cmp.w #9 / bhi` ($fcbd60) never branches, and the `bra` at $fcbd5e after arm 10's is never reached;
 *   * gdp_rbox sorts through its caller's A5 — the PTSIN this routine loaded on entry — which the core reads
 *     back from LINEA_PTSIN: arm 8 stores into the workstation record only, and nothing else between.
 */
#include <stdint.h>

#include "machine.h"
#include "addrs.h"
#include "vdi/vdi.h"
#include "vdi/helpers.h"
#include "vdi/blit.h"
#include "vdi/fill.h"
#include "vdi/arcs.h"
#include "vdi/gtext.h"
#include "vdi/gdp.h"

/* The ptsin word indexes of point `point`'s x and y. */
#define X_OF(point)           ((point) * VDI_POINT_WORDS)
#define Y_OF(point)           ((point) * VDI_POINT_WORDS + 1)
/* The bar's corners as vr_recfl leaves them sorted: (LEFT, TOP) and (RIGHT, BOTTOM). */
#define BAR_LEFT              X_OF(0)
#define BAR_TOP               Y_OF(0)
#define BAR_RIGHT             X_OF(1)
#define BAR_BOTTOM            Y_OF(1)

/* Word `from` of the points at `ptsin`, read once, stored into word `to` — and into `also` unless it is NONE. */
#define NONE                  (-1)

static void spread_word(uint8_t *image, uint32_t ptsin, int16_t from, int16_t to, int16_t also)
{
    uint16_t word = ram_uword(image, word_entry(ptsin, from));

    set_ram_word(image, word_entry(ptsin, to), word);
    if (also != NONE)
        set_ram_word(image, word_entry(ptsin, also), word);
}

/* The bar's perimeter over its corners as vr_recfl left them sorted: (L, T) (R, T) (R, B) (L, B) (L, T), in the
 * ROM's store order ($fcbc2c..$fcbc50) — through the PTSIN reloaded after LN_MASK's store — then contrl[1]. */
static void bar_perimeter(uint8_t *image)
{
    uint32_t ptsin;

    set_ram_word(image, LINEA_LN_MASK, VDI_PERIMETER_LINE_MASK);
    ptsin = linea_pointer(image, LINEA_PTSIN);
    spread_word(image, ptsin, BAR_BOTTOM, Y_OF(3), Y_OF(2));
    spread_word(image, ptsin, BAR_TOP, Y_OF(4), Y_OF(1));
    spread_word(image, ptsin, BAR_RIGHT, X_OF(2), NONE);
    spread_word(image, ptsin, BAR_LEFT, X_OF(4), X_OF(3));
    set_contrl_word(image, CONTRL_N_PTSIN, VDI_BAR_OUTLINE_POINTS);
    vdi_polyline(image);
}

/* GDP 1: the filled bar, and its perimeter when WS_FILL_PER asks for exactly that. */
static void bar(uint8_t *image)
{
    vdi_vr_recfl(image);
    if (current_work_word(image, WS_FILL_PER) == VDI_FILL_PERIMETER_ON)
        bar_perimeter(image);
}

/* The arc scratch for a whole turn from angle 0 to `end`, then the curve. */
static void whole_turn(uint8_t *image, uint16_t end)
{
    set_ram_word(image, LINEA_GDP_DEL_ANG, VDI_TENTHS_PER_TURN);
    set_ram_word(image, LINEA_GDP_BEG_ANG, 0);
    set_ram_word(image, LINEA_GDP_END_ANG, end);
    vdi_clc_nsteps(image);
    vdi_clc_arc(image);
}

/* The ptsin word a circle's radius is in: the third point's x. */
#define CIRCLE_RADIUS_WORD    X_OF(2)

/* GDP 4: the circle about ptsin[0..1] of radius ptsin[4], each word stored before the next is read. */
static void circle(uint8_t *image, uint32_t ptsin)
{
    set_ram_word(image, LINEA_GDP_XC, ram_uword(image, ptsin));
    set_ram_word(image, LINEA_GDP_YC, ram_uword(image, ptsin + VDI_POINT_Y));
    set_ram_word(image, LINEA_GDP_XRAD, ram_uword(image, word_entry(ptsin, CIRCLE_RADIUS_WORD)));
    set_ram_word(image, LINEA_GDP_YRAD, (uint16_t)vdi_aspect_y_radius(image));
    whole_turn(image, VDI_TENTHS_PER_TURN);
}

/* GDP 8: the outlined rounded box, its line ends cleared for the call and put back into the record at
 * LINEA_CUR_WORK read again after it ($fcbd3c). */
static void outlined_rounded_box(uint8_t *image, uint32_t work)
{
    uint16_t begin = (uint16_t)work_word(image, work, WS_LINE_BEG), end;

    set_work_word(image, work, WS_LINE_BEG, VDI_LINE_END_SQUARE);
    end = (uint16_t)work_word(image, work, WS_LINE_END);
    set_work_word(image, work, WS_LINE_END, VDI_LINE_END_SQUARE);
    vdi_gdp_rbox(image);
    work = current_work(image);
    set_work_word(image, work, WS_LINE_BEG, begin);
    set_work_word(image, work, WS_LINE_END, end);
}

/* $fcbbcc — vdi_gdp (opcode 11). */
void vdi_gdp(uint8_t *image)
{
    int16_t gdp = contrl_word(image, CONTRL_SUBFUNCTION);
    uint32_t ptsin = linea_pointer(image, LINEA_PTSIN);
    uint32_t work = current_work(image);

    switch (gdp) {
    case VDI_GDP_BAR:
        bar(image);
        break;
    case VDI_GDP_ARC:
    case VDI_GDP_PIE:
        vdi_gdp_arc(image);
        break;
    case VDI_GDP_CIRCLE:
        circle(image, ptsin);
        break;
    case VDI_GDP_ELLIPSE:
        vdi_ellipse_from_ptsin(image, ptsin);
        whole_turn(image, 0);
        break;
    case VDI_GDP_ELLIPTICAL_ARC:
    case VDI_GDP_ELLIPTICAL_PIE:
        vdi_gdp_ell(image);
        break;
    case VDI_GDP_ROUNDED_BOX:
        outlined_rounded_box(image, work);
        break;
    case VDI_GDP_FILLED_ROUNDED_BOX:
        vdi_gdp_rbox(image);
        break;
    case VDI_GDP_JUSTIFIED:
        vdi_d_justified(image);
        break;
    }
}
