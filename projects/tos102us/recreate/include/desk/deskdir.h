/* desk/deskdir.h — THE COPY ENGINE AND ITS HELPERS, unit C (`src/desk/deskdir.c`): its dialogs' drawing
 * (`$fdcf04..$fdd0a3`), the path editors (`$fdd0a4..$fdd19f`), the DOS verdict and the delete (`$fdd1a0`, `$fdd1ce`),
 * and the check that a folder is not copied into itself (`$fdd762`, `$fdd7a6`) — band 6 wave 1b, group G4; the engine,
 * d_dofcopy `$fdd1dc`, d_doop `$fdd454` and dir_op `$fdd918` — band 6 wave 2, group G1 (its block below).
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

/* ==== BAND 6 WAVE 2, group G1: THE COPY ENGINE — d_dofcopy `$fdd1dc`, d_doop `$fdd454`, dir_op `$fdd918` ============= */
/* ---- the desk's globals only the engine reads (the tallies and g_1text: `desk/deskglobals.h`) ---------------------- */
#define DESK_G_XBUF           6884       /* long: the copy buffer, Malloc'ed    ($fdd988 move.l d0,6884(a4))    */
#define DESK_G_XLEN           6888       /* long: ...its bytes: all free memory less XBUF_KEPT ($fdd976)       */
#define DESK_G_DTASTK         6892       /* DTA[DOOP_LEVELS + 1]: d_doop's search, one a folder level ($fdd47e) */
#define DESK_DTA_BYTES        44         /* ...a DTA's stride                   ($fdd476 muls.w #44,d1)         */
#define DESK_FILES_TEXT       14214      /* bytes: the dialog's files count, "%W" merged ($fdd724 addi.l #14214) */
#define DESK_FOLDERS_TEXT     14218      /* bytes: ...its folders count         ($fdd520 addi.l #14218)          */
#define DESK_FILES_OBJECT     14222      /* word: the dialog's object showing the files count ($fdd95a #3)     */
#define DESK_FOLDERS_OBJECT   14224      /* word: ...the folders count          ($fdd960 move.w #2,14224(a4))   */
#define DESK_OK_OBJECT        14226      /* word: ...its OK button              ($fdd966 move.w #4,14226(a4))   */
#define DESK_CANCEL_OBJECT    14228      /* word: ...its Cancel button          ($fdd96c move.w #5,14228(a4))   */
#define DESK_ML_FSRC          14234      /* bytes: ml_fsrc, the conflict's source name, 8.3 ($fdd242 #14234)    */
#define DESK_ML_FDST          14247      /* bytes: ml_fdst, ...its destination name, 8.3 ($fdd250 #14247)       */
#define DESK_ML_FSTR          14260      /* bytes: ml_fstr, the name typed, unformatted ($fdd32e #14260)        */
#define DESK_DELETE_DIALOG_TREE 8092     /* long: the delete dialog's tree       ($fdd954 move.l 8092(a4))      */
#define DESK_CONFIRM_COPIES   (DESK_PREFERENCES + 0)   /* word: Set Preferences' "confirm copies" ($fdd98c 8118)  */
#define DESK_CONFIRM_DELETES  (DESK_PREFERENCES + 2)   /* word: ..."confirm deletes" ($fdd94c 8120)               */
/* d_doop's deepest level below its top this walk — dir_op keeps the deepest of its walks in AES_DESK_OP_DEPTH */
#define AES_DESK_WALK_DEPTH   0xc834     /* word                                ($fdd46a move.w #1,$c834)       */

/* ---- the dialog's object numbers dir_op lays (its four words), and its two texts' template --------------------------- */
#define COPY_FILES_OBJECT     3          /* ($fdd95a move.w #3,14222(a4))                                       */
#define COPY_FOLDERS_OBJECT   2
#define COPY_OK_OBJECT        4
#define COPY_CANCEL_OBJECT    5
#define AES_DESK_DIR_OP_FILES_FORMAT   0xfef45a  /* "%W"                        ($fdd9d0 move.l #$fef45a,-(sp)) */
#define AES_DESK_DIR_OP_FOLDERS_FORMAT 0xfef45d  /* "%W"                        ($fdd9fa)                       */
#define AES_DESK_DIR_OP_FILE_FORMAT    0xfef465  /* "%W": a file done           ($fddd56)                       */
#define AES_DESK_DOOP_FOLDER_FORMAT    0xfef442  /* "%W": a folder done         ($fdd518)                       */
#define AES_DESK_DOOP_FILE_FORMAT      0xfef44a  /* "%W": a file done           ($fdd71c)                       */
#define AES_DESK_DOOP_RMDIR_TAIL       0xfef43d  /* "\*.*": put back after Ddelete ($fdd4ea)                    */
#define AES_DESK_DOOP_MKDIR_TAIL       0xfef445  /* "\*.*": after the new folder ($fdd610)                       */
#define AES_DESK_DIR_OP_FOLDER_TAIL    0xfef460  /* "\*.*": after the destination's folder ($fddc42)             */

/* ---- the engine's operations (dir_op's and d_doop's first argument) ------------------------------------------------- */
#define OP_COUNT              0          /* the selection counted (Show Info, the dialogs' first figures)       */
#define OP_DELETE             1
#define OP_COPY               2
#define XBUF_KEPT             512        /* free memory left GEMDOS by the buffer ($fdd97a subi.l #512,6888(a4)) */
#define DOOP_LEVELS           8          /* folders deeper than this are not entered ($fdd5c6 cmp.w #8,d4)     */
#define FOLDER_NAME_DOT       '.'        /* "." and "..": no folder to enter     ($fdd5bc cmpi.b #46)           */
#define DIALOG_UP             1          /* DESK_NAMECON_UP's word once a dialog is up ($fdda20 move.w #1)      */
#define FORM_DO_NO_EDIT       0          /* form_do's start object                ($fdda2c clr.w (sp))          */
/* The name-conflict dialog's fields and buttons: inf_sset 2 / 3, inf_what(4, 5) ($fdd2a4, $fdd2b8, $fdd2c6) */
#define NAMECON_SOURCE        2
#define NAMECON_DESTINATION   3
#define NAMECON_OK            4
#define NAMECON_SKIP          5
/* What the engine answers. (The conflict the folder's search makes up — dos_sfirst found it — is GEM_DOS_FAILED /
 * DOS_AX_ACCESS_DENIED, as fun_mkdir's: `desk_search_or_mkdir`, below.) */
#define COPY_STOPPED          0
#define COPY_GOES_ON          1
/* d_dofcopy: a write short of the read (the disk full): fun_alert(1, 17, 0) ($fdd3da move.l #$00010011) */
#define COPY_SHORT_ALERT_DEFAULT 1
#define COPY_SHORT_ALERT_STRING  17
#define COPY_SHORT_ALERT_NO_PARAMETERS 0
#define FCREATE_READ_ONLY_DROPPED 0xfffe /* the source's read-only bit off the copy ($fdd394 andi.w #-2,(sp))   */
#define DOS_OPEN_READ         0          /* Fopen's mode                          ($fdd1f0 clr.w (sp))          */
/* The sites each Line-F call to the glue's $fe3c28 family (and gem_gemdos_call) returns to — what is parked there */
#define AES_DESK_D_DOFCOPY_FREAD_RETURN          0xfdd21a
#define AES_DESK_D_DOFCOPY_CLOSE_WHOLE_RETURN    0xfdd240   /* the source read whole: closed at once           */
#define AES_DESK_D_DOFCOPY_CLOSE_FAILED_RETURN   0xfdd28c   /* the destination's Fopen failed otherwise        */
#define AES_DESK_D_DOFCOPY_CLOSE_FOUND_RETURN    0xfdd29c   /* the destination found: closed                   */
#define AES_DESK_D_DOFCOPY_CLOSE_SAME_RETURN     0xfdd322   /* the same file: nothing to copy                 */
#define AES_DESK_D_DOFCOPY_CLOSE_NO_NAME_RETURN  0xfdd34c   /* no name typed                                  */
#define AES_DESK_D_DOFCOPY_CLOSE_SKIPPED_RETURN  0xfdd35a   /* the conflict skipped                           */
#define AES_DESK_D_DOFCOPY_CREATE_RETURN         0xfdd39e
#define AES_DESK_D_DOFCOPY_FWRITE_RETURN         0xfdd3c2
#define AES_DESK_D_DOFCOPY_CLOSE_SHORT_DST_RETURN 0xfdd3ea  /* a short write: the destination closed...           */
#define AES_DESK_D_DOFCOPY_CLOSE_SHORT_SRC_RETURN 0xfdd3f0  /* ...and the source                                 */
#define AES_DESK_D_DOFCOPY_FREAD_AGAIN_RETURN    0xfdd414
#define AES_DESK_D_DOFCOPY_CLOSE_READ_END_RETURN 0xfdd42e   /* the source read to its end                      */
#define AES_DESK_D_DOFCOPY_CLOSE_DONE_RETURN     0xfdd450   /* the destination, its stamp set                 */
#define AES_DESK_D_DOOP_SDTA_FIRST_RETURN        0xfdd486
#define AES_DESK_D_DOOP_RMDIR_RETURN             0xfdd4e2
#define AES_DESK_D_DOOP_SDTA_UP_RETURN           0xfdd58c   /* a folder's end: back up a level                 */
#define AES_DESK_D_DOOP_SDTA_DOWN_RETURN         0xfdd632   /* a folder entered                               */
#define AES_DESK_DIR_OP_SDTA_RETURN              0xfddafe
#define AES_DESK_DIR_OP_FREE_RETURN              0xfdddc4

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
/* band 6 wave 2, group G1: the copy engine */
int16_t aes_desk_d_dofcopy(uint8_t *image, uint32_t source, uint32_t destination, uint32_t stamp, int16_t attributes); /* $fdd1dc */
int16_t aes_desk_d_doop(uint8_t *image, int16_t op, uint32_t tree, uint32_t source, uint32_t destination,
                        uint32_t files_count, uint32_t folders_count);                                           /* $fdd454 */
/* A C helper of units C and H (no ROM routine of its own): a folder searched, made up as refused where found, else
 * Dcreate'd — whether it was found. */
int desk_search_or_mkdir(uint8_t *image, uint32_t folder);
int16_t aes_desk_dir_op(uint8_t *image, int16_t op, uint32_t source, uint32_t files, uint32_t destination,
                        uint32_t files_count, uint32_t folders_count, uint32_t size);                            /* $fdd918 */
#endif

#endif /* TOS102US_DESK_DESKDIR_H */
