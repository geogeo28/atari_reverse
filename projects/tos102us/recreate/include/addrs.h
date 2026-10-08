/* addrs.h — every ROM and system address this recreate names, in one place.
 *
 * THE SINGLE SOURCE OF TRUTH ACROSS THE LANGUAGE BOUNDARY. The C cores include this; the Python
 * side (`test/`, `tools/boot_snapshot.py`) reads the same `#define`s out of this file through
 * `tools/addrs.py`, which parses it. Neither side keeps a second copy, so an address cannot be
 * right in the reconstruction and wrong in the case that proves it.
 *
 * Addresses here are the machine's own — a ROM address is where the ROM is mapped ($FC0000), and a
 * system-variable address is where TOS itself puts it. They are therefore also Ghidra addresses for
 * this project, whose image is loaded at its real base with no relocation (see ../README.md).
 */
#ifndef TOS102US_ADDRS_H
#define TOS102US_ADDRS_H

/* GUARDED, because `src/bios/trap.S` includes this header too: the trap dispatcher is an
 * exception handler and cannot be C on the target, so the one file that names every address
 * has to be readable by the assembler as well. os.h is C; everything defined in THIS file is a
 * plain integer `#define`, which both languages read, and gcc defines __ASSEMBLER__ when it
 * preprocesses a `.S`.
 *
 * SO NOTHING BELOW THE GUARD MAY EXPAND TO AN os.h NAME. A `#define` whose value is `OS_…` reads
 * as an undefined symbol once the include is skipped — the assembler does not fail on the header,
 * it fails at the line that USES the constant, and only if some `.S` ever does. The kit's own
 * addresses are therefore spelt here as integers and PINNED equal to os.h by a test, which is the
 * pattern `MFP_GPIP` already uses (`test_bios_vbl.py`) and `PSG_PORT_SELECT` now uses
 * (`test_bios_trap.py`); `test_bios_trap.py::test_the_header_the_transcription_includes_holds_no_os_names`
 * preprocesses this file as assembly and refuses a residual one. */
#ifndef __ASSEMBLER__
#include "os.h"
#endif

/* ---- the machine ------------------------------------------------------------------------------ */
#define ROM_BASE            0xfc0000   /* TOS 1.02 US is mapped here and linked for it */
#define ROM_BYTES           0x30000    /* 192 KB */
#define ST_RAM_BYTES        0x100000   /* the 1 MB machine the snapshot was taken on */

/* ---- the 68000 vector slots the OS owns ------------------------------------------------------- */
#define VECTOR_TRAP_GEMDOS  0x84       /* trap #1  -> $fc4f6e */
#define VECTOR_TRAP_GEM     0x88       /* trap #2  -> $fe3ea6 (AES/VDI) */
#define VECTOR_TRAP_BIOS    0xb4       /* trap #13 -> $fc07f8 */
#define VECTOR_TRAP_XBIOS   0xb8       /* trap #14 -> $fc07f2 */
#define VECTOR_VBL          0x70       /* the vertical-blank handler the snapshot is captured in */
#define VECTOR_BYTES        4          /* ...and one slot, which is Setexc's whole index arithmetic */

/* ---- system variables the reconstructed functions read or write -------------------------------- */
#define SYSVAR_PHYSTOP      0x42e      /* long: top of ST RAM */
#define SYSVAR_MEMBOT       0x432      /* long: bottom of the TPA */
#define SYSVAR_MEMTOP       0x436      /* long: top of the TPA */
#define SYSVAR_V_BAS_AD     0x44e      /* long: the logical screen base Setscreen stores */
#define SYSVAR_HZ_200       0x4ba      /* long: the 200 Hz system tick — XBIOS Random's entropy */
#define SYSVAR_SYSBASE      0x4f2      /* long: the OS header, i.e. ROM_BASE */

/* ---- the trap dispatch tables ------------------------------------------------------------------
 * Both are `word count` followed by `count` longword entries; the dispatcher at $fc07fc bounds the
 * function number against the count, and an entry with bit 31 set is INDIRECT — the longword at the
 * masked address is the routine (that is how Rwabs/Getbpb/Mediach reach a hard-disk driver). */
#define BIOS_FUNCTION_TABLE   0xfc0846  /* 12 entries */
#define XBIOS_FUNCTION_TABLE  0xfc0878  /* 65 entries */
#define TRAP_TABLE_COUNT_BYTES 2        /* the leading word */
#define TRAP_TABLE_ENTRY_BYTES 4
#define TRAP_TABLE_INDIRECT   0x80000000u

/* ---- the reconstructed ROM functions ------------------------------------------------------------
 * Both are reached through the XBIOS dispatcher at $fc07fc, which pops the function number and
 * `suba.l a5,a5` — so every ROM function runs with A5 = 0 and reaches both low RAM and the I/O page
 * through 16-bit displacements off it. A case must enter them the same way. */
#define XBIOS_RANDOM_FN     0x11        /* XBIOS function number */
#define XBIOS_RANDOM        0xfc1510
#define XBIOS_GIACCESS_FN   0x1c
#define XBIOS_GIACCESS      0xfc2ea4

/* ---- XBIOS Random ------------------------------------------------------------------------------ */
#define RANDOM_SEED         0x2a4a      /* long, in the OS's own BSS: the LCG's state */
#define RANDOM_MULTIPLIER   0xbb40e62du /* seed = seed * this + 1 */
#define RANDOM_SHIFT        8           /* ...and the result is the state shifted down this far... */
#define RANDOM_MASK         0xffffffu   /* ...and masked to 24 bits */

/* ---- XBIOS Giaccess ---------------------------------------------------------------------------- */
#define GIACCESS_REGISTER_MASK 0x0f     /* the YM2149's select latch decodes four bits */
#define GIACCESS_WRITE_FLAG    0x80     /* ...and bit 7 of the register argument means "write" */
/* The chip's select port, in the 24-bit bus form the ROM's own `lea $ffff8800,a0` aliases onto. This
 * project's name for os.h's `OS_PSG_PORT_SELECT` and NOT a second spelling of $ff8800: a core that
 * reached the chip directly would have to hit the address the oracle DECODES, or the PSG model
 * would quietly stop being in the picture. (Today no core does — they call psg.h, which is what
 * makes the accesses comparable — and the Python case that plants a decoy at the port reads the
 * same constant through `harness.OS_PSG_PORT_SELECT`, pinned to os.h by
 * recreate_kit/test/test_os_memory_map.py.)
 *
 * Spelt as the integer rather than as the os.h name for the guard's reason above — an `OS_…`
 * expansion is not readable by the assembler, and `tools/addrs.py` takes integers only, so the
 * Python side could not see it either. Held equal to os.h by
 * `test_bios_trap.py::test_the_psg_port_this_project_names_is_the_kit_s_own`. */
#define PSG_PORT_SELECT     0xff8800   /* = OS_PSG_PORT_SELECT */

/* ================================================================================================
 * THE BIOS/XBIOS LEAVES THAT READ AND WRITE RAM ONLY (wave 2)
 *
 * Everything below belongs to the group of trap routines whose whole body is system variables, an
 * IOREC ring or the caller's own buffer — no MFP, no ACIA, no shifter — which is what makes them
 * runnable under ROM mode's I/O-read refusal (../README.md, "The image in ROM mode").
 * ============================================================================================= */

/* ---- system variables these routines report or keep -------------------------------------------- */
#define SYSVAR_TIMR_MS      0x442      /* word: the system-timer calibration Tickcal reports, in ms */
#define SYSVAR_DRVBITS      0x4c2      /* long: one bit per mounted drive — Drvmap's whole body */

/* The four BIOS character-device vector TABLES, eight longwords each, built at boot from the ROM
 * image at $fc09ae. Bconstat/Bconin/Bcostat/Bconout are each a walk of one of them, so these are
 * RAM that steers control flow rather than data. */
#define XCONSTAT_TABLE      0x51e
#define XCONIN_TABLE        0x53e
#define XCOSTAT_TABLE       0x55e
#define XCON_TABLE_DEVICES  8          /* ...and how many longwords one of them holds */
#define XCON_TABLE_ENTRY_BYTES 4       /* ...each one a driver address, which is also the index step */
/* Bconout's table at $57e is deliberately absent: every one of its eight drivers writes a chip, so
 * nothing in this wave reaches it and a constant no code reads is a claim nothing checks. */

/* The ROM's own root MEMORY DESCRIPTOR, which Getmpb hands the caller a memory parameter block for.
 * Four longwords: link, start, length, owner (the GEMDOS MD layout). */
#define OS_MEMORY_DESCRIPTOR 0x48e

/* The GEMDOS MEMORY PARAMETER BLOCK Getmpb fills, and the memory DESCRIPTOR on its lists — field
 * offsets, in the order the ROM stores them. Both structures are the caller's view of GEMDOS's
 * allocator, so the names are GEMDOS's own (`mp_mfl`, `m_link`, ...). */
#define MPB_FREE_LIST        0         /* mp_mfl:   the free list's head */
#define MPB_ALLOCATED_LIST   4         /* mp_mal:   the allocated list's, empty at this point */
#define MPB_ROVER            8         /* mp_rover: where the next search starts */
#define MD_LINK              0         /* m_link:   the next descriptor, or 0 */
#define MD_START             4         /* m_start:  the block's base */
#define MD_LENGTH            8         /* m_length: its size in bytes */
#define MD_OWNER             12        /* m_own:    the basepage that owns it, or 0 */

#define KBSHIFT             0xe61      /* byte: the keyboard shift state — the OS header's pkbshift */
#define KEYTBL_STRUCT       0xe62      /* 3 longwords: the unshifted/shifted/CapsLock scancode tables */
#define KEYTBL_FIELD_UNSHIFTED 0       /* ...and which longword is which. Keytbl takes its three */
#define KEYTBL_FIELD_SHIFTED   4       /* arguments in this order and Bioskeys restores them in it, */
#define KEYTBL_FIELD_CAPSLOCK  8       /* so a swapped pair is a real defect rather than a typo */
#define KBRATE_DELAY        0xe82      /* byte: ticks before a held key starts repeating */
#define KBRATE_REPEAT       0xe83      /* byte: ticks between repeats — Kbrate reports BOTH as a word */

/* The three IOREC rings the interrupt handlers fill and the BIOS drains, in XBIOS Iorec's own order.
 * The RS232 record is the first of a PAIR (its output record follows at $c62); the other two are
 * single. */
#define IOREC_RS232         0xc54
/* ...and the RS232's OUTPUT record, the second of the pair: one IOREC is 14 bytes, and the RS232 is
 * the only device with a ring in each direction. BIOS Bcostat(AUX:) is a question about THIS one. */
#define IOREC_RS232_OUT     0xc62
#define IOREC_RS232_BYTES   1           /* `addq.w #1,d1` — a raw byte a record, like MIDI's */
#define IOREC_IKBD          0xc76
#define IOREC_MIDI          0xd84

/* ...and one record's fields. `size` is in BYTES, and so are `head`/`tail`, which index the ring
 * rather than count records — a keyboard record is four bytes wide and a MIDI one is a single byte. */
#define IOREC_BUFFER        0           /* long: the ring's base address */
#define IOREC_SIZE          4           /* word: the ring's length in bytes */
#define IOREC_HEAD          6           /* word: the BIOS's read index */
#define IOREC_TAIL          8           /* word: the interrupt handler's write index */
#define IOREC_KEY_BYTES     4           /* the IKBD ring's record: scancode word + ASCII word */
#define IOREC_MIDI_BYTES    1           /* the MIDI ring's record: one raw byte */

/* The alpha-cursor / console state block the BIOS console driver and the VDI escape share. Cursconf
 * reaches it through `lea $2994,a4` and addresses the rest at negative displacements off it. */
#define CON_STATE_FLAGS     0x2994     /* byte: bit 0 = cursor blinks, bit 1 = cursor drawn now */
/* byte: `Cursconf` 6 writes it and 7 reads it back — and the console's own cursor tail ($fc479a)
 * reads it too: a NONZERO value suppresses the redraw and becomes the blink timer's next value,
 * which is what makes it the console's "stop drawing my cursor" byte rather than a spare one. */
#define CON_STATE_SPARE     0x2995
#define CON_BLINK_RATE      0x2982     /* byte: vertical blanks between cursor blinks ($2994 - 18) */

/* ---- the BIOS routines (trap #13, table $fc0846) ------------------------------------------------ */
#define BIOS_GETMPB_FN      0
#define BIOS_GETMPB         0xfc0a46
#define BIOS_BCONSTAT_FN    1
#define BIOS_BCONSTAT       0xfc0984
#define BIOS_BCONIN_FN      2
#define BIOS_BCONIN         0xfc098c
#define BIOS_SETEXC_FN      5
#define BIOS_SETEXC         0xfc0a72
#define BIOS_SETEXC_REPORT_ONLY 0x80000000u /* a handler with bit 31 set: Setexc's `bmi`, read only */
#define BIOS_TICKCAL_FN     6
#define BIOS_TICKCAL        0xfc0a8a
#define BIOS_BCOSTAT_FN     8
#define BIOS_BCOSTAT        0xfc0994
#define BIOS_DRVMAP_FN      10
#define BIOS_DRVMAP         0xfc0a2e
#define BIOS_KBSHIFT_FN     11
#define BIOS_KBSHIFT        0xfc0a34

/* ---- the XBIOS routines (trap #14, table $fc0878) ----------------------------------------------- */
#define XBIOS_LOGBASE_FN    3
#define XBIOS_LOGBASE       0xfc0aa6
#define XBIOS_IOREC_FN      14
#define XBIOS_IOREC         0xfc28f6
#define IOREC_TABLE         0xfc2902   /* ...and the three-longword table in ROM it indexes, unbounded */
#define IOREC_TABLE_ENTRY_BYTES 4      /* ...one ring address, which is also the index step */
#define XBIOS_KEYTBL_FN     16
#define XBIOS_KEYTBL        0xfc302e
#define XBIOS_PROTOBT_FN    18
#define XBIOS_PROTOBT       0xfc15f8
#define XBIOS_SCRDMP_FN     20          /* the VBL's screen dump (`src/bios/vbl.c`); v_hardcopy traps to it */
#define XBIOS_SCRDMP        0xfc0d50
#define XBIOS_CURSCONF_FN   21
#define XBIOS_CURSCONF      0xfc4698
#define XBIOS_BIOSKEYS_FN   24
#define XBIOS_BIOSKEYS      0xfc305a
#define XBIOS_KBRATE_FN     35
#define XBIOS_KBRATE        0xfc309a
#define XBIOS_SUPEXEC_FN    38
#define XBIOS_SUPEXEC       0xfc097e

/* ---- the character-device DRIVERS the three Bcon* entries jump through --------------------------
 * A vector, not an entry point: the tables above hold these, and which of them a device number
 * reaches is a fact about the RAM the snapshot captured rather than about the ROM. Only the drivers
 * whose whole body is an IOREC are here; the printer's, the RS232's and the console's OUTPUT drivers
 * poll the MFP or the ACIA and are out of reach (../README.md, the I/O-read refusal). */
#define ROM_BARE_RTS        0xfc0670   /* the shared `rts`: the vector for a device with no driver */
#define XCONSTAT_RS232      0xfc2138
#define XCONSTAT_CON        0xfc2226   /* the console's INPUT status is the IKBD ring's */
#define XCONSTAT_MIDI       0xfc2044
#define XCONIN_CON          0xfc223c
#define XCONIN_MIDI         0xfc2060
#define XCOSTAT_CON         0xfc226c   /* the screen is never busy: `moveq #-1,d0` and nothing else */
/* ...and Bcostat's other four drivers, every one of which is a SINGLE read of one declared byte (or,
 * for the RS232's, of no byte at all). They were out of reach while the declared I/O map answered
 * only what a case could name and the halt in `src/bios/bcon.c` described all of them as polling —
 * which was true of the MFP and the two 6850s and never true of the RS232's, whose whole body is
 * its own output ring (`$fc28ea` is the wrap arithmetic, not an access). */
#define XCOSTAT_PRT         0xfc2124   /* the Centronics BUSY line, MFP GPIP bit 0 */
#define XCOSTAT_RS232       0xfc219a   /* ...the RS232 OUTPUT ring: is there room for one more byte? */
#define XCOSTAT_IKBD        0xfc21dc   /* ...the IKBD 6850's TDRE */
#define XCOSTAT_MIDI        0xfc2004   /* ...and the MIDI 6850's, one register block along */
/* MIDI's reader ends `move.b (a1,d1.w),d0`, a BYTE into the D0 its status driver had just filled
 * with `moveq #-1` — so Bconin(MIDI) answers this OR the byte, and never the bare byte. */
#define MIDI_RESULT_PREFIX  0xffffff00u

/* ---- XBIOS Keytbl / Bioskeys -------------------------------------------------------------------- */
#define KEYTBL_UNSHIFTED_ROM 0xfc2288  /* the three 128-byte scancode tables Bioskeys restores */
#define KEYTBL_SHIFTED_ROM   0xfc2308
#define KEYTBL_CAPSLOCK_ROM  0xfc2388

/* ---- XBIOS Cursconf ----------------------------------------------------------------------------- */
#define CURSCONF_JUMP_TABLE   0xfc46b2  /* eight SIGNED WORD displacements, from the table's own address */
#define CURSCONF_MAX_FUNCTION 7        /* `cmp.w #7,d0 / bhi` — above it the routine just returns */
#define CURSCONF_HIDE         0        /* these two DRAW: they are the CONSOLE driver's own cursor */
#define CURSCONF_SHOW         1        /* renderer, `console_hide_cursor` / `console_show_cursor` */
#define CURSCONF_BLINK        2
#define CURSCONF_STEADY       3
#define CURSCONF_SET_RATE     4
#define CURSCONF_GET_RATE     5
#define CURSCONF_SET_SPARE    6
#define CURSCONF_GET_SPARE    7
#define CON_FLAG_BLINKS       0        /* bit number, as the ROM's `bset #0,(a4)` names it */

/* ---- XBIOS Protobt ------------------------------------------------------------------------------
 * The boot-sector prototyper: pure computation over the caller's 512-byte buffer, plus one call into
 * XBIOS Random when the serial number it is given will not fit in three bytes. */
#define BOOT_SECTOR_BYTES    512
#define BOOT_SECTOR_WORDS    256
#define BOOT_SERIAL_AT       8         /* buf[8..10]: the three-byte disk serial number */
#define BOOT_SERIAL_BYTES    3
#define BOOT_SERIAL_MAX      0xffffff  /* ...so a larger one is replaced by a random one */
#define BOOT_BPB_AT          11        /* buf[11..29]: the BPB the prototype table supplies */
#define BOOT_BPB_BYTES       19
#define BOOT_CHECKSUM_AT     510       /* buf[510..511]: the word that makes the sector sum to... */
#define BOOT_EXECUTABLE_SUM  0x1234    /* ...this, which is what makes a boot sector executable */
#define PROTOBT_BPB_TABLE    0xfd2f32  /* four 19-byte BPB prototypes, indexed by disk type */

/* ---- XBIOS Getrez ($04) — the first reconstruction to read a HARDWARE register ------------------
 * Every routine above this line is RAM only, which is what made it reachable before the DECLARED
 * I/O MAP existed. Getrez is three instructions and one of them is a read of the shifter, so it is
 * the smallest function that needs a case to say what the machine answers there
 * (`io_seed={SHIFTER_RESOLUTION: <byte>}`; TRAP_MODEL.md, Phase 15).
 *
 * The register is the kit's, not this project's: `OS_HW_IO_*` bound the page it is in, and a second
 * spelling of $ff8260 here would be a second place for the address to be right in the
 * reconstruction and wrong in the case that proves it. This project names WHICH register, and the
 * kit owns the page. */
#define SHIFTER_RESOLUTION  0xff8260   /* the shifter's resolution byte; bits 0-1 are the mode */
#define GETREZ_MODE_MASK    0x03       /* `and.b #3,d0` — 0 low, 1 medium, 2 high */
#define XBIOS_GETREZ_FN     0x04
#define XBIOS_GETREZ        0xfc0aac

/* ================================================================================================
 * THE XBIOS SCREEN AND SOUND LEAVES (BIOS wave 2)
 *
 * The group that reaches the SHIFTER and the YM2149 rather than only RAM: the screen base, the
 * palette, the frame clock a caller can wait on, and the two front ends of the 200 Hz sound and
 * printer state. Every hardware byte one of them reads is a case's `io_seed` declaration and every
 * one it writes is a `hw.h` ledger entry (../README.md, "Writing a case"; TRAP_MODEL.md, Phases 10
 * and 15).
 * ============================================================================================= */

/* ---- the shifter's screen base ($ff8201/$ff8203) ------------------------------------------------
 * TWO BYTES AT ODD ADDRESSES, holding bits 23..16 and 15..8 of the physical screen address; the low
 * eight bits do not exist, which is why an ST screen is 256-byte aligned. `Physbase` assembles the
 * pair and `Setscreen` stores it. */
#define SHIFTER_BASE_HIGH   0xff8201
#define SHIFTER_BASE_MID    0xff8203
#define SHIFTER_BASE_SHIFT  8          /* ...so the pair IS the address shifted down this far */

/* ---- the shifter's palette ($ff8240) ------------------------------------------------------------
 * Sixteen WORDS. `Setcolor` indexes one of them; the VBL handler at $fc06de loads all sixteen from
 * `SYSVAR_COLORPTR` when `Setpalette` has left a pointer there. */
#define SHIFTER_PALETTE     0xff8240
#define PALETTE_ENTRY_BYTES 2
/* `add.w d1,d1 / andi.w #$1f,d1` — the BYTE offset of the entry, so the index wraps every 16 colours
 * (`Setcolor(16, …)` is colour 0) and can never leave the row. */
#define SETCOLOR_INDEX_MASK  0x1f
/* `andi.w #$777,d0` — three bits per gun, which is all an ST shifter decodes, applied to the value
 * REPORTED and not to the value stored. */
#define SETCOLOR_VALUE_MASK  0x777

/* ---- system variables the screen and sound leaves keep ------------------------------------------ */
#define SYSVAR_COLORPTR     0x45a      /* long: 16 palette words the next VBL loads, then clears */
#define SYSVAR_FRCLOCK      0x466      /* long: vertical blanks since power-on — Vsync's whole wait */
/* The 200 Hz driver's two words of state ($fc312a reads both). Dosound replaces the cursor and
 * clears the delay so the driver runs the new list on its very next tick. */
#define SOUND_LIST_POINTER  0xe8a      /* long: where the driver reads its next command, or 0 */
#define SOUND_LIST_DELAY    0xe8e      /* byte: ticks still to wait before it does */
#define PRINTER_CONFIG      0xe90      /* word: the printer description Setprt keeps */

/* ---- the YM2149 port the GI-bit pair drives ----------------------------------------------------
 * Register 14 is port A, whose eight bits are the drive select, the side select, the printer strobe
 * and the RS232 handshake lines — i.e. everything on the machine that is neither sound nor an ACIA.
 * `Ongibit`/`Offgibit` are its read-modify-write, made through `Giaccess` rather than the ports. */
#define PSG_PORT_A          14

/* ---- the routines ------------------------------------------------------------------------------ */
#define XBIOS_PHYSBASE_FN   0x02
#define XBIOS_PHYSBASE      0xfc0a92
#define XBIOS_SETSCREEN_FN  0x05
#define XBIOS_SETSCREEN     0xfc0ab8
#define XBIOS_SETSCREEN_RESOLUTION_ARM 0xfc0ae0 /* `move.b 13(sp),$44c`: the arm the recreate halts at */
#define XBIOS_SETPALETTE_FN 0x06
#define XBIOS_SETPALETTE    0xfc0b06
#define XBIOS_SETCOLOR_FN   0x07
#define XBIOS_SETCOLOR      0xfc0b0e
#define XBIOS_OFFGIBIT_FN   0x1d
#define XBIOS_OFFGIBIT      0xfc2f02
#define XBIOS_ONGIBIT_FN    0x1e
#define XBIOS_ONGIBIT       0xfc2edc
#define XBIOS_DOSOUND_FN    0x20
#define XBIOS_DOSOUND       0xfc3074
#define XBIOS_SETPRT_FN     0x21
#define XBIOS_SETPRT        0xfc3088
#define XBIOS_VSYNC_FN      0x25
#define XBIOS_VSYNC         0xfc07d0
/* Vsync's WAIT SITE: the `cmp.l SYSVAR_FRCLOCK,d0` the spin re-executes, which is the PC the case's
 * schedule names as its trigger and the core names at every poll (sched.h; TRAP_MODEL.md, Phase 8).
 * It is the RE-READ and not the `beq` below it — the agent's store lands just before the site's
 * instruction, so naming the branch would apply it one instruction too late. */
#define VSYNC_WAIT_SITE     0xfc07dc

/* ---- the TRAP DISPATCHER: how every BIOS and XBIOS call is entered ($fc07f2..$fc0845) ------------
 * Reconstruction agent D's block. Two exception entries — `trap #14` picks the XBIOS table,
 * `trap #13` the BIOS one — falling into one shared body that saves the caller's file into the
 * BIOS's save area, bounds the function number, and `jsr`s through the table with A5 = 0.
 * `src/bios/trap.S` is the transcription and `test/trap.py` stages the CALLER that enters it. */
#define XBIOS_TRAP14          0xfc07f2  /* vector $b8: `lea XBIOS_FUNCTION_TABLE(pc),a0` */
#define BIOS_TRAP13           0xfc07f8  /* vector $b4: ...and the BIOS table, falling through into */
#define TRAP_DISPATCH_COMMON  0xfc07fc  /* the shared body, which is what both entries are FOR */
#define SYSVAR_SAVPTR         0x4a2     /* long: the walking top of the BIOS's register-save area */
#define SR_SUPERVISOR_BIT     13        /* `btst #13,d0` on the frame's SR word — was the caller
                                         * supervisor? If not, its arguments are on the USER stack */
#define TRAP_TABLE_ENTRY_SHIFT 2        /* `lsl.w #2` — the index, as a WORD, into longword entries */
/* The same 6 bytes `EXCEPTION_FRAME_BYTES` names below, under the name the trap dispatcher's own
 * battery reads it by: a group-2 exception frame and a group-1 one are the same shape on a 68000,
 * and one size spelt twice is one of the two waiting to be corrected alone. */
#define TRAP_EXCEPTION_FRAME_BYTES EXCEPTION_FRAME_BYTES
#define TRAP_SAVED_REGISTERS  10        /* d3-d7/a3-a7: what the dispatcher gives the caller back,
                                         * and the whole of it — d0-d2/a0-a2 are the callee's */
#define TRAP_SAVE_FRAME_BYTES 46        /* ...so one nesting level costs this much of the save area */

/* BIOS 4 (Rwabs) is the dispatch table's INDIRECT entry the battery exercises: its longword has bit
 * 31 set over this RAM vector, which the boot fills with the floppy driver and a hard-disk driver
 * replaces. A case pokes it to a routine of its own, which is the only way to watch the dispatcher
 * call something whose body the case wrote. */
#define BIOS_RWABS_FN         4
#define HDV_RWABS             0x476     /* long: `hdv_rw`, the entry at $fc0848 + 4*4 points at */

/* ---- the GEM trap ($fe3ea6) — its SELECTOR SWITCH, read but not reconstructed -------------------
 * `trap #2` is three interfaces behind one vector, told apart by D0 alone. Documented here because
 * the BIOS/XBIOS dispatcher's battery proves what a trap entry IS and this is the third one; the
 * arms themselves are the AES's and the VDI's waves. */
