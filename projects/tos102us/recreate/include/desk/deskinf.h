/* desk/deskinf.h — AN INFO DIALOG'S FIELDS, unit F (`src/desk/deskinf.c`): inf_field `$fdea5e` (a name or a size into
 * one field) and inf_dttmsz `$fdea9a` (a file's date, time and size into three) — band 6 wave 1b, group G4.
 *
 * NAMES: inf_dttmsz is the published GEM desktop's (DESKINF), read from its body; inf_field is this file's own (`# ctx`
 * in the hand-back: the published desktop spells it inside its callers).
 *
 * NEITHER YIELDS, AND NEITHER ANSWERS: each ends on inf_sset, whose leftover D0 the ROM leaves its caller — counted, and
 * read by no caller (`test/test_desk_inf.py`).
 */
#ifndef TOS102US_DESK_DESKINF_H
#define TOS102US_DESK_DESKINF_H

#define AES_DESK_INF_SIZE_TEMPLATE 0xfef5c6 /* "%L": a size in decimal          ($fdea7a move.l #$fef5c6,-(sp)) */
/* inf_field's last argument: what its source is */
#define INF_FIELD_A_NUMBER    0          /* a long's address: merged as "%L"    ($fdea66 beq)                   */
#define INF_FIELD_A_NAME      1          /* a name, formatted 8.3               ($fdeb5a move.w #1,(sp))        */

/* inf_dttmsz's own frame, from -26(a6) (a slot off target, `host_slot.h`): the three texts it hands inf_sset */
#define DTTMSZ_DATE_TEXT      0          /* bytes: fmt_date's "mmddyy"          ($fdeaac -26(a6))               */
#define DTTMSZ_TIME_TEXT      8          /* bytes: fmt_time's "hhmmam"          ($fdead0 -18(a6))               */
#define DTTMSZ_SIZE_TEXT      16         /* bytes: inf_field's "%L"             ($fdeafe -10(a6))               */
#define DTTMSZ_FRAME_BYTES    26

/* ==== BAND 6 WAVE 2, group G1: inf_folder `$fde9ce` (GEM's DESKINF name, read from its body) ======================
 * Show Info's count of a folder: the tallies cleared, d_doop's count walk (no tree), the folder itself taken off the
 * folders, the two counts set into the dialog. Its frame (`link #-16`) is handed on whole — the two texts to
 * inf_field, the count word to d_doop as BOTH its counts (never written: no tree) — so it is one host slot off
 * target, laid as the ROM's: */
#define INF_FOLDER_FOLDERS_TEXT 0        /* bytes: the folders' "%L"              ($fdea44 addi.l #-16,(sp))     */
#define INF_FOLDER_FILES_TEXT 6          /* bytes: the files' "%L"                ($fdea22 addi.l #-10,(sp))     */
#define INF_FOLDER_COUNT      14         /* word: d_doop's two count pointers     ($fde9e8 subq.l #2,(sp))       */
#define INF_FOLDER_FRAME_BYTES 16
#define INF_FOLDER_FAILED     0          /* the walk failed                       ($fdea0e clr.w d0)             */
#define INF_FOLDER_COUNTED    1          /*                                       ($fdea5a moveq #1,d0)          */
#define INF_FOLDER_NO_TREE    0          /* d_doop's tree: none, so nothing drawn ($fde9f8 clr.l -(sp))          */

/* ==== BAND 6 W3a: THE CYCLE'S ONE BACK-EDGE, DECLARED (the orchestrator's split S2, rulings U3 / O4) ===================
 * inf_show `$fde8a6` handles the messages still pending after its dialog by calling hndl_msg `$fe2344` — the one call
 * of the cycle that points UP. Until hndl_msg flips (S2's stage 3) inf_show's C makes that call THROUGH THE TABLE, by
 * the ROM's own call word: a declared C -> ROM call of the desk door's kind, retired at stage 3 (`test/aes_desk_w3a.py`'s
 * CALLS_THROUGH_THE_TABLE, red by name once hndl_msg is flipped). */
#define INF_SHOW_HNDL_MSG_CALL_WORD 0xf558 /* hndl_msg's Line-F call word: inf_show's own ($fde99a)           */

/* ==== BAND 6 W3a, STAGE 1: THE DIALOGS — inf_show, inf_finish, inf_file, inf_folder_dlg, inf_disk, inf_pref, opn_appl
 * (`src/desk/deskinf.c`), COMPILED FOR THE TARGET ALONE (the user's R3, ruling O1: no host twin) ===================== */
/* inf_show: a dialog drawn whole, run, and put away; then the desk's messages handled while one is pending */
#define INF_SHOW_DEPTH        8          /* objc_draw's depth: MAX_DEPTH        ($fde8fc move.w #8,-(sp))       */
#define INF_SHOW_EVENTS       (EV_MU_MESAG | EV_MU_TIMER) /* evnt_multi's      ($fde982 move.w #48,-(sp))       */
#define INF_SHOW_DONE         1          /* ($fde9a4 moveq #1,d0)                                               */
/* ...form_center's four answers (a target local of the dialog's run; the ROM's -2..-8(a6)); evnt_multi's six answer
 * pointers all name one discarded word ($fde93a..$fde964: -12(a6), six times) */
#define INF_SHOW_X            0          /* ($fde8c0 -2(a6): form_center's x, its first answer)                 */
#define INF_SHOW_Y            2
#define INF_SHOW_W            4
#define INF_SHOW_H            6
#define INF_SHOW_RECT_BYTES   8
/* inf_folder_dlg's and inf_disk's answer: done, whatever the count said */
#define INF_DIALOG_DONE       1          /* ($fdedec, $fdef0e moveq #1,d0)                                      */
/* The 8.3 text an info dialog formats a name into (inf_field's), and the text form_do edited it to (fs_sget's) */
#define INF_NAME_TEXT_BYTES   14         /* -14(a6) up to the frame's top        ($fdeb66 addi.l #-14,(sp))     */
/* The searches inf_folder_dlg and inf_disk build in g_tmppth for inf_folder's count */
#define AES_DESK_INF_ALL_FILES 0xfef5c9  /* "\*.*", over the folder's name's NUL ($fded6a move.l #$fef5c9)      */
#define AES_DESK_INF_ROOT_FILES 0xfef5ce /* ":\*.*", after the drive's letter   ($fdee24 move.l #$fef5ce)       */
#define INF_WILDCARD          '*'        /* the search's '*' a name goes in at  ($fdeb52 cmpi.b #42)            */

/* inf_file's dialog (the desk's file-info tree) and its frame from -28(a6): the text form_do edits, then the name as
 * inf_field formatted it — the frame's own layout */
#define FILE_INFO_NAME        2          /* ($fdeb5e move.w #2,-(sp))                                           */
#define FILE_INFO_SIZE        3          /* inf_dttmsz's objects ($fdeb84 move.l #$00050003; $fdeb8a #4)        */
#define FILE_INFO_DATE        4
#define FILE_INFO_TIME        5
#define FILE_INFO_READ_WRITE  8          /* ($fdebca move.w #8,-(sp))                                           */
#define FILE_INFO_READ_ONLY   9          /* ($fdebaa move.w #9,-(sp))                                           */
#define FILE_INFO_OK          10         /* ($fdebe4 move.w #10,-(sp))                                          */
#define FILE_INFO_CANCEL      11
#define FILE_INFO_EDITED      0          /* bytes: fs_sget's text              ($fdec00 addi.l #-28,(sp))       */
#define FILE_INFO_SHOWN       14         /* bytes: inf_field's 8.3 text        ($fdeb66 addi.l #-14,(sp))       */
#define FILE_INFO_FRAME_BYTES 28
#define FILE_INFO_READ_ONLY_ALERT 18     /* fun_alert's string where Frename answers EACCDN ($fdec92 #$00010012) */
#define DOS_AX_EACCDN         (-36)      /* ($fdec86 cmpi.w #-36,$c918)                                         */
#define AES_INF_FILE_RENAME_RETURN 0xfdec84 /* dos_rename's parked return: the word after its Line-F call       */
#define AES_INF_FILE_CHMOD_RETURN  0xfdecf8 /* dos_chmod's                                                      */
#define FILE_ATTRIBUTE_READ_ONLY 0x01    /* ($fdecd4 or.w #1,d6; $fdecda and.w #-2,d6)                          */
#define DOS_CHMOD_SET         1          /* ($fdecea move.w #1,-(sp))                                           */

/* inf_folder_dlg's dialog (the desk's folder-info tree) */
#define FOLDER_INFO_NAME      2          /* ($fdeda0 move.w #2,-(sp))                                           */
#define FOLDER_INFO_DATE      3          /* inf_dttmsz's ($fdedce move.w #3; $fdedc8 move.l #$00040007)         */
#define FOLDER_INFO_TIME      4
#define FOLDER_INFO_FOLDERS   5          /* inf_folder's ($fded7c move.l #$00060005)                            */
#define FOLDER_INFO_FILES     6
#define FOLDER_INFO_SIZE      7
#define FOLDER_INFO_OK        8          /* inf_finish's ($fdede0 move.w #8,(sp))                               */

/* inf_disk's dialog (the desk's disk-info tree) and its frame from -60(a6) — the frame's own layout: the label 8.3,
 * the letter, the label as dos_label answers it, the free and the used bytes' texts, Dfree's two longwords */
#define DISK_INFO_LETTER      2          /* ($fdee9a move.w #2,-(sp))                                           */
#define DISK_INFO_LABEL       3
#define DISK_INFO_FOLDERS     4          /* inf_folder's ($fdee36 move.l #$00050004)                            */
#define DISK_INFO_FILES       5
#define DISK_INFO_USED        6          /* ($fdeeb8 move.w #6,-(sp))                                           */
#define DISK_INFO_FREE        7
#define DISK_INFO_OK          8
#define DISK_INFO_LABEL_SHOWN 0          /* bytes: fmt_str's label             ($fdee80 addi.l #-60,(sp))       */
#define DISK_INFO_LETTER_TEXT 12         /* bytes[2]: the letter and its NUL   ($fdee0c -48(a6), -47(a6))       */
#define DISK_INFO_LABEL_READ  14         /* bytes: dos_label's                 ($fdee68 addi.l #-46,(sp))       */
#define DISK_INFO_FREE_TEXT   26         /* bytes                              ($fdeee0 addi.l #-34,(sp))       */
#define DISK_INFO_USED_TEXT   36         /* bytes                              ($fdeec0 addi.l #-24,(sp))       */
#define DISK_INFO_FREE_BYTES  52         /* long: Dfree's free bytes            ($fdee4e -8(a6))                */
#define DISK_INFO_TOTAL_BYTES 56         /* long: ...and its total              ($fdee52 -4(a6))                */
#define DISK_INFO_FRAME_BYTES 60

