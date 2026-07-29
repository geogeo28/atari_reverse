| crash.S — 68000 exception catcher for the GAME_CRASH_REPORT diagnostic build (build_game.sh).
|
| These stubs take the FAULT vectors, snapshot the 68000 exception frame, and hand it to crash_report()
| (game_main.c). Why the build exists at all, and how to read what it prints, is in render/atari/README.md
| ("Diagnosing a crash on real hardware") — the one place that story is told.
|
| WHICH VECTORS. Only the seven that mean "this program did something wrong": 2 bus error, 3 address
| error, 4 illegal instruction, 5 divide by zero, 6 CHK, 7 TRAPV, 8 privilege violation. Deliberately NOT
| taken:
|   * 9 (trace) — nothing here sets the trace bit, and a debugger attached to the machine wants it.
|   * 10 / 11 (line-A / line-F) — on the Atari these are not faults at all. `$Axxx` is the documented
|     Line-A graphics API that the VDI, the mouse cursor, desk accessories and resident drivers execute
|     ON PURPOSE, and TOS's vector 10 is its dispatcher. Taking it would report a healthy machine as a
|     crash and, worse, would leave the desktop's Line-A entry pointing into this program's freed TPA
|     once it exits — killing the machine on the next redraw. An illegal instruction (4) already catches
|     the "jumped into data" landing these two would otherwise cover.
|
| FRAME LAYOUT differs by exception GROUP (68000 UM section 6.4), which is why there are two paths:
|   group 0 (vectors 2, 3): SSW.w  access-address.l  instruction-register.w  SR.w  PC.l   = 14 bytes
|   group 1/2 (vectors 4-8): SR.w  PC.l                                                   =  6 bytes
| A group-0 PC is only APPROXIMATE (the 68000 may have advanced 1-5 words past the faulting instruction)
| — the recorded opcode word is the tie-breaker when mapping it back to a source line.
|
| Each stub masks interrupts before touching anything: the VBL sound pump and the IKBD handler are still
| installed here, and letting either re-enter over a half-taken snapshot would report the wrong fault.
| crash_report() detaches both before it re-enables them (it needs the OS to print).
|
| ALL of the reporter's storage lives in this file's .bss, not in game_main.o's, and this file links LAST.
| That does NOT keep other globals at their shipping ADDRESSES — the reporter's own code grows .text, and
| .bss follows .text, so the whole block shifts (measured: +0x1a00 for every global). What it preserves is
| the shift's EVENNESS: no odd-sized object is inserted ahead of anything, so every global keeps its
| odd/even parity and its alignment relative to its neighbours. That is the property this build must not
| disturb, because the fault it exists to chase is an ADDRESS error — a diagnostic that re-parities the
| program's globals could move or hide the very bug it is hunting.
| Corollary for whoever reads a report: resolve TEXT+ / A0-A6 / FAULT against the build/game.elf of THIS
| build, never the shipping one — the two have different symbol addresses.

    .equ    SR_MASK_ALL,       0x2700   | supervisor, every interrupt masked
    .equ    G0_SSW,            0        | group-0 frame: special status word
    .equ    G0_FAULT_ADDR,     2        |   ... the address the faulting access used
    .equ    G0_OPCODE,         6        |   ... instruction register (the faulting opcode word)
    .equ    G0_SR,             8
    .equ    G0_PC,             10
    .equ    G12_SR,            0        | group-1/2 frame: SR then PC, no address and no opcode
    .equ    G12_PC,            2
    .equ    CRASH_STACK_BYTES, 2048     | crash_report's private stack (see crash_enter)
    .equ    CRASH_TEXT_BYTES,  512      | the report crash_report formats; sized in game_main.c's terms
    .equ    CRASH_VECTOR_SLOTS, 7       | vectors 2..8: one saved TOS vector each, restored on exit
    .equ    CRASH_REG_COUNT,   15       | D0-D7 + A0-A6, the movem set captured at the fault

    .text

| Each stub records its vector with an immediate-to-memory store rather than via a register, so the
| register file below is captured EXACTLY as the faulting instruction left it.
| ---- group 0: the two faults that produce a 14-byte frame -----------------------------------------
    .globl  crash_stub_2
crash_stub_2:                       | bus error (2 bombs) — e.g. a user-mode touch of an I/O register
    move.w  #2,crash_vector
    bra.s   crash_group0
    .globl  crash_stub_3
crash_stub_3:                       | address error (3 bombs) — a word/long access on an ODD address
    move.w  #3,crash_vector
