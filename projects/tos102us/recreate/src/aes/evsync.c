/* evsync.c — the scheduler's semaphore (`aes/evsync.h`), Alcyon C in the ROM, ported over its own order: every word of
 * the SPB is read where the ROM reads it, through its pointer on the 24-bit bus, and the running process (`rlr`) after
 * the count is stored — a semaphore laid over `rlr` itself is counted before it is compared.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/evsync.h"
#include "aes/wmupdate.h"

/* $fe4e5a — the caller counted in first (`addq.w #1,(a5)`); the semaphore is its own when the running process already
 * holds it (a deeper hold) or the count is now the first hold's (it was free: the owner left by the last release is
 * not looked at). Otherwise the count is taken back and the call refused — the caller waits (amutex queues it). */
uint16_t aes_tak_flag(uint8_t *image, uint32_t semaphore)
{
    set_bus_word(image, semaphore + SPB_COUNT, (uint16_t)(bus_word(image, semaphore + SPB_COUNT) + 1));
    if (bus_long(image, semaphore + SPB_OWNER) != be32(image + AES_RLR)
        && bus_word(image, semaphore + SPB_COUNT) != SPB_FIRST_HOLD) {
        set_bus_word(image, semaphore + SPB_COUNT, (uint16_t)(bus_word(image, semaphore + SPB_COUNT) - 1));
        return TAK_FLAG_REFUSED;
    }
    set_bus_long(image, semaphore + SPB_OWNER, be32(image + AES_RLR));
    return TAK_FLAG_TAKEN;
}
