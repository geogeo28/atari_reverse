| scroll_blit.S — asm twins for the twenty page-to-screen blits, TRANSCRIBED from the original.
|
|   scroll_page_to_screen_p00_asm .. _p19_asm  <- the original @ 0x15d56 .. 0x16284
|   the C references: ../scroll.c's scroll_page_to_screen_p00 .. _p19
|
| Together these are the single most expensive thing the reconstruction does — 244,702 cycles a frame
| against the original's 111,961 (atari/README.md, PERFORMANCE). The reason is not that the C is bad:
| it is that the original copies each row as a run of `movem.l` PAIRS, twelve longwords at a time
| through the register file, and no C the compiler will emit reaches that. So the fast version is not
| something to invent — the original's own instructions are in ../../out/prg_dis.txt, and everything
| between BLIT_PROLOGUE and BLIT_EPILOGUE below is a transcription of them.
|
| THAT CLAIM IS MEASURED, NOT ASSERTED. Each body is bracketed by `_body` / `_body_end` labels, and
| test_asm_scroll.py::test_the_blit_twins_transcribe_the_original compares those bytes against the
| original's own bytes at its entry address. They are IDENTICAL — the bodies touch only %a5, %a6 and
| the transfer registers, so there was nothing in them to translate — which is what makes these twins
| 1.00x by construction rather than by hope. A body edited to something the original does not do
| fails that test even if it still computes the right pixels.
|
| WHAT THE TWENTY DIFFER IN is the CHUNKING, not the result. A page is a RING one screen row wide:
| phase N's 152-byte window starts SCROLL_PHASE_STEP * (N + 1) bytes into the row, runs to the row's
| end, and picks up the rest from the row's start. Each body's `movem.l` register sets are cut so
| that the wrap lands on a chunk boundary — phase 2 copies 48+48+40 then wraps and copies 16, phase
| 12 copies 48+8 then wraps and copies 48+48 — and the LAST chunk of every row advances the
| destination by SCROLL_PHASE_STEP more than it copied, stepping over the screen's right-edge cell,
| which this routine must not write (the two emitters in scroll_emit.S own it). Every body therefore
| copies SCROLL_WINDOW_BYTES and advances SCREEN_ROW_BYTES; the generator that read these bodies out
| of the disassembly asserted exactly that, phase by phase.
|
| Phase 19 is the one that does not wrap: its window starts at 160, which is 0, so it has no leading
| `lea` and its row ends with a plain SCROLL_PHASE_STEP step over the edge cell.
|
| THE C ABI. Each twin carries the signature of the core it replaces, because ../frame.c reaches all
| twenty through a table and must not care which it got:
|
|   void scroll_page_to_screen_pNN(uint8_t *image, uint32_t page, uint32_t screen);
|
| THE IMAGE BASE. The original IS the image and receives its two cursors as absolute addresses in
| %a5 / %a6; the reconstruction passes them as OFFSETS from `image`, which on the target build is a
| real pointer. BLIT_PROLOGUE is the whole of that translation, and it is why the bodies below could
| be copied unchanged: nothing inside them mentions an address at all.
|
| REGISTERS, the original's:
|   %a5 = the page cursor, walked with (%a5)+ and stepped over the ring wrap
|   %a6 = the screen cursor, advanced by each chunk's own `lea`
|   %d0 = the row counter (PLAYFIELD_ROWS rows, `dbf`)
|   %d1-%d7 / %a0-%a4 = the transfer file — up to twelve longwords in flight per chunk
|
| A `movem.l` pair reads a whole chunk before storing any of it, so the chunk boundaries WOULD be
| observable if page and screen overlapped. They cannot: a page is one of the eight 0x5a00 buffers at
| `map_page_table` and the screen is a framebuffer. ../scroll.c's header records the same fact, which
| is what lets its C copy the window in order and still be byte-equal to this.

    .text

| ---- constants: ../../include/scroll.h's and ../../include/video.h's, by their names there --------
| test_constants.py::test_asm_twin_equates_match_the_headers pins every one against the header that
| owns it, so a value that moved there cannot go on living here.
    .equ SCROLL_PHASE_STEP,   8     | one 16-pixel cell — the step between two phases' window starts
    .equ SCREEN_ROW_BYTES,  160
    .equ PLAYFIELD_ROWS,    144

| ---- the C stack frame ---------------------------------------------------------------------------
| SAVED is what BLIT_PROLOGUE pushes: %d2-%d7 and %a2-%a6, the callee-saved registers these bodies
| clobber (%a5 and %a6 among them). Every argument offset is measured past it, so the two cannot
| drift apart.
    .equ SAVED,      (11 * 4)
    .equ ARG_IMAGE,    4 + SAVED
    .equ ARG_PAGE,     8 + SAVED
    .equ ARG_SCREEN,  12 + SAVED

