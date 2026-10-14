/* deskdir.c — THE COPY ENGINE AND ITS HELPERS (`desk/deskdir.h`): the dialogs' drawing, the path editors, the DOS verdict
 * and the delete, and the check that a folder is not copied into itself — fourteen routines of `$fdcf04..$fdd917`
 * (band 6 wave 1b) — and the engine itself, d_dofcopy `$fdd1dc`, d_doop `$fdd454` and dir_op `$fdd918` (band 6 wave 2,
 * group G1). Alcyon C in the ROM, ported over its own order.
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
#include "aes/objtext.h"
#include "aes/gemstart.h"
#include "aes/strings.h"
#include "desk/deskbind.h"
#include "desk/deskdir.h"
#include "desk/deskfpd.h"
#include "desk/deskfun.h"
#include "desk/deskleaf.h"
#include "gemdos/fs.h"
#include "gemdos/gemdos.h"

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

/* Is `file` shown by an object, and that object SELECTED on the screen's tree? */
static int file_selected(const uint8_t *image, uint32_t desk, uint32_t file)
{
    uint16_t object = bus_word(image, file + FNODE_OBID);

    return object != FNODE_NO_OBJECT
           && (bus_byte(image, object_address(desk + DESK_G_SCREEN_OBJECTS, (int16_t)object, OB_STATE + OB_WORD_LOW_BYTE))
               & OB_STATE_SELECTED);
}

/* The LAST of the files `files` that is shown by an object, SELECTED, and a folder by its attributes exactly (not a
 * folder with another attribute bit too): FNODE_NONE where there is none. */
