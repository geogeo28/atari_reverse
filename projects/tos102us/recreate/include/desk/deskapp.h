/* desk/deskapp.h — UNIT A, THE DESK'S APPLICATION LIST (`src/desk/deskapp.c`; band 6 wave 1b, group G2): the
 * DESKTOP.INF fields read and written, the list of ANODEs, the desktop's grid and the current path kept.
 *
 *   $fdb014 scan_str(cursor, &string)        blanks skipped, the text to its `@` copied into the desk's string
 *                                            buffer at g_pbuff (NUL-ended, g_pbuff moved past it); the cursor past `@`
 *   $fdb05a save_str(cursor, string)         the text, `@` and a blank written at the cursor; the cursor past them
 *   $fdb082 app_parse(cursor, anode)         an INF line: its type letter (a_type, a_flags), on the desktop its spot,
 *                                            its two icons, its letter and its two texts; the cursor
 *   $fdb186 app_tran(index)                  the desk resource's BITBLK `index` turned to the device's form in place
 *   $fdb220 app_rdicon()                     the ROM's ICONBLKs copied twice (g_iblist and the masks' list), their
 *                                            images laid in one block and their masks in another (Malloc), each
 *                                            turned to the device's form; BITBLK 0 turned too (app_tran); 1
 *   $fdb1c8 app_getfh(open, name, unused)    the name kept in g_tmppth, opened read-write or created; the handle (0
 *                                            where GEMDOS failed)
 *   $fdbeec app_blddesk()                    the desktop's tree emptied (obj_wfree), its pattern set by the
 *                                            resolution, an icon object made for each ANODE on the desktop (its
 *                                            ICONBLK copied from the mask list, its name and letter), and the disk
 *                                            drives' bit vector handed appl_bvset; its answer
 *   $fdb508 snap_disk(x, y, &x, &y)          a point of the desktop snapped to the icons' grid
 *   $fdbb0a app_revit()                      the list in use turned round
 *   $fdbe7e app_path_save()                  the current drive and its path kept, the boot drive's root made current
 *   $fdbeb6 app_path_restore()               ...and the kept ones made current again
 *
 * ALCYON C, each a `link` and a Line-F return. What each answers is the ROM's register where the C has it: a cursor
 * as the whole LONGWORD it walked (its top byte as it came in), the handle a WORD, app_tran gsx_trans's word, the
 * two path routines the glue's last answer. snap_disk and app_revit answer nothing in C: the word the ROM leaves in D0 there is a COUNTED
 * divergence (`test/test_desk_app.py`), read by no caller.
 *
 * NAMES: the published GEM desktop's DESKAPP where the body is its routine; the two path routines by what they do.
 */
#ifndef TOS102US_DESK_DESKAPP_H
#define TOS102US_DESK_DESKAPP_H

#include "desk/deskglobals.h"
#include "desk/deskleaf.h"

/* (The desk's global block, an ANODE's layout and its a_type values: `desk/deskglobals.h`.) */

/* app_parse's type letters (`$fdb0ec sub.w #'C',d0 / cmp.w #17,d0`: the table $fef364 over 'C'..'T') and what
 * each sets: a_type (AT_*), and a_flags where the arm stores them ('D' stores the type alone). */
#define INF_TYPE_CARTRIDGE    'C'
#define INF_TYPE_FOLDER       'D'
#define INF_TYPE_TOS_APP      'F'
#define INF_TYPE_GEM_APP      'G'
#define INF_TYPE_DISK         'M'
#define INF_TYPE_TTP_APP      'P'
#define INF_TYPE_TRASH        'T'
#define ANODE_ON_DESK_FLAGS   7          /* a disk's, the trash's, the cartridge's      ($fdb09e move.w #7,4(a4))   */
#define ANODE_GEM_APP_FLAGS   3          /*                                             ($fdb0c6 move.w #3,4(a4))   */
#define ANODE_TOS_APP_FLAGS   0          /*                                             ($fdb0d2 clr.w 4(a4))       */
#define ANODE_TTP_APP_FLAGS   8          /*                                             ($fdb0dc move.w #8,4(a4))   */
#define INF_TYPE_FIELD_BYTES  2          /* the letter and its blank                    ($fdb104 addq.l #2,a5)      */
#define INF_NO_LETTER         0          /* a letter field that is a blank              ($fdb154 clr.w d0)          */
#define INF_LETTER_FIELD_BYTES 2         /* the letter and its blank                    ($fdb160 addq.l #2,a5)      */

