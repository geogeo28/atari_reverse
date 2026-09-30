/* vdi/escape.h — the VDI's ESCAPE (opcode 5; `src/vdi/escape.c`, and the `escape.S` that ships): contrl[5]
 * picks one of the arms below.
 *
 * A VDI function like any other (`void vdi_escape(uint8_t *image)`, entered as the dispatcher leaves the
 * machine), in the BIOS's range because nearly all of it is the BIOS console's own code: its jump table at
 * VDI_ESCAPE_TABLE ($fc4298) holds the addresses of the VT52 driver's escape bodies. The arm numbers are
 * the ROM's table indexes and its two compares past the table ($fc42c0, $fc42c6); the names are GEM's.
 */
#ifndef TOS102US_VDI_ESCAPE_H
#define TOS102US_VDI_ESCAPE_H

#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

/* ---- the arms, by contrl[5] ----------------------------------------------------------------------- */
#define VDI_ESCAPE_NOTHING        0      /* the table's own `rts`                ($fc444e)           */
#define VDI_ESCAPE_VQ_CHCELLS     1      /* rows, columns                         ($fc442e)           */
#define VDI_ESCAPE_V_EXIT_CUR     2      /* cursor locked, then ESC E             ($fc4460)           */
#define VDI_ESCAPE_V_ENTER_CUR    3      /* ESC E, then the cursor shown          ($fc445a)           */
#define VDI_ESCAPE_V_CURUP        4      /* ESC A                                 ($fc4468)           */
#define VDI_ESCAPE_V_CURDOWN      5      /* ESC B                                 ($fc4478)           */
#define VDI_ESCAPE_V_CURRIGHT     6      /* ESC C                                 ($fc448c)           */
#define VDI_ESCAPE_V_CURLEFT      7      /* ESC D                                 ($fc44a0)           */
#define VDI_ESCAPE_V_CURHOME      8      /* ESC H                                 ($fc44b0)           */
#define VDI_ESCAPE_V_EEOS         9      /* ESC J                                 ($fc44b8)           */
#define VDI_ESCAPE_V_EEOL         10     /* ESC K                                 ($fc44ca)           */
#define VDI_ESCAPE_VS_CURADDRESS  11     /* intin: row, column, both 1-based      ($fc44dc)           */
#define VDI_ESCAPE_V_CURTEXT      12     /* contrl[3] characters of intin to Bconout(CON:) ($fc44ee)  */
#define VDI_ESCAPE_V_RVON         13     /* ESC p                                 ($fc4510)           */
#define VDI_ESCAPE_V_RVOFF        14     /* ESC q                                 ($fc4516)           */
#define VDI_ESCAPE_VQ_CURADDRESS  15     /* row, column, both 1-based             ($fc451c)           */
#define VDI_ESCAPE_VQ_TABSTATUS   16     /* "a tablet": 1                         ($fc453c)           */
#define VDI_ESCAPE_V_HARDCOPY     17     /* XBIOS Scrdmp                          ($fc4450)           */
#define VDI_ESCAPE_V_DSPCUR       18     /* intin[0] = 0, then v_show_c           ($fc454e)           */
#define VDI_ESCAPE_V_RMCUR        19     /* v_hide_c                              ($fc455a)           */
/* ...and the two the ROM tests for past the table; every other number returns doing nothing. */
#define VDI_ESCAPE_V_OFFSET       101    /* the text screen's first line          ($fc42d0)           */
#define VDI_ESCAPE_V_FONTINIT     102    /* the console's font, from a header     ($fc4a42)           */

/* ---- what the inquiries answer: `VDI_ESCAPE_ANSWER_*`, the one prefix that is NOT an arm ---------- */
#define VDI_ESCAPE_ANSWER_CELLS_WORDS  2    /* vq_chcells' and vq_curaddress' contrl[4] ($fc4432)          */
#define VDI_ESCAPE_ANSWER_TABLET_WORDS 1    /* vq_tabstatus' contrl[4], and its answer ($fc453c moveq #1)  */
#define VDI_ESCAPE_ANSWER_TABLET       1

#ifndef __ASSEMBLER__
void vdi_escape(uint8_t *image);
#endif

#endif /* TOS102US_VDI_ESCAPE_H */
