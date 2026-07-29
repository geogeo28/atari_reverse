| game_os.s — GEMDOS PRG entry + trap wrappers for the playable BuggyBoy reconstruction.
|
| C ABI (m68k SysV): args at 4(%sp), 8(%sp), ...; each int/pointer 4 bytes; result in %d0.
| Each wrapper cleans only its own trap-frame pushes; the caller cleans the C args.
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
|
| NOTE: the file-I/O wrappers (Fopen..Fwrite) MUST come first, right after _start — matching the
| proven demo os.s layout. Placing the GEMDOS control wrappers (Super/Malloc/Crawio) before them
| makes Hatari's GEMDOS-HD hand back handle 0 (stdin) from Fopen, which then reads the keyboard
| (hang) / discards writes. Keep this order.

    .text
    .globl  _start
_start:
    | Keep the whole TPA (no Mshrink): GEMDOS leaves A7 at the top of our memory, well above the
    | 1 MiB BSS image, so the stack has room. Mshrinking to a tight size would strand the stack.
    jsr     game_main
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

| long Fcreate(const char *name, short attr)   GEMDOS 0x3c  (used by the SMOKE dump path)
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

| long Fwrite(short handle, long count, void *buf)   GEMDOS 0x40  (SMOKE dump path)
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

| long Physbase(void)           XBIOS 2
    .globl  Physbase
Physbase:
    movem.l %d2/%a2,-(%sp)  | TOS traps may trash d2/a2 — see the register note at the head of this file
    move.w  #2,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| void Vsync(void)              XBIOS 0x25
    .globl  Vsync
Vsync:
    movem.l %d2/%a2,-(%sp)  | TOS traps may trash d2/a2 — see the register note at the head of this file
    move.w  #0x25,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| void Dosound(const void *ptr)   XBIOS 0x20 (play a YM2149 sound command list; TOS steps it per VBL)
    .globl  Dosound
Dosound:
    movem.l %d2/%a2,-(%sp)  | TOS traps may trash d2/a2 — see the register note at the head of this file
    move.l  12(%sp),-(%sp)       | ptr -> command list
    move.w  #0x20,-(%sp)
    trap    #14
    lea     6(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

| void Setpalette(const void *pal16)    XBIOS 6
    .globl  Setpalette
Setpalette:
    movem.l %d2/%a2,-(%sp)  | TOS traps may trash d2/a2 — see the register note at the head of this file
    move.l  12(%sp),-(%sp)
    move.w  #6,-(%sp)
    trap    #14
    lea     6(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

| void Setcolor(int colornum, int color)   XBIOS 7 (set one palette register)
| args are passed in 4-byte slots; the value is the low word of each (big-endian stack).
    .globl  Setcolor
Setcolor:
    movem.l %d2/%a2,-(%sp)  | TOS traps may trash d2/a2 — see the register note at the head of this file
    move.w  18(%sp),-(%sp)       | color    (arg2 longword @ 8, low word @ 10)
    move.w  16(%sp),-(%sp)        | colornum (arg1 low word @ 6; +2 for the push above -> 8)
    move.w  #7,-(%sp)
    trap    #14
    lea     6(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Kbdvbase(void)           XBIOS 0x22 (KBDVBASE vector table)
    .globl  Kbdvbase
Kbdvbase:
    movem.l %d2/%a2,-(%sp)  | TOS traps may trash d2/a2 — see the register note at the head of this file
    move.w  #0x22,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Super(void *stack)       GEMDOS 0x20 (Super(0) -> enter supervisor mode, stay there)
    .globl  Super
Super:
    movem.l %d2/%a2,-(%sp)  | TOS traps may trash d2/a2 — see the register note at the head of this file
    move.l  12(%sp),-(%sp)
    move.w  #0x20,-(%sp)
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Malloc(long amount)      GEMDOS 0x48
    .globl  Malloc
Malloc:
    movem.l %d2/%a2,-(%sp)  | TOS traps may trash d2/a2 — see the register note at the head of this file
    move.l  12(%sp),-(%sp)
    move.w  #0x48,-(%sp)
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Crawio(short w)          GEMDOS 0x06 (w=0xff -> non-blocking raw console input poll)
| The C ABI passes `short` in a 4-byte slot; on big-endian m68k the value is the LOW word at 6(sp),
| not 4(sp). Read the longword and push its low word (same idiom as Fcreate/Fopen).
    .globl  Crawio
Crawio:
    movem.l %d2/%a2,-(%sp)  | TOS traps may trash d2/a2 — see the register note at the head of this file
    move.l  12(%sp),%d0          | w (int); low word is the value
    move.w  %d0,-(%sp)
    move.w  #0x06,-(%sp)
    trap    #1
    addq.l  #4,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Crawcin(void)            GEMDOS 0x07 (blocking raw console input, no echo)
    .globl  Crawcin
Crawcin:
    movem.l %d2/%a2,-(%sp)  | TOS traps may trash d2/a2 — see the register note at the head of this file
    move.w  #0x07,-(%sp)
    trap    #1
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| joy_handler — installed at KBDVBASE joyvec (+0x18). The IKBD interrupt enters here with A0
| pointing at the 2-byte joystick packet. Save the old input_state to input_prev, then copy the
| packet's two bytes into input_state (hi = joy0, lo = joy1). Mirrors the game's own 0x12156
| handler, but writes to the image via `input_state_ptr` (a C global) instead of a baked address.
    .globl  joy_handler
    .extern input_state_ptr
joy_handler:
    move.l  input_state_ptr,%a1  | &input_state in the image
    move.w  (%a1),-2(%a1)        | input_prev = input_state
    move.b  (%a0)+,(%a1)+        | input_state hi = joy0
    move.b  (%a0)+,(%a1)+        | input_state lo = joy1
    rts
