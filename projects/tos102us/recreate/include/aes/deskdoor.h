/* aes/deskdoor.h — THE DESK DOOR: how the shell (`src/aes/shell.c`: sh_main, sh_cmd) calls what is still the ROM's, and
 * where PD0's stack stands when it does.
 *
 * FIVE ROUTINES OF BAND 6'S, the desk's range — the four built-ins OURS since band 6 slice F4, deskmain still the
 * ROM's until W3b's flip:
 *
 *   $fe272e deskmain()                  the desktop, until it returns: 0 to end the shell, anything else for a launch
 *   $fed61e show a file (name)          sh_cmd's `$fe`
 *   $fed624 print a file (name)         sh_cmd's `$fd`
 *   $fed912 format a disk (tail, cmd)   sh_cmd's `$fc`
 *   $fedde4 copy a disk (tail, cmd)     sh_cmd's `$fb`
 *
 * ON TARGET each is ONE `jsr` to what the Line-F table's generator binds it to (`aes/lineftable.h`: the ROM's own
 * address while the table leaves it the ROM's, the table's thunk once it is flipped), over the frame the ROM's
 * sh_main / sh_cmd lays for it — a `jsr` to the ROM's address is the one kind of call into the AES's ROM text a build
 * may make (`bench/tier3.py`: ROM_CALLS_OWED_TO_A_LATER_BAND, each held to one site in the function named). OFF
 * TARGET the routine cannot run (it is 68000 code in the image), so the
 * call leaves through `recreate_call_desk_door`, a hook the case binds: keyed by the routine's ROM address, handed the
 * frame's longwords, answering D0.
 *
 * THE ROM-DEPTH RULE (band 5 wave 4, ruling W4-R4). sh_main runs on PD0's stack for the whole session, so its frame —
 * and gem_main's under it — decide WHERE EVERY FRAME OF THE DESK LIES, and dos_exec parks the process's supervisor SP
 * 64 bytes under the SP it is entered with. So at each call out of the shell — the five above and dos_exec — the
 * door STANDS THE STACK POINTER WHERE THE ROM'S STANDS (DESK_DOOR_SP_*, read off the ROM's own frames below), lays
 * the ROM's frame there and puts the pointer back after: the callee's frames, and every address of them the AES
 * parks, are the ROM's whatever a compiler makes of ours. THE PAD is the gap between our own SP and the ROM's, taken
 * at run time — never a number of this file — AND IT IS NEVER NEGATIVE: a build whose frames run DEEPER than the
 * ROM's at a call, or a call made on another stack than PD0's, HALTS where the call would be made (the door's own
 * vet), never served on a shifted stack. What a caller must leave free is the ROM's own argument slot at
 * the SP (Alcyon's scratch longword, which its call sequence stores in) where the shape has one.
 */
#ifndef TOS102US_AES_DESKDOOR_H
#define TOS102US_AES_DESKDOOR_H

#include "addrs.h"
#include "aes/aes.h"

/* ---- PD0's stack as the ROM's own frames leave it, from its top (UDA1: gem_entry's `movea.l a6,sp`, $fd9fbc) ------ */
#define PD0_STACK_TOP         AES_UDA1
#define ROM_RETURN_BYTES      4          /* a `jsr`'s, or a Line-F call's as its callee finds it                */
#define ROM_LINK_BYTES        4          /* the caller's A6, pushed by `link`                                  */
#define ROM_SAVED_REGISTER_BYTES 4       /* each register a `movem.l` saves                                    */
/* An Alcyon routine's frame under its caller's SP: its return address, `link a6,#-locals`, `movem.l` of its saved
 * registers. */
/* gem_main ($fda062 link #-8; $fda066 movem.l d6-d7/a5), entered by gem_entry's `jsr` ($fd9fbe). */
#define GEM_MAIN_ROM_LOCALS   8
#define GEM_MAIN_ROM_SAVED    3
#define GEM_MAIN_ROM_FRAME    (ROM_RETURN_BYTES + ROM_LINK_BYTES + GEM_MAIN_ROM_LOCALS + GEM_MAIN_ROM_SAVED * ROM_SAVED_REGISTER_BYTES)
/* sh_main ($feb0e6 link #-10; $feb0ea movem.l d6-d7/a5), entered by gem_main's Line-F call ($fda398). */
#define SH_MAIN_ROM_LOCALS    10
#define SH_MAIN_ROM_SAVED     3
#define SH_MAIN_ROM_FRAME     (ROM_RETURN_BYTES + ROM_LINK_BYTES + SH_MAIN_ROM_LOCALS + SH_MAIN_ROM_SAVED * ROM_SAVED_REGISTER_BYTES)
/* sh_cmd ($feb2fc link #-2; $feb300 movem.l d7/a5), entered by sh_main's Line-F call ($feb22e). */
#define SH_CMD_ROM_LOCALS     2
#define SH_CMD_ROM_SAVED      2
#define SH_CMD_ROM_FRAME      (ROM_RETURN_BYTES + ROM_LINK_BYTES + SH_CMD_ROM_LOCALS + SH_CMD_ROM_SAVED * ROM_SAVED_REGISTER_BYTES)

/* WHERE THE ROM'S SP STANDS before each call's frame is laid: inside sh_main ($a368: deskmain is entered at $a364,
 * dos_exec at $a35e), and inside sh_cmd ($a356). */
#define DESK_DOOR_SP_IN_SH_MAIN (PD0_STACK_TOP - GEM_MAIN_ROM_FRAME - SH_MAIN_ROM_FRAME)
#define DESK_DOOR_SP_IN_SH_CMD  (DESK_DOOR_SP_IN_SH_MAIN - SH_CMD_ROM_FRAME)
/* What a call's own sequence stores AT the ROM's SP and above — the bytes our frames must leave free there. */
#define DESK_DOOR_NO_SLOT     0          /* deskmain: a bare call, its return address pushed below              */
#define DESK_DOOR_SCRATCH_SLOT 4         /* Alcyon's argument slot: the last argument stored at (sp)           */
/* dos_exec's frame as sh_main pushes it ($feb29c move.l,(sp); $feb2a2 clr.w -(sp); $feb2a4 move.l,-(sp)): the tail in
 * the scratch slot, then the mode and the name below it — and the SP dos_exec is entered with. */
#define DOS_EXEC_PUSHED_BYTES 6
#define DESK_DOOR_SP_AT_DOS_EXEC (DESK_DOOR_SP_IN_SH_MAIN - DOS_EXEC_PUSHED_BYTES - ROM_RETURN_BYTES)

#ifndef __ASSEMBLER__
#include <stdint.h>

#include "machine.h"
#include "staged_call.h"
#include "aes/gemdosif.h"
#include "aes/lineftable.h"

_Static_assert(DESK_DOOR_SP_IN_SH_MAIN == 0xa368, "sh_main's SP at its calls: deskmain is entered at $a364");
_Static_assert(DESK_DOOR_SP_IN_SH_CMD == 0xa356, "sh_cmd's SP at its calls");
_Static_assert(DESK_DOOR_SP_AT_DOS_EXEC == 0xa35e, "dos_exec's SP at its entry");

#ifdef RECREATE_HOST_DIFFERENTIAL
/* The hook: `routine` (its ROM address) called over `image` with the frame's longwords, `first` the lowest — each
 * STAGED_CALL_NO_ARGUMENT where the frame has none; its answer is the routine's D0. Bound by the case
 * (`test/aes_shmain.py`). */
extern uint32_t (*recreate_call_desk_door)(uint8_t *image, uint32_t routine, uint32_t first, uint32_t second);

static inline int16_t desk_door_deskmain(uint8_t *image)
{
    return (int16_t)recreate_call_desk_door(image, AES_ROM_DESKMAIN, STAGED_CALL_NO_ARGUMENT, STAGED_CALL_NO_ARGUMENT);
}

static inline void desk_door_file(uint8_t *image, uint32_t routine, uint32_t name)
{
    (void)recreate_call_desk_door(image, routine, name, STAGED_CALL_NO_ARGUMENT);
}

