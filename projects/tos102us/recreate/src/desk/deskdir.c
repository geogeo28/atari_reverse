/* deskdir.c — THE COPY ENGINE'S HELPERS (`desk/deskdir.h`): the dialogs' drawing, the path editors, the DOS verdict and
 * the delete, and the check that a folder is not copied into itself — fourteen routines of `$fdcf04..$fdd917`. Alcyon C
 * in the ROM, ported over its own order.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/fmdo.h"
#include "aes/gemdosif.h"
#include "aes/objdraw.h"
#include "aes/objects.h"
#include "aes/strings.h"
#include "desk/deskbind.h"
#include "desk/deskdir.h"
#include "desk/deskfpd.h"
#include "desk/deskfun.h"
#include "desk/deskleaf.h"

_Static_assert(DIAL_RECT_BYTES == HOST_SLOT_AES_DESK_DIR_RECT_BYTES, "the dialogs' rectangle and its host slot");
_Static_assert(GRECT_BYTES == HOST_SLOT_AES_DESK_DIR_RECT_BYTES, "draw_fld's GRECT and its host slot");

/* ---- the dialogs ------------------------------------------------------------------------------------------------ */

/* form_center's rectangle of `tree`, answered into the rectangle's slot `rect` (the ROM's four locals). */
static inline void centred(uint8_t *image, uint32_t tree, uint32_t rect)
{
    aes_desk_form_center(image, tree, rect + DIAL_X, rect + DIAL_Y, rect + DIAL_W, rect + DIAL_H);
}

/* A word of that rectangle, as the caller pushes it on to the next binding. */
static inline int16_t dial_word(const uint8_t *image, uint32_t rect, uint32_t field)
{
    return (int16_t)be16(image + rect + field);
}

/* The whole tree drawn over the rectangle. */
static inline void drawn(uint8_t *image, uint32_t tree, uint32_t rect)
{
    aes_desk_objc_draw(image, tree, OB_ROOT, DIAL_DEPTH, dial_word(image, rect, DIAL_X), dial_word(image, rect, DIAL_Y),
                       dial_word(image, rect, DIAL_W), dial_word(image, rect, DIAL_H));
}

/* form_dial of `type` over the rectangle, the little one all zeros (`clr.l / clr.l`): its answer. */
static inline uint16_t dialled(uint8_t *image, int16_t type, uint32_t rect)
{
    return aes_desk_form_dial(image, type, 0, 0, 0, 0, dial_word(image, rect, DIAL_X), dial_word(image, rect, DIAL_Y),
                              dial_word(image, rect, DIAL_W), dial_word(image, rect, DIAL_H));
}

/* $fdcf04 — draw_dial: the dialog `tree` drawn again where form_center puts it. The rectangle is held across both
 * bindings' yields. */
void aes_desk_draw_dial(uint8_t *image, uint32_t tree)
{
    uint16_t rect_local[FRAME_LOCAL_WORDS(DIAL_RECT_BYTES)];
    uint32_t rect = host_slot_claim(AES_DESK_DIR_RECT, rect_local);

    centred(image, tree, rect);
    drawn(image, tree, rect);
    host_slot_release(AES_DESK_DIR_RECT);
}

/* $fdcfa8 — hide_dial: the dialog `tree` taken down — form_dial(FINISH) over where form_center puts it: the screen
 * under it redrawn. Its answer is form_dial's. */
uint16_t aes_desk_hide_dial(uint8_t *image, uint32_t tree)
{
    uint16_t rect_local[FRAME_LOCAL_WORDS(DIAL_RECT_BYTES)];
    uint32_t rect = host_slot_claim(AES_DESK_DIR_RECT, rect_local);
    uint16_t done;

    centred(image, tree, rect);
    done = dialled(image, FMD_FINISH, rect);
    host_slot_release(AES_DESK_DIR_RECT);
    return done;
}

/* $fdcfea — show_dial: the dialog `tree` put up — form_dial(START), then drawn whole. */
void aes_desk_show_dial(uint8_t *image, uint32_t tree)
{
    uint16_t rect_local[FRAME_LOCAL_WORDS(DIAL_RECT_BYTES)];
    uint32_t rect = host_slot_claim(AES_DESK_DIR_RECT, rect_local);

    centred(image, tree, rect);
    (void)dialled(image, FMD_START, rect);
    drawn(image, tree, rect);
    host_slot_release(AES_DESK_DIR_RECT);
}

/* $fdcf48 — do_namecon: THE NAME-CONFLICT DIALOG — put up the first time (and marked up), drawn again after — run;
 * then, where the copy dialog is up, its item 4 drawn SELECTED in it and made normal again unseen. Every tree is read
 * again from the globals where the ROM reads it. */
