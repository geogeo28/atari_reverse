/* probe_common.h — the scaffolding every 68000-driving kit probe needs, in one place.
 *
 * Five probes here plant 68000 code into a scratch image and run it through the oracle:
 * entry_state_probe.c, reported_regs_probe.c, psg_model_probe.c, hw_model_probe.c and
 * io_model_probe.c. They had a copy of this each — the same geometry, the same extern block, the
 * same `plant_word`. Five copies of a buffer size and a register count is five places for one of
 * them to be wrong, and the register count in particular is a hand-kept mirror of `shim.c`'s
 * `OSH_OUT_REGS`: too small and `osh_run` — OR `osh_run_bench`, which reports the whole file too
 * since the callee-saved check was added — writes past the caller's buffer.
 *
 * (test/os_refusal_probe.c is deliberately NOT a fifth copy. It calls `include/os.h`'s helpers
 * directly, plants no code, never enters the CPU, and its own `PROBE_*` names denote in-image
 * addresses for a filename and a GEM parameter block — a different set of things with a colliding
 * prefix. There is nothing here for it to share.)
 *
 * WHAT THE EXTERN BLOCK BELOW GUARANTEES, AND WHAT IT DOES NOT. It is a re-declaration of functions
 * defined in ../oracle/shim.c, which ships no header because Python binds it by ctypes. An earlier
 * copy of this comment claimed "a drift is a compile error, since both translation units are linked
 * together" — THAT IS FALSE, and worth stating plainly because it is the reassuring kind of wrong: C
 * links by NAME, so a declaration whose signature has drifted from the definition is undefined
 * behaviour at the call, diagnosed by nothing. What is actually true is narrower and still worth
 * having: there is now ONE declaration, so the four probes cannot disagree with each other or be
 * half-updated, and `probe_build.compile_probe` recompiles `shim.c` from source on every run, so a
 * signature change lands in the same binary and shows up as a probe that misbehaves rather than as a
 * stale artifact that keeps passing. A real guarantee would need shim.c to export a header; that is
 * a larger change than this one and is not pretended to here.
 */
#ifndef RECREATE_KIT_PROBE_COMMON_H
#define RECREATE_KIT_PROBE_COMMON_H

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

/* ---- the oracle's entry points (see the header comment for what this does and does not pin) ---- */
int osh_run(uint8_t *mem, uint32_t size, uint32_t entry,
            const uint32_t *dregs, const uint32_t *aregs,
            uint32_t sp, uint32_t sentinel, uint32_t stop_pc, uint32_t max_insns,
            uint32_t *out_regs);
/* The OTHER door in: no OS traps, one stack argument, used where a probe must show that a per-run
 * reset lives in the shared `enter_from_reset` rather than in `osh_run` alone. */
int osh_run_bench(uint8_t *mem, uint32_t size, uint32_t entry, uint32_t arg0,
                  uint32_t sp, uint32_t sentinel, uint32_t max_insns, uint32_t *out_regs);
/* How many registers `osh_run` and `osh_run_bench` write into `out_regs` — shim.c's OSH_OUT_REGS. */
uint32_t osh_out_regs(void);

/* ---- the scratch image's geometry, identical in every probe that plants code ----
 * 64 KiB: room for the planted routine, the machine stack, and the vector page `osh_run` writes its
 * transient trap vectors into. A probe that needs a region of its own (reported_regs_probe.c's
 * table) puts it between PROBE_ENTRY and PROBE_SENTINEL and names it itself. */
#define PROBE_IMAGE_SIZE 0x10000u
#define PROBE_ENTRY      0x1000u   /* even, clear of the vector page and of shim.c's magic trap PCs */
#define PROBE_SENTINEL   0x2000u   /* the return address osh_run stops at */
#define PROBE_SP         0x8000u   /* the machine stack, well above the routine */

/* PROBE_MAX_INSNS is deliberately NOT here: it is each probe's own claim about its own routines
 * ("this is two instructions; an overrun is a bug"), and a shared value would be the loosest of
 * them, retiring that claim everywhere. */

#define NREGS    8                 /* D0..D7 / A0..A7, as osh_run takes them */
#define OUT_REGS 15                /* both runners report D0..D7 then A0..A6 (shim.c's OSH_OUT_REGS) */

#define OPCODE_RTS 0x4e75u
/* `move.b (xxx).l,Dn` — the byte read three probes plant to get a modeled value into a register the
 * oracle reports. It was #defined identically in each of them; one spelling, for the reason this
 * header exists. */
#define OPCODE_MOVE_B_ABSL_TO_DN(reg) ((uint16_t)(0x1039u | ((reg) << 9)))
#define MOVE_B_ABSL_TO_D1 OPCODE_MOVE_B_ABSL_TO_DN(1)
/* ...the same read WIDENED, which is the shape the seeded-hardware model REFUSES and the declared
 * I/O map serves only when every byte of it was declared — so both models' probes plant these. */
#define MOVE_W_ABSL_TO_D1  0x3239u /* move.w (xxx).l,d1 */
#define MOVE_L_ABSL_TO_D1  0x2239u /* move.l (xxx).l,d1 */
/* ...and the STORE both models need in order to reach their staleness rule: a declaration describes
 * the machine on ENTRY, and a run that overwrites the address has made it describe nothing. */
#define MOVE_B_IMM_TO_ABSL 0x13fcu /* move.b #imm,(xxx).l */
/* ...and the WIDE store, which the declared I/O map's WRITE-THROUGH arm needs: one store can
 * straddle a marked byte and an unmarked one, and each gets its own answer. */
#define MOVE_W_IMM_TO_ABSL 0x33fcu /* move.w #imm,(xxx).l */
#define CMPI_B_IMM_ABSL    0x0c39u /* cmpi.b #imm,(xxx).l — the read half of a verify loop */
#define BNE_SHORT          0x6600u /* bne.s <disp8>, the loop's own branch */

/* The scratch image every helper below writes into. `static` in a header is right here: a probe is
 * one translation unit plus the oracle's, so there is exactly one of these per binary. */
static uint8_t *g_image;

/* Allocate the scratch image, or die loudly — every probe opened with the same three lines. */
static inline uint8_t *probe_alloc_image(void) {
    g_image = calloc(PROBE_IMAGE_SIZE, 1);
    if (!g_image) {
        fprintf(stderr, "probe: could not allocate the %u-byte scratch image\n", PROBE_IMAGE_SIZE);
        exit(1);
    }
    return g_image;
}

/* Refuse to run against a shim that reports a different register count from the one this probe
 * sized its buffers for — `osh_run` would write past them, corrupting the probe's own stack.
 *
 * Every code-planting probe calls this, rather than trusting reported_regs_probe.c to have noticed:
 * that one REPORTS the count for its Python side to assert, which is a different job from a caller
 * protecting its own buffer, and it is only ever run by its own suite.
 */
static inline void probe_require_out_regs(void) {
    if (osh_out_regs() != OUT_REGS) {
        fprintf(stderr, "probe: shim.c reports %u registers per run, this probe is built for %d — "
                        "osh_run would overrun the out_regs buffer\n", osh_out_regs(), OUT_REGS);
        exit(1);
    }
}

/* ---- planting 68000 code, big-endian, into the scratch image ---- */
static inline void plant_word(uint32_t addr, uint16_t opcode) {
    g_image[addr] = (uint8_t)(opcode >> 8);
    g_image[addr + 1] = (uint8_t)opcode;
}

/* Returns the address AFTER the longword, so a caller emitting a stream of instructions can chain;
 * a caller filling a table ignores it. */
static inline uint32_t plant_long(uint32_t addr, uint32_t value) {
    plant_word(addr, (uint16_t)(value >> 16));
    plant_word(addr + 2, (uint16_t)value);
    return addr + 4;
}

static inline void plant_rts(uint32_t addr) { plant_word(addr, OPCODE_RTS); }

/* Each emitter plants ONE instruction at `addr` and returns the address after it, so a caller
 * emitting a stream chains them. Shared by the two seeded-read probes, which plant the identical
 * instructions at the identical addresses and differ only in which model's registers they aim at.
 *
 * `io_addr` is the address the planted instruction names — the untranslated `$ffff8260` form or the
 * folded `$ff8260` one, as the case wants; the oracle's callbacks fold it either way. */
static inline uint32_t emit_read(uint32_t addr, uint16_t opcode, uint32_t io_addr) {
    plant_word(addr, opcode);
    return plant_long(addr + 2, io_addr);
}

static inline uint32_t emit_write_byte(uint32_t addr, uint8_t value, uint32_t io_addr) {
    plant_word(addr, MOVE_B_IMM_TO_ABSL);
    plant_word(addr + 2, value);
    return plant_long(addr + 4, io_addr);
}

static inline uint32_t emit_write_word(uint32_t addr, uint16_t value, uint32_t io_addr) {
    plant_word(addr, MOVE_W_IMM_TO_ABSL);
    plant_word(addr + 2, value);
    return plant_long(addr + 4, io_addr);
}

/* `cmpi.b #imm,(xxx).l` and `bne.s` — the two instructions a STORE-AND-VERIFY loop needs beside the
 * store, which is the shape a chip with a settling time is programmed in (`move.b` the byte,
 * re-read it, go round again until it agrees). `emit_bne_back_to` takes the address to branch to
 * and encodes the SIGNED displacement the 68000 measures from the word after the opcode. */
static inline uint32_t emit_compare_byte(uint32_t addr, uint8_t value, uint32_t io_addr) {
    plant_word(addr, CMPI_B_IMM_ABSL);
    plant_word(addr + 2, value);
    return plant_long(addr + 4, io_addr);
}

static inline uint32_t emit_bne_back_to(uint32_t addr, uint32_t target) {
    int32_t displacement = (int32_t)target - (int32_t)(addr + 2);
    plant_word(addr, (uint16_t)(BNE_SHORT | (uint8_t)(int8_t)displacement));
    return addr + 2;
}

/* ---- driving a planted routine through each of the oracle's two entry points ----
 * `report` is the probe's own reporter, which takes the case name and the value the routine left in
 * D1; `d1_mask` is how wide that value is for THIS probe (a byte for the named set, the whole
 * longword for the declared I/O map, which serves word and long reads too).
 *
 * The image is NOT cleared between runs — only the code is re-planted — because one of the claims
 * both probes make is that the MODEL's own per-run state does not carry over even when the image
 * does. */
static inline void probe_run_and_report(const char *name, uint32_t d1_mask, uint32_t max_insns,
                                        void (*report)(const char *, uint32_t)) {
    uint32_t dregs[NREGS] = {0}, aregs[NREGS] = {0}, out[OUT_REGS] = {0};
    if (!osh_run(g_image, PROBE_IMAGE_SIZE, PROBE_ENTRY, dregs, aregs,
                 PROBE_SP, PROBE_SENTINEL, 0, max_insns, out)) {
        fprintf(stderr, "%s: the probe's routine did not return to the sentinel\n", name);
        exit(1);
    }
    report(name, out[1] & d1_mask);
}

/* The same through `osh_run_bench` — the OTHER entry point, which a perf measurement uses and which
 * installs no OS traps. Its routine is a bare `rts`: what such a case is about is the state the
 * bench STARTS from, since both entry points share `enter_from_reset()` and therefore every model's
 * per-run reinstall. The routine reads nothing, so the read is reported as 0. */
static inline void probe_bench_and_report(const char *name, uint32_t max_insns,
                                          void (*report)(const char *, uint32_t)) {
    uint32_t out[OUT_REGS] = {0};
    plant_rts(PROBE_ENTRY);
    if (!osh_run_bench(g_image, PROBE_IMAGE_SIZE, PROBE_ENTRY, 0,
                       PROBE_SP, PROBE_SENTINEL, max_insns, out)) {
        fprintf(stderr, "%s: the bench's routine did not return to the sentinel\n", name);
        exit(1);
    }
    report(name, 0);
}

#endif /* RECREATE_KIT_PROBE_COMMON_H */
