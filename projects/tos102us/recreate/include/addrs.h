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
#define CON_STATE_SPARE     0x2995     /* byte: Cursconf 6 writes it and 7 reads it back */
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
#define CURSCONF_HIDE         0        /* these two DRAW, and are not reconstructed here */
#define CURSCONF_SHOW         1
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
#define GEM_TRAP2_VDI_ARM     0xfe3eb8  /* everything else: `move.l SYSVAR_VDI_ENTRY,-(sp) / rts` */
#define SYSVAR_VDI_ENTRY      0x8c2a    /* long: where that arm jumps — $fc4ebc in this snapshot */

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
 * `include/mfp.h` carries that argument, and the bound on it.
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
                                        * `Xbtimer` never masked (`include/mfp.h`) */
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

#endif /* TOS102US_ADDRS_H */
