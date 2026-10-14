/* desk/deskdir.h — THE COPY ENGINE'S HELPERS, unit C (`src/desk/deskdir.c`): its dialogs' drawing (`$fdcf04..$fdd0a3`),
 * the path editors (`$fdd0a4..$fdd19f`), the DOS verdict and the delete (`$fdd1a0`, `$fdd1ce`), and the check that a
 * folder is not copied into itself (`$fdd762`, `$fdd7a6`) — band 6 wave 1b, group G4.
 *
 * NAMES: the published GEM desktop's (DESKDIR: draw_fld, add_path, sub_path, add_fname, del_fname, get_fname,
 * d_errmsg, d_dofdel, do_namecon, par_chk), each read from its body; draw_dial, show_dial, hide_dial (show_hide's two
 * halves in this ROM) and path_part are this file's own.
 *
 * WHAT YIELDS: every routine that ends on a binding of unit D (the dialogs', d_errmsg's alert arm, par_chk's alert arm).
 * WHAT A ROM CALLER READS IN D0 WHERE THE C ANSWERS NOTHING: the void routines here (draw_dial, show_dial, draw_fld,
 * get_fname, do_namecon) leave their last callee's D0 in the ROM — counted, and read by no caller
 * (`test/test_desk_dir.py`).
 */
#ifndef TOS102US_DESK_DESKDIR_H
#define TOS102US_DESK_DESKDIR_H

#include "desk/deskglobals.h"

/* (The desk's globals these routines read — the two dialogs' trees and flags, ml_ftmp, g_tmppth and par_chk's second
 * copy, the screen's objects: `desk/deskglobals.h`, their one home.) */

/* ---- the dialogs: centred, shown, drawn ------------------------------------------------------------------------- */
/* The rectangle form_center answers through four pointers — into the frame as the ROM lays its locals: x at -2(a6),
 * then DOWNWARD (`$fdcf08`: the four `pea`s) — offsets from the frame's lowest word, -8(a6) */
#define DIAL_X                6
#define DIAL_Y                4
#define DIAL_W                2
#define DIAL_H                0
#define DIAL_RECT_BYTES       8
#define DIAL_DEPTH            8          /* objc_draw's depth: the whole tree    ($fdcf34 move.w #8,-(sp))      */
#define DRAW_FLD_DEPTH        0          /* ...draw_fld's: the object alone      ($fdd090 clr.w -(sp))          */
/* do_namecon: the copy dialog's item it shows SELECTED while the dialog is drawn again (`$fdcf82 move.l #$00040001`) */
#define COPY_DIALOG_ITEM      4
#define COPY_DIALOG_NO_REDRAW 0

/* ---- the path editors: a path is "D:\FOLDER\...\*.*" ------------------------------------------------------------ */
#define PATH_SEPARATOR        '\\'
#define PATH_WILDCARD         '*'        /* the "*.*" a path ends on            ($fdd0b4 cmpi.b #42,(a5))      */
#define AES_DESK_ADD_PATH_TAIL 0xfef42e  /* "\*.*"                              ($fdd0c6 move.l #$fef42e,-(sp)) */
#define AES_DESK_SUB_PATH_TAIL 0xfef433  /* "\*.*"                              ($fdd0fe move.l #$fef433,-(sp)) */
#define AES_DESK_DEL_FNAME_TAIL 0xfef438 /* "\*.*"                              ($fdd14c move.l #$fef438,-(sp)) */
#define AES_DESK_PAR_CHK_TAIL 0xfef44d   /* "\*.*"                              ($fdd880 move.l #$fef44d,-(sp)) */
#define AES_DESK_PAR_CHK_END_SOURCE 0xfef452 /* "*.*": the source's parts are done ($fdd8c0 move.l #$fef452,(sp)) */
#define AES_DESK_PAR_CHK_END_DESTINATION 0xfef456 /* "*.*": the destination's   ($fdd8d0 move.l #$fef456,(sp))  */
#define WILDCARD_TAIL_BYTES   3          /* par_chk cuts the source's "*.*"    ($fdd85a clr.b 6625(a0): 6628 - 3) */

/* ---- d_errmsg: the DOS glue's verdict (`aes/gemdosif.h`) and the alert of a GEMDOS error ---------------------------- */
#define D_ERRMSG_LEAST_ALERTED (-32)     /* an answer above it shows nothing    ($fdd1ac cmpi.w #-32,$c918: bgt) */
#define D_ERRMSG_CODE_BIAS    30         /* form_error's code: ~answer - 30     ($fdd1c0 addi.w #-30,(sp))     */
#define D_ERRMSG_FAILED       0          /* ($fdd1c6 clr.w d0)                                                  */
#define D_ERRMSG_DONE         1          /* ($fdd1ca moveq #1,d0)                                               */
/* d_dofdel's dos_delete call: the site its Line-F call returns to — what dos_delete parks in AES_DOS_RETURN */
#define AES_DESK_D_DOFDEL_DELETE_RETURN 0xfdd1d8

/* ---- par_chk ------------------------------------------------------------------------------------------------------- */
#define FNODE_NO_OBJECT       0xffff     /* an FNODE shown by no object         ($fdd7da cmpi.w #-1,32(a3))    */
#define PAR_CHK_ALERT_DEFAULT 1          /* fun_alert(1, 22, 0)                 ($fdd906 move.l #$00010016)    */
#define PAR_CHK_ALERT_STRING  22         /* the desk's string: a folder into itself                            */
#define PAR_CHK_ALERT_NO_PARAMETERS 0
#define PAR_CHK_REFUSED       0          /* ($fdd910 clr.w d0)                                                  */
#define PAR_CHK_ALLOWED       1          /* ($fdd914 moveq #1,d0)                                               */

#ifndef __ASSEMBLER__
#include <stdint.h>

void aes_desk_draw_dial(uint8_t *image, uint32_t tree);                                                         /* $fdcf04 */
void aes_desk_do_namecon(uint8_t *image);                                                                       /* $fdcf48 */
uint16_t aes_desk_hide_dial(uint8_t *image, uint32_t tree);                                                     /* $fdcfa8 */
void aes_desk_show_dial(uint8_t *image, uint32_t tree);                                                         /* $fdcfea */
void aes_desk_draw_fld(uint8_t *image, uint32_t tree, int16_t object);                                          /* $fdd04c */
uint32_t aes_desk_add_path(uint8_t *image, uint32_t path, uint32_t name);                                       /* $fdd0a4 */
uint32_t aes_desk_sub_path(uint8_t *image, uint32_t path);                                                      /* $fdd0d2 */
uint32_t aes_desk_add_fname(uint8_t *image, uint32_t path, uint32_t name);                                      /* $fdd10a */
uint32_t aes_desk_del_fname(uint8_t *image, uint32_t path);                                                     /* $fdd12c */
void aes_desk_get_fname(uint8_t *image, uint32_t path, uint32_t text);                                          /* $fdd158 */
int16_t aes_desk_d_errmsg(uint8_t *image);                                                                      /* $fdd1a0 */
int16_t aes_desk_d_dofdel(uint8_t *image, uint32_t name);                                                       /* $fdd1ce */
uint32_t aes_desk_path_part(uint8_t *image, uint32_t cursor, uint32_t path);                                    /* $fdd762 */
int16_t aes_desk_par_chk(uint8_t *image, uint32_t source, uint32_t files, uint32_t destination);                /* $fdd7a6 */
#endif

#endif /* TOS102US_DESK_DESKDIR_H */
