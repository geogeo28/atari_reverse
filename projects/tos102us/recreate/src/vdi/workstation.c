/* workstation.c — the WORKSTATIONS: the physical one opened and closed, the virtual ones on the list behind
 * it, and init_wk, the record set-up both opens end in (`vdi/workstation.h`).
 *
 * THE LIST starts at the physical record (VDI_PHYS_WORK, handle 1) and runs through WS_NEXT; the dispatcher
 * walks it by handle for every call but the two opens ($fca9f6). A virtual record is `Malloc(308)`'d and
 * linked; a closed one is unlinked and `Mfree`'d — both through the VDI's GEMDOS door, gemdos_call, which
 * parks its caller's return address in LINEA_RETSAV (the RETURN SITES in `vdi/workstation.h`).
 *
 * WHAT THE ROM GETS WRONG, and what is therefore reproduced:
 *   * v_opnvwk's HANDLE is the first one the walk does not find IN LIST ORDER, and the new record goes after
 *     the record the walk stopped at, not before it. The list is only sorted until a record is closed out of
 *     its middle: over 1, 2, 4 an open takes 3 and appends it (1, 2, 4, 3), and the next open stops at the 4
 *     again and takes 3 AGAIN — two records with one handle, the dispatcher reaching only the first.
 *   * init_wk stores the fill STYLE index as given, 1-based, where vsf_style stores it less one
 *     ($fcaf9c `subq.w #1`) and st_fl_ptr reads it 0-based: a fresh workstation's pattern is the one AFTER the
 *     style asked for, and pattern style 24 reads past the last of the upper table.
 *   * init_wk's line type 0 is stored as -1 (the clamp tests 0..7 and then subtracts one).
 *   * v_clswk frees every virtual record but leaves the physical record's WS_NEXT naming the first of them,
 *     and LINEA_CUR_WORK at 0.
 *   * v_clsvwk's walk has no end test: a current record that is not on the list is looked for through
 *     address 0's vectors. The dispatcher only ever makes current a record it found on the list, so no call
 *     reaches that (and no case stages it).
 */
#include <stdint.h>

#include "machine.h"
#include "addrs.h"
#include "host_slot.h"
#include "m68k_idioms.h"
#include "vdi/vdi.h"
#include "vdi/font.h"
#include "vdi/attributes.h"
#include "vdi/helpers.h"
#include "vdi/inquire.h"
#include "vdi/screen.h"
#include "vdi/text.h"
#include "vdi/workstation.h"

/* ================================================================================================
 * The record, and the list through it.
 * ============================================================================================= */

/* A record's field by the address the list holds for it — a WS_NEXT a case or a caller wrote, so through the
 * bus the 68000 would drive (`bus_dereference`: free on target). */
static uint32_t next_of(const uint8_t *image, uint32_t work)
{
    return be32(image + bus_dereference(work + WS_NEXT));
}

static void set_next(uint8_t *image, uint32_t work, uint32_t next)
{
    wr32(image + bus_dereference(work + WS_NEXT), next);
}

static int16_t handle_of(const uint8_t *image, uint32_t work)
{
    return (int16_t)be16(image + bus_dereference(work + WS_HANDLE));
}

static void set_handle(uint8_t *image, uint32_t work, uint16_t handle)
{
    wr16(image + bus_dereference(work + WS_HANDLE), handle);
}

/* ================================================================================================
 * $fcd402 — init_wk: the CURRENT record's attributes from the open call's intin[1..10], each clamped to its
 * default as the setters clamp it, the rest at their defaults, and the open answered: DEV_TAB into intout,
 * SIZ_TAB into ptsout, VDI_RESULT set.
 *
 * INTIN AND THE RECORD ARE EACH LOADED ONCE (`movea.l $29a2,a5 / addq.l #2,a5`, `movea.l $27ca,a3`), and the
 * attributes are read and stored one at a time in intin's order — so an intin laid over the record reads the
 * stores before it. DEV_TAB[13], the colour bound, is re-read at every compare, and WS_FILL_STYLE is re-read
 * from the record to choose the style's range, AFTER intin[8] is read.
 * ============================================================================================= */
