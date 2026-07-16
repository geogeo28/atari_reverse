# SPEC — `blit_objshift2`: two-word-mask sub-pixel masked sprite blitter @ Ghidra 0x13ed6

**File offset 0x3ed6 = Ghidra 0x13ed6** (load base 0x10000). Addresses below are given as
Ghidra addresses; the aligned disassembly prints **file offsets** (`0x3exx`) = Ghidra − 0x10000.

This is a **PURE LEAF** (all branches internal, exits only via `rts`; no `bsr`/`jsr` out). It is a
4-plane Atari ST masked sprite blitter with sub-pixel (fine-x) horizontal shifting.

It is **DISTINCT** from the already-verified `g_blit_objshift` @ 0x14680 (`recreate/src/blit.c`):
- Its transparency mask is built from **exactly two source words** — `~( (a1) | 2(a1) )` — never
  from three words, and it **never loads `color_pairs`**.
- The pixel copy is a **plain shifted OR** (no colour indexing / no colour fill).
- Proposed name: **`blit_objshift2`** (two-word-mask, plain shifted copy).

Reconstructed purely from disassembly (Ghidra produced no decompilation for this block). Every
address, constant, cell count and rewind delta below was re-read from the bytes.

---

## 1. In-register contract (for the `proto` storage)

Confirmed from the glue wrapper at **0x13e8e** and its own caller **0x13e68**:

```
0x13e68  movea.l a6,a0            ; a0 = a6 (draw-buffer base)
0x13e6a  movea.l #$71ca,a2        ; a2 = reloc'd scanline-offset table
0x13e70  adda.w  $8c56.l,a2       ;   + per-frame table selector
0x13e76  adda.w  0(a2,d4.w),a0    ; a0 += word@table[d4]  -> a0 = dst scanline base
0x13e7a  rts

; a typical entry (there are 7, one per row-height) e.g. 0x13ed2:
0x13ed2  bsr.s   0x13e68          ; a0 = dst scanline base
0x13ed4  moveq   #$4,d4           ; d4 = rows-1   (0x4/0x6/0x8/0xa/0xc/0xe/0x12 across the 7 entries)
;   ... falls straight into 0x13ed6 for the moveq#4 entry; others reach the glue:

0x13e8e  movem.l #$00c0,-(a7)     ; save a0,a1   (predec mask 0x00c0 = bits 6,7 = a1,a0)  [LONG]
0x13e92  movem.w #$9800,-(a7)     ; save d0,d3,d4 (predec mask 0x9800 = bits 15,12,11)     [WORD]
0x13e96  bsr.s   0x13ed6          ; <<< THE BLITTER
0x13e98  movem.w (a7)+,#$0019     ; restore d0,d3,d4 (postinc mask 0x0019 = bits 0,3,4)
0x13e9c  movem.l (a7)+,#$0300     ; restore a0,a1   (postinc mask 0x0300 = bits 8,9)
0x13ea0  addi.w  #$30,d0          ; next sub-cell: x += 0x30
0x13ea4  adda.w  #$c,a1           ; next sprite:  a1 += 0xC
0x13ea8  dbf     d3,0x13e8e       ; d3 = outer column-group count (owned by the GLUE, not the leaf)
```

**Inputs consumed by 0x13ed6:**

| reg | type | role |
|-----|------|------|
| **a0** | ptr (long) | dst scanline base into the 4-plane interleaved draw buffer (byte-x added at entry) |
| **a1** | ptr (long) | src sprite word stream; consecutive big-endian 16-bit plane words, consumed forward with `(a1)+` |
| **d0** | int16 | screen x (signed). Low nibble = fine_x; the rest picks the byte column and the family/case |
| **d4** | int16 | **rows-1** (`dbf d4` counts d4+1 rows). Caller-supplied ∈ {4,6,8,10,12,14,18} |

d3 belongs to the glue's outer loop — it is **not** an input to the leaf (the leaf overwrites d3/d5
internally). a2 is internal (= a0+8).

