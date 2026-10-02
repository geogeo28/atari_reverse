/* aes/obuser.h — the object draw path's two LEAVES and the call they share (`src/aes/obuser.c`): ob_format, which
 * merges an editable text's raw string into its template, and ob_user, which calls a USERDEF object's own drawing
 * routine through far_call.
 *
 * ALCYON C, each entered over its caller's frame (in push order below): just_draw calls ob_format for G_FTEXT and
 * G_FBOXTEXT ($fe9c8a) and ob_user for G_USERDEF ($fe9dc4), ob_change ob_user ($fea43a), ob_edit ob_format ($fe9746,
 * $fe9918). What each answers is the ROM's register:
 *   * ob_format nothing — its bytes are the answer;
 *   * ob_user and far_call the WHOLE of D0 the routine leaves (`uint32_t`): far_call returns by a Line-F return that
 *     keeps D0, ob_user by another — so a caller reading the object's new state takes its low word.
 *
 * ob_user's PARMBLK is a frame local whose ADDRESS the routine is handed (`aes/objects.h`'s PARM_*): off target it is
 * `host_slot.h`'s AES_OB_USER_PARMBLK. The 68000 routine a case stages for it — and the host twin of it — is
 * `test/aes_obuser.py`'s, for every battery that reaches a G_USERDEF.
 */
#ifndef TOS102US_AES_OBUSER_H
#define TOS102US_AES_OBUSER_H

/* The bytes ob_format tests for. */
#define OB_FORMAT_EMPTY_MARK  0x40       /* '@' as a raw text's first byte: the text is empty ($fe99b0 cmpi.b #64) */
#define OB_FORMAT_PLACEHOLDER 0x5f       /* '_' in a template: the raw text's next byte ($fe9a20 cmpi.b #95)    */
/* TE_JUST's one value ob_format tells apart ($fe99de cmpi.w #1,8(a6)): the merge walks from the strings' ends. */
#define OB_FORMAT_RIGHT       1

#ifndef __ASSEMBLER__
#include <stdint.h>

void aes_ob_format(uint8_t *image, int16_t just, uint32_t raw, uint32_t tmplt, uint32_t out);           /* $fe99a4 */
uint32_t aes_ob_user(uint8_t *image, uint32_t tree, int16_t object, uint32_t rect, uint32_t userblk, int16_t curr,
                     int16_t new_state);                                                                 /* $fe9a46 */
uint32_t aes_far_call(uint8_t *image, uint32_t code, uint32_t parm);                                     /* $fddec6 */
#endif

#endif /* TOS102US_AES_OBUSER_H */
