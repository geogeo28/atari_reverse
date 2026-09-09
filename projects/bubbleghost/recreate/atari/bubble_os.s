| bubble_os.s — the trap wrappers, the two exception entries and the supervisor gate.
|
| NONE OF THIS IS EXERCISED BY THE DIFFERENTIAL. The oracle services traps in-process and runs no
| interrupt at all, so every routine here is uncovered by construction — docs/on-target-execution.md
| class 3, which is written from a wrapper that read the wrong half of a stack slot and made a whole
| input feature silently inert. Two rules follow, and `build.sh` measures the second one:
|
|   * A `short` ARGUMENT IS THE LOW WORD OF A 4-BYTE SLOT. The m68k SysV ABI passes every scalar in
|     a longword slot, so on this big-endian machine `4(%sp)` is the HIGH half and always zero.
|     Every wrapper below reads the whole longword and pushes `%dn` as a word.
|
|   * EVERY ROUTINE THAT TRAPS SAVES %d2 AND %a2. GCC treats %d2-%d7/%a2-%a6 as callee-saved and
|     caches live values there across a call; TOS preserves only %d3-%d7/%a3-%a6. So %d2/%a2 are
|     exactly the pair the compiler expects to survive and TOS may destroy, and the fault surfaces
|     in the CALLER, on hardware, long after the wrapper returned. `tools/assert_trap_registers.sh`
|     is the scan that keeps this true; it runs on every build and asserts the COUNT of wrappers it
|     evaluated, so a rotted pattern reds rather than passing vacuously. Note the argument offsets
|     move with the save: the first argument is at 12(%sp), not 4(%sp).
|
| THE `Mshrink` IS HERE, AND IT IS NOT BOOKKEEPING. GEMDOS hands a .PRG the WHOLE TPA and expects
| the program to give back what it does not need; this one's `.bss` is a 664 KB image, so without the
| shrink it owns every free byte of a 1 MB machine. That is invisible until something else asks TOS
| for memory — and on this program the something else is TOS'S OWN VDI: `v_opnvwk` allocates its
| virtual workstation with GEMDOS `Malloc` (0x134 bytes, from ROM PC $fd0622), gets 0, and answers
| HANDLE 0. Every later VDI call carries that handle and draws nothing at all, so the menu's four
| text lines, the HUD and every sprite blit are silently absent while the AES, the file I/O, the
| sound and the reconstruction's own raw blitters all work perfectly. Measured 2026-09-06: with no
| shrink the workstation handle is 0 and the visible screen stays black; the ORIGINAL, whose Alcyon
| crt0 shrinks to text+data+bss+0x2100, gets handle 2 under the same TOS and the same emulator.
|
| `../src/init.c`'s `crt0_relocate_and_clear` reproduces the shrink's ARITHMETIC and not the call —
| the model answers 0 and touches nothing — so this is the one part of the original's startup that a
| target build owes in assembly rather than in a verified core.
|
| The stack moves FIRST and the shrink follows, because the block being given back is the one the
| stack GEMDOS gave us stands in.

    STACK_RESERVE   = 32768         | what is kept above the program for the C stack. ONE DEFINITION
                                    | ACROSS THE LANGUAGE BOUNDARY (CLAUDE.md §5): build.sh's
                                    | STACK_RESERVE_BYTES is the same number and build.sh asserts
                                    | the two are equal, because the size gate weighs the .PRG
                                    | against a budget this reserve is subtracted from.
    BASEPAGE_BYTES  = 0x100         | GEMDOS puts the basepage immediately below p_tbase
    BP_TLEN         = 12            | the basepage's own segment lengths
    BP_DLEN         = 20
    BP_BLEN         = 28

    .text
    .globl  _start
_start:
    movea.l 4(%sp),%a0              | GEMDOS's basepage
    move.l  %a0,bg_basepage         | ...for the memory budget the record publishes
    move.l  %sp,bg_initial_sp       | ...and the stack it entered on, which is the TPA's ceiling

    move.l  BP_TLEN(%a0),%d0        | keep = basepage + text + data + bss + the stack reserve
    add.l   BP_DLEN(%a0),%d0
    add.l   BP_BLEN(%a0),%d0
    add.l   #BASEPAGE_BYTES+STACK_RESERVE,%d0
    move.l  %a0,%d1
    add.l   %d0,%d1
    andi.l  #-4,%d1                 | the 68000 wants the stack pointer aligned
    move.l  %d1,bg_kept_top         | what the record publishes as the new ceiling
    movea.l %d1,%sp                 | ...and the stack is inside the kept block from here on

    move.l  %d0,-(%sp)              | Mshrink(0, basepage, keep)
    move.l  %a0,-(%sp)
    clr.w   -(%sp)
    move.w  #0x4a,-(%sp)
    trap    #1
    lea     12(%sp),%sp
    move.l  %d0,bg_mshrink_result   | 0 = accepted; a record field, because a refused shrink is the
                                    | shape that leaves the VDI with no memory and no complaint

    jsr     bubble_main             | user mode, and it stays that way: see shim_include/tos.h
    clr.w   -(%sp)                  | Pterm0 (GEMDOS 0x00): terminate with status 0
    trap    #1

