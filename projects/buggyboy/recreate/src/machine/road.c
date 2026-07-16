/* road.c (machine model) — the byte-exact 1:1 transcription of render_road's seven bands.
 *
 * This is the TRUST ANCHOR: a faithful register/goto model of the original 68000, verified
 * byte-for-byte against the Musashi oracle. The readable default (g_render_road) lives in
 * ../road.c; both drive the shared pipeline in road_bands.h. Keep this in step with that
 * header — do not "clean up" the spaghetti here; its value is being a literal transcription.
 */
#include "road_bands.h"

/* Band A (0x9172) — 96 rows, the widest branch set. Byte-exact machine model (trust anchor).
 * Inline in the original; extracted here so the band pipeline can select it like the other bands. */
static void rr_band_A(rr_regs *r) {
    uint8_t *img = r->img;
    uint32_t d0, d1, d3, d5, d6, d7, a0, a1;
    uint32_t a2 = r->a2, a3 = r->a3, a4 = r->a4, a5 = r->a5, a6 = r->a6, d2 = r->d2;
    uint32_t d4 = 0x5f;
    d7 = 0;                         /* band A never masks d0 with d7 (d7 = saved-a0 scratch there) */
L9172:
    a1 = a3; a0 = a2;
    d0 = be32(img + a5); a5 += 4;                                   /* move.l (a5)+,d0 */
    d0 = rr_wset(d0, (uint16_t)(d0 + be16(img + a4))); a4 += 2;     /* add.w (a4)+,d0 */
    d1 = 0xf & d0; d1 = rr_wset(d1, (uint16_t)(d1 << 4));           /* moveq #f; and.w d0,d1; lsl.w #4 */
    a1 += sign_ext16((uint16_t)d1);                                /* adda.w d1,a1 */
    d3 = be32(img + a1 + RR_MASK_OFF_HI);                          /* move.l 0x2808(a1),d3 */
    d1 = be16(img + a4); a4 += 2;                                  /* move.w (a4)+,d1 */
    d5 = rr_moveq((int8_t)0xff);                                   /* d5 = 0xffffffff */
    d6 = rr_notw(0);                                              /* d6 = 0x0000ffff */
    if (d0 & RR_F_PLANE_HI) d6 = rr_swap(d6);                     /* -> 0xffff0000 */
    if (!(d0 & RR_F_SPLIT_A)) goto L92d6;
    a6 += 2;
    if (d0 & RR_F_WIDE) goto L92a8;
    if (!(d0 & RR_F_SKIP_ABC)) goto L92da;
    /* 0x91b0 */
    d6 = 0;
    a1 += sign_ext16((uint16_t)d1);
    d1 = be32(img + a4); a4 += 4;                                 /* move.l (a4)+,d1 */
    d0 = rr_wset(d0, (uint16_t)(rr_ws(d0) >> 1));                 /* asr.w #1 */
    if (!(d0 & RR_F_PLANE_HI)) goto L9230;
    /* 0x91c0 */
    d5 = 0;
    a1 += RR_SRC_A800;
    if (be16(img + a6 - 2) != 0) a1 += RR_SRC_0A00;
    d0 = rr_wset(d0, (uint16_t)(d0 & RR_D7_WORD_MASK));
    if (rr_ws(d0) >= 0) goto L91f8;
    d1 = 0x13; d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) < 0) goto L91e6;
    d1 = 0x12; a1 += 8;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
L91e6:
    do { wr32(img + a0, d6); a0 += 4; wr32(img + a0, d6); a0 += 4; }
    while (rr_dbf(&d1));                         /* dbf d1 */
    goto L91ee;
L91f8:
    a0 += sign_ext16((uint16_t)d0); d7 = a0;                      /* adda.w d0,a0; move.l a0,d7 */
    d2 = rr_wset(d2, (uint16_t)d0);                               /* move.w d0,d2 */
    d0 = rr_wset(d0, (uint16_t)(d0 - RR_ROW_STRIDE_D2));          /* subi.w #a0,d0 */
    if (rr_ws(d0) >= 0) goto L928c;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L921a;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L928c;
    goto L9224;
L921a:
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L928c;
L9224:
    do { wr32(img + a0, d6); a0 += 4; wr32(img + a0, d6); a0 += 4;
         d0 = rr_wset(d0, (uint16_t)(d0 + 8)); } while (rr_ws(d0) < 0);
    goto L928c;
L9230:
    a1 += sign_ext16(be16(img + a6 - 2));                         /* adda.w -2(a6),a1 */
    d0 = rr_wset(d0, (uint16_t)(d0 & RR_D7_WORD_MASK));
    if (rr_ws(d0) >= 0) goto L925c;
    d1 = 0x13; d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) < 0) goto L924a;
    d1 = 0x12; a1 += 8;
    rr_copy_long(img, &a0, &a1);            /* move.l (a1)+,(a0)+ */
    rr_copy_long_masked(img, &a0, &a1, d3);       /* move.l (a1)+,(a0); and.l d3,(a0)+ */
