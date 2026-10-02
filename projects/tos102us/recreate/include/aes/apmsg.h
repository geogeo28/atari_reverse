/* aes/apmsg.h — the window library's MESSAGE SENDER (`src/aes/apmsg.c`): ap_sendmsg, which builds GEM's sixteen-byte
 * message in its caller's buffer and writes it into the receiver's pipe through ap_rdwr — the event door's
 * (`aes/evdoor.h`).
 */
#ifndef TOS102US_AES_APMSG_H
#define TOS102US_AES_APMSG_H

#include <stdint.h>

/* The message: eight words, the type, the sender's process id and the bytes past the sixteen, then five of the
 * message's own ($febdc6.. one `move.w` into each, by its offset). */
#define AP_MSG_TYPE           0          /* word                                ($febdc6 move.w 12(a6),(a0))   */
#define AP_MSG_SENDER         2          /* word: the running process's id      ($febdd4 move.w 28(a1),2(a0))  */
#define AP_MSG_EXTRA          4          /* word: none                          ($febdde clr.w 4(a0))          */
#define AP_MSG_WORDS          6          /* words[5]: the message's own         ($febde6 .. $febe0e)           */
#define AP_MSG_BYTES          16         /* what ap_rdwr is told to write       ($febe18 move.w #16)           */

uint16_t aes_ap_sendmsg(uint8_t *image, uint32_t buffer, int16_t type, int16_t to, int16_t word3, int16_t word4,
                        int16_t word5, int16_t word6, int16_t word7);                               /* $febdbe */

#endif /* TOS102US_AES_APMSG_H */
