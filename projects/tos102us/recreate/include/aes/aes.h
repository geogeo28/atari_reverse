/* aes/aes.h — the AES's RAM: its globals in GEMBSS, THEGLO's tables (UDAs, PDs, CDAs, EVBs, the fork queue, the
 * ORECT pool, the window records), and the Line-F call mechanism every AES routine is entered and left through.
 *
 * WHERE THE AES KEEPS ITS STATE. Everything is at an ABSOLUTE address in GEMBSS (`$8900..$c9ff`), reached as
 * `move.l $c794,a0` — Alcyon C with no base register. The bulk is ONE block, THEGLO at `$9c58`, which gem_main
 * clears word by word (`$fd9f78`) and carves into fixed tables by offset from `a5 = $9c58` (`$fda06a`); the tables
 * are spelt below as absolute addresses (`AES_PD_TABLE` = THEGLO + $1206) and their records as offsets (`PD_UDA`).
 *
 * THE SNAPSHOT IS INSIDE THE DISPATCHER'S IDLE LOOP: `AES_RLR` is NULL, `AES_INDISP` is 1, both processes (PD0 the
 * shell and desk, PD1 the screen manager) wait on `AES_NRL`. So every case POKES `AES_RLR` (most of the AES reads
 * `rlr->…`) and decides `AES_INDISP` — `test/aes.py`'s `machine()` is that door.
 *
 * Every field carries one ROM access that establishes it, and the WIDTH TAG (`vdi/linea.h`, "THE WIDTH TAG") —
 * `test/aes.py`'s FIELDS parses it through `test/layouts.py`. A constant whose comment opens with anything else (a
 * count, a size, a mask, an address) is NOT a field. What the header does not name, and why, is in `test/aes.py`'s
 * docstring. Frozen the way `gemdos/fs.h` is: the only permitted edit is adding a field with its own citation.
 */
#ifndef TOS102US_AES_AES_H
#define TOS102US_AES_AES_H

#include "addrs.h"

/* ---- the SCHEDULER's globals -------------------------------------------------------------------------------
 * Three lists of PDs linked by PD_LINK: `rlr` the RUNNING one and those ready behind it, `nrl` those blocked in
 * an event wait, `drl` those an event woke that the idle loop moves back to `rlr` ($fe4d74). */
#define AES_RLR               0xc794     /* long: the running PD, head of the ready list ($fda192)             */
#define AES_NRL               0xc726     /* long: the not-ready list          ($fe4bb8 mwait_act's push)      */
#define AES_DRL               0x9c16     /* long: the woken list idle() drains ($fe4d74)                       */
/* A BYTE, and the dispatcher's whole re-entry guard: dsptch is a bare `rts` while it is set ($fe387c), savestate
 * sets it ($fe38f0 addq.b #1) and switchto clears it on the way out ($fe394e) — so the snapshot, taken inside
 * disp's idle loop, holds 1. */
#define AES_INDISP            0xc67e     /* byte: inside the dispatcher         ($fe387c tst.b)                */
#define AES_INDISP_SET        1          /* the value inside disp               (the snapshot's)               */
#define AES_FORKER_BUSY       0xc6ae     /* byte: forker is running forks      ($fe4bce move.b #1)             */
/* forker sets `rlr` to -1 while it runs the fork functions ($fe4bdc), so a fork function that reads rlr reads it. */
#define AES_RLR_IN_FORKER     0xffffffff /* ($fe4bdc move.l #-1,$c794)                                         */
#define AES_GL_CDA            0x97fa     /* long: the running PD's CDA          ($fda1c8, $fe4dec)             */
#define AES_STATIC_PIDS       0xc680     /* word: PDs gem_main set up           ($fda1a6 addq.w #1)            */
#define AES_ACCESSORY_COUNT   0xc682     /* word: accessories loaded            ($fe439c clr.w)                */
/* The three SR saves, one per mechanism, and the DISPATCHER's own stack: savestate leaves the process's super
 * stack for it ($fe3922 `lea $8c1a,sp`), which is the region below $8c1a two captures disagree about. */
#define AES_SR_DISPATCH       0x8994     /* word: savestate/switchto's SR       ($fe38d4)                      */
#define AES_SR_SPL            0x8996     /* word: spl7/splx's                   ($fe3890)                      */
#define AES_SR_PSETUP         0x8998     /* word: psetup's                      ($fe397a)                      */
#define AES_DISPATCHER_STACK_TOP 0x8c1a  /* the dispatcher's stack, growing down ($fe3922 lea)                */

/* ---- the FORK QUEUE: what an interrupt or the keyboard poll asks forker to run ------------------------------ */
#define AES_FORK_HEAD         0x9bf2     /* word: next entry forker takes       ($fe4bf0)                      */
#define AES_FORK_TAIL         0xc6b0     /* word: next entry forkq fills        ($fe4b2c)                      */
#define AES_FORK_COUNT        0xc906     /* word: entries queued                ($fe4b22 cmpi.w #32)           */
#define AES_FORK_POSTED       0x9c42     /* byte: set by every forkq            ($fe4b6a move.b #1)            */
#define AES_FORK_ENTRIES      32         /* ($fe4b22, $fe4b4a cmpi.w #32: the tail wraps)                     */
#define FORK_CODE             0          /* long: the fork function's ROM address ($fe4b5a)                    */
#define FORK_DATA             4          /* long: its one argument              ($fe4b5e)                      */
#define FORK_ENTRY_BYTES      8          /* ($fe4b32 asl.w #3)                                                 */

/* ---- event recording (appl_trecord), inside forker ---------------------------------------------------------- */
#define AES_GL_RECD           0xc79a     /* word: recording on                  ($fe4c1e tst.w)                */
#define AES_RECORD_CURSOR     0x96ee     /* long: next record                   ($fe4c62)                      */
#define AES_RECORD_LEFT       0x9728     /* word: records left                  ($fe4ca4 subq.w #1)            */
#define AES_TIMER_COUNTDOWN   0x9492     /* long: ticks to the ev_timer         ($fe4e48)                      */
#define AES_TIMER_ELAPSED     0x948e     /* long: ...and those counted          ($fe4e50 clr.l)                */

/* ---- the OS doors' parking places: a return address held across a trap, because the glue is not re-entrant -- */
#define AES_DOS_RETURN        0x8c1e     /* long: __DOS's caller                ($fe3ba0 move.l (sp)+)         */
#define AES_TRAP1_RETURN      0x8c22     /* long: the trap #1 glue's caller     ($fe3c3e)                      */
#define AES_BIOS_RETURN       0x95ae     /* long                                ($fee478)                      */
#define AES_XBIOS_RETURN      0x95b2     /* long                                ($fee488)                      */
#define AES_GEMDOS_RETURN     0x8900     /* long: gem_gemdos_call's caller      ($fd9fc6)                      */
#define AES_DOS_ERR           0x98ec     /* word: the last GEMDOS call failed   ($fd9fec move.w #1)            */
#define AES_DOS_AX            0xc918     /* word: ...and what it answered       ($fd9fde)                      */
/* The vectors GEM takes over, and what they held. `trap #2`'s old vector ($fe3c6e) is the one the VDI's own arm
 * jumps through, so it is `addrs.h`'s `SYSVAR_VDI_ENTRY` and not spelt a second time. */
#define AES_OLD_CRITIC        0x8c26     /* long: etv_critic before GEM         ($fe3cb0)                      */
/* The G_USERDEF door: the trampoline ob_draw calls through, and the 1 KB stack it switches to. */
#define AES_USERDEF_TRAMPOLINE 0x8c32    /* long: $fe3f3e                       ($fd9fa4)                      */
#define AES_USERDEF_SP_SAVE   0x8c36     /* long: the caller's SP               ($fe3f42)                      */
#define AES_USERDEF_STACK     0x8c3a     /* long: the userdef stack's top       ($fe3f48)                      */

/* ---- the AES's VDI arrays (gsx2 `$fecb5a`: `lea $9466,a0; move.l #$c7e0,(a0); trap #2`) --------------------
 * Addresses, not fields: each is a whole array the AES hands the VDI. contrl[0..3] ($c7e1 +7) are rewritten on
 * every keyboard poll of the idle loop (VDI 128, 33, 31), which is why they are in the capture MASK — a case that
 * reaches the VDI stages its own. */
#define AES_GSX_PB            0x9466     /* the parameter block's five pointers ($fecb5a lea)                  */
#define AES_GSX_CONTRL        0xc7e0     /* contrl[]                            ($fda8f4 lea)                  */
#define AES_GSX_INTIN         0x95ba     /* intin[]                             ($fda8ee lea)                  */
#define AES_GSX_PTSIN         0x98c4     /* ptsin[]                             ($fda7fe lea)                  */
#define AES_GSX_INTOUT        0x9706     /* intout[]                            ($fe4ce8)                      */
#define AES_GSX_PTSOUT        0x9abc     /* ptsout[]                            ($fdab2e lea)                  */

/* ---- the SHELL and the DESK ---------------------------------------------------------------------------------
 * The desk reaches every global of its own through ONE pointer, to a GEMDOS Malloc block in the TPA (desk_alloc
 * `$fee80a`): a desk case stages and compares TPA, not GEMBSS. */
#define AES_DESK_GLOBALS      0xc6a6     /* long: the desk's global block       ($fdaea2)                      */
#define AES_SHELL_BUFFER      0xc79e     /* long: the shell's buffer            ($fda00e)                      */
#define AES_SH_COMMAND        0xc42e     /* byte: sh_cmd's command              ($feb310 move.b)               */

/* ---- THEGLO: the one block gem_main clears and carves ($fda062) --------------------------------------------- */
#define AES_THEGLO            0x9c58     /* ($fda06a movea.l #$9c58,a5)                                        */
#define AES_THEGLO_WORDS      5388       /* the clear: $fee800's 5387, then `dbmi` ($fd9f82)                  */
/* The UDAs: a process's saved state, then its own supervisor stack growing down from the next UDA. NOT one stride:
 * UDA0 (the shell's) is THEGLO + 0 and 1,866 bytes, its stack top UDA1 itself ($fd9fb2 adda.l #1866); UDA1 and the
 * spare UDA2 are smaller, each stack top 4 bytes below what follows it ($fda168, $fda170). */
