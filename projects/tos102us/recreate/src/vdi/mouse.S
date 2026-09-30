/* mouse.S — the mouse and cursor routines AS THE ROM WROTE THEM: the TRANSCRIPTION of `src/vdi/mouse.c`'s
 * hand-written 68000 the target build ships, because each one's C measures over Tier 3's 1.10 bar
 * (`include/transcribed.h` says which entries, with each one's registers; STATUS.md has the rows).
 *
 * WHY THIS IS ASSEMBLY. The sprite pair is three fragments per row reached by `jsr (a6)` / `jmp (a3)` /
 * `jmp (a4)` / `jmp (a5)` out of two PC-relative tables, chosen once per call by the clip and once per
 * plane by the colours — a C port pays a call and a compare chain per row that the ROM pays per plane,
 * and lands three to eight times the ROM's cycles. The ISR saves every register with one `movem` and
 * passes its user vectors their arguments in D0/D1; the lock and the hide count are one `addq.b` each.
 *
 * WHAT PINS IT, needing no C:
 *   * BYTE FOR BYTE — `test_vdi_mouse_transcription.py` reads every word back out of the cross-compiled
 *     blob against the ROM's (`transcription.assert_transcribed`). The references that differ are RELOCATED there by
 *     name, each to its exact value: draw_sprite's `bsr.w` to concat (raster.S), the two `lea`s of the
 *     spread fragments and the fourteen longwords of the two fragment tables — which name THIS file's
 *     fragments, as the ROM's name its own.
 *   * BY BEHAVIOUR — every registered case through Tier 3's transcription relation: the same image, the
 *     whole register file (the fragment pointers the sprite leaves in A3-A6 cleared by the staged caller
 *     on both sides) and the same traffic.
 *
 * THE REGIONS are the ROM's, in its order, so every short branch and PC-relative table assembles to the
 * ROM's own word:
 *
 *   $fcfe28..$fcff67  mouse_isr, clamp_mouse, default_user_cur, vbl_draw_cursor
 *   $fcffb0..$fd0345  draw_sprite with its fragments and tables, undraw_sprite, hide_mouse, show_cursor,
 *                     vsc_form — laid out after the first with the gap between them kept
 *   $fca7c0..$fca7c9  poll_choice
 *   $fca88a..$fca913  poll_locator
 *
 * clamp_mouse is here and not in helpers.S because the ISR reaches it by `bsr.s`, whose displacement is a
 * byte of the opcode itself: only the ROM's own layout reproduces it. The three VDI vector exchanges
 * ($fcff68..$fcffaf, `src/vdi/attributes.c`) sit between vbl_draw_cursor and draw_sprite, which the VBL
 * reaches by `bsr.s` over them, so their SPACE is kept here — not their instructions, which would be code
 * nothing runs: their C is what ships (Tier 3 1.08). The byte pin checks the gap through that `bsr.s`.
 *
 * THE CODE ADDRESSES THE ROUTINES STORE are the ROM's own ($fca870, $fcff0a, $fcff2a, $fcfe28, and the
 * transcription relation compares the image they land in): a shipped ROM that moved these routines would
 * relocate them with the rest, and the C (`mouse.c`) stores the same `VDI_ROM_*` values. MAP_COL is read at
 * the ROM's address as `palette.S` reads it.
 *
 * THE POLLS ($fca7c0, $fca88a) take the BIOS through the machine's own `trap #13`; poll_key and the
 * workstation pair ($fca7ca, $fca7f8, $fca872) are within the bar as C and ship as C.
 */
#include "addrs.h"
#include "m68k_encodings.h"
#include "vdi/linea.h"
#include "vdi/vdi.h"
#include "vdi/mouse.h"

#define MOUSE_BIOS_FRAME_BYTES 4        /* Bconstat's frame, reused for Bconin: two words */
#define VEX_EXCHANGES_BYTES    (LINEA_ROM_DRAW_SPRITE - VDI_ROM_VEX_BUTV)  /* $fcff68..$fcffaf, the three */
#define BIOS_CONSOLE_STATUS    BIOS_BCONSTAT_FN
#define BIOS_CONSOLE_INPUT     BIOS_BCONIN_FN

    .text

