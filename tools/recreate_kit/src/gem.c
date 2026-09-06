/* gem.c — the GEM `trap #2` model: the AES opcodes and the VDI opcodes, over the parameter block a
 * caller points D1 at. The bit-level drawing underneath it is ../src/raster.c.
 *
 * THE CONTRACT. One implementation compiled into BOTH sides — kit.mk sweeps it into every candidate
 * and names it in the `$(ORACLE)` rule. It is STATELESS: the workstation attributes live in the
 * image (os.h's VDI state block), so two shared objects carrying a copy of these symbols cannot
 * disagree about anything. And it REFUSES NOTHING ITSELF — `os_refused()` is the candidate's tally
 * and the oracle does not link it, so every "cannot serve this" here is a `return 0` and the
 * CALLER (shim.c, or os.h's `os_gem_trap`) turns it into that side's refusal. The same split lets
 * the off-image effects (graf_mouse, v_show_c/v_hide_c) be REPORTED through the `os_event_t`
 * out-parameter instead of logged: each side owns a different ledger.
 *
 * WHY it is arranged that way, what each opcode does and does not capture, and what pins it:
 * TRAP_MODEL.md, "Phase 11" (the raster) and "Phase 12" (the opcodes). Stated there once.
 */
#include <stdint.h>
#include <string.h>

#include "os.h"
#include "raster.h"

/* v_opnvwk's work_out entry holding the number of colours the device shows at once. Only three of
 * the 45 are filled in at all; see os.h's OS_VDI_WORK_OUT_INTS. */
#define VDI_WORK_OUT_MAX_X   0
#define VDI_WORK_OUT_MAX_Y   1
#define VDI_WORK_OUT_COLOURS 13

/* vst_height's four ptsout words, and how many PAIRS that is. */
#define VDI_HEIGHT_CHAR_W 0
#define VDI_HEIGHT_CHAR_H 1
#define VDI_HEIGHT_CELL_W 2
#define VDI_HEIGHT_CELL_H 3
#define VDI_HEIGHT_PTSOUT_PAIRS 2

/* vq_mouse's outputs. */
#define VDI_MOUSE_PTSOUT_PAIRS 1

/* vro_cpyfm's ptsin: the source rectangle, then the destination's. */
#define VDI_CPYFM_SRC_X1 0
#define VDI_CPYFM_SRC_Y1 1
#define VDI_CPYFM_SRC_X2 2
#define VDI_CPYFM_SRC_Y2 3
#define VDI_CPYFM_DST_X1 4
#define VDI_CPYFM_DST_Y1 5

/* An MFDB address arrives as two contrl words, high half first. */
#define VDI_MFDB_WORD_BITS 16

/* The decoded parameter block plus the fault flag every accessor below reports through. A read or
 * write that would leave the image sets `fault` and the whole call is refused: `pblk` and the five
 * pointers come straight off the emulated program's stack, so an unchecked access would scribble the
 * harness's own memory rather than the image's. Writes already made when a later access faults do
 * not matter — a faulted call is refused, so the case is thrown away rather than compared. */
typedef struct {
    uint8_t *mem;
    uint32_t contrl, intin, ptsin, intout, ptsout;
    int fault;
} gem_ctx_t;

/* Resolve `base + offset` for a `width`-byte access, or fault. THE SUM IS TAKEN IN 64 BITS and only
 * then bounded: a pointer near the top of the address space plus an array index wraps in uint32 and
 * would land back in low memory, so the model would read the harness's own bytes through a `contrl`
 * of 0xfffffffe and call the call served. */
static int gem_addr(gem_ctx_t *ctx, uint32_t base, uint32_t offset, uint32_t width, uint32_t *out) {
    uint64_t addr = (uint64_t)base + offset;
    if (addr + width > OS_IMAGE_SIZE) { ctx->fault = 1; return 0; }
    *out = (uint32_t)addr;
    return 1;
}

static uint16_t rd_word(gem_ctx_t *ctx, uint32_t base, int index) {
    uint32_t addr;
    if (!gem_addr(ctx, base, (uint32_t)index * 2u, 2, &addr)) return 0;
    return be16(ctx->mem + addr);
}

static void wr_word(gem_ctx_t *ctx, uint32_t base, int index, uint16_t value) {
    uint32_t addr;
    if (!gem_addr(ctx, base, (uint32_t)index * 2u, 2, &addr)) return;
    wr16(ctx->mem + addr, value);
}

static int16_t rd_signed(gem_ctx_t *ctx, uint32_t base, int index) {
    return (int16_t)rd_word(ctx, base, index);
}

