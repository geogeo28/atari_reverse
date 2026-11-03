/* THE FLOPPY'S LOWER DRIVER in C (D4 phase P4a: the drive probe and the primitives it runs on) — the ROM's
 * [$fc173a, $fc1f08), entered through `floppy_entry.S` (the glue: the caller's registers saved to $a28 and restored from
 * there, the last-access stamp, `flock` cleared) from a 6-byte `jmp` laid at each ported ROM entry (R-P4-2).
 *
 *   $fc173a  the probe: the drive's record (A: $a4c, B: $a50) given `seekrate`, its track cleared; the common entry;
 *            the drive selected, the track UNKNOWN; a restore — or, failing, a seek to 10 and a restore again
 *   $fc1c48  the common entry: the request copied in, `flock` taken, the retries set, the record chosen (where its
 *            track is unknown, found again: no probe reaches that arm — its record is cleared first; hdv_boot's Floprd
 *            with drive A: absent and B: present does, R-P4b-1)
 *   $fc1ccc  the exits: on an error the media marked MAYBE changed and `$a26` the result, else 0; either way the head
 *            sought to the record's track once more ($fc1cdc) before the glue's tail
 *
 * EVERY WAIT IS AN INSTRUCTION COUNT, NOT TIME (`include/boot/floppy.h`): the type-I wait counts down `$40000` (`$60000`
 * with the motor off) BEFORE each poll of GPIP bit 5, so a timeout is 262,143 polls (393,215) — the FDC model's ledger
 * counts them, and GCC compiles the loop to the ROM's own four instructions. THE SETTLE is the other count: 33 `dbf`s
 * before and after every `$ff8604` access, a delay the WD1772 needs and no surface but the cycles sees; C has no way to
 * say an empty loop that must run, so it is the ROM's own helper (`floppy_settle`, the glue), called as the ROM's
 * routines call it — the SECTOR_SUM precedent (`late.c`). The force-interrupt's 16 `dbf`s likewise (`dbf_delay`).
 *
 * THE REGISTERS — THE ROM'S CONTRACT, ALL OF IT OBSERVABLE (the BIOS / XBIOS dispatcher hands a caller D1, D2, A0-A2 as
 * the routine leaves them; hdv_init's run goes on with them): D1 and D2 keep the caller's upper bytes and take, in their
 * low byte, the port-A byte the last select WROTE and the one it READ (`port_a_new`, `port_a_old`: the ROM's `move.b`s
 * into them); A1 is the drive's record (`record`); A2 and A6 are never touched; A5 is the DMA's mode register
 * (`dma_mode`: the ROM keeps it in A6, `lea $ff8606,a6`, which GCC cannot take — A6 is its frame pointer) until the glue
 * restores it. D3-D7 / A3-A6 are the caller's, saved at $a28 by the glue's `movem` and restored from there: the Makefile
 * makes D3-D5 / A3-A4 call-used, so GCC saves NO REGISTER on the stack; it spills one long (the error result kept across
 * the exit's last seek), and the probe's depth is the ROM's, 20 bytes — the chain holds the BIOS stack byte for byte
 * below $74ff, 29 bytes under the probe's entry (design P4 §3).
 */
/* TARGET ONLY (the orchestrator's call under standing policy: no host twin — the differential cannot arm the FDC model,
 * R-D4-1); off target the file is empty, as `late.c` is — the host's sweeps compile every source. */
#ifndef RECREATE_HOST_DIFFERENTIAL
#include <stdint.h>

#include "addrs.h"
#include "hw.h"
#include "boot/sysvars.h"
#include "boot/floppy.h"

register uint32_t handed_d1 __asm__("d1");      /* the ROM's D1: port A's byte the last select wrote, or the error the
                                                 * decode chose (`$fc1836`) — what the caller is handed back */
