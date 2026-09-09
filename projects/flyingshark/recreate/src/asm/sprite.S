| sprite.S — the asm twin for the four UNCLIPPED masked sprite blitters, TRANSCRIBED from the
| original binary.
|
|   blit_sprite_rows_unclipped_asm  <- the original @ 0x153b2 / 0x15408 / 0x154a4 / 0x15586,
|                                      the C reference ../sprite.c's `blit_sprite_rows`
|
| WHAT A TWIN IS. The C in `../sprite.c` is byte-for-byte equivalent to the original —
| `test/test_sprite.py`'s differential against the Musashi oracle says so — so when a core costs
| three times the original, the fast version is not something to invent: it is in
| `../../out/prg_dis.txt`, and it has the one property no rewrite can promise.
|
|     An asm twin that faithfully transcribes the original's instruction sequence is 1.00x by
|     construction.
|
| The corollary matters as much: DO NOT IMPROVE ON THE ORIGINAL. A cleverer instruction is a
| divergence you now have to justify, in a file whose whole warrant is that it does not diverge.
| `projects/zynaps/recreate/src/asm/README.md` is where that recipe is written out at length; this
| is Flying Shark's first twin and it follows it unchanged.
|
| THE CHAIN OF EVIDENCE
|
|     original ==(test/test_sprite.py)== C core ==(test/test_asm_sprite.py)== asm twin
|
| Both links are byte-exact over the WHOLE image, so the twin is pinned to the original transitively
| and neither link has to be re-derived.
|
| WHY THIS ROUTINE AND NOT ANOTHER. `atari/profile.py ours` over a 1000-vblank window of the attract
| screen: `blit_sprite_row` is 53% of everything the machine does, at 1,334 cycles a row against the
| original's 413 — 3.2x, and 92% of the blitter's cycles go through the UNCLIPPED path (the gated
| one, which the clip ladders reach, was 53,398 cycles a frame against 582,591). So this twin covers
| the unclipped path and `../sprite.c` keeps the C for the gated one; `../STATUS.md` carries the row.
|
| WHAT IS TRANSCRIBED AND WHAT IS OURS. Everything between a `_body` label and its `_body_end` is the
| original's instruction sequence in order, one instruction per line, each carrying its original
| address and encoding in a `|` comment — and `test_asm_sprite.py`'s transcription pin compares those
| spans against the .PRG byte for byte. The prologue, the width ladder and the epilogue are OURS:
| they have no counterpart in the original, whose caller picks a body out of a jump table
| (`A_sprite_blit_tbl` @ 0x16396) with the registers already loaded.
|
| THE FOUR SUBSTITUTIONS THE C ABI FORCES, and they are the whole of the judgement exercised here:
|
|   a0 = the sprite cursor    the original's caller loads it absolutely; here it is image + src
|   a1 = the screen cursor    likewise: image + dst
|   d6 = the sub-word shift   the original's `ror.l %d6,%dn` rotates by d6 mod 64 and the C's
|                             `rotate_right32` masks the count to 31. A 32-bit rotate is cyclic
|                             mod 32, so the two agree for EVERY count, not merely for the 0..15 a
|                             screen x can produce.
|   d7 = the row count        `dbf %d7` makes d7's low word + 1 passes, which is exactly the C's
|                             `loop_passes(rows_minus_one + 1, COUNT_MASK_WORD)`.
|
| THE `bsr` BRACKET. Each body ends in the original's own `rts`, so the ladder CALLS it and the
| epilogue runs on the way back. One `bsr.w` (18 cycles) is what keeps every body byte-identical to
| the original's, closing `rts` included.
|
| REGISTERS: the original's, unchanged through all four bodies —
|   a0 = sprite cursor   a1 = screen cursor   d6 = the shift   d7 = the row count
|   d1..d5 = one source group's mask and four planes, rotated (d0 as well, from the second group on)
    .text