**Clobbered:** d0,d1,d2,d3,d5,d6,d7 and a1,a2 are freely trashed. d4 is decremented to −1 by the
internal `dbf`. The caller restores a0,a1,d0,d3,d4 from the stack, so the leaf returns nothing in
registers; its entire effect is the memory writes at a0/a2.

**Proposed `proto` (explicit storage):**
```
proto 0x13ed6 blit_objshift2 image@- dst@a0:4 src@a1:4 x@d0:2 rows_m1@d4:2
```
(`image` is the C-model buffer base for the `wr32`/`rd32` helpers; `dst`/`src` are the a0/a1 byte
offsets into it. The register glue `g_blit_objshift2(image, dst, src, x, rows_m1)` mirrors this.)

---

## 2. Entry setup (0x13ed6–0x13ef0)

```
0x13ed6  moveq  #$f,d7          ; d7 = 0x0F
0x13ed8  and.w  d0,d7           ; d7 = fine_x = x & 0x0F                 (0..15) — the RIGHT-shift count
0x13eda  moveq  #$10,d6         ; d6 = 16
0x13edc  sub.w  d7,d6           ; d6 = shift = 16 - fine_x               (1..16) — the LEFT-shift count
0x13ede  asr.w  #1,d0           ; d0 = (int16)x >> 1     (arithmetic; x may be negative)
0x13ee0  andi.w #$fff8,d0       ; d0 = aligned_col = ((int16)x>>1) & 0xFFF8   (signed multiple of 8)
0x13ee4  adda.w d0,a0           ; a0 += sign_ext16(aligned_col)  -> a0 = aligned dst column base
0x13ee6  bmi.w  0x14104         ; aligned_col < 0            -> LEFT family
0x13eea  subi.w #$88,d0         ; d0 = aligned_col - 0x88
0x13eee  bpl.w  0x1429c         ; aligned_col - 0x88 >= 0    -> RIGHT/WIDE family
;   else fall through to BASE @ 0x13ef2   (0 <= aligned_col < 0x88)
```

Load-bearing facts:
- **`fine_x = (x & 0x0F)` is computed BEFORE the `asr.w #1`.** d7 = fine_x survives to the RIGHT
  edge cells (used as an `lsr.w d7` count). d6 = 16 − fine_x is used by BASE/LEFT (`rol.l d6` /
  `lsl.l d6` / `lsl.w d6`).
- `asr.w #1` is **arithmetic** (x may be negative); `andi.w #0xFFF8` floors to an 8-byte column
  stride. So `aligned_col = ((int16_t)x >> 1) & 0xFFF8`, a signed multiple of 8.
- The **signed** aligned_col (post-add into a0) drives dispatch — see §3.

---

## 3. Width dispatch (aligned_col → case)

`aligned_col = ((int16_t)x >> 1) & 0xFFF8`. It is always a multiple of 8.

### 3a. LEFT ladder @ 0x14104 (entered when `aligned_col < 0`)
a0 already points **left** of the buffer; the ladder walks a0/a1 forward (skipping fully-clipped
columns) until the first partially-visible column, then branches to a case:
```
0x14104  addq.w #8,d0 ; bpl.w 0x141d8   ; aligned_col == -8   -> CASE_L2C  (edge + 2 straddle)
0x1410a  addq.l #4,a1 ; addq.l #8,a0    ;   skip one fully-clipped column (src +4, dst +8)
0x1410e  addq.w #8,d0 ; bpl.s 0x14158   ; aligned_col == -16  -> CASE_L1C  (edge + 1 straddle)
0x14112  addq.l #4,a1 ; addq.l #8,a0
0x14116  addq.w #8,d0 ; bpl.s 0x1411c   ; aligned_col == -24  -> CASE_L0C  (edge only)
0x1411a  rts                            ; aligned_col <= -32  -> fully off-screen, NO DRAW
```

