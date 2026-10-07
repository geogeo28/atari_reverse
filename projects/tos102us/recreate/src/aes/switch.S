/* switch.S — THE PROCESS SWITCH's entry as the ROM spells it (`aes/switch.h`): dsptch, `$fe387c..$fe388f`, twenty
 * bytes of gemdosif's hand 68000 — byte for byte (`test/test_tier3.py` pins them on both blobs).
 *
 * A KIND OF ITS OWN (`atari/target.mk`: SWITCH_SOURCES; `include/transcribed.h` says why it is no row of the table):
 * not a transcription — there is no C twin a build could link instead, and no Tier 3 bar it was measured over: a
 * context switch has no C spelling (ruling Q4) — and not glue: these ARE the ROM's bytes. It carries the C NAME the
 * event layer's C calls, `aes_dsptch` (declared in the header for the target build; off target the same name is the
 * dispatcher's hook, which refuses).
 *
 * HOW IT IS ENTERED. By `jsr`, with its caller's return address on the stack — which is the whole of its contract:
 * under the guard (`indisp`: inside the dispatcher already) it returns at once; otherwise it pushes the status
 * register and A0 and JUMPS into disp, which reads that return address as the PC to resume the process at
 * (`$fe4d9e`: savestate). The image pointer a C caller pushed is above the return address and is nobody's: the caller
 * drops it when — a process switch later — the call returns. A0 is whatever the caller held (the ROM's own callers
 * arrive with the Line-F handler's table pointer in it); disp's frame only carries it.
 *
 * ITS `jmp` GOES TO THE ROM'S disp, at the ROM's address: disp ships with the scheduler (band 4, wave 2: its own
 * `.S`), and until it does this is the one instruction of the build that leaves for the AES's ROM text other than
 * the event door's `jsr`s — reached by no priced row (a row's run returns; a call that switches is Tier 1's,
 * `aes_event.switches_where_the_rom_does`), and held to that address by the byte pin.
 */
#include "addrs.h"
#include "aes/aes.h"
#include "aes/switch.h"

    .text

/* ---- dsptch, $fe387c ---------------------------------------------------------------------------------------------- */
    .globl  aes_dsptch
    .type   aes_dsptch,@function
aes_dsptch:
    tst.b   AES_INDISP
    beq.s   1f
    rts
1:  move.w  %sr,-(%sp)
    move.l  %a0,-(%sp)
    jmp     AES_ROM_DISP
    .size   aes_dsptch,.-aes_dsptch
