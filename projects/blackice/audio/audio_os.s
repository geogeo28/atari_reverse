| audio_os.s — the GEMDOS entry, the TOS trap wrappers, and the ONE interrupt-side entry
| AUDIOTEST.PRG needs. Modelled on projects/wonderboy/recreate/atari/wonderboy_os.s, which is where
| the two rules below were paid for on real hardware.
|
| C ABI (m68k SysV): args at 4(%sp), 8(%sp), ...; every int/pointer occupies 4 bytes; result in %d0.
| Each wrapper cleans only its own trap-frame pushes; the caller cleans the C args.
|
| REGISTERS — where the two calling conventions DISAGREE:
|   GCC (m68k SysV): %d0/%d1/%a0/%a1 scratch; %d2-%d7 and %a2-%a6 CALLEE-SAVED, so the compiler
|                    caches live values in %d2/%a2 across a call to any wrapper here.
|   TOS (GEMDOS/BIOS/XBIOS): preserves only %d3-%d7 and %a3-%a6 — %d0-%d2 and %a0-%a2 are VOLATILE.
| So every wrapper saves %d2/%a2 around its trap (hence each reads its C arguments at +12, not +4).
| Skipping it does not fail loudly: it silently corrupts one live variable in the CALLER, and it
| shipped a three-bombs-on-hardware bug in this workspace's BuggyBoy build.
|
| THE FILE-I/O WRAPPERS COME FIRST, right after _start, matching the proven BuggyBoy/Joust/Wonder
| Boy layout. Putting the GEMDOS control wrappers (Super/Pterm) ahead of them makes Hatari's
| GEMDOS-HD hand back handle 0 (stdin) from Fcreate, which then discards every write — a green run
| with an empty ledger. Keep this order.

    .text
    .globl  _start
_start:
    | Keep the whole TPA (no Mshrink): GEMDOS leaves %a7 at the top of our memory, above the image,
    | so the stack has room, and nothing here allocates.
    jsr     audiotest_main
    clr.w   -(%sp)                  | Pterm0 (GEMDOS 0x00): terminate
    trap    #1

| ---------------------------------------------------------------- GEMDOS file I/O (trap #1) ----

| long Fcreate(const char *name, short attr)               GEMDOS 0x3c
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

| long Fclose(short handle)                                GEMDOS 0x3e
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

| ------------------------------------------------------------ GEMDOS control (trap #1) --------

| long Super(void *stack)   GEMDOS 0x20 — Super(0) ENTERS supervisor and returns the old SSP.
| The way BACK is audio_leave_supervisor below, and the paragraph there says why it is not this.
    .globl  Super
Super:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)
    move.w  #0x20,-(%sp)
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long audio_leave_supervisor(void *ssp)   GEMDOS 0x20 again — the RETURN half, made safe.
|
| TOS returns to user mode by loading %a7 from the USER stack pointer, and the USP it uses is the
| one frozen when `Super(0)` was called — it does NOT set the USP from the supervisor stack on the
| way out (measured on TOS 1.04 in the Wonder Boy port). So a plain `Super(ssp)` returns onto the
| stack position the FIRST call stood at, and the wrapper's own unwind reads from there. That is
| right only while the compiler leaves %sp at the same depth at both call sites, and m68k GCC does
| not promise it: it defers argument pops and combines them, so an edit anywhere between the two
| calls can move one of them.
|
| So this sets the USER stack pointer to the supervisor stack it is standing on, one instruction
| before the trap, which makes the return independent of where either call was made.
| `move %a0,%usp` is privileged; this routine is supervisor-only by construction, since nothing
| else has a supervisor stack pointer to hand back.
    .globl  audio_leave_supervisor
audio_leave_supervisor:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)          | the SSP Super(0) handed back
    move.w  #0x20,-(%sp)
    move.l  %sp,%a0
    move.l  %a0,%usp                | ...so the return lands %a7 exactly here, whatever GCC did
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| ---------------------------------------------------------------- the VBL-queue entry ----------
|
| TOS's own level-4 handler walks `_vblqueue` and `jsr`s each non-null slot, so this is an `rts`
| routine and not an `rte` one — audiotest.c's install_vbl_tick is what puts it in a slot.
|
| WHY IT SAVES ANYTHING AT ALL. Every TOS this could run on saves %d0-%d7/%a0-%a6 before walking
| the queue, so in practice nothing here is needed. The four registers below are exactly the ones a
| SysV C function is free to destroy (%d2-%d7/%a2-%a6 the callee saves itself), so this is the
| cheapest possible hedge against a TOS that does not — 80 cycles against a ~2,000-cycle tick — and
| the failure it hedges against is an interrupted program corrupted at random.
    .globl  audio_vbl_entry
audio_vbl_entry:
    movem.l %d0-%d1/%a0-%a1,-(%sp)
    jsr     audio_vbl_tick          | audiotest.c: steps the music and fires this frame's SFX
    movem.l (%sp)+,%d0-%d1/%a0-%a1
    rts