static uint32_t last_selected_folder(const uint8_t *image, uint32_t desk, uint32_t files)
{
    uint32_t file, found = FNODE_NONE;

    for (file = files; file != FNODE_NONE; file = bus_long(image, file + FNODE_NEXT))
        if (file_selected(image, desk, file) && bus_byte(image, file + FNODE_ATTR) == FNODE_ATTR_SUBDIR)
            found = file;
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

/* ==== BAND 6 WAVE 2, group G1: THE COPY ENGINE — d_dofcopy, d_doop, dir_op ========================================== */

/* gem_gemdos_call ($fd9fc6) AS THE ENGINE REACHES IT for Fread and Fwrite: its caller's return site parked in
 * AES_GEMDOS_RETURN, the glue's verdict words cleared, `trap #1` over (function, handle, count, buffer), AES_DOS_AX :=
 * the answer's word, AES_DOS_ERR := 1 for a NEGATIVE LONGWORD alone. gem_gemdos_call is a byte-pinned `.S` that pops
 * its own return address so that GEMDOS reads its caller's frame — no C frame can be handed to it — so its effect is
 * spelt here, over `gemdos/gemdos.h`'s trap. The trap's whole D0 is the answer. */
static uint32_t file_transfer(uint8_t *image, uint32_t return_site, uint16_t function, int16_t handle, uint32_t count,
                              uint32_t buffer)
{
    uint32_t answer;

    set_bus_long(image, AES_GEMDOS_RETURN, return_site);
    set_bus_word(image, AES_DOS_ERR, GEM_DOS_NO_ERROR);
    set_bus_word(image, AES_DOS_AX, GEM_DOS_NO_ERROR);
    answer = gemdos_trap_word_word_long_long(image, function, (uint16_t)handle, count, buffer);
    set_bus_word(image, AES_DOS_AX, (uint16_t)answer);
    if ((int32_t)answer < 0)
        set_bus_word(image, AES_DOS_ERR, GEM_DOS_FAILED);
    return answer;
}

/* Fread of the copy buffer's whole length into it. */
static inline uint32_t buffer_read(uint8_t *image, uint32_t desk, uint32_t return_site, int16_t handle)
{
    return file_transfer(image, return_site, GEMDOS_FREAD_FN, handle, bus_long(image, desk + DESK_G_XLEN),
                         bus_long(image, desk + DESK_G_XBUF));
}

/* THE NAME CONFLICT of d_dofcopy, asked until the destination is free: what is left to do. */
enum copy_next { COPY_CREATE, COPY_RETURN };

/* The destination opened to see whether it is there: not found — create it; another failure — d_errmsg's verdict,
 * the source closed; found — closed, and the dialog asked (the two names shown, form_do): skipped, the same file, or no
 * name typed — the source closed, 1; a name typed — the destination's last name replaced by it, asked again unless the
 * typed name is the source's (then created over: the ROM's loop ends without opening it again). `*verdict` is what
 * d_dofcopy answers where it returns here. */
static enum copy_next name_conflict(uint8_t *image, uint32_t desk, int16_t source_handle, uint32_t source,
                                    uint32_t destination, int16_t *verdict)
{
    int16_t asking;

    do {
        int16_t destination_handle;

        asking = 1;
        destination_handle = (int16_t)aes_dos_open(image, destination, DOS_OPEN_READ);
        if (aes_dos_failed(image)) {
            if (bus_word(image, AES_DOS_AX) == DOS_AX_FILE_NOT_FOUND)
                return COPY_CREATE;
            *verdict = aes_desk_d_errmsg(image);
            (void)aes_dos_close(image, AES_DESK_D_DOFCOPY_CLOSE_FAILED_RETURN, source_handle);
            return COPY_RETURN;
        }
        (void)aes_dos_close(image, AES_DESK_D_DOFCOPY_CLOSE_FOUND_RETURN, destination_handle);
        aes_inf_sset(image, bus_long(image, desk + DESK_NAMECON_TREE), NAMECON_SOURCE, desk + DESK_ML_FSRC);
        aes_inf_sset(image, bus_long(image, desk + DESK_NAMECON_TREE), NAMECON_DESTINATION, desk + DESK_ML_FDST);
        aes_desk_do_namecon(image);
        *verdict = COPY_GOES_ON;
        if (!aes_inf_what(image, bus_long(image, desk + DESK_NAMECON_TREE), NAMECON_OK, NAMECON_SKIP)) {
            (void)aes_dos_close(image, AES_DESK_D_DOFCOPY_CLOSE_SKIPPED_RETURN, source_handle);
            return COPY_RETURN;
        }
        aes_desk_wait(image, DESK_WAIT_BUSY);
        aes_fs_sget(image, bus_long(image, desk + DESK_NAMECON_TREE), NAMECON_DESTINATION, desk + DESK_ML_FDST);
        if (aes_streq(image, desk + DESK_ML_FSRC, desk + DESK_ML_FDST)) {
            if (aes_streq(image, source, destination)) {
                (void)aes_dos_close(image, AES_DESK_D_DOFCOPY_CLOSE_SAME_RETURN, source_handle);
                return COPY_RETURN;
            }
            asking = 0;
        }
        aes_unfmt_str(image, desk + DESK_ML_FDST, desk + DESK_ML_FSTR);
        if (!bus_byte(image, desk + DESK_ML_FSTR)) {
            (void)aes_dos_close(image, AES_DESK_D_DOFCOPY_CLOSE_NO_NAME_RETURN, source_handle);
            return COPY_RETURN;
        }
        (void)aes_desk_del_fname(image, destination);
        (void)aes_desk_add_fname(image, destination, desk + DESK_ML_FSTR);
        (void)aes_strcpy(image, desk + DESK_ML_FDST, desk + DESK_ML_FSRC);
    } while (asking);
    return COPY_CREATE;
}

/* $fdd1dc — d_dofcopy: ONE FILE COPIED, `source` to `destination` — the source read into the copy buffer (closed at
 * once where it fits), the name conflict asked (`name_conflict`), the destination created (its read-only bit off),
 * written a buffer at a time and read again while the source filled the buffer; then its time and date set to
 * `stamp` (its time the high word) and closed. A write short of the read is the disk full: its alert, both closed, the
 * destination deleted, 0. Otherwise d_errmsg's last verdict — a failed open or read answers it AT ONCE, the source
 * left open (the ROM's), and a failed write's verdict is overwritten by the stamp's (the ROM's). */
int16_t aes_desk_d_dofcopy(uint8_t *image, uint32_t source, uint32_t destination, uint32_t stamp, int16_t attributes)
{
    uint32_t desk = desk_globals(image);
    int16_t source_handle, destination_handle, verdict, more_to_read = 0;
    uint32_t read, written;

    source_handle = (int16_t)aes_dos_open(image, source, DOS_OPEN_READ);
    verdict = aes_desk_d_errmsg(image);
    if (!verdict)
        return verdict;
    read = buffer_read(image, desk, AES_DESK_D_DOFCOPY_FREAD_RETURN, source_handle);
    verdict = aes_desk_d_errmsg(image);
    if (!verdict)
        return verdict;
    if (bus_long(image, desk + DESK_G_XLEN) == read)
        more_to_read = 1;
    else
        (void)aes_dos_close(image, AES_DESK_D_DOFCOPY_CLOSE_WHOLE_RETURN, source_handle);
    aes_desk_get_fname(image, source, desk + DESK_ML_FSRC);
    aes_desk_get_fname(image, destination, desk + DESK_ML_FDST);
    if (name_conflict(image, desk, source_handle, source, destination, &verdict) == COPY_RETURN)
        return verdict;
    destination_handle = (int16_t)aes_dos_create(image, AES_DESK_D_DOFCOPY_CREATE_RETURN, destination,
                                                 (int16_t)(attributes & FCREATE_READ_ONLY_DROPPED));
    verdict = aes_desk_d_errmsg(image);
    if (!verdict)
        return verdict;
    do {
        written = file_transfer(image, AES_DESK_D_DOFCOPY_FWRITE_RETURN, GEMDOS_FWRITE_FN, destination_handle, read,
                                bus_long(image, desk + DESK_G_XBUF));
        verdict = aes_desk_d_errmsg(image);
        if (verdict && read != written) {
            (void)aes_desk_fun_alert(image, COPY_SHORT_ALERT_DEFAULT, COPY_SHORT_ALERT_STRING, COPY_SHORT_ALERT_NO_PARAMETERS);
            (void)aes_dos_close(image, AES_DESK_D_DOFCOPY_CLOSE_SHORT_DST_RETURN, destination_handle);
            (void)aes_dos_close(image, AES_DESK_D_DOFCOPY_CLOSE_SHORT_SRC_RETURN, source_handle);
            (void)aes_desk_d_dofdel(image, destination);
            return COPY_STOPPED;
        }
        if (!more_to_read || !verdict)
            break;
        read = buffer_read(image, desk, AES_DESK_D_DOFCOPY_FREAD_AGAIN_RETURN, source_handle);
        verdict = aes_desk_d_errmsg(image);
        if (bus_long(image, desk + DESK_G_XLEN) != read) {
            (void)aes_dos_close(image, AES_DESK_D_DOFCOPY_CLOSE_READ_END_RETURN, source_handle);
            more_to_read = 0;
        }
    } while (verdict);
    (void)aes_dos_setdt(image, destination_handle, stamp);
    verdict = aes_desk_d_errmsg(image);
    (void)aes_dos_close(image, AES_DESK_D_DOFCOPY_CLOSE_DONE_RETURN, destination_handle);
    return verdict;
}

/* d_doop's DTA of folder level `level`: the desk's stack of them, one a level. */
static inline uint32_t level_dta(uint32_t desk, int16_t level)
{
    return table_entry(desk + DESK_G_DTASTK, level, DESK_DTA_BYTES);
}

/* A count of the dialog's down by one and shown again: `count` (the caller's word), merged by `format` into the
 * desk's `text`, set into the field the desk's word `object` names, that field drawn (the word read for each). */
static void counted_down(uint8_t *image, uint32_t desk, uint32_t tree, uint32_t count, uint32_t text, uint32_t format,
                         uint32_t object)
{
    sub_word_in_memory(image, count, 1);
    aes_merge_str(image, desk + text, format, count);
    aes_inf_sset(image, tree, (int16_t)bus_word(image, desk + object), desk + text);
    aes_desk_draw_fld(image, tree, (int16_t)bus_word(image, desk + object));
}

/* d_doop's walk at the end of a folder's search: the folder counted (OP_COUNT), or deleted — its path cut before
 * its "\*.*", Ddelete, the tail put back — (OP_DELETE); the dialog's folders count down; the deepest run of levels
 * kept; up a level — the walk over where the top folder ends. Answers d_doop's verdict, `more` or Ddelete's. */
static int16_t folder_ended(uint8_t *image, uint32_t desk, int16_t op, uint32_t tree, uint32_t source,
                            uint32_t destination, uint32_t folders_count, int16_t *level, int16_t *depth,
                            int16_t *searching, int16_t more)
{
    switch (op) {
    case OP_COUNT:
        set_bus_long(image, desk + DESK_G_NDIRS, bus_long(image, desk + DESK_G_NDIRS) + 1);
        break;
    case OP_DELETE:
        set_bus_byte(image, wildcard_of(image, source) - 1, STRING_NUL);
        (void)aes_dos_rmdir(image, AES_DESK_D_DOOP_RMDIR_RETURN, source);
        more = aes_desk_d_errmsg(image);
        (void)aes_strcat(image, AES_DESK_DOOP_RMDIR_TAIL, source);
        break;
    }
    if (tree)
        counted_down(image, desk, tree, folders_count, DESK_FOLDERS_TEXT, AES_DESK_DOOP_FOLDER_FORMAT, DESK_FOLDERS_OBJECT);
    if (*depth > (int16_t)bus_word(image, AES_DESK_WALK_DEPTH))
        set_bus_word(image, AES_DESK_WALK_DEPTH, (uint16_t)*depth);
    *depth = 1;
    if (--*level < 0) {
        *searching = 0;
        return more;
    }
    (void)aes_desk_sub_path(image, source);
    if (op == OP_COPY)
        (void)aes_desk_sub_path(image, destination);
    (void)aes_dos_sdta(image, AES_DESK_D_DOOP_SDTA_UP_RETURN, level_dta(desk, *level));
    return more;
}

/* ...and at a folder found: entered — not "." or "..", and no deeper than DOOP_LEVELS — its name onto the path (and,
 * copying, the destination's folder made: Dcreate's verdict), a level down, its search begun where nothing failed. */
static int16_t folder_found(uint8_t *image, uint32_t desk, int16_t op, uint32_t source, uint32_t destination,
                            uint32_t dta, int16_t *level, int16_t *depth, int16_t more)
{
    if (bus_byte(image, dta + DTA_NAME) == FOLDER_NAME_DOT || *level >= DOOP_LEVELS)
        return more;
    (void)aes_desk_add_path(image, source, dta + DTA_NAME);
    if (op == OP_COPY) {
        (void)aes_desk_add_fname(image, destination, dta + DTA_NAME);
        (void)aes_dos_mkdir(image, destination);
        more = aes_desk_d_errmsg(image);
        (void)aes_strcat(image, AES_DESK_DOOP_MKDIR_TAIL, destination);
    }
    ++*level;
    ++*depth;
    (void)aes_dos_sdta(image, AES_DESK_D_DOOP_SDTA_DOWN_RETURN, level_dta(desk, *level));
    if (more)
        (void)aes_dos_sfirst(image, source, DESK_SEARCH_ALL);
    return more;
}

/* ...and at a file found: counted (with its bytes), deleted, or copied (d_dofcopy, its DTA's time, date and
 * attributes) — its name onto the path for the two and taken off again; the dialog's files count down. */
static int16_t file_found(uint8_t *image, uint32_t desk, int16_t op, uint32_t tree, uint32_t source,
                          uint32_t destination, uint32_t files_count, uint32_t dta, int16_t more)
{
    if (op != OP_COUNT)
        (void)aes_desk_add_fname(image, source, dta + DTA_NAME);
    switch (op) {
    case OP_COUNT:
        set_bus_long(image, desk + DESK_G_NFILES, bus_long(image, desk + DESK_G_NFILES) + 1);
        set_bus_long(image, desk + DESK_G_SIZE, bus_long(image, desk + DESK_G_SIZE) + bus_long(image, dta + DTA_FILELN));
        break;
    case OP_DELETE:
        more = aes_desk_d_dofdel(image, source);
        break;
    case OP_COPY:
        (void)aes_desk_add_fname(image, destination, dta + DTA_NAME);
        more = aes_desk_d_dofcopy(image, source, destination,
                                  words_long((int16_t)bus_word(image, dta + DTA_TIME), (int16_t)bus_word(image, dta + DTA_DATE)),
                                  (int8_t)bus_byte(image, dta + DTA_FOUND_ATTR));
        (void)aes_desk_del_fname(image, destination);
        break;
    }
    if (op != OP_COUNT)
        (void)aes_desk_del_fname(image, source);
    if (tree)
        counted_down(image, desk, tree, files_count, DESK_FILES_TEXT, AES_DESK_DOOP_FILE_FORMAT, DESK_FILES_OBJECT);
    return more;
}

/* $fdd454 — d_doop: A FOLDER'S TREE WALKED — `source` (a path ending "\*.*") searched a level at a time, each level's
 * search in its own DTA of the desk's stack, and every file counted, deleted or copied to the same place under
 * `destination` (OP_COUNT / OP_DELETE / OP_COPY), every folder entered and, at its end, counted or deleted; `tree` (0:
 * none) the dialog whose two counts (`files_count`, `folders_count`, the caller's words) go down as it goes. The walk
 * stops at the first failure (d_errmsg's 0) — though the search is asked for its next once more (the ROM's) — and at
 * the top folder's end. Its answer: 1, or that 0. */
int16_t aes_desk_d_doop(uint8_t *image, int16_t op, uint32_t tree, uint32_t source, uint32_t destination,
                        uint32_t files_count, uint32_t folders_count)
{
    uint32_t desk = desk_globals(image);
    int16_t level = 0, depth = 1, more = 1, searching = 1;

    set_bus_word(image, AES_DESK_WALK_DEPTH, 1);
    (void)aes_dos_sdta(image, AES_DESK_D_DOOP_SDTA_FIRST_RETURN, level_dta(desk, level));
    (void)aes_dos_sfirst(image, source, DESK_SEARCH_ALL);
    while (searching && more) {
        uint32_t dta = level_dta(desk, level);
        int16_t ended = 0;

        if (aes_dos_failed(image)) {
            uint16_t answer = bus_word(image, AES_DOS_AX);

            if (answer == DOS_AX_NO_MORE_FILES || answer == DOS_AX_FILE_NOT_FOUND) {
                more = folder_ended(image, desk, op, tree, source, destination, folders_count, &level, &depth,
                                    &searching, more);
                ended = 1;
            } else {
                more = aes_desk_d_errmsg(image);
            }
        }
        if (!ended && more) {
            if (bus_byte(image, dta + DTA_FOUND_ATTR) & FNODE_ATTR_SUBDIR)
                more = folder_found(image, desk, op, source, destination, dta, &level, &depth, more);
            else
                more = file_found(image, desk, op, tree, source, destination, files_count, dta, more);
        }
        if (searching)
            (void)aes_dos_snext(image);
    }
    return more;
}

/* dir_op's dialog where Set Preferences asks for it (the word at `confirm`): its tree (the desk's long at `tree_at`),
 * and the four object numbers laid; else none, 0. DESK_COPY_DIALOG_UP keeps the preference either way. */
static uint32_t confirming_dialog(uint8_t *image, uint32_t desk, uint32_t confirm, uint32_t tree_at)
{
    uint16_t asks = bus_word(image, desk + confirm);

    set_bus_word(image, desk + DESK_COPY_DIALOG_UP, asks);
    if (!asks)
        return 0;
    set_bus_word(image, desk + DESK_FILES_OBJECT, COPY_FILES_OBJECT);
    set_bus_word(image, desk + DESK_FOLDERS_OBJECT, COPY_FOLDERS_OBJECT);
    set_bus_word(image, desk + DESK_OK_OBJECT, COPY_OK_OBJECT);
    set_bus_word(image, desk + DESK_CANCEL_OBJECT, COPY_CANCEL_OBJECT);
    return bus_long(image, desk + tree_at);
}

/* ...put up with the two counts (the caller's words, "%W") and run: OK or not (the busy bee where OK). NOT INLINED
 * (with folder_op, below) so dir_op's own prologue saves fewer registers on its short count run — the shape that
 * took the one-file count from 1.184 to 1.139 on the bench blob; it costs 48 B of the copy nest's depth. */
__attribute__((noinline)) static int16_t confirmed(uint8_t *image, uint32_t desk, uint32_t tree, uint32_t files_count, uint32_t folders_count)
{
    int16_t ok;

    aes_merge_str(image, desk + DESK_FILES_TEXT, AES_DESK_DIR_OP_FILES_FORMAT, files_count);
    aes_inf_sset(image, tree, (int16_t)bus_word(image, desk + DESK_FILES_OBJECT), desk + DESK_FILES_TEXT);
    aes_merge_str(image, desk + DESK_FOLDERS_TEXT, AES_DESK_DIR_OP_FOLDERS_FORMAT, folders_count);
    aes_inf_sset(image, tree, (int16_t)bus_word(image, desk + DESK_FOLDERS_OBJECT), desk + DESK_FOLDERS_TEXT);
    set_bus_word(image, desk + DESK_NAMECON_UP, DIALOG_UP);
    aes_desk_show_dial(image, tree);
    (void)aes_desk_form_do(image, tree, FORM_DO_NO_EDIT);
    ok = aes_inf_what(image, tree, (int16_t)bus_word(image, desk + DESK_OK_OBJECT),
                      (int16_t)bus_word(image, desk + DESK_CANCEL_OBJECT));
    if (ok)
        aes_desk_wait(image, DESK_WAIT_BUSY);
    return ok;
}

/* A FOLDER MADE WHERE IT IS NOT THERE — dir_op's destination and fun_mkdir's, one ROM idiom: `folder` searched (in
 * the DTA the caller named) and, found, the DOS glue's verdict MADE UP as a failure of AES_DOS_AX DOS_AX_ACCESS_DENIED
 * (`move.w #1,$98ec / move.w #5,$c918`: $fddb12, $fdffbe); else Dcreate (whose EACCDN reads the same). Answers
 * whether it was found. */
int desk_search_or_mkdir(uint8_t *image, uint32_t folder)
{
    if (aes_dos_sfirst(image, folder, DESK_SEARCH_ALL)) {
        set_bus_word(image, AES_DOS_ERR, GEM_DOS_FAILED);
        set_bus_word(image, AES_DOS_AX, DOS_AX_ACCESS_DENIED);
        return 1;
    }
    (void)aes_dos_mkdir(image, folder);
    return 0;
}

/* dir_op's folder copied, its destination first: the folder made under the destination's path — and while it is
 * there, the name conflict asked (the folder's name shown as the source, an empty destination): skipped, or no name
 * typed, stops the operation; a name typed is made instead. Answers whether the operation goes on. */
static int16_t destination_folder(uint8_t *image, uint32_t desk, uint32_t name, int16_t goes_on)
{
    uint32_t folder = desk + DESK_PAR_DESTINATION;

    (void)aes_desk_add_fname(image, folder, name);
    (void)aes_dos_sdta(image, AES_DESK_DIR_OP_SDTA_RETURN, AES_SH_SCRATCH);
    (void)desk_search_or_mkdir(image, folder);
    while (aes_dos_failed(image) && goes_on) {
        if (bus_word(image, AES_DOS_AX) != DOS_AX_ACCESS_DENIED) {
            goes_on = 0;
            break;
        }
        aes_fmt_str(image, name, desk + DESK_ML_FSRC);
        set_bus_byte(image, desk + DESK_ML_FDST, STRING_NUL);
        aes_inf_sset(image, bus_long(image, desk + DESK_NAMECON_TREE), NAMECON_SOURCE, desk + DESK_ML_FSRC);
        aes_inf_sset(image, bus_long(image, desk + DESK_NAMECON_TREE), NAMECON_DESTINATION, desk + DESK_ML_FDST);
        aes_desk_do_namecon(image);
        goes_on = aes_inf_what(image, bus_long(image, desk + DESK_NAMECON_TREE), NAMECON_OK, NAMECON_SKIP);
        if (!goes_on)
            break;
        aes_desk_wait(image, DESK_WAIT_BUSY);
        aes_fs_sget(image, bus_long(image, desk + DESK_NAMECON_TREE), NAMECON_DESTINATION, desk + DESK_ML_FDST);
        aes_unfmt_str(image, desk + DESK_ML_FDST, desk + DESK_ML_FSTR);
        (void)aes_desk_del_fname(image, folder);
        if (!bus_byte(image, desk + DESK_ML_FSTR)) {
            goes_on = 0;
            break;
        }
        (void)aes_desk_add_fname(image, folder, desk + DESK_ML_FSTR);
        (void)desk_search_or_mkdir(image, folder);
    }
    (void)aes_strcat(image, AES_DESK_DIR_OP_FOLDER_TAIL, folder);
    return goes_on;
}

/* dir_op's selected folder: its path in g_tmppth (and, copying, its destination made), then walked (d_doop) — the
 * deepest walk kept in AES_DESK_OP_DEPTH. Not inlined: `confirmed`'s reason. */
__attribute__((noinline)) static int16_t folder_op(uint8_t *image, uint32_t desk, int16_t op, uint32_t tree, uint32_t file, uint32_t files_count,
                         uint32_t folders_count, int16_t goes_on)
{
    (void)aes_desk_add_path(image, desk + DESK_G_TMPPTH, file + FNODE_NAME);
    if (op == OP_COPY)
        goes_on = destination_folder(image, desk, file + FNODE_NAME, goes_on);
    if (!goes_on)
        return goes_on;
    goes_on = aes_desk_d_doop(image, op, tree, desk + DESK_G_TMPPTH, desk + DESK_PAR_DESTINATION, files_count,
                              folders_count);
    if ((int16_t)bus_word(image, AES_DESK_WALK_DEPTH) > (int16_t)bus_word(image, AES_DESK_OP_DEPTH))
        set_bus_word(image, AES_DESK_OP_DEPTH, bus_word(image, AES_DESK_WALK_DEPTH));
    return goes_on;
}

/* ...and its selected file: counted, deleted or copied as d_doop does a file (from its FNODE's fields); then — where
 * not counting — the last name of the CALLER's `source` path replaced by "\*.*" (not g_tmppth's: the ROM's, harmless
 * on the "*.*" path every caller hands); the dialog's files count down. */
static int16_t file_op(uint8_t *image, uint32_t desk, int16_t op, uint32_t tree, uint32_t source, uint32_t file,
                       uint32_t files_count, int16_t goes_on)
{
    uint32_t path = desk + DESK_G_TMPPTH, copy = desk + DESK_PAR_DESTINATION;

    if (op != OP_COUNT)
        (void)aes_desk_add_fname(image, path, file + FNODE_NAME);
    switch (op) {
    case OP_COUNT:
        set_bus_long(image, desk + DESK_G_NFILES, bus_long(image, desk + DESK_G_NFILES) + 1);
        set_bus_long(image, desk + DESK_G_SIZE, bus_long(image, desk + DESK_G_SIZE) + bus_long(image, file + FNODE_SIZE));
        break;
    case OP_DELETE:
        goes_on = aes_desk_d_dofdel(image, path);
        break;
    case OP_COPY:
        (void)aes_desk_add_fname(image, copy, file + FNODE_NAME);
        goes_on = aes_desk_d_dofcopy(image, path, copy, bus_long(image, file + FNODE_TIME),
                                     (int8_t)bus_byte(image, file + FNODE_ATTR));
        (void)aes_desk_del_fname(image, copy);
        break;
    }
    if (op != OP_COUNT)
        (void)aes_desk_del_fname(image, source);
    if (tree)
        counted_down(image, desk, tree, files_count, DESK_FILES_TEXT, AES_DESK_DIR_OP_FILE_FORMAT, DESK_FILES_OBJECT);
    return goes_on;
}

/* $fdd918 — dir_op: THE COPY / DELETE ENGINE over the SELECTED files of the list `files` in the window of `source`:
 * OP_COUNT zeroes the tallies and hands them back (files and folders as WORDS, their bytes a long, through the three
 * pointers); OP_DELETE and OP_COPY put up their dialog where Set Preferences confirms (OP_COPY Mallocs all free memory
 * but XBUF_KEPT first, and frees it after) — Cancel ends it there. Each selected file goes to `file_op`, each folder
 * to `folder_op`, both paths built afresh in g_tmppth / par_chk's buffer, until one fails. Any dialog the desk put up
 * is taken down over the name-conflict dialog's place (the ROM's). Answers 1. */
int16_t aes_desk_dir_op(uint8_t *image, int16_t op, uint32_t source, uint32_t files, uint32_t destination,
                        uint32_t files_count, uint32_t folders_count, uint32_t size)
{
    uint32_t desk = desk_globals(image), tree = 0, file, next;
    int16_t goes_on = 1;

    set_bus_word(image, desk + DESK_NAMECON_UP, 0);
    set_bus_word(image, AES_DESK_OP_DEPTH, 0);
    switch (op) {
    case OP_COUNT:
        set_bus_long(image, desk + DESK_G_NFILES, 0);
        set_bus_long(image, desk + DESK_G_NDIRS, 0);
        set_bus_long(image, desk + DESK_G_SIZE, 0);
        break;
    case OP_DELETE:
        tree = confirming_dialog(image, desk, DESK_CONFIRM_DELETES, DESK_DELETE_DIALOG_TREE);
        break;
    case OP_COPY:
        set_bus_long(image, desk + DESK_G_XLEN, aes_dos_avail(image));
        set_bus_long(image, desk + DESK_G_XLEN, bus_long(image, desk + DESK_G_XLEN) - XBUF_KEPT);
        set_bus_long(image, desk + DESK_G_XBUF, aes_dos_alloc(image, bus_long(image, desk + DESK_G_XLEN)));
        tree = confirming_dialog(image, desk, DESK_CONFIRM_COPIES, DESK_COPY_DIALOG_TREE);
        break;
    }
    if (!tree || confirmed(image, desk, tree, files_count, folders_count)) {
        for (file = files; file && goes_on; file = next) {
            next = bus_long(image, file + FNODE_NEXT);
            if (!file_selected(image, desk, file))
                continue;
            (void)aes_strcpy(image, source, desk + DESK_G_TMPPTH);
            if (op == OP_COPY)
                (void)aes_strcpy(image, destination, desk + DESK_PAR_DESTINATION);
            if (bus_byte(image, file + FNODE_ATTR) == FNODE_ATTR_SUBDIR)
                goes_on = folder_op(image, desk, op, tree, file, files_count, folders_count, goes_on);
            else
                goes_on = file_op(image, desk, op, tree, source, file, files_count, goes_on);
        }
    }
    switch (op) {
    case OP_COUNT:
        set_bus_word(image, files_count, (uint16_t)bus_long(image, desk + DESK_G_NFILES));
        set_bus_word(image, folders_count, (uint16_t)bus_long(image, desk + DESK_G_NDIRS));
        set_bus_long(image, size, bus_long(image, desk + DESK_G_SIZE));
        break;
    case OP_COPY:
        (void)aes_dos_free(image, AES_DESK_DIR_OP_FREE_RETURN, bus_long(image, desk + DESK_G_XBUF));
        break;
    }
    if (bus_word(image, desk + DESK_NAMECON_UP))
        (void)aes_desk_hide_dial(image, bus_long(image, desk + DESK_NAMECON_TREE));
    return COPY_GOES_ON;
}
