/* sched_model_probe.c — the fixture behind test_sched_model.py.
 *
 * The SCHEDULED WRITE model (os.h, "SCHEDULED WRITES"; TRAP_MODEL.md, "Phase 8") is the third
 * modeled surface with a side on EACH shore: the oracle applies the case's declared store from
 * ../oracle/shim.c while the original spins, and a reconstruction reaches the identical store
 * through ../src/sched.c's `sched_poll8`. This probe drives both in one process and prints what each
 * produced, so the Python side can pin them against each other — and, crucially, can show the model
 * RED: the same routine with no schedule does not return at all.
 *
 * The same obstacle as hw_model_probe.c next door: `harness`/`emu` bind a project's candidate .so at
 * import and this directory deliberately binds no project, so the oracle is unreachable from Python
 * here, and the MUTANT candidate bodies below stand in for the reconstruction this suite has not got.
 *
 * Output is the two line kinds probe_build.py parses (this model has no per-slot file, so no `F`):
 *   K <case> <key> <value>   a scalar (a tally, a byte the run left, whether it returned)
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "os.h"        /* the shared entry encoding, OS_SCHED_* */
#include "sched.h"     /* the CANDIDATE side of the model (src/sched.c) */
#include "os.h"        /* ...and os_refused()'s tally, which an exhausted wait lands in */
#include "probe_common.h"   /* osh_run, the image geometry, the code planters */

/* ../oracle/shim.c ships no header — Python binds it by ctypes — so the entry points this probe
 * uses come from probe_common.h, and the model-specific exports are declared here. */
void     osh_schedule(const uint32_t *entries, uint32_t n);
uint32_t osh_sched_count(void);
uint32_t osh_sched_applied(void);
uint32_t osh_sched_arrivals(void);
uint32_t osh_sched_refused(void);
uint32_t osh_sched_max(void);
uint32_t osh_sched_fields(void);

/* Enough for the longest spin any case here schedules (five arrivals = ten instructions) with room
 * to overrun visibly, and small enough that the UNRELEASED cases end in microseconds rather than
 * spinning to a real cap. A case that expects `reached 0` is asserting this cap was hit. */
#define PROBE_MAX_INSNS 64u

/* The byte the planted routine spins on, and a scratch longword a second entry stores into. Both sit
 * above the code and below PROBE_SP, in the scratch image probe_common.h describes. */
#define WATCH_ADDR   0x3000u
#define SCRATCH_ADDR 0x3010u
#define HELD    0x19u   /* what the byte holds while the wait is waiting (Wonder Boy's press code) */
#define WANT    0x99u   /* ...and the release the wait is waiting for (that code | $80) */
#define SCRATCH_LONG 0x11223344u
#define SCRATCH_BYTE 0x5au

/* A PC the planted routine never executes, for the entry that can never come due. It is inside the
 * image and even, so nothing but the arrival count can be what stops it firing. */
#define UNREACHED_PC 0x2ffeu

/* A store BOTH sides refuse. The two bounds differ by design — the oracle bounds against the buffer
 * it was handed (this probe's 64 KiB scratch) and the candidate against OS_IMAGE_SIZE, the image
 * every reconstruction is given — so the one address that is outside both is at the top of the
 * larger. Anything between the two would be refused on one side and WRITTEN PAST THE BUFFER on the
 * other, which is what this constant exists to keep out of the cases. */
#define OUTSIDE_ADDR (OS_IMAGE_SIZE - 2u)

/* The candidate mutants below must not hang when they poll the wrong thing, so their loops are
 * bounded. The bound is deliberately larger than any correct body's poll count. */
#define CAND_POLL_CAP 16u

/* 68000 encodings. The spin is the shape Wonder Boy's pause wait has at $64e: an absolute-long byte
 * compare against an immediate, and a short branch back to it. (MOVE_B_ABSL_TO_D1 is in
 * probe_common.h — this was its third copy across the probes, which is the file's own threshold.) */
#define CMPI_B_IMM_ABSL   0x0c39u /* cmpi.b #imm,(xxx).l — imm in the low byte of the next word */
#define BNE_S             0x6600u /* bne.s <disp8>, the displacement in the low byte */

/* Plant `cmpi.b #WANT,(WATCH_ADDR).l / bne.s <back to the cmpi> / move.b (WATCH_ADDR).l,d1 / rts`
 * at PROBE_ENTRY. The compare is the instruction a `pc` trigger names: the wait re-executes it once
 * per iteration, which is what makes an arrival the same event as the candidate's poll. */
