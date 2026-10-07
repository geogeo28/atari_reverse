/* aes/evlib.h — THE EVENT LIBRARY's single waits and appl_read / appl_write (`src/aes/evlib.c`, gemevlib and
 * gemaplib): one event waited for and answered.
 *
 *   $fe6874 ev_block(code, parameter)        iasync, mwait, apret: ONE wait queued, waited for, answered — D0.w
 *   $fe65c4 ap_rdwr(code, pid, length, buf)  ev_block(code, its own arguments from `pid` on, as a QPB)
 *   $fe6894 ev_keybd()                       ev_block(a key): the key
 *   $fe68a4 ev_button(clicks, mask, state, answers)  ev_block(the buttons), then ev_rets: the clicks
 *   $fe68e4 ev_mouse(moblk, answers)         ev_block(the mouse), ev_rets, the buttons AS THEY ARE over its third word
 *   $fe6910 ev_mesag(buffer)                 ap_rdwr(read, the running process's id, 16, buffer)
 *   $fe6936 ev_timer(milliseconds)           ev_block(a delay of milliseconds / the tick's)
 *   $fe681a ev_rets(answers)                 the mouse (where the last button change was made, when one was counted
 *                                            since), the buttons of the last answer apret took, the shift keys
 *   $fe695c ev_mchk(moblk)                   D0.w: the running process owns the mouse and it is where the MOBLK asks
 *   $fe6c5e ev_dclick(rate, set)             the double-click rate set from the ROM's table, or just answered
 *
 * ALCYON C, every routine entered by a Line-F call over its caller's frame.
 */
#ifndef TOS102US_AES_EVLIB_H
#define TOS102US_AES_EVLIB_H

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

#include "aes/aes.h"

/* ---- the globals ----------------------------------------------------------------------------------------------- */
/* The double-click RATE (GEM's gl_dcindex), 0 the slowest: ev_dclick's index into the ROM's table of milliseconds,
 * from which it sets the ticks a click's count stays open (`aes/aes.h`'s AES_GL_DCLICK). */
#define AES_GL_DCINDEX        0xc79c     /* word                                ($fe6c68 move.w 8(a6),$c79c)   */
#define AES_DCLICK_MS_TABLE   0xfefa04   /* words[5]: 450, 330, 275, 220, 165   ($fe6c78 movea.l #$fefa04,a1)  */
#define AES_DCLICK_RATES      5          /* ...its entries, rates 0-4: another table begins at $fefa0e. NOT a bound
                                          * ev_dclick holds a rate to — the ROM indexes with whatever it is handed */
/* A word the control manager sets once it has sent the running application a message and tests before it sends
 * another ($fe487e, $fe4842), and that a message READ clears: ev_mesag before its read, ev_multi after one came
 * ($fe6c54). A `ctx` name. */
#define AES_CTL_MESSAGE_SENT  0x97fe     /* word                                ($fe6914 clr.w $97fe)          */

/* ---- ev_rets' ANSWERS, four words through its pointer ($fe682a..$fe6864) ------------------------------------------ */
#define EV_RETS_X             0
#define EV_RETS_Y             2
#define EV_RETS_BUTTONS       4
#define EV_RETS_SHIFT_KEYS    6

/* ---- ev_mchk's answer ($fe698e moveq #1,d0; $fe6994 clr.w d0) ----------------------------------------------------- */
#define EV_MCHK_CAME          1
#define EV_MCHK_NOT_YET       0

/* ---- ap_rdwr's QPB: its own three arguments after the code, in place ($fe65ca addi.l #10,(sp)) — the layout
 * `aes/pdpipe.h`'s QPB_* read. A host build keeps it in a slot of the running process's own (`host_slot.h`). */
#define AP_RDWR_QPB_BYTES     8

#ifndef __ASSEMBLER__
uint16_t aes_ev_block(uint8_t *image, int16_t code, uint32_t parameter);                             /* $fe6874 */
uint16_t aes_ap_rdwr(uint8_t *image, int16_t code, int16_t process, int16_t length, uint32_t buffer); /* $fe65c4 */
uint16_t aes_ev_keybd(uint8_t *image);                                                               /* $fe6894 */
uint16_t aes_ev_button(uint8_t *image, int16_t clicks, int16_t mask, int16_t state, uint32_t answers); /* $fe68a4 */
uint16_t aes_ev_mouse(uint8_t *image, uint32_t moblk, uint32_t answers);                             /* $fe68e4 */
uint16_t aes_ev_mesag(uint8_t *image, uint32_t buffer);                                              /* $fe6910 */
uint16_t aes_ev_timer(uint8_t *image, int32_t milliseconds);                                         /* $fe6936 */
void aes_ev_rets(uint8_t *image, uint32_t answers);                                                  /* $fe681a */
uint16_t aes_ev_mchk(uint8_t *image, uint32_t moblk);                                                /* $fe695c */
int16_t aes_ev_dclick(uint8_t *image, int16_t rate, int16_t set);                                    /* $fe6c5e */
#endif

#endif /* TOS102US_AES_EVLIB_H */