static inline void desk_door_disk(uint8_t *image, uint32_t routine, uint32_t tail, uint32_t command)
{
    (void)recreate_call_desk_door(image, routine, tail, command);
}

/* dos_exec is OURS (`gemdosif.c`): off target its twin is handed the SP the ROM's is entered with. */
static inline void desk_door_dos_exec(uint8_t *image, uint32_t name, int16_t mode, uint32_t tail)
{
    (void)aes_dos_exec(image, DESK_DOOR_SP_AT_DOS_EXEC, name, mode, tail);
}
#else
/* THE CALL, one shape for all six and ONE `asm`, so that nothing of the compiler's comes between its steps:
 *   - the SP kept in a register the callee keeps (Alcyon's D3-D7/A3-A6; dos_exec's Pexec gives the same back);
 *   - THE VET: our SP on PD0's stack, and at or above the ROM's with the call's own slot left free — else the halt
 *     `recreate_not_reconstructed` is on target (`trap #7`: the trap is the whole report);
 *   - the SP stood at the ROM's, `frame_and_call` — the ROM's own instructions for the frame, and the `jsr` —, the SP
 *     put back.
 * The frame's values ride in A0 / A1 / D1 (`operands`: each read-write, the callee may change it) — registers no
 * caller pays a saved register for — the rest of what the callee may change is `clobbers`, and its D0 is the answer.
 * Macros, as an "i" operand must be a constant where it is spelt (`aes/switch.h`). */
