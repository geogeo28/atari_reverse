/* psg_model_probe.c — the fixture behind test_psg_model.py.
 *
 * The seeded PSG read model (TRAP_MODEL.md, "Phase 6") is the one modeled surface with a side on
 * EACH shore: the oracle serves a `move.b $ff8800,dn` read-back out of ../oracle/shim.c's register
 * file, and a reconstruction reaches the identical model through ../src/psg.c. This probe drives
 * both in one process and prints what each produced, so the Python side can pin them against each
 * other — a miniature differential, which is the only way the kit's own suite can demonstrate the
 * false green the model closes (it binds no project, so it has no reconstruction to run).
 *
 * The same obstacle as entry_state_probe.c / reported_regs_probe.c: `harness`/`emu` bind a project's
 * candidate .so at import and this directory deliberately binds no project, so the oracle is
 * unreachable from Python here.
 *
 * Output is three line kinds, all owned by the Python side (a case printed without a claim there
 * fails loudly):
 *   K <case> <key> <value>              a scalar (the value a register held, a tally, a mask)
 *   L <case> <index> <kind> <reg> <val> one ordered ledger entry (kind = OS_PSG_EVENT_*)
 *   F <case> <reg> <value>              one byte of the modeled register file
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "os.h"      /* the refusal tally's ABI (src/os_refusal.c), and OS_PSG_* */
#include "psg.h"     /* the CANDIDATE side of the model (src/psg.c) */
#include "probe_common.h"   /* osh_run, the image geometry, the code planters */

/* ../oracle/shim.c ships no header — Python binds it by ctypes — so the entry points this probe
 * uses come from probe_common.h, which also carries the image geometry and the code planters, and
 * says exactly what that shared declaration does and does not guarantee. The model-specific exports
 * this probe reads are declared below. */
void            osh_psg_seed(const uint8_t *values, uint32_t known);
void            osh_audio_capture(int on);
void            osh_audio_reset(void);
const uint8_t  *osh_psg_file(void);
uint32_t        osh_psg_known(void);
uint32_t        osh_psg_unseeded(void);
uint32_t        osh_psg_no_select(void);
uint32_t        osh_psg_unmodeled(void);
uint32_t        osh_psg_nregs(void);
uint32_t        osh_psg_count(void);
const uint8_t  *osh_psg_kinds(void);
const uint8_t  *osh_psg_regs(void);
const uint8_t  *osh_psg_vals(void);

#define PROBE_MAX_INSNS  32u       /* the routines are a handful of instructions */

/* The ports come from os.h — one definition shared with shim.c, so this probe cannot plant code at
 * an address the oracle no longer decodes and still look like it tested the guard. */
#define PSG_SELECT OS_PSG_PORT_SELECT
#define PSG_DATA   OS_PSG_PORT_DATA

/* 68000 encodings, in the forms every real PSG driver uses (Wonder Boy's snd_psg_silence at $17f30
 * is `move.b #7,$ff8800; move.b $ff8800,d1; ori.b #$3f,d1; move.b d1,$ff8802` verbatim). */
#define MOVE_B_IMM_TO_ABSL 0x13fcu /* move.b #imm,(xxx).l */
#define MOVE_B_D1_TO_ABSL  0x13c1u /* move.b d1,(xxx).l */
#define ORI_B_IMM_D1       0x0001u /* ori.b #imm,d1 */
#define OPCODE_RTS         0x4e75u

/* The registers and values the cases use. Register 7 is the mixer, whose top two bits are the PSG's
 * port A/B DIRECTION lines: `ori.b #$3f` leaves them alone, so they are exactly the bits a read-back
 * exists to preserve and a fabricated 0 would destroy. */
#define MIXER_REG        7u
#define MIXER_SEED       0xc0u     /* the two port-direction bits, as TOS leaves them */
#define SILENCE_MASK     0x3fu     /* all six tone/noise enables off (active high in this register) */
#define MIXER_SILENCED   0xffu     /* MIXER_SEED | SILENCE_MASK: what the RMW must produce */
#define WRITE_ONLY_VALUE 0x0au     /* what the write-then-read-back case stores */
/* The TRANSPOSED read-modify-write's decoy: a second register seeded to the SAME byte as the mixer.
 * A candidate that reads THIS one and writes the mixer produces a correct run's write stream and a
 * correct run's register file — the read entry in the ordered ledger is the only thing that differs.
 * Volume A, chosen because a real replayer touches it in the same breath as the mixer. */
