/* tos.ld — link the on-target program at base 0 as one contiguous text+data blob (GEMDOS relocates at load).
 * Copied from recreate/render/atari/tos.ld. rodata folds into text so it is reachable; .bss is
 * zeroed by TOS. Packed tight (no gaps) so a fixup's virtual address equals its byte offset in the
 * flat binary. text+data is padded to 256 and .bss abuts it (SUBALIGN 1) — see the recreate note. */
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
  . = ALIGN(256);
  _bss_start = .;
  .bss (NOLOAD) : SUBALIGN(1) {
    *(.bss .bss.*)
    *(COMMON)
  }
  _bss_end = .;
  /DISCARD/ : { *(.comment) *(.note.*) *(.eh_frame) }
}
