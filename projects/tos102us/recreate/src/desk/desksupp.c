/* desksupp.c — UNIT J (`desk/desksupp.h`): drive_check, Alcyon C in the ROM, ported over its own order; and its
 * floppy door.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "recreate.h"
#include "aes/aes.h"
#include "aes/fmdo.h"
#include "aes/gemdosif.h"
#include "bios/bcon.h"
#include "host_slot.h"
#include "aes/objects.h"
#include "aes/resource.h"
#include "aes/shell.h"
#include "aes/strings.h"
#include "aes/wmlib.h"
#include "aes/wmupdate.h"
#include "desk/deskact.h"
#include "desk/deskapp.h"
#include "desk/deskbind.h"
#include "desk/deskfpd.h"
#include "desk/deskfun.h"
#include "desk/deskinf.h"
#include "desk/deskins.h"
#include "desk/deskleaf.h"
#include "desk/desksupp.h"
#include "desk/desktop.h"
#include "desk/deskview.h"
#include "desk/deskwin.h"

#ifdef RECREATE_HOST_DIFFERENTIAL
int32_t (*desk_floprd_door)(uint8_t *image, uint32_t buffer, uint16_t device, uint16_t sector, uint16_t track,
                            uint16_t side, uint16_t count);
#endif

/* Floprd through the XBIOS — the ROM's trp14 door over its caller's nine words (`desk/deskleaf.h`), its own return
 * parked in AES_XBIOS_RETURN first (the site the ROM's door parks: its Line-F call's). ON TARGET the trap over that
 * frame; OFF TARGET the hook a case binds, refused by name where none is. The answer's word, as the ROM reads it. */
static int16_t floprd(uint8_t *image, uint32_t buffer, int16_t device)
{
    desk_xbios_parked(image, AES_DRIVE_CHECK_FLOPRD_RETURN);
#ifdef RECREATE_HOST_DIFFERENTIAL
    if (!desk_floprd_door)
        recreate_not_reconstructed("drive_check's Floprd: the host has no floppy, and no case bound its door");
    return (int16_t)desk_floprd_door(image, buffer, (uint16_t)device, BOOT_SECTOR, BOOT_TRACK, BOOT_SIDE, BOOT_SECTORS);
#else
    {
        /* The frame as the ROM lays it: the function, the buffer, the filler, the device, the sector, the track, the
         * side, the count. */
        const uint16_t frame[] = {XBIOS_FLOPRD_FN, (uint16_t)(buffer >> 16), (uint16_t)buffer,
                                  (uint16_t)(FLOPRD_NO_FILLER >> 16), (uint16_t)FLOPRD_NO_FILLER, (uint16_t)device,
                                  BOOT_SECTOR, BOOT_TRACK, BOOT_SIDE, BOOT_SECTORS};

        _Static_assert(sizeof frame == FLOPRD_FRAME_BYTES, "Floprd's frame as the ROM pushes it");
        return (int16_t)desk_xbios_trap(frame, sizeof frame / sizeof frame[0]);
    }
#endif
}

/* A read Floprd answered as done — or with the media changed, which is as good. */
static inline int read_is_done(int16_t answer)
{
    return answer == 0 || answer == READ_MEDIA_CHANGED;
}

/* $fe1ad0 — drive_check (`desk/desksupp.h`). AES_DOS_ERR cleared first; the map's bit for the drive tested as the
 * LONG Drvmap answers, shifted right by the letter less 'A' (`asr.l`, the count modulo 64). */
