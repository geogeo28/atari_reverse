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
#include "desk/deskapp.h"
#include "desk/deskbind.h"
#include "desk/deskleaf.h"
#include "desk/desksupp.h"

#ifdef RECREATE_HOST_DIFFERENTIAL
int32_t (*desk_floprd_door)(uint8_t *image, uint32_t buffer, uint16_t device, uint16_t sector, uint16_t track,
                            uint16_t side, uint16_t count);
#endif

/* Floprd through the XBIOS — the ROM's trp14 door over its caller's nine words, its own return parked in
 * AES_XBIOS_RETURN first (the site the ROM's door parks: its Line-F call's). ON TARGET the trap over that frame; OFF
 * TARGET the hook a case binds, refused by name where none is. The answer's word, as the ROM reads it. */
_Static_assert(BOOT_TRACK == 0 && BOOT_SIDE == 0 && FLOPRD_NO_FILLER == 0, "the frame's zero words are pushed by clr.l");

static int16_t floprd(uint8_t *image, uint32_t buffer, int16_t device)
{
    wr32(image + AES_XBIOS_RETURN, AES_DRIVE_CHECK_FLOPRD_RETURN);
#ifdef RECREATE_HOST_DIFFERENTIAL
    if (!desk_floprd_door)
        recreate_not_reconstructed("drive_check's Floprd: the host has no floppy, and no case bound its door");
    return (int16_t)desk_floprd_door(image, buffer, (uint16_t)device, BOOT_SECTOR, BOOT_TRACK, BOOT_SIDE, BOOT_SECTORS);
#else
    {
        /* The frame as the ROM lays it, pushed from its end: the count, the side and track (two zero words), the
         * sector, the device, the filler, the buffer, the function; three operands in registers the trap does not keep. */
        register uint32_t answer __asm__("d0") = XBIOS_FLOPRD_FN;
        register uint32_t device_word __asm__("d1") = (uint16_t)device;
        register uint32_t form __asm__("a0") = buffer;

        __asm__ volatile ("move.w %4,-(%%sp)\n\t"
                          "clr.l -(%%sp)\n\t"
                          "move.w %5,-(%%sp)\n\t"
                          "move.w %1,-(%%sp)\n\t"
                          "clr.l -(%%sp)\n\t"
                          "move.l %2,-(%%sp)\n\t"
                          "move.w %0,-(%%sp)\n\t"
                          "trap #14\n\t"
                          "lea %c3(%%sp),%%sp"
                          : "+d"(answer), "+d"(device_word), "+a"(form)
                          : "i"(FLOPRD_FRAME_BYTES), "i"(BOOT_SECTORS), "i"(BOOT_SECTOR)
                          : "d2", "a1", "a2", "memory", "cc");
        return (int16_t)answer;
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
                aes_desk_wait(image, 1);
                answer = floprd(image, buffer, drive);
                retry = read_is_done(answer) ? 0 : aes_eralert(image, answer == READ_SEEK_ERROR ? ERALERT_SEEK : ERALERT_READ, drive);
            } while (retry);
            (void)aes_trp13(image, AES_DRIVE_CHECK_RWABS_RETURN, BIOS_RWABS_FN, 0, 0, 0, FORCED_CHANGE_COUNT, 0, drive);
            (void)aes_dos_free(image, AES_DRIVE_CHECK_FREE_RETURN, buffer);
            if (!read_is_done(answer))
                wr16(image + AES_DOS_ERR, DOS_ERR_SET);
        }
    }
    aes_desk_wait(image, 0);
}
