/* io_model_probe.c — the fixture behind test_io_model.py.
 *
 * The DECLARED I/O MAP (TRAP_MODEL.md, "Phase 15") is the third modeled surface with a side on EACH
 * shore: the oracle answers a `move.b $ffff8260,d0` out of ../oracle/shim.c's declared map, and a
 * reconstruction reaches the identical map through ../src/hw.c's `io_read8`. This probe drives both
 * in one process and prints what each produced, so the Python side can pin them against each other
 * — a miniature differential, which is the only way the kit's own suite can demonstrate the false
 * green the model closes (it binds no project, so it has no reconstruction to run).
 *
 * The same obstacle as hw_model_probe.c next door: `harness`/`emu` bind a project's candidate .so
 * at import and this directory deliberately binds no project, so the oracle is unreachable from
 * Python here.
 *
 * Output is the shared line protocol (probe_build.py owns the parser):
 *   K <case> <key> <value>              a scalar (a register, a tally, a count)
 *   L <case> <index> <addr> <w> <val>   one ordered ledger entry — width in BYTES
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "os.h"      /* the refusal tally's ABI (src/os_refusal.c), and the model's own helpers */
#include "hw.h"      /* the CANDIDATE side of the model (src/hw.c) */
#include "probe_common.h"   /* osh_run, the image geometry, the code planters */

/* ../oracle/shim.c ships no header — Python binds it by ctypes — so the entry points this probe
 * uses come from probe_common.h, which also says exactly what that shared declaration does and does
 * not guarantee. The model-specific exports this probe reads are declared below. */
void            osh_io_seed(const uint32_t *addrs, const uint8_t *values, const uint8_t *writeback,
                            uint32_t n);
uint32_t        osh_io_seed_count(void);
uint32_t        osh_io_seed_max(void);
uint32_t        osh_io_stale_reads(void);
uint32_t        osh_io_stale_first(void);
uint32_t        osh_io_count(void);
const uint32_t *osh_io_log_addrs(void);
const uint8_t  *osh_io_log_widths(void);
const uint32_t *osh_io_log_vals(void);
uint32_t        osh_io_unmodeled_reads(void);
uint32_t        osh_io_unmodeled_first(void);
/* ...and the NAMED SET's, for the one case that pins the two models' precedence: a read of a
 * Phase-7 slot must reach Phase 7 and leave this model's ledger empty. */
uint32_t        osh_hw_unseeded(void);
uint32_t        osh_hw_count(void);

#define PROBE_MAX_INSNS  32u       /* the routines are a handful of instructions */

/* The addresses the cases declare. Real registers, not arbitrary ones, because each stands for the
 * shape it is here to measure: the shifter's RESOLUTION byte is what XBIOS Getrez reads (one byte,
 * the model's founding case); the two PALETTE bytes are one colour word, which is the WIDE shape —
 * a word read of them is served only because BOTH were declared, where Phase 7 would have had to
 * fabricate the neighbour; and the VIDEO BASE's high byte is a second single byte, so that "two
 * reads in order" is a claim about the ledger rather than about one address read twice. */
#define SHIFTER_RESOLUTION 0xff8260u
#define PALETTE_0_HI       0xff8240u
#define PALETTE_0_LO       0xff8241u
#define VIDEO_BASE_HI      0xff8201u
/* An address in the page that NO case declares, used where the point is the refusal. */
#define UNDECLARED_IO_ADDR 0xff8604u   /* the FDC status register: a sequence, never a constant */
/* ...and the UNTRANSLATED spelling of the shifter register above — the form a hardware manual
 * prints, which the 68000's 24 address lines fold onto SHIFTER_RESOLUTION before anything decodes
 * it. No read can ever be keyed on it, so a declaration that is must be refused. */
#define UNTRANSLATED_IO_ADDR 0xffff8260u
/* Where the CAP case's OS_IO_SEED_MAX + 1 consecutive declarations start. The run of them must clear
 * every named model's addresses, or the case would measure an EXCLUSION (declarations the rule
 * rejected) rather than the cap — and it would measure it silently, since both produce a map
 * smaller than the case wrote. The static assert below is what says so; the shifter's block from
 * $ff8000 up is the space between the I/O page's start and Phase 6's chip. */
#define CAP_PROBE_BASE (OS_HW_IO_PAGE + 0x8000u)
_Static_assert(CAP_PROBE_BASE + OS_IO_SEED_MAX < OS_PSG_PORT_SELECT,
               "the cap probe's declarations now run into the YM2149's block, which os_io_seedable "
               "rejects — the case would measure that exclusion instead of OS_IO_SEED_MAX");

