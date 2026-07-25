/* object_list.c — remaster of draw_object_list (recreate's g_draw_object_list @0x1306e), its
 * obj_dispatch jump table, and the mid-level sprite draw-handlers (draw_obj_sprite_hi, handler_lo/dbl,
 * the objsprite width wrappers, and the objshift2 "P-prefix + glue" family).
 *
 * This is the register-glue layer between draw_game_objects and the verified fine-x blit engines
 * (rm_objsprite / rm_blit_objshift / rm_blit_objshift2 in blit.c). Two nested loops walk the object
 * list; per object a SPECIAL pass (flag word negative) and a NORMAL pass (keyed on the flag's low 6
 * bits) resolve a per-object record and dispatch through obj_type_jumptable to a handler.
 *
 * recreate threads one flat image; here each thing the dispatcher touches is its own arena in
 * ObjListCtx: `px` (the only WRITE target) at draw_buf-relative offsets, `buf_a` records, `buf_c`
 * sprite pixels, and the const STATIC tables. Every offset/cursor keeps recreate's arithmetic 1:1
 * (16-bit wraps mirrored) so the output is byte-identical (see test/test_object_list_rm.py).
 */
#include "game.h"
#include "screen.h"
#include "st.h"

/* STE hardware-blitter build (PERF30 C4): route the fixed-pass fine-x blit through the blitter dispatch
 * (BASE family on the blitter, CLIP family on the CPU asm engine — a pinned hybrid). Overriding the macro
 * HERE — the sole RM_BLIT_OBJSHIFT2 call site — keeps the seam out of include/game.h. */
#ifdef GAME_STE
#include "blitter.h"
#undef RM_BLIT_OBJSHIFT2
#define RM_BLIT_OBJSHIFT2 rm_blit_objshift2_dispatch
#endif

/* Jump-table resolution: recreate stores, per jumpidx, a word offset that added to the table base
 * (Ghidra 0x13144) gives the handler's Ghidra address. Those offsets are position-independent (a
 * difference of two code addresses), so we reconstruct the same key and switch on it — no code is
 * called; the address is purely a dispatch label. */
#define JUMPTABLE_BASE   0x13144

/* Handler dispatch labels (Ghidra addresses = JUMPTABLE_BASE + the stored word offset). */
#define OBJ_H_NOOP 0x13df8
#define OBJ_H_T1   0x13642
#define OBJ_H_T2   0x1352c
#define OBJ_H_W88  0x133b6
#define OBJ_H_T4   0x131f6
#define OBJ_H_STUB 0x131ac
#define OBJ_H_LO1  0x1466a
#define OBJ_H_LO2  0x144b2
#define OBJ_H_T16      0x1363e
#define OBJ_H_T49      0x13528
#define OBJ_H_T3       0x133b2
#define OBJ_H_T41      0x13628
#define OBJ_H_T42      0x13512
#define OBJ_H_HI0      0x131f2
#define OBJ_H_XF0      0x131ca
#define OBJ_H_A6GATE_T4  0x131d0
#define OBJ_H_A6GATE_W88 0x131e0
#define OBJ_H_PRE_T1_A6    0x13622
#define OBJ_H_PRE_T1_XFORM 0x1361c
#define OBJ_H_T42PRE   0x1350c
#define OBJ_H_T4CPRE   0x13506
#define OBJ_H_PREW88_44 0x133ac
#define OBJ_H_PREW88_4E 0x133a6
#define OBJ_H_DBL      0x1465c
#define OBJ_H_LO_FULL  0x14664
#define OBJ_H_DBL2     0x144a2
#define OBJ_H_LO_FULL2 0x144ac
#define OBJ_H_P24 0x13dfa
#define OBJ_H_P26 0x13e48
#define OBJ_H_P28 0x13e50
#define OBJ_H_P2A 0x13e5c
#define OBJ_H_P2C 0x13e7c
#define OBJ_H_P2E 0x13e88
#define OBJ_H_P30 0x13eae
#define OBJ_H_P32 0x13eb4
#define OBJ_H_P34 0x13ec0
#define OBJ_H_P36 0x13ec6
#define OBJ_H_P38 0x13ed2

