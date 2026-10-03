/* aes/fmlib.h — the FORM LIBRARY's event-free half (`src/aes/fmlib.c`): an alert string split into the alert tree's
 * lines and buttons (fm_strbrk, fm_parse) and the tree laid out for them (fm_build) — gemfmalt; the next field or the
 * default button found (find_obj, fm_inifld) and a form key turned into a move between fields (fm_keybd) — gemfmlib;
 * and the keyboard queue fm_do flushes before it waits (fq, dq — the event layer's own leaves, which reach no
 * dispatcher).
 *
 * ALCYON C, every routine entered by a Line-F call over its caller's frame (a tree, a string or a pointer a LONGWORD,
 * an object, a count or a key a WORD). find_obj, fm_inifld, fm_keybd and dq answer a WORD their callers read; the rest
 * leave a callee's D0, which no caller reads.
 *
 * THE ALERT TREE is the AES resource's tree 1 (rs_gaddr(R_TREE, 1), `$fe701e`): the root, the icon at object 1, five
 * message lines from object 2 (G_STRINGs over 32-byte buffers) and three buttons from object 7 (G_BUTTONs over 11-byte
 * buffers, so a button text of more than ten characters runs into the next button's). fm_build rebuilds it IN PLACE:
 * its sizes in character cells with a pixel offset in each word's high byte, which rs_obfix later turns to pixels.
 */
#ifndef TOS102US_AES_FMLIB_H
#define TOS102US_AES_FMLIB_H

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

#include "aes/objects.h"

/* ---- the alert string: "[icon][line|line|...][button|button|...]" ------------------------------------------------ */
#define ALERT_SECTION_END     0x5d       /* ']' — a section's end   ($fe6cee cmpb #93)                       */
#define ALERT_SEPARATOR       0x7c       /* '|' — a line's or a button's end ($fe6cf4 cmpb #124); doubled, itself */
#define ALERT_LINE_CHARACTERS 31         /* a line's characters past which the rest is skipped ($fe6cd4 cmpw #31) */
#define ALERT_ICON_DIGIT      1          /* the icon's digit, the string's second byte ($fe6d90 movea.l #1)    */
#define ALERT_FIRST_LINE_AT   4          /* the message section's first character, past "[n][" ($fe6daa move.w #4) */
#define ALERT_ICON_OBJECT     1          /* ($fe6f4e move.w #1: ob_setxywh)                                    */
#define ALERT_FIRST_LINE      2          /* the first message line's object     ($fe6dbc move.w #2)            */
#define ALERT_FIRST_BUTTON    7          /* the first button's object           ($fe6dde move.w #7)            */
/* fm_build's objects whose links it resets to none (lbcopy of six $ff bytes from $fefa0e, `$fe6f1e`): the root, the
 * icon, five lines and three buttons — the tree's every object. */
#define ALERT_OBJECTS         10         /* ($fe6f3a cmpw #10)                                                 */

/* ---- fm_build's layout, in character cells (a word's low byte) and pixels (its high byte) ------------------------- */
#define ALERT_ICON_CELLS      4          /* the icon's width and height         ($fe6e04, $fe6e0a move.w #4)   */
#define ALERT_BUTTON_GAP      2          /* cells between two buttons, and the box's margin ($fe6e1e asl.w #1, $fe6e40 addq.w #2) */
#define ALERT_LINES_AT        0x00020300 /* the first line's x and y: 2 cells, 3 pixels ($fe6e58 move.l #$20300) */
#define ALERT_ICON_AT         0x00010001 /* the icon's x and y: 1 cell, 1 cell  ($fe6e7c move.l #$10001)       */
#define ALERT_BOX_FOOT        3          /* cells added under the lines         ($fe6eb6 addq.w #3)            */
#define ALERT_PIXEL_SHIFT     8          /* a word's pixel offset, its high byte ($fe6f08 asl.w #8)            */
/* The flags fm_build gives each button: SELECTABLE and EXIT; the last (object count + 6, `$fe6ff2 addq.w #6`) also
 * LASTOB, the tree's end ($fe6fa4 move.w #5, $fe6ffc move.w #$25). */
