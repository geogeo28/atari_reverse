/* vdi/transcribed.h — THE TRANSCRIBED TABLE: every ROM routine the shipped build takes as the ROM's own
 * instructions (the `.S` files in `src/vdi/`) instead of its C core, and what a C caller needs to reach one.
 *
 * THE RULE IT RECORDS is the user's, for the hand-written 68000: port the routine to C first — Tier 1
 * proves the C against the ROM — and where the C measures over Tier 3's 1.10 bar, SHIP a byte-pinned
 * `.S` transcription. This table is the one place "ships as `.S`" is said, and three things are derived
 * from it rather than restated:
 *
 *   * TIER 3 (`bench/tier3.py`, legend (T), verdict `transcribed`): a routine here may have C rows over
 *     the bar ONLY while every one of its `.S` rows measures at or under it. Nothing is typed per row —
 *     delete a `.S` row, or let one drift over the bar, and the C rows go red.
 *   * THE BUILD CONTRACT (`atari/target.mk`): `TRANSCRIBED_ENTRIES` is what the ROM build links for these
 *     routines and `TRANSCRIBED_C_CORES` the C it must NOT link. `test_vdi_transcribed.py` pins the make
 *     lists against this table, every `.globl` of the `.S` sources against its rows, and the C callers
 *     that still reach a C core here (each needs the glue below once the ROM build links cores).
 *   * THE DECLARATIONS at the end, for that glue.
 *
 * ONE ROW PER `.S` ENTRY, and the naming rule (`addrs.h`, the VDI block) gives the rest: the ROM routine
 * is the entry upper-cased (`linea_rom_hline` -> `LINEA_ROM_HLINE`) and the C core is the entry less its
 * `rom_` (`linea_hline`). The second column is the entry's REGISTER CONTRACT against the GCC m68k ABI:
 * the CALLEE-SAVED registers (D2-D7, A2-A6) it leaves changed. D0/D1/A0/A1 are the ABI's scratch and
 * every entry may change them. A ROM caller never cared — Alcyon keeps less, and the VDI's `trap #2`
 * entry saves D1-A6 round the whole dispatch — but a C caller built by GCC keeps values in exactly these,
 * so a call that does not name them is the d2/a2 corruption class (`docs/on-target-execution.md`). The
 * sets are the ROM's own, measured over every registered `.S` case (`test_vdi_transcribed.py`), where
 * the transcription relation proves the `.S` leaves the same file; a front end that jumps through a
 * drawing vector is charged all of D2-D7/A2-A5, because what runs there is the vector's.
 *
 * The trailing comment is the rest of the contract a glue author needs: the registers an entry reads
 * and answers in (the Line-A ones are `test/vdi_raster.py`'s `declare_primitive`s), or "Alcyon" for a
 * word-argument C call answering in D0.w (`vdi/helpers.h`), or "function" for a VDI function reached
 * with the Line-A pointers set (`vdi/vdi.h`).
 */
#ifndef TOS102US_VDI_TRANSCRIBED_H
#define TOS102US_VDI_TRANSCRIBED_H

#define VDI_TRANSCRIBED(ENTRY)                                                                                \
    ENTRY(vdi_rom_sort_words,         "d2")                                 /* D0.w count, A0 array        */ \
    ENTRY(vdi_rom_smul_div,           "d2")                                 /* Alcyon, three words         */ \
    ENTRY(vdi_rom_get_kbshift,        "")                                   /* -> D0.w, high word kept     */ \
    ENTRY(vdi_rom_gemdos_call,        "d2 a2")                              /* Alcyon; `trap #1` keeps less */ \
    ENTRY(vdi_rom_clc_dda,            "")                                   /* Alcyon, two words           */ \
    ENTRY(vdi_rom_act_siz,            "")                                   /* Alcyon, one word            */ \
    ENTRY(vdi_rom_clamp_mouse,        "")                                   /* D0, D1 -> D0, D1            */ \
    ENTRY(vdi_rom_vr_trnfm,           "d7")                                 /* function 110                */ \
    ENTRY(vdi_rom_vs_color,           "d2 d3 d4")                           /* function 14                 */ \
    ENTRY(vdi_rom_vq_color,           "d2")                                 /* function 26                 */ \
    ENTRY(linea_rom_concat,           "d2")                                 /* D0 x, D1 y -> D0, D1        */ \
    ENTRY(linea_rom_line,             "d2 d3 d4 d5 d6 d7 a2 a3 a4 a5")      /* $a003                       */ \
    ENTRY(linea_rom_line_plane_words, "d2 d3")                              /* D3 planes, A2 buffer        */ \
    ENTRY(linea_rom_hline,            "d2 d3 d4 d5 d6 d7 a2 a3 a4 a5")      /* $a004                       */ \
    ENTRY(linea_rom_hline_patterned,  "d2 d3 d4 d5 d6 d7 a2 a3 a4 a5")      /* D4-D6, A4 Line-A base       */ \
    ENTRY(linea_rom_hline_span,       "d2 d3 d4 d5 d6 d7 a2 a3 a4 a5")      /* D4-D6, A0, D0, A4           */ \
    ENTRY(linea_rom_put_pixel,        "d2 d3")                              /* $a001                       */ \
    ENTRY(linea_rom_get_pixel,        "d2 d3")                              /* $a002 -> D0                 */ \
    ENTRY(linea_rom_filled_rect,      "d2 d3 d4 d5 d6 d7 a2 a3 a4 a5")      /* $a005                       */ \
    ENTRY(linea_rom_cpu_vline,        "d2 d3 d4 d5 d6 d7 a2 a3 a4 a5")      /* D4-D7, D0 = 2, A4           */ \
    ENTRY(linea_rom_cpu_hline,        "d3 d5 d7 a2 a3 a4 a5")               /* D0-D2, D4-D6, A0, A4        */ \
    ENTRY(linea_rom_cpu_rect_fill,    "d2 d3 d5 d7 a2 a3 a4 a5")            /* D0, D1, D4-D7, A2           */

/* ---- the DECLARATIONS a C caller reaches an entry through ----------------------------------------
 * Each entry is declared as a LABEL, not as a function: its arguments and answers are registers, so a
 * plain C call would pass nothing the routine reads and trust registers it destroys. `entry(...)` does
 * not compile; `(uint32_t)entry` does — the address a drawing vector is pointed at, or the operand of
 * glue that enters it as its ROM callers did:
 *
 *     __asm__ volatile ("jsr vdi_rom_get_kbshift" : "+d"(d0) : : "d1", "a0", "a1", "cc", "memory");
 *
 * naming its inputs and answers as operands, and the scratch registers plus the row's callee-saved set
 * as clobbers. THE CALL SITES SWITCH WHEN THE ROM BUILD LINKS CORES: today no build ships a core (the
 * ROM is a boot stub), and the one C caller of a core here — `vdi_vq_key_s`'s call of `vdi_get_kbshift`
 * — stays on the C core, which Tier 1 proves; `test_vdi_transcribed.py` pins that list. */
#ifndef __ASSEMBLER__
#define VDI_TRANSCRIBED_DECLARATION(entry, destroys) extern const char entry[];
VDI_TRANSCRIBED(VDI_TRANSCRIBED_DECLARATION)
#undef VDI_TRANSCRIBED_DECLARATION
#endif

#endif /* TOS102US_VDI_TRANSCRIBED_H */