| ---- GEMDOS (trap #1) -------------------------------------------------------------------------
| THE FILE-I/O WRAPPERS COME FIRST, right after `_start`, and the order is not cosmetic: it matches
| the proven BuggyBoy, Joust, Wonder Boy and Zynaps layout. With the GEMDOS control wrappers
| (`Super`, `Pterm`) placed before them, Hatari's GEMDOS-HD hands back HANDLE 0 — stdin — from
| `Fopen`, and a program that then reads it waits on the keyboard for ever or discards what it
| writes (the memory of it is `buggyboy-prg-fopen-handle0-bug`). Nothing in this build has ever
| exhibited it and nothing here explains WHY the order matters; what is known is that four builds in
| this workspace hit it and the layout below is the one that does not. Keep the order.
|
| Each label carries the GEMDOS function number the wrapper pushes, so the file can be read against
| `shim_include/tos.h`'s declarations without counting `move.w` immediates.

    .globl  Fcreate
Fcreate:                       | GEMDOS 0x3c
    movem.l %d2/%a2,-(%sp)          | TOS traps may trash d2/a2 — see the register note above
    move.l  12(%sp),%d1             | name
    move.l  16(%sp),%d0             | attr (int); the value is the LOW word of the slot
    move.w  %d0,-(%sp)
    move.l  %d1,-(%sp)
    move.w  #0x3c,-(%sp)
    trap    #1
    lea     8(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Fopen
Fopen:                         | GEMDOS 0x3d
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d1             | name
    move.l  16(%sp),%d0             | mode
    move.w  %d0,-(%sp)
    move.l  %d1,-(%sp)
    move.w  #0x3d,-(%sp)
    trap    #1
    lea     8(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Fclose
Fclose:                        | GEMDOS 0x3e
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #0x3e,-(%sp)
    trap    #1
    addq.l  #4,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Fread
Fread:                         | GEMDOS 0x3f
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

    .globl  Fwrite
Fwrite:                        | GEMDOS 0x40
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

    .globl  Fdelete
Fdelete:                       | GEMDOS 0x41
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)          | name
    move.w  #0x41,-(%sp)
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| Fseek(offset, handle, mode) — the stack the trap reads is opcode.w, offset.l, handle.w, mode.w,
| so the pushes run the other way round.
    .globl  Fseek
Fseek:                         | GEMDOS 0x42
    movem.l %d2/%a2,-(%sp)
    move.l  20(%sp),%d0             | mode
    move.l  16(%sp),%d1             | handle
    move.l  12(%sp),%a1             | offset
    move.w  %d0,-(%sp)
    move.w  %d1,-(%sp)
    move.l  %a1,-(%sp)
    move.w  #0x42,-(%sp)
    trap    #1
    lea     10(%sp),%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Cconout
Cconout:                       | GEMDOS 0x02
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #0x02,-(%sp)
    trap    #1
    addq.l  #4,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Cauxout
Cauxout:                       | GEMDOS 0x04
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #0x04,-(%sp)
    trap    #1
    addq.l  #4,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Cprnout
Cprnout:                       | GEMDOS 0x05
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #0x05,-(%sp)
    trap    #1
    addq.l  #4,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Crawio
Crawio:                        | GEMDOS 0x06
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #0x06,-(%sp)
    trap    #1
    addq.l  #4,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Crawcin
Crawcin:                       | GEMDOS 0x07
    movem.l %d2/%a2,-(%sp)
    move.w  #0x07,-(%sp)
    trap    #1
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Cnecin
Cnecin:                        | GEMDOS 0x08
    movem.l %d2/%a2,-(%sp)
    move.w  #0x08,-(%sp)
    trap    #1
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Cconis
Cconis:                        | GEMDOS 0x0b
    movem.l %d2/%a2,-(%sp)
    move.w  #0x0b,-(%sp)
    trap    #1
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Super
Super:                         | GEMDOS 0x20
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)
    move.w  #0x20,-(%sp)
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| The RETURN half of Super, and it is not the same routine — docs/on-target-execution.md class 9.
| TOS goes back to user mode on the USP as it stood when `Super(0)` ran, and does not reload it from
| the supervisor stack, so a plain `Super(ssp)` is correct only while the compiler happens to have
| left %sp at the same depth at both call sites. Planting the USP one instruction before the trap
| makes the value TOS returns on the one this routine chose.
    .globl  bg_leave_supervisor
bg_leave_supervisor:           | GEMDOS 0x20
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)          | the SSP the entering Super(0) handed back
    move.w  #0x20,-(%sp)
    move.l  %sp,%a0
    move.l  %a0,%usp                | ...so the return lands %a7 exactly here, whatever GCC did
    trap    #1
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| Pterm does not return, so there is nothing to restore and nothing for the register rule to
| protect; the save is kept anyway so that the scan sees one shape in this file rather than two.
    .globl  Pterm
Pterm:                         | GEMDOS 0x4c
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0
    move.w  %d0,-(%sp)
    move.w  #0x4c,-(%sp)
    trap    #1
    addq.l  #4,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| ---- BIOS (trap #13) ---------------------------------------------------------------------------

    .globl  Bconout
Bconout:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0             | dev
    move.l  16(%sp),%d1             | ch
    move.w  %d1,-(%sp)
    move.w  %d0,-(%sp)
    move.w  #0x03,-(%sp)
    trap    #13
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| ---- XBIOS (trap #14) --------------------------------------------------------------------------

    .globl  Physbase
Physbase:
    movem.l %d2/%a2,-(%sp)
    move.w  #2,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Logbase
Logbase:
    movem.l %d2/%a2,-(%sp)
    move.w  #3,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Getrez
Getrez:
    movem.l %d2/%a2,-(%sp)
    move.w  #4,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

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

    .globl  Setpalette
Setpalette:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)          | the sixteen words
    move.w  #6,-(%sp)
    trap    #14
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Setcolor
Setcolor:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0             | index
    move.l  16(%sp),%d1             | value
    move.w  %d1,-(%sp)
    move.w  %d0,-(%sp)
    move.w  #7,-(%sp)
    trap    #14
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Random
Random:
    movem.l %d2/%a2,-(%sp)
    move.w  #0x11,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Vsync