| Bind the C arguments to the original's register convention. %a0 is scratch under the C ABI and the
| bodies load it before they read it, so it can carry the image base through the prologue.
.macro BLIT_PROLOGUE
    movem.l %d2-%d7/%a2-%a6,-(%sp)
    movea.l ARG_IMAGE(%sp),%a0
    movea.l ARG_PAGE(%sp),%a5
    adda.l  %a0,%a5
    movea.l ARG_SCREEN(%sp),%a6
    adda.l  %a0,%a6
.endm

.macro BLIT_EPILOGUE
    movem.l (%sp)+,%d2-%d7/%a2-%a6
    rts
.endm

| One chunk of a row: read `regs` longwords out of the page, store them to the screen, and step the
| screen on by `dst_advance` — which is the chunk's own byte count, except on a row's last chunk,
| where it is that plus the right-edge cell this routine does not write.
.macro CHUNK regs, dst_advance
    movem.l (%a5)+,\regs
    movem.l \regs,(%a6)
    lea     \dst_advance(%a6),%a6
.endm
    .globl  scroll_page_to_screen_p00_asm
scroll_page_to_screen_p00_asm:
    BLIT_PROLOGUE
    .globl  scroll_page_to_screen_p00_body
scroll_page_to_screen_p00_body:                             | the original @ 0x15d56
    lea     SCROLL_PHASE_STEP * 1(%a5),%a5
    move.w  #PLAYFIELD_ROWS - 1,%d0
.L00_row:
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d2, 8 + SCROLL_PHASE_STEP
    lea     SCROLL_PHASE_STEP(%a5),%a5
    dbf     %d0,.L00_row
    .globl  scroll_page_to_screen_p00_body_end
scroll_page_to_screen_p00_body_end:
    BLIT_EPILOGUE

    .globl  scroll_page_to_screen_p01_asm
scroll_page_to_screen_p01_asm:
    BLIT_PROLOGUE
    .globl  scroll_page_to_screen_p01_body
scroll_page_to_screen_p01_body:                             | the original @ 0x15d98
    lea     SCROLL_PHASE_STEP * 2(%a5),%a5
    move.w  #PLAYFIELD_ROWS - 1,%d0
.L01_row:
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a4, 48
    lea     -SCREEN_ROW_BYTES(%a5),%a5
    CHUNK   %d1-%d2, 8 + SCROLL_PHASE_STEP
    lea     SCREEN_ROW_BYTES + SCROLL_PHASE_STEP(%a5),%a5
    dbf     %d0,.L01_row
    .globl  scroll_page_to_screen_p01_body_end
scroll_page_to_screen_p01_body_end:
    BLIT_EPILOGUE

    .globl  scroll_page_to_screen_p02_asm
scroll_page_to_screen_p02_asm:
    BLIT_PROLOGUE
    .globl  scroll_page_to_screen_p02_body
scroll_page_to_screen_p02_body:                             | the original @ 0x15dde
    lea     SCROLL_PHASE_STEP * 3(%a5),%a5
    move.w  #PLAYFIELD_ROWS - 1,%d0
.L02_row:
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a2, 40
    lea     -SCREEN_ROW_BYTES(%a5),%a5
    CHUNK   %d1-%d4, 16 + SCROLL_PHASE_STEP
    lea     SCREEN_ROW_BYTES + SCROLL_PHASE_STEP(%a5),%a5
    dbf     %d0,.L02_row
    .globl  scroll_page_to_screen_p02_body_end
scroll_page_to_screen_p02_body_end:
    BLIT_EPILOGUE

    .globl  scroll_page_to_screen_p03_asm
scroll_page_to_screen_p03_asm:
    BLIT_PROLOGUE
    .globl  scroll_page_to_screen_p03_body
scroll_page_to_screen_p03_body:                             | the original @ 0x15e24
    lea     SCROLL_PHASE_STEP * 4(%a5),%a5
    move.w  #PLAYFIELD_ROWS - 1,%d0
.L03_row:
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0, 32
    lea     -SCREEN_ROW_BYTES(%a5),%a5
    CHUNK   %d1-%d6, 24 + SCROLL_PHASE_STEP
    lea     SCREEN_ROW_BYTES + SCROLL_PHASE_STEP(%a5),%a5
    dbf     %d0,.L03_row
    .globl  scroll_page_to_screen_p03_body_end
scroll_page_to_screen_p03_body_end:
    BLIT_EPILOGUE

    .globl  scroll_page_to_screen_p04_asm
