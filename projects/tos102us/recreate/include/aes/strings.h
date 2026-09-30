/* aes/strings.h — the utility layer's MEMORY and STRING helpers (`src/aes/strings.c`, shipped as `src/aes/optimize.S`):
 * the copies, fills, compares, the 8.3 name formatters, the `%`-template merge and the wildcard match both the AES and
 * the desk call, and the Alcyon runtime's long multiply and divide the merge reaches.
 *
 * Hand 68000 in the ROM ("optimize", `$fecb5a..$fed3bd`), called like Alcyon C — a Line-F call (or, from the Line-A
 * mouse-form save, a `jsr`) over a frame of words and longwords, in push order below — and returning by `rts`, so no
 * Line-F return and no mask word. What each answers, and at what width, is the ROM's register, not C's habit:
 *   * a WORD in D0 (`int16_t`): the count, the compare, the flag. Several leave D0's HIGH word as the caller's
 *     (`clr.w d0`, `move.w`), which every caller ignores (`tst.w d0`, `move.w d0,…`);
 *   * a LONGWORD in D0 (`uint32_t`): the four that answer a POINTER into the string they walked (`move.l a1,d0`),
 *     and the runtime's two;
 *   * nothing (`void`): the copies and fills, which leave D0 as their loop left it and no caller reads.
 * Every string and buffer pointer is a caller's longword, so it is put on the 24-bit bus per byte (`bus_dereference`)
 * while an ANSWERED pointer keeps whatever top byte it came in with, as the register does. A word argument is taken
 * as the signed word the frame holds and read as the ROM reads it (a count unsigned, a character's low byte).
 *
 * The constants below are read by the C and the `.S` alike.
 */
#ifndef TOS102US_AES_STRINGS_H
#define TOS102US_AES_STRINGS_H

/* ---- the bytes the string routines test for ---------------------------------------------------------------- */
#define STRING_NUL            0x00
#define STRING_SPACE          0x20
#define STRING_PERCENT        0x25    /* merge_str's code introducer */
#define STRING_WILDCARD_ANY   0x2a    /* wildcmp's `*` */
#define STRING_DOT            0x2e    /* the 8.3 separator */
#define STRING_WILDCARD_ONE   0x3f    /* wildcmp's `?` */
#define TOUPPER_FIRST         0x61    /* 'a' ($fece7a cmp.w #97) */
#define TOUPPER_LAST          0x7a    /* 'z' ($fece80 cmp.w #122) */
#define TOUPPER_DISTANCE      (-32)   /* ($fece86 add.w #-32) */
#define FMT_NAME_BYTES        8       /* the 8 of 8.3: fmt_str's and unfmt_str's `dbf` from 7 */
/* merge_str's codes, and how it lays a number out */
#define MERGE_CODE_LONG       0x4c    /* 'L': a longword slot in decimal, signed through ldiv */
#define MERGE_CODE_STRING     0x53    /* 'S': the string a slot points at */
#define MERGE_CODE_WORD       0x57    /* 'W': the FIRST word of a slot, unsigned */
#define MERGE_SLOT_BYTES      4       /* every parameter takes a longword slot, %W's too ($fed0b8 addq.w #4) */
#define MERGE_DIGITS_BYTES    16      /* the digit buffer on its stack ($fed0d4 suba.l #16,sp) */
#define DECIMAL_BASE          10
#define DIGIT_ZERO            0x30    /* '0' */
/* ldiv ($fe3e08): a dividend below this is divided by one `divu.w`, one at or above it bit by bit */
#define LDIV_ONE_DIVIDE_BELOW 0x10000
#define LDIV_BY_ZERO_REMAINDER 0x80000000    /* what it leaves at AES_LDIV_REMAINDER before `divs.w #0` */

#ifndef __ASSEMBLER__
#include <stdint.h>

/* ---- arithmetic, and the VDI contrl[] pointer slots --------------------------------------------------------- */
int16_t aes_mul_div(int16_t multiplicand, int16_t multiplier, int16_t divisor);                          /* $fecb6e */
void aes_set_contrl_ptr(uint8_t *image, uint32_t pointer);                                               /* $fecbc6 */
void aes_get_contrl_ptr2(uint8_t *image, uint32_t answer);                                               /* $fecbda */
int16_t aes_min(int16_t left, int16_t right);                                                            /* $fece42 */
int16_t aes_max(int16_t left, int16_t right);                                                            /* $fece4e */
int16_t aes_toupper(int16_t character);                                                                  /* $fece74 */
int32_t aes_lmul(int32_t multiplicand, int32_t multiplier);                                              /* $fe3db4 */
int32_t aes_ldiv(uint8_t *image, int32_t dividend, int32_t divisor);                                     /* $fe3e08 */

/* ---- copies and fills: (destination, source, count) in the "large" helpers, (count, …) in the optimize ones --- */
int16_t aes_lstcpy(uint8_t *image, uint32_t destination, uint32_t source);                               /* $fecbe6 */
int16_t aes_xstrpix(uint8_t *image, uint32_t destination, uint32_t source);                              /* $fecbfa */
void aes_wset(uint8_t *image, uint32_t destination, int16_t words, int16_t value);                       /* $fecc12 */
void aes_xstrpix_n(uint8_t *image, uint32_t destination, uint32_t source, int16_t bytes);                /* $fecc28 */
void aes_wcopy(uint8_t *image, uint32_t destination, uint32_t source, int16_t words);                    /* $fecc40 */
void aes_wfill(uint8_t *image, uint32_t destination, int16_t words, int16_t value);                      /* $fecc56 */
int16_t aes_lstrlen(uint8_t *image, uint32_t string);                                                    /* $fecc6c */
void aes_lbcopy(uint8_t *image, uint32_t destination, uint32_t source, int16_t bytes);                   /* $fecc7e */
void aes_movs(uint8_t *image, int16_t bytes, uint32_t source, uint32_t destination);                     /* $fece2e */
void aes_bfill(uint8_t *image, int16_t bytes, int16_t value, uint32_t destination);                      /* $fece5e */

/* ---- strings: (source, destination) in the optimize ones --------------------------------------------------- */
int16_t aes_strlen(uint8_t *image, uint32_t string);                                                     /* $fece8c */
int16_t aes_streq(uint8_t *image, uint32_t left, uint32_t right);                                        /* $fece9c */
uint32_t aes_strcpy(uint8_t *image, uint32_t source, uint32_t destination);                              /* $feceb8 */
uint32_t aes_strscn(uint8_t *image, uint32_t source, uint32_t destination, int16_t stop);               /* $fecec4 */
uint32_t aes_strcat(uint8_t *image, uint32_t source, uint32_t destination);                              /* $feceda */
uint32_t aes_scasb(uint8_t *image, uint32_t string, int16_t character);                                  /* $feceee */
int16_t aes_strchk(uint8_t *image, uint32_t left, uint32_t right);                                       /* $fecf02 */
void aes_fmt_str(uint8_t *image, uint32_t source, uint32_t destination);                                 /* $fecf24 */
void aes_unfmt_str(uint8_t *image, uint32_t source, uint32_t destination);                               /* $fecf58 */
void aes_merge_str(uint8_t *image, uint32_t destination, uint32_t template, uint32_t parameters);        /* $fed070 */
int16_t aes_wildcmp(uint8_t *image, uint32_t pattern, uint32_t name);                                    /* $fed12e */
#endif

#endif /* TOS102US_AES_STRINGS_H */
