/* deskfun.c — THE DESK'S ALERT AND ITS MESSAGE TO ITSELF (`desk/deskfun.h`): fun_alert `$fdfd58` and fun_msg `$fdfda6`.
 * Alcyon C in the ROM, ported over its own order; each ends on a binding of unit D and answers that binding's word.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/deskmem.h"
#include "aes/resource.h"
#include "aes/strings.h"
#include "desk/deskbind.h"
#include "desk/deskfun.h"
/* ---- band 6 wave 2, group G2 (unit H): the drivers' callees ---- */
#include "aes/fmdo.h"
#include "aes/gemdosif.h"
#include "aes/gemstart.h"
#include "aes/objects.h"
#include "aes/objtext.h"
#include "aes/wmlib.h"
#include "aes/wmupdate.h"
#include "desk/deskact.h"
#include "desk/deskdir.h"
#include "desk/deskfpd.h"
#include "desk/deskleaf.h"
#include "desk/desktop.h"
#include "desk/deskview.h"
#include "desk/deskwin.h"
/* ---- end of group G2's wave-2 ---- */

_Static_assert(FUN_MSG_BYTES == HOST_SLOT_AES_DESK_FUN_MSG_BYTES, "fun_msg's message and its host slot");

/* $fdfd58 — fun_alert: alert string `string` of the desk's resource, MERGED with `parameters` where the caller hands
 * any (into the desk's 512-byte block, whose address is taken before anything else), shown with `default_button`.
 * Its answer is form_alert's: the button. */
int16_t aes_desk_fun_alert(uint8_t *image, int16_t default_button, int16_t string, uint32_t parameters)
{
    uint32_t merged = be32(image + AES_DESK_BLOCK_512);
    uint32_t desk = be32(image + AES_DESK_GLOBALS);

    (void)aes_desk_rsrc_gaddr(image, R_STRING, string, desk + DESK_G_ALERT);
    if (parameters) {
        aes_merge_str(image, merged, bus_long(image, desk + DESK_G_ALERT), parameters);
        set_bus_long(image, desk + DESK_G_ALERT, merged);
    }
    return aes_desk_form_alert(image, default_button, bus_long(image, desk + DESK_G_ALERT));
}

/* $fdfda6 — fun_msg: the message `type` from the desk to itself — its five words after the third the caller's last
 * five — written to its own pipe. The caller's second word is read by nothing (its one kind of caller pushes gl_apid
 * there, `$fe3746`). The message lies in the routine's own frame, handed to appl_write by address: a host slot off
 * target, HELD ACROSS THE BINDING'S YIELD (the dispatcher runs before appl_write's answer comes back). */
uint16_t aes_desk_fun_msg(uint8_t *image, int16_t type, int16_t unread, int16_t word3, int16_t word4, int16_t word5,
                          int16_t word6, int16_t word7)
{
    uint16_t message_local[FRAME_LOCAL_WORDS(FUN_MSG_BYTES)];
    uint32_t message = host_slot_claim(AES_DESK_FUN_MSG, message_local);
    uint16_t written;

    (void)unread;
    wr16(image + message + FUN_MSG_TYPE, (uint16_t)type);
    wr16(image + message + FUN_MSG_SENDER, be16(image + AES_GL_APID));
    wr16(image + message + FUN_MSG_MORE, FUN_MSG_NO_MORE);
    wr16(image + message + FUN_MSG_WORD_3, (uint16_t)word3);
    wr16(image + message + FUN_MSG_WORD_3 + M68K_WORD_BYTES, (uint16_t)word4);
    wr16(image + message + FUN_MSG_WORD_3 + 2 * M68K_WORD_BYTES, (uint16_t)word5);
    wr16(image + message + FUN_MSG_WORD_3 + 3 * M68K_WORD_BYTES, (uint16_t)word6);
    wr16(image + message + FUN_MSG_WORD_3 + 4 * M68K_WORD_BYTES, (uint16_t)word7);
    written = aes_desk_appl_write(image, (int16_t)be16(image + AES_GL_APID), FUN_MSG_BYTES, message);
    host_slot_release(AES_DESK_FUN_MSG);
    return written;
}

