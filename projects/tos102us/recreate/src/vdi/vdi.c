/* vdi.c — VDI functions, entered as `$fca9f6` (the dispatcher) leaves the machine.
 *
 * A function takes no arguments and returns nothing: it reads contrl/intin/ptsin through the Line-A
 * pointers, its attributes through LINEA_CUR_WORK, and answers into intout/ptsout and contrl's two
 * counts (`include/vdi/vdi.h`). So every core here is `void f(uint8_t *image)`.
 */
#include <stdint.h>

#include "machine.h"
#include "vdi/vdi.h"

/* $fcb45c — vsf_perimeter (opcode 104): outline filled areas when intin[0] is nonzero.
 *
 * The flag is stored NORMALISED to 0/1, into intout[0] and then the workstation, and contrl[4] (one
 * word answered) last — the ROM's order, which only shows when the arrays overlap each other. */
void vdi_vsf_perimeter(uint8_t *image)
{
    uint32_t work = be32(image + LINEA_CUR_WORK);
    uint32_t intout = be32(image + LINEA_INTOUT);
    uint16_t outlined = be16(image + be32(image + LINEA_INTIN)) != 0;

    wr16(image + intout, outlined);
    wr16(image + work + WS_FILL_PER, outlined);
    wr16(image + be32(image + LINEA_CONTRL) + CONTRL_N_INTOUT, 1);
}
