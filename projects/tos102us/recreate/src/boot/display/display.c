/* BOOT B5 — the boot's display slice in C, [$fc03e0, $fc0452): after the IKBD's reset (B3's), before the interrupts
 * open (B6's).
 *
 *   $fc03e0  the shifter's resolution read, its mode bits kept, the fourth value (3) taken as ST high: sshiftmd
 *   $fc03f8  the monitor socket asked (the MFP's GPIP bit 7, LOW for a mono monitor); for a mono monitor: the sync
 *            wait on timer B (`$fc0e1a`, returning through A6), then the shifter and sshiftmd := ST high
 *   $fc0418  the blitter probe (`$fc0f1a`: D0 = 2 or, the access faulting, 0), the Line-A's body vectors filled for
 *            that mode (`$fca99e`) and the console re-initialised for sshiftmd's resolution (`$fca914`)
 *   $fc0428  on ST medium the colour of pen 15 copied to pen 3; swv_vec := the reset; vblsem := 1 (open)
 *   $fc044c  the cartridge's hooks with D0 = 0 (`$fc0646`); on to `move #$2300,sr` ($fc0452, B6's)
 *
 * THE ROM'S ROUTINES IT CALLS ARE THE ROM'S, ON BOTH SHORES, IN PLACE: the sync wait and the cartridge's hooks are the
 * boot's own (unported; the head reaches the sync wait in place too), the probe is XBIOS Blitmode's (unported: its arm
 * a bus error), and the Line-A set-up and the console re-init lie in the VDI's range (unported). Each is called as the
 * ROM calls it — the sync wait with its return in A6, the rest by `jsr` — with the registers the ROM's slice hands it.
 *
 * THE REGISTERS THIS FILE MAY NOT TOUCH: D2-D7 and A2-A6 (the Makefile compiles it with them fixed). The routines it
 * calls clobber them freely (the probe A2, the sync wait D3/D4/A6, the console's set-up what its callees leave), and
 * the ROM's slice hands its continuation whatever they left — so the C holds nothing there and saves nothing there:
 * GCC would otherwise save every callee-saved register a call clobbers in a prologue the ROM does not run. Each call's
 * clobbers name the scratch registers alone (the fixed ones are never allocated). The image base comes through a
 * register (`target_image`) after every call, as the ROM's own `0(a5)` addressing assumes A5 = 0.
 */
/* TARGET ONLY: its own rule links it at DISPLAY_LAID_AT; it is a run of calls into the ROM with nothing of its own on
 * the host's side to call them, so off target the file is empty — the host's sweeps compile every source. */
#ifndef RECREATE_HOST_DIFFERENTIAL
#include <stdint.h>

#include "machine.h"
#include "hw.h"
#include "addrs.h"
#include "staged_call.h"
#include "boot/head.h"
#include "boot/hwinit.h"
#include "boot/launch.h"
#include "boot/display.h"

/* What a call into the ROM may leave changed that the compiler could hold: the scratch registers, the flags, memory. */
#define ROM_CALL_CLOBBERS "d0", "d1", "a0", "a1", "cc", "memory"

/* `lea <return>(pc),a6 / bra.w $fc0e1a`: the sync wait returns through A6, as the boot's link registers do. */
static inline void rom_sync_wait(void)
{
    __asm__ volatile ("lea 1f(%%pc),%%a6\n\t"
                      "jmp (%c0).l\n"
                      "1:"
                      : : "i"(ROM_SYNC_WAIT) : ROM_CALL_CLOBBERS);
}

/* `bsr $fc0f1a / jsr $fca99e / jsr $fca914`: the probe's answer reaches the Line-A's set-up in D0, as the ROM's does. */
static inline void rom_probe_and_set_up_the_screen(void)
{
    __asm__ volatile ("jsr (%c0).l\n\t"
                      "jsr (%c1).l\n\t"
                      "jsr (%c2).l"
                      : : "i"(ROM_BLITTER_PROBE), "i"(ROM_LINEA_SET_VECTORS), "i"(ROM_CONSOLE_REINIT)
                      : ROM_CALL_CLOBBERS);
}

/* `clr.w d0 / bsr $fc0646`, then on to where the ROM's boot goes next: the slice never returns. */
__attribute__((noreturn)) static inline void rom_hooks_and_on(void)
{
    __asm__ volatile ("clr.w %%d0\n\t"
                      "jsr (%c0).l\n\t"
                      "jmp (%c1).l"
                      : : "i"(ROM_CARTRIDGE_HOOKS), "i"(ROM_DISPLAY_END) : ROM_CALL_CLOBBERS);
    __builtin_unreachable();
}

_Static_assert(CARTRIDGE_HOOK_DISPLAY == 0, "the hooks' init bit is cleared into D0 (`clr.w d0`), not loaded");

/* Is a monochrome monitor plugged in? The MFP's GPIP bit 7 is LOW when one is. */
static inline int monochrome_monitor_attached(void)
{
    return (hw_read8(MFP_GPIP) & (1u << MFP_GPIP_MONOCHROME_BIT)) == 0;
}

/* $fc03e0 — entered where B3's stretch ends, A5 = 0 and the BIOS's stack as the ROM's boot leaves them. */
__attribute__((noreturn)) void boot_display_entry(void)
{
    uint8_t *image = target_image();
    uint8_t mode = io_read8(SHIFTER_RESOLUTION) & GETREZ_MODE_MASK;

    if (mode == SHIFTER_MODE_RESERVED)
        mode = SHIFTER_MODE_HIGH;
    /* The mode settled in its register before the store: without the barrier GCC stores the raw mode and then the
     * settled one, two stores of sshiftmd where the ROM makes one (measured). */
    REGISTER_BARRIER(mode, REGISTER_BARRIER_DATA_CLASS);
    image[SYSVAR_SSHIFTMD] = mode;
    if (monochrome_monitor_attached()) {
        rom_sync_wait();
        hw_write8(SHIFTER_RESOLUTION, SHIFTER_MODE_HIGH);
        image = target_image();
        image[SYSVAR_SSHIFTMD] = SHIFTER_MODE_HIGH;
    }
    rom_probe_and_set_up_the_screen();
    image = target_image();
    if (image[SYSVAR_SSHIFTMD] == SHIFTER_MODE_MEDIUM)
        hw_write16(SHIFTER_PALETTE + MEDIUM_FOREGROUND_PEN * PALETTE_ENTRY_BYTES,
                   io_read16(SHIFTER_PALETTE + LOW_FOREGROUND_PEN * PALETTE_ENTRY_BYTES));
    wr32(image + SYSVAR_SWV_VEC, ROM_RESET_ENTRY);
    wr16(image + SYSVAR_VBLSEM, VBLSEM_OPEN);
    rom_hooks_and_on();
}
#endif
