/* gemdosif.S — GEMDOSIF'S HAND 68000 THE TARGET SHIPS AS THE ROM SPELLS IT: pgmld with the hop it reaches `__DOS` by
 * (`$fe39b4..$fe3a0b`), `__DOS` itself (`$fe3c3e..$fe3c61`), the five vector takes behind it (`$fe3c62..$fe3cbd`:
 * restore_trap2, install_trap2, retake, giveerr, takeerr), THE CRITICAL-ERROR HANDLER they install (crit_err,
 * `$fe3cbe..$fe3d2d`, with its table `$fef790..$fef7a1`) and dos_exec (`$fe3d2e..$fe3db3`) — TRANSCRIPTIONS, where
 * `gemdosif.c`'s twins are what Tier 1's host differential proves.
 *
 * WHY THESE ARE ASSEMBLY. Each is hand 68000 over absolute addresses whose C twin measures over Tier 3's 1.10 bar —
 * the image pointer's floor on two to six instructions (restore_trap2 1.42, install_trap2 1.23; giveerr 1.13 and
 * takeerr 1.04 with the BIOS's whole Setexc in both columns, retake 1.13 so and 1.68 on its own cycles); pgmld 1.11 on the
 * arm where Pexec fails (80 cycles over the ROM's, a quarter on the routine's own: three registers saved round a
 * trap for a half that arm never runs) — so by the user's rule the target carries the ROM's own instructions
 * (`include/transcribed.h`). And none is a C function's shape: retake FALLS INTO the tail that makes the Setexc
 * (`$fe3c94`), giveerr branches into it, takeerr calls it and branches into it; pgmld hands Pexec the address of a
 * zero word of ITS OWN TEXT, reaches `__DOS` through a `jmp` two bytes behind that word, and leaves by a `moveq #1 /
 * rts` it shares with dos_sfirst.
 *
 * crit_err AND dos_exec ARE ASSEMBLY FOR ANOTHER REASON: C CANNOT SPELL THEM. crit_err leaves its caller's stack for
 * one of its own round a call; dos_exec parks the process's saved supervisor SP at ITS OWN SP less 64 — a value a
 * program's `trap #2` then stacks from, and a compiled frame's SP is not the ROM's. Each keeps a C twin for Tier 1
 * (dos_exec's handed the SP; crit_err's the table, the alert and the answer, with no stack of its own).
 *
 * THREE PINNED REGIONS (`test/test_aes_gemdosif_transcription.py`, every byte):
 *   - `$fe39b4..$fe3a0b`: the zero word, the hop, pgmld, and the two return tails behind it — `moveq #0 / rts` is
 *     dos_sfirst's and dos_open's miss, carried as the bytes it is (their C returns by itself). ONE WORD RELOCATED:
 *     the hop's `jmp $fe3c3e.l`, to where this file lays `__DOS` out.
 *   - `$fe3c3e..$fe3db3`: `__DOS`, the vector takes, crit_err and dos_exec. TEN LONGWORDS RELOCATED: retake's and
 *     takeerr's `move.l #$fe3cbe,d0` (crit_err, where this file lays it out); the six `jsr`s of spl7_save /
 *     spl_restore (`switch.S`'s entries); crit_err's `movea.l #$fef790,a1` (the table below) and its `jsr $fe768c`
 *     (eralert, which ships as C: the thunk at the end of this file).
 *   - `$fef790..$fef7a1`: crit_err's table, eighteen bytes of the ROM's data laid behind the text.
 *
 * WHAT A BUILD OF THIS FILE NAMES THAT THE ROM NAMES ELSEWHERE:
 *   - `__DOS` parks the return address it was reached with (AES_TRAP1_RETURN) — reached from pgmld, A SITE INSIDE
 *     pgmld: `$fe39ce` / `$fe39fa` in the ROM, `aes_rom_pgmld_pexec_return` / `_mshrink_return` here — and pgmld's
 *     command tail is `aes_rom_pgmld_empty_tail`'s address. Three LOCAL labels Tier 3's relocation registry maps by
 *     (`aes_event.TEXT_SITES`): a build's RAM holds its own, compared exactly, never dropped.
 *   - OF THE TWO HANDLERS THE VECTOR TAKES INSTALL, crit_err IS THE BUILD'S OWN (the sites `$fe3c8e`, `$fe3cb6`:
 *     `#aes_rom_crit_err`, a `Relocated(ABSOLUTE, ...)` of the pin) — so etv_critic holds this file's entry wherever
 *     a build's retake or takeerr ran, MAPPED at Tier 3 through the relocation registry
 *     (`aes_event.CRITICAL_ERROR_HANDLER`). THE TRAP #2 HANDLER IS STILL THE ROM'S ADDRESS (`#GEM_TRAP2`, the sites
 *     `$fe3c78`, `$fe3c84`): the trap door lands beside this in wave 3 and the two operands move with THE FLIP —
 *     `test_aes_rom_data.py` holds both statements (a by-value site whose target has a body of ours reds).
 *   - crit_err's alert is `aes_eralert`, C: its `jsr` names a LOCAL THUNK that takes the two words it pushed into
 *     the C call. The registers eralert's C leaves (D2/A2 kept, A0/A1 its own) are not Alcyon's: the BIOS's disk
 *     driver, compiled C itself, reads D0 alone where the handler returns (`$fc1030`, `$fc1252`).
 *
 * SUPERVISOR CODE. The vector takes are called with the interrupts masked (their Line-F callers bracket them).
 * REGISTERS: the trap #2 pair changes none; the three that trap leave D0 — Setexc's answer, the handler displaced —
 * AND D1 HOLDING THE HANDLER THEY HANDED Setexc (measured: the BIOS's dispatcher comes back with its argument
 * there; nothing else changed — why Tier 3 maps D1 for retake and takeerr); pgmld leaves D0 (1 or -1), D1 (`__DOS`'s
 * verdict) and A0; crit_err leaves D0 = D1 (its answer), D3-D7/A3-A6 as found and the rest eralert's; dos_exec
 * leaves D0 (Pexec's), A0 (the UDA), A1 (its own SP) and what Pexec left of D1, D2 and A2.
 */
