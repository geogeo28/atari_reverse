| os.S — GEMDOS entry, the TOS trap wrappers, the two interrupt entries, and the clock.
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
| real three-bombs-on-hardware bug in this workspace's BuggyBoy build. Copied from spike/os.S and
| audio/audio_os.s, which are canonical for the gotcha.
|
| NOTE: the file-I/O wrappers (Fcreate..Fseek) MUST come first, right after _start — matching the
| proven BuggyBoy, Joust, Wonder Boy, spike and audio layouts. Placing the GEMDOS control wrappers
| (Super/Pterm) before them makes Hatari's GEMDOS-HD hand back handle 0 (stdin) from Fopen, which
| then reads the keyboard (hang) or discards writes. Keep this order.

#include "plat.h"

    GEMDOS_PTERM    = 0x4c
    GEMDOS_CCONWS   = 0x09
    GEMDOS_SUPER    = 0x20
    GEMDOS_FCREATE  = 0x3c
    GEMDOS_FOPEN    = 0x3d
    GEMDOS_FCLOSE   = 0x3e
    GEMDOS_FREAD    = 0x3f
    GEMDOS_FWRITE   = 0x40
    GEMDOS_FSEEK    = 0x42

    BIOS_BCONSTAT   = 0x01
    BIOS_BCONIN     = 0x02
    BIOS_KBSHIFT    = 0x0b

    XBIOS_PHYSBASE  = 0x02
    XBIOS_LOGBASE   = 0x03
    XBIOS_GETREZ    = 0x04
    XBIOS_SETSCREEN = 0x05
    XBIOS_IKBDWS    = 0x19
    XBIOS_KBDVBASE  = 0x22

    | The IKBD's joystick report headers: $fe is port 0 (the mouse port), $ff is port 1.
    IKBD_JOYSTICK_1_REPORT = 0xff

    .text
    .globl  _start
_start:
    | Keep the whole TPA (no Mshrink): GEMDOS leaves %a7 at the top of our memory, well above the
    | BSS image and above BI_LEDGER_ADDR, so both the stack and the fixed ledger have room. main()
    | refuses to run if the BSS image has grown into the ledger, which is the failure this trades
    | an Mshrink for.
    | The program's EXIT STATUS is blackice_main's return value, and that matters: it returns
    | non-zero when BLACKICE.PAK is missing or malformed, or when the .bss image has grown into the
    | ledger's fixed address, and a harness that gates on the status (../CLAUDE.md names exit status
    | as an observable surface) would otherwise record a clean run for a program that drew nothing.
    | Pterm takes the code as a word; Pterm0 discards it.
    jsr     blackice_main
    move.w  %d0,-(%sp)
    move.w  #GEMDOS_PTERM,-(%sp)
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

| long Fopen(const char *name, short mode)          GEMDOS 0x3d
    .globl  Fopen
Fopen:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d1             | name
    move.l  16(%sp),%d0             | mode
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
    move.w  #GEMDOS_FREAD,-(%sp)
    trap    #1
    lea     12(%sp),%sp
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

| long Fseek(long offset, short handle, short mode) GEMDOS 0x42
    .globl  Fseek
Fseek:
    movem.l %d2/%a2,-(%sp)
    move.l  20(%sp),%d2             | mode
    move.l  16(%sp),%d1             | handle
    move.l  12(%sp),%d0             | offset
    move.w  %d2,-(%sp)
    move.w  %d1,-(%sp)
    move.l  %d0,-(%sp)
    move.w  #GEMDOS_FSEEK,-(%sp)
    trap    #1
    lea     10(%sp),%sp
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
| The way BACK is bi_leave_supervisor below and NOT this routine; the paragraph there says why.
    .globl  Super
Super:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)
    move.w  #GEMDOS_SUPER,-(%sp)
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long bi_leave_supervisor(void *ssp)   GEMDOS 0x20 again — the RETURN half, made safe.
|
| TOS goes back to user mode by loading %a7 from the USER stack pointer, and the USP it uses is the
| one FROZEN when `Super(0)` was called — it does not set the USP from the supervisor stack on the
| way out. So a plain `Super(ssp)` returns onto the stack position the FIRST call stood at, and the
| wrapper's own unwind reads from there; that is right only while the compiler leaves %sp at the
| SAME depth at both call sites, which m68k GCC does not promise. This sets the USER stack pointer
| to the supervisor stack it is standing on, one instruction before the trap, which makes the
| return independent of where either call was made. The measurement behind this is in
| projects/wonderboy/recreate/atari/wonderboy_os.s, which is canonical for it.
    .globl  bi_leave_supervisor
bi_leave_supervisor:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)          | the SSP Super(0) handed back
    move.w  #GEMDOS_SUPER,-(%sp)
    move.l  %sp,%a0
    move.l  %a0,%usp                | ...so the return lands %a7 exactly here, whatever GCC did
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| ------------------------------------------------------------------ BIOS (trap #13) -----------

| long Bconstat(short device)   BIOS 0x01 — is a character waiting?
    .globl  Bconstat
Bconstat:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #BIOS_BCONSTAT,-(%sp)
    trap    #13
    addq.l  #4,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Bconin(short device)     BIOS 0x02 — the character; on device 2 the IKBD scancode is in
| bits 16..23 and the ASCII value in bits 0..7.
    .globl  Bconin
Bconin:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #BIOS_BCONIN,-(%sp)
    trap    #13
    addq.l  #4,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Kbshift(short mode)      BIOS 0x0b — mode -1 reads the shift/control/alt bitmap.
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

| long Logbase(void)            XBIOS 0x03
    .globl  Logbase
Logbase:
    movem.l %d2/%a2,-(%sp)
    move.w  #XBIOS_LOGBASE,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| long Getrez(void)             XBIOS 0x04
    .globl  Getrez
Getrez:
    movem.l %d2/%a2,-(%sp)
    move.w  #XBIOS_GETREZ,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| void Setscreen(void *logical, void *physical, short rez)   XBIOS 0x05; -1 leaves a field alone.
    .globl  Setscreen
Setscreen:
    movem.l %d2/%a2,-(%sp)
    move.l  20(%sp),%d0             | rez
    move.l  16(%sp),%d1             | physical
    move.l  12(%sp),%a1             | logical
    move.w  %d0,-(%sp)
    move.l  %d1,-(%sp)
    move.l  %a1,-(%sp)
    move.w  #XBIOS_SETSCREEN,-(%sp)
    trap    #14
    lea     12(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

| void Ikbdws(short count_minus_one, const char *bytes)      XBIOS 0x19
    .globl  Ikbdws
Ikbdws:
    movem.l %d2/%a2,-(%sp)
    move.l  16(%sp),%a1             | bytes
    move.l  12(%sp),%d0             | count - 1
    move.l  %a1,-(%sp)
    move.w  %d0,-(%sp)
    move.w  #XBIOS_IKBDWS,-(%sp)
    trap    #14
    lea     8(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

| void *Kbdvbase(void)          XBIOS 0x22 — the KBDVECS table; joyvec is at +24.
    .globl  Kbdvbase
Kbdvbase:
    movem.l %d2/%a2,-(%sp)
    move.w  #XBIOS_KBDVBASE,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| ---------------------------------------------------------------- the interrupt entries --------
|
| bi_vbl_entry — installed in a free slot of TOS's `_vblqueue`, NOT on the level-4 vector.
|
| TOS's own VBL handler sets the shifter's base address from `_v_bas_ad` every frame and THEN walks
| the queue, `jsr`ing each non-null slot. A handler on the vector itself would therefore run BEFORE
| that write and its page flip would be overwritten by TOS a few microseconds later; from the queue
| the flip is the last word. The queue is also what keeps TOS's keyboard repeat, floppy timeout and
| the Bconin this program reads its keys through alive, which chaining a vector by hand does not.
| audio/audiotest.c installs its music tick the same way and for the same reason.
|
| So this is an `rts` routine and not an `rte` one. It saves exactly %d0-%d1/%a0-%a1 — the registers
| a SysV C function may destroy without saving them itself. Every TOS this could run on saves the
| whole file before walking the queue, so in practice nothing here is needed; 80 cycles against a
| tick of a few thousand is the cheapest possible hedge against one that does not, and the failure
| it hedges against is an interrupted program corrupted at random.
    .globl  bi_vbl_entry
bi_vbl_entry:
    movem.l %d0-%d1/%a0-%a1,-(%sp)
    jsr     bi_vbl_tick             | main.c: flips the page, counts the frame, steps the music
    movem.l (%sp)+,%d0-%d1/%a0-%a1
    rts

| bi_joy_entry — installed on KBDVECS.joyvec. TOS's IKBD handler reassembles the joystick packet
| and `jsr`s here with %a0 pointing at it: byte 0 is the report header ($fe for stick 0, $ff for
| stick 1) and byte 1 the direction/fire bitmap. It is an `rts` routine, not an `rte` one.
|
| ONLY PORT 1 IS RECORDED, and that is a hardware finding rather than a simplification. BRIEF.md and
| DESIGN 6 both name joystick port 1, which is the $ff report. Port 0 is the MOUSE port, and after
| the $14 this build sends the 6301 reports whatever is plugged there as joystick 0: a mouse rolling
| on the desk toggles its quadrature lines, and an earlier version of this file ORed that into the
| player's input word — the player would have walked when the mouse moved. Reading $fe at all would
| put that back the first time someone decided the OR was harmless.
    .globl  bi_joy_entry
bi_joy_entry:
    movem.l %d0/%a0,-(%sp)
    move.b  (%a0),%d0
    cmpi.b  #IKBD_JOYSTICK_1_REPORT,%d0
    bne.s   1f
    move.b  1(%a0),(bi_joy_port1)
1:  movem.l (%sp)+,%d0/%a0
    rts

| ---------------------------------------------------------------- the clock ====================
|
| unsigned long bi_ticks(void)   — SUPERVISOR ONLY (it reads _hz_200 below $800).
|
| TOS's 200 Hz counter gives 5 ms, far too coarse to time a stage that costs 2; the MFP's timer C
| down-counter is the SAME clock's sub-tick part, one unit per TIMER_TICK_NS. Reading both is a
| race, so _hz_200 is read either side of the counter and the pair is retried if it moved: equal
| reads prove no tick landed in the window, which is what makes the counter belong to it.
| Interrupts stay ENABLED — masking them would stop the clock this routine is reading.
|
| The multiply by TIMER_C_RELOAD is two shifts and an add rather than `mulu`, because `mulu` is
| 16x16 and _hz_200 outgrows a word after 5.5 minutes of emulated time.
    .globl  bi_ticks
bi_ticks:
    movem.l %d2-%d3,-(%sp)
5001:
    move.l  (HZ_200_ADDR).w,%d0
    moveq   #0,%d1
    move.b  (TIMER_C_DATA_ADDR).l,%d1
    move.l  (HZ_200_ADDR).w,%d2
    cmp.l   %d0,%d2
    bne.s   5001b
    move.l  %d0,%d3
    lsl.l   #7,%d0                              | * 128
    lsl.l   #6,%d3                              | *  64
    add.l   %d3,%d0                             | * 192 == TIMER_C_RELOAD
    move.l  #TIMER_C_RELOAD,%d2                 | moveq only reaches 127
    sub.l   %d1,%d2                             | the counter counts DOWN
    add.l   %d2,%d0
    movem.l (%sp)+,%d2-%d3
    rts

| unsigned long bi_timer_c_read(void) — the raw down-counter, for the run's own check that
| TIMER_C_RELOAD is what this TOS actually programmed. SUPERVISOR ONLY.
    .globl  bi_timer_c_read
bi_timer_c_read:
    moveq   #0,%d0
    move.b  (TIMER_C_DATA_ADDR).l,%d0
    rts

| ---------------------------------------------------------------- memcpy / memset ==============
|
| include/mem.h declares these two as the only libc the portable core may call, and m68k-elf ships
| no libc: the platform supplies them. They are ASM AND NOT C for a reason spike/REPORT.md paid
| for: GCC 16 folds a copy between two build-time-known addresses into
|       move.l (%a0)+,(d,%a0,%d0.l)          | d == destination - source
| and on the 68000 the source is fetched and %a0 post-incremented BEFORE the destination's
| effective address is computed, so every longword lands four bytes too high and the whole block is
| shifted by one slot. Hand-written, the aliasing does not exist.
|
| Both copy longwords while the ends allow it. Measured against the 68000 tables: the long loop is
| 20 + 12 = 32 cycles for 4 bytes (8 cyc/byte) against the byte loop's 12 + 10 = 22 for 1.

    .globl  memcpy
memcpy:
    move.l  4(%sp),%a1              | dst
    move.l  8(%sp),%a0              | src
    move.l  12(%sp),%d1             | count
    move.l  %a1,%d0                 | memcpy returns its destination; %d0 carries it throughout
    tst.l   %d1
    beq.s   4009f
    | Longwords need BOTH pointers even; a mismatched pair falls through to the byte loop.
    btst    #0,%d0
    bne.s   4003f
    move.l  %a0,%d0
    btst    #0,%d0
    bne.s   4002f
    move.l  %d1,%d0
    lsr.l   #2,%d0
    beq.s   4002f
4001:
    move.l  (%a0)+,(%a1)+           | 20
    subq.l  #1,%d0                  |  8   a LONG counter: `dbra` only counts a word, and even a
    bne.s   4001b                   | 10   screen copy is already 8,000 longwords
    moveq   #3,%d0
    and.l   %d0,%d1                 | the 0..3 byte tail
4002:
    move.l  4(%sp),%d0              | reload: the alignment test above consumed the return value
    tst.l   %d1
    beq.s   4009f
4003:
    move.b  (%a0)+,(%a1)+           | 12
    subq.l  #1,%d1                  |  8
    bne.s   4003b                   | 10
    move.l  4(%sp),%d0
4009:
    rts

    .globl  memset
memset:
    movem.l %d2-%d3,-(%sp)
    move.l  (8 + 4)(%sp),%a1        | dst
    move.l  (8 + 8)(%sp),%d1        | value; only the low byte is used
    move.l  (8 + 12)(%sp),%d2       | count
    | The two saved longwords sit between %sp and the return address, so every C argument is at
    | 8 + its SysV offset; spelling it that way keeps the two halves visibly related.
    tst.l   %d2
    beq.s   4109f
    and.l   #0xff,%d1
    move.l  %d1,%d3
    lsl.l   #8,%d3
    or.l    %d3,%d1
    move.l  %d1,%d3
    swap    %d3
    or.l    %d3,%d1                 | the byte, four times over, for the longword loop
    move.l  %a1,%d0
    btst    #0,%d0
    bne.s   4103f                   | an odd destination: byte fill the lot
    move.l  %d2,%d0
    lsr.l   #2,%d0
    beq.s   4103f
4101:
    move.l  %d1,(%a1)+              | 12
    subq.l  #1,%d0                  |  8
    bne.s   4101b                   | 10
    moveq   #3,%d0
    and.l   %d0,%d2                 | the 0..3 byte tail
    beq.s   4109f
4103:
    move.b  %d1,(%a1)+
    subq.l  #1,%d2
    bne.s   4103b
4109:
    movem.l (%sp)+,%d2-%d3
    move.l  4(%sp),%d0              | memset returns its destination
    rts

| ---------------------------------------------------------------- the floppy ------------------
|
| void bi_floppy_deselect(void)   — SUPERVISOR ONLY.
|
| BRIEF.md's gotcha, paid for on real hardware in projects/wonderboy: leave a drive SELECTED after
| loading and the machine's idle fuse can fire mid-sector on the next access. The resource load here
| goes through GEMDOS, so TOS owns the drive during it — but TOS deselects on its own schedule, and
| a game that has taken the vertical blank away from the desktop should not be relying on a timer it
| no longer feeds. One read-modify-write at the end of the load costs nothing and removes the class.
|
| THE SELECT LINES ARE ACTIVE LOW and live in PSG port A (register 14), which is why this is a
| read-modify-write and not a store: bits 0 and 3..7 are the side select, the RS232 handshake, the
| Centronics strobe and the STE's own line, and none of them are ours to change.
| projects/wonderboy/names.txt (`psg_set_drive_select`, `floppy_deselect_drives`) is canonical for
| the bit assignment; its `%101` is "side 1, drive A selected, drive B deselected".
|
| A PSG ACCESS IS A SELECT STORE FOLLOWED BY A DATA STORE, and any handler that touches the chip in
| between writes our data into its register — TOS's own floppy and keyboard code drives port A
| through these very addresses. So the pair runs at IPL 7, exactly as audio/ym_psg.S does for the
| same reason.

    PSG_SELECT_ADDR     = 0xffff8800
    PSG_DATA_ADDR       = 0xffff8802
    PSG_REG_PORT_A      = 14
    PSG_DRIVE_A_BIT     = 1         | active low: a 1 DESELECTS
    PSG_DRIVE_B_BIT     = 2
    PSG_DRIVE_DESELECT  = (1 << PSG_DRIVE_A_BIT) | (1 << PSG_DRIVE_B_BIT)
    CPU_IPL_MASK_ALL    = 0x0700

    .globl  bi_floppy_deselect
bi_floppy_deselect:
    move.w  %sr,-(%sp)
    ori.w   #CPU_IPL_MASK_ALL,%sr
    move.b  #PSG_REG_PORT_A,(PSG_SELECT_ADDR).l
    move.b  (PSG_SELECT_ADDR).l,%d0
    ori.b   #PSG_DRIVE_DESELECT,%d0
    move.b  #PSG_REG_PORT_A,(PSG_SELECT_ADDR).l
    move.b  %d0,(PSG_DATA_ADDR).l
    move.w  (%sp)+,%sr
    rts

| ---------------------------------------------------------------- the VBL, the other way -------
|
| bi_vbl_vector_entry — the FALLBACK install, on the level-4 autovector, chaining to whatever was
| there. bi_vbl_entry above is the preferred one and os.S's note there says why; this exists because
| TOS's queue has only `nvbls` slots and a machine with accessories loaded can have none free, and
| without a vertical blank of some kind this program has no frame clock, no page flip and no music.
|
| CHAINING IS SAFE HERE ONLY BECAUSE set_video_base WRITES `_v_bas_ad` AS WELL as the hardware. A
| handler on this vector runs BEFORE TOS's, which then reloads the shifter from `_v_bas_ad` — so a
| flip that wrote only the registers would be undone a few microseconds later, every frame. Writing
| both makes TOS's reload agree with us and the ordering stop mattering.
|
| `move.l chain,-(%sp) / rts` jumps to the old handler, whose own `rte` returns from the interrupt.
    .globl  bi_vbl_vector_entry
bi_vbl_vector_entry:
    movem.l %d0-%d1/%a0-%a1,-(%sp)
    jsr     bi_vbl_tick
    movem.l (%sp)+,%d0-%d1/%a0-%a1
    move.l  (bi_vbl_chain),-(%sp)
    rts
