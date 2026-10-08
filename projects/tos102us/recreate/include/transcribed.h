/* transcribed.h — THE TRANSCRIBED TABLE: every ROM routine, of ANY component, the shipped build takes as the
 * ROM's own instructions (the `.S` files in `src/vdi/` and `src/aes/`) instead of its C core, and what a C caller
 * needs to reach one. ONE table for every component: a component's rows are a block of it, so there is one list
 * the build, Tier 3 and the declarations read, and nothing that could forget a component's list.
 *
 * THE RULE IT RECORDS is the user's, for the hand-written 68000: port the routine to C first — Tier 1
 * proves the C against the ROM — and where the C measures over Tier 3's 1.10 bar, SHIP a byte-pinned
 * `.S` transcription. Three rows are here for the other reason a ROM routine ships as its own
 * instructions: an ENTRY a vector holds the address of, entered with a convention no C function has —
 * `vdi_rom_timer_tick`, etv_timer's, `linea_rom_dispatch`, vector $28's, and `vdi_rom_entry`, `trap #2`'s
 * (the `src/bios/trap.S` / `isr.S` precedent); Tier 1 still proves each one's C twin. One AES row is
 * here for a third: `aes_rom_lmul`, the Alcyon runtime a transcribed merge_str `jsr`s, whose call it can
 * relocate only into a region a battery pins (`src/aes/optimize.S`), though its own C is under the bar
 * (its sibling `aes_rom_ldiv` is here by the rule: its C is over the bar on its callers' divisors). This
 * table is the one place "ships as `.S`" is said, and three things are derived
 * from it rather than restated:
 *
 *   * TIER 3 (`bench/tier3.py`, legend (T), verdict `transcribed`): a routine here may have C rows over
 *     the bar ONLY while every one of its `.S` rows measures at or under it — or, for a `.S` that calls C
 *     through thunks of its own (the escape), has its OWN instructions at or under it (legend (T←), verdict
 *     `own`). Nothing is typed per row, and a written entry for a `.S` row carries nothing: delete a `.S`
 *     row, or let one drift over the bar, and the C rows go red.
 *   * THE BUILD CONTRACT (`atari/target.mk`): `TRANSCRIBED_ENTRIES` is what the ROM build links for these
 *     routines and `TRANSCRIBED_C_CORES` the C it must NOT link. `test_transcribed.py` pins the make
 *     lists against this table, every `.globl` of the `.S` sources against its rows, and the C callers
 *     that still reach a C core here (each needs the glue below once the ROM build links cores).
 *   * THE DECLARATIONS at the end, for that glue.
 *
 * ONE ROW PER `.S` ENTRY, and the naming rule (`test/routines.py`, every component's) gives the rest: the ROM
 * routine is the entry upper-cased (`linea_rom_hline` -> `LINEA_ROM_HLINE`, `aes_rom_x` -> `AES_ROM_X`) and the C
 * core is the entry less its `rom_` (`linea_hline`, `aes_x`). The second column is the entry's REGISTER
 * CONTRACT against the GCC m68k ABI: the CALLEE-SAVED registers (D2-D7, A2-A6) it leaves changed. D0/D1/A0/A1
 * are the ABI's scratch and every entry may change them. A ROM caller never cared — Alcyon keeps less, and the
 * VDI's `trap #2` entry saves D1-A6 round the whole dispatch — but a C caller built by GCC keeps values in
 * exactly these, so a call that does not name them is the d2/a2 corruption class
 * (`docs/on-target-execution.md`). The sets are the ROM's own, measured over every registered `.S` case
 * (`test_transcribed.py`), where the transcription relation proves the `.S` leaves the same file; a front end that jumps through a
 * drawing vector is charged all of D2-D7/A2-A5, because what runs there is the vector's. A DOOR is charged
 * the union over the routines it serves: the Line-A exception keeps D3-D7/A3-A5 round its `jsr` and leaves
 * D2, A2 and A6 as the primitive left them — A6 measured through $a007, which returns it 76 on ($fd05fc).
 *
 * The trailing comment is the rest of the contract a glue author needs: the registers an entry reads
 * and answers in (the Line-A ones are `test/vdi_raster.py`'s `declare_primitive`s), or "Alcyon" for a
 * word-argument C call answering in D0.w (`vdi/helpers.h`), or "function" for a VDI function reached
 * with the Line-A pointers set (`vdi/vdi.h`).
 *
 * AN AES ROW (`../README.md`, "What ships as the ROM's own instructions") is held to two more constraints on its
 * ROM routine's EXECUTED PATH, which `test_transcribed.py` reads off the oracle's profile over the row's cases: it is
 * HAND 68000 — it executes no Line-F word (`$Fxxx`), which would run the ROM's code through the handler's table
 * from inside the blob (the region may still carry another routine's Line-F words as bytes) — and every one of the
 * optimize layer's shared return tails ($fed066 / $fed06a) it reaches lies in its own pinned region.
 *
 * WHAT IS NOT A ROW, though it ships as the ROM's bytes: THE PROCESS SWITCH AND THE INTERRUPTS' GLUE
 * (`atari/target.mk`, SWITCH_SOURCES — `src/aes/switch.S`: dsptch, disp, savestate, switchto, gotopgm and the mask
 * brackets; `src/aes/irq.S`: the button, motion and tick glue, drawrat and the bare `rts`). A row says "this routine
 * has a C core Tier 1 proves, and the shipped build links the `.S` INSTEAD": the derived C-core name is the twin the
 * ROM build must not link, and the shipped blob reaches the entry through a generated thunk of that name. A context
 * switch has no C core to exclude, and its entry is reached by a plain `jsr` under the very name the C calls
 * (`aes_dsptch`) — a thunk there would put ITS return address under the frame dsptch builds; a glue is entered by
 * the VDI's interrupt code with a register contract no thunk has. (drawrat alone has a C spelling too — `evfork.c`'s
 * `aes_drawrat`, the one mchange calls: the `.S` is what the build hands whoever takes its address, not a twin the
 * build must leave out.) So they are a kind of their own in the build contract (kept out of TRANSCRIBED_SOURCES as
 * the Alcyon entries are), byte-pinned (`test/test_aes_switch.py`, `test/test_aes_irq.py`, `test/test_tier3.py`)
 * and, but for the rows that enter one from a staged caller, unpriced.
 */
