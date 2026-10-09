/* aes/shlib.h — gemshlib's SCREEN SWITCHES and the shell's BAND (`src/aes/shlib.c`): what sh_main (`$feb0e6`, band
 * 5's last wave) does round a program it launches.
 *
 *   $fead5a sh_tographic()                 the AES's two vectors retaken (retake, under the mask), the workstation
 *                                          put in graphics, the whole screen the clip, the screen's save buffer
 *                                          allocated, the busy mouse set, the mouse counted on — D0: 1
 *   $fead82 sh_toalpha()                   the arrow set, the critical-error vector given back (giveerr, under the
 *                                          mask), the mouse hidden, the save buffer freed, the workstation left in
 *                                          text mode — D0: 1
 *   $feada0 sh_draw(command, object, depth) while a GEM program is being launched and the desk is not: the launch
 *                                          band's text pointed at `command` and the band drawn from `object`
 *   $feaddc sh_show(command)               sh_draw of the band's objects 1 and 2 — the routine sh_main hands sh_find
 *                                          ($feb272 `move.l #$feaddc,(sp)`), called over the path found
 *
 * ALCYON C, each entered by a Line-F call over the frame its caller pushed (sh_show by sh_find's `jsr (a0)`).
 */
#ifndef TOS102US_AES_SHLIB_H
#define TOS102US_AES_SHLIB_H

#include <stdint.h>

/* What both screen switches answer ($fead7e, $fead9c `moveq #1,d0`). */
#define SH_SWITCHED           1
/* gsx_graphic's argument: the workstation in graphics, or back in text mode. */
#define SH_GRAPHICS           1          /* ($fead64 move.w #1,(sp))                                           */
#define SH_TEXT               0          /* ($fead98 clr.w (sp))                                               */

/* sh_show's walk: the band's objects from the first to the one before the last ($feade0 move.w #1; $feadfa cmpi.w
 * #3 / blt), each drawn alone ($feade8 clr.w (sp): depth 0). */
#define SH_SHOW_FIRST         1
#define SH_SHOW_END           3
#define SH_SHOW_DEPTH         0

#ifndef __ASSEMBLER__
int16_t aes_sh_tographic(uint8_t *image);                                                             /* $fead5a */
int16_t aes_sh_toalpha(uint8_t *image);                                                               /* $fead82 */
void aes_sh_draw(uint8_t *image, uint32_t command, int16_t object, int16_t depth);                    /* $feada0 */
void aes_sh_show(uint8_t *image, uint32_t command);                                                   /* $feaddc */
#endif

#endif /* TOS102US_AES_SHLIB_H */