/* ==== $fcfe28 — the mouse ISR: A0 the IKBD's relative packet ======================================= */
    .globl  vdi_rom_mouse_isr
vdi_rom_mouse_isr:
    tst.b   (LINEA_MOUSE_FLAG).l
    bne.w   .Lisr_done
    movem.l %d0-%a6,-(%sp)
    move.b  (%a0),%d0
    move.b  %d0,%d1
    andi.b  #MOUSE_PACKET_HEADER_MASK,%d1
    cmpi.b  #MOUSE_PACKET_HEADER_MASK,%d1
    bne.w   .Lisr_restore
    andi.w  #MOUSE_PACKET_BUTTONS_MASK,%d0
    lsr.b   #1,%d0
    bcc.s   .Lisr_swapped
    bset    #1,%d0
.Lisr_swapped:
    move.b  (LINEA_CUR_MS_STAT).l,%d1
    andi.w  #MOUSE_STAT_BUTTONS_MASK,%d1
    cmp.b   %d1,%d0
    beq.s   .Lisr_motion
    move.w  %d1,-(%sp)
    movea.l (LINEA_USER_BUT).l,%a1
    jsr     (%a1)
    move.w  (%sp)+,%d1
    move.w  %d0,(LINEA_MOUSE_BT).l
    eor.b   %d0,%d1
    ror.b   #2,%d1
    or.b    %d1,%d0
    move.b  %d0,(LINEA_CUR_MS_STAT).l
.Lisr_motion:
    move.b  MOUSE_PACKET_DX(%a0),%d0
    or.b    MOUSE_PACKET_DY(%a0),%d0
    bne.s   .Lisr_moved
    bclr    #MOUSE_STAT_MOVED_BIT,(LINEA_CUR_MS_STAT).l
    bra.s   .Lisr_restore
.Lisr_moved:
    bset    #MOUSE_STAT_MOVED_BIT,(LINEA_CUR_MS_STAT).l
    move.w  (LINEA_GCURX).l,%d0
    move.b  MOUSE_PACKET_DX(%a0),%d1
    ext.w   %d1
    add.w   %d1,%d0
    move.w  (LINEA_GCURY).l,%d1
    move.b  MOUSE_PACKET_DY(%a0),%d3
    ext.w   %d3
    add.w   %d3,%d1
    bsr.s   vdi_rom_clamp_mouse
    movea.l (LINEA_USER_MOT).l,%a1
    jsr     (%a1)
    bsr.s   vdi_rom_clamp_mouse
    move.w  %d0,(LINEA_GCURX).l
    move.w  %d1,(LINEA_GCURY).l
    movea.l (LINEA_USER_CUR).l,%a1
    jsr     (%a1)
.Lisr_restore:
    movem.l (%sp)+,%d0-%a6
.Lisr_done:
    rts

/* ---- $fcfedc — clamp_mouse: D0/D1 held to DEV_TAB's last column and row ------------------------------ */
    .globl  vdi_rom_clamp_mouse
vdi_rom_clamp_mouse:
    tst.w   %d0
    bge.s   .Lclamp_x_high
    clr.w   %d0
    bra.s   .Lclamp_y
.Lclamp_x_high:
    cmp.w   (LINEA_DEV_TAB + VDI_DEV_TAB_MAX_X_INDEX * VDI_WORD_BYTES).l,%d0
    ble.s   .Lclamp_y
    move.w  (LINEA_DEV_TAB + VDI_DEV_TAB_MAX_X_INDEX * VDI_WORD_BYTES).l,%d0
.Lclamp_y:
    tst.w   %d1
    bge.s   .Lclamp_y_high
    clr.w   %d1
    rts