### 3b. RIGHT/WIDE ladder @ 0x1429c (entered when `aligned_col >= 0x88`)
On entry d0 = aligned_col − 0x88 (≥0).
```
0x1429c  subq.w #8,d0 ; bmi.w 0x14368   ; aligned_col == 0x88 -> CASE_W2 (2 straddle + edge)
0x142a2  subq.w #8,d0 ; bmi.s 0x142e8   ; aligned_col == 0x90 -> CASE_W1 (1 straddle + edge)
0x142a6  subq.w #8,d0 ; bmi.s 0x142ac   ; aligned_col == 0x98 -> CASE_W0 (edge only)
0x142aa  rts                            ; aligned_col >= 0xA0 -> off right edge, NO DRAW
```
(0x142a2/0x142a6 are alternate entries used by the *interleaved sibling handlers* 0x13fd4/0x1408e,
which subtract 0x90/0x98 at their own entries; irrelevant to the 0x13ed6 entry, which always
enters the ladder at 0x1429c.)

### 3c. Full case table (0xA0 = 160-byte ST low-res scanline; 0x88 = 17 columns)

| aligned_col | family | case entry | body | rts |
|---|---|---|---|---|
| `<= -32` | LEFT | 0x1411a | (none — off left) | 0x1411a |
| `-24` | LEFT | 0x1411c | 1 edge cell | 0x14156 |
| `-16` | LEFT | 0x14158 | 1 edge + 1 straddle | 0x141d6 |
| `-8` | LEFT | 0x141d8 | 1 edge + 2 straddle | 0x1429a |
| `0x00 .. 0x80` | BASE | 0x13ef2 | 3 straddle | 0x13fd2 |
| `0x88` | WIDE | 0x14368 | 2 straddle + 1 edge | 0x1442a |
| `0x90` | WIDE | 0x142e8 | 1 straddle + 1 edge | 0x14366 |
| `0x98` | WIDE | 0x142ac | 1 edge cell | 0x142e6 |
| `>= 0xA0` | RIGHT | 0x142aa | (none — off right) | 0x142aa |

**Every listed case is reachable.** There are **no dead deeper unrolled cases** in either family
(unlike `g_blit_objshift`, whose s=1..3 straddle depths were dead). BASE covers all
`0x00 <= aligned_col <= 0x80`.

Exact source-x ranges (16-bit signed), since aligned_col = `((int16)x>>1) & 0xFFF8`:
- LEFT off-screen: `x <= -49`
- L0C (−24): `x ∈ [−48, −33]`
- L1C (−16): `x ∈ [−32, −17]`
- L2C (−8):  `x ∈ [−16, −1]`
- BASE (0..0x80): `x ∈ [0, 0x10D]` (i.e. `(x>>1)&~7 <= 0x80`)
- W2 (0x88): next 16-px band, W1 (0x90), W0 (0x98); RIGHT off-screen at `(x>>1)&~7 >= 0xA0`.

`fine_x = x & 0x0F` still selects the intra-cell shift within every case; it never changes which
case is chosen.

---

## 4. The two reusable per-cell kernels

Every case is built from just two cell primitives. Both operate on two column pointers:
**a0 = col0 (left)** and **a2 = col1 (right) = a0 + 8**, set once per case entry via
`movea.l a0,a2; addq.l #8,a2`.

Both kernels build a transparency "show" mask from **`~( w0 | w1 )`** of two source words and use
it to punch a hole in the destination, then OR the shifted plane data in. **No `color_pairs`.**

### 4a. STRADDLE cell (S-cell) — writes BOTH columns; 32-bit `rol`/`lsl` by `shift=16-fine_x`

Reference bytes at BASE 0x13efc–0x13f3e (identical copies at 0x13f40, 0x13f84, and inside every
LEFT/WIDE case). Consumes **2 source words** (via two `(a1)+`, a1 += 4), advances **a0 += 8** and
**a2 += 8**.

