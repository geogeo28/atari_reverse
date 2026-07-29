| os.s — GEMDOS PRG entry + trap wrappers for the leg-results demo.
|
| C ABI (m68k SysV): args on the stack at 4(%sp), 8(%sp), ...; each int/pointer is 4 bytes;
| integer/pointer results returned in %d0 (so pointer-returning traps are declared `long` in C
| and cast). Each wrapper cleans only its own trap-frame pushes; the caller cleans the C args.
|
| REGISTERS — the one place the two calling conventions DISAGREE:
|   GCC (m68k SysV): %d0/%d1/%a0/%a1 scratch; %d2-%d7 and %a2-%a6 CALLEE-SAVED, so the compiler caches
|                    live values in %d2/%a2 across a call to any wrapper here.
|   TOS (GEMDOS/BIOS/XBIOS): preserves only %d3-%d7 and %a3-%a6 — %d0-%d2 and %a0-%a2 are VOLATILE.
| So %d2/%a2 are exactly what GCC expects to survive and TOS may destroy. Every wrapper below saves and
| restores that pair around its trap (hence each reads its C arguments at +8). Skipping it does not fail
| loudly — it silently corrupts one live variable in the CALLER. That shipped a real 3-bombs-on-hardware
| bug in remaster/render/atari/os.s (TOS's Ikbdws returned phystop-1 in %d2 while GCC was caching a
| pointer there); EmuTOS leaves a benign value, so every Hatari pin stayed green. See that file's header.

    .text
    .globl  _start
_start:
    jsr     main
    clr.w   -(%sp)              | Pterm0 (GEMDOS 0x00): terminate
    trap    #1

| long Fopen(const char *name, short mode)      GEMDOS 0x3d
    .globl  Fopen
Fopen:
    movem.l %d2/%a2,-(%sp)  | TOS traps may trash d2/a2 — see the register note at the head of this file
    move.l  12(%sp),%d1          | name
    move.l  16(%sp),%d0          | mode (int); low word is the value
    move.w  %d0,-(%sp)
    move.l  %d1,-(%sp)
    move.w  #0x3d,-(%sp)
    trap    #1
    lea     8(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Fread(short handle, long count, void *buf)   GEMDOS 0x3f
    .globl  Fread
Fread:
    movem.l %d2/%a2,-(%sp)  | TOS traps may trash d2/a2 — see the register note at the head of this file
    move.l  20(%sp),%a1         | buf
    move.l  16(%sp),%d1          | count
    move.l  12(%sp),%d0          | handle (int); low word
    move.l  %a1,-(%sp)
    move.l  %d1,-(%sp)
    move.w  %d0,-(%sp)
    move.w  #0x3f,-(%sp)
    trap    #1
    lea     12(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Fclose(short handle)     GEMDOS 0x3e
    .globl  Fclose
Fclose:
    movem.l %d2/%a2,-(%sp)  | TOS traps may trash d2/a2 — see the register note at the head of this file
    move.l  12(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #0x3e,-(%sp)
    trap    #1
    addq.l  #4,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Fcreate(const char *name, short attr)   GEMDOS 0x3c
    .globl  Fcreate
Fcreate:
    movem.l %d2/%a2,-(%sp)  | TOS traps may trash d2/a2 — see the register note at the head of this file
    move.l  12(%sp),%d1          | name
    move.l  16(%sp),%d0          | attr (int); low word
    move.w  %d0,-(%sp)
    move.l  %d1,-(%sp)
    move.w  #0x3c,-(%sp)
    trap    #1
    lea     8(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Fwrite(short handle, long count, void *buf)   GEMDOS 0x40
    .globl  Fwrite
Fwrite:
    movem.l %d2/%a2,-(%sp)  | TOS traps may trash d2/a2 — see the register note at the head of this file
    move.l  20(%sp),%a1         | buf
    move.l  16(%sp),%d1          | count
    move.l  12(%sp),%d0          | handle (int); low word
    move.l  %a1,-(%sp)
    move.l  %d1,-(%sp)
    move.w  %d0,-(%sp)
    move.w  #0x40,-(%sp)
    trap    #1
    lea     12(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Cconin(void)             GEMDOS 0x01 (blocks for a key)
    .globl  Cconin
Cconin:
    movem.l %d2/%a2,-(%sp)  | TOS traps may trash d2/a2 — see the register note at the head of this file
    move.w  #1,-(%sp)
    trap    #1
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Physbase(void)           XBIOS 2 (physical screen base)
    .globl  Physbase
Physbase:
    movem.l %d2/%a2,-(%sp)  | TOS traps may trash d2/a2 — see the register note at the head of this file
    move.w  #2,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| void Setpalette(const void *pal16)    XBIOS 6 (load all 16 colour registers)
    .globl  Setpalette
Setpalette:
    movem.l %d2/%a2,-(%sp)  | TOS traps may trash d2/a2 — see the register note at the head of this file
    move.l  12(%sp),-(%sp)
    move.w  #6,-(%sp)
    trap    #14
    lea     6(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts
