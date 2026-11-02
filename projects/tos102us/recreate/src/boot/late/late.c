/* BOOT B6 — the boot's interrupt-enabled late slice in C, [$fc0452, $fc047a): after the display (B5's), before the
 * AUTO runner and the shell's launch (B4's).
 *
 *   $fc0452  the interrupts opened (`move #$2300,sr`); the cartridge's hooks with D0 = 1 (`$fc0646`)
 *   $fc045c  GEMDOS's disk buffers ($fc4a9e): two lists of two BCBs, each empty, over four sector buffers, their heads
 *            in _bufl; GEMDOS's own init (`$fc4e5e`); the boot drive made the current one (Dsetdrv, `$fc6cc0`)
 *   $fc0460  the DOS date seeded from the OS header's; the Mega ST's clock asked for the date and time ($fc4be8)
 *   $fc046e  THE FLOPPY'S BOOT ($fc053c): the cartridge's hooks with D0 = 3; hdv_boot; its sector run if it answers 0
 *   $fc0472  THE ACSI'S BOOT ($fc0558): for each of the eight targets, its first sector read to _dskbufp; run where
 *            its 256 words sum to $1234
 *   $fc0476  THE RESET-RESIDENT PROGRAMS ($fc0e56): from phystop down to $400 a page at a time, each page marked
 *            $12123456, holding its own address and summing to $5678 is called at its offset 8
 *   $fc047a  on to `tst.w _cmdload` (B4's)
 *
 * THE ROM'S ROUTINES IT CALLS ARE THE ROM'S, ON BOTH SHORES, IN PLACE: the cartridge's hooks (the boot's, unported),
 * GEMDOS's init and its Dsetdrv (GEMDOS stays the ROM's in the boot: the orchestrator's standing call), hdv_boot (the
 * floppy driver's, unported: D4), the clock's probe and read (the BIOS's; the probe answered at its entry, R-B4-2), the
 * ACSI's sector read (the boot's; answered at its entry "no device", ruling D3). Each is called as the ROM calls it,
 * with the registers the ROM's slice hands it. The code a boot finds — a boot sector, an ACSI sector, a reset-resident
 * program — is called the ROM's way and is FOREIGN (D12 open): no run of the slice reaches one.
 *
 * THE REGISTERS THIS FILE MAY NOT TOUCH: D2-D7 and A2-A6 (the Makefile compiles it with them fixed) — the ROM's
 * routines clobber them freely and the ROM's slice hands its continuation whatever they left, so the C holds nothing
 * there and saves nothing there (B5's rule). ONE IS NAMED: D7, the ACSI's target, which the ROM's sector read takes
 * in D7 and the ROM's loop steps in place — bound to D7 here, so the loop leaves D7 as the ROM's does.
 */
/* TARGET ONLY: its own rule links it at LATE_LAID_AT; it is a run of calls into the ROM with nothing of its own on the
 * host's side to call them, so off target the file is empty — the host's sweeps compile every source. */
#ifndef RECREATE_HOST_DIFFERENTIAL
#include <stdint.h>

#include "machine.h"
#include "addrs.h"
#include "gemdos/fs.h"
#include "boot/head.h"
#include "boot/sysvars.h"
#include "boot/hwinit.h"
#include "boot/launch.h"
#include "boot/late.h"

/* RAM AT ITS OWN ADDRESS: this file is linked for the target alone (no host twin hands it an image), so a system
 * variable is reached where it lies — absolute addressing, as the ROM's own code reaches it. Through `target_image()`
 * every address past $7fff became an indexed store off a register holding 0 (measured: `move.l #imm,0(a1,d0.l)` after
 * a `move.l #addr,d0`, and the 0 kept on the stack across every call). */
static inline uint8_t *ram(uint32_t at)
{
    return (uint8_t *)at;
}

/* What a call into the ROM may leave changed that the compiler could hold: the scratch registers, the flags, memory. */
#define ROM_CALL_CLOBBERS "d0", "d1", "a0", "a1", "cc", "memory"

/* `moveq #<bit>,d0 / bsr $fc0646`: the cartridge's hooks, the init bit in D0. */
static inline void rom_cartridge_hooks(uint32_t bit)
{
    register uint32_t init_bit __asm__("d0") = bit;

    __asm__ volatile ("jsr (%c1).l" : "+d"(init_bit) : "i"(ROM_CARTRIDGE_HOOKS) : "d1", "a0", "a1", "cc", "memory");
}

/* `bsr $fc4a9e / link a6,#-4 / ... / jsr $fc4e5e / move.w _bootdev,(sp) / jsr $fc6cc0`: GEMDOS's own init, then
 * Dsetdrv(_bootdev) — Alcyon's call, the word in the frame's one local — BOTH CALLED AT THE ROM'S DEPTH, under the
 * `bsr`'s return and the `link`'s frame (`GEMDOS_BUFFERS_FRAME_BYTES`): every BIOS call GEMDOS makes frames its
 * caller's registers below savptr, A6 and SP among them, and the last of those frames outlives the slice (measured:
 * called from no frame, the longwords at $92c and $930 — A6 and SP — were apart from the ROM's at $fc047a). */
