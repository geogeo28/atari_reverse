/* boot/floppy.h — the names THE FLOPPY'S LOWER DRIVER is spelt in (`src/boot/floppy/`, D4 phase P4): the ROM's
 * [$fc173a, $fc1f08), its six entries, its RAM and the WD1772 / DMA words it writes. P4a ports the drive probe
 * ($fc173a) and the primitives it runs on: the common entry ($fc1c48), the select ($fc1e14), PSG port A's
 * read-modify-write ($fc1e60), the settled register accesses ($fc1e86..$fc1ea4) and their settle ($fc1eac), the type-I
 * command and its wait ($fc1db6), the force-interrupt ($fc1dfa), the restore ($fc1da0), the seek ($fc1d2e), the media-
 * change mode store ($fc1ef6) and the two exits ($fc1ccc / $fc1cda). The names that already exist stay where they are
 * (`addrs.h`: `SYSVAR_HZ_200`, `SYSVAR_FLOCK`, `FLOPPY_VBL_ENTERED` — the byte the common entry `st`s too —,
 * `MFP_GPIP`, `PSG_PORT_SELECT`, `PSG_PORT_DATA`,
 * `PSG_PORT_A`, `FDC_DMA_MODE`, `SR_IPL_MASK`; `boot/sysvars.h`: `SYSVAR_SEEKRATE`).
 *
 * ASSEMBLER-SAFE above the `__ASSEMBLER__` guard (plain integer `#define`s, as `addrs.h`). The Python side reads it with
 * `layouts.parse_constants` (`test/boot_floppy.py`), so a value is spelt once.
 *
 * WHERE IT IS LAID (rulings "ROM-window overlay" and "Own link rule", 2026-10-29; R-P4-2 "Jump at ROM entries",
 * 2026-11-02): the body over a COPY of the image's ROM bytes no run that lays it executes or reads — SINCE P4b the VDI's
 * GDP text `[$fcc400, $fcd400)` (rounded boxes, arcs, ellipses, wide lines, circles, the fill attributes and the arrows,
 * widened at P4c by R-P4c-1 "Widen to $fcd400": VDI code GEM's own init first opens a
 * workstation for, after gem_entry — every run that lays the driver, B6, the chain's B6, the driver's arrival and staged
 * rows, ends before; held by `test_boot_floppy.py`). P4a's 674 bytes fit Prtblk's text, P4b's 2.3 KB and P4c's 3.9 KB do not; and the span
 * stays in $fc0000..$fcffff ON PURPOSE: a return into our body that a dead frame keeps past gem_entry (R-P4-5's bytes)
 * holds the ROM's own high byte `$fc` there — over the desk's text ($fe....) the chain's gem_entry set grew a twelfth
 * byte, `$7511` (measured) — and LINKED THERE by its own Makefile rule (`build/bootfloppy/`); and at
 * each ported ROM entry a 6-byte `jmp` to its glue, laid over the ROM's own first instruction there, so every caller —
 * the XBIOS table, hdv_init's `jsr`, every harness answer keyed by the entry — reaches ours unchanged.
 */
#ifndef TOS102US_BOOT_FLOPPY_H
#define TOS102US_BOOT_FLOPPY_H

#define FLOPPY_LAID_AT            0xfcc400   /* the body's first byte, over the VDI's GDP text (P4b: Prtblk's 1 KB too small) */
#define FLOPPY_LAID_LIMIT         0xfcd400   /* ...4 KB of it (R-P4c-1 "Widen to $fcd400"): gdp_rbox's tail .. do_arrow, past
                                              * the launch twin's [$fcc000, $fcc27e), ending before init_wk at $fcd402 */