.Lclamp_y_high:
    cmp.w   (LINEA_DEV_TAB + VDI_DEV_TAB_MAX_Y_INDEX * VDI_WORD_BYTES).l,%d1
    ble.s   .Lclamp_done
    move.w  (LINEA_DEV_TAB + VDI_DEV_TAB_MAX_Y_INDEX * VDI_WORD_BYTES).l,%d1
.Lclamp_done:
    rts

/* ---- $fcff0a — USER_CUR's default: (D0, D1) queued for the VBL while the cursor shows, masked -------- */
    .globl  vdi_rom_default_user_cur
vdi_rom_default_user_cur:
    tst.w   (LINEA_M_HID_CT).l
    bne.s   .Lqueue_done
    move.w  %sr,-(%sp)
    ori.w   #0x700,%sr
    lea     (LINEA_CUR_X).l,%a0
    move.w  %d0,(%a0)+
    move.w  %d1,(%a0)+
    bset    #CUR_FLAG_MOVED_BIT,(%a0)
    move.w  (%sp)+,%sr
.Lqueue_done:
    rts

/* ---- $fcff2a — _vblqueue[0]: the queued position redrawn ------------------------------------------- */
    .globl  vdi_rom_vbl_draw_cursor
vdi_rom_vbl_draw_cursor:
    tst.b   (LINEA_MOUSE_FLAG).l
    bne.s   .Lvbl_done
    bclr    #CUR_FLAG_MOVED_BIT,(LINEA_CUR_FLAG).l
    beq.s   .Lvbl_done
    move.l  (LINEA_CUR_X).l,%d1
    move.l  %d1,%d0
    swap    %d0
    movem.w %d0-%d1,-(%sp)
    lea     (LINEA_SAVE_BLOCK).l,%a2
    bsr.w   linea_rom_undraw_sprite
    movem.w (%sp)+,%d0-%d1
    lea     (LINEA_M_POS_HX).l,%a0
    lea     (LINEA_SAVE_BLOCK).l,%a2
    bsr.s   linea_rom_draw_sprite
.Lvbl_done:
    rts

/* ---- $fcff68..$fcffaf — where the ROM keeps vex_butv / vex_motv / vex_curv, whose C ships
 * (`src/vdi/attributes.c`): NOT their instructions, which nothing here executes, but as many bytes of
 * nothing, so the VBL's `bsr.s` over them keeps the ROM's displacement to draw_sprite ------------------ */
    .space  VEX_EXCHANGES_BYTES

/* ==== $fcffb0 — $a00d draw_sprite: A0 form, A2 save block, D0/D1 position ============================= */
#define SPRITE_OPS_XOR_OFFSET  16       /* the four XOR fragments' offset in the op table */
#define SPRITE_CLIP_LEFT       8        /* the store/loop pair for a sprite clipped at the left */
#define SPRITE_CLIP_RIGHT      16       /* ...and at the right */
#define SPRITE_EDGE            15       /* the last x (y) all sixteen columns (rows) fit at: max - 15 */
#define SPRITE_SHIFT_BY_ROL    8        /* from 8 pixels in, the spread is a `rol.l` of 16 - x */
#define SPRITE_FORM_ROW_SHIFT  2        /* rows * 4: a form row's bytes */
#define SPRITE_OP_TOP_BITS     3        /* `roxl.w #3`: fg to bit 3, bg to bit 2 */
    .globl  linea_rom_draw_sprite
linea_rom_draw_sprite:
    move.w  SPRITE_FORM_BG(%a0),-(%sp)
    move.w  SPRITE_FORM_FG(%a0),-(%sp)
    clr.w   %d2
    tst.w   SPRITE_FORM_PLANES(%a0)
    bge.s   .Ldraw_mode
    moveq   #SPRITE_OPS_XOR_OFFSET,%d2
