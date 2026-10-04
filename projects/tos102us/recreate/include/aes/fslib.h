/* aes/fslib.h — the FILE SELECTOR (`src/aes/fslib.c`, gemfslib): its tree found and centred at start-up (fs_start), a
 * path cut back to its directory and its file spec found (fs_back, fs_pspec), a directory read, filtered and sorted
 * (fs_active), the list's top moved a row (fs_1scroll), nine names laid into the list and its slider sized
 * (fs_format), a row selected (fs_sel), the list scrolled on the screen (fs_nscroll), a directory read and shown
 * whole (fs_newdir) — and the selector itself, run until OK or Cancel (fs_input).
 *
 * ALCYON C, every routine entered by a Line-F call over its caller's frame (a tree, a string or a pointer a LONGWORD,
 * a row, a count or an object a WORD). fs_back and fs_pspec answer a POINTER (D0 whole), fs_1scroll and fs_nscroll the
 * list's top (a WORD), fs_active and fs_format the 1 their tails leave, fs_input 1 — or 0 when GEMDOS has no memory
 * for its three blocks; the rest leave a callee's D0, which no caller reads.
 *
 * WHERE THE NAMES LIVE. fs_input ($fe7d90) Mallocs three blocks for its run and frees them at its end: the NAMES
 * (AES_AD_FSNAMES), the INDEX (AES_AD_FSINDEX) and the DTA (AES_AD_FSDTA). fs_active copies each name it keeps out of
 * the DTA from ONE BYTE BELOW the name — the last byte of the DTA's file length, which it first overwrites with the
 * name's kind: FS_FOLDER_MARK for a folder, a space for a file — packs them end to end in the names block, each
 * followed by its NUL and one spare byte, and stores each one's offset as a LONGWORD in the index. The sort moves the
 * index's longwords alone.
 */
#ifndef TOS102US_AES_FSLIB_H
#define TOS102US_AES_FSLIB_H

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

#include "aes/gemgraf.h"

/* ---- the selector's globals ------------------------------------------------------------------------------------- */
#define AES_AD_FSTREE         0x972a     /* long: the selector's tree           ($fe7796 move.l -4(a6),$972a)  */
#define AES_GL_RFS            0x9c00     /* bytes[GRECT_BYTES]: its box, centred ($fe779e move.l #$9c00)       */
#define AES_AD_HGMICE         0xc6aa     /* long: the busy mouse form           ($fe782e move.l $c6aa,(sp))    */
#define AES_AD_FSDTA          0xc838     /* long: fs_input's DTA block          ($fe7842 move.l $c838,(sp))    */
#define AES_AD_FSNAMES        0xc72e     /* long: ...its names block            ($fe78c4 add.l $c72e,d0)       */
#define AES_AD_FSINDEX        0xc7f8     /* long: ...its index block            ($fe78e2 adda.l $c7f8,a1)      */
/* What fs_input Mallocs for them: a hundred names of a kind byte, twelve of name, a NUL and a spare each, and a
 * hundred offsets, both with room over. */
#define FS_NAMES_BLOCK_BYTES  1600       /* ($fe7d9e move.l #1600)                                             */
#define FS_INDEX_BLOCK_BYTES  400        /* ($fe7dba move.l #400)                                              */
#define FS_DTA_BLOCK_BYTES    256        /* ($fe7dde move.l #256)                                              */
/* Two string scratches, addresses (their room is the gap to the next global, which no routine here bounds): a name to
 * compare or to format, and a row's or the title's text. The text's is 40 bytes, up to gl_mntree: fs_newdir's title of
 * a spec past 37 characters runs on over it, and from 50 over gl_rzero — the ROM's, reproduced. */
#define AES_FS_TEXT           0x9afe     /* ($fe7954 move.l #$9afe: the sort's left name; a row's text)        */
#define AES_FS_NAME           0x9b46     /* ($fe7978 move.l #$9b46: the sort's right name; the name formatted) */
/* ...and each past its first byte — a name's kind, the title's leading space — where the text proper starts. */
#define AES_FS_TEXT_BODY      (AES_FS_TEXT + 1)   /* ($fe7a94 move.l #$9aff)                                   */
#define AES_FS_NAME_BODY      (AES_FS_NAME + 1)   /* ($fe7a9a move.l #$9b47)                                   */

/* ---- the ROM's own strings and the title's redraw list, read in place ---------------------------------------- */
#define AES_FS_DEFAULT_PATH   0xfefafc   /* "A:\*.*": what fs_pspec makes of a path with no `\` ($fe7814)      */
#define AES_FS_TITLE_TAIL     0xfefb03   /* " ": after the spec in the title    ($fe7d4a move.l #$fefb03)      */
#define AES_FS_REDRAWN        0xfefaac   /* bytes: 5, 6, 7, 0 — the objects fs_newdir draws last ($fe7d62)     */
#define FS_DEFAULT_SPEC_AT    3          /* the spec in that path, past "A:\"   ($fe781e lea 3(a5),a4)         */
#define AES_FS_FIRST_TITLE    0xfefb05   /* " *.* ": the title fs_input starts with ($fe7e20 move.l #$fefb05)  */
#define AES_FS_EVERY_NAME     0xfefb0b   /* "*.*": the spec GEMDOS is always searched with ($fe7fb6)           */

/* ---- the selector's tree (the AES resource's tree 0) -------------------------------------------------------------- */
#define FS_TREE_INDEX         0          /* ($fe778a clr.l: R_TREE, tree 0)                                    */
#define FS_DIRECTORY          2          /* the path field                      ($fe7d02 move.w #2)            */
#define FS_SELECTION          3          /* the selection field                 ($fe7e8a move.w #3)            */
#define FS_CLOSER             4          /* the close box: the folder above     ($fefab0's row 0 -> $fe8144)   */
#define FS_TITLE              5          /* the title: the directory read again ($fefab0's row 1 -> $fe81a0)   */
#define FS_FILE_BOX           6          /* the list's box                      ($fe7cd2 move.w #6)            */
#define FS_SLIDER_BOX         7          /* the box round the arrows and the track ($fefab0's row 3 -> $fe81be) */
#define FS_SLIDER             10         /* the slider's track                  ($fe7cea move.w #10)           */
#define FS_ELEVATOR           11         /* ...and its elevator                 ($fe7b5a adda.l #282: 11's y)  */
#define FS_FIRST_NAME         12         /* the list's first row                ($fe7ad2 addi.w #12)           */
#define FS_ROWS               9          /* the rows shown                      ($fe7a5a move.w #9)            */
#define FS_UP_ARROW           8          /* the arrow that scrolls up           ($fe7a12 cmp.w #8)             */
#define FS_DOWN_ARROW         9          /* ...and down                         ($fe8042 moveq #9,d0)          */
#define FS_LAST_NAME          (FS_FIRST_NAME + FS_ROWS - 1)   /* the list's last row ($fefab0's row 16)       */
#define FS_OK                 21         /* ($fe7f36 cmp.w #21,d7)                                             */
#define FS_CANCEL             22         /* ($fe7f3c cmp.w #22,d7)                                             */
#define FS_DRAW_DEPTH         8          /* ob_draw's depth: the whole subtree  ($fe7cfe move.w #8)            */
#define FS_TREE_OBJECTS       25         /* the tree's objects, 0..24: two past Cancel, the last LASTOB       */
/* A row as fs_sel takes it: 1..9 (0 none), the object before the list's first plus it ($fe7b82 addi.w #11); its
 * ob_change always redraws (OB_CHANGE_REDRAW, `aes/objdraw.h`: $fe7b7a move.w #1). */
#define FS_ROW_OBJECT_BEFORE  (FS_FIRST_NAME - 1)
#define FS_PUT_DOWN           0          /* a row's or a button's state, no bit of it set ($fe7af4 clr.w)      */

/* ---- fs_back and fs_pspec: the `:` and the `\` they stop on are `aes/shell.h`'s SH_DRIVE_SEPARATOR ($fe77c2
 * cmpi.b #58) and SH_DIRECTORY_SEPARATOR ($fe77c8 cmpi.b #92) ---------------------------------------------------- */
#define FS_PATH_ROOM          64         /* ins_char's room for the `\` put after a `:` ($fe77da move.w #64)   */

/* ---- fs_active -------------------------------------------------------------------------------------------------- */
#define FS_SEARCH_ATTRIBUTES  0x10       /* Fsfirst: folders too                ($fe784a move.w #16)           */
#define FS_NAMES              100        /* the names kept; at the 100th the bell, and no more ($fe78fe)       */
#define FS_FOLDER_MARK        0x07       /* a folder's kind byte                ($fe787c moveq #7)             */
#define FS_FILE_MARK          0x20       /* a file's                            ($fe7880 moveq #32)            */
#define FS_KIND_BEFORE_NAME   1          /* the kind's byte, below the DTA's name ($fe7888 move.b d0,29(a1))   */
#define FS_NAME_SPARE         2          /* the NUL and one spare byte after each name ($fe78ee addq.w #2)     */
#define FS_INDEX_ENTRY_BYTES  4          /* a name's offset, a LONGWORD         ($fe78de adda.l a1,a1 twice)   */
#define FS_HIDDEN_FIRST       0x2e       /* '.': `.` and `..` are not listed    ($fe7864 cmpi.b #46)           */
#define FS_SORT_SHRINK        2          /* the shell sort's gap halved         ($fe7926 divs.w #2)            */
#define FS_ACTIVE_ANSWER      1          /* ($fe79fa moveq #1,d0)                                              */

/* ---- fs_format's frame (`link a6,#-10`) from -10(a6): what fs_sset answers through, each handed by address ------ */
#define FS_FORMAT_LENGTH      0          /* word: te_txtlen                     ($fe7ac0 addi.l #-10)          */
#define FS_FORMAT_TEXT        4          /* long: te_ptext                      ($fe7ac8 subq.l #6)            */
#define FS_FORMAT_FRAME_BYTES 8
#define FS_FORMAT_ANSWER      1          /* ($fe7b6c moveq #1,d0)                                              */
/* A row past the names is the text of a FILE's row with no name — its kind byte alone ($fe7ab0 move.b #32): the ROM's
 * own store, apart from fs_active's, of the one byte, and why a click on such a row is taken for a file's ($fe80d8).
 * (`STRING_SPACE`, which fs_newdir's title is padded with, is another thing: a character of a text, no row's kind.) */
#define FS_EMPTY_ROW          FS_FILE_MARK
#define FS_HALF               2          /* the elevator at least half a box tall ($fe7b32 divs.w #2)          */

/* ---- fs_nscroll's frame (`link a6,#-18`) from -18(a6): the clip saved and the list's rows, by address ----------- */
#define FS_NSCROLL_CLIP       0          /* bytes[GRECT_BYTES]: gsx_gclip's     ($fe7be4 addi.l #-18)          */
#define FS_NSCROLL_ROWS       GRECT_BYTES /* bytes[GRECT_BYTES]: ob_actxywh's   ($fe7bee addi.l #-10)          */
#define FS_NSCROLL_FRAME_BYTES (2 * GRECT_BYTES)
#define FS_SCROLL_RULE        3          /* bb_screen's rule: the source copied ($fe7c3e move.w #3)            */

/* ---- fs_input ----------------------------------------------------------------------------------------------------- */
/* Its frame (`link a6,#-46`) from -38(a6), every word and long it hands on by address — fs_sset's three lengths and
 * three text pointers, the elevator's place (ob_offset's), the selected row (fs_nscroll's), the mouse (gsx_mxmy's)
 * and the count (fs_newdir's) — laid out as the ROM's `link` lays them. The four flags below them (-46..-40(a6)) and
 * the list's top (-4(a6)) are kept by value: three across the passes (-46, -44, -42: fslib.c's `struct selector_run`),
 * the fourth — the double click's, -40, stored and read inside one pass — a local of that pass. */