/* ---- the ROM's entries ([$fc173a, $fc1f08): the lower driver) ------------------------------------------------------ */
#define ROM_FLOPPY_PROBE          0xfc173a   /* hdv_init's per-drive probe: `jsr` at $fc0f82, 12(sp) the drive */
#define ROM_FLOPPY_FLOPRD         0xfc1782   /* XBIOS 8 — and the probe's end */
#define ROM_FLOPPY_LOWER_END      0xfc1f08   /* past `$fc1ef6`'s `rts`: the driver's last byte */
#define ROM_FLOPPY_FLOPWR         0xfc1858   /* XBIOS 9 — and Floprd's end (its error decode $fc1836 the last of it) */
#define ROM_FLOPPY_FLOPFMT        0xfc1916   /* XBIOS 10 — and Flopwr's end (its track builder and fill to Flopver) */
#define ROM_FLOPPY_FLOPVER        0xfc1ae2   /* XBIOS 19 ... */
#define ROM_FLOPPY_VBL            0xfc1bc4   /* ...its verify core ($fc1afe) ending here, at the floppy's VBL service */
#define ROM_FLOPPY_PRIMITIVES     0xfc1c48   /* the common entry: from here to the driver's end, the shared primitives */
#define ROM_FLOPPY_CRITICAL_CALL  0xfc07e8   /* `move.l etv_critic,-(sp) / rts`: the single-drive alert's call */
#define FLOPPY_ENTRY_JUMP_BYTES   6          /* `jmp abs.l`: the stub laid at a ported entry (R-P4-2) */

/* ---- its RAM --------------------------------------------------------------------------------------------------------- */
#define FLOPPY_RETRIES            0x9f6      /* word: the retries a transfer has left (2 at the common entry) */
#define FLOPPY_LAST_ACCESS        0x9fc      /* long per drive: `_hz_200` stamped on the way out */
#define FLOPPY_DESELECTED         0xa06      /* word: cleared by the select, set by the VBL's motor-off deselect */
#define FLOPPY_DRIVE              0xa08      /* word: the request's drive... */
#define FLOPPY_TRACK              0xa0a      /* ...its track... */
#define FLOPPY_SECTOR             0xa0c      /* ...its first sector... */
#define FLOPPY_SIDE               0xa0e      /* ...its side... */
#define FLOPPY_COUNT              0xa10      /* ...its sector count... */
#define FLOPPY_BUFFER             0xa12      /* ...and its buffer (long): the DMA address, bytes $a13 (hi) .. $a15 (lo) */
#define FLOPPY_FORMAT_SPT         0xa16      /* word: Flopfmt's sectors a track */
#define FLOPPY_FORMAT_INTERLEAVE  0xa18      /* word: ...its interleave (negative: the skew table's) */
#define FLOPPY_FORMAT_VIRGIN      0xa1a      /* word: ...the two bytes each data field is filled with */
#define FLOPPY_FORMAT_SKEW        0xa1c      /* long: ...the skew table's address */
#define FLOPPY_SELECT_SCRATCH     0xa20      /* byte the select clears; nothing in the driver reads it */
#define FLOPPY_DEFAULT_ERROR      0xa24      /* word: the entry's error (its D0), what an undecoded status reports */
#define FLOPPY_ERROR              0xa26      /* word: the error the error exit returns */
#define FLOPPY_SAVE_AREA          0xa28      /* `movem.l d3-d7/a3-a6`: the CALLER's registers, restored on the way out */
#define FLOPPY_RECORD_A           0xa4c      /* drive A:'s record: its track (word; negative = unknown) ... */
#define FLOPPY_RECORD_B           0xa50      /* ...and B:'s */
#define FLOPPY_RECORD_TRACK       0          /* word */
#define FLOPPY_RECORD_SEEK_RATE   2          /* word: `seekrate` copied in by the probe; its low 2 bits the step rate */
#define FLOPPY_MEDIA_MODE         0x755a     /* byte per drive: the media-change mode (1 maybe, 2 changed) */
#define FLOPPY_WP_SEEN            0x9fa      /* word: the write-protect latches or'd (the VBL's); -1 by the alert */
#define FLOPPY_SINGLE_DRIVE_LETTER 0x7dc4    /* word: the letter a one-drive machine's drive last stood for */
#define SYSVAR_NFLOPS             0x4a6      /* word: the drives hdv_init counted */

/* ---- the request: the caller's arguments, offsets from its first (Floprd's layout; the probe's caller pushes the same
 * shape: hdv_init $fc0f74) ----------------------------------------------------------------------------------------- */
#define FLOPPY_ARG_BUFFER         0          /* long */
#define FLOPPY_ARG_DRIVE          8          /* word (past the long the caller leaves unused: Floprd's filler) */
#define FLOPPY_ARG_SECTOR         10
#define FLOPPY_ARG_TRACK          12
#define FLOPPY_ARG_SIDE           14
#define FLOPPY_ARG_COUNT          16
/* ...and Flopfmt's own: buffer 0, the skew table 4, drive 8, sectors a track 10, track 12, side 14, interleave 16 (where the
 * common entry copies the count), the magic 18 (long), the virgin word 22 */
#define FLOPFMT_ARG_SKEW          4
#define FLOPFMT_ARG_SPT           10
#define FLOPFMT_ARG_INTERLEAVE    16
#define FLOPFMT_ARG_MAGIC         18
#define FLOPFMT_ARG_VIRGIN        22
#define FLOPFMT_MAGIC             0x87654321 /* `cmpi.l #$87654321,22(sp)`: anything else takes the error exit, stale */

/* ---- the entry's error codes ------------------------------------------------------------------------------------------ */
#define FLOPPY_PROBE_ERROR        (-1)       /* the probe's `moveq #-1,d0`: its default error */
#define FLOPPY_SEEK_ERROR         (-6)       /* `move.w #-6,$a26`: the seek's, set before every type-I seek */
#define FLOPPY_RETRIES_EACH       2          /* `move.w #2,$9f6` */
#define FLOPPY_MEDIA_MAYBE        1          /* `moveq #1,d0` at the error exit */
#define FLOPPY_UNKNOWN_TRACK      0xff00     /* the record's track while the head's place is not known */
#define FLOPPY_PROBE_RETRY_TRACK  10         /* `moveq #10,d7`: the seek a failed restore retries from */
#define FLOPPY_RECALIBRATE_TRACK  5          /* `move.w #5,d7`: the recalibrate's seek after its restore */
#define FLOPPY_GENERAL_ERROR      (-1)       /* `move.w #-1,$a26`: each sector's error before its read */
#define FLOPPY_TIMED_OUT          (-2)       /* `move.w #-2,$a26`: a read's wait timed out */
#define FLOPPY_CRC_ERROR          (-4)       /* the decode's: CRC */
#define FLOPPY_RECORD_NOT_FOUND   (-8)       /* ...record not found */
#define FLOPPY_READ_ERROR         (-11)      /* `moveq #-11,d0`: Floprd's and Flopver's own error */
#define FLOPPY_WRITE_PROTECTED    (-13)      /* ...write-protected */
#define FLOPPY_INSERT_DISK        (-17)      /* `move.w #-17,-(sp)`: the alert's etv_critic code */
#define FLOPPY_WRITE_ERROR        (-10)      /* `moveq #-10,d0`: Flopwr's own error, and the track builder's default */
#define FLOPPY_BAD_SECTORS        (-16)      /* Flopfmt's: its verify listed a sector */
#define FLOPPY_MEDIA_CHANGED      2          /* `moveq #2,d0` at $fc1ef6: a boot sector written, a track formatted */
#define FLOPPY_SECTOR_BYTES       512

/* ---- the DMA chip's mode words (`$ff8606`) and its register window (`$ff8604`) --------------------------------------- */
#define FDC_DMA_ACCESS            0xff8604   /* word: the FDC register (or the sector count) the mode selects */
#define FDC_DMA_ADDRESS_HI        0xff8609   /* the DMA address, bytes — written lo, mid, hi */
#define FDC_DMA_ADDRESS_MID       0xff860b
#define FDC_DMA_ADDRESS_LO        0xff860d
#define FDC_MODE_STATUS           0x80       /* the command / status register */
#define FDC_MODE_TRACK            0x82
#define FDC_MODE_SECTOR           0x84
#define FDC_MODE_DATA             0x86
#define FDC_MODE_SECTOR_COUNT     0x90       /* the DMA's sector count (read direction); toggling bit 8 resets the DMA */
#define FDC_MODE_WRITE            0x100      /* the write direction */
#define DMA_STATUS_NO_ERROR       1          /* `$ff8606` read, bit 0 */

