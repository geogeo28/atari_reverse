/* BOOT B4 — the boot's last slice in C: the AUTO runner ($fc0c4a), the process it runs ($fc0cae), and the launch of
 * the shell, [$fc047a, gem_entry).
 *
 *   $fc047a  _cmdload?  both arms: the AUTO runner, then _sysbase := the ROM's header
 *     set    Pexec(0, "COMMAND.PRG", "", "")                                     (the glue's: `launch_entry.S`)
 *     clear  the environment at $840 ("PATH=", "A:\" — the boot drive's letter — ""), Pexec(5, "", "", $840),
 *            its text := exec_os, then Pexec(4, "", that basepage, $840): the shell (gem_entry) — the glue's
 *   $fc0512  jmp $fc0030 if the Pexec ever returns                              (the glue's)
 *
 *   $fc0c4a  THE AUTO RUNNER: its return kept at $980 (the glue's), the search's path at $984/$988; if the boot drive
 *            is mounted, Pexec(5) a basepage whose text is $fc0cae — this build's process entry — and Pexec(4) it
 *            (the glue's). The process never terminates: it returns through $980 itself, on the BIOS's stack.
 *   $fc0cae  THE PROCESS (Super and its stack are the glue's): Mshrink its block to its basepage, then for each
 *            `\AUTO\*.PRG` Fsfirst / Fsnext find, Pexec(0) it — the DTA set again before each Fsnext.
 *
 * WHAT IS THE GLUE'S AND WHY (`launch_entry.S`): every move of the stack pointer the C cannot make — the return kept
 * at $980 and taken from there, Super, the process's stack at its basepage's top — and THE TRAPS WHOSE REGISTER FRAME
 * OUTLIVES THEM. GEMDOS keeps a caller's D0/A3-A6 and the address of its frame in the CALLING process's basepage
 * (+$68..+$7f, `src/gemdos/trap1.S`), and the last trap of each process stays there: the runner's Pexec(4) in the
 * BIOS process's basepage, the launch's Pexec(4) in the AUTO process's (never terminated, it is still p_run). Both
 * are a surface of the pre-init machine, so both traps are made from the glue at the ROM's own stack depth, with the
 * ROM's registers in place. THE REGISTERS THIS FILE MAY NOT TOUCH: D3-D7 and A3-A6 (the Makefile compiles it with
 * them fixed). The BIOS frames exactly those at `savptr` on every disk call GEMDOS makes for a trap, and the ROM's own
 * code leaves them as the process was entered (A4 Super's answer, A5 the basepage: the glue's) — so ours must too.
 * D5 besides: Pexec(0)'s loader takes its Fopen mode from the caller's D5 (`gemdos/pexec_load.h`).
 *
 * THE ROM'S BUGS, KEPT: the environment's letter is made from _bootdev's high byte (`move.b $446,d0`); the runner
 * Pexec(5)'s a basepage without looking at the answer; the launch's Pexec(5) leaves a word on the stack (the glue's).
 */
/* TARGET ONLY: its own rule links it at LAUNCH_TWIN_LAID_AT; nothing of the host build calls it (a `trap #1` per GEMDOS
 * call, no host twin of its Pexec shape), so off target the file is empty — the host's sweeps compile every source. */
#ifndef RECREATE_HOST_DIFFERENTIAL
#include <stdint.h>

#include "machine.h"
#include "addrs.h"
#include "gemdos/gemdos.h"
#include "gemdos/fs.h"
#include "gemdos/process.h"
#include "boot/head.h"
#include "boot/sysvars.h"
#include "boot/launch.h"

_Static_assert(LAUNCH_PEXEC_LOAD_AND_GO == PEXEC_LOAD_AND_GO && LAUNCH_PEXEC_JUST_GO == PEXEC_JUST_GO
               && LAUNCH_PEXEC_CREATE_BASEPAGE == PEXEC_CREATE_BASEPAGE, "the .S's Pexec modes are not gemdos/process.h's");
_Static_assert(AUTO_DTA_NAME == DTA_NAME, "the .S's DTA name offset is not gemdos/fs.h's");

/* Pexec(mode, name, tail, environment) — the one GEMDOS shape here wider than `gemdos/gemdos.h`'s (its host twin's
 * slot is twelve bytes; this file is linked for the target alone, by its own rule). Operands pinned as that header's
 * are: the function word in D0, where the answer comes back, the rest in the registers the trap restores; the mode an
 * immediate (each call's is a constant). */
static inline __attribute__((always_inline)) uint32_t pexec(uint16_t mode, uint32_t name, uint32_t tail,
                                                            uint32_t environment)
{
    register uint32_t result __asm__("d0") = GEMDOS_PEXEC_FN;
    register uint32_t name_at __asm__("d1") = name;
    register uint32_t tail_at __asm__("a0") = tail;
    register uint32_t environment_at __asm__("a1") = environment;

    __asm__ volatile ("move.l %3,-(%%sp)\n\t"
                      "move.l %2,-(%%sp)\n\t"
                      "move.l %1,-(%%sp)\n\t"
                      "move.w %4,-(%%sp)\n\t"
                      "move.w %0,-(%%sp)\n\t"
                      "trap #1\n\t"
                      "lea %c5(%%sp),%%sp"
                      : "+d"(result)
                      : "d"(name_at), "a"(tail_at), "a"(environment_at), "i"(mode), "i"(PEXEC_FRAME_BYTES)
                      : "memory", "cc");
    return result;
}