static void plant_spin(void) {
    uint32_t at = PROBE_ENTRY;
    plant_word(at, CMPI_B_IMM_ABSL);
    plant_word(at + 2, WANT);
    at = plant_long(at + 4, WATCH_ADDR);
    int32_t back = (int32_t)PROBE_ENTRY - (int32_t)(at + 2);
    plant_word(at, (uint16_t)(BNE_S | (uint8_t)back));
    at += 2;
    plant_word(at, MOVE_B_ABSL_TO_D1);
    at = plant_long(at + 2, WATCH_ADDR);
    plant_rts(at);
}

/* Build one flattened entry into `flat` at index `i`. Every case spells its entries through this, so
 * the field ORDER lives in one place on this side of the model too. */
static void set_entry(uint32_t *flat, uint32_t i, uint32_t kind, uint32_t trigger, uint32_t nth,
                      uint32_t addr, uint32_t width, uint32_t value) {
    uint32_t *e = flat + i * OS_SCHED_FIELDS;
    e[OS_SCHED_F_KIND] = kind;
    e[OS_SCHED_F_TRIGGER] = trigger;
    e[OS_SCHED_F_NTH] = nth;
    e[OS_SCHED_F_ADDR] = addr;
    e[OS_SCHED_F_WIDTH] = width;
    e[OS_SCHED_F_VALUE] = value;
}

/* Run the planted spin under `entries` and print every surface the model left.
 *
 * The watched byte is re-armed to HELD before each run rather than the image being cleared, because
 * one of the claims is that the SCHEDULE's own state does not carry over even when the image does. */
static void oracle_case(const char *name, const uint32_t *entries, uint32_t n) {
    uint32_t dregs[NREGS] = {0}, aregs[NREGS] = {0}, out[OUT_REGS] = {0};
    g_image[WATCH_ADDR] = HELD;
    memset(g_image + SCRATCH_ADDR, 0, 4);
    plant_spin();
    osh_schedule(entries, n);
    int reached = osh_run(g_image, PROBE_IMAGE_SIZE, PROBE_ENTRY, dregs, aregs,
                          PROBE_SP, PROBE_SENTINEL, 0, PROBE_MAX_INSNS, out);
    printf("K %s reached %d\n", name, reached);
    printf("K %s d1 %u\n", name, out[1] & 0xffu);
    printf("K %s count %u\n", name, osh_sched_count());
    printf("K %s applied %u\n", name, osh_sched_applied());
    printf("K %s arrivals %u\n", name, osh_sched_arrivals());
    printf("K %s refused %u\n", name, osh_sched_refused());
    printf("K %s watch %u\n", name, g_image[WATCH_ADDR]);
    for (int i = 0; i < 4; i++)
        printf("K %s scratch%d %u\n", name, i, g_image[SCRATCH_ADDR + i]);
}

/* ---- the candidate side: ../src/sched.c, driven the way harness.differential drives it --------- */

/* The FAITHFUL reconstruction of the planted routine: poll the watched byte once per iteration,
 * exactly where the original's compare reads it. */
static uint32_t cand_body_polls_the_wait(uint8_t *image) {
    uint32_t guard = 0;
    while (sched_poll8(image, WATCH_ADDR) != WANT && ++guard < CAND_POLL_CAP)
        ;
    return image[WATCH_ADDR];
}

/* MUTANT — it reads the image directly after one poll, which is what a port written against a byte
 * that "is already there" looks like. Its memory ends identical to the faithful body's, because the
 * agent's store is applied from the same list either way; only the POLL COUNT separates them, which
 * is why harness.differential compares that against the oracle's arrivals. */
static uint32_t cand_body_polls_once_then_reads(uint8_t *image) {
    uint32_t guard = 0;
    sched_poll8(image, WATCH_ADDR);
    while (image[WATCH_ADDR] != WANT && ++guard < CAND_POLL_CAP)
        ;
    return image[WATCH_ADDR];
}

/* THE PRODUCTION SHAPE: the capped wait a reconstruction actually calls. Identical to the faithful
 * body above while the release arrives, and BOUNDED when it does not — which is the whole point. */
static uint32_t cand_body_waits(uint8_t *image) {
    if (!sched_wait8(image, WATCH_ADDR, WANT))
        return 0;                       /* refused: the case is void, and every caller returns */
    return image[WATCH_ADDR];
}

/* MUTANT — it polls twice per iteration (a port that reads the byte, then re-reads it to compare).
 * The store lands an iteration early and the poll count is double the original's. */
