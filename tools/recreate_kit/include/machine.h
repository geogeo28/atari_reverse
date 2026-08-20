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

/* ...and the same one size down: 68k `ext.w Dn` after a `move.b`, which is how a signed BYTE field
 * — a sprite descriptor's height or width code, a sound effect's id — becomes an index. The whole
 * register is extended rather than only its low word, so the result is usable as an address delta
 * directly; a caller that wants the `ext.w` behaviour exactly (low word replaced, high half left
 * alone) composes this with set_low_word. */
static inline uint32_t sign_ext8(uint32_t value) { return (uint32_t)(int32_t)(int8_t)value; }

/* Move an address by a delta THE WAY THE 68000's ADDRESS ALU DOES: in 32 bits, wrapping. A host
 * pointer does not wrap, so `image + base + delta` walks off the image into host memory where the
 * original goes round its own address space — which is undefined behaviour rather than a divergence
 * the differential would report. So a reconstruction computes the whole address here first, and adds
 * `image` only to the result.
 *
 * The delta is unsigned because the 68000's add is: a `d16(An)` displacement or an `adda.w` operand
 * arrives already sign-extended to 32 bits (sign_ext16 above), and from there the wrap is the same
 * bits whichever way the value is read. */
static inline uint32_t addr_add(uint32_t base, uint32_t delta) { return base + delta; }

/* 68k `rol.l #n,Dn` / `rol.l Dm,Dn` — a 32-bit ROTATE, not a shift: the bits that leave the top come
 * back in at the bottom. Total for EVERY count a caller can hand it, which C's own shifts are not:
 *
 *   * `count & 31` is the 68000's register form. `rol.l Dm,Dn` rotates by `Dm mod 64`, and a 32-bit
 *     rotate is cyclic mod 32 — a rotate by 32 is the identity — so mod 64 and mod 32 give the same
 *     VALUE for every count, and the mask is exact rather than a clamp. (Only the flags tell 0 from
 *     32 apart, and the kit's differential does not compare them.) It also makes the count of 0 the
 *     68000's own no-op instead of C's undefined `value >> 32`, so a caller whose count is a runtime
 *     word — a phase, a distance — needs no guard of its own.
 *   * THE IMMEDIATE FORM'S COUNT IS NOT THE FIELD. `rol.l #n,Dn` encodes n in three bits with 0
 *     MEANING 8, so a caller transcribing the raw count field out of a disassembly must decode it
 *     first; handing this the field would rotate by nothing where the original rotates by a byte.
 *
 * No reconstruction reaches a count >= 32 today: the wonderboy scroll's runtime count is a phase word
 * the game masks to a nibble (plus the literal 16 the right edge substitutes for phase 0) and every
 * other caller passes a literal, so the mask is totality rather than a pinned case. */
static inline uint32_t rotate_left32(uint32_t value, unsigned count) {
    count &= 31;
    if (count == 0)
        return value;
    return (value << count) | (value >> (32 - count));
}

/* 68k `.b` op on a word register: the result byte replaces the low byte, and the high byte is
 * left untouched (byte ops don't carry into it) — e.g. addq.b / asl.b applied to a data reg. */
static inline uint16_t set_low_byte(uint16_t word, uint8_t byte) {
    return (uint16_t)((word & 0xFF00u) | byte);
}

/* The same idea one size up: a `.w` op on a LONGWORD register — `move.w`/`clr.w`/`move.w #imm,Dn`
 * — replaces the low word and leaves the high one alone. It matters wherever the caller's own high
 * half comes back out of a routine that only ever wrote words, which is how a 68000 routine returns
 * "a word" in a register the differential compares as a longword. */
static inline uint32_t set_low_word(uint32_t value, uint16_t low) {
    return (value & 0xFFFF0000u) | low;
}

/* THE X FLAG AN ORDINARY ADD OR SUBTRACT LEAVES. On the 68000, `add`/`sub`/`addq`/`subq`/`addi`/
 * `subi`/`neg` copy the carry (or borrow) into X as well as C, and `abcd`/`sbcd`/`addx`/`subx`/
 * `roxl`/`roxr` fold it back in — so a port that threads a flag from a producing routine to a
 * consuming one needs the producer's bit modelled, and these are that model.
 *
 * On a two's-complement machine the carry IS the wrap, so none of them needs a mask or a wider
 * intermediate: a sum that came out below its own augend carried, and a minuend below its
 * subtrahend borrowed. They are named rather than spelt at each site because `(a + b) < a` is the
 * shape a reader mistakes for a bounds check. `neg` is `word_sub_extend(0, value)`, which is set
 * unless the operand was zero. */
static inline unsigned word_add_extend(uint16_t augend, uint16_t addend) {
    return (uint16_t)(augend + addend) < augend;
}

static inline unsigned word_sub_extend(uint16_t minuend, uint16_t subtrahend) {
    return minuend < subtrahend;
}

static inline unsigned byte_add_extend(uint8_t augend, uint8_t addend) {
    return (uint8_t)(augend + addend) < augend;
}

static inline unsigned byte_sub_extend(uint8_t minuend, uint8_t subtrahend) {
    return minuend < subtrahend;
}

#endif /* RECREATE_KIT_MACHINE_H */
