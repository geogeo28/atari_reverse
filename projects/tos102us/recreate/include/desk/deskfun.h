/* desk/deskfun.h — THE DESK'S ALERT AND ITS MESSAGE TO ITSELF, unit H (`src/desk/deskfun.c`): fun_alert `$fdfd58`, the
 * alert every file operation raises (an alert string of the desk's resource, a parameter merged into it), and fun_msg
 * `$fdfda6`, a message the desk writes to its own pipe (a window's redraw) — band 6 wave 1b, group G4.
 *
 * NAMES: the published GEM desktop's (DESKFUN), each read from its body.
 *
 * BOTH YIELD: each ends on a binding of unit D (`desk/deskbind.h`), so each is a row that switches at Tier 1; and both
 * answer the binding's own word, which the C has.
 */
#ifndef TOS102US_DESK_DESKFUN_H
#define TOS102US_DESK_DESKFUN_H

#include "desk/deskglobals.h"

/* fun_alert's string: `desk/deskglobals.h`'s DESK_G_ALERT — the address rs_gaddr answers for the resource's free
 * string, put back as the text merge_str made of it where the caller hands parameters. */

/* fun_msg's message, laid in its own frame and handed to appl_write by address: the eight words of an AES message. */
#define FUN_MSG_TYPE          0          /* word: the caller's type             ($fdfdaa -16(a6))              */
#define FUN_MSG_SENDER        2          /* word: gl_apid, the desk's own id    ($fdfdb0 -14(a6))              */
#define FUN_MSG_MORE          4          /* word: no bytes beyond the eight words ($fdfdb8 clr.w -12(a6))     */
#define FUN_MSG_WORD_3        6          /* words[5]: the caller's last five    ($fdfdbc -10(a6) .. -2(a6))    */
#define FUN_MSG_BYTES         16         /* appl_write's length                 ($fdfde2 move.w #16,-(sp))     */
#define FUN_MSG_NO_MORE       0

#ifndef __ASSEMBLER__
#include <stdint.h>

int16_t aes_desk_fun_alert(uint8_t *image, int16_t default_button, int16_t string, uint32_t parameters);      /* $fdfd58 */
uint16_t aes_desk_fun_msg(uint8_t *image, int16_t type, int16_t unread, int16_t word3, int16_t word4, int16_t word5,
                          int16_t word6, int16_t word7);                                                     /* $fdfda6 */
#endif

#endif /* TOS102US_DESK_DESKFUN_H */
