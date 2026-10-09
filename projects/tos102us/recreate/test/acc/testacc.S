| testacc.S — THE TEST ACCESSORY the accessory machine loads twice (`test/aes_boot.py`): a real GEM desk accessory,
| loaded by the ROM's own loader off drive A:, that does appl_init and then waits for ever in an event wait.
|
| WHAT IT DOES IS A WORD OF ITS OWN TEXT (`acc_mode`, at ACC_MODE_AT), so one build is every accessory the harness
| needs: the file's bytes are patched as they are laid on the disk, never rebuilt.
|   ACC_FIND   appl_find(acc_name) before the wait; the answer kept in `res_find`
|   ACC_WRITE  appl_write(to, 16, message) before the wait — `to` is what appl_find answered where ACC_FIND is set,
|              else `acc_write_to`; the answer kept in `res_write`
|   ACC_MULTI  the wait is a SIX-WAY evnt_multi (keyboard, button, two rectangles, message, timer) and not evnt_mesag
| Every answer the AES hands back is kept in DATA (`results`), which is how a test
| reads what a process the ROM ran really did: at the build's own symbol, off the TEXT base its basepage names.
|
| NO RELOCATION IS AVOIDED ON PURPOSE: the parameter block is absolute longwords, so the ROM's Pexec relocates this
| file as it does any program.

    AES_TRAP_SELECTOR = 0xc8            | d0 of `trap #2`: an AES call (0x73 is the VDI's)

    APPL_INIT  = 10
    APPL_WRITE = 12
    APPL_FIND  = 13
    EVNT_MESAG = 23
    EVNT_MULTI = 25

    ACC_FIND  = 1
    ACC_WRITE = 2
    ACC_MULTI = 4

    MU_EVERY_KIND = 0x3f                | MU_KEYBD | MU_BUTTON | MU_M1 | MU_M2 | MU_MESAG | MU_TIMER
    MESSAGE_BYTES = 16
    STACK_BYTES   = 0x200

    .text
    .globl  _start
_start:
    bra.s   begin
    .globl  acc_mode, acc_timer, acc_write_to, acc_name
acc_mode:                               | ACC_MODE_AT = 2
    .word   0
acc_timer:                              | the six-way wait's timer, milliseconds: low word, high word (evnt_multi's order)
    .word   0xffff, 0x7fff
acc_write_to:                           | appl_write's target where ACC_FIND is clear
    .word   0
acc_name:                               | appl_find's name: eight characters, blank-padded, NUL-ended
    .ascii  "TESTACC2"
    .byte   0, 0

begin:
    lea     stack_top, %sp

    | appl_init() -> our id
    lea     control, %a0
    move.w  #APPL_INIT, (%a0)+
    clr.w   (%a0)+                      | no intin
    move.w  #1, (%a0)+
    clr.w   (%a0)+
    clr.w   (%a0)
    bsr     aes
    move.w  intout, res_id

    btst    #0, acc_mode+1              | ACC_FIND
    beq.s   find_done
    lea     control, %a0
    move.w  #APPL_FIND, (%a0)+
    clr.w   (%a0)+
    move.w  #1, (%a0)+
    move.w  #1, (%a0)+
    clr.w   (%a0)
    move.l  #acc_name, addrin
    bsr     aes
    move.w  intout, res_find
    move.w  intout, acc_write_to
find_done:

    btst    #1, acc_mode+1              | ACC_WRITE
    beq.s   write_done
    move.w  res_id, sent+2              | word 1 of a message: who sent it
    lea     control, %a0
    move.w  #APPL_WRITE, (%a0)+
    move.w  #2, (%a0)+
    move.w  #1, (%a0)+
    move.w  #1, (%a0)+
    clr.w   (%a0)
    move.w  acc_write_to, intin
    move.w  #MESSAGE_BYTES, intin+2
    move.l  #sent, addrin
    bsr     aes
    move.w  intout, res_write
write_done:

wait:
    move.l  #received, addrin
    btst    #2, acc_mode+1              | ACC_MULTI
    bne.s   wait_six_ways
    lea     control, %a0
    move.w  #EVNT_MESAG, (%a0)+
    clr.w   (%a0)+
    move.w  #1, (%a0)+
    move.w  #1, (%a0)+
    clr.w   (%a0)
    bra.s   waited
wait_six_ways:
    lea     control, %a0
    move.w  #EVNT_MULTI, (%a0)+
    move.w  #16, (%a0)+
    move.w  #7, (%a0)+
    move.w  #1, (%a0)+
    clr.w   (%a0)
    lea     intin, %a0
    move.w  #MU_EVERY_KIND, (%a0)+
    move.w  #1, (%a0)+                  | one click
    move.w  #1, (%a0)+                  | of the left button
    move.w  #1, (%a0)+                  | going down
    moveq   #1, %d0                     | the two rectangles: LEAVING one pixel the pointer is not on never happens
    bsr.s   far_pixel
    moveq   #1, %d0
    bsr.s   far_pixel
    move.w  acc_timer, (%a0)+
    move.w  acc_timer+2, (%a0)
waited:
    bsr.s   aes
    move.w  intout, res_events
    addq.w  #1, res_wakes
    bra.s   wait

| A rectangle watch nothing satisfies, laid at (a0)+: d0 = 0 to wait for the pointer to ENTER the far corner's pixel.
far_pixel:
    clr.w   (%a0)+                      | flag 0: return on ENTRY
    move.w  #0x7ffe, (%a0)+             | x: off every screen
    move.w  #0x7ffe, (%a0)+
    move.w  #1, (%a0)+
    move.w  #1, (%a0)+
    rts

aes:
    move.l  #aespb, %d1
    move.w  #AES_TRAP_SELECTOR, %d0
    trap    #2
    rts

    .data
    .globl  results
results:
res_id:     .word   0xffff              | appl_init's answer
res_find:   .word   0xfffe              | appl_find's
res_write:  .word   0xfffe              | appl_write's
res_events: .word   0                   | the last wait's answer
res_wakes:  .word   0                   | how many waits came back
aespb:
    .long   control, global, intin, intout, addrin, addrout
sent:                                   | the message ACC_WRITE sends: a type no GEM component names, the sender, no extra bytes
    .word   0x5a41, 0, 0, 0x1111, 0x2222, 0x3333, 0x4444, 0x5555

    .bss
control:    .space  5 * 2
global:     .space  15 * 2
intin:      .space  16 * 2
intout:     .space  7 * 2
addrin:     .space  2 * 4
addrout:    .space  1 * 4
received:   .space  MESSAGE_BYTES
            .space  STACK_BYTES
stack_top:
