/*
 * mem.h - the only two libc functions the portable core is allowed to call.
 *
 * The Atari build is -ffreestanding -nostdlib: m68k-elf ships no libc, and the
 * platform layer supplies these two itself.  Declaring them here rather than
 * including <string.h> keeps src/ compiling identically on the host and on the
 * target, and makes the dependency a one-line fact instead of a whole header.
 */
#ifndef BLACKICE_MEM_H
#define BLACKICE_MEM_H

#include <stddef.h>

void *memset(void *dst, int value, size_t count);
void *memcpy(void *dst, const void *src, size_t count);

#endif /* BLACKICE_MEM_H */
