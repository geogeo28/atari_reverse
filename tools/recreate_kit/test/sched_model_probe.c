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
void     osh_schedule(const uint32_t *entries, uint32_t n, const uint32_t *sites, uint32_t site_n);
uint32_t osh_sched_count(void);
uint32_t osh_sched_applied(void);
uint32_t osh_sched_arrivals(void);
uint32_t osh_sched_refused(void);
uint32_t osh_sched_max(void);
uint32_t osh_sched_fields(void);
uint32_t osh_sched_site_max(void);
uint32_t osh_sched_site_count(void);
uint32_t osh_sched_site_arrivals(uint32_t i);

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

/* The SECOND wait's byte, for the two-wait routine below, and the WORD the sched_poll16 cases spin
 * on. Both are above WATCH_ADDR and clear of the scratch longword. */
#define WATCH2_ADDR  0x3020u
#define WORD_ADDR    0x3024u
#define WORD_HELD    0x1234u   /* what the word holds while its wait is waiting */
#define WORD_WANT    0x5678u   /* ...and what releases it */
#define TWO_WAIT_NTH 3u        /* the arrival the two-wait routine's SECOND spin is released at */

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

/* ...and the WORD wait's, which must be ABOVE the kit's own OS_SCHED_POLL_MAX rather than below it:
 * the case is about the kit's cap firing, and a body guard under it would fire first and hide it. */
#define WORD_POLL_GUARD (OS_SCHED_POLL_MAX + 8u)

/* 68000 encodings. The spin is the shape Wonder Boy's pause wait has at $64e: an absolute-long byte
 * compare against an immediate, and a short branch back to it. (MOVE_B_ABSL_TO_D1 is in
 * probe_common.h — this was its third copy across the probes, which is the file's own threshold.) */
#define CMPI_B_IMM_ABSL   0x0c39u /* cmpi.b #imm,(xxx).l — imm in the low byte of the next word */
#define CMPI_W_IMM_ABSL   0x0c79u /* cmpi.w #imm,(xxx).l — the WORD compare sched_poll16 mirrors */
#define MOVE_W_ABSL_TO_D1 0x3239u /* move.w (xxx).l,d1 */
#define BNE_S             0x6600u /* bne.s <disp8>, the displacement in the low byte */

/* One `cmpi.<size> #imm,(addr).l / bne.s <back to the cmpi>` spin at `at`; returns the address past
 * it. The compare is the instruction a `pc` trigger names AND the wait's SITE, and it qualifies
 * because it RE-READS the watched byte — a `cmpi.<size> #imm,(addr).l` reads and compares in one
 * instruction, so the read and the test coincide here. The store lands just before it, which is
 * what makes an arrival the same event as the candidate's poll at that site. */
static uint32_t plant_wait(uint32_t at, uint16_t compare, uint32_t imm, uint32_t addr) {
    uint32_t site = at;
    plant_word(at, compare);
    plant_word(at + 2, (uint16_t)imm);
    at = plant_long(at + 4, addr);
    int32_t back = (int32_t)site - (int32_t)(at + 2);
    plant_word(at, (uint16_t)(BNE_S | (uint8_t)back));
    return at + 2;
}

/* THE BYTES OF ONE WAIT, so a site address is arithmetic on this rather than a transcribed literal:
 * the compare is opcode + immediate + absolute long (8) and the branch back is one word (2).
 * plant_two_waits checks the sum against what plant_wait really emitted. */
#define WAIT_BYTES 10u

/* Plant `cmpi.b #WANT,(WATCH_ADDR).l / bne.s <back> / move.b (WATCH_ADDR).l,d1 / rts` at
 * PROBE_ENTRY: the one-wait routine every single-site case runs. */
static void plant_spin(void) {
    uint32_t at = plant_wait(PROBE_ENTRY, CMPI_B_IMM_ABSL, WANT, WATCH_ADDR);
    plant_word(at, MOVE_B_ABSL_TO_D1);
    plant_rts(plant_long(at + 2, WATCH_ADDR));
}