#ifndef TOS102US_TRANSCRIBED_H
#define TOS102US_TRANSCRIBED_H

#define TRANSCRIBED(ENTRY)                                                                                    \
    /* ---- the VDI and Line-A: `src/vdi`'s `.S` files ------------------------------------------------ */ \
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
    ENTRY(vdi_rom_clear_span,         "d2 a2")                              /* Alcyon (from.l, to.l)       */ \
    ENTRY(vdi_rom_timer_tick,         "d2 d3 d4 d5 d6 d7 a2 a3 a4 a5")      /* etv_timer: word at 4(sp)    */ \
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
    ENTRY(linea_rom_cpu_blit,         "d2 d3 d4 d5 d6 d7 a2 a3 a4 a5")      /* D0/D2/D4/D6 x edges, A6     */ \
    ENTRY(linea_rom_dispatch,         "d2 a2 a6")                           /* vector $28: frame, `rte`    */ \
    ENTRY(linea_rom_init,             "a2")                                 /* $a000 -> D0, A0, A1, A2     */ \
    ENTRY(vdi_rom_entry,              "")                                   /* trap #2: D1 block -> D0.w   */ \
    ENTRY(vdi_rom_escape,             "d2 d3 d4 d5 d6 d7 a2 a3 a4 a5")      /* function 5: console scratch */ \
    /* ---- the AES: `src/aes`'s `.S` files --------------------------------------------------------------- */ \
    ENTRY(aes_rom_mul_div,            "")                                   /* Alcyon (m1, m2, d) -> D0.w  */ \
    ENTRY(aes_rom_set_contrl_ptr,     "")                                   /* Alcyon (pointer)            */ \
    ENTRY(aes_rom_get_contrl_ptr2,    "")                                   /* Alcyon (answer)             */ \
    ENTRY(aes_rom_lstcpy,             "")                                   /* Alcyon (dst, src) -> D0.w   */ \
    ENTRY(aes_rom_xstrpix,            "")                                   /* Alcyon (dst, src) -> D0.w   */ \
    ENTRY(aes_rom_wset,               "")                                   /* Alcyon (dst, count, value)  */ \
    ENTRY(aes_rom_xstrpix_n,          "")                                   /* Alcyon (dst, src, count)    */ \
    ENTRY(aes_rom_wcopy,              "")                                   /* Alcyon (dst, src, count)    */ \
    ENTRY(aes_rom_wfill,              "")                                   /* Alcyon (dst, count, value)  */ \
    ENTRY(aes_rom_lstrlen,            "")                                   /* Alcyon (string) -> D0.w     */ \
    ENTRY(aes_rom_lbcopy,             "")                                   /* Alcyon (dst, src, count)    */ \
    ENTRY(aes_rom_movs,               "")                                   /* Alcyon (count, src, dst)    */ \
    ENTRY(aes_rom_min,                "")                                   /* Alcyon (a, b) -> D0.w       */ \
    ENTRY(aes_rom_max,                "")                                   /* Alcyon (a, b) -> D0.w       */ \
    ENTRY(aes_rom_bfill,              "")                                   /* Alcyon (count, byte, dst)   */ \
    ENTRY(aes_rom_toupper,            "")                                   /* Alcyon (character) -> D0.w  */ \
    ENTRY(aes_rom_strlen,             "")                                   /* Alcyon (string) -> D0.w     */ \
    ENTRY(aes_rom_streq,              "")                                   /* Alcyon (a, b) -> D0.w       */ \
    ENTRY(aes_rom_strcpy,             "")                                   /* Alcyon (src, dst) -> D0.l   */ \
    ENTRY(aes_rom_strscn,             "")                                   /* Alcyon (src, dst, stop) -> D0.l */ \
    ENTRY(aes_rom_strcat,             "")                                   /* Alcyon (src, dst) -> D0.l   */ \
    ENTRY(aes_rom_scasb,              "")                                   /* Alcyon (string, byte) -> D0.l */ \
    ENTRY(aes_rom_strchk,             "")                                   /* Alcyon (a, b) -> D0.w       */ \
    ENTRY(aes_rom_fmt_str,            "")                                   /* Alcyon (src, dst)           */ \
    ENTRY(aes_rom_unfmt_str,          "")                                   /* Alcyon (src, dst)           */ \
    ENTRY(aes_rom_merge_str,          "d2")                                 /* Alcyon (dst, template, parameters) */ \
    ENTRY(aes_rom_wildcmp,            "")                                   /* Alcyon (pattern, name) -> D0.w */ \
    ENTRY(aes_rom_lmul,               "d2")                                 /* Alcyon (a.l, b.l) -> D0.l: merge_str's callee */ \
    ENTRY(aes_rom_ldiv,               "")                                   /* Alcyon (a.l, b.l) -> D0.l: merge_str's callee */ \
    ENTRY(aes_rom_r_get,              "a2")                                 /* Alcyon (rect, &x, &y, &w, &h) */ \
    ENTRY(aes_rom_r_set,              "a2")                                 /* Alcyon (rect, x, y, w, h)   */ \
    ENTRY(aes_rom_rc_copy,            "")                                   /* Alcyon (from, to)           */ \
    ENTRY(aes_rom_rc_equal,           "")                                   /* Alcyon (one, other) -> D0.w */ \
    ENTRY(aes_rom_rc_union,           "d2")                                 /* Alcyon (from, into)         */ \
    ENTRY(aes_rom_rc_constrain,       "")                                   /* Alcyon (container, rect)    */ \
    ENTRY(aes_rom_gsx2,               "")                                   /* trap #2 -> D0.w             */ \
    ENTRY(aes_rom_gsx_ncode,          "")                                   /* Alcyon (op, n_ptsin, n_intin) -> D0.w */ \
    ENTRY(aes_rom_gsx_1code,          "")                                   /* Alcyon (op, value) -> D0.w  */ \
    ENTRY(aes_rom_gsx_mon,            "")                                   /* Alcyon ()                   */ \
    ENTRY(aes_rom_gsx_fix,            "a2")                                 /* Alcyon (mfdb, address, bytes, height) */ \
    ENTRY(aes_rom_gr_inside,          "")                                   /* Alcyon (rect, thickness)    */ \
    ENTRY(aes_rom_gr_crack,           "d2")                                 /* Alcyon (colour, five answer pointers) */ \
    ENTRY(aes_rom_gsx_gclip,          "")                                   /* Alcyon (rect)               */ \
    ENTRY(aes_rom_gsx_chkclip,        "d2 a2")                              /* Alcyon (rect) -> D0.l       */ \
    ENTRY(aes_rom_gsx_bxpts,          "d2")                                 /* Alcyon (rect)               */ \
    ENTRY(aes_rom_gsx_mret,           "")                                   /* Alcyon (&address, &length)  */ \
    ENTRY(aes_rom_ratinit,            "")                                   /* Alcyon ()                   */ \
    ENTRY(aes_rom_gsx_mxmy,           "")                                   /* Alcyon (&x, &y)             */ \
    ENTRY(aes_rom_gsx_button,         "")                                   /* Alcyon () -> D0.w           */ \
    ENTRY(aes_rom_uda_insuper,        "")                                   /* Alcyon (uda)                */ \
    ENTRY(aes_rom_psetup,             "a2")                                 /* Alcyon (pd, pc): supervisor */

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
 * contour primitives, listed as `(caller, core)` pairs in `test/transcription.py`'s C_CALLERS_OF_TRANSCRIBED_CORES
 * and held to the m68k build's own calls by `test_transcribed.py` — calls it by its C name in the host
 * build, where Tier 1 proves it. A shipped build reaches the `.S` instead, through a GLUE THUNK carrying
 * the core's name: `bench/shipped_glue.py` generates one per called core from this table (the row's
 * destroyed registers saved round the `jsr`) and the entry's declared contract, and Tier 3 builds and
 * measures that SHIPPED CONFIGURATION as a second blob (`../README.md`, "What ships as the ROM's own
 * instructions"). */
#ifndef __ASSEMBLER__
#define TRANSCRIBED_DECLARATION(entry, destroys) extern const char entry[];
TRANSCRIBED(TRANSCRIBED_DECLARATION)
#undef TRANSCRIBED_DECLARATION

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

/* ...AND THE ATTRIBUTE THE C TWIN OF EVERY EVENT-DOOR ENTRY IS DEFINED WITH (`aes/evdoor.h`: `aes_tak_flag`, ...), for
 * the same reason and no table row: a twin's FIRST INSTRUCTION is an ARRIVAL — where Tier 3 and the watches read the
 * call's frame, lay a delivery and take a slice's mark (`bench/tier3.py`'s `twin_entries`). GCC inlines a small twin
 * into a caller of its own file, and specialises a larger one, and the arrival is then nowhere: the row goes
 * unwatched on our side alone. Here, in a header with no include of its own, because a twin's header is one
 * `aes/evdoor.h` includes. `test/test_tier3.py` holds every linked twin to it, on both blobs. */
#if defined(__GNUC__) && !defined(__clang__)
#define EVDOOR_TWIN __attribute__((noipa))
#else
#define EVDOOR_TWIN __attribute__((noinline))
#endif

/* ...AND THE STATEMENT THAT FOLLOWS A TWIN'S CALL WHEREVER THE CALL'S ANSWER IS RETURNED AS IT IS — the rebound
 * wrappers' (`aes/evdoor.h`), and a twin's own `return aes_<entry>(...)` of another twin's core. An arrival is a CALL:
 * the watches close it at the return address the call left, inside our build's text, as the ROM's Line-F call word
 * leaves one inside its caller. GCC compiles a call in return position to a tail `jmp` when the callee's arguments
 * fit the caller's own, and the twin is then entered holding its caller's CALLER's return address — the run's
 * sentinel, for a row entered at the caller — which no watch can tell from an entry reached by no call at all
 * (rehearsed: with unsync and ap_rdwr flipped, 17 of the 222 door rows were refused "not a door call").
 *
 * WHAT STANDS BETWEEN THE CALL AND THE RETURN is a read of the function's own return address, its value dropped: a
 * statement GCC may not move the call past, which expands to no instruction and — unlike an empty `asm`, measured —
 * weighs NOTHING in the inliner's size estimate (an `asm` statement counts as one instruction, and one unit on
 * tak_flag's wrapper was enough to stop wm_opcl being inlined into wm_close: a committed object changed for a
 * statement that assembles to nothing). The call stays a `jsr`, its `rts` behind it. HELD ON THE BLOBS, not trusted
 * to the compiler: `test/test_tier3.py` — no jump into a twin's first instruction, on either. */
#define EVDOOR_A_CALL_NOT_A_JUMP (void)__builtin_return_address(0)
#endif

#endif /* TOS102US_TRANSCRIBED_H */