#define AES_UDA_COUNT         3          /* UDA0, UDA1 and the spare UDA2                                      */
#define AES_UDA1              0xa3a2     /* the screen manager's: THEGLO + $74a ($fda158 lea 1866(a5))          */
#define AES_UDA2              0xa89c     /* the spare: THEGLO + $c44            ($fda160 lea 3140(a5))          */
#define AES_UDA1_STACK_TOP    0xa898     /* UDA1's UDA_SUPER_SP at start-up     ($fda168 lea 3136(a5))          */
#define AES_UDA2_STACK_TOP    0xae5a     /* UDA2's                              ($fda170 lea 4610(a5))          */
#define UDA_STATE_BYTES       74         /* the saved state; the rest of a UDA is its stack (UDA_TRAP_SSP + 4) */
#define UDA_IN_SUPER          0          /* word: 1 inside a trap #2            ($fe3ee2 move.w #1)            */
#define UDA_REGS              2          /* longs[14]: D0..D7/A0..A5            ($fe38fe movem.l d0-a5,-(a6))  */
#define UDA_A6                58         /* long                                ($fe3904)                      */
#define UDA_SUPER_SP          62         /* long: the saved supervisor SP       ($fe3eee)                      */
#define UDA_USER_SP           66         /* long: the saved USP                 ($fe3ee6)                      */
#define UDA_TRAP_SSP          70         /* long: the SSP a trap #2 came in on  ($fe3eea)                      */
#define UDA_REG_COUNT         14         /* D0..A5: savestate's movem           ($fe38fe mask $fffc)           */
/* The PDs: 56 bytes of header, then the process's 128-byte message pipe. */
#define AES_PD_TABLE          0xae5e     /* THEGLO + $1206                      ($fda142 addi.l #4614)          */
#define AES_PD_COUNT          3          /* ($fda14e cmp.w #3)                                                 */
#define PD_BYTES              184        /* ($fda13a muls.w #184)                                              */
#define PD_LINK               0          /* long: the next PD on its list       ($fe4b96, $fda1b2)             */
#define PD_UDA                8          /* long                                ($fe3ede)                      */
#define PD_NAME               12         /* bytes[PD_NAME_BYTES]: blank-filled  ($fda3f6)                      */
#define PD_NAME_BYTES         8          /* ($fda3fc `move.l #$80020`: 8 x ' ')                                */
#define PD_CDA                20         /* long                                ($fda3e2)                      */
#define PD_LDADDR             24         /* long: the basepage gotopgm enters   ($fe38c0)                      */
#define PD_PID                28         /* word                                ($fda19e)                      */
#define PD_STAT               30         /* word: 0 ready, 1 waiting            ($fe4b80 clr.w, $fe40d8)       */
#define PD_EVWAIT             34         /* word: the events it waits for       ($fe40bc)                      */
#define PD_EVFLG              36         /* word: the events that came          ($fe40c8, $fe3f76 or.w)        */
#define PD_QUEUE_ADDRESS      50         /* long: -> PD_QUEUE                   ($fda3ec)                      */
#define PD_QUEUE_INDEX        54         /* word                                ($fda3f0 clr.w)                */
#define PD_QUEUE              56         /* bytes[PD_QUEUE_BYTES]: the message pipe ($fda3e8 lea 56(a5))       */
#define PD_QUEUE_BYTES        128        /* PD_BYTES - PD_QUEUE                                                */
#define PD_STAT_READY         0          /* ($fe4b80)                                                          */
#define PD_STAT_WAITING       1          /* ($fe40d8 move.w #1)                                                */
/* The CDAs, one a PD. */
#define AES_CDA_TABLE         0xb086     /* THEGLO + $142e                      ($fda130 addi.l #5166)          */
#define CDA_BYTES             36         /* ($fda128 muls.w #36)                                               */
#define CDA_KEY_COUNT         34         /* word: keys queued, 8 a full queue   ($fe4cf8 cmpi.w #8)            */
/* The EVBs: fifteen event blocks on the free list `AES_EUL`, and the timer list `AES_TIMER_LIST`. */
#define AES_EVB_TABLE         0xb0f2     /* THEGLO + $149a                      ($fda0ae)                      */
#define AES_EVB_COUNT         15         /* ($fda0ce cmp.w #15)                                                */
#define AES_EUL               0xc676     /* long: the free EVBs                 ($fda0c6, $fe40a4)             */
#define AES_TIMER_LIST        0xc84a     /* long: the timer EVBs                ($fe3fc6)                      */
#define EVB_BYTES             28         /* ($fda0a8 muls.w #28, $fe4024 the clear)                            */
#define EVB_NEXT              0          /* long: the free list's link          ($fe40a4)                      */
#define EVB_LINK              4          /* long: its list's next               ($fe4054)                      */
#define EVB_PRED              8          /* long: ...and previous               ($fe404c)                      */
#define EVB_PD                12         /* long: the PD it wakes               ($fe3f6a)                      */
#define EVB_PARM              16         /* long: a timer's delta               ($fe4094)                      */
#define EVB_FLAG              20         /* word                                ($fe3ff6 move.w #2)            */
#define EVB_MASK              22         /* word: the event bit it posts        ($fe3f72)                      */
/* The fork queue's entries (FORK_* above), and the ORECT pool (`aes/objects.h`'s ORECT_*). */
#define AES_FORK_QUEUE        0xb296     /* THEGLO + $163e                      ($fe4b3e adda.l #5694)          */
#define AES_ORECT_POOL        0xb396     /* THEGLO + $173e                      ($fe5a82)                      */
#define AES_ORECT_COUNT       80         /* ($fe5aa4 cmp.w #80)                                                */
#define AES_ORECT_FREE        0xc824     /* long: the free ORECTs               ($fe5a6a clr.l)                */
/* The WINDOW records: eight of 56 bytes, the last ending two bytes before the clear does ($c670). */
#define AES_WINDOWS           0xc4ae     /* THEGLO + $2856                      ($feb492 adda.l #10326)         */
#define AES_WINDOW_COUNT      8          /* ($fd9f78's clear ends at THEGLO + $2a18 = AES_WINDOWS + 8 x 56 + 2) */
#define WIN_BYTES             56         /* ($feb486 muls.w #56)                                               */
#define WIN_FLAGS             0          /* word: WIN_IN_USE, WIN_BROKEN        ($feb49e ori.w #1)             */
#define WIN_OWNER             2          /* long: the owning PD                 ($feb498)                      */
#define WIN_KIND              6          /* word: its gadgets                   ($feb4a2)                      */
#define WIN_CURR              16         /* words[4]: the current GRECT         ($feb51e adda +$2866)           */
#define WIN_PREV              24         /* words[4]: the previous one          ($feb508 +$286e)               */
#define WIN_FULL              32         /* words[4]: the full one              ($feb4f2 +$2876)               */
#define WIN_HSLIDE            40         /* word                                ($feb4ae)                      */
#define WIN_VSLIDE            42         /* word                                ($feb4aa)                      */
#define WIN_HSLSIZE           44         /* word                                ($feb4b8)                      */
#define WIN_VSLSIZE           46         /* word                                ($feb4b4)                      */
#define WIN_RLIST             48         /* long: its ORECT list, the visible rectangles ($fe5cc0 lea 48(a5)) */
#define WIN_IN_USE            1          /* ($feb49e ori.w #1)                                                 */
#define WIN_BROKEN            2          /* a rectangle was split               ($fe5cdc ori.w #2)             */

/* ---- LINE-F: how GEM calls itself ---------------------------------------------------------------------------
 * GEM's own code never `jsr`s an AES routine: every call is a `$F000|off` word, a Line-F EXCEPTION, whose handler
 * (vector $2c) finds the routine at `off` in the call table and jumps there; every Alcyon return is a `$F001|m`
 * word, whose handler restores the registers `m` names, `unlk a6` and `rts`. The handler runs from RAM: gemstart
 * Mallocs 100 bytes and copies it there ($fd9f2e, only if `$2c`'s top byte is non-zero), and on every return with
 * a non-empty mask it WRITES the mask into its own `movem` — `AES_LINEF_MASK_WORD`, a byte a C reconstruction
 * (whose calls are `jsr`) never writes. `test/aes.py` drops it by name (`LINE_F_MASK_WINDOW`). */
#define AES_LINEF_TABLE       0xfee900   /* the ROM call table, a longword each ($fee8d6 movea.l #)            */
#define AES_LINEF_TABLE_ENTRIES 658      /* $fee900..$fef347, to the first ROM word after it                   */
#define LINEF_RETURN_BIT      0x0001     /* a return, not a call                ($fee8c8 btst #0,d1)           */
#define LINEF_OFFSET_MASK     0x0fff     /* a call's byte offset into the table ($fee8d2 andi.w #$fff)         */
#define LINEF_REGISTER_BITS   0x0ffe     /* a return's register bits            ($fee8e2 andi.w #$ffe)         */
#define LINEF_MASK_SHIFT      2          /* ...moved to movem's mask            ($fee8e8 lsl.w #2)             */
#define LINEF_COPY_BYTES      100        /* gemstart's Malloc                   ($fd9f36 move.l #100)          */
#define LINEF_COPY_WORDS      50         /* ...and its copy: `dbf` from 49      ($fd9f46 move.w #49)           */
#define LINEF_MASK_OFFSET     0x36       /* the `movem`'s mask word, in the handler ($fee8f6 + 2 - $fee8c2)    */
/* Where THIS boot's Malloc put the copy — `$2c` in the snapshot, not a constant of the ROM — and so the word the
 * copy patches. `test_aes_door.py` pins both against the snapshot and the ROM handler. */
#define AES_LINEF_COPY        0xcc0e     /* bytes[LINEF_COPY_BYTES]: the RAM handler (the snapshot's $2c)      */
#define AES_LINEF_MASK_WORD   0xcc44     /* word: the last masked return's movem mask (AES_LINEF_COPY + $36)   */

#endif /* TOS102US_AES_AES_H */
