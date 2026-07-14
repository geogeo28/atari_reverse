| os.s — GEMDOS PRG entry + trap wrappers for the leg-results demo.
|
| C ABI (m68k SysV): args on the stack at 4(%sp), 8(%sp), ...; each int/pointer is 4 bytes;
| integer/pointer results returned in %d0 (so pointer-returning traps are declared `long` in C
| and cast). Each wrapper cleans only its own trap-frame pushes; the caller cleans the C args.

    .text
    .globl  _start
_start:
    jsr     main
    clr.w   -(%sp)              | Pterm0 (GEMDOS 0x00): terminate
    trap    #1

| long Fopen(const char *name, short mode)      GEMDOS 0x3d
    .globl  Fopen
Fopen:
    move.l  4(%sp),%d1          | name
    move.l  8(%sp),%d0          | mode (int); low word is the value
    move.w  %d0,-(%sp)
    move.l  %d1,-(%sp)
    move.w  #0x3d,-(%sp)
    trap    #1
    lea     8(%sp),%sp
    rts

| long Fread(short handle, long count, void *buf)   GEMDOS 0x3f
    .globl  Fread
Fread:
    move.l  12(%sp),%a1         | buf
    move.l  8(%sp),%d1          | count
    move.l  4(%sp),%d0          | handle (int); low word
    move.l  %a1,-(%sp)
    move.l  %d1,-(%sp)
    move.w  %d0,-(%sp)
    move.w  #0x3f,-(%sp)
    trap    #1
    lea     12(%sp),%sp
    rts

| long Fclose(short handle)     GEMDOS 0x3e
    .globl  Fclose
Fclose:
    move.l  4(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #0x3e,-(%sp)
    trap    #1
    addq.l  #4,%sp
    rts

| long Fcreate(const char *name, short attr)   GEMDOS 0x3c
    .globl  Fcreate
Fcreate:
    move.l  4(%sp),%d1          | name
    move.l  8(%sp),%d0          | attr (int); low word
    move.w  %d0,-(%sp)
    move.l  %d1,-(%sp)
    move.w  #0x3c,-(%sp)
    trap    #1
    lea     8(%sp),%sp
    rts

| long Fwrite(short handle, long count, void *buf)   GEMDOS 0x40
    .globl  Fwrite
Fwrite:
    move.l  12(%sp),%a1         | buf
    move.l  8(%sp),%d1          | count
    move.l  4(%sp),%d0          | handle (int); low word
    move.l  %a1,-(%sp)
    move.l  %d1,-(%sp)
    move.w  %d0,-(%sp)
    move.w  #0x40,-(%sp)
    trap    #1
    lea     12(%sp),%sp
    rts

| long Cconin(void)             GEMDOS 0x01 (blocks for a key)
    .globl  Cconin
Cconin:
    move.w  #1,-(%sp)
    trap    #1
    addq.l  #2,%sp
    rts

| long Physbase(void)           XBIOS 2 (physical screen base)
    .globl  Physbase
Physbase:
    move.w  #2,-(%sp)
    trap    #14
    addq.l  #2,%sp
    rts

| void Setpalette(const void *pal16)    XBIOS 6 (load all 16 colour registers)
    .globl  Setpalette
Setpalette:
    move.l  4(%sp),-(%sp)
    move.w  #6,-(%sp)
    trap    #14
    lea     6(%sp),%sp
    rts