L924a:
    do { rr_fill_pair(img, &a0, d5, d6); }
    while (rr_dbf(&d1));
    goto L91ee;
L925c:
    a0 += sign_ext16((uint16_t)d0); d7 = a0;
    d2 = rr_wset(d2, (uint16_t)d0);
    d0 = rr_wset(d0, (uint16_t)(d0 - RR_ROW_STRIDE_D2));
    if (rr_ws(d0) >= 0) goto L928c;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L927c;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    rr_copy_long_masked(img, &a0, &a1, d3);
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L928c;
    goto L9284;
L927c:
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L928c;
L9284:
    do { rr_fill_pair(img, &a0, d5, d6);
         d0 = rr_wset(d0, (uint16_t)(d0 + 8)); } while (rr_ws(d0) < 0);
L928c:
    d5 = rr_notw(0);                                              /* moveq #0,d5; not.w -> 0xffff */
    d6 = d5;                                                      /* move.l d5,d6 */
    if ((int32_t)d0 >= 0) goto L936a;                            /* tst.l d0; bpl */
    if (!(d0 & RR_F_PLANE_HI)) goto L936a;
    d5 = rr_moveq((int8_t)0xff); d6 = 0;                         /* 0x92a0 */
    goto L936a;
L92a8:
    d6 = 0;
    a1 += RR_SRC_5000;
    if (!(d0 & RR_F_SRC_400)) goto L92c6;
    a1 += RR_SRC_0400;
    if (d0 & RR_F_SRC_100) goto L92f6;
    a1 += RR_SRC_0100; d5 = 0;
    goto L92f6;
L92c6:
    if (d0 & RR_F_SRC_100) goto L92f6;
    a1 += RR_SRC_0100; d5 = rr_notw(0);                          /* moveq #0; not.w -> 0xffff */
    goto L92f6;
L92d6:
    a1 += sign_ext16((uint16_t)d1);
    a1 += sign_ext16(be16(img + a6)); a6 += 2;                   /* adda.w (a6)+,a1 */
L92da:
    if (!(d0 & RR_F_PLANE_HI)) goto L92e6;
    a1 += RR_SRC_5800;
    goto L92f6;
L92e6:
    if (!(d0 & RR_F_SRC_CONST)) goto L92f6;
    if ((int32_t)d0 < 0) goto L92f6;
    a1 = RR_CONST_5BAA;
L92f6:
    d1 = be32(img + a4); a4 += 4;                                /* move.l (a4)+,d1 */
    d0 = rr_wset(d0, (uint16_t)(rr_ws(d0) >> 1));                /* asr.w #1 */
    d0 = rr_wset(d0, (uint16_t)(d0 & RR_D7_WORD_MASK));          /* andi.w #fff8 */
    if (rr_ws(d0) >= 0) goto L9328;
    a1 += 8; d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L930a;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    goto L930e;
L930a:
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
L930e:
    d0 = rr_wset(d0, (uint16_t)(rr_ws(d0) >> 3));                /* asr.w #3 */
    d1 = rr_wset(d1, (uint16_t)(d1 + d0));                       /* add.w d0,d1 */
    if (rr_ws(d1) < 0) goto L931c;
    do { rr_fill_pair(img, &a0, d5, d6); }
    while (rr_dbf(&d1));                        /* dbf d1 */
L931c:
    a2 += RR_ROW_STRIDE_D2;                                      /* adda.w #a0,a2 */
    goto L9320;
L9328:
    a0 += sign_ext16((uint16_t)d0); d7 = a0;
    d2 = rr_wset(d2, (uint16_t)d0);
    d0 = rr_wset(d0, (uint16_t)(d0 - RR_ROW_STRIDE_D2));
    if (rr_ws(d0) >= 0) goto L9352;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L934e;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
L9340:                                                          /* combined d0/d1 shoulder-fill loop */
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L9352;
    rr_fill_pair(img, &a0, d5, d6);
    if (rr_dbf(&d1)) goto L9340;                                /* dbf d1,$9340 */
    goto L9352;
L934e:
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
L9352:
    d5 = rr_notw(0); d6 = d5;                                    /* moveq #0; not.w; move.l d5,d6 */
    if (!(d0 & RR_F_SRC_CONST)) goto L936a;
    if ((int32_t)d0 < 0) goto L936a;
    if (d0 & RR_F_PLANE_HI) goto L936a;
    d5 = rr_moveq((int8_t)0xff);
L936a:
    if (!(d0 & RR_F_WIDE)) goto L9384;
    d5 = rr_moveq((int8_t)0xff); d6 = 0;
    if (!(d0 & RR_F_SRC_100)) goto L9384;
    d5 = 0;
    if (d0 & RR_F_SRC_400) goto L9384;
    d5 = rr_notw(d5);                                           /* not.w d5 (0 -> 0xffff) */