Vsync:
    movem.l %d2/%a2,-(%sp)
    move.w  #0x25,-(%sp)
    trap    #14
    addq.l  #2,%sp
    movem.l (%sp)+,%d2/%a2
    rts

    .globl  Supexec
Supexec:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),-(%sp)          | the routine, which TOS calls in supervisor mode
    move.w  #0x26,-(%sp)
    trap    #14
    addq.l  #6,%sp
    movem.l (%sp)+,%d2/%a2
    rts

| ---- GEM (trap #2): the whole door -------------------------------------------------------------
| EVERY POINTER THE CORES PUT IN A GEM PARAMETER BLOCK IS AN IMAGE OFFSET. That is right in the
| differential's world, where the image IS the machine's memory and starts at 0, and right on the
| original, whose arrays are absolute against the base it runs at. Here the VDI would take `0x236f0`
| for an address and read its `contrl` out of the 68000's vector page. So a `trap #2` on this build
| has to RESTATE the block first, and `bg_gem_dispatch` below is the whole of that:
|
|   * the five (VDI) or six (AES) array pointers are staged into this file's own block for that
|     binding, each translated by the image base — so the VDI still reads its operands out of, and
|     writes its answers into, the game's OWN arrays, with no copy back and no field this door has
|     to know the meaning of. The image's own block is never touched at all.
|   * ...and for the VDI, staged ONCE. Four of its five slots hold the same four constants from the
|     moment the workstation is open, so `bg_gem_cache_vdi_pblock` translates all five after
|     `init_gem_and_screens` returns and every call after that restages `ptsin` alone — the one slot
|     that carries a runtime value. THIS IS THE ONE ASSUMPTION IN THIS FILE THAT IS ABOUT THE CORES
|     RATHER THAN ABOUT THE MACHINE, and it is held from three sides: `atari/build.sh`'s
|     "the VDI parameter block's constant slots" gate reads every writer out of `../src/frontend.c`
|     and refuses one this door does not expect; `bubble_main.c` re-reads the game's four slots at
|     the anchor and files any disagreement in STATE.BIN (`REC_VDI_PBLOCK_CACHE_STATE`, which
|     `smoke.py` requires to be 0); and until the cache is taken the door restates all five, so the
|     boot calls that run BEFORE it — `v_opnvwk`'s own, which lends the VDI three of the caller's
|     arrays — are staged the old way rather than out of a cache that does not exist yet.
|   * a raster copy (`vro_cpyfm`) has two more operands that are reached by DEREFERENCING the image
|     rather than by being handed over: `contrl[7..8]` and `contrl[9..10]` name two MFDBs, and each
|     MFDB names a raster. Those four longwords are patched in place, trapped on, and put straight
|     back, so the image the cores read afterwards holds exactly what it held before.
|
| A ZERO STAYS ZERO, AND THE SENTINEL IS LOAD-BEARING ON BOTH KINDS OF SLOT. For an MFDB's `fd_addr`
| 0 is `MFDB_SCREEN_ADDR`, the VDI's "the screen", and TOS substitutes the logical base `Setscreen`
| was given; translating it would point the copy at the bottom of the image. For a PARAMETER-BLOCK
| slot 0 is not a sentinel but a slot the game has not filled yet — `init_globals` leaves all five
| of `A_vdi_pblock`'s longwords zero and `../src/frontend.c`'s `v_opnvwk` fills `intin`, `intout`
| and `ptsout` but not `ptsin`, so the FIRST VDI call of every run is made with a ptsin of 0, and
| the shipped binary makes it with a ptsin of 0 too. Wave 4 took the test off the block's slots on
| the argument that it could not arise, was GREEN through both smokes because that call declares
| zero ptsin pairs, and reverted it (../STATUS.md, "Performance", wave 4). One `beq` covers both.
|
| THAT IS WHY THIS DOOR HAS ITS OWN TRANSLATION AND DOES NOT USE `shim_include/os.h`'s
| `bg_machine_address`, which is `bg_image_base + offset` with NO zero test: the XBIOS video doors
| translate values the game always fills, and this one translates slots it may not have. The two
| must not be swapped either way round.
|
| WHAT THE MUTATIONS ACTUALLY PROVE ABOUT THE MFDB HALF, because the paragraph above is easy to
| over-read: the PARAMETER-BLOCK half is proven load-bearing by wave 4's ptsin of 0. For an MFDB's
| `fd_addr` the sentinel is the VDI's documented "the screen" and is kept for that reason — but both
| of wave 5a's raster mutations fault on a DEREFERENCED offset, which means both `fd_addr`s are
| NON-ZERO in the frames the smoke captures. Whether this program's own MFDBs ever carry 0 is
| **unpinned by anything in this tree** (../STATUS.md, wave 5a), so the branch stays for the VDI's
| contract and not on evidence that this game reaches it.
|
| WHY IT IS ASSEMBLY. In C the door was `bg_gem_dispatch` + `raster_copy_call` in
| `bubble_backend.c`, 8,493 cycles a frame over 8.63 calls, and its cost was not the work: GCC has
| no way to keep a value in a register across a `jsr` to a routine that traps, so every live value
| went through the frame, and 184 of the raster path's 1,204 cycles went on pushing three arguments
| between the two entry points and the trap wrapper and reading them back. Here the image base, the
| two cursors and the raster path's seven live values are registers for the whole call. The staging
| run is 40 cycles a longword and there is no cheaper spelling of "translate unless zero" on a
| 68000 — `movem.l` in and out of a five-register block counts the same 200 — so a five-slot
| restatement is the floor for as long as five slots have to be restated. WHAT WAVE 7a TOOK IS THE
| OTHER FOUR: with the cache primed a VDI call stages ONE slot, and the whole tail is 82 cycles
| against 212 (`tst.b` on an absolute long 16, the taken `bne` 10, `move.l d16(%a0),%d0` 16, the
| sentinel 8, the add 8, `move.l %d0,xxx.l` 24 — the same M68000UM table 8-5 the 40-cycle staging
| row below is counted off). ../STATUS.md's wave 7a holds that hand count against the profiler.
|
| NOTHING RE-ENTERS IT, AND THE DOOR CANNOT SURVIVE ANYTHING THAT DOES. There is one staged block
| per binding for the whole program, and between the raster path's patch and its restore the game's
| own MFDB holds a MACHINE address where every other reader expects an image offset. The one
| interrupt this build installs is Timer C, whose handler is the sound tick and touches no GEM state
| at all — so no `trap #2` is ever live across an interrupt that could reach either. **A GEM call
| added to any interrupt path breaks both halves at once**: the inner call overwrites all five
| staged slots while the outer trap is still reading them, and a tick landing inside the patch reads
| a machine address out of the game's MFDB. Neither is visible to the differential (the oracle runs
| no interrupt), to `make test`, or to any smoke check. This paragraph is the whole of that guard.
|
| REGISTERS. %d0/%d1/%a0/%a1 are the door's scratch (GCC's caller-saved set). **%d1 IS THE IMAGE BASE
| FOR THE WHOLE CALL** — `TRANSLATE_D0` and `STAGE_POINTERS` both read it and neither says so in its
| operands, so nothing may reuse %d1 before the last staging run. The raster path's
| seven live values are %d3-%d6/%a3-%a5. Those are SAVED because m68k SysV makes them callee-saved
| and the C caller owns them; that TOS ALSO preserves them across the trap is why nothing more than
| the seven has to be saved. The original's own
| trampolines are the spec for that: `vdi_call` @ 0x168d4 and `gem_aes` @ 0x149b6 each save %a1 and
| %a2 around their `trap #2` AND NOTHING ELSE, while keeping their global base in %a4 across it.
| %d2/%a2 are the pair GCC believes is callee-saved and TOS may destroy; they are saved in
| `bg_gem_trap` below, which is the only routine here that traps.

    | THE CONSTANTS ARE THE KIT'S AND THE CORES', NOT THIS FILE'S (CLAUDE.md §5). Every one of them
    | is scraped out of the C header beside it by `build.sh`'s two-language loop and refused on a
    | disagreement, so a slot index that moved in `tools/recreate_kit/include/os.h` reds the build
    | rather than making this door patch the wrong two words of `contrl`.
    GEM_VDI             = 0x73      | tools/recreate_kit/include/os.h — d0 for a VDI call
    GEM_AES             = 0xc8      | ...and for an AES call
    VDI_VRO_CPYFM       = 109       | the one opcode whose operands are reached by dereference
    VDI_CONTRL_OPCODE   = 0         | contrl[] is an array of WORDS; these index it
    VDI_CONTRL_SRC_MFDB = 7         | ...and [8]: the source MFDB address, high word first
    VDI_CONTRL_DST_MFDB = 9         | ...and [10]: the destination MFDB address
    VDI_PB_PTSIN        = 2         | the ONE VDI slot with a runtime value: the cached tail
    VDI_PB_PTSOUT       = 4         | restages this and nothing else
    AES_PB_ADDROUT      = 5         | ...and these two are the LAST slot of each parameter block,
                                    | so each block's length is one more than the kit's own index
    MFDB_ADDR           = 0         | an MFDB's raster pointer, a long
    MFDB_SCREEN_ADDR    = 0         | fd_addr == this means the VDI's own screen
    A_VDI_CONTRL        = 0x236f0   | ../include/frontend.h — the game's own contrl array
    A_VDI_PBLOCK        = 0x1e8ca   | ...and its VDI parameter block, which is what the cache is
                                    | taken FROM and what every VDI caller hands this door

    CONTRL_WORD_BYTES   = 2         | contrl is `word[]` (../include/frontend.h)
    POINTER_BYTES       = 4         | ...and a parameter block is an array of longs
    CONTRL_OPCODE_SLOT   = VDI_CONTRL_OPCODE   * CONTRL_WORD_BYTES
    CONTRL_SRC_MFDB_SLOT = VDI_CONTRL_SRC_MFDB * CONTRL_WORD_BYTES
    CONTRL_DST_MFDB_SLOT = VDI_CONTRL_DST_MFDB * CONTRL_WORD_BYTES
    VDI_POINTER_LONGS = VDI_PB_PTSOUT  + 1
    AES_POINTER_LONGS = AES_PB_ADDROUT + 1
    VDI_PTSIN_SLOT    = VDI_PB_PTSIN   * POINTER_BYTES

    | `bg_gem_dispatch`'s three C arguments, at the entry %sp. Nothing below re-reads them after a
    | `movem` has moved the stack, so these offsets are never adjusted.
    ARG_MEM       = 4
    ARG_SELECTOR  = 8
    ARG_PBLOCK    = 12

    | THE SENTINEL IS A `beq`, so it can only be zero. The assembler refuses the drift rather than
    | this file carrying a comment that claims what the code no longer does.
    .ifne   MFDB_SCREEN_ADDR
    .error  "MFDB_SCREEN_ADDR is no longer 0, and this door tests for it with beq"
    .endif

    | ...AND BOTH LENGTHS ARE PINNED TO THEIR VALUE, not only to each other. `build.sh` pins the two
    | kit indices these are derived FROM, but nothing pins that each is its block's HIGHEST index —
    | a re-spelling of the kit's `VDI_PB_*` block that renumbered `PTSOUT` down would agree with the
    | loop, silently stage four pointers, and leave TOS writing its output counts through a stale
    | one. These two are the deleted `_Static_assert(VDI_POINTER_LONGS == 5u, ...)` pair, restated.
    .ifne   VDI_POINTER_LONGS-5
    .error  "the VDI parameter block is no longer five longwords"
    .endif
    .ifne   AES_POINTER_LONGS-6
    .error  "the AES parameter block is no longer six longwords"
    .endif

    | AN IMAGE OFFSET IN %d0 BECOMES A MACHINE ADDRESS, on the flags the load that produced it set.
    | THE LOCAL LABEL IS `\@`, GAS's per-expansion counter, and not a bare `9:`: this file writes its
    | own numeric labels by hand (`bg_super_gate_entry` uses 1/2/9), and a macro that emits into that
    | same namespace would let a later routine's `9f` bind to a label INSIDE a staging run.
    .macro  TRANSLATE_D0
    beq.s   9\@f                        | 0 is MFDB_SCREEN_ADDR, or a slot the game never filled
    add.l   %d1,%d0
9\@:
    .endm

    | ...and the block's own pointers, `\count` of them, from the game's block at (%a0)+ into the
    | staged one at (%a1)+. 40 cycles a longword: load 12, the sentinel 8, the add 8, the store 12.
    .macro  STAGE_POINTERS  count
    .rept   \count
    move.l  (%a0)+,%d0
    TRANSLATE_D0
    move.l  %d0,(%a1)+
    .endr
    .endm

    | THE STAGE-AND-TRAP TAIL, WHICH IS ONE FACT AND WAS ONCE THREE COPIES OF IT. The staged block,
    | its length and the selector must agree — a mismatched set either over-reads the game's block
    | or leaves the AES's `addr_out` holding the previous call's stale machine address — and the
    | deleted C `stage_and_trap` existed to hold them together. This macro is that helper, at zero
    | cycles, and the three now travel as one argument list.
    |
    | AND THE ASSEMBLER HOLDS THE THREE TOGETHER, which the old two-argument form did not have to:
    | while there was ONE staged block, a `.ifgt VDI_POINTER_LONGS-AES_POINTER_LONGS` made any
    | `\count` safe by construction. With a block per binding a one-token slip —
    | `bg_vdi_staged_pblock, AES_POINTER_LONGS` — stages six pointers into five longwords, inside a
    | `trap #2`, with no differential, no gate and no smoke able to see it. So the block DERIVES its
    | length, its selector and whether it is the cached one, and disagreement is an assembly error.
    |
    | THE CACHED ARM IS THE VDI'S ALONE. Once `bg_gem_cache_vdi_pblock` has translated the four
    | constant slots, a VDI call restates `ptsin` and nothing else (this file's header carries what
    | holds that assumption). The AES keeps the full restatement: its six pointers include
    | `addr_in`/`addr_out`, which are not constant, and it makes 0.00 calls in a profiled frame.
    |
    | Entered with %a0 = the game's block and %d1 = the image base; it ends `%d1` as the STAGED
    | block, which is why the address is materialised twice (`lea` into the cursor, `move.l` into
    | the trap's operand): %d1 has to stay the image base until the last `TRANSLATE_D0`, so there is
    | no register to keep the constant in across the run.
    |
    | %a0 IS NOT THE SAME ON EXIT FROM THE TWO ARMS — the restatement leaves it advanced by
    | `\count` longwords and the cached arm leaves it where it was. No caller reads it afterwards
    | (both VDI arms and the AES arm `rts`, and the raster restore uses only %d3-%d6/%a3-%a5); one
    | that started to would work on the AES path and on the boot's un-cached VDI calls and fail
    | only once the cache is taken.
    .macro  TRAP_STAGED  block, count, selector
    .ifc    "\block","bg_vdi_staged_pblock"
    .ifne   \count-VDI_POINTER_LONGS
    .error  "the VDI's staged block holds VDI_POINTER_LONGS pointers and may be staged no other length"
    .endif
    .ifne   \selector-GEM_VDI
    .error  "the VDI's staged block is trapped on with GEM_VDI"
    .endif
    tst.b   bg_vdi_pblock_cached
    bne.s   1\@f
    .else
    .ifne   \count-AES_POINTER_LONGS
    .error  "the AES's staged block holds AES_POINTER_LONGS pointers and may be staged no other length"
    .endif
    .ifne   \selector-GEM_AES
    .error  "the AES's staged block is trapped on with GEM_AES"
    .endif
    .endif
    lea     \block,%a1
    STAGE_POINTERS \count
    .ifc    "\block","bg_vdi_staged_pblock"
    bra.s   2\@f
1\@:
    move.l  VDI_PTSIN_SLOT(%a0),%d0     | the only slot a caller ever moves after the cache is taken
    TRANSLATE_D0
    move.l  %d0,\block+VDI_PTSIN_SLOT
2\@:
    .endif
    .if     \selector <= 127
    moveq   #\selector,%d0
    .else
    move.l  #\selector,%d0             | 0xc8 is past moveq's sign-extended range
    .endif
    move.l  #\block,%d1
    jsr     bg_gem_trap
    .endm

| int bg_gem_dispatch(uint8_t *mem, uint32_t selector, uint32_t pblock) — shim_include/os.h's
| `os_vdi` and `os_aes` are one call to this. It answers 1 ("modeled") on every path: TOS services
| every opcode this program makes and a `trap #2` has no way to say otherwise, so the cores' refusal
| arms are unreachable here (atari/README.md, "Unpinned", carries that as a residual).
|
| Hand-counted off the 68000's own tables and the objdump, with the VDI cache primed: 276 cycles for
| a non-raster VDI call, 412 for an AES one and 748 for a `vro_cpyfm`, plus `bg_gem_trap`'s own 68
| either way (the trap and the ROM behind it are on top of all three). The two VDI figures were 406
| and 878 while every call restated five slots; ../STATUS.md's wave 5a holds THOSE against what
| Hatari charged, and its wave 7a holds the 130-cycle difference against a second window.
    .globl  bg_gem_dispatch
bg_gem_dispatch:
    move.l  ARG_MEM(%sp),%d1            | the image base — the whole door's translation term
    movea.l %d1,%a0
    adda.l  ARG_PBLOCK(%sp),%a0         | ...and the game's own block, in the cursor the staging
                                        | run reads, so no arm has to move it there
    moveq   #GEM_VDI,%d0
    cmp.l   ARG_SELECTOR(%sp),%d0
    bne.s   bg_gem_aes_call             | THE DOOR HAS EXACTLY TWO CALLERS (os.h's `os_vdi` and
                                        | `os_aes`), so anything that is not the VDI is the AES
    addq.l  #1,bg_vdi_calls
    movea.l %d1,%a1
    adda.l  #A_VDI_CONTRL,%a1           | ...and only a VDI call has a contrl array, so only it pays
    cmpi.w  #VDI_VRO_CPYFM,CONTRL_OPCODE_SLOT(%a1)
    beq     bg_gem_raster_copy
    TRAP_STAGED bg_vdi_staged_pblock, VDI_POINTER_LONGS, GEM_VDI
    moveq   #1,%d0                      | the kit's door answers "modeled" on every path
    rts

| Entered by `bne` with %d1 = the image base and %a0 = the game's block. Nothing else is live.
bg_gem_aes_call:
    addq.l  #1,bg_aes_calls
    TRAP_STAGED bg_aes_staged_pblock, AES_POINTER_LONGS, GEM_AES
    moveq   #1,%d0
    rts

| THE RASTER COPY, patch-trap-restore. Its seven live values are all in the set TOS preserves:
|   %a3 the source MFDB's fd_addr slot      %d3 what that slot held
|   %a4 the destination's, or 0 if the two MFDBs are ONE       %d4 what THAT slot held
|   %a5 contrl      %d5 the source MFDB's own offset      %d6 the destination's
| ONE MFDB CAN BE BOTH OPERANDS, and a second pass over it would translate an ALREADY translated
| raster — the restore would then leave a machine address in the game's own MFDB for good, silently
| and for every later frame. No call site in this program does it (`../src/frontend.c` always passes
| `A_mfdb_src` and `A_mfdb_dst`); the comparison keeps an entry point that takes both as arguments
| from being a landmine. A staged slot is never 0 because the image base never is, so %a4 IS the
| "was the destination staged" flag.
| Entered by `beq` with %d1 = the image base, %a0 = the game's block and %a1 = contrl.
bg_gem_raster_copy:
    addq.l  #1,bg_vdi_raster_copies
    movem.l %d3-%d6/%a3-%a5,-(%sp)      | SAVED BECAUSE THE C CALLER OWNS THEM (m68k SysV makes
                                        | %d2-%d7/%a2-%a6 callee-saved), not because of the trap;
                                        | that TOS preserves this set is why seven is all that is
                                        | needed rather than why any of it is saved
    movea.l %a1,%a5                     | contrl, off the scratch register it was computed in
    movea.l %d1,%a1                     | ...and the image base borrows %a1 for the two leas below,
                                        | leaving %a0 pointing at the game's block for the staging
    move.l  CONTRL_SRC_MFDB_SLOT(%a5),%d5
    move.l  CONTRL_DST_MFDB_SLOT(%a5),%d6
    lea     MFDB_ADDR(%a1,%d5.l),%a3    | the source MFDB's raster
    move.l  (%a3),%d3
    move.l  %d3,%d0
    TRANSLATE_D0
    move.l  %d0,(%a3)
    move.l  %d5,%d0                     | ...and the source MFDB pointer itself. ITS ZERO TEST CANNOT
                                        | FIRE — `../src/frontend.c` always fills contrl[7..10] with
                                        | `A_mfdb_src`/`A_mfdb_dst` — and the two of them cost 96
                                        | cycles a frame for the macro's uniformity. Measured and
                                        | kept: a bare `add.l` here would be the one translation in
                                        | the door written a second way (../STATUS.md, wave 5a)
    TRANSLATE_D0
    move.l  %d0,CONTRL_SRC_MFDB_SLOT(%a5)
    suba.l  %a4,%a4                     | ...and nothing is staged for the destination yet
    cmp.l   %d5,%d6
    beq.s   2f                          | one MFDB is both operands: nothing more to stage
    lea     MFDB_ADDR(%a1,%d6.l),%a4    | the destination MFDB's raster
    move.l  (%a4),%d4
    move.l  %d4,%d0
    TRANSLATE_D0
    move.l  %d0,(%a4)
2:  move.l  %d6,%d0                     | ...and the destination MFDB pointer, aliased or not
    TRANSLATE_D0
    move.l  %d0,CONTRL_DST_MFDB_SLOT(%a5)

    TRAP_STAGED bg_vdi_staged_pblock, VDI_POINTER_LONGS, GEM_VDI

    move.l  %d3,(%a3)                   | ...and the image put back exactly as it was
    move.l  %d5,CONTRL_SRC_MFDB_SLOT(%a5)
    move.l  %a4,%d0
    beq.s   3f
    move.l  %d4,(%a4)
3:  move.l  %d6,CONTRL_DST_MFDB_SLOT(%a5)
    movem.l (%sp)+,%d3-%d6/%a3-%a5
    moveq   #1,%d0
    rts

| The trap itself, and it is ITS OWN ROUTINE for two reasons rather than one. Hatari's profiler
| charges an exception's whole ROM execution to the symbol that issued the `trap` — a trap is not a
| subroutine call, so the profiler never leaves the routine it was in — which is why this label,
| and not `bg_gem_dispatch`, is what `atari/profile.py` holds against the original's own `vdi_call`
| @ 0x168d4 as the ROM VDI's row. Folding it into the door would save the `jsr`/`rts` (34 cycles a
| call, ~290 a frame, 0.06%) and cost the campaign the one row that separates the door's own work
| from the ROM's. And `tools/assert_trap_registers.sh` reads routines label to label: one small
| routine that traps is one routine to keep the %d2/%a2 rule in.
|
| d0 = the selector, d1 = the staged block, exactly as the original's two trampolines set them up.
| NOT A C ENTRY POINT — its arguments are registers, so it has no declaration in shim_include/tos.h
| and NO `.globl` either: a C caller re-added from a later wave would compile with one warning in a
| build that has no `-Werror` and trap with a garbage selector. `m68k-elf-nm` still lists a local
| label as `t`, which is what `atari/profile.py`'s symbol map reads, so the ROM row survives.
bg_gem_trap:
    movem.l %d2/%a2,-(%sp)
    trap    #2
    movem.l (%sp)+,%d2/%a2
    rts

