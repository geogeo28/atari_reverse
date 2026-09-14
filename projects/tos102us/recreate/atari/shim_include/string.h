/* Minimal freestanding <string.h> for every 68000 build of this reconstruction.
 *
 * m68k-elf ships no libc at all (its only include directory is GCC's own), and the kit's `os.h`
 * — which `include/addrs.h` pulls in for the YM2149's port addresses — includes <string.h>. So the
 * header has to exist before a single core compiles for the target.
 *
 * DECLARATIONS ONLY, and deliberately no definitions: nothing in this reconstruction calls any of
 * them yet, so an unused definition would be dead code inside the ROM image. GCC also SYNTHESISES
 * calls to memcpy/memset out of struct assignments and fixed-size copies where no source line says
 * so — which is why all three are declared rather than only what is spelt — and the day one of those
 * appears the build fails at LINK, naming the symbol, rather than compiling against a stub.
 *
 * The same shape as projects/zynaps/recreate/atari/shim_include/string.h, whose header comment
 * records the same three names for the same reason.
 */
#ifndef TOS102US_SHIM_STRING_H
#define TOS102US_SHIM_STRING_H

void *memcpy(void *dst, const void *src, unsigned long n);
void *memmove(void *dst, const void *src, unsigned long n);
void *memset(void *dst, int c, unsigned long n);

#endif /* TOS102US_SHIM_STRING_H */
