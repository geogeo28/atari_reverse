/* deskinf.c — AN INFO DIALOG'S FIELDS (`desk/deskinf.h`): inf_field `$fdea5e` and inf_dttmsz `$fdea9a`. Alcyon C in the
 * ROM, ported over its own order. Neither yields. AND, SINCE BAND 6 W3a's STAGE 1, THE DIALOGS THEY FILL — inf_show,
 * inf_finish, inf_file, inf_folder_dlg, inf_disk, inf_pref and opn_appl — compiled for the target alone (below).
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/deskleaf.h"
#include "aes/fmdo.h"
#include "aes/objects.h"
#include "aes/objtext.h"
#include "aes/strings.h"
#include "desk/deskbind.h"
#include "desk/deskdir.h"
#include "desk/deskfpd.h"
#include "desk/deskfun.h"
#include "desk/deskglobals.h"
#include "desk/deskinf.h"
#include "desk/deskleaf.h"
#include "desk/desktop.h"
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

/* ==== BAND 6 W3a, STAGE 1: THE DIALOGS ===============================================================================
 * COMPILED FOR THE TARGET ALONE (the user's R3, ruling O1): no host twin, no Tier 1 — each held by its target-only rows
 * at the hands' arrivals (`test/test_desk_w3a.py`). Each dialog's texts lie in a frame of the routine's own, laid as
 * the ROM's from its lowest text up (an over-long text runs into the next as there). */
#ifndef RECREATE_HOST_DIFFERENTIAL

/* inf_show's dialog: `tree` centred, its box opened, drawn whole, run from `start` (form_do) and put away. A ROUTINE OF
 * ITS OWN (`noinline`, PD0: band 6 W3a's stage 1) — its four words and the registers that hold them off the stack
 * before the messages that follow are handled, the deepest path of any dialog (hndl_msg's redraws under it). */
__attribute__((noinline)) static void dialog_run(uint8_t *image, uint32_t tree, int16_t start)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(INF_SHOW_RECT_BYTES)];
    uint32_t frame = desk_local_address(frame_local);
    int16_t x, y, w, h;

    aes_desk_form_center(image, tree, frame + INF_SHOW_X, frame + INF_SHOW_Y, frame + INF_SHOW_W, frame + INF_SHOW_H);
    x = (int16_t)be16(image + frame + INF_SHOW_X);
    y = (int16_t)be16(image + frame + INF_SHOW_Y);
    w = (int16_t)be16(image + frame + INF_SHOW_W);
    h = (int16_t)be16(image + frame + INF_SHOW_H);
    (void)aes_desk_form_dial(image, FMD_START, 0, 0, 0, 0, x, y, w, h);
    aes_desk_objc_draw(image, tree, OB_ROOT, INF_SHOW_DEPTH, x, y, w, h);
    (void)aes_desk_form_do(image, tree, start);
    (void)aes_desk_form_dial(image, FMD_FINISH, 0, 0, 0, 0, x, y, w, h);
}

/* inf_show's question after its dialog: evnt_multi for a message with a timer of 0 — what is pending — its six answer
 * pointers all naming ONE discarded word of this frame (the ROM's -12(a6), six times: $fde93a..$fde964). A ROUTINE OF
 * ITS OWN (`noinline`) for the same reason as `dialog_run`: the word and its call are no frame under hndl_msg. What
 * evnt_multi answers. */
__attribute__((noinline)) static uint16_t messages_asked(uint8_t *image)
{
    uint16_t discard_local;
    uint32_t discard = desk_local_address(&discard_local);

    return aes_desk_evnt_multi(image, INF_SHOW_EVENTS, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                               bus_long(image, desk_globals(image) + DESK_A_RMSG), 0, 0,
                               discard, discard, discard, discard, discard, discard);
}

/* $fde8a6 — inf_show: the dialog `tree` run from `start` (`dialog_run`); then, while evnt_multi answers a message
 * (`messages_asked`), the message handled — the redraws putting the dialog away sent the desk. 1. NEVER INLINED
 * (`noinline`): its callers' frames — the dialogs' texts — would stand under hndl_msg with it. */
__attribute__((noinline)) int16_t aes_desk_inf_show(uint8_t *image, uint32_t tree, int16_t start)
{
    uint16_t which;

    dialog_run(image, tree, start);
    do {
        which = messages_asked(image);
        if (which & EV_MU_MESAG)
            (void)aes_hndl_msg(image);
    } while (which & EV_MU_MESAG);
    return INF_SHOW_DONE;
}