/* ---- band 6 wave 2, group G2 (unit H): THE OPERATIONS' DRIVERS ------------------------------------------------------
 * EACH FRAME THE ROM HANDS ON BY ADDRESS is a host slot off target (`host_slot.h`, group G2's window), the ROM's layout,
 * HELD ACROSS THE ROUTINE'S YIELDS AND WAITS — fun_rebld's over its bindings, fun_mkdir's over form_do and fun_alert,
 * fun_d2desk's over its alerts and pro_run, fun_op's over the copy engine's dialogs, fun_win2win's and fun_desk2win's
 * over the whole drop beneath them (each a "held where parked" fact `aes_event.SLOTS_HELD_WHERE_PARKED` owes a line at
 * the binding). */
_Static_assert(FUN_REBLD_FRAME_BYTES == HOST_SLOT_AES_DESK_FUN_REBLD_FRAME_BYTES, "fun_rebld's frame and its host slot");
_Static_assert(FUN_MKDIR_FRAME_BYTES == HOST_SLOT_AES_DESK_FUN_MKDIR_FRAME_BYTES, "fun_mkdir's frame and its host slot");
_Static_assert(FUN_D2DESK_FRAME_BYTES == HOST_SLOT_AES_DESK_FUN_D2DESK_FRAME_BYTES, "fun_d2desk's frame and its host slot");
_Static_assert(FUN_OP_FRAME_BYTES == HOST_SLOT_AES_DESK_FUN_OP_FRAME_BYTES, "fun_op's frame and its host slot");
_Static_assert(FUN_WIN2WIN_FRAME_BYTES == HOST_SLOT_AES_DESK_FUN_WIN2WIN_FRAME_BYTES, "fun_win2win's frame and its host slot");
_Static_assert(FUN_DESK2WIN_FRAME_BYTES == HOST_SLOT_AES_DESK_FUN_DESK2WIN_FRAME_BYTES, "fun_desk2win's frame and its host slot");

/* A window's GEM handle, read again at each use as the ROM's `6(a5)` is. */
static int16_t window_id(uint8_t *image, uint32_t window)
{
    return (int16_t)bus_word(image, window + WNODE_ID);
}

/* The spec a window shows: its path node's. */
static uint32_t spec_of(uint8_t *image, uint32_t window)
{
    return bus_long(image, window + WNODE_PATH) + PNODE_SPEC;
}

/* $fdfdf2 — fun_rebld: the hourglass; every open window whose spec is `window`'s (the windows by level, the fourth
 * first) read again (pn_active), verified, its info line made and set, and a redraw of its work area sent to the desk
 * itself; the arrow. */
void aes_desk_fun_rebld(uint8_t *image, uint32_t window)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(FUN_REBLD_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_FUN_REBLD_FRAME, frame_local);
    uint32_t spec;

    aes_desk_graf_mouse(image, DESK_CURSOR_HOURGLASS, DESK_NO_FORM);
    spec = spec_of(image, window);
    for (int16_t level = DESK_WINDOWS; level; level--) {
        uint32_t info;

        window = aes_win_ith(image, level);
        if (!window_id(image, window) || !aes_streq(image, spec_of(image, window), spec))
            continue;
        (void)aes_pn_active(image, bus_long(image, window + WNODE_PATH));
        aes_desk_verify(image, window_id(image, window), DESK_VERIFY_CHANGED);
        aes_win_sinfo(image, window);
        info = window + WNODE_INFO;
        (void)aes_desk_wind_set(image, window_id(image, window), WF_INFO, (int16_t)(info >> 16), (int16_t)info, 0, 0);
        (void)aes_desk_wind_get(image, window_id(image, window), WF_WORKXYWH, frame + FUN_REBLD_X, frame + FUN_REBLD_Y,
                                frame + FUN_REBLD_W, frame + FUN_REBLD_H);
        (void)aes_desk_fun_msg(image, WM_REDRAW, (int16_t)be16(image + AES_GL_APID), window_id(image, window),
                               (int16_t)be16(image + frame + FUN_REBLD_X), (int16_t)be16(image + frame + FUN_REBLD_Y),
                               (int16_t)be16(image + frame + FUN_REBLD_W), (int16_t)be16(image + frame + FUN_REBLD_H));
    }
    aes_desk_graf_mouse(image, DESK_CURSOR_ARROW, DESK_NO_FORM);
    host_slot_release(AES_DESK_FUN_REBLD_FRAME);
}

