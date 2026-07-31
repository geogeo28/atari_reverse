/* Minimal freestanding <string.h> for the Atari PRG build (m68k-elf ships no libc).
 * Only what the kit's os.h staged-file model calls; defined in joust_main.c. */
#ifndef JOUST_SHIM_STRING_H
#define JOUST_SHIM_STRING_H
void *memcpy(void *dst, const void *src, unsigned long n);
void *memmove(void *dst, const void *src, unsigned long n);
void *memset(void *dst, int c, unsigned long n);
#endif