register uint32_t handed_d2 __asm__("d2");      /* the ROM's D2: port A's byte the last select read */
register uint16_t fdc_command __asm__("d6");    /* the ROM's D6: the type-I command a wait issues */
register uint16_t fdc_status __asm__("d7");     /* the ROM's D7: the status the wait reads back */
register uint16_t *record __asm__("a1");
register uint16_t *bad_list __asm__("a2");      /* the ROM's A2: Flopver's cursor into its list of bad sectors */
register volatile uint16_t *dma_mode __asm__("a5");

#define LOW_BYTE 0xffu

/* RAM AT ITS OWN ADDRESS, as `late.c` reaches it (target only: absolute addressing, as the ROM's `d16(a5)` with A5 0). */
static inline uint8_t *ram8(uint32_t at)
{
    return (uint8_t *)at;
}

static inline uint16_t *ram16(uint32_t at)
{
    return (uint16_t *)at;
}

static inline uint32_t *ram32(uint32_t at)
{
    return (uint32_t *)at;
}

static inline uint16_t arg16(const uint8_t *args, uint32_t offset)
{
    return *(const uint16_t *)(args + offset);
}

/* `bsr $fc1eac`: the ROM's own settle (`floppy_settle`), around every access of the FDC's registers. */
static inline void settle(void)
{
    __asm__ volatile ("bsr.w floppy_settle" : : : "memory");
}

/* `move.w #<count>,d7 / dbf d7,*`: a delay of `count` + 1 iterations that nothing but the cycles sees. */
static inline void dbf_delay(uint16_t count)
{
    uint16_t left;
    __asm__ volatile ("move.w %1,%0\n"
                      "1:\tdbf %0,1b"
                      : "=&d"(left) : "i"(count));
}

/* `$fc1e86` / `$fc1e90`: a settled write of the register the mode selects. */
static inline void fdc_write(uint16_t value)
{
    settle();
    hw_write16(FDC_DMA_ACCESS, value);
    settle();
}

/* `$fc1e9a` / `$fc1ea4`: a settled read of it. */
static inline uint16_t fdc_read(void)
{
    settle();
    uint16_t value = io_read16(FDC_DMA_ACCESS);
    settle();
    return value;
}

/* `$fc1e60`: PSG port A's drive and side selects, read-modify-written with the interrupts masked. */
static inline void select_port_a(uint8_t selects)
{
    uint16_t interrupted;
    __asm__ volatile ("move.w %%sr,%0\n\t"
                      "ori.w %1,%%sr"
                      : "=d"(interrupted) : "i"(SR_IPL_MASK) : "memory");
    hw_write8(PSG_PORT_SELECT, PSG_PORT_A);
    uint8_t held = io_read8(PSG_PORT_SELECT);
    uint8_t merged = (held & PORT_A_KEPT_BITS) | selects;
    handed_d2 = (handed_d2 & ~LOW_BYTE) | held;
    handed_d1 = (handed_d1 & ~LOW_BYTE) | merged;
    hw_write8(PSG_PORT_DATA, merged);
    __asm__ volatile ("move.w %0,%%sr" : : "d"(interrupted) : "memory", "cc");
}

/* `$fc1dfa`: force-interrupt, the delay, the status read back. */
static inline uint16_t force_interrupt(void)
{
    *dma_mode = FDC_MODE_STATUS;
    fdc_write(WD1772_FORCE_INTERRUPT);
    dbf_delay(FDC_FORCE_DBF);
    return fdc_read();
}

/* `$fc1db6`: the type-I command in `fdc_command`, the record's step rate or'd in, waited for — 0 done, or 1 timed out
 * and forced; the status read back in `fdc_status` either way. The count down comes BEFORE each poll. */
static int type_one(void)
{
    fdc_command |= record[FLOPPY_RECORD_SEEK_RATE / sizeof *record] & WD1772_STEP_RATE_MASK;
    uint32_t budget = FDC_WAIT_MOTOR_ON;
    *dma_mode = FDC_MODE_STATUS;
    if (!(fdc_read() & WD1772_STATUS_MOTOR))
        budget = FDC_WAIT_MOTOR_OFF;
    fdc_write(fdc_command);
    while (--budget != 0) {
        if (!(hw_read8(MFP_GPIP) & MFP_GPIP_FDC_INTRQ)) {
            fdc_status = fdc_read();
            return 0;
        }
    }
    fdc_status = force_interrupt();
    return 1;
}