void aes_drive_check(uint8_t *image, int16_t letter)
{
    int16_t drive = (int16_t)(letter - DRIVE_LETTER_FIRST), answer, retry = 1;
    uint32_t map, buffer;

    wr16(image + AES_DOS_ERR, 0);
    map = aes_trp13(image, AES_DRIVE_CHECK_DRVMAP_RETURN, BIOS_DRVMAP_FN, 0, 0, 0, 0, 0, 0);
    if (!(asr_long_by((int32_t)map, (uint16_t)drive) & 1)) {
        (void)aes_fm_error(image, DOS_BAD_DRIVE);
        wr16(image + AES_DOS_ERR, DOS_ERR_SET);
        return;
    }
    if (letter <= FLOPPY_LETTER_LAST) {
        buffer = aes_dos_alloc(image, DRIVE_CHECK_SECTOR_BYTES);
        if (buffer == 0) {
            (void)aes_fm_error(image, DOS_NO_MEMORY);
        } else {
            do {
                aes_desk_wait(image, DESK_WAIT_BUSY);
                answer = floprd(image, buffer, drive);
                retry = read_is_done(answer) ? 0 : aes_eralert(image, answer == READ_SEEK_ERROR ? ERALERT_SEEK : ERALERT_READ, drive);
            } while (retry);
            (void)aes_trp13(image, AES_DRIVE_CHECK_RWABS_RETURN, BIOS_RWABS_FN, 0, 0, 0, FORCED_CHANGE_COUNT, 0, drive);
            (void)aes_dos_free(image, AES_DRIVE_CHECK_FREE_RETURN, buffer);
            if (!read_is_done(answer))
                wr16(image + AES_DOS_ERR, DOS_ERR_SET);
        }
    }
    aes_desk_wait(image, DESK_WAIT_DONE);
}

/* ================================================================================================
 * BAND 6 WAVE 2 (group G3): THE WINDOWS' OPENERS AND CLOSERS.
 * ============================================================================================= */

/* THE FRAMES' SIZES ARE THEIR HOST SLOTS' (`host_slot.h`). */
_Static_assert(SUPP_FRAME_BYTES == HOST_SLOT_AES_DESK_SUPP_FRAME_BYTES, "unit J's frame and its host slot");
_Static_assert(FUN_CLOSE_FRAME_BYTES == HOST_SLOT_AES_DESK_FUN_CLOSE_FRAME_BYTES, "fun_close's frame and its host slot");

static inline int16_t window_handle(const uint8_t *image, uint32_t window)
{
    return (int16_t)bus_word(image, window + WNODE_ID);
}

/* The window's work area answered into the rectangle at `rect`. */
static inline void get_work(uint8_t *image, uint32_t window, uint32_t rect)
{
    (void)aes_desk_wind_get(image, window_handle(image, window), WF_WORKXYWH, rect + GRECT_X, rect + GRECT_Y, rect + GRECT_W,
                            rect + GRECT_H);
}

/* A window's title or info line set: wind_set over the text's address, its high word first. */
static inline void set_text(uint8_t *image, uint32_t window, int16_t field, uint32_t text)
{
    (void)aes_desk_wind_set(image, window_handle(image, window), field, (int16_t)(text >> 16), (int16_t)text, 0, 0);
}

/* The window on top made the desk's last opened (g_wlastsel: its handle, 0 for none) and its view rebuilt. */
static void the_top_window_made_current(uint8_t *image)
{
    uint32_t globals = desk_globals(image), top = aes_win_ontop(image);

    set_bus_word(image, globals + DESK_G_WLASTSEL, top ? (uint16_t)window_handle(image, top) : 0);
    aes_desk_verify(image, (int16_t)bus_word(image, globals + DESK_G_WLASTSEL), DESK_VERIFY_CHANGED);
}

/* do_diropen's opened path made the window's: its PNODE kept and made active, the window's name (the cartridge's, or
 * the path's) and its info line made and set. A frame of its own (W6-R4): what it keeps in registers would otherwise
 * stand in do_diropen's frame under do_wopen's and desk_verify's redraws, deep paths of PD0. */
__attribute__((noinline)) static void the_window_s_path_named(uint8_t *image, uint32_t window, int16_t drive, uint32_t opened)
{
    set_bus_long(image, window + WNODE_PATH, opened);
    (void)aes_pn_active(image, bus_long(image, window + WNODE_PATH));
    if (drive == CARTRIDGE_DRIVE) {
        (void)aes_strcpy(image, CARTRIDGE_NAME, window + WNODE_NAME);
        (void)aes_strcpy(image, window + WNODE_NAME, AES_DESK_ROOT_NAME);
    } else {
        aes_win_sname(image, window);
    }
    aes_win_sinfo(image, window);
    set_text(image, window, WF_NAME, window + WNODE_NAME);
    set_text(image, window, WF_INFO, window + WNODE_INFO);
}