#define GEM_TRAP2             0xfe3ea6
#define GEM_SELECTOR_PTERM    0x0000    /* -> $fe3ec0: `Pterm(0)`, i.e. GEMDOS $4c through trap #1 */
#define GEM_SELECTOR_AES      0x00c8    /* -> $fe3eca: the AES dispatcher, via $fe3890/$fe65aa */
#define GEM_SELECTOR_AES_ALT  0x00c9    /* ...and the same arm: $c9 is $c8's alias */
#define GEM_TRAP2_PTERM_ARM   0xfe3ec0
#define GEM_TRAP2_AES_ARM     0xfe3eca
/* Inside that arm: past the caller's registers saved on its user stack ($fe3ed0..$fe3ed6, `move.l usp,a0` — a state no
 * oracle run stages), where the running PD's UDA is loaded and its stack taken ($fe3eee `movea.l 62(a6),sp`); and where
 * aes_entry has returned to it. A run between the two is a program's AES call on the stack the AES really runs on. */
#define GEM_TRAP2_AES_ON_UDA  0xfe3ed8
#define GEM_TRAP2_AES_BACK    0xfe3f08
#define GEM_TRAP2_VDI_ARM     0xfe3eb8  /* everything else: `move.l SYSVAR_VDI_ENTRY,-(sp) / rts` */
#define SYSVAR_VDI_ENTRY      0x8c2a    /* long: where that arm jumps — $fc4ebc in this snapshot */
/* ...which is the BIOS's own VDI door: D0 0 -> Pterm0's arm, $73 -> `jsr VDI_ROM_ENTRY` then `rte` ($fc4ec0 cmp.w). */
#define GEM_TRAP2_VDI_DOOR    0xfc4ebc
#define GEM_SELECTOR_VDI      0x0073    /* the VDI's selector ($fc4ec0 cmp.w #$73; the AES's gsx2 $fecb68 moveq) */

/* ================================================================================================
 * THE INTERRUPT HANDLERS (BIOS wave 2) — the every-tick code, entered through a LIVE VECTOR
 *
 * Everything below belongs to the four handlers the boot snapshot's own vector table points at:
 * the horizontal blank ($68), the vertical blank ($70), the MFP's 200 Hz timer C ($114) and the
 * ACIA channel the IKBD and MIDI 6850s share ($118). They are not trap routines — nothing calls
 * them, the machine does — so they take no arguments, return no result, and end in `rte` rather
 * than `rts`. `test/isr.py` is how a case enters one.
 * ============================================================================================= */

/* ---- the vector slots, and the handler the snapshot has in each --------------------------------
 * The VECTOR is the claim `test/isr.py` checks against the captured table: a handler reconstructed
 * at an address the machine does not dispatch to is a reconstruction of nothing. (`VECTOR_VBL`
 * above is the vertical blank's, already named because the capture stops inside it.) */
#define VECTOR_HBL            0x68      /* level-2 autovector — installed at $fc035e */
#define VECTOR_TIMER_C        0x114     /* MFP channel 5: timer C, the 200 Hz system tick */
#define VECTOR_ACIA           0x118     /* MFP channel 6: the IKBD and MIDI 6850s, one line between them */
#define ISR_HBL               0xfc06c8
#define ISR_VBL               0xfc06de
#define ISR_TIMER_C           0xfc30c4
#define ISR_ACIA              0xfc29ce
/* ...and where each handler's EXIT sequence begins, which is where the two paths of the VBL and of
 * timer C meet. `src/bios/isr.S` carries those sequences instruction for instruction and
 * `test/isr.py`'s `LITERAL_SPANS` compares the assembled words with the ROM's at these addresses —
 * a transcription that has to name the ROM span it is a transcription OF. */
#define ISR_VBL_RELEASE            0xfc07c4  /* `movem.l (sp)+,d0-a6`, then `addq.w #1,vblsem` */
#define ISR_TIMER_C_ACKNOWLEDGE    0xfc311c  /* ...then `bclr #5,$fffa11` on both paths */
#define ISR_ACIA_RESTORE           0xfc29f6  /* `movem.l (sp)+,d0-d3/a0-a3/a5` and the `rte` */

/* ---- the exception frame a handler returns through ---------------------------------------------
 * The 68000's group-1/2 frame: the SR the interrupt was taken at, then the PC it resumes at. The
 * HBL is the one handler here that WRITES it (`ori.w #$300,2(sp)` reaches the SR word past its own
 * pushed D0), so the offsets are named rather than spelt at the one site that uses them. */
#define EXCEPTION_FRAME_SR    0         /* word */
#define EXCEPTION_FRAME_PC    2         /* long */
#define EXCEPTION_FRAME_BYTES 6
#define SR_IPL_MASK           0x0700    /* the status register's three interrupt-mask bits */
#define HBL_IPL_FLOOR         0x0300    /* what the HBL ors into a frame whose mask is 0 */

/* ---- the system variables the VBL keeps ---------------------------------------------------------
 * Every one of them is reached as a 16-bit displacement off the A5 the handler zeroes itself, which
 * is the same `(a5)` addressing the trap dispatcher's own `suba.l a5,a5` sets up (COMPONENTS.md). */
#define SYSVAR_ETV_TIMER      0x400     /* long: -> the OS timer-tick vector timer C calls */
#define SYSVAR_FLOCK          0x43e     /* word: nonzero while a disk operation owns the FDC */
#define SYSVAR_DEFSHIFTMD     0x44a     /* byte: the resolution to restore when a colour monitor returns */
#define SYSVAR_SSHIFTMD       0x44c     /* byte: the shadow of the shifter's resolution register */
#define SYSVAR_VBLSEM         0x452     /* word: the VBL's re-entry semaphore — 1 open, <= 0 closed */
#define SYSVAR_NVBLS          0x454     /* word: how many slots _vblqueue has */
#define SYSVAR_VBLQUEUE       0x456     /* long: -> that many routine pointers, 0 for an empty slot */
#define SYSVAR_SCREENPT       0x45e     /* long: -> the screen base to program this VBL, or 0 */
#define SYSVAR_VBCLOCK        0x462     /* long: vertical blanks SERVICED (the semaphore was open) */
/* `SYSVAR_COLORPTR` ($45a) and `SYSVAR_FRCLOCK` ($466) are named with the screen leaves above, which
 * is where they are written; this handler is what reads and clears them. */
#define SYSVAR_SWV_VEC        0x46e     /* long: -> the routine a MONITOR CHANGE calls */
#define SYSVAR_CONTERM        0x484     /* byte: bit 0 = key click, bit 1 = key repeat */
#define SYSVAR_DUMPFLG        0x4ee     /* word: 0 asks this VBL for a screen dump; Scrdmp sets -1 */
#define SYSVAR_SCR_DUMP       0x502     /* long: -> the screen-dump routine Scrdmp jumps through */
#define VBLQUEUE_ENTRY_BYTES  4         /* ...and one slot of _vblqueue, which is the walk's step */
#define CONTERM_REPEAT_BIT    1         /* bit number, as the ROM's `btst #1,conterm` names it */

/* ---- the shifter and MFP registers these handlers touch ------------------------------------------
 * `SHIFTER_PALETTE`, `PALETTE_ENTRY_BYTES` and the two `SHIFTER_BASE_*` bytes are named with the
 * screen leaves above — the VBL programs the same registers `Setpalette` and `Setscreen` queue for
 * it, and a second spelling of $ff8240 would be a second place for one of them to be wrong. What is
 * this handler's own is how MANY palette words it moves, and the MFP. `MFP_GPIP` is os.h's
 * `OS_HW_MFP_GPIP`, spelt here because `tools/addrs.py` reads integers only and pinned equal to the
 * kit's by `test_bios_vbl.py::test_the_mfp_gpip_this_project_names_is_the_kit_s_own_slot`. */
#define SHIFTER_PALETTE_ENTRIES    16        /* `move.w #15,d0 / dbf` — the whole row, every VBL */
#define SHIFTER_MODE_LOW           0         /* Getrez's answers: ST low (setres's `tst.b`, $fca6f2) */
#define SHIFTER_MODE_MEDIUM        1         /* ...ST medium (setres's `moveq #1`, $fca726) */
#define SHIFTER_MODE_HIGH          2         /* `cmp.b #2,d0`: ST high, the mono monitor's resolution */
#define MFP_GPIP                   0xfffa01  /* = OS_HW_MFP_GPIP */
#define MFP_GPIP_MONOCHROME_BIT    7         /* 0 = a mono monitor is attached */
#define MFP_GPIP_ACIA_BIT          4         /* 0 = one of the two 6850s still wants service */
#define MFP_GPIP_PRINTER_BUSY_BIT  0         /* 1 = the Centronics port is BUSY (BIOS Bcostat) */
#define MFP_ISRB                   0xfffa11  /* in-service register B: a handler clears its own bit */
#define MFP_ISRB_TIMER_C_BIT       5
#define MFP_ISRB_ACIA_BIT          6

/* The ROM addresses the VBL's own body sits at — $fc4666 (the cursor blink), $fc4a1e (the cell
 * inversion), $fc1bc4 (the floppy service) and $fc0d50 (Scrdmp) — are named in `src/bios/vbl.c` at
 * the code that reconstructs each, and in the halt message of the one that is deferred. Nothing
 * compiles against them, so they are not `#define`s here: an address no build and no case reads is
 * a second spelling waiting to disagree with the comment beside the code.
 *
 * What IS here is the one byte of RAM that body writes before any of it. */
#define FLOPPY_VBL_ENTERED    0xa04     /* byte: the `st` the floppy VBL sets before it looks at flock */

/* ---- the alpha cursor's own state, past what Cursconf already names ------------------------------
 * All of it is reached as a displacement off `CON_STATE_FLAGS`, which is the block's anchor. */
#define CON_CURSOR_DISABLE    0x2840    /* word: nonzero suppresses the blink entirely ($2994 - 340) */
#define CON_BLINK_TIMER       0x2983    /* byte: vertical blanks left before the next toggle */
#define CON_CURSOR_ADDRESS    0x2978    /* long: -> the cursor cell's top-left byte on screen */
#define CON_CELL_HEIGHT       0x296c    /* word: scan lines in a character cell */
#define CON_PLANES            0x299a    /* word: bit planes — the cursor is inverted in each */
#define CON_LINE_BYTES        0x299c    /* word: bytes from one scan line to the next */
#define CON_FLAG_DRAWN        1         /* bit number: the cursor is on screen right now */
/* ...and how far apart the planes are, which is the cursor inversion's OUTER step (`addq.w #2,a1`):
 * an ST interleaves its bit planes word by word, so one 16-pixel screen cell is `CON_PLANES` words
 * side by side. Here rather than in `vbl.c` because `test_bios_vbl.py` computes the same set of
 * inverted bytes and a second spelling would be one the C could be corrected without. */
#define SCREEN_PLANE_WORD_BYTES 2

/* ---- timer C: the 200 Hz tick, its fourth-tick divider, and the keyboard's auto-repeat ----------- */
#define SYSVAR_TIMER_C_DIVIDER 0xe88    /* word: `rol.w` once a tick; the body runs when it goes negative */
#define SYSVAR_KB_REPEAT_KEY   0xe7f    /* byte: the scancode being auto-repeated, 0 for none */
#define SYSVAR_KB_REPEAT_DELAY 0xe80    /* byte: ticks left of the initial delay */
#define SYSVAR_KB_REPEAT_LEFT  0xe81    /* byte: ticks left until the next repeat */

/* ---- ...and the Dosound driver the same tick steps ------------------------------------------------
 * The sound table interpreter: a byte under $80 is a REGISTER to write, and $80/$81/anything above
 * are the three commands. `SYSVAR_DOSOUND_TEMP` is the byte command $81 ramps. */
/* `SOUND_LIST_POINTER` ($e8a) and `SOUND_LIST_DELAY` ($e8e) are named with XBIOS `Dosound` above,
 * which is the call that plants them; this is the driver that consumes them, plus the one byte only
 * the driver has. */
#define SOUND_RAMP_VALUE       0xe8f    /* byte: the accumulator command $81 steps towards its end */
#define DOSOUND_COMMAND_FLOOR  0x80     /* `bmi`: at or above this the byte is a command, not a register */
#define DOSOUND_LOAD_TEMP      0x80     /* $80 <byte>: load the accumulator */
#define DOSOUND_RAMP           0x81     /* $81 <reg> <step> <end>: step it and write it, once a tick */
#define DOSOUND_RAMP_OPERANDS  4        /* ...and the `subq.w #4,a0` that replays the whole command */
#define PSG_MIXER_REGISTER     7        /* the one register the driver READ-MODIFY-WRITES */
#define PSG_MIXER_CHANNEL_MASK 0x3f     /* ...taking these bits from the list... */
#define PSG_MIXER_PORT_MASK    0xc0     /* ...and keeping these, which are the two I/O port directions */

/* ---- the ACIA handler's two service vectors ------------------------------------------------------
 * The last two longwords of KBDVECS, which is what `Kbdvbase` hands a caller: the handler calls
 * both on every entry and goes round again while the MFP says either 6850 still wants service. */
#define KBDVECS                0xe12    /* nine longwords; `Kbdvbase` ($fc30bc) returns this */
#define KBDVECS_MIDISYS        0x1c     /* -> the MIDI 6850's service routine ($fc29fc) */
#define KBDVECS_IKBDSYS        0x20     /* -> the IKBD 6850's ($fc2a0c) */

/* ================================================================================================
 * THE MFP / TIMER / IKBD / SERIAL ROUTINES (BIOS wave 2)
 *
 * Everything below belongs to the group of XBIOS entries whose body is the MFP 68901's interrupt
 * controller and timers, one of the two 6850 ACIAs, or the MFP's own USART. They are the first
 * reconstructions here to WRITE hardware (TRAP_MODEL.md, Phase 10) and the first to change a bit of
 * a register they had to read first, which is what the DECLARED I/O MAP (Phase 15) makes provable —
 * `include/xbios/mfp.h` carries that argument, and the bound on it.
 * ============================================================================================= */

/* ---- the MFP 68901's registers -----------------------------------------------------------------
 * Every one of them is an ODD byte on a two-byte stride, because the chip sits on the low half of
 * the bus; the ROM reaches all of them off one `lea $fffffa01,a0` and names the rest by
 * displacement. These are the 24-BIT BUS FORMS, which is what a reconstruction spells and what the
 * oracle decodes (`hw.h`: the untranslated `$fffffa01` is a refusal, not an alias). */
/* `MFP_GPIP` ($fffa01) is the block's anchor and is already named above, with the VBL's own bits. */
#define MFP_IERA            0xfffa07   /* interrupt ENABLE, channels 8..15 */
#define MFP_IERB            0xfffa09   /* ...and channels 0..7 */
#define MFP_IPRA            0xfffa0b   /* interrupt PENDING */
#define MFP_IPRB            0xfffa0d
#define MFP_ISRA            0xfffa0f   /* interrupt IN-SERVICE — `MFP_ISRB` is named above */
#define MFP_IMRA            0xfffa13   /* interrupt MASK */
#define MFP_IMRB            0xfffa15
#define MFP_TACR            0xfffa19   /* timer A control — its own byte */
#define MFP_TBCR            0xfffa1b   /* timer B control — its own byte */
#define MFP_TCDCR           0xfffa1d   /* timers C and D SHARE this one: C bits 4-6, D bits 0-2 */
#define MFP_TADR            0xfffa1f   /* the four timers' data registers (the reload count) */
#define MFP_TBDR            0xfffa21
#define MFP_TCDR            0xfffa23
#define MFP_TDDR            0xfffa25
#define MFP_SCR             0xfffa27   /* USART synchronous character */
#define MFP_UCR             0xfffa29   /* USART control */
#define MFP_RSR             0xfffa2b   /* receiver status */
#define MFP_TSR             0xfffa2d   /* transmitter status */
#define MFP_UDR             0xfffa2f   /* USART data */

/* ...and the interrupt-channel arithmetic the three interrupt routines share ($fc26e6). */
#define MFP_CHANNEL_MASK      0x0f     /* `andi.l #15,d0` — the four bits a channel number is */
#define MFP_CHANNELS_PER_HALF 8        /* channels 8..15 are register A's bits 0..7 ... */
#define MFP_HALF_B_STEP       2        /* ...and 0..7 are register B's, two bytes above it */
#define MFP_BIT_NUMBER_MASK   0x07     /* `bclr d1,(a1)`: a bit number on MEMORY is modulo 8, which
                                        * is what bounds the half-select's answer for a channel byte
                                        * `Xbtimer` never masked (`include/xbios/mfp.h`) */
#define MFP_VECTOR_TABLE      0x100    /* `addi.l #256,d2` — the MFP's base vector register is $40,
                                        * so its sixteen channels are exception vectors $40..$4f */

/* ---- the MFP's four timers, and the tables the ROM's shared programmer at $fc25b0 indexes -------
 * Eight adjacent four-byte tables in the ROM, every one indexed by the timer number with a SIGNED
 * WORD add. The reconstruction reads them out of the mapped image rather than copying them into C
 * arrays, so an out-of-range timer reads the next table along exactly as the ROM does. */
#define MFP_TIMER_A         0
#define MFP_TIMER_B         1
#define MFP_TIMER_C         2
#define MFP_TIMER_D         3
#define MFP_TIMERS          4
#define MFP_TIMER_IER_OFFSETS      0xfc2638  /* +$06 +$06 +$08 +$08 off MFP_GPIP: IERA, IERA, IERB… */
#define MFP_TIMER_IPR_OFFSETS      0xfc263c
#define MFP_TIMER_ISR_OFFSETS      0xfc2640
#define MFP_TIMER_IMR_OFFSETS      0xfc2644
#define MFP_TIMER_INTERRUPT_MASKS  0xfc2648  /* $df $fe $df $ef — one bit cleared, per timer */
#define MFP_TIMER_CONTROL_OFFSETS  0xfc264c  /* +$18 +$1a +$1c +$1c: TACR, TBCR, then TCDCR twice */
#define MFP_TIMER_CONTROL_MASKS    0xfc2650  /* $00 $00 $8f $f8 — and THIS is what the pair is for */
#define MFP_TIMER_DATA_OFFSETS     0xfc2654  /* +$1e +$20 +$22 +$24: TADR, TBDR, TCDR, TDDR */

/* ---- the two 6850 ACIAs ($fffc00 the IKBD's, $fffc04 the MIDI's) ------------------------------- */
/* The IKBD's pair is the kit's, not this project's — `os.h` names both as Phase-7 NAMED slots — but
 * `tools/addrs.py` takes plain integers only, so it is spelt here as `MFP_GPIP` above is and
 * `test_xbios_ikbdws.py` pins the two equal against the oracle's own slot table rather than leaving
 * a second spelling to drift. The MIDI pair is nobody's named slot and is this project's to name. */
#define IKBD_ACIA_STATUS    0xfffc00           /* = OS_HW_ACIA_STATUS */
#define IKBD_ACIA_DATA      0xfffc02           /* = OS_HW_ACIA_DATA */
#define MIDI_ACIA_STATUS    0xfffc04
#define MIDI_ACIA_DATA      0xfffc06
#define ACIA_TRANSMIT_READY 0x02               /* = OS_ACIA_TX_RDY: the transmit register is empty */
/* `move.w #950,d2` + `dbf` = 951 iterations of `bsr` to an `rts`, between the IKBD's status poll
 * and its data store. Pure delay — the 6301 needs the gap — and the MIDI sender has none. */
#define IKBD_SETTLE_ITERATIONS 951

/* ---- KBDVECS: the IKBD/MIDI interrupt dispatch table in RAM, and Kbdvbase's whole body ---------- */
/* `KBDVECS` ($e12) is named above, with the two service vectors the ACIA handler calls. This is the
 * slot `Initmous` installs into, and `Kbdvbase`'s `move.l #$e12,d0` is the table's whole address. */
#define KBDVECS_MOUSEVEC    0x10       /* -> the IKBD mouse-packet handler */
#define KBDVECS_LONGWORDS   9

/* ---- XBIOS Initmous ----------------------------------------------------------------------------
 * The mouse reporting modes, the IKBD commands each one sends, and the parameter block's fields. */
#define INITMOUS_PACKET     0xe6e      /* the command buffer the routine builds its packet in */
#define INITMOUS_DISABLE    0
#define INITMOUS_RELATIVE   1
#define INITMOUS_ABSOLUTE   2
#define INITMOUS_KEYCODE    4
#define INITMOUS_DONE       0xffffffffu  /* `moveq #-1,d0` — every mode that sent something */
#define INITMOUS_UNKNOWN_MODE 0          /* `moveq #0,d0` — 3, 5 and up, vector installed anyway */
#define INITMOUS_RELATIVE_COUNT 6      /* the `Ikbdws` counts, which are ONE LESS than the bytes */
#define INITMOUS_ABSOLUTE_COUNT 16
#define INITMOUS_KEYCODE_COUNT  5
#define IKBD_SET_BUTTON_ACTION    0x07  /* the 6301's own command bytes */
#define IKBD_SET_RELATIVE_MOUSE   0x08
#define IKBD_SET_ABSOLUTE_MOUSE   0x09
#define IKBD_SET_KEYCODE_MOUSE    0x0a
#define IKBD_SET_MOUSE_THRESHOLD  0x0b
#define IKBD_SET_MOUSE_SCALE      0x0c
#define IKBD_SET_MOUSE_POSITION   0x0e
#define IKBD_DISABLE_MOUSE        0x12
#define MOUSE_PARAM_TOPMODE   0        /* the parameter block, as the ROM copies it */
#define MOUSE_PARAM_BUTTONS   1
#define MOUSE_PARAM_XPARAM    2
#define MOUSE_PARAM_YPARAM    3
#define MOUSE_PARAM_XMAX      4        /* four big-endian PAIRS, absolute mode only */
#define MOUSE_PARAM_YMAX      6
#define MOUSE_PARAM_XINITIAL  8
#define MOUSE_PARAM_YINITIAL  10
#define MOUSE_PARAM_PAIR_BYTES 2
#define MOUSE_COMMON_BYTES    5        /* xparam, yparam, the origin, the command and its byte */
#define MOUSE_TOPMODE_ORIGIN  16       /* `moveq #16,d1 / sub.b (a3),d1` — a BYTE subtract */
#define MOUSE_POSITION_FILLER 0        /* `move.b #0,(a2)+` after the set-position command */
#define MOUSE_DISCARD_HANDLER 0xfc3028 /* the ROM `rts` Initmous(0) parks `mousevec` on */

/* ---- XBIOS Rsconf ------------------------------------------------------------------------------ */
#define IOREC_FLOW_CONTROL  0x20       /* the RS232 input IOREC's handshake byte, past the record */
/* = IOREC_RS232 + IOREC_FLOW_CONTROL, spelt out because `tools/addrs.py` takes plain integers only;
 * `test_xbios_rsconf.py` asserts the sum rather than leaving the two spellings to drift. */
#define RSCONF_FLOW_CONTROL 0xc74
#define RSCONF_FLOW_NONE    0          /* 0 and 2 stand; `andi.b #$fd` is what says so... */
#define RSCONF_FLOW_KEEP_MASK 0xfd
#define RSCONF_FLOW_XON_XOFF 1         /* ...and every other value is stored back as this one */
#define RSCONF_USART_OFF    0          /* RSR and TSR across a baud change: off, then on */
#define RSCONF_USART_ON     1
#define RSCONF_BAUD_CONTROL_TABLE 0xfc29ae  /* timer D's control byte per rate: 14 x $01, then $02 */
#define RSCONF_BAUD_DATA_TABLE    0xfc29be  /* ...and its divider */
#define RSCONF_BAUD_RATES   16         /* both tables, and the bound the routine does NOT apply */
/* ...and the caller's argument frame, which this routine reads as a BLOCK rather than as registers:
 * six optional words at `4(sp)`..`14(sp)`, each one negative for "leave this alone". */
#define RSCONF_ARG_BAUD     0
#define RSCONF_ARG_FLOW     2
#define RSCONF_ARG_UCR      4
#define RSCONF_ARG_RSR      6
#define RSCONF_ARG_TSR      8
#define RSCONF_ARG_SCR      10

/* ---- the XBIOS routines (trap #14, table $fc0878) ----------------------------------------------- */
#define XBIOS_INITMOUS_FN   0x00
#define XBIOS_INITMOUS      0xfc2f28
#define XBIOS_MIDIWS_FN     0x0c
#define XBIOS_MIDIWS        0xfc2030
#define XBIOS_MFPINT_FN     0x0d
#define XBIOS_MFPINT        0xfc2658
#define XBIOS_RSCONF_FN     0x0f
#define XBIOS_RSCONF        0xfc290e
#define XBIOS_IKBDWS_FN     0x19
#define XBIOS_IKBDWS        0xfc2212
#define XBIOS_JDISINT_FN    0x1a
#define XBIOS_JDISINT       0xfc2682
#define XBIOS_JENABINT_FN   0x1b
#define XBIOS_JENABINT      0xfc26bc
#define XBIOS_XBTIMER_FN    0x1f
#define XBIOS_XBTIMER       0xfc2ff2
#define XBIOS_KBDVBASE_FN   0x22
#define XBIOS_KBDVBASE      0xfc30bc

/* ---- and the ROM addresses a SLICE case stops at ------------------------------------------------
 * Two routines here cannot be run to their `rts` under the declared I/O map, because each reads a
 * register back after storing to it (`src/xbios/mfp.c` and `src/xbios/xbtimer.c` carry the
 * measurement). What a case can do is stop at the instruction before the read-back, which is what
 * `differential(..., stop_pc=)` is for — the same way a routine that never returns is proved. */
#define MFPINT_ENABLE_HALF     0xfc267a  /* Mfpint's `bsr` into Jenabint's body: where it splits */
#define MFP_TIMER_PROGRAM      0xfc25b0  /* the shared timer programmer Xbtimer and Rsconf call */
#define MFP_TIMER_DATA_WRITE   0xfc2600  /* ...and where ITS slice ends, before the data register */
#define XBTIMER_CHANNEL_TABLE  0xfc302a  /* timer -> MFP channel: 13, 8, 5, 4 for A, B, C, D */
#define XBTIMER_TIMER_MASK     0xff      /* `andi.l #255,d0` before that table read — a BYTE, not 3 */

/* ================================================================================================
 * THE ACIA INPUT CHAIN (BIOS wave 3) — what the two KBDVECS service routines do with a byte
 *
 * The ACIA handler above asks each 6850 in turn through a RAM vector; this is what those two
 * vectors point at in the captured machine, and everything below them. One byte out of a data port
 * is either a PACKET (the 6301 reports the mouse, the joysticks, the clock and its own status with
 * a header byte $f6..$ff and a fixed number of bytes after it) or a SCANCODE — and the ROM tells
 * them apart by a single byte of state, `IKBD_PACKET_KIND`, which is non-zero exactly while a
 * packet is in progress. `src/bios/acia_service.c` and `src/bios/keyboard.c` are the two halves.
 * ============================================================================================= */

