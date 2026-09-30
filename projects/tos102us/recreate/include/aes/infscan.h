/* aes/infscan.h — the INF SCAN helpers (`src/aes/infscan.c`): the two-hex-digit fields of DESKTOP.INF, read and
 * written. Shared by the AES's own `#E` reader (gem_read_inf_E, $fda408) and the desk's INF parser and writer.
 *
 * ALCYON C, entered by a Line-F call over its caller's frame — a character or digit as a WORD (an Alcyon `int`), a
 * text cursor as a LONGWORD — and answering in D0: a WORD for the digit converters, the ADVANCED CURSOR as a whole
 * LONGWORD for the field scanners (`move.l a5,d0` / `move.l 8(a6),d0`: a pointer handed back with whatever top
 * byte it came in with, which the desk stores and walks on).
 */
#ifndef TOS102US_AES_INFSCAN_H
#define TOS102US_AES_INFSCAN_H

#include <stdint.h>

/* The INF text's digits and separator. */
#define INF_DECIMAL_BASE      10         /* the first letter digit's value      ($fdaf52 add.w #-55: 'A' - 10) */
#define INF_FIELD_SEPARATOR   ' '        /* after every field                   ($fdb006 move.b #32)            */
#define INF_NOT_A_DIGIT       ' '        /* uhex_dig of a value past 15         ($fdaf8e moveq #32)             */
#define INF_UNSET_FIELD       0xff       /* scan_2's "ff": answered as -1       ($fdafba cmp.w #255)            */
#define INF_UNSET_VALUE       (-1)       /*                                     ($fdafc0 moveq #-1)             */
#define INF_FIELD_DIGITS      2          /* a field's two hex digits            ($fdafa4, $fdafb0)              */
#define INF_FIELD_BYTES       3          /* ...and its separator: the cursor's advance ($fdafc4 addq.l #1)     */
#define INF_DIGIT_BITS        4          /* a hex digit                         ($fdafac asl.w #4)              */
#define INF_DIGIT_MASK        0x000f     /*                                     ($fdafda andi.w #15)            */

int16_t aes_hex_dig(int16_t character);                                                                 /* $fdaf20 */
int16_t aes_uhex_dig(int16_t digit);                                                                    /* $fdaf5c */
uint32_t aes_scan_2(uint8_t *image, uint32_t cursor, uint32_t value_out);                               /* $fdaf92 */
uint32_t aes_save_2(uint8_t *image, uint32_t cursor, int16_t value);                                   /* $fdafca */

#endif /* TOS102US_AES_INFSCAN_H */