/* The separators of the text at `text` past its first byte — the ROM's count: each byte read is the one BEHIND a
 * non-NUL byte (`tst.b (a3)+ / cmpi.b #92,(a3)`). */
static int16_t separators_past_the_first(uint8_t *image, uint32_t text)
{
    int16_t separators = 0;

    while (bus_byte(image, text++))
        if (bus_byte(image, text) == SPEC_SEPARATOR)
            separators++;
    return separators;
}

/* fun_mkdir's one turn of its dialog, once a name was typed: the name added to the path, searched for (an entry of
 * that name refused as EACCDN would be), else Dcreate'd; a refusal's alert — its answer, less one, whether to turn
 * again — and the name taken off; else the DOS glue's verdict, and the window rebuilt on success. */
static int16_t made_or_refused(uint8_t *image, uint32_t window, uint32_t name)
{
    uint32_t path = desk_globals(image) + DESK_G_TMPPTH;
    int16_t alert;

    (void)aes_desk_add_fname(image, path, name);
    (void)aes_dos_sdta(image, AES_FUN_MKDIR_SDTA_RETURN, AES_SH_SCRATCH);
    alert = desk_search_or_mkdir(image, path) ? FUN_ALERT_NO_SUCH_FOLDER : FUN_ALERT_DISK_FULL;
    if (be16(image + AES_DOS_ERR) && (int16_t)be16(image + AES_DOS_AX) == DOS_AX_ACCESS_DENIED) {
        int16_t again = (int16_t)(aes_desk_fun_alert(image, FUN_ALERT_FIRST_BUTTON, alert, FUN_ALERT_NO_PARAMETERS) - 1);

        (void)aes_desk_del_fname(image, path);
        return again;
    }
    if (aes_desk_d_errmsg(image))
        aes_desk_fun_rebld(image, window);
    return 0;
}

/* $fdfebc — fun_mkdir: File > New Folder in `window`. Its spec copied to g_tmppth; a path already eight folders deep
 * refused (alert, 0). Else the dialog — its field emptied, shown, run — until it is cancelled, its name is empty, or
 * a turn (`made_or_refused`) says not again; the arrow, the dialog put away; 1. */
int16_t aes_desk_fun_mkdir(uint8_t *image, uint32_t window)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(FUN_MKDIR_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_FUN_MKDIR_FRAME, frame_local);
    uint32_t tree = bus_long(image, desk_globals(image) + DESK_MKDIR_TREE);
    uint32_t path = desk_globals(image) + DESK_G_TMPPTH;
    int16_t again = 1;

    (void)aes_strcpy(image, spec_of(image, window), path);
    if (separators_past_the_first(image, path) > MKDIR_DEEPEST) {
        (void)aes_desk_fun_alert(image, FUN_ALERT_FIRST_BUTTON, FUN_ALERT_TOO_DEEP, FUN_ALERT_NO_PARAMETERS);
        host_slot_release(AES_DESK_FUN_MKDIR_FRAME);
        return FUN_MKDIR_TOO_DEEP;
    }
    while (again) {
        set_bus_byte(image, frame + FUN_MKDIR_TEXT, 0);
        aes_inf_sset(image, tree, MKDIR_NAME_FIELD, frame + FUN_MKDIR_TEXT);
        aes_desk_show_dial(image, tree);
        (void)aes_desk_form_do(image, tree, 0);
        again = 0;
        if (!aes_inf_what(image, tree, MKDIR_OK, MKDIR_CANCEL))
            continue;
        aes_desk_wait(image, DESK_WAIT_BUSY);
        aes_fs_sget(image, tree, MKDIR_NAME_FIELD, frame + FUN_MKDIR_TEXT);
        aes_unfmt_str(image, frame + FUN_MKDIR_TEXT, frame + FUN_MKDIR_NAME);
        if (bus_byte(image, frame + FUN_MKDIR_NAME))
            again = made_or_refused(image, window, frame + FUN_MKDIR_NAME);
    }
    aes_desk_wait(image, DESK_WAIT_DONE);
    (void)aes_desk_hide_dial(image, tree);
    host_slot_release(AES_DESK_FUN_MKDIR_FRAME);
    return FUN_MKDIR_MADE;
}