| void bg_gem_cache_vdi_pblock(uint8_t *mem) — shim_include/os.h declares it beside the door.
| CALLED ONCE, from `bubble_main.c`, on the instruction after `init_gem_and_screens` returns: from
| that point the game's `contrl`, `intin`, `intout` and `ptsout` slots hold the four library
| constants for the rest of the run, so their translations are staged here and the door's VDI tail
| restages `ptsin` alone. `ptsin` is staged too — it is one more longword out of the same run and it
| keeps this routine "the block, translated", rather than "the block except one slot".
|
| WHAT MAKES THE MOMENT RIGHT is `v_opnvwk`: it LENDS the VDI three of its caller's own arrays for
| the length of its own trap and puts the library's four back afterwards, so a cache taken any
| earlier would hold `work_in`/`work_out` and hand them to every later call. Taking it before
| `init_gem_and_screens` is what `bubble_main.c`'s anchor check and `smoke.py`'s
| `VDI_PBLOCK_CACHE_STATE` would report, and what the picture would show.
    .globl  bg_gem_cache_vdi_pblock
bg_gem_cache_vdi_pblock:
    move.l  ARG_MEM(%sp),%d1            | the same first argument, at the same offset, as the door's
    movea.l %d1,%a0
    adda.l  #A_VDI_PBLOCK,%a0
    lea     bg_vdi_staged_pblock,%a1
    STAGE_POINTERS VDI_POINTER_LONGS
    move.b  #1,bg_vdi_pblock_cached     | ...and ONLY now, so a fault mid-run leaves the door on its
    rts                                 | full-restatement arm rather than on half a cache

    | The blocks the trap is handed. Each has to outlive the call by the length of the trap, so it is
    | storage and not stack, and there is ONE PER BINDING rather than one shared: the VDI's four
    | constant slots are a cache that lives between calls, and a six-longword AES restatement into
    | the same bytes would overwrite it — silently, and only on the menu's `graf_mouse`, which is
    | the one AES call that happens after the cache is taken. `bubble_main.c` reads the VDI block
    | back at the anchor; nothing would have read it back mid-run.
    | THE `.balign` IS A REQUEST AND NOT A GUARANTEE: `atari/tos.ld` places
    | .bss with `SUBALIGN(2)`, which caps per-symbol alignment at a WORD and overrides this — an
    | even address is all a 68000 `move.l` needs, and even is what SUBALIGN(2) does guarantee.
    .bss
    .balign POINTER_BYTES
    .globl  bg_vdi_staged_pblock        | read back by bubble_main.c's anchor check, and by nothing