/* $fde9a8 — inf_finish: the dialog `tree` shown from its root (inf_show), then its exit object `object`'s state
 * cleared. (The ROM's D0 is that state's address, read by no caller: the C answers nothing.) */
void aes_desk_inf_finish(uint8_t *image, uint32_t tree, int16_t object)
{
    (void)aes_desk_inf_show(image, tree, OB_ROOT);
    set_object_word(image, tree, object, OB_STATE, 0);
}

/* inf_file's new attributes: the file's as it has them, its read-only bit the dialog's Read-Only button. */
static int16_t attributes_chosen(const uint8_t *image, uint32_t tree, uint32_t file)
{
    int16_t attributes = (int8_t)bus_byte(image, file + FNODE_ATTR);

    if (dialog_selected(image, tree, FILE_INFO_READ_ONLY))
        return (int16_t)(attributes | FILE_ATTRIBUTE_READ_ONLY);
    return (int16_t)(attributes & ~FILE_ATTRIBUTE_READ_ONLY);
}

/* $fdeb10 — inf_file: Show Info of the file `file` (an FNODE) of the folder whose search is `path`. The search copied
 * twice (g_tmppth, the destination buffer), each's '*' found; the dialog filled (its 8.3 name, date, time and size,
 * Read-Only / Read-Write by its attributes) and run. Cancelled: 0. Else the hourglass and 1 — unless what follows
 * fails: a NAME EDITED is put in place of each '*' (the old, the new) and the file renamed — an EACCDN answered by the
 * read-only alert (the answer still 1), any other error by d_errmsg, which answers; a renamed file's FNODE takes the
 * new name. Then, where the Read-Only button says other than its attributes, Fattrib set on the new name and, done,
 * kept in the FNODE; the arrow. */
int16_t aes_desk_inf_file(uint8_t *image, uint32_t path, uint32_t file)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(FILE_INFO_FRAME_BYTES)];
    uint32_t frame = desk_local_address(frame_local), desk = desk_globals(image);
    uint32_t tree = bus_long(image, desk + DESK_FILE_INFO_TREE);
    uint32_t old_name = desk + DESK_G_TMPPTH, new_name = desk + DESK_PAR_DESTINATION;
    int16_t at = 0, done, attributes;

    (void)aes_strcpy(image, path, old_name);
    (void)aes_strcpy(image, path, new_name);
    while (bus_byte(image, offset_by(old_name, at)) != INF_WILDCARD)
        at++;
    aes_desk_inf_field(image, file + FNODE_NAME, frame + FILE_INFO_SHOWN, tree, FILE_INFO_NAME, INF_FIELD_A_NAME);
    aes_desk_inf_dttmsz(image, tree, file, FILE_INFO_DATE, FILE_INFO_TIME, FILE_INFO_SIZE, file + FNODE_SIZE);
    attributes = (int8_t)bus_byte(image, file + FNODE_ATTR);
    aes_inf_fldset(image, tree, FILE_INFO_READ_ONLY, attributes, FILE_ATTRIBUTE_READ_ONLY, OB_STATE_SELECTED, 0);
    aes_inf_fldset(image, tree, FILE_INFO_READ_WRITE, attributes, FILE_ATTRIBUTE_READ_ONLY, 0, OB_STATE_SELECTED);
    (void)aes_desk_inf_show(image, tree, OB_ROOT);
    if (!aes_inf_what(image, tree, FILE_INFO_OK, FILE_INFO_CANCEL))
        return 0;
    aes_desk_graf_mouse(image, DESK_CURSOR_HOURGLASS, DESK_NO_FORM);
    done = 1;
    aes_fs_sget(image, tree, FILE_INFO_NAME, frame + FILE_INFO_EDITED);
    aes_unfmt_str(image, frame + FILE_INFO_SHOWN, offset_by(old_name, at));
    aes_unfmt_str(image, frame + FILE_INFO_EDITED, offset_by(new_name, at));
    if (!aes_streq(image, offset_by(old_name, at), offset_by(new_name, at))) {
        (void)aes_dos_rename(image, AES_INF_FILE_RENAME_RETURN, old_name, new_name);
        if ((int16_t)be16(image + AES_DOS_AX) == DOS_AX_EACCDN)
            (void)aes_desk_fun_alert(image, FUN_ALERT_FIRST_BUTTON, FILE_INFO_READ_ONLY_ALERT, FUN_ALERT_NO_PARAMETERS);
        else if ((done = aes_desk_d_errmsg(image)) != 0)
            (void)aes_strcpy(image, offset_by(new_name, at), file + FNODE_NAME);
    }
    attributes = attributes_chosen(image, tree, file);
    if ((uint8_t)attributes != bus_byte(image, file + FNODE_ATTR)) {
        (void)aes_dos_chmod(image, AES_INF_FILE_CHMOD_RETURN, new_name, DOS_CHMOD_SET, attributes);
        if ((done = aes_desk_d_errmsg(image)) != 0)
            set_bus_byte(image, file + FNODE_ATTR, (uint8_t)attributes);
    }
    aes_desk_graf_mouse(image, DESK_CURSOR_ARROW, DESK_NO_FORM);
    return done;
}

/* $fded16 — inf_folder_dlg: Show Info of the folder `folder` (an FNODE) of the folder whose search is `path`. Under the
 * hourglass, its own search built in g_tmppth — the folder's name in place of the '*', then "\*.*" — and counted
 * (inf_folder: the files and folders into the dialog); the arrow. Counted, the dialog's name, date and time and the
 * bytes counted set, and the dialog shown (inf_finish). 1. */
int16_t aes_desk_inf_folder_dlg(uint8_t *image, uint32_t path, uint32_t folder)
{
    uint16_t text_local[FRAME_LOCAL_WORDS(INF_NAME_TEXT_BYTES)];
    uint32_t text = desk_local_address(text_local), desk = desk_globals(image), tree, search, at;
    int16_t counted;

    aes_desk_graf_mouse(image, DESK_CURSOR_HOURGLASS, DESK_NO_FORM);
    tree = bus_long(image, desk + DESK_FOLDER_INFO_TREE);
    search = desk + DESK_G_TMPPTH;
    (void)aes_strcpy(image, path, search);
    for (at = search; bus_byte(image, at) != INF_WILDCARD; at++)
        ;
    at = aes_strcpy(image, folder + FNODE_NAME, at);
    (void)aes_strcpy(image, AES_DESK_INF_ALL_FILES, at - 1);
    counted = aes_desk_inf_folder(image, tree, FOLDER_INFO_FILES, FOLDER_INFO_FOLDERS, search);
    aes_desk_graf_mouse(image, DESK_CURSOR_ARROW, DESK_NO_FORM);
    if (counted) {
        aes_desk_inf_field(image, folder + FNODE_NAME, text, tree, FOLDER_INFO_NAME, INF_FIELD_A_NAME);
        aes_desk_inf_dttmsz(image, tree, folder, FOLDER_INFO_DATE, FOLDER_INFO_TIME, FOLDER_INFO_SIZE, desk + DESK_G_SIZE);
        aes_desk_inf_finish(image, tree, FOLDER_INFO_OK);
    }
    return INF_DIALOG_DONE;
}

/* $fdedf0 — inf_disk: Show Info of the disk whose letter is the low byte of `letter`. Under the hourglass, the root's
 * search ("X:\*.*") built in g_tmppth and counted (inf_folder: the files and folders into the dialog). Counted, its
 * Dfree and label read, the letter, the label (8.3), the bytes counted and the bytes free set; the arrow, and the
 * dialog shown (inf_finish). 1. */
