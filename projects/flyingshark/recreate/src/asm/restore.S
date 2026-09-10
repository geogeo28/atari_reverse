| restore.S — the asm twin for the FIVE restore blitters and the ring-seam copy, TRANSCRIBED from
| the original binary.
|
|   restore_blit_rows_asm      <- the original @ 0x14d58 / 0x14d6a / 0x14d80 / 0x14d9a / 0x14db8,
|                                 the C reference ../sprite.c's `restore_blit_rows`
|   restore_blit_rows_regs     <- the same ladder and bodies, entered with the registers loaded.
|                                 The C-ABI entry above is what the SUITE drives; this is what the
|                                 GAME calls (see "THE REGISTER-ABI ENTRY" below)
|   scroll_wrap_copy_1280_asm  <- the original @ 0x156ae, the C reference ../sprite.c's
|                                 `scroll_wrap_copy_1280`. C ABI only: its whole frame is 56 cycles
|                                 at ~1 call a frame, so a second entry would buy about fifty
|                                 cycles a frame and cost a name
|
| `sprite.S` is this directory's first twin and its header carries the recipe; ../README.md carries
| the six checks a twin needs. What follows is only what is THIS file's own.
|
| WHY THESE ROUTINES. `atari/profile.py`, matched 75-sprite frames, ours against the shipped binary:
| the restore replay is 149,634 profiled cycles a frame against 73,647, the single largest item in
| the frame — 2,138 cycles a call against the original's 862, at ~70 calls. The cause is
| `include/common.h`'s `copy_longs`, which INDEXES the image (`%aN@(0,%aM:l)`) because it takes the
| cursors as offsets and so cannot postincrement, and which `-funroll-loops` peels with a `__mulsi3`
| CALL per restore. The original does the same work in `move.l (a0)+,(a1)+`. The ring-seam copy is
| the same C helper over 80 longwords in one run, at ~1 call a frame.
|
| WHAT IS TRANSCRIBED AND WHAT IS OURS. Everything between a `_body` label and its `_body_end` is the
| original's instruction sequence, and `test/test_asm_restore.py`'s transcription pin plus
| `atari/assert_twin_bytes.py` compare those spans against the .PRG byte for byte. The C-ABI
| prologue, the width ladder and the epilogue are OURS: they have no counterpart in the original,
| whose caller enters a body out of a jump table (`A_restore_blit_tbl` @ 0x163c6) with a0/a1/d7
| already loaded.
|
| ONE MACRO FOR FIVE BODIES, WHICH IS NOT AN IMPROVEMENT ON THE ORIGINAL. The five differ in exactly
| one number — how many longwords a row is — and the original's own `lea` displacement is the rest of
| a 160-byte row after that run: 152/144/136/128/120 for 2/4/6/8/10 longs. Writing the five out
| longhand would be thirty lines of one instruction and five chances to mistype a displacement; the
| macro emits the same bytes and the byte pin is what proves it. That pin is also what keeps the two
| `.equ` below honest: a wrong SCREEN_ROW_BYTES changes the `lea` encoding and reddens by address.
|
| REGISTERS: the original's, unchanged through all six bodies —
|   a0 = source cursor   a1 = destination cursor   d7 = the row count (`dbf`, restore bodies only)
    .text

| ---- the geometry the bodies' `lea` displacements are made of -----------------------------------
| These mirror `../../include/sprite.h`'s SCREEN_ROW_BYTES and `include/common.h`'s LONG_BYTES. They
| are spelt again rather than included because a `.S` cannot include a header of C prototypes, and
| they are PINNED rather than trusted: both feed a `lea` inside a transcribed span, so a value that
| drifted from the header's would stop matching the original's bytes.
|
| EVERY `.equ` IN THIS FILE IS PREFIXED, these two included. `kit.mk` links every `.S` in this directory into
| ONE blob with one flat symbol table, and a gas `.equ` is a file-local ABSOLUTE symbol — two files
| defining one name do not collide at link, they both land in `twins.elf` and a pin resolving the
| name gets whichever `nm` printed last. That is the silent failure kit.mk records from a case where
| it happened, so the rule here is a prefix with no exception to argue about rather than a judgement
| per name.
    .equ    RESTORE_SCREEN_ROW_BYTES, 160
    .equ    RESTORE_LONG_BYTES, 4