/* The marker, colour and style clamps are the setters' (`vdi/attributes.h`); these are init_wk's own. */
#define LINE_TYPE_LAST        7     /* 0..7 pass, then less one                ($fcd41a cmp.w #7)  */
#define LINE_TYPE_DEFAULT     0     /*                                         ($fcd424 clr.w)     */
#define INTERIOR_DEFAULT      VDI_INTERIOR_HOLLOW /*                           ($fcd4be clr.w)     */
#define MARK_SCALE_ON         1     /*                                         ($fcd4ac)           */
#define FILL_PERIMETER_ON     1     /*                                         ($fcd53a)           */
#define OPEN_ANSWER_POINTS    (VDI_SIZ_TAB_WORDS / VDI_POINT_WORDS)         /* ($fcd5c0 move.w #6)  */

/* The pen a colour index maps to, clamped as the colour setters clamp it. */
static uint16_t open_colour(const uint8_t *image, int16_t index)
{
    return vdi_mapped_colour(image, vdi_colour_index_or_default(image, index));
}

static int16_t open_intin(const uint8_t *image, uint32_t intin, unsigned index)
{
    return (int16_t)be16(image + intin + index * VDI_WORD_BYTES);
}

/* intin[1..4], [6]: the line and marker attributes, and the text colour. */
static void open_line_and_marker(uint8_t *image, uint32_t intin, uint32_t work)
{
    int16_t value = open_intin(image, intin, VDI_OPEN_LINE_TYPE);

    set_work_word(image, work, WS_LINE_INDEX,
                  (uint16_t)(value > LINE_TYPE_LAST || value < 0 ? LINE_TYPE_DEFAULT : value - 1));
    set_work_word(image, work, WS_LINE_COLOR, open_colour(image, open_intin(image, intin, VDI_OPEN_LINE_COLOUR)));
    value = vdi_zero_based_or(open_intin(image, intin, VDI_OPEN_MARK_TYPE), VDI_MARKER_TYPE_COUNT, VDI_MARKER_INDEX_DEFAULT);
    set_work_word(image, work, WS_MARK_INDEX, (uint16_t)value);
    set_work_word(image, work, WS_MARK_COLOR, open_colour(image, open_intin(image, intin, VDI_OPEN_MARK_COLOUR)));
    set_work_word(image, work, WS_TEXT_COLOR, open_colour(image, open_intin(image, intin, VDI_OPEN_TEXT_COLOUR)));
    set_work_word(image, work, WS_MARK_HEIGHT, table_uword(image, LINEA_SIZ_TAB, VDI_SIZ_TAB_MIN_MARK_HEIGHT_INDEX));
    set_work_word(image, work, WS_MARK_SCALE, MARK_SCALE_ON);
}

/* intin[7..10]: the fill interior, its style (1-based, as given — the file's header says why that is wrong),
 * its colour, and the coordinate system; then the pattern pointer st_fl_ptr makes of them.
 * The two clamps are spelt out rather than `vdi_within_or`: init_wk tests the HIGH bound first (`cmp.w #4 / bgt`
 * $fcd4b4, `cmp.w #24 / bgt` $fcd4d2), and through the helper GCC lays both out differently — 2 to 4 cycles more
 * on every init_wk row, measured. */
static void open_fill(uint8_t *image, uint32_t intin, uint32_t work)
{
    int16_t interior = open_intin(image, intin, VDI_OPEN_FILL_INTERIOR);
    int16_t style;
    int16_t last;

    set_work_word(image, work, WS_FILL_STYLE,
                  (uint16_t)(interior > VDI_INTERIOR_USER || interior < 0 ? INTERIOR_DEFAULT : interior));
    style = open_intin(image, intin, VDI_OPEN_FILL_STYLE);
    last = work_word(image, work, WS_FILL_STYLE) == VDI_INTERIOR_PATTERN ? VDI_PATTERN_STYLE_COUNT : VDI_OTHER_STYLE_COUNT;
    set_work_word(image, work, WS_FILL_INDEX, (uint16_t)(style > last || style < VDI_FILL_STYLE_FIRST ? VDI_FILL_STYLE_DEFAULT : style));
    set_work_word(image, work, WS_FILL_COLOR, open_colour(image, open_intin(image, intin, VDI_OPEN_FILL_COLOUR)));
    set_work_word(image, work, WS_XFM_MODE, (uint16_t)open_intin(image, intin, VDI_OPEN_XFM_MODE));
    vdi_st_fl_ptr(image);
}

