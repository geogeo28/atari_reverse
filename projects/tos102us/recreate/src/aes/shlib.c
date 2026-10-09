/* shlib.c — gemshlib's SCREEN SWITCHES and the shell's BAND (`aes/shlib.h`): sh_tographic, sh_toalpha, sh_draw and
 * sh_show. Alcyon C in the ROM, ported over its own order.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/ctrl.h"
#include "aes/fslib.h"
#include "aes/gemdosif.h"
#include "aes/gemgraf.h"
#include "aes/gsx.h"
#include "aes/gsxif.h"
#include "aes/objdraw.h"
#include "aes/shlib.h"
#include "aes/switch.h"

/* $fead5a — sh_tographic: back from a program that owned the screen. The trap #2 vector and the critical-error
 * handler are GEM's again first — retaken with the interrupts masked — then the workstation's graphics, the clip,
 * the save buffer, the busy mouse and the mouse's count. */
int16_t aes_sh_tographic(uint8_t *image)
{
    aes_spl7_save(image);
    (void)aes_retake(image);
    aes_spl_restore(image);
    aes_gsx_graphic(image, SH_GRAPHICS);
    (void)aes_gsx_sclip(image, AES_GL_RSCREEN);
    aes_gsx_malloc(image);
    aes_gsx_mfset(image, be32(image + AES_AD_HGMICE));
    aes_ratinit(image);
    return SH_SWITCHED;
}

/* $fead82 — sh_toalpha: the screen handed to a program that is not GEM's. The arrow first, then the critical-error
 * handler given back to whoever had it (masked), the mouse off, the save buffer freed and the workstation in text. */
int16_t aes_sh_toalpha(uint8_t *image)
{
    aes_gsx_mfset(image, be32(image + AES_AD_ARMICE));
    aes_spl7_save(image);
    (void)aes_giveerr(image);
    aes_spl_restore(image);
    aes_gsx_moff(image);
    aes_gsx_mfree(image);
    aes_gsx_graphic(image, SH_TEXT);
    return SH_SWITCHED;
}

/* $feada0 — sh_draw: nothing unless a GEM program is being launched and the desk is not the one running. The band's
 * tree is read BEFORE the clip is set ($feadb4), its text pointer stored through ad_pfile after. */
void aes_sh_draw(uint8_t *image, uint32_t command, int16_t object, int16_t depth)
{
    uint32_t band;

    if (!be16(image + AES_GL_SHGEM) || be16(image + AES_SH_DODEF))
        return;
    band = be32(image + AES_AD_STDESK);
    (void)aes_gsx_sclip(image, AES_GL_RSCREEN);
    set_bus_long(image, be32(image + AES_AD_PFILE), command);
    aes_ob_draw(image, band, object, depth);
}

/* $feaddc — sh_show: the band's two objects drawn with `command`, each alone. */
void aes_sh_show(uint8_t *image, uint32_t command)
{
    int16_t object;

    for (object = SH_SHOW_FIRST; object < SH_SHOW_END; object++)
        aes_sh_draw(image, command, object, SH_SHOW_DEPTH);
}
