/* sound.h — handing a Dosound list to the 200 Hz driver, which three routines in this ROM do.
 *
 * The driver itself is `$fc312a`, entered by the timer C interrupt 200 times a second
 * (`src/bios/timerc.c`); it walks a list of command bytes, writing `$ff8800`/`$ff8802` as it goes.
 * Nothing here plays a sound — each of the three just hands that driver a new cursor:
 *
 *      XBIOS Dosound ($fc3074)  the caller's list       src/xbios/sound.c
 *      BEL ($fc2270)            the ROM's bell list     src/bios/vt52.c
 *      the key click ($fc2c4c)  the ROM's click list    src/bios/keyboard.c
 *
 * ...and every one of them is the SAME TWO STORES, which is why they are spelt once. The `clr.b` is
 * the half a reconstruction drops: `$0e8e` is the driver's "ticks still to wait", so clearing it is
 * what makes the NEXT tick start the new list instead of finishing the old one's pause. A
 * reconstruction that stored only the pointer would be silent for up to 255 ticks, and nothing but
 * that byte says so.
 */
#ifndef TOS102US_SOUND_H
#define TOS102US_SOUND_H

#include <stdint.h>

#include "machine.h"
#include "addrs.h"

static inline void sound_start_list(uint8_t *image, uint32_t list)
{
    wr32(image + SOUND_LIST_POINTER, list);
    image[SOUND_LIST_DELAY] = 0;
}

#endif /* TOS102US_SOUND_H */
