/* desk/deskutil.h — THE DESK'S UTILITIES, unit M (`src/desk/deskutil.c`): the range `$fed478..$fed887` — the cartridge
 * pair, the show / print engine. Band 5 owns the range's first two routines (cart_init `$fed478`, cart_find `$fed4be`:
 * `aes/cart.h`); band 6 wave 2 (group G2, ruling R-W2-1) takes the CARTRIDGE'S DIRECTORY SEARCH the directory read
 * pn_active `$fdfc3c` calls on drive 'c' — cart_sfirst `$fed522` and cart_snext `$fed534`, `aes/cart.h`'s own words
 * for them, each now read from its body. The rest of the unit is wave 4's.
 *
 * A SEARCH AS GEMDOS'S: the pair answers as dos_sfirst / dos_snext do — 1 an entry found (cart_find(1) has laid it into
 * the DTA cart_sfirst kept at AES_CART_DTA), 0 none, AES_DOS_AX then DOS_AX_NO_MORE_FILES. On the oracle's bus the
 * cartridge port reads 0 (`test/test_aes_cart.py`): cart_init always finds none there, so cart_sfirst's found arm
 * runs on no machine of ours.
 */
#ifndef TOS102US_DESK_DESKUTIL_H
#define TOS102US_DESK_DESKUTIL_H

/* ---- band 6 wave 2, group G2 (unit M) ---- */
#define CART_SNEXT_FILL       1          /* cart_find's `fill`: the entry laid into the DTA ($fed538 move.w #1,(sp)) */
#define CART_SNEXT_FOUND      1          /* ($fed542 moveq #1,d0)                                              */
#define CART_SNEXT_NONE       0          /* ($fed550 clr.w d0), AES_DOS_AX := DOS_AX_NO_MORE_FILES ($fed548)   */

#ifndef __ASSEMBLER__
#include <stdint.h>

int16_t aes_cart_sfirst(uint8_t *image, uint32_t dta, int16_t unread);                                /* $fed522 */
int16_t aes_cart_snext(uint8_t *image);                                                               /* $fed534 */
#endif
/* ---- end of group G2's wave-2 ---- */
/* ---- band 6 wave 4, group G1 (unit M) ---- */
/* THE SHOW / PRINT ENGINE (`$fed61e..$fed887`): desk_show_file and desk_print_file, the two built-ins sh_cmd runs, each
 * the engine `$fed632` over (name, show) — and its eight `bsr`-only parts, static C in `deskutil.c` (R-W4-5). The
 * engine's three words are `desk/deskglobals.h`'s AES_SHOW_INDEX / _AT_EOF / _COUNT. */
