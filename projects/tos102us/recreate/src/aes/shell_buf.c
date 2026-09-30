/* shell_buf.c — the SHELL's and the SCRAP's string buffers (`aes/shell_buf.h`): six copies between a caller's buffer
 * and the AES's own, through the utility layer's copies (`aes/strings.h`), in the ROM's order.
 */
#include <stdint.h>

#include "machine.h"
#include "aes/aes.h"
#include "aes/shell_buf.h"
#include "aes/strings.h"

#define SHELL_ANSWER          1          /* `moveq #1,d0` ($feacd0)                                            */

static inline uint32_t buffer_at(const uint8_t *image, uint32_t pointer)
{
    return be32(image + pointer);
}

/* $feac80 — scrp_read: the scrap directory's path into the caller's `path`. */
int16_t aes_sc_read(uint8_t *image, uint32_t path)
{
    return aes_lstcpy(image, path, AES_SCRAP_PATH);
}

/* $feac94 — scrp_write: the caller's `path` made the scrap directory's. */
int16_t aes_sc_write(uint8_t *image, uint32_t path)
{
    return aes_lstcpy(image, AES_SCRAP_PATH, path);
}

/* $feaca8 — shel_read: the shell's command line, then its tail, 128 bytes each into the caller's. */
int16_t aes_sh_read(uint8_t *image, uint32_t command, uint32_t tail)
{
    aes_lbcopy(image, command, buffer_at(image, AES_SHELL_BUFFER), AES_SHELL_LINE_BYTES);
    aes_lbcopy(image, tail, buffer_at(image, AES_SHELL_TAIL), AES_SHELL_LINE_BYTES);
    return SHELL_ANSWER;
}

/* $feacd4 — shel_write: the caller's command line and tail into the shell's, and the requests sh_main acts on —
 * `doexec` as it is, AES_SH_ISDEF and AES_SH_DODEF cleared, `isgem` as a flag. `isover` is not read. */
int16_t aes_sh_write(uint8_t *image, int16_t doexec, int16_t isgem, int16_t isover, uint32_t command, uint32_t tail)
{
    (void)isover;
    aes_lbcopy(image, buffer_at(image, AES_SHELL_BUFFER), command, AES_SHELL_LINE_BYTES);
    aes_lbcopy(image, buffer_at(image, AES_SHELL_TAIL), tail, AES_SHELL_LINE_BYTES);
    wr16(image + AES_SH_DOEXEC, (uint16_t)doexec);
    wr16(image + AES_SH_ISDEF, 0);
    wr16(image + AES_SH_DODEF, 0);
    wr16(image + AES_SH_ISGEM, isgem != 0);
    return SHELL_ANSWER;
}

/* $fead26 — shel_get: `bytes` of the shell's GEM buffer into the caller's. */
int16_t aes_sh_get(uint8_t *image, uint32_t buffer, int16_t bytes)
{
    aes_lbcopy(image, buffer, AES_SHELL_GEM_BUFFER, bytes);
    return SHELL_ANSWER;
}

/* $fead40 — shel_put: `bytes` of the caller's into the shell's GEM buffer. */
int16_t aes_sh_put(uint8_t *image, uint32_t data, int16_t bytes)
{
    aes_lbcopy(image, AES_SHELL_GEM_BUFFER, data, bytes);
    return SHELL_ANSWER;
}
