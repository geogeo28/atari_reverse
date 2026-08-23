| wonderboy_os.s — GEMDOS entry, the TOS trap wrappers, and the two INTERRUPT entries WB.PRG needs.
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
| real three-bombs-on-hardware bug in the BuggyBoy build. It is also this workspace's own recorded
| real-hardware gotcha, and it is invisible to every differential in the project.
|
| NOTE: the file-I/O wrappers (Fcreate..Fwrite) MUST come first, right after _start — matching the
| proven BuggyBoy and Joust layout. Placing the GEMDOS control wrappers (Super/Pterm) before them
| makes Hatari's GEMDOS-HD hand back handle 0 (stdin) from Fopen, which then reads the keyboard
| (hang) or discards writes. Keep this order.

    .text
    .globl  _start
_start:
    | Keep the whole TPA (no Mshrink): GEMDOS leaves %a7 at the top of our memory, well above the
    | 1 MiB BSS image, so the stack has room. Mshrinking to a tight size would strand it.
    jsr     wonderboy_main
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
| The way BACK is wb_leave_supervisor below and NOT this routine; the paragraph there says why.
|
| It is the ONE trap the original issues in its whole life (../project.toml's byte scan of the
| image), which is why this file is short: Wonder Boy drives the hardware itself.
    .globl  Super
Super:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)
    move.w  #0x20,-(%sp)
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long wb_leave_supervisor(void *ssp)   GEMDOS 0x20 again — the RETURN half, made safe.
|
| WHY THIS IS NOT JUST `Super(ssp)`, AND IT IS A DEFECT THIS DIRECTORY SHIPPED RATHER THAN A
| REFINEMENT. TOS goes back to user mode by loading %a7 from the USER stack pointer, and the USP it
| uses is the one FROZEN when `Super(0)` was called — measured on TOS 1.04, it does not set the USP
| from the supervisor stack on the way out. So a plain `Super(ssp)` returns onto the stack position
| the FIRST call stood at, and the wrapper's own unwind (`addq #6` / `movem` / `rts`) reads from
| there. That is right only while the compiler leaves %sp at the SAME depth at both call sites, and
| m68k GCC does not promise it: it DEFERS argument pops and combines them, so an edit anywhere
| between the two calls can move one of them.
|
| MEASURED, and it is how the fault was found: with the title slice added ahead of `Super(0)`, %sp
| at the second call sat 12 bytes above the first (`USP 003f7f52` against `ISP 003f7f5e`), the `rts`
| popped stale stack and the program died reading $26520020 — AFTER the teardown, with every
| read-back green and no record written. The M1 build's two calls are at the same depth
| (`USP 003f7fa2` == `ISP 003f7fa2`) and it survives on that coincidence.
|
| So this sets the USER stack pointer to the supervisor stack it is standing on, one instruction
| before the trap, which makes the return independent of where either call was made. `move %a0,%usp`
| is privileged; this routine is supervisor-only by construction, since nothing else has a supervisor
| stack pointer to hand back.
    .globl  wb_leave_supervisor
wb_leave_supervisor:
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
| give it back, and the read-back that says what the shifter is really displaying from.
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

| void Setscreen(void *log, void *phys, short rez)   XBIOS 0x05 — the TEARDOWN's way back. The RUN
| pokes $ff8201/$ff8203 directly, because that is what the reconstruction does; putting TOS's screen
| back needs _v_bas_ad updated too, and only Setscreen does that.
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
| `wonderboy_main.c` samples the reconstruction's own vblank counter (an image word `vbl_handler`
| writes) and the shim's independent tick count, and COMPARES THEM. Sampled without masking they can
| skew by one — the handler increments the shim's counter and then calls `vbl_handler`, so a vblank
| landing anywhere in the sampling window leaves the two describing different instants and the gate
| goes red on a correct build. Rare, and therefore worse than common: it would read as flake.
|
| A seqlock-style retry cannot close it. Reading the shim's counter either side of the image read
| proves no vblank COMPLETED in the window, not that none was in flight — the increment happens
| BEFORE `vbl_handler` writes the image, so a handler entered just before the first read can land its
| write in the middle with both shim reads equal. Masking is the answer that is airtight rather than
| nearly so, and it is four instructions.
|
| Used for that ONE section and deliberately not for the PSG select/data pair, which reproduces the
| original's race on purpose (see wonderboy_backend.c).

    IPL7 = 0x0700                   | interrupt priority mask, all levels off

| unsigned short wb_irq_disable(void) — returns the SR to hand back. Supervisor only, which is where
| every caller is; `move.w %sr,%d0` is unprivileged on the 68000 anyway.
    .globl  wb_irq_disable
wb_irq_disable:
    moveq   #0,%d0                  | clear the high half: the C return type is 16-bit
    move.w  %sr,%d0
    ori.w   #IPL7,%sr
    rts

| void wb_irq_restore(unsigned short sr) — the arg occupies a 4-byte C slot, so on the big-endian
| stack the value is the LOW word at +6.
    .globl  wb_irq_restore
wb_irq_restore:
    move.w  6(%sp),%sr
    rts

| ------------------------------------------------------- the two INTERRUPT entries -------------
|
| The reconstruction has one interrupt handler of its own — `vbl_handler` (../src/game.c, $716), the
| first routine in any of this workspace's three ports to end in `rte` — and needs a second one it
| does NOT have: `ikbd_acia_handler` ($754) is unported, and it is what writes the byte
| `sched_wait8` spins on. Both are installed at the REAL exception vectors, which is where the boot
| chain puts them ($f8bc: `$70 := $716`, `$118 := $754`), rather than at a TOS hook — the original
| owns the machine and so, for the length of its run, does this.
|
| EACH ENTRY IS THE `movem` PAIR THE C CANNOT WRITE, AND NOTHING ELSE. ../names.txt's cmt 0x716
| records that the original's handler saves d0-a6 and that the reconstruction deliberately does not
| reproduce it — "a C function's own registers are its compiler's business". On target that is only
| true of the registers the C function itself touches; the INTERRUPTED code's registers are this
| file's business, so the entry saves the full set and the body stays the verified C.

    .globl  wb_vbl_entry
wb_vbl_entry:
    movem.l %d0-%d7/%a0-%a6,-(%sp)
    jsr     wb_vbl_tick             | wonderboy_main.c: calls the reconstructed vbl_handler(image)
    movem.l (%sp)+,%d0-%d7/%a0-%a6
    rte

| MFP channel 6 — the keyboard/MIDI ACIA. The body reads $fffffc02 and files the byte; this entry
| adds the register save and the End-Of-Interrupt the MFP needs, which the C has no way to spell.
|
| THE EOI IS `bclr` ON ISRB, NOT A STORE. The MC68901's in-service register is cleared by writing a
| ZERO to the bit and ONES everywhere else — a `move.b #~0x40` would clear every other in-service
| channel at the same time. `bclr` on memory is a read-modify-write and does exactly the documented
| thing.
    MFP_ISRB    = 0xfffffa11
    MFP_ISRB_ACIA_BIT = 6

    .globl  wb_acia_entry
wb_acia_entry:
    movem.l %d0-%d7/%a0-%a6,-(%sp)
    jsr     wb_acia_byte            | wonderboy_main.c: read $fffffc02, dispatch, store in the image
    bclr    #MFP_ISRB_ACIA_BIT,MFP_ISRB
    movem.l (%sp)+,%d0-%d7/%a0-%a6
    rte