| One more width class is one more 16-pixel screen group, which is 8 bytes, which is this many
| longwords — the step the ladder below walks and the difference between any two adjacent bodies.
    .equ    RESTORE_LONGS_PER_GROUP, 2

| One restore body: `longs` x `move.l (%a0)+,(%a1)+` (22d8 each), then the `lea` on each cursor that
| completes a 160-byte screen row (41e8/43e9 + the displacement), then the `dbf` back to the top and
| the original's own `rts`.
    .macro  RESTORE_BODY  name, longs
    .globl  \name\()_body
\name\()_body:
    .rept   \longs
    move.l  (%a0)+,(%a1)+
    .endr
    lea     (RESTORE_SCREEN_ROW_BYTES - \longs * RESTORE_LONG_BYTES)(%a0),%a0
    lea     (RESTORE_SCREEN_ROW_BYTES - \longs * RESTORE_LONG_BYTES)(%a1),%a1
    dbf     %d7,\name\()_body
    rts
\name\()_body_end:
    .endm

| ---- the C ABI frame ---------------------------------------------------------------------------
| void restore_blit_rows_asm(uint8_t *image, uint32_t src, uint32_t dst, uint32_t rows_minus_one,
|                            uint32_t longs_per_row);
|
| ...which is `../sprite.c`'s `restore_blit_rows` argument for argument, so the seam there is a
| substitution and not a re-ordering. `../../include/sprite.h` declares it and is the one place the
| signature lives.
|
| THE THREE SUBSTITUTIONS THE C ABI FORCES:
|
|   a0 = the source cursor       the original's caller loads it absolutely; here it is image + src
|   a1 = the destination cursor  likewise: image + dst
|   d7 = the row count           `dbf %d7` makes d7's low word + 1 passes, which is exactly the C's
|                                `loop_passes(rows_minus_one + 1, COUNT_MASK_WORD)`.
|
| THE LADDER BRANCHES, IT DOES NOT CALL. Each body ends in the original's own `rts` — that closing
| instruction is inside the transcribed span and cannot be dropped — so the ladder `bra`s to a body
| and lets that `rts` return to whoever entered the ladder: the C-ABI entry's epilogue below, or the
| game. The same shape, and for the same reason, as `sprite.S`'s.
    .equ    RESTORE_SAVED, (1 * 4)          | what the prologue pushes: %d7, the only callee-saved
                                            | register any body touches
    .equ    RESTORE_ARG_IMAGE,            4 + RESTORE_SAVED
    .equ    RESTORE_ARG_SRC,              8 + RESTORE_SAVED
    .equ    RESTORE_ARG_DST,             12 + RESTORE_SAVED
    .equ    RESTORE_ARG_ROWS_MINUS_ONE,  16 + RESTORE_SAVED
    .equ    RESTORE_ARG_LONGS_PER_ROW,   20 + RESTORE_SAVED

        .globl  restore_blit_rows_asm
restore_blit_rows_asm:
        move.l  %d7,%sp@-
        movea.l RESTORE_ARG_IMAGE(%sp),%a0
        movea.l %a0,%a1
        adda.l  RESTORE_ARG_SRC(%sp),%a0
        adda.l  RESTORE_ARG_DST(%sp),%a1
        move.l  RESTORE_ARG_ROWS_MINUS_ONE(%sp),%d7
        move.l  RESTORE_ARG_LONGS_PER_ROW(%sp),%d0
        bsr.s   restore_blit_rows_regs
        move.l  %sp@+,%d7
        rts

| ---- THE REGISTER-ABI ENTRY, and it is the one the TARGET BUILD CALLS ---------------------------
| Same ladder, same bodies, entered with the values already in the original's own registers:
|
|   a0 = the source cursor (image + src)   a1 = the destination cursor (image + dst)
|   d7 = the row count    d0 = the longwords per row, consumed by the ladder
|
| Nothing else is touched — no body writes a data register but %d0 and %d7 — so a C caller reaching
| this entry saves not only its own argument pushes but the whole `%d7` push/pop and the four
| argument loads above. `sprite.S`'s twin carries the argument for both entries at length; the same
| one applies here, and the suite still drives the C-ABI entry above, which reaches this ladder
| through the `bsr.s`.
        .globl  restore_blit_rows_regs
