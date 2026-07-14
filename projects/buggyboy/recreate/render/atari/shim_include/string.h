/* Minimal freestanding <string.h> for the Atari demo build (m68k-elf has no libc).
 * Only the three the reconstructed cores call; defined in main.c. */
#ifndef BB_SHIM_STRING_H
#define BB_SHIM_STRING_H
void *memcpy(void *dst, const void *src, unsigned long n);
void *memmove(void *dst, const void *src, unsigned long n);
void *memset(void *dst, int c, unsigned long n);
#endif
