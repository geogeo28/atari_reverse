/* The test accessory's link (`test/aes_boot.py` builds it): one base-0 image GEMDOS relocates as it loads, the shape
 * atari/tos.ld gives the measurement programs — TEXT, DATA, then a BSS that abuts them, with the two symbols
 * atari/mkprg.py bounds a fixup's target by. */
OUTPUT_FORMAT("elf32-m68k")
ENTRY(_start)
SECTIONS
{
  . = 0;
  .text : { *(.text) }
  .data : { *(.data) }
  . = ALIGN(2);
  _bss_start = .;
  .bss (NOLOAD) : SUBALIGN(2) { *(.bss) *(COMMON) }
  _bss_end = .;
  /DISCARD/ : { *(.comment) *(.note.*) *(.eh_frame) }
}
