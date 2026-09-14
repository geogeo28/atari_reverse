| header.S — the rebuilt ROM's OS header, its reset entry, and the GEM MUPB block.
|
| THE FIRST 0x30 BYTES ARE THE OS HEADER and every field carries the value read out of the user's
| own TOS102US.img (romdefs.h says which, and where they were measured). The reset entry has to land
| at exactly ROM_BASE + OS_ENTRY_OFFSET, because that address is also the os_start LONGWORD four
| bytes into the header: the two must agree or the machine jumps into the header. `.org` inside the
| header section is what makes them agree by construction, and the Makefile asserts the linked
| address of `_reset` afterwards, so a header that grows past 0x30 fails the build instead of the
| boot.
|
| WHAT THE 68000 DOES AT POWER-ON, and why the first instruction is a stack load: the ST maps the
| ROM's first eight bytes at address 0 while RESET is asserted, so the processor takes its initial
| SSP from ROM+0 (`60 2e 01 02` — the bra.s and the version word, i.e. garbage) and its initial PC
| from ROM+4 (os_start). The stack pointer is therefore never usable until we set it, which is what
| `_reset` does first.

#include "romdefs.h"

    .section .header, "ax"
    .globl  _os_header
_os_header:
    bra.s   _reset                      | os_entry:   the jump the header opens with
    .word   OS_VERSION                  | os_version
    .long   OS_START                    | os_start:   the reset PC
    .long   ROM_BASE                    | os_base
    .long   OS_MEMBOT                   | os_membot:  end of the OS's own RAM
    .long   OS_RSV1                     | os_rsv1
    .long   OS_MUPB                     | os_magic:   -> the MUPB below
    .long   OS_DATE_BCD                 | os_date:    mmddyyyy in BCD
    .word   OS_CONF                     | os_conf:    country and video standard
    .word   OS_DOSDATE                  | os_dosdate: the same day, FAT12-packed
    .long   OS_P_ROOT                   | p_root      } the four longwords TOS 1.02 added
    .long   OS_P_KBSHIFT                | pkbshift    } after os_dosdate; see romdefs.h
    .long   OS_P_RUN                    | p_run       }
    .long   OS_RSV2                     | p_rsv2      }

    .org    OS_ENTRY_OFFSET             | fails the assembly if the header above overran 0x30
    .globl  _reset
_reset:
    move.w  #0x2700,%sr                 | supervisor, every interrupt masked
    move.l  #STUB_STACK_TOP,%sp         | ...the SSP the ROM's first longword pretended to be
    move.b  #MEMCTRL_1MB,MEMCTRL        | size the RAM banks before anything reads RAM
    jsr     stub_boot                   | paint the bands; stub_boot never returns
_reset_hang:                            | ...and if a future edit lets it, stop here rather than run on
    bra.s   _reset_hang

| The GEM memory-usage parameter block, placed at OS_MUPB by tos_rom.ld. TOS publishes it through
| os_magic and a loader identifies a GEM-capable ROM by the magic longword.
    .section .mupb, "a"
    .globl  _os_mupb
_os_mupb:
    .long   MUPB_MAGIC
    .long   MUPB_UI_START
    .long   MUPB_END_OS