| GAS OPTIMISES AND THE ORIGINAL'S ASSEMBLER DID NOT. Every body preloads a register with all ones
| — `move.l #$ffffffff,dN`, 0x203c|N<<9 then the longword — and gas silently spells any such
| `move.l #imm,Dn` whose immediate fits in a byte as `moveq`: two bytes shorter, EIGHT CYCLES
| CHEAPER, and not what the original does. Cheaper is still a divergence, and this one would also
| put every body two bytes out of step with the .PRG and make the transcription pin unsatisfiable.
| This gas has no `.noopt`, so the eleven of them are laid down as the encoding they are.
    .macro  MOVEL_ALL_ONES  reg
    .word   0x203c + (\reg << 9)        | move.l #$ffffffff,d\reg
    .long   0xffffffff
    .endm

| ---- the C ABI frame ---------------------------------------------------------------------------
| void blit_sprite_rows_unclipped_asm(uint8_t *image, uint32_t src, uint32_t dst,
|                                     unsigned width_class, unsigned shift,
|                                     uint32_t rows_minus_one);
|
| ...which is `../sprite.c`'s `blit_sprite_rows` without its `gated` argument, because this twin is
| the ungated half of that function and the seam only routes the ungated call sites to it.
    .equ    SAVED, (6 * 4)                  | what the prologue pushes: %d2-%d7
    .equ    ARG_IMAGE,            4 + SAVED
    .equ    ARG_SRC,              8 + SAVED
    .equ    ARG_DST,             12 + SAVED
    .equ    ARG_WIDTH_CLASS,     16 + SAVED
    .equ    ARG_SHIFT,           20 + SAVED
    .equ    ARG_ROWS_MINUS_ONE,  24 + SAVED

        .globl  blit_sprite_rows_unclipped_asm
blit_sprite_rows_unclipped_asm:
        movem.l %d2-%d7,%sp@-
        movea.l ARG_IMAGE(%sp),%a0
        movea.l %a0,%a1
        adda.l  ARG_SRC(%sp),%a0
        adda.l  ARG_DST(%sp),%a1
        move.l  ARG_SHIFT(%sp),%d6
        move.l  ARG_ROWS_MINUS_ONE(%sp),%d7
        | THE LADDER'S DOMAIN IS 0..3, and the fall-through arm below therefore takes class 3 and
        | nothing else. That is a property of every call site rather than a bound this file imposes,
        | and it is provable rather than assumed: `sprite_blit_w16`..`w64` pass a literal, and
        | `dispatch_sprite_blit`'s only other route here is `SPRITE_BLIT_TABLE[table + width_class]`
        | with `entry->ladder == 0`. A class of 4 through the PLAIN table indexes 0 + 4, which is
        | `SPRITE_BLIT_TBL_CLIP_LEFT`'s first entry — an entry that HAS a ladder — so it goes to
        | `blit_sprite_clipped` and the C, never here; through the clip-right table it is
        | `SPRITE_BLIT_TBL_RESTORE`, which `../sprite.c` answers with the restore blitter before any
        | of this is called. So a class above 3 cannot arrive, and if one ever could the C would
        | draw `class + 2` screen groups where this ladder would draw five.
        move.l  ARG_WIDTH_CLASS(%sp),%d0
        beq.s   .Lwidth16
        subq.l  #1,%d0
        beq.s   .Lwidth32
        subq.l  #1,%d0
        beq.s   .Lwidth48
        bsr.w   sprite_blit_w64_body
        bra.s   .Ldone
.Lwidth48:
        bsr.w   sprite_blit_w48_body
        bra.s   .Ldone
.Lwidth32:
        bsr.w   sprite_blit_w32_body
        bra.s   .Ldone
.Lwidth16:
        bsr.w   sprite_blit_w16_body
.Ldone:
        movem.l %sp@+,%d2-%d7
        rts

| ---- the transcribed bodies --------------------------------------------------------------------
    .globl  sprite_blit_w16_body
