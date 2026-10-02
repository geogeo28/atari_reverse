/* aes/obedit.h — THE OBJECT EDITOR (`src/aes/obedit.c`): ob_edit, objc_edit's arm and fm_do's field editor, and the
 * ten helpers of gemobed it calls — the TEDINFO copied out (ob_getsp), the template walked (find_pos, scan_to_end,
 * ob_stfn), the raw text edited (ins_char, ob_delit), a typed character validated (check, instr), and the cursor or a
 * stretch of the field redrawn (pxl_rect, curfld).
 *
 * ALCYON C, every routine entered by a Line-F call over its caller's frame (in push order below: a tree, a string or a
 * pointer a LONGWORD, an object, a position, a character or a count a WORD — an Alcyon `int`). What each answers is the
 * ROM's register at the width its callers read: find_pos, scan_to_end, instr, check, ob_delit and ob_edit a WORD; the
 * rest nothing a caller reads (each leaves D0 as its last callee or sum did).
 *
 * THE EDITOR WORKS ON COPIES, in the AES's globals beside just_draw's (`aes/objdraw.h`): the object's TEDINFO in
 * AES_EDBLK, its raw text in AES_RAWSTR, its template in AES_TMPLT (ODD: bytes only), its validation string in
 * AES_VALSTR — stretched to the template's length by repeating its last character — and the two merged by ob_format
 * into AES_FMTSTR. Only the raw text is copied back (into te_ptext) after a character is edited.
 *
 * Every field below carries one ROM access and the WIDTH TAG (`vdi/linea.h`, "THE WIDTH TAG"); `test/aes.py` parses
 * this header with `aes/aes.h`.
 */
#ifndef TOS102US_AES_OBEDIT_H
#define TOS102US_AES_OBEDIT_H

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

#include "aes/objdraw.h"

#define AES_VALSTR            0xb7f8     /* bytes[AES_TEXT_BUFFER_BYTES]: the validation string, one character a
                                            template placeholder ($fe96d4 lstcpy to a4+$1ba0)                      */

/* ob_edit's KINDS (objc_edit's ed_kind). EDSTART answers 1 and does nothing ($fe9692 tst.w 20(a6)); any kind past
 * EDEND does what EDEND does: the cursor drawn where the index lies ($fe996e..$fe9982). */
#define OB_EDIT_START         0
#define OB_EDIT_INIT          1          /* the index the raw text's end         ($fe996e cmp.w #1)            */
#define OB_EDIT_CHAR          2          /* a key edited in                      ($fe9976 cmp.w #2)            */
#define OB_EDIT_END           3          /* the cursor toggled off               ($fe997e cmp.w #3)            */
/* The keys EDCHAR tells apart — search table $fefb70, 5 keys and 0, every other key a character typed in. */
#define OB_EDIT_KEY_ESCAPE    0x011b     /* the field emptied                    (-> $fe97ac)                  */
#define OB_EDIT_KEY_BACKSPACE 0x0e08     /* the character before the index deleted (-> $fe979a)                */
#define OB_EDIT_KEY_LEFT      0x4b00     /* the index one left                   (-> $fe97d2)                  */
#define OB_EDIT_KEY_RIGHT     0x4d00     /* ...one right, up to the raw text's end (-> $fe97dc)                */
#define OB_EDIT_KEY_DELETE    0x537f     /* the character at the index deleted   (-> $fe97ba)                  */
#define OB_EDIT_ASCII_MASK    0x00ff     /* a typed key's character: its low byte ($fe980c and.w #255)         */
/* te_txtlen less this is the last index a character is typed or deleted at ($fe97c0, $fe97f8 subq.w #2): the length
 * counts the NUL, and the last place is kept free. */
#define OB_EDIT_TEXT_SPARE    2

/* check's VALIDATION CHARACTERS — search table $fefb10, 11 characters and 0 — and the AES resource's free string each
 * names (rs_str), the set a typed character must lie in. Upper-case sets also upcase the character; '9', 'a' and 'n'
 * do not ($fe9570 / $fe958e / $fe9594 clr.w d7). 'x' upcases anything, 'X' takes anything. */