L9384:
    a0 = d7;                                                    /* movea.l d7,a0 */
    d0 = rr_wset(d0, (uint16_t)d2);                            /* move.w d2,d0 */
    d1 = rr_swap(d1);                                          /* swap d1 */
    d2 = RR_ROW_STRIDE_D2;                                     /* move.w #a0,d2 */
L938e:
    d0 = rr_wset(d0, (uint16_t)(d0 - 8));                      /* subq.w #8,d0 */
    if (rr_ws(d0) < 0) goto L93a6;                             /* bmi */
    if (rr_ws(d0) - (int16_t)d2 >= 0) goto L93a0;             /* cmp.w d2,d0; bpl */
    rr_fill_pair_rev(img, &a0, d5, d6);              /* move.l d6,-(a0); move.l d5,-(a0) */
    if (rr_dbf(&d1)) goto L938e;            /* dbf d1,$938e */
    goto L93a6;
L93a0:
    a0 -= 8;                                                  /* subq.l #8,a0 */
    if (rr_dbf(&d1)) goto L938e;
L93a6:                                                        /* row tail: advance dst, next scanline */
L91ee:                                                        /* fill-path exits land here (d2 == 0xa0) */
    a2 += d2;                                                 /* adda.w d2,a2 */
L9320:
    if (rr_dbf(&d4)) goto L9172;
    goto done;

done:
    (void)a0; (void)a1; (void)d3; (void)d5; (void)d6; (void)d7;
    r->a2 = a2; r->a3 = a3; r->a4 = a4; r->a5 = a5; r->a6 = a6; r->d2 = d2;
}

/* ---- band B (0x93c2 near copy / 0x948c far copy): reg map a0=dst a1=src d0=ctrl d1=count
 * d3=mask d5/d6=fill. The two copies share the preamble + src dispatch but diverge at the blit
 * tail (near: 0x944a single masked column + shoulder fill; far: 0x9514, a wider 4-long blit with a
 * distinct full-fill path). `second` selects the far copy's tail. ---- */
