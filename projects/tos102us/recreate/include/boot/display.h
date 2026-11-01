/* boot/display.h — the names BOOT B5 is spelt in: the boot's display slice [$fc03e0, $fc0452) — the resolution read
 * into sshiftmd, the monitor socket asked, the mono switch, the blitter probe, the Line-A and console set-up, the
 * medium palette's foreground, swv_vec and vblsem, the cartridge's hook 0 (`src/boot/display/display.c`). The names that
 * already exist stay where they are (`addrs.h`: `SHIFTER_RESOLUTION`, `GETREZ_MODE_MASK`, `SHIFTER_MODE_*`,
 * `MFP_GPIP`, `SYSVAR_SSHIFTMD`, `SYSVAR_SWV_VEC`, `SYSVAR_VBLSEM`, `SHIFTER_PALETTE`; `boot/head.h`: `ROM_SYNC_WAIT`;
 * `boot/hwinit.h`: `ROM_CARTRIDGE_HOOKS`, `ROM_BOOT_IKBD_RESET_DONE` — this slice's first instruction; `boot/launch.h`:
 * `ROM_RESET_ENTRY`).
 *
 * ASSEMBLER-SAFE above the `__ASSEMBLER__` guard (plain integer `#define`s, as `addrs.h`). The Python side reads it
 * with `layouts.parse_constants` (`test/boot_display.py`), so a value is spelt once.
 *
 * WHERE IT IS LAID (rulings "ROM-window overlay" and "Own link rule", 2026-10-29): over a COPY of the image's ROM bytes
 * no instruction of the slice runs or reads (held: the ROM's own slice is the same run with and without the overlay,
 * `test_boot_display.py`) — Prtblk's text ($fc31fa.., XBIOS 36: unported, run by nothing of the slice), past B4's
 * launch (`LAUNCH_LAID_AT`, [$fc3200, $fc3ad6)) — and LINKED THERE by its own Makefile rule (`build/bootdisplay/`),
 * with every callee-saved register FIXED: the ROM's routines the slice calls clobber them freely, and the ROM's slice
 * leaves them to its continuation as those routines leave them.
 */
#ifndef TOS102US_BOOT_DISPLAY_H
#define TOS102US_BOOT_DISPLAY_H

#define DISPLAY_LAID_AT           0xfc3c00   /* the C's entry, its first byte */

/* ---- the ROM's slice ------------------------------------------------------------------------------------------- */
#define ROM_DISPLAY_END           0xfc0452   /* `move #$2300,sr`: the interrupts opened (B6's), where the slice ends */
#define SHIFTER_MODE_RESERVED     3          /* `cmp.b #3,d0`: the mode bits' fourth value, taken as ST high */
#define LOW_FOREGROUND_PEN        15         /* `move.w $ffff825e,$ffff8246` on ST medium: the colour of pen 15, ST low's
                                              * foreground, ... */
#define MEDIUM_FOREGROUND_PEN     3          /* ...copied to pen 3, the last of medium's four, which the console draws in */
#define VBLSEM_OPEN               1          /* `move.w #1,vblsem`: the VBL handler's body may run */
#define CARTRIDGE_HOOK_DISPLAY    0          /* `clr.w d0`: the init bit the boot calls the cartridge's hooks with here */

/* ---- the ROM's routines it calls, run in place on both shores (CODE obligations: `test_boot_rom_data.py`) -------- */
#define ROM_BLITTER_PROBE         0xfc0f1a   /* Blitmode's probe: D0 = 2 where `tst.w $ffff8a00` does not fault, 0 where
                                              * it does (the bus error the case declares, `bus_error.Fault`) */
#define ROM_LINEA_SET_VECTORS     0xfca99e   /* the Line-A's CPU / blitter sets named, then `jmp $fc4dde`: the ten body
                                              * vectors filled for the mode in D0 (VDI range, unported) */
#define ROM_CONSOLE_REINIT        0xfca914   /* the console re-initialised for sshiftmd's resolution (VDI range,
                                              * unported: Setscreen's resolution arm halts on it) */

#endif /* TOS102US_BOOT_DISPLAY_H */