/* $fc0c4a, past its return kept at $980 — the AUTO runner: the search's path laid; NO_AUTO_PROCESS where the boot
 * drive is not mounted; else a basepage made for the process, its text this build's process entry. The glue then
 * Pexec(4)s that basepage. */
uint32_t boot_auto_runner(uint8_t *image)
{
    uint32_t basepage;

    wr32(image + AUTO_PATH, ROM_AUTO_PATH);
    wr32(image + AUTO_PATTERN, ROM_AUTO_PATTERN);
    if (!(be32(image + SYSVAR_DRVBITS) & (1ul << (be16(image + SYSVAR_BOOTDEV) & BTST_REGISTER_BIT_MASK))))
        return NO_AUTO_PROCESS;
    basepage = pexec(PEXEC_CREATE_BASEPAGE, ROM_EMPTY_STRING, ROM_EMPTY_STRING, ROM_EMPTY_STRING);
    wr32(image + basepage + BASEPAGE_TBASE, (uint32_t)(uintptr_t)boot_auto_process_entry);
    return basepage;
}

/* The program's path for Pexec(0) at AUTO_PROGRAM_NAME: the search path's folder (every byte before its pattern), then
 * the name the search found, through its NUL. The two copies walk their cursors as the ROM's do (the barriers, inside
 * each pass: `machine.h` — a pointer GCC re-derives from the other costs an indexed mode a byte). */
static __attribute__((noinline)) void program_path_laid(uint8_t *image)
{
    const uint8_t *from = image + be32(image + AUTO_PATH);
    const uint8_t *pattern = image + be32(image + AUTO_PATTERN);
    uint8_t *to = image + AUTO_PROGRAM_NAME;

    do {
        CURSOR_BARRIER(from);
        CURSOR_BARRIER(to);
        *to++ = *from++;
    } while (from != pattern);
    from = image + AUTO_DTA + DTA_NAME;
    do {
        CURSOR_BARRIER(from);
        CURSOR_BARRIER(to);
    } while ((*to++ = *from++) != 0);
}

/* $fc0cae, past Super and the stack the glue moves to the basepage's top — THE AUTO PROCESS: its block shrunk to its
 * basepage (a failure ends it), then every `\AUTO\*.PRG` found run in turn. Each answer is tested as a word (`tst.w`). */
void boot_auto_process(uint8_t *image, uint32_t basepage)
{
    if ((int16_t)gemdos_trap_word_word_long_long(image, GEMDOS_MSHRINK_FN, MSHRINK_RESERVED_WORD, basepage,
                                                 AUTO_PROCESS_BYTES) != 0)
        return;
    gemdos_trap_word_long(image, GEMDOS_FSETDTA_FN, AUTO_DTA);
    if ((int16_t)gemdos_trap_word_long_word(image, GEMDOS_FSFIRST_FN, be32(image + AUTO_PATH), AUTO_SEARCH_ATTRIBUTES) != 0)
        return;
    do {
        program_path_laid(image);
        pexec(PEXEC_LOAD_AND_GO, AUTO_PROGRAM_NAME, ROM_EMPTY_STRING, ROM_EMPTY_STRING);
        gemdos_trap_word_long(image, GEMDOS_FSETDTA_FN, AUTO_DTA);
    } while ((int16_t)gemdos_trap_word(image, GEMDOS_FSNEXT_FN) == 0);
}

/* `_sysbase` the ROM's own header again (B2's `$fc0eba` named its RAM copy): both arms, after the AUTO runner — the
 * whole of the `_cmdload` arm's C (its Pexec(0) is the glue's). */
void boot_launch_sysbase(uint8_t *image)
{
    wr32(image + SYSVAR_SYSBASE, ROM_OS_HEADER);
}

/* The environment at BOOT_ENVIRONMENT: the ROM's template copied through its first byte with the top bit set, the
 * drive mark replaced by the boot drive's letter — made from _bootdev's HIGH byte (a ROM bug, kept: 'A' for every
 * drive below 256). The template holds one mark (`test_boot_launch.py`). */
static __attribute__((noinline)) void environment_laid(uint8_t *image)
{
    const uint8_t *from = image + ROM_ENVIRONMENT_TEMPLATE;
    uint8_t *to = image + BOOT_ENVIRONMENT;
    uint8_t *letter = to;
    int8_t byte;

    CURSOR_BARRIER(from);
    CURSOR_BARRIER(to);
    do {
        if (*from == ENVIRONMENT_DRIVE_MARK)
            letter = to;
        byte = (int8_t)*from++;
        *to++ = (uint8_t)byte;
    } while (byte >= 0);
    *letter = (uint8_t)(DRIVE_LETTER_A + image[SYSVAR_BOOTDEV]);
}

/* [$fc04a4, $fc04f8) — the GEM arm up to its Pexec(4): `_sysbase`, the environment, the shell's basepage made, its
 * text exec_os. Answers that basepage, which the glue hands Pexec(4). */
uint32_t boot_launch_gem(uint8_t *image)
{
    uint32_t basepage;

    boot_launch_sysbase(image);
    environment_laid(image);
    basepage = pexec(PEXEC_CREATE_BASEPAGE, ROM_EMPTY_STRING, ROM_EMPTY_STRING, BOOT_ENVIRONMENT);
    wr32(image + basepage + BASEPAGE_TBASE, be32(image + SYSVAR_EXEC_OS));
    return basepage;
}
#endif /* RECREATE_HOST_DIFFERENTIAL */