/* The same two for a word named by its ADDRESS rather than by an array index — the model's own
 * state block and the MFDB fields, whose offsets are byte offsets. */
static uint16_t rd_word_at(gem_ctx_t *ctx, uint32_t addr) { return rd_word(ctx, addr, 0); }
static void wr_word_at(gem_ctx_t *ctx, uint32_t addr, uint16_t value) {
    wr_word(ctx, addr, 0, value);
}

static uint32_t rd_long(gem_ctx_t *ctx, uint32_t addr) {
    uint32_t at;
    if (!gem_addr(ctx, addr, 0, 4, &at)) return 0;
    return be32(ctx->mem + at);
}

/* ---- the VDI workstation state, which lives in the image (os.h) ---- */
static uint16_t vdi_state(gem_ctx_t *ctx, int field) {
    return rd_word_at(ctx, OS_VDI_STATE + (uint32_t)field);
}

static void vdi_set_state(gem_ctx_t *ctx, int field, uint16_t value) {
    wr_word_at(ctx, OS_VDI_STATE + (uint32_t)field, value);
}

/* The raster "the screen" means: the base the case declared, or Physbase/Logbase's if it declared
 * none. Its geometry is the workstation's own — an MFDB whose fd_addr is 0 does not describe it. */
static void screen_raster(gem_ctx_t *ctx, raster_t *raster) {
    uint32_t base = rd_long(ctx, OS_VDI_STATE + OS_VDI_OFF_SCREEN);
    raster->addr = base ? base : OS_SCREEN_BASE;
    raster->w = OS_SCREEN_W;
    raster->h = OS_SCREEN_H;
    raster->wdwidth = OS_SCREEN_WDWIDTH;
    raster->nplanes = OS_SCREEN_PLANES;
}

/* Every opcode that DRAWS opens with this: the screen the case declared, or a refusal. One helper
 * rather than the same three lines per opcode, so a drawing call cannot be added that skips the
 * validity test and addresses outside the image from a bad declared base. */
static int screen_or_refuse(gem_ctx_t *ctx, raster_t *screen) {
    screen_raster(ctx, screen);
    return !ctx->fault && raster_valid(screen);
}

/* Decode an MFDB into a raster the model can address. 0 unless every field describes something it
 * can serve: STANDARD format is a different plane layout and is refused rather than misread, and
 * `raster_valid` refuses extents that would address outside the image.
 *
 * `is_screen` is optional: only the DESTINATION's answer means anything (clipping is in screen
 * coordinates), and passing NULL for the source says so rather than filling a variable nobody
 * reads. */
static int mfdb_raster(gem_ctx_t *ctx, uint32_t mfdb, raster_t *raster, int *is_screen) {
    if (is_screen) *is_screen = 0;
    if (!mfdb) return 0;                        /* a null MFDB POINTER; fd_addr is a separate field */
    uint32_t fd_addr = rd_long(ctx, mfdb + MFDB_ADDR);
    if (ctx->fault) return 0;
    if (fd_addr == MFDB_SCREEN_ADDR) {          /* the workstation's own screen, whose geometry wins */
        screen_raster(ctx, raster);
        if (is_screen) *is_screen = 1;
        return !ctx->fault && raster_valid(raster);
    }
    if (rd_word_at(ctx, mfdb + MFDB_STAND) == MFDB_STANDARD_FORMAT) return 0;
    raster->addr = fd_addr;
    raster->w = rd_word_at(ctx, mfdb + MFDB_W);
    raster->h = rd_word_at(ctx, mfdb + MFDB_H);
    raster->wdwidth = rd_word_at(ctx, mfdb + MFDB_WDWIDTH);
    raster->nplanes = rd_word_at(ctx, mfdb + MFDB_NPLANES);
    if (ctx->fault) return 0;
    return raster_valid(raster);
}

/* ---- the clip rectangle, read ONCE per call --------------------------------------------------
 * `vs_clip`'s rectangle is five words of image state, so testing it per pixel was five image reads
 * per pixel for a fact that cannot change mid-call. Read here, then narrowed into the loop bounds.
 *
 * IT APPLIES ONLY WHERE THE DESTINATION IS THE SCREEN — an MFDB whose fd_addr is 0. That is the
 * VDI's own rule and not an omission: the clip rectangle is in screen coordinates, so a memory MFDB
 * has no place in them, INCLUDING one whose fd_addr happens to point at screen memory. A raster
 * named by address is a raster, and the VDI clips it no more than it clips a sprite bank. */
typedef struct { int on; int32_t x1, y1, x2, y2; } vdi_clip_t;

static void read_clip(gem_ctx_t *ctx, vdi_clip_t *clip) {
    clip->on = vdi_state(ctx, OS_VDI_OFF_CLIP_ON) != 0;
    clip->x1 = (int16_t)vdi_state(ctx, OS_VDI_OFF_CLIP_X1);
    clip->y1 = (int16_t)vdi_state(ctx, OS_VDI_OFF_CLIP_Y1);
    clip->x2 = (int16_t)vdi_state(ctx, OS_VDI_OFF_CLIP_X2);
    clip->y2 = (int16_t)vdi_state(ctx, OS_VDI_OFF_CLIP_Y2);
}

static void order(int32_t *lo, int32_t *hi) {
    if (*lo > *hi) { int32_t swap = *lo; *lo = *hi; *hi = swap; }
}

/* Narrow the step range [*first, *last] so that `origin + step` stays inside [lo, hi].
 *
 * NARROWING THE LOOP RATHER THAN TESTING EACH PIXEL is not an optimisation: the rectangle comes off
 * the emulated program's stack as four signed words, so a garbage one spans up to 65,536 steps of
 * nothing, and a per-pixel test would make that a HANG instead of a failure. Every step inside the
 * narrowed range is addressable, so no further test is needed. */
static void narrow_span(int32_t *first, int32_t *last, int32_t origin, int32_t lo, int32_t hi) {
    if (*first < lo - origin) *first = lo - origin;
    if (*last > hi - origin) *last = hi - origin;
}

/* ...and the two-raster form: keep both `src_origin + step` and `dst_origin + step` in extent. */
static void clip_span(int32_t *first, int32_t *last, int32_t src_origin, int32_t src_extent,
                      int32_t dst_origin, int32_t dst_extent) {
    narrow_span(first, last, src_origin, 0, src_extent - 1);
    narrow_span(first, last, dst_origin, 0, dst_extent - 1);
}

/* How many entries of each output array the call wrote. Every serviced opcode sets both, because a
 * game reads them and leaving the caller's values standing would report the PREVIOUS call's counts. */
static void set_output_counts(gem_ctx_t *ctx, uint16_t ptsout_pairs, uint16_t intout_entries) {
    wr_word(ctx, ctx->contrl, VDI_CONTRL_PTSOUT_N, ptsout_pairs);
    wr_word(ctx, ctx->contrl, VDI_CONTRL_INTOUT_N, intout_entries);
}

/* ---- the opcodes -------------------------------------------------------------------------- */

/* v_opnvwk (100): open a virtual workstation.
 *
 * THE WHOLE WORK_OUT IS WRITTEN, because the call REPORTS having written it: contrl[2]/contrl[4] say
 * 6 pairs and 45 entries, and a caller walking those arrays reads whatever was in its own memory for
 * the 42 the model has nothing to say about. Zeroed first and then the three determinate fields
 * filled in — zero is not a fabricated attribute table, it is the absence of one, and it is the same
 * on both sides.
 *
 * THE ATTRIBUTES COME FROM WORK_IN, which is what opening a workstation means: intin[6..9] are the
 * text colour, the fill interior, the fill style and the fill colour a real VDI installs from the
 * caller's own array. (Bubble Ghost passes 1 in every one of work_in[0..9].) The three the array
 * cannot express — the writing mode, the text height and the clip flag — take the VDI's defaults. */
static int vdi_v_opnvwk(gem_ctx_t *ctx) {
    for (int i = 0; i < OS_VDI_WORK_OUT_INTS; i++) wr_word(ctx, ctx->intout, i, 0);
    for (int i = 0; i < OS_VDI_WORK_OUT_POINTS * 2; i++) wr_word(ctx, ctx->ptsout, i, 0);
    vdi_set_state(ctx, OS_VDI_OFF_HANDLE, OS_VDI_HANDLE);
    vdi_set_state(ctx, OS_VDI_OFF_TEXT_COLOR, rd_word(ctx, ctx->intin, VDI_WORK_IN_TEXT_COLOR));
    vdi_set_state(ctx, OS_VDI_OFF_FILL_INTERIOR,
                  rd_word(ctx, ctx->intin, VDI_WORK_IN_FILL_INTERIOR));
    vdi_set_state(ctx, OS_VDI_OFF_FILL_STYLE, rd_word(ctx, ctx->intin, VDI_WORK_IN_FILL_STYLE));
    vdi_set_state(ctx, OS_VDI_OFF_FILL_COLOR, rd_word(ctx, ctx->intin, VDI_WORK_IN_FILL_COLOR));
    vdi_set_state(ctx, OS_VDI_OFF_WRITE_MODE, OS_VDI_DEFAULT_WRITE_MODE);
    vdi_set_state(ctx, OS_VDI_OFF_TEXT_HEIGHT, OS_VDI_DEFAULT_TEXT_HEIGHT);
    vdi_set_state(ctx, OS_VDI_OFF_CLIP_ON, 0);
    wr_word(ctx, ctx->contrl, VDI_CONTRL_HANDLE, OS_VDI_HANDLE);
    wr_word(ctx, ctx->intout, VDI_WORK_OUT_MAX_X, OS_SCREEN_MAX_X);
    wr_word(ctx, ctx->intout, VDI_WORK_OUT_MAX_Y, OS_SCREEN_MAX_Y);
    wr_word(ctx, ctx->intout, VDI_WORK_OUT_COLOURS, OS_SCREEN_COLOURS);
    set_output_counts(ctx, OS_VDI_WORK_OUT_POINTS, OS_VDI_WORK_OUT_INTS);
    return 1;
}

