/* Minimal freestanding <string.h> for the Atari .PRG build — m68k-elf ships no libc, and
 * `-ffreestanding -nostdlib` is what makes that explicit rather than accidental.
 *
 * ONE CORE INCLUDES IT: ../src/sprite.c, for the fixed-size `memcpy` that saves a plane's spill
 * bytes. The other two names are here because GCC may SYNTHESISE a call to either from a structure
 * copy or an array initialisation in any core (`-fno-tree-loop-distribute-patterns` stops it
 * recognising a hand-written loop and calling the loop's own name, but not this), and a missing
 * body would be a link error rather than a warning. The bodies are in ../flyshark_backend.c.
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