/* A desktop icon's drive letter: its ICONBLK's character, the word's low byte. */
static uint8_t icon_letter(uint8_t *image, int16_t object)
{
    return (uint8_t)bus_word(image, aes_get_spec(image, screen_objects(image), object) + IB_CHAR);
}

/* fun_d2desk's drop of the drive `source` on the disk `object`: the copy's alert ("A" onto "B", the destination named
 * twice); then the two texts made "A: B:", and on OK the DISKCOPY command with that tail kept (pro_cmd) and run. */
static int16_t disk_copied(uint8_t *image, uint32_t frame, int16_t source, int16_t object)
{
    uint8_t from = icon_letter(image, source), to = icon_letter(image, object);
    int16_t answer;

    set_bus_byte(image, frame + FUN_D2DESK_SOURCE_TEXT, from);
    set_bus_byte(image, frame + FUN_D2DESK_SOURCE_TEXT + 1, 0);
    set_bus_byte(image, frame + FUN_D2DESK_BLANK, ' ');
    set_bus_byte(image, frame + FUN_D2DESK_DESTINATION_TEXT, to);
    set_bus_byte(image, frame + FUN_D2DESK_DESTINATION_TEXT + 1, 0);
    set_bus_byte(image, frame + FUN_D2DESK_DESTINATION_TEXT + 2, 0);
    set_bus_long(image, frame + FUN_D2DESK_COPY_PARAMETERS, frame + FUN_D2DESK_SOURCE_TEXT);
    set_bus_long(image, frame + FUN_D2DESK_COPY_PARAMETERS + M68K_LONG_BYTES, frame + FUN_D2DESK_DESTINATION_TEXT);
    set_bus_long(image, frame + FUN_D2DESK_COPY_PARAMETERS + 2 * M68K_LONG_BYTES, frame + FUN_D2DESK_DESTINATION_TEXT);
    answer = aes_desk_fun_alert(image, FUN_ALERT_SECOND_BUTTON, FUN_ALERT_DISK_COPY, frame + FUN_D2DESK_COPY_PARAMETERS);
    set_bus_byte(image, frame + FUN_D2DESK_SOURCE_TEXT + 1, DRIVE_MARK);
    set_bus_byte(image, frame + FUN_D2DESK_DESTINATION_TEXT + 1, DRIVE_MARK);
    if (answer != FUN_ALERT_OK)
        return D2DESK_NONE;
    if (!aes_pro_cmd(image, aes_ini_str(image, DISKCOPY_STRING), frame + FUN_D2DESK_SOURCE_TEXT, DISKCOPY_UNREAD,
                     DISKCOPY_TAIL_BYTE))
        return D2DESK_NONE;
    (void)aes_pro_run(image, DISKCOPY_ISGRAF, DISKCOPY_ISOVER, DESKTOP_WINDOW, object);
    return D2DESK_COPIED;
}

