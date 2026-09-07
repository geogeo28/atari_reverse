| flyshark_os.s — GEMDOS entry, the TOS trap wrappers, and the machine primitives FLYSHARK.PRG
| needs. Everything here is what a C function cannot write.
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
| real three-bombs-on-hardware bug in the BuggyBoy build (docs/on-target-execution.md class 3). It
| is invisible to every differential in this project, because the oracle services traps in-process
| and clobbers nothing. `tools/assert_trap_registers.sh` is the workspace's scan for it; build.sh
| runs it over this file with the wrapper count asserted, so a rotted pattern reddens rather than
| passing vacuously.
|
| NOTE: the file-I/O wrappers MUST come first, right after `_start` — matching the proven BuggyBoy,
| Joust, Wonder Boy and Zynaps layout. Placing the GEMDOS control wrappers (Super/Pterm) before them
| makes Hatari's GEMDOS-HD hand back handle 0 (stdin) from Fopen, which then reads the keyboard
| (hang) or discards writes. Keep this order: every one of the eight files this game loads arrives
| through Fopen, and a handle 0 would be a hang at the title picture.

    .text
    .globl  _start
_start:
    | Keep the whole TPA (no Mshrink): GEMDOS leaves %a7 at the top of our memory, well above the
    | half-megabyte .bss image, so the stack has room — and the interrupt handlers run on it too.
    | It is also what the original does: it takes the machine and never gives any of it back.
    |
    | THE BASEPAGE AND THE ENTRY STACK, LATCHED FIRST. GEMDOS leaves the basepage's address at
    | 4(%sp) on entry and the Super(0) push below moves %sp, so this is the only instant either can
    | be read. p_lowtpa/p_hitpa are the memory this program was given, which is how flyshark_main.c
    | MEASURES its budget instead of assuming one (docs/on-target-execution.md, "Fitting the
    | machine"), and %sp is the stack GEMDOS actually started us on — the LOWER of it and p_hitpa is
    | the ceiling that measurement uses, so a launcher that pushed an environment cannot make the
    | headroom over-report.
    move.l  4(%sp),fs_basepage
    move.l  %sp,fs_initial_sp
    | SUPERVISOR IS TAKEN HERE, ONCE, BEFORE ANY C RUNS, and handed back once at the end of
    | flyshark_main through `fs_leave_supervisor`. The original takes it four instructions into
    | `boot_init` and never gives it back; this build has to, because GEMDOS gets the machine after.
    | shim_include/os.h says why the cores' own `os_super` is a no-op rather than a second trap.
    clr.l   -(%sp)                  | Super(0)
    jsr     Super
    addq.l  #4,%sp
    move.l  %d0,fs_saved_ssp        | ...and the stack pointer to hand back
    jsr     flyshark_main
    clr.w   -(%sp)                  | Pterm0 (GEMDOS 0x00): terminate
    trap    #1

| ---------------------------------------------------------------- GEMDOS file I/O (trap #1) ----

| long Fopen(const char *name, short mode)          GEMDOS 0x3d
    .globl  Fopen
Fopen:
    movem.l %d2/%a2,-(%sp)          | TOS traps may trash d2/a2 — see the register note above
    move.l  12(%sp),%d1             | name
    move.l  16(%sp),%d0             | mode (int); the value is the LOW word of the slot
    move.w  %d0,-(%sp)
    move.l  %d1,-(%sp)
    move.w  #0x3d,-(%sp)
    trap    #1
    lea     8(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Fcreate(const char *name, short attr)        GEMDOS 0x3c — the record's, never a core's
    .globl  Fcreate
Fcreate:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d1             | name
    move.l  16(%sp),%d0             | attr
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

| ------------------------------------------------------------ GEMDOS control (trap #1) --------

| long Cconout(short ch)        GEMDOS 0x02 — the debug overlay's only output, and
| `console_show_message`'s. Nothing in a normal run reaches either.
    .globl  Cconout
Cconout:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #0x02,-(%sp)
    trap    #1
    addq.l  #4,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Super(void *stack)       GEMDOS 0x20 — Super(0) ENTERS supervisor and returns the old SSP.
| The way BACK is `fs_leave_supervisor` below and NOT this routine; the paragraph there says why.
    .globl  Super
Super:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)
    move.w  #0x20,-(%sp)
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long fs_leave_supervisor(void *ssp)   GEMDOS 0x20 again — the RETURN half, made safe.
|
| WHY THIS IS NOT JUST `Super(ssp)`. TOS goes back to user mode by loading %a7 from the USER stack
| pointer, and the USP it uses is the one FROZEN when `Super(0)` was called: measured on TOS 1.04 by
| a sibling project, it does not set the USP from the supervisor stack on the way out. So a plain
| `Super(ssp)` returns onto the stack position the FIRST call stood at, and the wrapper's own unwind
| reads from there. That is right only while the compiler leaves %sp at the SAME depth at both call
| sites, and m68k GCC does not promise it — it defers and combines argument pops
| (docs/on-target-execution.md class 9, whose reproduction is a crash AFTER a clean teardown with
| every read-back green).
|
| THIS BUILD IS THE EXPOSED SHAPE, not the lucky one: `_start` takes supervisor before any C runs
| and `flyshark_main` hands it back a whole game later, so the two %sp depths have no reason to
| agree. So this sets the USER stack pointer to the supervisor stack it is standing on, one
| instruction before the trap, which makes the return independent of where either call was made.
| `move %a0,%usp` is privileged; this routine is supervisor-only by construction, since nothing else
| has a supervisor stack pointer to hand back.
    .globl  fs_leave_supervisor
fs_leave_supervisor:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)          | the SSP Super(0) handed back
    move.w  #0x20,-(%sp)
    move.l  %sp,%a0
    move.l  %a0,%usp                | ...so the return lands %a7 exactly here, whatever GCC did
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| ------------------------------------------------------------------- BIOS (trap #13) ----------

| long Bconout(short device, short ch)      BIOS 3 — device 4 is the IKBD, where a byte is a
| command to the 6301 and not a character. `boot_init` sends exactly one: $14, report joystick
| events, without which the stick's packets never arrive (docs/on-target-execution.md class 12).
    .globl  Bconout
Bconout:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d1             | device
    move.l  16(%sp),%d0             | ch
    move.w  %d0,-(%sp)
    move.w  %d1,-(%sp)
    move.w  #3,-(%sp)
    trap    #13
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| ------------------------------------------------------------------ XBIOS (trap #14) ----------

| long Physbase(void)           XBIOS 2 — what the shifter is really displaying from, and the one
| instrument that catches a video base the STF truncated (docs/on-target-execution.md class 8).
    .globl  Physbase
Physbase:
    movem.l %d2/%a2,-(%sp)
    move.w  #2,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Logbase(void)            XBIOS 3
    .globl  Logbase
Logbase:
    movem.l %d2/%a2,-(%sp)
    move.w  #3,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| short Getrez(void)            XBIOS 4 — the resolution to give back, taken before the boot drops
| the machine into low res.
    .globl  Getrez
Getrez:
    movem.l %d2/%a2,-(%sp)
    move.w  #4,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| void Setscreen(void *log, void *phys, short rez)   XBIOS 5
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

| void Setpalette(void *table)  XBIOS 6 — sixteen colour words, applied at the next vertical blank.
    .globl  Setpalette
Setpalette:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)
    move.w  #6,-(%sp)
    trap    #14
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| void Vsync(void)              XBIOS 37 — wait for the next vertical blank.
    .globl  Vsync
Vsync:
    movem.l %d2/%a2,-(%sp)
    move.w  #37,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| void *Kbdvbase(void)          XBIOS 34 — the KBDVBASE struct, whose +$18 is TOS's own joystick
| packet callback. What the core does with the answer is flyshark_main.c's `fs_kbdvbase` note.
    .globl  Kbdvbase
Kbdvbase:
    movem.l %d2/%a2,-(%sp)
    move.w  #34,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| ---------------------------------------------------------- masking, for TWO critical sections ---
|
| The boot installs its two exception vectors as a pair, which the original brackets with
| `move.w #$2700,sr` @ 0x14ca8 and `move.w #$2300,sr` @ 0x14cce (../src/init.c says why the pair
| itself is not in the C: the model has no interrupt to mask). A vertical blank landing between the
| two stores would enter a handler through a vector whose other half still points at TOS's.

    IPL7 = 0x0700                   | interrupt priority mask, all levels off

| unsigned short fs_irq_disable(void) — returns the SR to hand back. `move.w %sr,%d0` is
| unprivileged on the 68000, and every caller is in supervisor mode anyway.
    .globl  fs_irq_disable
fs_irq_disable:
    moveq   #0,%d0                  | clear the high half: the C return type is 16-bit
    move.w  %sr,%d0
    ori.w   #IPL7,%sr
    rts

| void fs_irq_restore(unsigned short sr) — the arg occupies a 4-byte C slot, so on the big-endian
| stack the value is the LOW word at +6.
    .globl  fs_irq_restore
fs_irq_restore:
    move.w  6(%sp),%sr
    rts

| ------------------------------------------------------- the two INTERRUPT entries -------------
|
| The reconstruction's own handlers are verified in ../src/irq.c and end in `rte` there only in the
| sense that the ORIGINAL does; the C bodies return normally. Each entry below is installed at the
| REAL exception vector the boot's own `move.l` names — $70 and $118 — because the original owns the
| machine and so, for the length of its run, does this.
|
| THE C HALVES DISPATCH ON THE IMAGE'S OWN VECTOR PAGE. The cores store a Ghidra address into
| `image + $70` / `image + $118`, which on the real machine IS low memory but here is a longword
| inside the image array — ordinary diffable memory the differential already holds. So the shim
| reads it back and calls the handler it names; flyshark_main.c's `dispatch_image_vector` is the
| table, and an address it does not know is a halt with the value in the record, never a silent
| skip. That is what makes `acia_ikbd_isr`'s two-state machine — it re-points $118 at a
| continuation and the continuation puts it back — work with no knowledge of it here.
|
| EACH ENTRY SAVES FOUR REGISTERS AND NOT FIFTEEN, and that is the ABI rather than a preference:
| m68k SysV makes %d0/%d1/%a0/%a1 SCRATCH and %d2-%d7/%a2-%a6 CALLEE-SAVED, so everything reached
| from the `jsr` has already put back every register but those four. The original's handlers save
| `movem.l #$fffe` because they are hand asm and use whichever they like. The exception frame
| carries the SR, so the condition codes need no saving either.

    .globl  fs_vbl_entry
fs_vbl_entry:
    movem.l %d0-%d1/%a0-%a1,-(%sp)
    jsr     fs_vbl_tick             | flyshark_main.c: counts the entry, dispatches on image[$70]
    movem.l (%sp)+,%d0-%d1/%a0-%a1
    | ...AND THEN CHAINS, which is the whole of `vbl_handler`'s tail: it ends `jmp $1164e.l`, whose
    | operand `boot_init` fills from the $70 vector TOS had (../include/init.h, A_vbl_chain_vector).
    | `fs_vbl_tick` reads that operand out of the image and leaves it here, so the chain is the
    | program's own self-modified `jmp` and not a pointer this file keeps. TOS's handler ends in
    | `rte` on OUR exception frame, which is exactly what the original relies on to keep `_frclock`
    | and the rest of TOS's blank-time housekeeping alive.
    |
    | THE PUSH-AND-`rts` IS A JUMP THAT NEEDS NO REGISTER: every register is already restored, so
    | there is none to hold the target in. What it costs is the condition codes, which the `tst`
    | sets and TOS's handler does not read — and the `rte` at the end of it restores the interrupted
    | code's SR from the frame regardless.
    tst.l   fs_vbl_chain
    beq.s   fs_vbl_unchained
    move.l  fs_vbl_chain,-(%sp)
    rts
fs_vbl_unchained:
    rte

| The keyboard/MIDI ACIA, vector $118 — MFP channel 6, whose vector number is the MFP's base (0x40)
| plus the channel, i.e. 70, i.e. $118. `boot_init` installs `acia_ikbd_isr` there at 0x14cc2,
| displacing TOS's own keyboard handler for the length of the run.
|
| THIS IS THE ENTRY THAT MAKES THE GAME PLAYABLE: every byte the front end and the frame loop read
| — the fire button that starts a game, the stick, the pause and abort keys — is written by the
| handler this reaches. There is no chain: the game takes the vector outright, which is why
| `tos_joyvec_handler` (../src/irq.c) is dead on the machine. The end-of-interrupt is the C's, not
| this file's — `hw_bclr8(MFP_ISRB, ...)` in the core, which shim_include/hw.h makes the real
| `bclr` — because WHERE in the handler it falls is the original's business and the reconstruction
| reproduces it.
    .globl  fs_acia_entry
fs_acia_entry:
    movem.l %d0-%d1/%a0-%a1,-(%sp)
    jsr     fs_acia_tick            | flyshark_main.c: counts it, dispatches on image[$118]
    movem.l (%sp)+,%d0-%d1/%a0-%a1
    rte