```
0x13efc  moveq #$ff,d1        ; d1 = 0xFFFFFFFF          (moveq sign-extends 0xFF -> all ones)
0x13efe  move.w (a1),d1       ; d1 = 0xFFFF_w0           (a1 NOT advanced)
0x13f00  or.w   2(a1),d1      ; d1 = 0xFFFF_(w0|w1)      (word@a1+2; a1 NOT advanced)
0x13f04  not.w  d1            ; d1 = 0xFFFF_~(w0|w1)     -> HIGH word stays 0xFFFF (see §6!)
0x13f06  rol.l  d6,d1         ; d1 = rotl32(d1, shift)   -> straddle the mask across two columns
0x13f08  move.w d1,d2         ; d2.w = d1.lo
0x13f0a  swap   d2            ; d2.hi = d1.lo
0x13f0c  move.w d1,d2         ; d2 = (d1.lo << 16) | d1.lo  = dup16(d1.lo)   -> col1 AND-mask
0x13f0e  move.l d1,d0         ; d0 = full rotated mask
0x13f10  swap   d0            ; d0.lo = d1.hi
0x13f12  move.w d0,d1         ; d1.lo = d1.hi ; d1.hi UNCHANGED (= rotated mask's original high word)
0x13f14  and.l  d1,(a0)       ; (a0) &= d1     -> col0 masked  (32-bit; see §6 for d1.hi content)
0x13f16  and.l  d2,(a2)       ; (a2) &= d2     -> col1 masked

; --- plane OR: two words, shifted 32-bit, low half -> col1, high half -> col0 ---
0x13f18  moveq #$0,d0
0x13f1a  move.w (a1)+,d0      ; d0 = w0 ; a1 += 2
0x13f1c  lsl.l  d6,d0         ; d0 = (u32)w0 << shift
0x13f1e  or.w   d0,(a2)+      ; (a2).w |= d0.lo ; a2 += 2
0x13f20  swap   d0
0x13f22  or.w   d0,(a0)+      ; (a0).w |= d0.hi ; a0 += 2
0x13f24  moveq #$0,d0
0x13f26  move.w (a1)+,d0      ; d0 = w1 ; a1 += 2
0x13f28  lsl.l  d6,d0
0x13f2a  or.w   d0,(a2)+      ; a2 += 2
0x13f2c  swap   d0
0x13f2e  or.w   d0,(a0)+      ; a0 += 2

; --- trailing longword "opaque fill outside the show mask" for each column ---
0x13f30  move.l d1,d0
0x13f32  not.l  d0            ; d0 = ~d1
0x13f34  and.l  d1,(a0)       ; (a0) &= d1
0x13f36  or.l   d0,(a0)+      ; (a0) |= ~d1 ; a0 += 4   -> col0 long = (dst & d1) | ~d1
0x13f38  move.l d2,d0
0x13f3a  not.l  d0            ; d0 = ~d2
0x13f3c  and.l  d2,(a2)       ; (a2) &= d2
0x13f3e  or.l   d0,(a2)+      ; (a2) |= ~d2 ; a2 += 4   -> col1 long = (dst & d2) | ~d2
```

Per S-cell: **a1 += 4** (two `(a1)+`; the mask reads at (a1)/(a1+2) do NOT advance), **a0 += 8**
(two `or.w (a0)+` = +4, one `or.l (a0)+` = +4), **a2 += 8** likewise.

**Byte-exact C for the mask stage — mirror the 68k register file literally (do NOT "optimise" it):**
```c
uint32_t d1, d2, d0;                                   /* semantic names below in blit.c */
d1 = 0xFFFFFFFFu;                                      /* moveq #$ff,d1  -> all ones     */
d1 = (d1 & 0xFFFF0000u) | w0;                          /* move.w (a1),d1                 */
d1 = (d1 & 0xFFFF0000u) | (uint16_t)(d1 | w1);         /* or.w 2(a1),d1  (word op)       */
d1 = (d1 & 0xFFFF0000u) | (uint16_t)(~d1);             /* not.w d1  -> hi word stays 0xFFFF */
d1 = rotl32(d1, shift);                                /* rol.l d6,d1                    */
d2 = dup16((uint16_t)d1);                              /* move.w;swap;move.w -> dup16(lo)*/
d0 = d1; d0 = (d0 >> 16) | (d0 << 16);                 /* move.l d1,d0 ; swap d0         */
d1 = (d1 & 0xFFFF0000u) | (uint16_t)d0;                /* move.w d0,d1 -> d1.lo = old hi */
wr32(dst_col0, rd32(dst_col0) & d1);                   /* and.l d1,(a0)                  */
wr32(dst_col1, rd32(dst_col1) & d2);                   /* and.l d2,(a2)                  */
```
`rotl32` already exists in `recreate/src/blit.c` (identical semantics, count 1..16 → reuse it).
`dup16` is in `recreate/include/draw.h`.

