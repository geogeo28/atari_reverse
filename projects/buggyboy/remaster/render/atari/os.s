| os.s — GEMDOS PRG entry + trap wrappers for the remaster HUD demo.
| Copied from recreate/render/atari/os.s (generic GEMDOS glue).
|
| C ABI (m68k SysV): args on the stack at 4(%sp), 8(%sp), ...; each int/pointer is 4 bytes;
| integer/pointer results returned in %d0 (so pointer-returning traps are declared `long` in C
| and cast). Each wrapper cleans only its own trap-frame pushes; the caller cleans the C args.
|
| ORDER MATTERS — keep the file-I/O wrappers (Fcreate/Fopen/Fread/Fwrite/Fclose) together and FIRST,
| immediately after _start. Putting other wrappers ahead of or between them made Hatari's GEMDOS-HD
| return handle 0 (stdin) from Fopen in a large .PRG instead of a real handle, so Fread then read the
| keyboard and the graphics unpack spun forever waiting for its end marker. That cost a long debug in
| recreate's game_os.s, whose layout this mirrors. Add new non-file wrappers BELOW this block.

    .text
    .globl  _start
_start:
    jsr     main
    clr.w   -(%sp)              | Pterm0 (GEMDOS 0x00): terminate
    trap    #1

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

| long Fopen(const char *name, short mode)     GEMDOS 0x3d  (mode 0 = read-only)
    .globl  Fopen
Fopen:
    move.l  4(%sp),%d1          | name
    move.l  8(%sp),%d0          | mode (int); low word
    move.w  %d0,-(%sp)
    move.l  %d1,-(%sp)
    move.w  #0x3d,-(%sp)
    trap    #1
    lea     8(%sp),%sp
    rts

| long Fread(short handle, long count, void *buf)    GEMDOS 0x3f
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

| long Fclose(short handle)     GEMDOS 0x3e
    .globl  Fclose
