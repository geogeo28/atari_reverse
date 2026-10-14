/* deskinf.c — AN INFO DIALOG'S FIELDS (`desk/deskinf.h`): inf_field `$fdea5e` and inf_dttmsz `$fdea9a`. Alcyon C in the
 * ROM, ported over its own order. Neither yields.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/objtext.h"
#include "aes/strings.h"
#include "desk/deskfpd.h"
#include "desk/deskinf.h"
#include "desk/deskusr.h"

_Static_assert(DTTMSZ_FRAME_BYTES == HOST_SLOT_AES_DESK_INF_DTTMSZ_FRAME_BYTES, "inf_dttmsz's frame and its host slot");

/* $fdea5e — inf_field: object `object` of `tree` set to `text`, made first of `source` — a NAME in 8.3 form
 * (fmt_str) where `is_name`, else the decimal of the longword `source` points at (merge_str's "%L"). */
void aes_desk_inf_field(uint8_t *image, uint32_t source, uint32_t text, uint32_t tree, int16_t object, int16_t is_name)
{
    if (is_name != INF_FIELD_A_NUMBER)
        aes_fmt_str(image, source, text);
    else
        aes_merge_str(image, text, AES_DESK_INF_SIZE_TEMPLATE, source);
    aes_inf_sset(image, tree, object, text);
}

/* $fdea9a — inf_dttmsz: the file `file`'s date, time — read off its FNODE — and the size at `size` set into the three
 * objects of `tree`, each through a text of the routine's own frame (a host slot off target). */
void aes_desk_inf_dttmsz(uint8_t *image, uint32_t tree, uint32_t file, int16_t date_object, int16_t time_object,
                         int16_t size_object, uint32_t size)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(DTTMSZ_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_INF_DTTMSZ_FRAME, frame_local);

    aes_desk_fmt_date(image, (int16_t)bus_word(image, file + FNODE_DATE), frame + DTTMSZ_DATE_TEXT);
    aes_inf_sset(image, tree, date_object, frame + DTTMSZ_DATE_TEXT);
    (void)aes_desk_fmt_time(image, (int16_t)bus_word(image, file + FNODE_TIME), frame + DTTMSZ_TIME_TEXT);
    aes_inf_sset(image, tree, time_object, frame + DTTMSZ_TIME_TEXT);
    aes_desk_inf_field(image, size, frame + DTTMSZ_SIZE_TEXT, tree, size_object, INF_FIELD_A_NUMBER);
    host_slot_release(AES_DESK_INF_DTTMSZ_FRAME);
}
