| testacc.S — THE TEST ACCESSORY the accessory machine loads twice (`test/aes_boot.py`): a real GEM desk accessory,
| loaded by the ROM's own loader off drive A:, that does appl_init and then waits for ever in an event wait.
|
| WHAT IT DOES IS TWO WORDS OF ITS OWN TEXT, SIDE BY SIDE (`acc_kind`, then `acc_mode`: one longword, the kind its high
| half), so one build is every accessory the harness needs: the file's bytes are patched as they are laid on the disk,
| never rebuilt.
|   ACC_FIND   appl_find(acc_name) before the wait; the answer kept in `res_find`
|   ACC_WRITE  appl_write(to, 16, message) before the wait — `to` is what appl_find answered where ACC_FIND is set,
|              else `acc_write_to`; the answer kept in `res_write`
|   ACC_MULTI  the wait is a SIX-WAY evnt_multi (keyboard, button, two rectangles, message, timer) and not evnt_mesag
|   ACC_REGISTER  menu_register(our id, acc_title) before the wait: an entry of the desk's own menu, which the screen
|              manager answers with AC_OPEN; the answer kept in `res_menu`
|   ACC_HIDE   after a wait that came back with AC_OPEN (its menu entry chosen) the accessory hides the menu bar,
|              menu_bar(0, 0), TWICE: the one way this machine comes to have NO menu while its screen manager
|              runs, and the menu bar's own click counted twice before the screen manager takes one
|   a WINDOW   `acc_kind` is a window's KIND, GEM's own gadget bits; where it is not 0 the accessory creates a window
|              of that kind, names it, gives its two sliders a size and a place, and opens it before the wait — at a
|              rectangle of its own by its id, so two accessories' windows overlap and each keeps its gadgets in
|              view; the handle kept in `res_window`. It answers no message: what the screen manager sends it for a
|              gadget is read and dropped (`res_wakes` counts them).
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
    MENU_REGISTER = 35
    WIND_CREATE = 100
    WIND_OPEN  = 101
    WIND_SET   = 105

    ACC_FIND  = 1
    ACC_WRITE = 2
    ACC_MULTI = 4
    ACC_REGISTER = 8
    ACC_HIDE  = 16
    AC_OPEN   = 40                      | the message an accessory's menu entry sends it
    MENU_BAR  = 30

    WF_NAME = 2                         | wind_set's fields
    WF_INFO = 3
    WF_HSLIDE = 8
    WF_VSLIDE = 9
    WF_HSLSIZE = 15
    WF_VSLSIZE = 16
    SLIDER_SIZE = 300                   | of 1000: an elevator a third of its bar, so it has somewhere to be dragged
    HSLIDER_AT = 400                    | ...and where each stands, of 1000
    VSLIDER_AT = 600
    FIRST_ACCESSORY_ID = 2              | the pid appl_init answers the first accessory (the spare static PD's)
    WINDOW_X = 8                        | the first accessory's window, in low resolution's pixels...
    WINDOW_Y = 24
    WINDOW_W = 152
    WINDOW_H = 90
    WINDOW_STEP_X = 96                  | ...and how far right and down the next accessory's lies
    WINDOW_STEP_Y = 48
    FULL_X = 0                          | the largest a window may grow to: the desk's work area in low resolution
    FULL_Y = 11
    FULL_W = 320
    FULL_H = 189

    MU_EVERY_KIND = 0x3f                | MU_KEYBD | MU_BUTTON | MU_M1 | MU_M2 | MU_MESAG | MU_TIMER
    MESSAGE_BYTES = 16
    STACK_BYTES   = 0x200

    .text
    .globl  _start
_start:
    bra.s   begin
    .globl  acc_kind, acc_mode, acc_timer, acc_write_to, acc_name
acc_kind:                               | a window's kind, 0 for no window: the mode longword's high half
    .word   0
acc_mode:
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

    btst    #3, acc_mode+1              | ACC_REGISTER
    beq.s   register_done
    lea     control, %a0
    move.w  #MENU_REGISTER, (%a0)+
    move.w  #1, (%a0)+
    move.w  #1, (%a0)+
    move.w  #1, (%a0)+
    clr.w   (%a0)
    move.w  res_id, intin
    move.l  #acc_title, addrin
    bsr     aes
    move.w  intout, res_menu
register_done:

    move.w  acc_kind, %d0
    beq     window_done
    bsr     open_a_window
window_done:

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
    bsr     far_pixel
    moveq   #1, %d0
    bsr     far_pixel
    move.w  acc_timer, (%a0)+
    move.w  acc_timer+2, (%a0)
waited:
    bsr     aes
    move.w  intout, res_events
    addq.w  #1, res_wakes
    btst    #4, acc_mode+1              | ACC_HIDE
    beq     wait
    cmpi.w  #AC_OPEN, received
    bne     wait
    lea     control, %a0                | menu_bar(0, 0)
    move.w  #MENU_BAR, (%a0)+
    move.w  #1, (%a0)+
    move.w  #1, (%a0)+
    move.w  #1, (%a0)+
    clr.w   (%a0)
    clr.w   intin
    clr.l   addrin
    bsr     aes
    bsr     aes                         | ...again: the same call, its arrays as they stand
    bra     wait

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

| A window of the kind in d0, created, named, its sliders set, and opened (the header's note).
open_a_window:
    lea     control, %a0
    move.w  #WIND_CREATE, (%a0)+
    move.w  #5, (%a0)+
    move.w  #1, (%a0)+
    clr.w   (%a0)+
    clr.w   (%a0)
    lea     intin, %a0
    move.w  %d0, (%a0)+
    move.w  #FULL_X, (%a0)+
    move.w  #FULL_Y, (%a0)+
    move.w  #FULL_W, (%a0)+
    move.w  #FULL_H, (%a0)
    bsr     aes
    move.w  intout, res_window
    bmi     window_refused              | every window in use: nothing to name or open

    moveq   #WF_NAME, %d0
    move.l  #window_name, %d1
    bsr     set_window
    moveq   #WF_INFO, %d0
    move.l  #window_info, %d1
    bsr     set_window
    moveq   #WF_HSLSIZE, %d0
    move.l  #SLIDER_SIZE << 16, %d1
    bsr     set_window
    moveq   #WF_VSLSIZE, %d0
    move.l  #SLIDER_SIZE << 16, %d1
    bsr     set_window
    moveq   #WF_HSLIDE, %d0
    move.l  #HSLIDER_AT << 16, %d1
    bsr     set_window
    moveq   #WF_VSLIDE, %d0
    move.l  #VSLIDER_AT << 16, %d1
    bsr     set_window

    lea     control, %a0
    move.w  #WIND_OPEN, (%a0)+
    move.w  #5, (%a0)+
    move.w  #1, (%a0)+
    clr.w   (%a0)+
    clr.w   (%a0)
    move.w  res_id, %d0                 | the rectangle: a step right and down for each accessory after the first
    subq.w  #FIRST_ACCESSORY_ID, %d0
    move.w  %d0, %d1
    mulu.w  #WINDOW_STEP_X, %d0
    mulu.w  #WINDOW_STEP_Y, %d1
    lea     intin, %a0
    move.w  res_window, (%a0)+
    add.w   #WINDOW_X, %d0
    move.w  %d0, (%a0)+
    add.w   #WINDOW_Y, %d1
    move.w  %d1, (%a0)+
    move.w  #WINDOW_W, (%a0)+
    move.w  #WINDOW_H, (%a0)
    bsr     aes
    move.w  intout, res_opened
window_refused:
    rts

| wind_set(res_window, d0, d1's high word, d1's low word): a field given two words — a slider's place and nothing, or
| the two halves of a text's address.
set_window:
    lea     control, %a0
    move.w  #WIND_SET, (%a0)+
    move.w  #6, (%a0)+
    move.w  #1, (%a0)+
    clr.w   (%a0)+
    clr.w   (%a0)
    lea     intin, %a0
    move.w  res_window, (%a0)+
    move.w  %d0, (%a0)+
    move.l  %d1, (%a0)+
    clr.l   (%a0)
    bra     aes

    .data
    .globl  results
results:
res_id:     .word   0xffff              | appl_init's answer
res_find:   .word   0xfffe              | appl_find's
res_write:  .word   0xfffe              | appl_write's
res_events: .word   0                   | the last wait's answer
res_wakes:  .word   0                   | how many waits came back
res_menu:   .word   0xfffe              | menu_register's answer: our entry's index among the accessories'
res_window: .word   0xfffe              | wind_create's: the window's handle
res_opened: .word   0xfffe              | wind_open's
aespb:
    .long   control, global, intin, intout, addrin, addrout
sent:                                   | the message ACC_WRITE sends: a type no GEM component names, the sender, no extra bytes
    .word   0x5a41, 0, 0, 0x1111, 0x2222, 0x3333, 0x4444, 0x5555
acc_title:  .asciz  "  Test accessory"  | the desk menu's entry: two blanks, as an accessory's own is written
window_name: .asciz " TESTACC "
window_info: .asciz " a window of the test accessory"
    .even

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