/* The engine run over the path's selection, into g_1text, its three counts into the frame. */
static void dir_op_over(uint8_t *image, int16_t op, uint32_t path, uint32_t frame)
{
    (void)aes_desk_dir_op(image, op, path + PNODE_SPEC, bus_long(image, path + PNODE_FLIST), desk_globals(image) + DESK_G_1TEXT,
                          frame + FUN_OP_FILES, frame + FUN_OP_FOLDERS, frame + FUN_OP_SIZE);
}

/* fun_op's operation over its frame (below). */
static int16_t operated(uint8_t *image, int16_t op, uint32_t path, uint32_t frame)
{
    if (op == OP_NONE)
        return FUN_OP_REFUSED;
    if (op == OP_COPY) {
        if (!aes_desk_par_chk(image, path + PNODE_SPEC, bus_long(image, path + PNODE_FLIST), desk_globals(image) + DESK_G_1TEXT))
            return FUN_OP_REFUSED;
        dir_op_over(image, OP_COUNT, path, frame);
        if ((int16_t)(be16(image + AES_DESK_OP_DEPTH) + separators_past_the_first(image, desk_globals(image) + DESK_G_1TEXT))
            > FUN_OP_DEEPEST) {
            (void)aes_desk_fun_alert(image, FUN_ALERT_FIRST_BUTTON, FUN_ALERT_INVALID_COPY, FUN_ALERT_NO_PARAMETERS);
            return FUN_OP_REFUSED;
        }
    }
    dir_op_over(image, OP_COUNT, path, frame);
    dir_op_over(image, op, path, frame);
    return FUN_OP_DONE;
}

/* $fe003a — fun_op: the copy engine over the path's selection, its destination g_1text. Nothing to do: 0. A copy:
 * refused where a folder would go into itself (par_chk, 0); else counted, and refused where the deepest folder it
 * reaches plus the destination's separators pass nine (alert, 0). Then — A COPY COUNTED A SECOND TIME, the ROM's —
 * the selection counted, the operation run: 1. */
int16_t aes_desk_fun_op(uint8_t *image, int16_t op, uint32_t path)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(FUN_OP_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_FUN_OP_FRAME, frame_local);
    int16_t done = operated(image, op, path, frame);

    host_slot_release(AES_DESK_FUN_OP_FRAME);
    return done;
}

/* $fe0140 — fun_ddst: a window's files dropped on the desktop icon `anode` (object `object`): onto a disk, copied to
 * its root (g_1text "X:\*.*", the drive's letter its icon's); onto the trash, deleted; onto the cartridge, refused
 * (alert, 0); onto anything else — or no icon — nothing (fun_op's OP_NONE). fun_op's answer. */
int16_t aes_desk_fun_ddst(uint8_t *image, uint32_t path, uint32_t anode, int16_t object)
{
    int16_t op = OP_NONE;

    if (anode != ANODE_NONE)
        switch (bus_word(image, anode + ANODE_TYPE)) {
        case AT_ISDISK:
            set_bus_byte(image, desk_globals(image) + DESK_G_1TEXT, icon_letter(image, object));
            (void)aes_strcpy(image, AES_FUN_ROOT_SPEC, desk_globals(image) + DESK_G_1TEXT + 1);
            op = OP_COPY;
            break;
        case AT_ISTRSH:
            op = OP_DELETE;
            break;
        case AT_ISCART:
            (void)aes_desk_fun_alert(image, FUN_ALERT_FIRST_BUTTON, FUN_ALERT_CARTRIDGE, FUN_ALERT_NO_PARAMETERS);
            return FUN_OP_REFUSED;
        }
    return aes_desk_fun_op(image, op, path);
}

/* $fe01d6 — fun_wdst: a window's files dropped on a window whose spec is `spec`: the destination g_1text, the spec up
 * to its wildcard — then into the folder `fnode` names where the drop was on a folder's icon (`anode` a folder's:
 * its name and "\*.*"), else "*.*" again (the window's own path). A copy (fun_op). */