/* THE TWO-WAIT ROUTINE, and the arrangement the per-site counters exist for: two spins one after
 * the other, the first on a byte the case seeds ALREADY RELEASED so it falls through in one
 * arrival, the second declared and spun. It is Wonder Boy's `flip_screen` in miniature — see the
 * cases in main(), and os.h's "WAIT SITES" for what a run TOTAL loses here. */
#define TWO_WAIT_SITE_1 PROBE_ENTRY
#define TWO_WAIT_SITE_2 (PROBE_ENTRY + WAIT_BYTES)

static void plant_two_waits(void) {
    uint32_t at = plant_wait(TWO_WAIT_SITE_1, CMPI_B_IMM_ABSL, WANT, WATCH2_ADDR);
    if (at != TWO_WAIT_SITE_2) {
        fprintf(stderr, "probe: one wait is %u bytes, not WAIT_BYTES — the second site's address "
                        "and the candidate bodies' site constants would name nothing\n",
                at - TWO_WAIT_SITE_1);
        exit(1);
    }
    at = plant_wait(at, CMPI_B_IMM_ABSL, WANT, WATCH_ADDR);
    plant_word(at, MOVE_B_ABSL_TO_D1);
    plant_rts(plant_long(at + 2, WATCH_ADDR));
}

/* ...and the WORD wait `sched_poll16` mirrors: same shape, `cmpi.w` instead of `cmpi.b`. */
static void plant_word_spin(void) {
    uint32_t at = plant_wait(PROBE_ENTRY, CMPI_W_IMM_ABSL, WORD_WANT, WORD_ADDR);
    plant_word(at, MOVE_W_ABSL_TO_D1);
    plant_rts(plant_long(at + 2, WORD_ADDR));
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

/* Arm the scratch image the way every case starts: the watched bytes HELD, the word HELD, the
 * scratch longword clear. Re-armed rather than the image being cleared, because one of the claims is
 * that the SCHEDULE's own state does not carry over even when the image does. */
static void arm_image(void) {
    g_image[WATCH_ADDR] = HELD;
    /* WATCH2 comes in ALREADY RELEASED, always: it is the FIRST of the two-wait routine's waits, and
     * the arrangement being modelled is one whose first wait falls through in a single arrival while
     * the second spins (Wonder Boy's `flip_screen`). No other case reads it. */
    g_image[WATCH2_ADDR] = WANT;
    plant_word(WORD_ADDR, WORD_HELD);
    memset(g_image + SCRATCH_ADDR, 0, 4);
}

/* Run a planted routine under `entries`/`sites` and print every surface the model left.
 *
 * `sites` is the run's declared WAIT SITES (os.h), which a caller passes explicitly here because
 * this probe has no `emu.wait_site_pcs` to default them from the triggers — and because two of the
 * cases below are ABOUT a site list that is not simply the trigger set. */
static void oracle_case(const char *name, void (*plant)(void), const uint32_t *entries, uint32_t n,
                        const uint32_t *sites, uint32_t site_n) {
    uint32_t dregs[NREGS] = {0}, aregs[NREGS] = {0}, out[OUT_REGS] = {0};
    arm_image();
    plant();
    osh_schedule(entries, n, sites, site_n);
    int reached = osh_run(g_image, PROBE_IMAGE_SIZE, PROBE_ENTRY, dregs, aregs,
                          PROBE_SP, PROBE_SENTINEL, 0, PROBE_MAX_INSNS, out);
    printf("K %s reached %d\n", name, reached);
    printf("K %s d1 %u\n", name, out[1] & 0xffu);
    printf("K %s d1w %u\n", name, out[1] & 0xffffu);
    printf("K %s count %u\n", name, osh_sched_count());
    printf("K %s applied %u\n", name, osh_sched_applied());
    printf("K %s arrivals %u\n", name, osh_sched_arrivals());
    printf("K %s refused %u\n", name, osh_sched_refused());
    printf("K %s sites %u\n", name, osh_sched_site_count());
    for (uint32_t i = 0; i < osh_sched_site_count(); i++)
        printf("K %s arrivals%u %u\n", name, i, osh_sched_site_arrivals(i));
    printf("K %s watch %u\n", name, g_image[WATCH_ADDR]);
    printf("K %s watch2 %u\n", name, g_image[WATCH2_ADDR]);
    for (int i = 0; i < 4; i++)
        printf("K %s scratch%d %u\n", name, i, g_image[SCRATCH_ADDR + i]);
}

/* ---- the candidate side: ../src/sched.c, driven the way harness.differential drives it --------- */

/* The FAITHFUL reconstruction of the planted routine: poll the watched byte once per iteration,
 * exactly where the original's compare reads it, naming that compare's PC as the site. */
static uint32_t cand_body_polls_the_wait(uint8_t *image) {
    uint32_t guard = 0;
    while (sched_poll8(image, WATCH_ADDR, PROBE_ENTRY) != WANT && ++guard < CAND_POLL_CAP)
        ;
    return image[WATCH_ADDR];
}

/* MUTANT — it reads the image directly after one poll, which is what a port written against a byte
 * that "is already there" looks like. Its memory ends identical to the faithful body's, because the
 * agent's store is applied from the same list either way; only the POLL COUNT separates them, which
 * is why harness.differential compares that against the oracle's arrivals. */
static uint32_t cand_body_polls_once_then_reads(uint8_t *image) {
    uint32_t guard = 0;
    sched_poll8(image, WATCH_ADDR, PROBE_ENTRY);
    while (image[WATCH_ADDR] != WANT && ++guard < CAND_POLL_CAP)
        ;
    return image[WATCH_ADDR];
}

/* THE PRODUCTION SHAPE: the capped wait a reconstruction actually calls. Identical to the faithful
 * body above while the release arrives, and BOUNDED when it does not — which is the whole point. */
static uint32_t cand_body_waits(uint8_t *image) {
    if (!sched_wait8(image, WATCH_ADDR, WANT, PROBE_ENTRY))
        return 0;                       /* refused: the case is void, and every caller returns */
    return image[WATCH_ADDR];
}

/* MUTANT — it polls twice per iteration (a port that reads the byte, then re-reads it to compare).
 * The store lands an iteration early and the poll count is double the original's. */
static uint32_t cand_body_polls_twice_per_iteration(uint8_t *image) {
    uint32_t guard = 0;
    while (sched_poll8(image, WATCH_ADDR, PROBE_ENTRY) != WANT && ++guard < CAND_POLL_CAP)
        sched_poll8(image, WATCH_ADDR, PROBE_ENTRY);
    return image[WATCH_ADDR];
}

/* MUTANT — it names a site the run did not declare. A poll nobody counts is the hole the sites
 * close, so the model refuses it rather than serving it; the wait then runs to the body's guard. */
static uint32_t cand_body_polls_at_an_undeclared_site(uint8_t *image) {
    uint32_t guard = 0;
    while (sched_poll8(image, WATCH_ADDR, UNREACHED_PC) != WANT && ++guard < CAND_POLL_CAP)
        ;
    return image[WATCH_ADDR];
}

/* ---- the two-wait routine's bodies, and the whole reason the sites exist ------------------------ */

/* FAITHFUL: both waits, each naming its own site. The first falls through in one poll because the
 * case seeds its byte already released; the second spins until the declared store lands. */
static uint32_t cand_body_two_waits(uint8_t *image) {
    uint32_t guard = 0;
    while (sched_poll8(image, WATCH2_ADDR, TWO_WAIT_SITE_1) != WANT && ++guard < CAND_POLL_CAP)
        ;
    guard = 0;
    while (sched_poll8(image, WATCH_ADDR, TWO_WAIT_SITE_2) != WANT && ++guard < CAND_POLL_CAP)
        ;
    return image[WATCH_ADDR];
}

/* MUTANT — THE ONE THE PER-SITE COUNTERS WERE BUILT FOR. It drops the first wait entirely. Against
 * run TOTALS this was invisible: the store fired on the run's Nth poll either way, so the faithful
 * body's second wait ran one iteration FEWER than the original's and the first wait's poll made the
 * sum back up. Per site it is two counters against two, and the first one is 0 against 1. */
static uint32_t cand_body_two_waits_first_deleted(uint8_t *image) {
    uint32_t guard = 0;
    while (sched_poll8(image, WATCH_ADDR, TWO_WAIT_SITE_2) != WANT && ++guard < CAND_POLL_CAP)
        ;
    return image[WATCH_ADDR];
}

/* ---- the WORD wait: sched_poll16, the capped wrapper ------------------------------------------- */

/* The faithful body for the planted `cmpi.w` spin: ONE poll per iteration ticks the clock, and the
 * comparand is the full WORD. Spelt with the caller's own predicate, which is why sched_poll16 is an
 * iterator rather than a `sched_wait16(until)` — see include/sched.h. */
/* MUTANT — the WORD wait at a site the run did not declare. sched_poll16 stops the loop itself
 * rather than handing back a word, because it is the side that owns the bound; the poll is still
 * COUNTED, which is what makes its tally the same as sched_poll8's on the same refusal. */
static uint32_t cand_body_word_wait_at_an_undeclared_site(uint8_t *image) {
    uint16_t seen;
    uint32_t guard = 0;
    while (sched_poll16(image, WORD_ADDR, UNREACHED_PC, &seen) && ++guard < WORD_POLL_GUARD)
        if (seen == WORD_WANT)
            return seen;
    return 0;
}

static uint32_t cand_body_word_wait(uint8_t *image) {
    uint16_t seen;
    uint32_t guard = 0;
    /* A GUARD ABOVE THE KIT'S OWN CAP, and it is not belt-and-braces: `sched_poll16` is what bounds
     * this loop, so a mutant that REMOVES that bound turns this body into an infinite loop and the
     * suite HANGS instead of failing — which decides nothing (README's hang class). WORD_POLL_GUARD
     * is above OS_SCHED_POLL_MAX, so the kit's cap always fires first on a correct build and this
     * one only ever fires on a broken one. */
    while (sched_poll16(image, WORD_ADDR, PROBE_ENTRY, &seen) && ++guard < WORD_POLL_GUARD)
        if (seen == WORD_WANT)
            return seen;
    return 0;                           /* the cap; sched_poll16 has already tallied the refusal */
}

static void candidate_case(const char *name, const uint32_t *entries, uint32_t n,
                           const uint32_t *sites, uint32_t site_n,
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
    arm_image();
    g_sched_reset(entries, n, sites, site_n);
    g_os_refusal_reset();
    uint32_t read_value = body(g_image);
    printf("K %s d1 %u\n", name, read_value);
    printf("K %s count %u\n", name, g_sched_count());
    printf("K %s applied %u\n", name, g_sched_applied());
    printf("K %s polls %u\n", name, g_sched_polls());
    printf("K %s refused %u\n", name, g_sched_refused());
    printf("K %s exhausted %u\n", name, g_sched_exhausted());
    printf("K %s undeclared %u\n", name, g_sched_undeclared());
    printf("K %s os_refusals %u\n", name, g_os_refusal_count());
    printf("K %s sites %u\n", name, g_sched_site_count());
    for (uint32_t i = 0; i < g_sched_site_count(); i++)
        printf("K %s polls%u %u\n", name, i, g_sched_site_polls(i));
    printf("K %s watch %u\n", name, g_image[WATCH_ADDR]);
    printf("K %s watch2 %u\n", name, g_image[WATCH2_ADDR]);
    for (int i = 0; i < 4; i++)
        printf("K %s scratch%d %u\n", name, i, g_image[SCRATCH_ADDR + i]);
}

int main(void) {
    probe_alloc_image();
    probe_require_out_regs();
    printf("K sizes max %u\n", osh_sched_max());
    printf("K sizes fields %u\n", osh_sched_fields());
    printf("K sizes site_max %u\n", osh_sched_site_max());

    uint32_t flat[(OS_SCHED_MAX + 1) * OS_SCHED_FIELDS];
    memset(flat, 0, sizeof flat);
    /* The site lists the cases below declare. `one_site` is the trigger set of every single-wait
     * case, which is what emu.wait_site_pcs defaults to; the rest are named where they are used. */
    const uint32_t one_site[] = {PROBE_ENTRY};
    const uint32_t no_sites[] = {0};
    const uint32_t unreached_site[] = {UNREACHED_PC};
    const uint32_t two_sites[] = {TWO_WAIT_SITE_1, TWO_WAIT_SITE_2};

    /* THE RED CASE, and the reason the capability exists: the routine spins on a byte nothing in it
     * writes, so with no schedule it never returns. */
    oracle_case("no_schedule", plant_spin, flat, 0, no_sites, 0);

    /* The same routine, released before the third arrival at the compare. */
    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 3, WATCH_ADDR, 1, WANT);
    oracle_case("released_at_the_third_arrival", plant_spin, flat, 1, one_site, 1);

    /* nth = 1 lands the store before the very FIRST compare, which is the moment the candidate's
     * first poll matches — and one arrival is what the run then reports, which is what pins the
     * post-reset observation osh_run's loop skips (see the comment there). */
    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 1, WATCH_ADDR, 1, WANT);
    oracle_case("released_at_the_first_arrival", plant_spin, flat, 1, one_site, 1);

    /* A trigger PC the run never executes never comes due, however long the run is. */
    set_entry(flat, 0, OS_SCHED_AT_PC, UNREACHED_PC, 1, WATCH_ADDR, 1, WANT);
    oracle_case("trigger_pc_never_reached", plant_spin, flat, 1, unreached_site, 1);

    /* AN ENTRY WHOSE TRIGGER IS NOT A DECLARED SITE CAN NEVER COME DUE, which is why
     * emu.wait_site_pcs refuses the combination before a case can be written with it. The entry
     * names the compare the run really does execute; the run declares a DIFFERENT site, so nothing
     * counts the arrivals the entry is waiting for and the wait spins to the cap. */
    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 1, WATCH_ADDR, 1, WANT);
    oracle_case("trigger_is_not_a_declared_site", plant_spin, flat, 1, unreached_site, 1);

    /* The instruction-count trigger: no arrival is counted (it names no PC) and the store still
     * lands. The index is 1-based, and the loop is `cmpi, bne, cmpi, bne, cmpi, ...`, so 5 is the
     * third compare — two whole iterations run before the release. */
    set_entry(flat, 0, OS_SCHED_AT_INSN, 5, 1, WATCH_ADDR, 1, WANT);
    oracle_case("released_at_an_instruction_index", plant_spin, flat, 1, no_sites, 0);

    /* Two entries, and the wider stores: a longword into the scratch and the byte that releases the
     * wait. Also what pins AT MOST ONCE — the first entry comes due at arrival 1 and the run makes
     * five arrivals, so an entry that re-fired would show up as `applied` above 2. And it is what
     * pins ONE ARRIVAL PER INSTRUCTION: two entries name the same trigger PC and the count is five,
     * not ten, because the candidate polls the wait once per iteration however many stores the case
     * hung on it. */
    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 1, SCRATCH_ADDR, 4, SCRATCH_LONG);
    set_entry(flat, 1, OS_SCHED_AT_PC, PROBE_ENTRY, 5, WATCH_ADDR, 1, WANT);
    oracle_case("two_entries_and_a_longword", plant_spin, flat, 2, one_site, 1);

    /* AN ENTRY THAT FIRES BUT DOES NOT RELEASE THE WAIT. The store lands at arrival 1 and the loop
     * goes on re-executing its compare to the cap, so the arrival count must go on rising after the
     * entry has fired — which is what the harness compares against a candidate's poll count, and
     * what the first sweep found nothing measuring. HELD is stored, i.e. the byte the wait already
     * holds: the store is real and changes nothing. */
    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 1, WATCH_ADDR, 1, HELD);
    oracle_case("a_fired_entry_that_does_not_release_the_wait", plant_spin, flat, 1, one_site, 1);

    /* A store that leaves the image is REFUSED rather than made, and the wait then never ends. */
    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 1, OUTSIDE_ADDR, 4, SCRATCH_LONG);
    oracle_case("a_store_outside_the_image", plant_spin, flat, 1, one_site, 1);

    /* Entries past OS_SCHED_MAX are dropped, and `count` says so rather than the run silently
     * carrying fewer stores than the case declared. */
    for (uint32_t i = 0; i < OS_SCHED_MAX + 1; i++)
        set_entry(flat, i, OS_SCHED_AT_PC, PROBE_ENTRY, 1, SCRATCH_ADDR, 1, SCRATCH_BYTE);
    oracle_case("more_entries_than_the_cap", plant_spin, flat, OS_SCHED_MAX + 1, one_site, 1);

    /* ...and SITES past OS_SCHED_SITE_MAX likewise, for the same reason: a run whose second wait's
     * site was silently dropped would leave that wait uncounted, which is the hole itself. */
    {
        uint32_t many[OS_SCHED_SITE_MAX + 1];
        for (uint32_t i = 0; i < OS_SCHED_SITE_MAX + 1; i++)
            many[i] = PROBE_ENTRY + 2u * i;
        set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 3, WATCH_ADDR, 1, WANT);
        oracle_case("more_sites_than_the_cap", plant_spin, flat, 1, many, OS_SCHED_SITE_MAX + 1);
    }

    /* ...and the schedule does not survive into the next run: the RED case again, immediately after
     * a run whose entry DID fire. */
    memset(flat, 0, sizeof flat);
    oracle_case("no_schedule_after_a_scheduled_run", plant_spin, flat, 0, no_sites, 0);

    /* ---- THE TWO-WAIT ROUTINE, on the oracle: the arrangement the sites exist for ----
     * The first wait's byte comes in ALREADY RELEASED — `arm_image` sets WATCH2 to WANT for every
     * case, which is where that seeding lives and why nothing is poked here — so it falls through in
     * ONE arrival; the second is declared at TWO_WAIT_NTH. The two per-site counts are 1 and 3, and
     * their SUM is 4, which is the number a run total would report. The deleted-first-wait port
     * below produces 3 for that total and (0, 3) per site, so BOTH separate it — and which of the
     * two does the work is the point test_sched_model.py makes. */
    set_entry(flat, 0, OS_SCHED_AT_PC, TWO_WAIT_SITE_2, TWO_WAIT_NTH, WATCH_ADDR, 1, WANT);
    oracle_case("two_waits", plant_two_waits, flat, 1, two_sites, 2);

    /* ---- the candidate side, on the same entry the oracle's third-arrival case ran ---- */
    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 3, WATCH_ADDR, 1, WANT);
    candidate_case("cand_polls_the_wait", flat, 1, one_site, 1, cand_body_polls_the_wait);
    candidate_case("cand_waits_and_is_released", flat, 1, one_site, 1, cand_body_waits);
    candidate_case("cand_polls_once_then_reads", flat, 1, one_site, 1,
                   cand_body_polls_once_then_reads);
    /* ...and the same double-poller at nth = 3, where its extra poll lands on the iteration the
     * release was due anyway and NOTHING separates it from the faithful body. It is here to be
     * shown invisible: an `nth` that is a multiple of the port's polls-per-iteration hides exactly
     * this mutant, which is why the case below re-runs all three at nth = 4. */
    candidate_case("cand_polls_twice_at_an_aliasing_nth", flat, 1, one_site, 1,
                   cand_body_polls_twice_per_iteration);
    /* A POLL AT A SITE THE RUN DID NOT DECLARE is refused rather than counted. */
    candidate_case("cand_polls_at_an_undeclared_site", flat, 1, one_site, 1,
                   cand_body_polls_at_an_undeclared_site);

    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 4, WATCH_ADDR, 1, WANT);
    candidate_case("cand4_polls_the_wait", flat, 1, one_site, 1, cand_body_polls_the_wait);
    candidate_case("cand4_polls_once_then_reads", flat, 1, one_site, 1,
                   cand_body_polls_once_then_reads);
    candidate_case("cand4_polls_twice_per_iteration", flat, 1, one_site, 1,
                   cand_body_polls_twice_per_iteration);

    /* THE CAP. The store lands but stores the byte the wait ALREADY holds, so the wait is never
     * released — the shape a case gets when its declared value does not match the compare, and the
     * shape that used to HANG the whole suite. `sched_wait8` gives up at OS_SCHED_POLL_MAX and
     * tallies a refusal, which is what turns a hung run into a rejected case. */
    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 1, WATCH_ADDR, 1, HELD);
    candidate_case("cand_a_wait_that_is_never_released", flat, 1, one_site, 1, cand_body_waits);

    /* The candidate refuses the same out-of-image store the oracle refuses. Its wait then runs to
     * the body's own guard, which is what an unreleased poll loop looks like on this side. */
    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 1, OUTSIDE_ADDR, 4, SCRATCH_LONG);
    candidate_case("cand_a_store_outside_the_image", flat, 1, one_site, 1,
                   cand_body_polls_the_wait);

    /* ---- THE TWO-WAIT PAIR, and the measurement the whole remedy rests on ----
     * Both bodies run the SAME schedule the oracle's `two_waits` case ran. The faithful one polls
     * (1, 3), which is the oracle's (1, 3). The mutant that deletes the first wait polls (0, 3) —
     * caught site by site — and its RUN TOTAL is 3 where the faithful body's is 4, which is what
     * the per-site firing rule buys on top: under a run-total `nth` the entry would have fired on
     * the run's third poll either way, and both totals would have been 3. */
    set_entry(flat, 0, OS_SCHED_AT_PC, TWO_WAIT_SITE_2, TWO_WAIT_NTH, WATCH_ADDR, 1, WANT);
    candidate_case("cand_two_waits", flat, 1, two_sites, 2, cand_body_two_waits);
    candidate_case("cand_two_waits_first_deleted", flat, 1, two_sites, 2,
                   cand_body_two_waits_first_deleted);

    /* ---- THE WORD WAIT: the capped wrapper, against the oracle's own `cmpi.w` spin ---- */
    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 3, WORD_ADDR, 2, WORD_WANT);
    oracle_case("word_released_at_the_third_arrival", plant_word_spin, flat, 1, one_site, 1);
    candidate_case("cand_word_wait", flat, 1, one_site, 1, cand_body_word_wait);

    /* ...and its cap: the store lands and leaves the word as the wait already found it, so
     * sched_poll16 gives up at OS_SCHED_POLL_MAX with the same refusal sched_wait8 tallies. */
    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 1, WORD_ADDR, 2, WORD_HELD);
    candidate_case("cand_word_wait_never_released", flat, 1, one_site, 1, cand_body_word_wait);

    /* ...and the WORD wait at an UNDECLARED site, whose one poll must tally exactly as the byte
     * poll's does on the same refusal. */
    set_entry(flat, 0, OS_SCHED_AT_PC, PROBE_ENTRY, 3, WORD_ADDR, 2, WORD_WANT);
    candidate_case("cand_word_wait_at_an_undeclared_site", flat, 1, one_site, 1,
                   cand_body_word_wait_at_an_undeclared_site);
    return 0;
}
