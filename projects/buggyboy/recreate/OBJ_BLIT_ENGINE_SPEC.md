# SPEC: Shared object-sprite blit engine (Ghidra 0x131f6..0x13df8) + helper 0x145fc

Authoritative implementation spec, synthesized from the five slice analyses and **re-verified
directly against the disassembly** wherever the analyses disagreed. All addresses are **Ghidra**
addresses (file offset + 0x10000): file 0x31f6 = Ghidra 0x131f6. Disasm was taken with
`python3 ../../tools/prg_dis.py bin/BUGGYBOY.PRG --start $((0x31f6 + 28)) --len 0xa9a` (engine)
and `--start $((0x45fc + 28)) --len 0x24` (helper); the width-0x80 WIDE body at 0x13c8c lies just
past the 0xa9a window and was disassembled separately (`--start $((0x3c8c + 28)) --len 0x180`).

This is `g_blit_objshift2`'s SIBLING engine: same three-primitive shell (STRADDLE / LEFT-EDGE /
RIGHT-EDGE), same `a0`/`a2=a0+8` column pairing, same per-row `suba.w d3,{a0,a2,a1}; dbf d4; rts`
rewind, same clip ladders. It differs in exactly two ways: (a) the transparency mask is built from
**four** source words `~(w0|w1|w2|~w3)` (= `~w0 & ~w1 & ~w2 & w3`, the `objsh_build_mask` formula at
0x14680) instead of two; (b) there is **no colour indexing** — pixels are copied plain-shifted and
OR'd, with no `color_pairs` / `d3`/`d5` colour AND (contrast `g_blit_objshift` @ 0x14680).

> ## CORRECTIONS to the driving analyses (verified against bytes — trust THIS document)
> 1. **`moveq #$ff,d2` seeds d2 = 0xFFFFFFFF (HIGH word 0xFFFF), NOT 0x000000FF.** Bytes `74ff`. 0xFF
>    is a *negative* signed byte, so `moveq` sign-extends it: the high word is **0xFFFF** going into
>    `rol.l`/`lsr.l` (identical to `objsh_build_mask` @ 0x14680). `move.w (a1),d2` overwrites only the
>    LOW word with the show mask. **RE-CORRECTED after oracle verification during reconstruction:** an
>    earlier revision of THIS document claimed a 0x0000 high word — that is WRONG. With a zero high
>    word the col-0 background is wiped (mask rotates in zeros); the oracle preserves it. Correct:
>    `mask32 = rotl32(0xffff0000u | (uint16_t)~(w0|w1|w2|~w3), shl)`.
> 2. **BASE per-row STRADDLE-cell counts are 4 / 3 / 2 / 1** for widths 0x80 / 0x88 / 0x90 / 0x98
>    (counted `moveq #$ff` between each `dbf` target and its `suba.w d3`). Analysis 1 said 5,
>    Analysis 2 said 7/6/4 — **both wrong**.
> 3. **WIDE body 0x13c8c (width-0x80 wide path) is 3 STRADDLE cells + 1 RIGHT-EDGE cell**, d3=0xC0,
>    rts 0x13df8 — NOT "6 cells, no edge" (Analysis 4 wrong; it is past the 0xa9a slice).
> 4. **Helper 0x145fc third instruction is literally `adda.w -(a2),a3`** (bytes `d6e2`, predecrement
>    of a2), NOT `adda.w (a3),a3` / "a3 += word@(a3)" as the TARGET prose paraphrased. Confirmed by
>    the surrounding wrappers (t34/t33/t32) all doing `movea.l a6,a0; adda.w -(a2),a0`.
> 5. **`moveq #$e0,d3` in the helper sign-extends to 0xFFFFFFE0**, so the word `and.w (a3),d3` masks
>    with **0xFFE0** on the low word; the result is then sign-extended by `adda.w d3,a0`.
>    **RE-CORRECTED after oracle verification:** an earlier revision said 0x00E0 — WRONG. With real
>    table word 0x41a1 the oracle nudges a0 by 0x41a0 (= 0x41a1 & 0xFFE0), not 0x80. Model as
>    `a0 += sign_ext16(word[1] & 0xFFE0)`.

---

## §1. Shared-core IN-register contract (the fine-x prologue)

On entry to any width prologue (0x131f6 / 0x133b6 / 0x1352c / 0x13642):

| Reg | Role IN |
|-----|---------|
| D0.w | screen x (signed). Used for `fine_x = x & 0xf` and `aligned_col = ((int16)x >> 1) & 0xfff8`. |
| D4.w | rows − 1 (the `dbf d4` counter; draws D4+1 rows). |
| A0   | dst scanline base (image offset into a draw buffer). |
| A1   | src sprite stream (image offset; 4 plane words per cell, read `(a1)+`). |
| D1,D2,D3,D6,D7,A2 | scratch — the prologue and body overwrite all of them. |

