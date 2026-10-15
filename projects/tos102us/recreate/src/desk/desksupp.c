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
#include "aes/strings.h"
#include "aes/wmlib.h"
#include "aes/wmupdate.h"
#include "desk/deskact.h"
#include "desk/deskapp.h"
#include "desk/deskbind.h"
#include "desk/deskfpd.h"
#include "desk/deskfun.h"
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
    if (icon > 0) {
        aes_do_wopen(image, new_window, window_handle(image, window), icon, rect_word(image, rect, GRECT_X),
                     rect_word(image, rect, GRECT_Y), rect_word(image, rect, GRECT_W), rect_word(image, rect, GRECT_H));
        if (new_window)
            aes_win_top(image, window);
    }
    aes_desk_verify(image, window_handle(image, window), DESK_VERIFY_CHANGED);
    if (!new_window)
        aes_do_wredraw(image, window_handle(image, window), rect_word(image, rect, GRECT_X), rect_word(image, rect, GRECT_Y),
                       rect_word(image, rect, GRECT_W), rect_word(image, rect, GRECT_H));
    aes_desk_wait(image, DESK_WAIT_DONE);
    return DO_DIROPEN_DONE;
}

/* The drive letter of a desktop icon: its ICONBLK's ib_char's low byte. */
static inline int16_t icon_letter(uint8_t *image, int16_t icon)
{
    return (int16_t)(bus_word(image, aes_get_spec(image, screen_objects(image), icon) + ICON_CHARACTER) & 0xff);
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
    uint16_t frame_local[FRAME_LOCAL_WORDS(SUPP_FRAME_BYTES)];
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

/* $fe1972 — close_folder (`desk/desksupp.h`). */
int16_t aes_close_folder(uint8_t *image, uint32_t window, int16_t drive, uint32_t path, uint32_t name, uint32_t ext)
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