/* v_clsvwk (101): close it. The handle is the only state a close means anything to here. */
static int vdi_v_clsvwk(gem_ctx_t *ctx) {
    vdi_set_state(ctx, OS_VDI_OFF_HANDLE, 0);
    set_output_counts(ctx, 0, 0);
    return 1;
}

/* v_clrwk (3): clear the screen to colour 0. */
static int vdi_v_clrwk(gem_ctx_t *ctx) {
    raster_t screen;
    if (!screen_or_refuse(ctx, &screen)) return 0;
    memset(ctx->mem + screen.addr, 0, (size_t)raster_bytes(&screen));
    set_output_counts(ctx, 0, 0);
    return 1;
}

/* An attribute the model STORES AND ECHOES without interpreting it (the writing mode, the fill
 * interior and style). Returning what was set is what the real calls do, and a game reads it. */
static int vdi_record_attribute(gem_ctx_t *ctx, int field) {
    uint16_t value = rd_word(ctx, ctx->intin, 0);
    vdi_set_state(ctx, field, value);
    wr_word(ctx, ctx->intout, 0, value);
    set_output_counts(ctx, 0, 1);
    return 1;
}

/* ...and a COLOUR attribute, which the model does interpret: it is the pixel value a later draw
 * writes, so it is clamped to the pens the device has, exactly as the VDI clamps. */
static int vdi_set_colour(gem_ctx_t *ctx, int field) {
    int16_t requested = rd_signed(ctx, ctx->intin, 0);
    uint16_t pen = (uint16_t)(requested < 0 ? 0
                              : requested >= OS_SCREEN_COLOURS ? OS_SCREEN_COLOURS - 1 : requested);
    vdi_set_state(ctx, field, pen);
    wr_word(ctx, ctx->intout, 0, pen);
    set_output_counts(ctx, 0, 1);
    return 1;
}

/* vst_height (12): the model has ONE font, so the requested height is recorded and the answer is
 * always the 8x8 cell. TOS would pick among its 6x6/8x8/8x16 system fonts; see TRAP_MODEL.md. */
static int vdi_vst_height(gem_ctx_t *ctx) {
    vdi_set_state(ctx, OS_VDI_OFF_TEXT_HEIGHT, rd_word(ctx, ctx->ptsin, 1));
    wr_word(ctx, ctx->ptsout, VDI_HEIGHT_CHAR_W, OS_FONT_CELL_W);
    wr_word(ctx, ctx->ptsout, VDI_HEIGHT_CHAR_H, OS_FONT_CELL_H);
    wr_word(ctx, ctx->ptsout, VDI_HEIGHT_CELL_W, OS_FONT_CELL_W);
    wr_word(ctx, ctx->ptsout, VDI_HEIGHT_CELL_H, OS_FONT_CELL_H);
    set_output_counts(ctx, VDI_HEIGHT_PTSOUT_PAIRS, 0);
    return 1;
}

/* vs_clip (129): intin[0] turns clipping on or off; ptsin[0..3] is the rectangle, normalised here so
 * every later test is a plain range check. */
