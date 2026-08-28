| ym_psg.S — the one routine of the music driver that is assembly, and the measurement that put it
| here.
|
| THE PUBLISH IS 11 SELECT/DATA PAIRS AND NOTHING ELSE, and its cost is a fifth of the whole tick.
| Written in C, GCC folds the chip address into every store and emits, per register:
|     move.b d16(a0),d1        12 cycles   (the value, out of the image)
|     move.b #n,$ffff8800.w    16          (the select)
|     move.b d1,$ffff8802.w    12          (the data)
| = 40 cycles x 11 = 440. Holding the chip in an address register and walking the image with a
| post-increment gets the same eleven writes for 28 cycles each:
|     move.b #n,(a0)           12
|     move.b (a1)+,2(a0)       16
| = 308, and there is no way to spell that in C: the pointer is a compile-time constant, so the
| compiler always prefers the absolute form. Measured on the tick as 3,062 -> 2,9xx cycles a frame
| (REPORT.md), against a 3,000-cycle budget. That is the whole reason this file exists.
|
| The unroll is a .rept over PSG_REG_COUNT, so the count lives in ym_psg.h with the C that sizes
| the image — one definition, two readers.

#include "ym_psg.h"

    .text
    .globl  ym_psg_publish

| void ym_psg_publish(const unsigned char *image)
| C ABI (m68k SysV): the argument is at 4(%sp); %d0/%d1/%a0/%a1 are the scratch registers a callee
| may use freely, and this uses only those.
ym_psg_publish:
    move.l  4(%sp),%a1                      | the register image, in register order
    lea     PSG_CHIP_BASE_ADDRESS,%a0       | select at (%a0), data at PSG_DATA_OFFSET(%a0)
    move.w  %sr,%d1
    ori.w   #CPU_IPL_MASK_ALL,%sr

    .set    psg_register, 0
    .rept   PSG_REG_COUNT
    move.b  #psg_register,(%a0)
    move.b  (%a1)+,PSG_DATA_OFFSET(%a0)
    .set    psg_register, psg_register + 1
    .endr

    move.w  %d1,%sr
    rts
