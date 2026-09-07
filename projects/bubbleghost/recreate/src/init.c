/* init.c — Bubble Ghost's boot chain. What each address means is `include/init.h`.
 *
 * NOTHING HERE RETURNS on the real machine, so every routine but one is a SLICE entered at its own
 * PC and diffed at a checkpoint (`include/init.h`'s header comment says why, and ../STATUS.md's
 * `## Verified — init` section carries the `[start, end)` each row runs).
 */
#include "machine.h"

#include "clib.h"     /* the trap trampoline, the printf engine and `crt0_setup_args` */
#include "common.h"   /* LONG_BYTES */
#include "frontend.h" /* init_gem_and_screens, which is the only thing `main`'s game arm calls */
#include "init.h"
#include "init_globals_stream.h"

/* ================================================================================================
 * init_globals @ 0x16d8e — every non-zero BSS initialiser, one store at a time
 *
 * The interpreter over `include/init_globals_stream.h`. Ten cases, no control flow of its own: the
 * original has none either, which is exactly what makes the stream-as-data reconstruction faithful
 * rather than a summary of it.
 * ============================================================================================= */

void init_globals(uint8_t *image, uint32_t text_base) {
    uint32_t cursor = 0;    /* A1, which the first step always sets before anything reads it */
    unsigned step;

    for (step = 0; step < INIT_GLOBALS_STEPS; step++) {
        const InitGlobalsStep *at = &INIT_GLOBALS_STREAM[step];

        switch ((InitGlobalsOp)at->op) {
        case IG_CURSOR:
            cursor = at->a;
            break;
        case IG_ADVANCE:
            /* `adda.w`, so the step is a SIGNED WORD added to the whole address register. */
            cursor = addr_add(cursor, sign_ext16(at->a));
            break;
        case IG_PUT_B:
            image[cursor] = (uint8_t)at->a;
            cursor = addr_add(cursor, 1);
            break;
        case IG_PUT_W:
            wr16(image + cursor, (uint16_t)at->a);
            cursor = addr_add(cursor, 2);
            break;
        case IG_PUT_L:
            wr32(image + cursor, at->a);
            cursor = addr_add(cursor, LONG_BYTES);
            break;
        case IG_PUT_A5:
            /* The seven pointers into the program's own TEXT that make this routine depend on A5. */
            wr32(image + cursor, addr_add(text_base, at->a));
            cursor = addr_add(cursor, LONG_BYTES);
            break;
        case IG_SET_B:
            image[at->a] = (uint8_t)at->b;
            break;
        case IG_SET_W:
            wr16(image + at->a, (uint16_t)at->b);
            break;
        case IG_SET_L:
            wr32(image + at->a, at->b);
            break;
        case IG_COPY_L:
            wr32(image + at->a, be32(image + at->b));
            break;
        }
    }
}

/* ================================================================================================
 * crt0_start @ 0x10036 — the slice `[0x10036, 0x100a6)`
 *
 * The program is loaded as `[TEXT][DATA][BSS]` and has to run as `[TEXT][BSS][DATA]`, which is the
 * whole of what this does: shrink the block, slide the DATA segment up over the BSS, clear what it
 * left behind, and point A4 at the boundary so that every global becomes `n(a4)`.
 * ============================================================================================= */

static uint32_t basepage_long(const uint8_t *image, uint32_t basepage, unsigned field) {
    return be32(image + addr_add(basepage, field));
}

uint32_t crt0_relocate_and_clear(uint8_t *image, uint32_t basepage) {
    /* The FILE layout, straight out of the basepage: [TEXT][DATA][BSS]. `data_base` is where DATA
     * starts and `bss_base` is one past its last byte. */
    uint32_t data_base = basepage_long(image, basepage, BASEPAGE_DBASE);
    uint32_t data_length = basepage_long(image, basepage, BASEPAGE_DLEN);
    uint32_t bss_base = basepage_long(image, basepage, BASEPAGE_BBASE);
    uint32_t bss_length = basepage_long(image, basepage, BASEPAGE_BLEN);
    uint32_t globals_base;   /* what becomes A4, and every `n(a4)` in the program */
    int32_t data_counter;

    /* GEMDOS Mshrink of the program's block down to text + data + bss + CRT0_STACK_SLACK, with the
     * machine stack put at its top. The model answers 0 and touches nothing — no image state and no
     * ledger entry — so there is nothing here for a reconstruction to reproduce; ../STATUS.md
     * records the residual, and the STACK the call makes room for is the harness's own. */

    /* THE DATA SEGMENT MOVES BACKWARDS, and it has to: source and destination overlap by everything
     * but `bss_length`, so a forward copy would overwrite bytes it had not read yet. The counter is
     * `dlen - 1` tested `<= 0` BEFORE the `dbf`, so a data segment of one byte or none moves
     * nothing at all — a quirk of the original, transcribed rather than smoothed. */
    data_counter = (int32_t)data_length - 1;
    if (data_counter > 0) {
        uint32_t source = bss_base;                            /* one past the last DATA byte */
        uint32_t destination = addr_add(bss_base, bss_length); /* ...and where it is going */

        /* The `ble` is a LONG test and the `dbf` under it a WORD one, which is the pair of
         * instructions and not one idiom: a data segment of 0x10001 bytes passes the test with
         * `d0.w` = 0 and then moves exactly ONE byte. `loop_passes` is that `dbf`, spelt the same
         * way as the BSS clear's below. */
        for (unsigned i = loop_passes(data_length, COUNT_MASK_WORD); i > 0; i--) {
            source = addr_add(source, (uint32_t)-1);
            destination = addr_add(destination, (uint32_t)-1);
            image[destination] = image[source];
        }
    }

    /* ...and the space DATA vacated becomes the BSS, cleared by a `dbf` with no zero test at all —
     * so a zero-length BSS would clear 0x10000 bytes rather than none. */
    {
        uint32_t at = data_base;

        for (unsigned i = loop_passes(bss_length, COUNT_MASK_WORD); i > 0; i--) {
            image[at] = 0;
            at = addr_add(at, 1);
        }
    }

    globals_base = addr_add(data_base, bss_length);
    wr32(image + addr_add(globals_base, sign_ext16((uint32_t)CRT0_BASEPAGE_SLOT)), basepage);
    return globals_base;
}