static uint32_t cand_body_polls_twice_per_iteration(uint8_t *image) {
    uint32_t guard = 0;
    while (sched_poll8(image, WATCH_ADDR) != WANT && ++guard < CAND_POLL_CAP)
        sched_poll8(image, WATCH_ADDR);
    return image[WATCH_ADDR];
}

static void candidate_case(const char *name, const uint32_t *entries, uint32_t n,
                           uint32_t (*body)(uint8_t *image)) {
    /* THE CANDIDATE SIDE BOUNDS ITS STORE AGAINST OS_IMAGE_SIZE, not against this probe's buffer —
     * that is `sched_poll8`'s contract, since a reconstruction is handed the whole image and no
     * length. The scratch image here is PROBE_IMAGE_SIZE, so an entry between the two would be
     * SERVED and would write past the allocation. Every case's addresses are chosen either inside
     * this image or above OS_IMAGE_SIZE (OUTSIDE_ADDR); this is what keeps the next one honest. */
    for (uint32_t i = 0; i < n; i++) {
        uint32_t at = entries[i * OS_SCHED_FIELDS + OS_SCHED_F_ADDR];
        uint32_t width = entries[i * OS_SCHED_FIELDS + OS_SCHED_F_WIDTH];
        if (at < PROBE_IMAGE_SIZE && at + width > PROBE_IMAGE_SIZE) {
            fprintf(stderr, "%s: entry %u stores across the probe image's top\n", name, i);
            exit(1);
        }
        if (at >= PROBE_IMAGE_SIZE && at + width <= OS_IMAGE_SIZE) {
            fprintf(stderr, "%s: entry %u stores at %#x, outside this probe's %#x-byte image but "
                            "inside the OS_IMAGE_SIZE the candidate bounds against — it would be "
                            "served and would corrupt the heap\n", name, i, at, PROBE_IMAGE_SIZE);
            exit(1);
        }
    }
    g_image[WATCH_ADDR] = HELD;
    memset(g_image + SCRATCH_ADDR, 0, 4);
    g_sched_reset(entries, n);
    g_os_refusal_reset();
    uint32_t read_value = body(g_image);
    printf("K %s d1 %u\n", name, read_value);
    printf("K %s count %u\n", name, g_sched_count());
    printf("K %s applied %u\n", name, g_sched_applied());
    printf("K %s polls %u\n", name, g_sched_polls());
    printf("K %s refused %u\n", name, g_sched_refused());
    printf("K %s exhausted %u\n", name, g_sched_exhausted());
    printf("K %s os_refusals %u\n", name, g_os_refusal_count());
    printf("K %s watch %u\n", name, g_image[WATCH_ADDR]);
    for (int i = 0; i < 4; i++)
        printf("K %s scratch%d %u\n", name, i, g_image[SCRATCH_ADDR + i]);
}

