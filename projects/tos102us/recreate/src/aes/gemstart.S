/* gemstart.S — GEMSTART as the ROM spells it (`aes/gemstart.h`): gem_entry and gem_gemdos_call, `$fd9eca..$fd9ffb`,
 * BYTE FOR BYTE — and THE LINE-F HANDLER with the 38 bytes gem_entry copies behind it, `$fee8c2..$fee925`, as DATA.
 *
 * A KIND OF ITS OWN (`atari/target.mk`: GEMSTART_SOURCES), the switch's and the trap door's sibling: the ROM's bytes,
 * no C twin a build could link instead, no row of `include/transcribed.h` and no bar it was measured over. C FIRST
 * still holds for everything behind it that can be C: rom_rsc_init, size_theglo and gem_main are C (`resource.c`,
 * `deskmem.c`, `geminit.c`), `jsr`ed from gem_entry below.
 *
 * WHY THIS IS ASSEMBLY: IT SETS UP THE FIRST STACK. gem_entry is the program's entry — nothing calls it and it never
 * returns —; its second instruction takes a stack of its own, its second trap makes that stack the supervisor's, and
 * its loop moves the stack pointer to the top of UDA0 before the `jsr` that puts gem_main there: no C function is
 * entered without a stack, or may load one. It also clears THEGLO by the ROM's own loop form — `move.w d1,(a0)+ /
 * dbmi d0`, D0 the count size_theglo answers — which is the instruction, not a `memset`. gem_gemdos_call pops its own
 * return address into a word of RAM so that the frame GEMDOS reads is its caller's, and pushes it back for its `rts`.
 *
 * TWO PINS (`test/test_aes_gemstart.py`).
 *   - `$fd9eca..$fd9ffb` is BYTE-EXACT but for SEVEN longwords, each an operand that names where this build links what
 *     the ROM's names in the ROM: the Line-F handler it copies (the data region below), its three `jsr`s (the C
 *     rom_rsc_init through the thunk at the end of this file; the C size_theglo and gem_main, entered as they are),
 *     and the three routines it stores BY VALUE — `aes_rom_justretf` and `aes_rom_tick_glue` (`irq.S`) and
 *     `aes_rom_ub_trampoline` (`trapdoor.S`).
 *   - `$fee8c2..$fee925` is BYTE-EXACT BUT FOR ONE LONGWORD, THE EIGHTH RELOCATION (band 6 slice B, THE BINDING; ruling
 *     W6-R1): the handler's `movea.l #<table>,a0` loads OUR call table (`aes_linef_table`, `lineftable.S`) where the
 *     ROM's loads `$fee900`; gem_entry's copy carries it to the RAM copy's operand (`$cc24`). The nine and a half
 *     longwords behind the handler stay THE ROM'S ADDRESSES, the dead data they are (the handler indexes the table
 *     where it is linked; no byte of the table is copied). NOTHING OF THIS BUILD MAKES A LINE-F CALL: what runs the
 *     copy is the desk — the ROM's text until each routine flips — whose every call then goes through OUR table: into
 *     our AES, and into the ROM's own desk where the table still names it.
 *
 * WHAT A `jsr` INTO C CHANGES, AND WHY IT IS RIGHT. The ROM's three callees are Alcyon's (D3-D7/A3-A6 kept); GCC's
 * keep D2-D7/A2-A6 — more, never less — and gem_entry reads nothing but D0 after size_theglo (the count: its low
 * word, which is all `dbmi` reads) and nothing at all after the other two. A5, the basepage, is read once more
 * after the Mshrink trap alone ($fd9f04), before any call.
 *
 * WHO ENTERS IT (band 5 wave 4): the our-boot machine alone, a labelled staging (slice B: `test/aes_boot.py`) — on
 * iron the BIOS still starts the ROM's gem_entry. What a build's gem_entry stores by value (`$947a`, `$947e`, `$8c32`)
 * the relocation registry maps where a run ends, and a takeover's door maps on a machine the ROM booted (slice F).
 *
 * REGISTERS AND STACKS. Entered in USER state with the basepage above the stack pointer; from the second trap on,
 * supervisor state, on `[$890e, $8994)` until the loop's `movea.l a6,sp`, then on UDA0.
 */
#include "addrs.h"
#include "c_call_glue.h"
#include "m68k_encodings.h"
#include "aes/aes.h"
#include "aes/evlib.h"
#include "aes/gemstart.h"
#include "aes/gsxif.h"
#include "aes/loader.h"

/* `add.l #<imm>,D0` and `adda.l #<imm>,An` in the forms the ROM's assembler chose (gas picks ADDI, and a word
 * immediate for an address register): the program's size plus its basepage; the Mshrink frame dropped; UDA0's top. */
#define ADD_L_IMMEDIATE_D0    0xd0bc
#define ADDA_L_IMMEDIATE(an)  (0xd1fc + ((an) << M68K_DATA_REGISTER_SHIFT))
/* The `movem.l (sp)+,<mask>` whose mask word the handler writes into ITSELF on every masked return (LINEF_MASK_OFFSET):
 * the opcode, and the empty mask the ROM holds. */
#define MOVEM_L_FROM_STACK    0x4cdf
#define LINEF_EMPTY_MASK      0
/* Bit 0 of a Line-F word: a return, not a call (LINEF_RETURN_BIT, as `btst` numbers it). */
#define LINEF_RETURN_BIT_NUMBER 0
/* The half longword the copy ends on: the high word of the call table's tenth entry. */
#define HIGH_WORD_OF(address) ((address) >> 16)

    .text

/* ==== $fd9eca..$fd9ffb: gem_entry and gem_gemdos_call ================================================================ */

/* ---- gem_entry, $fd9eca: the AES as a program ---------------------------------------------------------------------- */
    .globl  aes_rom_gem_entry
    .type   aes_rom_gem_entry,@function
aes_rom_gem_entry:
    movea.l %sp,%a5
    .word   M68K_MOVEA_L_IMMEDIATE(M68K_A7)         /* movea.l #GEM_FIRST_STACK,sp: THE FIRST STACK */
    .long   GEM_FIRST_STACK
    movea.l GEM_BASEPAGE_ARGUMENT(%a5),%a5          /* the basepage */
    move.l  BASEPAGE_TLEN(%a5),%d0
    add.l   BASEPAGE_DLEN(%a5),%d0
    add.l   BASEPAGE_BLEN(%a5),%d0
    .word   ADD_L_IMMEDIATE_D0                      /* add.l #GEM_BASEPAGE_BYTES,d0 */
    .long   GEM_BASEPAGE_BYTES
    move.l  %d0,-(%sp)                              /* Mshrink(0, basepage, the program's own bytes) */
    move.l  %a5,-(%sp)
    move.w  %d0,-(%sp)                              /* the reserved word: whatever D0's low word is */
    move.w  #GEMDOS_MSHRINK_FN,-(%sp)
    trap    #1
    .word   ADDA_L_IMMEDIATE(M68K_A7)               /* adda.l #GEM_MSHRINK_FRAME_BYTES,sp */
    .long   GEM_MSHRINK_FRAME_BYTES
    move.l  %sp,-(%sp)                              /* Super(sp): supervisor state from here on, on this stack */
    move.w  #GEMDOS_SUPER_FN,-(%sp)
    trap    #1
    addq.w  #GEM_SUPER_FRAME_BYTES,%sp
    move.l  BASEPAGE_ENV(%a5),(AES_SH_ENVIRONMENT).l
    move.w  #GEM_NO_RESCHANGE,(AES_GL_RSCHANGE).l
    move.w  #GEM_FIRST_DEVICE,(AES_GL_RESTYPE).l
    move.w  #GEM_START_WORD_890C_SET,(GEM_START_WORD_890C).l
    move.l  #0,(GEM_START_LONG_8904).l
    move.b  (VECTOR_LINE_F).l,%d0                   /* the vector's HIGH BYTE: non-zero while it is the BIOS's */
    beq.s   1f                                      /* a RAM address already — the copy stands: the second pass */
    move.l  #LINEF_COPY_BYTES,-(%sp)                /* Malloc(100) */
    move.w  #GEMDOS_MALLOC_FN,-(%sp)
    trap    #1
    addq.l  #GEM_MALLOC_FRAME_BYTES,%sp
    movea.l %d0,%a0
    move.w  #(LINEF_COPY_WORDS - 1),%d1
    .word   M68K_MOVEA_L_IMMEDIATE(M68K_A1)         /* movea.l #<the handler>,a1: this file's own data, below */
    .long   aes_rom_linef_handler