sprite_blit_w16_body:
    MOVEL_ALL_ONES 1             | 0153b2  223cffffffff
    clr.l %d2                          | 0153b8  4282
    clr.l %d3                          | 0153ba  4283
    clr.l %d4                          | 0153bc  4284
    clr.l %d5                          | 0153be  4285
    move.w (%a0)+,%d1                  | 0153c0  3218
    move.w (%a0)+,%d2                  | 0153c2  3418
    move.w (%a0)+,%d3                  | 0153c4  3618
    move.w (%a0)+,%d4                  | 0153c6  3818
    move.w (%a0)+,%d5                  | 0153c8  3a18
    ror.l %d6,%d1                      | 0153ca  ecb9
    ror.l %d6,%d2                      | 0153cc  ecba
    ror.l %d6,%d3                      | 0153ce  ecbb
    ror.l %d6,%d4                      | 0153d0  ecbc
    ror.l %d6,%d5                      | 0153d2  ecbd
    and.w %d1,(%a1)                    | 0153d4  c351
    or.w %d2,(%a1)+                    | 0153d6  8559
    and.w %d1,(%a1)                    | 0153d8  c351
    or.w %d3,(%a1)+                    | 0153da  8759
    and.w %d1,(%a1)                    | 0153dc  c351
    or.w %d4,(%a1)+                    | 0153de  8959
    and.w %d1,(%a1)                    | 0153e0  c351
    or.w %d5,(%a1)+                    | 0153e2  8b59
    swap %d1                           | 0153e4  4841
    swap %d2                           | 0153e6  4842
    swap %d3                           | 0153e8  4843
    swap %d4                           | 0153ea  4844
    swap %d5                           | 0153ec  4845
    and.w %d1,(%a1)                    | 0153ee  c351
    or.w %d2,(%a1)+                    | 0153f0  8559
    and.w %d1,(%a1)                    | 0153f2  c351
    or.w %d3,(%a1)+                    | 0153f4  8759
    and.w %d1,(%a1)                    | 0153f6  c351
    or.w %d4,(%a1)+                    | 0153f8  8959
    and.w %d1,(%a1)                    | 0153fa  c351
    or.w %d5,(%a1)                     | 0153fc  8b51
    lea 146(%a1),%a1                   | 0153fe  43e90092
    dbf %d7,sprite_blit_w16_body       | 015402  51cfffae
    rts                                | 015406  4e75
sprite_blit_w16_body_end:

    .globl  sprite_blit_w32_body
