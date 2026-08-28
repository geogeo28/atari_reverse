/*
 * hash.c - FNV-1a.  See include/hash.h for why it is a translation unit of its
 * own and not an inline in the header.
 */
#include "hash.h"

uint32_t fnv_byte(uint32_t hash, uint8_t value)
{
    return (hash ^ value) * FNV_PRIME;
}

uint32_t fnv_word(uint32_t hash, uint32_t value)
{
    hash = fnv_byte(hash, (uint8_t)(value >> 24));
    hash = fnv_byte(hash, (uint8_t)(value >> 16));
    hash = fnv_byte(hash, (uint8_t)(value >> 8));
    return fnv_byte(hash, (uint8_t)value);
}

uint32_t fnv_bytes(uint32_t hash, const uint8_t *data, uint32_t count)
{
    uint32_t i;

    for (i = 0; i < count; ++i) {
        hash = fnv_byte(hash, data[i]);
    }
    return hash;
}