static void rr_band_B(rr_regs *r, uint32_t rows_m1, int second) {
    uint8_t *img = r->img;
    uint32_t d0, d1, d3, d5, d6, a0, a1;
    uint32_t d4 = rows_m1;
L93c2:
    a1 = r->a3; a0 = r->a2;
    d0 = be32(img + r->a5); r->a5 += 4;
    d0 = rr_wset(d0, (uint16_t)(d0 + be16(img + r->a4))); r->a4 += 2;
    d1 = 0xf & d0; d1 = rr_wset(d1, (uint16_t)(d1 << 4));
    a1 += sign_ext16((uint16_t)d1);
    d1 = be16(img + r->a4); r->a4 += 2;                         /* move.w (a4)+,d1 */
    d5 = rr_clrw(rr_moveq((int8_t)0xff));                      /* moveq #ff; clr.w -> 0xffff0000 */
    d6 = rr_notw(0);                                          /* 0x0000ffff */
    d3 = rr_moveq((int8_t)0xff);                              /* moveq #ff,d3 -> 0xffffffff */
    if (d0 & RR_F_MASK_A) { d5 = 0; d3 = be32(img + a1 + RR_MASK_OFF_HI); }
    if (!(d0 & RR_F_SPLIT_B)) goto L943c;
    if (!(d0 & RR_F_SKIP_ABC)) goto L9406;
    if ((int32_t)d0 >= 0) goto L9406;                         /* tst.l d0; bpl */
    r->a6 += 2; r->a2 += r->d2; if (rr_dbf(&d4)) goto L93c2;  /* addq #2,a6; adda d2,a2; dbf */
    return;
L9406:
    r->a6 += 2;
    if (!(d0 & RR_F_WIDE)) goto L9440;
    d6 = 0; a1 += RR_SRC_4700;
    if (!(d0 & RR_F_SRC_400)) goto L942c;
    a1 += RR_SRC_0400;
    if (d0 & RR_F_SRC_100) goto Ltail;
    a1 = RR_CONST_5B7A; goto Ltail;
L942c:
    d5 = rr_notw(d5);                                         /* not.w d5 */
    if (d0 & RR_F_SRC_100) goto Ltail;
    a1 = RR_CONST_5B9A; goto Ltail;
L943c:
    a1 += sign_ext16((uint16_t)d1);
    a1 += sign_ext16(be16(img + r->a6)); r->a6 += 2;
L9440:
    if (!(d0 & RR_F_PLANE_HI)) goto Ltail;
    a1 += RR_SRC_5800;
Ltail:
    if (second) goto L9514;

    /* --- near copy tail (0x944a): +8 both, single masked column, shoulder fill --- */
    a0 += 8; a1 += 8;                                         /* addq.l #8 both */
    d0 = rr_wset(d0, (uint16_t)(rr_ws(d0) >> 1));            /* asr.w #1 */
    d0 = rr_wset(d0, (uint16_t)(d0 & r->d7));                /* and.w d7,d0 */
    a0 += sign_ext16((uint16_t)d0);                          /* adda.w d0,a0 */
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L946c;
    rr_fill_full_row(img, &r->a2, d5, d6);                /* moveq #9,d1; dbf: full-width fill of a2 */
    if (rr_dbf(&d4)) goto L93c2;
    return;
L946c:
    d0 = rr_wset(d0, (uint16_t)(d0 - r->d2));               /* sub.w d2,d0 */
    if (rr_ws(d0) >= 0) goto L9484;
    rr_copy_long(img, &a0, &a1);       /* move.l (a1)+,(a0)+ */
    rr_andw(img, a0 - 4, d3);                               /* and.w d3,-4(a0) */
    rr_copy_long(img, &a0, &a1);
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L9484;
    do {
        rr_fill_pair(img, &a0, d5, d6);
        d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    } while (rr_ws(d0) < 0);
L9484:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L93c2;
    (void)a0; (void)a1;
    return;

    /* --- far copy tail (0x9514): no +8, asr/mask then either a dbf-counted fill (d0<0) or a
     * wider 4-long masked blit + shoulder fill (d0>=0) --- */
L9514:
    d0 = rr_wset(d0, (uint16_t)(rr_ws(d0) >> 1));            /* asr.w #1 */
    d0 = rr_wset(d0, (uint16_t)(d0 & r->d7));                /* and.w d7,d0 */
    if (rr_ws(d0) >= 0) goto L953c;                          /* bpl */
    d1 = 0x13;                                               /* moveq #$13,d1 */
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    if (rr_ws(d0) < 0) goto L952c;                           /* bmi */
    d1 = 0x12; a1 += 8;                                      /* moveq #$12,d1; addq.l #8,a1 */
    rr_copy_long(img, &a0, &a1);        /* move.l (a1)+,(a0)+ */
    rr_andw(img, a0 - 4, d3);                                /* and.w d3,-4(a0) */
    rr_copy_long(img, &a0, &a1);
L952c:
    do { rr_fill_pair(img, &a0, d5, d6); }
    while (rr_dbf(&d1));                                     /* dbf d1,$952c */
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L93c2;
    return;
L953c:
    a0 += sign_ext16((uint16_t)d0);                          /* adda.w d0,a0 */
    d0 = rr_wset(d0, (uint16_t)(d0 - r->d2));                /* sub.w d2,d0 */
    if (rr_ws(d0) >= 0) goto L9568;                          /* bpl -> row done */
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    if (rr_ws(d0) >= 0) goto L9558;                          /* bpl */
    rr_copy_long(img, &a0, &a1);        /* move.l (a1)+,(a0)+ x4, 3rd masked */
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    rr_andw(img, a0 - 4, d3);                                /* and.w d3,-4(a0) */
    rr_copy_long(img, &a0, &a1);
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    if (rr_ws(d0) >= 0) goto L9568;                          /* bpl */
    goto L9560;
L9558:
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    if (rr_ws(d0) >= 0) goto L9568;                          /* bpl */
L9560:
    do {
        rr_fill_pair(img, &a0, d5, d6);
        d0 = rr_wset(d0, (uint16_t)(d0 + 8));               /* addq.w #8,d0 */
    } while (rr_ws(d0) < 0);                                /* bmi $9560 */
L9568:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L93c2;
    (void)a0; (void)a1;
}

