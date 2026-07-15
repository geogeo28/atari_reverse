# render_road @ Ghidra 0x19144 — authoritative reconstruction spec

The pseudo-3D road rasterizer. **PURE LEAF** (no bsr/jsr); ends `rts @ 0x199ee` (early exit) and
`rts @ 0x19a3c` (function end). A 4-byte thunk at 0x15af6 (`bra.w 0x19144`) is a plain alias.

This spec is synthesized from 8 per-slice analyses and **re-verified against the disassembly** at
every address where the analyses disagreed. Addresses are **Ghidra addresses** (= file offset +
0x10000); the disassembler prints file offsets (file 0x9xxx = Ghidra 0x19xxx). Regenerate the
authoritative disassembly with:

    cd .../projects/buggyboy && python3 ../../tools/prg_dis.py bin/BUGGYBOY.PRG --start $((0x9144 + 28)) --len 2256

> **prg_dis gotcha:** it misprints `divu.w`/`mulu.w` as `or.w`/`and.w` on address-register
> encodings. Verified: render_road contains **no** such encoding — every `and.w`/`or.w` in the
> function has a data-register or memory operand and is genuine. No `divu`/`mulu` anywhere.

## STATUS

`make test` is **GREEN** — `render_road` is verified byte-for-byte against the Musashi oracle
(`test/test_render_road.py`, whole-image diff, poison/attribution on, fuzzed across every band and
flag family). Both the near/far tail splits are reconstructed: band B via `rr_band_B(..., second)`,
band C via `rr_band_C_near`/`rr_band_C_far`, band D via `rr_band_D(..., second)`. The final
divergence fixed during reconstruction was band B's **far** tail (0x19514): the near and far copies
share a preamble but the far copy omits the pre-`asr` `addq.l #8,a0/a1` and uses a wider masked blit,
so reusing the near tail shifted every narrow no-split row's edge cell by one column.

---

## 1. Flag-bit legend (btst #n on the 32-bit control long `d0`)

The control long is `move.l (a5)+,d0` then `add.w (a4)+,d0` (the add touches **only the low 16
bits** — the road half-width; the high 16 bits are the flag word and are preserved). Bits are
indexed from bit 0 of the long. `#define` names (all already in road.c):

| bit | mask        | name            | role |
|-----|-------------|-----------------|------|
| 16  | 0x00010000  | `RR_F_MASK_A`   | Band B: load edge mask `d3` from `a1+0x2808`; clear left fill (d5=0). |
| 17  | 0x00020000  | `RR_F_SPLIT_B`  | Band B: row has an edge split (else full-width `L943c`). |
| 18  | 0x00040000  | `RR_F_SPLIT_A`  | Band A: edge split present (else center-run `L92d6`). |
| 19  | 0x00080000  | `RR_F_SPLIT_C`  | Bands C/E: edge split present (else no-split `L9666`). |
| 20  | 0x00100000  | `RR_F_SPLIT_D`  | Bands D/F/G: edge split present (else no-split `L98f8`). |
| 21  | 0x00200000  | `RR_F_SRC_400`  | src sub-offset selector (+0x400). |
| 22  | 0x00400000  | `RR_F_SRC_100`  | src sub-offset selector (+0x100) / fill-side / const-src selector. |
| 23  | 0x00800000  | `RR_F_WIDE`     | wide/solid-centre branch (vs the edge-split blit). |
| 24  | 0x01000000  | `RR_F_MASK_A2`  | Bands D/F/G: load edge mask `d3` from `a1+0x2800`; clear left fill (d5=0). |
| 27  | 0x08000000  | `RR_F_PLANE_HI` | swap d6 (hi-plane pattern) and select an alternate src region (+0x5800 / +0xa800). |
| 28  | 0x10000000  | `RR_F_SRC_CONST`| select the const edge texture 0x15baa (only when d0 >= 0 as a long). |
| 29  | 0x20000000  | `RR_F_SKIP_ABC` | Bands A/B: gate for the edge-split fast path / skip-row. |
| 30  | 0x40000000  | `RR_F_SKIP_D`   | Bands C/D/E/F/G: gate for the edge-split fast path / skip-row. |
| 31  | 0x80000000  | (sign)          | `tst.l d0; bmi/bpl` — d0 < 0 gates the const-texture override and the skip-row paths. |

