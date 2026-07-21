/* shim.c — the freestanding libc the cores need on the Atari target.
 *
 * m68k-elf has no libc and we link -nostdlib, so the handful of <string.h> functions the remaster
 * cores call have to come from somewhere. Every on-target program (main.c, demo_main.c,
 * bench_main.c) links this one file rather than carrying its own copies. The declarations live in
 * shim_include/string.h, which stands in for the real header at compile time.
 *
 * Plain byte loops, correct for any alignment. They are NOT free: the demo clears a 32000-byte
 * framebuffer through `memset` every frame, and the boot-time graphics unpack slides ~450 KB through
 * `memmove`/`memcpy`. Neither shows up in `tools/bench.py`, which measures the four render cores
 * individually — so a long-word version is an open optimisation, not a done one.
 *
 * Note the one real cost of centralising them: with `memset` defined in the caller's own translation
 * unit GCC inlined it at the call site, and across a TU boundary it cannot, so the per-frame frame
 * clear in demo_main.c is now an out-of-line call rather than an inlined loop. One call per 32000-byte
 * clear is negligible against the copy itself, and the render cores' generated code is untouched
 * (bench.py's counts are unchanged) — but "identical code" would be the wrong claim to make.
 */
#include <stdint.h>
#include <string.h>          /* resolves to shim_include/string.h via each build's -I */

void *memset(void *d, int c, unsigned long n) {
    uint8_t *dp = d;
    while (n--) *dp++ = (uint8_t)c;
    return d;
}

void *memcpy(void *d, const void *s, unsigned long n) {
    uint8_t *dp = d; const uint8_t *sp = s;
    while (n--) *dp++ = *sp++;
    return d;
}

/* Overlap-safe: the graphics unpack slides two large blocks within the asset arena, in both
 * directions (see src/assets.c phases C and F). */
void *memmove(void *d, const void *s, unsigned long n) {
    uint8_t *dp = d; const uint8_t *sp = s;
    if (dp <= sp) { while (n--) *dp++ = *sp++; }
    else { dp += n; sp += n; while (n--) *--dp = *--sp; }
    return d;
}