/* ---- band C near copy (0x9582) ---- */
static void rr_band_C_near(rr_regs *r, uint32_t rows_m1) {
    uint8_t *img = r->img;
    uint32_t d0, d1, d3, d5, d6, a0, a1;
    uint32_t d4 = rows_m1;
L9582:
    a1 = r->a3; a0 = r->a2;
    d0 = be32(img + r->a5); r->a5 += 4;
    d0 = rr_wset(d0, (uint16_t)(d0 + be16(img + r->a4))); r->a4 += 2;
    d1 = 0xf & d0; d1 = rr_wset(d1, (uint16_t)(d1 << 4));
    a1 += sign_ext16((uint16_t)d1);
    d1 = be16(img + r->a4); r->a4 += 2;
    d3 = be32(img + a1 + RR_MASK_OFF_LO);                       /* move.l 0x2800(a1),d3 */
    d5 = rr_moveq((int8_t)0xff);                               /* 0xffffffff */
    d6 = rr_notw(0);                                          /* 0x0000ffff */
    if (d0 & RR_F_PLANE_HI) d6 = rr_swap(d6);
    if (!(d0 & RR_F_SPLIT_C)) goto L9666;
    r->a6 += 2;
    if (d0 & RR_F_WIDE) goto L9638;
    if (!(d0 & RR_F_SKIP_D)) goto L966a;
    /* 0x95c0 */
    d6 = 0;
    d0 = rr_wset(d0, (uint16_t)(rr_ws(d0) >> 1));            /* asr.w #1 */
    d0 = rr_wset(d0, (uint16_t)(d0 & r->d7));                /* and.w d7,d0 */
    if (rr_ws(d0) >= 0) goto L95d2;
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L9582;
    return;
L95d2:
    a1 += sign_ext16((uint16_t)d1);
    a0 += sign_ext16((uint16_t)d0);
    d1 = rr_wset(d1, (uint16_t)d0);                          /* move.w d0,d1 */
    if (!(d0 & RR_F_PLANE_HI)) goto L95fa;
    d5 = 0; a1 += RR_SRC_A800;
    if (be16(img + r->a6 - 2) != 0) a1 += RR_SRC_0A00;
    d0 = rr_wset(d0, (uint16_t)(d0 - r->d2));                /* sub.w d2,d0 */
    if (rr_ws(d0) >= 0) goto L9622;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    goto L9608;
L95fa:
    a1 += sign_ext16(be16(img + r->a6 - 2));
    d0 = rr_wset(d0, (uint16_t)(d0 - r->d2));
    if (rr_ws(d0) >= 0) goto L9622;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long_masked(img, &a0, &a1, d3);   /* move.l(a1)+,(a0); and.l d3,(a0)+ */
L9608:
    d1 = rr_wset(d1, (uint16_t)((uint16_t)d1 >> 3));         /* lsr.w #3,d1 */
    d1 = rr_wset(d1, (uint16_t)(d1 - 1));                    /* subq.w #1,d1 */
    if (rr_ws(d1) < 0) goto L9618;
    a0 = r->a2;
    do { rr_fill_pair(img, &a0, d5, d6); } while (rr_dbf(&d1));
L9618:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L9582;
    return;
L9622:
    rr_fill_full_row(img, &r->a2, d5, d6);                /* moveq #9,d1; dbf: full-width fill of a2 */
    if (rr_dbf(&d4)) goto L9582;
    return;
L9638:
    d6 = 0; a1 += RR_SRC_3E00;
    if (!(d0 & RR_F_SRC_400)) goto L9656;
    a1 += RR_SRC_0400;
    if (d0 & RR_F_SRC_100) goto L9686;
    a1 += RR_SRC_0100; d5 = 0; goto L9686;
L9656:
    if (d0 & RR_F_SRC_100) goto L9686;
    a1 += RR_SRC_0100; d5 = 0; d5 = rr_notw(d5); goto L9686;
L9666:
    a1 += sign_ext16((uint16_t)d1);
    a1 += sign_ext16(be16(img + r->a6)); r->a6 += 2;
L966a:
    if (!(d0 & RR_F_PLANE_HI)) goto L9676;
    a1 += RR_SRC_5800; goto L9686;
L9676:
    if (!(d0 & RR_F_SRC_CONST)) goto L9686;
    if ((int32_t)d0 < 0) goto L9686;
    a1 = RR_CONST_5BAA;
L9686:
    d0 = rr_wset(d0, (uint16_t)(rr_ws(d0) >> 1));           /* asr.w #1 */
    d0 = rr_wset(d0, (uint16_t)(d0 & r->d7));               /* and.w d7,d0 */
    d0 = rr_wset(d0, (uint16_t)(d0 - 8));                   /* subq.w #8,d0 */
    if (rr_ws(d0) >= 0) goto L969e;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) < 0) goto L96b0;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L9582;
    return;
L969e:
    a0 += sign_ext16((uint16_t)d0);
    d0 = rr_wset(d0, (uint16_t)(d0 - r->d2));
    if (rr_ws(d0) >= 0) goto L96b0;
    rr_fill_pair(img, &a0, d5, d6);
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L96b0;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
L96b0:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L9582;
    (void)a0; (void)a1; (void)d3;
}

/* ---- band C far copy (0x96b8) ---- byte-identical preamble + WIDE/no-split/src-select to the
 * near copy, but a distinct fast-split path (0x96f6: does the src select first, consumes one extra
 * a4 param word) and a distinct merge tail (0x9808: reads an extra param word, then a wider
 * bidirectional blit). Falls through to the C->D group step (no rts). ---- */