scroll_page_to_screen_p04_asm:
    BLIT_PROLOGUE
    .globl  scroll_page_to_screen_p04_body
scroll_page_to_screen_p04_body:                             | the original @ 0x15e6a
    lea     SCROLL_PHASE_STEP * 5(%a5),%a5
    move.w  #PLAYFIELD_ROWS - 1,%d0
.L04_row:
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d6, 24
    lea     -SCREEN_ROW_BYTES(%a5),%a5
    CHUNK   %d1-%d7/%a0, 32 + SCROLL_PHASE_STEP
    lea     SCREEN_ROW_BYTES + SCROLL_PHASE_STEP(%a5),%a5
    dbf     %d0,.L04_row
    .globl  scroll_page_to_screen_p04_body_end
scroll_page_to_screen_p04_body_end:
    BLIT_EPILOGUE

    .globl  scroll_page_to_screen_p05_asm
scroll_page_to_screen_p05_asm:
    BLIT_PROLOGUE
    .globl  scroll_page_to_screen_p05_body
scroll_page_to_screen_p05_body:                             | the original @ 0x15eb0
    lea     SCROLL_PHASE_STEP * 6(%a5),%a5
    move.w  #PLAYFIELD_ROWS - 1,%d0
.L05_row:
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d4, 16
    lea     -SCREEN_ROW_BYTES(%a5),%a5
    CHUNK   %d1-%d7/%a0-%a2, 40 + SCROLL_PHASE_STEP
    lea     SCREEN_ROW_BYTES + SCROLL_PHASE_STEP(%a5),%a5
    dbf     %d0,.L05_row
    .globl  scroll_page_to_screen_p05_body_end
scroll_page_to_screen_p05_body_end:
    BLIT_EPILOGUE

    .globl  scroll_page_to_screen_p06_asm
scroll_page_to_screen_p06_asm:
    BLIT_PROLOGUE
    .globl  scroll_page_to_screen_p06_body
scroll_page_to_screen_p06_body:                             | the original @ 0x15ef6
    lea     SCROLL_PHASE_STEP * 7(%a5),%a5
    move.w  #PLAYFIELD_ROWS - 1,%d0
.L06_row:
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d2, 8
    lea     -SCREEN_ROW_BYTES(%a5),%a5
    CHUNK   %d1-%d7/%a0-%a4, 48 + SCROLL_PHASE_STEP
    lea     SCREEN_ROW_BYTES + SCROLL_PHASE_STEP(%a5),%a5
    dbf     %d0,.L06_row
    .globl  scroll_page_to_screen_p06_body_end
scroll_page_to_screen_p06_body_end:
    BLIT_EPILOGUE

    .globl  scroll_page_to_screen_p07_asm
scroll_page_to_screen_p07_asm:
    BLIT_PROLOGUE
    .globl  scroll_page_to_screen_p07_body
scroll_page_to_screen_p07_body:                             | the original @ 0x15f3c
    lea     SCROLL_PHASE_STEP * 8(%a5),%a5
    move.w  #PLAYFIELD_ROWS - 1,%d0
.L07_row:
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a4, 48
    lea     -SCREEN_ROW_BYTES(%a5),%a5
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d2, 8 + SCROLL_PHASE_STEP
    lea     SCREEN_ROW_BYTES + SCROLL_PHASE_STEP(%a5),%a5
    dbf     %d0,.L07_row
    .globl  scroll_page_to_screen_p07_body_end
scroll_page_to_screen_p07_body_end:
    BLIT_EPILOGUE

    .globl  scroll_page_to_screen_p08_asm
scroll_page_to_screen_p08_asm:
    BLIT_PROLOGUE
    .globl  scroll_page_to_screen_p08_body
scroll_page_to_screen_p08_body:                             | the original @ 0x15f82
    lea     SCROLL_PHASE_STEP * 9(%a5),%a5
    move.w  #PLAYFIELD_ROWS - 1,%d0
.L08_row:
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a2, 40
    lea     -SCREEN_ROW_BYTES(%a5),%a5
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d4, 16 + SCROLL_PHASE_STEP
    lea     SCREEN_ROW_BYTES + SCROLL_PHASE_STEP(%a5),%a5
    dbf     %d0,.L08_row
    .globl  scroll_page_to_screen_p08_body_end
scroll_page_to_screen_p08_body_end:
    BLIT_EPILOGUE

    .globl  scroll_page_to_screen_p09_asm
scroll_page_to_screen_p09_asm:
    BLIT_PROLOGUE
    .globl  scroll_page_to_screen_p09_body