/* app_rdicon's ICONBLKs, as the ROM's resource has them: an image INDEX in each of ib_pmask and ib_pdata (made
 * addresses here), the list ended by an ib_pmask of -1; every icon the first one's size. */
#define ICONBLK_WIDTH         22         /* word: ib_wicon                              ($fdb2b2 move.w 13236(a5),d0) */
#define ICONBLK_HEIGHT        24         /* word: ib_hicon                              ($fdb2b6 muls.w 13238(a5),d0) */
#define ICONBLK_WTEXT         30         /* word: ib_wtext, the label's width   ($fdb92e add.w 13244(a3),d0)  */
#define ICONBLK_HTEXT         32         /* word: ib_htext, its height          ($fdb93a add.w 13246(a3),d0)  */
#define ICONBLK_LIST_END      0xffffffffu /* an ib_pmask that ends the list            ($fdb2a6 cmpi.l #-1,13214(a0)) */
#define APP_ICONBLKS_BYTES    204        /* the ROM's six ICONBLKs, and the images' part past them
                                                                                      ($fdb22e move.w #204,-16(a6)) */
#define ICON_PIXELS_A_WORD    16         /* an image's words: its width times its height over this ($fdb2bc divs.w #16) */
#define ICON_PIXELS_A_BYTE    8          /* ...and its bytes across                    ($fdb476 divs.w #8,d0)        */
#define IMAGE_IS_A_MASK       1          /*                                            ($fdb312 move.w #1,13622(a0)) */
#define IMAGE_IS_DATA         0          /*                                            ($fdb32c clr.w 13622(a0))     */
#define IMAGE_NOT_A_MASK      (-1)       /*                                            ($fdb368 move.w #-1,13622(a0)) */
#define APP_TRAN_FIRST_BITBLK 0          /* the one app_rdicon turns                   ($fdb500 clr.w (sp))          */
#define APP_RDICON_DONE       1          /*                                            ($fdb504 moveq #1,d0)         */

/* app_blddesk's desktop: its root, rebuilt over the screen; its pattern (the desktop object's ob_spec) by the
 * resolution — mono's for Getrez 2 and 4; the disks' bit vector (drive A: its top bit). */
#define REZ_MONO              2          /*                                              ($fdbf1a cmpi.w #2,-8(a6))   */
#define REZ_TT_MONO           4          /*                                              ($fdbf22 cmpi.w #4,-8(a6))   */
#define DESKTOP_PATTERN_MONO  0x00001143 /*                                              ($fdbf2a move.l #4419)       */
#define DESKTOP_PATTERN_COLOUR 0x00001173 /*                                             ($fdbf34 move.l #4467)       */
#define DRIVE_A_BIT           0x8000     /* appl_bvset's vector: A: its top bit           ($fdbf78 move.w #$8000,d0)   */
#define ICON_LETTER_BYTE      0x00ff     /* the letter ORed into ib_char's low byte       ($fdc058 and.w #255,d0)      */
#define AES_APP_BLDDESK_GETREZ_RETURN 0xfdbf16 /* trp14's parked return: the word after its Line-F call            */

/* scan_str's and save_str's text end: the INF's `@` (the blank between fields is `aes/infscan.h`'s separator). */
#define INF_TEXT_END          '@'

/* app_getfh's two GEMDOS opens of DESKTOP.INF: read-write, and a plain file. */
#define APP_OPEN_READ_WRITE   2          /*                                             ($fdb1fa move.w #2,(sp))    */
#define APP_CREATE_PLAIN      0          /* its third argument is read and never used   ($fdb208 clr.w (sp))        */

/* The drive and path app_path_save keeps, and the root it goes to (on drive C: where set_defdrv found it, else A:
 * `aes/deskleaf.h`'s DRIVE_C / DRIVE_A, $fdbea2 / $fdbea8). */
#define AES_DESK_KEPT_DRIVE   0x9b38     /* word                                        ($fdbe84 move.w d0,$9b38)   */
#define AES_DESK_KEPT_PATH    0x980e     /* bytes: Dgetpath's answer                    ($fdbe8a move.l #$980e,(sp)) */
#define AES_DESK_ROOT_PATH    0xfef42c   /* the ROM's "\"                               ($fdbeac move.l #$fef42c)   */
#define DGETPATH_DRIVE_BASE   1          /* Dgetpath's drive: 1 is A:, where Dgetdrv's 0 is ($fdbe96 addq.w #1,(sp)) */
/* THE RETURN SITES THE GLUE PARKS: each the word after its Line-F call (`aes/gemdosif.h`'s `return_site`). */
#define AES_APP_GETFH_CREATE_RETURN   0xfdb20e
#define AES_APP_PATH_SAVE_GDRV_RETURN 0xfdbe84
#define AES_APP_PATH_SAVE_SDRV_RETURN 0xfdbeac
#define AES_APP_PATH_SAVE_CHDIR_RETURN 0xfdbeb4
#define AES_APP_PATH_RESTORE_SDRV_RETURN 0xfdbec2
#define AES_APP_PATH_RESTORE_CHDIR_RETURN 0xfdbeca

/* app_tran's answer word: rs_gaddr's BITBLK address, handed on BY ADDRESS ($fdb18a move.l a6,(sp) / subq.l #4,(sp)). */
#define APP_TRAN_BITBLK_BYTES 4

/* ---- band 6 wave 2 (group G4): DESKTOP.INF read whole and parsed, and written ---------------------------------------
 * (Its buffer, length, text buffer and ANODE pool: `desk/deskglobals.h` DESK_G_AFILE .. DESK_ANODES; a window's
 * g_cnxsave entry: `desk/desktop.h` SAVE_*, `desk/deskview.h` WINDOW_SAVE_BYTES.) */
/* the buffer (shel_get's, dos_read's: $fdb64c move.w #2048,(sp)) is aes/geminit.h's INF_BUFFER_BYTES */
#define INF_LINE_START        '#'        /* a line's first byte                   ($fdb65c cmpib #35)            */
#define INF_TYPE_ENVIRONMENT  'E'        /* the INF's #E line: the view, sort, preferences, resolution          */
#define INF_TYPE_WINDOW       'W'        /* a window's #W line                                                  */
#define INF_DRIVE_LETTER_AT   14         /* a drive's letter in its #M / #T line  ($fdb712 cmpib #67,14(a4))    */
#define INF_DRIVE_C           'C'
#define AES_INF_NAME_READ     0xfef414   /* the ROM's "DESKTOP.INF", app_start's  ($fdb66e move.l #$fef414)    */
#define AES_INF_NAME_WRITE    0xfef420   /* ...and app_save's copy                ($fdbe34 move.l #$fef420)    */
#define AES_APP_START_CLOSE_RETURN 0xfdb6bc /* dos_close's parked return: the word after its Line-F call         */
#define AES_APP_SAVE_CLOSE_RETURN  0xfdbe68
/* The #E line's two fields: the first's bits the view, the sort and two preferences, the second's the third
 * preference over the resolution (from 0). */
#define INF_E_VIEW_BIT        0x80       /* ($fdb87e btst #7,-13(a6); $fdbb68 move.w #128,d0)                  */
#define INF_E_SORT_MASK       0x60       /* ($fdb894 and.w #96,d0)                                              */
#define INF_E_SORT_SHIFT      5          /* ($fdb898 asr.w #5,d0)                                               */
#define INF_E_PREFERENCE_1_BIT 0x10      /* DESK_CNX_PREFERENCES[1]               ($fdb89e btst #4,-13(a6))     */
#define INF_E_PREFERENCE_0_BIT 0x08      /* DESK_CNX_PREFERENCES[0]               ($fdb8b0 btst #3,-13(a6))     */
#define INF_E_PREFERENCE_2_MASK 0xf0     /* DESK_CNX_PREFERENCES[2], the second field's ($fdb8d6 and.w #240)     */
#define INF_E_PREFERENCE_2_SHIFT 4
#define APP_START_ENVIRONMENT_BYTES 2    /* scan_2's word, handed BY ADDRESS      ($fdb86e -14(a6))              */
/* A #W line's rectangle is in character cells: a column or a width past the screen's columns HALVED (a column at the
 * columns, a width only past them), the size at least seven boxes. */
#define WINDOW_LEAST_BOXES    7          /* ($fdb7e8 muls.w #7,d0)                                              */
/* The icons' grid (g_icw, g_ich: `desk/deskglobals.h` DESK_GRID_W / _H): an icon object and a space beside it of
 * 8 pixels where the screen is over 300 lines tall (`desk/deskview.h` TALL_SCREEN_LINES, ICON_SPACE_TALL), and two
 * under it; the screen's leftover shared out. */
#define ICON_SPACE_UNDER      2          /* ($fdb98a addq.w #2,d0)                                              */
/* The two drag outlines (DESK_G_XYICON, DESK_G_XYTEXT): point pairs, each cleared by a bfill of HALF ITS BYTES (the
 * ROM's count is bytes, its outline's words: the last two words of each are left as they were). */
#define ICON_OUTLINE_POINTS   9          /* ($fdba14 move.w #9,8128(a3))                                        */
#define TEXT_OUTLINE_POINTS   5          /* ($fdba1a move.w #5,8130(a3))                                        */
#define ICON_OUTLINE_CLEARED  18         /* ($fdba2a move.w #18,-(sp))                                          */
#define TEXT_OUTLINE_CLEARED  10         /* ($fdbab0 move.w #10,-(sp))                                          */
#define ICON_OUTLINE_LABEL_GAP 2         /* the image's frame ends this far above the label, less a small cell
                                          *                                     ($fdba4e subq.w #2,d0)         */
#define TEXT_OUTLINE_CELLS    12         /* a text line's outline, in cells across ($fdbabe muls.w #12,d0)      */
#define APP_START_DONE        1          /* ($fdbadc moveq #1,d0)                                               */
/* app_save's INF: written into g_afile past its first INF_KEPT_BYTES — those are shel_get's, put back from the shell's
 * buffer after (the AES's own #a..#d lines) — over INF_WRITTEN_BYTES cleared; an icon's line written only while
 * less than INF_ICON_LINES_END is; each line ended CR LF, the whole by the end mark and a NUL. */
#define INF_KEPT_BYTES        128        /* ($fdbb42 lea 8336(a3),a5; $fdbe06 move.w #128,(sp))                 */
#define INF_WRITTEN_BYTES     1920       /* ($fdbb4a move.w #1920,-(sp))                                        */
#define INF_ICON_LINES_END    2013       /* ($fdbcbe cmpi.l #2013,d0)                                           */
#define INF_CR                '\r'       /* ($fdbbd0 move.b #13,(a5)+)                                          */
#define INF_LF                '\n'
#define INF_FILE_END          0x1a       /* ($fdbdee move.b #26,(a5)+)                                          */
#define APP_START_NO_ICONS    0          /* app_rdicon's 0                        ($fdb922 clr.w d0)            */

#ifndef __ASSEMBLER__
#include <stdint.h>

uint32_t aes_scan_str(uint8_t *image, uint32_t cursor, uint32_t string_out);                     /* $fdb014 */
uint32_t aes_save_str(uint8_t *image, uint32_t cursor, uint32_t string);                         /* $fdb05a */
uint32_t aes_app_parse(uint8_t *image, uint32_t cursor, uint32_t anode);                         /* $fdb082 */
uint16_t aes_app_tran(uint8_t *image, int16_t index);                                            /* $fdb186 */
int16_t aes_app_rdicon(uint8_t *image);                                                          /* $fdb220 */
int16_t aes_app_getfh(uint8_t *image, int16_t open, uint32_t name, int16_t unused);              /* $fdb1c8 */
void aes_snap_disk(uint8_t *image, int16_t x, int16_t y, uint32_t x_out, uint32_t y_out);        /* $fdb508 */
void aes_app_revit(uint8_t *image);                                                              /* $fdbb0a */
uint32_t aes_app_path_save(uint8_t *image);                                                      /* $fdbe7e */
uint32_t aes_app_path_restore(uint8_t *image);                                                   /* $fdbeb6 */
int16_t aes_app_blddesk(uint8_t *image);                                                         /* $fdbeec */
int16_t aes_app_start(uint8_t *image);                                                           /* $fdb5fc */
void aes_app_save(uint8_t *image, int16_t to_disk);                                              /* $fdbb34 */
#endif

#endif /* TOS102US_DESK_DESKAPP_H */