#define ALERT_BUTTON_FLAGS    (OB_FLAG_SELECTABLE | OB_FLAG_EXIT)
#define ALERT_LAST_BUTTON_FLAGS (ALERT_BUTTON_FLAGS | OB_FLAG_LASTOB)

/* ---- find_obj's directions (fm_keybd's and fm_inifld's `which`) ----------------------------------------------------- */
#define FMD_FORWARD           0          /* the next EDITABLE after the object  ($fe723c beq)                  */
#define FMD_BACKWARD          1          /* ...the one before it                ($fe7242 cmpw #1)              */
#define FMD_DEFLT             2          /* the first DEFAULT from the root     ($fe7248 cmpw #2)              */

/* ---- fm_keybd's keys: search table $fefa30 (6 keys and 0, every other key the 0's arm) ----------------------------- */
#define FM_KEY_BACKTAB        0x0f00     /* shift-Tab: the field before         (-> $fe72b6)                   */
#define FM_KEY_TAB            0x0f09     /* the next field                      (-> $fe72be)                   */
#define FM_KEY_RETURN         0x1c0d     /* the default button                  (-> $fe72aa)                   */
#define FM_KEY_UP             0x4800     /* the field before                    (-> $fe72b6)                   */
#define FM_KEY_DOWN           0x5000     /* the next field                      (-> $fe72be)                   */
#define FM_KEY_ENTER          0x720d     /* the keypad's Enter: the default     (-> $fe72aa)                   */
/* fm_keybd's answer — and fm_button's (`aes/fmdo.h`): 0 the form is done (a default button was found and selected, an
 * exit taken), 1 it goes on. */
#define FM_KEYBD_DONE         0          /* ($fe733e clr.w d0)                                                 */
#define FM_KEYBD_GO_ON        1          /* ($fe7342 moveq #1,d0)                                              */

/* ---- the keyboard queue a CDA holds (`aes/aes.h`'s CDA at +14): eight keys in a ring -------------------------------- */
#define CDA_KEY_QUEUE         14         /* bytes[CQUEUE_BYTES]: the queue fq flushes ($fe5104 addi.l #14)       */
#define CQUEUE_KEYS           0          /* words[CQUEUE_ENTRIES]: the keys     ($fe50f2 move.w 0(a5,a0.l),d0)  */
#define CQUEUE_FRONT          16         /* word: the next key dq takes         ($fe50da move.w 16(a5),d7)      */
#define CQUEUE_COUNT          20         /* word: keys queued                   ($fe50d6 subq.w #1,20(a5))      */
#define CQUEUE_ENTRIES        8          /* the front wraps to 0 here           ($fe50e2 cmpi.w #8)             */
#define CQUEUE_BYTES          22

#ifndef __ASSEMBLER__
void aes_fm_strbrk(uint8_t *image, uint32_t tree, uint32_t string, int16_t object, uint32_t index_at,
                   uint32_t count_at, uint32_t longest_at);                                              /* $fe6c98 */
void aes_fm_parse(uint8_t *image, uint32_t tree, uint32_t string, uint32_t icon_at, uint32_t lines_at,
                  uint32_t line_length_at, uint32_t buttons_at, uint32_t button_length_at);              /* $fe6d84 */
void aes_fm_build(uint8_t *image, uint32_t tree, int16_t have_icon, int16_t lines, int16_t line_length,
                  int16_t buttons, int16_t button_length);                                               /* $fe6df8 */
int16_t aes_find_obj(uint8_t *image, uint32_t tree, int16_t start, int16_t which);                       /* $fe7214 */
int16_t aes_fm_inifld(uint8_t *image, uint32_t tree, int16_t field);                                     /* $fe727a */
int16_t aes_fm_keybd(uint8_t *image, uint32_t tree, int16_t object, uint32_t key_at, uint32_t next_at);  /* $fe7298 */
int16_t aes_dq(uint8_t *image, uint32_t queue);                                                          /* $fe50ca */
void aes_fq(uint8_t *image);                                                                             /* $fe50f8 */
#endif

#endif /* TOS102US_AES_FMLIB_H */