/* do_diropen's old window redrawn over the rectangle at `rect`. A call of its own (W6-R4): inlined, the rectangle's
 * four addresses — read again here after do_wopen's — are kept in do_diropen's frame under do_wopen and desk_verify,
 * deep paths of PD0. */
__attribute__((noinline)) static void the_window_redrawn(uint8_t *image, uint32_t window, uint32_t rect)
{
    aes_do_wredraw(image, window_handle(image, window), rect_word(image, rect, GRECT_X), rect_word(image, rect, GRECT_Y),
                   rect_word(image, rect, GRECT_W), rect_word(image, rect, GRECT_H));
}

/* $fe1068 — do_diropen (`desk/desksupp.h`). */
int16_t aes_do_diropen(uint8_t *image, uint32_t window, int16_t new_window, int16_t icon, int16_t drive, uint32_t path,
                       uint32_t name, uint32_t ext, uint32_t rect)
{
    uint32_t opened;

    aes_desk_wait(image, DESK_WAIT_BUSY);
    opened = aes_pn_open(image, drive, path, name, ext, DIROPEN_ATTRIBUTES);
    if (!opened) {
        (void)aes_desk_fun_alert(image, DEFAULT_FIRST_BUTTON, STRING_PATH_TOO_DEEP, 0);
        the_top_window_made_current(image);
        aes_desk_wait(image, DESK_WAIT_DONE);
        return DO_DIROPEN_DONE;
    }
    the_window_s_path_named(image, window, drive, opened);
    if (icon > 0) {
        aes_do_wopen(image, new_window, window_handle(image, window), icon, rect_word(image, rect, GRECT_X),
                     rect_word(image, rect, GRECT_Y), rect_word(image, rect, GRECT_W), rect_word(image, rect, GRECT_H));
        if (new_window)
            aes_win_top(image, window);
    }
    aes_desk_verify(image, window_handle(image, window), DESK_VERIFY_CHANGED);
    if (!new_window)
        the_window_redrawn(image, window, rect);
    aes_desk_wait(image, DESK_WAIT_DONE);
    return DO_DIROPEN_DONE;
}

/* The drive letter an ICONBLK bears: its ib_char's low byte. */
static inline int16_t spec_letter(const uint8_t *image, uint32_t spec)
{
    return (int16_t)(bus_word(image, spec + ICON_CHARACTER) & 0xff);
}

/* The drive letter of a desktop icon: its ICONBLK's. */
static inline int16_t icon_letter(uint8_t *image, int16_t icon)
{
    return spec_letter(image, aes_get_spec(image, screen_objects(image), icon));
}

/* $fe13ea — do_dopen (`desk/desksupp.h`). The alert's answer is read by nothing. */
int16_t aes_do_dopen(uint8_t *image, int16_t icon)
{
    uint32_t globals = desk_globals(image), spec = aes_get_spec(image, screen_objects(image), icon), window;
    int16_t letter;

    aes_desk_wait(image, DESK_WAIT_BUSY);
    letter = (int16_t)(bus_word(image, spec + ICON_CHARACTER) & 0xff);
    window = aes_win_alloc(image, icon);
    if (!window) {
        (void)aes_desk_rsrc_gaddr(image, R_STRING, STRING_NO_WINDOW, globals + DESK_G_ALERT);
        (void)aes_desk_form_alert(image, DEFAULT_FIRST_BUTTON, bus_long(image, globals + DESK_G_ALERT));
    } else {
        if (letter != CARTRIDGE_DRIVE)
            aes_drive_check(image, letter);
        else
            wr16(image + AES_DOS_ERR, 0);
        if (be16(image + AES_DOS_ERR)) {
            aes_win_free(image, window);
        } else {
            if (letter != CARTRIDGE_DRIVE)
                (void)aes_pro_chdir(image, letter, AES_DOPEN_CHDIR_PATH);
            (void)aes_do_diropen(image, window, 1, icon, letter, AES_DOPEN_PATH, AES_DOPEN_NAME, AES_DOPEN_EXT,
                                 object_address(screen_objects(image), (int16_t)bus_word(image, window + WNODE_ROOT), OB_X));
        }
    }
    aes_desk_wait(image, DESK_WAIT_DONE);
    return DO_OPEN_DONE;
}