The core is a LEAF: no stack frame, exits via `rts`, writes only the draw buffer via A0/A2, reads
sprite words from A1. No path's register outputs are consumed by callers.

The prologue derives:
- **D7 = fine_x = D0 & 0xf** (`moveq #$f,d7; and.w d0,d7`) — the RIGHT-shift count (`lsr`) for WIDE edges.
- **D6 = 16 − fine_x** (`moveq #$10,d6; sub.w d7,d6`) — the LEFT-shift count (`lsl.l`/`rol.l`/`lsl.w`)
  for BASE, LEFT, and WIDE straddle cells. Range 1..16 (D6=16 when fine_x=0).
- **D0 = aligned_col = (((int16)x) >> 1) & 0xFFF8** (`asr.w #1; andi.w #$fff8`), then **A0 += D0**
  (`adda.w d0,a0`, sign-extended word add). D0 stays live as the dispatch value.

Both D6 and D7 are live throughout (BASE/LEFT use D6; WIDE straddle uses D6, WIDE edge uses D7).

---

## §2. Fine-x prologue + width dispatch (four width variants)

Byte-identical per variant except the `WIDTH` immediate, the BASE `d3`, and the LEFT/WIDE targets.
Reference (width 0x80 @ 0x131f6):

```
0x131f6  moveq #$f,d7            ; d7 = fine_x seed
0x131f8  and.w  d0,d7            ; d7 = x & 0xf  = fine_x        (RIGHT-shift count)
0x131fa  moveq #$10,d6
0x131fc  sub.w  d7,d6            ; d6 = 16 - fine_x              (LEFT-shift count)
0x131fe  asr.w  #1,d0            ; d0 = (int16)x >> 1
0x13200  andi.w #$fff8,d0        ; d0 = aligned_col (8-byte granular, signed)
0x13204  adda.w d0,a0           ; a0 += aligned_col   <-- 0x13204 = ALT ENTRY (see §7)
0x13206  bmi.w  <LEFT>           ; aligned_col < 0  -> LEFT clip ladder
0x1320a  subi.w #<WIDTH>,d0      ; d0 = aligned_col - WIDTH
0x1320e  bpl.w  <WIDE>           ; aligned_col - WIDTH >= 0 -> WIDE clip ladder
         ;                       ; else fall into BASE body
```

Dispatch is signed-word (mirror with int16_t). Model `bmi <LEFT>` as `if (aligned_col < 0)` and
`subi.w #WIDTH,d0; bpl <WIDE>` as `if (aligned_col - WIDTH >= 0)` — the same model
`g_blit_objshift2` uses in `objsh_dispatch`.

| Prologue (Ghidra) | file | WIDTH | BASE d3 | LEFT target | WIDE target | BASE rts |
|---|---|---|---|---|---|---|
| 0x131f6 | 0x31f6 | 0x80 | 0xC0 | 0x136d2 | 0x13a6c | 0x133a4 |
| 0x133b6 | 0x33b6 | 0x88 | 0xB8 | 0x136dc | 0x13a72 | 0x13504 |
| 0x1352c | 0x352c | 0x90 | 0xB0 | 0x136e6 | 0x13a78 | 0x1361a |
| 0x13642 | 0x3642 | 0x98 | 0xA8 | 0x136ee | 0x13a7c | 0x136d0 |

There are **four** width families. The TARGET's STRUCTURE table listed three; the fourth (WIDTH=0x88,
d3=0xB8, prologue 0x133b6) is reached only via the t39/t34/t3 wrappers, never as a jump-table head.

---

## §3. The per-cell KERNEL (three primitives)

`d6 = shl = 16 − fine_x`; `d7 = shr = fine_x`; `d3` = per-body rewind constant. All 16-bit ops wrap
mod 2^16 — mirror with `uint16_t`/`int16_t`. The 32-bit `rol.l`/`lsl.l`/`lsr.l` operate on the full
long. Col0 = a0 (planes 0/1 word pair), col1 = a2 = a0+8 (planes 2/3 word pair).