.Ldraw_mode:
    move.w  %d2,-(%sp)
    clr.w   %d2
    bclr    #SPRITE_SAVE_LONG_BIT,SPRITE_SAVE_STAT(%a2)
    .word   M68K_SUB_W_D16(0, 0), SPRITE_FORM_HOT_X             /* sub.w 0(a0),d0 */
    bcs.s   .Ldraw_clip_left
    move.w  (LINEA_DEV_TAB + VDI_DEV_TAB_MAX_X_INDEX * VDI_WORD_BYTES).l,%d3
    .word   M68K_SUB_W_IMMEDIATE(3), SPRITE_EDGE                 /* sub.w #SPRITE_EDGE,d3 */
    cmp.w   %d3,%d0
    bhi.s   .Ldraw_clip_right
    bset    #SPRITE_SAVE_LONG_BIT,SPRITE_SAVE_STAT(%a2)
    bra.s   .Ldraw_y
.Ldraw_clip_left:
    .word   M68K_ADD_W_IMMEDIATE(0), SPRITE_ROWS                 /* add.w #SPRITE_ROWS,d0 */
    moveq   #SPRITE_CLIP_LEFT,%d2
    bra.s   .Ldraw_y
.Ldraw_clip_right:
    moveq   #SPRITE_CLIP_RIGHT,%d2
.Ldraw_y:
    sub.w   SPRITE_FORM_HOT_Y(%a0),%d1
    lea     SPRITE_FORM_ROWS(%a0),%a0
    bcs.s   .Ldraw_clip_top
    move.w  (LINEA_DEV_TAB + VDI_DEV_TAB_MAX_Y_INDEX * VDI_WORD_BYTES).l,%d3
    .word   M68K_SUB_W_IMMEDIATE(3), SPRITE_EDGE                 /* sub.w #SPRITE_EDGE,d3 */
    cmp.w   %d3,%d1
    bhi.s   .Ldraw_clip_bottom
    moveq   #SPRITE_ROWS,%d5
    bra.s   .Ldraw_place
.Ldraw_clip_top:
    move.w  %d1,%d5
    .word   M68K_ADD_W_IMMEDIATE(5), SPRITE_ROWS                 /* add.w #SPRITE_ROWS,d5 */
    asl.w   #SPRITE_FORM_ROW_SHIFT,%d1
    suba.w  %d1,%a0
    clr.w   %d1
    bra.s   .Ldraw_place
.Ldraw_clip_bottom:
    move.w  (LINEA_DEV_TAB + VDI_DEV_TAB_MAX_Y_INDEX * VDI_WORD_BYTES).l,%d5
    sub.w   %d1,%d5
    addq.w  #1,%d5
.Ldraw_place:
    bsr.w   linea_rom_concat
    movea.l (SYSVAR_V_BAS_AD).l,%a1
    adda.w  %d1,%a1
    lea     (.Ldraw_spread_right).l,%a3
    move.w  %d0,%d6
    .word   M68K_CMP_W_IMMEDIATE(6), SPRITE_SHIFT_BY_ROL         /* cmp.w #SPRITE_SHIFT_BY_ROL,d6 */
    bcs.s   .Ldraw_fragments
    lea     (.Ldraw_spread_left).l,%a3
    move.w  #SPRITE_ROWS,%d6
    sub.w   %d0,%d6
.Ldraw_fragments:
    movea.l .Ldraw_row_table(%pc,%d2.w),%a5
    movea.l .Ldraw_row_table+4(%pc,%d2.w),%a6
    move.w  (LINEA_PLANES).l,%d2
    move.w  %d2,%d3
    add.w   %d3,%d3
    move.w  (LINEA_WIDTH).l,%d4
    move.l  %a1,SPRITE_SAVE_ADDR(%a2)
    .word   M68K_MOVE_W_TO_D16(5, 2), SPRITE_SAVE_LEN            /* move.w d5,0(a2) */
    bset    #SPRITE_SAVE_VALID_BIT,SPRITE_SAVE_STAT(%a2)
    lea     SPRITE_SAVE_AREA(%a2),%a2
    move.l  %a1,%d7
    move.w  %d5,%d1
    bra.s   .Ldraw_next_plane
