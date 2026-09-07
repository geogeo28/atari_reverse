/* init.h — Bubble Ghost's boot chain: the crt0, `init_globals`, `main` and `game_top_loop`.
 *
 * WHAT MAKES THIS SUBSYSTEM DIFFERENT FROM EVERY OTHER ONE HERE: nothing in it returns. The crt0
 * ends by calling `main`, `main` either enters `game_top_loop` — a `do { … } while (true)` — or
 * hangs on a two-instruction spin, and `game_top_loop` never leaves. So every routine below is
 * ported as SLICES entered at their own PC and diffed at a checkpoint (docs/agent-playbook.md §5),
 * and ../STATUS.md's `## Verified — init` section opens each row with the `[start, end)` its
 * differential actually runs.
 *
 * THE ONE ROUTINE THAT IS NOT A SLICE is `init_globals` @ 0x16d8e, which runs to `rts` — and it is
 * odd in a different way: it is 7,869 straight-line stores with no control flow at all, the whole
 * of this program's non-zero BSS initialisers written one `move` at a time. `include/
 * init_globals_stream.h` is that instruction stream AS DATA, derived from the disassembly by a
 * generator rather than transcribed by hand, and `init_globals` below is the ten-case interpreter
 * over it. Deriving it from the ASM and not from the image matters: `test/conftest.py`'s post-init
 * fixture IS this routine's output, so a reconstruction read off the fixture would be a tautology.
 *
 * THIS SUBSYSTEM OWNS almost no state of its own. Everything the boot chain writes belongs to the
 * subsystem that reads it, and the headers of those subsystems are included to reach them.
 */
#ifndef BG_INIT_H
#define BG_INIT_H

#include <stdint.h>

#include "clib.h"    /* CallerAddressRegisters, and the printf engine `main`'s error arm reaches */

/* ================================================================================================
 * crt0_start @ 0x10036 — the Alcyon runtime's startup
 *
 * `[0x10036, 0x100a6)` is the whole of what it does to memory: Mshrink the program's own block down
 * to what it needs, MOVE the DATA segment up above the BSS (backwards, because the spans overlap),
 * clear the BSS, point A4 at the boundary and file the basepage pointer just below it. The tail —
 * `jsr 48(a5)` into `init_globals`, `crt0_setup_args`, `main` — is calls this reconstruction makes
 * from its own composition rather than from a transcribed instruction.
 * ============================================================================================= */

/* The basepage's own fields, all longwords, read off the crt0's own displacements. THE WHOLE RECORD
 * IS NAMED even though the slice's C reads only four of them: `BASEPAGE_TBASE` is the A5 the slice
 * leaves behind (a register, so the battery compares it rather than the core producing it),
 * `BASEPAGE_TLEN` is read by the unmodeled Mshrink, and `BASEPAGE_TAIL` by the read-verified tail —
 * and a half-named record is how the next reader mis-reads a displacement. */
#define BASEPAGE_TBASE   8u    /* `movea.l 8(a5),a5` @ 0x100a2 — the TEXT segment, which is also
                                * `init_globals`' A5 */
#define BASEPAGE_TLEN    12u   /* `move.l 12(a5),d0` @ 0x1003c */
#define BASEPAGE_DBASE   16u   /* `movea.l 16(a5),a0` @ 0x10086 — GEMDOS's own field order, so this
                                * is where DATA sits in the FILE layout and therefore where the
                                * cleared BSS ends up once DATA has moved off it */
#define BASEPAGE_DLEN    20u   /* `add.l 20(a5),d0` @ 0x10040 */
#define BASEPAGE_BBASE   24u   /* `movea.l 24(a5),a0` @ 0x1006c — where the BSS starts in the FILE
                                * layout, which is one past the last byte of DATA */
#define BASEPAGE_BLEN    28u   /* `add.l 28(a5),d0` @ 0x10044 */
#define BASEPAGE_TAIL   128u   /* `pea 128(a0)` @ 0x100ae: the command tail, which the argv hook
                                * takes and ignores */

/* `add.l #$2100,d0` @ 0x10048 — what the Mshrink leaves above the program for the machine stack —
 * is `BG_CRT0_STACK_SLACK` in `include/globals.h`, which owns the memory model, and is NOT restated
 * here. No C reads it either way: the Mshrink is unmodeled, so only the arithmetic's SHAPE survives
 * in `crt0_relocate_and_clear`'s comment and only the battery derives the stack top from it. */
#define CRT0_BASEPAGE_SLOT (-4)    /* `move.l a5,-4(a4)` @ 0x1009e — the one byte of the startup's
                                    * memory that `init_globals` alone does not produce
                                    * (test_image_model.py's crt0 pin names it) */

/* ================================================================================================
 * main @ 0x100dc — the resolution gate
 *
 * Three slices, and the middle one is UNREACHABLE under the model: XBIOS `Getrez` always answers
 * low resolution, so nothing a case can stage takes the error arm. It is entered directly instead,
 * which runs it without pretending the gate chose it.
 * ============================================================================================= */

/* What `main` TESTS Getrez's answer against (`cmp.w #$0,d0 / beq` @ 0x100ea) is
 * `XBIOS_GETREZ_LOW_RES` in `include/frontend.h`, which owns the XBIOS binding — not restated. */
#define A_rez_message    0x24f1au  /* `pea 0(a4)` @ 0x100f4 — the format string is the FIRST byte of
                                    * the DATA segment, which is where A4 points */
#define RET_MAIN_GETREZ  0x100e8u  /* where `xbios_trap` returns to for the one call `main` makes */
#define MODEL_GETREZ_ANSWER 0      /* what the KIT's shim leaves in D0 for XBIOS Getrez. It is the
                                    * model's answer and not the program's, which is why it is a
                                    * separate name from the value the program compares against —
                                    * the two being equal is what makes the error arm unreachable,
                                    * and is the residual ../STATUS.md records */

/* ================================================================================================
 * Cores
 * ============================================================================================= */

/* `init_globals` @ 0x16d8e. `text_base` is the basepage's `p_tbase`, which the crt0 leaves in A5
 * and the routine's last paragraph builds seven pointers from (`lea n(a5),a0`) — a dependency
 * nothing in the routine's shape suggests, and which `test_image_model.py`'s crt0 comparison is
 * what found. */
void init_globals(uint8_t *image, uint32_t text_base);

/* The crt0's memory work, `[0x10036, 0x100a6)`. `basepage` is what the loader left at `4(a7)`,
 * which is machine stack the differential drops — so it is an argument, and the case hands the same
 * value to both sides. ANSWERS the GLOBALS BASE the startup establishes (the value that becomes A4,
 * and `test/abi.py`'s `A4_BASE`), which is the other half of what the slice produces and which no
 * image byte carries. */
uint32_t crt0_relocate_and_clear(uint8_t *image, uint32_t basepage);

/* `main`'s three slices. The first ANSWERS whether the machine is in low resolution — the branch it
 * makes, which is not otherwise visible; the reconstruction's caller is what acts on it, exactly as
 * `frame_poll_input`'s ^P answer works. */
int16_t main_check_resolution(uint8_t *image, CallerAddressRegisters saved);
void    main_wrong_resolution(uint8_t *image, uint32_t argument_slot, PrintfCallerState caller,
                              CallerAddressRegisters *live);
void    main_start_game(uint8_t *image, uint32_t frame, CallerAddressRegisters saved);

#endif /* BG_INIT_H */