#define VALID_DIGIT           0x39       /* '9' 0..9                     STNUM   ($fe956e moveq #4)            */
#define VALID_ALPHA           0x41       /* 'A' A..Z, space              STALPHA ($fe9574 moveq #5)            */
#define VALID_FILE            0x46       /* 'F' a file name, ':', '?', '*' STFILE ($fe9584 moveq #9)           */
#define VALID_ALPHANUMERIC    0x4e       /* 'N' 0..9, A..Z, space        STANUM  ($fe9578 moveq #6)            */
#define VALID_PATH            0x50       /* 'P' a path name              STPATH  ($fe957c moveq #7)            */
#define VALID_ANY             0x58       /* 'X' anything, as typed               (-> $fe95a6)                  */
#define VALID_LOWER_ALPHA     0x61       /* 'a' a..z, A..Z, space        STLALPHA ($fe958c moveq #11)          */
#define VALID_LOWER_FILE      0x66       /* 'f' a file name              STLFILE ($fe9588 moveq #10)           */
#define VALID_LOWER_ALPHANUMERIC 0x6e    /* 'n' 0..9, a..z, A..Z, space  STLANUM ($fe9592 moveq #12)           */
#define VALID_LOWER_PATH      0x70       /* 'p' a path name              STLPATH ($fe9580 moveq #8)            */
#define VALID_ANY_UPPER       0x78       /* 'x' anything, upcased                (-> $fe9598)                  */
#define STNUM                 4
#define STALPHA               5
#define STANUM                6
#define STPATH                7
#define STLPATH               8
#define STFILE                9
#define STLFILE               10
#define STLALPHA              11
#define STLANUM               12
#define CHECK_NO_SET          (-1)       /* no set to look the character up in  ($fe9564 moveq #-1, $fe95c2)  */
/* instr's RANGE: "a..z" in a set is every character from 'a' to 'z' ($fe9530 / $fe9536 cmpi.b #46 twice). */
#define INSTR_RANGE_DOT       0x2e

/* curfld's CURSOR: a line the cell's height and 3 pixels more above and below ($fe94c8 subq.w #3, $fe94cc addq.w #6),
 * drawn in XOR, black, so a second draw takes it off. */
#define CURSOR_ABOVE          3
#define CURSOR_GROWTH         6
#define CURSOR_COLOUR         1          /* black                                ($fe94ba move.w #1)            */

#ifndef __ASSEMBLER__
void aes_ob_getsp(uint8_t *image, uint32_t tree, int16_t object, uint32_t tedinfo);                      /* $fe9260 */
int16_t aes_scan_to_end(uint8_t *image, uint32_t template, int16_t index, int16_t character);           /* $fe9352 */
void aes_ins_char(uint8_t *image, uint32_t string, int16_t at, int16_t character, int16_t room);         /* $fe937e */
int16_t aes_find_pos(uint8_t *image, uint32_t template, int16_t index);                                  /* $fe93da */
void aes_pxl_rect(uint8_t *image, uint32_t tree, int16_t object, int16_t position, uint32_t rect);       /* $fe941c */
void aes_curfld(uint8_t *image, uint32_t tree, int16_t object, int16_t position, int16_t characters);    /* $fe948a */
int16_t aes_instr(uint8_t *image, int16_t character, uint32_t set);                                      /* $fe9516 */
int16_t aes_check(uint8_t *image, uint32_t character, int16_t valid);                                    /* $fe9556 */
void aes_ob_stfn(uint8_t *image, int16_t index, uint32_t start, uint32_t finish);                        /* $fe95f2 */
int16_t aes_ob_delit(uint8_t *image, int16_t index);                                                     /* $fe962a */
int16_t aes_ob_edit(uint8_t *image, uint32_t tree, int16_t object, int16_t key, uint32_t index, int16_t kind);
                                                                                                         /* $fe9678 */
#endif

#endif /* TOS102US_AES_OBEDIT_H */