void aes_desk_do_namecon(uint8_t *image)
{
    uint32_t desk = desk_globals(image);

    if (bus_word(image, desk + DESK_NAMECON_UP)) {
        aes_desk_draw_dial(image, bus_long(image, desk + DESK_NAMECON_TREE));
    } else {
        aes_desk_show_dial(image, bus_long(image, desk + DESK_NAMECON_TREE));
        set_bus_word(image, desk + DESK_NAMECON_UP, 1);
    }
    (void)aes_desk_form_do(image, bus_long(image, desk + DESK_NAMECON_TREE), OB_ROOT);
    if (bus_word(image, desk + DESK_COPY_DIALOG_UP)) {
        aes_ob_change(image, bus_long(image, desk + DESK_COPY_DIALOG_TREE), COPY_DIALOG_ITEM, OB_STATE_SELECTED,
                      COPY_DIALOG_NO_REDRAW);
        aes_desk_draw_dial(image, bus_long(image, desk + DESK_COPY_DIALOG_TREE));
        aes_ob_change(image, bus_long(image, desk + DESK_COPY_DIALOG_TREE), COPY_DIALOG_ITEM, 0, COPY_DIALOG_NO_REDRAW);
    }
}

/* $fdd04c — draw_fld: object `object` of `tree` drawn alone — its rectangle copied out of the object (wcopy of its
 * four words), moved to where ob_offset puts it on the screen. */
void aes_desk_draw_fld(uint8_t *image, uint32_t tree, int16_t object)
{
    uint16_t rect_local[GRECT_WORDS];
    uint32_t rect = host_slot_claim(AES_DESK_DIR_RECT, rect_local);

    aes_wcopy(image, rect, object_address(tree, object, OB_X), GRECT_WORDS);
    (void)aes_desk_objc_offset(image, tree, object, rect + GRECT_X, rect + GRECT_Y);
    aes_desk_objc_draw(image, tree, object, DRAW_FLD_DEPTH, (int16_t)be16(image + rect + GRECT_X),
                       (int16_t)be16(image + rect + GRECT_Y), (int16_t)be16(image + rect + GRECT_W),
                       (int16_t)be16(image + rect + GRECT_H));
    host_slot_release(AES_DESK_DIR_RECT);
}

/* ---- the path editors -------------------------------------------------------------------------------------------- */

/* Where the path's "*.*" begins. */
static inline uint32_t wildcard_of(const uint8_t *image, uint32_t path)
{
    while (bus_byte(image, path) != PATH_WILDCARD)
        path++;
    return path;
}

/* Its end, then back to the last separator. */
static inline uint32_t last_separator(const uint8_t *image, uint32_t path)
{
    while (bus_byte(image, path))
        path++;
    while (bus_byte(image, path) != PATH_SEPARATOR)
        path--;
    return path;
}

/* $fdd0a4 — add_path: the folder `name` in place of the path's "*.*", and "\*.*" after it. strcat's answer. */
uint32_t aes_desk_add_path(uint8_t *image, uint32_t path, uint32_t name)
{
    uint32_t at = wildcard_of(image, path);

    (void)aes_strcpy(image, name, at);
    return aes_strcat(image, AES_DESK_ADD_PATH_TAIL, at);
}

/* $fdd0d2 — sub_path: the path's last folder dropped — from its separator before the last, "\*.*". */
uint32_t aes_desk_sub_path(uint8_t *image, uint32_t path)
{
    uint32_t at = last_separator(image, path) - 1;

    while (bus_byte(image, at) != PATH_SEPARATOR)
        at--;
    return aes_strcpy(image, AES_DESK_SUB_PATH_TAIL, at);
}

/* $fdd10a — add_fname: the file `name` in place of the path's "*.*". */
uint32_t aes_desk_add_fname(uint8_t *image, uint32_t path, uint32_t name)
{
    return aes_strcpy(image, name, wildcard_of(image, path));
}

/* $fdd12c — del_fname: "\*.*" in place of the path's last name. */
uint32_t aes_desk_del_fname(uint8_t *image, uint32_t path)
{
    return aes_strcpy(image, AES_DESK_DEL_FNAME_TAIL, last_separator(image, path));
}

/* $fdd158 — get_fname: the path's last name, copied into the desk's ml_ftmp and from there into `text` in the 8.3
 * form a dialog's field takes (fmt_str). */
void aes_desk_get_fname(uint8_t *image, uint32_t path, uint32_t text)
{
    uint32_t desk = desk_globals(image);

    (void)aes_strcpy(image, last_separator(image, path) + 1, desk + DESK_FNAME_TEXT);
    aes_fmt_str(image, desk + DESK_FNAME_TEXT, text);
}

/* ---- the DOS verdict, and the delete -------------------------------------------------------------------------------- */

/* $fdd1a0 — d_errmsg: the DOS glue's last verdict — done, 1; failed, 0, and where its answer is -32 or less the alert
 * of that GEMDOS error shown (form_error of ~answer - 30: EACCDN's -36 is 5). */
int16_t aes_desk_d_errmsg(uint8_t *image)
{
    uint16_t answer;

    if (!aes_dos_failed(image))
        return D_ERRMSG_DONE;
    answer = be16(image + AES_DOS_AX);
    if ((int16_t)answer <= D_ERRMSG_LEAST_ALERTED)
        (void)aes_desk_form_error(image, (int16_t)(uint16_t)((uint16_t)~answer - D_ERRMSG_CODE_BIAS));
    return D_ERRMSG_FAILED;
}