#include "addrs.h"
#include "c_call_glue.h"
#include "m68k_encodings.h"
#include "aes/aes.h"
#include "aes/gemdosif.h"

    .text

/* ==== $fe39b4..$fe3a0b: pgmld ========================================================================================= */
/* ---- the empty command tail, $fe39b4: a zero word — and the hop to `__DOS`, $fe39b6, every `bsr` of the glue takes -- */
aes_rom_pgmld_empty_tail:
    .short  0
gemdosif_dos_hop:
    .word   M68K_JMP_ABSOLUTE_LONG
    .long   gemdosif_dos_trap

/* ---- pgmld, $fe39bc: (handle.w, name, &basepage) -> Pexec(3, name, "", 0); *basepage = D0; Mshrink to its size ------- */
    .globl  aes_rom_pgmld
aes_rom_pgmld:
    clr.l   -(%sp)                                  /* the environment: the caller's own */
    pea     aes_rom_pgmld_empty_tail(%pc)
    move.l  PGMLD_NAME_ONCE_TWO_ARE_PUSHED(%sp),-(%sp)
    move.l  #PGMLD_PEXEC_LOAD_WORDS,-(%sp)
    bsr.s   gemdosif_dos_hop
aes_rom_pgmld_pexec_return:
    adda.w  #PGMLD_PEXEC_FRAME_BYTES,%sp
    bne.s   .Lpgmld_failed                          /* `__DOS`'s flags: its verdict word's */
    movea.l PGMLD_BASEPAGE_OUT(%sp),%a0
    move.l  %d0,(%a0)
    movea.l %d0,%a0
    move.l  #PGMLD_BASEPAGE_BYTES,%d0
    add.l   BASEPAGE_TLEN(%a0),%d0
    add.l   BASEPAGE_DLEN(%a0),%d0
    add.l   BASEPAGE_BLEN(%a0),%d0
    move.l  %d0,-(%sp)
    move.l  %a0,-(%sp)
    move.l  #PGMLD_MSHRINK_WORDS,-(%sp)
    bsr.s   gemdosif_dos_hop
aes_rom_pgmld_mshrink_return:
    adda.w  #PGMLD_MSHRINK_FRAME_BYTES,%sp
    beq.s   .Lpgmld_loaded
.Lpgmld_failed:
    moveq   #PGMLD_FAILED,%d0
    rts
    moveq   #0,%d0                                  /* $fe3a04: dos_sfirst's and dos_open's miss — their bytes */
    rts
.Lpgmld_loaded:
    moveq   #PGMLD_LOADED,%d0                       /* $fe3a08: dos_sfirst's "found", shared */
    rts

/* ==== $fe3c3e..$fe3db3: `__DOS`, the vectors GEM takes, crit_err and dos_exec ========================================= */
/* ---- `__DOS`, $fe3c3e: the return it was reached with parked, the trap, AES_DOS_AX and AES_DOS_ERR; D1 the verdict --- */
gemdosif_dos_trap:
    move.l  (%sp)+,(AES_TRAP1_RETURN).l
    trap    #1
    moveq   #0,%d1
    move.w  %d0,(AES_DOS_AX).l
    tst.l   %d0
    bge.s   .Ldos_done
    moveq   #1,%d1
