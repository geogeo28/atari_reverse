/* desk/desksupp.h — UNIT J, THE DESK'S SUPPORT ROUTINE THAT TOUCHES THE FLOPPY (`src/desk/desksupp.c`; band 6 wave 1b,
 * group G2).
 *
 *   $fe1ad0 drive_check(letter)              before the desk opens a drive: the drive map (Drvmap) asked for it —
 *                                            fm_error(15) and AES_DOS_ERR 1 where it lacks it; for A: and B: a
 *                                            sector's buffer (Malloc), the boot sector read (XBIOS Floprd) while
 *                                            eralert asks a retry, the media change forced (Rwabs(0, NULL, 2, 0)),
 *                                            the buffer given back, AES_DOS_ERR 1 where the read failed; no memory:
 *                                            fm_error(8); the arrow again (desk_wait(0)) on every arm but the first
 *
 * ALCYON C. THE FLOPPY READ IS A DOOR OF THIS FILE'S (`floprd`): on target the XBIOS's own `trap #14` over the ROM's
 * nine-word frame, AES_XBIOS_RETURN parked as the ROM's trp14 parks it; OFF TARGET the host has no floppy, so the read
 * goes through `desk_floprd_door`, a hook A CASE BINDS — the ROM's own Floprd REPLAYED (`test/aes_desksupp.py`:
 * DRIVER_REPLAYED). trp14's C twin (band 5's) is not touched: it serves Getrez alone. drive_check answers nothing in
 * C: the word the ROM leaves (its last binding's or fm_error's) is a COUNTED divergence (`test/test_desk_supp.py`).
 *
 * BAND 6 WAVE 2 (group G3): THE WINDOWS' OPENERS AND CLOSERS, each read from its body (names `# ctx`: GEM's DESKSUPP /
 * DESKFUN where the body is its routine).
 *   $fe1068 do_diropen(window, new, icon, drive, path, name, ext, rect)
 *                                            the hourglass; a path node opened (pn_open, folders too) — none free: an
 *                                            alert (fun_alert 19), the window on top the desk's current, and done —
 *                                            and read (pn_active); the window named (the cartridge's: "Cartridge", and
 *                                            that name kept as the root's) and its info line; where `icon` (> 0) the
 *                                            window opened from it (do_wopen) and, where `new`, put on top; its view
 *                                            rebuilt (desk_verify); not `new`: redrawn over `rect`. The arrow. 1, always
 *   $fe13ea do_dopen(icon)                   a drive's icon opened: a window (none free: the alert "no more windows");
 *                                            the drive checked (the cartridge's not), made current, its root opened in
 *                                            the window from the icon's own rectangle — or the window freed. 0
 *   $fe14ba do_fopen(window, icon, drive, path, name, ext)
 *                                            a folder's path shown in the window: the drive checked, made current, the
 *                                            path made current (where that fails, the drive's root, "*.*" — STORED INTO
 *                                            ITS OWN ARGUMENT SLOTS 16, 20 and 24(a6), its caller's frame: no ROM caller
 *                                            reads them back), the old path closed, do_diropen over the work area. 0
 *   $fe1800 desk_do_format(icon)             with no window current, a disk's icon formatted: the alert (fun_alert 9,
 *                                            the letter), then FORMAT run (ini_str 3, the tail "A: /V") through pro_run;
 *                                            its answer, else 0
 *   $fe18e4 close_window(window)             a box shrunk to the window's icon, the window's path closed and the window
 *                                            freed; the one now on top the desk's current, its view rebuilt. 0
 *   $fe1972 close_folder(window, drive, path, name, ext)
 *                                            a box shrunk to the work area's middle (an icon's size), then do_fopen of
 *                                            the parent. 0
 *   $fe1a18 fun_close(window, close it)      File > Close / Close Window: the window's spec parsed; closing it, or at
 *                                            the root, close_window; else the path cut at its last backslash and
 *                                            close_folder; the hourglass round it. The callee's answer (0)
 */
#ifndef TOS102US_DESK_DESKSUPP_H
#define TOS102US_DESK_DESKSUPP_H

#define XBIOS_FLOPRD_FN       8          /* Floprd                                ($fe1b5c move.w #8,-(sp))      */
#define FLOPRD_FRAME_BYTES    20         /* the function, the buffer, the filler and five words ($fe1b62 adda.l #18 + the
                                          * slot under it)                                                       */