/* ================================================================================================
 * main @ 0x100dc — the resolution gate
 * ============================================================================================= */

/* Slice 1, `[0x100dc, 0x1010a)` — XBIOS `Getrez`, and the branch on its answer.
 *
 * The trap is modeled as a no-op, so the trampoline's three save slots are the whole of what this
 * writes; the ANSWER is the rest, and it is what the caller acts on. */
int16_t main_check_resolution(uint8_t *image, CallerAddressRegisters saved) {
    trap_save_registers(image, saved, RET_MAIN_GETREZ);
    /* XBIOS `Getrez`. The kit SERVICES it and answers D0 = 0, with no `os_*` entry point of its own
     * (oracle/shim.c's `case 0x04`), so there is nothing here for a reconstruction to call and
     * nothing a case could stage — the answer is a property of the model rather than of the run.
     * ../STATUS.md records the residual: on a machine really in medium or high resolution the two
     * sides would take different arms and the differential could not see it. */
    return MODEL_GETREZ_ANSWER == (int16_t)XBIOS_GETREZ_LOW_RES;
}

/* Slice 2, `[0x100f4, 0x100fe)` — the wrong-resolution arm, which the model cannot reach.
 *
 * `Getrez` always answers low resolution, so no case can make the gate above choose this; it is
 * entered directly instead. What follows the `c_printf` in the original is `move.w #$1,d0 / bne` —
 * a two-instruction SPIN with no exit at all, which is why this slice stops at it and why the
 * reconstruction has nothing after the call. */
void main_wrong_resolution(uint8_t *image, uint32_t argument_slot, PrintfCallerState caller,
                           CallerAddressRegisters *live) {
    /* `pea 0(a4)` — the format string pushed as `c_printf`'s one argument, which the engine then
     * reads back through its own `pea 8(a6)`. A C reconstruction has no machine stack, so the case
     * names the slot and the push is made as an explicit store; it lands in the band the
     * differential drops, so what it changes is only what the callee goes on to read. */
    wr32(image + argument_slot, A_rez_message);
    c_printf(image, argument_slot, caller, live);
}

/* Slice 3, `[0x1010a, 0x1010e)` — the game arm's first call. `game_top_loop` @ 0x101e6 follows it
 * and never returns, which is where this slice stops. */
void main_start_game(uint8_t *image, uint32_t frame, CallerAddressRegisters saved) {
    init_gem_and_screens(image, frame, saved);
}

/* ================================================================================================
 * Glue. Alcyon/DRI C passes arguments on the stack (test/abi.py), so the oracle side of a case
 * pokes them at 4(A7) and the candidate side is handed the same values as C arguments here.
 * ============================================================================================= */

void g_init_globals(uint8_t *image, uint32_t text_base) { init_globals(image, text_base); }

uint32_t g_crt0_relocate_and_clear(uint8_t *image, uint32_t basepage) {
    return crt0_relocate_and_clear(image, basepage);
}

uint32_t g_main_check_resolution(uint8_t *image, uint32_t a1, uint32_t a2) {
    return (uint16_t)main_check_resolution(image, caller_registers(a1, a2));
}

/* The printf engine's two threaded machine-state values, and a register block by POINTER for the
 * reason `include/clib.h` gives: `c_write` leaves A1 where `c_getfdmode` put it. */
void g_main_wrong_resolution(uint8_t *image, uint32_t argument_slot,
                             uint32_t inherited_conversion, uint32_t status_high,
                             uint32_t a1, uint32_t a2) {
    PrintfCallerState caller = { (uint16_t)inherited_conversion, (uint16_t)status_high };
    CallerAddressRegisters live = caller_registers(a1, a2);

    main_wrong_resolution(image, argument_slot, caller, &live);
}

void g_main_start_game(uint8_t *image, uint32_t frame, uint32_t a1, uint32_t a2) {
    main_start_game(image, frame, caller_registers(a1, a2));
}
