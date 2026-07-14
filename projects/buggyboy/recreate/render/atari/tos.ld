/* tos.ld — link the demo at base 0 as one contiguous text+data blob (GEMDOS relocates at load).
 * rodata folds into text so it is reachable; .bss (the 1 MiB image) is zeroed by TOS. Packed
 * tight (no gaps) so a fixup's virtual address equals its byte offset in the flat binary. */
OUTPUT_FORMAT("elf32-m68k")
ENTRY(_start)
SECTIONS
{
  . = 0;
  .text : {
    *(.text._start)
    *(.text .text.*)
    *(.rodata .rodata.*)
  }
  .data : {
    *(.data .data.*)
    *(.got .got.*)
  }
  _bss_start = .;
  .bss : {
    *(.bss .bss.*)
    *(COMMON)
  }
  _bss_end = .;
  /DISCARD/ : { *(.comment) *(.note.*) *(.eh_frame) }
}
