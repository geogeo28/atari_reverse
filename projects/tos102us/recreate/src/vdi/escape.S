/* escape.S — the VDI's escape (opcode 5) as the ROM spells it: its dispatch and every arm that is its own code
 * ($fc427a..$fc42e5, $fc442e..$fc4463, $fc44dc..$fc455f, $fc4a42..$fc4a9d), the TRANSCRIPTION a target build ships,
 * where `escape.c` is what Tier 1's host differential proves.
 *
 * WHY THIS IS ASSEMBLY. The escape is hand-written 68000: a bounds test and a jump through a PC-relative word
 * table, arms of two to ten instructions that address the console's block off the `lea $2994,a4` the dispatch
 * made, and tail-jumps into the console's own routines. Its C twin measures 1.20x-3.13x against it, over the
 * 1.10 bar, and the user's rule for the hand-written routines is the ROM's own instructions, pinned byte for
 * byte (`include/transcribed.h`).
 *
 * WHAT IS NOT HERE is the VT52 console, whose code the escape's arms lie among and its table points into: ESC's
 * bodies (`ESC A` is v_curup's whole arm), the cursor's lock, the cell placement, the character entry. The
 * console ships as C (`src/bios/vt52.c`), so every reference the ROM makes into it names a THUNK below instead:
 * the glue a register-contract entry needs to reach a C body — the image base pushed (0 on target, where the
 * ROM had A4 = $2994), the register arguments pushed as the C's slots, the `jsr`, the slots dropped. The C keeps
 * D2-D7/A2-A6 where the ROM's bodies change some; the C twin's own Tier 1 is what proves each body.
 *
 * THE LAYOUT IS THE ROM's WITHIN EACH SPAN, and `test_vdi_escape_transcription.py` pins every word of the four
 * against the ROM. The words that measure to where things are linked are RELOCATED, each to its exact value:
 * the table's twenty displacements (from the table, to an arm of another span or to a thunk), the `beq.w` to
 * v_fontinit, and the `bsr.w`/`bra.w`s into the console. ESC E's body follows v_exit_cur in the ROM — its entry
 * falls into it and v_enter_cur's `bsr.s` reaches it — so its thunk is laid right after that span, where the
 * ROM has the body, and both keep the ROM's bytes. The graphic cursor's two arms end in `jmp` to v_show_c and
 * v_hide_c, whose C ships: those absolute addresses stay the ROM's own, CODE values a rebuilt ROM owes an entry
 * with the VDI convention (`test_vdi_rom_data.py`), as `entry.S`'s longword for $a009 does.
 *
 * REGISTERS: the transcription relation compares the escape's own (A4 the console block, D0 where an arm writes
 * it); its table row's set (`transcribed.h`) is the ROM's, whose console bodies use D2-D7/A2/A3/A5 as scratch —
 * this file, reaching C bodies instead, changes A4 alone of those, which the row's superset leaves safe.
 *
 * NO WORD EXCUSED otherwise: the three `cmp.w #imm,d0` are the register form GNU as would turn into CMPI, spelt
 * as the ROM's words (`m68k_encodings.h`), and every absolute address a `.l`.
 */
#include "addrs.h"
#include "c_call_glue.h"
#include "m68k_encodings.h"
#include "vdi/escape.h"
#include "vdi/font.h"
#include "vdi/linea.h"
#include "vdi/vdi.h"

/* The console block's fields and the Line-A pointers, as the displacements off A4 = CON_STATE_FLAGS the ROM uses. */
#define A4_(field) ((field) - CON_STATE_FLAGS)
/* A thunk into a console body the escape enters with nothing but A4 (`void f(uint8_t *image)`), named for the body. */
#define ESCAPE_THUNK(body) IMAGE_ONLY_THUNK(escape_to_##body, body)

    .text

/* ---- $fc427a, the dispatch: contrl[5] through the table, UNSIGNED, then the two numbers past it --------------- */
    .globl  vdi_rom_escape
vdi_rom_escape:
    lea     (CON_STATE_FLAGS).l,%a4
    movea.l A4_(LINEA_CONTRL)(%a4),%a0
    move.w  CONTRL_SUBFUNCTION(%a0),%d0
    .word   M68K_CMP_W_IMMEDIATE(M68K_D0), VDI_ESCAPE_LAST             /* cmp.w #19,d0 */
    bhi.s   .Lescape_past_the_table
    add.w   %d0,%d0
    move.w  .Lescape_table(%pc,%d0.w),%d0
    jmp     .Lescape_table(%pc,%d0.w)
.Lescape_table:
    .word   .Lescape_nothing - .Lescape_table                   /* 0: vq_chcells' own `rts` */
    .word   vdi_rom_vq_chcells - .Lescape_table
    .word   .Lescape_v_exit_cur - .Lescape_table
    .word   .Lescape_v_enter_cur - .Lescape_table
    .word   escape_to_console_cursor_up - .Lescape_table        /* 4..10: ESC A B C D H J K */
    .word   escape_to_console_cursor_down - .Lescape_table
    .word   escape_to_console_cursor_right - .Lescape_table
    .word   escape_to_console_cursor_left - .Lescape_table
    .word   escape_to_console_cursor_home - .Lescape_table
    .word   escape_to_console_clear_to_end_of_screen - .Lescape_table
    .word   escape_to_console_clear_to_end_of_line - .Lescape_table
    .word   vdi_rom_vs_curaddress - .Lescape_table
    .word   .Lescape_v_curtext - .Lescape_table
    .word   .Lescape_v_rvon - .Lescape_table
    .word   .Lescape_v_rvoff - .Lescape_table
    .word   .Lescape_vq_curaddress - .Lescape_table
    .word   .Lescape_vq_tabstatus - .Lescape_table
    .word   .Lescape_v_hardcopy - .Lescape_table
    .word   .Lescape_v_dspcur - .Lescape_table
    .word   .Lescape_v_rmcur - .Lescape_table
.Lescape_past_the_table:
    .word   M68K_CMP_W_IMMEDIATE(M68K_D0), VDI_ESCAPE_V_OFFSET         /* cmp.w #101,d0 */
    beq.s   .Lescape_v_offset
    .word   M68K_CMP_W_IMMEDIATE(M68K_D0), VDI_ESCAPE_V_FONTINIT       /* cmp.w #102,d0 */
    beq.w   vdi_rom_v_fontinit
    rts

/* $fc42d0 — v_offset: the text screen intin[0] scan lines down, under the cursor's lock; the cursor's own
 * address is not recomputed */
.Lescape_v_offset:
    bsr.w   escape_to_console_hide_cursor
    movea.l A4_(LINEA_INTIN)(%a4),%a0
    move.w  (%a0),%d0
    mulu.w  A4_(CON_LINE_BYTES)(%a4),%d0
    move.w  %d0,A4_(CON_CURSOR_OFFSET)(%a4)
    bra.w   escape_to_console_unlock_cursor

/* ---- $fc442e, the answering arm, the dump and alpha mode — ending in ESC E's body ----------------------------- */
vdi_rom_vq_chcells:
    movea.l A4_(LINEA_CONTRL)(%a4),%a0
    move.w  #VDI_ESCAPE_ANSWER_CELLS_WORDS,CONTRL_N_INTOUT(%a0)
    movea.l A4_(LINEA_INTOUT)(%a4),%a0
    move.w  A4_(CON_MAX_COLUMN)(%a4),%d0                        /* the columns first, into intout[1] */
    addq.w  #1,%d0
    move.w  %d0,VDI_WORD_BYTES(%a0)
    move.w  A4_(CON_MAX_ROW)(%a4),%d0
    addq.w  #1,%d0
    move.w  %d0,(%a0)
.Lescape_nothing:
    rts

/* $fc4450 — v_hardcopy: XBIOS Scrdmp */
.Lescape_v_hardcopy:
    move.w  #XBIOS_SCRDMP_FN,-(%sp)
    trap    #14
    addq.l  #2,%sp
    rts

/* $fc445a — v_enter_cur: ESC E, then the cursor forced on */
.Lescape_v_enter_cur:
    bsr.s   escape_to_console_clear_screen_and_home
    bra.w   escape_to_console_show_cursor

/* $fc4460 — v_exit_cur: the cursor locked, then ESC E, which the ROM's next instruction is */
.Lescape_v_exit_cur:
    bsr.w   escape_to_console_hide_cursor

/* ---- the thunk in ESC E's place ($fc4464): v_exit_cur falls into it and v_enter_cur's `bsr.s` reaches it ------ */
ESCAPE_THUNK(console_clear_screen_and_home)

/* ---- $fc44dc, the cursor's address, the text, reverse video, the two inquiries, the graphic cursor ------------ */
vdi_rom_vs_curaddress:
    movea.l A4_(LINEA_INTIN)(%a4),%a0
    move.w  (%a0),%d1                                           /* 1-based and unchecked: a 0 is $ffff */
    subq.w  #1,%d1
    move.w  VDI_WORD_BYTES(%a0),%d0
    subq.w  #1,%d0
    bra.w   escape_to_console_place_cursor

/* $fc44ee — v_curtext: contrl[3] words through the console's character entry, the count a `dbf`'s */
.Lescape_v_curtext:
    movea.l A4_(LINEA_CONTRL)(%a4),%a0
    move.w  CONTRL_N_INTIN(%a0),%d0
    movea.l A4_(LINEA_INTIN)(%a4),%a0
    bra.s   .Lescape_v_curtext_next
.Lescape_v_curtext_word:
    move.w  (%a0)+,%d1
    movem.l %d0/%a0,-(%sp)
    bsr.w   escape_to_console_output
    movem.l (%sp)+,%d0/%a0
.Lescape_v_curtext_next:
    dbf     %d0,.Lescape_v_curtext_word
    rts

/* $fc4510 / $fc4516 — v_rvon / v_rvoff: ESC p / ESC q, the flag alone */
.Lescape_v_rvon:
    bset    #CON_FLAG_REVERSE,(%a4)
    rts
.Lescape_v_rvoff:
    bclr    #CON_FLAG_REVERSE,(%a4)
    rts

/* $fc451c — vq_curaddress: the count, then the row and the column, 1-based, through one pointer */
.Lescape_vq_curaddress:
    movea.l A4_(LINEA_CONTRL)(%a4),%a0
    move.w  #VDI_ESCAPE_ANSWER_CELLS_WORDS,CONTRL_N_INTOUT(%a0)
    movea.l A4_(LINEA_INTOUT)(%a4),%a0
    move.w  A4_(CON_CURSOR_ROW)(%a4),%d0
    addq.w  #1,%d0
    move.w  %d0,(%a0)+
    move.w  A4_(CON_CURSOR_COLUMN)(%a4),%d0
    addq.w  #1,%d0
    move.w  %d0,(%a0)
    rts

/* $fc453c — vq_tabstatus: one `moveq`, stored as the count and as the answer */
.Lescape_vq_tabstatus:
    moveq   #VDI_ESCAPE_ANSWER_TABLET,%d0
    movea.l A4_(LINEA_CONTRL)(%a4),%a0
    move.w  %d0,CONTRL_N_INTOUT(%a0)
    movea.l A4_(LINEA_INTOUT)(%a4),%a0
    move.w  %d0,(%a0)
    rts

/* $fc454e / $fc455a — v_dspcur (the caller's intin[0] cleared, then v_show_c) and v_rmcur (v_hide_c) */
.Lescape_v_dspcur:
    movea.l A4_(LINEA_INTIN)(%a4),%a0
    clr.w   (%a0)
    jmp     (VDI_ROM_V_SHOW_C).l
.Lescape_v_rmcur:
    jmp     (VDI_ROM_V_HIDE_C).l

/* ---- THE THUNKS into the console's C, one per ROM routine the spans reach ------------------------------------- */
ESCAPE_THUNK(console_hide_cursor)                               /* $fc45de, the lock */
ESCAPE_THUNK(console_unlock_cursor)                             /* $fc45ae */
ESCAPE_THUNK(console_show_cursor)                               /* $fc45be */
ESCAPE_THUNK(console_cursor_up)                                 /* $fc4468, ESC A */
ESCAPE_THUNK(console_cursor_down)                               /* $fc4478, ESC B */
ESCAPE_THUNK(console_cursor_right)                              /* $fc448c, ESC C */
ESCAPE_THUNK(console_cursor_left)                               /* $fc44a0, ESC D */
ESCAPE_THUNK(console_cursor_home)                               /* $fc44b0, ESC H */
ESCAPE_THUNK(console_clear_to_end_of_screen)                    /* $fc44b8, ESC J */
ESCAPE_THUNK(console_clear_to_end_of_line)                      /* $fc44ca, ESC K */

/* $fc49fc — the cell placement, D0 the column and D1 the row: `console_place_cursor(image, column, row)`, each
 * word zero-extended into its slot. */
    .type   escape_to_console_place_cursor,@function
escape_to_console_place_cursor:
    move.w  %d1,-(%sp)
    clr.w   -(%sp)
    move.w  %d0,-(%sp)
    clr.w   -(%sp)
    pea     (0).w
    jsr     console_place_cursor
    lea     (IMAGE_ARGUMENT_BYTES + 2 * SLOT_BYTES)(%sp),%sp
    rts
    .size   escape_to_console_place_cursor,.-escape_to_console_place_cursor

/* $fc42f6 — the character entry past Bconout's argument fetch, D1 the word: `console_output(image, 0, character)`,
 * the D0 an entry past the trap dispatcher has no use for passed as 0, as the C twin passes it. */
    .type   escape_to_console_output,@function
escape_to_console_output:
    move.w  %d1,-(%sp)
    clr.w   -(%sp)
    clr.l   -(%sp)
    pea     (0).w
    jsr     console_output
    lea     (IMAGE_ARGUMENT_BYTES + 2 * SLOT_BYTES)(%sp),%sp
    rts
    .size   escape_to_console_output,.-escape_to_console_output

/* ---- $fc4a42, v_fontinit (102): the console's font and geometry from the header intin[0..1] points at --------- */
vdi_rom_v_fontinit:
    movea.l A4_(LINEA_INTIN)(%a4),%a0
    movea.l (%a0),%a0
    lea     (CON_STATE_FLAGS).l,%a4
    move.w  FONT_FORM_HEIGHT(%a0),%d0
    move.w  %d0,A4_(CON_CELL_HEIGHT)(%a4)
    move.w  A4_(CON_LINE_BYTES)(%a4),%d1
    mulu.w  %d0,%d1
    move.w  %d1,A4_(CON_ROW_BYTES)(%a4)
    moveq   #0,%d1
    move.w  A4_(LINEA_V_REZ_VT)(%a4),%d1
    divu.w  %d0,%d1
    subq.w  #1,%d1
    move.w  %d1,A4_(CON_MAX_ROW)(%a4)
    moveq   #0,%d1
    move.w  A4_(LINEA_V_REZ_HZ)(%a4),%d1
    divu.w  FONT_MAX_CELL_WIDTH(%a0),%d1
    subq.w  #1,%d1
    move.w  %d1,A4_(CON_MAX_COLUMN)(%a4)
    move.w  FONT_FORM_WIDTH(%a0),A4_(CON_FONT_FORM_BYTES)(%a4)
    move.w  FONT_FIRST_ADE(%a0),A4_(CON_FONT_FIRST)(%a4)
    move.w  FONT_LAST_ADE(%a0),A4_(CON_FONT_LAST)(%a4)
    move.l  FONT_DAT_TABLE(%a0),A4_(CON_FONT_FORM)(%a4)
    move.l  FONT_OFF_TABLE(%a0),A4_(CON_FONT_OFFSETS)(%a4)
    rts
