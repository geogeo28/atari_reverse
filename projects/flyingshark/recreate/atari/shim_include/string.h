/* Minimal freestanding <string.h> for the Atari .PRG build — m68k-elf ships no libc, and
 * `-ffreestanding -nostdlib` is what makes that explicit rather than accidental.
 *
 * NO CORE INCLUDES IT ANY MORE, and that is the point rather than an argument for deleting it.
 * `../src/sprite.c` did, for a fixed-size 16-byte `memcpy` in the sprite blitter's innermost loop —
 * which `-ffreestanding` (hence `-fno-builtin`) compiled into a real `jsr` costing 588 cycles a
 * call, 802 calls a frame, and which the performance campaign replaced with four assignments
 * (`../../STATUS.md`, "On-target performance", lever 1). What still reaches these bodies is
 * `../flyshark_main.c`'s `memset`, and anything GCC may SYNTHESISE from a structure copy or an
 * array initialisation in any core (`-fno-tree-loop-distribute-patterns` stops it recognising a
 * hand-written loop and calling the loop's own name, but not this) — a missing body would be a link
 * error rather than a warning. The bodies are in ../flyshark_backend.c.
 *
 * Angle-bracket includes of <string.h> from a core find this file because build.sh puts
 * `shim_include` first on the include path and m68k-elf's own headers are reached with `-nostdinc`
 * off — this shadows nothing, it supplies what the freestanding toolchain does not.
 */
#ifndef FS_SHIM_STRING_H
#define FS_SHIM_STRING_H

void *memcpy(void *dst, const void *src, unsigned long n);
void *memmove(void *dst, const void *src, unsigned long n);
void *memset(void *dst, int c, unsigned long n);

#endif /* FS_SHIM_STRING_H */