/* ---- the routines, and the internal entries a case enters directly ------------------------------ */
#define MIDI_ACIA_SERVICE      0xfc29fc  /* KBDVECS' midisys: the MIDI 6850's service routine */
#define IKBD_ACIA_SERVICE      0xfc2a0c  /* ...and ikbdsys. It FALLS INTO the shared body below */
#define ACIA_SERVICE_BODY      0xfc2a1a  /* the status test both entries reach, and the whole of them */
#define ACIA_SERVICE_RTS       0xfc2a40  /* the `rts` the body ends at — and what both error vectors
                                          * hold in this capture, so an overrun is a no-op here */
#define ACIA_TAKE_BYTE         0xfc2a42  /* the byte itself: a packet, a scancode, or MIDI's ring */
#define KBD_SCANCODE           0xfc2b5c  /* ...the scancode arm: the shift machine and auto-repeat */
#define KBD_QUEUE_KEY          0xfc2c42  /* ...and the translation into the IKBD IOREC's 4-byte record */
#define MIDI_QUEUE_BYTE        0xfc2e3a  /* the ROM's own `midivec`: one raw byte into the MIDI ring */

/* ---- the 6850's status bits the shared body tests, in the order it tests them ------------------- */
#define ACIA_INTERRUPT         0x80      /* `btst #7`: this chip is the one that raised the line */
#define ACIA_RECEIVE_FULL      0x01      /* `btst #0`: a byte is waiting in the receive register */
#define ACIA_OVERRUN           0x20      /* `andi.b #32`: one was lost — the error vector is called */
#define ACIA_DATA_OFFSET       2         /* `2(a1)`: the data port, two bytes above the status one */

/* ---- KBDVECS' first seven longwords, which is the rest of the table named above ----------------- */
#define KBDVECS_MIDIVEC        0x00      /* -> what a MIDI byte goes to ($fc2e3a in this capture) */
#define KBDVECS_VKBDERR        0x04      /* -> an IKBD overrun */
#define KBDVECS_VMIDERR        0x08      /* -> a MIDI overrun */
#define KBDVECS_STATVEC        0x0c      /* -> a completed $f6 status packet */
/* `KBDVECS_MOUSEVEC` (0x10) is named with `Initmous` above, which is what installs the mouse. */
#define KBDVECS_CLOCKVEC       0x14      /* -> a completed $fc time-of-day packet */
#define KBDVECS_JOYVEC         0x18      /* -> a completed $fd/$fe/$ff joystick packet */

/* ---- the packet state machine's two bytes, and the buffers the packets are assembled in ---------
 * The buffers are adjacent and their bounds come out of the ROM's own descriptor table below, so
 * each address here is the START of one packet and the END of the one before it. */
#define IKBD_PACKET_KIND       0xe36     /* byte: 0 = no packet in progress, else 1..7 (the table) */
#define IKBD_PACKET_REMAINING  0xe37     /* byte: how many more bytes this packet wants */
#define IKBD_STATUS_PACKET     0xe38     /* 7 bytes: the $f6 status report */
#define IKBD_ABSOLUTE_MOUSE_PACKET 0xe3f /* 5 bytes: the $f7 absolute-mouse report, header dropped */
#define IKBD_RELATIVE_MOUSE_PACKET 0xe44 /* 3 bytes: the $f8..$fb header, then dx and dy */
#define IKBD_CLOCK_PACKET      0xe47     /* 6 bytes: the $fc time of day, header dropped */
#define IKBD_JOYSTICK_PACKET   0xe4d     /* the $fd/$fe/$ff packet — see IKBD_JOYSTICK_DATA */
#define IKBD_JOYSTICK_DATA     0xe4e     /* ...where kinds 6 and 7 store, at + (kind - 6) */
#define IKBD_PACKET_END        0xe4f     /* one past the joystick packet: the table's last `end` */
#define KBD_MOUSE_PACKET       0xe5e     /* 3 bytes: the packet the ALT+arrow mouse EMULATION builds,
                                          * which is its own buffer and not the 6301's */

/* ---- the three ROM tables the packet machine indexes -------------------------------------------- */
#define IKBD_FIRST_HEADER      0xf6      /* `cmpi.b #$f6,d0 / bcs`: below this a byte is a scancode */
#define IKBD_PACKET_KIND_TABLE  0xfc2aa2 /* header - $f6 -> kind 1..7 */
#define IKBD_PACKET_COUNT_TABLE 0xfc2aac /* header - $f6 -> how many bytes follow it */
#define IKBD_PACKET_TABLE       0xfc2b06 /* kind 1..5 -> three longwords: */
#define IKBD_PACKET_TABLE_STRIDE 12      /*   ...`(kind - 1) * 3 * 4`, as the ROM's shifts compute it */
#define IKBD_PACKET_TABLE_START  0       /*   the packet's address, which is what the vector is given */
#define IKBD_PACKET_TABLE_END    4       /*   one past its last byte: the fill runs END - REMAINING */
#define IKBD_PACKET_TABLE_VECTOR 8       /*   -> the KBDVECS SLOT to call, not the routine */
#define IKBD_FIRST_UNTABLED_KIND 6       /* `cmpi.b #6 / bcc`: kinds 6 and 7 are the two one-stick
                                          * joystick reports, which the table does not describe */
/* ...and the two header ranges the BEGIN arm stores the header byte itself for, as the ROM's two
 * SIGNED byte compares name them (`cmpi.b #-8` / `#-5` / `#-3`). $f6, $f7 and $fc store nothing. */
#define IKBD_RELATIVE_MOUSE_FIRST 0xf8
#define IKBD_RELATIVE_MOUSE_LAST  0xfb
#define IKBD_JOYSTICK_FIRST       0xfd

/* ---- kbshift's bits, as the ROM's `bset`/`bclr`/`btst` immediates name them --------------------- */
#define KBSHIFT_RIGHT_SHIFT_BIT  0
#define KBSHIFT_LEFT_SHIFT_BIT   1
#define KBSHIFT_CONTROL_BIT      2
#define KBSHIFT_ALTERNATE_BIT    3
#define KBSHIFT_CAPSLOCK_BIT     4
#define KBSHIFT_RIGHT_BUTTON_BIT 5      /* ALT+Home — the emulated mouse's buttons live here too */
#define KBSHIFT_LEFT_BUTTON_BIT  6      /* ALT+Insert */
#define KBSHIFT_EITHER_SHIFT     0x03   /* `andi.b #3`: the two shift keys, tested as one mask */
#define KBSHIFT_BUTTON_SHIFT     5      /* `lsr.b #5`: the two button bits ARE the packet header's */
#define KBD_MOUSE_HEADER_BIAS    0xf8   /* ...after `addi.b #-8`, which biases them to $f8..$fb */

/* ---- conterm's other two bits (bit 1, the repeat gate, is named with the VBL above) ------------- */
#define CONTERM_CLICK_BIT        0      /* 1 = every key starts the click list below */
#define CONTERM_KBSHIFT_BIT      3      /* 1 = the IOREC record carries kbshift in its top byte */
#define KEYCLICK_SOUND_LIST      0xfc31e0  /* the Dosound list a click plants in `SOUND_LIST_POINTER` */

/* ---- the scancodes the shift machine and the two modifier arms name ----------------------------- */
#define SCANCODE_BREAK_BIT       7      /* `btst #7,d0`: set on the release of every key */
#define SCANCODE_INDEX_MASK      0x7f   /* `andi.w #127,d0`: what indexes a 128-byte key table */
#define SCANCODE_LEFT_SHIFT      0x2a
#define SCANCODE_RIGHT_SHIFT     0x36
#define SCANCODE_CONTROL         0x1d
#define SCANCODE_ALTERNATE       0x38
#define SCANCODE_CAPSLOCK        0x3a   /* the MAKE only: its break falls through to the key path */
#define SCANCODE_RELEASE         0x80   /* ...and the same bit as a MASK, which is what a
                                        * break scancode is its make plus. Two spellings of
                                        * one bit because the ROM uses both: `btst #7,d0` to
                                        * sort make from break, and $aa/$b6/$9d/$b8 as whole
                                        * bytes in the modifier chain */
/* The two BREAKS the release arm lets through to the key path, because ALT+Home and ALT+Insert are
 * the emulated mouse buttons and a button has to come back up. */
#define SCANCODE_HOME_BREAK      0xc7
#define SCANCODE_INSERT_BREAK    0xd2
/* ...and the four codes ALT looks for, as the ROM's own four-byte table rather than as constants:
 * $47, $c7, $52, $d2, walked from the END by a `dbf`. */
#define ALT_MOUSE_BUTTON_KEYS    0xfc2ea0
#define ALT_MOUSE_BUTTON_KEY_COUNT 4
/* Which button a matched key is: bit 4 of the scancode separates Home ($47/$c7) from Insert
 * ($52/$d2), and the ROM turns it into a kbshift bit number by adding it to bit 5. */
#define ALT_MOUSE_BUTTON_SELECT_BIT 4

/* ---- the keys the CONTROL and ALTERNATE arms rewrite -------------------------------------------- */
#define SCANCODE_FUNCTION_FIRST  0x3b   /* F1..F10, which SHIFT moves up by ten keys */
#define SCANCODE_FUNCTION_LAST   0x44
#define SCANCODE_FUNCTION_SHIFTED 25    /* `addi.w #25`: $3b -> $54, the shifted F-key codes */
#define SCANCODE_HOME            0x47
#define SCANCODE_CURSOR_UP       0x48
#define SCANCODE_CURSOR_LEFT     0x4b
#define SCANCODE_CURSOR_RIGHT    0x4d
#define SCANCODE_CURSOR_DOWN     0x50
#define SCANCODE_HELP            0x62   /* ALT+Help is the screen dump */
#define CONTROL_HOME_OFFSET      0x30   /* `addi.w #48`: ALT-less CTRL+Home becomes scancode $77 */
#define CONTROL_CURSOR_LEFT      0x73   /* ...and the two horizontal cursor keys get codes outright */
#define CONTROL_CURSOR_RIGHT     0x74
#define SCANCODE_DIGIT_FIRST     0x02   /* the number row, `1` through `=`, which ALT renumbers */
#define SCANCODE_DIGIT_LAST      0x0d
#define ALT_DIGIT_OFFSET         0x76   /* `addi.b #118`: $02 -> $78, the ALT-digit codes */
/* ...and how far the emulated mouse moves per keypress, which SHIFT changes from a step to a pixel. */
#define KBD_MOUSE_STEP           8
#define KBD_MOUSE_FINE_STEP      1

/* ---- what the CONTROL arm does to the ASCII the key table produced ------------------------------ */
#define ASCII_CARRIAGE_RETURN    0x0d   /* CTRL+M's table byte, which the arm turns into a line feed */
#define ASCII_LINE_FEED          0x0a
#define CONTROL_MASK             0x1f   /* the default: the low five bits, so CTRL+A is 1 */
/* ...and the three characters that are NOT that, because ASCII puts them outside the control run:
 * CTRL+2 is NUL, CTRL+6 is RS and CTRL+- is US. The ROM tests the ASCII, not the scancode. */
#define ASCII_DIGIT_TWO          0x32
#define ASCII_DIGIT_SIX          0x36
#define ASCII_MINUS              0x2d
#define CONTROL_DIGIT_TWO        0x00
#define CONTROL_DIGIT_SIX        0x1e
#define CONTROL_MINUS            0x1f
#define ASCII_UPPER_FIRST        0x41   /* the ALT arm drops the ASCII of a letter key outright */
#define ASCII_UPPER_LAST         0x5a
#define ASCII_LOWER_FIRST        0x61
#define ASCII_LOWER_LAST         0x7a

/* ================================================================================================
 * BIOS Bconout ($fc099c) AND ITS SIX OUTPUT DRIVERS (BIOS wave 3)
 *
 * The fourth of the character-device entries, over the fourth table copied out of $fc09ae: the same
 * four instructions as Bconstat/Bconin/Bcostat, and a CHARACTER WORD at 6(sp) above the device word.
 * What makes it a wave of its own is what the drivers are — the two 6850 senders are Ikbdws' and
 * Midiws' own bodies, the printer's drives the YM2149's port B and times out on `_hz_200`, the
 * RS232's pushes a byte into an output ring and primes the MFP's USART, and CON: is the whole VT52
 * console (`src/bios/vt52.c`).
 * ============================================================================================= */
#define BIOS_BCONOUT_FN     3
#define BIOS_BCONOUT        0xfc099c
#define XCONOUT_TABLE       0x57e      /* the fourth of the four tables at $51e, $53e, $55e, $57e */
/* ...and the six drivers it reaches, as the captured machine's own table holds them. */
#define XCONOUT_PRT         0xfc2090   /* the parallel port, through the YM2149's port B */
#define XCONOUT_RS232       0xfc21b4   /* ...the RS232 output ring, then the MFP's USART */
#define XCONOUT_CON         0xfc42f2   /* ...the VT52 console: escapes, control codes and a glyph */
#define XCONOUT_MIDI        0xfc2016   /* ...`Midiws`' own single-byte sender ($fc201a) */
#define XCONOUT_IKBD        0xfc21ee   /* ...and `Ikbdws`' ($fc21f2), settling delay included */
#define XCONOUT_RAW         0xfc42e6   /* the RAW console: the glyph renderer with no state machine */

/* ---- the printer driver ($fc2090) ---------------------------------------------------------------
 * `btst #4,PRINTER_CONFIG` first: a machine configured for a SERIAL printer sends the byte down the
 * RS232 driver instead, which is a `bne` into `$fc21b4` and not a call. */
#define PRINTER_CONFIG_SERIAL_BIT 4
#define PRINTER_RETRY_AT    0xe84      /* long: `_hz_200` as it stood when the port last timed out */
/* Two spans in 200 Hz ticks, both a `cmpi.l` against a longword difference and NOT the same compare:
 * the hold-off — a port that timed out less than five seconds ago is not tried again — is `bcs`,
 * UNSIGNED, and the thirty seconds the driver waits for BUSY to clear is `blt`, SIGNED. */
#define PRINTER_RETRY_HOLDOFF_TICKS 1000
#define PRINTER_TIMEOUT_TICKS       6000
/* ...and the WAIT SITE that second span is measured at: `move.l _hz_200,d3`, the re-read the busy
 * loop makes once a pass. Nothing inside a differential run advances the 200 Hz tick — it is an
 * interrupt — so the loop is infinite on both shores until a case says what that interrupt did, and
 * this is the PC its schedule triggers on and the core names at every poll (`sched.h`; TRAP_MODEL.md,
 * Phase 8). It is the RE-READ and not the `cmpi.l` below it: the store lands just before the site's
 * own instruction. */
#define PRINTER_WAIT_SITE   0xfc20b4
#define PSG_PORT_B          15         /* the eight parallel data lines (`PSG_PORT_A` is above) */
#define PSG_PORT_B_OUTPUT   0x80       /* `ori.b #$80`: mixer bit 7 turns port B into an output */
/* The Centronics strobe is port A bit 5, driven LOW and then back HIGH through Offgibit's and
 * Ongibit's own bodies ($fc2f08 / $fc2ee2, entered below their argument fetch with the mask in D2).
 * The ROM asserts it TWICE — `bsr .low / bsr .low / bsr .high` — which is the pulse width. */
#define PRINTER_STROBE_SET_MASK   0x0020    /* `moveq #32,d2`  -> Ongibit */
#define PRINTER_STROBE_CLEAR_MASK 0xffdf    /* `moveq #-33,d2` -> Offgibit; only its low byte is used */
#define PRINTER_STROBE_ASSERTIONS 2         /* ...how many times the low half is called */
#define PRINTER_SENT        0xffffffffu     /* `moveq #-1,d0` — the byte reached the port */
#define PRINTER_TIMED_OUT   0u              /* `moveq #0,d0` — BUSY never cleared */

/* ---- the RS232 driver ($fc21b4) and the transmitter it primes ($fc2836) --------------------------
 * The three bytes above the two IOREC records that the flow-control half keeps, and the MFP
 * transmitter status the ROM saves a copy of. All four are displacements off `IOREC_RS232`, which is
 * how the ROM reaches them (`29(a0)`..`33(a0)`), spelt out because `tools/addrs.py` takes plain
 * integers only; `test_bios_bconout.py` asserts each sum rather than leaving two spellings to drift. */
#define RS232_TRANSMIT_STATUS   0xc71  /* byte: the TSR byte the transmitter last saw (= $c54 + 29) */
#define RS232_REMOTE_STOPPED    0xc73  /* byte: masked with the flow mode — nonzero means "hold off" */
#define RS232_PENDING_CHARACTER 0xc75  /* byte: an XON/XOFF to send ahead of the ring, then cleared */
#define MFP_TSR_BUFFER_EMPTY_BIT 7     /* `tst.b TSR / bpl`: set when the USART can take a byte */

/* ---- conterm's bell gate, which BEL ($fc2270) is the only reader of -----------------------------
 * Its siblings (bits 0, 1 and 3) are named with the keyboard and the VBL above. */
#define CONTERM_BELL_BIT    2
#define BELL_SOUND_LIST     0xfc31c2   /* the Dosound list ^G plants in `SOUND_LIST_POINTER` */

/* ================================================================================================
 * THE VT52 CONSOLE ($fc42f2) — its state block, its state machine and its four screen routines.
 *
 * Everything the driver keeps is a displacement off `CON_STATE_FLAGS` ($2994), which is the Line-A
 * block's own anchor and is already named above with Cursconf's three bytes and the VBL's cursor
 * blink. The driver reads NO hardware at all: the screen base is `_v_bas_ad` in RAM and the cell
 * geometry, the font and the four screen routines are all fields of this block.
 * ============================================================================================= */
#define CON_STATE_VECTOR    0x4a8      /* long: the ROM routine the NEXT character goes to */
#define CON_ESCAPE_Y_ROW    0x4ac      /* word: ESC Y's row, held while its column byte is awaited */
/* ...and the six states, which are ROM addresses because the vector is a jump target. The four that
 * are WAITING for an argument are named `AWAIT` rather than `ESCAPE` so that none of them reads like
 * `CON_ESCAPE_Y_ROW` above, which is the RAM word one of them fills in. */
#define CON_STATE_NORMAL            0xfc4308
#define CON_STATE_ESCAPE            0xfc4354
#define CON_STATE_AWAIT_Y_ROW       0xfc4378
#define CON_STATE_AWAIT_Y_COLUMN    0xfc4388
#define CON_STATE_AWAIT_FOREGROUND  0xfc43a4
#define CON_STATE_AWAIT_BACKGROUND  0xfc43b8
/* ...and the routines the VDI's escape reaches besides ESC's own bodies (`src/vdi/escape.S`'s thunks), each named for
 * the C body it ships as (`bios/vt52.h`, `console_<name>`). The character entry is `XCONOUT_CON` past its
 * `move.w 6(sp),d1` argument fetch: the escape enters with D1 already the word. */
#define CON_HIDE_CURSOR     0xfc45de   /* the cursor's lock, entered past `lea $2994,a4` (A4 already holds it) */
#define CON_UNLOCK_CURSOR   0xfc45ae
#define CON_SHOW_CURSOR     0xfc45be   /* ESC e */
#define CON_PLACE_CURSOR    0xfc49fc   /* D0 the column, D1 the row */
#define CON_OUTPUT          0xfc42f6

/* The cell geometry and the cursor, in the order the block holds them. `CON_CURSOR_DISABLE`,
 * `CON_CURSOR_ADDRESS`, `CON_CELL_HEIGHT`, `CON_PLANES`, `CON_LINE_BYTES`, `CON_BLINK_RATE` and
 * `CON_BLINK_TIMER` are named with the VBL's cursor blink above; these are the rest. */
#define CON_MAX_COLUMN      0x296e     /* word: the LAST column, not the count ($2994 - 38) */
#define CON_MAX_ROW         0x2970     /* word: ...and the last row */
#define CON_ROW_BYTES       0x2972     /* word: one text row = `CON_LINE_BYTES` * `CON_CELL_HEIGHT` */
#define CON_COLOUR_BACKGROUND 0x2974   /* word: one bit a plane, LSB first (ESC c sets it) */
#define CON_COLOUR_FOREGROUND 0x2976   /* word: ...and ESC b sets this one */
#define CON_CURSOR_OFFSET   0x297c     /* word: added to `_v_bas_ad` before the cell arithmetic */
#define CON_CURSOR_COLUMN   0x297e     /* word: where the cursor is */
#define CON_CURSOR_ROW      0x2980
#define CON_FONT_FORM       0x2984     /* long: the font's bitmap, one scan line every FORM_BYTES */
#define CON_FONT_LAST       0x2988     /* word: the last character code the font draws */
#define CON_FONT_FIRST      0x298a     /* word: ...and the first */
#define CON_FONT_FORM_BYTES 0x298c     /* word: the font bitmap's width, which is its row stride */
#define CON_FONT_OFFSETS    0x2990     /* long: one WORD per code — the glyph's BIT column in the form */
#define CON_SAVED_POSITION  0x284c     /* long: ESC j's column and row, as one longword ($2994 - 328) */
/* ...and the three flag bits past the two Cursconf names, as the ROM's own `bset`/`btst` name them. */
#define CON_FLAG_WRAP       3          /* ESC v / ESC w: does the last column wrap to the next row? */
#define CON_FLAG_REVERSE    4          /* ESC p / ESC q: swap the two colours for the next glyph */
#define CON_FLAG_POSITION_SAVED 5      /* ESC j has stored a position ESC k may go back to */

/* The four screen routines, as LONGWORDS OF RAM the driver jumps through. TOS 1.02 installs the
 * BLITTER variants ($fc47be, $fc4852, $fc48b6, $fc4936) on a machine that has one, so which set the
 * console uses is a fact about the captured machine and not about the ROM — a reconstruction reads
 * the vector and halts on a variant it does not reconstruct, exactly as the device tables above are
 * read rather than assumed. */
#define CON_VECTOR_GLYPH        0x2a14  /* ($2994 + 128) */
#define CON_VECTOR_SCROLL_UP    0x2a18
#define CON_VECTOR_SCROLL_DOWN  0x2a1c
#define CON_VECTOR_CLEAR        0x2a20
#define CONOUT_GLYPH_CPU        0xfd141c   /* ...and the CPU set the snapshot's machine holds */
#define CONOUT_SCROLL_UP_CPU    0xfd149a
#define CONOUT_SCROLL_DOWN_CPU  0xfd14de
#define CONOUT_CLEAR_CPU        0xfd1542
/* ...and the two tables the CPU clear routine indexes: eight two-word edge masks, and the THREE
 * fill arms `(planes >> 1) * 4` chooses between (one word a group, two, four). Six or more planes
 * index past the second, which is what makes it a halt rather than a fourth arm. */
#define CONOUT_CLEAR_MASKS      0xfd1522
#define CONOUT_CLEAR_PLANE_ARMS 3

/* The control codes the console acts on. Everything from $20 up is a glyph; of what is below, only
 * $07..$0d and ESC do anything, which is the `subq.w #7 / bmi / cmp.w #6 / bgt` gate. */
#define CON_FIRST_PRINTABLE 0x20
#define CON_BEL             0x07
#define CON_BS              0x08
#define CON_TAB             0x09
#define CON_LF              0x0a
#define CON_VT              0x0b       /* ...both of these do exactly what LF does */
#define CON_FF              0x0c
#define CON_CR              0x0d
#define CON_ESC             0x1b
#define CON_TAB_STOP_MASK   0xfff8u    /* `andi.w #-8,d0 / addq.w #8,d0` — the next multiple of 8 */
#define CON_TAB_WIDTH       8
/* ESC Y and the two colour escapes bias their argument byte by a space, which is how VT52 spells a
 * small number as a printable character. */
#define CON_ESCAPE_BIAS     0x20
/* ...and the three escape ranges the ROM implements, as its own three-stage compare names them:
 * `ESC A`..`ESC M`, `ESC Y`, and `ESC b`..`ESC w`. Anything else returns to the normal state and
 * does nothing. */
#define CON_ESCAPE_UPPER_FIRST 0x41    /* 'A' — spelt as the code, because tools/addrs.py, which */
#define CON_ESCAPE_UPPER_LAST  0x4d    /* 'M'   binds this header for the cases, reads integers    */
#define CON_ESCAPE_POSITION    0x59    /* 'Y'   only and would silently skip a character literal   */
#define CON_ESCAPE_LOWER_FIRST 0x62    /* 'b' */
#define CON_ESCAPE_LOWER_LAST  0x77    /* 'w' */
/* ...and the two ranges' jump tables: WORD offsets from the table's own address, one a letter. The VDI's
 * escape (opcode 5, `VDI_ESCAPE_TABLE`) indexes into the same bodies (`test_vdi_escape.py` holds it to them). */
#define CON_ESCAPE_UPPER_TABLE 0xfc43e8  /* `A`..`M`                        ($fc43d6)           */
#define CON_ESCAPE_LOWER_TABLE 0xfc4402  /* `b`..`w`                        ($fc43e0)           */

/* ---- GEMDOS ($fc4f6e trap entry, $fc94e4 dispatcher, the RAM-only leaves) ------------------------
 *
 * Added by the GEMDOS trap/dispatcher wave (src/gemdos/trap1.S, dispatch.c, leaves.c). GEMDOS is the
 * third trap entry and the only one that is not a bare table dispatch: the entry serves `Super`
 * itself, builds the calling process's register frame in ITS OWN BASEPAGE, moves the stack to the
 * OS's supervisor stack and then calls a C dispatcher that indexes a table of SIX-BYTE records.
 */
#define GEMDOS_TRAP1          0xfc4f6e  /* vector $84 — the entry, and `Super`'s three arms with it */
#define GEMDOS_TRAP1_FRAME    0xfc4f8a  /* ...where a call that is NOT `Super` starts framing */
#define GEMDOS_SUPER_FROM_USER 0xfc501c /* `Super` as a user-mode caller reaches it */
#define GEMDOS_SUPER_FROM_SUPERVISOR 0xfc503a
#define GEMDOS_SUPER_QUERY    0xfc506a  /* ...and the `Super(1)` arm both of them share */
#define GEMDOS_SUPER_LEAVE_SUPERVISOR 0xfc5068  /* the `rte` that drops a supervisor caller to user */
#define GEMDOS_ENTRY_C        0xfc5078  /* the OS's own C-callable GEMDOS entry ($fc9886 uses it) */
#define GEMDOS_TRAP1_END      0xfc5092  /* one past the last byte src/gemdos/trap1.S transcribes */
#define GEMDOS_DISPATCH       0xfc94e4  /* the C dispatcher the entry calls, with the frame pointer */
#define GEMDOS_DISPATCH_SELECTOR 0xfc973e  /* ...and where it dispatches, PAST the `setjmp` */
#define GEMDOS_FREE_DND_TREE  0xfc93f4  /* the media-change recovery: a DND tree back to the pool */
#define GEMDOS_FREE_DRIVE_OFDS 0xfc9468 /* ...and the open files on the drive in the caller's A4 */
/* The dispatcher's own frame: `link a6,#-54`, and the ONE local a case entering the slice above has
 * to stand in for — the selector, which the prologue read out of the argument list before the
 * `setjmp` and every arm past it reads back from here. (The argument POINTER is at `8(a6)`, which
 * is where an ordinary `jsr` frame already puts it.) */
#define GEMDOS_DISPATCH_FRAME_BYTES 54
#define GEMDOS_DISPATCH_SELECTOR_LOCAL 0xffde
/* ...and the byte a REDIRECTED read `Fread`s into, `-14(a6)` ($fc97b6), which the case staging a stale
 * one has to find in the ROM's frame (the reconstruction's is `HOST_SLOT_REDIRECTED_BYTE`). */
