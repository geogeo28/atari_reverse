/* vdi/mouse.h — the MOUSE, CURSOR and INPUT routines (`src/vdi/mouse.c`, `src/vdi/mouse.S`).
 *
 *   $fcffb0 $a00d draw_sprite     $fd0184 $a00c undraw_sprite    $fd0254 $a00a hide_mouse
 *   $fd0286 show_cursor           $fcb120 $a009 v_show_c (122)   $fcb148 v_hide_c (123)
 *   $fd02ca $a00b vsc_form (111)  $fcfe28 mouse_isr (mousevec)   $fcff0a default_user_cur
 *   $fcff2a vbl_draw_cursor       $fca7f8 mouse_init / $fca872 mouse_off
 *   $fca88a / $fca7c0 / $fca7ca   the locator, choice and keyboard polls
 *   $fcb002 / $fcb1a0 / $fcb22a   vdi_locator (28), vdi_choice (30), vdi_string (31)
 *
 * THE REGISTER CONTRACTS are `test/vdi_mouse.py`'s `declare_primitive`s, and a core's arguments are the
 * registers named there, in that order.
 */
#ifndef TOS102US_VDI_MOUSE_H
#define TOS102US_VDI_MOUSE_H

#include "vdi/linea.h"

/* ---- a SPRITE FORM, as $a00d reads it through A0 --------------------------------------------------
 * The layout LINEA_M_POS_HX onwards has, which is the form every ROM caller hands it ($fcff58, $fd02a4);
 * a Line-A caller may hand any block of this shape. */
#define SPRITE_FORM_HOT_X      0         /* word                                ($fcffcc sub.w 0(a0)) */
#define SPRITE_FORM_HOT_Y      2         /* word                                ($fcfff2)           */
#define SPRITE_FORM_PLANES     4         /* word: NEGATIVE draws by XOR         ($fcffba tst.w)     */
#define SPRITE_FORM_BG         6         /* word: the mask's colour             ($fcffb0)           */
#define SPRITE_FORM_FG         8         /* word: the data's colour             ($fcffb4)           */
#define SPRITE_FORM_ROWS       10        /* 16 x (mask word, data word)         ($fcfff6 lea 10(a0)) */
#define SPRITE_FORM_ROW_BYTES  4
#define SPRITE_ROWS            16        /* rows a form has; its width in pixels too ($fd000a moveq) */

/* ---- a SAVE BLOCK, as the pair reaches it through A2 (LINEA_SAVE_BLOCK is the one the ROM uses) ---- */
#define SPRITE_SAVE_LEN        (LINEA_SAVE_LEN - LINEA_SAVE_BLOCK)
#define SPRITE_SAVE_ADDR       (LINEA_SAVE_ADDR - LINEA_SAVE_BLOCK)
#define SPRITE_SAVE_STAT       (LINEA_SAVE_STAT - LINEA_SAVE_BLOCK)
#define SPRITE_SAVE_AREA       (LINEA_SAVE_AREA - LINEA_SAVE_BLOCK)
#define SPRITE_SAVE_VALID_BIT  0         /* a save to restore                   ($fd006c, $fd0184)  */
#define SPRITE_SAVE_LONG_BIT   1         /* two words a row, not one            ($fcffe0, $fd01b0)  */

/* ---- CUR_MS_STAT's bits and the IKBD's relative mouse packet --------------------------------------- */
#define MOUSE_PACKET_HEADER_MASK 0xf8    /* a relative packet's header is $f8..$fb ($fcfe3a)        */
#define MOUSE_PACKET_BUTTONS_MASK 0x03   /* right button bit 0, left bit 1 — SWAPPED on the way in  */
#define MOUSE_PACKET_DX        1         /* signed byte                         ($fcfea0)           */
#define MOUSE_PACKET_DY        2         /* signed byte                         ($fcfeae)           */
#define MOUSE_STAT_BUTTONS_MASK 0x03     /* the buttons as the VDI numbers them ($fcfe58)           */
#define MOUSE_STAT_MOVED_BIT   5         /* the last packet moved the mouse     ($fcfe92 bset)      */
#define MOUSE_STAT_CHANGED_MASK 0xc0     /* a button changed: bit 6 left, bit 7 right ($fca892)     */
#define MOUSE_STAT_LEFT_CHANGED_BIT 6    /* ($fca89a btst #6)                                       */
#define MOUSE_STAT_KEPT_MASK   0x23      /* what the locator's button arm leaves ($fca8b2 andi.b)   */
#define CUR_FLAG_MOVED_BIT     0         /* LINEA_CUR_FLAG: a position queued   ($fcff22 bset)      */

/* ---- the input polls' answers and TERM_CH's values --------------------------------------------------- */
#define POLL_NOTHING           0
#define POLL_TERMINATED        1         /* a key, or a button                  ($fca8bc moveq #1)  */
#define POLL_MOVED             2         /* the mouse moved (the locator's)     ($fca90c moveq #2)  */
#define POLL_BOTH              3         /* the sample locator's fourth arm: no poll answers it     */
#define TERM_CH_LEFT_BUTTON    0x20      /* ($fca8a0)                                               */
#define TERM_CH_RIGHT_BUTTON   0x21      /* ($fca8aa)                                               */
#define TERM_CH_CHOICE         1         /* all the choice "device" ever answers ($fca7c0)          */
#define TERM_CH_ASCII_MASK     0x00ff    /* intout's key, unless a string's count was negative      */
#define TERM_CH_RETURN         13        /* ends a requested string             ($fcb29e cmpi.w)    */
#define CONSOLE_DEVICE         2         /* BIOS device 2, the keyboard         ($fca7ca)           */

/* ---- XBIOS Initmous as the two workstation calls make it --------------------------------------------- */
#define MOUSE_INITMOUS_UNUSED  0xffffffffu /* mouse_off's parameter block and vector ($fca87a moveq #-1) */

#ifndef __ASSEMBLER__
#include <stdint.h>

/* ---- the Line-A primitives and the register routines -------------------------------------------- */
void linea_draw_sprite(uint8_t *image, uint32_t form, uint32_t save_block, uint32_t x, uint32_t y);
void linea_undraw_sprite(uint8_t *image, uint32_t save_block);
void linea_hide_mouse(uint8_t *image);
void vdi_show_cursor(uint8_t *image);
/* KBDVECS' mousevec: A0 the packet, and the D0/D1 the IKBD handler left, whose HIGH words reach the
 * user vectors — the ISR only ever writes their low halves. */
void vdi_mouse_isr(uint8_t *image, uint32_t packet, uint32_t entry_d0, uint32_t entry_d1);
void vdi_default_user_cur(uint8_t *image, uint32_t x, uint32_t y);
void vdi_vbl_draw_cursor(uint8_t *image);
void vdi_mouse_init(uint8_t *image);
void vdi_mouse_off(uint8_t *image);
uint32_t vdi_poll_locator(uint8_t *image);
uint32_t vdi_poll_choice(uint8_t *image, uint32_t entry_d0);
uint32_t vdi_poll_key(uint8_t *image);

/* ---- the VDI functions ------------------------------------------------------------------------- */
void vdi_v_show_c(uint8_t *image);
void vdi_v_hide_c(uint8_t *image);
void vdi_vsc_form(uint8_t *image);
void vdi_locator(uint8_t *image);
void vdi_choice(uint8_t *image);
void vdi_string(uint8_t *image);
#endif /* __ASSEMBLER__ */

#endif /* TOS102US_VDI_MOUSE_H */