static int vdi_vs_clip(gem_ctx_t *ctx) {
    int32_t x1 = rd_signed(ctx, ctx->ptsin, 0), y1 = rd_signed(ctx, ctx->ptsin, 1);
    int32_t x2 = rd_signed(ctx, ctx->ptsin, 2), y2 = rd_signed(ctx, ctx->ptsin, 3);
    order(&x1, &x2);
    order(&y1, &y2);
    vdi_set_state(ctx, OS_VDI_OFF_CLIP_ON, rd_word(ctx, ctx->intin, 0) ? 1 : 0);
    vdi_set_state(ctx, OS_VDI_OFF_CLIP_X1, (uint16_t)x1);
    vdi_set_state(ctx, OS_VDI_OFF_CLIP_Y1, (uint16_t)y1);
    vdi_set_state(ctx, OS_VDI_OFF_CLIP_X2, (uint16_t)x2);
    vdi_set_state(ctx, OS_VDI_OFF_CLIP_Y2, (uint16_t)y2);
    set_output_counts(ctx, 0, 0);
    return 1;
}

/* The colour vr_recfl paints with, or -1 for an interior the model has no account of.
 *
 * The VDI's fill INTERIOR is what `vsf_interior` sets, and it decides the question before the fill
 * colour does: HOLLOW fills with the background (colour 0) and ignores the fill colour entirely,
 * SOLID fills with it. PATTERN, HATCH and USER-DEFINED each need a pattern table this model does not
 * have — inventing one would draw pixels no real machine draws — so they are REFUSED BY NAME rather
 * than quietly filled solid. */
static int vdi_fill_colour(gem_ctx_t *ctx) {
    switch (vdi_state(ctx, OS_VDI_OFF_FILL_INTERIOR)) {
    case VDI_FILL_HOLLOW: return 0;
    case VDI_FILL_SOLID:  return vdi_state(ctx, OS_VDI_OFF_FILL_COLOR);
    default:              return -1;               /* pattern / hatch / user-defined */
    }
}

/* vr_recfl (114): fill ptsin[0..3] on the screen, in the colour the fill interior selects, clipped
 * to the screen and to the clip rectangle. */
static int vdi_vr_recfl(gem_ctx_t *ctx) {
    raster_t screen;
    vdi_clip_t clip;
    if (!screen_or_refuse(ctx, &screen)) return 0;
    int32_t x1 = rd_signed(ctx, ctx->ptsin, 0), y1 = rd_signed(ctx, ctx->ptsin, 1);
    int32_t x2 = rd_signed(ctx, ctx->ptsin, 2), y2 = rd_signed(ctx, ctx->ptsin, 3);
    int colour = vdi_fill_colour(ctx);
    read_clip(ctx, &clip);
    order(&x1, &x2);
    order(&y1, &y2);
    if (ctx->fault || colour < 0) return 0;
    /* Narrowed to the screen and to the clip rectangle BEFORE the loop, for narrow_span's reason:
     * the rectangle is four signed words off the emulated stack, and iterating a 65,536-wide one
     * pixel by pixel would hang. */
    narrow_span(&x1, &x2, 0, 0, screen.w - 1);
    narrow_span(&y1, &y2, 0, 0, screen.h - 1);
    if (clip.on) {
        narrow_span(&x1, &x2, 0, clip.x1, clip.x2);
        narrow_span(&y1, &y2, 0, clip.y1, clip.y2);
    }
    for (int32_t y = y1; y <= y2; y++)
        for (int32_t x = x1; x <= x2; x++) {
            raster_at_t at = raster_locate(&screen, x, y);
            raster_at_set_pixel(ctx->mem, &at, screen.nplanes, colour);
        }
    set_output_counts(ctx, 0, 0);
    return 1;
}

/* v_gtext (8): the string in intin, one 16-bit character per entry, at ptsin[0..1].
 *
 * ALIGNMENT IS THE VDI DEFAULT (left, baseline), which vst_alignment is not modeled to change: x is
 * the left edge of the first cell and y is the BASELINE, so the glyph's eight rows occupy
 * [y - 7, y]. Only the glyph's set bits are written, in the text colour; the cell's background is
 * left alone and the writing mode is not consulted (TRAP_MODEL.md, Phase 12). */
