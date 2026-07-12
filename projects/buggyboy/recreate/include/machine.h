/* machine.h — big-endian accessors over the flat 68000 memory image.
 *
 * The image is a byte array whose indices are Ghidra addresses (see oracle/loader.py).
 * The host is little-endian, so multi-byte access goes through these helpers to preserve
 * the 68000's big-endian byte order — never cast a struct over the image.
 */
#ifndef BB_MACHINE_H
#define BB_MACHINE_H

#include <stdint.h>

static inline uint16_t be16(const uint8_t *ptr) { return (uint16_t)((ptr[0] << 8) | ptr[1]); }
static inline uint32_t be32(const uint8_t *ptr) {
    return ((uint32_t)ptr[0] << 24) | ((uint32_t)ptr[1] << 16) | ((uint32_t)ptr[2] << 8) | ptr[3];
}
static inline void wr16(uint8_t *ptr, uint16_t value) { ptr[0] = (uint8_t)(value >> 8); ptr[1] = (uint8_t)value; }
static inline void wr32(uint8_t *ptr, uint32_t value) {
    ptr[0] = (uint8_t)(value >> 24); ptr[1] = (uint8_t)(value >> 16);
    ptr[2] = (uint8_t)(value >> 8);  ptr[3] = (uint8_t)value;
}

#endif /* BB_MACHINE_H */