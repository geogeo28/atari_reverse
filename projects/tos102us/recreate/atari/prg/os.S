| os.S — the GEMDOS entry point and every TOS trap wrapper TOSTEST.PRG and TOSBENCH.PRG use.
|
| C ABI (m68k SysV): arguments at 4(%sp), 8(%sp), ...; every int and pointer occupies four bytes,
| so a `short` argument is the LOW word of its slot; the result comes back in %d0.
|
| REGISTERS — where the two conventions disagree, and it is not cosmetic:
|   GCC (m68k SysV): %d0/%d1/%a0/%a1 scratch; %d2-%d7 and %a2-%a6 CALLEE-SAVED, so the compiler
|                    caches live values in %d2/%a2 across a call to any wrapper below.
|   TOS (GEMDOS/BIOS/XBIOS): preserves only %d3-%d7 and %a3-%a6.
| %d2/%a2 are therefore exactly the pair GCC expects to survive and TOS may destroy, and every
| wrapper here saves and restores it around its trap — which is why each reads its first C argument
| at +12 and not +4. Skipping it does not fail loudly: it silently corrupts one live variable in the
| CALLER, and it shipped a three-bombs-on-hardware bug in this workspace's BuggyBoy build
| (docs/on-target-execution.md, bug class 3). tools/assert_trap_registers.sh is the scan that checks
| it, and ../Makefile runs it over this file on every build.
|
| EVERY WRAPPER HERE HAS A C CALL SITE, and one that stops having one is deleted rather than kept
| "in case": an unused wrapper is code no differential and no ledger ever executes, which makes it
| the one place a register-discipline mistake can sit unseen until the day something calls it.
| Mshrink and Super are absent for that reason even though _start issues both traps inline.
|
| THE FILE-I/O WRAPPERS COME FIRST, right after _start, matching the proven BuggyBoy, Joust, Wonder
| Boy, BLACK ICE and Zynaps layouts: placing the GEMDOS control wrappers (Super/Pterm) ahead of them
| makes Hatari's GEMDOS-HD emulation hand back handle 0 from Fopen, which then reads the keyboard.
| These programs boot off a real floppy image rather than a GEMDOS drive, so the trap is not live
| here — the order is kept because a later mode that does use one would meet it.

    GEMDOS_PTERM    = 0x4c
    GEMDOS_GETMPB   = 0x14
    GEMDOS_FSETDTA  = 0x1a
    GEMDOS_SUPER    = 0x20
    GEMDOS_TGETDATE = 0x2a
    GEMDOS_SVERSION = 0x30
    GEMDOS_FOPEN    = 0x3d
    GEMDOS_FCLOSE   = 0x3e
    GEMDOS_FREAD    = 0x3f
    GEMDOS_MALLOC   = 0x48
    GEMDOS_MFREE    = 0x49
    GEMDOS_MSHRINK  = 0x4a
    GEMDOS_FSFIRST  = 0x4e
    GEMDOS_FSNEXT   = 0x4f

    BIOS_BCONOUT    = 0x03
    BIOS_DRVMAP     = 0x0a
    BIOS_KBSHIFT    = 0x0b

    XBIOS_PHYSBASE  = 0x02
    XBIOS_LOGBASE   = 0x03
    XBIOS_GETREZ    = 0x04

    | Basepage offsets, for the Mshrink _start performs.
    BP_TLEN         = 0x0c
    BP_DLEN         = 0x14
    BP_BLEN         = 0x1c
    BP_BYTES        = 0x100
    | What the program keeps above its own BSS for the supervisor stack it then runs on. 8 KB is
    | far more than these two programs nest, and it is the ONLY slack: everything above the shrink
    | goes back to GEMDOS, which is what makes the Malloc records in TOSTEST mean anything at all.
    STACK_BYTES     = 0x2000

    .text
    .globl  _start
_start:
    | GEMDOS puts the basepage pointer at 4(sp) and leaves the whole TPA ours. Hand back everything
    | above text+data+bss+stack, so that GEMDOS has a free pool for Malloc to allocate out of; with
    | no Mshrink at all, Malloc has nothing to give and every allocation record would read 0.
    move.l  4(%sp),%a3                  | basepage (a3: TOS preserves it across the traps below)
    move.l  BP_TLEN(%a3),%d3
    add.l   BP_DLEN(%a3),%d3
    add.l   BP_BLEN(%a3),%d3
    add.l   #BP_BYTES + STACK_BYTES,%d3 | what we keep, basepage included
    | The stack goes at the top of the kept block, even: the 68000 faults on an odd stack pointer.
    move.l  %a3,%d4
    add.l   %d3,%d4
    and.l   #-2,%d4
    move.l  %d4,%sp

    move.l  %d3,-(%sp)                  | Mshrink(0, basepage, keep)
    move.l  %a3,-(%sp)
    clr.w   -(%sp)
    move.w  #GEMDOS_MSHRINK,-(%sp)
    trap    #1
    lea     12(%sp),%sp

    | Supervisor mode for the rest of the program, and no way back — see tosapi.h. Super(0) leaves
    | the stack pointer where it is, so the block reserved above is the supervisor stack from here.
    clr.l   -(%sp)
    move.w  #GEMDOS_SUPER,-(%sp)
    trap    #1
    addq.l  #6,%sp

    jsr     prg_main                    | the program's exit code, which Pterm passes to the shell
    move.w  %d0,-(%sp)
    move.w  #GEMDOS_PTERM,-(%sp)
    trap    #1

| ---------------------------------------------------------------- GEMDOS file I/O (trap #1) ----

| long Fopen(const char *name, short mode)          GEMDOS 0x3d
    .globl  Fopen
Fopen:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d1                 | name
    move.l  16(%sp),%d0                 | mode — the value is the LOW word of the 4-byte slot
    move.w  %d0,-(%sp)
    move.l  %d1,-(%sp)
    move.w  #GEMDOS_FOPEN,-(%sp)
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

| long Fread(short handle, long count, void *buffer) GEMDOS 0x3f
    .globl  Fread
Fread:
    movem.l %d2/%a2,-(%sp)
    move.l  20(%sp),%a1                 | buffer
    move.l  16(%sp),%d1                 | count
    move.l  12(%sp),%d0                 | handle
    move.l  %a1,-(%sp)
    move.l  %d1,-(%sp)
    move.w  %d0,-(%sp)
    move.w  #GEMDOS_FREAD,-(%sp)
    trap    #1
    lea     12(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Fsfirst(const char *pattern, short attr)     GEMDOS 0x4e
    .globl  Fsfirst
Fsfirst:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d1                 | pattern
    move.l  16(%sp),%d0                 | attr
    move.w  %d0,-(%sp)
    move.l  %d1,-(%sp)
    move.w  #GEMDOS_FSFIRST,-(%sp)
    trap    #1
    lea     8(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Fsnext(void)                                 GEMDOS 0x4f
    .globl  Fsnext
Fsnext:
    movem.l %d2/%a2,-(%sp)
    move.w  #GEMDOS_FSNEXT,-(%sp)
    trap    #1
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Fsetdta(void *dta)                           GEMDOS 0x1a
    .globl  Fsetdta
Fsetdta:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)
    move.w  #GEMDOS_FSETDTA,-(%sp)
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| ---------------------------------------------------------------- GEMDOS, the rest (trap #1) ---

| long Sversion(void)                               GEMDOS 0x30
    .globl  Sversion
Sversion:
    movem.l %d2/%a2,-(%sp)
    move.w  #GEMDOS_SVERSION,-(%sp)
    trap    #1
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Tgetdate(void)                               GEMDOS 0x2a
    .globl  Tgetdate
Tgetdate:
    movem.l %d2/%a2,-(%sp)
    move.w  #GEMDOS_TGETDATE,-(%sp)
    trap    #1
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Getmpb(void *mpb)                            GEMDOS 0x14
    .globl  Getmpb
Getmpb:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)
    move.w  #GEMDOS_GETMPB,-(%sp)
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Malloc(long bytes)                           GEMDOS 0x48
    .globl  Malloc
Malloc:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)
    move.w  #GEMDOS_MALLOC,-(%sp)
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Mfree(void *block)                           GEMDOS 0x49
    .globl  Mfree
Mfree:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)
    move.w  #GEMDOS_MFREE,-(%sp)
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| ---------------------------------------------------------------- BIOS (trap #13) --------------

| long Bconout(short device, short character)       BIOS 0x03
    .globl  Bconout
Bconout:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d1                 | device
    move.l  16(%sp),%d0                 | character
    move.w  %d0,-(%sp)
    move.w  %d1,-(%sp)
    move.w  #BIOS_BCONOUT,-(%sp)
    trap    #13
    lea     6(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Drvmap(void)                                 BIOS 0x0a
    .globl  Drvmap
Drvmap:
    movem.l %d2/%a2,-(%sp)
    move.w  #BIOS_DRVMAP,-(%sp)
    trap    #13
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Kbshift(short mode)                          BIOS 0x0b
    .globl  Kbshift
Kbshift:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #BIOS_KBSHIFT,-(%sp)
    trap    #13
    addq.l  #4,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| ---------------------------------------------------------------- XBIOS (trap #14) -------------

| long Physbase(void)                               XBIOS 0x02
    .globl  Physbase
Physbase:
    movem.l %d2/%a2,-(%sp)
    move.w  #XBIOS_PHYSBASE,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Logbase(void)                                XBIOS 0x03
    .globl  Logbase
Logbase:
    movem.l %d2/%a2,-(%sp)
    move.w  #XBIOS_LOGBASE,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Getrez(void)                                 XBIOS 0x04
    .globl  Getrez
Getrez:
    movem.l %d2/%a2,-(%sp)
    move.w  #XBIOS_GETREZ,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts
