/* hwinit_entry.S — where boot B3's C is entered, as the ROM enters what it replaces.
 *
 * `bios_hardware_init_entry` is `$fc2408` as the ROM calls it — `bsr`, no argument, A5 = 0, returning — the image base
 * pushed (0 on target, `c_call_glue.h`) for the C. `boot_hardware_init_called_entry` is the boot's stretch
 * [$fc03b6, $fc03e0), entered as B2's entry is (`sysvars_entry.S`): the init called as the ROM's `bsr $fc2408` calls it,
 * then — `boot_ikbd_reset_entry`, the init's return — the C (the IKBD reset, the pause), the cartridge's hook 2 — the
 * ROM's own routine (`$fc0646`, unported, called four times by the boot: a CODE obligation on a rebuilt ROM,
 * `test_boot_rom_data.py`; D2 open) with its init bit in D0 — and on to where the ROM's boot goes next. The C keeps
 * A2-A6 and D2-D7 (GCC's ABI); the hook leaves D0 and A0 as the ROM's does. */
#include "addrs.h"
#include "c_call_glue.h"
#include "boot/hwinit.h"

    .text
    .globl  bios_hardware_init_entry
    IMAGE_ONLY_THUNK(bios_hardware_init_entry, bios_hardware_init)

    .globl  boot_hardware_init_called_entry
    .type   boot_hardware_init_called_entry,@function
boot_hardware_init_called_entry:
    jbsr    bios_hardware_init_entry
    .globl  boot_ikbd_reset_entry
boot_ikbd_reset_entry:
    pea     (0).w
    jsr     boot_ikbd_reset
    addq.l  #IMAGE_ARGUMENT_BYTES,%sp
    moveq   #CARTRIDGE_HOOK_IKBD_RESET,%d0
    jsr     (ROM_CARTRIDGE_HOOKS).l
    jmp     (ROM_BOOT_IKBD_RESET_DONE).l
    .size   boot_hardware_init_called_entry,.-boot_hardware_init_called_entry