### 4b. LEFT EDGE cell (LE-cell) — writes col1 (a2) ONLY; 16-bit `lsl.w` by `shift=16-fine_x`

Reference bytes at 0x1411c–0x1414a (also 0x14162, 0x141d8). Consumes **2 source words**
(a1 += 4), writes only **col1 (a2) += 8**, then bumps a0 past the discarded left column with
`addq.l #8,a0`.
```
0x1411c  move.l (a1),d0       ; d0 = (w0<<16)|w1        (a1 NOT advanced)
0x14128  or.w   (a1)+,d0      ; d0.lo |= w0 ; a1 += 2   -> d0.lo = (w1 | w0)
0x1412a  lsl.w  d6,d0         ; d0.lo <<= shift   (WORD shift)
0x1412c  not.w  d0            ; d0.lo = ~...  = mask16
0x1412e  move.w d0,d2
0x14130  swap   d2
0x14132  move.w d0,d2         ; d2 = dup16(mask16)      -> col1 AND-mask
0x14134  and.l  d2,(a2)       ; (a2) &= d2
0x14136  swap   d0            ; d0.lo = the pre-shift high half (w0<<16 >> 16 -> old w0)
0x14138  lsl.w  d6,d0         ; d0.lo <<= shift
0x1413a  or.w   d0,(a2)+      ; (a2) |= ; a2 += 2
0x1413c  move.w (a1)+,d0      ; d0 = next word ; a1 += 2
0x1413e  lsl.w  d6,d0
0x14140  or.w   d0,(a2)+      ; a2 += 2
0x14142  move.l d2,d0
0x14144  not.l  d0
0x14146  and.l  d2,(a2)       ; (a2) &= d2
0x14148  or.l   d0,(a2)+      ; (a2) |= ~d2 ; a2 += 4
0x1414a  addq.l #8,a0         ; a0 += 8   (skip the discarded off-screen left column)
```
Per LE-cell: **a1 += 4, a2 += 8, a0 += 8**.

### 4c. RIGHT EDGE cell (RE-cell) — writes col0 (a0) ONLY; 16-bit `lsr.w` by `fine_x`

Reference bytes at 0x142b6–0x142d8 (also 0x14336, 0x143fa). Consumes **2 source words**
(a1 += 4), writes only **col0 (a0) += 8**, then bumps a2 with `addq.l #8,a2`.
```
0x142b6  move.l (a1),d0       ; d0 = (w0<<16)|w1
0x142b8  or.w   (a1)+,d0      ; d0.lo |= w0 ; a1 += 2
0x142ba  lsr.w  d7,d0         ; d0.lo >>= fine_x   (WORD right shift by d7)
0x142bc  not.w  d0            ; mask16
0x142be  move.w d0,d1
0x142c0  swap   d1
0x142c2  move.w d0,d1         ; d1 = dup16(mask16)     -> col0 AND-mask
0x142c4  and.l  d1,(a0)       ; (a0) &= d1
0x142c6  swap   d0            ; d0.lo = old w0
0x142c8  lsr.w  d7,d0
0x142ca  or.w   d0,(a0)+      ; a0 += 2
0x142cc  move.w (a1)+,d0      ; a1 += 2
0x142ce  lsr.w  d7,d0
0x142d0  or.w   d0,(a0)+      ; a0 += 2
0x142d2  move.l d1,d0
0x142d4  not.l  d0
0x142d6  and.l  d1,(a0)       ; (a0) &= d1
0x142d8  or.l   d0,(a0)+      ; (a0) |= ~d1 ; a0 += 4
0x142da  addq.l #8,a2         ; a2 += 8   (bookkeeping so a2's rewind lands correctly; see §5)
```
Per RE-cell: **a1 += 4, a0 += 8, a2 += 8**.

Note the shift-count asymmetry: **LE uses `lsl.w d6` (=16−fine_x)**, **RE uses `lsr.w d7`
(=fine_x)**. Both edge cells use **word** shifts (no straddle spill); the S-cell uses **long**
shifts. All three build the mask from `~(w0|w1)`.

