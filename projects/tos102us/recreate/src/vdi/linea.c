/* linea.c — Line-A primitives, entered by `jsr` with the register contract `test/vdi.py` declares.
 *
 * A primitive that answers in D0 RETURNS it; one answering in SEVERAL registers also takes a last
 * `uint32_t *results` it fills in the order its declaration names them (`declare_primitive`), because a
 * C function returns one register. Tier 1 compares every declared register; Tier 3 compares D0.
 */
#include <stdint.h>

#include "vdi/transcribed.h"
#include "vdi/vdi.h"

/* The order `test_vdi_linea_init.py` declares $a000's answer in. */
enum { INIT_D0, INIT_A0, INIT_A1, INIT_A2 };

/* $fc9f34 — $a000: the Line-A block's base in D0 and A0, $a000's font table in A1 and the opcode
 * table in A2. It reads nothing. Its four answers cost C a store each through `results`, over the bar, so
 * the ROM's own instructions ship (`entry.S`, where the region it lies in is laid out) — answering THAT
 * region's two tables, where this twin answers the ROM's. */
TRANSCRIBED_CORE
uint32_t linea_init(uint8_t *image, uint32_t *results)
{
    (void)image;
    results[INIT_D0] = LINEA_BASE;
    results[INIT_A0] = LINEA_BASE;
    results[INIT_A1] = LINEA_FONT_TABLE;
    results[INIT_A2] = LINEA_OPCODE_TABLE;
    return results[INIT_D0];
}