/* Everything the call does not choose, in the ROM's order ($fcd526..$fcd5b8). */
static void open_defaults(uint8_t *image, uint32_t work)
{
    set_work_word(image, work, WS_WRT_MODE, 0);
    set_work_word(image, work, WS_LINE_WIDTH, table_uword(image, LINEA_SIZ_TAB, VDI_SIZ_TAB_MIN_LINE_WIDTH_INDEX));
    set_work_word(image, work, WS_LINE_BEG, VDI_LINE_END_SQUARE);
    set_work_word(image, work, WS_LINE_END, VDI_LINE_END_SQUARE);
    set_work_word(image, work, WS_FILL_PER, FILL_PERIMETER_ON);
    set_work_word(image, work, WS_XMN_CLIP, 0);
    set_work_word(image, work, WS_YMN_CLIP, 0);
    set_work_word(image, work, WS_XMX_CLIP, table_uword(image, LINEA_DEV_TAB, VDI_DEV_TAB_MAX_X_INDEX));
    set_work_word(image, work, WS_YMX_CLIP, table_uword(image, LINEA_DEV_TAB, VDI_DEV_TAB_MAX_Y_INDEX));
    set_work_word(image, work, WS_CLIP, 0);
    set_work_long(image, work, WS_CUR_FONT, be32(image + LINEA_DEF_FONT));
    set_work_long(image, work, WS_LOADED_FONTS, 0);
    set_work_word(image, work, WS_SCRPT2, be16(image + VDI_SCRPT2_DEFAULT));
    set_work_long(image, work, WS_SCRTCHP, VDI_TEXT_SCRATCH);
    set_work_word(image, work, WS_NUM_FONTS, be16(image + LINEA_FONT_COUNT));
    set_work_word(image, work, WS_STYLE, 0);
    set_work_word(image, work, WS_SCALED, 0);
    set_work_word(image, work, WS_H_ALIGN, 0);
    set_work_word(image, work, WS_V_ALIGN, 0);
    set_work_word(image, work, WS_CHUP, 0);
    set_work_word(image, work, WS_PTS_MODE, VDI_PTS_MODE_HEIGHT);
    copy_words(image + work + WS_UD_PATRN, image + VDI_UD_PATTERN_DEFAULT, VDI_UD_PATTERN_ROWS);
    set_work_word(image, work, WS_MULTIFILL, 0);
    set_work_word(image, work, WS_UD_LS, be16(image + VDI_LINE_STYLES));
}

void vdi_init_wk(uint8_t *image)
{
    uint32_t intin = linea_pointer(image, LINEA_INTIN);
    uint32_t work = current_work(image);
    uint32_t contrl, intout, ptsout;                /* each loaded once, as the ROM's `movea.l` */

    open_line_and_marker(image, intin, work);
    open_fill(image, intin, work);
    open_defaults(image, work);
    contrl = linea_pointer(image, LINEA_CONTRL);
    wr16(image + contrl + CONTRL_N_PTSOUT, OPEN_ANSWER_POINTS);
    wr16(image + contrl + CONTRL_N_INTOUT, VDI_DEV_TAB_WORDS);
    intout = linea_pointer(image, LINEA_INTOUT);
    copy_words(image + intout, image + LINEA_DEV_TAB, VDI_DEV_TAB_WORDS);
    ptsout = linea_pointer(image, LINEA_PTSOUT);
    copy_words(image + ptsout, image + LINEA_SIZ_TAB, VDI_SIZ_TAB_WORDS);
    wr16(image + VDI_RESULT, VDI_RESULT_SET);
}

/* ================================================================================================
 * $fcb694 — v_opnwk (1): the physical workstation opened.
 *
 * In order: the three device tables from their ROM defaults (INQ_TAB[14] from its own word), the two RAM
 * system fonts' headers from the ROM's and the ring's slot 1 pointed at the 8x8, the resolution (setres, which
 * reads intin[0]), the tables patched for it, the physical record made current and alone on the list with
 * handle 1 (answered in contrl[6]), the text ring (text_init), the record's attributes and the open's answer
 * (init_wk), the input modes back to request, the mouse hidden once and centred, the timer and mouse taken
 * (init_timer_mouse, which ends in the screen clear), and LINEA_REQ_COL filled with the REALIZED colour of
 * every index — vq_color asked for each, over arrays of the ROM's own frame.
 *
 * THE RESOLUTION CHANGE HALTS: setres's two switching arms call XBIOS Setscreen's resolution arm, the console
 * re-initialisation, which is not reconstructed (`src/vdi/screen.c`). Everything before setres is stored by
 * then, nothing after.
 * ============================================================================================= */
