/* deskfun.c — THE DESK'S ALERT AND ITS MESSAGE TO ITSELF (`desk/deskfun.h`): fun_alert `$fdfd58` and fun_msg `$fdfda6`.
 * Alcyon C in the ROM, ported over its own order; each ends on a binding of unit D and answers that binding's word.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/deskmem.h"
#include "aes/resource.h"
#include "aes/strings.h"
#include "desk/deskbind.h"
#include "desk/deskfun.h"

_Static_assert(FUN_MSG_BYTES == HOST_SLOT_AES_DESK_FUN_MSG_BYTES, "fun_msg's message and its host slot");

/* $fdfd58 — fun_alert: alert string `string` of the desk's resource, MERGED with `parameters` where the caller hands
 * any (into the desk's 512-byte block, whose address is taken before anything else), shown with `default_button`.
 * Its answer is form_alert's: the button. */
int16_t aes_desk_fun_alert(uint8_t *image, int16_t default_button, int16_t string, uint32_t parameters)
{
    uint32_t merged = be32(image + AES_DESK_BLOCK_512);
    uint32_t desk = be32(image + AES_DESK_GLOBALS);

    (void)aes_desk_rsrc_gaddr(image, R_STRING, string, desk + DESK_G_ALERT);
    if (parameters) {
        aes_merge_str(image, merged, bus_long(image, desk + DESK_G_ALERT), parameters);
        set_bus_long(image, desk + DESK_G_ALERT, merged);
    }
    return aes_desk_form_alert(image, default_button, bus_long(image, desk + DESK_G_ALERT));
}

/* $fdfda6 — fun_msg: the message `type` from the desk to itself — its five words after the third the caller's last
 * five — written to its own pipe. The caller's second word is read by nothing (its one kind of caller pushes gl_apid
 * there, `$fe3746`). The message lies in the routine's own frame, handed to appl_write by address: a host slot off
 * target, HELD ACROSS THE BINDING'S YIELD (the dispatcher runs before appl_write's answer comes back). */
uint16_t aes_desk_fun_msg(uint8_t *image, int16_t type, int16_t unread, int16_t word3, int16_t word4, int16_t word5,
                          int16_t word6, int16_t word7)
{
    uint16_t message_local[FRAME_LOCAL_WORDS(FUN_MSG_BYTES)];
    uint32_t message = host_slot_claim(AES_DESK_FUN_MSG, message_local);
    uint16_t written;

    (void)unread;
    wr16(image + message + FUN_MSG_TYPE, (uint16_t)type);
    wr16(image + message + FUN_MSG_SENDER, be16(image + AES_GL_APID));
    wr16(image + message + FUN_MSG_MORE, FUN_MSG_NO_MORE);
    wr16(image + message + FUN_MSG_WORD_3, (uint16_t)word3);
    wr16(image + message + FUN_MSG_WORD_3 + M68K_WORD_BYTES, (uint16_t)word4);
    wr16(image + message + FUN_MSG_WORD_3 + 2 * M68K_WORD_BYTES, (uint16_t)word5);
    wr16(image + message + FUN_MSG_WORD_3 + 3 * M68K_WORD_BYTES, (uint16_t)word6);
    wr16(image + message + FUN_MSG_WORD_3 + 4 * M68K_WORD_BYTES, (uint16_t)word7);
    written = aes_desk_appl_write(image, (int16_t)be16(image + AES_GL_APID), FUN_MSG_BYTES, message);
    host_slot_release(AES_DESK_FUN_MSG);
    return written;
}