#define GEMDOS_DISPATCH_REDIRECTED_BYTE_LOCAL (-14)
#define GEMDOS_SETJMP         0xfc4f38  /* the three-longword frame record the dispatcher arms */
#define GEMDOS_TERMINATION_JMPBUF 0x7ef4   /* ...and where it writes it */
#define GEMDOS_CALL_DEPTH     0x68fa    /* word: cleared then bumped on every trap #1 ($fc94e8) */

/* The trap entry's own geometry. The register frame it builds runs UNDER the caller's own words —
 * the other stack pointer, the SR, the return PC and then ten registers — so its length is also the
 * displacement from the frame's base back up to the argument words. */
#define GEMDOS_SUPERVISOR_STACK 0x16ce  /* where the entry parks A7 before calling the dispatcher */
#define GEMDOS_SAVED_FRAME_BYTES 50     /* `lea 50(a5),a0`: 4 + 2 + 4 + 10 * 4 */
/* One register of the ten, `movem.l d1-a2`: a longword each, D1 first — the other stack pointer (4), the
 * SR (2) and the PC (4) are under them. D5 is the fifth, which `Pexec`'s loader reads its `Fopen` mode out
 * of (`include/gemdos/pexec_load.h`); `test_gemdos_trap1.py` reads each slot back out of a frame the ROM's
 * own entry built. */
#define GEMDOS_SAVED_REGISTER_BYTES 4
#define GEMDOS_SAVED_FRAME_D5 26        /* 4 + 2 + 4 + 4 * 4: past D1..D4 */
/* Where the ARGUMENTS are, measured from three different places, which is why there are three
 * names: from the argument list itself (the function number is the first word), from a supervisor
 * caller's stack pointer inside the entry (the exception frame is still on it), and from the
 * C entry's own frame pointer (the saved A6 and the return address are under them). */
#define GEMDOS_ARGUMENT_WORD  2
#define GEMDOS_SUPERVISOR_ARGUMENT 8    /* EXCEPTION_FRAME_BYTES + GEMDOS_ARGUMENT_WORD */
#define GEMDOS_C_ARGUMENTS    8         /* `lea 8(a6),a0` at $fc507e */
#define GEMDOS_SAVED_REGISTERS 10       /* d1-d7/a0-a2 — and note D0/A3-A6 go in the BASEPAGE */
#define SR_SUPERVISOR         0x2000    /* the S bit as a whole word, which `Super` sets and clears */
#define SR_USER_MASK          0xdfff    /* ...and `andi.w #$dfff,(sp)`, which is how it clears it */
#define SR_SUPERVISOR_HIGH_BYTE_BIT 5   /* `btst #5,(sp)`: bit 13 of the SR is bit 5 of its high byte */

/* The BASEPAGE, as the ROM's own instructions index it. The first twelve longwords are the published
 * layout; everything from $30 up is what GEMDOS keeps there about the running process, and the three
 * save slots are the trap entry's — it has nowhere else to put D0/A3-A6 before it has a stack. */
#define GEMDOS_P_RUN          0x87ce    /* long: -> the current process's basepage (OS header +$28) */
/* The published twelve, as `Pexec` fills them ($fc8370 onwards) and the loader and the child's own
 * startup read them. `p_tbase` is also where the basepage CLEAR starts — 256 bytes from +8, which
 * runs eight bytes past the basepage's own end. */
#define BASEPAGE_LOWTPA       0x00      /* long: the basepage itself */
#define BASEPAGE_HITPA        0x04      /* long: ...+ the TPA's length; the child's stack top */
#define BASEPAGE_TBASE        0x08      /* long: the entry point Pexec pushes for the child */
#define BASEPAGE_TLEN         0x0c
#define BASEPAGE_DBASE        0x10      /* long: ...which the child is handed in A5 */
#define BASEPAGE_DLEN         0x14
#define BASEPAGE_BBASE        0x18      /* long: ...and this one in A4 */
#define BASEPAGE_BLEN         0x1c
#define BASEPAGE_DTA          0x20      /* long: Fgetdta/Fsetdta, and the whole of both routines */
#define BASEPAGE_PARENT       0x24      /* long: p_parent — `Pterm` $fc805a reassigns p_run from it */
#define BASEPAGE_ENV          0x2c      /* long: p_env, the block `Pexec` cuts and copies */
#define BASEPAGE_HANDLES      0x30      /* 6 bytes: p_uft, the standard handles 0..5 that */
                                        /*    `Fforce` ($fc52de, its entry) stores into */
#define BASEPAGE_STANDARD_HANDLES 6
#define BASEPAGE_LDDRV        0x36      /* byte */
#define BASEPAGE_CURDRV       0x37      /* byte: Dgetdrv reports it, Dsetdrv stores it */
/* 16 bytes: p_curdir, one DIRECTORY NODE per drive. Each byte indexes `GEMDOS_CURDIR_REFCOUNTS`,
 * which `Pexec` bumps ($fc51de) and a process's release drops ($fc80ea). */
#define BASEPAGE_CURDIR       0x40
#define BASEPAGE_CURDIR_ENTRIES 16
/* 128 bytes: the COMMAND TAIL, a length byte and up to 125 characters — and the default DTA, which
 * `Pexec` points at this same address ($fc83b2). */
#define BASEPAGE_COMMAND_TAIL 0x80
#define BASEPAGE_SAVED_D0     0x68      /* long: D0, then A3, A4, A5 — the trap entry's save area */
#define BASEPAGE_SAVED_A3     0x6c
#define BASEPAGE_SAVED_A4     0x70      /* ...which `Pexec` seeds with p_bbase, so a child starts */
#define BASEPAGE_SAVED_A5     0x74      /*    with A4 = BSS and A5 = DATA ($fc85a4/$fc85b2) */
#define BASEPAGE_SAVED_A6     0x78      /* long: ...A6, which it had to push to free a base register */
#define BASEPAGE_SAVED_FRAME  0x7c      /* long: -> the register frame on the caller's own stack */
#define BASEPAGE_SAVED_REGISTERS 5      /* d0/a3-a6, as the returning `movem.l $68(a5)` reads them */

/* The dispatch TABLE: 88 six-byte records, a handler longword and an ARGUMENT-DESCRIPTOR word. */
#define GEMDOS_FUNCTION_TABLE 0xfd307a
#define GEMDOS_FUNCTION_COUNT 88
#define GEMDOS_MAX_SELECTOR   0x57      /* `cmpi.w #87` — above it, no record is read at all */
#define GEMDOS_RECORD_BYTES   6
#define GEMDOS_RECORD_DESCRIPTOR 4      /* the word the dispatcher reads at $fc9754 */
#define GEMDOS_EINVFN         0xffffffe0u   /* -32, what a selector past the table answers */
#define GEMDOS_EIHNDL         0xffffffdbu   /* -37, what an unresolvable handle answers */

/* The DESCRIPTOR word. Its low two bits are the ARGUMENT-FRAME CLASS — how many bytes of the
 * caller's words the dispatcher copies onto the stack before `jsr` — and bit 7 marks a call whose
 * argument is a HANDLE, so that a standard handle Fforce redirected reaches the file system and a
 * character device reaches the device driver. The low seven bits of such a descriptor are the
 * STANDARD HANDLE the redirection consults ($80 -> 0 stdin, $81 -> 1 stdout, $82 -> 2 stdaux,
 * $83 -> 3 stdprn). */
#define GEMDOS_DESC_HANDLE    0x80      /* `btst #7,<descriptor low byte>` at $fc991a */
/* ...and the ONE descriptor whose handle is not the first argument word: $81 is `Fseek`, whose
 * first argument is a longword offset, so its handle is the THIRD word (`cmpi.w #129` at $fc9924).
 * `Fread` and `Fwrite` are $82 and take theirs first. */
#define GEMDOS_DESC_HANDLE_AT_THIRD_WORD 0x81
#define GEMDOS_ARGUMENT_THIRD_WORD 6
#define GEMDOS_DESC_ARGUMENT_MASK 0x7f  /* `andi.w #127` at $fc9ba8 — what is left is 0..3 */
#define GEMDOS_ARGUMENT_CLASSES 4
/* ...and the four frames themselves, in bytes, as the four arms at $fc9bb6/$fc9bd8/$fc9c0a/$fc9c4e
 * push them. They are not 4/8/12/16: the widest is Pexec's word-plus-three-longwords. */
#define GEMDOS_ARGUMENT_BYTES_0 4
#define GEMDOS_ARGUMENT_BYTES_1 8
#define GEMDOS_ARGUMENT_BYTES_2 12
#define GEMDOS_ARGUMENT_BYTES_3 14

/* WHICH SELECTORS the standard-handle redirection applies to: the character-device group, in the two
 * runs the ROM's own four compares carve out ($fc9762..$fc9784). Everything else — Fread and Fwrite
 * included, which carry a $82 descriptor of their own — skips straight to the descriptor's bit 7. */
#define GEMDOS_REDIRECT_FIRST 1         /* Cconin .. Cconis */
#define GEMDOS_REDIRECT_LAST  11
#define GEMDOS_REDIRECT_SECOND_FIRST 16 /* Cconos, Cprnos, Cauxis, Cauxos */
#define GEMDOS_REDIRECT_SECOND_LAST  19
#define GEMDOS_REDIRECT_TABLE 0xfd328a  /* 19 longwords, indexed by selector - 1 ($fc98f4) */
/* ...and what the descriptor is REWRITTEN to when the standard handle is still a character device:
 * one pointer argument for the two console calls that take a string, and none for the rest. */
#define GEMDOS_CCONWS_FN      0x09
#define GEMDOS_CCONRS_FN      0x0a
/* ...and what a status call answers once its standard handle is a FILE: always ready, whichever of
 * the five it is (`move.l #255,d0` at $fc98dc). */
#define GEMDOS_REDIRECTED_READY 0xff

/* The HANDLE RECORDS $8092 holds — ten bytes each, whose own first longword POINTS at the 64-byte
 * open file descriptor the file system keeps (or, negative, names a character device). Named because
 * the dispatcher indexes them; `src/gemdos/handles.c` walks them, and nothing here follows that
 * pointer. NOT the OFD itself, which is `include/gemdos/fs.h`'s and keeps the `OFD_` prefix. */
#define GEMDOS_HANDLE_TABLE   0x8092    /* handle 6.. -> (handle - 6) * 10 + here ($fc9950) */
#define GEMDOS_HANDLE_STRIDE  10
#define GEMDOS_FIRST_FILE_HANDLE 6
/* CORRECTED BY THE PROCESS WAVE, and the correction is what this group's own routines pin: $8066 is
 * not indexed by a process at all. `gemdos_inherit_curdir` ($fc51de) bumps `$8066[node]` and
 * `gemdos_release_process` ($fc80ea) drops it, in both cases with `node` read out of a basepage's
 * `p_curdir` — so it is one REFERENCE COUNT PER DIRECTORY NODE, and $7dee is the node table those
 * counts are about. See `src/gemdos/process.c`.
 *
 * THREE CONSTANTS WAVE 7 PUT HERE HAVE BEEN DELETED, all three read off a "process table" that is
 * not one and none of them with a user in any core or case: `GEMDOS_PROCESS_ID` ($87cc, which is
 * really `GEMDOS_DISK_ERROR_DRIVE` — the file-system wave found the ROM storing a DRIVE there),
 * `GEMDOS_PROCESS_TABLE` ($8380, the per-drive DMD table) and `GEMDOS_PROCESS_OWNERS` ($7dee, the
 * DIRECTORY NODE table). The latter two are named in `../names.txt` (`gemdos_dmd_table`,
 * `gemdos_directory_nodes`) and came back in fs wave 3, when `$fc67de` became the first core to read
 * them (`GEMDOS_DMD_TABLE`, `GEMDOS_DIRECTORY_NODES`, with the file system's RAM below); `test/test_addrs.py`
 * now refuses a second name for one address, which is what $87cc had. */
#define GEMDOS_CURDIR_REFCOUNTS 0x8066  /* one byte per directory node: how many basepages hold it */

/* The RAM-ONLY LEAVES this wave reconstructs, and the two words two of them are the whole of. */
#define GEMDOS_DATE           0x8840    /* word: the DOS date, seeded from os_dosdate at $fc0460 */
#define GEMDOS_TIME           0x75b0    /* word: the DOS time */
#define GEMDOS_MONTH_LENGTHS  0xfd3060  /* 13 words: Tsetdate's day bound, indexed by month */
#define GEMDOS_PUBLISH_CLOCK  0xfc50b4  /* the XBIOS `Settime(date, time)` both setters end with */
#define XBIOS_SETTIME_FN      22        /* ...and the function number it pushes before `trap #14` */
#define GEMDOS_RANGE_ERROR    0xffffffffu   /* -1, what both setters answer a word out of range */
#define GEMDOS_BIOS_TRAMPOLINE 0xfc4eac /* `move.l (sp)+,$eb0 / trap #13 / move.l $eb0,-(sp) / rts` */
#define GEMDOS_BIOS_RETURN_SLOT 0xeb0   /* ...and the longword it parks the return address in */

#define GEMDOS_UNIMPLEMENTED  0xfc933e  /* every undefined selector's handler: `moveq #-32,d0` */
#define GEMDOS_DSETDRV        0xfc6cc0
#define GEMDOS_FSETDTA        0xfc6cac
#define GEMDOS_DGETDRV        0xfc6ce0
#define GEMDOS_TGETDATE       0xfc9e1a
#define GEMDOS_TSETDATE       0xfc9e2a
#define GEMDOS_TGETTIME       0xfc9ea2
#define GEMDOS_TSETTIME       0xfc9eb2
/* ...and the instruction in each setter that every refusal branches PAST: the store of the word it
 * has just accepted. A case that can only read the accepting arm as a slice stops here. */
#define GEMDOS_TSETDATE_STORE 0xfc9e8a
#define GEMDOS_TSETTIME_STORE 0xfc9ef4
#define GEMDOS_FGETDTA        0xfc6c9a
#define GEMDOS_SVERSION       0xfc9348

/* The selectors the cases drive, by number. The table above is indexed by these, so a case naming a
 * handler and a case naming a selector cannot drift apart. */
#define GEMDOS_DSETDRV_FN     0x0e
#define GEMDOS_UNDEFINED_FN   0x0c      /* the lowest selector the ABI leaves undefined */
#define GEMDOS_FSETDTA_FN     0x1a
#define GEMDOS_DGETDRV_FN     0x19
#define GEMDOS_SUPER_FN       0x20
#define GEMDOS_TGETDATE_FN    0x2a
#define GEMDOS_TSETDATE_FN    0x2b
#define GEMDOS_TGETTIME_FN    0x2c
#define GEMDOS_TSETTIME_FN    0x2d
#define GEMDOS_FGETDTA_FN     0x2f
#define GEMDOS_SVERSION_FN    0x30
#define GEMDOS_FCREATE_FN     0x3c      /* ...the two selectors whose FILENAME the dispatcher itself */
#define GEMDOS_FOPEN_FN       0x3d      /*    compares against the six device names at $fd32d6 */
#define GEMDOS_FREAD_FN       0x3f
#define GEMDOS_FWRITE_FN      0x40
#define GEMDOS_FSEEK_FN       0x42
#define GEMDOS_PEXEC_FN       0x4b
#define GEMDOS_DFREE_FN       0x36
#define GEMDOS_DGETPATH_FN    0x47
#define GEMDOS_FSNEXT_FN      0x4f
#define GEMDOS_FDATIME_FN     0x57
#define GEMDOS_DCREATE_FN     0x39
#define GEMDOS_DDELETE_FN     0x3a
#define GEMDOS_DSETPATH_FN    0x3b
#define GEMDOS_FDELETE_FN     0x41
#define GEMDOS_FATTRIB_FN     0x43
#define GEMDOS_FSFIRST_FN     0x4e
#define GEMDOS_FRENAME_FN     0x56

/* Sversion's answer, and the DOS date/time fields Tsetdate and Tsettime bound. The date word is
 * `(year - 1980) << 9 | month << 5 | day` and the time word `hour << 11 | minute << 5 | second / 2`,
 * and the ROM bounds each field with its own compare rather than with a mask. */
#define GEMDOS_VERSION        0x1300
#define GEMDOS_DATE_YEAR_SHIFT 9
#define GEMDOS_DATE_MONTH_SHIFT 5
#define GEMDOS_DATE_DAY_MASK  0x1f
#define GEMDOS_DATE_MONTH_MASK 0x0f     /* `asr.w #5 / andi.w #15` — FOUR bits, not the field's own */
#define GEMDOS_DATE_MAX_YEAR  119       /* 1980 + 119 = 2099 */
#define GEMDOS_DATE_MAX_MONTH 12
#define GEMDOS_DATE_FEBRUARY  2
#define GEMDOS_DATE_LEAP_MASK 0x0600    /* the two year bits a leap year clears (year % 4) */
#define GEMDOS_DATE_LEAP_DAYS 29
#define GEMDOS_TIME_SECOND_MASK 0x1f
#define GEMDOS_TIME_MAX_SECOND 30       /* `cmp.w #30 / blt` on the two-second field */
#define GEMDOS_TIME_SECOND_SHIFT 0     /* ...in TWO-second units, which is the `asr.w #1` */
#define GEMDOS_TIME_MINUTE_SHIFT 5
#define GEMDOS_TIME_HOUR_SHIFT 11
#define GEMDOS_TIME_MINUTE_MASK 0x07e0
#define GEMDOS_TIME_MAX_MINUTE 0x0780   /* 60 << 5, compared without shifting the field down */
#define GEMDOS_TIME_HOUR_MASK 0xf800
#define GEMDOS_TIME_MAX_HOUR  0xc000    /* 24 << 11, as a SIGNED longword compare ($fc9ee6) */

/* ---- the GEMDOS CHARACTER DEVICES (selectors $01..$0b and $10..$13) -----------------------------
 *
 * `src/gemdos/console.c`. Fifteen leaves over one small layer: each reads a STANDARD HANDLE out of
 * the running process's basepage, turns it into a BIOS device number by ADDING THREE (-1/-2/-3, the
 * three standard handle values, become CON:/AUX:/PRT: = 2/1/0) and then reaches the BIOS through the
 * trampoline at `GEMDOS_BIOS_TRAMPOLINE`. What sits between the leaves and the BIOS is GEMDOS's own
 * console state: a TYPEAHEAD queue, a per-device COLUMN counter, TAB expansion, the `^X` echo and
 * the `Cconrs` line editor.
 *
 * THE STATE IS SIZED FOR EXACTLY THREE DEVICES, and `GEMDOS_CONSOLE_INIT` says so in straight-line
 * code: it writes p_uft[0..3] = -1,-1,-2,-3 and then initialises three typeahead counts, three read
 * pointers and three write pointers, one instruction each. So a standard handle outside -3..-1
 * indexes off every one of these tables — see `src/gemdos/console.c` for the three facts that make
 * refusing it right (the dispatcher redirects every handle above 0, `Fforce` refuses 0..5, and what
 * is left is any NEGATIVE byte a program stores). */
#define GEMDOS_CCONIN         0xfc8ff2
#define GEMDOS_CCONIN_FN      0x01
#define GEMDOS_CCONOUT        0xfc8e1c
#define GEMDOS_CCONOUT_FN     0x02
#define GEMDOS_CAUXIN         0xfc903e
#define GEMDOS_CAUXIN_FN      0x03
#define GEMDOS_CAUXOUT        0xfc8ed2
#define GEMDOS_CAUXOUT_FN     0x04
#define GEMDOS_CPRNOUT        0xfc8efa
#define GEMDOS_CPRNOUT_FN     0x05
#define GEMDOS_CRAWIO         0xfc9062
#define GEMDOS_CRAWIO_FN      0x06
#define GEMDOS_CRAWCIN        0xfc8faa
#define GEMDOS_CRAWCIN_FN     0x07
#define GEMDOS_CNECIN         0xfc900c
#define GEMDOS_CNECIN_FN      0x08
#define GEMDOS_CCONWS         0xfc90c2      /* ...and GEMDOS_CCONWS_FN is above, with the table */
#define GEMDOS_CCONRS         0xfc91ea
#define GEMDOS_CCONIS         0xfc8b70
#define GEMDOS_CCONIS_FN      0x0b
#define GEMDOS_CCONOS         0xfc8b8a
#define GEMDOS_CCONOS_FN      0x10
#define GEMDOS_CPRNOS         0xfc8bae
#define GEMDOS_CPRNOS_FN      0x11
#define GEMDOS_CAUXIS         0xfc8bd2
#define GEMDOS_CAUXIS_FN      0x12
#define GEMDOS_CAUXOS         0xfc8bee
#define GEMDOS_CAUXOS_FN      0x13

/* The layer under them. None is a dispatch-table entry — each is a `bsr` from the leaf above it —
 * so they are named here for the cases and the name map rather than for a function number. */
#define GEMDOS_DEVICE_INPUT_STATUS 0xfc8b44 /* typeahead pending, else `Bconstat` */
#define GEMDOS_TYPEAHEAD_DRAIN  0xfc8c12    /* the poll every output makes FIRST: ^S/^Q/^C/^X */
#define GEMDOS_TYPEAHEAD_RESET  0xfc8d4e    /* count := 0 and both pointers back to the buffer */
#define GEMDOS_DEVICE_PUT       0xfc8d96    /* drain, `Bconout`, then track the column */
#define GEMDOS_DEVICE_PUT_TAB   0xfc8e3c    /* ...with TAB expanded to the next multiple of 8 */
#define GEMDOS_DEVICE_PUT_ECHO  0xfc8e88    /* ...and with a control code echoed as `^` + letter */
#define GEMDOS_DEVICE_GET       0xfc8f22    /* the typeahead queue if it has a record, else `Bconin` */
#define GEMDOS_DEVICE_GET_ECHOING 0xfc8fc6  /* ...and the same read echoed back RAW (`Cconin`) */
#define GEMDOS_DEVICE_PUT_STRING 0xfc90e2   /* `Cconws`' loop, one sign-extended byte at a time */
#define GEMDOS_DEVICE_NEW_LINE  0xfc910c    /* CR, LF, then N spaces — `Cconrs`' ^U and ^R redraw */
#define GEMDOS_DEVICE_ERASE     0xfc9152    /* one character rubbed out: BS, space, BS to a column */
#define GEMDOS_DEVICE_READ_LINE 0xfc9226    /* the line editor itself */
#define GEMDOS_CONSOLE_INIT     0xfc9356    /* what sizes all of the above at three devices */

/* WHICH standard handle each leaf reads, as the index into `BASEPAGE_HANDLES` the ROM's own
 * displacement names, and what turns one into a BIOS device number. */
#define GEMDOS_STDIN          0
#define GEMDOS_STDOUT         1
#define GEMDOS_STDAUX         2
#define GEMDOS_STDPRN         3
#define GEMDOS_HANDLE_TO_DEVICE 3       /* `addq.w #3,(sp)` on the sign-extended handle byte */
#define GEMDOS_CON_HANDLE     (-1)      /* CON:'s handle, AUX: and PRN: counting down from it */
#define GEMDOS_CONSOLE_DEVICE 2         /* ...which makes CON:'s -1 this (`cmpi.w #2` at $fc9a5e) */
#define GEMDOS_CONSOLE_DEVICES 3        /* ...and how many devices the state below is sized for */

/* The six device NAMES the dispatcher compares an `Fopen`/`Fcreate` filename against ($fc9aca..$fc9b96):
 * "CON:", "con:", "AUX:", "aux:", "PRN:", "prn:", each with its NUL, five bytes at a time through
 * `$fc7e94` — so a name matches only WHOLE, and only in one of the two cases spelt. A match is answered
 * with the device's handle as an unsigned WORD, CON: first and the other two counting down from it:
 * $0000ffff, $0000fffe, $0000fffd. */
#define GEMDOS_DEVICE_NAMES   0xfd32d6
#define GEMDOS_DEVICE_NAME_BYTES 5
#define GEMDOS_DEVICE_NAME_SPELLINGS 2  /* upper case, then lower */
#define GEMDOS_DEVICE_NAME_COUNT 3

/* GEMDOS's own console state, all of it indexed by that device number. */
#define GEMDOS_DEVICE_COLUMN  0x68f4    /* word[3]: which column the device's cursor is in */
#define GEMDOS_DEVICE_COLUMN_BYTES 2
#define GEMDOS_TYPEAHEAD_COUNT 0x756c   /* byte[3]: records queued ahead of the reader */
#define GEMDOS_TYPEAHEAD_COUNT_BYTES 1
#define GEMDOS_TYPEAHEAD_READ 0x8830    /* long[3]: where the next record comes OUT */
#define GEMDOS_TYPEAHEAD_WRITE 0x8896   /* long[3]: ...and where the next one goes IN */
#define GEMDOS_TYPEAHEAD_POINTER_BYTES 4
#define GEMDOS_TYPEAHEAD_BUFFER 0x83c0  /* the three queues themselves, one after another */
#define GEMDOS_TYPEAHEAD_BUFFER_BYTES 320
#define GEMDOS_TYPEAHEAD_RECORD_BYTES 4 /* one whole `Bconin` longword, scancode half included */
#define GEMDOS_TYPEAHEAD_MAX  80        /* `cmpi.b #80` — a SIGNED byte compare on the count */
#define GEMDOS_TYPEAHEAD_READY 0xffffffffu  /* `moveq #-1`: Cconis' answer when a record is queued */

/* `Cconrs`' buffer, which is a length-prefixed line: the caller's maximum, the length GEMDOS writes
 * back, and then the characters. The maximum is read as an UNSIGNED byte (`ext.w` then `andi.w
 * #255`) while the length written back is a plain `move.b`. */
#define GEMDOS_CCONRS_MAX     0
#define GEMDOS_CCONRS_LENGTH  1
#define GEMDOS_CCONRS_TEXT    2

/* The line editor's KEY SET, as the ROM's own two tables hold it: nine longwords compared with
 * `cmp.l (a0)+` under a `dbeq`, and nine arm addresses 32 bytes past where that search stops. The
 * ninth key is 0 and its arm is the DEFAULT arm, which is what makes "no match" and "matched the
 * ninth" the same branch. */
#define GEMDOS_LINE_EDITOR_KEYS 0xfd3018
#define GEMDOS_LINE_EDITOR_ARMS 0xfd303c
#define GEMDOS_LINE_EDITOR_KEY_COUNT 9

/* ...and the codes themselves, by their ASCII names. `CON_BS`, `CON_TAB`, `CON_LF` and `CON_CR` are
 * named with the VT52 console above; these are the rest of what this layer tests for. */
#define CON_ETX               0x03      /* ^C — ends the process through `GEMDOS_PTERM` */
#define CON_DC1               0x11      /* ^Q — resume output */
#define CON_DC2               0x12      /* ^R — retype the line */
#define CON_DC3               0x13      /* ^S — hold output: read on, blocking, until ^Q */
#define CON_NAK               0x15      /* ^U — kill the line */
#define CON_CAN               0x18      /* ^X — kill the line by rubbing it out */
#define CON_DEL               0x7f      /* ...and DEL, which is BS */
#define CON_SPACE             0x20
#define CON_HASH              0x23      /* what ^U and ^R print before redrawing */
#define CON_CARET             0x5e      /* ...and the `^` a control code is echoed as */
#define CON_CONTROL_LETTER    0x40      /* `or.w #64`: ^A echoes as '^' then 'A' */
#define CON_CONTROL_WIDTH     2         /* ...so a control code occupies two columns */
#define CON_TAB_PHASE_MASK    0x0007    /* `and.w #7`: the tab loop ends when the column is a stop */
#define GEMDOS_CTRLC_STATUS   0xffe0    /* `Pterm(-32)`, the word both ^C arms push */
#define GEMDOS_CRAWIO_READ    0x00ff    /* `Crawio`'s whole argument WORD, not just its low byte */

/* ---- the GEMDOS MEMORY MANAGER (selectors $48..$4a, and the five routines under them) -----------
 *
 * `src/gemdos/memory.c`; the STRUCTURES it reads — the MPB, the descriptors and the record pool —
 * are `include/gemdos/memory.h`'s. The addresses are here because this header is the one the
 * registries key on: `test_boot_snapshot.py` pairs every `<NAME>`/`<NAME>_FN` it finds against the
 * ROM's own dispatch table, and `bench/tier3.py` names a row by the same pair. A routine whose
 * address lived anywhere else would be a row nothing could label and an entry nothing could pin. */
#define GEMDOS_MALLOC         0xfc8aae
#define GEMDOS_MALLOC_FN      0x48
#define GEMDOS_MFREE          0xfc8afc
#define GEMDOS_MFREE_FN       0x49
#define GEMDOS_MSHRINK        0xfc895a
#define GEMDOS_MSHRINK_FN     0x4a
/* ...and the five with no function number at all: GEMDOS's own C calls them by name, so nothing
 * dispatches them and `bench/tier3.py` labels them by what they are instead. */
#define GEMDOS_MD_ALLOC       0xfc886a  /* the next-fit search, the split and the two lists */
#define GEMDOS_MD_FREE_INSERT 0xfc89dc  /* ...and the sorted insert with its two coalescing merges */
#define GEMDOS_POOL_ARENA_ALLOC 0xfc7ed0 /* the bump arena the descriptors themselves come out of */
#define GEMDOS_POOL_GET       0xfc7f1a  /* one ZEROED record of a size class, chain or arena */
#define GEMDOS_POOL_FREE      0xfc7f9c  /* ...and back onto the chain its header word names */

/* ---- the GEMDOS FILE SYSTEM ($fc5216..$fc7cce) --------------------------------------------------
 *
 * `src/gemdos/fs_disk.c` (the buffer cache over BIOS `Rwabs`) and `src/gemdos/fs_name.c` (the 8.3
 * name layer, which touches no disk at all); the STRUCTURES they read — the BPB, the drive media
 * descriptor, the buffer control block, the directory node and the open-file descriptor — are
 * `include/gemdos/fs.h`'s, by the wave's one-header-per-subsystem rule. The addresses are here for
 * `include/gemdos/memory.h`'s reason: this header is the one the registries key on.
 *
 * None of these carries a `_FN`: GEMDOS's own C calls them by name, so nothing dispatches them. */
#define GEMDOS_FS_LOG2        0xfc539a  /* `asr` until the word is 0, minus 1 — log2 of a power of 2 */
#define GEMDOS_FS_TOUPPER     0xfc50ca  /* 'a'..'z' -> `& 0x5f`, everything else through unchanged */
#define GEMDOS_CLUSTER_RECORD 0xfc55e6  /* cluster * `m_clsiz` — the pseudo-record a cluster starts at */
#define GEMDOS_BUFFER_FLUSH   0xfc590a  /* one dirty BCB back to the disk (a FAT buffer goes twice) */
#define GEMDOS_RWABS_DATA     0xfc59f2  /* a span of DATA records straight to `Rwabs`, cache flushed */
#define GEMDOS_BUFFER_GET     0xfc5a98  /* THE buffer cache: hit, media change, LRU evict, re-read */
#define GEMDOS_NAME_MATCH     0xfc5c9a  /* one 11-byte FCB pattern against one directory entry */
#define GEMDOS_BUILD_FCB_NAME 0xfc5d28  /* "name.ext" -> the 11-byte padded FCB form, `*` expanded */
/* fs wave 3: the shared byte copies (`src/gemdos/fs_copy.c`) — one loop, three argument orders. */
#define GEMDOS_COPY_OUT       0xfc55fa  /* (n, src, dst): the transfer engine's READ copy ($fc5ec4) */
#define GEMDOS_COPY_IN        0xfc5622  /* (n, dst, src): ...and its WRITE copy ($fc5f20) */
#define GEMDOS_BCOPY          0xfc564a  /* (n, src, dst): byte-identical to $fc55fa, called by name */
#define OS_SWAP_WORD          0xfc4f10  /* the word at the argument, its bytes exchanged in place */
#define OS_SWAP_LONG          0xfc4f22  /* ...and the long, all four bytes reversed */
/* fs wave 3: the I/O engine (`src/gemdos/fs_io.c`) — seek, the FAT as a pseudo-file, the transfer. */
#define GEMDOS_SPLIT_SHIFT    0xfc7e24  /* *rem = value & mask[shift] (word), value >> shift (asr) */
#define GEMDOS_OFD_ADVANCE    0xfc61d6  /* position += n, opt. in-cluster offset, length grown */
#define GEMDOS_OFD_SEEK       0xfc7d2a  /* the cursor to a position: ERANGE, -1, or the position */
#define GEMDOS_FAT_GET        0xfc6038  /* a cluster's FAT entry; negative cluster -> cl + 1 */
#define GEMDOS_FAT_SET        0xfc5f44  /* ...stored: FAT16 a word, FAT12 read-modify-write */
#define GEMDOS_NEXT_CLUSTER   0xfc60f2  /* the cursor one cluster on, allocating on a write */
#define GEMDOS_OFD_XFER       0xfc6218  /* THE transfer: head / sectors / cluster runs / tail */
#define GEMDOS_OFD_READ       0xfc5e9c  /* the transfer, clamped to the file's end, copy-out */
#define GEMDOS_OFD_WRITE      0xfc5f1c  /* ...and unclamped, copy-in */
#define GEMDOS_FREAD          0xfc5e6a  /* ...and the three leaves (their _FN numbers are above) */
#define GEMDOS_FWRITE         0xfc5eea
#define GEMDOS_FSEEK          0xfc7cce
/* fs wave 3: the record layer (`src/gemdos/fs_records.c`). */
#define GEMDOS_FCB_NAME_EQ    0xfc5672  /* two FCB names, eleven bytes, upper-cased: 1 or low word 0 */
#define GEMDOS_OFD_NEW        0xfc5c3c  /* a directory's OFD from its DND, length $7fffffff */
#define GEMDOS_DND_NEW        0xfc65a2  /* a child DND for a subdirectory entry, first on the list */
#define GEMDOS_OFD_OPEN       0xfc6fdc  /* a file's OFD into a handle record; a second open shares */
#define GEMDOS_HANDLE_ALLOC   0xfc6f5c  /* the first unowned handle record, then GEMDOS_OFD_OPEN */
#define GEMDOS_DIR_ZERO_CLUSTER 0xfc70f6 /* a directory's current cluster zeroed through the cache */
#define GEMDOS_FCB_TO_TEXT    0xfc6b66  /* eleven FCB bytes -> "NAME.EXT", NUL-ended */
#define GEMDOS_DND_PATH       0xfc6bd2  /* a DND -> "\A\B\", root first, unterminated */
#define GEMDOS_FILL_DTA       0xfc6ebc  /* a found entry's attribute, time, date, length, name */
/* fs wave 3: the file layer (`src/gemdos/fs_file.c`) — its _FN numbers are above, with the table. */
#define GEMDOS_OFD_CLOSE      0xfc57ee  /* entry rewritten if dirty, OFD unlinked, EVERY buffer flushed */
#define GEMDOS_DELETE_ENTRY   0xfc7824  /* open copies closed or EACCDN, chain freed, `$e5` written */
#define GEMDOS_FDATIME        0xfc772e  /* an open file's time and date, read or written in its entry */
/* fs wave 3: the two leaves over a whole drive (`src/gemdos/fs_leaves.c`). */
#define GEMDOS_DFREE          0xfc7a68  /* free and total clusters, by a FAT scan, and the geometry */
#define GEMDOS_DGETPATH       0xfc6c1a  /* the process's directory on a drive, as "\A\B" */
/* fs wave 3: the DIRECTORY layer (`src/gemdos/fs_dir.c`, `include/gemdos/fs_dir.h`). */
#define GEMDOS_DIR_SEARCH     0xfc663c  /* one directory from a position: the first entry a pattern matches */
#define GEMDOS_FIND_DIR       0xfc696c  /* a path walked down the DND tree to the directory of its last component */
#define GEMDOS_FSNEXT         0xfc6df4  /* the next match of the search a DTA holds, or ENMFIL */
/* fs wave 3: the NAME leaves (`src/gemdos/fs_open.c`, `include/gemdos/fs_open.h`). Their selectors are
 * above, with the table. */
#define GEMDOS_SFIRST         0xfc6d14  /* a path's first match, and the search's state, into a DTA */
#define GEMDOS_FSFIRST        0xfc6cf6  /* ...into the running process's DTA */
#define GEMDOS_DSETPATH       0xfc6a7e  /* a path made the drive's current directory; EPTHNF */
#define GEMDOS_OPEN           0xfc7606  /* a path's file into a handle; EACCDN writing a read-only one */
#define GEMDOS_FOPEN          0xfc75f2
#define GEMDOS_FATTRIB        0xfc7678  /* the entry's attribute byte, read or written */
#define GEMDOS_FDELETE        0xfc77b2  /* a path's file deleted; EACCDN for a read-only one */
/* fs wave 3: the CREATE layer (`src/gemdos/fs_create.c`, `include/gemdos/fs_create.h`). Selectors above. */
#define GEMDOS_CREATE         0xfc71b6  /* an entry made (an existing one deleted first) and opened */
#define GEMDOS_FCREATE        0xfc719a  /* ...Fcreate: the same, the subdirectory bit masked off */
#define GEMDOS_DDELETE        0xfc792a  /* an empty directory's DND freed and its entry deleted */
#define GEMDOS_DCREATE        0xfc73ce  /* a subdirectory entry, a zeroed cluster, `.` and `..` */
/* fs wave 3: `Frename` (`src/gemdos/fs_rename.c`, `include/gemdos/fs_rename.h`). Selector above. */
#define GEMDOS_FRENAME        0xfc7af0  /* renamed in place, or moved: `$e5` + `Fcreate`, the chain handed over */
/* The first 22 bytes — name, attribute, the ten reserved — of the `.` and `..` entries `Dcreate`
 * copies into a new directory's first cluster ($fc74e2, $fc752e `move.l #$fd2fec`/`#$fd3002`). */
#define GEMDOS_DOT_ENTRY_HEAD     0xfd2fec
#define GEMDOS_DOT_DOT_ENTRY_HEAD 0xfd3002

/* WHERE EACH OF THIS GROUP'S BIOS CALLS RETURNS TO — the longword `GEMDOS_BIOS_TRAMPOLINE` parks,
 * one per call site, exactly as `src/gemdos/console.c` keeps its fourteen. Each is the address of
 * the instruction after a `jsr GEMDOS_BIOS_TRAMPOLINE`, which `gemdos.bios_call_site` re-checks
 * against the ROM's own instruction stream. */
#define BIOS_RETURN_BUFFER_FLUSH 0xfc5966    /* $fc5960: the buffer's own record */
#define BIOS_RETURN_BUFFER_FLUSH_FAT1 0xfc59b8 /* $fc59b2: ...and the FIRST FAT copy, `m_fsiz` below */
#define BIOS_RETURN_RWABS_DATA 0xfc5a60      /* $fc5a5a */
#define BIOS_RETURN_BUFFER_READ 0xfc5b84     /* $fc5b7e: the miss that fills an evicted buffer */
#define BIOS_RETURN_BUFFER_MEDIACH 0xfc5bd6  /* $fc5bd0: the hit's media-change interrogation */
#define BIOS_RETURN_OPEN_DRIVE_GETBPB 0xfc6806 /* $fc6800: the drive's BPB — `Getbpb`'s one caller */
#define BIOS_RETURN_DEVICE_WRITE 0xfc9a9a    /* $fc9a94: the dispatcher's device arm, `Fwrite` to AUX:/PRN: */

/* fs wave 3: the DRIVE and PATH layer (`src/gemdos/fs_drive.c`, `include/gemdos/fs_drive.h`). */
#define GEMDOS_DMD_ALLOC      0xfc50fa  /* the DMD, root DND, root OFD and FAT OFD out of the pool */
#define GEMDOS_DMD_BUILD      0xfc53c0  /* BPB -> DMD: three record biases, two pseudo-files */
#define GEMDOS_OPEN_DRIVE     0xfc67de  /* log a drive in through `Getbpb`; a curdir slot for p_run */
#define GEMDOS_PATH_START     0xfc68dc  /* `X:` and a leading `\` -> the DND a path starts in */
#define GEMDOS_DOT_NAME       0xfc7e52  /* 1 for "", -1 for ".", -2 for "..", else 0 */
#define GEMDOS_SPLIT_PATH     0xfc5e08  /* the next path component into an FCB name */
#define GEMDOS_STRNEQ         0xfc7e94  /* n bytes of two strings equal: "CON:"/"AUX:"/"PRN:" */
/* The table `$fc53c0` and `$fc7e24` turn a log2 into a mask with: entry n is (1 << n) - 1 as a word
 * for n = 0..17 ($fc54a4, $fc7e2e); both index it with a signed word and no bound. */
#define GEMDOS_BIT_MASK_TABLE 0xfd2fc8

/* The two BIOS entries this group reaches that `include/bios/bcon.h` does not declare, because they are
 * not reconstructed BIOS cores at all: entries 4, 7 and 9 of the table at `$fc0846` have bit 31 set
 * and the dispatcher's `movea.l (a0),a0` turns each into a jump through a RAM VECTOR, so what runs
 * is whatever the boot (or a hard-disk driver) left there. `BIOS_RWABS_FN`/`HDV_RWABS` are above,
 * with the dispatcher battery that first exercised the indirection. */
#define BIOS_GETBPB_FN        7
#define HDV_BPB               0x472     /* long: `hdv_bpb`, the entry at $fc0846 + 4 + 7*4 points at */
#define BIOS_MEDIACH_FN       9
#define HDV_MEDIACH           0x47e     /* long: `hdv_mediach`, likewise for entry 9 */
/* ...and what `Mediach` answers, which is a three-way protocol rather than a flag. */
#define MEDIACH_UNCHANGED     0         /* the medium is definitely the same one */
#define MEDIACH_MAYBE         1         /* ...might have changed: `GEMDOS_BUFFER_GET` re-reads */
#define MEDIACH_CHANGED       2         /* ...definitely has: E_CHNG, and the call longjmps out */

/* GEMDOS's own file-system RAM. */
#define SYSVAR_BUFL           0x4b2     /* long[2]: the BCB list heads — [0] FAT, [1] dir AND data */
#define SYSVAR_BUFL_ENTRY_BYTES 4
#define GEMDOS_DISK_ERROR     0x75b4    /* long: the last BIOS disk result, kept for the longjmp */
#define GEMDOS_DISK_ERROR_DRIVE 0x87cc  /* word: ...and which drive it came from */
/* ...and the drive tables `$fc67de` keeps. A drive is LOGGED IN when its bit is set here; it then has
 * a DMD in the table, and each process names a directory on it by an index into the node table,
 * whose reference counts are `GEMDOS_CURDIR_REFCOUNTS` (above, one byte per node). */
#define GEMDOS_DRIVES_OPENED  0x8784    /* word: bit n = drive n's DMD is built ($fc67f0, $fc682a) */
#define GEMDOS_DMD_TABLE      0x8380    /* long[16]: each drive's DMD, stored BEFORE the test ($fc511c) */
/* ...the sixteen drives: one bit each in that WORD, one DMD each in this table. */
#define GEMDOS_DRIVE_COUNT    16
#define GEMDOS_DIRECTORY_NODES 0x7dee   /* long[40]: the DNDs a p_curdir byte indexes ($fc6856) */
#define GEMDOS_DIRECTORY_NODE_COUNT 40  /* `cmpi.w #40` bounding the slot search at $fc6874 */
/* ...as the LONGWORD the ROM stores, because that is the form both sides compare: `$fc5bf2` is a
 * `move.l #-14,$75b4`, and a signed spelling would not survive `tools/addrs.py`, which binds plain
 * integers only (a name bound to half a value is worse than a missing one). */
#define E_CHNG_LONG           0xfffffff2u

/* ---- the GEMDOS PROCESS group and the HANDLE machinery under it ---------------------------------
 *
 * `src/gemdos/process.c` and `src/gemdos/handles.c`; the STRUCTURES — the open-file descriptor and
 * what a handle means — are `include/gemdos/process.h`'s, and the BASEPAGE's own offsets are up
 * with the rest of the basepage above. The addresses are here for the registries' sake, exactly as
 * the memory manager's are: `test_boot_snapshot.py` pairs every `<NAME>`/`<NAME>_FN` against the
 * ROM's own dispatch table and `bench/tier3.py` labels a row by the same pair. */
#define GEMDOS_PTERM          0xfc8028
#define GEMDOS_PTERM_FN       0x4c
#define GEMDOS_PTERM0         0xfc8086
#define GEMDOS_PTERM0_FN      0x00
#define GEMDOS_PTERMRES       0xfc7fd8
#define GEMDOS_PTERMRES_FN    0x31
#define GEMDOS_PEXEC          0xfc817a  /* ...and GEMDOS_PEXEC_FN is above, with the table */
#define GEMDOS_FDUP           0xfc5216
#define GEMDOS_FDUP_FN        0x45
#define GEMDOS_FFORCE         0xfc52de
#define GEMDOS_FFORCE_FN      0x46
#define GEMDOS_FCLOSE         0xfc56c6
#define GEMDOS_FCLOSE_FN      0x3e
/* ...and the six with no function number: GEMDOS's own C calls each by name. `GEMDOS_PEXEC_CREATE`
 * is `Pexec` PAST the termination record it arms, which is where a case can enter it at all — the
 * dispatcher's own split, for the dispatcher's reason (`src/gemdos/dispatch.c`). */
#define GEMDOS_PEXEC_CREATE   0xfc8242
#define GEMDOS_PEXEC_LOAD     0xfc85ea  /* the program loader and relocator modes 0 and 3 call */
#define GEMDOS_RELEASE_PROCESS 0xfc8092 /* handles, descriptors, directories and memory, given back */
#define GEMDOS_FORCE_HANDLE   0xfc52f8  /* `Fforce`'s body, over a basepage the caller names */
#define GEMDOS_INHERIT_CURDIR 0xfc51de  /* one p_curdir entry copied, and its node's count bumped */
#define GEMDOS_RESYNC_CLOCK   0xfc5092  /* the Mega ST battery clock re-read, which only Pterm does */
/* Read only, for the cases and the name map: the trampoline `Pterm` reaches the terminate vector
 * through, the BIOS's battery-clock probe under `GEMDOS_RESYNC_CLOCK`, and GEMDOS's own setjmp and
 * longjmp — the dispatcher arms the record with the first and the FILE SYSTEM's critical-error
 * abort is what jumps to it with the second. `Pterm` uses neither. */
#define GEMDOS_CALL_TERM_VECTOR 0xfc4f0a
#define BIOS_RTC_PROBE        0xfc4c0c
#define GEMDOS_LONGJMP        0xfc4f54

/* ---- the VDI and LINE-A ($fc9f0c..$fd2f21) ------------------------------------------------------
 *
 * The STRUCTURES — the Line-A variable block, the workstation, the font header, the tables — are the
 * component's own headers (`include/vdi/`); only routine addresses are here, for the registries' sake.
 *
 * ONE RULE FOR EVERY ROUTINE ADDRESS in this block: `VDI_ROM_<X>` for a VDI routine — a function, a
 * dispatcher, a helper reached by `jsr` — and `LINEA_ROM_<X>` for a Line-A primitive or body. A `VDI_`
 * or `LINEA_` name WITHOUT the `ROM_` is data or a field (`include/vdi/`). The C core is the name less its
 * `ROM_`, lower-cased (`vdi_<x>`, `linea_<x>`), and a `.S` transcription's entry is the name lower-cased
 * (`vdi_rom_<x>`, `linea_rom_<x>`) — `test/routines.py`'s `core_symbol` and `test/transcription.py`'s
 * `transcription_symbol`. The `ROM_` is not decoration: the kit's `os.h`, which this header includes,
 * already defines `VDI_<FN>` as the OPCODE for the functions its game model serves (`VDI_VSF_INTERIOR`,
 * `VDI_V_OPNVWK`, ...).
 *
 * A VDI FUNCTION IS REACHED BY OPCODE, not by a trap function number, so it is spelt:
 *   `VDI_ROM_<FN>`            the routine's address, whose C core is `vdi_<fn>`;
 *   `VDI_ROM_<FN>_OPCODE`     the opcode `$fca9f6`'s tables serve it for — deliberately not `_FN`,
 *                             which `test_boot_snapshot.py` reads as a BIOS/XBIOS/GEMDOS table slot;
 *   `..._OPCODE_<k>`          each further opcode the SAME routine serves (a shared stub);
 *   `..._SUBFUNCTION`         for an ARM behind a sub-dispatcher: `_OPCODE` is then the parent's opcode
 *                             and this is contrl[5] (escape 5.n, GDP 11.n — `vdi/vdi.h`).
 * `test_vdi_staging.py` holds every one of them against the ROM's own opcode and sub-function tables,
 * and `bench/tier3.py` derives a function's Tier 3 entry from its `_OPCODE`, so a new VDI function is
 * one pair of lines here. */
#define VECTOR_LINE_A         0x28       /* the Line-A exception -> LINEA_ROM_DISPATCH */
#define LINEA_ROM_DISPATCH        0xfc9f0c   /* the $Axxx handler: `rte`, not `rts` */
#define LINEA_ROM_INIT            0xfc9f34   /* $a000 */
/* The PIXEL / SCANLINE primitives (`src/vdi/raster.c`), each with the register contract its battery
 * declares; `_PATTERNED` and `_SPAN` are MID-FUNCTION entries of $a004 that other routines enter at,
 * and the three `_CPU_` bodies are what drawing vectors 6..8 hold in the captured machine. */
#define LINEA_ROM_CONCAT          0xfca1b8   /* (x, y) in D0/D1 -> screen offset in D1, bit in D0 */
#define LINEA_ROM_LINE            0xfca1ea   /* $a003 */
#define LINEA_ROM_LINE_PLANE_WORDS 0xfca3f4  /* the diagonal/vertical line's per-plane opcode words */
#define LINEA_ROM_HLINE           0xfca57e   /* $a004 */
#define LINEA_ROM_HLINE_PATTERNED 0xfca58a   /* $a004 past its coordinate load: contour fill ($fcfb62) */
#define LINEA_ROM_HLINE_SPAN      0xfca5a2   /* ...past its pattern too: $a003's horizontal arm ($fca312) */
#define LINEA_ROM_PUT_PIXEL       0xfcface   /* $a001 */
#define LINEA_ROM_GET_PIXEL       0xfcfb16   /* $a002 */
#define LINEA_ROM_FILLED_RECT     0xfcfc56   /* $a005 */
#define LINEA_ROM_CPU_VLINE       0xfd19dc   /* LINEA_VECTOR_VLINE's CPU body */
#define LINEA_ROM_CPU_HLINE       0xfd1ae0   /* LINEA_VECTOR_HLINE's CPU body */
#define LINEA_ROM_CPU_RECT_FILL   0xfd1b16   /* LINEA_VECTOR_RECT_FILL's CPU body */
/* The TEXT raster (`src/vdi/text_raster.c`): $a008 and v_gtext's byte-aligned fast path, each a front end
 * that jumps through its drawing vector — 9 and 5 — to the `_CPU_` body the captured machine has there. */
#define LINEA_ROM_TEXTBLT         0xfcee54   /* $a008: A6 = the Line-A base, A5/A6 pushed, `jmp` vector 9 */
#define LINEA_ROM_CPU_TEXTBLT     0xfd1df6   /* LINEA_VECTOR_TEXTBLT's CPU body */
#define LINEA_ROM_FAST_TEXT       0xfcf96a   /* v_gtext's `jsr`: D0 = 1 drawn, 0 refused ($fcdba2) */
#define LINEA_ROM_CPU_FAST_TEXT   0xfd1cc4   /* LINEA_VECTOR_FAST_TEXT's CPU body */
/* The TEXT layer's C (`src/vdi/text.c`, `vdi/text.h`): the font ring's set-up and the scaled header, the
 * size and face setters, the two measuring inquiries, and the GDOS font loader. */
#define VDI_ROM_TEXT_INIT         0xfcde9c   /* v_opnwk's: the ring, SIZ_TAB's character sizes, DEF_FONT */
#define VDI_ROM_MAKE_HEADER       0xfce116   /* WS_CUR_FONT scaled into WS_SCRATCH_HEAD by the text DDA */
#define VDI_ROM_VST_HEIGHT        0xfcdfd0
#define VDI_ROM_VST_HEIGHT_OPCODE 12
#define VDI_ROM_VST_POINT         0xfce26c
#define VDI_ROM_VST_POINT_OPCODE  107
#define VDI_ROM_VST_FONT          0xfce47c
#define VDI_ROM_VST_FONT_OPCODE   21
#define VDI_ROM_VQT_EXTENT        0xfce62a
#define VDI_ROM_VQT_EXTENT_OPCODE 116
#define VDI_ROM_VQT_WIDTH         0xfce7f0
#define VDI_ROM_VQT_WIDTH_OPCODE  117
#define VDI_ROM_VST_LOAD_FONTS    0xfced06
#define VDI_ROM_VST_LOAD_FONTS_OPCODE 119
/* GRAPHIC TEXT (`src/vdi/gtext.c`, `vdi/gtext.h`): v_gtext, and the justified-text worker the GDP's arm 10
 * `jsr`s ($fcbd56), which draws through it. */
#define VDI_ROM_V_GTEXT           0xfcd756
#define VDI_ROM_V_GTEXT_OPCODE    8
#define VDI_ROM_D_JUSTIFIED       0xfce9e8   /* Alcyon, no arguments: GDP 10's string spread to ptsin[2] */
#define LINEA_ROM_SEEDABORT_DEFAULT 0xfc9f9a /* `moveq #0,d0 / rts`: v_contourfill's SEEDABORT ($fd08e4) */
#define VDI_ROM_ENTRY             0xfc9f9e   /* where SYSVAR_VDI_ENTRY's routine calls in, D1 = the parameter block */
#define VDI_ROM_DISPATCH          0xfca9f6
#define VDI_ROM_V_OPNWK           0xfcb694
#define VDI_ROM_V_OPNWK_OPCODE    1
#define VDI_ROM_V_OPNVWK          0xfcd612
#define VDI_ROM_V_OPNVWK_OPCODE   100
#define VDI_ROM_NOP               0xfca652   /* `rts`: four opcodes' entry, and USER_TIM's default */
#define VDI_ROM_NOP_OPCODE        4
#define VDI_ROM_NOP_OPCODE_10     10
#define VDI_ROM_NOP_OPCODE_27     27
#define VDI_ROM_NOP_OPCODE_34     34
#define VDI_ROM_ESCAPE            0xfc427a   /* the escape sub-dispatcher, in the BIOS's range */
#define VDI_ROM_ESCAPE_OPCODE     5
/* ...and the escape's own code past its dispatch, in the three spans `src/vdi/escape.S` lays out from their first
 * routines: the VT52 console's bodies lie between them, and the escape's table names those too. */
