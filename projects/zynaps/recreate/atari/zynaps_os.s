| zynaps_os.s — GEMDOS entry, the TOS trap wrappers, and the machine primitives ZYNAPS.PRG needs.
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
| real three-bombs-on-hardware bug in the BuggyBoy build. It is invisible to every differential in
| this project, because the oracle services traps in-process and clobbers nothing.
| `tools/assert_trap_registers.sh` is the workspace's scan for it; build.sh runs it over this file.
|
| NOTE: the file-I/O wrappers (Fcreate..Fwrite) MUST come first, right after _start — matching the
| proven BuggyBoy, Joust and Wonder Boy layout. Placing the GEMDOS control wrappers (Super/Pterm)
| before them makes Hatari's GEMDOS-HD hand back handle 0 (stdin) from Fopen, which then reads the
| keyboard (hang) or discards writes. Keep this order. It matters more here than in either sibling:
| Zynaps' loader is the program, and every graphic it shows arrives through Fopen.

    .text
    .globl  _start
_start:
    | Keep the whole TPA (no Mshrink): GEMDOS leaves %a7 at the top of our memory, well above the
    | 1 MiB BSS image, so the stack has room. Mshrinking to a tight size would strand it. It is also
    | what the original does — ../STATUS.md's project.toml byte scan found no Malloc/Mshrink in the
    | whole text, and `_start` simply keeps what the AUTO-folder loader gave it.
    |
    | SUPERVISOR IS TAKEN HERE, ONCE, BEFORE ANY C RUNS, and handed back once at the end of
    | zynaps_main through `zy_leave_supervisor`. The original takes it as its own first instruction
    | (0x10000) and never gives it back; this build has to, because GEMDOS gets the machine after.
    | shim_include/os.h says why the cores' own `os_super` is a no-op rather than a second trap.
    clr.l   -(%sp)                  | Super(0)
    jsr     Super
    addq.l  #4,%sp
    move.l  %d0,zy_saved_ssp        | ...and the stack pointer to hand back
    jsr     zynaps_main
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

| long Super(void *stack)       GEMDOS 0x20 — Super(0) ENTERS supervisor and returns the old SSP.
| The way BACK is zy_leave_supervisor below and NOT this routine; the paragraph there says why.
    .globl  Super
Super:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)
    move.w  #0x20,-(%sp)
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long zy_leave_supervisor(void *ssp)   GEMDOS 0x20 again — the RETURN half, made safe.
|
| WHY THIS IS NOT JUST `Super(ssp)`. TOS goes back to user mode by loading %a7 from the USER stack
| pointer, and the USP it uses is the one FROZEN when `Super(0)` was called — measured on TOS 1.04
| by the sibling project, it does not set the USP from the supervisor stack on the way out. So a
| plain `Super(ssp)` returns onto the stack position the FIRST call stood at, and the wrapper's own
| unwind (`addq #6` / `movem` / `rts`) reads from there. That is right only while the compiler
| leaves %sp at the SAME depth at both call sites, and m68k GCC does not promise it: it DEFERS
| argument pops and combines them, so an edit anywhere between the two calls can move one of them.
| projects/wonderboy/recreate/atari/wonderboy_os.s has the reproduction — a crash AFTER a clean
| teardown, with every read-back green, which is the worst shape a defect can take.
|
| THIS BUILD IS THE EXPOSED SHAPE, not the lucky one: `_start` takes supervisor before any C runs
| and zynaps_main hands it back nine hundred lines of boot later, so the two %sp depths have no
| reason whatever to agree. So this sets the USER stack pointer to the supervisor stack it is
| standing on, one instruction before the trap, which makes the return independent of where either
| call was made. `move %a0,%usp` is privileged; this routine is supervisor-only by construction,
| since nothing else has a supervisor stack pointer to hand back.
    .globl  zy_leave_supervisor
