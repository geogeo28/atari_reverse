/* stepix LZSS depacker and PAK directory layout -- shared by the engine and the tests. */
#ifndef STEPIX_DEPACK_H
#define STEPIX_DEPACK_H

/* PAK directory constants; see README.md for the byte-exact tables.
 * tests/test_readme_contract.py parses these lines and pins them to stepix.pack. */
#define PAK_MAGIC          "STPK"
#define PAK_FORMAT_VERSION 1
#define PAK_NAME_BYTES     8
#define PAK_HEADER_BYTES   8
#define PAK_ENTRY_BYTES    24
#define PAK_ALIGNMENT      2
#define PAK_METHOD_STORED  0
#define PAK_METHOD_LZSS    1

/* stepix_depack() return values. */
#define STEPIX_DEPACK_OK         0
#define STEPIX_DEPACK_BAD_STREAM 1

/* Expand `raw_len` bytes from the `packed_len`-byte LZSS stream at `src` into `dst`.
 * `dst` must have room for raw_len bytes.
 *
 * The stream ships with the game, but a corrupt one must not be able to walk outside the
 * buffers: a match token can name an offset that reaches before `dst`, or a length that
 * overruns `dst + raw_len`, and a truncated stream can read past `src + packed_len`. The
 * checks below are per token, not per byte, so the inner copy loop stays the shape the
 * 68000 wants. Returns STEPIX_DEPACK_OK, or STEPIX_DEPACK_BAD_STREAM with `dst` holding
 * whatever had been produced up to the bad token. */
int stepix_depack(const unsigned char *src, unsigned long packed_len,
                  unsigned char *dst, unsigned long raw_len);

#endif /* STEPIX_DEPACK_H */