### 3a. Mask build (identical in all three primitives)
```
moveq #$ff,d2          ; d2 = 0xFFFFFFFF   (74ff — moveq sign-extends 0xFF; HIGH WORD IS 0xFFFF, see CORRECTION 1)
move.w (a1)+,d2        ; d2.w  = w0
or.w   (a1)+,d2        ; d2.w |= w1
or.w   (a1)+,d2        ; d2.w |= w2
move.w (a1)+,d0        ; d0.w  = w3
not.w  d0              ; d0.w  = ~w3
or.w   d0,d2           ; d2.w  = w0|w1|w2|~w3
not.w  d2              ; d2.w  = ~(w0|w1|w2|~w3) = ~w0 & ~w1 & ~w2 & w3   (SHOW mask, 16-bit)
subq.l #8,a1           ; rewind a1: the same 4 words are re-read as the 4 plane pixel words
```
C: `uint16_t show = (uint16_t)~(uint16_t)(w0|w1|w2|(uint16_t)~w3);` then the 32-bit seed
`mask_seed = 0xffff0000u | show;` (HIGH word 0xFFFF, see CORRECTION 1) is rotated/shifted below.

### 3b. STRADDLE cell — writes BOTH columns (a0 & a2), 32-bit `rol.l`/`lsl.l` by d6=shl
Reference 0x1321a..0x13278 (first cell of width-0x80 BASE). Per cell: a1 += 8, a0 += 8, a2 += 8.
```
; mask build (3a) -> d2.w = show ; then:
rol.l  d6,d2           ; mask32 = rotl32(0xFFFF0000|show, shl)   (high word 0xFFFF going in)
move.l d2,d1 ; swap d1 ; d1.w = high16(mask32) = col0 AND-mask ; d2.w (low16) = col1 AND-mask
and.w  d1,(a0)         ; col0 word0: (a0) &= col0mask
and.w  d2,(a2)         ; col1 word0: (a2) &= col1mask
; plane words 0,1,2 (three iterations):
   moveq #0,d0 ; move.w (a1)+,d0 ; lsl.l d6,d0     ; pix32 = (uint32)w << shl
   or.w   d0,(a2)+                                  ; (a2) |= low16(pix32) ; a2 += 2
   swap   d0 ; or.w d0,(a0)+                         ; (a0) |= high16(pix32) ; a0 += 2
   and.w  d1,(a0) ; and.w d2,(a2)                    ; re-mask the NEXT word0 of each col
; plane word 3 (last): mask re-inverted for the trailing "opaque fill outside show"
   moveq #0,d0 ; move.w (a1)+,d0 ; lsl.l d6,d0
   not.w  d2 ; and.w d2,d0 ; or.w d0,(a2)+           ; (a2) |= (low16(pix32) & ~col1mask) ; a2 += 2
   swap   d0 ; not.w d1 ; and.w d1,d0 ; or.w d0,(a0)+; (a0) |= (high16(pix32) & ~col0mask) ; a0 += 2
```
This is `objsh2_straddle_cell`'s shape, but 4 plane words (not 2) and the zero-high-word mask seed.
There is **no** trailing `or.l ~d1` opaque-fill longword (objshift2's colour engine has it; this one
does not — it stops after the plane-3 inverse copy).

### 3c. LEFT-EDGE cell — writes ONLY col1 (a2), WORD `lsl.w` by d6=shl; discards col0
Reference 0x136fc..0x13736. Per cell: a1 += 8, a2 += 8, a0 += 8 (the trailing `addq.l #8,a0`).
```
; mask build (3a) -> d2.w = show ; then:
rol.l  d6,d2           ; NOTE rol.l (32-bit) though only low word d2.w is used here
and.w  d2,(a2)         ; (a2) &= mask
; plane words 0,1,2:
   move.w (a1)+,d0 ; lsl.w d6,d0 ; or.w d0,(a2)+ ; and.w d2,(a2)   ; WORD shift, col1 only
; plane word 3 (last):
   move.w (a1)+,d0 ; lsl.w d6,d0 ; not.w d2 ; and.w d2,d0 ; or.w d0,(a2)+
addq.l #8,a0           ; skip the discarded col0 (keeps the shared d3 rewind correct)
```

### 3d. RIGHT-EDGE cell — writes ONLY col0 (a0), WORD `lsr.w` by d7=shr; discards col1
Reference 0x13a8a..0x13ac2. Uses **d1** as the mask reg and shifts RIGHT by fine_x.
Per cell: a1 += 8, a0 += 8, a2 += 8 (the trailing `addq.l #8,a2`).
```
moveq #$ff,d1 ; move.w (a1)+,d1 ; or.w (a1)+,d1 ; or.w (a1)+,d1
move.w (a1)+,d0 ; not.w d0 ; or.w d0,d1 ; not.w d1     ; d1.w = show mask
subq.l #8,a1
lsr.l  d7,d1           ; mask32 = (uint32)show >> fine_x ; d1.w used as the AND-mask (NOT re-shifted per word)
and.w  d1,(a0)         ; word0
; plane words 0,1,2:
   move.w (a1)+,d0 ; lsr.w d7,d0 ; or.w d0,(a0)+ ; and.w d1,(a0)
; plane word 3 (last):
   move.w (a1)+,d0 ; lsr.w d7,d0 ; not.w d1 ; and.w d1,d0 ; or.w d0,(a0)+
addq.l #8,a2           ; a2 net +8 here; with the RE cell's own advance a2 ends +8 before the rewind
```