static int vdi_v_gtext(gem_ctx_t *ctx) {
    raster_t screen;
    vdi_clip_t clip;
    if (!screen_or_refuse(ctx, &screen)) return 0;
    int32_t x = rd_signed(ctx, ctx->ptsin, 0), y = rd_signed(ctx, ctx->ptsin, 1);
    int count = rd_word(ctx, ctx->contrl, VDI_CONTRL_INTIN_N);
    int colour = vdi_state(ctx, OS_VDI_OFF_TEXT_COLOR);
    read_clip(ctx, &clip);
    if (ctx->fault) return 0;
    for (int i = 0; i < count; i++) {
        uint8_t ch = (uint8_t)rd_word(ctx, ctx->intin, i);
        if (ctx->fault) return 0;
        int32_t left = x + (int32_t)i * RASTER_FONT_W;
        int32_t top = y - (RASTER_FONT_H - 1);
        /* The cell's own eight-by-eight window, narrowed once per character rather than per pixel. */
        int32_t col_first = 0, col_last = RASTER_FONT_W - 1;
        int32_t row_first = 0, row_last = RASTER_FONT_H - 1;
        narrow_span(&col_first, &col_last, left, 0, screen.w - 1);
        narrow_span(&row_first, &row_last, top, 0, screen.h - 1);
        if (clip.on) {
            narrow_span(&col_first, &col_last, left, clip.x1, clip.x2);
            narrow_span(&row_first, &row_last, top, clip.y1, clip.y2);
        }
        for (int32_t row = row_first; row <= row_last; row++) {
            uint8_t bits = raster_font_row(ch, (int)row);
            for (int32_t col = col_first; col <= col_last; col++) {
                if (!(bits & (uint8_t)(0x80u >> col))) continue;   /* leftmost pixel is bit 7 */
                raster_at_t at = raster_locate(&screen, left + col, top + row);
                raster_at_set_pixel(ctx->mem, &at, screen.nplanes, colour);
            }
        }
    }
    set_output_counts(ctx, 0, 0);
    return 1;
}

/* vro_cpyfm (109): copy the source rectangle onto the destination anchor under logic op intin[0].
 *
 * The EXTENT IS THE SOURCE'S — the VDI does not scale, and the destination rectangle contributes
 * only its top-left corner. A pixel whose source or destination falls outside its own raster is
 * skipped, which is the clipping that lets a sprite walk off the top of the screen.
 *
 * THE COPY DIRECTION IS CHOSEN, not fixed. Source and destination may be the SAME raster and may
 * overlap — scrolling a window is exactly that — and a copy that always ran top-left to
 * bottom-right would re-read pixels it had already written and smear the source down the screen.
 * Rows run backwards when the destination is BELOW the source and columns backwards when it is to
 * the RIGHT, which is the ordinary blit rule: every source pixel is then read before the write that
 * would have overwritten it. Chosen unconditionally rather than only on overlap, because for
 * disjoint rasters the two orders write exactly the same bytes. */
static int vdi_vro_cpyfm(gem_ctx_t *ctx) {
    unsigned op = rd_word(ctx, ctx->intin, 0);
    uint32_t src_mfdb = ((uint32_t)rd_word(ctx, ctx->contrl, VDI_CONTRL_SRC_MFDB)
                         << VDI_MFDB_WORD_BITS)
                        | rd_word(ctx, ctx->contrl, VDI_CONTRL_SRC_MFDB + 1);
    uint32_t dst_mfdb = ((uint32_t)rd_word(ctx, ctx->contrl, VDI_CONTRL_DST_MFDB)
                         << VDI_MFDB_WORD_BITS)
                        | rd_word(ctx, ctx->contrl, VDI_CONTRL_DST_MFDB + 1);
    raster_t src, dst;
    vdi_clip_t clip;
    /* Only the DESTINATION's answer is read: the clip rectangle is in screen coordinates, so it
     * governs where a copy lands and says nothing about where it came from — hence NULL for the
     * source's, rather than a variable nothing consults. */
    int dst_is_screen;
    if (ctx->fault || op >= RASTER_OP_COUNT) return 0;
    if (!mfdb_raster(ctx, src_mfdb, &src, NULL)) return 0;
    if (!mfdb_raster(ctx, dst_mfdb, &dst, &dst_is_screen)) return 0;
    if (src.nplanes != dst.nplanes) return 0;      /* the model has no plane conversion */

    int32_t sx1 = rd_signed(ctx, ctx->ptsin, VDI_CPYFM_SRC_X1);
    int32_t sy1 = rd_signed(ctx, ctx->ptsin, VDI_CPYFM_SRC_Y1);
    int32_t sx2 = rd_signed(ctx, ctx->ptsin, VDI_CPYFM_SRC_X2);
    int32_t sy2 = rd_signed(ctx, ctx->ptsin, VDI_CPYFM_SRC_Y2);
    int32_t dx1 = rd_signed(ctx, ctx->ptsin, VDI_CPYFM_DST_X1);
    int32_t dy1 = rd_signed(ctx, ctx->ptsin, VDI_CPYFM_DST_Y1);
    read_clip(ctx, &clip);
    if (ctx->fault) return 0;
    order(&sx1, &sx2);
    order(&sy1, &sy2);
    int32_t col_first = 0, col_last = sx2 - sx1, row_first = 0, row_last = sy2 - sy1;
    clip_span(&col_first, &col_last, sx1, src.w, dx1, dst.w);
    clip_span(&row_first, &row_last, sy1, src.h, dy1, dst.h);
    /* The clip rectangle narrows the DESTINATION span, once, and only where the destination is the
     * screen — see read_clip's header for why a memory MFDB is never clipped. */
    if (dst_is_screen && clip.on) {
        narrow_span(&col_first, &col_last, dx1, clip.x1, clip.x2);
        narrow_span(&row_first, &row_last, dy1, clip.y1, clip.y2);
    }
    /* An entirely clipped rectangle narrows to an EMPTY range, and the walk below counts to its end
     * rather than testing an ordering — so it has to return here, before a `first > last` range
     * would step past the end it is looking for and run away. */
    if (col_first > col_last || row_first > row_last) {
        set_output_counts(ctx, 0, 0);
        return 1;
    }
    int32_t row_step = dy1 > sy1 ? -1 : 1, col_step = dx1 > sx1 ? -1 : 1;
    int32_t row_start = row_step > 0 ? row_first : row_last;
    int32_t row_end   = row_step > 0 ? row_last + 1 : row_first - 1;
    int32_t col_start = col_step > 0 ? col_first : col_last;
    int32_t col_end   = col_step > 0 ? col_last + 1 : col_first - 1;

    for (int32_t row = row_start; row != row_end; row += row_step) {
        for (int32_t col = col_start; col != col_end; col += col_step) {
            raster_at_t from = raster_locate(&src, sx1 + col, sy1 + row);
            raster_at_t to = raster_locate(&dst, dx1 + col, dy1 + row);
            for (int plane = 0; plane < src.nplanes; plane++) {
                int bit = raster_logic_op((int)op,
                                          raster_at_plane_bit(ctx->mem, &from, plane),
                                          raster_at_plane_bit(ctx->mem, &to, plane));
                raster_at_set_plane_bit(ctx->mem, &to, plane, bit);
            }
        }
    }
    set_output_counts(ctx, 0, 0);
    return 1;
}

