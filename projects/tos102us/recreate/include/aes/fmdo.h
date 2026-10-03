/* aes/fmdo.h — the FORM LIBRARY's half that waits on the user (`src/aes/fmdo.c`): a dialog run until an exit
 * (fm_do), a click on one of its objects (fm_button), the screen given back round it (fm_dial), and the alerts —
 * one laid out from a string and run (fm_alert), one of the AES's own strings merged and shown (fm_show), the
 * critical error handler's (eralert) and a GEMDOS error's (fm_error) — and the bell fm_do rings for a click outside
 * its dialog.
 *
 * ALCYON C, every routine entered by a Line-F call over its caller's frame (a tree, a string or a pointer a LONGWORD,
 * an object, a count or a code a WORD), each answering a WORD its callers read; the bell is hand 68000 (a `trap #13`
 * and `rts`), answering nothing a caller reads. The event layer they wait in — ev_multi, ev_button — is the event
 * door's (`aes/evdoor.h`).
 *
 * WHAT fm_dial's CALLERS READ IN D0 (the desk's form_dial binding stores it): its type for FMD_START and any type it
 * does not know; for the other three the D0 its last callee leaves — gsx_mon's, the cursor shown again at the end of
 * gr_growbox, gr_shrinkbox and w_update: 1 while the hide nest is still open, else the VDI's answer to v_show_c (0,
 * the word at VDI_RESULT) — or, for FMD_FINISH while window drawing is HELD (wind_set's hold, AES_GL_WFROZEN), the 1
 * w_clipdraw answers under w_drawdesk, which w_update leaves as it found it.
 */
#ifndef TOS102US_AES_FMDO_H
#define TOS102US_AES_FMDO_H

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

#include "aes/fmlib.h"

/* ---- fm_do -------------------------------------------------------------------------------------------------------- */
/* Its ev_multi: a key, or a button press — up to two clicks of any button down ($fe750e move.l #$2ff01). */
#define FM_DO_CLICKS          2
#define FM_DO_BUTTONS         0xff
#define FM_DO_BUTTON_DOWN     1
/* Its frame (`link a6,#-20`), the words whose ADDRESSES it hands on, laid out from -20(a6) as the ROM's `link` lays
 * them: ev_multi's answers (the key's word handed fm_keybd), ob_edit's index, and the next object (fm_keybd's and
 * fm_button's answer). -6(a6) the go-on flag and -4(a6) the events are kept by value. */
#define FM_DO_ANSWERS         0          /* words[EV_MULTI_ANSWER_WORDS] ($fe7504 -20(a6))                     */
#define FM_DO_MOUSE_X         0          /* word: ev_multi's answers, the mouse  ($fe7574 move.l -20(a6))      */
#define FM_DO_MOUSE_Y         2          /* word                                                               */
#define FM_DO_KEY             8          /* word: the key                        ($fe7536 -12(a6))             */
#define FM_DO_CLICK_COUNT     10         /* word: the clicks                     ($fe75a0 move.w -10(a6))      */
#define FM_DO_INDEX           12         /* word: ob_edit's index                ($fe74f2 -8(a6))              */
#define FM_DO_NEXT            18         /* word: the next object                ($fe74ca move.w d0,-2(a6))    */
#define FM_DO_FRAME_BYTES     20
#define FM_DO_NONE_FOUND      (-1)       /* ob_find's answer off the tree: the bell ($fe758c cmpi.w #-1)       */
#define FM_DO_FIND_DEPTH      8          /* ob_find's depth: the whole tree     ($fe7578 move.w #8)            */

/* ---- fm_button ------------------------------------------------------------------------------------------------------ */
/* Its frame (`link a6,#-26`) from -26(a6): ev_button's answers, the sibling's flags and the object's — the three
 * words ob_fs and ev_button are handed by address. */
#define FM_BUTTON_ANSWERS     0          /* words[EV_BUTTON_ANSWER_WORDS]        ($fe745a -26(a6))             */
#define FM_BUTTON_SIBLING_FLAGS 12       /* word: a radio sibling's flags        ($fe73c6 -14(a6))             */
#define FM_BUTTON_FLAGS       18         /* word: the object's flags             ($fe7360 -8(a6))              */
#define FM_BUTTON_FRAME_BYTES 26
/* A double click on a TOUCHEXIT object: the object answered with its top bit set ($fe7380 move.w #$8000). */
#define FM_DOUBLE_CLICKS      2          /* ($fe7378 cmpi.w #2,14(a6))                                         */
#define FM_DOUBLE_CLICKED     0x8000
/* The wait for the button to rise after a SELECTABLE object is taken: one click, the left button, up
 * ($fe7462 clr.w; move.l #$10001). */
#define FM_RISE_CLICKS        1
#define FM_RISE_BUTTON        1
#define FM_RISE_UP            0

/* ---- fm_dial ------------------------------------------------------------------------------------------------------- */
#define FMD_START             0          /* ($fe7634 tst.w d0)                                                 */
#define FMD_GROW              1          /* gr_growbox                          ($fe7638 cmp.w #1)             */
#define FMD_SHRINK            2          /* gr_shrinkbox                        ($fe763e cmp.w #2)             */
#define FMD_FINISH            3          /* the desktop and the windows redrawn ($fe7644 cmp.w #3)             */
#define FM_DIAL_HELD_ANSWER   1          /* w_clipdraw's answer while drawing is held ($feb664 moveq #1,d0)    */
#define FM_DIAL_NEST_OPEN_ANSWER 1       /* gsx_mon's while the nest stays open ($fe8a8e moveq #1,d0)          */
/* ...and once it shows the cursor: v_show_c's answer, the word at VDI_RESULT, which the VDI's dispatcher clears
 * ($fcaa12) and v_show_c never sets. */
#define FM_DIAL_SHOWN_ANSWER  0

/* ---- fm_alert ------------------------------------------------------------------------------------------------------ */
/* Its frame (`link a6,#-36`) from -34(a6), every word and long it hands on by address: the clip saved, the box
 * centred, the icon's BITBLK and the tree rs_gaddr answers, and fm_parse's five answers. -36(a6) is never used. */
#define FM_ALERT_CLIP         0          /* bytes[GRECT_BYTES]: gsx_gclip's     ($fe712e -34(a6))              */
#define FM_ALERT_BOX          8          /* bytes[GRECT_BYTES]: ob_center's     ($fe710e -26(a6))              */
#define FM_ALERT_BITBLK       16         /* long: rs_gaddr(R_BITBLK)'s answer   ($fe70b2 -18(a6))              */
#define FM_ALERT_TREE         20         /* long: rs_gaddr(R_TREE)'s answer     ($fe700a -14(a6))              */
#define FM_ALERT_BUTTON_LENGTH 24        /* word: fm_parse's answers            ($fe7030 -10(a6))              */
#define FM_ALERT_BUTTONS      26         /* word                                ($fe7038 -8(a6))               */
#define FM_ALERT_LINE_LENGTH  28         /* word                                ($fe703c -6(a6))               */
#define FM_ALERT_LINES        30         /* word                                ($fe7040 -4(a6))               */
#define FM_ALERT_ICON         32         /* word                                ($fe7044 -2(a6))               */
#define FM_ALERT_FRAME_BYTES  34
#define ALERT_TREE_INDEX      1          /* the AES resource's tree 1           ($fe7012 move.w #1)            */
#define ALERT_ROOT_STATE      OB_STATE_OUTLINED   /* the root OUTLINED, whatever it was ($fe702c move.w #16)   */
#define ALERT_ICON_PIXELS     32         /* the icon's width and height, set after rs_obfix ($fe70fc #32)      */
#define ALERT_DRAW_DEPTH      8          /* ob_draw's depth: the whole tree     ($fe7142 move.w #8)            */
/* fm_do's answer is the exit button's object; the alert's answer its number, 1 for the first ($fe718a subq.w #6). */
#define ALERT_BUTTON_NUMBERED (ALERT_FIRST_BUTTON - 1)

/* ---- fm_show, eralert, fm_error ------------------------------------------------------------------------------------- */
#define AES_FM_SHOW_ALERT     0xb99a     /* bytes[AES_FM_SHOW_ALERT_BYTES]: the string merged ($fe766c move.l #$b99a) */
#define AES_FM_SHOW_ALERT_BYTES 256      /* up to the next global, $ba9a                                       */
/* eralert's two tables, a word per error (the handler's code: 0 write-protected .. 6 insert a disk): the AES string
 * shown, and its default button in the low byte with a nonzero high byte when the string names the drive (%S). */
#define AES_ERALERT_STRINGS   0xfefa14   /* words[ERALERT_ERRORS]               ($fe76f0 movea.l #$fefa14,a1)  */
#define AES_ERALERT_LEVELS    0xfefa22   /* words[ERALERT_ERRORS]               ($fe76ae movea.l #$fefa22,a1)  */
#define ERALERT_ERRORS        7
#define ERALERT_LEVEL_MASK    0x00ff     /* ($fe76b8 andi.w #255)                                              */
#define ERALERT_NAMES_DRIVE   0xff00     /* ($fe76d0 andi.w #-256)                                             */
#define ERALERT_DRIVE_LETTER  0x41       /* 'A': the drive's letter is 'A' + its number ($fe7694 addi.w #65)  */
/* Its frame (`link a6,#-18`) from -14(a6): the drive's name, a letter and its NUL, and the pointer to it fm_show is
 * handed by address (merge_str's %S argument); -12(a6) and -4(a6) between and above are kept by value. */
#define ERALERT_DRIVE_NAME    0          /* bytes[2]                            ($fe7698 -14(a6), $fe769c -13) */
#define ERALERT_DRIVE_POINTER 6          /* long                                ($fe76a4 move.l a0,-8(a6))     */
#define ERALERT_FRAME_BYTES   10
#define ALERT_FIRST_ANSWERED  1          /* the first button: the error taken as it is ($fe7702 cmpi.w #1)     */
/* fm_error: a code past MS-DOS's error numbers shows nothing ($fe771a cmpi.w #63); each one it knows its own string,
 * every other "TOS error #%W", merged over the code's own word. */
#define FM_ERROR_LAST_CODE    63
#define FM_ERROR_FIRST_CODE   2          /* the jump table's first row          ($fe7744 subq.w #2)            */
#define FM_ERROR_LEVEL        1          /* every alert's default button        ($fe775a move.w #1)            */
#define FM_ERROR_NOT_FOUND    19         /* "...can't find the folder or file..." ($fe772c moveq #19)          */
#define FM_ERROR_NO_HANDLES   21         /* "...doesn't have room to open another document" ($fe7730 #21)     */
#define FM_ERROR_DENIED       22         /* "An item with this name already exists..." ($fe7734 #22)           */
#define FM_ERROR_NO_DRIVE     23         /* "The drive you specified does not exist..." ($fe773c #23)          */
#define FM_ERROR_NO_MEMORY    25         /* "There isn't enough memory..."      ($fe7738 #25)                  */
#define FM_ERROR_TOS_ERROR    26         /* "TOS error #%W."                    ($fe7740 #26)                  */
/* ...and the MS-DOS error numbers its table has a row for (GEM's DOS binding's), each row's target cited. */
#define DOS_FILE_NOT_FOUND    2          /* row 0  -> $fe772c, FM_ERROR_NOT_FOUND                              */
#define DOS_PATH_NOT_FOUND    3          /* row 1  -> $fe772c                                                  */
#define DOS_NO_HANDLES        4          /* row 2  -> $fe7730, FM_ERROR_NO_HANDLES                             */
#define DOS_ACCESS_DENIED     5          /* row 3  -> $fe7734, FM_ERROR_DENIED                                 */
#define DOS_NO_MEMORY         8          /* row 6  -> $fe7738, FM_ERROR_NO_MEMORY                              */
#define DOS_BAD_ENVIRONMENT   10         /* row 8  -> $fe7738                                                  */
#define DOS_BAD_FORMAT        11         /* row 9  -> $fe7738                                                  */
#define DOS_BAD_DRIVE         15         /* row 13 -> $fe773c, FM_ERROR_NO_DRIVE                               */
#define DOS_NO_MORE_FILES     18         /* row 16 -> $fe772c                                                  */

/* ---- the bell: BIOS Bconout of a BEL to the console ($fe3a0c move.w #7; $fe3a10 move.l #$30002) ------------------ */
#define BELL_DEVICE           2          /* CON:                                                               */

#ifndef __ASSEMBLER__
int16_t aes_fm_button(uint8_t *image, uint32_t tree, int16_t object, int16_t clicks, uint32_t next_at); /* $fe7346 */
int16_t aes_fm_do(uint8_t *image, uint32_t tree, int16_t start);                                        /* $fe74a4 */
uint16_t aes_fm_dial(uint8_t *image, int16_t type, uint32_t little, uint32_t big);                      /* $fe75ec */
int16_t aes_fm_alert(uint8_t *image, int16_t default_button, uint32_t string);                          /* $fe7002 */
int16_t aes_fm_show(uint8_t *image, int16_t string_number, uint32_t values, int16_t default_button);   /* $fe764c */
int16_t aes_eralert(uint8_t *image, int16_t error, int16_t drive);                                      /* $fe768c */
int16_t aes_fm_error(uint8_t *image, int16_t code);                                                     /* $fe7712 */
void aes_bell(uint8_t *image);                                                                          /* $fe3a0c */
#endif

#endif /* TOS102US_AES_FMDO_H */