int16_t aes_desk_inf_disk(uint8_t *image, int16_t letter)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(DISK_INFO_FRAME_BYTES)];
    uint32_t frame = desk_local_address(frame_local), desk = desk_globals(image), tree, search;
    int16_t drive;

    aes_desk_graf_mouse(image, DESK_CURSOR_HOURGLASS, DESK_NO_FORM);
    tree = bus_long(image, desk + DESK_DISK_INFO_TREE);
    set_bus_byte(image, frame + DISK_INFO_LETTER_TEXT, (uint8_t)letter);
    set_bus_byte(image, frame + DISK_INFO_LETTER_TEXT + 1, 0);
    search = desk + DESK_G_TMPPTH;
    set_bus_byte(image, search, bus_byte(image, frame + DISK_INFO_LETTER_TEXT));
    (void)aes_strcpy(image, AES_DESK_INF_ROOT_FILES, search + 1);
    if (!aes_desk_inf_folder(image, tree, DISK_INFO_FILES, DISK_INFO_FOLDERS, search)) {
        aes_desk_graf_mouse(image, DESK_CURSOR_ARROW, DESK_NO_FORM);
        return INF_DIALOG_DONE;
    }
    drive = (int16_t)((int8_t)letter - DRIVE_LETTER_BASE);
    (void)aes_dos_space(image, drive, frame + DISK_INFO_TOTAL_BYTES, frame + DISK_INFO_FREE_BYTES);
    (void)aes_dos_label(image, drive, frame + DISK_INFO_LABEL_READ);
    aes_fmt_str(image, frame + DISK_INFO_LABEL_READ, frame + DISK_INFO_LABEL_SHOWN);
    aes_inf_sset(image, tree, DISK_INFO_LETTER, frame + DISK_INFO_LETTER_TEXT);
    aes_inf_sset(image, tree, DISK_INFO_LABEL, frame + DISK_INFO_LABEL_SHOWN);
    aes_desk_inf_field(image, desk + DESK_G_SIZE, frame + DISK_INFO_USED_TEXT, tree, DISK_INFO_USED, INF_FIELD_A_NUMBER);
    aes_desk_inf_field(image, frame + DISK_INFO_FREE_BYTES, frame + DISK_INFO_FREE_TEXT, tree, DISK_INFO_FREE,
                       INF_FIELD_A_NUMBER);
    aes_desk_graf_mouse(image, DESK_CURSOR_ARROW, DESK_NO_FORM);
    aes_desk_inf_finish(image, tree, DISK_INFO_OK);
    return INF_DIALOG_DONE;
}

/* Getrez THROUGH THE ROM's trp14 DOOR as inf_pref's call makes it ($fdefcc): its return site parked in
 * AES_XBIOS_RETURN, then `trap #14` over the one function word (`desk/deskleaf.h`'s door — the shipped glue's own
 * `jsr` of trp14's `.S` would park ITS return there, where the ROM's door parks its caller's). The mode's word. */
static int16_t getrez(uint8_t *image)
{
    static const uint16_t frame[] = {XBIOS_GETREZ_FN};

    desk_xbios_parked(image, AES_INF_PREF_GETREZ_RETURN);
    return (int16_t)desk_xbios_trap(frame, sizeof frame / sizeof frame[0]);
}

/* A Yes / No pair of Set Preferences, `yes` and the object after it, selected by whether `setting` is on. */
static void yes_no_set(uint8_t *image, uint32_t tree, int16_t yes, int16_t setting)
{
    set_object_word(image, tree, yes, OB_STATE, setting ? OB_STATE_SELECTED : 0);
    set_object_word(image, tree, (int16_t)(yes + 1), OB_STATE, setting ? 0 : OB_STATE_SELECTED);
}

/* $fdef12 — inf_pref: Options > Set Preferences. The two confirmations' pairs selected by the desk's preferences; five
 * objects' and the three resolution buttons' states cleared; by Getrez the buttons the screen cannot take disabled
 * (high: the two colour ones; else high) and its own selected. The dialog run. Cancelled: 0. Else the two preferences
 * kept, the resolution chosen kept as its device code ($890c) and handed app_reschange: 1 where it asks a change. */
int16_t aes_desk_inf_pref(uint8_t *image)
{
    uint32_t desk = desk_globals(image), tree = bus_long(image, desk + DESK_PREFS_TREE);
    int16_t index, resolution;

    yes_no_set(image, tree, PREF_DELETES_YES, (int16_t)bus_word(image, desk + DESK_CONFIRM_DELETES));
    yes_no_set(image, tree, PREF_COPIES_YES, (int16_t)bus_word(image, desk + DESK_CONFIRM_COPIES));
    for (index = 0; index < PREF_CLEARED_COUNT; index++)
        set_object_word(image, tree, (int16_t)(index + PREF_CLEARED_FIRST), OB_STATE, 0);
    for (index = 0; index < PREF_RESOLUTIONS; index++)
        set_object_word(image, tree, (int16_t)(index + PREF_RESOLUTION_FIRST), OB_STATE, 0);
    resolution = getrez(image);
    if (resolution == PREF_HIGH_RESOLUTION) {
        set_object_word(image, tree, PREF_RESOLUTION_FIRST, OB_STATE, OB_STATE_DISABLED);
        set_object_word(image, tree, PREF_RESOLUTION_FIRST + 1, OB_STATE, OB_STATE_DISABLED);
    } else {
        set_object_word(image, tree, PREF_RESOLUTION_FIRST + PREF_HIGH_RESOLUTION, OB_STATE, OB_STATE_DISABLED);
    }
    set_object_word(image, tree, (int16_t)(resolution + PREF_RESOLUTION_FIRST), OB_STATE, OB_STATE_SELECTED);
    (void)aes_desk_inf_show(image, tree, OB_ROOT);
    if (!aes_inf_what(image, tree, PREF_OK, PREF_CANCEL))
        return PREF_UNCHANGED;
    set_bus_word(image, desk + DESK_CONFIRM_DELETES, (uint16_t)aes_inf_what(image, tree, PREF_DELETES_YES, PREF_DELETES_NO));
    set_bus_word(image, desk + DESK_CONFIRM_COPIES, (uint16_t)aes_inf_what(image, tree, PREF_COPIES_YES, PREF_COPIES_NO));
    wr16(image + GEM_START_WORD_890C,
         (uint16_t)(aes_inf_gindex(image, tree, PREF_RESOLUTION_FIRST, PREF_RESOLUTIONS) + PREF_DEVICE_OF_INDEX));
    return aes_app_reschange(image, (int16_t)be16(image + GEM_START_WORD_890C)) ? PREF_CHANGED : PREF_UNCHANGED;
}

