/* Minimal freestanding <string.h> for the Atari PRG build (m68k-elf ships no libc for -nostdlib).
 *
 * IT IS THE KIT'S HEADER THAT NEEDS THIS, NOT THE CORES. the kit's own `os.h` pulls
 * `<string.h>` in at its line 25 for its staged-file model, and every core under `../../src/` that reaches `os.h` — directly
 * or through `../include/bus.h` — inherits the include. Deleting this file on the grounds that
 * nothing under `../src/` calls a string function fails the build in fifteen translation units,
 * which is how the dependency was found.
 *
 * The definitions are in ../wonderboy_backend.c, where every symbol GCC may synthesise a call to
 * lives together. `bzero` is there too and is not declared here: it has no `<string.h>` prototype to
 * satisfy, it is the compiler's own rewrite of `clear_message_buffer`'s 6400-byte clear
 * (../../src/text.c), and it is the only libc symbol the reconstruction actually reaches.
 */
#ifndef WONDERBOY_SHIM_STRING_H
#define WONDERBOY_SHIM_STRING_H
void *memcpy(void *dst, const void *src, unsigned long n);
void *memset(void *dst, int c, unsigned long n);
#endif
