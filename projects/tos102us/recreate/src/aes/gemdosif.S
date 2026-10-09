/* gemdosif.S — GEMDOSIF'S HAND 68000 THE TARGET SHIPS AS THE ROM SPELLS IT: pgmld with the hop it reaches `__DOS` by
 * (`$fe39b4..$fe3a0b`), `__DOS` itself (`$fe3c3e..$fe3c61`) and the five vector takes behind it (`$fe3c62..$fe3cbd`:
 * restore_trap2, install_trap2, retake, giveerr, takeerr) — TRANSCRIPTIONS, where `gemdosif.c`'s twins are what Tier
 * 1's host differential proves.
 *
 * WHY THESE ARE ASSEMBLY. Each is hand 68000 over absolute addresses whose C twin measures over Tier 3's 1.10 bar —
 * the image pointer's floor on two to six instructions (restore_trap2 1.42, install_trap2 1.23; retake and giveerr
 * 1.13 and takeerr 1.04 with the BIOS's whole Setexc in both columns, more on their own cycles); pgmld 1.11 on the
 * arm where Pexec fails (80 cycles over the ROM's, a quarter on the routine's own: three registers saved round a
 * trap for a half that arm never runs) — so by the user's rule the target carries the ROM's own instructions
 * (`include/transcribed.h`). And none is a C function's shape: retake FALLS INTO the tail that makes the Setexc
 * (`$fe3c94`), giveerr branches into it, takeerr calls it and branches into it; pgmld hands Pexec the address of a
 * zero word of ITS OWN TEXT, reaches `__DOS` through a `jmp` two bytes behind that word, and leaves by a `moveq #1 /
 * rts` it shares with dos_sfirst.
 *
 * TWO PINNED REGIONS (`test/test_aes_gemdosif_transcription.py`, every byte):
 *   - `$fe39b4..$fe3a0b`: the zero word, the hop, pgmld, and the two return tails behind it — `moveq #0 / rts` is
 *     dos_sfirst's and dos_open's miss, carried as the bytes it is (their C returns by itself). ONE WORD RELOCATED:
 *     the hop's `jmp $fe3c3e.l`, to where this file lays `__DOS` out.
 *   - `$fe3c3e..$fe3cbd`: `__DOS` and the vector takes, nothing relocated.
 *
 * WHAT A BUILD OF THIS FILE NAMES THAT THE ROM NAMES ELSEWHERE:
 *   - `__DOS` parks the return address it was reached with (AES_TRAP1_RETURN) — reached from pgmld, A SITE INSIDE
 *     pgmld: `$fe39ce` / `$fe39fa` in the ROM, `aes_rom_pgmld_pexec_return` / `_mshrink_return` here — and pgmld's
 *     command tail is `aes_rom_pgmld_empty_tail`'s address. Three LOCAL labels Tier 3's relocation registry maps by
 *     (`aes_event.TEXT_SITES`): a build's RAM holds its own, compared exactly, never dropped.
 *   - THE TWO HANDLERS THE VECTOR TAKES INSTALL are still THE ROM'S OWN ADDRESSES (`#GEM_TRAP2`, `#AES_ROM_CRIT_ERR`:
 *     the sites `$fe3c78`, `$fe3c84`, `$fe3c8e`, `$fe3cb6`): the AES's trap #2 handler and crit_err are band 5's
 *     wave 3. THE DAY THEY LAND, each of the four operands becomes the build's own entry and a `Relocated(ABSOLUTE,
 *     ...)` of the pin — `test_aes_rom_data.py` REDS until then (a by-value site whose target has a body of ours).
 *
 * SUPERVISOR CODE. The vector takes are called with the interrupts masked (their Line-F callers bracket them).
 * REGISTERS: the trap #2 pair changes none; the three that trap leave D0 — Setexc's answer — and no other changed
 * (measured: the BIOS's dispatcher restores what its Setexc uses but D0); pgmld leaves D0 (1 or -1), D1 (`__DOS`'s
 * verdict) and A0.
 */
#include "addrs.h"
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

/* ==== $fe3c3e..$fe3cbd: `__DOS`, and the vectors GEM takes ============================================================ */
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
    move.l  #AES_ROM_CRIT_ERR,%d0
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
    move.l  #AES_ROM_CRIT_ERR,%d0
    bra.s   .Lsetexc_critic
