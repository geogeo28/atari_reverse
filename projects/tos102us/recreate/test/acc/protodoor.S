| THE PROTOTYPE TRAP DOOR — a HARNESS FIXTURE, never a shipped object (`test/aes_boot.py`, `with_the_prototype_door`).
|
| What the door TAKEOVER is proved with, on any blob, whether or not the blob links a trap door of its own: the ROM's
| `trap #2` handler and its exit (`$fe3ea6..$fe3f3d`) and aes_entry (`$fe65aa`) as the ROM spells them, their calls
| naming THE BLOB'S OWN entries. It is assembled at the address after the blob's last byte and linked against the
| blob's ELF (`--just-symbols`), so the five routines below are the blob's — the interrupt-mask brackets of its
| `switch.S`, its marshal and its dsptch — and the bytes appended to the blob's image are a labelled extension of a
| BUILD (as `test_aes_boot.storing_into_itself`'s are), handed to the takeover as a door: a parameter.
|
| NOT THE SHIPPED DOOR: that is `src/aes/trapdoor.S` (band 5 wave 3, slice T), byte-pinned against the ROM by its own
| battery. Nothing here is pinned to the ROM's bytes or priced; the instructions are spelt as words so that the
| assembler chooses no encoding.
    .text
    .globl  proto_trap2, proto_trap2_exit, proto_aes_entry

proto_trap2:                            | $fe3ea6
    .word   0x0c40, 0x0000              | cmpi.w #0,d0
    beq.s   pterm
    .word   0x0c40, 0x00c8              | cmpi.w #200,d0
    beq.s   aes_arm
    .word   0x0c40, 0x00c9              | cmpi.w #201,d0
    beq.s   aes_arm
    .word   0x2f39, 0x0000, 0x8c2a      | move.l $8c2a,-(sp): the VDI's entry...
    rts                                 | ...entered
pterm:
    .word   0x3f3c, 0x0000              | move.w #0,-(sp)
    .word   0x3f3c, 0x004c              | move.w #$4c,-(sp)
    trap    #1                          | Pterm(0): no return
aes_arm:
    .word   0x4eb9
    .long   aes_rom_spl7_save
    .word   0x4e68                      | move.l usp,a0
    .word   0x48e0, 0x7ffe              | movem.l d1-a6,-(a0)
    .word   0x4e60                      | move.l a0,usp
    .word   0x2c79, 0x0000, 0xc794      | movea.l $c794,a6: the running PD
    .word   0x2c6e, 0x0008              | movea.l 8(a6),a6: its UDA
    .word   0x3cbc, 0x0001              | move.w #1,(a6): in supervisor
    .word   0x2d48, 0x0042              | move.l a0,66(a6)
    .word   0x2d4f, 0x0046              | move.l sp,70(a6)
    .word   0x2e6e, 0x003e              | movea.l 62(a6),sp: the process's own stack
    .word   0x4eb9
    .long   aes_rom_spl_restore
    .word   0x2f01                      | move.l d1,-(sp): the parameter block
    .word   0x3f3c, 0x0000              | move.w #0,-(sp)
    .word   0x3f00                      | move.w d0,-(sp): the selector
    .word   0x207c
    .long   proto_aes_entry             | movea.l #aes_entry,a0
    .word   0x4e90                      | jsr (a0)
proto_trap2_exit:                       | $fe3f08
    .word   0x302f, 0x0004              | move.w 4(sp),d0
    .word   0x4eb9
    .long   aes_rom_spl7_save
    .word   0xdffc, 0x0000, 0x0018      | adda.l #24,sp: aes_entry's Alcyon frame and the three pushed above
    .word   0x2079, 0x0000, 0xc794      | movea.l $c794,a0
    .word   0x2068, 0x0008              | movea.l 8(a0),a0
    .word   0x4250                      | clr.w (a0): out of supervisor
    .word   0x214f, 0x003e              | move.l sp,62(a0)
    .word   0x2e68, 0x0046              | movea.l 70(a0),sp
    .word   0x2068, 0x0042              | movea.l 66(a0),a0
    .word   0x4cd8, 0x7ffe              | movem.l (a0)+,d1-a6
    .word   0x4e60                      | move.l a0,usp
    .word   0x4eb9
    .long   aes_rom_spl_restore
    rte

proto_aes_entry:                        | $fe65aa, its three Line-F call words `jsr`s
    .word   0x4e56, 0xfffc              | link a6,#-4
    .word   0x0c6e, 0x00c8, 0x0008      | cmpi.w #200,8(a6)
    bne.s   1f
    .word   0x2eae, 0x000c              | move.l 12(a6),(sp)
    .word   0x4eb9
    .long   marshal_as_alcyon_calls_it
1:  .word   0x4eb9
    .long   aes_dsptch
    .word   0x4257                      | clr.w (sp)
    .word   0x4eb9
    .long   proto_trap2_exit

marshal_as_alcyon_calls_it:             | Alcyon's one longword -> aes_marshal(the image: none, the parameter block)
    move.l  4(%sp),-(%sp)
    pea     (0).w
    jsr     aes_marshal
    addq.l  #8,%sp
    rts
