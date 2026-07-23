/* Minimal freestanding <string.h> for the on-target program builds (m68k-elf has no libc).
 * Only what the HUD core calls; defined in main.c. */
#ifndef RM_SHIM_STRING_H
#define RM_SHIM_STRING_H
void *memcpy(void *dst, const void *src, unsigned long n);
void *memmove(void *dst, const void *src, unsigned long n);
void *memset(void *dst, int c, unsigned long n);
#endif