bg_vdi_staged_pblock:                   | else: this is the door's own storage
    .space  VDI_POINTER_LONGS*POINTER_BYTES
    .balign POINTER_BYTES
bg_aes_staged_pblock:
    .space  AES_POINTER_LONGS*POINTER_BYTES
    .text

| ---- the trap #9 supervisor gate ---------------------------------------------------------------
| The user-mode half. Three arguments in the registers the handler reads, exactly as the original's
| `psg_access` @ 0x14940 puts its three argument words in d1/d0/d2 before its own `trap #9`.
|
| %d2 IS AN ARGUMENT REGISTER HERE, and it is saved as half of the pair anyway. The handler below is
| OURS and clobbers neither %a2 nor %d2 beyond the argument it was handed — so the save could be
| %d2 alone — but `assert_trap_registers.sh` reads the SOURCE and cannot know whose handler is on the
| vector. One shape for every routine in this file is worth eight bytes: an exception list is how a
| scan stops seeing the wrapper that really did need the pair.
    .globl  bg_super_gate
bg_super_gate:
    movem.l %d2/%a2,-(%sp)
    move.l  12(%sp),%d0             | operation
    move.l  16(%sp),%d1             | register number, or the address for a byte store
    move.l  20(%sp),%d2             | value
    trap    #9
    movem.l (%sp)+,%d2/%a2
    rts

    | The gate's three operations. THE NUMBERS ARE shim_include/tos.h's — `BG_GATE_PSG_WRITE`,
    | `BG_GATE_PSG_READ` and `BG_GATE_STORE8` — and build.sh asserts the two spellings agree, because
    | a caller and a handler that disagree about which operation is 2 would store a register number
    | to an address (CLAUDE.md §5).
    GATE_PSG_WRITE = 0
    GATE_PSG_READ  = 1
    GATE_STORE8    = 2

    IPL7          = 0x0700          | interrupt priority mask, all levels off
    PSG_SELECT    = 0xffff8800      | write = select a register, read = read the selected one
    PSG_DATA      = 2               | ...and $ffff8802 is where a write's data goes
    PSG_REG_MASK  = 15              | the select latch decodes four bits; `and.b #$f,d1` @ 0x1495c
    BUS_HIGH_BYTE = 0xff000000      | 24-bit bus form -> the address a 68020 would also decode