static inline void rom_gemdos_init_and_boot_drive(void)
{
    __asm__ volatile ("lea -%c0(%%sp),%%sp\n\t"
                      "jsr (%c1).l\n\t"
                      "move.w (%c2).l,(%%sp)\n\t"
                      "jsr (%c3).l\n\t"
                      "lea %c0(%%sp),%%sp"
                      : : "i"(GEMDOS_BUFFERS_FRAME_BYTES), "i"(ROM_GEMDOS_INIT), "i"(SYSVAR_BOOTDEV), "i"(GEMDOS_DSETDRV)
                      : ROM_CALL_CLOBBERS);
}

/* `bsr $fc4c44`: the clock as one longword, the DOS date high and the time low (RTC_NO_STAMP: none read). */
static inline uint32_t rom_rtc_read(void)
{
    register uint32_t stamp __asm__("d0");

    __asm__ volatile ("jsr (%c1).l" : "=d"(stamp) : "i"(ROM_RTC_READ) : "d1", "a0", "a1", "cc", "memory");
    return stamp;
}

/* `movea.l hdv_boot,a0 / jsr (a0)`: the floppy driver's boot — 0 where the boot sector it read is executable. */
static inline uint16_t rom_hdv_boot(void)
{
    register uint32_t answer __asm__("d0");

    __asm__ volatile ("movea.l (%c1).l,%%a0\n\t"
                      "jsr (%%a0)"
                      : "=d"(answer) : "i"(SYSVAR_HDV_BOOT) : "d1", "a0", "a1", "cc", "memory");
    return answer;
}

/* `lea <entry>,a0 / jsr (a0)`: FOREIGN CODE the boot found at a fixed address (the floppy's boot sector). */
static inline void foreign_code_at(uint32_t entry)
{
    __asm__ volatile ("lea (%c0).l,%%a0\n\t"
                      "jsr (%%a0)"
                      : : "i"(entry) : ROM_CALL_CLOBBERS);
}

/* `movea.l <pointer>,a0 / jsr (a0)`: FOREIGN CODE the boot found where a system variable points (the ACSI's sector). */
static inline void foreign_code_through(uint32_t pointer)
{
    __asm__ volatile ("movea.l (%c0).l,%%a0\n\t"
                      "jsr (%%a0)"
                      : : "i"(pointer) : ROM_CALL_CLOBBERS);
}

/* `move.l a0,-(sp) / jsr 8(a0) / movea.l (sp)+,a0`: a reset-resident program FOUND (foreign code), called at its
 * entry with its page in A0, the page kept on the stack across it as the ROM keeps it. */
static inline uint32_t call_resident_program(uint32_t page)
{
    register uint32_t page_in_a0 __asm__("a0") = page;

    __asm__ volatile ("move.l %0,-(%%sp)\n\t"
                      "jsr %c1(%0)\n\t"
                      "movea.l (%%sp)+,%0"
                      : "+a"(page_in_a0) : "i"(RESIDENT_ENTRY) : "d0", "d1", "a1", "cc", "memory");
    return page_in_a0;
}

/* THE TWO SECTOR SUMS IN THE ROM'S OWN REGISTERS: the sum in D0, the `dbf` count in D1's low word (left at -1), the
 * cursor advanced — `move.w #255,d1 / addw (an)+,d0 / dbf d1` — D0 cleared first as each routine clears it: `moveq #0`
 * (the ACSI's, the whole long) or `clr.w` (the reset-resident scan's, its low word). WHY NOT C: both registers outlive
 * the loop (the slice hands them to `$fc047a`), and GCC kept the sum in D1 and the count in D0, behind a `subq / bmi`
 * guard (review RB6's F1, measured on a page with the mark and a wrong sum: D0 and D1 swapped at `$fc047a`). */
#define SECTOR_SUM(sector, clear_d0)                                                                                   \
    ({                                                                                                                 \
        register uint32_t sum_ __asm__("d0");                                                                          \
        register uint32_t count_ __asm__("d1");                                                                        \
        const uint8_t *cursor_ = (sector);                                                                             \
                                                                                                                       \
        __asm__ ("" : "=d"(sum_), "=d"(count_));    /* the registers as they stand: the word writes keep the rest */   \
        __asm__ volatile (clear_d0 "\n\t"                                                                             \
                          "move.w %3,%1\n"                                                                             \
                          "1:\taddw (%2)+,%0\n\t"                                                                    \
                          "dbf %1,1b"                                                                                  \
                          : "+d"(sum_), "+d"(count_), "+a"(cursor_) : "i"(BOOT_SECTOR_WORDS - 1) : "cc", "memory");    \
        (uint16_t)sum_;                                                                                                \
    })
#define CLEAR_D0_LONG "moveq #0,%0"
#define CLEAR_D0_WORD "clr.w %0"

