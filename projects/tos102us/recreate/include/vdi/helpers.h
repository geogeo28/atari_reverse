/* vdi/helpers.h — the VDI's PURE HELPERS (`src/vdi/helpers.c`): the arithmetic, the clipping and scaling
 * leaves, the small copies, and `vr_trnfm`.
 *
 * HOW EACH IS CALLED is the ROM's, and there are two kinds:
 *   * most are ALCYON C CALLS — the caller pushes WORD arguments and reads the answer out of D0's LOW
 *     WORD, which is all an Alcyon `int` is. Every call site of these moves D0.w on (`move.w d0,...`,
 *     `add.w`, `or.w`), so an `int16_t` core is the whole contract: what the ROM leaves in D0's high
 *     word — a divide's remainder, the sum of squares, a caller's leftovers — reaches no caller, and the
 *     batteries compare D0 at 16 bits for exactly that reason (`test/vdi_helpers.py`);
 *   * three are REGISTER routines reached by `jsr` from hand 68000 — `sort_words`, `clamp_mouse` and
 *     `get_kbshift` — whose arguments and answers are the registers `test/vdi.py`'s `declare_primitive`
 *     names for them, with the caller's own high words handed back where the ROM leaves them.
 *
 * `vr_trnfm` is the one VDI FUNCTION here (opcode 110), `void` like every other (`vdi/vdi.h`).
 */
#ifndef TOS102US_VDI_HELPERS_H
#define TOS102US_VDI_HELPERS_H

/* ---- the text scaler's DDA ---------------------------------------------------------------------
 * `clc_dda` answers the increment `act_siz` steps by: a fraction of 65536, or — for a size at least
 * double the font's — this marker, which `act_siz` answers by doubling instead ($fcee14 cmp.w #-1). */
#define VDI_DDA_DOUBLE        0xffff     /* ($fcedea moveq #-1)                                     */
#define VDI_DDA_ACCUMULATOR_START 0x7fff /* half of 65536, so a step rounds     ($fcee0a)           */
/* LINEA_T_SCLSTS' two values: `clc_dda` stores one, `act_siz` tests bit 0 of the field's LOW byte
 * ($fcee20 `btst #0,$29df`), which is the same bit as the word's. */
#define VDI_SCALE_DOWN        0          /* ($fcedee clr.w)                                         */
#define VDI_SCALE_UP          1          /* ($fceddc move.w #1)                                     */
#define VDI_SCALE_UP_MASK     0x0001

#ifndef __ASSEMBLER__
#include <stdint.h>

#include "machine.h"

/* ---- the Alcyon C calls ------------------------------------------------------------------------- */
int16_t vdi_vec_len(int16_t dx, int16_t dy);                                   /* $fc9ffc */
int16_t vdi_smul_div(int16_t multiplicand, int16_t multiplier, int16_t divisor); /* $fca186 */
int16_t vdi_isin(const uint8_t *image, int16_t angle);                         /* $fcab68 */
int16_t vdi_icos(const uint8_t *image, int16_t angle);                         /* $fcac4c */
int16_t vdi_clip_code(const uint8_t *image, int16_t x, int16_t y);             /* $fcc092 */
/* ...its OUTCODE bits, which clip_line ($fcbf16) tests one by one (`btst #0..#3`). */
#define OUTCODE_LEFT          1
#define OUTCODE_RIGHT         2
#define OUTCODE_ABOVE         4
#define OUTCODE_BELOW         8
void vdi_clc_nsteps(uint8_t *image);                                           /* $fcc6b4 */
/* `x_out` / `y_out` are the image addresses the signed coordinates are stored at. */
void vdi_quad_xform(uint8_t *image, int16_t quadrant, int16_t x, int16_t y,
                    uint32_t x_out, uint32_t y_out);                           /* $fcced6 */
int16_t vdi_clc_dda(uint8_t *image, int16_t actual, int16_t requested);        /* $fcedd0 */
int16_t vdi_act_siz(const uint8_t *image, int16_t size);                       /* $fcee02 */
void vdi_copy_name(uint8_t *image, uint32_t source, uint32_t destination);     /* $fce0ee */
void vdi_font_byteswap(uint8_t *image);                                        /* $fcfaac */
void vdi_s_fa_attr(uint8_t *image);                                            /* $fcd056 */
void vdi_r_fa_attr(uint8_t *image);                                            /* $fcd0c2 */

/* ---- the register routines ---------------------------------------------------------------------- */
/* $fca164 — `count` words at `array` (D0.w, A0) sorted ascending, signed, in place. */
void vdi_sort_words(uint8_t *image, uint32_t count, uint32_t array);
/* $fcfedc — the mouse position (D0, D1) clamped to the screen: both answered, D0 returned and D0/D1
 * written to `results` in that order, each with the caller's high word. */
uint32_t vdi_clamp_mouse(const uint8_t *image, uint32_t x, uint32_t y, uint32_t *results);
/* $fca648 — the four modifier keys' bits of the shift state, in D0's low word over the caller's high. */
uint32_t vdi_get_kbshift(const uint8_t *image, uint32_t entry_d0);

/* $fcfa9c — GEMDOS `function`(`argument`) through the VDI's `trap #1` door, which parks its caller's
 * return address in LINEA_RETSAV first: `return_site` is that address, the instruction after the
 * caller's `jsr`. Every call the VDI makes through it is a function word and one longword — `Malloc`
 * (v_opnvwk, $fcd62a) and `Mfree` (v_clswk, $fcb9ca; v_clsvwk, $fcd6ee) — and D0 is the trap's answer. */
uint32_t vdi_gemdos_call(uint8_t *image, uint32_t return_site, uint16_t function, uint32_t argument);

/* ---- the VDI function --------------------------------------------------------------------------- */
void vdi_vr_trnfm(uint8_t *image);                                             /* $fd2d32, opcode 110 */

#endif /* __ASSEMBLER__ */

#endif /* TOS102US_VDI_HELPERS_H */