/* $fe14ba — do_fopen (`desk/desksupp.h`). Where the path is refused the ROM stores the root's spec into its own
 * argument slots (16, 20, 24(a6) — words of its CALLER's frame, which close_folder pops unread); the C's are its
 * parameters. */
int16_t aes_do_fopen(uint8_t *image, uint32_t window, int16_t icon, int16_t drive, uint32_t path, uint32_t name,
                     uint32_t ext)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(SUPP_FRAME_WORK + GRECT_BYTES)];  /* to the work area's end, held under do_diropen (W6-R4) */
    uint32_t work = host_slot_claim(AES_DESK_SUPP_FRAME, frame_local) + SUPP_FRAME_WORK;

    get_work(image, window, work);
    aes_desk_wait(image, DESK_WAIT_BUSY);
    aes_drive_check(image, drive);
    if (!be16(image + AES_DOS_ERR)) {
        (void)aes_pro_chdir(image, drive, AES_FOPEN_CHDIR_PATH);
        (void)aes_pro_chdir(image, drive, path);
        aes_pn_close(image, bus_long(image, window + WNODE_PATH));
        if (be16(image + AES_DOS_ERR)) {
            path = AES_FOPEN_ROOT_PATH;
            name = AES_FOPEN_ROOT_NAME;
            ext = AES_FOPEN_ROOT_EXT;
        }
        (void)aes_do_diropen(image, window, 0, icon, drive, path, name, ext, work);
    }
    aes_desk_wait(image, DESK_WAIT_DONE);
    host_slot_release(AES_DESK_SUPP_FRAME);
    return DO_OPEN_DONE;
}

/* $fe1800 — desk_do_format (`desk/desksupp.h`). */
int16_t aes_desk_do_format(uint8_t *image, int16_t icon)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(SUPP_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_SUPP_FRAME, frame_local), globals = desk_globals(image), node = ANODE_NONE;
    uint32_t tail = frame + FORMAT_FRAME_TAIL;
    int16_t ran = 0, answer;

    if (!bus_word(image, globals + DESK_SELECTION_WINDOW))
        node = aes_app_afind(image, AFIND_ON_THE_DESKTOP, AFIND_ANY, icon, aes_win_iname(image, icon), frame + FORMAT_FRAME_IS_APP);
    if (node && (int16_t)bus_word(image, node + ANODE_TYPE) == AT_ISDISK) {
        set_bus_byte(image, tail, (uint8_t)icon_letter(image, icon));
        set_bus_byte(image, tail + FORMAT_FRAME_TAIL_TEXT, STRING_NUL);
        wr32(image + frame + FORMAT_FRAME_POINTER, tail);
        answer = aes_desk_fun_alert(image, FORMAT_DEFAULT_BUTTON, STRING_FORMAT_WARNING, frame + FORMAT_FRAME_POINTER);
        (void)aes_strcpy(image, AES_FORMAT_TAIL, tail + FORMAT_FRAME_TAIL_TEXT);
        if (answer == FORMAT_CHOSEN
            && aes_pro_cmd(image, aes_ini_str(image, STRING_FORMAT_COMMAND), tail, FORMAT_UNREAD, FORMAT_TAIL_COUNT))
            ran = aes_pro_run(image, FORMAT_GRAPHIC, FORMAT_OVER, (int16_t)bus_word(image, globals + DESK_SELECTION_WINDOW), icon);
    }
    host_slot_release(AES_DESK_SUPP_FRAME);
    return ran;
}

/* $fe18e4 — close_window (`desk/desksupp.h`). The work area wind_get answers is read by nothing. */
int16_t aes_close_window(uint8_t *image, uint32_t window)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(SUPP_FRAME_BYTES)];
    uint32_t objects = screen_objects(image);
    int16_t obid;

    get_work(image, window, host_slot_claim(AES_DESK_SUPP_FRAME, frame_local) + SUPP_FRAME_WORK);
    host_slot_release(AES_DESK_SUPP_FRAME);
    obid = (int16_t)bus_word(image, window + WNODE_OBID);
    aes_zoom_closed(image, 1, window_handle(image, window), object_word(image, objects, obid, OB_X),
                    object_word(image, objects, obid, OB_Y));
    aes_pn_close(image, bus_long(image, window + WNODE_PATH));
    aes_win_free(image, window);
    the_top_window_made_current(image);
    return DO_OPEN_DONE;
}

