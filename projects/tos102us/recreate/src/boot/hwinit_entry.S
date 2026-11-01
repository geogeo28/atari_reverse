/* hwinit_entry.S — where boot B3's C is entered, as the ROM enters what it replaces.
 *
 * `bios_hardware_init_entry` is `$fc2408` as the ROM calls it — `bsr`, no argument, A5 = 0, returning — the image base
 * pushed (0 on target, `c_call_glue.h`) for the C. `boot_hardware_init_called_entry` is the boot's stretch
 * [$fc03b6, $fc03e0), entered as B2's entry is (`sysvars_entry.S`): the init called as the ROM's `bsr $fc2408` calls it,
 * then — `boot_ikbd_reset_entry`, the init's return — the C (the IKBD reset, the pause), the cartridge's hook 2 — the
 * ROM's own routine (`$fc0646`, unported, called four times by the boot: a CODE obligation on a rebuilt ROM,
 * `test_boot_rom_data.py`; D2 open) with its init bit in D0 — and on to where the ROM's boot goes next. The C keeps
 * A2-A6 and D2-D7 (GCC's ABI); the hook leaves D0 and A0 as the ROM's does.
 *
 * TWO REGISTERS THE ROM'S CODE LEAVES AND THE BOOT HANDS ON, LEFT HERE AS IT LEAVES THEM (review RB6's R2, measured: the
 * ROM's own B5 / B6 carry both to `$fc047a`, and A3 on into the pre-init machine): A3 the RS232 handlers' table the init
 * walks (`ROM_RS232_HANDLER_TABLE`), at both entries' returns; D3 Ikbdws's byte count run out (`IKBDWS_COUNT_RUN_OUT`),
 * past the IKBD reset. The C keeps its caller's in both (callee-saved). */
#include "addrs.h"
#include "c_call_glue.h"
#include "boot/hwinit.h"

    .text
    .globl  bios_hardware_init_entry
    .type   bios_hardware_init_entry,@function
bios_hardware_init_entry:
    pea     (0).w
    jsr     bios_hardware_init
    addq.l  #IMAGE_ARGUMENT_BYTES,%sp
    movea.l #ROM_RS232_HANDLER_TABLE,%a3
    rts
    .size   bios_hardware_init_entry,.-bios_hardware_init_entry

    .globl  boot_hardware_init_called_entry
    .type   boot_hardware_init_called_entry,@function
boot_hardware_init_called_entry:
    jbsr    bios_hardware_init_entry
    .globl  boot_ikbd_reset_entry
boot_ikbd_reset_entry:
    pea     (0).w
    jsr     boot_ikbd_reset
    addq.l  #IMAGE_ARGUMENT_BYTES,%sp
    move.l  #IKBDWS_COUNT_RUN_OUT,%d3
    moveq   #CARTRIDGE_HOOK_IKBD_RESET,%d0
    jsr     (ROM_CARTRIDGE_HOOKS).l
    jmp     (ROM_BOOT_IKBD_RESET_DONE).l
    .size   boot_hardware_init_called_entry,.-boot_hardware_init_called_entry
