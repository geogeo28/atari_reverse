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
    ENTRY(linea_rom_cpu_rect_fill,    "d2 d3 d5 d7 a2 a3 a4 a5")            /* D0, D1, D4-D7, A2           */ \
    ENTRY(vdi_rom_mouse_isr,          "")                                   /* A0 packet: `movem` round it */ \
    ENTRY(vdi_rom_default_user_cur,   "")                                   /* D0, D1                      */ \
    ENTRY(vdi_rom_vbl_draw_cursor,    "d2 d3 d4 d5 d6 d7 a2 a3 a4 a5 a6")   /* _vblqueue[0]                */ \
    ENTRY(linea_rom_draw_sprite,      "d2 d3 d4 d5 d6 d7 a2 a3 a4 a5 a6")   /* $a00d: A0 form, A2, D0/D1   */ \
    ENTRY(linea_rom_undraw_sprite,    "d2 d3 d4 d5 a2 a3 a4 a5")            /* $a00c: A2 save block        */ \
    ENTRY(linea_rom_hide_mouse,       "d2 d3 d4 d5 a2 a3 a4 a5")            /* $a00a                       */ \
    ENTRY(vdi_rom_show_cursor,        "d2 d3 d4 d5 d6 d7 a2 a3 a4 a5")      /* A6 kept round the draw      */ \
    ENTRY(vdi_rom_vsc_form,           "")                                   /* function 111, $a00b         */ \
    ENTRY(vdi_rom_poll_choice,        "")                                   /* D0 the caller's             */ \
    ENTRY(vdi_rom_poll_locator,       "a2")                                 /* -> D0; `trap #13` keeps less */ \
    ENTRY(linea_rom_filled_poly,      "d2 d3 d4 d5 d6 d7 a2 a3 a4 a5")      /* $a006                       */ \
    ENTRY(linea_rom_fill_span,        "d2 d3 d4 d5 d6 d7 a2 a3 a4 a5")      /* Alcyon (x1, x2, y)          */ \
    ENTRY(linea_rom_end_pts,          "d2 d3 d4 d6 d7 a2 a3 a4 a5")         /* Alcyon (x,y,&l,&r) -> D0.w */ \
    ENTRY(linea_rom_copy_raster,      "")                                   /* $a00e: `movem` round it all */ \
    ENTRY(linea_rom_bitblt,           "d2 d3 d4 d5 d6 d7 a2 a3 a4 a5 a6")   /* $a007: A6 block -> +76      */ \
    ENTRY(linea_rom_textblt,          "d2 d3 d4 d5 d6 d7 a2 a3 a4")         /* $a008: A5/A6 kept           */ \
    ENTRY(linea_rom_cpu_textblt,      "d2 d3 d4 d5 d6 d7 a2 a3 a4")         /* A6 base, A5/A6 pushed       */ \
    ENTRY(linea_rom_fast_text,        "d2 d3 d4 d5 d6 d7 a2 a3 a4")         /* -> D0 1 drawn, 0 refused    */ \
    ENTRY(linea_rom_cpu_fast_text,    "d2 d3 d4 d5 d6 d7 a2 a3 a4")         /* D0-D3, A5 &FBASE pushed     */ \
    ENTRY(linea_rom_cpu_blit,         "d2 d3 d4 d5 d6 d7 a2 a3 a4 a5")      /* D0/D2/D4/D6 x edges, A6     */

/* ---- the DECLARATIONS a C caller reaches an entry through ----------------------------------------
 * Each entry is declared as a LABEL, not as a function: its arguments and answers are registers, so a
 * plain C call would pass nothing the routine reads and trust registers it destroys. `entry(...)` does
 * not compile; `(uint32_t)entry` does — the address a drawing vector is pointed at, or the operand of
 * glue that enters it as its ROM callers did:
 *
 *     __asm__ volatile ("jsr vdi_rom_get_kbshift" : "+d"(d0) : : "d1", "a0", "a1", "cc", "memory");
 *
 * naming its inputs and answers as operands, and the scratch registers plus the row's callee-saved set
 * as clobbers.
 *
 * THE C THAT STILL CALLS A C CORE HERE — the VDI functions and fill layer round the raster, sprite and
 * contour primitives, listed as `(caller, core)` pairs in `test/vdi.py`'s C_CALLERS_OF_TRANSCRIBED_CORES
 * and held to the m68k build's own calls by `test_vdi_transcribed.py` — calls it by its C name in the host
 * build, where Tier 1 proves it. A shipped build reaches the `.S` instead, through a GLUE THUNK carrying
 * the core's name: `bench/shipped_glue.py` generates one per called core from this table (the row's
 * destroyed registers saved round the `jsr`) and the entry's declared contract, and Tier 3 builds and
 * measures that SHIPPED CONFIGURATION as a second blob (`../README.md`, "What ships as the ROM's own
 * instructions"). */
#ifndef __ASSEMBLER__
#define VDI_TRANSCRIBED_DECLARATION(entry, destroys) extern const char entry[];
VDI_TRANSCRIBED(VDI_TRANSCRIBED_DECLARATION)
#undef VDI_TRANSCRIBED_DECLARATION

/* THE ATTRIBUTE EVERY C CORE OF THIS TABLE IS DEFINED WITH. A core must stay a CALLED function in every
 * build of it: the shipped configuration replaces its body with a glue thunk at link time, which reaches
 * only a real call — a copy GCC inlined, cloned or specialised into its caller would go on shipping the C,
 * and the caller pairs above would name the wrong call sites. `noipa` is GCC's "treat the body as unknown":
 * no inlining, no clone, and no interprocedural register allocation, without which a caller could keep a
 * value in a scratch register the C core happens not to touch and the `.S` does.
 *
 * In the SHIPPED CONFIGURATION's build (`TRANSCRIBED_CORES_WEAK`, the Makefile's shipped blob) each core is
 * also WEAK, so the thunk of the same name is the definition every call links to. It must be weak in the
 * SOURCE: the assembler resolves a call to a global function of its own file against the function's
 * SECTION rather than its name — past the reach of anything done to the symbol afterwards — and leaves a
 * weak one by name. The host differential is built by clang, which spells none of this and needs only the
 * call kept (`noinline`). */
#if defined(__GNUC__) && !defined(__clang__) && defined(TRANSCRIBED_CORES_WEAK)
#define TRANSCRIBED_CORE __attribute__((noipa, weak))
#elif defined(__GNUC__) && !defined(__clang__)
#define TRANSCRIBED_CORE __attribute__((noipa))
#else
#define TRANSCRIBED_CORE __attribute__((noinline))
#endif
#endif

#endif /* TOS102US_VDI_TRANSCRIBED_H */