int16_t aes_desk_fun_wdst(uint8_t *image, uint32_t path, uint32_t spec, uint32_t anode, uint32_t fnode)
{
    uint32_t at = desk_globals(image) + DESK_G_1TEXT;

    (void)aes_strcpy(image, spec, at);
    while (bus_byte(image, at) != SPEC_WILDCARD)
        at++;
    set_bus_byte(image, at, 0);
    if (anode != ANODE_NONE && bus_word(image, anode + ANODE_TYPE) == AT_ISFOLD) {
        at = aes_strcpy(image, fnode + FNODE_NAME, at);
        (void)aes_strcpy(image, AES_FUN_FOLDER_SPEC, at - 1);
    } else
        (void)aes_strcat(image, AES_FUN_ALL_FILES, at);
    return aes_desk_fun_op(image, OP_COPY, path);
}

/* A window that shows the cartridge: its name the cartridge window's (AES_DESK_ROOT_NAME's text). */
static int shows_the_cartridge(uint8_t *image, uint32_t window)
{
    return aes_streq(image, window + WNODE_NAME, AES_DESK_ROOT_NAME) != 0;
}

/* $fe0258 — fun_win2win: a drag from the window `source` into the window `destination`, let go on `object`. Either
 * window the cartridge's: refused (alert). Else the files copied there (fun_wdst, the destination's item found by
 * i_find); done, the source window cleared of its selection (when it is another) and the destination rebuilt. */
void aes_desk_fun_win2win(uint8_t *image, int16_t source, int16_t destination, int16_t object)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(FUN_WIN2WIN_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_FUN_WIN2WIN_FRAME, frame_local);
    uint32_t from = aes_win_find(image, source), to = aes_win_find(image, destination);

    if (shows_the_cartridge(image, from) || shows_the_cartridge(image, to))
        (void)aes_desk_fun_alert(image, FUN_ALERT_FIRST_BUTTON, FUN_ALERT_CARTRIDGE, FUN_ALERT_NO_PARAMETERS);
    else {
        uint32_t anode = aes_i_find(image, destination, object, frame + FUN_WIN2WIN_FNODE, frame + FUN_WIN2WIN_ISAPP);

        if (aes_desk_fun_wdst(image, bus_long(image, from + WNODE_PATH), spec_of(image, to), anode,
                              bus_long(image, frame + FUN_WIN2WIN_FNODE))) {
            if (source != destination)
                aes_desk_clear(image, source);
            aes_desk_fun_rebld(image, to);
        }
    }
    host_slot_release(AES_DESK_FUN_WIN2WIN_FRAME);
}

/* $fe02f2 — fun_win2desk: a drag from the window `source` let go on the desktop icon `object`. From the cartridge's
 * window: onto a disk or the cartridge refused (alert), onto the trash GEM's error 5; nothing done. Else the files
 * dropped there (fun_ddst); done, the source window rebuilt. */
void aes_desk_fun_win2desk(uint8_t *image, int16_t source, int16_t object)
{
    uint32_t anode = aes_app_afind(image, AFIND_ON_THE_DESKTOP, AT_ISFILE, object, 0, 0);
    uint32_t window = aes_win_find(image, source);

    if (shows_the_cartridge(image, window)) {
        switch (bus_word(image, anode + ANODE_TYPE)) {
        case AT_ISDISK:
        case AT_ISCART:
            (void)aes_desk_fun_alert(image, FUN_ALERT_FIRST_BUTTON, FUN_ALERT_CARTRIDGE, FUN_ALERT_NO_PARAMETERS);
            break;
        case AT_ISTRSH:
            (void)aes_fm_error(image, FM_ERROR_ACCESS_DENIED);
            break;
        }
        return;
    }
    if (aes_desk_fun_ddst(image, bus_long(image, window + WNODE_PATH), anode, object))
        aes_desk_fun_rebld(image, window);
}

/* $fe038c — fun_disk: the drive icon `drive`'s root opened as a path ("X:\*.*", every kind of entry) and read, every
 * file of it un-shown (its object 0), the screen's root SELECTED while its files are dropped — on the window `window`
 * (fun_wdst, into its spec) or, with none, on the desktop icon (fun_ddst) —, then the path closed and the desktop's
 * icons deselected. The drop's answer. A ROM BEHAVIOUR: pn_active's answer is compared with 18 and dropped; and where
 * no path node is free the answer is D7 AS ITS CALLER LEFT IT — no C has that word: the C answers 0 there. */
