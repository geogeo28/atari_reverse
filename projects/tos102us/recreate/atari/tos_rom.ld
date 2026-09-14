/* tos_rom.ld — link the rebuilt TOS as a ROM image at 0xFC0000, not as a program.
 *
 * THIS IS NOT tos.ld. That one links a base-0 blob GEMDOS relocates as it loads a .PRG; this one
 * links code that is BURNED at a fixed address and is never relocated, so absolute addresses are
 * final and there is no relocation table to emit. The two live side by side in this directory
 * because both builds happen here: the ROM (this script) and the two conformance programs (tos.ld).
 *
 * THE IMAGE'S SIZE IS PRODUCED, NOT PADDED, and the MUPB is what produces it. 0xFEFFF4 plus the
 * block's twelve bytes is 0xFF0000, so the MUPB occupies the LAST twelve bytes of a 192 KB ROM —
 * measured in the original, whose own image ends `87 65 43 21 00 00 ca 00 00 fd 9e ca`. Placing it
 * at its fixed address therefore makes `objcopy -O binary` span 0xFC0000 to the end of the ROM and
 * fill the hole between the code and it with zeroes: exactly 196,608 bytes, no padding step. The
 * Makefile asserts the byte count anyway — a script that silently produced 191 KB would otherwise
 * reach Hatari as an unknown TOS image.
 *
 * .bss IS AT AN ABSOLUTE RAM ADDRESS AND IS NOT IN THE IMAGE. A ROM cannot carry writable data, so
 * anything the OS keeps in RAM is placed by hand at an address the OS owns (the original's OS
 * variables live below os_membot = 0x8900). The stub has no .bss at all and the ASSERT below keeps
 * it that way: the day a component needs one, that address is a decision to make deliberately, not
 * a section that quietly appeared inside the ROM.
 */
OUTPUT_FORMAT("elf32-m68k")
ENTRY(_reset)

ROM_BASE = 0xFC0000;
MUPB_ADDR = 0xFEFFF4;

SECTIONS
{
  . = ROM_BASE;

  /* The OS header has to be the first thing in the image: the machine takes its reset PC out of it
   * and Hatari identifies the ROM by it. KEEP, because nothing references `_os_header` by symbol. */
  .header : { KEEP(*(.header)) }

  .text : {
    *(.text .text.*)
    *(.rodata .rodata.*)
  }
  /* Its own output section purely so the ASSERT below can see it: folded into .text, an
   * initialised writable global would be indistinguishable from rodata to the linker. */
  .data : { *(.data .data.*) }
  _rom_code_end = .;

  .mupb MUPB_ADDR : { KEEP(*(.mupb)) }

  .bss (NOLOAD) : { *(.bss .bss.*) *(COMMON) }

  /DISCARD/ : { *(.comment) *(.note.*) *(.eh_frame) *(.debug_*) }
}

ASSERT(_rom_code_end <= MUPB_ADDR,
       "the ROM's code has grown past the MUPB at 0xFEFFF4")
ASSERT(SIZEOF(.bss) == 0,
       "a ROM cannot carry .bss — place the OS's RAM at an absolute address it owns")
/* An initialised non-const global is worse than a .bss one: the linker FREEZES its initial value
 * into the image and every store to it at run time is discarded by the ROM, so the program keeps
 * reading the value it was built with and nothing anywhere reports a fault. */
ASSERT(SIZEOF(.data) == 0,
       "a ROM cannot carry .data — make the global const, or place it in RAM the OS owns")