/* opn_appl's two halves round its dialog, each A ROUTINE OF ITS OWN (`noinline`, PD0: band 6 W3a's stage 1) so that
 * the name's text — the ROM's -14(a6), which no byte of the dialog's run reads (inf_sset and fs_sget copy) — is no
 * frame of opn_appl's under the dialog and the redraws after it, the deepest path of opn_appl's chain (its Cancel).
 * THE FIELDS SET: `name` 8.3, and the parameters `tail`. */
__attribute__((noinline)) static void appl_fields_set(uint8_t *image, uint32_t tree, uint32_t name, uint32_t tail)
{
    uint16_t text_local[FRAME_LOCAL_WORDS(INF_NAME_TEXT_BYTES)];

    aes_desk_inf_field(image, name, desk_local_address(text_local), tree, OPEN_APPL_NAME, INF_FIELD_A_NAME);
    aes_inf_sset(image, tree, OPEN_APPL_TAIL, tail);
}

/* ...AND ITS FIELDS READ BACK (`noinline`, the same reason): the name unformatted into `name_out`, the parameters into
 * `tail_out`. */
__attribute__((noinline)) static void appl_fields_read(uint8_t *image, uint32_t tree, uint32_t name_out, uint32_t tail_out)
{
    uint16_t text_local[FRAME_LOCAL_WORDS(INF_NAME_TEXT_BYTES)];
    uint32_t text = desk_local_address(text_local);

    aes_fs_sget(image, tree, OPEN_APPL_NAME, text);
    aes_unfmt_str(image, text, name_out);
    aes_fs_sget(image, tree, OPEN_APPL_TAIL, tail_out);
}

/* ...AND THE DIALOG RUN: from the parameters' field; cancelled, 0; else the fields read back, 1. A ROUTINE OF ITS OWN
 * (`noinline`) THAT opn_appl LEAVES TO BY A JUMP (a sibling call: opn_appl's frame, and the fields' call's arguments
 * left on its stack, popped first) — so no frame of opn_appl's stands under the dialog. */
__attribute__((noinline)) static int16_t appl_dialog_run(uint8_t *image, uint32_t tree, uint32_t name_out, uint32_t tail_out)
{
    (void)aes_desk_inf_show(image, tree, OPEN_APPL_TAIL);
    if (!aes_inf_what(image, tree, OPEN_APPL_OK, OPEN_APPL_CANCEL))
        return OPEN_APPL_CANCELLED;
    appl_fields_read(image, tree, name_out, tail_out);
    return OPEN_APPL_DONE;
}

/* $fdf082 — opn_appl: the OPEN APPLICATION dialog, the program's name `name` (8.3) and the parameters `tail` set, run
 * from the parameters' field (`appl_dialog_run`). Cancelled: 0. Else the name read back unformatted into `name_out`
 * and the parameters into `tail_out`: 1. */
int16_t aes_desk_opn_appl(uint8_t *image, uint32_t name, uint32_t tail, uint32_t name_out, uint32_t tail_out)
{
    uint32_t tree = bus_long(image, desk_globals(image) + DESK_OPEN_APPL_TREE);

    appl_fields_set(image, tree, name, tail);
    return appl_dialog_run(image, tree, name_out, tail_out);
}
#endif