int16_t aes_desk_fun_disk(uint8_t *image, int16_t drive, uint32_t window, uint32_t anode, uint32_t fnode, int16_t object)
{
    uint32_t root = aes_pn_open(image, (int16_t)bus_word(image, aes_get_spec(image, screen_objects(image), drive) + IB_CHAR),
                                AES_FUN_NO_PATH, AES_FUN_ANY_NAME, AES_FUN_ANY_EXT, DESK_SEARCH_ALL);
    int16_t dropped = 0;

    if (root == PNODE_NONE)
        return FUN_DISK_NO_PATH_NODE;
    (void)aes_pn_active(image, root);
    if (bus_long(image, root + PNODE_FLIST) != FNODE_NONE) {
        for (uint32_t file = bus_long(image, root + PNODE_FLIST); file != FNODE_NONE; file = bus_long(image, file + FNODE_NEXT))
            set_bus_word(image, file + FNODE_OBID, 0);
        set_bus_word(image, screen_objects(image) + OB_STATE, FUN_DISK_ROOT_SELECTED);
        dropped = window ? aes_desk_fun_wdst(image, root, spec_of(image, window), anode, fnode)
                         : aes_desk_fun_ddst(image, root, anode, object);
        set_bus_word(image, screen_objects(image) + OB_STATE, 0);
    }
    aes_pn_close(image, root);
    aes_desk_clear(image, DESKTOP_WINDOW);
    return dropped;
}

/* $fe0454 — fun_desk2win: the selected desktop icons let go in the window `window`, on its `object`. Each: the trash
 * and the cartridge refused (an alert each); a drive's files dropped there (fun_disk), the window rebuilt where any
 * were. */
void aes_desk_fun_desk2win(uint8_t *image, int16_t window, int16_t object)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(FUN_DESK2WIN_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_FUN_DESK2WIN_FRAME, frame_local);
    uint32_t to = aes_win_find(image, window);
    uint32_t anode = aes_i_find(image, window, object, frame + FUN_DESK2WIN_FNODE, frame + FUN_DESK2WIN_ISAPP);

    for (int16_t source = aes_win_isel(image, screen_objects(image), DESKTOP_ROOT, 0); source;
         source = aes_win_isel(image, screen_objects(image), DESKTOP_ROOT, source)) {
        uint32_t icon = aes_i_find(image, DESKTOP_WINDOW, source, frame + FUN_DESK2WIN_EACH_FNODE, frame + FUN_DESK2WIN_ISAPP);

        if (bus_word(image, icon + ANODE_TYPE) == AT_ISTRSH)
            (void)aes_desk_fun_alert(image, FUN_ALERT_FIRST_BUTTON, FUN_ALERT_DESKTOP_TO_WINDOW, FUN_ALERT_NO_PARAMETERS);
        else if (bus_word(image, icon + ANODE_TYPE) == AT_ISCART)
            (void)aes_desk_fun_alert(image, FUN_ALERT_FIRST_BUTTON, FUN_ALERT_CARTRIDGE, FUN_ALERT_NO_PARAMETERS);
        else if (aes_desk_fun_disk(image, source, to, anode, bus_long(image, frame + FUN_DESK2WIN_FNODE), object))
            aes_desk_fun_rebld(image, to);
    }
    host_slot_release(AES_DESK_FUN_DESK2WIN_FRAME);
}

/* $fe070a — fun_drag: a drag's drop sent to its driver by where it began (`source`, a window's handle or 0: the
 * desktop) and ended (`destination`), let go on `object` (`root` the desktop's background). Window to window:
 * fun_win2win; window to the desktop's background: refused (alert); window to an icon: fun_win2desk; desktop to a
 * window: fun_desk2win; desktop to an icon: fun_d2desk, whose answer is the drag's (else 0). */