#define DRIVE_CHECK_SECTOR_BYTES 512     /* the buffer Malloc'ed                  ($fe1b2e move.l #512,(sp))     */
#define BOOT_SECTOR           1          /* Floprd's sector, track 0, side 0, one ($fe1b4c move.w #1,-(sp))     */
#define BOOT_TRACK            0
#define BOOT_SIDE             0
#define BOOT_SECTORS          1
#define FLOPRD_NO_FILLER      0          /*                                       ($fe1b58 clr.l -(sp))         */
#define FLOPPY_LETTER_LAST    'B'        /* a letter past it is no floppy: no read ($fe1b24 cmpi.w #67: bge)     */
#define READ_MEDIA_CHANGED    (-14)      /* Floprd's E_CHNG: as good as done      ($fe1b6e cmpi.w #-14,d6)       */
#define READ_SEEK_ERROR       (-6)       /* ...its E_SEEK: eralert's error 1, any other 2 ($fe1b7c cmpi.w #-6)  */
#define ERALERT_SEEK          1
#define ERALERT_READ          2
/* (fm_error is handed `aes/fmdo.h`'s DOS_BAD_DRIVE ($fe1b12 move.w #15) and DOS_NO_MEMORY ($fe1bd0 move.w #8).) */
#define FORCED_CHANGE_COUNT   2          /* Rwabs(0, NULL, 2, 0, drive): the media change forced ($fe1ba4)      */
#define DOS_ERR_SET           1
/* THE RETURN SITES THE DOORS PARK: each the word after its Line-F call. */
#define AES_DRIVE_CHECK_DRVMAP_RETURN  0xfe1ae6
#define AES_DRIVE_CHECK_FLOPRD_RETURN  0xfe1b62
#define AES_DRIVE_CHECK_RWABS_RETURN   0xfe1bb2
#define AES_DRIVE_CHECK_FREE_RETURN    0xfe1bbc

/* ---- band 6 wave 2: the openers and closers ----------------------------------------------------------------------- */
#define DO_DIROPEN_DONE       1          /* do_diropen's answer, both arms      ($fe11b0 moveq #1,d0)           */
#define DO_OPEN_DONE          0          /* do_dopen's, do_fopen's, close_window's, close_folder's ($fe13fc clr.w d5) */
#define DIROPEN_ATTRIBUTES    0x10       /* pn_open's: files and folders (F_SUBDIR) ($fe108a move.w #16,(sp))   */
#define DEFAULT_FIRST_BUTTON  1          /* fun_alert's / form_alert's default  ($fe10b0 move.l #$10013)        */
#define STRING_PATH_TOO_DEEP  19         /* fun_alert's string: STDEEPPA        ($fe10b0 #$10013)               */
#define STRING_NO_WINDOW      7          /* rsrc_gaddr's free string: no more windows ($fe142e #$50007)         */
#define STRING_FORMAT_WARNING 9          /* fun_alert's: the disk erased         ($fe1878 #$20009)               */
#define FORMAT_DEFAULT_BUTTON 2          /* ...its default: Cancel               ($fe1878)                       */
#define FORMAT_CHOSEN         1          /* ...the button that formats           ($fe1896 cmpi.w #1,d5)          */
#define STRING_FORMAT_COMMAND 3          /* ini_str's: the FORMAT program's name ($fe18ac move.w #3,-(sp))       */
#define FORMAT_TAIL_COUNT     252        /* pro_cmd's count byte: $fc, as the ROM pushes it ($fe189c #252)       */
#define FORMAT_UNREAD         1          /* pro_cmd's third word, read by nothing ($fe18a0 move.w #1,-(sp))      */
#define FORMAT_GRAPHIC        1          /* pro_run's isgraf and isover          ($fe18ca move.l #$10001)        */
#define FORMAT_OVER           1
#define ICON_CHARACTER        12         /* word: an ICONBLK's ib_char, the drive letter in its low byte ($fe1414) */
/* ROM data: the paths, names and extensions the openers hand on, and FORMAT's tail past its drive letter. */
#define AES_DOPEN_CHDIR_PATH  0xfef632   /* ""                                    ($fe1468 move.l #$fef632)       */
#define AES_DOPEN_PATH        0xfef633   /* ""                                    ($fe1494)                       */
#define AES_DOPEN_NAME        0xfef634   /* "*"                                   ($fe148e)                       */
#define AES_DOPEN_EXT         0xfef636   /* "*"                                   ($fe1488)                       */
#define AES_FOPEN_CHDIR_PATH  0xfef638   /* ""                                    ($fe1500 move.l #$fef638)       */
#define AES_FOPEN_ROOT_PATH   0xfef639   /* "": the root, where the path is refused ($fe1528)                    */
#define AES_FOPEN_ROOT_NAME   0xfef63a   /* "*"                                   ($fe1530)                       */
#define AES_FOPEN_ROOT_EXT    0xfef63c   /* "*"                                   ($fe1538)                       */
#define AES_FORMAT_TAIL       0xfef640   /* ": /V"                                ($fe188c move.l #$fef640)       */
/* fun_close: the path cut at its last backslash. */
#define PATH_SEPARATOR        '\\'      /* ($fe1a94 cmpi.b #92,(a3))                                             */
/* THE GROUP'S FRAMES (`host_slot.h`): unit J's one, and fun_close's own.
 * UNIT J'S FRAME — do_fopen's, close_folder's and close_window's work area (-12(a6) up, -8(a6) up: wind_get's
 * answers; do_fopen's is do_diropen's `rect`, HELD across it), and desk_do_format's tail (-16(a6): its letter, then
 * ": /V" copied over the NUL after it), the pointer to it fun_alert's merge reads (-6(a6)) and app_afind's answer
 * (-2(a6)) — HELD ACROSS fun_alert's WAIT: the tail is copied after it. None of the four nests in another. */