---

## 5. Case bodies (cell sequence + rewind deltas)

At each case entry: `a2 = a0 + 8`, then `move.w #d3,d3`, `moveq #d5,d5` set the per-row rewind
constants. After the row's cells, the tail rewinds: `suba.w d3,a0; suba.w d3,a2; suba.w d5,a1;
dbf d4,<loop-top>`. **Row count = d4 + 1.** a2 is maintained by its own `suba.w d3,a2` each row
(it is NOT recomputed as a0+8 per row) and stays exactly 8 ahead of a0 by the invariant that every
cell advances a0 and a2 by +8 (the edge cells make one column advance via a write and the other via
the trailing `addq.l #8`).

**All cases share the same geometry: net a0 movement per row = −0xA0 (one scanline up-screen),
net a1 movement per row = −0x50 (sprite src stride 0x50 bytes).** The constants satisfy:
```
d3 = 0xA0 + 8 * cells_per_row        ; net a0 = 8*cells - d3 = -0xA0
d5 = 0x50 + 4 * cells_per_row        ; net a1 = 4*cells - d5 = -0x50
```

| case | entry | loop-top | cells / row | src bytes / row | dst cols / row | d3 (dst rewind) | d5 (src rewind) | rts |
|---|---|---|---|---|---|---|---|---|
| **BASE** | 0x13ef2 | 0x13efc | 3 S | 12 | 6 | 0xB8 | 0x5C | 0x13fd2 |
| **L0C** | 0x1411c | 0x14126 | 1 LE | 4 | 1 (col1) | 0xA8 | 0x54 | 0x14156 |
| **L1C** | 0x14158 | 0x14162 | 1 LE + 1 S | 8 | 3 | 0xB0 | 0x58 | 0x141d6 |
| **L2C** | 0x141d8 | 0x141e2 | 1 LE + 2 S | 12 | 5 | 0xB8 | 0x5C | 0x1429a |
| **W0** | 0x142ac | 0x142b6 | 1 RE | 4 | 1 (col0) | 0xA8 | 0x54 | 0x142e6 |
| **W1** | 0x142e8 | 0x142f2 | 1 S + 1 RE | 8 | 3 | 0xB0 | 0x58 | 0x14366 |
| **W2** | 0x14368 | 0x14372 | 2 S + 1 RE | 12 | 4 | 0xB8 | 0x5C | 0x1442a |

Verification `net a0 = 8*cells − d3 = −0xA0`: BASE 24−184=−160 ✓; L0C 8−168=−160 ✓;
L1C 16−176=−160 ✓; L2C 24−184=−160 ✓; W0 8−168=−160 ✓; W1 16−176=−160 ✓; W2 24−184=−160 ✓.

Notes per family:
- **LEFT** cases always lead with the LE-cell (clips the off-screen left half, writes only col1),
  then 0..2 full S-cells. The `dbf` loop-top is the *first cell* of each body, so the ladder's
  `addq.l #8,a0` / `addq.l #4,a1` pre-advances (§3a) apply once, before the loop.
- **WIDE** cases are S-cells first, then a trailing RE-cell (clips the off-screen right half, writes
  only col0). The RE-cell's `addq.l #8,a2` keeps a2 in lockstep so the shared `suba.w d3,a2` rewind
  lands correctly.
- **BASE** is 3 pure S-cells — the common on-screen path and the reusable kernel driver.

### Collapsing the unroll into a parameterized C loop
The C can express the whole blitter as:
```
per case (base, left, wide):
    a2 = a0 + 8
    for (row = 0; row <= rows_m1; row++) {          // dbf d4
        // LEFT: 1 LE-cell then n_straddle S-cells
        // WIDE: n_straddle S-cells then 1 RE-cell
        // BASE: 3 S-cells (no edge)
        a0 -= d3; a2 -= d3; a1 -= d5;
    }
```
with `(n_straddle, edge_kind, d3, d5)` chosen from the dispatch:
- BASE: n_straddle=3, edge=none, d3=0xB8, d5=0x5C.
- LEFT: edge=LE, n_straddle ∈ {0 (L0C), 1 (L1C), 2 (L2C)}; d3=0xA8+8·(n+1)? — use the literal
  table values (0xA8/0xB0/0xB8, 0x54/0x58/0x5C) rather than a derived formula, to stay byte-exact.
