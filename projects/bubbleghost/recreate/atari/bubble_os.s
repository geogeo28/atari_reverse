| bubble_os.s — the trap wrappers, the two exception entries and the supervisor gate.
|
| NONE OF THIS IS EXERCISED BY THE DIFFERENTIAL. The oracle services traps in-process and runs no
| interrupt at all, so every routine here is uncovered by construction — docs/on-target-execution.md
| class 3, which is written from a wrapper that read the wrong half of a stack slot and made a whole
| input feature silently inert. Two rules follow, and `build.sh` measures the second one:
|
|   * A `short` ARGUMENT IS THE LOW WORD OF A 4-BYTE SLOT. The m68k SysV ABI passes every scalar in
|     a longword slot, so on this big-endian machine `4(%sp)` is the HIGH half and always zero.
|     Every wrapper below reads the whole longword and pushes `%dn` as a word.
|
|   * EVERY ROUTINE THAT TRAPS SAVES %d2 AND %a2. GCC treats %d2-%d7/%a2-%a6 as callee-saved and
|     caches live values there across a call; TOS preserves only %d3-%d7/%a3-%a6. So %d2/%a2 are
|     exactly the pair the compiler expects to survive and TOS may destroy, and the fault surfaces
|     in the CALLER, on hardware, long after the wrapper returned. `tools/assert_trap_registers.sh`
|     is the scan that keeps this true; it runs on every build and asserts the COUNT of wrappers it
|     evaluated, so a rotted pattern reds rather than passing vacuously. Note the argument offsets
|     move with the save: the first argument is at 12(%sp), not 4(%sp).
|
| THE `Mshrink` IS HERE, AND IT IS NOT BOOKKEEPING. GEMDOS hands a .PRG the WHOLE TPA and expects
| the program to give back what it does not need; this one's `.bss` is a 664 KB image, so without the
| shrink it owns every free byte of a 1 MB machine. That is invisible until something else asks TOS
| for memory — and on this program the something else is TOS'S OWN VDI: `v_opnvwk` allocates its
| virtual workstation with GEMDOS `Malloc` (0x134 bytes, from ROM PC $fd0622), gets 0, and answers
| HANDLE 0. Every later VDI call carries that handle and draws nothing at all, so the menu's four
| text lines, the HUD and every sprite blit are silently absent while the AES, the file I/O, the
| sound and the reconstruction's own raw blitters all work perfectly. Measured 2026-09-06: with no
| shrink the workstation handle is 0 and the visible screen stays black; the ORIGINAL, whose Alcyon
| crt0 shrinks to text+data+bss+0x2100, gets handle 2 under the same TOS and the same emulator.
|
| `../src/init.c`'s `crt0_relocate_and_clear` reproduces the shrink's ARITHMETIC and not the call —
| the model answers 0 and touches nothing — so this is the one part of the original's startup that a
| target build owes in assembly rather than in a verified core.
|
| The stack moves FIRST and the shrink follows, because the block being given back is the one the
| stack GEMDOS gave us stands in.

    STACK_RESERVE   = 32768         | what is kept above the program for the C stack. ONE DEFINITION
                                    | ACROSS THE LANGUAGE BOUNDARY (CLAUDE.md §5): build.sh's
                                    | STACK_RESERVE_BYTES is the same number and build.sh asserts
                                    | the two are equal, because the size gate weighs the .PRG
                                    | against a budget this reserve is subtracted from.
    BASEPAGE_BYTES  = 0x100         | GEMDOS puts the basepage immediately below p_tbase
    BP_TLEN         = 12            | the basepage's own segment lengths
    BP_DLEN         = 20
    BP_BLEN         = 28

    .text
    .globl  _start
_start:
    movea.l 4(%sp),%a0              | GEMDOS's basepage
    move.l  %a0,bg_basepage         | ...for the memory budget the record publishes
    move.l  %sp,bg_initial_sp       | ...and the stack it entered on, which is the TPA's ceiling

    move.l  BP_TLEN(%a0),%d0        | keep = basepage + text + data + bss + the stack reserve
    add.l   BP_DLEN(%a0),%d0
    add.l   BP_BLEN(%a0),%d0
    add.l   #BASEPAGE_BYTES+STACK_RESERVE,%d0
    move.l  %a0,%d1
    add.l   %d0,%d1
    andi.l  #-4,%d1                 | the 68000 wants the stack pointer aligned
    move.l  %d1,bg_kept_top         | what the record publishes as the new ceiling
    movea.l %d1,%sp                 | ...and the stack is inside the kept block from here on

    move.l  %d0,-(%sp)              | Mshrink(0, basepage, keep)
    move.l  %a0,-(%sp)
    clr.w   -(%sp)
    move.w  #0x4a,-(%sp)
    trap    #1
    lea     12(%sp),%sp
    move.l  %d0,bg_mshrink_result   | 0 = accepted; a record field, because a refused shrink is the
                                    | shape that leaves the VDI with no memory and no complaint

    jsr     bubble_main             | user mode, and it stays that way: see shim_include/tos.h
    clr.w   -(%sp)                  | Pterm0 (GEMDOS 0x00): terminate with status 0
    trap    #1

