/* machine.h — big-endian accessors over the flat 68000 memory image.
 *
 * The image is a byte array whose indices are Ghidra addresses (see oracle/loader.py).
 * Multi-byte access must preserve the 68000's big-endian byte order.
 *
 * On a big-endian target (the m68k-elf PRG build) that byte order IS the machine's own, so each
 * accessor is just an aligned native load/store — and we emit exactly that, one `move.w`/`move.l`,
 * instead of the byte-shuffle GCC would otherwise generate. This is the hot path: every field read
 * in every draw/blit routine goes through here, so a 4-8x-cheaper access is a large, uniform win.
 * These accesses are all even-aligned (the original ran on a 68000, which faults on misalignment;
 * our reads mirror its accesses). On a little-endian host (the differential-test .so) we keep the
 * portable byte assembly, so the verified behaviour is byte-identical either way.
 */
#ifndef RECREATE_KIT_MACHINE_H
#define RECREATE_KIT_MACHINE_H

#include <stdint.h>

#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
/* Big-endian target (68000): the image byte order is native — direct aligned access. */
static inline uint16_t be16(const uint8_t *ptr) { return *(const uint16_t *)ptr; }
static inline uint32_t be32(const uint8_t *ptr) { return *(const uint32_t *)ptr; }
static inline void wr16(uint8_t *ptr, uint16_t value) { *(uint16_t *)ptr = value; }
static inline void wr32(uint8_t *ptr, uint32_t value) { *(uint32_t *)ptr = value; }
#else
/* Little-endian host (differential-test .so): assemble the big-endian order byte by byte. */
static inline uint16_t be16(const uint8_t *ptr) { return (uint16_t)((ptr[0] << 8) | ptr[1]); }
static inline uint32_t be32(const uint8_t *ptr) {
    return ((uint32_t)ptr[0] << 24) | ((uint32_t)ptr[1] << 16) | ((uint32_t)ptr[2] << 8) | ptr[3];
}
static inline void wr16(uint8_t *ptr, uint16_t value) { ptr[0] = (uint8_t)(value >> 8); ptr[1] = (uint8_t)value; }
static inline void wr32(uint8_t *ptr, uint32_t value) {
    ptr[0] = (uint8_t)(value >> 24); ptr[1] = (uint8_t)(value >> 16);
    ptr[2] = (uint8_t)(value >> 8);  ptr[3] = (uint8_t)value;
}
#endif

/* Sign-extend a 16-bit register word to a 32-bit address delta (68k adda.w / word EA). */
static inline uint32_t sign_ext16(uint32_t value) { return (uint32_t)(int32_t)(int16_t)value; }

/* 68k `.b` op on a word register: the result byte replaces the low byte, and the high byte is
 * left untouched (byte ops don't carry into it) — e.g. addq.b / asl.b applied to a data reg. */
static inline uint16_t set_low_byte(uint16_t word, uint8_t byte) {
    return (uint16_t)((word & 0xFF00u) | byte);
}

#endif /* RECREATE_KIT_MACHINE_H */