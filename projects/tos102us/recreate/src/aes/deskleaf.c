/* deskleaf.c — THREE LEAVES OF THE DESK'S RANGE (`aes/deskleaf.h`): app_reschange, set_defdrv and the desk's
 * rsrc_free binding. Alcyon C in the ROM, ported over its own order.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/deskleaf.h"
#include "aes/gemdosif.h"
#include "aes/gsxif.h"
#include "aes/resource.h"
#include "aes/switch.h"

/* $fdbae0 — app_reschange: the device code compared as a WORD with the one in use. */
int16_t aes_app_reschange(uint8_t *image, int16_t device)
{
    if ((uint16_t)device == be16(image + AES_GL_RESTYPE))
        return RESCHANGE_NONE;
    wr16(image + AES_GL_RESTYPE, (uint16_t)device);
    wr16(image + AES_GL_RSCHANGE, RESCHANGE_ASKED);
    return RESCHANGE_ASKED;
}

/* $fdbecc — set_defdrv: the drive map (isdrive's Dsetdrv of the current drive) asked for C:. */
int16_t aes_set_defdrv(uint8_t *image)
{
    if (aes_isdrive(image) & DRIVE_C_BIT) {
        (void)aes_dos_sdrv(image, AES_SET_DEFDRV_C_RETURN, DRIVE_C);
        return DEFDRV_IS_C;
    }
    (void)aes_dos_sdrv(image, AES_SET_DEFDRV_A_RETURN, DRIVE_A);
    return DEFDRV_IS_A;
}

/* $fde33c — the desk's rsrc_free: the implementation over the desk's own global[], then the dispatch every AES call
 * ends on, and the implementation's answer. */
int16_t aes_desk_rsrc_free(uint8_t *image)
{
    int16_t freed = aes_rs_free(image, AES_DESK_APP_GLOBAL);

    aes_dsptch(image);
    return freed;
}
