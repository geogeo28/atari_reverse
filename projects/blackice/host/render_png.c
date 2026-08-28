/*
 * render_png.c - a minimal indexed-colour PNG writer.
 *
 * Deflate is used in its "stored" mode: no compression, which keeps the writer
 * to a CRC and an Adler sum and makes the output byte-identical on every host.
 * The golden-frame test hashes these files, so reproducibility matters far
 * more than size here.
 */
#include <stdio.h>
#include <string.h>

#include "render_png.h"
#include "c2p.h"
#include "render.h"

#define PNG_BIT_DEPTH           8
#define PNG_COLOUR_TYPE_INDEXED 3
#define DEFLATE_STORED_MAX      65535
#define ZLIB_CMF                0x78    /* deflate, 32 KB window */
#define ZLIB_FLG                0x01    /* no dictionary, check bits valid */
#define ADLER_MODULUS           65521

static const uint8_t PNG_SIGNATURE[8] = { 137, 'P', 'N', 'G', '\r', '\n', 26, '\n' };

static uint32_t crc32_of(const uint8_t *data, size_t len, uint32_t crc)
{
    static const uint32_t CRC32_POLYNOMIAL = 0xedb88320u;
    size_t i;
    int bit;

    for (i = 0; i < len; ++i) {
        crc ^= data[i];
        for (bit = 0; bit < 8; ++bit) {
            crc = (crc >> 1) ^ (CRC32_POLYNOMIAL & (uint32_t)(-(int32_t)(crc & 1)));
        }
    }
    return crc;
}

static void put_be32(uint8_t *out, uint32_t value)
{
    out[0] = (uint8_t)(value >> 24);
    out[1] = (uint8_t)(value >> 16);
    out[2] = (uint8_t)(value >> 8);
    out[3] = (uint8_t)value;
}

static int write_chunk(FILE *file, const char *type, const uint8_t *data, size_t len)
{
    uint8_t header[4];
    uint8_t trailer[4];
    uint32_t crc;

    put_be32(header, (uint32_t)len);
    if (fwrite(header, 1, 4, file) != 4 || fwrite(type, 1, 4, file) != 4) {
        return -1;
    }
    if (len && fwrite(data, 1, len, file) != len) {
        return -1;
    }
    crc = crc32_of((const uint8_t *)type, 4, 0xffffffffu);
    crc = crc32_of(data, len, crc) ^ 0xffffffffu;
    put_be32(trailer, crc);
    return fwrite(trailer, 1, 4, file) == 4 ? 0 : -1;
}

/* Wrap raw bytes in a zlib stream made only of stored deflate blocks. */
static size_t zlib_stored(const uint8_t *raw, size_t raw_len, uint8_t *out)
{
    uint32_t adler_low = 1;
    uint32_t adler_high = 0;
    size_t written = 0;
    size_t offset = 0;
    size_t i;

    out[written++] = ZLIB_CMF;
    out[written++] = ZLIB_FLG;
    while (offset < raw_len) {
        size_t block = raw_len - offset;
        int final;

        if (block > DEFLATE_STORED_MAX) {
            block = DEFLATE_STORED_MAX;
        }
        final = (offset + block == raw_len);
        out[written++] = (uint8_t)(final ? 1 : 0);
        out[written++] = (uint8_t)(block & 0xff);
        out[written++] = (uint8_t)(block >> 8);
        out[written++] = (uint8_t)(~block & 0xff);
        out[written++] = (uint8_t)((~block >> 8) & 0xff);
        memcpy(out + written, raw + offset, block);
        written += block;
        offset += block;
    }
    for (i = 0; i < raw_len; ++i) {
        adler_low = (adler_low + raw[i]) % ADLER_MODULUS;
        adler_high = (adler_high + adler_low) % ADLER_MODULUS;
    }
    put_be32(out + written, (adler_high << 16) | adler_low);
    return written + 4;
}

int render_png_write(const char *path, const uint8_t *planar)
{
    /* One filter byte plus one index byte per pixel, per row. */
    static uint8_t raw[(size_t)SCREEN_H * (SCREEN_W + 1)];
    static uint8_t stream[sizeof(raw) + sizeof(raw) / DEFLATE_STORED_MAX * 5 + 16];
    uint8_t ihdr[13];
    uint8_t plte[PALETTE_SIZE * 3];
    size_t raw_len = 0;
    size_t stream_len;
    uint16_t x, y;
    int i;
    FILE *file;
    int result = -1;

    for (y = 0; y < SCREEN_H; ++y) {
        raw[raw_len++] = 0;                         /* filter type 0: none */
        for (x = 0; x < SCREEN_W; ++x) {
            raw[raw_len++] = planar_pixel(planar, x, y);
        }
    }
    stream_len = zlib_stored(raw, raw_len, stream);

    put_be32(ihdr, SCREEN_W);
    put_be32(ihdr + 4, SCREEN_H);
    ihdr[8] = PNG_BIT_DEPTH;
    ihdr[9] = PNG_COLOUR_TYPE_INDEXED;
    ihdr[10] = 0;
    ihdr[11] = 0;
    ihdr[12] = 0;
    for (i = 0; i < PALETTE_SIZE; ++i) {
        plte[i * 3 + 0] = g_palette_rgb[i][0];
        plte[i * 3 + 1] = g_palette_rgb[i][1];
        plte[i * 3 + 2] = g_palette_rgb[i][2];
    }

    file = fopen(path, "wb");
    if (!file) {
        return -1;
    }
    if (fwrite(PNG_SIGNATURE, 1, sizeof(PNG_SIGNATURE), file) == sizeof(PNG_SIGNATURE)
        && write_chunk(file, "IHDR", ihdr, sizeof(ihdr)) == 0
        && write_chunk(file, "PLTE", plte, sizeof(plte)) == 0
        && write_chunk(file, "IDAT", stream, stream_len) == 0
        && write_chunk(file, "IEND", 0, 0) == 0) {
        result = 0;
    }
    fclose(file);
    return result;
}
