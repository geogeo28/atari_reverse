| os.s — GEMDOS PRG entry + trap wrappers for every remaster on-target program: BUGGYBOY.PRG and the
| harness/measurement variants build_game.sh emits from the same shell, plus bench.elf (bench_build.sh).
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
    move.l  4(%sp),basepage     | GEMDOS hands a child its BASPAG pointer at 4(sp) (the Pexec convention);
                                | game_main.c reads p_bbase/p_blen/p_hitpa out of it to find the free TPA.
    move.l  %sp,initial_sp      | ... and starts the stack at the top of that TPA. Captured so the free-TPA
                                | window can be floored by the LOWER of p_hitpa and the real stack.
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

| void Dosound(const void *ptr)   XBIOS 32 (play a YM2149 command list; TOS steps it per VBL)
| The race-start countdown beeps + the engine idle go through this, exactly as the original (main
| @0x1021c). TOS's own kept _vblqueue entries advance the list — see the sound install in game_main.c.
    .globl  Dosound
Dosound:
    move.l  4(%sp),-(%sp)       | list pointer
    move.w  #32,-(%sp)
    trap    #14
    addq.l  #6,%sp
    rts

| long Supexec(long (*func)(void))   XBIOS 38 (run func in supervisor mode, return to the caller's mode)
| The shell is a user-mode GEMDOS program, but installing the VBL sound handler touches the TOS VBL
| queue (_vblqueue/_nvbls at 0x456/0x454) and conterm (0x484) — all supervisor-only low memory. Rather
| than flip the whole program supervisor (which would run the GEMDOS SCREEN.BIN dumps supervisor and
| risk the handle-0 GEMDOS-HD bug this file's header warns about), the install runs in one brief
| Supexec excursion; the VBL handler itself already runs supervisor (TOS calls the queue at interrupt).
    .globl  Supexec
Supexec:
    move.l  4(%sp),-(%sp)       | func pointer
    move.w  #38,-(%sp)
    trap    #14
    addq.l  #6,%sp
    rts

| --- held keys + IKBD packet parsing --------------------------------------------------------------
| The GEMDOS console reports key PRESSES; driving needs to know which keys are HELD, and several at
| once (throttle plus steering), PLUS the joystick. So the game takes the IKBD ACIA interrupt itself
| (MFP channel 6, vector 0x46 @ 0x118). Mouse reporting is switched off (kbd_install), but joystick
| reporting is kept, so the ACIA delivers two kinds of message and this handler is a small packet
| state machine, not a bare scancode reader:
|   * a keyboard make/break is a single byte < 0xF6 (break codes = scancode|0x80 top out at 0xF2):
|       bit 7 clear -> that scancode is now down;  bit 7 set -> it is up  (key_down[] / key_hit[]).
|   * an IKBD report is a header 0xF6..0xFF followed by a fixed-length payload (ikbd_pkt_payload). The
|     joystick INTERROGATE reply is a 0xFD both-sticks report: header, then the joystick-0 byte, then the
|     joystick-1 byte. Only that FINAL byte (joystick 1, the ST's game port) is stored to joy_state — the
|     byte read_input reads, its bits (up 1 / down 2 / left 4 / right 8 / fire 0x80) byte-identical to the
|     RM_IN_* word; the joystick-0 byte is swallowed, so a mouse-port stick never briefly leaks into it.
|     Every other report's payload is swallowed too: mouse packets never reach key_down[], and the
|     event-mode single-stick reports (0xFE joy0 / 0xFF joy1) — which mode 0x15 stops the IKBD from ever
|     sending, so only interrogate replies arrive (see kbd_install) — never store the wrong port. IKBD
|     reports arrive byte-contiguous, so pkt_left tracks a report cleanly across interrupts without a
|     scancode interleaving mid-payload.
| C polls key_down[] / joy_state once a frame. Interrupt handlers run in supervisor mode, no mode juggling.
    .globl  kbd_isr
kbd_isr:
    movem.l %d0/%d1/%a0/%a1,-(%sp)
    btst    #0,0xfffffc00       | IKBD ACIA status: receive buffer full?
    beq     kbd_eoi
    moveq   #0,%d0
    move.b  0xfffffc02,%d0      | the received byte

    tst.b   pkt_left            | mid-report? then this byte is one of its payload bytes
    beq.s   kbd_header_or_key
    tst.b   pkt_join            | a 0xFD joystick report? (only its payload is stored)
    beq.s   kbd_swallow         | no (mouse/other/0xFE/0xFF): swallow the payload byte
    cmpi.b  #1,pkt_left         | store ONLY the final payload byte = joystick 1 (the game port);
    bne.s   kbd_swallow         | the joystick-0 byte (pkt_left==2 here) is never briefly visible
    move.b  %d0,joy_state
kbd_swallow:
    subq.b  #1,pkt_left
    bra     kbd_eoi

kbd_header_or_key:
    cmpi.b  #0xf6,%d0           | 0xF6..0xFF is an IKBD report header (keyboard break codes stop at 0xF2)
    bcs.s   kbd_scancode        | below 0xF6 -> a keyboard make/break scancode
    move.w  %d0,%d1
    subi.w  #0xf6,%d1           | index 0..9 into the payload-length table
    lea     ikbd_pkt_payload,%a1
    move.b  (%a1,%d1.w),pkt_left  | payload bytes to expect for this report
    moveq   #0,%d1              | pkt_join set ONLY for a 0xFD report (both sticks): its final byte is
    cmpi.b  #0xfd,%d0           | stored. 0xFE/0xFF (single-stick, event mode) and every other report
    bne.s   kbd_set_join        | are swallowed — 0xFE's lone byte is joystick 0, so storing it would
    moveq   #1,%d1              | leak the wrong port; with mode 0x15 pinned neither ever arrives anyway.
kbd_set_join:
    move.b  %d1,pkt_join
    bra     kbd_eoi

kbd_scancode:
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

    .align  2
| IKBD report payload lengths (bytes AFTER the header), indexed by header - 0xF6 (standard HD6301
| protocol). Only the joystick report (0xFD) can actually arrive here — mouse, clock and status
| reporting are never enabled (kbd_install sends mouse-off + joystick-interrogation-mode 0x15, so only
| an 0x16-interrogate reply comes back) — so the other rows are defensive: they let a stray report's
| payload be swallowed rather than mis-read as scancodes. (.rodata folds into .text per tos.ld; sits
| after the rte, never executed.)
ikbd_pkt_payload:
    .byte 7                     | 0xF6 status report
    .byte 5                     | 0xF7 absolute mouse position
    .byte 2                     | 0xF8 relative mouse (buttons 00)
    .byte 2                     | 0xF9 relative mouse
    .byte 2                     | 0xFA relative mouse
    .byte 2                     | 0xFB relative mouse (buttons 11)
    .byte 6                     | 0xFC time-of-day
    .byte 2                     | 0xFD joystick, both sticks (joy0, joy1)
    .byte 1                     | 0xFE joystick 0
    .byte 1                     | 0xFF joystick 1
    .align  2

    .bss
    .align  2
| Captured by _start (above), read by game_main.c's TPA map. FIRST in this .bss block so the two longs
| stay word-aligned whatever the byte-sized state below grows to.
    .globl  basepage
basepage:
    .space  4                   | GEMDOS BASPAG of this process (4(sp) at entry)
    .globl  initial_sp
initial_sp:
    .space  4                   | the stack pointer GEMDOS handed _start (top of the TPA)
    .globl  key_down
key_down:
    .space  128                 | one byte per scancode: nonzero while held
    .globl  key_hit
key_hit:
    .space  128                 | one byte per scancode: latched press, cleared by the C that reads it
    .globl  joy_state
joy_state:
    .space  1                   | joystick 1 (game port): the final byte of the last 0xFD reply kbd_isr saw
pkt_left:
    .space  1                   | IKBD report payload bytes still expected (0 = idle: header or scancode next)
pkt_join:
    .space  1                   | nonzero while a 0xFD joystick report's payload is in progress
    .even                       | keep this .bss EVEN-sized: tos.ld packs the next object's .bss right
                                | after it (SUBALIGN(1), no gap), so an odd size would shift every
                                | word-aligned global downstream odd -> a move.w address-errors at boot.
