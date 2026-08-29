/* Minimal freestanding <string.h> for the Atari PRG build (m68k-elf ships no libc).
 * Only what the cores and the kit's headers call; defined in zynaps_backend.c.
 *
 * ../src/video.c calls memset, ../src/text.c calls memmove, and GCC synthesises calls to memcpy
 * out of struct assignments and fixed-size copies even where no source line says so — which is why
 * all three are declared here and not just the two that are spelt.
 */
#ifndef ZYNAPS_SHIM_STRING_H
#define ZYNAPS_SHIM_STRING_H
void *memcpy(void *dst, const void *src, unsigned long n);
void *memmove(void *dst, const void *src, unsigned long n);
void *memset(void *dst, int c, unsigned long n);
#endif