static void rr_band_C_far(rr_regs *r, uint32_t rows_m1) {
    uint8_t *img = r->img;
    uint32_t d0, d1, d3, d5, d6, a0, a1;
    uint32_t d4 = rows_m1;
L96b8:
    a1 = r->a3; a0 = r->a2;
    d0 = be32(img + r->a5); r->a5 += 4;
    d0 = rr_wset(d0, (uint16_t)(d0 + be16(img + r->a4))); r->a4 += 2;
    d1 = 0xf & d0; d1 = rr_wset(d1, (uint16_t)(d1 << 4));
    a1 += sign_ext16((uint16_t)d1);
    d1 = be16(img + r->a4); r->a4 += 2;
    d3 = be32(img + a1 + RR_MASK_OFF_LO);                       /* move.l 0x2800(a1),d3 */
    d5 = rr_moveq((int8_t)0xff);                               /* 0xffffffff */
    d6 = rr_notw(0);                                          /* 0x0000ffff */
    if (d0 & RR_F_PLANE_HI) d6 = rr_swap(d6);
    if (!(d0 & RR_F_SPLIT_C)) goto L97e8;
    r->a6 += 2;
    if (d0 & RR_F_WIDE) goto L97ba;
    if (!(d0 & RR_F_SKIP_D)) goto L97ec;
    /* 0x96f6 fast edge-split: src select FIRST, extra a4 += 2 vs the near copy */
    a1 += sign_ext16((uint16_t)d1);                          /* adda.w d1,a1 */
    r->a4 += 2;                                              /* addq.l #2,a4 (far-only) */
    d0 = rr_wset(d0, (uint16_t)(rr_ws(d0) >> 1));            /* asr.w #1 */
    d6 = 0;
    if (!(d0 & RR_F_PLANE_HI)) goto L9750;
    /* 0x9704 (bit27 set) */
    d5 = 0; a1 += RR_SRC_A800;
    if (be16(img + r->a6 - 2) != 0) a1 += RR_SRC_0A00;
    d0 = rr_wset(d0, (uint16_t)(d0 & r->d7));                /* and.w d7,d0 */
    if (rr_ws(d0) >= 0) goto L972e;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    if (rr_ws(d0) < 0) goto L9724;
    a1 += 8;                                                 /* addq.l #8,a1 */
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
L9724:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L96b8;
    return;
L972e:
    a0 += sign_ext16((uint16_t)d0);
    d1 = rr_wset(d1, (uint16_t)d0);                          /* move.w d0,d1 */
    d0 = rr_wset(d0, (uint16_t)(d0 - r->d2));                /* sub.w d2,d0 */
    if (rr_ws(d0) >= 0) goto L97a4;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    if (rr_ws(d0) >= 0) goto L9748;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    goto L978a;
L9748:
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    goto L978a;
L9750:                                                       /* 0x9750 (bit27 clear) */
    a1 += sign_ext16(be16(img + r->a6 - 2));                 /* adda.w -2(a6),a1 */
    d0 = rr_wset(d0, (uint16_t)(d0 & r->d7));                /* and.w d7,d0 */
    if (rr_ws(d0) >= 0) goto L976c;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) < 0) goto L9762;
    a1 += 8;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
L9762:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L96b8;
    return;
L976c:
    a0 += sign_ext16((uint16_t)d0);
    d1 = rr_wset(d1, (uint16_t)d0);                          /* move.w d0,d1 */
    d0 = rr_wset(d0, (uint16_t)(d0 - r->d2));                /* sub.w d2,d0 */
    if (rr_ws(d0) >= 0) goto L97a4;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L9784;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long_masked(img, &a0, &a1, d3);   /* move.l(a1)+,(a0); and.l d3,(a0)+ */
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    goto L978a;
L9784:
    rr_copy_long(img, &a0, &a1);
    rr_copy_long_masked(img, &a0, &a1, d3);
L978a:
    d1 = rr_wset(d1, (uint16_t)((uint16_t)d1 >> 3));         /* lsr.w #3,d1 */
    d1 = rr_wset(d1, (uint16_t)(d1 - 1));                    /* subq.w #1,d1 */
    if (rr_ws(d1) < 0) goto L979a;
    a0 = r->a2;
    do { rr_fill_pair(img, &a0, d5, d6); } while (rr_dbf(&d1));
L979a:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L96b8;
    return;
L97a4:                                                       /* full-width fill */
    rr_fill_full_row(img, &r->a2, d5, d6);                /* moveq #9,d1; dbf: full-width fill of a2 */
    if (rr_dbf(&d4)) goto L96b8;
    return;
L97ba:                                                       /* WIDE src select (identical to near) */
    d6 = 0; a1 += RR_SRC_3E00;
    if (!(d0 & RR_F_SRC_400)) goto L97d8;
    a1 += RR_SRC_0400;
    if (d0 & RR_F_SRC_100) goto L9808;
    a1 += RR_SRC_0100; d5 = 0; goto L9808;
L97d8:
    if (d0 & RR_F_SRC_100) goto L9808;
    a1 += RR_SRC_0100; d5 = 0; d5 = rr_notw(d5); goto L9808;
L97e8:                                                       /* no-split (a6-add) */
    a1 += sign_ext16((uint16_t)d1);
    a1 += sign_ext16(be16(img + r->a6)); r->a6 += 2;