/* vq_mouse (124) / vq_key_s (128): report the poked input state. Neither CONSUMES it — a real
 * driver's position and shift mask persist until the hardware moves them. */
static int vdi_vq_mouse(gem_ctx_t *ctx) {
    wr_word(ctx, ctx->intout, 0, rd_word_at(ctx, OS_MOUSE + OS_MOUSE_OFF_BUTTONS));
    wr_word(ctx, ctx->ptsout, 0, rd_word_at(ctx, OS_MOUSE + OS_MOUSE_OFF_X));
    wr_word(ctx, ctx->ptsout, 1, rd_word_at(ctx, OS_MOUSE + OS_MOUSE_OFF_Y));
    set_output_counts(ctx, VDI_MOUSE_PTSOUT_PAIRS, 1);
    return 1;
}

static int vdi_vq_key_s(gem_ctx_t *ctx) {
    wr_word(ctx, ctx->intout, 0, rd_word_at(ctx, OS_KEY_SHIFT));
    set_output_counts(ctx, 0, 1);
    return 1;
}

/* v_show_c (122) / v_hide_c (123): the graphics cursor is not in the image, so the call is a
 * LEDGER ENTRY and nothing else. */
static int vdi_cursor(gem_ctx_t *ctx, os_event_t *event, uint16_t visible) {
    event->kind = OS_EVENT_VDI_CURSOR;
    event->value = visible;
    set_output_counts(ctx, 0, 0);
    return 1;
}

static int vdi_dispatch(gem_ctx_t *ctx, os_event_t *event) {
    switch (rd_word(ctx, ctx->contrl, VDI_CONTRL_OPCODE)) {
    case VDI_V_CLRWK:       return vdi_v_clrwk(ctx);
    case VDI_V_GTEXT:       return vdi_v_gtext(ctx);
    case VDI_VST_HEIGHT:    return vdi_vst_height(ctx);
    case VDI_VST_COLOR:     return vdi_set_colour(ctx, OS_VDI_OFF_TEXT_COLOR);
    case VDI_VSF_INTERIOR:  return vdi_record_attribute(ctx, OS_VDI_OFF_FILL_INTERIOR);
    case VDI_VSF_STYLE:     return vdi_record_attribute(ctx, OS_VDI_OFF_FILL_STYLE);
    case VDI_VSF_COLOR:     return vdi_set_colour(ctx, OS_VDI_OFF_FILL_COLOR);
    case VDI_VSWR_MODE:     return vdi_record_attribute(ctx, OS_VDI_OFF_WRITE_MODE);
    case VDI_V_OPNVWK:      return vdi_v_opnvwk(ctx);
    case VDI_V_CLSVWK:      return vdi_v_clsvwk(ctx);
    case VDI_VRO_CPYFM:     return vdi_vro_cpyfm(ctx);
    case VDI_VR_RECFL:      return vdi_vr_recfl(ctx);
    case VDI_V_SHOW_C:      return vdi_cursor(ctx, event, 1);
    case VDI_V_HIDE_C:      return vdi_cursor(ctx, event, 0);
    case VDI_VQ_MOUSE:      return vdi_vq_mouse(ctx);
    case VDI_VQ_KEY_S:      return vdi_vq_key_s(ctx);
    case VDI_VS_CLIP:       return vdi_vs_clip(ctx);
    default:                return 0;
    }
}