/* ---- the WD1772's commands and status bits --------------------------------------------------------------------------- */
#define WD1772_RESTORE            0x00
#define WD1772_SEEK               0x10
#define WD1772_SEEK_VERIFY        0x14       /* `moveq #20,d6` */
#define WD1772_READ_SECTOR        0x80
#define WD1772_WRITE_SECTOR       0xa0
#define WD1772_WRITE_TRACK        0xf0
#define WD1772_WRITE_ERRORS       0x5c       /* `and.b #$5c,d0`: WP, RNF, CRC, lost data — after WP's own exit */
#define WD1772_FORMAT_ERRORS      0x44       /* `and.b #$44,d0`: WP, lost data */
#define FDC_FORMAT_COUNT          31         /* `moveq #31,d7`: the DMA's count for a track (more than its 6,250 bytes) */
#define WD1772_FORCE_INTERRUPT    0xd0
#define WD1772_STEP_RATE_MASK     3          /* the record's rate, or'd into a type-I command */
#define WD1772_STATUS_MOTOR       0x80
#define WD1772_STATUS_TRACK_00    0x04
#define WD1772_STATUS_WRITE_PROTECT 0x40
#define WD1772_STATUS_RECORD_NOT_FOUND 0x10
#define WD1772_STATUS_CRC_ERROR   0x08
#define WD1772_TYPE_II_ERRORS     0x1c       /* `and.b #$1c,d0`: RNF, CRC, lost data */
#define MFP_GPIP_FDC_INTRQ        0x20       /* GPIP bit 5: the FDC's interrupt line, LOW when a command is done */

/* ---- the waits: INSTRUCTION COUNTS, not time (`move.l #$40000,d7`; `#$60000` with the motor off) ---------------------- */
#define FDC_WAIT_MOTOR_ON         0x40000
#define FDC_WAIT_MOTOR_OFF        0x60000
#define FDC_SETTLE_DBF            32         /* `move.w #32,d7 / dbf d7,*` ($fc1eac): 33 iterations around an access */
#define FDC_FORCE_DBF             15         /* `move.w #15,d7 / dbf d7,*` ($fc1e06): after a force-interrupt */

/* ---- the PSG's port A: the drive and side selects, active low ---------------------------------------------------------- */
#define PORT_A_SELECT_BITS        7          /* bit 0 side (0 = side 1), bits 1/2 drive A/B */
#define PORT_A_KEPT_BITS          0xf8

/* ---- the track Flopfmt builds ($fc198c): its gaps and marks, each run a `dbf` of count - 1 ---------------------------- */
#define TRACK_GAP_BYTE            0x4e
#define TRACK_SYNC_BYTE           0x00
#define TRACK_MARK_PREFIX         0xf5       /* written as $A1 with a missing clock */
#define TRACK_ID_MARK             0xfe
#define TRACK_DATA_MARK           0xfb
#define TRACK_CRC_BYTES           0xf7       /* the FDC writes the two CRC bytes */
#define TRACK_SECTOR_SIZE_CODE    2          /* 512 bytes */
#define TRACK_GAP_FIRST           60         /* `moveq #59,d1` */
#define TRACK_SYNC_BYTES          12
#define TRACK_MARK_PREFIXES       3
#define TRACK_GAP_AFTER_ID        22
#define TRACK_GAP_AFTER_DATA      40
#define TRACK_GAP_LAST            1401       /* `move.w #1400,d1` */

#endif /* TOS102US_BOOT_FLOPPY_H */