/* `$fc1da0`: a restore — 0 where it ends at track 0 (the record's track then 0). */
static int restore(void)
{
    fdc_command = WD1772_RESTORE;
    if (type_one() || !(fdc_status & WD1772_STATUS_TRACK_00))
        return 1;
    record[FLOPPY_RECORD_TRACK] = 0;
    return 0;
}

/* `$fc1d2e`: a seek to `track` (no verify), the error made the seek's first. */
static inline int seek(uint16_t track)
{
    *ram16(FLOPPY_ERROR) = (uint16_t)FLOPPY_SEEK_ERROR;
    *dma_mode = FDC_MODE_DATA;
    fdc_write(track);
    fdc_command = WD1772_SEEK;
    return type_one();
}

/* `$fc1e3c`: the sector register and the DMA address (written lo, mid, hi) from the request. */
static inline void set_sector_and_address(void)
{
    *dma_mode = FDC_MODE_SECTOR;
    fdc_write(*ram16(FLOPPY_SECTOR));
    const uint8_t *buffer = ram8(FLOPPY_BUFFER);
    hw_write8(FDC_DMA_ADDRESS_LO, buffer[3]);
    hw_write8(FDC_DMA_ADDRESS_MID, buffer[2]);
    hw_write8(FDC_DMA_ADDRESS_HI, buffer[1]);
}

/* `$fc1e14`: the request's drive and side selected, the track register the record's, then `$fc1e3c`. */
static void select_drive(void)
{
    *ram16(FLOPPY_DESELECTED) = 0;
    uint8_t drive_bit = (uint8_t)((uint8_t)(*ram16(FLOPPY_DRIVE) + 1) << 1);
    select_port_a((uint8_t)((drive_bit | *ram16(FLOPPY_SIDE)) ^ PORT_A_SELECT_BITS) & PORT_A_SELECT_BITS);
    *dma_mode = FDC_MODE_TRACK;
    fdc_write(record[FLOPPY_RECORD_TRACK]);
    *ram8(FLOPPY_SELECT_SCRATCH) = 0;
    set_sector_and_address();
}

/* `$fc1c48`: the request copied in, `flock` taken, the record chosen — and where its track is UNKNOWN (negative: the probe
 * that failed left `$ff00`), found again ($fc1caa..$fc1cca): select, restore; else a seek to 10 and a restore; else the
 * track unknown still. The probe never takes that arm (it clears the record's track first); hdv_boot's Floprd on a machine
 * whose drive A: is absent and B: present does (ruling R-P4b-1: the one arm of any run that reaches it). */
static inline void common_entry(const uint8_t *args, int16_t error)
{
    dma_mode = (volatile uint16_t *)FDC_DMA_MODE;
    *ram8(FLOPPY_VBL_ENTERED) = 0xff;
    *ram16(FLOPPY_DEFAULT_ERROR) = (uint16_t)error;
    *ram16(FLOPPY_ERROR) = (uint16_t)error;
    *ram16(SYSVAR_FLOCK) = 1;
    *ram32(FLOPPY_BUFFER) = *(const uint32_t *)(args + FLOPPY_ARG_BUFFER);
    *ram16(FLOPPY_DRIVE) = arg16(args, FLOPPY_ARG_DRIVE);
    *ram16(FLOPPY_SECTOR) = arg16(args, FLOPPY_ARG_SECTOR);
    *ram16(FLOPPY_TRACK) = arg16(args, FLOPPY_ARG_TRACK);
    *ram16(FLOPPY_SIDE) = arg16(args, FLOPPY_ARG_SIDE);
    *ram16(FLOPPY_COUNT) = arg16(args, FLOPPY_ARG_COUNT);
    *ram16(FLOPPY_RETRIES) = FLOPPY_RETRIES_EACH;
    record = *ram16(FLOPPY_DRIVE) ? ram16(FLOPPY_RECORD_B) : ram16(FLOPPY_RECORD_A);
    if ((int16_t)record[FLOPPY_RECORD_TRACK] >= 0)
        return;
    select_drive();
    record[FLOPPY_RECORD_TRACK] = 0;
    if (!restore())
        return;
    if (!seek(FLOPPY_PROBE_RETRY_TRACK) && !restore())
        return;
    record[FLOPPY_RECORD_TRACK] = FLOPPY_UNKNOWN_TRACK;
}