#define DECOY_REG        8u
/* A select the chip cannot decode: its upper nibble is non-zero. Refused, not masked down to 14. */
#define BAD_SELECT       0x1eu
/* Where a bare data write lands when nothing has selected a register — the latch's placeholder. */
#define UNSELECTED_REG   0u
#define LEAK_PROBE_REG   10u       /* the register the arm-from-off leak case selects, then must lose */

/* Each emitter plants one instruction at `addr` and returns the address after it. */
static uint32_t emit_select(uint32_t addr, uint8_t reg) {
    plant_word(addr, MOVE_B_IMM_TO_ABSL);
    plant_word(addr + 2, reg);
    return plant_long(addr + 4, PSG_SELECT);
}

static uint32_t emit_write_data(uint32_t addr, uint8_t value) {
    plant_word(addr, MOVE_B_IMM_TO_ABSL);
    plant_word(addr + 2, value);
    return plant_long(addr + 4, PSG_DATA);
}

static uint32_t emit_read_back(uint32_t addr, uint32_t port) {
    plant_word(addr, MOVE_B_ABSL_TO_D1);
    return plant_long(addr + 2, port);
}

static uint32_t emit_ori_d1(uint32_t addr, uint8_t mask) {
    plant_word(addr, ORI_B_IMM_D1);
    plant_word(addr + 2, mask);
    return addr + 4;
}

static uint32_t emit_write_d1(uint32_t addr) {
    plant_word(addr, MOVE_B_D1_TO_ABSL);
    return plant_long(addr + 2, PSG_DATA);
}

/* Install a seed declaring MIXER_REG and, when `known` names it, DECOY_REG — both holding
 * MIXER_SEED, which is what makes the transposed-read case's two surfaces identical to a correct
 * run's. A `known` of 0 withdraws the seed entirely. */
static void seed(uint16_t known) {
    uint8_t values[OS_PSG_NREGS];
    memset(values, 0, sizeof values);
    values[MIXER_REG] = MIXER_SEED;
    values[DECOY_REG] = MIXER_SEED;
    osh_psg_seed(values, known);
}