2:  move.w  (%a1)+,(%a0)+
    dbf     %d1,2b
    move.l  %d0,(VECTOR_LINE_F).l
1:  nop
    M68K_JSR_LONG(gemstart_to_aes_rom_rsc_init)     /* $fd9f5e: the ROM's resources into a Malloc block (C) */
    move.w  #GEM_DISK_USABLE,(AES_DISK_USABLE).l
    clr.w   (AES_CTL_MESSAGE_SENT).l
.Lgem_loop:                                         /* $fd9f72: every pass of GEM begins here */
    M68K_JSR_LONG(aes_size_theglo)                  /* $fd9f72: D0.w the clear's count (C) */
    .word   M68K_MOVEA_L_IMMEDIATE(M68K_A0)         /* movea.l #AES_THEGLO,a0 */
    .long   AES_THEGLO
    clr.l   %d1
3:  move.w  %d1,(%a0)+                              /* THEGLO cleared: D0 + 1 words, by `dbmi` */
    dbmi    %d0,3b
    lea     (aes_rom_justretf).l,%a0                /* $fd9f86: the routine that draws nothing */
    move.l  %a0,(AES_DRWADDR).l
    lea     (aes_rom_tick_glue).l,%a0               /* $fd9f92: the tick glue, for gem_main's vex_timv */
    move.l  %a0,(AES_TICK_ROUTINE).l
    lea     (aes_rom_ub_trampoline).l,%a0           /* $fd9f9e: the desk's G_USERDEF door */
    move.l  %a0,(AES_USERDEF_TRAMPOLINE).l
    .word   M68K_MOVEA_L_IMMEDIATE(M68K_A6)         /* movea.l #AES_THEGLO,a6: UDA0 */
    .long   AES_THEGLO
    movea.l %a6,%a5
    .word   ADDA_L_IMMEDIATE(M68K_A6)               /* adda.l #AES_UDA0_BYTES,a6: its stack's top */
    .long   AES_UDA0_BYTES
    move.l  %a6,UDA_SUPER_SP(%a5)
    movea.l %a6,%sp                                 /* THE PROCESS'S STACK, from here on */
    M68K_JSR_LONG(aes_rom_gem_main)                 /* $fd9fbe: GEM up, the shell, GEM down (C) */
    bra.s   .Lgem_loop
    .size   aes_rom_gem_entry,.-aes_rom_gem_entry

/* ---- gem_gemdos_call, $fd9fc6: a `trap #1` over the caller's own frame; the verdict in the glue's two words -------- */
    .globl  aes_rom_gem_gemdos_call
    .type   aes_rom_gem_gemdos_call,@function
aes_rom_gem_gemdos_call:
    move.l  (%sp)+,(AES_GEMDOS_RETURN).l            /* the return address out of GEMDOS's way */
    move.w  #GEM_DOS_NO_ERROR,(AES_DOS_ERR).l
    move.w  #GEM_DOS_NO_ERROR,(AES_DOS_AX).l
    trap    #1
    move.w  %d0,(AES_DOS_AX).l
    .word   M68K_CMP_L_IMMEDIATE(M68K_D0)           /* cmp.l #0,d0 */
    .long   0
    bge.s   1f
    move.w  #GEM_DOS_FAILED,(AES_DOS_ERR).l         /* a negative LONGWORD alone is an error */