crash_group0:
    move.w  #SR_MASK_ALL,%sr        | freeze the pump + IKBD handler before the snapshot
    movem.l %d0-%d7/%a0-%a6,crash_regs
    move.l  %usp,%a0                | the faulting code's own stack, when it faulted in USER mode
    move.l  %a0,crash_usp
    move.w  G0_SSW(%sp),crash_ssw
    move.l  G0_FAULT_ADDR(%sp),crash_fault
    move.w  G0_OPCODE(%sp),crash_opcode
    move.w  G0_SR(%sp),crash_sr
    move.l  G0_PC(%sp),crash_pc
    bra.s   crash_enter

| ---- group 1/2: the rest, a 6-byte frame (no faulting address, no opcode) -------------------------
    .globl  crash_stub_4
crash_stub_4:                       | illegal instruction (4 bombs) — the usual "jumped into data" landing
    move.w  #4,crash_vector
    bra.s   crash_group1
    .globl  crash_stub_5
crash_stub_5:                       | divide by zero
    move.w  #5,crash_vector
    bra.s   crash_group1
    .globl  crash_stub_6
crash_stub_6:                       | CHK
    move.w  #6,crash_vector
    bra.s   crash_group1
    .globl  crash_stub_7
crash_stub_7:                       | TRAPV
    move.w  #7,crash_vector
    bra.s   crash_group1
    .globl  crash_stub_8
crash_stub_8:                       | privilege violation — a supervisor-only opcode run in user mode
    move.w  #8,crash_vector
crash_group1:
    move.w  #SR_MASK_ALL,%sr
    movem.l %d0-%d7/%a0-%a6,crash_regs
    move.l  %usp,%a0
    move.l  %a0,crash_usp
    clr.w   crash_ssw               | this frame shape carries no status word / fault address / opcode,
    clr.l   crash_fault             | so clear them rather than report a previous fault's values
    clr.w   crash_opcode
    move.w  G12_SR(%sp),crash_sr
    move.l  G12_PC(%sp),crash_pc

| Report on a private stack: the fault may itself have been a stack overrun, and TOS's supervisor stack
| has very little headroom for the GEMDOS calls crash_report makes.
crash_enter:
    lea     crash_stack_top,%sp
    jsr     crash_report            | prints and never returns; the halt below is belt-and-braces
crash_halt:
    bra.s   crash_halt

    .bss
    .align  2
| The snapshot and the reporter's buffers, read by crash_report(). Keep this block EVEN-sized: tos.ld
| packs .bss with SUBALIGN(1), so an odd size would shift anything linked after it onto odd addresses
| (see os.s's tail note) — the exact fault class this build hunts.
    .globl  crash_vector
crash_vector:
    .space  2                       | the exception vector number = TOS's bomb count
    .globl  crash_ssw
crash_ssw:
    .space  2                       | group-0 special status word (function code / read-write / in-out)
    .globl  crash_opcode
crash_opcode:
    .space  2                       | group-0 instruction register: the faulting opcode word
    .globl  crash_sr
crash_sr:
    .space  2                       | SR at the fault (bit 13 set = the fault happened in supervisor mode)
    .globl  crash_fault
crash_fault:
    .space  4                       | group-0 access address — the odd/illegal address that faulted
    .globl  crash_pc
crash_pc:
    .space  4                       | PC at the fault (group 0: approximate — see the header)
    .globl  crash_frames
crash_frames:
    .space  2                       | frames presented before the fault (game_main.c's CRASH_FRAME_TICK)
| The register file as the faulting instruction left it. The ADDRESS registers are what localise a bad
| pointer — the fault address alone says "something dereferenced garbage", A0-A6 say WHICH pointer — and
| crash_usp with the stack words below it give the faulting function's return address and arguments.
    .globl  crash_regs
crash_regs:
    .space  CRASH_REG_COUNT * 4     | D0-D7 then A0-A6, in movem order
    .globl  crash_usp
crash_usp:
    .space  4
| Both buffers export an _end label: game_main.c bounds its writes with those instead of restating the
| sizes on the C side, so there is no size constant to keep in sync across the asm/C boundary.
    .globl  crash_old_vectors
crash_old_vectors:
    .space  CRASH_VECTOR_SLOTS * 4  | the TOS vectors crash_install displaced, restored by crash_uninstall
    .globl  crash_old_vectors_end
crash_old_vectors_end:
    .globl  crash_text
crash_text:
    .space  CRASH_TEXT_BYTES        | the formatted report handed to Cconws
    .globl  crash_text_end
crash_text_end:
    .globl  crash_stage_id
crash_stage_id:
    .space  1                       | last boot milestone reached (game_main.c's CRASH_STAGE)
    .even                           | ... the one odd-sized field, so pad the block back to even
crash_stack:
    .space  CRASH_STACK_BYTES
crash_stack_top:
