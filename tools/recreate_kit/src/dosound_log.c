/* dosound_log.c — the candidate side of the XBIOS Dosound(A0) side-effect ledger.
 *
 * Dosound hands the YM2149 a command list through A0. It writes the chip, not our memory image, so
 * a wrong or missing command list is invisible to the image diff even when the call runs. Every
 * reconstruction therefore calls g_dosound() wherever the original traps Dosound, passing the image
 * address of the list; harness.differential() clears the ledger before each candidate run and
 * compares it against the oracle's ordered Dosound trap stream (shim.c keeps the mirror ledger).
 *
 * This lives in the kit because the contract does — see "What the candidate .so must export" in
 * ../README.md — and kit.mk links it into every project's candidate, so the three exported symbols
 * are present and identical for every game instead of being copied per project.
 *
 * Off-target only: a reconstruction built for the real Atari (e.g. BuggyBoy's PRG shim) supplies its
 * own g_dosound that issues the real XBIOS trap, and does not compile this file.
 */
#include <stdint.h>

#include "os.h"

static uint32_t g_dosound_log[OS_DOSOUND_LOG_MAX];
static uint32_t g_dosound_log_n;

void            g_dosound_log_reset(void) { g_dosound_log_n = 0; }
uint32_t        g_dosound_log_count(void) { return g_dosound_log_n; }
const uint32_t *g_dosound_log_args(void)  { return g_dosound_log; }

/* The recording side. `list_addr` is the image address of the command list the original would have
 * handed to TOS. Entries past the cap are dropped exactly as the oracle's ledger drops them, so a
 * run longer than the cap still compares like for like. */
void g_dosound(uint8_t *image, uint32_t list_addr) {
    (void)image;
    if (g_dosound_log_n < OS_DOSOUND_LOG_MAX) g_dosound_log[g_dosound_log_n++] = list_addr;
}