/* Half of a word, as `divs.w #2` leaves its quotient: toward 0. */
static inline int16_t half_of(int16_t value)
{
    return (int16_t)(value / 2);
}

/* close_folder's box: shrunk from an icon's size at the middle of the window's work area onto that work area. A
 * frame of its own (W6-R4): the work area and the registers its arithmetic keeps would stand under do_fopen, on the
 * deepest path of PD0. */
__attribute__((noinline)) static void zoom_onto_the_middle(uint8_t *image, uint32_t window)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(SUPP_FRAME_BYTES)];
    uint32_t work = host_slot_claim(AES_DESK_SUPP_FRAME, frame_local) + SUPP_FRAME_WORK, globals = desk_globals(image);
    int16_t x, y;

    get_work(image, window, work);
    x = (int16_t)(half_of(rect_word(image, work, GRECT_W)) + rect_word(image, work, GRECT_X)
                  - half_of((int16_t)bus_word(image, globals + DESK_G_WICON)));
    y = (int16_t)(half_of(rect_word(image, work, GRECT_H)) + rect_word(image, work, GRECT_Y)
                  - half_of((int16_t)bus_word(image, globals + DESK_G_HICON)));
    host_slot_release(AES_DESK_SUPP_FRAME);
    aes_zoom_closed(image, 0, window_handle(image, window), x, y);
}

/* $fe1972 — close_folder (`desk/desksupp.h`). */
int16_t aes_close_folder(uint8_t *image, uint32_t window, int16_t drive, uint32_t path, uint32_t name, uint32_t ext)
{
    zoom_onto_the_middle(image, window);
    (void)aes_do_fopen(image, window, 0, drive, path, name, ext);
    return DO_OPEN_DONE;
}

/* $fe1a18 — fun_close (`desk/desksupp.h`). */
int16_t aes_fun_close(uint8_t *image, uint32_t window, int16_t close_it)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(FUN_CLOSE_FRAME_BYTES)];
    uint32_t frame = host_slot_claim(AES_DESK_FUN_CLOSE_FRAME, frame_local), path = frame + FUN_CLOSE_FRAME_PATH, end;
    int16_t answer;

    aes_desk_graf_mouse(image, DESK_CURSOR_HOURGLASS, DESK_NO_FORM);
    aes_fpd_parse(image, bus_long(image, window + WNODE_PATH) + PNODE_SPEC, frame + FUN_CLOSE_FRAME_DRIVE, path,
                  frame + FUN_CLOSE_FRAME_NAME, frame + FUN_CLOSE_FRAME_EXT);
    if (close_it)
        set_bus_byte(image, path, STRING_NUL);
    if (!bus_byte(image, path)) {
        answer = aes_close_window(image, window);
    } else {
        for (end = offset_by(path, (int16_t)(aes_strlen(image, path) - 1)); end != path && bus_byte(image, end) != PATH_SEPARATOR; end--)
            ;
        set_bus_byte(image, end, STRING_NUL);
        answer = aes_close_folder(image, window, (int16_t)be16(image + frame + FUN_CLOSE_FRAME_DRIVE), path,
                                  frame + FUN_CLOSE_FRAME_NAME, frame + FUN_CLOSE_FRAME_EXT);
    }
    aes_desk_graf_mouse(image, DESK_CURSOR_ARROW, DESK_NO_FORM);
    host_slot_release(AES_DESK_FUN_CLOSE_FRAME);
    return answer;
}

/* ==== BAND 6 W3a, STAGE 2: THE SELECTION OPENED AND SHOWN ============================================================
 * COMPILED FOR THE TARGET ALONE (the user's R3, ruling O1): no host twin, no Tier 1 — each held by its target-only rows
 * at the hands' arrivals (`test/test_desk_w3a_stage2.py`). */
#ifndef RECREATE_HOST_DIFFERENTIAL