---

## §4. BASE bodies (the `bmi`/`bpl` both-fail fall-through)

Each BASE body: `a2 = a0+8; move.w #<d3>,d3` once, then **N STRADDLE cells** per row, then rewind +
loop. **N verified by counting `moveq #$ff` between the `dbf` target and the `suba.w d3`:**

| BASE head | d3 | STRADDLE cells/row | dbf top | rts | src cell reads per row |
|---|---|---|---|---|---|
| 0x13212 (w0x80) | 0xC0 | **4** | 0x1321a | 0x133a4 | 4 |
| 0x133d2 (w0x88) | 0xB8 | **3** | 0x133da | 0x13504 | 3 |
| 0x1354c (w0x90) | 0xB0 | **2** | 0x13550 | 0x1361a | 2 |
| 0x13666 (w0x98) | 0xA8 | **1** | 0x13666 | 0x136d0 | 1 |

Row tail (identical shape):
```
suba.w d3,a0 ; suba.w d3,a2 ; suba.w d3,a1 ; dbf d4,<top> ; rts
```
Per-row net advance = N cells × 8 = 0x20/0x18/0x10/0x8 bytes; each pointer then rewinds by the
literal d3. Net per-row pointer delta = `8*N − d3` = −0xA0 for all four (one 160-byte scanline up,
and the same for a1). Treat d3 as a per-body **literal** constant (mirror `OBJSH2_REWIND*` style); do
not derive it.

---

## §5. LEFT clip family (Ghidra 0x136d2..0x13a6a)

### 5a. Shared LEFT ladder (0x136d2..0x136f2)
```
0x136d2  addq.w #8,d0 ; bpl.w 0x138fe   ; [w0x80 LEFT entry] -> body @0x138fe (1 LE + 4 straddle)
0x136d8  addq.l #8,a1 ; addq.l #8,a0    ; skip one fully-clipped column (src + dst)
0x136dc  addq.w #8,d0 ; bpl.w 0x137f0   ; [w0x88 LEFT entry] -> body @0x137f0 (1 LE + 3 straddle)
0x136e2  addq.l #8,a1 ; addq.l #8,a0
0x136e6  addq.w #8,d0 ; bpl.s 0x13742   ; [w0x90 LEFT entry] -> body @0x13742 (1 LE + 2 straddle)
0x136ea  addq.l #8,a1 ; addq.l #8,a0
0x136ee  addq.w #8,d0 ; bpl.s 0x136f4   ; [w0x98 LEFT entry] -> body @0x136f4 (1 LE + 1 straddle)
0x136f2  rts                            ; still < 0 -> fully off-left, draw nothing
```
Each width's `bmi` from §2 enters at a different rung (0x136d2/0x136dc/0x136e6/0x136ee). Each
`addq.w #8,d0` walks the negative aligned_col toward 0 in 8-byte steps; each pair of `addq.l #8`
discards one fully-clipped column from a1 AND a0 (these advances DO carry into the body). d0 is not
read again after dispatch. Mirrors `g_blit_objshift2`'s LEFT ladder but with FOUR rungs.

### 5b. LEFT bodies — 1 LEFT-EDGE cell (§3c) then k STRADDLE cells (§3b), verified
```
0x136f4 (d3=0xA8): 1 LE + 1 straddle ... wait — see counts below (verified by moveq #$ff between dbf top and suba)
```
Verified cell content (`moveq #$ff` occurrences between each dbf target and its `suba.w d3`):

| LEFT body | d3 | LEFT-EDGE | STRADDLE | dbf top | rts |
|---|---|---|---|---|---|
| 0x136f4 | 0xA8 | 1 | **0** (LE cell only) | 0x136fc | 0x13740 |
| 0x13742 | 0xB0 | 1 | **1** (straddle @0x13784) | 0x1374a | 0x137ee |
| 0x137f0 | 0xB8 | 1 | **2** (@0x13832, 0x13892) | 0x137f8 | 0x138fc |
| 0x138fe | 0xC0 | 1 | **3** (@0x13940, 0x139a0, 0x13a00) | 0x13906 | 0x13a6a |

Each LEFT body: `a2 = a0+8; move.w #<d3>,d3` once, then per row runs the LEFT-EDGE cell (§3c, whose
trailing `addq.l #8,a0` re-syncs past the discarded col0) followed by k STRADDLE cells, then
`suba.w d3,{a0,a2,a1}; dbf d4; rts`. Per-row net pointer delta = −0xA0 (= 8*(1+k) − d3) for all.
**No `bsr` appears anywhere in the LEFT bodies.**