/* `$fc1cdc`: either exit's last seek, to the record's track — then the glue's tail. */
static inline uint32_t leave_with(uint32_t result)
{
    *dma_mode = FDC_MODE_DATA;
    fdc_write(record[FLOPPY_RECORD_TRACK]);
    fdc_command = WD1772_SEEK;
    type_one();
    return result;
}

/* `$fc1ccc`: the error exit — the media marked maybe changed (`$fc1ef6`), `$a26` the result. */
static inline uint32_t leave_with_the_error(void)
{
    ram8(FLOPPY_MEDIA_MODE)[(int16_t)*ram16(FLOPPY_DRIVE)] = FLOPPY_MEDIA_MAYBE;
    return leave_with((uint32_t)(int32_t)(int16_t)*ram16(FLOPPY_ERROR));
}

/* `$fc173a`: hdv_init's probe of one drive (the arguments at A0, laid there by the glue). */
uint32_t floppy_probe(void)
{
    register const uint8_t *args_in_a0 __asm__("a0");
    __asm__ ("" : "=a"(args_in_a0));       /* the glue's `lea 4(sp),a0`: the caller's arguments, as they stand */
    const uint8_t *args = args_in_a0;
    record = arg16(args, FLOPPY_ARG_DRIVE) ? ram16(FLOPPY_RECORD_B) : ram16(FLOPPY_RECORD_A);
    record[FLOPPY_RECORD_SEEK_RATE / sizeof *record] = *ram16(SYSVAR_SEEKRATE);
    record[FLOPPY_RECORD_TRACK] = 0;
    common_entry(args, FLOPPY_PROBE_ERROR);
    select_drive();
    record[FLOPPY_RECORD_TRACK] = FLOPPY_UNKNOWN_TRACK;
    if (!restore())
        return leave_with(0);
    if (seek(FLOPPY_PROBE_RETRY_TRACK) || restore())
        return leave_with_the_error();
    return leave_with(0);
}

/* ---- P4b: the read side ------------------------------------------------------------------------------------------------ */

/* `$fc1d7a`: a seek WITH verify to the request's track, the error the seek's first — 0 where the head is there and its ID
 * read clean (the record's track then the request's), else nonzero: the wait timed out, or record-not-found / CRC. */
static int seek_verify(void)
{
    *ram16(FLOPPY_ERROR) = (uint16_t)FLOPPY_SEEK_ERROR;
    *dma_mode = FDC_MODE_DATA;
    fdc_write(*ram16(FLOPPY_TRACK));
    fdc_command = WD1772_SEEK_VERIFY;
    if (type_one())
        return 1;
    record[FLOPPY_RECORD_TRACK] = *ram16(FLOPPY_TRACK);
    return fdc_status & (WD1772_STATUS_RECORD_NOT_FOUND | WD1772_STATUS_CRC_ERROR);
}

/* `$fc1d46`: the second-last retry's recalibrate — a restore, the track register 0, a seek to 5, then the seek-verify; its
 * result unread (Floprd and Flopver retry whatever it found). */