/* do_open's window, where the selection is in one (g_cwin, read again as the ROM reads it): found (win_find),
 * AES_SH_CART_LAUNCH set by whether it is the cartridge's (its name $9888's), and its spec parsed into do_open's `frame`
 * where i_find found an FNODE; on the desktop none, the drive word cleared. A ROUTINE OF ITS OWN (`noinline`, W6-R4):
 * what its three calls keep live would stand in do_open's frame under every arm (a drive's window the deepest, File >
 * Open). The window, or 0. */
__attribute__((noinline)) static uint32_t the_window_s_spec_parsed(uint8_t *image, uint32_t frame)
{
    int16_t current = (int16_t)bus_word(image, desk_globals(image) + DESK_SELECTION_WINDOW);
    uint32_t window;

    if (current == DESKTOP_WINDOW) {
        wr16(image + frame + OPEN_PARSED_DRIVE, 0);
        return 0;
    }
    window = aes_win_find(image, current);
    wr16(image + AES_SH_CART_LAUNCH, aes_streq(image, window + WNODE_NAME, AES_DESK_ROOT_NAME) ? 1 : 0);
    if (be32(image + frame + OPEN_FRAME_FOUND + FIND_FNODE) != FNODE_NONE)
        aes_fpd_parse(image, bus_long(image, window + WNODE_PATH) + PNODE_SPEC, frame + OPEN_PARSED_DRIVE,
                      frame + OPEN_PARSED_PATH, frame + OPEN_PARSED_NAME, frame + OPEN_PARSED_EXT);
    return window;
}

/* A folder's name joined to do_open's parsed path: a backslash first where the path is not empty. */
__attribute__((noinline)) static void folder_joined(uint8_t *image, uint32_t path, uint32_t fnode)
{
    if (bus_byte(image, path))
        (void)aes_strcat(image, AES_OPEN_SEPARATOR, path);
    (void)aes_strcat(image, fnode + FNODE_NAME, path);
}

/* The trash opened: its alert (rsrc_gaddr's free string into a_alert, form_alert). A routine of its own (`noinline`,
 * W6-R4): the desk's block it reads twice would otherwise be kept in a register of do_open's frame. */
__attribute__((noinline)) static void the_trash_refused(uint8_t *image)
{
    uint32_t alert = desk_globals(image) + DESK_G_ALERT;

    (void)aes_desk_rsrc_gaddr(image, R_STRING, STRING_TRASH_OPENED, alert);
    (void)aes_desk_form_alert(image, TRASH_ALERT_DEFAULT, bus_long(image, alert));
}

/* $fe1568 — do_open (`desk/desksupp.h`). Its frame the ROM's (`OPEN_*`): fpd_parse's answers and i_find's two, handed
 * on BY ADDRESS. On the desktop (window 0) the drive is cleared and the path left as the frame holds it — the ROM's,
 * which no run reaches: the desktop holds no file and no folder. */
int16_t aes_do_open(uint8_t *image, int16_t icon)
{
    uint16_t frame_local[FRAME_LOCAL_WORDS(OPEN_FRAME_FOUND + FIND_FRAME_BYTES)];
    uint32_t frame = desk_local_address(frame_local), found = frame + OPEN_FRAME_FOUND, anode, window;

    anode = aes_i_find(image, (int16_t)bus_word(image, desk_globals(image) + DESK_SELECTION_WINDOW), icon, found + FIND_FNODE,
                       found + FIND_IS_APP);
    window = the_window_s_spec_parsed(image, frame);
    if (anode == ANODE_NONE)
        return DO_SUPP_NOTHING_DONE;
    switch (bus_word(image, anode + ANODE_TYPE)) {
    case AT_ISFILE:
        return aes_do_aopen(image, anode, (int16_t)be16(image + found + FIND_IS_APP), icon,
                            (int16_t)be16(image + frame + OPEN_PARSED_DRIVE), frame + OPEN_PARSED_PATH,
                            be32(image + found + FIND_FNODE) + FNODE_NAME);
    case AT_ISFOLD:
        folder_joined(image, frame + OPEN_PARSED_PATH, be32(image + found + FIND_FNODE));
        return aes_do_fopen(image, window, icon, (int16_t)be16(image + frame + OPEN_PARSED_DRIVE), frame + OPEN_PARSED_PATH,
                            frame + OPEN_PARSED_NAME, frame + OPEN_PARSED_EXT);
    case AT_ISDISK:
    case AT_ISCART:
        return aes_do_dopen(image, icon);
    case AT_ISTRSH:
        the_trash_refused(image);
        break;
    }
    return DO_SUPP_NOTHING_DONE;
}