int16_t aes_desk_fun_drag(uint8_t *image, int16_t source, int16_t destination, int16_t root, int16_t object)
{
    if (source) {
        if (destination)
            aes_desk_fun_win2win(image, source, destination, object);
        else if (object == root)
            (void)aes_desk_fun_alert(image, FUN_ALERT_FIRST_BUTTON, FUN_ALERT_FILES_TO_DESKTOP, FUN_ALERT_NO_PARAMETERS);
        else
            aes_desk_fun_win2desk(image, source, object);
        return D2DESK_NONE;
    }
    if (destination)
        aes_desk_fun_desk2win(image, destination, object);
    else if (object != root)
        return aes_desk_fun_d2desk(image, object);
    return D2DESK_NONE;
}

/* fun_d2desk's refusals: an alert, and nothing done (0). */
static int16_t refused(uint8_t *image, int16_t default_button, int16_t string, uint32_t parameters)
{
    (void)aes_desk_fun_alert(image, default_button, string, parameters);
    return D2DESK_NONE;
}

/* fun_d2desk's walk of the selection (below), over its frame. */
static int16_t dropped_on_an_icon(uint8_t *image, uint32_t frame, int16_t object)
{
    uint32_t destination = aes_app_afind(image, AFIND_ON_THE_DESKTOP, AT_ISFILE, object, 0, 0);
    int16_t copied = D2DESK_NONE;

    for (int16_t source = aes_win_isel(image, screen_objects(image), DESKTOP_ROOT, 0); source;
         source = aes_win_isel(image, screen_objects(image), DESKTOP_ROOT, source)) {
        uint32_t anode = aes_i_find(image, DESKTOP_WINDOW, source, frame + FUN_D2DESK_FNODE, frame + FUN_D2DESK_ISAPP);

        if (anode == destination)
            continue;
        if (bus_word(image, anode + ANODE_TYPE) == AT_ISCART || bus_word(image, anode + ANODE_TYPE) == AT_ISTRSH)
            return refused(image, FUN_ALERT_FIRST_BUTTON, FUN_ALERT_ICON_ON_ICON, FUN_ALERT_NO_PARAMETERS);
        switch (bus_word(image, destination + ANODE_TYPE)) {
        case AT_ISTRSH:
            set_bus_byte(image, frame + FUN_D2DESK_TRASH_TEXT, icon_letter(image, source));
            set_bus_byte(image, frame + FUN_D2DESK_TRASH_TEXT + 1, 0);
            set_bus_long(image, frame + FUN_D2DESK_TRASH_PARAMETER, frame + FUN_D2DESK_TRASH_TEXT);
            return refused(image, FUN_ALERT_SECOND_BUTTON, FUN_ALERT_DISK_TO_TRASH, frame + FUN_D2DESK_TRASH_PARAMETER);
        case AT_ISCART:
            return refused(image, FUN_ALERT_FIRST_BUTTON, FUN_ALERT_CARTRIDGE, FUN_ALERT_NO_PARAMETERS);
        case AT_ISDISK:
            if (disk_copied(image, frame, source, object))
                copied = D2DESK_COPIED;
            break;
        }
    }
    return copied;
}

/* $fe0500 — fun_d2desk: the selected desktop icons dropped on the icon `object`. Each selected but the destination's
 * own: the trash or the cartridge as a source refused; then by the destination's type — the trash: a disk may not go
 * there (the alert names the drive); the cartridge: refused; a disk: the disk copy (`disk_copied`). The answer: 1
 * once a copy was run. */
int16_t aes_desk_fun_d2desk(uint8_t *image, int16_t object)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(FUN_D2DESK_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_FUN_D2DESK_FRAME, frame_local);
    int16_t copied = dropped_on_an_icon(image, frame, object);

    host_slot_release(AES_DESK_FUN_D2DESK_FRAME);
    return copied;
}
/* ---- end of group G2's wave-2 ---- */
