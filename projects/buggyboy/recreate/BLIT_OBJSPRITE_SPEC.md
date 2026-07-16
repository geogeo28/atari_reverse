# SPEC: roadside-object sprite draw-handler family @ 0x14620 / 0x1465c / 0x14664 (+ tail 0x14676)

Authoritative reconstruction spec, synthesized from three independent slice analyses (helper-bodies,
descriptor-record, caller-contract) and re-verified bit-exact against `bin/BUGGYBOY.PRG`.

All addresses are **Ghidra addresses** = file offset + `0x10000` (file 0x4620 = Ghidra 0x14620). The
whole block is disassembly-driven (no Ghidra decomp) and ends by calling the already-verified leaf
`blit_objshift` @ 0x14680 (`g_blit_objshift` in `recreate/src/blit.c`,
ABI `x@D0 colour@D1 rows_m1@D4 dst@A0 src@A1 stride_ptr@A3`).

---

## 0. Decode traps — verified bit-exact (READ FIRST)

`prg_dis.py` misprints `mulu.w`/`divu.w` as `and.w`/`or.w` when it wrongly reads an address-register
destination. Each suspicious byte below was decoded by hand (opmode = bits 8-6: `001`=AND.W ea→Dn,
`011`=MULU.W ea→Dn, `101`=AND.W Dn→ea) and confirmed:

| Ghidra | bytes | prg_dis PRINTS | ACTUAL (verified) | why |
|---|---|---|---|---|
| 0x1463a | `c4c4` | `and.w d4,a2` | **`mulu.w d4,d2`** | `1100 010 011 000 100`: Dn=D2, opmode=`011`=MULU.W, ea=D4. AND has no A-reg dest. **LOAD-BEARING** — sets the sprite pixel height. |
| 0x1466c | `c479 00008c60` | `and.w $8c60,d2` | **`and.w $18c60.l,d2`** (genuine) | opmode `001`=AND.W ea→Dn, dest D2. This one really is AND. |

The `and.w`/`or.w` that prg_dis prints at 0x1462e, 0x14648, 0x14670, 0x1467a are **not instructions** —
they are the trailing extension/immediate words of the preceding `move.w $18c56,d7` / `movea.l #…,a3` /
`adda.w …,a1` / `movea.l #…,a3`.

**movem masks** (68k predecrement uses reversed bit order; postincrement uses normal order):

| Ghidra | bytes | decoded |
|---|---|---|
| 0x14640 | `48a7 1400` | `movem.w d3/d5,-(a7)` — pushed low→high addr as **[D3][D5]** (a7 ends at the D3 slot) |
| 0x14650 | `4c9f 0011` | `movem.w (a7)+,d0/d4` — read low→high as **D0←D3-slot, D4←D5-slot** |

This is a deliberate **register rename across the blit**: after the call, `D0 = pre-call D3` and
`D4 = pre-call D5 (= pre-call D4)`. Get this wrong and the popped D0/D4 are swapped/wrong.

---

## 1. Dispatch & caller contract (context only — do NOT reconstruct)

`draw_object_list` @ 0x1306e dispatches per roadside object through a jump table at **0x13144**
(`move.w (0,a3,d3.w),d3 ; jsr (0,a3,d3.w)`, a3=0x13144, entries are 16-bit offsets from 0x13144).
- **0x1465c** and **0x14664** are table-reachable object-type draw handlers.
- **0x14620** is a shared subroutine reached only by `bsr` from a handler (0x1465c, and siblings).
- **0x14676** is a shared tail entered by fall-through (0x14664) or `bra` (0x1465c).