#define LINE_CW_NONE           ((uint16_t)-1)   /* no quarter circle built for any width ($fcb7e8)  */
#define INPUT_MODE_REQUEST     0                /*                                   ($fcb7fc clr.w) */
#define MOUSE_HIDDEN_ONCE      1                /*                                   ($fcb814)       */
#define VQ_COLOR_REALIZED      1                /* intin[1] of the call              ($fcb87c)       */

static void patch_medium(uint8_t *image)
{
    set_table_word(image, LINEA_DEV_TAB, VDI_DEV_TAB_MAX_X_INDEX, VDI_OPNWK_WIDE_MAX_X);
    set_table_word(image, LINEA_DEV_TAB, VDI_DEV_TAB_PIXEL_WIDTH_INDEX, VDI_OPNWK_MEDIUM_PIXEL_WIDTH);
    set_table_word(image, LINEA_DEV_TAB, VDI_DEV_TAB_COLOURS_INDEX, VDI_OPNWK_MEDIUM_COLOURS);
    set_table_word(image, LINEA_INQ_TAB, VDI_INQ_TAB_PLANES_INDEX, VDI_OPNWK_MEDIUM_PLANES);
}

static void patch_high(uint8_t *image)
{
    set_table_word(image, LINEA_DEV_TAB, VDI_DEV_TAB_MAX_X_INDEX, VDI_OPNWK_WIDE_MAX_X);
    set_table_word(image, LINEA_DEV_TAB, VDI_DEV_TAB_MAX_Y_INDEX, VDI_OPNWK_HIGH_MAX_Y);
    set_table_word(image, LINEA_DEV_TAB, VDI_DEV_TAB_PIXEL_WIDTH_INDEX, VDI_OPNWK_HIGH_PIXEL_WIDTH);
    set_table_word(image, LINEA_DEV_TAB, VDI_DEV_TAB_COLOURS_INDEX, VDI_OPNWK_HIGH_COLOURS);
    set_table_word(image, LINEA_DEV_TAB, VDI_DEV_TAB_COLOUR_CAPABLE_INDEX, VDI_OPNWK_HIGH_COLOUR_CAPABLE);
    set_table_word(image, LINEA_DEV_TAB, VDI_DEV_TAB_PALETTE_INDEX, VDI_OPNWK_HIGH_PALETTE);
    set_table_word(image, LINEA_INQ_TAB, VDI_INQ_TAB_BACKGROUNDS_INDEX, VDI_OPNWK_HIGH_BACKGROUNDS);
    set_table_word(image, LINEA_INQ_TAB, VDI_INQ_TAB_PLANES_INDEX, VDI_OPNWK_HIGH_PLANES);
    set_table_word(image, LINEA_INQ_TAB, VDI_INQ_TAB_LUT_INDEX, VDI_OPNWK_HIGH_LUT);
    wr16(image + FONT_RAM_8X8 + FONT_POINT, VDI_OPNWK_HIGH_8X8_POINT);
    wr16(image + FONT_RAM_8X16 + FONT_POINT, VDI_OPNWK_HIGH_8X16_POINT);
    wr16(image + FONT_RAM_8X8 + FONT_FLAGS, be16(image + FONT_RAM_8X8 + FONT_FLAGS) ^ FONT_FLAG_DEFAULT_MASK);
    wr16(image + FONT_RAM_8X16 + FONT_FLAGS, be16(image + FONT_RAM_8X16 + FONT_FLAGS) | FONT_FLAG_DEFAULT_MASK);
}

/* LINEA_REQ_COL, three words a colour for DEV_TAB[13] colours (re-read every pass), from vq_color's realized
 * answer. The call's arrays are v_opnwk's own frame locals, their ADDRESSES put in LINEA_CONTRL/INTIN/INTOUT
 * — so one host slot off target (`host_slot.h`) — and the caller's three pointers are put back after. */
