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

#ifndef __ASSEMBLER__
#include <stdint.h>

void aes_desk_inf_field(uint8_t *image, uint32_t source, uint32_t text, uint32_t tree, int16_t object, int16_t is_name); /* $fdea5e */
void aes_desk_inf_dttmsz(uint8_t *image, uint32_t tree, uint32_t file, int16_t date_object, int16_t time_object,
                         int16_t size_object, uint32_t size);                                                  /* $fdea9a */
int16_t aes_desk_inf_folder(uint8_t *image, uint32_t tree, int16_t files_object, int16_t folders_object, uint32_t path); /* $fde9ce */
#endif

#endif /* TOS102US_DESK_DESKINF_H */
