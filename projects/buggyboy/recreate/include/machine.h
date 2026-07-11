/* machine.h — big-endian accessors over the flat 68000 memory image.
 *
 * The image is a byte array whose indices are Ghidra addresses (see oracle/loader.py).
 * The host is little-endian, so multi-byte access goes through these helpers to preserve
 * the 68000's big-endian byte order — never cast a struct over the image.
 */
#ifndef BB_MACHINE_H
#define BB_MACHINE_H

#include <stdint.h>

static inline uint16_t be16(const uint8_t *p) { return (uint16_t)((p[0] << 8) | p[1]); }
static inline uint32_t be32(const uint8_t *p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
}
static inline void wr16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }
static inline void wr32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8);  p[3] = (uint8_t)v;
}

#endif /* BB_MACHINE_H */