| The supervisor half, on the vector at $a4. IT RAISES TO IPL 7 ACROSS THE PAIR, exactly as the
| original's handler does: the 200 Hz Timer C interrupt drives the same chip, and one landing
| between a register select and its data write would send the data to whichever register the
| handler selected last. The `rte` puts the mask back, so nothing here restores it by hand.
|
| d0/d1/d2 are this call's own arguments and may be clobbered; %a0 is not, and is saved.
    .globl  bg_super_gate_entry
bg_super_gate_entry:
    ori.w   #IPL7,%sr
    move.l  %a0,-(%sp)
    cmpi.l  #GATE_STORE8,%d0
    bne     1f
    ori.l   #BUS_HIGH_BYTE,%d1
    movea.l %d1,%a0
    move.b  %d2,(%a0)
    bra     9f
1:  lea     PSG_SELECT,%a0
    andi.l  #PSG_REG_MASK,%d1
    move.b  %d1,(%a0)
    tst.l   %d0                     | GATE_PSG_WRITE is 0; anything else is the read
    bne     2f
    move.b  %d2,PSG_DATA(%a0)
2:  moveq   #0,%d0
    move.b  (%a0),%d0               | the selected register, read back — the gate's answer
9:  movea.l (%sp)+,%a0
    rte

| The SAME PSG write WITHOUT THE TRAP — the sound ISR's, ~3 a tick — is not here and is no longer in
| C either: it is the five bare `move.b <reg>,(%a1)` / `move.b <data>,2(%a1)` pairs transcribed into
| `../src/asm/sound_tick.S`, which is the original's own shape. (It was a `jsr` here until wave 3a,
| then `psg_untrapped_write` in shim_include/psg.h until wave 7a, which deleted that door with the
| `bg_in_timer_c` flag nothing had set since 5b.) The port and its data displacement above are the
| two `shim_include/psg.h` spells, and build.sh pins THIS file's pair equal to that header while
| `test/test_constants.py` pins the twin's; PSG_REG_MASK stays here alone, because only the TRAPPED
| door masks.