- WIDE: edge=RE, n_straddle ∈ {0 (W0), 1 (W1), 2 (W2)}; d3/d5 from the table.
- Off-screen (`aligned_col <= -32` or `>= 0xA0`): return immediately (empty rts).

The LEFT-ladder src/dst pre-skips (`addq.l #4,a1; addq.l #8,a0`, applied `(2 − n_straddle)` times
for the −16/−24 cases before reaching the body) must be reproduced when modelling a0/a1 at body
entry. Equivalently: after `a0 += sign_ext16(aligned_col)`, the LEFT body starts with
`a0 += 8*(clipped_cols)` and `a1 += 4*(clipped_cols)` where `clipped_cols = (-aligned_col)/8 - 1 -
n_straddle`… — simplest correct model is to literally run the ladder (add 8 to a signed counter
starting at aligned_col; each pre-`bpl` failure does a0+=8,a1+=4) exactly as in §3a.

**No dead cases.** Every entry in the §3c table is statically reachable and none is a
never-taken deeper unroll.

---

## 6. 16-bit / wrap-sensitive spots (get these exactly right or the diff fails)

1. **`moveq #$ff,d1` sets d1 = 0xFFFFFFFF, NOT 0x000000FF.** moveq always sign-extends its 8-bit
   immediate to 32 bits; 0xFF → 0xFFFFFFFF. Therefore after `move.w/or.w/not.w` the **high word of
   d1 remains 0xFFFF** going into `rol.l d6,d1`. (Analysis 1 wrongly claimed the high word was
   0x0000; Analysis 3 is correct.) The C must start the mask register at `0xFFFFFFFF`.