static void recalibrate(void)
{
    *ram16(FLOPPY_ERROR) = (uint16_t)FLOPPY_SEEK_ERROR;
    if (restore())
        return;
    record[FLOPPY_RECORD_TRACK] = 0;
    *dma_mode = FDC_MODE_TRACK;
    fdc_write(0);
    *dma_mode = FDC_MODE_DATA;
    fdc_write(FLOPPY_RECALIBRATE_TRACK);
    fdc_command = WD1772_SEEK;
    if (type_one())
        return;
    record[FLOPPY_RECORD_TRACK] = FLOPPY_RECALIBRATE_TRACK;
    seek_verify();
}

/* `$fc1836`: a type-II status decoded into the error the exit returns, D1 the ROM's register for it — write-protect -13,
 * record-not-found -8, CRC -4, else the entry's own (`$a24`, moved over the CRC's `moveq`: D1's high word stays -1). */
static void decode_status(uint16_t status)
{
    if (status & WD1772_STATUS_WRITE_PROTECT)
        handed_d1 = (uint32_t)FLOPPY_WRITE_PROTECTED;
    else if (status & WD1772_STATUS_RECORD_NOT_FOUND)
        handed_d1 = (uint32_t)FLOPPY_RECORD_NOT_FOUND;
    else if (status & WD1772_STATUS_CRC_ERROR)
        handed_d1 = (uint32_t)FLOPPY_CRC_ERROR;
    else
        handed_d1 = ((uint32_t)FLOPPY_CRC_ERROR & ~0xffffu) | *ram16(FLOPPY_DEFAULT_ERROR);
    *ram16(FLOPPY_ERROR) = (uint16_t)handed_d1;
}

/* One sector read through the DMA ($fc17a0..$fc17f8, Flopver's $fc1b3a..$fc1b8c): the DMA reset and its count 1, the read
 * command, the wait — the POLL BEFORE the count down here, 262,144 polls to a timeout — then the DMA's status and the
 * FDC's. 0 done; else FLOPPY_TRANSFER_TIMED_OUT (forced) or the FDC's status (the DMA's error bit as 0). `settled_count`:
 * Flopver writes the count through the settled write, Floprd straight ($fc17ac: `move.w #1,$ff8604`). */
#define FLOPPY_TRANSFER_TIMED_OUT 0x10000u
#define FLOPPY_TRANSFER_READ      0x20000u   /* (or'd over a status read back: a read, whatever its status) */
static uint32_t read_one_sector(int settled_count)
{
    *dma_mode = FDC_MODE_SECTOR_COUNT;
    *dma_mode = FDC_MODE_SECTOR_COUNT | FDC_MODE_WRITE;
    *dma_mode = FDC_MODE_SECTOR_COUNT;
    if (settled_count)
        fdc_write(1);
    else
        hw_write16(FDC_DMA_ACCESS, 1);
    *dma_mode = FDC_MODE_STATUS;
    fdc_write(WD1772_READ_SECTOR);
    uint32_t budget = FDC_WAIT_MOTOR_ON;
    do {
        if (!(hw_read8(MFP_GPIP) & MFP_GPIP_FDC_INTRQ)) {
            *dma_mode = FDC_MODE_SECTOR_COUNT;
            if (!(*dma_mode & DMA_STATUS_NO_ERROR))
                return 0;           /* (the ROM retries on a DMA error with the status unread: a zero status, retried) */
            *dma_mode = FDC_MODE_STATUS;
            return fdc_read() | FLOPPY_TRANSFER_READ;
        }
    } while (--budget != 0);
    fdc_status = force_interrupt();
    return FLOPPY_TRANSFER_TIMED_OUT;
}

/* The retry rule both readers share ($fc181e / $fc1baa): the second-last retry recalibrates first; 0 while retries are
 * left (`$9f6` decremented, still >= 0). */
static int another_try(void)
{
    if (*ram16(FLOPPY_RETRIES) == 1)
        recalibrate();
    return (int16_t)--*ram16(FLOPPY_RETRIES) >= 0;
}

/* `$fc1782`: XBIOS 8 — `count` sectors from (`track`, `side`, `sector`) into `buffer`, one at a time; each sector's
 * failure retried from the select, the error the last decoded (or the seek's, or -2 a timeout). */
