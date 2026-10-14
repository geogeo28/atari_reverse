/* deskinf.c — AN INFO DIALOG'S FIELDS (`desk/deskinf.h`): inf_field `$fdea5e` and inf_dttmsz `$fdea9a`. Alcyon C in the
 * ROM, ported over its own order. Neither yields.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/objtext.h"
#include "aes/strings.h"
#include "desk/deskdir.h"
#include "desk/deskfpd.h"
#include "desk/deskglobals.h"
#include "desk/deskinf.h"
#include "desk/deskusr.h"

_Static_assert(DTTMSZ_FRAME_BYTES == HOST_SLOT_AES_DESK_INF_DTTMSZ_FRAME_BYTES, "inf_dttmsz's frame and its host slot");
_Static_assert(INF_FOLDER_FRAME_BYTES == HOST_SLOT_AES_DESK_INF_FOLDER_FRAME_BYTES, "inf_folder's frame and its host slot");

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

/* ==== band 6 wave 2, group G1 ======================================================================================= */

/* $fde9ce — inf_folder: SHOW INFO'S COUNT OF THE FOLDER `path` — the copy engine's tallies cleared, its count walk
 * (d_doop, no tree; its two count pointers both the frame's one word), then the folder itself taken off the folders and
 * the two tallies set into objects `files_object` and `folders_object` of `tree` ("%L"). 1, or 0 where the walk failed
 * (the fields left as they were). */
int16_t aes_desk_inf_folder(uint8_t *image, uint32_t tree, int16_t files_object, int16_t folders_object, uint32_t path)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(INF_FOLDER_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_INF_FOLDER_FRAME, frame_local);
    uint32_t desk = desk_globals(image);
    int16_t counted;

    set_bus_long(image, desk + DESK_G_NFILES, 0);
    set_bus_long(image, desk + DESK_G_NDIRS, 0);
    set_bus_long(image, desk + DESK_G_SIZE, 0);
    counted = aes_desk_d_doop(image, OP_COUNT, INF_FOLDER_NO_TREE, path, path, frame + INF_FOLDER_COUNT,
                              frame + INF_FOLDER_COUNT);
    if (counted) {
        set_bus_long(image, desk + DESK_G_NDIRS, bus_long(image, desk + DESK_G_NDIRS) - 1);
        aes_desk_inf_field(image, desk + DESK_G_NFILES, frame + INF_FOLDER_FILES_TEXT, tree, files_object, INF_FIELD_A_NUMBER);
        aes_desk_inf_field(image, desk + DESK_G_NDIRS, frame + INF_FOLDER_FOLDERS_TEXT, tree, folders_object,
                           INF_FIELD_A_NUMBER);
    }
    host_slot_release(AES_DESK_INF_FOLDER_FRAME);
    return counted ? INF_FOLDER_COUNTED : INF_FOLDER_FAILED;
}
