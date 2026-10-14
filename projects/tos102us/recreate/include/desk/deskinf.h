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

#ifndef __ASSEMBLER__
#include <stdint.h>

void aes_desk_inf_field(uint8_t *image, uint32_t source, uint32_t text, uint32_t tree, int16_t object, int16_t is_name); /* $fdea5e */
void aes_desk_inf_dttmsz(uint8_t *image, uint32_t tree, uint32_t file, int16_t date_object, int16_t time_object,
                         int16_t size_object, uint32_t size);                                                  /* $fdea9a */
#endif

#endif /* TOS102US_DESK_DESKINF_H */
