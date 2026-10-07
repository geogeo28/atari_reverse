/* apmsg.c — ap_sendmsg (`aes/apmsg.h`), Alcyon C in the ROM: GEM's message built in the caller's buffer — re-reading
 * the buffer pointer from its frame for every store, and the running process AFTER the type's store, as the ROM does —
 * then written into the receiver's pipe by ap_rdwr, through the event door (`aes/evdoor.h`). D0 is ap_rdwr's.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/apmsg.h"
#include "aes/evdoor.h"
#include "vdi/vdi.h"

uint16_t aes_ap_sendmsg(uint8_t *image, uint32_t buffer, int16_t type, int16_t to, int16_t word3, int16_t word4,
                        int16_t word5, int16_t word6, int16_t word7)
{
    set_bus_word(image, buffer + AP_MSG_TYPE, (uint16_t)type);
    set_bus_word(image, buffer + AP_MSG_SENDER, bus_word(image, running(image, PD_PID)));
    set_bus_word(image, buffer + AP_MSG_EXTRA, 0);
    set_bus_word(image, word_entry(buffer + AP_MSG_WORDS, 0), (uint16_t)word3);
    set_bus_word(image, word_entry(buffer + AP_MSG_WORDS, 1), (uint16_t)word4);
    set_bus_word(image, word_entry(buffer + AP_MSG_WORDS, 2), (uint16_t)word5);
    set_bus_word(image, word_entry(buffer + AP_MSG_WORDS, 3), (uint16_t)word6);
    set_bus_word(image, word_entry(buffer + AP_MSG_WORDS, 4), (uint16_t)word7);
    return evdoor_ap_rdwr(image, AP_RDWR_WRITE, to, AP_MSG_BYTES, buffer);
}
