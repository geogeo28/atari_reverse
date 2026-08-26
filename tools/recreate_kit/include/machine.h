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

/* 68k `ror.l #n,Dn` / `ror.l Dm,Dn` — the mirror of the above, TOTAL on exactly the same terms: the
 * `& 31` is the register form's own mod, and the count of 0 is the 68000's no-op where C's
 * `value << 32` is undefined. Both notes above apply here word for word, the immediate form's
 * 0-means-8 encoding included.
 *
 * It is spelt as the right rotate it is rather than as `rotate_left32(value, 32 - count)`, which is
 * the same VALUE for every count. The reason is cycles: the 68000's register-form rotate costs two
 * per bit turned, so a caller whose count is a small right rotation — a sprite's sub-word shift is
 * the low nibble of a screen x — pays for 0..15 bits here and for 17..32 through the mirror. Wonder
 * Boy's sprite blitters measured that difference; see projects/wonderboy/recreate/STATUS.md. */
static inline uint32_t rotate_right32(uint32_t value, unsigned count) {
    count &= 31;
    if (count == 0)
        return value;
    return (value >> count) | (value << (32 - count));
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

/* WHAT KEEPS A SPELT-OUT COPY RUN A POSTINCREMENT RUN. The 68000 has no block move, so a copy is a
 * run of `move.l (a0)+,(a1)+` at 20 cycles a longword, and a reconstruction spells that run out.
 * GCC will not leave it alone: its induction-variable pass sees ONE base with constant offsets and
 * addresses every copy after the first as `move.l d16(a0),d16(a1)` — 28 cycles for the pair against
 * the postincrement's 20 — batching the increments into a `lea` at the end of the run. Declaring the
 * cursor modified by an opaque `asm` hides that relationship, so each copy addresses through the
 * cursor it actually advances. It emits nothing, on the target and on the differential's host alike.
 *
 * IT APPLIES TO EVERY STEP THE RUN MAKES, not only to the copies. An adjustment made in the middle
 * of a run — a ring buffer's `cursor -= row_bytes` at a seam — folds into the NEXT copy's
 * displacement in exactly the same way if it is left outside the barrier: measured, `move.l
 * -128(a1),(a0)+ / lea -124(a1),a1` (24 + 8 cycles) where the barrier gives back the original's own
 * `lea -128(a1),a1` and a postincrement copy (8 + 20), 4 cycles a run. Barrier the cursor after any
 * adjustment that has to stay its own `lea`.
 *
 * AND THE CONSTRAINT SAYS WHICH REGISTER CLASS, on the one target where that is a distinction. A
 * plain `+r` is GENERAL_REGS on m68k — data registers included — and the m68k allocator takes it up:
 * it parks the cursor in a DATA register and shuffles it back, `move.l a0,d0 / movea.l d0,a0`, 8
 * cycles a time. How far it goes depends on how much else the body is holding, so the constraint is
 * pinned rather than trusted: measured on Wonder Boy's background blit (2026-08-26), `+r` puts two
 * such shuffles inside every scanline of the wrapped half and costs 64 bytes across src/scroll.c;
 * measured on the shape that run had BEFORE its sixteen bodies were split out, it put one around
 * EVERY copy — 248 bytes of body for what `+a` assembled in 126. `+a` is the address-register class
 * the postincrement addressing needs, so it is what the target asks for and there is nothing to
 * re-measure. `__m68k__` is what m68k-elf-gcc defines; every other host has no such class and takes
 * the generic barrier, where the run is portable C either way and only the differential's answers
 * matter.
 *
 * THE SAME TRICK ONE REGISTER CLASS OVER IS A LOOP COUNT, which is why the barrier is parameterised
 * by its class here rather than spelt a second time in a game file. A count GCC can read off the
 * source is not a counter to it at all: over a CONSTANT number of iterations it re-derives the
 * loop's end and spends `moveq #16 / subq.w #1,dN / bne` (14 cycles), or folds the test into the
 * ENCLOSING loop's as a `dbne` (26). An empty `asm` on the counter hides the literal and the loop
 * comes back as the `dbf` (10) the original closes with — measured on Wonder Boy's background fill
 * (src/scroll.c's clear_cells and draw_tiles), whose sixteen scanlines are a literal.
 *
 * ITS CLASS IS `+d`, and pinned for the mirror of the reason above: `dbf` counts a DATA register, so
 * a `+r` the m68k allocator chose to satisfy with an ADDRESS register would hold a register the loop
 * cannot close on and quietly buy nothing. Off the target there is no such class and no `dbf` to buy
 * — and `+d` is not even a valid constraint on every host (clang/arm64 rejects it outright) — so
 * both classes collapse to the generic barrier there.
 *
 * ONLY A LOOP WHOSE COUNT IS A CONSTANT needs COUNT_BARRIER: a count that arrives at run time is
 * already opaque to GCC and already closes with a `dbf`. Both macros emit nothing, on the target and
 * on the differential's host alike. */
#ifdef __m68k__
#define REGISTER_BARRIER_ADDRESS_CLASS "+a"
#define REGISTER_BARRIER_DATA_CLASS    "+d"
#else
#define REGISTER_BARRIER_ADDRESS_CLASS "+r"
#define REGISTER_BARRIER_DATA_CLASS    "+r"
#endif
#define REGISTER_BARRIER(var, constraint) __asm__("" : constraint(var))
/* A pointer walked by postincrement — the copy run above. */
#define CURSOR_BARRIER(cursor) REGISTER_BARRIER(cursor, REGISTER_BARRIER_ADDRESS_CLASS)
/* ...and a loop counter that has to stay a `dbf`. */
#define COUNT_BARRIER(count)   REGISTER_BARRIER(count, REGISTER_BARRIER_DATA_CLASS)

#endif /* RECREATE_KIT_MACHINE_H */
