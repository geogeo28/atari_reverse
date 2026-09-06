/* os_log.c — the candidate side of the off-image OS event ledger. WHAT it records and WHY those
 * calls need a ledger at all is in "the OFF-IMAGE OS EVENT LEDGER" at the top of ../include/os.h;
 * what each event means is in TRAP_MODEL.md, "Phase 13". The oracle keeps its own mirror in
 * oracle/shim.c, the same split every other ledger in the kit uses.
 *
 * It lives in the kit for the reason src/dosound_log.c next door does — the contract is kit-wide,
 * and kit.mk sweeps every kit source into every project's candidate, so the ledger is one
 * implementation shared by every game rather than a copy per project.
 *
 * ON-TARGET builds do not compile this file: there a console byte really goes to the screen and an
 * IKBD command really goes to the keyboard, so the project's own build supplies `g_os_event` — a
 * link-time substitution, exactly as it supplies its own `g_dosound`.
 */
#include <stdint.h>

#include "os.h"

/* Two parallel arrays rather than an array of os_event_t, so the harness can cast each one straight
 * through ctypes the way it already does the oracle's. */
static uint16_t g_event_kind[OS_EVENT_LOG_MAX];
static uint32_t g_event_value[OS_EVENT_LOG_MAX];
static uint32_t g_event_n;

void             g_os_event_reset(void)  { g_event_n = 0; }
uint32_t         g_os_event_count(void)  { return g_event_n; }
const uint16_t  *g_os_event_kinds(void)  { return g_event_kind; }
const uint32_t  *g_os_event_values(void) { return g_event_value; }

/* Append one event. Entries past the cap are dropped exactly as the oracle's mirror drops them, so a
 * run longer than the cap still compares like for like; the harness refuses a comparison AT the cap
 * rather than trust a truncated one. */
void g_os_event(uint16_t kind, uint32_t value) {
    if (g_event_n >= OS_EVENT_LOG_MAX) return;
    g_event_kind[g_event_n] = kind;
    g_event_value[g_event_n] = value;
    g_event_n++;
}
