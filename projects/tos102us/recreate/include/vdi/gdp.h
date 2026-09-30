/* vdi/gdp.h — the GENERALIZED DRAWING PRIMITIVE (`src/vdi/gdp.c`): vdi_gdp, VDI opcode 11, which serves
 * contrl[5] = 1..10 through a C switch of longwords ($fd3954) whose arms are inline in it — the bar and the
 * circle and ellipse arms do their own work, every other arm calls its worker (`vdi/arcs.h`, `vdi/gtext.h`).
 * A contrl[5] outside 1..10 draws nothing (`VDI_GDP_FIRST` / `VDI_GDP_LAST`, `vdi/vdi.h`).
 */
#ifndef TOS102US_VDI_GDP_H
#define TOS102US_VDI_GDP_H

/* ---- contrl[5]: the arms the curve workers' own GDP numbers (`vdi/arcs.h`) do not name ------------------ */
#define VDI_GDP_BAR           1          /* vr_recfl, then its perimeter        ($fcbc0a)           */
#define VDI_GDP_JUSTIFIED     10         /* d_justified                         ($fcbd56)           */

/* ---- the bar's perimeter: its four corners and the first again ------------------------------------------ */
#define VDI_BAR_OUTLINE_POINTS 5         /* contrl[1]                           ($fcbc5a move.w #5) */

#ifndef __ASSEMBLER__
#include <stdint.h>

void vdi_gdp(uint8_t *image);                /* $fcbbcc, opcode 11 */
#endif /* __ASSEMBLER__ */

#endif /* TOS102US_VDI_GDP_H */