/* do_aopen's two boxes, read by nothing after — the icon's and the root's (get_xywh), the root's corner added to the
 * icon's, as the ROM does. A ROUTINE OF ITS OWN (`noinline`, W6-R4): their sixteen bytes no frame under opn_appl's
 * dialog and pro_run. */
__attribute__((noinline)) static void the_boxes_read(uint8_t *image, int16_t icon)
{
    uint16_t boxes_local[FRAME_LOCAL_WORDS(AOPEN_BOXES_BYTES)];
    uint32_t boxes = desk_local_address(boxes_local), globals = desk_globals(image);

    aes_get_xywh(image, screen_objects(image), icon, boxes + AOPEN_ICON_X, boxes + AOPEN_ICON_Y, boxes + AOPEN_ICON_W,
                 boxes + AOPEN_ICON_H);
    aes_get_xywh(image, screen_objects(image), (int16_t)bus_word(image, globals + DESK_SELECTION_ROOT), boxes + AOPEN_ROOT_X,
                 boxes + AOPEN_ROOT_Y, boxes + AOPEN_ROOT_W, boxes + AOPEN_ROOT_H);
    wr16(image + boxes + AOPEN_ICON_X, (uint16_t)(be16(image + boxes + AOPEN_ICON_X) + be16(image + boxes + AOPEN_ROOT_X)));
    wr16(image + boxes + AOPEN_ICON_Y, (uint16_t)(be16(image + boxes + AOPEN_ICON_Y) + be16(image + boxes + AOPEN_ROOT_Y)));
}

/* Whether an ANODE's application pattern names no program ('*', '?' or empty): a document with none installed. */
static int names_no_program(const uint8_t *image, uint32_t anode)
{
    uint8_t first = bus_byte(image, bus_long(image, anode + ANODE_PAPPL));

    return first == PATTERN_ANY || first == PATTERN_ONE || first == STRING_NUL;
}

/* The Show / Print / Cancel alert's command: the viewer's or the printer's (ini_str) over the document, its tail's
 * count byte the ROM's; Cancel 0; any other answer itself. */
static int16_t show_or_print_commanded(uint8_t *image, int16_t answer, uint32_t name)
{
    switch (answer) {
    case SHOW_CHOSEN:
        return aes_pro_cmd(image, aes_ini_str(image, STRING_SHOW_COMMAND), name, AOPEN_UNREAD, SHOW_TAIL_BYTE);
    case PRINT_CHOSEN:
        return aes_pro_cmd(image, aes_ini_str(image, STRING_PRINT_COMMAND), name, AOPEN_UNREAD, PRINT_TAIL_BYTE);
    case CANCEL_CHOSEN:
        return 0;
    }
    return answer;
}

/* $fe11b4 — do_aopen (`desk/desksupp.h`). The command and the tail are the desk's own buffers where an arm made them
 * there, else copied into them; the ANODE's flags read once, as the ROM keeps them. */