/* Object-list layout + field offsets (recreate's draw_object_list constants). */
#define OBJ_SPECIAL_BASE 0x21d0     /* buf_a-relative base of the special-object record (+rec_off) */
#define OBJ_TYPE_BASE    0x8a0      /* buf_a-relative base of the per-type records */
#define OBJ_TYPE_STRIDE  0xd0       /* bytes per per-type record */
#define OBJ_COLOUR_OFF   0x10       /* colour word at type_base - this */
#define OBJ_VSEED_OFF    0xb        /* vertical seed byte at data_base - this */
#define OBJ_REC_ROWS     0x04       /* rows-1 word */
#define OBJ_REC_JUMP     0x06       /* jumptable index word */
#define OBJ_REC_DSTADJ   0x08       /* a0 += this word (normal) / special record cursor */
#define OBJ_REC_XADJ     0x0a       /* x += this word (normal) / normal record cursor */
#define OBJ_HANDLER_SRCADJ 0x02     /* handler_lo: src += word@(cursor + this + parity) */
#define OBJ_BONUS_MIN_TYPE 6
#define OBJ_ROWS_ONLY    0x3f
#define OBJ_ROW_OBJECTS  0xe        /* inner loop runs this+1 (=15) objects per row */
#define OBJ_D6_STEP      0x10
#define OBJ_STUB_X_ADV   0x40
#define OBJ_STUB_SRC_ADV 0x20
#define OBJD_WIDTH       0xa0

/* objshift2 P-prefix constants. */
#define OBJSH2P_SUBCELL_X 0x30
#define OBJSH2P_SUBCELL_S 0xc

/* view-transform record masks (obj_view_xform). */
#define VIEW_XFORM_OFF_MASK 0xffe0
#define VIEW_XFORM_ROW_MASK 0x001f

/* draw_obj_sprite_hi / tail modes (the per-row stride the objshift leaf reads). */
#define OBJH_MODE_MAIN  0x8
#define OBJH_MODE_TAIL  0xa8
#define OBJH_BAND_LO    0x3ac0      /* fixed dst-band offset from draw_buf (handler_lo full entry) */
#define OBJH_PARITY_MASK 0x2
#define OBJH_SRC_REWIND 0xa0

/* P24 global-byte flag path. */
#define OBJ_P24_FLAG_ON  0x31
#define OBJ_P24_SRC2_OFF 0xb1f8
#define OBJ_P24_X3_OFF   0xd0
#define OBJ_P24_SRC3_OFF 0x34
#define OBJ_XFORM_VIEW_BIT 0x4

/* set_low_byte (68k `.b` op on a word register) now lives in st.h, shared with sound.c. */

/* ---- objsprite width wrappers (map to rm_objsprite / rm_objsprite_alt) ----
 * width_idx: t4=0, w88=1, t2=2, t1=3. The wrappers differ only in how they derive the dst base and
 * (for the hi/xform families) x / rows / src before joining the shared fine-x prologue. */

static void osp(const ObjListCtx *c, uint16_t x, uint16_t rows_m1, uint32_t dst, uint32_t src, int wi) {
    rm_objsprite(c->px, dst, c->buf_c, src, x, rows_m1, wi);
}

/* draw_obj_sprite_hi @0x14620 — mode-8 first pass; returns the registers renamed for the caller's
 * second (width-prologue) pass. rec_cursor is a buf_a offset (rec+0xa). */
struct obj_hi_out { uint16_t x_out; uint16_t rows_out; uint32_t dst_out; uint32_t src_out; };

