/* geminit.c — geminit's three LEAVES (`aes/geminit.h`): ini_dlongs, all_run and pinit. Alcyon C in the ROM, ported
 * over its own order.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/geminit.h"
#include "aes/mnlib.h"
#include "aes/objects.h"
#include "aes/strings.h"
#include "aes/switch.h"
#include "aes/wmupdate.h"

/* The ROM reaches four of the five through A5, THEGLO's base (`lea <offset>(a5),a0`): the offsets its instructions
 * carry, held to the absolute addresses the C stores. */
#define THEGLO_SHELL_LINE     8022       /* ($fda00a lea 8022(a5),a0)                                          */
#define THEGLO_SH_COMMAND     10198      /* ($fda014 lea 10198(a5),a0)                                         */
#define THEGLO_SH_PATH_BUFFER 7910       /* ($fda01e lea 7910(a5),a0)                                          */
#define THEGLO_SYSTEM_GLOBAL  7992       /* ($fda028 lea 7992(a5),a0)                                          */
_Static_assert(AES_SHELL_LINE == AES_THEGLO + THEGLO_SHELL_LINE && AES_SH_COMMAND == AES_THEGLO + THEGLO_SH_COMMAND,
               "the shell's two lines lie in THEGLO");
_Static_assert(AES_SH_PATH_BUFFER == AES_THEGLO + THEGLO_SH_PATH_BUFFER
               && AES_SYSTEM_GLOBAL == AES_THEGLO + THEGLO_SYSTEM_GLOBAL, "...and the path and global[]");

/* $fd9ffc — ini_dlongs: the five long pointers, in the ROM's order — the command line, its tail, the working path,
 * the AES's global[], and the screen's lock. */
void aes_ini_dlongs(uint8_t *image)
{
    wr32(image + AES_SHELL_BUFFER, AES_SHELL_LINE);
    wr32(image + AES_SHELL_TAIL, AES_SH_COMMAND);
    wr32(image + AES_SH_PATH_POINTER, AES_SH_PATH_BUFFER);
    wr32(image + AES_RS_SYSTEM_GLOBAL, AES_SYSTEM_GLOBAL);
    wr32(image + AES_AD_WINDSPB, AES_WIND_SPB);
}

/* $fda03e — all_run: a yield (the ROM's loop of one), then the screen's lock taken and given back — the caller
 * waits there for whoever holds it. It sets no D0 (what is left there is the release's — unsync's — and none of its
 * three callers reads it: $fda396, $fddea2 `moveq #1,d0`, $fe5e6c). */
void aes_all_run(uint8_t *image)
{
    int16_t yielded;

    for (yielded = 0; yielded < ALL_RUN_YIELDS; yielded++)
        aes_dsptch(image);
    (void)aes_wm_update(image, WM_BEG_UPDATE);
    (void)aes_wm_update(image, WM_END_UPDATE);
}

/* $fda3d6 — pinit: the PD at `pd` given its CDA, its pipe (the address of its own queue, read from the start) and a
 * blank name. Every other field is left as it is. */
void aes_pinit(uint8_t *image, uint32_t pd, uint32_t cda)
{
    set_bus_long(image, pd + PD_CDA, cda);
    set_bus_long(image, pd + PD_QUEUE_ADDRESS, pd + PD_QUEUE);
    set_bus_word(image, pd + PD_QUEUE_INDEX, 0);
    aes_bfill(image, PD_NAME_BYTES, PD_NAME_FILL, pd + PD_NAME);
}