| ---- the Timer C entry is NOT HERE, and that is a measurement ------------------------------------
| `bg_timer_c_entry` — the machine's $114 vector — is in `../src/asm/sound_tick.S`, at the head of
| the hand-written transcription it used to `jsr` to. It lived here for two waves as twelve
| instructions of glue: save four registers, push the image base, call the twin (which saved four
| more and read the base back off the stack), pop the base, mirror $484, restore, push TOS's chain,
| `rts`. That glue cost 356 cycles of every 200 Hz tick; folded into the twin, where the vector's
| own `movem` is the only register save and the base is one absolute load, it costs 260
| (../STATUS.md, "Performance", wave 6a).
|
| WHAT WATCHES IT NOW that it is not in this file: `build.sh`'s conterm-mirror gate reads the store
| back out of the LINKED disassembly instead of out of this source, scoped to the vector's own
| routine — entry to its one `rts` — and asserts in the same scrape that the routine calls nothing
| and contains the transcribed body. `atari/shim_include/tos.h` still declares the entry, because
| `bubble_main.c` is what puts its address on the vector.

| ---- machine primitives, all three supervisor-only and all three Supexec'd ----------------------

    .globl  bg_read_long
bg_read_long:
    movea.l 4(%sp),%a0
    move.l  (%a0),%d0
    rts

    .globl  bg_write_long
bg_write_long:
    movea.l 4(%sp),%a0
    move.l  8(%sp),(%a0)
    rts

    .globl  bg_write_byte
bg_write_byte:
    movea.l 4(%sp),%a0
    move.l  8(%sp),%d0
    move.b  %d0,(%a0)
    rts
