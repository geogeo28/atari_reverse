/* sysvars_entry.S — where the boot's C is entered, as the head leaves it (boot B2, ruling D7: "C after `lea $755a,sp`").
 *
 * The head ends standing on the BIOS's stack with A5 = 0 and nothing to return to: the ROM falls through into the
 * system variables. This is that fall-through for a build: the image base pushed (0 on target, `c_call_glue.h`), the C
 * called, and on to where the ROM's boot goes next — `bsr $fc2408` at `ROM_BOOT_HARDWARE_INIT_CALL`, still the ROM's
 * (B3's; a CODE obligation on a rebuilt ROM, `test_boot_rom_data.py`). The C keeps A2-A6 and D2-D7 (GCC's ABI), so A5
 * reaches the ROM's continuation as the head left it, and the stack pointer as `lea $755a,sp` set it. */
#include "addrs.h"
#include "c_call_glue.h"
#include "boot/sysvars.h"

    .text
    .globl  boot_sysvars_entry
    .type   boot_sysvars_entry,@function
boot_sysvars_entry:
    pea     (0).w
    jsr     boot_sysvars_and_vectors
    addq.l  #IMAGE_ARGUMENT_BYTES,%sp
    jmp     (ROM_BOOT_HARDWARE_INIT_CALL).l
    .size   boot_sysvars_entry,.-boot_sysvars_entry