/* Print everything the model produced after a run. */
static void report_oracle(const char *name, uint32_t read_back) {
    printf("K %s d1 %u\n", name, read_back);           /* the read-back lands in d1 */
    printf("K %s unseeded %u\n", name, osh_psg_unseeded());
    printf("K %s no_select %u\n", name, osh_psg_no_select());
    printf("K %s unmodeled %u\n", name, osh_psg_unmodeled());
    printf("K %s known %u\n", name, osh_psg_known());
    uint32_t n = osh_psg_count();
    printf("K %s nlog %u\n", name, n);
    const uint8_t *kinds = osh_psg_kinds(), *regs = osh_psg_regs(), *vals = osh_psg_vals();
    for (uint32_t i = 0; i < n; i++)
        printf("L %s %u %u %u %u\n", name, i, kinds[i], regs[i], vals[i]);
    const uint8_t *file = osh_psg_file();
    for (uint32_t reg = 0; reg < osh_psg_nregs(); reg++)
        printf("F %s %u %u\n", name, reg, file[reg]);
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
 * the model's per-run reset. A bench issued after a seeded run must see the SEED, not that run's
 * leftovers. The bench's routine reads nothing, so the read-back is reported as 0. */
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

/* The candidate side's mirror of the same report, over ../src/psg.c's state. */
static void report_candidate(const char *name, uint32_t read_value, uint32_t refusals) {
    printf("K %s d1 %u\n", name, read_value);
    printf("K %s refusals %u\n", name, refusals);
    printf("K %s known %u\n", name, g_psg_file_known());
    uint32_t n = g_psg_log_count();
    printf("K %s nlog %u\n", name, n);
    const uint8_t *kinds = g_psg_log_kinds(), *regs = g_psg_log_regs(), *vals = g_psg_log_vals();
    for (uint32_t i = 0; i < n; i++)
        printf("L %s %u %u %u %u\n", name, i, kinds[i], regs[i], vals[i]);
    const uint8_t *file = g_psg_file();
    for (uint32_t reg = 0; reg < OS_PSG_NREGS; reg++)
        printf("F %s %u %u\n", name, reg, file[reg]);
}

/* Seed the candidate the way harness.differential does, run `body`, and report. The seed is the
 * SAME one the oracle cases get, so the two sides' cases are comparable pair by pair. */
static void candidate_case(const char *name, uint16_t known, void (*body)(uint32_t *read_value)) {
    uint8_t values[OS_PSG_NREGS];
    memset(values, 0, sizeof values);
    values[MIXER_REG] = MIXER_SEED;
    values[DECOY_REG] = MIXER_SEED;
    g_psg_reset(values, known);
    g_os_refusal_reset();
    uint32_t read_value = 0;
    body(&read_value);
    report_candidate(name, read_value, g_os_refusal_count());
}

/* The faithful reconstruction of the oracle's `rmw` routine: read the mixer, merge, write it back. */
static void cand_body_rmw(uint32_t *read_value) {
    uint8_t mixer = psg_port_read(MIXER_REG);
    *read_value = mixer;
    psg_port_write(MIXER_REG, (uint8_t)(mixer | SILENCE_MASK));
}

/* MUTANT 1 — it reads the mixer and never writes it back. The image diff cannot see this: the ports
 * are off-image, so nothing about the run's memory changes. */
static void cand_body_skips_the_write(uint32_t *read_value) {
    *read_value = psg_port_read(MIXER_REG);
}

/* MUTANT 2 — it writes the right register with the right mask but ignores the READ, i.e. drops the
 * read-modify-write's preserved bits. This is the defect a fabricated 0 read would have HIDDEN: with
 * the chip's prior contents invented as 0, `0 | $3f` and `read | $3f` agree. */
static void cand_body_ignores_the_read(uint32_t *read_value) {
    *read_value = 0;
    psg_port_write(MIXER_REG, SILENCE_MASK);
}

/* MUTANT 3 — the TRANSPOSED read-modify-write: it reads the WRONG register (the decoy, seeded to the
 * same byte the mixer holds) and writes the right one. Its write stream and its register file are a
 * correct run's, exactly; only the ordered ledger's READ entry names a different register. This is
 * the mutant that made reads part of the compared stream. */
static void cand_body_reads_the_wrong_register(uint32_t *read_value) {
    uint8_t decoy = psg_port_read(DECOY_REG);
    *read_value = decoy;
    psg_port_write(MIXER_REG, (uint8_t)(decoy | SILENCE_MASK));
}

/* ...and the same read the oracle refuses, made by the candidate: it must tally rather than serve. */
static void cand_body_unseeded_read(uint32_t *read_value) {
    *read_value = psg_port_read(MIXER_REG);
}

/* A register number the chip does not have. Refused on this side too, so that the two sides answer
 * the same way to the same mistake (the oracle counts a $ff8800 write above $0f unmodeled). */
static void cand_body_out_of_range_register(uint32_t *read_value) {
    psg_port_write(BAD_SELECT, SILENCE_MASK);
    *read_value = psg_port_read(BAD_SELECT);
}

int main(void) {
    probe_require_out_regs();
    probe_alloc_image();

    const uint16_t SEED_MIXER = 1u << MIXER_REG;
    const uint16_t SEED_MIXER_AND_DECOY = (1u << MIXER_REG) | (1u << DECOY_REG);

    /* --- a read of a register the case DECLARED, and of one it did not --- */
    uint32_t pc = emit_select(PROBE_ENTRY, MIXER_REG);
    pc = emit_read_back(pc, PSG_SELECT);
    plant_rts(pc);
    seed(SEED_MIXER);
    run_and_report("seeded_read");
    run_and_report("seeded_read_again");        /* the seed is not consumed by one run */
    seed(0);
    run_and_report("unseeded_read");            /* ...and clearing it restores the refusal */

    /* --- a read with nothing selected: the latch is not seedable, so this is its own refusal --- */
    pc = emit_read_back(PROBE_ENTRY, PSG_SELECT);
    plant_rts(pc);
    seed(SEED_MIXER);                           /* seeded, and still refused: the SELECT is missing */
    run_and_report("read_before_any_select");

    /* --- a select the chip cannot decode: refused, not masked down to register 14 --- */
    pc = emit_select(PROBE_ENTRY, BAD_SELECT);
    plant_rts(pc);
    run_and_report("high_nibble_select");

    /* --- the read-modify-write the whole model exists for --- */
    pc = emit_select(PROBE_ENTRY, MIXER_REG);
    pc = emit_read_back(pc, PSG_SELECT);
    pc = emit_ori_d1(pc, SILENCE_MASK);
    pc = emit_write_d1(pc);
    plant_rts(pc);
    seed(SEED_MIXER);
    run_and_report("rmw");

    /* The same routine with the seed withdrawn: the register the LAST run wrote must not still be
     * readable, or one case would be verified against another case's writes. */
    seed(0);
    run_and_report("rmw_unseeded");

    /* ...and once more with the DECOY register declared alongside the mixer, holding the same byte.
     * This is the oracle side of the transposed-read mutant below: identical write stream, identical
     * register file, and only the ledger's READ entry telling the two apart. */
    seed(SEED_MIXER_AND_DECOY);
    run_and_report("rmw_two_seeded");

    /* ...and now a BENCH, which reaches the model through the other entry point. It must start from
     * the same seed the run above did — register 7 back at $c0, not the $ff that run left. */
    bench_and_report("bench_after_a_seeded_run");

    /* --- a register this run wrote itself needs no seed: the chip reads back its own store --- */
    seed(0);
    pc = emit_select(PROBE_ENTRY, MIXER_REG);
    pc = emit_write_data(pc, WRITE_ONLY_VALUE);
    pc = emit_read_back(pc, PSG_SELECT);
    plant_rts(pc);
    run_and_report("write_then_read");

    /* --- the ordered ledger, unchanged: a write-only run's (reg,val) stream --- */
    pc = emit_select(PROBE_ENTRY, 0);
    pc = emit_write_data(pc, 0x11);
    pc = emit_select(pc, MIXER_REG);
    pc = emit_write_data(pc, SILENCE_MASK);
    pc = emit_select(pc, MIXER_REG);            /* the same register twice: order, not a set */
    pc = emit_write_data(pc, 0x0f);
    pc = emit_select(pc, 10);
    pc = emit_write_data(pc, 0x00);             /* a zero write: "written 0" is not "never written" */
    plant_rts(pc);
    run_and_report("write_only");

    /* --- what stays refused: the data port is write-only on the chip --- */
    pc = emit_select(PROBE_ENTRY, MIXER_REG);
    pc = emit_read_back(pc, PSG_DATA);
    plant_rts(pc);
    seed(SEED_MIXER);
    run_and_report("data_port_read");

    /* --- the audio-capture mode, which is this model RELAXED (and shares its one register file) ---
     * Its own cases live in projects/wonderboy (they need a real replayer); what is pinned here is
     * the relaxation itself, because that is a property of the shared model rather than of a game. */
    pc = emit_select(PROBE_ENTRY, LEAK_PROBE_REG);   /* a differential run SELECTS register 10... */
    pc = emit_write_data(pc, WRITE_ONLY_VALUE);      /* ...and leaves $0a in it */
    plant_rts(pc);
    seed(SEED_MIXER);
    run_and_report("before_capture");

    /* Arming from OFF must inherit NEITHER half of that chip state — not the register file, and not
     * the select latch. The latch is the half that was leaking: with only the file cleared, the bare
     * data write below landed in register 10, in a capture that never named it. */
    osh_audio_capture(1);
    pc = emit_write_data(PROBE_ENTRY, WRITE_ONLY_VALUE);   /* bare data write, nothing selected */
    plant_rts(pc);
    run_and_report("capture_bare_write_after_arming");

    osh_audio_reset();                           /* back to an empty capture for the reads below */
    pc = emit_select(PROBE_ENTRY, MIXER_REG);
    pc = emit_read_back(pc, PSG_SELECT);
    plant_rts(pc);
    run_and_report("capture_unknown_reads_zero");   /* the relaxation: 0, not a refusal */

    pc = emit_select(PROBE_ENTRY, MIXER_REG);
    pc = emit_write_data(pc, WRITE_ONLY_VALUE);
    plant_rts(pc);
    run_and_report("capture_write_tick");           /* one "VBL tick" writes the register... */
    pc = emit_select(PROBE_ENTRY, MIXER_REG);
    pc = emit_read_back(pc, PSG_SELECT);
    plant_rts(pc);
    run_and_report("capture_next_tick_reads_it");   /* ...and the next one reads it back */
    osh_audio_capture(0);

    /* --- the candidate side of the same model --- */
    candidate_case("cand_rmw", SEED_MIXER, cand_body_rmw);
    candidate_case("cand_skips_the_write", SEED_MIXER, cand_body_skips_the_write);
    candidate_case("cand_ignores_the_read", SEED_MIXER, cand_body_ignores_the_read);
    candidate_case("cand_rmw_two_seeded", SEED_MIXER_AND_DECOY, cand_body_rmw);
    candidate_case("cand_reads_the_wrong_register", SEED_MIXER_AND_DECOY,
                   cand_body_reads_the_wrong_register);
    candidate_case("cand_unseeded_read", 0, cand_body_unseeded_read);
    candidate_case("cand_out_of_range_register", SEED_MIXER, cand_body_out_of_range_register);

    free(g_image);
    return 0;
}