.Ldos_done:
    move.w  %d1,(AES_DOS_ERR).l
    movea.l (AES_TRAP1_RETURN).l,%a0
    jmp     (%a0)

/* ---- restore_trap2, $fe3c62: vector $88 := the holder install_trap2 saved ------------------------------------------- */
    .globl  aes_rom_restore_trap2
aes_rom_restore_trap2:
    move.l  (SYSVAR_VDI_ENTRY).l,(VECTOR_TRAP_GEM).l
    rts

/* ---- install_trap2, $fe3c6e: the vector's holder saved, then the AES's handler stored ------------------------------- */
    .globl  aes_rom_install_trap2
aes_rom_install_trap2:
    move.l  (VECTOR_TRAP_GEM).l,(SYSVAR_VDI_ENTRY).l
    move.l  #GEM_TRAP2,(VECTOR_TRAP_GEM).l
    rts

/* ---- retake, $fe3c84: both of GEM's again — the trap #2 vector stored, then crit_err through the tail it falls into */
    .globl  aes_rom_retake
aes_rom_retake:
    move.l  #GEM_TRAP2,(VECTOR_TRAP_GEM).l
    move.l  #aes_rom_crit_err,%d0
/* ...the shared tail, $fe3c94: Setexc($101, D0) — D0 the handler displaced */
.Lsetexc_critic:
    move.l  %d0,-(%sp)
    move.w  #SETEXC_ETV_CRITIC,-(%sp)
    move.w  #BIOS_SETEXC_FN,-(%sp)
    trap    #13
    addq.w  #8,%sp
    rts

/* ---- giveerr, $fe3ca4: the handler takeerr saved, installed again ---------------------------------------------------- */
    .globl  aes_rom_giveerr
aes_rom_giveerr:
    move.l  (AES_OLD_CRITIC).l,%d0
    bra.s   .Lsetexc_critic

/* ---- takeerr, $fe3cac: the handler in place asked for and saved, then crit_err installed ----------------------------- */
    .globl  aes_rom_takeerr
aes_rom_takeerr:
    moveq   #-1,%d0
    bsr.s   .Lsetexc_critic
    move.l  %d0,(AES_OLD_CRITIC).l
    move.l  #aes_rom_crit_err,%d0
    bra.s   .Lsetexc_critic

/* ---- crit_err, $fe3cbe: (error.w, drive.w) -> D0.l — the alert shown on a stack of its own; the error, or RETRY ------ */
#if AES_CRIT_ERR_SAVED_SP + 4 != AES_CRIT_ERR_STACK
#error "crit_err's stack begins right above the longword its caller's SP is parked in"
#endif
#if CRIT_ERR_LAST_ROW != CRIT_ERR_ALERT_ROWS - 1
#error "crit_err's table: the last row its compare admits is not the table's last"
#endif
    .globl  aes_rom_crit_err
aes_rom_crit_err:
    move.w  CRIT_ERR_ERROR(%sp),%d0
    move.w  CRIT_ERR_DRIVE(%sp),%d1
    M68K_JSR_LONG(aes_rom_spl7_save)                /* $fe3cc6 */
    move.l  %sp,(AES_CRIT_ERR_SAVED_SP).l
    movea.l #AES_CRIT_ERR_STACK_TOP,%sp
    M68K_JSR_LONG(aes_rom_spl_restore)              /* $fe3cd8 */
    movem.l %d3-%d7/%a3-%a6,-(%sp)
    movea.l #aes_rom_crit_err_alerts,%a1            /* $fe3ce2: the table, where this file lays it */
    move.w  %d0,-(%sp)                              /* the error, kept for the answer — and its flags tested */
    bne.s   .Lcrit_err_mapped
    movea.w #CRIT_ERR_ROW_OF_NO_ERROR,%a0
    bra.s   .Lcrit_err_alert
.Lcrit_err_mapped:
    not.w   %d0
    movea.w %d0,%a0
    .word   M68K_CMP_W_IMMEDIATE(M68K_D0), CRIT_ERR_LAST_ROW        /* cmp.w #17,d0 */
    ble.s   .Lcrit_err_alert                        /* SIGNED: a positive error's row is below the table */
    movea.w #CRIT_ERR_ROW_OF_NO_ERROR,%a0
.Lcrit_err_alert:
    move.b  (0,%a0,%a1.l),%d0                       /* the row's byte over the LOW byte of ~error alone */
    move.w  %d1,-(%sp)
    move.w  %d0,-(%sp)
    M68K_JSR_LONG(gemdosif_to_aes_eralert)          /* $fe3d08: jsr eralert */
    addq.l  #ERALERT_FRAME_WORDS_BYTES,%sp
    move.w  (%sp)+,%d1
    ext.l   %d1
    .word   M68K_CMP_W_IMMEDIATE(M68K_D0), 0        /* cmp.w #0,d0: the alert's first button — the error stands */
    beq.s   .Lcrit_err_answered
    move.l  #CRIT_ERR_RETRY,%d1