static void request_realized_colours(uint8_t *image)
{
    uint16_t frame_local[VDI_OPNWK_CALL_BYTES / VDI_WORD_BYTES];
    _Static_assert(sizeof frame_local == HOST_SLOT_VDI_OPNWK_COLOUR_CALL_BYTES, "v_opnwk's vq_color arrays");
    uint32_t intin = linea_pointer(image, LINEA_INTIN);
    uint32_t intout = linea_pointer(image, LINEA_INTOUT);
    uint32_t contrl = linea_pointer(image, LINEA_CONTRL);
    uint32_t call = host_slot_claim(VDI_OPNWK_COLOUR_CALL, frame_local);
    uint32_t requested = LINEA_REQ_COL;
    int16_t index;

    wr32(image + LINEA_CONTRL, call + VDI_OPNWK_CALL_CONTRL);
    wr32(image + LINEA_INTIN, call + VDI_OPNWK_CALL_INTIN);
    wr32(image + LINEA_INTOUT, call + VDI_OPNWK_CALL_INTOUT);
    wr16(image + call + VDI_OPNWK_CALL_INTIN + VDI_WORD_BYTES, VQ_COLOR_REALIZED);
    for (index = 0; index < table_word(image, LINEA_DEV_TAB, VDI_DEV_TAB_COLOURS_INDEX); index++) {
        wr16(image + call + VDI_OPNWK_CALL_INTIN, (uint16_t)index);
        vdi_vq_color(image);
        copy_words(image + requested, image + call + VDI_OPNWK_CALL_INTOUT + VDI_WORD_BYTES, VDI_REQ_COL_COMPONENTS);
        requested += VDI_REQ_COL_COMPONENTS * VDI_WORD_BYTES;
    }
    wr32(image + LINEA_CONTRL, contrl);
    wr32(image + LINEA_INTIN, intin);
    wr32(image + LINEA_INTOUT, intout);
    host_slot_release(VDI_OPNWK_COLOUR_CALL);
}

void vdi_v_opnwk(uint8_t *image)
{
    uint16_t mode;

    copy_words(image + LINEA_DEV_TAB, image + VDI_DEV_TAB_DEFAULT, VDI_DEV_TAB_WORDS);
    copy_words(image + LINEA_INQ_TAB, image + VDI_INQ_TAB_DEFAULT, VDI_INQ_TAB_WORDS);
    set_table_word(image, LINEA_INQ_TAB, VDI_INQ_TAB_MAX_VERTICES_INDEX, be16(image + VDI_MAX_VERTICES_DEFAULT));
    copy_words(image + LINEA_SIZ_TAB, image + VDI_SIZ_TAB_DEFAULT, VDI_SIZ_TAB_WORDS);
    copy_words(image + FONT_RAM_8X8, image + FONT_ROM_8X8, FONT_HEADER_BYTES / VDI_WORD_BYTES);
    copy_words(image + FONT_RAM_8X16, image + FONT_ROM_8X16, FONT_HEADER_BYTES / VDI_WORD_BYTES);
    wr32(image + LINEA_FONT_RING + LINEA_FONT_RING_BUILTIN * VDI_LONG_BYTES, FONT_RAM_8X8);

    mode = (uint16_t)vdi_setres(image);             /* kept as a word: `move.w d0,-40(a6)` */
    if (mode == VDI_SETRES_ANSWER_MEDIUM)
        patch_medium(image);
    else if (mode == VDI_SETRES_ANSWER_HIGH)
        patch_high(image);

    set_handle(image, VDI_PHYS_WORK, VDI_PHYS_HANDLE);
    set_contrl_word(image, CONTRL_HANDLE, VDI_PHYS_HANDLE);
    wr32(image + LINEA_CUR_WORK, VDI_PHYS_WORK);
    set_next(image, VDI_PHYS_WORK, 0);
    set_ram_word(image, LINEA_LINE_CW, LINE_CW_NONE);
    vdi_text_init(image);
    vdi_init_wk(image);

    set_ram_word(image, LINEA_LOC_MODE, INPUT_MODE_REQUEST);
    set_ram_word(image, LINEA_VAL_MODE, INPUT_MODE_REQUEST);
    set_ram_word(image, LINEA_CHC_MODE, INPUT_MODE_REQUEST);
    set_ram_word(image, LINEA_STR_MODE, INPUT_MODE_REQUEST);
    set_ram_word(image, LINEA_M_HID_CT, MOUSE_HIDDEN_ONCE);
    set_ram_word(image, LINEA_GCURX, (uint16_t)(table_word(image, LINEA_DEV_TAB, VDI_DEV_TAB_MAX_X_INDEX) / 2));
    set_ram_word(image, LINEA_GCURY, (uint16_t)(table_word(image, LINEA_DEV_TAB, VDI_DEV_TAB_MAX_Y_INDEX) / 2));
    vdi_init_timer_mouse(image);
    request_realized_colours(image);
}

