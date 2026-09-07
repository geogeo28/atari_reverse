/* flyshark_backend.c — the seam's target half: the counters the shim's doors keep, and the three
 * libc bodies a freestanding m68k build has to supply itself.
 *
 * Off target the doors' work is done by translation units this build leaves out —
 * `tools/recreate_kit/src/hw.c` (the ordered hardware read and write ledgers), `src/psg.c` (the
 * YM2149's two ports), `src/sched.c` (the scheduled-write model) and `src/os_log.c` (the OS event
 * ledger). Each of those files says in its own header that a build for the real Atari does not
 * compile it and drives the machine itself. The DOORS are `static inline` in `shim_include/hw.h`,
 * `psg.h`, `sched.h` and `os.h`, for the reason those files carry (a body the call site can see
 * folds the bus arithmetic away); what cannot live in a header is the state they share, because a
 * definition in a header would be one per translation unit and the counts would be per-file rather
 * than per-run. That state is this file.
 *
 * WHAT THE COUNTERS ARE FOR. On target there is no ledger to compare, so these are the only surface
 * a run has for a hardware access, an OS call or a file (docs/on-target-execution.md, "The
 * observable surfaces"). `flyshark_main.c` publishes every one of them in STATE.BIN and `smoke.py`
 * asserts them — a count of 0 where the boot must have made hundreds says the seam is not wired,
 * which is a failure that otherwise looks exactly like a quiet success.
 */
#include <stdint.h>

#include "hw.h"      /* the three read/write/rmw counters the hardware doors keep */
#include "os.h"      /* the file seam's four, and the video group's three */
#include "psg.h"     /* ...and the chip's two */

/* ---- the hardware doors' (shim_include/hw.h) -------------------------------------------------- */
volatile uint32_t fs_hw_writes;
volatile uint32_t fs_hw_rmw;
volatile uint32_t fs_hw_reads;

/* ---- the YM2149's (shim_include/psg.h) -------------------------------------------------------- */
volatile uint32_t fs_psg_writes;
volatile uint32_t fs_psg_refused;

/* ---- the file seam's (shim_include/os.h) ------------------------------------------------------ */
volatile uint32_t fs_file_opens;
volatile uint32_t fs_file_open_failures;
volatile uint32_t fs_file_bytes_read;
volatile uint32_t fs_file_refusals;

/* ---- and the video group's, which off target are ORDERED EVENTS the differential compares ----- */
volatile uint32_t fs_setscreen_calls;
volatile uint32_t fs_setpalette_calls;
volatile uint32_t fs_vsync_calls;
volatile uint32_t fs_ikbd_commands;

/* ================================================================================================
 * The freestanding libc the cores need. m68k-elf ships none, and `-ffreestanding -nostdlib` is what
 * makes that explicit rather than accidental.
 *
 * `-fno-tree-loop-distribute-patterns` is what stops GCC recognising each of these loops and
 * replacing it with a call to itself.
 * ============================================================================================= */
void *memset(void *dst, int c, unsigned long n) {
    unsigned char *out = dst;

    while (n--)
        *out++ = (unsigned char)c;
    return dst;
}

void *memcpy(void *dst, const void *src, unsigned long n) {
    unsigned char *out = dst;
    const unsigned char *in = src;

    while (n--)
        *out++ = *in++;
    return dst;
}

/* Overlap-safe, which `memcpy` is not. No core calls it today; it is here because GCC may
 * SYNTHESISE a call to it from a structure copy in any of the ten, and a missing body would be a
 * link error rather than a warning. */
void *memmove(void *dst, const void *src, unsigned long n) {
    unsigned char *out = dst;
    const unsigned char *in = src;

    if (out <= in)
        return memcpy(dst, src, n);
    out += n;
    in += n;
    while (n--)
        *--out = *--in;
    return dst;
}