uint32_t floppy_floprd(void)
{
    register const uint8_t *args_in_a0 __asm__("a0");
    __asm__ ("" : "=a"(args_in_a0));
    common_entry(args_in_a0, FLOPPY_READ_ERROR);       /* (the single-drive alert ran first, in the glue) */
    for (;;) {
        select_drive();
        if (!seek_verify()) {
            for (;;) {
                *ram16(FLOPPY_ERROR) = (uint16_t)FLOPPY_GENERAL_ERROR;
                uint32_t read = read_one_sector(0);
                if (read == FLOPPY_TRANSFER_TIMED_OUT) {
                    *ram16(FLOPPY_ERROR) = (uint16_t)FLOPPY_TIMED_OUT;
                    break;
                }
                if (!read)
                    break;
                if ((uint8_t)read & WD1772_TYPE_II_ERRORS) {
                    decode_status((uint8_t)read & WD1772_TYPE_II_ERRORS);
                    break;
                }
                *ram16(FLOPPY_RETRIES) = FLOPPY_RETRIES_EACH;
                ++*ram16(FLOPPY_SECTOR);
                *ram32(FLOPPY_BUFFER) += FLOPPY_SECTOR_BYTES;
                if (!--*ram16(FLOPPY_COUNT))
                    return leave_with(0);
                set_sector_and_address();
            }
        }
        if (!another_try())
            return leave_with_the_error();
    }
}

/* `$fc1afe`: the verify core — each sector of the request read into the buffer past its first 512 bytes, retried as
 * Floprd's from the DMA address (no reselect); one that exhausts its retries LISTED at the buffer (A2 its cursor); the
 * list ended by 0, the buffer given back. */
static void verify_sectors(void)
{
    *ram16(FLOPPY_DEFAULT_ERROR) = (uint16_t)FLOPPY_READ_ERROR;
    bad_list = (uint16_t *)*ram32(FLOPPY_BUFFER);
    *ram32(FLOPPY_BUFFER) += FLOPPY_SECTOR_BYTES;
    do {
        *ram16(FLOPPY_RETRIES) = FLOPPY_RETRIES_EACH;
        *dma_mode = FDC_MODE_SECTOR;
        fdc_write(*ram16(FLOPPY_SECTOR));
        for (;;) {
            const uint8_t *buffer = ram8(FLOPPY_BUFFER);
            hw_write8(FDC_DMA_ADDRESS_LO, buffer[3]);
            hw_write8(FDC_DMA_ADDRESS_MID, buffer[2]);
            hw_write8(FDC_DMA_ADDRESS_HI, buffer[1]);
            uint32_t read = read_one_sector(1);
            if (read != FLOPPY_TRANSFER_TIMED_OUT && read) {
                decode_status((uint8_t)read);
                if (!((uint8_t)read & WD1772_TYPE_II_ERRORS))
                    break;
            }
            if (!another_try()) {
                *bad_list++ = *ram16(FLOPPY_SECTOR);
                break;
            }
        }
        ++*ram16(FLOPPY_SECTOR);
    } while (--*ram16(FLOPPY_COUNT));
    *ram32(FLOPPY_BUFFER) -= FLOPPY_SECTOR_BYTES;
    *bad_list = 0;
}

/* `$fc1ae2`: XBIOS 19 — the request's sectors verified (`verify_sectors`): 0 whatever it listed; the seek-verify's error
 * where the head cannot get there. */
uint32_t floppy_flopver(void)
{
    register const uint8_t *args_in_a0 __asm__("a0");
    __asm__ ("" : "=a"(args_in_a0));
    common_entry(args_in_a0, FLOPPY_READ_ERROR);       /* (the single-drive alert ran first, in the glue) */
    select_drive();
    if (seek_verify())
        return leave_with_the_error();
    verify_sectors();
    return leave_with(0);
}

#endif /* RECREATE_HOST_DIFFERENTIAL */
