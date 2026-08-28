/*
 * hash.h - FNV-1a, the one hash the project uses.
 *
 * State hashes are how a replay proves itself: the same script must produce the
 * same number twice, and a run that diverges says so at the tick it diverged.
 * Every hashed thing goes through here so there is one set of constants and one
 * byte order, rather than a copy per file that can quietly disagree.
 *
 * These are FUNCTIONS, not inline: FNV's step is a 32-bit multiply, which on the
 * 68000 is a __mulsi3 call, and keeping it in one translation unit is what lets
 * the Makefile's libgcc gate exempt exactly that one object and hold every other
 * object in src/ to no libgcc arithmetic at all.  Nothing hashes on the target -
 * this exists for the host replay - so the extra `jsr` costs nothing that runs.
 */
#ifndef BLACKICE_HASH_H
#define BLACKICE_HASH_H

#include <stdint.h>

#define FNV_OFFSET_BASIS 2166136261u
#define FNV_PRIME        16777619u

/* Fold one byte into the hash. */
uint32_t fnv_byte(uint32_t hash, uint8_t value);

/* Fold four bytes, most significant first, so the digest does not depend on
 * the host's byte order. */
uint32_t fnv_word(uint32_t hash, uint32_t value);

/* Fold a run of bytes. */
uint32_t fnv_bytes(uint32_t hash, const uint8_t *data, uint32_t count);

#endif /* BLACKICE_HASH_H */
