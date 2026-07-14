/* intermission.c — intermission-screen block blitter (intermission_poll @ 0x12914).
 *
 * Despite the "poll" name (inferred from call context, unconfirmed), this reads no input: it is a
 * table-driven plain block copy. A 9-entry control table (INTERMISSION_BLITS, inline right after
 * the function body) drives nine rectangular copies from a pre-rendered screen-layout graphic in
 * buf_c into the draw buffer (physbase_tbl[flip_idx] + 0x990). Each entry is three words:
 *   src_off (u16, unsigned)   dst_off (i16, signed)   dims (u16)
 * dims packs the row count-1 in the high byte and the inner 8-byte-unit count-1 in the low nibble,
 * so a row copies ((dims & 0xf) + 1) * 8 contiguous bytes and there are ((dims >> 8) + 1) rows.
 * Source and destination both step one scanline (ROW_STRIDE) per row — the source is stored at
 * screen pitch. No mask/transparency; src and dst bases are both recomputed fresh each entry.
 */
#include <string.h>
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"

#define INTERMISSION_BLITS   0x1296a   /* inline control table: 9 x {src_off, dst_off, dims} words */
#define INTERMISSION_ENTRIES 9
#define INTERMISSION_SRC_OFF 0x32c80   /* source base = buf_c + this */
#define INTERMISSION_DST_OFF 0x990     /* dest base = physbase_tbl[flip_idx] + this */
#define BLIT_UNIT            8          /* bytes per inner unit (two longword moves) */

void g_intermission_poll(uint8_t *image) {
    int16_t flip_idx = (int16_t)be16(image + A_flip_idx);
    uint32_t dst_base = be32(image + A_physbase_tbl + flip_idx) + INTERMISSION_DST_OFF;
    uint32_t src_base = be32(image + A_buf_c) + INTERMISSION_SRC_OFF;

    uint32_t tbl = INTERMISSION_BLITS;
    for (int e = 0; e < INTERMISSION_ENTRIES; e++, tbl += 6) {
        uint32_t src = src_base + be16(image + tbl);                   /* unsigned src offset */
        uint32_t dst = dst_base + sign_ext16(be16(image + tbl + 2));   /* signed dst offset */
        uint16_t dims = be16(image + tbl + 4);
        uint32_t width = (uint32_t)((dims & 0xf) + 1) * BLIT_UNIT;
        int rows = (dims >> 8) + 1;
        for (int r = 0; r < rows; r++)
            memcpy(image + dst + r * ROW_STRIDE, image + src + r * ROW_STRIDE, width);
    }
}