Fclose:
    move.l  4(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #0x3e,-(%sp)
    trap    #1
    addq.l  #4,%sp
    rts

| long Cconws(const char *s)    GEMDOS 0x09 (write a NUL-terminated string to the console)
    .globl  Cconws
Cconws:
    move.l  4(%sp),-(%sp)
    move.w  #9,-(%sp)
    trap    #1
    lea     6(%sp),%sp
    rts

| long Cconin(void)             GEMDOS 0x01 (blocks for a key)
    .globl  Cconin
Cconin:
    move.w  #1,-(%sp)
    trap    #1
    addq.l  #2,%sp
    rts

| long Cconis(void)             GEMDOS 0x0b (non-blocking: -1 if a key is waiting, else 0)
    .globl  Cconis
Cconis:
    move.w  #0x0b,-(%sp)
    trap    #1
    addq.l  #2,%sp
    rts

| void Vsync(void)              XBIOS 37 (wait for the next vertical blank)
    .globl  Vsync
Vsync:
    move.w  #37,-(%sp)
    trap    #14
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

| long Setcolor(short idx, short color)   XBIOS 7 (color -1 reads without writing; returns the old value)
    .globl  Setcolor
Setcolor:
    move.w  10(%sp),%d1         | color (low word of the int arg)
    move.w  6(%sp),%d0          | index (low word of the int arg)
    move.w  %d1,-(%sp)
    move.w  %d0,-(%sp)
    move.w  #7,-(%sp)
    trap    #14
    addq.l  #6,%sp
    rts

| long Setscreen(long logLoc, long physLoc, short rez)   XBIOS 5 (rez/-1 leaves it; latches at vblank)
    .globl  Setscreen
Setscreen:
    move.l  4(%sp),%a0          | logLoc
    move.l  8(%sp),%a1          | physLoc
    move.w  14(%sp),%d0         | rez (low word of the int arg)
    move.w  %d0,-(%sp)
    move.l  %a1,-(%sp)
    move.l  %a0,-(%sp)
    move.w  #5,-(%sp)
    trap    #14
    lea     12(%sp),%sp
    rts

| long Setexc(short number, long vector)   BIOS 5 (install an exception vector; returns the old one)
    .globl  Setexc
Setexc:
    move.l  8(%sp),%d1          | vector
    move.l  4(%sp),%d0          | vector number (int); low word
    move.l  %d1,-(%sp)
    move.w  %d0,-(%sp)
    move.w  #5,-(%sp)
    trap    #13
    lea     8(%sp),%sp
    rts

| void Ikbdws(short count_m1, const void *buf)   XBIOS 25 (send count_m1+1 bytes to the IKBD)
    .globl  Ikbdws
Ikbdws:
    move.l  8(%sp),%a0          | buf
    move.l  4(%sp),%d0          | byte count - 1 (int); low word
    move.l  %a0,-(%sp)
    move.w  %d0,-(%sp)
    move.w  #25,-(%sp)
    trap    #14
    lea     8(%sp),%sp
    rts

| --- held-key tracking ------------------------------------------------------------------------
| The GEMDOS console reports key PRESSES; driving needs to know which keys are HELD, and several at
| once (throttle plus steering). So the demo takes the IKBD ACIA interrupt itself (MFP channel 6,
| vector 0x46 @ 0x118). With mouse and joystick reporting switched off (kbd_install), the ACIA
| delivers nothing but keyboard make/break scancodes, so the handler is simply:
|   bit 7 clear -> that scancode is now down;  bit 7 set -> it is up.
| C polls key_down[] once a frame. Interrupt handlers run in supervisor mode, so no mode juggling.
    .globl  kbd_isr
kbd_isr:
    movem.l %d0/%d1/%a0/%a1,-(%sp)
    btst    #0,0xfffffc00       | IKBD ACIA status: receive buffer full?
    beq.s   kbd_eoi
    moveq   #0,%d0
    move.b  0xfffffc02,%d0      | scancode; bit 7 = break (key released)
    .ifdef  KBD_RAWLOG
    | Debug (--defsym KBD_RAWLOG=1): record EVERY byte the ACIA delivers, in arrival order, before
    | it is interpreted as a scancode. That is the ground truth for whether non-keyboard packets
    | (mouse/joystick reports) are still coming through and being indexed into key_down[].
    move.w  kbd_raw_pos,%d1
    cmpi.w  #KBD_RAW_MAX,%d1
    bge.s   kbd_nolog
    lea     kbd_raw_log,%a1
    move.b  %d0,(%a1,%d1.w)
    addq.w  #1,%d1
    move.w  %d1,kbd_raw_pos
kbd_nolog:
    .endif
    lea     key_down,%a0
    btst    #7,%d0
    bne.s   kbd_break
    move.b  #1,(%a0,%d0.w)      | held state: set on make, cleared on break
    lea     key_hit,%a1
    move.b  #1,(%a1,%d0.w)      | latched press: set on make, cleared only by the C that consumes it
    bra.s   kbd_eoi
kbd_break:
    andi.w  #0x7f,%d0
    clr.b   (%a0,%d0.w)
kbd_eoi:
    move.b  #0xbf,0xfffffa11    | MFP ISRB: clear the in-service bit for channel 6 (write 0 to it)
    movem.l (%sp)+,%d0/%d1/%a0/%a1
    rte

    .bss
    .align  2
    .globl  key_down
key_down:
    .space  128                 | one byte per scancode: nonzero while held
    .globl  key_hit
key_hit:
    .space  128                 | one byte per scancode: latched press, cleared by the C that reads it

    .ifdef  KBD_RAWLOG
    .equ    KBD_RAW_MAX,4096
    .align  2
    .globl  kbd_raw_pos
kbd_raw_pos:
    .space  2                   | bytes logged so far (stops at KBD_RAW_MAX)
    .globl  kbd_raw_log
kbd_raw_log:
    .space  KBD_RAW_MAX
    .endif