**Reachability (no dead cases):** w0x80 LEFT reaches all of {0x138fe, 0x137f0, 0x13742, 0x136f4,
rts}; w0x88 reaches {0x137f0, 0x13742, 0x136f4, rts}; w0x90 reaches {0x13742, 0x136f4, rts}; w0x98
reaches {0x136f4, rts}. (0x138fe is a LEFT body, NOT a BASE body — Analysis 1 mislabeled it.)

---

## §6. WIDE clip family (Ghidra 0x13a6c..0x13df8)

### 6a. Shared WIDE ladder (0x13a6c..0x13a80)
Entry d0 = aligned_col − WIDTH (already computed by the prologue's `subi.w #WIDTH,d0`, `>= 0`).
```
0x13a6c  subq.w #8,d0 ; bmi.w 0x13c8c   ; [w0x80 WIDE entry] -> body @0x13c8c (3 straddle + 1 RE, d3=0xC0)
0x13a72  subq.w #8,d0 ; bmi.w 0x13b7e   ; [w0x88 WIDE entry] -> body @0x13b7e (2 straddle + 1 RE, d3=0xB8)
0x13a78  subq.w #8,d0 ; bmi.s 0x13ad0   ; [w0x90 WIDE entry] -> body @0x13ad0 (1 straddle + 1 RE, d3=0xB0)
0x13a7c  subq.w #8,d0 ; bmi.s 0x13a82   ; [w0x98 WIDE entry] -> body @0x13a82 (0 straddle + 1 RE, d3=0xA8)
0x13a80  rts                            ; never went negative -> fully off-right, draw nothing
```
Mirror of the LEFT ladder: the first `subq` that drives d0 negative selects how many whole cells fit.

### 6b. WIDE bodies — k STRADDLE cells (§3b) then 1 RIGHT-EDGE cell (§3d), verified
`moveq #$ff` = mask build; `rol.l` marks a STRADDLE cell, `lsr.l` marks the RIGHT-EDGE cell:

| WIDE body | d3 | STRADDLE | RIGHT-EDGE | dbf top | rts |
|---|---|---|---|---|---|
| 0x13a82 | 0xA8 | **0** | 1 (RE @0x13a8a) | 0x13a8a | 0x13ace |
| 0x13ad0 | 0xB0 | **1** (@0x13ad8) | 1 (RE @0x13b38) | 0x13ad8 | 0x13b7c |
| 0x13b7e | 0xB8 | **2** (@0x13b86, 0x13be6) | 1 (RE @0x13c46) | 0x13b86 | 0x13c8a |
| 0x13c8c | 0xC0 | **3** (@0x13c94, 0x13d06, 0x13d66) | 1 (RE @0x13db4) | 0x13c94 | 0x13df8 |

Each WIDE body: `a2 = a0+8; move.w #<d3>,d3` once, then per row runs k STRADDLE cells then the
RIGHT-EDGE cell (§3d, a0-only), then `addq.l #8,a2` (bookkeeping — the RE cell only advanced a0, and
this bump keeps the shared d3 rewind landing correctly), then `suba.w d3,{a0,a2,a1}; dbf d4; rts`.
Note ALL FOUR wide bodies (including 0x13c8c) have the `addq.l #8,a2` before the rewind — Analysis 4
was wrong that the widest body omits it. **No `bsr` appears in the WIDE bodies.** Per-row net delta:
0x13a82 = −0xA8 (a0 walks 5 words = 10 bytes in the RE cell, so a0 net = 10 − 0xA8; a2 = 16 − 0xA8;
a1 net = 8 − 0xA8 — mirror the literal `suba.w d3` per pointer, do not derive).

**Exit map:** rts 0x13a80 (clipped), 0x13ace (w0x98 wide), 0x13b7c (w0x90 wide), 0x13c8a (w0x88 wide),
0x13df8 (w0x80 wide). The 0x13df8 rts is past the declared 0xa9a slice; extend the disasm window to
capture the 0x13c8c body.

---

## §7. The 18 entry points (all thin C wrappers)

Every entry presets registers then reaches a width prologue (0x131f6 / 0x133b6 / 0x1352c / 0x13642)
or an alt/mid re-entry. The join target selects WIDTH + BASE d3. Enumerated with verified presets:

### Width-0x80 group (WIDTH=0x80, BASE d3=0xC0, prologue 0x131f6)
| Entry (Ghidra) | file | Types | Preset / action | Joins |
|---|---|---|---|---|
| 0x131f6 | 0x31f6 | t4 | full prologue | self |
| 0x13204 | 0x3204 | t53 | **ALT ENTRY** — enters at `adda.w d0,a0`, skipping the fine-x/aligned-col calc. Caller pre-sets d0=aligned_col, d6=shl, d7=fine_x, a0=pre-add base, a1=src, d4=rows−1. | 0x13206 dispatch |

### Width-0x88 group (WIDTH=0x88, BASE d3=0xB8, prologue 0x133b6)
| Entry (Ghidra) | file | Types | Preset / action | Joins |
|---|---|---|---|---|
| 0x133a6 | 0x33a6 | t39 | `bsr.w 0x145fc` (view transform); `bra.s 0x133b6` | 0x133b6 prologue |
| 0x133ac | 0x33ac | t34 | `movea.l a6,a0 ; adda.w -(a2),a0` (a0 = a6 + sign_ext16(word@--a2)); `bra.s 0x133b6` | 0x133b6 prologue |
| 0x133b2 | 0x33b2 | t3 | `bsr.w 0x14620` (g_draw_obj_sprite_hi); fall through | 0x133b6 prologue |
| 0x133b6 | 0x33b6 | (join) | full prologue (WIDTH=0x88) | self |
| 0x13444 | 0x3444 | t60 | **MID-BODY re-entry** at `not.w d0` inside the 0x133b6 BASE cell (file 0x343a group). Caller pre-sets d0/d2/a0/a1/a2/d1/d6 to a mid-cell state. Model as re-entry glue; verify reachability before writing a body (likely reached only via the game's live jump-table). | mid BASE 0x133b6 |

### Width-0x90 group (WIDTH=0x90, BASE d3=0xB0, prologue 0x1352c)
| Entry (Ghidra) | file | Types | Preset / action | Joins |
|---|---|---|---|---|
| 0x13506 | 0x3506 | t38 | `bsr.w 0x145fc` ; `bra.s 0x1352c` | 0x1352c prologue |
| 0x1350c | 0x350c | t33 | `movea.l a6,a0 ; adda.w -(a2),a0` ; `bra.s 0x1352c` | 0x1352c prologue |
| 0x13512 | 0x3512 | t42 | scan-table x-build (see below) ; `bra.s 0x1352c` | 0x1352c prologue |
| 0x13528 | 0x3528 | t49 | `bsr.w 0x14620` ; fall through | 0x1352c prologue |
| 0x1352c | 0x352c | t2 | full prologue (WIDTH=0x90) | self |

### Width-0x98 group (WIDTH=0x98, BASE d3=0xA8, prologue 0x13642)
| Entry (Ghidra) | file | Types | Preset / action | Joins |
|---|---|---|---|---|
| 0x1361c | 0x361c | t37 | `bsr.w 0x145fc` ; `bra.s 0x13642` | 0x13642 prologue |
| 0x13622 | 0x3622 | t32 | `movea.l a6,a0 ; adda.w -(a2),a0` ; `bra.s 0x13642` | 0x13642 prologue |
| 0x13628 | 0x3628 | t41 | scan-table x-build (see below) ; `bra.s 0x13642` | 0x13642 prologue |
| 0x1363e | 0x363e | t16,17,43,48 | `bsr.w 0x14620` ; fall through | 0x13642 prologue |
| 0x13642 | 0x3642 | t1 | full prologue (WIDTH=0x98) | self |
| 0x13784 | 0x3784 | t61 | **MID-BODY re-entry** at `moveq #$ff,d2` = the STRADDLE cell of the width-0x90 LEFT body 0x13742. Caller pre-sets a0/a1/a2/d1/d2/d3/d4/d6/d7 to a mid-loop state. Model as re-entry glue; verify reachability first. | mid LEFT 0x13742 |

### Scan-table x-build wrappers (t42 @0x13512, t41 @0x13628), verified byte-identical shape:
```
movea.l a6,a0                 ; a0 = a6
adda.w  (a2)+,a0              ; a0 += sign_ext16(word@a2) ; a2 += 2   (POST-increment)
move.w  0x18c58,d7           ; d7 = word@A_obj_scan_off
neg.w   d7                    ; d7 = -scan_off  (used as the a5 index register below)
move.w  (0,a5,d7.w),d0        ; d0 = word@(a5 + sign_ext16(d7))   (bytes 30357000: mode 6, a5, ext 0x7000 = d7.w index, disp 0)
add.w   (a4),d0               ; d0 += word@a4
add.w   (a2),d0               ; d0 += word@a2
bra <prologue>                ; the prologue recomputes fine_x/aligned_col from this fresh d0
```
(d7 is set here but the prologue's `moveq #$f,d7; and.w d0,d7` overwrites it — the neg'd scan_off is
consumed only by the `move.w (0,a5,d7.w),d0` index.)

**Wrapper families (implement once, parameterized by which prologue they join):**
1. `bsr 0x145fc` then bra/fall — t39/t38/t37.
2. `bsr 0x14620` then fall — t3/t49/t16,17,43,48.
3. `movea.l a6,a0 ; adda.w -(a2),a0` then bra — t34/t33/t32.
4. scan-table x-build then bra — t42/t41.
Plus 0x131f6/0x1352c/0x13642/0x133b6 (bare prologue heads), the ALT entry 0x13204, and the two
mid-body re-entries t60/t61.

**Dead / verify-first cases:** the mid-body re-entries t60 (0x13444) and t61 (0x13784) require the
caller to have set a mid-loop register snapshot. They are analogous to `objsh2`'s dead-body entries;
model them as unreachable-from-clean-entry (or explicit re-entry glue only if a test exercises them)
and confirm reachability against the Musashi oracle before writing bodies.

---

## §8. Helper 0x145fc — byte-exact contract (reconstruct inline)

Raw bytes (file 0x45fc): `204e 267c 0000722a d6e2 3639 00008c56 d643 d6c3 92db 76e0 c653 d0c3 761f c653 9843 4e75`
```
0x145fc  movea.l a6,a0                 ; a0 = a6  (object/buffer base)
0x145fe  movea.l #$0000722a,a3         ; a3 = Ghidra 0x1722a (view-transform table base)   <RELOC>
0x14604  adda.w  -(a2),a3              ; a2 -= 2 ; a3 += sign_ext16(word@a2)   (LITERAL -(a2), see CORRECTION 4)
0x14606  move.w  $18c56.l,d3           ; d3 = word@A_view_flags (0x18c56)                   <RELOC>
0x1460c  add.w   d3,d3                 ; d3 = view_flags * 2  (word doubling; wrap as uint16)
0x1460e  adda.w  d3,a3                 ; a3 += sign_ext16(d3)  -> per-view record
0x14610  suba.w  (a3)+,a1              ; a1 -= sign_ext16(word@a3) ; a3 += 2   (src rewind = record word[0])
0x14612  moveq   #$e0,d3               ; d3 = 0xFFFFFFE0  (moveq sign-extends 0xE0)
0x14614  and.w   (a3),d3               ; d3 = (record word[1]) & 0xFFE0
0x14616  adda.w  d3,a0                 ; a0 += sign_ext16(word[1] & 0xFFE0)
0x14618  moveq   #$1f,d3               ; d3 = 0x0000001F
0x1461a  and.w   (a3),d3               ; d3 = (record word[1]) & 0x001F   (SAME word; a3 not advanced)
0x1461c  sub.w   d3,d4                 ; d4 -= (word[1] & 0x1F)   (shrink rows)
0x1461e  rts
```
**Inputs consumed:** a6 (→a0), a2 (predecremented, left −2), a1 (adjusted), d4 (adjusted),
word@A_view_flags, and the table at 0x1722a. **Outputs:** a0 = a6 + sign_ext16(word[1]&0xFFE0);
a1 −= word[0]; d4 −= (word[1]&0x1F); a3 clobbered; d3 clobbered; **a2 left = a2_in − 2**. **No memory WRITE.**

Record address = `0x1722a + sign_ext16(word@(a2−2)) + view_flags*2`; the helper reads two consecutive
words from it — word[0] = src rewind (subtracted from a1), word[1] = packed field (bits &0xFFE0 →
a0 nudge sign-extended, low 5 bits &0x1F → row-count clip).

**Verification:** cannot be image-verified alone (no writes → nothing to diff). Verify only THROUGH a
caller (t39 @0x133a6, t38 @0x13506, t37 @0x1361c) that runs it then blits, with `_pokes` populating
the 0x1722a table, A_view_flags, and the a2 record.

C shape (image-offset pointers as uint32 addresses):
```
a0 = a6;
a3 = 0x1722a + sign_ext16(be16(image + (a2 -= 2)));      /* adda.w -(a2),a3 */
a3 += 2 * (uint16_t)be16(image + A_view_flags);          /* add.w d3,d3 ; adda.w d3,a3 */
a1 -= sign_ext16(be16(image + a3)); a3 += 2;             /* suba.w (a3)+,a1 */
uint16_t rec1 = be16(image + a3);
a0 += sign_ext16(rec1 & 0xFFE0);                          /* moveq #$e0 -> 0xFFE0 word mask, sign-extended */
d4 -= (uint16_t)(rec1 & 0x001F);
```

---

## §9. 16-bit-wrap / gotcha spots (mirror carefully)

- **Mask seed high word is 0xFFFF** (`moveq #$ff` sign-extends → 0xFFFFFFFF; `move.w` sets only the
  low word). `mask32 = rotl32(0xffff0000u | show16, shl)`.
- **STRADDLE/LEFT use `rol.l`/`lsl.l`/`lsl.w` by d6=16−fine_x; WIDE-EDGE uses `lsr.l`/`lsr.w` by
  d7=fine_x.** When fine_x=0, shl=16 → `rotl32(v,16)` / `<<16`; guard the C shift (`<<16` on a
  16-bit value promoted to 32-bit is fine; a bare `>>16` right-shift by 0 for fine_x=0 in the WIDE
  edge is also fine). The WIDE edge is never reached with fine_x that would over-shift because it
  uses `lsr` by d7 ∈ 0..15.
- **All dispatch compares are signed word** (`bmi`, `bpl` after `subi.w`): mirror aligned_col and
  `aligned_col − WIDTH` as int16_t.
- **`adda.w`/`suba.w` sign-extend the word** before adding to the address register (aligned_col add,
  the −(a2)/(a2)+ record words, the helper's a1/a0/a3 adjustments).
- **Helper `moveq #$e0` = 0xFFFFFFE0** → the `and.w` masks 0xFFE0, then `adda.w` sign-extends (CORRECTION 5).
- **`neg.w d7`** in the scan-table wrappers negates a word; the `move.w (0,a5,d7.w),d0` brief-extension
  index sign-extends d7's word.
- **d3 is a per-body literal rewind, NOT an input.** Entry wrappers do not set it; each body's
  `move.w #<d3>,d3` loads it. Name each: 0xC0/0xB8/0xB0/0xA8.

---

## §10. Implementation shape (match blit.c house style)

- New static primitives (do NOT reuse `objsh2_*` — mask-word count and plane-word count differ):
  `objsprite_build_mask` (reuse the existing `objsh_build_mask` @ blit.c:215 — same 4-word formula),
  `objsprite_straddle_cell` (§3b), `objsprite_left_edge_cell` (§3c), `objsprite_right_edge_cell` (§3d).
  Reuse `rotl32`, `dup16`, `sign_ext16`, `aligned_col`, `be16`/`wr16`.
- One parameterized core `objsprite_core(image, aligned_col, shl, shr, rows_m1, a0, a1, WIDTH, d3_base)`
  implementing §2 dispatch + §4/§5/§6 bodies. The LEFT/WIDE ladders pick the straddle count per §5b/§6b.
  The four widths call it with (0x80,0xC0)/(0x88,0xB8)/(0x90,0xB0)/(0x98,0xA8).
- A prologue wrapper `objsprite_entry(image, x, rows_m1, a0, a1, WIDTH, d3_base)` computing
  fine_x/shl/shr/aligned_col; a second alt wrapper for 0x13204 taking pre-decoded shl/shr/aligned_col.
- Glue `g_objsprite_t1..t61` (one per entry, §7) mapping register presets; the tiny wrappers call the
  inline helper transform (§8) or `g_draw_obj_sprite_hi` (0x14620) first. Register-glue + `proto`/`param`
  lines with explicit storage (d0/d4/a0/a1 register), matching the objshift entries in names.txt.
- Named constants: `OBJSPRITE_WIDTH_80/88/90/98` (0x80/0x88/0x90/0x98),
  `OBJSPRITE_REWIND_C0/B8/B0/A8` (0xC0/0xB8/0xB0/0xA8), `OBJSPRITE_CELL_BYTES=8`,
  `OBJSPRITE_SHIFT_BASE=16`, `OBJSPRITE_FINE_MASK=0xf`, `OBJSPRITE_COL_ALIGN=0xfff8`,
  helper masks `VIEW_XFORM_OFF_MASK=0xFFE0` / `VIEW_XFORM_ROW_MASK=0x001F`. Add
  `A_obj_view_xform = 0x1722a` to addrs.h; reuse `A_view_flags = 0x18c56`, `A_obj_scan_off = 0x18c58`.
- Differential tests (mirror `test_blit_objshift2.py` / `test_blit_objsprite.py`):
  `differential(entry, regs={d0,d4,a0,a1,...,"_pokes":{addr:bytes}}, glue, poison=True)` per entry,
  covering each WIDTH family and each BASE/LEFT/WIDE ladder branch, plus the three `bsr 0x145fc`
  wrappers (staging the 0x1722a table + a2 record + A_view_flags) to exercise the helper transitively.

---

## Appendix: Blitter rts/exit addresses (boundary sanity)
BASE: 0x133a4 (w80), 0x13504 (w88), 0x1361a (w90), 0x136d0 (w98).
LEFT: 0x13740 (0-straddle), 0x137ee (1), 0x138fc (2), 0x13a6a (3); off-left rts 0x136f2.
WIDE: 0x13ace (w98/0-straddle), 0x13b7c (w90/1), 0x13c8a (w88/2), 0x13df8 (w80/3); off-right rts 0x13a80.