| ---- GEMDOS (trap #1) -------------------------------------------------------------------------
| THE FILE-I/O WRAPPERS COME FIRST, right after `_start`, and the order is not cosmetic: it matches
| the proven BuggyBoy, Joust, Wonder Boy and Zynaps layout. With the GEMDOS control wrappers
| (`Super`, `Pterm`) placed before them, Hatari's GEMDOS-HD hands back HANDLE 0 — stdin — from
| `Fopen`, and a program that then reads it waits on the keyboard for ever or discards what it
| writes (the memory of it is `buggyboy-prg-fopen-handle0-bug`). Nothing in this build has ever
| exhibited it and nothing here explains WHY the order matters; what is known is that four builds in
| this workspace hit it and the layout below is the one that does not. Keep the order.
|
| Each label carries the GEMDOS function number the wrapper pushes, so the file can be read against
| `shim_include/tos.h`'s declarations without counting `move.w` immediates.

    .globl  Fcreate
Fcreate:                       | GEMDOS 0x3c
    movem.l %d2/%a2,-(%sp)          | TOS traps may trash d2/a2 — see the register note above
    move.l  12(%sp),%d1             | name
    move.l  16(%sp),%d0             | attr (int); the value is the LOW word of the slot
    move.w  %d0,-(%sp)
    move.l  %d1,-(%sp)
    move.w  #0x3c,-(%sp)
    trap    #1
    lea     8(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Fopen
Fopen:                         | GEMDOS 0x3d
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d1             | name
    move.l  16(%sp),%d0             | mode
    move.w  %d0,-(%sp)
    move.l  %d1,-(%sp)
    move.w  #0x3d,-(%sp)
    trap    #1
    lea     8(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Fclose
Fclose:                        | GEMDOS 0x3e
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #0x3e,-(%sp)
    trap    #1
    addq.l  #4,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Fread
Fread:                         | GEMDOS 0x3f
    movem.l %d2/%a2,-(%sp)
    move.l  20(%sp),%a1             | buf
    move.l  16(%sp),%d1             | count
    move.l  12(%sp),%d0             | handle
    move.l  %a1,-(%sp)
    move.l  %d1,-(%sp)
    move.w  %d0,-(%sp)
    move.w  #0x3f,-(%sp)
    trap    #1
    lea     12(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Fwrite
Fwrite:                        | GEMDOS 0x40
    movem.l %d2/%a2,-(%sp)
    move.l  20(%sp),%a1             | buf
    move.l  16(%sp),%d1             | count
    move.l  12(%sp),%d0             | handle
    move.l  %a1,-(%sp)
    move.l  %d1,-(%sp)
    move.w  %d0,-(%sp)
    move.w  #0x40,-(%sp)
    trap    #1
    lea     12(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Fdelete
Fdelete:                       | GEMDOS 0x41
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)          | name
    move.w  #0x41,-(%sp)
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| Fseek(offset, handle, mode) — the stack the trap reads is opcode.w, offset.l, handle.w, mode.w,
| so the pushes run the other way round.
    .globl  Fseek
Fseek:                         | GEMDOS 0x42
    movem.l %d2/%a2,-(%sp)
    move.l  20(%sp),%d0             | mode
    move.l  16(%sp),%d1             | handle
    move.l  12(%sp),%a1             | offset
    move.w  %d0,-(%sp)
    move.w  %d1,-(%sp)
    move.l  %a1,-(%sp)
    move.w  #0x42,-(%sp)
    trap    #1
    lea     10(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Cconout
Cconout:                       | GEMDOS 0x02
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #0x02,-(%sp)
    trap    #1
    addq.l  #4,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Cauxout
Cauxout:                       | GEMDOS 0x04
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #0x04,-(%sp)
    trap    #1
    addq.l  #4,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Cprnout
Cprnout:                       | GEMDOS 0x05
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #0x05,-(%sp)
    trap    #1
    addq.l  #4,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Crawio
Crawio:                        | GEMDOS 0x06
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #0x06,-(%sp)
    trap    #1
    addq.l  #4,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Crawcin
Crawcin:                       | GEMDOS 0x07
    movem.l %d2/%a2,-(%sp)
    move.w  #0x07,-(%sp)
    trap    #1
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Cnecin
Cnecin:                        | GEMDOS 0x08
    movem.l %d2/%a2,-(%sp)
    move.w  #0x08,-(%sp)
    trap    #1
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Cconis
Cconis:                        | GEMDOS 0x0b
    movem.l %d2/%a2,-(%sp)
    move.w  #0x0b,-(%sp)
    trap    #1
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Super
Super:                         | GEMDOS 0x20
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)
    move.w  #0x20,-(%sp)
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| The RETURN half of Super, and it is not the same routine — docs/on-target-execution.md class 9.
| TOS goes back to user mode on the USP as it stood when `Super(0)` ran, and does not reload it from
| the supervisor stack, so a plain `Super(ssp)` is correct only while the compiler happens to have
| left %sp at the same depth at both call sites. Planting the USP one instruction before the trap
| makes the value TOS returns on the one this routine chose.
    .globl  bg_leave_supervisor
bg_leave_supervisor:           | GEMDOS 0x20
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)          | the SSP the entering Super(0) handed back
    move.w  #0x20,-(%sp)
    move.l  %sp,%a0
    move.l  %a0,%usp                | ...so the return lands %a7 exactly here, whatever GCC did
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| Pterm does not return, so there is nothing to restore and nothing for the register rule to
| protect; the save is kept anyway so that the scan sees one shape in this file rather than two.
    .globl  Pterm
Pterm:                         | GEMDOS 0x4c
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #0x4c,-(%sp)
    trap    #1
    addq.l  #4,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| ---- BIOS (trap #13) ---------------------------------------------------------------------------

    .globl  Bconout
Bconout:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0             | dev
    move.l  16(%sp),%d1             | ch
    move.w  %d1,-(%sp)
    move.w  %d0,-(%sp)
    move.w  #0x03,-(%sp)
    trap    #13
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| ---- XBIOS (trap #14) --------------------------------------------------------------------------

    .globl  Physbase
Physbase:
    movem.l %d2/%a2,-(%sp)
    move.w  #2,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Logbase
Logbase:
    movem.l %d2/%a2,-(%sp)
    move.w  #3,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Getrez
Getrez:
    movem.l %d2/%a2,-(%sp)
    move.w  #4,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Setscreen
Setscreen:
    movem.l %d2/%a2,-(%sp)
    move.l  20(%sp),%d0             | rez (int); the value is the LOW word of the slot
    move.l  16(%sp),%d1             | phys
    move.l  12(%sp),%a1             | log
    move.w  %d0,-(%sp)
    move.l  %d1,-(%sp)
    move.l  %a1,-(%sp)
    move.w  #5,-(%sp)
    trap    #14
    lea     12(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Setpalette
Setpalette:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)          | the sixteen words
    move.w  #6,-(%sp)
    trap    #14
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Setcolor
Setcolor:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0             | index
    move.l  16(%sp),%d1             | value
    move.w  %d1,-(%sp)
    move.w  %d0,-(%sp)
    move.w  #7,-(%sp)
    trap    #14
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Random
Random:
    movem.l %d2/%a2,-(%sp)
    move.w  #0x11,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Vsync
Vsync:
    movem.l %d2/%a2,-(%sp)
    move.w  #0x25,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Supexec
Supexec:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)          | the routine, which TOS calls in supervisor mode
    move.w  #0x26,-(%sp)
    trap    #14
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| ---- GEM (trap #2) -----------------------------------------------------------------------------
| The game's own two bindings, `gem_aes` @ 0x149b6 and `vdi_call` @ 0x168d4, are this instruction
| with `d0` = 0xc8 or 0x73 and `d1` = the parameter block. What has to happen to the block before it
| is handed over is shim_include/os.h's and bubble_backend.c's, not this file's.
    .globl  bg_gem_trap
bg_gem_trap:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0             | selector
    move.l  16(%sp),%d1             | the parameter block, as a MACHINE address
    trap    #2
    movem.l (%sp)+,%d2/%a2
    rts

| ---- the trap #9 supervisor gate ---------------------------------------------------------------
| The user-mode half. Three arguments in the registers the handler reads, exactly as the original's
| `psg_access` @ 0x14940 puts its three argument words in d1/d0/d2 before its own `trap #9`.
|
| %d2 IS AN ARGUMENT REGISTER HERE, and it is saved as half of the pair anyway. The handler below is
| OURS and clobbers neither %a2 nor %d2 beyond the argument it was handed — so the save could be
| %d2 alone — but `assert_trap_registers.sh` reads the SOURCE and cannot know whose handler is on the
| vector. One shape for every routine in this file is worth eight bytes: an exception list is how a
| scan stops seeing the wrapper that really did need the pair.
    .globl  bg_super_gate
bg_super_gate:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0             | operation
    move.l  16(%sp),%d1             | register number, or the address for a byte store
    move.l  20(%sp),%d2             | value
    trap    #9
    movem.l (%sp)+,%d2/%a2
    rts

    | The gate's three operations. THE NUMBERS ARE shim_include/tos.h's — `BG_GATE_PSG_WRITE`,
    | `BG_GATE_PSG_READ` and `BG_GATE_STORE8` — and build.sh asserts the two spellings agree, because
    | a caller and a handler that disagree about which operation is 2 would store a register number
    | to an address (CLAUDE.md §5).
    GATE_PSG_WRITE = 0
    GATE_PSG_READ  = 1
    GATE_STORE8    = 2

    IPL7          = 0x0700          | interrupt priority mask, all levels off
    PSG_SELECT    = 0xffff8800      | write = select a register, read = read the selected one
    PSG_DATA      = 2               | ...and $ffff8802 is where a write's data goes
    PSG_REG_MASK  = 15              | the select latch decodes four bits; `and.b #$f,d1` @ 0x1495c
    BUS_HIGH_BYTE = 0xff000000      | 24-bit bus form -> the address a 68020 would also decode

| The supervisor half, on the vector at $a4. IT RAISES TO IPL 7 ACROSS THE PAIR, exactly as the
| original's handler does: the 200 Hz Timer C interrupt drives the same chip, and one landing
| between a register select and its data write would send the data to whichever register the
| handler selected last. The `rte` puts the mask back, so nothing here restores it by hand.
|
| d0/d1/d2 are this call's own arguments and may be clobbered; %a0 is not, and is saved.
    .globl  bg_super_gate_entry
bg_super_gate_entry:
    ori.w   #IPL7,%sr
    move.l  %a0,-(%sp)
    cmpi.l  #GATE_STORE8,%d0
    bne     1f
    ori.l   #BUS_HIGH_BYTE,%d1
    movea.l %d1,%a0
    move.b  %d2,(%a0)
    bra     9f
1:  lea     PSG_SELECT,%a0
    andi.l  #PSG_REG_MASK,%d1
    move.b  %d1,(%a0)
    tst.l   %d0                     | GATE_PSG_WRITE is 0; anything else is the read
    bne     2f
    move.b  %d2,PSG_DATA(%a0)
2:  moveq   #0,%d0
    move.b  (%a0),%d0               | the selected register, read back — the gate's answer
9:  movea.l (%sp)+,%a0
    rte

| ---- the same PSG write, WITHOUT the trap ------------------------------------------------------
| For a caller that is already supervisor with the MFP masked — which is the sound ISR and nothing
| else (shim_include/tos.h argues it, shim_include/psg.h's door decides it). The constants are the
| gate's own, ten lines up, so the two paths cannot drift apart in the address they write or the
| four bits they decode; what is missing here against the gate is only the `trap`, the IPL raise the
| caller already has, and the read-back no writer looks at.
    .globl  bg_psg_write_super
bg_psg_write_super:
    move.l  4(%sp),%d0              | the register number...
    move.l  8(%sp),%d1              | ...and the byte for it
    lea     PSG_SELECT,%a0
    andi.l  #PSG_REG_MASK,%d0
    move.b  %d0,(%a0)
    move.b  %d1,PSG_DATA(%a0)
    rts

| ---- the Timer C entry -------------------------------------------------------------------------
| IT DOES NOT `rte`, AND THAT IS THE ORIGINAL'S SHAPE. `timer_c_sound_isr` @ 0x1459a ends by pushing
| TOS's own saved $114 vector and `rts`ing, so the exception frame is left for TOS's handler to
| return from and the 200 Hz work TOS still wants done — the clock, the key repeat — still happens.
| `bubble_main.c` fills `bg_timer_c_chain` from the vector it read before the install, and asserts
| it against what the verified installer parked in the image.
    .globl  bg_timer_c_entry
bg_timer_c_entry:
    movem.l %d0-%d1/%a0-%a1,-(%sp)  | the caller-saved set; the C half preserves the rest
    jsr     bg_timer_c_tick         | bubble_main.c: bumps the count, runs the verified ISR
    movem.l (%sp)+,%d0-%d1/%a0-%a1
    move.l  bg_timer_c_chain,-(%sp)
    rts

| ---- machine primitives, all three supervisor-only and all three Supexec'd ----------------------

    .globl  bg_read_long
bg_read_long:
    movea.l 4(%sp),%a0
    move.l  (%a0),%d0
    rts

    .globl  bg_write_long
bg_write_long:
    movea.l 4(%sp),%a0
    move.l  8(%sp),(%a0)
    rts

    .globl  bg_write_byte
bg_write_byte:
    movea.l 4(%sp),%a0
    move.l  8(%sp),%d0
    move.b  %d0,(%a0)
    rts
