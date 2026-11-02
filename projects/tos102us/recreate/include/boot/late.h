/* boot/late.h — the names BOOT B6 is spelt in: the boot's interrupt-enabled late slice [$fc0452, $fc047a) — the
 * interrupts opened, the cartridge's hook 1, GEMDOS's disk buffers and its init (`$fc4a9e`), the DOS date seeded from
 * the OS header and the clock asked for a better one (`$fc4be8`), the floppy's boot (`$fc053c`), the ACSI's (`$fc0558`)
 * and the reset-resident programs' scan (`$fc0e56`) (`src/boot/late/late.c`). The names that already exist stay where
 * they are (`addrs.h`: `SYSVAR_PHYSTOP`, `SYSVAR_BUFL`, `GEMDOS_DATE`, `GEMDOS_TIME`, `GEMDOS_DSETDRV`,
 * `BIOS_RTC_PROBE`, `BOOT_SECTOR_WORDS`, `BOOT_EXECUTABLE_SUM`; `boot/head.h`: `SYSVAR_HDV_BOOT`; `boot/sysvars.h`:
 * `SYSVAR_DSKBUFP`, `BOOT_DISK_BUFFER`, `ROM_OS_HEADER`, `OS_HEADER_DOSDATE`; `boot/hwinit.h`: `ROM_CARTRIDGE_HOOKS`;
 * `boot/display.h`: `ROM_DISPLAY_END` — this slice's first instruction; `boot/launch.h`: `ROM_LAUNCH` — where it ends,
 * `SYSVAR_BOOTDEV`; `gemdos/fs.h`: the BCB's fields).
 *
 * ASSEMBLER-SAFE above the `__ASSEMBLER__` guard (plain integer `#define`s, as `addrs.h`). The Python side reads it
 * with `layouts.parse_constants` (`test/boot_late.py`), so a value is spelt once.
 *
 * WHERE IT IS LAID (rulings "ROM-window overlay" and "Own link rule", 2026-10-29): over a COPY of the image's ROM bytes
 * no instruction of the slice runs or reads (held: the ROM's own slice is the same run with and without the overlay,
 * `test_boot_late.py`) — Prtblk's text ($fc31fa..$fc4278, XBIOS 36: unported, run by nothing of the slice), past B5's
 * display (`DISPLAY_LAID_AT`, [$fc3c00, $fc3c98)) — and LINKED THERE by its own Makefile rule (`build/bootlate/`),
 * with every callee-saved register FIXED: the ROM's routines the slice calls clobber them freely, and the ROM's slice
 * leaves them to its continuation as those routines leave them.
 */
#ifndef TOS102US_BOOT_LATE_H
#define TOS102US_BOOT_LATE_H

#define LATE_LAID_AT              0xfc3d00   /* the C's entry, its first byte */

/* ---- the ROM's slice ------------------------------------------------------------------------------------------- */
#define BOOT_SR_INTERRUPTS_OPEN   0x2300     /* `move #$2300,sr`: supervisor, the mask at 3 — the VBL (4) and the MFP
                                              * (6) let in, the HBL (2) kept out */
#define CARTRIDGE_HOOK_INTERRUPTS 1          /* the hooks' init bit once the interrupts are open (`moveq #1,d0`) */
#define CARTRIDGE_HOOK_FLOPPY_BOOT 3         /* ...and before the floppy's boot (`moveq #3,d0`, $fc053c) */
#define FLOPPY_BOOT_FRAME_BYTES   4          /* where $fc053c calls hdv_boot from: under the `bsr $fc053c`'s return (4) */

/* ---- $fc4a9e: GEMDOS's disk buffers, two lists of two BCBs, then its init and the boot drive made current -------- */
#define BOOT_BCB_FIRST            0x8846     /* four BCBs, end to end from here: the lists [0] -> [1] and [2] -> [3] */
#define BOOT_BCBS_PER_LIST        2
#define BOOT_SECTOR_BUFFER_FIRST  0x75c4     /* their four 512-byte sector buffers, end to end from here, in order */
#define ROM_GEMDOS_INIT           0xfc4e5e   /* GEMDOS's own init (Alcyon C: the ROM's on both shores, OS both run) */
#define GEMDOS_BUFFERS_FRAME_BYTES 12        /* where $fc4a9e calls it and Dsetdrv from: under the `bsr`'s return (4)
                                              * and its `link a6,#-4` (the saved A6, 4, and the one local, 4) */

/* ---- $fc4be8: the date and time read off the Mega ST's clock, where there is one ------------------------------- */
#define ROM_RTC_READ              0xfc4c44   /* the clock as one longword, date high, time low; -1: none read */
#define RTC_NO_STAMP              0xffffffff /* `cmpi.l #-1,d0`: the read that found no clock */

/* ---- $fc0558: the ACSI's boot — eight targets, each one's first sector read to `_dskbufp` and run where its 256
 * words sum to BOOT_EXECUTABLE_SUM ---------------------------------------------------------------------------------- */
#define ROM_ACSI_READ_BOOT_SECTOR 0xfc0586   /* D7 the target (in bits 5-7): Z set = the sector read (CODE: the ROM's,
                                              * ANSWERED AT ITS ENTRY on both shores, ruling D3) */
#define ACSI_TARGET_STEP          0x20       /* `add.b #32,d7`: the next target, until the byte wraps to 0 */

/* ---- $fc0e56: the reset-resident programs — RAM scanned from phystop down, a 512-byte page at a time ---------- */
#define RESIDENT_PAGE_BYTES       0x200      /* `suba.w #512,a0` */
#define RESIDENT_SCAN_FLOOR       0x400      /* `cmpa.l #$400,a0`: the scan stops here, the page not looked at */
#define RESIDENT_MAGIC            0x12123456u /* a page's first long: a program's mark ... */
#define RESIDENT_SELF             4          /* ...its second: the page's own address */
#define RESIDENT_ENTRY            8          /* `jsr 8(a0)`: the program's code, past the two longs */
#define RESIDENT_SUM              0x5678     /* the page's 256 words sum to this */

#endif /* TOS102US_BOOT_LATE_H */