/* ---- the AES ------------------------------------------------------------------------------
 * The AES fills its own contrl counts before the trap (its `crys_if` binding does it from a table),
 * so unlike the VDI there is nothing here to report back but the intout entries themselves. */
static int aes_dispatch(gem_ctx_t *ctx, os_event_t *event) {
    switch (rd_word(ctx, ctx->contrl, VDI_CONTRL_OPCODE)) {
    case AES_APPL_INIT:
        wr_word(ctx, ctx->intout, 0, OS_AES_AP_ID);
        return 1;
    case AES_APPL_EXIT:
        wr_word(ctx, ctx->intout, 0, 1);                     /* 1 = success, 0 = error */
        return 1;
    case AES_GRAF_HANDLE:
        wr_word(ctx, ctx->intout, 0, OS_VDI_HANDLE);
        wr_word(ctx, ctx->intout, 1, OS_FONT_CELL_W);        /* wchar */
        wr_word(ctx, ctx->intout, 2, OS_FONT_CELL_H);        /* hchar */
        wr_word(ctx, ctx->intout, 3, OS_FONT_CELL_W);        /* wbox  */
        wr_word(ctx, ctx->intout, 4, OS_FONT_CELL_H);        /* hbox  */
        return 1;
    case AES_GRAF_MOUSE:
        /* The GEM pointer is not in the image: showing or hiding it is a ledger entry. */
        event->kind = OS_EVENT_GEM_MOUSE;
        event->value = rd_word(ctx, ctx->intin, 0);
        wr_word(ctx, ctx->intout, 0, 1);
        return 1;
    default:
        return 0;
    }
}

/* One longword of the parameter block, SHORT-CIRCUITING on a fault: the block's own pointer comes
 * off the emulated stack, so once one slot is unreachable the rest are being read from an address
 * the model has already refused. */
static uint32_t pblk_slot(gem_ctx_t *ctx, uint32_t pblk, int index) {
    if (ctx->fault) return 0;
    return rd_long(ctx, pblk + (uint32_t)index * 4u);
}

int gem_dispatch(uint8_t *mem, uint32_t d0, uint32_t pblk, os_event_t *event) {
    gem_ctx_t ctx = {mem, 0, 0, 0, 0, 0, 0};
    event->kind = OS_EVENT_NONE;
    event->value = 0;
    if (d0 != GEM_AES && d0 != GEM_VDI) return 0;

    /* The parameter block itself: five longs for the VDI, six for the AES. Read the five both
     * subsystems share, then the AES's intout from its own slot. */
    ctx.contrl = pblk_slot(&ctx, pblk, VDI_PB_CONTRL);
    if (d0 == GEM_VDI) {
        ctx.intin  = pblk_slot(&ctx, pblk, VDI_PB_INTIN);
        ctx.ptsin  = pblk_slot(&ctx, pblk, VDI_PB_PTSIN);
        ctx.intout = pblk_slot(&ctx, pblk, VDI_PB_INTOUT);
        ctx.ptsout = pblk_slot(&ctx, pblk, VDI_PB_PTSOUT);
    } else {
        ctx.intin  = pblk_slot(&ctx, pblk, AES_PB_INTIN);
        ctx.intout = pblk_slot(&ctx, pblk, AES_PB_INTOUT);
    }
    if (ctx.fault) return 0;

    int modeled = d0 == GEM_VDI ? vdi_dispatch(&ctx, event) : aes_dispatch(&ctx, event);
    if (!modeled || ctx.fault) {
        /* A faulted call may have reported an event before it faulted; drop it, or a refused run
         * would still push an entry onto one side's ledger. */
        event->kind = OS_EVENT_NONE;
        event->value = 0;
        return 0;
    }
    return 1;
}
