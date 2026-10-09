/* aes/deskleaf.h — THREE LEAVES OF THE DESK'S RANGE that band 5's code calls (`src/aes/deskleaf.c`); the rest of the
 * desk is band 6's.
 *
 *   $fdbae0 app_reschange(device)  a resolution change asked for: the device code kept and the change flagged —
 *                                  D0 1 — unless it is the device in use (D0.w 0). gem_read_inf's caller ($fda53c)
 *   $fdbecc set_defdrv()           the current drive made C: when the drive map has one (D0 1), else A: (D0.w 0).
 *                                  gem_main's caller ($fda246)
 *   $fde33c desk_rsrc_free()       the desk's own rsrc_free BINDING: rs_free of the desk's global[], then a yield
 *                                  (dsptch) — what the AES's trap would have done — and rs_free's answer
 *
 * ALCYON C, each entered by a Line-F call over the frame its caller pushed. `set_defdrv` and `desk_rsrc_free` are
 * `ctx` names (read from the bodies); app_reschange is GEM's own.
 */
#ifndef TOS102US_AES_DESKLEAF_H
#define TOS102US_AES_DESKLEAF_H

#include <stdint.h>

/* The drive map's bit set_defdrv tests, and the drives it makes current. */
#define DRIVE_C_BIT           0x0004     /* ($fdbed2 and.w #4,d0)                                              */
#define DRIVE_A               0          /* ($fdbee4 clr.w (sp))                                               */
#define DRIVE_C               2          /* ($fdbed8 move.w #2,(sp))                                           */
/* ...what it answers: whether C: is the drive it made current. */
#define DEFDRV_IS_C           1          /* ($fdbede moveq #1,d0)                                              */
#define DEFDRV_IS_A           0          /* ($fdbee8 clr.w d0)                                                 */
/* app_reschange's answer, which is also the flag it raises (gl_rschange): a change of resolution asked for. */
#define RESCHANGE_NONE        0          /* ($fdbaf0 clr.w d0)                                                 */
#define RESCHANGE_ASKED       1          /* ($fdbafe move.w #1,$890a; $fdbb06 moveq #1,d0)                     */

#ifndef __ASSEMBLER__
int16_t aes_app_reschange(uint8_t *image, int16_t device);                                            /* $fdbae0 */
int16_t aes_set_defdrv(uint8_t *image);                                                               /* $fdbecc */
int16_t aes_desk_rsrc_free(uint8_t *image);                                                           /* $fde33c */
#endif

#endif /* TOS102US_AES_DESKLEAF_H */
