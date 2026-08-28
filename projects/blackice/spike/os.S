| os.S — GEMDOS entry and the TOS trap wrappers the raycast spike needs.
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
| real three-bombs-on-hardware bug in the BuggyBoy build. Copied from
| projects/wonderboy/recreate/atari/wonderboy_os.s, which is canonical for the gotcha.
|
| NOTE: the file-I/O wrappers (Fcreate..Fwrite) MUST come first, right after _start — matching the
| proven BuggyBoy, Joust and Wonder Boy layout. Placing the GEMDOS control wrappers (Super/Pterm)
| before them makes Hatari's GEMDOS-HD hand back handle 0 (stdin) from Fopen, which then reads the
| keyboard (hang) or discards writes. Keep this order.

    GEMDOS_PTERM0   = 0x00
    GEMDOS_CCONWS   = 0x09
    GEMDOS_SUPER    = 0x20
    GEMDOS_FCREATE  = 0x3c
    GEMDOS_FCLOSE   = 0x3e
    GEMDOS_FWRITE   = 0x40
    XBIOS_PHYSBASE  = 0x02

    .text
    .globl  _start
_start:
    | Keep the whole TPA (no Mshrink): GEMDOS leaves %a7 at the top of our memory, well above the
    | BSS image and above SPIKE_LEDGER_ADDR, so both the stack and the fixed ledger have room.
    jsr     spike_main
    clr.w   -(%sp)                  | Pterm0
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
    move.w  #GEMDOS_FCREATE,-(%sp)
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
    move.w  #GEMDOS_FCLOSE,-(%sp)
    trap    #1
    addq.l  #4,%sp
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
    move.w  #GEMDOS_FWRITE,-(%sp)
    trap    #1
    lea     12(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

| ------------------------------------------------------------ GEMDOS control (trap #1) --------

| void Cconws(const char *s)                        GEMDOS 0x09
    .globl  Cconws
Cconws:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)
    move.w  #GEMDOS_CCONWS,-(%sp)
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Super(void *stack)       GEMDOS 0x20 — Super(0) ENTERS supervisor and returns the old SSP.
| The way BACK is spike_leave_supervisor below and NOT this routine; the paragraph there says why.
    .globl  Super
Super:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)
    move.w  #GEMDOS_SUPER,-(%sp)
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long spike_leave_supervisor(void *ssp)   GEMDOS 0x20 again — the RETURN half, made safe.
|
| TOS goes back to user mode by loading %a7 from the USER stack pointer, and the USP it uses is the
| one FROZEN when `Super(0)` was called — it does not set the USP from the supervisor stack on the
| way out. So a plain `Super(ssp)` returns onto the stack position the FIRST call stood at, and the
| wrapper's own unwind reads from there; that is right only while the compiler leaves %sp at the
| SAME depth at both call sites, which m68k GCC does not promise. This sets the USER stack pointer
| to the supervisor stack it is standing on, one instruction before the trap, which makes the return
| independent of where either call was made. The measurement behind this is in
| projects/wonderboy/recreate/atari/wonderboy_os.s, which is canonical for it.
    .globl  spike_leave_supervisor
spike_leave_supervisor:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)          | the SSP Super(0) handed back
    move.w  #GEMDOS_SUPER,-(%sp)
    move.l  %sp,%a0
    move.l  %a0,%usp                | ...so the return lands %a7 exactly here, whatever GCC did
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| ------------------------------------------------------------------ XBIOS (trap #14) ----------

| long Physbase(void)           XBIOS 0x02 — the screen the shifter is really displaying from.
    .globl  Physbase
Physbase:
    movem.l %d2/%a2,-(%sp)
    move.w  #XBIOS_PHYSBASE,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts
