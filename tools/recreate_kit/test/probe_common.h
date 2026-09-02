/* probe_common.h — the scaffolding every 68000-driving kit probe needs, in one place.
 *
 * Four probes here plant 68000 code into a scratch image and run it through the oracle:
 * entry_state_probe.c, reported_regs_probe.c, psg_model_probe.c and hw_model_probe.c. They had a
 * copy of this each — the same geometry, the same extern block, the same `plant_word`. Four copies
 * of a buffer size and a register count is four places for one of them to be wrong, and the register
 * count in particular is a hand-kept mirror of `shim.c`'s `OSH_OUT_REGS`: too small and `osh_run`
 * — OR `osh_run_bench`, which reports the whole file too since the callee-saved check was added —
 * writes past the caller's buffer.
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

#endif /* RECREATE_KIT_PROBE_COMMON_H */