.Lcrit_err_answered:
    move.l  %d1,%d0
    movem.l (%sp)+,%d3-%d7/%a3-%a6
    movea.l (AES_CRIT_ERR_SAVED_SP).l,%sp
    rts

/* ---- dos_exec, $fe3d2e: (name, mode.w, tail) -> D0.l — Pexec, the UDA's SP parked under the caller's frames --------- */
    .globl  aes_rom_dos_exec
aes_rom_dos_exec:
    M68K_JSR_LONG(aes_rom_spl7_save)                /* $fe3d2e */
    movea.l (AES_RLR).l,%a0
    movea.l PD_UDA(%a0),%a0
    move.l  UDA_SUPER_SP(%a0),(AES_DOS_EXEC_SAVED_SSP).l
    movea.l %sp,%a1
    suba.l  #DOS_EXEC_STACK_KEPT,%a1
    move.l  %a1,UDA_SUPER_SP(%a0)
    M68K_JSR_LONG(aes_rom_spl_restore)              /* $fe3d52 */
    movea.l %sp,%a1
    move.l  #DOS_EXEC_NO_ENVIRONMENT,-(%sp)
    move.l  DOS_EXEC_TAIL(%a1),-(%sp)
    move.l  DOS_EXEC_NAME(%a1),-(%sp)
    move.w  DOS_EXEC_MODE(%a1),-(%sp)
    move.w  #GEMDOS_PEXEC_FN,-(%sp)
    trap    #1
    adda.l  #DOS_EXEC_PEXEC_FRAME_BYTES,%sp
    M68K_JSR_LONG(aes_rom_spl7_save)                /* $fe3d78 */
    movea.l (AES_RLR).l,%a0
    movea.l PD_UDA(%a0),%a0
    move.l  (AES_DOS_EXEC_SAVED_SSP).l,UDA_SUPER_SP(%a0)
    M68K_JSR_LONG(aes_rom_spl_restore)              /* $fe3d90 */
    move.w  #DOS_EXEC_OK,(AES_DOS_ERR).l
    .word   M68K_CMP_W_IMMEDIATE(M68K_D0), 0        /* cmp.w #0,d0: the answer's WORD */
    beq.s   .Ldos_exec_done
    move.w  #DOS_EXEC_FAILED,(AES_DOS_ERR).l
    move.w  %d0,(AES_DOS_AX).l
.Ldos_exec_done:
    rts

/* ==== $fef790..$fef7a1: crit_err's table — row ~error, the alert eralert shows (its number: `aes/fmdo.h`'s two tables,
 * 0 write-protected .. 6 insert a disk). ROM DATA, laid behind the text: what lies BELOW it is this file's own code,
 * where the ROM has another table's longwords — the bytes a positive error's row reads (`aes/gemdosif.h`) =========== */
aes_rom_crit_err_alerts:
    .byte   4, 1, 1, 2, 1, 1, 2, 2, 4, 2, 2, 2, 0, 3, 4, 2, 6, 0
    .if     . - aes_rom_crit_err_alerts - CRIT_ERR_ALERT_ROWS
    .error  "crit_err's table is not CRIT_ERR_ALERT_ROWS bytes"
    .endif

/* ==== THE THUNK crit_err's `jsr` into C reaches: eralert's two words, each sign-extended into its slot as a C caller
 * promotes it, under the image base (`c_call_glue.h`). Local, sized: no ROM bytes, and no entry of the build's. ======== */
#define ERALERT_ALERT         ALCYON_FIRST_ARGUMENT
#define ERALERT_DRIVE         (ALCYON_FIRST_ARGUMENT + 2)
#define ERALERT_ARGUMENT_SLOTS 2
    .type   gemdosif_to_aes_eralert,@function
gemdosif_to_aes_eralert:
    move.w  ERALERT_DRIVE(%sp),%d0
    ext.l   %d0
    move.l  %d0,-(%sp)
    move.w  (ERALERT_ALERT + SLOT_BYTES)(%sp),%d0   /* the alert, the stack one slot deeper */
    ext.l   %d0
    move.l  %d0,-(%sp)
    pea     (0).w
    jsr     aes_eralert
    lea     (IMAGE_ARGUMENT_BYTES + ERALERT_ARGUMENT_SLOTS * SLOT_BYTES)(%sp),%sp
    rts
    .size   gemdosif_to_aes_eralert,.-gemdosif_to_aes_eralert
