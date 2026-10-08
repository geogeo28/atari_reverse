/* c_call_glue.h — the glue an ASSEMBLY entry uses to call one of this recreate's C cores (`void f(uint8_t *image, ...)`)
 * under the m68k SysV ABI: every argument a pushed longword slot, the first at 4(sp), dropped by the caller after the
 * `jsr`. Shared by every `.S` that reaches C (`src/vdi/escape.S`'s console thunks, the AES's Alcyon entries),
 * so the slot arithmetic has one spelling. Assembler-safe: defines only.
 */
#ifndef C_CALL_GLUE_H
#define C_CALL_GLUE_H

/* The pushed image base — 0 on target, the machine's own base — which the caller drops after its `jsr`. Named because
 * it is an ARGUMENT SLOT and not a stack tidy-up. */
#define IMAGE_ARGUMENT_BYTES 4
/* One further argument's slot: a longword the C reads its value out of, a promoted word included. */
#define SLOT_BYTES 4

/* THE ALCYON FRAME everyobj pushes for the routine a tree walk is handed by value (`staged_call.h`'s
 * call_alcyon_object), from its first argument: the tree a longword, then the object, x and y words — what each ALCYON
 * ENTRY (`src/aes/obdraw.S`, `src/aes/wmupdate.S`) repacks into a C call. */
#define ALCYON_FIRST_ARGUMENT 4          /* past the return address */
#define ALCYON_TREE           0
#define ALCYON_OBJECT         4
#define ALCYON_X              6
#define ALCYON_Y              8

/* A thunk named `thunk` into a C body the caller enters with nothing but the image: `void body(uint8_t *image)`.
 * (`;` separates the statements: a macro expands onto one logical line.) */
#define IMAGE_ONLY_THUNK(thunk, body)                                                                                  \
    .type   thunk,@function;                                                                                           \
thunk:                                                                                                                 \
    pea     (0).w;                                                                                                     \
    jsr     body;                                                                                                      \
    addq.l  #IMAGE_ARGUMENT_BYTES,%sp;                                                                                 \
    rts;                                                                                                               \
    .size   thunk,.-thunk

#endif
