/* tos.ld — link ZYNAPS.PRG at base 0 as one contiguous text+data blob (GEMDOS relocates at load).
 * rodata folds into text so it is reachable; .bss (the 1 MiB image) is zeroed by TOS. Packed
 * tight (no gaps) so a fixup's virtual address equals its byte offset in the flat binary.
 *
 * GEMDOS places BSS immediately after text+data (at tlen+dlen), so .bss MUST start there with no
 * gap. A BSS symbol with a large alignment would otherwise push .bss past the end of the emitted
 * binary, and every BSS access on-target would land at the wrong address. We force text+data — and
 * hence the whole load — to a 256-byte boundary and cap per-symbol alignment inside .bss at a WORD
 * (SUBALIGN 2), so .bss abuts text+data exactly.
 *
 * THE 256-BYTE LOAD BOUNDARY DOES NOT ALIGN THE IMAGE, and this project must not read it that way.
 * GEMDOS loads a .PRG at whatever the TPA gives, which is not 256-aligned, so the alignment forced
 * here is alignment WITHIN the emitted binary and nothing more (docs/on-target-execution.md, class
 * 8). Zynaps hands the shifter a framebuffer address, and an STF's video base register has no low
 * byte — so `zynaps_main.c` reserves slack and rounds the image's base up at RUN TIME, and reads
 * the result back through Physbase. That is the fix; this is not.
 *
 * IT IS SUBALIGN(2) AND NOT SUBALIGN(1), AND THE DIFFERENCE IS AN ADDRESS ERROR. Packing .bss at
 * BYTE granularity strips the word alignment the 68000 requires of every `move.w`/`move.l`, so a
 * longword in .bss lands on an odd address whenever the object before it has odd size, and the
 * program dies at its first store to it. Nothing in the C can defend against it, because SUBALIGN
 * overrides a variable's own `__attribute__((aligned))`. The cap costs at most one padding byte
 * per object and moves nothing else: the dot is already 256-aligned when `.bss` opens.
 *
 * COPIED FROM projects/wonderboy/recreate/atari/tos.ld (each sibling carries its own copy; see
 * mkprg.py's marker for why). It DIFFERS from that one in a single deliberate way: there is no
 * `KEEP(*atari_wonderboy_os.s.o(.text))`, because this build does not pass `--gc-sections` and the
 * KEEP is inert without the collector. Adopting that flag here means adding the KEEP for
 * `atari_zynaps_os.s.o` in the same change — every routine in that file is entered from an
 * exception vector or from GEMDOS at RUNTIME, which no relocation names.
 */
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
  . = ALIGN(256);              /* pad text+data to a 256 boundary so .bss abuts it AND stays aligned */
  _bss_start = .;
  .bss (NOLOAD) : SUBALIGN(2) {
    *(.bss .bss.*)
    *(COMMON)
  }
  _bss_end = .;
  /DISCARD/ : { *(.comment) *(.note.*) *(.eh_frame) }
}