Note bands A and C use `RR_F_MASK` reads **unconditionally** in the preamble (band A reads
`a1+0x2808` into d3 at 0x9182; band C reads `a1+0x2800` at 0x9594) — the flag-gated mask load is
only in bands B (bit16) and D/F/G (bit24).

## 2. Table / offset map (named constants)

    RR_DST_ROAD_OFF   0x4100     a2 = draw_buffer(image) + this  (top of on-screen road band)
    RR_PARAM_TBL      0x1623a    a4: per-scanline perspective-offset param stream (real image data)
    RR_EDGE_TBL_BASE  0x15c3a    a6 base: per-scanline edge/run table (real image data)
    A_road_edge_sel   0x18c5a    signed word added to RR_EDGE_TBL_BASE to pick a6's start
    RR_WIDTH_TBL      0x18f24    a5 = road_width_tbl (RESET to base at each band group)
    A_flip_idx        0x18bf2    signed word; A_physbase_tbl = 0x18bf4; A_buf_b = 0x18c04

    -- inter-band-group step (0x93ac / 0x956e / 0x9868) --
    RR_DST_BAND_STEP  0x3c00     a2 -= this  (rewind up the screen)   [suba.w: full 32-bit subtract]
    RR_SRC_BAND_STEP  0x0a00     a3 += this  (next texture sub-block)
    RR_EDGE_BAND_STEP 0x00c0     a6 -= this

    -- edge-mask read offsets into buf_b (d3 = *(a1 + off), a1 = buf_b + fine_x) --
    RR_MASK_OFF_HI    0x2808     bands A/B
    RR_MASK_OFF_LO    0x2800     bands C/D/E/F/G

    -- const edge textures near buf_b (image-absolute; movea.l #imm,a1) --
    RR_CONST_5B7A     0x15b7a
    RR_CONST_5B9A     0x15b9a
    RR_CONST_5BAA     0x15baa
    -- src sub-region deltas added to a1 (= buf_b + fine_x) per the flags --
    RR_SRC_A800  0xa800   RR_SRC_5800 0x5800   RR_SRC_5000 0x5000   RR_SRC_4700 0x4700
    RR_SRC_3E00  0x3e00   RR_SRC_3500 0x3500   RR_SRC_0A00 0x0a00   RR_SRC_0400 0x0400   RR_SRC_0100 0x0100

    RR_ROW_STRIDE_D2  0x00a0     d2 = ROW_STRIDE (160 bytes / scanline)
    RR_D7_WORD_MASK   0xfff8     d7.w (bands B..G): masks d0.w to a column-aligned offset

## 3. Setup (0x19144 – 0x19170) — verified byte-for-byte

    0x19144  movea.l #0x18bf2,a0        ; a0 = &flip_idx
    0x1914a  adda.w  (a0)+,a0           ; read word@0x18bf2 (flip_idx); a0 := 0x18bf4; a0 := 0x18bf4 + sext(flip_idx)
    0x1914c  movea.l (a0),a2            ; a2 = *(long)(0x18bf4 + flip_idx) == draw_buffer(image)
    0x1914e  adda.w  #0x4100,a2         ; a2 += RR_DST_ROAD_OFF
    0x19152  movea.l (0x18c04),a3       ; a3 = buf_b   (SOURCE arena base)
    0x19156  movea.l #0x1623a,a4        ; a4 = RR_PARAM_TBL
    0x1915c  movea.l #0x15c3a,a6        ; a6 = RR_EDGE_TBL_BASE
    0x19162  adda.w  (0x18c5a),a6       ; a6 += sext(A_road_edge_sel)
    0x19166  move.w  #0x00a0,d2         ; d2 = ROW_STRIDE
    0x1916a  movea.l #0x18f24,a5        ; a5 = RR_WIDTH_TBL
    0x19170  moveq   #0x5f,d4           ; band A row counter (0x5f -> 96 rows)

**Resolved disagreement (Analysis 1):** the `adda.w (a0)+,a0` at 0x1914a is NOT a 2-byte skew. The
post-increment advances a0 from 0x18bf2 to 0x18bf4, then the add lands a0 at `0x18bf4 +
sext(flip_idx)`, so `movea.l (a0),a2` reads `physbase_tbl[flip_idx]` — exactly `draw_buffer(image)`.
C idiom: `a2 = draw_buffer(image) + RR_DST_ROAD_OFF`. Do **not** subtract 2. `d7` is left 0/scratch
in band A (band A never masks d0 with d7); it is set to 0xfffffff8 at the first inter-band step.

## 4. Register threading model

`a0..a6` hold image byte offsets; `d0..d7` are 32-bit with 16-bit-faithful word ops. Registers that
survive band-to-band (threaded through the shared `rr_regs` struct in road.c):

- **a2** — DST cursor. `+= ROW_STRIDE` once per drawn row; `-= RR_DST_BAND_STEP` at each group step.
- **a3** — SOURCE base (buf_b). Only changed by the group step (`+= RR_SRC_BAND_STEP`); read into a1
  each row, never otherwise written inside a band.
- **a4** — param stream. Streams monotonically across ALL bands (never reset). Advance is
  data-dependent per row (see each band); a wrong advance desyncs everything downstream.
- **a5** — control stream = road_width_tbl. **RESET to RR_WIDTH_TBL at the start of every band
  group** (A, B-group, C-group, D-group). `+= 4` per row within a group.
- **a6** — edge table. `-= RR_EDGE_BAND_STEP` at each group step; `+= 2` per row (data-dependent).
- **d2** — ROW_STRIDE 0xa0. Band A transiently overwrites `d2.w` (via `move.w d0,d2`) but restores
  0xa0 before every band exit; bands B..G never write d2. Treat as constant 0xa0 across boundaries.
- **d7** — 0x00000000 in band A, then 0xfffffff8 from the first inter-band step onward (d7.w=0xfff8).
- **d0,d1,d3,d5,d6,a0,a1** — per-row scratch, reinitialized at each row top; dead across boundaries.

Band groups and the calls (road.c `g_render_road`):

    Band A  0x19172  d4=0x5f  (96 rows)   -- inline
    step 0x193ac: a2-=3c00; a3+=0a00; a6-=00c0; d7=0xfffffff8; a5=WIDTH_TBL
    Band B1 0x193c2  d4=0x04  (5 rows)    rr_band_B(0x04)
    Band B2 0x1948c  d4=0x5a  (91 rows)   rr_band_B(0x5a)
    step 0x1956e: a2-=3c00; a3+=0a00; a6-=00c0; a5=WIDTH_TBL   (d7 NOT re-set — stays 0xfffffff8)
    Band C  0x19582  d4=0x05  (6 rows)    rr_band_C_near(0x05)
    Band E  0x196b8  d4=0x59  (90 rows)   rr_band_C_FAR(0x59)   *** see §Band E: distinct tail ***
    step 0x19868: a2-=3c00; a3+=0a00; a6-=00c0; a5=WIDTH_TBL
    Band F  0x1987c  d4=0x05  (6 rows)    rr_band_D(0x05, second=0)
    Band G  0x19950  d4=0x59  (90 rows)   rr_band_D(0x59, second=1)  -> ends the function via rts

There is **no** inter-group step between C and E, nor between F and G — each far copy immediately
follows its near copy and continues the same a2/a3/a4/a5/a6 cursors.

## 5. Shared per-scanline preamble

Every band begins each row with this (only the mask-read offset and the d5/d6 init differ):

    a1 = a3;  a0 = a2;
    d0 = be32(img + a5); a5 += 4;                              // control long
    d0.w = (uint16)(d0.w + be16(img + a4)); a4 += 2;           // + perspective offset (LOW WORD only)
    d1 = 0xf & d0; d1.w = (uint16)(d1.w << 4);                 // fine-x nibble * 16
    a1 += sign_ext16(d1.w);                                    // src column
    d1.w = be16(img + a4); a4 += 2;                            // 2nd param word (edge offset / count seed)
    // d5/d6/d3 init per band (see below), then flag dispatch

Per-band d5/d6/d3 init and mask read:

- **Band A:** `d3 = be32(a1+0x2808)` (unconditional); `d5 = 0xffffffff`; `d6 = 0x0000ffff`.
- **Band B:** `d5 = 0xffff0000`; `d6 = 0x0000ffff`; `d3 = 0xffffffff`; if bit16: `d5=0, d3=be32(a1+0x2808)`.
- **Band C/E:** `d3 = be32(a1+0x2800)` (unconditional); `d5 = 0xffffffff`; `d6 = 0x0000ffff`.
- **Band D/F/G:** `d5 = 0xffff0000`; `d6 = 0x0000ffff`; `d3 = 0xffffffff`; if bit24: `d5=0, d3=be32(a1+0x2800)`.

In all bands: if `bit27 (PLANE_HI)` → `d6 = swap(d6)` (0x0000ffff → 0xffff0000).

## 6. The seven bands (clean pseudocode; labels = Ghidra addresses)

The existing road.c is a faithful 1:1 machine model for **Bands A, B, C-near, F, G** and should be
treated as the reference for those. Below is the structural pseudocode plus the exact per-band
divergences. `ws(x)` = signed low word `(int16_t)x`; `dbf(dN)` = decrement low word, loop while != -1.

### Band A (0x19172 – 0x193ac; 96 rows), inline

    preamble (mask off 0x2808; d5=0xffffffff, d6=0x0000ffff; swap d6 if bit27)
    if !SPLIT_A(18)          -> L92d6 (center-run)
    a6 += 2
    if WIDE(23)              -> L92a8 (wide src select: +0x5000 ±0x400/±0x100)
    if !SKIP_ABC(29)         -> L92da (hi/const src select)
    // 0x91b0 edge-split fast path:
    d6=0; a1 += sext(d1); d1 = be32(a4); a4 += 4;  // *** move.l (a4)+,d1: +4 bytes ***
    d0.w = ws(d0) >> 1;                            // asr.w #1
    if !PLANE_HI(27)         -> L9230 (a6-relative masked src)
    // 0x91c0: d5=0; a1 += 0xa800; if be16(a6-2)!=0 a1 += 0x0a00; align d0 &= 0xfff8
    //   then left-clip walker L91f8 (4/2-long copies bounded by adding 8 to d0), fill d6, or
    //   the masked variant L9230/L925c (last copied long masked by d3, fill d5/d6).
    L928c: interior color-select (bit27); L936a: WIDE-tail color select (bits 23/22/21)
    L9384: backward tail-fill from saved d7 (move.l d6/d5,-(a0), bounded by cmp.w d2,d0 and dbf d1)

Key band-A specifics: uses `move.l (a4)+,d1` (+4) on the edge-split path (0x91b4) and the center-run
path (0x92f6); saves the DST start in `d7` (`move.l a0,d7`) and the aligned width in `d2.w`, then
reuses them in the L9384 backward fill; restores `d2.w = 0xa0` at 0x938a before the row exit.

### Band B (0x193c2 d4=4 / 0x1948c d4=0x5a); `rr_band_B`

    preamble (d5=0xffff0000, d6=0x0000ffff, d3=0xffffffff)
    if bit16(MASK_A):  d5=0; d3 = be32(a1 + 0x2808)
    if !SPLIT_B(17)          -> L943c (no-split: a1 += sext(d1) + sext(be16(a6)); a6+=2)
    if !SKIP_ABC(29)         -> L9406
    if (int32)d0 < 0:  a6+=2; a2+=ROW_STRIDE; dbf -> next row   // full skip row
    L9406: a6+=2
      if !WIDE(23)           -> L9440
      d6=0; a1 += 0x4700
      if SRC_400(21): a1+=0x400; if SRC_100(22) -> L944a else a1=0x15b7a -> L944a
      else: d5=notw(d5); if SRC_100(22) -> L944a else a1=0x15b9a -> L944a
    L9440: if PLANE_HI(27): a1 += 0x5800
    L944a: a0+=8; a1+=8; d0.w = ws(d0)>>1; d0.w &= d7(0xfff8); a0 += sext(d0.w); d0.w += 8
      if ws(d0) < 0:  // wide big-fill: 10 iters of (d5,d6,d5,d6) written through a2 (=160 bytes)
      else L946c: d0.w -= d2; if ws(d0) < 0 { copy long; and.w d3,-4(a0); copy long;
                  then d0.w+=8; while ws(d0)<0 fill (d5,d6) }; a2 += ROW_STRIDE
    Per-row: a4 += 4 (2 words); a5 += 4; a6 += 2 (every path).

### Band C — NEAR copy (0x19582, d4=0x05; 6 rows)

    preamble (mask off 0x2800 unconditional; d5=0xffffffff, d6=0x0000ffff; swap d6 if bit27)
    if !SPLIT_C(19)          -> L9666 (no-split: a1 += sext(d1) + sext(be16(a6)); a6+=2)
    a6 += 2
    if WIDE(23)              -> L9638 (wide src: +0x3e00 ±0x400/±0x100, d5/d6 select)
    if !SKIP_D(30)           -> L966a (hi/const src select: +0x5800 or a1=0x15baa if d0>=0)
    // 0x95c0 fast edge-split:
    d6=0; d0.w = ws(d0)>>1; d0.w &= 0xfff8;
    if ws(d0) < 0:  a2+=ROW_STRIDE; dbf -> next row      // skip row
    L95d2: a1 += sext(d1); a0 += sext(d0.w); d1.w = d0.w;
      if PLANE_HI(27): d5=0; a1+=0xa800; if be16(a6-2)!=0 a1+=0x0a00; d0.w-=d2;
                       if ws(d0)>=0 -> L9622 else copy 2 longs -> L9608
      else L95fa:      a1 += sext(be16(a6-2)); d0.w-=d2;
                       if ws(d0)>=0 -> L9622 else { copy long; copy long masked by d3 (and.l d3) } -> L9608
    L9608: d1.w = (uint16)d1.w >> 3; d1.w -= 1; if ws(d1)>=0 { a0=a2; fill (d5,d6) dbf d1 }; a2+=ROW_STRIDE
    L9622: 10 iters of (d5,d6,d5,d6) through a2 (full row); a2 advanced by the writes
    L9686 (near merge/blit): d0.w = ws(d0)>>1; d0.w &= 0xfff8; d0.w -= 8;
      if ws(d0) >= 0 -> L969e;
      else { d0.w += 8; if ws(d0)<0 skip; else copy 2 longs; a2+=ROW_STRIDE; dbf }
    L969e: a0 += sext(d0.w); d0.w -= d2; if ws(d0)>=0 skip;
      else { fill (d5,d6); d0.w+=8; if ws(d0)>=0 skip; else copy 2 longs }; a2+=ROW_STRIDE; dbf
    Per-row: a4 += 4 (2 words); a5 += 4; a6 += 2.

### Band E — FAR copy of band C (0x196b8, d4=0x59; 90 rows) — **DISTINCT tail, NOT the near copy**

The preamble and src-dispatch (0x96b8 – 0x9802) are byte-identical to the near copy **except two
divergences confirmed in the disassembly**:

1. **Fast edge-split path (0x96f6)** — the far copy inserts `addq.l #2,a4` (0x96f8) that the near
   copy (0x95c0) does not, and reorders: far = `adda.w d1,a1; addq.l #2,a4; asr.w #1,d0; moveq
   #0,d6; btst #27,d0 …`, near = `moveq #0,d6; asr.w #1,d0; and.w d7,d0; …`. **The far fast-split
   path consumes an extra param word (a4 += 2).**

2. **Merge/blit tail (0x9808)** — the far copy is a completely different, longer tail than the near
   `L9686`. It begins with an extra `move.w (a4)+,d1` (0x9808, a4 += 2) and then:

        0x9808  d1.w = be16(a4); a4 += 2;          // *** far-only extra param read ***
        0x980a  d0.w = ws(d0) >> 1;                // asr.w #1
        0x980c  d0.w &= d7 (0xfff8);
        0x980e  if ws(d0) >= 0 -> L9822
        0x9810  d0.w += 8; if ws(d0) < 0 -> L981a
        0x9814  a1 += 8; copy 2 longs
        0x981a  L981a: a2 += ROW_STRIDE; dbf d4,$96b8; bra $9868   // -> group step
        0x9822  L9822: a0 += sext(d0.w); d3.w = d0.w;   // *** move.w d0,d3 (near uses d1) ***
        0x9826  d0.w -= d2;
        0x9828  if ws(d0) < 0 -> L9846
        0x982a  d0.w -= 8; if ws(d0) < 0 -> L984c
        0x982e  a2 += ROW_STRIDE; d0.w = (uint16)d0.w >> 3;   // lsr.w #3
        0x9832  d1.w -= d0.w;
        0x9834  if ws(d1) < 0 -> L9840
        0x9836  a0 = a2;
        0x9838  L9838: move.l d6,-(a0); move.l d5,-(a0); dbf d1,$9838   // reverse fill
        0x9840  L9840: dbf d4,$96b8; bra $9868
        0x9846  L9846: d0.w = 0; copy 2 longs
        0x984c  L984c: d0.w += 8; copy 2 longs; d0.w += 8; a0 -= sext(d0.w); d3.w -= 8;
        0x9858  if ws(d3) < 0 -> L9862
        0x985a  L985a: move.l d6,-(a0); move.l d5,-(a0); dbf d1,$9856  // NB dbf target 0x9856: re-runs subq #8,d3
        0x9862  L9862: a2 += ROW_STRIDE; dbf d4,$96b8
        0x9868  (falls through to the C->D group step)

Note the L985a loop's `dbf d1,$9856` target re-executes `subq.w #8,d3` and `suba.w d0,a0` each pass
— faithful transcription is required. Band E is reconstructed as its own function (`rr_band_C_far`)
that (a) inserts `addq.l #2,a4` on the fast-split path, (b) inserts the `move.w (a4)+,d1` at the
merge label, and (c) uses this 0x9808–0x9864 tail. (Verified; see §STATUS.)

### Band F — near copy of band D (0x1987c, d4=0x05; 6 rows); `rr_band_D(second=0)`

    preamble (d5=0xffff0000, d6=0x0000ffff, d3=0xffffffff)
    if bit24(MASK_A2): d5=0; d3 = be32(a1 + 0x2800)
    if !SPLIT_D(20)          -> L98f8 (no-split: a1 += sext(d1) + sext(be16(a6)); a6+=2)
    if !SKIP_D(30)           -> L98c0
    if (int32)d0 < 0:  a6+=2; a2+=ROW_STRIDE; dbf -> next row     // skip row
    L98c0: a6+=2
      if !WIDE(23)           -> L98fc
      d5=0; d6=0; a1 += 0x3500
      if SRC_400(21): a1+=0x400; if SRC_100(22) -> L9906 else a1=0x15b7a -> L9906
      else: d5=notw(d5); if SRC_100(22) -> L9906 else a1=0x15b9a -> L9906
    L98fc: if PLANE_HI(27): a1 += 0x5800
    L9906 (near tail): d0.w = ws(d0)>>1; d0.w &= 0xfff8;
      if ws(d0) < 0:  a2+=ROW_STRIDE; dbf -> next row
      L9914: a0 += sext(d0.w); d1.w=d0.w; d0.w -= d2;
        if ws(d0) < 0 { copy long; and.w d3,-4(a0); copy long;
                        d1.w=(uint16)d1.w>>3; d1.w-=1; if ws(d1)>=0 { a0=a2; fill (d5,d6) dbf d1 } }
        else L993c: 10 iters (d5,d6,d5,d6) through a2 (full row)
        a2 += ROW_STRIDE; dbf
    Per-row: a4 += 4; a5 += 4; a6 += 2 (every path).

### Band G — far copy of band D (0x19950, d4=0x59; 90 rows); `rr_band_D(second=1)` — ends the function

Preamble + src-dispatch (0x9950 – 0x99d4) are byte-identical to band F. The tail (0x99d8) differs
and terminates the function. This IS correctly modelled by road.c's `D2_tail`:

    L99d8 (far tail): d0.w = ws(d0)>>1; d0.w &= 0xfff8;
      if ws(d0) < 0 (0x99dc bpl $99f0 else): d0.w += 8; if ws(d0) < 0 -> L99e8;
         else a1 += 8; copy 2 longs; L99e8: a2 += ROW_STRIDE; dbf d4,$9950; rts   // *** rts @0x99ee ***
      L99f0: a0 += sext(d0.w); d1.w = d0.w; d0.w -= d2;
        if ws(d0) >= 0 -> L9a2a (10-iter full-row fill through a2; dbf; rts @0x9a3c)
        d0.w += 8;
        if ws(d0) >= 0 -> L9a0a { copy long; and.w d3,-4(a0); copy long } -> L9a12
        else { copy long; and.w d3,-4(a0); copy 3 longs } -> L9a12
      L9a12: d1.w=(uint16)d1.w>>3; d1.w-=1; if ws(d1)>=0 { a0=a2; fill (d5,d6) dbf d1 };
             a2 += ROW_STRIDE; dbf d4,$9950; rts @0x9a3c   // *** function end ***

Two `rts`: 0x199ee (early exit — the SKIP_D-clear short-copy path on band G's last row) and 0x19a3c
(true function end). The `rts @ 0x19990` is band G's skip-row path (bit30 set, d0<0) on the last
row. All three are inside band G; band F never returns (its last `dbf` falls into band G's entry).

## 7. 16-bit-wrap / sign-sensitive spots (mirror exactly)

- `add.w (a4)+,d0` (each preamble): modifies **only d0's low 16 bits**; the flag bits (16..31) are
  preserved. Model `d0 = (d0 & 0xffff0000) | (uint16)(d0 + word)`.
- `asr.w #1,d0` / `asr.w #3,d0` (band A): **arithmetic** signed shift of the low word; `lsr.w #3,d1`
  (bands C..G) is **logical**. Do not shift the full long. A following `btst #27,d0` still tests the
  original (unshifted) bit 27.
- `and.w d7,d0` / `andi.w #0xfff8,d0`: mask low word to 0xfff8 (column-align). After the mask the
  low word is only guaranteed non-negative in bands F/G (d7.w=0xfff8 there); the subsequent
  `bpl/bmi` tests the **word** sign (bit 15).
- `sub.w d2,d0`, `subq.w #8`, `addq.w #8`, `subq.w #1`: all word ops; `bpl/bmi` test `ws(d0)` /
  `ws(d1)` (bit 15), NOT bit 31.
- `tst.l d0; bmi/bpl`: tests the **full 32-bit** sign (bit 31) — gates the const-texture override
  and the skip-row fast paths. Distinct from the word-sign branches.
- `adda.w`/`suba.w Xn,An` (all pointer adjusts incl. the group steps): sign-extend the 16-bit
  operand to 32 bits and add to the **full 32-bit** address register (no 16-bit wrap of the pointer).
  `adda.l #0xa800,a1` (bands A/C/E) is a full 32-bit add.
- `and.l d3,(a0)+` (bands A/C/E masked copy) masks a **full long**; `and.w d3,-4(a0)` (bands B/D/F/G)
  masks **only the high word** of the just-written long. Do not conflate the two.
- `swap d6`: 32-bit half-word exchange (0x0000ffff -> 0xffff0000).
- `move.l a0,d7` / `movea.l d7,a0` (band A only): d7 doubles as saved-DST scratch in band A (it is
  NOT the 0xfff8 mask there — that role begins at the first inter-band step).
- `dbf dN,label`: decrement low word; loop while result != 0xffff. `d4` seeds give (seed+1) rows.

## 8. Files

- Reconstruction: `recreate/src/road.c` (`g_render_road` + `rr_band_B/C/D`). All seven bands verified
  byte-for-byte, including band E (far band C) via its distinct fast-split + merge tail (`rr_band_C_far`).
- Test: `recreate/test/test_render_road.py` (differential vs Musashi; GREEN).
- Disassembly: `python3 ../../tools/prg_dis.py bin/BUGGYBOY.PRG --start $((0x9144 + 28)) --len 2256`.