/* $fc4a9e — one of GEMDOS's two buffer lists: its two BCBs empty and linked, their sector buffers, the list's head. */
static inline void lay_bcb_list(uint32_t list)
{
    uint32_t first = BOOT_BCB_FIRST + list * BOOT_BCBS_PER_LIST * BCB_BYTES;
    uint32_t second = first + BCB_BYTES;
    uint32_t buffer = BOOT_SECTOR_BUFFER_FIRST + list * BOOT_BCBS_PER_LIST * BOOT_SECTOR_BYTES;

    wr32(ram(first + BCB_LINK), second);
    wr16(ram(first + BCB_BUFDRV), BCB_EMPTY);
    wr16(ram(second + BCB_BUFDRV), BCB_EMPTY);
    wr32(ram(first + BCB_BUFR), buffer);
    wr32(ram(second + BCB_BUFR), buffer + BOOT_SECTOR_BYTES);
    wr32(ram(SYSVAR_BUFL + list * SYSVAR_BUFL_ENTRY_BYTES), first);
}

/* $fc4a9e — GEMDOS's disk buffers laid, its init, the boot drive made current. */
static inline void boot_gemdos(void)
{
    lay_bcb_list(0);
    lay_bcb_list(1);
    rom_gemdos_init_and_boot_drive();
}

/* $fc4be8 — the DOS date and time from the Mega ST's clock, where there is one and it reads. */
static inline void boot_clock(void)
{
    uint32_t stamp;

    __asm__ goto ("jsr (%c0).l\n\t"
                   "bcs %l[absent]"
                   : : "i"(BIOS_RTC_PROBE) : ROM_CALL_CLOBBERS : absent);
    stamp = rom_rtc_read();
    if (stamp != RTC_NO_STAMP) {
        wr16(ram(GEMDOS_TIME), (uint16_t)stamp);
        wr16(ram(GEMDOS_DATE), (uint16_t)(stamp >> 16));
    }
absent:;
}

/* $fc053c — the floppy's boot: the hooks with 3, hdv_boot, and the boot sector it read run where it answers 0. */
static inline void boot_floppy(void)
{
    rom_cartridge_hooks(CARTRIDGE_HOOK_FLOPPY_BOOT);
    if (rom_hdv_boot() == 0)
        foreign_code_at(BOOT_DISK_BUFFER);
}

/* $fc0558 — the ACSI's boot: each target's first sector read to _dskbufp (`$fc0586`, the target in D7: Z set = read)
 * and run where it sums to BOOT_EXECUTABLE_SUM. */
static inline void boot_acsi(void)
{
    register uint8_t target __asm__("d7");

    __asm__ ("moveq #0,%0" : "=d"(target));     /* the WHOLE register cleared, as the ROM's `moveq #0,d7` */

    do {
        __asm__ goto ("jsr (%c1).l\n\t"
                      "bne %l[unread]"
                      : : "d"(target), "i"(ROM_ACSI_READ_BOOT_SECTOR) : ROM_CALL_CLOBBERS : unread);
        if (SECTOR_SUM(ram(be32(ram(SYSVAR_DSKBUFP))), CLEAR_D0_LONG) == BOOT_EXECUTABLE_SUM)
            foreign_code_through(SYSVAR_DSKBUFP);
unread:
        target += ACSI_TARGET_STEP;
    } while (target);
}

/* Does the page at `page` hold a reset-resident program: its mark, its own address, its sum? */
static inline int resident_program_at(uint32_t page)
{
    return be32(ram(page)) == RESIDENT_MAGIC && be32(ram(page + RESIDENT_SELF)) == page
           && SECTOR_SUM(ram(page), CLEAR_D0_WORD) == RESIDENT_SUM;
}

/* $fc0e56 — the reset-resident programs, from phystop down: each found is called at its entry. The page steps down
 * before it is compared, as the ROM's `suba.w` comes before its `cmpa.l` (the barrier: without it GCC compared the
 * page before the step, in a second address register — A1 left phystop where the ROM's leaves it untouched). */
static inline void boot_reset_resident(void)
{
    const uint8_t *page = ram(be32(ram(SYSVAR_PHYSTOP)));

    for (;;) {
        page -= RESIDENT_PAGE_BYTES;
        CURSOR_BARRIER(page);
        if (page == ram(RESIDENT_SCAN_FLOOR))
            return;
        if (resident_program_at((uint32_t)page))
            page = ram(call_resident_program((uint32_t)page));
    }
}

/* $fc0452 — entered where B5's slice ends, on the BIOS's stack as the ROM's boot leaves it. */
__attribute__((noreturn)) void boot_late_entry(void)
{
    __asm__ volatile ("move.w %0,%%sr" : : "i"(BOOT_SR_INTERRUPTS_OPEN) : "cc", "memory");
    rom_cartridge_hooks(CARTRIDGE_HOOK_INTERRUPTS);
    boot_gemdos();
    wr16(ram(GEMDOS_DATE), be16(ram(ROM_OS_HEADER + OS_HEADER_DOSDATE)));
    boot_clock();
    boot_floppy();
    boot_acsi();
    boot_reset_resident();
    __asm__ volatile ("jmp (%c0).l" : : "i"(ROM_LAUNCH) : "memory");    /* leaves for good: a store before it must land */
    __builtin_unreachable();
}
#endif