/* What the cases declare those addresses hold. Distinct bytes, so a mutant that reads the WRONG
 * declared address diverges on the value as well as on the ledger — except where a case deliberately
 * declares two addresses to ONE byte, which is how the wrong-address mutant is made invisible to
 * everything but the ordered stream. */
#define RESOLUTION_MONO      0x02u   /* bits 0-1 = 2: the ST's monochrome mode, which Getrez reports */
#define PALETTE_HI_BYTE     0x07u
#define PALETTE_LO_BYTE     0x77u
#define VIDEO_BASE_BYTE     0x03u
/* A byte the machine cannot answer while it also answers the ones above — used where a case must
 * show WHICH declaration was installed, and as the value a store overwrites the map's with. */
#define OTHER_BYTE          0xa5u

/* Install a declaration of per-run CONSTANTS. `n` may be 0, which withdraws the previous one
 * entirely — the shape that restores the fabricated 0 this model exists to replace. */
static void declare(const uint32_t *addrs, const uint8_t *values, uint32_t n) {
    osh_io_seed(addrs, values, (const uint8_t *)0, n);
}

/* ...and one carrying the WRITE-THROUGH column, which is what makes a store to a marked address
 * replace the byte later reads are served (os.h, OS_IO_WRITE_THROUGH). */
static void declare_with_writeback(const uint32_t *addrs, const uint8_t *values,
                                   const uint8_t *writeback, uint32_t n) {
    osh_io_seed(addrs, values, writeback, n);
}

/* The four addresses and bytes almost every case declares, in one place so a case that wants a
 * SUBSET spells the subset rather than a second copy of the whole. */
static const uint32_t ALL_ADDRS[] = {SHIFTER_RESOLUTION, PALETTE_0_HI, PALETTE_0_LO, VIDEO_BASE_HI};
static const uint8_t  ALL_VALUES[] = {RESOLUTION_MONO, PALETTE_HI_BYTE, PALETTE_LO_BYTE,
                                      VIDEO_BASE_BYTE};
#define ALL_N ((uint32_t)(sizeof ALL_ADDRS / sizeof ALL_ADDRS[0]))

/* ...and the WRITE-THROUGH column for those four: the resolution byte alone is marked, which is
 * what makes "a store to a MARKED address latches and a store to an unmarked one goes stale" a
 * claim about the mark rather than about the map. */
static const uint8_t ALL_WRITE_THROUGH[] = {OS_IO_WRITE_THROUGH, OS_IO_DECLARED_CONSTANT,
                                            OS_IO_DECLARED_CONSTANT, OS_IO_DECLARED_CONSTANT};
_Static_assert(sizeof ALL_WRITE_THROUGH == sizeof ALL_VALUES,
               "the write-through column must cover every declaration it is installed beside");

/* ...and the pair a WIDE store straddles: the palette word's high byte marked and its low byte not,
 * so one `move.w` reaches both rules at once. */
static const uint32_t STRADDLE_ADDRS[] = {PALETTE_0_HI, PALETTE_0_LO};
static const uint8_t  STRADDLE_VALUES[] = {PALETTE_HI_BYTE, PALETTE_LO_BYTE};
static const uint8_t  STRADDLE_WRITE_THROUGH[] = {OS_IO_WRITE_THROUGH, OS_IO_DECLARED_CONSTANT};
#define STRADDLE_N ((uint32_t)(sizeof STRADDLE_ADDRS / sizeof STRADDLE_ADDRS[0]))

/* ...and the four CONSECUTIVE bytes a LONG read covers — the palette's first colour word and the
 * one beside it. Declared at file scope because both shores' long-read cases share it, and they are
 * only comparable while they run against the same declaration. */
static const uint32_t LONG_ADDRS[] = {PALETTE_0_HI, PALETTE_0_LO, PALETTE_0_HI + 2, PALETTE_0_HI + 3};
static const uint8_t  LONG_VALUES[] = {PALETTE_HI_BYTE, PALETTE_LO_BYTE, OTHER_BYTE, RESOLUTION_MONO};
#define LONG_N ((uint32_t)(sizeof LONG_ADDRS / sizeof LONG_ADDRS[0]))