static struct obj_hi_out draw_obj_sprite_hi(const ObjListCtx *c, uint16_t x, uint16_t colour,
                                            uint16_t width, uint16_t rows_seed, uint16_t voff,
                                            uint32_t dst, uint32_t src, uint32_t rec_cursor) {
    uint16_t rows_copy = rows_seed;
    uint32_t rec_xoff = rec_cursor - 2;                          /* a2 = rec+8 */
    uint16_t xoff = be16(c->buf_a + rec_xoff);
    dst = (uint32_t)(dst - sx16(xoff));
    dst = (uint32_t)(dst + sx16(voff));
    uint16_t base_col = (uint16_t)(xoff + x);

    uint16_t view = (uint16_t)(c->view_flags >> 1);
    uint8_t rows_byte = c->buf_a[rec_xoff + 4 + view];
    uint16_t rows_m1 = set_low_byte(rows_seed, rows_byte);

    uint32_t dst_top = (uint32_t)(dst - sx16(width));
    uint16_t height = (uint16_t)(width * rows_byte);
    dst_top = (uint32_t)(dst_top - sx16(height));

    RM_BLIT_OBJSHIFT(c->px, dst, c->buf_c, src, x, colour, rows_m1, OBJH_MODE_MAIN,
                     c->color_pairs, /*base_cells=*/1);

    struct obj_hi_out out = { base_col, rows_copy, dst_top,
                              (uint32_t)(src - sx16(OBJH_SRC_REWIND)) };
    return out;
}

/* handler_lo (0x1466a mid / 0x14664 full): src += per-view-parity record word, tail blit at the
 * base_cells width family. The full entry rebuilds dst from draw_buf + a fixed band. */
static void obj_handler_lo(const ObjListCtx *c, uint16_t x, uint16_t colour, uint16_t rows_m1,
                           uint32_t dst, uint32_t src, uint32_t rec_cursor, int base_cells) {
    uint16_t parity = (uint16_t)(OBJH_PARITY_MASK & c->view_parity);
    src = (uint32_t)(src + sx16(be16(c->buf_a + rec_cursor + OBJ_HANDLER_SRCADJ + parity)));
    RM_BLIT_OBJSHIFT(c->px, dst, c->buf_c, src, x, colour, rows_m1, OBJH_MODE_TAIL,
                     c->color_pairs, base_cells);
}

static void obj_handler_lo_full(const ObjListCtx *c, uint16_t x, uint16_t colour, uint16_t rows_m1,
                                uint32_t src, uint32_t rec_cursor, int base_cells) {
    uint32_t dst = (uint32_t)(c->draw_buf + sx16(OBJH_BAND_LO));
    obj_handler_lo(c, x, colour, rows_m1, dst, src, rec_cursor, base_cells);
}

/* handler_dbl (0x1465c / 0x144a2): mode-8 hi pass, then the mode-0xa8 tail at the base_cells family. */
static void obj_handler_dbl(const ObjListCtx *c, uint16_t x, uint16_t colour, uint16_t voff,
                            uint32_t dst, uint32_t src, uint32_t rec_cursor, uint16_t rows_seed,
                            int base_cells) {
    struct obj_hi_out r = draw_obj_sprite_hi(c, x, colour, OBJD_WIDTH, rows_seed, voff, dst, src,
                                             rec_cursor);
    RM_BLIT_OBJSHIFT(c->px, r.dst_out, c->buf_c, r.src_out, r.x_out, colour, r.rows_out,
                     OBJH_MODE_TAIL, c->color_pairs, base_cells);
}

/* objsprite hi-pass wrapper (t3/t49/t16/hi0): mode-8 pass then a fine-x prologue on the renamed regs. */
static void objsprite_hi_wrapper(const ObjListCtx *c, uint16_t x, uint16_t colour, uint16_t rows_seed,
                                 uint16_t voff, uint32_t dst, uint32_t src, uint32_t rec_cursor, int wi) {
    struct obj_hi_out r = draw_obj_sprite_hi(c, x, colour, OBJD_WIDTH, rows_seed, voff, dst, src,
                                             rec_cursor);
    osp(c, r.x_out, r.rows_out, r.dst_out, r.src_out, wi);
}

/* a6-prefix wrapper (t34/t33/t32): dst = draw_buf + word@(rec_cursor-2), then a fresh prologue. */
static void objsprite_a6_wrapper(const ObjListCtx *c, uint16_t x, uint16_t rows_m1, uint32_t rec_cursor,
                                 uint32_t src, int wi) {
    uint32_t dst = (uint32_t)(c->draw_buf + sx16(be16(c->buf_a + rec_cursor - 2)));
    osp(c, x, rows_m1, dst, src, wi);
}

/* view-transform wrapper (t39/t38/t37/xf0): adjust dst/src/rows via the per-view record, then blit. */
static void objsprite_xform_wrapper(const ObjListCtx *c, uint16_t x, uint16_t rows_m1, uint32_t src,
                                    uint32_t rec_cursor, int wi) {
    uint32_t rec_ptr = sx16(be16(c->buf_a + rec_cursor - 2));   /* offset into view_xform (a2 predec) */
    uint16_t view2 = (uint16_t)(c->view_flags * 2);
    rec_ptr += sx16(view2);
    uint32_t dst = c->draw_buf;
    src = (uint32_t)(src - sx16(be16(c->view_xform + rec_ptr)));
    rec_ptr += 2;
    uint16_t rec1 = be16(c->view_xform + rec_ptr);
    dst = (uint32_t)(dst + sx16((uint16_t)(rec1 & VIEW_XFORM_OFF_MASK)));
    uint16_t rows_out = (uint16_t)(rows_m1 - (uint16_t)(rec1 & VIEW_XFORM_ROW_MASK));
    osp(c, x, rows_out, dst, src, wi);
}

/* scan wrapper (t41/t42): dst = draw_buf + word@rec_cursor; x rebuilt from the list/xoff streams. */
static void objsprite_scan_wrapper(const ObjListCtx *c, uint16_t rows_m1, uint32_t rec_cursor,
                                   const uint8_t *xoff, uint32_t xoff_off,
                                   const uint8_t *list, uint32_t list_off, uint32_t src, int wi) {
    uint32_t dst = (uint32_t)(c->draw_buf + sx16(be16(c->buf_a + rec_cursor)));
    uint32_t rec_next = rec_cursor + 2;
    int16_t neg_scan = (int16_t)-(int16_t)c->obj_scan_off;
    uint16_t x = (uint16_t)(be16(list + list_off + sx16((uint16_t)neg_scan))
                            + be16(xoff + xoff_off)
                            + be16(c->buf_a + rec_next));
    osp(c, x, rows_m1, dst, src, wi);
}

/* a6-prefix then view&4-gated width selection (0x131d0 / 0x131e0). */
static void obj_handler_a6gate_t4(const ObjListCtx *c, uint16_t x, uint16_t rows_m1, uint32_t src,
                                  uint32_t rec_cursor) {
    uint32_t dst = (uint32_t)(c->draw_buf + sx16(be16(c->buf_a + rec_cursor - 2)));
    osp(c, x, rows_m1, dst, src, 0);                                 /* t4 */
    if (c->view_flags & OBJ_XFORM_VIEW_BIT)
        osp(c, (uint16_t)(x + OBJ_STUB_X_ADV), rows_m1, dst, src + OBJ_STUB_SRC_ADV, 3);   /* t1 */
}

static void obj_handler_a6gate_w88(const ObjListCtx *c, uint16_t x, uint16_t rows_m1, uint32_t src,
                                   uint32_t rec_cursor) {
    uint32_t dst = (uint32_t)(c->draw_buf + sx16(be16(c->buf_a + rec_cursor - 2)));
    if (c->view_flags & OBJ_XFORM_VIEW_BIT) osp(c, x, rows_m1, dst, src, 0);   /* t4 */
    else                                    osp(c, x, rows_m1, dst, src, 1);   /* w88 */
}

/* ---- objshift2 "P-prefix + glue" family ---- */

static uint32_t objshift2_prefix_dst(const ObjListCtx *c, uint16_t rows_m1) {
    uint32_t table = sx16(c->view_flags);                           /* adda.w view_flags,a2 */
    return (uint32_t)(c->draw_buf + sx16(be16(c->objsh2p_tbl + table + sx16(rows_m1))));
}

static void objshift2_glue(const ObjListCtx *c, uint16_t x, uint16_t rows, uint32_t dst, uint32_t src,
                           int groups) {
    for (int i = 0; i <= groups; i++)
        RM_BLIT_OBJSHIFT2(c->px, dst, c->buf_c, src + OBJSH2P_SUBCELL_S * i,
                          (uint16_t)(x + OBJSH2P_SUBCELL_X * i), rows, /*width_idx=*/0);
}

static void obj_handler_p24(const ObjListCtx *c, uint16_t x, uint16_t rows_m1, uint32_t src) {
    uint32_t dp = objshift2_prefix_dst(c, rows_m1);
    if (c->p24_flag == OBJ_P24_FLAG_ON) {
        RM_BLIT_OBJSHIFT2(c->px, dp, c->buf_c, src, x, /*rows=*/0x2a, /*width_idx=*/0);   /* stage 1 */
        uint16_t x2 = (uint16_t)(OBJSH2P_SUBCELL_X + x);
        uint32_t src2 = OBJ_P24_SRC2_OFF;
        objshift2_glue(c, x2, /*rows=*/0x26, dp, src2, /*groups=*/2);
        RM_BLIT_OBJSHIFT2(c->px, dp, c->buf_c, src2 + OBJSH2P_SUBCELL_S * (2 + 1),
                          (uint16_t)(x2 + OBJSH2P_SUBCELL_X * (2 + 1)), /*rows=*/0x26, 2);
        RM_BLIT_OBJSHIFT2(c->px, dp, c->buf_c, src + OBJ_P24_SRC3_OFF,
                          (uint16_t)(x + OBJ_P24_X3_OFF), /*rows=*/0x2a, 0);                /* stage 3 */
    } else {
        objshift2_glue(c, x, /*rows=*/0x2a, dp, src, /*groups=*/4);
        RM_BLIT_OBJSHIFT2(c->px, dp, c->buf_c, src + OBJSH2P_SUBCELL_S * (4 + 1),
                          (uint16_t)(x + OBJSH2P_SUBCELL_X * (4 + 1)), /*rows=*/0x2a, 2);
    }
}

/* P-prefix + glue(g) + optional final blit (P26..P38). rows/glue-groups/final width per handler. */
static void obj_handler_p_glue(const ObjListCtx *c, uint16_t x, uint16_t rows_m1, uint32_t src,
                               uint16_t rows, int groups, int final_wi) {
    uint32_t dp = objshift2_prefix_dst(c, rows_m1);
    objshift2_glue(c, x, rows, dp, src, groups);
    if (final_wi >= 0)
        RM_BLIT_OBJSHIFT2(c->px, dp, c->buf_c, src + OBJSH2P_SUBCELL_S * (groups + 1),
                          (uint16_t)(x + OBJSH2P_SUBCELL_X * (groups + 1)), rows, final_wi);
}

