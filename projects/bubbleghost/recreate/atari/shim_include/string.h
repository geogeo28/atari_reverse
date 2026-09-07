/* Minimal freestanding <string.h> for the Atari PRG build (m68k-elf ships no libc).
 *
 * Only what the cores and the kit's headers call; defined in bubble_backend.c. The kit's `os.h`
 * includes <string.h> for the two `memcpy` calls in its staged-file model — which this build
 * replaces — but the include happens before the shadow can say so, so the header has to exist.
 * GCC also synthesises calls to `memcpy` and `memset` out of struct assignments and fixed-size
 * copies even where no source line says so, which is why all three are declared and not just the
 * ones that are spelt.
 */
#ifndef BUBBLEGHOST_SHIM_STRING_H
#define BUBBLEGHOST_SHIM_STRING_H
void *memcpy(void *dst, const void *src, unsigned long n);
void *memmove(void *dst, const void *src, unsigned long n);
void *memset(void *dst, int c, unsigned long n);
#endif
