/* st.h — Atari ST hardware byte-order accessors.
 *
 * The framebuffer and the static asset tables (palette fills, mask/ink streams) are ST hardware
 * data: big-endian, plane-interleaved. That is NOT "game state" — it is a fixed hardware format — so
 * remaster reads/writes it byte-accurately, exactly like the real machine. (Native game state lives
 * in game.h structs; only these hardware bytes go through here.)
 *
 * On the m68k target the machine IS big-endian, so each accessor is one aligned move. On a
 * little-endian test host we assemble the big-endian order byte by byte, so the bytes we compare
 * against recreate's output are identical either way.
 */
#ifndef RM_ST_H
#define RM_ST_H

#include <stdint.h>

#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
static inline uint16_t be16(const uint8_t *p) { return *(const uint16_t *)p; }
static inline uint32_t be32(const uint8_t *p) { return *(const uint32_t *)p; }
static inline void wr16(uint8_t *p, uint16_t v) { *(uint16_t *)p = v; }
static inline void wr32(uint8_t *p, uint32_t v) { *(uint32_t *)p = v; }
#else
static inline uint16_t be16(const uint8_t *p) { return (uint16_t)((p[0] << 8) | p[1]); }
static inline uint32_t be32(const uint8_t *p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
}
static inline void wr16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }
static inline void wr32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8);  p[3] = (uint8_t)v;
}
#endif

/* Duplicate a 16-bit plane word into both halves of a long (the 68k mask/ink broadcast). */
static inline uint32_t dup16(uint16_t w) { return ((uint32_t)w << 16) | w; }
/* Sign-extend a 16-bit table offset to a signed index (68k adda.w / word displacement). */
static inline int32_t sx16(uint16_t w) { return (int32_t)(int16_t)w; }

#endif /* RM_ST_H */