1:  move.l  (AES_GEMDOS_RETURN).l,-(%sp)
    rts
    .size   aes_rom_gem_gemdos_call,.-aes_rom_gem_gemdos_call

/* ==== THE THUNK gem_entry's `jsr` of rom_rsc_init reaches: the image base pushed for a C body that is handed nothing
 * else (`c_call_glue.h`). Local, sized: no ROM bytes, and no entry of the build's. (size_theglo takes nothing and
 * gem_main's target entry takes its image base through a register — `geminit.c` — so neither has one.) */
IMAGE_ONLY_THUNK(gemstart_to_aes_rom_rsc_init, aes_rom_rsc_init)

/* ==== $fee8c2..$fee925: WHAT gem_entry COPIES — the Line-F handler and the call table's first 38 bytes, AS DATA ====== */
/* The handler is written as the instructions it is so that the pin's every word reads as what the ROM's is; no
 * instruction of a build jumps here, and the copy is run by the ROM's desk's own Line-F words alone (this file's head). */
    .balign 2
    .globl  aes_rom_linef_handler
    .type   aes_rom_linef_handler,@object
aes_rom_linef_handler:
    move.w  (%sp)+,%d2                              /* the exception frame: the status register... */
    movea.l (%sp)+,%a0                              /* ...and the PC, at the Line-F word */
    move.w  (%a0)+,%d1
    btst    #LINEF_RETURN_BIT_NUMBER,%d1
    bne.s   1f
    move.w  %d2,%sr                                 /* A CALL: back to the caller's state, */
    move.l  %a0,-(%sp)                              /* the word after the call its return address, */
    andi.w  #LINEF_OFFSET_MASK,%d1
    .word   M68K_MOVEA_L_IMMEDIATE(M68K_A0)         /* movea.l #<our table>,a0: THE BINDING (the ROM's: $fee900), */
    .long   aes_linef_table
    movea.l 0(%a0,%d1.w),%a0
    jmp     (%a0)                                   /* and into the routine the entry names */
1:  andi.w  #LINEF_REGISTER_BITS,%d1                /* A RETURN: its register bits */
    beq.s   2f
    lsl.w   #LINEF_MASK_SHIFT,%d1
    ori.w   #SR_IPL_MASK,%sr
    lea     .Llinef_mask(%pc),%a0
    move.w  %d1,(%a0)                               /* ...written into the `movem` below: the copy patches itself */
    addq.l  #LINEF_SCRATCH_BYTES,%sp
    .word   MOVEM_L_FROM_STACK
.Llinef_mask:
    .word   LINEF_EMPTY_MASK
2:  move.w  %d2,%sr
    unlk    %a6
    rts
/* ...and the first nine and a half longwords of the ROM's call table, which the 100-byte copy takes with it and
 * nothing reads (the handler indexes OUR table, where the blob links it): ROM routines' addresses, as the data they are. */
    .long   AES_ROM_GSX_1CODE, AES_ROM_BB_FILL, AES_ROM_GSX_TCALC, AES_ROM_GR_JUST, AES_ROM_GSX_TBLT
    .long   AES_ROM_GSX_ATTR, AES_ROM_GSX_BLT, AES_ROM_GSX_MOFF, AES_ROM_GR_INSIDE
    .word   HIGH_WORD_OF(AES_ROM_GSX_BOX)
    .size   aes_rom_linef_handler,.-aes_rom_linef_handler
#if LINEF_COPY_BYTES != 2 * LINEF_COPY_WORDS
#error "gem_entry copies the handler a word at a time: the Malloc's bytes are the copy's words"
#endif