/* $fdd1ce — d_dofdel: the file `name` deleted (dos_delete, its caller's return the ROM's own Line-F site), then
 * d_errmsg's verdict. */
int16_t aes_desk_d_dofdel(uint8_t *image, uint32_t name)
{
    (void)aes_dos_delete(image, AES_DESK_D_DOFDEL_DELETE_RETURN, name);
    return aes_desk_d_errmsg(image);
}

/* ---- par_chk: a folder copied into itself -------------------------------------------------------------------------- */

/* $fdd762 — path_part: THE PATH'S NEXT FOLDER NAME, cut off in place. From `cursor` past the next separator (or the
 * NUL) — the name it begins — to the separator after it, which is made a NUL; `path` the buffer the path is in. The
 * ROM walks `path` up to the cursor a byte at a time before it looks (a loop whose reads go nowhere: `move.b (a4)+,d0`
 * until the two addresses are one), which is the cursor itself; it would run round the address space for a buffer
 * above its cursor, which no caller hands. The name's start is the answer. */
uint32_t aes_desk_path_part(uint8_t *image, uint32_t cursor, uint32_t path)
{
    uint32_t end;

    (void)path;
    while (bus_byte(image, cursor) != PATH_SEPARATOR && bus_byte(image, cursor))
        cursor++;
    cursor++;
    end = cursor;
    while (bus_byte(image, end) != PATH_SEPARATOR && bus_byte(image, end))
        end++;
    set_bus_byte(image, end, STRING_NUL);
    return cursor;
}

/* The LAST of the files `files` that is shown by an object, SELECTED, and a folder by its attributes exactly (not a
 * folder with another attribute bit too): FNODE_NONE where there is none. */
static uint32_t last_selected_folder(const uint8_t *image, uint32_t desk, uint32_t files)
{
    uint32_t file, found = FNODE_NONE;

    for (file = files; file != FNODE_NONE; file = bus_long(image, file + FNODE_NEXT)) {
        uint16_t object = bus_word(image, file + FNODE_OBID);

        if (object == FNODE_NO_OBJECT)
            continue;
        if (!(bus_byte(image, object_address(desk + DESK_G_SCREEN_OBJECTS, (int16_t)object, OB_STATE + OB_WORD_LOW_BYTE))
              & OB_STATE_SELECTED))
            continue;
        if (bus_byte(image, file + FNODE_ATTR) == FNODE_ATTR_SUBDIR)
            found = file;
    }
    return found;
}

/* $fdd7a6 — par_chk: MAY THE SELECTED FILES OF `source` BE COPIED INTO `destination`? Not where a folder among them
 * (the last such) would go into itself: the two paths — the source's with the folder's name in place of its "*.*" —
 * are walked a folder name at a time (path_part over copies in the desk's two path buffers, made again on every turn:
 * each turn's cut is undone by the next copy), and where the last pair compared before either path ran out is the same
 * name, the alert is shown and the answer is 0. Paths of two drives, or no folder selected: 1. */
int16_t aes_desk_par_chk(uint8_t *image, uint32_t source, uint32_t files, uint32_t destination)
{
    uint32_t desk = desk_globals(image);
    uint32_t source_copy = desk + DESK_G_TMPPTH, destination_copy = desk + DESK_PAR_DESTINATION;
    uint32_t source_part = source_copy, destination_part = destination_copy, folder;
    int16_t inside = 0;

    if (bus_byte(image, source) != bus_byte(image, destination))
        return PAR_CHK_ALLOWED;
    folder = last_selected_folder(image, desk, files);
    if (folder == FNODE_NONE)
        return PAR_CHK_ALLOWED;
    for (;;) {
        (void)aes_strcpy(image, source, source_copy);
        set_bus_byte(image, offset_by(source_copy, aes_strlen(image, source_copy)) - WILDCARD_TAIL_BYTES, STRING_NUL);
        (void)aes_strcat(image, folder + FNODE_NAME, source_copy);
        (void)aes_strcat(image, AES_DESK_PAR_CHK_TAIL, source_copy);
        (void)aes_strcpy(image, destination, destination_copy);
        source_part = aes_desk_path_part(image, source_part, source_copy);
        destination_part = aes_desk_path_part(image, destination_part, destination_copy);
        if (aes_streq(image, source_part, AES_DESK_PAR_CHK_END_SOURCE)
            || aes_streq(image, destination_part, AES_DESK_PAR_CHK_END_DESTINATION))
            break;
        inside = aes_streq(image, destination_part, source_part) ? 1 : 0;
    }
    if (!inside)
        return PAR_CHK_ALLOWED;
    (void)aes_desk_fun_alert(image, PAR_CHK_ALERT_DEFAULT, PAR_CHK_ALERT_STRING, PAR_CHK_ALERT_NO_PARAMETERS);
    return PAR_CHK_REFUSED;
}
