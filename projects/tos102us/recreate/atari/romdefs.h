/* romdefs.h — the numbers the rebuilt ROM is built from: its OS header, the machine it boots, and
 * the shifter registers the boot stub pokes. Included by header.S (via the assembler's C
 * preprocessor) and by boot_stub.c, so there is ONE definition of each and the two cannot disagree
 * about where the reset entry or the MUPB sits.
 *
 * EVERY HEADER VALUE HERE WAS READ OUT OF THE USER'S OWN TOS102US.img, not copied from a reference:
 *   60 2e 01 02 00 fc 00 30 00 fc 00 00 00 00 89 00 00 fc 00 30 00 fe ff f4 04 22 19 87 00 00 0e 96
 * The rebuilt ROM emits the same field values (with os_start pointing at OUR entry, which lands at
 * the same 0xFC0030), so anything that identifies a ROM by its header — Hatari's own sanity check
 * included — sees what it saw before.
 */
#ifndef TOS102US_ROMDEFS_H
#define TOS102US_ROMDEFS_H

/* The screen geometry is the MACHINE's, not the ROM's, so it is stated once for both builds here
 * and included rather than repeated (st_screen.h says why). */
#include "st_screen.h"

/* ---- where the ROM lives ------------------------------------------------------------------- */
#define ROM_BASE            0xFC0000        /* os_beg: the ST maps the OS ROM here               */
#define ROM_BYTES           0x30000         /* 192 KB — the size TOS 1.0x images are, exactly    */
#define ROM_END             (ROM_BASE + ROM_BYTES)

/* ---- the OS header, field by field (offsets from ROM_BASE) --------------------------------- */
#define OS_HEADER_BYTES     0x30            /* os_entry .. os_dosdate + the four TOS 1.02 fields */
#define OS_VERSION          0x0102          /* the BCD version word every TOS carries at +2      */
#define OS_ENTRY_OFFSET     0x30            /* where os_entry's bra.s lands = the reset PC       */
#define OS_START            (ROM_BASE + OS_ENTRY_OFFSET)
/* os_membot: the original's end of the OS's own RAM. Our stub owns no RAM below it, but the field
 * is what a program asks for the bottom of the TPA, so it keeps the original's value. */
#define OS_MEMBOT           0x8900
/* os_rsv1: the original repeats os_start here (measured 0x00FC0030). */
#define OS_RSV1             OS_START
#define OS_MUPB             0xFEFFF4        /* os_magic: the GEM memory-usage parameter block     */
#define OS_DATE_BCD         0x04221987      /* mmddyyyy, BCD — 1987-04-22                         */
/* os_conf: country (bits 15..1) and the video standard in bit 0. The US ROM reads 0x0000 —
 * country 0 (USA), NTSC. It is the ONE field that decides the machine's line rate; see
 * STUB_SYNC_MODE below, which derives the shifter value from it rather than restating it. */
#define OS_CONF             0x0000
#define OS_CONF_PAL_BIT     0x0001          /* set = PAL/50 Hz, clear = NTSC/60 Hz                */
/* os_dosdate: the same day in FAT12's packed form — (1987-1980)<<9 | 4<<5 | 22. */
#define OS_DOSDATE          0x0E96
/* The four longwords TOS 1.02 added after os_dosdate: pointers into the OS's own RAM that a program
 * may follow (p_root = the GEMDOS memory pool, pkbshift = the shift-key state, p_run = the current
 * process descriptor, and one reserved). Read out of the original; a stub with no GEMDOS has
 * nothing to point them at, so it emits the original's values and nothing follows them. */
#define OS_P_ROOT           0x00007E9C
#define OS_P_KBSHIFT        0x00000E61
#define OS_P_RUN            0x000087CE
#define OS_RSV2             0x00000000

/* The MUPB itself, at OS_MUPB. Three longwords: the magic TOS looks for, then the two GEM entry
 * points the original publishes (read out of the image: 87 65 43 21 / 00 00 ca 00 / 00 fd 9e ca). */
#define MUPB_MAGIC          0x87654321
#define MUPB_UI_START       0x0000CA00
#define MUPB_END_OS         0x00FD9ECA

/* ---- the machine the boot stub assumes ----------------------------------------------------- */
/* 1 MB of ST RAM. The stub does not size memory — it is a toolchain proof, not an OS — so the
 * screen address and the memory-controller value below are BOTH statements about `--memsize 1`,
 * and booting the stub on another size is out of its contract (README.md says so).            */
#define STUB_PHYSTOP        0x100000
#define STUB_SCREEN_BASE    0x078000        /* 256-byte aligned, 32,000 bytes clear of phystop    */
#define STUB_STACK_TOP      0x020000        /* well below the screen, well above the vector page  */

/* ---- the shifter and the memory controller ------------------------------------------------- */
#define MEMCTRL             0xFFFF8001
/* Bank 1 in bits 3..2, bank 0 in bits 1..0; 01 = 512 KB. Two of them is the 1 MB above. */
#define MEMCTRL_1MB         0x05
#define VIDEO_BASE_HIGH     0xFFFF8201      /* bits 23..16 of the screen address                  */
#define VIDEO_BASE_MID      0xFFFF8203      /* bits 15..8 — an STF has no low byte at all         */
#define SYNC_MODE           0xFFFF820A
#define SYNC_MODE_50HZ      0x02            /* PAL: 50 Hz, 313 scan lines                         */
#define SYNC_MODE_60HZ      0x00            /* NTSC: 60 Hz, 263 scan lines                        */
/* THE ORIGINAL ROM WRITES THIS REGISTER ON THE PAL BRANCH ONLY. At 0xFC009E it does
 * `btst #0` on os_conf's low byte and a `beq` jumps PAST the single `move.b #2,$ffff820a` at
 * 0xFC00AE, so a US ROM (OS_CONF bit 0 clear) leaves the shifter at the 60 Hz setting it came up
 * with. The stub WRITES that value rather than skipping the write — it installs no OS and takes
 * nothing on trust about how the machine powered on — but the value comes from OS_CONF, not from a
 * second constant that could be edited into disagreeing with the header the ROM is identified by.
 * Measured both ways in Hatari's debugger: derived, $ffff820a reads 00 and `info video` reports
 * 60 Hz; hard-coded to SYNC_MODE_50HZ it reads 02 and reports 50 Hz. */
#define STUB_SYNC_MODE      ((OS_CONF & OS_CONF_PAL_BIT) ? SYNC_MODE_50HZ : SYNC_MODE_60HZ)
#define PALETTE             0xFFFF8240      /* sixteen $0RGB words                                */
#define SHIFTER_RES         0xFFFF8260
#define SHIFTER_RES_LOW     0x00            /* 320x200, four bitplanes                            */

/* ---- the picture the boot stub paints ------------------------------------------------------ */
/* The unmistakable pattern: sixteen horizontal bands, one per pen. 200 does not divide by 16, so
 * the last band takes the remainder rather than the picture losing eight rows. */
#define BAND_COUNT          16
#define BAND_ROWS           (SCREEN_HEIGHT / BAND_COUNT)                    /* 12                 */

#endif /* TOS102US_ROMDEFS_H */
