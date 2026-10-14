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

#ifndef __ASSEMBLER__
#include <stdint.h>

void aes_drive_check(uint8_t *image, int16_t letter);                                            /* $fe1ad0 */
#ifdef RECREATE_HOST_DIFFERENTIAL
/* The host's floppy read, which a case binds: Floprd(buffer, 0, device, sector, track, side, count)'s answer. */
extern int32_t (*desk_floprd_door)(uint8_t *image, uint32_t buffer, uint16_t device, uint16_t sector, uint16_t track,
                                   uint16_t side, uint16_t count);
#endif
#endif

#endif /* TOS102US_DESK_DESKSUPP_H */