#define VDI_ROM_VQ_CHCELLS        0xfc442e   /* vq_chcells .. v_exit_cur, which ends in ESC E's body */
#define VDI_ROM_VS_CURADDRESS     0xfc44dc   /* vs_curaddress .. v_rmcur */
#define VDI_ROM_V_FONTINIT        0xfc4a42   /* escape 102, past the console's cell routines */
#define VDI_ROM_GDP               0xfcbbcc   /* the GDP sub-dispatcher */
#define VDI_ROM_GDP_OPCODE        11
#define VDI_ROM_V_CONTOURFILL     0xfd08e0   /* installs LINEA_ROM_SEEDABORT_DEFAULT, then $a00f */
#define VDI_ROM_V_CONTOURFILL_OPCODE 103
#define VDI_ROM_VSF_PERIMETER     0xfcb45c
#define VDI_ROM_VSF_PERIMETER_OPCODE 104
/* The ATTRIBUTE SETTERS (`src/vdi/attributes.c`), and the two helpers they share with other layers:
 * the fill-pattern pointer and the corner sort, reached by `jsr` with a C frame rather than by opcode. */
#define VDI_ROM_VSL_TYPE          0xfcac76
#define VDI_ROM_VSL_TYPE_OPCODE   15
#define VDI_ROM_VSL_WIDTH         0xfcacc0
#define VDI_ROM_VSL_WIDTH_OPCODE  16
#define VDI_ROM_VSL_ENDS          0xfcad20
#define VDI_ROM_VSL_ENDS_OPCODE   108
#define VDI_ROM_VSL_COLOR         0xfcad7c
#define VDI_ROM_VSL_COLOR_OPCODE  17
#define VDI_ROM_VSM_HEIGHT        0xfcadcc
#define VDI_ROM_VSM_HEIGHT_OPCODE 19
#define VDI_ROM_VSM_TYPE          0xfcae58
#define VDI_ROM_VSM_TYPE_OPCODE   18
#define VDI_ROM_VSM_COLOR         0xfcaea8
#define VDI_ROM_VSM_COLOR_OPCODE  20
#define VDI_ROM_VSF_INTERIOR      0xfcaefe
#define VDI_ROM_VSF_INTERIOR_OPCODE 23
#define VDI_ROM_VSF_STYLE         0xfcaf4a
#define VDI_ROM_VSF_STYLE_OPCODE  24
#define VDI_ROM_VSF_COLOR         0xfcafb2
#define VDI_ROM_VSF_COLOR_OPCODE  25
#define VDI_ROM_VSWR_MODE         0xfcb32e
#define VDI_ROM_VSWR_MODE_OPCODE  32
#define VDI_ROM_VSIN_MODE         0xfcb388
#define VDI_ROM_VSIN_MODE_OPCODE  33
#define VDI_ROM_VQIN_MODE         0xfcb3f6
#define VDI_ROM_VQIN_MODE_OPCODE  115
#define VDI_ROM_VSL_UDSTY         0xfcb4a2
#define VDI_ROM_VSL_UDSTY_OPCODE  113
#define VDI_ROM_VS_CLIP           0xfcb4ba
#define VDI_ROM_VS_CLIP_OPCODE    129
#define VDI_ROM_VSF_UDPAT         0xfcd6fa
#define VDI_ROM_VSF_UDPAT_OPCODE  112
#define VDI_ROM_VST_EFFECTS       0xfce3b2
#define VDI_ROM_VST_EFFECTS_OPCODE 106
#define VDI_ROM_VST_ALIGNMENT     0xfce3e6
#define VDI_ROM_VST_ALIGNMENT_OPCODE 39
#define VDI_ROM_VST_ROTATION      0xfce442
#define VDI_ROM_VST_ROTATION_OPCODE 13
#define VDI_ROM_VST_COLOR         0xfce560
#define VDI_ROM_VST_COLOR_OPCODE  22
#define VDI_ROM_VEX_TIMV          0xfca6a4
#define VDI_ROM_VEX_TIMV_OPCODE   118
#define VDI_ROM_VEX_BUTV          0xfcff68
#define VDI_ROM_VEX_BUTV_OPCODE   125
#define VDI_ROM_VEX_MOTV          0xfcff80
#define VDI_ROM_VEX_MOTV_OPCODE   126
#define VDI_ROM_VEX_CURV          0xfcff98
#define VDI_ROM_VEX_CURV_OPCODE   127
#define VDI_ROM_ST_FL_PTR         0xfcc9a6   /* WS_PATPTR/PATMSK from the interior and style index */
#define VDI_ROM_ARB_CORNER        0xfcb55e   /* (corners.l, order.w): sort a rectangle's two corners */
/* The INQUIRIES (`src/vdi/inquire.c`) and the PALETTE pair (`src/vdi/palette.c`). */
#define VDI_ROM_VALUATOR          0xfcb198   /* `link / unlk / rts`: valuator input is not served */
#define VDI_ROM_VALUATOR_OPCODE   29
#define VDI_ROM_VQL_ATTRIBUTES    0xfcbd7e
#define VDI_ROM_VQL_ATTRIBUTES_OPCODE 35
#define VDI_ROM_VQM_ATTRIBUTES    0xfcbdda
#define VDI_ROM_VQM_ATTRIBUTES_OPCODE 36
#define VDI_ROM_VQF_ATTRIBUTES    0xfcbe3a
#define VDI_ROM_VQF_ATTRIBUTES_OPCODE 37
#define VDI_ROM_VQT_ATTRIBUTES    0xfce5b0
#define VDI_ROM_VQT_ATTRIBUTES_OPCODE 38
#define VDI_ROM_VQ_EXTND          0xfcb8d0
#define VDI_ROM_VQ_EXTND_OPCODE   102
#define VDI_ROM_VST_UNLOAD_FONTS  0xfced9a
#define VDI_ROM_VST_UNLOAD_FONTS_OPCODE 120
#define VDI_ROM_VQ_MOUSE          0xfcb156
#define VDI_ROM_VQ_MOUSE_OPCODE   124
#define VDI_ROM_VQ_KEY_S          0xfcb30a
#define VDI_ROM_VQ_KEY_S_OPCODE   128
#define VDI_ROM_VQT_NAME          0xfce8ca
#define VDI_ROM_VQT_NAME_OPCODE   130
#define VDI_ROM_VQT_FONTINFO      0xfce95a
#define VDI_ROM_VQT_FONTINFO_OPCODE 131
#define VDI_ROM_VS_COLOR          0xfd2dd2   /* hand 68000; the mono clamp is its local $fd2e6e */
#define VDI_ROM_VS_COLOR_OPCODE   14
#define VDI_ROM_VQ_COLOR          0xfd2e84   /* hand 68000 */
#define VDI_ROM_VQ_COLOR_OPCODE   26
/* The PURE HELPERS (`src/vdi/helpers.c`, `vdi/helpers.h`): Alcyon C calls taking WORD arguments on the
 * stack, and three register routines — sort_words, clamp_mouse, get_kbshift — whose contracts their
 * battery declares. vr_trnfm is the one VDI function among them, with its two transposes. */
#define VDI_ROM_VEC_LEN           0xfc9ffc   /* isqrt(dx^2 + dy^2) by bisection */
#define VDI_ROM_SORT_WORDS        0xfca164   /* D0.w words at A0, bubble-sorted, signed */
#define VDI_ROM_SMUL_DIV          0xfca186   /* a * b / c rounded half away from zero, by `divs.w` */
#define VDI_ROM_ISIN              0xfcab68   /* sine x 32767 of an angle in tenths of a degree */
#define VDI_ROM_ICOS              0xfcac4c   /* ...cosine, as isin(angle + 900) */
#define VDI_ROM_CLIP_CODE         0xfcc092   /* a point's outcode against the Line-A clip rectangle */
#define VDI_ROM_CLC_NSTEPS        0xfcc6b4   /* LINEA_GDP_N_STEPS from the larger radius */
#define VDI_ROM_QUAD_XFORM        0xfcced6   /* (x, y) signed into a quadrant, through two pointers */
#define VDI_ROM_CLC_DDA           0xfcedd0   /* the text scaler's increment and direction */
#define VDI_ROM_ACT_SIZ           0xfcee02   /* a size stepped through the text scaler's DDA */
#define VDI_ROM_COPY_NAME         0xfce0ee   /* a font's 32-byte name, copied */
#define VDI_ROM_CLAMP_MOUSE       0xfcfedc   /* D0/D1 clamped to the screen */
#define VDI_ROM_FONT_BYTESWAP     0xfcfaac   /* an Intel-order font form turned round in place */
#define VDI_ROM_GEMDOS_CALL       0xfcfa9c   /* `trap #1` with its return address parked at LINEA_RETSAV */
#define VDI_ROM_GET_KBSHIFT       0xfca648   /* the shift state's four modifier bits, in D0.w */
#define VDI_ROM_S_FA_ATTR         0xfcd056   /* the fill attributes saved, a solid outline set */
#define VDI_ROM_R_FA_ATTR         0xfcd0c2   /* ...and restored */
#define VDI_ROM_VR_TRNFM          0xfd2d32   /* device <-> standard raster form */
#define VDI_ROM_VR_TRNFM_OPCODE   110
#define VDI_ROM_TRNFM_IN_PLACE    0xfd2d80   /* vr_trnfm's transpose over one buffer */
#define VDI_ROM_TRNFM_COPY        0xfd2db4   /* ...and from one buffer into another */
/* The BIT-BLOCK TRANSFER (`src/vdi/blit.c`): the two Line-A front ends, the CPU engine drawing vector 4
 * holds in the captured machine and the threaded logic-op code it jumps through, and the three VDI
 * functions over them. The register contracts are `test/vdi_blit.py`'s `declare_primitive`s. */
#define LINEA_ROM_COPY_RASTER     0xfd0346   /* $a00e: two MFDBs, ptsin's two rectangles, intin's mode */
#define LINEA_ROM_BITBLT          0xfd05fc   /* $a007: A6 = the caller's BITBLT block */
#define LINEA_ROM_CPU_BLIT        0xfd1038   /* LINEA_VECTOR_BITBLT's CPU body: D0/D2/D4/D6 edges, A6 frame */
#define LINEA_ROM_CPU_BLIT_OPS    0xfd1694   /* its fragments: the pattern row, the aligners, 16 logic ops */
#define VDI_ROM_VRO_CPYFM         0xfcb5aa
#define VDI_ROM_VRO_CPYFM_OPCODE  109
#define VDI_ROM_VRT_CPYFM         0xfcb5dc
#define VDI_ROM_VRT_CPYFM_OPCODE  121
#define VDI_ROM_VR_RECFL          0xfcb614
#define VDI_ROM_VR_RECFL_OPCODE   114
/* POLYGONS and FILLS (`src/vdi/fill.c`, `vdi/fill.h`): $a006's scanline fill and the Alcyon geometry
 * over it, and $a00f's contour (seed) fill with its hand-68000 span and scan helpers. */
#define LINEA_ROM_FILLED_POLY     0xfca05e   /* $a006: one scanline, Y1, of the polygon ptsin closes */
#define VDI_ROM_POLYLINE          0xfcbe8c   /* contrl[1] points joined by $a003, clipped when CLIP */
#define VDI_ROM_CLIP_LINE         0xfcbf16   /* X1,Y1..X2,Y2 cut to the clip rectangle -> D0.w: 0 = none left */
#define VDI_ROM_PLYGN             0xfcc0ea   /* the polygon filled row by row, then its perimeter */
#define VDI_ROM_V_FILLAREA        0xfcbbc0
#define VDI_ROM_V_FILLAREA_OPCODE 9
#define LINEA_ROM_CONTOUR_FILL    0xfd08f4   /* $a00f */
#define LINEA_ROM_FILL_SPAN       0xfcfb54   /* Alcyon (x1, x2, y) -> $a004's patterned entry */
#define LINEA_ROM_END_PTS         0xfcfb66   /* Alcyon (x, y, &xleft, &xright): the seed colour's run */
#define LINEA_ROM_CRUNCH_QUEUE    0xfd0dc8   /* the queue's empty top records dropped; SEEDABORT per pass */
#define LINEA_ROM_GET_SEED        0xfd0e22   /* Alcyon (x, y, &xleft, &xright, &collide): a span queued */
#define VDI_ROM_V_GET_PIXEL       0xfd0fde
#define VDI_ROM_V_GET_PIXEL_OPCODE 105
/* POLYLINES and MARKERS (`src/vdi/lines.c`, `vdi/lines.h`): the two functions and the Alcyon geometry of a
 * WIDE line — its quarter circle, round ends, segments and arrowheads. */
#define VDI_ROM_V_PLINE           0xfcb9e0   /* the style and colour, then polyline + arrows, or wline */
#define VDI_ROM_V_PLINE_OPCODE    6
#define VDI_ROM_V_PMARKER         0xfcba7a   /* each point's shape as polylines through v_pline */
#define VDI_ROM_V_PMARKER_OPCODE  7
#define VDI_ROM_CIR_DDA           0xfcca86   /* LINEA_Q_CIRCLE for WS_LINE_WIDTH, in the device's aspect */
#define VDI_ROM_WLINE             0xfccba0   /* a polyline WS_LINE_WIDTH wide: a polygon a segment, round ends */
#define VDI_ROM_PERP_OFF          0xfccd92   /* Alcyon (&x, &y): a direction turned into the quarter circle's offset */
#define VDI_ROM_DO_CIRC           0xfccf4e   /* Alcyon (x, y): a disc of the quarter circle, a line a row */
#define VDI_ROM_ARROW             0xfcd0fa   /* the arrowheads WS_LINE_BEG/END ask for, the line shortened */
#define VDI_ROM_DO_ARROW          0xfcd196   /* Alcyon (&point, step): one arrowhead at the point, filled */
/* ARCS, ELLIPSES and ROUNDED BOXES (`src/vdi/arcs.c`, `vdi/arcs.h`): the GDP's curve workers, each entered
 * by `jsr` from one of vdi_gdp's arms with the arc scratch or the arm's arrays staged. */
#define VDI_ROM_CLC_PTS           0xfcc914   /* Alcyon (point): the point at LINEA_GDP_ANGLE into ptsin[point] */
#define VDI_ROM_CLC_ARC           0xfcc79e   /* the curve as points in ptsin, then v_pline or plygn */
#define VDI_ROM_GDP_ARC           0xfcc62e   /* arc and pie: intin's angles, ptsin's centre and radius */
#define VDI_ROM_GDP_ELL           0xfcc714   /* the elliptical arc and pie: ...and both radii */
#define VDI_ROM_GDP_RBOX          0xfcc284   /* the rounded box, outlined or filled: 21 points */
/* The MOUSE, CURSOR and INPUT routines (`src/vdi/mouse.c`): the sprite pair and the hide/show count
 * ($a009..$a00d), the IKBD mouse vector and the VBL's redraw, the device polls and the three input
 * functions. The register routines' contracts are `test/vdi_mouse.py`'s `declare_primitive`s. */
#define LINEA_ROM_DRAW_SPRITE     0xfcffb0   /* $a00d: A0 form, A2 save block, D0/D1 position */
#define LINEA_ROM_UNDRAW_SPRITE   0xfd0184   /* $a00c: A2 save block */
#define LINEA_ROM_HIDE_MOUSE      0xfd0254   /* $a00a; also v_hide_c's body */
#define VDI_ROM_SHOW_CURSOR       0xfd0286   /* the hide count down one; drawn at GCURX/GCURY on reaching 0 */
#define VDI_ROM_V_SHOW_C          0xfcb120   /* also $a009 */
#define VDI_ROM_V_SHOW_C_OPCODE   122
#define VDI_ROM_V_HIDE_C          0xfcb148
#define VDI_ROM_V_HIDE_C_OPCODE   123
#define VDI_ROM_VSC_FORM          0xfd02ca   /* also $a00b */
#define VDI_ROM_VSC_FORM_OPCODE   111
#define VDI_ROM_MOUSE_ISR         0xfcfe28   /* KBDVECS' mousevec: A0 the relative packet */
#define VDI_ROM_DEFAULT_USER_CUR  0xfcff0a   /* USER_CUR's default: D0/D1 queued for the VBL */
#define VDI_ROM_VBL_DRAW_CURSOR   0xfcff2a   /* _vblqueue[0]: the queued position redrawn */
#define VDI_ROM_MOUSE_INIT        0xfca7f8   /* user vectors, the arrow, the VBL slot, XBIOS Initmous */
#define VDI_ROM_USER_VECTOR_DEFAULT 0xfca870 /* mouse_init's own closing `rts`: USER_BUT/MOT's default ($fca7f8) */
#define VDI_ROM_MOUSE_OFF         0xfca872   /* the VBL slot cleared, XBIOS Initmous(0) */
#define VDI_ROM_POLL_LOCATOR      0xfca88a   /* -> D0: 0 nothing, 1 a button or key, 2 motion */
#define VDI_ROM_POLL_CHOICE       0xfca7c0   /* TERM_CH = 1; D0 is the CALLER'S */
#define VDI_ROM_POLL_KEY          0xfca7ca   /* -> D0: 1 a key read into TERM_CH, 0 none waiting */
#define VDI_ROM_LOCATOR           0xfcb002
#define VDI_ROM_LOCATOR_OPCODE    28
#define VDI_ROM_CHOICE            0xfcb1a0
#define VDI_ROM_CHOICE_OPCODE     30
#define VDI_ROM_STRING            0xfcb22a
#define VDI_ROM_STRING_OPCODE     31
/* The SCREEN AND WORKSTATION PLUMBING (`src/vdi/screen.c`): the screen clear, the resolution v_opnwk opens
 * in, and the timer and mouse the physical workstation takes over and gives back. */
#define VDI_ROM_CLEAR_SPAN        0xfc4b7c   /* the BIOS's bzero(from.l, to.l); GEMDOS's loader calls it too */
#define VDI_ROM_V_CLRWK           0xfca654   /* the span clear over _v_bas_ad .. +32000 */
#define VDI_ROM_V_CLRWK_OPCODE    3
#define VDI_ROM_INIT_TIMER_MOUSE  0xfca670   /* v_opnwk's: USER_TIM, etv_timer, mouse_init, cursor off, clear */
#define VDI_ROM_SETRES            0xfca6d4   /* v_opnwk's: -> D0 = the resolution opened in, plus one */
#define VDI_ROM_TIMER_TICK        0xfca78a   /* etv_timer: USER_TIM, then NEXT_TIM with the tick word */
#define VDI_ROM_RESTORE_TIMER_MOUSE 0xfca7a2 /* v_clswk's: etv_timer back, mouse_off, clear, cursor on */
/* The WORKSTATIONS (`src/vdi/workstation.c`, `vdi/workstation.h`): the two closes, and the record set-up both
 * opens end in. The opens themselves, served without a handle lookup, are named with the dispatcher above. */
#define VDI_ROM_V_CLSWK           0xfcb998   /* every virtual workstation Mfree'd, then restore_timer_mouse */
#define VDI_ROM_V_CLSWK_OPCODE    2
#define VDI_ROM_V_CLSVWK          0xfcd6a4   /* the current one unlinked and Mfree'd, unless handle 1 */
#define VDI_ROM_V_CLSVWK_OPCODE   101
#define VDI_ROM_INIT_WK           0xfcd402   /* Alcyon, no arguments: the current record from intin[1..10] */
/* The REQUEST spins' WAIT SITES (sched.h): each loop's `jsr` to its poll, where a pass re-enters and where
 * a case's schedule lands an interrupt's store — before the poll reads CUR_MS_STAT or the keyboard ring. */
#define VDI_LOCATOR_WAIT_SITE     0xfcb03c
#define VDI_CHOICE_WAIT_SITE      0xfcb1b8
#define VDI_STRING_WAIT_SITE      0xfcb268

/* ---- the AES ($fe387c..$fee8ff; gemstart and geminit $fd9eca..$fda56d) ---------------------------------------
 *
 * The STRUCTURES — GEMBSS, THEGLO's tables, the object layer, the Line-F mechanism — are the component's own headers
 * (`include/aes/`); only routine addresses are here, for the registries' sake.
 *
 * THE VDI's NAMING RULE, one component over (`test/routines.py`): `AES_ROM_<X>` for an AES routine, whose C core is
 * `aes_<x>`; an `AES_` name without the `ROM_` is data or a field (`include/aes/`). The `ROM_` is needed for the
 * VDI's reason: the kit's `os.h` already defines `AES_<FN>` as the OPCODE its game model serves (`AES_APPL_INIT`).
 *
 * GEM NEVER ENTERS AN AES ROUTINE THROUGH ITS OWN ABI: `trap #2` reaches the dispatcher, whose arms Line-F-call the
 * implementation, and the desk calls the implementations directly. So an AES FUNCTION is spelt as the VDI's is:
 *   `AES_ROM_<FN>`            the implementation the dispatcher's arm calls;
 *   `AES_ROM_<FN>_OPCODE`     the opcode whose arm (`AES_OPCODE_TABLE`, opcode - 10) calls it;
 *   `..._OPCODE_<k>`          each further opcode whose arm calls the SAME routine.
 * `test_aes_door.py` holds every one to the arm's own Line-F call (or `movea.l #routine,a0` for 73/74). Names marked
 * `ctx` are inferred from the opcode arm that calls them, not from a read of the body (`names.txt`'s `# ctx`).
 * Not paired: 10 appl_init and 77 graf_handle (inline in their arms), 19 appl_exit and 78 graf_mouse (several calls),
 * 34 menu_text (the string copy), and 11 appl_read — its arm FALLS INTO 12's, so no call of its own names ap_rdwr. */
#define VECTOR_LINE_F             0x2c       /* the Line-F exception -> the RAM copy of AES_ROM_LINEF_HANDLER */
#define AES_OPCODE_TABLE          0xfef834   /* longwords for opcodes 10..125, by opcode - 10 ($fe64c8) */
#define AES_OPCODE_FIRST          10         /* ($fe64ba sub.w #10) */
#define AES_OPCODE_LAST           125        /* ($fe64be cmp.w #115 over the sub, then `bhi`: unsigned) */
#define AES_ROM_DEFAULT_ARM       0xfe64a6   /* every gap in the table: an alert, then -1 */
/* The entries and the dispatcher's own machinery (hand 68000 but for the three Alcyon routines named so). */
#define AES_ROM_GEM_ENTRY         0xfd9eca   /* gemstart: the entry the memory-usage block at $fefff4 names */
#define AES_ROM_LINEF_HANDLER     0xfee8c2   /* copied to RAM at init; $2c points at the copy */
#define AES_ROM_ENTRY             0xfe65aa   /* aes_entry (Alcyon): `trap #2` D0 = 200/201 */
#define AES_ROM_MARSHAL           0xfe64e6   /* aes_marshal (Alcyon): the arrays in, the dispatch, intout back */
#define AES_ROM_DISPATCH          0xfe5d9c   /* aes_dispatch (Alcyon): the opcode switch */
#define AES_ROM_DSPTCH            0xfe387c   /* a bare `rts` while AES_INDISP is set, else into disp */
#define AES_ROM_SAVESTATE         0xfe38d4
#define AES_ROM_SWITCHTO          0xfe3930   /* `rte` into another process's UDA: never returns */
#define AES_ROM_GOTOPGM           0xfe38b0   /* `rte` into the basepage's text, user mode */
/* ...the interrupt-mask brackets beside them (hand 68000; Line-F words $f740 / $f744 / $f890 / $f898), and where a run
 * that follows switchto into another context ends: its `rte`. */
#define AES_ROM_SPL7_SAVE         0xfe3890   /* the SR parked in AES_SR_SPL, the mask raised to 7 */
#define AES_ROM_SPL_RESTORE       0xfe389c   /* ...and the SR back from it */
#define AES_ROM_CLI               0xfe38a4   /* the mask raised to 7, nothing parked (gem_main's) */
#define AES_ROM_STI               0xfe38aa   /* ...and cleared to 0 */
#define AES_ROM_SWITCHTO_RTE      0xfe395a   /* switchto's last instruction: the resumed process's frame under SP */
#define AES_ROM_DISP              0xfe4d9e   /* Alcyon: savestate, the lists, forker/idle, switchto */
#define AES_ROM_DISP_ACT          0xfe4b74
#define AES_ROM_MWAIT_ACT         0xfe4b9c
#define AES_ROM_FORKQ             0xfe4b1a
#define AES_ROM_FORKER            0xfe4bc6   /* `jsr (a0)` on each queued fork function's ROM address ($fe4cba) */
#define AES_ROM_CHKKBD            0xfe4cd6   /* the keyboard, polled through the VDI (128, 33, 31) */
#define AES_ROM_IDLE              0xfe4d68   /* chkkbd until a process is ready or a fork is queued */
/* ...disp's own LOOP, where the snapshot waits: forker, then idle, until a process is ready; then switchto the first
 * ready one ($fe4dda..$fe4dfe). The event door's machines are woken by running it (`test/aes_event.py`). */
#define AES_ROM_DISP_LOOP         0xfe4dda
/* ...idle's own loop, where the machine WAITS FOR AN INTERRUPT: its chkkbd call, reached with nothing ready, nothing
 * woken and nothing queued ($fe4d70) — and disp's call of switchto, after which it runs no instruction: the Line-F
 * return behind it ($fe4e00) is dead. */
#define AES_ROM_IDLE_LOOP         0xfe4d70
#define AES_ROM_IDLE_POLLED       0xfe4d72   /* ...and the instruction its chkkbd comes back to */
#define AES_ROM_DISP_SWITCHTO     0xfe4dfe
#define AES_ROM_DISP_END          0xfe4e00
/* The FORK FUNCTIONS: forkq queues one by its ROM address, an immediate (`test/aes.py`'s FORK_FUNCTION_IMMEDIATES). */
#define AES_ROM_TCHANGE           0xfe4e02   /* the timer's */
#define AES_ROM_KCHANGE           0xfe5180   /* the keyboard's */
#define AES_ROM_BCHANGE           0xfe51d8   /* the button's */
#define AES_ROM_MCHANGE           0xfe534c   /* the mouse's */
#define AES_AP_TPLAY_FORKQ_CALL   0xfe671e   /* ap_tplay's forkq call: it pushes a LOCAL, not an immediate */
/* THE INPUT LAYER's posts and the click counter (geminput, Alcyon, `aes/evinput.h`, read:). */
#define AES_ROM_NQ                0xfe5092   /* (key, queue): a key at the rear of a CDA's key queue, dropped when full */
#define AES_ROM_DOWNORUP          0xfe5292   /* (buttons, parameter): whether the buttons satisfy a button wait */
#define AES_ROM_POST_KEYBD        0xfe51a2   /* (pd, key): to pd's first keyboard wait, else into its key queue */
#define AES_ROM_POST_MOUSE        0xfe5480   /* (pd, x, y): each of pd's mouse waits the point satisfies woken */
#define AES_ROM_INOROUT           0xfe54b8   /* (evb, x, y): the point against a mouse wait's rectangle and sense */
#define AES_ROM_MOWNER            0xfe4ef0   /* (x, y): 1 the control rectangle, -1 the bar or a window, 0 */
#define AES_ROM_SET_MOWN          0xfe504a   /* (mouse pd, keyboard pd): the owners set, the mouse's told */
#define AES_ROM_B_CLICK           0xfe4f40   /* (buttons): the button interrupt's click counter, entered by `jsr` ($fed3d0) */
#define AES_ROM_B_DELAY           0xfe4fb0   /* (ticks): the click count run down; at 0 forkq(bchange, clicks) */
/* ...and the cursor call mchange makes while a recording plays (hand 68000: `jsr` through AES_DRWADDR), with the bare
 * `rts` whose ADDRESS the snapshot holds there. */