#define DESK_DOOR_CALL(rom_sp, slot_bytes, frame_and_call, operands, ...)                                               \
    __asm__ volatile ("move.l %%sp,%[kept]\n\t"                                                                        \
                      "cmpa.l %[floor],%%sp\n\t"                                                                        \
                      "bcs.s 0f\n\t"                                                                                    \
                      "cmpa.l %[top],%%sp\n\t"                                                                          \
                      "bls.s 1f\n"                                                                                      \
                      "0:\ttrap #7\n"                                                                                   \
                      "1:\tmovea.l %[stood],%%sp\n\t"                                                                   \
                      frame_and_call "\n\t"                                                                             \
                      "movea.l %[kept],%%sp"                                                                            \
                      : "=d"(answer_), [kept] "=&r"(kept_) operands                                                     \
                      : [stood] "i"(rom_sp), [floor] "i"((rom_sp) + (slot_bytes)), [top] "i"(PD0_STACK_TOP)             \
                      : "d2", "a2", "memory", "cc", ##__VA_ARGS__)
/* What every door declares first: D0, the answer, and the SP kept — PINNED to a register of the callee's kept set
 * (left to the compiler it is given a frame slot as well: four bytes of the depth this door exists to hold). */
#define DESK_DOOR_ANSWER                                                                                                \
    register uint32_t answer_ __asm__("d0");                                                                            \
    register uint32_t kept_ __asm__("d3")
/* A ROM routine's address as the `jsr`'s own operand: absolute, so the build's one call of it is a word a listing
 * shows (`bench/tier3.py` reads them). A BUILT-IN's operand (the two shapes below) is what the Line-F table's
 * generator binds it to, `DESK_DOOR_BOUND_<its addrs.h NAME>` (`aes/lineftable.h`: the ROM's routine while the table
 * leaves it the ROM's, the table's own thunk once it is flipped) — the name pasted where the shape's macro is spelt,
 * so it is never expanded to its address first. */
#define DESK_DOOR_TEXT_(address) #address
#define DESK_DOOR_TEXT(address) DESK_DOOR_TEXT_(address)

/* A frame's values, as each shape hands them over: the longword pushed last in A0, the one before it in A1, a word
 * in D1. */
#define DESK_DOOR_LAST        , [last] "+a"(last_)
#define DESK_DOOR_BEFORE_IT   , [before_it] "+a"(before_it_)
#define DESK_DOOR_WORD        , [word] "+d"(word_)

/* The bare call ($feb1dc): deskmain — bound as a built-in is (band 6 W3b's prep, the orchestrator's O2), its shape
 * taking the routine's name as the built-ins' do. */
#define desk_door_bare(image, routine)                                                                                  \
    ({                                                                                                                  \
        DESK_DOOR_ANSWER;                                                                                               \
                                                                                                                        \
        (void)(image);                                                                                                  \
        DESK_DOOR_CALL(DESK_DOOR_SP_IN_SH_MAIN, DESK_DOOR_NO_SLOT,                                                      \
                       "jsr " DESK_DOOR_TEXT(DESK_DOOR_BOUND_##routine), , "d1", "a0", "a1");                           \
        (int16_t)answer_;                                                                                               \
    })
#define desk_door_deskmain(image) desk_door_bare(image, AES_ROM_DESKMAIN)

/* `move.l <name>,(sp)` and the call ($feb320, $feb354): the two file routines. */
#define desk_door_file(image, routine, name)                                                                            \
    do {                                                                                                                \
        DESK_DOOR_ANSWER;                                                                                               \
        register uint32_t last_ __asm__("a0") = (name);                                                                 \
                                                                                                                        \
        (void)(image);                                                                                                  \
        DESK_DOOR_CALL(DESK_DOOR_SP_IN_SH_CMD, DESK_DOOR_SCRATCH_SLOT,                                                  \
                       "move.l %[last],(%%sp)\n\tjsr " DESK_DOOR_TEXT(DESK_DOOR_BOUND_##routine), DESK_DOOR_LAST,       \
                       "d1", "a1");                                                                                     \
    } while (0)

/* `move.l <command>,(sp) / move.l <tail>,-(sp)` and the call ($feb36a, $feb388): the two disk routines. */
#define desk_door_disk(image, routine, tail, command)                                                                   \
    do {                                                                                                                \
        DESK_DOOR_ANSWER;                                                                                               \
        register uint32_t last_ __asm__("a0") = (tail);                                                                 \
        register uint32_t before_it_ __asm__("a1") = (command);                                                         \
                                                                                                                        \
        (void)(image);                                                                                                  \
        DESK_DOOR_CALL(DESK_DOOR_SP_IN_SH_CMD, DESK_DOOR_SCRATCH_SLOT,                                                  \
                       "move.l %[before_it],(%%sp)\n\tmove.l %[last],-(%%sp)\n\tjsr "                                   \
                       DESK_DOOR_TEXT(DESK_DOOR_BOUND_##routine),                                                       \
                       DESK_DOOR_LAST DESK_DOOR_BEFORE_IT, "d1");                                                       \
    } while (0)

/* dos_exec is OURS — the `.S`'s entry (`gemdosif.S`: the ROM's instructions, which read the SP they are entered
 * with), named in the `jsr` itself — over sh_main's frame: `move.l <tail>,(sp) / move.w <mode>,-(sp) /
 * move.l <name>,-(sp)`. */
#define desk_door_dos_exec(image, name, mode, tail)                                                                     \
    do {                                                                                                                \
        DESK_DOOR_ANSWER;                                                                                               \
        register uint32_t last_ __asm__("a0") = (name);                                                                 \
        register uint32_t before_it_ __asm__("a1") = (tail);                                                            \
        register uint32_t word_ __asm__("d1") = (uint16_t)(mode);                                                       \
                                                                                                                        \
        (void)(image);                                                                                                  \
        DESK_DOOR_CALL(DESK_DOOR_SP_IN_SH_MAIN, DESK_DOOR_SCRATCH_SLOT,                                                 \
                       "move.l %[before_it],(%%sp)\n\tmove.w %[word],-(%%sp)\n\tmove.l %[last],-(%%sp)\n\t"           \
                       "jsr aes_rom_dos_exec", DESK_DOOR_LAST DESK_DOOR_BEFORE_IT DESK_DOOR_WORD);                      \
    } while (0)
#endif
#endif /* __ASSEMBLER__ */

#endif /* TOS102US_AES_DESKDOOR_H */