L97ec:                                                       /* hi/const src select */
    if (!(d0 & RR_F_PLANE_HI)) goto L97f8;
    a1 += RR_SRC_5800; goto L9808;
L97f8:
    if (!(d0 & RR_F_SRC_CONST)) goto L9808;
    if ((int32_t)d0 < 0) goto L9808;
    a1 = RR_CONST_5BAA;
L9808:                                                       /* far merge/blit tail (distinct) */
    d1 = be16(img + r->a4); r->a4 += 2;                      /* move.w (a4)+,d1 (far-only) */
    d0 = rr_wset(d0, (uint16_t)(rr_ws(d0) >> 1));            /* asr.w #1 */
    d0 = rr_wset(d0, (uint16_t)(d0 & r->d7));                /* and.w d7,d0 */
    if (rr_ws(d0) >= 0) goto L9822;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    if (rr_ws(d0) < 0) goto L981a;
    a1 += 8;                                                 /* addq.l #8,a1 */
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
L981a:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L96b8;
    return;
L9822:
    a0 += sign_ext16((uint16_t)d0);                          /* adda.w d0,a0 */
    d3 = rr_wset(d3, (uint16_t)d0);                          /* move.w d0,d3 (near uses d1) */
    d0 = rr_wset(d0, (uint16_t)(d0 - r->d2));                /* sub.w d2,d0 */
    if (rr_ws(d0) < 0) goto L9846;                           /* bmi */
    d0 = rr_wset(d0, (uint16_t)(d0 - 8));                    /* subq.w #8,d0 */
    if (rr_ws(d0) < 0) goto L984c;                           /* bmi */
    r->a2 += r->d2;                                          /* adda.w d2,a2 */
    d0 = rr_wset(d0, (uint16_t)((uint16_t)d0 >> 3));         /* lsr.w #3,d0 */
    d1 = rr_wset(d1, (uint16_t)(d1 - d0));                   /* sub.w d0,d1 */
    if (rr_ws(d1) < 0) goto L9840;                           /* bmi */
    a0 = r->a2;
L9838:
    rr_fill_pair_rev(img, &a0, d5, d6);              /* move.l d6,-(a0); move.l d5,-(a0) */
    if (rr_dbf(&d1)) goto L9838;                             /* dbf d1,$9838 */
L9840:
    if (rr_dbf(&d4)) goto L96b8;
    return;
L9846:
    d0 = 0;                                                  /* moveq #0,d0 (clears the full register) */
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
L984c:
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    a0 -= sign_ext16((uint16_t)d0);                          /* suba.w d0,a0 */
L9856:
    d3 = rr_wset(d3, (uint16_t)(d3 - 8));                    /* subq.w #8,d3 */
    if (rr_ws(d3) < 0) goto L9862;                           /* bmi */
    rr_fill_pair_rev(img, &a0, d5, d6);              /* move.l d6,-(a0); move.l d5,-(a0) */
    if (rr_dbf(&d1)) goto L9856;                             /* dbf d1,$9856 (re-runs subq/suba) */
L9862:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L96b8;
    (void)a0; (void)a1;
}

/* ---- band D (0x987c near copy / 0x9950 far copy; the far copy's last dbf falls through to rts).
 * The two copies share the preamble + src dispatch but diverge at the blit tail (0x9914 vs 0x99f0);
 * `second` selects the far copy's wider blit tail. ---- */
