/* stack_diet.h — what a routine ON A STACK THE ROM SIZED is compiled with so that its frame costs what the ROM's does.
 *
 * The screen manager runs ctlmgr and everything under it on the 1,196 bytes of its own UDA (`test/aes_stack.py`), and
 * the first accessory's AES calls run the opcode switch and their arm on PD2's 1,396 (the same file, THE TRAP PATH):
 * stacks Alcyon's frames fit and GCC's, at -O2, do not. Most of the difference is not the C: it is what -O2 spends
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
 *
 * NOT MARKS, AND NOT IN THIS REGISTER — THE DESK'S PD0 SPLIT (band 6 slice D, W6-R4; PD0 saved on the flipped build by
 * `tools/flipped_depths.py`, the ledger's slice D entry): `noinline` on the_sliders_set (win_bldview leaves to it by a
 * jump: −64 folder close), zoom_onto_the_middle (−68), get_rect_called (−32 folder close, −16 Print),
 * the_rectangles_read (−12 Print), the_command_run (−16 Print), the_window_s_path_named + the_window_redrawn (−24 File
 * > Open), `always_inline` on act_redrawn_inside (−20 Print); each held as a routine of the shipped ELF, or as none, by
 * `test/test_aes_desk_ours.py`. BAND 6 W3a's DIET (the user's ruling B1: opn_appl's Cancel, hndl_msg's WM_REDRAW down
 * to an icon's label, 1,618 -> 1,534): `noinline` on allchg_walked, act_allchg's walk (−52), and desk_clear's local
 * cut to its work area's end (−12) — beside two MARKS of the register, do_wredraw's (−12) and desk_objc_draw's (−8).
 * BAND 6 W3a's STAGE 1 (the same path, under inf_show: hndl_msg's redraws after a dialog, opn_appl's Cancel 1,580 ->
 * 1,524): `noinline` on dialog_run and messages_asked (inf_show's dialog and its message question, no frame of theirs
 * under hndl_msg), and on opn_appl's three parts — its fields set, its dialog's run (LEFT TO BY A JUMP: opn_appl's frame
 * and the fields' call's deferred arguments popped first) and its fields read back; NO MARK (a mark's reading follows
 * its function into inf_show, whose Line-F call of hndl_msg it cannot count).
 * BAND 6 W3a's STAGE 2 (do_open's frame the ROM's 146 bytes of locals, over a drive's window — File > Open, 1,536 ->
 * 1,534): `noinline` on what do_open's window, folder and trash arms keep (the_window_s_spec_parsed, folder_joined,
 * the_trash_refused) and on do_aopen's two dead boxes (the_boxes_read, under opn_appl's dialog); NO MARK (the same
 * reading's reason: do_open's callees reach inf_show).
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

/* THE BUILDS WHOSE FRAMES STAND ON A STACK THE ROM SIZED: GCC's for the target. The host differential's library runs on
 * the host's stack (and clang knows neither attribute's flags): there a mark, and a routine made for its frame alone
 * (`src/aes/gemsuper.c`, A_DEEP_ARM), is nothing. ONE SPELLING, for every such guard. */
#if defined(__GNUC__) && !defined(__clang__) && !defined(RECREATE_HOST_DIFFERENTIAL)
#define STACK_DIET_ON_TARGET 1
#endif

#if defined(STACK_DIET_ON_TARGET) && !defined(STACK_DIET_MARKS_OFF)
#define FRAME_DIET(...) __attribute__((optimize(OPTIMIZE_KEEPS_FREESTANDING_S_LOOPS, __VA_ARGS__)))
#else
#define FRAME_DIET(...)
#endif

#endif /* TOS102US_STACK_DIET_H */
