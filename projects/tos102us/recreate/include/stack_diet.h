/* stack_diet.h — what a routine ON A STACK THE ROM SIZED is compiled with so that its frame costs what the ROM's does.
 *
 * The screen manager runs ctlmgr and everything under it on the 1,196 bytes of its own UDA (`test/aes_stack.py`), a
 * stack Alcyon's frames fit and GCC's, at -O2, do not. Most of the difference is not the C: it is what -O2 spends
 * STACK on to save cycles, in a build whose every address is `image + constant` and whose every argument is a
 * longword slot. `FRAME_DIET("no-<pass>", ...)` turns those passes off FOR ONE FUNCTION — the ones measured to make
 * that function's frame smaller, and no other:
 *
 *   no-defer-pop               -O2 leaves a call's arguments on the stack and pops several calls' at once: up to 28
 *                              dead bytes under the NEXT call, which is where a routine of a deep path stands when
 *                              its callee goes deeper. Alcyon pops after every call.
 *   no-optimize-sibling-calls  a function that ends in a call it can turn into a jump treats ITS OWN argument slots
 *                              as that jump's scratch, so every argument it needs later is copied into its frame
 *                              first (gsx_blt: 20 bytes of copies of what lies 40 bytes above them).
 *   no-move-loop-invariants    every `image + address` a loop uses is computed once and KEPT in a register for the
 *                              loop — a register saved on entry (forker: eleven of them for a loop of five globals).
 *   no-function-cse            ...and so is every callee's address a function calls twice (`src/aes/ctlmgr.c`).
 *   no-caller-saves            a value live across a call is kept in a call-saved register rather than re-read.
 *   no-gcse, no-tree-dominator-opts   common subexpressions carried across blocks, each in a register or a spill.
 *
 * GCC DOCUMENTS `optimize` AS A DEBUGGING AID, "not suitable for production code" (`src/aes/gemsuper.c` says the same
 * of its jump table). What holds it here is the build's own output, read by `test/test_stack_diet.py`: each marked
 * function is compiled twice — as marked, and with the marks off under the same flags on the command line — and the
 * two must be the same instructions, so the attribute changes nothing but its flags for it (it drops no flag the
 * command line spells, and the one implied setting it would reset is spelt inside it: below); and each mark is
 * held to what it buys: the function's frame with it against the frame without. `STACK_DIET_MARKS_OFF` is that
 * guard's switch, no build's. The cycles a mark costs are Tier 3's to hold (the bar, per row).
 */
#ifndef TOS102US_STACK_DIET_H
#define TOS102US_STACK_DIET_H

/* WHAT EVERY `optimize` ATTRIBUTE OF THIS BUILD CARRIES. The attribute keeps every flag the command line SPELLS
 * (-fno-strict-aliasing, -fno-jump-tables, -fomit-frame-pointer, -ffunction-sections: measured), but ONE SETTING THE
 * BUILD HAS IS NOT SPELT: `-ffreestanding` turns loop-pattern recognition off by implication, and the attribute puts
 * it back to -O2's default for its function — a fill, copy or length loop then compiles to `jsr memset` / `memcpy` /
 * `memmove` / `strlen`, which a `-nostdlib` ROM does not have (the frame diet's review, 2026-10-10: 16 functions of
 * this tree would, the moment they were marked; none of the marked ones had such a loop). Spelt inside the
 * attribute it stays off. `src/aes/gemsuper.c`'s jump table carries it too; `test_stack_diet.py` holds both: no
 * function under an `optimize` attribute references a library routine. */
#define OPTIMIZE_KEEPS_FREESTANDING_S_LOOPS "no-tree-loop-distribute-patterns"

#if defined(__GNUC__) && !defined(__clang__) && !defined(RECREATE_HOST_DIFFERENTIAL) && !defined(STACK_DIET_MARKS_OFF)
#define FRAME_DIET(...) __attribute__((optimize(OPTIMIZE_KEEPS_FREESTANDING_S_LOOPS, __VA_ARGS__)))
#else
#define FRAME_DIET(...)
#endif

#endif /* TOS102US_STACK_DIET_H */
