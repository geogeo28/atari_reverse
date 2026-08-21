/* hw_model_probe.c — the fixture behind test_hw_model.py.
 *
 * The seeded HARDWARE read model (TRAP_MODEL.md, "Phase 7") is the second modeled surface with a
 * side on EACH shore: the oracle answers a `btst #7,$fffa01` out of ../oracle/shim.c's declared-byte
 * file, and a reconstruction reaches the identical model through ../src/hw.c. This probe drives both
 * in one process and prints what each produced, so the Python side can pin them against each other
 * — a miniature differential, which is the only way the kit's own suite can demonstrate the false
 * green the model closes (it binds no project, so it has no reconstruction to run).
 *
 * The same obstacle as psg_model_probe.c next door: `harness`/`emu` bind a project's candidate .so
 * at import and this directory deliberately binds no project, so the oracle is unreachable from
 * Python here.
 *
 * Output is three line kinds, all owned by the Python side (a case printed without a claim there
 * fails loudly):
 *   K <case> <key> <value>        a scalar (the byte a register held, a tally, a mask)
 *   L <case> <index> <slot> <val> one ordered read-ledger entry (slot = OS_HW_SLOT_*)
 *   F <case> <slot> <value>       one declared byte of the modeled file
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "os.h"      /* the refusal tally's ABI (src/os_refusal.c), and OS_HW_* */
#include "hw.h"      /* the CANDIDATE side of the model (src/hw.c) */
#include "probe_common.h"   /* osh_run, the image geometry, the code planters */

/* ../oracle/shim.c ships no header — Python binds it by ctypes — so the entry points this probe
 * uses come from probe_common.h, which also carries the image geometry and the code planters, and
 * says exactly what that shared declaration does and does not guarantee. The model-specific exports
 * this probe reads are declared below. */
void            osh_hw_seed(const uint8_t *values, uint32_t known);
void            osh_audio_capture(int on);
const uint8_t  *osh_hw_file(void);
uint32_t        osh_hw_known(void);
uint32_t        osh_hw_reread(void);
uint32_t        osh_hw_unseeded(void);
uint32_t        osh_hw_stale(void);
uint32_t        osh_hw_wide(void);
uint32_t        osh_hw_count(void);
const uint8_t  *osh_hw_log_slots(void);
const uint8_t  *osh_hw_log_vals(void);
const uint8_t  *osh_hw_capture_profile(void);

#define PROBE_MAX_INSNS  32u       /* the routines are a handful of instructions */

/* 68000 encodings. The byte read is the shape Wonder Boy's tempo selector has at $17c7e
 * (`btst.b #7,$fffa01`, which the 68000 executes as an absolute-long byte read); the word and long
 * forms are the same instruction widened, which is the shape the model refuses. */
#define MOVE_W_ABSL_TO_D1  0x3239u /* move.w (xxx).l,d1 */
#define MOVE_L_ABSL_TO_D1  0x2239u /* move.l (xxx).l,d1 */
#define MOVE_B_IMM_TO_ABSL 0x13fcu /* move.b #imm,(xxx).l */
#define OPCODE_RTS         0x4e75u

/* What the cases declare the machine holds. Both slots get the SAME byte, which is what makes the
 * wrong-address mutant's every other surface identical to a correct run's: only the ordered
 * ledger's slot separates the two. The value is arbitrary and deliberately NOT the capture
 * profile's, so a case that got the profile where it asked for a declaration is visible. */
#define DECLARED_BYTE 0x5au
/* A byte the machine cannot answer while it also answers DECLARED_BYTE — used where a case must
 * show WHICH declaration was installed. */
#define OTHER_BYTE    0xa5u
/* What the write-then-read case stores into the sync register: the game's own `move.b #2,$ff820a`
 * at Wonder Boy's $f91c. The model drops it, which is exactly why a read after it is refused. */
#define SYNC_50HZ     0x02u
/* An address the model does not name — the FDC status register, whose answer is a per-access
 * SEQUENCE that no per-run constant can express (TRAP_MODEL.md, Phase 7's non-goal). */