/* inf_pref's dialog (Options > Set Preferences) */
#define PREF_DELETES_YES      4          /* the confirm-deletes pair            ($fdef48 106 = 4 * 24 + 10)     */
#define PREF_DELETES_NO       5
#define PREF_COPIES_YES       8          /* the confirm-copies pair             ($fdef78 202 = 8 * 24 + 10)     */
#define PREF_COPIES_NO        9
#define PREF_CLEARED_FIRST    12         /* five objects whose states are cleared ($fdef8c addw #12; cmpw #5)    */
#define PREF_CLEARED_COUNT    5
#define PREF_RESOLUTION_FIRST 21         /* the three resolution buttons: low, medium, high ($fdefae addw #21)   */
#define PREF_RESOLUTIONS      3
#define PREF_OK               17         /* ($fdf026 move.w #17,-(sp))                                          */
#define PREF_CANCEL           18
#define PREF_HIGH_RESOLUTION  2          /* Getrez's high: the two colour ones disabled ($fdefd2 cmpiw #2)      */
#define PREF_DEVICE_OF_INDEX  2          /* a resolution button's index to the device code ($fdf066 addq.w #2)  */
#define PREF_CHANGED          1          /* app_reschange said a change is asked ($fdf07a moveq #1,d0)          */
#define PREF_UNCHANGED        0          /* ...or not, or the dialog was cancelled ($fdf07e clr.w d0)           */
#define AES_INF_PREF_GETREZ_RETURN 0xfdefce /* trp14's parked return: the word after its Line-F call            */

/* opn_appl's dialog (the OPEN APPLICATION parameters) and its frame */
#define OPEN_APPL_NAME        2          /* ($fdf0a0 move.w #2,-(sp))                                           */
#define OPEN_APPL_TAIL        3          /* ($fdf0ba move.w #3,-(sp)), and inf_show's start ($fdf0c4)           */
#define OPEN_APPL_OK          4          /* ($fdf0d2 move.w #4,-(sp))                                           */
#define OPEN_APPL_CANCEL      5
#define OPEN_APPL_DONE        1          /* ($fdf110 moveq #1,d0)                                               */
#define OPEN_APPL_CANCELLED   0          /* ($fdf116 clr.w d0)                                                  */

#ifndef __ASSEMBLER__
#include <stdint.h>

void aes_desk_inf_field(uint8_t *image, uint32_t source, uint32_t text, uint32_t tree, int16_t object, int16_t is_name); /* $fdea5e */
void aes_desk_inf_dttmsz(uint8_t *image, uint32_t tree, uint32_t file, int16_t date_object, int16_t time_object,
                         int16_t size_object, uint32_t size);                                                  /* $fdea9a */
int16_t aes_desk_inf_folder(uint8_t *image, uint32_t tree, int16_t files_object, int16_t folders_object, uint32_t path); /* $fde9ce */
#ifndef RECREATE_HOST_DIFFERENTIAL
int16_t aes_desk_inf_show(uint8_t *image, uint32_t tree, int16_t start);                               /* $fde8a6 */
void aes_desk_inf_finish(uint8_t *image, uint32_t tree, int16_t object);                               /* $fde9a8 */
int16_t aes_desk_inf_file(uint8_t *image, uint32_t path, uint32_t file);                               /* $fdeb10 */
int16_t aes_desk_inf_folder_dlg(uint8_t *image, uint32_t path, uint32_t folder);                       /* $fded16 */
int16_t aes_desk_inf_disk(uint8_t *image, int16_t drive);                                              /* $fdedf0 */
int16_t aes_desk_inf_pref(uint8_t *image);                                                             /* $fdef12 */
int16_t aes_desk_opn_appl(uint8_t *image, uint32_t name, uint32_t tail, uint32_t name_out, uint32_t tail_out); /* $fdf082 */

#include "machine.h"
#include "m68k_idioms.h"
#include "aes/objects.h"

/* A frame local's address, handed on as the ROM hands its `-n(a6)`: on the target the C local IS the frame's slot
 * (`host_slot.h`), and a target-only routine has no host slot to claim. */
static inline uint32_t desk_local_address(void *local)
{
    return (uint32_t)(uintptr_t)local;
}

/* Whether a dialog's object is SELECTED, as the ROM asks it: bit 0 of its state's low byte (`btst #0`). */
static inline int dialog_selected(const uint8_t *image, uint32_t tree, int16_t object)
{
    return bus_byte(image, object_address(tree, object, OB_STATE + OB_WORD_LOW_BYTE)) & OB_STATE_SELECTED;
}
#endif
#endif

#endif /* TOS102US_DESK_DESKINF_H */