Per drawn object, before the `jsr`, `draw_object_list` sets (the three mulu misprints in the caller —
0x130ee `c2fc 00d0`=`mulu.w #0xd0,d1`, 0x1310c `cef9`=`mulu.w view_flags,d7`, 0x13114 `cec2`=`mulu.w
d2,d7` — are documented for completeness; they shape the record geometry but are the caller's, not ours):

```
d2 = 0xa0                                             ; scanline stride constant (= OBJD_WIDTH)
d0 = <x accum> + word@a4(scroll) + word@rec+0xa       ; sub-pixel screen x accumulator
d1 = word@(slotbase - 0x10)                           ; colour index (used by 0x1465c tail)
d4 = word@rec+0x4                                     ; rows/height seed
d7 = (((byte@rec-0xb - d4.b) * view_flags) >> 4) * d2 ; vertical band offset (already applied to a0)
a0 = a6(buffer base) + word@a5(band) - d7 + word@rec+0x8   ; dst scanline base
a1 = *A_buf_c + long@rec+0x0                          ; src sprite stream
a2 = *A_buf_a + 0x8a0 + type_index*0xd0 + d6, walked to rec+0xa  ; record cursor
a6 = draw-buffer base                                 ; used only by 0x14664
```

`slotbase = *A_buf_a + 0x8a0 + type_index*0xd0`; the per-object record `rec = slotbase + d6`. On entry
to a handler **a2 = rec + 0xa** (the caller's last field read at rec+0xa was `add.w (a2),d0`, no post-inc).

### Descriptor-record field map (offsets from `rec`)

| offset | size | meaning | read by |
|---|---|---|---|
| slotbase-0x10 | word | colour index → D1 | caller |
| rec-0xb | byte | height/scale byte (drives d7 vertical offset) | caller |
| rec+0x0 | long | src-stream delta: `a1 = *A_buf_c + this` | caller |
| rec+0x4 | word | rows/height seed → D4 (helper copies to D5) | caller |
| rec+0x6 | word | handler selector (index into table @ 0x13144) | caller |
| rec+0x8 | word | x screen offset added to a0; **re-read** by 0x14620 via `move.w -(a2),d3` | caller + 0x14620 |
| rec+0xa | word | added to d0 (fine-x); a2 left here on handler entry | caller |
| rec+0xc + (view>>1) | byte×4 | per-view rows-1 byte, indexed `4(a2,d7.w)` with a2=rec+0x8 | 0x14620 |
| rec+0xc / rec+0xe | word | per-parity src offset, `2(a2,d2.w)` with a2=rec+0xa, d2∈{0,2} | 0x14664 |

---

## 2. In-register contract per entry (for the proto storage)

`d2` is always `0xa0` (`OBJD_WIDTH`) on entry. `a3` is scratch (each entry sets it to `A_blit_mode`).

**0x14620** (shared helper — reached only by `bsr` from a handler):
- **In:** `d0`=x accum, `d1`=colour (passed straight to blit), `d2`=0xa0, `d3`=x contribution
  (immediately overwritten by `move.w -(a2),d3`), `d4`=rows/height seed, `d7`=vertical offset word
  (re-applied to a0, then overwritten), `a0`=dst scanline base, `a1`=src stream, `a2`=rec+0xa.
- **Out (after rts):** `d0`=final base col (renamed from D3 = word@rec+8 + old d0),
  `d4`=rows-1 copy (renamed from D5 = old d4), `a0`=sprite-top dst, `a1`=src−0xa0; d2/d3/d5/d7 clobbered,
  a2 clobbered, a3=`A_blit_mode`. Stack net zero.

**0x1465c** (handler — save colour, run 0x14620, then tail):
- **In:** the full caller contract of §1 (same registers), plus relies on nothing extra.
- Draws the sprite twice: 0x14620 pass (mode word 8), then the 0x14676 tail (mode word 0xa8),
  with `d1` restored to the caller colour for the second pass.

**0x14664** (handler — recompute dst from A6, adjust src, fall into tail):
- **In:** caller contract of §1 **plus a6 = draw-buffer base**. Uses d0/d1/d4/a1/a2 and a6.
  Does NOT call 0x14620. Overrides `a0 = a6 + 0x3ac0`; adjusts `a1 += word@2(a2,d2.w)`.

### proto lines (verify storage before committing to names.txt)

```
proto 0x14620 draw_obj_sprite_hi   x@D0 colour@D1 width@D2 rows_seed@D4 voff@D7 dst@A0 src@A1 rec@A2
proto 0x1465c draw_obj_handler_dbl x@D0 colour@D1 width@D2 rows_seed@D4 voff@D7 dst@A0 src@A1 rec@A2
proto 0x14664 draw_obj_handler_lo  x@D0 colour@D1 rows_m1@D4 src@A1 rec@A2 base@A6
fn   0x14676 draw_obj_blit_tail
var  0x18cb0 blit_mode_word
var  0x18c60 view_parity_flag
```

---

## 3. Exact instruction decode

### 0x14620 helper
```
14620  3a04           move.w d4,d5                 ; D5 = D4 (rows seed copy; survives blit → renamed to D4)
14622  3622           move.w -(a2),d3              ; a2 -= 2 (→ rec+8); D3 = word@rec+8  (OVERWRITES caller D3)
14624  90c3           suba.w d3,a0                 ; A0 -= (int16)D3
14626  d0c7           adda.w d7,a0                 ; A0 += (int16)D7  (re-apply caller vertical offset)
14628  d640           add.w  d0,d3                 ; D3 = word@rec+8 + D0  (final base col; D0 unchanged)
1462a  3e39 00018c56  move.w view_flags,d7         ; D7 = *A_view_flags (0,2,4,6)
14630  e24f           lsr.w  #1,d7                 ; D7 >>= 1  (→ 0,1,2,3 view index)
14632  1832 7004      move.b 4(a2,d7.w),d4         ; D4.b = byte@(rec+0xc + view_idx)  (OVERWRITES D4 low byte)
14636  2448           movea.l a0,a2               ; A2 = A0
14638  94c2           suba.w d2,a2                ; A2 -= 0xa0
1463a  c4c4           MULU.W d4,d2                ; D2 = (u16)D2 * (u16)D4 = 0xa0 * rows_byte  (**mulu, not and**)
1463c  94c2           suba.w d2,a2                ; A2 -= (int16)D2  → A2 = sprite-top (the caller's tail dst, restored to A0 after the blit; A0 itself is unchanged and is the blit's dst)
1463e  2f0a           move.l a2,-(a7)             ; push A2 (long) → restored to A0 after blit
14640  48a7 1400      movem.w d3/d5,-(a7)         ; push D3 then D5 (stack: [D3][D5][A2])
14644  267c 00018cb0  movea.l #A_blit_mode,a3    ; A3 = 0x18cb0
1464a  36bc 0008      move.w #8,(a3)             ; mode word = 8  (OBJH_MODE_MAIN)
1464e  6130           bsr.s  blit_objshift        ; call g_blit_objshift(x=D0,col=D1,rows_m1=D4,dst=A0,src=A1,A3)
14650  4c9f 0011      movem.w (a7)+,d0/d4         ; D0 ← saved D3, D4 ← saved D5  (rename)
14654  205f           movea.l (a7)+,a0           ; A0 ← saved A2 (sprite-top)
14656  92fc 00a0      suba.w #0xa0,a1            ; A1 -= 0xa0 (rewind src one band)
1465a  4e75           rts
```

### 0x1465c handler
```
1465c  3f01           move.w d1,-(a7)             ; save colour across the 0x14620 call
1465e  61c0           bsr.s  0x14620
14660  321f           move.w (a7)+,d1             ; restore colour for the tail's blit
14662  6012           bra.s  0x14676              ; fall into shared tail (2nd blit, mode 0xa8)
```

### 0x14664 handler
```
14664  204e           movea.l a6,a0              ; A0 = A6 (buffer base)
14666  d0fc 3ac0      adda.w #0x3ac0,a0          ; A0 = A6 + 0x3ac0 (fixed dst band)
1466a  7402           moveq  #2,d2               ; D2 = 2
1466c  c479 00018c60  and.w  view_parity_flag,d2 ; D2 = 2 & word@0x18c60  (→ 0 or 2)  (**genuine and.w**)
14672  d2f2 2002      adda.w 2(a2,d2.w),a1       ; A1 += (int16)word@(rec+0xc | rec+0xe)  [a2 = rec+0xa]
                       (falls through into 0x14676)
```

### 0x14676 shared tail — sets mode 0xa8 and FALLS THROUGH into blit_objshift (no bsr)
```
14676  267c 00018cb0  movea.l #A_blit_mode,a3    ; A3 = 0x18cb0
1467c  36bc 00a8      move.w #0xa8,(a3)          ; mode word = 0xa8  (OBJH_MODE_TAIL)
14680  (blit_objshift entry — execution falls straight in; its rts returns to the handler's caller)
```

Contrast: 0x14620 uses `bsr` (returns to 0x14650 to pop/rename and rewind A1) with mode 8; the tail is
a fall-through with mode 0xa8. `g_blit_objshift`'s `stride_ptr` must therefore be `A_blit_mode`
(0x18cb0), and the mode word (8 or 0xa8) is written there before the call — the leaf reads it per row
via A3 (`suba.w (a3),a1`).

---

## 4. Clean pseudocode (C-style, calling g_blit_objshift)

16-bit ops wrap mod 2^16 (mirror with `uint16_t`/`int16_t`). `move.b 4(a2,d7.w),d4` writes only D4's
low byte; the blit reads `(int16_t)D4`, so with a zeroed/positive byte it is the rows-1 value.

```c
#define A_blit_mode     0x18cb0   /* per-row src-stride/mode word the leaf reads via A3 */
#define OBJH_MODE_MAIN  0x8       /* mode for the 0x14620 (first) pass */
#define OBJH_MODE_TAIL  0xa8      /* mode for the 0x14676 (tail/second) pass */
#define OBJH_BAND_LO    0x3ac0    /* fixed dst-band offset from A6 (0x14664) */
#define REC_XOFF        0x8       /* word@rec+8 re-read by move.w -(a2),d3 */
#define REC_ROWS_TBL    0xc       /* per-view rows-1 byte table base = rec+0xc; index 4(a2,d7) a2=rec+8 */
#define REC_SRC_OFF     0xc       /* per-parity src offset 2(a2,d2) with a2=rec+0xa */
/* OBJD_WIDTH (0xa0), A_view_flags, A_buf_a, A_buf_c already defined. */

/* Shared tail: set mode 0xa8, blit once. `rec_cursor` = a2 value (rec+0xa) — unused by the tail
   itself; kept for symmetry with the fall-through entries. */
static void draw_obj_blit_tail(uint8_t *img, uint16_t x, uint16_t colour, uint16_t rows_m1,
                               uint32_t dst, uint32_t src) {
    wr16(img + A_blit_mode, OBJH_MODE_TAIL);
    g_blit_objshift(img, x, colour, rows_m1, dst, src, A_blit_mode);
}

/* 0x14620: compute geometry from the record + view_flags, first blit (mode 8). Returns the renamed
   registers the caller (0x1465c) reuses for the tail. */
struct obj_hi_out { uint16_t d0_x; uint16_t d4_rows; uint32_t a0_dst; uint32_t a1_src; };

static struct obj_hi_out
draw_obj_sprite_hi(uint8_t *img, uint16_t d0_x, uint16_t colour, uint16_t width /*=0xa0*/,
                   uint16_t rows_seed, uint16_t voff, uint32_t a0_dst, uint32_t a1_src,
                   uint32_t rec_cursor /* = rec+0xa */) {
    uint16_t d5_rows = rows_seed;                                  /* move.w d4,d5 */
    uint32_t a2 = rec_cursor - 2;                                  /* move.w -(a2),d3  → a2 = rec+8 */
    uint16_t xoff = rd16(img + a2);                                /* D3 = word@rec+8 */
    a0_dst = (uint32_t)(a0_dst - sign_ext16(xoff));               /* suba.w d3,a0 */
    a0_dst = (uint32_t)(a0_dst + sign_ext16(voff));               /* adda.w d7,a0 */
    uint16_t base_col = (uint16_t)(xoff + d0_x);                   /* add.w d0,d3 (D0 unchanged) */

    uint16_t view = rd16(img + A_view_flags) >> 1;                 /* view index 0..3 */
    uint16_t rows_byte = img[a2 + 4 + view];                       /* move.b 4(a2,d7.w),d4 (a2=rec+8) */
    /* move.b writes only D4's LOW byte; the high byte survives from rows_seed and the blit reads
       (int16)D4 (in practice rows_seed's high byte is 0, so rows_m1 == rows_byte). */
    uint16_t rows_m1 = (uint16_t)((rows_seed & 0xff00) | rows_byte);

    /* CORRECTION (verified): the blit runs with A0 = a0_dst (the −xoff,+voff scanline base). The
       sprite-top (A2) is pushed and restored to A0 only AFTER the call — it is the caller's tail
       dst, NOT the blit's dst. `movea.l a0,a2` copies A0 into A2 but leaves A0 unchanged. */
    uint32_t dst_top = a0_dst;                                     /* movea.l a0,a2 */
    dst_top = (uint32_t)(dst_top - sign_ext16(width));            /* suba.w d2,a2 */
    uint16_t height = (uint16_t)(width * rows_byte);              /* MULU.W d4,d2 (low 16 bits used) */
    dst_top = (uint32_t)(dst_top - sign_ext16(height));          /* suba.w d2,a2 → sprite top (A2) */

    wr16(img + A_blit_mode, OBJH_MODE_MAIN);                       /* mode word = 8 */
    g_blit_objshift(img, d0_x, colour, rows_m1, a0_dst, a1_src, A_blit_mode);  /* dst = A0, not A2 */

    /* movem rename: D0 ← D3(base_col), D4 ← D5(rows seed); A0 ← sprite-top (restored A2); A1 -= 0xa0 */
    struct obj_hi_out out = { base_col, d5_rows, dst_top,
                              (uint32_t)(a1_src - sign_ext16(OBJD_WIDTH)) };
    return out;
}

/* 0x1465c: colour-preserving double draw. */
static void draw_obj_handler_dbl(uint8_t *img, uint16_t d0_x, uint16_t colour, uint16_t width,
                                 uint16_t rows_seed, uint16_t voff, uint32_t a0_dst, uint32_t a1_src,
                                 uint32_t rec_cursor) {
    struct obj_hi_out r = draw_obj_sprite_hi(img, d0_x, colour, width, rows_seed, voff,
                                             a0_dst, a1_src, rec_cursor);      /* mode 8 pass */
    draw_obj_blit_tail(img, r.d0_x, colour, r.d4_rows, r.a0_dst, r.a1_src);    /* mode 0xa8, colour restored */
}

/* 0x14664: dst from A6, src adjusted by a per-parity record word, single tail blit (mode 0xa8). */
static void draw_obj_handler_lo(uint8_t *img, uint16_t d0_x, uint16_t colour, uint16_t rows_m1,
                                uint32_t a1_src, uint32_t rec_cursor /* = rec+0xa */, uint32_t a6_base) {
    uint32_t a0_dst = (uint32_t)(a6_base + sign_ext16(OBJH_BAND_LO));          /* a6 + 0x3ac0 */
    uint16_t parity = (uint16_t)(2 & rd16(img + view_parity_flag));            /* 0 or 2 */
    a1_src = (uint32_t)(a1_src + sign_ext16(rd16(img + rec_cursor + 2 + parity)));
    draw_obj_blit_tail(img, d0_x, colour, rows_m1, a0_dst, a1_src);
}
```

Notes:
- `voff` (D7) is a *caller-supplied* word here; the caller already applied it to A0, and 0x14620
  re-applies it (`adda.w d7,a0` at 0x14626). Pass through unchanged.
- The mulu `width * rows_byte` result is used only via `suba.w` (low 16 bits) — the `uint16_t height`
  captures exactly the bits that matter.
- The tail's blit `rts` returns to the *handler's* caller (dispatch site), not into the handler — so in
  C the handler simply returns after `draw_obj_blit_tail`.

---

## 5. movem save/restore register lists

| site | encoding | list | net |
|---|---|---|---|
| 0x14640 push | `48a7 1400` | `d3/d5` → -(a7); mem [D3][D5] | 2 words |
| 0x1463e push | `2f0a` | `a2` (long) → -(a7); mem [A2long] above D5 | 2 words |
| 0x14650 pop | `4c9f 0011` | `d0/d4` ← (a7)+; **D0←D3-slot, D4←D5-slot** | -2 words |
| 0x14654 pop | `205f` | `a0` (long) ← (a7)+ | -2 words |

Stack at the `bsr` (low→high): `[a7]=D3.w, [a7+2]=D5.w, [a7+4]=A2(long)`. Push {D3,D5,A2long}=4 words;
pop {D0,D4,A0long}=4 words → balanced. The D3→D0 / D5→D4 rename is intentional and load-bearing.

`draw_object_list` (caller) saves `movem.w d2/d3/d4/d6` + `movem.l a0/a3` around the `jsr`, and pops
them back — so the handler may freely clobber d0/d1/d5/d7 and a1/a2 (and a0/a3, restored by the caller).

---

## 6. 16-bit-wrap spots

- 0x14624/26/28: `suba.w`/`adda.w`/`add.w` — all word ops; sign-extend the word before applying to the
  32-bit A-reg (`sign_ext16`), add mod 2^16 for the D-reg (`base_col`).
- 0x14632 `move.b` writes only D4's low byte (`rows_byte` 0..0xff); blit reads `(int16_t)D4`.
- 0x1463a `mulu.w` product is 32-bit but consumed only through `suba.w` (low 16 bits) — mirror as
  `uint16_t height = width * rows_byte`.
- 0x14656 `suba.w #0xa0,a1` and 0x14672 `adda.w 2(a2,d2),a1` — sign-extended word adjustments to A1.
- 0x1466c `and.w` — genuine 16-bit AND on D2.

---

## 7. What a differential test must stage

Each entry is a register-glue routine like `g_blit_objshift`; use `differential(entry, regs, glue,
poison=True)` with `regs["_pokes"] = {addr: bytes}`. `A_color_pairs` @ 0x15afa is real image data the
leaf reads (NOT staged). Stage a noise dst band, a noise src arena, and the record bytes; poison every
register the chosen entry does not define.

Shared globals to poke:
- `A_view_flags` (0x18c56): the view selector word (0/2/4/6) — drives `view>>1` and the rows byte index
  (0x14620) and, via the caller, the parity flag semantics.
- `A_blit_mode` (0x18cb0): written by the code (8 or 0xa8) before the leaf reads it — stage any value,
  it is overwritten; but the region must be writable.
- `view_parity_flag` (0x18c60): only 0x14664 reads it; low bit survives `&2`.

**Entry 0x14620** — presets: `d0`=x accum, `d1`=colour (0..0xf), `d2`=0xa0, `d4`=rows seed (small,
0..0x20), `d7`=voff (a small multiple of 0xa0), `a0`=dst band base (160-aligned, with headroom below for
`suba` of up to (rows_byte+1)*0xa0 + xoff), `a1`=src base, `a2`=rec+0xa. `_pokes`:
- word at rec+8 (int16 x offset, e.g. ±0x40) — the `move.w -(a2),d3` target,
- 4 bytes at rec+0xc..rec+0xf (the per-view rows byte; only rec+0xc+view is read),
- `A_view_flags`, dst noise band spanning `[a0 - (rows_byte+1)*0xa0 - xoff .. a0]`, src noise band.

**Entry 0x14664** — presets: `d0`,`d1`,`d4`(rows_m1),`a1`,`a2`=rec+0xa, `a6`=buffer base (so
a0=a6+0x3ac0). `_pokes`: `view_parity_flag`, the record word at rec+0xc/rec+0xe (selected by parity),
dst noise band around a6+0x3ac0, src noise band. Sweep `view_parity_flag` low bit over {0,1}.

**Entry 0x1465c** — same presets as 0x14620 (colour must be a definite value; it is preserved for the
2nd pass). Two blits fire (mode 8 at the 0x14620 sprite-top, mode 0xa8 reusing the renamed
a0/d0/d4). Stage the dst noise band wide enough for both passes; diff the whole image, poison=True.

---

## 8. Constants to name (no magic numbers)

| value | meaning | name |
|---|---|---|
| 0x18cb0 | blit mode/stride word (leaf reads via A3, `suba.w (a3),a1` per row) | `A_blit_mode` |
| 8 | mode for the 0x14620 first pass | `OBJH_MODE_MAIN` |
| 0xa8 | mode for the 0x14676 tail pass | `OBJH_MODE_TAIL` |
| 0xa0 | scanline stride / band width (= caller D2) | `OBJD_WIDTH` (existing) |
| 0x3ac0 | fixed dst-band offset from A6 (0x14664) | `OBJH_BAND_LO` |
| 0x18c60 | per-view parity flag word (`&2`) | `view_parity_flag` |
| 0x8 | rec+8 x-offset field re-read by `-(a2)` | `REC_XOFF` |
| 0xc | rec+0xc rows-byte table / src-offset base | `REC_ROWS_TBL` / `REC_SRC_OFF` |
| 0x8a0 / 0xd0 | buf_a slot-table origin / per-type slot stride | (caller — pin only) |

---

## 9. Summary table

| entry | role | dst/src override | mode word | leaf call | leaves |
|---|---|---|---|---|---|
| 0x14620 | shared helper: geometry from record+view_flags, first blit | A0 from caller-A0 (−xoff,+voff,−(rows+1)*0xa0); A1−=0xa0 | 8 | `bsr`, returns | D0=word@rec8+d0, D4=rows seed (via D5), A0=sprite-top, A1=src−0xa0 |
| 0x1465c | handler: save D1, run 0x14620, restore D1, tail | reuses 0x14620 outputs | 8 then 0xa8 | 0x14620 bsr + tail fall-through | returns to dispatcher via leaf rts |
| 0x14664 | handler: A0=A6+0x3ac0, A1+=per-parity word, tail | A0=A6+0x3ac0; A1+=word@2(a2,parity) | 0xa8 | tail fall-through | returns to dispatcher via leaf rts |