#define UNMODELED_HW_ADDR 0xff8604u

#define ALL_SLOTS_DECLARED ((1u << OS_HW_NSLOTS) - 1u)
#define SLOT_BIT(slot) (1u << (slot))

/* Each emitter plants one instruction at `addr` and returns the address after it. */
static uint32_t emit_read(uint32_t addr, uint16_t opcode, uint32_t hw_addr) {
    plant_word(addr, opcode);
    return plant_long(addr + 2, hw_addr);
}

static uint32_t emit_write_byte(uint32_t addr, uint8_t value, uint32_t hw_addr) {
    plant_word(addr, MOVE_B_IMM_TO_ABSL);
    plant_word(addr + 2, value);
    return plant_long(addr + 4, hw_addr);
}

/* Install a seed declaring the slots `known` names, each holding `value`. A `known` of 0 withdraws
 * the declaration entirely, which is what restores the model's fabricated 0. */
static void seed(uint32_t known, uint8_t value) {
    uint8_t values[OS_HW_NSLOTS];
    memset(values, value, sizeof values);
    osh_hw_seed(values, known);
}

/* Print everything the model produced after a run. */
static void report_oracle(const char *name, uint32_t read_value) {
    printf("K %s d1 %u\n", name, read_value);          /* the read lands in d1 */
    printf("K %s unseeded %u\n", name, osh_hw_unseeded());
    printf("K %s stale %u\n", name, osh_hw_stale());
    printf("K %s wide %u\n", name, osh_hw_wide());
    printf("K %s reread %u\n", name, osh_hw_reread());
    printf("K %s known %u\n", name, osh_hw_known());
    uint32_t n = osh_hw_count();
    printf("K %s nlog %u\n", name, n);
    const uint8_t *slots = osh_hw_log_slots(), *vals = osh_hw_log_vals();
    for (uint32_t i = 0; i < n; i++)
        printf("L %s %u %u %u\n", name, i, slots[i], vals[i]);
    const uint8_t *file = osh_hw_file();
    for (int slot = 0; slot < OS_HW_NSLOTS; slot++)
        printf("F %s %d %u\n", name, slot, file[slot]);
}

/* Run whatever is planted at PROBE_ENTRY and report. The image is NOT cleared between runs — only
 * the code is re-planted — because one of the claims is that the MODEL's own state does not carry
 * over even when the image does. */
static void run_and_report(const char *name) {
    uint32_t dregs[NREGS] = {0}, aregs[NREGS] = {0}, out[OUT_REGS] = {0};
    if (!osh_run(g_image, PROBE_IMAGE_SIZE, PROBE_ENTRY, dregs, aregs,
                 PROBE_SP, PROBE_SENTINEL, 0, PROBE_MAX_INSNS, out)) {
        fprintf(stderr, "%s: the probe's routine did not return to the sentinel\n", name);
        exit(1);
    }
    report_oracle(name, out[1] & 0xffu);
}

/* The same, through osh_run_bench — the OTHER entry point into the oracle, which a perf measurement
 * uses and which installs no OS traps. Its routine here is a bare `rts`: what the case is about is
 * the state the bench STARTS from, since both entry points share enter_from_reset() and therefore
 * the model's per-run reinstall. osh_run_bench writes only out[0], so the read is reported as 0. */
static void bench_and_report(const char *name) {
    uint32_t out[OUT_REGS] = {0};
    plant_rts(PROBE_ENTRY);
    if (!osh_run_bench(g_image, PROBE_IMAGE_SIZE, PROBE_ENTRY, 0,
                       PROBE_SP, PROBE_SENTINEL, PROBE_MAX_INSNS, out)) {
        fprintf(stderr, "%s: the bench's routine did not return to the sentinel\n", name);
        exit(1);
    }
    report_oracle(name, 0);
}

/* The capture mode's own profile, so the Python side can pin "the mode serves this" against "a case
 * declaring the same bytes serves the same" without holding a copy of the constants. */
