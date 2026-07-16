# Sub-pixel 4-plane masked sprite blitter @ Ghidra 0x14680 — implementation spec

Authoritative, byte-exact spec synthesized and re-verified against the aligned disassembly
(`python3 ../../tools/prg_dis.py bin/BUGGYBOY.PRG --start $((0x4680+28)) --len $((0x5016-0x4680))`).

**Addressing note.** File offsets = Ghidra − 0x10000 (file 0x4680 = Ghidra 0x14680). This spec uses
**file offsets** throughout (matching the disassembler's printed `^00[0-9a-f]{4}:` column); add 0x10000
for the Ghidra/`names.txt` address. Function body = file 0x4680..0x5016, final `rts` @ 0x5014.

This is the innermost sprite engine: a **sub-pixel (fine-x shifted) 4-plane masked-transparency
blitter**. It is the fine-x cousin of `blit_transp_cell` (`include/draw.h`) and the `blit_obj_*`
family (`src/blit.c`): where those blit at byte/cell granularity, this one shifts each 16-pixel source
column left by `16 − fine_x` (or right by `fine_x` on a clipped right edge) so a sprite lands at an
arbitrary pixel x, straddling two 16-pixel destination columns.

**PURE LEAF** — no `bsr`/`jsr`; every branch is internal.

---

## 0. Resolved disagreements between the source analyses

Re-read the disassembly at each contested point; the resolutions are load-bearing:

1. **BASE is ONE cell per row, not five.** File 0x46b2..0x4728 is a *single* 4-plane straddle cell;
   `dbf d4,$46b2` loops it, rewind `0xa8`. (Analysis 3's "5 full cells" was wrong.)
2. **The width dispatch is entered mid-ladder, so only three bodies are reachable.** The entry
   `bmi.w $4756` lands on the *last* rung of the LEFT ladder (0x4756), and `bpl.w $4bbe` lands on
   the last rung of the RIGHT ladder (0x4bbe). Nothing branches to the earlier rungs (0x473a / 0x4bae),
   and the code above them is a preceding case's `rts`. Therefore from the real entry point:
   - `aligned_col < 0`  → **only** `aligned_col == -8` draws (LEFT case1); any `aligned_col ≤ -16` `rts`.
   - `aligned_col ≥ 0x98` → **only** `aligned_col == 0x98` draws (RIGHT case1); any `aligned_col ≥ 0xa0` `rts`.
   - `0 ≤ aligned_col ≤ 0x90` → BASE.
   The deeper LEFT/RIGHT cases (2/3/4) are fully decoded below for byte-exactness (a differential
   test that jumps directly into a body, or a mid-ladder caller elsewhere in the ROM, must still
   match) but are **dead on the documented entry path**. The C models the *reachable* dispatch and
   parameterizes all nine bodies from one loop.
3. **`move.l idx(a2),d3` is `d1.w`-indexed** (bytes `26321000` = `move.l (0,a2,d1.w),d3`,
   `2a321004` = `move.l (4,a2,d1.w),d5`): `d3 = color_pairs[colour*8]`, `d5 = color_pairs[colour*8+4]`.

---

## 1. IN-register contract (for a `proto` with explicit storage)

Decoded from entry setup 0x4680..0x46b2. Live inputs on entry:

| Reg | Storage | Role | Consumed as |
|-----|---------|------|-------------|
| `d0` | `x@D0` (int16) | **screen x** — signed pixel x of the sprite's left edge | fine-x nibble `x & 0xf`; then `asr.w #1` + `& 0xfff8` → column-aligned byte x; drives the whole dispatch |
| `d1` | `color@D1` (int16) | **colour index** (0..15 in low nibble) | `(d1 & 0xf) << 3` → byte offset into `color_pairs`; then dead / reused as scratch |
| `d4` | `rows_minus1@D4` (int16) | **rows − 1** | `dbf d4` counter in every body (rows = d4+1) |
| `a0` | `dst@A0` (ptr) | **dst scanline base** into the draw buffer | `adda.w d0` adds aligned x; per-column write pointer |
| `a1` | `src@A1` (ptr) | **src sprite stream** | `move.w (a1)+` reads 4 plane words A,B,C,D per cell (then re-read after `subq.l #8,a1`); rewound per row by `suba.w (a3),a1` |
| `a3` | `stride_ptr@A3` (ptr) | **→ per-row src-stride word** | `suba.w (a3),a1` rewinds a1 by that word each row |

Not inputs (derived/clobbered): `a2` (loaded with `color_pairs` then repurposed as the second-column
dst pointer `a0+8`), `d2,d3,d5,d6,d7`, and `d0` after decode.

The register-glue wrapper (matching `src/blit.c`'s `g_*` style) also takes the `image` base pointer
(for the absolute `color_pairs` read at 0x15afa and for reading/writing `a0`/`a1`/`a3` as
image-relative offsets via `be16`/`wr16`). No stack params. Void result (all callers treat it as void).

Suggested proto (explicit storage):
```
proto 0x14680 blit_obj_shift x@D0 color@D1 rows_minus1@D4 dst@A0 src@A1 stride_ptr@A3
```

---

## 2. Entry setup + color_pairs load (0x4680..0x46b2)

```
4680: movea.l #$5afa,a2      ; a2 = A_color_pairs = 0x15afa (RELOC-fixed image-absolute ptr)
4686: moveq   #$f,d7         ; d7 = 0x0000000f (nibble mask)
4688: and.w   d7,d1          ; d1 = colour_index & 0xf
468a: lsl.w   #3,d1          ; d1 = (colour_index & 0xf) << 3   (byte offset = colour*8)
468c: move.l  (0,a2,d1.w),d3 ; d3 = be32(color_pairs + colour*8 + 0)   fill pair 0 (planes 0,1)
4690: move.l  (4,a2,d1.w),d5 ; d5 = be32(color_pairs + colour*8 + 4)   fill pair 1 (planes 2,3)
4694: and.w   d0,d7          ; d7 = FINE_X = x & 0xf          (uses ORIGINAL x, before the asr/andi)
4696: moveq   #$10,d6
4698: sub.w   d7,d6          ; d6 = 16 - FINE_X               (LEFT sub-pixel shift count; range 1..16)
469a: asr.w   #1,d0          ; d0 = x >> 1  (ARITHMETIC — sign preserved)
469c: andi.w  #$fff8,d0      ; d0 = (x>>1) & 0xfff8 = aligned_col  (byte x, 8-byte cell granularity)
46a0: adda.w  d0,a0          ; a0 = dst_base + sext16(aligned_col)
46a2: bmi.w   $4756          ; aligned_col < 0  -> LEFT-CLIP dispatch (last rung)
46a6: subi.w  #$98,d0        ; d0 = aligned_col - 0x98
46aa: bpl.w   $4bbe          ; (aligned_col - 0x98) >= 0  -> RIGHT dispatch (last rung), d0 = R
46ae: movea.l a0,a2          ; else BASE: a2 = a0
46b0: addq.l  #8,a2          ; a2 = a0 + 8   (second 16px column of the straddle)
46b2: (fall into BASE row loop)
```

Byte-exact derived values:
- `FINE_X = x & 0xf` — the fractional 16-pixel position, from the **original** x (computed at 0x4694
  before the `asr`/`andi`). Compute it FIRST.
- `SHL = d6 = 16 − FINE_X` — left-shift count for `rol.l`/`lsl.l`/`lsl.w` (BASE + LEFT).
- `SHR = d7 = FINE_X` — right-shift count for `lsr.l`/`lsr.w` (RIGHT trailing-edge cells).
- `aligned_col = ((int16_t)x >> 1) & 0xfff8` — identical to `blit.c`'s `aligned_col()`. `asr` is
  arithmetic, so negative x → negative aligned_col → LEFT path.
- `d3 = be32(image + A_color_pairs + colour*8)`, `d5 = be32(image + A_color_pairs + colour*8 + 4)`.
- `a0 = dst_base + sign_ext16(aligned_col)`.

`subi.w #0x98,d0` mutates d0 to `aligned_col − 0x98`; the RIGHT ladder continues from there.

---

## 3. Width dispatch (aligned_col → case, with boundaries)

Let `A = aligned_col` (signed 16-bit, multiple of 8). `R = A − 0x98`.

### 3.1 Top-level (entry)
```
A < 0        -> bmi.w $4756  (LEFT ladder, enters at its LAST rung 0x4756)
A >= 0x98    -> bpl.w $4bbe  (RIGHT ladder, enters at its LAST rung 0x4bbe; d0 = R)
0 <= A < 0x98-> fall to $46b2 (BASE)
```

### 3.2 LEFT ladder (0x473a..0x475a), entered at 0x4756
```
4756: addq.w #8,d0 ; bpl.s $475c   ; A+8 >= 0 (A == -8) -> LEFT case1 @ 475c
475a: rts                          ; else (A <= -16) nothing to draw
; --- rungs above are UNREACHABLE from entry (nothing branches to 0x473a): ---
4750: addq.w #8,d0 ; bpl.s $47ba   ; -> LEFT case2
4746: addq.w #8,d0 ; bpl.w $4892   ; -> LEFT case3
473c: addq.w #8,d0 ; bpl.w $49e4   ; -> LEFT case4
;   (each continuing rung also does addq.l #8,a1 ; addq.l #8,a0 before the next test)
```

### 3.3 RIGHT ladder (0x4bae..0x4bc2), entered at 0x4bbe (d0 = R)
```
4bbe: subq.w #8,d0 ; bmi.s $4bc4   ; R-8 < 0 (R == 0, i.e. A == 0x98) -> RIGHT case1 @ 4bc4
4bc2: rts                          ; else (A >= 0xa0) nothing to draw
; --- rungs above are UNREACHABLE from entry: ---
4bba: subq.w #8,d0 ; bmi.s $4c22   ; -> RIGHT case2
4bb4: subq.w #8,d0 ; bmi.w $4cfa   ; -> RIGHT case3
4bae: subq.w #8,d0 ; bmi.w $4e4c   ; -> RIGHT case4
```

### 3.4 Reachable mapping (the dispatch the C must reproduce)
| aligned_col A | case | entry | cells/row | edge | rewind a0/a2 | a1 extra |
|---|---|---|---|---|---|---|
| A ≤ −16 | (clipped) | 0x475a | — (rts) | — | — | — |
| A = −8 | LEFT case1 | 0x475c | 1 | 1 lead a2-only | 0xa8 | 0 |
| 0 ≤ A ≤ 0x90 | BASE | 0x46b2 | 1 | none (full) | 0xa8 | 0 |
| A = 0x98 | RIGHT case1 | 0x4bc4 | 1 | 1 trail a0-only | 0xa8 | 0 |
| A ≥ 0xa0 | (clipped) | 0x4bc2 | — (rts) | — | — | — |

C dispatch:
```
if (A < 0)          { if (A == -8)   run(LEFT,  full=0); else return; }
else if (A - 0x98 >= 0) { if (A == 0x98) run(RIGHT, full=0); else return; }
else                run(BASE, full=1);
```
(`full` = the count of two-column STRADDLE cells; the edge cell type is implied by the family.)

---

## 4. The ONE reusable per-cell kernel

A "cell" = one 16-pixel source column (4 plane words A,B,C,D + one shared mask word, all read from a1)
written into the destination. Three shift/column variants, all sharing the same mask build, the same
`swap`-toggled plane→fill assignment, and the same plane-3 inverse-mask rule:

### 4.1 Shared mask build (once per cell)
```
moveq  #$ff,dM       ; dM = 0xFFFFFFFF  (moveq SIGN-EXTENDS #$ff -> the HIGH word is 0xFFFF, NOT 0)
move.w (a1)+,dM      ; dM.w = A  (low word only; high word stays 0xFFFF)
or.w   (a1)+,dM      ; dM.w |= B
or.w   (a1)+,dM      ; dM.w |= C
move.w (a1)+,d0      ; d0.w = D
not.w  d0            ; d0.w = ~D
or.w   d0,dM         ; dM.w = A|B|C|~D
not.w  dM            ; dM.w = ~(A|B|C|~D) = ~(A|B|C) & D   (16-bit SHOW/keep mask; high word STILL 0xFFFF)
subq.l #8,a1         ; rewind a1: the 4 plane words are re-read as pixel data below
```
`dM` = **d2** for BASE/LEFT (all cells), = **d1** for RIGHT (all cells). After this, `dM = 0xFFFF<mask16>`.
**CRITICAL (load-bearing):** `moveq #$ff` sign-extends the byte 0xff to `0xFFFFFFFF`, so the mask
longword's **high word is 0xFFFF**, not 0. Those set high bits shift/rotate into the *other* 16-pixel
column under `rol.l d6` / `lsr.l d7`, so the straddled column's keep-mask is `(rotl32(0xFFFF<<16 |
mask16, shl))` — the high-word 1s land in the low word after the rotate and must be present. Build the
mask as `mask32 = 0xFFFF0000u | mask16` before every `rol.l`/`lsr.l`. (An earlier draft of this spec
wrongly said the high word was 0 — that produced correct col0 but a wrong keep-mask on the straddled
column; verified against the oracle.)

Result `mask16 = (uint16_t)(~(A | B | C) & D)` — identical to `blit_transp_cell`'s `mask`.

### 4.2 Plane → fill-half assignment (identical in all cells)
Four planes emitted in order, each preceded by exactly one `swap` of its fill register:
- plane 0 → `swap d3` then `and.w d3,d0`
- plane 1 → `swap d3` then `and.w d3,d0`
- plane 2 → `swap d5` then `and.w d5,d0`
- plane 3 → `swap d5` then `and.w d5,d0`, **plus the plane-3 inverse-mask** (see 4.6).

`d3`/`d5` start each cell un-swapped; the FIRST `swap` brings the HIGH word into the low half. So
across a cell the fill halves consumed are: `plane0 = d3>>16`, `plane1 = d3 & 0xffff`,
`plane2 = d5>>16`, `plane3 = d5 & 0xffff`. Two `swap`s of d3 + two of d5 per cell = even → d3/d5 are
restored to their un-swapped state at the cell boundary, so the next cell starts consistent. **Model
d3/d5 as live 32-bit state whose halves are consumed in this fixed order** (equivalently, precompute
`d3hi=d3>>16, d3lo=d3&0xffff, d5hi, d5lo` and index by plane).

### 4.3 STRADDLE cell (BASE + LEFT non-edge + RIGHT non-edge) — writes BOTH (a0) and (a2)
Reference: BASE 0x46b2..0x4728.
```
rol.l  d6,dM         ; rotate 32-bit mask LEFT by d6 = 16-FINE_X (straddles two columns)
move.l dM,d1 ; swap d1   ; d1.w = MASK_HI = mask straddled into the (a0) column
                          ; dM.w  = MASK_LO = mask straddled into the (a2) column
and.w  d1,(a0)       ; punch hole in column 0 (a0)
and.w  dM,(a2)       ; punch hole in column 1 (a2 = a0+8)
; then per plane p in 0..3:
  and.w d1,(a0)      ;   (re-apply MASK_HI before every plane after plane 0)
  and.w dM,(a2)      ;   (re-apply MASK_LO)
  moveq #0,d0
  move.w (a1)+,d0    ;   d0 = plane_word_p (zero-extended)
  lsl.l  d6,d0       ;   d0 <<= (16-FINE_X)  (32-bit; high word = overflow into col 0)
  swap   dF ; and.w dF,d0    ;   dF in {d3,d5}: mask LOW half (col 1) with the plane's fill half
  or.w   d0,(a2)+    ;   write col 1, advance a2
  swap   d0 ; and.w dF,d0    ;   d0.w = HIGH half (col 0), masked by the SAME fill half
  or.w   d0,(a0)+    ;   write col 0, advance a0
```
Bit math: `pix32 = (uint32_t)plane_word << (16 - FINE_X)`; low word (`pix32 & 0xffff`) → (a2),
high word (`pix32 >> 16`) → (a0). Mask straddle: `m32 = rotl32(mask16, 16 - FINE_X)`,
`MASK_HI = m32 >> 16` gates (a0), `MASK_LO = m32 & 0xffff` gates (a2). Per cell: `a0 += 8, a2 += 8,
a1 += 8` (net, after the mask-rewind). Note in the disassembly the pre-AND for plane 0 is the two
`and.w d1,(a0)/and.w dM,(a2)` right after the mask build; for planes 1..3 they repeat at the head of
each plane group. Order within a plane: write **(a2) first, then (a0)**.

### 4.4 LEFT lead edge cell (a2-only) — writes ONLY (a2), 16-bit shift
Reference: LEFT case1 0x4760..0x47a6. The sprite's leading 16px column is off-screen-left; only its
rightward sub-pixel spill lands on-screen (in the (a2) column).
```
rol.l  d6,d2         ; (mask built into d2; still rol.l — but only the LOW word is used)
and.w  d2,(a2)       ; punch hole ONLY in (a2); (a0) never touched, d1/MASK_HI never computed
; per plane p in 0..3:
  and.w d2,(a2)      ;   (re-apply, planes 1..3)
  move.w (a1)+,d0
  lsl.w  d6,d0       ;   WORD shift (no straddle spill kept)
  swap   dF ; and.w dF,d0
  or.w   d0,(a2)+    ;   write (a2) only; plane 3 also applies not.w d2 first (see 4.6)
```
After the 4 planes: `addq.l #8,a0` re-syncs a0 to the first visible column so following STRADDLE cells
write in step. `a2 += 8, a1 += 8` per this cell.

### 4.5 RIGHT trail edge cell (a0-only) — writes ONLY (a0), right shift by FINE_X
Reference: RIGHT case1 0x4bc8..0x4c0e. The sprite's trailing column is off-screen-right; only the
on-screen (a0) column is drawn, aligned by a RIGHT shift.
```
lsr.l  d7,d1         ; (mask built into d1) shift 32-bit mask RIGHT by d7 = FINE_X; low word = mask>>FINE_X
and.w  d1,(a0)       ; punch hole ONLY in (a0)
; per plane p in 0..3:
  and.w d1,(a0)      ;   (re-apply, planes 1..3)
  move.w (a1)+,d0
  lsr.w  d7,d0       ;   WORD right shift by FINE_X
  swap   dF ; and.w dF,d0
  or.w   d0,(a0)+    ;   write (a0) only; plane 3 also applies not.w d1 first (see 4.6)
```
`a0 += 8, a1 += 8` per cell. `(a2)` is never written (the case still keeps a2 stepping via `addq.l
#8,a2` for the uniform rewind arithmetic — dead bookkeeping).

### 4.6 Plane-3 inverse-mask rule (all cell variants)
The last plane (D) is the "leftover" plane: it lights only where the sprite is opaque — i.e. its
PIXELS are ANDed with `~mask` before the OR, exactly as `blit_transp_cell` writes `d & ~mask` for
plane 3. The destination is still pre-masked with the ORIGINAL (non-inverted) `mask` via the per-plane
`and.w mask,(dst)`; the `not.w` inverts the register only for the **pixel** AND, not the dst AND. So
plane 3 = `(dst & mask) | (pix & ~mask)`, while planes 0..2 = `(dst & mask) | pix`.
In asm the mask register is inverted in place right before plane 3's PIXEL AND (`not.w dM; and.w dM,d0`):
- STRADDLE: `not.w d2; and.w d2,d0` on the (a2)/col-1 pixel, `not.w d1; and.w d1,d0` on the (a0)/col-0
  pixel → `col1 = (dst1 & MASK_LO) | (pix_lo & ~MASK_LO)`, `col0 = (dst0 & MASK_HI) | (pix_hi & ~MASK_HI)`.
- LEFT edge: `not.w d2; and.w d2,d0` on the (a2) pixel → `col = (dst & MASK_LO) | (pix & ~MASK_LO)`.
- RIGHT edge: `not.w d1; and.w d1,d0` on the (a0) pixel → `col = (dst & mask') | (pix & ~mask')`.
The `not.w` also leaves d1/d2 inverted after the cell, but both are rebuilt fresh next cell
(`moveq #$ff` / new `rol.l`), so the inversion never leaks across cells.

---

## 5. The nine bodies as (edge, straddle-count, rewind) — and the parameterized loop

Every body is: `movea.l a0,a2 ; addq.l #8,a2` (dst2 = dst+8, ONCE at entry), then N cells, then row
epilogue `suba.w #Δ,a0 ; suba.w #Δ,a2 ; suba.w (a3),a1 [; suba.w #extra,a1]`, then `dbf d4,<top>`,
then `rts`. `<top>` is the address *after* the a2 setup, so `a2 = a0+8` re-inits every row.
`rows = d4 + 1`.

| Body | entry | dbf top | rts | cell mix (order) | Δa0=Δa2 | a1 extra | shift |
|------|-------|---------|-----|------------------|---------|----------|-------|
| BASE     | 0x46b2 | 0x46b2 | 0x4738 | S                     | 0xa8 | 0     | `rol/lsl.l d6` |
| LEFT-1   | 0x475c | 0x4760 | 0x47b8 | A2                    | 0xa8 | 0     | `lsl.w d6` |
| LEFT-2   | 0x47ba | 0x47be | 0x4890 | A2, S                 | 0xb0 | 8     | mixed |
| LEFT-3   | 0x4892 | 0x4896 | 0x49e2 | A2, S, S              | 0xb8 | 0x10  | mixed |
| LEFT-4   | 0x49e4 | 0x49e8 | 0x4bac | A2, S, S, S           | 0xc0 | 0x18  | mixed |
| RIGHT-1  | 0x4bc4 | 0x4bc8 | 0x4c20 | R                     | 0xa8 | 0     | `lsr.w d7` |
| RIGHT-2  | 0x4c22 | 0x4c26 | 0x4cf8 | S, R                  | 0xb0 | 8     | mixed |
| RIGHT-3  | 0x4cfa | 0x4cfe | 0x4e4a | S, S, R               | 0xb8 | 0x10  | mixed |
| RIGHT-4  | 0x4e4c | 0x4e50 | 0x5014 | S, S, S, R            | 0xc0 | 0x18  | mixed |

Cell types: **S** = straddle (4.3, both columns), **A2** = LEFT lead edge (4.4, a2-only),
**R** = RIGHT trail edge (4.5, a0-only).

**Collapsing the unrolled 68000 into one parameterized C loop.** Three families
{BASE, LEFT, RIGHT}, each parameterized by `straddle_cells s ∈ {0,1,2,3}`:

- **BASE** — `edge = none`, one S cell (s is effectively 1 S with no edge), Δ = 0xa8, extra = 0.
  (BASE is its own family: 1 S cell, no edge, and it is the only 0≤A<0x98 body.)
- **LEFT** — `edge = A2 (lead)`, then `s` S cells; then per-row `a0 += 8` was folded as the
  post-edge re-sync (already accounted: it happens once, inside the row). Δa0=Δa2 = `0xa8 + 8*s`,
  a1 extra = `8*s`. LEFT-1 → s=0; LEFT-2 → s=1; LEFT-3 → s=2; LEFT-4 → s=3.
- **RIGHT** — `s` S cells, then `edge = R (trail)`. Δa0=Δa2 = `0xa8 + 8*s`, a1 extra = `8*s`.
  RIGHT-1 → s=0; RIGHT-2 → s=1; RIGHT-3 → s=2; RIGHT-4 → s=3.

Per-row pseudo-loop:
```
a2 = a0 + 8;                         /* dst2 = dst + 8 */
for each of (rows_minus1 + 1) rows:
    switch family:
      BASE:  straddle_cell();                                   /* 1 S */
      LEFT:  lead_edge_cell();  a0 += 8;                        /* A2, then re-sync a0 */
             for (i=0;i<s;i++) straddle_cell();
      RIGHT: for (i=0;i<s;i++) straddle_cell();
             trail_edge_cell();  a2 += 8;                       /* R, then keep a2 in step */
    a0 -= (0xa8 + 8*s);  a2 -= (0xa8 + 8*s);
    a1 -= be16(image + stride_ptr);
    a1 -= 8*s;                                                  /* a1 extra (0 for BASE/edge-only) */
```
(`a0`, `a2`, `a1` are image offsets; `straddle_cell`/`lead_edge_cell`/`trail_edge_cell` advance them
per 4.3/4.4/4.5.) For BASE, `s=0` in the rewind term (Δ=0xa8, extra=0) and the body is a single S cell.

Since only BASE, LEFT-1 (s=0), and RIGHT-1 (s=0) are reachable from the documented entry, a minimal
correct port needs only those three; the `s∈{1,2,3}` parameterization is provided so the same loop
reproduces the dead bodies byte-exactly if a test enters them directly.

**Note on RIGHT-1's dbf/a2 bookkeeping (0x4bc4):** the loop top is 0x4bc8 (after `movea.l a0,a2;
addq.l #8,a2`), and inside each row `addq.l #8,a2` (0x4c10) then `suba.w #0xa8,a2` moves a2 by −0xa0,
matching a0's net −0xa0, so `a2 = a0 + 8` is preserved across rows even though a2 is never written.

---

## 6. 16-bit-wrap-sensitive spots (mirror the 68000 word ops exactly)

1. **`asr.w #1` is arithmetic** — sign-extend before shifting: `(int16_t)x >> 1`. A logical shift
   would break negative x → wrong dispatch.
2. **`aligned_col` and `R` are 16-bit** — `A = ((int16_t)x >> 1) & 0xfff8` as `uint16_t`; the sign
   tests (`bmi`, `bpl`) are on the 16-bit value: `(int16_t)A < 0`, `(int16_t)(A - 0x98) >= 0`.
3. **`FINE_X` from the ORIGINAL x** — `x & 0xf` computed before the `asr`/`andi`. Compute first.
4. **`moveq #$ff` then `move.w` mask build** — the mask longword's **high word is 0xFFFF** going into
   `rol.l`/`lsr.l` (moveq sign-extends 0xff to 0xFFFFFFFF; the `move.w`/`not.w` only touch the low
   word). Build `mask16` as a `uint16_t`, then set the high 16 to 0xFFFF before the rotate/shift:
   `mask32 = 0xFFFF0000u | mask16;`. The straddled column's keep-mask depends on those high 1s.
5. **`rol.l d6,d2` is a full 32-bit rotate**; `lsl.l d6,d0` a 32-bit shift; `lsr.l d7,d1` a 32-bit
   right shift. `d6 = 16 − FINE_X ∈ [1,16]`, `d7 = FINE_X ∈ [0,15]`. 68000 shift counts are mod 64, so
   16 is a genuine 16-bit straddle (not 0). Use a real `rotl32`. **`d6 == 16` (FINE_X == 0)** is the
   pixel-aligned degenerate: `rotl32(mask16,16)` → hi=mask16, lo=0; `lsl.l d0,16` → hi=plane, lo=0
   (all pixels land in the (a0) column, (a2) gets nothing). Still routes through this function.
6. **`lsl.w d6`/`lsr.w d7` are WORD ops** (edge cells) — mask/shift as `uint16_t`, no straddle spill.
   `lsl.w` by 16 (FINE_X==0, LEFT edge) yields 0 on the 68000 (word shift count 16 clears the word);
   mirror with `(uint16_t)((uint32_t)word << (16-FINE_X))` cast down. `lsr.w` by 0 (RIGHT edge,
   FINE_X==0) is a no-op.
7. **`suba.w (a3),a1`** reads a **word** at `stride_ptr` and subtracts its sign-extended value:
   `a1 -= sign_ext16(be16(image + stride_ptr))`. Likewise `suba.w #Δ,a0/a2` subtract sign-extended
   word constants (all positive here). Keep a0/a1/a2 as `uint32_t` image offsets with wraparound.
8. **RMW on (a0)/(a2)** is 16-bit: `wr16(image+ptr, (be16(image+ptr) & mask) | pix)`. The `and.w` and
   `or.w` are separate instructions in asm; the net per-plane effect is one masked OR-in.
9. **`not.w`** inverts only the low 16 bits: `mask16 ^ 0xffff` (kept as `uint16_t`).

---

## 7. Implementation guidance (recreate/ style)

- Two kernels mirroring `blit_transp_cell`, both taking `image`, running pointers by reference, and
  the fill halves + shift count:
  - `blit_shift_straddle_cell(image, &a0, &a2, &a1, shl /*=d6*/, d3, d5)` — 4.3 (both columns).
  - `blit_shift_edge_cell(image, &ptr, &a1, shift, is_right /*a0 vs a2, lsr vs lsl.w*/, d3, d5)` —
    4.4/4.5 (single column). The lead (LEFT) and trail (RIGHT) edges differ only in shift direction
    and which pointer they write; share one helper.
- The `g_blit_obj_shift` wrapper maps the register ABI (§1) to the loop of §5, reading `(a1)`/`(a3)`
  as image offsets via `be16` exactly like `blit.c`'s `load32`/`store32`.
- Named constants (no magic numbers):
  `A_color_pairs = 0x15afa`, `COL_ALIGN = 0xfff8`, `NIBBLE = 0xf`, `COLOR_STRIDE = 8` (colour*8),
  `SUBPX_BITS = 16` (d6 = 16 − FINE_X), `RIGHT_BOUND = 0x98`, `CELL_BYTES = 8`, `COLUMN_BYTES = 8`
  (a2 = a0 + 8), `ROW_REWIND_BASE = 0xa8` (Δ = ROW_REWIND_BASE + CELL_BYTES*s),
  `A1_EXTRA = CELL_BYTES*s`, `PLANES = 4`, `LEFT_EDGE_COL = -8`.
- Reuse `dup16`/`sign_ext16` from `include/machine.h`/`include/draw.h` where applicable; add a small
  `rotl32` helper (no existing one).

---

## 8. Register state at rts

Leaf; no return value (void). At `rts`: d0/d1/d2 = scratch (clobbered), a0/a2 = final-row base minus
rewind, a1 = src rewound, d4 = 0xffff (dbf exhausted), d3/d5/d6/d7 net-preserved (even # of swaps),
a3 unchanged. Callers (via `draw_object_list`) treat it as a pure blit.