int16_t aes_do_aopen(uint8_t *image, uint32_t anode, int16_t is_app, int16_t icon, int16_t drive, uint32_t path,
                     uint32_t name)
{
    uint16_t flags = bus_word(image, anode + ANODE_FLAGS);
    int16_t graphic = (int16_t)(flags & AF_ISGRAF), unbound = (int16_t)names_no_program(image, anode), going = 1;
    uint32_t globals, command = 0, tail = 0;

    the_boxes_read(image, icon);
    if (!(flags & AF_ISFMEM))
        (void)aes_pro_chdir(image, drive, path);
    globals = desk_globals(image);
    set_bus_byte(image, globals + DESK_G_CMD, STRING_NUL);
    set_bus_byte(image, globals + DESK_G_TAIL_TEXT, STRING_NUL);
    if (!unbound && !is_app) {
        command = bus_long(image, anode + ANODE_PAPPL);
        tail = name;
    } else if (is_app) {
        if (flags & AF_ISPARM) {
            command = globals + DESK_G_CMD;
            tail = globals + DESK_G_TAIL_TEXT;
            going = aes_desk_opn_appl(image, name, AES_OPEN_APPL_NO_TAIL, command, tail);
        } else {
            command = name;
        }
    } else {
        going = aes_desk_fun_alert(image, SHOW_PRINT_DEFAULT, STRING_SHOW_PRINT_CANCEL, FUN_ALERT_NO_PARAMETERS);
        command = globals + DESK_G_CMD;
        tail = globals + DESK_G_TAIL_TEXT;
        if (going == PRINT_CHOSEN)
            graphic = AOPEN_GRAPHIC;
        going = show_or_print_commanded(image, going, name);
    }
    if (!going)
        return DO_SUPP_NOTHING_DONE;
    globals = desk_globals(image);
    if (command != globals + DESK_G_CMD && command != 0)
        (void)aes_strcpy(image, command, globals + DESK_G_CMD);
    if (tail != globals + DESK_G_TAIL_TEXT && tail != 0)
        (void)aes_strcpy(image, tail, globals + DESK_G_TAIL_TEXT);
    if (flags & AF_ISFMEM)
        set_bus_byte(image, globals + DESK_G_TAIL, AOPEN_FULL_MEMORY_TAIL);
    return aes_pro_run(image, graphic, AOPEN_OVER, (int16_t)bus_word(image, globals + DESK_SELECTION_WINDOW), icon);
}

/* The drive a window's spec names: its first byte, sign-extended (`ext.w`). */
static int16_t spec_drive(const uint8_t *image, uint32_t window)
{
    return (int16_t)(int8_t)bus_byte(image, bus_long(image, window + WNODE_PATH) + PNODE_SPEC);
}

/* $fe16e6 — do_info (`desk/desksupp.h`). i_find's two answers handed BY ADDRESS (a target local, the ROM's -10 / -6);
 * a disk's letter is its desktop icon's (its ICONBLK's ib_char, the low byte). The dialogs' answers, but inf_file's,
 * are read by nothing; do_info answers 0. */
int16_t aes_do_info(uint8_t *image, int16_t icon)
{
    uint16_t found_local[FRAME_LOCAL_WORDS(FIND_FRAME_BYTES)];
    uint32_t found = desk_local_address(found_local), globals = desk_globals(image), anode, window = 0, tree, spec;
    int16_t current = (int16_t)bus_word(image, globals + DESK_SELECTION_WINDOW);

    anode = aes_i_find(image, current, icon, found + FIND_FNODE, found + FIND_IS_APP);
    if (current != DESKTOP_WINDOW)
        window = aes_win_find(image, current);
    if (anode == ANODE_NONE)
        return DO_SUPP_NOTHING_DONE;
    switch (bus_word(image, anode + ANODE_TYPE)) {
    case AT_ISFILE:
        aes_drive_check(image, spec_drive(image, window));
        if (!be16(image + AES_DOS_ERR)
            && aes_desk_inf_file(image, bus_long(image, window + WNODE_PATH) + PNODE_SPEC, be32(image + found + FIND_FNODE)))
            aes_desk_fun_rebld(image, window);
        break;
    case AT_ISFOLD:
        aes_drive_check(image, spec_drive(image, window));
        if (!be16(image + AES_DOS_ERR))
            (void)aes_desk_inf_folder_dlg(image, bus_long(image, window + WNODE_PATH) + PNODE_SPEC, be32(image + found + FIND_FNODE));
        break;
    case AT_ISDISK:
        spec = aes_get_spec(image, screen_objects(image), icon);
        aes_drive_check(image, spec_letter(image, spec));
        if (!be16(image + AES_DOS_ERR))
            (void)aes_desk_inf_disk(image, spec_letter(image, spec));
        break;
    case AT_ISTRSH:
        tree = bus_long(image, globals + DESK_TRASH_INFO_TREE);
        (void)aes_desk_inf_show(image, tree, OB_ROOT);
        set_object_word(image, tree, TRASH_INFO_OK, OB_STATE, 0);
        break;
    }
    return DO_SUPP_NOTHING_DONE;
}
#endif
