| clipped.S — the asm twin for the four GATED (clipped) masked sprite bodies, TRANSCRIBED from the
| original binary WITH ONE DECLARED SUBSTITUTION. It is the first body in this directory that is not
| byte-identical to the .PRG, and the whole of the divergence is stated below and pinned instruction
| by instruction.
|
|   blit_sprite_rows_gated_asm   <- the original @ 0x14e1e / 0x14f06 / 0x1505e / 0x15230, the C
|                                   reference ../sprite.c's `blit_sprite_rows` with `gated` set
|   blit_sprite_rows_gated_regs  <- the same ladder and bodies, entered with the registers loaded.
|                                   The C-ABI entry above is what the SUITE drives; this is what the
|                                   GAME calls (`sprite.S`, "THE REGISTER-ABI ENTRY", for the
|                                   argument, which is this file's unchanged)
|
| `sprite.S` is this directory's first twin and its header carries the recipe; ../README.md carries
| the six checks a twin needs and the section "The gated twin's declared substitution" carries the
| case for this one. What follows is only what is THIS file's own.
|
| WHY THESE BODIES. `atari/profile.py ours`, a 1000-vblank window of the attract screen: the clipped
| path costs 12,589 cycles a call at ~4.6 calls a frame against the original's 3,802 — 3.3x, and the
| third-largest item in the frame after the restore replay and the unclipped blitter, both of which
| this directory has already answered. A C rewrite was measured first and refused: GCC's `.constprop`
| clones for the gated path spill nothing, call nothing per rotate, and the ONE call left in the path
| (a `__mulsi3` deriving the row loop's trip count) is 257 of the 12,589 — so the 3.3x is spread over
| instruction selection and there is no C change that reaches the original's shape.
|
| ---- THE ONE SUBSTITUTION, AND WHY IT IS UNAVOIDABLE ------------------------------------------
|
| Each gated body differs from its unclipped twin in `sprite.S` by ONE instruction per screen group:
|
|     btst    #n,$16426.l          | 0839 000n 0001 6426 — 8 bytes, 20 cycles
|
| an ABSOLUTE address. This reconstruction receives the image base as a RUN-TIME ARGUMENT — that is
| what `asm_twin.py`'s memory layout exists to enforce, and what the target build actually does — so
| no operand in a `.S` can name `image + 0x16426`. A byte-identical transcription of these four
| bodies is impossible by construction rather than merely inconvenient, and this file substitutes:
|
|     btst    #n,(%a2)             | 0812 000n           — 4 bytes, 12 cycles
|
| with `%a2` holding `image + A_blit_clip_mask`, loaded ONCE per call by the entry below. Three
| things make that a declared substitution rather than a hole:
|
|   * THE SEMANTICS ARE THE ORIGINAL'S. The gate byte is still READ FROM MEMORY at every group of
|     every row — not hoisted into a register — so a blit whose own destination covers 0x16426 draws
|     its later groups under the gate its earlier ones wrote. `../sprite.c`'s SPRITE_GATE_CLIP_MASK
|     comment argues it and `test_sprite.py`'s poked-destination case pins it;
|   * `%a2` IS FREE. No instruction in any of the four bodies touches it: they use a0, a1 and
|     d0-d7 and nothing else, which the transcription below is the evidence for;
|   * EVERY OTHER BYTE IS THE ORIGINAL'S, and each body is pinned as a LIST OF SEGMENTS between the
|     substituted instructions — `<name>_segN_body` .. `<name>_segN_body_end`, each compared against
|     the .PRG at its own address by `test/test_asm_clipped.py` and by `atari/assert_twin_bytes.py`.
|     The suite additionally checks that the segments TILE each body exactly, that each gap between
|     two of them is the 4-byte substitution for the 8-byte instruction the original holds there, and
|     that the bit number is the original's own.
|
| THE `dbf` IS THE SUBSTITUTION'S ONE CONSEQUENCE. The row loop's closing `dbf %d7,<body>` branches
| back over every substituted site, so its displacement is the original's plus 4 for each of them —
| the loop is that much shorter. It is therefore outside the segments too, and pinned by that
| arithmetic (`test_asm_clipped.py`'s `test_the_loop_branch_shrank_by_exactly_the_substitution`).
| Every other branch in these bodies is INTRA-GROUP — the `bne.s` over a skipped group and the
| `bra.w` past its merge both stay between two gates — so no other displacement moves, which the
| segment compare is what proves.
|
| THE COST PIN IS NOT EQUALITY WITH THE ORIGINAL, and cannot be: the substitution is 8 cycles
| CHEAPER per group per row. The suite pins `twin == original - 8 * groups * rows + FRAME`, with
| FRAME the C-ABI frame measured once, exactly as `test_asm_sprite.py`'s TWIN_FRAME_CYCLES is.
|
| REGISTERS: the original's, unchanged through all four bodies, plus the one this file adds —
|   a0 = sprite cursor   a1 = screen cursor   d6 = the shift   d7 = the row count
|   d1..d5 = one source group's mask and four planes, rotated (d0 as well, from the second group on)
|   a2 = image + A_blit_clip_mask, OURS: the substitution's base, written by neither the ladder nor
|        any body
    .text

| GAS OPTIMISES AND THE ORIGINAL'S ASSEMBLER DID NOT — `sprite.S`'s argument, unchanged, and spelt
| again here rather than shared. Sharing it is POSSIBLE (both assembly paths run the file through
| gcc, so a `#include` would work): it is not done because this directory's rule is to re-spell a
| value and let the byte pin prove it, and every use of this macro is inside a compared segment, so a
| copy that drifted reddens by address. A shared prelude would buy three lines and cost a file that
| `kit.mk`'s glob and `build.sh`'s twin list would each need teaching about.
    .macro  MOVEL_ALL_ONES  reg
    .word   0x203c + (\reg << 9)        | move.l #$ffffffff,d\reg
    .long   0xffffffff
    .endm

| ---- the C ABI frame ---------------------------------------------------------------------------
| void blit_sprite_rows_gated_asm(uint8_t *image, uint32_t src, uint32_t dst, unsigned width_class,
|                                 unsigned shift, uint32_t rows_minus_one);
|
| ...which is `../sprite.c`'s `blit_sprite_rows` without its `gated` argument, because this twin IS
| the gated half of that function. `../../include/sprite.h` declares it and is the one place the
| signature lives.
|
| THE GATE ADDRESS IS SPELT HERE and is `../../include/sprite.h`'s A_blit_clip_mask. It is not inside
| a compared segment, so the byte pin does not cover it — what does is the DIFFERENTIAL: a value that
| drifted from the header's would gate every group off a byte the C core does not read, and the very
| first case would diverge.
    .equ    GATED_BLIT_CLIP_MASK, 0x16426
    .equ    GATED_SAVED, (7 * 4)            | what the prologue pushes: %d2-%d7 and %a2
    .equ    GATED_ARG_IMAGE,             4 + GATED_SAVED
    .equ    GATED_ARG_SRC,               8 + GATED_SAVED
    .equ    GATED_ARG_DST,              12 + GATED_SAVED
    .equ    GATED_ARG_WIDTH_CLASS,      16 + GATED_SAVED
    .equ    GATED_ARG_SHIFT,            20 + GATED_SAVED
    .equ    GATED_ARG_ROWS_MINUS_ONE,   24 + GATED_SAVED

        .globl  blit_sprite_rows_gated_asm
blit_sprite_rows_gated_asm:
        movem.l %d2-%d7/%a2,%sp@-
        | THE WIDTH CLASS IS LOADED FIRST and %d7 LAST, so that the flags entering the ladder are the
        | ROW COUNT's — `sprite.S`'s argument for the order, which applies here unchanged: a `tst.l`
        | deleted from the ladder must redden here the way it would on the machine, where the
        | register entry's caller sets no flags at all.
        move.l  GATED_ARG_WIDTH_CLASS(%sp),%d0
        movea.l GATED_ARG_IMAGE(%sp),%a0
        movea.l %a0,%a1
        movea.l %a0,%a2
        adda.l  #GATED_BLIT_CLIP_MASK,%a2
        adda.l  GATED_ARG_SRC(%sp),%a0
        adda.l  GATED_ARG_DST(%sp),%a1
        move.l  GATED_ARG_SHIFT(%sp),%d6
        move.l  GATED_ARG_ROWS_MINUS_ONE(%sp),%d7
        bsr.s   blit_sprite_rows_gated_regs
        movem.l %sp@+,%d2-%d7/%a2
        rts

| ---- THE REGISTER-ABI ENTRY, and it is the one the TARGET BUILD CALLS ---------------------------
| Same ladder, same bodies, entered with the values already in the original's own registers:
|
|   a0 = the sprite cursor (image + src)   a1 = the screen cursor (image + dst)
|   a2 = image + A_blit_clip_mask          d6 = the shift    d7 = the row count
|   d0 = the width class, consumed by the ladder
|   d1-d5 = the bodies' scratch, and therefore the caller's to save
|
| `%a2` IS LOADED BY THE CALLER HERE, in one `lea` at `../sprite.c`'s seam, which is what keeps the
| `btst` substitution the only divergence in this file: a body that computed the gate address itself
| would be a second one. `sprite.S`'s "WHY BOTH ENTRIES EXIST" carries the measurement; the same
| argument applies unchanged, and `atari/smoke.py`'s framebuffer identity is the surface for the
| shipped-only glue.
        .globl  blit_sprite_rows_gated_regs
blit_sprite_rows_gated_regs:
        | THE LADDER'S DOMAIN IS 0..3 and the fall-through arm takes class 3 — a property of the one
        | call site rather than a bound this file imposes. `../sprite.c`'s `blit_sprite_clipped` is
        | reached only through `SPRITE_BLIT_TABLE`'s eight clipped entries, each of which carries its
        | own literal class, so nothing else can arrive (`sprite.S`'s ladder note has the full walk
        | of why a class of 4 never reaches a ladder at all).
        tst.l   %d0
        beq.s   .Lgated_width16
        subq.l  #1,%d0
        beq.s   .Lgated_width32
        subq.l  #1,%d0
        beq.s   .Lgated_width48
        bra.w   sprite_blit_w64_gated_seg0_body
.Lgated_width48:
        bra.w   sprite_blit_w48_gated_seg0_body
.Lgated_width32:
        bra.w   sprite_blit_w32_gated_seg0_body
.Lgated_width16:
        bra.w   sprite_blit_w16_gated_seg0_body

| ---- the transcribed segments ------------------------------------------------------------------
| Everything between a `_segN_body` label and its `_segN_body_end` is the original's instruction
| sequence in order, one instruction per line, each carrying its original address and encoding. The
| two kinds of line BETWEEN two segments are the substitution and its consequence, and they are the
| only instructions in this section that are not the .PRG's own bytes.

| ------------------------------------------------------------------------------------------------
| sprite_blit_w16_gated: the original @ 0x14e1e..0x14e98

    .globl  sprite_blit_w16_gated_seg0_body
sprite_blit_w16_gated_seg0_body:
    MOVEL_ALL_ONES 1                      | 014e1e  223cffffffff
    clr.l   %d2                           | 014e24  4282
    clr.l   %d3                           | 014e26  4283
    clr.l   %d4                           | 014e28  4284
    clr.l   %d5                           | 014e2a  4285
    move.w  (%a0)+,%d1                    | 014e2c  3218
    move.w  (%a0)+,%d2                    | 014e2e  3418
    move.w  (%a0)+,%d3                    | 014e30  3618
    move.w  (%a0)+,%d4                    | 014e32  3818
    move.w  (%a0)+,%d5                    | 014e34  3a18
    ror.l   %d6,%d1                       | 014e36  ecb9
    ror.l   %d6,%d2                       | 014e38  ecba
    ror.l   %d6,%d3                       | 014e3a  ecbb
    ror.l   %d6,%d4                       | 014e3c  ecbc
    ror.l   %d6,%d5                       | 014e3e  ecbd
sprite_blit_w16_gated_seg0_body_end:
    btst    #1,(%a2)                      | 014e40  0839000100006426 -> 08120001  SUBSTITUTED
    .globl  sprite_blit_w16_gated_seg1_body
sprite_blit_w16_gated_seg1_body:
    bne.s   .Lsprite_blit_w16_gated_bit1_draw    | 014e48  6608
    lea     8(%a1),%a1                    | 014e4a  43e90008
    bra.w   .Lsprite_blit_w16_gated_bit1_done    | 014e4e  60000012
.Lsprite_blit_w16_gated_bit1_draw:
    and.w   %d1,(%a1)                     | 014e52  c351
    or.w    %d2,(%a1)+                    | 014e54  8559
    and.w   %d1,(%a1)                     | 014e56  c351
    or.w    %d3,(%a1)+                    | 014e58  8759
    and.w   %d1,(%a1)                     | 014e5a  c351
    or.w    %d4,(%a1)+                    | 014e5c  8959
    and.w   %d1,(%a1)                     | 014e5e  c351
    or.w    %d5,(%a1)+                    | 014e60  8b59
.Lsprite_blit_w16_gated_bit1_done:
    swap    %d1                           | 014e62  4841
    swap    %d2                           | 014e64  4842
    swap    %d3                           | 014e66  4843
    swap    %d4                           | 014e68  4844
    swap    %d5                           | 014e6a  4845
sprite_blit_w16_gated_seg1_body_end:
    btst    #0,(%a2)                      | 014e6c  0839000000006426 -> 08120000  SUBSTITUTED
    .globl  sprite_blit_w16_gated_seg2_body
sprite_blit_w16_gated_seg2_body:
    bne.s   .Lsprite_blit_w16_gated_bit0_draw    | 014e74  6608
    lea     6(%a1),%a1                    | 014e76  43e90006
    bra.w   .Lsprite_blit_w16_gated_bit0_done    | 014e7a  60000012
.Lsprite_blit_w16_gated_bit0_draw:
    and.w   %d1,(%a1)                     | 014e7e  c351
    or.w    %d2,(%a1)+                    | 014e80  8559
    and.w   %d1,(%a1)                     | 014e82  c351
    or.w    %d3,(%a1)+                    | 014e84  8759
    and.w   %d1,(%a1)                     | 014e86  c351
    or.w    %d4,(%a1)+                    | 014e88  8959
    and.w   %d1,(%a1)                     | 014e8a  c351
    or.w    %d5,(%a1)                     | 014e8c  8b51
.Lsprite_blit_w16_gated_bit0_done:
    lea     146(%a1),%a1                  | 014e8e  43e90092
sprite_blit_w16_gated_seg2_body_end:
    dbf     %d7,sprite_blit_w16_gated_seg0_body  | 014e92  51cfff8a, less 4 a substitution
    .globl  sprite_blit_w16_gated_seg3_body
sprite_blit_w16_gated_seg3_body:
    rts                                   | 014e96  4e75
sprite_blit_w16_gated_seg3_body_end:

| ------------------------------------------------------------------------------------------------
| sprite_blit_w32_gated: the original @ 0x14f06..0x14fd8

    .globl  sprite_blit_w32_gated_seg0_body
sprite_blit_w32_gated_seg0_body:
    MOVEL_ALL_ONES 1                      | 014f06  223cffffffff
    clr.l   %d2                           | 014f0c  4282
    clr.l   %d3                           | 014f0e  4283
    clr.l   %d4                           | 014f10  4284
    clr.l   %d5                           | 014f12  4285
    move.w  (%a0)+,%d1                    | 014f14  3218
    move.w  (%a0)+,%d2                    | 014f16  3418
    move.w  (%a0)+,%d3                    | 014f18  3618
    move.w  (%a0)+,%d4                    | 014f1a  3818
    move.w  (%a0)+,%d5                    | 014f1c  3a18
    ror.l   %d6,%d1                       | 014f1e  ecb9
    ror.l   %d6,%d2                       | 014f20  ecba
    ror.l   %d6,%d3                       | 014f22  ecbb
    ror.l   %d6,%d4                       | 014f24  ecbc
    ror.l   %d6,%d5                       | 014f26  ecbd
sprite_blit_w32_gated_seg0_body_end:
    btst    #2,(%a2)                      | 014f28  0839000200006426 -> 08120002  SUBSTITUTED
    .globl  sprite_blit_w32_gated_seg1_body
sprite_blit_w32_gated_seg1_body:
    bne.s   .Lsprite_blit_w32_gated_bit2_draw    | 014f30  6608
    lea     8(%a1),%a1                    | 014f32  43e90008
    bra.w   .Lsprite_blit_w32_gated_bit2_done    | 014f36  60000012
.Lsprite_blit_w32_gated_bit2_draw:
    and.w   %d1,(%a1)                     | 014f3a  c351
    or.w    %d2,(%a1)+                    | 014f3c  8559
    and.w   %d1,(%a1)                     | 014f3e  c351
    or.w    %d3,(%a1)+                    | 014f40  8759
    and.w   %d1,(%a1)                     | 014f42  c351
    or.w    %d4,(%a1)+                    | 014f44  8959
    and.w   %d1,(%a1)                     | 014f46  c351
    or.w    %d5,(%a1)+                    | 014f48  8b59
.Lsprite_blit_w32_gated_bit2_done:
    swap    %d1                           | 014f4a  4841
    MOVEL_ALL_ONES 0                      | 014f4c  203cffffffff
    move.w  (%a0)+,%d0                    | 014f52  3018
    ror.l   %d6,%d0                       | 014f54  ecb8
    and.w   %d1,%d0                       | 014f56  c041
    swap    %d2                           | 014f58  4842
    clr.l   %d1                           | 014f5a  4281
    move.w  (%a0)+,%d1                    | 014f5c  3218
    ror.l   %d6,%d1                       | 014f5e  ecb9
    or.w    %d2,%d1                       | 014f60  8242
    swap    %d3                           | 014f62  4843
    clr.l   %d2                           | 014f64  4282
    move.w  (%a0)+,%d2                    | 014f66  3418
    ror.l   %d6,%d2                       | 014f68  ecba
    or.w    %d3,%d2                       | 014f6a  8443
    swap    %d4                           | 014f6c  4844
    clr.l   %d3                           | 014f6e  4283
    move.w  (%a0)+,%d3                    | 014f70  3618
    ror.l   %d6,%d3                       | 014f72  ecbb
    or.w    %d4,%d3                       | 014f74  8644
    swap    %d5                           | 014f76  4845
    clr.l   %d4                           | 014f78  4284
    move.w  (%a0)+,%d4                    | 014f7a  3818
    ror.l   %d6,%d4                       | 014f7c  ecbc
    or.w    %d5,%d4                       | 014f7e  8845
sprite_blit_w32_gated_seg1_body_end:
    btst    #1,(%a2)                      | 014f80  0839000100006426 -> 08120001  SUBSTITUTED
    .globl  sprite_blit_w32_gated_seg2_body
sprite_blit_w32_gated_seg2_body:
    bne.s   .Lsprite_blit_w32_gated_bit1_draw    | 014f88  6608
    lea     8(%a1),%a1                    | 014f8a  43e90008
    bra.w   .Lsprite_blit_w32_gated_bit1_done    | 014f8e  60000012
.Lsprite_blit_w32_gated_bit1_draw:
    and.w   %d0,(%a1)                     | 014f92  c151
    or.w    %d1,(%a1)+                    | 014f94  8359
    and.w   %d0,(%a1)                     | 014f96  c151
    or.w    %d2,(%a1)+                    | 014f98  8559
    and.w   %d0,(%a1)                     | 014f9a  c151
    or.w    %d3,(%a1)+                    | 014f9c  8759
    and.w   %d0,(%a1)                     | 014f9e  c151
    or.w    %d4,(%a1)+                    | 014fa0  8959
.Lsprite_blit_w32_gated_bit1_done:
    swap    %d0                           | 014fa2  4840
    swap    %d1                           | 014fa4  4841
    swap    %d2                           | 014fa6  4842
    swap    %d3                           | 014fa8  4843
    swap    %d4                           | 014faa  4844
sprite_blit_w32_gated_seg2_body_end:
    btst    #0,(%a2)                      | 014fac  0839000000006426 -> 08120000  SUBSTITUTED
    .globl  sprite_blit_w32_gated_seg3_body
sprite_blit_w32_gated_seg3_body:
    bne.s   .Lsprite_blit_w32_gated_bit0_draw    | 014fb4  6608
    lea     6(%a1),%a1                    | 014fb6  43e90006
    bra.w   .Lsprite_blit_w32_gated_bit0_done    | 014fba  60000012
.Lsprite_blit_w32_gated_bit0_draw:
    and.w   %d0,(%a1)                     | 014fbe  c151
    or.w    %d1,(%a1)+                    | 014fc0  8359
    and.w   %d0,(%a1)                     | 014fc2  c151
    or.w    %d2,(%a1)+                    | 014fc4  8559
    and.w   %d0,(%a1)                     | 014fc6  c151
    or.w    %d3,(%a1)+                    | 014fc8  8759
    and.w   %d0,(%a1)                     | 014fca  c151
    or.w    %d4,(%a1)                     | 014fcc  8951
.Lsprite_blit_w32_gated_bit0_done:
    lea     138(%a1),%a1                  | 014fce  43e9008a
sprite_blit_w32_gated_seg3_body_end:
    dbf     %d7,sprite_blit_w32_gated_seg0_body  | 014fd2  51cfff32, less 4 a substitution
    .globl  sprite_blit_w32_gated_seg4_body
sprite_blit_w32_gated_seg4_body:
    rts                                   | 014fd6  4e75
sprite_blit_w32_gated_seg4_body_end:

| ------------------------------------------------------------------------------------------------
| sprite_blit_w48_gated: the original @ 0x1505e..0x15188

    .globl  sprite_blit_w48_gated_seg0_body
sprite_blit_w48_gated_seg0_body:
    MOVEL_ALL_ONES 1                      | 01505e  223cffffffff
    clr.l   %d2                           | 015064  4282
    clr.l   %d3                           | 015066  4283
    clr.l   %d4                           | 015068  4284
    clr.l   %d5                           | 01506a  4285
    move.w  (%a0)+,%d1                    | 01506c  3218
    move.w  (%a0)+,%d2                    | 01506e  3418
    move.w  (%a0)+,%d3                    | 015070  3618
    move.w  (%a0)+,%d4                    | 015072  3818
    move.w  (%a0)+,%d5                    | 015074  3a18
    ror.l   %d6,%d1                       | 015076  ecb9
    ror.l   %d6,%d2                       | 015078  ecba
    ror.l   %d6,%d3                       | 01507a  ecbb
    ror.l   %d6,%d4                       | 01507c  ecbc
    ror.l   %d6,%d5                       | 01507e  ecbd
sprite_blit_w48_gated_seg0_body_end:
    btst    #3,(%a2)                      | 015080  0839000300006426 -> 08120003  SUBSTITUTED
    .globl  sprite_blit_w48_gated_seg1_body
sprite_blit_w48_gated_seg1_body:
    bne.s   .Lsprite_blit_w48_gated_bit3_draw    | 015088  6608
    lea     8(%a1),%a1                    | 01508a  43e90008
    bra.w   .Lsprite_blit_w48_gated_bit3_done    | 01508e  60000012
.Lsprite_blit_w48_gated_bit3_draw:
    and.w   %d1,(%a1)                     | 015092  c351
    or.w    %d2,(%a1)+                    | 015094  8559
    and.w   %d1,(%a1)                     | 015096  c351
    or.w    %d3,(%a1)+                    | 015098  8759
    and.w   %d1,(%a1)                     | 01509a  c351
    or.w    %d4,(%a1)+                    | 01509c  8959
    and.w   %d1,(%a1)                     | 01509e  c351
    or.w    %d5,(%a1)+                    | 0150a0  8b59
.Lsprite_blit_w48_gated_bit3_done:
    swap    %d1                           | 0150a2  4841
    MOVEL_ALL_ONES 0                      | 0150a4  203cffffffff
    move.w  (%a0)+,%d0                    | 0150aa  3018
    ror.l   %d6,%d0                       | 0150ac  ecb8
    and.w   %d1,%d0                       | 0150ae  c041
    swap    %d2                           | 0150b0  4842
    clr.l   %d1                           | 0150b2  4281
    move.w  (%a0)+,%d1                    | 0150b4  3218
    ror.l   %d6,%d1                       | 0150b6  ecb9
    or.w    %d2,%d1                       | 0150b8  8242
    swap    %d3                           | 0150ba  4843
    clr.l   %d2                           | 0150bc  4282
    move.w  (%a0)+,%d2                    | 0150be  3418
    ror.l   %d6,%d2                       | 0150c0  ecba
    or.w    %d3,%d2                       | 0150c2  8443
    swap    %d4                           | 0150c4  4844
    clr.l   %d3                           | 0150c6  4283
    move.w  (%a0)+,%d3                    | 0150c8  3618
    ror.l   %d6,%d3                       | 0150ca  ecbb
    or.w    %d4,%d3                       | 0150cc  8644
    swap    %d5                           | 0150ce  4845
    clr.l   %d4                           | 0150d0  4284
    move.w  (%a0)+,%d4                    | 0150d2  3818
    ror.l   %d6,%d4                       | 0150d4  ecbc
    or.w    %d5,%d4                       | 0150d6  8845
sprite_blit_w48_gated_seg1_body_end:
    btst    #2,(%a2)                      | 0150d8  0839000200006426 -> 08120002  SUBSTITUTED
    .globl  sprite_blit_w48_gated_seg2_body
sprite_blit_w48_gated_seg2_body:
    bne.s   .Lsprite_blit_w48_gated_bit2_draw    | 0150e0  6608
    lea     8(%a1),%a1                    | 0150e2  43e90008
    bra.w   .Lsprite_blit_w48_gated_bit2_done    | 0150e6  60000012
.Lsprite_blit_w48_gated_bit2_draw:
    and.w   %d0,(%a1)                     | 0150ea  c151
    or.w    %d1,(%a1)+                    | 0150ec  8359
    and.w   %d0,(%a1)                     | 0150ee  c151
    or.w    %d2,(%a1)+                    | 0150f0  8559
    and.w   %d0,(%a1)                     | 0150f2  c151
    or.w    %d3,(%a1)+                    | 0150f4  8759
    and.w   %d0,(%a1)                     | 0150f6  c151
    or.w    %d4,(%a1)+                    | 0150f8  8959
.Lsprite_blit_w48_gated_bit2_done:
    swap    %d0                           | 0150fa  4840
    MOVEL_ALL_ONES 5                      | 0150fc  2a3cffffffff
    move.w  (%a0)+,%d5                    | 015102  3a18
    ror.l   %d6,%d5                       | 015104  ecbd
    and.w   %d0,%d5                       | 015106  ca40
    swap    %d1                           | 015108  4841
    clr.l   %d0                           | 01510a  4280
    move.w  (%a0)+,%d0                    | 01510c  3018
    ror.l   %d6,%d0                       | 01510e  ecb8
    or.w    %d1,%d0                       | 015110  8041
    swap    %d2                           | 015112  4842
    clr.l   %d1                           | 015114  4281
    move.w  (%a0)+,%d1                    | 015116  3218
    ror.l   %d6,%d1                       | 015118  ecb9
    or.w    %d2,%d1                       | 01511a  8242
    swap    %d3                           | 01511c  4843
    clr.l   %d2                           | 01511e  4282
    move.w  (%a0)+,%d2                    | 015120  3418
    ror.l   %d6,%d2                       | 015122  ecba
    or.w    %d3,%d2                       | 015124  8443
    swap    %d4                           | 015126  4844
    clr.l   %d3                           | 015128  4283
    move.w  (%a0)+,%d3                    | 01512a  3618
    ror.l   %d6,%d3                       | 01512c  ecbb
sprite_blit_w48_gated_seg2_body_end:
    btst    #1,(%a2)                      | 01512e  0839000100006426 -> 08120001  SUBSTITUTED
    .globl  sprite_blit_w48_gated_seg3_body
sprite_blit_w48_gated_seg3_body:
    bne.s   .Lsprite_blit_w48_gated_bit1_draw    | 015136  6608
    lea     8(%a1),%a1                    | 015138  43e90008
    bra.w   .Lsprite_blit_w48_gated_bit1_done    | 01513c  60000014
.Lsprite_blit_w48_gated_bit1_draw:
    or.w    %d4,%d3                       | 015140  8644
    and.w   %d5,(%a1)                     | 015142  cb51
    or.w    %d0,(%a1)+                    | 015144  8159
    and.w   %d5,(%a1)                     | 015146  cb51
    or.w    %d1,(%a1)+                    | 015148  8359
    and.w   %d5,(%a1)                     | 01514a  cb51
    or.w    %d2,(%a1)+                    | 01514c  8559
    and.w   %d5,(%a1)                     | 01514e  cb51
    or.w    %d3,(%a1)+                    | 015150  8759
.Lsprite_blit_w48_gated_bit1_done:
    swap    %d5                           | 015152  4845
    swap    %d0                           | 015154  4840
    swap    %d1                           | 015156  4841
    swap    %d2                           | 015158  4842
    swap    %d3                           | 01515a  4843
sprite_blit_w48_gated_seg3_body_end:
    btst    #0,(%a2)                      | 01515c  0839000000006426 -> 08120000  SUBSTITUTED
    .globl  sprite_blit_w48_gated_seg4_body
sprite_blit_w48_gated_seg4_body:
    bne.s   .Lsprite_blit_w48_gated_bit0_draw    | 015164  6608
    lea     6(%a1),%a1                    | 015166  43e90006
    bra.w   .Lsprite_blit_w48_gated_bit0_done    | 01516a  60000012
.Lsprite_blit_w48_gated_bit0_draw:
    and.w   %d5,(%a1)                     | 01516e  cb51
    or.w    %d0,(%a1)+                    | 015170  8159
    and.w   %d5,(%a1)                     | 015172  cb51
    or.w    %d1,(%a1)+                    | 015174  8359
    and.w   %d5,(%a1)                     | 015176  cb51
    or.w    %d2,(%a1)+                    | 015178  8559
    and.w   %d5,(%a1)                     | 01517a  cb51
    or.w    %d3,(%a1)                     | 01517c  8751
.Lsprite_blit_w48_gated_bit0_done:
    lea     130(%a1),%a1                  | 01517e  43e90082
sprite_blit_w48_gated_seg4_body_end:
    dbf     %d7,sprite_blit_w48_gated_seg0_body  | 015182  51cffeda, less 4 a substitution
    .globl  sprite_blit_w48_gated_seg5_body
sprite_blit_w48_gated_seg5_body:
    rts                                   | 015186  4e75
sprite_blit_w48_gated_seg5_body_end:

| ------------------------------------------------------------------------------------------------
| sprite_blit_w64_gated: the original @ 0x15230..0x153b2

    .globl  sprite_blit_w64_gated_seg0_body
sprite_blit_w64_gated_seg0_body:
    MOVEL_ALL_ONES 1                      | 015230  223cffffffff
    clr.l   %d2                           | 015236  4282
    clr.l   %d3                           | 015238  4283
    clr.l   %d4                           | 01523a  4284
    clr.l   %d5                           | 01523c  4285
    move.w  (%a0)+,%d1                    | 01523e  3218
    move.w  (%a0)+,%d2                    | 015240  3418
    move.w  (%a0)+,%d3                    | 015242  3618
    move.w  (%a0)+,%d4                    | 015244  3818
    move.w  (%a0)+,%d5                    | 015246  3a18
    ror.l   %d6,%d1                       | 015248  ecb9
    ror.l   %d6,%d2                       | 01524a  ecba
    ror.l   %d6,%d3                       | 01524c  ecbb
    ror.l   %d6,%d4                       | 01524e  ecbc
    ror.l   %d6,%d5                       | 015250  ecbd
sprite_blit_w64_gated_seg0_body_end:
    btst    #4,(%a2)                      | 015252  0839000400006426 -> 08120004  SUBSTITUTED
    .globl  sprite_blit_w64_gated_seg1_body
sprite_blit_w64_gated_seg1_body:
    bne.s   .Lsprite_blit_w64_gated_bit4_draw    | 01525a  6608
    lea     8(%a1),%a1                    | 01525c  43e90008
    bra.w   .Lsprite_blit_w64_gated_bit4_done    | 015260  60000012
.Lsprite_blit_w64_gated_bit4_draw:
    and.w   %d1,(%a1)                     | 015264  c351
    or.w    %d2,(%a1)+                    | 015266  8559
    and.w   %d1,(%a1)                     | 015268  c351
    or.w    %d3,(%a1)+                    | 01526a  8759
    and.w   %d1,(%a1)                     | 01526c  c351
    or.w    %d4,(%a1)+                    | 01526e  8959
    and.w   %d1,(%a1)                     | 015270  c351
    or.w    %d5,(%a1)+                    | 015272  8b59
.Lsprite_blit_w64_gated_bit4_done:
    swap    %d1                           | 015274  4841
    MOVEL_ALL_ONES 0                      | 015276  203cffffffff
    move.w  (%a0)+,%d0                    | 01527c  3018
    ror.l   %d6,%d0                       | 01527e  ecb8
    and.w   %d1,%d0                       | 015280  c041
    swap    %d2                           | 015282  4842
    clr.l   %d1                           | 015284  4281
    move.w  (%a0)+,%d1                    | 015286  3218
    ror.l   %d6,%d1                       | 015288  ecb9
    or.w    %d2,%d1                       | 01528a  8242
    swap    %d3                           | 01528c  4843
    clr.l   %d2                           | 01528e  4282
    move.w  (%a0)+,%d2                    | 015290  3418
    ror.l   %d6,%d2                       | 015292  ecba
    or.w    %d3,%d2                       | 015294  8443
    swap    %d4                           | 015296  4844
    clr.l   %d3                           | 015298  4283
    move.w  (%a0)+,%d3                    | 01529a  3618
    ror.l   %d6,%d3                       | 01529c  ecbb
    or.w    %d4,%d3                       | 01529e  8644
    swap    %d5                           | 0152a0  4845
    clr.l   %d4                           | 0152a2  4284
    move.w  (%a0)+,%d4                    | 0152a4  3818
    ror.l   %d6,%d4                       | 0152a6  ecbc
    or.w    %d5,%d4                       | 0152a8  8845
sprite_blit_w64_gated_seg1_body_end:
    btst    #3,(%a2)                      | 0152aa  0839000300006426 -> 08120003  SUBSTITUTED
    .globl  sprite_blit_w64_gated_seg2_body
sprite_blit_w64_gated_seg2_body:
    bne.s   .Lsprite_blit_w64_gated_bit3_draw    | 0152b2  6608
    lea     8(%a1),%a1                    | 0152b4  43e90008
    bra.w   .Lsprite_blit_w64_gated_bit3_done    | 0152b8  60000012
.Lsprite_blit_w64_gated_bit3_draw:
    and.w   %d0,(%a1)                     | 0152bc  c151
    or.w    %d1,(%a1)+                    | 0152be  8359
    and.w   %d0,(%a1)                     | 0152c0  c151
    or.w    %d2,(%a1)+                    | 0152c2  8559
    and.w   %d0,(%a1)                     | 0152c4  c151
    or.w    %d3,(%a1)+                    | 0152c6  8759
    and.w   %d0,(%a1)                     | 0152c8  c151
    or.w    %d4,(%a1)+                    | 0152ca  8959
.Lsprite_blit_w64_gated_bit3_done:
    swap    %d0                           | 0152cc  4840
    MOVEL_ALL_ONES 5                      | 0152ce  2a3cffffffff
    move.w  (%a0)+,%d5                    | 0152d4  3a18
    ror.l   %d6,%d5                       | 0152d6  ecbd
    and.w   %d0,%d5                       | 0152d8  ca40
    swap    %d1                           | 0152da  4841
    clr.l   %d0                           | 0152dc  4280
    move.w  (%a0)+,%d0                    | 0152de  3018
    ror.l   %d6,%d0                       | 0152e0  ecb8
    or.w    %d1,%d0                       | 0152e2  8041
    swap    %d2                           | 0152e4  4842
    clr.l   %d1                           | 0152e6  4281
    move.w  (%a0)+,%d1                    | 0152e8  3218
    ror.l   %d6,%d1                       | 0152ea  ecb9
    or.w    %d2,%d1                       | 0152ec  8242
    swap    %d3                           | 0152ee  4843
    clr.l   %d2                           | 0152f0  4282
    move.w  (%a0)+,%d2                    | 0152f2  3418
    ror.l   %d6,%d2                       | 0152f4  ecba
    or.w    %d3,%d2                       | 0152f6  8443
    swap    %d4                           | 0152f8  4844
    clr.l   %d3                           | 0152fa  4283
    move.w  (%a0)+,%d3                    | 0152fc  3618
    ror.l   %d6,%d3                       | 0152fe  ecbb
    or.w    %d4,%d3                       | 015300  8644
sprite_blit_w64_gated_seg2_body_end:
    btst    #2,(%a2)                      | 015302  0839000200006426 -> 08120002  SUBSTITUTED
    .globl  sprite_blit_w64_gated_seg3_body
sprite_blit_w64_gated_seg3_body:
    bne.s   .Lsprite_blit_w64_gated_bit2_draw    | 01530a  6608
    lea     8(%a1),%a1                    | 01530c  43e90008
    bra.w   .Lsprite_blit_w64_gated_bit2_done    | 015310  60000012
.Lsprite_blit_w64_gated_bit2_draw:
    and.w   %d5,(%a1)                     | 015314  cb51
    or.w    %d0,(%a1)+                    | 015316  8159
    and.w   %d5,(%a1)                     | 015318  cb51
    or.w    %d1,(%a1)+                    | 01531a  8359
    and.w   %d5,(%a1)                     | 01531c  cb51
    or.w    %d2,(%a1)+                    | 01531e  8559
    and.w   %d5,(%a1)                     | 015320  cb51
    or.w    %d3,(%a1)+                    | 015322  8759
.Lsprite_blit_w64_gated_bit2_done:
    swap    %d5                           | 015324  4845
    MOVEL_ALL_ONES 4                      | 015326  283cffffffff
    move.w  (%a0)+,%d4                    | 01532c  3818
    ror.l   %d6,%d4                       | 01532e  ecbc
    and.w   %d5,%d4                       | 015330  c845
    swap    %d0                           | 015332  4840
    clr.l   %d5                           | 015334  4285
    move.w  (%a0)+,%d5                    | 015336  3a18
    ror.l   %d6,%d5                       | 015338  ecbd
    or.w    %d0,%d5                       | 01533a  8a40
    swap    %d1                           | 01533c  4841
    clr.l   %d0                           | 01533e  4280
    move.w  (%a0)+,%d0                    | 015340  3018
    ror.l   %d6,%d0                       | 015342  ecb8
    or.w    %d1,%d0                       | 015344  8041
    swap    %d2                           | 015346  4842
    clr.l   %d1                           | 015348  4281
    move.w  (%a0)+,%d1                    | 01534a  3218
    ror.l   %d6,%d1                       | 01534c  ecb9
    or.w    %d2,%d1                       | 01534e  8242
    swap    %d3                           | 015350  4843
    clr.l   %d2                           | 015352  4282
    move.w  (%a0)+,%d2                    | 015354  3418
    ror.l   %d6,%d2                       | 015356  ecba
    or.w    %d3,%d2                       | 015358  8443
sprite_blit_w64_gated_seg3_body_end:
    btst    #1,(%a2)                      | 01535a  0839000100006426 -> 08120001  SUBSTITUTED
    .globl  sprite_blit_w64_gated_seg4_body
sprite_blit_w64_gated_seg4_body:
    bne.s   .Lsprite_blit_w64_gated_bit1_draw    | 015362  6608
    lea     8(%a1),%a1                    | 015364  43e90008
    bra.w   .Lsprite_blit_w64_gated_bit1_done    | 015368  60000012
.Lsprite_blit_w64_gated_bit1_draw:
    and.w   %d4,(%a1)                     | 01536c  c951
    or.w    %d5,(%a1)+                    | 01536e  8b59
    and.w   %d4,(%a1)                     | 015370  c951
    or.w    %d0,(%a1)+                    | 015372  8159
    and.w   %d4,(%a1)                     | 015374  c951
    or.w    %d1,(%a1)+                    | 015376  8359
    and.w   %d4,(%a1)                     | 015378  c951
    or.w    %d2,(%a1)+                    | 01537a  8559
.Lsprite_blit_w64_gated_bit1_done:
    swap    %d4                           | 01537c  4844
    swap    %d5                           | 01537e  4845
    swap    %d0                           | 015380  4840
    swap    %d1                           | 015382  4841
    swap    %d2                           | 015384  4842
sprite_blit_w64_gated_seg4_body_end:
    btst    #0,(%a2)                      | 015386  0839000000006426 -> 08120000  SUBSTITUTED
    .globl  sprite_blit_w64_gated_seg5_body
sprite_blit_w64_gated_seg5_body:
    bne.s   .Lsprite_blit_w64_gated_bit0_draw    | 01538e  6608
    lea     6(%a1),%a1                    | 015390  43e90006
    bra.w   .Lsprite_blit_w64_gated_bit0_done    | 015394  60000012
.Lsprite_blit_w64_gated_bit0_draw:
    and.w   %d4,(%a1)                     | 015398  c951
    or.w    %d5,(%a1)+                    | 01539a  8b59
    and.w   %d4,(%a1)                     | 01539c  c951
    or.w    %d0,(%a1)+                    | 01539e  8159
    and.w   %d4,(%a1)                     | 0153a0  c951
    or.w    %d1,(%a1)+                    | 0153a2  8359
    and.w   %d4,(%a1)                     | 0153a4  c951
    or.w    %d2,(%a1)                     | 0153a6  8551
.Lsprite_blit_w64_gated_bit0_done:
    lea     122(%a1),%a1                  | 0153a8  43e9007a
sprite_blit_w64_gated_seg5_body_end:
    dbf     %d7,sprite_blit_w64_gated_seg0_body  | 0153ac  51cffe82, less 4 a substitution
    .globl  sprite_blit_w64_gated_seg6_body
sprite_blit_w64_gated_seg6_body:
    rts                                   | 0153b0  4e75
sprite_blit_w64_gated_seg6_body_end:
