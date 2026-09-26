/* XBIOS Protobt (function 18) — $fc15f8.
 *
 * Builds a floppy boot sector in the caller's 512-byte buffer: a serial number, a BPB for the disk
 * geometry asked for, and the checksum word that decides whether the ROM's boot code will execute
 * it. It is the routine behind the desktop's Format, and it is pure computation over that buffer —
 * the only machine state it touches is XBIOS Random's seed, and only when it has to invent a serial.
 *
 * Compiled by Alcyon C: a `link a6` frame with the arguments at 8(a6), and the two mutable ones
 * (`serial` at 12(a6), `executable` at 18(a6)) rewritten IN THE CALLER'S FRAME as it goes.
 *
 *      link    a6,#-6              ; -6(a6) = the running checksum, -4(a6) = the cursor
 *      movem.l d5-d7/a5,-(sp)
 *      tst.w   18(a6)              ; `executable` < 0: decide it from what is already in the buffer
 *      bge.s   .serial
 *        move.w  #BOOT_SECTOR_WORDS,(sp)   ; the Alcyon write-to-(sp) second argument
 *        move.l  8(a6),-(sp)
 *        bsr     sum_words                 ; $fc16e4
 *        addq    #4,sp
 *        cmp.w   #BOOT_EXECUTABLE_SUM,d0
 *        ...     move.w #0/#1,18(a6)
 *   .serial:
 *      tst.l   12(a6)              ; `serial` < 0: leave bytes 8..10 alone
 *      blt.s   .bpb
 *        move.l  12(a6),d0
 *        cmp.l   #BOOT_SERIAL_MAX,d0
 *        ble.s   .store
 *          bsr   Random            ; $fc1510 — a serial that will not fit in 3 bytes gets a new one
 *          move.l d0,12(a6)
 *   .store: for (i = 0; i < 3; i++) { buf[8+i] = serial & 0xff; serial >>= 8; }   ; asr.l, on the frame
 *   .bpb:
 *      tst.w   16(a6)              ; `disk_type` < 0: leave bytes 11..29 alone
 *      blt.s   .checksum
 *        d6 = disk_type * 19
 *        for (i = 0; i < 19; i++) buf[11+i] = PROTOBT_BPB_TABLE[d6++]
 *   .checksum:
 *      sum every word of buf[0..509]                 ; note: 255 words, NOT 256
 *      *(word *)(buf + 510) = BOOT_EXECUTABLE_SUM - sum
 *      tst.w   18(a6)
 *      bne.s   .done
 *        addq.w #1,(buf + 510)     ; ...and if it must NOT be executable, break the sum by one
 *   .done:
 *      rts
 *
 * THE CHECKSUM LOOP STOPS AT 510, NOT 512 — `cmp.l buf+510,cursor / bhi` runs while the cursor is
 * strictly below buf+510, so it sums words 0..254 and the word it then writes at 510 is the 256th.
 * Summing 256 words instead would leave a sector whose checksum included itself.
 *
 * ...AND THE `executable < 0` PROBE SUMS 256, because there it is reading a sector someone else
 * built, checksum word included. The two loops are deliberately different lengths, which is why
 * `sum_words` takes a count rather than being written twice.
 *
 * THE SERIAL IS SHIFTED WITH `asr.l`, an arithmetic shift — but it can only be reached with a value
 * in [0, $ffffff], where arithmetic and logical shifts agree, so the C shifts an unsigned long. A
 * negative serial never gets here (the `blt` above sends it away) and Random returns 24 bits.
 *
 * IT MODIFIES ITS OWN ARGUMENTS. `serial` and `executable` are rewritten on the stack, which is
 * ordinary Alcyon practice and invisible to a caller that does not look — but it IS output, so the
 * reconstruction reports both through pointers rather than pretending the frame is read-only.
 */
#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif
#include <stdint.h>

#include "machine.h"
#include "addrs.h"
#include "m68k_idioms.h"
#include "xbios/xbios.h"      /* xbios_random: the ROM's own call at $fc1636, reconstructed as a call */

#define BPB_TABLE_ENTRY_BYTES 1     /* the prototype table is a table of BYTES */

/* $fc16e4: add `count` big-endian words, in 16 bits, wrapping. The ROM's own loop tests the count
 * AFTER reading it and decrements the caller's copy, so `count` = 0 would sum 65536 words; no call
 * site does that and the C says so with its bound rather than reproducing the wrap. */
static uint16_t sum_words(const uint8_t *image, uint32_t at, unsigned count)
{
    uint16_t sum = 0;

    for (unsigned i = 0; i < count; i++)
        sum = (uint16_t)(sum + be16(image + addr_add(at, i * 2u)));
    return sum;
}

/* `serial` and `executable` are in/out: the ROM rewrites both in the caller's stack frame, and a
 * case reads them back out of it. `disk_type` is not — nothing writes 16(a6). */
void xbios_protobt(uint8_t *image, uint32_t buffer, uint32_t *serial, int16_t disk_type,
                   int16_t *executable)
{
    uint16_t checksum;

#ifdef RECREATE_HOST_DIFFERENTIAL
    /* The buffer is the CALLER's pointer and the routine does not check it. HOST-ONLY, the way the
     * kit prescribes (kit.mk: "asserted where there is a process to abort"). */
    assert(buffer + BOOT_SECTOR_BYTES <= ST_RAM_BYTES);
#endif

    /* A negative `executable` means "keep whatever this sector already is", which is answered by
     * summing the sector as it stands — all 256 words this time. */
    if (*executable < 0)
        *executable = sum_words(image, buffer, BOOT_SECTOR_WORDS) == BOOT_EXECUTABLE_SUM;

    if (!keeps_current_value_long(*serial)) {
        if (*serial > BOOT_SERIAL_MAX)
            *serial = xbios_random(image);
        for (unsigned i = 0; i < BOOT_SERIAL_BYTES; i++) {
            image[addr_add(buffer, BOOT_SERIAL_AT + i)] = (uint8_t)*serial;
            *serial >>= 8;
        }
    }

    if (disk_type >= 0) {
        /* `muls.w #19,d6` then `movea.w d6,a1` on every pass: the row is a WORD and the index off
         * the prototype table is that word SIGN-EXTENDED, so a disk type whose product passes
         * $7fff reads BELOW the table (`m68k_idioms.h`; disk type 1725 is the case for it). */
        uint16_t row = (uint16_t)(disk_type * BOOT_BPB_BYTES);

        for (unsigned i = 0; i < BOOT_BPB_BYTES; i++)
            image[addr_add(buffer, BOOT_BPB_AT + i)] =
                image[addr_add(PROTOBT_BPB_TABLE, word_index(row + i, BPB_TABLE_ENTRY_BYTES))];
    }

    /* Everything below 510, so the checksum word itself is not part of what it balances. The ROM
     * stores the balancing word and then bumps the STORED word by one when the sector must not be
     * executable; one store of the same final value is the same image. */
    checksum = (uint16_t)(BOOT_EXECUTABLE_SUM - sum_words(image, buffer, BOOT_CHECKSUM_AT / 2));
    if (*executable == 0)
        checksum++;
    wr16(image + addr_add(buffer, BOOT_CHECKSUM_AT), checksum);
}