static void report_capture_profile(void) {
    const uint8_t *profile = osh_hw_capture_profile();
    for (int slot = 0; slot < OS_HW_NSLOTS; slot++)
        printf("F capture_profile %d %u\n", slot, profile[slot]);
}

/* The candidate side's mirror of the same report, over ../src/hw.c's state. */
static void report_candidate(const char *name, uint32_t read_value, uint32_t refusals) {
    printf("K %s d1 %u\n", name, read_value);
    printf("K %s refusals %u\n", name, refusals);
    printf("K %s known %u\n", name, g_hw_file_known());
    uint32_t n = g_hw_log_count();
    printf("K %s nlog %u\n", name, n);
    const uint8_t *slots = g_hw_log_slots(), *vals = g_hw_log_vals();
    for (uint32_t i = 0; i < n; i++)
        printf("L %s %u %u %u\n", name, i, slots[i], vals[i]);
    const uint8_t *file = g_hw_file();
    for (int slot = 0; slot < OS_HW_NSLOTS; slot++)
        printf("F %s %d %u\n", name, slot, file[slot]);
}

/* Seed the candidate the way harness.differential does, run `body`, and report. The seed is the SAME
 * one the oracle cases get, so the two sides' cases are comparable pair by pair. */
static void candidate_case(const char *name, uint32_t known, void (*body)(uint32_t *read_value)) {
    uint8_t values[OS_HW_NSLOTS];
    memset(values, DECLARED_BYTE, sizeof values);
    g_hw_reset(values, known);
    g_os_refusal_reset();
    uint32_t read_value = 0;
    body(&read_value);
    report_candidate(name, read_value, g_os_refusal_count());
}

/* The faithful reconstruction of the oracle's routine: read the monitor-detect byte. */
static void cand_body_reads_the_gpip(uint32_t *read_value) {
    *read_value = hw_read8(OS_HW_MFP_GPIP);
}

/* MUTANT — it reads the OTHER modeled address, declared to the same byte. Every surface but the
 * ordered ledger is a correct run's: the value it branches on is identical, the declared file is
 * identical, and the image is untouched either way. Only the ledger's slot separates them, which is
 * why the comparison is over the ordered stream rather than over the bytes served. */
static void cand_body_reads_the_wrong_address(uint32_t *read_value) {
    *read_value = hw_read8(OS_HW_SHIFTER_SYNC);
}

/* MUTANT — it never reads at all and hardcodes the answer, which is exactly what a port written
 * against a fabricated 0 looks like. Its ledger is empty where the oracle's has an entry. */
static void cand_body_skips_the_read(uint32_t *read_value) {
    *read_value = DECLARED_BYTE;
}

/* ...and the same read the oracle serves 0, made by the candidate against no declaration: it must
 * tally a refusal rather than answer, and log the read anyway (the oracle logs its own). */
static void cand_body_undeclared_read(uint32_t *read_value) {
    *read_value = hw_read8(OS_HW_MFP_GPIP);
}

/* An address outside the modeled set. Refused AND unlogged: the oracle records nothing for it
 * either, so a ledger entry here would diverge the streams for a reason that is not about a read
 * the model claims to serve. */
static void cand_body_unmodeled_address(uint32_t *read_value) {
    *read_value = hw_read8(UNMODELED_HW_ADDR);
}

