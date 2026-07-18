| game_os.s — GEMDOS PRG entry + trap wrappers for the playable BuggyBoy reconstruction.
|
| C ABI (m68k SysV): args at 4(%sp), 8(%sp), ...; each int/pointer 4 bytes; result in %d0.
| Each wrapper cleans only its own trap-frame pushes; the caller cleans the C args.
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

| long Fcreate(const char *name, short attr)   GEMDOS 0x3c  (used by the SMOKE dump path)
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

| long Fwrite(short handle, long count, void *buf)   GEMDOS 0x40  (SMOKE dump path)
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

| long Physbase(void)           XBIOS 2
    .globl  Physbase
Physbase:
    move.w  #2,-(%sp)
    trap    #14
    addq.l  #2,%sp
    rts

| void Vsync(void)              XBIOS 0x25
    .globl  Vsync
Vsync:
    move.w  #0x25,-(%sp)
    trap    #14
    addq.l  #2,%sp
    rts

| void Setpalette(const void *pal16)    XBIOS 6
    .globl  Setpalette
Setpalette:
    move.l  4(%sp),-(%sp)
    move.w  #6,-(%sp)
    trap    #14
    lea     6(%sp),%sp
    rts

| long Kbdvbase(void)           XBIOS 0x22 (KBDVBASE vector table)
    .globl  Kbdvbase
Kbdvbase:
    move.w  #0x22,-(%sp)
    trap    #14
    addq.l  #2,%sp
    rts

| long Super(void *stack)       GEMDOS 0x20 (Super(0) -> enter supervisor mode, stay there)
    .globl  Super
Super:
    move.l  4(%sp),-(%sp)
    move.w  #0x20,-(%sp)
    trap    #1
    addq.l  #6,%sp
    rts

| long Malloc(long amount)      GEMDOS 0x48
    .globl  Malloc
Malloc:
    move.l  4(%sp),-(%sp)
    move.w  #0x48,-(%sp)
    trap    #1
    addq.l  #6,%sp
    rts

| long Crawio(short w)          GEMDOS 0x06 (w=0xff -> non-blocking raw console input poll)
| The C ABI passes `short` in a 4-byte slot; on big-endian m68k the value is the LOW word at 6(sp),
| not 4(sp). Read the longword and push its low word (same idiom as Fcreate/Fopen).
    .globl  Crawio
Crawio:
    move.l  4(%sp),%d0          | w (int); low word is the value
    move.w  %d0,-(%sp)
    move.w  #0x06,-(%sp)
    trap    #1
    addq.l  #4,%sp
    rts

| long Crawcin(void)            GEMDOS 0x07 (blocking raw console input, no echo)
    .globl  Crawcin
Crawcin:
    move.w  #0x07,-(%sp)
    trap    #1
    addq.l  #2,%sp
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
