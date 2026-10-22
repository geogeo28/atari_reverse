/* desk/deskusr.h — THE TEXT VIEW'S LINE AND ITS FORMATTERS, unit E (`src/desk/deskusr.c`): my_itoa `$fde500`, fmt_time
 * `$fde546`, fmt_date `$fde5ba` and ob_sfcb `$fde610`, the line a file is shown by in a window's text view — band 6
 * wave 1b, group G4.
 *
 * NAMES: the published GEM desktop's (DESKINF's my_itoa, fmt_time, fmt_date and ob_sfcb), each read from its body.
 *
 * NONE YIELDS. WHAT A ROM CALLER READS IN D0 WHERE THE C ANSWERS NOTHING: my_itoa and fmt_date leave merge_str's (and
 * so my_itoa's) leftover — counted, and read by no caller (`test/test_desk_usr.py`).
 */
#ifndef TOS102US_DESK_DESKUSR_H
#define TOS102US_DESK_DESKUSR_H

#include "aes/gemgraf.h"

/* ---- my_itoa: a number as two digits ------------------------------------------------------------------------------ */
#define MY_ITOA_DIGITS        2          /* ($fde51c cmp.w #2,d7)                                               */
#define MY_ITOA_ONE_DIGIT_MOST 9         /* at most this, the merge starts past the first '0' ($fde530 cmpi.w #9: bls) */
#define AES_DESK_MY_ITOA_TEMPLATE 0xfef5ba /* "%W"                              ($fde52a move.l #$fef5ba,-(sp)) */

/* ---- a DOS time and a DOS date, as GEMDOS packs them (`hhhhhmmmmmmsssss`, `yyyyyyymmmmddddd`) ---------------------- */
#define DOS_TIME_HOURS_MASK   0xf800     /* ($fde558 andw #-2048,d5)                                            */
#define DOS_TIME_HOURS_SHIFT  11         /* ($fde55c moveq #11,d0: asr)                                         */
#define DOS_TIME_HOURS_FIELD  0x1f       /* ($fde560 andw #31,d5)                                               */
#define DOS_TIME_MINUTES_MASK 0x07e0     /* ($fde58e andw #2016,d0)                                             */
#define DOS_TIME_MINUTES_SHIFT 5
#define DOS_TIME_MINUTES_FIELD 0x3f      /* ($fde596 andiw #63,(sp))                                            */
#define DOS_DATE_MONTH_MASK   0x01e0     /* ($fde5cc andw #480,d0)                                              */
#define DOS_DATE_MONTH_SHIFT  5
#define DOS_DATE_DAY_FIELD    0x1f       /* ($fde5e0 andiw #31,(sp))                                            */
#define DOS_DATE_YEAR_SHIFT   9          /* ($fde5f0 moveq #9,d1: lsr)                                          */
#define DOS_DATE_YEAR_FIELD   0x7f       /* ($fde5f4 andw #127,d0)                                              */
#define DOS_DATE_YEAR_BASE    80         /* 1980, the year GEMDOS counts from   ($fde5f8 addw #80,d0)           */
#define CENTURY_YEARS         100        /* the year's last two digits          ($fde602 divuw #100,d0)         */
/* fmt_time's twelve-hour clock: noon and after is the afternoon, an hour 0 is 12 */
#define CLOCK_HALF_DAY_HOURS  12         /* ($fde564 cmpw #12,d5)                                               */
#define AES_DESK_PM           0xfef5bd   /* "pm"                                ($fde5a6 move.l #$fef5bd,-(sp)) */
#define AES_DESK_AM           0xfef5c0   /* "am"                                ($fde5ae move.l #$fef5c0,-(sp)) */
/* What the two text fields hold: "hhmm" then the two letters; "mmddyy" — each a pair of digits a call of my_itoa */
#define FMT_PAIR_BYTES        2
#define FMT_TIME_SUFFIX       4          /* "am" / "pm" after the four digits   ($fde5a0 addql #4,(sp))         */

/* ---- ob_sfcb: the SFCB it copies — a file as a directory search answers it, from its attributes on (an FNODE's tail,
 * `desk/deskfpd.h`'s FNODE_ATTR on): the attributes, time, date, size, name — and the line it makes: a folder's glyph,
 * the name, the extension, the size, the date, the time ---------------------------------------------------------------- */
#define SFCB_BYTES            23         /* ($fde620 move.w #23,(sp))                                           */
#define SFCB_ATTR             0          /* byte: bit 4 a folder                ($fde646 btst #4,-23(a6))       */
#define SFCB_ATTR_SUBDIR_BIT  4
#define SFCB_TIME             1          /* word                                ($fde76c -22(a6))               */
#define SFCB_DATE             3          /* word                                ($fde72e -20(a6))               */
#define SFCB_SIZE             5          /* long                                ($fde6de -18(a6))               */
#define SFCB_NAME             9          /* bytes: "NAME.EXT"                   ($fde634 lea -14(a6),a3)        */
/* ob_sfcb's own frame, from -50(a6) (a slot off target, `host_slot.h`): what it hands merge_str, fmt_date, fmt_time
 * and strcpy by address, and the SFCB copied in, laid as the ROM lays them */