restore_blit_rows_regs:
        | THE LADDER'S DOMAIN IS 2, 4, 6, 8 AND 10 LONGWORDS, and the fall-through arm below
        | therefore takes 10 and nothing else. That is a property of every call site rather than a
        | bound this file imposes: `../sprite.c` reaches `restore_blit_rows` from seven places and
        | every one of them passes a RESTORE_LONGS_W* constant — the five `restore_blit_w*` entries
        | pass their own, `dispatch_sprite_blit`'s class-4 arm passes RESTORE_LONGS_W32, and
        | `restore_blit` passes one of the five out of its own table, whose index the caller bounds
        | (a class the five-entry table cannot answer is what its host-only assert names).
        |
        | AND IF ONE EVER COULD ARRIVE, this ladder and the C would DIVERGE rather than agree: the C
        | copies `longs_per_row` longwords a row for any value, where every arm below is one of the
        | five. That assert is `#ifdef RECREATE_HOST_DIFFERENTIAL`, so on target it is not there to
        | stop it — the same shape, and the same standing bet, as `sprite.S`'s class-above-3 note.
        subq.l  #RESTORE_LONGS_PER_GROUP,%d0
        beq.s   .Lw16
        subq.l  #RESTORE_LONGS_PER_GROUP,%d0
        beq.s   .Lw32
        subq.l  #RESTORE_LONGS_PER_GROUP,%d0
        beq.s   .Lw48
        subq.l  #RESTORE_LONGS_PER_GROUP,%d0
        beq.s   .Lw64
        bra.w   restore_blit_w80_body
.Lw64:
        bra.w   restore_blit_w64_body
.Lw48:
        bra.w   restore_blit_w48_body
.Lw32:
        bra.w   restore_blit_w32_body
.Lw16:
        bra.w   restore_blit_w16_body

| ---- the five transcribed restore bodies -------------------------------------------------------
    RESTORE_BODY  restore_blit_w16,  2      | 014d58..014d69: 22d8 x2, lea 152, dbf, rts
    RESTORE_BODY  restore_blit_w32,  4      | 014d6a..014d7f: 22d8 x4, lea 144, dbf, rts
    RESTORE_BODY  restore_blit_w48,  6      | 014d80..014d99: 22d8 x6, lea 136, dbf, rts
    RESTORE_BODY  restore_blit_w64,  8      | 014d9a..014db7: 22d8 x8, lea 128, dbf, rts
    RESTORE_BODY  restore_blit_w80, 10      | 014db8..014dd9: 22d8 x10, lea 120, dbf, rts

| ---- the ring-seam copy ------------------------------------------------------------------------
| void scroll_wrap_copy_1280_asm(uint8_t *image, uint32_t src, uint32_t dst);
|
| 80 longwords in ONE run, no row structure and no loop — the original is 80 x `move.l (a0)+,(a1)+`
| and an `rts`, `bsr`ed four times per seam by `render_frame` @ 0x14464.
|
| NO `bsr` BRACKET HERE, unlike the restore entry above: this prologue touches no callee-saved
| register, so there is no epilogue for a body to come back to. The prologue FALLS THROUGH into the
| body and the original's own `rts` returns straight to the C caller — four instructions of glue and
| nothing else.
    .equ    SEAM_ARG_IMAGE,  4
    .equ    SEAM_ARG_SRC,    8
    .equ    SEAM_ARG_DST,   12
| `../../include/sprite.h`'s SEAM_COPY_LONGS: two whole screen rows.
    .equ    SEAM_COPY_LONGS, 80

        .globl  scroll_wrap_copy_1280_asm
scroll_wrap_copy_1280_asm:
        movea.l SEAM_ARG_IMAGE(%sp),%a0
        movea.l %a0,%a1
        adda.l  SEAM_ARG_SRC(%sp),%a0
        adda.l  SEAM_ARG_DST(%sp),%a1
        .globl  scroll_wrap_copy_1280_body
scroll_wrap_copy_1280_body:                 | 0156ae..01574f: 22d8 x80, rts
    .rept   SEAM_COPY_LONGS
    move.l  (%a0)+,(%a1)+
    .endr
    rts
scroll_wrap_copy_1280_body_end:
