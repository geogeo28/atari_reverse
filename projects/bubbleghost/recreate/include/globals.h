/* Bubble Ghost's RUN-TIME memory model: the one place a core or a test names the boundaries the
 * Alcyon/DRI C small model puts the program's own sections at.
 *
 * Every global in this program is reached as `n(a4)` with a4 fixed at the BSS/DATA boundary, so a
 * reconstruction's addresses are `A4_BASE + n` (signed n: negative is BSS, positive is DATA). The
 * numbers below are the ONLY spelling of that model in this project — a subsystem header names its
 * own globals as absolute addresses and includes this to say where the section boundaries are.
 *
 * PROVENANCE. Every value is read off the two .PRG headers rather than believed:
 * `../bin/GHOST_PLAIN.PRG` (the decrypted FILE layout: tlen 0xe8ca, dlen 0x2f4, blen 0x6650) and
 * `../bin/GHOST_RT.PRG` (the same program in the RUN-TIME layout `tools/prg_relayout.py` builds:
 * tlen' = tlen + blen = 0x14f1a, dlen' = 0x2f4, blen' = 0). `test/test_image_model.py` re-derives
 * each of them from those headers and fails by name on a drift, so this header cannot go stale
 * against the binaries. The crt0 that establishes the model at run time is `crt0_start` @ 0x10036
 * (../notes/anchors.md, "The compiler's memory model"), and that test runs it.
 */
#ifndef BG_GLOBALS_H
#define BG_GLOBALS_H

#define BG_LOAD_BASE    0x10000u  /* project.toml's load_base; ../names.txt addresses assume it */
#define BG_TEXT_BYTES   0xe8cau   /* GHOST_PLAIN.PRG's tlen: code 0x10036.. plus 30 KB of graphics */
#define BG_BSS_BYTES    0x6650u   /* ...its blen, zeroed by the crt0 and then written by
                                   * init_globals @ 0x16d8e one `move` at a time */
#define BG_DATA_BYTES   0x2f4u    /* ...its dlen: the program's strings, and nothing else */

#define BG_BSS_BASE     0x1e8cau  /* = BG_LOAD_BASE + BG_TEXT_BYTES. At run time the BSS sits HERE,
                                   * where the file layout has its DATA — that is the whole of what
                                   * the crt0's segment move does */
#define A4_BASE         0x24f1au  /* = BG_BSS_BASE + BG_BSS_BYTES, the BSS/DATA boundary and the
                                   * value of a4 in every function of the program. `run.sh` pins it
                                   * as a tracked register value so Ghidra resolves `n(a4)` to
                                   * `A4_BASE + n`; every differential case passes it in `regs` */
#define BG_PROGRAM_END  0x2520eu  /* = A4_BASE + BG_DATA_BYTES, one past the program's last byte.
                                   * Equals loader.PROGRAM_END for BOTH .PRG layouts */
#define BG_BASEPAGE_BYTES 0x100u  /* TOS puts the 256-byte basepage immediately below p_tbase, so
                                   * the basepage of a program loaded at BG_LOAD_BASE is at
                                   * BG_LOAD_BASE - this. Not in any header: it is the GEMDOS
                                   * loader's own convention, and it is what makes the crt0's stack
                                   * arithmetic below land where it does */
#define BG_CRT0_STACK_SLACK 0x2100u /* the crt0 Mshrinks to text+data+bss + this (@ 0x10048), so
                                     * this is the game's whole stack plus its heap headroom */
#define BG_STACK_TOP    0x2720eu  /* where the crt0 leaves a7 (@ 0x10058): basepage + text + data +
                                   * bss + BG_CRT0_STACK_SLACK, i.e. BG_PROGRAM_END
                                   * - BG_BASEPAGE_BYTES + BG_CRT0_STACK_SLACK, rounded down to a
                                   * word. Recorded because it is the game's OWN stack; the
                                   * differential's cases run on the kit's (emu.STACK_TOP) instead */

#endif /* BG_GLOBALS_H */