2. **In the S-cell, `and.l d1,(a0)` at 0x13f14 uses d1 AFTER the `move.w d0,d1` at 0x13f12** —
   i.e. d1.lo = the rotated mask's high word, and **d1.hi is UNCHANGED from the `rol.l` result**
   (the rotated mask's *original* high 16 bits, since only `move.w` touched the low word). Mirror
   the register moves literally (see §4a C) rather than reasoning about which half masks what.
   Likewise `d2 = dup16(rotated_lo)` masks col1's full longword with the low-half mask replicated.

3. **Word vs long shifts:** S-cell uses `lsl.l d6` / `rol.l d6` (32-bit, straddling). LE-cell uses
   `lsl.w d6` (16-bit). RE-cell uses `lsr.w d7` (16-bit). Model each with the exact width
   (`uint32_t` for `.l`, `uint16_t` for `.w`). Shift counts are 1..16 → no 68000 mod-64 wrap, but
   `lsl.l #16` produces `w << 16` (word fully into the high half; low half becomes 0) — matches
   fine_x==0 (pure column copy, no straddle bits in the low half).

4. **All memory `and.l`/`or.l` on `(a0)`/`(a2)` are 32-bit reads/writes** at the current pointer;
   the `or.w …,(a0)+` writes are 16-bit. Use `rd32/wr32` and `rd16/wr16` (big-endian) exactly per
   width so the interleaved-plane bytes match.

5. **`asr.w #1,d0` is arithmetic** on the signed 16-bit x (sign-preserving); do it as
   `(int16_t)x >> 1`, then `& 0xFFF8` on the 16-bit result. The dispatch compares the **signed**
   aligned_col.

6. **RE-cell's trailing `addq.l #8,a2` and the S-cell's dual-column advances** are required for
   a2 to end each row at exactly a0+8 so the shared `suba.w d3,a2` rewind is correct. If the
   differential test checks final a2 it must match; even if it doesn't, emit the advance to keep
   the register model faithful.

7. **`and.w`/`or.w` in this blitter are all genuine data/memory ops** (operands are Dn or
   `(a0)`/`(a2)`, never An) — none is a misprinted `mulu.w`/`divu.w`. Confirmed by re-reading the
   raw bytes (e.g. `82690002` = `or.w 2(a1),d1`; `8059` = `or.w (a1)+,d0`).

---

## 7. Named constants to introduce (no magic numbers)

```
OBJSH2_FINE_MASK        0x000f   /* x & 0xF  -> fine_x                        */
OBJSH2_SHIFT_BASE       16       /* shift = 16 - fine_x  (d6)                 */
OBJSH2_COL_ALIGN        0xfff8   /* (x>>1) & ~7  -> aligned_col               */
OBJSH2_RIGHT_BOUND      0x88     /* subi.w #$88 dispatch threshold (17 cols)  */
OBJSH2_COL_BYTES        8        /* one 4-plane column = 8 bytes (addq #8)    */
OBJSH2_SCANLINE_BYTES   0xa0     /* net a0 rewind/row = -160 (ST low-res line)*/
OBJSH2_SRC_STRIDE       0x50     /* net a1 rewind/row = -80                   */
OBJSH2_MASK_INIT        0xffffffffu /* moveq #$ff,d1 -> all ones              */
/* per-case rewind constants (literal, keep byte-exact): */
OBJSH2_REWIND3_DST 0xb8  OBJSH2_REWIND3_SRC 0x5c   /* 3 cells (BASE, L2C, W2) */
OBJSH2_REWIND2_DST 0xb0  OBJSH2_REWIND2_SRC 0x58   /* 2 cells (L1C, W1)       */
OBJSH2_REWIND1_DST 0xa8  OBJSH2_REWIND1_SRC 0x54   /* 1 cell  (L0C, W0)       */
```

---

## 8. Address cross-reference

| Ghidra | file | what |
|---|---|---|
| 0x13ed6 | 0x3ed6 | entry / setup |
| 0x13ee6 | 0x3ee6 | `bmi 0x14104` → LEFT |
| 0x13eee | 0x3eee | `bpl 0x1429c` → RIGHT/WIDE |
| 0x13ef2 | 0x3ef2 | BASE body (3 S-cells) |
| 0x13fd2 | 0x3fd2 | BASE rts |
| 0x13fd4 / 0x1408e | 0x3fd4 / 0x408e | **sibling handlers — NOT this blitter, ignore** |
| 0x14104 | 0x4104 | LEFT ladder |
| 0x1411a | 0x411a | LEFT off-screen rts |
| 0x1411c | 0x411c | CASE_L0C (1 LE) |
| 0x14156 | 0x4156 | L0C rts |
| 0x14158 | 0x4158 | CASE_L1C (LE + 1 S) |
| 0x141d6 | 0x41d6 | L1C rts |
| 0x141d8 | 0x41d8 | CASE_L2C (LE + 2 S) |
| 0x1429a | 0x429a | L2C rts |
| 0x1429c | 0x429c | RIGHT/WIDE ladder |
| 0x142aa | 0x42aa | RIGHT off-screen rts |
| 0x142ac | 0x42ac | CASE_W0 (1 RE) |
| 0x142e6 | 0x42e6 | W0 rts |
| 0x142e8 | 0x42e8 | CASE_W1 (1 S + RE) |
| 0x14366 | 0x4366 | W1 rts |
| 0x14368 | 0x4368 | CASE_W2 (2 S + RE) |
| 0x1442a | 0x442a | W2 rts — **blitter ends here** |
| 0x1442c | 0x442c | unrelated table-driven longword sprite-copy — NOT this blitter |

---

**Reference files:** `recreate/src/blit.c` (house style, `rotl32`, g_ glue + `proto` pattern),
`recreate/include/draw.h` (`dup16`, `blit_transp_cell`), `recreate/include/machine.h`
(`be16/be32/wr16/wr32/sign_ext16`), `recreate/test/test_blit_objshift.py` (differential staging
model: `differential(entry, regs, glue, poison=True)` with `regs` presetting d0/a0/a1/d4 and
`"_pokes"={addr:bytes}` for the src sprite words). The S-cell is the reusable primitive; LE/RE are
its two clipped-edge variants.