zy_leave_supervisor:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)          | the SSP Super(0) handed back
    move.w  #0x20,-(%sp)
    move.l  %sp,%a0
    move.l  %a0,%usp                | ...so the return lands %a7 exactly here, whatever GCC did
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| ------------------------------------------------------------------ XBIOS (trap #14) ----------

| long Physbase(void)           XBIOS 0x02 — TOS's own screen, saved at startup so the teardown can
| give it back, and the read-back that says what the shifter is really displaying from. It is the
| one instrument that catches a video base the STF truncated (docs/on-target-execution.md class 8).
    .globl  Physbase
Physbase:
    movem.l %d2/%a2,-(%sp)
    move.w  #2,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Logbase(void)            XBIOS 0x03
    .globl  Logbase
Logbase:
    movem.l %d2/%a2,-(%sp)
    move.w  #3,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| short Getrez(void)            XBIOS 0x04 — the resolution to give back, taken before the boot's
| `andi.b #$fc,$ff8260` drops the machine into low res.
    .globl  Getrez
Getrez:
    movem.l %d2/%a2,-(%sp)
    move.w  #4,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| void Setscreen(void *log, void *phys, short rez)   XBIOS 0x05 — the TEARDOWN's way back. The RUN
| pokes $ff8201/$ff8203 and $ff8260 directly, because that is what the reconstruction does; putting
| TOS's screen back needs `_v_bas_ad` and `sshiftmd` updated too, and only Setscreen does that.
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

| ---------------------------------------------------------- masking, for ONE critical section ---
|
| The two exception vectors are installed as a pair, which the original brackets with
| `move.w #$2700,sr` at 0x1005e and `move.w #$2300,sr` at 0x10076. A vertical blank landing between
| the two stores would enter a handler through a vector whose other half still points at TOS's.

    IPL7 = 0x0700                   | interrupt priority mask, all levels off

| unsigned short zy_irq_disable(void) — returns the SR to hand back. `move.w %sr,%d0` is
| unprivileged on the 68000, and every caller is in supervisor mode anyway.
    .globl  zy_irq_disable
zy_irq_disable:
    moveq   #0,%d0                  | clear the high half: the C return type is 16-bit
    move.w  %sr,%d0
    ori.w   #IPL7,%sr
    rts

| void zy_irq_restore(unsigned short sr) — the arg occupies a 4-byte C slot, so on the big-endian
| stack the value is the LOW word at +6.
    .globl  zy_irq_restore
zy_irq_restore:
    move.w  6(%sp),%sr
    rts

| ------------------------------------------------------- Line A, and the IKBD ------------------

| void zy_line_a_hide_mouse(void) — the `dc.w $a00a` at 0x10010, for real.
|
| The oracle takes an unimplemented instruction as an exception, so ../src/init.c models this as a
| no-op and ../STATUS.md carries it as MODELLED, not verified. Here it is the opcode. The Line A
| handler clobbers %d0-%d2/%a0-%a2 (it returns its variable pointers there), and %d2/%a2 are the
| pair GCC expects to survive — the same rule as every trap wrapper above, for the same reason.
    .globl  zy_line_a_hide_mouse
zy_line_a_hide_mouse:
    movem.l %d2/%a2,-(%sp)
    .word   0xa00a                  | Line A: hide mouse pointer
    movem.l (%sp)+,%d2/%a2
    rts

| int zy_ikbd_send_cmd(unsigned char command) — `ikbd_send_cmd` @ 0x14444, BOUNDED.
|
| The original is four instructions: `btst #1,$fffc00 / beq.s self / move.b d0,$fffc02 / rts`. It is
| unported (../STATUS.md, "Not reconstructed") because the kit models no read for the ACIA status
| byte, so the oracle spins there for ever — which is exactly why it is here and not in ../src.
|
| THE BOUND IS THE ONE DEVIATION, and it buys the verdict. The original cannot fail; a headless
| check that hangs decides nothing, and a hang looks identical to a broken machine. So the wait is
| capped and the answer says which happened: 1 = the transmitter went ready and the byte was
| stored, 0 = the wait spun out and NOTHING was stored. zynaps_main.c publishes both calls' verdicts
| in STATE.BIN and smoke.py asserts them. The kit's own `sched_wait8` makes the identical trade for
| the identical reason.
|
| THE CAP IS A SPIN COUNT, NOT A TIME. At 8 MHz this loop is ~20 cycles, so the cap is ~0.2 s —
| four orders of magnitude above the ACIA's ~64 us character time and far below any watchdog. It is
| local to this routine, which is why it is defined here.
|
| The byte is read out of the low END of the 4-byte C slot, matching every wrapper above: the SysV
| ABI passes an `unsigned char` in a full slot and on a big-endian stack the value is at +7. Read as
| the longword and used as its low byte, which is the shape that does not depend on the argument's
| declared width.

    IKBD_ACIA_STATUS   = 0xfffffc00
    IKBD_ACIA_DATA     = 0xfffffc02
    IKBD_TX_READY_BIT  = 1          | `btst #1,$fffc00` — the transmitter-data-register-empty bit
    IKBD_SPIN_MAX      = 100000

    .globl  zy_ikbd_send_cmd
zy_ikbd_send_cmd:
    move.l  4(%sp),%d1              | the command byte, in the low byte of its slot
    move.l  #IKBD_SPIN_MAX,%d0
1:  btst    #IKBD_TX_READY_BIT,IKBD_ACIA_STATUS
    bne.s   2f
    subq.l  #1,%d0
    bne.s   1b
    rts                             | spun out: %d0 is 0, and nothing was stored
2:  move.b  %d1,IKBD_ACIA_DATA
    moveq   #1,%d0
    rts

| ------------------------------------------------------- the two INTERRUPT entries -------------
|
| The reconstruction's own handlers — `vbl_isr` @ 0x10776 and `timer_b_isr` @ 0x10782, both verified
| in ../src/irq.c and both ending in `rte` there only in the sense that the ORIGINAL does; the C
| bodies return normally. Both are installed at the REAL exception vectors $70 and $120, which is
| where the boot puts them (0x10062 and 0x1006c), rather than at a TOS hook — the original owns the
| machine and so, for the length of its run, does this.
|
| EACH ENTRY IS THE `movem` PAIR THE C CANNOT WRITE, AND NOTHING ELSE. The original's handlers save
| every register (`movem.l #$fffe,-(a7)` in the sound tick's own prologue); a C function's own
| registers are its compiler's business, but the INTERRUPTED code's registers are this file's.

    .globl  zy_vbl_entry
zy_vbl_entry:
    movem.l %d0-%d7/%a0-%a6,-(%sp)
    jsr     zy_vbl_tick             | zynaps_main.c: bumps the tick count, calls vbl_isr(image)
    movem.l (%sp)+,%d0-%d7/%a0-%a6
    rte

| MFP Timer B. The original installs this vector at 0x1006c and this build does the same, but
| NOTHING IN M1 STARTS TIMER B: the boot slice programs no MFP timer, and TOS leaves Timer B stopped
| on an ST. So this entry is installed and never entered, which is a claim STATE.BIN carries as a
| number (`timer_b_ticks`, expected 0) rather than a sentence. The acknowledge the handler needs is
| `mfp_ack_timer_b` in zynaps_backend.c, not here, because the C body is where the original's
| `bclr #0,$fffa0f` sits.
    .globl  zy_timer_b_entry
zy_timer_b_entry:
    movem.l %d0-%d7/%a0-%a6,-(%sp)
    jsr     zy_timer_b_tick         | zynaps_main.c: bumps its count, calls timer_b_isr(image)
    movem.l (%sp)+,%d0-%d7/%a0-%a6
    rte