#define SUPP_FRAME_WORK       0          /* bytes[GRECT_BYTES]                                                   */
#define FORMAT_FRAME_TAIL     0          /* bytes[6]: the letter, ": /V", NUL    ($fe1864 -16(a6), $fe1884 -15(a6)) */
#define FORMAT_FRAME_TAIL_TEXT 1
#define FORMAT_FRAME_POINTER  10         /* long                                 ($fe1870 -6(a6))                */
#define FORMAT_FRAME_IS_APP   14         /* word                                 ($fe1824 -2(a6))                */
#define SUPP_FRAME_BYTES      16
/* FUN_CLOSE'S FRAME — its whole `link`, the ROM's layout: the spec's extension, name, path and drive word as fpd_parse
 * answers them, HELD across close_window / close_folder (the path, name and extension are handed on down). */
#define FUN_CLOSE_FRAME_EXT   0          /* bytes[4]                             ($fe1a34 -138(a6))              */
#define FUN_CLOSE_FRAME_NAME  4          /* bytes[10]                            ($fe1a3c -134(a6))              */
#define FUN_CLOSE_FRAME_PATH  14         /* bytes[122]                           ($fe1a44 -124(a6))              */
#define FUN_CLOSE_FRAME_DRIVE 136        /* word                                 ($fe1a4c -2(a6))                */
#define FUN_CLOSE_FRAME_BYTES 138

#ifndef __ASSEMBLER__
#include <stdint.h>

void aes_drive_check(uint8_t *image, int16_t letter);                                            /* $fe1ad0 */
/* band 6 wave 2 (group G3) */
int16_t aes_do_diropen(uint8_t *image, uint32_t window, int16_t new_window, int16_t icon, int16_t drive, uint32_t path,
                       uint32_t name, uint32_t ext, uint32_t rect);                             /* $fe1068 */
int16_t aes_do_dopen(uint8_t *image, int16_t icon);                                              /* $fe13ea */
int16_t aes_do_fopen(uint8_t *image, uint32_t window, int16_t icon, int16_t drive, uint32_t path, uint32_t name,
                     uint32_t ext);                                                              /* $fe14ba */
int16_t aes_desk_do_format(uint8_t *image, int16_t icon);                                        /* $fe1800 */
int16_t aes_close_window(uint8_t *image, uint32_t window);                                       /* $fe18e4 */
int16_t aes_close_folder(uint8_t *image, uint32_t window, int16_t drive, uint32_t path, uint32_t name,
                         uint32_t ext);                                                          /* $fe1972 */
int16_t aes_fun_close(uint8_t *image, uint32_t window, int16_t close_it);                        /* $fe1a18 */
#ifdef RECREATE_HOST_DIFFERENTIAL
/* The host's floppy read, which a case binds: Floprd(buffer, 0, device, sector, track, side, count)'s answer. */
extern int32_t (*desk_floprd_door)(uint8_t *image, uint32_t buffer, uint16_t device, uint16_t sector, uint16_t track,
                                   uint16_t side, uint16_t count);
#endif
#endif

#endif /* TOS102US_DESK_DESKSUPP_H */
