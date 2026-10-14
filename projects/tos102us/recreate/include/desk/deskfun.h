/* desk/deskfun.h — THE DESK'S ALERT AND ITS MESSAGE TO ITSELF, unit H (`src/desk/deskfun.c`): fun_alert `$fdfd58`, the
 * alert every file operation raises (an alert string of the desk's resource, a parameter merged into it), and fun_msg
 * `$fdfda6`, a message the desk writes to its own pipe (a window's redraw) — band 6 wave 1b, group G4.
 *
 * NAMES: the published GEM desktop's (DESKFUN), each read from its body.
 *
 * BOTH YIELD: each ends on a binding of unit D (`desk/deskbind.h`), so each is a row that switches at Tier 1; and both
 * answer the binding's own word, which the C has.
 */
#ifndef TOS102US_DESK_DESKFUN_H
#define TOS102US_DESK_DESKFUN_H

#include "desk/deskdir.h"
#include "desk/deskglobals.h"

/* fun_alert's string: `desk/deskglobals.h`'s DESK_G_ALERT — the address rs_gaddr answers for the resource's free
 * string, put back as the text merge_str made of it where the caller hands parameters. */

/* fun_msg's message, laid in its own frame and handed to appl_write by address: the eight words of an AES message. */
#define FUN_MSG_TYPE          0          /* word: the caller's type             ($fdfdaa -16(a6))              */
#define FUN_MSG_SENDER        2          /* word: gl_apid, the desk's own id    ($fdfdb0 -14(a6))              */
#define FUN_MSG_MORE          4          /* word: no bytes beyond the eight words ($fdfdb8 clr.w -12(a6))     */
#define FUN_MSG_WORD_3        6          /* words[5]: the caller's last five    ($fdfdbc -10(a6) .. -2(a6))    */
#define FUN_MSG_BYTES         16         /* appl_write's length                 ($fdfde2 move.w #16,-(sp))     */
#define FUN_MSG_NO_MORE       0

#ifndef __ASSEMBLER__
#include <stdint.h>

int16_t aes_desk_fun_alert(uint8_t *image, int16_t default_button, int16_t string, uint32_t parameters);      /* $fdfd58 */
uint16_t aes_desk_fun_msg(uint8_t *image, int16_t type, int16_t unread, int16_t word3, int16_t word4, int16_t word5,
                          int16_t word6, int16_t word7);                                                     /* $fdfda6 */
#endif

/* ---- band 6 wave 2, group G2 (unit H): THE OPERATIONS' DRIVERS --------------------------------------------------------
 *   $fdfdf2 fun_rebld(window)                    every open window showing the window's path read again (pn_active),
 *                                                verified, its info line set, a redraw of its work area sent
 *   $fdfebc fun_mkdir(window)                    File > New Folder: the dialog until a name is made or refused, Dcreate
 *   $fe003a fun_op(op, path)                     the copy engine (unit C's dir_op) over the path's selection — a copy
 *                                                checked first (par_chk) and counted, its depth bounded
 *   $fe0140 fun_ddst(path, anode, object)        a window's files dropped on a desktop icon: a disk (copy), the trash
 *                                                (delete), the cartridge (refused)
 *   $fe01d6 fun_wdst(path, spec, anode, fnode)   ...on a window: into the folder dropped on, or its own path (copy)
 *   $fe0258 fun_win2win(source, destination, object)   a drag from a window into a window
 *   $fe02f2 fun_win2desk(source, object)         a drag from a window onto a desktop icon
 *   $fe038c fun_disk(drive, window, anode, fnode, object)  a drive's root read and dropped as files (fun_wdst / fun_ddst)
 *   $fe0454 fun_desk2win(window, object)         the selected desktop icons dropped into a window
 *   $fe0500 fun_d2desk(object)                   ...dropped on a desktop icon: a disk copied (DISKCOPY), else refused
 *   $fe070a fun_drag(source, destination, root, object)  a drag's drop sent to its driver by where it began and ended
 * NAMES: the published GEM desktop's (DESKFUN) where it has the routine, each read from its body. */

/* fun_alert's strings (the desk resource's free strings), and its default button: the first. */
#define FUN_ALERT_FIRST_BUTTON 1
#define FUN_ALERT_SECOND_BUTTON 2         /* the disk alerts' default            ($fe05b6 move.l #$0002000c)    */
#define FUN_ALERT_NO_PARAMETERS 0
#define FUN_ALERT_ICON_ON_ICON 11        /* "You cannot place this icon over another icon." */
#define FUN_ALERT_DISK_TO_TRASH 12       /* "You cannot drag a disk to the trash can. ..." (handed the drive)  */
#define FUN_ALERT_DISK_COPY   13         /* "Copying disk %S: to disk %S: will ERASE ... disk %S: ..." [OK|Cancel] */
#define FUN_ALERT_FILES_TO_DESKTOP 14    /* "You cannot drag folders, files or applications onto the Desktop. ..." */
#define FUN_ALERT_DESKTOP_TO_WINDOW 15   /* "You cannot drag Desktop icons into a window." */
#define FUN_ALERT_NO_SUCH_FOLDER 16      /* "You can not create a folder with that name. ..." [Cancel|Retry]   */
#define FUN_ALERT_DISK_FULL   COPY_SHORT_ALERT_STRING /* "This disk does not have enough room ..." (unit C's) */
#define FUN_ALERT_TOO_DEEP    19         /* "You cannot create or access a folder this far down the directory path." */
#define FUN_ALERT_CARTRIDGE   20         /* "You cannot copy files or folders to or from the cartridge."       */
#define FUN_ALERT_INVALID_COPY PAR_CHK_ALERT_STRING /* "Invalid copy operation." (unit C's)                */
#define FUN_ALERT_OK          1          /* the disk copy's first button        ($fe0680 cmpi.w #1,-10(a6))    */

/* fun_rebld's frame: wind_get's four answers, the ROM's layout from -8(a6). */
#define FUN_REBLD_H           0          /* ($fdfe66 subq.l #8,(sp))                                           */
#define FUN_REBLD_W           2
#define FUN_REBLD_Y           4
#define FUN_REBLD_X           6
#define FUN_REBLD_FRAME_BYTES 8

/* fun_mkdir: its dialog (DESK_MKDIR_TREE) and the path it is built in (DESK_G_TMPPTH). */
#define MKDIR_NAME_FIELD      2          /* the name's field                    ($fdff26 move.w #2,-(sp))      */
#define MKDIR_OK              3          /* inf_what's two exits                ($fdff42 move.w #3,-(sp))      */
#define MKDIR_CANCEL          4
#define MKDIR_DEEPEST         8          /* separators past a spec's first byte ($fdfefc cmp.w #8,d3: ble)    */
#define FUN_MKDIR_NAME        0          /* bytes[14]: the name unformatted     ($fdff6c -26(a6))              */
#define FUN_MKDIR_TEXT        14         /* bytes[12]: the field's text         ($fdff1a -12(a6))              */
#define FUN_MKDIR_FRAME_BYTES 26
#define FUN_MKDIR_MADE        1          /* ($fe0036 moveq #1,d0)                                              */
#define FUN_MKDIR_TOO_DEEP    0          /* ($fdff0e clr.w d0)                                                 */

/* fun_op: nothing to do (the copy engine's operations are unit C's OP_*, `desk/deskdir.h`), its three answers' frame,
 * the deepest copy. */
#define OP_NONE               (-1)       /* nothing to do                       ($fe0046 cmpi.w #-1,8(a6))     */
#define FUN_OP_DEEPEST        9          /* the depth reached plus the separators ($fe00c4 cmpi.w #9,-12(a6))  */
#define FUN_OP_FILES          6          /* word: dir_op's three answers, the files ($fe0080 subq.l #2: -2(a6)) */
#define FUN_OP_FOLDERS        4          /* word: ...the folders                ($fe007c subq.l #4: -4(a6))    */
#define FUN_OP_SIZE           0          /* long: ...their bytes                ($fe0078 subq.l #8: -8(a6))    */
#define FUN_OP_FRAME_BYTES    8
#define FUN_OP_DONE           1          /* ($fe0138 moveq #1,d0)                                              */
#define FUN_OP_REFUSED        0

/* fun_ddst / fun_wdst: the destination spec, built in g_1text (DESK_G_1TEXT) — ROM texts. */
#define AES_FUN_ROOT_SPEC     0xfef5d8   /* ":\*.*", after a drive's letter    ($fe01aa move.l #$fef5d8)      */
#define AES_FUN_FOLDER_SPEC   0xfef5de   /* "\*.*", after a folder's name      ($fe0232 move.l #$fef5de)      */
#define AES_FUN_ALL_FILES     0xfef5e3   /* "*.*"                               ($fe0240 move.l #$fef5e3)      */
#define SPEC_WILDCARD         '*'        /* where a spec's name begins          ($fe020a cmpi.b #42,(a3))      */
/* fun_disk's path node over a drive: no path, "*" "*" ($fe03b0..$fe03bc), its attributes. ROM texts. */
#define AES_FUN_NO_PATH       0xfef5e7
#define AES_FUN_ANY_NAME      0xfef5e8
#define AES_FUN_ANY_EXT       0xfef5ea
#define FUN_DISK_ROOT_SELECTED 1         /* the screen's root's ob_state while the drop runs ($fe0402 move.w #1) */
#define FUN_DISK_NO_PATH_NODE 0          /* the C's answer where pn_open has none: the ROM's is its caller's D7 */
#define FM_ERROR_ACCESS_DENIED 5         /* fm_error's code: the cartridge's files cannot go to the trash ($fe034a) */

/* fun_win2win / fun_desk2win: i_find's two answers, the ROM's layout. */
#define FUN_WIN2WIN_FNODE     0          /* long ($fe02b4 subq.l #8: -8(a6))                                   */
#define FUN_WIN2WIN_ISAPP     4          /* ($fe02b0 subq.l #4: -4(a6))                                        */
#define FUN_WIN2WIN_FRAME_BYTES 8
#define FUN_DESK2WIN_EACH_FNODE 0        /* long: each icon's   ($fe0486 addi.l #-12: -12(a6))                 */
#define FUN_DESK2WIN_ISAPP    4          /* ...both calls'      ($fe046a subq.l #8: -8(a6))                    */
#define FUN_DESK2WIN_FNODE    8          /* long: the drop's    ($fe046e subq.l #4: -4(a6))                    */
#define FUN_DESK2WIN_FRAME_BYTES 12

/* fun_d2desk: its frame, the ROM's layout from -42(a6) — the disk copy alert's three parameters (the source's letter,
 * the destination's twice), the two letters' texts ("A" NUL, a blank, "B" NUL NUL: made "A: B:" after the alert, the
 * copy's tail), the trash alert's letter and its one parameter, i_find's two answers. */
#define FUN_D2DESK_COPY_PARAMETERS 0     /* longs[3]                            ($fe064a -42(a6))              */
#define FUN_D2DESK_SOURCE_TEXT 12        /* bytes: 'A', NUL / ':'               ($fe0620 -30(a6))              */
#define FUN_D2DESK_BLANK      14         /* ($fe0628 move.b #32,-28(a6))                                       */
#define FUN_D2DESK_DESTINATION_TEXT 15   /* bytes: 'B', NUL / ':', NUL          ($fe063a -27(a6))              */
#define FUN_D2DESK_TRASH_TEXT 18         /* bytes: the drive's letter, NUL      ($fe059e -24(a6))              */
#define FUN_D2DESK_TRASH_PARAMETER 28    /* long                                ($fe05aa -14(a6))              */
#define FUN_D2DESK_FNODE      34         /* long: i_find's                      ($fe0532 subq.l #8: -8(a6))    */
#define FUN_D2DESK_ISAPP      38         /* ($fe052e subq.l #4: -4(a6))                                        */
#define FUN_D2DESK_FRAME_BYTES 42
#define DRIVE_MARK            ':'        /* ($fe0674 move.b #58,-29(a6))                                       */
#define DISKCOPY_STRING       4          /* the desk's free string "DISKCOPY"   ($fe0698 move.w #4,-(sp))      */
#define DISKCOPY_TAIL_BYTE    251        /* pro_cmd's byte                      ($fe0688 move.w #251,(sp))     */
#define DISKCOPY_UNREAD       1          /* ($fe068c move.w #1,-(sp))                                          */
#define DISKCOPY_ISGRAF       1          /* pro_run's: a GEM program, run over the desk ($fe06ba move.l #$00010001) */
#define DISKCOPY_ISOVER       1
#define D2DESK_COPIED         1          /* ($fe06c4 move.w #1,-44(a6))                                        */
#define D2DESK_NONE           0

#ifndef __ASSEMBLER__
void aes_desk_fun_rebld(uint8_t *image, uint32_t window);                                             /* $fdfdf2 */
int16_t aes_desk_fun_mkdir(uint8_t *image, uint32_t window);                                          /* $fdfebc */
int16_t aes_desk_fun_op(uint8_t *image, int16_t op, uint32_t path);                                   /* $fe003a */
int16_t aes_desk_fun_ddst(uint8_t *image, uint32_t path, uint32_t anode, int16_t object);              /* $fe0140 */
int16_t aes_desk_fun_wdst(uint8_t *image, uint32_t path, uint32_t spec, uint32_t anode, uint32_t fnode); /* $fe01d6 */
void aes_desk_fun_win2win(uint8_t *image, int16_t source, int16_t destination, int16_t object);       /* $fe0258 */
void aes_desk_fun_win2desk(uint8_t *image, int16_t source, int16_t object);                           /* $fe02f2 */
int16_t aes_desk_fun_disk(uint8_t *image, int16_t drive, uint32_t window, uint32_t anode, uint32_t fnode,
                          int16_t object);                                                            /* $fe038c */
void aes_desk_fun_desk2win(uint8_t *image, int16_t window, int16_t object);                           /* $fe0454 */
int16_t aes_desk_fun_d2desk(uint8_t *image, int16_t object);                                          /* $fe0500 */
int16_t aes_desk_fun_drag(uint8_t *image, int16_t source, int16_t destination, int16_t root, int16_t object); /* $fe070a */
#endif
/* ---- end of group G2's wave-2 ---- */

#endif /* TOS102US_DESK_DESKFUN_H */