int main(void) {
    probe_require_out_regs();
    probe_alloc_image();

    const uint32_t GPIP_ONLY = SLOT_BIT(OS_HW_SLOT_MFP_GPIP);

    /* --- a read of an address the case DECLARED, and of one it did not --- */
    uint32_t pc = emit_read(PROBE_ENTRY, MOVE_B_ABSL_TO_D1, OS_HW_MFP_GPIP);
    plant_rts(pc);
    seed(GPIP_ONLY, DECLARED_BYTE);
    run_and_report("declared_read");
    run_and_report("declared_read_again");      /* the seed is not consumed by one run */
    seed(0, DECLARED_BYTE);
    run_and_report("undeclared_read");          /* ...and withdrawing it restores the 0 */

    /* --- THE VIDEO COUNTER, the pair added for Wonder Boy's $51ac. Its two bytes are read once
     * each per call and summed into an arithmetic result rather than branched on, so what a
     * fabricated 0 costs is not a wrong branch but a draw that collapses to a constant. Same three
     * shapes as the pair above, over the two new slots, so that "the model grew" is a claim about
     * behaviour and not only about a table's length. --- */
    const uint32_t VCOUNT_PAIR = SLOT_BIT(OS_HW_SLOT_SHIFTER_VCOUNT_MID)
                                 | SLOT_BIT(OS_HW_SLOT_SHIFTER_VCOUNT_LOW);
    pc = emit_read(PROBE_ENTRY, MOVE_B_ABSL_TO_D1, OS_HW_SHIFTER_VCOUNT_MID);
    pc = emit_read(pc, MOVE_B_ABSL_TO_D1, OS_HW_SHIFTER_VCOUNT_LOW);
    plant_rts(pc);
    seed(VCOUNT_PAIR, DECLARED_BYTE);
    run_and_report("vcount_pair_declared");
    seed(GPIP_ONLY, DECLARED_BYTE);
    run_and_report("vcount_pair_undeclared");   /* the two OLD slots' declaration is not theirs */

    /* ...and a WRITE to one of them makes the seed stale, exactly as it does for the sync byte. */
    pc = emit_write_byte(PROBE_ENTRY, DECLARED_BYTE, OS_HW_SHIFTER_VCOUNT_LOW);
    pc = emit_read(pc, MOVE_B_ABSL_TO_D1, OS_HW_SHIFTER_VCOUNT_LOW);
    plant_rts(pc);
    seed(ALL_SLOTS_DECLARED, DECLARED_BYTE);
    run_and_report("vcount_write_then_read");

    /* --- THE VOLATILE RULE, which is what makes os.h's admissibility argument enforceable. A
     * static byte may be read as often as a run likes, since one declaration describes every read
     * of it; a volatile one may be read ONCE, because the second answer a per-run constant gives is
     * the first one and the machine's would not be. --- */
    pc = emit_read(PROBE_ENTRY, MOVE_B_ABSL_TO_D1, OS_HW_SHIFTER_VCOUNT_LOW);
    pc = emit_read(pc, MOVE_B_ABSL_TO_D1, OS_HW_SHIFTER_VCOUNT_LOW);
    plant_rts(pc);
    seed(ALL_SLOTS_DECLARED, DECLARED_BYTE);
    run_and_report("volatile_read_twice");

    pc = emit_read(PROBE_ENTRY, MOVE_B_ABSL_TO_D1, OS_HW_MFP_GPIP);
    pc = emit_read(pc, MOVE_B_ABSL_TO_D1, OS_HW_MFP_GPIP);
    plant_rts(pc);
    seed(ALL_SLOTS_DECLARED, DECLARED_BYTE);
    run_and_report("static_read_twice");

    /* --- declaring ONE address does not declare the other --- */
    pc = emit_read(PROBE_ENTRY, MOVE_B_ABSL_TO_D1, OS_HW_SHIFTER_SYNC);
    plant_rts(pc);
    seed(GPIP_ONLY, DECLARED_BYTE);
    run_and_report("other_address_undeclared");

    /* --- the ORDER of two reads, which is the whole of what the ledger comparison adds --- */
    pc = emit_read(PROBE_ENTRY, MOVE_B_ABSL_TO_D1, OS_HW_SHIFTER_SYNC);
    pc = emit_read(pc, MOVE_B_ABSL_TO_D1, OS_HW_MFP_GPIP);
    plant_rts(pc);
    seed(ALL_SLOTS_DECLARED, DECLARED_BYTE);
    run_and_report("two_reads_in_order");

    /* --- a WIDE read taking the byte in: served nothing, tallied, and NOT ledgered.
     * Declared, so that the refusal cannot be mistaken for a missing declaration. --- */
    seed(GPIP_ONLY, DECLARED_BYTE);
    /* From the EVEN address below it: a word read AT $fffa01 would be an address error on a real
     * 68000 (only the kit's M68K_EMULATE_ADDRESS_ERROR=OFF lets one execute at all), so the case
     * would stop measuring the wide-read refusal the day that flag moved. Every wide shape here is
     * one a 68000 can really execute. */
    pc = emit_read(PROBE_ENTRY, MOVE_W_ABSL_TO_D1, OS_HW_MFP_GPIP - 1);
    plant_rts(pc);
    run_and_report("word_read");
    pc = emit_read(PROBE_ENTRY, MOVE_L_ABSL_TO_D1, OS_HW_SHIFTER_SYNC);
    plant_rts(pc);
    run_and_report("long_read");
    /* ...and one that straddles INTO a modeled byte from below, the case an equality test misses. */
    pc = emit_read(PROBE_ENTRY, MOVE_L_ABSL_TO_D1, OS_HW_SHIFTER_SYNC - 2);
    plant_rts(pc);
    run_and_report("long_read_straddling_in");

    /* --- the run WRITES the address and then reads it back: the declaration is stale.
     * Declared, deliberately: the point is that a case CAN declare this byte and still be wrong. --- */
    seed(ALL_SLOTS_DECLARED, DECLARED_BYTE);
    pc = emit_write_byte(PROBE_ENTRY, SYNC_50HZ, OS_HW_SHIFTER_SYNC);
    pc = emit_read(pc, MOVE_B_ABSL_TO_D1, OS_HW_SHIFTER_SYNC);
    plant_rts(pc);
    run_and_report("write_then_read");
    /* ...while a write NOTHING reads back is the ordinary invisible hardware write it always was. */
    pc = emit_write_byte(PROBE_ENTRY, SYNC_50HZ, OS_HW_SHIFTER_SYNC);
    plant_rts(pc);
    run_and_report("write_only");

    /* --- the AUDIO-CAPTURE fold: the mode is a SEED over this model, not a switch beside it --- */
    report_capture_profile();
    pc = emit_read(PROBE_ENTRY, MOVE_B_ABSL_TO_D1, OS_HW_MFP_GPIP);
    pc = emit_read(pc, MOVE_B_ABSL_TO_D1, OS_HW_SHIFTER_SYNC);
    plant_rts(pc);
    seed(0, DECLARED_BYTE);                     /* nothing declared: off the mode both read 0 */
    run_and_report("profile_pair_undeclared");
    osh_audio_capture(1);
    run_and_report("profile_pair_under_capture");
    /* ...and the mode's declaration WINS over a case's, which is why emu.run refuses to take one. */
    seed(ALL_SLOTS_DECLARED, OTHER_BYTE);
    run_and_report("capture_overrides_a_seed");
    osh_audio_capture(0);
    /* ...but does not survive the mode: the very next run is back on the case's own declaration, with
     * no reset call, which is what stops the profile leaking into a differential. */
    run_and_report("after_capture_the_case_seed_returns");

    /* --- the seed is per-RUN state, and the bench shares it (both go through enter_from_reset) --- */
    seed(ALL_SLOTS_DECLARED, DECLARED_BYTE);
    bench_and_report("bench_starts_from_the_seed");

    /* --- the candidate side, seeded and run exactly as harness.differential does it --- */
    candidate_case("cand_declared_read", ALL_SLOTS_DECLARED, cand_body_reads_the_gpip);
    candidate_case("cand_wrong_address", ALL_SLOTS_DECLARED, cand_body_reads_the_wrong_address);
    candidate_case("cand_skips_the_read", ALL_SLOTS_DECLARED, cand_body_skips_the_read);
    candidate_case("cand_undeclared_read", 0, cand_body_undeclared_read);
    candidate_case("cand_unmodeled_address", ALL_SLOTS_DECLARED, cand_body_unmodeled_address);
    /* ...and the reset really clears: a case declaring nothing must not see the previous one's. */
    candidate_case("cand_seed_does_not_leak", 0, cand_body_reads_the_gpip);

    free(g_image);
    return 0;
}