#define FS_INPUT_TITLE_LENGTH 0          /* word: fs_sset's                     ($fe7e12 addi.l #-38)          */
#define FS_INPUT_PATH_LENGTH  2          /* word: fs_sset's, THEN the working path's length ($fe7f0e -36(a6)) */
#define FS_INPUT_SELECTION_LENGTH 4      /* word: fs_sset's                     ($fe7e76 addi.l #-34)          */
#define FS_INPUT_TITLE_TEXT   6          /* long: the title's te_ptext          ($fe7e1a addi.l #-32)          */
#define FS_INPUT_SELECTION_TEXT 10       /* long: the selection field's         ($fe7e7e addi.l #-28)          */
#define FS_INPUT_PATH_TEXT    14         /* long: the path field's              ($fe7e3e addi.l #-24)          */
#define FS_INPUT_ELEVATOR_Y   22         /* word: ob_offset's                   ($fe8018 addi.l #-16)          */
#define FS_INPUT_ELEVATOR_X   24         /* word                                ($fe8020 addi.l #-14)          */
#define FS_INPUT_SELECTED     26         /* word: the row selected, 0 none      ($fe7ec2 clr.w -12(a6))        */
#define FS_INPUT_MOUSE_Y      28         /* word: gsx_mxmy's                    ($fe7ef0 addi.l #-10)          */
#define FS_INPUT_MOUSE_X      30         /* word                                ($fe7ef8 subq.l #8)            */
#define FS_INPUT_COUNT        32         /* word: the names listed              ($fe7fc2 subq.l #6)            */
#define FS_INPUT_FRAME_BYTES  34
#define FS_FIRST_DRAW_DEPTH   1          /* the first ob_draw: the root and its children ($fe7eb6 move.w #1)   */
#define FS_ARROW_ROWS         1          /* an arrow scrolls a row              ($fe8010 moveq #1,d6)          */
#define FS_SLIDE_SCALE        1000       /* gr_slidebox's answer, 0..1000       ($fe8068 move.w #1000)         */
#define FS_SLIDE_VERTICAL     1          /* ($fe8052 move.w #1,(sp))                                           */
#define FS_INPUT_DONE         1          /* ($fe82d2 moveq #1,d0)                                              */
#define FS_INPUT_NO_MEMORY    0          /* ($fe7db4, $fe7dd8, $fe7e04 clr.w d0)                               */
/* What inf_what answers with neither button SELECTED: the button word is then 0, Cancel's ($fe82ae cmp.w #-1). */
#define FS_NO_BUTTON          (-1)
#define FS_CANCELLED          0

#ifndef __ASSEMBLER__
void aes_fs_start(uint8_t *image);                                                                       /* $fe7782 */
uint32_t aes_fs_back(uint8_t *image, uint32_t path, uint32_t end);                                       /* $fe77ae */
uint32_t aes_fs_pspec(uint8_t *image, uint32_t path, uint32_t end);                                      /* $fe77ee */
int16_t aes_fs_active(uint8_t *image, uint32_t path, uint32_t spec, uint32_t count_at);                  /* $fe7826 */
int16_t aes_fs_1scroll(int16_t top, int16_t count, int16_t arrow);                                       /* $fe79fe */
int16_t aes_fs_format(uint8_t *image, uint32_t tree, int16_t top, int16_t count);                        /* $fe7a44 */
void aes_fs_sel(uint8_t *image, int16_t row, int16_t state);                                             /* $fe7b70 */
int16_t aes_fs_nscroll(uint8_t *image, uint32_t tree, uint32_t row_at, int16_t top, int16_t count, int16_t arrow,
                       int16_t rows);                                                                    /* $fe7b92 */
void aes_fs_newdir(uint8_t *image, uint32_t title, uint32_t path, uint32_t spec, uint32_t tree,
                   uint32_t count_at);                                                                   /* $fe7cfa */
int16_t aes_fs_input(uint8_t *image, uint32_t path, uint32_t selection, uint32_t button_at);            /* $fe7d90 */
#endif

#endif /* TOS102US_AES_FSLIB_H */
