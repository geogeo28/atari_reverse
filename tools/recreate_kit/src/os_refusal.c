/* os_refusal.c — the candidate side of the refused-os_*-call tally. WHY it exists and what it
 * closes is in "refusing a call, on BOTH sides" at the top of ../include/os.h; the contract the
 * harness reads it through is in ../README.md, "What the candidate .so must export".
 *
 * It lives in the kit for the same reason the Dosound ledger next door does — the contract is
 * kit-wide, and kit.mk sweeps every kit source into every project's candidate, so the tally is one
 * implementation shared by every game rather than a copy per project.
 *
 * ON-TARGET builds do not compile this file (real TOS refuses nothing); one that calls a refusing
 * helper defines OS_NO_REFUSAL_TALLY instead. Off target it IS compiled, into every candidate by
 * kit.mk — the harness treats its absence as a hard error. See os.h.
 */
#include <stdint.h>

#include "os.h"

static uint32_t g_os_refusals;

void     g_os_refusal_reset(void) { g_os_refusals = 0; }
uint32_t g_os_refusal_count(void) { return g_os_refusals; }

/* The recording side. Returns `sentinel` unchanged so a refusing helper reads as one statement
 * (`return os_refused(-1);`) and cannot tally without also returning, or vice versa. */
int32_t os_refused(int32_t sentinel) {
    g_os_refusals++;
    return sentinel;
}
