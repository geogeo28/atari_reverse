/* move16_guard.c — the oracle's 68000 takes the Line-F exception at `$F620..$F627`, as a 68000 does.
 *
 * Musashi's opcode table is ONE table for every CPU type: m68kmake installs each handler wherever its
 * mask matches and lets the CPU columns of m68k_in.c set only the CYCLES (a `.` column is 0 cycles,
 * not "absent"). So an instruction a CPU lacks must refuse itself in its handler — every other Line-F
 * handler does (`if(CPU_TYPE_IS_..._PLUS(CPU_TYPE)) ...; m68ki_exception_1111();`: cpgen, pmmu, 040fpu…)
 * — and MOVE16's does not: upstream's oracle, set to a 68000, EXECUTED `MOVE16 (Ax)+,(Ay)+` there,
 * copying sixteen bytes in no cycles where a 68000 traps through vector 11 (found by tos102us, whose
 * desk calls Show Info and New Folder by the words `$f620` / `$f624`).
 *
 * The guard is that missing handler line, installed over the table at run time rather than edited
 * into m68k_in.c, because oracle/musashi/ is an UNTRACKED clone of upstream HEAD (kit.mk): an edit
 * there would vanish with the next clone, silently. Pinned by test/test_line_f.py. */
#include "m68kcpu.h"
#include "m68kops.h"     /* m68ki_instruction_jump_table */

/* `1111011000100yyy`: MOVE16 (Ax)+,(Ay)+, the one form m68k_in.c's table carries. */
#define MOVE16_FIRST 0xf620
#define MOVE16_COUNT 8

static void (*g_move16)(void);  /* the handler m68kmake installed: the 68040's MOVE16 */

static void move16_or_line_f(void) {
    if (CPU_TYPE_IS_040_PLUS(CPU_TYPE)) {
        g_move16();
        return;
    }
    m68ki_exception_1111();
}

/* Called after every m68k_init(), which builds the table once per process: idempotent. */
void oracle_guard_move16(void) {
    if (m68ki_instruction_jump_table[MOVE16_FIRST] == move16_or_line_f)
        return;
    g_move16 = m68ki_instruction_jump_table[MOVE16_FIRST];
    for (unsigned op = MOVE16_FIRST; op < MOVE16_FIRST + MOVE16_COUNT; op++)
        m68ki_instruction_jump_table[op] = move16_or_line_f;
}