/* Print everything the model produced after a run. */
static void report_oracle(const char *name, uint32_t read_value) {
    printf("K %s d1 %u\n", name, read_value);          /* the read lands in d1 */
    printf("K %s declared %u\n", name, osh_io_seed_count());
    printf("K %s unmodeled %u\n", name, osh_io_unmodeled_reads());
    printf("K %s unmodeled_first %u\n", name, osh_io_unmodeled_first());
    printf("K %s stale %u\n", name, osh_io_stale_reads());
    printf("K %s stale_first %u\n", name, osh_io_stale_first());
    printf("K %s hw_unseeded %u\n", name, osh_hw_unseeded());
    printf("K %s hw_nlog %u\n", name, osh_hw_count());
    uint32_t n = osh_io_count();
    printf("K %s nlog %u\n", name, n);
    const uint32_t *addrs = osh_io_log_addrs(), *vals = osh_io_log_vals();
    const uint8_t *widths = osh_io_log_widths();
    for (uint32_t i = 0; i < n; i++)
        printf("L %s %u %u %u %u\n", name, i, addrs[i], widths[i], vals[i]);
}

/* This model serves reads of every width, so a case reports the WHOLE of D1 — a long read's value
 * does not fit in anything narrower. The two drivers themselves are probe_common.h's, shared with
 * hw_model_probe.c. */
#define IO_READ_MASK 0xffffffffu

static void run_and_report(const char *name) {
    probe_run_and_report(name, IO_READ_MASK, PROBE_MAX_INSNS, report_oracle);
}

static void bench_and_report(const char *name) {
    probe_bench_and_report(name, PROBE_MAX_INSNS, report_oracle);
}

/* The candidate side's mirror of the same report, over ../src/hw.c's state. */
static void report_candidate(const char *name, uint32_t read_value, uint32_t refusals) {
    printf("K %s d1 %u\n", name, read_value);
    printf("K %s refusals %u\n", name, refusals);
    printf("K %s declared %u\n", name, g_io_seed_count());
    uint32_t n = g_io_log_count();
    printf("K %s nlog %u\n", name, n);
    const uint32_t *addrs = g_io_log_addrs(), *vals = g_io_log_vals();
    const uint8_t *widths = g_io_log_widths();
    for (uint32_t i = 0; i < n; i++)
        printf("L %s %u %u %u %u\n", name, i, addrs[i], widths[i], vals[i]);
}

/* Seed the candidate the way harness.differential does, run `body`, and report. The declaration is
 * the SAME one the oracle cases get, so the two sides' cases are comparable pair by pair. */
static void candidate_case_with_writeback(const char *name, const uint32_t *addrs,
                                          const uint8_t *values, const uint8_t *writeback,
                                          uint32_t n, void (*body)(uint32_t *read_value)) {
    /* The refusal tally FIRST, then the declaration — `harness.arm_candidate`'s own order, and it
     * is load-bearing: `g_io_reset` charges a refusal for a declaration os.h's rule rejected, and
     * clearing the tally after it would throw that away. */
    g_os_refusal_reset();
    g_io_reset(addrs, values, writeback, n);
    uint32_t read_value = 0;
    body(&read_value);
    report_candidate(name, read_value, g_os_refusal_count());
}

/* ...and the ordinary form, whose every declaration is a per-run CONSTANT. */
static void candidate_case(const char *name, const uint32_t *addrs, const uint8_t *values,
                           uint32_t n, void (*body)(uint32_t *read_value)) {
    candidate_case_with_writeback(name, addrs, values, (const uint8_t *)0, n, body);
}

/* The faithful reconstruction of the oracle's routine: read the shifter's resolution byte. */
static void cand_body_reads_the_resolution(uint32_t *read_value) {
    *read_value = io_read8(SHIFTER_RESOLUTION);
}

/* MUTANT — it reads a DIFFERENT declared address. The cases that use it declare both to the same
 * byte, so every surface but the ordered ledger is a correct run's: the value it returns is
 * identical and the image is untouched either way. Only the ledger's address separates them, which
 * is why the comparison is over the ordered stream rather than over the bytes served. */
static void cand_body_reads_the_wrong_address(uint32_t *read_value) {
    *read_value = io_read8(VIDEO_BASE_HI);
}

/* MUTANT — it never reads at all and hardcodes the answer, which is exactly what a port written
 * against a fabricated 0 looks like once the byte is declared. Its ledger is empty where the
 * oracle's has an entry. */
static void cand_body_skips_the_read(uint32_t *read_value) {
    *read_value = RESOLUTION_MONO;
}

/* ...and the same read the oracle counts as unmodeled, made by the candidate against no
 * declaration: it must tally a refusal rather than answer, and log NOTHING — the oracle has no
 * entry for it either, so an entry here would diverge the streams for a reason that is not about
 * this read. */
static void cand_body_undeclared_read(uint32_t *read_value) {
    *read_value = io_read8(UNDECLARED_IO_ADDR);
}

/* A WORD read of the palette's two declared bytes: ONE ledger entry of width 2, big-endian, which
 * is what the oracle's own `move.w` produces. */
static void cand_body_reads_the_palette_word(uint32_t *read_value) {
    *read_value = io_read16(PALETTE_0_HI);
}

/* MUTANT — two byte reads where the original made one word read. Both bytes are declared, so both
 * are served and the VALUE the routine computes can be made identical; the ledger holds two entries
 * of width 1 where the oracle's holds one of width 2, which is the only witness. */
static void cand_body_reads_the_palette_as_two_bytes(uint32_t *read_value) {
    *read_value = (uint32_t)io_read8(PALETTE_0_HI) << 8 | io_read8(PALETTE_0_LO);
}

/* A LONG read of the four declared bytes: ONE ledger entry of width 4, big-endian, which is what
 * the oracle's own `move.l` produces. */
static void cand_body_reads_the_long(uint32_t *read_value) {
    *read_value = io_read32(PALETTE_0_HI);
}

/* ---- the WRITE-THROUGH arm's candidate bodies (os.h, OS_IO_WRITE_THROUGH) ----
 * A marked declaration says the register LATCHES what is stored and reads it back, so a store
 * through `hw_write8` replaces what the next `io_read8` of the address is served. */

/* The faithful shape the arm exists for: store, then read the register back. */
static void cand_body_stores_then_reads_back(uint32_t *read_value) {
    hw_write8(SHIFTER_RESOLUTION, OTHER_BYTE);
    *read_value = io_read8(SHIFTER_RESOLUTION);
}

/* ...and the same read with NO store before it, which must be served the declared entry byte: a
 * marked byte the run never stores to is an ordinary declaration. */
static void cand_body_reads_without_storing(uint32_t *read_value) {
    *read_value = io_read8(SHIFTER_RESOLUTION);
}

/* MUTANT — it reads BEFORE it stores, so it is served the byte the machine held on ENTRY where the
 * original was served what it had just written. That is what a port written against the model
 * WITHOUT this arm looks like, and the ledger's VALUE is what separates it. */
static void cand_body_reads_back_before_storing(uint32_t *read_value) {
    *read_value = io_read8(SHIFTER_RESOLUTION);
    hw_write8(SHIFTER_RESOLUTION, OTHER_BYTE);
}

/* MUTANT — it stores a DIFFERENT byte, which the register then latches: the write ledger's value
 * and the read ledger's value both move, from one wrong store. */
static void cand_body_stores_a_different_value(uint32_t *read_value) {
    hw_write8(SHIFTER_RESOLUTION, RESOLUTION_MONO);
    *read_value = io_read8(SHIFTER_RESOLUTION);
}

/* A WIDE store straddling a MARKED byte and an unmarked one: the marked half latches and the
 * unmarked half keeps its declaration (on the oracle it also goes stale, which is that side's
 * tally). The word read after it is therefore half what the run wrote and half what it declared. */
static void cand_body_wide_store_then_word_read(uint32_t *read_value) {
    hw_write16(PALETTE_0_HI, (uint32_t)OTHER_BYTE << 8 | OTHER_BYTE);
    *read_value = io_read16(PALETTE_0_HI);
}

/* MUTANT — two word reads where the original made one long read. Both halves are declared, so the
 * value it computes is identical; the ledger holds two entries of width 2 where the oracle's holds
 * one of width 4, which is the only witness. */
static void cand_body_reads_the_long_as_two_words(uint32_t *read_value) {
    *read_value = (uint32_t)io_read16(PALETTE_0_HI) << 16 | io_read16(PALETTE_0_HI + 2);
}