#define OB_SFCB_SIZE_TEXT     0          /* bytes: merge_str's "%L" of the size ($fde6ec -50(a6))               */
#define OB_SFCB_TIME_TEXT     10         /* bytes: fmt_time's                   ($fde766 -40(a6))               */
#define OB_SFCB_DATE_TEXT     18         /* bytes: fmt_date's                   ($fde728 -32(a6))               */
#define OB_SFCB_COPY          27         /* bytes[SFCB_BYTES]: the SFCB         ($fde628 -23(a6))               */
#define OB_SFCB_FRAME_BYTES   50
#define AES_DESK_SIZE_TEMPLATE 0xfef5c3  /* "%L"                                ($fde6e4 move.l #$fef5c3,-(sp)) */
/* The line, column by column: on a screen 320 pixels across (low resolution) the blanks between the fields are left
 * out — the name's column and the extension's end two and three characters sooner */
#define LOW_RESOLUTION_WIDTH  320        /* ($fde638 cmpiw #320,$980a)                                          */
#define FOLDER_GLYPH          7          /* the character a folder's line begins with ($fde64e moveq #7,d0)     */
#define OB_SFCB_EXTENSION_AT  12         /* where the extension starts           ($fde680 moveq #12,d0)         */
#define OB_SFCB_EXTENSION_AT_LOW 10      /* ...on the low resolution's screen    ($fde67c moveq #10,d0)         */
#define OB_SFCB_SIZE_AT       16         /* where the size's field starts        ($fde6b4 moveq #16,d0)         */
#define OB_SFCB_SIZE_AT_LOW   13         /*                                      ($fde6b0 moveq #13,d0)         */
#define OB_SFCB_SIZE_DIGITS   8          /* the size right-aligned in eight     ($fde6f6 moveq #8,d6)           */
#define OB_SFCB_DATE_PAIRS    3          /* "mm-dd-yy"                          ($fde73a moveq #3,d6)           */
#define OB_SFCB_DATE_SEPARATOR '-'
#define OB_SFCB_TIME_PAIRS    2          /* "hh:mm"                             ($fde778 moveq #2,d6)           */
#define OB_SFCB_TIME_SEPARATOR ':'
#define OB_SFCB_SUFFIX_STEP   3          /* past "am"'s two letters and its NUL ($fde7ac addql #3,a4)           */

/* ==== BAND 6 WAVE 2, group G1: the text view's G_USERDEF draw — dr_code `$fde7b4` (GEM's DESKUSR name, read from its
 * body) and its one caller `$fde844` (AES_ROM_DESK_USERDEF), which ub_trampoline calls by VALUE on the desk's userdef
 * stack (no Line-F word: its binding is that `jsr`'s operand, `trapdoor.S`'s thunk since band 6 slice F3, N18) ==== */
/* dr_code: a line whose SELECTED bit changed is inverted (bb_fill in XOR, solid); any other drawn — ob_sfcb into
 * g_1text, the text's colour set, its characters into intin, v_gtext in the large font at the object's corner, and the
 * LINE colour left in XOR mode ($fde830..$fde83a: gsx_attr(0, 3, 1)). Its answer: the current state, as handed. */
#define DR_CODE_INVERT_MODE   GSX_MODE_XOR  /* bb_fill's mode                ($fde7d6 move.w #3,-(sp))               */
#define DR_CODE_INVERT_FILL   GSX_FIS_SOLID /* ...interior and style ($fde7d0 move.l #$00010007): solid             */
#define DR_CODE_INVERT_STYLE  GSX_PATTERN_SOLID
#define DR_CODE_TEXT_MODE     GSX_MODE_REPLACE  /* gsx_attr(1, 1, 1): the text's ($fde7fc move.l #$00010001)        */
#define DR_CODE_COLOUR        1          /* black                                 ($fde7f8 move.w #1,(sp))      */
#define DR_CODE_LINE_MODE_AFTER GSX_MODE_XOR  /* gsx_attr(0, 3, 1) after the text ($fde834 move.w #3,-(sp))        */
/* $fde844's frame (`link #-38`, a slot off target, `host_slot.h`): the clip it keeps, then the PARMBLK copied whole
 * (lbcopy) — the clip it sets is the copy's own, and dr_code is handed the copy's fields */
#define USERDEF_CLIP_KEPT     0          /* bytes[GRECT_BYTES]: gsx_gclip's         ($fde862 addi.l #-38,(sp))  */
#define USERDEF_PARMBLK       8          /* bytes[PARM_BYTES]                       ($fde856 addi.l #-30,(sp))  */
#define USERDEF_FRAME_BYTES   38

#ifndef __ASSEMBLER__
#include <stdint.h>

void aes_desk_my_itoa(uint8_t *image, int16_t number, uint32_t text);                                           /* $fde500 */
uint32_t aes_desk_fmt_time(uint8_t *image, int16_t time, uint32_t text);                                        /* $fde546 */
void aes_desk_fmt_date(uint8_t *image, int16_t date, uint32_t text);                                            /* $fde5ba */
uint32_t aes_desk_ob_sfcb(uint8_t *image, uint32_t sfcb, uint32_t text);                                        /* $fde610 */
int16_t aes_desk_dr_code(uint8_t *image, uint32_t tree, int16_t object, int16_t previous_state, int16_t current_state,
                         int16_t x, int16_t y, int16_t width, int16_t height, uint32_t sfcb);                    /* $fde7b4 */
int16_t aes_desk_userdef(uint8_t *image, uint32_t parmblk);                                                     /* $fde844 */
#endif

#endif /* TOS102US_DESK_DESKUSR_H */
