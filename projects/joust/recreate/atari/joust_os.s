| joust_os.s — GEMDOS PRG entry, TOS trap wrappers and the IKBD joystick handler for JOUST.PRG.
|
| C ABI (m68k SysV): args at 4(%sp), 8(%sp), ...; every int/pointer occupies 4 bytes; result in %d0.
| Each wrapper cleans only its own trap-frame pushes; the caller cleans the C args.
|
| REGISTERS — the one place the two calling conventions DISAGREE:
|   GCC (m68k SysV): %d0/%d1/%a0/%a1 scratch; %d2-%d7 and %a2-%a6 CALLEE-SAVED, so the compiler
|                    caches live values in %d2/%a2 across a call to any wrapper here.
|   TOS (GEMDOS/BIOS/XBIOS): preserves only %d3-%d7 and %a3-%a6 — %d0-%d2 and %a0-%a2 are VOLATILE.
| So %d2/%a2 are exactly what GCC expects to survive and TOS may destroy. Every wrapper below saves
| and restores that pair around its trap (hence each reads its C arguments at +12, not +4). Skipping
| it does not fail loudly — it silently corrupts one live variable in the CALLER, and it shipped a
| real three-bombs-on-hardware bug in the BuggyBoy build (see that project's game_os.s header).
|
| NOTE: the file-I/O wrappers (Fcreate..Fwrite) MUST come first, right after _start — matching the
| proven BuggyBoy layout. Placing the GEMDOS control wrappers (Super/Pterm) before them makes
| Hatari's GEMDOS-HD hand back handle 0 (stdin) from Fopen, which then reads the keyboard (hang) or
| discards writes. Keep this order.

    .text
    .globl  _start
_start:
    | Keep the whole TPA (no Mshrink): GEMDOS leaves %a7 at the top of our memory, well above the
    | 1 MiB BSS image, so the stack has room. Mshrinking to a tight size would strand it.
    jsr     joust_main
    clr.w   -(%sp)                  | Pterm0 (GEMDOS 0x00): terminate
    trap    #1

| ---------------------------------------------------------------- GEMDOS file I/O (trap #1) ----

| long Fcreate(const char *name, short attr)        GEMDOS 0x3c
    .globl  Fcreate
Fcreate:
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

| long Fopen(const char *name, short mode)          GEMDOS 0x3d
    .globl  Fopen
Fopen:
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

| long Fclose(short handle)                         GEMDOS 0x3e
    .globl  Fclose
Fclose:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #0x3e,-(%sp)
    trap    #1
    addq.l  #4,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Fread(short handle, long count, void *buf)   GEMDOS 0x3f
    .globl  Fread
Fread:
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

| long Fwrite(short handle, long count, const void *buf)   GEMDOS 0x40
    .globl  Fwrite
Fwrite:
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

| ------------------------------------------------------------ GEMDOS control (trap #1) --------

| long Super(void *stack)       GEMDOS 0x20 — Super(0) enters supervisor and returns the old SSP;
| Super(that value) goes back to user mode.
|
| RETRACTION (2026-08-23, from Wonder Boy's batch 44 phase B): the note here used to claim that
| pairing the two calls was the whole of the requirement, and pointed at joust_main.c for it. That is
| NOT sufficient. TOS returns to user mode on the USP as
| it stood when Super(0) ran and does NOT reload it from the supervisor stack — so this wrapper is
| correct only while the compiler leaves %sp at the same depth at both call sites, and m68k GCC
| defers and combines argument pops. Wonder Boy's two depths diverged by twelve bytes the moment a
| load was inserted ahead of its Super(0); the rts popped stale stack and the program died AFTER a
| clean teardown with every read-back green. Joust has five leave sites and is currently lucky, not
| correct. The fix is one instruction — plant the USP yourself immediately before the trap; see
| projects/wonderboy/recreate/atari/wonderboy_os.s's wb_leave_supervisor and
| docs/on-target-execution.md bug 9. NOT APPLIED HERE: Joust is closed and this phase did not re-run
| its on-target ladder, so the change is registered rather than made.
    .globl  Super
Super:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)
    move.w  #0x20,-(%sp)
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| void Pterm(short code)        GEMDOS 0x4c — never returns.
    .globl  Pterm
Pterm:
    move.l  4(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #0x4c,-(%sp)
    trap    #1

| ------------------------------------------------------------------- BIOS (trap #13) ----------

| long Bconstat(short dev)      BIOS 0x01
    .globl  Bconstat
Bconstat:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #1,-(%sp)
    trap    #13
    addq.l  #4,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Bconin(short dev)        BIOS 0x02 (blocks; every caller gates on Bconstat first)
    .globl  Bconin
Bconin:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #2,-(%sp)
    trap    #13
    addq.l  #4,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| ------------------------------------------------------------------ XBIOS (trap #14) ----------

| long Logbase(void)            XBIOS 0x03 (and Physbase is 0x02) — TOS's own screen, saved at
| startup so the quit path can give it back.
    .globl  Logbase
Logbase:
    movem.l %d2/%a2,-(%sp)
    move.w  #3,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Physbase(void)           XBIOS 0x02
    .globl  Physbase
Physbase:
    movem.l %d2/%a2,-(%sp)
    move.w  #2,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| void Setscreen(void *log, void *phys, short rez)   XBIOS 0x05
| rez = -1 leaves the resolution alone. Setscreen (not a poke at $ffff8201/8203) because TOS's own
| VBL routine reloads the shifter from _v_bas_ad, which only Setscreen updates.
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

| void Setpalette(const void *palette16)    XBIOS 0x06
    .globl  Setpalette
Setpalette:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)
    move.w  #6,-(%sp)
    trap    #14
    lea     6(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Setcolor(short pen, short colour)    XBIOS 0x07 — colour -1 QUERIES the pen without setting
| it, which is how the shim reads the desktop's palette back at startup. Both args are the LOW word
| of their 4-byte C slot.
    .globl  Setcolor
Setcolor:
    movem.l %d2/%a2,-(%sp)
    move.l  16(%sp),%d1             | colour
    move.l  12(%sp),%d0             | pen
    move.w  %d1,-(%sp)
    move.w  %d0,-(%sp)
    move.w  #7,-(%sp)
    trap    #14
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Random(void)             XBIOS 0x11 (24-bit pseudo-random value)
    .globl  Random
Random:
    movem.l %d2/%a2,-(%sp)
    move.w  #0x11,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| void Ikbdws(short count_minus_one, const void *buf)   XBIOS 0x19
    .globl  Ikbdws
Ikbdws:
    movem.l %d2/%a2,-(%sp)
    move.l  16(%sp),%a1             | buf
    move.l  12(%sp),%d0             | count - 1
    move.l  %a1,-(%sp)
    move.w  %d0,-(%sp)
    move.w  #0x19,-(%sp)
    trap    #14
    lea     8(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Giaccess(short data, short reg)      XBIOS 0x1c (YM2149; bit 7 of reg selects write)
    .globl  Giaccess
Giaccess:
    movem.l %d2/%a2,-(%sp)
    move.l  16(%sp),%d1             | reg
    move.l  12(%sp),%d0             | data
    move.w  %d1,-(%sp)
    move.w  %d0,-(%sp)
    move.w  #0x1c,-(%sp)
    trap    #14
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| void Dosound(const void *list)    XBIOS 0x20 (TOS steps the command list once per VBL)
    .globl  Dosound
Dosound:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)
    move.w  #0x20,-(%sp)
    trap    #14
    lea     6(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Kbdvbase(void)           XBIOS 0x22 (the KBDVBASE vector table)
    .globl  Kbdvbase
Kbdvbase:
    movem.l %d2/%a2,-(%sp)
    move.w  #0x22,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| void Vsync(void)              XBIOS 0x25
    .globl  Vsync
Vsync:
    movem.l %d2/%a2,-(%sp)
    move.w  #0x25,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| ------------------------------------------------------------- setjmp / longjmp ---------------
|
| The reconstruction's RESTART exit is a `jmp` back into the middle of _start that abandons the
| stack (`addq.w #4,a7` and go). The C reconstruction cannot do that — it returns a result code that
| `start()` drops, exactly as the original's `jsr`s do — so the SHIM has to unwind instead, and this
| is the unwind. GCC's freestanding m68k ships no libc, so setjmp/longjmp are here rather than
| #included; they save only what the m68k SysV ABI makes callee-saved, plus the stack pointer.
|
| The buffer's layout is named below and SHIM_JMP_BUF_LONGS (shim_include/tos.h) must equal
| JB_LONGS — one C constant, one asm constant, and a comment in each pointing at the other, because
| nothing in the build can check them against each other.
|
| THE RETURN ADDRESS IS SAVED, NOT LEFT ON THE STACK. A first version stored %sp as it stood inside
| setjmp — pointing AT its own return address — and let longjmp's `rts` pick it up from there. That
| slot is dead the moment setjmp returns, and every call the game makes afterwards reuses it, so by
| the time longjmp ran it held whatever the last `jsr` had left. Measured: the longjmp fired and
| execution never reached the instruction after setjmp.

    JB_REGS  = 0                    | %d2-%d7/%a2-%a6, 11 longwords
    JB_SP    = 44                   | the caller's %sp once setjmp has returned
    JB_RET   = 48                   | ...and the address it returns to
    JB_LONGS = 13                   | == SHIM_JMP_BUF_LONGS in shim_include/tos.h

| int shim_setjmp(long env[JB_LONGS]) — 0 when called, `value` when longjmp lands here.
    .globl  shim_setjmp
shim_setjmp:
    move.l  4(%sp),%a0
    movem.l %d2-%d7/%a2-%a6,JB_REGS(%a0)
    move.l  (%sp),JB_RET(%a0)       | the return address, copied OUT of the stack
    lea     4(%sp),%a1
    move.l  %a1,JB_SP(%a0)          | ...and the %sp the caller will have once we return
    moveq   #0,%d0
    rts

| void shim_longjmp(long env[JB_LONGS], int value) — never returns; `value` of 0 is handed back as 1.
    .globl  shim_longjmp
shim_longjmp:
    move.l  4(%sp),%a0
    move.l  8(%sp),%d0
    bne.s   shim_longjmp_go
    moveq   #1,%d0
shim_longjmp_go:
    movem.l JB_REGS(%a0),%d2-%d7/%a2-%a6
    move.l  JB_SP(%a0),%sp          | the caller's stack, unwound
    move.l  JB_RET(%a0),-(%sp)      | its return address pushed back below it (dead space), and
    rts                             |   consumed on the spot

| ------------------------------------------------------- the IKBD joystick-packet handler -----
|
| Installed at KBDVBASE joyvec (+0x18). TOS's IKBD interrupt enters here with %a0 pointing at the
| two joystick bytes of the reply. It does what the ORIGINAL's six-byte handler at 0x102da does —
| publish the packet where the game's wait loops can see it — but it cannot BE that handler: the
| original stores %a0 itself, an address inside the original's own load, and our cores read
| ikbd_packet as an IMAGE OFFSET (`image[packet + 0]`). So the two bytes are copied into a fixed
| scratch slot in the image and that slot's OFFSET is published instead.
|
| It then CHAINS another "interrogate joysticks" ($16) straight at the ACIA. That is the shim's
| answer to the one thing the reconstruction cannot do for itself: request_ikbd_packet (src/input.c)
| clears ikbd_packet but issues no Ikbdws, because the trap has no image effect and the differential
| could not have held it — so on target nothing would ever ask the IKBD for a reply and every wait
| would spin for ever. Chaining from the reply keeps one interrogate permanently in flight, so a
| wait costs about the 2.6 ms of one 2-byte reply at 7812.5 baud, which is what the original pays.
|
| It runs on an interrupt, so it saves everything it touches.

    .extern ikbd_packets

    ACIA_STATUS = 0xfffffc00           | IKBD ACIA status; bit 1 = transmit data register empty
    ACIA_DATA   = 0xfffffc02
    IKBD_INTERROGATE = 0x16

    .globl  joy_handler
joy_handler:
    movem.l %d0/%a0/%a1,-(%sp)
    move.l  joy_buf_addr,%a1        | image + JOY_PACKET_BUF, as a REAL address
    move.b  (%a0)+,(%a1)+           | joystick 0
    move.b  (%a0),(%a1)             | joystick 1
    move.l  joy_slot_addr,%a1       | image + A_ikbd_packet, as a REAL address
    move.l  joy_packet_off,(%a1)    | ...holding the IMAGE OFFSET the cores dereference
    addq.l  #1,ikbd_packets         | one more reply filed (the only headless evidence of a live
                                    |   joystick path — see joust_main.c)
    move.b  ACIA_STATUS,%d0
    btst    #1,%d0
    beq.s   joy_no_chain            | transmitter busy: the VBL watchdog re-primes instead
    move.b  #IKBD_INTERROGATE,ACIA_DATA
joy_no_chain:
    movem.l (%sp)+,%d0/%a0/%a1
    rts

| The mouse vector gets this: the original installs a handler that files the mouse packet away and
| returns, and we have no use for the packet — but TOS's own default must not stay hooked while the
| game owns the keyboard. Two bytes, no side effects.
    .globl  null_handler
null_handler:
    rts