int main(void) {
    probe_require_out_regs();
    probe_alloc_image();

    /* --- a read of an address the case DECLARED, and of one it did not --- */
    uint32_t pc = emit_read(PROBE_ENTRY, MOVE_B_ABSL_TO_D1, SHIFTER_RESOLUTION);
    plant_rts(pc);
    declare(ALL_ADDRS, ALL_VALUES, ALL_N);
    run_and_report("declared_read");
    run_and_report("declared_read_again");      /* the declaration is not consumed by one run */
    declare(ALL_ADDRS, ALL_VALUES, 0);
    run_and_report("undeclared_read");          /* ...and withdrawing it restores the 0 */

    /* --- a declared byte read TWICE. There is no volatile rule here and that is the model's
     * stated limit: a declaration is a per-run CONSTANT, so both reads are served the same byte and
     * both are ledgered. A register whose two reads must DIFFER is Phase 8's shape, not this one's. */
    pc = emit_read(PROBE_ENTRY, MOVE_B_ABSL_TO_D1, SHIFTER_RESOLUTION);
    pc = emit_read(pc, MOVE_B_ABSL_TO_D1, SHIFTER_RESOLUTION);
    plant_rts(pc);
    declare(ALL_ADDRS, ALL_VALUES, ALL_N);
    run_and_report("declared_read_twice");

    /* --- the ORDER of two reads, which is the whole of what the ledger comparison adds --- */
    pc = emit_read(PROBE_ENTRY, MOVE_B_ABSL_TO_D1, VIDEO_BASE_HI);
    pc = emit_read(pc, MOVE_B_ABSL_TO_D1, SHIFTER_RESOLUTION);
    plant_rts(pc);
    run_and_report("two_reads_in_order");

    /* --- A WORD IS TWO DECLARED BYTES. This is the honest generalisation of Phase 7's wide-read
     * refusal: there the neighbouring register could not be described at all, here it can, so a
     * case that declares both bytes has said what the word holds — and one that declares only the
     * first has not, and the refusal names the byte that is MISSING rather than the access. --- */
    pc = emit_read(PROBE_ENTRY, MOVE_W_ABSL_TO_D1, PALETTE_0_HI);
    plant_rts(pc);
    run_and_report("word_read_both_bytes_declared");

    const uint32_t HALF_WORD_ADDRS[] = {SHIFTER_RESOLUTION, PALETTE_0_HI};
    const uint8_t  HALF_WORD_VALUES[] = {RESOLUTION_MONO, PALETTE_HI_BYTE};
    declare(HALF_WORD_ADDRS, HALF_WORD_VALUES, 2);
    run_and_report("word_read_half_declared");

    /* ...and a LONG read over four declared bytes, which BOTH sides spell: the oracle decodes
     * whatever width the ROM really executes, and `io_read32` is what a reconstruction of such an
     * instruction calls. The candidate's half of this case is `cand_long_read` below, and the two
     * must produce the same single width-4 entry or a faithful port of a `move.l` would red. */
    declare(LONG_ADDRS, LONG_VALUES, LONG_N);
    pc = emit_read(PROBE_ENTRY, MOVE_L_ABSL_TO_D1, PALETTE_0_HI);
    plant_rts(pc);
    run_and_report("long_read_all_four_declared");

    /* --- the run WRITES a declared byte and then reads it back: the declaration is stale.
     * Declared, deliberately: the point is that a case CAN declare this byte and still be wrong,
     * and that no bigger declaration fixes it. --- */
    declare(ALL_ADDRS, ALL_VALUES, ALL_N);
    pc = emit_write_byte(PROBE_ENTRY, OTHER_BYTE, SHIFTER_RESOLUTION);
    pc = emit_read(pc, MOVE_B_ABSL_TO_D1, SHIFTER_RESOLUTION);
    plant_rts(pc);
    run_and_report("write_then_read");
    /* ...while a write NOTHING reads back is the ordinary invisible hardware write it always was. */
    pc = emit_write_byte(PROBE_ENTRY, OTHER_BYTE, SHIFTER_RESOLUTION);
    plant_rts(pc);
    run_and_report("write_only");
    /* ...and the staleness note is PER RUN: the very next run of the same read is clean, which is
     * what stops one case's store refusing the next case. */
    pc = emit_read(PROBE_ENTRY, MOVE_B_ABSL_TO_D1, SHIFTER_RESOLUTION);
    plant_rts(pc);
    run_and_report("after_the_write_the_next_run_is_clean");

    /* --- THE WRITE-THROUGH ARM. A declaration marked OS_IO_WRITE_THROUGH says the register LATCHES
     * what the run stores and reads it back unchanged, so the store REPLACES what a later read is
     * served instead of making the declaration stale. The three rows below are the whole arm: the
     * store read back, a marked byte the run never stores (which is an ordinary declaration), and
     * the per-run reset — the next run is served the case's declaration again, or one case's store
     * would reach the next. --- */
    declare_with_writeback(ALL_ADDRS, ALL_VALUES, ALL_WRITE_THROUGH, ALL_N);
    pc = emit_write_byte(PROBE_ENTRY, OTHER_BYTE, SHIFTER_RESOLUTION);
    pc = emit_read(pc, MOVE_B_ABSL_TO_D1, SHIFTER_RESOLUTION);
    plant_rts(pc);
    run_and_report("write_through_read_back");

    pc = emit_read(PROBE_ENTRY, MOVE_B_ABSL_TO_D1, SHIFTER_RESOLUTION);
    plant_rts(pc);
    run_and_report("write_through_never_stored_reads_the_declaration");

    /* ...and the STORE-AND-VERIFY loop the arm exists for, which is the MFP timer programmer's own
     * shape (`projects/tos102us`, `$fc260e`): store the byte, read it back, go round again until
     * the chip agrees. Undeclared it never terminates and declared as a constant it never
     * terminates either — the compare can only come true because the register latched. */
    pc = emit_write_byte(PROBE_ENTRY, OTHER_BYTE, SHIFTER_RESOLUTION);
    pc = emit_compare_byte(pc, OTHER_BYTE, SHIFTER_RESOLUTION);
    pc = emit_bne_back_to(pc, PROBE_ENTRY);
    plant_rts(pc);
    run_and_report("write_through_store_and_verify_loop");

    /* ...and a WIDE store straddling a MARKED byte and an unmarked one: each covered byte gets its
     * own answer, so the word read after it is half the byte the run wrote and half the byte the
     * case declared — and the unmarked half is STALE, which is the refusal this arm does not
     * remove. A store that latched the whole access would serve both halves the written word. */
    declare_with_writeback(STRADDLE_ADDRS, STRADDLE_VALUES, STRADDLE_WRITE_THROUGH, STRADDLE_N);
    pc = emit_write_word(PROBE_ENTRY, (uint16_t)(OTHER_BYTE << 8 | OTHER_BYTE), PALETTE_0_HI);
    pc = emit_read(pc, MOVE_W_ABSL_TO_D1, PALETTE_0_HI);
    plant_rts(pc);
    run_and_report("a_wide_store_straddles_a_marked_byte_and_an_unmarked_one");

    /* --- PRECEDENCE. A Phase-7 NAMED SLOT offered to this model is NOT installed, and a read of it
     * still reaches Phase 7 — so no byte is ever served by two models with only one model's rules
     * enforced. (Through the Python door a case may write one here and `emu.seed_split` routes it
     * to Phase 7's installer; what this measures is the C rule underneath, which must refuse it
     * whatever reaches the ABI.) Every exclusion case below offers its rejected address ALONGSIDE
     * ordinary ones, so each measures "installed all but this one" rather than "installed none of
     * one" — which a rule that rejected everything would also produce. --- */
    const uint32_t WITH_NAMED_SLOT[] = {SHIFTER_RESOLUTION, PALETTE_0_HI, PALETTE_0_LO,
                                        VIDEO_BASE_HI, OS_HW_MFP_GPIP};
    const uint8_t  WITH_NAMED_SLOT_VALUES[] = {RESOLUTION_MONO, PALETTE_HI_BYTE, PALETTE_LO_BYTE,
                                               VIDEO_BASE_BYTE, OTHER_BYTE};
    declare(WITH_NAMED_SLOT, WITH_NAMED_SLOT_VALUES, 5);
    pc = emit_read(PROBE_ENTRY, MOVE_B_ABSL_TO_D1, OS_HW_MFP_GPIP);
    plant_rts(pc);
    run_and_report("named_slot_is_not_shadowed");

    /* ...and the mark buys no admission: the same slot offered WITH a write-through claim is still
     * not installed, so a case cannot reach past os_io_seedable by marking an address. (Through the
     * Python door such a claim is a ValueError in `emu.seed_split`, which is where the routing
     * decision is; this is the C rule underneath.) */
    const uint8_t WITH_NAMED_SLOT_WRITEBACK[] = {OS_IO_DECLARED_CONSTANT, OS_IO_DECLARED_CONSTANT,
                                                 OS_IO_DECLARED_CONSTANT, OS_IO_DECLARED_CONSTANT,
                                                 OS_IO_WRITE_THROUGH};
    declare_with_writeback(WITH_NAMED_SLOT, WITH_NAMED_SLOT_VALUES, WITH_NAMED_SLOT_WRITEBACK, 5);
    pc = emit_write_byte(PROBE_ENTRY, OTHER_BYTE, OS_HW_MFP_GPIP);
    pc = emit_read(pc, MOVE_B_ABSL_TO_D1, OS_HW_MFP_GPIP);
    plant_rts(pc);
    run_and_report("a_named_slot_marked_write_through_is_still_not_installed");

    /* ...and the same for the YM2149's block, which Phase 6 owns along with two refusals of its own
     * that a byte served from here would reach none of. Only the INSTALL is measured: a read of the
     * chip's ports goes through psg_read_back, whose own state is another model's subject. */
    const uint32_t WITH_PSG_PORT[] = {SHIFTER_RESOLUTION, OS_PSG_PORT_DATA};
    const uint8_t  WITH_PSG_PORT_VALUES[] = {RESOLUTION_MONO, OTHER_BYTE};
    declare(WITH_PSG_PORT, WITH_PSG_PORT_VALUES, 2);
    plant_rts(PROBE_ENTRY);
    run_and_report("psg_port_is_not_declarable");

    /* ...and an address BELOW the page, which is ordinary off-image memory and no model's. */
    const uint32_t WITH_LOW_ADDR[] = {SHIFTER_RESOLUTION, PROBE_SENTINEL};
    const uint8_t  WITH_LOW_ADDR_VALUES[] = {RESOLUTION_MONO, OTHER_BYTE};
    declare(WITH_LOW_ADDR, WITH_LOW_ADDR_VALUES, 2);
    run_and_report("an_address_below_the_page_is_not_declarable");

    /* ...and an UNTRANSLATED spelling of a real register, which the bus folds before it decodes:
     * every read reaches os.h's rule as `$ff8260`, so a row keyed on `$ffff8260` would serve nothing
     * while the case believed the byte declared. emu.py refuses such a key by name; this is the C
     * shore's own rule, which a caller that never goes through emu.py reaches instead. */
    const uint32_t WITH_UNTRANSLATED[] = {SHIFTER_RESOLUTION, UNTRANSLATED_IO_ADDR};
    const uint8_t  WITH_UNTRANSLATED_VALUES[] = {RESOLUTION_MONO, OTHER_BYTE};
    declare(WITH_UNTRANSLATED, WITH_UNTRANSLATED_VALUES, 2);
    run_and_report("an_untranslated_address_is_not_declarable");

    /* ...and a DUPLICATE, which would otherwise make the map's size disagree with the case's dict
     * — the shape a Python caller cannot produce (a dict has one value per key) and the C ABI can. */
    const uint32_t WITH_DUPLICATE[] = {SHIFTER_RESOLUTION, SHIFTER_RESOLUTION};
    const uint8_t  WITH_DUPLICATE_VALUES[] = {RESOLUTION_MONO, OTHER_BYTE};
    declare(WITH_DUPLICATE, WITH_DUPLICATE_VALUES, 2);
    pc = emit_read(PROBE_ENTRY, MOVE_B_ABSL_TO_D1, SHIFTER_RESOLUTION);
    plant_rts(pc);
    run_and_report("a_duplicate_declaration_is_installed_once");

    /* --- the CAP: one entry past OS_IO_SEED_MAX is dropped, not wrapped over the array. --- */
    uint32_t over_addrs[OS_IO_SEED_MAX + 1];
    uint8_t over_values[OS_IO_SEED_MAX + 1];
    for (uint32_t i = 0; i < OS_IO_SEED_MAX + 1; i++) {
        over_addrs[i] = CAP_PROBE_BASE + i;
        over_values[i] = (uint8_t)i;
    }
    declare(over_addrs, over_values, OS_IO_SEED_MAX + 1);
    plant_rts(PROBE_ENTRY);
    run_and_report("one_past_the_cap_is_dropped");

    /* --- the declaration is per-RUN state, and the bench shares it (both go through
     * enter_from_reset), so a bench run starts from the case's map with an empty ledger. --- */
    declare(ALL_ADDRS, ALL_VALUES, ALL_N);
    bench_and_report("bench_starts_from_the_declaration");

    /* --- the candidate side, seeded and run exactly as harness.differential does it --- */
    candidate_case("cand_declared_read", ALL_ADDRS, ALL_VALUES, ALL_N,
                   cand_body_reads_the_resolution);
    candidate_case("cand_skips_the_read", ALL_ADDRS, ALL_VALUES, ALL_N, cand_body_skips_the_read);
    candidate_case("cand_undeclared_read", ALL_ADDRS, ALL_VALUES, ALL_N,
                   cand_body_undeclared_read);
    candidate_case("cand_palette_word", ALL_ADDRS, ALL_VALUES, ALL_N,
                   cand_body_reads_the_palette_word);
    candidate_case("cand_palette_as_two_bytes", ALL_ADDRS, ALL_VALUES, ALL_N,
                   cand_body_reads_the_palette_as_two_bytes);
    /* ...the wrong-address mutant, against a declaration that gives BOTH addresses the same byte —
     * so the value it returns, the map it ran against and its (empty) image effect are a correct
     * run's exactly, and only the ledger's address tells them apart. */
    const uint32_t TWINNED_ADDRS[] = {SHIFTER_RESOLUTION, VIDEO_BASE_HI};
    const uint8_t  TWINNED_VALUES[] = {RESOLUTION_MONO, RESOLUTION_MONO};
    candidate_case("cand_twinned_right_address", TWINNED_ADDRS, TWINNED_VALUES, 2,
                   cand_body_reads_the_resolution);
    candidate_case("cand_twinned_wrong_address", TWINNED_ADDRS, TWINNED_VALUES, 2,
                   cand_body_reads_the_wrong_address);
    /* ...the LONG read, which is the candidate's half of `long_read_all_four_declared` above: one
     * entry of width 4, and the mutant that spells it as two word reads instead. */
    candidate_case("cand_long_read", LONG_ADDRS, LONG_VALUES, LONG_N, cand_body_reads_the_long);
    candidate_case("cand_long_read_as_two_words", LONG_ADDRS, LONG_VALUES, LONG_N,
                   cand_body_reads_the_long_as_two_words);
    /* ...a HALF-declared word, which must refuse whole rather than serve the byte it does have. */
    candidate_case("cand_word_half_declared", HALF_WORD_ADDRS, HALF_WORD_VALUES, 2,
                   cand_body_reads_the_palette_word);
    /* ...the reset really clears: a case declaring nothing must not see the previous one's map. */
    candidate_case("cand_declaration_does_not_leak", ALL_ADDRS, ALL_VALUES, 0,
                   cand_body_reads_the_resolution);
    /* ...and a declaration os.h's rule REJECTED is a refusal on this side too, so a case that
     * bypassed emu's encoder cannot run against a map quietly smaller than the one it wrote. */
    candidate_case("cand_rejected_declaration", WITH_NAMED_SLOT, WITH_NAMED_SLOT_VALUES, 5,
                   cand_body_reads_the_resolution);

    /* ...and the WRITE-THROUGH arm on this shore, which must serve exactly what the oracle's rows
     * above serve or a faithful reconstruction of a store-and-verify loop would red. The three
     * mutants are the ways a port of such a loop goes wrong while touching no image byte: it reads
     * before it stores (so it is served the ENTRY byte, which is what the model without this arm
     * would have given it), or it stores the wrong byte (which the register then latches). */
    candidate_case_with_writeback("cand_write_through_read_back", ALL_ADDRS, ALL_VALUES,
                                  ALL_WRITE_THROUGH, ALL_N, cand_body_stores_then_reads_back);
    candidate_case_with_writeback("cand_write_through_never_stored", ALL_ADDRS, ALL_VALUES,
                                  ALL_WRITE_THROUGH, ALL_N, cand_body_reads_without_storing);
    candidate_case_with_writeback("cand_write_through_read_before_store", ALL_ADDRS, ALL_VALUES,
                                  ALL_WRITE_THROUGH, ALL_N, cand_body_reads_back_before_storing);
    candidate_case_with_writeback("cand_write_through_stores_another_value", ALL_ADDRS, ALL_VALUES,
                                  ALL_WRITE_THROUGH, ALL_N, cand_body_stores_a_different_value);
    /* ...and the same store to an UNMARKED declaration, which keeps today's rule verbatim: the read
     * is served the byte the case declared, identically on both shores, and the refusal is the
     * harness's on the ORACLE's staleness tally rather than anything either core can see. */
    candidate_case("cand_unmarked_write_then_read", ALL_ADDRS, ALL_VALUES, ALL_N,
                   cand_body_stores_then_reads_back);
    /* ...and the WIDE store that straddles the two rules, whose word read is half what the run
     * wrote and half what the case declared. */
    candidate_case_with_writeback("cand_wide_store_straddle", STRADDLE_ADDRS, STRADDLE_VALUES,
                                  STRADDLE_WRITE_THROUGH, STRADDLE_N,
                                  cand_body_wide_store_then_word_read);

    free(g_image);
    return 0;
}