scroll_page_to_screen_p09_body:                             | the original @ 0x15fc8
    lea     SCROLL_PHASE_STEP * 10(%a5),%a5
    move.w  #PLAYFIELD_ROWS - 1,%d0
.L09_row:
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0, 32
    lea     -SCREEN_ROW_BYTES(%a5),%a5
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d6, 24 + SCROLL_PHASE_STEP
    lea     SCREEN_ROW_BYTES + SCROLL_PHASE_STEP(%a5),%a5
    dbf     %d0,.L09_row
    .globl  scroll_page_to_screen_p09_body_end
scroll_page_to_screen_p09_body_end:
    BLIT_EPILOGUE

    .globl  scroll_page_to_screen_p10_asm
scroll_page_to_screen_p10_asm:
    BLIT_PROLOGUE
    .globl  scroll_page_to_screen_p10_body
scroll_page_to_screen_p10_body:                             | the original @ 0x1600e
    lea     SCROLL_PHASE_STEP * 11(%a5),%a5
    move.w  #PLAYFIELD_ROWS - 1,%d0
.L10_row:
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d6, 24
    lea     -SCREEN_ROW_BYTES(%a5),%a5
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0, 32 + SCROLL_PHASE_STEP
    lea     SCREEN_ROW_BYTES + SCROLL_PHASE_STEP(%a5),%a5
    dbf     %d0,.L10_row
    .globl  scroll_page_to_screen_p10_body_end
scroll_page_to_screen_p10_body_end:
    BLIT_EPILOGUE

    .globl  scroll_page_to_screen_p11_asm
scroll_page_to_screen_p11_asm:
    BLIT_PROLOGUE
    .globl  scroll_page_to_screen_p11_body
scroll_page_to_screen_p11_body:                             | the original @ 0x16054
    lea     SCROLL_PHASE_STEP * 12(%a5),%a5
    move.w  #PLAYFIELD_ROWS - 1,%d0
.L11_row:
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d4, 16
    lea     -SCREEN_ROW_BYTES(%a5),%a5
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a2, 40 + SCROLL_PHASE_STEP
    lea     SCREEN_ROW_BYTES + SCROLL_PHASE_STEP(%a5),%a5
    dbf     %d0,.L11_row
    .globl  scroll_page_to_screen_p11_body_end
scroll_page_to_screen_p11_body_end:
    BLIT_EPILOGUE

    .globl  scroll_page_to_screen_p12_asm
scroll_page_to_screen_p12_asm:
    BLIT_PROLOGUE
    .globl  scroll_page_to_screen_p12_body
scroll_page_to_screen_p12_body:                             | the original @ 0x1609a
    lea     SCROLL_PHASE_STEP * 13(%a5),%a5
    move.w  #PLAYFIELD_ROWS - 1,%d0
.L12_row:
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d2, 8
    lea     -SCREEN_ROW_BYTES(%a5),%a5
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a4, 48 + SCROLL_PHASE_STEP
    lea     SCREEN_ROW_BYTES + SCROLL_PHASE_STEP(%a5),%a5
    dbf     %d0,.L12_row
    .globl  scroll_page_to_screen_p12_body_end
scroll_page_to_screen_p12_body_end:
    BLIT_EPILOGUE

    .globl  scroll_page_to_screen_p13_asm
scroll_page_to_screen_p13_asm:
    BLIT_PROLOGUE
    .globl  scroll_page_to_screen_p13_body
scroll_page_to_screen_p13_body:                             | the original @ 0x160e0
    lea     SCROLL_PHASE_STEP * 14(%a5),%a5
    move.w  #PLAYFIELD_ROWS - 1,%d0
.L13_row:
    CHUNK   %d1-%d7/%a0-%a4, 48
    lea     -SCREEN_ROW_BYTES(%a5),%a5
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d2, 8 + SCROLL_PHASE_STEP
    lea     SCREEN_ROW_BYTES + SCROLL_PHASE_STEP(%a5),%a5
    dbf     %d0,.L13_row
    .globl  scroll_page_to_screen_p13_body_end
scroll_page_to_screen_p13_body_end:
    BLIT_EPILOGUE

    .globl  scroll_page_to_screen_p14_asm
scroll_page_to_screen_p14_asm:
    BLIT_PROLOGUE
    .globl  scroll_page_to_screen_p14_body
scroll_page_to_screen_p14_body:                             | the original @ 0x16126
    lea     SCROLL_PHASE_STEP * 15(%a5),%a5
    move.w  #PLAYFIELD_ROWS - 1,%d0
.L14_row:
    CHUNK   %d1-%d7/%a0-%a2, 40
    lea     -SCREEN_ROW_BYTES(%a5),%a5
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d4, 16 + SCROLL_PHASE_STEP
    lea     SCREEN_ROW_BYTES + SCROLL_PHASE_STEP(%a5),%a5
    dbf     %d0,.L14_row
    .globl  scroll_page_to_screen_p14_body_end
scroll_page_to_screen_p14_body_end:
    BLIT_EPILOGUE

    .globl  scroll_page_to_screen_p15_asm
scroll_page_to_screen_p15_asm:
    BLIT_PROLOGUE
    .globl  scroll_page_to_screen_p15_body
scroll_page_to_screen_p15_body:                             | the original @ 0x1616c
    lea     SCROLL_PHASE_STEP * 16(%a5),%a5
    move.w  #PLAYFIELD_ROWS - 1,%d0
.L15_row:
    CHUNK   %d1-%d7/%a0, 32
    lea     -SCREEN_ROW_BYTES(%a5),%a5
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d6, 24 + SCROLL_PHASE_STEP
    lea     SCREEN_ROW_BYTES + SCROLL_PHASE_STEP(%a5),%a5
    dbf     %d0,.L15_row
    .globl  scroll_page_to_screen_p15_body_end
scroll_page_to_screen_p15_body_end:
    BLIT_EPILOGUE

    .globl  scroll_page_to_screen_p16_asm
scroll_page_to_screen_p16_asm:
    BLIT_PROLOGUE
    .globl  scroll_page_to_screen_p16_body
scroll_page_to_screen_p16_body:                             | the original @ 0x161b2
    lea     SCROLL_PHASE_STEP * 17(%a5),%a5
    move.w  #PLAYFIELD_ROWS - 1,%d0
.L16_row:
    CHUNK   %d1-%d6, 24
    lea     -SCREEN_ROW_BYTES(%a5),%a5
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0, 32 + SCROLL_PHASE_STEP
    lea     SCREEN_ROW_BYTES + SCROLL_PHASE_STEP(%a5),%a5
    dbf     %d0,.L16_row
    .globl  scroll_page_to_screen_p16_body_end
scroll_page_to_screen_p16_body_end:
    BLIT_EPILOGUE

    .globl  scroll_page_to_screen_p17_asm
scroll_page_to_screen_p17_asm:
    BLIT_PROLOGUE
    .globl  scroll_page_to_screen_p17_body
scroll_page_to_screen_p17_body:                             | the original @ 0x161f8
    lea     SCROLL_PHASE_STEP * 18(%a5),%a5
    move.w  #PLAYFIELD_ROWS - 1,%d0
.L17_row:
    CHUNK   %d1-%d4, 16
    lea     -SCREEN_ROW_BYTES(%a5),%a5
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a2, 40 + SCROLL_PHASE_STEP
    lea     SCREEN_ROW_BYTES + SCROLL_PHASE_STEP(%a5),%a5
    dbf     %d0,.L17_row
    .globl  scroll_page_to_screen_p17_body_end
scroll_page_to_screen_p17_body_end:
    BLIT_EPILOGUE

    .globl  scroll_page_to_screen_p18_asm
scroll_page_to_screen_p18_asm:
    BLIT_PROLOGUE
    .globl  scroll_page_to_screen_p18_body
scroll_page_to_screen_p18_body:                             | the original @ 0x1623e
    lea     SCROLL_PHASE_STEP * 19(%a5),%a5
    move.w  #PLAYFIELD_ROWS - 1,%d0
.L18_row:
    CHUNK   %d1-%d2, 8
    lea     -SCREEN_ROW_BYTES(%a5),%a5
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a4, 48 + SCROLL_PHASE_STEP
    lea     SCREEN_ROW_BYTES + SCROLL_PHASE_STEP(%a5),%a5
    dbf     %d0,.L18_row
    .globl  scroll_page_to_screen_p18_body_end
scroll_page_to_screen_p18_body_end:
    BLIT_EPILOGUE

    .globl  scroll_page_to_screen_p19_asm
scroll_page_to_screen_p19_asm:
    BLIT_PROLOGUE
    .globl  scroll_page_to_screen_p19_body
scroll_page_to_screen_p19_body:                             | the original @ 0x16284
    move.w  #PLAYFIELD_ROWS - 1,%d0
.L19_row:
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d7/%a0-%a4, 48
    CHUNK   %d1-%d2, 8 + SCROLL_PHASE_STEP
    lea     SCROLL_PHASE_STEP(%a5),%a5
    dbf     %d0,.L19_row
    .globl  scroll_page_to_screen_p19_body_end
scroll_page_to_screen_p19_body_end:
    BLIT_EPILOGUE