#define AES_ROM_DRAWRAT           0xfed412   /* (x, y): D0, D1 := the words, `jsr (*$947a)` */
#define AES_ROM_JUSTRETF          0xfed424   /* an `rts`: what AES_DRWADDR holds while no cursor routine is saved */
#define AES_ROM_EV_MWAIT          0xfe40b2   /* PD_EVWAIT := mask; blocks through dsptch unless PD_EVFLG has it */
#define AES_ROM_EV_MWAIT_RESUMED  0xfe40e0   /* ...past its call of dsptch: where a process that waited resumes, woken */
/* A WAIT QUEUED (gemasync's iasync and geminput's five kinds, Alcyon, `aes/evwait.h`, read:), and the event library's
 * two helpers ev_multi shares with the single waits (Alcyon, `aes/evlib.h`, read:). */
#define AES_ROM_IASYNC            0xfe40ec   /* (code, parameter): an EVB for rlr, a free event bit, the wait of `code` queued */
#define AES_ROM_AMUTEX            0xfe4e8e   /* (evb, spb): tak_flag → completed, else onto the semaphore's wait list */
#define AES_ROM_AKBIN             0xfe5520   /* (evb): a queued key taken (dq) and completed, else onto the CDA's keyboard wait */
#define AES_ROM_ADELAY            0xfe5566   /* (evb, ticks): the countdown re-armed under spl7, the EVB into the delta list */
#define AES_ROM_ABUTTON           0xfe55f8   /* (evb, wanted): downorup now → completed, else onto the CDA's button wait */
#define AES_ROM_AMOUSE            0xfe5666   /* (evb, moblk): already in/out as asked → completed, else onto the mouse wait */
#define AES_ROM_EV_RETS           0xfe681a   /* (answers): the mouse (the click's own when one was counted), buttons, shift keys */
#define AES_ROM_EV_MCHK           0xfe695c   /* (moblk): D0 = rlr owns the mouse and it is where the MOBLK asks */
#define AES_ROM_ACANCEL           0xfe427a   /* (mask): the running PD's EVBs of those events cancelled (ev_multi's tail) */
/* The event blocks' LISTS (gemasync and geminput's evremove, Alcyon, `aes/evasync.h`, read:). */
#define AES_ROM_SIGNAL            0xfe3f5e   /* (evb): its event posted to its PD; a PD parked on it moved to the woken list */
#define AES_ROM_AZOMBIE           0xfe3fba   /* (evb): onto the completed list, EVB_FLAG := complete, signal */
#define AES_ROM_GET_EVB           0xfe4002   /* (): the first free EVB taken and cleared, or 0 */
#define AES_ROM_EVINSERT          0xfe4030   /* (evb, list): at the head of a wait list */
#define AES_ROM_TAKEOFF           0xfe4062   /* (evb): off its wait list (a delay's ticks to its successor), freed */
#define AES_ROM_APRET             0xfe41bc   /* (mask): the running PD's completed EVB of that event freed, its answer */
#define AES_ROM_EVREMOVE          0xfe511a   /* (evb, answer): its answer kept, off its wait list, azombie */
/* ev_multi's Line-F RETURN word: its answers written, its waits cancelled — where a process the dispatcher switched to
 * comes out of the evnt_multi it was parked in. */
#define AES_ROM_EV_MULTI_RETURN   0xfe6c5c
#define AES_ROM_GSX2              0xfecb5a   /* the AES's one `trap #2` to the VDI */
/* The VDI BINDING (gemgsxif, hand 68000, `aes/gsx.h`): contrl filled, gsx2 reached; each wrapper read from its body. */
#define AES_ROM_GSX_NCODE         0xfe87d2   /* (opcode, points, words): contrl[0,1,3], the AES's handle, gsx2 */
#define AES_ROM_GSX_1CODE         0xfe87f0   /* (opcode, value): intin[0], then gsx_ncode(opcode, 0, 1) */
#define AES_ROM_GSX_MOFF          0xfe8a72   /* the AES's cursor hidden (v_hide_c) on the first of a nest */
#define AES_ROM_GSX_MON           0xfe8a8e   /* ...and shown again (v_show_c 1) when the nest unwinds */
#define AES_ROM_V_PLINE           0xfe8afa   /* (count, points): ptsin pointed at the caller's points for the call */
#define AES_ROM_VS_CLIP           0xfe8b0e   /* (flag, points) */
#define AES_ROM_VST_HEIGHT        0xfe8b22   /* (height, &w, &h, &cell w, &cell h): ptsout's four words out */
#define AES_ROM_VR_RECFL          0xfe8b50   /* (points, mfdb) */
#define AES_ROM_VRO_CPYFM         0xfe8b60   /* (mode, points, source mfdb, destination mfdb) */
#define AES_ROM_VRT_CPYFM         0xfe8b72   /* (mode, points, source, destination, foreground, background) */
#define AES_ROM_VRN_TRNFM         0xfe8b88   /* (source mfdb, destination mfdb) */
#define AES_ROM_VSL_WIDTH         0xfe8b92   /* (width): ptsin[0..1] = width, 0 */
#define AES_ROM_GSX_FIX           0xfda992   /* (mfdb, address, bytes across, height): an MFDB, 0 the screen's */
/* ...and the rest of gemgsxif (`aes/gsxif.h`), each read from its body. */
#define AES_ROM_GSX_MALLOC        0xfe8790   /* gl_tmp the screen's MFDB, its buffer Malloc'd ($3400) */
#define AES_ROM_GSX_MFREE         0xfe87b0   /* ...Mfree'd */
#define AES_ROM_GSX_MRET          0xfe87bc   /* (&address, &length): gl_tmp's buffer and gl_mlen out */
#define AES_ROM_GSX_INIT          0xfe8808   /* gsx_wsopen, gsx_start, the AES's mouse routines, vq_mouse */
#define AES_ROM_GSX_GRAPHIC       0xfe8828   /* (graphic): escape 2 + the AES's mouse routines, or escape 3 + the old */
#define AES_ROM_GSX_SETMB_AES     0xfe883e   /* gsx_setmb(button glue, motion glue, &drwaddr): gsx_graphic's tail */
#define AES_ROM_GSX_ESCAPES       0xfe8866   /* (escape): contrl[5], VDI 5 */
#define AES_ROM_GSX_WSOPEN        0xfe8876   /* v_opnwk on gl_restype; gl_restype from the size answered */
#define AES_ROM_GSX_WSCLOSE       0xfe88de   /* v_clswk */
#define AES_ROM_RATINIT           0xfe88e4   /* v_show_c(0); the hide nest 0 */
#define AES_ROM_BB_SET            0xfe88f8   /* (x, y, w, h, pts1, pts2, mfdb, src, dst): a word-aligned vro_cpyfm */
#define AES_ROM_BB_SAVE           0xfe8966   /* (rect): the screen under it into gl_tmp */
#define AES_ROM_BB_RESTORE        0xfe8996   /* (rect): ...and back */
#define AES_ROM_GSX_SETMB         0xfe89c6   /* (button, motion, &drwaddr): vex_butv, vex_motv, the old ones kept */
#define AES_ROM_GSX_RESETMB       0xfe89f8   /* ...the old ones put back */
#define AES_ROM_GSX_TICK          0xfe8a18   /* (routine, &old): vex_timv; intout[0] answered */
#define AES_ROM_GSX_MFSET         0xfe8a38   /* (form): the cursor hidden, 37 words into intin, vsc_form, shown */
#define AES_ROM_GSX_MXMY          0xfe8a54   /* (&x, &y): xrat, yrat */
#define AES_ROM_GSX_BUTTON        0xfe8a6a   /* the buttons' word */
#define AES_ROM_V_OPNWK           0xfe8aae   /* (work_in, &handle, work_out): the block's arrays for the one call */
#define AES_ROM_GSX_START         0xfdaab0   /* the caches, the clip, the screen's metrics and GRECTs */
#define AES_ROM_GSX_MFSAVE        0xfee498   /* `$a000`; the Line-A mouse form saved */
#define AES_ROM_GSX_MFRESTORE     0xfee4c0   /* ...and copied back */
/* The AES's interrupt GLUE: ROM code the AES hands the VDI as VALUES and never calls (`test_aes_rom_data.py` lists
 * each). Each parks the interrupted SP and runs on a stack of the AES's own: the button and motion glue on $94f2 (SP
 * in $9482), saving D0-D2/A0-A2 around one call; the tick glue on $9552 (SP in $9486), then chaining on. */
#define AES_ROM_BUTTON_GLUE       0xfed3be   /* vex_butv's routine: b_click(D0) called directly ($fe4f40)
                                                ($fe884a pea, gsx_setmb_aes) */
#define AES_ROM_MOTION_GLUE       0xfed3e4   /* vex_motv's: forkq(mchange, D0, D1) ($fe8844 pea, gsx_setmb_aes) */
#define AES_ROM_TICK_GLUE         0xfed426   /* vex_timv's: while a count is set ($9492) it counts the ticks ($948e)
                                                down and at zero forkq(tchange, elapsed); then b_delay(1) ($fe4fb0)
                                                always, the interrupted SP back, and `jsr` to the routine displaced
                                                ($948a) ($fd9f92 lea, into $947e by gem_entry) */
/* The GRAPHICS LIBRARY (gemgraf, hand 68000, `aes/gemgraf.h`), each read from its body; gr_movebox, gr_growbox and
 * gr_shrinkbox are the dispatcher's AES_ROM_GR_* below. */
#define AES_ROM_GR_INSIDE         0xfda56e   /* (rect, thickness): shrunk by it on every side */
#define AES_ROM_GR_RECT           0xfda582   /* (colour, pattern, rect): vsf_color, bb_fill in replace mode */
#define AES_ROM_GR_JUST           0xfda5c2   /* (just, font, text, w, h, rect): gsx_tcalc, the corner justified; D0 the count */
#define AES_ROM_GR_GTEXT          0xfda62c   /* (just, font, text, rect): a copy of rect justified, gsx_tblt */
#define AES_ROM_GR_CRACK          0xfda66a   /* (colour, &border, &text, &pattern, &interior, &mode) */
#define AES_ROM_GR_GICON          0xfda6c4   /* (state, mask, data, text, char, cx, cy, icon rect, text rect) */
#define AES_ROM_GR_BOX            0xfda7a4   /* (x, y, w, h, thickness): gr_inside + gsx_box per line */
#define AES_ROM_GSX_SCLIP         0xfda7f8   /* (rect): the clip words, vs_clip; D0 = 1 */
#define AES_ROM_GSX_GCLIP         0xfda846   /* (rect): the clip words out */
#define AES_ROM_GSX_CHKCLIP       0xfda864   /* (rect): D0 = 1 when it touches the clip, or the clip is empty */
#define AES_ROM_GSX_CLINE         0xfda8d2   /* (x1, y1, x2, y2): v_pline over its own frame, the cursor hidden */
#define AES_ROM_GSX_ATTR          0xfda8e6   /* (text, mode, colour): vswr_mode, vst_color or vsl_color through caches */
#define AES_ROM_GSX_BXPTS         0xfda956   /* (rect): its five corners into ptsin */
#define AES_ROM_GSX_BOX           0xfda97c   /* (rect): v_pline of gsx_bxpts' corners */
#define AES_ROM_GSX_BLT           0xfda9ce   /* (src, sx, sy, swb, dst, dx, dy, dwb, w, h, rule, fg, bg) */
#define AES_ROM_BB_SCREEN         0xfdaa48   /* (rule, sx, sy, dx, dy, w, h): gsx_blt screen to screen */
#define AES_ROM_GSX_TRANS         0xfdaa6a   /* (src, swb, dst, dwb, h): vrn_trnfm of a standard form */
#define AES_ROM_BB_FILL           0xfdac28   /* (mode, interior, style, x, y, w, h): vr_recfl through the caches */
#define AES_ROM_GSX_TCALC         0xfdaca4   /* (font, text, &w, &h, &count): xstrpix into intin, its size */
#define AES_ROM_GSX_TBLT          0xfdad0a   /* (font, x, y, count): the font set, v_gtext of intin */
#define AES_ROM_GSX_XBOX          0xfdada4   /* (rect): a dotted box */
#define AES_ROM_GSX_XCBOX         0xfdadce   /* (rect): ...its four corners */
#define AES_ROM_GSX_XLINE         0xfdae38   /* (count, points): dotted lines, the dots in step with the screen's */
/* ...and the box animations' helpers (gemgrlib, hand 68000): the names GEM's sources give them. */
#define AES_ROM_GR_SETUP          0xfe85b0   /* (colour): the clip the screen, XOR */
#define AES_ROM_GR_SCALE          0xfe8472   /* (dx, dy, &count, &xstep, &ystep): gr_setup, the steps */
#define AES_ROM_GR_STEPCALC       0xfe82e6   /* (w, h, rect, &cx, &cy, &count, &xstep, &ystep): centred, gr_scale */
#define AES_ROM_GR_XOR            0xfe83be   /* (corners, count, x, y, w, h, xstep, ystep, grows): stepped XOR boxes */
/* ...and the wait gr_watchbox loops on, which reaches the event layer through `aes/evdoor.h` (hand 68000, the name
 * GEM's sources give it; entered by `bsr` and by Line-F `$f0b0`). */
#define AES_ROM_GR_STILLDN        0xfe8508   /* (out, x, y, w, h): ev_multi(BUTTON|M1) over its own frame; 1 = no rise */
/* ...and the drag loops' own helpers (hand 68000, `aes/grdrag.h`; the names GEM's sources give them), each read from
 * its body: gr_wait (Line-F `$f0c4`, folding gr_draw $fe8532 and gr_xdraw $fe8564, both reached by `bsr` alone),
 * gr_rubwind (`bsr` from gr_rubbox, Line-F `$f790` from the control manager) and gr_clamp (Line-F `$f0c0`, folding its
 * fragment $fe86c2). */
#define AES_ROM_GR_WAIT           0xfe8576   /* (po, poff, mx, my): the box XORed (two unless poff is gl_rzero's), gr_stilldn */
#define AES_ROM_GR_RUBWIND        0xfe85de   /* (x, y, wmin, hmin, poff, &w, &h): the screen locked, gr_clamp/gr_wait */
#define AES_ROM_GR_CLAMP          0xfe86dc   /* (x, y, wmin, hmin, &w, &h): the mouse's distance + 1, at least the min */
/* The MENU LIBRARY's own helpers (gemmnlib, Alcyon, `aes/mnlib.h`), each read from its body. */
#define AES_ROM_RECT_CHANGE       0xfe8bf4   /* (tree, moblk, obj, leave): an object's rectangle into a MOBLK */
#define AES_ROM_MENU_SET          0xfe8c7a   /* (tree, last, cur, set): do_chg(last, SELECTED) unless -1 or cur */
#define AES_ROM_MENU_SR           0xfe8cb6   /* (save, tree, menu): the screen under a drop-down saved or restored */
#define AES_ROM_MENU_DOWN         0xfe8cf4   /* (tree, title): the title selected, its drop-down saved and drawn */
#define AES_ROM_MN_DO             0xfe8d6e   /* (&title, &item): the mouse tracked through the bar until a click */
#define AES_ROM_MN_CLSDA          0xfe91a4   /* (): AC_CLOSE sent to every registered accessory */
/* ...and the scheduler's leaf mn_register names a process with (Alcyon, read:), and the event layer's button post
 * mn_bar reaches through the event door (`aes/evdoor.h`; Alcyon, read:). */
#define AES_ROM_PD_NAMEIT         0xfe5856   /* (pd, name): the PD's name blank-filled, the name copied up to '.' */
#define AES_ROM_POST_BUTTON       0xfe52e2   /* (pd, button, clicks): each of pd's button waits it satisfies woken */
/* The event door's other first users: the window library's message sender and the control manager's mouse grab. */
#define AES_ROM_AP_SENDMSG        0xfebdbe   /* (buffer, type, to, five words): the message built, ap_rdwr(AQWRT, to, 16) */
#define AES_ROM_CT_MOUSE          0xfe4a98   /* (grab): the mouse form saved and the arrow shown, or the form put back */
/* ...and the scheduler's and control manager's routines the window library reaches through the door (Alcyon, read:). */
#define AES_ROM_TAK_FLAG          0xfe4e5a   /* (spb): the semaphore taken if free or the running PD's, D0 = got it */
#define AES_ROM_UNSYNC            0xfe4eb8   /* (spb): given up; at count 0 handed to its first wait, dsptch */
#define AES_ROM_EV_BLOCK          0xfe6874   /* (code, parameter): one EVB queued by iasync, ev_mwait, its event */
#define AES_ROM_CT_CHGOWN         0xfe49ba   /* (pd, rect): set_ctrl(rect), the mouse and keyboard to pd */
/* The CONTROL MANAGER's leaves (Alcyon, `aes/wmupdate.h`), each read from its body. */
#define AES_ROM_SET_CTRL          0xfe5008   /* (rect): the control rectangle copied in */
#define AES_ROM_GET_CTRL          0xfe501c   /* (rect): ...and out */
#define AES_ROM_GET_MOWN          0xfe5030   /* (&mouse, &keyboard): the two owners copied out */
/* The form manager's hold on the screen (Alcyon, `aes/wmupdate.h`): the lock, the menu and the mouse taken. */
#define AES_ROM_FM_OWN            0xfe718e   /* (take): nested; the first take saves and hands the screen to rlr */
/* The form library's event-free half (Alcyon, `aes/fmlib.h`, read:), and the event layer's keyboard-queue leaves fm_do
 * flushes the queue with (Alcyon, read:; non-blocking). */
#define AES_ROM_FM_STRBRK         0xfe6c98   /* (tree, str, obj, &idx, &n, &maxlen): one ']' section into ob_specs */
#define AES_ROM_FM_PARSE          0xfe6d84   /* (tree, str, &icon, &nmsg, &mlen, &nbut, &blen): an alert string split */
#define AES_ROM_FM_BUILD          0xfe6df8   /* (tree, icon, nmsg, mlen, nbut, blen): the alert tree laid out */
#define AES_ROM_FIND_OBJ          0xfe7214   /* (tree, start, which): the next/previous EDITABLE, or the first DEFAULT */
#define AES_ROM_FM_INIFLD         0xfe727a   /* (tree, fld): fld, or for 0 the first EDITABLE */
#define AES_ROM_DQ                0xfe50ca   /* (queue): the front key taken off and answered */
#define AES_ROM_FQ                0xfe50f8   /* (): the running process's key queue emptied */
/* PROCESSES AND THEIR PIPES (Alcyon, `aes/pdpipe.h`, read:), and gemdosif's two hand-68000 leaves under pstart. */
#define AES_ROM_PD_MATCH          0xfe56f6   /* ctx name; read: (name, pid, pd): pd's name is `name`, or with none its id is pid */
#define AES_ROM_FPDNM             0xfe5750   /* (name, pid): the PD pd_match finds — three static, then the accessories' */
#define AES_ROM_GETPD             0xfe57e0   /* (): the next PD — a static one, else an accessory's — its id set, in super */
#define AES_ROM_PSTART            0xfe5886   /* (code, name, ldaddr): getpd, named, psetup(code), onto the woken list */
#define AES_ROM_DOQ               0xfe58c0   /* (write, pd, qpb): qpb's bytes into pd's pipe (a redraw merged) or out of it */
#define AES_ROM_AQUEUE            0xfe5988   /* (write, evb, qpb): doq if it can and the other end's first wait served; else queued */
#define AES_ROM_UDA_INSUPER       0xfe3970   /* (uda): hand 68000 — UDA_IN_SUPER := 1 */
#define AES_ROM_PSETUP            0xfe397a   /* (pd, pc): hand 68000 — an rte frame (pc, SR $2000) pushed on pd's own stack */
/* The form library's half that waits on the user, and its alerts (Alcyon, `aes/fmdo.h`, read:), and the bell fm_do rings
 * (hand 68000 beside the GEMDOS glue). */