int main(void) {
    probe_alloc_image();
    probe_require_out_regs();
    printf("K sizes max %u\n", osh_sched_max());
    printf("K sizes fields %u\n", osh_sched_fields());

    uint32_t flat[(OS_SCHED_MAX + 1) * OS_SCHED_FIELDS];
    memset(flat, 0, sizeof flat);

    /* THE RED CASE, and the reason the capability exists: the routine spins on a byte nothing in it
     * writes, so with no schedule it never returns. */
    oracle_case("no_schedule", flat, 0);

    /* The same routine, released before the third arrival at the compare. */
    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 3, WATCH_ADDR, 1, WANT);
    oracle_case("released_at_the_third_arrival", flat, 1);

    /* nth = 1 lands the store before the very FIRST compare, which is the moment the candidate's
     * first poll matches — and one arrival is what the run then reports, which is what pins the
     * post-reset observation osh_run's loop skips (see the comment there). */
    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 1, WATCH_ADDR, 1, WANT);
    oracle_case("released_at_the_first_arrival", flat, 1);

    /* A trigger PC the run never executes never comes due, however long the run is. */
    set_entry(flat, 0, OS_SCHED_AT_PC, UNREACHED_PC, 1, WATCH_ADDR, 1, WANT);
    oracle_case("trigger_pc_never_reached", flat, 1);

    /* The instruction-count trigger: no arrival is counted (it names no PC) and the store still
     * lands. The index is 1-based, and the loop is `cmpi, bne, cmpi, bne, cmpi, ...`, so 5 is the
     * third compare — two whole iterations run before the release. */
    set_entry(flat, 0, OS_SCHED_AT_INSN, 5, 1, WATCH_ADDR, 1, WANT);
    oracle_case("released_at_an_instruction_index", flat, 1);

    /* Two entries, and the wider stores: a longword into the scratch and the byte that releases the
     * wait. Also what pins AT MOST ONCE — the first entry comes due at arrival 1 and the run makes
     * five arrivals, so an entry that re-fired would show up as `applied` above 2. And it is what
     * pins ONE ARRIVAL PER INSTRUCTION: two entries name the same trigger PC and the count is five,
     * not ten, because the candidate polls the wait once per iteration however many stores the case
     * hung on it. */
    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 1, SCRATCH_ADDR, 4, SCRATCH_LONG);
    set_entry(flat, 1, OS_SCHED_AT_PC, PROBE_ENTRY, 5, WATCH_ADDR, 1, WANT);
    oracle_case("two_entries_and_a_longword", flat, 2);

    /* AN ENTRY THAT FIRES BUT DOES NOT RELEASE THE WAIT. The store lands at arrival 1 and the loop
     * goes on re-executing its compare to the cap, so the arrival count must go on rising after the
     * entry has fired — which is what the harness compares against a candidate's poll count, and
     * what the first sweep found nothing measuring. HELD is stored, i.e. the byte the wait already
     * holds: the store is real and changes nothing. */
    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 1, WATCH_ADDR, 1, HELD);
    oracle_case("a_fired_entry_that_does_not_release_the_wait", flat, 1);

    /* A store that leaves the image is REFUSED rather than made, and the wait then never ends. */
    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 1, OUTSIDE_ADDR, 4, SCRATCH_LONG);
    oracle_case("a_store_outside_the_image", flat, 1);

    /* Entries past OS_SCHED_MAX are dropped, and `count` says so rather than the run silently
     * carrying fewer stores than the case declared. */
    for (uint32_t i = 0; i < OS_SCHED_MAX + 1; i++)
        set_entry(flat, i, OS_SCHED_AT_PC, PROBE_ENTRY, 1, SCRATCH_ADDR, 1, SCRATCH_BYTE);
    oracle_case("more_entries_than_the_cap", flat, OS_SCHED_MAX + 1);

    /* ...and the schedule does not survive into the next run: the RED case again, immediately after
     * a run whose entry DID fire. */
    memset(flat, 0, sizeof flat);
    oracle_case("no_schedule_after_a_scheduled_run", flat, 0);

    /* ---- the candidate side, on the same entry the oracle's third-arrival case ran ---- */
    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 3, WATCH_ADDR, 1, WANT);
    candidate_case("cand_polls_the_wait", flat, 1, cand_body_polls_the_wait);
    candidate_case("cand_waits_and_is_released", flat, 1, cand_body_waits);
    candidate_case("cand_polls_once_then_reads", flat, 1, cand_body_polls_once_then_reads);
    /* ...and the same double-poller at nth = 3, where its extra poll lands on the iteration the
     * release was due anyway and NOTHING separates it from the faithful body. It is here to be
     * shown invisible: an `nth` that is a multiple of the port's polls-per-iteration hides exactly
     * this mutant, which is why the case below re-runs all three at nth = 4. */
    candidate_case("cand_polls_twice_at_an_aliasing_nth", flat, 1,
                   cand_body_polls_twice_per_iteration);

    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 4, WATCH_ADDR, 1, WANT);
    candidate_case("cand4_polls_the_wait", flat, 1, cand_body_polls_the_wait);
    candidate_case("cand4_polls_once_then_reads", flat, 1, cand_body_polls_once_then_reads);
    candidate_case("cand4_polls_twice_per_iteration", flat, 1, cand_body_polls_twice_per_iteration);

    /* THE CAP. The store lands but stores the byte the wait ALREADY holds, so the wait is never
     * released — the shape a case gets when its declared value does not match the compare, and the
     * shape that used to HANG the whole suite. `sched_wait8` gives up at OS_SCHED_POLL_MAX and
     * tallies a refusal, which is what turns a hung run into a rejected case. */
    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 1, WATCH_ADDR, 1, HELD);
    candidate_case("cand_a_wait_that_is_never_released", flat, 1, cand_body_waits);

    /* The candidate refuses the same out-of-image store the oracle refuses. Its wait then runs to
     * the body's own guard, which is what an unreleased poll loop looks like on this side. */
    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 1, OUTSIDE_ADDR, 4, SCRATCH_LONG);
    candidate_case("cand_a_store_outside_the_image", flat, 1, cand_body_polls_the_wait);
    return 0;
}
