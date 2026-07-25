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

/* Semantic aliases for the two roles a 32-bit word plays in the ST render code (both are uint32_t,
 * which reads ambiguously): a byte offset/cursor into a buffer, and a 4-plane 16-pixel longword
 * (two plane words packed). Pointers stay uint8_t*, single plane words stay uint16_t.
 *
 * Pointer-walking rule (host-64 vs target-32): the m68k target is 32-bit, so a cursor `base + off`
 * and every per-row delta applied to it wrap mod 2^32 for free. A 64-bit host pointer does NOT wrap,
 * so any delta added straight to a real pointer must carry its true sign (int32_t / sx16) — a negative
 * delta stored unsigned is a ~4 GB forward walk, not a step back. The running offsets themselves stay
 * non-negative (screen overdraw / staged src guarantee it), so forming `base + (Offset)off` — compute
 * the 32-bit offset first, then widen it onto the base — reads the same byte on both. */
typedef uint32_t Offset;
typedef uint32_t Plane4;

/* be16/be32 — read a 16/32-bit big-endian value at p; wr16/wr32 — write one. The file header
 * explains the two builds: native aligned moves on the m68k target, byte-assembly on a host. */
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

/* TOS's free-running 200 Hz counter (_hz_200, system variable 0x4BA) — the finest clock the target
 * offers without programming a timer, so every on-target cost measurement reads it (the sweep's cost
 * bench, the cadence trace's sub-vblank render clock). SUPERVISOR ONLY: low memory bus-errors from user
 * mode, so a user-mode reader wraps the load in a Supexec excursion. Target-only, but harmless on a
 * host build that never expands it. */
#define SYS_HZ200 (*(volatile uint32_t *)0x4BAUL)

/* Duplicate a 16-bit plane word into both halves of a long (the 68k mask/ink broadcast). */
static inline Plane4 dup16(uint16_t w) { return ((Plane4)w << 16) | w; }
/* Sign-extend a 16-bit table offset to a signed index (68k adda.w / word displacement). */
static inline int32_t sx16(uint16_t w) { return (int32_t)(int16_t)w; }
/* Replace the low byte of a word, keeping its high byte (the 68k `move.b`/`add.b` on a word reg). */
static inline uint16_t set_low_byte(uint16_t word, uint8_t lo) { return (uint16_t)((word & 0xff00) | lo); }

#endif /* RM_ST_H */