#define AES_ROM_FM_SHOW           0xfe764c   /* (string, values, default): an AES string, merged, as an alert */
#define AES_ROM_ERALERT           0xfe768c   /* (error, drive): the critical error handler's alert; 1 to retry */
#define AES_ROM_BELL              0xfe3a0c   /* (): BIOS Bconout(CON:, BEL) */
/* The utility layer's MEMORY and STRING helpers (hand 68000, `aes/strings.h`), each named from its body. */
#define AES_ROM_MUL_DIV           0xfecb6e   /* m1 * m2 / d, rounded: `muls.w` by 2*m2, `divs.w`, +-1, `asr.w` */
#define AES_ROM_SET_CONTRL_PTR    0xfecbc6   /* contrl[7..8] := the argument */
#define AES_ROM_GET_CONTRL_PTR2   0xfecbda   /* *answer := contrl[9..10] */
#define AES_ROM_LSTCPY            0xfecbe6   /* (dst, src): copy with the NUL, D0.w = the length counted in a BYTE */
#define AES_ROM_XSTRPIX           0xfecbfa   /* (dst, src): a string's bytes as words, no NUL, D0 = count (a byte) */
#define AES_ROM_WSET              0xfecc12   /* (dst, count, value): count words, none for 0 (no caller) */
#define AES_ROM_XSTRPIX_N         0xfecc28   /* (dst, src, count): count bytes as words, 65536 for 0 (no caller) */
#define AES_ROM_WCOPY             0xfecc40   /* (dst, src, count): count words, none for 0 */
#define AES_ROM_WFILL             0xfecc56   /* (dst, count, value): its guard tests the VALUE (no caller) */
#define AES_ROM_LSTRLEN           0xfecc6c   /* a string's length, a word (count, then test) */
#define AES_ROM_LBCOPY            0xfecc7e   /* (dst, src, count): memmove, the direction a SIGNED compare */
#define AES_ROM_MOVS              0xfece2e   /* (count, src, dst): count bytes forward (`dbf`) */
#define AES_ROM_MIN               0xfece42   /* the smaller signed word */
#define AES_ROM_MAX               0xfece4e   /* the larger signed word */
#define AES_ROM_BFILL             0xfece5e   /* (count, byte, dst): count bytes (`dbf`) */
#define AES_ROM_TOUPPER           0xfece74   /* a-z less 32, every other byte sign-extended */
#define AES_ROM_STRLEN            0xfece8c   /* a string's length, a word (test, then count) */
#define AES_ROM_STREQ             0xfece9c   /* 1 when two strings are equal, through the shared tails */
#define AES_ROM_STRCPY            0xfeceb8   /* (src, dst): copy with the NUL, D0 = dst past the NUL */
#define AES_ROM_STRSCN            0xfecec4   /* (src, dst, stop): copy up to stop or the NUL, D0 = dst's end */
#define AES_ROM_STRCAT            0xfeceda   /* (src, dst): src after dst's NUL, D0 = dst past the new NUL */
#define AES_ROM_SCASB             0xfeceee   /* (string, byte): the byte's first place or the NUL's (desk-only) */
#define AES_ROM_STRCHK            0xfecf02   /* the signed byte difference where two strings first differ, or 0 */
#define AES_ROM_FMT_STR           0xfecf24   /* "NAME.EXT" -> the 8.3 form "NAME    EXT" */
#define AES_ROM_UNFMT_STR         0xfecf58   /* ...and back: spaces dropped, the dot put back */
#define AES_ROM_MERGE_STR         0xfed070   /* (dst, template, parameters): %L %W %S %% into a string */
#define AES_ROM_WILDCMP           0xfed12e   /* 1 when a name matches a `*`/`?` pattern */
/* The Alcyon runtime merge_str calls by `jsr` (compiled C: link/unlk, no Line-F). */
#define AES_ROM_LMUL              0xfe3db4   /* the signed 32x32 multiply, low long in D0 */
#define AES_ROM_LDIV              0xfe3e08   /* the signed 32/32 divide: quotient in D0, remainder at $8c3e */
/* The DESKTOP.INF field helpers the AES's `#E` reader and the desk share (Alcyon C, `aes/infscan.h`). */
#define AES_ROM_HEX_DIG           0xfdaf20   /* a hex digit's value, 0 for no digit (upper case only) */
#define AES_ROM_UHEX_DIG          0xfdaf5c   /* a value's upper-case hex digit, ' ' past 15 */
#define AES_ROM_SCAN_2            0xfdaf92   /* (cursor, &value): two hex digits, "ff" -> -1; D0.l = cursor + 3 */
#define AES_ROM_SAVE_2            0xfdafca   /* (cursor, value): two hex digits and ' '; D0.l = cursor + 3 */
/* The utility layer both the AES and the desk call ("optimize": hand 68000 and a little Alcyon C). */
#define AES_ROM_R_GET             0xfecca6   /* hand 68000: a GRECT's four words out through four pointers */
#define AES_ROM_R_SET             0xfeccbe   /* hand 68000: a GRECT := four frame words, as two longwords */
#define AES_ROM_RC_COPY           0xfeccca   /* hand 68000: (from, to) two longwords */
#define AES_ROM_INSIDE            0xfeccd6   /* hand 68000: (x, y, rect) D0 = the point is in it, through the shared tails */
#define AES_ROM_RC_EQUAL          0xfecd0c   /* hand 68000: D0 = two GRECTs equal (`cmpm.l` twice), through the tails */
#define AES_ROM_RC_INTERSECT      0xfecd22   /* hand 68000: the intersection into the second GRECT, D0 = non-empty */
#define AES_ROM_RC_UNION          0xfecd8c   /* hand 68000: (from, into) into grown to cover from */
#define AES_ROM_RC_CONSTRAIN      0xfecde4   /* hand 68000: (container, rect) rect moved to lie inside container */
#define AES_ROM_RC_RETURN_FALSE   0xfed066   /* the helpers' shared tails, WORD writes (D0.hi is the caller's): `clr.w d0 / bra.s` the rts ... */
#define AES_ROM_RC_RETURN_TRUE    0xfed06a   /* ...and `move.w #1,d0 / rts` */
#define AES_ROM_RC_RETURN_D0      0xfed06e   /* ...and their bare `rts`, D0 as left: strlen's `beq.w` ($fece94), $fed03a's */
#define AES_ROM_FS_SSET           0xfecf84   /* (tree, obj, text, &ptext, &txtlen): text INTO the TEDINFO's */
#define AES_ROM_INF_SSET          0xfecfb2   /* Alcyon: (tree, obj, text) fs_sset with its answers in its locals */
#define AES_ROM_FS_SGET           0xfecfd6   /* (tree, obj, text): the TEDINFO's text OUT into text */
#define AES_ROM_INF_FLDSET        0xfecfee   /* (tree, obj, field, bits, set, clear): ob_state from a flag test */
#define AES_ROM_INF_GINDEX        0xfed010   /* (tree, first, count): the first SELECTED of a run, -1 none */
#define AES_ROM_INF_WHAT          0xfed03a   /* (tree, ok, cancel): 1 OK, 0 the next, -1 neither; its state cleared */
#define AES_ROM_OB_ADDR           0xfed18e   /* hand 68000: A0 += tree + 24 * obj (its field offset) */
#define AES_ROM_OB_SST            0xfed19e   /* Alcyon: an object's spec, state, type, flags, rectangle and border */
#define AES_ROM_EVERYOBJ          0xfed27c   /* Alcyon: a depth-first walk calling `jsr (a0)` per object */
#define AES_ROM_GET_PAR           0xfed382   /* Alcyon: an object's parent, -1 for the root */
/* The RECTANGLE LISTS (gemrlist, all Alcyon): the ORECT pool's free list, and a window's visible rectangles cut. */
#define AES_ROM_OR_START          0xfe5a62   /* every ORECT of the pool onto an emptied free list, the last on top */
#define AES_ROM_GET_ORECT         0xfe5aac   /* the free list's head, unlinked; 0 when the list is empty */
#define AES_ROM_MKPIECE           0xfe5acc   /* one piece of a rectangle the cut leaves: above, left, right or below it */
#define AES_ROM_BRKRCT            0xfe5ba8   /* a listed rectangle the cut overlaps replaced by its pieces, and freed */
#define AES_ROM_MKRECT            0xfe5c9a   /* everyobj's callback: one window's list cut by the rectangle newrect set */
#define AES_ROM_NEWRECT           0xfe5cee   /* everyobj's callback too: a window's list rebuilt, the windows before it cut */
/* A WINDOW's rectangles (gemwmlib, Alcyon). */
#define AES_ROM_W_GETXPTR         0xfeb4be   /* the address of a window's rectangle by WS_* (switch table $fefcca) */
#define AES_ROM_W_GETSIZE         0xfeb53e   /* a window's rectangle copied out; WS_TRUE's grown by its border */
/* The WINDOW LIBRARY (gemwmlib, Alcyon, `aes/wmlib.h`): the gadget tree built and drawn, the window records kept. */
#define AES_ROM_W_NILIT           0xfeb3c0   /* (count, objects): each one's next, head and tail -1 */
#define AES_ROM_W_OBADD           0xfeb408   /* (objects, parent, child): ob_add's body over a bare object array */
#define AES_ROM_W_SETUP           0xfeb47a   /* (pd, window, kind): a window record claimed */
#define AES_ROM_W_SETSIZE         0xfeb57c   /* (which, window, rect): a window's rectangle copied in */
#define AES_ROM_W_ADJUST          0xfeb594   /* (parent, obj, x, y, w, h): a gadget placed and added to W_ACTIVE */
#define AES_ROM_W_HVASSIGN        0xfeb5f8   /* (isvert, parent, obj, vx, vy, hx, hy, w, h): w_adjust, one bar's way */
#define AES_ROM_W_CLIPDRAW        0xfeb646   /* (window, tree, obj, depth, clip): ob_draw per visible rectangle */
#define AES_ROM_W_DRAWDESK        0xfeb6c8   /* (rect): the desktop drawn under a rectangle, grown by the border */
#define AES_ROM_W_CPWALK          0xfeb712   /* (window, obj, depth, usetrue): a window's gadgets built and drawn */
#define AES_ROM_W_STRCHG          0xfeb768   /* (window, obj, text): a title or information line set and drawn */
#define AES_ROM_W_BARCALC         0xfeb7ca   /* (isvert, space, value, size, min, &v, &h): a slider's elevator */
#define AES_ROM_W_BLDBAR          0xfeb84e   /* (kind, istop, bar, value, size, x, y, w, h): a scroll bar built */
#define AES_ROM_W_BLDACTIVE       0xfeba9c   /* (window): the gadget tree W_ACTIVE built for a window */
#define AES_ROM_W_MVFIX           0xfebece   /* (from, to): a rectangle clipped to the desktop, its left edge fixed */
#define AES_ROM_W_MOVE            0xfebf00   /* (window, &stop, rect): a moved window's image blitted, the gap out */
#define AES_ROM_W_OWNS            0xfec39a   /* (window, orect, rect, out): the next visible rectangle over rect */
#define AES_ROM_W_UNION           0xfec3ea   /* (orect, rect): the bounding box of a rectangle list */
/* ...and its half that reaches the event layer (Alcyon, `aes/wmupdate.h`). */
#define AES_ROM_W_SETACTIVE       0xfeba54   /* (): the top window's owner given the mouse, its work area the control */
#define AES_ROM_W_REDRAW          0xfebe2a   /* (window, rect): a WM_REDRAW of what of rect it shows, to its owner */
#define AES_ROM_W_UPDATE          0xfec026   /* (bottom, rect, top, moved): windows top..bottom redrawn under rect */
#define AES_ROM_DRAW_CHANGE       0xfec0ca   /* (window, rect): a window moved, sized or topped, and drawn */
#define AES_ROM_WM_OPCL           0xfec676   /* (window, rect, add): added to or taken out of the window tree */
#define AES_ROM_WM_START          0xfec424   /* (): the window library set up, the desktop window 0 */
/* The OBJECT LIBRARY's own helpers (gemoblib, all Alcyon, laid out after ob_change in the source's order). */
#define AES_ROM_OB_FS             0xfea4b6   /* an object's flags into a word, its state answered */
#define AES_ROM_OB_ACTXYWH        0xfea4e8   /* an object's GRECT on the screen: ob_offset, then its width and height */
#define AES_ROM_OB_RELXYWH        0xfea538   /* an object's GRECT as it stands, relative to its parent: wcopy out */
#define AES_ROM_OB_SETXYWH        0xfea55e   /* ...and set from a GRECT: wcopy in */
#define AES_ROM_GET_PREV          0xfea5dc   /* the sibling before an object, -1 when it is its parent's head */
/* The OBJECT DRAW PATH (gemobjop/gemoblib, Alcyon, `aes/objdraw.h`). */
#define AES_ROM_JUST_DRAW         0xfe9a88   /* read: (tree, obj, x, y) one object drawn — ob_draw's everyobj routine */
#define AES_ROM_OB_FORMAT         0xfe99a4   /* read: (just, raw, tmplt, out) an editable text's raw text merged into its template */
#define AES_ROM_OB_USER           0xfe9a46   /* read: (tree, obj, rect, userblk, curr, new) a USERDEF's routine over a PARMBLK */
#define AES_ROM_FAR_CALL          0xfddec6   /* read: (code, parm) `jsr` to code over one pushed longword, its D0 answered */
/* The OBJECT EDITOR (gemobed, Alcyon, `aes/obedit.h`): ob_edit's helpers, in the ROM's order. */
#define AES_ROM_OB_GETSP          0xfe9260   /* read: (tree, obj, ted) the object's TEDINFO copied, an INDIRECT spec followed */
#define AES_ROM_SCAN_TO_END       0xfe9352   /* read: (tmplt, idx, chr) the index advanced past the template's placeholders up to chr */
#define AES_ROM_INS_CHAR          0xfe937e   /* read: (str, pos, chr, room) a character inserted, the string ended within room */
#define AES_ROM_FIND_POS          0xfe93da   /* read: (tmplt, idx) the template place of raw character idx */
#define AES_ROM_PXL_RECT          0xfe941c   /* read: (tree, obj, pos, rect) the screen cell of a template place */
#define AES_ROM_CURFLD            0xfe948a   /* read: (tree, obj, pos, n) the XOR cursor, or n cells of the field redrawn */
#define AES_ROM_INSTR             0xfe9516   /* read: (chr, set) 1 when chr is in a set of characters and a..z ranges */
#define AES_ROM_CHECK             0xfe9556   /* read: (&chr, valid) a typed character validated, upcased in place */
#define AES_ROM_OB_STFN           0xfe95f2   /* read: (idx, &start, &finish) the template places of idx and the raw end */
#define AES_ROM_OB_DELIT          0xfe962a   /* read: (idx) the raw text's character at idx deleted; 1 at its end */
/* The functions the dispatcher's arms call (`ctx` names: see above). */
#define AES_ROM_AP_RDWR           0xfe65c4   /* read: (code, pid, length, buffer) ev_block(code, its own frame +10) */
#define AES_ROM_AP_RDWR_OPCODE    12
#define AES_ROM_AP_FIND           0xfe65da   /* read: (name) copied into the frame, fpdnm by name: its id, or -1 */
#define AES_ROM_AP_FIND_OPCODE    13
#define AES_ROM_AP_TPLAY          0xfe6610   /* ctx */
#define AES_ROM_AP_TPLAY_OPCODE   14
#define AES_ROM_AP_TRECD          0xfe6766   /* ctx */
#define AES_ROM_AP_TRECD_OPCODE   15
#define AES_ROM_EV_KEYBD          0xfe6894   /* ctx */
#define AES_ROM_EV_KEYBD_OPCODE   20
#define AES_ROM_EV_BUTTON         0xfe68a4   /* read: (clicks, mask, state, &rets): ev_block(7), then the mouse into rets */
#define AES_ROM_EV_BUTTON_OPCODE  21
#define AES_ROM_EV_MOUSE          0xfe68e4   /* ctx */
#define AES_ROM_EV_MOUSE_OPCODE   22
#define AES_ROM_EV_MESAG          0xfe6910   /* ctx */
#define AES_ROM_EV_MESAG_OPCODE   23
#define AES_ROM_EV_TIMER          0xfe6936   /* ctx */
#define AES_ROM_EV_TIMER_OPCODE   24
#define AES_ROM_EV_MULTI          0xfe6998   /* read: (flags, mouse 1, mouse 2, timer, button, message, answers) */
#define AES_ROM_EV_MULTI_OPCODE   25
#define AES_ROM_EV_DCLICK         0xfe6c5e   /* ctx */
#define AES_ROM_EV_DCLICK_OPCODE  26
#define AES_ROM_MN_BAR            0xfe902a   /* read: (tree, show): the bar set up and drawn, or none; post_button */
#define AES_ROM_MN_BAR_OPCODE     30
#define AES_ROM_DO_CHG            0xfe8c14   /* read: (tree, item, bits, set, redraw, chkdis): menu_icheck/ienable/tnormal */
#define AES_ROM_DO_CHG_OPCODE     31
#define AES_ROM_DO_CHG_OPCODE_32  32
#define AES_ROM_DO_CHG_OPCODE_33  33
#define AES_ROM_MN_REGISTER       0xfe91e2   /* read: (pid, name): an accessory's slot, or -1 the caller's name */
#define AES_ROM_MN_REGISTER_OPCODE 35
#define AES_ROM_OB_ADD            0xfea1ba   /* read: a child linked in as its parent's last */
#define AES_ROM_OB_ADD_OPCODE     40
#define AES_ROM_OB_DELETE         0xfea21e   /* read: an object unlinked from its parent's children */
#define AES_ROM_OB_DELETE_OPCODE  41
#define AES_ROM_OB_DRAW           0xfea028   /* read: (tree, obj, depth) a subtree drawn by everyobj, just_draw per object */
#define AES_ROM_OB_DRAW_OPCODE    42
#define AES_ROM_OB_FIND           0xfea0a8   /* read: the deepest visible object under a point, -1 for none */
#define AES_ROM_OB_FIND_OPCODE    43
#define AES_ROM_OB_OFFSET         0xfea584   /* read: the object's screen position, the sum of its and its ancestors' */
#define AES_ROM_OB_OFFSET_OPCODE  44
#define AES_ROM_OB_ORDER          0xfea2be   /* read: an object moved to a place among its siblings */
#define AES_ROM_OB_ORDER_OPCODE   45
#define AES_ROM_OB_EDIT           0xfe9678   /* read: (tree, obj, key, &idx, kind) an editable field's key edited in */
#define AES_ROM_OB_EDIT_OPCODE    46
#define AES_ROM_OB_CHANGE         0xfea38e   /* read: (tree, obj, new, redraw) a state set, SELECTED inverted or redrawn */
#define AES_ROM_OB_CHANGE_OPCODE  47
#define AES_ROM_FM_DO             0xfe74a4   /* read: (tree, start): fields edited, keys and clicks until an exit */
#define AES_ROM_FM_DO_OPCODE      50
#define AES_ROM_FM_DIAL           0xfe75ec   /* read: (type, little, big): grown, shrunk, or the screen redrawn */
#define AES_ROM_FM_DIAL_OPCODE    51
#define AES_ROM_FM_ALERT          0xfe7002   /* read: (default, string): tree 1 laid out, drawn, fm_do; the button */
#define AES_ROM_FM_ALERT_OPCODE   52
#define AES_ROM_FM_ERROR          0xfe7712   /* read: (code): an MS-DOS error's alert, 0 past 63; 0 for its first button */
#define AES_ROM_FM_ERROR_OPCODE   53
#define AES_ROM_OB_CENTER         0xfe92ae   /* read: form_center, a tree's root centred on the screen */
#define AES_ROM_OB_CENTER_OPCODE  54
#define AES_ROM_FM_KEYBD          0xfe7298   /* read: (tree, obj, &key, &next): a tab/arrow to a field, Return to the default */
#define AES_ROM_FM_KEYBD_OPCODE   55
#define AES_ROM_FM_BUTTON         0xfe7346   /* read: (tree, obj, clicks, &next): a click taken, radio, watched, exit */
#define AES_ROM_FM_BUTTON_OPCODE  56
#define AES_ROM_GR_RUBBOX         0xfe85c6   /* read: (x, y, wmin, hmin, &w, &h): gr_rubwind with poff gl_rzero */
#define AES_ROM_GR_RUBBOX_OPCODE  70
#define AES_ROM_GR_DRAGBOX        0xfe8640   /* read: (w, h, x, y, bound, &x, &y): the box dragged inside bound */
#define AES_ROM_GR_DRAGBOX_OPCODE 71
#define AES_ROM_GR_MOVEBOX        0xfe8402   /* read: (w, h, sx, sy, dx, dy) gr_scale, gr_xor drawn and undrawn */
#define AES_ROM_GR_MOVEBOX_OPCODE 72
#define AES_ROM_GR_GROWBOX        0xfe8340   /* read: (from, to); the arm's `movea.l #`, then the shared `jsr (a0)` ($fe622e) */
#define AES_ROM_GR_GROWBOX_OPCODE 73
#define AES_ROM_GR_SHRINKBOX      0xfe837a   /* read: (from, to) ...the same */
#define AES_ROM_GR_SHRINKBOX_OPCODE 74
#define AES_ROM_GR_WATCHBOX       0xfe84ba   /* read: (tree, obj, in, out) the state toggled until the button rises */
#define AES_ROM_GR_WATCHBOX_OPCODE 75
#define AES_ROM_GR_SLIDEBOX       0xfe86fa   /* read: (tree, parent, obj, vert): dragged; 0..1000 along it */
#define AES_ROM_GR_SLIDEBOX_OPCODE 76
#define AES_ROM_GR_MKSTATE        0xfe8768   /* read: xrat, yrat, the buttons, the shift state out through four pointers */
#define AES_ROM_GR_MKSTATE_OPCODE 79
#define AES_ROM_SC_READ           0xfeac80   /* read: scrp_read, the scrap path lstcpy'd out into the caller's */
#define AES_ROM_SC_READ_OPCODE    80
#define AES_ROM_SC_WRITE          0xfeac94   /* read: scrp_write, the caller's path lstcpy'd in as the scrap path */
#define AES_ROM_SC_WRITE_OPCODE   81
#define AES_ROM_FS_INPUT          0xfe7d90   /* (path, selection, &button): the file selector run until OK or Cancel; 1, or 0 for no memory */
#define AES_ROM_FS_INPUT_OPCODE   90
#define AES_ROM_WM_CREATE         0xfec602   /* read: (kind, rect): the first free window claimed, -1 for none */
#define AES_ROM_WM_CREATE_OPCODE  100
#define AES_ROM_WM_OPEN           0xfec6da   /* read: (window, rect): wm_opcl(window, rect, 1) */
#define AES_ROM_WM_OPEN_OPCODE    101
#define AES_ROM_WM_CLOSE          0xfec6f0   /* read: (window): wm_opcl(window, &gl_rzero, 0) */
#define AES_ROM_WM_CLOSE_OPCODE   102
#define AES_ROM_WM_DELETE         0xfec706   /* read: (window): its record freed */
#define AES_ROM_WM_DELETE_OPCODE  103
#define AES_ROM_WM_GET            0xfec722   /* read: (window, field, out): wind_get (switch table $fefcde) */
#define AES_ROM_WM_GET_OPCODE     104
#define AES_ROM_WM_SET            0xfec83a   /* read: (window, field, words): wind_set (switch table $fefd16) */
#define AES_ROM_WM_SET_OPCODE     105
#define AES_ROM_WM_FIND           0xfeca4a   /* read: (x, y): ob_find over the window tree */
#define AES_ROM_WM_FIND_OPCODE    106
#define AES_ROM_WM_UPDATE         0xfeca68   /* read: (code): the screen lock, or fm_own(code - 2) */
#define AES_ROM_WM_UPDATE_OPCODE  107
#define AES_ROM_WM_CALC           0xfecaac   /* read: (type, kind, x, y, w, h, &x, &y, &w, &h): a border added or taken */
#define AES_ROM_WM_CALC_OPCODE    108
#define AES_ROM_RS_LOAD           0xfeac5c   /* read: rs_readit, then the objects fixed (rs_fixit) if it read one */
#define AES_ROM_RS_LOAD_OPCODE    110
#define AES_ROM_RS_FREE           0xfeaa58   /* read: the caller's resource Mfree'd; whether GEMDOS took it */
#define AES_ROM_RS_FREE_OPCODE    111
#define AES_ROM_RS_GADDR          0xfeaa86   /* read: get_addr's answer stored through the answer pointer, and != -1 */
#define AES_ROM_RS_GADDR_OPCODE   112
#define AES_ROM_RS_SADDR          0xfeaab2   /* read: a longword stored at the address get_addr names */
#define AES_ROM_RS_SADDR_OPCODE   113
#define AES_ROM_RS_OBFIX          0xfea69c   /* read: an object's four coordinates from character cells to pixels */
#define AES_ROM_RS_OBFIX_OPCODE   114
/* The resource layer's internals (`src/aes/resource.c`), each read from its body: rsrc_gaddr's switch and the load's
 * relocation, which every rsrc_* call and the ROM's own resources' set-up reach. */
#define AES_ROM_FIX_CHPOS         0xfea622   /* one coordinate: low byte cells times the cell, high byte a pixel offset */
#define AES_ROM_RS_STR            0xfea6e6   /* free string n of the AES's own resource, copied to AES_RS_STRING */
#define AES_ROM_GET_SUB           0xfea716   /* element n of a header section: header + offset word + n * size */
#define AES_ROM_GET_ADDR          0xfea742   /* rsrc_gaddr's switch: the address of element n of a resource type */
#define AES_ROM_FIX_TRINDEX       0xfea86a   /* the tree table into global[5..6], every tree pointer relocated */
#define AES_ROM_FIX_OBJECTS       0xfea8bc   /* every object rs_obfix'd, its ob_spec relocated unless a colour */
#define AES_ROM_FIX_TEDINFO       0xfea918   /* every TEDINFO's three pointers relocated, its two lengths set */
#define AES_ROM_FIX_NPTRS         0xfea9d4   /* fix_ptr of one type over elements n..0 */
#define AES_ROM_FIX_PTR           0xfea9f8   /* fix_long of the address get_addr names */
#define AES_ROM_FIX_LONG          0xfeaa0a   /* an offset made an address by adding the header's; -1 left */
#define AES_ROM_RS_SGLOBAL        0xfeaa38   /* the caller's global[] and its header made the resource globals */
#define AES_ROM_DO_RSFIX          0xfeaba4   /* a resource read in relocated: every pointer but the objects' */
#define AES_ROM_RS_FIXIT          0xfeac4e   /* rs_sglobal, then fix_objects */
#define AES_ROM_DOS_ALLOC         0xfe3bba   /* Malloc: the size rounded up to even, 0 -> AES_DOS_ERR; the block too */
#define AES_ROM_DOS_FREE          0xfe3c26   /* Mfree through __DOS: both return addresses parked, AES_DOS_ERR/AX set */
#define AES_RS_FREE_MFREE_RETURN  0xfeaa76   /* rs_free's return site from dos_free: what AES_DOS_RETURN holds after */
#define AES_DOS_TRAP_RETURN       0xfe3c34   /* __DOS's caller's return site inside the glue: AES_TRAP1_RETURN's */
/* The rest of the glue the shell and the resource load reach, each read from its body: `__DOS` reached by `bsr`, so
 * AES_TRAP1_RETURN is parked with the return site inside the glue — or (dos_sdta, dos_close) through $fe3c28 as
 * dos_free is, its caller's return parked in AES_DOS_RETURN too. */
#define AES_ROM_DOS_SFIRST        0xfe3a1c   /* Fsfirst: 1 found; EFILNF or ENMFIL -> AES_DOS_AX 18 */
#define AES_ROM_DOS_OPEN          0xfe3a52   /* Fopen: the handle, or 0 on AES_DOS_ERR; EFILNF -> AES_DOS_AX 2 */
#define AES_ROM_DOS_READ          0xfe3a78   /* Fread of a WORD count, zero-extended */
#define AES_ROM_DOS_LSEEK         0xfe3a9a   /* Fseek (handle, mode, offset) */
#define AES_ROM_DOS_SDTA          0xfe3c06   /* Fsetdta through $fe3c28 */
#define AES_ROM_DOS_CLOSE         0xfe3c0a   /* Fclose through $fe3c28 */
#define AES_DOS_SFIRST_TRAP_RETURN 0xfe3a2a  /* dos_sfirst's `bsr __DOS` return: AES_TRAP1_RETURN's after it */
#define AES_DOS_OPEN_TRAP_RETURN  0xfe3a62   /* ...dos_open's */
#define AES_DOS_READ_TRAP_RETURN  0xfe3a94   /* ...dos_read's */
#define AES_DOS_LSEEK_TRAP_RETURN 0xfe3aaa   /* ...dos_lseek's */
/* The shell's file finding (`aes/shell.h`) and the resource load's read, each read from its body. */
#define AES_ROM_SH_NAME           0xfeae04   /* the name part of a path: past its last `\` or `:` */
#define AES_ROM_SH_PATH           0xfeaf1e   /* PATH's element n, `\` and the name after it, into a buffer; n + 1 */
#define AES_ROM_RS_READIT         0xfeaae2   /* a resource file found, read whole into a Malloc block, relocated */
#define AES_SH_FIND_SDTA_RETURN   0xfeafca   /* sh_find's return site from dos_sdta: what AES_DOS_RETURN holds after */
#define AES_RS_READIT_CLOSE_RETURN 0xfeaba0  /* rs_readit's return site from dos_close: the same */
#define AES_ROM_ROM_RAM           0xfee5c8   /* a part of the ROM's resources: copied, relocated on first use, or its global[] */
#define AES_ROM_ROM_RSC_INIT      0xfee4de   /* start-up: the ROM's resource bundle copied into a Malloc block, its parts' table set */
#define AES_ROM_SH_READ           0xfeaca8   /* read: shel_read, the shell's command line and tail out, 128 bytes each */
#define AES_ROM_SH_READ_OPCODE    120
#define AES_ROM_SH_WRITE          0xfeacd4   /* read: shel_write, both lines in and sh_main's requests set */
#define AES_ROM_SH_WRITE_OPCODE   121
#define AES_ROM_SH_GET            0xfead26   /* read: shel_get, `n` bytes of the shell's GEM buffer out */
#define AES_ROM_SH_GET_OPCODE     122
#define AES_ROM_SH_PUT            0xfead40   /* read: shel_put, `n` bytes into the shell's GEM buffer */
#define AES_ROM_SH_PUT_OPCODE     123
#define AES_ROM_SH_FIND           0xfeafbe   /* read: a file looked for as given, at the root, then down PATH */
#define AES_ROM_SH_FIND_OPCODE    124
#define AES_ROM_SH_ENVRN          0xfeae36   /* read: where a name's value starts in the environment, or 0 */
#define AES_ROM_SH_ENVRN_OPCODE   125
/* The file selector's event-free routines (`aes/fslib.h`), each read from its body — and the two pieces of the GEMDOS
 * glue fs_active reaches, with the return sites they park (the glue's own, and fs_active's through $fe3c28). */
#define AES_ROM_FS_START          0xfe7782   /* (): ad_fstree := the AES resource's tree 0, centred into gl_rfs */
#define AES_ROM_FS_BACK           0xfe77ae   /* (path, end): back from end to a `:` or `\`; a `\` put in after a `:` */
#define AES_ROM_FS_PSPEC          0xfe77ee   /* (path, end): past the last `\`; with none the path becomes "A:\*.*" */
#define AES_ROM_FS_ACTIVE         0xfe7826   /* (path, spec, &count): a directory read, filtered by spec, sorted */
#define AES_ROM_FS_1SCROLL        0xfe79fe   /* (top, count, arrow): the list's top one row up or down, bounded */
#define AES_ROM_FS_FORMAT         0xfe7a44   /* (tree, top, count): nine names into the list's rows, the elevator sized */
#define AES_ROM_FS_SEL            0xfe7b70   /* (row, state): the list's row changed and drawn; row 0 none */
#define AES_ROM_FS_NSCROLL        0xfe7b92   /* (tree, &row, top, count, arrow, n): scrolled n rows on the screen; the top */
#define AES_ROM_FS_NEWDIR         0xfe7cfa   /* (title, path, spec, tree, &count): a directory read, listed and drawn */
#define AES_ROM_DOS_SNEXT         0xfe3a46   /* Fsnext, then dos_sfirst's tail: 1 found; ENMFIL or EFILNF -> AES_DOS_AX 18 */
#define AES_ROM_DOS_CCONOUT       0xfe3bf6   /* Cconout through $fe3c28, over the character word its caller pushed */
#define AES_DOS_SNEXT_TRAP_RETURN 0xfe3a4e   /* dos_snext's `bsr __DOS` return: AES_TRAP1_RETURN's after it */
#define AES_FS_ACTIVE_SDTA_RETURN 0xfe784a   /* fs_active's return site from dos_sdta: what AES_DOS_RETURN holds after */
#define AES_FS_ACTIVE_BELL_RETURN 0xfe7910   /* ...and from the bell's Cconout */
#define AES_FS_INPUT_NEWDIR_RETURN 0xfe7fd6  /* fs_input, back from its fs_newdir: a directory read, listed and drawn */
#define AES_FS_INPUT_PASS         0xfe7ed8   /* fs_input's loop: the head of a pass */
#define AES_FS_INPUT_NO_READ      0xfe7fea   /* fs_input's pass, past the directory read: where a path already read arrives */
/* fs_input's return sites from dos_free — what AES_DOS_RETURN holds after each: its three blocks freed at its end, and
 * the one or two it frees where a later Malloc found no memory. */
#define AES_FS_INPUT_NAMES_ONLY_FREE_RETURN 0xfe7dd8   /* the names, the index refused */
#define AES_FS_INPUT_NAMES_FREE_RETURN_NO_DTA 0xfe7dfc /* the names, the DTA refused */
#define AES_FS_INPUT_INDEX_FREE_RETURN_NO_DTA 0xfe7e04 /* ...then the index */
#define AES_FS_INPUT_DTA_FREE_RETURN   0xfe82c2        /* at its end: the DTA */
#define AES_FS_INPUT_INDEX_FREE_RETURN 0xfe82ca        /* ...the index */
#define AES_FS_INPUT_NAMES_FREE_RETURN 0xfe82d2        /* ...the names */

#endif /* TOS102US_ADDRS_H */