/* ---- the jump-table dispatch ---- */
static void obj_dispatch(const ObjListCtx *c, uint16_t jumpidx, uint16_t x, uint16_t colour,
                         uint16_t rows_m1, uint32_t dst, uint32_t src, uint32_t rec_cursor,
                         uint16_t voff, const uint8_t *xoff, uint32_t xoff_off,
                         const uint8_t *list, uint32_t list_off) {
    int16_t off = (int16_t)be16(c->jumptable + jumpidx);
    uint32_t target = (uint32_t)(JUMPTABLE_BASE + off);
    switch (target) {
        case OBJ_H_NOOP: break;
        case OBJ_H_T1:  osp(c, x, rows_m1, dst, src, 3); break;
        case OBJ_H_T2:  osp(c, x, rows_m1, dst, src, 2); break;
        case OBJ_H_W88: osp(c, x, rows_m1, dst, src, 1); break;
        case OBJ_H_T4:  osp(c, x, rows_m1, dst, src, 0); break;
        case OBJ_H_STUB:
            osp(c, x, rows_m1, dst, src, 0);
            osp(c, (uint16_t)(x + OBJ_STUB_X_ADV), rows_m1, dst, src + OBJ_STUB_SRC_ADV, 3);
            break;
        case OBJ_H_LO1: obj_handler_lo(c, x, colour, rows_m1, dst, src, rec_cursor, 1); break;
        case OBJ_H_LO2: obj_handler_lo(c, x, colour, rows_m1, dst, src, rec_cursor, 2); break;

        case OBJ_H_T3:  objsprite_hi_wrapper(c, x, colour, rows_m1, voff, dst, src, rec_cursor, 1); break;
        case OBJ_H_T49: objsprite_hi_wrapper(c, x, colour, rows_m1, voff, dst, src, rec_cursor, 2); break;
        case OBJ_H_T16: objsprite_hi_wrapper(c, x, colour, rows_m1, voff, dst, src, rec_cursor, 3); break;
        case OBJ_H_HI0: objsprite_hi_wrapper(c, x, colour, rows_m1, voff, dst, src, rec_cursor, 0); break;

        case OBJ_H_T41: objsprite_scan_wrapper(c, rows_m1, rec_cursor, xoff, xoff_off, list, list_off, src, 3); break;
        case OBJ_H_T42: objsprite_scan_wrapper(c, rows_m1, rec_cursor, xoff, xoff_off, list, list_off, src, 2); break;

        case OBJ_H_PREW88_44: objsprite_a6_wrapper(c, x, rows_m1, rec_cursor, src, 1); break;
        case OBJ_H_T42PRE:    objsprite_a6_wrapper(c, x, rows_m1, rec_cursor, src, 2); break;
        case OBJ_H_PRE_T1_A6: objsprite_a6_wrapper(c, x, rows_m1, rec_cursor, src, 3); break;

        case OBJ_H_PREW88_4E:    objsprite_xform_wrapper(c, x, rows_m1, src, rec_cursor, 1); break;
        case OBJ_H_T4CPRE:       objsprite_xform_wrapper(c, x, rows_m1, src, rec_cursor, 2); break;
        case OBJ_H_PRE_T1_XFORM: objsprite_xform_wrapper(c, x, rows_m1, src, rec_cursor, 3); break;
        case OBJ_H_XF0:          objsprite_xform_wrapper(c, x, rows_m1, src, rec_cursor, 0); break;

        case OBJ_H_A6GATE_T4:  obj_handler_a6gate_t4(c, x, rows_m1, src, rec_cursor); break;
        case OBJ_H_A6GATE_W88: obj_handler_a6gate_w88(c, x, rows_m1, src, rec_cursor); break;

        case OBJ_H_DBL:      obj_handler_dbl(c, x, colour, voff, dst, src, rec_cursor, rows_m1, 1); break;
        case OBJ_H_DBL2:     obj_handler_dbl(c, x, colour, voff, dst, src, rec_cursor, rows_m1, 2); break;
        case OBJ_H_LO_FULL:  obj_handler_lo_full(c, x, colour, rows_m1, src, rec_cursor, 1); break;
        case OBJ_H_LO_FULL2: obj_handler_lo_full(c, x, colour, rows_m1, src, rec_cursor, 2); break;

        case OBJ_H_P24: obj_handler_p24(c, x, rows_m1, src); break;
        case OBJ_H_P26: obj_handler_p_glue(c, x, rows_m1, src, 0x20, 3, -1); break;
        case OBJ_H_P28: obj_handler_p_glue(c, x, rows_m1, src, 0x1c, 2, 2); break;
        case OBJ_H_P2A: obj_handler_p_glue(c, x, rows_m1, src, 0x17, 1, 1); break;
        case OBJ_H_P2C: obj_handler_p_glue(c, x, rows_m1, src, 0x12, 1, 2); break;
        case OBJ_H_P2E: obj_handler_p_glue(c, x, rows_m1, src, 0x0e, 1, -1); break;
        case OBJ_H_P30: obj_handler_p_glue(c, x, rows_m1, src, 0x0c, 0, 1); break;
        case OBJ_H_P32: obj_handler_p_glue(c, x, rows_m1, src, 0x0a, 0, 1); break;
        case OBJ_H_P34: obj_handler_p_glue(c, x, rows_m1, src, 0x08, 0, 2); break;
        case OBJ_H_P36: obj_handler_p_glue(c, x, rows_m1, src, 0x06, 0, 2); break;
        case OBJ_H_P38: {
            uint32_t dp = objshift2_prefix_dst(c, rows_m1);
            RM_BLIT_OBJSHIFT2(c->px, dp, c->buf_c, src, x, 0x04, 0);
            break;
        }
        default: break;
    }
}