sprite_blit_w32_body:
    MOVEL_ALL_ONES 1             | 015408  223cffffffff
    clr.l %d2                          | 01540e  4282
    clr.l %d3                          | 015410  4283
    clr.l %d4                          | 015412  4284
    clr.l %d5                          | 015414  4285
    move.w (%a0)+,%d1                  | 015416  3218
    move.w (%a0)+,%d2                  | 015418  3418
    move.w (%a0)+,%d3                  | 01541a  3618
    move.w (%a0)+,%d4                  | 01541c  3818
    move.w (%a0)+,%d5                  | 01541e  3a18
    ror.l %d6,%d1                      | 015420  ecb9
    ror.l %d6,%d2                      | 015422  ecba
    ror.l %d6,%d3                      | 015424  ecbb
    ror.l %d6,%d4                      | 015426  ecbc
    ror.l %d6,%d5                      | 015428  ecbd
    and.w %d1,(%a1)                    | 01542a  c351
    or.w %d2,(%a1)+                    | 01542c  8559
    and.w %d1,(%a1)                    | 01542e  c351
    or.w %d3,(%a1)+                    | 015430  8759
    and.w %d1,(%a1)                    | 015432  c351
    or.w %d4,(%a1)+                    | 015434  8959
    and.w %d1,(%a1)                    | 015436  c351
    or.w %d5,(%a1)+                    | 015438  8b59
    swap %d1                           | 01543a  4841
    MOVEL_ALL_ONES 0             | 01543c  203cffffffff
    move.w (%a0)+,%d0                  | 015442  3018
    ror.l %d6,%d0                      | 015444  ecb8
    and.w %d1,%d0                      | 015446  c041
    swap %d2                           | 015448  4842
    clr.l %d1                          | 01544a  4281
    move.w (%a0)+,%d1                  | 01544c  3218
    ror.l %d6,%d1                      | 01544e  ecb9
    or.w %d2,%d1                       | 015450  8242
    swap %d3                           | 015452  4843
    clr.l %d2                          | 015454  4282
    move.w (%a0)+,%d2                  | 015456  3418
    ror.l %d6,%d2                      | 015458  ecba
    or.w %d3,%d2                       | 01545a  8443
    swap %d4                           | 01545c  4844
    clr.l %d3                          | 01545e  4283
    move.w (%a0)+,%d3                  | 015460  3618
    ror.l %d6,%d3                      | 015462  ecbb
    or.w %d4,%d3                       | 015464  8644
    swap %d5                           | 015466  4845
    clr.l %d4                          | 015468  4284
    move.w (%a0)+,%d4                  | 01546a  3818
    ror.l %d6,%d4                      | 01546c  ecbc
    or.w %d5,%d4                       | 01546e  8845
    and.w %d0,(%a1)                    | 015470  c151
    or.w %d1,(%a1)+                    | 015472  8359
    and.w %d0,(%a1)                    | 015474  c151
    or.w %d2,(%a1)+                    | 015476  8559
    and.w %d0,(%a1)                    | 015478  c151
    or.w %d3,(%a1)+                    | 01547a  8759
    and.w %d0,(%a1)                    | 01547c  c151
    or.w %d4,(%a1)+                    | 01547e  8959
    swap %d0                           | 015480  4840
    swap %d1                           | 015482  4841
    swap %d2                           | 015484  4842
    swap %d3                           | 015486  4843
    swap %d4                           | 015488  4844
    and.w %d0,(%a1)                    | 01548a  c151
    or.w %d1,(%a1)+                    | 01548c  8359
    and.w %d0,(%a1)                    | 01548e  c151
    or.w %d2,(%a1)+                    | 015490  8559
    and.w %d0,(%a1)                    | 015492  c151
    or.w %d3,(%a1)+                    | 015494  8759
    and.w %d0,(%a1)                    | 015496  c151
    or.w %d4,(%a1)                     | 015498  8951
    lea 138(%a1),%a1                   | 01549a  43e9008a
    dbf %d7,sprite_blit_w32_body       | 01549e  51cfff68
    rts                                | 0154a2  4e75
sprite_blit_w32_body_end:

    .globl  sprite_blit_w48_body
