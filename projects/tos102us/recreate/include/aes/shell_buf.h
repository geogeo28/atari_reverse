/* aes/shell_buf.h — the SHELL's and the SCRAP's string buffers (`src/aes/shell_buf.c`): scrp_read/scrp_write and
 * shel_read/shel_write/shel_get/shel_put, each a copy between a caller's buffer and one of the AES's own
 * (`aes/aes.h`: AES_SCRAP_PATH, AES_SHELL_BUFFER and AES_SHELL_TAIL, AES_SHELL_GEM_BUFFER).
 *
 * ALCYON C, entered by a Line-F call over the frame its caller pushed, each copy the utility layer's (`aes/strings.h`:
 * lstcpy for a NUL-ended string, LBCOPY for a counted one). The shel_* answer 1 (`moveq #1`); the scrp_* answer D0 as
 * lstcpy left it (its byte count), which no caller reads — the dispatcher's arms keep their own answer.
 */
#ifndef TOS102US_AES_SHELL_BUF_H
#define TOS102US_AES_SHELL_BUF_H

#include <stdint.h>

int16_t aes_sc_read(uint8_t *image, uint32_t path);                                                   /* $feac80 */
int16_t aes_sc_write(uint8_t *image, uint32_t path);                                                  /* $feac94 */
int16_t aes_sh_read(uint8_t *image, uint32_t command, uint32_t tail);                                /* $feaca8 */
int16_t aes_sh_write(uint8_t *image, int16_t doexec, int16_t isgem, int16_t isover, uint32_t command,
                     uint32_t tail);                                                                    /* $feacd4 */
int16_t aes_sh_get(uint8_t *image, uint32_t buffer, int16_t bytes);                                  /* $fead26 */
int16_t aes_sh_put(uint8_t *image, uint32_t data, int16_t bytes);                                    /* $fead40 */

#endif /* TOS102US_AES_SHELL_BUF_H */