/* ================================================================================================
 * $fcd612 — v_opnvwk (100): a virtual workstation. `Malloc(308)`; none, and contrl[6] answers handle 0 and
 * nothing else is done. Otherwise the walk from the physical record takes the first handle, counting from 1,
 * that the record it stands on does not hold, and stops on that record or the last; the new record is linked
 * AFTER it, made current, handed that handle (contrl[6] first), and set up by init_wk.
 *
 * THE ROM HAS TWO LINK ARMS — the record the walk stopped at last on the list or not — and they store the same
 * three longwords in the same order: its WS_NEXT, LINEA_CUR_WORK, and the new record's WS_NEXT, which is the
 * old WS_NEXT in both (0 in the first). One spelling here.
 * ============================================================================================= */
#define NO_HANDLE              0                /*                                   ($fcd638 clr.w) */

void vdi_v_opnvwk(uint8_t *image)
{
    uint32_t record = vdi_gemdos_call(image, VDI_OPNVWK_MALLOC_RETURN, GEMDOS_MALLOC_FN, WS_BYTES);
    uint32_t work = VDI_PHYS_WORK;
    uint16_t handle = VDI_PHYS_HANDLE;
    uint32_t following;

    if (record == 0) {
        set_contrl_word(image, CONTRL_HANDLE, NO_HANDLE);
        return;
    }
    while ((int16_t)handle == handle_of(image, work)) {
        handle++;
        if (next_of(image, work) == 0)
            break;
        work = next_of(image, work);
    }
    following = next_of(image, work);
    set_next(image, work, record);
    wr32(image + LINEA_CUR_WORK, record);
    set_next(image, record, following);
    set_contrl_word(image, CONTRL_HANDLE, handle);
    set_handle(image, record, handle);
    vdi_init_wk(image);
}

/* ================================================================================================
 * $fcd6a4 — v_clsvwk (101): the current workstation unlinked and given back — unless it is handle 1, the
 * physical one, which is left alone. The walk finds the record whose WS_NEXT holds the current one's HANDLE
 * (not its address), and LINEA_CUR_WORK is read again for each of the two uses after it.
 * ============================================================================================= */
void vdi_v_clsvwk(uint8_t *image)
{
    int16_t handle = handle_of(image, current_work(image));
    uint32_t work = VDI_PHYS_WORK;

    if (handle == VDI_PHYS_HANDLE)
        return;
    while (handle != handle_of(image, next_of(image, work)))
        work = next_of(image, work);
    set_next(image, work, next_of(image, current_work(image)));
    (void)vdi_gemdos_call(image, VDI_CLSVWK_MFREE_RETURN, GEMDOS_MFREE_FN, current_work(image));
}

/* ================================================================================================
 * $fcb998 — v_clswk (2): every virtual workstation on the list given back, in list order — each one's WS_NEXT
 * read before its `Mfree`, through LINEA_CUR_WORK, which the loop walks and leaves at 0 — and then the timer
 * and mouse given back and the screen cleared (restore_timer_mouse). The physical record's WS_NEXT is left
 * naming the first record freed.
 * ============================================================================================= */
void vdi_v_clswk(uint8_t *image)
{
    uint32_t following;

    if (next_of(image, VDI_PHYS_WORK) != 0) {
        wr32(image + LINEA_CUR_WORK, next_of(image, VDI_PHYS_WORK));
        do {
            following = next_of(image, current_work(image));
            (void)vdi_gemdos_call(image, VDI_CLSWK_MFREE_RETURN, GEMDOS_MFREE_FN, current_work(image));
            wr32(image + LINEA_CUR_WORK, following);
        } while (following != 0);
    }
    vdi_restore_timer_mouse(image);
}