sprite_blit_w48_body:
    MOVEL_ALL_ONES 1             | 0154a4  223cffffffff
    clr.l %d2                          | 0154aa  4282
    clr.l %d3                          | 0154ac  4283
    clr.l %d4                          | 0154ae  4284
    clr.l %d5                          | 0154b0  4285
    move.w (%a0)+,%d1                  | 0154b2  3218
    move.w (%a0)+,%d2                  | 0154b4  3418
    move.w (%a0)+,%d3                  | 0154b6  3618
    move.w (%a0)+,%d4                  | 0154b8  3818
    move.w (%a0)+,%d5                  | 0154ba  3a18
    ror.l %d6,%d1                      | 0154bc  ecb9
    ror.l %d6,%d2                      | 0154be  ecba
    ror.l %d6,%d3                      | 0154c0  ecbb
    ror.l %d6,%d4                      | 0154c2  ecbc
    ror.l %d6,%d5                      | 0154c4  ecbd
    and.w %d1,(%a1)                    | 0154c6  c351
    or.w %d2,(%a1)+                    | 0154c8  8559
    and.w %d1,(%a1)                    | 0154ca  c351
    or.w %d3,(%a1)+                    | 0154cc  8759
    and.w %d1,(%a1)                    | 0154ce  c351
    or.w %d4,(%a1)+                    | 0154d0  8959
    and.w %d1,(%a1)                    | 0154d2  c351
    or.w %d5,(%a1)+                    | 0154d4  8b59
    swap %d1                           | 0154d6  4841
    MOVEL_ALL_ONES 0             | 0154d8  203cffffffff
    move.w (%a0)+,%d0                  | 0154de  3018
    ror.l %d6,%d0                      | 0154e0  ecb8
    and.w %d1,%d0                      | 0154e2  c041
    swap %d2                           | 0154e4  4842
    clr.l %d1                          | 0154e6  4281
    move.w (%a0)+,%d1                  | 0154e8  3218
    ror.l %d6,%d1                      | 0154ea  ecb9
    or.w %d2,%d1                       | 0154ec  8242
    swap %d3                           | 0154ee  4843
    clr.l %d2                          | 0154f0  4282
    move.w (%a0)+,%d2                  | 0154f2  3418
    ror.l %d6,%d2                      | 0154f4  ecba
    or.w %d3,%d2                       | 0154f6  8443
    swap %d4                           | 0154f8  4844
    clr.l %d3                          | 0154fa  4283
    move.w (%a0)+,%d3                  | 0154fc  3618
    ror.l %d6,%d3                      | 0154fe  ecbb
    or.w %d4,%d3                       | 015500  8644
    swap %d5                           | 015502  4845
    clr.l %d4                          | 015504  4284
    move.w (%a0)+,%d4                  | 015506  3818
    ror.l %d6,%d4                      | 015508  ecbc
    or.w %d5,%d4                       | 01550a  8845
    and.w %d0,(%a1)                    | 01550c  c151
    or.w %d1,(%a1)+                    | 01550e  8359
    and.w %d0,(%a1)                    | 015510  c151
    or.w %d2,(%a1)+                    | 015512  8559
    and.w %d0,(%a1)                    | 015514  c151
    or.w %d3,(%a1)+                    | 015516  8759
    and.w %d0,(%a1)                    | 015518  c151
    or.w %d4,(%a1)+                    | 01551a  8959
    swap %d0                           | 01551c  4840
    MOVEL_ALL_ONES 5             | 01551e  2a3cffffffff
    move.w (%a0)+,%d5                  | 015524  3a18
    ror.l %d6,%d5                      | 015526  ecbd
    and.w %d0,%d5                      | 015528  ca40
    swap %d1                           | 01552a  4841
    clr.l %d0                          | 01552c  4280
    move.w (%a0)+,%d0                  | 01552e  3018
    ror.l %d6,%d0                      | 015530  ecb8
    or.w %d1,%d0                       | 015532  8041
    swap %d2                           | 015534  4842
    clr.l %d1                          | 015536  4281
    move.w (%a0)+,%d1                  | 015538  3218
    ror.l %d6,%d1                      | 01553a  ecb9
    or.w %d2,%d1                       | 01553c  8242
    swap %d3                           | 01553e  4843
    clr.l %d2                          | 015540  4282
    move.w (%a0)+,%d2                  | 015542  3418
    ror.l %d6,%d2                      | 015544  ecba
    or.w %d3,%d2                       | 015546  8443
    swap %d4                           | 015548  4844
    clr.l %d3                          | 01554a  4283
    move.w (%a0)+,%d3                  | 01554c  3618
    ror.l %d6,%d3                      | 01554e  ecbb
    or.w %d4,%d3                       | 015550  8644
    and.w %d5,(%a1)                    | 015552  cb51
    or.w %d0,(%a1)+                    | 015554  8159
    and.w %d5,(%a1)                    | 015556  cb51
    or.w %d1,(%a1)+                    | 015558  8359
    and.w %d5,(%a1)                    | 01555a  cb51
    or.w %d2,(%a1)+                    | 01555c  8559
    and.w %d5,(%a1)                    | 01555e  cb51
    or.w %d3,(%a1)+                    | 015560  8759
    swap %d5                           | 015562  4845
    swap %d0                           | 015564  4840
    swap %d1                           | 015566  4841
    swap %d2                           | 015568  4842
    swap %d3                           | 01556a  4843
    and.w %d5,(%a1)                    | 01556c  cb51
    or.w %d0,(%a1)+                    | 01556e  8159
    and.w %d5,(%a1)                    | 015570  cb51
    or.w %d1,(%a1)+                    | 015572  8359
    and.w %d5,(%a1)                    | 015574  cb51
    or.w %d2,(%a1)+                    | 015576  8559
    and.w %d5,(%a1)                    | 015578  cb51
    or.w %d3,(%a1)                     | 01557a  8751
    lea 130(%a1),%a1                   | 01557c  43e90082
    dbf %d7,sprite_blit_w48_body       | 015580  51cfff22
    rts                                | 015584  4e75