/* Per clip: the store fragment, and the row loop's entry — its own `dbf`. */
.Ldraw_row_table:
    .long   .Ldraw_store_both, .Ldraw_rows_both
    .long   .Ldraw_store_low, .Ldraw_rows_low
    .long   .Ldraw_store_high, .Ldraw_rows_high
.Ldraw_plane:
    clr.w   %d0
    lsr.w   2(%sp)
    addx.w  %d0,%d0
    lsr.w   4(%sp)
    roxl.w  #SPRITE_OP_TOP_BITS,%d0
    .word   M68K_ADD_W_D16(7, 0), 0                              /* add.w 0(sp),d0 */
    movea.l .Ldraw_op_table(%pc,%d0.w),%a4
    movem.l %d1-%d2,-(%sp)
    jsr     (%a6)
    movem.l (%sp)+,%d1-%d2
    move.w  %d1,%d5
    lsl.w   #SPRITE_FORM_ROW_SHIFT,%d5
    suba.w  %d5,%a0
    move.w  %d1,%d5
    addq.l  #2,%d7
    movea.l %d7,%a1
.Ldraw_next_plane:
    dbf     %d2,.Ldraw_plane
    addq.l  #6,%sp
    rts
/* By (XOR, fg, bg): the combine fragment. */
.Ldraw_op_table:
    .long   .Ldraw_op_clear, .Ldraw_op_mask, .Ldraw_op_data, .Ldraw_op_both
    .long   .Ldraw_op_xor_clear, .Ldraw_op_xor_mask, .Ldraw_op_xor_data, .Ldraw_op_xor_both
/* Two groups a row: both screen words saved as a longword, both stored. */
.Ldraw_row_both:
    move.w  (%a1),%d2
    swap    %d2
    move.w  0(%a1,%d3.w),%d2
    move.l  %d2,(%a2)+
    jmp     (%a3)
.Ldraw_store_both:
    move.w  %d2,0(%a1,%d3.w)
    swap    %d2
    move.w  %d2,(%a1)
    adda.w  %d4,%a1
.Ldraw_rows_both:
    dbf     %d5,.Ldraw_row_both
    rts
/* Clipped at the left: the right-hand group, the spread's low word. */
.Ldraw_row_low:
    move.w  (%a1),%d2
    move.w  %d2,(%a2)+
    jmp     (%a3)
.Ldraw_store_low:
    move.w  %d2,(%a1)
    adda.w  %d4,%a1
.Ldraw_rows_low:
    dbf     %d5,.Ldraw_row_low
    rts
/* Clipped at the right: the left-hand group, the spread's high word. */
.Ldraw_row_high:
    move.w  (%a1),%d2
    move.w  %d2,(%a2)+
    swap    %d2
    jmp     (%a3)
.Ldraw_store_high:
    swap    %d2
    move.w  %d2,(%a1)
    adda.w  %d4,%a1
.Ldraw_rows_high:
    dbf     %d5,.Ldraw_row_high
    rts
/* The mask and data words spread over the two groups: `rol.l` of 16 - x from 8 pixels in, else `ror.l`. */
.Ldraw_spread_left:
    moveq   #0,%d0
    move.w  (%a0)+,%d0
    rol.l   %d6,%d0
    moveq   #0,%d1
    move.w  (%a0)+,%d1
    rol.l   %d6,%d1
    jmp     (%a4)
.Ldraw_spread_right:
    moveq   #0,%d0
    move.w  (%a0)+,%d0
    swap    %d0
    ror.l   %d6,%d0
    moveq   #0,%d1
    move.w  (%a0)+,%d1
    swap    %d1
    ror.l   %d6,%d1
    jmp     (%a4)
/* The eight combines: D0 the mask, D1 the data, D2 the screen. */
.Ldraw_op_clear:
    not.l   %d0
    and.l   %d0,%d2
    not.l   %d1
    and.l   %d1,%d2
    jmp     (%a5)
.Ldraw_op_mask:
    or.l    %d0,%d2
    not.l   %d1
    and.l   %d1,%d2
    jmp     (%a5)
.Ldraw_op_data:
    not.l   %d0
    and.l   %d0,%d2
    or.l    %d1,%d2
    jmp     (%a5)
.Ldraw_op_both:
    or.l    %d0,%d2
    or.l    %d1,%d2
    jmp     (%a5)
.Ldraw_op_xor_clear:
    eor.l   %d1,%d2
    not.l   %d0
    and.l   %d0,%d2
    jmp     (%a5)
.Ldraw_op_xor_mask:
    or.l    %d0,%d2
    eor.l   %d1,%d2
    jmp     (%a5)
.Ldraw_op_xor_data:
    not.l   %d0
    and.l   %d0,%d2
    eor.l   %d1,%d2
    jmp     (%a5)
.Ldraw_op_xor_both:
    eor.l   %d0,%d2
    or.l    %d1,%d2
    jmp     (%a5)

/* ==== $fd0184 — $a00c undraw_sprite: A2 the save block ============================================= */
#define UNDRAW_PLANES_TWO      2
    .globl  linea_rom_undraw_sprite
linea_rom_undraw_sprite:
    bclr    #SPRITE_SAVE_VALID_BIT,SPRITE_SAVE_STAT(%a2)
    beq.w   .Lundraw_done
    .word   M68K_MOVE_W_D16(2, 4), SPRITE_SAVE_LEN               /* move.w 0(a2),d4 */
    move.w  %d4,%d2
    subq.w  #1,%d2
    move.w  (LINEA_WIDTH).l,%d3
    movea.l SPRITE_SAVE_ADDR(%a2),%a0
    lea     SPRITE_SAVE_AREA(%a2),%a1
    move.w  (LINEA_PLANES).l,%d5
    subq.w  #UNDRAW_PLANES_TWO,%d5
    bhi.s   .Lundraw_four
    beq.s   .Lundraw_two
    btst    #SPRITE_SAVE_LONG_BIT,SPRITE_SAVE_STAT(%a2)
    bne.s   .Lundraw_one_long
.Lundraw_one_word:
    move.w  (%a1)+,(%a0)
    adda.w  %d3,%a0
    dbf     %d2,.Lundraw_one_word
    rts
.Lundraw_one_long:
    move.l  (%a1)+,(%a0)
    adda.w  %d3,%a0
    dbf     %d2,.Lundraw_one_long
    rts
.Lundraw_two:
    movea.l %a0,%a5
    add.w   %d4,%d4
    btst    #SPRITE_SAVE_LONG_BIT,SPRITE_SAVE_STAT(%a2)
    bne.s   .Lundraw_two_long
    movea.l %a1,%a2
    adda.w  %d4,%a2
.Lundraw_two_word:
    move.w  (%a1)+,(%a0)+
    move.w  (%a2)+,(%a0)
    adda.w  %d3,%a5
    movea.l %a5,%a0
    dbf     %d2,.Lundraw_two_word
    rts
.Lundraw_two_long:
    movea.l %a1,%a2
    adda.w  %d4,%a2
    adda.w  %d4,%a2
.Lundraw_two_long_row:
    move.w  (%a1)+,(%a0)+
    move.w  (%a2)+,(%a0)+
    move.w  (%a1)+,(%a0)+
    move.w  (%a2)+,(%a0)
    adda.w  %d3,%a5
    movea.l %a5,%a0
    dbf     %d2,.Lundraw_two_long_row
    rts
.Lundraw_four:
    movea.l %a0,%a5
    add.w   %d4,%d4
    btst    #SPRITE_SAVE_LONG_BIT,SPRITE_SAVE_STAT(%a2)
    bne.s   .Lundraw_four_long
    movea.l %a1,%a2
    adda.w  %d4,%a2
    movea.l %a2,%a3
    adda.w  %d4,%a3
    movea.l %a3,%a4
    adda.w  %d4,%a4
.Lundraw_four_word:
    move.w  (%a1)+,(%a0)+
    move.w  (%a2)+,(%a0)+
    move.w  (%a3)+,(%a0)+
    move.w  (%a4)+,(%a0)
    adda.w  %d3,%a5
    movea.l %a5,%a0
    dbf     %d2,.Lundraw_four_word
    rts
.Lundraw_four_long:
    add.w   %d4,%d4
    movea.l %a1,%a2
    adda.w  %d4,%a2
    movea.l %a2,%a3
    adda.w  %d4,%a3
    movea.l %a3,%a4
    adda.w  %d4,%a4
.Lundraw_four_long_row:
    move.w  (%a1)+,(%a0)+
    move.w  (%a2)+,(%a0)+
    move.w  (%a3)+,(%a0)+
    move.w  (%a4)+,(%a0)+
    move.w  (%a1)+,(%a0)+
    move.w  (%a2)+,(%a0)+
    move.w  (%a3)+,(%a0)+
    move.w  (%a4)+,(%a0)
    adda.w  %d3,%a5
    movea.l %a5,%a0
    dbf     %d2,.Lundraw_four_long_row
.Lundraw_done:
    rts

/* ==== $fd0254 — $a00a hide_mouse ================================================================== */
    .globl  linea_rom_hide_mouse
linea_rom_hide_mouse:
    addq.b  #1,(LINEA_MOUSE_FLAG).l
    addq.w  #1,(LINEA_M_HID_CT).l
    cmpi.w  #1,(LINEA_M_HID_CT).l
    bne.s   .Lhide_done
    move.l  %a6,-(%sp)
    lea     (LINEA_SAVE_BLOCK).l,%a2
    bsr.w   linea_rom_undraw_sprite
    movea.l (%sp)+,%a6
    clr.b   (LINEA_CUR_FLAG).l
.Lhide_done:
    subq.b  #1,(LINEA_MOUSE_FLAG).l
    rts

/* ==== $fd0286 — show_cursor: one shallower, drawn at GCURX/GCURY on reaching 0 ======================= */
    .globl  vdi_rom_show_cursor
vdi_rom_show_cursor:
    addq.b  #1,(LINEA_MOUSE_FLAG).l
    subq.w  #1,(LINEA_M_HID_CT).l
    bgt.s   .Lshow_done
    bmi.s   .Lshow_zero
    move.w  (LINEA_GCURX).l,%d0
    move.w  (LINEA_GCURY).l,%d1
    move.l  %a6,-(%sp)
    lea     (LINEA_M_POS_HX).l,%a0
    lea     (LINEA_SAVE_BLOCK).l,%a2
    bsr.w   linea_rom_draw_sprite
    movea.l (%sp)+,%a6
    clr.b   (LINEA_CUR_FLAG).l
.Lshow_zero:
    clr.w   (LINEA_M_HID_CT).l
.Lshow_done:
    subq.b  #1,(LINEA_MOUSE_FLAG).l
    rts

/* ==== $fd02ca — vsc_form (111), $a00b ============================================================= */
#define FORM_HOT_SPOT_MASK     15       /* four bits of each hot-spot coordinate */
#define FORM_DATA_FROM_MASK    30       /* `30(a0)` past the mask word just read: intin[21 + row] */
    .globl  vdi_rom_vsc_form
vdi_rom_vsc_form:
    addq.b  #1,(LINEA_MOUSE_FLAG).l
    movea.l (LINEA_INTIN).l,%a0
    lea     (LINEA_M_POS_HX).l,%a1
    move.w  (%a0)+,%d0
    .word   M68K_AND_W_IMMEDIATE(0), FORM_HOT_SPOT_MASK          /* and.w #FORM_HOT_SPOT_MASK,d0 */
    move.w  %d0,(LINEA_M_POS_HX).l
    move.w  (%a0)+,%d0
    .word   M68K_AND_W_IMMEDIATE(0), FORM_HOT_SPOT_MASK          /* and.w #FORM_HOT_SPOT_MASK,d0 */
    move.w  %d0,(LINEA_M_POS_HY).l
    move.w  (%a0)+,(LINEA_M_PLANES).l
    move.w  (%a0)+,%d0
    cmp.w   (LINEA_DEV_TAB + VDI_DEV_TAB_COLOURS_INDEX * VDI_WORD_BYTES).l,%d0
    bmi.s   .Lform_background
    moveq   #1,%d0
.Lform_background:
    movea.l #VDI_MAP_COL,%a1
    add.w   %d0,%d0
    move.w  0(%a1,%d0.w),(LINEA_M_CDB_BG).l
    move.w  (%a0)+,%d0
    cmp.w   (LINEA_DEV_TAB + VDI_DEV_TAB_COLOURS_INDEX * VDI_WORD_BYTES).l,%d0
    bmi.s   .Lform_foreground
    moveq   #1,%d0
.Lform_foreground:
    add.w   %d0,%d0
    move.w  0(%a1,%d0.w),(LINEA_M_CDB_FG).l
    moveq   #SPRITE_ROWS - 1,%d0
    lea     (LINEA_MASK_FORM).l,%a1
.Lform_row:
    move.w  (%a0)+,(%a1)+
    move.w  FORM_DATA_FROM_MASK(%a0),(%a1)+
    dbf     %d0,.Lform_row
    subq.b  #1,(LINEA_MOUSE_FLAG).l
    rts

/* ==== $fca7c0 — poll_choice: TERM_CH = 1, D0 the caller's ========================================== */
    .globl  vdi_rom_poll_choice
vdi_rom_poll_choice:
    move.w  #TERM_CH_CHOICE,(LINEA_TERM_CH).l
    rts

/* ==== $fca88a — poll_locator: a changed button, else a key, else the moved bit ======================= */
#define TERM_CH_SCANCODE_SHIFT 8
    .globl  vdi_rom_poll_locator
vdi_rom_poll_locator:
    move.b  (LINEA_CUR_MS_STAT).l,%d0
    move.b  %d0,%d1
    andi.b  #MOUSE_STAT_CHANGED_MASK,%d0
    beq.s   .Llocator_keyboard
    move.b  %d1,%d0
    btst    #MOUSE_STAT_LEFT_CHANGED_BIT,%d0
    beq.s   .Llocator_right
    move.w  #TERM_CH_LEFT_BUTTON,(LINEA_TERM_CH).l
    bra.s   .Llocator_button_kept
.Llocator_right:
    move.w  #TERM_CH_RIGHT_BUTTON,(LINEA_TERM_CH).l
.Llocator_button_kept:
    andi.b  #MOUSE_STAT_KEPT_MASK,%d0
    move.b  %d0,(LINEA_CUR_MS_STAT).l
    moveq   #POLL_TERMINATED,%d0
    rts
.Llocator_keyboard:
    move.w  #CONSOLE_DEVICE,-(%sp)
    move.w  #BIOS_CONSOLE_STATUS,-(%sp)
    trap    #13
    tst.w   %d0
    bne.s   .Llocator_key
    addq.l  #MOUSE_BIOS_FRAME_BYTES,%sp
    bra.s   .Llocator_motion
.Llocator_key:
    move.w  #BIOS_CONSOLE_INPUT,(%sp)
    trap    #13
    addq.l  #MOUSE_BIOS_FRAME_BYTES,%sp
    move.l  %d0,%d1
    swap    %d1
    lsl.w   #TERM_CH_SCANCODE_SHIFT,%d1
    or.w    %d1,%d0
    move.w  %d0,(LINEA_TERM_CH).l
    moveq   #POLL_TERMINATED,%d0
    rts
.Llocator_motion:
    bclr    #MOUSE_STAT_MOVED_BIT,%d1
    beq.s   .Llocator_nothing
    move.b  %d1,(LINEA_CUR_MS_STAT).l
    move.w  (LINEA_GCURX).l,(LINEA_X1).l
    move.w  (LINEA_GCURY).l,(LINEA_Y1).l
    moveq   #POLL_MOVED,%d0
    rts
.Llocator_nothing:
    moveq   #POLL_NOTHING,%d0
    rts