static void rr_band_D(rr_regs *r, uint32_t rows_m1, int second) {
    uint8_t *img = r->img;
    uint32_t d0, d1, d3, d5, d6, a0, a1;
    uint32_t d4 = rows_m1;
Ltop:
    a1 = r->a3; a0 = r->a2;
    d0 = be32(img + r->a5); r->a5 += 4;
    d0 = rr_wset(d0, (uint16_t)(d0 + be16(img + r->a4))); r->a4 += 2;
    d1 = 0xf & d0; d1 = rr_wset(d1, (uint16_t)(d1 << 4));
    a1 += sign_ext16((uint16_t)d1);
    d1 = be16(img + r->a4); r->a4 += 2;
    d5 = rr_clrw(rr_moveq((int8_t)0xff));                       /* 0xffff0000 */
    d6 = rr_notw(0);                                          /* 0x0000ffff */
    d3 = rr_moveq((int8_t)0xff);                              /* 0xffffffff */
    if (d0 & RR_F_MASK_A2) { d5 = 0; d3 = be32(img + a1 + RR_MASK_OFF_LO); }
    if (!(d0 & RR_F_SPLIT_D)) goto L98f8;
    if (!(d0 & RR_F_SKIP_D)) goto L98c0;
    if ((int32_t)d0 >= 0) goto L98c0;
    r->a6 += 2; r->a2 += r->d2; if (rr_dbf(&d4)) goto Ltop;
    return;
L98c0:
    r->a6 += 2;
    if (!(d0 & RR_F_WIDE)) goto L98fc;
    d5 = 0; d6 = 0; a1 += RR_SRC_3500;
    if (!(d0 & RR_F_SRC_400)) goto L98e8;
    a1 += RR_SRC_0400;
    if (d0 & RR_F_SRC_100) goto L9906;
    a1 = RR_CONST_5B7A; goto L9906;
L98e8:
    d5 = rr_notw(d5);
    if (d0 & RR_F_SRC_100) goto L9906;
    a1 = RR_CONST_5B9A; goto L9906;
L98f8:
    a1 += sign_ext16((uint16_t)d1);
    a1 += sign_ext16(be16(img + r->a6)); r->a6 += 2;
L98fc:
    if (!(d0 & RR_F_PLANE_HI)) goto L9906;
    a1 += RR_SRC_5800;
L9906:
    d0 = rr_wset(d0, (uint16_t)(rr_ws(d0) >> 1));            /* asr.w #1 */
    d0 = rr_wset(d0, (uint16_t)(d0 & r->d7));                /* and.w d7,d0 */
    if (second) goto D2_tail;

    /* --- near copy tail (0x990a) --- */
    if (rr_ws(d0) >= 0) goto L9914;
    r->a2 += r->d2; if (rr_dbf(&d4)) goto Ltop;
    return;
L9914:                                                       /* single masked 2-long blit + fill */
    a0 += sign_ext16((uint16_t)d0);
    d1 = rr_wset(d1, (uint16_t)d0);                          /* move.w d0,d1 */
    d0 = rr_wset(d0, (uint16_t)(d0 - r->d2));                /* sub.w d2,d0 */
    if (rr_ws(d0) >= 0) goto L993c;
    rr_copy_long(img, &a0, &a1);
    rr_andw(img, a0 - 4, d3);                                /* and.w d3,-4(a0) */
    rr_copy_long(img, &a0, &a1);
    d1 = rr_wset(d1, (uint16_t)((uint16_t)d1 >> 3));         /* lsr.w #3,d1 */
    d1 = rr_wset(d1, (uint16_t)(d1 - 1));                    /* subq.w #1 */
    if (rr_ws(d1) < 0) goto L9934;
    a0 = r->a2;
    do { rr_fill_pair(img, &a0, d5, d6); } while (rr_dbf(&d1));
L9934:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto Ltop;
    return;
L993c:
    rr_fill_full_row(img, &r->a2, d5, d6);                /* moveq #9,d1; dbf: full-width fill of a2 */
    if (rr_dbf(&d4)) goto Ltop;
    return;

    /* --- far copy tail (0x99dc) --- */
D2_tail:
    if (rr_ws(d0) >= 0) goto L99f0;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    if (rr_ws(d0) < 0) goto L99e8;
    a1 += 8;                                                 /* addq.l #8,a1 */
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
L99e8:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto Ltop;
    return;
L99f0:
    a0 += sign_ext16((uint16_t)d0);                          /* adda.w d0,a0 */
    d1 = rr_wset(d1, (uint16_t)d0);                          /* move.w d0,d1 */
    d0 = rr_wset(d0, (uint16_t)(d0 - r->d2));                /* sub.w d2,d0 */
    if (rr_ws(d0) >= 0) goto L9a2a;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    if (rr_ws(d0) >= 0) goto L9a0a;
    rr_copy_long(img, &a0, &a1);        /* move.l(a1)+,(a0)+ */
    rr_andw(img, a0 - 4, d3);                                /* and.w d3,-4(a0) */
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    goto L9a12;
L9a0a:
    rr_copy_long(img, &a0, &a1);
    rr_andw(img, a0 - 4, d3);
    rr_copy_long(img, &a0, &a1);
L9a12:
    d1 = rr_wset(d1, (uint16_t)((uint16_t)d1 >> 3));         /* lsr.w #3,d1 */
    d1 = rr_wset(d1, (uint16_t)(d1 - 1));                    /* subq.w #1 */
    if (rr_ws(d1) < 0) goto L9a22;
    a0 = r->a2;
    do { rr_fill_pair(img, &a0, d5, d6); } while (rr_dbf(&d1));
L9a22:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto Ltop;
    return;
L9a2a:
    rr_fill_full_row(img, &r->a2, d5, d6);                /* moveq #9,d1; dbf: full-width fill of a2 */
    if (rr_dbf(&d4)) goto Ltop;
    return;
}

/* Layer 1 (trust anchor): the byte-exact machine model, all bands. */
static const rr_bands RR_BANDS_MACHINE = {
    rr_band_A, rr_band_B, rr_band_C_near, rr_band_C_far, rr_band_D,
};
/* render_road via the machine model — verified against the oracle to anchor the default. */
void g_render_road_machine(uint8_t *image) {
    render_road_impl(image, &RR_BANDS_MACHINE);
}