void rm_draw_object_list(const ObjListCtx *c, const uint8_t *list, uint32_t list_off,
                         const uint8_t *flags, uint32_t flags_off,
                         uint16_t outer_rows_m1, uint16_t rec_off, uint16_t colour) {
    list_off = (uint32_t)(list_off + sx16((uint16_t)c->obj_scan_off));    /* adda.w obj_scan_off,a5 */

    int outer = (int16_t)outer_rows_m1 + 1;
    for (int oi = 0; oi < outer; oi++) {
        uint32_t row_dst = (uint32_t)(c->draw_buf + sx16(be16(list + list_off))); list_off += 2;
        uint32_t xoff_off = sx16(be16(list + list_off)); list_off += 2;    /* into xoff_tbl */

        for (int inner = OBJ_ROW_OBJECTS; inner >= 0; inner--) {
            /* SPECIAL pass: only when the flag word is negative. */
            if ((int16_t)be16(flags + flags_off) < 0) {
                uint16_t x = be16(list + list_off);                        /* peeked; consumed below */
                uint32_t rec_ptr = (uint32_t)(OBJ_SPECIAL_BASE + sx16((uint16_t)rec_off));
                uint32_t src = be32(c->buf_a + rec_ptr);
                uint16_t rows = be16(c->buf_a + rec_ptr + OBJ_REC_ROWS);
                uint16_t jumpidx = be16(c->buf_a + rec_ptr + OBJ_REC_JUMP);
                obj_dispatch(c, jumpidx, x, colour, rows, row_dst, src, rec_ptr + OBJ_REC_DSTADJ,
                             /*voff=*/0, c->xoff_tbl, xoff_off, list, list_off);
            }
            /* NORMAL pass. */
            uint16_t x = be16(list + list_off); list_off += 2;
            uint16_t type = (uint16_t)(be16(flags + flags_off) & OBJ_ROWS_ONLY); flags_off += 2;
            if (type != 0) {
                if (c->bonus_timer != 0 && (int16_t)(type - OBJ_BONUS_MIN_TYPE) < 0)
                    type = OBJ_BONUS_MIN_TYPE;                             /* bonus-window clamp */
                x = (uint16_t)(x + be16(c->xoff_tbl + xoff_off));
                uint32_t type_base = (uint32_t)(OBJ_TYPE_BASE
                                                + sx16((uint16_t)(type * OBJ_TYPE_STRIDE)));
                colour = be16(c->buf_a + type_base - OBJ_COLOUR_OFF);
                uint32_t data_base = (uint32_t)(type_base + sx16((uint16_t)rec_off));
                uint32_t src = be32(c->buf_a + data_base);
                uint16_t rows = be16(c->buf_a + data_base + OBJ_REC_ROWS);
                /* vertical offset: (vseed - rows).b * view_flags >> 4 * width, subtracted from row_dst. */
                uint16_t v = (uint16_t)(uint8_t)(c->buf_a[data_base - OBJ_VSEED_OFF] - (uint8_t)rows);
                v = (uint16_t)(v * c->view_flags);
                v = (uint16_t)(v >> 4);
                v = (uint16_t)(v * OBJD_WIDTH);
                uint32_t dst = (uint32_t)(row_dst - sx16(v));
                uint16_t jumpidx = be16(c->buf_a + data_base + OBJ_REC_JUMP);
                dst = (uint32_t)(dst + sx16(be16(c->buf_a + data_base + OBJ_REC_DSTADJ)));
                x = (uint16_t)(x + be16(c->buf_a + data_base + OBJ_REC_XADJ));
                obj_dispatch(c, jumpidx, x, colour, rows, dst, src, data_base + OBJ_REC_XADJ,
                             /*voff=*/v, c->xoff_tbl, xoff_off, list, list_off);
            }
        }
        flags_off += 2;
        rec_off = (uint16_t)(rec_off - OBJ_D6_STEP);
    }
}