sprite_blit_w48_body_end:

    .globl  sprite_blit_w64_body
sprite_blit_w64_body:
    MOVEL_ALL_ONES 1             | 015586  223cffffffff
    clr.l %d2                          | 01558c  4282
    clr.l %d3                          | 01558e  4283
    clr.l %d4                          | 015590  4284
    clr.l %d5                          | 015592  4285
    move.w (%a0)+,%d1                  | 015594  3218
    move.w (%a0)+,%d2                  | 015596  3418
    move.w (%a0)+,%d3                  | 015598  3618
    move.w (%a0)+,%d4                  | 01559a  3818
    move.w (%a0)+,%d5                  | 01559c  3a18
    ror.l %d6,%d1                      | 01559e  ecb9
    ror.l %d6,%d2                      | 0155a0  ecba
    ror.l %d6,%d3                      | 0155a2  ecbb
    ror.l %d6,%d4                      | 0155a4  ecbc
    ror.l %d6,%d5                      | 0155a6  ecbd
    and.w %d1,(%a1)                    | 0155a8  c351
    or.w %d2,(%a1)+                    | 0155aa  8559
    and.w %d1,(%a1)                    | 0155ac  c351
    or.w %d3,(%a1)+                    | 0155ae  8759
    and.w %d1,(%a1)                    | 0155b0  c351
    or.w %d4,(%a1)+                    | 0155b2  8959
    and.w %d1,(%a1)                    | 0155b4  c351
    or.w %d5,(%a1)+                    | 0155b6  8b59
    swap %d1                           | 0155b8  4841
    MOVEL_ALL_ONES 0             | 0155ba  203cffffffff
    move.w (%a0)+,%d0                  | 0155c0  3018
    ror.l %d6,%d0                      | 0155c2  ecb8
    and.w %d1,%d0                      | 0155c4  c041
    swap %d2                           | 0155c6  4842
    clr.l %d1                          | 0155c8  4281
    move.w (%a0)+,%d1                  | 0155ca  3218
    ror.l %d6,%d1                      | 0155cc  ecb9
    or.w %d2,%d1                       | 0155ce  8242
    swap %d3                           | 0155d0  4843
    clr.l %d2                          | 0155d2  4282
    move.w (%a0)+,%d2                  | 0155d4  3418
    ror.l %d6,%d2                      | 0155d6  ecba
    or.w %d3,%d2                       | 0155d8  8443
    swap %d4                           | 0155da  4844
    clr.l %d3                          | 0155dc  4283
    move.w (%a0)+,%d3                  | 0155de  3618
    ror.l %d6,%d3                      | 0155e0  ecbb
    or.w %d4,%d3                       | 0155e2  8644
    swap %d5                           | 0155e4  4845
    clr.l %d4                          | 0155e6  4284
    move.w (%a0)+,%d4                  | 0155e8  3818
    ror.l %d6,%d4                      | 0155ea  ecbc
    or.w %d5,%d4                       | 0155ec  8845
    and.w %d0,(%a1)                    | 0155ee  c151
    or.w %d1,(%a1)+                    | 0155f0  8359
    and.w %d0,(%a1)                    | 0155f2  c151
    or.w %d2,(%a1)+                    | 0155f4  8559
    and.w %d0,(%a1)                    | 0155f6  c151
    or.w %d3,(%a1)+                    | 0155f8  8759
    and.w %d0,(%a1)                    | 0155fa  c151
    or.w %d4,(%a1)+                    | 0155fc  8959
    swap %d0                           | 0155fe  4840
    MOVEL_ALL_ONES 5             | 015600  2a3cffffffff
    move.w (%a0)+,%d5                  | 015606  3a18
    ror.l %d6,%d5                      | 015608  ecbd
    and.w %d0,%d5                      | 01560a  ca40
    swap %d1                           | 01560c  4841
    clr.l %d0                          | 01560e  4280
    move.w (%a0)+,%d0                  | 015610  3018
    ror.l %d6,%d0                      | 015612  ecb8
    or.w %d1,%d0                       | 015614  8041
    swap %d2                           | 015616  4842
    clr.l %d1                          | 015618  4281
    move.w (%a0)+,%d1                  | 01561a  3218
    ror.l %d6,%d1                      | 01561c  ecb9
    or.w %d2,%d1                       | 01561e  8242
    swap %d3                           | 015620  4843
    clr.l %d2                          | 015622  4282
    move.w (%a0)+,%d2                  | 015624  3418
    ror.l %d6,%d2                      | 015626  ecba
    or.w %d3,%d2                       | 015628  8443
    swap %d4                           | 01562a  4844
    clr.l %d3                          | 01562c  4283
    move.w (%a0)+,%d3                  | 01562e  3618
    ror.l %d6,%d3                      | 015630  ecbb
    or.w %d4,%d3                       | 015632  8644
    and.w %d5,(%a1)                    | 015634  cb51
    or.w %d0,(%a1)+                    | 015636  8159
    and.w %d5,(%a1)                    | 015638  cb51
    or.w %d1,(%a1)+                    | 01563a  8359
    and.w %d5,(%a1)                    | 01563c  cb51
    or.w %d2,(%a1)+                    | 01563e  8559
    and.w %d5,(%a1)                    | 015640  cb51
    or.w %d3,(%a1)+                    | 015642  8759
    swap %d5                           | 015644  4845
    MOVEL_ALL_ONES 4             | 015646  283cffffffff
    move.w (%a0)+,%d4                  | 01564c  3818
    ror.l %d6,%d4                      | 01564e  ecbc
    and.w %d5,%d4                      | 015650  c845
    swap %d0                           | 015652  4840
    clr.l %d5                          | 015654  4285
    move.w (%a0)+,%d5                  | 015656  3a18
    ror.l %d6,%d5                      | 015658  ecbd
    or.w %d0,%d5                       | 01565a  8a40
    swap %d1                           | 01565c  4841
    clr.l %d0                          | 01565e  4280
    move.w (%a0)+,%d0                  | 015660  3018
    ror.l %d6,%d0                      | 015662  ecb8
    or.w %d1,%d0                       | 015664  8041
    swap %d2                           | 015666  4842
    clr.l %d1                          | 015668  4281
    move.w (%a0)+,%d1                  | 01566a  3218
    ror.l %d6,%d1                      | 01566c  ecb9
    or.w %d2,%d1                       | 01566e  8242
    swap %d3                           | 015670  4843
    clr.l %d2                          | 015672  4282
    move.w (%a0)+,%d2                  | 015674  3418
    ror.l %d6,%d2                      | 015676  ecba
    or.w %d3,%d2                       | 015678  8443
    and.w %d4,(%a1)                    | 01567a  c951
    or.w %d5,(%a1)+                    | 01567c  8b59
    and.w %d4,(%a1)                    | 01567e  c951
    or.w %d0,(%a1)+                    | 015680  8159
    and.w %d4,(%a1)                    | 015682  c951
    or.w %d1,(%a1)+                    | 015684  8359
    and.w %d4,(%a1)                    | 015686  c951
    or.w %d2,(%a1)+                    | 015688  8559
    swap %d4                           | 01568a  4844
    swap %d5                           | 01568c  4845
    swap %d0                           | 01568e  4840
    swap %d1                           | 015690  4841
    swap %d2                           | 015692  4842
    and.w %d4,(%a1)                    | 015694  c951
    or.w %d5,(%a1)+                    | 015696  8b59
    and.w %d4,(%a1)                    | 015698  c951
    or.w %d0,(%a1)+                    | 01569a  8159
    and.w %d4,(%a1)                    | 01569c  c951
    or.w %d1,(%a1)+                    | 01569e  8359
    and.w %d4,(%a1)                    | 0156a0  c951
    or.w %d2,(%a1)                     | 0156a2  8551
    lea 122(%a1),%a1                   | 0156a4  43e9007a
    dbf %d7,sprite_blit_w64_body       | 0156a8  51cffedc
    rts                                | 0156ac  4e75
sprite_blit_w64_body_end:

