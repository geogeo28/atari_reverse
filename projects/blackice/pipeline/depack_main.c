/* Test harness for stepix_depack: depack_main <packed> <raw_len> <out>.
 * Kept out of depack.c so the engine can link the depacker without a main(). */
#include <stdio.h>
#include <stdlib.h>

#include "depack.h"

#define ARG_COUNT 4         /* argv[0] plus packed file, raw length, output file */
#define EXIT_IO_ERROR   1
#define EXIT_USAGE      2
#define EXIT_BAD_STREAM 3   /* stepix_depack rejected the stream; nothing is written */

int main(int argc, char **argv)
{
    FILE *in, *out;
    int status;
    long packed_len;
    unsigned long raw_len;
    unsigned char *packed, *raw;

    if (argc != ARG_COUNT) {
        fprintf(stderr, "usage: %s <packed> <raw_len> <out>\n", argv[0]);
        return EXIT_USAGE;
    }
    raw_len = strtoul(argv[2], NULL, 10);

    in = fopen(argv[1], "rb");
    if (!in) { perror(argv[1]); return EXIT_IO_ERROR; }
    fseek(in, 0, SEEK_END);
    packed_len = ftell(in);
    fseek(in, 0, SEEK_SET);
    packed = malloc((size_t)packed_len + 1);
    raw = malloc(raw_len ? raw_len : 1);
    if (!packed || !raw) { fprintf(stderr, "out of memory\n"); return EXIT_IO_ERROR; }
    if (packed_len && fread(packed, 1, (size_t)packed_len, in) != (size_t)packed_len) {
        fprintf(stderr, "short read on %s\n", argv[1]);
        return EXIT_IO_ERROR;
    }
    fclose(in);

    status = stepix_depack(packed, (unsigned long)packed_len, raw, raw_len);
    if (status != STEPIX_DEPACK_OK) {
        fprintf(stderr, "%s: malformed LZSS stream\n", argv[1]);
        return EXIT_BAD_STREAM;
    }

    out = fopen(argv[3], "wb");
    if (!out) { perror(argv[3]); return EXIT_IO_ERROR; }
    if (raw_len && fwrite(raw, 1, raw_len, out) != raw_len) {
        fprintf(stderr, "short write\n");
        return EXIT_IO_ERROR;
    }
    fclose(out);
    free(packed);
    free(raw);
    return 0;
}