#define SHOW_BUFFER_BYTES     4096       /* the buffer, kept in A6 AS DATA      ($fed636 movea.l #4096,a6)      */
#define SHOW_INDEX_AT_THE_END (-1)       /* AES_SHOW_INDEX once the viewer showed the end ($fed80e)            */
#define SHOW_AT_EOF_SET       1          /* AES_SHOW_AT_EOF once an Fread came short ($fed714)                 */
#define ENGINE_SHOWS          1          /* the engine's word: shown ($fed61e) ...  ($fed66e tst.w 44(sp))      */
#define ENGINE_PRINTS         0          /* ...or printed ($fed624)                                            */
#define ENGINE_DONE           1          /* ($fed6ce moveq #1,d0)                                              */
#define ENGINE_FAILED         0          /* not opened, or no buffer: D0's word cleared ($fed656 clr.w d0)      */
#define CRAWIO_ASK            0xff       /* Crawio's "a key, if one is there" ($fed692 move.w #255,-(sp))       */
#define SETPRT_ASK            (-1)       /* Setprt(-1): the configuration answered, unchanged ($fed67a $0021ffff) */
#define SETPRT_RS232          0x10       /* the configuration's bit 4: the printer is on the RS232 port ($fed684) */
#define BCONOUT_CONSOLE       2          /* Bconout's device: the console       ($fed7d4 move.w #2,-(sp))       */
#define VIEWER_PAGE_LINES     22         /* a page: dbf from 21                 ($fed7c0 moveq #21,d6)          */
#define VIEWER_QUIT           0x51       /* 'Q' at "-MORE-" (a BYTE compare)    ($fed768 cmp.b #81,d0)          */
#define VIEWER_NEXT_PAGE      0x20       /* ' ': the next page                  ($fed778 cmpi.w #32,d0)         */
/* The ROM's strings the viewer writes. */
#define VIEWER_WRAP_ON        0xfefd93   /* "ESC v", by Cconws                  ($fed738 pea $fefd93)           */
#define VIEWER_ERASE_LINE     0xfefd90   /* "ESC l", by Cconws                  ($fed7ae pea $fefd90)           */
#define VIEWER_MORE           0xfef468   /* "-MORE-", by Crawio                 ($fed790 pea $fef468)           */
#define VIEWER_END            0xfef470   /* "-END OF FILE-", by Crawio          ($fed804 pea $fef470)           */
/* THE PRINTER'S "NOT READY" ALERT, as the engine calls fm_show: it pushes THREE WORDS (17, 0, 1) and fm_show reads a
 * word, a LONGWORD and a word — so its values pointer is $00000001 (the 0 and the 1) and its default button the word
 * above them on the stack, the high word of the engine's own `bsr` return address ($00fed6xx). Reproduced. */
#define PRINTER_ALERT_STRING  17         /*                                     ($fed84e move.w #17,-(sp))      */
#define PRINTER_ALERT_VALUES  1          /* the words 0 and 1, read as one longword ($fed84c clr.w, $fed848)    */
#define PRINTER_ALERT_DEFAULT 0x00fe     /* the high word of `bsr`'s return into $fed6xx, read as the default  */
#define PRINTER_ALERT_CANCEL  1          /* fm_show's answer that abandons      ($fed85e cmp.w #1,d6)           */
#define PRINT_ABANDONED       99         /* ($fed864 move.w #99,d6)                                            */
#define PRINT_CHAR_DONE       1          /* the RS232 port's answer             ($fed884 moveq #1,d0)           */
/* The sites each Line-F call to the glue's $fe3c28 family, gem_gemdos_call, trp13 and trp14 returns to — parked */
#define AES_SHOW_CLOSE_RETURN       0xfed6c8
#define AES_SHOW_FREE_RETURN        0xfed6cc
#define AES_SHOW_SETPRT_RETURN      0xfed682   /* trp14's park, AES_XBIOS_RETURN */
#define AES_SHOW_KEY_CHECK_RETURN   0xfed698   /* printing: a key looked for between two bytes */
#define AES_SHOW_WRAP_RETURN        0xfed744
#define AES_SHOW_END_KEY_RETURN     0xfed75a   /* the viewer's wait at the file's end */
#define AES_SHOW_MORE_KEY_RETURN    0xfed7a2   /* ...and at "-MORE-" */
#define AES_SHOW_ERASE_RETURN       0xfed7ba
#define AES_SHOW_BCONOUT_RETURN     0xfed7de   /* trp13's park, AES_BIOS_RETURN */
#define AES_SHOW_END_CR_RETURN      0xfed7fe
#define AES_SHOW_END_LF_RETURN      0xfed804
#define AES_SHOW_STRING_RETURN      0xfed828
#define AES_SHOW_CPRNOUT_RETURN     0xfed842
#define AES_SHOW_CAUXOUT_RETURN     0xfed882

#ifndef __ASSEMBLER__
#include <stdint.h>

int16_t aes_desk_show_file(uint8_t *image, uint32_t name);                                            /* $fed61e */
int16_t aes_desk_print_file(uint8_t *image, uint32_t name);                                           /* $fed624 */
#endif
/* ---- end of group G1's wave-4 ---- */

#endif /* TOS102US_DESK_DESKUTIL_H */
