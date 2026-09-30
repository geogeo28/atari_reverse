/* c_call_glue.h — the glue an ASSEMBLY entry uses to call one of this recreate's C cores (`void f(uint8_t *image, ...)`)
 * under the m68k SysV ABI: every argument a pushed longword slot, the first at 4(sp), dropped by the caller after the
 * `jsr`. Shared by every `.S` that reaches C (`src/bios/isr.S`'s handler stubs, `src/vdi/escape.S`'s console thunks),
 * so the slot arithmetic has one spelling. Assembler-safe: defines only.
 */
#ifndef C_CALL_GLUE_H
#define C_CALL_GLUE_H

/* The pushed image base — 0 on target, the machine's own base — which the caller drops after its `jsr`. Named because
 * it is an ARGUMENT SLOT and not a stack tidy-up. */
#define IMAGE_ARGUMENT_BYTES 4
/* One further argument's slot: a longword the C reads its value out of, a promoted word included. */
#define SLOT_BYTES 4

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
